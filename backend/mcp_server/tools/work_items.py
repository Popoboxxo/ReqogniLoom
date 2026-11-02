"""MCP tool group for the ``WorkItem`` artifact (``work_item.*``).

Plan F F3-T6 (#1374). The ``WorkItem`` artifact has had a REST surface since
F3-T5 but no MCP tool group, so an agent could not read, author or resume a
work item at all. This group closes that asymmetry — it is the F3-T6
counterpart of ``rest_api.views.WorkItemViewSet`` and keeps the same contract:

  work_item.create       — create an item in a document (write)
  work_item.read         — fetch one item incl. its custom fields (read)
  work_item.query        — list a workspace's items (read)
  work_item.update       — update content fields / custom fields (write)
  work_item.transition   — move through the workflow (write)
  work_item.set_progress — set 0–100 progress independently of the state (write)
  work_item.checkpoint   — create a Checkpoint with a resume hint (write)
  work_item.resume       — newest checkpoint + every open item (read)

Every write goes through :class:`application.work_item_service.WorkItemService`
(ADR-01) — no business logic here. In particular the mandatory document, rule
10 (``blocked`` needs a reason), the extended preset's human sign-off and the
optimistic-lock compare stay in the service, so this transport cannot bypass
them; the JSON-RPC error codes are the ones the REST layer reports
(``CONFLICT`` / ``PERMISSION_DENIED`` / ``VALIDATION_ERROR``).

**Loom ≠ memory (spec §12).** A work item is Loom's explicit, queryable answer
to "where does this stand, what is open, what comes next" — deterministic and
linked. Conversation memory ("what was said, how does the user tick") lives in
``memory.*`` (Honcho) and is deliberately not duplicated here.

No ORM access in this module (ADR-01).
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from django.utils import timezone
from django.utils.dateparse import parse_datetime

from application.base import (
    NotFoundError,
    OptimisticLockError,
    ValidationError,
)
from application.work_item_service import WorkItemService
from auth_tenancy.context import AuthContext
from mcp_server.protocol_handler import ToolResult
from mcp_server.tools.base import (
    BaseToolGroup,
    artifact_custom_fields,
    require_param,
    require_uuid,
    resolve_engine_status,
    resolve_status_map,
)
from persistence.errors import PermissionDeniedError
from persistence.models import WorkItem

#: The workflow item type this group speaks about (PascalCase).
_ITEM_TYPE = "WorkItem"

#: The kinds the ``WorkItem`` model accepts; the schemas publish them so a
#: client does not have to guess the enum (#345-style honesty).
_KINDS: tuple[str, ...] = tuple(WorkItem.Kind.values)

#: Spec §12 (Loom vs. memory), named verbatim in every ``work_item.*`` tool
#: description (F3-T8). An agent choosing between the groups must be able to
#: tell "where the work stands" (Loom) from "what was said" (memory/Honcho).
LOOM_MEMORY_BOUNDARY = (
    "Loom work state ('where the work stands', explicit and queryable) is not "
    "conversation memory ('what was said', memory.*/Honcho); memory is not "
    "duplicated here."
)


def _iso(value: Any) -> str | None:
    """Render a ``date``/``datetime`` as ISO-8601, or ``None``."""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _parse_due_date(value: Any) -> datetime | None:
    """Normalise the wire ``due_date`` (string/null/datetime) to a datetime.

    JSON has no datetime type, so MCP callers send an ISO-8601 string. A naive
    timestamp is attached to the project timezone, mirroring what DRF's
    ``DateTimeField`` does for the REST endpoint.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = parse_datetime(str(value))
        if parsed is None:
            raise ValidationError(
                f"Invalid due_date {value!r}; expected an ISO-8601 datetime."
            )
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed)
    return parsed


