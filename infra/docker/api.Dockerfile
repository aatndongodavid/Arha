# Arha API and worker image. Multi-stage, non root, pinned dependencies from uv.lock.
FROM python:3.15-slim-bookworm AS build
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /usr/local/bin/uv
WORKDIR /app/apps/api
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY apps/api/pyproject.toml apps/api/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY apps/api/ ./
RUN uv sync --frozen --no-dev

FROM python:3.15-slim-bookworm
# WeasyPrint needs Pango; fonts for receipts and invoices.
RUN apt-get update && apt-get install -y --no-install-recommends libpango-1.0-0 libpangoft2-1.0-0 fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/* && useradd --uid 10001 --create-home arha
WORKDIR /app
COPY --from=build --chown=arha:arha /app/apps/api /app/apps/api
COPY --chown=arha:arha config /app/config
COPY --chown=arha:arha packages/i18n/api /app/packages/i18n/api
COPY --chown=arha:arha apps/forms/dist/index.html /app/apps/forms/dist/index.html
ENV PATH="/app/apps/api/.venv/bin:$PATH" PYTHONUNBUFFERED=1 CONFIG_DIR=/app/config
USER arha
WORKDIR /app/apps/api
EXPOSE 8000
CMD ["gunicorn", "arha.main:app", "-k", "uvicorn.workers.UvicornWorker", "-w", "4", "-b", "0.0.0.0:8000", "--access-logfile", "-", "--graceful-timeout", "30"]
