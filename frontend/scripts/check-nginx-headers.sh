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
# Usage: bash frontend/scripts/check-nginx-headers.sh [--bluepencil] <base-url>
# Exit:  0 = every checked response carries every header; 1 = a check failed;
#        2 = usage error.
#
# `--bluepencil` additionally asserts the layer delivery contract from plan D /
# D1.2 (RB-D04, RB-D05) on the same server:
#   * `/bluepencil/latest/latest.json` answers 2xx with the security headers AND
#     `Cache-Control: no-cache` (never `immutable` — a pinned layer file name is
#     stable, so an immutable answer would freeze browsers on old bytes), and
#   * `/bluepencil/latest/missing.json` answers 404 — NOT the SPA document with
#     status 200. A 200 here means `location ^~ /bluepencil/latest/` is missing or
#     lost its `try_files $uri =404`, and the layer loader would parse index.html
#     as JavaScript.
# The flag is opt-in: without it the script checks exactly what it checked
# before, and the docroot does not have to contain a layer.
#
# The CI job `nginx-headers-smoke` runs it against a throwaway nginx container
# and additionally proves the negative case (a snippet with 'unsafe-inline'
# must make the script exit 1).
set -euo pipefail

bluepencil=0
base_arg=""

while [ "$#" -gt 0 ]; do
  case "$1" in
    --bluepencil)
      bluepencil=1
      shift
      ;;
    -h | --help)
      # The header comment block is the manual.
      awk 'NR > 1 && /^#/ { sub(/^# ?/, ""); print; next } NR > 1 { exit }' "${BASH_SOURCE[0]}"
      exit 0
      ;;
    -*)
      printf 'usage: %s [--bluepencil] <base-url>\n' "$0" >&2
      exit 2
      ;;
    *)
      if [ -n "${base_arg}" ]; then
        printf 'usage: %s [--bluepencil] <base-url>\n' "$0" >&2
        exit 2
      fi
      base_arg="$1"
      shift
      ;;
  esac
done

BASE_URL="${base_arg}"
if [ -z "${BASE_URL}" ]; then
  echo "usage: $0 [--bluepencil] <base-url>" >&2
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

# 5. The bluepencil layer location (plan D / D1.2). Opt-in via --bluepencil, so
#    the D1.0 smoke path and its docroot stay unchanged.
check_bluepencil() {
  local label="/bluepencil/latest/latest.json"
  local url="${BASE_URL}${label}"
  local headers status cache_control

  if ! headers="$(curl -sS -D - -o /dev/null "${url}")"; then
    fail "${label}" "request failed: ${url}"
    return
  fi

  status="${headers%%$'\n'*}"
  status="$(printf '%s' "${status}" | awk '{print $2}')"
  case "${status:-}" in
    2*) ;;
    *)
      fail "${label}" "unexpected HTTP status: ${status:-<none>} (is the layer fetched and mounted?)"
      return
      ;;
  esac

  require_headers "${label}" "${headers}"
  check_csp "${label}" "${headers}"

  cache_control="$(grep -i '^cache-control:' <<<"${headers}" | head -n1 || true)"
  if [ -z "${cache_control}" ]; then
    fail "${label}" "missing Cache-Control — the layer must not be inheriting the immutable asset policy"
  else
    case "$(printf '%s' "${cache_control}" | tr '[:upper:]' '[:lower:]')" in
      *immutable*)
        fail "${label}" "Cache-Control contains 'immutable' — a layer update would never reach an existing browser"
        ;;
      *no-cache* | *no-store*) ;;
      *) fail "${label}" "Cache-Control is neither no-cache nor no-store: ${cache_control#*: }" ;;
    esac
  fi
}

# A missing layer asset must 404, not fall back to index.html. `curl -w` keeps
# the status even though the body is discarded; a network error yields 000 and
# fails the check like any other wrong status.
check_bluepencil_missing() {
  local label="/bluepencil/latest/missing.json"
  local status
  status="$(curl -sS -o /dev/null -w '%{http_code}' "${BASE_URL}${label}" || true)"
  if [ "${status}" != "404" ]; then
    fail "${label}" "expected 404, got ${status:-<none>} — the SPA fallback answers with index.html, so the layer location is missing or lacks 'try_files \$uri =404'"
  fi
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

# 5. Layer delivery contract (plan D / D1.2), only when explicitly requested.
if [ "${bluepencil}" -eq 1 ]; then
  check_bluepencil
  check_bluepencil_missing
fi

if [ "${failures}" -ne 0 ]; then
  printf '%d header check(s) failed\n' "${failures}" >&2
  exit 1
fi

printf 'OK: security headers present on every checked response\n'
