"""Civic Pulse — Centralised application settings loaded from environment / ``.env``.

Uses ``pydantic-settings`` so every value is typed, validated at startup, and
available as a cached singleton via :func:`get_settings`.
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All configuration knobs consumed by the Civic Pulse backend.

    Values are resolved in standard ``pydantic-settings`` priority order:
    explicit init kwargs → environment variables → ``.env`` file → defaults.
    """

    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ------------------------------------------------------------------
    # Application
    # ------------------------------------------------------------------
    APP_ENV: str = "development"
    DEBUG: bool = True
    LOG_LEVEL: str = "info"
    SERVER_HOST: str = "0.0.0.0"
    SERVER_PORT: int = 8000

    # ------------------------------------------------------------------
    # PostgreSQL (async + sync engines)
    # ------------------------------------------------------------------
    DATABASE_URL: str = (
        "postgresql+asyncpg://civicpulse:civicpulse_secret@localhost:5432/civicpulse_db"
    )
    SYNC_DATABASE_URL: str = (
        "postgresql+psycopg2://civicpulse:civicpulse_secret@localhost:5432/civicpulse_db"
    )

    # ------------------------------------------------------------------
    # Redis
    # ------------------------------------------------------------------
    REDIS_URL: str = "redis://localhost:6379/0"

    # ------------------------------------------------------------------
    # Object Storage (MinIO / S3)
    # ------------------------------------------------------------------
    S3_ENDPOINT_URL: str = "http://localhost:9000"
    S3_ACCESS_KEY: str = "minioadmin"
    S3_SECRET_KEY: str = "minioadmin_secret"
    S3_BUCKET_NAME: str = "civicpulse-media"
    S3_PUBLIC_BASE_URL: str = "http://localhost:9000/civicpulse-media"
    S3_REGION: str = "us-east-1"

    # ------------------------------------------------------------------
    # Authentication & Security
    # ------------------------------------------------------------------
    JWT_SECRET_KEY: str = (
        "09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7"
    )
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # AES-256-GCM — 32-byte key encoded as Base64
    PII_ENCRYPTION_KEY: str = "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="

    # ------------------------------------------------------------------
    # External AI & API Integrations
    # ------------------------------------------------------------------
    GEMINI_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    BHASHINI_API_KEY: str = ""
    BHASHINI_USER_ID: str = ""
    BHASHINI_PIPELINE_ID: str = ""
    GOOGLE_FACTCHECK_API_KEY: str = ""

    # ------------------------------------------------------------------
    # CORS
    # ------------------------------------------------------------------
    CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def _parse_cors_origins(cls, v: Any) -> list[str]:
        """Accept both a JSON array string and a native Python list."""
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
                if isinstance(parsed, list):
                    return [str(item) for item in parsed]
            except (json.JSONDecodeError, TypeError):
                # Comma-separated fallback: "http://a,http://b"
                return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v  # type: ignore[return-value]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached :class:`Settings` singleton.

    Call this function instead of constructing ``Settings()`` directly so that
    environment parsing happens at most once per process.
    """
    return Settings()

