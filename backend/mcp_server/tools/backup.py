"""
COMP-MC-009 BackupToolGroup — 3 DR MCP tools under ``admin.*`` (REQ-L1-046).

leaf_id : COMP-MC-009
req_id  : REQ-L1-046 (Disaster Recovery),
          REQ-L2-MC-009 (direct ApplicationService access),
          REQ-L2-MC-012 (MCP audit trail)

Tools implemented (admin-only; create + restore are write, list is read):

  admin.backup_create   (write)  — create a new backup
  admin.backup_list     (read)   — list backups (newest first)
  admin.restore         (write)  — restore from a backup (captcha "RESTORE")

Architecture:

* The ``admin.*`` namespace is owned by this group; ``workspace.*`` stays
  under :class:`AdminToolGroup` (REQ-L1-042). Both are registered with
  different prefixes in ``tool_registry._ensure_groups()``.
* All three handlers delegate to the existing :class:`BackupService` and
  :class:`AdminRestoreService` (the same services the REST adapter uses)
  and never duplicate the business logic (transaction wrapping, audit
  hooks, captcha check, file I/O). The MCP wrapper adds parameter
  validation, error mapping and the MCP-specific audit entry on write
  tools.
* ``admin.backup_create`` and ``admin.restore`` are added to
  ``_WRITE_TOOL_PREFIXES`` in ``tool_registry`` so the RBAC layer treats
  them as writes; ``admin.backup_list`` is read-only.

Error mapping (REQ-L2-MC-011):
  BackupNotFoundError / NotFoundError -> NOT_FOUND
  PermissionDeniedError               -> PERMISSION_DENIED
  ValidationError / ValueError /
      ParameterError                   -> VALIDATION_ERROR
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from auth_tenancy.context import AuthContext

from admin_ops.models import BackupStatus, BackupType
from admin_ops.services import (
    AdminRestoreService,
    BackupService,
)
from admin_ops.services.admin_restore_service import RESTORE_CAPTCHA
from admin_ops.services.exceptions import BackupNotFoundError

from application.base import (
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)

from mcp_server.protocol_handler import ToolResult
from mcp_server.tools.base import (
    BaseToolGroup,
    ParameterError,
    require_param,
    require_uuid,
    write_mcp_audit,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Allowed filter values (mirror of REST adapter / model choices)
# ---------------------------------------------------------------------------

_VALID_STATUSES = frozenset(choice for choice, _label in BackupStatus.choices)
_VALID_TYPES = frozenset(choice for choice, _label in BackupType.choices)


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------


def _backup_to_dict(backup: Any) -> Dict[str, Any]:
    """Serialise a BackupMetadata row to a JSON-safe dict."""
    return {
        "id": str(backup.id),
        "status": backup.status,
        "backup_type": backup.backup_type,
        "file_path": backup.file_path,
        "file_size_bytes": backup.file_size_bytes,
        "checksum_sha256": backup.checksum_sha256,
        "error_message": backup.error_message or "",
        "metadata": backup.metadata or {},
        "completed_at": (
            backup.completed_at.isoformat()
            if getattr(backup, "completed_at", None) is not None
            else None
        ),
        "is_restorable": bool(getattr(backup, "is_restorable", False)),
        "created_at": (
            backup.created_at.isoformat()
            if getattr(backup, "created_at", None) is not None
            else None
        ),
        "created_by": (
            str(backup.created_by_id)
            if getattr(backup, "created_by_id", None) is not None
            else None
        ),
    }


def _restore_result_to_dict(result: Any) -> Dict[str, Any]:
    """Serialise a RestoreResult to a JSON-safe dict."""
    return {
        "backup_id": str(result.backup_id),
        "started_at": (
            result.started_at.isoformat()
            if getattr(result, "started_at", None) is not None
            else None
        ),
        "completed_at": (
            result.completed_at.isoformat()
            if getattr(result, "completed_at", None) is not None
            else None
        ),
        "restored_tables": list(getattr(result, "restored_tables", []) or []),
        "rows_per_table": dict(getattr(result, "rows_per_table", {}) or {}),
    }


# ---------------------------------------------------------------------------
# BackupToolGroup
# ---------------------------------------------------------------------------


class BackupToolGroup(BaseToolGroup):
    """COMP-MC-009 — Disaster Recovery MCP tool group (3 tools, admin.*)."""

    _TOOL_MAP = {
        "admin.backup_create": "_handle_backup_create",
        "admin.backup_list": "_handle_backup_list",
        "admin.restore": "_handle_restore",
    }

    _TOOL_SCHEMAS = [
        {
            "name": "admin.backup_create",
            "description": "Create a new backup (admin-only, write, audited).",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "reason": {"type": "string", "description": "Optional free-form change reason."},
                    "backup_type": {
                        "type": "string",
                        "description": "Backup type ('full' default or 'partial').",
                    },
                },
            },
        },
        {
            "name": "admin.backup_list",
            "description": "List backups newest-first (admin-only, read).",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "status": {"type": "string", "description": "Optional BackupStatus filter."},
                    "backup_type": {"type": "string", "description": "Optional BackupType filter."},
                    "limit": {"type": "integer", "description": "Page size (1..1000, default 100)."},
                    "offset": {"type": "integer", "description": "Rows to skip (default 0)."},
                },
            },
        },
        {
            "name": "admin.restore",
            "description": "Restore from a backup with captcha 'RESTORE' (admin-only, write, audited).",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "backup_id": {"type": "string", "description": "UUID of the backup to restore."},
                    "confirmation_text": {
                        "type": "string",
                        "description": "Must equal the literal 'RESTORE' (case-sensitive captcha).",
                    },
                    "restore_type": {
                        "type": "string",
                        "description": "Advisory restore type ('full' default or 'partial').",
                    },
                },
                "required": ["backup_id", "confirmation_text"],
            },
        },
    ]

    def __init__(
        self,
        backup_service: Optional[BackupService] = None,
        restore_service: Optional[AdminRestoreService] = None,
    ) -> None:
        self._backup_service = backup_service or BackupService()
        self._restore_service = restore_service or AdminRestoreService()

    # ------------------------------------------------------------------
    # admin.backup_create (write)
    # ------------------------------------------------------------------

    def _handle_backup_create(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """admin.backup_create — create a new backup (REQ-L1-046).

        Optional params:
            reason       — free-form change-reason text (stored in metadata).
            backup_type  — ``"full"`` (default) or ``"partial"``.
        """
        # Optional parameters
        reason_raw = params.get("reason")
        reason: Optional[str] = None
        if reason_raw is not None:
            if not isinstance(reason_raw, str):
                raise ParameterError(
                    "Optional parameter 'reason' must be a string."
                )
            reason = reason_raw.strip() or None

        backup_type_raw = params.get("backup_type")
        if backup_type_raw is None or backup_type_raw == "":
            backup_type: str = BackupType.FULL
        elif isinstance(backup_type_raw, str) and backup_type_raw in _VALID_TYPES:
            backup_type = backup_type_raw
        else:
            return ToolResult.error(
                "VALIDATION_ERROR",
                f"Optional parameter 'backup_type' must be one of {sorted(_VALID_TYPES)}.",
            )

        metadata: Dict[str, Any] = {}
        if reason:
            metadata["reason"] = reason

        try:
            row = self._backup_service.create_backup(
                auth_context,
                backup_type=backup_type,
                metadata=metadata,
            )
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        except (ValidationError, ValueError) as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))

        write_mcp_audit(
            ctx=auth_context,
            operation="admin.backup_create",
            entity_type="BackupMetadata",
            entity_id=row.id,
            tool_name="admin.backup_create",
            api_key=api_key,
            details={
                "backup_type": backup_type,
                "reason": reason,
                "file_size_bytes": row.file_size_bytes,
            },
        )
        return ToolResult.ok({"backup": _backup_to_dict(row)})

    # ------------------------------------------------------------------
    # admin.backup_list (read)
    # ------------------------------------------------------------------

    def _handle_backup_list(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """admin.backup_list — list backups (newest first, REQ-L1-046).

        Optional params:
            status       — filter by ``BackupStatus`` value.
            backup_type  — filter by ``BackupType`` value.
            limit        — cap the number of returned rows (1..1000, default 100).
            offset       — skip the first N rows (default 0).
        """
        # Optional filters — validate against model choices, applied
        # in-process (the service signature does not expose them).
        status_filter = params.get("status")
        if status_filter is not None and status_filter != "":
            if status_filter not in _VALID_STATUSES:
                return ToolResult.error(
                    "VALIDATION_ERROR",
                    f"Optional parameter 'status' must be one of {sorted(_VALID_STATUSES)}.",
                )
        else:
            status_filter = None

        type_filter = params.get("backup_type")
        if type_filter is not None and type_filter != "":
            if type_filter not in _VALID_TYPES:
                return ToolResult.error(
                    "VALIDATION_ERROR",
                    f"Optional parameter 'backup_type' must be one of {sorted(_VALID_TYPES)}.",
                )
        else:
            type_filter = None

        # limit / offset parsing
        limit_raw = params.get("limit", 100)
        offset_raw = params.get("offset", 0)
        try:
            limit = int(limit_raw)
        except (TypeError, ValueError):
            return ToolResult.error(
                "VALIDATION_ERROR",
                "Optional parameter 'limit' must be an integer.",
            )
        try:
            offset = int(offset_raw)
        except (TypeError, ValueError):
            return ToolResult.error(
                "VALIDATION_ERROR",
                "Optional parameter 'offset' must be an integer.",
            )
        if limit < 1:
            return ToolResult.error(
                "VALIDATION_ERROR",
                "Optional parameter 'limit' must be >= 1.",
            )
        if offset < 0:
            return ToolResult.error(
                "VALIDATION_ERROR",
                "Optional parameter 'offset' must be >= 0.",
            )

        try:
            fetch_limit = max(limit + offset, 100)
            rows = self._backup_service.list_backups(
                auth_context, limit=fetch_limit
            )
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        except (ValidationError, ValueError) as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))

        if status_filter is not None:
            rows = [r for r in rows if r.status == status_filter]
        if type_filter is not None:
            rows = [r for r in rows if r.backup_type == type_filter]
        rows = rows[offset : offset + limit]

        return ToolResult.ok(
            {"backups": [_backup_to_dict(r) for r in rows]}
        )

    # ------------------------------------------------------------------
    # admin.restore (write, captcha-gated)
    # ------------------------------------------------------------------

    def _handle_restore(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """admin.restore — restore from a backup (REQ-L1-046, captcha-gated).

        Required params:
            backup_id          — UUID of the :class:`BackupMetadata` to restore.
            confirmation_text  — MUST equal the literal ``"RESTORE"`` (case-sensitive).

        Optional:
            restore_type       — ``"full"`` (default) or ``"partial"``;
                                 currently advisory only (the service
                                 runs a full restore).
        """
        backup_id = require_uuid(params, "backup_id")

        # require_param raises ParameterError if missing/empty; the
        # BaseToolGroup dispatcher converts ParameterError to
        # VALIDATION_ERROR (matches the rest of the MCP surface).
        confirmation_text = require_param(params, "confirmation_text")
        if not isinstance(confirmation_text, str):
            return ToolResult.error(
                "VALIDATION_ERROR",
                "Required parameter 'confirmation_text' must be a string.",
            )
        # Explicit captcha check at the MCP boundary so the error
        # response is a clean VALIDATION_ERROR with a clear message.
        # The service would also raise ValidationError("Captcha mismatch")
        # as defence in depth.
        if confirmation_text != RESTORE_CAPTCHA:
            return ToolResult.error(
                "VALIDATION_ERROR",
                "Captcha mismatch: confirmation_text must equal 'RESTORE'.",
            )

        restore_type_raw = params.get("restore_type")
        if restore_type_raw is not None and restore_type_raw != "":
            if (
                not isinstance(restore_type_raw, str)
                or restore_type_raw not in _VALID_TYPES
            ):
                return ToolResult.error(
                    "VALIDATION_ERROR",
                    f"Optional parameter 'restore_type' must be one of {sorted(_VALID_TYPES)}.",
                )

        try:
            result = self._restore_service.restore(
                auth_context,
                backup_id=backup_id,
                confirmation_text=confirmation_text,
            )
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        except (ValidationError, ValueError) as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))
        except BackupNotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except FileNotFoundError as exc:
            # Data file referenced by the row is missing on disk.
            return ToolResult.error("NOT_FOUND", str(exc))

        write_mcp_audit(
            ctx=auth_context,
            operation="admin.restore",
            entity_type="BackupRestore",
            entity_id=backup_id,
            tool_name="admin.restore",
            api_key=api_key,
            details={
                "backup_id": str(backup_id),
                "duration_seconds": (
                    (result.completed_at - result.started_at).total_seconds()
                    if getattr(result, "started_at", None) is not None
                    and getattr(result, "completed_at", None) is not None
                    else None
                ),
            },
        )
        return ToolResult.ok({"restore": _restore_result_to_dict(result)})


__all__ = ["BackupToolGroup"]
