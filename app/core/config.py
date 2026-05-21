"""
Centralized application configuration.
Uses pydantic-settings to load from environment variables / .env file.
Every config value is defined here — no magic strings scattered across the codebase.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # --- App ---
    app_env: str = "development"
    app_debug: bool = False
    app_title: str = "SportyTadka API"
    app_version: str = "0.1.0"

    # --- Database ---
    # SQLite for local dev (zero setup), PostgreSQL for production (Render)
    database_url: str = "sqlite+aiosqlite:///./sportytadka.db"

    # --- CORS ---
    cors_origins: str = "http://localhost:3000"

    # --- Cricket API ---
    cricket_api_key: str = ""
    cricket_api_base_url: str = "https://api.cricapi.com/v1"

    # --- Football API (football-data.org) ---
    football_api_key: str = ""

    # --- NBA API (balldontlie.io) ---
    nba_api_key: str = ""

    # --- Gemini AI ---
    gemini_api_key: str = ""

    # --- Polling ---
    live_match_poll_interval: int = 30
    upcoming_match_poll_interval: int = 300

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",")]

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton. Call this everywhere you need config."""
    return Settings()
