"""Emit the canonical MCP tool manifest — the single source of truth every
agent-template/plugin generator downstream reads from, instead of each
maintaining its own copy of the tool list by hand."""
import json
from collections import Counter
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand

from mcp_server.tool_registry import ToolRegistry

#: Location of the manifest relative to whichever ancestor directory holds it.
_MANIFEST_SUFFIX = Path("docs") / "agent-templates" / "tool-manifest.json"


def _find_repo_root() -> Path:
    """Return the directory that holds ``VERSION`` / ``docs/agent-templates``.

    Two layouts have to work with the same code:

    * host — ``<repo>/backend/mcp_server/management/commands/`` (root =
      ``parents[4]``), where both ``VERSION`` and ``docs/`` sit at the repo root;
    * container — ``/app/mcp_server/management/commands/`` (root =
      ``parents[3]``), where ``backend/`` *is* ``/app``, there is no ``VERSION``
      file, and ``docs/`` is bind-mounted at ``/app/docs``.

    Probing for the manifest directory as well as ``VERSION`` keeps
    ``DEFAULT_OUT`` pointing at a writable, correct path inside Docker, where
    the old VERSION-only probe fell through to ``parents[4] == "/"`` and made
    the documented ``manage.py export_tool_manifest`` fix unrunnable there
    (issue #434).
    """
    current = Path(__file__).resolve()
    for ancestor in current.parents:
        if (ancestor / _MANIFEST_SUFFIX).is_file() or (ancestor / "VERSION").is_file():
            return ancestor
    # Last resort: the host layout.
    return current.parents[4]


REPO_ROOT = _find_repo_root()
DEFAULT_OUT = REPO_ROOT / _MANIFEST_SUFFIX


def collect_raw_tool_schemas(
    registry: ToolRegistry | None = None,
) -> list[dict[str, Any]]:
    """Collect every group's tool schemas *before* any name-based dedup.

    Keeping this step separate is what makes the drift gate able to see a
    collision: comparing the committed manifest against a builder that silently
    drops duplicates leaves both sides agreeing on a loss (API-005). A group
    object registered under more than one prefix is still visited once, which
    is group identity dedup — not tool-name dedup.
    """
    if registry is None:
        registry = ToolRegistry()
        registry._ensure_groups()  # populates registry._groups; no DB access, pure schema build

    schemas: list[dict[str, Any]] = []
    seen_group_ids: set[int] = set()
    for group in registry._groups.values():
        if id(group) in seen_group_ids:
            continue
        seen_group_ids.add(id(group))
        if not hasattr(group, "get_tool_schemas"):
            continue
        schemas.extend(group.get_tool_schemas())
    return schemas


def build_manifest() -> dict[str, Any]:
    import os
    # Try to read VERSION file first; fall back to APP_VERSION env var (set at Docker build time)
    version_file = REPO_ROOT / "VERSION"
    if version_file.exists():
        version = version_file.read_text(encoding="utf-8").strip()
    else:
        version = os.environ.get("APP_VERSION", "unknown")

    registry = ToolRegistry()
    registry._ensure_groups()
    raw_schemas = collect_raw_tool_schemas(registry)

    # API-005: fail loudly on a collision instead of silently shadowing a tool.
    # ToolGroupRouter.route() returns the first prefix match, so a duplicate
    # name would be unreachable at runtime while this gate stayed green.
    counts = Counter(schema.get("name", "") for schema in raw_schemas)
    duplicates = sorted(name for name, count in counts.items() if count > 1)
    if duplicates:
        raise ValueError(
            "Duplicate MCP tool name(s) emitted by more than one group: "
            + ", ".join(duplicates)
            + ". Shadowed tools are unreachable at runtime; fix the registry "
            "instead of deduplicating them in the manifest."
        )

    tools: list[dict[str, Any]] = []
    for schema in raw_schemas:
        name = schema.get("name", "")
        tools.append(
            {
                "name": name,
                "prefix": name.split(".", 1)[0] if "." in name else name,
                "is_write": registry._is_write_tool(name),
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

        # Write manifest to file
        manifest_json = json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"
        out_path.write_text(manifest_json, encoding="utf-8")

        # Self-validate: round-trip through json.loads() to ensure valid JSON
        try:
            validated = json.loads(out_path.read_text(encoding="utf-8"))
            if validated.get("tool_count") != len(validated.get("tools", [])):
                raise ValueError(
                    f"Manifest validation failed: tool_count ({validated['tool_count']}) "
                    f"does not match tools array length ({len(validated.get('tools', []))})"
                )
        except json.JSONDecodeError as e:
            raise RuntimeError(
                f"Manifest JSON validation failed after write to {out_path}: {e}"
            ) from e

        self.stdout.write(
            self.style.SUCCESS(f"Wrote {manifest['tool_count']} tools to {out_path}")
        )
