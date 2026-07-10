"""
COMP-AS-003 ArchitectureService — ArchitectureElement CRUD with versioning.

leaf_id : COMP-AS-003
req_id  : REQ-L2-AS-004 (ArchitectureElement CRUD with Versioning)

Manages ArchitectureElement entities with:
  - Automatic version increment on each update
  - Optimistic locking (OptimisticLockError on stale version)
  - Cascade TraceLink deletion on delete

Interfaces consumed:
  IF-AS-INT-004     TraceLinkService.cascade_delete_trace_links (on delete)
  IF-AS-INT-010     DomainEventBus → ArchitectureElementCreated/Updated/Deleted
  IF-AS-EXT-OUT-007 persistence.models.ArchitectureElement (Django ORM)

Architecture:
  docs/se/L1/Gesamtsystem/L2/ApplicationServiceSystem/
    Components/COMP-AS-003_ArchitectureService/
      L3_COMP-AS-003_ArchitectureService_Architecture.md
"""
from __future__ import annotations

import logging
from typing import List, Optional
from uuid import UUID

from django.db.models import F

from auth_tenancy.context import AuthContext
from persistence.models import ArchitectureElement, Artifact, ElementType, Tenant, Workspace
from persistence.transactions import atomic_transaction

from application.artifact_service import _clean_custom_fields
from application.base import NotFoundError, OptimisticLockError, ServiceBase, ValidationError
from application.models import DomainEventOutbox
from application.validators import ArchitectureElementInvariantValidator

logger = logging.getLogger(__name__)

# Sentinel distinguishing "parameter omitted" from "set parent to None (root)"
_UNSET = object()


