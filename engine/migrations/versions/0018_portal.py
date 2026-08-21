"""Customer portal — per-tenant embed key + CORS origins, and the ``web`` intake channel (Phase: portal)

The first customer-facing front door (PORTAL.md). Two additions to ``tenant``:
  * ``embed_key``       — the public, write-only capability that a business drops in its ``<script>`` tag.
                          It can only CREATE a case for its tenant (via /p/submit); it can read nothing.
                          Unique + nullable (set when a tenant is onboarded to the portal).
  * ``allowed_origins`` — the CORS allowlist for that tenant's embed (which sites may POST to /p).

And ``web`` joins the ``channel`` CHECK on ``case_record`` + ``source_document`` so a portal case (and its
source docs) is a first-class channel alongside whatsapp / email / file_drop — the portal is "just another
channel", so nothing else about the case model changes.

No RLS change: ``tenant`` is the un-scoped root table (an admin reads it to resolve a key → tenant, then
sets the GUC). Reversible.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

from app.config import settings

revision: str = "0018_portal"
down_revision: str | None = "0017_case_commit"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_APP_ROLE = settings.postgres_user
_CHANNELS_NEW = "('whatsapp','email','file_drop','web')"
_CHANNELS_OLD = "('whatsapp','email','file_drop')"


def upgrade() -> None:
    op.execute("ALTER TABLE tenant ADD COLUMN embed_key text")
    op.execute("ALTER TABLE tenant ADD COLUMN allowed_origins jsonb NOT NULL DEFAULT '[]'::jsonb")
    op.execute("CREATE UNIQUE INDEX ix_tenant_embed_key ON tenant (embed_key)")

    # The portal resolves embed_key → tenant BEFORE any tenant is known, so the existing RLS policy
    # (id = app.tenant_id GUC) can't serve it. This PERMISSIVE, SELECT-only policy lets the app role read
    # exactly the one tenant row whose embed_key it presents via the `app.embed_key` GUC — the embed key
    # is the public capability, so reading that tenant's id + allowed_origins with it is precisely its
    # purpose. It grants nothing beyond that row, and only for SELECT. (OR-combines with `tenant_self`.)
    op.execute(f"""
        CREATE POLICY tenant_by_embed_key ON tenant FOR SELECT TO {_APP_ROLE}
          USING (
            embed_key IS NOT NULL
            AND embed_key = NULLIF(current_setting('app.embed_key', true), '')
          )
        """)

    # `web` becomes a valid intake channel for the portal (case + its source documents).
    for table in ("case_record", "source_document"):
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT {table}_channel_check")
        op.execute(
            f"ALTER TABLE {table} ADD CONSTRAINT {table}_channel_check "
            f"CHECK (channel IN {_CHANNELS_NEW})"
        )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_by_embed_key ON tenant")
    for table in ("case_record", "source_document"):
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT {table}_channel_check")
        op.execute(
            f"ALTER TABLE {table} ADD CONSTRAINT {table}_channel_check "
            f"CHECK (channel IN {_CHANNELS_OLD})"
        )
    op.execute("DROP INDEX IF EXISTS ix_tenant_embed_key")
    op.execute("ALTER TABLE tenant DROP COLUMN allowed_origins")
    op.execute("ALTER TABLE tenant DROP COLUMN embed_key")