def _work_item_to_dict(
    item: WorkItem, status_map: dict[str, str] | None = None
) -> dict[str, Any]:
    """Serialize a ``WorkItem`` ORM row for the MCP responses.

    Mirrors ``rest_api.views._work_item_to_dict`` / ``WorkItemSerializer``
    field-for-field, plus the ``status`` value the workflow engine owns (the
    model deliberately has no lifecycle column, REQ-143). ``custom_fields``
    lives on the backing ``Artifact`` and is normalised to a dict.
    """
    return {
        "id": str(item.id),
        "workspace_id": str(item.workspace_id),
        "document_id": str(item.document_id),
        "artifact_id": (
            str(item.artifact_id) if getattr(item, "artifact_id", None) else None
        ),
        "uid": getattr(item, "uid", None),
        "title": item.title,
        "kind": item.kind,
        "ordinal": item.ordinal,
        "body": getattr(item, "body", ""),
        "progress": item.progress,
        "blocked_reason": getattr(item, "blocked_reason", ""),
        "next_action": getattr(item, "next_action", ""),
        "last_activity_at": _iso(getattr(item, "last_activity_at", None)),
        "last_actor": getattr(item, "last_actor", ""),
        "evidence_ref": getattr(item, "evidence_ref", ""),
        "approved_by": getattr(item, "approved_by", ""),
        "approved_at": _iso(getattr(item, "approved_at", None)),
        "due_date": _iso(getattr(item, "due_date", None)),
        "exit_criteria": getattr(item, "exit_criteria", ""),
        "custom_fields": artifact_custom_fields(item),
        "status": resolve_engine_status(
            _ITEM_TYPE, item.id, status_map=status_map
        ),
        "version": item.version,
        "created_at": _iso(getattr(item, "created_at", None)),
        "updated_at": _iso(getattr(item, "modified_at", None)),
    }


