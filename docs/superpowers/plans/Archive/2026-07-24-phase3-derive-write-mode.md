# Phase 3: Derive-Modi (preview + write) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `mode` parameter (`preview` = today's draft-only behavior, `write` = new — persist the draft, auto-create a trace link, optionally auto-approve) to the 4 existing AI-derivation MCP tools, and add 3 new derive pairs (Architecture→Risk, Workspace→Glossary, Decision→ADR).

**Architecture:** A single shared helper, `_write_derived_entity(...)`, does the "persist a draft + create a trace link + optionally auto-approve" work once; every derive tool's `mode=write` path calls it instead of duplicating create/link/transition logic 7 times. `mode=preview` paths are completely untouched (existing behavior, zero risk of regression). Auto-approve (policy="auto") walks the entity's actual workflow preset via `workflow.services.transition()` (the real business-transition pipeline — NOT `outdate()`), one hop per available non-terminal transition, capped at 5 hops as a safety bound, since presets vary in hop count and there is no persisted review-policy config yet (that's Phase 5's job — this phase treats `policy` as a per-call param, not stored config).

**Tech Stack:** Django 4.2, Python 3.x, pytest, `backend/application/ai_derivation_service.py`, `backend/mcp_server/tools/ai_derivation.py`, `backend/mcp_server/tools/tests.py`.

## Global Constraints

