"""FastAPI routes for the research agent API — Enhanced.

New in v2:
- GET /research/{id}/stream  — Server-Sent Events for live progress
- GET /history               — list all research jobs (most recent first)
- Job dict updated in real-time as research phases progress
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Any

import structlog
from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse, StreamingResponse

from app.agents.graph import run_research
from app.api.schemas import (
    ClaimResponse,
    HealthResponse,
    ReportResponse,
    ResearchJobResponse,
    ResearchRequest,
    ResearchStatusResponse,
    SourceResponse,
)
from app.models.research import ResearchQuery

logger = structlog.get_logger(__name__)
router = APIRouter()

# In-memory job store (production: use Redis or a database)
_jobs: dict[str, dict[str, Any]] = {}


def _get_progress(phase: str) -> int:
    """Map phase name to progress percentage."""
    phase_progress = {
        "starting": 2,
        "planning_complete": 10,
        "discovery_complete": 25,
        "ranking_complete": 35,
        "retrieval_complete": 50,
        "extraction_complete": 65,
        "verification_complete": 80,
        "synthesis_complete": 90,
        "report_complete": 100,
    }
    return phase_progress.get(phase, 0)


async def _run_research_job(job_id: str, query: ResearchQuery) -> None:
    """Background task that runs the full research pipeline."""
    try:
        _jobs[job_id]["status"] = "running"
        _jobs[job_id]["started_at"] = datetime.now(timezone.utc)

        final_state = await run_research(query, session_id=job_id)

        phase = final_state.get("current_phase", "unknown")
        _jobs[job_id]["state"] = final_state
        _jobs[job_id]["status"] = "completed"
        _jobs[job_id]["current_phase"] = phase
        _jobs[job_id]["completed_at"] = datetime.now(timezone.utc)

        logger.info("job_completed", job_id=job_id, phase=phase)

    except Exception as e:
        logger.error("job_failed", job_id=job_id, error=str(e))
        _jobs[job_id]["status"] = "failed"
        _jobs[job_id]["error"] = str(e)
        _jobs[job_id]["completed_at"] = datetime.now(timezone.utc)


# ── Health ────────────────────────────────────────────────────────────────────

@router.get("/health", response_model=HealthResponse, tags=["System"])
async def health_check():
    """Health check endpoint."""
    return HealthResponse()


# ── Research lifecycle ────────────────────────────────────────────────────────

@router.post("/research", response_model=ResearchJobResponse, tags=["Research"])
async def start_research(
    request: ResearchRequest,
    background_tasks: BackgroundTasks,
):
    """Start a new research job.

    The research runs asynchronously in the background. Use the returned
    job_id to poll status or subscribe to SSE stream.
    """
    job_id = str(uuid.uuid4())

    query = ResearchQuery(
        question=request.question,
        depth=request.depth,
        source_restrictions=request.source_restrictions,
    )

    _jobs[job_id] = {
        "query": query,
        "status": "queued",
        "current_phase": "starting",
        "state": None,
        "started_at": None,
        "completed_at": None,
        "error": None,
    }

    background_tasks.add_task(_run_research_job, job_id, query)

    logger.info(
        "research_job_created",
        job_id=job_id,
        question=request.question,
        depth=request.depth.value,
    )

    return ResearchJobResponse(job_id=job_id)


@router.get(
    "/research/{job_id}/status",
    response_model=ResearchStatusResponse,
    tags=["Research"],
)
async def get_research_status(job_id: str):
    """Get the current status of a research job."""
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    job = _jobs[job_id]
    state = job.get("state") or {}
    phase = state.get("current_phase", job.get("current_phase", "starting"))

    return ResearchStatusResponse(
        job_id=job_id,
        status=job["status"],
        current_phase=phase,
        progress_percent=_get_progress(phase),
        sources_found=len(state.get("discovered_sources", [])),
        facts_extracted=len(state.get("extracted_facts", [])),
        claims_verified=len(state.get("verified_claims", [])),
        errors=state.get("errors", [])[:5],
        started_at=job.get("started_at"),
        completed_at=job.get("completed_at"),
    )


@router.get("/research/{job_id}/stream", tags=["Research"])
async def stream_research_status(job_id: str):
    """Stream research progress as Server-Sent Events (SSE).

    Connect to this endpoint from the frontend to receive live phase updates.
    The stream closes automatically when the job completes or fails.

    Event format: ``data: <json>\\n\\n``
    """

    async def event_generator():
        if job_id not in _jobs:
            yield f"data: {json.dumps({'error': 'Job not found'})}\n\n"
            return

        last_phase: str | None = None

        while True:
            job = _jobs.get(job_id, {})
            state = job.get("state") or {}
            phase = state.get("current_phase", job.get("current_phase", "starting"))
            status = job.get("status", "queued")

            event_data = {
                "job_id": job_id,
                "status": status,
                "phase": phase,
                "progress": _get_progress(phase),
                "sources_found": len(state.get("discovered_sources", [])),
                "facts_extracted": len(state.get("extracted_facts", [])),
                "claims_verified": len(state.get("verified_claims", [])),
            }

            # Only emit when phase changes (reduces noise)
            if phase != last_phase:
                yield f"data: {json.dumps(event_data)}\n\n"
                last_phase = phase

            if status in ("completed", "failed"):
                # Always emit a terminal event
                yield f"data: {json.dumps({**event_data, 'final': True})}\n\n"
                break

            await asyncio.sleep(1.5)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


# ── Report retrieval ──────────────────────────────────────────────────────────

@router.get("/research/{job_id}/report", response_model=ReportResponse, tags=["Research"])
async def get_report(job_id: str):
    """Get the completed research report."""
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    job = _jobs[job_id]
    if job["status"] != "completed":
        raise HTTPException(
            status_code=409,
            detail=f"Job is {job['status']}, not completed yet.",
        )

    state = job["state"]
    report = state.get("report")
    if not report:
        raise HTTPException(status_code=500, detail="Report not generated")

    return ReportResponse(
        job_id=job_id,
        title=report.title,
        research_question=report.research_question,
        markdown_content=report.markdown_content,
        total_sources=report.total_sources_used,
        total_claims=report.total_claims_verified,
        generation_time_seconds=report.generation_time_seconds,
        generated_at=report.generated_at,
        references=[
            {"index": r.index, "formatted": r.formatted, "url": r.citation.url}
            for r in report.references
        ],
    )


@router.get("/research/{job_id}/report/download", tags=["Research"])
async def download_report(job_id: str, format: str = "md"):
    """Download the report as Markdown.

    Query Parameters:
        format: 'md' (default) or 'pdf'
    """
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    job = _jobs[job_id]
    if job["status"] != "completed":
        raise HTTPException(status_code=409, detail="Job not completed")

    report = job["state"].get("report")
    if not report:
        raise HTTPException(status_code=500, detail="No report available")

    if format == "pdf" and getattr(report, "pdf_path", None):
        return FileResponse(
            report.pdf_path,
            media_type="application/pdf",
            filename=f"research_report_{job_id[:8]}.pdf",
        )

    from fastapi.responses import Response

    return Response(
        content=report.markdown_content,
        media_type="text/markdown",
        headers={
            "Content-Disposition": f"attachment; filename=research_report_{job_id[:8]}.md"
        },
    )


# ── Sources & Claims ──────────────────────────────────────────────────────────

@router.get(
    "/research/{job_id}/sources",
    response_model=list[SourceResponse],
    tags=["Research"],
)
async def get_sources(job_id: str):
    """List all discovered and ranked sources for a job."""
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    state = _jobs[job_id].get("state", {}) or {}
    sources = state.get("retrieved_sources", []) or state.get("ranked_sources", [])

    return [
        SourceResponse(
            url=s.metadata.url,
            title=s.metadata.title,
            domain=s.metadata.domain,
            content_type=s.metadata.content_type.value,
            score=s.score.composite,
            status=s.status.value,
        )
        for s in sources
    ]


@router.get(
    "/research/{job_id}/claims",
    response_model=list[ClaimResponse],
    tags=["Research"],
)
async def get_claims(job_id: str):
    """List all verified claims for a job."""
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    state = _jobs[job_id].get("state", {}) or {}
    claims = state.get("verified_claims", [])

    return [
        ClaimResponse(
            statement=vc.claim.statement,
            confidence=vc.confidence,
            supporting_sources=vc.claim.supporting_sources,
            is_contested=vc.is_contested,
            verification_notes=vc.verification_notes,
        )
        for vc in claims
    ]


# ── History ───────────────────────────────────────────────────────────────────

@router.get("/history", tags=["Research"])
async def get_history():
    """Return list of all research jobs (most recent first)."""
    jobs_list = []
    for job_id, job in reversed(list(_jobs.items())):
        query = job.get("query")
        started = job.get("started_at")
        completed = job.get("completed_at")
        jobs_list.append({
            "job_id": job_id,
            "question": query.question if query else "",
            "status": job.get("status", "unknown"),
            "depth": query.depth.value if query else "",
            "started_at": started.isoformat() if started else None,
            "completed_at": completed.isoformat() if completed else None,
        })
    return jobs_list
