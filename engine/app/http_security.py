"""Shared HTTP security-header helpers.

The Content-Security-Policy is defined ONCE here so the global middleware (``app.main``) and any route
that must vary it can never drift apart — two independently-maintained CSP strings is exactly how a
directive silently weakens. The only route that varies it today is the portal standalone page, which
authorises its single trusted inline config ``<script>`` with a per-response nonce (the app default is
``script-src 'self'`` with no ``'unsafe-inline'``, so that inline script is otherwise blocked and the
widget loads with no embed key — see ``app/portal/router.py``).
"""

from __future__ import annotations


def content_security_policy(script_src: str = "'self'") -> str:
    """The application CSP. ``script_src`` is the only knob a caller overrides — e.g. a route adding a
    per-response ``'nonce-…'`` for one trusted inline script — everything else stays fixed and strict.
    """
    return (
        "default-src 'self'; connect-src 'self'; font-src 'self'; "
        "img-src 'self' blob: data:; media-src 'self' blob:; object-src 'none'; "
        "base-uri 'self'; frame-ancestors 'none'; form-action 'self'; "
        f"style-src 'self' 'unsafe-inline'; script-src {script_src}"
    )
