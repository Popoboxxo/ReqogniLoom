"""MCP tool group for saved table views (``saved_view.*``).

Slice 3 of ``docs/superpowers/plans/2026-11-04-tabellenansicht-neu.md``
(Task 3.4). The MCP counterpart of ``rest_api.saved_view_views`` and deliberately
**read-only**: agents discover the views a workspace offers and apply one, they
do not create or edit them (the plan calls for exactly these two tools; the
write path is a UI act whose owner is a human).

  saved_view.list   — own views plus the workspace-wide views of others (read)
  saved_view.apply  — run a stored view, return the paginated rows (read)

Two properties are load-bearing:

* **Both are reads.** ``saved_view.list``/``saved_view.apply`` are listed in
  ``tool_registry._READ_ONLY_TOOL_NAMES``; a read-only API key may call them and
  nothing is persisted (applying a view runs a SELECT).
* **The workspace is a fence, not a hint.** ``saved_view.apply`` requires
  ``workspace_id`` because that is what the dispatcher scopes the caller's roles
  to. A view that lives in a *different* workspace than the one the call names
  answers ``NOT_FOUND`` — otherwise the roles resolved for workspace A would
  authorise reading a view of workspace B. The check is explicit in the handler
  because the service answers object-derived facts only.

No ORM access here (ADR-01): every call goes through
:class:`application.saved_view_service.SavedViewService`. Payloads are JSON
primitives only (``str()`` UUIDs, ``.isoformat()``).
"""
from __future__ import annotations

from typing import Any

from application.base import NotFoundError, OptimisticLockError, ValidationError
from application.saved_view_service import SavedViewService
from auth_tenancy.context import AuthContext
from mcp_server.protocol_handler import ToolResult
from mcp_server.tools.base import (
    BaseToolGroup,
    reject_unknown_params,
    require_uuid,
)
from persistence.errors import PermissionDeniedError

#: Default/maximum page size of ``saved_view.apply`` (mirrors StandardPagination).
DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 100


def _service_error(exc: Exception) -> ToolResult:
    """Map a service exception to the MCP error vocabulary used elsewhere."""
    if isinstance(exc, NotFoundError):
        return ToolResult.error("NOT_FOUND", str(exc))
    if isinstance(exc, PermissionDeniedError):
        return ToolResult.error("PERMISSION_DENIED", str(exc))
    if isinstance(exc, OptimisticLockError):
        return ToolResult.error("CONFLICT", str(exc))
    if isinstance(exc, ValidationError):
        code = getattr(exc, "error_code", None) or "VALIDATION_ERROR"
        return ToolResult.error(code, str(exc))
    return ToolResult.error("INTERNAL_ERROR", "An internal error occurred.")


def _positive_int(params: dict[str, Any], name: str, default: int) -> int:
    """Return a validated positive integer parameter (''/None -> *default*)."""
    raw = params.get(name)
    if raw is None or raw == "":
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"'{name}' must be an integer") from exc
    if value < 1:
        raise ValidationError(f"'{name}' must be >= 1")
    return value


class SavedViewToolGroup(BaseToolGroup):
    """MCP tool group for the ``saved_view.*`` namespace (slice 3)."""

    _TOOL_MAP = {
        "saved_view.list": "_handle_list",
        "saved_view.apply": "_handle_apply",
    }

    _TOOL_SCHEMAS = [
        {
            "name": "saved_view.list",
            "description": (
                "List the saved table views a workspace offers: the caller's own "
                "views plus every workspace-wide view of other users. A private "
                "view of another user is never listed (read-only)."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace_id": {
                        "type": "string",
                        "description": "Required. UUID of the workspace.",
                    },
                    "item_type": {
                        "type": "string",
                        "description": (
                            "Optional. Restrict to one artifact type, e.g. "
                            "'Requirement'."
                        ),
                    },
                },
                "required": ["workspace_id"],
            },
        },
        {
            "name": "saved_view.apply",
            "description": (
                "Run a saved table view and return its rows (read-only): "
                "{results: [{id, artifact_id, item_type, version, values, "
                "locked}], count, page, page_size, warnings}. The stored filter "
                "DSL is applied server-side; if it no longer compiles (attribute "
                "removed) the answer is an empty []result plus a warnings entry, "
                "never an error."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "view_id": {
                        "type": "string",
                        "description": "Required. UUID of the saved view.",
                    },
                    "workspace_id": {
                        "type": "string",
                        "description": (
                            "Required. UUID of the workspace the view belongs to; "
                            "a view of another workspace answers NOT_FOUND."
                        ),
                    },
                    "page": {
                        "type": "integer",
                        "description": "Optional. 1-based page number (default 1).",
                    },
                    "page_size": {
                        "type": "integer",
                        "description": (
                            "Optional. Rows per page (default 50, maximum 100)."
                        ),
                    },
                },
                "required": ["view_id", "workspace_id"],
            },
        },
    ]

    def _svc(self) -> SavedViewService:
        return SavedViewService()

    # ---------- Handlers ----------

    def _handle_list(
        self, *, params: dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        try:
            reject_unknown_params(
                params, ["workspace_id", "item_type"], "saved_view.list"
            )
            workspace_id = require_uuid(params, "workspace_id")
            item_type = params.get("item_type") or None
            views = self._svc().list(auth_context, workspace_id, item_type)
        except ValueError as exc:
            # ``ParameterError`` (unknown/missing/malformed parameter) and the
            # service's ``ValidationError`` are both ``ValueError`` subclasses.
            return ToolResult.error("VALIDATION_ERROR", str(exc))
        except PermissionDeniedError as exc:  # pragma: no cover - read path
            return _service_error(exc)
        except NotFoundError as exc:
            return _service_error(exc)
        except Exception:  # noqa: BLE001 — masked, logged server-side
            return ToolResult.error("INTERNAL_ERROR", "An internal error occurred.")
        return ToolResult.ok(
            {
                "views": [view.as_payload() for view in views],
                "count": len(views),
            }
        )

    def _handle_apply(
        self, *, params: dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        try:
            reject_unknown_params(
                params,
                ["view_id", "workspace_id", "page", "page_size"],
                "saved_view.apply",
            )
            view_id = require_uuid(params, "view_id")
            workspace_id = require_uuid(params, "workspace_id")
            page = _positive_int(params, "page", 1)
            page_size = min(_positive_int(params, "page_size", DEFAULT_PAGE_SIZE), MAX_PAGE_SIZE)
            result = self._svc().apply(auth_context, view_id)
        except ValueError as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))
        except PermissionDeniedError as exc:  # pragma: no cover - read path
            return _service_error(exc)
        except NotFoundError as exc:
            return _service_error(exc)
        except Exception:  # noqa: BLE001 — masked, logged server-side
            return ToolResult.error("INTERNAL_ERROR", "An internal error occurred.")

        # The workspace parameter is the authorization fence. A view living in
        # another workspace answers exactly like a missing one (no existence
        # leak, and no cross-workspace read through roles resolved for A).
        if str(result.view.workspace_id) != str(workspace_id):
            return ToolResult.error(
                "NOT_FOUND", f"Saved view {view_id} not found"
            )

        offset = (page - 1) * page_size
        rows = result.rows[offset : offset + page_size]
        return ToolResult.ok(
            {
                "results": rows,
                "count": len(result.rows),
                "page": page,
                "page_size": page_size,
                "warnings": result.warnings,
            }
        )
