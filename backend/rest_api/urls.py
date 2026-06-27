"""
ARCH-L1-002 RestApiAdapter — URL routing (COMP-RA-001 + COMP-RA-005).

leaf_id : COMP-RA-001 (router wiring)
req_id  : REQ-L2-RA-001 (CRUD endpoints), REQ-L2-RA-002 (OpenAPI schema)
          REQ-L3-RA001-001 (CRUD routing for all 7 entities)

Registers:
  /api/v1/artifacts/          ArtifactViewSet
  /api/v1/requirements/       RequirementViewSet
  /api/v1/architecture/       ArchitectureElementViewSet
  /api/v1/testcases/          TestCaseViewSet
  /api/v1/tracelinks/         TraceLinkViewSet
  /api/v1/baselines/          BaselineViewSet  (preset-gated)
  /api/v1/workflows/          WorkflowDefinitionViewSet
  /api/v1/workspaces/         WorkspaceViewSet (list + retrieve, REQ-L1-017)
  /api/v1/adrs/               AdrViewSet (REQ-L1-029)
  /api/v1/risks/              RiskViewSet (REQ-L1-029)
  /api/v1/issues/             IssueViewSet (REQ-L1-029)

Schema endpoints (served at project-level via drf-spectacular):
  /api/v1/schema/             SpectacularAPIView
  /api/v1/schema/swagger-ui/  SpectacularSwaggerView

Reference: docs/se/L1/Gesamtsystem/L2/RestApiAdapterSystem/
  L2_RestApiAdapterSystem_Architecture.md
"""
from __future__ import annotations

from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.routers import DefaultRouter

from rest_api.api_key_views import ApiKeyViewSet
from rest_api.auth_views import LoginView, MeView
from rest_api.diagram_views import DiagramViewSet
from rest_api.icd_views import IcdViewSet
from rest_api.metrics_views import MetricsViewSet
from rest_api.views import (
    AdrViewSet,
    ArtifactViewSet,
    ArchitectureElementViewSet,
    BaselineViewSet,
    IssueViewSet,
    RequirementHistoryView,
    RequirementViewSet,
    RiskViewSet,
    SearchViewSet,
    TestCaseViewSet,
    TraceLinkViewSet,
    WorkflowDefinitionViewSet,
    WorkspaceViewSet,
)

# ---------------------------------------------------------------------------
# DRF DefaultRouter — registers all 7 entity ViewSets (REQ-L3-RA001-001)
# ---------------------------------------------------------------------------

router = DefaultRouter(trailing_slash=True)
router.register(r"artifacts", ArtifactViewSet, basename="artifact")
router.register(r"requirements", RequirementViewSet, basename="requirement")
router.register(r"architecture", ArchitectureElementViewSet, basename="architecture")
router.register(r"testcases", TestCaseViewSet, basename="testcase")
router.register(r"tracelinks", TraceLinkViewSet, basename="tracelink")
router.register(r"baselines", BaselineViewSet, basename="baseline")
router.register(r"workflows", WorkflowDefinitionViewSet, basename="workflow")
router.register(r"workspaces", WorkspaceViewSet, basename="workspace")
router.register(r"adrs", AdrViewSet, basename="adr")
router.register(r"risks", RiskViewSet, basename="risk")
router.register(r"issues", IssueViewSet, basename="issue")
router.register(r"search", SearchViewSet, basename="search")
router.register(r"api-keys", ApiKeyViewSet, basename="api-key")
router.register(r"diagrams", DiagramViewSet, basename="diagram")
router.register(r"icds", IcdViewSet, basename="icd")
router.register(r"metrics", MetricsViewSet, basename="metrics")

# ---------------------------------------------------------------------------
# URL patterns
# /api/v1/ is the mount point (defined in reqflow/urls.py)
# Schema endpoints bypass auth (REQ-L3-RA005-001 AC, REQ-L3-RA003-001 AC)
# ---------------------------------------------------------------------------

urlpatterns = [
    # Password login (REQ-L1-010) — public token exchange + authenticated bootstrap.
    # auth/login/ is PUBLIC (AllowAny, no auth); auth/me/ requires a Bearer token.
    path("auth/login/", LoginView.as_view(), name="api-v1-auth-login"),
    path("auth/me/", MeView.as_view(), name="api-v1-auth-me"),
    # Requirement audit-trail (REQ-L0-011) — must precede router.urls to avoid
    # being swallowed by the router's requirements/<pk>/ catch-all pattern.
    path(
        "requirements/<uuid:pk>/history/",
        RequirementHistoryView.as_view(),
        name="requirement-history",
    ),
    # CRUD endpoints — all 7 domain entities
    path("", include(router.urls)),
    # OpenAPI schema — accessible without auth (REQ-L2-RA-002, REQ-L3-RA005-001)
    path(
        "schema/",
        SpectacularAPIView.as_view(),
        name="api-v1-schema",
    ),
    # Swagger UI — accessible without auth (REQ-L2-RA-002, REQ-L3-RA005-002)
    path(
        "schema/swagger-ui/",
        SpectacularSwaggerView.as_view(url_name="api-v1-schema"),
        name="api-v1-swagger-ui",
    ),
]
