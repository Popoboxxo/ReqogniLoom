"""MCP tool group for the ``Document`` artifact (``document.*``).

Plan F F2-T6 (ADR-026, #1374). The ``Document`` artifact had a REST surface
since F2-T5 but no MCP tool group, so an agent could not read or author a
document at all. This group closes that asymmetry — it is the F2-T6 counterpart
of ``rest_api.views.DocumentViewSet`` and keeps the same contract:

  document.create     — create a document (write)
  document.read       — fetch one document incl. its custom fields (read)
  document.query      — list a workspace's documents (read)
  document.update     — update content fields / custom fields (write)
  document.transition — move through the workflow (write, F-1/F-5/gates)
  document.versions   — list recorded content revisions (read)
  document.diff       — field-level diff between two revisions (read)
  document.outdate    — soft-delete via the workflow outdate path (write)
  document.reactivate — undo the soft-delete (write)

Every write goes through :class:`application.document_service.DocumentService`
(ADR-01) — no business logic here. In particular the freeze (F-3), the release
gates (G-1…G-4) and the optimistic-lock compare stay in the service, so this
transport cannot bypass them; the JSON-RPC error code is the same one the REST
layer reports (``FIELD_FROZEN`` / ``DOCUMENT_GATE_FAILED`` / ``CONFLICT``).

Soft delete (G1.5) is the workflow engine's outdate escape hatch: the row is
never removed, ``status`` becomes ``"outdated"`` and ``document.query`` hides it
unless ``include_outdated`` is true. The MCP parameter keeps the surface-wide
``include_outdated`` name; it maps to REST's ``?include_deleted=``.

No ORM access in this module (ADR-01); the outbox events are emitted by
``DocumentService`` in the same transaction as the write (F2-T7).
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from django.utils.dateparse import parse_date

from application.artifact_diff_service import ArtifactDiffService
from application.base import (
    NotFoundError,
    OptimisticLockError,
    ValidationError,
)
from application.document_service import DocumentService
from auth_tenancy.context import AuthContext
from mcp_server.protocol_handler import ToolResult
from mcp_server.tools.base import (
    BaseToolGroup,
    artifact_custom_fields,
    require_param,
    require_uuid,
    resolve_engine_status,
    resolve_status_map,
    workspace_query_required,
)
from persistence.errors import PermissionDeniedError
from persistence.models import Document

#: The workflow item type this group speaks about (PascalCase).
_ITEM_TYPE = "Document"

#: The kinds the ``Document`` model accepts; the create/update schemas publish
#: them so a client does not have to guess the enum (#345-style honesty).
_KINDS: tuple[str, ...] = tuple(Document.Kind.values)


def _iso(value: Any) -> str | None:
    """Render a ``date``/``datetime`` as ISO-8601, or ``None``."""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _parse_doc_date(value: Any) -> date | None:
    """Normalise the wire ``doc_date`` (string/null/date) to a ``date``.

    JSON has no date type, so MCP callers send an ISO-8601 string. The service
    expects a ``date`` (its revision snapshot calls ``isoformat()``), and the
    REST serializer does the same conversion — parsing here keeps both
    transports on the identical contract. ``None`` clears the value.
    """
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    parsed = parse_date(str(value))
    if parsed is None:
        raise ValidationError(
            f"Invalid doc_date {value!r}; expected an ISO-8601 date (YYYY-MM-DD)."
        )
    return parsed


def _document_to_dict(
    document: Document, status_map: dict[str, str] | None = None
) -> dict[str, Any]:
    """Serialize a ``Document`` ORM row for the MCP responses.

    Mirrors ``rest_api.views._document_to_dict`` / ``DocumentSerializer``
    field-for-field, plus the ``status`` value the workflow engine owns (the
    model deliberately has no lifecycle column, ADR-026 R2). ``custom_fields``
    lives on the backing ``Artifact`` and is normalised to a dict.
    """
    return {
        "id": str(document.id),
        "workspace_id": str(document.workspace_id),
        "artifact_id": (
            str(document.artifact_id)
            if getattr(document, "artifact_id", None)
            else None
        ),
        "uid": getattr(document, "uid", None),
        "title": document.title,
        "kind": document.kind,
        "description": getattr(document, "description", ""),
        "body": getattr(document, "body", ""),
        "doc_date": _iso(getattr(document, "doc_date", None)),
        "frozen_at": _iso(getattr(document, "frozen_at", None)),
        "frozen_fields": list(getattr(document, "frozen_fields", None) or []),
        # Phase G / #1374 S3: read-only dual-source/projection bookkeeping.
        "owner_mode": getattr(document, "owner_mode", "loom"),
        "source_path": getattr(document, "source_path", ""),
        "source_sha256": getattr(document, "source_sha256", ""),
        "projection_mode": getattr(document, "projection_mode", "none"),
        "projected_sha256": getattr(document, "projected_sha256", ""),
        "projected_version": getattr(document, "projected_version", None),
        "custom_fields": artifact_custom_fields(document),
        "status": resolve_engine_status(
            _ITEM_TYPE, document.id, status_map=status_map
        ),
        "version": document.version,
        "created_at": _iso(getattr(document, "created_at", None)),
        "updated_at": _iso(getattr(document, "modified_at", None)),
    }


def _validation_error(exc: Exception) -> ToolResult:
    """Map a service validation error to its transport error code.

    ``FieldFrozenError`` and ``DocumentGateFailedError`` are
    ``ValidationError`` subclasses that carry a stable ``error_code`` — the
    same code the REST layer answers (``409 FIELD_FROZEN`` /
    ``409 DOCUMENT_GATE_FAILED``). Forwarding it keeps the two transports
    diagnosable with one vocabulary instead of collapsing both into
    ``VALIDATION_ERROR``.
    """
    code = getattr(exc, "error_code", None) or "VALIDATION_ERROR"
    details = getattr(exc, "details", None)
    return ToolResult.error(
        code,
        str(exc),
        details={"details": details} if details else None,
    )


class DocumentToolGroup(BaseToolGroup):
    """MCP tool group for the ``document.*`` namespace (Plan F F2-T6)."""

    _TOOL_MAP = {
        "document.create": "_handle_create",
        "document.read": "_handle_read",
        "document.project": "_handle_project",
        "document.projection_status": "_handle_projection_status",
        "document.adopt": "_handle_adopt",
        "document.query": "_handle_query",
        "document.update": "_handle_update",
        "document.transition": "_handle_transition",
        "document.versions": "_handle_versions",
        "document.diff": "_handle_diff",
        "document.outdate": "_handle_outdate",
        "document.reactivate": "_handle_reactivate",
    }

    _TOOL_SCHEMAS = [
        {
            "name": "document.create",
            "description": (
                "Create a Document artifact (write). Title and kind are "
                "required; the local identifier DOC-NNN and the initial "
                "workflow state are assigned server-side."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace_id": {
                        "type": "string",
                        "description": "Required. UUID of the target workspace.",
                    },
                    "title": {
                        "type": "string",
                        "description": "Required. Document title (max 255 characters).",
                    },
                    "kind": {
                        "type": "string",
                        "enum": list(_KINDS),
                        "description": "Required. Document kind.",
                    },
                    "description": {
                        "type": "string",
                        "description": (
                            "Purpose/summary (not the content). Defaults to ''."
                        ),
                    },
                    "body": {
                        "type": "string",
                        "description": "Markdown content. Defaults to ''.",
                    },
                    "doc_date": {
                        "type": ["string", "null"],
                        "description": "Optional document date (ISO-8601 date).",
                    },
                    "custom_fields": {
                        "type": "object",
                        "additionalProperties": True,
                        "description": (
                            "Extended user-defined attributes (flat key/value "
                            "map) defined by this workspace's attribute definition."
                        ),
                    },
                },
                "required": ["workspace_id", "title", "kind"],
            },
        },
        {
            "name": "document.read",
            "description": (
                "Fetch a single Document by ID, including its content, freeze "
                "state and extended attributes (read-only)."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "UUID of the document."},
                },
                "required": ["id"],
            },
        },
        {
            "name": "document.query",
            "description": (
                "List a workspace's documents, ordered by -modified_at, id "
                "(read-only). Soft-deleted documents are omitted unless "
                "include_outdated is true."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace_id": {
                        "type": "string",
                        "description": "Required. UUID of the target workspace.",
                    },
                    "include_outdated": {
                        "type": "boolean",
                        "description": (
                            "If true, include soft-deleted documents (REST's "
                            "?include_deleted=true). Defaults to false."
                        ),
                    },
                    "uid": {
                        "type": "string",
                        "description": (
                            "Optional local identifier (e.g. 'DOC-004'); when "
                            "supplied, only the document carrying it is returned."
                        ),
                    },
                },
                "required": workspace_query_required(),
            },
        },
        {
            "name": "document.update",
            "description": (
                "Update a Document's content fields and/or extended attributes "
                "(write). Omitted fields keep their current value. A frozen "
                "content field is refused with FIELD_FROZEN; a stale "
                "expected_version with CONFLICT."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "UUID of the document."},
                    "title": {"type": "string", "description": "New title."},
                    "kind": {
                        "type": "string",
                        "enum": list(_KINDS),
                        "description": "New document kind.",
                    },
                    "description": {"type": "string"},
                    "body": {"type": "string"},
                    "doc_date": {
                        "type": ["string", "null"],
                        "description": "New document date; null clears it.",
                    },
                    "custom_fields": {
                        "type": "object",
                        "additionalProperties": True,
                        "description": (
                            "Extended user-defined attributes (flat key/value "
                            "map). Replaces the stored map."
                        ),
                    },
                    "change_reason": {
                        "type": "string",
                        "description": "Reason recorded on the change/revision.",
                    },
                    "expected_version": {
                        "type": "integer",
                        "description": (
                            "Last-seen Document version (the ETag source). A "
                            "stale value is refused instead of overwriting."
                        ),
                    },
                },
                "required": ["id"],
            },
        },
        {
            "name": "document.transition",
            "description": (
                "Move a Document through its workflow (write). Entering the "
                "release state applies the F-1 freeze; leaving it re-opens "
                "the document (F-5). Release gates answer DOCUMENT_GATE_FAILED."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "UUID of the document."},
                    "target_state": {
                        "type": "string",
                        "description": (
                            "Requested workflow state (e.g. 'In Prüfung', "
                            "'Freigegeben'). The states are workspace-configured."
                        ),
                    },
                    "change_reason": {
                        "type": "string",
                        "description": "Reason recorded on the transition.",
                    },
                    "credential": {
                        "type": "string",
                        "description": (
                            "Password/TOTP token for a signature-gated transition."
                        ),
                    },
                    "expected_version": {
                        "type": "integer",
                        "description": (
                            "Last-seen Document version. A stale value is "
                            "refused instead of overwriting."
                        ),
                    },
                },
                "required": ["id", "target_state"],
            },
        },
        {
            "name": "document.versions",
            "description": (
                "List a Document's recorded content revisions, oldest first "
                "(read-only)."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "UUID of the document."},
                },
                "required": ["id"],
            },
        },
        {
            "name": "document.diff",
            "description": (
                "Field-level diff between two revisions of a Document "
                "(read-only). from_version 0 is the creation baseline."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "UUID of the document."},
                    "from_version": {
                        "type": "integer",
                        "description": "Source version (default 0 = empty baseline).",
                        "default": 0,
                    },
                    "to_version": {
                        "type": "integer",
                        "description": (
                            "Target version. Defaults to the document's current "
                            "version."
                        ),
                    },
                },
                "required": ["id"],
            },
        },
        {
            "name": "document.project",
            "description": (
                "Render one document as deterministic Markdown (read-only). The "
                "server never writes to a repository; write the content on a "
                "branch and report the hash back via document.projection_status."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Document UUID."},
                },
                "required": ["id"],
            },
        },
        {
            "name": "document.projection_status",
            "description": (
                "Compare client-computed repository file hashes with Loom's "
                "projection state (READ). Returns in_sync | loom_changed | "
                "file_changed | conflict | missing_in_repo | untracked_in_loom "
                "per document. An optional confirm object records a written hash."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace_id": {"type": "string", "description": "Workspace UUID."},
                    "files": {
                        "type": "object",
                        "additionalProperties": {"type": "string"},
                        "description": "Repository path -> SHA-256, computed locally.",
                    },
                    "confirm": {
                        "type": "object",
                        "properties": {
                            "document_id": {"type": "string"},
                            "sha256": {"type": "string"},
                        },
                        "required": ["document_id", "sha256"],
                        "description": "Optional: record the hash that was actually written.",
                    },
                },
                "required": ["workspace_id"],
            },
        },
        {
            "name": "document.adopt",
            "description": (
                "Turn a repo_external document into a loom-owned, projected one "
                "(write). Requires file_sha256 to equal the imported source hash; "
                "otherwise CONFLICT (409)."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Document UUID."},
                    "file_sha256": {
                        "type": "string",
                        "description": "SHA-256 of the repository file.",
                    },
                    "source_path": {"type": "string"},
                    "freeze": {
                        "type": "boolean",
                        "description": "Release (freeze) the document after adoption.",
                    },
                },
                "required": ["id", "file_sha256"],
            },
        },
        {
            "name": "document.outdate",
            "description": (
                "Soft-delete a Document via the workflow engine's outdate "
                "escape hatch (write). The row is kept; status becomes 'outdated'."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "UUID of the document."},
                    "reason": {
                        "type": "string",
                        "description": "Optional audit reason (may be mandatory per preset).",
                    },
                },
                "required": ["id"],
            },
        },
        {
            "name": "document.reactivate",
            "description": (
                "Restore a soft-deleted Document to its previous workflow state "
                "(write)."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "UUID of the document."},
                },
                "required": ["id"],
            },
        },
    ]

    def _svc(self) -> DocumentService:
        return DocumentService()

    # ---- Handlers ---------------------------------------------------------

    def _handle_create(
        self, *, params: dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        workspace_id = require_uuid(params, "workspace_id")
        try:
            title = require_param(params, "title")
            kind = require_param(params, "kind")
            doc_date = _parse_doc_date(params.get("doc_date"))
        except ValueError as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))

        try:
            document = self._svc().create_document(
                workspace_id=workspace_id,
                ctx=auth_context,
                title=str(title),
                kind=str(kind),
                description=params.get("description") or "",
                body=params.get("body") or "",
                doc_date=doc_date,
                custom_fields=params.get("custom_fields"),
            )
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _validation_error(exc)
        except Exception:  # noqa: BLE001 — masked, logged server-side
            return ToolResult.error("INTERNAL_ERROR", "An internal error occurred.")
        return ToolResult.ok({"document": _document_to_dict(document)})

    def _handle_read(
        self, *, params: dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        document_id = require_uuid(params, "id")
        try:
            document = self._svc().get_document(document_id, auth_context)
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        return ToolResult.ok({"document": _document_to_dict(document)})

    # ---------- Projection and adoption (Phase G / #1374 S3) ----------

    def _handle_project(
        self, *, params: dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """Render one document deterministically; nothing is persisted."""
        from application.document_projection_service import (
            DocumentProjectionService,
        )

        document_id = require_uuid(params, "id")
        try:
            projected = DocumentProjectionService().project(document_id, auth_context)
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _validation_error(exc)
        except Exception:  # noqa: BLE001 — masked, logged server-side
            return ToolResult.error("INTERNAL_ERROR", "An internal error occurred.")
        return ToolResult.ok(projected.to_dict())

    def _handle_projection_status(
        self, *, params: dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """Compare repository hashes and optionally confirm one written file."""
        from application.document_projection_service import (
            DocumentProjectionService,
        )

        reject_unknown_params(
            params, ["workspace_id", "files", "confirm"], "document.projection_status"
        )
        workspace_id = require_uuid(params, "workspace_id")
        files = params.get("files") or {}
        if not isinstance(files, dict):
            return ToolResult.error("VALIDATION_ERROR", "files must be an object.")
        confirm = params.get("confirm") or None
        try:
            service = DocumentProjectionService()
            rows = service.status(workspace_id, files, auth_context)
            if confirm:
                service.confirm(
                    require_uuid(confirm, "document_id"),
                    str(confirm.get("sha256") or ""),
                    auth_context,
                )
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _validation_error(exc)
        except Exception:  # noqa: BLE001 — masked, logged server-side
            return ToolResult.error("INTERNAL_ERROR", "An internal error occurred.")
        return ToolResult.ok({"documents": [row.to_dict() for row in rows]})

    def _handle_adopt(
        self, *, params: dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """Adopt a repo-external document once its hash matches."""
        from application.document_projection_service import (
            DocumentProjectionService,
        )

        reject_unknown_params(
            params,
            ["id", "file_sha256", "source_path", "freeze"],
            "document.adopt",
        )
        document_id = require_uuid(params, "id")
        try:
            document = DocumentProjectionService().adopt(
                document_id,
                file_sha256=str(require_param(params, "file_sha256")),
                source_path=str(params.get("source_path") or ""),
                freeze=bool(params.get("freeze", False)),
                ctx=auth_context,
            )
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _validation_error(exc)
        except Exception:  # noqa: BLE001 — masked, logged server-side
            return ToolResult.error("INTERNAL_ERROR", "An internal error occurred.")
        return ToolResult.ok({"document": _document_to_dict(document)})

    def _handle_query(
        self, *, params: dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        workspace_id = require_uuid(params, "workspace_id")
        uid_filter = params.get("uid")
        if uid_filter is not None:
            uid_filter = str(uid_filter).strip() or None
        try:
            documents = self._svc().list_documents(
                workspace_id=workspace_id,
                ctx=auth_context,
                include_deleted=bool(params.get("include_outdated", False)),
            )
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _validation_error(exc)
        except Exception:  # noqa: BLE001 — masked, logged server-side
            return ToolResult.error("INTERNAL_ERROR", "An internal error occurred.")

        if uid_filter is not None:
            documents = [
                doc for doc in documents if str(getattr(doc, "uid", "") or "") == uid_filter
            ]
        status_map = resolve_status_map(
            _ITEM_TYPE, [doc.id for doc in documents]
        )
        return ToolResult.ok({
            "documents": [
                _document_to_dict(doc, status_map=status_map) for doc in documents
            ],
            "count": len(documents),
        })

    def _handle_update(
        self, *, params: dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        document_id = require_uuid(params, "id")
        if "status" in params:
            return ToolResult.error(
                "VALIDATION_ERROR",
                "'status' cannot be changed via document.update; use "
                "document.transition for a state-machine-gated status change.",
            )

        # PATCH semantics: an omitted `doc_date`/`custom_fields` keeps the
        # stored value, so only forward the keys the caller actually sent.
        sentinels: dict[str, Any] = {}
        if "doc_date" in params:
            try:
                sentinels["doc_date"] = _parse_doc_date(params["doc_date"])
            except ValueError as exc:
                return ToolResult.error("VALIDATION_ERROR", str(exc))
        if "custom_fields" in params:
            sentinels["custom_fields"] = params["custom_fields"]

        try:
            document = self._svc().update_document(
                document_id=document_id,
                ctx=auth_context,
                title=params.get("title"),
                kind=params.get("kind"),
                description=params.get("description"),
                body=params.get("body"),
                change_reason=params.get("change_reason"),
                expected_version=params.get("expected_version"),
                **sentinels,
            )
        except OptimisticLockError as exc:
            return ToolResult.error("CONFLICT", f"Version conflict: {exc}")
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _validation_error(exc)
        except Exception:  # noqa: BLE001 — masked, logged server-side
            return ToolResult.error("INTERNAL_ERROR", "An internal error occurred.")
        return ToolResult.ok({"document": _document_to_dict(document)})

    def _handle_transition(
        self, *, params: dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        document_id = require_uuid(params, "id")
        try:
            target_state = require_param(params, "target_state")
        except ValueError as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))

        svc = self._svc()
        try:
            previous_state = svc.current_status(document_id, auth_context)
            document = svc.transition_status(
                document_id,
                str(target_state),
                auth_context,
                change_reason=params.get("change_reason") or "",
                credential=params.get("credential") or "",
                expected_version=params.get("expected_version"),
            )
            new_state = svc.current_status(document_id, auth_context)
        except OptimisticLockError as exc:
            return ToolResult.error("CONFLICT", f"Version conflict: {exc}")
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _validation_error(exc)
        except Exception:  # noqa: BLE001 — masked, logged server-side
            return ToolResult.error("INTERNAL_ERROR", "An internal error occurred.")
        return ToolResult.ok({
            "id": str(document.id),
            "previous_state": previous_state,
            "new_state": new_state,
            "version": document.version,
            "document": _document_to_dict(document),
        })

    def _handle_versions(
        self, *, params: dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        document_id = require_uuid(params, "id")
        try:
            document = self._svc().get_document(document_id, auth_context)
            versions = ArtifactDiffService().list_versions(
                document.artifact_id, auth_context
            )
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        except Exception:  # noqa: BLE001 — masked, logged server-side
            return ToolResult.error("INTERNAL_ERROR", "An internal error occurred.")
        return ToolResult.ok({"versions": versions, "count": len(versions)})

    def _handle_diff(
        self, *, params: dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        document_id = require_uuid(params, "id")
        try:
            document = self._svc().get_document(document_id, auth_context)
            from_version = int(params.get("from_version", 0))
            to_version = int(
                params.get("to_version", document.version)
                if params.get("to_version") is not None
                else document.version
            )
        except (TypeError, ValueError) as exc:
            return ToolResult.error("VALIDATION_ERROR", f"Invalid version: {exc}")
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))

        try:
            result = ArtifactDiffService().diff(
                artifact_id=document.artifact_id,
                from_version=from_version,
                to_version=to_version,
                ctx=auth_context,
            )
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        except (ValidationError, ValueError) as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))
        except Exception:  # noqa: BLE001 — masked, logged server-side
            return ToolResult.error("INTERNAL_ERROR", "An internal error occurred.")
        return ToolResult.ok({"diff": result})

    def _handle_outdate(
        self, *, params: dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        document_id = require_uuid(params, "id")
        try:
            self._svc().delete_document(
                document_id,
                auth_context,
                change_reason=params.get("reason") or "",
            )
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _validation_error(exc)
        except Exception:  # noqa: BLE001 — masked, logged server-side
            return ToolResult.error("INTERNAL_ERROR", "An internal error occurred.")
        return ToolResult.ok({"id": str(document_id), "status": "outdated"})

    def _handle_reactivate(
        self, *, params: dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        document_id = require_uuid(params, "id")
        svc = self._svc()
        try:
            document = svc.restore_document(document_id, auth_context)
            new_state = svc.current_status(document_id, auth_context)
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _validation_error(exc)
        except Exception:  # noqa: BLE001 — masked, logged server-side
            return ToolResult.error("INTERNAL_ERROR", "An internal error occurred.")
        return ToolResult.ok({
            "id": str(document_id),
            "previous_state": "outdated",
            "new_state": new_state,
            "document": _document_to_dict(document),
        })


__all__ = ["DocumentToolGroup"]
