"""Tool catalogue for the full ReqogniLoom MCP surface.

The plugin is a thin client over ReqogniLoom's native MCP server: every
operation is a ``tools/call`` against the same 248-tool surface the rest of the
ecosystem uses (measured 2026-10-18, server ``1.8.0-beta.21``: 248 tools,
39 groups). Two things this module adds on top of the raw list:

1. **A runtime catalogue.** :func:`fetch_catalogue` reads ``tools/list`` from
   the configured server and classifies every entry, cached per server with a
   TTL. Nothing is hardcoded: a server-side tool added tomorrow shows up in the
   dashboard without touching this plugin.

2. **A risk classification, because MCP does not ship one.** ``tools/list``
   returns ``name``/``description``/``inputSchema`` — there is no ``is_write``
   flag on the wire (the repo's generated ``docs/agent-templates/tool-manifest.json``
   has one, but that is a build artifact, not the protocol). The dashboard needs
   to know, per tool, whether it needs a confirmation dialog (state change),
   a plain spinner (an LLM/expensive computation that mutates nothing), or
   nothing at all (a read). :func:`classify` derives that from the tool name —
   deterministically and testably, not by guesswork at runtime:

   * ``mutate``  — changes server state (create/update/delete/link/approve/…);
   * ``compute`` — runs an LLM or a heavy analysis without changing state
     (``requirement.validate``, ``traceability.coverage``, …);
   * ``read``    — everything else.

   ``tests/test_tools_catalog.py`` pins this against the repo manifest (248
   tools) with two invariants: no tool the server marks as a write is classified
   ``read``, and no tool the server marks as a read is classified ``mutate`` or
   ``compute``. Classification drift therefore fails in CI instead of surfacing
   as a missing confirmation dialog.
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

#: Seconds a fetched catalogue stays fresh in process memory. Short enough that
#: a server upgrade shows up on its own, long enough that opening a few dashboard
#: views does not re-fetch 248 tool schemas every time.
CATALOGUE_TTL_SECONDS = 300

#: Verb segments (single words and whole compound verbs) that mark a tool as
#: state-changing. Calibrated against the repo's ``tool-manifest.json``: with the
#: ``*_EXACT`` sets below, all 248 tools classify identically to the server's own
#: write/read split (invariant-tested, see ``tests/test_tools_catalog.py``).
MUTATE_VERBS = frozenset(
    {
        "create", "update", "delete", "set", "reset", "link", "unlink", "transition",
        "approve", "reject", "accept", "formalize", "write", "promote", "import", "apply",
        "rollback", "revoke", "add", "remove", "start", "stop", "complete", "deactivate",
        "activate", "suspend", "close", "abandon", "outdate", "reactivate", "mark", "waive",
        "replay", "deprecate", "reorder", "forget", "commit", "restore", "generate", "derive",
        "decompose", "seed", "publish", "finalize", "assign", "grant", "rename", "merge",
        "split", "archive", "reply", "clear", "answer", "chat", "consolidate",
        # compound verbs — the verb segment as a whole, not a single word
        "report_results", "run_create", "run_complete", "run_report_results", "mark_reviewed",
        "derive_requirements", "derive_from_requirement", "create_version", "create_manual",
        "decompose_commit", "request_changes", "remember_interaction", "backup_create",
    }
)

#: State-changing tools whose verb does not say so.
MUTATE_EXACT = frozenset(
    {
        "requirement.acceptance_criteria.check",  # sets fulfilled/text (#1288)
        "comment.resolve",
        "memory.forget",  # deletes a memory entry
    }
)

#: Non-mutating tools the server nevertheless gates like writes — because they
#: drive an LLM call, are admin-only, or produce a suggestion. They get a spinner
#: and a note in the UI, never a "this changes data" confirmation.
COMPUTE_EXACT = frozenset(
    {
        "memory.ask", "memory.overview", "memory.settings", "memory.projection",
        "memory.export",
        "requirement.validate", "requirement.check_consistency_status",
        "requirement.suggest_level", "requirement.decompose",
        "traceability.coverage", "traceability.vcrm", "traceability.suggest_links",
        "context.related", "attribute_definition.count_usages", "audit.se_audit",
        "interview.grounding_context", "attribute_migration.dry_run",
        "attribute_definition.export", "attribute_definition.export_workspace",
        "ai_derivation.decompose_requirement_next_level",
        "ai_derivation.suggest_architecture_for_requirement",
        "ai_derivation.derive_adr_from_decision",
        "ai_derivation.derive_glossary_from_workspace",
        "ai_derivation.derive_requirements_from_need",
        "ai_derivation.derive_risks_from_architecture",
    }
)

#: Reads whose verb would otherwise read as a write.
READ_EXACT = frozenset({"workspace.resolve_references", "attribute_migration.plan"})

#: Tools that decide a *human* question — a proposal, a review, an approval.
#: The server refuses these for an agent principal (``PERMISSION_DENIED``: an
#: agent may not accept its own proposal), so the plugin needs the per-server
#: ``user_api_key`` for them and says so instead of failing opaquely.
HUMAN_TOOLS = frozenset(
    {
        "review.approve",
        "review.reject",
        "review.request_changes",
        "suggestion.accept",
        "suggestion.reject",
        "main_goal.approve",
    }
)

#: Tools that destroy or irreversibly reshape data. They additionally require
#: the typed confirmation (the user types the tool name) in the dashboard.
DESTRUCTIVE_TOOLS = frozenset(
    {
        "workspace.delete",
        "workspace.close",
        "admin.restore",
        "attribute_migration.apply",
        "attribute_migration.rollback",
        "attribute_definition.reset",
        "link_type.reset",
        "events.dlq_replay",
        "permissions.revoke",
        "user.deactivate",
        "user.suspend_role",
        "user.revoke_tenant_admin",
    }
)

#: Any tool whose name ends in this is destructive, named in the set or not.
DESTRUCTIVE_SUFFIX = ".delete"

#: Risk classes used by the write gate.
RISK_NONE = "none"
RISK_NORMAL = "normal"
RISK_DESTRUCTIVE = "destructive"

CLASS_READ = "read"
CLASS_COMPUTE = "compute"
CLASS_MUTATE = "mutate"

#: Group prefix assumed for a tool name without a dot (defensive only).
_UNGROUPED = "other"


# --------------------------------------------------------------------------
# classification
# --------------------------------------------------------------------------


def verb_of(tool_name: str) -> str:
    """The action segment of ``group.action`` (``a.b.c`` keeps its dots)."""
    parts = tool_name.split(".", 1)
    return parts[1] if len(parts) > 1 else tool_name


def group_of(tool_name: str) -> str:
    """The group prefix of ``group.action``."""
    parts = tool_name.split(".", 1)
    return parts[0] if len(parts) > 1 else _UNGROUPED


def classify(tool_name: str) -> str:
    """``read`` | ``compute`` | ``mutate`` — see the module docstring."""
    if tool_name in READ_EXACT:
        return CLASS_READ
    if tool_name in COMPUTE_EXACT:
        return CLASS_COMPUTE
    if tool_name in MUTATE_EXACT:
        return CLASS_MUTATE
    verb = verb_of(tool_name).replace(".", "_")
    candidates = {verb} | set(verb.split("_"))
    return CLASS_MUTATE if candidates & MUTATE_VERBS else CLASS_READ


def is_mutating(tool_name: str) -> bool:
    return classify(tool_name) == CLASS_MUTATE


def is_compute(tool_name: str) -> bool:
    return classify(tool_name) == CLASS_COMPUTE


def requires_human(tool_name: str) -> bool:
    """True when the tool decides a human question and needs the user key."""
    return tool_name in HUMAN_TOOLS


def is_destructive(tool_name: str) -> bool:
    return tool_name in DESTRUCTIVE_TOOLS or tool_name.endswith(DESTRUCTIVE_SUFFIX)


def risk_class(tool_name: str) -> str:
    """``none`` (read/compute) | ``normal`` | ``destructive`` (typed confirm)."""
    if classify(tool_name) != CLASS_MUTATE:
        return RISK_NONE
    return RISK_DESTRUCTIVE if is_destructive(tool_name) else RISK_NORMAL


# --------------------------------------------------------------------------
# arguments: validation, canonical form, confirmation token
# --------------------------------------------------------------------------


def canonical_arguments(arguments: Optional[Dict[str, Any]]) -> str:
    """Stable JSON for hashing and comparison (sorted keys, no whitespace)."""
    return json.dumps(arguments or {}, sort_keys=True, separators=(",", ":"), default=str)


def confirm_token(server_id: str, tool_name: str, arguments: Optional[Dict[str, Any]]) -> str:
    """Token binding preview and execution to *exactly* server+tool+arguments.

    Deliberately not a security boundary — the dashboard plugin has no
    credential of its own and shares the host's session cookie, so this cannot
    authenticate a browser. It is an anti-fat-finger guard that lives in the
    backend (not in the browser) so the UI cannot skip the preview step by
    accident: an argument set that changed between preview and execution
    invalidates the token.
    """
    material = f"{server_id}|{tool_name}|{canonical_arguments(arguments)}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def declared_properties(input_schema: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """The ``properties`` map of a tool's input schema (``{}`` when absent)."""
    if not isinstance(input_schema, dict):
        return {}
    properties = input_schema.get("properties")
    return properties if isinstance(properties, dict) else {}


