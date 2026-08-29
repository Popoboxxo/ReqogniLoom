"""
COMP-AS-008 ExportService — Multi-format artifact export.

leaf_id : COMP-AS-008
req_id  : REQ-L1-019, REQ-L1-023, REQ-L2-AppSvc-006, REQ-L2-AppSvc-007,
          REQ-L3-EXP-001, REQ-L3-EXP-002, REQ-L3-EXP-003

Produces JSON, CSV, Markdown, and PDF exports for StakeholderNeeds, Requirements,
ArchitectureElements, TestCases (persistence app) and Adrs, Risks, Issues
(application app) scoped by workspace or single artifact. Embeds active
terminology profile as metadata.

C7 (frontend-feedback Cluster C): StakeholderNeed added to enable CSV export
of Bedarfe alongside Requirements and ArchitectureElements.

Round-trip fidelity: the exported column set is driven by the shared
``ENTITY_FIELD_SPECS`` registry and includes identity/audit columns (id,
artifact_id, version, created_at, modified/updated timestamp) so that
``export_csv -> ImportService.import_csv`` is a lossless round-trip (the ReqFlow
self-migration safety net) -- with one deliberate exception (SA-31, Systemaudit
2026-08-27 AP-6): a string field starting with ``=``/``+``/``-``/``@``/TAB/CR
is prefixed with a leading ``'`` on export (see :func:`_csv_cell`), the
OWASP-documented CSV/formula-injection mitigation. Re-importing that cell
therefore recovers the quote-prefixed text, not byte-for-byte the original --
an accepted, security-motivated trade-off, not a bug.

PDF support: Implemented via reportlab. Delegates to pdf_report_generator
for workspace-level document exports.

Interface contracts implemented:
  IF-AS-EXT-IN-001  — inbound: export_json, export_csv, export_markdown, export_pdf
  IF-AS-EXT-OUT-007 — outbound: persistence ORM queries (Requirement, ArchitectureElement, TestCase)
  IF-AS-EXT-OUT-004 — outbound: PresetPolicyService (terminology profile via presets.services)

Architecture:
  docs/se/L1/Gesamtsystem/L2/ApplicationServiceSystem/Components/
    COMP-AS-008_ExportService/
"""
from __future__ import annotations

import csv
import io
import json
import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

from auth_tenancy.context import AuthContext

# Backward-compat alias used by tests that patch 'application.export_service.TenantContext'
TenantContext = AuthContext

from application.base import NotFoundError, ServiceBase, ValidationError
from application.csv_safety import neutralize_csv_formula

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Round-trip field registry (shared with ImportService)
# ---------------------------------------------------------------------------
#
# A single, symmetric field registry drives BOTH export serialisation and
# import deserialisation so that ``export_csv -> import_csv`` is a lossless
# round-trip (COMP-AS-008 / COMP-AS-009). ImportService imports
# ``ENTITY_FIELD_SPECS`` and the entity-type sets from this module; the two
# services therefore agree on the exact column set and per-column value kind.
#
# Each spec entry is ``(column_name, kind)`` where ``column_name`` is BOTH the
# CSV/JSON column and the ORM attribute name, and ``kind`` is one of:
#   "str"      — non-nullable text (None -> "")
#   "nstr"     — nullable text (empty CSV cell -> None)
#   "int"      — nullable integer (empty CSV cell -> None)
#   "bool"     — boolean ("true"/"false" in CSV)
#   "json"     — JSON list/dict (serialised to a JSON string in CSV)
#   "datetime" — ISO-8601 timestamp
#   "uuid"     — UUID rendered as a string
#
# Identity / audit columns (id, artifact_id, version, created_at, and the
# per-model modified timestamp) are part of the spec so they round-trip; the
# import path gives them special handling (see ImportService._insert_rows).

# Common trailing columns for the artifact-backed persistence models
# (StakeholderNeed, Requirement, ArchitectureElement, TestCase). Their
# "modified" timestamp column is ``modified_at`` (AuditableModel).
_COMMON_PERSISTENCE_FIELDS = [
    ("uid", "nstr"),
    ("id", "uuid"),
    ("artifact_id", "uuid"),
    ("version", "int"),
    ("created_at", "datetime"),
    ("modified_at", "datetime"),
]