class ArchitectureService(ServiceBase):
    """COMP-AS-003 — ArchitectureElement lifecycle management."""

    # Supported element types — derived from ElementType TextChoices enum
    VALID_ELEMENT_TYPES = frozenset(ElementType.values)

    def __init__(self, trace_link_service=None) -> None:
        from application.trace_link_service import TraceLinkService

        self._trace_link_service = trace_link_service or TraceLinkService()

    # ---------- helpers ----------

    @staticmethod
    def _validate_element_type(element_type: str) -> str:
        """Validate and normalize *element_type* to a lowercase enum value.

        Accepts both exact lowercase values (``"component"``) and legacy
        PascalCase labels (``"Component"``).  Raises ``ValidationError``
        for anything outside the ElementType enum (e.g. ``"banane"``).
        """
        normalized = (element_type or "").strip().lower()
        if normalized not in ArchitectureService.VALID_ELEMENT_TYPES:
            raise ValidationError(
                f"Invalid element_type '{element_type}'. "
                f"Allowed values: {', '.join(sorted(ElementType.values))}"
            )
        return normalized

    # ---------- CRUD (REQ-L2-AS-004) ----------

    @atomic_transaction
    def create_architecture_element(
        self,
        workspace_id: UUID,
        title: str,
        ctx: AuthContext,
        description: str = "",
        element_type: str = ElementType.COMPONENT,
        parent_id: Optional[UUID] = None,
        asil_level: Optional[str] = None,
        make_or_buy: Optional[str] = None,
        uid: Optional[str] = None,
        custom_fields: Optional[dict] = None,
    ) -> ArchitectureElement:
        """Create an ArchitectureElement with initial version=1.

        REQ-L2-AS-004 acceptance: create → version=1, initial WorkflowState.
        REQ-L3-RF004-004: Accepts ASIL level and Make-or-Buy decision.
        REQ-L2-RF-025 AC3: Accepts uid for stable identification.
        """
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)

        # Validate element_type against enum (rejects "banane" etc.)
        element_type = self._validate_element_type(element_type)

        # Tenant and Workspace are imported at module level to allow test mocking.
        tenant = Tenant.objects.filter(id=ctx.tenant_id).first()
        if tenant is None:
            raise NotFoundError(f"Tenant {ctx.tenant_id} not found")

        workspace = Workspace.objects.filter(id=workspace_id).first()
        if workspace is None:
            raise NotFoundError(f"Workspace {workspace_id} not found")

        artifact = Artifact.objects.create(
            tenant=tenant,
            workspace=workspace,
            artifact_type="ArchitectureElement",
            custom_fields=_clean_custom_fields(custom_fields),
        )

        # REQ-L1-044: hierarchy invariants I1/I3, rigor-gated via workspace preset.
        # I3 replaces the former plain existence check and additionally rejects
        # cross-workspace parents (behavior change: 400 instead of 404 for a
        # dangling parent_id).
        if parent_id is not None:
            validator = ArchitectureElementInvariantValidator.for_workspace(workspace_id)
            validator.validate_parent_assignment(
                parent_id=parent_id, workspace_id=workspace_id
            )

        arch_el = ArchitectureElement.objects.create(
            tenant=tenant,
            artifact=artifact,
            title=title,
            description=description,
            element_type=element_type,
            parent_id=parent_id,
            version=1,
            asil_level=asil_level,
            make_or_buy=make_or_buy,
            uid=uid,
        )

        # Initialise workflow state
        try:
            from workflow.services import initialize_workflow_states

            initialize_workflow_states(
                item_ids=[arch_el.id],
                item_type="ArchitectureElement",
                workspace_id=workspace_id,
                ctx=ctx,
            )
        except Exception:
            logger.debug(
                "ArchitectureService: workflow init skipped for arch_el=%s", arch_el.id
            )

        self._audit(ctx=ctx, operation="create", entity_type="ArchitectureElement", entity_id=arch_el.id)
        self._emit_event(
            self._make_event(
                event_type=DomainEventOutbox.EventType.ARCHITECTURE_ELEMENT_CREATED,
                entity_id=arch_el.id,
                workspace_id=workspace_id,
                payload={"title": title, "element_type": element_type},
            )
        )
        return arch_el

    @atomic_transaction
    def update_architecture_element(
        self,
        arch_el_id: UUID,
        ctx: AuthContext,
        expected_version: int | None = None,
        title: Optional[str] = None,
        description: Optional[str] = None,
        element_type: Optional[str] = None,
        parent_id: object = _UNSET,
        asil_level: Optional[str] = _UNSET,
        make_or_buy: Optional[str] = _UNSET,
        uid: Optional[str] = _UNSET,
        custom_fields: object = _UNSET,
    ) -> ArchitectureElement:
        """Update an ArchitectureElement with optimistic locking.

        REQ-L2-AS-004: version incremented on every update; stale
        expected_version → OptimisticLockError.  When *expected_version* is
        omitted, no optimistic lock check is performed (backwards-compatible
        path for callers that do not track versions).

        REQ-L1-044: when *parent_id* is provided (UUID or None to detach),
        the hierarchy invariants I1-I3 are enforced according to the
        workspace's rigor preset before the new parent is persisted.

        REQ-L3-RF004-004: Accepts ASIL level and Make-or-Buy decision.
        REQ-L2-RF-025 AC3: Accepts uid for stable identification.
        """
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)

        arch_el = ArchitectureElement.objects.select_related("artifact").filter(
            id=arch_el_id
        ).first()
        if arch_el is None:
            raise NotFoundError(f"ArchitectureElement {arch_el_id} not found")

        # Optimistic lock check (REQ-L2-AS-004)
        if expected_version is not None and arch_el.version != expected_version:
            raise OptimisticLockError(
                f"Stale version: expected {expected_version}, "
                f"current is {arch_el.version}"
            )

        changed_fields: dict = {}
        if title is not None:
            arch_el.title = title
            changed_fields["title"] = title
        if description is not None:
            arch_el.description = description
            changed_fields["description"] = description
        if element_type is not None:
            arch_el.element_type = self._validate_element_type(element_type)
            changed_fields["element_type"] = arch_el.element_type
        if asil_level is not _UNSET:
            arch_el.asil_level = asil_level
            changed_fields["asil_level"] = asil_level
        if make_or_buy is not _UNSET:
            arch_el.make_or_buy = make_or_buy
            changed_fields["make_or_buy"] = make_or_buy
        if uid is not _UNSET:
            arch_el.uid = uid
            changed_fields["uid"] = uid

        # REQ-L2-AS-037: custom_fields lives on the backing Artifact, not on the
        # ArchitectureElement row — persist it separately from changed_fields.
        if custom_fields is not _UNSET:
            arch_el.artifact.custom_fields = _clean_custom_fields(custom_fields)
            arch_el.artifact.save(update_fields=["custom_fields", "modified_at"])

        # REQ-L1-044: invariant checks (I1-I3) before re-parenting
        if parent_id is not _UNSET:
            if parent_id is not None:
                workspace_id = arch_el.artifact.workspace_id
                validator = ArchitectureElementInvariantValidator.for_workspace(
                    workspace_id
                )
                validator.validate_parent_assignment(
                    parent_id=parent_id,
                    element=arch_el,
                    element_id=arch_el_id,
                    workspace_id=workspace_id,
                )
            arch_el.parent_id = parent_id
            changed_fields["parent_id"] = parent_id

        # Atomic version increment + field persistence — guarded by
        # expected_version when provided.  Changed fields are written in the
        # same UPDATE (fix: they were previously assigned in memory only).
        current_version = expected_version if expected_version is not None else arch_el.version
        ArchitectureElement.objects.filter(id=arch_el_id, version=current_version).update(
            version=F("version") + 1, **changed_fields
        )
        arch_el.refresh_from_db(fields=["version"])

        self._audit(ctx=ctx, operation="update", entity_type="ArchitectureElement", entity_id=arch_el_id)
        self._emit_event(
            self._make_event(
                event_type=DomainEventOutbox.EventType.ARCHITECTURE_ELEMENT_UPDATED,
                entity_id=arch_el_id,
                workspace_id=arch_el.artifact.workspace_id,
            )
        )
        return arch_el

    @atomic_transaction
    def delete_architecture_element(self, arch_el_id: UUID, ctx: AuthContext) -> None:
        """Delete ArchitectureElement + cascade TraceLinks (IF-AS-INT-004)."""
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)

        arch_el = ArchitectureElement.objects.select_related("artifact").filter(
            id=arch_el_id
        ).first()
        if arch_el is None:
            raise NotFoundError(f"ArchitectureElement {arch_el_id} not found")

        workspace_id = arch_el.artifact.workspace_id
        artifact_id = arch_el.artifact_id

        # IF-AS-INT-004
        self._trace_link_service.cascade_delete_trace_links(
            UUID(str(artifact_id)), ctx
        )

        arch_el.delete()

        self._audit(ctx=ctx, operation="delete", entity_type="ArchitectureElement", entity_id=arch_el_id)
        self._emit_event(
            self._make_event(
                event_type=DomainEventOutbox.EventType.ARCHITECTURE_ELEMENT_DELETED,
                entity_id=arch_el_id,
                workspace_id=workspace_id,
            )
        )

    def get_architecture_element(self, arch_el_id: UUID, ctx: AuthContext) -> ArchitectureElement:
        """Fetch a single ArchitectureElement."""
        self._set_tenant_context(ctx)
        arch_el = ArchitectureElement.objects.select_related("artifact").filter(
            id=arch_el_id
        ).first()
        if arch_el is None:
            raise NotFoundError(f"ArchitectureElement {arch_el_id} not found")
        return arch_el

    def list_architecture_elements(
        self, workspace_id: UUID, ctx: AuthContext
    ) -> List[ArchitectureElement]:
        """Return all ArchitectureElements in *workspace_id*."""
        self._set_tenant_context(ctx)
        return list(
            ArchitectureElement.objects.select_related("artifact").filter(
                artifact__workspace_id=workspace_id
            )
        )


__all__ = ["ArchitectureService"]
