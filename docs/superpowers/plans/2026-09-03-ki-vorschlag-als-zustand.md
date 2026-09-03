# KI-Vorschlag als Zustand Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An API key can act as a first-class *agent* principal (own scope, workspace allow-list, expiry), and everything such an agent creates lands in a reviewable `proposed` workflow state that only a human can confirm or reject.

**Architecture:** Two additive layers on existing seams. (1) `ApiKey` gains five columns; `validate_api_key` lifts them into `IdentityClaims` → `AuthContext.actor_type`/`scope`/`workspace_ids`, so "who is acting" is decided once at the auth layer. (2) The single already-existing choke point `workflow.services.initialize_workflow_states(..., ctx)` — which every `create_X()` service already calls and which already receives `ctx` and currently ignores it — branches to the preset's `proposed` state when the caller is an agent. Confirm/reject are ordinary transitions of the existing state machine; a hard rule in `TransitionValidator` forbids any agent from leaving `proposed`. TraceLinks, which have no `WorkflowItemState`, use two nullable columns instead.

**Tech Stack:** Django 5.2 + DRF (backend), React 18 + TypeScript 5.5 strict (frontend), PostgreSQL 16, pytest / vitest.

**Spec:** docs/superpowers/specs/2026-09-03-ki-vorschlag-als-zustand-design.md

## Global Constraints

- `ApiKey.scope` choices are exactly `"read"` / `"write"`, default `"write"` — the MCP-Modernisierung spec (§6.1) consumes these literal values.
- `ApiKey.principal_type` choices are exactly `"user"` / `"agent"`, default `"user"`. Existing rows keep `"user"` — no retroactive behaviour change.
- `ApiKey.workspace_ids` is a `JSONField(default=list, blank=True)`; an **empty list means "all workspaces of the owning user"** (no restriction).
- `AuthContext.actor_type` values are exactly `"user"` / `"agent"` — byte-identical to `audit.models.AuditEntry.ACTOR_TYPE_USER` / `ACTOR_TYPE_AGENT` (`audit/models.py:106-111`).
- `proposed` is **never** `states[0]`. `WorkflowDefinitionDTO.initial_state` returns `self.states[0]` (`workflow/definition_store.py:94-97`); prepending would make every human-created artifact start as a proposal.
- Workflow state name strings stay byte-identical to the owning entity's `Status.choices` values (`workflow/definition_store.py:213-219`), because `_sync_status_mirror` writes `current_state` verbatim into the entity's `status` column. Hence a per-preset spelling table, never one global `"proposed"` literal.
- The `minimal` rigor preset never proposes — enforced at resolution time via `presets.services.get_preset(workspace_id).preset`, not by the graph alone (see Task 9 / the DEVIATION note below).
- No agent principal may ever execute a transition **out of** `proposed`, regardless of `allowed_roles` (`workflow/transition_validator.py`, Rule 2b).
- Terminal-state marking reuses the existing `state_meta: {"<state>": {"is_outdated_equivalent": True}}` mechanism. No new terminal-state concept.
- `TraceLink.proposed_by` / `proposed_at` are added in the **same migration** as the traceability-semantik spec's `rationale` / `suspect_flagged_at` / `suspect_source_change` (Task 11 — one `AddField` batch, not two migrations).
- Confirming a proposed TraceLink sets both fields to `NULL`; rejecting deletes the link. Only a non-agent principal may do either.
- Workflow transitions by agents stay out of scope — governance for those remains `signature_gate: true` on the transition rule (spec §6).

---

## Spec Critique — findings from verifying against the current tree

Every code reference in the spec was checked against `main`. The four cited locations are correct:
`auth_tenancy/models.py:62` is `class ApiKey`, `:82` is its `user` FK; `audit/writer.py:64` is
`ContextEnricher.enrich(actor_type, ctx)` (the `ACTOR_TYPE_CHOICES` constant itself lives at
`audit/models.py:106-111`); `persistence/models.py:1352` is `class TraceLink`. `ApiKey` today has
only `user`, `name`, `key_hash`, `revoked_at`, `last_used_at` — all five spec fields are genuinely new.

Nine substantive deviations were found. All are resolved inline in the tasks below; none is blocking.

**C1 — `proposed` must not be first in `states` (spec §4.1 JSON is wrong).**
The spec's example is `"states": ["proposed", "draft", "..."]`. But `initial_state` is `states[0]`, and
`definition_store.py:217-219` documents this as a MUST that equals the model field default. As written,
*every* artifact — human-created included — would start in `proposed`, the exact opposite of §4.2's
"Sonst unverändert wie heute". **Resolution:** append `proposed`/`rejected` after the existing states.
Task 7 adds a regression test asserting `initial_state` is unchanged for all 16 presets.

**C2 — the rigor coupling as described only works for `Requirement`.**
Spec §4.1 says `minimal` keeps its graph without `proposed` and calls that "the entire rigor coupling".
But only `Requirement` is provisioned with a rigor-tier preset; the other twelve entity types get
rigor-independent per-entity keys (`need_default`, `adr_default`, … — `provision_workflow_definitions.py:46-64`).
Adding `proposed` to `need_default` would hand it to minimal-rigor workspaces too. **Resolution (DEVIATION,
preserves spec intent):** `initial_state_for()` requires *both* that the resolved graph contains the
proposed state *and* that the workspace tier is not `minimal`, read through the same
`presets.services.get_preset()` call `TransitionValidator._resolve_preset_tier` already uses
(`transition_validator.py:211-237`). Cost: three lines. Benefit: "minimal never proposes" holds for all
thirteen types instead of one.

**C3 — the §8 "risk" of 8-11 duplicated `create_X()` checks does not exist.**
All thirteen services already funnel through one function,
`workflow.services.initialize_workflow_states(item_ids, item_type, workspace_id, ctx)`
(`workflow/services.py:428-457`), which **already accepts `ctx` and currently ignores it**. The shared
helper the spec calls "Pflicht, nicht optional" is therefore a single function body; the thirteen call
sites need zero changes. This is the largest scope reduction in the plan.

**C4 — the status mirror is not written at initialization (spec missed this).**
`_sync_status_mirror` runs only from `perform_transition`/`force_transition` (`lifecycle_manager.py:540`),
never from `initialize_workflow_states`. Meanwhile every `create_X()` sets `status="draft"` on the row
*before* calling workflow init. Initializing at `proposed` without mirroring produces an artifact whose
`status` reads `draft` while its `WorkflowItemState` reads `proposed` — invisible in every list and every
baseline snapshot. **Resolution:** Task 9 mirrors at init, and *only* when the initial state is the
proposed state (no behaviour change for the normal path).

**C5 — with C4 fixed, spec §4.4's list filter needs no work at all.**
`buildStatusFilterOptions(items, activeValue)` (`utils/workflowStatus.ts:156-170`) derives the filter
options from the loaded items' `status` values (GH-453), precisely so it cannot drift from
`PRESET_SCHEMAS`. Once `status` carries `proposed`, the "nur KI-Vorschläge" option appears in all ten
artifact lists for free. Frontend work collapses to one entry in `STATUS_ORDER`, one in
`STATUS_VARIANT_MAP`, plus the detail-view hint and bulk-accept.

**C6 — `rejected` already exists, with unrelated semantics.**
`ccb_approval` has `rejected` (CCB rejection, plus a `rejected → draft` rework path) and `adr_default`
has `Rejected`. Blindly adding a `proposed → rejected` edge merges two meanings. **Resolution:** the
Task 7 table reuses an existing rejected-state where the graph has one and only introduces a new state
where it does not — with the entity's own spelling (`Rejected` for Adr, `Abgelehnt` for Goal/MainGoal).

**C7 — `WorkflowHistoryEntry` is NOT written at initialization (spec §4.2 asserts it is).**
§4.2 says provenance is safe because the history entry "bei der State-Initialisierung ohnehin geschrieben
wird". It is not: `initialize_workflow_states` only does `WorkflowItemState.objects.create(...)`. Without a
fix, nothing on the artifact records which agent proposed it. **Resolution:** Task 9 writes one genesis
`WorkflowHistoryEntry` (`from_state=""`, `to_state=<proposed>`, `transitioned_by=<agent_label>`) inside the
same atomic block — the field is already documented as accepting "AI-agent client identifiers"
(`workflow/models.py:244-245`), and the UI reads it through the existing `/workflow-history/` endpoint.

**C8 — three `AuthContext` rebuild sites silently drop fields.**
`mcp_server/tool_registry.py:849`, `:874` and `:892` reconstruct `AuthContext` field-by-field and already
drop `tenant_name`/`workspace_id`. A new `actor_type` would be dropped identically — for every
*workspace-scoped* MCP call, i.e. exactly the agent traffic this spec exists for. Task 4 fixes all three
with `dataclasses.replace`, which cannot drop a field again.

**C9 — `actor_type` today means "transport", not "identity".**
`application/base.py:187` hardcodes `actor_type="user"`, `mcp_server/tools/base.py:123` hardcodes
`"agent"`. **Decision:** `ServiceBase._audit` switches to `ctx.actor_type` (default `"user"`, so no
behaviour change); `write_mcp_audit` deliberately **keeps its `"agent"` literal**, preserving today's
MCP audit semantics exactly rather than silently downgrading existing agent trails to `"user"` when a
`principal_type="user"` key is used over MCP. Recorded here so the divergence is intentional, not drift.

**Known ceiling (accepted):** `ArchitectureElement`, `GlossaryTerm`, `Icd` and `Diagram` have no `status`
column (they are in `_LIFECYCLE_MIRROR_MODELS`, not `_STATUS_MIRROR_MODELS`). For these four, a proposal is
visible in the `WorkflowStatusEditor` and in the transitions API, but **not** as a list status-filter option.
Marked with a `ponytail:` comment in Task 9; the upgrade path is the `status`/`lifecycle_status` consolidation
owned by the Datenmodell-Konsolidierung spec.

### OFFENE FRAGE (needs a user decision — implement as specced meanwhile)

Spec §5 says confirming a proposed TraceLink sets `proposed_by`/`proposed_at` back to `NULL`. That
**destroys the provenance**: unlike artifacts (whose genesis history entry survives, see C7), a TraceLink
has no history table, so after confirmation nothing on the link records that an agent ever proposed it —
only the generic audit entry for its creation. Is the nulling intended (keep the column meaning strictly
"still open"), or should confirmation instead set a `proposed_confirmed_at` and keep `proposed_by`?
Task 12 implements the spec as written (nulling) behind one service method, so switching to the
provenance-preserving variant later is a single-function change.

---

## File Structure

```
backend/
  auth_tenancy/
    models.py                                   MODIFY  ApiKey: +5 fields
    context.py                                  MODIFY  IdentityClaims/AuthContext: +actor_type,+scope,+workspace_ids
    api_key_scope.py                            CREATE  shared scope/workspace gate predicates
    errors.py                                   MODIFY  (verify) AuthenticationFailed code strings
    services/authentication.py                  MODIFY  validate_api_key/create_api_key/list_api_keys
    services/tenant_context.py                  MODIFY  build_auth_context propagates the 3 new fields
    rest.py                                     MODIFY  API-key scope + workspace gate on the REST path
    migrations/0013_apikey_agent_identity.py    CREATE
    tests/test_api_key_agent_identity.py        CREATE
    tests/test_api_key_scope_gate.py            CREATE
  workflow/
    proposal.py                                 CREATE  PROPOSAL_STATES table + initial_state_for()
    definition_store.py                         MODIFY  PRESET_SCHEMAS: append proposed/rejected
    lifecycle_manager.py                        MODIFY  initialize_workflow_states: proposed branch
    transition_validator.py                     MODIFY  ValidationRequest.actor_type + Rule 2b
    services.py                                 MODIFY  transition(): pass ctx.actor_type
    migrations/0018_seed_proposed_state.py      CREATE
    tests/test_proposal_initial_state.py        CREATE
    tests/test_proposal_agent_cannot_confirm.py CREATE
    tests/test_preset_initial_state_unchanged.py CREATE
  persistence/
    models.py                                   MODIFY  TraceLink: +proposed_by,+proposed_at
    migrations/0070_tracelink_semantics.py      CREATE  (shared with traceability-semantik spec)
  application/
    base.py                                     MODIFY  _audit uses ctx.actor_type
    trace_link_service.py                       MODIFY  create_trace_link stamps proposal; confirm/reject
    tests/test_trace_link_proposal.py           CREATE
  mcp_server/
    tool_registry.py                            MODIFY  3 AuthContext rebuilds -> dataclasses.replace
    tests/test_agent_ctx_propagation.py         CREATE
  rest_api/
    api_key_views.py                            MODIFY  expose the 5 new fields
    views.py                                    MODIFY  TraceLinkViewSet: confirm/reject actions
    serializers.py                              MODIFY  TraceLinkSerializer: proposed_by/proposed_at
    tests/test_api_key_agent_fields.py          CREATE
frontend/src/
  utils/workflowStatus.ts                       MODIFY  STATUS_ORDER: +proposed
  utils/statusBadge.ts                          MODIFY  STATUS_VARIANT_MAP: +proposed
  api/api-keys.ts                               MODIFY  agent fields on create/list
  api/tracelinks.ts                             MODIFY  confirm/reject
  components/UserProfileSettings/ApiKeysSection.tsx        MODIFY  agent-key form
  components/WorkflowStatusEditor/ProposalHint.tsx         CREATE  "Vorschlag von {agent_label}"
  components/Reviews/BulkAcceptBar.tsx                     CREATE  bulk confirm
  i18n/locales/{de,en}.json                     MODIFY  proposal.* keys
```

---

## Task 1: ApiKey agent-identity columns

**Files:**
- Modify: `backend/auth_tenancy/models.py:62-108` (class `ApiKey`)
- Create: `backend/auth_tenancy/migrations/0013_apikey_agent_identity.py`
- Test: `backend/auth_tenancy/tests/test_api_key_agent_identity.py`

**Interfaces:**
- Produces: `ApiKey.principal_type`, `ApiKey.agent_label`, `ApiKey.scope`, `ApiKey.workspace_ids`, `ApiKey.expires_at`; module constants `PRINCIPAL_TYPE_USER = "user"`, `PRINCIPAL_TYPE_AGENT = "agent"`, `SCOPE_READ = "read"`, `SCOPE_WRITE = "write"`; property `ApiKey.is_expired`.

- [ ] **Step 1: Write the failing test**

```python
# backend/auth_tenancy/tests/test_api_key_agent_identity.py
"""ApiKey agent-identity columns (KI-Vorschlag-als-Zustand spec §3)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from auth_tenancy.models import (
    PRINCIPAL_TYPE_AGENT,
    PRINCIPAL_TYPE_USER,
    SCOPE_READ,
    SCOPE_WRITE,
    ApiKey,
)
from persistence.models import Tenant, User


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(name="t1", is_active=True)


@pytest.fixture
def user(db, tenant):
    return User.objects.create(
        email="a@example.com", tenant=tenant, is_active=True
    )


@pytest.mark.django_db
def test_defaults_are_backward_compatible(user, tenant):
    key = ApiKey.unscoped.create(
        user=user, tenant=tenant, name="legacy", key_hash="sha256:" + "a" * 64
    )
    assert key.principal_type == PRINCIPAL_TYPE_USER
    assert key.scope == SCOPE_WRITE
    assert key.agent_label == ""
    assert key.workspace_ids == []
    assert key.expires_at is None
    assert key.is_expired is False


@pytest.mark.django_db
def test_agent_key_stores_label_scope_and_expiry(user, tenant):
    expiry = datetime.now(timezone.utc) + timedelta(days=30)
    key = ApiKey.unscoped.create(
        user=user,
        tenant=tenant,
        name="claude",
        key_hash="sha256:" + "b" * 64,
        principal_type=PRINCIPAL_TYPE_AGENT,
        agent_label="Claude Code — Daniels Workspace",
        scope=SCOPE_READ,
        workspace_ids=["11111111-1111-1111-1111-111111111111"],
        expires_at=expiry,
    )
    key.refresh_from_db()
    assert key.principal_type == PRINCIPAL_TYPE_AGENT
    assert key.agent_label == "Claude Code — Daniels Workspace"
    assert key.scope == SCOPE_READ
    assert key.workspace_ids == ["11111111-1111-1111-1111-111111111111"]
    assert key.is_expired is False


@pytest.mark.django_db
def test_is_expired_true_for_past_timestamp(user, tenant):
    key = ApiKey.unscoped.create(
        user=user,
        tenant=tenant,
        name="stale",
        key_hash="sha256:" + "c" * 64,
        expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
    )
    assert key.is_expired is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec backend pytest auth_tenancy/tests/test_api_key_agent_identity.py -v`
Expected: FAIL with `ImportError: cannot import name 'PRINCIPAL_TYPE_AGENT' from 'auth_tenancy.models'`

- [ ] **Step 3: Write minimal implementation**

Add above `class ApiKey` in `backend/auth_tenancy/models.py` (after `MAX_ACTIVE_API_KEYS_PER_USER`):