# Common trailing columns for the plain application models (Adr, Risk, Issue).
# These carry ``workspace_id``/``tenant_id`` as UUID columns (not FKs) and use
# ``updated_at`` as their modified timestamp.
_COMMON_APP_FIELDS = [
    ("uid", "nstr"),
    ("id", "uuid"),
    ("artifact_id", "uuid"),
    ("version", "int"),
    ("created_by", "str"),
    ("created_at", "datetime"),
    ("updated_at", "datetime"),
]

ENTITY_FIELD_SPECS: Dict[str, List[tuple]] = {
    "StakeholderNeed": [
        ("title", "str"),
        ("description", "str"),
        ("category", "str"),
        ("status", "str"),
        ("moscow_priority", "nstr"),
        ("suspect", "bool"),
        ("lifecycle_status", "str"),
    ]
    + _COMMON_PERSISTENCE_FIELDS,
    "Requirement": [
        ("title", "str"),
        ("description", "str"),
        ("category", "str"),
        ("status", "str"),
        ("type", "str"),
        ("level", "int"),
        ("complexity_fibonacci", "int"),
        ("verification_method", "nstr"),
        ("suspect", "bool"),
        ("lifecycle_status", "str"),
    ]
    + _COMMON_PERSISTENCE_FIELDS,
    "ArchitectureElement": [
        ("title", "str"),
        ("description", "str"),
        ("element_type", "str"),
        ("asil_level", "nstr"),
        ("make_or_buy", "nstr"),
        ("suspect", "bool"),
        ("lifecycle_status", "str"),
    ]
    + _COMMON_PERSISTENCE_FIELDS,
    "TestCase": [
        ("title", "str"),
        ("description", "str"),
        ("steps", "json"),
        ("test_type", "nstr"),
        ("suspect", "bool"),
        ("status", "str"),
    ]
    + _COMMON_PERSISTENCE_FIELDS,
    "Adr": [
        ("title", "str"),
        ("description", "str"),
        ("context", "str"),
        ("consequences", "str"),
        ("status", "str"),
    ]
    + _COMMON_APP_FIELDS,
    "Risk": [
        ("title", "str"),
        ("description", "str"),
        ("category", "str"),
        ("probability", "str"),
        ("impact", "str"),
        ("risk_score", "int"),
        ("severity", "str"),
        ("owner", "str"),
        ("mitigation_strategy", "str"),
        ("detection", "int"),
        ("status", "str"),
    ]
    + _COMMON_APP_FIELDS,
    "Issue": [
        ("title", "str"),
        ("description", "str"),
        ("severity", "str"),
        ("category", "str"),
        ("assignee_id", "uuid"),
        ("due_date", "datetime"),
        ("tags", "json"),
        ("status", "str"),
    ]
    + _COMMON_APP_FIELDS,
}

# Entity types whose rows live in the persistence app (artifact-scoped via the
# 1:1 ``artifact`` FK and the tenant-isolating TenantManager).
_PERSISTENCE_ENTITY_TYPES = frozenset(
    {"StakeholderNeed", "Requirement", "ArchitectureElement", "TestCase"}
)

# Entity types owned by the application app (plain models with UUID
# ``workspace_id``/``tenant_id`` columns and a nullable backing ``artifact``).
_APP_ENTITY_TYPES = frozenset({"Adr", "Risk", "Issue"})

# Supported entity types (single source: the field registry).
_VALID_ENTITY_TYPES = frozenset(ENTITY_FIELD_SPECS.keys())


def _export_value(value: Any, kind: str) -> Any:
    """Serialise an ORM attribute *value* to its export representation.

    Returns native Python types (str/int/bool/list/dict/None) suitable for the
    JSON exporter; the CSV exporter further flattens complex values via
    :func:`_csv_cell`. ``datetime`` values become ISO-8601 strings and ``uuid``
    values become their string form.
    """
    if value is None:
        return None
    if kind == "datetime":
        return value.isoformat()
    if kind == "uuid":
        return str(value)
    # str / nstr / int / bool / json → native value (JSON-serialisable as-is)
    return value


