# ReqogniLoom Agent Templates

Five provider-agnostic agent templates for a downstream project that wants to work against a
ReqogniLoom workspace through its native MCP server (`/mcp/sse/`, JSON-RPC 2.0).

## Roles

| File | Role | Review profile |
|---|---|---|
| `requirements-architect.md` | Capture stakeholder needs, derive/decompose requirements (V-Modell L0-L3) | `review_changes` |
| `test-engineer.md` | Create/link test cases, record test-run results | `auto` |
| `risk-analyst.md` | Identify risks, link to requirements/architecture | `review_high_risk` |
| `change-manager.md` | Manage ADRs/issues, apply approved requirement/architecture changes | `review_high_risk` |
| `quality-auditor.md` | Read-only traceability and coverage auditing | `auto` (no write tools) |

## Installation

1. Copy the role file(s) you need into your project's agent-definition directory (for an
   `agent-meta`-based project: `agents/1-generic/` or `agents/2-platform/`, matching the
   Frontmatter format already used there; for other setups, wherever your provider expects an
   agent system-prompt file with YAML frontmatter).
2. Check the `compatible_with` field against the `VERSION` file of the ReqogniLoom instance you
   are connecting to. These templates were written against `reqogniloom>=1.0.0`; a
   `compatible_with` mismatch means a `tools:` whitelist entry may reference an MCP tool name
   that has since been renamed or removed — re-verify against your instance's MCP tool registry
   before trusting the whitelist.
3. Copy the relevant section of `BOOTSTRAP.md` into your project's `CLAUDE.md`/`AGENTS.md`/
   `GEMINI.md` (or equivalent).
4. (Claude Code only, optional) install the review-policy hook — see
   `hooks/review-policy-gate.md`.

## Scope

These templates are for **downstream projects consuming ReqogniLoom** — they are not
ReqogniLoom's own `se-*` development-process agents (those live in this repo's own agent
configuration and are out of scope here).
