"""
admin_ops — REST adapter for Disaster Recovery (REQ-L1-046).

Drives the ``/api/v1/admin/backups/`` and ``/api/v1/admin/restore/`` resources
from Welle D. The view delegates ALL business logic to the existing
:class:`BackupService` and :class:`AdminRestoreService` (REQ-L3-RA001-004 —
no business logic in views). It is a thin HTTP-translation layer:

* Maps HTTP methods to service calls.
* Translates service outcomes (return values, raised exceptions) to the
  standardised JSON shape + HTTP status codes required by the rest of
  the API.
* Enforces admin-only access via :class:`HasOperationPermission` with
  :attr:`Operation.WORKSPACE_CONFIG` (admin-only in the RBAC matrix).
* Validates the captcha confirmation text for ``restore`` BEFORE calling
  the service. The service enforces the same captcha as a backstop, but
  catching it at the REST layer lets the response return the clean
  ``400`` shape used by the rest of the API.

Endpoints:
    GET    /api/v1/admin/backups/
        Query: ?status=... &backup_type=... &limit=... [&offset=...]
        200: {"backups": [...]} on success
        400: validation error (bad limit / bad type)
        403: caller is not admin
    POST   /api/v1/admin/backups/
        Body: {"reason"?: str, "backup_type"?: "full" | "partial"}
        201: {"backup": {...}} on success
        400: validation error (unknown backup_type)
        403: caller is not admin
    POST   /api/v1/admin/restore/
        Body: {"backup_id": "<uuid>",
               "confirmation_text": "RESTORE",
               "restore_type"?: "full" | "partial"}
        200: {"restore": {...}} on success
        400: validation error (missing fields, bad UUID, captcha mismatch)
        403: caller is not admin
        404: backup does not exist or is not restorable

The view intentionally does NOT embed auditing logic — the services
write the ``AuditLogEntry`` rows. REST-audit is a concern of the service
layer, not the adapter.
"""
from __future__ import annotations

import logging
from typing import Any, Optional
from uuid import UUID