def declared_parameter_names(input_schema: Optional[Dict[str, Any]]) -> List[str]:
    return sorted(declared_properties(input_schema).keys())


def required_parameters(input_schema: Optional[Dict[str, Any]]) -> List[str]:
    if not isinstance(input_schema, dict):
        return []
    required = input_schema.get("required")
    return [str(name) for name in required] if isinstance(required, list) else []


def validate_arguments(
    input_schema: Optional[Dict[str, Any]], arguments: Optional[Dict[str, Any]]
) -> List[str]:
    """Problems with one argument set, as readable strings (empty = fine).

    Checks what the schema declares: missing required parameters, empty values
    for required parameters, an unknown parameter name (a likely typo — the
    server rejects unknown names for most tools), and a scalar type mismatch.

    Deliberately *not* checked: parameters the server accepts without declaring
    them (a known backend finding, #1376). The UI must not offer them, and this
    validator must not encourage passing them.
    """
    problems: List[str] = []
    props = declared_properties(input_schema)
    args = arguments or {}
    for name in required_parameters(input_schema):
        if name not in args:
            problems.append(f"missing required parameter '{name}'")
        elif args[name] in ("", None):
            problems.append(f"required parameter '{name}' is empty")
    for name, value in args.items():
        if name not in props:
            problems.append(f"unknown parameter '{name}'")
            continue
        expected = props[name].get("type") if isinstance(props[name], dict) else None
        if expected == "string" and not isinstance(value, str):
            problems.append(f"parameter '{name}' expects a string")
        elif expected == "boolean" and not isinstance(value, bool):
            problems.append(f"parameter '{name}' expects true/false")
        elif expected == "integer" and not isinstance(value, int):
            problems.append(f"parameter '{name}' expects an integer")
        elif expected == "number" and not isinstance(value, (int, float)):
            problems.append(f"parameter '{name}' expects a number")
        elif expected == "array" and not isinstance(value, list):
            problems.append(f"parameter '{name}' expects a list")
        elif expected == "object" and not isinstance(value, dict):
            problems.append(f"parameter '{name}' expects an object")
    return problems


