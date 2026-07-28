"""
GlossaryService — Semantic Project Glossary CRUD and Versioning (REQ-L1-044).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Optional
from uuid import UUID

from auth_tenancy.context import AuthContext
from django.db.models import F, Q
from persistence.models import GlossaryTerm, GlossaryTermVersion, Workspace
from persistence.transactions import atomic_transaction

from application.base import NotFoundError, ServiceBase, ValidationError

logger = logging.getLogger(__name__)


@dataclass
class GlossaryTermDTO:
    id: UUID
    workspace_id: Optional[UUID]
    term: str
    definition: str
    synonyms: list
    abbreviation: str
    version: int
    lifecycle_status: str = "active"  # REQ-006: soft-delete lifecycle

    @classmethod
    def from_orm(cls, term: GlossaryTerm) -> "GlossaryTermDTO":
        return cls(
            id=term.id,
            workspace_id=term.workspace_id,
            term=term.term,
            definition=term.definition,
            synonyms=term.synonyms,
            abbreviation=term.abbreviation,
            version=term.version,
            lifecycle_status=getattr(term, "lifecycle_status", "active"),
        )


class GlossaryService(ServiceBase):
    """Handles CRUD and versioning for GlossaryTerm."""

    def __init__(self, preset_policy_service=None) -> None:
        from application.preset_policy_service import get_preset_policy_service

        self._preset_policy = preset_policy_service or get_preset_policy_service()

    def get(self, ctx: AuthContext, term_id: UUID) -> GlossaryTermDTO:
        term = GlossaryTerm.objects.filter(id=term_id).first()
        if not term:
            raise NotFoundError(f"GlossaryTerm {term_id} not found.")
        return GlossaryTermDTO.from_orm(term)

    def list_by_workspace(
        self, ctx: AuthContext, workspace_id: UUID, include_deleted: bool = False
    ) -> List[GlossaryTermDTO]:
        """Return GlossaryTerms for *workspace_id*.

        REQ-006: Excludes soft-deleted terms (lifecycle_status='deleted') by default.
        Pass ``include_deleted=True`` for admin/audit access.
        """
        qs = GlossaryTerm.objects.filter(
            Q(workspace_id=workspace_id) | Q(workspace__isnull=True)
        )
        if not include_deleted:
            # Phase 0: delete() routes soft-delete through
            # workflow.services.outdate(). GlossaryTerm is NOT wired into
            # _STATUS_MIRROR_MODELS (no mirrored status column), so the
            # workflow state lives solely in WorkflowItemState — filter there
            # instead of on the now-dead `lifecycle_status` column.
            from workflow.services import outdated_item_ids

            qs = qs.exclude(id__in=outdated_item_ids("GlossaryTerm"))
        return [GlossaryTermDTO.from_orm(t) for t in qs.order_by("term")]

    @atomic_transaction
    def create(
        self,
        ctx: AuthContext,
        workspace_id: UUID,
        term: str,
        definition: str,
        synonyms: Optional[list] = None,
        abbreviation: str = "",
    ) -> GlossaryTermDTO:
        if not term.strip() or not definition.strip():
            raise ValidationError("Term and definition are required.")

        workspace = Workspace.objects.filter(id=workspace_id).first()
        if not workspace:
            raise NotFoundError(f"Workspace {workspace_id} not found.")

        if GlossaryTerm.objects.filter(workspace_id=workspace_id, term=term).exists():
            raise ValidationError(f"Glossary term '{term}' already exists in this workspace.")

        syns = synonyms or []

        gt = GlossaryTerm.objects.create(
            workspace=workspace,
            term=term,
            definition=definition,
            synonyms=syns,
            abbreviation=abbreviation,
            version=1,
            # Changed from actor_id to user_id to fix bug
        created_by_id=ctx.user_id,
            modified_by_id=ctx.user_id,
        )

        GlossaryTermVersion.objects.create(
            term_fk=gt,
            term_version=gt.version,
            definition=gt.definition,
            synonyms=gt.synonyms,
            abbreviation=gt.abbreviation,
            # Changed from actor_id to user_id to fix bug
        created_by_id=ctx.user_id,
        )

        # Initialise workflow state (REQ-006/Phase 0): without this,
        # delete()'s workflow.services.outdate() call has no WorkflowItemState
        # to transition and raises WorkflowItemState.DoesNotExist.
        try:
            from workflow.services import initialize_workflow_states

            initialize_workflow_states(
                item_ids=[gt.id],
                item_type="GlossaryTerm",
                workspace_id=workspace_id,
                ctx=ctx,
            )
        except Exception:
            logger.debug(
                "GlossaryService: workflow init skipped for term=%s", gt.id
            )

        return GlossaryTermDTO.from_orm(gt)

    @atomic_transaction
    def update(
        self,
        ctx: AuthContext,
        term_id: UUID,
        definition: Optional[str] = None,
        synonyms: Optional[list] = None,
        abbreviation: Optional[str] = None,
        change_reason: Optional[str] = None,
    ) -> GlossaryTermDTO:
        gt = GlossaryTerm.objects.filter(id=term_id).first()
        if not gt:
            raise NotFoundError(f"GlossaryTerm {term_id} not found.")

        if self._preset_policy.is_change_reason_required(str(gt.workspace_id)):
            if not change_reason:
                raise ValidationError("change_reason required by workspace preset policy")

        changed = False
        if definition is not None and definition != gt.definition:
            gt.definition = definition
            changed = True
        if synonyms is not None and synonyms != gt.synonyms:
            gt.synonyms = synonyms
            changed = True
        if abbreviation is not None and abbreviation != gt.abbreviation:
            gt.abbreviation = abbreviation
            changed = True

        if not changed:
            return GlossaryTermDTO.from_orm(gt)

        # Update version and save
        gt.version = F("version") + 1
        gt.modified_by_id = ctx.user_id
        gt.save(update_fields=["definition", "synonyms", "abbreviation", "version", "modified_at", "modified_by"])
        gt.refresh_from_db(fields=["version"])

        GlossaryTermVersion.objects.create(
            term_fk=gt,
            term_version=gt.version,
            definition=gt.definition,
            synonyms=gt.synonyms,
            abbreviation=gt.abbreviation,
            # Changed from actor_id to user_id to fix bug
        created_by_id=ctx.user_id,
        )

        self._audit(
            ctx=ctx,
            operation="update",
            entity_type="GlossaryTerm",
            entity_id=term_id,
            change_reason=change_reason,
        )

        return GlossaryTermDTO.from_orm(gt)

    @atomic_transaction
    def delete(self, ctx: AuthContext, term_id: UUID) -> None:
        """Soft-delete GlossaryTerm by setting lifecycle_status to 'deleted' (REQ-006).

        Physical deletion is intentionally avoided for end-user operations.
        The term remains in the database for audit purposes.
        Hard-delete is available only via the Django admin panel.
        """
        gt = GlossaryTerm.objects.filter(id=term_id).first()
        if not gt:
            raise NotFoundError(f"GlossaryTerm {term_id} not found.")
        # REQ-006/Phase 0: route soft-delete through the workflow engine's
        # outdate() escape hatch instead of writing lifecycle_status directly.
        from workflow.services import outdate

        outdate(
            item_id=gt.id,
            item_type="GlossaryTerm",
            workspace_id=gt.workspace_id,
            ctx=ctx,
            reason="deleted via glossary.delete",
        )