#: SYSTEMAUDIT-2026-08-27 AP-6 L-4: the trigger set and the escaping logic
#: live in :mod:`application.csv_safety`, shared with
#: :func:`application.requirement_bundle_formatters._csv_safe` (same
#: OWASP-documented CSV/formula-injection mitigation, same set — SA-31,
#: Systemaudit 2026-08-27 AP-6: this exporter was the one CSV output path
#: that used to skip it).


def _csv_cell(value: Any) -> str:
    """Flatten a native export value to a single CSV cell string.

    Complex values (list/dict) and booleans are rendered as JSON so the import
    side can recover them losslessly with :func:`json.loads`; ``None`` becomes an
    empty cell.

    String cells starting with ``=``, ``+``, ``-``, ``@``, TAB or CR are
    prefixed with a single quote (SA-31: CSV/formula injection, see
    :func:`application.csv_safety.neutralize_csv_formula`). Requirement/
    ArchitectureElement/... titles and descriptions are free text written by
    any editor-role tenant user, and this export is served directly as
    ``text/csv`` for the caller to open in a spreadsheet application -- an
    unescaped ``=cmd|'/c calc'!A1`` title would otherwise execute on whoever
    opens the file.
    """
    if value is None:
        return ""
    if isinstance(value, str):
        return neutralize_csv_formula(value)
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)

# ---------- DTOs ----------


class ExportResult:
    """Container for export output.

    Attributes:
        content: Serialised export content (str or bytes for PDF).
        media_type: MIME type string.
        filename: Suggested filename for HTTP Content-Disposition.
        record_count: Number of exported records.
    """

    def __init__(
        self,
        content: str | bytes,
        media_type: str,
        filename: str,
        record_count: int,
    ) -> None:
        self.content = content
        self.media_type = media_type
        self.filename = filename
        self.record_count = record_count


# ---------- Service ----------


