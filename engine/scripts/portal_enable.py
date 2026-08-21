"""Onboard a tenant to the customer portal: mint a public embed key + register its CORS origins.

Manual tenant onboarding is allowed behind the scenes (winning-condition §6). Prints the embed key, the
<script> tag to drop on the business's site, and the standalone links to share.

Usage:
    uv run python scripts/portal_enable.py "Bakery Co" https://bakery.example http://localhost:5173
"""

from __future__ import annotations

import json
import secrets
import sys

from sqlalchemy import text

from app.store import api
from app.store.db import admin_session


def main() -> int:
    if len(sys.argv) < 2:
        print('usage: portal_enable.py "<tenant name>" [allowed-origin ...]')
        return 1
    name = sys.argv[1]
    origins = sys.argv[2:]
    embed_key = "ek_" + secrets.token_urlsafe(18)

    with admin_session() as a:
        tid = a.execute(
            text("SELECT id FROM tenant WHERE name = :n ORDER BY id LIMIT 1"), {"n": name}
        ).scalar()
        if tid is None:
            tid = api.create_tenant(a, name)
        a.execute(
            text("UPDATE tenant SET embed_key = :k, allowed_origins = :o WHERE id = :t"),
            {"k": embed_key, "o": json.dumps(origins), "t": tid},
        )

    print(f"\ntenant       : {tid}  ({name})")
    print(f"embed key    : {embed_key}")
    print(f"origins      : {origins or '(none — embed only works same-origin / standalone page)'}")
    print("\nEmbed on a site (one tag):")
    print(f'  <script src="https://YOUR-HOST/p/embed.js" data-key="{embed_key}"></script>')
    print("\nShareable links (no website needed):")
    print(f"  submit :  https://YOUR-HOST/p/s/{embed_key}")
    print("  status :  the link the customer gets after submitting (their signed case token)")
    print("\nRun the engine with PORTAL_ENABLED=true and PORTAL_SECRET set.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
