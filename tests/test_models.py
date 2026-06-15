"""Tests for Pydantic data models."""

from __future__ import annotations

import pytest

from app.models.citation import Citation, CitationStyle, Reference
from app.models.fact import Claim, Fact, FactCategory, VerifiedClaim
from app.models.report import Report, ReportSection
from app.models.research import DepthLevel, ResearchPlan, ResearchQuery
from app.models.source import ContentType, Source, SourceMetadata, SourceScore, SourceStatus


class TestResearchQuery:
    """Tests for ResearchQuery validation."""

    def test_valid_query(self):
        q = ResearchQuery(question="What is the impact of AI on productivity?")
        assert q.depth == DepthLevel.STANDARD
        assert q.source_restrictions == []

    def test_short_question_rejected(self):
        with pytest.raises(Exception):
            ResearchQuery(question="AI?")

    def test_depth_levels(self):
        for depth in DepthLevel:
            q = ResearchQuery(question="Test question for depth level", depth=depth)
            assert q.depth == depth

    def test_source_restrictions(self):
        q = ResearchQuery(
            question="Test question with restrictions",
            source_restrictions=["arxiv.org", ".gov"],
        )
        assert len(q.source_restrictions) == 2


class TestSourceScore:
    """Tests for source scoring."""

    def test_composite_score(self):
        score = SourceScore(
            authority=1.0,
            relevance=1.0,
            freshness=1.0,
            domain_trust=1.0,
        )
        assert score.composite == 1.0

    def test_composite_score_weighted(self):
        score = SourceScore(
            authority=0.8,
            relevance=0.9,
            freshness=0.7,
            domain_trust=0.6,
        )
        expected = 0.8 * 0.25 + 0.9 * 0.35 + 0.7 * 0.20 + 0.6 * 0.20
        assert abs(score.composite - expected) < 0.001

    def test_zero_scores(self):
        score = SourceScore()
        assert score.composite == 0.0


class TestSource:
    """Tests for Source model."""

    def test_is_usable(self, sample_source):
        assert sample_source.is_usable is True

    def test_not_usable_when_failed(self, sample_source_metadata):
        source = Source(
            metadata=sample_source_metadata,
            status=SourceStatus.FAILED,
        )
        assert source.is_usable is False

    def test_not_usable_with_short_content(self, sample_source_metadata):
        source = Source(
            metadata=sample_source_metadata,
            clean_content="Too short",
            status=SourceStatus.RETRIEVED,
        )
        assert source.is_usable is False


class TestCitation:
    """Tests for citation formatting."""

    def test_ieee_format(self):
        citation = Citation(
            index=1,
            url="https://example.com",
            title="Test Paper",
            author="John Doe",
            published_date="2025",
            style=CitationStyle.IEEE,
        )
        formatted = citation.format()
        assert "[1]" in formatted
        assert "John Doe" in formatted
        assert "Test Paper" in formatted

    def test_apa_format(self):
        citation = Citation(
            index=1,
            url="https://example.com",
            title="Test Paper",
            author="Jane Smith",
            published_date="2025",
            style=CitationStyle.APA,
        )
        formatted = citation.format()
        assert "Jane Smith" in formatted
        assert "(2025)" in formatted

    def test_all_styles_produce_output(self):
        for style in CitationStyle:
            citation = Citation(
                index=1,
                url="https://example.com",
                title="Test",
                style=style,
            )
            assert len(citation.format()) > 10

    def test_missing_fields_handled(self):
        citation = Citation(index=1, url="https://example.com")
        formatted = citation.format()
        assert "Unknown Author" in formatted


class TestFact:
    """Tests for Fact model."""

    def test_valid_fact(self, sample_fact):
        assert sample_fact.confidence == 0.85
        assert sample_fact.category == FactCategory.STATISTIC

    def test_confidence_clamping(self):
        with pytest.raises(Exception):
            Fact(
                statement="Test",
                source_url="https://example.com",
                confidence=1.5,  # Out of range
            )


class TestVerifiedClaim:
    """Tests for VerifiedClaim model."""

    def test_verified_claim(self, sample_claim):
        assert sample_claim.confidence == 0.82
        assert sample_claim.is_contested is False
        assert sample_claim.importance == 0.9


class TestResearchPlan:
    """Tests for ResearchPlan model."""

    def test_valid_plan(self, sample_plan):
        assert len(sample_plan.sub_questions) >= 2
        assert len(sample_plan.search_queries) >= 2

    def test_plan_has_required_fields(self, sample_plan):
        assert sample_plan.objective
        assert sample_plan.keywords
