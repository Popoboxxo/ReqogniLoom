# Phase 0: Status-Modell-Vereinheitlichung — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace all hard/bespoke soft-deletes across 8 entity services with one universal, workflow-engine-backed `outdate()`/`reactivate()` mechanism, and make "which states count as outdated" a per-preset, workspace-overridable piece of config.

**Architecture:** Add a `state_meta` JSON key alongside the existing `states`/`transitions` keys inside `WorkflowEngineDefinition.workflow_json` (no schema migration needed — it's a `JSONField`). Add two new module-level functions, `outdate()` and `reactivate()`, in `backend/workflow/services.py`, backed by a new `force_transition()` primitive on `StateLifecycleManager` that bypasses normal preset-transition validation (outdating must work from ANY current state, on ANY preset, even ones that never modeled a "rejected" path). Rewire the 8 existing delete call sites to call `outdate()` instead. Backfill existing `lifecycle_status="deleted"` / `Adr.Status.DELETED` records via a management command.

**Tech Stack:** Django 4.2, Python 3.x, pytest, existing `workflow` app (`backend/workflow/`).

## Global Constraints

- No REQ-ID in commit messages — this project has req-traceability disabled (Conventional Commits: `feat: ...` / `fix: ...` / `refactor: ...`, no `(REQ-xxx)`).
- Big-bang migration is acceptable — single-user/homelab system, no concurrent-write safety net needed beyond what Django's `atomic_transaction` already gives us.
- Every new/changed code path must go through the existing `@atomic_transaction` pattern already used by all service delete methods.
- `WorkflowHistoryEntry.save()` is append-only (raises on UPDATE of existing pk) — never attempt to mutate a history row, only ever create new ones.
- Out of scope for this plan (explicitly deferred to their own future spec→plan cycles): CustomField/Workspace workflow-engine wiring, the `WorkspaceGoal` pseudo-artifact itself, any MCP tool changes (that's Phase 1), any `review.*` endpoints (Phase 5).

---

## Task 1: `state_meta` — per-state "outdated" flag storage + global defaults

**Files:**
- Modify: `backend/workflow/definition_store.py` (add `state_meta` to `PRESET_SCHEMAS` entries that need it, add a `get_state_meta()` helper)
- Create: `backend/workflow/migrations/0010_seed_state_meta_outdated_flags.py`
- Test: `backend/workflow/tests/test_state_meta.py`

**Interfaces:**
- Produces: `get_state_meta(workflow_json: dict, state_name: str) -> dict` — returns `{"is_outdated_equivalent": bool}`, defaulting to `{"is_outdated_equivalent": False}` if the state has no entry in `state_meta` or `state_meta` is absent entirely (backward-compatible with any `workflow_json` blob that predates this change).
- **Not consumed anywhere within this Phase 0 plan.** `outdate()`/`reactivate()` (Task 2) are a presetindependent escape hatch that never look at `state_meta` — they always target/restore-from the synthetic `"outdated"` state directly, regardless of which named business states a preset defines. `get_state_meta()` exists so that **Phase 2's context-generator filtering** (a separate future plan) can ALSO treat business states like `"rejected"`/`"Wontfix"`/`"deprecated"` as outdated-equivalent for `include_outdated=false` queries, without requiring an explicit `.outdate()` call on every such item. This task only lands the data + read helper; wiring it into any query path is out of scope here.

- [ ] **Step 1: Write the failing test for `get_state_meta`**

```python
# backend/workflow/tests/test_state_meta.py
from workflow.definition_store import get_state_meta


def test_get_state_meta_returns_flag_when_present():
    workflow_json = {
        "states": ["draft", "deprecated"],
        "transitions": [],
        "state_meta": {"deprecated": {"is_outdated_equivalent": True}},
    }
    assert get_state_meta(workflow_json, "deprecated") == {"is_outdated_equivalent": True}


def test_get_state_meta_defaults_to_false_when_state_meta_missing():
    workflow_json = {"states": ["draft", "done"], "transitions": []}
    assert get_state_meta(workflow_json, "done") == {"is_outdated_equivalent": False}


def test_get_state_meta_defaults_to_false_for_unlisted_state():
    workflow_json = {
        "states": ["draft", "approved"],
        "transitions": [],
        "state_meta": {"approved": {"is_outdated_equivalent": False}},
    }
    assert get_state_meta(workflow_json, "draft") == {"is_outdated_equivalent": False}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest workflow/tests/test_state_meta.py -v`
Expected: FAIL with `ImportError: cannot import name 'get_state_meta'`

- [ ] **Step 3: Implement `get_state_meta` in `definition_store.py`**

Add near the top of `backend/workflow/definition_store.py`, after the existing `PRESET_SCHEMAS` dict definition:

```python
def get_state_meta(workflow_json: dict, state_name: str) -> dict:
    """Return per-state metadata (currently just `is_outdated_equivalent`).

    Backward-compatible: workflow_json blobs written before this key existed
    have no "state_meta" entry at all, and any state not explicitly listed
    inside "state_meta" defaults to not-outdated.
    """
    state_meta = workflow_json.get("state_meta", {})
    return state_meta.get(state_name, {"is_outdated_equivalent": False})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest workflow/tests/test_state_meta.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Add `state_meta` to the `PRESET_SCHEMAS` entries that need a `True` flag**

In `backend/workflow/definition_store.py`, edit `PRESET_SCHEMAS` — add a `"state_meta"` key to the affected entries (leave all other presets untouched; `get_state_meta` already defaults missing entries to `False`, so presets with zero outdated-equivalent states — `minimal`, `risk_default` — need no `state_meta` key at all):

```python
# Requirement standard/extended presets: "deprecated" -> outdated
"standard": {
    "states": ["draft", "approved", "deprecated"],
    "transitions": _standard_transitions(),
    "state_meta": {"deprecated": {"is_outdated_equivalent": True}},
},
"extended": {
    "states": ["draft", "in_review", "approved", "implemented", "verified", "deprecated"],
    "transitions": _extended_transitions(),
    "state_meta": {"deprecated": {"is_outdated_equivalent": True}},
},
# ChangeRequest (ccb_approval): only "rejected" -> outdated ("implemented" is terminal but NOT outdated)
"ccb_approval": {
    "states": ["draft", "submitted", "under_review", "approved", "rejected", "implemented"],
    "transitions": _ccb_approval_transitions(),  # keep existing transitions reference as-is
    "state_meta": {"rejected": {"is_outdated_equivalent": True}},
},
# StakeholderNeed: "deprecated" -> outdated
"need_default": {
    "states": ["draft", "in_review", "approved", "deprecated"],
    "transitions": _need_transitions(),
    "state_meta": {"deprecated": {"is_outdated_equivalent": True}},
},
# ArchitectureElement: "deprecated" -> outdated
"architecture_default": {
    "states": ["draft", "in_review", "approved", "deprecated"],
    "transitions": _architecture_transitions(),
    "state_meta": {"deprecated": {"is_outdated_equivalent": True}},
},
# TestCase: "Deprecated" -> outdated
"testcase_default": {
    "states": ["Draft", "Ready", "Approved", "Deprecated"],
    "transitions": _testcase_transitions(),
    "state_meta": {"Deprecated": {"is_outdated_equivalent": True}},
},
# Issue: only "Wontfix" -> outdated ("Closed" stays visible)
"issue_default": {
    "states": ["Open", "In Progress", "Resolved", "Closed", "Wontfix"],
    "transitions": _issue_transitions(),
    "state_meta": {"Wontfix": {"is_outdated_equivalent": True}},
},
# Diagram / GlossaryTerm / ICD (all share _design_lifecycle_transitions): "deprecated" -> outdated
"diagram_default": {
    "states": ["draft", "in_review", "approved", "deprecated"],
    "transitions": _design_lifecycle_transitions(),
    "state_meta": {"deprecated": {"is_outdated_equivalent": True}},
},
"glossary_term_default": {
    "states": ["draft", "in_review", "approved", "deprecated"],
    "transitions": _design_lifecycle_transitions(),
    "state_meta": {"deprecated": {"is_outdated_equivalent": True}},
},
"icd_default": {
    "states": ["draft", "in_review", "approved", "deprecated"],
    "transitions": _design_lifecycle_transitions(),
    "state_meta": {"deprecated": {"is_outdated_equivalent": True}},
},
```

**Note for the implementer:** only ADD the `"state_meta"` key to each existing dict literal — do not change `"states"` or `"transitions"` values, and do not touch `"minimal"` or `"risk_default"` (both intentionally have zero outdated-equivalent states, per the confirmed design decision — "done" and "Closed" remain visible by default).

- [ ] **Step 6: Write the data migration to backfill existing `GlobalWorkflowDefinition` + non-customized `WorkflowEngineDefinition` rows**

```python
# backend/workflow/migrations/0010_seed_state_meta_outdated_flags.py
from django.db import migrations

STATE_META_BY_PRESET = {
    "standard": {"deprecated": {"is_outdated_equivalent": True}},
    "extended": {"deprecated": {"is_outdated_equivalent": True}},
    "ccb_approval": {"rejected": {"is_outdated_equivalent": True}},
    "need_default": {"deprecated": {"is_outdated_equivalent": True}},
    "architecture_default": {"deprecated": {"is_outdated_equivalent": True}},
    "testcase_default": {"Deprecated": {"is_outdated_equivalent": True}},
    "issue_default": {"Wontfix": {"is_outdated_equivalent": True}},
    "diagram_default": {"deprecated": {"is_outdated_equivalent": True}},
    "glossary_term_default": {"deprecated": {"is_outdated_equivalent": True}},
    "icd_default": {"deprecated": {"is_outdated_equivalent": True}},
}


def seed_state_meta(apps, schema_editor):
    GlobalWorkflowDefinition = apps.get_model("workflow", "GlobalWorkflowDefinition")
    WorkflowEngineDefinition = apps.get_model("workflow", "WorkflowEngineDefinition")

    for global_def in GlobalWorkflowDefinition.objects.all():
        state_meta = STATE_META_BY_PRESET.get(global_def.preset)
        if not state_meta:
            continue
        workflow_json = global_def.workflow_json
        workflow_json["state_meta"] = state_meta
        global_def.workflow_json = workflow_json
        global_def.save(update_fields=["workflow_json"])

        # Propagate to every non-customized derived definition, same as
        # GlobalWorkflowDefinitionStore._propagate does at runtime.
        WorkflowEngineDefinition.objects.filter(
            source_global_id=global_def.id, is_customized=False
        ).update(workflow_json=workflow_json)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("workflow", "0009_backfill_global_workflow_defaults"),
    ]

    operations = [
        migrations.RunPython(seed_state_meta, noop_reverse),
    ]
```

- [ ] **Step 7: Run the migration and verify**

Run: `cd backend && python manage.py migrate workflow`
Expected: `Applying workflow.0010_seed_state_meta_outdated_flags... OK`

- [ ] **Step 8: Commit**

```bash
git add backend/workflow/definition_store.py backend/workflow/migrations/0010_seed_state_meta_outdated_flags.py backend/workflow/tests/test_state_meta.py
git commit -m "feat: add per-state outdated-equivalent metadata to workflow presets"
```

---

## Task 2: Universal `outdate()` / `reactivate()` mechanism

**Files:**
- Modify: `backend/workflow/lifecycle_manager.py` (add `force_transition` method to `StateLifecycleManager`)
- Modify: `backend/workflow/services.py` (add module-level `outdate()`/`reactivate()` functions)
- Test: `backend/workflow/tests/test_outdate_reactivate.py`

**Interfaces:**
- Consumes: `WorkflowItemState` (fields: `item_id`, `item_type`, `workspace_id`, `definition`, `current_state`), `WorkflowHistoryEntry` (fields: `item_state`, `from_state`, `to_state`, `transitioned_by`, `transitioned_at`, `change_reason`, `workspace_id`), `StateLifecycleManager.ensure_item_state(item_id, item_type, workspace_id, initial_state) -> WorkflowItemState` (all confirmed existing).
- Produces:
  - `StateLifecycleManager.force_transition(self, item_id: UUID, item_type: str, workspace_id: UUID, target_state: str, change_reason: str, actor: str) -> "TransitionResult"` — bypasses normal preset-transition-list validation (used only for the system-level outdate/reactivate escape hatch, never exposed directly to business logic elsewhere).
  - `workflow.services.outdate(item_id: UUID | str, item_type: str, workspace_id: UUID | str, ctx: AuthContext, reason: str = "") -> "TransitionResult"`
  - `workflow.services.reactivate(item_id: UUID | str, item_type: str, workspace_id: UUID | str, ctx: AuthContext) -> "TransitionResult"` — raises `ValueError("item is not outdated")` if current state isn't `"outdated"`.

- [ ] **Step 1: Write the failing tests**

```python
# backend/workflow/tests/test_outdate_reactivate.py
import pytest
from workflow.services import outdate, reactivate
from workflow.models import WorkflowItemState, WorkflowHistoryEntry


@pytest.mark.django_db
def test_outdate_transitions_from_any_current_state(requirement_with_workflow, auth_ctx):
    item_id, workspace_id = requirement_with_workflow

    result = outdate(
        item_id=item_id,
        item_type="Requirement",
        workspace_id=workspace_id,
        ctx=auth_ctx,
        reason="superseded by REQ-99",
    )

    assert result.new_state == "outdated"
    item_state = WorkflowItemState.objects.get(item_id=item_id, item_type="Requirement")
    assert item_state.current_state == "outdated"
    history = WorkflowHistoryEntry.objects.filter(item_state=item_state).order_by("-transitioned_at").first()
    assert history.to_state == "outdated"
    assert history.change_reason == "superseded by REQ-99"


@pytest.mark.django_db
def test_reactivate_restores_previous_state(requirement_with_workflow, auth_ctx):
    item_id, workspace_id = requirement_with_workflow
    outdate(item_id=item_id, item_type="Requirement", workspace_id=workspace_id, ctx=auth_ctx, reason="test")

    result = reactivate(item_id=item_id, item_type="Requirement", workspace_id=workspace_id, ctx=auth_ctx)

    assert result.new_state == "draft"  # the state it was in before outdate()
    item_state = WorkflowItemState.objects.get(item_id=item_id, item_type="Requirement")
    assert item_state.current_state == "draft"


@pytest.mark.django_db
def test_reactivate_raises_if_not_currently_outdated(requirement_with_workflow, auth_ctx):
    item_id, workspace_id = requirement_with_workflow

    with pytest.raises(ValueError, match="item is not outdated"):
        reactivate(item_id=item_id, item_type="Requirement", workspace_id=workspace_id, ctx=auth_ctx)
```

Add the two fixtures at the top of the same test file (or `conftest.py` if the project convention puts shared fixtures there — check `backend/workflow/tests/conftest.py` first and follow its existing pattern for creating a tenant-scoped `AuthContext` and a `Requirement` with an initialized `WorkflowItemState`; if no such fixture exists yet, add both directly in `test_outdate_reactivate.py`):

```python
@pytest.fixture
def requirement_with_workflow(db, tenant, workspace, auth_ctx):
    from persistence.models import Requirement
    requirement = Requirement.objects.create(
        tenant=tenant, workspace_id=workspace.id, title="Test Req", description="",
    )
    return requirement.id, workspace.id
```

(If `tenant`/`workspace`/`auth_ctx` fixtures already exist under a different name in the project's shared `conftest.py`, use those exact names instead of inventing new ones — check `backend/workflow/tests/conftest.py` and `backend/conftest.py` before writing this step.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest workflow/tests/test_outdate_reactivate.py -v`
Expected: FAIL with `ImportError: cannot import name 'outdate'`

- [ ] **Step 3: Implement `force_transition` on `StateLifecycleManager`**

Add to `backend/workflow/lifecycle_manager.py`, as a new method on the `StateLifecycleManager` class (alongside `ensure_item_state`):

```python
def force_transition(
    self,
    item_id,
    item_type: str,
    workspace_id,
    target_state: str,
    change_reason: str,
    actor: str,
):
    """Transition an item to `target_state` bypassing normal preset-transition
    validation. Used exclusively by the outdate()/reactivate() escape hatch —
    outdating must work from ANY current state, on ANY preset, even ones that
    never modeled a "rejected"-style path in their transitions list.
    """
    with transaction.atomic():
        item_state = (
            WorkflowItemState.objects.select_for_update()
            .get(item_id=item_id, item_type=item_type, workspace_id=workspace_id)
        )
        previous_state = item_state.current_state
        item_state.current_state = target_state
        item_state.version += 1
        item_state.save(update_fields=["current_state", "version"])

        WorkflowHistoryEntry.objects.create(
            item_state=item_state,
            from_state=previous_state,
            to_state=target_state,
            transitioned_by=actor,
            transitioned_at=timezone.now(),
            change_reason=change_reason,
            workspace_id=workspace_id,
        )

        self._sync_status_mirror(item_type, item_id, target_state)

        return TransitionResult(
            item_id=item_id,
            previous_state=previous_state,
            new_state=target_state,
            history_entry_id=None,
            signature_seal="",
        )
```

**Note for the implementer:** confirm the exact import names already present at the top of `lifecycle_manager.py` for `transaction`, `timezone`, `WorkflowItemState`, `WorkflowHistoryEntry`, `TransitionResult` — reuse them, do not add duplicate imports. `_sync_status_mirror` is confirmed to already exist as a static/instance method on this same class (per Task 3's rewiring, it must already handle `item_type` values that have no mirror entry as a silent no-op — verify this by reading its current implementation before relying on it here; if it doesn't already no-op safely for unregistered types, this is a pre-existing behavior to confirm, not something to change in this task).

- [ ] **Step 4: Implement `outdate()`/`reactivate()` in `services.py`**

Add to `backend/workflow/services.py`, near the existing `transition()` function:

```python
def outdate(
    item_id,
    item_type: str,
    workspace_id,
    ctx: "AuthContext",
    *,
    reason: str = "",
) -> TransitionResult:
    """Mark an item as outdated (soft-delete), regardless of its current
    workflow state or which preset it uses. Always available — this is the
    system-level escape hatch, not a business-process transition.
    """
    manager = StateLifecycleManager()
    return manager.force_transition(
        item_id=item_id,
        item_type=item_type,
        workspace_id=workspace_id,
        target_state="outdated",
        change_reason=reason,
        actor=ctx.user_id,
    )


def reactivate(
    item_id,
    item_type: str,
    workspace_id,
    ctx: "AuthContext",
) -> TransitionResult:
    """Restore an outdated item to whatever state it was in immediately
    before it was outdated (read from the most recent WorkflowHistoryEntry
    transitioning into "outdated").
    """
    item_state = WorkflowItemState.objects.get(
        item_id=item_id, item_type=item_type, workspace_id=workspace_id
    )
    if item_state.current_state != "outdated":
        raise ValueError("item is not outdated")

    last_outdate_entry = (
        WorkflowHistoryEntry.objects.filter(item_state=item_state, to_state="outdated")
        .order_by("-transitioned_at")
        .first()
    )
    restore_to = last_outdate_entry.from_state

    manager = StateLifecycleManager()
    return manager.force_transition(
        item_id=item_id,
        item_type=item_type,
        workspace_id=workspace_id,
        target_state=restore_to,
        change_reason="reactivated",
        actor=ctx.user_id,
    )
```

**Note for the implementer:** confirm `StateLifecycleManager` is already imported in `services.py` (it's used internally by the existing `transition()` function per Task grounding) — reuse the existing import, do not add a duplicate.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && python -m pytest workflow/tests/test_outdate_reactivate.py -v`
Expected: PASS (3 tests)

- [ ] **Step 6: Commit**

```bash
git add backend/workflow/lifecycle_manager.py backend/workflow/services.py backend/workflow/tests/test_outdate_reactivate.py
git commit -m "feat: add universal outdate/reactivate transitions to workflow engine"
```

---

## Task 3: Rewire the 8 existing delete call sites to use `outdate()`

**Files:**
- Modify: `backend/application/requirement_service.py:380-381`
- Modify: `backend/application/adr_service.py:312-313`
- Modify: `backend/application/architecture_service.py:302-303`
- Modify: `backend/application/glossary_service.py:173-174`
- Modify: `backend/application/risk_service.py:412`
- Modify: `backend/application/issue_service.py:363`
- Modify: `backend/application/test_service.py:248`
- Modify: `backend/application/change_request_service.py:314`
- Test: existing test files for each service (extend, don't replace) — `backend/application/tests/test_requirement_service.py`, `test_adr_service.py`, `test_architecture_service.py`, `test_glossary_service.py`, `test_risk_service.py`, `test_issue_service.py`, `test_test_service.py` (or wherever `TestCase`'s service tests live), `test_change_request_service.py` — check exact file names before editing, they may differ slightly from this guess.

**Interfaces:**
- Consumes: `workflow.services.outdate(item_id, item_type, workspace_id, ctx, reason="") -> TransitionResult` (from Task 2).

Each of the 8 sub-steps below follows the identical pattern: replace the current delete body with a call to `outdate()`, using the entity's own `ctx`/ `workspace_id` already in scope in that method. Do all 8 as one task since they share one deliverable ("no entity hard-deletes or writes a bespoke deleted-marker directly anymore") — but commit after each pair to keep diffs reviewable.

### 3a. Requirement

- [ ] **Step 1: Write the failing test**

```python
# add to backend/application/tests/test_requirement_service.py
@pytest.mark.django_db
def test_delete_requirement_calls_outdate_not_lifecycle_status(requirement, auth_ctx):
    from application.requirement_service import RequirementService

    RequirementService().delete_requirement(requirement_id=requirement.id, ctx=auth_ctx)

    requirement.refresh_from_db()
    # lifecycle_status is no longer written directly - it's synced by the
    # workflow's status-mirror side effect instead (verified by outdate()'s
    # own tests in Task 2); here we assert the workflow state itself moved.
    from workflow.models import WorkflowItemState
    item_state = WorkflowItemState.objects.get(item_id=requirement.id, item_type="Requirement")
    assert item_state.current_state == "outdated"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest application/tests/test_requirement_service.py::test_delete_requirement_calls_outdate_not_lifecycle_status -v`
Expected: FAIL (item_state.current_state is still whatever it was, not "outdated")

- [ ] **Step 3: Replace the delete body in `requirement_service.py:380-381`**

Replace:
```python
requirement.lifecycle_status = "deleted"
requirement.save(update_fields=["lifecycle_status"])
```
With:
```python
from workflow.services import outdate  # add to top-of-file imports if not already present

outdate(
    item_id=requirement.id,
    item_type="Requirement",
    workspace_id=requirement.workspace_id,
    ctx=ctx,
    reason="deleted via requirement.delete",
)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest application/tests/test_requirement_service.py::test_delete_requirement_calls_outdate_not_lifecycle_status -v`
Expected: PASS

### 3b. ADR

- [ ] **Step 1: Write the failing test**

```python
# add to backend/application/tests/test_adr_service.py
@pytest.mark.django_db
def test_delete_adr_calls_outdate(adr, auth_ctx):
    from application.adr_service import AdrService

    AdrService().delete_adr(adr_id=adr.id, ctx=auth_ctx)

    from workflow.models import WorkflowItemState
    item_state = WorkflowItemState.objects.get(item_id=adr.id, item_type="Adr")
    assert item_state.current_state == "outdated"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest application/tests/test_adr_service.py::test_delete_adr_calls_outdate -v`

- [ ] **Step 3: Replace the delete body in `adr_service.py:312-313`**

Replace:
```python
adr.status = Adr.Status.DELETED
adr.save(update_fields=["status"])
```
With:
```python
from workflow.services import outdate

outdate(
    item_id=adr.id,
    item_type="Adr",
    workspace_id=adr.workspace_id,
    ctx=ctx,
    reason="deleted via adr.delete",
)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest application/tests/test_adr_service.py::test_delete_adr_calls_outdate -v`
Expected: PASS

- [ ] **Step 5: Commit (3a + 3b)**

```bash
git add backend/application/requirement_service.py backend/application/adr_service.py backend/application/tests/test_requirement_service.py backend/application/tests/test_adr_service.py
git commit -m "refactor: route Requirement and ADR delete through workflow outdate()"
```

### 3c. ArchitectureElement

- [ ] **Step 1: Write the failing test**

```python
# add to backend/application/tests/test_architecture_service.py
@pytest.mark.django_db
def test_delete_architecture_element_calls_outdate(architecture_element, auth_ctx):
    from application.architecture_service import ArchitectureService

    ArchitectureService().delete_architecture_element(element_id=architecture_element.id, ctx=auth_ctx)

    from workflow.models import WorkflowItemState
    item_state = WorkflowItemState.objects.get(item_id=architecture_element.id, item_type="ArchitectureElement")
    assert item_state.current_state == "outdated"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest application/tests/test_architecture_service.py::test_delete_architecture_element_calls_outdate -v`

- [ ] **Step 3: Replace the delete body in `architecture_service.py:302-303`**

Replace:
```python
arch_el.lifecycle_status = "deleted"
arch_el.save(update_fields=["lifecycle_status"])
```
With:
```python
from workflow.services import outdate

outdate(
    item_id=arch_el.id,
    item_type="ArchitectureElement",
    workspace_id=arch_el.workspace_id,
    ctx=ctx,
    reason="deleted via architecture.delete",
)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest application/tests/test_architecture_service.py::test_delete_architecture_element_calls_outdate -v`

### 3d. GlossaryTerm

- [ ] **Step 1: Write the failing test**

```python
# add to backend/application/tests/test_glossary_service.py
@pytest.mark.django_db
def test_delete_glossary_term_calls_outdate(glossary_term, auth_ctx):
    from application.glossary_service import GlossaryService

    GlossaryService().delete(term_id=glossary_term.id, ctx=auth_ctx)

    from workflow.models import WorkflowItemState
    item_state = WorkflowItemState.objects.get(item_id=glossary_term.id, item_type="GlossaryTerm")
    assert item_state.current_state == "outdated"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest application/tests/test_glossary_service.py::test_delete_glossary_term_calls_outdate -v`

- [ ] **Step 3: Replace the delete body in `glossary_service.py:173-174`**

Replace:
```python
gt.lifecycle_status = "deleted"
gt.save(update_fields=["lifecycle_status"])
```
With:
```python
from workflow.services import outdate

outdate(
    item_id=gt.id,
    item_type="GlossaryTerm",
    workspace_id=gt.workspace_id,
    ctx=ctx,
    reason="deleted via glossary.delete",
)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest application/tests/test_glossary_service.py::test_delete_glossary_term_calls_outdate -v`

- [ ] **Step 5: Commit (3c + 3d)**

```bash
git add backend/application/architecture_service.py backend/application/glossary_service.py backend/application/tests/test_architecture_service.py backend/application/tests/test_glossary_service.py
git commit -m "refactor: route ArchitectureElement and GlossaryTerm delete through workflow outdate()"
```

### 3e. Risk

- [ ] **Step 1: Write the failing test**

```python
# add to backend/application/tests/test_risk_service.py
@pytest.mark.django_db
def test_delete_risk_calls_outdate_not_hard_delete(risk, auth_ctx):
    from application.risk_service import RiskService

    RiskService().delete_risk(risk_id=risk.id, ctx=auth_ctx)

    # must NOT be hard-deleted from the DB anymore
    from application.models import Risk
    assert Risk.objects.filter(id=risk.id).exists()

    from workflow.models import WorkflowItemState
    item_state = WorkflowItemState.objects.get(item_id=risk.id, item_type="Risk")
    assert item_state.current_state == "outdated"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest application/tests/test_risk_service.py::test_delete_risk_calls_outdate_not_hard_delete -v`
Expected: FAIL (row no longer exists — the old hard `.delete()` still runs)

- [ ] **Step 3: Replace the delete body in `risk_service.py:412`**

Replace:
```python
risk.delete()
```
With:
```python
from workflow.services import outdate

outdate(
    item_id=risk.id,
    item_type="Risk",
    workspace_id=risk.workspace_id,
    ctx=ctx,
    reason="deleted via risk.delete",
)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest application/tests/test_risk_service.py::test_delete_risk_calls_outdate_not_hard_delete -v`
Expected: PASS

### 3f. Issue

- [ ] **Step 1: Write the failing test**

```python
# add to backend/application/tests/test_issue_service.py
@pytest.mark.django_db
def test_delete_issue_calls_outdate_not_hard_delete(issue, auth_ctx):
    from application.issue_service import IssueService

    IssueService().delete_issue(issue_id=issue.id, ctx=auth_ctx)

    from application.models import Issue
    assert Issue.objects.filter(id=issue.id).exists()

    from workflow.models import WorkflowItemState
    item_state = WorkflowItemState.objects.get(item_id=issue.id, item_type="Issue")
    assert item_state.current_state == "outdated"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest application/tests/test_issue_service.py::test_delete_issue_calls_outdate_not_hard_delete -v`

- [ ] **Step 3: Replace the delete body in `issue_service.py:363`**

Replace:
```python
issue.delete()
```
With:
```python
from workflow.services import outdate

outdate(
    item_id=issue.id,
    item_type="Issue",
    workspace_id=issue.workspace_id,
    ctx=ctx,
    reason="deleted via issue.delete",
)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest application/tests/test_issue_service.py::test_delete_issue_calls_outdate_not_hard_delete -v`

- [ ] **Step 5: Commit (3e + 3f)**

```bash
git add backend/application/risk_service.py backend/application/issue_service.py backend/application/tests/test_risk_service.py backend/application/tests/test_issue_service.py
git commit -m "refactor: route Risk and Issue delete through workflow outdate() instead of hard delete"
```

### 3g. TestCase

- [ ] **Step 1: Write the failing test**

```python
# add to the test file covering test_service.py (confirm exact path/name before editing)
@pytest.mark.django_db
def test_delete_test_case_calls_outdate_not_hard_delete(test_case, auth_ctx):
    from application.test_service import TestService

    TestService().delete_test_case(test_case_id=test_case.id, ctx=auth_ctx)

    from persistence.models import TestCase
    assert TestCase.objects.filter(id=test_case.id).exists()

    from workflow.models import WorkflowItemState
    item_state = WorkflowItemState.objects.get(item_id=test_case.id, item_type="TestCase")
    assert item_state.current_state == "outdated"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest application/tests/ -k test_delete_test_case_calls_outdate_not_hard_delete -v`

- [ ] **Step 3: Replace the delete body in `test_service.py:248`**

Replace:
```python
test_case.delete()
```
With:
```python
from workflow.services import outdate

outdate(
    item_id=test_case.id,
    item_type="TestCase",
    workspace_id=test_case.workspace_id,
    ctx=ctx,
    reason="deleted via test.delete",
)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest application/tests/ -k test_delete_test_case_calls_outdate_not_hard_delete -v`

### 3h. ChangeRequest (fixes the known docstring/behavior bug)

- [ ] **Step 1: Write the failing test**

```python
# add to backend/application/tests/test_change_request_service.py
@pytest.mark.django_db
def test_delete_change_request_calls_outdate_not_hard_delete(change_request, auth_ctx):
    from application.change_request_service import ChangeRequestService

    ChangeRequestService().delete_change_request(cr_id=change_request.id, ctx=auth_ctx)

    from application.models import ChangeRequest
    assert ChangeRequest.objects.filter(id=change_request.id).exists()

    from workflow.models import WorkflowItemState
    item_state = WorkflowItemState.objects.get(item_id=change_request.id, item_type="ChangeRequest")
    assert item_state.current_state == "outdated"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest application/tests/test_change_request_service.py::test_delete_change_request_calls_outdate_not_hard_delete -v`
Expected: FAIL (row doesn't exist — the current queryset-level `.delete()` runs)

- [ ] **Step 3: Replace the delete body in `change_request_service.py:314`**

Replace:
```python
ChangeRequest.objects.filter(id=cr_id).delete()
```
With (note: this call site works off `cr_id` directly rather than a fetched instance — fetch the `workspace_id` first, since `outdate()` needs it):
```python
from workflow.services import outdate

change_request = ChangeRequest.objects.get(id=cr_id)
outdate(
    item_id=cr_id,
    item_type="ChangeRequest",
    workspace_id=change_request.workspace_id,
    ctx=ctx,
    reason="deleted via change_request.delete",
)
```

Also update the misleading docstring at line 295 (currently claims "soft-delete... sets status to rejected") to describe what the method now actually does:
```python
"""Outdate a change request (soft-delete via the workflow engine).

Transitions the item's WorkflowItemState to "outdated" — the record is
never removed from the database, and can be restored via workflow.services.reactivate().
"""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest application/tests/test_change_request_service.py::test_delete_change_request_calls_outdate_not_hard_delete -v`
Expected: PASS

- [ ] **Step 5: Commit (3g + 3h)**

```bash
git add backend/application/test_service.py backend/application/change_request_service.py backend/application/tests/test_change_request_service.py
git commit -m "fix: route TestCase and ChangeRequest delete through workflow outdate(), fixing ChangeRequest docstring/behavior mismatch"
```

---

## Task 4: Backfill already-deleted records

**Files:**
- Create: `backend/workflow/management/commands/backfill_outdated_from_legacy_status.py`
- Test: `backend/workflow/tests/test_backfill_outdated_command.py`

**Interfaces:**
- Consumes: `workflow.services.outdate()` (Task 2), the 4 legacy fields (`Requirement.lifecycle_status`, `Adr.status`, `ArchitectureElement.lifecycle_status`, `GlossaryTerm.lifecycle_status`).
- Produces: a one-shot, idempotent management command (`python manage.py backfill_outdated_from_legacy_status`) that transitions every already-"deleted" record's `WorkflowItemState` to `"outdated"`, matching the pattern of `backend/workflow/management/commands/backfill_workflow_item_states.py`.

- [ ] **Step 1: Write the failing test**

```python
# backend/workflow/tests/test_backfill_outdated_command.py
import pytest
from django.core.management import call_command


@pytest.mark.django_db
def test_backfill_transitions_legacy_deleted_requirements_to_outdated(requirement_with_workflow, auth_ctx):
    from persistence.models import Requirement

    item_id, workspace_id = requirement_with_workflow
    requirement = Requirement.objects.get(id=item_id)
    requirement.lifecycle_status = "deleted"
    requirement.save(update_fields=["lifecycle_status"])

    call_command("backfill_outdated_from_legacy_status")

    from workflow.models import WorkflowItemState
    item_state = WorkflowItemState.objects.get(item_id=item_id, item_type="Requirement")
    assert item_state.current_state == "outdated"


@pytest.mark.django_db
def test_backfill_is_idempotent(requirement_with_workflow, auth_ctx):
    from persistence.models import Requirement

    item_id, workspace_id = requirement_with_workflow
    requirement = Requirement.objects.get(id=item_id)
    requirement.lifecycle_status = "deleted"
    requirement.save(update_fields=["lifecycle_status"])

    call_command("backfill_outdated_from_legacy_status")
    call_command("backfill_outdated_from_legacy_status")  # must not raise or double-transition

    from workflow.models import WorkflowItemState, WorkflowHistoryEntry
    item_state = WorkflowItemState.objects.get(item_id=item_id, item_type="Requirement")
    assert item_state.current_state == "outdated"
    history_count = WorkflowHistoryEntry.objects.filter(item_state=item_state, to_state="outdated").count()
    assert history_count == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest workflow/tests/test_backfill_outdated_command.py -v`
Expected: FAIL with `CommandError: Unknown command: 'backfill_outdated_from_legacy_status'`

- [ ] **Step 3: Implement the management command**

```python
# backend/workflow/management/commands/backfill_outdated_from_legacy_status.py
from django.core.management.base import BaseCommand

from workflow.models import WorkflowItemState
from workflow.services import outdate
from application.models import Adr


class _SystemAuthContext:
    """Minimal ctx stand-in for a system-run backfill (not a real user)."""
    user_id = "system:backfill_outdated_from_legacy_status"


LEGACY_DELETED_LOOKUPS = [
    ("persistence.models", "Requirement", "lifecycle_status", "deleted", "Requirement"),
    ("persistence.models", "ArchitectureElement", "lifecycle_status", "deleted", "ArchitectureElement"),
    ("persistence.models", "GlossaryTerm", "lifecycle_status", "deleted", "GlossaryTerm"),
    ("application.models", "Adr", "status", Adr.Status.DELETED, "Adr"),
]


class Command(BaseCommand):
    help = "One-shot backfill: transition already-legacy-deleted records to the workflow 'outdated' state."

    def handle(self, *args, **options):
        from importlib import import_module

        ctx = _SystemAuthContext()
        total = 0

        for module_path, class_name, field_name, deleted_value, item_type in LEGACY_DELETED_LOOKUPS:
            model = getattr(import_module(module_path), class_name)
            queryset = model.objects.filter(**{field_name: deleted_value})

            for obj in queryset:
                item_state = WorkflowItemState.objects.filter(
                    item_id=obj.id, item_type=item_type
                ).first()
                if item_state is None or item_state.current_state == "outdated":
                    continue  # no workflow item, or already backfilled - idempotent skip
                outdate(
                    item_id=obj.id,
                    item_type=item_type,
                    workspace_id=item_state.workspace_id,
                    ctx=ctx,
                    reason="backfilled from legacy deleted status",
                )
                total += 1

        self.stdout.write(self.style.SUCCESS(f"Backfilled {total} records to outdated."))
```

**Note for the implementer:** confirm the exact import path/class name for `AuthContext` used elsewhere in `services.py` — `_SystemAuthContext` above only needs to satisfy whatever attribute `outdate()` actually reads off `ctx` (confirmed as `ctx.user_id` in Task 2's implementation), so this minimal stand-in should work without needing the real `AuthContext` class, but verify by running the test.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest workflow/tests/test_backfill_outdated_command.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Run the command for real against the dev database**

Run: `cd backend && python manage.py backfill_outdated_from_legacy_status`
Expected: `Backfilled N records to outdated.` (N may be 0 if there are no legacy-deleted records yet — that's fine)

- [ ] **Step 6: Commit**

```bash
git add backend/workflow/management/commands/backfill_outdated_from_legacy_status.py backend/workflow/tests/test_backfill_outdated_command.py
git commit -m "feat: add one-shot backfill command for legacy deleted records"
```

---

## Post-Plan Verification

- [ ] Run the full backend test suite once all tasks are committed: `cd backend && python -m pytest` — expect no new failures beyond any pre-existing, unrelated ones (note them if so, don't attempt to fix out-of-scope failures in this plan).
- [ ] Grep for any remaining direct hard `.delete()` or `lifecycle_status = "deleted"` / `Adr.Status.DELETED` assignments outside of the now-replaced 8 call sites, to confirm nothing was missed: `grep -rn "lifecycle_status = \"deleted\"\|Status.DELETED\|\.delete()" backend/application/*.py`

---

*Plan complete. Next: choose an execution approach (see below).*