def summarise_arguments(
    arguments: Optional[Dict[str, Any]], *, limit: int = 3, max_length: int = 120
) -> str:
    """Compact ``k=v`` rendering of the arguments, for the confirm dialog.

    Empty values are skipped (they carry no meaning in a summary) and the result
    is bounded: a confirmation dialog must stay readable.
    """
    parts: List[str] = []
    args = arguments or {}
    for key in sorted(args.keys()):
        value = args[key]
        if value in ("", None, [], {}):
            continue
        if isinstance(value, (dict, list)):
            rendered = json.dumps(value, ensure_ascii=False, default=str)
        else:
            rendered = str(value)
        if len(rendered) > 40:
            rendered = rendered[:37] + "…"
        parts.append(f"{key}={rendered}")
        if len(parts) >= limit:
            break
    summary = " ".join(parts)
    return summary if len(summary) <= max_length else summary[: max_length - 1] + "…"


# --------------------------------------------------------------------------
# catalogue (tools/list, cached)
# --------------------------------------------------------------------------

#: server key -> (fetched_at_epoch, payload). In-process only: the dashboard's
#: handlers and the slash command share the host process; a fresh process simply
#: fetches once.
_CATALOGUE_CACHE: Dict[str, Tuple[float, Dict[str, Any]]] = {}


