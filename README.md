# Adaptive Intake

Adaptive Intake turns an unstructured complaint—text, documents, images, or voice—into a structured,
prioritised case that a human can verify against its source before anything is approved or reported.

## Current status

This is a working proof of concept, **not a production-ready product**. The trust spine, review flow,
customer portal, object-store matching, and local deployment path are implemented. The current measured
accuracy gates, independent validation, authentication, and external onboarding gates are not complete.
See [Market readiness](docs/MARKET-READINESS.md) for the evidence-based launch decision.

## Choose your path

- **Reviewer or operator:** start with the [User guide](docs/USER-GUIDE.md).
- **Developer:** follow the local setup below, then read [Technical specification](TECH-SPEC.md).
- **Deployment owner:** use [Deployment guide](docs/DEPLOY.md) and the production gates in
  [Market readiness](docs/MARKET-READINESS.md).
- **Product decision-maker:** read the [PRD](PRD.md), then the live [build/readiness tracker](docs/tracker.html).
- **Ship decision:** read the [winning-condition audit](docs/WINNING-CONDITION-REVIEW.md).

## What the system does

1. A customer submits messy source material through the portal, file intake, or WhatsApp adapter.
2. The engine stores the original, normalises it, extracts structured fields, resolves a related order
   or job where possible, and applies tenant policy.
3. The review queue puts uncertain cases first. A reviewer can trace every field to the source, correct
   it, and explicitly approve it.
4. Only an approved case can produce the report or register output. Corrections feed a human-gated
   tuning workflow.

## Local setup

Prerequisites: Docker Desktop, Python 3.12, [uv](https://docs.astral.sh/uv/), Node 20, pnpm 9, Ollama,
and enough local resources for the configured models. The committed PoC path assumes an NVIDIA GPU;
see [Prerequisites](PREREQUISITES.md) for model-specific setup.

```powershell
Copy-Item .env.example .env
docker compose -f deploy/docker-compose.yml up -d db minio
Set-Location engine
uv sync --group dev
uv run python -m app.init_db
uv run uvicorn app.main:app --reload
```

In a second terminal:

```powershell
Set-Location ui
pnpm install --frozen-lockfile
pnpm dev
```

Open the URL printed by Vite. A workspace/tenant UUID is currently required; seed a demo workspace with
the scripts under `engine/scripts`, or obtain the UUID from an administrator. This manual identity step
is a known product gap, not the intended production onboarding experience.

## Verify a change

```powershell
Set-Location engine
uv run ruff check .
uv run black --check .
uv run mypy app
uv run pytest -q

Set-Location ..\ui
pnpm test
pnpm build
```

Database-backed tests require Docker. CI sets `REQUIRE_DB=1` so those tests cannot silently skip.

## Repository map

| Path | Purpose |
|---|---|
| `engine/app` | FastAPI API, pipeline, storage, rules, review and portal logic |
| `engine/tests` | Unit, integration, isolation and trust-gate tests |
| `engine/eval` | Evaluation data, scoring and tuning gates |
| `ui/src` | Reviewer application |
| `deploy` | Docker Compose, application image and Caddy edge config |
| `assets` | Starter taxonomy, policy and demo object-store files |
| `docs` | User, deployment, channel and readiness guides |

## Important constraints

- Never commit `.env`, customer source material, generated reports, or local databases.
- The default policy contains illustrative values; replace it with an approved tenant policy before a pilot.
- `APP_ENV=prod` rejects placeholder secrets, but production also requires authentication and the other
  launch gates listed in [Market readiness](docs/MARKET-READINESS.md).
- Do not present the current evaluation figures as customer accuracy claims; the label set is not yet
  independently produced.

## Contributors

See [CONTRIBUTORS.md](CONTRIBUTORS.md) for human ownership and AI-assistance attribution.
