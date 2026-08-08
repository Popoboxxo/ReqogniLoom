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
import io
from typing import Any, Dict

from application.requirement_bundle_service import BundleItem, BundleResult


def _item_to_dict(item: BundleItem) -> Dict[str, Any]:
    return {
        "requirement_id": str(item.requirement_id),
        "found_under_element_id": str(item.found_under_element_id),
        "depth": item.depth,
        "fields": dict(item.fields),
    }


def format_bundle_json(result: BundleResult) -> Dict[str, Any]:
    """Return a JSON-ready dict: {"items": [...], "truncated_at_depth": bool}."""
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
        title = item.fields.get("title", str(item.requirement_id))
        lines.append(f"\n### {title}")
        for field_name, value in item.fields.items():
            if field_name == "title":
                continue
            lines.append(f"- **{field_name}**: {value}")
    return "\n".join(lines) + "\n"


def format_bundle_csv(result: BundleResult) -> str:
    """Render the bundle as flat CSV: one row per requirement.

    Column order: requirement_id, found_under_element_id, depth, then every
    field key present across all items (union, stable-sorted), so a bundle
    whose items carry heterogeneous field sets (filter_mode='custom' with a
    field only some requirement types have) still produces one consistent
    header row.
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
        row.update({k: item.fields.get(k, "") for k in field_names})
        writer.writerow(row)
    return buffer.getvalue()


__all__ = ["format_bundle_json", "format_bundle_markdown", "format_bundle_csv"]
