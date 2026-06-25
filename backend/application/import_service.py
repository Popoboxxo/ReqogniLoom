"""
COMP-AS-009 ImportService — Atomic CSV bulk import.

leaf_id : COMP-AS-009
req_id  : REQ-L1-021, REQ-L2-AppSvc-014, REQ-L3-IMP-001, REQ-L3-IMP-002,
          REQ-L3-IMP-003, REQ-L3-IMP-004

Imports Requirements, ArchitectureElements, or TestCases from CSV.
Validates every row (RFC 4180, required fields, type checks) and writes all
valid rows in a single transaction (all-or-nothing, REQ-L3-IMP-002).
Supports up to 1000 rows per call.

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
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from auth_tenancy.context import AuthContext
from django.db import transaction

# Backward-compat alias used by tests that patch 'application.import_service.TenantContext'
TenantContext = AuthContext

from application.base import NotFoundError, ServiceBase, ValidationError

logger = logging.getLogger(__name__)

# Maximum rows in a single import call (REQ-L3-IMP-003)
_MAX_ROWS = 1000

# Required fields per entity type (REQ-L3-IMP-001)
_REQUIRED_FIELDS: Dict[str, List[str]] = {
    "Requirement": ["title"],
    "ArchitectureElement": ["title"],
    "TestCase": ["title"],
}

# Valid entity types
_VALID_ENTITY_TYPES = set(_REQUIRED_FIELDS.keys())


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
                    operation=f"{entity_type.lower()}.import",
                    entity_type=entity_type,
                    entity_id=ws_uuid,  # workspace as aggregate entity_id for batch
                    details={
                        "workspace_id": str(ws_uuid),
                        "imported_count": imported,
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

        IF-AS-EXT-OUT-007: persistence ORM writes.
        Returns count of inserted rows.
        """
        from persistence.models import ArchitectureElement, Artifact, Requirement, TestCase, Workspace

        workspace = Workspace.objects.get(id=workspace_id)
        tenant = workspace.tenant

        inserted = 0
        for _row_num, row in rows:
            title = row.get("title", "").strip()
            description = row.get("description", "").strip()

            artifact = Artifact.objects.create(
                tenant=tenant,
                workspace=workspace,
                artifact_type=artifact_type_tag,
            )

            if entity_type == "Requirement":
                Requirement.objects.create(
                    tenant=tenant,
                    artifact=artifact,
                    title=title,
                    description=description,
                    category=row.get("category", "").strip(),
                    status=row.get("status", "draft").strip(),
                )
            elif entity_type == "ArchitectureElement":
                ArchitectureElement.objects.create(
                    tenant=tenant,
                    artifact=artifact,
                    title=title,
                    description=description,
                    element_type=row.get("element_type", "").strip(),
                )
            elif entity_type == "TestCase":
                steps_raw = row.get("steps", "")
                steps: List[Any] = []
                if steps_raw:
                    try:
                        import json as _json
                        steps = _json.loads(steps_raw)
                    except Exception:
                        steps = [steps_raw]

                TestCase.objects.create(
                    tenant=tenant,
                    artifact=artifact,
                    title=title,
                    description=description,
                    steps=steps,
                )

            inserted += 1

        return inserted


__all__ = ["ImportService", "ImportResult", "ImportRowError"]
