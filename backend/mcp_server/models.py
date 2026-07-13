"""
ARCH-L1-003 McpServer — Models.

McpServer is a pure adapter layer (no own models).
All entities are owned by the persistence app (ARCH-L1-010).

TODO(COMP-MCP-001): Implement MCP tool dispatcher — routes tool calls to
  ApplicationService use-case methods.
TODO(COMP-MCP-002): Implement 20 MCP tools in 4 groups:
  Group 1 — Requirements: requirement.create, requirement.get, requirement.update,
    requirement.delete, requirement.list, requirement.decompose
  Group 2 — Architecture: architecture.create, architecture.get, architecture.update,
    architecture.list, architecture.link
  Group 3 — Tests: test.create, test.get, test.update, test.list, test.run
  Group 4 — Cross-cutting: artifact.search (REQ-L1-020), workspace.get_preset,
    trace.query, baseline.create
TODO(COMP-MCP-003): Implement transport handlers: stdio, SSE, HTTP.
TODO(COMP-MCP-004): Implement preset-aware tool visibility filter.

Reference: docs/se/L1/Gesamtsystem/L2/McpServerSystem/L2_McpServerSystem_Architecture.md
"""
