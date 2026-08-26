"""least-privilege authentication RPCs — keep credential tables unreadable to app_rw"""

from __future__ import annotations

import re
from collections.abc import Sequence

from alembic import op

from app.config import settings

revision: str = "0027_auth_least_privilege"
down_revision: str | None = "0026_membership_workspace_name"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_APP_ROLE = settings.postgres_user


def _validate_role() -> None:
    if not re.fullmatch(r"[a-z_][a-z0-9_]*", _APP_ROLE):
        raise ValueError("unsafe app role identifier")


def upgrade() -> None:
    _validate_role()
    # Auth happens before a tenant GUC exists, but that does not justify giving the runtime role bulk
    # SELECT access to every password hash and live session. Expose only exact-key operations through
    # fixed-search-path SECURITY DEFINER functions; table ownership remains with the migration role.
    op.execute(f"REVOKE ALL ON app_user, workspace_membership, review_session FROM {_APP_ROLE}")
    op.execute("""
        CREATE FUNCTION create_review_identity(
            login_email text, person_name text, password_salt bytea, password_digest bytea,
            new_workspace_name text
        ) RETURNS TABLE(user_id uuid, tenant_id uuid)
        LANGUAGE plpgsql SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $function$
        DECLARE new_user_id uuid; new_tenant_id uuid;
        BEGIN
          INSERT INTO public.tenant (name)
          VALUES (trim(new_workspace_name)) RETURNING id INTO new_tenant_id;
          INSERT INTO public.app_user (email, display_name, password_salt, password_hash)
          VALUES (login_email, person_name, password_salt, password_digest)
          RETURNING id INTO new_user_id;
          INSERT INTO public.workspace_membership
              (user_id, tenant_id, role, workspace_name)
          VALUES (new_user_id, new_tenant_id, 'admin', trim(new_workspace_name));
          user_id := new_user_id;
          tenant_id := new_tenant_id;
          RETURN NEXT;
        END
        $function$
    """)
    op.execute("""
        CREATE FUNCTION lookup_review_login(login_email text)
        RETURNS TABLE(user_id uuid, email text, display_name text, password_salt bytea,
                      password_hash bytea, tenant_id uuid, role text, workspace_name text)
        LANGUAGE sql STABLE SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $function$
          SELECT u.id, u.email, u.display_name, u.password_salt, u.password_hash,
                 m.tenant_id, m.role, m.workspace_name
            FROM public.app_user u
            JOIN public.workspace_membership m ON m.user_id = u.id
           WHERE u.email = login_email
           ORDER BY m.created_at
           LIMIT 1
        $function$
    """)
    op.execute("""
        CREATE FUNCTION lookup_review_session(session_token_hash text)
        RETURNS TABLE(user_id uuid, tenant_id uuid, email text, display_name text,
                      role text, workspace_name text)
        LANGUAGE sql STABLE SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $function$
          SELECT s.user_id, s.tenant_id, u.email, u.display_name, m.role, m.workspace_name
            FROM public.review_session s
            JOIN public.app_user u ON u.id = s.user_id
            JOIN public.workspace_membership m
              ON m.user_id = s.user_id AND m.tenant_id = s.tenant_id
           WHERE s.token_hash = session_token_hash
             AND s.revoked_at IS NULL AND s.expires_at > now()
        $function$
    """)
    op.execute("""
        CREATE FUNCTION create_review_session(
            session_user_id uuid, session_tenant_id uuid, session_token_hash text,
            session_csrf_hash text, session_expires_at timestamptz
        ) RETURNS void
        LANGUAGE sql VOLATILE SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $function$
          INSERT INTO public.review_session
              (user_id, tenant_id, token_hash, csrf_hash, expires_at)
          SELECT session_user_id, session_tenant_id, session_token_hash,
                 session_csrf_hash,
                 least(session_expires_at, now() + interval '12 hours')
            FROM public.workspace_membership
           WHERE user_id = session_user_id AND tenant_id = session_tenant_id
             AND session_expires_at > now()
        $function$
    """)
    op.execute("""
        CREATE FUNCTION lookup_review_csrf(session_token_hash text) RETURNS text
        LANGUAGE sql STABLE SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $function$
          SELECT csrf_hash::text FROM public.review_session
           WHERE token_hash = session_token_hash
             AND revoked_at IS NULL AND expires_at > now()
        $function$
    """)
    op.execute("""
        CREATE FUNCTION revoke_review_session(session_token_hash text) RETURNS void
        LANGUAGE sql VOLATILE SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $function$
          UPDATE public.review_session SET revoked_at = now()
           WHERE token_hash = session_token_hash AND revoked_at IS NULL
        $function$
    """)
    signatures = (
        "create_review_identity(text,text,bytea,bytea,text)",
        "lookup_review_login(text)",
        "lookup_review_session(text)",
        "create_review_session(uuid,uuid,text,text,timestamptz)",
        "lookup_review_csrf(text)",
        "revoke_review_session(text)",
    )
    for signature in signatures:
        op.execute(f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC")
        op.execute(f"GRANT EXECUTE ON FUNCTION {signature} TO {_APP_ROLE}")


def downgrade() -> None:
    _validate_role()
    for signature in (
        "revoke_review_session(text)",
        "lookup_review_csrf(text)",
        "create_review_session(uuid,uuid,text,text,timestamptz)",
        "lookup_review_session(text)",
        "lookup_review_login(text)",
        "create_review_identity(text,text,bytea,bytea,text)",
    ):
        op.execute(f"DROP FUNCTION IF EXISTS {signature}")
    op.execute(f"GRANT SELECT, INSERT ON app_user TO {_APP_ROLE}")
    op.execute(f"GRANT SELECT, INSERT ON workspace_membership TO {_APP_ROLE}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON review_session TO {_APP_ROLE}")
