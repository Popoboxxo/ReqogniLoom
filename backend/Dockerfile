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

# Install build-time system dependencies.
# `git` is required only by the temporary `django-celery-beat @ git+https://...`
# VCS pin in requirements.txt (see the comment there): python:3.12-slim ships no
# git, so pip aborts with "Cannot find command 'git' - do you have 'git'
# installed and in your PATH?". Build-stage only — the runtime stage copies just
# /install, so no git binary lands in the shipped image. Remove this again when
# django-celery-beat goes back to a PyPI pin.
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    git \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies to a custom prefix
COPY requirements.txt .
# CPU-only torch first: sentence-transformers pulls in `torch`, whose default
# PyPI wheel bundles the full NVIDIA CUDA runtime as separate `nvidia-*`
# packages (several GB) even though this deployment (ADR-08, self-hosted,
# no GPU) never uses CUDA. Installing the CPU-only build from PyTorch's own
# index FIRST means the subsequent requirements.txt install finds torch
# already satisfied and never pulls the CUDA variant. Without this, the
# runtime stage below can exceed several GB of otherwise-dead weight.
RUN pip install --no-cache-dir --prefix=/install torch --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# NOTE: the sentence-transformers model pre-download (REQ-L2-VS-004) does NOT
# happen in this stage. `--prefix=/install` above installs packages under
# /install/lib/python3.X/site-packages, which is not on THIS stage's
# sys.path (it only becomes importable once copied to /usr/local in the
# runtime stage below) -- `import sentence_transformers` here would raise
# ModuleNotFoundError. See the runtime stage for the actual download step.

# ─────────────────────────────────────────────────────────
# Stage 2: runtime — minimal image with only runtime deps
# ─────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

# Build metadata stamping — exposed via GET /api/v1/version/ (reqogniloom/version.py).
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
# procps provides pgrep, used by the celery-beat healthcheck (#171) to detect
# a crashed/restart-looping beat process (celery-beat has no worker to `inspect ping`).
# `apt-get upgrade` patches OS packages already present in the python:3.12-slim
# base image (not just the ones installed below) — the base tag is floating,
# so packages like libssl can carry CVEs Debian's repo has already fixed by
# the time this image is built. Trivy's exit-code:1 gate in docker-publish.yml
# found this class of issue in the frontend image on 2026-08-30.
RUN apt-get update && apt-get upgrade -y && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    procps \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from builder stage
COPY --from=builder /install /usr/local

# The builder stage's two independent `pip install --prefix=/install ...`
# invocations (torch, then -r requirements.txt) don't see each other's
# already-installed packages under that prefix, so each can pull its own
# copy of setuptools as a transitive build dependency. That leaves TWO
# `setuptools-*.dist-info` directories in /install — confirmed via a
# temporary diagnostic build (run 33370133189): a stray
# `setuptools-78.1.0.dist-info` (with its own vendored wheel 0.45.1 /
# jaraco.context 5.3.0, three HIGH CVEs) sitting right next to whatever
# newer version a plain `pip install --upgrade`/`--force-reinstall` adds.
# pip's uninstall step only removes the ONE distribution it resolves as
# "existing" (found existing installation: <newer version> in that
# diagnostic run) and never touches the orphaned older one, so Trivy kept
# flagging the same three CVEs on the v1.8.0-beta.4 image and on two
# follow-up scans (runs 33366112907, 33369068014) despite the upgrade
# reporting success both times. Wiping the whole `setuptools/` package dir
# and any `setuptools-*.dist-info` metadata before installing sidesteps
# pip's uninstall/RECORD matching entirely, so no duplicate can survive
# regardless of how many prior copies exist.
#
# The base image's own pip (25.0.1, untouched by any of the above since
# nothing here ever upgrades pip itself) carries 5 more CVEs — one
# (CVE-2026-8643) HIGH enough to still fail Trivy's exit-code:1 gate even
# after the setuptools cleanup above cleared every other finding (confirmed
# via CI run 33371207796). Upgrade it in the same layer.
#
# requirements.txt doesn't pin setuptools, so exactly which stale transitive
# version leaks into /install from the builder stage isn't stable across
# builds — the rm -rf above cleared a 78.1.0 leftover in run 33371207796,
# but the very next run (33372024549) turned up a *different* stray version,
# 70.3.0, that the old `-iname 'setuptools-*.dist-info'` glob (dist-info
# only, maxdepth implied by the literal path) didn't catch — most likely a
# legacy `.egg-info` install or a copy nested one level down rather than
# directly under site-packages. Widened to a recursive `-iname 'setuptools*'`
# sweep so the format/location of the leftover doesn't matter. Also caught a
# genuine (non-duplicate) HIGH CVE in msgpack in that same scan — upgraded
# alongside since it's in the same transitive, unpinned boat.
RUN pip install --no-cache-dir --upgrade "pip>=26.1.2" \
    && find /usr/local/lib/python3.*/site-packages -iname 'setuptools*' -exec rm -rf {} + \
    && pip install --no-cache-dir "setuptools>=78.1.1" "msgpack>=1.2.1"

# Copy application code
COPY . .

