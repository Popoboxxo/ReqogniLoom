"""Document projection, status comparison and adoption (Issue #1374 S3).

The server renders and compares only. It never writes to a repository and holds
no repository credentials: a client (CI job or agent) fetches the projection,
writes the file on a branch and reports the written hash back with
:meth:`DocumentProjectionService.confirm`.

Conflict rules (concept §7.2) are fail-loud: a repository file that changed
behind Loom's back is reported as ``file_changed`` and never overwritten; when
both sides moved the state is ``conflict`` and adoption refuses.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Mapping
from uuid import UUID

from django.db import transaction

from application.base import (
    AdoptionHashMismatchError,
    NotFoundError,
    PermissionDeniedError,
    ServiceBase,
    ValidationError,
)
from application.document_projection_render import (
    render_document,
    projection_path,
    with_header,
)
from application.models import DomainEventOutbox
from auth_tenancy.context import AuthContext
from persistence.models import Document, GlossaryTerm, InlineAnchor, TraceLink
from workflow.state_reader import current_states

logger = logging.getLogger(__name__)

PROJECTION_STATES = (
    "in_sync",
    "loom_changed",
    "file_changed",
    "conflict",
    "missing_in_repo",
    "untracked_in_loom",
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class ProjectedDocument:
    path: str
    content: str
    sha256: str
    version: int
    state: str
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "content": self.content,
            "sha256": self.sha256,
            "version": self.version,
            "state": self.state,
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class ProjectionStatusRow:
    document_id: str
    path: str
    state: str
    projected_sha256: str
    current_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "path": self.path,
            "state": self.state,
            "projected_sha256": self.projected_sha256,
            "current_sha256": self.current_sha256,
        }


def _assert_sha256(value: str, *, field: str) -> str:
    normalized = (value or "").strip().lower()
    if not _SHA256_RE.match(normalized):
        raise ValidationError(f"{field} must be a lowercase SHA-256 hex digest.")
    return normalized


class DocumentProjectionService(ServiceBase):
    """Render, compare and adopt document projections."""

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def project(self, document_id: UUID, ctx: AuthContext) -> ProjectedDocument:
        """Render one document deterministically (no side effects)."""
        self._set_tenant_context(ctx)
        self._assert_read_permission(ctx)
        document = self._load_document(document_id, ctx)

        anchors = list(
            InlineAnchor.objects.filter(
                source_artifact=document.artifact_id, field="body"
            ).select_related("target_artifact")
        )
        for anchor in anchors:
            target = anchor.target_artifact
            anchor.target_lifecycle = getattr(target, "lifecycle_status", "active")
            anchor.target_label = f"{target.artifact_type} {str(target.id)[:8]}"

        edges = []
        for link in TraceLink.objects.filter(source_id=document.artifact_id).select_related(
            "target"
        )[:500]:
            edges.append(
                {
                    "link_type": link.link_type,
                    "target_label": (
                        f"{link.target.artifact_type} {str(link.target_id)[:8]}"
                    ),
                }
            )

        glossary = {
            term.term: term.definition
            for term in GlossaryTerm.objects.filter(workspace_id=document.workspace_id)
        }

        state = (
            current_states("Document", [document.id], tenant_id=ctx.tenant_id).get(
                str(document.id)
            )
            or ""
        )

        projected = render_document(
            document,
            anchors=anchors,
            edges=edges,
            glossary=glossary,
            state=state,
        )
        content = with_header(projected, document=document, state=state)

        return ProjectedDocument(
            path=projection_path(document),
            content=content,
            sha256=projected.sha256,
            version=document.version,
            state=state or "unknown",
            warnings=projected.warnings,
        )

    def status(
        self,
        workspace_id: UUID,
        files: Mapping[str, str],
        ctx: AuthContext,
    ) -> list[ProjectionStatusRow]:
        """Classify every projected document against the repository hashes.

        ``files`` maps a repository path to the SHA-256 the client computed
        locally; the server never sees repository content.
        """
        self._set_tenant_context(ctx)
        self._assert_read_permission(ctx)

        rows: list[ProjectionStatusRow] = []
        documents = Document.objects.filter(workspace_id=workspace_id).order_by("id")
        for document in documents:
            path = projection_path(document)
            repo_hash = files.get(path)
            projected_hash = document.projected_sha256 or ""

            if not projected_hash and repo_hash is None:
                continue
            if not projected_hash:
                state = "untracked_in_loom"
            elif repo_hash is None:
                state = "missing_in_repo"
            else:
                repo_hash = _assert_sha256(repo_hash, field=f"files[{path}]")
                loom_changed = document.version != (document.projected_version or 0)
                file_changed = repo_hash != projected_hash
                if not loom_changed and not file_changed:
                    state = "in_sync"
                elif loom_changed and not file_changed:
                    state = "loom_changed"
                elif file_changed and not loom_changed:
                    state = "file_changed"
                else:
                    state = "conflict"

            rows.append(
                ProjectionStatusRow(
                    document_id=str(document.id),
                    path=path,
                    state=state,
                    projected_sha256=projected_hash,
                    current_sha256=repo_hash or "",
                )
            )
        return rows

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    @transaction.atomic
    def confirm(self, document_id: UUID, sha256: str, ctx: AuthContext) -> None:
        """Record the hash a client actually wrote for the current version."""
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)
        document = self._load_document(document_id, ctx)
        document.projected_sha256 = _assert_sha256(sha256, field="sha256")
        document.projected_version = document.version
        document.save(update_fields=["projected_sha256", "projected_version"])

    @transaction.atomic
    def adopt(
        self,
        document_id: UUID,
        *,
        file_sha256: str,
        source_path: str = "",
        freeze: bool = False,
        ctx: AuthContext,
    ) -> Document:
        """Turn a repo-external document into a loom-owned, projected one.

        Requires the repository hash to match the hash recorded at import time:
        adopting a file that changed on disk would silently bless content nobody
        reviewed.
        """
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)
        document = self._load_document(document_id, ctx)

        if document.owner_mode != "repo_external":
            raise ValidationError("Only a repo_external document can be adopted.")
        candidate = _assert_sha256(file_sha256, field="file_sha256")
        if candidate != (document.source_sha256 or ""):
            raise AdoptionHashMismatchError(
                "The repository file differs from the imported source; "
                "re-import or resolve the conflict before adopting."
            )

        document.owner_mode = "loom"
        document.projection_mode = "generated"
        if source_path:
            document.source_path = source_path
        document.projected_sha256 = candidate
        document.projected_version = document.version
        document.save(
            update_fields=[
                "owner_mode",
                "projection_mode",
                "source_path",
                "projected_sha256",
                "projected_version",
            ]
        )

        self._audit(
            ctx=ctx,
            operation="update",
            entity_type="Document",
            entity_id=document.id,
            change_reason="Adopted a repository document.",
            details={"source_path": document.source_path},
        )
        self._publish_adopted(document, ctx)

        if freeze:
            from application.document_service import DocumentService

            document = DocumentService().release(
                document.id, ctx, change_reason="Adopted and released."
            )
        return document

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _load_document(self, document_id: UUID, ctx: AuthContext) -> Document:
        document = Document.objects.filter(
            id=document_id, tenant_id=ctx.tenant_id
        ).first()
        if document is None:
            raise NotFoundError(f"Document {document_id} not found")
        return document

    @staticmethod
    def _assert_read_permission(ctx: AuthContext) -> None:
        from auth_tenancy.services.authorization import AuthorizationService, Operation

        if not AuthorizationService().decide_access(ctx.active_roles, Operation.READ).allow:
            raise PermissionDeniedError(
                "Permission denied: reading a projection requires at least 'viewer'."
            )

    @staticmethod
    def _publish_adopted(document: Document, ctx: AuthContext) -> None:
        from application.event_bus import publish_entity_event

        publish_entity_event(
            DomainEventOutbox.EventType.DOCUMENT_ADOPTED.value,
            entity_id=document.id,
            workspace_id=document.workspace_id,
            payload={"document_id": str(document.id), "uid": document.uid or ""},
        )
