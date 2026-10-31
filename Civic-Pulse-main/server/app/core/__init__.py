"""Civic Pulse shared core infrastructure package.

This package is a **read-only contract** consumed by every domain module and both
Backend Developer A (Person 2) and Backend Developer B (Person 3).

Exports:
    settings / get_settings — Pydantic-Settings singleton
    Base / AsyncSessionLocal / get_async_session — SQLAlchemy 2.0 async engine
    security helpers — Argon2 hashing, JWT, AES-256-GCM PII vault
    StorageService — S3/MinIO object store wrapper
    redis_client / publish_ws_event — Redis async client & pub/sub
    ConnectionManager — WebSocket ↔ Redis bridge
    AppException hierarchy — Structured error envelope
    ApiEnvelope / PaginatedMeta — Shared response schemas
    get_db / get_current_user / require_roles — FastAPI dependencies
"""

