"""Web search tool powered by Tavily with rate limiting, retries, and fallback.

Provides async search capabilities with automatic rate limiting (semaphore-based),
exponential backoff retries via tenacity, and structured result mapping to
SourceMetadata models. Falls back to DuckDuckGo when Tavily is unconfigured
or returns no results.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional
from urllib.parse import urlparse

import structlog
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.config import get_settings
from app.models.source import ContentType, SourceMetadata
from app.tools.search_fallback import DuckDuckGoSearchTool

logger = structlog.get_logger(__name__)


# ── Exceptions ──────────────────────────────────────────────────────────────

class SearchError(Exception):
    """Raised when a search operation fails after all retries."""


class SearchRateLimitError(Exception):
    """Raised when the per-minute rate limit is exceeded."""


# ── Domain classification helpers ───────────────────────────────────────────

_ACADEMIC_DOMAINS = frozenset({
    "arxiv.org", "scholar.google.com", "pubmed.ncbi.nlm.nih.gov",
    "doi.org", "semanticscholar.org", "researchgate.net", "jstor.org",
    "springer.com", "nature.com", "sciencedirect.com", "ieee.org",
    "acm.org", "wiley.com", "plos.org",
})

_GOV_DOMAINS = frozenset({
    ".gov", ".gov.uk", ".gov.au", ".gc.ca", ".europa.eu",
})

_NEWS_DOMAINS = frozenset({
    "reuters.com", "bbc.com", "bbc.co.uk", "nytimes.com",
    "washingtonpost.com", "theguardian.com", "apnews.com", "bloomberg.com",
    "cnbc.com", "techcrunch.com", "arstechnica.com", "wired.com",
})

_WIKI_DOMAINS = frozenset({
    "wikipedia.org", "en.wikipedia.org",
})


def _classify_domain(domain: str) -> ContentType:
    """Heuristically classify a domain into a ContentType."""
    domain_lower = domain.lower()

    if domain_lower in _ACADEMIC_DOMAINS or any(
        d in domain_lower for d in ("arxiv", "pubmed", "scholar", "doi.org")
    ):
        return ContentType.ACADEMIC_PAPER
    if any(domain_lower.endswith(g) for g in _GOV_DOMAINS):
        return ContentType.GOVERNMENT_REPORT
    if domain_lower in _NEWS_DOMAINS:
        return ContentType.NEWS_ARTICLE
    if domain_lower in _WIKI_DOMAINS:
        return ContentType.WIKI
    if any(kw in domain_lower for kw in ("blog", "medium.com", "substack")):
        return ContentType.BLOG_POST
    if any(kw in domain_lower for kw in ("docs.", "readthedocs", "documentation")):
        return ContentType.DOCUMENTATION

    return ContentType.UNKNOWN


# ── Sliding-window rate limiter ─────────────────────────────────────────────

class _SlidingWindowRateLimiter:
    """Sliding-window rate limiter enforcing *max_calls* per *window_seconds*."""

    def __init__(self, max_calls: int, window_seconds: float = 60.0) -> None:
        self._max_calls = max_calls
        self._window = window_seconds
        self._timestamps: list[float] = []
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            # Purge expired timestamps
            cutoff = now - self._window
            self._timestamps = [t for t in self._timestamps if t > cutoff]

            if len(self._timestamps) >= self._max_calls:
                wait_for = self._timestamps[0] - cutoff
                logger.warning(
                    "search_rate_limit_hit",
                    current_count=len(self._timestamps),
                    wait_seconds=round(wait_for, 2),
                )
                await asyncio.sleep(wait_for)
                # Re-purge after sleeping
                now = time.monotonic()
                cutoff = now - self._window
                self._timestamps = [t for t in self._timestamps if t > cutoff]

            self._timestamps.append(time.monotonic())


# ── TavilySearchTool ────────────────────────────────────────────────────────

class TavilySearchTool:
    """Async web search tool backed by the Tavily API.

    Features
    --------
    - Per-minute sliding-window rate limiter.
    - Automatic retries with exponential backoff (tenacity).
    - Result mapping to ``SourceMetadata`` models with domain classification.
    - Graceful degradation — falls back to DuckDuckGo when Tavily is
      unconfigured or returns no results; returns empty list on persistent failure.

    Usage
    -----
    >>> tool = TavilySearchTool()
    >>> results = await tool.search("latest advances in quantum computing", max_results=5)
    """

    def __init__(self, api_key: str | None = None) -> None:
        settings = get_settings()
        self._api_key = api_key or settings.tavily_api_key
        self._ddg_fallback = DuckDuckGoSearchTool()
        self._log = logger.bind(tool="TavilySearchTool")

        if self._api_key:
            from tavily import AsyncTavilyClient  # type: ignore[import]

            self._client: Optional[object] = AsyncTavilyClient(api_key=self._api_key)
            self._rate_limiter = _SlidingWindowRateLimiter(
                max_calls=settings.search_max_per_minute, window_seconds=60.0
            )
        else:
            logger.warning(
                "tavily_api_key_missing",
                detail="Tavily disabled — all searches will use DuckDuckGo fallback.",
            )
            self._client = None
            self._rate_limiter = _SlidingWindowRateLimiter(max_calls=60)

    # ── Public API ──────────────────────────────────────────────

    async def search(
        self,
        query: str,
        *,
        max_results: int = 10,
        include_raw_content: bool = False,
        search_depth: str = "basic",
        include_domains: list[str] | None = None,
        exclude_domains: list[str] | None = None,
    ) -> list[SourceMetadata]:
        """Execute a web search and return structured metadata.

        Parameters
        ----------
        query:
            The search query string.
        max_results:
            Maximum number of results to return (1-20).
        include_raw_content:
            Whether to request full page content from Tavily.
        search_depth:
            ``"basic"`` (fast) or ``"advanced"`` (deeper, slower).
        include_domains:
            Only include results from these domains.
        exclude_domains:
            Exclude results from these domains.

        Returns
        -------
        list[SourceMetadata]
            Ranked list of source metadata objects (may be empty on failure).
        """
        self._log.info("search_start", query=query, max_results=max_results)

        # ── No Tavily key → go straight to DDG ──────────────────
        if not self._api_key or self._client is None:
            logger.warning("tavily_empty_using_ddg", query=query)
            return await self._ddg_fallback.search(query, max_results=max_results)

        # ── Try Tavily first ─────────────────────────────────────
        try:
            await self._rate_limiter.acquire()
            raw_results = await self._execute_search(
                query=query,
                max_results=max_results,
                include_raw_content=include_raw_content,
                search_depth=search_depth,
                include_domains=include_domains,
                exclude_domains=exclude_domains,
            )
            sources = self._map_results(raw_results, query)
            self._log.info("search_complete", query=query, result_count=len(sources))

            # ── Tavily returned nothing → fallback ───────────────
            if not sources:
                logger.warning("tavily_empty_using_ddg", query=query)
                return await self._ddg_fallback.search(query, max_results=max_results)

            return sources

        except Exception:
            self._log.exception("search_failed", query=query)
            return []

    async def multi_search(
        self,
        queries: list[str],
        *,
        max_results_per_query: int = 10,
        include_domains: list[str] | None = None,
        exclude_domains: list[str] | None = None,
    ) -> list[SourceMetadata]:
        """Execute multiple search queries concurrently and deduplicate results.

        Parameters
        ----------
        queries:
            List of search query strings.
        max_results_per_query:
            Maximum results per individual query.
        include_domains:
            Only include results from these domains.
        exclude_domains:
            Exclude results from these domains.

        Returns
        -------
        list[SourceMetadata]
            Deduplicated list of source metadata across all queries.
        """
        self._log.info("multi_search_start", query_count=len(queries))

        tasks = [
            self.search(
                q,
                max_results=max_results_per_query,
                include_domains=include_domains,
                exclude_domains=exclude_domains,
            )
            for q in queries
        ]
        all_results = await asyncio.gather(*tasks, return_exceptions=True)

        # Flatten + deduplicate by URL
        seen_urls: set[str] = set()
        deduplicated: list[SourceMetadata] = []

        for result_set in all_results:
            if isinstance(result_set, Exception):
                self._log.warning("multi_search_partial_failure", error=str(result_set))
                continue
            for source in result_set:
                if source.url not in seen_urls:
                    seen_urls.add(source.url)
                    deduplicated.append(source)

        self._log.info(
            "multi_search_complete",
            query_count=len(queries),
            total_results=len(deduplicated),
        )
        return deduplicated

    # ── Internal helpers ────────────────────────────────────────

    @retry(
        retry=retry_if_exception_type((Exception,)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        before_sleep=before_sleep_log(logger, logging.INFO),  # type: ignore[arg-type]
        reraise=True,
    )
    async def _execute_search(
        self,
        *,
        query: str,
        max_results: int,
        include_raw_content: bool,
        search_depth: str,
        include_domains: list[str] | None,
        exclude_domains: list[str] | None,
    ) -> list[dict]:
        """Call the Tavily API with tenacity retries."""
        kwargs: dict = {
            "query": query,
            "max_results": min(max_results, 20),
            "include_raw_content": include_raw_content,
            "search_depth": search_depth,
        }
        if include_domains:
            kwargs["include_domains"] = include_domains
        if exclude_domains:
            kwargs["exclude_domains"] = exclude_domains

        response = await self._client.search(**kwargs)  # type: ignore[union-attr]
        return response.get("results", [])

    def _map_results(
        self, raw_results: list[dict], query: str
    ) -> list[SourceMetadata]:
        """Convert raw Tavily results into SourceMetadata models."""
        sources: list[SourceMetadata] = []

        for item in raw_results:
            url: str = item.get("url", "")
            if not url:
                continue

            try:
                parsed = urlparse(url)
                domain = parsed.netloc.removeprefix("www.")
            except Exception:
                domain = ""

            title = item.get("title", "") or ""
            snippet = item.get("content", "") or ""
            content_type = _classify_domain(domain)

            # Detect PDF links
            if url.lower().endswith(".pdf"):
                content_type = ContentType.PDF

            source = SourceMetadata(
                url=url,
                title=title,
                snippet=snippet,
                domain=domain,
                content_type=content_type,
                search_query=query,
            )
            sources.append(source)

        return sources
