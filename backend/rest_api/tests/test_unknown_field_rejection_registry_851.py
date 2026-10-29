"""#851 follow-up — every REST write serializer rejects unknown request keys.

The first #851 pass introduced :class:`rest_api.serializers
.UnknownFieldRejectionMixin` and wired it into the artifact serializers it
already covered (plus the ones #915/#916 touched). Auditing every
``Serializer(data=request.data)`` call site in ``rest_api/`` found a second set
of create/update serializers that still relied on DRF's default: a key no
declared field accepts was silently dropped while the request answered
200/201 — indistinguishable from success.

This module pins the now-uniform contract for the remaining write serializers
and adds a discovery guard: a new ``*Serializer`` in one of
:data:`_SERIALIZER_MODULES` fails the suite until it is explicitly classified
as guarded or exempt, so the silent-drop gap cannot reopen unnoticed.
"""
from __future__ import annotations

import importlib
import inspect
import uuid
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from rest_framework import serializers as drf_serializers
from rest_framework.test import APIRequestFactory

from application.settings_service import SettingsService
from auth_tenancy.context import AuthContext, AuthMethod
from rest_api.architecture_decompose_views import GenerateDraftRequestSerializer
from rest_api.audit_views import RemediateRequestSerializer, WaiverCreateSerializer
from rest_api.icd_views import IcdViewSet
from rest_api.notification_preference_views import (
    NotificationPreferenceUpdateSerializer,
)
from rest_api.preference_views import PreferenceUpdateSerializer
from rest_api.prompt_variable_views import PromptVariableWriteSerializer
from rest_api.serializers import (
    AdrSerializer,
    ArchitectureElementSerializer,
    ArtifactSerializer,
    BaselineSerializer,
    ChangeRequestSerializer,
    CommentSerializer,
    GlossaryTermSerializer,
    GoalSerializer,
    IcdParameterSerializer,
    IssueSerializer,
    MainGoalSerializer,
    RequirementSerializer,
    RiskSerializer,
    StakeholderNeedSerializer,
    TestCaseSerializer,
    TestRunResultBulkSerializer,
    TestRunResultSerializer,
    TestRunSerializer,
    TraceLinkSerializer,
    UnknownFieldRejectionMixin,
    WorkflowDefinitionSerializer,
    WorkspaceSerializer,
)
from rest_api.serializers_diagram import (
    CanvasStrokeDataSerializer,
    MermaidSourceSerializer,
)
from rest_api.settings_views import (
    ContextGraphSettingsSerializer,
    LlmSettingsSerializer,
    PromptTemplateSerializer,
    PromptTemplateSlotWriteSerializer,
    ReviewPolicySerializer,
)

# ---------------------------------------------------------------------------
# Registries
# ---------------------------------------------------------------------------

#: Every top-level REST create/update serializer that must carry the shared
#: unknown-field guard. Listed explicitly so the discovery guard below can tell
#: a deliberate exemption apart from a forgotten one.
_GUARDED_WRITE_SERIALIZERS: tuple[type, ...] = (
    # artifact/domain serializers (guarded by the original #851 pass)
    ArtifactSerializer,
    RequirementSerializer,
    StakeholderNeedSerializer,
    ArchitectureElementSerializer,
    TestCaseSerializer,
    TraceLinkSerializer,
    BaselineSerializer,
    GoalSerializer,
    MainGoalSerializer,
    IssueSerializer,
    ChangeRequestSerializer,
    GlossaryTermSerializer,
    AdrSerializer,
    RiskSerializer,
    # newly covered by this pass
    WorkspaceSerializer,
    WorkflowDefinitionSerializer,
    TestRunSerializer,
    # wired into the raw /results/ and /results/bulk/ write paths
    TestRunResultSerializer,
    TestRunResultBulkSerializer,
    IcdParameterSerializer,
    CommentSerializer,
    PreferenceUpdateSerializer,
    NotificationPreferenceUpdateSerializer,
    PromptVariableWriteSerializer,
    LlmSettingsSerializer,
    PromptTemplateSerializer,
    PromptTemplateSlotWriteSerializer,
    ReviewPolicySerializer,
    ContextGraphSettingsSerializer,
    RemediateRequestSerializer,
    GenerateDraftRequestSerializer,
    CanvasStrokeDataSerializer,
    MermaidSourceSerializer,
    # #569: the standalone suppression create serializer (rejects granted_by).
    WaiverCreateSerializer,
)

#: Write serializers that reject unknown request keys with their *own*,
#: deliberately different accumulation logic instead of
#: :class:`UnknownFieldRejectionMixin`. Keyed by ``module.ClassName`` with the
#: reason the shared mixin is not used; the discovery guard treats them as
#: classified (guarded), and the behaviour itself is pinned separately.
_BESPOKE_GUARDED_SERIALIZERS: dict[str, str] = {
    "rest_api.api_key_serializers.ApiKeyCreateSerializer": (
        "bespoke cumulative validation in run_validation (#1439): it reports "
        "every unknown key together with every field problem under the "
        "historical wording, and the mixin would additionally re-admit the "
        "always-allowed PATCH keys this create-only route rejects"
    ),
}

