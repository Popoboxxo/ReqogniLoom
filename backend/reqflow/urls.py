"""
ReqFlow URL configuration.

ARCH-L1-002 RestApiAdapter: All API routes are registered under /api/v1/.
ARCH-L1-003 McpServer: MCP transport endpoint registered under /mcp/.
OpenAPI schema: served via drf-spectacular at /api/schema/.

TODO(ARCH-L1-002): Register domain-specific API routers once rest_api app
  implements ViewSets (requirements, architecture, tests, baselines, etc.).
TODO(ARCH-L1-003): Register MCP transport view once mcp_server app is implemented.
"""
from __future__ import annotations

from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

from reqflow.health import HealthView
from reqflow.version import VersionView

urlpatterns = [
    # Health check endpoint (REQ-063) — for container readiness probes
    path("health/", HealthView.as_view(), name="health"),
    # Deployed build/version metadata — public, precedes the rest_api include
    # so it can never be shadowed by a future "version/" route there.
    path("api/v1/version/", VersionView.as_view(), name="version"),
    # Django admin
    path("admin/", admin.site.urls),
    # OpenAPI schema (drf-spectacular)
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "api/schema/swagger-ui/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
    path(
        "api/schema/redoc/",
        SpectacularRedocView.as_view(url_name="schema"),
        name="redoc",
    ),
    # REST API v1 — ARCH-L1-002
    # TODO(ARCH-L1-002): include("rest_api.urls") once implemented
    path("api/v1/", include("rest_api.urls")),
    # MCP transport — ARCH-L1-003
    # TODO(ARCH-L1-003): include("mcp_server.urls") once implemented
    path("api/v1/mcp/", include("mcp_server.urls")),
    path("mcp/", include("mcp_server.urls")),
]
