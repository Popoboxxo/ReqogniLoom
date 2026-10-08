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

Collection routes (ADR-013 amendment to ADR-011)
------------------------------------------------
A "detail route" names a single target object; a "collection route" (DRF
``list``/``create``) does not. They cannot be fenced the same way:

* **List / retrieve-many** carries no target object. Denying it outright (the
  pre-ADR-013 behaviour) turned every flat collection request into a 403. The
  endpoint resolves its own workspace from the URL/query and the auth layer
  scopes the caller's roles to it; when a workspace is named the seam enforces
  the caller's role in that workspace (a member of A cannot list B). When no
  workspace is named the endpoint's own filter/validation applies; the seam
  never blanket-denies a list.
* **Create / collection** resolves the target workspace **content-type
  independently** from URL kwargs, query and body (JSON, form-urlencoded and
  multipart). The **body is authoritative** over the query on a flat create
  (it is the value the serializer persists); the URL memory of a nested route
  stays first. A create that names two *different* workspaces (URL/query vs.
  body) is denied **403** as a mismatch instead of silently choosing one — this
  closes the residual in which the query scoped the caller's roles to A while
  the body wrote to B. When a target resolves and the caller holds no active
  role there, the create is denied **403** — this closes the form-encoded create
  bypass (SEC-02 review M1). When *no* target resolves the seam does not invent
  a 403: the endpoint's serializer requires a workspace (400) or its service
  resolves the workspace from the parent entity and enforces membership itself.
  These per-view trust boundaries are documented in the ADR and covered by the
  collection gate in ``rest_api/tests/test_resource_scope_coverage.py``.

Object routes stay object-derived and fail-closed, with the 404-vs-403 rule of
ADR-013: a **resolvable object in the caller's tenant** without a role is denied
(403); an object that does not resolve — missing, malformed id or belonging to
another tenant — is *not* denied here, so the tenant-scoped view answers
404/400. A foreign object therefore stays indistinguishable from a missing one
**across tenants** (no cross-tenant existence leak). Within one tenant a
member-facing 403 (no role) versus 404 (missing object) is deliberately
distinguishable; that is a documented residual, not a leak.

Feature gate (decision point 4, flipped on by ADR-013)
------------------------------------------------------
The classification/default-deny seam is gated by
``settings.AUTHZ_WORKSPACE_SCOPE_ENFORCED`` (default **True** since ADR-013):
the coverage gate in ``rest_api/tests/test_resource_scope_coverage.py`` is
green, so the seam is switched on. Operators can still set the env var to
``False`` for a rollback window, but the repository default now enforces
DEFAULT-DENY (ADR-011). The API-key workspace fence (SEC-03) is narrower — it
only affects keys that carry a non-empty ``workspace_ids`` fence — and is
enforced independently of that gate via
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
from .workspace_scope import (
    resolve_create_workspace_mismatch,
    resolve_request_workspace_id,
    workspace_exists,
)

logger = logging.getLogger(__name__)

