"""drf-spectacular schema policy for the ReqogniLoom REST surface (#1388).

The published OpenAPI document used to describe *nothing* for every view that
does not declare a DRF serializer. ``AutoSchema._get_serializer()`` answered
``None`` with the blunt ``unable to guess serializer … Ignoring view for now``
error, and the generator then rendered the operation with
``responses: {200: {description: "No response body"}}`` and no request body at
all. The path survived, but the contract was empty — a generated client could
not tell a status endpoint from a 204-only operation, and a POST body could
only be guessed.

Trade-off — a permissive schema is honest, a missing path is a lie
------------------------------------------------------------------
A view that genuinely has no serializer is *not* an error worth dropping: its
path, method, parameters, security and error responses are real and must be
published. This module therefore replaces the silent ``None`` with an explicit,
permissive fallback that is marked ``x-reqlo-untyped: true`` and still carries
the operation's real metadata. The fallback says only what is true — "any JSON
object" — instead of inventing a shape or pretending there is no body.

The fallback is *not* a licence to skip serializers: every view that reaches it
must be listed in :data:`UNTYPED_VIEW_ALLOWLIST` on purpose, with a reason, and
the paired gate (``rest_api.tests.test_schema_completeness_1388``) fails when
the two directions disagree. A new untyped view therefore cannot slip in
silently — it either ships a serializer or is added here deliberately.

Where the base class raised its "guess" error, this subclass resolves nothing
and does not emit the error; everywhere it *can* resolve a serializer it
returns exactly what ``AutoSchema`` would have returned. No view is dropped and
no view's real schema changes.
"""
from __future__ import annotations

from typing import Any, Optional

import uritemplate
from drf_spectacular.openapi import AutoSchema
from drf_spectacular.plumbing import (
    build_serializer_context,
    get_view_model,
    resolve_django_path_parameter,
    resolve_regex_path_parameter,
)
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse
from rest_framework.generics import GenericAPIView
from rest_framework.views import APIView

# Importing the module registers the ``AuthTenancyAuthentication`` extension
# (drf-spectacular discovers extensions via their metaclass). It is imported
# here — next to ``DEFAULT_SCHEMA_CLASS`` — so the extension is guaranteed to
# exist before the first ``get_auth()`` call, without touching app startup.
from auth_tenancy import schema as _auth_tenancy_schema  # noqa: F401

__all__ = [
    "ReqLoAutoSchema",
    "UNTYPED_VIEW_ALLOWLIST",
    "reset_untyped_view_usage",
    "untyped_views_used",
]


