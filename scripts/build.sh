#!/bin/bash

###############################################################################
# ReqFlow Docker Build Script
#
# Description:
#   Build the Docker Compose stack with real version/commit/build-time
#   metadata stamped into the backend image (exposed via GET /api/v1/version/).
#   Without these build args populated, the image defaults to "unknown".
#
#   Computed automatically:
#     APP_VERSION     <- root VERSION file  (e.g. 0.2.0)
#     GIT_COMMIT_SHA  <- git rev-parse HEAD
#     BUILD_TIME      <- current UTC time   (ISO-8601, e.g. 2026-07-18T21:00:00Z)
#
# Usage:
#   ./scripts/build.sh                 # Build all services
#   ./scripts/build.sh backend         # Build a specific service (args forwarded)
#
# Requirements:
#   - docker/docker-compose installed
#   - git available (repository checkout)
#   - root VERSION file present
#
# Author: ReqFlow DevOps
# Last Updated: 2026-07-18
###############################################################################

set -euo pipefail

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

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

  if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    log_error "docker-compose is not installed or not in PATH"
    exit 1
  fi

  if [ ! -f "${PROJECT_ROOT}/VERSION" ]; then
    log_error "VERSION file not found at ${PROJECT_ROOT}"
    exit 1
  fi
}

main() {
  check_prerequisites

  cd "$PROJECT_ROOT"

  APP_VERSION="$(cat VERSION | tr -d '[:space:]')"
  GIT_COMMIT_SHA="$(git rev-parse HEAD 2>/dev/null || echo unknown)"
  BUILD_TIME="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

  export APP_VERSION GIT_COMMIT_SHA BUILD_TIME

  log_info "APP_VERSION=${APP_VERSION}"
  log_info "GIT_COMMIT_SHA=${GIT_COMMIT_SHA}"
  log_info "BUILD_TIME=${BUILD_TIME}"

  # `-f deploy/docker-compose.yml` ONLY (no override.yml) on purpose (same as
  # scripts/backup.sh and the Makefile's TEST_COMPOSE): the override merges
  # the frontend's *development* target instead of the release image this
  # script stamps metadata into, and legacy `docker-compose` v1 cannot parse
  # its `!override` merge tag at all (needs Compose >= 2.24.4). Deployment
  # compose files live under deploy/, not the repo root — `--project-directory
  # .` pins .env lookup and relative bind-mount paths (./backend, ./docker/...)
  # to the repo root instead of deploy/'s own directory.
  if docker-compose --version &> /dev/null; then
    docker-compose -f deploy/docker-compose.yml --project-directory . build "$@"
  else
    docker compose -f deploy/docker-compose.yml --project-directory . build "$@"
  fi

  log_info "Build completed"
}

main "$@"
