"""
Central configuration.  Every account-scoped value comes from environment
variables — no hardcoded URLs, tokens, or project IDs anywhere else.
"""
from __future__ import annotations

from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Apify ─────────────────────────────────────────────────────────────────
    apify_token: str = Field(..., description="Apify API token")
    apify_actor_id: str = Field(
        default="vIGxjRrHqDTPuE6M4",
        description="fantastic.jobs LinkedIn Jobs API actor — do not change",
    )

    # ── People-search ─────────────────────────────────────────────────────────
    ai_ark_token: str = Field(default="", description="AI Ark bearer token")
    prospeo_api_key: str = Field(default="", description="Prospeo.io API key")
    people_search_provider: Literal["ai_ark", "prospeo", "both"] = Field(
        default="both",
        description="Which people-search provider to use. 'both' = AI Ark primary, Prospeo fallback.",
    )
    people_search_max_results: int = Field(
        default=2,
        description="Hard cap: max people returned per people_search call (credit budget).",
    )

    # ── OpenRouter ────────────────────────────────────────────────────────────
    openrouter_api_key: str = Field(..., description="OpenRouter API key")
    openrouter_base_url: str = Field(
        default="https://openrouter.ai/api/v1",
        description="OpenRouter base URL",
    )
    # Model for ICP fit-check — must support web search / online browsing
    icp_model: str = Field(
        default="perplexity/sonar",
        description="Web-enabled model for ICP company fit-check",
    )
    # Model for hiring-manager validation — cheap classification task
    hm_validation_model: str = Field(
        default="deepseek/deepseek-chat",
        description="Cheap model for hiring-manager validation",
    )

    # ── Supabase ──────────────────────────────────────────────────────────────
    supabase_url: str = Field(..., description="Supabase project URL")
    supabase_service_role_key: str = Field(
        ..., description="Supabase service-role key (server-side ingest)"
    )
    supabase_db_url: str = Field(
        default="", description="Optional direct Postgres connection string"
    )

    # ── Pipeline tuning ───────────────────────────────────────────────────────
    max_scrape_items: int = Field(
        default=500,
        description="Max jobs to pull from Apify per run (stay within free tier)",
    )
    scrape_time_range: str = Field(default="7d", description="Apify time-range filter")
    dmm_cascade_levels: list[str] = Field(
        default=["city", "country", "region", "worldwide"],
        description="Geographic cascade order for people-search",
    )
    pipeline_concurrency: int = Field(
        default=5,
        description="asyncio.Semaphore cap for concurrent API calls",
    )

    # ── Observability ─────────────────────────────────────────────────────────
    log_level: str = Field(default="INFO")
    output_dir: str = Field(default="output")


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
