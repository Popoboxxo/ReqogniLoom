#!/bin/bash
# Build Backend Docker Image with Automatic Version Stamping
#
# Usage:
#   ./backend/scripts/build.sh [TAG] [EXTRA_DOCKER_ARGS]
#
# If TAG is not provided, defaults to:
#   - Local dev: use git commit SHA (7-char short form)
#   - CI: use version tag (from VERSION file)
#
# This script extracts the Authoritative Source of Truth:
#   - APP_VERSION: from root ./VERSION file
#   - GIT_COMMIT_SHA: from git rev-parse HEAD (current checkout)
#   - BUILD_TIME: current UTC timestamp
#
# These are passed as build-args to docker build, ensuring consistency between:
#   - OCI image labels (org.opencontainers.image.revision, etc.)
#   - Runtime environment variables (APP_VERSION, GIT_COMMIT_SHA, BUILD_TIME)
#   - GET /api/v1/version/ endpoint response
#
# This eliminates the drift where OCI labels and runtime env-vars can diverge.

set -euo pipefail

# Determine project root (script is at ./backend/scripts/build.sh)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
BACKEND_DIR="$PROJECT_ROOT/backend"

# Extract build metadata from source of truth
if [[ ! -f "$PROJECT_ROOT/VERSION" ]]; then
  echo "ERROR: VERSION file not found at $PROJECT_ROOT/VERSION" >&2
  exit 1
fi

APP_VERSION=$(cat "$PROJECT_ROOT/VERSION" | tr -d '[:space:]')
if [[ -z "$APP_VERSION" ]]; then
  echo "ERROR: VERSION file is empty" >&2
  exit 1
fi

if ! command -v git &> /dev/null; then
  echo "ERROR: git not found in PATH" >&2
  exit 1
fi

# Get current commit SHA (full 40-char)
GIT_COMMIT_SHA=$(cd "$PROJECT_ROOT" && git rev-parse HEAD)
BUILD_TIME=$(date -u +%Y-%m-%dT%H:%M:%SZ)

# Default tag: use version or commit short-SHA
TAG="${1:-reqogniloom-backend:${APP_VERSION}}"
EXTRA_ARGS="${2:-}"

# Docker buildx or plain docker build
DOCKER_CMD="docker"
if command -v docker &> /dev/null; then
  DOCKER_CMD="docker"
fi

echo "[build.sh] Building Docker image: $TAG"
echo "[build.sh]   APP_VERSION=$APP_VERSION"
echo "[build.sh]   GIT_COMMIT_SHA=$GIT_COMMIT_SHA (${GIT_COMMIT_SHA:0:7})"
echo "[build.sh]   BUILD_TIME=$BUILD_TIME"
echo ""

# Build with explicit version stamping
$DOCKER_CMD build \
  --build-arg "APP_VERSION=$APP_VERSION" \
  --build-arg "GIT_COMMIT_SHA=$GIT_COMMIT_SHA" \
  --build-arg "BUILD_TIME=$BUILD_TIME" \
  -t "$TAG" \
  $EXTRA_ARGS \
  "$BACKEND_DIR"

echo "[build.sh] Build complete: $TAG"
echo "[build.sh] Verify: docker run --rm $TAG curl http://localhost:8000/api/v1/version/"
