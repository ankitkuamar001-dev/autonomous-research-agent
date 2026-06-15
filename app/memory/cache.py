"""Async SQLite-backed research cache with TTL support.

Caches search results and scraped content to avoid redundant network
calls across research sessions.  Values are JSON-serialized and
expired entries are cleaned up automatically.
"""

from __future__ import annotations

import json
import time
from typing import Any

import aiosqlite
import structlog

from app.config import get_settings

logger = structlog.get_logger(__name__)

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS cache (
    key   TEXT PRIMARY KEY,
    value TEXT    NOT NULL,
    created_at REAL NOT NULL,
    ttl_hours  INTEGER NOT NULL
);
"""

_CREATE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_cache_expiry
    ON cache (created_at, ttl_hours);
"""


class ResearchCache:
    """Async SQLite cache with per-key TTL.

    Usage::

        cache = ResearchCache()
        await cache.init()

        await cache.set("search:q1", {"results": [...]}, ttl_hours=24)
        data = await cache.get("search:q1")  # returns dict or None
    """

    def __init__(self, db_path: str | None = None) -> None:
        settings = get_settings()
        self._db_path = db_path or str(settings.cache_path)
        self._db: aiosqlite.Connection | None = None

    # ── Lifecycle ───────────────────────────────────────────────

    async def init(self) -> None:
        """Open the database and ensure the schema exists."""
        import os
        os.makedirs(os.path.dirname(self._db_path) or ".", exist_ok=True)

        self._db = await aiosqlite.connect(self._db_path)
        await self._db.execute(_CREATE_TABLE_SQL)
        await self._db.execute(_CREATE_INDEX_SQL)
        await self._db.commit()

        logger.info("cache_initialized", db_path=self._db_path)

    async def close(self) -> None:
        """Close the database connection."""
        if self._db:
            await self._db.close()
            self._db = None
            logger.info("cache_closed", db_path=self._db_path)

    async def __aenter__(self) -> "ResearchCache":
        await self.init()
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    # ── Core Operations ─────────────────────────────────────────

    async def get(self, key: str) -> Any | None:
        """Retrieve a cached value by key.

        Returns ``None`` if the key does not exist or has expired.
        """
        self._ensure_connected()
        assert self._db is not None

        now = time.time()
        async with self._db.execute(
            "SELECT value, created_at, ttl_hours FROM cache WHERE key = ?",
            (key,),
        ) as cursor:
            row = await cursor.fetchone()

        if row is None:
            return None

        value_json, created_at, ttl_hours = row
        expires_at = created_at + (ttl_hours * 3600)

        if now > expires_at:
            # Entry has expired — remove it lazily
            await self._db.execute("DELETE FROM cache WHERE key = ?", (key,))
            await self._db.commit()
            logger.debug("cache_expired", key=key)
            return None

        logger.debug("cache_hit", key=key)
        return json.loads(value_json)

    async def set(
        self,
        key: str,
        value: Any,
        ttl_hours: int | None = None,
    ) -> None:
        """Store a value in the cache.

        Parameters
        ----------
        key:
            Cache key (must be unique).
        value:
            Any JSON-serializable value.
        ttl_hours:
            Time-to-live in hours.  Defaults to the configured
            ``cache_search_ttl_hours`` from settings.
        """
        self._ensure_connected()
        assert self._db is not None

        settings = get_settings()
        if ttl_hours is None:
            ttl_hours = settings.cache_search_ttl_hours

        value_json = json.dumps(value, default=str)
        now = time.time()

        await self._db.execute(
            """
            INSERT INTO cache (key, value, created_at, ttl_hours)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                created_at = excluded.created_at,
                ttl_hours = excluded.ttl_hours
            """,
            (key, value_json, now, ttl_hours),
        )
        await self._db.commit()
        logger.debug("cache_set", key=key, ttl_hours=ttl_hours)

    async def invalidate(self, key: str) -> bool:
        """Remove a specific key from the cache.

        Returns ``True`` if the key existed, ``False`` otherwise.
        """
        self._ensure_connected()
        assert self._db is not None

        cursor = await self._db.execute(
            "DELETE FROM cache WHERE key = ?", (key,)
        )
        await self._db.commit()
        deleted = cursor.rowcount > 0

        if deleted:
            logger.debug("cache_invalidated", key=key)
        return deleted

    async def invalidate_prefix(self, prefix: str) -> int:
        """Remove all keys starting with *prefix*.

        Returns the number of entries removed.
        """
        self._ensure_connected()
        assert self._db is not None

        cursor = await self._db.execute(
            "DELETE FROM cache WHERE key LIKE ?", (f"{prefix}%",)
        )
        await self._db.commit()
        count = cursor.rowcount

        logger.info("cache_prefix_invalidated", prefix=prefix, count=count)
        return count

    async def cleanup_expired(self) -> int:
        """Remove all expired entries.

        Returns the number of entries removed.
        """
        self._ensure_connected()
        assert self._db is not None

        now = time.time()
        cursor = await self._db.execute(
            "DELETE FROM cache WHERE (created_at + ttl_hours * 3600) < ?",
            (now,),
        )
        await self._db.commit()
        count = cursor.rowcount

        logger.info("cache_cleanup", expired_count=count)
        return count

    async def stats(self) -> dict[str, Any]:
        """Return cache statistics.

        Returns
        -------
        dict
            Keys: ``total_entries``, ``expired_entries``, ``db_path``.
        """
        self._ensure_connected()
        assert self._db is not None

        now = time.time()
        async with self._db.execute("SELECT COUNT(*) FROM cache") as cur:
            total = (await cur.fetchone())[0]  # type: ignore[index]

        async with self._db.execute(
            "SELECT COUNT(*) FROM cache WHERE (created_at + ttl_hours * 3600) < ?",
            (now,),
        ) as cur:
            expired = (await cur.fetchone())[0]  # type: ignore[index]

        return {
            "total_entries": total,
            "expired_entries": expired,
            "db_path": self._db_path,
        }

    # ── Internal ────────────────────────────────────────────────

    def _ensure_connected(self) -> None:
        if self._db is None:
            raise RuntimeError(
                "Cache not initialized — call `await cache.init()` or use "
                "`async with ResearchCache() as cache:`"
            )
