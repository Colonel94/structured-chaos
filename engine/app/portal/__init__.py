"""The customer-facing portal (PORTAL.md) — a SEPARATE public surface from the agent ``/api``.

A thin rendering of decisions the engine already makes: it reuses intake, windowing, extraction,
resolution, the elicitation policy + anchor+2 budget, and the rules-engine deadline unchanged. The only
portal-specific code is the signed tokens, a redacted status projection, rate-limiting/CORS/limits, and
the widget. The tenant is resolved from the embed key or the signed case token — never a client header.
"""
