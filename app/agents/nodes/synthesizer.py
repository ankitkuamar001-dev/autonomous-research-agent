"""Phase 7: Knowledge Synthesis Node.

Organizes verified claims into themes, identifies patterns,
trends, contradictions, and emerging insights. This is the
"intelligence" layer — genuine synthesis, not summarization.
"""

from __future__ import annotations

import json

import structlog
from langchain_core.prompts import ChatPromptTemplate

from app.agents.state import AgentState
from app.models.fact import VerifiedClaim

logger = structlog.get_logger(__name__)

SYNTHESIS_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        "You are an expert research analyst who performs genuine knowledge synthesis. "
        "You do NOT merely summarize — you identify patterns, relationships, contradictions, "
        "and emerging insights across sources.\n\n"
        "Given a set of verified claims with confidence scores, organize them into "
        "coherent themes and provide deep analysis.\n\n"
        "For each theme, provide:\n"
        "- title: Theme name\n"
        "- summary: 2-3 sentence overview\n"
        "- key_claims: List of claim statements that belong to this theme\n"
        "- patterns: Patterns observed across claims\n"
        "- insights: Novel insights derived from combining claims\n"
        "- contradictions: Any contradictions within the theme\n"
        "- confidence: Overall theme confidence (average of claim confidences)\n"
        "- trend_direction: 'increasing', 'decreasing', 'stable', or 'emerging'\n\n"
        "Also provide:\n"
        "- cross_theme_insights: Insights that span multiple themes\n"
        "- knowledge_gaps: What the research could NOT answer\n"
        "- risk_factors: Potential risks or limitations\n\n"
        "Return a JSON object with 'themes' (array) and 'meta' (object with "
        "cross_theme_insights, knowledge_gaps, risk_factors).",
    ),
    (
        "human",
        "Research Question: {research_question}\n\n"
        "Verified Claims ({claim_count} total):\n{claims_text}\n\n"
        "Synthesize these claims into themes and insights.",
    ),
])


def _format_claims_for_prompt(claims: list[VerifiedClaim]) -> str:
    """Format verified claims for the synthesis prompt."""
    lines: list[str] = []
    for i, vc in enumerate(claims, 1):
        lines.append(
            f"{i}. [{vc.confidence:.1%} confidence] {vc.claim.statement}\n"
            f"   Sources: {', '.join(vc.claim.supporting_sources[:3])}"
            f"{'  ⚠️ CONTESTED' if vc.is_contested else ''}"
        )
    return "\n".join(lines)


async def synthesize_knowledge(state: AgentState) -> dict:
    """Organize verified claims into themes with genuine synthesis.

    Args:
        state: Must contain ``verified_claims``.

    Returns:
        Partial state with ``themes`` and ``current_phase``.
    """
    claims = state.get("verified_claims", [])
    query = state["research_query"]

    if not claims:
        logger.warning("no_claims_to_synthesize")
        return {
            "themes": [],
            "current_phase": "synthesis_complete",
            "errors": ["No verified claims to synthesize"],
        }

    # Focus on higher-quality claims for synthesis
    significant_claims = [c for c in claims if c.confidence >= 0.3]
    if not significant_claims:
        significant_claims = claims[:20]  # Fallback: use top 20

    logger.info(
        "synthesizing_knowledge",
        claim_count=len(significant_claims),
        high_confidence=sum(1 for c in significant_claims if c.confidence >= 0.7),
    )

    from app.services.llm_service import get_llm

    llm = get_llm(use_strong=True)  # Use stronger model for synthesis

    claims_text = _format_claims_for_prompt(significant_claims)

    chain = SYNTHESIS_PROMPT | llm

    try:
        response = await chain.ainvoke({
            "research_question": query.question,
            "claim_count": len(significant_claims),
            "claims_text": claims_text,
        })

        content = response.content if hasattr(response, "content") else str(response)

        # Parse the JSON response
        text = content.strip()
        if "```" in text:
            parts = text.split("```")
            for part in parts[1:]:
                if part.strip().startswith("json"):
                    text = part.strip()[4:].strip()
                    break
                elif part.strip().startswith("{"):
                    text = part.strip()
                    break

        result = json.loads(text)

        themes = result.get("themes", [])
        meta = result.get("meta", {})

        # Enrich themes with metadata
        for theme in themes:
            if "cross_theme_insights" not in theme:
                theme["cross_theme_insights"] = meta.get("cross_theme_insights", [])
            if "knowledge_gaps" not in theme:
                theme["knowledge_gaps"] = meta.get("knowledge_gaps", [])
            if "risk_factors" not in theme:
                theme["risk_factors"] = meta.get("risk_factors", [])

        # Add meta as a special theme for the reporter
        if meta:
            themes.append({
                "title": "_meta",
                "cross_theme_insights": meta.get("cross_theme_insights", []),
                "knowledge_gaps": meta.get("knowledge_gaps", []),
                "risk_factors": meta.get("risk_factors", []),
            })

        logger.info(
            "synthesis_complete",
            theme_count=len([t for t in themes if t.get("title") != "_meta"]),
        )

        return {
            "themes": themes,
            "current_phase": "synthesis_complete",
        }

    except Exception as e:
        logger.error("synthesis_failed", error=str(e))

        # Fallback: create a single theme from all claims
        fallback_theme = {
            "title": "Key Findings",
            "summary": f"Analysis of {len(significant_claims)} verified claims.",
            "key_claims": [c.claim.statement for c in significant_claims[:10]],
            "patterns": [],
            "insights": [],
            "contradictions": [],
            "confidence": sum(c.confidence for c in significant_claims) / len(significant_claims),
            "trend_direction": "stable",
        }

        return {
            "themes": [fallback_theme],
            "current_phase": "synthesis_complete",
            "errors": [f"Synthesis degraded: {e}"],
        }
