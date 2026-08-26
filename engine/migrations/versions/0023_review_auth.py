"""review authentication — accounts, memberships, hashed sessions, and CSRF binding"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

from app.config import settings

revision: str = "0023_review_auth"
down_revision: str | None = "0022_case_feedback"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_APP_ROLE = settings.postgres_user


def upgrade() -> None:
    op.execute("""
        CREATE TABLE app_user (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            email text NOT NULL,
            display_name text NOT NULL,
            password_salt bytea NOT NULL,
            password_hash bytea NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            CHECK (email = lower(email))
        )
    """)
    op.execute("CREATE UNIQUE INDEX ux_app_user_email ON app_user (lower(email))")
    op.execute("""
        CREATE TABLE workspace_membership (
            user_id uuid NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
            tenant_id uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
            role text NOT NULL CHECK (role IN ('admin', 'reviewer')),
            created_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (user_id, tenant_id)
        )
    """)
    op.execute("CREATE INDEX ix_workspace_membership_tenant ON workspace_membership (tenant_id)")
    op.execute("""
        CREATE TABLE review_session (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id uuid NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
            tenant_id uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
            token_hash char(64) NOT NULL UNIQUE,
            csrf_hash char(64) NOT NULL,
            expires_at timestamptz NOT NULL,
            revoked_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            FOREIGN KEY (user_id, tenant_id)
                REFERENCES workspace_membership (user_id, tenant_id) ON DELETE CASCADE
        )
    """)
    op.execute("CREATE INDEX ix_review_session_expiry ON review_session (expires_at)")
    # These are global identity tables, intentionally not tenant-content tables: session resolution
    # happens before the tenant GUC exists. The runtime gets only the operations used by auth.
    op.execute(f"GRANT SELECT, INSERT ON tenant TO {_APP_ROLE}")
    op.execute(f"GRANT SELECT, INSERT ON app_user TO {_APP_ROLE}")
    op.execute(f"GRANT SELECT, INSERT ON workspace_membership TO {_APP_ROLE}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON review_session TO {_APP_ROLE}")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS review_session CASCADE")
    op.execute("DROP TABLE IF EXISTS workspace_membership CASCADE")
    op.execute("DROP TABLE IF EXISTS app_user CASCADE")