def _validation_error(exc: Exception) -> ToolResult:
    """Map a service validation error to its transport error code.

    A ``ValidationError`` subclass may carry a stable ``error_code`` — the same
    code the REST layer answers. Forwarding it keeps the two transports
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


class WorkItemToolGroup(BaseToolGroup):
    """MCP tool group for the ``work_item.*`` namespace (Plan F F3-T6)."""

    _TOOL_MAP = {
        "work_item.create": "_handle_create",
        "work_item.read": "_handle_read",
        "work_item.query": "_handle_query",
        "work_item.update": "_handle_update",
        "work_item.transition": "_handle_transition",
        "work_item.set_progress": "_handle_set_progress",
        "work_item.checkpoint": "_handle_checkpoint",
        "work_item.resume": "_handle_resume",
    }

    _TOOL_SCHEMAS = [
        {
            "name": "work_item.create",
            "description": (
                "Create a WorkItem inside a document (write). A work item is "
                "the explicit, queryable work state of the Loom (progress, "
                "blocked reason, resume hint, heartbeat) — not conversation "
                "memory, which stays in memory.*. The local identifier WI-NNN "
                "and the initial workflow state are assigned server-side."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace_id": {
                        "type": "string",
                        "description": "Required. UUID of the target workspace.",
                    },
                    "document_id": {
                        "type": "string",
                        "description": (
                            "Required. Owning document; a work item never "
                            "exists without one."
                        ),
                    },
                    "kind": {
                        "type": "string",
                        "enum": list(_KINDS),
                        "description": "Required. Work-item kind.",
                    },
                    "title": {
                        "type": "string",
                        "description": "Required. Item title (max 255 characters).",
                    },
                    "body": {
                        "type": "string",
                        "description": "Markdown of the section. Defaults to ''.",
                    },
                    "ordinal": {
                        "type": "integer",
                        "minimum": 0,
                        "description": (
                            "Position inside the document. Resume sorts by "
                            "(ordinal, id). Defaults to 0."
                        ),
                    },
                    "progress": {
                        "type": ["integer", "null"],
                        "minimum": 0,
                        "maximum": 100,
                        "description": "Optional 0-100 progress.",
                    },
                    "blocked_reason": {
                        "type": "string",
                        "description": (
                            "Reason for a blocked item (or the dismissal reason "
                            "of a dropped one)."
                        ),
                    },
                    "next_action": {
                        "type": "string",
                        "description": "Resume hint ('where to continue').",
                    },
                    "evidence_ref": {
                        "type": "string",
                        "description": "Evidence (commit, test run, artifact id).",
                    },
                    "due_date": {
                        "type": ["string", "null"],
                        "description": "Optional due date (ISO-8601 datetime).",
                    },
                    "exit_criteria": {
                        "type": "string",
                        "description": "Definition of done for this item.",
                    },
                    "custom_fields": {
                        "type": "object",
                        "additionalProperties": True,
                        "description": (
                            "Extended user-defined attributes (flat key/value "
                            "map) defined by this workspace's attribute definition."
                        ),
                    },
                    "actor": {
                        "type": "string",
                        "description": (
                            "Optional free-text actor label for the heartbeat; "
                            "defaults to the API key's agent label."
                        ),
                    },
                },
                "required": ["workspace_id", "document_id", "kind", "title"],
            },
        },
        {
            "name": "work_item.read",
            "description": (
                "Fetch a single WorkItem by ID, including progress, blocked "
                "reason, resume hint, heartbeat and extended attributes "
                "(read-only). Loom owns this explicit work state; conversation "
                "memory is memory.* (Honcho), not here."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "UUID of the work item."},
                },
                "required": ["id"],
            },
        },
        {
            "name": "work_item.query",
            "description": (
                "List a workspace's work items, ordered by (ordinal, id) "
                "(read-only). Soft-deleted items are omitted unless "
                "include_outdated is true. This is the queryable Loom work "
                "state, not conversation memory (memory.*)."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace_id": {
                        "type": "string",
                        "description": "Required. UUID of the target workspace.",
                    },
                    "document_id": {
                        "type": "string",
                        "description": "Optional. Only items of this document.",
                    },
                    "include_outdated": {
                        "type": "boolean",
                        "description": (
                            "If true, include soft-deleted items (REST's "
                            "?include_deleted=true). Defaults to false."
                        ),
                    },
                    "uid": {
                        "type": "string",
                        "description": (
                            "Optional local identifier (e.g. 'WI-004'); when "
                            "supplied, only the item carrying it is returned."
                        ),
                    },
                },
                "required": ["workspace_id"],
            },
        },
        {
            "name": "work_item.update",
            "description": (
                "Update a WorkItem's content fields and/or extended attributes "
                "(write). Omitted fields keep their current value; the owning "
                "document is immutable. A stale expected_version is refused "
                "with CONFLICT."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "UUID of the work item."},
                    "title": {"type": "string", "description": "New title."},
                    "kind": {
                        "type": "string",
                        "enum": list(_KINDS),
                        "description": "New work-item kind.",
                    },
                    "body": {"type": "string", "description": "New markdown body."},
                    "ordinal": {
                        "type": "integer",
                        "minimum": 0,
                        "description": "New position inside the document.",
                    },
                    "progress": {
                        "type": ["integer", "null"],
                        "minimum": 0,
                        "maximum": 100,
                        "description": "New progress; null clears it.",
                    },
                    "blocked_reason": {"type": "string"},
                    "next_action": {"type": "string"},
                    "evidence_ref": {"type": "string"},
                    "due_date": {
                        "type": ["string", "null"],
                        "description": "New due date (ISO-8601 datetime); null clears it.",
                    },
                    "exit_criteria": {"type": "string"},
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
                            "Last-seen item version (the ETag source). A stale "
                            "value is refused instead of overwriting."
                        ),
                    },
                    "actor": {
                        "type": "string",
                        "description": "Optional free-text actor label for the heartbeat.",
                    },
                },
                "required": ["id"],
            },
        },
        {
            "name": "work_item.transition",
            "description": (
                "Move a WorkItem through its workflow (write). Entering "
                "'blocked' requires a non-empty blocked_reason; the extended "
                "preset's sign-off transition requires an approver/admin role. "
                "A stale expected_version is refused with CONFLICT."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "UUID of the work item."},
                    "target_state": {
                        "type": "string",
                        "description": (
                            "Requested workflow state (e.g. 'in_progress', "
                            "'blocked', 'done'). The states are "
                            "workspace-configured."
                        ),
                    },
                    "blocked_reason": {
                        "type": "string",
                        "description": (
                            "Mandatory when entering 'blocked'; otherwise an "
                            "optional reason/history hint."
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
                            "Last-seen item version. A stale value is refused "
                            "instead of overwriting."
                        ),
                    },
                    "actor": {
                        "type": "string",
                        "description": "Optional free-text actor label for the heartbeat.",
                    },
                },
                "required": ["id", "target_state"],
            },
        },
        {
            "name": "work_item.set_progress",
            "description": (
                "Set a WorkItem's progress (0-100) and stamp the heartbeat "
                "(write). Progress is independent of the workflow state in "
                "every preset."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "UUID of the work item."},
                    "progress": {
                        "type": "integer",
                        "minimum": 0,
                        "maximum": 100,
                        "description": "Required. New progress, 0-100.",
                    },
                    "change_reason": {
                        "type": "string",
                        "description": "Optional audit reason.",
                    },
                    "expected_version": {
                        "type": "integer",
                        "description": (
                            "Last-seen item version. A stale value is refused "
                            "instead of overwriting."
                        ),
                    },
                    "actor": {
                        "type": "string",
                        "description": "Optional free-text actor label for the heartbeat.",
                    },
                },
                "required": ["id", "progress"],
            },
        },
        {
            "name": "work_item.checkpoint",
            "description": (
                "Create a Checkpoint item carrying the resume hint ('continue "
                "here') in a document (write). A checkpoint is an informational "
                "marker, not a work deliverable, so it needs no trace link."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace_id": {
                        "type": "string",
                        "description": "Required. UUID of the target workspace.",
                    },
                    "document_id": {
                        "type": "string",
                        "description": "Required. Owning document.",
                    },
                    "next_action": {
                        "type": "string",
                        "description": (
                            "Required. Where to continue — the resume hint."
                        ),
                    },
                    "title": {
                        "type": "string",
                        "description": "Checkpoint title. Defaults to 'Checkpoint'.",
                    },
                    "body": {
                        "type": "string",
                        "description": "Optional markdown note.",
                    },
                    "ordinal": {
                        "type": "integer",
                        "minimum": 0,
                        "description": "Position inside the document. Defaults to 0.",
                    },
                    "actor": {
                        "type": "string",
                        "description": "Optional free-text actor label for the heartbeat.",
                    },
                },
                "required": ["workspace_id", "document_id", "next_action"],
            },
        },
        {
            "name": "work_item.resume",
            "description": (
                "Return the document's newest checkpoint and every open work "
                "item, sorted by (ordinal, id) (read-only). This is the single "
                "call an agent without repo access needs to answer 'where do I "
                "continue?' — Loom's explicit work state, not conversation "
                "memory (memory.*)."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace_id": {
                        "type": "string",
                        "description": "Required. UUID of the workspace.",
                    },
                    "document_id": {
                        "type": "string",
                        "description": "Required. Document whose work state is resumed.",
                    },
                    "actor": {
                        "type": "string",
                        "description": (
                            "Optional caller label (informational; not persisted)."
                        ),
                    },
                },
                "required": ["workspace_id", "document_id"],
            },
        },
    ]

    # F3-T8 (spec §12): the boundary is named verbatim in every tool
    # description, not only in this module's docstring.
    for _schema in _TOOL_SCHEMAS:
        _schema["description"] = (
            f"{_schema['description']} {LOOM_MEMORY_BOUNDARY}"
        )
    del _schema

    def _svc(self) -> WorkItemService:
        return WorkItemService()

    # ---- Handlers ---------------------------------------------------------

    def _handle_create(
        self, *, params: dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        workspace_id = require_uuid(params, "workspace_id")
        document_id = require_uuid(params, "document_id")
        try:
            kind = require_param(params, "kind")
            title = require_param(params, "title")
            due_date = _parse_due_date(params.get("due_date"))
        except ValidationError as exc:
            return _validation_error(exc)
        except ValueError as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))

        try:
            item = self._svc().create_work_item(
                workspace_id=workspace_id,
                document_id=document_id,
                ctx=auth_context,
                kind=str(kind),
                title=str(title),
                body=params.get("body") or "",
                ordinal=params.get("ordinal", 0),
                progress=params.get("progress"),
                blocked_reason=params.get("blocked_reason") or "",
                next_action=params.get("next_action") or "",
                evidence_ref=params.get("evidence_ref") or "",
                due_date=due_date,
                exit_criteria=params.get("exit_criteria") or "",
                custom_fields=params.get("custom_fields"),
                actor=params.get("actor") or "",
            )
        except OptimisticLockError as exc:
            return ToolResult.error("CONFLICT", f"Version conflict: {exc}")
        except ValidationError as exc:
            return _validation_error(exc)
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        except Exception:  # noqa: BLE001 — masked, logged server-side
            return ToolResult.error("INTERNAL_ERROR", "An internal error occurred.")
        return ToolResult.ok({"work_item": _work_item_to_dict(item)})

    def _handle_read(
        self, *, params: dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        item_id = require_uuid(params, "id")
        try:
            item = self._svc().get_work_item(item_id, auth_context)
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        return ToolResult.ok({"work_item": _work_item_to_dict(item)})

    def _handle_query(
        self, *, params: dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        workspace_id = require_uuid(params, "workspace_id")
        document_id = (
            require_uuid(params, "document_id")
            if params.get("document_id") not in (None, "")
            else None
        )
        uid_filter = params.get("uid")
        if uid_filter is not None:
            uid_filter = str(uid_filter).strip() or None
        try:
            items = self._svc().list_work_items(
                workspace_id=workspace_id,
                ctx=auth_context,
                document_id=document_id,
                include_deleted=bool(params.get("include_outdated", False)),
            )
        except ValidationError as exc:
            return _validation_error(exc)
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        except Exception:  # noqa: BLE001 — masked, logged server-side
            return ToolResult.error("INTERNAL_ERROR", "An internal error occurred.")

        if uid_filter is not None:
            items = [
                item
                for item in items
                if str(getattr(item, "uid", "") or "") == uid_filter
            ]
        status_map = resolve_status_map(_ITEM_TYPE, [item.id for item in items])
        return ToolResult.ok({
            "work_items": [
                _work_item_to_dict(item, status_map=status_map) for item in items
            ],
            "count": len(items),
        })

    def _handle_update(
        self, *, params: dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        item_id = require_uuid(params, "id")
        if "status" in params:
            return ToolResult.error(
                "VALIDATION_ERROR",
                "'status' cannot be changed via work_item.update; use "
                "work_item.transition for a state-machine-gated status change.",
            )
        if "document_id" in params:
            return ToolResult.error(
                "VALIDATION_ERROR",
                "document_id is immutable; a work item cannot be moved to "
                "another document.",
            )

        # PATCH semantics: only forward the keys the caller actually sent, so
        # an omitted value keeps the stored one while an explicit null clears.
        sentinels: dict[str, Any] = {}
        if "progress" in params:
            sentinels["progress"] = params["progress"]
        if "custom_fields" in params:
            sentinels["custom_fields"] = params["custom_fields"]
        if "due_date" in params:
            try:
                sentinels["due_date"] = _parse_due_date(params["due_date"])
            except ValidationError as exc:
                return _validation_error(exc)

        try:
            item = self._svc().update_work_item(
                item_id=item_id,
                ctx=auth_context,
                title=params.get("title"),
                kind=params.get("kind"),
                body=params.get("body"),
                ordinal=params.get("ordinal"),
                blocked_reason=params.get("blocked_reason"),
                next_action=params.get("next_action"),
                evidence_ref=params.get("evidence_ref"),
                exit_criteria=params.get("exit_criteria"),
                change_reason=params.get("change_reason"),
                expected_version=params.get("expected_version"),
                actor=params.get("actor") or "",
                **sentinels,
            )
        except OptimisticLockError as exc:
            return ToolResult.error("CONFLICT", f"Version conflict: {exc}")
        except ValidationError as exc:
            return _validation_error(exc)
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        except Exception:  # noqa: BLE001 — masked, logged server-side
            return ToolResult.error("INTERNAL_ERROR", "An internal error occurred.")
        return ToolResult.ok({"work_item": _work_item_to_dict(item)})

    def _handle_transition(
        self, *, params: dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        item_id = require_uuid(params, "id")
        try:
            target_state = require_param(params, "target_state")
        except ValueError as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))

        svc = self._svc()
        try:
            previous_state = svc.current_status(item_id, auth_context)
            item = svc.transition(
                item_id,
                str(target_state),
                auth_context,
                blocked_reason=params.get("blocked_reason"),
                change_reason=params.get("change_reason") or "",
                credential=params.get("credential") or "",
                expected_version=params.get("expected_version"),
                actor=params.get("actor") or "",
            )
            new_state = svc.current_status(item_id, auth_context)
        except OptimisticLockError as exc:
            return ToolResult.error("CONFLICT", f"Version conflict: {exc}")
        except ValidationError as exc:
            return _validation_error(exc)
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        except Exception:  # noqa: BLE001 — masked, logged server-side
            return ToolResult.error("INTERNAL_ERROR", "An internal error occurred.")
        return ToolResult.ok({
            "id": str(item.id),
            "previous_state": previous_state,
            "new_state": new_state,
            "version": item.version,
            "work_item": _work_item_to_dict(item),
        })

    def _handle_set_progress(
        self, *, params: dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        item_id = require_uuid(params, "id")
        try:
            progress = require_param(params, "progress")
        except ValueError as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))

        try:
            item = self._svc().set_progress(
                item_id,
                progress,
                auth_context,
                change_reason=params.get("change_reason"),
                expected_version=params.get("expected_version"),
                actor=params.get("actor") or "",
            )
        except OptimisticLockError as exc:
            return ToolResult.error("CONFLICT", f"Version conflict: {exc}")
        except ValidationError as exc:
            return _validation_error(exc)
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        except Exception:  # noqa: BLE001 — masked, logged server-side
            return ToolResult.error("INTERNAL_ERROR", "An internal error occurred.")
        return ToolResult.ok({"work_item": _work_item_to_dict(item)})

    def _handle_checkpoint(
        self, *, params: dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        workspace_id = require_uuid(params, "workspace_id")
        document_id = require_uuid(params, "document_id")
        try:
            next_action = require_param(params, "next_action")
        except ValueError as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))

        try:
            item = self._svc().checkpoint(
                workspace_id,
                document_id,
                auth_context,
                next_action=str(next_action),
                title=params.get("title") or "Checkpoint",
                body=params.get("body") or "",
                ordinal=params.get("ordinal", 0),
                actor=params.get("actor") or "",
            )
        except ValidationError as exc:
            return _validation_error(exc)
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        except Exception:  # noqa: BLE001 — masked, logged server-side
            return ToolResult.error("INTERNAL_ERROR", "An internal error occurred.")
        return ToolResult.ok({"work_item": _work_item_to_dict(item)})

    def _handle_resume(
        self, *, params: dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        workspace_id = require_uuid(params, "workspace_id")
        document_id = require_uuid(params, "document_id")
        try:
            result = self._svc().resume(
                workspace_id,
                document_id,
                auth_context,
                actor=params.get("actor") or "",
            )
        except ValidationError as exc:
            return _validation_error(exc)
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        except Exception:  # noqa: BLE001 — masked, logged server-side
            return ToolResult.error("INTERNAL_ERROR", "An internal error occurred.")
        return ToolResult.ok(result)


__all__ = ["WorkItemToolGroup"]
