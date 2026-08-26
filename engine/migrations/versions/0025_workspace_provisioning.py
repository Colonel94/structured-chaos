"""workspace provisioning — narrow RLS-safe signup function"""

from __future__ import annotations

import re
from collections.abc import Sequence

from alembic import op

from app.config import settings

revision: str = "0025_workspace_provisioning"
down_revision: str | None = "0024_deletion_ledger"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_APP_ROLE = settings.postgres_user


def upgrade() -> None:
    if not re.fullmatch(r"[a-z_][a-z0-9_]*", _APP_ROLE):
        raise ValueError("unsafe app role identifier")
    # Signup occurs before a tenant GUC can exist. Expose one operation rather than weakening tenant RLS
    # or putting an admin connection on the request path. The fixed search_path prevents object shadowing.
    op.execute("""
        CREATE FUNCTION create_review_workspace(workspace_name text) RETURNS uuid
        LANGUAGE plpgsql SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $function$
        DECLARE workspace_id uuid;
        BEGIN
          IF char_length(trim(workspace_name)) NOT BETWEEN 2 AND 120 THEN
            RAISE EXCEPTION 'invalid workspace name';
          END IF;
          INSERT INTO public.tenant (name) VALUES (trim(workspace_name)) RETURNING id INTO workspace_id;
          RETURN workspace_id;
        END
        $function$
    """)
    op.execute("REVOKE ALL ON FUNCTION create_review_workspace(text) FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION create_review_workspace(text) TO {_APP_ROLE}")
    op.execute(f"REVOKE INSERT ON tenant FROM {_APP_ROLE}")


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS create_review_workspace(text)")
    op.execute(f"GRANT INSERT ON tenant TO {_APP_ROLE}")
