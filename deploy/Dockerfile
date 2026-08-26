# Build the reviewer SPA once and serve it from the API image. Keeping one origin is deliberate:
# secure session cookies and CSRF protection do not depend on cross-origin exceptions.
FROM node:22-slim AS ui-build
WORKDIR /ui
RUN corepack enable
COPY ui/package.json ui/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY ui/ ./
RUN pnpm build

# Engine image. Linux base so PaddleOCR + WeasyPrint (GTK/Pango) install cleanly —
# the whole reason we containerise instead of installing on the Windows host (§3).
FROM python:3.12-slim

# System libs:
#   WeasyPrint    -> Pango/Cairo/GDK-Pixbuf
#   PaddleOCR     -> libGL, glib, libgomp (OpenMP runtime for paddlepaddle)
#   ffmpeg        -> audio decode (opus/m4a/ogg) on the ASR path
#   fonts-noto*   -> Arabic + Latin glyphs for RTL PDF rendering (spike 3 / register report)
RUN apt-get update && apt-get install -y --no-install-recommends \
      libpango-1.0-0 libpangocairo-1.0-0 libcairo2 libgdk-pixbuf-2.0-0 libffi-dev \
      libgl1 libglib2.0-0 libgomp1 ffmpeg \
      fonts-noto fonts-noto-core fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

# uv for fast, lockfile-based installs.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app
# Copy source BEFORE install so `uv pip install .` can build the project wheel
# (hatchling needs app/ present) — and so container-only heavy groups resolve.
COPY engine/ ./engine/
COPY scripts/ ./scripts/
COPY --from=ui-build /ui/dist /app/ui-dist

# Install the project (core runtime deps) + the container-only heavy groups, into the
# system interpreter. sh-safe: no bash process-substitution (the old `<(...)` broke here).
RUN cd engine && uv pip install --system \
      --group embed --group ocr --group pdf --group report --group vad \
      .

RUN groupadd --system --gid 10001 intake \
    && useradd --system --uid 10001 --gid intake --home-dir /app --shell /usr/sbin/nologin intake \
    && chown -R intake:intake /app

USER intake

WORKDIR /app/engine
ENV PYTHONPATH=/app/engine
ENV UI_DIST_DIR=/app/ui-dist

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
