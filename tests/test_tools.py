"""Tests for agent tools."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.source import ContentType


class TestSourceClassification:
    """Tests for domain classification in the discoverer."""

    def test_arxiv_classified_as_academic(self):
        from app.agents.nodes.discoverer import _classify_domain

        domain, content_type = _classify_domain("https://arxiv.org/abs/2301.12345")
        assert domain == "arxiv.org"
        assert content_type == ContentType.ACADEMIC_PAPER

    def test_gov_classified_as_government(self):
        from app.agents.nodes.discoverer import _classify_domain

        domain, content_type = _classify_domain("https://www.nih.gov/report")
        assert content_type == ContentType.GOVERNMENT_REPORT

    def test_medium_classified_as_blog(self):
        from app.agents.nodes.discoverer import _classify_domain

        domain, content_type = _classify_domain("https://medium.com/article")
        assert domain == "medium.com"
        assert content_type == ContentType.BLOG_POST

    def test_pdf_url_classified(self):
        from app.agents.nodes.discoverer import _classify_domain

        _, content_type = _classify_domain("https://example.com/report.pdf")
        assert content_type == ContentType.PDF

    def test_unknown_domain(self):
        from app.agents.nodes.discoverer import _classify_domain

        _, content_type = _classify_domain("https://randomsite.xyz/page")
        assert content_type == ContentType.UNKNOWN


class TestDeduplication:
    """Tests for source deduplication."""

    def test_duplicates_removed(self):
        from app.agents.nodes.discoverer import _deduplicate_sources
        from app.models.source import SourceMetadata

        sources = [
            SourceMetadata(url="https://example.com/page1", title="Page 1"),
            SourceMetadata(url="https://example.com/page1/", title="Page 1 Dup"),
            SourceMetadata(url="https://example.com/page2", title="Page 2"),
        ]
        result = _deduplicate_sources(sources)
        assert len(result) == 2


class TestRankerScoring:
    """Tests for source ranking logic."""

    def test_academic_scores_higher_than_blog(self):
        from app.agents.nodes.ranker import _score_source
        from app.models.source import SourceMetadata

        academic = SourceMetadata(
            url="https://arxiv.org/paper",
            domain="arxiv.org",
            content_type=ContentType.ACADEMIC_PAPER,
            snippet="AI productivity study results",
        )
        blog = SourceMetadata(
            url="https://medium.com/post",
            domain="medium.com",
            content_type=ContentType.BLOG_POST,
            snippet="AI productivity study results",
        )

        academic_score = _score_source(academic, "AI productivity study")
        blog_score = _score_source(blog, "AI productivity study")

        assert academic_score.composite > blog_score.composite

    def test_freshness_scoring(self):
        from app.agents.nodes.ranker import _score_freshness

        recent = _score_freshness("2026-06-01")
        old = _score_freshness("2020-01-01")
        unknown = _score_freshness(None)

        assert recent > old
        assert unknown == 0.3


class TestChunking:
    """Tests for text chunking in the extractor."""

    def test_short_text_single_chunk(self):
        from app.agents.nodes.extractor import _chunk_text

        chunks = _chunk_text("Short text that fits in one chunk.")
        assert len(chunks) == 1

    def test_long_text_multiple_chunks(self):
        from app.agents.nodes.extractor import _chunk_text

        long_text = "Word " * 1000  # ~5000 chars
        chunks = _chunk_text(long_text, chunk_size=500, overlap=50)
        assert len(chunks) > 1

    def test_chunks_have_overlap(self):
        from app.agents.nodes.extractor import _chunk_text

        text = "Sentence one. " * 200
        chunks = _chunk_text(text, chunk_size=200, overlap=50)
        # Verify chunks are not disjoint
        assert len(chunks) >= 2


class TestFactParsing:
    """Tests for fact extraction response parsing."""

    def test_valid_json_parsed(self):
        from app.agents.nodes.extractor import _parse_facts_response

        response = '[{"statement": "AI improves productivity by 30%", "category": "statistic", "confidence": 0.85}]'
        facts = _parse_facts_response(response, "https://example.com", "Test")
        assert len(facts) == 1
        assert facts[0].confidence == 0.85

    def test_code_block_json_parsed(self):
        from app.agents.nodes.extractor import _parse_facts_response

        response = '```json\n[{"statement": "Test fact", "category": "finding", "confidence": 0.7}]\n```'
        facts = _parse_facts_response(response, "https://example.com", "Test")
        assert len(facts) == 1

    def test_invalid_json_returns_empty(self):
        from app.agents.nodes.extractor import _parse_facts_response

        facts = _parse_facts_response("not valid json", "https://example.com", "Test")
        assert len(facts) == 0