#: One-line, true reasons for each view that legitimately reaches the
#: permissive fallback. Populated from a real generation run — never guessed.
#:
#: Rules:
#: * a view that ships a serializer must NOT be listed here;
#: * a view added here must say *why* its shape is not statically described
#:   (hand-built response dict, protocol/stream payload, third-party model, …);
#: * the gate asserts ``set(allowlist) == untyped_views_used()`` in both
#:   directions, so adding a view without a reason is a build failure.
UNTYPED_VIEW_ALLOWLIST: dict[str, str] = {
    "AdminRestoreView": (
        "Admin operational endpoint returning a hand-built status/payload dict; "
        "no model serializer exists."
    ),
    "ArtifactCommentsView": (
        "Collaboration comment list assembled from service dicts; no DRF "
        "serializer."
    ),
    "ArtifactMemoryDigestView": (
        "Memory payload assembled by MemoryEntryService (`_view`/digest); no DRF "
        "serializer exists."
    ),
    "ArtifactMemoryView": (
        "Memory payload assembled by MemoryEntryService (`_view`/digest); no DRF "
        "serializer exists."
    ),
    "AttributeCatalogAddToDefinitionView": (
        "Admin attribute-catalog configuration; entries are JSON documents built "
        "by AttributeCatalogService."
    ),
    "AttributeCatalogDeprecateView": (
        "Admin attribute-catalog configuration; entries are JSON documents built "
        "by AttributeCatalogService."
    ),
    "AttributeCatalogDetailView": (
        "Admin attribute-catalog configuration; entries are JSON documents built "
        "by AttributeCatalogService."
    ),
    "AttributeCatalogExportView": (
        "Admin attribute-catalog configuration; entries are JSON documents built "
        "by AttributeCatalogService."
    ),
    "AttributeCatalogImportView": (
        "Admin attribute-catalog configuration; entries are JSON documents built "
        "by AttributeCatalogService."
    ),
    "AttributeCatalogListView": (
        "Admin attribute-catalog configuration; entries are JSON documents built "
        "by AttributeCatalogService."
    ),
    "AttributeCatalogSearchView": (
        "Admin attribute-catalog configuration; entries are JSON documents built "
        "by AttributeCatalogService."
    ),
    "AttributeDefaultsDetailView": (
        "Attribute-definition document (JSON-schema-like configuration) resolved "
        "per workspace/preset."
    ),
    "AttributeDefaultsExportView": (
        "Attribute-definition document (JSON-schema-like configuration) resolved "
        "per workspace/preset."
    ),
    "AttributeDefaultsImportView": (
        "Attribute-definition document (JSON-schema-like configuration) resolved "
        "per workspace/preset."
    ),
    "AttributeDefaultsListView": (
        "Attribute-definition document (JSON-schema-like configuration) resolved "
        "per workspace/preset."
    ),
    "AttributeDefaultsReorderView": (
        "Attribute-definition document (JSON-schema-like configuration) resolved "
        "per workspace/preset."
    ),
    "AttributeMigrationApplyView": (
        "Declarative attribute-migration plan/report document (nested, "
        "user-supplied shape)."
    ),
    "AttributeMigrationPlanView": (
        "Declarative attribute-migration plan/report document (nested, "
        "user-supplied shape)."
    ),
    "AttributeMigrationRollbackView": (
        "Declarative attribute-migration plan/report document (nested, "
        "user-supplied shape)."
    ),
    "AttributeMigrationRunDetailView": (
        "Declarative attribute-migration plan/report document (nested, "
        "user-supplied shape)."
    ),
    "AttributeMigrationRunListView": (
        "Declarative attribute-migration plan/report document (nested, "
        "user-supplied shape)."
    ),
    "AttributeSchemaView": (
        "Resolved attribute schema document; its shape is dynamic per workspace "
        "and rigor preset."
    ),
    "AttributeUsageView": (
        "Usage-count report over custom attributes (aggregated, dynamic keys)."
    ),
    "AuditRuleCatalogView": (
        "Static SE-Auditor rule catalog list; no model backs the rows."
    ),
    "BackupListCreateView": (
        "Admin operational endpoint returning a hand-built status/payload dict; "
        "no model serializer exists."
    ),
    "BundleCompressionStatusView": (
        "Async Celery task-status envelope keyed by arbitrary task id."
    ),
    "ConsistencyStatusView": (
        "Async Celery task-status envelope keyed by arbitrary task id."
    ),
    "ContextGraphRebuildView": (
        "Context-graph rebuild status payload (configuration + counters)."
    ),
    "ContextGraphSettingsView": (
        "Context-graph settings document (free-form configuration map)."
    ),
    "CreateFormConfigGlobalView": (
        "Create-dialog form-definition document (ordered, dynamic field list)."
    ),
    "CreateFormConfigUserView": (
        "Create-dialog form-definition document (ordered, dynamic field list)."
    ),
    "CreateFormConfigWorkspaceView": (
        "Create-dialog form-definition document (ordered, dynamic field list)."
    ),
    "CsvExportView": (
        "Streaming CSV file response (Content-Disposition attachment); there is "
        "no JSON body to model."
    ),
    "CsvImportView": (
        "Multipart CSV upload with a hand-built import report; the request is a "
        "file, not JSON."
    ),
    "DiagramViewSet": (
        "Diagram CRUD deliberately has no serializer_class (DTO-built fields); "
        "response dicts are assembled in the view."
    ),
    "DisplayPreferenceView": (
        "Per-user display-preference map (free-form keys)."
    ),
    "EnforcementFlipView": (
        "Permission-enforcement toggle payload (configuration state)."
    ),
    "EnforcementStatusView": (
        "Permission-enforcement status payload (configuration state)."
    ),
    "GlobalPermissionDefinitionView": (
        "Permission-matrix document (RBAC configuration)."
    ),
    "GlobalWorkflowDefinitionDetailView": (
        "Workflow-definition graph document (states + transitions)."
    ),
    "GlobalWorkflowDefinitionListView": (
        "Workflow-definition graph document (states + transitions)."
    ),
    "GlobalWorkflowInitializeView": (
        "Workflow-definition graph document (states + transitions)."
    ),
    "GlobalWorkflowStateDetailView": (
        "Workflow-definition graph document (states + transitions)."
    ),
    "GlobalWorkflowStatesView": (
        "Workflow-definition graph document (states + transitions)."
    ),
    "GlobalWorkflowTransitionDetailView": (
        "Workflow-definition graph document (states + transitions)."
    ),
    "GlobalWorkflowTransitionsView": (
        "Workflow-definition graph document (states + transitions)."
    ),
    "IcdViewSet": (
        "ICD CRUD deliberately has no serializer_class (DTO-built fields); "
        "response dicts are assembled in the view."
    ),
    "InterviewViewSet": (
        "Interview protocol payload (session state / artifact proposals) built "
        "by InterviewService."
    ),
    "ItemPermissionViewSet": (
        "Item-level permission rules; dicts built by the permission service."
    ),
    "LinkTypeDefaultsDetailView": (
        "Link-type catalog definition document (tenant-extensible JSON "
        "catalogue)."
    ),
    "LinkTypeDefaultsListView": (
        "Link-type catalog definition document (tenant-extensible JSON "
        "catalogue)."
    ),
    "LlmSettingsView": (
        "LLM settings view with a masked/encrypted API-key payload; never a "
        "model serializer."
    ),
    "LoginView": (
        "Authentication/session endpoint returning a credential or identity "
        "payload built in the view."
    ),
    "LogoutView": (
        "Authentication/session endpoint returning a hand-built confirmation "
        "payload."
    ),
    "MeView": (
        "Authentication/session endpoint returning the caller's identity/role "
        "payload."
    ),
    "MemoryEntryDetailView": (
        "Memory payload assembled by MemoryEntryService (`_view`/digest); no DRF "
        "serializer exists."
    ),
    "MemoryEntryPromoteView": (
        "Memory payload assembled by MemoryEntryService (`_view`/digest); no DRF "
        "serializer exists."
    ),
    "MemorySelfServiceView": (
        "Memory payload assembled by MemoryEntryService (`_view`/digest); no DRF "
        "serializer exists."
    ),
    "MetricsViewSet": (
        "Metrics/KPI map computed by the se_metrics read model (dynamic metric "
        "keys)."
    ),
    "NotificationPreferenceView": (
        "Per-user notification-preference map (free-form keys)."
    ),
    "PermissionMismatchListView": (
        "Permission-mismatch log rows (read-only audit entries)."
    ),
    "PromptTemplateResetView": (
        "Prompt-template registry entry/content payload."
    ),
    "PromptTemplateSlotDetailView": (
        "Prompt-template registry entry/content payload."
    ),
    "PromptTemplateSlotListView": (
        "Prompt-template registry entry/content payload."
    ),
    "PromptTemplateView": (
        "Prompt-template registry entry/content payload."
    ),
    "PromptVariableDetailView": (
        "Prompt-variable catalog entry/configuration payload."
    ),
    "PromptVariableListView": (
        "Prompt-variable catalog entry/configuration payload."
    ),
    "RefreshView": (
        "Authentication/session endpoint returning a refreshed credential "
        "payload."
    ),
    "RequirementHistoryView": (
        "Artifact history rows assembled by the history service (field-level "
        "changes)."
    ),
    "ReviewPolicyView": (
        "Review-policy configuration document."
    ),
    "ReviewsPendingView": (
        "Review-queue rows assembled from workflow state (dynamic item types)."
    ),
    "SearchViewSet": (
        "Full-text search results assembled by SearchService (heterogeneous "
        "artifact rows)."
    ),
    "SuggestionAcceptView": (
        "Durable suggestion-inbox proposal document (polymorphic payload)."
    ),
    "SuggestionListView": (
        "Durable suggestion-inbox proposal document (polymorphic payload)."
    ),
    "SuggestionRejectView": (
        "Durable suggestion-inbox proposal document (polymorphic payload)."
    ),
    "SystemMemoryEntriesExportView": (
        "Memory admin export: JSON document or CSV file streamed by "
        "MemoryAdminService."
    ),
    "SystemMemoryEntriesListView": (
        "Memory admin list payload assembled by MemoryAdminService."
    ),
    "SystemMemoryProjectionView": (
        "Memory admin PCA-projection payload (computed coordinates + clusters)."
    ),
    "SystemMemorySettingsResetView": (
        "Deployment-global memory configuration map (env fallback per field)."
    ),
    "SystemMemorySettingsView": (
        "Deployment-global memory configuration map (env fallback per field)."
    ),
    "SystemMemoryWorkspaceDeleteView": (
        "Memory admin deletion report (per-tier counters)."
    ),
    "SystemMemoryWorkspaceOverviewView": (
        "Memory admin per-workspace overview rows."
    ),
    "TraceabilitySuggestLinksStatusView": (
        "Async Celery task-status envelope keyed by arbitrary task id."
    ),
    "TreeDisplayConfigGlobalView": (
        "Tree display config document (ordered, dynamic field selection)."
    ),
    "TreeDisplayConfigUserView": (
        "Tree display config document (ordered, dynamic field selection)."
    ),
    "TreeDisplayConfigWorkspaceView": (
        "Tree display config document (ordered, dynamic field selection)."
    ),
    "UserPreferenceView": (
        "Per-user preference map (free-form keys)."
    ),
    "UserViewSet": (
        "Tenant-admin user lifecycle; list/create payloads are hand-built and "
        "include computed roles."
    ),
    "VersionView": (
        "Static build/version metadata; no request and a fixed hand-built body."
    ),
    "WorkspaceArchitectureDecomposeCommitView": (
        "Decomposition draft/commit payload (nested elements + derived "
        "requirements)."
    ),
    "WorkspaceArchitectureDecomposeView": (
        "Decomposition draft/commit payload (nested elements + derived "
        "requirements)."
    ),
    "WorkspaceAttributeDefinitionExportView": (
        "Workspace attribute-definition document (JSON configuration)."
    ),
    "WorkspaceAttributeDefinitionImportView": (
        "Workspace attribute-definition document (JSON configuration)."
    ),
    "WorkspaceAttributeDefinitionReorderView": (
        "Workspace attribute-definition document (JSON configuration)."
    ),
    "WorkspaceAttributeDefinitionResetView": (
        "Workspace attribute-definition document (JSON configuration)."
    ),
    "WorkspaceAttributeDefinitionView": (
        "Workspace attribute-definition document (JSON configuration)."
    ),
    "WorkspaceAuditAiReviewView": (
        "SE-Auditor report payload with dynamic finding rows and refactoring "
        "packages."
    ),
    "WorkspaceAuditRemediateView": (
        "SE-Auditor remediation payload (dynamic finding references)."
    ),
    "WorkspaceAuditWaiverView": (
        "Waiver record payload with server-set metadata."
    ),
    "WorkspaceLinkTypeDetailView": (
        "Link-type catalog definition document (tenant-extensible JSON "
        "catalogue)."
    ),
    "WorkspaceLinkTypeListView": (
        "Link-type catalog definition document (tenant-extensible JSON "
        "catalogue)."
    ),
    "WorkspaceLinkTypeResetView": (
        "Link-type catalog definition document (tenant-extensible JSON "
        "catalogue)."
    ),
    "WorkspaceMemberRoleTransitionView": (
        "Workspace membership payload assembled from role rows."
    ),
    "WorkspaceMembersView": (
        "Workspace membership list assembled from role rows."
    ),
    "WorkspaceMemoryAskView": (
        "Memory payload assembled by MemoryEntryService (`ask` result + "
        "envelope)."
    ),
    "WorkspaceMemoryDigestView": (
        "Memory payload assembled by MemoryEntryService (`_view`/digest); no DRF "
        "serializer exists."
    ),
    "WorkspaceMemoryEntriesView": (
        "Memory payload assembled by MemoryEntryService (`_view`/digest); no DRF "
        "serializer exists."
    ),
    "WorkspaceMemorySettingsView": (
        "Workspace memory settings map (feature toggle configuration)."
    ),
    "WorkspacePermissionDefinitionView": (
        "Permission-matrix document (RBAC configuration)."
    ),
    "WorkspacePermissionResetView": (
        "Permission-matrix document (RBAC configuration)."
    ),
    "WorkspaceReviewsPendingView": (
        "Review-queue rows assembled from workflow state (dynamic item types)."
    ),
    "WorkspaceTraceabilitySuggestLinksView": (
        "Async suggestion run: task id or the suggestion-inbox proposal payload."
    ),
    "scope_preview": (
        "Baseline scope-preview function view returning a computed, dynamic diff "
        "preview."
    ),
}


