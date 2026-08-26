"""Preflight: can this process reach Ollama and is the extraction model present? (R1)

THE deploy trap this guards against (verified 2026-08-21c, longterm_context.md §0): the compose worker/
engine reach the host GPU's Ollama via ``OLLAMA_HOST=http://host.docker.internal:11434`` +
``extra_hosts: host.docker.internal:host-gateway``. That works on Docker Desktop (which proxies
host.docker.internal to host loopback) but BREAKS on a native Linux server, where host-gateway resolves
to the docker bridge gateway (e.g. 172.17.0.1) which does NOT reach a 127.0.0.1-bound Ollama →
connection refused → every extract/elicit job retries, exhausts, and the case is honestly stamped
``processing_failed``. Silent-at-the-case-level, fatal-at-the-product-level.

Run this from the SAME context the worker runs in — ideally INSIDE the worker container, so it exercises
the exact OLLAMA_HOST + extra_hosts path:

    docker compose -f deploy/docker-compose.yml run --rm worker python /app/scripts/preflight_ollama.py

or on the host (checks the host→Ollama path):

    uv run python scripts/preflight_ollama.py

Exit 0 = reachable and the model is present. Exit non-zero = a clear diagnosis + the exact fix. Wired
into scripts/deploy_rebuild.sh so a misconfigured deploy fails LOUD instead of silently failing cases.
"""

from __future__ import annotations

import sys

import httpx

from app.config import settings


def main() -> int:
    host = settings.ollama_host.rstrip("/")
    model = settings.ollama_model
    print(f">> preflight: OLLAMA_HOST={host}  model={model}")

    try:
        resp = httpx.get(f"{host}/api/tags", timeout=5.0)
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        print(
            f"\n!! CANNOT REACH OLLAMA at {host}: {type(exc).__name__}: {exc}\n"
            "\n   This is almost certainly the container→Ollama bind trap on a native Linux host:\n"
            "   host.docker.internal:host-gateway resolves to the docker bridge gateway, which does\n"
            "   NOT reach an Ollama bound to 127.0.0.1 only.\n"
            "\n   FIX (on the host running the OLLAMA SERVER, not the container):\n"
            "     1. Bind Ollama to all interfaces:  set  OLLAMA_HOST=0.0.0.0:11434  in Ollama's\n"
            "        environment (⚠ SAME env var name, OPPOSITE role: on the host it is Ollama's BIND\n"
            "        address; in the container it is the client TARGET url — do not conflate them).\n"
            "     2. Restart Ollama, then confirm:  curl http://<host-ip>:11434/api/tags\n"
            "     3. Firewall 11434 to the docker bridge subnet ONLY (never the public internet).\n"
            "     4. Point the container at it:  OLLAMA_HOST=http://<host-bridge-ip>:11434  (or keep\n"
            "        host.docker.internal once step 1 makes it reachable).\n"
            "   On Docker Desktop (Windows/Mac) this path already works — the trap is Linux-only.\n"
            "   See docs/DEPLOY.md §Ollama.",
            file=sys.stderr,
        )
        return 2

    names = {m.get("model", m.get("name", "")) for m in resp.json().get("models", [])}
    # Ollama tags carry the full tag (e.g. "qwen3:14b"); match on prefix so "qwen3" or "qwen3:14b" pass.
    if not any(n == model or n.startswith(model.split(":")[0]) for n in names):
        print(
            f"\n!! Ollama is reachable but the model '{model}' is NOT pulled.\n"
            f"   Available: {sorted(names) or '(none)'}\n"
            f"   FIX:  ollama pull {model}\n"
            "   See docs/DEPLOY.md §Ollama.",
            file=sys.stderr,
        )
        return 3

    print(
        f">> OK: Ollama reachable at {host} and '{model}' is present. Extraction path is live."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
