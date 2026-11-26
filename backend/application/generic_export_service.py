"""Generic multi-format export for every entity in the transfer contract (P2).

The existing :class:`~application.export_service.ExportService` serves seven
types through ``ENTITY_FIELD_SPECS``. This service closes the gap for the
remaining REST/MCP entities declared in
:mod:`application.artifact_transfer_contract`: it resolves the Django model,
filters it to one workspace, serialises concrete columns (never secrets or
embeddings) and renders JSON/CSV/Markdown/PDF.

It is intentionally *not* the ReqIF path (standard-conformant mapping lives in
``reqif_export_service``) and not the ZIP snapshot (P5). Large workspaces are
rejected with a row cap here; P5 adds the async/streaming path.
"""
from __future__ import annotations

import csv
import io
import json
from datetime import date, datetime
from typing import Any
from uuid import UUID

from django.apps import apps
from django.db import models

from application.artifact_transfer_contract import (
    SNAPSHOT_EXCLUSIONS,
    TRANSFER_SPECS,
    ArtifactTransferSpec,
    spec_for,
)
from application.base import NotFoundError, ServiceBase, ValidationError
from application.csv_safety import neutralize_csv_formula
from application.export_service import ExportResult
from auth_tenancy.context import AuthContext

#: Columns that must never leave the instance through a generic export.
_SENSITIVE_FRAGMENTS = (
    "password",
    "secret",
    "ciphertext",
    "api_key",
    "token",
    "embedding",
    "file_sha256",
)

#: Two model names in the entity-surface matrix differ from their class names.
_MODEL_OVERRIDES: dict[str, str] = {
    "Baseline": "baseline.BaselineSnapshot",
    "WorkspaceLinkType": "link_types.WorkspaceLinkTypeDefinition",
}

_DEFAULT_MAX_ROWS = 10_000

_MEDIA_TYPES = {
    "json": "application/json",
    "csv": "text/csv",
    "markdown": "text/markdown",
    "pdf": "application/pdf",
}


def _model_for(spec: ArtifactTransferSpec) -> type[models.Model]:
    label = _MODEL_OVERRIDES.get(spec.type_name, spec.type_name)
    if "." in label:
        model = apps.get_model(label)
    else:
        matches = [m for m in apps.get_models() if m.__name__ == label]
        if len(matches) != 1:
            raise ValidationError(
                f"Transfer entity {spec.entity_key!r} does not resolve to one model "
                f"({len(matches)} matches for {label!r})."
            )
        model = matches[0]
    return model


def _workspace_filter(model: type[models.Model], workspace_id: UUID, ctx: AuthContext) -> dict[str, Any]:
    """Return the ORM filter selecting the rows visible from one workspace.

    Most models are scoped through their artifact/source or a workspace column.
    Two tenant-level configuration entities carry no workspace relation at all
    and are therefore scoped by the tenant: the exported ``Workspace`` row
    itself and the tenant-wide ``GlobalWorkflowDefinition`` templates.
    """
    fields = {f.name for f in model._meta.get_fields()}
    if "artifact" in fields:
        return {"artifact__workspace_id": workspace_id}
    if "source" in fields and "workspace" not in fields:
        # TraceLink: the source artifact determines the workspace.
        return {"source__workspace_id": workspace_id}
    if "workspace" in fields or "workspace_id" in fields:
        return {"workspace_id": workspace_id}
    if model.__name__ == "GlobalWorkflowDefinition":
        # Tenant-wide workflow template: the tenant is the scope; every
        # workspace of the tenant sees the same rows.
        return {"tenant_id": ctx.tenant_id}
    if spec_scope_is_global(model):
        # Workspace itself: the tenant is the scope; return only that row.
        return {"id": workspace_id, "tenant_id": ctx.tenant_id}
    raise ValidationError(
        f"Model {model.__name__} has no workspace scoping path; cannot export per workspace."
    )


def spec_scope_is_global(model: type[models.Model]) -> bool:
    """True for tenant-level entities that carry no workspace relation."""
    return model.__name__ == "Workspace"


def _export_value(value: Any) -> Any:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, models.Model):
        return str(value.pk)
    if isinstance(value, (list, dict, bool, int, float)) or value is None:
        return value
    return str(value)


def _serialize_row(obj: models.Model) -> dict[str, Any]:
    row: dict[str, Any] = {}
    for field in obj._meta.concrete_fields:
        name = field.name
        lowered = name.lower()
        if name in SNAPSHOT_EXCLUSIONS:
            continue
        if any(fragment in lowered for fragment in _SENSITIVE_FRAGMENTS):
            continue
        value = _export_value(getattr(obj, name, None))
        if field.is_relation and value is not None:
            row[f"{name}_id"] = str(getattr(obj, f"{name}_id", value))
        else:
            row[name] = value
    return row


