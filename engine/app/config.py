"""Typed configuration + the local|cloud|fake backend switch.

Every inference component (ASR / LLM / Embedding / Blob) sits behind one interface with
a `local` and a `cloud` backend, chosen by config, never by a code change (CLAUDE.md §4,
TECH-SPEC §0.1). The PoC runs all-LOCAL on the 4070 (owner override 2026-08-10):
faster-whisper / Ollama / BGE-M3 / MinIO. The cloud impls are the deferred path (ASR/LLM/embed
cloud modules are not built yet). Tests use `fake`.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Absolute path to the repo-root `.env`, so config loads identically from any CWD
# (repo root, engine/, a test runner, alembic). engine/app/config.py → parents[2] = repo root.
_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Backend(StrEnum):
    cloud = "cloud"
    local = "local"
    fake = "fake"


class Settings(BaseSettings):
    # Loads from process env (which overrides) or the repo-root `.env` (gitignored).
    # extra="ignore" so the shared `.env` template can carry keys a given process does not use.
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE), env_file_encoding="utf-8", extra="ignore"
    )

    app_env: str = "dev"
    log_level: str = "INFO"
    # Stamped into every idempotency key (§7.3) so a code change forces a fresh run
    # instead of silently colliding with a prior one. Bump on any extraction-behaviour change.
    code_version: str = "0.1.0"

    # --- backend switch (one per interface) — default LOCAL (the committed PoC path); the .env
    #     sets these explicitly. Defaulting to `cloud` here would ImportError on a fresh checkout,
    #     since the cloud ASR/LLM/embed impls are not built yet. ---
    asr_backend: Backend = Backend.local
    llm_backend: Backend = Backend.local
    embedding_backend: Backend = Backend.local
    blob_backend: Backend = Backend.local

    # --- cloud credentials (empty until Gate A; smoke scripts assert 200) ---
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-haiku-4-5"
    cohere_api_key: str = ""

    # --- whatsapp (dev test number) ---
    whatsapp_token: str = ""
    whatsapp_phone_number_id: str = ""
    whatsapp_verify_token: str = ""
    whatsapp_app_secret: str = ""

    # --- postgres ---
    # TWO roles, deliberately (EDD §7.1). The engine connects as the least-privilege
    # `app_rw` (NOSUPERUSER, NOBYPASSRLS) so RLS is actually enforced against it; migrations
    # and role bootstrap run as the superuser `intake_admin`. A single superuser here would
    # silently bypass RLS and make the tenant-isolation gate unprovable.
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "adaptive_intake"
    postgres_user: str = "app_rw"  # runtime app role — RLS-enforced
    postgres_password: str = ""
    postgres_admin_user: str = "intake_admin"  # superuser — migrations/bootstrap only
    postgres_admin_password: str = ""

    # --- minio / s3 ---
    minio_endpoint: str = "http://localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = ""
    minio_bucket: str = "originals"

    bge_model: str = Field(default="BAAI/bge-m3")

    # --- local model backends (PoC primary path — on the 4070, $0, no external call) ---
    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "qwen3:14b"  # reasoning model → extraction must disable "think"
    whisper_model: str = "large-v3"
    whisper_device: str = "auto"  # auto → cuda if available else cpu
    # OCR language (English-first, 2026-08-12 §0): "en" selects PP-OCRv5; "ar" the Arabic path.
    # The Gulf-Arabic voice moat capability is retained in code, just deprioritised for now.
    ocr_lang: str = "en"

    @property
    def database_url(self) -> str:
        """Runtime connection as the RLS-enforced `app_rw` role (the engine uses this)."""
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def admin_database_url(self) -> str:
        """Privileged connection as `intake_admin` — migrations and role bootstrap only."""
        return (
            f"postgresql+psycopg://{self.postgres_admin_user}:{self.postgres_admin_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


# Import-time singleton. Cheap; reads env once.
settings = Settings()
