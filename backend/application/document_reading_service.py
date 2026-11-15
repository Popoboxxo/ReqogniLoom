"""Document reading view — the read object behind ``GET /documents/{id}/view/``.

Slice R1 of ``docs/superpowers/plans/2026-11-15-document-view-on-document.md``:
the document view is **not** a new model, it is an editable reading surface on
the existing ``Document`` artifact (triage direction E1(b)). This service is the
single Layer-2 entry point for that surface — it reads, it never writes:

* the document head (identity, content fields, version, workflow state, freeze
  bookkeeping, projection bookkeeping),
* the freeze-derived list of editable fields (R1: freeze only — the
  permission- and repo-external-aware resolution arrives with R2,
  ``application/document_edit_policy.py``),
* the chapters, extracted purely from the Markdown ``body``
  (:mod:`application.markdown_chapters`).

Writing stays where it is: ``DocumentService.update_document`` is the only
content write path (plan §0), and R5/R6 will call it through the existing REST
endpoints. No new MCP tool, no migration (plan §0).

Read permission follows the established two-layer pattern: the RBAC matrix
(:class:`~auth_tenancy.services.authorization.AuthorizationService`) decides by
role, then an ``ItemPermission`` may narrow the answer to a single artefact
(issue #1578) — mirrors ``QualityService._assert_item_read_permission``. Rights
are restricting, never broadening (plan §0).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from uuid import UUID

from application.base import PermissionDeniedError, ServiceBase
from application.document_service import (
    DOCUMENT_ITEM_TYPE,
    FROZEN_FIELDS,
    DocumentService,
)
from application.markdown_chapters import Chapter, split_chapters
from auth_tenancy.context import AuthContext
from persistence.models import Document
from workflow.state_reader import current_states, initial_state

__all__ = [
    "ALWAYS_EDITABLE_FIELDS",
    "EDITABLE_TEXT_FIELDS",
    "DocumentProjectionInfo",
    "DocumentReadingService",
    "DocumentViewResult",
    "compute_editable_fields",
]

#: Content fields a release freezes, minus ``kind``: the kind is the document's
#: classification, not authored content, and is never edited inline
#: (plan O2 = (a), ADR-026 F-2 freezes it against the generic write path).
EDITABLE_TEXT_FIELDS: tuple[str, ...] = tuple(
    name for name in FROZEN_FIELDS if name != "kind"
)

#: Fields that stay editable even on a frozen document (ADR-026 F-2: ``doc_date``
#: is derived metadata; ``custom_fields`` follow the attribute catalog and are
#: not part of the R1 field list).
ALWAYS_EDITABLE_FIELDS: tuple[str, ...] = ("doc_date",)


def compute_editable_fields(
    frozen_at: datetime | None,
    frozen_fields: Any,
) -> tuple[str, ...]:
    """Return the content fields a client may still write (R1 freeze rule).

    Pure function — no DB, no ``ctx`` — so the REST layer and a future edit
    policy share one truth and the rule is testable without a database.

    R1 scope: the field freeze only. R2 replaces this with
    ``application.document_edit_policy.resolve_field_permissions``, which also
    accounts for the caller's write permission and ``owner_mode``. Until then a
    caller must not read this list as "everything here will actually save" — it
    is the *freeze* answer, not a permission grant.
    """
    if frozen_at is None:
        return EDITABLE_TEXT_FIELDS + ALWAYS_EDITABLE_FIELDS
    frozen = {str(name) for name in (frozen_fields or ())}
    return (
        tuple(name for name in EDITABLE_TEXT_FIELDS if name not in frozen)
        + ALWAYS_EDITABLE_FIELDS
    )


@dataclass(frozen=True)
class DocumentProjectionInfo:
    """Read-only projection bookkeeping of a document (Phase G / #1374 S3)."""

    projection_mode: str
    source_path: str
    projected_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "projection_mode": self.projection_mode,
            "source_path": self.source_path,
            "projected_sha256": self.projected_sha256,
        }


@dataclass(frozen=True)
class DocumentViewResult:
    """The document reading object (wire contract of ``.../view/``).

    Flat on purpose: the surface reads exactly these keys, and every additional
    nesting level would have to be justified by a consumer. ``to_dict`` is the
    one wire conversion, so the serializer and the OpenAPI schema cannot drift
    from the service.
    """

    id: UUID
    artifact_id: UUID | None
    uid: str | None
    title: str
    kind: str
    description: str
    body: str
    doc_date: date | None
    version: int
    status: str
    frozen_at: datetime | None
    frozen_fields: tuple[str, ...]
    editable_fields: tuple[str, ...]
    chapters: tuple[Chapter, ...]
    projection: DocumentProjectionInfo

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "artifact_id": str(self.artifact_id) if self.artifact_id else None,
            "uid": self.uid,
            "title": self.title,
            "kind": self.kind,
            "description": self.description,
            "body": self.body,
            "doc_date": self.doc_date.isoformat() if self.doc_date else None,
            "version": self.version,
            "status": self.status,
            "frozen_at": self.frozen_at.isoformat() if self.frozen_at else None,
            "frozen_fields": list(self.frozen_fields),
            "editable_fields": list(self.editable_fields),
            "chapters": [chapter.to_dict() for chapter in self.chapters],
            "projection": self.projection.to_dict(),
        }