#: Every serializer in :data:`_SERIALIZER_MODULES` that legitimately carries no
#: guard, each with the reason it is exempt. The discovery guard fails on any
#: module-local ``*Serializer`` that appears in neither registry.
_EXEMPT_SERIALIZERS: dict[str, str] = {
    # --- rest_api.serializers -------------------------------------------
    "UserProfileSerializer": (
        "own equivalent QIRK-002 guard in validate() (#73): rejects unknown "
        "keys and protected fields with a targeted message"
    ),
    "BlockerWaiverSerializer": (
        "nested child of the guarded BaselineSerializer; the guard applies at "
        "the top-level request serializer"
    ),
    "NotificationSerializer": "read-only response serializer",
    "ImpactNodeSerializer": "read-only response serializer",
    "ResolvedArtifactSerializer": "read-only response serializer",
    "SimilarRequirementSerializer": "read-only response serializer",
    "SimilarTraceLinkSerializer": "read-only response serializer",
    "TracePathSerializer": "read-only response serializer",
    "BaselineDeltaEntrySerializer": "read-only response serializer",
    "BaselineSummarySerializer": (
        "read-only list response serializer for GET /baselines/ (#1078); every "
        "field is read_only, so the route accepts no body to guard"
    ),
    "FieldChangeSerializer": "read-only response serializer",
    "DiffItemSerializer": "read-only response serializer",
    "BaselineDiffSerializer": "read-only response serializer",
    # #1388/M3 + F6: response shapes added for the OpenAPI contract. The CSV
    # import's request body is the inline multipart ``CsvImportUpload`` and the
    # suggestion accept/reject bodies are ``None``/``SuggestionRejectBody`` —
    # never one of these classes.
    "CsvImportReportSerializer": (
        "read-only 200/201/207/422 CSV import report; the route's request body "
        "is an inline multipart serializer, not this one"
    ),
    "CsvImportCountsSerializer": (
        "nested read-only component of CsvImportReportSerializer"
    ),
    "CsvImportItemSerializer": (
        "nested read-only component of CsvImportReportSerializer"
    ),
    "CsvImportItemCauseSerializer": (
        "nested read-only component of CsvImportItemSerializer"
    ),
    "CsvImportRowErrorSerializer": (
        "nested read-only component of CsvImportReportSerializer"
    ),
    "SuggestionSerializer": (
        "read-only 200 receipt of the suggestion list/accept/reject routes; "
        "accept sends no body and reject's body is inline SuggestionRejectBody"
    ),
    # --- rest_api.serializers_diagram -----------------------------------
    "CanvasPointSerializer": "nested child of CanvasStrokeElementSerializer",
    "CanvasStrokeElementSerializer": (
        "nested child of CanvasStrokeDataSerializer; the guard applies at the "
        "top-level request serializer"
    ),
    "CanvasStrokeResponseSerializer": "read-only response serializer",
    "MermaidSourceResponseSerializer": "read-only response serializer",
    "MermaidPreviewResponseSerializer": "read-only response serializer",
    # Node graph serializers exist only for drf-spectacular schema generation;
    # the real validation lives in diagram.node_graph.validate_node_graph().
    "NodeGraphPositionSerializer": "OpenAPI documentation-only serializer",
    "NodeGraphSizeSerializer": "OpenAPI documentation-only serializer",
    "NodeGraphNodeStyleSerializer": "OpenAPI documentation-only serializer",
    "NodeGraphEdgeStyleSerializer": "OpenAPI documentation-only serializer",
    "NodeGraphArtifactRefSerializer": "OpenAPI documentation-only serializer",
    "NodeGraphNodeSerializer": "OpenAPI documentation-only serializer",
    "NodeGraphEdgeSerializer": "OpenAPI documentation-only serializer",
    "NodeGraphViewportSerializer": "OpenAPI documentation-only serializer",
    "NodeGraphPayloadSerializer": "OpenAPI documentation-only serializer",
    # --- other request modules ------------------------------------------
    "UserWorkspacePreferenceSerializer": "read-only response serializer",
    # --- rest_api.audit_views -------------------------------------------
    # #1382: schema-only serializers for the audit response; they describe the
    # 200 body, never a request body, so there is nothing to reject.
    "AuditCountsSerializer": "read-only response serializer (#1382)",
    "AuditPageCountsSerializer": "read-only response serializer (#1382)",
    "AuditFindingSerializer": "read-only response serializer",
    "AuditReportSerializer": (
        "read-only 200 body of GET .../audit/ (#1382); no request body to guard"
    ),
    # --- rest_api.api_key_serializers (M4, #1439 review) ------------------
    # The create request serializer is the bespoke-guarded entry above; every
    # other class in that module only describes a response body.
    "ApiKeyCreateResponseSerializer": "read-only 201 response serializer",
    "ApiKeyMetadataSerializer": "read-only list/retrieve response serializer",
    "ApiKeyValidationErrorDetailSerializer": (
        "OpenAPI documentation-only serializer: one 400 detail entry, never a "
        "request body"
    ),
    "ApiKeyLegacyValidationErrorDetailSerializer": (
        "OpenAPI documentation-only serializer: the historical 400 detail "
        "entry, never a request body"
    ),
    "ApiKeyValidationErrorSerializer": (
        "OpenAPI documentation-only serializer: the 400 inner error object, "
        "never a request body"
    ),
    "ApiKeyErrorResponseSerializer": (
        "OpenAPI documentation-only serializer: the 400 envelope, never a "
        "request body"
    ),
    # --- rest_api.serializers_diagram (#1388 burndown, Diagram/ICD surface) ---
    # DiagramViewSet deliberately has no serializer_class: every handler reads
    # request.data key-by-key and builds its own dict, so no serializer of this
    # module ever validates a request. The two *Request* classes document those
    # key-by-key bodies; the rest describe response bodies.
    "DiagramSerializer": "read-only list projection (#1388)",
    "DiagramDetailSerializer": "read-only retrieve projection (#1388)",
    "DiagramListResponseSerializer": "read-only pagination envelope (#1388)",
    "DiagramVersionResponseSerializer": "read-only 200 body of PATCH /diagrams/{id}/",
    "DiagramCreateRequestSerializer": (
        "OpenAPI documentation-only serializer: POST /diagrams/ reads "
        "request.data key-by-key (no serializer validates it), so the class "
        "describes the body but never guards it"
    ),
    "DiagramUpdateRequestSerializer": (
        "OpenAPI documentation-only serializer: PATCH /diagrams/{id}/ reads "
        "request.data key-by-key (no serializer validates it)"
    ),
    "ArtifactVersionEntrySerializer": "read-only version-list entry (#1388)",
    "ArtifactDiffFieldSerializer": "nested read-only diff entry (#1388)",
    "ArtifactDiffResponseSerializer": "read-only 200 diff body (#1388)",
    "WorkflowTransitionsResponseSerializer": (
        "read-only 200 body of the shared GET …/transitions/ action (#1388)"
    ),
    "WorkflowTransitionRequestSerializer": (
        "OpenAPI documentation-only serializer: the workflow mixin reads "
        "request.data directly (target_state/change_reason/credential), so the "
        "class describes the body but never guards it"
    ),
    "WorkflowTransitionResultSerializer": (
        "read-only 200 body of …/transitions/ POST and …/reactivate/ (#1388)"
    ),
    "WorkflowHistoryEntrySerializer": "read-only workflow audit row (#1388)",
    # --- rest_api.notification_preference_views (#1388 burndown) ------------
    "NotificationPreferenceResponseSerializer": (
        "read-only response serializer; the PATCH body is the guarded "
        "NotificationPreferenceUpdateSerializer"
    ),
    # --- rest_api.architecture_decompose_views (#1388 burndown) -------------
    "DraftRequirementSerializer": "nested read-only draft component (#1388)",
    "DraftNodeSerializer": "nested read-only draft component (#1388)",
    "DecompositionDraftSerializer": (
        "read-only 200 body of the non-persistent decompose draft (#1388); "
        "the request body is the guarded GenerateDraftRequestSerializer"
    ),
    "DecompositionCommitRequestSerializer": (
        "OpenAPI documentation-only envelope: the nested draft is validated by "
        "DecompositionDraft.from_dict, which owns the shape and the 400, so "
        "this class must not second-guess it"
    ),
    "DecompositionCommitResultSerializer": "read-only 201 commit result (#1388)",
    # --- rest_api.audit_views (#1388 burndown, audit/warning surface) ------
    # The four audit views answer service-built dicts (AuditService report
    # views, AiReviewResult, SuppressionView.to_dict, the rule catalogue) and
    # validate their writes with the guarded RemediateRequestSerializer /
    # WaiverCreateSerializer. The classes below describe response bodies only.
    "AuditWaiverSerializer": "read-only waiver row (#1388)",
    "AuditWaiverCountsSerializer": "read-only waiver counts block (#1388)",
    "AuditWaiverListSerializer": "read-only 200 waivers envelope (#1388)",
    "AuditRemediationProposalSerializer": (
        "read-only proposal component of RemediationResult.to_dict (#1388)"
    ),
    "AuditRemediationResultSerializer": "read-only 200 remediate body (#1388)",
    "AuditAiReviewFindingRefSerializer": (
        "read-only compact finding reference (#1388)"
    ),
    "AuditAiReviewPackageSerializer": "read-only package component (#1388)",
    "AuditAiReviewCountsSerializer": "read-only N8 counts block (#1388)",
    "AuditAiReviewResultSerializer": "read-only 200 ai-review body (#1388)",
    "AuditRuleCatalogueEntrySerializer": "read-only catalogue entry (#1388)",
    "AuditRuleCatalogueSerializer": "read-only 200 /audit/rules/ body (#1388)",
    # --- rest_api.settings_views (#1388 burndown, prompt-template surface) --
    "PromptTemplateSlotSerializer": (
        "read-only per-slot state; the PUT body is the guarded "
        "PromptTemplateSlotWriteSerializer"
    ),
    "PromptTemplateSlotListSerializer": "read-only slots envelope (#1388)",
    "PromptTemplateResetRequestSerializer": (
        "OpenAPI documentation-only serializer: SettingsService.reset_prompt_"
        "template reads request.data['slot'] directly and owns the 400 for an "
        "unknown slot name, so the class must not second-guess it"
    ),
    "ContextGraphRebuildStatusSerializer": (
        "read-only 202 acknowledgement body (#1388)"
    ),
    # --- rest_api.prompt_variable_views (#1388 burndown) --------------------
    "PromptVariableSerializer": (
        "read-only per-scope variable state; the PUT body is the guarded "
        "PromptVariableWriteSerializer"
    ),
    "PromptVariableListSerializer": "read-only variables envelope (#1388)",
    # --- rest_api.attribute_config_schema_serializers (#1388 burndown) ---
    # attribute_catalog_views / attribute_definition_views adapt
    # AttributeCatalogService / AttributeDefinitionService: they return the
    # services' dicts unchanged and read every write body from request.data,
    # so no class here validates a request.
    "I18nTextSerializer": "read-only response serializer (#1388)",
    "AttributeOptionSerializer": "read-only response serializer (#1388)",
    "ValidationRulesSerializer": "read-only response serializer (#1388)",
    "AttributeFlowTokenSerializer": "read-only response serializer (#1388)",
    "SectionFlowTokenSerializer": "read-only response serializer (#1388)",
    "SectionSerializer": "read-only response serializer (#1388)",
    "AttributeBlockSerializer": "read-only response serializer (#1388)",
    "GlobalAttributeDefinitionSerializer": "read-only response serializer (#1388)",
    "WorkspaceAttributeDefinitionSerializer": "read-only response serializer (#1388)",
    "AttributeDefinitionDocumentSerializer": "read-only response serializer (#1388)",
    "AttributeDefinitionListSerializer": "read-only response serializer (#1388)",
    "AttributeDefinitionUpdateRequestSerializer": (
        "OpenAPI documentation-only serializer: the view reads request.data key-by-key, so "
        "this class describes the body but never guards it (#1388)"
    ),
    "AttributeReorderRequestSerializer": (
        "OpenAPI documentation-only serializer: the view reads request.data key-by-key, so "
        "this class describes the body but never guards it (#1388)"
    ),
    "AttributeDefinitionVersionSerializer": "read-only response serializer (#1388)",
    "AttributeUsageResponseSerializer": "read-only response serializer (#1388)",
    "AttributeCatalogEntrySerializer": "read-only response serializer (#1388)",
    "AttributeCatalogEntryDocumentSerializer": "read-only response serializer (#1388)",
    "AttributeCatalogListSerializer": "read-only response serializer (#1388)",
    "AttributeCatalogCreateRequestSerializer": (
        "OpenAPI documentation-only serializer: the view reads request.data key-by-key, so "
        "this class describes the body but never guards it (#1388)"
    ),
    "AttributeCatalogUpdateRequestSerializer": (
        "OpenAPI documentation-only serializer: the view reads request.data key-by-key, so "
        "this class describes the body but never guards it (#1388)"
    ),
    "AttributeCatalogDeprecateRequestSerializer": (
        "OpenAPI documentation-only serializer: the view reads request.data key-by-key, so "
        "this class describes the body but never guards it (#1388)"
    ),
    "AttributeCatalogDocumentSerializer": "read-only response serializer (#1388)",
    "AttributeCatalogImportRequestSerializer": (
        "OpenAPI documentation-only serializer: the view reads request.data key-by-key, so "
        "this class describes the body but never guards it (#1388)"
    ),
    "AttributeCatalogImportSummarySerializer": "read-only response serializer (#1388)",
    "AttributeCatalogAddToDefinitionRequestSerializer": (
        "OpenAPI documentation-only serializer: the view reads request.data key-by-key, so "
        "this class describes the body but never guards it (#1388)"
    ),
    "AttributeCatalogAddToDefinitionResponseSerializer": "read-only response serializer (#1388)",
    # --- rest_api.attribute_migration_schema_serializers (#1388 burndown) ---
    # attribute_migration_views adapts AttributeMigrationService and reads
    # the plan from request.data; these classes describe its bodies.
    "MigrationScopeSerializer": "read-only response serializer (#1388)",
    "MigrationScopeEffectSerializer": "read-only response serializer (#1388)",
    "MigrationStepCountsSerializer": "read-only response serializer (#1388)",
    "MigrationTransformCountsSerializer": "read-only response serializer (#1388)",
    "MigrationStepOutcomeSerializer": "read-only response serializer (#1388)",
    "MigrationSummarySerializer": "read-only response serializer (#1388)",
    "MigrationReportSerializer": "read-only response serializer (#1388)",
    "MigrationPlanRequestSerializer": (
        "OpenAPI documentation-only serializer: the view reads request.data key-by-key, so "
        "this class describes the body but never guards it (#1388)"
    ),
    "MigrationRunSerializer": "read-only response serializer (#1388)",
    "MigrationRunListSerializer": "read-only response serializer (#1388)",
    "MigrationRollbackSerializer": "read-only response serializer (#1388)",
    # --- rest_api.link_type_schema_serializers (#1388 burndown) ----------
    # link_type_views reads request.data['key']/['definition'] and delegates
    # to LinkTypeCatalogService; the *Request* class only documents it.
    "LinkTypeLabelSerializer": "read-only response serializer (#1388)",
    "LinkTypePairSerializer": "read-only response serializer (#1388)",
    "LinkTypeDefinitionSerializer": "read-only response serializer (#1388)",
    "GlobalLinkTypeSerializer": "read-only response serializer (#1388)",
    "WorkspaceLinkTypeSerializer": "read-only response serializer (#1388)",
    "LinkTypeWriteRequestSerializer": (
        "OpenAPI documentation-only serializer: the view reads request.data key-by-key, so "
        "this class describes the body but never guards it (#1388)"
    ),
    "GlobalLinkTypePageSerializer": "read-only response serializer (#1388)",
    "WorkspaceLinkTypePageSerializer": "read-only response serializer (#1388)",
    # --- rest_api.platform_schema_serializers (#1388 burndown) -----------
    # response shapes of the platform endpoints (history, bundle,
    # consistency, suggestions, metrics, pending review); none of them is a
    # request body.
    "RequirementHistoryEntrySerializer": "read-only response serializer (#1388)",
    "RequirementHistoryResponseSerializer": "read-only response serializer (#1388)",
    "BundleCompressionStatusSerializer": "read-only response serializer (#1388)",
    "ConsistencyStatusSerializer": "read-only response serializer (#1388)",
    "AttributeSchemaEntrySerializer": "read-only response serializer (#1388)",
    "PendingReviewItemSerializer": "read-only response serializer (#1388)",
    "PendingReviewPageSerializer": "read-only response serializer (#1388)",
    "LinkCandidateSerializer": "read-only response serializer (#1388)",
    "LinkSuggestionSerializer": "read-only response serializer (#1388)",
    "SuggestLinksCountsSerializer": "read-only response serializer (#1388)",
    "SuggestLinksResultSerializer": "read-only response serializer (#1388)",
    "SuggestLinksDispatchSerializer": "read-only response serializer (#1388)",
    "SuggestLinksStatusSerializer": "read-only response serializer (#1388)",
    "MetricsVolatileRequirementSerializer": "read-only response serializer (#1388)",
    "MetricsVolatilitySerializer": "read-only response serializer (#1388)",
    "MetricsCoverageSerializer": "read-only response serializer (#1388)",
    "MetricsVerificationCoverageSerializer": "read-only response serializer (#1388)",
    "MetricsWorkflowGapSerializer": "read-only response serializer (#1388)",
    "MetricsWorkflowGapsSerializer": "read-only response serializer (#1388)",
    "MetricsOpenRisksSerializer": "read-only response serializer (#1388)",
    "MetricsThresholdWarningSerializer": "read-only response serializer (#1388)",
    "MetricsReportSerializer": "read-only response serializer (#1388)",
    "MetricValuesEntrySerializer": "read-only response serializer (#1388)",
    "MetricValuesEnvelopeSerializer": "read-only response serializer (#1388)",
    "MetricCatalogueEntrySerializer": "read-only response serializer (#1388)",
    "MetricCatalogueSerializer": "read-only response serializer (#1388)",
    # --- auth_tenancy.schema_serializers (#1388 burndown) ----------------
    # rest_item_permission / rest_workspace_members read request.data
    # directly and delegate to AuthorizationService; the *Request* classes
    # document those bodies only.
    "ItemPermissionSerializer": "read-only response serializer (#1388)",
    "ItemPermissionGrantRequestSerializer": (
        "OpenAPI documentation-only serializer: the view reads request.data key-by-key, so "
        "this class describes the body but never guards it (#1388)"
    ),
    "ItemPermissionResponseSerializer": "read-only response serializer (#1388)",
    "ItemPermissionListSerializer": "read-only response serializer (#1388)",
    "ItemPermissionRevokeRequestSerializer": (
        "OpenAPI documentation-only serializer: the view reads request.data key-by-key, so "
        "this class describes the body but never guards it (#1388)"
    ),
    "WorkspaceMemberSerializer": "read-only response serializer (#1388)",
    "WorkspaceMemberListSerializer": "read-only response serializer (#1388)",
    "WorkspaceMemberWriteRequestSerializer": (
        "OpenAPI documentation-only serializer: the view reads request.data key-by-key, so "
        "this class describes the body but never guards it (#1388)"
    ),
    "RoleAssignmentResponseSerializer": "read-only response serializer (#1388)",
    "WorkspaceMemberRoleRequestSerializer": (
        "OpenAPI documentation-only serializer: the view reads request.data key-by-key, so "
        "this class describes the body but never guards it (#1388)"
    ),
    "RoleTransitionResponseSerializer": "read-only response serializer (#1388)",
    # --- memory.schema_serializers (#1388 burndown) ----------------------
    # memory_rest spreads the envelope onto service dicts and reads each
    # write body from request.data; the *Request* classes document those
    # bodies.
    "MemorySearchItemSerializer": "read-only response serializer (#1388)",
    "MemorySearchResponseSerializer": "read-only response serializer (#1388)",
    "MemoryEntryViewSerializer": "read-only response serializer (#1388)",
    "MemoryEnvelopeSerializer": "read-only response serializer (#1388)",
    "MemoryEntryListResponseSerializer": "read-only response serializer (#1388)",
    "MemoryScopePurgeResponseSerializer": "read-only response serializer (#1388)",
    "MemoryEntryForgetResponseSerializer": "read-only response serializer (#1388)",
    "MemoryDigestResponseSerializer": "read-only response serializer (#1388)",
    "MemoryAskRequestSerializer": (
        "OpenAPI documentation-only serializer: the view reads request.data key-by-key, so "
        "this class describes the body but never guards it (#1388)"
    ),
    "MemoryAnswerResponseSerializer": "read-only response serializer (#1388)",
    "MemoryEntryPromoteRequestSerializer": (
        "OpenAPI documentation-only serializer: the view reads request.data key-by-key, so "
        "this class describes the body but never guards it (#1388)"
    ),
    "MemorySelfServiceResponseSerializer": "read-only response serializer (#1388)",
    "MemorySelfServiceDeleteResponseSerializer": "read-only response serializer (#1388)",
    "WorkspaceMemorySettingsResponseSerializer": "read-only response serializer (#1388)",
    "WorkspaceMemorySettingsWriteSerializer": (
        "OpenAPI documentation-only serializer: the view reads request.data key-by-key, so "
        "this class describes the body but never guards it (#1388)"
    ),
    "SystemMemorySettingsResponseSerializer": "read-only response serializer (#1388)",
    "MemoryWorkspaceOverviewRowSerializer": "read-only response serializer (#1388)",
    "MemoryWorkspaceOverviewResponseSerializer": "read-only response serializer (#1388)",
    "MemoryWorkspaceDeleteResponseSerializer": "read-only response serializer (#1388)",
    "MemoryAdminEntryRowSerializer": "read-only response serializer (#1388)",
    "MemoryAdminEntryListResponseSerializer": "read-only response serializer (#1388)",
    "MemoryEntryExportResponseSerializer": "read-only response serializer (#1388)",
    "MemoryProjectionPointSerializer": "read-only response serializer (#1388)",
    "MemoryProjectionResponseSerializer": "read-only response serializer (#1388)",
}