def _render_json(rows: list[dict[str, Any]], spec: ArtifactTransferSpec, workspace_id: UUID) -> str:
    return json.dumps(
        {
            "metadata": {
                "entity": spec.entity_key,
                "type": spec.type_name,
                "workspace_id": str(workspace_id),
                "record_count": len(rows),
                "contract": "artifact-transfer/v1",
            },
            "data": rows,
        },
        ensure_ascii=False,
        indent=2,
        default=str,
    )


def _columns(rows: list[dict[str, Any]]) -> list[str]:
    if not rows:
        return []
    columns: list[str] = []
    for row in rows:
        for key in row:
            if key not in columns:
                columns.append(key)
    return columns


def _render_csv(rows: list[dict[str, Any]]) -> str:
    buf = io.StringIO()
    columns = _columns(rows)
    writer = csv.DictWriter(buf, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({key: neutralize_csv_formula(row.get(key)) for key in columns})
    return buf.getvalue()


def _render_markdown(rows: list[dict[str, Any]], spec: ArtifactTransferSpec) -> str:
    columns = _columns(rows)
    lines = [f"# {spec.type_name}", ""]
    if not columns:
        return "\n".join(lines + ["_No records._", ""])
    lines += ["| " + " | ".join(columns) + " |", "| " + " | ".join("---" for _ in columns) + " |"]
    for row in rows:
        lines.append(
            "| " + " | ".join(str(row.get(col, "")).replace("|", "\\|") for col in columns) + " |"
        )
    return "\n".join(lines) + "\n"


def _render_pdf(rows: list[dict[str, Any]], spec: ArtifactTransferSpec) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    pdf = canvas.Canvas(buf, pagesize=A4)
    width, height = A4
    y = height - 40
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(40, y, f"{spec.type_name} — {len(rows)} records")
    y -= 24
    pdf.setFont("Helvetica", 8)
    for row in rows:
        line = " · ".join(f"{k}={str(v)[:80]}" for k, v in list(row.items())[:6])
        for chunk in (line[i : i + 110] for i in range(0, max(1, len(line)), 110)):
            if y < 40:
                pdf.showPage()
                pdf.setFont("Helvetica", 8)
                y = height - 40
            pdf.drawString(40, y, chunk)
            y -= 10
    pdf.save()
    return buf.getvalue()


class GenericArtifactExportService(ServiceBase):
    """Export any transfer-contract entity in all four artifact formats."""

    def export(
        self,
        *,
        ctx: AuthContext,
        workspace_id: UUID | str,
        entity_key: str,
        format: str = "json",
        max_rows: int = _DEFAULT_MAX_ROWS,
    ) -> ExportResult:
        spec = spec_for(entity_key)
        if spec is None:
            raise ValidationError(
                f"Unknown transfer entity {entity_key!r}; allowed: {sorted(TRANSFER_SPECS)}"
            )
        if format not in _MEDIA_TYPES:
            raise ValidationError(
                f"Unsupported export format {format!r}; allowed: {sorted(_MEDIA_TYPES)}"
            )
        if format not in spec.formats:
            raise ValidationError(
                f"Format {format!r} is not declared for {entity_key!r}; "
                f"declared: {sorted(spec.formats)}"
            )
        if max_rows < 1:
            raise ValidationError("max_rows must be >= 1")

        self._set_tenant_context(ctx)
        ws_uuid = UUID(str(workspace_id))
        from persistence.models import Workspace

        if not Workspace.objects.filter(id=ws_uuid, tenant_id=ctx.tenant_id).exists():
            raise NotFoundError(f"Workspace {ws_uuid} not found")

        model = _model_for(spec)
        queryset = model.objects.filter(**_workspace_filter(model, ws_uuid, ctx))
        queryset = queryset[: max_rows + 1]
        objects = list(queryset)
        truncated = len(objects) > max_rows
        rows = [_serialize_row(obj) for obj in objects[:max_rows]]

        if format == "json":
            content: str | bytes = _render_json(rows, spec, ws_uuid)
        elif format == "csv":
            content = _render_csv(rows)
        elif format == "markdown":
            content = _render_markdown(rows, spec)
        else:
            content = _render_pdf(rows, spec)

        return ExportResult(
            content=content,
            media_type=_MEDIA_TYPES[format],
            filename=f"export_{entity_key}.{format}",
            record_count=len(rows),
            truncated=truncated,
        )


__all__ = [
    "GenericArtifactExportService",
    "SNAPSHOT_EXCLUSIONS",
    "spec_for",
]
