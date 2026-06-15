"""Phase 6: Cross-Source Verification Node — Enhanced.

Improvements over v1:
- Parallel asyncio.gather() for all verification LLM calls
- Semaphore-bounded concurrency (5 concurrent calls)
- Capped at 20 claims to avoid quota exhaustion
- Better error isolation: one failed claim doesn't block others
"""

from __future__ import annotations

import asyncio
import json

import structlog
from langchain_core.prompts import ChatPromptTemplate

from app.agents.state import AgentState
from app.models.fact import Claim, Fact, VerifiedClaim

logger = structlog.get_logger(__name__)

VERIFICATION_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        "You are a rigorous fact-checker and verification expert. "
        "Your job is to assess the confidence level of claims based on evidence.\n\n"
        "Given a claim and the evidence for and against it, provide:\n"
        "1. confidence: A score from 0.0 to 1.0\n"
        "2. verification_notes: Brief explanation of your assessment\n"
        "3. is_contested: Whether credible sources disagree\n"
        "4. importance: How important this claim is (0.0-1.0)\n\n"
        "Scoring guidelines:\n"
        "- Single source, no corroboration: 0.2-0.4\n"
        "- Two independent sources agree: 0.5-0.7\n"
        "- Three or more independent sources: 0.7-0.9\n"
        "- Academic/government sources add +0.1 bonus\n"
        "- Contradicting sources reduce by 0.1-0.2\n"
        "- Statistical claims with cited data: +0.1\n\n"
        "Return ONLY a JSON object with: confidence, verification_notes, is_contested, importance",
    ),
    (
        "human",
        "Research Question: {research_question}\n\n"
        "Claim: {claim}\n\n"
        "Supporting Evidence ({support_count} sources):\n{supporting_evidence}\n\n"
        "Contradicting Evidence ({contradict_count} sources):\n{contradicting_evidence}\n\n"
        "Assess this claim's reliability.",
    ),
])


def _group_related_facts(facts: list[Fact]) -> list[list[Fact]]:
    """Group facts by similarity using Jaccard keyword overlap."""
    if not facts:
        return []

    groups: list[list[Fact]] = []
    used: set[int] = set()

    for i, fact in enumerate(facts):
        if i in used:
            continue

        group = [fact]
        used.add(i)
        fact_words = set(fact.statement.lower().split())

        for j, other in enumerate(facts):
            if j in used or j <= i:
                continue

            other_words = set(other.statement.lower().split())
            if fact_words and other_words:
                overlap = len(fact_words & other_words)
                union = len(fact_words | other_words)
                similarity = overlap / union if union > 0 else 0

                if similarity > 0.25:
                    group.append(other)
                    used.add(j)

        groups.append(group)

    return groups


def _build_claim(group: list[Fact]) -> Claim:
    """Build a Claim from a group of related facts."""
    group.sort(key=lambda f: f.confidence, reverse=True)
    primary = group[0]

    supporting = list({f.source_url for f in group})
    related = [f.statement for f in group[1:]]

    return Claim(
        statement=primary.statement,
        supporting_sources=supporting,
        contradicting_sources=[],
        related_facts=related,
    )


async def verify_claims(state: AgentState) -> dict:
    """Cross-verify extracted facts with parallel LLM calls.

    Improvements:
    - All verification calls run concurrently with asyncio.gather()
    - Semaphore limits to 5 concurrent LLM requests
    - Capped at 20 claims to protect quota

    Args:
        state: Must contain ``extracted_facts``.

    Returns:
        Partial state with ``verified_claims`` and ``current_phase``.
    """
    facts = state.get("extracted_facts", [])
    query = state["research_query"]

    if not facts:
        logger.warning("no_facts_to_verify")
        return {
            "verified_claims": [],
            "current_phase": "verification_complete",
            "errors": ["No facts available for verification"],
        }

    logger.info("verifying_claims", fact_count=len(facts))

    # Group related facts → claims
    groups = _group_related_facts(facts)
    logger.info("fact_groups_created", group_count=len(groups))

    claims = [_build_claim(group) for group in groups]

    # Cap to avoid quota exhaustion — take most supported claims first
    MAX_CLAIMS = 20
    if len(claims) > MAX_CLAIMS:
        claims = sorted(claims, key=lambda c: len(c.supporting_sources), reverse=True)[:MAX_CLAIMS]
        logger.info("claims_capped", capped_at=MAX_CLAIMS)

    # Get LLM once outside the tasks
    from app.services.llm_service import get_llm
    llm = get_llm()

    semaphore = asyncio.Semaphore(5)

    async def _verify_one(claim: Claim) -> VerifiedClaim:
        async with semaphore:
            try:
                supporting_text = "\n".join(
                    f"- Source: {url}" for url in claim.supporting_sources
                )
                if claim.related_facts:
                    supporting_text += "\nRelated statements:\n" + "\n".join(
                        f"- {f}" for f in claim.related_facts[:5]
                    )

                contradicting_text = "No contradicting evidence found."
                if claim.contradicting_sources:
                    contradicting_text = "\n".join(
                        f"- Source: {url}" for url in claim.contradicting_sources
                    )

                chain = VERIFICATION_PROMPT | llm
                response = await chain.ainvoke({
                    "research_question": query.question,
                    "claim": claim.statement,
                    "support_count": len(claim.supporting_sources),
                    "supporting_evidence": supporting_text,
                    "contradict_count": len(claim.contradicting_sources),
                    "contradicting_evidence": contradicting_text,
                })

                content = (
                    response.content if hasattr(response, "content") else str(response)
                )

                # Parse JSON
                text = content.strip()
                text = text.replace("```json", "").replace("```", "").strip()
                # Find first {...} block
                import re
                match = re.search(r"\{.*\}", text, re.DOTALL)
                if match:
                    text = match.group(0)

                result = json.loads(text)
                confidence = min(1.0, max(0.0, float(result.get("confidence", 0.5))))
                notes = result.get("verification_notes", "")
                is_contested = bool(result.get("is_contested", False))
                importance = min(1.0, max(0.0, float(result.get("importance", 0.5))))

            except Exception as e:
                logger.warning(
                    "verification_failed",
                    claim=claim.statement[:80],
                    error=str(e)[:120],
                )
                n_sources = len(claim.supporting_sources)
                confidence = min(0.9, 0.2 + n_sources * 0.2)
                notes = f"Heuristic score ({n_sources} supporting sources)"
                is_contested = len(claim.contradicting_sources) > 0
                importance = 0.5

            return VerifiedClaim(
                claim=claim,
                confidence=confidence,
                verification_notes=notes,
                is_contested=is_contested,
                importance=importance,
            )

    # Run all verifications in parallel
    verified_claims: list[VerifiedClaim] = await asyncio.gather(
        *[_verify_one(claim) for claim in claims],
        return_exceptions=False,
    )

    # Sort by importance × confidence descending
    verified_claims.sort(
        key=lambda vc: vc.importance * vc.confidence,
        reverse=True,
    )

    logger.info(
        "verification_complete",
        total_claims=len(verified_claims),
        high_confidence=sum(1 for vc in verified_claims if vc.confidence >= 0.7),
        contested=sum(1 for vc in verified_claims if vc.is_contested),
    )

    return {
        "verified_claims": verified_claims,
        "current_phase": "verification_complete",
    }
