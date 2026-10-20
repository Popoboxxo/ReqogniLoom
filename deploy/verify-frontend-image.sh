#!/usr/bin/env bash
# deploy/verify-frontend-image.sh
#
# Guard for #1436: when BLUEPENCIL_ENABLED=1, the running frontend must be a
# LOCALLY BUILT image that carries the re-vendored Bluepencil layer. The base
# deploy/docker-compose.yml pins the frontend as the GHCR registry image; an
# overlay that only overrides ports/limits/build: still starts that image — the
# stack looks healthy while the SPA serves the repo-default layer.
#
# Usage (from the repository root, with the stack up):
#   bash deploy/verify-frontend-image.sh
#
# Environment:
#   BLUEPENCIL_ENABLED             read from the shell, else from ./.env
#   COMPOSE_PROJECT_NAME           container prefix (default: repo dir, lowercased)
#   BLUEPENCIL_FRONTEND_CONTAINER  explicit container name overrides the default
#   BLUEPENCIL_IMAGE               optional expected local image; its served
#                                  layer must match the running container's
#
# Exit codes: 0 = OK or skipped (BLUEPENCIL_ENABLED != 1), 1 = mismatch.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVED_PATH="/usr/share/nginx/html/bluepencil/latest/latest.json"
REPO_LAYER="$ROOT_DIR/frontend/public/bluepencil/latest/latest.json"

# Compose reads .env, not the shell; honour the file when the variable was not
# exported into this process.
_enabled="${BLUEPENCIL_ENABLED:-}"
if [ -z "$_enabled" ] && [ -f "$ROOT_DIR/.env" ]; then
  _enabled="$(
    sed -n 's/^[[:space:]]*BLUEPENCIL_ENABLED[[:space:]]*=[[:space:]]*//p' \
      "$ROOT_DIR/.env" | tail -n 1 | tr -d ' "\r'
  )"
fi
if [ "${_enabled:-0}" != "1" ]; then
  echo "SKIP: BLUEPENCIL_ENABLED=${_enabled:-0} (the Bluepencil loader is not armed)."
  exit 0
fi

_project="${COMPOSE_PROJECT_NAME:-$(basename "$ROOT_DIR" | tr '[:upper:]' '[:lower:]')}"
_container="${BLUEPENCIL_FRONTEND_CONTAINER:-${_project}-frontend-1}"

if ! docker inspect "$_container" >/dev/null 2>&1; then
  echo "FAIL: frontend container '$_container' not found."
  echo "      Set COMPOSE_PROJECT_NAME or BLUEPENCIL_FRONTEND_CONTAINER."
  exit 1
fi

_image="$(docker inspect -f '{{.Config.Image}}' "$_container")"
_served="$(docker exec "$_container" cat "$SERVED_PATH" 2>/dev/null || true)"

echo "container: $_container"
echo "image:     $_image"
if [ -n "$_served" ]; then
  echo "served:    $_served"
fi

if [ -z "$_served" ]; then
  echo "FAIL: '$_container' serves no $SERVED_PATH — the image does not bundle the Bluepencil layer."
  exit 1
fi

# A published image carries the layer that was baked at publish time (the repo
# default), never a locally re-vendored one. This is the #1436 failure mode.
case "$_image" in
  ghcr.io/* | docker.io/* | registry-1.docker.io/*)
    cat <<EOF
FAIL: BLUEPENCIL_ENABLED=1 but the running frontend is the registry image '$_image'.
      A published image serves the layer baked at publish time (the repo default),
      not the locally re-vendored one. Override 'image:' in your overlay (#1436):
        services:
          frontend:
            image: reqogniloom-frontend:bluepencil-\${REQOGNILOOM_VERSION}
            pull_policy: build
            ports: !override
              - "5173:8080"
      See deploy/README.md "Overlays that replace the frontend image (#1436)".
EOF
    exit 1
    ;;
esac

if [ -n "${BLUEPENCIL_IMAGE:-}" ]; then
  if [ "$_image" != "$BLUEPENCIL_IMAGE" ]; then
    echo "FAIL: BLUEPENCIL_IMAGE='$BLUEPENCIL_IMAGE' but the running frontend uses '$_image'."
    exit 1
  fi
  _expected="$(docker run --rm --entrypoint cat "$BLUEPENCIL_IMAGE" "$SERVED_PATH" 2>/dev/null || true)"
  if [ -z "$_expected" ]; then
    echo "FAIL: BLUEPENCIL_IMAGE='$BLUEPENCIL_IMAGE' has no $SERVED_PATH."
    exit 1
  fi
  if [ "$_expected" != "$_served" ]; then
    echo "FAIL: the served layer differs from BLUEPENCIL_IMAGE's layer."
    printf '  served:   %s\n' "$_served"
    printf '  expected: %s\n' "$_expected"
    exit 1
  fi
fi

if [ -f "$REPO_LAYER" ] && [ "$(cat "$REPO_LAYER")" = "$_served" ]; then
  echo "WARN: the running image serves the REPO-DEFAULT Bluepencil layer, not a re-vendored one."
  echo "      If you rebuilt with a newer layer, the overlay is still using an image that"
  echo "      predates the re-vendor. Rebuild the frontend image and set 'image:' in the overlay."
  exit 0
fi

echo "OK: the running frontend is a locally built image serving the Bluepencil layer."
