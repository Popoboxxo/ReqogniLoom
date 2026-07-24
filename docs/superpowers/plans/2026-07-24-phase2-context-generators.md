# Phase 2: Context-Generatoren Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend `workspace.get_context` with `depth`/`include_outdated`/`role` params and workspace-configurable token budgets; add `workspace.llm_system_prompt`, `context.test_coverage`, `context.change_impact` MCP tools.

**Architecture:** All new/extended tools live on `CrossCuttingToolGroup` (`backend/mcp_server/tools/cross_cutting.py`), registered under a new `"context"` prefix on the SAME shared instance already used for `traceability`/`artifact` (`tool_registry.py:319`) — not the separate instance `AdminToolGroup` lazily constructs for itself. No new domain services are needed for depth=summary/normal (plain queryset counts/projections); `context.test_coverage` composes the existing `CoverageCalculator`; `context.change_impact` reuses the LLM-call pattern already established by `AiDerivationService._complete`/`TraceabilitySuggestService._complete`.

**Tech Stack:** Django 4.2, Python 3.x, pytest, `backend/mcp_server/tools/cross_cutting.py`.

## Global Constraints

- No REQ-ID in commit messages.
- `role` param is a pure label — it must appear in `workspace.llm_system_prompt`'s generated text, but must NEVER filter which data `workspace.get_context`/`workspace.llm_system_prompt` return (confirmed design decision).
- `include_outdated` defaults to `false` everywhere in this phase.
- Per-entity outdated-exclusion mechanism differs and must be used correctly: `Requirement`/`TestCase`/`Risk`/`Issue`/`Adr`/`ChangeRequest`/`StakeholderNeed` → `.exclude(status="outdated")` (status-mirror column); `ArchitectureElement`/`GlossaryTerm`/`Diagram` → `workflow.services.outdated_item_ids(item_type, tenant_id=...)` + `.exclude(id__in=...)`. Getting this backwards for any entity silently breaks filtering (Phase 0/1's final reviews both caught this exact bug class — do not repeat it).
- Token budgets (`depth=summary` max 300 tokens, `depth=normal` max 2000, `depth=full` unbounded) are soft/informational — truncate gracefully on overflow, never raise a hard error. Defaults live in code; per-workspace override reads from `Workspace.ai_prompts["context_token_budgets"]` (a new key in the existing JSON field — do not add a new model field for this).
- Explicitly out of scope for this plan: the `WorkspaceGoal` pseudo-artifact does not exist yet (deferred out of Phase 0). `workspace.llm_system_prompt` must NOT reference a goal — build it without that line, and leave a clearly-marked one-line TODO comment for whichever future phase adds `WorkspaceGoal` to wire it in as the prompt's first sentence.
- `open_requirements_count`'s existing query (`cross_cutting.py:~440`) does NOT currently exclude outdated requirements from its count — a pre-existing quirk. Fix it as part of Task 1 since Task 1 touches this exact code path anyway (do not leave a known-inconsistent count sitting next to brand-new outdated-aware counts).

---

## Task 1: `workspace.get_context` — `depth=summary` + `include_outdated` + `role` + token-budget config

**Files:**
- Modify: `backend/mcp_server/tools/cross_cutting.py` (`_handle_workspace_get_context`, schema at ~L161-183)
- Test: `backend/mcp_server/tests/test_cross_cutting_tool_group.py` (confirm exact file name first — check `backend/mcp_server/tests/` directory listing; if no such file exists yet for this tool group, create it following the structural conventions of `test_diagram_tool_group.py`)

**Interfaces:**
- Produces: `_get_context_token_budget(workspace: Workspace, depth: str) -> int` — reads `workspace.ai_prompts.get("context_token_budgets", {}).get(depth, DEFAULT_BUDGETS[depth])`, module-level `DEFAULT_BUDGETS = {"summary": 300, "normal": 2000, "full": None}` (`None` = unbounded).
- Produces: `_entity_counts(workspace_id: UUID, tenant_id: UUID, include_outdated: bool) -> dict` — returns `{"requirements": {"active": N, "outdated": M, "total": N+M}, "architecture": {...}, "tests": {"active": N, "pass": X, "fail": Y, "outdated": Z}, "risks": {"open": N, "mitigated": M, "accepted": K}}`.

- [ ] **Step 1: Write failing tests for the new params**

```python
# backend/mcp_server/tests/test_cross_cutting_tool_group.py
import pytest


@pytest.mark.django_db
def test_get_context_summary_depth_returns_entity_counts(workspace_with_data, auth_ctx):
    from mcp_server.tools.cross_cutting import CrossCuttingToolGroup

    workspace_id, tenant_id = workspace_with_data
    group = CrossCuttingToolGroup()
    result = group.execute_tool(
        "workspace.get_context",
        params={"workspace_id": str(workspace_id), "depth": "summary"},
        auth_context=auth_ctx,
        api_key="",
    )

    ctx = result.data["workspace_context"]
    assert ctx["requirements"]["total"] >= 1
    assert "architecture" in ctx
    assert "tests" in ctx
    assert "risks" in ctx


@pytest.mark.django_db
def test_get_context_excludes_outdated_by_default(workspace_with_outdated_requirement, auth_ctx):
    from mcp_server.tools.cross_cutting import CrossCuttingToolGroup

    workspace_id, tenant_id, outdated_req_id = workspace_with_outdated_requirement
    group = CrossCuttingToolGroup()

    result = group.execute_tool(
        "workspace.get_context",
        params={"workspace_id": str(workspace_id), "depth": "summary"},
        auth_context=auth_ctx, api_key="",
    )
    assert result.data["workspace_context"]["requirements"]["outdated"] == 1
    # active count must not include the outdated one
    active_only = result.data["workspace_context"]["requirements"]["active"]

    result_incl = group.execute_tool(
        "workspace.get_context",
        params={"workspace_id": str(workspace_id), "depth": "summary", "include_outdated": True},
        auth_context=auth_ctx, api_key="",
    )
    assert result_incl.data["workspace_context"]["requirements"]["total"] == active_only + 1


@pytest.mark.django_db
def test_get_context_role_is_label_only_does_not_filter_data(workspace_with_data, auth_ctx):
    from mcp_server.tools.cross_cutting import CrossCuttingToolGroup

    workspace_id, tenant_id = workspace_with_data
    group = CrossCuttingToolGroup()

    result_dev = group.execute_tool(
        "workspace.get_context",
        params={"workspace_id": str(workspace_id), "depth": "summary", "role": "developer"},
        auth_context=auth_ctx, api_key="",
    )
    result_tester = group.execute_tool(
        "workspace.get_context",
        params={"workspace_id": str(workspace_id), "depth": "summary", "role": "tester"},
        auth_context=auth_ctx, api_key="",
    )
    # role must not change which counts come back
    assert result_dev.data["workspace_context"]["requirements"] == result_tester.data["workspace_context"]["requirements"]
```

Check whether `workspace_with_data`/`workspace_with_outdated_requirement` fixtures already exist somewhere reusable (e.g. a shared `conftest.py` under `mcp_server/tests/`); if not, add them to this file following the fixture style established in `test_own_tool_groups_lifecycle.py` (Phase 1) — a workspace with a default workflow provisioned, plus one active + one `outdate()`-d Requirement.

- [ ] **Step 2: Run to verify failure**

```bash
docker-compose build backend
docker-compose run --rm backend python -m pytest mcp_server/tests/test_cross_cutting_tool_group.py -v
```

- [ ] **Step 3: Add `depth`/`include_outdated`/`role` to the schema and implement `_entity_counts`**

In `backend/mcp_server/tools/cross_cutting.py`, near the top of the file (module level, alongside other constants):
```python
DEFAULT_CONTEXT_TOKEN_BUDGETS = {"summary": 300, "normal": 2000, "full": None}


def _get_context_token_budget(workspace, depth: str) -> "int | None":
    overrides = (workspace.ai_prompts or {}).get("context_token_budgets", {})
    return overrides.get(depth, DEFAULT_CONTEXT_TOKEN_BUDGETS[depth])
```

Add a new method on `CrossCuttingToolGroup`:
```python
def _entity_counts(self, *, workspace_id, tenant_id, include_outdated: bool) -> Dict[str, Any]:
    from persistence.models import Requirement
    from application.models import Risk
    from workflow.services import outdated_item_ids

    req_qs = Requirement.objects.filter(artifact__workspace_id=workspace_id)
    req_outdated = req_qs.filter(status="outdated").count()
    req_active = req_qs.exclude(status="outdated").count()

    arch_outdated_ids = set(
        outdated_item_ids("ArchitectureElement", tenant_id=tenant_id).values_list("item_id", flat=True)
    )
    # verify the exact import used elsewhere for ArchitectureElement's model/manager
    # (application.models or persistence.models — check architecture_service.py's own
    # import before assuming persistence.models here)
    from persistence.models import ArchitectureElement
    arch_qs = ArchitectureElement.objects.filter(workspace_id=workspace_id)  # verify exact FK/field name used elsewhere
    arch_total = arch_qs.count()
    arch_outdated = arch_qs.filter(id__in=arch_outdated_ids).count()

    from persistence.models import TestCase
    test_qs = TestCase.objects.filter(artifact__workspace_id=workspace_id)  # verify FK path matches TestService's own queries
    test_outdated = test_qs.filter(status="outdated").count()
    test_pass = test_qs.exclude(status="outdated").filter(status="pass").count()  # verify exact TestCase.Status pass value string
    test_fail = test_qs.exclude(status="outdated").filter(status="fail").count()  # verify exact TestCase.Status fail value string

    risk_qs = Risk.objects.filter(workspace_id=workspace_id)  # verify exact FK field name
    risk_open = risk_qs.filter(status=Risk.RiskStatus.IDENTIFIED).count()
    risk_mitigated = risk_qs.filter(status=Risk.RiskStatus.MITIGATED).count()
    risk_accepted = risk_qs.filter(status=Risk.RiskStatus.ACCEPTED).count()

    counts = {
        "requirements": {"active": req_active, "outdated": req_outdated, "total": req_active + req_outdated},
        "architecture": {"active": arch_total - arch_outdated, "outdated": arch_outdated, "total": arch_total},
        "tests": {"pass": test_pass, "fail": test_fail, "outdated": test_outdated},
        "risks": {"open": risk_open, "mitigated": risk_mitigated, "accepted": risk_accepted},
    }
    if not include_outdated:
        for entity_counts in counts.values():
            entity_counts.pop("outdated", None)
    return counts
```

**Note for the implementer:** every line above marked "verify" is a genuine unknown from this plan's research pass (exact FK field names on `ArchitectureElement`/`TestCase`/`Risk` linking to workspace, exact `TestCase.Status` pass/fail string values). Read the actual model definitions in `persistence/models.py`/`application/models.py` and the equivalent existing queries in `architecture_service.py`/`test_service.py`/`risk_service.py` before finalizing — do not guess field names.

- [ ] **Step 4: Wire `depth`/`include_outdated`/`role` into `_handle_workspace_get_context`**

Extend the existing handler (current body shown in this plan's research — keep the existing `tenant_id`/`user_id`/`active_roles`/preset/terminology logic untouched, only ADD to it):
```python
def _handle_workspace_get_context(self, *, params, auth_context, api_key):
    workspace_id_str = params.get("workspace_id")
    depth = params.get("depth", "summary")
    include_outdated = bool(params.get("include_outdated", False))
    role = params.get("role", "")  # label only, never used to filter data below

    context_data = {
        "tenant_id": str(auth_context.tenant_id),
        "user_id": str(auth_context.user_id),
        "active_roles": list(auth_context.active_roles),
    }
    if role:
        context_data["role"] = role

    if workspace_id_str:
        workspace_id = UUID(str(workspace_id_str))
        # ... existing preset/terminology/change_reason_policy logic unchanged ...

        # FIX the pre-existing quirk while touching this code: exclude outdated
        # requirements from open_requirements_count unless include_outdated=True
        from persistence.models import Requirement
        open_reqs_qs = Requirement.objects.filter(artifact__workspace_id=workspace_id).exclude(status="approved")
        if not include_outdated:
            open_reqs_qs = open_reqs_qs.exclude(status="outdated")
        context_data["open_requirements_count"] = open_reqs_qs.count()

        if depth in ("summary", "normal", "full"):
            context_data.update(self._entity_counts(
                workspace_id=workspace_id, tenant_id=auth_context.tenant_id, include_outdated=include_outdated
            ))

    context_data["workspace_id"] = workspace_id_str
    return ToolResult.ok({"workspace_context": context_data})
```

`depth=normal`/`depth=full` list-level detail is Task 2/3 — this task only needs `depth` to be accepted without error and to still return the summary-level counts for all three values (normal/full are supersets, built next).

- [ ] **Step 5: Run tests to verify pass**

```bash
docker-compose run --rm backend python -m pytest mcp_server/tests/test_cross_cutting_tool_group.py -v
```

- [ ] **Step 6: Commit**

```bash
git add backend/mcp_server/tools/cross_cutting.py backend/mcp_server/tests/test_cross_cutting_tool_group.py
git commit -m "feat: add depth/include_outdated/role params and entity counts to workspace.get_context"
```

---

## Task 2: `depth=normal` — lightweight per-item lists

**Files:**
- Modify: `backend/mcp_server/tools/cross_cutting.py`
- Test: same test file as Task 1

**Interfaces:**
- Produces: `_entity_lists(workspace_id, tenant_id, include_outdated) -> dict` — `{"requirements": [{"id", "title", "status", "level"}], "architecture": [{"id", "name", "type", "status"}], "tests": [{"id", "title", "status", "linked_req_id"}]}`.

- [ ] **Step 1: Write failing test**

```python
@pytest.mark.django_db
def test_get_context_normal_depth_returns_item_lists(workspace_with_data, auth_ctx):
    from mcp_server.tools.cross_cutting import CrossCuttingToolGroup
    workspace_id, tenant_id = workspace_with_data
    group = CrossCuttingToolGroup()
    result = group.execute_tool(
        "workspace.get_context",
        params={"workspace_id": str(workspace_id), "depth": "normal"},
        auth_context=auth_ctx, api_key="",
    )
    ctx = result.data["workspace_context"]
    assert isinstance(ctx["requirements_list"], list)
    assert ctx["requirements_list"][0].keys() >= {"id", "title", "status", "level"}
```

- [ ] **Step 2: Run to verify failure**

- [ ] **Step 3: Implement `_entity_lists` and wire into the handler for `depth in ("normal", "full")`**

```python
def _entity_lists(self, *, workspace_id, tenant_id, include_outdated: bool) -> Dict[str, Any]:
    from persistence.models import Requirement, ArchitectureElement, TestCase
    from workflow.services import outdated_item_ids

    req_qs = Requirement.objects.filter(artifact__workspace_id=workspace_id)
    if not include_outdated:
        req_qs = req_qs.exclude(status="outdated")
    requirements = list(req_qs.values("id", "title", "status", "level"))

    arch_qs = ArchitectureElement.objects.filter(workspace_id=workspace_id)  # verify field name, per Task 1
    if not include_outdated:
        outdated_ids = outdated_item_ids("ArchitectureElement", tenant_id=tenant_id)
        arch_qs = arch_qs.exclude(id__in=outdated_ids)
    architecture = list(arch_qs.values("id", "name", "type", "status"))  # verify ArchitectureElement's actual field names (type vs element_type, etc.)

    test_qs = TestCase.objects.filter(artifact__workspace_id=workspace_id)  # verify FK path
    if not include_outdated:
        test_qs = test_qs.exclude(status="outdated")
    tests = list(test_qs.values("id", "title", "status", "linked_req_id"))  # verify TestCase's actual FK field name to Requirement (may not be literally "linked_req_id")

    return {"requirements_list": requirements, "architecture_list": architecture, "tests_list": tests}
```

**Note for the implementer:** field names marked "verify" must be checked against the actual `ArchitectureElement`/`TestCase` model definitions before finalizing — `.values(...)` with a wrong field name raises `FieldError` immediately, so this will fail loudly in Step 4's test run if wrong, not silently.

- [ ] **Step 4: Run tests, verify pass**

- [ ] **Step 5: Commit**

```bash
git add backend/mcp_server/tools/cross_cutting.py backend/mcp_server/tests/test_cross_cutting_tool_group.py
git commit -m "feat: add depth=normal item lists to workspace.get_context"
```

---

## Task 3: `depth=full` + token-budget truncation

**Files:**
- Modify: `backend/mcp_server/tools/cross_cutting.py`
- Test: same test file

**Interfaces:**
- Consumes: `_get_context_token_budget` (Task 1), `_entity_counts`/`_entity_lists` (Tasks 1-2).
- Produces: a token-estimation + truncation helper `_truncate_to_budget(context_data: dict, budget: int | None) -> dict`.

- [ ] **Step 1: Write failing test proving depth=full includes everything and depth=summary respects the token budget**

```python
@pytest.mark.django_db
def test_get_context_full_depth_includes_all_fields(workspace_with_data, auth_ctx):
    ...  # assert requirements_list, architecture_list, tests_list, AND recent_changes all present

@pytest.mark.django_db
def test_get_context_summary_depth_is_truncated_under_budget(workspace_with_many_requirements, auth_ctx):
    # create enough requirements that a naive summary would exceed 300 tokens
    ...  # assert a rough token-count estimate (e.g. len(json.dumps(...)) // 4) stays under the configured budget

@pytest.mark.django_db
def test_workspace_can_override_token_budget(workspace_with_data, auth_ctx):
    # set workspace.ai_prompts["context_token_budgets"] = {"summary": 50}
    # assert the returned summary is smaller/truncated more aggressively than the default
    ...
```

- [ ] **Step 2: Run to verify failure**

- [ ] **Step 3: Implement `_truncate_to_budget` (soft truncation, never raises) and a `recent_changes` field for `depth=full`**

```python
def _truncate_to_budget(self, context_data: Dict[str, Any], budget: "int | None") -> Dict[str, Any]:
    import json
    if budget is None:
        return context_data
    # Rough token estimate: 1 token ~= 4 chars. Soft truncation only — never raise.
    serialized = json.dumps(context_data, default=str)
    if len(serialized) // 4 <= budget:
        return context_data
    # Drop list-shaped keys first (cheapest to shed), then truncate remaining lists,
    # re-checking the estimate after each step, until under budget or nothing left to drop.
    trimmed = dict(context_data)
    for list_key in ("tests_list", "architecture_list", "requirements_list", "recent_changes"):
        if len(json.dumps(trimmed, default=str)) // 4 <= budget:
            break
        trimmed.pop(list_key, None)
    return trimmed
```

For `depth="full"`, additionally add a `recent_changes` field — query the most recent N `WorkflowHistoryEntry` rows for the workspace (across all item types) as `[{entity_type, title, timestamp}]`. Check whether `WorkflowHistoryEntry` has a direct `workspace_id` field (confirmed present per Phase 0 research) to query directly without joining through each entity type.

Wire `_truncate_to_budget` as the final step before `return ToolResult.ok(...)` in `_handle_workspace_get_context`, using `_get_context_token_budget(workspace, depth)` (Task 1) as the budget.

- [ ] **Step 4: Run tests, verify pass**

- [ ] **Step 5: Commit**

```bash
git add backend/mcp_server/tools/cross_cutting.py backend/mcp_server/tests/test_cross_cutting_tool_group.py
git commit -m "feat: add depth=full recent_changes and soft token-budget truncation to workspace.get_context"
```

---

## Task 4: `workspace.llm_system_prompt` (new tool)

**Files:**
- Modify: `backend/mcp_server/tools/cross_cutting.py`
- Modify: `backend/mcp_server/tool_registry.py` (only if this tool needs a new `_WRITE_TOOL_PREFIXES`-relevant entry — it does NOT, this is a read-only generator tool, add nothing there)
- Test: same test file

**Interfaces:**
- Consumes: `_entity_counts`, `_entity_lists` (Tasks 1-2).
- Produces: new `_handle_llm_system_prompt(self, *, params, auth_context, api_key) -> ToolResult`, registered as `"workspace.llm_system_prompt": "_handle_llm_system_prompt"` in `_TOOL_MAP`.

- [ ] **Step 1: Write failing test**

```python
@pytest.mark.django_db
def test_llm_system_prompt_includes_requirements_and_architecture(workspace_with_data, auth_ctx):
    from mcp_server.tools.cross_cutting import CrossCuttingToolGroup
    workspace_id, tenant_id = workspace_with_data
    group = CrossCuttingToolGroup()
    result = group.execute_tool(
        "workspace.llm_system_prompt",
        params={"workspace_id": str(workspace_id), "role": "developer"},
        auth_context=auth_ctx, api_key="",
    )
    prompt = result.data["system_prompt"]
    assert isinstance(prompt, str)
    assert "Requirements" in prompt or "requirement" in prompt.lower()
```

- [ ] **Step 2: Run to verify failure**

- [ ] **Step 3: Implement the handler**

```python
def _handle_llm_system_prompt(self, *, params, auth_context, api_key):
    workspace_id_str = params.get("workspace_id")
    if not workspace_id_str:
        return ToolResult.error("VALIDATION_ERROR", "workspace_id is required")
    workspace_id = UUID(str(workspace_id_str))
    role = params.get("role", "")
    include_outdated = bool(params.get("include_outdated", False))

    from persistence.models import Workspace
    try:
        workspace = Workspace.objects.get(id=workspace_id, tenant_id=auth_context.tenant_id)
    except Workspace.DoesNotExist:
        return ToolResult.error("NOT_FOUND", f"Workspace {workspace_id} not found")

    counts = self._entity_counts(workspace_id=workspace_id, tenant_id=auth_context.tenant_id, include_outdated=include_outdated)
    lists = self._entity_lists(workspace_id=workspace_id, tenant_id=auth_context.tenant_id, include_outdated=include_outdated)

    # TODO(future phase): once WorkspaceGoal exists, prepend "goal_approved" here
    # as the prompt's first sentence, per the design spec's Phase 0.4/2.2 intent.
    # Deliberately NOT implemented now — WorkspaceGoal was descoped from Phase 0.

    lines = [f'Du arbeitest am Projekt "{workspace.name}".']
    if role:
        lines.append(f"Du bist als {role} unterwegs.")
    lines.append("")
    lines.append("## Aktive Requirements")
    for req in lists["requirements_list"][:20]:  # cap list length defensively regardless of token-budget truncation
        lines.append(f"- [{req.get('level', '?')}] {req['title']} (status: {req['status']})")
    lines.append("")
    lines.append("## Architecture")
    for ae in lists["architecture_list"][:20]:
        lines.append(f"- {ae['name']} (type: {ae.get('type', '?')}, status: {ae['status']})")
    lines.append("")
    lines.append(
        f"## Testabdeckung\n{counts['tests']['pass']} pass, {counts['tests']['fail']} fail"
    )

    prompt_text = "\n".join(lines)
    budget = self._get_context_token_budget(workspace, "normal")
    if budget is not None and len(prompt_text) // 4 > budget:
        prompt_text = prompt_text[: budget * 4] + "\n... (truncated)"

    return ToolResult.ok({"system_prompt": prompt_text})
```

Add to `_TOOL_MAP` and `_TOOL_SCHEMAS` following this file's existing conventions.

- [ ] **Step 4: Run tests, verify pass**

- [ ] **Step 5: Commit**

```bash
git add backend/mcp_server/tools/cross_cutting.py backend/mcp_server/tests/test_cross_cutting_tool_group.py
git commit -m "feat: add workspace.llm_system_prompt MCP tool"
```

---

## Task 5: `context.test_coverage`

**Files:**
- Modify: `backend/mcp_server/tools/cross_cutting.py`
- Modify: `backend/mcp_server/tool_registry.py` (register new `"context"` prefix)
- Modify: `backend/traceability/coverage_calculator.py` (add `include_outdated` support, currently absent entirely)
- Test: same test file + `backend/traceability/tests/test_coverage_calculator.py`

**Interfaces:**
- Consumes: `traceability.coverage_calculator.CoverageCalculator.get_coverage_data(workspace_id, baseline_id=None)` (existing, extend with `include_outdated: bool = False`).
- Produces: `"context.test_coverage": "_handle_test_coverage"` on `CrossCuttingToolGroup`.

- [ ] **Step 1: Write failing tests**

```python
# backend/traceability/tests/test_coverage_calculator.py — add
@pytest.mark.django_db
def test_get_coverage_data_excludes_outdated_requirements_when_requested(workspace_with_outdated_requirement):
    from traceability.coverage_calculator import CoverageCalculator
    workspace_id, tenant_id, outdated_req_id = workspace_with_outdated_requirement
    calc = CoverageCalculator()

    data_default = calc.get_coverage_data(workspace_id)
    assert not any(e.requirement_id == outdated_req_id for e in data_default.entries)

    data_incl = calc.get_coverage_data(workspace_id, include_outdated=True)
    assert any(e.requirement_id == outdated_req_id for e in data_incl.entries)
```

```python
# backend/mcp_server/tests/test_cross_cutting_tool_group.py — add
@pytest.mark.django_db
def test_context_test_coverage_returns_test_cases_and_gaps(requirement_with_tests, auth_ctx):
    from mcp_server.tools.cross_cutting import CrossCuttingToolGroup
    req_id, workspace_id = requirement_with_tests
    group = CrossCuttingToolGroup()
    result = group.execute_tool(
        "context.test_coverage",
        params={"requirement_id": str(req_id)},
        auth_context=auth_ctx, api_key="",
    )
    assert "test_cases" in result.data
    assert "gaps" in result.data  # requirements without any linked test case, per the design spec's "Lücken" wording
```

- [ ] **Step 2: Run to verify failure**

- [ ] **Step 3: Add `include_outdated` to `CoverageCalculator.get_coverage_data`**

Read the exact current method body first (confirmed at `traceability/coverage_calculator.py:143` per this plan's research). Thread a new `include_outdated: bool = False` param through: exclude outdated Requirements from the returned `entries` list (`.exclude(status="outdated")` on whatever Requirement queryset backs the entries), and — since the underlying `_get_verifies_links_detail` raw SQL may pull test case IDs regardless of outdated status — filter the per-entry `test_cases` list against `outdated_item_ids`-excluded TestCase ids when `include_outdated=False` (TestCase is mirrored, so this can also be a `status != "outdated"` check applied to whatever TestCase rows are loaded to build each entry — verify against the actual code shape before deciding which point in the pipeline is cheapest to filter at).

- [ ] **Step 4: Run coverage calculator tests, verify pass**

```bash
docker-compose run --rm backend python -m pytest traceability/tests/test_coverage_calculator.py -v
```

- [ ] **Step 5: Implement `_handle_test_coverage` on `CrossCuttingToolGroup`**

```python
def _handle_test_coverage(self, *, params, auth_context, api_key):
    req_id_str = params.get("requirement_id")
    if not req_id_str:
        return ToolResult.error("VALIDATION_ERROR", "requirement_id is required")
    include_outdated = bool(params.get("include_outdated", False))

    from persistence.models import Requirement
    try:
        requirement = Requirement.objects.get(id=UUID(str(req_id_str)), tenant_id=auth_context.tenant_id)
    except Requirement.DoesNotExist:
        return ToolResult.error("NOT_FOUND", f"Requirement {req_id_str} not found")

    from traceability.coverage_calculator import CoverageCalculator
    calc = CoverageCalculator()
    data = calc.get_coverage_data(requirement.artifact.workspace_id, include_outdated=include_outdated)  # verify exact workspace_id access path on Requirement
    entry = next((e for e in data.entries if e.requirement_id == requirement.id), None)

    if entry is None:
        return ToolResult.ok({"test_cases": [], "gaps": [str(requirement.id)]})
    return ToolResult.ok({
        "test_cases": [{"id": str(tc.id), "result": tc.result} for tc in entry.test_cases],  # verify exact TestCaseEntry attribute names
        "gaps": [] if entry.test_cases else [str(requirement.id)],
    })
```

- [ ] **Step 6: Register `"context"` prefix**

In `tool_registry.py`, find the existing registration of `cross_cutting_tool_group` (the shared instance at L319, registered under `"traceability"`/`"artifact"`) and add:
```python
"context": cross_cutting_tool_group,
```
to the same `register_groups({...})` dict — reusing the SAME instance, not constructing a new one (per this plan's research on the two-instance ambiguity — this is the "directly registered" instance, not `AdminToolGroup`'s private fallthrough copy).

- [ ] **Step 7: Run tests, verify pass, commit**

```bash
docker-compose run --rm backend python -m pytest mcp_server/tests/test_cross_cutting_tool_group.py traceability/tests/test_coverage_calculator.py -v
git add backend/mcp_server/tools/cross_cutting.py backend/mcp_server/tool_registry.py backend/traceability/coverage_calculator.py backend/mcp_server/tests/test_cross_cutting_tool_group.py backend/traceability/tests/test_coverage_calculator.py
git commit -m "feat: add context.test_coverage MCP tool with include_outdated support"
```

---

## Task 6: `context.change_impact`

**Files:**
- Modify: `backend/mcp_server/tools/cross_cutting.py`
- Test: same test file

**Interfaces:**
- Consumes: `traceability.services.query(...)` (existing trace-link walk, confirmed at `traceability/services.py:108`), an LLM call following the established `_complete()` pattern from `AiDerivationService`/`TraceabilitySuggestService`.

- [ ] **Step 1: Write a failing test using a mock LLM provider (follow this codebase's existing mock-provider test convention — check how `test_ai_derivation_service.py` or `test_traceability_suggest_service.py` mocks `llm_adapter.providers.get_provider` before writing this)**

```python
@pytest.mark.django_db
def test_change_impact_returns_affected_entities(entity_with_traces, auth_ctx, monkeypatch):
    from mcp_server.tools.cross_cutting import CrossCuttingToolGroup
    entity_id, entity_type, workspace_id = entity_with_traces
    group = CrossCuttingToolGroup()

    result = group.execute_tool(
        "context.change_impact",
        params={
            "entity_id": str(entity_id),
            "entity_type": entity_type,
            "change_description": "Renaming this field to improve clarity",
        },
        auth_context=auth_ctx, api_key="",
    )
    assert "affected_entities" in result.data
    assert isinstance(result.data["affected_entities"], list)
```

- [ ] **Step 2: Run to verify failure**

- [ ] **Step 3: Implement `_handle_change_impact`**

Reuse `traceability.services.query(...)`'s trace-walk (upstream+downstream, per this plan's research) to gather directly-linked entities, PLUS a children walk for hierarchical entity types (ArchitectureElement/Requirement decomposition) if `query()` doesn't already include it — verify by reading `traceability/services.py:108`'s actual behavior before assuming children are or aren't included. Then call an LLM completion (mirror `AiDerivationService._complete`'s exact pattern — cache-key-by-purpose, mock-fallback, same import list: `from llm_adapter.providers import get_provider, MockLlmProvider, LlmNotConfiguredError, LlmProviderUnknownError`) with a prompt combining `change_description` + the gathered entity list, asking the LLM to rank/annotate which are most likely genuinely impacted.

```python
def _handle_change_impact(self, *, params, auth_context, api_key):
    entity_id_str = params.get("entity_id")
    entity_type = params.get("entity_type")
    change_description = params.get("change_description", "")
    include_outdated = bool(params.get("include_outdated", False))
    if not entity_id_str or not entity_type:
        return ToolResult.error("VALIDATION_ERROR", "entity_id and entity_type are required")

    from traceability.services import query as te_query
    linked = te_query(
        entity_id=UUID(str(entity_id_str)), entity_type=entity_type,
        direction="both", tenant_id=auth_context.tenant_id,
    )  # verify exact te_query signature/param names against traceability/services.py:108 before finalizing

    if not include_outdated:
        linked = [e for e in linked if not self._is_outdated(e)]  # helper to write, dispatching by entity_type per the mirrored/unmirrored split (Task 1's pattern)

    # LLM-assisted ranking — mirror AiDerivationService._complete's exact call shape
    from application.ai_derivation_service import AiDerivationService  # or wherever _complete's pattern is best extracted from; verify whether a shared helper should be factored out here instead of duplicating a 3rd copy
    ...

    return ToolResult.ok({"affected_entities": [...], "change_description": change_description})
```

**Note for the implementer:** this task has the most genuine design latitude in the whole plan — the LLM-ranking step's exact prompt/response shape isn't prescribed elsewhere in the design spec beyond "Returns: betroffene Entitäten (Traces + Children, inkl. outdated auf Wunsch)". Use your judgment for the LLM prompt wording, but do NOT duplicate a third near-identical `_complete()` implementation without at least considering (and reporting your decision on) extracting a shared helper — flag this choice explicitly in your task report either way.

- [ ] **Step 4: Register in `_TOOL_MAP`/`_TOOL_SCHEMAS`, run tests, verify pass**

- [ ] **Step 5: Commit**

```bash
git add backend/mcp_server/tools/cross_cutting.py backend/mcp_server/tests/test_cross_cutting_tool_group.py
git commit -m "feat: add context.change_impact MCP tool"
```

---

## Post-Plan Verification

- [ ] Run full regression: `docker-compose run --rm backend python -m pytest mcp_server/tests/ traceability/tests/ application/tests/ workflow/tests/ -q` — cross-check any new failures against `git diff --name-only <task-1-start>..HEAD`, same discipline as Phase 0/1's finishing steps.
- [ ] Grep for any other `.exclude(lifecycle_status=` or entity-status filters this phase's new code might interact with inconsistently: `grep -rn "outdated_item_ids\|status=\"outdated\"" backend/mcp_server/tools/cross_cutting.py backend/traceability/coverage_calculator.py`.
- [ ] Confirm `context.test_coverage`/`context.change_impact` are NOT in `_WRITE_TOOL_PREFIXES` (both read-only).

---

*Plan complete. Next: choose an execution approach.*
