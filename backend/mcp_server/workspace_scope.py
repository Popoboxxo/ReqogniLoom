"""Target-workspace resolution for the MCP dispatch RBAC gate.

Systemaudit 2026-08-29 (``docs/SYSTEMAUDIT_2026-08-29_GESAMTTEST_MCP.md`` §6.5)
found that MCP *reads* were not workspace-scoped: ``dispatch_request`` only ran
its RBAC gate for tools classified as WRITE, so ``requirement.query`` against a
workspace the caller holds no role in returned that workspace's data with HTTP
200. Workspace membership was a write boundary, not a confidentiality boundary.

Mapping the whole surface turned up the mirror-image hole on the write side:
71 of 106 write tools take no ``workspace_id`` at all (``requirement.update``,
``risk.delete``, ``goal.transition``, ...). For those, ``_resolve_roles`` falls
back to ``_resolve_global_roles`` — the tenant-wide union of every role the
caller holds *anywhere* — so an Editor in workspace A passed the WRITE gate for
an object living in workspace B. The audit missed this because it verified the
write path with ``requirement.create``, one of the 35 write tools that *does*
carry ``workspace_id``.

Both holes have the same root cause: **the dispatcher only knew the workspace a
call targets when the caller spelled it out in a parameter.** This module
supplies the missing half — it maps each tool to the parameter naming its
target object and asks
:func:`application.workspace_lookup.resolve_owning_workspace_id` which
workspace owns it, so the RBAC gate can be evaluated against the workspace the
call actually touches rather than against a tenant-wide role aggregate.

Design notes
------------

* **Layering (ADR-01).** This module holds only the MCP-specific tool → param
  mapping. The models and the query live in ``application/workspace_lookup.py``
  — ``mcp_server/`` performs no ORM access of its own (enforced by
  ``rest_api/tests/test_architecture.py::test_no_new_direct_orm_access_mcp_root``,
  whose ceiling for this file is 0 and must stay there).
* **Fail-soft resolution, fail-closed gate.** Resolution returning ``None``
  (unknown tool, absent/malformed id, deleted row, lookup error) leaves the
  pre-existing behaviour untouched — it never invents a workspace and never
  denies on its own. Whenever a workspace *is* resolved, the gate in
  ``tool_registry`` is strict: no role in that workspace means
  ``PERMISSION_DENIED``. A missing registry entry can therefore only ever be a
  missed tightening, never a new outage.
* **The registry is declarative on purpose.** Every entry is a
  ``(param name, entity key)`` pair, checked in order, first hit wins. Several
  tools list more than one candidate entity for the same parameter (e.g.
  ``context.change_impact``'s ``entity_id``, which may name any of four
  artifact types); UUID primary keys make a cross-table collision effectively
  impossible, so probing in order is safe and avoids duplicating the tool's own
  ``entity_type`` dispatch logic here.
* **Cost.** One indexed primary-key lookup per dispatch in the common case
  (the first candidate hits), and only for tools that name an object by id.
  Tools whose ``workspace_id`` is *required* never reach this module. The worst
  case — every candidate missing on a multi-entity parameter — costs one lookup
  per candidate, but that only happens for ids the tool itself is about to
  reject as NOT_FOUND anyway.

Read-tool classification
------------------------

Every read tool must be accounted for by exactly one mechanism, and
``test_mcp_workspace_scope.py`` fails the build otherwise:

1. ``workspace_id`` **required** in its input schema — the dispatcher narrows
   roles to it and gates there.
2. an entry in :data:`_TOOL_TARGETS` — the gate resolves the workspace from the
   object the call names.
3. :data:`TOOL_ENFORCED_WORKSPACE_SCOPE` — the tool performs its own,
   equivalent membership check.
4. :data:`TENANT_SCOPED_READ_TOOLS` — deliberately tenant-wide, with a reason.

The ratchet deliberately does **not** accept a merely *declared* ``workspace_id``
as scoping. That weaker check shipped in the first cut of this change and hid a
live instance of the very bug it was meant to catch: ``artifact.search``
declared the parameter, accepted ``None`` for it, and then fell through to
``SearchService.search(scope="workspace", workspace_id=None)`` — documented as
"the whole tenant with no RBAC narrowing". Declaring a parameter is not
enforcing it.
"""
from __future__ import annotations