#: Modules whose module-local ``*Serializer`` classes are part of the REST
#: request/response contract and therefore subject to the discovery guard.
#: The six ``*_schema_serializers`` / ``schema_serializers`` modules are the
#: #1388 burndown's documentation-only shapes: without them here the guard
#: would not see a single one of their classes, which is precisely the
#: silent-drop path #851 exists to close.
_SERIALIZER_MODULES: tuple[str, ...] = (
    "rest_api.serializers",
    "rest_api.serializers_diagram",
    "rest_api.settings_views",
    "rest_api.preference_views",
    "rest_api.notification_preference_views",
    "rest_api.prompt_variable_views",
    "rest_api.audit_views",
    "rest_api.architecture_decompose_views",
    "rest_api.api_key_serializers",
    # #1388 burndown: schema-only shape modules for the remaining surfaces.
    "rest_api.attribute_config_schema_serializers",
    "rest_api.attribute_migration_schema_serializers",
    "rest_api.link_type_schema_serializers",
    "rest_api.platform_schema_serializers",
    "auth_tenancy.schema_serializers",
    "memory.schema_serializers",
)

#: A complete, valid payload for every serializer newly covered by this pass.
_FULL_PAYLOADS: dict[type, dict] = {
    WorkspaceSerializer: {
        "name": "Full workspace",
        "terminology_profile": "se_mode",
        "language": "en",
        "theme": "dark",
        "decomposition_link_type": "decomposes",
        "default_link_type": "derives-from",
        "goals_enabled": True,
        "goals_ai_enabled": False,
    },
    WorkflowDefinitionSerializer: {
        "workspace_id": str(uuid.uuid4()),
        "artifact_id": str(uuid.uuid4()),
        "name": "Full workflow",
    },
    TestRunSerializer: {
        "workspace_id": str(uuid.uuid4()),
        "name": "Full run",
        "ci_job_id": "ci-42",
        "test_case_ids": [str(uuid.uuid4())],
    },
    TestRunResultSerializer: {
        "test_case_id": str(uuid.uuid4()),
        "status": "passed",
        "message": "all assertions passed",
        "duration_ms": 120,
    },
    TestRunResultBulkSerializer: {
        "results": [
            {
                "test_case_id": str(uuid.uuid4()),
                "status": "passed",
                "message": "entry ok",
                "duration_ms": 5,
            }
        ],
    },
    IcdParameterSerializer: {
        "name": "voltage",
        "description": "bus voltage",
        "unit": "V",
        "data_type": "float",
        "direction": "input",
        "min_value": "0.0",
        "max_value": "10.0",
        "nominal_value": "5.0",
        "tolerance": "0.1",
        "ordering": 0,
        "version": 1,
    },
    CommentSerializer: {"text": "a comment"},
    PreferenceUpdateSerializer: {
        "workspace_id": str(uuid.uuid4()),
        "optional_artifact_visibility": {"goal": True},
    },
    NotificationPreferenceUpdateSerializer: {"preferences": {}},
    PromptVariableWriteSerializer: {
        "value": 3,
        "var_type": "int",
        "description": "how deep",
    },
    LlmSettingsSerializer: {
        "provider": SettingsService.provider_choices()[0],
        "base_url": "",
        "model_name": "model",
        "api_key": "not-a-real-key",
    },
    PromptTemplateSerializer: {
        "need_to_sysreq": "p1",
        "sysreq_to_arch_assign": "p2",
        "sysreq_decompose_next_level": "p3",
        "goal_aggregate": "p4",
    },
    PromptTemplateSlotWriteSerializer: {"content": "prompt text"},
    ReviewPolicySerializer: {
        "mode": SettingsService.review_policy_modes()[0],
        "min_confidence": 0.5,
    },
    ContextGraphSettingsSerializer: {"enabled": True, "enabled_generators": []},
    RemediateRequestSerializer: {
        "rule_id": "TRACE-P1",
        "artifact_ids": ["00000000-0000-0000-0000-000000000001"],
        "scope": "project",
    },
    GenerateDraftRequestSerializer: {
        "element_id": str(uuid.uuid4()),
        "max_breadth": 3,
        "max_depth": 2,
    },
    CanvasStrokeDataSerializer: {
        "strokes": [{"type": "pen"}],
        "width": 800,
        "height": 600,
    },
    MermaidSourceSerializer: {"source": "graph TD; A-->B;"},
}


