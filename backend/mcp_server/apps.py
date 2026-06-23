"""App configuration for ARCH-L1-003 McpServer."""
from django.apps import AppConfig


class McpServerConfig(AppConfig):
    """ARCH-L1-003 McpServer — MCP Protocol Handler.

    Responsibilities:
    - Native MCP protocol handler (stdio/sse/HTTP transport per client).
    - 20 Tools in 4 groups: Requirements, Architecture, Tests, Cross-cutting.
    - Accesses ApplicationService DIRECTLY (not via REST, ADR-01).
    - Write operations are recorded in AuditLog with Agent-Client identity + API Key.
    - Consults PresetConfigEngine for tool visibility per workspace preset.

    See: docs/se/L1/Gesamtsystem/L2/McpServerSystem/L2_McpServerSystem_Architecture.md
    REQ-L1: REQ-L1-005 (MCP server)
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "mcp_server"
    verbose_name = "ARCH-L1-003 McpServer"
