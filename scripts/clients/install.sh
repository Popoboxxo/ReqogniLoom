#!/usr/bin/env bash
# ReqogniLoom client installer (#1171, Bundle B0, AP-1.3).
#
# One command per client: installs the MCP server *and* the ReqogniLoom skills.
# Writes only client-side files, never a secret: the key is passed as an
# *env-var name* (--key-env), never a value, so it cannot leak into argv,
# shell history, or the config file.
#
# Usage:
#   bash scripts/clients/install.sh --client <id> --url <https://host> \
#       [--key-env REQOGNILOOM_API_KEY] [--skills-dir <dir>] \
#       [--with-dashboard] [--force|--refresh] [--dry-run] [--yes]
#
# --skills-dir overrides the per-client default skills directory.
# --with-dashboard (hermes only) also links the agent + dashboard plugin into
#       ~/.hermes/plugins/reqogniloom (own SemVer, ADR-017 decision 2).
# --force / --refresh re-copies existing skills, DOMAIN_MODEL.md and a copied
#       Hermes plugin after a timestamped `.bak-<ts>` backup; without it an
#       existing destination is left untouched (safe re-runs, #1351).
# Supported ids: claude-code codex opencode opencode-v2 kimi-code antigravity hermes
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

CLIENT=""
URL=""
KEY_ENV="REQOGNILOOM_API_KEY"
SKILLS_DIR=""
WITH_DASHBOARD=0
REFRESH=0
DRY_RUN=0
ASSUME_YES=0
# Name of the OpenCode client binary. Overridable so a V2 beta installed under
# another name (e.g. `opencode2`) can still be detected and driven.
OPENCODE_BIN="${OPENCODE_BIN:-opencode}"

usage() {
  sed -n '2,20p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
  exit "${1:-0}"
}

while [ $# -gt 0 ]; do
  case "$1" in
    --client) CLIENT="${2:-}"; shift 2 ;;
    --url) URL="${2:-}"; shift 2 ;;
    --key-env) KEY_ENV="${2:-}"; shift 2 ;;
    --skills-dir) SKILLS_DIR="${2:-}"; shift 2 ;;
    --with-dashboard) WITH_DASHBOARD=1; shift ;;
    --force|--refresh) REFRESH=1; shift ;;
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
if [ "$WITH_DASHBOARD" -eq 1 ] && [ "$CLIENT" != "hermes" ]; then
  echo "--with-dashboard is only supported for --client hermes" >&2
  usage 1
fi

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

# backup_file <path> — timestamped copy (.bak-<ts>) before an in-place edit or a
# --refresh replacement. Accepts a file or a directory.
backup_file() {
  local path="$1"
  [ -e "$path" ] || return 0
  local bak="${path}.bak-$(date +%Y%m%d%H%M%S)"
  run cp -R "$path" "$bak"
  echo "backup: $bak"
}

confirm() {
  [ "$ASSUME_YES" -eq 1 ] && return 0
  [ "$DRY_RUN" -eq 1 ] && return 0
  printf 'Write config for %s against %s? [y/N] ' "$CLIENT" "$URL"
  read -r reply
  case "$reply" in y|Y|yes|YES) return 0 ;; *) echo "aborted" >&2; exit 1 ;; esac
}

# copy_if_absent <src> <dst> — copy a file or a directory. An existing
# destination is left untouched on a normal run (re-runs stay safe and
# idempotent); --force/--refresh replaces it instead, after copying the old
# target to `.bak-<ts>`. Without that branch the documented "re-run to update"
# path was a no-op (#1351).
copy_if_absent() {
  local src="$1" dst="$2"
  if [ ! -e "$src" ]; then
    echo "warn: source '$src' not found (client '$CLIENT')" >&2
    return 0
  fi
  if [ -e "$dst" ]; then
    if [ "$REFRESH" -eq 0 ]; then
      echo "skip: $dst (already present; pass --refresh to update)"
      return 0
    fi
    backup_file "$dst"
    # `cp -R src existing-dir` would nest src one level deeper; the backup above
    # is the rollback path, so replace the target instead of merging into it.
    run rm -rf "$dst"
    run cp -R "$src" "$dst"
    echo "refreshed: $dst"
    return 0
  fi
  if [ "$DRY_RUN" -eq 0 ]; then mkdir -p "$(dirname "$dst")"; fi
  run cp -R "$src" "$dst"
  echo "installed: $dst"
}

