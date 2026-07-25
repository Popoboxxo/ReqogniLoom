# Bootstrap snippet — ReqogniLoom Agent Templates

Copy this section into your project's `CLAUDE.md` / `AGENTS.md` / `GEMINI.md`.

## ReqogniLoom MCP Integration

This project talks to a ReqogniLoom workspace via its native MCP server:

- Endpoint: `{{REQFLOW_MCP_URL}}/mcp/sse/` (Server-Sent Events, JSON-RPC 2.0)
- Auth: API-key header (see your ReqogniLoom instance's API-key management; never hardcode the
  key in this file — inject it via your MCP client's secret/credential mechanism)

Five agent roles are available under `docs/agent-templates/` (or wherever you copied them to in
this project):

- **requirements-architect** — capture stakeholder needs, derive and decompose requirements
  (V-Modell L0-L3).
- **test-engineer** — create/link test cases, record test-run results.
- **risk-analyst** — identify risks, link them to requirements/architecture.
- **change-manager** — manage ADRs/issues, apply approved requirement/architecture changes.
- **quality-auditor** — read-only traceability and coverage auditing.

Each role's Markdown file's YAML frontmatter carries a `compatible_with` field (currently
`reqogniloom>=1.0.0`) — check it against your ReqogniLoom instance's `VERSION` file before
trusting the `tools:` whitelist; a mismatch means the MCP tool names may be stale.

If you use the optional Claude Code review-policy hook (`hooks/review-policy-gate.sh`), set
`REQFLOW_AGENT_ROLE` to the active role name in your Claude Code settings' `env` block — see
`hooks/review-policy-gate.md` for installation and its limitations.
