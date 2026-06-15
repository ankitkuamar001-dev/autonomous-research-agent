"""Async web scraper with concurrency control, HTML cleaning, and metadata extraction.

Scrapes web pages using httpx with configurable concurrency limits (asyncio.Semaphore),
strips non-content elements (nav, script, style, ads), extracts metadata from meta tags,
and returns cleaned text content mapped to Source models.
"""

from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

import httpx
import logging
import structlog
from bs4 import BeautifulSoup, Tag
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
    before_sleep_log,
)

from app.config import get_settings
from app.models.source import Source, SourceMetadata, SourceStatus

logger = structlog.get_logger(__name__)

# ── Constants ───────────────────────────────────────────────────────────────

_UNWANTED_TAGS = frozenset({
    "script", "style", "nav", "footer", "iframe", "aside",
    "header", "noscript", "svg", "form", "button",
})

_AD_CLASSES = frozenset({
    "ad", "ads", "advert", "advertisement", "banner",
    "sponsor", "promo", "sidebar", "popup", "cookie",
    "newsletter", "social-share", "share-buttons",
})

_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)


# ── Exceptions ──────────────────────────────────────────────────────────────

class ScraperError(Exception):
    """Raised when scraping a single URL fails after retries."""


# ── WebScraperTool ──────────────────────────────────────────────────────────

