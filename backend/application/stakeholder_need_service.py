"""
StakeholderNeedService — Stakeholder Need CRUD.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from uuid import UUID

from auth_tenancy.context import AuthContext
from django.db.models import F
from persistence.models import Artifact, StakeholderNeed, Tenant, Workspace
from persistence.transactions import atomic_transaction

from application.base import (
    NotFoundError,
    ServiceBase,
    ValidationError,
)
from application.models import DomainEventOutbox

logger = logging.getLogger(__name__)

_UNSET = object()

@dataclass
class StakeholderNeedDTO:
    """Read-oriented DTO returned by StakeholderNeedService methods."""
    id: UUID
    workspace_id: UUID
    title: str
    description: str
    category: str
    status: str
    moscow_priority: Optional[str]
    version: int

    @classmethod
    def from_orm(cls, need: StakeholderNeed) -> "StakeholderNeedDTO":
        return cls(
            id=need.id,
            workspace_id=need.artifact.workspace_id,
            title=need.title,
            description=need.description,
            category=need.category,
            status=need.status,
            moscow_priority=need.moscow_priority,
            version=need.version,
        )


class StakeholderNeedService(ServiceBase):
    """StakeholderNeed CRUD service."""

    def __init__(self, preset_policy_service=None):
        self.preset_policy_service = preset_policy_service

    @atomic_transaction
    def create(
        self,
        ctx: AuthContext,
        workspace_id: UUID | str,
        title: str,
        description: str = "",
        category: str = "",
        status: str = "draft",
        moscow_priority: str | None = None,
    ) -> StakeholderNeedDTO:
        try:
            workspace = Workspace.objects.get(id=workspace_id, tenant_id=ctx.tenant_id)
        except Workspace.DoesNotExist:
            raise NotFoundError(f"Workspace {workspace_id} not found.")

        # Pre-flight check for change reason
        if self.preset_policy_service:
            if self.preset_policy_service.is_change_reason_required(
                workspace, "stakeholder_need", "create", None
            ):
                raise ValidationError("change_reason is required by preset policy.")

        artifact = Artifact.objects.create(
            workspace=workspace,
            artifact_type="StakeholderNeed",
            tenant_id=ctx.tenant_id,
            created_by=ctx.user,
        )
        need = StakeholderNeed.objects.create(
            artifact=artifact,
            tenant_id=ctx.tenant_id,
            title=title,
            description=description,
            category=category,
            status=status,
            moscow_priority=moscow_priority,
            created_by=ctx.user,
        )

        DomainEventOutbox.publish(
            ctx.tenant_id,
            "StakeholderNeedCreated",
            str(need.id),
            {"workspace_id": str(workspace.id), "title": need.title},
        )
        return StakeholderNeedDTO.from_orm(need)

    def get(self, ctx: AuthContext, need_id: UUID | str) -> StakeholderNeedDTO:
        try:
            need = StakeholderNeed.objects.select_related("artifact").get(
                id=need_id, tenant_id=ctx.tenant_id
            )
            return StakeholderNeedDTO.from_orm(need)
        except StakeholderNeed.DoesNotExist:
            raise NotFoundError(f"StakeholderNeed {need_id} not found.")

    def list_by_workspace(
        self, ctx: AuthContext, workspace_id: UUID | str
    ) -> List[StakeholderNeedDTO]:
        needs = StakeholderNeed.objects.select_related("artifact").filter(
            tenant_id=ctx.tenant_id, artifact__workspace_id=workspace_id
        )
        return [StakeholderNeedDTO.from_orm(n) for n in needs]

    @atomic_transaction
    def update(
        self,
        ctx: AuthContext,
        need_id: UUID | str,
        title: str | Any = _UNSET,
        description: str | Any = _UNSET,
        category: str | Any = _UNSET,
        status: str | Any = _UNSET,
        moscow_priority: str | Any = _UNSET,
        change_reason: str = "",
    ) -> StakeholderNeedDTO:
        try:
            need = StakeholderNeed.objects.select_related("artifact__workspace").get(
                id=need_id, tenant_id=ctx.tenant_id
            )
        except StakeholderNeed.DoesNotExist:
            raise NotFoundError(f"StakeholderNeed {need_id} not found.")

        if self.preset_policy_service:
            if self.preset_policy_service.is_change_reason_required(
                need.artifact.workspace, "stakeholder_need", "update", change_reason
            ):
                raise ValidationError("change_reason is required by preset policy.")

        changes = {}
        if title is not _UNSET:
            need.title = title
            changes["title"] = title
        if description is not _UNSET:
            need.description = description
            changes["description"] = description
        if category is not _UNSET:
            need.category = category
            changes["category"] = category
        if status is not _UNSET:
            need.status = status
            changes["status"] = status
        if moscow_priority is not _UNSET:
            need.moscow_priority = moscow_priority
            changes["moscow_priority"] = moscow_priority

        if changes:
            need.version = F("version") + 1
            need.modified_by = ctx.user
            need.save()
            need.refresh_from_db()

            DomainEventOutbox.publish(
                ctx.tenant_id,
                "StakeholderNeedUpdated",
                str(need.id),
                {"changes": list(changes.keys()), "change_reason": change_reason},
            )

        return StakeholderNeedDTO.from_orm(need)

    @atomic_transaction
    def delete(
        self, ctx: AuthContext, need_id: UUID | str, change_reason: str = ""
    ) -> None:
        try:
            need = StakeholderNeed.objects.select_related("artifact__workspace").get(
                id=need_id, tenant_id=ctx.tenant_id
            )
        except StakeholderNeed.DoesNotExist:
            raise NotFoundError(f"StakeholderNeed {need_id} not found.")

        if self.preset_policy_service:
            if self.preset_policy_service.is_change_reason_required(
                need.artifact.workspace, "stakeholder_need", "delete", change_reason
            ):
                raise ValidationError("change_reason is required by preset policy.")

        workspace_id = need.artifact.workspace_id
        # Artifact cascades to StakeholderNeed
        need.artifact.delete()

        DomainEventOutbox.publish(
            ctx.tenant_id,
            "StakeholderNeedDeleted",
            str(need_id),
            {"workspace_id": str(workspace_id), "change_reason": change_reason},
        )

    def derive_requirements_async(self, ctx: AuthContext, need_id: UUID | str) -> Dict[str, Any]:
        """Trigger an async LLM task to derive system requirements from a stakeholder need.

        Returns:
            Dict containing the task_id.
        """
        try:
            need = StakeholderNeed.objects.select_related("artifact").get(
                id=need_id, tenant_id=ctx.tenant_id
            )
        except StakeholderNeed.DoesNotExist:
            raise NotFoundError(f"StakeholderNeed {need_id} not found.")

        from llm_adapter.services import derive_requirements
        response = derive_requirements(str(need_id))
        
        if "error" in response:
            raise ValueError(
                f"LLM derivation dispatch failed: {response['error'].get('message', response)}"
            )

        return response
