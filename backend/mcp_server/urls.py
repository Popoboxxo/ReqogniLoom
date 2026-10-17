"""
ARCH-L1-003 McpServer — URL routing.

Registers HTTP and SSE MCP transport endpoints (REQ-L2-MC-005).

  POST /mcp/       — HTTP transport (JSON-RPC 2.0 request/response)
  POST /mcp/sse/   — SSE transport (single-event response)
  GET  /mcp/       — Server info / health check

Canonical path (#1292): ``/mcp/`` is THE transport path — every shipped client
config points at it. The URLconf additionally mounts this same ``urlpatterns``
under the REST prefix (``/api/v1/mcp/``) for historical compatibility; that
alias is DEPRECATED and every response from it advertises the deprecation via
``Deprecation``/``Sunset``/``Link`` headers (see
``mcp_server.views._apply_legacy_path_deprecation``). Do not add a second mount
or point new configs at ``/api/v1/mcp/``.

Reference:
  docs/se/L1/Gesamtsystem/L2/McpServerSystem/L2_McpServerSystem_Architecture.md
  COMP-MC-001 ProtocolHandler — REQ-L2-MC-005
"""
from django.urls import path

from mcp_server.views import McpHttpTransportView, McpMessagesView, McpSseTransportView

urlpatterns = [
    # HTTP transport (IF-MC-EXT-IN-001 over HTTP)
    path("", McpHttpTransportView.as_view(), name="mcp-http"),
    # SSE transport (IF-MC-EXT-IN-001 over SSE)
    path("sse/", McpSseTransportView.as_view(), name="mcp-sse"),
    path("sse", McpSseTransportView.as_view(), name="mcp-sse-no-slash"),
    # SSE message endpoint
    path("messages/", McpMessagesView.as_view(), name="mcp-messages"),
]
