"""Phase 4: Content Retrieval Node.

Fetches full-text content for ranked sources using the web scraper
and PDF reader tools. Handles errors gracefully and marks failed sources.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import structlog

from app.agents.state import AgentState
from app.config import get_settings
from app.models.source import Source, SourceStatus

logger = structlog.get_logger(__name__)


async def retrieve_content(state: AgentState) -> dict:
    """Fetch full content for each ranked source.

    Args:
        state: Must contain ``ranked_sources``.

    Returns:
        Partial state with ``retrieved_sources`` and ``current_phase``.
    """
    ranked = state.get("ranked_sources", [])

    if not ranked:
        logger.warning("no_sources_to_retrieve")
        return {
            "retrieved_sources": [],
            "current_phase": "retrieval_complete",
            "errors": ["No ranked sources to retrieve"],
        }

    settings = get_settings()
    logger.info("retrieving_content", source_count=len(ranked))

    from app.tools.scraper import WebScraperTool
    from app.tools.pdf_reader import PDFReaderTool

    scraper = WebScraperTool()
    pdf_reader = PDFReaderTool()
    semaphore = asyncio.Semaphore(settings.scrape_concurrency)

    async def _retrieve_one(source: Source) -> Source:
        async with semaphore:
            url = source.metadata.url
            try:
                # Check if it's a PDF
                if url.lower().endswith(".pdf") or source.metadata.content_type.value == "pdf":
                    result = await pdf_reader.extract_to_source(
                        url, existing_metadata=source.metadata
                    )
                else:
                    result = await scraper.scrape_single_url(url)

                # Use the result if it has usable content
                if result.is_usable:
                    # Preserve our scoring from the ranking phase
                    result.score = source.score
                    return result
                else:
                    source.status = SourceStatus.FAILED
                    source.error = result.error or "Insufficient content extracted"

            except Exception as e:
                logger.warning("retrieval_failed", url=url, error=str(e))
                source.status = SourceStatus.FAILED
                source.error = str(e)

            return source

    # Retrieve all in parallel
    tasks = [_retrieve_one(s) for s in ranked]
    retrieved = await asyncio.gather(*tasks)

    # Separate successes and failures
    successes = [s for s in retrieved if s.is_usable]
    failures = [s for s in retrieved if not s.is_usable]

    logger.info(
        "retrieval_complete",
        successful=len(successes),
        failed=len(failures),
        total_words=sum(s.word_count for s in successes),
    )

    errors = [
        f"Failed to retrieve {s.metadata.url}: {s.error}"
        for s in failures
        if s.error
    ]

    return {
        "retrieved_sources": successes,
        "current_phase": "retrieval_complete",
        "errors": errors[:10],  # Cap error messages
    }
