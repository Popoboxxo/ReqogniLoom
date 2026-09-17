"""Output formatters for RequirementBundleQueryService results (Plan 1 Task 3).

Three formats, matching the design spec's §5 raw-mode decision:
  - JSON: default, for REST/MCP/UI consumption.
  - Markdown: hierarchical, token-efficient (also the compressed-mode default
    in a later plan).
  - CSV: flat, one row per requirement, denormalized with a
    found_under_element_id column since CSV cannot express hierarchy.
"""
from __future__ import annotations

import csv
import datetime
import decimal
import io
import uuid
from typing import Any, Dict

from application.csv_safety import neutralize_csv_formula
from application.requirement_bundle_service import BundleItem, BundleResult


def _json_safe(value: Any) -> Any:
    """Coerce a raw ORM column value into something ``json.dumps`` accepts.

    ``BundleItem.fields`` comes straight out of ``QuerySet.values()``, so it
    carries native Python types: ``uuid.UUID`` for ``id``/``workspace_id`` and
    ``datetime`` for ``created_at``/``modified_at``. DRF's JSONRenderer
    encodes those, but the MCP transport does not — ``protocol_handler`` calls
    stdlib ``json.dumps(result.data)`` directly, which raises ``TypeError:
    Object of type UUID is not JSON serializable`` and surfaces as an
    unhandled 500 on the tool's *default* invocation. Normalising here (rather
    than at either transport) keeps both surfaces on one representation.
    """
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, (datetime.datetime, datetime.date, datetime.time)):
        return value.isoformat()
    if isinstance(value, decimal.Decimal):
        return float(value)
    return value


def _csv_safe(value: Any) -> Any:
    """Neutralise a spreadsheet formula in a CSV cell (CSV injection).

    SYSTEMAUDIT-2026-08-27 AP-6 L-4: thin wrapper around the shared
    :func:`application.csv_safety.neutralize_csv_formula` (same trigger set,
    same mitigation, also used by
    :func:`application.export_service._csv_cell`). Any *string* cell starting
    with ``=``, ``+``, ``-``, ``@``, TAB or CR is prefixed with a single
    quote so Excel/LibreOffice treat it as literal text. Requirement
    titles/descriptions are free text written by any editor-role tenant user
    and this bundle is served over an authenticated ``text/csv`` REST
    endpoint, so an unescaped ``=cmd|'/c calc'!A1`` title would execute on
    whoever opens the export.
    """
    return neutralize_csv_formula(value)


def _item_to_dict(item: BundleItem) -> Dict[str, Any]:
    return {
        "requirement_id": str(item.requirement_id),
        "found_under_element_id": str(item.found_under_element_id),
        "depth": item.depth,
        "fields": {k: _json_safe(v) for k, v in item.fields.items()},
    }


def format_bundle_json(result: BundleResult) -> Dict[str, Any]:
    """Return a JSON-ready dict: {"items": [...], "truncated_at_depth": bool}.

    Every value in the payload is guaranteed ``json.dumps``-serialisable (see
    :func:`_json_safe`) — the MCP transport serialises with the stdlib
    encoder, not DRF's.
    """
    return {
        "items": [_item_to_dict(item) for item in result.items],
        "truncated_at_depth": result.truncated_at_depth,
    }


def format_bundle_markdown(result: BundleResult) -> str:
    """Render the bundle as hierarchical Markdown, grouped by
    found_under_element_id in the order items were returned (already
    depth-ordered by the query)."""
    lines = ["# Requirement Bundle"]
    if result.truncated_at_depth:
        lines.append("\n> **Note:** results truncated at the maximum depth cap.")

    current_group: "str | None" = None
    for item in result.items:
        group_key = str(item.found_under_element_id)
        if group_key != current_group:
            lines.append(f"\n## Element {group_key} (depth {item.depth})")
            current_group = group_key
        title = _json_safe(item.fields.get("title", str(item.requirement_id)))
        lines.append(f"\n### {title}")
        for field_name, value in item.fields.items():
            if field_name == "title":
                continue
            lines.append(f"- **{field_name}**: {_json_safe(value)}")
    return "\n".join(lines) + "\n"


def format_bundle_csv(result: BundleResult) -> str:
    """Render the bundle as flat CSV: one row per requirement.

    Column order: requirement_id, found_under_element_id, depth, then every
    field key present across all items (union, sorted alphabetically), so a
    bundle whose items carry heterogeneous field sets (filter_mode='custom'
    with a field only some requirement types have) still produces one
    consistent header row.

    String cells are formula-neutralised before writing (see
    :func:`_csv_safe`) — the output is served directly as ``text/csv`` and
    opened in spreadsheet applications.
    """
    buffer = io.StringIO()
    field_names: "list[str]" = []
    seen = set()
    for item in result.items:
        for key in item.fields:
            if key not in seen:
                seen.add(key)
                field_names.append(key)

    header = ["requirement_id", "found_under_element_id", "depth"] + sorted(field_names)
    writer = csv.DictWriter(buffer, fieldnames=header)
    writer.writeheader()
    for item in result.items:
        row = {
            "requirement_id": str(item.requirement_id),
            "found_under_element_id": str(item.found_under_element_id),
            "depth": item.depth,
        }
        row.update(
            {k: _csv_safe(_json_safe(item.fields.get(k, ""))) for k in field_names}
        )
        writer.writerow(row)
    return buffer.getvalue()


__all__ = ["format_bundle_json", "format_bundle_markdown", "format_bundle_csv"]