from typing import Any, Dict, Mapping, Optional, Tuple
from uuid import UUID

from application.workspace_lookup import (
    ARTIFACT_BACKED_ENTITY_KEYS,
    resolve_owning_workspace_id,
)


# ---------------------------------------------------------------------------
# Tool → target registry
# ---------------------------------------------------------------------------


def _artifact_or_domain(param: str) -> Tuple[Tuple[str, str], ...]:
    """Targets for a param naming either an Artifact or a domain entity."""
    return ((param, "artifact"),) + tuple(
        (param, key) for key in ARTIFACT_BACKED_ENTITY_KEYS
    )


#: ``tool name -> ((param, entity key), ...)``, probed in order, first hit wins.
#: Only tools that name an object by id belong here — tools whose
#: ``workspace_id`` is required are scoped by the dispatcher without help.
_TOOL_TARGETS: Dict[str, Tuple[Tuple[str, str], ...]] = {
    # -- reads ---------------------------------------------------------
    "adr.read": (("id", "adr"),),
    "architecture.get": (("id", "architecture"),),
    "baseline.compare": (
        ("baseline_a_id", "baseline"),
        ("baseline_b_id", "baseline"),
    ),
    "baseline.get": (("id", "baseline"),),
    "change_request.read": (("id", "change_request"),),
    # entity_type selects the model inside the handler; probing all four
    # candidates here keeps that dispatch table from being duplicated.
    "context.change_impact": (
        ("entity_id", "requirement"),
        ("entity_id", "architecture"),
        ("entity_id", "testcase"),
        ("entity_id", "need"),
    ),
    "context.query": (("artifact_id", "artifact"),),
    "context.test_coverage": (("requirement_id", "requirement"),),
    "custom_field.get": (("id", "custom_field"),),
    "diagram.get": (("id", "diagram"),),
    "glossary.read": (("id", "glossary"),),
    "goal.list_versions": (("lineage_id", "goal_lineage"),),
    "goal.read": (("goal_id", "goal"),),
    "interview.get": (("session_id", "interview"),),
    "interview.get_state": (("session_id", "interview"),),
    "interview.propose": (("session_id", "interview"),),
    "issue.read": (("id", "issue"),),
    "needs.get_traces": (("id", "need"),),
    "needs.read": (("id", "need"),),
    "requirement.get": (("id", "requirement"),),
    "risk.read": (("id", "risk"),),
    "test.get": (("id", "testcase"),),
    "test.run_get": (("run_id", "test_run"),),
    "traceability.query": _artifact_or_domain("artifact_id"),
    # -- writes --------------------------------------------------------
    # The same seam closes the write-side hole described in the module
    # docstring: without it these tools are gated against the caller's
    # tenant-wide role union instead of the target workspace.
    "adr.delete": (("id", "adr"),),
    "adr.outdate": (("id", "adr"),),
    "adr.reactivate": (("id", "adr"),),
    "adr.update": (("id", "adr"),),
    "ai_derivation.decompose_requirement_next_level": (
        ("requirement_id", "requirement"),
    ),
    "ai_derivation.derive_requirements_from_need": (("need_id", "need"),),
    "ai_derivation.derive_risks_from_architecture": (
        ("architecture_element_id", "architecture"),
    ),
    "ai_derivation.suggest_architecture_for_requirement": (
        ("requirement_id", "requirement"),
    ),
    "architecture.decompose": (("element_id", "architecture"),),
    "architecture.link": (
        ("arch_id", "architecture"),
        ("target_id", "artifact"),
    ),
    "architecture.outdate": (("id", "architecture"),),
    "architecture.reactivate": (("id", "architecture"),),
    "architecture.update": (("id", "architecture"),),
    "change_request.delete": (("id", "change_request"),),
    "change_request.outdate": (("id", "change_request"),),
    "change_request.reactivate": (("id", "change_request"),),
    "change_request.update": (("id", "change_request"),),
    "context.related": _artifact_or_domain("artifact_id"),
    "diagram.outdate": (("id", "diagram"),),
    "diagram.reactivate": (("id", "diagram"),),
    "diagram.update": (("id", "diagram"),),
    "glossary.delete": (("id", "glossary"),),
    "glossary.outdate": (("id", "glossary"),),
    "glossary.reactivate": (("id", "glossary"),),
    "glossary.update": (("id", "glossary"),),
    "goal.delete": (("goal_id", "goal"),),
    "goal.outdate": (("goal_id", "goal"), ("id", "goal")),
    "goal.reactivate": (("goal_id", "goal"), ("id", "goal")),
    "goal.transition": (("goal_id", "goal"),),
    "goal.update": (("goal_id", "goal"),),
    "interview.abandon": (("session_id", "interview"),),
    "interview.answer": (("session_id", "interview"),),
    "interview.formalize": (("session_id", "interview"),),
    "interview.grounding_context": (("session_id", "interview"),),
    "interview.set_target": (("session_id", "interview"),),
    "issue.delete": (("id", "issue"),),
    "issue.outdate": (("id", "issue"),),
    "issue.reactivate": (("id", "issue"),),
    "issue.update": (("id", "issue"),),
    "main_goal.approve": (("main_goal_id", "main_goal"),),
    "needs.derive_requirements": (("id", "need"),),
    "needs.outdate": (("id", "need"),),
    "needs.reactivate": (("id", "need"),),
    "needs.update": (("id", "need"),),
    "requirement.decompose": (("requirement_id", "requirement"),),
    "requirement.derive": (("parent_requirement_id", "requirement"),),
    "requirement.outdate": (("id", "requirement"),),
    "requirement.reactivate": (("id", "requirement"),),
    "requirement.update": (("id", "requirement"),),
    "requirement.validate": (("requirement_id", "requirement"),),
    "risk.delete": (("id", "risk"),),
    "risk.outdate": (("id", "risk"),),
    "risk.reactivate": (("id", "risk"),),
    "risk.update": (("id", "risk"),),
    "test.derive_from_requirement": (("requirement_id", "requirement"),),
    "test.link": (("test_id", "testcase"), ("req_id", "requirement")),
    "test.outdate": (("id", "testcase"),),
    "test.reactivate": (("id", "testcase"),),
    "test.run_complete": (("run_id", "test_run"),),
    "test.run_report_results": (("run_id", "test_run"),),
    "test.update": (("id", "testcase"),),
    "traceability.create_link": (
        _artifact_or_domain("artifact_id")
        + _artifact_or_domain("source_artifact_id")
        + _artifact_or_domain("source_id")
    ),
}


