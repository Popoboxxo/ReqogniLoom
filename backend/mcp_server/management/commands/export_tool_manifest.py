"""Emit the canonical MCP tool manifest — the single source of truth every
agent-template/plugin generator downstream reads from, instead of each
maintaining its own copy of the tool list by hand."""
import json
from pathlib import Path
from typing import Any, Dict, List

from django.core.management.base import BaseCommand

from mcp_server.tool_registry import ToolRegistry, _WRITE_TOOL_PREFIXES

# Find the repo root by looking for VERSION file, trying multiple parent levels
# Local dev: backend/mcp_server/management/commands/export_tool_manifest.py → parents[4]
# Docker dev: /app/mcp_server/management/commands/export_tool_manifest.py → parents[3]
def _find_repo_root() -> Path:
    current = Path(__file__).resolve()
    for i in range(5):
        candidate = current.parents[i] / "VERSION"
        if candidate.exists():
            return current.parents[i]
    # Fallback to parents[4] for local, parents[3] for Docker
    return current.parents[4]

REPO_ROOT = _find_repo_root()
DEFAULT_OUT = REPO_ROOT / "docs" / "agent-templates" / "tool-manifest.json"


def _is_write_tool(tool_name: str) -> bool:
    return any(
        tool_name == p or tool_name.startswith(f"{p}.")
        for p in _WRITE_TOOL_PREFIXES
    )


def build_manifest() -> Dict[str, Any]:
    import os
    # Try to read VERSION file first; fall back to APP_VERSION env var (set at Docker build time)
    version_file = REPO_ROOT / "VERSION"
    if version_file.exists():
        version = version_file.read_text(encoding="utf-8").strip()
    else:
        version = os.environ.get("APP_VERSION", "unknown")

    registry = ToolRegistry()
    registry._ensure_groups()  # populates registry._groups; no DB access, pure schema build

    tools: List[Dict[str, Any]] = []
    seen_group_ids: set[int] = set()
    seen_names: set[str] = set()
    for prefix, group in registry._groups.items():
        if id(group) in seen_group_ids:
            continue
        seen_group_ids.add(id(group))
        if not hasattr(group, "get_tool_schemas"):
            continue
        for schema in group.get_tool_schemas():
            name = schema.get("name", "")
            if name in seen_names:
                continue
            seen_names.add(name)
            tools.append(
                {
                    "name": name,
                    "prefix": name.split(".", 1)[0] if "." in name else name,
                    "is_write": _is_write_tool(name),
                    "description": schema.get("description", ""),
                    "inputSchema": schema.get("inputSchema", {}),
                }
            )

    tools.sort(key=lambda t: t["name"])
    return {
        "generated_from": f"reqogniloom=={version}",
        "tool_count": len(tools),
        "tools": tools,
    }


class Command(BaseCommand):
    help = "Export the canonical MCP tool manifest (docs/agent-templates/tool-manifest.json)."

    def add_arguments(self, parser):
        parser.add_argument("--out", default=str(DEFAULT_OUT))

    def handle(self, *args, **options):
        manifest = build_manifest()
        out_path = Path(options["out"])
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        self.stdout.write(
            self.style.SUCCESS(f"Wrote {manifest['tool_count']} tools to {out_path}")
        )
