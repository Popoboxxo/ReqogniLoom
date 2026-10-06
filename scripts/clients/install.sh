#!/usr/bin/env bash
# ReqogniLoom client installer (#1171, Bundle B0, AP-1.3).
#
# One command per client: installs the MCP server *and* the ReqogniLoom skills.
# Writes only client-side files, never a secret: the key is passed as an
# *env-var name* (--key-env), never a value, so it cannot leak into argv,
# shell history, or the config file.
#
# Usage:
#   scripts/clients/install.sh --client <id> --url <https://host> \
#       [--key-env REQOGNILOOM_API_KEY] [--skills-dir <dir>] [--dry-run] [--yes]
#
# --skills-dir overrides the per-client default skills directory.
# Supported ids: claude-code codex opencode kimi-code antigravity hermes
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

CLIENT=""
URL=""
KEY_ENV="REQOGNILOOM_API_KEY"
SKILLS_DIR=""
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
    --skills-dir) SKILLS_DIR="${2:-}"; shift 2 ;;
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
  # A dry-run only previews: it must not fail when a client binary is absent.
  [ "$DRY_RUN" -eq 1 ] && return 0
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

# copy_if_absent <src> <dst> — copy-if-absent (no refresh). Accepts a file or a
# directory; an existing destination is left untouched, so re-runs are safe but
# never update a changed source. Callers needing a refresh must remove the target.
copy_if_absent() {
  local src="$1" dst="$2"
  if [ ! -e "$src" ]; then
    echo "warn: source '$src' not found (client '$CLIENT')" >&2
    return 0
  fi
  if [ -e "$dst" ]; then
    echo "skip: $dst (already present)"
    return 0
  fi
  if [ "$DRY_RUN" -eq 0 ]; then mkdir -p "$(dirname "$dst")"; fi
  run cp -R "$src" "$dst"
  echo "installed: $dst"
}

