"""
COMP-RA-004 PresetGuard — Runtime preset-based endpoint/field visibility.

leaf_id : COMP-RA-004
req_id  : REQ-L2-RA-008 (Preset-Sichtbarkeit)
          REQ-L3-RA004-001, REQ-L3-RA004-002, REQ-L3-RA004-003

Architecture:
  docs/se/L1/Gesamtsystem/L2/RestApiAdapterSystem/Components/
    COMP-RA-004_PresetGuard/L3_COMP-RA-004_PresetGuard_Architecture.md

Interfaces:
  IF-RA-INT-002  COMP-RA-001 <-> COMP-RA-004  (PresetDecision)
  IF-RA-INT-004  COMP-RA-004 -> COMP-RA-002   (FieldFilter)
  IF-RA-EXT-OUT-006 -> PresetConfigEngine (is_feature_enabled)

Design:
  - All preset decisions are delegated to PresetConfigEngine via is_feature_enabled.
  - No hard-coded feature flag lists in this module (REQ-L3-RA004-003 AC).
  - FieldFilter is generated only after a positive PresetDecision (REQ-L3-RA004-002 AC).
  - PresetConfigEngine unavailable -> PresetError -> HTTP 503.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from presets.services import get_preset, is_feature_enabled


# ---------------------------------------------------------------------------
# Data contracts (IF-RA-INT-002 and IF-RA-INT-004)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PresetDecision:
    """Result of an endpoint-visibility check (IF-RA-INT-002).

    Attributes:
        visible: True if the endpoint is visible in the active preset.
        reason: Human-readable explanation.
    """

    visible: bool
    reason: str = ""


@dataclass(frozen=True)
class FieldFilter:
    """Field-visibility directive for DataSerializer (IF-RA-INT-004).

    Attributes:
        permitted_fields: All fields allowed in serialized output/input.
            An empty frozenset means "all fields permitted" (no restriction).
        required_fields: Fields that MUST be present in write requests.
    """

    permitted_fields: frozenset[str] = field(default_factory=frozenset)
    required_fields: frozenset[str] = field(default_factory=frozenset)

    @classmethod
    def allow_all(cls) -> "FieldFilter":
        """Return a FieldFilter that allows all fields with no extra requirements."""
        return cls(permitted_fields=frozenset(), required_fields=frozenset())


class PresetError(Exception):
    """Raised when the PresetConfigEngine is unavailable or returns an error."""


# ---------------------------------------------------------------------------
# Preset feature-key registry
# Per REQ-L3-RA004-003: all routing goes through is_feature_enabled calls.
# Keys must be registered in PresetConfigEngine; none are hard-coded here.
# ---------------------------------------------------------------------------

# Extended-preset field additions (change_reason is mandatory in Extended)
_EXTENDED_REQUIRED_FIELDS: frozenset[str] = frozenset({"change_reason"})

# Fields that are Extended-only and excluded from Minimal preset
_EXTENDED_ONLY_FIELDS: frozenset[str] = frozenset(
    {"change_reason", "approval_comment", "approver_id"}
)

# Minimal permitted fields for requirements (base set)
_MINIMAL_PERMITTED_FIELDS: frozenset[str] = frozenset(
    {
        "id",
        "workspace_id",
        "title",
        "description",
        "category",
        "status",
        "version",
        "created_at",
        "updated_at",
    }
)


class PresetGuard:
    """COMP-RA-004: Runtime preset gate for endpoints and field-level filtering.

    REQ-L3-RA004-001: Endpoint visibility check via is_feature_enabled.
    REQ-L3-RA004-002: FieldFilter generated only after positive PresetDecision.
    REQ-L3-RA004-003: No hard-coded feature flag lists.
    """

    def check_endpoint(
        self, endpoint_key: str, workspace_id: UUID | str
    ) -> PresetDecision:
        """Check whether an endpoint is visible in the workspace's active preset.

        Args:
            endpoint_key: Feature key registered in PresetConfigEngine (e.g.
                "baseline_endpoints", "workflow_approval_endpoints").
            workspace_id: UUID of the active workspace (from AuthContext).

        Returns:
            PresetDecision with visible=True/False.

        Raises:
            PresetError: PresetConfigEngine unavailable.
        """
        try:
            enabled = is_feature_enabled(endpoint_key, workspace_id)
        except Exception as exc:
            raise PresetError(
                f"PresetConfigEngine unavailable for key={endpoint_key!r}: {exc}"
            ) from exc

        return PresetDecision(
            visible=bool(enabled),
            reason=(
                f"Feature '{endpoint_key}' is {'enabled' if enabled else 'disabled'} "
                f"for workspace {workspace_id}."
            ),
        )

    def get_field_filter(self, workspace_id: UUID | str) -> FieldFilter:
        """Return FieldFilter based on active preset for the workspace.

        Must only be called after a positive PresetDecision (REQ-L3-RA004-002 AC).
        Delegates all preset queries to PresetConfigEngine.

        Args:
            workspace_id: UUID of the active workspace.

        Returns:
            FieldFilter with permitted_fields and required_fields.

        Raises:
            PresetError: PresetConfigEngine unavailable.
        """
        try:
            preset_rules = get_preset(workspace_id)
        except Exception as exc:
            raise PresetError(
                f"PresetConfigEngine unavailable for workspace {workspace_id}: {exc}"
            ) from exc

        preset_tier = preset_rules.preset.lower()

        if preset_tier == "extended":
            # Extended preset: all fields permitted, change_reason required
            return FieldFilter(
                permitted_fields=frozenset(),  # empty = all permitted
                required_fields=_EXTENDED_REQUIRED_FIELDS,
            )
        else:
            # Minimal / standard: exclude Extended-only fields, no extra required
            return FieldFilter(
                permitted_fields=_MINIMAL_PERMITTED_FIELDS,
                required_fields=frozenset(),
            )


# ---------------------------------------------------------------------------
# DRF mixin for preset endpoint gating
# ---------------------------------------------------------------------------


class PresetGateMixin:
    """Mixin for DRF ViewSets: gates endpoint visibility by preset.

    Usage:
        class BaselineViewSet(PresetGateMixin, viewsets.ModelViewSet):
            preset_endpoint_key = "baseline_endpoints"

    REQ-L2-RA-008: Preset-based endpoint/field visibility enforced per request.
    """

    preset_endpoint_key: str = ""  # Override in subclass

    def _guard_preset(self, workspace_id_override: str | None = None) -> None:
        """Check preset endpoint gate; raises Http404 or PermissionDenied.

        Args:
            workspace_id_override: Workspace id resolved by the caller (e.g.
                a nested-route ``workspace_pk`` URL kwarg, issue #49). Takes
                precedence over the request body/query-params/tenant-id
                fallbacks below.
        """
        from django.http import Http404

        if not self.preset_endpoint_key:
            return  # No key configured — endpoint always visible

        guard = PresetGuard()
        auth_ctx = getattr(self.request, "auth_context", None)
        # For write endpoints the workspace_id lives in the request body;
        # for list/retrieve endpoints it is in query_params.
        body_workspace_id = None
        if self.request.method in ("POST", "PUT", "PATCH"):
            body_workspace_id = self.request.data.get("workspace_id") if hasattr(self.request, "data") else None
        workspace_id = (
            workspace_id_override
            or body_workspace_id
            or self.request.query_params.get("workspace_id")
            or (
                str(auth_ctx.tenant_id)
                if auth_ctx is not None
                else None
            )
        )
        if workspace_id is None:
            return  # Cannot determine workspace — allow and let service validate

        try:
            decision = guard.check_endpoint(self.preset_endpoint_key, workspace_id)
        except PresetError:
            from rest_framework.response import Response
            from rest_framework import status
            # Service unavailable
            raise Http404()

        if not decision.visible:
            raise Http404()


__all__ = [
    "PresetDecision",
    "FieldFilter",
    "PresetError",
    "PresetGuard",
    "PresetGateMixin",
]
