"""API request/response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.models.research import DepthLevel


class ResearchRequest(BaseModel):
    """API request to start a research job."""

    question: str = Field(
        ...,
        min_length=10,
        max_length=2000,
        description="The research question to investigate.",
        examples=["Research the impact of AI agents on software engineering productivity in 2025"],
    )
    depth: DepthLevel = Field(
        default=DepthLevel.STANDARD,
        description="Research depth: quick, standard, or deep.",
    )
    source_restrictions: list[str] = Field(
        default_factory=list,
        description="Optional domain restrictions.",
    )
    date_from: Optional[str] = Field(
        default=None,
        description="Only consider sources after this date (YYYY-MM-DD).",
    )
    date_to: Optional[str] = Field(
        default=None,
        description="Only consider sources before this date (YYYY-MM-DD).",
    )
    citation_style: str = Field(
        default="ieee",
        description="Citation format: ieee, apa, mla, chicago.",
    )


class ResearchJobResponse(BaseModel):
    """Response when a research job is created."""

    job_id: str
    status: str = "started"
    message: str = "Research job started successfully"


class ResearchStatusResponse(BaseModel):
    """Current status of a research job."""

    job_id: str
    status: str
    current_phase: str
    progress_percent: int = Field(ge=0, le=100)
    sources_found: int = 0
    facts_extracted: int = 0
    claims_verified: int = 0
    errors: list[str] = Field(default_factory=list)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class ReportResponse(BaseModel):
    """Response with the completed research report."""

    job_id: str
    title: str
    research_question: str
    markdown_content: str
    total_sources: int
    total_claims: int
    generation_time_seconds: float
    generated_at: datetime
    references: list[dict]


class SourceResponse(BaseModel):
    """Summary of a discovered source."""

    url: str
    title: str
    domain: str
    content_type: str
    score: float
    status: str


class ClaimResponse(BaseModel):
    """Summary of a verified claim."""

    statement: str
    confidence: float
    supporting_sources: list[str]
    is_contested: bool
    verification_notes: str


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = "healthy"
    version: str = "1.0.0"
    timestamp: datetime = Field(default_factory=datetime.utcnow)
