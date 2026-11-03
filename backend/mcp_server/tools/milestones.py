"""MCP tool group for planned review milestones (``milestone.*``).

Plan B B6-T2 (#879). ``Milestone`` has had a model and a service since B6-T1
but no MCP surface, so an agent could not plan or inspect a formal review. This
group is the MCP counterpart of ``rest_api.views.MilestoneViewSet`` and keeps
the same contract:

  milestone.create         — plan a review in a workspace (write)
  milestone.get            — fetch one milestone (read)
  milestone.list           — list a workspace's milestones (read)
  milestone.update         — update name/review_type/target_date/status (write)
  milestone.bind_baseline  — bind a baseline of the same workspace (write)
  milestone.record_audit   — freeze the workspace's SE-Auditor counts (write)

Every write goes through :class:`application.milestone_service
.MilestoneService` (ADR-01) — no business logic here. A milestone is a plain
tenant-scoped planning row (ENT-B2 = a — only ``Milestone``, no ``Measure``):
no backing ``Artifact``, no ``uid``, no workflow state and no trace-link
endpoints, so there is deliberately no ``milestone.delete`` tool (deletion is a
REST-only administrative act; the MCP surface plans and records).

The step ``record_audit`` is a **record, never a gate**: open blockers are
stored on the milestone and refuse nothing (unlike the baseline gate, GH-513).
A stale ``expected_version`` is answered with ``CONFLICT``, the same code the
REST layer reports (409).

No ORM access in this module (ADR-01).
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from application.base import (
    NotFoundError,
    OptimisticLockError,
    ValidationError,
)
from application.milestone_service import MilestoneService
from auth_tenancy.context import AuthContext
from mcp_server.protocol_handler import ToolResult
from mcp_server.tools.base import (
    BaseToolGroup,
    reject_unknown_params,
    require_param,
    require_uuid,
)
from persistence.errors import PermissionDeniedError
from persistence.models import Milestone

_REVIEW_TYPES: tuple[str, ...] = tuple(Milestone.ReviewType.values)
_STATUSES: tuple[str, ...] = tuple(Milestone.Status.values)

_CREATE_PARAMS = [
    "workspace_id",
    "name",
    "review_type",
    "target_date",
    "status",
    "baseline_id",
]
_UPDATE_PARAMS = [
    "id",
    "name",
    "review_type",
    "target_date",
    "status",
    # Declared so the handler can answer with the actionable "use
    # milestone.bind_baseline" message instead of the generic unknown-param one.
    "baseline_id",
    "change_reason",
    "expected_version",
]


def _iso(value: Any) -> str | None:
    """Render a ``date``/``datetime`` as ISO-8601, or return it unchanged."""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _parse_target_date(value: Any) -> date:
    """Normalise the wire ``target_date`` (ISO-8601 date string) to a ``date``."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise ValidationError(
            f"Invalid target_date {value!r}; expected an ISO-8601 date (YYYY-MM-DD)."
        ) from exc


def _milestone_to_dict(milestone: Milestone) -> dict[str, Any]:
    """Serialize a ``Milestone`` ORM row for the MCP responses.

    Mirrors ``rest_api.views._milestone_to_dict`` / ``MilestoneSerializer``
    field-for-field: ``target_date`` as an ISO date, ``baseline_id`` as a
    string or ``None`` and ``audit_snapshot`` passed through unchanged.
    """
    return {
        "id": str(milestone.id),
        "workspace_id": str(milestone.workspace_id),
        "name": milestone.name,
        "review_type": milestone.review_type,
        "target_date": _iso(milestone.target_date),
        "status": milestone.status,
        "baseline_id": (
            str(milestone.baseline_id)
            if getattr(milestone, "baseline_id", None)
            else None
        ),
        "audit_snapshot": getattr(milestone, "audit_snapshot", None),
        "version": milestone.version,
        "created_at": _iso(getattr(milestone, "created_at", None)),
        "updated_at": _iso(
            getattr(milestone, "updated_at", None)
            or getattr(milestone, "modified_at", None)
        ),
    }


def _validation_error(exc: Exception) -> ToolResult:
    """Map a service validation error to its transport error code."""
    code = getattr(exc, "error_code", None) or "VALIDATION_ERROR"
    details = getattr(exc, "details", None)
    return ToolResult.error(
        code,
        str(exc),
        details={"details": details} if details else None,
    )


