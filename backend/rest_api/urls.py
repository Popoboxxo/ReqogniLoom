"""
ARCH-L1-002 RestApiAdapter — URL routing (COMP-RA-001 + COMP-RA-005).

leaf_id : COMP-RA-001 (router wiring)
req_id  : REQ-L2-RA-001 (CRUD endpoints), REQ-L2-RA-002 (OpenAPI schema)
          REQ-L3-RA001-001 (CRUD routing for all 7 entities)

Registers:
  /api/v1/artifacts/          ArtifactViewSet
  /api/v1/requirements/       RequirementViewSet
  /api/v1/architecture/       ArchitectureElementViewSet
  /api/v1/test-cases/         TestCaseViewSet (canonical kebab-case, #1177)
  /api/v1/testcases/          TestCaseViewSet (legacy un-hyphenated alias, #1177)
  /api/v1/tracelinks/         TraceLinkViewSet (legacy path, kept for compat)
  /api/v1/trace-links/        TraceLinkViewSet (kebab-case alias, fix #233)
  /api/v1/reviews/            pending-review queue collection root (#1177, #1089)
  /api/v1/reviews/pending/    pending-review queue (flat, ?workspace_id=)
  /api/v1/baselines/          BaselineViewSet  (preset-gated)
  /api/v1/workspaces/{id}/baselines/  BaselineViewSet list/create, workspace-scoped (issue #49)
  /api/v1/workflows/          WorkflowDefinitionViewSet
  /api/v1/workspaces/         WorkspaceViewSet (list + retrieve, REQ-L1-017)
  /api/v1/adrs/               AdrViewSet (REQ-L1-029)
  /api/v1/adrs/derive-from-decision/  AdrViewSet.derive_from_decision (#1358 REST parity)
  /api/v1/risks/              RiskViewSet (REQ-L1-029)
  /api/v1/architecture/{pk}/derive-risks/  ArchitectureElementViewSet.derive_risks (#1358)
  /api/v1/glossary/derive/    GlossaryTermViewSet.derive (#1358 REST parity)
  /api/v1/goals/               GoalViewSet (REQ-L2-TE-020)
  /api/v1/main-goals/          MainGoalViewSet (REQ-L2-TE-020)
  /api/v1/issues/             IssueViewSet (REQ-L1-029)
  /api/v1/admin/backups/      BackupListCreateView (REQ-L1-046)
  /api/v1/admin/restore/      AdminRestoreView   (REQ-L1-046)
  /api/v1/admin/health/       SystemHealthView   (system health dashboard)
  /api/v1/users/me/preferences/ UserPreferenceView (REQ-L1-027)
  /api/v1/users/me/display-preferences/ DisplayPreferenceView (Issue #1096)

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

from admin_ops.banner_rest import GlobalBannerView, PublicLoginBannerView, WorkspaceBannerView
from admin_ops.health_rest import SystemHealthView
from admin_ops.rate_limit_rest import GlobalRateLimitsView, RateLimitsView
from admin_ops.rest import AdminRestoreView, BackupListCreateView
from admin_ops.theme_rest import (
    TenantThemeDefaultView,
    ThemePaletteDetailView,
    ThemePaletteExportView,
    ThemePaletteListView,
    UserThemePreferenceView,
)
from auth_tenancy.rest_item_permission import ItemPermissionViewSet
from auth_tenancy.rest_workspace_members import (
    WorkspaceMemberRoleTransitionView,
    WorkspaceMembersView,
)
from baseline.urls import urlpatterns as baseline_urlpatterns
from memory.memory_rest import (
    ArtifactMemoryDigestView,
    ArtifactMemoryView,
    MemoryEntryDetailView,
    MemoryEntryPromoteView,
    MemorySelfServiceSettingsView,
    MemorySelfServiceView,
    SystemMemoryEntriesExportView,
    SystemMemoryEntriesListView,
    SystemMemoryProjectionView,
    SystemMemorySettingsResetView,
    SystemMemorySettingsView,
    SystemMemoryWorkspaceDeleteView,
    SystemMemoryWorkspaceOverviewView,
    WorkspaceMemoryAskView,
    WorkspaceMemoryDigestView,
    WorkspaceMemoryEntriesView,
    WorkspaceMemorySearchView,
    WorkspaceMemorySessionSummariesView,
    WorkspaceMemorySettingsView,
)
from rest_api.api_key_views import ApiKeyViewSet
from rest_api.architecture_decompose_views import (
    WorkspaceArchitectureDecomposeCommitView,
    WorkspaceArchitectureDecomposeView,
)
from rest_api.attribute_catalog_views import (
    AttributeCatalogAddToDefinitionView,
    AttributeCatalogDeprecateView,
    AttributeCatalogDetailView,
    AttributeCatalogExportView,
    AttributeCatalogImportView,
    AttributeCatalogListView,
    AttributeCatalogSearchView,
)
from rest_api.attribute_definition_views import (
    AttributeDefaultsDetailView,
    AttributeDefaultsExportView,
    AttributeDefaultsImportView,
    AttributeDefaultsListView,
    AttributeDefaultsReorderView,
    AttributeUsageView,
    WorkspaceAttributeDefinitionExportView,
    WorkspaceAttributeDefinitionImportView,
    WorkspaceAttributeDefinitionReorderView,
    WorkspaceAttributeDefinitionResetView,
    WorkspaceAttributeDefinitionView,
)
from rest_api.attribute_migration_views import (
    AttributeMigrationApplyView,
    AttributeMigrationPlanView,
    AttributeMigrationRollbackView,
    AttributeMigrationRunDetailView,
    AttributeMigrationRunListView,
)
from rest_api.audit_views import (
    AuditRuleCatalogView,
    WorkspaceAuditAiReviewView,
    WorkspaceAuditRemediateView,
    WorkspaceAuditView,
    WorkspaceAuditWaiverView,
)
from rest_api.auth_views import (
    LoginMfaView,
    LoginView,
    LogoutView,
    MeView,
    RefreshView,
)
from rest_api.collaboration_views import (
    ArtifactCommentsView,
    CommentViewSet,
    NotificationViewSet,
)
from rest_api.create_form_config_views import (
    CreateFormConfigGlobalView,
    CreateFormConfigUserView,
    CreateFormConfigWorkspaceView,
)
from rest_api.diagram_canvas_views import (
    CanvasStrokeView,
    MermaidPreviewView,
    MermaidSourceView,
)
from rest_api.diagram_views import DiagramViewSet
from rest_api.display_preference_views import DisplayPreferenceView
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
from rest_api.icd_views import IcdViewSet
from rest_api.interview_views import InterviewViewSet
from rest_api.link_type_views import (
    LinkTypeDefaultsDetailView,
    LinkTypeDefaultsListView,
    WorkspaceLinkTypeDetailView,
    WorkspaceLinkTypeListView,
    WorkspaceLinkTypeResetView,
)
from rest_api.metrics_views import MetricsViewSet
from rest_api.mfa_views import (
    MfaConfirmView,
    MfaDisableView,
    MfaEnrollView,
    MfaRecoveryCodesRegenerateView,
    MfaStatusView,
)
from rest_api.notification_preference_views import NotificationPreferenceView
from rest_api.preference_value_views import (
    GlobalPreferenceLevelView,
    PreferenceRegistryView,
    UserEffectivePreferenceView,
    UserPreferenceLevelView,
    WorkspaceEffectivePreferenceView,
    WorkspacePreferenceLevelView,
)
from rest_api.preference_views import UserPreferenceView
from rest_api.prompt_variable_views import (
    PromptVariableDetailView,
    PromptVariableListView,
)
from rest_api.review_views import (
    ReviewsPendingView,
    WorkspaceReviewsPendingView,
)
from rest_api.quality_views import QualityAssessView, QualityHistoryView
from rest_api.settings_views import (
    ContextGraphRebuildView,
    ContextGraphSettingsView,
    LlmSettingsView,
    PromptTemplateResetView,
    PromptTemplateSlotDetailView,
    PromptTemplateSlotListView,
    PromptTemplateView,
    ReviewPolicyView,
)
from rest_api.suggestion_views import (
    SuggestionAcceptView,
    SuggestionListView,
    SuggestionRejectView,
)
from rest_api.traceability_suggest_views import (
    TraceabilitySuggestLinksStatusView,
    WorkspaceTraceabilitySuggestLinksView,
)
from rest_api.tree_display_config_views import (
    TreeDisplayConfigGlobalView,
    TreeDisplayConfigUserView,
    TreeDisplayConfigWorkspaceView,
)
from rest_api.user_management_views import UserViewSet
from rest_api.views import (
    AdrViewSet,
    ArchitectureElementViewSet,
    ArtifactViewSet,
    AttributeSchemaView,
    BaselineViewSet,
    BundleCompressionStatusView,
    ChangeRequestViewSet,
    ConsistencyStatusView,
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
    RiskViewSet,
    SearchViewSet,
    StakeholderNeedViewSet,
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
# fix #1177 (B4): kebab-case is the canonical multi-word spelling (see the
# trace-links alias below and main-goals/change-requests/test-runs). Register
# the canonical "test-cases" too; "testcases" stays for backward compatibility
# (frontend/src/api/testcases.ts and the rest of the legacy spellings).
router.register(r"test-cases", TestCaseViewSet, basename="test-case")
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
# #1177 alias: the un-hyphenated legacy spelling stays reachable alongside the
# canonical "main-goals" so no existing client breaks.
router.register(r"maingoals", MainGoalViewSet, basename="maingoal")
router.register(r"issues", IssueViewSet, basename="issue")
router.register(r"change-requests", ChangeRequestViewSet, basename="change-request")
# #1177 alias: canonical "change-requests" plus the legacy un-hyphenated form.
router.register(r"changerequests", ChangeRequestViewSet, basename="changerequest")
router.register(r"test-runs", TestRunViewSet, basename="test-run")
# #1177 alias: canonical "test-runs" plus the legacy un-hyphenated form.
router.register(r"testruns", TestRunViewSet, basename="testrun")
router.register(r"search", SearchViewSet, basename="search")
router.register(r"api-keys", ApiKeyViewSet, basename="api-key")
router.register(r"diagrams", DiagramViewSet, basename="diagram")
router.register(r"icds", IcdViewSet, basename="icd")
router.register(r"metrics", MetricsViewSet, basename="metrics")
router.register(r"glossary", GlossaryTermViewSet, basename="glossary")
router.register(r"interviews", InterviewViewSet, basename="interview")
# Comments (Menschen-im-System spec §4) — detail actions resolve/ and the
# default destroy; list/create hang off the artifact-nested route below.
router.register(r"comments", CommentViewSet, basename="comment")
# Notifications (Menschen-im-System spec §5) — the caller's own feed; no MCP
# counterpart by design.
router.register(r"notifications", NotificationViewSet, basename="notification")

# ---------------------------------------------------------------------------
# URL patterns
# /api/v1/ is the mount point (defined in reqogniloom/urls.py)
# Schema endpoints bypass auth (REQ-L3-RA005-001 AC, REQ-L3-RA003-001 AC)
# ---------------------------------------------------------------------------

urlpatterns = [
    # Password login (REQ-L1-010) — public token exchange + authenticated bootstrap.
    # auth/login/ is PUBLIC (AllowAny, no auth); auth/me/ requires a Bearer token.
    path("auth/login/", LoginView.as_view(), name="api-v1-auth-login"),
    # Second step of the two-step login (#1308, WP E3.4) — public, same
    # throttles as `auth/login/`; exchanges the signed challenge + TOTP/recovery
    # code for the session cookies.
    path(
        "auth/login/mfa/",
        LoginMfaView.as_view(),
        name="api-v1-auth-login-mfa",
    ),
    # Logout (REQ-052) — clears the httpOnly access cookie; requires auth + CSRF.
    path("auth/logout/", LogoutView.as_view(), name="api-v1-auth-logout"),
    # Second-factor management (#1308, Plan E / WP E3.6) — self-scoped to the
    # calling account. Writes are interactive-session only (an API key gets 403
    # MFA_REQUIRES_INTERACTIVE_SESSION); enroll/confirm also accept the signed
    # purpose=enroll challenge via the X-MFA-Challenge header.
    path(
        "auth/mfa/status/",
        MfaStatusView.as_view(),
        name="api-v1-auth-mfa-status",
    ),
    path(
        "auth/mfa/totp/enroll/",
        MfaEnrollView.as_view(),
        name="api-v1-auth-mfa-enroll",
    ),
    path(
        "auth/mfa/totp/confirm/",
        MfaConfirmView.as_view(),
        name="api-v1-auth-mfa-confirm",
    ),
    path(
        "auth/mfa/recovery-codes/regenerate/",
        MfaRecoveryCodesRegenerateView.as_view(),
        name="api-v1-auth-mfa-recovery-codes-regenerate",
    ),
    path(
        "auth/mfa/disable/",
        MfaDisableView.as_view(),
        name="api-v1-auth-mfa-disable",
    ),
    # Silent token refresh (GitHub #135) — public, identity via the refresh
    # cookie only; mints a new access cookie so a mid-session expiry does not
    # hard-log the user out.
    path("auth/refresh/", RefreshView.as_view(), name="api-v1-auth-refresh"),
    path("auth/me/", MeView.as_view(), name="api-v1-auth-me"),
    # System & Workspace Banners — public login-page banner (unauthenticated).
    path(
        "public/banners/login/",
        PublicLoginBannerView.as_view(),
        name="public-banner-login",
    ),
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
    # Workspace member role suspend/reactivate (multi-user management design
    # spec) — admin-guarded soft-suspend / reversal of a single role.
    path(
        "workspaces/<uuid:workspace_id>/members/<uuid:user_id>/suspend/",
        WorkspaceMemberRoleTransitionView.as_view(),
        {"action": "suspend"},
        name="workspace-member-suspend",
    ),
    path(
        "workspaces/<uuid:workspace_id>/members/<uuid:user_id>/reactivate/",
        WorkspaceMemberRoleTransitionView.as_view(),
        {"action": "reactivate"},
        name="workspace-member-reactivate",
    ),
    # Multi-user management (multi-user management design spec) — tenant-admin-guarded
    # user lifecycle CRUD + activation + tenant-admin role grant/revoke.
    path(
        "users/",
        UserViewSet.as_view({"get": "list", "post": "create"}),
        name="user-list-create",
    ),
    path(
        "users/<uuid:pk>/activate/",
        UserViewSet.as_view({"post": "activate"}),
        name="user-activate",
    ),
    path(
        "users/<uuid:pk>/deactivate/",
        UserViewSet.as_view({"post": "deactivate"}),
        name="user-deactivate",
    ),
    path(
        "users/<uuid:pk>/tenant-admin/",
        UserViewSet.as_view({"post": "tenant_admin", "delete": "tenant_admin"}),
        name="user-tenant-admin",
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
    # Runtime-configurable rate limits (GitHub #944).
    # /admin/rate-limits/global/ -> deployment-wide default; System-Admin only.
    # NOTE: registered before the tenant-scoped route so the more specific
    # path is unambiguously matched first.
    path(
        "admin/rate-limits/global/",
        GlobalRateLimitsView.as_view(),
        name="admin-rate-limits-global",
    ),
    # /admin/rate-limits/ -> GET any user, PUT/DELETE System-Admin only.
    path(
        "admin/rate-limits/",
        RateLimitsView.as_view(),
        name="admin-rate-limits",
    ),
    # System & Workspace Banners.
    # /admin/banners/global/  -> GET/PUT, System-Admin only
    path(
        "admin/banners/global/",
        GlobalBannerView.as_view(),
        name="admin-banner-global",
    ),
    path(
        "workspaces/<uuid:workspace_id>/banner/",
        WorkspaceBannerView.as_view(),
        name="workspace-banner",
    ),
    # Theme Presets.
    # /admin/theme-palettes/  -> GET any user; POST (import) System-Admin only
    path(
        "admin/theme-palettes/",
        ThemePaletteListView.as_view(),
        name="theme-palette-list",
    ),
    # /admin/theme-palettes/<key>/export/  -> GET any user
    # NOTE: export/ must precede the detail route so it is not shadowed.
    path(
        "admin/theme-palettes/<str:key>/export/",
        ThemePaletteExportView.as_view(),
        name="theme-palette-export",
    ),
    # /admin/theme-palettes/<key>/  -> DELETE System-Admin; system rows 403
    path(
        "admin/theme-palettes/<str:key>/",
        ThemePaletteDetailView.as_view(),
        name="theme-palette-detail",
    ),
    # User workspace preferences (REQ-L1-027) — per-user visibility overrides.
    path(
        "users/me/preferences/",
        UserPreferenceView.as_view(),
        name="user-preferences",
    ),
    # Notification delivery preferences (OD-1, 2026-09-15) — the caller's own
    # opt-out switches over the four notification triggers. Same self-service
    # shape as users/me/preferences/ directly above.
    path(
        "users/me/notification-preferences/",
        NotificationPreferenceView.as_view(),
        name="user-notification-preferences",
    ),
    # Display preferences (Issue #1096) — the caller's own UI display flags
    # (readable-id visibility). Same self-service shape as the two routes
    # directly above.
    path(
        "users/me/display-preferences/",
        DisplayPreferenceView.as_view(),
        name="user-display-preferences",
    ),
    # Tree-display configuration (Issue #1257) — the personal level of the
    # navigation tree's configurable field selection. Same self-service shape as
    # the display-preferences route directly above.
    path(
        "users/me/tree-display-config/",
        TreeDisplayConfigUserView.as_view(),
        name="user-tree-display-config",
    ),
    # Tree-display configuration (Issue #1257) — the tenant-wide default
    # (global) level. Read: any member; write: admin (service-enforced) plus the
    # ADMIN-tier API-key capability (AdminScopeRequiredMixin).
    path(
        "system/tree-display-config/",
        TreeDisplayConfigGlobalView.as_view(),
        name="system-tree-display-config",
    ),
    # Tree-display configuration (Issue #1257) — the per-workspace level. The
    # URL carries workspace_id, so the auth layer scopes active_roles to it and
    # the service re-asserts WORKSPACE_CONFIG (workspace admin, ENT-C3 = B).
    path(
        "workspaces/<uuid:workspace_id>/tree-display-config/",
        TreeDisplayConfigWorkspaceView.as_view(),
        name="workspace-tree-display-config",
    ),
    # Create-dialog form definition (Issue #1263) — the personal level of the
    # "new artifact" dialog's configurable field selection (which fields are
    # visible, order, required, default). Same self-service shape as the
    # tree-display routes directly above.
    path(
        "users/me/create-form-config/",
        CreateFormConfigUserView.as_view(),
        name="user-create-form-config",
    ),
    # Create-dialog form definition (Issue #1263) — the tenant-wide default
    # (global) level. Read: any member; write: admin (service-enforced) plus the
    # ADMIN-tier API-key capability (AdminScopeRequiredMixin).
    path(
        "system/create-form-config/",
        CreateFormConfigGlobalView.as_view(),
        name="system-create-form-config",
    ),
    # Create-dialog form definition (Issue #1263) — the per-workspace level. The
    # URL carries workspace_id, so the auth layer scopes active_roles to it and
    # the service re-asserts WORKSPACE_CONFIG (workspace admin, ENT-C3 = B).
    path(
        "workspaces/<uuid:workspace_id>/create-form-config/",
        CreateFormConfigWorkspaceView.as_view(),
        name="workspace-create-form-config",
    ),
    # ---------------------------------------------------------------------
    # Three-level preference values (Plan C, T-C2-3) — one self-contained
    # block, sorted by path. The registry lists every known key; the two
    # "effective" reads resolve user > workspace > global > default; the three
    # level routes read/write ONE level (``null`` resets a key). Workspace
    # reads need READ, workspace writes WORKSPACE_CONFIG (ENT-C3 = B), the
    # global write the admin role plus the ADMIN-tier API-key capability.
    # ---------------------------------------------------------------------
    path(
        "preference-values/registry/",
        PreferenceRegistryView.as_view(),
        name="preference-values-registry",
    ),
    path(
        "system/preference-values/",
        GlobalPreferenceLevelView.as_view(),
        name="system-preference-values",
    ),
    # The ``effective/`` routes sit before their level sibling so the more
    # specific path is unambiguous in the resolver listing.
    path(
        "users/me/preference-values/effective/",
        UserEffectivePreferenceView.as_view(),
        name="user-preference-values-effective",
    ),
    path(
        "users/me/preference-values/",
        UserPreferenceLevelView.as_view(),
        name="user-preference-values",
    ),
    path(
        "workspaces/<uuid:workspace_id>/preference-values/effective/",
        WorkspaceEffectivePreferenceView.as_view(),
        name="workspace-preference-values-effective",
    ),
    path(
        "workspaces/<uuid:workspace_id>/preference-values/",
        WorkspacePreferenceLevelView.as_view(),
        name="workspace-preference-values",
    ),
    # Theme Presets — the caller's own theme choice (GET/PUT).
    # NOTE: must precede any other users/me/ pattern that could shadow it.
    path(
        "users/me/theme-preference/",
        UserThemePreferenceView.as_view(),
        name="user-theme-preference",
    ),
    # Theme Presets — tenant-wide default (GET any user; PUT System-Admin).
    path(
        "system/theme-default/",
        TenantThemeDefaultView.as_view(),
        name="tenant-theme-default",
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
    # Workspace Context Graph — per-workspace settings toggle (Issue #377,
    # Task 9) — admin-only, mirrors the review-policy route above.
    path(
        "workspaces/<uuid:workspace_id>/context-graph-settings/",
        ContextGraphSettingsView.as_view(),
        name="workspace-context-graph-settings",
    ),
    path(
        "workspaces/<uuid:workspace_id>/context-graph-settings/rebuild/",
        ContextGraphRebuildView.as_view(),
        name="workspace-context-graph-rebuild",
    ),
    # AI Long-Term Memory — per-workspace settings toggle (Task 11). GET: any
    # workspace member. PUT: editor or admin (workspace-scoped).
    path(
        "workspaces/<uuid:workspace_id>/memory-settings/",
        WorkspaceMemorySettingsView.as_view(),
        name="workspace-memory-settings",
    ),
    # AI Long-Term Memory — active env configuration visibility (Task 11).
    # System-Admin only, mirrors system/theme-default/.
    path(
        "system/memory-settings/",
        SystemMemorySettingsView.as_view(),
        name="system-memory-settings",
    ),
    path(
        "system/memory-settings/reset/",
        SystemMemorySettingsResetView.as_view(),
        name="system-memory-settings-reset",
    ),
    # AI Long-Term Memory — System-Admin workspace overview + delete
    # (Memory Admin UI Phase 1, spec 2026-08-26).
    path(
        "system/memory/workspaces/",
        SystemMemoryWorkspaceOverviewView.as_view(),
        name="system-memory-workspace-overview",
    ),
    path(
        "system/memory/workspaces/<uuid:workspace_id>/",
        SystemMemoryWorkspaceDeleteView.as_view(),
        name="system-memory-workspace-delete",
    ),
    # AI Long-Term Memory — System-Admin visualization: entry list +
    # PCA/cluster projection (Memory Admin UI Phase 5, spec 2026-08-26).
    path(
        "system/memory/entries/",
        SystemMemoryEntriesListView.as_view(),
        name="system-memory-entries",
    ),
    path(
        "system/memory/projection/",
        SystemMemoryProjectionView.as_view(),
        name="system-memory-projection",
    ),
    # AI Long-Term Memory — user self-service (Memory Admin UI Phase 4,
    # spec 2026-08-26). Any authenticated user, own user-scoped memory only.
    path(
        "memory/me/",
        MemorySelfServiceView.as_view(),
        name="memory-self-service",
    ),
    # Plan A T-A1-4: the caller's OWN memory switches (Q1 user level).
    path(
        "memory/me/settings/",
        MemorySelfServiceSettingsView.as_view(),
        name="memory-self-service-settings",
    ),
    # RFC #1002 PR B: workspace-scoped memory listing/create + semantic search.
    path(
        "workspaces/<uuid:workspace_id>/memory/entries/",
        WorkspaceMemoryEntriesView.as_view(),
        name="workspace-memory-entries",
    ),
    path(
        "workspaces/<uuid:workspace_id>/memory/search/",
        WorkspaceMemorySearchView.as_view(),
        name="workspace-memory-search",
    ),
    # RFC #1002 F6: consolidated digest of one memory scope (read-only).
    path(
        "workspaces/<uuid:workspace_id>/memory/digest/",
        WorkspaceMemoryDigestView.as_view(),
        name="workspace-memory-digest",
    ),
    # Plan A T-A4-5: the engine's summaries of ONE session. Read-only; the
    # session must belong to this workspace's peer or the caller's own user
    # peer, otherwise 404 (QR-S04).
    path(
        "workspaces/<uuid:workspace_id>/memory/sessions/<str:session_id>/summaries/",
        WorkspaceMemorySessionSummariesView.as_view(),
        name="workspace-memory-session-summaries",
    ),
    # AP-B5.2 (#1155 Aspekt 1): natural-language Q&A over one memory scope --
    # REST mirror of the WRITE-gated MCP ``memory.ask`` tool, delegating to
    # the same ``MemoryEntryService.ask``.
    path(
        "workspaces/<uuid:workspace_id>/memory/ask/",
        WorkspaceMemoryAskView.as_view(),
        name="workspace-memory-ask",
    ),
    # RFC #1002 PR B: global entry detail/forget + promote, artifact memory,
    # and the DSGVO export. Literal sub-paths precede the ``<str:entry_id>``
    # detail route (they cannot collide: ``str`` never matches a slash).
    path(
        "memory/entries/<str:entry_id>/promote/",
        MemoryEntryPromoteView.as_view(),
        name="memory-entry-promote",
    ),
    path(
        "memory/entries/<str:entry_id>/",
        MemoryEntryDetailView.as_view(),
        name="memory-entry-detail",
    ),
    path(
        "artifacts/<uuid:artifact_id>/memory/",
        ArtifactMemoryView.as_view(),
        name="artifact-memory",
    ),
    path(
        "artifacts/<uuid:artifact_id>/memory/digest/",
        ArtifactMemoryDigestView.as_view(),
        name="artifact-memory-digest",
    ),
    path(
        "system/memory/entries/export/",
        SystemMemoryEntriesExportView.as_view(),
        name="system-memory-entries-export",
    ),
    # -- Central attribute catalog (WS5 #942, spec section 8) — tenant-wide
    # template library. Literal sub-paths precede the ``<uuid:entry_id>``
    # detail route (they cannot collide: the converter only matches a UUID).
    path(
        "attribute-catalog/",
        AttributeCatalogListView.as_view(),
        name="attribute-catalog-list",
    ),
    path(
        "attribute-catalog/search/",
        AttributeCatalogSearchView.as_view(),
        name="attribute-catalog-search",
    ),
    path(
        "attribute-catalog/export/",
        AttributeCatalogExportView.as_view(),
        name="attribute-catalog-export",
    ),
    path(
        "attribute-catalog/import/",
        AttributeCatalogImportView.as_view(),
        name="attribute-catalog-import",
    ),
    path(
        "attribute-catalog/<uuid:entry_id>/deprecate/",
        AttributeCatalogDeprecateView.as_view(),
        name="attribute-catalog-deprecate",
    ),
    path(
        "attribute-catalog/<uuid:entry_id>/add-to-definition/",
        AttributeCatalogAddToDefinitionView.as_view(),
        name="attribute-catalog-add-to-definition",
    ),
    path(
        "attribute-catalog/<uuid:entry_id>/",
        AttributeCatalogDetailView.as_view(),
        name="attribute-catalog-detail",
    ),
    # -- AWMS value migrations (WS7 #940, spec section 7) — tenant-wide admin
    # tooling. `plan/` previews (dry run), `apply/` executes; the run resource
    # is read-only plus one rollback action.
    path(
        "attribute-migration/plan/",
        AttributeMigrationPlanView.as_view(),
        name="attribute-migration-plan",
    ),
    path(
        "attribute-migration/apply/",
        AttributeMigrationApplyView.as_view(),
        name="attribute-migration-apply",
    ),
    path(
        "attribute-migration/runs/",
        AttributeMigrationRunListView.as_view(),
        name="attribute-migration-run-list",
    ),
    path(
        "attribute-migration/runs/<uuid:run_id>/rollback/",
        AttributeMigrationRollbackView.as_view(),
        name="attribute-migration-rollback",
    ),
    path(
        "attribute-migration/runs/<uuid:run_id>/",
        AttributeMigrationRunDetailView.as_view(),
        name="attribute-migration-run-detail",
    ),
    path(
        "attribute-migration/",
        AttributeMigrationApplyView.as_view(),
        name="attribute-migration-apply-alias",
    ),
    # -- Attribute definitions (spec section 5) — tenant-wide global defaults
    # plus per-workspace materialized overrides. The reset route precedes the
    # detail route so the two stay visually adjacent (they do not actually
    # compete: different path depth).
    path(
        "attribute-defaults/",
        AttributeDefaultsListView.as_view(),
        name="attribute-defaults-list",
    ),
    path(
        "attribute-defaults/<str:item_type>/<str:preset>/export/",
        AttributeDefaultsExportView.as_view(),
        name="attribute-defaults-export",
    ),
    path(
        "attribute-defaults/<str:item_type>/<str:preset>/import/",
        AttributeDefaultsImportView.as_view(),
        name="attribute-defaults-import",
    ),
    # Feature #1260: atomic section+position move of one attribute. Precedes the
    # {item_type}/{preset}/ detail route, like export/ and import/ above.
    path(
        "attribute-defaults/<str:item_type>/<str:preset>/reorder/",
        AttributeDefaultsReorderView.as_view(),
        name="attribute-defaults-reorder",
    ),
    path(
        "attribute-defaults/<str:item_type>/<str:preset>/",
        AttributeDefaultsDetailView.as_view(),
        name="attribute-defaults-detail",
    ),
    path(
        "workspaces/<uuid:workspace_id>/attribute-definitions/<str:item_type>/reset/",
        WorkspaceAttributeDefinitionResetView.as_view(),
        name="workspace-attribute-definition-reset",
    ),
    path(
        "workspaces/<uuid:workspace_id>/attribute-definitions/<str:item_type>/usage/",
        AttributeUsageView.as_view(),
        name="workspace-attribute-definition-usage",
    ),
    path(
        "workspaces/<uuid:workspace_id>/attribute-definitions/<str:item_type>/export/",
        WorkspaceAttributeDefinitionExportView.as_view(),
        name="workspace-attribute-definition-export",
    ),
    path(
        "workspaces/<uuid:workspace_id>/attribute-definitions/<str:item_type>/import/",
        WorkspaceAttributeDefinitionImportView.as_view(),
        name="workspace-attribute-definition-import",
    ),
    # Feature #1260: workspace-scoped sibling of attribute-defaults-reorder.
    path(
        "workspaces/<uuid:workspace_id>/attribute-definitions/<str:item_type>/reorder/",
        WorkspaceAttributeDefinitionReorderView.as_view(),
        name="workspace-attribute-definition-reorder",
    ),
    path(
        "workspaces/<uuid:workspace_id>/attribute-definitions/<str:item_type>/",
        WorkspaceAttributeDefinitionView.as_view(),
        name="workspace-attribute-definition",
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
    # -- Link-type catalog (Task 19/20) — tenant-wide defaults + workspace
    # overrides. reset/ precedes <str:key>/ so it is not shadowed.
    path(
        "link-type-defaults/",
        LinkTypeDefaultsListView.as_view(),
        name="link-type-defaults-list",
    ),
    path(
        "link-type-defaults/<str:key>/",
        LinkTypeDefaultsDetailView.as_view(),
        name="link-type-defaults-detail",
    ),
    # <uuid:> deliberately, not <str:>: the lenient converter lets a non-UUID
    # reach the view and 500 in the service instead of 404-ing at the router.
    path(
        "workspaces/<uuid:workspace_id>/link-type-definitions/",
        WorkspaceLinkTypeListView.as_view(),
        name="workspace-link-types-list",
    ),
    path(
        "workspaces/<uuid:workspace_id>/link-type-definitions/<str:key>/reset/",
        WorkspaceLinkTypeResetView.as_view(),
        name="workspace-link-types-reset",
    ),
    path(
        "workspaces/<uuid:workspace_id>/link-type-definitions/<str:key>/",
        WorkspaceLinkTypeDetailView.as_view(),
        name="workspace-link-types-detail",
    ),
    # SE-Auditor rule catalogue (#1262) — top-level, read-only metadata for
    # every registered audit rule. Not workspace-scoped: the rule vocabulary is
    # global, and the Auditor UI renders it before any workspace run.
    path(
        "audit/rules/",
        AuditRuleCatalogView.as_view(),
        name="audit-rules",
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
    # #569: standalone per-finding suppressions (waivers). Must precede the
    # bare audit/ run route so the specific path is never shadowed.
    path(
        "workspaces/<uuid:workspace_id>/audit/waivers/",
        WorkspaceAuditWaiverView.as_view(),
        name="workspace-audit-waivers",
    ),
    path(
        "workspaces/<uuid:workspace_id>/audit/",
        WorkspaceAuditView.as_view(),
        name="workspace-audit",
    ),
    # Plan B B5-T3 (#378) — advisory quality assessment of ONE artifact.
    # ``assess/`` is listed before the history route only for readability; the
    # two cannot shadow each other (2 vs 3 segments after ``quality/``).
    path(
        "workspaces/<uuid:workspace_id>/quality/assess/",
        QualityAssessView.as_view(),
        name="workspace-quality-assess",
    ),
    path(
        "workspaces/<uuid:workspace_id>/quality/<str:entity_type>/<uuid:entity_id>/",
        QualityHistoryView.as_view(),
        name="workspace-quality-history",
    ),
    # SysEng 2.0 N3 (traceability.suggest_links, Phase 4b, first stage) —
    # rank plausible link targets for SE-Auditor findings; no pgvector.
    path(
        "workspaces/<uuid:workspace_id>/traceability/suggest-links/",
        WorkspaceTraceabilitySuggestLinksView.as_view(),
        name="workspace-traceability-suggest-links",
    ),
    # #1197: poll a suggest-links Celery dispatch (?async=true). Flat route
    # matching bundle-compression-status/ and consistency-status/.
    path(
        "traceability/suggest-links-status/<str:task_id>/",
        TraceabilitySuggestLinksStatusView.as_view(),
        name="api-v1-traceability-suggest-links-status",
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
    # Consistency-check async polling (GH-796) — status of a
    # requirement.check_consistency Celery dispatch.
    path(
        "consistency-status/<str:task_id>/",
        ConsistencyStatusView.as_view(),
        name="api-v1-consistency-status",
    ),
    # Pending-review queue (issue #1089) — the REST half of the MCP
    # `review.list_pending` tool, which existed while both of these routes
    # 404'd. One service (`application.review_queue_service.ReviewQueueService`),
    # two transports; the flat route follows the `?workspace_id=` convention
    # every other unscoped list endpoint in this API uses, the nested one the
    # workspace-scoped convention. Approving/rejecting stays on the existing
    # `POST /<entity>/<pk>/transitions/` action — see review_views' docstring.
    # Collection root (#1177): the SPA renders a review queue, yet GET
    # /api/v1/reviews/ 404'd while only /reviews/pending/ existed. The root is
    # the same handler as pending/ (same ReviewQueueService, same workspace
    # scoping/permissions, same StandardPagination envelope) — one data source,
    # two paths, so a generic client can list the collection at its natural URL.
    path(
        "reviews/",
        ReviewsPendingView.as_view(),
        name="api-v1-reviews",
    ),
    path(
        "reviews/pending/",
        ReviewsPendingView.as_view(),
        name="api-v1-reviews-pending",
    ),
    path(
        "workspaces/<uuid:workspace_id>/reviews/pending/",
        WorkspaceReviewsPendingView.as_view(),
        name="workspace-reviews-pending",
    ),
    # Generic suggestion inbox (ADR-019 WP4) — the REST half of the MCP
    # `suggestion.*` tool group (WP3), both a thin adapter over the Layer-2
    # `application.suggestion_service.SuggestionService`. Accept/reject delegate
    # to the existing per-kind domain path (for `trace_link` the M2 confirm/
    # discard) and then stamp the durable receipt; no state transition is
    # reimplemented here. Error taxonomy (review finding 003-01):
    # AgentSelfConfirmError -> 403, ProducerContextRequiredError -> 409.
    path(
        "suggestions/",
        SuggestionListView.as_view(),
        name="api-v1-suggestions",
    ),
    path(
        "suggestions/<uuid:suggestion_id>/accept/",
        SuggestionAcceptView.as_view(),
        name="api-v1-suggestion-accept",
    ),
    path(
        "suggestions/<uuid:suggestion_id>/reject/",
        SuggestionRejectView.as_view(),
        name="api-v1-suggestion-reject",
    ),
    # Artifact comments (Menschen-im-System spec §4) — nested sub-resource,
    # must precede router.urls so the artifacts/<pk>/ detail route cannot
    # shadow it.
    path(
        "artifacts/<uuid:artifact_id>/comments/",
        ArtifactCommentsView.as_view(),
        name="api-v1-artifact-comments",
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
