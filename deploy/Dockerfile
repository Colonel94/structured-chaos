# Engine image. Linux base so PaddleOCR + WeasyPrint (GTK/Pango) install cleanly —
# the whole reason we containerise instead of installing on the Windows host (§3).
FROM python:3.12-slim

# System libs: WeasyPrint (Pango/Cairo/GDK-Pixbuf), PaddleOCR/ffmpeg (libGL, glib), fonts (Arabic).
RUN apt-get update && apt-get install -y --no-install-recommends \
      libpango-1.0-0 libpangocairo-1.0-0 libcairo2 libgdk-pixbuf-2.0-0 libffi-dev \
      libgl1 libglib2.0-0 ffmpeg \
      fonts-noto fonts-noto-core fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

# uv for fast, lockfile-based installs.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app
COPY engine/pyproject.toml ./engine/pyproject.toml

# Install core + the container-only heavy groups (ocr, pdf, report, embed, vad).
RUN cd engine && uv pip install --system \
      --group ocr --group pdf --group report --group embed --group vad \
      -r <(uv pip compile pyproject.toml 2>/dev/null || true) || \
    (cd engine && uv sync --group ocr --group pdf --group report --group embed --group vad)

COPY engine/ ./engine/
COPY scripts/ ./scripts/
WORKDIR /app/engine
ENV PYTHONPATH=/app/engine

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
