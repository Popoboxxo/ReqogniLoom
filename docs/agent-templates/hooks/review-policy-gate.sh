#!/usr/bin/env bash
# review-policy-gate.sh — optional Claude Code PreToolUse hook reference implementation.
# Not a security mechanism: see review-policy-gate.md for its limitations.
set -euo pipefail

input="$(cat)"
tool_name="$(printf '%s' "$input" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("tool_name",""))')"
role="${REQFLOW_AGENT_ROLE:-}"

decision="allow"

if [[ -n "$role" ]]; then
  case "$role" in
    requirements-architect)
      case "$tool_name" in
        needs.create|needs.update|requirement.create|requirement.update|requirement.decompose)
          decision="ask" ;;
      esac
      ;;
    risk-analyst)
      case "$tool_name" in
        risk.create|risk.update|risk.delete)
          decision="ask" ;;
      esac
      ;;
    change-manager)
      case "$tool_name" in
        adr.create|adr.update|adr.delete|issue.create|issue.update|issue.delete|requirement.update|architecture.update)
          decision="ask" ;;
      esac
      ;;
    test-engineer|quality-auditor)
      # review profile is "auto" for both -- no gating.
      ;;
  esac
fi

python3 -c "
import json
print(json.dumps({'hookSpecificOutput': {'permissionDecision': '$decision'}}))
"
