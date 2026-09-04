"""
COMP-AS-013 AdrService — Architecture Decision Record CRUD.

leaf_id : COMP-AS-013
req_id  : REQ-L1-029

Orchestrates:
  IF-AS-INT-002   TraceLinkService.create_trace_link / cascade_delete_trace_links
  IF-AS-INT-003   WorkflowFacade.transition (status transitions)
  IF-AS-INT-015   DomainEventBus → AdrCreated/Updated/Deleted (Outbox)
  IF-AS-EXT-OUT-007  application.models.Adr (Django ORM — plain, no TenantScopedModel)

Architecture:
  docs/se/L1/Gesamtsystem/L2/ApplicationServiceSystem/
    Components/COMP-AS-013_AdrService/
      L3_COMP-AS-013_AdrService_Architecture.md

ADR-L3-ADR-01: Append-Only versioning (version counter incremented on update).
ADR-L3-ADR-02: TraceLinks as separate entities via TraceLinkService.
ADR-L3-ADR-03: All mutations inside atomic transactions.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List, Optional
from uuid import UUID

from auth_tenancy.context import AuthContext
from django.db.models import F, QuerySet
from persistence.transactions import atomic_transaction

from application.artifact_service import (
    has_field_changes,
    snapshot_versioned_fields,
)
from application.base import NotFoundError, ServiceBase, ValidationError
from application.models import Adr, DomainEventOutbox
from application.optimistic_lock import (
    assert_expected_version,
    lock_for_version_check,
)
from traceability.types import LinkType
from workflow import state_reader

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# DTOs
# ---------------------------------------------------------------------------


@dataclass
class AdrDTO:
    """Read-oriented DTO returned by AdrService methods.

    leaf_id : COMP-AS-013
    req_id  : REQ-L1-029
    """

    id: UUID
    workspace_id: UUID
    tenant_id: UUID
    title: str
    description: str
    context: str
    decision: str
    consequences: str
    status: str
    version: int

    @classmethod
    def from_orm(cls, adr: Adr, *, status: str = "") -> "AdrDTO":
        """Build a DTO. ``status`` comes from the workflow engine (Phase 1)."""
        resolved_status = status
        return cls(
            id=adr.id,
            workspace_id=adr.workspace_id,
            tenant_id=adr.tenant_id,
            title=adr.title,
            description=adr.description,
            context=adr.context,
            decision=adr.decision,
            consequences=adr.consequences,
            status=resolved_status,
            version=adr.version,
        )


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------


class AdrValidator:
    """Schema validation for ADR payloads (REQ-L3-ADR-009).

    leaf_id : COMP-AS-013
    req_id  : REQ-L1-029
    """

    # REQ-006: "Deleted" is a soft-delete marker set by delete_adr(); users
    # must not be able to create or manually set status to "Deleted" via the API.
    VALID_STATUSES = frozenset(s for s in Adr.Status.values if s != Adr.Status.DELETED)

    @classmethod
    def validate_create(
        cls, title: str, description: str, status: str = "Draft"
    ) -> None:
        """Validate fields for ADR creation."""
        if not title or len(title) < 3:
            raise ValidationError("ADR title must be at least 3 characters")
        if len(title) > 200:
            raise ValidationError("ADR title must not exceed 200 characters")
        if len(description) > 10000:
            raise ValidationError("ADR description must not exceed 10,000 characters")
        if status not in cls.VALID_STATUSES:
            raise ValidationError(
                f"ADR status '{status}' invalid; must be one of {sorted(cls.VALID_STATUSES)}"
            )


# ---------------------------------------------------------------------------
# AdrService
# ---------------------------------------------------------------------------


class AdrService(ServiceBase):
    """COMP-AS-013 — Architecture Decision Record CRUD with Workflow and TraceLinks.

    leaf_id : COMP-AS-013
    req_id  : REQ-L1-029
    """

    def __init__(
        self,
        trace_link_service=None,
    ) -> None:
        from application.trace_link_service import TraceLinkService

        self._trace_link_service = trace_link_service or TraceLinkService()

    # ---------- CRUD ----------

    @atomic_transaction
    def create_adr(
        self,
        workspace_id: UUID,
        title: str,
        description: str,
        ctx: AuthContext,
        context: str = "",
        decision: str = "",
        consequences: str = "",
        status: str = "Draft",
        uid: Optional[str] = None,
    ) -> Adr:
        """Create an ADR with initial workflow state (REQ-L3-ADR-001).

        Args:
            workspace_id: Target workspace UUID.
            title: ADR title (3–200 chars).
            description: Full ADR description (max 10,000 chars).
            ctx: Resolved AuthContext (tenant + roles).
            context: Optional context section (max 5,000 chars).
            decision: Optional decision section (max 5,000 chars) — the
                standard ADR "Decision" text (#373).
            consequences: Optional consequences section (max 5,000 chars).
            status: Initial status (default: Draft).

        Returns:
            Persisted Adr ORM instance.
        """
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)

        AdrValidator.validate_create(title=title, description=description, status=status)

        # REQ-L2-TE-020: create the backing Artifact first so the ADR can
        # participate in the Artifact-to-Artifact TraceLink graph. Mirrors
        # RequirementService.create_requirement's Artifact pattern.
        from persistence.models import Artifact, Tenant, Workspace

        tenant = Tenant.objects.filter(id=ctx.tenant_id).first()
        if tenant is None:
            raise NotFoundError(f"Tenant {ctx.tenant_id} not found")

        workspace = Workspace.objects.filter(id=workspace_id).first()
        if workspace is None:
            raise NotFoundError(f"Workspace {workspace_id} not found")

        artifact = Artifact.objects.create(
            tenant=tenant,
            workspace=workspace,
            artifact_type="Adr",
        )

        # Datenmodell-Konsolidierung: the `status` column is no longer read by
        # any service-layer consumer (WorkflowItemState.current_state is
        # authoritative, seeded below by initialize_workflow_states() from the
        # workflow definition's own initial_state — not from this argument).
        # `status` is still validated above so bad input is rejected, but it
        # is deliberately not written here; the model field's own default
        # keeps the column non-null until it is dropped (Task 12).
        adr = Adr.objects.create(
            artifact=artifact,
            workspace_id=workspace_id,
            tenant_id=ctx.tenant_id,
            title=title,
            description=description,
            context=context,
            decision=decision,
            consequences=consequences,
            uid=uid,
            created_by=str(ctx.user_id),
        )

        # Initialize workflow state (IF-AS-EXT-OUT-001)
        try:
            from workflow.services import initialize_workflow_states

            initialize_workflow_states(
                item_ids=[adr.id],
                item_type="Adr",
                workspace_id=workspace_id,
                ctx=ctx,
            )
        except Exception:
            logger.debug("AdrService: workflow init skipped for adr=%s", adr.id)

        self._audit(ctx=ctx, operation="create", entity_type="Adr", entity_id=adr.id)
        self._emit_event(
            self._make_event(
                event_type=DomainEventOutbox.EventType.ADR_CREATED,
                entity_id=adr.id,
                workspace_id=workspace_id,
                # artifact_id: additive, for context_graph.projector (Issue #377).
                payload={"title": title, "artifact_id": str(artifact.id)},
            )
        )
        return adr

    @atomic_transaction
    def update_adr(
        self,
        adr_id: UUID,
        ctx: AuthContext,
        title: Optional[str] = None,
        description: Optional[str] = None,
        context: Optional[str] = None,
        decision: Optional[str] = None,
        consequences: Optional[str] = None,
        change_reason: Optional[str] = None,
        expected_version: Optional[int] = None,
    ) -> Adr:
        """Update an ADR, incrementing its version (REQ-L3-ADR-002, ADR-L3-ADR-01).

        Args:
            adr_id: UUID of the ADR to update.
            ctx: Resolved AuthContext.
            title: New title (optional).
            description: New description (optional).
            context: New context section (optional).
            decision: New decision section (optional, #373).
            consequences: New consequences section (optional).
            change_reason: Optional change rationale for audit.
            expected_version: Caller's last-seen ``version``. When supplied and
                stale, the update is refused with ``OptimisticLockError`` (409)
                instead of overwriting a concurrent edit. Omitting it keeps the
                previous last-writer-wins behaviour.

        Returns:
            Updated Adr ORM instance.

        Raises:
            OptimisticLockError: *expected_version* does not match the stored one.
        """
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)

        adr = lock_for_version_check(
            Adr.objects.filter(id=adr_id, tenant_id=ctx.tenant_id), expected_version
        ).first()
        if adr is None:
            raise NotFoundError(f"ADR {adr_id} not found")
        assert_expected_version(adr, expected_version, entity_type="Adr")

        # #269 finding 5: snapshot BEFORE any assignment so the version bump
        # below can be gated on a real value change.
        _before = snapshot_versioned_fields(adr)

        if title is not None:
            if not title or len(title) < 3:
                raise ValidationError("ADR title must be at least 3 characters")
            adr.title = title
        if description is not None:
            if len(description) > 10000:
                raise ValidationError("ADR description must not exceed 10,000 characters")
            adr.description = description
        if context is not None:
            adr.context = context
        if decision is not None:
            adr.decision = decision
        if consequences is not None:
            adr.consequences = consequences

        # Atomic version increment (REQ-L3-PL001-002): save payload fields first,
        # then issue a single SQL UPDATE that increments version at the database
        # level — avoids the read-modify-write race condition of `version += 1`.
        # #269 finding 5: only a real value change is a new revision.
        adr.save()
        if has_field_changes(adr, _before):
            Adr.objects.filter(id=adr.id).update(version=F("version") + 1)
            adr.refresh_from_db(fields=["version"])

        self._audit(
            ctx=ctx,
            operation="update",
            entity_type="Adr",
            entity_id=adr_id,
            change_reason=change_reason,
        )
        self._emit_event(
            self._make_event(
                event_type=DomainEventOutbox.EventType.ADR_UPDATED,
                entity_id=adr_id,
                workspace_id=adr.workspace_id,
                # artifact_id: additive, for context_graph.projector (Issue #377).
                payload={
                    "change_reason": change_reason,
                    "version": adr.version,
                    "artifact_id": str(adr.artifact_id),
                },
            )
        )
        return adr

    @atomic_transaction
    def delete_adr(self, adr_id: UUID, ctx: AuthContext) -> None:
        """Soft-delete ADR by setting status to 'Deleted' (REQ-006).

        Physical deletion is intentionally avoided for end-user operations.
        The ADR and its backing Artifact remain in the database; TraceLinks
        are preserved for audit trail purposes. Hard-delete is available only
        via the Django admin panel.

        Args:
            adr_id: UUID of the ADR to soft-delete.
            ctx: Resolved AuthContext.
        """
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)

        adr = Adr.objects.filter(id=adr_id, tenant_id=ctx.tenant_id).first()
        if adr is None:
            raise NotFoundError(f"ADR {adr_id} not found")

        workspace_id = adr.workspace_id

        # REQ-006/Phase 0: route soft-delete through the workflow engine's
        # outdate() escape hatch instead of writing status directly.
        from workflow.services import outdate

        outdate(
            item_id=adr.id,
            item_type="Adr",
            workspace_id=workspace_id,
            ctx=ctx,
            reason="deleted via adr.delete",
        )

        self._audit(ctx=ctx, operation="delete", entity_type="Adr", entity_id=adr_id)
        self._emit_event(
            self._make_event(
                event_type=DomainEventOutbox.EventType.ADR_DELETED,
                entity_id=adr_id,
                workspace_id=workspace_id,
            )
        )

    def get_adr(self, adr_id: UUID, ctx: AuthContext) -> Adr:
        """Fetch a single ADR (tenant-scoped, REQ-L3-ADR-008).

        Args:
            adr_id: UUID of the ADR to retrieve.
            ctx: Resolved AuthContext.

        Returns:
            Adr ORM instance.
        """
        self._set_tenant_context(ctx)
        adr = Adr.objects.filter(id=adr_id, tenant_id=ctx.tenant_id).first()
        if adr is None:
            raise NotFoundError(f"ADR {adr_id} not found")
        return adr

    def list_adrs(
        self, workspace_id: UUID, ctx: AuthContext, include_deleted: bool = False
    ) -> QuerySet[Adr]:
        """Return ADRs in *workspace_id* (tenant-scoped, REQ-L3-ADR-008).

        REQ-006: Excludes soft-deleted ADRs (status='Deleted') by default.
        Pass ``include_deleted=True`` for admin/audit access.

        Args:
            workspace_id: Target workspace UUID.
            ctx: Resolved AuthContext.
            include_deleted: If True, include ADRs with status='Deleted'.

        Returns:
            QuerySet of Adr ORM instances.

        REQ-088: Returns a lazy ``QuerySet`` so the paginating ViewSet
        (REQ-034) slices with LIMIT/OFFSET instead of materialising all rows.
        """
        self._set_tenant_context(ctx)
        qs = Adr.objects.filter(workspace_id=workspace_id, tenant_id=ctx.tenant_id)
        if not include_deleted:
            # Datenmodell-Konsolidierung Phase 1: soft-delete routes through
            # workflow.services.outdate(); the state is read from
            # WorkflowItemState now that Adr.status is no longer the seam.
            qs = qs.exclude(
                id__in=state_reader.item_ids_in_state(
                    "Adr", "outdated", tenant_id=ctx.tenant_id
                )
            )
        return qs.order_by("created_at")

    def list_adrs_by_status(
        self, workspace_id: UUID, status: str, ctx: AuthContext
    ) -> List[Adr]:
        """Return ADRs filtered by *status* (REQ-L3-ADR-008).

        Args:
            workspace_id: Target workspace UUID.
            status: One of the Adr.Status values.
            ctx: Resolved AuthContext.

        Returns:
            Filtered list of Adr ORM instances.
        """
        self._set_tenant_context(ctx)
        return list(
            Adr.objects.filter(
                workspace_id=workspace_id,
                tenant_id=ctx.tenant_id,
                id__in=state_reader.item_ids_in_state(
                    "Adr", status, tenant_id=ctx.tenant_id
                ),
            ).order_by("created_at")
        )

    # ---------- Status Transition (REQ-L3-ADR-004, IF-AS-INT-003) ----------

    @atomic_transaction
    def transition_status(
        self,
        adr_id: UUID,
        target_status: str,
        ctx: AuthContext,
        change_reason: Optional[str] = None,
        superseded_by_id: Optional[UUID] = None,
        credential: Optional[str] = None,
    ) -> Adr:
        """Transition an ADR's workflow status (REQ-L3-ADR-004).

        Delegates to WorkflowFacade when available; falls back to direct
        status update if workflow engine is not configured.

        Args:
            adr_id: UUID of the ADR.
            target_status: Target status from Adr.Status choices.
            ctx: Resolved AuthContext.
            change_reason: Optional reason for audit.
            superseded_by_id: UUID of the successor ADR. Only meaningful when
                target_status is Adr.Status.SUPERSEDED (REQ-L3-ADR-005); a
                'decides' TraceLink is created from the successor ADR to this
                ADR so the TraceLink graph records which decision replaced it.
                Ignored for all other target statuses.

        Returns:
            Updated Adr ORM instance.
        """
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)

        adr = Adr.objects.filter(id=adr_id, tenant_id=ctx.tenant_id).first()
        if adr is None:
            raise NotFoundError(f"ADR {adr_id} not found")

        if target_status not in AdrValidator.VALID_STATUSES:
            raise ValidationError(
                f"Invalid ADR status '{target_status}'; "
                f"must be one of {sorted(AdrValidator.VALID_STATUSES)}"
            )

        # REQ-165/REQ-167: the WorkflowEngine is the SOLE authority for the
        # transition (IF-AS-INT-003). Role, change_reason and signature gates are
        # enforced by the engine; their errors propagate and abort this atomic
        # transaction instead of being swallowed (the previous bare
        # ``except Exception: pass`` silently flipped the status even when a gate
        # denied the move). The engine also writes the denormalized ``status``
        # mirror inside its own transaction (StateLifecycleManager
        # ._sync_status_mirror), so no direct status assignment is done here. A
        # workflow transition is not a content edit, so ``version`` is not bumped
        # — this matches the Requirement transition endpoint.
        from application.workflow_facade import WorkflowFacade

        WorkflowFacade().transition(
            item_id=adr_id,
            item_type="Adr",
            target_state=target_status,
            workspace_id=adr.workspace_id,
            ctx=ctx,
            change_reason=change_reason or "",
            credential=credential or "",
        )
        adr.refresh_from_db(fields=["status", "version"])

        # REQ-L3-ADR-005: when an ADR is superseded, record which ADR replaced
        # it via a 'decides' TraceLink (new -> old). 'supersedes' is not a
        # member of VALID_LINK_TYPES; 'decides' is the closest semantic match
        # already used for ADR decision links (REQ-L2-TE-020).
        if target_status == Adr.Status.SUPERSEDED and superseded_by_id is not None:
            self._trace_link_service.create_trace_link(
                source_id=superseded_by_id,
                target_id=adr_id,
                link_type=LinkType.DECIDES.value,
                ctx=ctx,
            )

        # The transition audit entry is written authoritatively by the
        # WorkflowEngine (WorkflowFacade._audit, op="transition") inside the same
        # atomic transaction — a second service-level audit here would duplicate
        # that row (details are v1-ignored), so it is intentionally omitted.
        return adr

    # ---------- TraceLink management (REQ-L3-ADR-005, IF-AS-INT-002) ----------
    #
    # ADR TraceLinks are created through the generic TraceLinkService.create_trace_link
    # flow (source=ADR id, target=ArchitectureElement id, link_type="decides").
    # TraceLinkService._resolve_artifact_id maps the ADR id to its backing
    # Artifact id (REQ-L2-TE-020). The former AdrService.create_tracelink /
    # ADR_LINK_TYPES helper was dead code: its link types ("addresses",
    # "supersedes", "related-to") were never members of VALID_LINK_TYPES, so
    # every call failed downstream.
    #
    # ADR-to-ADR supersession links (REQ-L3-ADR-005) are created in
    # transition_status() above when target_status=SUPERSEDED and a
    # superseded_by_id is supplied — also via the 'decides' link type
    # (source=successor ADR, target=superseded ADR), since 'supersedes' is
    # not a member of VALID_LINK_TYPES either.


__all__ = [
    "AdrService",
    "AdrDTO",
]
