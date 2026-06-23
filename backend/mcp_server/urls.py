"""
ARCH-L1-003 McpServer — URL routing.

TODO(COMP-MCP-003): Register MCP transport views:
  - path('', McpHttpTransportView.as_view())  for HTTP transport
  - SSE transport endpoint if applicable

Reference: docs/se/L1/Gesamtsystem/L2/McpServerSystem/L2_McpServerSystem_Architecture.md
"""
from django.urls import path

urlpatterns: list = []
