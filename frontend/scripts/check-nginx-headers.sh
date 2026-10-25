#!/usr/bin/env bash
# Verify the security headers on every nginx response (plan D / D1.0, RB-D02).
#
# Why this exists: nginx drops ALL inherited `add_header` directives as soon as
# a location defines one of its own. The SPA document (`/index.html`), the
# static asset location and `/healthz` each define one, so they used to serve
# no CSP, no X-Frame-Options and no nosniff. This script is the executable
# definition of "fixed": it checks the document route, a deep-link route (SPA
# fallback), a real script asset and the health endpoint.
#
# It also enforces the CSP hardening from QR-S17:
#   * `frame-ancestors 'none'` must be present,
#   * `script-src` must not contain 'unsafe-inline' or 'unsafe-eval'.
#
# Usage: bash frontend/scripts/check-nginx-headers.sh <base-url>
# Exit:  0 = every checked response carries every header; 1 = a check failed.
#
# The CI job `nginx-headers-smoke` runs it against a throwaway nginx container
# and additionally proves the negative case (a snippet with 'unsafe-inline'
# must make the script exit 1).
set -euo pipefail

BASE_URL="${1:-}"
if [ -z "${BASE_URL}" ]; then
  echo "usage: $0 <base-url>" >&2
  exit 2
fi
BASE_URL="${BASE_URL%/}"

# Header needles are matched case-insensitively against the response headers.
# The CSP entry is checked separately (presence + directive content).
REQUIRED_HEADERS=(
  "content-security-policy"
  "x-frame-options: deny"
  "x-content-type-options: nosniff"
  "referrer-policy: strict-origin-when-cross-origin"
)

failures=0

fail() {
  printf 'FAIL %s: %s\n' "$1" "$2" >&2
  failures=$((failures + 1))
}

require_headers() {
  local label="$1"
  local headers="$2"
  local needle
  for needle in "${REQUIRED_HEADERS[@]}"; do
    if ! printf '%s\n' "${headers}" | grep -qi "^${needle}"; then
      fail "${label}" "missing header: ${needle%%:*}"
    fi
  done
}

check_csp() {
  local label="$1"
  local headers="$2"
  local csp csp_lower script_src

  # grep is case-insensitive; the value keeps its original casing.
  csp="$(printf '%s\n' "${headers}" \
    | grep -i '^content-security-policy:' \
    | head -n1 \
    | cut -d: -f2- || true)"

  if [ -z "${csp}" ]; then
    # A missing CSP was already reported by require_headers.
    return
  fi

  csp_lower="$(printf '%s' "${csp}" | tr '[:upper:]' '[:lower:]')"

  case "${csp_lower}" in
    *"frame-ancestors 'none'"*) ;;
    *) fail "${label}" "CSP is missing frame-ancestors 'none'" ;;
  esac

  script_src="$(printf '%s' "${csp_lower}" \
    | tr ';' '\n' \
    | grep -E '^[[:space:]]*script-src[[:space:]]' \
    | head -n1 || true)"

  if [ -z "${script_src}" ]; then
    fail "${label}" "CSP has no script-src directive"
    return
  fi
  case "${script_src}" in
    *"'unsafe-inline'"*) fail "${label}" "CSP script-src must not contain 'unsafe-inline'" ;;
  esac
  case "${script_src}" in
    *"'unsafe-eval'"*) fail "${label}" "CSP script-src must not contain 'unsafe-eval'" ;;
  esac
}

check_url() {
  local url="$1"
  local label="$2"
  local headers

  if ! headers="$(curl -sS -D - -o /dev/null "${url}")"; then
    fail "${label}" "request failed: ${url}"
    return
  fi

  # First line only; parameter expansion avoids a printf|head SIGPIPE under
  # `set -o pipefail`.
  local status_line status
  status_line="${headers%%$'\n'*}"
  status="$(printf '%s' "${status_line}" | awk '{print $2}')"
  case "${status:-}" in
    2*) ;;
    *) fail "${label}" "unexpected HTTP status: ${status:-<none>}"; return ;;
  esac

  require_headers "${label}" "${headers}"
  check_csp "${label}" "${headers}"
}

# 1. SPA document (server-level headers, no location add_header).
check_url "${BASE_URL}/" "/"
# 2. Deep link: served through the SPA fallback, a different location.
check_url "${BASE_URL}/requirements" "/requirements"
# 3. Health endpoint: has its own add_header (Content-Type).
check_url "${BASE_URL}/healthz" "/healthz"

# 4. A real script asset: the asset location has its own add_header and is the
#    one that lost the headers in the regression.
index_html="$(curl -sS "${BASE_URL}/" || true)"
asset="$(printf '%s' "${index_html}" \
  | grep -oE 'src="[^"]+\.js"' \
  | head -n1 \
  | sed -E 's/^src="//; s/"$//' || true)"

if [ -z "${asset}" ]; then
  fail "/" 'could not find a <script src="...js"> reference in index.html'
elif printf '%s' "${asset}" | grep -qE '^https?://'; then
  check_url "${asset}" "${asset}"
elif printf '%s' "${asset}" | grep -qE '^/'; then
  check_url "${BASE_URL}${asset}" "${asset}"
else
  check_url "${BASE_URL}/${asset}" "${asset}"
fi

if [ "${failures}" -ne 0 ]; then
  printf '%d header check(s) failed\n' "${failures}" >&2
  exit 1
fi

printf 'OK: security headers present on every checked response\n'
