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
* **Fail-soft resolution, fail-closed gate — for reads.** Resolution returning
  ``None`` (unknown tool, absent/malformed id, deleted row, lookup error) leaves
  a *read* tool's pre-existing behaviour untouched — it never invents a
  workspace and never denies on its own. Whenever a workspace *is* resolved, the
  gate in ``tool_registry`` is strict: no role in that workspace means
  ``PERMISSION_DENIED``.
* **Writes are fail-closed.** Security finding #4
  (``.tmp/security-audit-rest-mcp-2026-11-25.md``) showed what the read-side
  rule costs on the write path: a write tool missing here fell back to the
  caller's tenant-wide role aggregate, so an Editor in workspace A could mutate
  an object in workspace B. A write tool that cannot be scoped to a workspace is
  therefore **denied** before any domain work, unless it is instance-level or
  deliberately tenant-scoped (see :data:`TENANT_SCOPED_WRITE_TOOLS`). The error
  class depends on the cause: a *missing or malformed* target parameter is a
  ``VALIDATION_ERROR`` (a request-shape defect, diagnosed from the same registry
  by :func:`target_param_error`), while only a *well-formed* target that matches
  no row — or a row in a workspace the caller holds no role in — is
  ``PERMISSION_DENIED`` with the scope text. Reads are unchanged.
* **The registry is declarative on purpose.** Every entry is a
  ``(param name, entity key)`` pair, checked in order, first hit wins. A param
  name may be a dotted path into a nested payload (``draft.root_element_id``)
  or name a list of ids (``ids``); both are probed with the same rule — the
  first value that resolves decides, and nothing resolving means "unresolved",
  which a write then denies. Several
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

Write-tool classification
-------------------------

Every write tool must be accounted for by exactly one mechanism, and
``test_every_write_tool_is_classified`` fails the build otherwise:

