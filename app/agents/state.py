"""Central agent state flowing through the LangGraph workflow.

Every node reads from and writes partial updates to this state.
We use Annotated types with reducer functions so that list fields
accumulate rather than overwrite.
"""

from __future__ import annotations

import operator
from typing import Annotated, Optional, TypedDict

from app.models.citation import Reference
from app.models.fact import Fact, VerifiedClaim
from app.models.report import Report
from app.models.research import ResearchPlan, ResearchQuery
from app.models.source import Source, SourceMetadata


class AgentState(TypedDict, total=False):
    """Immutable state that flows through the research workflow.

    Fields marked with ``Annotated[..., operator.add]`` are *additive*:
    each node can return a partial list and LangGraph will concatenate
    it onto the existing value rather than replacing it.
    """

    # ── Input ───────────────────────────────────────────────────
    research_query: ResearchQuery

    # ── Phase 1: Planning ───────────────────────────────────────
    research_plan: Optional[ResearchPlan]

    # ── Phase 2: Discovery ──────────────────────────────────────
    discovered_sources: Annotated[list[SourceMetadata], operator.add]

    # ── Phase 3: Ranking ────────────────────────────────────────
    ranked_sources: list[Source]

    # ── Phase 4: Retrieval ──────────────────────────────────────
    retrieved_sources: list[Source]

    # ── Phase 5: Extraction ─────────────────────────────────────
    extracted_facts: Annotated[list[Fact], operator.add]

    # ── Phase 6: Verification ───────────────────────────────────
    verified_claims: list[VerifiedClaim]

    # ── Phase 7: Synthesis ──────────────────────────────────────
    themes: list[dict]

    # ── Phase 8: Report ─────────────────────────────────────────
    report: Optional[Report]
    references: list[Reference]

    # ── Metadata ────────────────────────────────────────────────
    current_phase: str
    errors: Annotated[list[str], operator.add]
    session_id: str
