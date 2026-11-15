"""Document reading view — the read object behind ``GET /documents/{id}/view/``.

Slices R1+R2 of ``docs/superpowers/plans/2026-11-15-document-view-on-document.md``:
the document view is **not** a new model, it is an editable reading surface on
the existing ``Document`` artifact (triage direction E1(b)). This service is the
single Layer-2 entry point for that surface — it reads, it never writes:

* the document head (identity, content fields, version, workflow state, freeze
  bookkeeping, projection bookkeeping),
* per-field write verdicts and the document-level read-only reason
  (``application/document_edit_policy.py``, R2): permission beats ownership,
  ownership beats freeze, so the surface never offers a write the service would
  reject,
* the chapters, extracted purely from the Markdown ``body``
  (:mod:`application.markdown_chapters`),
* the Markdown export of those chapters (R7.1,
  :meth:`DocumentViewResult.to_markdown`): exactly the reading state, no edit
  markers.

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
from application.document_edit_policy import (
    EDITABLE_FIELDS_V1,
    resolve_field_permissions,
)
from application.document_service import DOCUMENT_ITEM_TYPE, DocumentService
from application.markdown_chapters import Chapter, split_chapters
from auth_tenancy.context import AuthContext
from persistence.models import Document
from workflow.state_reader import current_states, initial_state

__all__ = [
    "DocumentProjectionInfo",
    "DocumentReadingService",
    "DocumentViewResult",
]

#: Read-only document-level reason used when no field can be written because the
#: content is owned by an external repository (ADR-026 ENT-F5).
REASON_PERMISSION = "PERMISSION"
REASON_REPO_EXTERNAL = "REPO_EXTERNAL"


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
    fields: tuple[dict[str, Any], ...]
    capabilities: dict[str, Any]
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
            "fields": [dict(field) for field in self.fields],
            "capabilities": dict(self.capabilities),
            "chapters": [chapter.to_dict() for chapter in self.chapters],
            "projection": self.projection.to_dict(),
        }

    def to_markdown(self) -> str:
        """Render this reading object as Markdown — the surface's reading state.

        Slice R7.1: the export is the *reading* half of the object, never the
        editing one. It reads :attr:`chapters` only — the same numbered, flat
        list ``to_dict()`` publishes — so the export carries the numbers and
        order the view shows and cannot grow a second chapter logic (plan risk
        R1). No edit markers: no per-field verdicts (``editable``/``locked``),
        no capability flags, no HTML or Markdown comment fences; those belong to
        the surface, not to a document that leaves the application.

        Returns:
            Markdown with one ATX heading per chapter (the chapter's own level,
            prefixed with its number and title), each chapter body beneath it,
            and the unnumbered preamble first. An empty body yields an empty
            document (``""``) — never a lone heading.
        """
        blocks: list[str] = []
        for chapter in self.chapters:
            if chapter.level > 0:
                blocks.append(f"{'#' * chapter.level} {chapter.number} {chapter.title}")
            if chapter.body:
                blocks.append(chapter.body)
        if not blocks:
            return ""
        return "\n\n".join(blocks) + "\n"


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
        owner_mode = getattr(document, "owner_mode", "loom")
        permission_ok = self._has_write_permission(ctx, document)
        permissions = resolve_field_permissions(
            document,
            can_write=permission_ok,
            owner_mode=owner_mode,
            frozen_fields=frozen_fields,
            # No attribute-catalog restriction exists on this write path:
            # ``update_document`` accepts any key ``validate_custom_fields``
            # permits, so ``None`` (= catalog unknown) is the honest input and
            # keeps ``editable`` aligned with the real PATCH outcome.
            allowed_custom_fields=None,
        )
        can_write = permission_ok and owner_mode != "repo_external"
        read_only_reason: str | None = None
        if not can_write:
            read_only_reason = (
                REASON_REPO_EXTERNAL
                if permission_ok
                else REASON_PERMISSION
            )
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
            editable_fields=tuple(
                name for name in EDITABLE_FIELDS_V1 if permissions[name].editable
            ),
            fields=self._field_entries(document, permissions),
            capabilities={
                "can_write": can_write,
                "read_only_reason": read_only_reason,
            },
            chapters=split_chapters(document.body or ""),
            projection=DocumentProjectionInfo(
                projection_mode=getattr(document, "projection_mode", "none"),
                source_path=getattr(document, "source_path", "") or "",
                projected_sha256=getattr(document, "projected_sha256", "") or "",
            ),
        )

    @staticmethod
    def _has_write_permission(ctx: AuthContext, document: Document) -> bool:
        """Return whether the caller may write this document.

        Merged answer from :class:`EffectivePermissionService` (RBAC matrix +
        item-level rule), never a broader one: the item layer can only narrow.
        The item-level lookup is cached per (user, workspace, artifact), and the
        read gate above already resolved the same triple, so this adds no query
        (plan R2: "keine neue Query").
        """
        from application.effective_permission_service import EffectivePermissionService

        artifact_id = getattr(document, "artifact_id", None)
        decision = EffectivePermissionService().resolve_effective_permission(
            active_roles=ctx.active_roles,
            user_id=ctx.user_id,
            workspace_id=document.workspace_id,
            artifact_id=UUID(str(artifact_id)) if artifact_id else None,
            level="write",
        )
        return decision.is_allowed

    @staticmethod
    def _field_entries(
        document: Document,
        permissions: dict[str, Any],
    ) -> tuple[dict[str, Any], ...]:
        """Render one wire entry per policy field, in policy order.

        Values are wire-ready (ISO date, plain dict for ``custom_fields``); the
        editable/locked half comes from the shared policy so it cannot drift from
        what ``PATCH /documents/{id}/`` accepts.
        """
        custom_fields = dict(getattr(document.artifact, "custom_fields", None) or {})
        values: dict[str, Any] = {
            "title": document.title,
            "description": document.description or "",
            "body": document.body or "",
            "doc_date": document.doc_date.isoformat() if document.doc_date else None,
            "custom_fields": custom_fields,
        }
        return tuple(
            {
                "name": name,
                "value": values[name],
                "editable": permissions[name].editable,
                "locked": (
                    dict(permissions[name].locked)
                    if permissions[name].locked is not None
                    else None
                ),
            }
            for name in EDITABLE_FIELDS_V1
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
