"""Application configuration loaded from environment variables."""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(str, Enum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class LLMProvider(str, Enum):
    GEMINI = "gemini"
    GROQ = "groq"


class Settings(BaseSettings):
    """Central configuration — reads from .env automatically."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Environment ──────────────────────────────────────────────
    app_env: Environment = Environment.DEVELOPMENT
    log_level: str = "INFO"

    # ── LLM Provider Keys ───────────────────────────────────────
    gemini_api_key: str = ""
    groq_api_key: str = ""
    huggingfacehub_api_token: str = ""

    # ── Search API Keys ─────────────────────────────────────────
    tavily_api_key: str = ""

    # ── Default LLM Settings ────────────────────────────────────
    default_llm_provider: LLMProvider = LLMProvider.GEMINI
    default_llm_model: str = "gemini-2.0-flash"
    fast_llm_model: str = "gemini-2.0-flash"
    strong_llm_model: str = "gemini-2.5-flash"

    # ── ChromaDB ────────────────────────────────────────────────
    chroma_persist_dir: str = "./data/chroma"
    chroma_collection_prefix: str = "research_"

    # ── Cache ───────────────────────────────────────────────────
    cache_db_path: str = "./data/cache.db"
    cache_search_ttl_hours: int = 24
    cache_scrape_ttl_hours: int = 168  # 7 days

    # ── Rate Limits ─────────────────────────────────────────────
    search_max_per_minute: int = 10
    scrape_concurrency: int = 10
    scrape_timeout_seconds: int = 15

    # ── Report Output ───────────────────────────────────────────
    reports_dir: str = "./reports"

    # ── Depth Configurations ────────────────────────────────────
    quick_max_sources: int = 8
    standard_max_sources: int = 25
    deep_max_sources: int = 50
    quick_max_queries: int = 5
    standard_max_queries: int = 10
    deep_max_queries: int = 20

    # ── Derived Paths ───────────────────────────────────────────
    @property
    def chroma_path(self) -> Path:
        return Path(self.chroma_persist_dir)

    @property
    def cache_path(self) -> Path:
        return Path(self.cache_db_path)

    @property
    def reports_path(self) -> Path:
        return Path(self.reports_dir)

    def get_max_sources(self, depth: str) -> int:
        return {
            "quick": self.quick_max_sources,
            "standard": self.standard_max_sources,
            "deep": self.deep_max_sources,
        }.get(depth, self.standard_max_sources)

    def get_max_queries(self, depth: str) -> int:
        return {
            "quick": self.quick_max_queries,
            "standard": self.standard_max_queries,
            "deep": self.deep_max_queries,
        }.get(depth, self.standard_max_queries)


@lru_cache
def get_settings() -> Settings:
    """Cached singleton — call this everywhere instead of instantiating Settings()."""
    return Settings()
