"""Research orchestration service.

Builds the full LangGraph workflow, wires up all agent nodes, and
executes the end-to-end research pipeline from question to report.
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Callable, Coroutine, Optional

import structlog
from langgraph.graph import END, StateGraph

from app.agents.state import AgentState
from app.config import get_settings
from app.memory.checkpointer import get_checkpointer
from app.memory.vector_store import VectorStore
from app.memory.cache import ResearchCache
from app.models.report import Report
from app.models.research import ResearchQuery
from app.services.llm_service import LLMService

logger = structlog.get_logger(__name__)

# Type alias for status callbacks
StatusCallback = Callable[[str, dict[str, Any]], Coroutine[Any, Any, None]]


async def _noop_status(phase: str, data: dict[str, Any]) -> None:
    """Default no-op status callback."""


class ResearchService:
    """Orchestrates the full research pipeline via LangGraph.

    Usage::

        service = ResearchService()
        report = await service.run_research(
            query=ResearchQuery(question="...", depth="standard"),
            on_status=my_status_handler,
        )
    """

    def __init__(
        self,
        llm_service: LLMService | None = None,
    ) -> None:
        self._settings = get_settings()
        self._llm_service = llm_service or LLMService()

    # ── Public API ──────────────────────────────────────────────

    async def run_research(
        self,
        query: ResearchQuery,
        on_status: StatusCallback | None = None,
        session_id: str | None = None,
    ) -> Report:
        """Execute the complete research workflow.

        Parameters
        ----------
        query:
            The user's research query.
        on_status:
            Async callback invoked when the workflow transitions between
            phases.  Receives ``(phase_name, metadata_dict)``.
        session_id:
            Optional session identifier.  Generated if not provided.

        Returns
        -------
        Report
            The final research report.
        """
        status_cb = on_status or _noop_status
        session_id = session_id or str(uuid.uuid4())
        start_time = time.time()

        logger.info(
            "research_started",
            question=query.question[:120],
            depth=query.depth.value,
            session_id=session_id,
        )
        await status_cb("initializing", {"session_id": session_id})

        # ── Build infrastructure ────────────────────────────────
        vector_store = VectorStore(session_id=session_id)
        cache = ResearchCache()
        await cache.init()

        try:
            # ── Build & compile graph ───────────────────────────
            graph = self._build_graph(vector_store, cache, status_cb)
            checkpointer = await get_checkpointer()
            app = graph.compile(checkpointer=checkpointer)

            # ── Prepare initial state ───────────────────────────
            initial_state: AgentState = {
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
                "current_phase": "planning",
                "errors": [],
                "session_id": session_id,
            }

            config = {"configurable": {"thread_id": session_id}}

            # ── Execute the workflow ────────────────────────────
            await status_cb("executing", {"phase": "planning"})
            final_state: dict[str, Any] | None = None

            async for state_update in app.astream(
                initial_state,
                config=config,
                stream_mode="values",
            ):
                current_phase = state_update.get("current_phase", "unknown")
                await status_cb("phase_update", {"phase": current_phase})
                final_state = state_update

            # ── Extract report ──────────────────────────────────
            elapsed = time.time() - start_time

            if final_state and final_state.get("report"):
                report: Report = final_state["report"]
                report.generation_time_seconds = elapsed
                logger.info(
                    "research_completed",
                    session_id=session_id,
                    elapsed_seconds=round(elapsed, 2),
                    sections=len(report.sections),
                    sources_used=report.total_sources_used,
                )
                await status_cb("completed", {
                    "session_id": session_id,
                    "elapsed_seconds": round(elapsed, 2),
                })
                return report

            # Fallback: construct a minimal report from available state
            report = self._build_fallback_report(query, final_state, elapsed)
            logger.warning(
                "research_completed_with_fallback",
                session_id=session_id,
                errors=final_state.get("errors", []) if final_state else [],
            )
            await status_cb("completed_with_errors", {
                "session_id": session_id,
                "errors": final_state.get("errors", []) if final_state else [],
            })
            return report

        finally:
            await cache.close()

    # ── Graph Construction ──────────────────────────────────────

    def _build_graph(
        self,
        vector_store: VectorStore,
        cache: ResearchCache,
        status_cb: StatusCallback,
    ) -> StateGraph:
        """Construct the LangGraph research workflow.

        The graph follows this pipeline::

            plan → discover → rank → retrieve → extract → verify → synthesize → report

        Each node is a thin wrapper that delegates to the appropriate
        agent node function (to be implemented in ``app.agents.nodes``).
        """
        graph = StateGraph(AgentState)

        # ── Define nodes ────────────────────────────────────────
        async def plan_node(state: AgentState) -> dict[str, Any]:
            """Generate a research plan from the query."""
            from app.prompts.planner import PLANNER_PROMPT

            await status_cb("planning", {"question": state["research_query"].question})

            llm = self._llm_service.get_structured_llm(
                pydantic_model=__import__("app.models.research", fromlist=["ResearchPlan"]).ResearchPlan,
                model_name=self._settings.fast_llm_model,
            )

            query = state["research_query"]
            settings = self._settings

            prompt = PLANNER_PROMPT.format_messages(
                question=query.question,
                depth=query.depth.value,
                min_queries=settings.get_max_queries(query.depth.value) // 2,
                max_queries=settings.get_max_queries(query.depth.value),
            )

            try:
                plan = await llm.ainvoke(prompt)
                logger.info(
                    "plan_generated",
                    sub_questions=len(plan.sub_questions),
                    search_queries=len(plan.search_queries),
                )
                return {
                    "research_plan": plan,
                    "current_phase": "discovery",
                }
            except Exception as e:
                logger.error("planning_failed", error=str(e))
                return {
                    "errors": [f"Planning failed: {e}"],
                    "current_phase": "discovery",
                }

        async def discover_node(state: AgentState) -> dict[str, Any]:
            """Search for sources using the research plan queries."""
            await status_cb("discovering", {
                "queries": len(state.get("research_plan", {}).search_queries)
                if state.get("research_plan") else 0,
            })

            # Placeholder — actual search implementation lives in agents/nodes/
            logger.info("discover_node_executed")
            return {"current_phase": "ranking"}

        async def rank_node(state: AgentState) -> dict[str, Any]:
            """Score and rank discovered sources."""
            await status_cb("ranking", {
                "source_count": len(state.get("discovered_sources", [])),
            })

            logger.info("rank_node_executed")
            return {"current_phase": "retrieval"}

        async def retrieve_node(state: AgentState) -> dict[str, Any]:
            """Fetch full content from top-ranked sources."""
            await status_cb("retrieving", {
                "source_count": len(state.get("ranked_sources", [])),
            })

            logger.info("retrieve_node_executed")
            return {"current_phase": "extraction"}

        async def extract_node(state: AgentState) -> dict[str, Any]:
            """Extract structured facts from retrieved content."""
            await status_cb("extracting", {
                "source_count": len(state.get("retrieved_sources", [])),
            })

            # Index retrieved content into vector store for later retrieval
            retrieved = state.get("retrieved_sources", [])
            if retrieved:
                texts = [s.clean_content for s in retrieved if s.clean_content]
                metas = [
                    {
                        "source_url": s.metadata.url,
                        "source_title": s.metadata.title,
                    }
                    for s in retrieved if s.clean_content
                ]
                if texts:
                    await vector_store.add_documents(texts=texts, metadatas=metas)

            logger.info("extract_node_executed")
            return {"current_phase": "verification"}

        async def verify_node(state: AgentState) -> dict[str, Any]:
            """Cross-reference and verify extracted claims."""
            await status_cb("verifying", {
                "fact_count": len(state.get("extracted_facts", [])),
            })

            logger.info("verify_node_executed")
            return {"current_phase": "synthesis"}

        async def synthesize_node(state: AgentState) -> dict[str, Any]:
            """Organize verified claims into themes."""
            await status_cb("synthesizing", {
                "claim_count": len(state.get("verified_claims", [])),
            })

            logger.info("synthesize_node_executed")
            return {"current_phase": "reporting"}

        async def report_node(state: AgentState) -> dict[str, Any]:
            """Generate the final research report."""
            await status_cb("reporting", {
                "theme_count": len(state.get("themes", [])),
            })

            logger.info("report_node_executed")
            return {"current_phase": "complete"}

        # ── Register nodes ──────────────────────────────────────
        graph.add_node("plan", plan_node)
        graph.add_node("discover", discover_node)
        graph.add_node("rank", rank_node)
        graph.add_node("retrieve", retrieve_node)
        graph.add_node("extract", extract_node)
        graph.add_node("verify", verify_node)
        graph.add_node("synthesize", synthesize_node)
        graph.add_node("report", report_node)

        # ── Define edges ────────────────────────────────────────
        graph.set_entry_point("plan")
        graph.add_edge("plan", "discover")
        graph.add_edge("discover", "rank")
        graph.add_edge("rank", "retrieve")
        graph.add_edge("retrieve", "extract")
        graph.add_edge("extract", "verify")
        graph.add_edge("verify", "synthesize")
        graph.add_edge("synthesize", "report")
        graph.add_edge("report", END)

        logger.info("research_graph_built", nodes=8, edges=8)
        return graph

    # ── Helpers ──────────────────────────────────────────────────

    @staticmethod
    def _build_fallback_report(
        query: ResearchQuery,
        state: dict[str, Any] | None,
        elapsed: float,
    ) -> Report:
        """Construct a minimal report when the pipeline fails partially."""
        from app.models.report import ReportSection

        errors = state.get("errors", []) if state else ["Unknown error"]
        error_text = "\n".join(f"- {e}" for e in errors)

        return Report(
            title=f"Research Report: {query.question[:80]}",
            research_question=query.question,
            sections=[
                ReportSection(
                    title="Errors During Research",
                    content=(
                        "The research pipeline encountered errors and could "
                        "not produce a complete report.\n\n"
                        f"## Errors\n{error_text}"
                    ),
                    order=1,
                ),
            ],
            generation_time_seconds=elapsed,
            markdown_content=(
                f"# Research Report: {query.question[:80]}\n\n"
                f"## Errors\n{error_text}\n"
            ),
        )
