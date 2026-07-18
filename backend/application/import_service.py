"""
COMP-AS-009 ImportService — Atomic CSV bulk import.

leaf_id : COMP-AS-009
req_id  : REQ-L1-021, REQ-L2-AppSvc-014, REQ-L3-IMP-001, REQ-L3-IMP-002,
          REQ-L3-IMP-003, REQ-L3-IMP-004

Imports StakeholderNeeds, Requirements, ArchitectureElements, TestCases (persistence
app) and Adrs, Risks, Issues (application app) from CSV. Validates every row
(RFC 4180, required fields, type checks) and writes all valid rows in a single
transaction (all-or-nothing, REQ-L3-IMP-002). Supports up to 1000 rows per call.

Round-trip fidelity (COMP-AS-008 → COMP-AS-009): when a row carries the
identity/audit columns emitted by ExportService (id, artifact_id, version,
created_at and the model's modified timestamp), those values are preserved so an
``export -> import`` cycle reproduces the original record exactly — the safety
net for the ReqFlow self-migration. The field set is driven by the shared
``application.export_service.ENTITY_FIELD_SPECS`` registry.

Interface contracts implemented:
  IF-AS-EXT-IN-001  — inbound: import_csv(csv_text, entity_type, workspace_id, ctx)
  IF-AS-EXT-OUT-007 — outbound: persistence ORM (Artifact + entity creates)
  IF-AS-EXT-OUT-006 — outbound: DomainEventBus (batch import event)

Architecture:
  docs/se/L1/Gesamtsystem/L2/ApplicationServiceSystem/Components/
    COMP-AS-009_ImportService/
"""
from __future__ import annotations

import csv
import io
import json
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from auth_tenancy.context import AuthContext
from django.db import transaction
from django.utils.dateparse import parse_datetime

# Backward-compat alias used by tests that patch 'application.import_service.TenantContext'
TenantContext = AuthContext

from application.base import NotFoundError, ServiceBase, ValidationError
from application.export_service import (
    ENTITY_FIELD_SPECS,
    _APP_ENTITY_TYPES,
    _PERSISTENCE_ENTITY_TYPES,
)

logger = logging.getLogger(__name__)

# Maximum rows in a single import call (REQ-L3-IMP-003)
_MAX_ROWS = 1000

# Required fields per entity type (REQ-L3-IMP-001). Derived from the shared
# round-trip field registry so importer and exporter cannot drift apart; every
# supported entity requires a non-empty ``title``.
_REQUIRED_FIELDS: Dict[str, List[str]] = {
    entity_type: ["title"] for entity_type in ENTITY_FIELD_SPECS
}

# Valid entity types
_VALID_ENTITY_TYPES = set(_REQUIRED_FIELDS.keys())

# Identity / audit columns handled specially by _insert_rows (not passed through
# as plain content create kwargs).
_IDENTITY_COLUMNS = frozenset(
    {"id", "artifact_id", "version", "created_at", "modified_at", "updated_at", "created_by"}
)


def _import_value(cell: Any, kind: str) -> Any:
    """Deserialise a single CSV *cell* string to its typed value per *kind*.

    Inverse of :func:`application.export_service._csv_cell` /
    :func:`~application.export_service._export_value`. Empty cells become ``None``
    (text/int/uuid/datetime), ``False`` (bool) or ``[]`` (json) so that absent
    values fall back to the model default on create.
    """
    text = "" if cell is None else str(cell)
    stripped = text.strip()
    if kind in ("str", "nstr"):
        # Preserve exact (unstripped) content when present; empty -> None so the
        # model default applies on create.
        return text if stripped else None
    if kind == "int":
        return int(stripped) if stripped else None
    if kind == "bool":
        return stripped.lower() in ("true", "1", "yes")
    if kind == "json":
        if not stripped:
            return []
        try:
            return json.loads(stripped)
        except (ValueError, TypeError):
            # Legacy / non-JSON payload: wrap the raw value so nothing is dropped.
            return [stripped]
    if kind == "datetime":
        return parse_datetime(stripped) if stripped else None
    if kind == "uuid":
        return UUID(stripped) if stripped else None
    return text


# ---------- DTOs ----------


@dataclass
class ImportRowError:
    """Validation error for a single CSV row."""

    row_number: int
    field: str
    message: str


@dataclass
class ImportResult:
    """Result of a CSV import operation.

    Attributes:
        success: True if all valid rows were persisted.
        imported_count: Number of rows persisted.
        skipped_count: Number of rows that failed validation.
        errors: Per-row error list (empty on full success).
        status: "ok" | "validation_error" | "rollback"
    """

    success: bool
    imported_count: int
    skipped_count: int
    errors: List[ImportRowError] = field(default_factory=list)
    status: str = "ok"


# ---------- Service ----------