- No REQ-ID in commit messages.
- `mode=preview` behavior must be BYTE-FOR-BYTE unchanged for all 4 existing derive tools — this is the single most important regression risk in this phase (these tools are already shipped and used).
- `mode=write` ALWAYS creates the entity as `draft` first (via the entity's existing `create_*` service method, which already self-initializes workflow state per Phase 1) — it never skips straight to an approved state.
- `policy` param (`"manual"` default | `"auto"`) is a PER-CALL parameter, not a stored workspace setting — no new model field, no new config. `policy="auto"` walks the entity through its real workflow transitions (`workflow.services.transition()`, real business pipeline) up to 5 hops, picking the first available non-terminal, non-"outdated-equivalent" transition at each step (use `state_meta`/`is_outdated_equivalent` from Phase 0 if a transition's target has that flag — skip it; otherwise take the first available transition). If no transition is available (already terminal) or the entity has no configured workflow transitions at all reachable within 5 hops, stop there and report the actual final state reached — never raise an error for "didn't reach approved."
- Every `mode=write` call creates exactly one trace link from the derived entity back to its source entity, using the semantically-closest existing `LinkType` (see per-task mapping below) — EXCEPT Decision→ADR, which has no source entity (free-text input only) and creates no trace link. This asymmetry is deliberate, not a bug — document it in that task's code/tests.
- `write_mcp_audit(...)` must be called on every `mode=write` path (it's a write operation), never on `mode=preview` (unchanged, still read-only/no-audit).
- Out of scope for this plan: persisted review-policy config, `min_confidence`/`review_high_risk` thresholds, `review.*` MCP endpoints (all Phase 5). Batch/bulk derive is out of scope (one draft in, one entity out, per call — matching the existing preview tools' shape).

---

## Task 1: Shared `_write_derived_entity` helper + wire into the 3 `AiDerivationToolGroup` tools

**Files:**
- Modify: `backend/application/ai_derivation_service.py` (add the shared write-mode helper as a method on `AiDerivationService`)
- Modify: `backend/mcp_server/tools/ai_derivation.py` (add `mode` param handling to all 3 existing handlers)
- Test: `backend/application/tests/test_ai_derivation_service.py`, `backend/mcp_server/tests/test_ai_derivation_tool_group.py`

**Interfaces:**
- Produces: `AiDerivationService._write_derived_entity(self, *, ctx: AuthContext, workspace_id: UUID, item_type: str, create_fn: Callable[[], Any], source_entity_id: UUID, source_item_type: str, link_type: str, policy: str = "manual") -> Dict[str, Any]` — calls `create_fn()` (a zero-arg closure the caller builds, e.g. `lambda: self._requirement_service.create_requirement(...)`) to persist the draft, then `TraceLinkService.create_trace_link(source_id=..., target_id=<created>.id, link_type=link_type, ctx=ctx)`, then if `policy == "auto"` walks `_auto_approve(item_type, created.id, workspace_id, ctx)` (new helper, described in Step 3 below). Returns `{"id": str(created.id), "status": <final status string>, "trace_link_id": str(link.id)}`.
- Consumes: `workflow.services.transition(item_id, target_state, change_reason, ctx, *, item_type, workspace_id) -> TransitionResult`, `workflow.definition_store.get_state_meta(workflow_json, state_name) -> dict` (Phase 0), `TraceLinkService.create_trace_link(source_id, target_id, link_type, ctx)` (all confirmed existing).

- [ ] **Step 1: Write failing tests for the shared helper in isolation**

```python
# add to backend/application/tests/test_ai_derivation_service.py
@pytest.mark.django_db
def test_write_derived_entity_creates_entity_and_trace_link(need_with_workflow, auth_ctx):
    from application.ai_derivation_service import AiDerivationService
    from application.requirement_service import RequirementService

    need_id, workspace_id = need_with_workflow
    svc = AiDerivationService()

    result = svc._write_derived_entity(
        ctx=auth_ctx,
        workspace_id=workspace_id,
        item_type="Requirement",
        create_fn=lambda: RequirementService().create_requirement(
            workspace_id=workspace_id, title="Derived Req", ctx=auth_ctx, description="from need",
        ),
        source_entity_id=need_id,
        source_item_type="StakeholderNeed",
        link_type="derives-from",
        policy="manual",
    )

    assert result["status"] == "draft"
    from persistence.models import Requirement
    assert Requirement.objects.filter(id=result["id"]).exists()
    from application.models import TraceLink  # verify exact module — TraceLink may live in persistence.models instead, check before writing
    assert TraceLink.objects.filter(id=result["trace_link_id"]).exists()


@pytest.mark.django_db
def test_write_derived_entity_policy_auto_advances_state(need_with_workflow, auth_ctx):
    from application.ai_derivation_service import AiDerivationService
    from application.requirement_service import RequirementService

    need_id, workspace_id = need_with_workflow
    svc = AiDerivationService()

    result = svc._write_derived_entity(
        ctx=auth_ctx, workspace_id=workspace_id, item_type="Requirement",
        create_fn=lambda: RequirementService().create_requirement(
            workspace_id=workspace_id, title="Derived Req 2", ctx=auth_ctx,
        ),
        source_entity_id=need_id, source_item_type="StakeholderNeed",
        link_type="derives-from", policy="auto",
    )
    # workspace's Requirement preset must actually have a transition path out of "draft"
    # for this assertion to be meaningful — use a workspace provisioned with the
    # "standard" or "extended" preset (has draft->approved / draft->in_review),
    # not "minimal" alone if that preset's only exit is "draft"->"done" (still fine,
    # "done" just isn't literally "approved" — assert status != "draft" instead of
    # a specific target state, since preset choice determines the exact reachable state)
    assert result["status"] != "draft"
```

Check whether `need_with_workflow` already exists as a shared fixture (Phase 0/1 tests established similar `*_with_workflow` fixtures) — reuse the naming convention, add to this file if not already shared via a `conftest.py`.

- [ ] **Step 2: Run to verify failure**

```bash
docker-compose build backend
docker-compose run --rm backend python -m pytest application/tests/test_ai_derivation_service.py -v
```

- [ ] **Step 3: Implement `_write_derived_entity` and `_auto_approve` on `AiDerivationService`**

```python
def _auto_approve(self, item_type: str, item_id, workspace_id, ctx) -> str:
    """Walk the entity forward through its real workflow transitions, one hop
    at a time, skipping any transition whose target is flagged
    is_outdated_equivalent (Phase 0 state_meta) or that is otherwise a
    reject/terminal path. Stops after 5 hops or when no transition remains.
    Never raises — returns whatever the final reached state is.
    """
    from workflow.services import get_available_transitions, transition  # verify exact function name for listing available transitions — confirm against workflow/services.py before finalizing, the plan's research only confirmed transition()/outdate()/reactivate() by name
    current_state = None
    for _ in range(5):
        available = get_available_transitions(item_id=item_id, item_type=item_type, workspace_id=workspace_id, ctx=ctx)
        if not available:
            break
        # Prefer the first non-outdated-equivalent transition; verify get_available_transitions'
        # actual return shape (list of state-name strings? list of dicts with from/to/roles?)
        # before assuming `.target_state`/similar attribute access below.
        next_state = available[0]  # placeholder access — replace with the real shape once verified
        result = transition(
            item_id=item_id, target_state=next_state, change_reason="auto-approved via AI-Derivation",
            ctx=ctx, item_type=item_type, workspace_id=workspace_id,
        )
        current_state = result.new_state
    return current_state or "draft"


def _write_derived_entity(self, *, ctx, workspace_id, item_type, create_fn, source_entity_id, source_item_type, link_type, policy="manual"):
    created = create_fn()
    from application.trace_link_service import TraceLinkService
    link = TraceLinkService().create_trace_link(
        source_id=source_entity_id, target_id=created.id, link_type=link_type, ctx=ctx,
    )
    status = "draft"
    if policy == "auto":
        status = self._auto_approve(item_type, created.id, workspace_id, ctx)
    return {"id": str(created.id), "status": status, "trace_link_id": str(link.id)}
```

**Note for the implementer:** `get_available_transitions`'s exact name/signature/return shape is NOT confirmed by this plan's research — the research pass only confirmed `transition()`/`outdate()`/`reactivate()` by name. Read `backend/workflow/services.py` in full before finalizing `_auto_approve` — if no such listing function exists, check `workflow/lifecycle_manager.py`'s `StateLifecycleManager` for an equivalent (e.g. `get_available_transitions` might be a method there, not a module-level function in `services.py`), or `workflow/definition_store.py`'s `WorkflowDefinitionStore` for a way to read the current definition's transition list directly and filter by `from_state == current`. Do not guess the access pattern — this is the one piece of `_auto_approve` most likely to need real correction against source.

- [ ] **Step 4: Run tests, verify pass**

- [ ] **Step 5: Add `mode` param to the 3 `AiDerivationToolGroup` handlers**

For each of `_handle_derive_requirements` (need→requirement), `_handle_suggest_architecture` (requirement→architecture), `_handle_decompose_next_level` (requirement→sub-requirement) in `backend/mcp_server/tools/ai_derivation.py`:

```python
def _handle_derive_requirements(self, *, params, auth_context, api_key):
    mode = params.get("mode", "preview")
    need_id = require_uuid(params, "need_id")
    n = params.get("n", 3)
    policy = params.get("policy", "manual")

    try:
        preview = self._service.derive_requirements_from_need(auth_context, need_id, n=n)
    except NotFoundError as exc:
        return ToolResult.error("NOT_FOUND", str(exc))

    if mode == "preview":
        return ToolResult.ok(preview)

    # mode == "write": persist EACH draft (this tool's preview returns a LIST of
    # drafts, unlike the single-draft testcase tool — write mode creates one
    # Requirement per draft, one trace link each, matching the preview shape 1:1)
    from persistence.models import StakeholderNeed
    need = StakeholderNeed.objects.get(id=need_id)  # confirm exact model/field access matches this file's existing get-pattern
    written = []
    for draft in preview["drafts"]:
        result = self._service._write_derived_entity(
            ctx=auth_context, workspace_id=need.workspace_id, item_type="Requirement",
            create_fn=lambda d=draft: self._requirement_service.create_requirement(
                workspace_id=need.workspace_id, title=d["title"], ctx=auth_context, description=d["description"],
            ),
            source_entity_id=need_id, source_item_type="StakeholderNeed",
            link_type="derives-from", policy=policy,
        )
        written.append(result)
    write_mcp_audit("ai_derivation.derive_requirements_from_need", need_id, auth_context, api_key)
    return ToolResult.ok({"written": written})
```

**Note for the implementer:** verify `self._requirement_service` (or equivalent) is already an attribute on `AiDerivationToolGroup`, or needs adding — check the class `__init__`. Apply the identical `mode`/`policy` pattern to `_handle_suggest_architecture` (writes ArchitectureElement from a `suggested_arch_element_ids`-shaped preview — note this one's preview shape is `{"suggested_arch_element_ids": [...]}`, NOT a `drafts` list of dicts with title/description; verify what write-mode should actually create here since the preview doesn't return title/description fields to persist — read `suggest_architecture_for_requirement`'s full body to understand what "suggest" actually means before assuming a straightforward create; it might suggest EXISTING architecture elements to link to, not draft NEW ones, which would make "write mode" here mean "create the trace links to the suggested existing elements" rather than "create new ArchitectureElements" — this needs to be resolved by reading the actual method body, not assumed from its name) and `_handle_decompose_next_level` (writes child Requirements, same `drafts`-list shape as need→requirement).

Update all 3 tools' `_TOOL_SCHEMAS` to add `mode` (enum: `["preview", "write"]`, default `"preview"`) and `policy` (enum: `["manual", "auto"]`, default `"manual"`) params.

- [ ] **Step 6: Add `ai_derivation.derive_requirements_from_need`/`.suggest_architecture_for_requirement`/`.decompose_requirement_next_level` to `_WRITE_TOOL_PREFIXES`**

These 3 tools were previously read-only (preview-only) and thus NOT in `_WRITE_TOOL_PREFIXES` — now that `mode=write` makes them capable of mutation, add all 3 to `backend/mcp_server/tool_registry.py`'s `_WRITE_TOOL_PREFIXES`. This is a genuinely new RBAC requirement introduced by this phase — do not skip it (this exact omission class caused Critical findings in Phase 0 and Phase 1's final reviews).

- [ ] **Step 7: Write tests for `mode=preview` unchanged + `mode=write` end-to-end + RBAC gate**

```python
@pytest.mark.django_db
def test_derive_requirements_preview_mode_unchanged(need_with_workflow, auth_ctx):
    # confirm mode=preview (or omitted) returns identical shape to before this phase
    ...

@pytest.mark.django_db
def test_derive_requirements_write_mode_persists_requirements_and_traces(need_with_workflow, auth_ctx):
    ...

def test_ai_derivation_write_tools_require_editor_role():
    # viewer role -> mode=write -> PERMISSION_DENIED
    ...
```

- [ ] **Step 8: Run tests, verify pass, commit**

```bash
docker-compose run --rm backend python -m pytest application/tests/test_ai_derivation_service.py mcp_server/tests/test_ai_derivation_tool_group.py -v
git add backend/application/ai_derivation_service.py backend/mcp_server/tools/ai_derivation.py backend/mcp_server/tool_registry.py backend/application/tests/test_ai_derivation_service.py backend/mcp_server/tests/test_ai_derivation_tool_group.py
git commit -m "feat: add mode=write support to the 3 AiDerivationToolGroup derive tools"
```

---

## Task 2: `test.derive_from_requirement` — same `mode`/`policy` treatment

**Files:**
- Modify: `backend/mcp_server/tools/tests.py`
- Test: `backend/mcp_server/tests/test_own_tool_groups_lifecycle.py` (or wherever `tests.py`'s existing tests live — confirm exact file name)

**Interfaces:**
- Consumes: `AiDerivationService._write_derived_entity` (Task 1), `TestService.create_test_case`.

- [ ] **Step 1: Write failing tests (preview-unchanged + write + RBAC)**, following Task 1's pattern exactly, adapted for `TestCase` (`item_type="TestCase"`, `link_type="verifies"` back to the source Requirement — this is the one existing pair where the link direction/type was already unambiguous from Phase 2's research: TestCase→Requirement via `verifies`).

- [ ] **Step 2: Run to verify failure**

- [ ] **Step 3: Add `mode`/`policy` to `_handle_derive_from_requirement` in `tests.py`, wire into `_write_derived_entity`**

The existing preview shape is `{"draft": {title, description, steps}, "requirement_id": ...}` — a single draft object (not a list), simpler than Task 1's list-shaped tools. `create_fn` should persist `title`/`description` via `TestService.create_test_case(...)`; verify how `steps` (list of `{step, expected_result}`) should be stored — check whether `TestCase`/a related model has a steps field, or whether steps are only meaningful as descriptive text folded into `description` for now (flag this as a scope decision if no structured steps storage exists).

- [ ] **Step 4: Add `test.derive_from_requirement` to `_WRITE_TOOL_PREFIXES`**

- [ ] **Step 5: Run tests, verify pass, commit**

```bash
git add backend/mcp_server/tools/tests.py backend/mcp_server/tool_registry.py backend/mcp_server/tests/
git commit -m "feat: add mode=write support to test.derive_from_requirement"
```

---

## Task 3: New derive pair — Architecture → Risk

**Files:**
- Modify: `backend/application/ai_derivation_service.py` (new `derive_risks_from_architecture` method)
- Modify: `backend/mcp_server/tools/ai_derivation.py` (new `risk.derive_from_architecture` tool — per the design spec's naming, this lives under the `risk` prefix, not `ai_derivation`, since it's entity-centric like `test.derive_from_requirement`; confirm which file/prefix convention to follow — the design spec names it `risk.derive_from_architecture (neu)`, suggesting the `risk` prefix on `GenericCrudToolGroup`, not a new handler in `ai_derivation.py`. Since `GenericCrudToolGroup` doesn't have a generic "derive" concept, add a THIN wrapper: a new small tool group method OR extend `GenericCrudToolGroup` with an optional derive hook. Simplest: add this as a standalone method in `ai_derivation.py` but register it under the `risk` prefix's tool map if that's structurally possible (verify: can two different tool GROUPS both contribute tool names under the same "risk" prefix, or must all `risk.*` tools live on ONE group instance? Per Phase 2's research on `ToolGroupRouter`, prefix routing picks ONE group instance per prefix — so `risk.derive_from_architecture` must be added to WHICHEVER group instance is registered under `"risk"` today, i.e. the `GenericCrudToolGroup("risk", RiskService, item_type="Risk")` instance from Phase 1. This means either (a) extending `GenericCrudToolGroup` itself with an optional injectable "derive" tool (invasive, affects all 5 generic entities), or (b) keeping the tool name `ai_derivation.derive_risks_from_architecture` instead of `risk.derive_from_architecture` to avoid the prefix collision (deviates from the design spec's suggested name, but avoids a much bigger refactor). Make this call explicitly and document it in the task report — this is a genuine architectural decision, not a small detail.)
- Test: `backend/application/tests/test_ai_derivation_service.py`, `backend/mcp_server/tests/test_ai_derivation_tool_group.py`

**Interfaces:**
- Consumes: `RiskService.create_risk(workspace_id, title, probability, impact, ctx, description="", category="technical", ...)` (existing), `_write_derived_entity` (Task 1).

- [ ] **Step 1: Write a failing test for the new preview method**

```python
@pytest.mark.django_db
def test_derive_risks_from_architecture_returns_drafts_with_valid_probability_impact(architecture_with_workflow, auth_ctx):
    from application.ai_derivation_service import AiDerivationService
    ae_id, workspace_id = architecture_with_workflow
    svc = AiDerivationService()
    result = svc.derive_risks_from_architecture(auth_ctx, ae_id)
    assert "drafts" in result
    for draft in result["drafts"]:
        assert draft["probability"] in ("low", "medium", "high")
        assert draft["impact"] in ("low", "medium", "high")
```

- [ ] **Step 2: Run to verify failure**

- [ ] **Step 3: Implement `derive_risks_from_architecture`**

Mirror `suggest_architecture_for_requirement`'s exact structure (fetch source entity, render prompt via a `PromptTemplate` slot or an inline prompt if no slot exists yet for this purpose — check `PromptTemplate`'s current fixed 3 slots from Phase 0 research; this is a NEW slot not among the 3 existing ones, so use an inline prompt string for now rather than trying to add PromptTemplate CRUD, which is Phase 4's job), call `_complete()` (mirror the exact pattern already used 2-3 times in this codebase per Phase 2's research), parse into `{"drafts": [{title, description, probability, impact, category}]}`. Constrain the LLM prompt explicitly to only emit `probability`/`impact` values from the valid enum set, and validate/clamp the parsed response defensively (fall back to `"medium"` for an invalid/missing value rather than crashing) since these are the exact fields `RiskService.create_risk` requires as enums, not free text.

- [ ] **Step 4: Run test, verify pass**

- [ ] **Step 5: Add the MCP tool (per the Step-1-flagged naming decision) with `mode`/`policy`, write-mode wired to `_write_derived_entity(item_type="Risk", link_type="implements", ...)`** — `implements` fits an ArchitectureElement→Risk relationship better than `derives-from` per the existing `LinkType` set (a risk "implements" awareness of an architectural concern); if the implementer judges another existing `LinkType` value fits better, use it and document the choice.

- [ ] **Step 6: Add the new tool name to `_WRITE_TOOL_PREFIXES`, write tests, run, commit**

```bash
git add backend/application/ai_derivation_service.py backend/mcp_server/tools/ai_derivation.py backend/mcp_server/tool_registry.py backend/application/tests/ backend/mcp_server/tests/
git commit -m "feat: add Architecture-to-Risk derive pair (preview + write)"
```

---

## Task 4: New derive pair — Workspace → Glossary

**Files:**
- Modify: `backend/application/ai_derivation_service.py` (new `derive_glossary_from_workspace` method)
- Modify: `backend/mcp_server/tools/ai_derivation.py` (new tool — same naming-decision process as Task 3, but for the `glossary` prefix; the design spec names it `glossary.derive_from_workspace`, same prefix-collision consideration applies since `glossary` is also a `GenericCrudToolGroup` instance)
- Test: same files as Task 3

**Interfaces:**
- Consumes: `GlossaryService.create(ctx, workspace_id, term, definition, synonyms=None, abbreviation="")` (existing).

- [ ] **Step 1: Write a failing test**

```python
@pytest.mark.django_db
def test_derive_glossary_from_workspace_returns_term_definition_drafts(workspace_with_data, auth_ctx):
    from application.ai_derivation_service import AiDerivationService
    workspace_id, tenant_id = workspace_with_data
    svc = AiDerivationService()
    result = svc.derive_glossary_from_workspace(auth_ctx, workspace_id)
    assert "drafts" in result
    for draft in result["drafts"]:
        assert "term" in draft and "definition" in draft
```

- [ ] **Step 2: Run to verify failure**

- [ ] **Step 3: Implement `derive_glossary_from_workspace`**

Source input: scan workspace Requirements/Architecture titles+descriptions (reuse `_entity_lists`-style lightweight queries, or a simpler direct query — this doesn't need Phase 2's full machinery, just enough text to seed an LLM prompt asking "extract domain terms and definitions from this text"). Return `{"drafts": [{term, definition, synonyms: [], abbreviation: ""}]}`.

- [ ] **Step 4: Run test, verify pass**

- [ ] **Step 5: Add the MCP tool with `mode`/`policy`, write-mode wired to `_write_derived_entity(item_type="GlossaryTerm", ...)` — handle the `unique_together=(workspace, term)` constraint from Section 4's research: `mode=write` must catch a `ValidationError` from a colliding term name and report a clear error (`ToolResult.error("VALIDATION_ERROR", ...)`, not an unhandled 500) rather than assuming every derived term is guaranteed unique.**

- [ ] **Step 6: `link_type` decision:** Workspace is not itself an artifact/traceable entity in the same sense as Requirement/ArchitectureElement — check whether `TraceLinkService.create_trace_link` even accepts a Workspace as a valid `source_id` (per Section 3's research, it resolves Artifact/Requirement/ArchitectureElement IDs — a bare Workspace id likely does NOT resolve). If Workspace cannot be a trace-link source, this pair — like Decision→ADR — creates NO trace link (document this as another deliberate asymmetry, verify by reading `_resolve_artifact_id`'s actual accepted types before deciding, not assumed).

- [ ] **Step 7: Add to `_WRITE_TOOL_PREFIXES`, write tests, run, commit**

```bash
git add backend/application/ai_derivation_service.py backend/mcp_server/tools/ai_derivation.py backend/mcp_server/tool_registry.py backend/application/tests/ backend/mcp_server/tests/
git commit -m "feat: add Workspace-to-Glossary derive pair (preview + write)"
```

---

## Task 5: New derive pair — Decision → ADR

**Files:**
- Modify: `backend/application/ai_derivation_service.py` (new `derive_adr_from_decision` method)
- Modify: `backend/mcp_server/tools/ai_derivation.py` (new tool — `adr` prefix has the same collision consideration as Tasks 3-4)
- Test: same files as Task 3

**Interfaces:**
- Consumes: `AdrService.create_adr(workspace_id, title, description, ctx, context="", consequences="", status="Draft", uid=None)` (existing).

- [ ] **Step 1: Write a failing test**

```python
@pytest.mark.django_db
def test_derive_adr_from_decision_returns_title_description_context(workspace_with_data, auth_ctx):
    from application.ai_derivation_service import AiDerivationService
    workspace_id, tenant_id = workspace_with_data
    svc = AiDerivationService()
    result = svc.derive_adr_from_decision(auth_ctx, workspace_id, decision_description="We will use Postgres instead of MySQL for better JSON support.")
    assert "draft" in result
    for key in ("title", "description", "context", "consequences"):
        assert key in result["draft"]
```

- [ ] **Step 2: Run to verify failure**

- [ ] **Step 3: Implement `derive_adr_from_decision(self, ctx, workspace_id, decision_description: str) -> Dict[str, Any]`** — no source entity to fetch (this is the one derive flow whose INPUT is raw free text, not an existing artifact id). Prompt the LLM to structure `decision_description` into `{title, description, context, consequences}`.

- [ ] **Step 4: Run test, verify pass**

- [ ] **Step 5: Add the MCP tool with `mode`/`policy` — write-mode creates the ADR but creates NO trace link (no source entity exists to link from, per this plan's Global Constraints). Document this explicitly in the handler's docstring and in a test asserting `"trace_link_id" not in result` (or equivalent) for this one tool, distinguishing it from every other derive tool in this phase.**

- [ ] **Step 6: Add to `_WRITE_TOOL_PREFIXES`, write tests, run, commit**

```bash
git add backend/application/ai_derivation_service.py backend/mcp_server/tools/ai_derivation.py backend/mcp_server/tool_registry.py backend/application/tests/ backend/mcp_server/tests/
git commit -m "feat: add Decision-to-ADR derive pair (preview + write, no trace link)"
```

---

## Post-Plan Verification

- [ ] Run full regression: `docker-compose run --rm backend python -m pytest application/tests/ mcp_server/tests/ workflow/tests/ traceability/tests/ -q` — cross-check any new failures against `git diff --name-only <task-1-start>..HEAD`.
- [ ] Confirm EVERY new/modified derive tool name is in `_WRITE_TOOL_PREFIXES` for its `mode=write` capability — enumerate the full list and cross-check against the tool_registry.py's actual tuple, the same discipline that caught real gaps in Phase 1's final review.
- [ ] Grep for any remaining place `mode` defaults to something other than `"preview"` — a derive tool that silently defaults to `write` would be a serious behavior-change regression for existing callers.

---

*Plan complete. Next: choose an execution approach.*