# ---------------------------------------------------------------------------
# Serializer-level contract for the newly covered serializers
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("serializer_cls", list(_FULL_PAYLOADS))
def test_full_supported_payload_is_accepted(serializer_cls: type) -> None:
    """Positive control: a complete, legitimate payload still validates."""
    serializer = serializer_cls(data=dict(_FULL_PAYLOADS[serializer_cls]))
    assert serializer.is_valid(), serializer.errors


@pytest.mark.parametrize("serializer_cls", list(_FULL_PAYLOADS))
def test_undeclared_key_is_rejected(serializer_cls: type) -> None:
    """A key no declared field accepts is a 400, not a silent drop (#851)."""
    payload = dict(_FULL_PAYLOADS[serializer_cls])
    payload["totally_unknown_key"] = "should be rejected"

    serializer = serializer_cls(data=payload)

    assert not serializer.is_valid()
    assert serializer.errors.get("totally_unknown_key") == ["Unknown field."]


# ---------------------------------------------------------------------------
# Discovery guard
# ---------------------------------------------------------------------------


def _module_local_serializers() -> dict[str, type]:
    """Return ``{module.path.ClassName: class}`` for every module-local serializer."""
    found: dict[str, type] = {}
    for module_name in _SERIALIZER_MODULES:
        module = importlib.import_module(module_name)
        for name, obj in vars(module).items():
            if not inspect.isclass(obj) or not name.endswith("Serializer"):
                continue
            if not issubclass(obj, drf_serializers.Serializer):
                continue
            # Only classes *defined* in that module — ignore re-imports.
            if obj.__module__ != module_name:
                continue
            found[f"{module_name}.{name}"] = obj
    return found


