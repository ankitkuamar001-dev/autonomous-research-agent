"""LangGraph state persistence via async SQLite checkpointer.

Provides a thin factory that creates and returns an ``AsyncSqliteSaver``
for durable workflow state across restarts and crash recovery.
"""

from __future__ import annotations

from pathlib import Path

import structlog
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from app.config import get_settings

logger = structlog.get_logger(__name__)


async def get_checkpointer(
    db_path: str | None = None,
) -> AsyncSqliteSaver:
    """Create and return an async SQLite checkpointer for LangGraph.

    Parameters
    ----------
    db_path:
        Optional override for the database file path.  Falls back to
        ``<chroma_persist_dir>/../checkpoints.db`` derived from settings.

    Returns
    -------
    AsyncSqliteSaver
        A ready-to-use LangGraph checkpointer backed by SQLite.
    """
    settings = get_settings()

    if db_path is None:
        checkpoint_dir = Path(settings.chroma_persist_dir).parent
        checkpoint_dir.mkdir(parents=True, exist_ok=True)
        db_path = str(checkpoint_dir / "checkpoints.db")

    logger.info("creating_langgraph_checkpointer", db_path=db_path)

    checkpointer = AsyncSqliteSaver.from_conn_string(db_path)

    logger.info("checkpointer_ready", db_path=db_path)
    return checkpointer
