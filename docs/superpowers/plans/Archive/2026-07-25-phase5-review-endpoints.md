# Phase 5 — Review-Endpunkte Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose a `review.*` MCP tool group (`approve`/`reject`/`request_changes`/`list_pending`) as a thin wrapper over the existing `WorkflowFacade`, and introduce a per-workspace `ReviewPolicy` (`mode` + `min_confidence`) that governs whether `ai_derivation_service`'s `policy="auto"` path may cross an approval gate unsupervised.

**Architecture:** Reuses Phase 0's universal `outdate` transition and `WorkflowDefinitionDTO.initial_state`, and Phase 3's `auto_approve_target`/`is_approval_gate` concepts — no new `state_meta` flags. One new persistence model (`ReviewPolicy`, mirrors `PromptTemplate`'s tenant/workspace-override scoping but without versioning). `_is_approval_gate` is promoted from a private `AiDerivationService` staticmethod to a shared `workflow.services.is_approval_gate` function so both the derivation service and the new tool group depend on the workflow layer, not on each other.

**Tech Stack:** Django 4.2 (models/migrations), DRF (REST settings endpoint), MCP tool group (`mcp_server/tools/`).

## Global Constraints

- Branch: continue on `feat/reqogniloom-vision-consolidation` (Phases 0-4 all merged there, not `main`) unless the user says otherwise before work starts.
- Every new write tool name MUST be added to `backend/mcp_server/tool_registry.py`'s `_WRITE_TOOL_PREFIXES` — this exact omission caused Critical findings in earlier phases.
- No confidence signal exists anywhere in the codebase today (verified: zero hits for `confidence` in `application/ai_derivation_service.py` and `backend/llm_adapter/`). `review_high_risk` mode therefore uses a minimal, explicitly-documented heuristic (Task 2) — this is a deliberate scope decision, not an oversight.
- `review_changes` mode has no "modifying an existing approved artifact" flow to distinguish from "creating a new one" among the 6 current derive tools (all 6 are pure creates). It is implemented as a stored, forward-compatible config value that currently behaves identically to `auto` — documented as YAGNI-deferred, not silently dropped.
- Single-user/homelab system (no production traffic) — `list_pending`'s per-item transition check (Task 3) does not need bulk-query optimization.

---

### Task 1: `ReviewPolicy` model + migration + resolver service method

**Files:**
- Modify: `backend/persistence/models.py` (add `ReviewPolicy` class, after `PromptTemplate` around line 1560-1620)
- Create: `backend/persistence/migrations/0046_add_review_policy.py`
- Modify: `backend/application/settings_service.py` (add `ReviewPolicy` resolver methods)
- Test: `backend/application/tests/test_settings_service.py`

**Interfaces:**
- Produces: `persistence.models.ReviewPolicy` (fields: `tenant`, `workspace_id: UUID | None`, `mode: str`, `min_confidence: float`)
- Produces: `persistence.models.REVIEW_POLICY_MODES = ("auto", "review_changes", "review_all", "review_high_risk")`
- Produces: `SettingsService.get_effective_review_policy(ctx, workspace_id: UUID | None) -> ReviewPolicy` — resolution order: active workspace-scoped row -> active tenant-global row (`workspace_id=None`) -> an unsaved `ReviewPolicy(mode="auto", min_confidence=0.7)` default instance (never creates a row for a read).
- Produces: `SettingsService.update_review_policy(ctx, *, workspace_id: UUID | None, mode: str, min_confidence: float) -> ReviewPolicy` — upserts (not versioned, unlike `PromptTemplate`) the single row for `(tenant, workspace_id)`, validating `mode` is one of `REVIEW_POLICY_MODES` and `0.0 <= min_confidence <= 1.0` (else `ValidationError`).

- [ ] **Step 1: Write the failing model test**

```python
# backend/persistence/tests/test_review_policy_model.py
import pytest
from persistence.models import ReviewPolicy, Tenant


@pytest.mark.django_db
def test_review_policy_defaults_and_scope():
    tenant = Tenant.objects.create(name="t1", slug="t1")
    row = ReviewPolicy.objects.create(tenant=tenant, workspace_id=None, mode="review_all", min_confidence=0.9)
    assert row.workspace_id is None
    assert row.mode == "review_all"
    assert row.min_confidence == 0.9
```

Run: `pytest backend/persistence/tests/test_review_policy_model.py -v`
Expected: FAIL — `ImportError: cannot import name 'ReviewPolicy'`

- [ ] **Step 2: Add the model**

```python
# backend/persistence/models.py — insert after the PromptTemplate class

REVIEW_POLICY_MODES = ("auto", "review_changes", "review_all", "review_high_risk")


class ReviewPolicy(TenantScopedModel):
    """Per-workspace (or tenant-global) AI-derivation review policy (Phase 5).

    Governs whether ``AiDerivationService``'s ``policy="auto"`` path
    (``_auto_approve``) may cross an approval gate unsupervised, or must stop
    and leave the item in its pre-gate state for a human to process via the
    ``review.*`` MCP tool group. Unlike ``PromptTemplate`` this is a plain
    upsert target, not append-only version history — there is no audit value
    in keeping old policy values around, only the effective one matters.

    ``workspace_id=None`` is the tenant-wide default; a non-null
    ``workspace_id`` overrides it for that workspace only. At most one row
    per ``(tenant, workspace_id)`` — enforced by the unique index below.
    """

    mode = models.CharField(
        max_length=32,
        choices=[(m, m) for m in REVIEW_POLICY_MODES],
        default="auto",
        help_text="auto | review_changes | review_all | review_high_risk.",
    )
    min_confidence = models.FloatField(
        default=0.7,
        help_text="Threshold used only by review_high_risk mode.",
    )
    workspace_id = models.UUIDField(
        null=True,
        blank=True,
        help_text="Workspace override scope. NULL means tenant-wide default.",
    )

    class Meta:
        db_table = "pl_review_policy"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "workspace_id"], name="uq_review_policy_scope"
            ),
        ]

    def __str__(self) -> str:
        scope = str(self.workspace_id) if self.workspace_id else "tenant-global"
        return f"ReviewPolicy({scope}, {self.mode})"
```

- [ ] **Step 3: Generate + review the migration**

Run: `python backend/manage.py makemigrations persistence`
Expected: creates `backend/persistence/migrations/0046_add_review_policy.py` with a `CreateModel` for `ReviewPolicy` and the `uq_review_policy_scope` unique constraint. Open it and confirm it depends on `0045_prompt_template_versioning_cleanup`.

- [ ] **Step 4: Run the model test**

Run: `pytest backend/persistence/tests/test_review_policy_model.py -v`
Expected: PASS

- [ ] **Step 5: Write the failing resolver-service tests**

```python
# backend/application/tests/test_settings_service.py — add to existing file

def test_get_effective_review_policy_defaults_to_auto(settings_service, ctx):
    policy = settings_service.get_effective_review_policy(ctx, workspace_id=None)
    assert policy.mode == "auto"
    assert policy.min_confidence == 0.7


def test_get_effective_review_policy_workspace_overrides_tenant_global(
    settings_service, ctx, workspace_id
):
    settings_service.update_review_policy(
        ctx, workspace_id=None, mode="review_all", min_confidence=0.5
    )
    settings_service.update_review_policy(
        ctx, workspace_id=workspace_id, mode="review_high_risk", min_confidence=0.8
    )
    scoped = settings_service.get_effective_review_policy(ctx, workspace_id=workspace_id)
    assert scoped.mode == "review_high_risk"
    global_only = settings_service.get_effective_review_policy(ctx, workspace_id=None)
    assert global_only.mode == "review_all"


def test_update_review_policy_rejects_unknown_mode(settings_service, ctx):
    from application.base import ValidationError
    with pytest.raises(ValidationError):
        settings_service.update_review_policy(
            ctx, workspace_id=None, mode="bogus", min_confidence=0.5
        )


def test_update_review_policy_rejects_out_of_range_confidence(settings_service, ctx):
    from application.base import ValidationError
    with pytest.raises(ValidationError):
        settings_service.update_review_policy(
            ctx, workspace_id=None, mode="auto", min_confidence=1.5
        )
```

Run: `pytest backend/application/tests/test_settings_service.py -k review_policy -v`
Expected: FAIL — `AttributeError: 'SettingsService' object has no attribute 'get_effective_review_policy'`

- [ ] **Step 6: Implement the resolver methods**

```python
# backend/application/settings_service.py — add near the PromptTemplate section

from persistence.models import ReviewPolicy, REVIEW_POLICY_MODES


class SettingsService(ServiceBase):
    ...

    # ---- ReviewPolicy (Phase 5) ----------------------------------------

    def get_effective_review_policy(
        self, ctx: AuthContext, *, workspace_id: "UUID | None" = None
    ) -> ReviewPolicy:
        """Return the effective ReviewPolicy: workspace override, else tenant-
        global row, else an unsaved default (mode="auto", min_confidence=0.7)
        — never creates a row for a read."""
        self._set_tenant_context(ctx)
        if workspace_id is not None:
            row = ReviewPolicy.objects.filter(
                tenant_id=ctx.tenant_id, workspace_id=workspace_id
            ).first()
            if row is not None:
                return row
        row = ReviewPolicy.objects.filter(
            tenant_id=ctx.tenant_id, workspace_id=None
        ).first()
        if row is not None:
            return row
        return ReviewPolicy(tenant_id=ctx.tenant_id, workspace_id=workspace_id, mode="auto", min_confidence=0.7)

    def update_review_policy(
        self,
        ctx: AuthContext,
        *,
        workspace_id: "UUID | None",
        mode: str,
        min_confidence: float,
    ) -> ReviewPolicy:
        """Upsert the single (tenant, workspace_id) ReviewPolicy row."""
        self._set_tenant_context(ctx)
        if mode not in REVIEW_POLICY_MODES:
            raise ValidationError(
                f"Unknown review policy mode '{mode}'. Valid: {', '.join(REVIEW_POLICY_MODES)}."
            )
        if not (0.0 <= min_confidence <= 1.0):
            raise ValidationError("min_confidence must be between 0.0 and 1.0.")
        row, _ = ReviewPolicy.objects.update_or_create(
            tenant_id=ctx.tenant_id,
            workspace_id=workspace_id,
            defaults={"mode": mode, "min_confidence": min_confidence},
        )
        return row
```

- [ ] **Step 7: Run tests, then commit**

Run: `pytest backend/persistence/tests/test_review_policy_model.py backend/application/tests/test_settings_service.py -v`
Expected: PASS

```bash
git add backend/persistence/models.py backend/persistence/migrations/0046_add_review_policy.py backend/application/settings_service.py backend/persistence/tests/test_review_policy_model.py backend/application/tests/test_settings_service.py
git commit -m "feat: add per-workspace ReviewPolicy model and resolver service"
```

---

### Task 2: Shared `is_approval_gate` helper + wire `ReviewPolicy` into `_auto_approve`

**Files:**
- Modify: `backend/workflow/services.py` (add module-level `is_approval_gate`)
- Modify: `backend/application/ai_derivation_service.py` (`_auto_approve`, its 3 callers stay unchanged — only the internals of `_auto_approve` and `_is_approval_gate` change)
- Test: `backend/application/tests/test_ai_derivation_service.py`

**Interfaces:**
- Consumes: `TransitionDefinitionDTO.allowed_roles` (`backend/workflow/definition_store.py:57`), `SettingsService.get_effective_review_policy` (Task 1)
- Produces: `workflow.services.is_approval_gate(transition_dto: TransitionDefinitionDTO) -> bool` — `"editor" not in transition_dto.allowed_roles` (moved verbatim from `AiDerivationService._is_approval_gate`)
- Produces: `AiDerivationService._estimate_confidence(purpose: str, artifact_id) -> float | None` — returns `1.0` when the active LLM provider is `mock` (deterministic output), else `None` (no real confidence signal exists yet; `None` is treated as "below any threshold" by `review_high_risk`).

- [ ] **Step 1: Write the failing test for the shared helper**

```python
# backend/workflow/tests/test_services_is_approval_gate.py
from workflow.definition_store import TransitionDefinitionDTO
from workflow.services import is_approval_gate


def test_editor_allowed_transition_is_not_a_gate():
    t = TransitionDefinitionDTO(from_state="draft", to_state="in_review", allowed_roles=("editor", "admin"))
    assert is_approval_gate(t) is False


def test_approver_only_transition_is_a_gate():
    t = TransitionDefinitionDTO(from_state="in_review", to_state="approved", allowed_roles=("approver", "admin"))
    assert is_approval_gate(t) is True
```

Run: `pytest backend/workflow/tests/test_services_is_approval_gate.py -v`
Expected: FAIL — `ImportError: cannot import name 'is_approval_gate'`

- [ ] **Step 2: Add `is_approval_gate` to `workflow/services.py`**

```python
# backend/workflow/services.py — add near the other public facade functions

def is_approval_gate(transition_dto: "TransitionDefinitionDTO") -> bool:
    """True if *transition_dto* is a genuine human approval decision.

    A transition an ``editor`` can already take unsupervised (its
    ``allowed_roles`` includes ``"editor"``) is a self-service submission step
    (e.g. ``draft -> in_review``), not an approval. A transition restricted to
    ``approver``/``admin`` (no ``editor``) is the real "someone signed off on
    this" gate. Shared by ``AiDerivationService._auto_approve`` (Phase 3) and
    the ``review.*`` MCP tool group (Phase 5) so neither layer imports from
    the other for this concept.
    """
    return "editor" not in transition_dto.allowed_roles
```

- [ ] **Step 3: Run the helper test**

Run: `pytest backend/workflow/tests/test_services_is_approval_gate.py -v`
Expected: PASS

- [ ] **Step 4: Write the failing test for policy-gated `_auto_approve`**

```python
# backend/application/tests/test_ai_derivation_service.py — add to existing file

def test_auto_approve_stops_immediately_under_review_all_policy(
    ai_derivation_service, ctx, workspace_id, settings_service
):
    settings_service.update_review_policy(
        ctx, workspace_id=workspace_id, mode="review_all", min_confidence=0.7
    )
    final_state = ai_derivation_service._auto_approve(
        "Adr", some_adr_id, workspace_id, ctx
    )
    assert final_state == "Draft"  # never left the initial state


def test_auto_approve_review_high_risk_blocks_without_confidence_signal(
    ai_derivation_service, ctx, workspace_id, settings_service
):
    settings_service.update_review_policy(
        ctx, workspace_id=workspace_id, mode="review_high_risk", min_confidence=0.5
    )
    # Default LLM provider in tests is "mock" -> _estimate_confidence returns 1.0,
    # which is >= 0.5, so the real-provider "no signal" case is exercised via
    # monkeypatching _estimate_confidence to return None.
    ai_derivation_service._estimate_confidence = lambda *a, **kw: None
    final_state = ai_derivation_service._auto_approve(
        "Adr", some_adr_id, workspace_id, ctx
    )
    assert final_state != "Approved"


def test_auto_approve_unchanged_under_auto_policy(
    ai_derivation_service, ctx, workspace_id
):
    # No ReviewPolicy row exists -> resolver default is "auto" -> identical
    # behaviour to pre-Phase-5 (regression guard for the existing
    # test_auto_approve_stops_before_approval_gate_for_risk family).
    final_state = ai_derivation_service._auto_approve(
        "Adr", some_adr_id, workspace_id, ctx
    )
    assert final_state == "Approved"
```

Run: `pytest backend/application/tests/test_ai_derivation_service.py -k auto_approve_review -v`
Expected: FAIL — behaviour not yet policy-aware (`review_all`/`review_high_risk` tests fail; `auto` test already passes)

- [ ] **Step 5: Wire `ReviewPolicy` into `_auto_approve`**

```python
# backend/application/ai_derivation_service.py — replace _is_approval_gate call
# sites and the method body of _auto_approve

    def _auto_approve(
        self,
        item_type: str,
        item_id: UUID | str,
        workspace_id: UUID | str,
        ctx: AuthContext,
    ) -> str:
        """... (existing docstring, append:)

        Phase 5: the walk additionally consults the workspace's effective
        ``ReviewPolicy`` (``SettingsService.get_effective_review_policy``)
        before crossing any approval gate:
          - ``mode="auto"``: unchanged pre-Phase-5 behaviour (this file's
            original docstring above).
          - ``mode="review_all"``: never crosses an approval gate — stops at
            the first self-service hop's boundary, same as if no explicit
            ``auto_approve_target`` existed and ``ctx`` held no approver role.
          - ``mode="review_changes"``: identical to "auto" for now — none of
            the 6 current derive tools modifies a pre-existing approved
            artifact, so there is nothing to distinguish yet. Stored for
            forward compatibility (see this plan's Global Constraints).
          - ``mode="review_high_risk"``: crosses a gate only if
            ``_estimate_confidence(...)`` returns a value
            ``>= policy.min_confidence``; ``None`` (no signal) never crosses.
        """
        from workflow.definition_store import get_state_meta
        from workflow.models import WorkflowEngineDefinition
        from workflow.services import get_available_transitions, is_approval_gate, transition
        from application.settings_service import SettingsService

        policy = SettingsService().get_effective_review_policy(ctx, workspace_id=workspace_id)
        confidence = (
            self._estimate_confidence(item_type, item_id)
            if policy.mode == "review_high_risk"
            else None
        )

        current_state = "draft"
        try:
            for _ in range(5):
                available = get_available_transitions(
                    item_id=item_id, item_type=item_type, workspace_id=workspace_id
                )
                current_state = available.current_state or current_state

                definition = WorkflowEngineDefinition.objects.filter(
                    workspace_id=workspace_id, item_type=item_type
                ).first()
                workflow_json = definition.workflow_json if definition else {}

                if get_state_meta(workflow_json, current_state).get(
                    "auto_approve_target", False
                ):
                    break

                if not available.transitions:
                    break

                has_explicit_target = any(
                    meta.get("auto_approve_target", False)
                    for meta in workflow_json.get("state_meta", {}).values()
                )

                next_transition = next(
                    (
                        t
                        for t in available.transitions
                        if not get_state_meta(workflow_json, t.to_state).get(
                            "is_outdated_equivalent", False
                        )
                    ),
                    None,
                )
                if next_transition is None:
                    break

                if is_approval_gate(next_transition):
                    if policy.mode == "review_all":
                        break
                    if policy.mode == "review_high_risk" and (
                        confidence is None or confidence < policy.min_confidence
                    ):
                        break
                    if policy.mode in ("auto", "review_changes") and not has_explicit_target:
                        break

                result = transition(
                    item_id=item_id,
                    target_state=next_transition.to_state,
                    change_reason=f"auto-approved via AI-Derivation ({item_type})",
                    ctx=ctx,
                    item_type=item_type,
                    workspace_id=workspace_id,
                )
                current_state = result.new_state
        except Exception:  # noqa: BLE001 — auto-approve must never break a write
            logger.warning(
                "Auto-approve stopped for %s %s at state %s",
                item_type,
                item_id,
                current_state,
                exc_info=True,
            )
        return current_state

    def _estimate_confidence(
        self, item_type: str, item_id: "UUID | str"
    ) -> "float | None":
        """Minimal v1 confidence heuristic (Phase 5).

        No LLM adapter surfaces a real confidence score today (verified:
        zero hits across ``llm_adapter/``). The mock provider's output is
        fully deterministic, so it is treated as maximum confidence (1.0);
        every real provider currently returns ``None`` ("no signal"), which
        ``_auto_approve``'s ``review_high_risk`` branch treats as always
        below threshold — the conservative default until a provider actually
        reports one.
        """
        from django.conf import settings as django_settings

        if getattr(django_settings, "LLM_PROVIDER", "mock") == "mock":
            return 1.0
        return None
```

Remove the old `_is_approval_gate` staticmethod from `AiDerivationService` entirely (superseded by `workflow.services.is_approval_gate`); grep the file for any other internal callers first.

- [ ] **Step 6: Run tests, fix, run again**

Run: `pytest backend/application/tests/test_ai_derivation_service.py -v`
Expected: PASS (including the pre-existing `test_auto_approve_stops_before_approval_gate_for_risk` and the new Step 4 tests)

- [ ] **Step 7: Commit**

```bash
git add backend/workflow/services.py backend/application/ai_derivation_service.py backend/workflow/tests/test_services_is_approval_gate.py backend/application/tests/test_ai_derivation_service.py
git commit -m "feat: gate auto-approve on per-workspace ReviewPolicy"
```

---

### Task 3: `review.*` MCP tool group

**Files:**
- Create: `backend/mcp_server/tools/review.py`
- Modify: `backend/mcp_server/tool_registry.py` (`_ensure_groups`, `_WRITE_TOOL_PREFIXES`)
- Test: `backend/mcp_server/tests/test_review_tool_group.py`

**Interfaces:**
- Consumes: `WorkflowFacade.transition`, `WorkflowFacade.get_available_transitions`, `WorkflowFacade.get_definition` (`backend/application/workflow_facade.py`), `workflow.services.is_approval_gate` (Task 2), `workflow.models.WorkflowItemState` (fields: `item_id`, `item_type`, `workspace_id`, `current_state`, per `backend/workflow/models.py:186-211`)
- Produces: `ReviewToolGroup` with tools `review.list_pending`, `review.approve`, `review.reject`, `review.request_changes`

- [ ] **Step 1: Write the failing tool-group tests**

```python
# backend/mcp_server/tests/test_review_tool_group.py
import pytest


@pytest.mark.django_db
def test_list_pending_returns_items_awaiting_an_approval_gate(
    review_tool_group, auth_context, api_key, adr_awaiting_review, adr_in_draft
):
    result = review_tool_group.execute_tool(
        "review.list_pending", {}, auth_context, api_key
    )
    ids = {item["item_id"] for item in result.data["items"]}
    assert str(adr_awaiting_review.id) in ids
    assert str(adr_in_draft.id) not in ids  # draft->in_review is editor-allowed, not a gate


@pytest.mark.django_db
def test_approve_transitions_to_auto_approve_target(
    review_tool_group, auth_context, api_key, adr_awaiting_review
):
    result = review_tool_group.execute_tool(
        "review.approve",
        {"item_id": str(adr_awaiting_review.id), "item_type": "Adr", "workspace_id": str(adr_awaiting_review.workspace_id)},
        auth_context,
        api_key,
    )
    assert result.data["new_state"] == "Approved"


@pytest.mark.django_db
def test_reject_transitions_to_outdated(
    review_tool_group, auth_context, api_key, adr_awaiting_review
):
    result = review_tool_group.execute_tool(
        "review.reject",
        {
            "item_id": str(adr_awaiting_review.id),
            "item_type": "Adr",
            "workspace_id": str(adr_awaiting_review.workspace_id),
            "reason": "not aligned with current architecture",
        },
        auth_context,
        api_key,
    )
    assert result.data["new_state"] == "outdated"


@pytest.mark.django_db
def test_request_changes_transitions_to_initial_state(
    review_tool_group, auth_context, api_key, adr_awaiting_review
):
    result = review_tool_group.execute_tool(
        "review.request_changes",
        {
            "item_id": str(adr_awaiting_review.id),
            "item_type": "Adr",
            "workspace_id": str(adr_awaiting_review.workspace_id),
            "reason": "needs a risk section",
        },
        auth_context,
        api_key,
    )
    assert result.data["new_state"] == "Draft"


def test_write_tools_are_rbac_gated():
    from mcp_server.tool_registry import _WRITE_TOOL_PREFIXES
    assert "review.approve" in _WRITE_TOOL_PREFIXES
    assert "review.reject" in _WRITE_TOOL_PREFIXES
    assert "review.request_changes" in _WRITE_TOOL_PREFIXES
    assert "review.list_pending" not in _WRITE_TOOL_PREFIXES
```

Run: `pytest backend/mcp_server/tests/test_review_tool_group.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'mcp_server.tools.review'`

- [ ] **Step 2: Implement `ReviewToolGroup`**

```python
"""
MCP Tool Group for review/approval endpoints (Phase 5, REQ-L2-RV-001).

A deliberately thin wrapper over WorkflowFacade — no new state machine, no
new state_meta flags. Reuses:
  - workflow.services.is_approval_gate (Task 2) for review.list_pending,
  - WorkflowEngineDefinition's state_meta "auto_approve_target" (Phase 3) for
    review.approve's destination,
  - the universal Phase-0 "outdate" transition for review.reject,
  - WorkflowDefinitionDTO.initial_state for review.request_changes.
"""
from __future__ import annotations

from typing import Any, Dict

from auth_tenancy.context import AuthContext

from application.base import PermissionDeniedError, ValidationError
from application.workflow_facade import WorkflowFacade

from mcp_server.tools.base import (
    BaseToolGroup,
    ToolResult,
    optional_uuid,
    require_param,
    require_uuid,
    write_mcp_audit,
)


class ReviewToolGroup(BaseToolGroup):
    """review.* tool group (REQ-L2-RV-001)."""

    _TOOL_MAP = {
        "review.list_pending": "_handle_list_pending",
        "review.approve": "_handle_approve",
        "review.reject": "_handle_reject",
        "review.request_changes": "_handle_request_changes",
    }

    _TOOL_SCHEMAS = [
        {
            "name": "review.list_pending",
            "description": (
                "List items across one or all artifact types whose current "
                "workflow state is one hop away from a human approval gate "
                "(a transition whose allowed_roles excludes 'editor')."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "item_type": {"type": "string", "description": "Optional entity type filter."},
                    "workspace_id": {"type": "string", "description": "Workspace to scope the search to."},
                },
                "required": ["workspace_id"],
            },
        },
        {
            "name": "review.approve",
            "description": (
                "Approve an item currently awaiting review: transitions it to "
                "its preset's auto_approve_target state (falls back to the "
                "first available approver/admin-gated transition's target if "
                "no explicit auto_approve_target is configured)."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "item_id": {"type": "string"},
                    "item_type": {"type": "string"},
                    "workspace_id": {"type": "string"},
                    "change_reason": {"type": "string"},
                },
                "required": ["item_id", "item_type", "workspace_id"],
            },
        },
        {
            "name": "review.reject",
            "description": (
                "Reject an item currently awaiting review: transitions it to "
                "the universal 'outdated' state (Phase 0), recording reason "
                "in the workflow history."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "item_id": {"type": "string"},
                    "item_type": {"type": "string"},
                    "workspace_id": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["item_id", "item_type", "workspace_id"],
            },
        },
        {
            "name": "review.request_changes",
            "description": (
                "Send an item currently awaiting review back to its "
                "workflow's initial state for rework, recording reason in "
                "the workflow history."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "item_id": {"type": "string"},
                    "item_type": {"type": "string"},
                    "workspace_id": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["item_id", "item_type", "workspace_id"],
            },
        },
    ]

    # ------------------------------------------------------------------

    def _handle_list_pending(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        from workflow.models import WorkflowItemState
        from workflow.services import is_approval_gate

        workspace_id = require_uuid(params, "workspace_id")
        item_type = params.get("item_type")

        facade = WorkflowFacade()
        qs = WorkflowItemState.objects.filter(
            tenant_id=auth_context.tenant_id, workspace_id=workspace_id
        )
        if item_type:
            qs = qs.filter(item_type=item_type)

        pending = []
        for state in qs:
            available = facade.get_available_transitions(
                state.item_id,
                auth_context,
                item_type=state.item_type,
                workspace_id=workspace_id,
            )
            if any(is_approval_gate(t) for t in available.transitions):
                pending.append(
                    {
                        "item_id": str(state.item_id),
                        "item_type": state.item_type,
                        "current_state": state.current_state,
                    }
                )
        return ToolResult.ok({"items": pending, "count": len(pending)})

    def _handle_approve(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        return self._transition_to_gate_target(
            params=params,
            auth_context=auth_context,
            api_key=api_key,
            operation="approve",
            reason_param="change_reason",
            prefer_auto_approve_target=True,
        )

    def _handle_reject(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        item_id = require_uuid(params, "item_id")
        item_type = require_param(params, "item_type")
        workspace_id = require_uuid(params, "workspace_id")
        reason = params.get("reason", "")

        facade = WorkflowFacade()
        try:
            result = facade.transition(
                item_id=item_id,
                target_state="outdated",
                change_reason=reason,
                ctx=auth_context,
                item_type=item_type,
                workspace_id=workspace_id,
            )
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        except ValidationError as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))

        write_mcp_audit(
            ctx=auth_context, operation="reject", entity_type=item_type,
            entity_id=item_id, tool_name="review.reject", api_key=api_key,
        )
        return ToolResult.ok({"item_id": str(item_id), "new_state": result.new_state})

    def _handle_request_changes(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        item_id = require_uuid(params, "item_id")
        item_type = require_param(params, "item_type")
        workspace_id = require_uuid(params, "workspace_id")
        reason = params.get("reason", "")

        facade = WorkflowFacade()
        definition = facade.get_definition(auth_context, item_type=item_type, workspace_id=workspace_id)
        if definition is None:
            return ToolResult.error(
                "VALIDATION_ERROR", f"No workflow configured for {item_type} in this workspace."
            )

        try:
            result = facade.transition(
                item_id=item_id,
                target_state=definition.initial_state,
                change_reason=reason,
                ctx=auth_context,
                item_type=item_type,
                workspace_id=workspace_id,
            )
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        except ValidationError as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))

        write_mcp_audit(
            ctx=auth_context, operation="request_changes", entity_type=item_type,
            entity_id=item_id, tool_name="review.request_changes", api_key=api_key,
        )
        return ToolResult.ok({"item_id": str(item_id), "new_state": result.new_state})

    def _transition_to_gate_target(
        self, *, params, auth_context, api_key, operation, reason_param, prefer_auto_approve_target
    ) -> ToolResult:
        from workflow.definition_store import get_state_meta
        from workflow.models import WorkflowEngineDefinition
        from workflow.services import is_approval_gate

        item_id = require_uuid(params, "item_id")
        item_type = require_param(params, "item_type")
        workspace_id = require_uuid(params, "workspace_id")
        reason = params.get(reason_param, "")

        facade = WorkflowFacade()
        available = facade.get_available_transitions(
            item_id, auth_context, item_type=item_type, workspace_id=workspace_id
        )

        definition_row = WorkflowEngineDefinition.objects.filter(
            workspace_id=workspace_id, item_type=item_type
        ).first()
        workflow_json = definition_row.workflow_json if definition_row else {}

        target = None
        if prefer_auto_approve_target:
            target = next(
                (
                    t.to_state
                    for t in available.transitions
                    if get_state_meta(workflow_json, t.to_state).get("auto_approve_target", False)
                ),
                None,
            )
        if target is None:
            gate = next((t for t in available.transitions if is_approval_gate(t)), None)
            target = gate.to_state if gate is not None else None

        if target is None:
            return ToolResult.error(
                "VALIDATION_ERROR",
                f"No approval-shaped transition is available from '{available.current_state}' for {item_type}.",
            )

        try:
            result = facade.transition(
                item_id=item_id,
                target_state=target,
                change_reason=reason,
                ctx=auth_context,
                item_type=item_type,
                workspace_id=workspace_id,
            )
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        except ValidationError as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))

        write_mcp_audit(
            ctx=auth_context, operation=operation, entity_type=item_type,
            entity_id=item_id, tool_name=f"review.{operation}", api_key=api_key,
        )
        return ToolResult.ok({"item_id": str(item_id), "new_state": result.new_state})


__all__ = ["ReviewToolGroup"]
```

- [ ] **Step 3: Register the group + RBAC prefixes**

```python
# backend/mcp_server/tool_registry.py — in _WRITE_TOOL_PREFIXES, after the
# ai_derivation.* entries:
    "review.approve",
    "review.reject",
    "review.request_changes",
)
```

```python
# backend/mcp_server/tool_registry.py — in _ensure_groups(), alongside the
# other tool-group imports and self.register_groups({...}):
        from mcp_server.tools.review import ReviewToolGroup
        ...
        self.register_groups({
            ...
            "review": ReviewToolGroup(),
        })
```

- [ ] **Step 4: Run tests, fix, run again**

Run: `pytest backend/mcp_server/tests/test_review_tool_group.py -v`
Expected: PASS

- [ ] **Step 5: Run the full existing tool_registry regression test**

Run: `pytest backend/mcp_server/tests/test_tool_registry.py -v`
Expected: PASS (no orphaned write-prefix entries; `review` group's schemas listed in `tools/list`)

- [ ] **Step 6: Commit**

```bash
git add backend/mcp_server/tools/review.py backend/mcp_server/tool_registry.py backend/mcp_server/tests/test_review_tool_group.py
git commit -m "feat: add review.* MCP tool group (approve/reject/request_changes/list_pending)"
```

---

### Task 4: REST endpoint for `ReviewPolicy` configuration

**Files:**
- Modify: `backend/rest_api/settings_views.py`
- Modify: `backend/rest_api/serializers.py` (or wherever `LlmSettings`/`PromptTemplate` serializers live — check import in `settings_views.py` first)
- Modify: `backend/rest_api/urls.py`
- Test: `backend/rest_api/tests/test_review_policy_views.py`

**Interfaces:**
- Consumes: `SettingsService.get_effective_review_policy` / `.update_review_policy` (Task 1)
- Produces: `GET/PUT /api/v1/workspaces/{workspace_id}/review-policy/` — admin-only (mirrors the existing admin-only gate documented in `settings_service.py`'s module docstring for LlmSettings/PromptTemplate)

- [ ] **Step 1: Read the existing `settings_views.py` LlmSettings view for the exact admin-permission-check idiom and URL registration pattern before writing this task's view** (this file was not fully re-read in this plan's research pass — the implementer must open it first and mirror its existing `IsAdminUser`-style permission class and response shape, rather than inventing a new one).

- [ ] **Step 2: Write the failing REST test**

```python
# backend/rest_api/tests/test_review_policy_views.py
import pytest
from rest_framework.test import APIClient


@pytest.mark.django_db
def test_admin_can_get_and_update_review_policy(admin_api_client, workspace):
    resp = admin_api_client.get(f"/api/v1/workspaces/{workspace.id}/review-policy/")
    assert resp.status_code == 200
    assert resp.data["mode"] == "auto"

    resp = admin_api_client.put(
        f"/api/v1/workspaces/{workspace.id}/review-policy/",
        {"mode": "review_all", "min_confidence": 0.9},
        format="json",
    )
    assert resp.status_code == 200
    assert resp.data["mode"] == "review_all"


@pytest.mark.django_db
def test_non_admin_cannot_update_review_policy(editor_api_client, workspace):
    resp = editor_api_client.put(
        f"/api/v1/workspaces/{workspace.id}/review-policy/",
        {"mode": "review_all", "min_confidence": 0.9},
        format="json",
    )
    assert resp.status_code == 403


@pytest.mark.django_db
def test_update_review_policy_rejects_invalid_mode(admin_api_client, workspace):
    resp = admin_api_client.put(
        f"/api/v1/workspaces/{workspace.id}/review-policy/",
        {"mode": "bogus", "min_confidence": 0.9},
        format="json",
    )
    assert resp.status_code == 400
```

Run: `pytest backend/rest_api/tests/test_review_policy_views.py -v`
Expected: FAIL — 404 (URL not registered)

- [ ] **Step 3: Implement the view, serializer, and URL** (exact class names/base classes to be taken from the Step 1 read of the existing `LlmSettingsView`; wire the same `ValidationError -> 400`, `PermissionDenied -> 403` mapping already used there)

- [ ] **Step 4: Run tests, fix, run again**

Run: `pytest backend/rest_api/tests/test_review_policy_views.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/rest_api/settings_views.py backend/rest_api/serializers.py backend/rest_api/urls.py backend/rest_api/tests/test_review_policy_views.py
git commit -m "feat: add REST endpoint for per-workspace ReviewPolicy configuration"
```

---

### Task 5: Whole-branch regression + docs

**Files:**
- Modify: `docs/REQUIREMENTS.md` (register new REQ-IDs for Phase 5, following the same REQ-L2-RV-001-style convention used in `review.py`'s docstrings above — pick the next free REQ number)
- Modify: `docs/superpowers/specs/Archive/2026-07-23-reqogniloom-status-unification-design.md` (mark Phase 5 section 8 as implemented, note the `review_changes`/`review_high_risk` scope decisions from this plan's Global Constraints)

- [ ] **Step 1: Run the full backend test suite, record baseline-diffed results**

Run: `pytest backend -v`
Expected: only the already-known pre-existing failures/errors from `progress-phase4.md`'s baseline (2823 passed, 6 failed, 6 skipped, 166 errors) plus this phase's new passing tests — zero new regressions.

- [ ] **Step 2: Update `docs/REQUIREMENTS.md` and the design spec's Phase 5 section**

- [ ] **Step 3: Commit**

```bash
git add docs/REQUIREMENTS.md docs/superpowers/specs/Archive/2026-07-23-reqogniloom-status-unification-design.md
git commit -m "docs: mark Phase 5 review endpoints implemented, register REQ-IDs"
```

---

## Self-Review Notes (for the plan author, kept for traceability)

- **Spec coverage:** 8.1 (review.* tool group) -> Task 3. 8.2 (`mode`/`min_confidence` "jetzt umgesetzt") -> Tasks 1+2. `allowed_reviewers`/`require_pair_review` explicitly YAGNI per spec — not planned, matches spec's own scope cut.
- **Known open design debt, explicitly deferred, not hidden:** `review_changes` mode has no distinguishing behavior yet (no modify-in-place derive flow exists); `review_high_risk`'s confidence signal is a placeholder heuristic (mock=1.0, real providers=None) until an LLM adapter actually reports one. Both are called out in Global Constraints and in code docstrings so a future phase can find and complete them without re-deriving the reasoning.
- **Merge target:** same open question as Phase 4 — confirm with the user whether this branches off / merges into `feat/reqogniloom-vision-consolidation` before invoking `finishing-a-development-branch`.