def invalidate(server_key: Optional[str] = None) -> None:
    """Drop the cached catalogue (one server, or all of them)."""
    if server_key is None:
        _CATALOGUE_CACHE.clear()
    else:
        _CATALOGUE_CACHE.pop(server_key, None)


def describe_tool(tool: Dict[str, Any]) -> Dict[str, Any]:
    """One catalogue entry as the dashboard consumes it."""
    name = str(tool.get("name") or "")
    schema = tool.get("inputSchema") if isinstance(tool.get("inputSchema"), dict) else {}
    tool_class = classify(name)
    return {
        "name": name,
        "group": group_of(name),
        "description": str(tool.get("description") or ""),
        "class": tool_class,
        "risk": risk_class(name),
        "requires_human": requires_human(name),
        "destructive": is_destructive(name),
        "required": required_parameters(schema),
        "parameters": declared_parameter_names(schema),
        "input_schema": schema,
    }


def build_catalogue(raw_tools: Sequence[Dict[str, Any]], *, server_key: str) -> Dict[str, Any]:
    """Assemble the catalogue payload from a raw ``tools/list`` result."""
    described = [describe_tool(tool) for tool in raw_tools if isinstance(tool, dict)]
    described.sort(key=lambda entry: entry["name"])
    groups: Dict[str, int] = {}
    for entry in described:
        groups[entry["group"]] = groups.get(entry["group"], 0) + 1
    counts = {CLASS_READ: 0, CLASS_COMPUTE: 0, CLASS_MUTATE: 0}
    for entry in described:
        counts[entry["class"]] = counts.get(entry["class"], 0) + 1
    return {
        "server": server_key,
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "tool_count": len(described),
        "group_count": len(groups),
        "counts": counts,
        "groups": [{"name": name, "tool_count": count} for name, count in sorted(groups.items())],
        "tools": described,
    }


def fetch_catalogue(
    client: Any, *, server_key: Optional[str] = None, refresh: bool = False
) -> Dict[str, Any]:
    """The catalogue of one server, from cache or from ``tools/list``.

    ``client`` is any object with ``tools_list()`` / ``base_url`` — the
    ReqogniLoom client, or a double in tests. Errors propagate as
    ``ReqogniLoomError``; the callers (dashboard API, slash command) render them.
    """
    key = server_key or getattr(client, "server_id", None) or getattr(client, "base_url", "?")
    now = time.monotonic()
    cached = _CATALOGUE_CACHE.get(key)
    if cached is not None and not refresh and (now - cached[0]) < CATALOGUE_TTL_SECONDS:
        payload = dict(cached[1])
        payload["cached"] = True
        return payload
    raw = client.tools_list()
    payload = build_catalogue(raw, server_key=str(key))
    payload["cached"] = False
    _CATALOGUE_CACHE[key] = (now, payload)
    return payload


def find_tool(catalogue: Dict[str, Any], tool_name: str) -> Optional[Dict[str, Any]]:
    for entry in catalogue.get("tools", []):
        if entry.get("name") == tool_name:
            return entry
    return None
