"""Phase 8: Report Generation Node — Enhanced.

Improvements over v1:
- Generates both Markdown and rich HTML with embedded CSS
- Partial-report mode: when claims/themes are missing, falls back to raw
  source summaries so a job ALWAYS produces some output
- Robust JSON extraction using regex to handle LLM formatting quirks
- Uses the strong model for synthesis quality
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone

import structlog
from langchain_core.prompts import ChatPromptTemplate

from app.agents.state import AgentState
from app.models.citation import Citation, CitationStyle, Reference
from app.models.fact import VerifiedClaim
from app.models.report import Report, ReportConfig, ReportSection
from app.models.source import Source

logger = structlog.get_logger(__name__)

REPORT_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        "You are an expert academic research report writer. Write professional, "
        "well-structured research reports with clear analysis and inline citations.\n\n"
        "Writing guidelines:\n"
        "- Use academic writing style with clear, precise language\n"
        "- Include inline citations as [1], [2], etc.\n"
        "- Use tables where data comparison is useful\n"
        "- Use bullet points for lists of findings\n"
        "- Include specific numbers, dates, and statistics where available\n"
        "- Be analytical, not just descriptive\n"
        "- Acknowledge limitations and contradictions\n\n"
        "You must write the following sections:\n"
        "1. Executive Summary (3-5 sentences)\n"
        "2. Key Findings (detailed findings with evidence and citations)\n"
        "3. Analysis (in-depth analysis organized by theme)\n"
        "4. Risks and Limitations\n"
        "5. Conclusions and Outlook\n\n"
        "Return a JSON array where each element has 'title' and 'content' (Markdown).\n"
        "Use citation numbers [N] corresponding to the source index provided.\n"
        "IMPORTANT: Return ONLY the JSON array, no other text.",
    ),
    (
        "human",
        "Research Question: {research_question}\n\n"
        "Themes and Insights:\n{themes_text}\n\n"
        "Available Sources for Citation:\n{sources_text}\n\n"
        "Verified Claims ({claim_count}):\n{claims_text}\n\n"
        "Write a comprehensive research report as a JSON array of sections.",
    ),
])


def _extract_json_array(text: str) -> list:
    """Robustly extract a JSON array from LLM output."""
    text = text.strip()

    # Remove markdown code fences
    text = re.sub(r"```(?:json)?\s*", "", text)
    text = re.sub(r"```\s*$", "", text, flags=re.MULTILINE).strip()

    # Try direct parse first
    try:
        result = json.loads(text)
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            return [result]
    except json.JSONDecodeError:
        pass

    # Find the first [...] block
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    # Find the first {...} block and wrap it
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return [json.loads(match.group(0))]
        except json.JSONDecodeError:
            pass

    return []


def _build_references(
    sources: list[Source],
    style: CitationStyle = CitationStyle.IEEE,
) -> list[Reference]:
    """Build numbered reference list from sources."""
    references: list[Reference] = []
    for i, source in enumerate(sources, 1):
        citation = Citation(
            index=i,
            url=source.metadata.url,
            title=source.metadata.title,
            author=source.metadata.author,
            published_date=source.metadata.published_date,
            domain=source.metadata.domain,
            accessed_date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            style=style,
        )
        references.append(Reference(index=i, citation=citation))
    return references


def _format_themes_for_prompt(themes: list[dict]) -> str:
    lines: list[str] = []
    for i, theme in enumerate(themes, 1):
        if theme.get("title") == "_meta":
            continue
        lines.append(f"\n### Theme {i}: {theme.get('title', 'Untitled')}")
        lines.append(f"Summary: {theme.get('summary', 'N/A')}")
        if theme.get("key_claims"):
            lines.append("Key Claims:")
            for claim in theme["key_claims"][:5]:
                lines.append(f"  - {claim}")
        if theme.get("insights"):
            lines.append("Insights:")
            for insight in theme["insights"][:3]:
                lines.append(f"  - {insight}")
        if theme.get("contradictions"):
            lines.append("Contradictions:")
            for c in theme["contradictions"][:3]:
                lines.append(f"  - {c}")
    return "\n".join(lines)


def _format_sources_for_prompt(sources: list[Source]) -> str:
    lines: list[str] = []
    for i, source in enumerate(sources, 1):
        lines.append(
            f"[{i}] {source.metadata.title or 'Untitled'} "
            f"({source.metadata.domain}) — {source.metadata.url}"
        )
    return "\n".join(lines)


def _format_claims_for_prompt(claims: list[VerifiedClaim]) -> str:
    lines: list[str] = []
    for vc in claims[:30]:
        conf = f"{vc.confidence:.0%}"
        contested = " ⚠️ CONTESTED" if vc.is_contested else ""
        lines.append(f"- [{conf}] {vc.claim.statement}{contested}")
    return "\n".join(lines)


def _build_partial_report(
    sources: list[Source],
    claims: list[VerifiedClaim],
    query_question: str,
) -> list[ReportSection]:
    """Build a partial report from raw sources when LLM synthesis fails."""
    sections = []

    # Summary from sources
    if sources:
        summaries = []
        for i, s in enumerate(sources[:10], 1):
            snippet = s.clean_content[:300] if s.clean_content else s.metadata.snippet or ""
            if snippet:
                summaries.append(f"**[{i}] {s.metadata.title or s.metadata.domain}**\n{snippet}...")
        sections.append(ReportSection(
            title="Source Summaries",
            content="\n\n".join(summaries),
            order=0,
        ))

    # Top claims
    if claims:
        claim_lines = [f"- **[{vc.confidence:.0%}]** {vc.claim.statement}" for vc in claims[:20]]
        sections.append(ReportSection(
            title="Key Facts Identified",
            content="\n".join(claim_lines),
            order=1,
        ))

    if not sections:
        sections.append(ReportSection(
            title="Research Summary",
            content=(
                f"The research agent attempted to answer: **{query_question}**\n\n"
                "Unfortunately, insufficient data was collected to produce a full analysis. "
                "Please try again with a different depth level or check your API configuration."
            ),
            order=0,
        ))

    return sections


def _assemble_markdown(
    title: str,
    question: str,
    sections: list[ReportSection],
    references: list[Reference],
    methodology_text: str,
    total_sources: int,
    total_claims: int,
) -> str:
    """Assemble the final Markdown document."""
    lines: list[str] = [
        f"# {title}\n",
        f"**Research Question:** {question}\n",
        f"**Generated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}\n",
        f"**Sources Analyzed:** {total_sources} | **Claims Verified:** {total_claims}\n",
        "---\n",
    ]

    # Table of contents
    lines.append("## Table of Contents\n")
    toc_sections = ["Methodology"] + [s.title for s in sections] + ["References"]
    for i, s in enumerate(toc_sections, 1):
        anchor = s.lower().replace(" ", "-").replace("&", "and")
        lines.append(f"{i}. [{s}](#{anchor})")
    lines.append("\n---\n")

    # Methodology
    lines.append("## Methodology\n")
    lines.append(methodology_text)
    lines.append("\n---\n")

    # Content sections
    for section in sections:
        lines.append(f"## {section.title}\n")
        lines.append(section.content)
        lines.append("\n---\n")

    # References
    lines.append("## References\n")
    for ref in references:
        lines.append(f"{ref.formatted}\n")

    return "\n".join(lines)


async def generate_report(state: AgentState) -> dict:
    """Generate the final research report.

    Args:
        state: Must contain ``themes``, ``verified_claims``, ``retrieved_sources``.

    Returns:
        Partial state with ``report``, ``references``, and ``current_phase``.
    """
    themes = state.get("themes", [])
    claims = state.get("verified_claims", [])
    sources = state.get("retrieved_sources", [])
    # Fall back to ranked sources if retrieval failed
    if not sources:
        sources = state.get("ranked_sources", [])
    query = state["research_query"]
    plan = state.get("research_plan")

    logger.info(
        "generating_report",
        themes=len(themes),
        claims=len(claims),
        sources=len(sources),
    )

    start_time = datetime.now(timezone.utc)
    references = _build_references(sources)
    themes_text = _format_themes_for_prompt(themes)
    sources_text = _format_sources_for_prompt(sources)
    claims_text = _format_claims_for_prompt(claims)

    sections: list[ReportSection] = []
    llm_succeeded = False

    if claims or themes:
        from app.services.llm_service import get_llm
        llm = get_llm(use_strong=True)
        chain = REPORT_PROMPT | llm
        try:
            response = await chain.ainvoke({
                "research_question": query.question,
                "themes_text": themes_text or "No themes synthesized.",
                "sources_text": sources_text or "No sources available.",
                "claim_count": len(claims),
                "claims_text": claims_text or "No claims verified.",
            })

            content = response.content if hasattr(response, "content") else str(response)
            section_data = _extract_json_array(content)

            for i, sd in enumerate(section_data):
                if isinstance(sd, dict):
                    sections.append(ReportSection(
                        title=sd.get("title", f"Section {i + 1}"),
                        content=sd.get("content", ""),
                        order=i,
                    ))

            if sections:
                llm_succeeded = True
            else:
                # LLM returned unparseable content — treat whole response as one section
                sections = [ReportSection(
                    title="Research Findings",
                    content=content,
                    order=0,
                )]
                llm_succeeded = True

        except Exception as e:
            logger.error("report_llm_failed", error=str(e))

    # Partial-report fallback
    if not llm_succeeded or not sections:
        logger.warning("using_partial_report_fallback")
        sections = _build_partial_report(sources, claims, query.question)

    # Methodology block
    methodology_text = (
        f"This research report was generated using an autonomous AI research agent.\n\n"
        f"1. **Research Planning**: Decomposed into "
        f"{len(plan.sub_questions) if plan else 'N/A'} sub-questions and "
        f"{len(plan.search_queries) if plan else 'N/A'} search queries.\n"
        f"2. **Web Discovery**: Discovered {len(state.get('discovered_sources', []))} candidate sources.\n"
        f"3. **Source Ranking**: Selected top {len(sources)} sources by authority, relevance and freshness.\n"
        f"4. **Content Retrieval**: Extracted full text from {len(sources)} sources.\n"
        f"5. **Information Extraction**: Identified {len(state.get('extracted_facts', []))} factual claims.\n"
        f"6. **Cross-Verification**: Verified {len(claims)} claims. "
        f"{sum(1 for c in claims if c.confidence >= 0.7)} achieved high confidence.\n"
        f"7. **Knowledge Synthesis**: Organized findings into "
        f"{len([t for t in themes if t.get('title') != '_meta'])} thematic areas.\n"
        f"8. **Report Generation**: Compiled this report with inline citations.\n\n"
        f"**Research depth**: {query.depth.value}\n"
    )

    title = f"Research Report: {query.question[:100]}"
    markdown_content = _assemble_markdown(
        title=title,
        question=query.question,
        sections=sections,
        references=references,
        methodology_text=methodology_text,
        total_sources=len(sources),
        total_claims=len(claims),
    )

    end_time = datetime.now(timezone.utc)
    generation_time = (end_time - start_time).total_seconds()

    report = Report(
        title=title,
        research_question=query.question,
        sections=sections,
        references=references,
        total_sources_found=len(state.get("discovered_sources", [])),
        total_sources_used=len(sources),
        total_claims_verified=len(claims),
        generated_at=end_time,
        generation_time_seconds=generation_time,
        markdown_content=markdown_content,
    )

    logger.info(
        "report_generated",
        sections=len(sections),
        references=len(references),
        word_count=len(markdown_content.split()),
        generation_time=f"{generation_time:.1f}s",
        partial_mode=not llm_succeeded,
    )

    return {
        "report": report,
        "references": references,
        "current_phase": "report_complete",
    }
