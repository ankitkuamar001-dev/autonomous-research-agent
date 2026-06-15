"""PDF text extraction tool using PyMuPDF (fitz).

Extracts text, metadata, and structural information from PDF files — both local
paths and remote URLs (downloaded asynchronously via httpx).
"""

from __future__ import annotations

import asyncio
import re
import tempfile
from pathlib import Path
from typing import Optional

import fitz  # PyMuPDF
import httpx
import logging
import structlog
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
    before_sleep_log,
)

from app.config import get_settings
from app.models.source import Source, SourceMetadata, SourceStatus, ContentType

logger = structlog.get_logger(__name__)

# ── Constants ───────────────────────────────────────────────────────────────

_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)

_MAX_PDF_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB


# ── Exceptions ──────────────────────────────────────────────────────────────

class PDFReadError(Exception):
    """Raised when a PDF cannot be read or parsed."""


# ── Data containers ─────────────────────────────────────────────────────────

class PDFContent:
    """Container for extracted PDF content and metadata."""

    __slots__ = (
        "text", "title", "author", "page_count",
        "word_count", "creation_date", "file_path",
    )

    def __init__(
        self,
        text: str,
        title: str = "",
        author: str = "",
        page_count: int = 0,
        word_count: int = 0,
        creation_date: str | None = None,
        file_path: str = "",
    ) -> None:
        self.text = text
        self.title = title
        self.author = author
        self.page_count = page_count
        self.word_count = word_count
        self.creation_date = creation_date
        self.file_path = file_path


# ── PDFReaderTool ───────────────────────────────────────────────────────────

