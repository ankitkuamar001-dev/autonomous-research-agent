"""Report data models."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.models.citation import CitationStyle, Reference


class ReportSection(BaseModel):
    """A single section of the research report."""

    title: str = Field(..., description="Section heading.")
    content: str = Field(..., description="Section body (Markdown).")
    citation_indices: list[int] = Field(
        default_factory=list,
        description="Indices of citations used in this section.",
    )
    order: int = Field(default=0, description="Section ordering.")


class ReportConfig(BaseModel):
    """Configuration for report generation."""

    citation_style: CitationStyle = Field(default=CitationStyle.IEEE)
    include_executive_summary: bool = True
    include_methodology: bool = True
    include_risks: bool = True
    include_table_of_contents: bool = True
    max_report_words: int = Field(default=5000, description="Target max word count.")


class Report(BaseModel):
    """The final research report."""

    title: str = Field(..., description="Report title.")
    research_question: str = Field(..., description="Original research question.")
    sections: list[ReportSection] = Field(default_factory=list)
    references: list[Reference] = Field(default_factory=list)
    config: ReportConfig = Field(default_factory=ReportConfig)
    total_sources_found: int = Field(default=0)
    total_sources_used: int = Field(default=0)
    total_claims_verified: int = Field(default=0)
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    generation_time_seconds: float = Field(default=0.0)
    markdown_content: str = Field(default="", description="Full Markdown report.")
    pdf_path: Optional[str] = Field(default=None, description="Path to generated PDF.")
