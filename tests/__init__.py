"""Shared test fixtures for the Autonomous Research Agent."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Set test environment before importing app modules
os.environ["APP_ENV"] = "development"
os.environ["GEMINI_API_KEY"] = "test-key"
os.environ["GROQ_API_KEY"] = "test-key"
os.environ["TAVILY_API_KEY"] = "test-key"

from app.models.citation import Citation, CitationStyle, Reference
from app.models.fact import Claim, Fact, FactCategory, VerifiedClaim
from app.models.report import Report, ReportConfig, ReportSection
from app.models.research import DepthLevel, ResearchPlan, ResearchQuery
from app.models.source import ContentType, Source, SourceMetadata, SourceScore, SourceStatus


# ── Research Query Fixtures ──────────────────────────────────────

@pytest.fixture
def sample_query() -> ResearchQuery:
    return ResearchQuery(
        question="Research the impact of AI agents on software engineering productivity in 2025",
        depth=DepthLevel.STANDARD,
    )


@pytest.fixture
def quick_query() -> ResearchQuery:
    return ResearchQuery(
        question="What is the current state of quantum computing?",
        depth=DepthLevel.QUICK,
    )


# ── Research Plan Fixtures ───────────────────────────────────────

@pytest.fixture
def sample_plan() -> ResearchPlan:
    return ResearchPlan(
        objective="Investigate the impact of AI agents on software engineering productivity",
        sub_questions=[
            "What productivity metrics are affected by AI agents?",
            "Which AI tools are most commonly used by developers?",
            "What do empirical studies show about productivity gains?",
        ],
        search_queries=[
            "AI agents software engineering productivity 2025",
            "GitHub Copilot productivity study",
            "AI coding assistant developer survey results",
            "LLM impact software development metrics",
        ],
        keywords=["AI agents", "productivity", "software engineering", "coding assistants"],
        information_gaps=["Long-term productivity effects", "Quality vs speed tradeoffs"],
        expected_source_types=["academic_paper", "industry_report"],
    )


# ── Source Fixtures ──────────────────────────────────────────────

@pytest.fixture
def sample_source_metadata() -> SourceMetadata:
    return SourceMetadata(
        url="https://arxiv.org/abs/2301.12345",
        title="AI Agents and Developer Productivity: A Large-Scale Study",
        snippet="We conducted a randomized controlled trial with 500 developers...",
        author="Smith et al.",
        published_date="2025-03-15",
        domain="arxiv.org",
        content_type=ContentType.ACADEMIC_PAPER,
        search_query="AI agents software engineering productivity",
    )


@pytest.fixture
def sample_source(sample_source_metadata: SourceMetadata) -> Source:
    return Source(
        metadata=sample_source_metadata,
        score=SourceScore(
            authority=0.95,
            relevance=0.85,
            freshness=0.90,
            domain_trust=0.95,
        ),
        clean_content="We conducted a randomized controlled trial with 500 developers "
                      "using AI coding assistants. Results show a 30% productivity increase "
                      "in code completion tasks, with statistical significance (p<0.01).",
        word_count=30,
        status=SourceStatus.RETRIEVED,
        retrieved_at=datetime.now(timezone.utc),
    )


# ── Fact Fixtures ────────────────────────────────────────────────

@pytest.fixture
def sample_fact() -> Fact:
    return Fact(
        statement="Developers using AI coding assistants showed a 30% productivity increase",
        source_url="https://arxiv.org/abs/2301.12345",
        source_title="AI Agents and Developer Productivity",
        category=FactCategory.STATISTIC,
        confidence=0.85,
        entities=["AI coding assistants"],
        dates=["2025"],
    )


@pytest.fixture
def sample_verified_claim(sample_fact: Fact) -> VerifiedClaim:
    return VerifiedClaim(
        claim=Claim(
            statement=sample_fact.statement,
            supporting_sources=[sample_fact.source_url, "https://example.com/study2"],
            contradicting_sources=[],
            related_facts=["Similar study found 25% improvement"],
        ),
        confidence=0.82,
        verification_notes="Supported by two independent studies",
        is_contested=False,
        importance=0.9,
    )


# ── Mock LLM Fixture ────────────────────────────────────────────

@pytest.fixture
def mock_llm():
    """Create a mock LLM that returns predictable responses."""
    mock = MagicMock()
    mock.ainvoke = AsyncMock(return_value=MagicMock(
        content='[{"statement": "Test fact", "category": "finding", "confidence": 0.8}]'
    ))
    mock.with_structured_output = MagicMock(return_value=mock)
    return mock
