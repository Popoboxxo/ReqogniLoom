"""Central resource-scope classifier for the two-level authorization axis.

ADR-011 (``docs/se/ADR/ADR-011_autorisierungsachse_workspace_tenant.md``,
status ``accepted``) splits authorization into two levels:

* **Tenant** stays the isolation hull (Row-Level-Security is not touched here).
* **Workspace** is the leading axis for object authorization: the authority for
  a workspace-scoped resource is derived from the **target object**, never from
  a client-supplied ``workspace_id``.

This module is the *one* declaration point the ADR asks for (decision point 3):
every REST resource/view class declares exactly one scope — ``tenant`` or
``workspace`` — with framework/public/infrastructure classes named as explicit
``exception`` entries rather than silently defaulting. The enforcement seam in
:func:`enforce_request_scope` derives the fence from this declaration at a single
place (``RbacPermission`` / ``HasOperationPermission``), not per route.

DEFAULT-DENY semantics (decision point 3)
-----------------------------------------
* A view class that is not declared is **denied** (403) once enforcement is
  switched on — there is no fallback to the tenant-wide role union and no
  implicit ``tenant`` assumption.
* For a ``workspace``-scoped resource whose **target workspace cannot be
  resolved**, the answer is also **403** (fail-closed). A ``tenant``/``exception``
  resource needs no target workspace and is not subject to this rule.

Feature gate (hard-stop discipline, decision point 4 and the SEC-02 plan)
------------------------------------------------------------------------
The classification/default-deny seam is gated by
``settings.AUTHZ_WORKSPACE_SCOPE_ENFORCED`` (default **False**): the coverage
gate in ``rest_api/tests/test_resource_scope_coverage.py`` must be green *before*
the seam is switched on, so a misclassification cannot silently fail a whole
scope open. The API-key workspace fence (SEC-03) is narrower — it only affects
keys that carry a non-empty ``workspace_ids`` fence — and is therefore enforced
independently of that gate via
``settings.AUTHZ_API_KEY_WORKSPACE_FENCE_ENFORCED`` (default **True**), mirroring
the MCP dispatcher (``mcp_server.tool_registry``).

Layering note: the object→workspace lookup lives in
``application.workspace_lookup`` (the same helper the MCP dispatcher uses); it is
imported lazily so this module stays import-safe and shares exactly one fence
implementation between REST and MCP.

req_id: ADR-011, findings AUD-2026-09-222 / N2 / 240 / 035.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable
from uuid import UUID

from .context import AuthContext
from .workspace_scope import resolve_request_workspace_id

logger = logging.getLogger(__name__)

__all__ = [
    "ResourceClassification",
    "ResourceScope",
    "UNCLASSIFIED_DENIAL",
    "WORKSPACE_MEMBERSHIP_DENIAL",
    "WORKSPACE_UNRESOLVABLE_DENIAL",
    "classify_class_name",
    "classify_view",
    "enforce_request_scope",
    "resolve_object_workspace_id",
    "resolve_target_workspace_id",
    "scope_enforcement_enabled",
    "workspace_fence_denial",
]


class ResourceScope(str, Enum):
    """Authorization scope declared for one REST resource/view class."""

    #: Tenant-wide resource: no single target workspace is required.
    TENANT = "tenant"
    #: Workspace-owned resource: authority follows the target object.
    WORKSPACE = "workspace"
    #: Named, tenant-like exception (framework, public, infra or handler-enforced).
    EXCEPTION = "exception"


@dataclass(frozen=True)
class ResourceClassification:
    """One declared resource classification.

    Attributes:
        scope: The declared :class:`ResourceScope`.
        reason: Human-readable justification, mandatory for ``exception`` and
            used to make every unusual decision reviewable.
        entity_key: Key into ``application.workspace_lookup.ENTITY_SPECS`` used
            to derive the owning workspace from the object id on detail routes.
            ``None`` when the route carries the workspace in its URL/query/body.
        id_kwargs: URL kwargs that may carry the object primary key, probed in
            order (first hit wins).
    """

    scope: ResourceScope
    reason: str = ""
    entity_key: str | None = None
    id_kwargs: tuple[str, ...] = ("pk",)


# ---------------------------------------------------------------------------
# Denial reasons (English; surfaced verbatim in the 403 envelope detail).
# ---------------------------------------------------------------------------

UNCLASSIFIED_DENIAL = (
    "Access denied: this resource is not declared in the authorization scope "
    "registry, and unclassified resources are denied by default (ADR-011)."
)
WORKSPACE_UNRESOLVABLE_DENIAL = (
    "Access denied: this workspace-scoped resource names no resolvable target "
    "workspace, so workspace authority cannot be established (ADR-011)."
)
WORKSPACE_MEMBERSHIP_DENIAL = (
    "Access denied: you hold no active role in the workspace that owns this "
    "object (ADR-011)."
)


# ---------------------------------------------------------------------------
# Central registry
# ---------------------------------------------------------------------------

#: Declared scope + object-resolution metadata per view class name.
#:
#: Keyed by *class name* (not the class object) so the registry has no import
#: side effects and the coverage gate can compare it against the URL resolver
#: without importing every module. Keep the three groups in sync with
#: ``rest_api/tests/test_resource_scope_coverage.py``; a new class that is not
#: listed here turns that gate red.
_REGISTRY: dict[str, ResourceClassification] = {}


def _declare(name: str, classification: ResourceClassification) -> None:
    _REGISTRY[name] = classification


# -- workspace-scoped: object-derived owning workspace -------------------------
# Core domain ViewSets whose objects live in a workspace; detail/action routes
# name the object by ``pk`` and derive authority from it.
for _name, _entity in {
    "ArtifactViewSet": "artifact",
    "RequirementViewSet": "requirement",
    "StakeholderNeedViewSet": "need",
    "ArchitectureElementViewSet": "architecture",
    "TestCaseViewSet": "testcase",
    "AdrViewSet": "adr",
    "RiskViewSet": "risk",
    "GoalViewSet": "goal",
    "MainGoalViewSet": "main_goal",
    "IssueViewSet": "issue",
    "ChangeRequestViewSet": "change_request",
    "CommentViewSet": "comment",
    "DiagramViewSet": "diagram",
    "GlossaryTermViewSet": "glossary",
    "IcdViewSet": "icd",
    "TestRunViewSet": "test_run",
    "InterviewViewSet": "interview",
    "BaselineViewSet": "baseline",
    "RequirementHistoryView": "requirement",
    "CanvasStrokeView": "diagram",
    "MermaidSourceView": "diagram",
    "MermaidPreviewView": "diagram",
}.items():
    _declare(_name, ResourceClassification(ResourceScope.WORKSPACE, entity_key=_entity))

# Sub-resources that name their object with a non-``pk`` kwarg.
_declare(
    "ArtifactCommentsView",
    ResourceClassification(
        ResourceScope.WORKSPACE, entity_key="artifact", id_kwargs=("artifact_id",)
    ),
)
_declare(
    "ArtifactMemoryView",
    ResourceClassification(
        ResourceScope.WORKSPACE, entity_key="artifact", id_kwargs=("artifact_id",)
    ),
)
_declare(
    "ArtifactMemoryDigestView",
    ResourceClassification(
        ResourceScope.WORKSPACE, entity_key="artifact", id_kwargs=("artifact_id",)
    ),
)

# -- workspace-scoped: workspace named in URL/query/body ------------------------
# These routes carry the workspace explicitly (``workspaces/<uuid:...>/...``),
# so ``resolve_request_workspace_id`` supplies the target. No object lookup.
_WORKSPACE_VIA_REQUEST = (
    "CsvImportView",
    "CsvExportView",
    "ReqifImportView",
    "ReqifExportView",
    "ReviewPolicyView",
    "ContextGraphSettingsView",
    "ContextGraphRebuildView",
    "ItemPermissionViewSet",
    "WorkspaceMembersView",
    "WorkspaceMemberRoleTransitionView",
    "WorkspaceArchitectureDecomposeView",
    "WorkspaceArchitectureDecomposeCommitView",
    "WorkspaceAttributeDefinitionView",
    "WorkspaceAttributeDefinitionExportView",
    "WorkspaceAttributeDefinitionImportView",
    "WorkspaceAttributeDefinitionResetView",
    "WorkspaceAuditView",
    "WorkspaceAuditRemediateView",
    "WorkspaceAuditAiReviewView",
    "WorkspaceAuditWaiverView",
    "WorkspaceBannerView",
    "WorkspaceLinkTypeListView",
    "WorkspaceLinkTypeDetailView",
    "WorkspaceLinkTypeResetView",
    "WorkspaceMemoryEntriesView",
    "WorkspaceMemorySearchView",
    "WorkspaceMemoryDigestView",
    "WorkspaceMemorySettingsView",
    "WorkspacePermissionDefinitionView",
    "WorkspacePermissionResetView",
    "WorkspaceReviewsPendingView",
    "WorkspaceTraceabilitySuggestLinksView",
    "AttributeUsageView",
)
for _name in _WORKSPACE_VIA_REQUEST:
    _declare(
        _name,
        ResourceClassification(
            ResourceScope.WORKSPACE,
            reason="target workspace carried in the request URL/query/body",
        ),
    )

# Trace links connect two artifacts and have no single owning workspace row, so
# the owning workspace is resolved by the link service; the route derives the
# request workspace when one is supplied.
_declare(
    "TraceLinkViewSet",
    ResourceClassification(
        ResourceScope.WORKSPACE,
        reason="trace-link ownership resolved by the link service",
    ),
)
_declare(
    "TraceabilityViewSet",
    ResourceClassification(
        ResourceScope.TENANT,
        reason="tenant-wide trace query; workspace filtering applied in-service",
    ),
)

# -- tenant-scoped resources ---------------------------------------------------
_TENANT_SCOPED = {
    # workspace / user / key administration
    "WorkspaceViewSet": "workspace discovery and lifecycle (tenant-wide)",
    "UserViewSet": "tenant user administration",
    "ApiKeyViewSet": "self-/governance-scoped API-key management",
    # self-service identity
    "MeView": "caller's own identity",
    "UserPreferenceView": "caller's own preferences",
    "UserThemePreferenceView": "caller's own theme preference",
    "NotificationPreferenceView": "caller's own notification preferences",
    "NotificationViewSet": "caller's own notification feed",
    "MemorySelfServiceView": "caller's own user-scoped memory",
    # tenant-wide configuration / catalogs
    "LlmSettingsView": "tenant singleton LLM configuration",
    "PromptTemplateView": "tenant-wide prompt template",
    "PromptTemplateResetView": "tenant-wide prompt template reset",
    "PromptTemplateSlotListView": "tenant-wide prompt slots",
    "PromptTemplateSlotDetailView": "tenant-wide prompt slot",
    "PromptVariableListView": "tenant-wide prompt variables",
    "PromptVariableDetailView": "tenant-wide prompt variable",
    "AttributeCatalogListView": "tenant-wide attribute catalog",
    "AttributeCatalogSearchView": "tenant-wide attribute catalog",
    "AttributeCatalogExportView": "tenant-wide attribute catalog",
    "AttributeCatalogImportView": "tenant-wide attribute catalog",
    "AttributeCatalogDetailView": "tenant-wide attribute catalog",
    "AttributeCatalogDeprecateView": "tenant-wide attribute catalog",
    "AttributeCatalogAddToDefinitionView": "tenant-wide attribute catalog",
    "AttributeDefaultsListView": "tenant-wide attribute defaults",
    "AttributeDefaultsExportView": "tenant-wide attribute defaults",
    "AttributeDefaultsImportView": "tenant-wide attribute defaults",
    "AttributeDefaultsDetailView": "tenant-wide attribute defaults",
    "AttributeSchemaView": "tenant-wide attribute schema discovery",
    "AttributeMigrationPlanView": "tenant-wide attribute migration tooling",
    "AttributeMigrationApplyView": "tenant-wide attribute migration tooling",
    "AttributeMigrationRollbackView": "tenant-wide attribute migration tooling",
    "AttributeMigrationRunListView": "tenant-wide attribute migration tooling",
    "AttributeMigrationRunDetailView": "tenant-wide attribute migration tooling",
    "GlobalWorkflowDefinitionListView": "tenant-wide workflow defaults",
    "GlobalWorkflowDefinitionDetailView": "tenant-wide workflow defaults",
    "GlobalWorkflowInitializeView": "tenant-wide workflow defaults",
    "GlobalWorkflowStatesView": "tenant-wide workflow defaults",
    "GlobalWorkflowStateDetailView": "tenant-wide workflow defaults",
    "GlobalWorkflowTransitionsView": "tenant-wide workflow defaults",
    "GlobalWorkflowTransitionDetailView": "tenant-wide workflow defaults",
    "GlobalPermissionDefinitionView": "tenant-wide permission definition",
    "PermissionMismatchListView": "tenant-wide permission decision log",
    "EnforcementStatusView": "tenant-wide enforcement toggle",
    "EnforcementFlipView": "tenant-wide enforcement toggle",
    "LinkTypeDefaultsListView": "tenant-wide link-type catalog",
    "LinkTypeDefaultsDetailView": "tenant-wide link-type catalog",
    "WorkflowDefinitionViewSet": "tenant/workspace workflow definitions",
    # reviews queue (flat), search/metrics read-models, async status
    "ReviewsPendingView": "flat review queue; optional ?workspace_id",
    "SearchViewSet": "tenant-wide search across accessible workspaces",
    "MetricsViewSet": "tenant-wide KPI read-model",
    "BundleCompressionStatusView": "async task status, tenant-owned",
    "ConsistencyStatusView": "async task status, tenant-owned",
    "scope_preview": "baseline scope preview",
    # admin / system operations
    "AdminRestoreView": "system-admin disaster recovery",
    "BackupListCreateView": "system-admin backup management",
    "SystemHealthView": "system-admin health dashboard",
    "GlobalRateLimitsView": "system-admin rate-limit defaults",
    "RateLimitsView": "system-admin rate-limit management",
    "GlobalBannerView": "system-admin global banner",
    "TenantThemeDefaultView": "tenant theme default",
    "ThemePaletteListView": "theme palette catalog",
    "ThemePaletteExportView": "theme palette catalog",
    "ThemePaletteDetailView": "theme palette catalog",
    "SystemMemorySettingsView": "system-admin memory configuration",
    "SystemMemorySettingsResetView": "system-admin memory configuration",
    "SystemMemoryWorkspaceOverviewView": "system-admin memory overview",
    "SystemMemoryWorkspaceDeleteView": "system-admin memory deletion",
    "SystemMemoryEntriesListView": "system-admin memory entries",
    "SystemMemoryProjectionView": "system-admin memory projection",
    "SystemMemoryEntriesExportView": "system-admin memory export",
}
for _name, _reason in _TENANT_SCOPED.items():
    _declare(_name, ResourceClassification(ResourceScope.TENANT, reason=_reason))

# -- named exceptions ----------------------------------------------------------
# Framework/public/infrastructure or handler-enforced resources that are
# deliberately neither tenant- nor workspace-gated at this seam.
_EXCEPTIONS = {
    # memory entries apply their own MemoryPolicy inside the service (RFC #1002),
    # the same "enforced by the handler" class the MCP dispatcher records.
    "MemoryEntryDetailView": "memory access policy enforced inside the service",
    "MemoryEntryPromoteView": "memory access policy enforced inside the service",
    # framework / infrastructure / public endpoints
    "APIRootView": "DRF router API root, no resource",
    "RedirectView": "URL format-suffix redirect",
    "SpectacularAPIView": "public OpenAPI schema",
    "SpectacularSwaggerView": "public Swagger UI",
    "SpectacularRedocView": "public ReDoc UI",
    "VersionView": "public version endpoint",
    "HealthView": "infrastructure health probe",
    "PublicLoginBannerView": "public login-page banner",
    "LoginView": "public credential exchange",
    "RefreshView": "public refresh-cookie exchange",
    "LogoutView": "self-scoped session teardown",
    "McpHttpTransportView": "MCP transport; own API-key authentication",
    "McpMessagesView": "MCP transport; own API-key authentication",
    "McpSseTransportView": "MCP transport; own API-key authentication",
}
for _name, _reason in _EXCEPTIONS.items():
    _declare(_name, ResourceClassification(ResourceScope.EXCEPTION, reason=_reason))


def classify_class_name(name: str) -> ResourceClassification | None:
    """Return the declared classification for a view class name, or ``None``."""
    return _REGISTRY.get(name)


def classify_view(view: Any) -> ResourceClassification | None:
    """Return the declared classification for a view instance/class, or ``None``.

    ``None`` means *unclassified* and is treated as DEFAULT-DENY by the seam
    once enforcement is enabled.
    """
    if isinstance(view, type):
        return _REGISTRY.get(view.__name__)
    return _REGISTRY.get(type(view).__name__)


# ---------------------------------------------------------------------------
# Target-workspace resolution
# ---------------------------------------------------------------------------


def _coerce_uuid(value: Any) -> UUID | None:
    if value is None or isinstance(value, (list, dict, bool)):
        return None
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        return None


def _resolve_owning_from_request(
    request: Any, classification: ResourceClassification
) -> UUID | None:
    """Resolve the workspace owning the object named by the request's URL kwargs.

    Fail-soft: an absent/malformed id, a deleted row or a lookup error all yield
    ``None`` so the caller can fall back to the request workspace. The *deny*
    decision itself belongs to the caller.
    """
    if classification.entity_key is None:
        return None
    match = getattr(request, "resolver_match", None)
    kwargs = getattr(match, "kwargs", None) or {}
    from application.workspace_lookup import resolve_owning_workspace_id

    for key in classification.id_kwargs:
        value = _coerce_uuid(kwargs.get(key))
        if value is None:
            continue
        resolved = resolve_owning_workspace_id(classification.entity_key, value)
        if resolved is not None:
            return resolved
    return None


def _view_from_request(request: Any) -> Any | None:
    """Return the view instance/class behind *request*, if resolvable.

    During DRF authentication the view is available through
    ``request.parser_context['view']``; as a fallback the resolver match's
    callback exposes ``cls`` (the ``as_view`` wrapper). Returns ``None`` when
    neither is available, which callers treat as "cannot derive object scope".
    """
    parser_context = getattr(request, "parser_context", None)
    if isinstance(parser_context, dict):
        view = parser_context.get("view")
        if view is not None:
            return view
    match = getattr(request, "resolver_match", None)
    func = getattr(match, "func", None)
    return getattr(func, "cls", None)


def resolve_object_workspace_id(request: Any) -> UUID | None:
    """Return the workspace owning the object the request names, or ``None``.

    Used by :class:`AuthTenancyAuthentication` (only when scope enforcement is
    enabled) so the *RBAC matrix itself* is evaluated against the target
    object's workspace for detail routes that carry no ``workspace`` segment —
    the object-derived half of SEC-02. Returns ``None`` for tenant/exception
    resources, unclassified views, and objects that cannot be resolved.
    """
    view = _view_from_request(request)
    if view is None:
        return None
    classification = classify_view(view)
    if classification is None or classification.scope is not ResourceScope.WORKSPACE:
        return None
    return _resolve_owning_from_request(request, classification)


def resolve_target_workspace_id(request: Any, view: Any) -> UUID | None:
    """Return the workspace a REST request targets, or ``None`` if unresolvable.

    Precedence (ADR-011 decision point 2 — authority from the target object):

    1. If the view declares an ``entity_key`` and the route names the object by
       id, the owning workspace is derived from that **object** first. A
       client-supplied ``workspace_id`` therefore cannot override the object's
       real workspace.
    2. Otherwise the workspace named in the URL/query/body is used
       (:func:`resolve_request_workspace_id`).
    """
    classification = classify_view(view)
    if classification is not None:
        owning = _resolve_owning_from_request(request, classification)
        if owning is not None:
            return owning
    return resolve_request_workspace_id(request)


# ---------------------------------------------------------------------------
# API-key workspace fence (shared by REST and MCP — SEC-03)
# ---------------------------------------------------------------------------


def workspace_fence_denial(
    allowed_workspace_ids: Iterable[str] | None,
    target_workspace_id: Any,
) -> str | None:
    """Return why a key may not act on *target_workspace_id*, else ``None``.

    ``ApiKey.workspace_ids`` fences a key to an explicit set of workspaces. An
    empty/absent tuple means "no fence" and is always allowed. A fenced key with
    **no** resolvable target workspace is denied as well: without a target there
    is nothing to check the fence against, and the tenant-wide fallback would
    hand the key exactly the workspaces it was fenced out of. Fail closed.

    This is the single implementation used by both transports
    (``mcp_server.tool_registry._check_workspace_fence`` delegates here), so the
    fence cannot drift between REST and MCP.
    """
    allowed = tuple(allowed_workspace_ids or ())
    if not allowed:
        return None
    if target_workspace_id is not None and str(target_workspace_id) in allowed:
        return None
    return (
        "This API key is restricted to specific workspaces and may not be used "
        "for this call. Target the workspace the key was issued for, or use a "
        "key without a workspace restriction."
    )


# ---------------------------------------------------------------------------
# Enforcement seam
# ---------------------------------------------------------------------------


def scope_enforcement_enabled() -> bool:
    """Return whether the DEFAULT-DENY resource-scope seam is switched on."""
    from django.conf import settings

    return bool(getattr(settings, "AUTHZ_WORKSPACE_SCOPE_ENFORCED", False))


def _api_key_fence_enabled() -> bool:
    from django.conf import settings

    return bool(
        getattr(settings, "AUTHZ_API_KEY_WORKSPACE_FENCE_ENFORCED", True)
    )


def _has_active_role_in_workspace(auth_context: AuthContext, workspace_id: UUID) -> bool:
    """Return whether the caller holds any non-suspended role in *workspace_id*.

    Reuses the already-resolved roles when the context was scoped to exactly
    that workspace; otherwise asks :class:`AuthorizationService` (tenant-scoped
    by the active RLS context). Any lookup failure is fail-closed.
    """
    if auth_context.workspace_id is not None and auth_context.workspace_id == workspace_id:
        return bool(auth_context.active_roles)
    try:
        from .services import AuthorizationService

        roles = AuthorizationService().active_roles_for(
            user_id=auth_context.user_id, workspace_id=workspace_id
        )
    except Exception:  # noqa: BLE001 — fail closed on any resolution error
        logger.debug(
            "Workspace membership lookup failed for user=%s workspace=%s",
            auth_context.user_id,
            workspace_id,
        )
        return False
    return bool(roles)


def enforce_request_scope(
    request: Any, view: Any, auth_context: AuthContext | None
) -> str | None:
    """Return a denial reason for the request, or ``None`` when it may proceed.

    Two independent gates, in order:

    1. **API-key workspace fence** (SEC-03) — active for any key carrying a
       non-empty ``workspace_ids``; unaffected for unfenced keys.
    2. **Resource-scope default-deny** (SEC-02) — only when
       ``AUTHZ_WORKSPACE_SCOPE_ENFORCED`` is on. Unclassified view classes and
       workspace-scoped resources with no resolvable target workspace are denied;
       tenant/exception resources are not affected by the target-workspace rule.

    The caller (`RbacPermission` / `HasOperationPermission`) raises
    ``PermissionDenied`` (403) on a non-``None`` result.
    """
    if auth_context is None:
        return None

    # Nothing to do (and no DB lookup) for an unfenced key with enforcement off:
    # the common case must stay behaviour- and cost-neutral.
    fence_applies = _api_key_fence_enabled() and bool(
        getattr(auth_context, "api_key_workspace_ids", ())
    )
    scope_applies = scope_enforcement_enabled()
    if not fence_applies and not scope_applies:
        return None

    target_workspace_id = resolve_target_workspace_id(request, view)

    if fence_applies:
        fence_denial = workspace_fence_denial(
            auth_context.api_key_workspace_ids,
            target_workspace_id,
        )
        if fence_denial is not None:
            return fence_denial

    if not scope_applies:
        return None

    classification = classify_view(view)
    if classification is None:
        return UNCLASSIFIED_DENIAL
    if classification.scope is not ResourceScope.WORKSPACE:
        return None
    if target_workspace_id is None:
        return WORKSPACE_UNRESOLVABLE_DENIAL
    if not _has_active_role_in_workspace(auth_context, target_workspace_id):
        return WORKSPACE_MEMBERSHIP_DENIAL
    return None