# copy_skills <src_dir> <dst_dir> — copy every child (one skill folder) into the
# destination; existing children are skipped unless --force/--refresh was given.
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

# resolve_skills_dir <default_dir> — echo the skills directory to install into.
#
# An explicit --skills-dir is honoured verbatim. A per-client *default* is
# expanded to an absolute path and refused when it lands inside this checkout:
# a CWD-relative default (`.opencode/skills`, `.agents/skills`) writes into
# whatever directory the installer happens to run from — including this
# ReqogniLoom repo — which the 2026-10-05 client smoke test flagged as an
# installer defect (docs/bugfix-hub/smoke/2026-10-05-client-smoke.md §5).
resolve_skills_dir() {
  local candidate="$1"
  if [ -n "$SKILLS_DIR" ]; then
    printf '%s' "$SKILLS_DIR"
    return 0
  fi
  case "$candidate" in
    /*|[A-Za-z]:[\\/]*) ;;                 # already absolute
    *) candidate="${PWD}/${candidate}" ;;
  esac
  case "$candidate" in
    "${REPO_ROOT}"|"${REPO_ROOT}"/*)
      echo "error: default skills dir '$1' resolves inside this checkout" >&2
      echo "       ($candidate); pass an absolute --skills-dir instead." >&2
      exit 4
      ;;
  esac
  printf '%s' "$candidate"
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
  # `--bearer-token-env-var` names the env var Codex reads and expands into
  # `Authorization: Bearer <key>`; Codex's Streamable-HTTP transport has no
  # custom-header option, so this is its ONLY way to carry the API key. Without
  # it the server is registered unauthenticated and every call 401s. The value
  # is an env-var *name*, never the key itself.
  run codex mcp add reqogniloom --url "$URL/mcp/" \
    --bearer-token-env-var "$KEY_ENV"
  local skills_dir
  skills_dir="$(resolve_skills_dir "$HOME/.codex/skills")"
  copy_skills "${REPO_ROOT}/dist/codex/skills" "$skills_dir"
  # SKILL.md links resolve '../../DOMAIN_MODEL.md' from skills/<name>/:
  copy_if_absent "${REPO_ROOT}/docs/agent-templates/DOMAIN_MODEL.md" \
    "$(dirname "$skills_dir")/DOMAIN_MODEL.md"
}

install_opencode_v1() {
  require_bin "$OPENCODE_BIN"
  # The key header is passed as an opencode env placeholder (env indirection);
  # `--header` keeps the value literal, so no secret ever lands in argv. Without
  # `--header` opencode registers the server with no credential and reports
  # "needs authentication" on connect.
  run "$OPENCODE_BIN" mcp add reqogniloom --url "$URL/mcp/sse/" \
    --header "X-API-Key={env:${KEY_ENV}}"
  # Default to OpenCode's USER-level skills dir (never the CWD): a default of
  # `.opencode/skills` writes into whatever directory the installer happens to
  # run from — including this ReqogniLoom checkout — which the client smoke test
  # flagged as an installer defect. Pass --skills-dir for a per-project install.
  local skills_dir
  skills_dir="$(resolve_skills_dir "$HOME/.config/opencode/skills")"
  copy_skills "${REPO_ROOT}/dist/opencode/skills" "$skills_dir"
  # SKILL.md links resolve '../../DOMAIN_MODEL.md' from skills/<name>/:
  copy_if_absent "${REPO_ROOT}/docs/agent-templates/DOMAIN_MODEL.md" \
    "$(dirname "$skills_dir")/DOMAIN_MODEL.md"
}

# detect_opencode_major — echo the client binary's major version (1 or 2).
#
# Falls back to 1 whenever `--version` is missing or unparseable, so an absent or
# older binary keeps the long-standing V1 path instead of failing. The version
# output is captured *before* it is parsed on purpose: under `set -euo pipefail`
# a bare `"$OPENCODE_BIN" --version | sed … | head -1` aborts the whole installer
# when the binary is absent (127) or when `head` closes the pipe early
# (SIGPIPE/141) — the trailing `|| true` covers the latter, the capture covers
# the former.
detect_opencode_major() {
  local out major
  out="$("$OPENCODE_BIN" --version 2>/dev/null || true)"
  # V2 prints "opencode v2.2.5", V1 prints "1.19.5": skip any non-digit prefix
  # (program name, honourific "v"), then take the first major before a dot.
  major="$(printf '%s\n' "$out" | tr -d '\r' \
    | sed -nE 's/^[^0-9]*([0-9]+)\.[0-9]+.*/\1/p' | head -1 || true)"
  printf '%s\n' "${major:-1}"
}

