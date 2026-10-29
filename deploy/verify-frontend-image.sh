#!/usr/bin/env bash
# deploy/verify-frontend-image.sh
#
# Guard for #1436: when BLUEPENCIL_ENABLED=1, the running frontend must be a
# LOCALLY BUILT image that carries the re-vendored Bluepencil layer. The base
# deploy/docker-compose.yml pins the frontend as the GHCR registry image; an
# overlay that only overrides ports/limits/build: still starts that image — the
# stack looks healthy while the SPA serves a layer nobody chose.
#
# Plan D / D1.2 adds a second half to the check: the layer itself is delivered by
# the read-only mount declared in deploy/docker-compose.bluepencil.yml and
# materialised by deploy/bluepencil/fetch-layer.sh, and its provenance is the pin
# in deploy/bluepencil/layer.lock.json. The served manifest is therefore compared
# against the LOCK (version + element digest) rather than against a repository
# file, which no longer exists.
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
# Plan D / D1.2: the layer is no longer repository content. Its provenance is
# the pin in deploy/bluepencil/layer.lock.json, so that — not a file under
# frontend/public/ — is what a served manifest is compared against.
LAYER_LOCK="$ROOT_DIR/deploy/bluepencil/layer.lock.json"

# First `"<key>": "<value>"` in a JSON file. The lock and the manifest are
# two-key documents written by this repository, so a JSON toolchain would be a
# dependency without a safety gain; an absent key yields an empty string, which
# every caller below treats as "unparseable" rather than as a match.
_json_value() {
  grep -o "\"$1\"[[:space:]]*:[[:space:]]*\"[^\"]*\"" "$2" \
    | head -n 1 \
    | sed -e 's/^"[^"]*"[[:space:]]*:[[:space:]]*"//' -e 's/"$//'
}

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

# Does the container serve the LAYER THE LOCK PINS (version + element digest)?
# Under D1.2 the bytes come from deploy/docker-compose.bluepencil.yml's read-only
# mount, materialised by deploy/bluepencil/fetch-layer.sh — so a mismatch means
# the delivery chain is not the verified one: either the image still carries a
# pre-D1.2 baked layer, or BLUEPENCIL_LAYER_DIR points at a directory that was
# never fetched (or was fetched against a different lock).
if [ -f "$LAYER_LOCK" ]; then
  _lock_version="$(_json_value version "$LAYER_LOCK")"
  _lock_element_sha="$(_json_value 'bluepencil\.element\.min\.js' "$LAYER_LOCK")"
  _served_version="$(_json_value version "$SERVED_PATH" 2>/dev/null || true)"
  _served_sha="$(_json_value sha256 "$SERVED_PATH" 2>/dev/null || true)"

  if [ -n "$_lock_version" ] && [ "$_served_version" = "$_lock_version" ] \
    && [ -n "$_lock_element_sha" ] && [ "$_served_sha" = "$_lock_element_sha" ]; then
    echo "OK: the frontend serves the layer pinned in deploy/bluepencil/layer.lock.json (v$_lock_version)."
    exit 0
  fi

  cat <<EOF
WARN: the served layer does not match deploy/bluepencil/layer.lock.json.
  served: version='${_served_version:-<none>}' sha256='${_served_sha:-<none>}'
  pinned: version='${_lock_version:-<none>}' sha256='${_lock_element_sha:-<none>}'
      The layer is delivered by a read-only mount, not by the image. Materialise it
      from the pin and restart the frontend:
        bash deploy/bluepencil/fetch-layer.sh --dest "\${BLUEPENCIL_LAYER_DIR:-deploy/bluepencil/layer}"
      If a NEWER upstream release is intended, bump deploy/bluepencil/layer.lock.json
      first (same commit), then fetch. Never hand-copy layer bytes.
EOF
  exit 0
fi

echo "OK: the running frontend is a locally built image serving the Bluepencil layer."
