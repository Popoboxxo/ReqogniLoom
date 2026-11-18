"""
COMP-MC-002 ToolRegistry — Tool discovery, routing, auth/RBAC/preset enforcement.

leaf_id : COMP-MC-002
req_id  : REQ-L2-MC-006 (API-key auth), REQ-L2-MC-007 (RBAC),
          REQ-L2-MC-008 (preset-based tool visibility),
          REQ-L2-MC-009 (direct ApplicationService access)

Responsibilities:
- Validate API key via AuthAndTenancy (IF-MC-EXT-OUT-002).
- Build AuthContext from validated identity claims + role resolution.
- Enforce RBAC against the workspace a call targets, for writes AND reads
  (IF-MC-EXT-OUT-002; read scoping added by Systemaudit 2026-08-29 §6.5 —
  see ``mcp_server/workspace_scope.py``).
- Check preset-based tool visibility via PresetConfigEngine (IF-MC-EXT-OUT-004).
- Route tool calls to the correct ToolGroup (IF-MC-INT-002..005).
- Return ToolResult from the group or a structured error.

Interface contracts implemented:
  IF-MC-INT-001  — inbound: dispatch_request(tool_name, params, api_key)
  IF-MC-EXT-OUT-002 — outbound: AuthAndTenancy API-key validation
  IF-MC-EXT-OUT-004 — outbound: PresetConfigEngine preset query

Architecture:
  docs/se/L1/Gesamtsystem/L2/McpServerSystem/Components/
    COMP-MC-002_ToolRegistry/
      L3_COMP-MC-002_ToolRegistry_Architecture.md

ADR-L3-MC002-01: Three-layer auth (API-key → RBAC → Preset) sequential.
ADR-L3-MC002-02: Preset caching with TTL.
ADR-L3-MC002-03: Prefix-based tool routing.
"""
from __future__ import annotations

import hashlib
import logging
import time
from collections import OrderedDict
from collections.abc import Callable
from typing import Any, NamedTuple
from uuid import UUID

