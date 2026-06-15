"""Research planning data models."""

from __future__ import annotations

from enum import Enum
from datetime import date
from typing import Optional

from pydantic import BaseModel, Field


class DepthLevel(str, Enum):
    """Research depth controls source count, query count, and analysis thoroughness."""

    QUICK = "quick"
    STANDARD = "standard"
    DEEP = "deep"


class ResearchQuery(BaseModel):
    """User-submitted research request."""

    question: str = Field(
        ...,
        min_length=10,
        max_length=2000,
        description="The research question to investigate.",
    )
    depth: DepthLevel = Field(
        default=DepthLevel.STANDARD,
        description="How deeply to research the topic.",
    )
    source_restrictions: list[str] = Field(
        default_factory=list,
        description="Optional domain restrictions (e.g., ['arxiv.org', '.gov']).",
    )
    date_from: Optional[date] = Field(
        default=None,
        description="Only consider sources published after this date.",
    )
    date_to: Optional[date] = Field(
        default=None,
        description="Only consider sources published before this date.",
    )


class ResearchPlan(BaseModel):
    """AI-generated research strategy."""

    objective: str = Field(
        ...,
        description="Clear statement of the research objective.",
    )
    sub_questions: list[str] = Field(
        default_factory=list,
        min_length=2,
        description="Decomposed sub-questions to investigate.",
    )
    search_queries: list[str] = Field(
        default_factory=list,
        min_length=3,
        description="Optimized search queries to execute.",
    )
    keywords: list[str] = Field(
        default_factory=list,
        description="Key terms and phrases for this research topic.",
    )
    information_gaps: list[str] = Field(
        default_factory=list,
        description="Known gaps the research should try to fill.",
    )
    expected_source_types: list[str] = Field(
        default_factory=list,
        description="Types of sources to prioritize (e.g., 'academic paper', 'industry report').",
    )