# install_opencode_v2 — OpenCode V2 (beta) reads MCP servers from
# `mcp.servers.<name>` and `mcp add` does not write that shape, so the entry is
# merged into the JSON config by dist/opencode/merge_config.py instead. Writing
# the config needs no client binary, hence no require_bin here; merge_config.py
# refuses JSONC/invalid JSON and writes nothing in that case.
install_opencode_v2() {
  # --key-env is an env-var *name* that ends up inside an `{env:NAME}`
  # placeholder. Anything that is not a plain shell identifier (space, `$`,
  # `{`, `}`) would be a config-injection path, so it is rejected before any
  # file is touched.
  if ! [[ "$KEY_ENV" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
    echo "error: --key-env must be an env-var name ([A-Za-z_][A-Za-z0-9_]*)," \
      "got '$KEY_ENV'" >&2
    exit 2
  fi
  local config="${XDG_CONFIG_HOME:-$HOME/.config}/opencode/opencode.json"
  local merge_args=(--config "$config" --url "$URL" --key-env "$KEY_ENV")
  if [ "$DRY_RUN" -eq 1 ]; then merge_args+=(--dry-run); fi
  run python3 "${REPO_ROOT}/dist/opencode/merge_config.py" "${merge_args[@]}"
  # Skills and DOMAIN_MODEL.md are the same artifacts as on the V1 path.
  local skills_dir
  skills_dir="$(resolve_skills_dir "$HOME/.config/opencode/skills")"
  copy_skills "${REPO_ROOT}/dist/opencode/skills" "$skills_dir"
  # SKILL.md links resolve '../../DOMAIN_MODEL.md' from skills/<name>/:
  copy_if_absent "${REPO_ROOT}/docs/agent-templates/DOMAIN_MODEL.md" \
    "$(dirname "$skills_dir")/DOMAIN_MODEL.md"
}

# install_opencode — pick the installer path from the client binary's major
# version; an unknown/absent version keeps V1 (see detect_opencode_major).
install_opencode() {
  if [ "$(detect_opencode_major)" = 2 ]; then
    install_opencode_v2
  else
    install_opencode_v1
  fi
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
  local skills_dir
  skills_dir="$(resolve_skills_dir "$HOME/.kimi-code/skills")"
  copy_skills "${REPO_ROOT}/dist/agent-skills" "$skills_dir"
  # SKILL.md links resolve '../../DOMAIN_MODEL.md' from skills/<name>/:
  copy_if_absent "${REPO_ROOT}/docs/agent-templates/DOMAIN_MODEL.md" \
    "$(dirname "$skills_dir")/DOMAIN_MODEL.md"
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
  # Default to Antigravity's USER-level skills dir, sibling of the
  # `~/.gemini/config/mcp_config.json` written above — a CWD-relative default
  # (`.agents/skills`) would write into whatever directory the installer runs
  # from, including this checkout. Pass --skills-dir for a per-project install.
  local skills_dir
  skills_dir="$(resolve_skills_dir "$HOME/.gemini/skills")"
  copy_skills "${REPO_ROOT}/dist/plugins/antigravity/reqogniloom/skills" "$skills_dir"
  copy_if_absent "${REPO_ROOT}/dist/plugins/antigravity/reqogniloom/DOMAIN_MODEL.md" \
    "$(dirname "$skills_dir")/DOMAIN_MODEL.md"
}

# install_hermes_plugin - agent + dashboard plugin (issue #1352).
#
# The plugin lives in `integrations/hermes-agent-plugin/` and keeps its own
# SemVer + minServerVersion (ADR-017 decision 2), so it is NOT version-coupled
# to VERSION. A symlink is preferred over a copy: `git pull` then updates the
# installed plugin without re-running the installer. Hosts where symlinks are
# unavailable fall back to a copy; re-run with --force/--refresh to replace that
# copy (timestamped backup first) or remove it manually.
install_hermes_plugin() {
  local src="${REPO_ROOT}/integrations/hermes-agent-plugin"
  local dst="${HERMES_PLUGINS_DIR:-$HOME/.hermes/plugins}/reqogniloom"
  if [ ! -d "$src" ]; then
    echo "warn: plugin source '$src' not found (client '$CLIENT')" >&2
    return 0
  fi
  if [ -L "$dst" ]; then
    if [ "$REFRESH" -eq 1 ]; then
      # Remove the link itself (never the target) and re-link; `ln -sfn` is not
      # portable across all hosts the installer supports.
      run rm -f "$dst"
      run ln -s "$src" "$dst"
      echo "refreshed: $dst -> $src"
    else
      echo "skip: $dst (symlink; follows git pull — pass --refresh to re-link)"
    fi
    return 0
  fi
  if [ -e "$dst" ]; then
    if [ "$REFRESH" -eq 0 ]; then
      echo "skip: $dst (already present; pass --refresh to update)"
      return 0
    fi
    backup_file "$dst"
    run rm -rf "$dst"
  fi
  if [ "$DRY_RUN" -eq 1 ]; then
    printf '[dry-run] ln -s %s %s\n' "$src" "$dst"
    return 0
  fi
  mkdir -p "$(dirname "$dst")"
  if ln -s "$src" "$dst" 2>/dev/null; then
    echo "installed: $dst -> $src"
  else
    cp -R "$src" "$dst"
    echo "installed: $dst (copy; pass --refresh to update)"
  fi
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
  if [ "$WITH_DASHBOARD" -eq 1 ]; then
    install_hermes_plugin
  fi
}

case "$CLIENT" in
  claude-code) confirm; install_claude_code ;;
  codex) confirm; install_codex ;;
  opencode) confirm; install_opencode ;;
  opencode-v2) confirm; install_opencode_v2 ;;
  kimi-code) confirm; install_kimi_code ;;
  antigravity) confirm; install_antigravity ;;
  hermes) confirm; install_hermes ;;
  *) echo "unknown client: $CLIENT" >&2; usage 1 ;;
esac

echo "install: $CLIENT configured"
if [ "$CLIENT" != "kimi-code" ] && [ "$CLIENT" != "antigravity" ]; then
  # A dry-run must stay side-effect free: preview the verify step, never exec it.
  if [ "$DRY_RUN" -eq 1 ]; then
    printf '[dry-run] skip: bash %s --client %s\n' "$SCRIPT_DIR/verify.sh" "$CLIENT"
  else
    # Invoke through `bash`: a Windows checkout (core.fileMode=false) does not
    # materialise the index's 100755 bit, so a direct `exec` fails with exit 126
    # even though the repository mode is correct (#1350).
    exec bash "$SCRIPT_DIR/verify.sh" --client "$CLIENT"
  fi
fi
