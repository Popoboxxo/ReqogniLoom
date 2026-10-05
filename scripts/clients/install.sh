#!/usr/bin/env bash
# ReqogniLoom client installer (#1171, Bundle B0, AP-1.3).
#
# One command per client. Writes only the client-side config, never a secret:
# the key is passed as an *env-var name* (--key-env), never as a value, so it
# cannot leak into argv, shell history, or the config file.
#
# Usage:
#   scripts/clients/install.sh --client <id> --url <https://host> \
#       [--key-env REQOGNILOOM_API_KEY] [--dry-run] [--yes]
#
# Supported ids: claude-code codex opencode kimi-code antigravity hermes
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

CLIENT=""
URL=""
KEY_ENV="REQOGNILOOM_API_KEY"
DRY_RUN=0
ASSUME_YES=0

usage() {
  sed -n '2,14p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
  exit "${1:-0}"
}

while [ $# -gt 0 ]; do
  case "$1" in
    --client) CLIENT="${2:-}"; shift 2 ;;
    --url) URL="${2:-}"; shift 2 ;;
    --key-env) KEY_ENV="${2:-}"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    --yes) ASSUME_YES=1; shift ;;
    -h|--help) usage 0 ;;
    *) echo "unknown argument: $1" >&2; usage 1 ;;
  esac
done

[ -n "$CLIENT" ] || { echo "--client is required" >&2; usage 1; }
[ -n "$URL" ] || { echo "--url is required" >&2; usage 1; }
URL="${URL%/}"
KEY_ENV="${KEY_ENV:-REQOGNILOOM_API_KEY}"

run() {
  if [ "$DRY_RUN" -eq 1 ]; then
    printf '[dry-run] %s\n' "$*"
  else
    "$@"
  fi
}

require_bin() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "error: '$1' not found on PATH (client '$CLIENT' requires it)" >&2
    exit 3
  fi
}

# backup_file <path> — timestamped copy before an in-place edit.
backup_file() {
  local path="$1"
  [ -f "$path" ] || return 0
  local bak="${path}.bak-$(date +%Y%m%d%H%M%S)"
  run cp "$path" "$bak"
  echo "backup: $bak"
}

confirm() {
  [ "$ASSUME_YES" -eq 1 ] && return 0
  [ "$DRY_RUN" -eq 1 ] && return 0
  printf 'Write config for %s against %s? [y/N] ' "$CLIENT" "$URL"
  read -r reply
  case "$reply" in y|Y|yes|YES) return 0 ;; *) echo "aborted" >&2; exit 1 ;; esac
}

install_claude_code() {
  require_bin claude
  local marketplace="${SCRIPT_DIR}/../../dist/plugins/claude-code"
  run claude plugin marketplace add "$marketplace"
  run claude plugin install reqogniloom@claude-code
  echo "export REQOGNILOOM_MCP_URL=\"$URL\""
  echo "export ${KEY_ENV}=\"reqlo_...\"   # set this in your shell"
}

install_codex() {
  require_bin codex
  run codex mcp add reqogniloom --url "$URL/mcp/"
}

install_opencode() {
  require_bin opencode
  run opencode mcp add reqogniloom --url "$URL/mcp/sse/"
}

install_kimi_code() {
  local dir="${HOME}/.kimi-code"
  local file="${dir}/mcp.json"
  if [ "$DRY_RUN" -eq 0 ]; then mkdir -p "$dir"; fi
  backup_file "$file"
  local payload
  payload=$(cat <<JSON
{
  "mcpServers": {
    "reqogniloom": {
      "type": "http",
      "url": "$URL/mcp/",
      "headers": { "Authorization": "Bearer \${${KEY_ENV}}" }
    }
  }
}
JSON
)
  if [ "$DRY_RUN" -eq 1 ]; then
    printf '[dry-run] write %s:\n%s\n' "$file" "$payload"
  else
    printf '%s\n' "$payload" > "$file"
    echo "wrote $file"
  fi
}

install_antigravity() {
  local dir="${HOME}/.gemini/config"
  local file="${dir}/mcp_config.json"
  if [ "$DRY_RUN" -eq 0 ]; then mkdir -p "$dir"; fi
  backup_file "$file"
  local payload
  payload=$(cat <<JSON
{
  "mcpServers": {
    "reqogniloom": {
      "type": "sse",
      "url": "$URL/mcp/sse/",
      "headers": { "X-API-Key": "\${${KEY_ENV}}" }
    }
  }
}
JSON
)
  if [ "$DRY_RUN" -eq 1 ]; then
    printf '[dry-run] write %s:\n%s\n' "$file" "$payload"
  else
    printf '%s\n' "$payload" > "$file"
    echo "wrote $file"
  fi
}

install_hermes() {
  require_bin hermes
  run hermes mcp add reqogniloom
}

case "$CLIENT" in
  claude-code) confirm; install_claude_code ;;
  codex) confirm; install_codex ;;
  opencode) confirm; install_opencode ;;
  kimi-code) confirm; install_kimi_code ;;
  antigravity) confirm; install_antigravity ;;
  hermes) confirm; install_hermes ;;
  *) echo "unknown client: $CLIENT" >&2; usage 1 ;;
esac

echo "install: $CLIENT configured"
if [ "$CLIENT" != "kimi-code" ] && [ "$CLIENT" != "antigravity" ]; then
  exec "$SCRIPT_DIR/verify.sh" --client "$CLIENT"
fi
