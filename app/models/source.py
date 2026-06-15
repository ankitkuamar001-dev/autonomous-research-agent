"""Source and scoring data models."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, HttpUrl


class SourceStatus(str, Enum):
    DISCOVERED = "discovered"
    RANKED = "ranked"
    RETRIEVED = "retrieved"
    FAILED = "failed"
    REJECTED = "rejected"


class ContentType(str, Enum):
    ACADEMIC_PAPER = "academic_paper"
    GOVERNMENT_REPORT = "government_report"
    INDUSTRY_REPORT = "industry_report"
    NEWS_ARTICLE = "news_article"
    BLOG_POST = "blog_post"
    DOCUMENTATION = "documentation"
    WIKI = "wiki"
    PDF = "pdf"
    UNKNOWN = "unknown"


class SourceMetadata(BaseModel):
    """Metadata discovered during web search (before content retrieval)."""

    url: str = Field(..., description="Source URL.")
    title: str = Field(default="", description="Page title.")
    snippet: str = Field(default="", description="Search result snippet.")
    author: str = Field(default="", description="Author name if available.")
    published_date: Optional[str] = Field(default=None, description="Publication date string.")
    domain: str = Field(default="", description="Domain name (e.g., 'arxiv.org').")
    content_type: ContentType = Field(default=ContentType.UNKNOWN)
    search_query: str = Field(default="", description="Query that found this source.")


class SourceScore(BaseModel):
    """Multi-dimensional quality score for a source."""

    authority: float = Field(default=0.0, ge=0.0, le=1.0, description="Domain authority score.")
    relevance: float = Field(default=0.0, ge=0.0, le=1.0, description="Relevance to research question.")
    freshness: float = Field(default=0.0, ge=0.0, le=1.0, description="Recency score.")
    domain_trust: float = Field(default=0.0, ge=0.0, le=1.0, description="Domain trustworthiness.")

    @property
    def composite(self) -> float:
        """Weighted composite score."""
        return (
            self.authority * 0.25
            + self.relevance * 0.35
            + self.freshness * 0.20
            + self.domain_trust * 0.20
        )


class Source(BaseModel):
    """Full source model with content and scoring."""

    metadata: SourceMetadata
    score: SourceScore = Field(default_factory=SourceScore)
    raw_content: str = Field(default="", description="Raw extracted text.")
    clean_content: str = Field(default="", description="Cleaned, processed text.")
    word_count: int = Field(default=0, description="Word count of clean content.")
    status: SourceStatus = Field(default=SourceStatus.DISCOVERED)
    retrieved_at: Optional[datetime] = Field(default=None)
    error: Optional[str] = Field(default=None, description="Error message if retrieval failed.")

    @property
    def is_usable(self) -> bool:
        return self.status == SourceStatus.RETRIEVED and len(self.clean_content) > 100