from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from admin_ops.models import BackupStatus, BackupType
from admin_ops.services import (
    AdminRestoreService,
    BackupNotFoundError,
    BackupService,
)
from admin_ops.services.admin_restore_service import RESTORE_CAPTCHA
from admin_ops.services.exceptions import BackupStorageError
from auth_tenancy.context import AuthContext
from auth_tenancy.rest import HasOperationPermission
from auth_tenancy.services import Operation
from application.base import (
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Allowed filter values exposed to clients for early validation
# ---------------------------------------------------------------------------

_VALID_BACKUP_STATUSES = frozenset(choice for choice, _label in BackupStatus.choices)
_VALID_BACKUP_TYPES = frozenset(choice for choice, _label in BackupType.choices)


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------


def _backup_to_dict(backup: Any) -> dict[str, Any]:
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


def _restore_result_to_dict(result: Any) -> dict[str, Any]:
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
# Error translation
# ---------------------------------------------------------------------------


def _err(code: str, message: str, http_status: int) -> Response:
    """Build a standardised error response body."""
    return Response(
        {"error": code, "message": message},
        status=http_status,
    )


# ---------------------------------------------------------------------------
# UUID / input parsing helpers
# ---------------------------------------------------------------------------


def _parse_uuid(value: Any, field: str) -> Optional[UUID]:
    """Parse *value* as a UUID; raise ValidationError on failure."""
    if value is None:
        return None
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        raise ValidationError(f"Field '{field}' is not a valid UUID: {value!r}")


def _parse_optional_str(value: Any, field: str, *, max_len: int = 512) -> Optional[str]:
    """Return *value* as a stripped string, or None if it is missing/empty."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValidationError(f"Field '{field}' must be a string.")
    stripped = value.strip()
    if not stripped:
        return None
    if len(stripped) > max_len:
        raise ValidationError(
            f"Field '{field}' exceeds maximum length of {max_len} characters."
        )
    return stripped


# ---------------------------------------------------------------------------
# BackupListCreateView
# ---------------------------------------------------------------------------


class BackupListCreateView(APIView):
    """REST adapter for BackupService (REQ-L1-046).

    URL: ``/api/v1/admin/backups/``

    Permissions:
        * :class:`HasOperationPermission` with ``Operation.WORKSPACE_CONFIG``
          — admin-only in the RBAC matrix; denies when no auth context is
          present (401/403) or the caller lacks the role. The service
          performs its own ``_assert_permission(ctx, "admin")`` as the final
          gate.

    Tenant scope:
        Implicit via the :class:`BackupService` which calls
        :meth:`ServiceBase._set_tenant_context`; queries use the plain
        (non-tenant-scoped) manager because :class:`BackupMetadata` is
        instance-level by design.
    """

    permission_classes = [HasOperationPermission]
    required_operation = Operation.WORKSPACE_CONFIG

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._service = BackupService()

    # -- helpers -----------------------------------------------------------

    @staticmethod
    def _auth_context(request: Request) -> AuthContext:
        """Return the request's auth context (set by BearerTokenAuthentication)."""
        ctx = getattr(request, "auth_context", None)
        if ctx is None:
            # Should be caught by HasOperationPermission, but be defensive.
            raise PermissionDeniedError("Authentication required.")
        return ctx

    # -- GET: list ---------------------------------------------------------

    def get(self, request: Request, **kwargs: Any) -> Response:
        """List backups (newest first).

        Query parameters (all optional):
            * ``status`` — filter by ``BackupStatus`` value.
            * ``backup_type`` — filter by ``BackupType`` value.
            * ``limit`` — cap the number of returned rows (1..1000, default 100).
            * ``offset`` — skip the first N rows (default 0).

        Returns 200 with ``{"backups": [...]}``.
        """
        # The service-level admin gate is the authoritative one; we still
        # let DRF's HasOperationPermission handle the 403 mapping.
        try:
            ctx = self._auth_context(request)
        except PermissionDeniedError as exc:
            return _err("PERMISSION_DENIED", str(exc), status.HTTP_403_FORBIDDEN)

        # Optional filters
        status_filter = request.query_params.get("status")
        if status_filter is not None and status_filter not in _VALID_BACKUP_STATUSES:
            return _err(
                "VALIDATION_ERROR",
                f"Query parameter 'status' must be one of {sorted(_VALID_BACKUP_STATUSES)}.",
                status.HTTP_400_BAD_REQUEST,
            )

        type_filter = request.query_params.get("backup_type")
        if type_filter is not None and type_filter not in _VALID_BACKUP_TYPES:
            return _err(
                "VALIDATION_ERROR",
                f"Query parameter 'backup_type' must be one of {sorted(_VALID_BACKUP_TYPES)}.",
                status.HTTP_400_BAD_REQUEST,
            )

        # limit / offset parsing
        try:
            limit = int(request.query_params.get("limit", 100))
        except (TypeError, ValueError):
            return _err(
                "VALIDATION_ERROR",
                "Query parameter 'limit' must be an integer.",
                status.HTTP_400_BAD_REQUEST,
            )
        try:
            offset = int(request.query_params.get("offset", 0))
        except (TypeError, ValueError):
            return _err(
                "VALIDATION_ERROR",
                "Query parameter 'offset' must be an integer.",
                status.HTTP_400_BAD_REQUEST,
            )

        try:
            rows = self._list_with_filters(
                ctx=ctx,
                status_filter=status_filter,
                backup_type=type_filter,
                limit=limit,
                offset=offset,
            )
        except PermissionDeniedError as exc:
            return _err("PERMISSION_DENIED", str(exc), status.HTTP_403_FORBIDDEN)
        except ValidationError as exc:
            return _err("VALIDATION_ERROR", str(exc), status.HTTP_400_BAD_REQUEST)
        except NotFoundError as exc:
            return _err("NOT_FOUND", str(exc), status.HTTP_404_NOT_FOUND)

        return Response(
            {"backups": [_backup_to_dict(r) for r in rows]},
            status=status.HTTP_200_OK,
        )

    def _list_with_filters(
        self,
        *,
        ctx: AuthContext,
        status_filter: Optional[str],
        backup_type: Optional[str],
        limit: int,
        offset: int,
    ):
        """List with optional in-process post-filters.

        The service exposes :meth:`list_backups` with no ``status`` /
        ``backup_type`` filter argument. The expected row counts are
        small in practice (admin overview), so we filter in-process to
        keep the service signature stable. Offset / limit are also
        applied in-process for symmetry — the result page is bounded
        by the service's own ``_LIST_LIMIT_CAP``.
        """
        # Fetch one window from the service. We always pull a window big
        # enough to satisfy ``limit`` after in-process filtering.
        fetch_limit = max(limit + offset, 100)
        rows = self._service.list_backups(ctx, limit=fetch_limit)
        if status_filter is not None:
            rows = [r for r in rows if r.status == status_filter]
        if backup_type is not None:
            rows = [r for r in rows if r.backup_type == backup_type]
        return rows[offset : offset + limit]

    # -- POST: create -------------------------------------------------------

    def post(self, request: Request, **kwargs: Any) -> Response:
        """Create a new backup (admin-only).

        Body (JSON object, both fields optional):
            * ``reason``     — free-form change-reason text (stored in metadata).
            * ``backup_type`` — ``"full"`` (default) or ``"partial"``.

        Returns 201 with ``{"backup": {...}}``.
        """
        try:
            ctx = self._auth_context(request)
        except PermissionDeniedError as exc:
            return _err("PERMISSION_DENIED", str(exc), status.HTTP_403_FORBIDDEN)

        data = request.data
        if not isinstance(data, dict):
            return _err(
                "VALIDATION_ERROR",
                "Request body must be a JSON object.",
                status.HTTP_400_BAD_REQUEST,
            )

        # reason → stored in metadata; non-breaking if missing.
        try:
            reason = _parse_optional_str(data.get("reason"), "reason")
        except ValidationError as exc:
            return _err("VALIDATION_ERROR", str(exc), status.HTTP_400_BAD_REQUEST)

        # backup_type: default "full"; validate against the model choices.
        backup_type_raw = data.get("backup_type")
        if backup_type_raw is None or backup_type_raw == "":
            backup_type: str = BackupType.FULL
        else:
            if (
                not isinstance(backup_type_raw, str)
                or backup_type_raw not in _VALID_BACKUP_TYPES
            ):
                return _err(
                    "VALIDATION_ERROR",
                    f"Field 'backup_type' must be one of {sorted(_VALID_BACKUP_TYPES)}.",
                    status.HTTP_400_BAD_REQUEST,
                )
            backup_type = backup_type_raw

        metadata = {}
        if reason:
            metadata["reason"] = reason

        try:
            row = self._service.create_backup(ctx, backup_type=backup_type, metadata=metadata)
        except PermissionDeniedError as exc:
            return _err("PERMISSION_DENIED", str(exc), status.HTTP_403_FORBIDDEN)
        except ValidationError as exc:
            return _err("VALIDATION_ERROR", str(exc), status.HTTP_400_BAD_REQUEST)
        except ValueError as exc:
            # BackupService raises ValueError for unknown backup_type as
            # a backstop; we already validate above, but stay defensive.
            return _err("VALIDATION_ERROR", str(exc), status.HTTP_400_BAD_REQUEST)
        except NotFoundError as exc:
            return _err("NOT_FOUND", str(exc), status.HTTP_404_NOT_FOUND)
        except BackupStorageError as exc:
            # GitHub #37: clean 500 with an actionable message instead of a
            # raw OSError ("Permission denied: /app/backups/") reaching the
            # client, or an unmapped exception producing a bare 500.
            return _err(
                "BACKUP_STORAGE_ERROR", str(exc), status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        return Response(
            {"backup": _backup_to_dict(row)},
            status=status.HTTP_201_CREATED,
        )


# ---------------------------------------------------------------------------
# AdminRestoreView
# ---------------------------------------------------------------------------


class AdminRestoreView(APIView):
    """REST adapter for AdminRestoreService (REQ-L1-046).

    URL: ``/api/v1/admin/restore/``

    Permissions:
        * :class:`HasOperationPermission` with ``Operation.WORKSPACE_CONFIG``
          — admin-only in the RBAC matrix; denies when no auth context is
          present (401/403) or the caller lacks the role. The service
          performs its own ``_assert_permission(ctx, "admin")`` as the final
          gate.

    Captcha:
        * ``confirmation_text`` MUST equal the literal ``"RESTORE"`` —
          case-sensitive, no trailing whitespace. The check is performed
          BOTH here (so the REST response shape is a clean 400) and
          inside the service (defence in depth).
    """

    permission_classes = [HasOperationPermission]
    required_operation = Operation.WORKSPACE_CONFIG

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._service = AdminRestoreService()

    # -- helpers -----------------------------------------------------------

    @staticmethod
    def _auth_context(request: Request) -> AuthContext:
        """Return the request's auth context."""
        ctx = getattr(request, "auth_context", None)
        if ctx is None:
            raise PermissionDeniedError("Authentication required.")
        return ctx

    # -- POST: restore ------------------------------------------------------

    def post(self, request: Request, **kwargs: Any) -> Response:
        """Restore from a backup (admin-only, captcha-gated).

        Body:
            {
              "backup_id": "<uuid>",
              "confirmation_text": "RESTORE",
              "restore_type"?: "full" | "partial"  (advisory only; service is full)
            }

        Returns 200 with ``{"restore": {...}}`` on success.
        """
        try:
            ctx = self._auth_context(request)
        except PermissionDeniedError as exc:
            return _err("PERMISSION_DENIED", str(exc), status.HTTP_403_FORBIDDEN)

        data = request.data
        if not isinstance(data, dict):
            return _err(
                "VALIDATION_ERROR",
                "Request body must be a JSON object.",
                status.HTTP_400_BAD_REQUEST,
            )

        # backup_id (required, UUID)
        try:
            backup_id = _parse_uuid(data.get("backup_id"), "backup_id")
        except ValidationError as exc:
            return _err("VALIDATION_ERROR", str(exc), status.HTTP_400_BAD_REQUEST)
        if backup_id is None:
            return _err(
                "VALIDATION_ERROR",
                "Field 'backup_id' is required.",
                status.HTTP_400_BAD_REQUEST,
            )

        # confirmation_text (required, exact match against RESTORE_CAPTCHA)
        confirmation_text = data.get("confirmation_text")
        if not isinstance(confirmation_text, str) or not confirmation_text:
            return _err(
                "VALIDATION_ERROR",
                "Field 'confirmation_text' is required.",
                status.HTTP_400_BAD_REQUEST,
            )
        if confirmation_text != RESTORE_CAPTCHA:
            # Captcha mismatch — explicit 400 so clients can present a
            # clear re-confirmation prompt. The service would also
            # raise ValidationError with "Captcha mismatch" but we want
            # the REST shape to match the rest of the API.
            return _err(
                "VALIDATION_ERROR",
                "Captcha mismatch: confirmation_text must equal 'RESTORE'.",
                status.HTTP_400_BAD_REQUEST,
            )

        # restore_type is accepted for forward-compatibility (the service
        # itself runs a full restore). We validate against the type
        # choices but do not pass it to the service yet.
        restore_type_raw = data.get("restore_type")
        if restore_type_raw is not None and restore_type_raw != "":
            if (
                not isinstance(restore_type_raw, str)
                or restore_type_raw not in _VALID_BACKUP_TYPES
            ):
                return _err(
                    "VALIDATION_ERROR",
                    f"Field 'restore_type' must be one of {sorted(_VALID_BACKUP_TYPES)}.",
                    status.HTTP_400_BAD_REQUEST,
                )

        try:
            result = self._service.restore(
                ctx,
                backup_id=backup_id,  # type: ignore[arg-type]
                confirmation_text=confirmation_text,
            )
        except PermissionDeniedError as exc:
            return _err("PERMISSION_DENIED", str(exc), status.HTTP_403_FORBIDDEN)
        except ValidationError as exc:
            return _err("VALIDATION_ERROR", str(exc), status.HTTP_400_BAD_REQUEST)
        except BackupNotFoundError as exc:
            return _err("NOT_FOUND", str(exc), status.HTTP_404_NOT_FOUND)
        except NotFoundError as exc:
            return _err("NOT_FOUND", str(exc), status.HTTP_404_NOT_FOUND)
        except FileNotFoundError as exc:
            # The data file referenced by the row is missing on disk.
            return _err("NOT_FOUND", str(exc), status.HTTP_404_NOT_FOUND)

        return Response(
            {"restore": _restore_result_to_dict(result)},
            status=status.HTTP_200_OK,
        )


__all__ = ["BackupListCreateView", "AdminRestoreView"]
