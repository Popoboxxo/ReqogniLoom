# Agent Template Installation

## Claude Code

1. Add the local marketplace (once per machine, or point at the published
   Git repo once this package is pushed to one):
   ```bash
   claude plugin marketplace add dist/plugins/claude-code
   ```
2. Install the plugin:
   ```bash
   claude plugin install reqogniloom
   ```
3. Set the two required environment variables before starting Claude Code
   (never commit real values — use your shell profile or a secrets
   manager, matching this repo's own `templates/configs/mcp-secrets.local-template.yaml`
   convention):
   ```bash
   export REQOGNILOOM_MCP_URL="https://your-reqogniloom-instance"
   export REQOGNILOOM_API_KEY="reqlo_..."
   ```
4. Verify: `/plugin` inside Claude Code should list `reqogniloom` as
   installed with 5 agents and 1 MCP server (`reqogniloom`, SSE).
5. Invoke a role: `@requirements-architect` and ask it to call
   `workspace.get_context` — a successful response confirms the MCP
   connection, auth, and RBAC all resolved correctly end to end. Then try
   `@change-manager` and ask it to call `review.list_pending` — this
   confirms the Task 3 additions (CCB/review tools) actually reached the
   packaged agent.
