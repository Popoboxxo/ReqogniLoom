"""
ARCH-L1-003 McpServer — URL routing.

Registers HTTP and SSE MCP transport endpoints (REQ-L2-MC-005).

  POST /mcp/       — HTTP transport (JSON-RPC 2.0 request/response)
  POST /mcp/sse/   — SSE transport (single-event response)
  GET  /mcp/       — Server info / health check

Reference:
  docs/se/L1/Gesamtsystem/L2/McpServerSystem/L2_McpServerSystem_Architecture.md
  COMP-MC-001 ProtocolHandler — REQ-L2-MC-005
"""
from django.urls import path

from mcp_server.views import McpHttpTransportView, McpSseTransportView

urlpatterns = [
    # HTTP transport (IF-MC-EXT-IN-001 over HTTP)
    path("", McpHttpTransportView.as_view(), name="mcp-http"),
    # SSE transport (IF-MC-EXT-IN-001 over SSE)
    path("sse/", McpSseTransportView.as_view(), name="mcp-sse"),
    path("sse", McpSseTransportView.as_view(), name="mcp-sse-no-slash"),
]
