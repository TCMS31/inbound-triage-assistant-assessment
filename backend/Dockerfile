# syntax=docker/dockerfile:1

# ---- build: resolve and install dependencies into a self-contained venv ----
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

# Dependency metadata first so the layer survives source-only changes.
COPY pyproject.toml ./
COPY src ./src

RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir .

# ---- runtime: no build tools, no source tree, no root ----
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    PORT=8787

RUN useradd --create-home --uid 10001 triage
WORKDIR /app

# Created (and owned) before the named volume is mounted over it, so the
# non-root runtime user can actually write the triage cache.
RUN mkdir -p /app/cache && chown triage:triage /app/cache

COPY --from=builder /opt/venv /opt/venv
# The message corpus and the writable cache directory.
COPY --chown=triage:triage data ./data

USER triage
EXPOSE 8787

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; \
sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8787/api/health', timeout=2).status == 200 else 1)"

CMD ["python", "-m", "triage_backend"]
