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

from pydantic import Field, model_validator
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
    # Egress channel — default LOCAL ($0 record-and-relay PoC sink); `cloud` = WhatsApp Cloud API,
    # the deferred path (needs the Meta test number), so it raises loudly if selected before setup.
    channel_backend: Backend = Backend.local

    # --- cloud credentials (empty until Gate A; smoke scripts assert 200) ---
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-haiku-4-5"
    cohere_api_key: str = ""

    # --- whatsapp (dev test number) ---
    whatsapp_token: str = ""
    whatsapp_phone_number_id: str = ""
    whatsapp_verify_token: str = ""
    whatsapp_app_secret: str = ""
    # Graph API version the send call targets — configurable so a version deprecation is a .env change,
    # not a code edit. Match whatever the Meta app dashboard shows (e.g. v21.0).
    whatsapp_api_version: str = "v21.0"
    # The tenant an inbound WhatsApp message is ingested into. The webhook carries no X-Tenant-Id (it is
    # Meta calling, not the review UI), so a WhatsApp number maps to exactly one tenant here. PoC: one
    # configured tenant; a multi-number product would map phone_number_id → tenant instead.
    whatsapp_tenant_id: str = ""

    # --- customer portal (PORTAL.md) — the public /p surface is a SEPARATE router, gated on `enabled` ---
    portal_enabled: bool = False  # the public routes only mount when this is on (fail-closed)
    portal_secret: str = (
        ""  # HMAC key for signed case tokens; the router refuses to sign without it
    )
    portal_max_file_bytes: int = (
        10 * 1024 * 1024
    )  # 10 MB per file (edge limit, before any model call)
    portal_max_request_bytes: int = 25 * 1024 * 1024  # 25 MB per submit
    portal_rate_ip_per_10min: int = 5  # submit/answer cap per client IP
    portal_rate_tenant_per_hour: int = 60  # submit/answer cap per tenant
    portal_stall_seconds: int = (
        90  # a still-processing case older than this shows "taking longer" copy
    )

    # --- sentiment trajectory (rules/sentiment) ---
    # The recency window the peak/trend is computed over. A case can accrue MULTIPLE episodes (an original
    # complaint, a follow-up windowing folds in days later, a "thanks" within the reopen window); without a
    # bound, a single early angry reading would route the case as angry FOREVER, including after it's
    # resolved. So readings older than this before the latest reading age out of the arc — peak/trend
    # reflect the CURRENT episode, not the case's whole lifetime. 72h > the 24h same-conversation gap (a
    # multi-day active complaint keeps its peak) but < a week (a later thank-you ages the old anger out).
    sentiment_window_hours: float = 72

    # --- worker liveness (R3) ---
    # A worker stamps worker_heartbeat every ~15s; if the newest beat is older than this, the worker is
    # treated as DOWN — the portal shows the honest handoff copy immediately (not an open-ended spinner)
    # and /health reports it. 60s = tolerate a missed beat or two before crying wolf.
    worker_liveness_seconds: int = 60

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

    @model_validator(mode="after")
    def _fail_closed_on_default_secrets(self) -> Settings:
        """R5 — refuse to START in prod with an empty or placeholder secret on anything reachable.

        The whole point of "market ready" is that ``change_me_*`` / the PoC portal secret never sits on a
        deployment holding real complaint data. This is fail-CLOSED: only ``app_env`` in {prod,production}
        is gated, so dev / test / the local PoC (the committed default) are entirely unaffected — a real
        deployment must set real secrets or it will not boot, with the exact list of what's missing. Never
        weaken this to a warning: a warning on a prod boot is a secret nobody rotated.
        """
        if self.app_env.strip().lower() not in ("prod", "production"):
            return self

        def insecure(v: str) -> bool:
            s = (v or "").strip().lower()
            return s == "" or "change_me" in s or "poc-portal-secret" in s

        problems: list[str] = []
        if insecure(self.postgres_password):
            problems.append("POSTGRES_PASSWORD (the app_rw runtime role)")
        if insecure(self.postgres_admin_password):
            problems.append("POSTGRES_ADMIN_PASSWORD")
        if insecure(self.minio_secret_key):
            problems.append("MINIO_SECRET_KEY")
        if self.portal_enabled and insecure(self.portal_secret):
            problems.append("PORTAL_SECRET (portal is enabled)")
        if problems:
            raise ValueError(
                "Refusing to start in prod with default/empty secrets: "
                + ", ".join(problems)
                + ". Set real values in .env before deploying "
                "(generate one with: openssl rand -hex 32). See docs/DEPLOY.md."
            )
        return self


# Import-time singleton. Cheap; reads env once.
settings = Settings()
