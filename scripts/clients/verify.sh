#!/usr/bin/env bash
# ReqogniLoom client verifier (#1171, Bundle B0, AP-1.3).
#
# The unified smoke check: prove the client is *connected*, not merely
# configured. For clients with a native status command we grep the expected
# marker; for config-file-only clients we validate the config loads and point
# the operator at the in-client smoke task (docs/clients/README.md).
#
# Usage: bash scripts/clients/verify.sh --client <id>
set -euo pipefail

CLIENT=""
while [ $# -gt 0 ]; do
  case "$1" in
    --client) CLIENT="${2:-}"; shift 2 ;;
    -h|--help) sed -n '2,10p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done
[ -n "$CLIENT" ] || { echo "--client is required" >&2; exit 2; }

# Name of the OpenCode client binary (default `opencode`), matching install.sh.
OPENCODE_BIN="${OPENCODE_BIN:-opencode}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

require_bin() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "fail: '$1' not found on PATH" >&2; exit 3;
  }
}

expect_marker() {
  local haystack="$1" marker="$2"
  if printf '%s' "$haystack" | grep -qF -- "$marker"; then
    echo "ok: found '$marker'"
  else
    echo "fail: expected marker '$marker' not found" >&2
    exit 1
  fi
}

case "$CLIENT" in
  claude-code)
    require_bin claude
    out="$(claude mcp list 2>&1 || true)"
    expect_marker "$out" "reqogniloom"
    echo "info: skills ship inside the installed reqogniloom plugin (no separate copy)."
    ;;
  codex)
    require_bin codex
    out="$(codex mcp list 2>&1 || true)"
    expect_marker "$out" "reqogniloom"
    expect_marker "$out" "enabled"
    echo "info: skills expected at ${HOME}/.codex/skills"
    ;;
  opencode|opencode-v2)
    require_bin "$OPENCODE_BIN"
    # Isolation: run the client outside the checkout. OpenCode also loads a
    # project-root config, so inside the repository it would mix the
    # maintainer's own servers into the answer (observed: a foreign
    # `playwright` server appeared next to reqogniloom).
    verify_cwd="$(mktemp -d)"
    trap 'rm -rf "$verify_cwd"' EXIT
    # OpenCode V2 runs a background service that re-reads the config written by
    # install.sh with a delay (docs/clients/opencode-v2-known-issues.md); a
    # single immediate `mcp list` produced a false negative. V1 needs no retry.
    attempts="${VERIFY_RETRY_ATTEMPTS:-}"
    if [ -z "$attempts" ]; then
      if [ "$CLIENT" = "opencode-v2" ]; then attempts=10; else attempts=3; fi
    fi
    delay="${VERIFY_RETRY_DELAY:-2}"
    out=""
    i=0
    while [ "$i" -lt "$attempts" ]; do
      out="$(cd "$verify_cwd" && "$OPENCODE_BIN" mcp list 2>&1 || true)"
      if printf '%s' "$out" | grep -q "reqogniloom"; then break; fi
      i=$((i + 1))
      [ "$i" -lt "$attempts" ] && sleep "$delay"
    done
    expect_marker "$out" "reqogniloom"
    echo "info: skills expected at ${HOME}/.config/opencode/skills (DOMAIN_MODEL.md at ${HOME}/.config/opencode/; pass --skills-dir for a per-project install)"
    if [ "$CLIENT" = "opencode-v2" ]; then
      echo "info: OpenCode V2 is a beta; config lives in mcp.servers.reqogniloom"
    fi
    ;;
  hermes)
    require_bin hermes
    out="$(hermes mcp test reqogniloom 2>&1 || true)"
    expect_marker "$out" "Connected"
    echo "info: skills expected at ${HOME}/.hermes/skills/reqogniloom"

    # #1914: a copied plugin install goes stale while a symlink follows
    # `git pull`. Enforce that the installed SemVer matches the shipped
    # manifest, and point at the explicit --refresh update path on drift.
    repo_plugin="$REPO_ROOT/integrations/hermes-agent-plugin/plugin.yaml"
    installed_plugin="${HERMES_PLUGINS_DIR:-$HOME/.hermes/plugins}/reqogniloom"
    if [ -f "$repo_plugin" ] && [ -f "$installed_plugin/plugin.yaml" ]; then
      expected_version="$(sed -n 's/^version:[[:space:]]*//p' "$repo_plugin" | head -n 1 | tr -d '\r"')"
      actual_version="$(sed -n 's/^version:[[:space:]]*//p' "$installed_plugin/plugin.yaml" | head -n 1 | tr -d '\r"')"
      if [ -n "$expected_version" ] && [ "$actual_version" != "$expected_version" ]; then
        echo "fail: installed Hermes plugin $actual_version != shipped $expected_version (#1914)" >&2
        echo "      update: bash $REPO_ROOT/scripts/clients/install.sh --client hermes --with-dashboard --refresh --url \"https://<host>\" --key-env REQOGNILOOM_API_KEY" >&2
        exit 1
      fi
      echo "ok: Hermes plugin version $actual_version matches shipped manifest"
      if [ -L "$installed_plugin" ]; then
        echo "info: symlink install -> $(readlink "$installed_plugin") (follows git pull)"
      fi
    elif [ ! -f "$installed_plugin/plugin.yaml" ]; then
      echo "info: no agent/dashboard plugin at $installed_plugin (optional; use --with-dashboard)"
    fi
    ;;
  kimi-code|antigravity)
    # No native status command: the config file is the artifact. A full smoke
    # test runs in-client (see docs/clients/README.md -> Unified smoke test).
    echo "info: $CLIENT has no native status command."
    echo "info: run the in-client smoke task and cross-check against REST:"
    echo "      GET /api/v1/requirements/?workspace_id=<id> -> count"
    if [ "$CLIENT" = "kimi-code" ]; then
      echo "info: skills expected at ${HOME}/.kimi-code/skills"
    else
      echo "info: skills expected at ${HOME}/.gemini/skills (DOMAIN_MODEL.md at ${HOME}/.gemini/; pass --skills-dir for a per-project install)"
    fi
    ;;
  *)
    echo "unknown client: $CLIENT" >&2; exit 2 ;;
esac

echo "verify: $CLIENT OK"