class MilestoneToolGroup(BaseToolGroup):
    """MCP tool group for the ``milestone.*`` namespace (Plan B B6-T2)."""

    _TOOL_MAP = {
        "milestone.create": "_handle_create",
        "milestone.get": "_handle_get",
        "milestone.list": "_handle_list",
        "milestone.update": "_handle_update",
        "milestone.bind_baseline": "_handle_bind_baseline",
        "milestone.record_audit": "_handle_record_audit",
    }

    _TOOL_SCHEMAS = [
        {
            "name": "milestone.create",
            "description": (
                "Plan a formal review milestone (SRR/PDR/CDR/TRR/ORR/OTHER) in "
                "a workspace (write). An optional baseline_id must belong to "
                "the same workspace; a cross-workspace binding is refused with "
                "VALIDATION_ERROR."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace_id": {
                        "type": "string",
                        "description": "Required. UUID of the target workspace.",
                    },
                    "name": {
                        "type": "string",
                        "description": "Required. Milestone name (max 200 characters).",
                    },
                    "review_type": {
                        "type": "string",
                        "enum": list(_REVIEW_TYPES),
                        "description": "Required. Formal review this milestone plans.",
                    },
                    "target_date": {
                        "type": "string",
                        "description": "Required. Planned review date (YYYY-MM-DD).",
                    },
                    "status": {
                        "type": "string",
                        "enum": list(_STATUSES),
                        "description": "Planning/execution state. Defaults to 'planned'.",
                    },
                    "baseline_id": {
                        "type": "string",
                        "description": (
                            "Optional. Baseline of the same workspace to bind."
                        ),
                    },
                },
                "required": ["workspace_id", "name", "review_type", "target_date"],
            },
        },
        {
            "name": "milestone.get",
            "description": (
                "Fetch a single milestone by ID, including its bound baseline "
                "and the frozen audit snapshot (read-only)."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "UUID of the milestone."},
                },
                "required": ["id"],
            },
        },
        {
            "name": "milestone.list",
            "description": (
                "List a workspace's milestones, ordered by target_date then id "
                "(read-only). A foreign or unknown workspace answers NOT_FOUND."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace_id": {
                        "type": "string",
                        "description": "Required. UUID of the target workspace.",
                    },
                },
                "required": ["workspace_id"],
            },
        },
        {
            "name": "milestone.update",
            "description": (
                "Update a milestone's name, review type, target date and/or "
                "status (write). Omitted fields keep their current value; the "
                "owning workspace is immutable. A stale expected_version is "
                "refused with CONFLICT."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "UUID of the milestone."},
                    "name": {"type": "string", "description": "New name."},
                    "review_type": {
                        "type": "string",
                        "enum": list(_REVIEW_TYPES),
                        "description": "New review type.",
                    },
                    "target_date": {
                        "type": "string",
                        "description": "New target date (YYYY-MM-DD).",
                    },
                    "status": {
                        "type": "string",
                        "enum": list(_STATUSES),
                        "description": "New planning/execution state.",
                    },
                    "change_reason": {
                        "type": "string",
                        "description": "Reason recorded on the audit trail.",
                    },
                    "expected_version": {
                        "type": "integer",
                        "description": (
                            "Last-seen milestone version (the ETag source). A "
                            "stale value is refused with CONFLICT."
                        ),
                    },
                },
                "required": ["id"],
            },
        },
        {
            "name": "milestone.bind_baseline",
            "description": (
                "Bind a baseline to a milestone of the same workspace (write). "
                "A baseline from another workspace is refused with "
                "VALIDATION_ERROR; a stale expected_version with CONFLICT."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "UUID of the milestone."},
                    "baseline_id": {
                        "type": "string",
                        "description": "Required. UUID of the baseline to bind.",
                    },
                    "change_reason": {
                        "type": "string",
                        "description": "Reason recorded on the audit trail.",
                    },
                    "expected_version": {
                        "type": "integer",
                        "description": (
                            "Last-seen milestone version. A stale value is "
                            "refused with CONFLICT."
                        ),
                    },
                },
                "required": ["id", "baseline_id"],
            },
        },
        {
            "name": "milestone.record_audit",
            "description": (
                "Run the SE-Auditor for the milestone's workspace and freeze "
                "{tier, counts, run_at} into its audit_snapshot (write). This "
                "is a record, never a gate: open blockers do not refuse it."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "UUID of the milestone."},
                    "change_reason": {
                        "type": "string",
                        "description": "Reason recorded on the audit trail.",
                    },
                    "expected_version": {
                        "type": "integer",
                        "description": (
                            "Last-seen milestone version. A stale value is "
                            "refused with CONFLICT."
                        ),
                    },
                },
                "required": ["id"],
            },
        },
    ]

    def _svc(self) -> MilestoneService:
        return MilestoneService()

    # ---- Handlers ---------------------------------------------------------

    def _handle_create(
        self, *, params: dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        try:
            reject_unknown_params(params, _CREATE_PARAMS, "milestone.create")
            workspace_id = require_uuid(params, "workspace_id")
            name = require_param(params, "name")
            review_type = require_param(params, "review_type")
            target_date = _parse_target_date(require_param(params, "target_date"))
        except ValidationError as exc:
            return _validation_error(exc)
        except ValueError as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))

        baseline_id = params.get("baseline_id") or None
        try:
            milestone = self._svc().create(
                auth_context,
                workspace_id=workspace_id,
                name=str(name),
                review_type=str(review_type),
                target_date=target_date,
                status=params.get("status") or Milestone.Status.PLANNED,
                baseline_id=baseline_id,
            )
        except ValidationError as exc:
            return _validation_error(exc)
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        except Exception:  # noqa: BLE001 — masked, logged server-side
            return ToolResult.error("INTERNAL_ERROR", "An internal error occurred.")
        return ToolResult.ok({"milestone": _milestone_to_dict(milestone)})

    def _handle_get(
        self, *, params: dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        try:
            reject_unknown_params(params, ["id"], "milestone.get")
            milestone_id = require_uuid(params, "id")
        except ValueError as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))
        try:
            milestone = self._svc().get(milestone_id, auth_context)
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        return ToolResult.ok({"milestone": _milestone_to_dict(milestone)})

    def _handle_list(
        self, *, params: dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        try:
            reject_unknown_params(params, ["workspace_id"], "milestone.list")
            workspace_id = require_uuid(params, "workspace_id")
        except ValueError as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))
        try:
            items = self._svc().list(workspace_id, auth_context)
        except ValidationError as exc:
            return _validation_error(exc)
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        except Exception:  # noqa: BLE001 — masked, logged server-side
            return ToolResult.error("INTERNAL_ERROR", "An internal error occurred.")
        return ToolResult.ok({
            "milestones": [_milestone_to_dict(item) for item in items],
            "count": len(items),
        })

    def _handle_update(
        self, *, params: dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        try:
            reject_unknown_params(params, _UPDATE_PARAMS, "milestone.update")
            milestone_id = require_uuid(params, "id")
        except ValueError as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))

        if "baseline_id" in params:
            return ToolResult.error(
                "VALIDATION_ERROR",
                "baseline_id is not an update field; use "
                "milestone.bind_baseline to bind a baseline.",
            )

        target_date = None
        if "target_date" in params:
            try:
                target_date = _parse_target_date(params["target_date"])
            except ValidationError as exc:
                return _validation_error(exc)

        try:
            milestone = self._svc().update(
                milestone_id,
                auth_context,
                name=params.get("name"),
                review_type=params.get("review_type"),
                target_date=target_date,
                status=params.get("status"),
                change_reason=params.get("change_reason"),
                expected_version=params.get("expected_version"),
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
        return ToolResult.ok({"milestone": _milestone_to_dict(milestone)})

    def _handle_bind_baseline(
        self, *, params: dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        try:
            reject_unknown_params(
                params,
                ["id", "baseline_id", "change_reason", "expected_version"],
                "milestone.bind_baseline",
            )
            milestone_id = require_uuid(params, "id")
            baseline_id = require_uuid(params, "baseline_id")
        except ValueError as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))

        try:
            milestone = self._svc().bind_baseline(
                milestone_id,
                baseline_id,
                auth_context,
                change_reason=params.get("change_reason"),
                expected_version=params.get("expected_version"),
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
        return ToolResult.ok({"milestone": _milestone_to_dict(milestone)})

    def _handle_record_audit(
        self, *, params: dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        try:
            reject_unknown_params(
                params,
                ["id", "change_reason", "expected_version"],
                "milestone.record_audit",
            )
            milestone_id = require_uuid(params, "id")
        except ValueError as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))

        try:
            milestone = self._svc().record_audit(
                milestone_id,
                auth_context,
                change_reason=params.get("change_reason"),
                expected_version=params.get("expected_version"),
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
        return ToolResult.ok({"milestone": _milestone_to_dict(milestone)})


__all__ = ["MilestoneToolGroup"]
