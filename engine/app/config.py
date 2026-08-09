"""Typed configuration + the local|cloud|fake backend switch.

Every inference component (ASR / LLM / Embedding / Blob) sits behind one interface with
a `local` and a `cloud` backend, chosen by config, never by a code change (CLAUDE.md §4,
TECH-SPEC §0.1). The PoC runs all-cloud; local impls are stubs; tests use `fake`.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Backend(StrEnum):
    cloud = "cloud"
    local = "local"
    fake = "fake"


class Settings(BaseSettings):
    # Loads from process env or a repo-root `.env` (gitignored). extra="ignore" so the
    # shared `.env` template can carry keys a given process does not use.
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "dev"
    log_level: str = "INFO"

    # --- backend switch (one per interface) ---
    asr_backend: Backend = Backend.cloud
    llm_backend: Backend = Backend.cloud
    embedding_backend: Backend = Backend.cloud
    blob_backend: Backend = Backend.cloud

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
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "adaptive_intake"
    postgres_user: str = "app_rw"
    postgres_password: str = ""

    # --- minio / s3 ---
    minio_endpoint: str = "http://localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = ""
    minio_bucket: str = "originals"

    bge_model: str = Field(default="BAAI/bge-m3")

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


# Import-time singleton. Cheap; reads env once.
settings = Settings()