#: Views that actually used the fallback during the current build. A
#: preprocessing hook clears it at the start of every generation so the gate
#: observes exactly the operations of *this* document.
_used_untyped_views: set[str] = set()


def reset_untyped_view_usage(endpoints: Any, **kwargs: Any) -> Any:
    """``PREPROCESSING_HOOKS`` entry point: clear the per-build usage record.

    drf-spectacular calls preprocessing hooks once per generation with the
    endpoint list, before any view is inspected. Returning the endpoints
    unchanged keeps the hook side-effect-free for discovery.
    """
    _used_untyped_views.clear()
    return endpoints


def untyped_views_used() -> frozenset[str]:
    """The view class names that used the permissive fallback in this build."""
    return frozenset(_used_untyped_views)


def _fallback_schema() -> dict[str, Any]:
    """A fresh permissive object schema for a view without a serializer."""
    return {
        "type": "object",
        "additionalProperties": True,
        "description": (
            "Permissive fallback schema (#1388): this view declares no DRF "
            "serializer, so its concrete fields are not described. Any JSON "
            "object is accepted and returned. The view is listed in "
            "rest_api.schema.UNTYPED_VIEW_ALLOWLIST; a generated client must "
            "not treat the absence of properties as an empty body."
        ),
        "x-reqlo-untyped": True,
    }


