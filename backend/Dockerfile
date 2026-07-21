# Backend Dockerfile — ARCH-L1 Django Backend
# ADR-08: Self-Hosted via Docker Compose (no Kubernetes in v1)
# REQ-061: Multi-stage build to reduce runtime image size by removing build dependencies

# ─────────────────────────────────────────────────────────
# Stage 1: builder — install dependencies (with build tools)
# ─────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /app

# Prevent interactive prompts during package installation
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install build-time system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies to a custom prefix
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ─────────────────────────────────────────────────────────
# Stage 2: runtime — minimal image with only runtime deps
# ─────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

# Build metadata stamping — exposed via GET /api/v1/version/ (reqflow/version.py).
# A runtime image built from this Dockerfile ships no repo root / .git directory,
# so these build args are the authoritative source of the deployed
# version/commit/build time. Stamp them at build time, e.g.:
#   docker build \
#     --build-arg APP_VERSION=$(cat VERSION) \
#     --build-arg GIT_COMMIT_SHA=$(git rev-parse HEAD) \
#     --build-arg BUILD_TIME=$(date -u +%Y-%m-%dT%H:%M:%SZ) \
#     -t reqflow-backend .
ARG APP_VERSION=unknown
ARG GIT_COMMIT_SHA=unknown
ARG BUILD_TIME=
ENV APP_VERSION=${APP_VERSION}
ENV GIT_COMMIT_SHA=${GIT_COMMIT_SHA}
ENV BUILD_TIME=${BUILD_TIME}

WORKDIR /app

# Prevent interactive prompts during package installation
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Codeberg #99: pytest run as the non-root "app" user (below) cannot always
# create /app/.pytest_cache/... (e.g. read-only/foreign-UID container
# filesystems in some orchestrators). The cache buys nothing across ephemeral
# containers anyway, so disable the cache provider for any pytest invocation
# inside this image rather than chasing filesystem permissions. Host-side
# `pytest` runs (outside Docker) are unaffected, since this only applies
# within this container's environment.
ENV PYTEST_ADDOPTS="-p no:cacheprovider"

# Install runtime-only system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from builder stage
COPY --from=builder /install /usr/local

# Copy application code
COPY . .

# Create non-root user for security (REQ-059)
RUN addgroup --system app && adduser --system --ingroup app app

# Ensure working directory is owned by app user
RUN chown -R app:app /app

# Collect static files (required for production deployment).
# Settings fail fast when secrets are unset (REQ-115/REQ-081); collectstatic
# only needs importable settings, so build-only dummy values are injected for
# this single step. They are not baked into the image environment.
RUN SECRET_KEY=build-only-dummy \
    AUTH_JWT_SECRET=build-only-dummy \
    FIELD_ENCRYPTION_KEY=build-only-dummy \
    python manage.py collectstatic --noinput

EXPOSE 8000

# Run as non-root user
USER app

# Production: Gunicorn managing uvicorn ASGI workers (REQ-044).
# ASGI is required so the async MCP SSE transport streams without blocking a
# sync worker per connected client. Multi-worker deployment (4 workers).
CMD ["gunicorn", "reqflow.asgi:application", "-k", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8000", "--workers", "4"]
