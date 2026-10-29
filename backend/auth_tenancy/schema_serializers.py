"""OpenAPI shapes for the workspace-authorization REST surface (#1388).

:mod:`auth_tenancy.rest_item_permission` and
:mod:`auth_tenancy.rest_workspace_members` are plain ``APIView`` adapters over
``ItemPermissionService`` / ``AuthorizationService``: they hand the services'
dicts to ``Response`` unchanged and validate their writes in place. These
serializers describe those shapes for the generated contract only; nothing is
rendered through them at runtime.

Transcribed from ``rest_item_permission._permission_to_dict``,
``rest_workspace_members._member_to_dict`` and the bodies the two views read.
Keeping them here mirrors :mod:`admin_ops.schema_serializers`: the adapters stay
free of DRF-serializer imports (they are plain ``APIView``s by design) while the
contract is still published.
"""
from __future__ import annotations

from rest_framework import serializers

__all__ = [
    "ItemPermissionGrantRequestSerializer",
    "ItemPermissionResponseSerializer",
    "ItemPermissionRevokeRequestSerializer",
    "ItemPermissionSerializer",
    "ItemPermissionListSerializer",
    "RoleAssignmentResponseSerializer",
    "RoleTransitionResponseSerializer",
    "WorkspaceMemberRoleRequestSerializer",
    "WorkspaceMemberSerializer",
    "WorkspaceMemberListSerializer",
    "WorkspaceMemberWriteRequestSerializer",
]

#: ``_VALID_LEVELS`` — the item-permission levels a client may grant.
_PERMISSION_LEVELS = ["read", "write", "none"]
#: The roles ``AuthorizationService.assign_role`` accepts (preset-gated).
_ROLES = ["admin", "editor", "viewer", "approver"]


class ItemPermissionSerializer(serializers.Serializer):
    """One ``ItemPermission`` row (``_permission_to_dict``)."""

    id = serializers.CharField()
    user_id = serializers.CharField()
    workspace_id = serializers.CharField()
    artifact_id = serializers.CharField(
        allow_null=True,
        help_text="Null for a workspace-wide rule.",
    )
    permission_level = serializers.ChoiceField(choices=_PERMISSION_LEVELS)
    granted_by = serializers.CharField(allow_null=True)
    is_workspace_wide = serializers.BooleanField()
    is_explicit_deny = serializers.BooleanField()


class ItemPermissionGrantRequestSerializer(serializers.Serializer):
    """Body of ``POST .../permissions/`` (grant or upsert one rule)."""

    user_id = serializers.CharField()
    artifact_id = serializers.CharField(
        required=False,
        allow_null=True,
        help_text="Omit or null for a workspace-wide rule.",
    )
    permission_level = serializers.ChoiceField(choices=_PERMISSION_LEVELS)


class ItemPermissionResponseSerializer(serializers.Serializer):
    """201 body of the grant route."""

    permission = ItemPermissionSerializer()


class ItemPermissionListSerializer(serializers.Serializer):
    """``GET .../permissions/?user_id=…`` envelope."""

    permissions = ItemPermissionSerializer(many=True)


class ItemPermissionRevokeRequestSerializer(serializers.Serializer):
    """Body of ``DELETE .../permissions/``.

    The id may also travel as the ``permission_id`` query parameter, which is
    the fallback for clients that cannot send a DELETE body.
    """

    permission_id = serializers.CharField()


class WorkspaceMemberSerializer(serializers.Serializer):
    """One workspace member (``_member_to_dict``)."""

    user_id = serializers.CharField()
    username = serializers.CharField()
    email = serializers.CharField(allow_blank=True)
    display_name = serializers.CharField(allow_blank=True)
    roles = serializers.ListField(
        child=serializers.CharField(),
        help_text="The member's active roles in this workspace.",
    )


class WorkspaceMemberListSerializer(serializers.Serializer):
    """``GET .../members/`` envelope."""

    members = WorkspaceMemberSerializer(many=True)


class WorkspaceMemberWriteRequestSerializer(serializers.Serializer):
    """Body of ``POST .../members/`` — assign a role to a user.

    A ``preset`` field sent by older clients is ignored: the view resolves the
    workspace's real preset server-side (fix round 1, C-2), so it is not part of
    the contract.
    """

    user_id = serializers.CharField()
    role = serializers.ChoiceField(choices=_ROLES)


class RoleAssignmentResponseSerializer(serializers.Serializer):
    """201 body of ``POST .../members/``."""

    assigned = serializers.BooleanField()


class WorkspaceMemberRoleRequestSerializer(serializers.Serializer):
    """Body of the suspend/reactivate routes — which role to change."""

    role = serializers.ChoiceField(choices=_ROLES)


class RoleTransitionResponseSerializer(serializers.Serializer):
    """200 body of ``.../members/{user_id}/suspend|reactivate/``.

    The two routes share one handler and answer a key named after the action
    (``{"suspend": true}`` / ``{"reactivate": true}``), so both are optional
    here.
    """

    suspend = serializers.BooleanField(
        required=False, help_text="Present on the suspend route.",
    )
    reactivate = serializers.BooleanField(
        required=False, help_text="Present on the reactivate route.",
    )
