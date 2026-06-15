"""LangGraph StateGraph — wires the 8 research phases into a DAG.

This is the central orchestration module. It builds a compiled graph
that can be invoked with ``await graph.ainvoke(initial_state)``.
"""

from __future__ import annotations

import uuid
from typing import Any

import structlog
from langgraph.graph import END, StateGraph

from app.agents.nodes.discoverer import discover_sources
from app.agents.nodes.extractor import extract_information
from app.agents.nodes.planner import plan_research
from app.agents.nodes.ranker import rank_sources
from app.agents.nodes.reporter import generate_report
from app.agents.nodes.retriever import retrieve_content
from app.agents.nodes.synthesizer import synthesize_knowledge
from app.agents.nodes.verifier import verify_claims
from app.agents.state import AgentState
from app.models.research import ResearchQuery

logger = structlog.get_logger(__name__)


def _should_continue_after_discovery(state: AgentState) -> str:
    """Route after discovery: proceed if sources found, else end."""
    sources = state.get("discovered_sources", [])
    if not sources:
        logger.warning("no_sources_discovered_aborting")
        return "generate_report"  # Jump to report (will note failure)
    return "rank_sources"


def _should_continue_after_ranking(state: AgentState) -> str:
    """Route after ranking: proceed if ranked sources exist."""
    ranked = state.get("ranked_sources", [])
    if not ranked:
        return "generate_report"
    return "retrieve_content"


def _should_continue_after_retrieval(state: AgentState) -> str:
    """Route after retrieval: proceed if content was fetched."""
    retrieved = state.get("retrieved_sources", [])
    if not retrieved:
        return "generate_report"
    return "extract_information"


def _should_continue_after_extraction(state: AgentState) -> str:
    """Route after extraction: proceed if facts were found."""
    facts = state.get("extracted_facts", [])
    if not facts:
        return "generate_report"
    return "verify_claims"


def _should_continue_after_verification(state: AgentState) -> str:
    """Route after verification: proceed to synthesis."""
    claims = state.get("verified_claims", [])
    if not claims:
        return "generate_report"
    return "synthesize_knowledge"


def build_research_graph() -> StateGraph:
    """Build the LangGraph research workflow.

    Returns:
        Compiled StateGraph ready for invocation.
    """
    graph = StateGraph(AgentState)

    # ── Add nodes ───────────────────────────────────────────────
    graph.add_node("plan_research", plan_research)
    graph.add_node("discover_sources", discover_sources)
    graph.add_node("rank_sources", rank_sources)
    graph.add_node("retrieve_content", retrieve_content)
    graph.add_node("extract_information", extract_information)
    graph.add_node("verify_claims", verify_claims)
    graph.add_node("synthesize_knowledge", synthesize_knowledge)
    graph.add_node("generate_report", generate_report)

    # ── Set entry point ─────────────────────────────────────────
    graph.set_entry_point("plan_research")

    # ── Add edges ───────────────────────────────────────────────
    # Phase 1 → Phase 2 (always)
    graph.add_edge("plan_research", "discover_sources")

    # Phase 2 → Phase 3 or Report (conditional)
    graph.add_conditional_edges(
        "discover_sources",
        _should_continue_after_discovery,
        {
            "rank_sources": "rank_sources",
            "generate_report": "generate_report",
        },
    )

    # Phase 3 → Phase 4 or Report
    graph.add_conditional_edges(
        "rank_sources",
        _should_continue_after_ranking,
        {
            "retrieve_content": "retrieve_content",
            "generate_report": "generate_report",
        },
    )

    # Phase 4 → Phase 5 or Report
    graph.add_conditional_edges(
        "retrieve_content",
        _should_continue_after_retrieval,
        {
            "extract_information": "extract_information",
            "generate_report": "generate_report",
        },
    )

    # Phase 5 → Phase 6 or Report
    graph.add_conditional_edges(
        "extract_information",
        _should_continue_after_extraction,
        {
            "verify_claims": "verify_claims",
            "generate_report": "generate_report",
        },
    )

    # Phase 6 → Phase 7 or Report
    graph.add_conditional_edges(
        "verify_claims",
        _should_continue_after_verification,
        {
            "synthesize_knowledge": "synthesize_knowledge",
            "generate_report": "generate_report",
        },
    )

    # Phase 7 → Phase 8 (always)
    graph.add_edge("synthesize_knowledge", "generate_report")

    # Phase 8 → END
    graph.add_edge("generate_report", END)

    return graph


async def run_research(
    query: ResearchQuery,
    session_id: str | None = None,
) -> AgentState:
    """Execute the full research workflow.

    Args:
        query: The research question and parameters.
        session_id: Optional session ID for caching/persistence.

    Returns:
        Final AgentState with the completed report.
    """
    if session_id is None:
        session_id = str(uuid.uuid4())

    logger.info(
        "starting_research",
        question=query.question,
        depth=query.depth.value,
        session_id=session_id,
    )

    graph = build_research_graph()
    compiled = graph.compile()

    initial_state: dict[str, Any] = {
        "research_query": query,
        "research_plan": None,
        "discovered_sources": [],
        "ranked_sources": [],
        "retrieved_sources": [],
        "extracted_facts": [],
        "verified_claims": [],
        "themes": [],
        "report": None,
        "references": [],
        "current_phase": "starting",
        "errors": [],
        "session_id": session_id,
    }

    final_state = await compiled.ainvoke(initial_state)

    logger.info(
        "research_complete",
        session_id=session_id,
        phase=final_state.get("current_phase"),
        errors=len(final_state.get("errors", [])),
    )

    return final_state