# copy_skills <src_dir> <dst_dir> — copy every child (one skill folder) into the
# destination; existing children are skipped, so a second run changes nothing.
copy_skills() {
  local src="$1" dst="$2" child
  if [ ! -d "$src" ]; then
    echo "warn: skills source '$src' not found (client '$CLIENT')" >&2
    return 0
  fi
  for child in "$src"/*; do
    [ -e "$child" ] || continue
    copy_if_absent "$child" "${dst}/$(basename "$child")"
  done
}

install_claude_code() {
  require_bin claude
  local marketplace="${SCRIPT_DIR}/../../dist/plugins/claude-code"
  # `plugin@marketplace` must name the marketplace declared in its own
  # marketplace.json ("name"), not the source directory (claude-code):
  # otherwise `Plugin "reqogniloom" not found in marketplace "<id>"`.
  local marketplace_name
  marketplace_name="$(sed -n 's/.*"name"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' \
    "${marketplace}/.claude-plugin/marketplace.json" | head -n 1)"
  if [ -z "$marketplace_name" ]; then
    echo "error: no marketplace name in ${marketplace}/.claude-plugin/marketplace.json" >&2
    exit 3
  fi
  run claude plugin marketplace add "$marketplace"
  # --scope user keeps the plugin out of the project tree; -y accepts the
  # marketplace-declared command without prompting (required off a TTY).
  run claude plugin install "reqogniloom@${marketplace_name}" --scope user -y
  # The plugin ships its own skills/ and agents/ — nothing to copy separately.
  echo "export REQOGNILOOM_MCP_URL=\"$URL\""
  echo "export ${KEY_ENV}=\"reqlo_...\"   # set this in your shell"
}

install_codex() {
  require_bin codex
  run codex mcp add reqogniloom --url "$URL/mcp/"
  local skills_dir="${SKILLS_DIR:-$HOME/.codex/skills}"
  copy_skills "${REPO_ROOT}/dist/codex/skills" "$skills_dir"
  # SKILL.md links resolve '../../DOMAIN_MODEL.md' from skills/<name>/:
  copy_if_absent "${REPO_ROOT}/docs/agent-templates/DOMAIN_MODEL.md" \
    "$(dirname "$skills_dir")/DOMAIN_MODEL.md"
}

install_opencode() {
  require_bin opencode
  # The key header is passed as an opencode env placeholder (env indirection);
  # `--header` keeps the value literal, so no secret ever lands in argv.
  run opencode mcp add reqogniloom --url "$URL/mcp/sse/" \
    --header "X-API-Key={env:${KEY_ENV}}"
  local skills_dir="${SKILLS_DIR:-.opencode/skills}"
  copy_skills "${REPO_ROOT}/dist/opencode/skills" "$skills_dir"
  # SKILL.md links resolve '../../DOMAIN_MODEL.md' from skills/<name>/:
  copy_if_absent "${REPO_ROOT}/docs/agent-templates/DOMAIN_MODEL.md" \
    "$(dirname "$skills_dir")/DOMAIN_MODEL.md"
}

install_kimi_code() {
  local dir="${HOME}/.kimi-code"
  local file="${dir}/mcp.json"
  if [ "$DRY_RUN" -eq 0 ]; then mkdir -p "$dir"; fi
  backup_file "$file"
  local payload
  # Kimi's mcp.json schema keys off `transport` and resolves the bearer token
  # from `bearerTokenEnvVar`; a literal `headers.Authorization: Bearer ${VAR}`
  # is NOT interpolated and is sent verbatim (→ 401, no tools). The value is
  # an env-var *name*, never a secret.
  payload=$(cat <<JSON
{
  "mcpServers": {
    "reqogniloom": {
      "transport": "http",
      "url": "$URL/mcp/",
      "bearerTokenEnvVar": "${KEY_ENV}"
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
  copy_skills "${REPO_ROOT}/dist/agent-skills" "${SKILLS_DIR:-$HOME/.kimi-code/skills}"
  # SKILL.md links resolve '../../DOMAIN_MODEL.md' from skills/<name>/:
  copy_if_absent "${REPO_ROOT}/docs/agent-templates/DOMAIN_MODEL.md" \
    "$(dirname "${SKILLS_DIR:-$HOME/.kimi-code/skills}")/DOMAIN_MODEL.md"
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
  # Copy the packaged skills offline (not `npx skills add`, which needs network).
  local skills_dir="${SKILLS_DIR:-.agents/skills}"
  copy_skills "${REPO_ROOT}/dist/plugins/antigravity/reqogniloom/skills" "$skills_dir"
  copy_if_absent "${REPO_ROOT}/dist/plugins/antigravity/reqogniloom/DOMAIN_MODEL.md" \
    "$(dirname "$skills_dir")/DOMAIN_MODEL.md"
}

install_hermes() {
  require_bin hermes
  # `hermes mcp add` is discovery-first: it prompts for a key on a TTY and
  # probes the server, which does not work as an installer step. Use Hermes'
  # own non-interactive config writer instead (same `mcp_servers` schema, deep
  # merge, idempotent). The bearer token is referenced by env-var name only;
  # Hermes interpolates ${VAR} from ~/.hermes/.env at spawn time.
  local cfg
  cfg="$(hermes config path 2>/dev/null || true)"
  if [ -n "$cfg" ]; then backup_file "$cfg"; fi
  run hermes config set mcp_servers.reqogniloom.url "$URL/mcp/"
  run hermes config set mcp_servers.reqogniloom.headers.Authorization "Bearer \${${KEY_ENV}}"
  copy_if_absent "${REPO_ROOT}/integrations/hermes-skill/reqogniloom" \
    "${SKILLS_DIR:-$HOME/.hermes/skills}/reqogniloom"
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
  # A dry-run must stay side-effect free: preview the verify step, never exec it.
  if [ "$DRY_RUN" -eq 1 ]; then
    printf '[dry-run] skip: %s --client %s\n' "$SCRIPT_DIR/verify.sh" "$CLIENT"
  else
    exec "$SCRIPT_DIR/verify.sh" --client "$CLIENT"
  fi
fi