```python
# Principal identity of an API key (KI-Vorschlag-als-Zustand spec §3). "user"
# keeps the historical behaviour — the key acts AS its owning human. "agent"
# makes the key a distinct principal whose writes land in the ``proposed``
# workflow state (see workflow/proposal.py). Values are byte-identical to
# audit.models.AuditEntry.ACTOR_TYPE_USER / ACTOR_TYPE_AGENT, because
# AuthContext.actor_type is handed straight to the audit writer.
PRINCIPAL_TYPE_USER = "user"
PRINCIPAL_TYPE_AGENT = "agent"
PRINCIPAL_TYPE_CHOICES = (
    (PRINCIPAL_TYPE_USER, "User"),
    (PRINCIPAL_TYPE_AGENT, "Agent"),
)

# Coarse capability scope (audit finding E2.1). "write" is the default so
# existing keys are unaffected. The MCP-Modernisierung spec (§6.1) filters and
# refuses write tools on these exact literals — do not rename them.
SCOPE_READ = "read"
SCOPE_WRITE = "write"
SCOPE_CHOICES = (
    (SCOPE_READ, "Read"),
    (SCOPE_WRITE, "Write"),
)
```

Add the fields inside `class ApiKey`, directly after `last_used_at`:

```python
    principal_type = models.CharField(
        max_length=16,
        choices=PRINCIPAL_TYPE_CHOICES,
        default=PRINCIPAL_TYPE_USER,
    )
    #: Display name used everywhere the owning user's name would otherwise
    #: appear (provenance hints, audit view, WorkflowHistoryEntry actor column).
    agent_label = models.CharField(max_length=255, blank=True, default="")
    scope = models.CharField(
        max_length=16, choices=SCOPE_CHOICES, default=SCOPE_WRITE
    )
    #: Workspace UUIDs (as strings) this key may act in. EMPTY LIST MEANS ALL
    #: workspaces of the owning user — the historical, unrestricted behaviour.
    workspace_ids = models.JSONField(default=list, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
```

Add the property after `is_active`:

```python
    @property
    def is_expired(self) -> bool:
        """Return whether the key carries an expiry that has already passed."""
        if self.expires_at is None:
            return False
        from datetime import datetime, timezone as _tz

        return self.expires_at <= datetime.now(_tz.utc)
```

- [ ] **Step 4: Generate the migration**

Run: `docker compose exec backend python manage.py makemigrations auth_tenancy --name apikey_agent_identity`
Expected: creates `auth_tenancy/migrations/0013_apikey_agent_identity.py` with five `AddField` operations, depending on `0012_refreshtoken`.

- [ ] **Step 5: Run test to verify it passes**

Run: `docker compose exec backend pytest auth_tenancy/tests/test_api_key_agent_identity.py -v --create-db`
Expected: PASS (3 tests)

- [ ] **Step 6: Commit**

```bash
git add backend/auth_tenancy/models.py backend/auth_tenancy/migrations/0013_apikey_agent_identity.py backend/auth_tenancy/tests/test_api_key_agent_identity.py
git commit -m "feat(auth): add agent-identity columns to ApiKey"
```

---

## Task 2: Carry principal identity into IdentityClaims and AuthContext

**Files:**
- Modify: `backend/auth_tenancy/context.py:43-65` (`IdentityClaims`), `:87-141` (`AuthContext`)
- Modify: `backend/auth_tenancy/services/authentication.py:482-545` (`validate_api_key`)
- Modify: `backend/auth_tenancy/services/tenant_context.py:56-84` (`build_auth_context`)
- Test: `backend/auth_tenancy/tests/test_api_key_agent_identity.py` (extend)

**Interfaces:**
- Consumes: `ApiKey.principal_type` / `.scope` / `.workspace_ids` / `.agent_label` / `.is_expired` (Task 1).
- Produces: `IdentityClaims.actor_type: str`, `.scope: str`, `.workspace_ids: tuple[str, ...]`, `.agent_label: str`; `AuthContext.actor_type: str = "user"`, `.scope: str = "write"`, `.workspace_ids: tuple[str, ...] = ()`, `.agent_label: str = ""`; `AuthContext.is_agent` property; `AuthenticationFailed("api_key_expired")`.

- [ ] **Step 1: Write the failing test**

Append to `backend/auth_tenancy/tests/test_api_key_agent_identity.py`:

```python
from auth_tenancy.errors import AuthenticationFailed
from auth_tenancy.services.authentication import (
    AuthenticationService,
    generate_api_key_plaintext,
    hash_api_key,
)


def _make_key(user, tenant, **kwargs) -> str:
    plaintext = generate_api_key_plaintext()
    ApiKey.unscoped.create(
        user=user, tenant=tenant, name="k", key_hash=hash_api_key(plaintext), **kwargs
    )
    return plaintext


@pytest.mark.django_db
def test_validate_api_key_marks_agent_principal(user, tenant):
    plaintext = _make_key(
        user,
        tenant,
        principal_type=PRINCIPAL_TYPE_AGENT,
        agent_label="Claude Code",
        scope=SCOPE_READ,
        workspace_ids=["11111111-1111-1111-1111-111111111111"],
    )
    claims = AuthenticationService().validate_api_key(plaintext)
    assert claims.actor_type == "agent"
    assert claims.scope == "read"
    assert claims.agent_label == "Claude Code"
    assert claims.workspace_ids == ("11111111-1111-1111-1111-111111111111",)


@pytest.mark.django_db
def test_validate_api_key_user_principal_defaults(user, tenant):
    plaintext = _make_key(user, tenant)
    claims = AuthenticationService().validate_api_key(plaintext)
    assert claims.actor_type == "user"
    assert claims.scope == "write"
    assert claims.workspace_ids == ()


@pytest.mark.django_db
def test_expired_key_is_rejected(user, tenant):
    plaintext = _make_key(
        user, tenant, expires_at=datetime.now(timezone.utc) - timedelta(seconds=1)
    )
    with pytest.raises(AuthenticationFailed) as exc:
        AuthenticationService().validate_api_key(plaintext)
    assert exc.value.code == "api_key_expired"


@pytest.mark.django_db
def test_build_auth_context_propagates_agent_identity(user, tenant):
    from auth_tenancy.services.tenant_context import TenantContextService

    plaintext = _make_key(
        user, tenant, principal_type=PRINCIPAL_TYPE_AGENT, agent_label="Bot"
    )
    svc = TenantContextService()
    claims = AuthenticationService().validate_api_key(plaintext)
    tctx = svc.resolve_tenant_context(claims)
    ctx = svc.build_auth_context(claims, tctx, ("editor",))
    assert ctx.actor_type == "agent"
    assert ctx.agent_label == "Bot"
    assert ctx.is_agent is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec backend pytest auth_tenancy/tests/test_api_key_agent_identity.py -k "agent_principal or expired_key or propagates" -v`
Expected: FAIL with `AttributeError: 'IdentityClaims' object has no attribute 'actor_type'`

- [ ] **Step 3: Extend the dataclasses**

In `backend/auth_tenancy/context.py`, append to `IdentityClaims` (all fields defaulted, so
positional construction stays valid):

```python
    #: "user" | "agent" — byte-identical to audit.models.AuditEntry
    #: ACTOR_TYPE_USER / ACTOR_TYPE_AGENT. Decided by ApiKey.principal_type;
    #: Bearer tokens are always "user".
    actor_type: str = "user"
    #: "read" | "write" — coarse capability scope of an API key (E2.1).
    scope: str = "write"
    #: Workspace UUID strings this credential may act in. EMPTY = unrestricted.
    workspace_ids: tuple[str, ...] = ()
    #: Display name of an agent principal; empty for human principals.
    agent_label: str = ""
```

Append the same four fields to `AuthContext` (after `workspace_id`), plus:

```python
    @property
    def is_agent(self) -> bool:
        """True when this request is made by an agent principal, not a human.

        The single predicate the workflow-proposal branch and the
        "agent never confirms itself" rule both key off. Never infer
        agent-ness from the transport (REST vs MCP) — an MCP call made with
        a ``principal_type="user"`` key is a human acting through a tool.
        """
        return self.actor_type == "agent"
```

And in `AuthContext.system(...)`, leave `actor_type` at its `"user"` default (a Celery task is
not an agent principal; it must never be blocked by the proposal rules).

- [ ] **Step 4: Populate the fields at the two build sites**

In `backend/auth_tenancy/services/authentication.py::validate_api_key`, insert an expiry check
directly after the `revoked_at` check (~line 522):

```python
        if api_key.is_expired:
            raise AuthenticationFailed("api_key_expired")
```

and extend the returned claims:

```python
        return IdentityClaims(
            user_id=api_key.user_id,
            tenant_id=api_key.user.tenant_id,
            roles=(),  # roles are resolved by AuthorizationService from UserRole.
            auth_method=AuthMethod.API_KEY,
            api_key_id=api_key.id,
            actor_type=api_key.principal_type,
            scope=api_key.scope,
            workspace_ids=tuple(str(w) for w in (api_key.workspace_ids or ())),
            agent_label=api_key.agent_label,
        )
```

In `backend/auth_tenancy/services/tenant_context.py::build_auth_context`, extend the returned
`AuthContext(...)` with:

```python
            actor_type=claims.actor_type,
            scope=claims.scope,
            workspace_ids=claims.workspace_ids,
            agent_label=claims.agent_label,
```

- [ ] **Step 5: Run test to verify it passes**

Run: `docker compose exec backend pytest auth_tenancy/tests/test_api_key_agent_identity.py -v`
Expected: PASS (7 tests)

- [ ] **Step 6: Run the auth regression suite**

Run: `docker compose exec backend pytest auth_tenancy/ -q`
Expected: no new failures versus the pre-change baseline.

- [ ] **Step 7: Commit**

```bash
git add backend/auth_tenancy/context.py backend/auth_tenancy/services/authentication.py backend/auth_tenancy/services/tenant_context.py backend/auth_tenancy/tests/test_api_key_agent_identity.py
git commit -m "feat(auth): resolve agent principal identity at the auth layer"
```

---

## Task 3: Scope and workspace allow-list enforcement

**Files:**
- Create: `backend/auth_tenancy/api_key_scope.py`
- Modify: `backend/auth_tenancy/rest.py:200-215` (after `build_auth_context`)
- Test: `backend/auth_tenancy/tests/test_api_key_scope_gate.py`

**Interfaces:**
- Consumes: `AuthContext.scope`, `AuthContext.workspace_ids`, `AuthContext.auth_method` (Task 2).
- Produces: `is_write_method(method: str) -> bool`, `scope_denies_write(ctx: AuthContext, method: str) -> bool`, `workspace_denied(ctx: AuthContext, workspace_id: str | None) -> bool`. The MCP-Modernisierung spec §6.1 imports `scope_denies_write` rather than reimplementing it.

- [ ] **Step 1: Write the failing test**

```python
# backend/auth_tenancy/tests/test_api_key_scope_gate.py
"""ApiKey scope + workspace allow-list gates (spec §3)."""
from __future__ import annotations

from uuid import uuid4

from auth_tenancy.api_key_scope import (
    is_write_method,
    scope_denies_write,
    workspace_denied,
)
from auth_tenancy.context import AuthContext, AuthMethod

WS_A = str(uuid4())
WS_B = str(uuid4())


def _ctx(**kwargs) -> AuthContext:
    base = dict(
        user_id=uuid4(),
        tenant_id=uuid4(),
        active_roles=("editor",),
        auth_method=AuthMethod.API_KEY,
    )
    base.update(kwargs)
    return AuthContext(**base)


def test_is_write_method_classifies_http_verbs():
    assert is_write_method("POST") is True
    assert is_write_method("patch") is True
    assert is_write_method("PUT") is True
    assert is_write_method("DELETE") is True
    assert is_write_method("GET") is False
    assert is_write_method("HEAD") is False
    assert is_write_method("OPTIONS") is False


def test_read_scope_denies_write_methods():
    ctx = _ctx(scope="read")
    assert scope_denies_write(ctx, "POST") is True
    assert scope_denies_write(ctx, "GET") is False


def test_write_scope_allows_everything():
    ctx = _ctx(scope="write")
    assert scope_denies_write(ctx, "DELETE") is False


def test_bearer_token_is_never_scope_limited():
    """Scope lives on the API key; a Bearer session must not inherit it."""
    ctx = _ctx(scope="read", auth_method=AuthMethod.BEARER_TOKEN)
    assert scope_denies_write(ctx, "POST") is False


def test_empty_workspace_ids_means_unrestricted():
    ctx = _ctx(workspace_ids=())
    assert workspace_denied(ctx, WS_A) is False
    assert workspace_denied(ctx, None) is False


def test_workspace_allow_list_blocks_foreign_workspace():
    ctx = _ctx(workspace_ids=(WS_A,))
    assert workspace_denied(ctx, WS_A) is False
    assert workspace_denied(ctx, WS_B) is True


def test_scoped_key_without_workspace_target_is_allowed():
    """A workspace-less request (e.g. /api-keys/) is not workspace traffic."""
    ctx = _ctx(workspace_ids=(WS_A,))
    assert workspace_denied(ctx, None) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec backend pytest auth_tenancy/tests/test_api_key_scope_gate.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'auth_tenancy.api_key_scope'`

- [ ] **Step 3: Write minimal implementation**

```python
# backend/auth_tenancy/api_key_scope.py
"""API-key capability gates: coarse scope and workspace allow-list (spec §3).

Both predicates are pure functions over an already-resolved
:class:`~auth_tenancy.context.AuthContext`, so REST (``auth_tenancy.rest``) and
MCP (``mcp_server.tool_registry``, MCP-Modernisierung spec §6.1) enforce one
implementation instead of two drifting copies.

Fail-closed on the write path, permissive on the read path: an unknown HTTP
method is treated as a write.
"""
from __future__ import annotations

from .context import AuthContext, AuthMethod
from .models import SCOPE_READ

#: HTTP methods that never mutate state. Anything not listed counts as a write.
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})


def is_write_method(method: str) -> bool:
    """Return whether *method* is a state-mutating HTTP verb."""
    return (method or "").upper() not in _SAFE_METHODS


def scope_denies_write(ctx: AuthContext, method: str) -> bool:
    """Return True when a ``scope="read"`` API key attempts a write.

    Only applies to API-key auth: ``scope`` is a property of the key, and a
    Bearer session of the same user must keep its full role-derived rights.
    """
    if ctx.auth_method != AuthMethod.API_KEY:
        return False
    if ctx.scope != SCOPE_READ:
        return False
    return is_write_method(method)


def workspace_denied(ctx: AuthContext, workspace_id: str | None) -> bool:
    """Return True when the key declares an allow-list that excludes *workspace_id*.

    An empty ``workspace_ids`` means "every workspace of the owning user" —
    the historical, unrestricted behaviour. A request that targets no specific
    workspace (``workspace_id is None``) is not workspace traffic and is never
    blocked here; its authorization is the ordinary role check.
    """
    if not ctx.workspace_ids:
        return False
    if workspace_id is None:
        return False
    return str(workspace_id) not in set(ctx.workspace_ids)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec backend pytest auth_tenancy/tests/test_api_key_scope_gate.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Wire the gate into the REST authentication path**

In `backend/auth_tenancy/rest.py`, immediately after `auth_context = self._tenancy.build_auth_context(...)`
(~line 208) and before the context is returned:

```python
            from rest_framework.exceptions import PermissionDenied

            from .api_key_scope import scope_denies_write, workspace_denied

            if scope_denies_write(auth_context, request.method):
                raise PermissionDenied(
                    "This API key has read-only scope and cannot perform writes."
                )
            requested_workspace = (
                request.GET.get("workspace_id")
                or (request.data.get("workspace_id") if hasattr(request, "data") else None)
            )
            if workspace_denied(auth_context, requested_workspace):
                raise PermissionDenied(
                    "This API key is not authorised for the requested workspace."
                )
```

- [ ] **Step 6: Verify the wiring with a request-level test**

Append to `backend/auth_tenancy/tests/test_api_key_scope_gate.py`:

```python
import pytest
from rest_framework.test import APIClient

from auth_tenancy.models import SCOPE_READ, ApiKey
from auth_tenancy.services.authentication import (
    generate_api_key_plaintext,
    hash_api_key,
)
from persistence.models import Tenant, User


@pytest.mark.django_db
def test_read_scope_key_gets_403_on_post():
    tenant = Tenant.objects.create(name="t", is_active=True)
    user = User.objects.create(email="s@example.com", tenant=tenant, is_active=True)
    plaintext = generate_api_key_plaintext()
    ApiKey.unscoped.create(
        user=user,
        tenant=tenant,
        name="ro",
        key_hash=hash_api_key(plaintext),
        scope=SCOPE_READ,
    )
    client = APIClient()
    resp = client.post(
        "/api/v1/api-keys/", {"name": "x"}, format="json", HTTP_X_API_KEY=plaintext
    )
    assert resp.status_code == 403
```

Run: `docker compose exec backend pytest auth_tenancy/tests/test_api_key_scope_gate.py -v --create-db`
Expected: PASS (8 tests)

- [ ] **Step 7: Commit**

```bash
git add backend/auth_tenancy/api_key_scope.py backend/auth_tenancy/rest.py backend/auth_tenancy/tests/test_api_key_scope_gate.py
git commit -m "feat(auth): enforce API-key read scope and workspace allow-list"
```

---

## Task 4: Stop dropping identity fields when MCP rebuilds AuthContext

**Files:**
- Modify: `backend/mcp_server/tool_registry.py:849-856`, `:874-881`, `:892-899`
- Test: `backend/mcp_server/tests/test_agent_ctx_propagation.py`

**Interfaces:**
- Consumes: `AuthContext.actor_type` / `.agent_label` / `.scope` / `.workspace_ids` (Task 2).
- Produces: no new API — a behavioural guarantee that role resolution preserves every `AuthContext` field.

- [ ] **Step 1: Write the failing test**

```python
# backend/mcp_server/tests/test_agent_ctx_propagation.py
"""Role resolution must not drop AuthContext identity fields (spec §3, C8).

``_resolve_roles`` rebuilds AuthContext field-by-field and already silently
dropped ``tenant_name``/``workspace_id``. A dropped ``actor_type`` would make
every workspace-scoped MCP call look like a human — i.e. exactly the traffic
the proposal mechanism exists for.
"""
from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from auth_tenancy.context import AuthContext, AuthMethod


