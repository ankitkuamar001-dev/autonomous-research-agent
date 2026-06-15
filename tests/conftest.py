"""Shared test fixtures for the Autonomous Research Agent."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
import structlog

# Set test environment before importing app modules
os.environ["APP_ENV"] = "development"
os.environ["GEMINI_API_KEY"] = "test-key"
os.environ["GROQ_API_KEY"] = "test-key"
os.environ["TAVILY_API_KEY"] = "test-key"

# Configure structlog for tests (must happen before any app module import)
structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.format_exc_info,
        structlog.dev.ConsoleRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=False,
)

from app.models.citation import Citation, CitationStyle, Reference
from app.models.fact import Claim, Fact, FactCategory, VerifiedClaim
from app.models.report import Report, ReportConfig, ReportSection
from app.models.research import DepthLevel, ResearchPlan, ResearchQuery
from app.models.source import ContentType, Source, SourceMetadata, SourceScore, SourceStatus


@pytest.fixture
def sample_query() -> ResearchQuery:
    return ResearchQuery(
        question="Research the impact of AI agents on software engineering productivity in 2025",
        depth=DepthLevel.STANDARD,
    )


@pytest.fixture
def sample_plan() -> ResearchPlan:
    return ResearchPlan(
        objective="Investigate the impact of AI agents on software engineering productivity",
        sub_questions=[
            "What productivity metrics are affected by AI agents?",
            "Which AI tools are most commonly used by developers?",
        ],
        search_queries=[
            "AI agents software engineering productivity 2025",
            "GitHub Copilot productivity study",
            "AI coding assistant developer survey results",
        ],
        keywords=["AI agents", "productivity"],
        information_gaps=["Long-term effects"],
        expected_source_types=["academic_paper"],
    )


@pytest.fixture
def sample_source_metadata() -> SourceMetadata:
    return SourceMetadata(
        url="https://arxiv.org/abs/2301.12345",
        title="AI Agents and Developer Productivity",
        snippet="A study of 500 developers...",
        author="Smith et al.",
        published_date="2025-03-15",
        domain="arxiv.org",
        content_type=ContentType.ACADEMIC_PAPER,
    )


@pytest.fixture
def sample_source(sample_source_metadata) -> Source:
    return Source(
        metadata=sample_source_metadata,
        score=SourceScore(authority=0.95, relevance=0.85, freshness=0.9, domain_trust=0.95),
        clean_content="A study of 500 developers showed 30% productivity increase when using AI coding assistants. The randomized controlled trial measured task completion time, code quality, and developer satisfaction across multiple programming languages and project types.",
        word_count=100,
        status=SourceStatus.RETRIEVED,
    )


@pytest.fixture
def sample_fact() -> Fact:
    return Fact(
        statement="30% productivity increase with AI coding assistants",
        source_url="https://arxiv.org/abs/2301.12345",
        source_title="AI Agents Study",
        category=FactCategory.STATISTIC,
        confidence=0.85,
    )


@pytest.fixture
def sample_claim(sample_fact) -> VerifiedClaim:
    return VerifiedClaim(
        claim=Claim(
            statement=sample_fact.statement,
            supporting_sources=[sample_fact.source_url],
        ),
        confidence=0.82,
        verification_notes="Supported by independent study",
        is_contested=False,
        importance=0.9,
    )


@pytest.fixture
def mock_llm():
    mock = MagicMock()
    mock.ainvoke = AsyncMock(return_value=MagicMock(content="test response"))
    mock.with_structured_output = MagicMock(return_value=mock)
    return mock
