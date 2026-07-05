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
        )


class GlossaryService(ServiceBase):
    """Handles CRUD and versioning for GlossaryTerm."""

    def get(self, ctx: AuthContext, term_id: UUID) -> GlossaryTermDTO:
        term = GlossaryTerm.objects.filter(id=term_id).first()
        if not term:
            raise NotFoundError(f"GlossaryTerm {term_id} not found.")
        return GlossaryTermDTO.from_orm(term)

    def list_by_workspace(self, ctx: AuthContext, workspace_id: UUID) -> List[GlossaryTermDTO]:
        terms = GlossaryTerm.objects.filter(
            Q(workspace_id=workspace_id) | Q(workspace__isnull=True)
        ).order_by("term")
        return [GlossaryTermDTO.from_orm(t) for t in terms]

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

        return GlossaryTermDTO.from_orm(gt)

    @atomic_transaction
    def update(
        self,
        ctx: AuthContext,
        term_id: UUID,
        definition: Optional[str] = None,
        synonyms: Optional[list] = None,
        abbreviation: Optional[str] = None,
    ) -> GlossaryTermDTO:
        gt = GlossaryTerm.objects.filter(id=term_id).first()
        if not gt:
            raise NotFoundError(f"GlossaryTerm {term_id} not found.")

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
        gt.modified_by_id = ctx.actor_id
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

        return GlossaryTermDTO.from_orm(gt)

    @atomic_transaction
    def delete(self, ctx: AuthContext, term_id: UUID) -> None:
        gt = GlossaryTerm.objects.filter(id=term_id).first()
        if not gt:
            raise NotFoundError(f"GlossaryTerm {term_id} not found.")
        gt.delete()