# Create non-root user for security (REQ-059).
# #439: `adduser --system` without `--home` leaves HOME at Debian's system-user
# default, `/nonexistent` — gunicorn's control server derives its socket path
# from $HOME and fails to bind there ("Control server error: [Errno 13]
# Permission denied: '/nonexistent'") on every startup. `--home` alone does
# not create the directory for a --system account either, so it is made and
# chown'd explicitly; ENV HOME backs up any tool that reads the env var
# directly instead of doing a passwd lookup.
RUN addgroup --system app \
    && adduser --system --ingroup app --home /home/app --shell /usr/sbin/nologin app \
    && mkdir -p /home/app && chown app:app /home/app
ENV HOME=/home/app

# Pre-download sentence-transformers model (REQ-L2-VS-004) to avoid slow
# first-request download at runtime and to keep the image self-contained (no
# HuggingFace network access needed on first real embed call in production).
#
# This MUST run here -- in the runtime stage, after `COPY --from=builder
# /install /usr/local` above made sentence-transformers importable, and
# BEFORE the `USER app` switch further down -- and with an explicit HF_HOME.
# Without HF_HOME, huggingface_hub caches under `$HOME/.cache/huggingface`;
# running the download as root without it would put the cache under
# /root/.cache, a path the non-root runtime user (HOME=/home/app) can
# neither read nor reuse, causing a silent re-download from HuggingFace on
# the first real request in production -- defeating the point of baking the
# model in. /home/app already exists (created above), so the download is
# run as root into HF_HOME and then handed off to the app user via chown.
ENV HF_HOME=/home/app/.cache/huggingface
RUN mkdir -p "${HF_HOME}" \
    && python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')" \
    && chown -R app:app "${HF_HOME}"

# Codeberg Gesamttest 2026-08-29 F-1: even with the model files fully cached
# above, huggingface_hub still contacts huggingface.co on every process
# preload/first-use to *revalidate* the local cache (ETag HEAD/GET
# round-trips) -- ~15 HTTP calls / ~3.5s wasted per cold worker, since this
# image already bakes the exact pinned model weights in and never expects
# them to change out from under it. HF_HUB_OFFLINE=1 makes huggingface_hub
# skip that revalidation entirely and read straight from HF_HOME. Set here
# (not just as a docker-compose env var) so it applies to every process that
# runs from this image, including one-off `docker run`/CI invocations that
# don't go through docker-compose.yml. The HF_HUB_ETAG_TIMEOUT=5 default set
# in llm_adapter/apps.py remains as a safety net for the case this variable
# is ever unset/overridden at runtime.
ENV HF_HUB_OFFLINE=1

# Ensure working directory is owned by app user
RUN chown -R app:app /app

# DR backups (admin_ops, REQ-L1-046) are written to <BASE_DIR>/backups = /app/backups.
# Pre-create the directory owned by the non-root app user so:
#   * the runtime image can write here without a permission error, and
#   * a Docker named volume mounted at /app/backups inherits app:app ownership
#     on first initialisation (Docker seeds a fresh volume from the image path),
#     which also survives the dev bind-mount of ./backend over /app.
RUN mkdir -p /app/backups && chown app:app /app/backups

# Collect static files (required for production deployment).
# Settings fail fast when secrets are unset (REQ-115/REQ-081); collectstatic
# only needs importable settings, so build-only dummy values are injected for
# this single step. They are not baked into the image environment.
RUN SECRET_KEY=build-only-dummy \
    AUTH_JWT_SECRET=build-only-dummy \
    FIELD_ENCRYPTION_KEY=build-only-dummy \
    DB_PASSWORD=build-only-dummy \
    DB_APP_PASSWORD=build-only-dummy \
    REDIS_PASSWORD=build-only-dummy \
    python manage.py collectstatic --noinput

# TEMP DIAGNOSTIC — remove before merge. Trivy keeps finding setuptools
# 70.3.0 and msgpack 1.1.2 even after upgrading both explicitly earlier in
# this stage; a recursive `-iname 'setuptools*' -exec rm -rf` under
# site-packages didn't help either, so the leftover is presumably outside
# site-packages entirely. Sweep the WHOLE filesystem for the exact stale
# strings/paths right at the point Trivy actually scans (end of build).
RUN echo "=== full-fs setuptools/msgpack sweep ===" \
    ; find / -xdev \( -iname "*setuptools*" -o -iname "*msgpack*" \) 2>/dev/null | grep -v "^/proc" \
    ; echo "=== grep for version strings in file content ===" \
    ; grep -rl "70\.3\.0" /usr/local/lib/python3.12/site-packages 2>/dev/null | head -20 \
    ; echo "=== end sweep ===" \
    ; true

EXPOSE 8000

# Run as non-root user
USER app

# Production: Gunicorn managing uvicorn ASGI workers (REQ-044).
# ASGI is required so the async MCP SSE transport streams without blocking a
# sync worker per connected client. Multi-worker deployment (4 workers).
# SA-49: Added timeout flags to prevent hung requests and allow graceful shutdown:
#   --timeout: hard limit on a single request (30s)
#   --graceful-timeout: soft limit before SIGKILL during shutdown (30s)
#   --max-requests: recycle workers after N requests to prevent memory leaks (1000)
#   --max-requests-jitter: randomize to avoid thundering herd (50)
CMD ["gunicorn", "reqogniloom.asgi:application", "-k", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8000", "--workers", "4", "--timeout", "30", "--graceful-timeout", "30", "--max-requests", "1000", "--max-requests-jitter", "50"]
