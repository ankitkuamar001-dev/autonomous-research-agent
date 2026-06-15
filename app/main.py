"""FastAPI application entry point.

Run with:
    uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings

# Configure structlog
structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.dev.ConsoleRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown."""
    settings = get_settings()

    # Create required directories
    Path(settings.reports_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.chroma_persist_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.cache_db_path).parent.mkdir(parents=True, exist_ok=True)

    # Initialize cache
    from app.memory.cache import ResearchCache

    cache = ResearchCache()
    await cache.init()

    logger.info(
        "application_started",
        env=settings.app_env.value,
        llm_provider=settings.default_llm_provider.value,
        llm_model=settings.default_llm_model,
    )

    yield

    # Cleanup
    logger.info("application_shutting_down")


app = FastAPI(
    title="Autonomous Research Agent API",
    description=(
        "Production-grade AI research agent that autonomously searches the web, "
        "collects and verifies information, and generates professional research reports."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("unhandled_exception", error=str(exc), path=request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal error occurred. Please try again."},
    )


# Include routes
from app.api.routes import router

app.include_router(router, prefix="/api/v1")


# Root redirect
@app.get("/", include_in_schema=False)
async def root():
    return {
        "name": "Autonomous Research Agent",
        "version": "1.0.0",
        "docs": "/docs",
        "api": "/api/v1",
    }