class ReqLoAutoSchema(AutoSchema):
    """``AutoSchema`` that publishes untyped views instead of emptying them.

    Two behaviours change relative to the base class, both additive:

    1. A view for which no serializer can be resolved returns a marked
       permissive object schema (request: media-type map; response:
       ``OpenApiResponse``) instead of ``None`` + an ``unable to guess
       serializer`` error. ``DELETE`` keeps its conventional 204 because an
       ``OpenApiResponse`` still routes through the base ``DELETE`` handling.
    2. Path parameters whose type cannot be derived (no converter, no model —
       e.g. a plain ``ViewSet`` without ``queryset``) are declared explicitly
       as strings. This silences ``could not derive type of path parameter``
       without weakening any typed route: an existing converter or a resolvable
       model field always wins.
    """

    # -- serializer resolution ------------------------------------------------

    def _resolve_serializer(self) -> Optional[Any]:
        """Mirror ``AutoSchema._get_serializer`` without emitting an error.

        Returns the serializer/instance the base class would have returned, or
        ``None`` when it would have failed. The base class' private helper is
        not called because it emits the very error this schema exists to
        replace; the resolution rules below are copied verbatim from
        drf-spectacular 0.30 (``GenericAPIView`` → ``APIView`` leniency).
        """
        view = self.view
        context = build_serializer_context(view)
        try:
            if isinstance(view, GenericAPIView):
                # Same shortcut the base class takes: only call get_serializer()
                # when the view overrides it, otherwise get_serializer_class().
                if view.__class__.get_serializer == GenericAPIView.get_serializer:
                    serializer_class = view.get_serializer_class()
                    if serializer_class is None:
                        return None
                    return serializer_class(context=context)
                return view.get_serializer(context=context)
            if isinstance(view, APIView):
                get_serializer = getattr(view, "get_serializer", None)
                if callable(get_serializer):
                    return get_serializer(context=context)
                get_serializer_class = getattr(view, "get_serializer_class", None)
                if callable(get_serializer_class):
                    serializer_class = get_serializer_class()
                    if serializer_class is None:
                        return None
                    return serializer_class(context=context)
                return getattr(view, "serializer_class", None)
        except Exception:  # noqa: BLE001 - the base class swallows this too
            # A serializer whose get_queryset()/get_serializer_class() needs a
            # real request is not statically describable; fall back instead of
            # turning schema generation into a 500.
            return None
        return None

    def _serializer(self) -> Optional[Any]:
        """Resolve once per operation (request and response share the result)."""
        if not hasattr(self, "_reqlo_resolved_serializer"):
            self._reqlo_resolved_serializer = self._resolve_serializer()
        return self._reqlo_resolved_serializer

    def _record_untyped(self) -> None:
        _used_untyped_views.add(self.view.__class__.__name__)

    def get_auth(self) -> list[Any]:
        """Deduplicate security requirements emitted for one operation.

        Registering an ``OpenApiAuthenticationExtension`` for the project's
        authenticator (#1388) makes each operation declare ``BearerAuth`` from
        the authenticator *and* from the global ``SECURITY`` setting, which
        drf-spectacular appends unconditionally. Publishing the same
        requirement twice adds noise to every generated client, so exact
        duplicates are collapsed while the original order is preserved.
        """
        requirements = super().get_auth()
        seen: set[tuple[Any, ...]] = set()
        deduped: list[Any] = []
        for requirement in requirements:
            if isinstance(requirement, dict):
                key = tuple(
                    sorted(
                        (name, tuple(scopes or []))
                        for name, scopes in requirement.items()
                    )
                )
            else:  # pragma: no cover - defensive, requirements are mappings
                key = (str(requirement),)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(requirement)
        return deduped

    # -- request / response fallback -----------------------------------------

    def get_request_serializer(self) -> Any:
        """Return the resolved serializer or a marked permissive request body."""
        serializer = self._serializer()
        if serializer is not None:
            return serializer
        self._record_untyped()
        # A ``dict`` returned here is read by ``_get_request_body`` as a
        # media-type map, so wrap the raw schema accordingly.
        return {"application/json": _fallback_schema()}

    def get_response_serializers(self) -> Any:
        """Return the resolved serializer or a marked permissive response body."""
        serializer = self._serializer()
        if serializer is not None:
            return serializer
        self._record_untyped()
        # ``OpenApiResponse`` keeps the base class' ``DELETE -> 204`` rule and
        # its create (201) / read (200) status selection intact.
        return OpenApiResponse(
            response=_fallback_schema(),
            description=(
                "Permissive fallback response (#1388): the view declares no DRF "
                "serializer, so the concrete body is not described."
            ),
        )

    # -- path parameter types -------------------------------------------------

    def get_override_parameters(self) -> list[Any]:
        """Declare string path parameters the generator cannot type (#1388).

        ``_resolve_path_parameters`` warns for every path variable that has no
        Django converter and whose view exposes no model. Those variables are
        already published as ``string``; declaring them through the override
        seam records the same schema without the warning and makes the type
        explicit. A converter or a resolvable model field is never overridden.
        """
        parameters: list[Any] = list(super().get_override_parameters())
        try:
            model = get_view_model(self.view, emit_warnings=False)
        except Exception:  # noqa: BLE001 - no model is exactly the case we fill
            model = None
        if model is not None:
            return parameters

        for variable in uritemplate.variables(self.path):
            if resolve_django_path_parameter(
                self.path_regex, variable, self.map_renderers("format")
            ):
                continue
            if resolve_regex_path_parameter(self.path_regex, variable):
                continue
            parameters.append(
                OpenApiParameter(
                    variable,
                    type=str,
                    location=OpenApiParameter.PATH,
                    description=(
                        "Resource identifier. The route carries no converter "
                        "and the view exposes no model, so the type is declared "
                        "here as a string (#1388)."
                    ),
                )
            )
        return parameters
