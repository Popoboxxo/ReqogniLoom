"""Request/response contracts for the ADR-028 release cascade.

Kept beside the views (not in the general ``serializers`` module) because they
describe one cohesive feature and are only used by ``release_views``.
"""

from __future__ import annotations

from rest_framework import serializers


class ReleaseRequestSerializer(serializers.Serializer):
    """Body of both release routes."""

    change_reason = serializers.CharField(
        required=True,
        allow_blank=False,
        help_text=(
            "Audit reason recorded on every workflow transition of the cascade."
        ),
    )


class ReleaseImpactSerializer(serializers.Serializer):
    """Read-only preview returned by ``GET .../release-impact/``."""

    element_id = serializers.UUIDField()
    release_state = serializers.CharField(
        allow_null=True,
        help_text="The workspace state carrying freeze_on_enter, or null when none is configured.",
    )
    allowed_source_states = serializers.ListField(child=serializers.CharField())
    descendant_elements = serializers.IntegerField()
    requirements_total = serializers.IntegerField()
    requirements_releasable = serializers.IntegerField()
    requirements_by_state = serializers.DictField(
        child=serializers.IntegerField(),
        help_text="Requirement count per current workflow state.",
    )
    content_freeze = serializers.BooleanField(
        help_text="True when the workspace preset is extended (content snapshots)."
    )
    async_required = serializers.BooleanField(
        help_text="True when the cascade exceeds the synchronous item limit."
    )
    conflicts = serializers.IntegerField(
        help_text="Requirements with more than one active allocation.",
    )


class ReleaseResultSerializer(serializers.Serializer):
    """Result of an element release."""

    element_id = serializers.UUIDField()
    release_state = serializers.CharField()
    elements_released = serializers.IntegerField()
    requirements_released = serializers.IntegerField()
    content_freeze = serializers.BooleanField()


class RequirementReleaseResultSerializer(serializers.Serializer):
    """Result of a single-requirement release (D10 special case)."""

    requirement_id = serializers.UUIDField()
    release_state = serializers.CharField()
    released = serializers.BooleanField(
        help_text="False when the requirement was already released (no-op success)."
    )
    reason = serializers.CharField(required=False)


class ReleaseConflictDetailSerializer(serializers.Serializer):
    """One actionable detail entry of a ``RELEASE_NOT_ALLOWED`` (409)."""

    field = serializers.CharField()
    required_action = serializers.CharField()
    change_request_url = serializers.CharField()
    reason = serializers.CharField()


class ReleaseErrorBodySerializer(serializers.Serializer):
    """Inner error object; unique name so drf-spectacular cannot confuse it
    with the generic ``ErrorBodySerializer`` from ``rest_api.openapi``."""

    code = serializers.CharField()
    message = serializers.CharField()
    details = serializers.ListField(
        child=ReleaseConflictDetailSerializer(), required=False
    )


class ReleaseErrorSerializer(serializers.Serializer):
    """Standard error envelope (REQ-L2-RA-009) for the release routes."""

    error = ReleaseErrorBodySerializer()