# ---------------------------------------------------------------------------
# Reads scoped by the tool itself
# ---------------------------------------------------------------------------

#: Read tools whose handler performs its own workspace-membership check, so the
#: dispatcher gate would only duplicate it. Listed explicitly (not inferred) so
#: the claim is reviewable and the ratchet can hold each one to it.
#:
#: * ``memory.query`` / ``memory.list`` — ``MemoryToolGroup`` requires
#:   ``workspace_id`` for ``scope="workspace"`` and then calls
#:   ``_check_workspace_membership()``, whose own docstring cites this exact
#:   bug class ("any API key valid for tenant T could ..."). Workspace-scoped
#:   entries are additionally re-checked per row before they are returned.
TOOL_ENFORCED_WORKSPACE_SCOPE: frozenset[str] = frozenset(
    {
        "memory.query",
        "memory.list",
    }
)


# ---------------------------------------------------------------------------
# Deliberately tenant-scoped read tools
# ---------------------------------------------------------------------------

#: Read tools that are safe **when no ``workspace_id`` is supplied**. Each entry
#: is a product decision backed by a re-read of the handler, not an assumption;
#: the coverage ratchet asserts every read tool outside these sets is scoped.
#:
#: This set is documentation for the ratchet, **not** a runtime bypass. Most of
#: its members still accept a ``workspace_id``, and when one is supplied the
#: dispatcher gate must apply as usual — see the "no exemption list here" note
#: in ``ToolRegistry._check_read_rbac`` for the regression that taught us to
#: keep the two apart.
#:
#: * ``admin.backup_list`` — ``BackupMetadata`` is instance-level, not even
#:   tenant-scoped (see ``_INSTANCE_LEVEL_TOOLS`` in ``tool_registry``).
#: * ``user.list`` — the tenant user directory; scoping it to one workspace
#:   would break the admin flows that assign a user their *first* role.
#: * ``workspace.list`` — workspace discovery. This is how a caller learns
#:   which workspaces exist for them; it cannot require a workspace up front.
#: * ``requirement_bundle.attribute_schema`` — a static per-entity-type field
#:   schema, no tenant data at all.
#: * ``requirement_bundle.compression_status`` — polls a Celery task result
#:   through a tenant-ownership cache mapping the tool checks itself; the task
#:   id is not an artifact and has no workspace.
#: * ``audit.query`` — admin-gated in the handler (``_check_admin``) and
#:   ``AuditEntry`` is tenant-scoped; its ``workspace_id`` parameter is
#:   documented as *reserved* and does not filter.
#: * ``requirement.query`` — the parameter is optional in the schema but
#:   enforced at runtime: an omitted ``workspace_id`` returns VALIDATION_ERROR,
#:   so the unscoped path is unreachable. (Schema/handler mismatch worth
#:   tidying one day; it is not a hole.)
#: * ``workspace.get_context`` — without ``workspace_id`` it returns only the
#:   caller's own identity (tenant_id, user_id, active_roles); every workspace
#:   fact is inside the ``if workspace_id_str:`` branch, which the dispatcher
#:   gates.
#: * ``prompt_template.get`` / ``prompt_variable.get`` / ``prompt_variable.list``
#:   — omitting ``workspace_id`` selects the *tenant-wide* row only
#:   (``try_resolve_template_content`` consults a workspace row solely when one
#:   is given; ``list_variables`` keeps only ``workspace_id is None`` rows), so
#:   another workspace's values are never reachable.
#: * ``prompt_template.list`` — tenant-wide by contract, but the raw service
#:   call also returns *other workspaces'* rows, so the handler now narrows the
#:   result to the caller's accessible workspaces (see ``prompt_template.py``).
#: * ``artifact.search`` — tenant-wide by design, but only across the
#:   workspaces the caller holds a role in: the handler now passes
#:   ``scope="tenant"`` when no ``workspace_id`` is given, which routes through
#:   ``AuthorizationService.accessible_workspace_ids()``.
TENANT_SCOPED_READ_TOOLS: frozenset[str] = frozenset(
    {
        "admin.backup_list",
        "user.list",
        "workspace.list",
        "requirement_bundle.attribute_schema",
        "requirement_bundle.compression_status",
        "audit.query",
        "requirement.query",
        "workspace.get_context",
        "prompt_template.get",
        "prompt_template.list",
        "prompt_variable.get",
        "prompt_variable.list",
        "artifact.search",
    }
)


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------


def resolve_target_workspace_id(
    tool_name: str, params: Mapping[str, Any]
) -> Optional[str]:
    """Return the workspace owning the object ``tool_name`` targets.

    Args:
        tool_name: MCP tool identifier, e.g. ``"requirement.update"``.
        params: Caller-supplied parameters (``api_key`` already stripped).

    Returns:
        The owning workspace id as a string, or ``None`` when the tool names
        no resolvable object — the caller then keeps its previous behaviour.
    """
    targets = _TOOL_TARGETS.get(tool_name)
    if not targets:
        return None

    for param_name, entity_key in targets:
        raw = params.get(param_name)
        if raw in (None, ""):
            continue
        try:
            value = UUID(str(raw))
        except (ValueError, TypeError, AttributeError):
            # A malformed id is the tool's own validation problem; it must not
            # short-circuit the remaining candidates.
            continue
        workspace_id = resolve_owning_workspace_id(entity_key, value)
        if workspace_id is not None:
            return str(workspace_id)
    return None


__all__ = [
    "TENANT_SCOPED_READ_TOOLS",
    "TOOL_ENFORCED_WORKSPACE_SCOPE",
    "resolve_target_workspace_id",
]
