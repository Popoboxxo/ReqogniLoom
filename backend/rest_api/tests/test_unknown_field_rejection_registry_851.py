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

import pytest
from rest_framework import serializers as drf_serializers

from application.settings_service import SettingsService
from rest_api.architecture_decompose_views import GenerateDraftRequestSerializer
from rest_api.audit_views import RemediateRequestSerializer
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
)

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
    "FieldChangeSerializer": "read-only response serializer",
    "DiffItemSerializer": "read-only response serializer",
    "BaselineDiffSerializer": "read-only response serializer",
    "TestRunResultSerializer": (
        "not wired to a REST write path: the /results/ and /results/bulk/ "
        "endpoints read request.data directly"
    ),
    "TestRunResultBulkSerializer": (
        "not wired to a REST write path: the /results/bulk/ endpoint reads "
        "request.data directly"
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
}

#: Modules whose module-local ``*Serializer`` classes are part of the REST
#: request/response contract and therefore subject to the discovery guard.
_SERIALIZER_MODULES: tuple[str, ...] = (
    "rest_api.serializers",
    "rest_api.serializers_diagram",
    "rest_api.settings_views",
    "rest_api.preference_views",
    "rest_api.notification_preference_views",
    "rest_api.prompt_variable_views",
    "rest_api.audit_views",
    "rest_api.architecture_decompose_views",
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
    # _EXEMPT_SERIALIZERS is keyed by bare class name; resolve each to its
    # module-qualified key so a typo cannot silently exempt nothing.
    exempt = {
        _resolve_exempt_key(name): reason
        for name, reason in _EXEMPT_SERIALIZERS.items()
    }

    classified = guarded | set(exempt)
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
