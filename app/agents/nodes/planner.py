"""Phase 1: Research Planning Node.

Takes the user's research question and generates a structured research plan
including sub-questions, search queries, keywords, and information gaps.
"""

from __future__ import annotations

import structlog
from langchain_core.prompts import ChatPromptTemplate

from app.agents.state import AgentState
from app.config import get_settings
from app.models.research import ResearchPlan

logger = structlog.get_logger(__name__)

PLANNER_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        "You are an expert research strategist. Given a research question, "
        "you create comprehensive research plans that maximize the chance of "
        "finding accurate, high-quality information.\n\n"
        "Your plan must include:\n"
        "1. A clear research objective\n"
        "2. Sub-questions that decompose the main question\n"
        "3. Optimized search queries (diverse phrasing for better coverage)\n"
        "4. Key terms and phrases\n"
        "5. Information gaps to watch for\n"
        "6. Expected source types to prioritize\n\n"
        "Depth level '{depth}' means:\n"
        "- quick: 3-5 search queries, focus on top results\n"
        "- standard: 8-12 search queries, balanced coverage\n"
        "- deep: 15-20 search queries, exhaustive coverage\n\n"
        "Generate diverse search queries that cover different angles, "
        "synonyms, and related concepts. Include both broad and specific queries.",
    ),
    (
        "human",
        "Research Question: {question}\n"
        "Depth Level: {depth}\n\n"
        "Generate a comprehensive research plan.",
    ),
])


async def plan_research(state: AgentState) -> dict:
    """Generate a research plan from the user's question.

    Args:
        state: Current agent state with ``research_query`` populated.

    Returns:
        Partial state update with ``research_plan`` and ``current_phase``.
    """
    query = state["research_query"]
    settings = get_settings()

    logger.info(
        "planning_research",
        question=query.question,
        depth=query.depth.value,
    )

    # Import here to avoid circular dependency at module load time
    from app.services.llm_service import get_llm

    llm = get_llm()
    structured_llm = llm.with_structured_output(ResearchPlan)
    chain = PLANNER_PROMPT | structured_llm

    try:
        plan: ResearchPlan = await chain.ainvoke({
            "question": query.question,
            "depth": query.depth.value,
        })

        # Enforce query limits based on depth
        max_queries = settings.get_max_queries(query.depth.value)
        plan.search_queries = plan.search_queries[:max_queries]

        logger.info(
            "research_plan_created",
            sub_questions=len(plan.sub_questions),
            search_queries=len(plan.search_queries),
            keywords=len(plan.keywords),
        )

        return {
            "research_plan": plan,
            "current_phase": "planning_complete",
        }

    except Exception as e:
        logger.error("planning_failed", error=str(e))
        # Create a minimal fallback plan
        fallback_plan = ResearchPlan(
            objective=f"Research: {query.question}",
            sub_questions=[
                query.question,
                f"What are the key concepts of {query.question}?",
            ],
            search_queries=[
                query.question,
                f"{query.question} research 2025",
                f"{query.question} latest findings",
            ],
            keywords=query.question.split(),
            information_gaps=["Unable to generate detailed plan"],
            expected_source_types=["academic_paper", "news_article"],
        )
        return {
            "research_plan": fallback_plan,
            "current_phase": "planning_complete",
            "errors": [f"Planning degraded: {e}"],
        }
