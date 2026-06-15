"""Phase 2: Web Discovery Node.

Executes search queries from the research plan to discover candidate sources.
Uses Tavily as the primary search engine with deduplication.
"""

from __future__ import annotations

import asyncio
from urllib.parse import urlparse

import structlog

from app.agents.state import AgentState
from app.config import get_settings
from app.models.source import ContentType, SourceMetadata

logger = structlog.get_logger(__name__)

# Domain → ContentType mapping for classification
DOMAIN_TYPES: dict[str, ContentType] = {
    "arxiv.org": ContentType.ACADEMIC_PAPER,
    "scholar.google.com": ContentType.ACADEMIC_PAPER,
    "pubmed.ncbi.nlm.nih.gov": ContentType.ACADEMIC_PAPER,
    "ieee.org": ContentType.ACADEMIC_PAPER,
    "acm.org": ContentType.ACADEMIC_PAPER,
    "nature.com": ContentType.ACADEMIC_PAPER,
    "science.org": ContentType.ACADEMIC_PAPER,
    "springer.com": ContentType.ACADEMIC_PAPER,
    "gov": ContentType.GOVERNMENT_REPORT,
    "mckinsey.com": ContentType.INDUSTRY_REPORT,
    "deloitte.com": ContentType.INDUSTRY_REPORT,
    "gartner.com": ContentType.INDUSTRY_REPORT,
    "forrester.com": ContentType.INDUSTRY_REPORT,
    "wikipedia.org": ContentType.WIKI,
    "medium.com": ContentType.BLOG_POST,
    "dev.to": ContentType.BLOG_POST,
    "substack.com": ContentType.BLOG_POST,
}


def _classify_domain(url: str) -> tuple[str, ContentType]:
    """Extract domain and classify content type."""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower().removeprefix("www.")
    except Exception:
        return "", ContentType.UNKNOWN

    # Check exact domain matches
    for pattern, ctype in DOMAIN_TYPES.items():
        if domain.endswith(pattern):
            return domain, ctype

    # Check TLD-based rules
    if domain.endswith(".gov"):
        return domain, ContentType.GOVERNMENT_REPORT
    if domain.endswith(".edu"):
        return domain, ContentType.ACADEMIC_PAPER

    # URL heuristics
    if url.lower().endswith(".pdf"):
        return domain, ContentType.PDF

    return domain, ContentType.UNKNOWN


def _deduplicate_sources(sources: list[SourceMetadata]) -> list[SourceMetadata]:
    """Remove duplicate sources by normalized URL."""
    seen: set[str] = set()
    unique: list[SourceMetadata] = []
    for src in sources:
        normalized = src.url.rstrip("/").lower()
        if normalized not in seen:
            seen.add(normalized)
            unique.append(src)
    return unique


async def discover_sources(state: AgentState) -> dict:
    """Execute search queries and collect candidate sources.

    Args:
        state: Must contain ``research_plan`` with search queries.

    Returns:
        Partial state with ``discovered_sources`` and ``current_phase``.
    """
    plan = state.get("research_plan")
    query = state["research_query"]

    if not plan or not plan.search_queries:
        logger.error("no_search_queries")
        return {
            "discovered_sources": [],
            "current_phase": "discovery_failed",
            "errors": ["No search queries available"],
        }

    logger.info(
        "discovering_sources",
        query_count=len(plan.search_queries),
        depth=query.depth.value,
    )

    settings = get_settings()
    all_sources: list[SourceMetadata] = []

    # Import search tool
    from app.tools.search import TavilySearchTool

    search_tool = TavilySearchTool()
    max_results_per_query = max(3, settings.get_max_sources(query.depth.value) // len(plan.search_queries))

    # Execute searches concurrently with rate limiting
    semaphore = asyncio.Semaphore(settings.search_max_per_minute)

    async def _search(search_query: str) -> list[SourceMetadata]:
        async with semaphore:
            try:
                results = await search_tool.search(
                    query=search_query,
                    max_results=max_results_per_query,
                )
                # TavilySearchTool.search() returns list[SourceMetadata] directly
                return results
            except Exception as e:
                logger.warning("search_failed", query=search_query, error=str(e))
                return []

    tasks = [_search(q) for q in plan.search_queries]
    results = await asyncio.gather(*tasks)

    for result_list in results:
        all_sources.extend(result_list)

    # Deduplicate
    unique_sources = _deduplicate_sources(all_sources)

    # Apply source restrictions
    if query.source_restrictions:
        filtered = [
            s for s in unique_sources
            if any(r.lower() in s.domain.lower() for r in query.source_restrictions)
        ]
        if filtered:
            unique_sources = filtered

    logger.info(
        "discovery_complete",
        total_found=len(all_sources),
        unique_sources=len(unique_sources),
    )

    return {
        "discovered_sources": unique_sources,
        "current_phase": "discovery_complete",
    }
