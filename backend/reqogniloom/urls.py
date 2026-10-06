"""
ReqFlow URL configuration.

ARCH-L1-002 RestApiAdapter: All API routes are registered under /api/v1/.
ARCH-L1-003 McpServer: MCP transport endpoint registered under /mcp/.
OpenAPI schema: served via drf-spectacular at /api/schema/ (YAML) and
/openapi.json (JSON; alias /api/openapi.json).

TODO(ARCH-L1-002): Register domain-specific API routers once rest_api app
  implements ViewSets (requirements, architecture, tests, baselines, etc.).
TODO(ARCH-L1-003): Register MCP transport view once mcp_server app is implemented.
"""
from __future__ import annotations

from django.contrib import admin
from django.urls import include, path, re_path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularJSONAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

from reqogniloom.health import (
    HealthAliasView,
    HealthLivenessView,
    HealthReadinessView,
)
from reqogniloom.version import VersionView
from rest_api.not_found import api_not_found

urlpatterns = [
    # Health contract (ADR-010, REQ-060/REQ-063). Explicitly both the trailing
    # and non-trailing forms: a 301 redirect (Django's APPEND_SLASH) would let
    # `curl -f` read a probe as green, so the probes must answer directly.
    # /health/live  — liveness, always 200, no dependency probe.
    path("health/live", HealthLivenessView.as_view(), name="health-live"),
    path("health/live/", HealthLivenessView.as_view(), name="health-live-slash"),
    # /health/ready — fail-closed readiness (503 on a mandatory dependency).
    path("health/ready", HealthReadinessView.as_view(), name="health-ready"),
    path("health/ready/", HealthReadinessView.as_view(), name="health-ready-slash"),
    # /health/ — deprecated alias for /health/ready (ADR-010 §3).
    path("health/", HealthAliasView.as_view(), name="health"),
    # Deployed build/version metadata — public, precedes the rest_api include
    # so it can never be shadowed by a future "version/" route there.
    path("api/v1/version/", VersionView.as_view(), name="version"),
    # Django admin
    path("admin/", admin.site.urls),
    # OpenAPI schema (drf-spectacular). Public entry points (#1177):
    #   /openapi.json      — canonical machine-readable JSON document; SDK
    #                        generators that cannot consume YAML use this.
    #   /api/openapi.json  — alias matching the path the auth middleware already
    #                        exempts (auth_tenancy.middleware.EXEMPT_PATH_PREFIXES)
    #                        and the SE requirement text names.
    #   /api/schema/       — YAML by default, JSON via Accept (kept unchanged).
    #   /api/schema        — no-slash alias: APPEND_SLASH is disabled (CR-03), so
    #                        without this the bare path 404s instead of redirecting.
    path("openapi.json", SpectacularJSONAPIView.as_view(), name="openapi-json"),
    path(
        "api/openapi.json",
        SpectacularJSONAPIView.as_view(),
        name="api-openapi-json",
    ),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/schema", SpectacularAPIView.as_view(), name="schema-noslash"),
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
    # JSON 404 for every unclaimed /api/v1/ path (issue #460, finding 1).
    # MUST stay last: Django matches top-to-bottom, so this only runs once
    # every real route above — including the two mcp_server includes, which
    # is why the fallback cannot live inside rest_api/urls.py — has declined
    # the path. Scoped to /api/v1/ so /admin/, /mcp/, /api/schema/ and static
    # paths keep Django's HTML 404.
    re_path(r"^api/v1/", api_not_found),
]

# Second half of the same fix: the catch-all above only sees *routing* misses.
# An Http404 raised inside a view — PresetGateMixin._guard_preset does exactly
# that when a workspace's preset hides an endpoint — bypasses the URLconf and
# lands in Django's core handler, which rendered HTML. This keeps that path on
# the JSON envelope for /api/v1/ and delegates every other prefix to Django's
# default. Ignored while DEBUG=True (Django shows its technical 404 instead),
# which is why the catch-all route above is still needed.
handler404 = "rest_api.not_found.api_aware_page_not_found"