class ImportService(ServiceBase):
    """Atomic CSV bulk import for domain entities.

    COMP-AS-009. REQ-L3-IMP-001 (parsing), REQ-L3-IMP-002 (atomicity),
    REQ-L3-IMP-003 (1000-row limit), REQ-L3-IMP-004 (audit).

    Usage::

        svc = ImportService()
        result = svc.import_csv(
            csv_text=file_content,
            entity_type="Requirement",
            workspace_id=ws_uuid,
            ctx=auth_ctx,
        )
        if not result.success:
            print(result.errors)
    """

    def import_csv(
        self,
        csv_text: str,
        entity_type: str,
        workspace_id: UUID | str,
        ctx: AuthContext,
        artifact_type_tag: str = "",
    ) -> ImportResult:
        """Parse, validate, and atomically persist CSV rows.

        REQ-L3-IMP-001: validation with full error report.
        REQ-L3-IMP-002: single transaction.atomic() for all inserts.
        REQ-L3-IMP-003: max 1000 rows enforced before any DB write.

        Args:
            csv_text: Raw CSV content string (RFC 4180).
            entity_type: "Requirement" | "ArchitectureElement" | "TestCase"
            workspace_id: Target workspace UUID.
            ctx: AuthContext for tenant scoping and audit.
            artifact_type_tag: Optional artifact_type tag string.

        Returns:
            ImportResult with success flag, counts, and per-row errors.

        Raises:
            ValidationError: entity_type invalid or row count exceeds limit.
        """
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)

        if entity_type not in _VALID_ENTITY_TYPES:
            raise ValidationError(
                f"Unsupported entity_type '{entity_type}'. "
                f"Allowed: {sorted(_VALID_ENTITY_TYPES)}"
            )

        ws_uuid = UUID(str(workspace_id))

        # ---------- Parse CSV (RFC 4180) ----------
        rows, parse_errors = self._parse_csv(csv_text)

        if parse_errors:
            return ImportResult(
                success=False,
                imported_count=0,
                skipped_count=len(rows),
                errors=parse_errors,
                status="validation_error",
            )

        if len(rows) > _MAX_ROWS:
            raise ValidationError(
                f"CSV exceeds maximum row limit of {_MAX_ROWS} "
                f"(got {len(rows)} data rows)."
            )

        # ---------- Validate all rows, collect full error report ----------
        validation_errors: List[ImportRowError] = []
        for row_num, row in rows:
            errs = self._validate_row(row_num, row, entity_type)
            validation_errors.extend(errs)

        if validation_errors:
            return ImportResult(
                success=False,
                imported_count=0,
                skipped_count=len(rows),
                errors=validation_errors,
                status="validation_error",
            )

        # ---------- Atomic insert of all valid rows ----------
        try:
            with transaction.atomic():
                imported = self._insert_rows(
                    rows=rows,
                    entity_type=entity_type,
                    workspace_id=ws_uuid,
                    ctx=ctx,
                    artifact_type_tag=artifact_type_tag or entity_type,
                )

                # REQ-L3-IMP-004: batch audit event
                self._audit(
                    ctx=ctx,
                    operation="create",
                    entity_type=entity_type,
                    entity_id=ws_uuid,  # workspace as aggregate entity_id for batch
                    details={
                        "workspace_id": str(ws_uuid),
                        "imported_count": imported,
                        "operation_type": "bulk_import",
                    },
                )

        except Exception:
            logger.exception(
                "ImportService: DB error during atomic insert, rolling back. "
                "entity_type=%s workspace_id=%s",
                entity_type,
                ws_uuid,
            )
            return ImportResult(
                success=False,
                imported_count=0,
                skipped_count=len(rows),
                errors=[],
                status="rollback",
            )

        return ImportResult(
            success=True,
            imported_count=imported,
            skipped_count=0,
            errors=[],
            status="ok",
        )

    # ---------- Private helpers ----------

    @staticmethod
    def _parse_csv(
        csv_text: str,
    ) -> Tuple[List[Tuple[int, Dict[str, str]]], List[ImportRowError]]:
        """Parse CSV text into (row_number, dict) tuples.

        Skips comment lines starting with '#'.
        Returns (rows, errors).
        """
        errors: List[ImportRowError] = []
        rows: List[Tuple[int, Dict[str, str]]] = []

        # Strip comment lines (e.g. terminology header from ExportService)
        clean_lines = [
            line for line in csv_text.splitlines() if not line.startswith("#")
        ]
        clean_text = "\n".join(clean_lines)

        try:
            reader = csv.DictReader(io.StringIO(clean_text))
            for line_num, row in enumerate(reader, start=2):  # 2 = header is line 1
                rows.append((line_num, dict(row)))
        except csv.Error as exc:
            errors.append(
                ImportRowError(row_number=0, field="csv", message=f"CSV parse error: {exc}")
            )

        return rows, errors

    @staticmethod
    def _validate_row(
        row_number: int,
        row: Dict[str, str],
        entity_type: str,
    ) -> List[ImportRowError]:
        """Validate a single row. Returns list of errors (empty = valid)."""
        errors: List[ImportRowError] = []
        required = _REQUIRED_FIELDS.get(entity_type, [])

        for field_name in required:
            value = row.get(field_name, "").strip()
            if not value:
                errors.append(
                    ImportRowError(
                        row_number=row_number,
                        field=field_name,
                        message=f"Required field '{field_name}' is missing or empty.",
                    )
                )

        # Length constraints
        title = row.get("title", "")
        if len(title) > 500:
            errors.append(
                ImportRowError(
                    row_number=row_number,
                    field="title",
                    message=f"'title' must not exceed 500 characters (got {len(title)}).",
                )
            )

        return errors

    @staticmethod
    def _insert_rows(
        rows: List[Tuple[int, Dict[str, str]]],
        entity_type: str,
        workspace_id: UUID,
        ctx: AuthContext,
        artifact_type_tag: str,
    ) -> int:
        """Insert all rows as Artifact + entity pairs. Must run inside atomic().

        IF-AS-EXT-OUT-007: persistence / application ORM writes.

        Round-trip fidelity (COMP-AS-008 → COMP-AS-009): when a row carries the
        identity/audit columns produced by :class:`~application.export_service.ExportService`
        (``id``, ``artifact_id``, ``version``, ``created_at`` and the model's
        modified timestamp), those values are preserved so ``export -> import``
        reproduces the original record exactly. Rows without those columns (e.g.
        a hand-authored CSV) keep the previous behaviour: fresh UUIDs, version 1
        and current timestamps.

        ``auto_now`` / ``auto_now_add`` on ``created_at``/``modified_at``/
        ``updated_at`` are bypassed with a follow-up ``QuerySet.update()`` (which
        does not touch auto timestamps), the only way to write caller-supplied
        audit timestamps.

        Supported entity types: StakeholderNeed, Requirement, ArchitectureElement,
        TestCase (persistence app) and Adr, Risk, Issue (application app).

        Returns count of inserted rows.
        """
        from persistence.models import (
            ArchitectureElement,
            Artifact,
            Requirement,
            StakeholderNeed,
            TestCase,
            Workspace,
        )
        from application.models import Adr, Issue, Risk

        persistence_models = {
            "StakeholderNeed": StakeholderNeed,
            "Requirement": Requirement,
            "ArchitectureElement": ArchitectureElement,
            "TestCase": TestCase,
        }
        app_models = {"Adr": Adr, "Risk": Risk, "Issue": Issue}

        workspace = Workspace.objects.get(id=workspace_id)
        tenant = workspace.tenant
        spec = ENTITY_FIELD_SPECS[entity_type]

        inserted = 0
        for _row_num, row in rows:
            # ---- Parse row per field spec, splitting identity from content ----
            identity: Dict[str, Any] = {}
            content: Dict[str, Any] = {}
            for col, kind in spec:
                if col not in row:
                    continue
                value = _import_value(row.get(col), kind)
                if col in _IDENTITY_COLUMNS:
                    identity[col] = value
                elif value is None and kind not in ("bool", "json"):
                    # Empty optional value -> fall back to the model default.
                    continue
                else:
                    content[col] = value

            preserved_id = identity.get("id")
            preserved_artifact_id = identity.get("artifact_id")
            version = identity.get("version")
            created_at = identity.get("created_at")
            modified_at = identity.get("modified_at") or identity.get("updated_at")

            # ---- Backing Artifact (every entity type has one) ----
            artifact_kwargs: Dict[str, Any] = dict(
                tenant=tenant,
                workspace=workspace,
                artifact_type=artifact_type_tag,
            )
            if preserved_artifact_id is not None:
                artifact_kwargs["id"] = preserved_artifact_id
            artifact = Artifact.objects.create(**artifact_kwargs)

            # ---- Entity row ----
            if entity_type in _PERSISTENCE_ENTITY_TYPES:
                model = persistence_models[entity_type]
                create_kwargs: Dict[str, Any] = dict(
                    tenant=tenant, artifact=artifact, **content
                )
                mod_field = "modified_at"
            else:  # Adr / Risk / Issue
                model = app_models[entity_type]
                create_kwargs = dict(
                    artifact=artifact,
                    workspace_id=workspace.id,
                    tenant_id=tenant.id,
                    **content,
                )
                # Preserve exported author, else attribute to the importing user.
                created_by = identity.get("created_by")
                create_kwargs["created_by"] = (
                    created_by if created_by else str(ctx.user_id)
                )
                mod_field = "updated_at"

            if preserved_id is not None:
                create_kwargs["id"] = preserved_id
            if version is not None:
                create_kwargs["version"] = version

            obj = model.objects.create(**create_kwargs)

            # ---- Preserve audit timestamps (bypass auto_now/auto_now_add) ----
            ts_updates: Dict[str, Any] = {}
            if created_at is not None:
                ts_updates["created_at"] = created_at
            if modified_at is not None:
                ts_updates[mod_field] = modified_at
            if ts_updates:
                model.objects.filter(pk=obj.pk).update(**ts_updates)

            inserted += 1

        return inserted


__all__ = ["ImportService", "ImportResult", "ImportRowError"]
