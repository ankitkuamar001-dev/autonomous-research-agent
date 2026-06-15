"""Phase 3: Source Ranking Node.

Scores and ranks discovered sources by authority, relevance, freshness,
and domain trust. Filters out low-quality sources.
"""

from __future__ import annotations

from datetime import datetime, timezone

import structlog

from app.agents.state import AgentState
from app.config import get_settings
from app.models.source import ContentType, Source, SourceMetadata, SourceScore, SourceStatus

logger = structlog.get_logger(__name__)

# Hardcoded domain trust scores (0–1)
DOMAIN_TRUST: dict[str, float] = {
    # Academic & Research
    "arxiv.org": 0.95,
    "scholar.google.com": 0.90,
    "pubmed.ncbi.nlm.nih.gov": 0.95,
    "ieee.org": 0.95,
    "acm.org": 0.95,
    "nature.com": 0.95,
    "science.org": 0.95,
    "springer.com": 0.90,
    "researchgate.net": 0.75,
    # Government
    "whitehouse.gov": 0.90,
    "nih.gov": 0.95,
    "cdc.gov": 0.90,
    "nist.gov": 0.90,
    # Industry Research
    "mckinsey.com": 0.85,
    "deloitte.com": 0.80,
    "gartner.com": 0.85,
    "forrester.com": 0.80,
    "hbr.org": 0.85,
    "mit.edu": 0.90,
    "stanford.edu": 0.90,
    # News & Tech
    "reuters.com": 0.85,
    "bbc.com": 0.80,
    "nytimes.com": 0.80,
    "techcrunch.com": 0.70,
    "wired.com": 0.70,
    "arstechnica.com": 0.75,
    "theverge.com": 0.65,
    # Reference
    "wikipedia.org": 0.60,
    "stackoverflow.com": 0.65,
    # Blogs (lower trust)
    "medium.com": 0.40,
    "dev.to": 0.45,
    "substack.com": 0.45,
    "wordpress.com": 0.30,
    "blogspot.com": 0.25,
}

# Content type authority bonuses
CONTENT_TYPE_BONUS: dict[ContentType, float] = {
    ContentType.ACADEMIC_PAPER: 0.30,
    ContentType.GOVERNMENT_REPORT: 0.25,
    ContentType.INDUSTRY_REPORT: 0.20,
    ContentType.NEWS_ARTICLE: 0.05,
    ContentType.DOCUMENTATION: 0.10,
    ContentType.WIKI: 0.00,
    ContentType.BLOG_POST: -0.10,
    ContentType.PDF: 0.10,
    ContentType.UNKNOWN: 0.00,
}


def _get_domain_trust(domain: str) -> float:
    """Look up domain trust score with TLD fallback."""
    # Exact match
    if domain in DOMAIN_TRUST:
        return DOMAIN_TRUST[domain]

    # Check if any known domain is a suffix
    for known, score in DOMAIN_TRUST.items():
        if domain.endswith(f".{known}") or domain == known:
            return score

    # TLD-based defaults
    if domain.endswith(".gov"):
        return 0.80
    if domain.endswith(".edu"):
        return 0.80
    if domain.endswith(".org"):
        return 0.50

    # Unknown domain
    return 0.35


def _score_freshness(published_date: str | None) -> float:
    """Score based on publication recency. More recent = higher score."""
    if not published_date:
        return 0.3  # Unknown date gets a middling score

    try:
        # Try common date formats
        for fmt in ("%Y-%m-%d", "%Y-%m", "%Y", "%B %d, %Y", "%d %B %Y"):
            try:
                pub = datetime.strptime(published_date, fmt).replace(tzinfo=timezone.utc)
                break
            except ValueError:
                continue
        else:
            return 0.3

        now = datetime.now(timezone.utc)
        days_old = (now - pub).days

        if days_old <= 30:
            return 1.0
        if days_old <= 90:
            return 0.9
        if days_old <= 180:
            return 0.8
        if days_old <= 365:
            return 0.7
        if days_old <= 730:
            return 0.5
        return 0.3

    except Exception:
        return 0.3


def _score_source(source: SourceMetadata, research_question: str) -> SourceScore:
    """Compute multi-dimensional score for a source."""
    # Domain trust
    domain_trust = _get_domain_trust(source.domain)

    # Authority = domain trust + content type bonus
    type_bonus = CONTENT_TYPE_BONUS.get(source.content_type, 0.0)
    authority = min(1.0, max(0.0, domain_trust + type_bonus))

    # Relevance — keyword overlap between snippet and research question
    q_words = set(research_question.lower().split())
    snippet_words = set(source.snippet.lower().split()) if source.snippet else set()
    if q_words:
        overlap = len(q_words & snippet_words) / len(q_words)
        relevance = min(1.0, overlap * 1.5)  # Scale up, cap at 1.0
    else:
        relevance = 0.5

    # Freshness
    freshness = _score_freshness(source.published_date)

    return SourceScore(
        authority=authority,
        relevance=relevance,
        freshness=freshness,
        domain_trust=domain_trust,
    )


async def rank_sources(state: AgentState) -> dict:
    """Score and rank discovered sources, filtering low quality.

    Args:
        state: Must contain ``discovered_sources``.

    Returns:
        Partial state with ``ranked_sources`` and ``current_phase``.
    """
    discovered = state.get("discovered_sources", [])
    query = state["research_query"]
    settings = get_settings()

    if not discovered:
        logger.warning("no_sources_to_rank")
        return {
            "ranked_sources": [],
            "current_phase": "ranking_complete",
            "errors": ["No sources discovered to rank"],
        }

    logger.info("ranking_sources", count=len(discovered))

    # Score all sources
    scored_sources: list[Source] = []
    for meta in discovered:
        score = _score_source(meta, query.question)
        source = Source(
            metadata=meta,
            score=score,
            status=SourceStatus.RANKED,
        )
        scored_sources.append(source)

    # Sort by composite score (descending)
    scored_sources.sort(key=lambda s: s.score.composite, reverse=True)

    # Filter by minimum composite threshold
    min_threshold = 0.20
    filtered = [s for s in scored_sources if s.score.composite >= min_threshold]

    # Limit to max sources for depth level
    max_sources = settings.get_max_sources(query.depth.value)
    selected = filtered[:max_sources]

    # Mark rejected sources
    rejected_count = len(scored_sources) - len(selected)

    logger.info(
        "ranking_complete",
        total=len(scored_sources),
        selected=len(selected),
        rejected=rejected_count,
        top_score=selected[0].score.composite if selected else 0,
    )

    return {
        "ranked_sources": selected,
        "current_phase": "ranking_complete",
    }
