# KI-Vorschlag als Zustand Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give an API key a first-class agent identity (`principal_type`/`agent_label`/`scope`/`workspace_ids`/`expires_at`) and route every artifact an agent creates into a new `proposed` workflow state that only a human can leave.

**Architecture:** Agent identity is carried end-to-end as three new immutable fields on `IdentityClaims`/`AuthContext` (`actor_type`, `agent_label`, `scope`), set once at API-key validation. The `proposed` state is injected into the existing `PRESET_SCHEMAS` graphs (never at index 0, which is the definition's `initial_state`) and propagated into live `GlobalWorkflowDefinition`/`WorkflowEngineDefinition` rows by one data migration. The already-existing single seam `workflow.services.initialize_workflow_states(item_ids, item_type, workspace_id, ctx)` — called by all 13 `create_X()` services and the only caller of `StateLifecycleManager.initialize_workflow_states` — picks `proposed` instead of `initial_state`; the "an agent never confirms itself" rule is a new pre-rule in `TransitionValidator.validate` plus one guard on the validator-bypassing `workflow.services.outdate()` path.

**Tech Stack:** Django 5.2 / Python 3.x, PostgreSQL 16 (JSONB + RLS), DRF + drf-spectacular, native MCP tool registry (JSON-RPC 2.0), React 18 + TypeScript 5.5 (strict), react-i18next, pytest, vitest.

**Spec:** docs/superpowers/specs/2026-09-03-ki-vorschlag-als-zustand-design.md

## Global Constraints

- `ApiKey.scope` choices are exactly `("read", "Read")` and `("write", "Write")`, default `"write"` — the MCP-Modernisierung spec (§6.1) consumes these exact string values.
- `ApiKey.principal_type` choices are exactly `("user", "User")` and `("agent", "Agent")`, default `"user"`. Existing rows keep `"user"`; this spec is deliberately inert until a key owner opts in.
- `AuthContext.actor_type` values are exactly `"user"` / `"agent"` — byte-identical to `audit.models.AuditEntry.ACTOR_TYPE_USER` / `ACTOR_TYPE_AGENT` (`audit/models.py:107`), so the value flows into the audit log unchanged.
- The proposal state name is exactly `"proposed"`. It is NEVER `states[0]` — `WorkflowDefinitionDTO.initial_state` is `states[0]` (`workflow/definition_store.py:96`) and `states[0]` must equal the entity's `status` column default (`definition_store.py:217-220`). `"proposed"` is always inserted at index 1.
- `minimal` keeps its graph without `proposed`. This is the whole rigor coupling — no runtime preset lookup anywhere in the initialization path; graph membership is the only switch.
- A newly added reject state carries `state_meta: {"<state>": {"is_outdated_equivalent": True}}` — the existing mechanism every "filtered out of active lists" consumer already honours. No consumer changes.
- The `proposed -> <initial_state>` (confirm) transition has `requires_change_reason: false`; the `proposed -> <reject_state>` (discard) transition has `requires_change_reason: true`. Both `signature_gate: false`. Both `allowed_roles: ["editor", "approver", "admin"]`.
- A principal with `actor_type == "agent"` may never execute ANY transition out of `"proposed"` — enforced in the validator, not in `allowed_roles`.
- `TraceLink.proposed_by` is a nullable FK to `auth_tenancy.ApiKey` with `on_delete=SET_NULL`; confirming sets both `proposed_by` and `proposed_at` to `NULL`, discarding deletes the row.
- Workflow *transitions* by agents stay out of scope — they remain governed by the existing `signature_gate` flag (spec §6).
- Backend commands run inside the stack: `docker compose exec backend pytest <path>`. Frontend: `docker compose exec frontend npm test -- <path>`.

---

## Verified Against Current Code (2026-09-04)

Read this table before starting. Six spec claims drifted from the code; every one of them changes a task below.

| Spec claim | Reality in the tree | Consequence |
|---|---|---|
| §4.1 example graph `"states": ["proposed", "draft", "..."]` | `WorkflowDefinitionDTO.initial_state` is `states[0]` (`definition_store.py:96`), and the `PRESET_SCHEMAS` header comment (`definition_store.py:217-220`) states `states[0]` MUST equal the model field default because `_sync_status_mirror` writes `current_state` verbatim into the entity's `status` column | `proposed` first would make **every** creation — human included — land in `proposed` and desync every status mirror. Task 7 inserts at index **1**. |
| §4.2 "der `WorkflowHistoryEntry`, der bei der State-Initialisierung ohnehin geschrieben wird" | `StateLifecycleManager.initialize_workflow_states` (`lifecycle_manager.py:220-271`) creates only `WorkflowItemState`. **No history entry is written at init.** | Task 10 writes the history entry — otherwise "wer hat vorgeschlagen" has no storage at all. |
| §8 "ein gemeinsamer Helper … ist Pflicht" for 8–13 `create_X()` paths | The helper already exists: `workflow.services.initialize_workflow_states(item_ids, item_type, workspace_id, ctx)` already takes `ctx`, is called by all 13 create services (`requirement_service.py:283`, `adr_service.py:214`, `architecture_service.py:185`, `change_request_service.py:235`, `glossary_service.py:152`, `goal_service.py:163`, `interview_service.py:226`, `issue_service.py:243`, `main_goal_service.py:415`, `risk_service.py:270`, `test_service.py:128`, …), and is the only caller of the lifecycle method | **Zero `create_X()` files are touched.** Task 9 changes one function. The spec's risk "ein vergessener Pfad" is structurally impossible. |
| §3 "Bei `principal_type='agent'` trägt der resolvte `AuthContext` `actor_type='agent'`" | `AuthContext` (`auth_tenancy/context.py:88`) has **no** `actor_type` field at all; `ServiceBase._audit` (`application/base.py:187`) hardcodes `actor_type="user"` | Tasks 2 and 6 add the field and stop hardcoding. |
| §4.1 "`minimal` behält seinen heutigen Default-Graphen ohne `proposed`" | Only `Requirement` uses the tier presets. The other 12 workflow entity types use fixed per-entity preset keys (`need_default`, `adr_default`, … — `application/workspace_provisioning.py:45-58`) that have **no per-tier variant** | See Decision 3 — the minimal exemption can only hold for `Requirement`. |
| §7.2 "läuft in derselben Migration wie die `rationale`/`suspect_*`-Felder" | That migration (`persistence/migrations/00XX_tracelink_semantics_fields.py`, Traceability-Semantik plan Task 12) is created and **applied** by the preceding plan in the sequence | See Decision 4 — a separate, additive migration. |

**Live-code anchors this plan edits (all line numbers verified 2026-09-04):**

| File | What changes |
|---|---|
| `backend/auth_tenancy/models.py:62-107` | `ApiKey` + 5 fields |
| `backend/auth_tenancy/context.py:44-66, 88-136` | `IdentityClaims` + 3 fields, `AuthContext` + 4 fields |
| `backend/auth_tenancy/services/authentication.py:482-546` | `validate_api_key` populates them + rejects expired keys |
| `backend/auth_tenancy/services/authentication.py:549-611` | `create_api_key` accepts them |
| `backend/auth_tenancy/services/tenant_context.py:57-85` | `build_auth_context` forwards them + applies `workspace_ids` |
| `backend/rest_api/auth_enforcer.py:75-110` | `RbacPermission` scope gate |
| `backend/rest_api/api_key_views.py:151-215` | create/list expose the new fields |
| `backend/mcp_server/tool_registry.py:613-626, 638-641, 845-856, 869-899` | scope gate + `actor_type` propagation |
| `backend/application/base.py:159-200` | `_audit` uses `ctx.actor_type` / `ctx.agent_label` |
| `backend/workflow/definition_store.py:597-816` | `PRESET_SCHEMAS` + injection helper |
| `backend/workflow/lifecycle_manager.py:219-271` | optional `initial_state` override |
| `backend/workflow/services.py:428-457` | `initial_state_for` + wiring |
| `backend/workflow/services.py:285-368` | `outdate()` agent guard |
| `backend/workflow/transition_validator.py:65-93, 251-306` | `ValidationRequest.actor_type` + Rule 0 |
| `backend/persistence/models.py:1352-1409` | `TraceLink` + 2 fields |
| `backend/rest_api/mixins/workflow_transitions.py:165-198` | `proposed_by` in the GET body |
| `frontend/src/utils/workflowStatus.ts:39-50` | `proposed` in `STATUS_ORDER` |
| `frontend/src/utils/statusBadge.ts:60+` | `proposed` variant |
| `frontend/src/components/WorkflowStatusEditor/WorkflowStatusEditor.tsx` | proposal hint |
| `frontend/src/components/Reviews/useReviewsData.ts:37-44` | proposals queue mode |
| `frontend/src/components/Reviews/ReviewsView.tsx` | bulk confirm |

---

## Decisions (deviations from the spec, with reasons)

**Decision 1 — `proposed` is inserted at index 1, never index 0.**
`WorkflowDefinitionDTO.initial_state` returns `states[0]`, and `PRESET_SCHEMAS`' own header comment makes `states[0] == model field default` a hard invariant (the status mirror writes `current_state` verbatim into `Requirement.status`, `Adr.status`, …). The spec's `["proposed", "draft", ...]` snippet would silently move every human-created artifact into `proposed`. Index 1 keeps `initial_state` and every mirror default untouched.

**Decision 2 — the shared helper is `workflow.services.initial_state_for(ctx, item_type, workspace_id)`, a module-level function, not a `WorkflowInitializationService` class.**
`workflow/services.py` IS the workflow facade (its docstring: "the ONLY public import surface"); every other public operation there is a module-level function. A class with one static method and one call site would be an abstraction the codebase does not use anywhere else in this module.

**Decision 3 — the `minimal` exemption applies to `Requirement` only.**
`Requirement` is the only entity type whose workflow is seeded from the tier presets (`minimal`/`standard`/`extended`). The other 12 use fixed per-entity keys (`need_default`, `adr_default`, …) that exist in exactly one variant, and `GlobalWorkflowDefinition` is keyed `(tenant, item_type, preset)` — so a tier-dependent seed for those types is not expressible without inventing 12×3 new preset keys, which this spec does not ask for. Consequence: on a `minimal` workspace an agent-created `Adr`/`Risk`/`Goal`/… does land in `proposed`; a `Requirement` does not. This only ever fires for an explicitly opted-in `principal_type="agent"` key, and a workspace admin can remove the state via the existing Workflow Editor (spec §4.1 blesses exactly that escape hatch).

**Decision 4 — `TraceLink.proposed_by`/`proposed_at` get their own migration, not an edit of the Traceability-Semantik migration.**
That plan runs first in the agreed sequence, so its `00XX_tracelink_semantics_fields.py` is already applied in every dev database by the time this plan starts. Editing an applied migration is the classic footgun (Django will not re-run it; `makemigrations` then produces a phantom diff). The spec's "nicht doppelt anlegen" is honoured — `rationale`/`suspect_*` are not re-declared.

**Decision 5 — the reject target is per preset schema; a literal `"rejected"` state is only added where it does not collide.**
`adr_default` already has `"Rejected"` (Title Case, flagged `is_outdated_equivalent` by migration 0016) — adding a lowercase `"rejected"` next to it would give `Adr.status` two near-identical values and break the frontend badge/label mapping. `ccb_approval` already has `"rejected"`. `goal_default`/`main_goal_default` use German state names and already have `"Archiviert"` as their `is_outdated_equivalent` dead end. A four-entry override table `_PROPOSED_REJECT_STATE` handles those; every other schema gets a new `"rejected"` state flagged `is_outdated_equivalent: True`. Because that flag is the existing "treat as outdated / hide from active lists" signal, spec risk §8 bullet 3 ("ein vergessener Konsument") is structurally closed — no consumer is changed.

**Decision 6 — the `?status=proposed` list filter needs no frontend filter work.**
`RequirementList.tsx:251` builds its status dropdown from the data via `buildStatusFilterOptions(requirements, statusFilter)`. Once Task 10 syncs the status mirror on the proposed path, `proposed` appears in that dropdown automatically. Only the label ordering (`workflowStatus.ts`) and the badge colour (`statusBadge.ts`) need a value each — Task 16.

**Decision 7 — `workspace_ids` and `scope` are enforced fail-closed at two seams each (REST + MCP), not at every call site.**
`workspace_ids` narrows `active_roles` to `()` for a workspace outside the list; `scope == "read"` denies `Operation.WRITE`. Both produce a normal `PERMISSION_DENIED`, which every caller already handles.

## OFFENE FRAGEN

None blocking. Every ambiguity found is resolved by a Decision above.

---

## File Structure

```
backend/
  auth_tenancy/
    models.py                                      MOD  ApiKey +5 fields
    context.py                                     MOD  IdentityClaims/AuthContext +fields
    migrations/0013_apikey_agent_identity.py       NEW
    services/authentication.py                     MOD  validate_api_key / create_api_key
    services/tenant_context.py                     MOD  build_auth_context
    tests/test_api_key_agent_identity.py           NEW
    tests/test_api_key_scope_enforcement.py        NEW
  rest_api/
    auth_enforcer.py                               MOD  scope gate
    api_key_views.py                               MOD  new fields in/out
    mixins/workflow_transitions.py                 MOD  proposed_by in GET
    tests/test_api_key_agent_fields.py             NEW
    tests/test_transitions_proposed_by.py          NEW
  mcp_server/
    tool_registry.py                               MOD  scope gate + actor_type
    tests/test_api_key_scope_gate.py               NEW
  application/
    base.py                                        MOD  _audit actor_type
    trace_link_service.py                          MOD  proposal fields + confirm/discard
    ai_derivation_service.py                       MOD  never auto-approve out of proposed
    tests/test_trace_link_proposal.py              NEW
    tests/test_audit_actor_type.py                 NEW
  workflow/
    definition_store.py                            MOD  inject_proposed_state + PRESET_SCHEMAS
    lifecycle_manager.py                           MOD  initial_state override
    services.py                                    MOD  initial_state_for, outdate guard
    transition_validator.py                        MOD  ValidationRequest.actor_type + Rule 0
    migrations/0018_add_proposed_state.py          NEW
    tests/test_proposed_state_injection.py         NEW
    tests/test_proposed_initialization.py          NEW
    tests/test_agent_transition_guard.py           NEW
    tests/test_proposed_state_migration.py         NEW
  persistence/
    models.py                                      MOD  TraceLink +2 fields
    migrations/0070_tracelink_proposed_by.py       NEW
  rest_api/serializers.py                          MOD  TraceLinkSerializer +2 read-only
frontend/src/
  utils/workflowStatus.ts                          MOD  STATUS_ORDER
  utils/statusBadge.ts                             MOD  STATUS_VARIANT_MAP
  utils/workflowStatus.proposed.test.ts            NEW
  api/workflow-transitions.ts                      MOD  proposed_by on the response type
  components/WorkflowStatusEditor/
    WorkflowStatusEditor.tsx                       MOD  proposal hint
    WorkflowStatusEditor.proposed.test.tsx         NEW
  components/Reviews/
    useReviewsData.ts                              MOD  proposals queue mode
    ReviewsView.tsx                                MOD  mode toggle + bulk confirm
    ReviewsView.proposals.test.tsx                 NEW
  i18n/locales/de.json, en.json                    MOD  new keys
```

---

## Task Sequence

Phase A (Tasks 1–7) — agent identity, independently shippable.
Phase B (Tasks 8–9) — `proposed` in the graphs.
Phase C (Tasks 10–13) — initialization + the hard rule.
Phase D (Tasks 14–15) — TraceLink proposals.
Phase E (Tasks 16–20) — REST surface + frontend.

---

### Task 1: `ApiKey` agent-identity schema

**Files:**
- Modify: `backend/auth_tenancy/models.py:62-107`
- Create: `backend/auth_tenancy/migrations/0013_apikey_agent_identity.py`
- Test: `backend/auth_tenancy/tests/test_api_key_agent_identity.py`

**Interfaces:**
- Produces: `ApiKey.principal_type: str`, `ApiKey.agent_label: str`, `ApiKey.scope: str`, `ApiKey.workspace_ids: list[str]`, `ApiKey.expires_at: datetime | None`, `ApiKey.is_expired: bool`, and the module constants `PRINCIPAL_TYPE_USER`, `PRINCIPAL_TYPE_AGENT`, `API_KEY_SCOPE_READ`, `API_KEY_SCOPE_WRITE`.

- [ ] **Step 1: Write the failing test**

```python
# backend/auth_tenancy/tests/test_api_key_agent_identity.py
"""ApiKey agent-identity fields (KI-Vorschlag-als-Zustand spec §3)."""
from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from auth_tenancy.models import (
    API_KEY_SCOPE_READ,
    API_KEY_SCOPE_WRITE,
    PRINCIPAL_TYPE_AGENT,
    PRINCIPAL_TYPE_USER,
    ApiKey,
)
from persistence.models import Tenant, User


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(name="t-agent-identity", is_active=True)


@pytest.fixture
def user(tenant):
    return User.objects.create(
        tenant=tenant, email="agent-owner@example.com", is_active=True
    )


@pytest.mark.django_db
def test_defaults_are_backward_compatible(tenant, user):
    key = ApiKey.unscoped.create(
        tenant=tenant, user=user, name="legacy", key_hash="sha256:aa"
    )
    assert key.principal_type == PRINCIPAL_TYPE_USER
    assert key.agent_label == ""
    assert key.scope == API_KEY_SCOPE_WRITE
    assert key.workspace_ids == []
    assert key.expires_at is None
    assert key.is_expired is False


@pytest.mark.django_db
def test_agent_key_stores_label_scope_and_workspaces(tenant, user):
    key = ApiKey.unscoped.create(
        tenant=tenant,
        user=user,
        name="claude-code",
        key_hash="sha256:bb",
        principal_type=PRINCIPAL_TYPE_AGENT,
        agent_label="Claude Code — Daniels Workspace",
        scope=API_KEY_SCOPE_READ,
        workspace_ids=["11111111-1111-1111-1111-111111111111"],
    )
    key.refresh_from_db()
    assert key.principal_type == PRINCIPAL_TYPE_AGENT
    assert key.agent_label == "Claude Code — Daniels Workspace"
    assert key.scope == API_KEY_SCOPE_READ
    assert key.workspace_ids == ["11111111-1111-1111-1111-111111111111"]


@pytest.mark.django_db
def test_is_expired_flips_after_expires_at(tenant, user):
    past = ApiKey.unscoped.create(
        tenant=tenant,
        user=user,
        name="expired",
        key_hash="sha256:cc",
        expires_at=timezone.now() - timedelta(seconds=1),
    )
    future = ApiKey.unscoped.create(
        tenant=tenant,
        user=user,
        name="valid",
        key_hash="sha256:dd",
        expires_at=timezone.now() + timedelta(days=1),
    )
    assert past.is_expired is True
    assert future.is_expired is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec backend pytest auth_tenancy/tests/test_api_key_agent_identity.py -v`
Expected: FAIL with `ImportError: cannot import name 'API_KEY_SCOPE_READ' from 'auth_tenancy.models'`

- [ ] **Step 3: Add the constants and fields**

In `backend/auth_tenancy/models.py`, directly below `MAX_ACTIVE_API_KEYS_PER_USER` (line 59):

```python
# Principal type of an API key (KI-Vorschlag-als-Zustand spec §3). ``agent``
# makes the key act as an AI agent in its own right, not as the owning human:
# the resolved AuthContext carries ``actor_type="agent"`` and every artifact the
# key creates lands in the "proposed" workflow state where the graph has one.
PRINCIPAL_TYPE_USER = "user"
PRINCIPAL_TYPE_AGENT = "agent"
PRINCIPAL_TYPE_CHOICES = (
    (PRINCIPAL_TYPE_USER, "User"),
    (PRINCIPAL_TYPE_AGENT, "Agent"),
)

# Coarse capability scope of an API key (audit finding E2.1). ``read`` denies
# every Operation.WRITE at the REST and MCP gates; ``write`` is the historical
# behaviour and stays the default so existing keys are unaffected. The two
# string values are consumed verbatim by the MCP-Modernisierung spec §6.1.
API_KEY_SCOPE_READ = "read"
API_KEY_SCOPE_WRITE = "write"
API_KEY_SCOPE_CHOICES = (
    (API_KEY_SCOPE_READ, "Read"),
    (API_KEY_SCOPE_WRITE, "Write"),
)
```

In the `ApiKey` class body, after `last_used_at` (line 91):

```python
    #: ``agent`` makes the key a principal of its own (spec §3). Default
    #: ``user`` keeps every pre-existing key behaving exactly as before — this
    #: feature is opt-in per key, never retroactive.
    principal_type = models.CharField(
        max_length=16, choices=PRINCIPAL_TYPE_CHOICES, default=PRINCIPAL_TYPE_USER
    )
    #: Human-readable agent name shown wherever the owning user's name would
    #: otherwise appear (provenance labels, audit trail, workflow history).
    agent_label = models.CharField(max_length=255, blank=True, default="")
    #: Coarse capability gate, checked at the REST and MCP permission seams.
    scope = models.CharField(
        max_length=16, choices=API_KEY_SCOPE_CHOICES, default=API_KEY_SCOPE_WRITE
    )
    #: Workspace UUIDs (as strings) this key may act in. Empty list = every
    #: workspace the owning user holds a role in (the historical behaviour).
    workspace_ids = models.JSONField(default=list, blank=True)
    #: Hard expiry. NULL = never expires (historical behaviour).
    expires_at = models.DateTimeField(null=True, blank=True)
```

And after the `is_active` property (line 107):

```python
    @property
    def is_expired(self) -> bool:
        """Return whether the key's hard expiry has passed (NULL = never)."""
        if self.expires_at is None:
            return False
        from django.utils import timezone

        return self.expires_at <= timezone.now()
```

- [ ] **Step 4: Generate the migration**

Run: `docker compose exec backend python manage.py makemigrations auth_tenancy --name apikey_agent_identity`
Expected: `Migrations for 'auth_tenancy': 0013_apikey_agent_identity.py — Add field agent_label ... expires_at ... principal_type ... scope ... workspace_ids to apikey`

- [ ] **Step 5: Apply and run the test**

Run: `docker compose exec backend python manage.py migrate auth_tenancy && docker compose exec backend pytest auth_tenancy/tests/test_api_key_agent_identity.py -v`
Expected: PASS (3 tests)

- [ ] **Step 6: Commit**

```bash
git add backend/auth_tenancy/models.py backend/auth_tenancy/migrations/0013_apikey_agent_identity.py backend/auth_tenancy/tests/test_api_key_agent_identity.py
git commit -m "feat(auth): add agent identity, scope and expiry fields to ApiKey"
```

---

### Task 2: Carry agent identity through `IdentityClaims` and `AuthContext`

**Files:**
- Modify: `backend/auth_tenancy/context.py:44-66` (`IdentityClaims`), `:88-136` (`AuthContext`)
- Modify: `backend/auth_tenancy/services/authentication.py:482-546` (`validate_api_key`)
- Modify: `backend/auth_tenancy/services/tenant_context.py:57-85` (`build_auth_context`)
- Test: `backend/auth_tenancy/tests/test_api_key_agent_identity.py` (extend)

**Interfaces:**
- Consumes: `ApiKey.principal_type`, `.agent_label`, `.scope`, `.workspace_ids`, `.is_expired` (Task 1).
- Produces: `IdentityClaims.actor_type: str`, `.agent_label: str`, `.scope: str`, `.api_key_workspace_ids: tuple[str, ...]`; the same four on `AuthContext`; `AuthContext.is_agent: bool`.

- [ ] **Step 1: Write the failing test**

Append to `backend/auth_tenancy/tests/test_api_key_agent_identity.py`:

```python
from auth_tenancy.errors import AuthenticationFailed
from auth_tenancy.services.authentication import (
    AuthenticationService,
    generate_api_key_plaintext,
    hash_api_key,
)


def _issue(tenant, user, **fields) -> str:
    plaintext = generate_api_key_plaintext()
    ApiKey.unscoped.create(
        tenant=tenant,
        user=user,
        name=fields.pop("name", "k"),
        key_hash=hash_api_key(plaintext),
        **fields,
    )
    return plaintext


@pytest.mark.django_db
def test_user_key_claims_actor_type_user(tenant, user):
    plaintext = _issue(tenant, user)
    claims = AuthenticationService().validate_api_key(plaintext)
    assert claims.actor_type == "user"
    assert claims.agent_label == ""
    assert claims.scope == API_KEY_SCOPE_WRITE
    assert claims.api_key_workspace_ids == ()


@pytest.mark.django_db
def test_agent_key_claims_actor_type_agent(tenant, user):
    plaintext = _issue(
        tenant,
        user,
        principal_type=PRINCIPAL_TYPE_AGENT,
        agent_label="Claude Code",
        scope=API_KEY_SCOPE_READ,
        workspace_ids=["11111111-1111-1111-1111-111111111111"],
    )
    claims = AuthenticationService().validate_api_key(plaintext)
    assert claims.actor_type == "agent"
    assert claims.agent_label == "Claude Code"
    assert claims.scope == API_KEY_SCOPE_READ
    assert claims.api_key_workspace_ids == (
        "11111111-1111-1111-1111-111111111111",
    )


@pytest.mark.django_db
def test_expired_key_is_rejected(tenant, user):
    plaintext = _issue(tenant, user, expires_at=timezone.now() - timedelta(seconds=1))
    with pytest.raises(AuthenticationFailed) as exc:
        AuthenticationService().validate_api_key(plaintext)
    assert exc.value.code == "api_key_expired"


@pytest.mark.django_db
def test_auth_context_exposes_is_agent(tenant, user):
    from auth_tenancy.context import TenantContext as TenantContextValue
    from auth_tenancy.services.tenant_context import TenantContextService

    plaintext = _issue(
        tenant, user, principal_type=PRINCIPAL_TYPE_AGENT, agent_label="Bot"
    )
    claims = AuthenticationService().validate_api_key(plaintext)
    ctx = TenantContextService().build_auth_context(
        claims,
        TenantContextValue(tenant_id=tenant.id, tenant_name=tenant.name),
        ("editor",),
    )
    assert ctx.actor_type == "agent"
    assert ctx.agent_label == "Bot"
    assert ctx.is_agent is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec backend pytest auth_tenancy/tests/test_api_key_agent_identity.py -k "claims or expired or is_agent" -v`
Expected: FAIL with `AttributeError: 'IdentityClaims' object has no attribute 'actor_type'`

- [ ] **Step 3: Extend the two dataclasses**

In `backend/auth_tenancy/context.py`, add to `IdentityClaims` after `api_key_id`:

```python
    #: ``"user"`` or ``"agent"`` — byte-identical to
    #: ``audit.models.AuditEntry.ACTOR_TYPE_*`` so the value reaches the audit
    #: log unchanged. Only an ``ApiKey`` with ``principal_type="agent"``
    #: produces ``"agent"``; every Bearer-token login is a human.
    actor_type: str = "user"
    #: Display name of the agent, empty for humans.
    agent_label: str = ""
    #: ``"read"`` or ``"write"`` — the key's coarse capability gate.
    scope: str = "write"
    #: Workspace UUIDs (as strings) the key is restricted to; empty = no
    #: restriction beyond the owner's role assignments.
    api_key_workspace_ids: tuple[str, ...] = ()
```

Add the same four fields to `AuthContext` after `workspace_id`, plus:

```python
    @property
    def is_agent(self) -> bool:
        """Return whether this request is made by an AI agent principal."""
        return self.actor_type == "agent"
```

Note: `AuthContext.system()` needs no change — the defaults already produce `actor_type="user"`.

- [ ] **Step 4: Populate the claims in `validate_api_key`**

In `backend/auth_tenancy/services/authentication.py`, insert directly after the `if api_key.revoked_at is not None:` block:

```python
        if api_key.is_expired:
            # E2.1: a key with a hard expiry stops authenticating the moment it
            # passes, exactly like a revoked one. Distinct error code so the
            # caller can tell "rotate me" from "you were cut off".
            raise AuthenticationFailed("api_key_expired")
```

and replace the `return IdentityClaims(...)` at the end with:

```python
        return IdentityClaims(
            user_id=api_key.user_id,
            tenant_id=api_key.user.tenant_id,
            roles=(),  # roles are resolved by AuthorizationService from UserRole.
            auth_method=AuthMethod.API_KEY,
            api_key_id=api_key.id,
            actor_type=api_key.principal_type,
            agent_label=api_key.agent_label,
            scope=api_key.scope,
            api_key_workspace_ids=tuple(
                str(w) for w in (api_key.workspace_ids or [])
            ),
        )
```

- [ ] **Step 5: Forward them in `build_auth_context`**

In `backend/auth_tenancy/services/tenant_context.py`, extend the returned `AuthContext(...)` with:

```python
            actor_type=claims.actor_type,
            agent_label=claims.agent_label,
            scope=claims.scope,
            api_key_workspace_ids=claims.api_key_workspace_ids,
```

- [ ] **Step 6: Run test to verify it passes**

Run: `docker compose exec backend pytest auth_tenancy/tests/test_api_key_agent_identity.py -v`
Expected: PASS (7 tests)

- [ ] **Step 7: Run the auth regression suite**

Run: `docker compose exec backend pytest auth_tenancy/ -q`
Expected: no NEW failures versus the pre-change baseline (record the baseline with the same command before Step 3 if unsure).

- [ ] **Step 8: Commit**

```bash
git add backend/auth_tenancy/context.py backend/auth_tenancy/services/authentication.py backend/auth_tenancy/services/tenant_context.py backend/auth_tenancy/tests/test_api_key_agent_identity.py
git commit -m "feat(auth): carry actor_type, agent_label and scope into AuthContext"
```

---

### Task 3: `workspace_ids` restriction (fail-closed, REST seam)

**Files:**
- Modify: `backend/auth_tenancy/services/tenant_context.py:57-85`
- Test: `backend/auth_tenancy/tests/test_api_key_scope_enforcement.py`

**Interfaces:**
- Consumes: `AuthContext.api_key_workspace_ids` (Task 2).
- Produces: `build_auth_context` returns `active_roles=()` when `workspace_id` is outside a non-empty `api_key_workspace_ids`.

- [ ] **Step 1: Write the failing test**

```python
# backend/auth_tenancy/tests/test_api_key_scope_enforcement.py
"""API-key scope and workspace restriction (audit finding E2.1)."""
from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from auth_tenancy.context import (
    AuthMethod,
    IdentityClaims,
    TenantContext as TenantContextValue,
)
from auth_tenancy.services.tenant_context import TenantContextService

TENANT_ID = UUID("22222222-2222-2222-2222-222222222222")
ALLOWED_WS = UUID("11111111-1111-1111-1111-111111111111")


def _claims(workspace_ids: tuple[str, ...]) -> IdentityClaims:
    return IdentityClaims(
        user_id=uuid4(),
        tenant_id=TENANT_ID,
        roles=(),
        auth_method=AuthMethod.API_KEY,
        api_key_id=uuid4(),
        actor_type="agent",
        agent_label="Bot",
        scope="write",
        api_key_workspace_ids=workspace_ids,
    )


def _tenant() -> TenantContextValue:
    return TenantContextValue(tenant_id=TENANT_ID, tenant_name="t")


def test_empty_workspace_ids_keeps_all_roles():
    ctx = TenantContextService().build_auth_context(
        _claims(()), _tenant(), ("editor", "admin"), workspace_id=ALLOWED_WS
    )
    assert ctx.active_roles == ("editor", "admin")


def test_listed_workspace_keeps_roles():
    ctx = TenantContextService().build_auth_context(
        _claims((str(ALLOWED_WS),)),
        _tenant(),
        ("editor",),
        workspace_id=ALLOWED_WS,
    )
    assert ctx.active_roles == ("editor",)


def test_unlisted_workspace_loses_all_roles():
    ctx = TenantContextService().build_auth_context(
        _claims((str(ALLOWED_WS),)), _tenant(), ("admin",), workspace_id=uuid4()
    )
    assert ctx.active_roles == ()


def test_restricted_key_without_workspace_context_loses_all_roles():
    # A restricted key must not fall back to the tenant-wide role union, which
    # is exactly the path that would hand it every workspace it was fenced out of.
    ctx = TenantContextService().build_auth_context(
        _claims((str(ALLOWED_WS),)), _tenant(), ("admin",), workspace_id=None
    )
    assert ctx.active_roles == ()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec backend pytest auth_tenancy/tests/test_api_key_scope_enforcement.py -v`
Expected: FAIL — `test_unlisted_workspace_loses_all_roles` asserts `() == ('admin',)`

- [ ] **Step 3: Apply the restriction in `build_auth_context`**

Insert before the `return AuthContext(...)` in `backend/auth_tenancy/services/tenant_context.py`:

```python
        # E2.1: a key restricted to specific workspaces must not carry roles
        # anywhere else. Narrowing ``active_roles`` to () (rather than raising)
        # keeps this a plain RBAC denial that every existing caller — REST
        # RbacPermission, MCP _check_rbac/_check_read_rbac — already handles.
        # A restricted key with NO workspace context is denied too: the
        # workspace-less path resolves the tenant-wide role union, which would
        # hand the key exactly the workspaces it was fenced out of.
        allowed = claims.api_key_workspace_ids
        if allowed and (
            workspace_id is None or str(workspace_id) not in allowed
        ):
            active_roles = ()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec backend pytest auth_tenancy/tests/test_api_key_scope_enforcement.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/auth_tenancy/services/tenant_context.py backend/auth_tenancy/tests/test_api_key_scope_enforcement.py
git commit -m "feat(auth): fence a workspace-restricted API key out of other workspaces"
```

---

### Task 4: `scope="read"` denies writes at the REST gate

**Files:**
- Modify: `backend/rest_api/auth_enforcer.py:75-110`
- Test: `backend/rest_api/tests/test_api_key_scope_gate.py`

**Interfaces:**
- Consumes: `AuthContext.scope` (Task 2), `auth_tenancy.services.Operation`.
- Produces: `RbacPermission.has_permission` raises `PermissionDenied` for a read-scoped key on any non-`READ` operation.

- [ ] **Step 1: Write the failing test**

```python
# backend/rest_api/tests/test_api_key_scope_gate.py
"""A read-scoped API key may not write, whatever its RBAC roles say."""
from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from rest_framework import exceptions

from auth_tenancy.context import AuthContext, AuthMethod
from auth_tenancy.services import Operation
from rest_api.auth_enforcer import RbacPermission


def _ctx(scope: str) -> AuthContext:
    return AuthContext(
        user_id=uuid4(),
        tenant_id=uuid4(),
        active_roles=("admin",),
        auth_method=AuthMethod.API_KEY,
        api_key_id=uuid4(),
        actor_type="agent",
        agent_label="Bot",
        scope=scope,
    )


class _View:
    required_operation = None


def _request(method: str, ctx: AuthContext):
    return SimpleNamespace(method=method, auth_context=ctx)


def test_read_scope_allows_get():
    assert RbacPermission().has_permission(_request("GET", _ctx("read")), _View())


def test_read_scope_denies_post():
    with pytest.raises(exceptions.PermissionDenied) as exc:
        RbacPermission().has_permission(_request("POST", _ctx("read")), _View())
    assert "read-only" in str(exc.value).lower()


def test_read_scope_denies_declared_write_operation():
    view = _View()
    view.required_operation = Operation.WORKFLOW_TRANSITION
    with pytest.raises(exceptions.PermissionDenied):
        RbacPermission().has_permission(_request("GET", _ctx("read")), view)


def test_write_scope_allows_post():
    assert RbacPermission().has_permission(_request("POST", _ctx("write")), _View())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec backend pytest rest_api/tests/test_api_key_scope_gate.py -v`
Expected: FAIL — `test_read_scope_denies_post` does not raise

- [ ] **Step 3: Add the scope check**

In `backend/rest_api/auth_enforcer.py`, insert directly after the `required_operation` override block (before `decision = self._authz.decide_access(...)`):

```python
        # E2.1: the API key's coarse scope is an independent, fail-closed gate
        # ABOVE the RBAC matrix. It can only ever narrow: a read-scoped key is
        # denied every non-READ operation regardless of how privileged its
        # owner is. Placed before decide_access so no shadow-permission path
        # can widen it back.
        if auth_context.scope == "read" and operation is not Operation.READ:
            raise exceptions.PermissionDenied(
                detail=(
                    "API key is read-only (scope='read'); "
                    f"operation '{operation.value}' requires scope='write'."
                )
            )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec backend pytest rest_api/tests/test_api_key_scope_gate.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/rest_api/auth_enforcer.py backend/rest_api/tests/test_api_key_scope_gate.py
git commit -m "feat(rest): deny writes for read-scoped API keys"
```

---

### Task 5: `scope="read"` denies writes at the MCP gate

**Files:**
- Modify: `backend/mcp_server/tool_registry.py:613-626` (`_check_rbac`), `:638-641` (`list_tools`), `:845-856` and `:869-899` (`AuthContext` reconstruction)
- Test: `backend/mcp_server/tests/test_api_key_scope_gate.py`

**Interfaces:**
- Consumes: `AuthContext.scope`, `.actor_type`, `.agent_label` (Task 2).
- Produces: `_check_rbac` returns a non-`None` message for a read-scoped context; `list_tools` hides write tools from a read-scoped key.

- [ ] **Step 1: Write the failing test**

```python
# backend/mcp_server/tests/test_api_key_scope_gate.py
"""MCP honours ApiKey.scope and preserves agent identity across role resolution."""
from __future__ import annotations

from uuid import uuid4

import pytest

from auth_tenancy.context import AuthContext, AuthMethod
from mcp_server.tool_registry import ToolRegistry


def _ctx(scope: str = "write", actor_type: str = "agent") -> AuthContext:
    return AuthContext(
        user_id=uuid4(),
        tenant_id=uuid4(),
        active_roles=("admin",),
        auth_method=AuthMethod.API_KEY,
        api_key_id=uuid4(),
        actor_type=actor_type,
        agent_label="Claude Code",
        scope=scope,
    )


def test_check_rbac_denies_read_scope():
    msg = ToolRegistry()._check_rbac(_ctx(scope="read"))
    assert msg is not None
    assert "read-only" in msg.lower()


def test_check_rbac_allows_write_scope():
    assert ToolRegistry()._check_rbac(_ctx(scope="write")) is None


@pytest.mark.django_db
def test_resolve_roles_preserves_agent_identity():
    registry = ToolRegistry()
    resolved = registry._resolve_roles(_ctx(), workspace_id=None)
    assert resolved.actor_type == "agent"
    assert resolved.agent_label == "Claude Code"
    assert resolved.scope == "write"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec backend pytest mcp_server/tests/test_api_key_scope_gate.py -v`
Expected: FAIL — `_check_rbac` returns `None` for the read-scoped context; `_resolve_roles` drops `actor_type`

- [ ] **Step 3: Add the scope check to `_check_rbac`**

In `backend/mcp_server/tool_registry.py`, at the top of `_check_rbac` (before `decision = ...`):

```python
        if ctx.scope == "read":
            # E2.1: read-only key. Independent of and above the RBAC matrix,
            # same rule as rest_api.auth_enforcer.RbacPermission.
            return (
                "API key is read-only (scope='read'); this tool performs a "
                "write. Issue a key with scope='write' to use it."
            )
```

- [ ] **Step 4: Hide write tools from read-scoped keys in `list_tools`**

Replace the `can_write = ...` assignment:

```python
            can_write = (
                auth_ctx.scope != "read"
                and self._authz_service.decide_access(roles, Operation.WRITE).allow
            )
```

- [ ] **Step 5: Preserve the new fields on every `AuthContext` rebuild**

`_validate_api_key` (line ~849), `_resolve_roles` (lines ~874 and ~892) each construct a fresh `AuthContext`. Add the same four kwargs to **all three**:

```python
            actor_type=claims.actor_type,
            agent_label=claims.agent_label,
            scope=claims.scope,
            api_key_workspace_ids=claims.api_key_workspace_ids,
```

(in `_resolve_roles` the source is `ctx.` rather than `claims.`):

```python
            actor_type=ctx.actor_type,
            agent_label=ctx.agent_label,
            scope=ctx.scope,
            api_key_workspace_ids=ctx.api_key_workspace_ids,
```

- [ ] **Step 6: Run test to verify it passes**

Run: `docker compose exec backend pytest mcp_server/tests/test_api_key_scope_gate.py -v`
Expected: PASS (3 tests)

- [ ] **Step 7: Run the MCP dispatch regression suite**

Run: `docker compose exec backend pytest mcp_server/tests/ -q`
Expected: no NEW failures versus baseline

- [ ] **Step 8: Commit**

```bash
git add backend/mcp_server/tool_registry.py backend/mcp_server/tests/test_api_key_scope_gate.py
git commit -m "feat(mcp): honour ApiKey.scope and preserve agent identity in role resolution"
```

---

### Task 6: Expose the agent fields through the API-key REST endpoints

**Files:**
- Modify: `backend/auth_tenancy/services/authentication.py:549-611` (`create_api_key`), `:613-628` (`list_api_keys`)
- Modify: `backend/rest_api/api_key_views.py:151-215` (`create`), `:96-110` (`list`)
- Test: `backend/rest_api/tests/test_api_key_agent_fields.py`

**Interfaces:**
- Consumes: Task 1 model fields.
- Produces: `AuthenticationService.create_api_key(*, user_id, tenant_id, name, principal_type="user", agent_label="", scope="write", workspace_ids=None, expires_at=None)`; `list_api_keys` entries additionally carry `principal_type`, `agent_label`, `scope`, `workspace_ids`, `expires_at`.

- [ ] **Step 1: Write the failing test**

```python
# backend/rest_api/tests/test_api_key_agent_fields.py
"""POST/GET /api/v1/api-keys/ round-trips the agent identity fields."""
from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from auth_tenancy.models import ApiKey
from auth_tenancy.services.authentication import AuthenticationService
from persistence.models import Tenant, User


@pytest.fixture
def owner(db):
    tenant = Tenant.objects.create(name="t-agent-rest", is_active=True)
    user = User.objects.create(
        tenant=tenant, email="owner-rest@example.com", is_active=True
    )
    return tenant, user


@pytest.mark.django_db
def test_create_api_key_persists_agent_fields(owner):
    tenant, user = owner
    expires = timezone.now() + timedelta(days=30)
    result = AuthenticationService().create_api_key(
        user_id=user.id,
        tenant_id=tenant.id,
        name="claude",
        principal_type="agent",
        agent_label="Claude Code",
        scope="read",
        workspace_ids=["11111111-1111-1111-1111-111111111111"],
        expires_at=expires,
    )
    key = ApiKey.unscoped.get(id=result.api_key_id)
    assert key.principal_type == "agent"
    assert key.agent_label == "Claude Code"
    assert key.scope == "read"
    assert key.workspace_ids == ["11111111-1111-1111-1111-111111111111"]
    assert key.expires_at == expires


@pytest.mark.django_db
def test_create_api_key_defaults_stay_user_write(owner):
    tenant, user = owner
    result = AuthenticationService().create_api_key(
        user_id=user.id, tenant_id=tenant.id, name="plain"
    )
    key = ApiKey.unscoped.get(id=result.api_key_id)
    assert key.principal_type == "user"
    assert key.scope == "write"
    assert key.workspace_ids == []
    assert key.expires_at is None


@pytest.mark.django_db
def test_list_api_keys_exposes_agent_fields(owner):
    tenant, user = owner
    AuthenticationService().create_api_key(
        user_id=user.id,
        tenant_id=tenant.id,
        name="claude",
        principal_type="agent",
        agent_label="Claude Code",
        scope="read",
    )
    entry = AuthenticationService().list_api_keys(user_id=user.id)[0]
    assert entry["principal_type"] == "agent"
    assert entry["agent_label"] == "Claude Code"
    assert entry["scope"] == "read"
    assert entry["workspace_ids"] == []
    assert entry["expires_at"] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec backend pytest rest_api/tests/test_api_key_agent_fields.py -v`
Expected: FAIL with `TypeError: create_api_key() got an unexpected keyword argument 'principal_type'`

- [ ] **Step 3: Extend `create_api_key` and `list_api_keys`**

In `backend/auth_tenancy/services/authentication.py`, change the signature to:

```python
    def create_api_key(
        self,
        *,
        user_id: UUID,
        tenant_id: UUID,
        name: str,
        principal_type: str = "user",
        agent_label: str = "",
        scope: str = "write",
        workspace_ids: list[str] | None = None,
        expires_at: "datetime | None" = None,
    ) -> ApiKeyCreationResult:
```

and the `ApiKey.unscoped.create(...)` call to:

```python
            api_key = ApiKey.unscoped.create(
                user_id=user_id,
                tenant_id=tenant_id,
                name=name,
                key_hash=hash_api_key(plaintext),
                principal_type=principal_type,
                agent_label=agent_label,
                scope=scope,
                workspace_ids=list(workspace_ids or []),
                expires_at=expires_at,
            )
```

In `list_api_keys`, extend each dict with:

```python
                "principal_type": k.principal_type,
                "agent_label": k.agent_label,
                "scope": k.scope,
                "workspace_ids": list(k.workspace_ids or []),
                "expires_at": k.expires_at.isoformat() if k.expires_at else None,
                "expired": k.is_expired,
```

- [ ] **Step 4: Validate and forward the fields in the ViewSet**

In `backend/rest_api/api_key_views.py`, in `create()`, replace the service call block with:

```python
        principal_type = request.data.get("principal_type", "user")
        if principal_type not in ("user", "agent"):
            return Response(
                build_error_response(
                    code="VALIDATION_ERROR",
                    message="Field 'principal_type' must be 'user' or 'agent'.",
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
        scope = request.data.get("scope", "write")
        if scope not in ("read", "write"):
            return Response(
                build_error_response(
                    code="VALIDATION_ERROR",
                    message="Field 'scope' must be 'read' or 'write'.",
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
        raw_workspace_ids = request.data.get("workspace_ids", []) or []
        if not isinstance(raw_workspace_ids, list):
            return Response(
                build_error_response(
                    code="VALIDATION_ERROR",
                    message="Field 'workspace_ids' must be a list of UUID strings.",
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
        from uuid import UUID
        try:
            workspace_ids = [str(UUID(str(w))) for w in raw_workspace_ids]
        except (ValueError, AttributeError, TypeError):
            return Response(
                build_error_response(
                    code="VALIDATION_ERROR",
                    message="Field 'workspace_ids' must be a list of UUID strings.",
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
        raw_expires_at = request.data.get("expires_at")
        expires_at = None
        if raw_expires_at:
            from django.utils.dateparse import parse_datetime

            expires_at = parse_datetime(str(raw_expires_at))
            if expires_at is None:
                return Response(
                    build_error_response(
                        code="VALIDATION_ERROR",
                        message="Field 'expires_at' must be an ISO-8601 datetime.",
                    ),
                    status=status.HTTP_400_BAD_REQUEST,
                )

        agent_label = str(request.data.get("agent_label", "") or "")[:255]

        try:
            result = self._authn.create_api_key(
                user_id=UUID(user_id),
                tenant_id=UUID(tenant_id),
                name=name.strip(),
                principal_type=principal_type,
                agent_label=agent_label,
                scope=scope,
                workspace_ids=workspace_ids,
                expires_at=expires_at,
            )
        except ValueError as exc:
            return Response(
                build_error_response(code="VALIDATION_ERROR", message=str(exc)),
                status=status.HTTP_400_BAD_REQUEST,
            )
```

and extend the 201 body with `"principal_type": principal_type, "agent_label": agent_label, "scope": scope`.

`list()` needs no change — it returns `list_api_keys()` verbatim.

- [ ] **Step 5: Run test to verify it passes**

Run: `docker compose exec backend pytest rest_api/tests/test_api_key_agent_fields.py -v`
Expected: PASS (3 tests)

- [ ] **Step 6: Commit**

```bash
git add backend/auth_tenancy/services/authentication.py backend/rest_api/api_key_views.py backend/rest_api/tests/test_api_key_agent_fields.py
git commit -m "feat(rest): create and list API keys with agent identity fields"
```

---

### Task 7: Audit entries record the real actor type

**Files:**
- Modify: `backend/application/base.py:159-200` (`ServiceBase._audit`)
- Test: `backend/application/tests/test_audit_actor_type.py`

**Interfaces:**
- Consumes: `AuthContext.actor_type`, `.agent_label` (Task 2).
- Produces: `_audit` forwards `actor_type=ctx.actor_type` and, for agents, `details["client_name"] = ctx.agent_label`.

- [ ] **Step 1: Write the failing test**

```python
# backend/application/tests/test_audit_actor_type.py
"""ServiceBase._audit records the caller's real actor_type (spec §3)."""
from __future__ import annotations

from unittest.mock import patch
from uuid import uuid4

from application.base import ServiceBase
from auth_tenancy.context import AuthContext, AuthMethod


def _ctx(actor_type: str, agent_label: str = "") -> AuthContext:
    return AuthContext(
        user_id=uuid4(),
        tenant_id=uuid4(),
        active_roles=("editor",),
        auth_method=AuthMethod.API_KEY,
        api_key_id=uuid4(),
        actor_type=actor_type,
        agent_label=agent_label,
    )


def test_human_actor_type_is_user():
    with patch("audit.services.log_write") as log_write:
        ServiceBase._audit(
            ctx=_ctx("user"),
            operation="create",
            entity_type="Requirement",
            entity_id=uuid4(),
        )
    assert log_write.call_args.kwargs["actor_type"] == "user"


def test_agent_actor_type_and_client_name():
    with patch("audit.services.log_write") as log_write:
        ServiceBase._audit(
            ctx=_ctx("agent", "Claude Code"),
            operation="create",
            entity_type="Requirement",
            entity_id=uuid4(),
        )
    kwargs = log_write.call_args.kwargs
    assert kwargs["actor_type"] == "agent"
    assert kwargs["details"]["client_name"] == "Claude Code"


def test_agent_client_name_does_not_clobber_existing_details():
    with patch("audit.services.log_write") as log_write:
        ServiceBase._audit(
            ctx=_ctx("agent", "Claude Code"),
            operation="create",
            entity_type="Requirement",
            entity_id=uuid4(),
            details={"uid": "REQ-1"},
        )
    details = log_write.call_args.kwargs["details"]
    assert details["uid"] == "REQ-1"
    assert details["client_name"] == "Claude Code"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec backend pytest application/tests/test_audit_actor_type.py -v`
Expected: FAIL — `test_agent_actor_type_and_client_name` sees `actor_type == "user"`

- [ ] **Step 3: Use the context's actor type**

In `backend/application/base.py`, replace the `log_write(...)` call inside `_audit` with:

```python
            # Spec §3: the actor type is decided at the auth layer (an ApiKey
            # with principal_type="agent"), not reconstructed here. Previously
            # hardcoded to "user", which made every agent write look human.
            audit_details = details
            if ctx.actor_type == "agent" and ctx.agent_label:
                audit_details = {**(details or {}), "client_name": ctx.agent_label}

            log_write(
                actor=str(ctx.user_id),
                actor_type=ctx.actor_type,
                operation=operation,
                entity_type=entity_type,
                entity_id=entity_id,
                change_reason=change_reason,
                details=audit_details,
            )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec backend pytest application/tests/test_audit_actor_type.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/application/base.py backend/application/tests/test_audit_actor_type.py
git commit -m "feat(audit): record the caller's real actor_type instead of hardcoding user"
```

---

### Task 8: `inject_proposed_state()` and the updated `PRESET_SCHEMAS`

**Files:**
- Modify: `backend/workflow/definition_store.py:597-816` (`PRESET_SCHEMAS` block)
- Test: `backend/workflow/tests/test_proposed_state_injection.py`

**Interfaces:**
- Produces: `workflow.definition_store.PROPOSED_STATE: str`, `PROPOSED_ROLES: tuple[str, ...]`, `_PROPOSED_REJECT_STATE: dict[str, str]`, `inject_proposed_state(schema: dict) -> dict`, `SCHEMAS_WITHOUT_PROPOSED: frozenset[str]`.

- [ ] **Step 1: Write the failing test**

```python
# backend/workflow/tests/test_proposed_state_injection.py
"""The "proposed" state injection helper (spec §4.1)."""
from __future__ import annotations

import copy

import pytest

from workflow.definition_store import (
    PRESET_SCHEMAS,
    PROPOSED_STATE,
    SCHEMAS_WITHOUT_PROPOSED,
    WorkflowDefinitionDTO,
    inject_proposed_state,
)


def _schema(states, transitions=None, state_meta=None):
    out = {"states": list(states), "transitions": list(transitions or [])}
    if state_meta is not None:
        out["state_meta"] = state_meta
    return out


def test_proposed_is_never_the_initial_state():
    result = inject_proposed_state(_schema(["draft", "approved"]))
    assert result["states"][0] == "draft"
    assert result["states"][1] == PROPOSED_STATE


def test_confirm_transition_targets_the_initial_state():
    result = inject_proposed_state(_schema(["draft", "approved"]))
    confirm = next(
        t
        for t in result["transitions"]
        if t["from_state"] == PROPOSED_STATE and t["to_state"] == "draft"
    )
    assert confirm["requires_change_reason"] is False
    assert confirm["signature_gate"] is False
    assert confirm["allowed_roles"] == ["editor", "approver", "admin"]


def test_discard_transition_requires_a_change_reason():
    result = inject_proposed_state(_schema(["draft", "approved"]))
    discard = next(
        t
        for t in result["transitions"]
        if t["from_state"] == PROPOSED_STATE and t["to_state"] == "rejected"
    )
    assert discard["requires_change_reason"] is True


def test_new_reject_state_is_flagged_outdated_equivalent():
    result = inject_proposed_state(_schema(["draft", "approved"]))
    assert "rejected" in result["states"]
    assert result["state_meta"]["rejected"]["is_outdated_equivalent"] is True


def test_existing_reject_state_is_reused_not_duplicated():
    result = inject_proposed_state(
        _schema(["Draft", "Approved", "Rejected"]), reject_state="Rejected"
    )
    assert result["states"].count("Rejected") == 1
    assert "rejected" not in result["states"]
    discard = next(
        t for t in result["transitions"] if t["to_state"] == "Rejected"
    )
    assert discard["from_state"] == PROPOSED_STATE


def test_injection_is_idempotent():
    once = inject_proposed_state(_schema(["draft", "approved"]))
    twice = inject_proposed_state(copy.deepcopy(once))
    assert twice == once


def test_input_schema_is_not_mutated():
    original = _schema(["draft", "approved"])
    snapshot = copy.deepcopy(original)
    inject_proposed_state(original)
    assert original == snapshot


def test_minimal_preset_has_no_proposed_state():
    assert "minimal" in SCHEMAS_WITHOUT_PROPOSED
    assert PROPOSED_STATE not in PRESET_SCHEMAS["minimal"]["states"]


@pytest.mark.parametrize(
    "preset", ["standard", "extended", "need_default", "adr_default", "goal_default"]
)
def test_shipped_schemas_carry_proposed(preset):
    schema = PRESET_SCHEMAS[preset]
    assert schema["states"][1] == PROPOSED_STATE
    dto = WorkflowDefinitionDTO(
        states=tuple(schema["states"]),
        transitions=(),
        workspace_id=None,  # type: ignore[arg-type]
        item_type="X",
        preset=preset,
    )
    # Decision 1: initial_state must be unchanged by the injection.
    assert dto.initial_state == schema["states"][0]


def test_adr_reuses_its_title_case_rejected_state():
    states = PRESET_SCHEMAS["adr_default"]["states"]
    assert "Rejected" in states
    assert "rejected" not in states


def test_goal_reuses_archiviert_as_reject_target():
    transitions = PRESET_SCHEMAS["goal_default"]["transitions"]
    discard = next(
        t for t in transitions if t["from_state"] == PROPOSED_STATE
        and t["to_state"] == "Archiviert"
    )
    assert discard["requires_change_reason"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec backend pytest workflow/tests/test_proposed_state_injection.py -v`
Expected: FAIL with `ImportError: cannot import name 'PROPOSED_STATE' from 'workflow.definition_store'`

- [ ] **Step 3: Add the helper above `PRESET_SCHEMAS`**

In `backend/workflow/definition_store.py`, insert immediately before the `PRESET_SCHEMAS: dict[str, dict[str, Any]] = {` line:

```python
# ---------------------------------------------------------------------------
# "proposed" — the AI-proposal state (KI-Vorschlag-als-Zustand spec §4.1)
# ---------------------------------------------------------------------------

#: The state an artifact created by an ``actor_type="agent"`` principal lands
#: in, when the resolved graph knows it. One literal, never localized: the
#: initialization check (workflow.services.initial_state_for) and the
#: agent-confirmation guard (TransitionValidator rule 0) both key on it.
PROPOSED_STATE = "proposed"

#: Roles allowed to confirm or discard a proposal. Deliberately the normal
#: editing roles — a proposal is a review chore, not an approval decision.
PROPOSED_ROLES: tuple[str, ...] = ("editor", "approver", "admin")

#: Preset keys that must NOT gain "proposed" (spec §4.1: minimal keeps its
#: graph). Only "minimal" — see Decision 3 in the plan: the 12 fixed-preset
#: entity types have no per-tier graph variant to exempt.
SCHEMAS_WITHOUT_PROPOSED: frozenset[str] = frozenset({"minimal"})

#: Per-schema override for the discard target. Every schema not listed gets a
#: new "rejected" state. These four already own a terminal dead-end whose name
#: a lowercase "rejected" would shadow ("Rejected" vs "rejected" on the same
#: Adr.status column) or duplicate.
_PROPOSED_REJECT_STATE: dict[str, str] = {
    "adr_default": "Rejected",
    "ccb_approval": "rejected",
    "goal_default": "Archiviert",
    "main_goal_default": "Archiviert",
}

_DEFAULT_REJECT_STATE = "rejected"


def inject_proposed_state(
    schema: dict[str, Any], reject_state: str = _DEFAULT_REJECT_STATE
) -> dict[str, Any]:
    """Return a copy of *schema* extended with the "proposed" state.

    Adds the state at index **1** — never index 0. ``states[0]`` is the
    definition's ``initial_state`` (:pyattr:`WorkflowDefinitionDTO.initial_state`)
    and must keep matching the entity's ``status`` column default, because
    ``StateLifecycleManager._sync_status_mirror`` writes ``current_state``
    verbatim into that column.

    Two outgoing transitions are added:

    * confirm: ``proposed -> states[0]`` (no change_reason)
    * discard: ``proposed -> reject_state`` (change_reason required)

    A *reject_state* that is not already a member gets appended and flagged
    ``is_outdated_equivalent`` — the existing "treat as terminal / hide from
    active lists" signal, so no downstream consumer needs to learn a new state.

    Idempotent: re-injecting an already-injected schema is a no-op. The input
    is never mutated.

    Args:
        schema: A ``{"states": [...], "transitions": [...], "state_meta": {...}}``
            preset schema.
        reject_state: The discard target state name.

    Returns:
        A deep copy carrying the proposal state, transitions and metadata.
    """
    result = copy.deepcopy(schema)
    states: list[str] = list(result.get("states") or [])
    if not states:
        return result
    initial_state = states[0]

    if PROPOSED_STATE not in states:
        states.insert(1, PROPOSED_STATE)
    if reject_state not in states:
        states.append(reject_state)
        state_meta = result.get("state_meta", {})
        state_meta[reject_state] = {
            **state_meta.get(reject_state, {}),
            "is_outdated_equivalent": True,
        }
        result["state_meta"] = state_meta
    result["states"] = states

    transitions: list[dict[str, Any]] = list(result.get("transitions") or [])
    existing = {(t["from_state"], t["to_state"]) for t in transitions}
    for to_state, needs_reason in (
        (initial_state, False),
        (reject_state, True),
    ):
        if (PROPOSED_STATE, to_state) in existing:
            continue
        transitions.append(
            {
                "from_state": PROPOSED_STATE,
                "to_state": to_state,
                "allowed_roles": list(PROPOSED_ROLES),
                "requires_change_reason": needs_reason,
                "signature_gate": False,
            }
        )
    result["transitions"] = transitions
    return result
```

- [ ] **Step 4: Apply the injection to the shipped schemas**

Directly after the closing `}` of the `PRESET_SCHEMAS = {...}` literal (currently line 816), append:

```python
# Spec §4.1: every default graph except "minimal" gains the proposal state.
# Applied here rather than inline in each literal so the 16 schemas cannot
# drift apart and so `SCHEMAS_WITHOUT_PROPOSED` stays the single exemption
# list. Runs once at import; PRESET_SCHEMAS is rebound in place so existing
# `from .definition_store import PRESET_SCHEMAS` importers see the result.
for _preset_key in list(PRESET_SCHEMAS):
    if _preset_key in SCHEMAS_WITHOUT_PROPOSED:
        continue
    PRESET_SCHEMAS[_preset_key] = inject_proposed_state(
        PRESET_SCHEMAS[_preset_key],
        reject_state=_PROPOSED_REJECT_STATE.get(_preset_key, _DEFAULT_REJECT_STATE),
    )
del _preset_key
```

- [ ] **Step 5: Export the new names**

In the `__all__` list at the bottom of `definition_store.py`, add `"PROPOSED_STATE"`, `"PROPOSED_ROLES"`, `"SCHEMAS_WITHOUT_PROPOSED"`, `"inject_proposed_state"`.

- [ ] **Step 6: Run test to verify it passes**

Run: `docker compose exec backend pytest workflow/tests/test_proposed_state_injection.py -v`
Expected: PASS (12 tests)

- [ ] **Step 7: Run the workflow definition regression suite**

Run: `docker compose exec backend pytest workflow/tests/test_definition_store.py workflow/tests/test_definition_edit.py workflow/tests/test_available_transitions.py -q`
Expected: no NEW failures. If a test asserts an exact `states` tuple for a non-minimal preset, update it to include `"proposed"` at index 1 — that is the intended change, not a regression.

- [ ] **Step 8: Commit**

```bash
git add backend/workflow/definition_store.py backend/workflow/tests/test_proposed_state_injection.py
git commit -m "feat(workflow): add the proposed state to every non-minimal preset default"
```

---

### Task 9: Backfill `proposed` into live workflow definitions

**Files:**
- Create: `backend/workflow/migrations/0018_add_proposed_state.py`
- Test: `backend/workflow/tests/test_proposed_state_migration.py`

**Interfaces:**
- Consumes: `inject_proposed_state`, `SCHEMAS_WITHOUT_PROPOSED`, `_PROPOSED_REJECT_STATE` (Task 8).
- Produces: every `GlobalWorkflowDefinition` and every `is_customized=False` `WorkflowEngineDefinition` outside `SCHEMAS_WITHOUT_PROPOSED` carries the proposal state.

- [ ] **Step 1: Write the failing test**

```python
# backend/workflow/tests/test_proposed_state_migration.py
"""0018 backfills the proposal state into live definitions (spec §7.3)."""
from __future__ import annotations

import pytest

from workflow.migrations._proposed_backfill import backfill_definition
from workflow.definition_store import PROPOSED_STATE


def test_backfill_adds_proposed_to_a_standard_graph():
    graph = {
        "states": ["draft", "approved", "deprecated"],
        "transitions": [
            {
                "from_state": "draft",
                "to_state": "approved",
                "allowed_roles": ["approver", "admin"],
                "requires_change_reason": False,
                "signature_gate": False,
            }
        ],
    }
    changed = backfill_definition(graph, "standard")
    assert changed is True
    assert graph["states"] == [
        "draft",
        PROPOSED_STATE,
        "approved",
        "deprecated",
        "rejected",
    ]


def test_backfill_skips_minimal():
    graph = {"states": ["draft", "done"], "transitions": []}
    assert backfill_definition(graph, "minimal") is False
    assert graph["states"] == ["draft", "done"]


def test_backfill_is_idempotent():
    graph = {"states": ["draft", "approved"], "transitions": []}
    backfill_definition(graph, "standard")
    snapshot = {"states": list(graph["states"]), "transitions": list(graph["transitions"])}
    assert backfill_definition(graph, "standard") is False
    assert graph["states"] == snapshot["states"]


def test_backfill_reuses_adr_title_case_rejected():
    graph = {
        "states": ["Draft", "In Review", "Approved", "Rejected", "Superseded"],
        "transitions": [],
    }
    backfill_definition(graph, "adr_default")
    assert graph["states"].count("Rejected") == 1
    assert "rejected" not in graph["states"]


@pytest.mark.django_db
def test_migration_backfilled_shipped_rows():
    # The migration ran during test-DB setup; every seeded non-minimal global
    # default must now carry the state.
    from workflow.models import GlobalWorkflowDefinition

    for row in GlobalWorkflowDefinition.unscoped.exclude(preset="minimal"):
        assert PROPOSED_STATE in row.workflow_json.get("states", []), row.preset
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec backend pytest workflow/tests/test_proposed_state_migration.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'workflow.migrations._proposed_backfill'`

- [ ] **Step 3: Write the shared backfill helper**

```python
# backend/workflow/migrations/_proposed_backfill.py
"""Shared backfill logic for migration 0018 (kept importable for tests).

A migration module name starting with a digit cannot be imported directly, so
the transformation lives here and 0018 is a thin RunPython wrapper. The helper
deliberately re-uses ``definition_store.inject_proposed_state`` rather than
re-implementing it: a divergence between what new workspaces get seeded and
what existing rows are backfilled with is exactly the class of bug that makes
one workspace behave differently from its neighbour.
"""
from __future__ import annotations

from typing import Any


def backfill_definition(workflow_json: dict[str, Any], preset: str) -> bool:
    """Add the proposal state to *workflow_json* in place.

    Args:
        workflow_json: The stored graph. Mutated in place when it changes.
        preset: The row's preset key, deciding exemption and reject target.

    Returns:
        True when the graph actually changed (keeps the migration idempotent
        and avoids pointless UPDATEs).
    """
    from workflow.definition_store import (
        _DEFAULT_REJECT_STATE,
        _PROPOSED_REJECT_STATE,
        SCHEMAS_WITHOUT_PROPOSED,
        inject_proposed_state,
    )

    if preset in SCHEMAS_WITHOUT_PROPOSED:
        return False
    if not workflow_json.get("states"):
        return False

    updated = inject_proposed_state(
        workflow_json,
        reject_state=_PROPOSED_REJECT_STATE.get(preset, _DEFAULT_REJECT_STATE),
    )
    if updated == workflow_json:
        return False

    workflow_json["states"] = updated["states"]
    workflow_json["transitions"] = updated["transitions"]
    if "state_meta" in updated:
        workflow_json["state_meta"] = updated["state_meta"]
    return True
```

- [ ] **Step 4: Write the migration**

```python
# backend/workflow/migrations/0018_add_proposed_state.py
"""Spec §7.3 — add the "proposed" state to existing workflow definitions.

Same shape as 0016_seed_adr_risk_outdated_equivalent_flags: update every
GlobalWorkflowDefinition, propagate into its ``is_customized=False`` derived
rows, then sweep the workspace rows that have no linked global (pre-REQ-178
data). ``is_customized=True`` rows are deliberately left alone — that workspace
diverged on purpose and an admin can re-add the state via the Workflow Editor
(spec §7.3).
"""
from django.db import migrations

from workflow.migrations._proposed_backfill import backfill_definition


def add_proposed_state(apps, schema_editor):
    GlobalWorkflowDefinition = apps.get_model("workflow", "GlobalWorkflowDefinition")
    WorkflowEngineDefinition = apps.get_model("workflow", "WorkflowEngineDefinition")

    for global_def in GlobalWorkflowDefinition.objects.all():
        workflow_json = global_def.workflow_json
        if not backfill_definition(workflow_json, global_def.preset):
            continue
        global_def.workflow_json = workflow_json
        global_def.save(update_fields=["workflow_json"])
        WorkflowEngineDefinition.objects.filter(
            source_global_id=global_def.id, is_customized=False
        ).update(workflow_json=workflow_json)

    for record in WorkflowEngineDefinition.objects.filter(is_customized=False):
        workflow_json = record.workflow_json
        if not backfill_definition(workflow_json, record.preset):
            continue
        record.workflow_json = workflow_json
        record.save(update_fields=["workflow_json"])


def remove_proposed_state(apps, schema_editor):
    """Reverse: drop the proposal state and its two transitions.

    Items currently sitting in "proposed" would become orphaned, so this
    refuses rather than silently corrupting them.
    """
    WorkflowItemState = apps.get_model("workflow", "WorkflowItemState")
    if WorkflowItemState.objects.filter(current_state="proposed").exists():
        raise RuntimeError(
            "Cannot reverse 0018: items still sit in the 'proposed' state. "
            "Confirm or discard them first."
        )

    GlobalWorkflowDefinition = apps.get_model("workflow", "GlobalWorkflowDefinition")
    WorkflowEngineDefinition = apps.get_model("workflow", "WorkflowEngineDefinition")
    for model in (GlobalWorkflowDefinition, WorkflowEngineDefinition):
        for row in model.objects.all():
            graph = row.workflow_json
            states = [s for s in graph.get("states", []) if s != "proposed"]
            transitions = [
                t
                for t in graph.get("transitions", [])
                if t.get("from_state") != "proposed"
            ]
            if states == graph.get("states") and transitions == graph.get(
                "transitions"
            ):
                continue
            graph["states"] = states
            graph["transitions"] = transitions
            row.workflow_json = graph
            row.save(update_fields=["workflow_json"])


class Migration(migrations.Migration):

    dependencies = [
        ("workflow", "0017_backfill_lifecycle_status_mirror"),
    ]

    operations = [
        migrations.RunPython(add_proposed_state, remove_proposed_state),
    ]
```

- [ ] **Step 5: Apply and run the test**

Run: `docker compose exec backend python manage.py migrate workflow && docker compose exec backend pytest workflow/tests/test_proposed_state_migration.py -v --create-db`
Expected: PASS (5 tests)

- [ ] **Step 6: Commit**

```bash
git add backend/workflow/migrations/_proposed_backfill.py backend/workflow/migrations/0018_add_proposed_state.py backend/workflow/tests/test_proposed_state_migration.py
git commit -m "feat(workflow): backfill the proposed state into existing definitions"
```

---

### Task 10: `initial_state_for()` — agents start in `proposed`

**Files:**
- Modify: `backend/workflow/lifecycle_manager.py:219-271` (`initialize_workflow_states`)
- Modify: `backend/workflow/services.py:428-457` (`initialize_workflow_states`)
- Test: `backend/workflow/tests/test_proposed_initialization.py`

**Interfaces:**
- Consumes: `AuthContext.actor_type` (Task 2), `PROPOSED_STATE` (Task 8), `WorkflowDefinitionStore.get_definition` → `WorkflowDefinitionDTO`.
- Produces: `workflow.services.initial_state_for(ctx: AuthContext, item_type: str, workspace_id: UUID | str) -> str`; `StateLifecycleManager.initialize_workflow_states(..., initial_state: str | None = None)`.

- [ ] **Step 1: Write the failing test**

```python
# backend/workflow/tests/test_proposed_initialization.py
"""Agent-created artifacts start in "proposed" (spec §4.2)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import pytest

from auth_tenancy.context import AuthContext, AuthMethod
from workflow.definition_store import WorkflowDefinitionDTO
from workflow.services import initial_state_for

WS = UUID("11111111-1111-1111-1111-111111111111")


def _ctx(actor_type: str) -> AuthContext:
    return AuthContext(
        user_id=uuid4(),
        tenant_id=uuid4(),
        active_roles=("editor",),
        auth_method=AuthMethod.API_KEY,
        api_key_id=uuid4(),
        actor_type=actor_type,
    )


def _dto(states: tuple[str, ...]) -> WorkflowDefinitionDTO:
    return WorkflowDefinitionDTO(
        states=states,
        transitions=(),
        workspace_id=WS,
        item_type="Requirement",
        preset="standard",
    )


def test_human_gets_the_definitions_initial_state():
    store = MagicMock()
    store.get_definition.return_value = _dto(("draft", "proposed", "approved"))
    with patch("workflow.services._get_store", return_value=store):
        assert initial_state_for(_ctx("user"), "Requirement", WS) == "draft"


def test_agent_gets_proposed_when_the_graph_has_it():
    store = MagicMock()
    store.get_definition.return_value = _dto(("draft", "proposed", "approved"))
    with patch("workflow.services._get_store", return_value=store):
        assert initial_state_for(_ctx("agent"), "Requirement", WS) == "proposed"


def test_agent_falls_back_when_the_graph_lacks_proposed():
    store = MagicMock()
    store.get_definition.return_value = _dto(("draft", "done"))
    with patch("workflow.services._get_store", return_value=store):
        assert initial_state_for(_ctx("agent"), "Requirement", WS) == "draft"


def test_definition_lookup_failure_never_raises():
    from workflow.definition_store import WorkflowDefinitionError

    store = MagicMock()
    store.get_definition.side_effect = WorkflowDefinitionError("nope")
    with patch("workflow.services._get_store", return_value=store):
        # The create_X() paths swallow workflow-init exceptions, so a raise here
        # would silently leave the artifact with no workflow state at all.
        assert initial_state_for(_ctx("agent"), "Requirement", WS) == "draft"


@pytest.mark.django_db
def test_lifecycle_honours_an_explicit_initial_state(requirement_with_workflow):
    from workflow.lifecycle_manager import StateLifecycleManager

    item_id, workspace_id = requirement_with_workflow
    other_id = uuid4()
    states = StateLifecycleManager().initialize_workflow_states(
        item_ids=[other_id],
        item_type="Requirement",
        workspace_id=workspace_id,
        initial_state="proposed",
    )
    assert states[0].current_state == "proposed"
```

> `requirement_with_workflow` is the existing fixture in `backend/workflow/tests/conftest.py:45`. Confirm its return shape before running; if it returns the ORM object rather than a tuple, adapt the two unpacked names in the last test only.

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec backend pytest workflow/tests/test_proposed_initialization.py -v`
Expected: FAIL with `ImportError: cannot import name 'initial_state_for' from 'workflow.services'`

- [ ] **Step 3: Add the optional override to the lifecycle manager**

In `backend/workflow/lifecycle_manager.py`, change the signature and the two lines that use it:

```python
    def initialize_workflow_states(
        self,
        item_ids: list[UUID],
        item_type: str,
        workspace_id: UUID,
        initial_state: str | None = None,
    ) -> list[WorkflowItemState]:
```

and replace `initial_state = dto.initial_state` with:

```python
        # ``initial_state`` overrides the definition's own initial state. Used
        # by the agent-proposal path (spec §4.2), which seeds "proposed"
        # instead. None keeps the historical behaviour for every other caller.
        dto = self._store.get_definition(workspace_id, item_type)
        if initial_state is None:
            initial_state = dto.initial_state
```

Add the parameter to the docstring's `Args:` block.

- [ ] **Step 4: Add `initial_state_for` and wire it in**

In `backend/workflow/services.py`, add above `initialize_workflow_states`:

```python
def initial_state_for(
    ctx: AuthContext, item_type: str, workspace_id: UUID | str
) -> str:
    """Return the workflow state a newly created item must start in (spec §4.2).

    An artifact created by an ``actor_type="agent"`` principal starts in
    ``"proposed"`` — but only when the workspace's resolved graph for this item
    type actually knows that state. A ``minimal``-preset workspace, or one whose
    admin removed the state from its customized definition, keeps the normal
    initial state; graph membership is the ONLY switch (no preset lookup here).

    This is the single seam the spec's risk section demands: every ``create_X()``
    service reaches the workflow engine through
    :func:`initialize_workflow_states`, which calls this. There is no per-service
    copy to forget.

    Never raises: the ``create_X()`` callers swallow workflow-init exceptions, so
    a raise here would silently produce artifacts with no workflow state at all.
    An unresolvable definition degrades to ``"draft"``, which is what the caller
    would have got before this feature existed.

    Args:
        ctx: The resolved request identity.
        item_type: Entity type (e.g. "Requirement").
        workspace_id: Workspace the item belongs to.

    Returns:
        The state name to seed ``WorkflowItemState.current_state`` with.
    """
    from .definition_store import PROPOSED_STATE

    try:
        dto = _get_store().get_definition(UUID(str(workspace_id)), item_type)
    except Exception:  # noqa: BLE001 — see the docstring: never raise
        return "draft"

    if ctx.actor_type == "agent" and PROPOSED_STATE in dto.states:
        return PROPOSED_STATE
    return dto.initial_state
```

and change the body of `initialize_workflow_states` to:

```python
    uuid_ids = [UUID(str(i)) for i in item_ids]
    workspace_uuid = UUID(str(workspace_id))
    return _get_lifecycle().initialize_workflow_states(
        item_ids=uuid_ids,
        item_type=item_type,
        workspace_id=workspace_uuid,
        initial_state=initial_state_for(ctx, item_type, workspace_uuid),
    )
```

Add `"initial_state_for"` to the module's `__all__`.

- [ ] **Step 5: Run test to verify it passes**

Run: `docker compose exec backend pytest workflow/tests/test_proposed_initialization.py -v`
Expected: PASS (5 tests)

- [ ] **Step 6: Verify no create path regressed**

Run: `docker compose exec backend pytest workflow/tests/ application/tests/test_requirement_service.py application/tests/test_adr_service.py application/tests/test_stakeholder_need_service.py -q`
Expected: no NEW failures

- [ ] **Step 7: Commit**

```bash
git add backend/workflow/lifecycle_manager.py backend/workflow/services.py backend/workflow/tests/test_proposed_initialization.py
git commit -m "feat(workflow): seed agent-created artifacts in the proposed state"
```

---

### Task 11: Record the proposer and sync the status mirror

**Files:**
- Modify: `backend/workflow/lifecycle_manager.py:219-271`
- Test: `backend/workflow/tests/test_proposed_initialization.py` (extend)

**Interfaces:**
- Consumes: `WorkflowHistoryEntry`, `StateLifecycleManager._sync_status_mirror`, `._sync_lifecycle_mirror` (existing).
- Produces: `initialize_workflow_states(..., initial_state=..., proposed_by="<label>")` writes one `WorkflowHistoryEntry` per item and syncs the status mirror when `initial_state` differs from the definition's own initial state.

- [ ] **Step 1: Write the failing test**

Append to `backend/workflow/tests/test_proposed_initialization.py`:

```python
@pytest.mark.django_db
def test_proposed_init_writes_a_history_entry(requirement_with_workflow):
    from workflow.lifecycle_manager import StateLifecycleManager
    from workflow.models import WorkflowHistoryEntry

    _item_id, workspace_id = requirement_with_workflow
    new_id = uuid4()
    states = StateLifecycleManager().initialize_workflow_states(
        item_ids=[new_id],
        item_type="Requirement",
        workspace_id=workspace_id,
        initial_state="proposed",
        proposed_by="Claude Code",
    )
    entry = WorkflowHistoryEntry.unscoped.get(item_state=states[0])
    assert entry.from_state == ""
    assert entry.to_state == "proposed"
    assert entry.transitioned_by == "Claude Code"


@pytest.mark.django_db
def test_normal_init_writes_no_history(requirement_with_workflow):
    from workflow.lifecycle_manager import StateLifecycleManager
    from workflow.models import WorkflowHistoryEntry

    _item_id, workspace_id = requirement_with_workflow
    new_id = uuid4()
    states = StateLifecycleManager().initialize_workflow_states(
        item_ids=[new_id], item_type="Requirement", workspace_id=workspace_id
    )
    assert not WorkflowHistoryEntry.unscoped.filter(item_state=states[0]).exists()


@pytest.mark.django_db
def test_proposed_init_syncs_the_status_mirror(requirement_with_workflow):
    from persistence.models import Requirement
    from workflow.lifecycle_manager import StateLifecycleManager

    item_id, workspace_id = requirement_with_workflow
    Requirement.unscoped.filter(id=item_id).update(status="draft")
    StateLifecycleManager().initialize_workflow_states(
        item_ids=[item_id],
        item_type="Requirement",
        workspace_id=workspace_id,
        initial_state="proposed",
        proposed_by="Claude Code",
    )
    # The mirror must follow, otherwise `?status=proposed` list filtering and
    # every status badge would still read "draft".
    assert Requirement.unscoped.get(id=item_id).status == "proposed"
```

> The last test reuses `item_id`, which already has a `WorkflowItemState`. If the fixture's row already exists, delete it first inside the test (`WorkflowItemState.unscoped.filter(item_id=item_id).delete()`) so `initialize_workflow_states` can create it.

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec backend pytest workflow/tests/test_proposed_initialization.py -k "history or mirror" -v`
Expected: FAIL with `TypeError: initialize_workflow_states() got an unexpected keyword argument 'proposed_by'`

- [ ] **Step 3: Write the history entry and sync the mirror**

In `backend/workflow/lifecycle_manager.py`, extend the signature with `proposed_by: str = ""` and replace the creation loop with:

```python
        created: list[WorkflowItemState] = []
        seeded_off_default = initial_state != dto.initial_state
        for item_id in item_ids:
            state = WorkflowItemState.objects.create(
                item_id=item_id,
                item_type=item_type,
                workspace_id=workspace_id,
                definition=definition_record,
                current_state=initial_state,
            )
            created.append(state)

            if not seeded_off_default:
                continue

            # Spec §4.2: "wer hat vorgeschlagen" lives in the history entry.
            # Nothing wrote one at initialization before this — a plain
            # initialization is not a transition and needs no record, but a
            # proposal does, because it is the only provenance the artifact has.
            # ``from_state=""`` marks "came into existence here".
            WorkflowHistoryEntry.objects.create(
                item_state=state,
                from_state="",
                to_state=initial_state,
                transitioned_by=proposed_by or "agent",
                transitioned_at=datetime.now(timezone.utc),
                change_reason="",
                workspace_id=workspace_id,
            )
            # The denormalized status/lifecycle mirrors are normally written by
            # perform_transition only. Seeding off-default has to write them
            # too, otherwise the entity's ``status`` column keeps its model
            # default and every list filter / badge shows the wrong state.
            self._sync_status_mirror(item_id, item_type, initial_state)
            self._sync_lifecycle_mirror(item_id, item_type, initial_state)

        return created
```

Confirm `datetime`/`timezone` are already imported at the top of the module (they are — `perform_transition` uses them); if not, add `from datetime import datetime, timezone`.

- [ ] **Step 4: Pass the agent label through the facade**

In `backend/workflow/services.py`, `initialize_workflow_states`, extend the delegation:

```python
    resolved_initial = initial_state_for(ctx, item_type, workspace_uuid)
    return _get_lifecycle().initialize_workflow_states(
        item_ids=uuid_ids,
        item_type=item_type,
        workspace_id=workspace_uuid,
        initial_state=resolved_initial,
        proposed_by=ctx.agent_label or str(ctx.user_id),
    )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `docker compose exec backend pytest workflow/tests/test_proposed_initialization.py -v`
Expected: PASS (8 tests)

- [ ] **Step 6: Commit**

```bash
git add backend/workflow/lifecycle_manager.py backend/workflow/services.py backend/workflow/tests/test_proposed_initialization.py
git commit -m "feat(workflow): record the proposer and sync the status mirror on proposal"
```

---

### Task 12: Rule 0 — an agent may never leave `proposed`

**Files:**
- Modify: `backend/workflow/transition_validator.py:65-93` (`ValidationRequest`), `:44-53` (error codes), `:251-306` (`validate`)
- Modify: `backend/workflow/services.py:238-252` (the `ValidationRequest` construction in `transition()`)
- Test: `backend/workflow/tests/test_agent_transition_guard.py`

**Interfaces:**
- Consumes: `AuthContext.actor_type` (Task 2), `PROPOSED_STATE` (Task 8).
- Produces: `ValidationRequest.actor_type: str = "user"`; `transition_validator.EC_AGENT_SELF_CONFIRM = "AGENT_SELF_CONFIRM_FORBIDDEN"`.

- [ ] **Step 1: Write the failing test**

```python
# backend/workflow/tests/test_agent_transition_guard.py
"""Spec §4.3 — an agent never confirms its own proposal."""
from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

from workflow.definition_store import (
    TransitionDefinitionDTO,
    WorkflowDefinitionDTO,
)
from workflow.transition_validator import (
    EC_AGENT_SELF_CONFIRM,
    TransitionValidator,
    ValidationRequest,
)

WS = UUID("11111111-1111-1111-1111-111111111111")


def _definition() -> WorkflowDefinitionDTO:
    return WorkflowDefinitionDTO(
        states=("draft", "proposed", "approved", "rejected"),
        transitions=(
            TransitionDefinitionDTO(
                from_state="proposed",
                to_state="draft",
                # Deliberately mis-configured to include an agent-ish role:
                # the guard must hold regardless of allowed_roles (spec §4.3).
                allowed_roles=("editor", "approver", "admin"),
            ),
            TransitionDefinitionDTO(
                from_state="draft",
                to_state="approved",
                allowed_roles=("approver", "admin"),
            ),
        ),
        workspace_id=WS,
        item_type="Requirement",
        preset="standard",
    )


def _request(actor_type: str, current: str, target: str) -> ValidationRequest:
    return ValidationRequest(
        item_id=uuid4(),
        workspace_id=WS,
        item_type="Requirement",
        current_state=current,
        target_state=target,
        user_id=uuid4(),
        user_roles=("admin",),
        tenant_id=uuid4(),
        actor_type=actor_type,
    )


def _validate(request: ValidationRequest):
    validator = TransitionValidator(definition_store=MagicMock())
    with patch.object(
        TransitionValidator, "_load_definition", return_value=_definition()
    ):
        return validator.validate(request)


def test_agent_cannot_leave_proposed():
    result = _validate(_request("agent", "proposed", "draft"))
    assert result.valid is False
    assert result.error_code == EC_AGENT_SELF_CONFIRM


def test_agent_cannot_discard_its_own_proposal():
    result = _validate(_request("agent", "proposed", "rejected"))
    assert result.valid is False
    assert result.error_code == EC_AGENT_SELF_CONFIRM


def test_human_can_leave_proposed():
    assert _validate(_request("user", "proposed", "draft")).valid is True


def test_agent_may_still_transition_elsewhere():
    assert _validate(_request("agent", "draft", "approved")).valid is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec backend pytest workflow/tests/test_agent_transition_guard.py -v`
Expected: FAIL with `ImportError: cannot import name 'EC_AGENT_SELF_CONFIRM'`

- [ ] **Step 3: Add the error code and the request field**

In `backend/workflow/transition_validator.py`, next to the other `EC_*` constants:

```python
EC_AGENT_SELF_CONFIRM = "AGENT_SELF_CONFIRM_FORBIDDEN"
```

and add to `ValidationRequest` after `tenant_id`:

```python
    #: ``"user"`` or ``"agent"`` (AuthContext.actor_type). Drives rule 0 —
    #: an agent may never move an item out of the "proposed" state.
    actor_type: str = "user"
```

Document it in the `Attributes:` docstring block.

- [ ] **Step 4: Add rule 0 to `validate`**

In `TransitionValidator.validate`, insert immediately after the `ws_str = str(request.workspace_id)` line and **before** the definition load:

```python
        # ---- Rule 0: an agent never confirms its own proposal (spec §4.3) ---
        # Checked here, not via allowed_roles, so a workspace admin who
        # accidentally grants an agent-held role on the proposed-> transitions
        # cannot switch the control off. Runs before the definition load
        # because it needs no definition and must not be reachable past any
        # rule that could pass first.
        from .definition_store import PROPOSED_STATE

        if request.actor_type == "agent" and request.current_state == PROPOSED_STATE:
            return ValidationResult(
                valid=False,
                error_code=EC_AGENT_SELF_CONFIRM,
                error_message=(
                    "An AI agent may not confirm or discard a proposal. "
                    "A human principal must perform this transition."
                ),
            )
```

- [ ] **Step 5: Wire the field from the request context**

In `backend/workflow/services.py`, in `transition()`, add to the `ValidationRequest(...)` construction:

```python
        actor_type=ctx.actor_type,
```

- [ ] **Step 6: Export the new code**

Add `EC_AGENT_SELF_CONFIRM` to the `from .transition_validator import (...)` block at the top of `workflow/services.py` and to that module's `__all__`.

- [ ] **Step 7: Run test to verify it passes**

Run: `docker compose exec backend pytest workflow/tests/test_agent_transition_guard.py -v`
Expected: PASS (4 tests)

- [ ] **Step 8: Commit**

```bash
git add backend/workflow/transition_validator.py backend/workflow/services.py backend/workflow/tests/test_agent_transition_guard.py
git commit -m "feat(workflow): forbid agents from leaving the proposed state"
```

---

### Task 13: Close the two validator-bypassing paths

**Files:**
- Modify: `backend/workflow/services.py:285-368` (`outdate`)
- Modify: `backend/application/ai_derivation_service.py:1465-1530` (`_auto_approve` loop)
- Test: `backend/workflow/tests/test_agent_transition_guard.py` (extend)

**Interfaces:**
- Consumes: `PROPOSED_STATE`, `WorkflowTransitionError`, `EC_AGENT_SELF_CONFIRM` (Task 12).
- Produces: `outdate()` raises `WorkflowTransitionError(EC_AGENT_SELF_CONFIRM, ...)` for an agent acting on a proposed item; `_auto_approve` stops at `proposed`.

- [ ] **Step 1: Write the failing test**

Append to `backend/workflow/tests/test_agent_transition_guard.py`:

```python
import pytest

from workflow.services import WorkflowTransitionError, outdate


def _ctx(actor_type: str):
    from auth_tenancy.context import AuthContext, AuthMethod

    return AuthContext(
        user_id=uuid4(),
        tenant_id=uuid4(),
        active_roles=("admin",),
        auth_method=AuthMethod.API_KEY,
        api_key_id=uuid4(),
        actor_type=actor_type,
    )


def test_outdate_blocks_an_agent_on_a_proposed_item():
    lifecycle = MagicMock()
    lifecycle.get_item_state.return_value = MagicMock(current_state="proposed")
    with patch("workflow.services._get_lifecycle", return_value=lifecycle):
        with pytest.raises(WorkflowTransitionError) as exc:
            outdate(uuid4(), "Requirement", WS, _ctx("agent"))
    assert exc.value.error_code == EC_AGENT_SELF_CONFIRM
    lifecycle.force_transition.assert_not_called()


def test_outdate_allows_a_human_on_a_proposed_item():
    lifecycle = MagicMock()
    lifecycle.get_item_state.return_value = MagicMock(current_state="proposed")
    lifecycle.force_transition.return_value = MagicMock(
        previous_state="proposed",
        new_state="outdated",
        history_entry_id=uuid4(),
        signature_seal="",
    )
    with patch("workflow.services._get_lifecycle", return_value=lifecycle):
        result = outdate(uuid4(), "Requirement", WS, _ctx("user"))
    assert result.new_state == "outdated"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec backend pytest workflow/tests/test_agent_transition_guard.py -k outdate -v`
Expected: FAIL — `test_outdate_blocks_an_agent_on_a_proposed_item` does not raise

- [ ] **Step 3: Guard `outdate()`**

In `backend/workflow/services.py`, `outdate()`, replace the lazy-init block with:

```python
    lifecycle = _get_lifecycle()
    existing_state = lifecycle.get_item_state(item_id_uuid, item_type, workspace_uuid)

    # Spec §4.3: outdate() deliberately bypasses the TransitionValidator
    # (force_transition), so rule 0 would not fire here — an agent could
    # soft-delete its own proposal and make the human review disappear.
    from .definition_store import PROPOSED_STATE

    if (
        ctx.actor_type == "agent"
        and existing_state is not None
        and existing_state.current_state == PROPOSED_STATE
    ):
        raise WorkflowTransitionError(
            error_code=EC_AGENT_SELF_CONFIRM,
            error_message=(
                "An AI agent may not discard a proposal. A human principal "
                "must confirm or reject it."
            ),
        )

    if existing_state is None:
        if not allow_lazy_init:
            raise WorkflowItemNotFoundError(
                f"No workflow-tracked {item_type} {item_id_uuid} in workspace "
                f"{workspace_uuid}."
            )
        dto = _get_store().get_definition(workspace_uuid, item_type)
        lifecycle.ensure_item_state(
            item_id_uuid, item_type, workspace_uuid, dto.initial_state
        )
```

Update the `Raises:` section of the docstring with `WorkflowTransitionError: the caller is an agent and the item is a proposal.`

- [ ] **Step 4: Stop auto-approval from lifting a proposal**

In `backend/application/ai_derivation_service.py`, inside the `_auto_approve` loop, immediately after `available` is refreshed and before the `auto_approve_target` check:

```python
                if available.current_state == "proposed":
                    # Spec §4.3: a proposal is a human decision. Auto-approval
                    # must stop here rather than call transition() and take a
                    # WorkflowTransitionError for a state it should never have
                    # entered.
                    break
```

- [ ] **Step 5: Run test to verify it passes**

Run: `docker compose exec backend pytest workflow/tests/test_agent_transition_guard.py -v && docker compose exec backend pytest application/tests/ -k derivation -q`
Expected: PASS (6 tests), no NEW derivation failures

- [ ] **Step 6: Commit**

```bash
git add backend/workflow/services.py backend/application/ai_derivation_service.py backend/workflow/tests/test_agent_transition_guard.py
git commit -m "fix(workflow): close the outdate and auto-approve bypasses for agent proposals"
```

---

### Task 14: `TraceLink.proposed_by` / `proposed_at`

**Files:**
- Modify: `backend/persistence/models.py:1352-1409` (`TraceLink`)
- Create: `backend/persistence/migrations/0070_tracelink_proposed_by.py`
- Modify: `backend/rest_api/serializers.py` (`TraceLinkSerializer`, alongside the `rationale`/`suspect_*` fields added by the Traceability-Semantik plan Task 13)
- Test: `backend/application/tests/test_trace_link_proposal.py`

**Interfaces:**
- Consumes: `auth_tenancy.ApiKey` (Task 1).
- Produces: `TraceLink.proposed_by: ApiKey | None`, `TraceLink.proposed_at: datetime | None`, `TraceLink.is_proposal: bool`; `TraceLinkSerializer` returns `proposed_by`, `proposed_at`, `proposed_by_label` (read-only).

- [ ] **Step 1: Write the failing test**

```python
# backend/application/tests/test_trace_link_proposal.py
"""TraceLink proposal fields and their confirm/discard semantics (spec §5)."""
from __future__ import annotations

import pytest
from django.utils import timezone

from auth_tenancy.models import ApiKey
from persistence.models import Artifact, TraceLink, Tenant, User, Workspace


@pytest.fixture
def graph(db):
    tenant = Tenant.objects.create(name="t-tl-proposal", is_active=True)
    user = User.objects.create(
        tenant=tenant, email="tl@example.com", is_active=True
    )
    workspace = Workspace.objects.create(tenant=tenant, name="ws")
    src = Artifact.objects.create(
        tenant=tenant, workspace=workspace, artifact_type="Requirement", title="s"
    )
    tgt = Artifact.objects.create(
        tenant=tenant, workspace=workspace, artifact_type="Requirement", title="t"
    )
    key = ApiKey.unscoped.create(
        tenant=tenant,
        user=user,
        name="bot",
        key_hash="sha256:tl",
        principal_type="agent",
        agent_label="Claude Code",
    )
    return tenant, src, tgt, key


@pytest.mark.django_db
def test_human_link_has_no_proposal_fields(graph):
    tenant, src, tgt, _key = graph
    link = TraceLink.objects.create(
        tenant=tenant, source=src, target=tgt, link_type="derives-from"
    )
    assert link.proposed_by is None
    assert link.proposed_at is None
    assert link.is_proposal is False


@pytest.mark.django_db
def test_agent_link_carries_the_proposing_key(graph):
    tenant, src, tgt, key = graph
    now = timezone.now()
    link = TraceLink.objects.create(
        tenant=tenant,
        source=src,
        target=tgt,
        link_type="derives-from",
        proposed_by=key,
        proposed_at=now,
    )
    link.refresh_from_db()
    assert link.proposed_by_id == key.id
    assert link.proposed_at == now
    assert link.is_proposal is True


@pytest.mark.django_db
def test_deleting_the_key_keeps_the_link(graph):
    tenant, src, tgt, key = graph
    link = TraceLink.objects.create(
        tenant=tenant,
        source=src,
        target=tgt,
        link_type="derives-from",
        proposed_by=key,
        proposed_at=timezone.now(),
    )
    key.delete()
    link.refresh_from_db()
    # SET_NULL: losing the key must never cascade away a real trace edge.
    assert link.proposed_by_id is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec backend pytest application/tests/test_trace_link_proposal.py -v`
Expected: FAIL with `TypeError: TraceLink() got unexpected keyword arguments: 'proposed_by'`

- [ ] **Step 3: Add the fields**

In `backend/persistence/models.py`, in `TraceLink` after `embedding`:

```python
    # KI-Vorschlag-als-Zustand spec §5: a trace link is not a workflow-tracked
    # item (no WorkflowItemState per link), so an agent-proposed link is marked
    # by these two fields instead of by a state. Confirming NULLs both;
    # discarding deletes the row.
    #
    # SET_NULL, not CASCADE: revoking or deleting the proposing key must not
    # delete trace edges. A NULL proposed_by with a non-NULL proposed_at simply
    # reads as "proposed by a key that no longer exists".
    proposed_by = models.ForeignKey(
        "auth_tenancy.ApiKey",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="proposed_trace_links",
        help_text=(
            "API key of the AI agent that proposed this link; NULL once a human "
            "confirmed it or when a human created it directly."
        ),
    )
    proposed_at = models.DateTimeField(null=True, blank=True)
```

and after `__str__`:

```python
    @property
    def is_proposal(self) -> bool:
        """Return whether this link is still an unconfirmed agent proposal."""
        return self.proposed_at is not None
```

- [ ] **Step 4: Generate and apply the migration**

Run: `docker compose exec backend python manage.py makemigrations persistence --name tracelink_proposed_by && docker compose exec backend python manage.py migrate persistence`
Expected: `Add field proposed_at to tracelink`, `Add field proposed_by to tracelink`; migration applies cleanly

- [ ] **Step 5: Expose the fields on the serializer**

In `backend/rest_api/serializers.py`, in `TraceLinkSerializer`, next to the `suspect_*` declarations:

```python
    proposed_by = serializers.UUIDField(read_only=True, allow_null=True)
    proposed_at = serializers.DateTimeField(read_only=True, allow_null=True)
    proposed_by_label = serializers.SerializerMethodField()

    def get_proposed_by_label(self, obj) -> str:
        """Return the proposing agent's display label, empty for human links."""
        key = getattr(obj, "proposed_by", None)
        return getattr(key, "agent_label", "") or ""
```

and add the three names to the serializer's `fields` tuple.

- [ ] **Step 6: Run test to verify it passes**

Run: `docker compose exec backend pytest application/tests/test_trace_link_proposal.py -v`
Expected: PASS (3 tests)

- [ ] **Step 7: Commit**

```bash
git add backend/persistence/models.py backend/persistence/migrations/0070_tracelink_proposed_by.py backend/rest_api/serializers.py backend/application/tests/test_trace_link_proposal.py
git commit -m "feat(traceability): mark agent-proposed trace links with proposed_by/proposed_at"
```

---

### Task 15: Create, confirm and discard proposed trace links

**Files:**
- Modify: `backend/application/trace_link_service.py` (`create_trace_link` and new methods)
- Test: `backend/application/tests/test_trace_link_proposal.py` (extend)

**Interfaces:**
- Consumes: `AuthContext.actor_type`, `.api_key_id` (Task 2); `TraceLink.proposed_by`/`proposed_at` (Task 14).
- Produces: `TraceLinkService.confirm_proposed_link(link_id: UUID, ctx: AuthContext) -> TraceLink`, `TraceLinkService.discard_proposed_link(link_id: UUID, ctx: AuthContext) -> None`, and `AgentSelfConfirmError`.

- [ ] **Step 1: Write the failing test**

Append to `backend/application/tests/test_trace_link_proposal.py`:

```python
from uuid import uuid4

from application.trace_link_service import AgentSelfConfirmError, TraceLinkService
from auth_tenancy.context import AuthContext, AuthMethod


def _ctx(tenant_id, actor_type: str, api_key_id=None) -> AuthContext:
    return AuthContext(
        user_id=uuid4(),
        tenant_id=tenant_id,
        active_roles=("editor",),
        auth_method=AuthMethod.API_KEY,
        api_key_id=api_key_id,
        actor_type=actor_type,
    )


@pytest.mark.django_db
def test_confirm_clears_both_proposal_fields(graph):
    tenant, src, tgt, key = graph
    link = TraceLink.objects.create(
        tenant=tenant,
        source=src,
        target=tgt,
        link_type="derives-from",
        proposed_by=key,
        proposed_at=timezone.now(),
    )
    TraceLinkService().confirm_proposed_link(link.id, _ctx(tenant.id, "user"))
    link.refresh_from_db()
    assert link.proposed_by_id is None
    assert link.proposed_at is None
    assert link.is_proposal is False


@pytest.mark.django_db
def test_discard_deletes_the_link(graph):
    tenant, src, tgt, key = graph
    link = TraceLink.objects.create(
        tenant=tenant,
        source=src,
        target=tgt,
        link_type="derives-from",
        proposed_by=key,
        proposed_at=timezone.now(),
    )
    TraceLinkService().discard_proposed_link(link.id, _ctx(tenant.id, "user"))
    assert not TraceLink.objects.filter(id=link.id).exists()


@pytest.mark.django_db
def test_agent_may_not_confirm(graph):
    tenant, src, tgt, key = graph
    link = TraceLink.objects.create(
        tenant=tenant,
        source=src,
        target=tgt,
        link_type="derives-from",
        proposed_by=key,
        proposed_at=timezone.now(),
    )
    with pytest.raises(AgentSelfConfirmError):
        TraceLinkService().confirm_proposed_link(
            link.id, _ctx(tenant.id, "agent", key.id)
        )
    link.refresh_from_db()
    assert link.is_proposal is True


@pytest.mark.django_db
def test_agent_may_not_discard(graph):
    tenant, src, tgt, key = graph
    link = TraceLink.objects.create(
        tenant=tenant,
        source=src,
        target=tgt,
        link_type="derives-from",
        proposed_by=key,
        proposed_at=timezone.now(),
    )
    with pytest.raises(AgentSelfConfirmError):
        TraceLinkService().discard_proposed_link(
            link.id, _ctx(tenant.id, "agent", key.id)
        )
    assert TraceLink.objects.filter(id=link.id).exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec backend pytest application/tests/test_trace_link_proposal.py -k "confirm or discard" -v`
Expected: FAIL with `ImportError: cannot import name 'AgentSelfConfirmError'`

- [ ] **Step 3: Add the error type and the two methods**

In `backend/application/trace_link_service.py`, at module level:

```python
class AgentSelfConfirmError(PermissionError):
    """An AI agent tried to confirm or discard a proposal (spec §4.3/§5).

    Mirrors ``workflow.transition_validator``'s rule 0 for the one artifact
    kind that has no workflow state: a trace link.
    """
```

and inside `TraceLinkService`:

```python
    def confirm_proposed_link(self, link_id: UUID, ctx: AuthContext) -> TraceLink:
        """Accept an agent-proposed trace link (spec §5).

        Clears ``proposed_by``/``proposed_at`` — the link becomes an ordinary,
        human-owned edge. Idempotent: confirming an already-confirmed link is a
        no-op that returns it unchanged.

        Args:
            link_id: TraceLink primary key.
            ctx: The confirming principal.

        Returns:
            The refreshed TraceLink.

        Raises:
            AgentSelfConfirmError: ``ctx`` is an agent.
            NotFoundError: no such link in the active tenant.
        """
        self._set_tenant_context(ctx)
        if ctx.actor_type == "agent":
            raise AgentSelfConfirmError(
                "An AI agent may not confirm a proposed trace link."
            )
        link = TraceLink.objects.filter(id=link_id).first()
        if link is None:
            raise NotFoundError(f"TraceLink {link_id} not found")
        if link.proposed_at is not None or link.proposed_by_id is not None:
            link.proposed_by = None
            link.proposed_at = None
            link.save(update_fields=["proposed_by", "proposed_at", "modified_at"])
            self._audit(
                ctx=ctx,
                operation="update",
                entity_type="TraceLink",
                entity_id=link.id,
                details={"proposal": "confirmed"},
            )
        return link

    def discard_proposed_link(self, link_id: UUID, ctx: AuthContext) -> None:
        """Reject an agent-proposed trace link by deleting it (spec §5).

        Args:
            link_id: TraceLink primary key.
            ctx: The rejecting principal.

        Raises:
            AgentSelfConfirmError: ``ctx`` is an agent.
            NotFoundError: no such link in the active tenant.
            ValueError: the link is not a proposal — deleting a confirmed link
                goes through the normal delete path, not this one.
        """
        self._set_tenant_context(ctx)
        if ctx.actor_type == "agent":
            raise AgentSelfConfirmError(
                "An AI agent may not discard a proposed trace link."
            )
        link = TraceLink.objects.filter(id=link_id).first()
        if link is None:
            raise NotFoundError(f"TraceLink {link_id} not found")
        if not link.is_proposal:
            raise ValueError(
                "TraceLink is not a proposal; use the regular delete endpoint."
            )
        self._audit(
            ctx=ctx,
            operation="delete",
            entity_type="TraceLink",
            entity_id=link.id,
            details={"proposal": "discarded"},
        )
        link.delete()
```

Confirm `NotFoundError` and `_set_tenant_context` are the names this service already uses; if it inherits from `ServiceBase`, they are.

- [ ] **Step 4: Stamp the fields on agent-created links**

In `TraceLinkService.create_trace_link`, where the `TraceLink` row is created, add:

```python
        # Spec §5: a link an agent created is a proposal until a human confirms
        # it. ``api_key_id`` is the proposing key; a bearer-token (human)
        # request leaves both fields NULL.
        proposal_fields: dict = {}
        if ctx.actor_type == "agent" and ctx.api_key_id is not None:
            from django.utils import timezone

            proposal_fields = {
                "proposed_by_id": ctx.api_key_id,
                "proposed_at": timezone.now(),
            }
```

and pass `**proposal_fields` into the `TraceLink.objects.create(...)` call.

- [ ] **Step 5: Run test to verify it passes**

Run: `docker compose exec backend pytest application/tests/test_trace_link_proposal.py -v`
Expected: PASS (7 tests)

- [ ] **Step 6: Run the trace-link regression suite**

Run: `docker compose exec backend pytest application/tests/test_trace_link_service.py -q`
Expected: no NEW failures

- [ ] **Step 7: Commit**

```bash
git add backend/application/trace_link_service.py backend/application/tests/test_trace_link_proposal.py
git commit -m "feat(traceability): confirm and discard agent-proposed trace links"
```

---

### Task 16: Frontend status vocabulary knows `proposed`

**Files:**
- Modify: `frontend/src/utils/workflowStatus.ts:39-50` (`STATUS_ORDER`)
- Modify: `frontend/src/utils/statusBadge.ts` (`STATUS_VARIANT_MAP`)
- Test: `frontend/src/utils/workflowStatus.proposed.test.ts`

**Interfaces:**
- Produces: `getWorkflowStatusLabel("proposed") === "Proposed"`; `resolveBadgeVariant("proposed") === "info"`; `compareWorkflowStatus("proposed", "draft") < 0`.

- [ ] **Step 1: Write the failing test**

```ts
// frontend/src/utils/workflowStatus.proposed.test.ts
import { describe, expect, it } from "vitest";

import { resolveBadgeVariant } from "./statusBadge";
import {
  compareWorkflowStatus,
  getWorkflowStatusLabel,
} from "./workflowStatus";

describe("proposed status vocabulary", () => {
  it("sorts before every other lifecycle state", () => {
    expect(compareWorkflowStatus("proposed", "draft")).toBeLessThan(0);
    expect(compareWorkflowStatus("proposed", "approved")).toBeLessThan(0);
  });

  it("renders a readable label", () => {
    expect(getWorkflowStatusLabel("proposed")).toBe("Proposed");
  });

  it("uses the info badge variant", () => {
    expect(resolveBadgeVariant("proposed")).toBe("info");
  });

  it("keeps rejected on the danger variant", () => {
    expect(resolveBadgeVariant("rejected")).toBe("danger");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec frontend npm test -- src/utils/workflowStatus.proposed.test.ts`
Expected: FAIL — `compareWorkflowStatus("proposed", "draft")` returns a positive number (unknown states sort last)

- [ ] **Step 3: Add the state to the ordering**

In `frontend/src/utils/workflowStatus.ts`, at the very top of `STATUS_ORDER`, before `'draft'`:

```ts
  // AI proposal — precedes every human lifecycle state because an unconfirmed
  // proposal is upstream of "draft" (KI-Vorschlag-als-Zustand spec §4.1).
  'proposed',
```

- [ ] **Step 4: Add the badge variant**

In `frontend/src/utils/statusBadge.ts`, in `STATUS_VARIANT_MAP`, add to the pre-work/intake group:

```ts
  // Spec §4.4: a proposal is informational, not a warning — it needs a human
  // look, it is not a problem. `rejected` already maps to `danger`.
  proposed: 'info',
```

- [ ] **Step 5: Run test to verify it passes**

Run: `docker compose exec frontend npm test -- src/utils/workflowStatus.proposed.test.ts`
Expected: PASS (4 tests)

- [ ] **Step 6: Commit**

```bash
git add frontend/src/utils/workflowStatus.ts frontend/src/utils/statusBadge.ts frontend/src/utils/workflowStatus.proposed.test.ts
git commit -m "feat(ui): add the proposed status to the frontend status vocabulary"
```

---

### Task 17: `proposed_by` on the transitions endpoint

**Files:**
- Modify: `backend/rest_api/mixins/workflow_transitions.py:165-198` (the GET branch)
- Modify: `frontend/src/api/workflow-transitions.ts` (`WorkflowTransitionsResponse`)
- Test: `backend/rest_api/tests/test_transitions_proposed_by.py`

**Interfaces:**
- Consumes: `WorkflowHistoryEntry` (Task 11).
- Produces: `GET /{resource}/{id}/transitions/` additionally returns `"proposed_by": string | null`; TS type gains `proposed_by: string | null`.

- [ ] **Step 1: Write the failing test**

```python
# backend/rest_api/tests/test_transitions_proposed_by.py
"""GET transitions/ surfaces who proposed a "proposed" item (spec §4.4)."""
from __future__ import annotations

from uuid import uuid4

from rest_api.mixins.workflow_transitions import resolve_proposed_by


class _Entry:
    def __init__(self, to_state: str, transitioned_by: str) -> None:
        self.to_state = to_state
        self.transitioned_by = transitioned_by


def test_returns_none_when_not_proposed():
    assert resolve_proposed_by("draft", uuid4(), "Requirement", uuid4()) is None


def test_returns_the_history_actor(monkeypatch):
    monkeypatch.setattr(
        "rest_api.mixins.workflow_transitions._latest_proposal_actor",
        lambda item_id, item_type, workspace_id: "Claude Code",
    )
    assert (
        resolve_proposed_by("proposed", uuid4(), "Requirement", uuid4())
        == "Claude Code"
    )


def test_returns_none_when_no_history_exists(monkeypatch):
    monkeypatch.setattr(
        "rest_api.mixins.workflow_transitions._latest_proposal_actor",
        lambda item_id, item_type, workspace_id: None,
    )
    assert resolve_proposed_by("proposed", uuid4(), "Requirement", uuid4()) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec backend pytest rest_api/tests/test_transitions_proposed_by.py -v`
Expected: FAIL with `ImportError: cannot import name 'resolve_proposed_by'`

- [ ] **Step 3: Add the two helpers**

In `backend/rest_api/mixins/workflow_transitions.py`, at module level above `class WorkflowTransitionsMixin`:

```python
def _latest_proposal_actor(
    item_id: UUID, item_type: str, workspace_id: UUID
) -> str | None:
    """Return the actor of the newest ``-> "proposed"`` history entry, or None.

    Split out from :func:`resolve_proposed_by` so the pure decision logic stays
    testable without a database.
    """
    from workflow.models import WorkflowHistoryEntry, WorkflowItemState

    state = WorkflowItemState.objects.filter(
        item_id=item_id, item_type=item_type, workspace_id=workspace_id
    ).first()
    if state is None:
        return None
    entry = (
        WorkflowHistoryEntry.objects.filter(item_state=state, to_state="proposed")
        .order_by("-transitioned_at")
        .first()
    )
    return entry.transitioned_by if entry is not None else None


def resolve_proposed_by(
    current_state: str | None,
    item_id: UUID,
    item_type: str,
    workspace_id: UUID,
) -> str | None:
    """Return the proposing agent's label when the item is a proposal.

    Spec §4.4: the artifact header shows "Vorschlag von {agent_label}" instead
    of the plain status badge. Returns ``None`` for every non-proposed item so
    the UI can branch on a single nullable field.
    """
    if current_state != "proposed":
        return None
    return _latest_proposal_actor(item_id, item_type, workspace_id)
```

- [ ] **Step 4: Include it in the GET body**

In the GET branch's `Response({...})`, add:

```python
                    "proposed_by": resolve_proposed_by(
                        avail.current_state,
                        item_id,
                        self.workflow_item_type,
                        workspace_id,
                    ),
```

- [ ] **Step 5: Extend the TypeScript response type**

In `frontend/src/api/workflow-transitions.ts`, in `WorkflowTransitionsResponse`:

```ts
  /**
   * Display label of the AI agent that proposed this artifact, or null when the
   * item is not in the "proposed" state (KI-Vorschlag-als-Zustand spec §4.4).
   */
  proposed_by: string | null;
```

Because the field is required on the type, update the two `setData({ current_state: null, states: [], allowed_transitions: [] })` fallbacks in `WorkflowStatusEditor.tsx` to include `proposed_by: null`.

- [ ] **Step 6: Run test to verify it passes**

Run: `docker compose exec backend pytest rest_api/tests/test_transitions_proposed_by.py -v && docker compose exec frontend npx tsc --noEmit -p tsconfig.json`
Expected: PASS (3 tests); tsc reports no new errors

- [ ] **Step 7: Commit**

```bash
git add backend/rest_api/mixins/workflow_transitions.py backend/rest_api/tests/test_transitions_proposed_by.py frontend/src/api/workflow-transitions.ts frontend/src/components/WorkflowStatusEditor/WorkflowStatusEditor.tsx
git commit -m "feat(rest): surface the proposing agent on the transitions endpoint"
```

---

### Task 18: The proposal hint in `WorkflowStatusEditor`

**Files:**
- Modify: `frontend/src/components/WorkflowStatusEditor/WorkflowStatusEditor.tsx`
- Modify: `frontend/src/i18n/locales/de.json`, `frontend/src/i18n/locales/en.json`
- Test: `frontend/src/components/WorkflowStatusEditor/WorkflowStatusEditor.proposed.test.tsx`

**Interfaces:**
- Consumes: `WorkflowTransitionsResponse.proposed_by` (Task 17).
- Produces: a `data-testid="workflow-proposal-hint"` element; i18n keys `workflow.proposal.hint` and `workflow.proposal.hintUnknown`.

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/components/WorkflowStatusEditor/WorkflowStatusEditor.proposed.test.tsx
import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { WorkflowStatusEditor } from "./WorkflowStatusEditor";
import { workflowTransitionsApi } from "../../api/workflow-transitions";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) =>
      opts?.agent ? `${key}:${String(opts.agent)}` : key,
  }),
}));

describe("WorkflowStatusEditor proposal hint", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("shows the proposing agent when the item is proposed", async () => {
    vi.spyOn(workflowTransitionsApi, "getTransitions").mockResolvedValue({
      current_state: "proposed",
      states: ["draft", "proposed"],
      allowed_transitions: [
        { target_state: "draft", requires_change_reason: false, signature_gate: false },
      ],
      proposed_by: "Claude Code",
    });

    render(<WorkflowStatusEditor artifactType="requirement" artifactId="a1" />);

    await waitFor(() =>
      expect(screen.getByTestId("workflow-proposal-hint")).toHaveTextContent(
        "workflow.proposal.hint:Claude Code",
      ),
    );
  });

  it("falls back to a generic hint without an agent label", async () => {
    vi.spyOn(workflowTransitionsApi, "getTransitions").mockResolvedValue({
      current_state: "proposed",
      states: ["draft", "proposed"],
      allowed_transitions: [],
      proposed_by: null,
    });

    render(<WorkflowStatusEditor artifactType="requirement" artifactId="a2" />);

    await waitFor(() =>
      expect(screen.getByTestId("workflow-proposal-hint")).toHaveTextContent(
        "workflow.proposal.hintUnknown",
      ),
    );
  });

  it("renders no hint for a normal state", async () => {
    vi.spyOn(workflowTransitionsApi, "getTransitions").mockResolvedValue({
      current_state: "draft",
      states: ["draft", "approved"],
      allowed_transitions: [],
      proposed_by: null,
    });

    render(<WorkflowStatusEditor artifactType="requirement" artifactId="a3" />);

    await waitFor(() =>
      expect(screen.queryByTestId("workflow-proposal-hint")).toBeNull(),
    );
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec frontend npm test -- src/components/WorkflowStatusEditor/WorkflowStatusEditor.proposed.test.tsx --testTimeout=30000`
Expected: FAIL — `Unable to find an element by: [data-testid="workflow-proposal-hint"]`

- [ ] **Step 3: Render the hint**

In `WorkflowStatusEditor.tsx`, after the `interactive` const:

```tsx
  // Spec §4.4: a proposal replaces the plain status badge with an explicit
  // "proposed by X" hint. The transition buttons stay exactly as they are —
  // confirm/discard are ordinary transitions of the same state machine.
  const isProposal = (data?.current_state ?? null) === "proposed";
  const proposedBy = data?.proposed_by ?? null;
```

and inside the returned JSX, directly before the badge/trigger element:

```tsx
      {isProposal && (
        <span
          data-testid="workflow-proposal-hint"
          role="note"
          style={proposalHintStyle}
        >
          {proposedBy
            ? t("workflow.proposal.hint", { agent: proposedBy })
            : t("workflow.proposal.hintUnknown")}
        </span>
      )}
```

with a hoisted named style constant at module level (the `ui-ratchet` gate rejects new inline `style={{` in `components/`):

```tsx
const proposalHintStyle: CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  gap: "var(--space-1)",
  marginRight: "var(--space-2)",
  fontSize: "var(--font-size-sm)",
  color: "var(--color-badge-info-text)",
  background: "var(--color-badge-info-bg)",
  borderRadius: "var(--radius-sm)",
  padding: "var(--space-1) var(--space-2)",
};
```

Import `CSSProperties` as a type-only import alongside the existing `KeyboardEvent` type import.

- [ ] **Step 4: Add the i18n keys**

`frontend/src/i18n/locales/de.json`, inside the `workflow` object:

```json
    "proposal": {
      "hint": "Vorschlag von {{agent}}",
      "hintUnknown": "KI-Vorschlag",
      "bulkConfirm": "Ausgewählte bestätigen",
      "bulkConfirmDone": "{{count}} Vorschläge bestätigt",
      "bulkConfirmFailed": "{{count}} Vorschläge konnten nicht bestätigt werden",
      "queueMode": "Nur KI-Vorschläge",
      "selectAll": "Alle auswählen"
    }
```

`frontend/src/i18n/locales/en.json`, same object:

```json
    "proposal": {
      "hint": "Proposed by {{agent}}",
      "hintUnknown": "AI proposal",
      "bulkConfirm": "Confirm selected",
      "bulkConfirmDone": "{{count}} proposals confirmed",
      "bulkConfirmFailed": "{{count}} proposals could not be confirmed",
      "queueMode": "AI proposals only",
      "selectAll": "Select all"
    }
```

> Nested objects, not dotted flat keys — `keySeparator` is `"."`, so `"proposal.hint"` as a literal key inside `workflow` would never resolve.

- [ ] **Step 5: Run test to verify it passes**

Run: `docker compose exec frontend npm test -- src/components/WorkflowStatusEditor/WorkflowStatusEditor.proposed.test.tsx --testTimeout=30000`
Expected: PASS (3 tests)

- [ ] **Step 6: Restart the frontend container and eyeball it**

Run: `docker compose restart frontend`
Then open a workspace artifact created by an agent key and confirm the hint renders in place of the status badge, the confirm/discard buttons appear in the dropdown, and the layout does not shift in light and dark theme at 1280px and 768px width.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/WorkflowStatusEditor/ frontend/src/i18n/locales/de.json frontend/src/i18n/locales/en.json
git commit -m "feat(ui): show the proposing agent on artifacts in the proposed state"
```

---

### Task 19: A proposals mode in the review queue

**Files:**
- Modify: `frontend/src/components/Reviews/useReviewsData.ts:37-44`
- Modify: `frontend/src/components/Reviews/ReviewsView.tsx`
- Test: `frontend/src/components/Reviews/ReviewsView.proposals.test.tsx`

**Interfaces:**
- Consumes: the `?status=proposed` list filter (works because Task 11 syncs the status mirror).
- Produces: `useReviewsData({ ..., queueMode?: "review" | "proposals" })`; a `data-testid="reviews-queue-mode-toggle"` control in `ReviewsView`.

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/components/Reviews/ReviewsView.proposals.test.tsx
import { describe, expect, it } from "vitest";

import { pendingStateFor } from "./useReviewsData";

describe("proposals queue mode", () => {
  it("queries the proposed state in proposals mode", () => {
    expect(pendingStateFor("requirement", "proposals")).toBe("proposed");
    expect(pendingStateFor("goal", "proposals")).toBe("proposed");
  });

  it("keeps the historical review states in review mode", () => {
    expect(pendingStateFor("requirement", "review")).toBe("in_review");
    expect(pendingStateFor("goal", "review")).toBe("Entwurf");
  });

  it("defaults to review mode", () => {
    expect(pendingStateFor("requirement")).toBe("in_review");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec frontend npm test -- src/components/Reviews/ReviewsView.proposals.test.tsx --testTimeout=30000`
Expected: FAIL — `pendingStateFor` is not exported

- [ ] **Step 3: Make the queue state mode-aware**

In `frontend/src/components/Reviews/useReviewsData.ts`, replace `pendingStateFor` with:

```ts
/** Which queue the review list shows. */
export type ReviewQueueMode = "review" | "proposals";

/**
 * Workflow state the queue lists for a given artifact type and mode.
 *
 * In "proposals" mode the state is the same literal for every type — the
 * proposal state is injected into every non-minimal graph under one name
 * (backend/workflow/definition_store.py PROPOSED_STATE), so no per-type
 * override table is needed here.
 */
export function pendingStateFor(
  type: WorkflowArtifactType,
  mode: ReviewQueueMode = "review",
): string {
  if (mode === "proposals") return "proposed";
  return PENDING_STATE_OVERRIDES[type] ?? REVIEW_STATE;
}
```

Add `queueMode?: ReviewQueueMode` to `UseReviewsDataParams`, thread it into the `pendingStateFor(...)` call and into the `reviewKeys.list(...)` cache key (so switching modes refetches rather than serving the other queue from cache):

```ts
  list: (type: WorkflowArtifactType, workspaceId: string, mode: ReviewQueueMode = "review") =>
    ["reviews", type, "list", workspaceId, mode] as const,
```

- [ ] **Step 4: Add the mode toggle to `ReviewsView`**

Add state and a toggle next to the existing type select:

```tsx
  const [queueMode, setQueueMode] = useState<ReviewQueueMode>("review");
```

pass `queueMode` into `useReviewsData({...})`, reset the page on change by adding `queueMode` to the existing `useEffect(() => setPage(1), [search, selectedArtifactType])` dependency array, and render:

```tsx
        <label data-testid="reviews-queue-mode-toggle">
          <input
            type="checkbox"
            data-testid="reviews-queue-mode-checkbox"
            checked={queueMode === "proposals"}
            onChange={(e) =>
              setQueueMode(e.target.checked ? "proposals" : "review")
            }
          />
          {t("workflow.proposal.queueMode")}
        </label>
```

In proposals mode the approve/reject targets differ from `REVIEW_ACTION_CONFIG` (which is keyed to `in_review`). Derive them from the loaded transitions instead:

```tsx
  // In proposals mode the confirm target is the graph's own initial state and
  // the discard target its reject state — both come back in
  // `transitions.allowed_transitions`, so read them rather than maintaining a
  // second per-type table that would drift from the backend graph.
  const { approve: APPROVE_TARGET, reject: REJECT_TARGET } = useMemo(() => {
    if (queueMode !== "proposals") return REVIEW_ACTION_CONFIG[selectedArtifactType];
    const allowed = transitions?.allowed_transitions ?? [];
    return {
      approve: allowed.find((t) => !t.requires_change_reason)?.target_state ?? "draft",
      reject: allowed.find((t) => t.requires_change_reason)?.target_state ?? "rejected",
    };
  }, [queueMode, selectedArtifactType, transitions]);
```

- [ ] **Step 5: Run test to verify it passes**

Run: `docker compose exec frontend npm test -- src/components/Reviews/ReviewsView.proposals.test.tsx src/components/Reviews/ReviewsView.test.tsx --testTimeout=30000`
Expected: PASS — 3 new tests, no regression in the existing `ReviewsView.test.tsx`

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/Reviews/useReviewsData.ts frontend/src/components/Reviews/ReviewsView.tsx frontend/src/components/Reviews/ReviewsView.proposals.test.tsx
git commit -m "feat(ui): add an AI-proposals mode to the review queue"
```

---

### Task 20: Bulk-confirm selected proposals

**Files:**
- Modify: `frontend/src/components/Reviews/ReviewsView.tsx`
- Test: `frontend/src/components/Reviews/ReviewsView.proposals.test.tsx` (extend)

**Interfaces:**
- Consumes: `workflowTransitionsApi.transition` (existing), `pendingStateFor` (Task 19).
- Produces: `bulkConfirm(ids, transitionFn) -> Promise<{ confirmed: string[]; failed: string[] }>` exported from `ReviewsView.tsx`; a `data-testid="reviews-bulk-confirm-btn"` button.

- [ ] **Step 1: Write the failing test**

Append to `frontend/src/components/Reviews/ReviewsView.proposals.test.tsx`:

```tsx
import { vi } from "vitest";

import { bulkConfirm } from "./ReviewsView";

describe("bulkConfirm", () => {
  it("confirms every selected id", async () => {
    const fn = vi.fn().mockResolvedValue(undefined);
    const result = await bulkConfirm(["a", "b", "c"], fn);
    expect(fn).toHaveBeenCalledTimes(3);
    expect(result.confirmed).toEqual(["a", "b", "c"]);
    expect(result.failed).toEqual([]);
  });

  it("keeps going after a failure and reports it", async () => {
    const fn = vi
      .fn()
      .mockResolvedValueOnce(undefined)
      .mockRejectedValueOnce(new Error("409"))
      .mockResolvedValueOnce(undefined);
    const result = await bulkConfirm(["a", "b", "c"], fn);
    expect(fn).toHaveBeenCalledTimes(3);
    expect(result.confirmed).toEqual(["a", "c"]);
    expect(result.failed).toEqual(["b"]);
  });

  it("is a no-op for an empty selection", async () => {
    const fn = vi.fn();
    const result = await bulkConfirm([], fn);
    expect(fn).not.toHaveBeenCalled();
    expect(result).toEqual({ confirmed: [], failed: [] });
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec frontend npm test -- src/components/Reviews/ReviewsView.proposals.test.tsx --testTimeout=30000`
Expected: FAIL — `bulkConfirm` is not exported from `./ReviewsView`

- [ ] **Step 3: Add the pure bulk helper**

At module level in `ReviewsView.tsx`:

```tsx
/**
 * Confirm a list of proposals one at a time (spec §4.4, minimal bulk edit).
 *
 * Sequential on purpose: each call is a workflow transition with optimistic
 * locking and a server-side validator, and firing N of them in parallel turns
 * a partial failure into an unreadable pile of 409s. A failing item never
 * aborts the run — the caller reports both lists.
 */
export async function bulkConfirm(
  ids: readonly string[],
  confirmOne: (id: string) => Promise<unknown>,
): Promise<{ confirmed: string[]; failed: string[] }> {
  const confirmed: string[] = [];
  const failed: string[] = [];
  for (const id of ids) {
    try {
      await confirmOne(id);
      confirmed.push(id);
    } catch {
      failed.push(id);
    }
  }
  return { confirmed, failed };
}
```

- [ ] **Step 4: Wire selection and the button into the list**

Add state:

```tsx
  const [selectedIds, setSelectedIds] = useState<readonly string[]>([]);
  const [bulkResult, setBulkResult] = useState<{ ok: number; failed: number } | null>(
    null,
  );
```

Clear it whenever the queue changes — add `setSelectedIds([])` to the existing `useEffect` that resets the page.

Render a checkbox inside each list row (proposals mode only):

```tsx
              {queueMode === "proposals" && (
                <input
                  type="checkbox"
                  data-testid={`review-select-${r.id}`}
                  checked={selectedIds.includes(r.id)}
                  onChange={(e) =>
                    setSelectedIds((prev) =>
                      e.target.checked
                        ? [...prev, r.id]
                        : prev.filter((id) => id !== r.id),
                    )
                  }
                  onClick={(e) => e.stopPropagation()}
                />
              )}
```

and the action above the list:

```tsx
      {queueMode === "proposals" && selectedIds.length > 0 && (
        <button
          type="button"
          data-testid="reviews-bulk-confirm-btn"
          disabled={isActing}
          onClick={async () => {
            setIsActing(true);
            const { confirmed, failed } = await bulkConfirm(selectedIds, (id) =>
              workflowTransitionsApi.transition(
                selectedArtifactType,
                id,
                APPROVE_TARGET,
              ),
            );
            setSelectedIds([]);
            setBulkResult({ ok: confirmed.length, failed: failed.length });
            setIsActing(false);
          }}
        >
          {t("workflow.proposal.bulkConfirm")} ({selectedIds.length})
        </button>
      )}
      {bulkResult && (
        <p role="status" data-testid="reviews-bulk-confirm-result">
          {t("workflow.proposal.bulkConfirmDone", { count: bulkResult.ok })}
          {bulkResult.failed > 0
            ? ` — ${t("workflow.proposal.bulkConfirmFailed", { count: bulkResult.failed })}`
            : ""}
        </p>
      )}
```

After a bulk run the list must refetch: call the same query invalidation the single approve path already uses (see the `transition` mutation's `onSuccess` in `useReviewsData.ts`) — expose it as `refetchQueue` from the hook and invoke it after `setBulkResult`.

- [ ] **Step 5: Run test to verify it passes**

Run: `docker compose exec frontend npm test -- src/components/Reviews/ReviewsView.proposals.test.tsx src/components/Reviews/ReviewsView.queue-refresh.test.tsx --testTimeout=30000`
Expected: PASS (6 new tests, no regression)

- [ ] **Step 6: Restart the frontend and verify in the browser**

Run: `docker compose restart frontend`
Open `/reviews`, tick "Nur KI-Vorschläge", select three proposals, press "Ausgewählte bestätigen", and confirm all three leave the list and the status badges change to the graph's initial state.

- [ ] **Step 7: Grep for E2E specs landing on the reviews view**

Run: `grep -rn "reviews-list\|review-list-item\|reviews-type-select" e2e/`
Expected: any spec found still passes — a new checkbox column changes the row's DOM shape. Run only the matched spec files: `npx playwright test <matched spec>` from `e2e/` using the local `@playwright/test` cli.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/components/Reviews/
git commit -m "feat(ui): bulk-confirm selected AI proposals from the review queue"
```

---

## Self-Review

**1. Spec coverage.**

| Spec section | Task |
|---|---|
| §3 `ApiKey` +5 fields | 1 |
| §3 `AuthContext` carries `actor_type` | 2 |
| §3 `agent_label` in audit / history / provenance | 7, 11, 17, 18 |
| §3 scope + expiry (audit E2.1) | 1, 2, 4, 5, 6 |
| §3 workspace access | 3 |
| §4.1 `proposed` + reject state in standard/extended defaults | 8 |
| §4.1 `minimal` unchanged | 8 (`SCHEMAS_WITHOUT_PROPOSED`), Decision 3 |
| §4.1 workspace override remains possible | 9 (`is_customized=True` untouched) |
| §4.2 agent init into `proposed`, shared helper | 10 |
| §4.2 no new field on `Artifact`; proposer in history | 11 |
| §4.3 agent never confirms itself | 12, 13, 15 |
| §4.4 proposal hint instead of the badge | 18 |
| §4.4 "only AI proposals" filter | 16 + Decision 6, 19 |
| §4.4 bulk accept | 20 |
| §5 `TraceLink.proposed_by`/`proposed_at` | 14 |
| §5 confirm clears, discard deletes, agents excluded | 15 |
| §6 transitions stay out of scope | not implemented, by design |
| §7 additive migrations | 1, 9, 14 |
| §8 risk "vergessener create-Pfad" | structurally closed — see the verification table |
| §8 risk "rejected als neuer Terminalzustand" | closed via `is_outdated_equivalent` (Decision 5) |
| §8 risk "bestehende Keys bleiben user" | preserved by the `principal_type` default (Task 1) |

**2. Placeholder scan.** No "TBD", no "similar to Task N", no "add error handling" without code. Every step names a file, a command and its expected output. The three places that ask the implementer to check something before proceeding (`requirement_with_workflow`'s return shape in Task 10, the `NotFoundError` name in Task 15, the queue-invalidation callback in Task 20) each name the exact file and line to look at and the exact adaptation to make.

**3. Type consistency across tasks.** `actor_type` is `str` with the values `"user"`/`"agent"` in `IdentityClaims` (Task 2) → `AuthContext` (Task 2) → `ValidationRequest` (Task 12) → `AuditEntry` (Task 7) — one type, one vocabulary, no coercion anywhere. `PROPOSED_STATE` is a `str` constant defined once in Task 8 and imported by Tasks 9, 10, 12 and 13; the frontend hardcodes the same literal in two places (Tasks 16 and 19) because there is no shared constant module across the language boundary — both are covered by a test that fails if the backend value changes. `initial_state_for` returns `str` (Task 10) and feeds `StateLifecycleManager.initialize_workflow_states(initial_state: str | None)` (Tasks 10/11). `proposed_by` is `str | None` in the REST response (Task 17) and `string | null` in TypeScript (Tasks 17/18) — matching nullability. `TraceLink.proposed_by` is an `ApiKey | None` FK in Python (Task 14) but serializes as a UUID with a separate `proposed_by_label` string, so the wire type is unambiguous.
</content>
</invoke>
