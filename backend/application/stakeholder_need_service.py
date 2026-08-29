"""
StakeholderNeedService — Stakeholder Need CRUD.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from auth_tenancy.context import AuthContext
from django.db.models import F, Q
from persistence.models import Artifact, StakeholderNeed, Tenant, Workspace
from persistence.transactions import atomic_transaction

from application.artifact_service import (
    _clean_custom_fields,
    has_field_changes,
    snapshot_versioned_fields,
)
from application.base import (
    NotFoundError,
    ServiceBase,
    ValidationError,
)
from application.optimistic_lock import (
    assert_expected_version,
    lock_for_version_check,
)

logger = logging.getLogger(__name__)

_UNSET = object()

@dataclass
class StakeholderNeedDTO:
    """Read-oriented DTO returned by StakeholderNeedService methods."""

    id: UUID
    workspace_id: UUID
    artifact_id: UUID  # REQ-001: required by diff/versions endpoints in views.py
    parent_id: Optional[UUID]
    title: str
    description: str
    category: str
    status: str
    moscow_priority: Optional[str]
    uid: Optional[str]
    suspect: bool
    version: int
    created_at: datetime
    modified_at: datetime
    custom_fields: dict = None  # REQ-L2-AS-037: user-defined attributes

    @classmethod
    def from_orm(cls, need: StakeholderNeed) -> "StakeholderNeedDTO":
        return cls(
            id=need.id,
            workspace_id=need.artifact.workspace_id,
            artifact_id=need.artifact_id,  # REQ-001: expose FK for diff/versions lookup
            # TODO (hierarchy consolidation): Artifact.parent is deprecated —
            # StakeholderNeedService never populates it, so this is always
            # None in practice. Hierarchy is expressed via 'derives-from'
            # TraceLinks; prefer TraceLinkService for consumers that need
            # need-to-need parentage.
            parent_id=need.artifact.parent_id,
            title=need.title,
            description=need.description,
            category=need.category,
            status=need.status,
            moscow_priority=need.moscow_priority,
            uid=need.uid,
            suspect=need.suspect,
            version=need.version,
            created_at=need.created_at,
            modified_at=need.modified_at,
            custom_fields=getattr(need.artifact, "custom_fields", None) or {},
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


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
        custom_fields: dict | None = None,
    ) -> StakeholderNeedDTO:
        # REQ-022 (S-03): RBAC gate — must come before any domain logic.
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)

        try:
            workspace = Workspace.objects.get(id=workspace_id, tenant_id=ctx.tenant_id)
        except Workspace.DoesNotExist:
            raise NotFoundError(f"Workspace {workspace_id} not found.")


        artifact = Artifact.objects.create(
            workspace=workspace,
            artifact_type="StakeholderNeed",
            tenant_id=ctx.tenant_id,
            created_by_id=ctx.user_id,
            custom_fields=_clean_custom_fields(custom_fields),
        )
        need = StakeholderNeed.objects.create(
            artifact=artifact,
            tenant_id=ctx.tenant_id,
            title=title,
            description=description,
            category=category,
            status=status,
            moscow_priority=moscow_priority,
            created_by_id=ctx.user_id,
        )

        self._emit_event(
            self._make_event(
                event_type="StakeholderNeedCreated",
                entity_id=need.id,
                workspace_id=workspace.id,
                # artifact_id: additive, for context_graph.projector (Issue #377).
                payload={"title": need.title, "artifact_id": str(artifact.id)},
            )
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
        self,
        ctx: AuthContext,
        workspace_id: UUID | str,
        include_deleted: bool = False,
        search: str | None = None,
    ) -> List[StakeholderNeedDTO]:
        """Return StakeholderNeeds in workspace_id.

        REQ-006: Excludes soft-deleted needs (lifecycle_status='deleted') by default.
        Pass include_deleted=True for admin/audit access.

        Issue #267 (same root cause as RequirementService.list_requirements):
        ``search`` case-insensitively filters on title/description/uid.
        """
        needs = StakeholderNeed.objects.select_related("artifact").filter(
            tenant_id=ctx.tenant_id, artifact__workspace_id=workspace_id
        )
        if not include_deleted:
            # Phase 0: outdate() mirrors the "outdated" state into `status`,
            # not `lifecycle_status` (StakeholderNeed is registered in
            # workflow.lifecycle_manager._STATUS_MIRROR_MODELS).
            needs = needs.exclude(status="outdated")
        if search:
            needs = needs.filter(
                Q(title__icontains=search)
                | Q(description__icontains=search)
                | Q(uid__icontains=search)
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
        custom_fields: Any = _UNSET,
        expected_version: int | None = None,
    ) -> StakeholderNeedDTO:
        """Update a StakeholderNeed.

        SYSTEMAUDIT_2026-08-29 REST finding 1: ``expected_version`` carries the
        caller's last-seen ``version``. When supplied and stale, the update is
        refused with ``OptimisticLockError`` (409 CONFLICT) instead of silently
        overwriting a concurrent edit. Omitting it keeps the previous
        last-writer-wins behaviour.
        """
        try:
            need = lock_for_version_check(
                StakeholderNeed.objects.select_related("artifact__workspace"),
                expected_version,
            ).get(id=need_id, tenant_id=ctx.tenant_id)
        except StakeholderNeed.DoesNotExist:
            raise NotFoundError(f"StakeholderNeed {need_id} not found.")
        assert_expected_version(
            need, expected_version, entity_type="StakeholderNeed"
        )

        if self.preset_policy_service:
            if self.preset_policy_service.is_change_reason_required(str(need.artifact.workspace_id)):
                if not change_reason:
                    raise ValidationError("change_reason is required by preset policy.")

        # #269 finding 5: ``changes`` below records which fields were *supplied*,
        # which is what the emitted event should name — but it is not a safe
        # trigger for the version bump, because re-sending a field with its
        # current value is a no-op. Snapshot the real column values instead.
        _before = snapshot_versioned_fields(need)
        _custom_fields_changed = False

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

        # REQ-L2-AS-037: custom_fields lives on the backing Artifact, so it is
        # outside the StakeholderNeed snapshot and compared separately.
        if custom_fields is not _UNSET:
            cleaned_custom_fields = _clean_custom_fields(custom_fields)
            _custom_fields_changed = (
                cleaned_custom_fields != (need.artifact.custom_fields or {})
            )
            need.artifact.custom_fields = cleaned_custom_fields
            need.artifact.save(update_fields=["custom_fields", "modified_at"])
            changes["custom_fields"] = True

        # Both conditions matter, and neither implies the other: ``changes``
        # keeps "no field was supplied at all" a silent no-op (no event, no
        # bump), while the value comparison additionally catches a field that
        # was supplied but carries its current value (#269 finding 5).
        if changes and (has_field_changes(need, _before) or _custom_fields_changed):
            need.version = F("version") + 1
            # REQ-159: AuthContext exposes user_id, not user.
            need.modified_by_id = ctx.user_id
            need.save()
            need.refresh_from_db()

            self._emit_event(
                self._make_event(
                    event_type="StakeholderNeedUpdated",
                    entity_id=need.id,
                    workspace_id=need.artifact.workspace_id,
                    # artifact_id: additive, for context_graph.projector (Issue #377).
                    payload={
                        "changes": list(changes.keys()),
                        "change_reason": change_reason,
                        "artifact_id": str(need.artifact_id),
                    },
                )
            )

        return StakeholderNeedDTO.from_orm(need)

    @atomic_transaction
    def delete(
        self, ctx: AuthContext, need_id: UUID | str, change_reason: str = ""
    ) -> None:
        """Soft-delete StakeholderNeed via the workflow engine's outdate() (REQ-006, Phase 0).

        Physical deletion intentionally avoided — Hard-delete available only via
        Django admin.
        """
        try:
            need = StakeholderNeed.objects.select_related("artifact__workspace").get(
                id=need_id, tenant_id=ctx.tenant_id
            )
        except StakeholderNeed.DoesNotExist:
            raise NotFoundError(f"StakeholderNeed {need_id} not found.")

        if self.preset_policy_service:
            if self.preset_policy_service.is_change_reason_required(str(need.artifact.workspace_id)):
                if not change_reason:
                    raise ValidationError("change_reason is required by preset policy.")

        workspace_id = need.artifact.workspace_id

        from workflow.services import outdate

        outdate(
            item_id=need.id,
            item_type="StakeholderNeed",
            workspace_id=workspace_id,
            ctx=ctx,
            reason="deleted via needs.delete",
        )

        self._emit_event(
            self._make_event(
                event_type="StakeholderNeedDeleted",
                entity_id=need_id,
                workspace_id=workspace_id,
                payload={"change_reason": change_reason},
            )
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
