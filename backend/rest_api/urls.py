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
  /api/v1/tracelinks/         TraceLinkViewSet (legacy path, kept for compat)
  /api/v1/trace-links/        TraceLinkViewSet (kebab-case alias, fix #233)
  /api/v1/baselines/          BaselineViewSet  (preset-gated)
  /api/v1/workspaces/{id}/baselines/  BaselineViewSet list/create, workspace-scoped (issue #49)
  /api/v1/workflows/          WorkflowDefinitionViewSet
  /api/v1/workspaces/         WorkspaceViewSet (list + retrieve, REQ-L1-017)
  /api/v1/adrs/               AdrViewSet (REQ-L1-029)
  /api/v1/risks/              RiskViewSet (REQ-L1-029)
  /api/v1/goals/               GoalViewSet (REQ-L2-TE-020)
  /api/v1/main-goals/          MainGoalViewSet (REQ-L2-TE-020)
  /api/v1/issues/             IssueViewSet (REQ-L1-029)
  /api/v1/admin/backups/      BackupListCreateView (REQ-L1-046)
  /api/v1/admin/restore/      AdminRestoreView   (REQ-L1-046)
  /api/v1/admin/health/       SystemHealthView   (system health dashboard)
  /api/v1/users/me/preferences/ UserPreferenceView (REQ-L1-027)

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

from auth_tenancy.rest_item_permission import ItemPermissionViewSet
from auth_tenancy.rest_workspace_members import WorkspaceMembersView
from admin_ops.health_rest import SystemHealthView
from rest_api.audit_views import (
    WorkspaceAuditAiReviewView,
    WorkspaceAuditRemediateView,
    WorkspaceAuditView,
)
from rest_api.traceability_suggest_views import WorkspaceTraceabilitySuggestLinksView
from rest_api.architecture_decompose_views import (
    WorkspaceArchitectureDecomposeCommitView,
    WorkspaceArchitectureDecomposeView,
)
from admin_ops.rest import AdminRestoreView, BackupListCreateView
from baseline.urls import urlpatterns as baseline_urlpatterns
from rest_api.api_key_views import ApiKeyViewSet
from rest_api.auth_views import LoginView, LogoutView, MeView, RefreshView
from rest_api.diagram_canvas_views import (
    CanvasStrokeView,
    MermaidPreviewView,
    MermaidSourceView,
)
from rest_api.diagram_views import DiagramViewSet
from rest_api.icd_views import IcdViewSet
from rest_api.interview_views import InterviewViewSet
from rest_api.metrics_views import MetricsViewSet
from rest_api.preference_views import UserPreferenceView
from rest_api.prompt_variable_views import (
    PromptVariableDetailView,
    PromptVariableListView,
)
from rest_api.settings_views import (
    LlmSettingsView,
    PromptTemplateResetView,
    PromptTemplateSlotDetailView,
    PromptTemplateSlotListView,
    PromptTemplateView,
    ReviewPolicyView,
)
from rest_api.global_default_views import (
    EnforcementFlipView,
    EnforcementStatusView,
    GlobalPermissionDefinitionView,
    GlobalWorkflowDefinitionDetailView,
    GlobalWorkflowDefinitionListView,
    GlobalWorkflowInitializeView,
    GlobalWorkflowStateDetailView,
    GlobalWorkflowStatesView,
    GlobalWorkflowTransitionDetailView,
    GlobalWorkflowTransitionsView,
    PermissionMismatchListView,
    WorkspacePermissionDefinitionView,
    WorkspacePermissionResetView,
)
from rest_api.views import (
    AdrViewSet,
    ArchitectureElementViewSet,
    ArtifactCustomFieldValuesView,
    ArtifactViewSet,
    AttributeSchemaView,
    AttributeVisibilityConfigViewSet,
    BaselineViewSet,
    BundleCompressionStatusView,
    ChangeRequestViewSet,
    CustomFieldDefinitionViewSet,
    CsvExportView,
    CsvImportView,
    GlossaryTermViewSet,
    GoalViewSet,
    IssueViewSet,
    MainGoalViewSet,
    ReqifExportView,
    ReqifImportView,
    RequirementHistoryView,
    RequirementViewSet,
    StakeholderNeedViewSet,
    RiskViewSet,
    SearchViewSet,
    TestCaseViewSet,
    TestRunViewSet,
    TraceabilityViewSet,
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
router.register(r"needs", StakeholderNeedViewSet, basename="need")
router.register(r"architecture", ArchitectureElementViewSet, basename="architecture")
router.register(r"testcases", TestCaseViewSet, basename="testcase")
router.register(r"tracelinks", TraceLinkViewSet, basename="tracelink")
# fix #233: "tracelinks" predates the kebab-case convention used by every
# other multi-word route (main-goals, change-requests, test-runs, ...) and
# POST /api/v1/trace-links/ 404ed with an HTML page instead of a JSON error.
# Register the same ViewSet under the conventional path too; "tracelinks" is
# kept for backward compatibility (frontend/src/api/tracelinks.ts and docs
# reference it extensively).
router.register(r"trace-links", TraceLinkViewSet, basename="trace-link")
router.register(r"traceability", TraceabilityViewSet, basename="traceability")
router.register(r"baselines", BaselineViewSet, basename="baseline")
router.register(r"workflows", WorkflowDefinitionViewSet, basename="workflow")
router.register(r"workspaces", WorkspaceViewSet, basename="workspace")
router.register(r"adrs", AdrViewSet, basename="adr")
router.register(r"risks", RiskViewSet, basename="risk")
router.register(r"goals", GoalViewSet, basename="goal")
router.register(r"main-goals", MainGoalViewSet, basename="main-goal")
router.register(r"issues", IssueViewSet, basename="issue")
router.register(r"change-requests", ChangeRequestViewSet, basename="change-request")
router.register(r"test-runs", TestRunViewSet, basename="test-run")
router.register(r"search", SearchViewSet, basename="search")
router.register(r"api-keys", ApiKeyViewSet, basename="api-key")
router.register(r"diagrams", DiagramViewSet, basename="diagram")
router.register(r"icds", IcdViewSet, basename="icd")
router.register(r"metrics", MetricsViewSet, basename="metrics")
router.register(r"attribute-visibility-configs", AttributeVisibilityConfigViewSet, basename="attribute-visibility-config")
router.register(r"glossary", GlossaryTermViewSet, basename="glossary")
router.register(r"interviews", InterviewViewSet, basename="interview")

# ---------------------------------------------------------------------------
# URL patterns
# /api/v1/ is the mount point (defined in reqogniloom/urls.py)
# Schema endpoints bypass auth (REQ-L3-RA005-001 AC, REQ-L3-RA003-001 AC)
# ---------------------------------------------------------------------------

urlpatterns = [
    # Password login (REQ-L1-010) — public token exchange + authenticated bootstrap.
    # auth/login/ is PUBLIC (AllowAny, no auth); auth/me/ requires a Bearer token.
    path("auth/login/", LoginView.as_view(), name="api-v1-auth-login"),
    # Logout (REQ-052) — clears the httpOnly access cookie; requires auth + CSRF.
    path("auth/logout/", LogoutView.as_view(), name="api-v1-auth-logout"),
    # Silent token refresh (GitHub #135) — public, identity via the refresh
    # cookie only; mints a new access cookie so a mid-session expiry does not
    # hard-log the user out.
    path("auth/refresh/", RefreshView.as_view(), name="api-v1-auth-refresh"),
    path("auth/me/", MeView.as_view(), name="api-v1-auth-me"),
    # Baseline scope-preview + other custom baseline views (REQ-011) — must precede
    # router.urls to avoid being swallowed by the router's baselines/<pk>/ pattern.
    path("baselines/", include(baseline_urlpatterns)),
    # Requirement audit-trail (REQ-L0-011) — must precede router.urls to avoid
    # being swallowed by the router's requirements/<pk>/ catch-all pattern.
    path(
        "requirements/<uuid:pk>/history/",
        RequirementHistoryView.as_view(),
        name="requirement-history",
    ),
    # CSV bulk import (REQ-L0-013, REQ-L2-AS-014) — workspace-scoped.
    path(
        "workspaces/<uuid:pk>/import/csv/",
        CsvImportView.as_view(),
        name="workspace-csv-import",
    ),
    # CSV export (REQ-L3-EXP-002, C7 frontend-feedback Cluster C) — workspace-scoped.
    path(
        "workspaces/<uuid:pk>/export/csv/",
        CsvExportView.as_view(),
        name="workspace-csv-export",
    ),
    # ReqIF 1.2 export (REQ-146, COMP-AS-008) — workspace-scoped.
    path(
        "workspaces/<uuid:pk>/export/reqif/",
        ReqifExportView.as_view(),
        name="workspace-reqif-export",
    ),
    # ReqIF 1.2 import (REQ-147, COMP-AS-008b) — workspace-scoped.
    path(
        "workspaces/<uuid:pk>/import/reqif/",
        ReqifImportView.as_view(),
        name="workspace-reqif-import",
    ),
    # Needs routing by workspace
    path(
        "workspaces/<uuid:workspace_pk>/needs/",
        StakeholderNeedViewSet.as_view({"get": "list", "post": "create"}),
        name="workspace-needs",
    ),
    # Baselines routing by workspace (issue #49) — mirrors the Needs pattern
    # above. The flat "baselines/" route (registered via the router) is kept
    # for backward compatibility (frontend/MCP callers use ?workspace_id=).
    path(
        "workspaces/<uuid:workspace_pk>/baselines/",
        BaselineViewSet.as_view({"get": "list", "post": "create"}),
        name="workspace-baselines",
    ),
    # Custom field definitions (REQ-016) — workspace-scoped list/create.
    path(
        "workspaces/<uuid:workspace_pk>/custom-field-definitions/",
        CustomFieldDefinitionViewSet.as_view({"get": "list", "post": "create"}),
        name="workspace-custom-field-definitions",
    ),
    # Custom field definition detail (REQ-016) — update/delete by id (admin-only).
    path(
        "custom-field-definitions/<uuid:pk>/",
        CustomFieldDefinitionViewSet.as_view(
            {"patch": "partial_update", "delete": "destroy"}
        ),
        name="custom-field-definition-detail",
    ),
    # Custom field values (REQ-016) — read/upsert values for one artifact.
    path(
        "artifacts/<uuid:pk>/custom-field-values/",
        ArtifactCustomFieldValuesView.as_view(),
        name="artifact-custom-field-values",
    ),
    # ItemPermission CRUD (REQ-L1-039, COMP-AT-005) — workspace-scoped, admin-only.
    path(
        "workspaces/<uuid:workspace_id>/permissions/",
        ItemPermissionViewSet.as_view(),
        name="workspace-item-permissions",
    ),
    # Workspace member directory (REQ-014, COMP-AT-002) — feeds the Item-Permission
    # user picker; readable by any active member of the workspace.
    path(
        "workspaces/<uuid:workspace_id>/members/",
        WorkspaceMembersView.as_view(),
        name="workspace-members",
    ),
    # Disaster Recovery (REQ-L1-046) — admin-only.
    # /admin/backups/  -> GET list, POST create
    # /admin/restore/  -> POST restore (captcha "RESTORE")
    path(
        "admin/backups/",
        BackupListCreateView.as_view(),
        name="admin-backups",
    ),
    path(
        "admin/restore/",
        AdminRestoreView.as_view(),
        name="admin-restore",
    ),
    # System health dashboard — admin-only, non-blocking infra snapshot.
    # /admin/health/  -> GET components status + recent audit-log entries
    path(
        "admin/health/",
        SystemHealthView.as_view(),
        name="admin-health",
    ),
    # User workspace preferences (REQ-L1-027) — per-user visibility overrides.
    path(
        "users/me/preferences/",
        UserPreferenceView.as_view(),
        name="user-preferences",
    ),
    # LLM configuration (REQ-L2-LLM-001) — tenant-scoped singleton, admin-only.
    path(
        "llm-settings/",
        LlmSettingsView.as_view(),
        name="llm-settings",
    ),
    # LLM prompt templates (REQ-L2-PT-001) — tenant-scoped singleton, admin-only.
    # reset/ must precede the singleton route so it is not shadowed.
    path(
        "prompt-templates/reset/",
        PromptTemplateResetView.as_view(),
        name="prompt-templates-reset",
    ),
    # Slot API (issue #119) — all 7 slots + per-workspace overrides. Must
    # precede the singleton route for the same shadowing reason as reset/.
    path(
        "prompt-templates/slots/",
        PromptTemplateSlotListView.as_view(),
        name="prompt-template-slots",
    ),
    path(
        "prompt-templates/slots/<str:name>/",
        PromptTemplateSlotDetailView.as_view(),
        name="prompt-template-slot-detail",
    ),
    path(
        "prompt-templates/",
        PromptTemplateView.as_view(),
        name="prompt-templates",
    ),
    # Prompt variable catalog (spec §3.1) — admin-only, same scope semantics
    # as the prompt-template slot API above.
    path(
        "prompt-variables/",
        PromptVariableListView.as_view(),
        name="prompt-variables",
    ),
    path(
        "prompt-variables/<str:name>/",
        PromptVariableDetailView.as_view(),
        name="prompt-variable-detail",
    ),
    # Per-workspace AI-derivation review policy (Phase 5, REQ-L2-RV-001) —
    # admin-only, mirrors the workspace-scoped permission-definition pattern.
    path(
        "workspaces/<uuid:workspace_id>/review-policy/",
        ReviewPolicyView.as_view(),
        name="workspace-review-policy",
    ),
    # -- Global workflow defaults (REQ-178) — tenant-wide, per item_type+preset.
    # More specific sub-paths precede the {item_type}/{preset}/ detail route.
    path(
        "workflow-defaults/",
        GlobalWorkflowDefinitionListView.as_view(),
        name="workflow-defaults-list",
    ),
    path(
        "workflow-defaults/<str:item_type>/<str:preset>/initialize/",
        GlobalWorkflowInitializeView.as_view(),
        name="workflow-defaults-initialize",
    ),
    path(
        "workflow-defaults/<str:item_type>/<str:preset>/states/<str:state_id>/",
        GlobalWorkflowStateDetailView.as_view(),
        name="workflow-defaults-state-detail",
    ),
    path(
        "workflow-defaults/<str:item_type>/<str:preset>/states/",
        GlobalWorkflowStatesView.as_view(),
        name="workflow-defaults-states",
    ),
    path(
        "workflow-defaults/<str:item_type>/<str:preset>/transitions/<str:transition_id>/",
        GlobalWorkflowTransitionDetailView.as_view(),
        name="workflow-defaults-transition-detail",
    ),
    path(
        "workflow-defaults/<str:item_type>/<str:preset>/transitions/",
        GlobalWorkflowTransitionsView.as_view(),
        name="workflow-defaults-transitions",
    ),
    path(
        "workflow-defaults/<str:item_type>/<str:preset>/",
        GlobalWorkflowDefinitionDetailView.as_view(),
        name="workflow-defaults-detail",
    ),
    # -- Global permission definition (REQ-181/186/187) — tenant singleton.
    # enforcement sub-routes precede the singleton route so they are not shadowed.
    path(
        "permission-defaults/enforcement/flip/",
        EnforcementFlipView.as_view(),
        name="permission-defaults-enforcement-flip",
    ),
    path(
        "permission-defaults/enforcement/",
        EnforcementStatusView.as_view(),
        name="permission-defaults-enforcement",
    ),
    path(
        "permission-defaults/",
        GlobalPermissionDefinitionView.as_view(),
        name="permission-defaults",
    ),
    # -- Workspace permission definition (REQ-182/183) — matrix override + reset.
    path(
        "workspaces/<uuid:workspace_id>/permission-definition/reset/",
        WorkspacePermissionResetView.as_view(),
        name="workspace-permission-definition-reset",
    ),
    path(
        "workspaces/<uuid:workspace_id>/permission-definition/",
        WorkspacePermissionDefinitionView.as_view(),
        name="workspace-permission-definition",
    ),
    # -- Permission decision mismatch log (REQ-187) — read-only, append-only.
    path(
        "permission-mismatches/",
        PermissionMismatchListView.as_view(),
        name="permission-mismatches",
    ),
    # SE-Auditor (SysEng 2.0 Phase 3) — workspace-scoped audit dashboard.
    # remediate/ and ai-review/ must precede the audit/ run route so neither
    # is shadowed.
    path(
        "workspaces/<uuid:workspace_id>/audit/remediate/",
        WorkspaceAuditRemediateView.as_view(),
        name="workspace-audit-remediate",
    ),
    # SysEng 2.0 N8 (audit.ai_review, Phase 4b) — LLM refactoring packages.
    path(
        "workspaces/<uuid:workspace_id>/audit/ai-review/",
        WorkspaceAuditAiReviewView.as_view(),
        name="workspace-audit-ai-review",
    ),
    path(
        "workspaces/<uuid:workspace_id>/audit/",
        WorkspaceAuditView.as_view(),
        name="workspace-audit",
    ),
    # SysEng 2.0 N3 (traceability.suggest_links, Phase 4b, first stage) —
    # rank plausible link targets for SE-Auditor findings; no pgvector.
    path(
        "workspaces/<uuid:workspace_id>/traceability/suggest-links/",
        WorkspaceTraceabilitySuggestLinksView.as_view(),
        name="workspace-traceability-suggest-links",
    ),
    # SysEng 2.0 N1 (architecture.decompose) — Draft-Staging copilot.
    # commit/ must precede the generate route so it is not shadowed.
    path(
        "workspaces/<uuid:workspace_id>/architecture/decompose/commit/",
        WorkspaceArchitectureDecomposeCommitView.as_view(),
        name="workspace-architecture-decompose-commit",
    ),
    path(
        "workspaces/<uuid:workspace_id>/architecture/decompose/",
        WorkspaceArchitectureDecomposeView.as_view(),
        name="workspace-architecture-decompose",
    ),
    # Canvas strokes (REQ-L1-056, IF-L1-058/060) — diagram sub-resource.
    path(
        "diagrams/<uuid:pk>/canvas-strokes/",
        CanvasStrokeView.as_view(),
        name="diagram-canvas-strokes",
    ),
    # Mermaid source (REQ-L1-057, IF-L1-059) — diagram sub-resource.
    path(
        "diagrams/<uuid:pk>/mermaid-source/",
        MermaidSourceView.as_view(),
        name="diagram-mermaid-source",
    ),
    # Mermaid preview (REQ-L1-057, IF-L1-061) — diagram sub-resource.
    path(
        "diagrams/<uuid:pk>/mermaid-preview/",
        MermaidPreviewView.as_view(),
        name="diagram-mermaid-preview",
    ),
    # Attribute schema discovery (Requirement Bundle Export, Plan 1 Task 5) —
    # lists known attribute names + visibility per entity type.
    path(
        "attribute-schema/",
        AttributeSchemaView.as_view(),
        name="api-v1-attribute-schema",
    ),
    # Bundle compression async polling (Requirement Bundle Export, Plan 2
    # Task 4) — status of a requirement-bundle/?mode=compressed&async=true
    # Celery dispatch.
    path(
        "bundle-compression-status/<str:task_id>/",
        BundleCompressionStatusView.as_view(),
        name="api-v1-bundle-compression-status",
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
