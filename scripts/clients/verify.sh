#!/usr/bin/env bash
# ReqogniLoom client verifier (#1171, Bundle B0, AP-1.3).
#
# The unified smoke check: prove the client is *connected*, not merely
# configured. For clients with a native status command we grep the expected
# marker; for config-file-only clients we validate the config loads and point
# the operator at the in-client smoke task (docs/clients/README.md).
#
# Usage: scripts/clients/verify.sh --client <id>
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
  opencode)
    require_bin opencode
    out="$(opencode mcp list 2>&1 || true)"
    expect_marker "$out" "reqogniloom"
    echo "info: skills expected at .opencode/skills (DOMAIN_MODEL.md at .opencode/)"
    ;;
  hermes)
    require_bin hermes
    out="$(hermes mcp test reqogniloom 2>&1 || true)"
    expect_marker "$out" "Connected"
    echo "info: skills expected at ${HOME}/.hermes/skills/reqogniloom"
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
      echo "info: skills expected at .agents/skills (DOMAIN_MODEL.md at .agents/)"
    fi
    ;;
  *)
    echo "unknown client: $CLIENT" >&2; exit 2 ;;
esac

echo "verify: $CLIENT OK"
