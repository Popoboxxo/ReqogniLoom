# Phase 1: MCP-CRUD-Vervollständigung Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose `.outdate`/`.reactivate` as MCP tools on every entity type, make `.list`/`.query` MCP endpoints default to excluding outdated items everywhere, and add MCP access for 4 previously-missing entity types (ChangeRequest, Diagram: full CRUD+outdate; CustomField, Workspace-Preferences: read+list only).

**Architecture:** Builds entirely on Phase 0's `workflow.services.outdate()`/`reactivate()`/`outdated_item_ids()` (already merged). No new domain concepts — this phase is pure MCP-surface + service-layer-filter wiring. Two mechanical patterns repeat throughout: (a) add `.outdate`/`.reactivate` MCP handlers that call the Phase 0 primitives, and (b) make every `.list`/`.query` MCP tool forward an `include_outdated` param down to a service-layer filter that uses `outdated_item_ids()` (for un-mirrored entities) or `.exclude(status="outdated")` (for mirrored entities).

**Tech Stack:** Django 4.2, Python 3.x, pytest, `backend/mcp_server/` (JSON-RPC 2.0 tool groups).

## Global Constraints

- No REQ-ID in commit messages (req-traceability disabled).
- Every new write tool name (`.outdate`, `.reactivate`, `.create`, `.update`, `.delete` on any newly-wired entity) MUST be added to `_WRITE_TOOL_PREFIXES` in `backend/mcp_server/tool_registry.py` — a tool not listed there silently bypasses RBAC (Editor/Admin gate). This is the single most important constraint in this phase; missing it is a security gap, not a cosmetic bug.
- `.delete` is kept as a backward-compatible alias for `.outdate` on every entity that already had a `.delete` MCP tool (do not remove `.delete`, just add `.outdate`/`.reactivate` alongside it, both routing to the same handler) — avoids breaking existing MCP clients.
- Every list/query default: `include_outdated=false` unless explicitly passed `true`.
- Follow existing per-file conventions exactly: `ToolResult.ok(...)`/`ToolResult.error(CODE, message)` return shape, `NotFoundError`/`PermissionDeniedError` → `"NOT_FOUND"`/`"PERMISSION_DENIED"` mapping, `write_mcp_audit(...)` call on every write handler (see `requirements.py`'s `_handle_create`/`_handle_update` for the exact pattern to copy).
- Out of scope for this plan (explicitly deferred): `context.test_coverage`, `context.change_impact`, `workspace.llm_system_prompt`, token-budget/depth params on `workspace.get_context` (all Phase 2). Review-endpoint work (Phase 5) is untouched here even though `.outdate`/`.reactivate` overlaps conceptually with review — this phase only adds the outdate/reactivate verbs, not review workflow.

---

## Task 1: Fix pre-existing gaps found during Phase 1 research (prerequisite cleanup)

Three real gaps surfaced while grounding this plan that must be fixed before the MCP wiring makes sense — otherwise Phase 1's new `.query`/`.outdate` tools would either crash or silently misbehave for these 3 entities.

**Files:**
- Modify: `backend/application/stakeholder_need_service.py` (delete method + list filter)
- Modify: `backend/application/risk_service.py` (list filter, currently has none)
- Modify: `backend/application/issue_service.py` (list filter, currently has none)
- Modify: `backend/diagram/services.py` (`delete_diagram`)
- Test: `backend/application/tests/test_stakeholder_need_service.py`, `backend/application/tests/test_risk_service.py`, `backend/application/tests/test_issue_service.py`, `backend/diagram/tests/test_services.py` (confirm exact test file name before editing — check `diagram/tests/` directory listing first)

**Interfaces:**
- Consumes: `workflow.services.outdate(item_id, item_type, workspace_id, ctx, *, reason="") -> TransitionResult`, `workflow.services.outdated_item_ids(item_type, *, tenant_id=None) -> QuerySet[UUID]` (both from Phase 0, already merged).

- [ ] **Step 1: Write the failing test for StakeholderNeed delete-via-outdate**

```python
# add to backend/application/tests/test_stakeholder_need_service.py
@pytest.mark.django_db
def test_delete_calls_outdate_not_lifecycle_status(need_with_workflow, auth_ctx):
    from application.stakeholder_need_service import StakeholderNeedService

    item_id, workspace_id = need_with_workflow
    StakeholderNeedService().delete(need_id=item_id, ctx=auth_ctx)

    from workflow.models import WorkflowItemState
    item_state = WorkflowItemState.objects.get(item_id=item_id, item_type="StakeholderNeed")
    assert item_state.current_state == "outdated"
```

If a `need_with_workflow` fixture doesn't already exist in this test file, check the file's existing fixtures first (follow whatever pattern Phase 0's `test_requirement_service.py` used for its own `requirement_with_workflow`-style setup) and add an equivalent one here — do not invent a fixture name that collides with an existing one.

- [ ] **Step 2: Run test to verify it fails**

Run (from project root):
```bash
docker-compose build backend
docker-compose run --rm backend python -m pytest application/tests/test_stakeholder_need_service.py -k test_delete_calls_outdate_not_lifecycle_status -v
```
Expected: FAIL (item_state.current_state is not "outdated", since delete() still writes lifecycle_status directly)

- [ ] **Step 3: Replace the delete body in `stakeholder_need_service.py`'s `delete()` method (around line 224-246)**

Find:
```python
need.lifecycle_status = "deleted"
need.save(update_fields=["lifecycle_status"])
```
Replace with:
```python
from workflow.services import outdate  # add to top-of-file imports if not already present

outdate(
    item_id=need.id,
    item_type="StakeholderNeed",
    workspace_id=need.workspace_id,
    ctx=ctx,
    reason="deleted via needs.delete",
)
```
(Verify the exact local variable name holding the fetched `StakeholderNeed` instance and the `ctx` parameter name in the surrounding method signature before editing — match what's actually there, don't assume `need`/`ctx` are the literal names without checking.)

- [ ] **Step 4: Update `list_by_workspace`'s filter (around line 142-155)**

Find:
```python
if not include_deleted:
    needs = needs.exclude(lifecycle_status="deleted")
```
Replace with:
```python
if not include_deleted:
    needs = needs.exclude(status="outdated")
```
(`StakeholderNeed` is registered in `_STATUS_MIRROR_MODELS`, so `outdate()` writes `"outdated"` into its `status` field — same pattern as Phase 0's Requirement fix.)

- [ ] **Step 5: Run test to verify it passes**

Run: `docker-compose run --rm backend python -m pytest application/tests/test_stakeholder_need_service.py -v`
Expected: all pass, including the new test.

- [ ] **Step 6: Add outdated-filtering to `RiskService.list_risks` and `IssueService.list_issues`**

Both currently have zero outdated-exclusion logic (`Risk`/`Issue` have no `lifecycle_status` field and are not registered with a status mirror covering "exclude from list" logic today — they DO have `status` mirrored via Phase 0, but nothing filters on it in list methods). Read each method's current signature and body first, then add an `include_deleted: bool = False` param (matching the naming convention used by `RequirementService.list_requirements`/`StakeholderNeedService.list_by_workspace`) and, when `False`, `.exclude(status="outdated")` on the returned queryset — both `Risk` and `Issue` are registered in `_STATUS_MIRROR_MODELS` (Phase 0), so this is the same lightweight mirrored-field filter, not the `outdated_item_ids()` subquery pattern.

- [ ] **Step 7: Write tests proving Risk/Issue list methods now exclude outdated items**

```python
# add to backend/application/tests/test_risk_service.py
@pytest.mark.django_db
def test_list_risks_excludes_outdated_by_default(risk, auth_ctx):
    from application.risk_service import RiskService
    svc = RiskService()
    svc.delete_risk(risk_id=risk.id, ctx=auth_ctx)

    results = svc.list_risks(workspace_id=risk.workspace_id, ctx=auth_ctx)
    assert risk.id not in [r.id for r in results]

    results_incl = svc.list_risks(workspace_id=risk.workspace_id, ctx=auth_ctx, include_deleted=True)
    assert risk.id in [r.id for r in results_incl]
```
Write the equivalent for `IssueService.list_issues`/`test_issue_service.py`. Adjust the exact call signature (`workspace_id`/`ctx` param order, keyword vs positional) to match what `list_risks`/`list_issues` actually declare — read the method signature before writing the call.

- [ ] **Step 8: Run both test files, verify pass**

Run: `docker-compose run --rm backend python -m pytest application/tests/test_risk_service.py application/tests/test_issue_service.py -v`

- [ ] **Step 9: Redirect `diagram/services.py`'s `delete_diagram` through `outdate()`**

Current (around line 190-206):
```python
def delete_diagram(diagram_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
    diagram = Diagram.objects.get(id=diagram_id, tenant_id=tenant_id)
    diagram.delete()
```
This function's signature takes `tenant_id`, not a full `ctx`/`workspace_id` pair like the `application/` services — check how callers of this function obtain `ctx`/`AuthContext` (search `delete_diagram(` call sites, likely in `rest_api/diagram_views.py` or similar) to determine whether to change this function's signature to accept `ctx: AuthContext` and `workspace_id`, or whether to look up `diagram.workspace_id` from the fetched instance and construct enough of an `AuthContext`-like call from what's already available. Prefer the minimal change: keep the `tenant_id` param, add the outdate call using `diagram.workspace_id` (already on the fetched instance) and pass through whatever `ctx`-equivalent the caller already has available (check the call site to see if a real `AuthContext` is accessible there and can be threaded through as a new parameter):

```python
def delete_diagram(diagram_id: uuid.UUID, tenant_id: uuid.UUID, ctx: "AuthContext") -> None:
    from workflow.services import outdate

    diagram = Diagram.objects.get(id=diagram_id, tenant_id=tenant_id)
    outdate(
        item_id=diagram.id,
        item_type="Diagram",
        workspace_id=diagram.workspace_id,
        ctx=ctx,
        reason="deleted via diagram delete",
    )
```
Update the call site(s) to pass `ctx` through. If no `AuthContext` is available at any current call site (e.g. this is only ever called from a context that only has `tenant_id`, not a full ctx), report this as a NEEDS_CONTEXT blocker rather than fabricating a fake ctx — the MCP tool wiring in Task 5 will need a real `ctx` regardless, so this dependency must be resolved here first.

- [ ] **Step 10: Write a test proving `delete_diagram` no longer hard-deletes**

```python
# add to the diagram app's existing test file for services.py (find exact name first, e.g. backend/diagram/tests/test_services.py)
@pytest.mark.django_db
def test_delete_diagram_calls_outdate_not_hard_delete(diagram_with_workflow, auth_ctx):
    from diagram.services import delete_diagram
    from diagram.models import Diagram

    diagram_id, tenant_id = diagram_with_workflow
    delete_diagram(diagram_id, tenant_id, ctx=auth_ctx)

    assert Diagram.objects.filter(id=diagram_id).exists()  # not hard-deleted

    from workflow.models import WorkflowItemState
    item_state = WorkflowItemState.objects.get(item_id=diagram_id, item_type="Diagram")
    assert item_state.current_state == "outdated"
```

- [ ] **Step 11: Run diagram tests, verify pass**

Run: `docker-compose run --rm backend python -m pytest diagram/ -v`

- [ ] **Step 12: Full regression + commit**

Run: `docker-compose run --rm backend python -m pytest application/tests/ diagram/ workflow/ -q` — expect no new failures (the known pre-existing `test_test_service.py` flake and `test_services_facade.py` flake may still appear in isolation, unrelated).

```bash
git add backend/application/stakeholder_need_service.py backend/application/risk_service.py backend/application/issue_service.py backend/diagram/services.py backend/application/tests/test_stakeholder_need_service.py backend/application/tests/test_risk_service.py backend/application/tests/test_issue_service.py backend/diagram/tests/
git commit -m "fix: route StakeholderNeed/Diagram delete through outdate(), add missing outdated-filters to Risk/Issue list methods"
```

---

## Task 2: `GenericCrudToolGroup` — add `.outdate`, `.reactivate`, `.query`

**Files:**
- Modify: `backend/mcp_server/tools/generic.py`
- Test: `backend/mcp_server/tests/test_generic_tool_group.py`

**Interfaces:**
- Produces: `{prefix}.outdate`, `{prefix}.reactivate`, `{prefix}.query` tool names for every entity using `GenericCrudToolGroup` (today: adr, risk, issue, glossary; after Task 4, also change_request).
- Consumes: `workflow.services.outdate`/`reactivate` (Phase 0), each entity's own `list_*`/`outdated`-aware service method (Task 1 for risk/issue; already-correct for adr/glossary).

- [ ] **Step 1: Write failing tests for the 3 new generic tool-group verbs**

```python
# add to backend/mcp_server/tests/test_generic_tool_group.py
def test_outdate_tool_calls_workflow_outdate(monkeypatch):
    # Follow this file's existing pattern for constructing a GenericCrudToolGroup
    # instance + mock service + auth_context (see an existing test for .delete or
    # .create in this same file and mirror its setup exactly).
    ...

def test_reactivate_tool_calls_workflow_reactivate(monkeypatch):
    ...

def test_query_tool_defaults_to_excluding_outdated(monkeypatch):
    ...
```
Read the existing tests in this file first (there is at least one for `.delete` already, per Task 1's grounding) and write these 3 following the exact same mocking/assertion style — do not invent a new test pattern for this file.

- [ ] **Step 2: Run to verify failure**

Run: `docker-compose run --rm backend python -m pytest mcp_server/tests/test_generic_tool_group.py -v`

- [ ] **Step 3: Add `.outdate`/`.reactivate`/`.query` to `_TOOL_MAP` and 3 new handlers**

In `backend/mcp_server/tools/generic.py`, extend `_TOOL_MAP` (currently `read`/`create`/`update`/`delete` per `__init__`, lines ~54-59):
```python
self._TOOL_MAP = {
    f"{prefix}.read": "_handle_read",
    f"{prefix}.create": "_handle_create",
    f"{prefix}.update": "_handle_update",
    f"{prefix}.delete": "_handle_delete",       # kept as alias, unchanged
    f"{prefix}.outdate": "_handle_outdate",     # new
    f"{prefix}.reactivate": "_handle_reactivate",  # new
    f"{prefix}.query": "_handle_query",         # new
}
```

Add the 3 new handler methods, following `_handle_delete`'s existing shape (lines ~163-169) for error handling:
```python
def _handle_outdate(self, *, params, auth_context, api_key):
    obj_id = require_uuid(params, "id")
    reason = params.get("reason", "")
    workspace_id = params.get("workspace_id")  # confirm: does _handle_delete already resolve workspace_id from the fetched object, or does it require it as a param? Match that existing convention.
    try:
        from workflow.services import outdate
        outdate(item_id=obj_id, item_type=self._item_type, workspace_id=workspace_id, ctx=auth_context, reason=reason)
    except Exception as exc:
        return ToolResult.error("INTERNAL_ERROR", str(exc))
    return ToolResult.ok({"id": str(obj_id), "status": "outdated"})

def _handle_reactivate(self, *, params, auth_context, api_key):
    obj_id = require_uuid(params, "id")
    workspace_id = params.get("workspace_id")
    try:
        from workflow.services import reactivate
        result = reactivate(item_id=obj_id, item_type=self._item_type, workspace_id=workspace_id, ctx=auth_context)
    except ValueError as exc:
        return ToolResult.error("INVALID_STATE", str(exc))
    except Exception as exc:
        return ToolResult.error("INTERNAL_ERROR", str(exc))
    return ToolResult.ok({"id": str(obj_id), "status": result.new_state})

def _handle_query(self, *, params, auth_context, api_key):
    include_outdated = params.get("include_outdated", False)
    workspace_id = require_uuid(params, "workspace_id")
    list_method = self._resolve_method(self._service, self.prefix, "list") or self._resolve_method(self._service, self.prefix, "query")
    try:
        results = list_method(ctx=auth_context, workspace_id=workspace_id, include_deleted=include_outdated)
    except Exception as exc:
        return ToolResult.error("INTERNAL_ERROR", str(exc))
    return ToolResult.ok({"items": [self._to_dict(r) for r in results]})
```

**Note for the implementer (verify before finalizing):** `self._item_type` — check whether `GenericCrudToolGroup.__init__` already stores an `item_type` string (needed to call `outdate(item_type=...)`), or only stores `prefix` + `service`. The `workflow` `item_type` strings are PascalCase (`"Adr"`, `"Risk"`, `"Issue"`, `"GlossaryTerm"`) while `prefix` is lowercase (`"adr"`, `"risk"`, `"issue"`, `"glossary"`) — these do NOT match 1:1 (`"glossary"` prefix vs `"GlossaryTerm"` item_type), so `GenericCrudToolGroup`'s constructor call sites (Task 4 will add one more) need an explicit `item_type` argument passed in, distinct from `prefix`. Check `tool_registry.py`'s existing `GenericCrudToolGroup("glossary", GlossaryService)` call — if there's no `item_type` param today, add one: `GenericCrudToolGroup("glossary", GlossaryService, item_type="GlossaryTerm")`, defaulting to `prefix.capitalize()` if not given (works for adr→"Adr", risk→"Risk", issue→"Issue"; glossary needs the explicit override).

**Also verify:** does `_to_dict` (or equivalent serialization helper) already exist on this class for `_handle_read`/`_handle_create`'s responses? Reuse it — don't invent a second serialization path for `_handle_query`.

- [ ] **Step 4: Run tests to verify pass**

Run: `docker-compose run --rm backend python -m pytest mcp_server/tests/test_generic_tool_group.py -v`

- [ ] **Step 5: Add all new write tool names to RBAC gate**

In `backend/mcp_server/tool_registry.py`, find `_WRITE_TOOL_PREFIXES` (module-level tuple, ~lines 54-98) and add: `"adr.outdate"`, `"adr.reactivate"`, `"risk.outdate"`, `"risk.reactivate"`, `"issue.outdate"`, `"issue.reactivate"`, `"glossary.outdate"`, `"glossary.reactivate"` (Task 4 will add `change_request.outdate`/`.reactivate` separately). `.query` tools are read-only, do NOT add to this list.

- [ ] **Step 6: Write a test proving RBAC gate covers the new tools**

Follow whatever existing test proves `adr.delete` is Editor/Admin-gated (search `test_tool_registry.py` for `_WRITE_TOOL_PREFIXES` coverage) and add an equivalent assertion for `adr.outdate` (viewer role → `PERMISSION_DENIED`).

- [ ] **Step 7: Run full mcp_server suite + commit**

Run: `docker-compose run --rm backend python -m pytest mcp_server/tests/ -q`
```bash
git add backend/mcp_server/tools/generic.py backend/mcp_server/tool_registry.py backend/mcp_server/tests/test_generic_tool_group.py backend/mcp_server/tests/test_tool_registry.py
git commit -m "feat: add outdate/reactivate/query MCP tools to GenericCrudToolGroup"
```

---

## Task 3: Requirement/Architecture/Test/Needs — add `.outdate`/`.reactivate`, forward `include_outdated` on `.query`

**Files:**
- Modify: `backend/mcp_server/tools/requirements.py`, `backend/mcp_server/tools/architecture.py`, `backend/mcp_server/tools/tests.py`, `backend/mcp_server/tools/needs.py`
- Test: matching test files in `backend/mcp_server/tests/`

**Interfaces:**
- Consumes: `workflow.services.outdate`/`reactivate`; each service's `list_*(..., include_deleted: bool)` (already correct for Requirement/Architecture/StakeholderNeed post-Task-1; Task 1 also added it for none of these 4 directly since Test needs its own addition — see Step 5 below).

- [ ] **Step 1: Add `.outdate`/`.reactivate` to `requirements.py`, mirroring `_handle_get`'s error-handling shape (shown in this plan's research)**

```python
def _handle_outdate(
    self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
) -> ToolResult:
    """requirement.outdate — soft-delete via workflow engine."""
    req_id = require_uuid(params, "id")
    reason = params.get("reason", "")
    try:
        req = self._service.get_requirement(req_id, auth_context)
    except NotFoundError as exc:
        return ToolResult.error("NOT_FOUND", str(exc))
    from workflow.services import outdate
    outdate(item_id=req_id, item_type="Requirement", workspace_id=req.workspace_id, ctx=auth_context, reason=reason)
    write_mcp_audit("requirement.outdate", req_id, auth_context, api_key)  # match exact call signature used by _handle_update
    return ToolResult.ok({"id": str(req_id), "status": "outdated"})

def _handle_reactivate(
    self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
) -> ToolResult:
    """requirement.reactivate — restore a previously outdated requirement."""
    req_id = require_uuid(params, "id")
    try:
        req = self._service.get_requirement(req_id, auth_context)
    except NotFoundError as exc:
        return ToolResult.error("NOT_FOUND", str(exc))
    from workflow.services import reactivate
    try:
        result = reactivate(item_id=req_id, item_type="Requirement", workspace_id=req.workspace_id, ctx=auth_context)
    except ValueError as exc:
        return ToolResult.error("INVALID_STATE", str(exc))
    write_mcp_audit("requirement.reactivate", req_id, auth_context, api_key)
    return ToolResult.ok({"id": str(req_id), "status": result.new_state})
```
Add both to `requirements.py`'s tool-map/registration structure (find how `.get`/`.create`/etc. are mapped — likely a dict similar to `GenericCrudToolGroup`'s `_TOOL_MAP`, confirm the exact structure in this file before editing since "own" tool groups may wire this differently, e.g. an explicit `if/elif` dispatcher instead of a dict).

- [ ] **Step 2: Repeat Step 1's pattern for `architecture.py` (item_type="ArchitectureElement") and `tests.py` (item_type="TestCase")**

Use the equivalent get-method for each (`get_architecture_element`/`get_test_case` — verify exact method names before writing) and the same outdate/reactivate/audit shape.

- [ ] **Step 3: Repeat for `needs.py` (item_type="StakeholderNeed")** — this one already HAS an `include_deleted` pattern to mirror for consistency (per this plan's research, `needs.py` already exposes `include_deleted` correctly elsewhere) — use its existing get-method (verify exact name, likely `get_need` or similar).

- [ ] **Step 4: Write tests for all 8 new handlers (outdate+reactivate × 4 entities)**, following each file's existing test conventions (check `mcp_server/tests/test_requirements_tool_group.py`-equivalent file names — confirm exact test file names for each of the 4, they may not follow an identical naming pattern).

- [ ] **Step 5: Forward `include_outdated` on all 4 `.query` handlers**

For `requirement.query`/`architecture.query`/`needs.query` (whose underlying services already support `include_deleted`): find each `_handle_query`/`_handle_get_query`-equivalent method and add forwarding of `params.get("include_outdated", False)` into the service call's `include_deleted` kwarg — today these MCP handlers likely call the service's list method WITHOUT this param at all (confirmed in research for requirement/architecture), so this is a small addition to an existing call, not a new method.

For `test.query`: `TestService.list_test_cases` has **no outdated-filtering logic at all** yet (confirmed in research) — add it first (mirror Task 1's Risk/Issue pattern: `TestCase` is in `_STATUS_MIRROR_MODELS`, so use `.exclude(status="outdated")` when `include_deleted=False`), then wire `test.query`'s handler to forward `include_outdated`.

- [ ] **Step 6: Write tests proving each `.query` tool respects `include_outdated`**

For each of the 4: create an item, outdate it via the service, call the MCP `.query` handler with default params (assert item absent), then with `include_outdated=True` (assert item present).

- [ ] **Step 7: Add new write tool names to `_WRITE_TOOL_PREFIXES`**

`"requirement.outdate"`, `"requirement.reactivate"`, `"architecture.outdate"`, `"architecture.reactivate"`, `"test.outdate"`, `"test.reactivate"`, `"needs.outdate"`, `"needs.reactivate"`.

- [ ] **Step 8: Run full test suite for these 4 modules + commit**

Run: `docker-compose run --rm backend python -m pytest mcp_server/tests/ application/tests/test_test_service.py -q`
```bash
git add backend/mcp_server/tools/requirements.py backend/mcp_server/tools/architecture.py backend/mcp_server/tools/tests.py backend/mcp_server/tools/needs.py backend/application/test_service.py backend/mcp_server/tool_registry.py backend/mcp_server/tests/
git commit -m "feat: add outdate/reactivate MCP tools and include_outdated query filtering to requirement/architecture/test/needs"
```

---

## Task 4: ChangeRequest — new MCP tool group (full CRUD + outdate)

**Files:**
- Modify: `backend/mcp_server/tool_registry.py` (`_ensure_groups()`, `_WRITE_TOOL_PREFIXES`)
- Test: create `backend/mcp_server/tests/test_change_request_tool_group.py` (or extend an existing generic-group test file if the project convention shares one file across generic-backed entities — check `test_generic_tool_group.py` first, it may already parametrize across adr/risk/issue/glossary and should gain `change_request` as one more parametrized case rather than a new file)

**Interfaces:**
- Consumes: `ChangeRequestService` (already has full CRUD + `delete_change_request` already routed through `outdate()` per Phase 0) via `GenericCrudToolGroup` (Task 2's extended version).

- [ ] **Step 1: Write a failing test asserting `change_request.*` tools are registered**

```python
# in whichever file Task 2's Step 1 investigation determined is the right location
def test_change_request_tools_registered():
    registry = _build_registry()  # match this file's existing helper
    tool_names = {t["name"] for t in registry.list_tools()}
    assert "change_request.create" in tool_names
    assert "change_request.outdate" in tool_names
    assert "change_request.query" in tool_names
```

- [ ] **Step 2: Run to verify failure**

- [ ] **Step 3: Register the tool group**

In `backend/mcp_server/tool_registry.py`'s `_ensure_groups()`, add (matching the existing adr/risk/issue/glossary registration block found in this plan's research, ~lines 305-308):
```python
"change_request": GenericCrudToolGroup("change_request", ChangeRequestService, item_type="ChangeRequest"),
```
Add the corresponding import for `ChangeRequestService` at the top of the file if not already present.

- [ ] **Step 4: Add write tool names to `_WRITE_TOOL_PREFIXES`**

`"change_request.create"`, `"change_request.update"`, `"change_request.outdate"`, `"change_request.reactivate"`.

- [ ] **Step 5: Run test to verify pass, plus a full create→outdate→query round-trip test**

```python
@pytest.mark.django_db
def test_change_request_create_outdate_query_roundtrip(auth_ctx_admin):
    # follow this file's existing DB-integration test pattern (Task 2 will have
    # established one for adr/risk/issue via GenericCrudToolGroup already)
    ...
```

- [ ] **Step 6: Commit**

```bash
git add backend/mcp_server/tool_registry.py backend/mcp_server/tests/
git commit -m "feat: register ChangeRequest as an MCP tool group with full CRUD + outdate"
```

---

## Task 5: Diagram — new MCP tool group (full CRUD + outdate)

**Files:**
- Create: `backend/mcp_server/tools/diagram.py` (new "own" tool group, since `diagram/services.py` is module-level functions, not a class `GenericCrudToolGroup` can wrap directly)
- Modify: `backend/mcp_server/tool_registry.py`
- Test: create `backend/mcp_server/tests/test_diagram_tool_group.py`

**Interfaces:**
- Consumes: `diagram.services.create_diagram`, `update_diagram`, `delete_diagram` (Task 1's outdate-routed version), `list_versions`, plus a `list`/`query` capability — check whether `diagram/services.py` or `diagram/manager.py`'s `DiagramManager` already has a workspace-scoped list function; if neither does, add a minimal `list_diagrams(workspace_id, tenant_id, include_deleted=False)` function to `diagram/services.py` following the file's existing module-function style (not a new class), filtering via `workflow.services.outdated_item_ids("Diagram", tenant_id=tenant_id)` since `Diagram` has no status mirror (confirmed in research).

- [ ] **Step 1: Confirm exact `Diagram` model fields needed for create/update params** (already known from research: `name`, `workspace_id`, `diagram_type`, `description`, plus first/next `DiagramVersion`'s `payload_format`+`payload`) — re-verify against `backend/diagram/models.py` directly before writing the tool schema, since the research pass didn't read the full model file.

- [ ] **Step 2: Write failing tests for `diagram.create`/`.get`/`.update`/`.outdate`/`.reactivate`/`.query`** in `backend/mcp_server/tests/test_diagram_tool_group.py`, following the exact structural pattern of `requirements.py`'s test file (own tool group, not generic) as the closest analog.

- [ ] **Step 3: Implement `backend/mcp_server/tools/diagram.py`** — a new `DiagramToolGroup` class, following `RequirementsToolGroup`'s file structure (constructor takes nothing entity-service-specific since `diagram/services.py` uses module functions — import them directly), with handlers: `_handle_create`, `_handle_get`, `_handle_update`, `_handle_outdate`, `_handle_reactivate`, `_handle_query`, each calling the corresponding `diagram.services.*` function and following the `ToolResult.ok`/`.error` conventions used throughout this codebase.

- [ ] **Step 4: Register in `tool_registry.py`**

```python
"diagram": DiagramToolGroup(),
```
(Adjust the constructor call to whatever `DiagramToolGroup.__init__` actually ends up requiring.)

- [ ] **Step 5: Add write tool names to `_WRITE_TOOL_PREFIXES`**

`"diagram.create"`, `"diagram.update"`, `"diagram.outdate"`, `"diagram.reactivate"`.

- [ ] **Step 6: Run tests, verify pass, commit**

Run: `docker-compose run --rm backend python -m pytest mcp_server/tests/test_diagram_tool_group.py diagram/ -v`
```bash
git add backend/mcp_server/tools/diagram.py backend/diagram/services.py backend/mcp_server/tool_registry.py backend/mcp_server/tests/test_diagram_tool_group.py
git commit -m "feat: add Diagram MCP tool group with full CRUD + outdate"
```

---

## Task 6: CustomField — read+list only MCP tool group

**Files:**
- Create: `backend/mcp_server/tools/custom_field.py`
- Modify: `backend/mcp_server/tool_registry.py`
- Test: create `backend/mcp_server/tests/test_custom_field_tool_group.py`

**Interfaces:**
- Consumes: `CustomFieldService.list_definitions(ctx, workspace_id)`, `get_definition(ctx, definition_id)` (both already exist per research) — deliberately do NOT wire `create_definition`/`update_definition`/`delete_definition` (out of scope per the design spec's decision: CustomField gets read+list only, to protect against accidental workspace misconfiguration by an AI agent).

- [ ] **Step 1: Write failing tests for `custom_field.get`/`.query`, and a test PROVING `.create`/`.update`/`.delete`/`.outdate` are NOT registered**

```python
def test_custom_field_write_tools_not_registered():
    registry = _build_registry()
    tool_names = {t["name"] for t in registry.list_tools()}
    assert "custom_field.get" in tool_names
    assert "custom_field.query" in tool_names
    assert "custom_field.create" not in tool_names
    assert "custom_field.update" not in tool_names
    assert "custom_field.delete" not in tool_names
```

- [ ] **Step 2: Run to verify current failure (tool group doesn't exist yet at all)**

- [ ] **Step 3: Implement `CustomFieldToolGroup`** in `backend/mcp_server/tools/custom_field.py` with only `_handle_get`/`_handle_query`, wired to `CustomFieldService.get_definition`/`list_definitions`.

- [ ] **Step 4: Register in `tool_registry.py`** — `"custom_field": CustomFieldToolGroup()`. Do NOT add anything to `_WRITE_TOOL_PREFIXES` for this prefix (read-only, no write tools exist to gate).

- [ ] **Step 5: Run tests, verify pass, commit**

```bash
git add backend/mcp_server/tools/custom_field.py backend/mcp_server/tool_registry.py backend/mcp_server/tests/test_custom_field_tool_group.py
git commit -m "feat: add read-only CustomField MCP tool group"
```

---

## Task 7: Workspace-Preferences — read-only extension on existing `workspace.*` namespace

**Design decision (made during planning, not re-litigated with the user given no natural entity exists):** rather than inventing a synthetic `workspace_preferences` prefix with no backing model, extend the existing `AdminToolGroup` (which already owns the `workspace.*` prefix) with one new read-only tool: `workspace.get_preferences`.

**Files:**
- Modify: whichever file currently implements `AdminToolGroup` (confirm exact file — likely `backend/mcp_server/tools/admin.py`, per Task 1's research referencing `mcp_server.tools.admin.write_mcp_audit`)
- Test: extend that tool group's existing test file

**Interfaces:**
- Consumes: `Workspace` model fields directly (`preset`, `ai_prompts`, `decomposition_link_type`, `default_link_type`, `language`) via `WorkspaceService` (check whether a `get_workspace`-style read method already exists to reuse before writing a new query).

- [ ] **Step 1: Write a failing test for `workspace.get_preferences`**

```python
def test_get_preferences_returns_workspace_config_fields(auth_ctx_admin):
    # follow AdminToolGroup's existing test setup pattern
    response = _post(handler, "workspace.get_preferences", {"workspace_id": str(WORKSPACE_ID)})
    assert "result" in response
    assert "preset" in response["result"]
    assert "ai_prompts" in response["result"]
    assert "language" in response["result"]
```

- [ ] **Step 2: Run to verify failure**

- [ ] **Step 3: Implement `_handle_get_preferences`**

```python
def _handle_get_preferences(self, *, params, auth_context, api_key):
    workspace_id = require_uuid(params, "workspace_id")
    try:
        workspace = self._workspace_service.get_workspace(workspace_id, auth_context)  # confirm exact method name
    except NotFoundError as exc:
        return ToolResult.error("NOT_FOUND", str(exc))
    return ToolResult.ok({
        "workspace_id": str(workspace_id),
        "preset": workspace.preset,
        "ai_prompts": workspace.ai_prompts,
        "decomposition_link_type": workspace.decomposition_link_type,
        "default_link_type": workspace.default_link_type,
        "language": workspace.language,
    })
```
Add `"workspace.get_preferences": "_handle_get_preferences"` to whatever tool-map structure `AdminToolGroup` uses. This is read-only — do NOT add to `_WRITE_TOOL_PREFIXES`.

- [ ] **Step 4: Run tests, verify pass, commit**

```bash
git add backend/mcp_server/tools/admin.py backend/mcp_server/tests/
git commit -m "feat: add workspace.get_preferences read-only MCP tool"
```

---

## Post-Plan Verification

- [ ] Run the full backend test suite: `docker-compose run --rm backend python -m pytest -q --ignore=mcp_server/tests/test_e2e_all_tools.py` (the e2e-all-tools file is known to need a live server per Phase 0's final verification — skip it here too). Cross-check any failures against files this plan actually touched, the same way Phase 0's finishing step did — do not assume a failure is unrelated without checking `git diff --name-only <task-1-start>..HEAD` against the failing file's path.
- [ ] Grep for any remaining `.exclude(lifecycle_status=` across `backend/application/*.py` to confirm Task 1 closed every gap this plan intended to close: `grep -rn "lifecycle_status=\"deleted\"" backend/application/*.py`.
- [ ] Confirm every new write tool name added in Tasks 2-7 appears in `_WRITE_TOOL_PREFIXES` — re-read the final state of that tuple and cross-check against this plan's task list rather than trusting each task's individual claim.

---

*Plan complete. Next: choose an execution approach (see below).*
