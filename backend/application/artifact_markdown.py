"""Generic artifact -> Markdown renderer (MCP-Modernisierung Task 5).

Single source of Markdown for one artifact, consumed by the MCP
``resources/read`` capability (``mcp_server.tools.resources``) and intended as
the module the Dokumentensicht spec consumes for its reading surface, so the
two access paths cannot drift apart (spec section 8, risk 2).

Why this module exists and what it does **not** reuse
-----------------------------------------------------
The existing document renderers are deliberately *document*-shaped, not
artifact-shaped:

* :meth:`application.document_reading_service.DocumentViewResult.to_markdown`
  serialises the chapters parsed out of one ``Document.body`` — a single
  already-Markdown column. It has no notion of "which fields does this entity
  type carry".
* :func:`application.document_projection_render.render_document` renders a
  repository projection of that same ``Document`` row (header, anchors, edges,
  glossary). Also document-specific and not usable for a ``Requirement``,
  ``TestCase`` or ``Adr`` row.
* ``diagram.mcp_artifact_provider.McpArtifactProvider`` renders *diagrams*; the
  ``artifact.get`` tool the design spec attributes to it does not exist in this
  codebase (see the plan's "Spec corrections" table).

None of them is a generic artifact renderer, so this module is genuinely new.
It is driven by Django field *classes*, not field *names*: a title-like
``CharField`` becomes the H1, short scalar fields become bullet metadata, and
every non-empty ``TextField`` becomes its own ``##`` section. All nine Generic
Artifact Model types are therefore covered by one implementation, and a column
added by a later spec shows up without touching this module.

A ``Document`` artifact's ``body`` is a ``TextField`` like any other, so it
renders as one section here; a caller that wants the chaptered reading surface
uses the document services above, which remain the authorities for documents.

Cross-plan note (``docs/superpowers/plans/2026-09-04-open-decisions.md``):
the Dokumentensicht plan independently sketched a dict-based
``render_artifact_markdown(row, *, heading_level, number, skip_fields)``
primitive. This module implements the ID-resolving entry point from the MCP
plan; if the Dokumentensicht primitive lands it can sit beside this function
and :func:`render_artifact_markdown` can delegate to it without changing the
MCP-facing contract.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Type
from uuid import UUID

from django.db import models

from application.base import NotFoundError
from auth_tenancy.context import AuthContext

logger = logging.getLogger(__name__)

#: MIME type announced for rendered artifacts on the MCP resource surface.
ARTIFACT_MARKDOWN_MIME = "text/markdown"

#: Columns that are infrastructure, not content. ``embedding`` is a
#: thousand-plus float vector, the join keys are ids the reader already holds,
#: and the audit columns are noise inside a specification document (the
#: History endpoint is the place for those).
_HIDDEN_FIELDS: frozenset[str] = frozenset(
    {
        "id",
        "tenant",
        "tenant_id",
        "artifact",
        "artifact_id",
        "workspace",
        "workspace_id",
        "embedding",
        "created_at",
        "updated_at",
        "modified_at",
        "created_by",
        "updated_by",
        "search_vector",
    }
)

#: Field names probed, in order, for the document heading.
_TITLE_FIELDS: tuple[str, ...] = ("title", "name", "summary")

#: Scalar field classes rendered as one-line bullet metadata. ``TextField`` is
#: deliberately absent: long text must never collapse into a bullet (see the
#: ordering note in :func:`render_artifact_markdown`).
_SCALAR_FIELD_TYPES: tuple[type, ...] = (
    models.CharField,
    models.BooleanField,
    models.IntegerField,
    models.PositiveIntegerField,
    models.PositiveSmallIntegerField,
    models.SmallIntegerField,
    models.DecimalField,
    models.FloatField,
    models.DateField,
)


def _model_for(entity_type: str) -> Type[models.Model] | None:
    """Return the Django model backing *entity_type*, or ``None``.

    Probes ``persistence.models`` first (Requirement, ArchitectureElement,
    StakeholderNeed, TestCase, Document) and falls back to the Layer-0
    domain-model registry for the application-layer models (Adr, Risk, Issue,
    Goal, MainGoal) and for ``Icd``, mirroring
    ``traceability.service._domain_model_registry``.
    """
    from persistence import models as persistence_models
    from persistence.domain_model_registry import get_model

    model = getattr(persistence_models, entity_type, None)
    if isinstance(model, type) and issubclass(model, models.Model):
        return model
    return get_model(entity_type)


def _label(field: models.Field) -> str:
    """Return the human-readable heading for *field*."""
    verbose = str(getattr(field, "verbose_name", "") or field.name)
    return verbose.replace("_", " ").strip().title()


def _display(row: models.Model, field: models.Field) -> str:
    """Return the display value of *field* on *row* (choices resolved)."""
    raw = getattr(row, field.name, "")
    if raw is None or raw == "":
        return ""
    if field.choices:
        getter = getattr(row, f"get_{field.name}_display", None)
        if callable(getter):
            return str(getter() or "")
    return str(raw)


def _workflow_status(entity_type: str, entity_id: Any) -> str | None:
    """Return the engine status of *(entity_type, entity_id)*, if it has one.

    Only types in :data:`workflow.state_reader.STATUS_TRACKED_ITEM_TYPES` carry
    a status concept at all; for every other type (e.g. ``Document``, which has
    its own ``status`` column rendered as an ordinary scalar field) this
    returns ``None`` so the renderer does not invent a status line.
    """
    from workflow import state_reader

    if entity_type not in state_reader.STATUS_TRACKED_ITEM_TYPES:
        return None
    try:
        state = state_reader.current_state(entity_type, entity_id)
    except Exception:  # pragma: no cover - defensive: engine must not break a read
        logger.debug("Workflow state lookup failed for %s %s", entity_type, entity_id)
        state = None
    return state or state_reader.initial_state(entity_type)


def render_artifact_markdown(artifact_id: UUID | str, ctx: AuthContext) -> str:
    """Render one artifact as a Markdown document.

    Args:
        artifact_id: ``persistence.models.Artifact`` primary key. This is the
            *artifact* id space, not the domain-entity id space — the same
            space the trace graph and the ``resources/read`` URIs use.
        ctx: Caller identity. Tenant isolation is enforced by
            ``traceability.service.resolve_artifacts``, which only ever returns
            ids visible to ``ctx.tenant_id``.

    Returns:
        A Markdown string: H1 heading, bullet metadata, one ``##`` section per
        non-empty long-text / JSON field. Always ends with a newline.

    Raises:
        NotFoundError: The artifact does not exist, is not visible to the
            caller's tenant, or has no backing domain row.
    """
    from persistence.middleware import set_request_tenant
    from traceability.service import resolve_artifacts

    set_request_tenant(ctx.tenant_id)
    resolved = resolve_artifacts([artifact_id], tenant_id=ctx.tenant_id)
    if not resolved or not resolved[0].resolved:
        raise NotFoundError(f"Artifact {artifact_id} not found")

    entry = resolved[0]
    entity_type = str(entry.entity_type)
    model = _model_for(entity_type)
    if model is None:
        raise NotFoundError(f"Artifact {artifact_id} not found")

    row = model.objects.filter(pk=entry.entity_id).first()
    if row is None:
        raise NotFoundError(f"Artifact {artifact_id} not found")

    heading = ""
    for candidate in _TITLE_FIELDS:
        value = getattr(row, candidate, "")
        if value:
            heading = str(value)
            break
    if not heading:
        heading = f"{entity_type} {entry.entity_id}"

    lines: list[str] = [f"# {heading}", ""]
    # "Artifact Type" instead of the plan's "Type": a domain row usually has
    # its own ``type`` column (Requirement.type = SyReq/UseCase/...), and two
    # bullets labelled "Type" would make the document ambiguous.
    lines.append(f"- **Artifact Type:** {entity_type}")
    lines.append(f"- **Artifact ID:** {entry.artifact_id}")

    # Status is no longer a column on the ten workflow-tracked types
    # (Datenmodell-Konsolidierung Phase 1); it is projected from the engine so
    # a specification document still states where the artifact stands.
    if not any(field.name == "status" for field in row._meta.fields):
        status = _workflow_status(entity_type, entry.entity_id)
        if status:
            lines.append(f"- **Status:** {status}")

    sections: list[tuple[str, str]] = []
    for field in row._meta.fields:
        if field.name in _HIDDEN_FIELDS:
            continue
        if field.name in _TITLE_FIELDS and str(getattr(row, field.name, "")) == heading:
            continue
        if isinstance(field, models.JSONField):
            # Read the raw value: ``str(dict)`` is a Python repr, not JSON.
            rendered = _render_json(getattr(row, field.name, None))
            if rendered:
                sections.append((_label(field), rendered))
            continue
        value = _display(row, field)
        if not value:
            continue
        # TextField must be checked before the scalar branch: a long text
        # column must never collapse into a one-line bullet.
        if isinstance(field, models.TextField):
            sections.append((_label(field), value))
        elif isinstance(field, _SCALAR_FIELD_TYPES):
            lines.append(f"- **{_label(field)}:** {value}")

    for label, value in sections:
        lines.extend(["", f"## {label}", "", value])

    return "\n".join(lines) + "\n"


def _render_json(value: Any) -> str:
    """Return *value* as a fenced JSON block, or ``""`` for empty containers.

    JSON columns carry structured content (``acceptance_criteria_items``,
    ``preconditions``) that a reader needs verbatim; ``sort_keys`` keeps the
    output deterministic for a given payload.
    """
    try:
        parsed = json.loads(value) if isinstance(value, str) else value
    except (TypeError, ValueError):
        parsed = value
    if not parsed:
        return ""
    return "```json\n" + json.dumps(parsed, indent=2, sort_keys=True, default=str) + "\n```"


__all__ = ["ARTIFACT_MARKDOWN_MIME", "render_artifact_markdown"]