class ExportService(ServiceBase):
    """Multi-format export for Requirements, ArchitectureElements, TestCases.

    COMP-AS-008. REQ-L3-EXP-001 (JSON), REQ-L3-EXP-002 (CSV),
    REQ-L3-EXP-003 (Markdown), REQ-L1-023 (PDF stub).

    Usage::

        svc = ExportService()
        result = svc.export_json(
            entity_type="Requirement",
            workspace_id=ws_uuid,
            ctx=auth_ctx,
        )
        response.write(result.content)
    """

    # ---------- JSON ----------

    def export_json(
        self,
        entity_type: str,
        workspace_id: UUID | str,
        ctx: AuthContext,
        artifact_id: Optional[UUID | str] = None,
    ) -> ExportResult:
        """Export entities as JSON with embedded terminology metadata.

        REQ-L3-EXP-001.

        Args:
            entity_type: "Requirement" | "ArchitectureElement" | "TestCase"
            workspace_id: Workspace UUID.
            ctx: AuthContext for tenant scoping.
            artifact_id: Optional — restrict export to single artifact.

        Returns:
            ExportResult with media_type="application/json".
        """
        self._set_tenant_context(ctx)
        self._validate_entity_type(entity_type)

        ws_uuid = UUID(str(workspace_id))
        rows = self._fetch_entities(entity_type, ws_uuid, artifact_id)
        terminology = self._get_terminology_profile(str(ws_uuid))

        payload: Dict[str, Any] = {
            "metadata": {
                "entity_type": entity_type,
                "workspace_id": str(ws_uuid),
                "terminology_profile": terminology,
                "record_count": len(rows),
            },
            "data": rows,
        }

        content = json.dumps(payload, ensure_ascii=False, indent=2)
        return ExportResult(
            content=content,
            media_type="application/json",
            filename=f"export_{entity_type.lower()}.json",
            record_count=len(rows),
        )

    # ---------- CSV ----------

    def export_csv(
        self,
        entity_type: str,
        workspace_id: UUID | str,
        ctx: AuthContext,
        artifact_id: Optional[UUID | str] = None,
    ) -> ExportResult:
        """Export entities as CSV with terminology comment in first row.

        REQ-L3-EXP-002.

        Args:
            entity_type: "Requirement" | "ArchitectureElement" | "TestCase"
            workspace_id: Workspace UUID.
            ctx: AuthContext for tenant scoping.
            artifact_id: Optional — restrict to single artifact.

        Returns:
            ExportResult with media_type="text/csv".
        """
        self._set_tenant_context(ctx)
        self._validate_entity_type(entity_type)

        ws_uuid = UUID(str(workspace_id))
        rows = self._fetch_entities(entity_type, ws_uuid, artifact_id)
        terminology = self._get_terminology_profile(str(ws_uuid))

        buf = io.StringIO()

        # REQ-L3-EXP-002: terminology profile as comment in row 1
        buf.write(f"# terminology_profile: {terminology}\n")

        if rows:
            writer = csv.DictWriter(
                buf,
                fieldnames=list(rows[0].keys()),
                extrasaction="ignore",
                quoting=csv.QUOTE_ALL,
            )
            writer.writeheader()
            for row in rows:
                # Flatten complex values (list/dict/bool/None) to lossless CSV
                # cells so ImportService can recover them via json.loads.
                writer.writerow({k: _csv_cell(v) for k, v in row.items()})

        content = buf.getvalue()
        return ExportResult(
            content=content,
            media_type="text/csv",
            filename=f"export_{entity_type.lower()}.csv",
            record_count=len(rows),
        )

    # ---------- Markdown ----------

    def export_markdown(
        self,
        entity_type: str,
        workspace_id: UUID | str,
        ctx: AuthContext,
        artifact_id: Optional[UUID | str] = None,
    ) -> ExportResult:
        """Export entities as Markdown document.

        REQ-L1-019.

        Args:
            entity_type: "Requirement" | "ArchitectureElement" | "TestCase"
            workspace_id: Workspace UUID.
            ctx: AuthContext for tenant scoping.
            artifact_id: Optional — restrict to single artifact.

        Returns:
            ExportResult with media_type="text/markdown".
        """
        self._set_tenant_context(ctx)
        self._validate_entity_type(entity_type)

        ws_uuid = UUID(str(workspace_id))
        rows = self._fetch_entities(entity_type, ws_uuid, artifact_id)
        terminology = self._get_terminology_profile(str(ws_uuid))

        lines = [
            f"# {entity_type} Export",
            f"",
            f"> **Workspace:** {ws_uuid}  ",
            f"> **Terminology profile:** {terminology}  ",
            f"> **Record count:** {len(rows)}",
            f"",
            "---",
            "",
        ]

        for row in rows:
            lines.append(f"## {row.get('title', row.get('id', 'Unknown'))}")
            lines.append("")
            if row.get("description"):
                lines.append(row["description"])
                lines.append("")
            # remaining fields as definition list
            for k, v in row.items():
                if k not in ("title", "description") and v:
                    lines.append(f"**{k}:** {v}  ")
            lines.append("")
            lines.append("---")
            lines.append("")

        content = "\n".join(lines)
        return ExportResult(
            content=content,
            media_type="text/markdown",
            filename=f"export_{entity_type.lower()}.md",
            record_count=len(rows),
        )

    # ---------- PDF (REQ-L2-AS-016) ----------

    def export_pdf(
        self,
        entity_type: str,
        workspace_id: UUID | str,
        ctx: AuthContext,
        artifact_id: Optional[UUID | str] = None,
    ) -> ExportResult:
        """Export workspace report as PDF.

        REQ-L2-AS-016 / REQ-L1-023: PDF export via reportlab.
        Delegates to traceability.pdf_report_generator for workspace-level
        reports.

        Args:
            entity_type: "Requirement" | "ArchitectureElement" | "TestCase"
                (used to select layout: Requirement → requirement_document,
                others → traceability_matrix).
            workspace_id: Workspace UUID.
            ctx: AuthContext for tenant scoping.
            artifact_id: Optional — ignored for workspace-level PDF.

        Returns:
            ExportResult with media_type="application/pdf".
        """
        self._set_tenant_context(ctx)
        self._validate_entity_type(entity_type)

        ws_uuid = UUID(str(workspace_id))

        # Select layout based on entity_type
        layout = (
            "requirement_document"
            if entity_type == "Requirement"
            else "traceability_matrix"
        )

        from traceability.pdf_report_generator import generate_pdf_report

        pdf_bytes = generate_pdf_report(
            workspace_id=ws_uuid,
            layout=layout,
        )

        return ExportResult(
            content=pdf_bytes,
            media_type="application/pdf",
            filename=f"export_{entity_type.lower()}.pdf",
            record_count=1,  # workspace-level report
        )

    # ---------- Private helpers ----------

    @staticmethod
    def _validate_entity_type(entity_type: str) -> None:
        if entity_type not in _VALID_ENTITY_TYPES:
            raise ValidationError(
                f"Unsupported entity_type '{entity_type}'. "
                f"Allowed: {sorted(_VALID_ENTITY_TYPES)}"
            )

    @staticmethod
    def _get_terminology_profile(workspace_id: str) -> str:
        """Fetch active terminology profile name from PresetConfigEngine.

        IF-AS-EXT-OUT-004.
        """
        try:
            from presets.services import get_preset

            preset = get_preset(workspace_id)
            # preset object may expose terminology_profile attribute or dict key
            return str(getattr(preset, "terminology_profile", "default"))
        except Exception:
            logger.warning(
                "ExportService: could not fetch terminology profile for ws=%s, "
                "using 'default'",
                workspace_id,
            )
            return "default"

    @staticmethod
    def _fetch_entities(
        entity_type: str,
        workspace_id: UUID,
        artifact_id: Optional[UUID | str],
    ) -> List[Dict[str, Any]]:
        """Query the persistence/application layer for entities of *entity_type*.

        IF-AS-EXT-OUT-007. Serialises each row via the shared
        :data:`ENTITY_FIELD_SPECS` registry so the exported column set is exactly
        what :class:`~application.import_service.ImportService` consumes on
        re-import (lossless round-trip).

        Adr/Risk/Issue are plain application models scoped by their ``workspace_id``
        UUID column (a workspace belongs to exactly one tenant, so filtering by
        workspace provides tenant isolation without a TenantManager).
        """
        spec = ENTITY_FIELD_SPECS[entity_type]

        if entity_type in _PERSISTENCE_ENTITY_TYPES:
            from persistence.models import (
                ArchitectureElement,
                Requirement,
                StakeholderNeed,
                TestCase,
            )

            model = {
                "StakeholderNeed": StakeholderNeed,
                "Requirement": Requirement,
                "ArchitectureElement": ArchitectureElement,
                "TestCase": TestCase,
            }[entity_type]

            flt: Dict[str, Any] = {"artifact__workspace_id": workspace_id}
            if artifact_id is not None:
                flt["artifact_id"] = UUID(str(artifact_id))
            qs = model.objects.filter(**flt).select_related("artifact")
        else:  # Adr / Risk / Issue
            from application.models import Adr, Issue, Risk

            model = {"Adr": Adr, "Risk": Risk, "Issue": Issue}[entity_type]

            flt = {"workspace_id": workspace_id}
            if artifact_id is not None:
                flt["artifact_id"] = UUID(str(artifact_id))
            qs = model.objects.filter(**flt)

        return [ExportService._serialize_row(obj, spec) for obj in qs]

    @staticmethod
    def _serialize_row(obj: Any, spec: List[tuple]) -> Dict[str, Any]:
        """Serialise a single ORM *obj* into a row dict per *spec*."""
        return {col: _export_value(getattr(obj, col, None), kind) for col, kind in spec}


__all__ = [
    "ExportService",
    "ExportResult",
    "ENTITY_FIELD_SPECS",
    "_PERSISTENCE_ENTITY_TYPES",
    "_APP_ENTITY_TYPES",
]