def test_every_serializer_is_classified() -> None:
    """A new write serializer must be guarded or explicitly exempted (#851).

    This is the regression gate: adding a ``*Serializer`` to any of
    :data:`_SERIALIZER_MODULES` without deciding its unknown-field behaviour
    fails here and names the class.
    """
    discovered = _module_local_serializers()
    guarded = {
        f"{cls.__module__}.{cls.__name__}" for cls in _GUARDED_WRITE_SERIALIZERS
    }
    # Bespoke guards are registered by module-qualified key (they deliberately
    # do not inherit the shared mixin) — see _BESPOKE_GUARDED_SERIALIZERS.
    bespoke = set(_BESPOKE_GUARDED_SERIALIZERS)
    # _EXEMPT_SERIALIZERS is keyed by bare class name; resolve each to its
    # module-qualified key so a typo cannot silently exempt nothing.
    exempt = {
        _resolve_exempt_key(name): reason
        for name, reason in _EXEMPT_SERIALIZERS.items()
    }

    classified = guarded | bespoke | set(exempt)
    unclassified = sorted(set(discovered) - classified)
    assert not unclassified, (
        "Unclassified serializers — add UnknownFieldRejectionMixin or an "
        f"entry in _EXEMPT_SERIALIZERS with a reason: {unclassified}"
    )
    stale = sorted(classified - set(discovered))
    assert not stale, f"Classified serializers no longer discovered: {stale}"


