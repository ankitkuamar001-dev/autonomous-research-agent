"""Fact extraction and verification data models."""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class FactCategory(str, Enum):
    STATISTIC = "statistic"
    FINDING = "finding"
    CLAIM = "claim"
    QUOTE = "quote"
    DATE_EVENT = "date_event"
    DEFINITION = "definition"
    METHODOLOGY = "methodology"


class Fact(BaseModel):
    """A single extracted piece of information from a source."""

    statement: str = Field(..., description="The factual statement.")
    source_url: str = Field(..., description="URL of the source.")
    source_title: str = Field(default="", description="Title of the source.")
    category: FactCategory = Field(default=FactCategory.CLAIM)
    confidence: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Initial extraction confidence.",
    )
    entities: list[str] = Field(default_factory=list, description="Named entities mentioned.")
    dates: list[str] = Field(default_factory=list, description="Dates mentioned.")
    context: str = Field(default="", description="Surrounding context for the fact.")


class Claim(BaseModel):
    """A fact elevated to a claim with cross-source evidence."""

    statement: str = Field(..., description="The claim text.")
    supporting_sources: list[str] = Field(
        default_factory=list,
        description="URLs of sources that support this claim.",
    )
    contradicting_sources: list[str] = Field(
        default_factory=list,
        description="URLs of sources that contradict this claim.",
    )
    related_facts: list[str] = Field(
        default_factory=list,
        description="Related fact statements from other sources.",
    )


class VerifiedClaim(BaseModel):
    """A claim with a final verification score and assessment."""

    claim: Claim
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Final confidence score after verification.",
    )
    verification_notes: str = Field(
        default="",
        description="Explanation of the confidence assessment.",
    )
    is_contested: bool = Field(
        default=False,
        description="True if contradicting sources exist.",
    )
    importance: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="How important this claim is to the research question.",
    )
