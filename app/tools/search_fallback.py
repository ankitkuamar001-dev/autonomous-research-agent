"""DuckDuckGo search fallback — zero API key required.

Used automatically when Tavily is not configured or returns no results.
Uses the duckduckgo_search package (DDGS class).
"""

from __future__ import annotations

import asyncio
from urllib.parse import urlparse

import structlog

from app.models.source import ContentType, SourceMetadata

logger = structlog.get_logger(__name__)

# Domain → ContentType mapping (mirrors discoverer.py)
_DOMAIN_TYPES: dict[str, ContentType] = {
    "arxiv.org": ContentType.ACADEMIC_PAPER,
    "pubmed.ncbi.nlm.nih.gov": ContentType.ACADEMIC_PAPER,
    "ieee.org": ContentType.ACADEMIC_PAPER,
    "acm.org": ContentType.ACADEMIC_PAPER,
    "nature.com": ContentType.ACADEMIC_PAPER,
    "science.org": ContentType.ACADEMIC_PAPER,
    "springer.com": ContentType.ACADEMIC_PAPER,
    "mckinsey.com": ContentType.INDUSTRY_REPORT,
    "gartner.com": ContentType.INDUSTRY_REPORT,
    "deloitte.com": ContentType.INDUSTRY_REPORT,
    "wikipedia.org": ContentType.WIKI,
    "medium.com": ContentType.BLOG_POST,
    "dev.to": ContentType.BLOG_POST,
    "substack.com": ContentType.BLOG_POST,
}


def _classify_url(url: str) -> tuple[str, ContentType]:
    """Extract domain and classify content type from URL."""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower().removeprefix("www.")
    except Exception:
        return "", ContentType.UNKNOWN

    for pattern, ctype in _DOMAIN_TYPES.items():
        if domain.endswith(pattern):
            return domain, ctype

    if domain.endswith(".gov"):
        return domain, ContentType.GOVERNMENT_REPORT
    if domain.endswith(".edu"):
        return domain, ContentType.ACADEMIC_PAPER
    if url.lower().endswith(".pdf"):
        return domain, ContentType.PDF

    return domain, ContentType.UNKNOWN


class DuckDuckGoSearchTool:
    """Free web search using DuckDuckGo — no API key required.

    Used as a fallback when Tavily is unconfigured or returns no results.
    """

    async def search(
        self,
        query: str,
        max_results: int = 5,
    ) -> list[SourceMetadata]:
        """Search DuckDuckGo and return SourceMetadata objects.

        Runs DDGS synchronously in a thread pool to keep the event loop free.
        Returns an empty list on any error.
        """
        try:
            from duckduckgo_search import DDGS
        except ImportError:
            logger.warning(
                "duckduckgo_search_not_installed",
                hint="Run: pip install duckduckgo-search",
            )
            return []

        def _sync_search() -> list[dict]:
            try:
                with DDGS() as ddgs:
                    return list(ddgs.text(query, max_results=max_results))
            except Exception as e:
                logger.warning("ddg_search_error", error=str(e)[:200])
                return []

        try:
            raw_results = await asyncio.to_thread(_sync_search)
        except Exception as e:
            logger.warning("ddg_thread_error", error=str(e))
            return []

        sources: list[SourceMetadata] = []
        for item in raw_results:
            url = item.get("href") or item.get("url", "")
            if not url:
                continue

            domain, content_type = _classify_url(url)
            snippet = item.get("body") or item.get("snippet", "")

            sources.append(
                SourceMetadata(
                    url=url,
                    title=item.get("title", domain),
                    domain=domain,
                    snippet=snippet[:500],
                    content_type=content_type,
                    published_date=None,
                    author=None,
                )
            )

        logger.info("ddg_search_complete", query=query[:60], results=len(sources))
        return sources