def _agent_ctx(workspace_id=None) -> AuthContext:
    return AuthContext(
        user_id=uuid4(),
        tenant_id=uuid4(),
        active_roles=(),
        auth_method=AuthMethod.API_KEY,
        api_key_id=uuid4(),
        tenant_name="Acme",
        workspace_id=workspace_id,
        actor_type="agent",
        scope="write",
        workspace_ids=(),
        agent_label="Claude Code",
    )


@pytest.mark.django_db
def test_resolve_roles_without_workspace_preserves_agent_identity():
    from mcp_server.tool_registry import TenantToolRegistry

    registry = TenantToolRegistry()
    registry._authz_service = MagicMock()
    registry._authz_service.active_roles_across_workspaces.return_value = ("editor",)

    out = registry._resolve_roles(_agent_ctx(), None)

    assert out.active_roles == ("editor",)
    assert out.actor_type == "agent"
    assert out.agent_label == "Claude Code"
    assert out.tenant_name == "Acme"


@pytest.mark.django_db
def test_resolve_roles_with_workspace_preserves_agent_identity():
    from mcp_server.tool_registry import TenantToolRegistry

    ws = uuid4()
    registry = TenantToolRegistry()
    registry._authz_service = MagicMock()
    registry._authz_service.active_roles_for.return_value = ("editor",)

    out = registry._resolve_roles(_agent_ctx(), str(ws))

    assert out.actor_type == "agent"
    assert out.agent_label == "Claude Code"
    assert out.tenant_name == "Acme"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec backend pytest mcp_server/tests/test_agent_ctx_propagation.py -v`
Expected: FAIL with `AssertionError: assert 'user' == 'agent'`

- [ ] **Step 3: Replace field-by-field rebuilds with `dataclasses.replace`**

Add `from dataclasses import replace` to the imports of `backend/mcp_server/tool_registry.py`.

Replace the two rebuilds inside `_resolve_roles` (`:874-881` and `:892-899`) with:

```python
                return replace(ctx, active_roles=roles)
```

and

```python
        return replace(ctx, active_roles=roles)