def _resolve_exempt_key(class_name: str) -> str:
    """Map a bare exempt class name to its ``module.ClassName`` key."""
    matches = [
        key
        for key in _module_local_serializers()
        if key.rsplit(".", 1)[1] == class_name
    ]
    assert len(matches) == 1, (
        f"_EXEMPT_SERIALIZERS entry {class_name!r} matches {len(matches)} "
        f"serializers; use a unique class name"
    )
    return matches[0]


@pytest.mark.parametrize("serializer_cls", _GUARDED_WRITE_SERIALIZERS)
def test_guarded_serializer_carries_the_mixin(serializer_cls: type) -> None:
    """Every registered write serializer inherits the shared guard."""
    assert issubclass(serializer_cls, UnknownFieldRejectionMixin), (
        f"{serializer_cls.__name__} must inherit UnknownFieldRejectionMixin"
    )


def test_bespoke_guarded_api_key_serializer_rejects_unknown_keys() -> None:
    """The bespoke-guarded entry is guarded in behaviour, not only on paper.

    ``ApiKeyCreateSerializer`` deliberately keeps its own accumulation (#1439)
    instead of :class:`UnknownFieldRejectionMixin`; this pins that the
    classification above still describes a serializer that answers an unknown
    request key with an error rather than dropping it.
    """
    from rest_api.api_key_serializers import ApiKeyCreateSerializer

    serializer = ApiKeyCreateSerializer(data={"name": "ok", "totally_unknown": 1})

    assert not serializer.is_valid()
    assert serializer.errors["totally_unknown"] == ["Unknown field 'totally_unknown'."]