class PDFReaderTool:
    """Async PDF reader that extracts text and metadata from local or remote PDFs.

    Features
    --------
    - Downloads remote PDFs via httpx with retry + timeout.
    - Extracts text per-page using PyMuPDF for high fidelity.
    - Pulls metadata (title, author, creation date) from the PDF catalog.
    - Runs CPU-bound PDF parsing in a thread pool to avoid blocking the event loop.
    - Converts results to Source models for pipeline integration.

    Usage
    -----
    >>> reader = PDFReaderTool()
    >>> content = await reader.extract_from_url("https://example.com/paper.pdf")
    >>> print(content.text[:500])
    """

    def __init__(self, download_timeout: float = 60.0) -> None:
        self._download_timeout = download_timeout
        self._log = logger.bind(tool="PDFReaderTool")

    # ── Public API ──────────────────────────────────────────────

    async def extract_from_path(self, file_path: str | Path) -> PDFContent:
        """Extract text and metadata from a local PDF file.

        Parameters
        ----------
        file_path:
            Absolute or relative path to the PDF file.

        Returns
        -------
        PDFContent
            Extracted text, metadata, and statistics.

        Raises
        ------
        PDFReadError
            If the file doesn't exist or cannot be parsed.
        """
        path = Path(file_path)
        if not path.exists():
            raise PDFReadError(f"PDF file not found: {path}")
        if not path.suffix.lower() == ".pdf":
            raise PDFReadError(f"Not a PDF file: {path}")

        self._log.info("pdf_read_local", path=str(path))

        # Run blocking PDF parsing in a thread
        loop = asyncio.get_running_loop()
        content = await loop.run_in_executor(None, self._parse_pdf, str(path))
        content.file_path = str(path)

        self._log.info(
            "pdf_read_complete",
            path=str(path),
            pages=content.page_count,
            words=content.word_count,
        )
        return content

    async def extract_from_url(self, url: str) -> PDFContent:
        """Download and extract text from a remote PDF.

        Parameters
        ----------
        url:
            The URL pointing to a PDF file.

        Returns
        -------
        PDFContent
            Extracted text, metadata, and statistics.

        Raises
        ------
        PDFReadError
            If the download fails or the content is not a valid PDF.
        """
        self._log.info("pdf_download_start", url=url)

        pdf_bytes = await self._download_pdf(url)

        # Write to a temp file for PyMuPDF (it needs a file path or bytes)
        loop = asyncio.get_running_loop()
        content = await loop.run_in_executor(
            None, self._parse_pdf_from_bytes, pdf_bytes
        )
        content.file_path = url

        self._log.info(
            "pdf_download_complete",
            url=url,
            pages=content.page_count,
            words=content.word_count,
        )
        return content

    async def extract_to_source(
        self,
        url_or_path: str,
        existing_metadata: SourceMetadata | None = None,
    ) -> Source:
        """Extract PDF and wrap in a Source model for pipeline integration.

        Parameters
        ----------
        url_or_path:
            A URL or local file path to a PDF.
        existing_metadata:
            Optional pre-existing metadata (e.g. from a search result).

        Returns
        -------
        Source
            Source with extracted content and metadata, status set accordingly.
        """
        try:
            if url_or_path.startswith(("http://", "https://")):
                content = await self.extract_from_url(url_or_path)
            else:
                content = await self.extract_from_path(url_or_path)

            # Build or enrich metadata
            metadata = existing_metadata or SourceMetadata(
                url=url_or_path,
                content_type=ContentType.PDF,
            )
            if not metadata.title and content.title:
                metadata = metadata.model_copy(update={"title": content.title})
            if not metadata.author and content.author:
                metadata = metadata.model_copy(update={"author": content.author})
            if not metadata.published_date and content.creation_date:
                metadata = metadata.model_copy(
                    update={"published_date": content.creation_date}
                )

            from datetime import datetime, timezone

            return Source(
                metadata=metadata,
                raw_content=content.text[:50_000],
                clean_content=content.text,
                word_count=content.word_count,
                status=SourceStatus.RETRIEVED,
                retrieved_at=datetime.now(timezone.utc),
            )

        except Exception as exc:
            self._log.warning(
                "pdf_extract_to_source_failed",
                url_or_path=url_or_path,
                error=str(exc),
            )
            metadata = existing_metadata or SourceMetadata(
                url=url_or_path, content_type=ContentType.PDF
            )
            return Source(
                metadata=metadata,
                status=SourceStatus.FAILED,
                error=str(exc),
            )

    # ── Download ────────────────────────────────────────────────

    @retry(
        retry=retry_if_exception_type((httpx.TransportError, httpx.TimeoutException)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=20),
        before_sleep=before_sleep_log(logger, logging.INFO),  # type: ignore[arg-type]
        reraise=True,
    )
    async def _download_pdf(self, url: str) -> bytes:
        """Download a PDF from a URL with retry."""
        async with httpx.AsyncClient(
            headers={"User-Agent": _USER_AGENT},
            follow_redirects=True,
            timeout=httpx.Timeout(self._download_timeout, connect=15.0),
        ) as client:
            response = await client.get(url)
            response.raise_for_status()

            # Validate size
            if len(response.content) > _MAX_PDF_SIZE_BYTES:
                raise PDFReadError(
                    f"PDF exceeds max size ({len(response.content)} bytes > "
                    f"{_MAX_PDF_SIZE_BYTES} bytes)"
                )

            # Basic PDF signature check
            if not response.content[:5].startswith(b"%PDF"):
                content_type = response.headers.get("content-type", "")
                if "pdf" not in content_type.lower():
                    raise PDFReadError(
                        f"Response is not a PDF (content-type: {content_type})"
                    )

            return response.content

    # ── PDF parsing (synchronous, run in executor) ──────────────

    def _parse_pdf(self, file_path: str) -> PDFContent:
        """Parse a local PDF file and extract text + metadata."""
        try:
            doc = fitz.open(file_path)
        except Exception as exc:
            raise PDFReadError(f"Cannot open PDF: {exc}") from exc

        return self._extract_from_document(doc)

    def _parse_pdf_from_bytes(self, pdf_bytes: bytes) -> PDFContent:
        """Parse PDF from raw bytes."""
        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        except Exception as exc:
            raise PDFReadError(f"Cannot parse PDF bytes: {exc}") from exc

        return self._extract_from_document(doc)

    def _extract_from_document(self, doc: fitz.Document) -> PDFContent:
        """Extract text, metadata, and stats from an opened fitz.Document."""
        try:
            # Extract text page-by-page
            pages_text: list[str] = []
            for page_num in range(len(doc)):
                page = doc[page_num]
                text = page.get_text("text")
                if text.strip():
                    pages_text.append(text.strip())

            full_text = "\n\n".join(pages_text)

            # Normalise whitespace
            full_text = re.sub(r"\n{3,}", "\n\n", full_text)
            full_text = re.sub(r"[ \t]{2,}", " ", full_text)

            # Extract metadata
            meta = doc.metadata or {}
            title = meta.get("title", "") or ""
            author = meta.get("author", "") or ""
            creation_date = meta.get("creationDate", "") or None

            # Clean PyMuPDF date format (D:20231015...)
            if creation_date and creation_date.startswith("D:"):
                creation_date = creation_date[2:10]  # YYYYMMDD
                try:
                    from datetime import datetime
                    dt = datetime.strptime(creation_date, "%Y%m%d")
                    creation_date = dt.strftime("%Y-%m-%d")
                except ValueError:
                    pass

            word_count = len(full_text.split())

            return PDFContent(
                text=full_text,
                title=title,
                author=author,
                page_count=len(doc),
                word_count=word_count,
                creation_date=creation_date,
            )
        finally:
            doc.close()
