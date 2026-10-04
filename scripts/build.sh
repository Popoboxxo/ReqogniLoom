#!/bin/bash

###############################################################################
# ReqogniLoom Docker Build Script
#
# Description:
#   Build the TWO release images (backend, frontend) locally with real
#   version/commit/build-time metadata stamped into the backend image
#   (exposed via GET /api/v1/version/). Without these build args populated,
#   the image defaults to "unknown".
#
#   Computed automatically:
#     APP_VERSION     <- root VERSION file  (e.g. 1.8.0-beta.18)
#     GIT_COMMIT_SHA  <- git rev-parse HEAD
#     BUILD_TIME      <- current UTC time   (ISO-8601, e.g. 2026-07-18T21:00:00Z)
#
# Why `docker build` and not `docker compose build`:
#   deploy/docker-compose.yml is the RELEASE manifest — it pins finished
#   GHCR `image:` references and carries NO `build:` sections. A
#   `docker compose ... build` therefore reports "No services to build" and
#   is a silent no-op. The real build definitions are the multi-stage
#   Dockerfiles in backend/ (default target) and frontend/ (target
#   `production`), so this script invokes `docker build` against those
#   contexts directly — exactly like CI does.
#
#   This script ONLY builds. Publishing to GHCR is NOT done here: on a
#   version tag push (vX.Y.Z) the GitHub Actions workflow
#   .github/workflows/docker-publish.yml builds, scans (Trivy), signs
#   (cosign) and pushes the same two images. Run before tagging, or use it
#   to reproduce a release image locally.
#
# Usage:
#   ./scripts/build.sh
#
# Requirements:
#   - docker installed and running
#   - git available (repository checkout)
#   - root VERSION file present
#
# Author: ReqogniLoom DevOps
# Last Updated: 2026-10-03
###############################################################################

set -euo pipefail

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

GHCR_REGISTRY="ghcr.io/popoboxxo"
BACKEND_IMAGE="reqogniloom-backend"
FRONTEND_IMAGE="reqogniloom-frontend"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m' # No Color

log_info() {
  echo -e "${GREEN}[INFO]${NC} $*"
}

log_error() {
  echo -e "${RED}[ERROR]${NC} $*" >&2
}

check_prerequisites() {
  if ! command -v docker &> /dev/null; then
    log_error "docker is not installed or not in PATH"
    exit 1
  fi

  if ! command -v git &> /dev/null; then
    log_error "git is not installed or not in PATH"
    exit 1
  fi

  if [ ! -f "${PROJECT_ROOT}/VERSION" ]; then
    log_error "VERSION file not found at ${PROJECT_ROOT}"
    exit 1
  fi

  if [ ! -f "${PROJECT_ROOT}/backend/Dockerfile" ]; then
    log_error "backend/Dockerfile not found at ${PROJECT_ROOT}"
    exit 1
  fi

  if [ ! -f "${PROJECT_ROOT}/frontend/Dockerfile" ]; then
    log_error "frontend/Dockerfile not found at ${PROJECT_ROOT}"
    exit 1
  fi
}

main() {
  check_prerequisites

  cd "$PROJECT_ROOT"

  APP_VERSION="$(tr -d '[:space:]' < VERSION)"
  # Documented invariant (issue #1145): CI independently enforces
  # image-SHA == tag-SHA before publishing. This script itself does NOT verify
  # that HEAD is the tag commit — run it at the tag commit.
  GIT_COMMIT_SHA="$(git rev-parse HEAD)"
  BUILD_TIME="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

  log_info "APP_VERSION=${APP_VERSION}"
  log_info "GIT_COMMIT_SHA=${GIT_COMMIT_SHA}"
  log_info "BUILD_TIME=${BUILD_TIME}"

  # Backend image — the Dockerfile declares ARG APP_VERSION/GIT_COMMIT_SHA/
  # BUILD_TIME and stamps them into the runtime image for GET /api/v1/version/.
  # Build args mirror .github/workflows/docker-publish.yml exactly (the CI
  # frontend build passes no build args, so neither do we).
  log_info "Building backend image: ${GHCR_REGISTRY}/${BACKEND_IMAGE}:${APP_VERSION}"
  docker build \
    --tag "${GHCR_REGISTRY}/${BACKEND_IMAGE}:${APP_VERSION}" \
    --build-arg "APP_VERSION=${APP_VERSION}" \
    --build-arg "GIT_COMMIT_SHA=${GIT_COMMIT_SHA}" \
    --build-arg "BUILD_TIME=${BUILD_TIME}" \
    backend/

  # Frontend image — the release image is the `production` stage (nginx);
  # the Dockerfile's default final stage is not the release target.
  log_info "Building frontend image: ${GHCR_REGISTRY}/${FRONTEND_IMAGE}:${APP_VERSION}"
  docker build \
    --target production \
    --tag "${GHCR_REGISTRY}/${FRONTEND_IMAGE}:${APP_VERSION}" \
    frontend/

  log_info "Build completed"
  log_info "Publishing to GHCR is handled by .github/workflows/docker-publish.yml on version tag push."
}

main