# ---------------------------------------------------------------------------
# Route-level: the raw request.data handlers (#851)
# ---------------------------------------------------------------------------
#
# Icd entity writes have no DRF serializer (the handler builds the
# IcdCreateDTO/IcdUpdateDTO by hand) and the test-run result handlers used to
# read ``request.data`` key by key. Both now run ``reject_unknown_fields``, so
# these tests pin the same 400 envelope the guarded serializer routes produce.

_FAKE_TENANT_ID = uuid.uuid4()
_FAKE_USER_ID = uuid.uuid4()
_FAKE_ICD_ID = uuid.uuid4()


def _http_auth_context() -> AuthContext:
    return AuthContext(
        user_id=_FAKE_USER_ID,
        tenant_id=_FAKE_TENANT_ID,
        active_roles=("admin",),
        auth_method=AuthMethod.BEARER_TOKEN,
    )


_ICD_CREATE_PAYLOAD: dict = {
    "name": "Full ICD",
    "workspace_id": str(uuid.uuid4()),
    "source_element_id": str(uuid.uuid4()),
    "target_element_id": str(uuid.uuid4()),
    "direction": "bidirectional",
    "interface_type": "CAN",
    "semantic_description": "full contract",
    "preconditions": ["power on"],
    "postconditions": ["bus idle"],
    "invariants": ["voltage stable"],
}


def _icd_result_stub() -> MagicMock:
    fake_icd = MagicMock()
    fake_icd.id = _FAKE_ICD_ID
    fake_icd.name = "Full ICD"
    fake_icd.workspace_id = uuid.uuid4()
    fake_icd.source_element_id = uuid.uuid4()
    fake_icd.target_element_id = uuid.uuid4()
    fake_icd.created_at = None
    fake_result = MagicMock()
    fake_result.icd = fake_icd
    fake_result.current_version.version_number = 1
    fake_result.current_version.direction = "bidirectional"
    return fake_result


def _post_icd(payload: dict, create_icd: MagicMock) -> Any:
    factory = APIRequestFactory()
    req = factory.post("/api/v1/icds/", data=payload, format="json")
    req.auth_context = _http_auth_context()
    view = IcdViewSet.as_view({"post": "create"})
    with (
        patch("rest_api.icd_views.get_auth_context", return_value=req.auth_context),
        patch("rest_api.icd_views.get_tenant"),
        patch("rest_api.icd_views.get_user"),
        patch("rest_api.icd_views.create_icd", create_icd),
    ):
        return view(req)


def test_icd_create_with_full_payload_returns_201() -> None:
    """Positive control: every key the create handler reads still passes."""
    response = _post_icd(
        dict(_ICD_CREATE_PAYLOAD), MagicMock(return_value=_icd_result_stub())
    )

    assert response.status_code == 201, response.data


def test_icd_create_rejects_unknown_field() -> None:
    """A key the create handler does not read is a 400, not a silent drop."""
    payload = dict(_ICD_CREATE_PAYLOAD)
    payload["not_a_real_icd_field"] = "dropped"
    create_icd = MagicMock()

    response = _post_icd(payload, create_icd)

    assert response.status_code == 400, response.data
    assert response.data["error"]["code"] == "VALIDATION_ERROR"
    details = {d["field"]: d["errors"] for d in response.data["error"]["details"]}
    assert details["not_a_real_icd_field"] == ["Unknown field."]
    create_icd.assert_not_called()


