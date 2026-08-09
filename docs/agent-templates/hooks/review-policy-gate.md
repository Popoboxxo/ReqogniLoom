# review-policy-gate.sh — limitations

This is a **reference implementation for Claude Code only** (`PreToolUse` hook). It is not a
security mechanism and not a substitute for ReqogniLoom's own `ReviewPolicy` configuration.

## What it does

Reads `REQFLOW_AGENT_ROLE` from the environment and, if the tool call about to run matches that
role's `review_changes`/`review_high_risk` tool subset (a static table hardcoded in the script,
derived from the `tools:` whitelist in each role's Markdown file at the time the hook was
written), returns a `permissionDecision` of `ask` instead of `allow`.

## Limitations

- **Static, not live:** the tool-to-role table is hardcoded in the script. If the downstream
  project changes its ReqogniLoom `ReviewPolicy` via the REST API (`PUT /api/v1/review-policy/`),
  this script does not know about it — the two can drift. Update the script's `case` blocks by
  hand if you change which tools should be gated for a role.
- **Claude Code only:** other providers (Gemini, Opencode, Continue) have no equivalent hook
  mechanism in this repository. For those, the review profile documented in each role file
  remains a prompt-level instruction to the agent, not an enforced gate.
- **Fail-open:** if `REQFLOW_AGENT_ROLE` is unset, the script returns `allow` for every tool call.
  This is intentional — a misconfigured downstream project should not silently lose all write
  access — but it means an unset environment variable provides zero protection. Set
  `REQFLOW_AGENT_ROLE` explicitly in your Claude Code settings (`env` block) if you want this
  hook to do anything.

## Installation

Add to the downstream project's Claude Code settings (e.g. `.claude/settings.json`):

```json
{
  "env": { "REQFLOW_AGENT_ROLE": "requirements-architecture-manager" },
  "hooks": {
    "PreToolUse": [
      { "matcher": "*", "hooks": [{ "type": "command", "command": "bash docs/agent-templates/hooks/review-policy-gate.sh" }] }
    ]
  }
}
```