class DocumentReadingService(ServiceBase):
    """Assemble the document reading object (R1).

    leaf_id : COMP-AS-023 (Document lifecycle)
    req_id  : REQ-L2-PL-004, REQ-L2-PL-010
    """

    def read(self, document_id: UUID, ctx: AuthContext) -> DocumentViewResult:
        """Return the reading object for one document.

        Args:
            document_id: ``Document`` primary key.
            ctx: Resolved ``AuthContext`` (tenant + roles).

        Returns:
            The reading object, chapters included.

        Raises:
            NotFoundError: No such document in the caller's tenant.
            PermissionDeniedError: The RBAC matrix or an item-level rule denies
                the read.
        """
        self._set_tenant_context(ctx)
        self._assert_read_permission(ctx)
        # ``get_document`` is tenant-scoped, so a foreign tenant's document is
        # indistinguishable from a missing one (404, no existence oracle).
        document = DocumentService().get_document(document_id, ctx)
        self._assert_item_read_permission(ctx, document)
        return self._build(document, ctx)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _build(self, document: Document, ctx: AuthContext) -> DocumentViewResult:
        frozen_fields = tuple(str(name) for name in (document.frozen_fields or ()))
        return DocumentViewResult(
            id=document.id,
            artifact_id=document.artifact_id,
            uid=document.uid,
            title=document.title,
            kind=document.kind,
            description=document.description or "",
            body=document.body or "",
            doc_date=document.doc_date,
            version=document.version,
            status=self._status(document, ctx),
            frozen_at=document.frozen_at,
            frozen_fields=frozen_fields,
            editable_fields=compute_editable_fields(document.frozen_at, frozen_fields),
            chapters=split_chapters(document.body or ""),
            projection=DocumentProjectionInfo(
                projection_mode=getattr(document, "projection_mode", "none"),
                source_path=getattr(document, "source_path", "") or "",
                projected_sha256=getattr(document, "projected_sha256", "") or "",
            ),
        )

    @staticmethod
    def _status(document: Document, ctx: AuthContext) -> str:
        """Resolve the workflow state in **one** query (single-item map lookup).

        Uses ``current_states`` (not ``current_state``) so the soft-delete
        overlay applies — a deleted document reports ``"outdated"`` exactly as
        the detail route does (G1.5 V3).
        """
        states = current_states(
            DOCUMENT_ITEM_TYPE, [document.id], tenant_id=ctx.tenant_id
        )
        return states.get(str(document.id)) or initial_state(DOCUMENT_ITEM_TYPE)

    @staticmethod
    def _assert_read_permission(ctx: AuthContext) -> None:
        """Deny a caller the RBAC matrix does not grant READ to.

        The matrix check (not ``ctx.has_role("viewer")``, which only matches that
        one literal role name): editor/approver/admin read too, and an unknown or
        empty role set stays fail-closed.
        """
        from auth_tenancy.services.authorization import AuthorizationService, Operation

        if not AuthorizationService().decide_access(ctx.active_roles, Operation.READ).allow:
            raise PermissionDeniedError(
                "Permission denied: reading a document requires at least 'viewer'."
            )

    @staticmethod
    def _assert_item_read_permission(ctx: AuthContext, document: Document) -> None:
        """Issue #1578: an item-level rule may narrow the read to one artefact.

        The coarse RBAC matrix only says "this role may read somewhere"; an
        ``ItemPermission`` can restrict it per workspace/artefact. No rule (or a
        ``read``/``write`` grant) leaves the RBAC verdict untouched.
        """
        artifact_id = getattr(document, "artifact_id", None)
        if artifact_id is None:
            return
        from application.effective_permission_service import EffectivePermissionService

        decision = EffectivePermissionService().resolve_effective_permission(
            active_roles=ctx.active_roles,
            user_id=ctx.user_id,
            workspace_id=document.workspace_id,
            artifact_id=UUID(str(artifact_id)),
            level="read",
        )
        if not decision.is_allowed:
            raise PermissionDeniedError(
                "Permission denied: no read access to this document."
            )