1. ``workspace_id`` **required** in its input schema — the dispatcher narrows
   roles to it and gates there. Omitting a *required* parameter stays a
   request-shape defect the handler reports as ``VALIDATION_ERROR`` (#1374);
   it is never a scoping ambiguity, because the tool cannot be called without
   the workspace it targets.
2. an entry in :data:`_TOOL_TARGETS` — the gate resolves the workspace from the
   object the call names (a scalar id, a list of ids, or a dotted path into a
   nested payload such as ``architecture.decompose_commit``'s ``draft``).
3. :data:`TENANT_SCOPED_WRITE_TOOLS` — deliberately tenant/instance level, with
   a per-entry reason.
4. ``_INSTANCE_LEVEL_TOOLS`` in ``tool_registry`` — already declared
   instance-level in ``GROUP_SPECS`` (``admin.backup_create``, ``admin.restore``).

Anything else is denied at dispatch. The ratchet is the guard against a *new*
tool shipping unscoped; the runtime gate in
``ToolRegistry._unscoped_write_denial`` is what makes a missed entry fail closed
instead of falling back to tenant-wide roles.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import UUID

from application.workspace_lookup import (
    ARTIFACT_BACKED_ENTITY_KEYS,
    resolve_owning_workspace_id,
)

# ---------------------------------------------------------------------------
# Tool → target registry
# ---------------------------------------------------------------------------


def _artifact_or_domain(param: str) -> tuple[tuple[str, str], ...]:
    """Targets for a param naming either an Artifact or a domain entity."""
    return ((param, "artifact"),) + tuple(
        (param, key) for key in ARTIFACT_BACKED_ENTITY_KEYS
    )


#: ``tool name -> ((param, entity key), ...)``, probed in order, first hit wins.
#: Only tools that name an object by id belong here — tools whose
#: ``workspace_id`` is required are scoped by the dispatcher without help.
_TOOL_TARGETS: dict[str, tuple[tuple[str, str], ...]] = {
    # -- reads ---------------------------------------------------------
    "adr.read": (("id", "adr"),),
    # Issue #1792 (S3): the on-demand artifact summary names its target by
    # ``artifact_id`` and declares no ``workspace_id``, so the gate resolves the
    # owning workspace from the artifact itself — a foreign workspace then fails
    # the role check instead of leaking a summary of its content. (Its sibling
    # ``artifact.get_tree`` needs no entry: ``workspace_id`` is required there.)
    "artifact.summary": (("artifact_id", "artifact"),),
    # Issue #1793 (S6) deliberately has NO entry here: ``summary.get`` and
    # ``summary.refresh`` both require ``workspace_id`` in their published
    # schema, so the dispatcher narrows the caller's roles to it and gates
    # there. The optional ``artifact_id`` narrows *within* that workspace and
    # is re-checked by the service (item-level read for a read, workspace write
    # for a refresh), never used to widen the target.
    "architecture.get": (("id", "architecture"),),
    "baseline.compare": (
        ("baseline_a_id", "baseline"),
        ("baseline_b_id", "baseline"),
    ),
    "baseline.get": (("id", "baseline"),),
    "change_request.read": (("id", "change_request"),),
    # Menschen-im-System spec §4: comment.list names its target artifact, so the
    # gate resolves the owning workspace from it. Without this entry the tool is
    # a read tool with no enforced scoping and the coverage ratchet fails.
    "comment.list": (("artifact_id", "artifact"),),
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
    # Plan F F2-T6 (ADR-026): every document tool that names its target by id
    # resolves the gate from the document's own workspace. document.create and
    # document.query declare a required ``workspace_id`` and need no entry here.
    "document.read": (("id", "document"),),
    # Phase G / #1374 S3: project and adopt name the document by ``id``;
    # projection_status declares a required ``workspace_id``.
    "document.project": (("id", "document"),),
    "document.adopt": (("id", "document"),),
    "document.versions": (("id", "document"),),
    "document.diff": (("id", "document"),),
    # Plan F F3-T6 (#1374): work_item.read/write name their target by ``id``.
    # work_item.create/query/checkpoint/resume declare a required
    # ``workspace_id`` and need no entry here.
    "work_item.read": (("id", "work_item"),),
    # Plan B B6-T2 (#879): every milestone tool that names its target by ``id``
    # resolves the gate from the milestone's own workspace.
    # milestone.create/milestone.list declare a required ``workspace_id`` and
    # need no entry here.
    "milestone.get": (("id", "milestone"),),
    "diagram.get": (("id", "diagram"),),
    "glossary.read": (("id", "glossary"),),
    # P6 visual groups: group.members names the group by ``group_id`` and its
    # schema declares no ``workspace_id``, so without this entry it was a read
    # tool with no enforced scoping (coverage ratchet). A group *is* an
    # ``Artifact`` of type "Group", so the generic artifact lookup resolves the
    # owning workspace; a foreign group then fails the role gate instead of
    # leaking its membership list.
    "group.members": (("group_id", "artifact"),),
    "icd.read": (("id", "icd"),),
    "goal.list_versions": (("lineage_id", "goal_lineage"),),
    "goal.read": (("goal_id", "goal"),),
    "interview.get": (("session_id", "interview"),),
    "interview.get_state": (("session_id", "interview"),),
    "interview.propose": (("session_id", "interview"),),
    "issue.read": (("id", "issue"),),
    "needs.get_traces": (("id", "need"),),
    "needs.read": (("id", "need"),),
    "requirement.get": (("id", "requirement"),),
    # #1288: reads the acceptance criteria of a requirement — scope resolves
    # from the requirement's own workspace, same as requirement.get.
    "requirement.acceptance_criteria.get": (("id", "requirement"),),
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
    # Finding #4 (P1.2): the draft's root element is the object the commit
    # actually extends — the service derives the workspace from *that row*
    # (never from the caller-supplied ``draft.workspace_id``), so resolving the
    # dotted path is what stops an Editor in A from committing a decomposition
    # into workspace B. A missing/unresolvable root id is denied, not admitted.
    "architecture.decompose_commit": (("draft.root_element_id", "architecture"),),
    "architecture.link": (
        ("arch_id", "architecture"),
        ("target_id", "artifact"),
    ),
    "architecture.outdate": (("id", "architecture"),),
    "architecture.reactivate": (("id", "architecture"),),
    "architecture.update": (("id", "architecture"),),
    # F4.2: tags are metadata, but the write still targets one baseline; without
    # this entry the gate would fall back to the caller's tenant-wide role union
    # and let an editor of workspace A tag a workspace-B baseline.
    "baseline.set_tags": (("id", "baseline"),),
    # Plan F F4.4: all three rollback tools name the baseline they act on. The
    # preview is a read tool, so it *must* be classified here (declaring the
    # param is not enforcing it); request/apply are writes and would otherwise
    # be gated against the tenant-wide role union (SEC-RB-01).
    "baseline.rollback_preview": (("id", "baseline"),),
    "baseline.rollback_request": (("id", "baseline"),),
    "baseline.rollback_apply": (("id", "baseline"),),
    "change_request.delete": (("id", "change_request"),),
    "change_request.outdate": (("id", "change_request"),),
    "change_request.reactivate": (("id", "change_request"),),
    "change_request.update": (("id", "change_request"),),
    "comment.create": (("artifact_id", "artifact"),),
    "comment.resolve": (("id", "comment"),),
    # Finding #4 (P1.2): both tools act on ``Artifact`` rows but still name no
    # workspace. ``artifact.move`` names one artifact; ``artifact.bulk_transition``
    # names a list of them, and the *first* resolvable id decides the workspace
    # the gate is evaluated against. A batch that mixes workspaces is refused by
    # the service as a request defect before any row moves, so one workspace is
    # the correct gate target for the whole call.
    "artifact.move": (("artifact_id", "artifact"),),
    "artifact.bulk_transition": (("ids", "artifact"),),
    # P6 visual groups: a group is an ``Artifact`` of type "Group", and its
    # members are requirements. Both ids name objects in the group's workspace;
    # without these entries an Editor in A could add/move/remove members of a
    # group living in B on the tenant-wide role fallback.
    "group.add_member": (
        ("group_id", "artifact"),
        ("requirement_id", "requirement"),
    ),
    "group.move_member": (
        ("group_id", "artifact"),
        ("requirement_id", "requirement"),
    ),
    "group.remove_member": (
        ("group_id", "artifact"),
        ("requirement_id", "requirement"),
    ),
    "context.related": _artifact_or_domain("artifact_id"),
    "diagram.outdate": (("id", "diagram"),),
    "diagram.reactivate": (("id", "diagram"),),
    "diagram.update": (("id", "diagram"),),
    # Plan F F2-T6 (ADR-026): document writes name their target by ``id``.
    "document.update": (("id", "document"),),
    "document.transition": (("id", "document"),),
    "document.outdate": (("id", "document"),),
    "document.reactivate": (("id", "document"),),
    "work_item.update": (("id", "work_item"),),
    "milestone.update": (("id", "milestone"),),
    "milestone.bind_baseline": (("id", "milestone"),),
    "milestone.record_audit": (("id", "milestone"),),
    "work_item.transition": (("id", "work_item"),),
    "work_item.set_progress": (("id", "work_item"),),
    # P2.8: the WorkItem soft-delete/restore pair names its target by ``id`` too.
    "work_item.outdate": (("id", "work_item"),),
    "work_item.reactivate": (("id", "work_item"),),
    "glossary.delete": (("id", "glossary"),),
    "glossary.outdate": (("id", "glossary"),),
    "glossary.reactivate": (("id", "glossary"),),
    "glossary.update": (("id", "glossary"),),
    "icd.update": (("id", "icd"),),
    "goal.delete": (("goal_id", "goal"),),
    "goal.outdate": (("goal_id", "goal"), ("id", "goal")),
    "goal.reactivate": (("goal_id", "goal"), ("id", "goal")),
    "goal.transition": (("goal_id", "goal"),),
    "goal.update": (("goal_id", "goal"),),
    "interview.abandon": (("session_id", "interview"),),
    "interview.answer": (("session_id", "interview"),),
    "interview.chat": (("session_id", "interview"),),
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
    # #1357: the requirement tools that name their target object by ``id`` must
    # resolve the gate from the requirement's own workspace — the same rule as
    # requirement.update/outdate above. Without these entries a
    # workspace-restricted key had "no target workspace" from the fence's point
    # of view, so a call against a requirement in the key's *own* workspace was
    # denied with the workspace-scope message (and a genuinely missing/typo'd
    # parameter was masked by the same message). The acceptance-criteria write
    # pair mirrors requirement.acceptance_criteria.get (the #1288 read fix).
    "requirement.acceptance_criteria.check": (("id", "requirement"),),
    "requirement.acceptance_criteria.set": (("id", "requirement"),),
    "requirement.suggest_level": (("id", "requirement"),),
    "risk.delete": (("id", "risk"),),
    "risk.outdate": (("id", "risk"),),
    "risk.reactivate": (("id", "risk"),),
    "risk.update": (("id", "risk"),),
    # B-01 (ADR-019 WP3): accept/reject name only the suggestion id. Without
    # these entries ``_scoped_gate_context`` resolves no target workspace and
    # the WRITE gate runs on the caller's tenant-wide role union, so an editor
    # in workspace A could decide a suggestion of workspace B. The suggestion
    # row carries the workspace directly (``ENTITY_SPECS["suggestion"]``).
    "suggestion.accept": (("id", "suggestion"),),
    "suggestion.reject": (("id", "suggestion"),),
    "test.derive_from_requirement": (("requirement_id", "requirement"),),
    "test.link": (("test_id", "testcase"), ("req_id", "requirement")),
    # #1373: the write sibling of test.get — names its target via
    # ``test_case_id`` (not ``id``). Without the entry no target workspace
    # resolved, so a fenced key was over-denied inside its own workspace and an
    # unfenced Editor in A could flip the review flag of a test case in B, whose
    # service gate checks only tenant + WRITE.
    "test.mark_reviewed": (("test_case_id", "testcase"),),
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
#: * ``memory.get`` (RFC #1002 PR B) — names only an entry id; the handler
#:   delegates to ``MemoryEntryService.get``, which applies ``MemoryPolicy``
#:   (own user memory, any active role in the owning workspace, or a role in
#:   the artifact's workspace). The workspace is resolved inside the service,
#:   so the dispatcher cannot pre-resolve it — same "enforced by the handler"
#:   class as the two above.
#: * ``memory.digest`` (RFC #1002 F6) — declares ``workspace_id`` as *required*,
#:   so the dispatcher already narrows and gates on it; the handler then calls
#:   ``MemoryEntryService.digest``, which re-checks the read matrix via
#:   ``MemoryPolicy`` (an ``artifact_id`` resolves its owning workspace inside
#:   the service). Listed explicitly so the coverage ratchet records the
#:   handler-side enforcement rather than inferring it from the schema alone.
TOOL_ENFORCED_WORKSPACE_SCOPE: frozenset[str] = frozenset(
    {
        "memory.query",
        "memory.list",
        "memory.get",
        "memory.digest",
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
#: * ``requirement_bundle.compression_status`` — polls a Celery task result
#:   through a tenant-ownership cache mapping the tool checks itself; the task
#:   id is not an artifact and has no workspace.
#: * ``traceability.suggest_links_status`` — same shape (#1197): polls the task
#:   dispatched by ``traceability.suggest_links`` (``async=true``) through the
#:   tenant-ownership cache mapping; the task id is not an artifact and has no
#:   workspace.
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
#: * ``attribute_definition.list`` — the tenant-wide global defaults are
#:   per (item_type, preset), not per workspace; there is no workspace to
#:   scope to. The handler is admin-gated in the service.
#: * ``attribute_catalog.list`` / ``attribute_catalog.search`` /
#:   ``attribute_catalog.export`` — the central catalog (WS5 #942) is a
#:   tenant-wide template library by design (spec section 8), not a workspace
#:   resource: entries carry no workspace and are shared across all of them.
#:   All three are admin-gated in ``AttributeCatalogService``, so a caller
#:   without tenant-wide admin standing cannot reach any row.
#: * ``attribute_migration.plan`` / ``attribute_migration.list_runs`` /
#:   ``attribute_migration.get_run`` — AWMS (WS7 #940) is tenant-wide admin
#:   tooling: ``plan`` is a pure schema validation + hash with no DB access at
#:   all, and the run history is keyed by the plan's scope (which may span
#:   several workspaces) rather than by one workspace. All three are admin-gated
#:   in ``AttributeMigrationService``; ``dry_run``/``apply``/``rollback`` are
#:   fail-closed write-gated in the tool registry.
#: * ``metrics.catalog`` (#1265) — the statistics catalogue is pure registry
#:   metadata (keys, titles, units, scopes, query contracts) with no workspace
#:   data and no DB access; it accepts no ``workspace_id``, so there is nothing
#:   to scope to. Its sibling ``metrics.get`` declares ``workspace_id`` as
#:   *required* and is therefore gated by the dispatcher like any other
#:   workspace-scoped read.
#: * ``tree_display_config.get`` (#1257) — without a ``workspace_id`` it reads
#:   only the caller's own selection (keyed by ``ctx.user_id``) and the
#:   tenant-wide default, neither of which is workspace data. Its
#:   ``workspace_id`` parameter is optional-but-enforced: when it *is* supplied
#:   the dispatcher narrows the roles to that workspace and runs the read gate
#:   (``_TOOL_TARGETS`` deliberately has no entry — the parameter *is* the
#:   target workspace, so a resolution table would add nothing), and the
#:   workspace override is only ever reached that way.
#: * ``create_form_definition.get`` (#1263) — the same shape as
#:   ``tree_display_config.get`` directly above: without a ``workspace_id`` it
#:   reads only the caller's own definition and the tenant-wide default, and a
#:   supplied ``workspace_id`` makes the dispatcher narrow the roles to it and
#:   run the read gate.
#: * ``preference.registry`` (Plan C / Q1) — the preference-key catalogue is
#:   code, not a workspace resource: it carries no workspace and performs no DB
#:   access, so there is nothing to scope to.
#: * ``preference.get`` (Plan C / Q1) — the same shape as
#:   ``tree_display_config.get``: without a ``workspace_id`` it resolves only
#:   the caller's own user values and the tenant-wide default (plus the
#:   registry defaults), neither of which is workspace data. A supplied
#:   ``workspace_id`` is what makes the workspace level participate, and then
#:   the dispatcher narrows the roles to it and runs the read gate — the
#:   parameter *is* the target workspace, so ``_TOOL_TARGETS`` adds nothing.
#: * ``tool.list_groups`` (MCP-Modernisierung Task 13) — pure catalogue
#:   metadata: the registry's group names and schema counts, derived from code
#:   with no DB access. There is no workspace (or tenant) data to scope to.
#: * ``workflow_default.list`` — the tenant-wide global workflow defaults
#:   (P1.8/M-11). They are keyed by ``(tenant, item_type, preset)`` and are the
#:   template every non-customized workspace definition inherits, so no
#:   workspace exists to scope to; the handler re-asserts tenant admin.
#: * ``workflow_default.get`` — the same table, one ``(item_type, preset)``
#:   pair; also workspace-less by contract, admin gate in the handler.
TENANT_SCOPED_READ_TOOLS: frozenset[str] = frozenset(
    {
        "admin.backup_list",
        "user.list",
        "workspace.list",
        "requirement_bundle.compression_status",
        "traceability.suggest_links_status",
        "audit.query",
        "requirement.query",
        "workspace.get_context",
        "prompt_template.get",
        "prompt_template.list",
        "prompt_variable.get",
        "prompt_variable.list",
        "artifact.search",
        "attribute_definition.list",
        "attribute_catalog.list",
        "attribute_catalog.search",
        "attribute_catalog.export",
        "attribute_migration.plan",
        "attribute_migration.list_runs",
        "attribute_migration.get_run",
        "metrics.catalog",
        "tree_display_config.get",
        "create_form_definition.get",
        "create_form_definition.export",
        "preference.registry",
        "preference.get",
        "tool.list_groups",
        "workflow_default.list",
        "workflow_default.get",
    }
)


#: Tools that filter their own result to the API key's fence instead of being
#: denied by the dispatcher (E1.3). Only honoured when the call names no
#: workspace (``scope_workspace_id is None``): a workspace-less list cannot
#: resolve a target, and the fail-closed fence would otherwise make the list
#: unreachable for every fenced key. The tool must narrow its result itself —
#: ``workspace.list`` does so through ``WorkspaceService.list_workspaces``.
FENCE_FILTERED_TOOLS: frozenset[str] = frozenset({"workspace.list"})


# ---------------------------------------------------------------------------
# Deliberately tenant-scoped write tools
# ---------------------------------------------------------------------------

#: Write tools that are safe **when no ``workspace_id`` is supplied and no
#: target object is named**. Each entry is a product decision backed by a read
#: of the handler/service, never a convenience bucket: a workspace-level write
#: whose target is merely *unknown* must be denied, not listed here.
#:
#: The set is what ``ToolRegistry._unscoped_write_denial`` consults, so an entry
#: means "this workspace-less call is admitted". A tool that *also* accepts a
#: ``workspace_id`` is still narrowed to it by the dispatcher (Case 1 of
#: ``_scoped_gate_context``) whenever the caller supplies one, and the strict
#: role gate applies then — the entry only covers the genuinely tenant-wide
#: shape. The ratchet asserts every entry is a live write tool.
#:
#: Tenant-wide configuration catalogues (no workspace resource at all):
#:
#: * ``attribute_definition.create`` / ``.delete`` / ``.export`` / ``.import`` —
#:   the tenant-wide global defaults are per (item_type, preset), not per
#:   workspace (see ``TENANT_SCOPED_READ_TOOLS``' ``attribute_definition.list``
#:   entry); the workspace-scoped siblings are the explicit
#:   ``*_workspace`` tools, which require ``workspace_id``. Admin-gated in
#:   ``AttributeDefinitionService``.
#: * ``attribute_catalog.create`` / ``.update`` / ``.deprecate`` / ``.import`` /
#:   ``.add_to_definition`` / ``.reorder`` — the central catalog (WS5 #942) is a
#:   tenant-wide template library by design (spec section 8): entries carry no
#:   workspace and are shared across all of them. ``add_to_definition`` and
#:   ``reorder`` accept an optional ``workspace_id`` to shape one workspace's
#:   definition instead of the global default; that path is dispatcher-gated.
#:   All six are admin-gated in ``AttributeCatalogService``.
#: * ``attribute_migration.apply`` / ``.dry_run`` / ``.rollback`` — AWMS
#:   (WS7 #940) is tenant-wide admin tooling: a plan is keyed by its scope,
#:   which may span several workspaces, so no single workspace can be the gate
#:   target. Admin-gated in ``AttributeMigrationService`` (same reasoning as the
#:   read-side ``attribute_migration.*`` entries).
#: * ``link_type.create`` — creates a *global* tenant link-type definition
#:   (``LinkTypeFacade.create_global``); it has no ``workspace_id`` parameter at
#:   all. ``link_type.update`` follows the same split: it updates the global
#:   definition without one and switches to ``update_workspace`` (dispatcher-
#:   gated) when a ``workspace_id`` is supplied. Both are ADMIN tier.
#: * ``prompt_template.create`` / ``.update`` — the template is tenant-wide by
#:   contract; an optional ``workspace_id`` selects the workspace override and
#:   is dispatcher-gated (mirror of the ``prompt_template.get`` / ``.list`` read
#:   entries). Admin tier (governance namespace).
#: * ``prompt_variable.set`` / ``.clear`` — the same variable catalog and the
#:   same optional-workspace split; admin tier.
#: * ``preference.set`` — writes the caller's *own* user-level values only
#:   (self-service, no workspace; the handler refuses any other level).
#: * ``preference.set_default`` — the tenant-wide default; a ``workspace_id``
#:   selects the workspace level and is dispatcher-gated (mirror of
#:   ``preference.get``).
#: * ``tree_display_config.set`` / ``create_form_definition.set`` /
#:   ``create_form_definition.import`` — without a ``workspace_id`` these write
#:   only the caller's own level or the tenant-wide default, neither of which is
#:   workspace data; a supplied ``workspace_id`` is what makes the workspace
#:   level participate and is then dispatcher-gated (mirror of the
#:   ``tree_display_config.get`` / ``create_form_definition.*`` read entries).
#:
#: Tenant administration (a user is not a workspace resource):
#:
#: * ``user.create`` / ``user.activate`` / ``user.deactivate`` /
#:   ``user.assign_tenant_admin`` / ``user.revoke_tenant_admin`` — the tenant
#:   user directory; scoping them to one workspace would break exactly the
#:   admin flows ``user.list`` is exempted for (assigning a user their first
#:   role). Tenant-admin-only, re-checked in ``UserService``.
#:
#: Task-status polls (the id is not an artifact and has no workspace):
#:
#: * ``requirement.check_consistency_status`` — polls the Celery task dispatched
#:   by ``requirement.check_consistency`` through the tenant-ownership cache
#:   mapping the tool checks itself (same shape as the read-side
#:   ``requirement_bundle.compression_status`` entry).
#:
#: Memory (workspace scope is resolved by ``MemoryPolicy``, not by the artifact
#: registry):
#:
#: * ``memory.export`` / ``memory.overview`` / ``memory.projection`` /
#:   ``memory.settings`` — the System-Admin memory surface; ``MemoryAdminService``
#:   (and, for ``settings``, the handler) re-assert System-Admin, so a
#:   workspace-less call cannot reach another tenant's or another workspace's
#:   memory without that standing. ``projection``'s optional ``workspace_id`` is
#:   dispatcher-gated.
#: * ``memory.write`` / ``memory.forget`` — ``MemoryEntryService`` applies
#:   ``MemoryPolicy``: ``scope="user"`` is the caller's own memory (no
#:   workspace), ``scope="workspace"`` requires ``workspace_id`` (dispatcher-
#:   gated), and ``scope="artifact"`` / an existing entry are checked against the
#:   owning workspace's roles inside the service — which is why the dispatcher
#:   cannot pre-resolve them (same "enforced by the service" class as the
#:   read-side ``memory.get`` / ``memory.query`` entries).
#:
#: Tenant-wide workflow configuration (no workspace resource at all):
#:
#: * ``workflow_default.initialize`` — creates the tenant-wide global workflow
#:   default for one ``(item_type, preset)`` pair (P1.8/M-11). It is the
#:   template inherited by every non-customized workspace definition; there is
#:   no workspace to gate on, and the handler re-asserts tenant admin exactly as
#:   REST's ``_require_admin`` does.
#: * ``workflow_default.add_state`` — appends a state to that global template
#:   and propagates it into every inheriting workspace; workspace-less and
#:   admin-gated in the handler.
#: * ``workflow_default.update_state`` — renames a state and/or toggles its
#:   freeze flag on the global template; workspace-less, admin-gated.
#: * ``workflow_default.delete_state`` — removes a state from the global
#:   template (fail-closed CONFLICT while a transition references it or a live
#:   item in an inheriting workspace occupies it); workspace-less, admin-gated.
#: * ``workflow_default.add_transition`` — appends an edge to the global
#:   template; workspace-less, admin-gated.
#: * ``workflow_default.update_transition`` — updates one edge's role/gate
#:   flags on the global template; workspace-less, admin-gated.
#: * ``workflow_default.delete_transition`` — removes one edge from the global
#:   template; workspace-less, admin-gated.
#:
#: The seven are the mutations REST publishes under
#: ``/api/v1/workflow-defaults/``; the corresponding reads
#: (``workflow_default.list`` / ``workflow_default.get``) are justified in
#: ``TENANT_SCOPED_READ_TOOLS``.
TENANT_SCOPED_WRITE_TOOLS: frozenset[str] = frozenset(
    {
        "attribute_catalog.add_to_definition",
        "attribute_catalog.create",
        "attribute_catalog.deprecate",
        "attribute_catalog.import",
        "attribute_catalog.reorder",
        "attribute_catalog.update",
        "attribute_definition.create",
        "attribute_definition.delete",
        "attribute_definition.export",
        "attribute_definition.import",
        "attribute_migration.apply",
        "attribute_migration.dry_run",
        "attribute_migration.rollback",
        "create_form_definition.import",
        "create_form_definition.set",
        "link_type.create",
        "link_type.update",
        "memory.export",
        "memory.forget",
        "memory.overview",
        "memory.projection",
        "memory.settings",
        "memory.write",
        "preference.set",
        "preference.set_default",
        "prompt_template.create",
        "prompt_template.update",
        "prompt_variable.clear",
        "prompt_variable.set",
        "requirement.check_consistency_status",
        "tree_display_config.set",
        "user.activate",
        "user.assign_tenant_admin",
        "user.create",
        "user.deactivate",
        "user.revoke_tenant_admin",
        "workflow_default.add_state",
        "workflow_default.add_transition",
        "workflow_default.delete_state",
        "workflow_default.delete_transition",
        "workflow_default.initialize",
        "workflow_default.update_state",
        "workflow_default.update_transition",
    }
)


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------


def _param_value(params: Mapping[str, Any], path: str) -> Any:
    """Return the value *path* names in *params*, walking nested objects.

    A plain name (``"id"``) is a direct lookup. A dotted name
    (``"draft.root_element_id"``) walks into the nested object — the registry
    needs it for a tool whose published schema wraps its target in a payload
    object (``architecture.decompose_commit``). Returns ``None`` as soon as a
    segment is absent or is not a mapping, which reads as "not supplied".
    """
    current: Any = params
    for segment in path.split("."):
        if not isinstance(current, Mapping):
            return None
        current = current.get(segment)
    return current


def _candidate_ids(raw: Any) -> tuple[Any, ...]:
    """Normalise a target parameter into the ids to probe, in order.

    A batch parameter (``artifact.bulk_transition``'s ``ids``) carries a list;
    every element is a candidate, so the first one that resolves decides the
    workspace. Every scalar is its own single candidate.
    """
    if isinstance(raw, (list, tuple)):
        return tuple(raw)
    return (raw,)


def resolve_target_workspace_id(
    tool_name: str, params: Mapping[str, Any]
) -> str | None:
    """Return the workspace owning the object ``tool_name`` targets.

    Args:
        tool_name: MCP tool identifier, e.g. ``"requirement.update"``.
        params: Caller-supplied parameters (``api_key`` already stripped).

    Returns:
        The owning workspace id as a string, or ``None`` when the tool names
        no resolvable object — a read tool then keeps its previous behaviour,
        a write tool is denied by ``ToolRegistry._unscoped_write_denial``.
    """
    targets = _TOOL_TARGETS.get(tool_name)
    if not targets:
        return None

    for param_name, entity_key in targets:
        for raw in _candidate_ids(_param_value(params, param_name)):
            if raw in (None, ""):
                continue
            try:
                value = UUID(str(raw))
            except (ValueError, TypeError, AttributeError):
                # A malformed id is the tool's own validation problem; it must
                # not short-circuit the remaining candidates.
                continue
            workspace_id = resolve_owning_workspace_id(entity_key, value)
            if workspace_id is not None:
                return str(workspace_id)
    return None


def target_param_error(tool_name: str, params: Mapping[str, Any]) -> str | None:
    """Explain a *parameter-level* cause for an unresolved target workspace.

    Only meaningful after :func:`resolve_target_workspace_id` returned ``None``
    for *tool_name*: it answers "was the target unresolvable because the call
    itself is malformed?" (#1357). Two cases qualify:

    * a supplied target parameter is not a UUID — a definite parameter defect,
      reported with priority over the next case, or
    * none of the tool's registered target parameters was supplied at all —
      the caller missed (or typo'd) the parameter naming the object.

    All target parameters are inspected, not just the first one: a malformed
    candidate stays reported even when another candidate was well-formed (its
    lookup simply found no row), so the call's actual defect is named instead
    of the workspace-scope text.

    A batch target (a list of ids) is well-formed as soon as one element parses
    — that is exactly the set :func:`resolve_target_workspace_id` probed — and a
    dotted target path (``draft.root_element_id``) is looked up the same way the
    resolver looks it up.

    Returns ``None`` when the failure is *not* parameter-level — i.e. every
    supplied target parameter is well-formed but resolved to no row (deleted
    object, foreign tenant). That failure must keep the caller's previous
    answer (the fail-closed workspace-fence denial), so a nonexistent object
    never becomes distinguishable from a fenced-out one through this diagnosis.

    The message names the tool, the expected parameter(s) and the received
    parameter keys, so an agent can spot a wrong parameter name (the case in
    #1357: ``suggestion_id`` sent where ``id`` is required) instead of being
    sent debugging the key's workspace fence.
    """
    targets = _TOOL_TARGETS.get(tool_name)
    if not targets:
        return None

    malformed: list[str] = []
    has_well_formed = False
    for param_name, _entity_key in targets:
        supplied = [
            raw
            for raw in _candidate_ids(_param_value(params, param_name))
            if raw not in (None, "")
        ]
        if not supplied:
            continue
        # A batch parameter is well-formed as soon as one of its ids parses:
        # the resolver probes the same set, so a single typo in a list of ids
        # is not the reason the whole call failed to resolve.
        well_formed_here = False
        for raw in supplied:
            try:
                UUID(str(raw))
            except (ValueError, TypeError, AttributeError):
                continue
            well_formed_here = True
            break
        if well_formed_here:
            has_well_formed = True
        else:
            malformed.append(param_name)

    if malformed:
        names = sorted(set(malformed))
        rendered = ", ".join(f"'{name}'" for name in names)
        return (
            f"Tool '{tool_name}' received malformed target parameter(s) "
            f"{rendered}: a target id must be a valid UUID. The target object "
            "could not be resolved; correct the parameter and retry."
        )

    if has_well_formed:
        # Every supplied target id was well-formed and tried against the
        # object lookup: the resolution failure is data-level (no such row in
        # this tenant), not a parameter problem.
        return None

    expected = sorted({name for name, _entity_key in targets})
    rendered_expected = " or ".join(f"'{name}'" for name in expected)
    received = sorted(str(key) for key in params)
    rendered_received = ", ".join(f"'{key}'" for key in received) if received else "(none)"
    return (
        f"Tool '{tool_name}' requires target parameter {rendered_expected} to "
        "name the object it acts on, but none was supplied "
        f"(received parameters: {rendered_received}). Check the parameter name "
        "and retry."
    )


__all__ = [
    "FENCE_FILTERED_TOOLS",
    "TENANT_SCOPED_READ_TOOLS",
    "TENANT_SCOPED_WRITE_TOOLS",
    "TOOL_ENFORCED_WORKSPACE_SCOPE",
    "resolve_target_workspace_id",
    "target_param_error",
]
