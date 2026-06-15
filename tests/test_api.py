"""Tests for FastAPI endpoints."""

from __future__ import annotations

import os

os.environ["APP_ENV"] = "development"
os.environ["GEMINI_API_KEY"] = "test-key"
os.environ["TAVILY_API_KEY"] = "test-key"

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


class TestHealthEndpoint:
    """Tests for the health check."""

    def test_health_check(self):
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "version" in data


class TestRootEndpoint:
    """Tests for the root endpoint."""

    def test_root(self):
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Autonomous Research Agent"


class TestResearchEndpoint:
    """Tests for the research job API."""

    def test_create_research_job(self):
        response = client.post("/api/v1/research", json={
            "question": "What is the impact of AI on software engineering?",
            "depth": "quick",
        })
        assert response.status_code == 200
        data = response.json()
        assert "job_id" in data
        assert data["status"] == "started"

    def test_create_job_short_question_rejected(self):
        response = client.post("/api/v1/research", json={
            "question": "AI?",
        })
        assert response.status_code == 422  # Validation error

    def test_get_status_unknown_job(self):
        response = client.get("/api/v1/research/nonexistent-id/status")
        assert response.status_code == 404

    def test_get_report_before_completion(self):
        # Create a job
        resp = client.post("/api/v1/research", json={
            "question": "What is the impact of AI on healthcare delivery?",
            "depth": "quick",
        })
        job_id = resp.json()["job_id"]

        # Immediately try to get report (should be 409)
        report_resp = client.get(f"/api/v1/research/{job_id}/report")
        assert report_resp.status_code == 409

    def test_get_sources_unknown_job(self):
        response = client.get("/api/v1/research/nonexistent-id/sources")
        assert response.status_code == 404

    def test_get_claims_unknown_job(self):
        response = client.get("/api/v1/research/nonexistent-id/claims")
        assert response.status_code == 404