```

respectively. `replace` copies every field including future ones, so this class of drop cannot
recur. Leave the initial construction at `:849` as an explicit constructor call, but add the
identity fields there so the partial context is correct from the start:

```python
        ctx = AuthContext(
            user_id=claims.user_id,
            tenant_id=claims.tenant_id,
            active_roles=(),  # resolved in step 2
            auth_method=AuthMethod.API_KEY,
            api_key_id=claims.api_key_id,
            actor_type=claims.actor_type,
            scope=claims.scope,
            workspace_ids=claims.workspace_ids,
            agent_label=claims.agent_label,
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec backend pytest mcp_server/tests/test_agent_ctx_propagation.py -v --create-db`
Expected: PASS (2 tests)

- [ ] **Step 5: Run the MCP auth regression suite**

Run: `docker compose exec backend pytest mcp_server/tests/ -q -k "auth or tenant_context or registry"`
Expected: no new failures.

- [ ] **Step 6: Commit**

```bash
git add backend/mcp_server/tool_registry.py backend/mcp_server/tests/test_agent_ctx_propagation.py
git commit -m "fix(mcp): preserve AuthContext identity fields across role resolution"
```

---

## Task 5: Audit entries record the resolved actor type

**Files:**
- Modify: `backend/application/base.py:184-190`
- Test: `backend/application/tests/test_audit_actor_type.py`

**Interfaces:**
- Consumes: `AuthContext.actor_type` (Task 2).
- Produces: audit entries whose `actor_type` reflects the credential, not the transport.

Note (decision C9): `mcp_server/tools/base.py::write_mcp_audit` deliberately keeps its `"agent"`
literal. Changing it would retroactively relabel existing MCP trails as `"user"` whenever a
`principal_type="user"` key is used — a silent semantic change to an append-only audit log.

- [ ] **Step 1: Write the failing test**

```python
# backend/application/tests/test_audit_actor_type.py
"""ServiceBase._audit records the resolved principal type (spec §3, C9)."""
from __future__ import annotations

from unittest.mock import patch
from uuid import uuid4

from auth_tenancy.context import AuthContext, AuthMethod
from application.base import ServiceBase


def _ctx(actor_type: str) -> AuthContext:
    return AuthContext(
        user_id=uuid4(),
        tenant_id=uuid4(),
        active_roles=("editor",),
        auth_method=AuthMethod.API_KEY,
        actor_type=actor_type,
    )


def test_audit_uses_agent_actor_type_for_agent_ctx():
    with patch("audit.services.log_write") as log_write:
        ServiceBase._audit(
            ctx=_ctx("agent"),
            operation="create",
            entity_type="Requirement",
            entity_id=uuid4(),
        )
    assert log_write.call_args.kwargs["actor_type"] == "agent"


def test_audit_defaults_to_user_actor_type():
    with patch("audit.services.log_write") as log_write:
        ServiceBase._audit(
            ctx=_ctx("user"),
            operation="create",
            entity_type="Requirement",
            entity_id=uuid4(),
        )
    assert log_write.call_args.kwargs["actor_type"] == "user"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec backend pytest application/tests/test_audit_actor_type.py -v`
Expected: FAIL with `AssertionError: assert 'user' == 'agent'`

- [ ] **Step 3: Write minimal implementation**

In `backend/application/base.py`, change the hardcoded literal (line ~187):

```python
                actor_type=ctx.actor_type,
```

and extend the docstring of `_audit` with:

```
        The actor type follows the *credential*, not the transport: an API key
        with ``principal_type="agent"`` logs ``"agent"`` even over REST, and a
        human's Bearer session logs ``"user"`` even when it drives an agent-ish
        tool. ``AuthContext.actor_type`` defaults to ``"user"``, so this is a
        no-op for every pre-existing caller.
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec backend pytest application/tests/test_audit_actor_type.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/application/base.py backend/application/tests/test_audit_actor_type.py
git commit -m "feat(audit): derive actor_type from the resolved principal"
```

---

## Task 6: Expose the agent fields through the API-key REST surface

**Files:**
- Modify: `backend/auth_tenancy/services/authentication.py:549-627` (`create_api_key`, `list_api_keys`)
- Modify: `backend/rest_api/api_key_views.py` (`create`, `list`)
- Test: `backend/rest_api/tests/test_api_key_agent_fields.py`

**Interfaces:**
- Consumes: `ApiKey` columns (Task 1), `PRINCIPAL_TYPE_CHOICES`, `SCOPE_CHOICES`.
- Produces: `ApiKeyCreationResult` unchanged; `create_api_key(*, user_id, tenant_id, name, principal_type="user", agent_label="", scope="write", workspace_ids=None, expires_at=None)`; `list_api_keys` dicts gain `principal_type`, `agent_label`, `scope`, `workspace_ids`, `expires_at`.

- [ ] **Step 1: Write the failing test**

```python
# backend/rest_api/tests/test_api_key_agent_fields.py
"""POST/GET /api/v1/api-keys/ carry the agent-identity fields (spec §3)."""
from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from persistence.models import Tenant, User


@pytest.fixture
def authed(db):
    tenant = Tenant.objects.create(name="t", is_active=True)
    user = User.objects.create(email="k@example.com", tenant=tenant, is_active=True)
    from auth_tenancy.models import ROLE_ADMIN, UserRole
    from persistence.models import Workspace

    ws = Workspace.objects.create(name="w", tenant=tenant)
    UserRole.objects.create(user=user, workspace_id=ws.id, role=ROLE_ADMIN, tenant=tenant)
    from auth_tenancy.jwt_tokens import issue_token

    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {issue_token(user)}")
    return client


@pytest.mark.django_db
def test_create_agent_key_persists_identity_fields(authed):
    resp = authed.post(
        "/api/v1/api-keys/",
        {
            "name": "claude",
            "principal_type": "agent",
            "agent_label": "Claude Code",
            "scope": "read",
            "expires_at": "2027-01-01T00:00:00Z",
        },
        format="json",
    )
    assert resp.status_code == 201
    assert resp.data["principal_type"] == "agent"
    assert resp.data["agent_label"] == "Claude Code"
    assert resp.data["scope"] == "read"

    listing = authed.get("/api/v1/api-keys/")
    row = listing.data[0]
    assert row["principal_type"] == "agent"
    assert row["scope"] == "read"
    assert row["agent_label"] == "Claude Code"
    assert row["expires_at"].startswith("2027-01-01")


@pytest.mark.django_db
def test_create_rejects_unknown_principal_type(authed):
    resp = authed.post(
        "/api/v1/api-keys/", {"name": "x", "principal_type": "root"}, format="json"
    )
    assert resp.status_code == 400
    assert resp.data["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.django_db
def test_create_defaults_to_user_principal(authed):
    resp = authed.post("/api/v1/api-keys/", {"name": "plain"}, format="json")
    assert resp.status_code == 201
    assert resp.data["principal_type"] == "user"
    assert resp.data["scope"] == "write"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec backend pytest rest_api/tests/test_api_key_agent_fields.py -v --create-db`
Expected: FAIL with `KeyError: 'principal_type'`

- [ ] **Step 3: Extend the service**

In `backend/auth_tenancy/services/authentication.py`, change the `create_api_key` signature and
the `ApiKey.unscoped.create(...)` call:

```python
    def create_api_key(
        self,
        *,
        user_id: UUID,
        tenant_id: UUID,
        name: str,
        principal_type: str = PRINCIPAL_TYPE_USER,
        agent_label: str = "",
        scope: str = SCOPE_WRITE,
        workspace_ids: list[str] | None = None,
        expires_at: datetime | None = None,
    ) -> ApiKeyCreationResult:
```

Validate the two enums before the transaction (fail fast, no partial write):

```python
        if principal_type not in dict(PRINCIPAL_TYPE_CHOICES):
            raise ValueError(
                f"principal_type must be one of {sorted(dict(PRINCIPAL_TYPE_CHOICES))}."
            )
        if scope not in dict(SCOPE_CHOICES):
            raise ValueError(f"scope must be one of {sorted(dict(SCOPE_CHOICES))}.")
```

and pass the new columns through:

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

Return the identity alongside the plaintext by adding four fields to `ApiKeyCreationResult`
(`authentication.py:50-59`), each defaulted so existing constructions stay valid:

```python
    principal_type: str = PRINCIPAL_TYPE_USER
    agent_label: str = ""
    scope: str = SCOPE_WRITE
    expires_at: "datetime | None" = None
```

and populate them in the `return ApiKeyCreationResult(...)`.

Extend each dict in `list_api_keys`:

```python
                "principal_type": k.principal_type,
                "agent_label": k.agent_label,
                "scope": k.scope,
                "workspace_ids": list(k.workspace_ids or []),
                "expires_at": k.expires_at.isoformat() if k.expires_at else None,
```

Add `PRINCIPAL_TYPE_CHOICES`, `PRINCIPAL_TYPE_USER`, `SCOPE_CHOICES`, `SCOPE_WRITE` to the module's
`from ..models import ApiKey` import.

- [ ] **Step 4: Extend the ViewSet**

In `backend/rest_api/api_key_views.py::create`, after the existing `name` validation:

```python
        from django.utils.dateparse import parse_datetime

        principal_type = request.data.get("principal_type", "user")
        agent_label = request.data.get("agent_label", "") or ""
        scope = request.data.get("scope", "write")
        workspace_ids = request.data.get("workspace_ids") or []
        if not isinstance(workspace_ids, list):
            return Response(
                build_error_response(
                    code="VALIDATION_ERROR",
                    message="Field 'workspace_ids' must be a list of workspace UUIDs.",
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
        expires_raw = request.data.get("expires_at")
        expires_at = parse_datetime(expires_raw) if expires_raw else None
        if expires_raw and expires_at is None:
            return Response(
                build_error_response(
                    code="VALIDATION_ERROR",
                    message="Field 'expires_at' must be an ISO-8601 timestamp.",
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
```

Pass them into `self._authn.create_api_key(...)` — the existing `except ValueError` branch already
turns the enum validation from Step 3 into the expected 400 — and extend the 201 body:

```python
                "principal_type": result.principal_type,
                "agent_label": result.agent_label,
                "scope": result.scope,
                "expires_at": result.expires_at.isoformat() if result.expires_at else None,
```

- [ ] **Step 5: Run test to verify it passes**

Run: `docker compose exec backend pytest rest_api/tests/test_api_key_agent_fields.py -v --create-db`
Expected: PASS (3 tests)

- [ ] **Step 6: Commit**

```bash
git add backend/auth_tenancy/services/authentication.py backend/rest_api/api_key_views.py backend/rest_api/tests/test_api_key_agent_fields.py
git commit -m "feat(api): expose agent identity on the API-key endpoints"
```

---

## Task 7: Add `proposed` / rejected states to the preset defaults

**Files:**
- Create: `backend/workflow/proposal.py`
- Modify: `backend/workflow/definition_store.py:597-830` (`PRESET_SCHEMAS`)
- Test: `backend/workflow/tests/test_preset_initial_state_unchanged.py`

**Interfaces:**
- Produces: `PROPOSAL_STATES: dict[str, ProposalStates]` and `@dataclass(frozen=True) ProposalStates(proposed: str, rejected: str, confirm_target: str, rejected_is_new: bool)`; `proposal_states_for_preset(preset: str) -> ProposalStates | None`; `apply_proposal_states(schema: dict, states: ProposalStates) -> dict`.

**Per-preset spelling table** (states are byte-identical to each entity's `Status.choices`; `confirm_target` is that preset's pre-existing `states[0]`):

| preset | proposed | rejected | confirm target | rejected is new |
|---|---|---|---|---|
| `minimal` | — (rigor gate) | — | — | — |
| `interview_default` | — (a session is not a proposable artifact) | — | — | — |
| `standard` | `proposed` | `rejected` | `draft` | yes |
| `extended` | `proposed` | `rejected` | `draft` | yes |
| `need_default` | `proposed` | `rejected` | `draft` | yes |
| `testcase_default` | `proposed` | `rejected` | `draft` | yes |
| `architecture_default` | `proposed` | `rejected` | `draft` | yes |
| `icd_default` | `proposed` | `rejected` | `draft` | yes |
| `diagram_default` | `proposed` | `rejected` | `draft` | yes |
| `glossary_term_default` | `proposed` | `rejected` | `draft` | yes |
| `ccb_approval` | `proposed` | `rejected` | `draft` | **no — reuse** |
| `adr_default` | `Proposed` | `Rejected` | `Draft` | **no — reuse** |
| `risk_default` | `Proposed` | `Rejected` | `Identified` | yes |
| `issue_default` | `Proposed` | `Rejected` | `Open` | yes |
| `goal_default` | `Vorgeschlagen` | `Abgelehnt` | `Entwurf` | yes |
| `main_goal_default` | `Vorgeschlagen` | `Abgelehnt` | `Entwurf` | yes |

- [ ] **Step 1: Write the failing test**

```python
# backend/workflow/tests/test_preset_initial_state_unchanged.py
"""The proposal states must never displace a preset's initial state (C1).

``WorkflowDefinitionDTO.initial_state`` is ``states[0]``
(definition_store.py:94-97) and definition_store.py:217-219 requires it to equal
the entity's model-field default. Prepending "proposed" would start every
human-created artifact as a proposal.
"""
from __future__ import annotations

from workflow.definition_store import PRESET_SCHEMAS
from workflow.proposal import PROPOSAL_STATES, proposal_states_for_preset

#: The initial state each preset had before the proposal states were added.
EXPECTED_INITIAL_STATE = {
    "minimal": "draft",
    "standard": "draft",
    "extended": "draft",
    "ccb_approval": "draft",
    "need_default": "draft",
    "adr_default": "Draft",
    "risk_default": "Identified",
    "issue_default": "Open",
    "interview_default": "in_progress",
    "testcase_default": "draft",
    "architecture_default": "draft",
    "icd_default": "draft",
    "diagram_default": "draft",
    "glossary_term_default": "draft",
    "goal_default": "Entwurf",
    "main_goal_default": "Entwurf",
}


def test_every_preset_keeps_its_initial_state():
    for preset, expected in EXPECTED_INITIAL_STATE.items():
        assert PRESET_SCHEMAS[preset]["states"][0] == expected, preset


def test_table_covers_every_preset_exactly_once():
    assert set(PROPOSAL_STATES) | {"minimal", "interview_default"} == set(PRESET_SCHEMAS)


def test_minimal_and_interview_have_no_proposal_states():
    for preset in ("minimal", "interview_default"):
        assert proposal_states_for_preset(preset) is None
        assert "proposed" not in PRESET_SCHEMAS[preset]["states"]
        assert "Proposed" not in PRESET_SCHEMAS[preset]["states"]


def test_proposed_state_and_two_transitions_exist():
    for preset, states in PROPOSAL_STATES.items():
        schema = PRESET_SCHEMAS[preset]
        assert states.proposed in schema["states"], preset
        assert states.rejected in schema["states"], preset
        edges = {
            (t["from_state"], t["to_state"]) for t in schema["transitions"]
        }
        assert (states.proposed, states.confirm_target) in edges, preset
        assert (states.proposed, states.rejected) in edges, preset


def test_rejected_state_is_marked_terminal():
    for preset, states in PROPOSAL_STATES.items():
        meta = PRESET_SCHEMAS[preset].get("state_meta", {})
        assert meta.get(states.rejected, {}).get("is_outdated_equivalent") is True, preset


def test_reused_rejected_states_are_not_duplicated():
    for preset in ("ccb_approval", "adr_default"):
        states = PROPOSAL_STATES[preset]
        assert PRESET_SCHEMAS[preset]["states"].count(states.rejected) == 1


def test_confirm_transition_excludes_viewer_role():
    for preset, states in PROPOSAL_STATES.items():
        for t in PRESET_SCHEMAS[preset]["transitions"]:
            if t["from_state"] != states.proposed:
                continue
            assert "viewer" not in t["allowed_roles"], preset
            assert set(t["allowed_roles"]) == {"editor", "approver", "admin"}, preset


def test_rejection_requires_a_change_reason():
    for preset, states in PROPOSAL_STATES.items():
        edge = next(
            t
            for t in PRESET_SCHEMAS[preset]["transitions"]
            if t["from_state"] == states.proposed and t["to_state"] == states.rejected
        )
        assert edge["requires_change_reason"] is True, preset
        assert edge["signature_gate"] is False, preset
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec backend pytest workflow/tests/test_preset_initial_state_unchanged.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'workflow.proposal'`

- [ ] **Step 3: Write the proposal-state table**

```python
# backend/workflow/proposal.py
"""AI-proposal workflow states (KI-Vorschlag-als-Zustand spec §4).

An artifact created by an agent principal starts in this preset's *proposed*
state instead of its normal initial state, and a human confirms it (into
``confirm_target``) or rejects it (into ``rejected``) through ordinary
transitions of the very same state machine.

Two constraints drive the shape of this table:

* State names are byte-identical to the owning entity's ``Status.choices``
  values, because ``StateLifecycleManager._sync_status_mirror`` writes
  ``current_state`` verbatim into the entity's ``status`` column
  (definition_store.py:213-219). Hence "Proposed" for Adr/Risk/Issue and
  "Vorgeschlagen" for Goal/MainGoal — not one global lowercase literal.
* ``ccb_approval`` and ``adr_default`` already own a rejected state with
  unrelated semantics (CCB rejection / a never-adopted ADR). Those are reused
  rather than duplicated, so the graph keeps exactly one rejected state.

``minimal`` is excluded by the rigor rule (spec §4.1). ``interview_default`` is
excluded because an InterviewSession is a live conversation, not a proposable
artifact — it has no "draft" equivalent to confirm into.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProposalStates:
    """The three state names a preset uses for the proposal cycle."""

    #: State an agent-created item is initialised into.
    proposed: str
    #: Terminal state a human moves a bad proposal to.
    rejected: str
    #: State a confirmed proposal moves to — the preset's normal initial state.
    confirm_target: str
    #: False when ``rejected`` already existed in the preset before this change.
    rejected_is_new: bool


def _s(proposed: str, rejected: str, target: str, new: bool = True) -> ProposalStates:
    return ProposalStates(
        proposed=proposed, rejected=rejected, confirm_target=target, rejected_is_new=new
    )


PROPOSAL_STATES: dict[str, ProposalStates] = {
    "standard": _s("proposed", "rejected", "draft"),
    "extended": _s("proposed", "rejected", "draft"),
    "need_default": _s("proposed", "rejected", "draft"),
    "testcase_default": _s("proposed", "rejected", "draft"),
    "architecture_default": _s("proposed", "rejected", "draft"),
    "icd_default": _s("proposed", "rejected", "draft"),
    "diagram_default": _s("proposed", "rejected", "draft"),
    "glossary_term_default": _s("proposed", "rejected", "draft"),
    # Existing "rejected" reused (CCB rejection) — no second rejected state.
    "ccb_approval": _s("proposed", "rejected", "draft", new=False),
    # Existing "Rejected" reused (a never-adopted ADR).
    "adr_default": _s("Proposed", "Rejected", "Draft", new=False),
    "risk_default": _s("Proposed", "Rejected", "Identified"),
    "issue_default": _s("Proposed", "Rejected", "Open"),
    "goal_default": _s("Vorgeschlagen", "Abgelehnt", "Entwurf"),
    "main_goal_default": _s("Vorgeschlagen", "Abgelehnt", "Entwurf"),
}

#: Presets that deliberately have no proposal cycle.
PRESETS_WITHOUT_PROPOSAL = frozenset({"minimal", "interview_default"})

#: Roles allowed to confirm or reject. "viewer" is excluded: confirming a
#: proposal promotes it into the live artifact set, which is a write.
_CONFIRM_ROLES = ["editor", "approver", "admin"]


def proposal_states_for_preset(preset: str) -> ProposalStates | None:
    """Return the proposal states for *preset*, or None if it has none."""
    return PROPOSAL_STATES.get(preset)


def apply_proposal_states(schema: dict, states: ProposalStates) -> dict:
    """Return *schema* with the proposal state and its two exits merged in.

    Idempotent, and it APPENDS: ``states[0]`` — the definition's
    ``initial_state`` — is never displaced (see C1 in the plan). Mutates and
    returns the same dict so it can be applied in place to ``PRESET_SCHEMAS``.
    """
    state_list: list[str] = schema.setdefault("states", [])
    for name in (states.proposed, states.rejected):
        if name not in state_list:
            state_list.append(name)

    transitions: list[dict] = schema.setdefault("transitions", [])
    existing = {(t["from_state"], t["to_state"]) for t in transitions}
    for target, needs_reason in (
        (states.confirm_target, False),
        (states.rejected, True),
    ):
        if (states.proposed, target) in existing:
            continue
        transitions.append(
            {
                "from_state": states.proposed,
                "to_state": target,
                "allowed_roles": list(_CONFIRM_ROLES),
                "requires_change_reason": needs_reason,
                "signature_gate": False,
            }
        )

    state_meta: dict = schema.setdefault("state_meta", {})
    entry = state_meta.get(states.rejected, {})
    state_meta[states.rejected] = {**entry, "is_outdated_equivalent": True}
    return schema


__all__ = [
    "PROPOSAL_STATES",
    "PRESETS_WITHOUT_PROPOSAL",
    "ProposalStates",
    "apply_proposal_states",
    "proposal_states_for_preset",
]
```

- [ ] **Step 4: Apply the table to `PRESET_SCHEMAS`**

At the very end of `backend/workflow/definition_store.py`, directly after the `PRESET_SCHEMAS`
literal closes (before the next `def`), append:

```python
# KI-Vorschlag-als-Zustand spec §4.1: merge the proposal state + its two exits
# into every preset that has one. Applied here rather than written into each
# literal above so the state names live in exactly one table
# (workflow/proposal.py) and the "never displace states[0]" invariant is
# enforced by one function instead of sixteen hand-edits.
def _install_proposal_states() -> None:
    from workflow.proposal import PROPOSAL_STATES, apply_proposal_states

    for _preset, _states in PROPOSAL_STATES.items():
        apply_proposal_states(PRESET_SCHEMAS[_preset], _states)


_install_proposal_states()
```

- [ ] **Step 5: Run test to verify it passes**

Run: `docker compose exec backend pytest workflow/tests/test_preset_initial_state_unchanged.py -v`
Expected: PASS (8 tests)

- [ ] **Step 6: Run the workflow definition regression suite**

Run: `docker compose exec backend pytest workflow/tests/test_definition_store.py workflow/tests/test_available_transitions.py -q --create-db`
Expected: no new failures.

- [ ] **Step 7: Commit**

```bash
git add backend/workflow/proposal.py backend/workflow/definition_store.py backend/workflow/tests/test_preset_initial_state_unchanged.py
git commit -m "feat(workflow): add proposed/rejected states to the preset defaults"
```

---

## Task 8: Backfill the proposal states into existing definitions

**Files:**
- Create: `backend/workflow/migrations/0018_seed_proposed_state.py`
- Test: `backend/workflow/tests/test_proposal_backfill_migration.py`

**Interfaces:**
- Consumes: `PROPOSAL_STATES`, `apply_proposal_states` (Task 7).
- Produces: existing `GlobalWorkflowDefinition` rows and their `is_customized=False` derived
  `WorkflowEngineDefinition` rows carry the proposal states.

Template: `backend/workflow/migrations/0016_seed_adr_risk_outdated_equivalent_flags.py` — same
two-pass shape (globals + propagation, then unlinked non-customized workspace rows).

- [ ] **Step 1: Write the failing test**

```python
# backend/workflow/tests/test_proposal_backfill_migration.py
"""Migration 0018 backfills proposal states into pre-existing definitions (spec §7.3)."""
from __future__ import annotations

from uuid import uuid4

import pytest

from persistence.models import Tenant
from persistence.tenancy import TenantContext
from workflow.migrations import _proposal_backfill  # helper module under test
from workflow.models import GlobalWorkflowDefinition, WorkflowEngineDefinition


@pytest.mark.django_db
def test_backfill_adds_states_and_propagates_to_non_customized():
    tenant = Tenant.objects.create(name="t", is_active=True)
    TenantContext.set_tenant(tenant.id)
    try:
        g = GlobalWorkflowDefinition.objects.create(
            tenant=tenant,
            item_type="StakeholderNeed",
            preset="need_default",
            workflow_json={
                "states": ["draft", "in_review", "approved", "deprecated"],
                "transitions": [],
                "state_meta": {"deprecated": {"is_outdated_equivalent": True}},
            },
        )
        plain = WorkflowEngineDefinition.objects.create(
            tenant=tenant,
            workspace_id=uuid4(),
            item_type="StakeholderNeed",
            preset="need_default",
            workflow_json=dict(g.workflow_json),
            source_global=g,
            is_customized=False,
        )
        custom = WorkflowEngineDefinition.objects.create(
            tenant=tenant,
            workspace_id=uuid4(),
            item_type="StakeholderNeed",
            preset="need_default",
            workflow_json=dict(g.workflow_json),
            source_global=g,
            is_customized=True,
        )

        _proposal_backfill.backfill(
            GlobalWorkflowDefinition, WorkflowEngineDefinition
        )

        g.refresh_from_db()
        plain.refresh_from_db()
        custom.refresh_from_db()
        assert g.workflow_json["states"][0] == "draft"
        assert "proposed" in g.workflow_json["states"]
        assert "proposed" in plain.workflow_json["states"]
        # Spec §7.3: customized workspaces are NOT auto-upgraded.
        assert "proposed" not in custom.workflow_json["states"]
    finally:
        TenantContext.clear_tenant()


@pytest.mark.django_db
def test_backfill_is_idempotent():
    tenant = Tenant.objects.create(name="t2", is_active=True)
    TenantContext.set_tenant(tenant.id)
    try:
        g = GlobalWorkflowDefinition.objects.create(
            tenant=tenant,
            item_type="Risk",
            preset="risk_default",
            workflow_json={
                "states": ["Identified", "Monitored", "Closed"],
                "transitions": [],
            },
        )
        for _ in range(2):
            _proposal_backfill.backfill(
                GlobalWorkflowDefinition, WorkflowEngineDefinition
            )
        g.refresh_from_db()
        assert g.workflow_json["states"].count("Proposed") == 1
        assert g.workflow_json["states"].count("Rejected") == 1
        assert len(g.workflow_json["transitions"]) == 2
    finally:
        TenantContext.clear_tenant()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec backend pytest workflow/tests/test_proposal_backfill_migration.py -v`
Expected: FAIL with `ImportError: cannot import name '_proposal_backfill'`

- [ ] **Step 3: Write the reusable backfill helper**

```python
# backend/workflow/migrations/_proposal_backfill.py
"""Shared backfill body for migration 0018 (kept importable for its test)."""
from __future__ import annotations


def backfill(GlobalWorkflowDefinition, WorkflowEngineDefinition) -> None:
    """Merge the proposal states into every non-customized definition.

    Two passes, mirroring 0016_seed_adr_risk_outdated_equivalent_flags:
    globals first (then propagated to their non-customized derived rows, the
    same thing GlobalWorkflowDefinitionStore._propagate does at runtime), then
    any non-customized workspace row that has no linked global (pre-REQ-178
    data). ``is_customized=True`` rows are deliberately left alone — spec §7.3
    hands those to an admin via the Workflow-Editor UI.
    """
    from workflow.proposal import PROPOSAL_STATES, apply_proposal_states

    def _merge(workflow_json: dict, preset: str) -> dict | None:
        states = PROPOSAL_STATES.get(preset)
        if states is None:
            return None
        before = (
            list(workflow_json.get("states", [])),
            len(workflow_json.get("transitions", [])),
            dict(workflow_json.get("state_meta", {})),
        )
        merged = apply_proposal_states(workflow_json, states)
        after = (
            list(merged.get("states", [])),
            len(merged.get("transitions", [])),
            dict(merged.get("state_meta", {})),
        )
        return merged if before != after else None

    for global_def in GlobalWorkflowDefinition.objects.all():
        merged = _merge(global_def.workflow_json, global_def.preset)
        if merged is None:
            continue
        global_def.workflow_json = merged
        global_def.save(update_fields=["workflow_json"])
        WorkflowEngineDefinition.objects.filter(
            source_global_id=global_def.id, is_customized=False
        ).update(workflow_json=merged)

    for record in WorkflowEngineDefinition.objects.filter(
        source_global__isnull=True, is_customized=False
    ):
        merged = _merge(record.workflow_json, record.preset)
        if merged is None:
            continue
        record.workflow_json = merged
        record.save(update_fields=["workflow_json"])
```

- [ ] **Step 4: Write the migration**

```python
# backend/workflow/migrations/0018_seed_proposed_state.py
"""KI-Vorschlag-als-Zustand spec §7.3 — backfill the proposal states.

``definition_store.PRESET_SCHEMAS`` already carries them, so every workspace
created from now on inherits them at seed time. Rows created before this
change need this one-time backfill. Same two-pass shape as
0016_seed_adr_risk_outdated_equivalent_flags.
"""
from django.db import migrations

from workflow.migrations._proposal_backfill import backfill


def seed_proposal_states(apps, schema_editor):
    backfill(
        apps.get_model("workflow", "GlobalWorkflowDefinition"),
        apps.get_model("workflow", "WorkflowEngineDefinition"),
    )


def noop_reverse(apps, schema_editor):
    """No-op: leaving the extra states in place is harmless on an older build
    (they are simply never reached without the agent branch)."""


class Migration(migrations.Migration):

    dependencies = [
        ("workflow", "0017_backfill_lifecycle_status_mirror"),
    ]

    operations = [
        migrations.RunPython(seed_proposal_states, noop_reverse),
    ]
```

- [ ] **Step 5: Run test to verify it passes**

Run: `docker compose exec backend pytest workflow/tests/test_proposal_backfill_migration.py -v --create-db`
Expected: PASS (2 tests)

- [ ] **Step 6: Apply the migration against the dev database**

Run: `docker compose exec backend python manage.py migrate workflow`
Expected: `Applying workflow.0018_seed_proposed_state... OK`

- [ ] **Step 7: Commit**

```bash
git add backend/workflow/migrations/0018_seed_proposed_state.py backend/workflow/migrations/_proposal_backfill.py backend/workflow/tests/test_proposal_backfill_migration.py
git commit -m "feat(workflow): backfill proposal states into existing definitions"
```

---

## Task 9: Initialise agent-created items into `proposed`

**Files:**
- Modify: `backend/workflow/proposal.py` (add `initial_state_for`)
- Modify: `backend/workflow/lifecycle_manager.py:220-270` (`initialize_workflow_states`)
- Modify: `backend/workflow/services.py:428-457` (`initialize_workflow_states` wrapper)
- Test: `backend/workflow/tests/test_proposal_initial_state.py`

**Interfaces:**
- Consumes: `AuthContext.is_agent` / `.agent_label` (Task 2); `proposal_states_for_preset` (Task 7);
  `WorkflowDefinitionDTO.initial_state`, `.states`, `.preset` (`definition_store.py`).
- Produces: `initial_state_for(dto, workspace_id, actor_type) -> tuple[str, bool]` returning
  `(state_name, is_proposal)`; `StateLifecycleManager.initialize_workflow_states(..., proposed_as: str = "", agent_label: str = "")`.

This is the single seam described in C3: all thirteen `create_X()` services already call
`workflow.services.initialize_workflow_states(..., ctx=ctx)` and none of them changes.

- [ ] **Step 1: Write the failing test**

```python
# backend/workflow/tests/test_proposal_initial_state.py
"""Agent-created items initialise into the proposal state (spec §4.2)."""
from __future__ import annotations

from unittest.mock import patch
from uuid import uuid4

import pytest

from workflow.definition_store import WorkflowDefinitionDTO
from workflow.proposal import initial_state_for

WS = uuid4()


def _dto(preset: str, states: list[str]) -> WorkflowDefinitionDTO:
    # WorkflowDefinitionDTO declares states/transitions as tuples
    # (definition_store.py:75-76) — pass tuples, not lists.
    return WorkflowDefinitionDTO(
        workspace_id=WS, item_type="Requirement", preset=preset,
        states=tuple(states), transitions=(),
    )


def _tier(value: str | None):
    """Patch the preset-tier lookup initial_state_for consults."""
    return patch("workflow.proposal._workspace_tier", return_value=value)


def test_human_actor_keeps_the_normal_initial_state():
    dto = _dto("standard", ["draft", "approved", "proposed", "rejected"])
    with _tier("standard"):
        assert initial_state_for(dto, WS, "user") == ("draft", False)


def test_agent_actor_gets_the_proposal_state():
    dto = _dto("standard", ["draft", "approved", "proposed", "rejected"])
    with _tier("standard"):
        assert initial_state_for(dto, WS, "agent") == ("proposed", True)


def test_minimal_tier_never_proposes():
    """C2: per-entity presets are rigor-independent, so the tier is the gate."""
    dto = _dto("need_default", ["draft", "approved", "proposed", "rejected"])
    with _tier("minimal"):
        assert initial_state_for(dto, WS, "agent") == ("draft", False)


def test_graph_without_the_state_never_proposes():
    """A workspace that removed 'proposed' from its override opts out (spec §4.1)."""
    dto = _dto("standard", ["draft", "approved"])
    with _tier("standard"):
        assert initial_state_for(dto, WS, "agent") == ("draft", False)


def test_preset_without_a_proposal_cycle_never_proposes():
    dto = _dto("interview_default", ["in_progress", "completed"])
    with _tier("extended"):
        assert initial_state_for(dto, WS, "agent") == ("in_progress", False)


def test_unknown_tier_falls_back_to_proposing():
    """Fail-open on the LABEL, not on the control: an unreadable preset must
    not silently let agent writes into the live set."""
    dto = _dto("standard", ["draft", "proposed", "rejected"])
    with _tier(None):
        assert initial_state_for(dto, WS, "agent") == ("proposed", True)


def test_adr_uses_its_own_title_case_spelling():
    dto = _dto("adr_default", ["Draft", "Approved", "Proposed", "Rejected"])
    with _tier("extended"):
        assert initial_state_for(dto, WS, "agent") == ("Proposed", True)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec backend pytest workflow/tests/test_proposal_initial_state.py -v`
Expected: FAIL with `ImportError: cannot import name 'initial_state_for' from 'workflow.proposal'`

- [ ] **Step 3: Implement the resolver**

Append to `backend/workflow/proposal.py`:

```python
def _workspace_tier(workspace_id) -> str | None:
    """Return the workspace's rigor tier, or None when it cannot be read.

    Same lookup ``TransitionValidator._resolve_preset_tier`` uses
    (transition_validator.py:211-237). Isolated in its own function so tests
    can patch one seam.
    """
    try:
        from presets.services import get_preset

        return get_preset(str(workspace_id)).preset
    except Exception:  # noqa: BLE001 — an unreadable preset must not break creation
        return None


def initial_state_for(dto, workspace_id, actor_type: str) -> tuple[str, bool]:
    """Return ``(initial_state, is_proposal)`` for a newly created item.

    An agent principal starts in the preset's proposed state when BOTH hold:

    * the preset declares a proposal cycle (``PROPOSAL_STATES``), and
    * the *resolved* graph of this workspace actually contains that state — a
      workspace admin may have removed it from their override (spec §4.1), and
    * the workspace's rigor tier is not ``minimal``.

    The tier is checked separately from the graph because only ``Requirement``
    is provisioned with a rigor-tier preset; the other twelve entity types use
    rigor-independent per-entity presets (``need_default``, ``adr_default``, …).
    Without this check "minimal never proposes" would hold for Requirement only
    — see C2 in the implementation plan.

    Never raises: every caller sits inside a ``try/except Exception`` in its
    ``create_X()`` service, where an exception silently means "this artifact
    gets no workflow state at all".
    """
    fallback = (dto.initial_state, False)
    if actor_type != "agent":
        return fallback

    states = PROPOSAL_STATES.get(getattr(dto, "preset", "") or "")
    if states is None:
        return fallback
    if states.proposed not in (getattr(dto, "states", None) or ()):
        return fallback
    if _workspace_tier(workspace_id) == "minimal":
        return fallback
    return (states.proposed, True)
```

Add `"initial_state_for"` to `__all__`.

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec backend pytest workflow/tests/test_proposal_initial_state.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Write the failing integration test for the lifecycle manager**

Append to `backend/workflow/tests/test_proposal_initial_state.py`:

```python
@pytest.mark.django_db
def test_initialize_writes_state_mirror_and_genesis_history():
    """C4 + C7: the status mirror and the provenance entry are written at init."""
    from persistence.models import Requirement, Tenant, Workspace
    from persistence.tenancy import TenantContext
    from workflow.lifecycle_manager import StateLifecycleManager
    from workflow.models import WorkflowEngineDefinition, WorkflowHistoryEntry
    from workflow.proposal import PROPOSAL_STATES, apply_proposal_states

    tenant = Tenant.objects.create(name="t", is_active=True)
    TenantContext.set_tenant(tenant.id)
    try:
        ws = Workspace.objects.create(name="w", tenant=tenant)
        schema = apply_proposal_states(
            {"states": ["draft", "approved"], "transitions": []},
            PROPOSAL_STATES["standard"],
        )
        WorkflowEngineDefinition.objects.create(
            tenant=tenant, workspace_id=ws.id, item_type="Requirement",
            preset="standard", workflow_json=schema,
        )
        req = Requirement.objects.create(
            tenant=tenant, workspace=ws, title="r", status="draft"
        )

        StateLifecycleManager().initialize_workflow_states(
            item_ids=[req.id], item_type="Requirement", workspace_id=ws.id,
            proposed_as="proposed", agent_label="Claude Code",
        )

        req.refresh_from_db()
        assert req.status == "proposed"
        entry = WorkflowHistoryEntry.objects.get(item_state__item_id=req.id)
        assert entry.from_state == ""
        assert entry.to_state == "proposed"
        assert entry.transitioned_by == "Claude Code"
    finally:
        TenantContext.clear_tenant()
```

- [ ] **Step 6: Run test to verify it fails**

Run: `docker compose exec backend pytest workflow/tests/test_proposal_initial_state.py::test_initialize_writes_state_mirror_and_genesis_history -v --create-db`
Expected: FAIL with `TypeError: initialize_workflow_states() got an unexpected keyword argument 'proposed_as'`

- [ ] **Step 7: Extend the lifecycle manager**

In `backend/workflow/lifecycle_manager.py::initialize_workflow_states`, change the signature to:

```python
    def initialize_workflow_states(
        self,
        item_ids: list[UUID],
        item_type: str,
        workspace_id: UUID,
        proposed_as: str = "",
        agent_label: str = "",
    ) -> list[WorkflowItemState]:
```

Replace the `initial_state = dto.initial_state` line with:

```python
        # KI-Vorschlag-als-Zustand spec §4.2: an agent-created item starts in
        # the preset's proposed state. The decision itself is made by the
        # caller (workflow.services.initialize_workflow_states), which has the
        # AuthContext; this method only receives the resolved state name.
        initial_state = proposed_as or dto.initial_state
```

and replace the creation loop with:

```python
        from datetime import datetime, timezone as _tz

        created: list[WorkflowItemState] = []
        for item_id in item_ids:
            state = WorkflowItemState.objects.create(
                item_id=item_id,
                item_type=item_type,
                workspace_id=workspace_id,
                definition=definition_record,
                current_state=initial_state,
            )
            created.append(state)

            if not proposed_as:
                continue

            # C4: the mirror is normally written only by perform_transition, but
            # every create_X() service sets status="draft" on the row BEFORE
            # calling us. Without this write the artifact reads "draft" while
            # its WorkflowItemState reads "proposed" — invisible in every list
            # filter and every baseline snapshot.
            # ponytail: ArchitectureElement/GlossaryTerm/Icd/Diagram have no
            # `status` column (they sit in _LIFECYCLE_MIRROR_MODELS), so for
            # those four this is a no-op and the proposal shows up only in the
            # transitions API, not the list status filter. Upgrade path: the
            # status/lifecycle_status consolidation of the
            # Datenmodell-Konsolidierung spec.
            self._sync_status_mirror(item_id, item_type, initial_state)

            # C7: the spec assumes a history entry already exists here. It does
            # not — this is the only record of WHICH agent proposed the item.
            # transitioned_by is documented as accepting AI-agent client
            # identifiers (workflow/models.py:244-245).
            WorkflowHistoryEntry.objects.create(
                item_state=state,
                from_state="",
                to_state=initial_state,
                transitioned_by=agent_label or "agent",
                transitioned_at=datetime.now(_tz.utc),
                change_reason="",
                workspace_id=workspace_id,
            )

        return created
```

Ensure `WorkflowHistoryEntry` is imported at the top of the module (it already is, for
`perform_transition`).

- [ ] **Step 8: Wire the decision into the service wrapper**

In `backend/workflow/services.py::initialize_workflow_states`, replace the delegating call:

```python
    uuid_ids = [UUID(str(i)) for i in item_ids]
    workspace_uuid = UUID(str(workspace_id))

    # KI-Vorschlag-als-Zustand spec §4.2 — the single seam. Every create_X()
    # service already routes through this function and already passes ``ctx``,
    # so no service needs a copy of this check (see C3 in the plan).
    from workflow.proposal import initial_state_for

    dto = _get_store().get_definition(workspace_uuid, item_type)
    proposed_as, is_proposal = initial_state_for(
        dto, workspace_uuid, getattr(ctx, "actor_type", "user")
    )
    return _get_lifecycle().initialize_workflow_states(
        item_ids=uuid_ids,
        item_type=item_type,
        workspace_id=workspace_uuid,
        proposed_as=proposed_as if is_proposal else "",
        agent_label=getattr(ctx, "agent_label", "") or "",
    )
```

and update its docstring `Args:` entry for `ctx`:

```
        ctx:          AuthContext. ``actor_type``/``agent_label`` decide whether
                      the items start in the preset's proposed state (spec §4.2).
```

- [ ] **Step 9: Run test to verify it passes**

Run: `docker compose exec backend pytest workflow/tests/test_proposal_initial_state.py -v --create-db`
Expected: PASS (8 tests)

- [ ] **Step 10: Verify no create path regressed**

Run: `docker compose exec backend pytest workflow/tests/test_lifecycle_manager.py application/tests/test_stakeholder_need_service.py application/tests/test_adr_service.py -q --create-db`
Expected: no new failures — human creates still land in `draft`/`Draft`/`Entwurf`.

- [ ] **Step 11: Commit**

```bash
git add backend/workflow/proposal.py backend/workflow/lifecycle_manager.py backend/workflow/services.py backend/workflow/tests/test_proposal_initial_state.py
git commit -m "feat(workflow): initialise agent-created items into the proposed state"
```

---

## Task 10: An agent may never leave the `proposed` state

**Files:**
- Modify: `backend/workflow/transition_validator.py:64-93` (`ValidationRequest`), `:46-51` (codes), `:291-302` (Rule 2)
- Modify: `backend/workflow/services.py:245-256` (build `ValidationRequest`)
- Test: `backend/workflow/tests/test_proposal_agent_cannot_confirm.py`

**Interfaces:**
- Consumes: `ValidationRequest`, `ValidationResult`, `PROPOSAL_STATES` (Task 7), `AuthContext.actor_type` (Task 2).
- Produces: `ValidationRequest.actor_type: str = "user"`; `EC_AGENT_SELF_CONFIRM = "AGENT_SELF_CONFIRM"`.

- [ ] **Step 1: Write the failing test**

```python
# backend/workflow/tests/test_proposal_agent_cannot_confirm.py
"""Spec §4.3 — an agent principal never confirms its own proposal.

Enforced in the validator, not in allowed_roles: a workspace admin who
accidentally grants an agent's role on the proposed-> edges must not be able to
switch the control off.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

from workflow.definition_store import WorkflowDefinitionDTO, TransitionDefinitionDTO
from workflow.transition_validator import (
    EC_AGENT_SELF_CONFIRM,
    TransitionValidator,
    ValidationRequest,
)

WS, TENANT, USER = uuid4(), uuid4(), uuid4()


def _dto() -> WorkflowDefinitionDTO:
    return WorkflowDefinitionDTO(
        workspace_id=WS,
        item_type="Requirement",
        preset="standard",
        states=("draft", "approved", "proposed", "rejected"),
        transitions=(
            TransitionDefinitionDTO(
                from_state="proposed", to_state="draft",
                allowed_roles=["editor", "approver", "admin"],
                requires_change_reason=False, signature_gate=False,
            ),
            TransitionDefinitionDTO(
                from_state="draft", to_state="approved",
                allowed_roles=["approver", "admin"],
                requires_change_reason=False, signature_gate=False,
            ),
        ),
    )


def _req(current: str, target: str, actor_type: str) -> ValidationRequest:
    return ValidationRequest(
        item_id=uuid4(), workspace_id=WS, item_type="Requirement",
        current_state=current, target_state=target, user_id=USER,
        user_roles=("admin",), tenant_id=TENANT, actor_type=actor_type,
    )


def _validate(req: ValidationRequest):
    v = TransitionValidator()
    with patch.object(v, "_load_definition", return_value=_dto()), patch(
        "workflow.transition_validator.check_mandatory_fields", return_value=None
    ), patch(
        "workflow.transition_validator.check_verifies_link", return_value=None
    ), patch(
        "workflow.transition_validator.check_verification_evidence", return_value=None
    ):
        return v.validate(req)


def test_agent_cannot_confirm_its_own_proposal():
    result = _validate(_req("proposed", "draft", "agent"))
    assert result.valid is False
    assert result.error_code == EC_AGENT_SELF_CONFIRM


def test_agent_cannot_reject_a_proposal_either():
    result = _validate(_req("proposed", "rejected", "agent"))
    assert result.valid is False
    assert result.error_code == EC_AGENT_SELF_CONFIRM


def test_human_may_confirm():
    assert _validate(_req("proposed", "draft", "user")).valid is True


def test_agent_may_still_perform_unrelated_transitions():
    """Spec §6: normal agent transitions stay allowed, gated by signature_gate."""
    assert _validate(_req("draft", "approved", "agent")).valid is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec backend pytest workflow/tests/test_proposal_agent_cannot_confirm.py -v`
Expected: FAIL with `ImportError: cannot import name 'EC_AGENT_SELF_CONFIRM'`

- [ ] **Step 3: Add the field, the code and the rule**

In `backend/workflow/transition_validator.py`, add next to the other codes (line ~51):

```python
EC_AGENT_SELF_CONFIRM = "AGENT_SELF_CONFIRM"
```

Append to `ValidationRequest` (defaulted, so every existing construction stays valid):

```python
    #: "user" | "agent" — the resolved principal type of the caller
    #: (AuthContext.actor_type). Drives rule 2b (spec §4.3).
    actor_type: str = "user"
```

and document it in the class docstring's `Attributes:` block:

```
        actor_type:    Resolved principal type of the caller ("user"/"agent").
                       An agent may never transition OUT of a proposed state.
```

Insert Rule 2b in `validate`, immediately after the Rule 2 role check and before Rule 3:

```python
        # ---- Rule 2b: agent never confirms its own proposal (spec §4.3) ------
        # Deliberately checked here rather than through allowed_roles: a
        # workspace admin who accidentally lists an agent-held role on a
        # proposed-> edge must not be able to disable the control. Applies to
        # EVERY exit from the proposed state, confirm and reject alike.
        if request.actor_type == "agent":
            from workflow.proposal import proposal_states_for_preset

            proposal = proposal_states_for_preset(definition.preset or "")
            if proposal is not None and request.current_state == proposal.proposed:
                return ValidationResult(
                    valid=False,
                    error_code=EC_AGENT_SELF_CONFIRM,
                    error_message=(
                        "An agent principal cannot confirm or reject its own "
                        "proposal. A human editor, approver or admin must "
                        "review it."
                    ),
                )
```

- [ ] **Step 4: Pass the actor type in from the service**

In `backend/workflow/services.py::transition`, add to the `ValidationRequest(...)` construction
(~line 245):

```python
        actor_type=getattr(ctx, "actor_type", "user"),
```

- [ ] **Step 5: Run test to verify it passes**

Run: `docker compose exec backend pytest workflow/tests/test_proposal_agent_cannot_confirm.py -v`
Expected: PASS (4 tests)

- [ ] **Step 6: Run the validator regression suite**

Run: `docker compose exec backend pytest workflow/tests/ -q -k "validator or transition" --create-db`
Expected: no new failures.

- [ ] **Step 7: Commit**

```bash
git add backend/workflow/transition_validator.py backend/workflow/services.py backend/workflow/tests/test_proposal_agent_cannot_confirm.py
git commit -m "feat(workflow): forbid agents from leaving the proposed state"
```

---

## Task 11: TraceLink proposal columns

**Files:**
- Modify: `backend/persistence/models.py:1352-1409` (class `TraceLink`)
- Create: `backend/persistence/migrations/0070_tracelink_semantics.py`
- Test: `backend/persistence/tests/test_tracelink_proposal_fields.py`

**Interfaces:**
- Produces: `TraceLink.proposed_by` (FK → `auth_tenancy.ApiKey`, nullable, `SET_NULL`), `TraceLink.proposed_at` (nullable timestamp), `TraceLink.is_proposal` property.

**Coordination with the traceability-semantik spec (Global Constraint):** that spec's §6.3 adds
`rationale`, `suspect_flagged_at` and `suspect_source_change` to the same table. Both belong in
**one** migration. Add all five fields to the model here and generate a single migration named
`0070_tracelink_semantics`. If the traceability-semantik plan has already landed its own
`AddField` migration for the three suspect fields, drop those three from this step and add only
`proposed_by`/`proposed_at` to the existing migration file instead of creating a second one.

- [ ] **Step 1: Write the failing test**

```python
# backend/persistence/tests/test_tracelink_proposal_fields.py
"""TraceLink proposal provenance columns (spec §5)."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from auth_tenancy.models import PRINCIPAL_TYPE_AGENT, ApiKey
from persistence.models import Artifact, TraceLink, Tenant, User, Workspace
from persistence.tenancy import TenantContext


@pytest.fixture
def link_fixture(db):
    tenant = Tenant.objects.create(name="t", is_active=True)
    TenantContext.set_tenant(tenant.id)
    ws = Workspace.objects.create(name="w", tenant=tenant)
    user = User.objects.create(email="t@example.com", tenant=tenant, is_active=True)
    src = Artifact.objects.create(tenant=tenant, workspace=ws, title="a", artifact_type="Requirement")
    tgt = Artifact.objects.create(tenant=tenant, workspace=ws, title="b", artifact_type="Requirement")
    key = ApiKey.unscoped.create(
        user=user, tenant=tenant, name="bot", key_hash="sha256:" + "d" * 64,
        principal_type=PRINCIPAL_TYPE_AGENT, agent_label="Claude Code",
    )
    yield tenant, src, tgt, key
    TenantContext.clear_tenant()


@pytest.mark.django_db
def test_human_created_link_has_no_proposal_marker(link_fixture):
    tenant, src, tgt, _ = link_fixture
    link = TraceLink.objects.create(
        tenant=tenant, source=src, target=tgt, link_type="derives-from"
    )
    assert link.proposed_by is None
    assert link.proposed_at is None
    assert link.is_proposal is False


@pytest.mark.django_db
def test_agent_created_link_carries_the_key_and_timestamp(link_fixture):
    tenant, src, tgt, key = link_fixture
    now = datetime.now(timezone.utc)
    link = TraceLink.objects.create(
        tenant=tenant, source=src, target=tgt, link_type="derives-from",
        proposed_by=key, proposed_at=now,
    )
    link.refresh_from_db()
    assert link.proposed_by_id == key.id
    assert link.is_proposal is True


@pytest.mark.django_db
def test_revoking_the_key_does_not_delete_the_link(link_fixture):
    """SET_NULL: a proposal must outlive the key that made it."""
    tenant, src, tgt, key = link_fixture
    link = TraceLink.objects.create(
        tenant=tenant, source=src, target=tgt, link_type="derives-from",
        proposed_by=key, proposed_at=datetime.now(timezone.utc),
    )
    key.delete()
    link.refresh_from_db()
    assert link.proposed_by_id is None
    assert link.proposed_at is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec backend pytest persistence/tests/test_tracelink_proposal_fields.py -v`
Expected: FAIL with `TypeError: TraceLink() got unexpected keyword arguments: 'proposed_by'`

- [ ] **Step 3: Add the fields**

In `backend/persistence/models.py`, inside `class TraceLink`, after `embedding`:

```python
    # KI-Vorschlag-als-Zustand spec §5: TraceLinks are not workflow-tracked
    # items (there is no WorkflowItemState per link), so an agent-proposed link
    # is marked with these two columns instead of a workflow state. Both NULL
    # means "confirmed, or authored by a human directly".
    #
    # SET_NULL rather than CASCADE: revoking or deleting the key that proposed a
    # link must never delete the link itself.
    proposed_by = models.ForeignKey(
        "auth_tenancy.ApiKey",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="proposed_trace_links",
        help_text=(
            "API key of the agent that proposed this link; NULL once a human "
            "has confirmed it or when a human created it directly (spec §5)."
        ),
    )
    proposed_at = models.DateTimeField(null=True, blank=True)
```

and add, after `__str__`:

```python
    @property
    def is_proposal(self) -> bool:
        """True while this link is an unconfirmed agent proposal (spec §5)."""
        return self.proposed_at is not None
```

Also add an index for the "show me open link proposals" query, inside `Meta.indexes`:

```python
            models.Index(
                fields=["proposed_at"], name="idx_tracelink_proposed"
            ),
```

- [ ] **Step 4: Generate the migration**

Run: `docker compose exec backend python manage.py makemigrations persistence --name tracelink_semantics`
Expected: creates `persistence/migrations/0070_tracelink_semantics.py` with two `AddField` plus one
`AddIndex`, depending on `0069_align_embedding_dimensions` and on `auth_tenancy.0013_apikey_agent_identity`.

Verify the cross-app dependency is present; if `makemigrations` omitted it, add it manually:

```python
    dependencies = [
        ("persistence", "0069_align_embedding_dimensions"),
        ("auth_tenancy", "0013_apikey_agent_identity"),
    ]
```

- [ ] **Step 5: Run test to verify it passes**

Run: `docker compose exec backend pytest persistence/tests/test_tracelink_proposal_fields.py -v --create-db`
Expected: PASS (3 tests)

- [ ] **Step 6: Commit**

```bash
git add backend/persistence/models.py backend/persistence/migrations/0070_tracelink_semantics.py backend/persistence/tests/test_tracelink_proposal_fields.py
git commit -m "feat(traceability): add proposal provenance columns to TraceLink"
```

---

## Task 12: TraceLink proposal service and REST actions

**Files:**
- Modify: `backend/application/trace_link_service.py:336+` (`create_trace_link`; add `confirm_trace_link`, `reject_trace_link`)
- Modify: `backend/rest_api/views.py:2351+` (`TraceLinkViewSet`)
- Modify: `backend/rest_api/serializers.py:1021+` (`TraceLinkSerializer`)
- Test: `backend/application/tests/test_trace_link_proposal.py`

**Interfaces:**
- Consumes: `TraceLink.proposed_by` / `.proposed_at` / `.is_proposal` (Task 11); `AuthContext.is_agent` / `.api_key_id` (Task 2).
- Produces: `TraceLinkService.confirm_trace_link(link_id: UUID, ctx: AuthContext) -> TraceLink`;
  `TraceLinkService.reject_trace_link(link_id: UUID, ctx: AuthContext) -> None`;
  `POST /api/v1/trace-links/<pk>/confirm/`, `POST /api/v1/trace-links/<pk>/reject/`;
  serializer fields `proposed_by` (UUID, read-only), `proposed_by_label` (string, read-only), `proposed_at` (datetime, read-only).

- [ ] **Step 1: Write the failing test**

```python
# backend/application/tests/test_trace_link_proposal.py
"""TraceLink proposal lifecycle (spec §5)."""
from __future__ import annotations

from uuid import uuid4

import pytest

from application.trace_link_service import TraceLinkService
from auth_tenancy.context import AuthContext, AuthMethod
from auth_tenancy.models import PRINCIPAL_TYPE_AGENT, ApiKey
from persistence.models import Artifact, TraceLink, Tenant, User, Workspace
from persistence.tenancy import TenantContext


@pytest.fixture
def env(db):
    tenant = Tenant.objects.create(name="t", is_active=True)
    TenantContext.set_tenant(tenant.id)
    ws = Workspace.objects.create(name="w", tenant=tenant)
    user = User.objects.create(email="p@example.com", tenant=tenant, is_active=True)
    key = ApiKey.unscoped.create(
        user=user, tenant=tenant, name="bot", key_hash="sha256:" + "e" * 64,
        principal_type=PRINCIPAL_TYPE_AGENT, agent_label="Claude Code",
    )
    src = Artifact.objects.create(tenant=tenant, workspace=ws, title="a", artifact_type="Requirement")
    tgt = Artifact.objects.create(tenant=tenant, workspace=ws, title="b", artifact_type="Requirement")
    yield tenant, ws, user, key, src, tgt
    TenantContext.clear_tenant()


def _ctx(user, tenant, *, agent: bool, key=None, ws=None) -> AuthContext:
    return AuthContext(
        user_id=user.id, tenant_id=tenant.id, active_roles=("editor",),
        auth_method=AuthMethod.API_KEY, api_key_id=key.id if key else None,
        workspace_id=ws.id if ws else None,
        actor_type="agent" if agent else "user",
        agent_label="Claude Code" if agent else "",
    )


@pytest.mark.django_db
def test_agent_created_link_is_stamped_as_a_proposal(env):
    tenant, ws, user, key, src, tgt = env
    link = TraceLinkService().create_trace_link(
        source_id=src.id, target_id=tgt.id, link_type="derives-from",
        ctx=_ctx(user, tenant, agent=True, key=key, ws=ws),
    )
    link.refresh_from_db()
    assert link.is_proposal is True
    assert link.proposed_by_id == key.id


@pytest.mark.django_db
def test_human_created_link_is_not_a_proposal(env):
    tenant, ws, user, key, src, tgt = env
    link = TraceLinkService().create_trace_link(
        source_id=src.id, target_id=tgt.id, link_type="derives-from",
        ctx=_ctx(user, tenant, agent=False, ws=ws),
    )
    assert link.is_proposal is False


@pytest.mark.django_db
def test_confirm_clears_both_fields(env):
    tenant, ws, user, key, src, tgt = env
    svc = TraceLinkService()
    link = svc.create_trace_link(
        source_id=src.id, target_id=tgt.id, link_type="derives-from",
        ctx=_ctx(user, tenant, agent=True, key=key, ws=ws),
    )
    out = svc.confirm_trace_link(link.id, _ctx(user, tenant, agent=False, ws=ws))
    assert out.proposed_by_id is None
    assert out.proposed_at is None


@pytest.mark.django_db
def test_reject_deletes_the_link(env):
    tenant, ws, user, key, src, tgt = env
    svc = TraceLinkService()
    link = svc.create_trace_link(
        source_id=src.id, target_id=tgt.id, link_type="derives-from",
        ctx=_ctx(user, tenant, agent=True, key=key, ws=ws),
    )
    svc.reject_trace_link(link.id, _ctx(user, tenant, agent=False, ws=ws))
    assert not TraceLink.objects.filter(id=link.id).exists()


@pytest.mark.django_db
def test_agent_may_not_confirm(env):
    tenant, ws, user, key, src, tgt = env
    svc = TraceLinkService()
    link = svc.create_trace_link(
        source_id=src.id, target_id=tgt.id, link_type="derives-from",
        ctx=_ctx(user, tenant, agent=True, key=key, ws=ws),
    )
    with pytest.raises(PermissionError):
        svc.confirm_trace_link(link.id, _ctx(user, tenant, agent=True, key=key, ws=ws))


@pytest.mark.django_db
def test_agent_may_not_reject(env):
    tenant, ws, user, key, src, tgt = env
    svc = TraceLinkService()
    link = svc.create_trace_link(
        source_id=src.id, target_id=tgt.id, link_type="derives-from",
        ctx=_ctx(user, tenant, agent=True, key=key, ws=ws),
    )
    with pytest.raises(PermissionError):
        svc.reject_trace_link(link.id, _ctx(user, tenant, agent=True, key=key, ws=ws))


@pytest.mark.django_db
def test_confirming_a_non_proposal_is_a_no_op(env):
    tenant, ws, user, key, src, tgt = env
    svc = TraceLinkService()
    link = svc.create_trace_link(
        source_id=src.id, target_id=tgt.id, link_type="derives-from",
        ctx=_ctx(user, tenant, agent=False, ws=ws),
    )
    out = svc.confirm_trace_link(link.id, _ctx(user, tenant, agent=False, ws=ws))
    assert out.id == link.id
    assert out.proposed_at is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec backend pytest application/tests/test_trace_link_proposal.py -v --create-db`
Expected: FAIL with `AttributeError: 'TraceLinkService' object has no attribute 'confirm_trace_link'`

- [ ] **Step 3: Stamp proposals on creation**

At the end of `TraceLinkService.create_trace_link` in `backend/application/trace_link_service.py`,
after the link has been created and before it is returned:

```python
        # KI-Vorschlag-als-Zustand spec §5: a link authored by an agent
        # principal is an unconfirmed proposal until a human clears the marker.
        if getattr(ctx, "is_agent", False) and ctx.api_key_id is not None:
            from datetime import datetime, timezone as _tz

            link.proposed_by_id = ctx.api_key_id
            link.proposed_at = datetime.now(_tz.utc)
            link.save(update_fields=["proposed_by", "proposed_at"])
```

- [ ] **Step 4: Add the confirm / reject methods**

Append to `TraceLinkService`:

```python
    def _load_link_for_review(self, link_id: UUID, ctx: AuthContext):
        """Fetch a link for a proposal decision, enforcing spec §5's hard rule.

        Raises:
            PermissionError: The caller is an agent principal. Same control as
                the workflow rule in spec §4.3, applied to links: an agent must
                never clear its own proposal marker.
            LookupError: No such link in the caller's tenant.
        """
        if getattr(ctx, "is_agent", False):
            raise PermissionError(
                "An agent principal cannot confirm or reject a proposed trace "
                "link. A human must review it."
            )
        link = TraceLink.objects.filter(id=link_id).first()
        if link is None:
            raise LookupError(f"TraceLink {link_id} not found")
        return link

    def confirm_trace_link(self, link_id: UUID, ctx: AuthContext):
        """Accept an agent-proposed link by clearing its proposal marker (spec §5).

        Idempotent: confirming a link that carries no marker returns it
        unchanged rather than erroring, so a double-click or a bulk action that
        overlaps a single confirm is harmless.
        """
        link = self._load_link_for_review(link_id, ctx)
        if link.proposed_at is not None:
            link.proposed_by = None
            link.proposed_at = None
            link.save(update_fields=["proposed_by", "proposed_at"])
            self._audit(
                ctx=ctx,
                operation="update",
                entity_type="TraceLink",
                entity_id=link.id,
                details={"action": "confirm_proposal"},
            )
        return link

    def reject_trace_link(self, link_id: UUID, ctx: AuthContext) -> None:
        """Discard a proposed link entirely (spec §5: rejecting deletes it).

        Raises:
            ValueError: The link is not a proposal — deleting a human-authored
                link through this path would be a silent data loss.
        """
        link = self._load_link_for_review(link_id, ctx)
        if link.proposed_at is None:
            raise ValueError(
                "This trace link is not an open proposal; delete it through the "
                "normal delete endpoint instead."
            )
        link_id_copy = link.id
        link.delete()
        self._audit(
            ctx=ctx,
            operation="delete",
            entity_type="TraceLink",
            entity_id=link_id_copy,
            details={"action": "reject_proposal"},
        )
```

Ensure `TraceLink` and `AuthContext` are imported in the module (both already are).

- [ ] **Step 5: Run test to verify it passes**

Run: `docker compose exec backend pytest application/tests/test_trace_link_proposal.py -v --create-db`
Expected: PASS (7 tests)

- [ ] **Step 6: Expose the fields and the two actions over REST**

Add to `TraceLinkSerializer` in `backend/rest_api/serializers.py`:

```python
    # KI-Vorschlag-als-Zustand spec §5: proposal provenance. Read-only — the
    # marker is set by the service on agent writes, never by a client.
    proposed_by = serializers.UUIDField(read_only=True, required=False, allow_null=True)
    proposed_by_label = serializers.CharField(
        read_only=True, required=False, allow_blank=True, default="",
        help_text="agent_label of the proposing API key; empty when not a proposal.",
    )
    proposed_at = serializers.DateTimeField(read_only=True, required=False, allow_null=True)
```

Add the two actions to `TraceLinkViewSet` in `backend/rest_api/views.py`:

```python
    @action(detail=True, methods=["post"], url_path="confirm")
    def confirm(self, request: Request, pk: str | None = None, **kwargs: Any) -> Response:
        """POST /api/v1/trace-links/<pk>/confirm/ — accept an agent proposal (spec §5)."""
        try:
            link = self._svc().confirm_trace_link(UUID(str(pk)), request.auth_context)
        except PermissionError as exc:
            return Response(
                build_error_response(code="PERMISSION_DENIED", message=str(exc)),
                status=status.HTTP_403_FORBIDDEN,
            )
        except (LookupError, ValueError) as exc:
            return Response(
                build_error_response(code="NOT_FOUND", message=str(exc)),
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(
            TraceLinkSerializer(link).data, status=status.HTTP_200_OK
        )

    @action(detail=True, methods=["post"], url_path="reject")
    def reject(self, request: Request, pk: str | None = None, **kwargs: Any) -> Response:
        """POST /api/v1/trace-links/<pk>/reject/ — discard an agent proposal (spec §5)."""
        try:
            self._svc().reject_trace_link(UUID(str(pk)), request.auth_context)
        except PermissionError as exc:
            return Response(
                build_error_response(code="PERMISSION_DENIED", message=str(exc)),
                status=status.HTTP_403_FORBIDDEN,
            )
        except ValueError as exc:
            return Response(
                build_error_response(code="VALIDATION_ERROR", message=str(exc)),
                status=status.HTTP_400_BAD_REQUEST,
            )
        except LookupError as exc:
            return Response(
                build_error_response(code="NOT_FOUND", message=str(exc)),
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)
```

- [ ] **Step 7: Verify the endpoints respond**

Run: `docker compose exec backend pytest rest_api/tests/ -q -k "tracelink or trace_link" --create-db`
Expected: no new failures; the two new routes resolve.

- [ ] **Step 8: Commit**

```bash
git add backend/application/trace_link_service.py backend/rest_api/views.py backend/rest_api/serializers.py backend/application/tests/test_trace_link_proposal.py
git commit -m "feat(traceability): confirm/reject flow for agent-proposed trace links"
```

---

## Task 13: Frontend — proposal status ordering, badge variant and labels

**Files:**
- Modify: `frontend/src/utils/workflowStatus.ts:37-73` (`STATUS_ORDER`), `:80-89` (`STATUS_LABELS`)
- Modify: `frontend/src/utils/statusBadge.ts:59-120` (`STATUS_VARIANT_MAP`)
- Modify: `frontend/src/i18n/locales/de.json`, `frontend/src/i18n/locales/en.json`
- Test: `frontend/src/test/proposalStatus.test.ts`

**Interfaces:**
- Consumes: `getWorkflowStatusLabel`, `compareWorkflowStatus`, `buildStatusFilterOptions` (existing), `resolveBadgeVariant` (existing).
- Produces: no new exports — `proposed` / `Vorgeschlagen` sort before `draft` and render with the `info` badge variant.

Per C5 no filter component changes: `buildStatusFilterOptions` derives its options from the loaded
items' `status` values, which Task 9 now populates with the proposal state.

- [ ] **Step 1: Write the failing test**

```ts
// frontend/src/test/proposalStatus.test.ts
import { describe, expect, it } from "vitest";
import {
  buildStatusFilterOptions,
  compareWorkflowStatus,
  getWorkflowStatusLabel,
} from "../utils/workflowStatus";
import { resolveBadgeVariant } from "../utils/statusBadge";

describe("proposal status presentation", () => {
  it("sorts every proposal spelling ahead of draft", () => {
    expect(compareWorkflowStatus("proposed", "draft")).toBeLessThan(0);
    expect(compareWorkflowStatus("Proposed", "Draft")).toBeLessThan(0);
    expect(compareWorkflowStatus("Vorgeschlagen", "Entwurf")).toBeLessThan(0);
  });

  it("renders a readable label", () => {
    expect(getWorkflowStatusLabel("proposed")).toBe("Proposed");
    expect(getWorkflowStatusLabel("Vorgeschlagen")).toBe("Vorgeschlagen");
  });

  it("uses the info variant so a proposal never looks approved or neutral", () => {
    expect(resolveBadgeVariant("proposed")).toBe("info");
    expect(resolveBadgeVariant("Proposed")).toBe("info");
    expect(resolveBadgeVariant("Vorgeschlagen")).toBe("info");
  });

  it("keeps the rejected spellings on the danger variant", () => {
    expect(resolveBadgeVariant("rejected")).toBe("danger");
    expect(resolveBadgeVariant("Abgelehnt")).toBe("danger");
  });

  it("offers the proposal option as soon as one item carries it", () => {
    const options = buildStatusFilterOptions([
      { status: "draft" },
      { status: "proposed" },
    ]);
    expect(options.map((o) => o.value)).toEqual(["proposed", "draft"]);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec frontend npx vitest run src/test/proposalStatus.test.ts --testTimeout=30000`
Expected: FAIL — `expect(resolveBadgeVariant("proposed")).toBe("info")` receives `"neutral"`, and the sort assertions fail because `proposed` is an unknown state ranked last.

- [ ] **Step 3: Add the states to the ordering table**

In `frontend/src/utils/workflowStatus.ts`, insert at the very top of `STATUS_ORDER`, above `'draft'`:

```ts
  // KI-Vorschlag-als-Zustand: an unconfirmed AI proposal precedes every
  // human-authored state. Three spellings because state names are byte-identical
  // to each entity's Status.choices (see backend/workflow/proposal.py).
  'proposed',
  'vorgeschlagen',
```

and add to the terminal block, next to `'rejected'`:

```ts
  'abgelehnt',
```

`getWorkflowStatusLabel`'s `humanizeStatus` fallback already turns `proposed` into `Proposed` and
leaves `Vorgeschlagen` intact, so `STATUS_LABELS` needs no entry.

- [ ] **Step 4: Add the badge variants**

In `frontend/src/utils/statusBadge.ts`, add to `STATUS_VARIANT_MAP` in the pre-work section:

```ts
  // A proposal is live, unreviewed work — 'info', never 'neutral' (which would
  // make it indistinguishable from 'draft') and never 'success'.
  proposed: 'info',
  vorgeschlagen: 'info',
```

and next to the existing `rejected: 'danger'`:

```ts
  abgelehnt: 'danger',
```

- [ ] **Step 5: Add the i18n keys**

Add to `frontend/src/i18n/locales/de.json` at the top level (flat nested object — note the project's
`keySeparator` is `"."`, so these must be a real nested `proposal` object, not dotted keys):

```json
  "proposal": {
    "hint": "Vorschlag von {{agent}}",
    "hintUnknownAgent": "KI-Vorschlag",
    "confirm": "Bestätigen",
    "reject": "Verwerfen",
    "bulkConfirm": "Ausgewählte bestätigen",
    "bulkConfirmed": "{{count}} Vorschläge bestätigt",
    "bulkFailed": "{{count}} Vorschläge konnten nicht bestätigt werden"
  },
```

and the English equivalent in `frontend/src/i18n/locales/en.json`:

```json
  "proposal": {
    "hint": "Proposed by {{agent}}",
    "hintUnknownAgent": "AI proposal",
    "confirm": "Confirm",
    "reject": "Discard",
    "bulkConfirm": "Confirm selected",
    "bulkConfirmed": "{{count}} proposals confirmed",
    "bulkFailed": "{{count}} proposals could not be confirmed"
  },
```

- [ ] **Step 6: Run test to verify it passes**

Run: `docker compose exec frontend npx vitest run src/test/proposalStatus.test.ts --testTimeout=30000`
Expected: PASS (5 tests)

- [ ] **Step 7: Restart the frontend container**

Run: `docker compose restart frontend`
Reason: Vite has no working HMR on Windows in this stack — without a restart every later manual
and E2E check silently tests stale code.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/utils/workflowStatus.ts frontend/src/utils/statusBadge.ts frontend/src/i18n/locales/de.json frontend/src/i18n/locales/en.json frontend/src/test/proposalStatus.test.ts
git commit -m "feat(ui): present the proposal state in status badges and filters"
```

---

## Task 14: Frontend — "Vorschlag von {agent_label}" hint on the artifact detail

**Files:**
- Create: `frontend/src/components/WorkflowStatusEditor/ProposalHint.tsx`
- Modify: `frontend/src/components/WorkflowStatusEditor/WorkflowStatusEditor.tsx`
- Test: `frontend/src/components/WorkflowStatusEditor/ProposalHint.test.tsx`

**Interfaces:**
- Consumes: `workflowTransitionsApi.getWorkflowHistory(type, id)` and `WorkflowHistoryEntry` (existing, `api/workflow-transitions.ts`); the genesis entry written by Task 9 (`from_state === ""`).
- Produces: `ProposalHint({ artifactType, artifactId, currentState, proposedStates })` and the exported constant `PROPOSAL_STATE_NAMES: readonly string[]`.

Scope note: the confirm/reject *buttons* need no new code — `WorkflowStatusEditor` already renders
every entry of `allowed_transitions` as a menu item, and Task 7 put `proposed → confirm_target` and
`proposed → rejected` into the graph. This task adds only the provenance line.

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/components/WorkflowStatusEditor/ProposalHint.test.tsx
import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../api/workflow-transitions", () => ({
  workflowTransitionsApi: { getWorkflowHistory: vi.fn() },
}));

import { workflowTransitionsApi } from "../../api/workflow-transitions";
import { PROPOSAL_STATE_NAMES, ProposalHint } from "./ProposalHint";

const mocked = vi.mocked(workflowTransitionsApi.getWorkflowHistory);

describe("ProposalHint", () => {
  beforeEach(() => mocked.mockReset());

  it("renders nothing when the artifact is not a proposal", () => {
    const { container } = render(
      <ProposalHint artifactType="requirement" artifactId="a1" currentState="draft" />,
    );
    expect(container).toBeEmptyDOMElement();
    expect(mocked).not.toHaveBeenCalled();
  });

  it("names the proposing agent from the genesis history entry", async () => {
    mocked.mockResolvedValue([
      {
        id: "h1",
        from_state: "",
        to_state: "proposed",
        actor: "Claude Code",
        change_reason: "",
        transitioned_at: "2026-09-03T10:00:00Z",
        sealed: false,
      },
    ]);
    render(
      <ProposalHint artifactType="requirement" artifactId="a1" currentState="proposed" />,
    );
    await waitFor(() =>
      expect(screen.getByTestId("proposal-hint")).toHaveTextContent("Claude Code"),
    );
  });

  it("falls back to a generic label when no genesis entry exists", async () => {
    mocked.mockResolvedValue([]);
    render(
      <ProposalHint artifactType="requirement" artifactId="a1" currentState="proposed" />,
    );
    await waitFor(() =>
      expect(screen.getByTestId("proposal-hint")).toBeInTheDocument(),
    );
  });

  it("recognises every backend spelling of the proposal state", () => {
    expect(PROPOSAL_STATE_NAMES).toContain("proposed");
    expect(PROPOSAL_STATE_NAMES).toContain("Proposed");
    expect(PROPOSAL_STATE_NAMES).toContain("Vorgeschlagen");
  });

  it("survives a failing history request without throwing", async () => {
    mocked.mockRejectedValue(new Error("boom"));
    const { container } = render(
      <ProposalHint artifactType="requirement" artifactId="a1" currentState="proposed" />,
    );
    await waitFor(() => expect(container).toBeEmptyDOMElement());
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec frontend npx vitest run src/components/WorkflowStatusEditor/ProposalHint.test.tsx --testTimeout=30000`
Expected: FAIL with `Failed to resolve import "./ProposalHint"`

- [ ] **Step 3: Write the component**

```tsx
// frontend/src/components/WorkflowStatusEditor/ProposalHint.tsx
/**
 * ARCH-L1-001 ReactFrontend — AI-proposal provenance hint.
 *
 * spec: docs/superpowers/specs/2026-09-03-ki-vorschlag-als-zustand-design.md §4.4
 *
 * Shows "Vorschlag von {agent_label}" next to the status badge while an
 * artifact sits in its preset's proposed state. The agent label lives in the
 * genesis WorkflowHistoryEntry the backend writes at state initialisation
 * (from_state === ""), so this needs no new endpoint — it reads the same
 * /workflow-history/ the detail view already exposes.
 *
 * The confirm/reject BUTTONS are deliberately not here: "proposed -> draft" and
 * "proposed -> rejected" are ordinary transitions, so WorkflowStatusEditor
 * already renders them from allowed_transitions. This component adds only the
 * provenance line.
 */
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Sparkles } from "lucide-react";

import {
  workflowTransitionsApi,
  type WorkflowArtifactType,
} from "../../api/workflow-transitions";

/**
 * Every spelling of the proposal state across the preset defaults
 * (backend/workflow/proposal.py PROPOSAL_STATES). State names are
 * byte-identical to each entity's Status.choices, so there is no single
 * lowercase literal to compare against.
 */
export const PROPOSAL_STATE_NAMES: readonly string[] = [
  "proposed",
  "Proposed",
  "Vorgeschlagen",
];

export interface ProposalHintProps {
  artifactType: WorkflowArtifactType;
  artifactId: string;
  /** Current workflow state, as reported by the transitions endpoint. */
  currentState?: string | null;
}

export function ProposalHint({
  artifactType,
  artifactId,
  currentState,
}: ProposalHintProps): JSX.Element | null {
  const { t } = useTranslation();
  const [agent, setAgent] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  const isProposal = PROPOSAL_STATE_NAMES.includes((currentState ?? "").trim());

  useEffect(() => {
    if (!isProposal) return;
    let cancelled = false;
    workflowTransitionsApi
      .getWorkflowHistory(artifactType, artifactId)
      .then((entries) => {
        if (cancelled) return;
        const genesis = entries.find((e) => !e.from_state);
        setAgent(genesis?.actor ?? "");
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, [isProposal, artifactType, artifactId]);

  if (!isProposal || failed || agent === null) return null;

  return (
    <span
      data-testid="proposal-hint"
      role="note"
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "var(--spacing-xs)",
        color: "var(--color-text-muted)",
        fontSize: "var(--font-size-sm)",
      }}
    >
      <Sparkles size={14} aria-hidden="true" />
      {agent
        ? t("proposal.hint", { agent })
        : t("proposal.hintUnknownAgent")}
    </span>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec frontend npx vitest run src/components/WorkflowStatusEditor/ProposalHint.test.tsx --testTimeout=30000`
Expected: PASS (5 tests)

- [ ] **Step 5: Render the hint next to the status badge**

In `frontend/src/components/WorkflowStatusEditor/WorkflowStatusEditor.tsx`, import the component:

```tsx
import { ProposalHint } from "./ProposalHint";
```

and render it immediately after the badge element in the returned JSX:

```tsx
      <ProposalHint
        artifactType={artifactType}
        artifactId={artifactId}
        currentState={data?.current_state ?? currentStatus}
      />
```

- [ ] **Step 6: Verify the editor suite still passes**

Run: `docker compose exec frontend npx vitest run src/components/WorkflowStatusEditor --testTimeout=30000`
Expected: PASS — no regressions in `WorkflowStatusEditor.test.tsx`.

- [ ] **Step 7: Restart the frontend container and check it in the browser**

Run: `docker compose restart frontend`
Then open a workspace, create a requirement through an agent API key (or set one item's
`WorkflowItemState.current_state` to `proposed` via the shell) and confirm: the badge reads
"Proposed" in the info colour, the hint reads "Vorschlag von …", and the status dropdown offers
exactly two moves (confirm target + rejected).

- [ ] **Step 8: Commit**

```bash
git add frontend/src/components/WorkflowStatusEditor/ProposalHint.tsx frontend/src/components/WorkflowStatusEditor/ProposalHint.test.tsx frontend/src/components/WorkflowStatusEditor/WorkflowStatusEditor.tsx
git commit -m "feat(ui): show the proposing agent on artifacts in the proposed state"
```

---

## Task 15: Frontend — bulk confirm for AI proposals

**Files:**
- Create: `frontend/src/components/Reviews/BulkAcceptBar.tsx`
- Modify: `frontend/src/components/Reviews/ReviewsView.tsx`
- Test: `frontend/src/components/Reviews/BulkAcceptBar.test.tsx`

**Interfaces:**
- Consumes: `workflowTransitionsApi.transition(type, id, targetState)` (existing); `PROPOSAL_STATE_NAMES` (Task 14).
- Produces: `BulkAcceptBar({ artifactType, selectedIds, confirmTarget, onDone })`; `confirmProposals(artifactType, ids, confirmTarget) -> Promise<BulkAcceptResult>` with `BulkAcceptResult = { confirmed: string[]; failed: string[] }`.

Spec §4.4 scope: only the `proposed → confirm_target` transition. No general bulk edit.

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/components/Reviews/BulkAcceptBar.test.tsx
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../api/workflow-transitions", () => ({
  workflowTransitionsApi: { transition: vi.fn() },
}));

import { workflowTransitionsApi } from "../../api/workflow-transitions";
import { BulkAcceptBar, confirmProposals } from "./BulkAcceptBar";

const mocked = vi.mocked(workflowTransitionsApi.transition);

describe("confirmProposals", () => {
  beforeEach(() => mocked.mockReset());

  it("confirms every id and reports them", async () => {
    mocked.mockResolvedValue({ id: "x", previous_state: "proposed", new_state: "draft" });
    const result = await confirmProposals("requirement", ["a", "b"], "draft");
    expect(result.confirmed).toEqual(["a", "b"]);
    expect(result.failed).toEqual([]);
    expect(mocked).toHaveBeenCalledTimes(2);
    expect(mocked).toHaveBeenCalledWith("requirement", "a", "draft");
  });

  it("keeps going when one item fails and reports the failure", async () => {
    mocked
      .mockResolvedValueOnce({ id: "a", previous_state: "proposed", new_state: "draft" })
      .mockRejectedValueOnce(new Error("403"))
      .mockResolvedValueOnce({ id: "c", previous_state: "proposed", new_state: "draft" });
    const result = await confirmProposals("requirement", ["a", "b", "c"], "draft");
    expect(result.confirmed).toEqual(["a", "c"]);
    expect(result.failed).toEqual(["b"]);
  });
});

describe("BulkAcceptBar", () => {
  beforeEach(() => mocked.mockReset());

  it("is hidden while nothing is selected", () => {
    const { container } = render(
      <BulkAcceptBar
        artifactType="requirement"
        selectedIds={[]}
        confirmTarget="draft"
        onDone={vi.fn()}
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("shows the selected count and confirms on click", async () => {
    mocked.mockResolvedValue({ id: "a", previous_state: "proposed", new_state: "draft" });
    const onDone = vi.fn();
    render(
      <BulkAcceptBar
        artifactType="requirement"
        selectedIds={["a", "b"]}
        confirmTarget="draft"
        onDone={onDone}
      />,
    );
    expect(screen.getByTestId("bulk-accept-count")).toHaveTextContent("2");
    fireEvent.click(screen.getByTestId("bulk-accept-confirm"));
    await waitFor(() =>
      expect(onDone).toHaveBeenCalledWith({ confirmed: ["a", "b"], failed: [] }),
    );
  });

  it("disables the button while the batch is running", async () => {
    let resolve: (v: unknown) => void = () => {};
    mocked.mockImplementation(() => new Promise((r) => (resolve = r)));
    render(
      <BulkAcceptBar
        artifactType="requirement"
        selectedIds={["a"]}
        confirmTarget="draft"
        onDone={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByTestId("bulk-accept-confirm"));
    await waitFor(() =>
      expect(screen.getByTestId("bulk-accept-confirm")).toBeDisabled(),
    );
    resolve({ id: "a", previous_state: "proposed", new_state: "draft" });
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec frontend npx vitest run src/components/Reviews/BulkAcceptBar.test.tsx --testTimeout=30000`
Expected: FAIL with `Failed to resolve import "./BulkAcceptBar"`

- [ ] **Step 3: Write the component**

```tsx
// frontend/src/components/Reviews/BulkAcceptBar.tsx
/**
 * ARCH-L1-001 ReactFrontend — bulk confirm for AI proposals.
 *
 * spec: docs/superpowers/specs/2026-09-03-ki-vorschlag-als-zustand-design.md §4.4
 *
 * The minimal version of the bulk editing asked for in audit ch. Q1.3: exactly
 * one transition (proposed -> the preset's confirm target), applied to a
 * multi-selection. Not a general bulk edit.
 *
 * ponytail: sequential requests, not a batch endpoint — a reviewer confirms
 * tens of proposals, not thousands, and one failing item must not roll back the
 * rest. Add a server-side batch transition if a run ever exceeds ~100 items.
 */
import { useCallback, useState } from "react";
import { useTranslation } from "react-i18next";

import {
  workflowTransitionsApi,
  type WorkflowArtifactType,
} from "../../api/workflow-transitions";

export interface BulkAcceptResult {
  confirmed: string[];
  failed: string[];
}

/**
 * Confirm every id in turn, collecting successes and failures separately.
 *
 * Deliberately sequential and never rejecting: a 403 on one artifact (an
 * item-level permission, or a workspace that removed the proposal state) must
 * not abort the remaining items or lose the successes already made.
 */
export async function confirmProposals(
  artifactType: WorkflowArtifactType,
  ids: readonly string[],
  confirmTarget: string,
): Promise<BulkAcceptResult> {
  const confirmed: string[] = [];
  const failed: string[] = [];
  for (const id of ids) {
    try {
      await workflowTransitionsApi.transition(artifactType, id, confirmTarget);
      confirmed.push(id);
    } catch {
      failed.push(id);
    }
  }
  return { confirmed, failed };
}

export interface BulkAcceptBarProps {
  artifactType: WorkflowArtifactType;
  selectedIds: readonly string[];
  /** The preset's confirm target ("draft" / "Draft" / "Entwurf" / "Open" / …). */
  confirmTarget: string;
  onDone: (result: BulkAcceptResult) => void;
}

export function BulkAcceptBar({
  artifactType,
  selectedIds,
  confirmTarget,
  onDone,
}: BulkAcceptBarProps): JSX.Element | null {
  const { t } = useTranslation();
  const [busy, setBusy] = useState(false);

  const handleConfirm = useCallback(async () => {
    setBusy(true);
    try {
      onDone(await confirmProposals(artifactType, selectedIds, confirmTarget));
    } finally {
      setBusy(false);
    }
  }, [artifactType, selectedIds, confirmTarget, onDone]);

  if (selectedIds.length === 0) return null;

  return (
    <div
      role="toolbar"
      aria-label={t("proposal.bulkConfirm")}
      style={{
        display: "flex",
        alignItems: "center",
        gap: "var(--spacing-sm)",
        padding: "var(--spacing-sm)",
        background: "var(--color-surface-raised)",
        borderRadius: "var(--radius-md)",
      }}
    >
      <span data-testid="bulk-accept-count">{selectedIds.length}</span>
      <button
        type="button"
        data-testid="bulk-accept-confirm"
        disabled={busy}
        aria-busy={busy}
        onClick={handleConfirm}
      >
        {t("proposal.bulkConfirm")}
      </button>
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec frontend npx vitest run src/components/Reviews/BulkAcceptBar.test.tsx --testTimeout=30000`
Expected: PASS (5 tests)

- [ ] **Step 5: Mount the bar in the review queue**

In `frontend/src/components/Reviews/ReviewsView.tsx`, add a selection state and render the bar
above the list:

```tsx
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
```

```tsx
        <BulkAcceptBar
          artifactType={artifactType}
          selectedIds={selectedIds}
          confirmTarget={confirmTarget}
          onDone={(result) => {
            setSelectedIds([]);
            void reloadQueue();
            if (result.failed.length > 0) {
              setError(t("proposal.bulkFailed", { count: result.failed.length }));
            }
          }}
        />
```

`confirmTarget` comes from the transitions payload the queue already loads: the single
`allowed_transitions` entry whose `to_state` is not the preset's rejected state. Derive it once:

```tsx
  const confirmTarget = useMemo(
    () =>
      transitions.find((tr) => !/^(rejected|Rejected|Abgelehnt)$/.test(tr.target_state))
        ?.target_state ?? "",
    [transitions],
  );
```

Add a checkbox per row with `data-testid={`review-select-${item.id}`}` that toggles membership in
`selectedIds`.

- [ ] **Step 6: Verify the review suite still passes**

Run: `docker compose exec frontend npx vitest run src/components/Reviews --testTimeout=30000`
Expected: PASS — `ReviewsView.test.tsx` and `ReviewsView.queue-refresh.test.tsx` unchanged.

- [ ] **Step 7: Restart the frontend and verify in the browser**

Run: `docker compose restart frontend`
Then open the review queue with at least two proposals, select both, click "Ausgewählte bestätigen",
and confirm both rows leave the proposal state and the queue reloads.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/components/Reviews/BulkAcceptBar.tsx frontend/src/components/Reviews/BulkAcceptBar.test.tsx frontend/src/components/Reviews/ReviewsView.tsx
git commit -m "feat(ui): bulk confirm AI proposals from the review queue"
```

---

## Task 16: End-to-end verification of the proposal loop

**Files:**
- Test: `backend/application/tests/test_agent_proposal_e2e.py`

**Interfaces:**
- Consumes: everything from Tasks 1-12.
- Produces: no code — the regression net that proves the seams are actually wired together.

- [ ] **Step 1: Write the failing test**

```python
# backend/application/tests/test_agent_proposal_e2e.py
"""End-to-end: an agent key creates a requirement, a human confirms it.

Proves the seams are actually wired to each other rather than each unit test
passing against its own mock: ApiKey.principal_type -> IdentityClaims ->
AuthContext.actor_type -> initialize_workflow_states -> WorkflowItemState +
status mirror + genesis history -> TransitionValidator rule 2b.
"""
from __future__ import annotations

import pytest

from application.requirement_service import RequirementService
from auth_tenancy.context import AuthContext, AuthMethod
from auth_tenancy.models import (
    PRINCIPAL_TYPE_AGENT,
    ROLE_ADMIN,
    ApiKey,
    UserRole,
)
from auth_tenancy.services.authentication import (
    AuthenticationService,
    generate_api_key_plaintext,
    hash_api_key,
)
from auth_tenancy.services.tenant_context import TenantContextService
from persistence.models import Requirement, Tenant, User, Workspace
from persistence.tenancy import TenantContext
from workflow.models import WorkflowHistoryEntry, WorkflowItemState
from workflow.services import create_default_workflow, transition
from workflow.transition_validator import EC_AGENT_SELF_CONFIRM


@pytest.fixture
def env(db):
    tenant = Tenant.objects.create(name="t", is_active=True)
    TenantContext.set_tenant(tenant.id)
    ws = Workspace.objects.create(name="w", tenant=tenant)
    user = User.objects.create(email="e2e@example.com", tenant=tenant, is_active=True)
    UserRole.objects.create(
        user=user, workspace_id=ws.id, role=ROLE_ADMIN, tenant=tenant
    )
    create_default_workflow(
        workspace_id=ws.id, preset="standard", item_type="Requirement",
        tenant_id=tenant.id,
    )
    plaintext = generate_api_key_plaintext()
    ApiKey.unscoped.create(
        user=user, tenant=tenant, name="bot", key_hash=hash_api_key(plaintext),
        principal_type=PRINCIPAL_TYPE_AGENT, agent_label="Claude Code",
    )
    yield tenant, ws, user, plaintext
    TenantContext.clear_tenant()


def _agent_ctx(plaintext: str, ws) -> AuthContext:
    svc = TenantContextService()
    claims = AuthenticationService().validate_api_key(plaintext)
    return svc.build_auth_context(
        claims, svc.resolve_tenant_context(claims), ("admin",), workspace_id=ws.id
    )


def _human_ctx(user, tenant, ws) -> AuthContext:
    return AuthContext(
        user_id=user.id, tenant_id=tenant.id, active_roles=("admin",),
        auth_method=AuthMethod.BEARER_TOKEN, workspace_id=ws.id,
    )


@pytest.mark.django_db
def test_agent_created_requirement_lands_in_proposed(env):
    tenant, ws, user, plaintext = env
    ctx = _agent_ctx(plaintext, ws)
    assert ctx.is_agent is True

    req = RequirementService().create_requirement(
        title="agent req", description="d", workspace_id=ws.id, ctx=ctx
    )

    state = WorkflowItemState.objects.get(item_id=req.id, item_type="Requirement")
    assert state.current_state == "proposed"
    # C4: the mirror agrees, so lists and baselines see it.
    assert Requirement.objects.get(id=req.id).status == "proposed"
    # C7: provenance exists.
    genesis = WorkflowHistoryEntry.objects.get(item_state=state, from_state="")
    assert genesis.transitioned_by == "Claude Code"


@pytest.mark.django_db
def test_agent_cannot_confirm_its_own_requirement(env):
    from workflow.services import WorkflowTransitionError

    tenant, ws, user, plaintext = env
    ctx = _agent_ctx(plaintext, ws)
    req = RequirementService().create_requirement(
        title="agent req", description="d", workspace_id=ws.id, ctx=ctx
    )
    with pytest.raises(WorkflowTransitionError) as exc:
        transition(
            item_id=req.id, target_state="draft", change_reason="",
            ctx=ctx, item_type="Requirement", workspace_id=ws.id,
        )
    assert exc.value.error_code == EC_AGENT_SELF_CONFIRM


@pytest.mark.django_db
def test_human_confirms_the_proposal(env):
    tenant, ws, user, plaintext = env
    req = RequirementService().create_requirement(
        title="agent req", description="d", workspace_id=ws.id,
        ctx=_agent_ctx(plaintext, ws),
    )
    transition(
        item_id=req.id, target_state="draft", change_reason="",
        ctx=_human_ctx(user, tenant, ws), item_type="Requirement",
        workspace_id=ws.id,
    )
    assert (
        WorkflowItemState.objects.get(
            item_id=req.id, item_type="Requirement"
        ).current_state
        == "draft"
    )
    assert Requirement.objects.get(id=req.id).status == "draft"


@pytest.mark.django_db
def test_human_created_requirement_is_unaffected(env):
    tenant, ws, user, plaintext = env
    req = RequirementService().create_requirement(
        title="human req", description="d", workspace_id=ws.id,
        ctx=_human_ctx(user, tenant, ws),
    )
    assert (
        WorkflowItemState.objects.get(
            item_id=req.id, item_type="Requirement"
        ).current_state
        == "draft"
    )
    assert not WorkflowHistoryEntry.objects.filter(
        item_state__item_id=req.id
    ).exists()
```

- [ ] **Step 2: Run test to verify it fails (before Tasks 1-10 land) / passes (after)**

Run: `docker compose exec backend pytest application/tests/test_agent_proposal_e2e.py -v --create-db`
Expected: PASS (4 tests) once Tasks 1-10 are complete. If `test_agent_created_requirement_lands_in_proposed`
fails with `current_state == "draft"`, the `ctx` is not reaching
`workflow.services.initialize_workflow_states` — check Task 9 Step 8 first, then Task 2.

- [ ] **Step 3: Run the full touched-module suite**

Run: `docker compose exec backend pytest auth_tenancy/ workflow/ application/tests/test_trace_link_proposal.py application/tests/test_agent_proposal_e2e.py application/tests/test_audit_actor_type.py mcp_server/tests/test_agent_ctx_propagation.py -q --create-db`
Expected: no new failures versus the pre-change baseline. Do not run the whole backend tree — CI covers that in parallel.

- [ ] **Step 4: Run the frontend suites touched by this change**

Run: `docker compose exec frontend npx vitest run src/test/proposalStatus.test.ts src/components/WorkflowStatusEditor src/components/Reviews --testTimeout=30000`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/application/tests/test_agent_proposal_e2e.py
git commit -m "test: end-to-end coverage for the agent proposal loop"
```

---

## Self-Review

**1. Spec coverage**

| Spec section | Requirement | Task |
|---|---|---|
| §3 | `principal_type`, `agent_label`, `scope`, `workspace_ids`, `expires_at` on `ApiKey` | 1 |
| §3 | `AuthContext` carries `actor_type="agent"` instead of masking as the user | 2 |
| §3 | Scope + expiry enforcement (audit E2.1) | 2 (expiry), 3 (scope) |
| §3 | `workspace_ids` enforcement | 3 |
| §3 | `agent_label` shown where the user name would be | 5 (audit), 9 (history actor), 14 (UI) |
| §4.1 | `proposed` + `rejected` in the standard/extended defaults | 7 |
| §4.1 | `minimal` keeps its graph without `proposed` | 7 + 9 (tier gate, C2) |
| §4.1 | `rejected` as a terminal state | 7 (`is_outdated_equivalent`) |
| §4.1 | Workspace overrides may add/remove `proposed` | 9 (graph membership check) |
| §4.2 | Every `create_X()` initialises agents into `proposed` | 9 (one seam, C3) |
| §4.2 | No new field on `Artifact` | 9 (state + mirror + history only) |
| §4.2 | Provenance in `WorkflowHistoryEntry` | 9 (genesis entry, C7) |
| §4.3 | Agent never confirms itself, enforced in the validator | 10 |
| §4.4 | Proposal hint instead of the plain badge | 13 + 14 |
| §4.4 | Confirm/reject as ordinary transition buttons | 7 (graph) + 14 (no new code needed) |
| §4.4 | "Only AI proposals" list filter | 13 (free via C5) |
| §4.4 | Bulk accept | 15 |
| §5 | `TraceLink.proposed_by` / `proposed_at` | 11 |
| §5 | Confirm nulls both, reject deletes, agents may do neither | 12 |
| §6 | Transitions stay out of scope | — (no task, by design) |
| §7.1 | Additive `ApiKey` migration, existing keys default to `user` | 1 |
| §7.2 | `TraceLink` fields in the same migration as the suspect fields | 11 |
| §7.3 | Bootstrap backfill; `is_customized=True` not auto-upgraded | 8 |
| §8 | Risk: a forgotten `create_X()` path | Refuted (C3) — one seam, covered by Task 16 |
| §8 | Risk: existing keys stay `principal_type="user"` | Accepted, tested in Task 1 |
| §8 | Risk: `rejected` must be honoured by terminal-state consumers | 7 (`is_outdated_equivalent`, 4 existing consumers) |

**2. Placeholder scan** — no `TBD`, no `TODO`, no "similar to Task N", no "add error handling"
without code. Every test body is executable; every implementation snippet is complete. The two
`ponytail:` comments (Task 9, Task 15) name a concrete ceiling and its upgrade path, which is a
documented convention, not a placeholder.

**3. Type consistency across tasks**
- `actor_type` is the string `"user"`/`"agent"` in `ApiKey.principal_type` → `IdentityClaims.actor_type` → `AuthContext.actor_type` → `ValidationRequest.actor_type` → `AuditEntry.actor_type`. One vocabulary, five hops, no enum/str mismatch.
- `ApiKey.workspace_ids` is `list[str]` on the model and `tuple[str, ...]` on the frozen dataclasses; the conversion happens exactly once, in `validate_api_key` (Task 2 Step 4).
- `initial_state_for` returns `tuple[str, bool]`; the caller (Task 9 Step 8) passes `""` — not `None` — for the non-proposal case, matching `proposed_as: str = ""` in the lifecycle manager.
- `ProposalStates.confirm_target` (Task 7) is the same string the frontend derives as `confirmTarget` (Task 15) and the E2E test asserts as `"draft"` (Task 16).
- `PROPOSAL_STATE_NAMES` (Task 14) lists exactly the three distinct `ProposalStates.proposed` values in `PROPOSAL_STATES` (Task 7); Task 13's `STATUS_ORDER` additions and Task 15's rejected-state regex cover the same three plus their rejected counterparts.
- `TraceLink.proposed_by` is an FK, so the ORM attribute is `proposed_by` and the id is `proposed_by_id` — Task 12's service sets `proposed_by_id`, Task 11's tests read both, and the serializer exposes it as a `UUIDField` named `proposed_by`.
