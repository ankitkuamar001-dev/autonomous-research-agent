"""Prompt template for the final report writing phase.

Generates a well-structured Markdown research report from synthesized
themes, including an executive summary, methodology section, thematic
analysis, and conclusions.
"""

from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate

REPORTER_PROMPT: ChatPromptTemplate = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            (
                "You are an expert research report writer. Your task is to produce a "
                "publication-quality research report in Markdown format from the "
                "synthesized research findings.\n\n"
                "## Report Structure\n"
                "Generate the following sections IN ORDER:\n\n"
                "### 1. Title\n"
                "A clear, informative title for the report.\n\n"
                "### 2. Executive Summary\n"
                "A 150-250 word overview covering: the research question, key "
                "findings, and primary conclusions. This should stand alone — a "
                "reader should understand the core results from this section only.\n\n"
                "### 3. Methodology\n"
                "Describe the research process:\n"
                "- How many sources were searched and analyzed\n"
                "- What types of sources were used\n"
                "- How claims were verified (cross-source validation)\n"
                "- Any limitations of the research process\n"
                "Use the methodology details provided below.\n\n"
                "### 4. Findings\n"
                "For each theme, write a subsection with:\n"
                "- A descriptive heading\n"
                "- 2-4 paragraphs analyzing the theme's findings\n"
                "- Inline citations using [n] notation referencing source indices\n"
                "- Discussion of confidence levels where relevant\n"
                "- Highlight any contested findings with balanced treatment\n\n"
                "### 5. Analysis & Discussion\n"
                "- Cross-theme connections and patterns\n"
                "- Areas of strong consensus vs. active debate\n"
                "- Implications of the findings\n\n"
                "### 6. Conclusions\n"
                "- Direct answer to the research question\n"
                "- Key takeaways (3-5 bullet points)\n"
                "- Limitations and caveats\n\n"
                "### 7. Knowledge Gaps & Future Research\n"
                "- What remains unknown\n"
                "- Suggested areas for further investigation\n\n"
                "## Writing Guidelines\n"
                "- Write in a professional, objective, analytical tone.\n"
                "- Use clear topic sentences for each paragraph.\n"
                "- Support every claim with inline citations [n].\n"
                "- Do NOT fabricate information — use only what is provided.\n"
                "- Use Markdown formatting: headers (##), bold, bullet lists, "
                "  and blockquotes where appropriate.\n"
                "- Aim for {max_words} words total.\n\n"
                "## Output Format\n"
                "Return a JSON object with these keys:\n"
                "- `title` (string): Report title.\n"
                "- `sections` (list of objects): Each has `title` (string), "
                "  `content` (string in Markdown), and `order` (int starting at 1).\n"
                "- `markdown_content` (string): The complete report as a single "
                "  Markdown document with all sections assembled.\n\n"
                "Return ONLY the JSON object. No markdown fences around the JSON."
            ),
        ),
        (
            "human",
            (
                "Research Question:\n{research_question}\n\n"
                "## Synthesized Themes\n{themes}\n\n"
                "## Methodology Details\n{methodology}\n\n"
                "## Source References (for citation)\n{references}"
            ),
        ),
    ]
)