def _patch_icd(payload: dict, update_icd: MagicMock) -> Any:
    factory = APIRequestFactory()
    req = factory.patch(
        f"/api/v1/icds/{_FAKE_ICD_ID}/", data=payload, format="json"
    )
    req.auth_context = _http_auth_context()
    view = IcdViewSet.as_view({"patch": "partial_update"})
    with (
        patch("rest_api.icd_views.get_auth_context", return_value=req.auth_context),
        patch("rest_api.icd_views.get_user"),
        patch("rest_api.icd_views.update_icd", update_icd),
    ):
        return view(req, pk=str(_FAKE_ICD_ID))


def test_icd_partial_update_with_full_payload_returns_200() -> None:
    """Positive control: the update handler's accepted keys still pass."""
    response = _patch_icd(
        {"semantic_description": "v2", "name": "Renamed ICD"},
        MagicMock(return_value=_icd_result_stub()),
    )

    assert response.status_code == 200, response.data


def test_icd_partial_update_rejects_unknown_field() -> None:
    update_icd = MagicMock()

    response = _patch_icd(
        {"semantic_description": "v2", "not_a_real_icd_field": "dropped"},
        update_icd,
    )

    assert response.status_code == 400, response.data
    assert response.data["error"]["code"] == "VALIDATION_ERROR"
    details = {d["field"]: d["errors"] for d in response.data["error"]["details"]}
    assert details["not_a_real_icd_field"] == ["Unknown field."]
    update_icd.assert_not_called()


def _test_run_result_stub() -> MagicMock:
    test_case = MagicMock()
    test_case.id = uuid.uuid4()
    test_case.title = "TC-Login"
    result = MagicMock()
    result.id = uuid.uuid4()
    result.test_run_id = uuid.uuid4()
    result.test_case = test_case
    result.test_case_id = test_case.id
    result.test_case_title = test_case.title
    result.status = "passed"
    result.message = ""
    result.duration_ms = 12
    result.executed_at = None
    result.version = 1
    result.created_at = None
    result.created_by = None
    return result


def _post_test_run_results(action: str, data: dict, svc: MagicMock) -> Any:
    # Lazy import: a module-level ``TestRunViewSet`` would be collected by
    # pytest as a test class (its name starts with "Test").
    from rest_api.views import TestRunViewSet

    factory = APIRequestFactory()
    pk = str(uuid.uuid4())
    req = factory.post(
        f"/api/v1/test-runs/{pk}/results/", data=data, format="json"
    )
    req.auth_context = _http_auth_context()
    view = TestRunViewSet.as_view({"post": action})
    with patch.object(TestRunViewSet, "_svc", return_value=svc):
        return view(req, pk=pk)


@pytest.mark.django_db
def test_test_run_single_result_with_full_payload_returns_201() -> None:
    """Positive control: the /results/ handler's accepted keys still pass."""
    svc = MagicMock()
    svc.add_result.return_value = _test_run_result_stub()

    response = _post_test_run_results(
        "results",
        {
            "test_case_id": str(uuid.uuid4()),
            "status": "passed",
            "message": "all good",
            "duration_ms": 12,
        },
        svc,
    )

    assert response.status_code == 201, response.data
    svc.add_result.assert_called_once()


@pytest.mark.django_db
def test_test_run_single_result_rejects_unknown_field() -> None:
    """A key the /results/ handler does not read is now a 400 (#851)."""
    svc = MagicMock()

    response = _post_test_run_results(
        "results",
        {
            "test_case_id": str(uuid.uuid4()),
            "status": "passed",
            "not_a_real_result_field": "dropped",
        },
        svc,
    )

    assert response.status_code == 400, response.data
    assert response.data["error"]["code"] == "VALIDATION_ERROR"
    details = {d["field"]: d["errors"] for d in response.data["error"]["details"]}
    assert details["not_a_real_result_field"] == ["Unknown field."]
    svc.add_result.assert_not_called()


@pytest.mark.django_db
def test_test_run_bulk_results_with_full_payload_returns_201() -> None:
    """Positive control: the /results/bulk/ handler's accepted keys still pass."""
    svc = MagicMock()
    svc.add_results_bulk.return_value = [_test_run_result_stub()]

    response = _post_test_run_results(
        "results_bulk",
        {
            "results": [
                {
                    "test_case_id": str(uuid.uuid4()),
                    "status": "failed",
                    "message": "assertion failed",
                    "duration_ms": 3,
                }
            ]
        },
        svc,
    )

    assert response.status_code == 201, response.data
    svc.add_results_bulk.assert_called_once()


@pytest.mark.django_db
def test_test_run_bulk_results_rejects_unknown_top_level_field() -> None:
    svc = MagicMock()

    response = _post_test_run_results(
        "results_bulk",
        {
            "results": [
                {"test_case_id": str(uuid.uuid4()), "status": "passed"}
            ],
            "not_a_real_bulk_field": "dropped",
        },
        svc,
    )

    assert response.status_code == 400, response.data
    assert response.data["error"]["code"] == "VALIDATION_ERROR"
    details = {d["field"]: d["errors"] for d in response.data["error"]["details"]}
    assert details["not_a_real_bulk_field"] == ["Unknown field."]
    svc.add_results_bulk.assert_not_called()


@pytest.mark.django_db
def test_test_run_bulk_results_rejects_unknown_entry_field() -> None:
    """The guard reaches each nested batch entry, not just the top level."""
    svc = MagicMock()

    response = _post_test_run_results(
        "results_bulk",
        {
            "results": [
                {
                    "test_case_id": str(uuid.uuid4()),
                    "status": "passed",
                    "not_a_real_entry_field": "dropped",
                }
            ]
        },
        svc,
    )

    assert response.status_code == 400, response.data
    assert response.data["error"]["code"] == "VALIDATION_ERROR"
    assert any(
        d["field"] == "results" for d in response.data["error"]["details"]
    )
    svc.add_results_bulk.assert_not_called()