__all__ = [
    "ResourceClassification",
    "ResourceScope",
    "UNCLASSIFIED_DENIAL",
    "WORKSPACE_MEMBERSHIP_DENIAL",
    "WORKSPACE_TARGET_MISMATCH_DENIAL",
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
    #: Documented trust boundary for a ``workspace``-scoped route that names its
    #: target workspace in the request. When set, the seam defers the membership
    #: decision to the view/service (which enforces it, including any deliberate
    #: elevation or bootstrap branch). Empty means the seam enforces authority
    #: centrally. Only set where the central check would wrongly lock out an
    #: intended service-level branch (ADR-013 review CODE-1).
    handler_guard: str = ""


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
WORKSPACE_TARGET_MISMATCH_DENIAL = (
    "Access denied: the workspace named in the URL/query does not match the "
    "workspace named in the request body. A create must name one consistent "
    "target workspace (ADR-013)."
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
# ADR-019 WP4: accept/reject name the suggestion by id and derive the target
# workspace from the suggestion row itself, so authority follows the object —
# a caller without a role in the suggestion's workspace is denied and a foreign
# tenant's id resolves to nothing (404, no existence leak).
for _name in ("SuggestionAcceptView", "SuggestionRejectView"):
    _declare(
        _name,
        ResourceClassification(
            ResourceScope.WORKSPACE,
            entity_key="suggestion",
            id_kwargs=("suggestion_id",),
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
    "WorkspaceMemoryAskView",
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

# Routes whose view/service deliberately owns the membership decision because it
# implements a documented elevation or bootstrap branch that a central role
# check would lock out. Each guard names the exact enforcement point; the seam
# defers to it (ADR-013 review CODE-1). Everything else in the group is enforced
# centrally against the resolved target workspace.
for _name, _guard in {
    "WorkspaceMembersView": (
        "AuthorizationService.assign_role enforces admin/tenant-admin and the "
        "SEC-05 bootstrap (roleless self-assign in an own-tenant, admin-less "
        "workspace); a central role check would lock that branch out."
    ),
}.items():
    _existing = _REGISTRY[_name]
    _declare(
        _name,
        ResourceClassification(
            ResourceScope.WORKSPACE,
            reason=_existing.reason,
            handler_guard=_guard,
        ),
    )

# Trace links connect two artifacts and have no single owning workspace row, so
# the owning workspace is derived from the source artifact's workspace (ADR-013
# refines ADR-011's "resolved by the link service"): a caller must hold a role in
# the workspace that owns the link's source end to reach it by id.
_declare(
    "TraceLinkViewSet",
    ResourceClassification(
        ResourceScope.WORKSPACE,
        reason="trace-link ownership derived from the source artifact's workspace",
        entity_key="trace_link",
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
    "DisplayPreferenceView": "caller's own display preferences",
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
    # ADR-019 WP4: the flat suggestion inbox mirrors ReviewsPendingView — the
    # mandatory ?workspace_id is validated by the view (400 when absent) and the
    # auth layer scopes the caller's roles to it, so a same-tenant non-member is
    # denied by RBAC while a foreign-tenant workspace answers an empty page.
    "SuggestionListView": "flat suggestion inbox; mandatory ?workspace_id",
    "SearchViewSet": "tenant-wide search across accessible workspaces",
    "MetricsViewSet": "tenant-wide KPI read-model",
    "BundleCompressionStatusView": "async task status, tenant-owned",
    "ConsistencyStatusView": "async task status, tenant-owned",
    "TraceabilitySuggestLinksStatusView": "async task status, tenant-owned",
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
    "SpectacularJSONAPIView": "public OpenAPI JSON schema",
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


def _request_url_kwargs(request: Any, view: Any | None = None) -> dict[str, Any]:
    """Return the URL kwargs of the request, resilient to direct view calls.

    Routed traffic exposes them via ``resolver_match.kwargs``; DRF's
    ``initialize_request`` mirrors them into ``parser_context['kwargs']``; and
    boundary tests that invoke a handler directly set the view's own
    ``kwargs``. Merging all three is safe: for routed traffic they are the same
    values.
    """
    kwargs: dict[str, Any] = {}
    match = getattr(request, "resolver_match", None)
    match_kwargs = getattr(match, "kwargs", None)
    if isinstance(match_kwargs, dict):
        kwargs.update(match_kwargs)
    parser_context = getattr(request, "parser_context", None)
    if isinstance(parser_context, dict):
        context_kwargs = parser_context.get("kwargs")
        if isinstance(context_kwargs, dict):
            kwargs.update(context_kwargs)
    if view is not None:
        view_kwargs = getattr(view, "kwargs", None)
        if isinstance(view_kwargs, dict):
            kwargs.update(view_kwargs)
    return kwargs


def _resolve_owning_from_request(
    request: Any, classification: ResourceClassification, view: Any | None = None
) -> UUID | None:
    """Resolve the workspace owning the object named by the request's URL kwargs.

    Fail-soft: an absent/malformed id, a deleted row or a lookup error all yield
    ``None`` so the caller can fall back to the request workspace. The *deny*
    decision itself belongs to the caller.
    """
    if classification.entity_key is None:
        return None
    kwargs = _request_url_kwargs(request, view)
    from application.workspace_lookup import resolve_owning_workspace_id

    for key in classification.id_kwargs:
        value = _coerce_uuid(kwargs.get(key))
        if value is None:
            continue
        resolved = resolve_owning_workspace_id(classification.entity_key, value)
        if resolved is not None:
            return resolved
    return None


def _workspace_from_url_kwargs(request: Any, view: Any | None = None) -> UUID | None:
    """Return a workspace named by the request/view URL kwargs, if any.

    Fallback for direct handler calls where the request has no
    ``resolver_match``; routed traffic resolves this from the URL first.
    """
    kwargs = _request_url_kwargs(request, view)
    for key in ("workspace_id", "workspace_pk"):
        resolved = _coerce_uuid(kwargs.get(key))
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
    return _resolve_owning_from_request(request, classification, view)


def _resolve_target_workspaces(
    request: Any, view: Any, classification: ResourceClassification | None
) -> tuple[UUID | None, UUID | None]:
    """Return ``(owning_workspace_id, target_workspace_id)`` in one pass.

    ``owning_workspace_id`` is the workspace of the object the route names by id
    (``None`` when the route names no object, or the object does not resolve);
    ``target_workspace_id`` is the authorization target — the object's workspace
    when it resolves, else the workspace named by URL/query/body. Computing both
    here keeps the object lookup single-shot instead of resolving it again in
    the object branch (ADR-013 review CODE-3).
    """
    owning: UUID | None = None
    if classification is not None:
        owning = _resolve_owning_from_request(request, classification, view)
    target = owning
    if target is None:
        target = resolve_request_workspace_id(request)
    if target is None:
        target = _workspace_from_url_kwargs(request, view)
    return owning, target


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
    _, target = _resolve_target_workspaces(request, view, classification)
    return target


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

    Three cases, aligned with how the auth layer builds the context:

    * The context is scoped to exactly this workspace — reuse its already
      workspace-filtered roles (no second query). Real object routes always land
      here: ``AuthTenancyAuthentication`` derives the workspace from the object
      when the URL names none (ADR-011/SEC-02).
    * The context is scoped to a *different* workspace — the client named one
      workspace while the object lives in another. That is the cross-workspace
      escalation case, so a real membership lookup in the object's workspace is
      required (a scoped role in one workspace must not authorise another).
    * The context is not workspace-scoped at all (``workspace_id`` is ``None``).
      This is the boundary/direct-call shape (a caller that bypassed
      ``AuthTenancyAuthentication`` and supplied roles directly) and the
      pre-ADR behaviour for it: trust the context's roles. For routed traffic
      this is unreachable whenever a target object resolves, because the auth
      layer scopes ``workspace_id`` to that same object workspace before the
      permission layer runs.

    Any membership lookup failure is fail-closed.
    """
    if auth_context.workspace_id is None:
        return bool(auth_context.active_roles)
    if auth_context.workspace_id == workspace_id:
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


def _is_tenant_admin(auth_context: AuthContext) -> bool:
    """Return whether the caller holds an active tenant-admin role.

    Fail-closed: any lookup error denies. Used only to preserve the documented
    System-Admin elevation on routes that deliberately declare no RBAC operation
    (ADR-013 review CODE-1).
    """
    tenant_id = getattr(auth_context, "tenant_id", None)
    if tenant_id is None:
        return False
    try:
        from .services import AuthorizationService

        return AuthorizationService().is_tenant_admin(
            user_id=auth_context.user_id, tenant_id=tenant_id
        )
    except Exception:  # noqa: BLE001 — fail closed on any resolution error
        logger.debug(
            "Tenant-admin lookup failed for user=%s", auth_context.user_id
        )
        return False


def _has_workspace_authority(auth_context: AuthContext, workspace_id: UUID) -> bool:
    """Return whether the caller may act on *workspace_id*.

    Authority is a workspace role **or** tenant-admin (System-Admin) elevation.
    The elevation branch keeps the documented ``required_operation=None`` routes
    (workspace members, banner, memory settings) working now that the central
    membership check is restored: a System-Admin holds no workspace-level
    ``UserRole`` but is the tenant's legitimate override. Every other caller
    without a role is denied (ADR-013 review CODE-1).
    """
    if _has_active_role_in_workspace(auth_context, workspace_id):
        return True
    return _is_tenant_admin(auth_context)


def _is_collection_action(view: Any) -> bool:
    """Return whether *view* is a DRF ``list``/``create`` collection action.

    Both the action name **and** DRF's ``detail`` flag are required: a view could
    declare an action literally named ``create`` while still being a detail
    route, and only ``detail is False`` marks a real collection route (ADR-013
    review CODE-4). Plain ``APIView`` instances carry neither attribute and so
    never touch a collection: the ``getattr(..., True)`` default keeps them out.
    """
    if getattr(view, "detail", True) is not False:
        return False
    return getattr(view, "action", None) in ("list", "create")


def _workspace_in_active_tenant(workspace_id: UUID) -> bool:
    """Return whether *workspace_id* exists in the caller's active tenant.

    Distinguishes "same tenant, no role" (403) from "another tenant" (404): the
    tenant-scoped ``Workspace`` manager reports a foreign workspace as absent, so
    a foreign object never produces a 403 that would leak its existence.

    Fail-closed: a resolution error counts as "in tenant" so the membership gate
    still decides (deny unless a real role is found), matching
    :func:`_has_active_role_in_workspace`. The error is logged as a warning so it
    is not silent (ADR-013 review CODE-2). The existence check itself is shared
    with authentication via :func:`auth_tenancy.workspace_scope.workspace_exists`
    (ADR-013 review CODE-3).
    """
    try:
        return workspace_exists(workspace_id)
    except Exception as exc:  # noqa: BLE001 — split below, fail closed by default
        # No active tenant is the boundary/direct-call shape (a caller that
        # bypassed AuthTenancyAuthentication): there is nothing to scope against,
        # so defer to the tenant-scoped view as the "not in this tenant" result
        # rather than 403 (mirrors the pre-existing behaviour and keeps a
        # hand-built AuthContext usable in permission-layer unit tests).
        from persistence.tenancy import TenantContextNotSetError

        if isinstance(exc, TenantContextNotSetError):
            return False
        logger.warning(
            "Workspace existence check failed for workspace=%s; failing closed",
            workspace_id,
        )
        return True


def _enforce_collection_scope(
    view: Any, auth_context: AuthContext, target_workspace_id: UUID | None
) -> str | None:
    """Enforce workspace authority for a DRF collection ``list``/``create``.

    ``list`` carries no single target object. When a workspace is named it is the
    authorization target and a caller without a role there is denied; when none
    is named the endpoint's own filter/validation applies, so the seam does not
    blanket-deny.

    ``create`` must resolve a target workspace when one is named (URL/query/body,
    content-type independent): a caller without a role in it is denied. When no
    target resolves the endpoint's serializer or service owns the guard (it
    requires a workspace or derives it from the parent entity and enforces
    membership), documented per view in the ADR; the seam never invents a role
    from the tenant-wide union.
    """
    action = getattr(view, "action", None)
    if action == "list" and target_workspace_id is None:
        return None

    if target_workspace_id is None:
        # create without a resolvable target: view/service guard, see ADR-013.
        return None

    if not _workspace_in_active_tenant(target_workspace_id):
        # Names a workspace outside the caller's tenant: never deny here, the
        # tenant-scoped view answers 404/400 (no cross-tenant existence leak).
        return None
    if not _has_workspace_authority(auth_context, target_workspace_id):
        return WORKSPACE_MEMBERSHIP_DENIAL
    return None


def enforce_request_scope(
    request: Any, view: Any, auth_context: AuthContext | None
) -> str | None:
    """Return a denial reason for the request, or ``None`` when it may proceed.

    Two independent gates, in order:

    1. **API-key workspace fence** (SEC-03) — active for any key carrying a
       non-empty ``workspace_ids``; unaffected for unfenced keys.
    2. **Resource-scope default-deny** (SEC-02/ADR-013) — only when
       ``AUTHZ_WORKSPACE_SCOPE_ENFORCED`` is on. Unclassified view classes are
       denied; workspace-scoped *object* routes are denied when the object
       resolves in the caller's tenant and the caller holds no role there;
       collection routes (list/create) are fenced against a named target but
       never blanket-denied when none is named.

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

    classification = classify_view(view)
    owning_workspace_id, target_workspace_id = _resolve_target_workspaces(
        request, view, classification
    )

    if fence_applies:
        fence_denial = workspace_fence_denial(
            auth_context.api_key_workspace_ids,
            target_workspace_id,
        )
        if fence_denial is not None:
            return fence_denial

    if not scope_applies:
        return None

    if classification is None:
        return UNCLASSIFIED_DENIAL
    if classification.scope is not ResourceScope.WORKSPACE:
        return None

    # Collection routes name no single target object (ADR-013). They are still
    # fenced against a *named* target workspace (see the helper) but never
    # blanket-denied when none is named. A create that names two different
    # workspaces (URL/query vs. body) is rejected outright: without this the
    # query value scoped the caller's roles while the body value was persisted,
    # allowing a same-tenant write into a workspace without a role (SEC-02
    # review residual). Fail closed rather than pick a winner.
    if _is_collection_action(view):
        if (
            getattr(view, "action", None) == "create"
            and resolve_create_workspace_mismatch(request)
        ):
            return WORKSPACE_TARGET_MISMATCH_DENIAL
        return _enforce_collection_scope(view, auth_context, target_workspace_id)

    # Object/mutation route: authority follows the target object.
    if classification.entity_key is not None:
        if owning_workspace_id is None:
            # No object row in this tenant (missing, malformed id, or another
            # tenant's object): never deny here. The tenant-scoped view answers
            # 404/400, so a foreign object stays indistinguishable from a
            # missing one (ADR-013 404-vs-403 rule, no cross-tenant leak).
            return None
        if not _workspace_in_active_tenant(owning_workspace_id):
            return None
        if not _has_active_role_in_workspace(auth_context, owning_workspace_id):
            return WORKSPACE_MEMBERSHIP_DENIAL
        return None

    # No object resolution available: a workspace-scoped action that lives on the
    # request workspace (import/export, workspace members, ...). It must name one
    # AND the caller must hold authority there — the central membership check
    # (workspace role or System-Admin elevation) is restored here as defence in
    # depth (ADR-013 review CODE-1). A registered ``handler_guard`` marks the few
    # routes whose service owns a deliberate elevation/bootstrap branch and is
    # deferred to; without a named workspace the answer stays fail-closed
    # (ADR-011 decision point 3).
    if target_workspace_id is None:
        return WORKSPACE_UNRESOLVABLE_DENIAL
    if classification.handler_guard:
        return None
    if not _workspace_in_active_tenant(target_workspace_id):
        return None
    if not _has_workspace_authority(auth_context, target_workspace_id):
        return WORKSPACE_MEMBERSHIP_DENIAL
    return None
