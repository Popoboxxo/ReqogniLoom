"""Visual requirement groups (P6, V11).

A group is a plain ``Artifact`` of type ``Group`` (no workflow entity) whose
title/description live in ``custom_fields``. Membership is a ``grouped-in``
TraceLink (Requirement -> Group); a requirement may be in several groups. The
membership order is ``TraceLink.sort_key`` (nullable, filled only for
``grouped-in``).

Groups are purely visual: they never change ``tier_key``, ``level_source`` or an
allocation.
"""
from __future__ import annotations

from uuid import UUID

from django.db import transaction

from application.base import NotFoundError, ServiceBase, ValidationError
from auth_tenancy.context import AuthContext
from persistence.models import Artifact, Requirement, TraceLink
from persistence.sort_keys import key_between

_GROUP_TYPE = "Group"
_MEMBER_LINK = "grouped-in"


class GroupService(ServiceBase):
    """Create groups and manage their ordered membership."""

    def create(
        self,
        workspace_id: UUID,
        title: str,
        ctx: AuthContext,
        *,
        description: str = "",
    ) -> Artifact:
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)
        if not title.strip():
            raise ValidationError("Group title must not be empty.")
        from persistence.models import Tenant, Workspace

        tenant = Tenant.objects.filter(id=ctx.tenant_id).first()
        workspace = Workspace.objects.filter(id=workspace_id).first()
        if tenant is None or workspace is None:
            raise NotFoundError(f"Workspace {workspace_id} not found")
        return Artifact.objects.create(
            tenant=tenant,
            workspace=workspace,
            artifact_type=_GROUP_TYPE,
            custom_fields={"title": title, "description": description},
        )

    def list_groups(self, workspace_id: UUID, ctx: AuthContext) -> list[Artifact]:
        self._set_tenant_context(ctx)
        return list(
            Artifact.objects.filter(
                workspace_id=workspace_id, artifact_type=_GROUP_TYPE
            ).order_by("created_at", "id")
        )

    def _group(self, group_id: UUID) -> Artifact:
        group = Artifact.objects.filter(
            id=group_id, artifact_type=_GROUP_TYPE
        ).first()
        if group is None:
            raise NotFoundError(f"Group {group_id} not found")
        return group

    def _requirement_artifact_id(self, requirement_id: UUID) -> UUID:
        row = (
            Requirement.objects.filter(id=requirement_id)
            .values_list("artifact_id", flat=True)
            .first()
        )
        if row is None:
            raise NotFoundError(f"Requirement {requirement_id} not found")
        return row

    def add_member(
        self,
        group_id: UUID,
        requirement_id: UUID,
        ctx: AuthContext,
        *,
        after_id: UUID | None = None,
    ) -> TraceLink:
        """Add a requirement to *group*, optionally behind *after_id*."""
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)
        group = self._group(group_id)
        requirement_artifact_id = self._requirement_artifact_id(requirement_id)

        if TraceLink.objects.filter(
            source_id=requirement_artifact_id,
            target_id=group.id,
            link_type=_MEMBER_LINK,
        ).exists():
            raise ValidationError("Requirement is already a member of this group.")

        before_key = None
        after_key = None
        if after_id is not None:
            anchor = TraceLink.objects.filter(
                id=after_id, target_id=group.id, link_type=_MEMBER_LINK
            ).first()
            if anchor is None:
                raise ValidationError("after_id is not a member of this group.")
            before_key = anchor.sort_key
        else:
            last = (
                TraceLink.objects.filter(
                    target_id=group.id, link_type=_MEMBER_LINK
                )
                .exclude(sort_key__isnull=True)
                .order_by("-sort_key")
                .first()
            )
            before_key = last.sort_key if last else None
            after_key = None

        with transaction.atomic():
            return TraceLink.objects.create(
                tenant_id=group.tenant_id,
                source_id=requirement_artifact_id,
                target_id=group.id,
                link_type=_MEMBER_LINK,
                sort_key=key_between(before_key, after_key),
            )

    def remove_member(
        self, group_id: UUID, requirement_id: UUID, ctx: AuthContext
    ) -> None:
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)
        group = self._group(group_id)
        requirement_artifact_id = self._requirement_artifact_id(requirement_id)
        TraceLink.objects.filter(
            source_id=requirement_artifact_id,
            target_id=group.id,
            link_type=_MEMBER_LINK,
        ).delete()

    def move_member(
        self,
        group_id: UUID,
        requirement_id: UUID,
        ctx: AuthContext,
        *,
        after_id: UUID | None = None,
    ) -> TraceLink:
        """Reorder an existing member (one-row write on ``TraceLink.sort_key``)."""
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)
        group = self._group(group_id)
        requirement_artifact_id = self._requirement_artifact_id(requirement_id)
        row = TraceLink.objects.filter(
            source_id=requirement_artifact_id,
            target_id=group.id,
            link_type=_MEMBER_LINK,
        ).first()
        if row is None:
            raise NotFoundError("Requirement is not a member of this group.")

        if after_id is None:
            following = (
                TraceLink.objects.filter(target_id=group.id, link_type=_MEMBER_LINK)
                .exclude(id=row.id)
                .exclude(sort_key__isnull=True)
                .order_by("sort_key")
                .first()
            )
            before_key, after_key = None, (following.sort_key if following else None)
        else:
            anchor = (
                TraceLink.objects.filter(
                    id=after_id, target_id=group.id, link_type=_MEMBER_LINK
                )
                .exclude(id=row.id)
                .first()
            )
            if anchor is None:
                raise ValidationError("after_id is not a member of this group.")
            next_member = (
                TraceLink.objects.filter(
                    target_id=group.id,
                    link_type=_MEMBER_LINK,
                    sort_key__gt=anchor.sort_key,
                )
                .exclude(id=row.id)
                .order_by("sort_key")
                .first()
            )
            before_key = anchor.sort_key
            after_key = next_member.sort_key if next_member else None

        new_key = key_between(before_key, after_key)
        TraceLink.objects.filter(id=row.id).update(sort_key=new_key)
        row.sort_key = new_key
        return row

    def members(self, group_id: UUID, ctx: AuthContext) -> list[dict]:
        self._set_tenant_context(ctx)
        self._group(group_id)
        result = []
        for link in TraceLink.objects.filter(
            target_id=group_id, link_type=_MEMBER_LINK
        ).order_by("sort_key", "created_at", "id"):
            result.append(
                {
                    "trace_link_id": str(link.id),
                    "requirement_artifact_id": str(link.source_id),
                    "sort_key": link.sort_key,
                }
            )
        return result