class WebScraperTool:
    """Async web scraper with concurrency control and intelligent content extraction.

    Features
    --------
    - Semaphore-controlled concurrency to avoid overwhelming servers.
    - Automatic removal of non-content HTML (scripts, nav, ads, sidebars).
    - Metadata extraction from ``<meta>`` tags and ``<title>``.
    - Retry with exponential backoff on transient HTTP errors.
    - Realistic User-Agent header to avoid bot blocking.

    Usage
    -----
    >>> scraper = WebScraperTool()
    >>> sources = await scraper.scrape_urls(["https://example.com"])
    >>> for src in sources:
    ...     print(src.clean_content[:200])
    """

    def __init__(
        self,
        concurrency: int | None = None,
        timeout: float | None = None,
    ) -> None:
        settings = get_settings()
        self._concurrency = concurrency or settings.scrape_concurrency
        self._timeout = timeout or float(settings.scrape_timeout_seconds)
        self._semaphore = asyncio.Semaphore(self._concurrency)
        self._log = logger.bind(tool="WebScraperTool")

    # ── Public API ──────────────────────────────────────────────

    async def scrape_urls(
        self,
        urls: list[str],
        *,
        existing_metadata: dict[str, SourceMetadata] | None = None,
    ) -> list[Source]:
        """Scrape multiple URLs concurrently and return Source models.

        Parameters
        ----------
        urls:
            List of URLs to scrape.
        existing_metadata:
            Optional mapping of URL → pre-populated SourceMetadata (e.g. from search).
            If a URL has existing metadata, the scraper enriches rather than replaces it.

        Returns
        -------
        list[Source]
            One Source per URL, with status indicating success or failure.
        """
        existing_metadata = existing_metadata or {}
        self._log.info("scrape_batch_start", url_count=len(urls))

        async with httpx.AsyncClient(
            limits=httpx.Limits(
                max_connections=self._concurrency,
                max_keepalive_connections=self._concurrency // 2 or 1,
            ),
            headers={"User-Agent": _USER_AGENT},
            follow_redirects=True,
            timeout=httpx.Timeout(self._timeout, connect=10.0),
        ) as client:
            tasks = [
                self._scrape_single(client, url, existing_metadata.get(url))
                for url in urls
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        sources: list[Source] = []
        for url, result in zip(urls, results):
            if isinstance(result, Exception):
                self._log.warning("scrape_url_exception", url=url, error=str(result))
                sources.append(self._make_failed_source(url, str(result)))
            else:
                sources.append(result)

        ok = sum(1 for s in sources if s.status == SourceStatus.RETRIEVED)
        self._log.info(
            "scrape_batch_complete",
            total=len(sources),
            succeeded=ok,
            failed=len(sources) - ok,
        )
        return sources

    async def scrape_single_url(self, url: str) -> Source:
        """Convenience method to scrape a single URL.

        Parameters
        ----------
        url:
            The URL to scrape.

        Returns
        -------
        Source
            The scraped Source (check ``.status`` for success/failure).
        """
        results = await self.scrape_urls([url])
        return results[0]

    # ── Internal helpers ────────────────────────────────────────

    async def _scrape_single(
        self,
        client: httpx.AsyncClient,
        url: str,
        metadata: SourceMetadata | None,
    ) -> Source:
        """Scrape one URL, guarded by the concurrency semaphore."""
        async with self._semaphore:
            self._log.debug("scrape_start", url=url)
            try:
                raw_html = await self._fetch_page(client, url)
                soup = BeautifulSoup(raw_html, "lxml")

                # Extract metadata from the page itself
                page_meta = self._extract_metadata(soup, url)

                # Merge with pre-existing search metadata
                if metadata:
                    page_meta = self._merge_metadata(metadata, page_meta)

                # Clean HTML and extract text
                self._remove_unwanted_elements(soup)
                clean_text = self._extract_clean_text(soup)

                word_count = len(clean_text.split())

                source = Source(
                    metadata=page_meta,
                    raw_content=raw_html[:50_000],  # cap raw content storage
                    clean_content=clean_text,
                    word_count=word_count,
                    status=SourceStatus.RETRIEVED,
                    retrieved_at=datetime.now(timezone.utc),
                )
                self._log.info(
                    "scrape_success", url=url, word_count=word_count,
                )
                return source

            except Exception as exc:
                self._log.warning("scrape_failed", url=url, error=str(exc))
                return self._make_failed_source(url, str(exc), metadata)

    @retry(
        retry=retry_if_exception_type((httpx.TransportError, httpx.TimeoutException)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=15),
        before_sleep=before_sleep_log(logger, logging.INFO),  # type: ignore[arg-type]
        reraise=True,
    )
    async def _fetch_page(self, client: httpx.AsyncClient, url: str) -> str:
        """Fetch a single page with tenacity retry."""
        response = await client.get(url)
        response.raise_for_status()

        content_type = response.headers.get("content-type", "")
        if "text/html" not in content_type and "text/plain" not in content_type:
            raise ScraperError(
                f"Non-HTML content type: {content_type} for {url}"
            )

        return response.text

    # ── HTML cleaning ───────────────────────────────────────────

    def _remove_unwanted_elements(self, soup: BeautifulSoup) -> None:
        """Remove scripts, styles, nav, ads, and other non-content elements in-place."""
        # Remove unwanted tags entirely
        for tag in soup.find_all(list(_UNWANTED_TAGS)):
            tag.decompose()

        # Remove elements with ad-related class names
        for element in soup.find_all(True):
            if not isinstance(element, Tag):
                continue
            classes = " ".join(element.get("class", []))  # type: ignore[arg-type]
            element_id = element.get("id", "") or ""
            combined = f"{classes} {element_id}".lower()
            if any(ad_cls in combined for ad_cls in _AD_CLASSES):
                element.decompose()

    def _extract_clean_text(self, soup: BeautifulSoup) -> str:
        """Extract readable text from cleaned HTML.

        Preserves paragraph boundaries as newlines and collapses whitespace.
        """
        # Get the main content area if identifiable
        main_content = (
            soup.find("main")
            or soup.find("article")
            or soup.find("div", {"role": "main"})
            or soup.find("div", class_=re.compile(r"content|post|article|entry", re.I))
            or soup.body
            or soup
        )

        # Extract text with paragraph separators
        lines: list[str] = []
        for element in main_content.find_all(  # type: ignore[union-attr]
            ["p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "td", "th", "blockquote", "pre"]
        ):
            text = element.get_text(separator=" ", strip=True)
            if text and len(text) > 10:
                lines.append(text)

        # Fallback: if structured extraction yields very little, use raw text
        full_text = "\n\n".join(lines)
        if len(full_text) < 200:
            full_text = main_content.get_text(separator="\n", strip=True)  # type: ignore[union-attr]

        # Normalise whitespace
        full_text = re.sub(r"\n{3,}", "\n\n", full_text)
        full_text = re.sub(r"[ \t]{2,}", " ", full_text)
        return full_text.strip()

    # ── Metadata extraction ─────────────────────────────────────

    def _extract_metadata(self, soup: BeautifulSoup, url: str) -> SourceMetadata:
        """Extract metadata from HTML meta tags, Open Graph, and title."""
        title = ""
        author = ""
        published_date: str | None = None
        description = ""

        # Title: prefer og:title, then <title>
        og_title = soup.find("meta", property="og:title")
        if og_title and isinstance(og_title, Tag):
            title = str(og_title.get("content", ""))
        if not title:
            title_tag = soup.find("title")
            if title_tag:
                title = title_tag.get_text(strip=True)

        # Author
        author_meta = soup.find("meta", attrs={"name": "author"})
        if author_meta and isinstance(author_meta, Tag):
            author = str(author_meta.get("content", ""))

        # Published date: several conventions
        for attr_name in ("article:published_time", "og:published_time", "date"):
            meta = soup.find("meta", attrs={"property": attr_name}) or soup.find(
                "meta", attrs={"name": attr_name}
            )
            if meta and isinstance(meta, Tag):
                published_date = str(meta.get("content", ""))
                break
        if not published_date:
            time_tag = soup.find("time")
            if time_tag and isinstance(time_tag, Tag):
                published_date = str(time_tag.get("datetime", "")) or time_tag.get_text(strip=True)

        # Description / snippet
        desc_meta = soup.find("meta", attrs={"name": "description"}) or soup.find(
            "meta", property="og:description"
        )
        if desc_meta and isinstance(desc_meta, Tag):
            description = str(desc_meta.get("content", ""))

        # Domain
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.removeprefix("www.")
        except Exception:
            domain = ""

        return SourceMetadata(
            url=url,
            title=title,
            snippet=description,
            author=author,
            published_date=published_date if published_date else None,
            domain=domain,
        )

    def _merge_metadata(
        self, existing: SourceMetadata, page_meta: SourceMetadata
    ) -> SourceMetadata:
        """Merge pre-existing search metadata with page-extracted metadata.

        Page-extracted values fill in blanks; search metadata takes priority when
        both are present (since search snippets are usually higher quality).
        """
        return SourceMetadata(
            url=existing.url,
            title=existing.title or page_meta.title,
            snippet=existing.snippet or page_meta.snippet,
            author=existing.author or page_meta.author,
            published_date=existing.published_date or page_meta.published_date,
            domain=existing.domain or page_meta.domain,
            content_type=existing.content_type,
            search_query=existing.search_query,
        )

    def _make_failed_source(
        self,
        url: str,
        error: str,
        metadata: SourceMetadata | None = None,
    ) -> Source:
        """Create a Source in FAILED status."""
        if not metadata:
            try:
                domain = urlparse(url).netloc.removeprefix("www.")
            except Exception:
                domain = ""
            metadata = SourceMetadata(url=url, domain=domain)

        return Source(
            metadata=metadata,
            status=SourceStatus.FAILED,
            error=error,
        )
