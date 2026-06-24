"""
COMP-AS-008 ExportService — Multi-format artifact export.

leaf_id : COMP-AS-008
req_id  : REQ-L1-019, REQ-L1-023, REQ-L2-AppSvc-006, REQ-L2-AppSvc-007,
          REQ-L3-EXP-001, REQ-L3-EXP-002, REQ-L3-EXP-003

Produces JSON, CSV, Markdown, and PDF exports for Requirements,
ArchitectureElements, and TestCases scoped by workspace or single artifact.
Embeds active terminology profile as metadata.

PDF support: stub/NotImplemented — reportlab/weasyprint not available in the
current container image. See TODO-PDF below.

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

from application.base import NotFoundError, ServiceBase, ValidationError

logger = logging.getLogger(__name__)

# Supported entity types
_VALID_ENTITY_TYPES = {"Requirement", "ArchitectureElement", "TestCase"}

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
                writer.writerow(row)

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

    # ---------- PDF (stub) ----------

    def export_pdf(
        self,
        entity_type: str,
        workspace_id: UUID | str,
        ctx: AuthContext,
        artifact_id: Optional[UUID | str] = None,
    ) -> ExportResult:
        """Export entities as PDF — STUB, not yet implemented.

        REQ-L1-023 requires PDF export. Implementation blocked pending
        reportlab/weasyprint availability in the container image.

        TODO-PDF: Install a PDF library and implement _render_pdf().
        Until then this raises NotImplementedError.

        Raises:
            NotImplementedError: Always — PDF lib not installed.
        """
        raise NotImplementedError(
            "PDF export (REQ-L1-023) is not yet implemented. "
            "Add reportlab or weasyprint to requirements.txt and implement "
            "ExportService._render_pdf(). Tracking: TODO-PDF."
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
        """Query persistence layer for entities of the given type.

        IF-AS-EXT-OUT-007.
        """
        from persistence.models import ArchitectureElement, Requirement, TestCase

        art_filter: Dict[str, Any] = {"artifact__workspace_id": workspace_id}
        if artifact_id is not None:
            art_filter["artifact_id"] = UUID(str(artifact_id))

        if entity_type == "Requirement":
            qs = Requirement.objects.filter(**art_filter).select_related("artifact")
            return [
                {
                    "id": str(r.id),
                    "artifact_id": str(r.artifact_id),
                    "title": r.title,
                    "description": r.description,
                    "category": r.category,
                    "status": r.status,
                    "version": r.version,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                    "modified_at": r.modified_at.isoformat() if r.modified_at else None,
                }
                for r in qs
            ]

        if entity_type == "ArchitectureElement":
            qs = ArchitectureElement.objects.filter(**art_filter).select_related("artifact")
            return [
                {
                    "id": str(e.id),
                    "artifact_id": str(e.artifact_id),
                    "title": e.title,
                    "description": e.description,
                    "element_type": e.element_type,
                    "version": e.version,
                    "created_at": e.created_at.isoformat() if e.created_at else None,
                    "modified_at": e.modified_at.isoformat() if e.modified_at else None,
                }
                for e in qs
            ]

        if entity_type == "TestCase":
            qs = TestCase.objects.filter(**art_filter).select_related("artifact")
            return [
                {
                    "id": str(t.id),
                    "artifact_id": str(t.artifact_id),
                    "title": t.title,
                    "description": t.description,
                    "steps": t.steps,
                    "version": t.version,
                    "created_at": t.created_at.isoformat() if t.created_at else None,
                    "modified_at": t.modified_at.isoformat() if t.modified_at else None,
                }
                for t in qs
            ]

        return []  # unreachable due to _validate_entity_type guard


__all__ = ["ExportService", "ExportResult"]