from auth_tenancy.context import AuthContext, AuthMethod
from auth_tenancy.errors import AuthenticationFailed
from auth_tenancy.models import ROLE_ADMIN
from auth_tenancy.services.authentication import AuthenticationService
from auth_tenancy.services.authorization import (
    AuthorizationService,
    Operation,
    scope_allows,
    scope_denial_reason,
)
from mcp_server.api_key_policy import get_api_key_policy
from mcp_server.protocol_handler import ToolResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tool catalogue filtering + compaction (issue #866).
#
# `tools/list` returns the full 180+-tool catalogue (~100 KB of JSON schemas,
# ~35k tokens), which a client pays for on every session start and which
# pushes coding agents towards their context ceiling. Two levers, both opt-in
# so the default surface is unchanged:
#
#   1. `toolset`/`filter` — request only the subset relevant to the current
#      phase (authoring / verification / auditing / …), or explicit
#      group prefixes / tool names / a free-text search.
#   2. `compact` — trim each tool's prose (description to its first sentence,
#      every JSON-schema `description`/`title`) while keeping the callable
#      contract (types, `required`, `enum`) intact.
#
# `tools/filter` exposes the same mechanism as its own JSON-RPC method and
# also returns the available toolset names, so a client can discover them
# without a second round trip.
# ---------------------------------------------------------------------------

#: Named phase presets -> the tool-group prefixes they include. A prefix is the
#: part before the first "." in a tool name (ADR-L3-MC002-03).
_TOOLSETS: dict[str, tuple[str, ...]] = {
    "core": (
        "requirement", "needs", "architecture", "test",
        "traceability", "artifact", "context", "comment",
    ),
    "authoring": (
        "requirement", "needs", "architecture", "adr", "risk", "issue",
        "glossary", "change_request", "icd", "diagram", "comment", "goal",
        "main_goal",
    ),
    "verification": (
        "requirement", "test", "traceability", "artifact", "context",
        "baseline", "review",
    ),
    "auditing": (
        "audit", "events", "baseline", "traceability", "context", "workspace",
        "admin", "permissions", "user", "attribute_definition",
        "attribute_catalog", "attribute_migration", "link_type",
    ),
    "admin": (
        "workspace", "admin", "permissions", "user", "audit", "events",
        "attribute_definition", "attribute_catalog", "attribute_migration",
        "link_type",
    ),
    "ai": (
        "ai_derivation", "memory", "prompt_template", "prompt_variable",
        "interview", "requirement", "needs", "architecture",
        "requirement_bundle", "goal", "main_goal",
    ),
}

TOOLSET_NAMES: tuple[str, ...] = tuple(_TOOLSETS)

#: JSON-schema keys that are pure prose; stripped in `compact` mode.
_SCHEMA_PROSE_KEYS = ("description", "title")


def tool_prefix(name: str) -> str:
    """Return the group prefix of *name* (the part before the first ".")."""
    return str(name).split(".", 1)[0]


def _strip_schema_prose(node: Any) -> Any:
    """Recursively drop `description`/`title` from a JSON-schema fragment."""
    if isinstance(node, dict):
        return {
            key: _strip_schema_prose(value)
            for key, value in node.items()
            if key not in _SCHEMA_PROSE_KEYS
        }
    if isinstance(node, list):
        return [_strip_schema_prose(item) for item in node]
    return node


def _first_sentence(text: str, limit: int = 160) -> str:
    """Return the first sentence of *text*, capped at *limit* characters."""
    collapsed = " ".join(str(text).split())
    for sep in (". ", ".\n", "! ", "? "):
        idx = collapsed.find(sep)
        if idx != -1:
            collapsed = collapsed[: idx + 1]
            break
    return collapsed if len(collapsed) <= limit else collapsed[: limit - 1].rstrip() + "…"


def compact_tool(tool: dict[str, Any]) -> dict[str, Any]:
    """Return *tool* with its prose trimmed but its callable schema intact.

    Keeps ``name``, a first-sentence ``description`` and the full ``inputSchema``
    minus every ``description``/``title`` (types, ``required`` and ``enum``
    survive, so the tool stays callable).
    """
    compacted: dict[str, Any] = {
        "name": tool.get("name"),
        "description": _first_sentence(tool.get("description") or ""),
    }
    schema = tool.get("inputSchema")
    if isinstance(schema, dict):
        compacted["inputSchema"] = _strip_schema_prose(schema)
    return compacted


def filter_tool_catalogue(
    tools: list[dict[str, Any]],
    *,
    toolset: str | None = None,
    groups: Any | None = None,
    names: Any | None = None,
    search: str | None = None,
) -> list[dict[str, Any]]:
    """Return the subset of *tools* matching the given selectors.

    Selectors combine with AND: a toolset narrows by prefix, an explicit
    ``names`` list then narrows by exact name, and ``search`` matches a
    case-insensitive substring of the name or description.

    Raises:
        ValueError: ``toolset`` is not one of :data:`TOOLSET_NAMES`.
    """
    selected = list(tools)

    prefix_source: tuple[str, ...] | None = None
    if toolset is not None:
        if toolset not in _TOOLSETS:
            raise ValueError(
                f"Unknown toolset '{toolset}'. Known toolsets: "
                f"{', '.join(TOOLSET_NAMES)}."
            )
        prefix_source = _TOOLSETS[toolset]
    elif groups:
        prefix_source = tuple(str(g) for g in groups)
    if prefix_source is not None:
        prefix_set = set(prefix_source)
        selected = [t for t in selected if tool_prefix(t.get("name", "")) in prefix_set]

    if names:
        name_set = {str(n) for n in names}
        selected = [t for t in selected if t.get("name") in name_set]

    if search:
        query = str(search).strip().lower()
        if query:
            selected = [
                t
                for t in selected
                if query
                in f"{t.get('name', '')} {t.get('description') or ''}".lower()
            ]

    return selected


# ---------------------------------------------------------------------------
# Tool policy metadata — single source of truth (R2C-009 / ANPASSEN).
#
# A tool group's security classification used to be declared in eight separate
# module-level collections spread over ~700 lines, while its schemas lived in
# the group class and its construction in a 227-line ``_ensure_groups``. Adding
# one group therefore required >=5 coordinated edits and a reviewer could not
# read a tool's effective tier from a single place.
#
# Each group is now declared exactly once as a :class:`_GroupSpec`: its prefix,
# the factory key that builds it, and all policy metadata for its tools. The
# eight historical collections below are *derived* from those specs at import
# time and kept as module-level aliases so the ~17 tests and the manifest
# drift gate that import them keep working unchanged. Values are algebraically
# identical to the pre-consolidation literals (pinned by
# ``mcp_server/tests/test_tool_registry_policy_consolidation.py``).
#
# Security invariants preserved verbatim:
#   * FAIL-CLOSED default — ``_is_write_tool()`` treats every unknown tool name
#     as WRITE (RBAC-gated). It consults the derived ``_READ_ONLY_TOOL_NAMES``
#     and ``_READ_ONLY_TOOL_SUFFIXES`` only as explicit read exemptions;
#     ``_WRITE_TOOL_PREFIXES`` stays a documented catalogue / test oracle.
#   * ``_GOVERNANCE_*`` narrow the AUTHOR->ADMIN capability tier,
#     ``_INSTANCE_LEVEL_TOOLS`` skip workspace-scoped role narrowing,
#     ``_ALWAYS_VISIBLE_TOOLS`` survive the ApiKey.tool_groups filter, and
#     ``_TENANT_ADMIN_ELEVATED_USER_TOOLS`` bypass the coarse write-RBAC gate
#     only for handlers that re-check tenant-admin themselves.
# ---------------------------------------------------------------------------


class _GroupSpec(NamedTuple):
    """One tool group's construction recipe plus its security policy.

    Attributes:
        prefix: Published tool-name namespace (part before the first ``.``).
        group_key: Key into the factory map in :meth:`ToolRegistry._ensure_groups`;
            groups sharing a key share one instance (REQ-129).
        write_tools: Fully-qualified write-tool names. Concatenated, in spec
            order, into the historical ``_WRITE_TOOL_PREFIXES`` catalogue.
        read_only: Explicit read-exempt tool names (the fail-closed gate's
            allowlist; suffixes handle the rest).
        governance_namespace: Whether this whole namespace is ADMIN-tier.
        governance_tools: Individual ADMIN-tier tools in a mixed namespace.
        instance_level: Tools whose authority is instance/tenant-wide, not
            workspace-scoped.
        always_visible: Tools surviving the ApiKey.tool_groups filter.
        tenant_admin_elevated: user.* tools with a tenant-admin-aware handler.
    """

    prefix: str
    group_key: str
    write_tools: tuple[str, ...] = ()
    read_only: frozenset[str] = frozenset()
    governance_namespace: bool = False
    governance_tools: frozenset[str] = frozenset()
    instance_level: frozenset[str] = frozenset()
    always_visible: frozenset[str] = frozenset()
    tenant_admin_elevated: frozenset[str] = frozenset()


#: Declarative registry of every default tool group and its policy (R2C-009).
#: Order follows the historical ``_ensure_groups`` registration; a shared
#: ``group_key`` (cross_cutting, audit) is what makes several prefixes reuse a
#: single group instance. TOOL MAP: policy fields are the single source for the
#: derived aliases below.
GROUP_SPECS: tuple[_GroupSpec, ...] = (
    _GroupSpec(
        prefix="requirement", group_key="requirement",
        write_tools=(
            "requirement.create",
            "requirement.decompose",
            "requirement.derive",
            "requirement.outdate",
            "requirement.reactivate",
            "requirement.update",
            "requirement.validate",
        ),
        read_only=frozenset({
            "requirement.acceptance_criteria.get",
            "requirement.check_consistency",
            "requirement.get",
            "requirement.query",
        }),
    ),
    _GroupSpec(
        prefix="needs", group_key="needs",
        write_tools=(
            "needs.create",
            "needs.delete",
            "needs.outdate",
            "needs.reactivate",
            "needs.update",
        ),
        read_only=frozenset({
            "needs.get_traces",
            "needs.query",
            "needs.read",
        }),
    ),
    _GroupSpec(
        prefix="architecture", group_key="architecture",
        write_tools=(
            "architecture.create",
            "architecture.decompose_commit",
            "architecture.link",
            "architecture.outdate",
            "architecture.reactivate",
            "architecture.update",
        ),
        read_only=frozenset({
            "architecture.get",
            "architecture.query",
        }),
    ),
    _GroupSpec(
        prefix="test", group_key="test",
        write_tools=(
            "test.create",
            "test.derive_from_requirement",
            "test.link",
            "test.mark_reviewed",
            "test.outdate",
            "test.reactivate",
            "test.run_complete",
            "test.run_create",
            "test.run_report_results",
            "test.update",
        ),
        read_only=frozenset({
            "test.get",
            "test.query",
            "test.run_get",
            "test.run_list",
        }),
    ),
    _GroupSpec(
        prefix="traceability", group_key="cross_cutting",
        write_tools=("traceability.create_link",),
        read_only=frozenset({
            "traceability.query",
            "traceability.query_links",
            "traceability.suggest_links_status",
        }),
    ),
    _GroupSpec(
        prefix="artifact", group_key="cross_cutting",
        write_tools=(
            "artifact.bulk_transition",
            "artifact.bulk_update",
            "artifact.move",
        ),
        read_only=frozenset({
            "artifact.get_tree",
            "artifact.search",
            "artifact.summary",
        }),
    ),
    _GroupSpec(
        prefix="context", group_key="cross_cutting",
        write_tools=(
            "group.add_member",
            "group.create",
            "group.move_member",
            "group.remove_member",
        ),
        read_only=frozenset({
            "allocation.query",
            "context.change_impact",
            "context.test_coverage",
            "group.list",
            "group.members",
        }),
    ),
    _GroupSpec(
        prefix="workspace", group_key="workspace",
        write_tools=(
            "workspace.close",
            "workspace.delete",
            "workspace.reactivate",
        ),
        read_only=frozenset({
            "workspace.get_context",
            "workspace.get_preferences",
            "workspace.list",
            "workspace.llm_system_prompt",
            "workspace.resolve_references",
        }),
        governance_namespace=True,
    ),
    _GroupSpec(
        prefix="permissions", group_key="permissions",
        write_tools=(
            "permissions.revoke",
            "permissions.set_rule",
        ),
        read_only=frozenset({
            "permissions.check",
            "permissions.list",
        }),
        governance_namespace=True,
    ),
    _GroupSpec(
        prefix="admin", group_key="admin",
        write_tools=(
            "admin.backup_create",
            "admin.restore",
        ),
        read_only=frozenset({
            "admin.backup_list",
        }),
        instance_level=frozenset({
            "admin.backup_create",
            "admin.backup_list",
            "admin.restore",
        }),
        governance_namespace=True,
    ),
    _GroupSpec(
        prefix="audit", group_key="audit",
        write_tools=("audit.waive_finding",),
        read_only=frozenset({
            "audit.ai_review",
            "audit.query",
            "audit.waivers",
        }),
        governance_tools=frozenset({
            "audit.waive_finding",
        }),
    ),
    _GroupSpec(
        prefix="events", group_key="audit",
        write_tools=("events.dlq_replay",),
        read_only=frozenset({
            "events.dlq_list",
        }),
        governance_namespace=True,
    ),
    _GroupSpec(
        prefix="user", group_key="user",
        write_tools=(
            "user.activate",
            "user.assign_role",
            "user.assign_tenant_admin",
            "user.create",
            "user.deactivate",
            "user.reactivate_role",
            "user.revoke_tenant_admin",
            "user.suspend_role",
        ),
        read_only=frozenset({
            "user.list",
        }),
        tenant_admin_elevated=frozenset({
            "user.activate",
            "user.assign_role",
            "user.assign_tenant_admin",
            "user.create",
            "user.deactivate",
            "user.reactivate_role",
            "user.revoke_tenant_admin",
            "user.suspend_role",
        }),
        governance_namespace=True,
    ),
    _GroupSpec(
        prefix="adr", group_key="adr",
        write_tools=(
            "adr.create",
            "adr.delete",
            "adr.outdate",
            "adr.reactivate",
            "adr.update",
        ),
    ),
    _GroupSpec(
        prefix="risk", group_key="risk",
        write_tools=(
            "risk.create",
            "risk.delete",
            "risk.outdate",
            "risk.reactivate",
            "risk.update",
        ),
    ),
    _GroupSpec(
        prefix="issue", group_key="issue",
        write_tools=(
            "issue.create",
            "issue.delete",
            "issue.outdate",
            "issue.reactivate",
            "issue.update",
        ),
    ),
    _GroupSpec(
        prefix="glossary", group_key="glossary",
        write_tools=(
            "glossary.create",
            "glossary.delete",
            "glossary.outdate",
            "glossary.reactivate",
            "glossary.update",
        ),
    ),
    _GroupSpec(
        prefix="change_request", group_key="change_request",
        write_tools=(
            "change_request.create",
            "change_request.delete",
            "change_request.outdate",
            "change_request.reactivate",
            "change_request.update",
        ),
    ),
    _GroupSpec(
        prefix="prompt_template", group_key="prompt_template",
        write_tools=(
            "prompt_template.create",
            "prompt_template.delete",
            "prompt_template.update",
        ),
        read_only=frozenset({
            "prompt_template.get",
            "prompt_template.list",
        }),
        governance_namespace=True,
    ),
    _GroupSpec(
        prefix="prompt_variable", group_key="prompt_variable",
        write_tools=(
            "prompt_variable.clear",
            "prompt_variable.set",
        ),
        read_only=frozenset({
            "prompt_variable.get",
            "prompt_variable.list",
        }),
        governance_namespace=True,
    ),
    _GroupSpec(
        prefix="ai_derivation", group_key="ai_derivation",
        write_tools=(
            "ai_derivation.decompose_requirement_next_level",
            "ai_derivation.derive_adr_from_decision",
            "ai_derivation.derive_glossary_from_workspace",
            "ai_derivation.derive_requirements_from_need",
            "ai_derivation.derive_risks_from_architecture",
            "ai_derivation.suggest_architecture_for_requirement",
        ),
    ),
    _GroupSpec(
        prefix="diagram", group_key="diagram",
        write_tools=(
            "diagram.create",
            "diagram.outdate",
            "diagram.reactivate",
            "diagram.update",
        ),
        read_only=frozenset({
            "diagram.get",
            "diagram.query",
        }),
    ),
    _GroupSpec(
        prefix="document", group_key="document",
        write_tools=(
            "document.adopt",
            "document.create",
            "document.outdate",
            "document.reactivate",
            "document.transition",
            "document.update",
        ),
        read_only=frozenset({
            "document.diff",
            "document.project",
            "document.projection_status",
            "document.versions",
        }),
    ),
    _GroupSpec(
        prefix="work_item", group_key="work_item",
        write_tools=(
            "work_item.checkpoint",
            "work_item.create",
            "work_item.set_progress",
            "work_item.transition",
            "work_item.update",
        ),
        read_only=frozenset({
            "work_item.resume",
        }),
    ),
    _GroupSpec(
        prefix="milestone", group_key="milestone",
        write_tools=(
            "milestone.bind_baseline",
            "milestone.create",
            "milestone.record_audit",
            "milestone.update",
        ),
        read_only=frozenset({
            "milestone.get",
            "milestone.list",
        }),
    ),
    _GroupSpec(
        prefix="review", group_key="review",
        write_tools=(
            "review.approve",
            "review.reject",
            "review.request_changes",
        ),
        read_only=frozenset({
            "review.list_pending",
        }),
    ),
    _GroupSpec(
        prefix="suggestion", group_key="suggestion",
        read_only=frozenset({
            "suggestion.list",
        }),
    ),
    _GroupSpec(
        prefix="baseline", group_key="baseline",
        write_tools=(
            "baseline.create",
            "baseline.rollback_apply",
            "baseline.rollback_request",
            "baseline.set_tags",
        ),
        read_only=frozenset({
            "baseline.compare",
            "baseline.get",
            "baseline.list",
            "baseline.rollback_preview",
        }),
        governance_namespace=True,
    ),
    _GroupSpec(
        prefix="goal", group_key="goal",
        read_only=frozenset({
            "goal.list_versions",
        }),
    ),
    _GroupSpec(
        prefix="main_goal", group_key="main_goal",
        read_only=frozenset({
            "main_goal.list_versions",
            "main_goal.query",
        }),
    ),
    _GroupSpec(
        prefix="requirement_bundle", group_key="requirement_bundle",
        read_only=frozenset({
            "requirement_bundle.attribute_schema",
            "requirement_bundle.compression_status",
            "requirement_bundle.export",
        }),
    ),
    _GroupSpec(
        prefix="interview", group_key="interview",
        write_tools=(
            "interview.abandon",
            "interview.answer",
            "interview.chat",
            "interview.formalize",
            "interview.grounding_context",
            "interview.set_target",
            "interview.start",
        ),
        read_only=frozenset({
            "interview.get",
            "interview.get_state",
            "interview.list",
            "interview.propose",
        }),
    ),
    _GroupSpec(
        prefix="memory", group_key="memory",
        write_tools=(
            "memory.ask",
            "memory.delete_workspace",
            "memory.export",
            "memory.forget",
            "memory.overview",
            "memory.projection",
            "memory.promote",
            "memory.remember_interaction",
            "memory.settings",
            "memory.write",
        ),
        read_only=frozenset({
            "memory.digest",
            "memory.get",
            "memory.list",
            "memory.query",
            "memory.session_summaries",
        }),
        governance_tools=frozenset({
            "memory.delete_workspace",
            "memory.export",
            "memory.overview",
            "memory.projection",
            "memory.settings",
        }),
    ),
    _GroupSpec(
        prefix="link_type", group_key="link_type",
        read_only=frozenset({
            "link_type.get",
            "link_type.list",
        }),
        governance_namespace=True,
    ),
    _GroupSpec(
        prefix="attribute_definition", group_key="attribute_definition",
        read_only=frozenset({
            "attribute_definition.get",
            "attribute_definition.list",
        }),
        governance_namespace=True,
    ),
    _GroupSpec(
        prefix="attribute_catalog", group_key="attribute_catalog",
        write_tools=(
            "attribute_catalog.add_to_definition",
            "attribute_catalog.create",
            "attribute_catalog.deprecate",
            "attribute_catalog.import",
            "attribute_catalog.reorder",
            "attribute_catalog.update",
        ),
        read_only=frozenset({
            "attribute_catalog.export",
            "attribute_catalog.list",
            "attribute_catalog.search",
        }),
        governance_namespace=True,
    ),
    _GroupSpec(
        prefix="attribute_migration", group_key="attribute_migration",
        write_tools=(
            "attribute_migration.apply",
            "attribute_migration.dry_run",
            "attribute_migration.rollback",
        ),
        read_only=frozenset({
            "attribute_migration.get_run",
            "attribute_migration.list_runs",
            "attribute_migration.plan",
        }),
        governance_namespace=True,
    ),
    _GroupSpec(
        prefix="icd", group_key="icd",
        write_tools=(
            "icd.create",
            "icd.update",
        ),
    ),
    _GroupSpec(
        prefix="comment", group_key="comment",
        write_tools=(
            "comment.create",
            "comment.resolve",
        ),
        read_only=frozenset({
            "comment.list",
        }),
    ),
    _GroupSpec(
        prefix="metrics", group_key="metrics",
        read_only=frozenset({
            "metrics.catalog",
            "metrics.get",
        }),
    ),
    _GroupSpec(
        prefix="tree_display_config", group_key="tree_display_config",
        read_only=frozenset({
            "tree_display_config.get",
        }),
    ),
    _GroupSpec(
        prefix="create_form_definition", group_key="create_form_definition",
        read_only=frozenset({
            "create_form_definition.export",
            "create_form_definition.get",
        }),
    ),
    _GroupSpec(
        prefix="preference", group_key="preference",
        read_only=frozenset({
            "preference.get",
            "preference.registry",
        }),
        governance_tools=frozenset({
            "preference.set_default",
        }),
    ),
    _GroupSpec(
        prefix="quality", group_key="quality",
    ),
    _GroupSpec(
        prefix="summary", group_key="summary",
        write_tools=("summary.refresh",),
        read_only=frozenset({
            "summary.get",
        }),
    ),
    _GroupSpec(
        prefix="resource", group_key="resource",
        read_only=frozenset({
            "resource.list",
            "resource.read",
            "resource.templates_list",
        }),
    ),
    _GroupSpec(
        prefix="prompt", group_key="prompt",
        read_only=frozenset({
            "prompt.get",
            "prompt.list",
        }),
    ),
    _GroupSpec(
        prefix="tool", group_key="tool",
        read_only=frozenset({
            "tool.list_groups",
        }),
        always_visible=frozenset({
            "tool.list_groups",
        }),
    ),
    _GroupSpec(
        prefix="saved_view", group_key="saved_view",
        read_only=frozenset({
            "saved_view.apply",
            "saved_view.list",
        }),
    ),
)


# Derived aliases — the historical module-level collections, now computed once
# from :data:`GROUP_SPECS`. Set-valued aliases are order-independent; the
# ``_WRITE_TOOL_PREFIXES`` tuple is used only for membership/prefix tests, so
# its element order carries no semantics.
_WRITE_TOOL_PREFIXES: tuple[str, ...] = tuple(
    name for spec in GROUP_SPECS for name in spec.write_tools
)
_READ_ONLY_TOOL_NAMES: frozenset[str] = frozenset(
    name for spec in GROUP_SPECS for name in spec.read_only
)
_READ_ONLY_TOOL_SUFFIXES: tuple[str, ...] = (".read", ".query")
_GOVERNANCE_TOOL_NAMESPACES: frozenset[str] = frozenset(
    spec.prefix for spec in GROUP_SPECS if spec.governance_namespace
)
_GOVERNANCE_TOOL_NAMES: frozenset[str] = frozenset(
    name for spec in GROUP_SPECS for name in spec.governance_tools
)
_INSTANCE_LEVEL_TOOLS: frozenset[str] = frozenset(
    name for spec in GROUP_SPECS for name in spec.instance_level
)
_ALWAYS_VISIBLE_TOOLS: frozenset[str] = frozenset(
    name for spec in GROUP_SPECS for name in spec.always_visible
)
_TENANT_ADMIN_ELEVATED_USER_TOOLS: frozenset[str] = frozenset(
    name for spec in GROUP_SPECS for name in spec.tenant_admin_elevated
)

# ---------------------------------------------------------------------------
# Tool → feature-key mapping for preset filtering (REQ-L2-MC-008)
# ---------------------------------------------------------------------------

_TOOL_FEATURE_MAP: dict[str, str] = {
    "requirement.decompose": "llm_decompose",
    "requirement.validate": "llm_validate",
    "architecture.link": "architecture_links",
    "test.link": "test_links",
    "traceability.query": "traceability",
    # #1098: its collection sibling is gated by the same feature key as
    # traceability.query — a preset that disables traceability for a workspace
    # must not leave the link graph enumerable through the new tool.
    "traceability.query_links": "traceability",
    "artifact.get_tree": "artifact_tree",
}


class McpAuthenticationError(Exception):
    """Raised by :meth:`ToolRegistry.list_tools` when the credential is
    missing or invalid, so the caller can surface AUTH_FAILED/401 instead of
    silently returning an empty tool list."""


# ---------------------------------------------------------------------------
# Preset cache (ADR-L3-MC002-02)
# ---------------------------------------------------------------------------


class _PresetCacheEntry:
    """Single preset cache entry with TTL."""

    TTL_SECONDS = 300  # 5 minutes

    def __init__(self, features: dict[str, bool]) -> None:
        self.features = features
        self.expires_at = time.monotonic() + self.TTL_SECONDS

    def is_valid(self) -> bool:
        return time.monotonic() < self.expires_at


class PresetCache:
    """Bounded LRU cache for preset feature flags keyed by workspace_id.

    Entries expire via TTL (:class:`_PresetCacheEntry`) and the total number of
    entries is capped at ``maxsize`` (REQ-108). Once the cap is reached the
    least-recently-used entry is evicted, so the cache cannot grow without bound
    under a large or adversarial set of workspace ids.
    """

    DEFAULT_MAXSIZE = 256

    def __init__(self, maxsize: int = DEFAULT_MAXSIZE) -> None:
        if maxsize <= 0:
            raise ValueError("PresetCache maxsize must be positive")
        self._maxsize = maxsize
        self._cache: OrderedDict[str, _PresetCacheEntry] = OrderedDict()

    def get(self, workspace_id: str) -> dict[str, bool] | None:
        entry = self._cache.get(workspace_id)
        if entry is None:
            return None
        if not entry.is_valid():
            # Drop the stale entry so it does not occupy a cache slot.
            self._cache.pop(workspace_id, None)
            return None
        # Mark as most-recently-used for LRU eviction ordering.
        self._cache.move_to_end(workspace_id)
        return entry.features

    def set(self, workspace_id: str, features: dict[str, bool]) -> None:
        self._cache[workspace_id] = _PresetCacheEntry(features)
        self._cache.move_to_end(workspace_id)
        # Evict least-recently-used entries until within the size bound.
        while len(self._cache) > self._maxsize:
            self._cache.popitem(last=False)

    def invalidate(self, workspace_id: str) -> None:
        self._cache.pop(workspace_id, None)


# ---------------------------------------------------------------------------
# Tool group router (ADR-L3-MC002-03)
# ---------------------------------------------------------------------------


class ToolGroupRouter:
    """Route tool names to ToolGroup instances based on name prefix."""

    def __init__(self, groups: dict[str, Any]) -> None:
        """Initialise with a mapping of prefix → ToolGroup instance."""
        self._groups = groups  # e.g. {"requirement": group, "architecture": group}

    def route(self, tool_name: str) -> tuple[Any | None, str | None]:
        """Return (tool_group, error_code) for *tool_name*.

        Returns:
            (group, None) on success; (None, "UNKNOWN_TOOL") on failure.
        """
        for prefix, group in self._groups.items():
            if tool_name.startswith(f"{prefix}.") or tool_name == prefix:
                return group, None
        return None, "UNKNOWN_TOOL"


# ---------------------------------------------------------------------------
# ToolRegistry (COMP-MC-002)
# ---------------------------------------------------------------------------


class _DispatchContext(NamedTuple):
    """What :meth:`ToolRegistry.dispatch_request` resolves before the run.

    Carries the role-resolved context the tool is executed with, the context
    the access gates are evaluated on (the two may name different workspaces,
    see :meth:`ToolRegistry._scoped_gate_context`), the routed tool group and
    the workspace ids the preset gate needs.
    """

    auth_ctx: AuthContext
    gate_ctx: AuthContext
    group: Any
    workspace_id: str | None
    scope_workspace_id: str | None


class ToolRegistry:
    """Central dispatch and access-control gate for MCP tools (COMP-MC-002).

    Auth flow (ADR-L3-MC002-01):
      1. validate_api_key → IdentityClaims / AUTH_FAILED
      2. resolve roles     → AuthContext
      3. RBAC check        → PERMISSION_DENIED (write only)
      4. Preset filter     → FEATURE_NOT_ENABLED (feature-gated tools)
      5. Route to group    → UNKNOWN_TOOL or execute
    """

    def __init__(
        self,
        auth_service: AuthenticationService | None = None,
        authz_service: AuthorizationService | None = None,
        workspace_exists: Callable[[str], bool] | None = None,
    ) -> None:
        self._auth_service = auth_service or AuthenticationService()
        self._authz_service = authz_service or AuthorizationService()
        self._workspace_exists_fn = workspace_exists or self._default_workspace_exists
        self._preset_cache = PresetCache()
        self._router: ToolGroupRouter | None = None

        # Lazily built ``tool name -> declared inputSchema properties`` index.
        # See :meth:`_published_schema_param_names` (#1376): routing alone is
        # not enough because a prefix can delegate to a wrapped group
        # (``AdminToolGroup`` -> ``CrossCuttingToolGroup`` for
        # ``workspace.get_context``), so the *published* schema, not the routed
        # group's local schema list, must decide whether a parameter exists.
        self._schema_param_index: dict[str, tuple[str, ...]] | None = None

        # Lazy-imported tool groups to avoid circular imports at module load
        self._groups: dict[str, Any] = {}

    def register_groups(self, groups: dict[str, Any]) -> None:
        """Register tool group instances.

        Args:
            groups: Mapping of prefix string → ToolGroup instance.
                    E.g.: {"requirement": RequirementsToolGroup(), ...}
        """
        self._groups = groups
        self._router = ToolGroupRouter(groups)
        # Registered schemas changed — the published-parameter index is stale.
        self._schema_param_index = None

    def all_tool_schemas(self) -> list[dict[str, Any]]:
        """Return every registered tool schema, before any RBAC/scope gating.

        The *complete* catalogue the server can offer — the denominator a
        caller needs to notice that its own ``tools/list`` answer is narrowed
        (issue #1593). :meth:`list_tools` starts from exactly this list and
        then removes what the calling key/role may not execute, so the two can
        never disagree about which tools exist.

        Deduplicates by group object identity (REQ-129): several prefixes
        intentionally share one group instance (``audit``/``events``,
        ``traceability``/``artifact``), so iterating ``_groups.values()``
        naively would emit the same schemas once per prefix.
        """
        self._ensure_groups()
        tools: list[dict[str, Any]] = []
        seen_group_ids: set[int] = set()
        for group in self._groups.values():
            if id(group) in seen_group_ids:
                continue
            seen_group_ids.add(id(group))
            if hasattr(group, "get_tool_schemas"):
                tools.extend(group.get_tool_schemas())
        return tools

    def hidden_tool_aliases(self) -> dict[str, dict[str, Any]]:
        """Return the R2A-003 hidden legacy-verb aliases for the catalogue.

        For each published ``*.get``/``*.read`` the alternative ``*.read``/
        ``*.get`` spelling is declared as a deprecated alias, and likewise for
        ``*.list``/``*.query``. ``replacedBy`` always names a tool that is
        actually published, so an agent reading the metadata can migrate with
        a direct rename.

        Aliases are metadata **only**: they are not added to
        :meth:`all_tool_schemas`/``tools/list`` (the catalogue stays at 301)
        and they are not routable — the #1376 "no shadow tools" ratchet keys
        off ``_TOOL_MAP`` and must keep holding. They document the legacy
        spelling for one release; remove them once clients have migrated.
        """
        # Lazy import: tool groups import ``mcp_server.protocol_handler`` and
        # some are themselves imported lazily by ``_ensure_groups``.
        from mcp_server.tools.base import FETCH_VERBS, LIST_VERBS, verb_operation

        self._ensure_groups()
        published = {
            schema.get("name")
            for schema in self.all_tool_schemas()
            if schema.get("name")
        }
        aliases: dict[str, dict[str, Any]] = {}
        for name in sorted(published):
            operation = verb_operation(name)
            if operation is None:
                continue
            prefix, verb = name.rsplit(".", 1)
            alternatives = (FETCH_VERBS if operation == "fetch" else LIST_VERBS) - {verb}
            for alternative in sorted(alternatives):
                alias = f"{prefix}.{alternative}"
                # A prefix that publishes both spellings (e.g. memory.get and
                # memory.query) has no alias for the published one.
                if alias in published:
                    continue
                aliases[alias] = {"deprecated": True, "replacedBy": name}
        return aliases

    def _ensure_groups(self) -> None:
        """Lazy-initialise default tool groups from :data:`GROUP_SPECS`.

        The group imports stay local (circular-import safe, ADR-L3-MC002-03),
        but construction is now a small loop over the declarative spec table:
        one place declares each prefix, which physical group instance it maps
        to (``group_key``), and its whole security policy (R2C-009).
        """
        if self._router is not None:
            return
        from application.adr_service import AdrService
        from application.change_request_service import ChangeRequestService
        from application.glossary_service import GlossaryService
        from application.issue_service import IssueService
        from application.risk_service import RiskService
        from mcp_server.tools.admin import AdminToolGroup
        from mcp_server.tools.ai_derivation import AiDerivationToolGroup
        from mcp_server.tools.architecture import ArchitectureToolGroup
        from mcp_server.tools.attribute_catalog import AttributeCatalogToolGroup
        from mcp_server.tools.attribute_definition import AttributeDefinitionToolGroup
        from mcp_server.tools.attribute_migration import AttributeMigrationToolGroup
        from mcp_server.tools.audit import AuditToolGroup
        from mcp_server.tools.backup import BackupToolGroup
        from mcp_server.tools.baseline import BaselineToolGroup
        from mcp_server.tools.comment import CommentToolGroup
        from mcp_server.tools.create_form_config import CreateFormConfigToolGroup
        from mcp_server.tools.cross_cutting import CrossCuttingToolGroup
        from mcp_server.tools.diagram import DiagramToolGroup
        from mcp_server.tools.document import DocumentToolGroup
        from mcp_server.tools.generic import GenericCrudToolGroup
        from mcp_server.tools.goals import GoalToolGroup, MainGoalToolGroup
        from mcp_server.tools.icd import IcdToolGroup
        from mcp_server.tools.interview import InterviewToolGroup
        from mcp_server.tools.introspection import IntrospectionToolGroup
        from mcp_server.tools.link_type import LinkTypeToolGroup
        from mcp_server.tools.memory import MemoryToolGroup
        from mcp_server.tools.metrics import MetricsToolGroup
        from mcp_server.tools.milestones import MilestoneToolGroup
        from mcp_server.tools.needs import StakeholderNeedsToolGroup
        from mcp_server.tools.permissions import PermissionsToolGroup
        from mcp_server.tools.preference import PreferenceToolGroup
        from mcp_server.tools.prompt_template import PromptTemplateToolGroup
        from mcp_server.tools.prompt_variable import PromptVariableToolGroup
        from mcp_server.tools.prompts import PromptsToolGroup
        from mcp_server.tools.quality import QualityToolGroup
        from mcp_server.tools.requirement_bundle import RequirementBundleToolGroup
        from mcp_server.tools.requirements import RequirementsToolGroup
        from mcp_server.tools.resources import ResourcesToolGroup
        from mcp_server.tools.review import ReviewToolGroup
        from mcp_server.tools.saved_view import SavedViewToolGroup
        from mcp_server.tools.suggestion import SuggestionToolGroup
        from mcp_server.tools.summaries import SummaryToolGroup
        from mcp_server.tools.tests import TestToolGroup
        from mcp_server.tools.tree_display_config import TreeDisplayConfigToolGroup
        from mcp_server.tools.users import UsersToolGroup
        from mcp_server.tools.work_items import WorkItemToolGroup

        # group_key -> zero-arg factory. Shared keys (cross_cutting, audit)
        # intentionally map to one instance reused by several prefixes (REQ-129).
        factories: dict[str, Callable[[], Any]] = {
            "requirement": RequirementsToolGroup,
            "needs": StakeholderNeedsToolGroup,
            "architecture": ArchitectureToolGroup,
            "test": TestToolGroup,
            "cross_cutting": CrossCuttingToolGroup,
            "workspace": AdminToolGroup,
            "permissions": PermissionsToolGroup,
            "admin": BackupToolGroup,
            "audit": AuditToolGroup,
            "user": UsersToolGroup,
            "adr": lambda: GenericCrudToolGroup("adr", AdrService),
            "risk": lambda: GenericCrudToolGroup("risk", RiskService),
            "issue": lambda: GenericCrudToolGroup("issue", IssueService),
            "glossary": lambda: GenericCrudToolGroup(
                "glossary", GlossaryService, item_type="GlossaryTerm"
            ),
            "change_request": lambda: GenericCrudToolGroup(
                "change_request", ChangeRequestService, item_type="ChangeRequest"
            ),
            "prompt_template": PromptTemplateToolGroup,
            "prompt_variable": PromptVariableToolGroup,
            "ai_derivation": AiDerivationToolGroup,
            "diagram": DiagramToolGroup,
            "document": DocumentToolGroup,
            "work_item": WorkItemToolGroup,
            "milestone": MilestoneToolGroup,
            "review": ReviewToolGroup,
            "suggestion": SuggestionToolGroup,
            "baseline": BaselineToolGroup,
            "goal": GoalToolGroup,
            "main_goal": MainGoalToolGroup,
            "requirement_bundle": RequirementBundleToolGroup,
            "interview": InterviewToolGroup,
            "memory": MemoryToolGroup,
            "link_type": LinkTypeToolGroup,
            "attribute_definition": AttributeDefinitionToolGroup,
            "attribute_catalog": AttributeCatalogToolGroup,
            "attribute_migration": AttributeMigrationToolGroup,
            "icd": IcdToolGroup,
            "comment": CommentToolGroup,
            "metrics": MetricsToolGroup,
            "tree_display_config": TreeDisplayConfigToolGroup,
            "create_form_definition": CreateFormConfigToolGroup,
            "preference": PreferenceToolGroup,
            "quality": QualityToolGroup,
            "summary": SummaryToolGroup,
            "resource": ResourcesToolGroup,
            "prompt": PromptsToolGroup,
            "tool": IntrospectionToolGroup,
            "saved_view": SavedViewToolGroup,
        }
        instances: dict[str, Any] = {}
        groups: dict[str, Any] = {}
        for spec in GROUP_SPECS:
            if spec.group_key not in instances:
                instances[spec.group_key] = factories[spec.group_key]()
            groups[spec.prefix] = instances[spec.group_key]
        self.register_groups(groups)

    def list_tools(
        self, api_key: str, workspace_id: str | None = None
    ) -> list[dict[str, Any]]:
        """List the tools available to the given API key.

        Applies the same RBAC gate as :meth:`dispatch_request` (REQ-108): a
        caller without WRITE permission (e.g. a Viewer) does not see write
        tools, so the advertised tool surface matches what the caller may
        actually execute. Preset feature gating stays an execution-time concern.

        #865 adds the capability tier on top: a READ_ONLY-scoped key sees no
        write tools at all and an AUTHOR-scoped key sees no governance tools
        (``admin.*``, ``user.*``, ``baseline.create``, ...), matching the gate
        :meth:`dispatch_request` applies.

        Args:
            api_key: Raw API key for validation.
            workspace_id: Optional workspace to resolve roles against. When
                omitted, roles are aggregated across all of the caller's
                non-suspended assignments (MCP ``tools/list`` is workspace-less).
        """
        self._ensure_groups()

        auth_ctx, auth_error = self._validate_api_key(api_key)
        if auth_error or auth_ctx is None:
            # Auth failure must surface as AUTH_FAILED/401 like every other
            # MCP method — an empty list here reads as "authenticated, zero
            # tools" and hides invalid/missing credentials from the caller.
            raise McpAuthenticationError(auth_error or "invalid_api_key")

        # fix #110: use set_request_tenant, not the bare TenantContext
        # thread-local, so the DB-level RLS session variable (COMP-PL-006)
        # is armed as a backstop for the MCP path too — previously only the
        # app-layer thread-local filter was active here.
        from persistence.middleware import clear_request_tenant, set_request_tenant
        try:
            if auth_ctx.tenant_id is not None:
                set_request_tenant(auth_ctx.tenant_id)

            roles = self._resolve_list_roles(auth_ctx, workspace_id)
            can_write = (
                scope_allows(auth_ctx.scope, Operation.WRITE)
                and self._authz_service.decide_access(roles, Operation.WRITE).allow
            )
            # #865: a governance tool the key's scope can never execute must not
            # be advertised either — same "advertised surface matches what the
            # caller may actually execute" invariant as the WRITE filter below.
            # Deliberately scope-only (not the RBAC matrix): role-based
            # visibility stays exactly as it was, the tiers only narrow what the
            # key itself was issued for. Legacy ``write`` keys are the ADMIN
            # tier, so their tool list is unchanged.
            can_govern = scope_allows(auth_ctx.scope, Operation.WORKSPACE_CONFIG)

            # MCP-Modernisierung spec section 6: the key's own policy. One
            # primary-key lookup serves both the manifest-side read-only mirror
            # below and the ``tool_groups`` curation at the end of this method.
            policy = get_api_key_policy(auth_ctx.api_key_id)

            # Deduplicate by group object identity (REQ-129): several prefixes
            # intentionally share a single instance (e.g. "audit"/"events" →
            # one AuditToolGroup, "traceability"/"artifact" → one
            # CrossCuttingToolGroup). ``all_tool_schemas`` owns that rule so the
            # gated list and the ungated catalogue size cannot diverge.
            tools: list[dict[str, Any]] = self.all_tool_schemas()

            if not can_write or policy.is_read_only:
                # Hide write tools from read-only callers (Viewer role, or a
                # read-scoped key) — except the tenant-admin-elevated ``user.*``
                # tools (_TENANT_ADMIN_ELEVATED_USER_TOOLS), which a pure
                # tenant-admin (TenantRole(admin), zero workspace-level
                # UserRole) can actually execute via the same
                # ``_is_tenant_admin_exempt`` bypass ``dispatch_request``'s
                # Step 3 RBAC gate already applies. Without this, tools/list
                # advertised none of the 8 tools such a caller can run.
                # That elevation does NOT survive a read scope: scope is a hard
                # boundary the dispatcher enforces above every exemption, so
                # advertising those tools to a read-scoped key would promise
                # something tools/call refuses.
                tools = [
                    t
                    for t in tools
                    if not self._is_write_tool(t.get("name", ""))
                    or (
                        not policy.is_read_only
                        and self._is_tenant_admin_exempt(t.get("name", ""), auth_ctx)
                    )
                ]
            if not can_govern:
                # AUTHOR-tier key: everything it may not execute is hidden,
                # including the tenant-admin-elevated ``user.*`` tools — those
                # are exempt from the *role* matrix, never from the capability
                # tier (same rule dispatch_request applies above its own
                # exemptions, security review B2).
                tools = [
                    t
                    for t in tools
                    if self._required_scope_operation(t.get("name", ""))
                    is not Operation.WORKSPACE_CONFIG
                ]
            # Spec section 6.2: ApiKey.tool_groups is CATALOGUE CURATION ONLY.
            # It changes what this key SEES, never what it may EXECUTE — there
            # is deliberately no counterpart to this block in
            # dispatch_request(). A key with narrow tool_groups loses no
            # ability; it just gets a smaller menu (fewer manifest tokens in the
            # client's context) and can still call any other permitted tool
            # directly by name.
            if policy.tool_groups:
                tools = [
                    t
                    for t in tools
                    if t.get("name", "") in _ALWAYS_VISIBLE_TOOLS
                    or policy.allows_group(t.get("name", "").split(".", 1)[0])
                ]
            return tools
        finally:
            if auth_ctx.tenant_id is not None:
                clear_request_tenant()

    def list_tools_page(
        self,
        api_key: str,
        workspace_id: str | None = None,
        *,
        toolset: str | None = None,
        tool_filter: dict[str, Any] | None = None,
        compact: bool = False,
    ) -> dict[str, Any]:
        """Filtered/compacted catalogue for ``tools/list`` and ``tools/filter``.

        Applies exactly the RBAC/scope gating of :meth:`list_tools` first, so a
        filter can only ever narrow the advertised surface, never widen it
        (issue #866).

        Args:
            api_key: Raw API key.
            workspace_id: Optional workspace to resolve roles against.
            toolset: A named phase preset (see :data:`TOOLSET_NAMES`).
            tool_filter: Optional mapping with ``groups`` (list of prefixes),
                ``names`` (list of exact tool names) and/or ``search`` (string).
            compact: Trim prose (first-sentence description, no schema
                descriptions) while keeping the callable schema.

        Returns:
            ``{"tools", "count", "total", "catalogue_total", "hidden_by_scope",
            "filtered", "workspace_id", "toolsets"}``.

            * ``total`` — the caller's full **RBAC-gated** catalogue size (the
              ``tools/filter`` contract since #866), so a client can see what a
              *client-side* filter saved;
            * ``catalogue_total`` — every tool the registry holds, before role
              and capability-tier gating (issue #1593). Without it a key that
              sees 98 of 248 tools had no way to tell its catalogue is
              filtered at all;
            * ``hidden_by_scope`` — ``catalogue_total - total``, i.e. how many
              tools this key's role/capability scope hid;
            * ``filtered`` — ``count < catalogue_total``: True whenever *this
              response* is narrower than the complete catalogue, whether
              because of the key's scope or an explicit filter/toolset;
            * ``workspace_id`` — the workspace roles were resolved against
              (``None`` = tenant-wide aggregate).

        Raises:
            McpAuthenticationError: propagated from :meth:`list_tools`.
            ValueError: an unknown ``toolset``/selector shape.
        """
        tools = self.list_tools(api_key, workspace_id)
        total = len(tools)
        catalogue_total = len(self.all_tool_schemas())

        f = tool_filter or {}
        if not isinstance(f, dict):
            raise ValueError("'filter' must be an object.")
        groups = f.get("groups")
        names = f.get("names")
        search = f.get("search")
        if groups is not None and not isinstance(groups, list):
            raise ValueError("'filter.groups' must be an array of prefixes.")
        if names is not None and not isinstance(names, list):
            raise ValueError("'filter.names' must be an array of tool names.")

        selected = filter_tool_catalogue(
            tools,
            toolset=toolset,
            groups=groups,
            names=names,
            search=search,
        )
        if compact:
            selected = [compact_tool(t) for t in selected]

        return {
            "tools": selected,
            "count": len(selected),
            "total": total,
            # #1593: the filter metadata. `tools` and the (absent) nextCursor
            # stay byte-compatible; these keys are purely additive so a client
            # can tell "98 of 248" from "the catalogue really is 98 tools".
            "catalogue_total": catalogue_total,
            "hidden_by_scope": max(catalogue_total - total, 0),
            "filtered": len(selected) < catalogue_total,
            "workspace_id": workspace_id,
            "toolsets": {name: list(prefixes) for name, prefixes in _TOOLSETS.items()},
        }

    def dispatch_request(
        self,
        tool_name: str,
        params: dict[str, Any],
        api_key: str,
    ) -> ToolResult:
        """Execute a MCP tool call after full auth/RBAC/preset checks.

        Args:
            tool_name: MCP tool identifier, e.g. "requirement.create".
            params: Caller-provided parameters (api_key already stripped).
            api_key: Raw API key for validation.

        Returns:
            ToolResult with success payload or structured error.
        """
        self._ensure_groups()

        # --- Step 1: API-key validation (REQ-L2-MC-006) ---
        # Auth runs BEFORE the TenantContext is activated. On auth failure we
        # return early without ever touching the context — the failure path
        # does not need cleanup.
        auth_ctx, auth_error = self._validate_api_key(api_key)
        if auth_error:
            return ToolResult.error("AUTH_FAILED", auth_error)

        # --- Activate TenantContext for tenant-scoped queries ---
        # Subsequent steps (role resolution via AuthorizationService, RBAC, preset
        # lookup, tool execution) all hit tenant-scoped models whose default
        # manager requires an active TenantContext. We must set the context
        # INSIDE this method — the View layer cannot do it earlier because
        # the auth lookup that produces the tenant id happens here, and
        # clearing it must happen here too so no thread-local state leaks
        # into the next request handled on the same worker thread.
        # The try/finally guarantees the context is cleared on every
        # exit path (success, early-return error, or unhandled exception).
        try:
            from persistence.middleware import clear_request_tenant, set_request_tenant

            if auth_ctx is not None and auth_ctx.tenant_id is not None:
                set_request_tenant(auth_ctx.tenant_id)

            # #1376: an undeclared ``workspace_id`` must behave exactly as if
            # it had never been sent — before role resolution, the gates and
            # the handler all see the same, schema-backed parameters.
            params = self._drop_undeclared_workspace_id(tool_name, params)
            context, error = self._resolve_dispatch_context(tool_name, params, auth_ctx)
            if error is not None:
                return error

            error = self._authorize_tool_call(context, tool_name, params)
            if error is not None:
                return error

            # --- Step 6: Execute tool ---
            return self._execute_tool_call(context, tool_name, params, api_key)
        finally:
            from persistence.middleware import clear_request_tenant

            clear_request_tenant()

    def _drop_undeclared_workspace_id(
        self, tool_name: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        """Remove a ``workspace_id`` the tool's published schema does not declare.

        #1376 (CWE-863): ``_scoped_gate_context`` Case 1 trusts a
        client-supplied ``workspace_id`` as the workspace the call targets.
        That trust is only warranted for tools whose ``inputSchema`` actually
        declares the parameter — the dispatcher's role narrowing, the API-key
        fence and the preset gate all use it as an explicit target then.

        For every other tool the value is a caller-controlled shortcut past
        target resolution: a key fenced to workspace A could send
        ``{"workspace_id": A, "id": <object in B>}``, get gated against A and
        reach a handler that mutates/reads the object in B (the service layer
        checks tenant and roles, not the object's workspace). ``_TOOL_TARGETS``
        entries for those tools exist precisely so the *object* decides the
        workspace; the undeclared parameter must not pre-empt that.

        The fix is structural rather than per-handler: the parameter is
        dropped here, before role resolution and before every gate, so the
        call behaves exactly as if it had not been sent. Target resolution and
        the fence then run on the object id as usual (fail-closed: an
        unresolvable or foreign target is denied), and no handler can read the
        stray value incidentally. Handlers that already reject the parameter
        themselves (:func:`tools.base.reject_unknown_params`) keep that guard
        for direct (non-dispatch) calls; at the wire it is simply never seen.

        Returns the original mapping when nothing changes, otherwise a shallow
        copy without ``workspace_id`` — the caller's dict is left untouched.

        Unknown tool names and non-:class:`BaseToolGroup` registrations are
        returned unchanged: the former are answered with ``UNKNOWN_TOOL``
        before any handler runs, and the latter only occur in tests (every
        production group in :meth:`_ensure_groups` is a ``BaseToolGroup``;
        ``test_mcp_workspace_fence_1376.py`` ratchets that).
        """
        if "workspace_id" not in params:
            return params
        declared = self._published_schema_param_names(tool_name)
        if declared is None or "workspace_id" in declared:
            return params
        return {key: value for key, value in params.items() if key != "workspace_id"}

    def _published_schema_param_names(self, tool_name: str) -> tuple[str, ...] | None:
        """Return *tool_name*'s published ``inputSchema`` property names.

        Built by walking every registered group's ``get_tool_schemas()`` — the
        same catalogue ``list_tools``/the manifest publish — and cached until
        :meth:`register_groups` runs again. Routing is deliberately not used:
        ``AdminToolGroup`` delegates non-lifecycle ``workspace.*`` calls to a
        wrapped ``CrossCuttingToolGroup`` (e.g. ``workspace.get_context``), so
        the routed group's local schema list does not necessarily contain the
        tool's published contract.

        ``None`` means "not inspectable": the tool name is absent from every
        schema of a :class:`BaseToolGroup` (unknown tool, or a unit-test-only
        double group). Callers keep the pre-#1376 behaviour in that case; in
        production unknown names are answered with ``UNKNOWN_TOOL`` before any
        handler runs, and every group registered by :meth:`_ensure_groups` is a
        ``BaseToolGroup`` (ratcheted by
        ``test_mcp_workspace_fence_1376.py``).
        """
        if self._schema_param_index is None:
            # Lazy import: tool groups import ``mcp_server.protocol_handler``
            # and some are themselves imported lazily by ``_ensure_groups``.
            from mcp_server.tools.base import BaseToolGroup

            index: dict[str, tuple[str, ...]] = {}
            seen_groups: set[int] = set()
            for group in self._groups.values():
                if id(group) in seen_groups:
                    continue
                seen_groups.add(id(group))
                if not isinstance(group, BaseToolGroup):
                    continue
                for schema in group.get_tool_schemas():
                    name = schema.get("name")
                    if not name or name in index:
                        continue
                    properties = (schema.get("inputSchema") or {}).get(
                        "properties"
                    ) or {}
                    index[name] = tuple(properties)
            self._schema_param_index = index
        return self._schema_param_index.get(tool_name)

    def _resolve_dispatch_context(
        self,
        tool_name: str,
        params: dict[str, Any],
        auth_ctx: AuthContext | None,
    ) -> tuple[_DispatchContext | None, ToolResult | None]:
        """Resolve the call's workspace, roles and tool group (Steps 2-2b).

        A named ``workspace_id`` that does not exist fails NOT_FOUND *before*
        routing, and routing happens *before* the RBAC gate so an unrecognised
        tool name never leaks PERMISSION_DENIED. The route is resolved once
        here and reused when the call is executed (no double routing).

        Returns:
            ``(context, None)`` on success; ``(None, error)`` for the
            NOT_FOUND and UNKNOWN_TOOL paths.
        """
        # --- Step 2: Resolve active roles ---
        workspace_id: str | None = params.get("workspace_id")
        if workspace_id and not self._workspace_exists_fn(workspace_id):
            return None, ToolResult.error(
                "NOT_FOUND", f"Workspace '{workspace_id}' does not exist."
            )
        # GitHub #37: instance-level tools (e.g. admin.backup_create) are
        # not workspace-bound; an incidental workspace_id in params must
        # not narrow the caller's roles to that single workspace.
        role_workspace_id = None if tool_name in _INSTANCE_LEVEL_TOOLS else workspace_id
        auth_ctx = self._resolve_roles(auth_ctx, role_workspace_id)  # type: ignore[arg-type]

        # --- Step 2b: Existence check (ADR-L3-MC002-03) ---
        # Resolved before the RBAC gate: an unrecognised tool name never
        # reaches a handler regardless of the RBAC outcome, so gating it
        # on WRITE first would (a) leak PERMISSION_DENIED for names that
        # don't exist and (b) since #99's fail-closed default treats any
        # unrecognised name as a write tool, would mask UNKNOWN_TOOL
        # behind a 403 for callers without write roles. Route once here;
        # the resolved group is reused when the call is executed
        # (no double routing).
        assert self._router is not None
        group, route_error = self._router.route(tool_name)
        if route_error:
            return None, ToolResult.error("UNKNOWN_TOOL", f"Unknown tool: '{tool_name}'")

        # --- Step 3: RBAC (REQ-L2-MC-007, Systemaudit 2026-08-29 §6.5) ---
        # The gate is evaluated against the workspace the call actually
        # targets. When that workspace is not named in ``workspace_id``,
        # ``mcp_server.workspace_scope`` derives it from the object the
        # call addresses by id; see that module for why both the read and
        # the write path need it.
        gate_ctx, scope_workspace_id = self._scoped_gate_context(
            tool_name, params, auth_ctx, role_workspace_id  # type: ignore[arg-type]
        )
        return (
            _DispatchContext(
                auth_ctx=auth_ctx,
                gate_ctx=gate_ctx,
                group=group,
                workspace_id=workspace_id,
                scope_workspace_id=scope_workspace_id,
            ),
            None,
        )

    def _authorize_tool_call(
        self,
        context: _DispatchContext,
        tool_name: str,
        params: dict[str, Any],
    ) -> ToolResult | None:
        """Run every gate between routing and execution (Steps 3a-4).

        Order matters and is fixed: the API-key workspace fence first (it
        applies on every path, including the RBAC exemptions), then the write
        or read RBAC branch, then the preset feature gate.

        Returns:
            The error to answer with, or ``None`` when the call may proceed.
        """
        # --- Step 3a: API-key workspace fence (security review B3) ---
        # Runs before every other gate, including the RBAC exemptions: a
        # key fenced to workspace A must not reach workspace B through any
        # path. REST gets this for free because it builds its AuthContext
        # via ``TenantContextService.build_auth_context``; MCP constructs
        # the context itself (see ``_validate_api_key``/``_resolve_roles``)
        # and therefore never inherited the fence.
        # E1.3: a workspace-less call to an opted-in list tool is not denied
        # here — the tool narrows its own result to the key's fence. Every
        # other call keeps the fail-closed denial.
        from mcp_server.workspace_scope import FENCE_FILTERED_TOOLS

        fence_filtered = (
            tool_name in FENCE_FILTERED_TOOLS
            and context.scope_workspace_id is None
        )
        fence_error = (
            None
            if fence_filtered
            else self._check_workspace_fence(
                context.gate_ctx, context.scope_workspace_id
            )
        )
        if fence_error:
            # #1357: the fence stays fail-closed — the call below never runs.
            # But when the fence denied because *no target workspace could be
            # resolved* and the reason is a parameter-level defect of the call
            # (missing/typo'd/malformed target id), answer with the validation
            # class (JSON-RPC -32602 on the direct-method path, the same
            # error the tool's own parameter validation would raise) instead
            # of the workspace-scope text, which used to mask the real cause.
            param_error = self._unresolved_target_param_error(
                tool_name, params, context.scope_workspace_id
            )
            if param_error is not None:
                return ToolResult.error("VALIDATION_ERROR", param_error)
            return ToolResult.error("PERMISSION_DENIED", fence_error)

        if fence_filtered and getattr(context.gate_ctx, "api_key_workspace_ids", ()):
            # #1444: an opted-in list is exempt from the *fence* only — REST
            # still decides it with the fence-scoped roles, so MCP must not
            # answer 200 with an empty list where REST answers 403. The verdict
            # and its text come from the same ``auth_tenancy`` helper REST uses.
            # Only a fenced key needs it: an unfenced key's list carries no
            # fence to intersect and keeps the tenant-scoped read behaviour.
            from auth_tenancy.resource_scope import fence_filtered_list_decision

            _, list_denial = fence_filtered_list_decision(context.gate_ctx)
            if list_denial is not None:
                return ToolResult.error("PERMISSION_DENIED", list_denial)

        if self._is_write_tool(tool_name):
            error = self._authorize_write_tool(context, tool_name, params)
            if error is not None:
                return error
        elif context.scope_workspace_id is not None:
            read_error = self._check_read_rbac(context.gate_ctx, tool_name)
            if read_error:
                return ToolResult.error("PERMISSION_DENIED", read_error)

        # --- Step 4: Preset feature gate (REQ-L2-MC-008) ---
        # #1376: the gate runs against the workspace the call actually targets.
        # For a schema-declared ``workspace_id`` that is the named workspace
        # (unchanged behaviour); for an object-targeted call it is the
        # resolved target workspace, so the undeclared parameter no longer
        # picks which workspace's preset is consulted. The gate can only deny,
        # so the fence/RBAC checks above stay the deciding hard gate.
        preset_workspace_id = context.scope_workspace_id or context.workspace_id
        if preset_workspace_id:
            preset_error = self._check_preset(preset_workspace_id, tool_name)
            if preset_error:
                return ToolResult.error(
                    "FEATURE_NOT_ENABLED",
                    f"Tool '{tool_name}' is not available in the active workspace preset.",
                )
        return None

    def _authorize_write_tool(
        self,
        context: _DispatchContext,
        tool_name: str,
        params: dict[str, Any],
    ) -> ToolResult | None:
        """Gate a write tool on the key's capability tier, then on the matrix.

        The two RBAC exemptions are evaluated last: an exempted caller still
        has to hold a key whose scope covers the required tier.

        Returns:
            The error to answer with, or ``None`` when the call may proceed.
        """
        # Security review B2: the key-scope gate is evaluated BEFORE
        # the two RBAC exemptions, not inside ``_check_rbac`` which
        # they skip. Scope and RBAC-exemption are orthogonal: being
        # exempt from the *role* matrix (bootstrap, tenant-admin) must
        # never exempt a caller from the capability tier their key was
        # issued with, or a read-scoped bootstrap/tenant-admin key
        # could write freely.
        #
        # MCP-Modernisierung spec section 6.1: this is also the enforcement
        # point for ``scope="read"`` on the ``tools/call`` path — the read tier
        # is below WRITE's required tier, so a read-scoped key is refused here
        # with PERMISSION_DENIED whether or not it learned the tool name from
        # ``tools/list``. Deliberately the *same* gate as REST (one tier table,
        # not a second MCP-only rule); ``ApiKeyPolicy.is_read_only`` mirrors it
        # on the manifest side in ``list_tools``.
        #
        # #865: the required tier depends on the tool — governance
        # namespaces need the ADMIN tier, ordinary content writes only
        # the AUTHOR tier (see ``_required_scope_operation``). Legacy
        # ``write`` keys are the ADMIN tier and are unaffected.
        scope_error = scope_denial_reason(
            context.gate_ctx.scope, self._required_scope_operation(tool_name)
        )
        if scope_error:
            return ToolResult.error("PERMISSION_DENIED", scope_error)

        if self._is_bootstrap_candidate(
            tool_name, params, context.auth_ctx  # type: ignore[arg-type]
        ) or self._is_tenant_admin_exempt(
            tool_name, context.auth_ctx  # type: ignore[arg-type]
        ):
            return None

        rbac_error = self._check_rbac(context.gate_ctx, tool_name)
        if rbac_error:
            return ToolResult.error("PERMISSION_DENIED", rbac_error)
        return None

    def _execute_tool_call(
        self,
        context: _DispatchContext,
        tool_name: str,
        params: dict[str, Any],
        api_key: str,
    ) -> ToolResult:
        """Hand the call to the routed tool group (Step 6).

        Runs inside the TenantContext armed by :meth:`dispatch_request`, which
        stays active until the group has produced its result.

        Plan A T-A1-5 / ADR-024 AC-6: the call runs inside a memory-injection
        ledger, so a tool whose prompt built memory reports it as an additive
        ``memory_injected`` key on its successful dict payload. A tool that
        never touches memory (the overwhelming majority), a non-dict payload
        and an error result stay byte-identical.
        """
        try:
            # Inside the guard on purpose: an ImportError here must not escape
            # the fix-#108 safety net as an unmasked 500.
            from memory.injection_ledger import open_ledger

            with open_ledger() as ledger:
                result: ToolResult = context.group.execute_tool(  # type: ignore[union-attr]
                    tool_name=tool_name,
                    params=params,
                    auth_context=context.auth_ctx,
                    api_key=api_key,
                )
                _attach_memory_injected(result, ledger)
                return result
        except Exception:
            # fix #108: outer safety net — same masking as
            # BaseToolGroup.execute_tool's inner catch-all, in case a
            # tool group's execute_tool override raises before reaching it.
            logger.exception("Unexpected error in tool group for tool=%s", tool_name)
            return ToolResult.error("INTERNAL_ERROR", "An internal error occurred.")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _validate_api_key(
        self, api_key: str
    ) -> tuple[AuthContext | None, str | None]:
        """Validate API key via AuthenticationService.

        Returns:
            (partial_auth_ctx, None) on success.
            (None, error_message) on failure.
        """
        if not api_key.startswith("reqlo_"):
            # By design, MCP only accepts API keys (reqlo_...), never JWT bearer
            # tokens: REQ-L2-MC-006 mandates API-key auth for the MCP server,
            # and REQ-052 confines cookie/JWT auth to the REST adapter. This
            # is unrelated to REQ-126 (symmetric role resolution for the REST
            # Bearer-token path) — that requirement never changed MCP's auth
            # method. A JWT sent via Authorization: Bearer would otherwise
            # fail key lookup with the misleading "invalid_api_key" — this
            # makes the real cause explicit.
            logger.debug("MCP auth: credential does not match API-key format")
            return None, (
                "Authentication failed: bearer_not_supported — MCP requires an "
                "API key (X-API-Key header or 'Authorization: Bearer reqlo_...'), "
                "not a JWT bearer token. This is intentional (REQ-L2-MC-006, "
                "REQ-052) and independent of REQ-126, which only concerns the "
                "REST Bearer-token role-resolution path."
            )

        try:
            claims = self._auth_service.validate_api_key(api_key)
        except AuthenticationFailed as exc:
            logger.debug("MCP API key validation failed: %s", exc.code)
            return None, f"Authentication failed: {exc.code}"
        except Exception:
            # D-3 (CWE-209): mirror the masking already used at the outer
            # dispatch_request safety net (see "An internal error occurred."
            # above) — the raw exception must not reach the caller under
            # AUTH_FAILED, since that can leak infra details (DSN fragments
            # etc.) to an unauthenticated-or-wrongly-authenticated caller.
            logger.exception("Unexpected auth error")
            return None, "An internal error occurred."

        # Build a partial AuthContext (roles resolved separately)
        ctx = AuthContext(
            user_id=claims.user_id,
            tenant_id=claims.tenant_id,
            active_roles=(),  # resolved in step 2
            auth_method=AuthMethod.API_KEY,
            api_key_id=claims.api_key_id,
            actor_type=claims.actor_type,
            agent_label=claims.agent_label,
            scope=claims.scope,
            api_key_workspace_ids=claims.api_key_workspace_ids,
        )
        return ctx, None

    def _resolve_roles(
        self, ctx: AuthContext, workspace_id: str | None
    ) -> AuthContext:
        """Resolve active roles for ctx in workspace_id.

        With a workspace context, roles are resolved workspace-scoped. Without
        one, API-key callers fall back to a global aggregate of every
        non-suspended role they hold (REQ-127): most MCP tool calls carry no
        ``workspace_id`` param, and returning an empty role tuple there caused
        every write operation to fail with PERMISSION_DENIED. This mirrors the
        REST path (auth_tenancy/rest.py), which always loads API-key roles
        globally. Falls back to empty roles only if lookup fails.
        """
        if not workspace_id:
            if ctx.auth_method == AuthMethod.API_KEY:
                roles = self._resolve_global_roles(ctx)
                return AuthContext(
                    user_id=ctx.user_id,
                    tenant_id=ctx.tenant_id,
                    active_roles=roles,
                    auth_method=ctx.auth_method,
                    api_key_id=ctx.api_key_id,
                    actor_type=ctx.actor_type,
                    agent_label=ctx.agent_label,
                    scope=ctx.scope,
                    api_key_workspace_ids=ctx.api_key_workspace_ids,
                )
            return ctx

        try:
            workspace_uuid = UUID(str(workspace_id))
            roles = self._authz_service.active_roles_for(
                user_id=ctx.user_id, workspace_id=workspace_uuid
            )
        except Exception:  # noqa: BLE001 — roles probe best-effort; fail-closed (), logged
            logger.debug("Role resolution failed for workspace=%s", workspace_id)
            roles = ()

        return AuthContext(
            user_id=ctx.user_id,
            tenant_id=ctx.tenant_id,
            active_roles=roles,
            auth_method=ctx.auth_method,
            api_key_id=ctx.api_key_id,
            actor_type=ctx.actor_type,
            agent_label=ctx.agent_label,
            scope=ctx.scope,
            api_key_workspace_ids=ctx.api_key_workspace_ids,
        )

    def _resolve_global_roles(self, ctx: AuthContext) -> tuple[str, ...]:
        """Aggregate every non-suspended role the caller holds across workspaces.

        Used when no workspace context is available (REQ-127, REQ-108). Returns
        an empty tuple if the lookup fails.

        #1444: a workspace-fenced key must not borrow a role it holds *outside*
        its fence. Such a key resolves to the same fence-scoped tuple REST uses
        for its list decision (:func:`fenced_collection_roles`), so both doors
        decide with identical roles; without this, an Editor in workspace B
        passed the workspace-less MCP gate on a key fenced to workspace A.
        """
        try:
            if getattr(ctx, "api_key_workspace_ids", ()):
                from auth_tenancy.resource_scope import fenced_collection_roles

                return fenced_collection_roles(ctx)
            roles = self._authz_service.active_roles_across_workspaces(
                user_id=ctx.user_id
            )
            # Coerce defensively: a stubbed/partial service must degrade to the
            # fail-closed empty tuple rather than leak a non-role object into
            # the RBAC gate.
            return tuple(sorted({str(role) for role in roles}))
        except Exception:  # noqa: BLE001 — global roles probe best-effort; fail-closed (), logged
            logger.debug("Global role resolution failed for user=%s", ctx.user_id)
            return ()

    def _resolve_list_roles(
        self, ctx: AuthContext, workspace_id: str | None
    ) -> tuple[str, ...]:
        """Resolve the caller's active roles for the ``tools/list`` RBAC gate.

        With a workspace context we reuse the workspace-scoped resolution.
        Without one (the common ``tools/list`` case) we aggregate every
        non-suspended role the caller holds across all workspaces, so a caller
        that may write anywhere still sees the write tools while a pure Viewer
        does not (REQ-108).
        """
        # Security review B3: a workspace-fenced key gets no roles outside its
        # fence, so ``tools/list`` advertises it the read-only tool set rather
        # than write tools it would be denied at dispatch. Same rule and same
        # fail-closed workspace-less branch as ``_check_workspace_fence``.
        if self._check_workspace_fence(ctx, workspace_id):
            return ()

        if workspace_id:
            return self._resolve_roles(ctx, workspace_id).active_roles

        return self._resolve_global_roles(ctx)

    def _is_write_tool(self, tool_name: str) -> bool:
        """Return True if tool_name requires the WRITE RBAC gate.

        Fail-closed default (#99): a tool is write-protected unless it is
        explicitly known to be read-only, either by exact name
        (:data:`_READ_ONLY_TOOL_NAMES`) or by one of the read-only suffixes
        emitted by dynamically generated tool groups
        (:data:`_READ_ONLY_TOOL_SUFFIXES`). Unrecognised/new tool names are
        therefore RBAC-checked by default instead of silently passing
        through, unlike the previous allowlist-of-write-prefixes approach.
        """
        if tool_name in _READ_ONLY_TOOL_NAMES:
            return False
        if tool_name.endswith(_READ_ONLY_TOOL_SUFFIXES):
            return False
        return True

    def _required_scope_operation(self, tool_name: str) -> Operation:
        """Return the operation the key-scope gate must evaluate for *tool_name*.

        Maps an MCP tool onto the same :class:`Operation` vocabulary the REST
        adapters use, so one shared gate
        (``auth_tenancy.services.authorization.scope_denial_reason``) decides
        both transports (#865):

        * read tools -> :attr:`Operation.READ` (any tier may read),
        * write tools named in the tool-level governance set
          (:data:`_GOVERNANCE_TOOL_NAMES`, e.g. ``audit.waive_finding``, #569)
          -> :attr:`Operation.WORKSPACE_CONFIG`, i.e. the ADMIN tier. Checked
          first so an individually-named governance tool wins over its
          (mixed) namespace,
        * write tools in a governance namespace
          (:data:`_GOVERNANCE_TOOL_NAMESPACES`, e.g. ``user.create``,
          ``admin.restore``, ``baseline.create``, ``prompt_template.update``,
          ``link_type.create``) ->
          :attr:`Operation.WORKSPACE_CONFIG`, i.e. the ADMIN tier,
        * every other write tool -> :attr:`Operation.WRITE` (AUTHOR tier).
        """
        if not self._is_write_tool(tool_name):
            return Operation.READ
        if tool_name in _GOVERNANCE_TOOL_NAMES:
            return Operation.WORKSPACE_CONFIG
        namespace = tool_name.split(".", 1)[0]
        if namespace in _GOVERNANCE_TOOL_NAMESPACES:
            return Operation.WORKSPACE_CONFIG
        return Operation.WRITE

    def _is_bootstrap_candidate(
        self, tool_name: str, params: dict[str, Any], ctx: AuthContext
    ) -> bool:
        """SEC-05: let a self-targeted admin-bootstrap ``user.assign_role``
        call past the blanket write-RBAC gate.

        This only defers the decision to ``AuthorizationService.assign_role``,
        which still enforces the real invariant (zero active admins in the
        target workspace) before the assignment is actually persisted, so a
        caller who isn't genuinely bootstrapping still gets rejected there.
        """
        if tool_name != "user.assign_role":
            return False
        if str(params.get("role", "")).lower() != ROLE_ADMIN:
            return False
        try:
            return UUID(str(params.get("user_id"))) == ctx.user_id
        except (ValueError, TypeError):
            return False

    def _is_tenant_admin_exempt(self, tool_name: str, ctx: AuthContext) -> bool:
        """Let a pure tenant-admin caller past the blanket write-RBAC gate.

        Only applies to :data:`_TENANT_ADMIN_ELEVATED_USER_TOOLS`, whose
        handlers/services already re-check tenant-admin standing themselves
        (defense in depth is not lost). Fails closed (returns ``False``) on
        any lookup error, matching :meth:`_resolve_global_roles`'s own
        fail-closed default.
        """
        if tool_name not in _TENANT_ADMIN_ELEVATED_USER_TOOLS:
            return False
        try:
            return self._authz_service.is_tenant_admin(
                user_id=ctx.user_id, tenant_id=ctx.tenant_id
            )
        except Exception:  # noqa: BLE001 — tenant-admin probe best-effort; logged at debug
            logger.debug(
                "Tenant-admin lookup failed for user=%s tool=%s",
                ctx.user_id,
                tool_name,
            )
            return False

    def _scoped_gate_context(
        self,
        tool_name: str,
        params: dict[str, Any],
        ctx: AuthContext,
        role_workspace_id: str | None,
    ) -> tuple[AuthContext, str | None]:
        """Return ``(ctx to gate on, workspace the call targets)``.

        Three cases, in order:

        1. ``role_workspace_id`` is set — Step 2 already narrowed ``ctx`` to
           that workspace, so it is returned unchanged. Since #1376 this only
           happens when the tool's published schema **declares**
           ``workspace_id``: an undeclared value is dropped by
           :meth:`_drop_undeclared_workspace_id` before this point, because
           otherwise it would bypass target resolution and the object's
           workspace check.
        2. The tool names an object whose owning workspace resolves (see
           :func:`mcp_server.workspace_scope.resolve_target_workspace_id`) —
           roles are re-resolved against *that* workspace for the gate only.
        3. Nothing resolves — the caller's tenant-wide role aggregate is used,
           exactly as before.

        Case 2 deliberately does **not** replace the ``AuthContext`` the tool
        is executed with. Narrowing the executing context is a separate,
        much larger behaviour change (several tool groups re-check
        ``has_role("admin")`` against it), and this gate needs none of it: it
        only has to decide admittance. Residual, therefore: inside a tool the
        caller still carries their tenant-wide roles.
        """
        if role_workspace_id is not None:
            return ctx, role_workspace_id
        if tool_name in _INSTANCE_LEVEL_TOOLS:
            # Not workspace-bound at all — narrowing would be the #37 bug.
            return ctx, None

        from mcp_server.workspace_scope import resolve_target_workspace_id

        target_workspace_id = resolve_target_workspace_id(tool_name, params)
        if target_workspace_id is None:
            return ctx, None
        return self._resolve_roles(ctx, target_workspace_id), target_workspace_id

    @staticmethod
    def _check_workspace_fence(
        ctx: AuthContext, target_workspace_id: str | None
    ) -> str | None:
        """Return why the key may not act on *target_workspace_id*, else None.

        ``ApiKey.workspace_ids`` fences a key to an explicit set of workspaces.
        An empty tuple means "no fence" (the common, unrestricted key) and is
        always allowed.

        A fenced key with **no** resolvable target workspace is denied too.
        That mirrors ``TenantContextService.build_auth_context``, which blanks
        the roles of a fenced key on the workspace-less path for the same
        reason: without a target there is nothing to check the fence against,
        and the tenant-wide fallback would hand the key exactly the workspaces
        it was fenced out of. Fail closed.

        Args:
            ctx: The caller's resolved context.
            target_workspace_id: Workspace the call addresses, or None when the
                tool names no workspace and none could be derived from it.

        Returns:
            A denial reason, or ``None`` when the call is within the fence.
        """
        # ADR-011 SEC-03: one fence implementation shared with REST, so the two
        # transports cannot drift apart.
        from auth_tenancy.resource_scope import workspace_fence_denial

        return workspace_fence_denial(ctx.api_key_workspace_ids, target_workspace_id)

    @staticmethod
    def _unresolved_target_param_error(
        tool_name: str, params: dict[str, Any], scope_workspace_id: str | None
    ) -> str | None:
        """Return the parameter-level diagnosis for a fence denial, else None.

        #1357: only relevant when the fence denied because **no target
        workspace could be resolved** (``scope_workspace_id is None``). When a
        target *was* resolved and lies outside the fence, the parameters are
        not the issue and the caller keeps the plain scope text. The diagnosis
        itself lives in :func:`mcp_server.workspace_scope.target_param_error`
        (the same registry that feeds target resolution), so the two cannot
        disagree about which parameter names the target.
        """
        if scope_workspace_id is not None:
            return None
        from mcp_server.workspace_scope import target_param_error

        return target_param_error(tool_name, params)

    def _check_rbac(self, ctx: AuthContext, tool_name: str | None = None) -> str | None:
        """Return error message if write is not permitted, else None.

        REQ-L2-MC-007: Viewer-only role must not write.

        ``tool_name`` is optional so the check stays callable standalone (as
        several tests do); when supplied, the capability gate is evaluated for
        that tool's tier, otherwise for a plain WRITE (#865).
        """
        # E2.1: read-only key. Independent of and above the RBAC matrix, same
        # rule as rest_api.auth_enforcer.RbacPermission. Kept here as well as
        # at the caller (which checks it before the RBAC exemptions, see B2)
        # so this method stays safe to call on its own.
        scope_error = scope_denial_reason(
            ctx.scope,
            self._required_scope_operation(tool_name)
            if tool_name
            else Operation.WRITE,
        )
        if scope_error:
            return scope_error

        decision = self._authz_service.decide_access(ctx.active_roles, Operation.WRITE)
        if not decision.allow:
            return (
                f"Role '{ctx.active_roles}' does not permit write operations. "
                "Editor or Admin role required."
            )
        return None

    def _check_read_rbac(self, ctx: AuthContext, tool_name: str) -> str | None:
        """Return an error message if the caller may not read here, else None.

        Systemaudit 2026-08-29 §6.5. Only reached once the target workspace is
        known, so an empty role tuple means "holds no role in the workspace
        this call names" — a deny, not a fallback. Every RBAC role grants
        ``Operation.READ`` (``_RBAC_MATRIX``), so this rejects exactly the
        non-members and nobody else.

        There is deliberately **no exemption list here.** An earlier revision
        skipped the check for ``workspace_scope.TENANT_SCOPED_READ_TOOLS``,
        which silently punched a hole straight back through the finding: that
        set documents which tools are safe *when no workspace is named*, and
        several of its members (``requirement.query``, ``audit.query``,
        ``artifact.search``, ...) do accept a ``workspace_id``. Reusing it as a
        runtime bypass re-opened ``requirement.query`` against a foreign
        workspace — caught by this file's own regression test. Classification
        and enforcement are separate concerns; keep them separate. Tools that
        genuinely must not be narrowed are handled earlier, by
        ``_INSTANCE_LEVEL_TOOLS`` in :meth:`_scoped_gate_context`.
        """
        decision = self._authz_service.decide_access(ctx.active_roles, Operation.READ)
        if not decision.allow:
            return (
                f"Role '{ctx.active_roles}' does not permit read access to the "
                "targeted workspace. An active role in that workspace is required."
            )
        return None

    def _check_preset(self, workspace_id: str, tool_name: str) -> bool:
        """Return True (blocked) if the tool is feature-gated and disabled.

        REQ-L2-MC-008.
        """
        feature_key = _TOOL_FEATURE_MAP.get(tool_name)
        if not feature_key:
            # Not feature-gated — always allowed
            return False

        # Check cache first
        cached = self._preset_cache.get(workspace_id)
        if cached is not None:
            features = cached
        else:
            try:
                from presets.services import get_preset

                preset_rules = get_preset(workspace_id)
                features = preset_rules.features
                self._preset_cache.set(workspace_id, features)
            except Exception:  # noqa: BLE001 — preset fail-open by design; auth is the hard gate
                logger.warning("Preset lookup failed for workspace=%s", workspace_id)
                # On failure, allow (fail-open for preset; auth is the hard gate)
                return False

        return not features.get(feature_key, True)

    @staticmethod
    def _default_workspace_exists(workspace_id: str) -> bool:
        """Return True if workspace_id refers to a real Workspace row.

        Guards against #95: a malformed or nonexistent workspace_id used to
        fail open (empty roles / auto-created preset config) and let read
        tools proceed with an HTTP 200 instead of a clear error. Injectable
        via the ``workspace_exists`` constructor arg so tests can stub it
        out without needing DB access, matching auth_service/authz_service.
        """
        from persistence.models import Workspace

        try:
            workspace_uuid = UUID(str(workspace_id))
        except (ValueError, TypeError):
            return False
        return Workspace.objects.filter(id=workspace_uuid).exists()

    @staticmethod
    def hash_api_key(plaintext: str) -> str:
        """Return sha256 hash of API key for audit log (never store plaintext)."""
        return "sha256:" + hashlib.sha256(plaintext.encode()).hexdigest()


def _attach_memory_injected(result: ToolResult, ledger: Any) -> None:
    """Add ``memory_injected`` to a successful dict payload (Plan A T-A1-5).

    Additive only (ADR-024 AC-6): a tool that recorded nothing leaves the
    payload byte-identical, and an error result is never decorated (its
    ``data`` belongs to the error contract). No tool's output schema changes.
    """
    # Invariant: never reuse a payload dict — a decorated copy replaces it.
    if not result.success or not isinstance(result.data, dict):
        return
    contract = ledger.as_contract()
    if contract is None or "memory_injected" in result.data:
        return
    result.data = {**result.data, "memory_injected": contract}


__all__ = [
    "PresetCache",
    "ToolGroupRouter",
    "ToolRegistry",
]
