# Rollenbasierte Sichten Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the four existing RBAC roles (`admin`/`editor`/`viewer`/`approver`) into three deliberate UI views — Leser / Autor / Experte — by making navigation visibility runtime-configurable data, deriving the artifact-form mode from role *and* workflow state, and collapsing `audience="expert"` sections behind a per-user expert-mode switch.

**Architecture:** No new RBAC concept and no new Django app. Navigation visibility becomes a tenant-singleton JSON blob plus a per-workspace materialized override, modelled 1:1 on the existing `GlobalPermissionDefinition` / `WorkspacePermissionDefinition` pair in `backend/auth_tenancy/` (same table shape, same service methods, same admin gate, same `is_customized`/`source_global`/reset semantics). The per-state field lock ("an approved artifact is read-only even for an author") reuses the already-live `workflow_json.state_meta` extension point instead of introducing a new table. `audience` is consumed from the Attribute-Definition system object (Spec 2) — this plan never re-implements it.

**Tech Stack:** Django 5.2 + DRF (backend), pytest/pytest-django (backend tests), React 18 + TypeScript 5.5 strict (frontend), Vitest + @testing-library/react (frontend tests), i18next (DE/EN), Docker Compose test overlay (`testing/docker-compose.test.yml`).

**Spec:** docs/superpowers/specs/2026-09-03-rollenbasierte-sichten-design.md

## Global Constraints

- Role strings are exactly `admin`, `editor`, `viewer`, `approver` (`backend/auth_tenancy/models.py:35-38`, `ROLE_ADMIN`/`ROLE_EDITOR`/`ROLE_VIEWER`/`ROLE_APPROVER`). No new role is introduced by this plan.
- View mapping is fixed: **Leser** = `viewer`, **Autor** = `editor`, **Experte** = `admin` or `approver`.
- Navigation visibility is **not a security boundary**. The real gate stays the server-side RBAC check on the route/API. A misconfigured `required_role` is a UX defect, never a security hole.
- `audience` is **not a security boundary**. It only controls the default collapsed/expanded state of a section. `visible` (Attribute-Definition Spec) remains the visibility property.
- Expert mode is a **user preference, not a right**. The switch changes what is initially expanded, never what is editable, and never grants a capability.
- An item a role must not see is **not rendered** — never CSS-hidden, never merely `disabled`.
- Every new interactive element carries a `data-testid` (E2E requirement).
- No hardcoded colors/sizes — CSS custom properties from `frontend/src/styles/tokens.css` only.
- DRF views never touch `persistence.models` directly — always through `application/` or `auth_tenancy/services/`.
- Every DRF view resolves tenant context via `get_auth_context(request)` / `ServiceBase._set_tenant_context(ctx)`.
- Commits use Conventional Commits, English, imperative, ≤72 chars in the subject line.
- Backend tests: `docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm backend-test pytest <path> -v`
- Frontend tests: `docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm frontend-test sh -c "npm install && npx vitest run <path> --testTimeout=30000"`
- Never run the full backend suite or the full Playwright suite in the fix loop — CI covers both.

---

## Verification of the spec against the live codebase

Read this before Task 1. Four spec statements were checked against `main` and three of them are stale or imprecise.

| Spec claim | Reality on `main` (commit `54b09760`, "P0 hardening — role-gate UI") | Consequence for this plan |
|---|---|---|
| "Rollen liegen schon im Login-Response, aber **die UI kennt sie nicht** — sie zeigt jedem alles" (§1) | **Stale.** `frontend/src/hooks/useHasRole.ts` exists and is consumed by `SidebarNavigation.tsx`, `RequirementForm.tsx`, `RequirementList.tsx`, `RequirementEditors.tsx`, `ReqTraceLinkPanel.tsx`. `NAV_ITEMS` already has `requires?: "admin" \| "editor"` (`SidebarNavigation.tsx:71`), and `/settings` + `/system-settings` are already admin-gated. | The **hard minimal fix of #848 is already merged.** This plan does not re-fix it; it replaces the hardcoded gate with runtime-configurable data and extends the same gate to the artifact form's *workflow-state* dimension, which is genuinely missing. |
| "`NAV_ITEMS` verliert sein statisches `requires`-Feld" (§3.1) | `requires` is today the only thing keeping `/settings` and `/system-settings` off a viewer's sidebar. | **Deviation (see DECISION 2):** `requires` is **kept** as the code-level default and the data layer *overrides* it. Fail-safe: a renamed key or an empty config still gates the admin pages. Also removes the need for the §7.2 bootstrap seed entirely — an empty map already is the current state. |
| "Die **26** heutigen Nav-Einträge" (§3.1, §7.2) | **25** entries in `NAV_ITEMS` (`SidebarNavigation.tsx:74-134`). | Cosmetic; the plan never hardcodes a count. |
| "`roles` liegt im Login-Response" (§1) | **Correct.** `LoginResponse.roles`, `AuthUser.roles`, plus `is_tenant_admin` (`frontend/src/context/AuthContext.tsx:57-63`), served by `_user_payload` (`backend/rest_api/auth_views.py:154`). | `_user_payload` is the free carrier for `expert_mode_enabled` — no extra round trip. |

Additional gap found, **not** mentioned in the spec: `useHasRole`'s `RequiredRole` type is `'admin' | 'editor'` only. `approver` and `viewer` are not expressible today, so the spec's "Experte = `admin`, `approver`" cannot be written with the current hook. Task 9 widens it.

Hard dependencies on sibling specs (these tasks **cannot start** before the named spec ships):
- `shared/ArtifactForm/` and `AttributeEditorPage` do **not** exist yet → Tasks 15, 16, 17 depend on **Spec 2 (Attribut-Definition)**.
- `/documents/:id/read` does **not** exist yet → Task 18 depends on **Spec 10 (Dokumentensicht)**.

### DECISION 1 — one JSON blob per scope, not one row per nav item

**context:** §3.1 specifies `GlobalNavigationVisibility` / `WorkspaceNavigationVisibility` with one row per `nav_item_key`.
**choice:** One row per scope holding a `visibility_json` map `{nav_item_key: required_role | null}`, exactly like `GlobalPermissionDefinition.permission_json`.
**alternatives:** One row per key (spec literal) — 25 rows × N workspaces, a propagation loop over 25× more rows, and a 25-row-per-workspace backfill, for a config read once per sidebar render. Rejected as pure row inflation.
**consequences:** The whole read is one row; `PUT` with a full map and `PUT` with one changed key are the same operation; `is_customized` / `source_global` / reset semantics come from an existing, tested pattern. The spec's per-key REST route `…/{nav_item_key}/` collapses into a whole-map `GET/PUT`.

### DECISION 2 — `NAV_ITEMS.requires` stays as the code default

**context:** §3.1 says `NAV_ITEMS` loses `requires` and reads visibility purely from data; §7.2 then needs a bootstrap seed of all 25 entries.
**choice:** `requires` stays as the fallback. Resolution order per item: `visibility_json[key]` if the key is present, else `item.requires`.
**alternatives:** Pure data (spec literal) — requires a seed migration, and a renamed/missing key silently fails **open**, exposing `/system-settings` in a viewer's sidebar.
**consequences:** No seed migration; an empty `visibility_json` is exactly today's behaviour. An admin only ever stores the deltas they actually changed. Fail-safe by construction.

### DECISION 3 — the read-only-when-approved rule lives in `workflow_json.state_meta`

**context:** §3.2 requires the form mode to derive from role **and** workflow state ("an `approved` artifact is read-only for an author too"), but no state-level lock flag exists.
**choice:** Reuse the live `state_meta` extension point (`backend/workflow/definition_store.py:818` `get_state_meta`, already carrying `is_outdated_equivalent` / `auto_approve_target`) with a new key `fields_locked: bool`, surfaced on the existing `GET /{resource}/{id}/transitions/` envelope.
**alternatives:** (a) Turn `workflow_json.states` from strings into objects — breaks the whole workflow editor (states are strings by design). (b) A new tenant-level "locked states" list — wrong granularity; different item types legitimately freeze at different states. (c) A new table — over-built for one boolean.
**consequences:** Per `(item_type, preset, workspace)` granularity for free, inherits the existing global→workspace propagation, no new endpoint, no schema break. Default is `false` everywhere → zero behaviour change until an admin sets it.

### OFFENE FRAGE (blocking for the default configuration, not for the code)

§3.2 states the Leser navigation is limited to *"Dashboard, Artefakte (read-only), Verknüpfungen, Baselines, Freigaben (nur eigene)"* — 5 areas. §7.2 simultaneously instructs that the migration seeds the **current** hardcoded state, under which a viewer sees ~23 of the 25 entries. These two are incompatible.

**Working assumption taken by this plan (documented, reversible in the UI without a deploy):** §7 is the normative migration section, so the shipped default is **no change** (empty `visibility_json`; a viewer keeps today's sidebar minus the two admin pages). §3.2's 5-item list is treated as an *illustration of what an admin can now configure*, not as a shipped default. If the intent was the opposite, the fix is a single `PUT /navigation-visibility-defaults/` — no code change, no migration. **Needs a human decision before rollout, not before implementation.**

Secondary, non-blocking: §3.2's "Freigaben (nur eigene)" implies a per-user filter on `/reviews` that does not exist today. Out of scope for this plan — flagged for the reviewer.

---

## File Structure

```
backend/
  auth_tenancy/
    models.py                                   MODIFY  + GlobalNavigationVisibility, WorkspaceNavigationVisibility
    migrations/00XX_navigation_visibility.py    CREATE
    services/
      navigation_visibility.py                  CREATE  NavigationVisibilityService, validate_visibility_map
      __init__.py                               MODIFY  re-export
      profile_service.py                        MODIFY  expert_mode_enabled write path
    tests/
      test_navigation_visibility_service.py     CREATE
  persistence/
    models.py                                   MODIFY  User.expert_mode_enabled
    migrations/00XX_user_expert_mode.py         CREATE
  workflow/
    definition_store.py                         (read only — get_state_meta reused as-is)
  application/
    workflow_facade.py                          MODIFY  + get_state_meta()
    workspace_provisioning.py                   MODIFY  + navigation provisioning
  rest_api/
    global_default_views.py                     MODIFY  + 3 navigation-visibility views
    urls.py                                     MODIFY  + 3 routes
    auth_views.py                               MODIFY  _user_payload + expert_mode_enabled
    serializers.py                              MODIFY  UserProfileSerializer WRITABLE_FIELDS
    mixins/workflow_transitions.py              MODIFY  + fields_locked in GET envelope
    tests/
      test_navigation_visibility_api.py         CREATE
      test_expert_mode_profile.py               CREATE
      test_transitions_fields_locked.py         CREATE

frontend/src/
  hooks/
    useHasRole.ts                               MODIFY  widen RequiredRole, add useViewRole
  api/
    navigation-visibility.ts                    CREATE
  context/
    AuthContext.tsx                             MODIFY  expertModeEnabled + setExpertMode
  components/
    NavigationShell/
      SidebarNavigation.tsx                     MODIFY  NavItem.key + data-driven gate
      NavigationShell.tsx                       MODIFY  reader default entry (Task 18)
    SystemSettings/
      NavigationVisibilityEditor.tsx            CREATE  scope="global" | "workspace"
      SystemSettings.tsx                        MODIFY  + navigation-visibility tab
    WorkspaceSettings/
      WorkspaceSettings.tsx                     MODIFY  + navigation-visibility tab
    shared/
      ExpertModeToggle.tsx                      CREATE
      ArtifactForm/ArtifactForm.tsx             MODIFY  (Spec 2 artifact) audience collapse + mode
    AttributeEditor/AttributeEditorPage.tsx     MODIFY  (Spec 2 artifact) "Nur für Experten" toggle
  i18n/locales/{de,en}.json                     MODIFY
  test/
    useViewRole.test.tsx                        CREATE
    navigationVisibility.test.tsx               CREATE
    SidebarNavigation.test.tsx                  MODIFY
    ExpertModeToggle.test.tsx                   CREATE
    NavigationVisibilityEditor.test.tsx         CREATE
    ArtifactFormAudience.test.tsx               CREATE
    ArtifactFormMode.test.tsx                   CREATE

e2e/tests/
  role-based-views.spec.ts                      CREATE
```

---

## Task 1: `WorkflowFacade.get_state_meta`

**Files:**
- Modify: `backend/application/workflow_facade.py` (append a method next to `get_definition`, currently at line 306)
- Test: `backend/rest_api/tests/test_transitions_fields_locked.py`

**Interfaces:**
- Consumes: `workflow.definition_store.get_state_meta(workflow_json: dict, state_name: str) -> dict` (exists, line 818)
- Produces: `WorkflowFacade.get_state_meta(ctx: AuthContext, *, item_type: str, workspace_id: UUID | str, state: str) -> dict[str, Any]`

- [ ] **Step 1: Write the failing test**

Create `backend/rest_api/tests/test_transitions_fields_locked.py`:

```python
"""Rollenbasierte Sichten §3.2 — per-state field lock via workflow state_meta."""
from __future__ import annotations

import pytest

from application.workflow_facade import WorkflowFacade
from application.workspace_service import WorkspaceService
from auth_tenancy.context import AuthContext, AuthMethod
from persistence.models import Tenant, User
from persistence.tenancy import TenantContext
from workflow.models import WorkflowEngineDefinition


@pytest.fixture
def wf_ctx(db):
    tenant = Tenant.objects.create(name="FieldsLockedTenant")
    TenantContext.set_tenant(tenant.id)
    user = User.objects.create(
        tenant=tenant, username="fluser", email="fl@x.io", is_active=True
    )
    ctx = AuthContext(
        user_id=user.id,
        tenant_id=tenant.id,
        active_roles=("admin",),
        auth_method=AuthMethod.BEARER_TOKEN,
    )
    ws = WorkspaceService().create_workspace(ctx, name="FLWS", preset="standard")
    yield ctx, ws
    TenantContext.clear_tenant()


@pytest.mark.django_db
def test_get_state_meta_defaults_to_unlocked(wf_ctx):
    ctx, ws = wf_ctx
    meta = WorkflowFacade().get_state_meta(
        ctx, item_type="Requirement", workspace_id=ws.id, state="approved"
    )
    assert meta["fields_locked"] is False


@pytest.mark.django_db
def test_get_state_meta_reads_a_configured_lock(wf_ctx):
    ctx, ws = wf_ctx
    definition = WorkflowEngineDefinition.unscoped.get(
        tenant_id=ctx.tenant_id, workspace_id=ws.id, item_type="Requirement"
    )
    wf = dict(definition.workflow_json)
    wf["state_meta"] = {"approved": {"fields_locked": True}}
    definition.workflow_json = wf
    definition.save(update_fields=["workflow_json"])

    meta = WorkflowFacade().get_state_meta(
        ctx, item_type="Requirement", workspace_id=ws.id, state="approved"
    )
    assert meta["fields_locked"] is True
    # An unrelated state stays unlocked.
    other = WorkflowFacade().get_state_meta(
        ctx, item_type="Requirement", workspace_id=ws.id, state="draft"
    )
    assert other["fields_locked"] is False


@pytest.mark.django_db
def test_get_state_meta_on_a_missing_definition_is_unlocked(wf_ctx):
    ctx, ws = wf_ctx
    meta = WorkflowFacade().get_state_meta(
        ctx, item_type="NoSuchType", workspace_id=ws.id, state="approved"
    )
    assert meta["fields_locked"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm backend-test pytest rest_api/tests/test_transitions_fields_locked.py -v`
Expected: FAIL with `AttributeError: 'WorkflowFacade' object has no attribute 'get_state_meta'`

- [ ] **Step 3: Write minimal implementation**

Append to `backend/application/workflow_facade.py` (after `get_definition`):

```python
    def get_state_meta(
        self,
        ctx: AuthContext,
        *,
        item_type: str = "Requirement",
        workspace_id: UUID | str,
        state: str,
    ) -> dict[str, Any]:
        """Return per-state metadata for one workflow state (read-only).

        Extends the existing ``state_meta`` extension point (which already
        carries ``is_outdated_equivalent`` / ``auto_approve_target``) with
        ``fields_locked`` — Rollenbasierte-Sichten §3.2: an artifact sitting in
        a ``fields_locked`` state is field-read-only for every role except
        ``admin``; its status can still be moved via an allowed transition.

        Never raises for "not configured": a workspace without a definition, or
        a state without a ``state_meta`` entry, resolves to all-false so the
        default is always the permissive, pre-existing behaviour.
        """
        self._set_tenant_context(ctx)

        from workflow.definition_store import get_state_meta as wf_state_meta
        from workflow.models import WorkflowEngineDefinition

        definition = WorkflowEngineDefinition.unscoped.filter(
            tenant_id=ctx.tenant_id,
            workspace_id=workspace_id,
            item_type=item_type,
        ).first()
        workflow_json = definition.workflow_json if definition else {}
        meta = wf_state_meta(workflow_json or {}, state)
        return {"fields_locked": False, **meta}
```

Ensure `from typing import Any` and `from uuid import UUID` are imported at the top of the module (both are already used by neighbouring methods; add whichever is missing).

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm backend-test pytest rest_api/tests/test_transitions_fields_locked.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/application/workflow_facade.py backend/rest_api/tests/test_transitions_fields_locked.py
git commit -m "feat: read fields_locked from workflow state_meta"
```

---

## Task 2: Surface `fields_locked` on the transitions envelope

**Files:**
- Modify: `backend/rest_api/mixins/workflow_transitions.py:184-199` (the GET branch of `transitions`)
- Test: `backend/rest_api/tests/test_transitions_fields_locked.py` (append)

**Interfaces:**
- Consumes: `WorkflowFacade.get_state_meta(ctx, *, item_type, workspace_id, state) -> dict[str, Any]` (Task 1)
- Produces: `GET /{resource}/{id}/transitions/` response gains `"fields_locked": bool` (additive; existing keys unchanged)

- [ ] **Step 1: Write the failing test**

Append to `backend/rest_api/tests/test_transitions_fields_locked.py`:

```python
from django.test import override_settings
from rest_framework.test import APIClient

_JWT = dict(
    AUTH_JWT_SECRET="test-secret-not-a-real-key",
    AUTH_JWT_ISSUER="reqflow",
    AUTH_JWT_AUDIENCE="reqflow-api",
    AUTH_JWT_TTL_SECONDS=3600,
)


@pytest.fixture
def api_client_with_requirement(db):
    from application.requirement_service import RequirementService

    tenant = Tenant.objects.create(name="FieldsLockedApiTenant")
    TenantContext.set_tenant(tenant.id)
    user = User.objects.create(
        tenant=tenant, username="fladmin", email="fla@x.io", is_active=True
    )
    user.set_password("flpass12345")
    user.save()
    ctx = AuthContext(
        user_id=user.id,
        tenant_id=tenant.id,
        active_roles=("admin",),
        auth_method=AuthMethod.BEARER_TOKEN,
    )
    ws = WorkspaceService().create_workspace(ctx, name="FLApiWS", preset="standard")
    req = RequirementService().create_requirement(
        ctx, workspace_id=ws.id, title="Locked probe", description="d"
    )

    client = APIClient()
    with override_settings(**_JWT):
        resp = client.post(
            "/api/v1/auth/login/",
            {"username": "fladmin", "password": "flpass12345"},
            format="json",
        )
        assert resp.status_code == 200, resp.content
        token = resp.json()["token"]
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    TenantContext.clear_tenant()
    return client, ctx, ws, req


@override_settings(**_JWT)
@pytest.mark.django_db
def test_transitions_get_reports_fields_locked_false_by_default(
    api_client_with_requirement,
):
    client, ctx, ws, req = api_client_with_requirement
    resp = client.get(f"/api/v1/requirements/{req.id}/transitions/")
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["fields_locked"] is False
    # Additive only — the pre-existing envelope keys are untouched.
    assert set(["current_state", "states", "allowed_transitions"]) <= set(body)


@override_settings(**_JWT)
@pytest.mark.django_db
def test_transitions_get_reports_fields_locked_for_the_current_state(
    api_client_with_requirement,
):
    client, ctx, ws, req = api_client_with_requirement
    definition = WorkflowEngineDefinition.unscoped.get(
        tenant_id=ctx.tenant_id, workspace_id=ws.id, item_type="Requirement"
    )
    current = client.get(f"/api/v1/requirements/{req.id}/transitions/").json()[
        "current_state"
    ]
    wf = dict(definition.workflow_json)
    wf["state_meta"] = {current: {"fields_locked": True}}
    definition.workflow_json = wf
    definition.save(update_fields=["workflow_json"])

    resp = client.get(f"/api/v1/requirements/{req.id}/transitions/")
    assert resp.status_code == 200, resp.content
    assert resp.json()["fields_locked"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm backend-test pytest rest_api/tests/test_transitions_fields_locked.py -k fields_locked_ -v`
Expected: FAIL with `KeyError: 'fields_locked'`

- [ ] **Step 3: Write minimal implementation**

In `backend/rest_api/mixins/workflow_transitions.py`, replace the GET `Response(...)` block (currently lines 184-199) with:

```python
            # Rollenbasierte Sichten §3.2: the form mode derives from role AND
            # workflow state. `fields_locked` reports whether the CURRENT state
            # freezes field edits (status changes stay possible through an
            # allowed transition). Defaults to False, so no existing workspace
            # changes behaviour until an admin sets state_meta.<state>.
            fields_locked = bool(
                facade.get_state_meta(
                    ctx,
                    item_type=self.workflow_item_type,
                    workspace_id=workspace_id,
                    state=avail.current_state or "",
                ).get("fields_locked", False)
            )
            return Response(
                {
                    "current_state": avail.current_state,
                    "states": list(avail.states),
                    "fields_locked": fields_locked,
                    "allowed_transitions": [
                        {
                            "target_state": t.to_state,
                            "requires_change_reason": (
                                t.requires_change_reason or preset_requires
                            ),
                            "signature_gate": t.signature_gate,
                        }
                        for t in avail.transitions
                    ],
                }
            )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm backend-test pytest rest_api/tests/test_transitions_fields_locked.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/rest_api/mixins/workflow_transitions.py backend/rest_api/tests/test_transitions_fields_locked.py
git commit -m "feat: expose fields_locked on the transitions envelope"
```

---

## Task 3: `User.expert_mode_enabled` field + migration

**Files:**
- Modify: `backend/persistence/models.py` (inside `class User`, after `is_active`, currently line 501)
- Create: `backend/persistence/migrations/00XX_user_expert_mode.py` (generated)
- Test: `backend/rest_api/tests/test_expert_mode_profile.py`

**Interfaces:**
- Produces: `persistence.models.User.expert_mode_enabled: bool` (default `False`, non-null)

- [ ] **Step 1: Write the failing test**

Create `backend/rest_api/tests/test_expert_mode_profile.py`:

```python
"""Rollenbasierte Sichten §5 — expert mode is a user preference, not a right."""
from __future__ import annotations

import pytest

from persistence.models import Tenant, User
from persistence.tenancy import TenantContext


@pytest.mark.django_db
def test_expert_mode_defaults_to_false():
    tenant = Tenant.objects.create(name="ExpertModeTenant")
    TenantContext.set_tenant(tenant.id)
    try:
        user = User.objects.create(
            tenant=tenant, username="emuser", email="em@x.io", is_active=True
        )
        user.refresh_from_db()
        assert user.expert_mode_enabled is False
    finally:
        TenantContext.clear_tenant()


@pytest.mark.django_db
def test_expert_mode_is_persistable():
    tenant = Tenant.objects.create(name="ExpertModeTenant2")
    TenantContext.set_tenant(tenant.id)
    try:
        user = User.objects.create(
            tenant=tenant, username="emuser2", email="em2@x.io", is_active=True
        )
        user.expert_mode_enabled = True
        user.save(update_fields=["expert_mode_enabled"])
        user.refresh_from_db()
        assert user.expert_mode_enabled is True
    finally:
        TenantContext.clear_tenant()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm backend-test pytest rest_api/tests/test_expert_mode_profile.py -v --create-db`
Expected: FAIL with `AttributeError: 'User' object has no attribute 'expert_mode_enabled'`

- [ ] **Step 3: Write minimal implementation**

In `backend/persistence/models.py`, inside `class User`, directly after the `is_active` field:

```python
    # Rollenbasierte Sichten §5 — pure UI preference: expands
    # `audience="expert"` form sections by default. NOT a permission: the
    # switch changes what is initially visible, never what the user may do.
    # Additive with a False default so every existing row stays valid without
    # a backfill.
    expert_mode_enabled = models.BooleanField(default=False)
```

Generate the migration:

```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm backend-test python manage.py makemigrations persistence --name user_expert_mode
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm backend-test pytest rest_api/tests/test_expert_mode_profile.py -v --create-db`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/persistence/models.py backend/persistence/migrations/ backend/rest_api/tests/test_expert_mode_profile.py
git commit -m "feat: add User.expert_mode_enabled preference flag"
```

---

## Task 4: `/auth/me/` reads and writes `expert_mode_enabled`

**Files:**
- Modify: `backend/rest_api/auth_views.py:154-165` (`_user_payload`)
- Modify: `backend/rest_api/serializers.py:1929` (`UserProfileSerializer.WRITABLE_FIELDS`) and its field list + `update()`
- Modify: `backend/auth_tenancy/services/profile_service.py:24,50-58`
- Test: `backend/rest_api/tests/test_expert_mode_profile.py` (append)

**Interfaces:**
- Consumes: `User.expert_mode_enabled` (Task 3)
- Produces: `GET/PATCH /api/v1/auth/me/` payload key `user.expert_mode_enabled: bool`; `PATCH` body accepts `{"expert_mode_enabled": bool}`

- [ ] **Step 1: Write the failing test**

Append to `backend/rest_api/tests/test_expert_mode_profile.py`:

```python
from django.test import override_settings
from rest_framework.test import APIClient

_JWT = dict(
    AUTH_JWT_SECRET="test-secret-not-a-real-key",
    AUTH_JWT_ISSUER="reqflow",
    AUTH_JWT_AUDIENCE="reqflow-api",
    AUTH_JWT_TTL_SECONDS=3600,
)


@pytest.fixture
def me_client(db):
    tenant = Tenant.objects.create(name="MeTenant")
    TenantContext.set_tenant(tenant.id)
    user = User.objects.create(
        tenant=tenant, username="meuser", email="me@x.io", is_active=True
    )
    user.set_password("mepass123456")
    user.save()
    client = APIClient()
    with override_settings(**_JWT):
        resp = client.post(
            "/api/v1/auth/login/",
            {"username": "meuser", "password": "mepass123456"},
            format="json",
        )
        assert resp.status_code == 200, resp.content
        token = resp.json()["token"]
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    TenantContext.clear_tenant()
    return client, user


@override_settings(**_JWT)
@pytest.mark.django_db
def test_me_reports_expert_mode(me_client):
    client, _user = me_client
    resp = client.get("/api/v1/auth/me/")
    assert resp.status_code == 200, resp.content
    assert resp.json()["user"]["expert_mode_enabled"] is False


@override_settings(**_JWT)
@pytest.mark.django_db
def test_me_patch_toggles_expert_mode(me_client):
    client, user = me_client
    resp = client.patch(
        "/api/v1/auth/me/", {"expert_mode_enabled": True}, format="json"
    )
    assert resp.status_code == 200, resp.content
    assert resp.json()["user"]["expert_mode_enabled"] is True
    user.refresh_from_db()
    assert user.expert_mode_enabled is True


@override_settings(**_JWT)
@pytest.mark.django_db
def test_me_patch_still_rejects_protected_fields(me_client):
    """QIRK-002 must keep holding — expert mode is not a hole in the allowlist."""
    client, _user = me_client
    resp = client.patch("/api/v1/auth/me/", {"roles": ["admin"]}, format="json")
    assert resp.status_code == 400
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm backend-test pytest rest_api/tests/test_expert_mode_profile.py -k me_ -v`
Expected: FAIL — first test with `KeyError: 'expert_mode_enabled'`

- [ ] **Step 3: Write minimal implementation**

(a) `backend/rest_api/auth_views.py` — add one key to `_user_payload`:

```python
def _user_payload(user: Any, roles: tuple[str, ...]) -> dict[str, Any]:
    """Serialise the public-safe user fields for login / me responses."""
    return {
        "id": str(user.id),
        "username": user.username,
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "is_active": user.is_active,
        "tenant_id": str(user.tenant_id) if user.tenant_id else None,
        "roles": list(roles),
        # Rollenbasierte Sichten §5 — UI preference, rides the identity
        # payload the SPA already fetches so no extra round trip is needed.
        "expert_mode_enabled": bool(getattr(user, "expert_mode_enabled", False)),
    }
```

(b) `backend/rest_api/serializers.py` — in `UserProfileSerializer`:

```python
    #: Writable via this endpoint. Everything else in the payload is an error.
    WRITABLE_FIELDS = ("first_name", "last_name", "expert_mode_enabled")
```

Add the field declaration after `is_active`:

```python
    # Rollenbasierte Sichten §5 — a display-density preference, deliberately in
    # the same writable set as the display name: it grants no capability, so it
    # does not belong in PROTECTED_FIELDS.
    expert_mode_enabled = serializers.BooleanField(required=False)
```

Extend `update()` so the boolean is not `.strip()`-ed like the name fields:

```python
    def update(self, instance: Any, validated_data: dict[str, Any]) -> Any:
        """Apply profile changes to ``instance`` and persist them.

        Only fields present in ``validated_data`` are touched (PATCH
        semantics). String fields are trimmed; ``expert_mode_enabled`` is a
        boolean and must not go through the string path.
        """
        updated_fields: list[str] = []
        for field in ("first_name", "last_name"):
            if field in validated_data:
                setattr(instance, field, validated_data[field].strip())
                updated_fields.append(field)
        if "expert_mode_enabled" in validated_data:
            instance.expert_mode_enabled = bool(validated_data["expert_mode_enabled"])
            updated_fields.append("expert_mode_enabled")
        if updated_fields:
            instance.save(update_fields=updated_fields)
        return instance
```

(c) `backend/auth_tenancy/services/profile_service.py` — the view persists through the service, so mirror the same split there:

```python
# Fields a user may edit on their own profile.
_EDITABLE_PROFILE_FIELDS = ("first_name", "last_name")
# Boolean preference fields — must not go through the ``.strip()`` path above.
_EDITABLE_PROFILE_FLAGS = ("expert_mode_enabled",)
```

and inside `update_profile`, after the existing string loop:

```python
        for field in _EDITABLE_PROFILE_FLAGS:
            if field in validated_data:
                setattr(user, field, bool(validated_data[field]))
                updated_fields.append(field)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm backend-test pytest rest_api/tests/test_expert_mode_profile.py auth_tenancy/tests/ -v`
Expected: PASS (5 new tests pass; no regression in `auth_tenancy/tests/`)

- [ ] **Step 5: Commit**

```bash
git add backend/rest_api/auth_views.py backend/rest_api/serializers.py backend/auth_tenancy/services/profile_service.py backend/rest_api/tests/test_expert_mode_profile.py
git commit -m "feat: read and write expert_mode_enabled via /auth/me/"
```

---

## Task 5: Navigation-visibility models + migration

**Files:**
- Modify: `backend/auth_tenancy/models.py` (append after `WorkspacePermissionDefinition`, currently ending near line 575)
- Create: `backend/auth_tenancy/migrations/00XX_navigation_visibility.py` (generated)
- Test: `backend/auth_tenancy/tests/test_navigation_visibility_service.py`

**Interfaces:**
- Produces: `auth_tenancy.models.GlobalNavigationVisibility` (fields: `tenant`, `visibility_json`, `version`), `auth_tenancy.models.WorkspaceNavigationVisibility` (fields: `tenant`, `workspace`, `visibility_json`, `source_global`, `is_customized`, `version`)

- [ ] **Step 1: Write the failing test**

Create `backend/auth_tenancy/tests/test_navigation_visibility_service.py`:

```python
"""Rollenbasierte Sichten §3.1 — navigation visibility as a system object."""
from __future__ import annotations

import pytest

from auth_tenancy.models import (
    GlobalNavigationVisibility,
    WorkspaceNavigationVisibility,
)
from persistence.models import Tenant, Workspace
from persistence.tenancy import TenantContext


@pytest.fixture
def nav_tenant(db):
    tenant = Tenant.objects.create(name="NavVisTenant")
    TenantContext.set_tenant(tenant.id)
    workspace = Workspace.objects.create(tenant=tenant, name="NavWS")
    yield tenant, workspace
    TenantContext.clear_tenant()


@pytest.mark.django_db
def test_global_row_is_unique_per_tenant(nav_tenant):
    tenant, _ws = nav_tenant
    GlobalNavigationVisibility.unscoped.create(
        tenant_id=tenant.id, visibility_json={"system-settings": "admin"}
    )
    with pytest.raises(Exception):
        GlobalNavigationVisibility.unscoped.create(
            tenant_id=tenant.id, visibility_json={}
        )


@pytest.mark.django_db
def test_workspace_row_links_back_to_the_global(nav_tenant):
    tenant, ws = nav_tenant
    global_row = GlobalNavigationVisibility.unscoped.create(
        tenant_id=tenant.id, visibility_json={"workflows": "editor"}
    )
    ws_row = WorkspaceNavigationVisibility.unscoped.create(
        tenant_id=tenant.id,
        workspace_id=ws.id,
        visibility_json={"workflows": "editor"},
        source_global=global_row,
        is_customized=False,
    )
    assert ws_row.source_global_id == global_row.id
    assert ws_row.is_customized is False
    assert ws_row.version == 1


@pytest.mark.django_db
def test_deleting_the_global_does_not_delete_the_override(nav_tenant):
    tenant, ws = nav_tenant
    global_row = GlobalNavigationVisibility.unscoped.create(
        tenant_id=tenant.id, visibility_json={}
    )
    ws_row = WorkspaceNavigationVisibility.unscoped.create(
        tenant_id=tenant.id,
        workspace_id=ws.id,
        visibility_json={"audit": "admin"},
        source_global=global_row,
        is_customized=True,
    )
    global_row.delete()
    ws_row.refresh_from_db()
    assert ws_row.source_global_id is None
    assert ws_row.visibility_json == {"audit": "admin"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm backend-test pytest auth_tenancy/tests/test_navigation_visibility_service.py -v --create-db`
Expected: FAIL with `ImportError: cannot import name 'GlobalNavigationVisibility' from 'auth_tenancy.models'`

- [ ] **Step 3: Write minimal implementation**

Append to `backend/auth_tenancy/models.py`:

```python
class GlobalNavigationVisibility(TenantScopedModel):
    """Tenant-wide navigation-visibility defaults (Rollenbasierte Sichten §3.1).

    ``visibility_json`` maps a stable ``nav_item_key`` to the role required to
    SEE that navigation entry::

        {"system-settings": "admin", "workflows": "editor", "audit": null}

    ``null`` means "visible to every authenticated role". A key that is ABSENT
    falls back to the frontend's coded default (``NAV_ITEMS[].requires``), so an
    empty map is exactly the shipped behaviour and no bootstrap seed is needed.

    NOT a security boundary: hiding an entry does not stop a direct URL call —
    the route/API RBAC check remains the actual gate. Exactly one row per
    tenant, mirroring :class:`GlobalPermissionDefinition`.
    """

    visibility_json = models.JSONField(default=dict)
    version = models.IntegerField(default=1)

    class Meta:
        db_table = "at_global_navigation_visibility"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant"],
                name="uq_global_nav_vis_tenant",
            )
        ]

    def __str__(self) -> str:
        return f"GlobalNavVisibility(tenant:{self.tenant_id})"


class WorkspaceNavigationVisibility(TenantScopedModel):
    """Per-workspace navigation-visibility override (Rollenbasierte Sichten §3.1).

    Materialized copy of :class:`GlobalNavigationVisibility`, structurally
    identical to :class:`WorkspacePermissionDefinition`: ``source_global`` is
    SET_NULL (deleting the tenant default must never cascade-delete a live
    override) and ``is_customized`` is the on-default/customized signal that
    reset-to-default clears.
    """

    workspace = models.ForeignKey(
        "persistence.Workspace",
        on_delete=models.CASCADE,
        related_name="navigation_visibilities",
    )
    visibility_json = models.JSONField(default=dict)
    source_global = models.ForeignKey(
        "auth_tenancy.GlobalNavigationVisibility",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="derived_definitions",
    )
    is_customized = models.BooleanField(default=False)
    version = models.IntegerField(default=1)

    class Meta:
        db_table = "at_workspace_navigation_visibility"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "workspace"],
                name="uq_ws_nav_vis_tenant_ws",
            )
        ]
        indexes = [
            models.Index(
                fields=["workspace"],
                name="idx_ws_nav_vis_workspace",
            )
        ]

    def __str__(self) -> str:
        return f"WorkspaceNavVisibility(ws:{self.workspace_id})"
```

Add both names to the module's `__all__` if one is defined. Generate the migration:

```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm backend-test python manage.py makemigrations auth_tenancy --name navigation_visibility
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm backend-test pytest auth_tenancy/tests/test_navigation_visibility_service.py -v --create-db`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/auth_tenancy/models.py backend/auth_tenancy/migrations/ backend/auth_tenancy/tests/test_navigation_visibility_service.py
git commit -m "feat: add navigation-visibility system-object models"
```

---

## Task 6: `NavigationVisibilityService`

**Files:**
- Create: `backend/auth_tenancy/services/navigation_visibility.py`
- Modify: `backend/auth_tenancy/services/__init__.py` (re-export)
- Test: `backend/auth_tenancy/tests/test_navigation_visibility_service.py` (append)

**Interfaces:**
- Consumes: `GlobalNavigationVisibility`, `WorkspaceNavigationVisibility` (Task 5); `application.base.ServiceBase`; `auth_tenancy.context.AuthContext`
- Produces:
  - `validate_visibility_map(data: object) -> dict[str, str | None]` (raises `NavigationVisibilityError`)
  - `NavigationVisibilityService.get_or_create_global(tenant_id) -> GlobalNavigationVisibility`
  - `NavigationVisibilityService.replace_global(ctx, mapping) -> tuple[GlobalNavigationVisibility, int]`
  - `NavigationVisibilityService.get_or_create_workspace(tenant_id, workspace_id) -> WorkspaceNavigationVisibility`
  - `NavigationVisibilityService.replace_workspace(ctx, workspace_id, mapping) -> WorkspaceNavigationVisibility`
  - `NavigationVisibilityService.reset_workspace(ctx, workspace_id) -> WorkspaceNavigationVisibility` (raises `NoNavigationGlobalSourceError`)
  - `NavigationVisibilityService.provision_workspace(tenant_id, workspace_id) -> WorkspaceNavigationVisibility`

- [ ] **Step 1: Write the failing test**

Append to `backend/auth_tenancy/tests/test_navigation_visibility_service.py`:

```python
from auth_tenancy.context import AuthContext, AuthMethod
from auth_tenancy.services.navigation_visibility import (
    NavigationVisibilityError,
    NavigationVisibilityService,
    NoNavigationGlobalSourceError,
    validate_visibility_map,
)
from persistence.models import User


@pytest.fixture
def nav_ctx(nav_tenant):
    tenant, ws = nav_tenant
    user = User.objects.create(
        tenant=tenant, username="navadmin", email="nav@x.io", is_active=True
    )
    ctx = AuthContext(
        user_id=user.id,
        tenant_id=tenant.id,
        active_roles=("admin",),
        auth_method=AuthMethod.BEARER_TOKEN,
    )
    return ctx, ws


def test_validate_accepts_known_roles_and_null():
    assert validate_visibility_map(
        {"system-settings": "admin", "audit": None, "workflows": "approver"}
    ) == {"system-settings": "admin", "audit": None, "workflows": "approver"}


def test_validate_rejects_an_unknown_role():
    with pytest.raises(NavigationVisibilityError):
        validate_visibility_map({"audit": "superuser"})


def test_validate_rejects_a_malformed_key():
    with pytest.raises(NavigationVisibilityError):
        validate_visibility_map({"Audit Page!": "admin"})


def test_validate_rejects_a_non_object():
    with pytest.raises(NavigationVisibilityError):
        validate_visibility_map(["audit"])


def test_validate_rejects_too_many_keys():
    with pytest.raises(NavigationVisibilityError):
        validate_visibility_map({f"item-{i}": None for i in range(201)})


@pytest.mark.django_db
def test_global_is_seeded_empty(nav_ctx):
    ctx, _ws = nav_ctx
    obj = NavigationVisibilityService().get_or_create_global(ctx.tenant_id)
    assert obj.visibility_json == {}


@pytest.mark.django_db
def test_replace_global_propagates_into_on_default_workspaces(nav_ctx):
    ctx, ws = nav_ctx
    svc = NavigationVisibilityService()
    svc.provision_workspace(ctx.tenant_id, ws.id)

    obj, propagated = svc.replace_global(ctx, {"audit": "admin"})
    assert obj.visibility_json == {"audit": "admin"}
    assert propagated == 1

    ws_row = svc.get_or_create_workspace(ctx.tenant_id, ws.id)
    assert ws_row.visibility_json == {"audit": "admin"}
    assert ws_row.is_customized is False


@pytest.mark.django_db
def test_replace_global_skips_customized_workspaces(nav_ctx):
    ctx, ws = nav_ctx
    svc = NavigationVisibilityService()
    svc.replace_workspace(ctx, ws.id, {"audit": "editor"})

    _obj, propagated = svc.replace_global(ctx, {"audit": "admin"})
    assert propagated == 0

    ws_row = svc.get_or_create_workspace(ctx.tenant_id, ws.id)
    assert ws_row.visibility_json == {"audit": "editor"}
    assert ws_row.is_customized is True


@pytest.mark.django_db
def test_reset_workspace_restores_the_global(nav_ctx):
    ctx, ws = nav_ctx
    svc = NavigationVisibilityService()
    svc.replace_global(ctx, {"audit": "admin"})
    svc.replace_workspace(ctx, ws.id, {"audit": "editor"})

    ws_row = svc.reset_workspace(ctx, ws.id)
    assert ws_row.visibility_json == {"audit": "admin"}
    assert ws_row.is_customized is False


@pytest.mark.django_db
def test_reset_without_a_linked_global_raises(nav_ctx):
    ctx, ws = nav_ctx
    svc = NavigationVisibilityService()
    row = svc.get_or_create_workspace(ctx.tenant_id, ws.id)
    row.source_global = None
    row.save(update_fields=["source_global"])
    with pytest.raises(NoNavigationGlobalSourceError):
        svc.reset_workspace(ctx, ws.id)


@pytest.mark.django_db
def test_replace_bumps_the_version(nav_ctx):
    ctx, _ws = nav_ctx
    svc = NavigationVisibilityService()
    first, _ = svc.replace_global(ctx, {"audit": "admin"})
    assert first.version == 2
    second, _ = svc.replace_global(ctx, {"audit": "editor"})
    assert second.version == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm backend-test pytest auth_tenancy/tests/test_navigation_visibility_service.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'auth_tenancy.services.navigation_visibility'`

- [ ] **Step 3: Write minimal implementation**

Create `backend/auth_tenancy/services/navigation_visibility.py`:

```python
"""Navigation-visibility service (Rollenbasierte Sichten §3.1).

Global (tenant singleton) + workspace override for the role a navigation entry
requires to be RENDERED. Structurally identical to
:mod:`auth_tenancy.services.permission_definition`: get-or-create, replace with
propagation into ``is_customized=False`` derived rows, and reset-to-default.

NOT an authorization mechanism. Hiding a nav entry does not block the route it
points at — the server-side RBAC check on the route/API remains the only gate.
An entry made visible here that the server then rejects is a UX defect, not a
privilege escalation.
"""
from __future__ import annotations

import copy
import re
from typing import Any
from uuid import UUID

from django.db import transaction

from application.base import ServiceBase
from auth_tenancy.context import AuthContext
from auth_tenancy.models import (
    GlobalNavigationVisibility,
    ROLE_ADMIN,
    ROLE_APPROVER,
    ROLE_EDITOR,
    ROLE_VIEWER,
    WorkspaceNavigationVisibility,
)

#: Roles a nav entry may require. ``None`` means "any authenticated role".
ALLOWED_REQUIRED_ROLES = frozenset(
    {ROLE_ADMIN, ROLE_EDITOR, ROLE_VIEWER, ROLE_APPROVER}
)

#: Upper bound on stored keys — the frontend has ~25 nav entries; 200 leaves
#: generous headroom while keeping an unbounded-JSON write off the table.
MAX_NAV_ITEM_KEYS = 200

#: A nav_item_key is a stable slug owned by the frontend routing table.
_NAV_ITEM_KEY_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")


class NavigationVisibilityError(ValueError):
    """The supplied visibility map is structurally invalid."""


class NoNavigationGlobalSourceError(Exception):
    """A workspace override has no linked global default to reset to."""


def validate_visibility_map(data: object) -> dict[str, str | None]:
    """Validate and normalise a ``{nav_item_key: required_role | None}`` map.

    Args:
        data: Raw JSON body value.

    Returns:
        A new dict with validated keys and values.

    Raises:
        NavigationVisibilityError: Not an object, too many keys, a malformed
            key, or a role outside :data:`ALLOWED_REQUIRED_ROLES`.
    """
    if not isinstance(data, dict):
        raise NavigationVisibilityError("visibility_json must be a JSON object.")
    if len(data) > MAX_NAV_ITEM_KEYS:
        raise NavigationVisibilityError(
            f"visibility_json may contain at most {MAX_NAV_ITEM_KEYS} keys."
        )
    cleaned: dict[str, str | None] = {}
    for key, value in data.items():
        if not isinstance(key, str) or not _NAV_ITEM_KEY_RE.match(key):
            raise NavigationVisibilityError(
                f"Invalid nav_item_key {key!r}: expected a lowercase slug "
                f"(a-z, 0-9, '-'), max 64 characters."
            )
        if value is None:
            cleaned[key] = None
            continue
        if not isinstance(value, str) or value not in ALLOWED_REQUIRED_ROLES:
            raise NavigationVisibilityError(
                f"Invalid required_role {value!r} for {key!r}: expected null or "
                f"one of {sorted(ALLOWED_REQUIRED_ROLES)}."
            )
        cleaned[key] = value
    return cleaned


class NavigationVisibilityService(ServiceBase):
    """CRUD + inheritance for navigation-visibility definitions."""

    # ---------- Global (tenant-wide singleton) ----------

    def get_or_create_global(
        self, tenant_id: UUID | str
    ) -> GlobalNavigationVisibility:
        """Return the tenant global row, seeding an EMPTY map if absent.

        Empty is deliberate: an absent key falls back to the frontend's coded
        default, so a fresh tenant behaves exactly as before this feature
        existed (no bootstrap seed, no behaviour break).
        """
        obj, _created = GlobalNavigationVisibility.unscoped.get_or_create(
            tenant_id=tenant_id, defaults={"visibility_json": {}}
        )
        return obj

    def replace_global(
        self, ctx: AuthContext, mapping: object
    ) -> tuple[GlobalNavigationVisibility, int]:
        """Replace the tenant map and propagate into non-customized workspaces.

        Returns:
            ``(row, propagated_workspace_count)``.

        Raises:
            NavigationVisibilityError: The map is invalid.
        """
        self._set_tenant_context(ctx)
        normalised = validate_visibility_map(mapping)
        with transaction.atomic():
            obj = self.get_or_create_global(ctx.tenant_id)
            obj.visibility_json = normalised
            obj.version = obj.version + 1
            obj.save(update_fields=["visibility_json", "version", "modified_at"])
            propagated = WorkspaceNavigationVisibility.unscoped.filter(
                tenant_id=ctx.tenant_id, source_global_id=obj.id, is_customized=False
            ).update(visibility_json=copy.deepcopy(normalised))
            self._audit(
                ctx,
                operation="update",
                entity_type="GlobalNavigationVisibility",
                entity_id=obj.id,
                details={
                    "action": "replace_visibility",
                    "propagated_workspace_count": propagated,
                },
            )
        return obj, propagated

    # ---------- Workspace override ----------

    def get_or_create_workspace(
        self, tenant_id: UUID | str, workspace_id: UUID | str
    ) -> WorkspaceNavigationVisibility:
        """Return the workspace row, inheriting from the global if absent."""
        existing = WorkspaceNavigationVisibility.unscoped.filter(
            tenant_id=tenant_id, workspace_id=workspace_id
        ).first()
        if existing is not None:
            return existing
        global_row = self.get_or_create_global(tenant_id)
        obj, _created = WorkspaceNavigationVisibility.unscoped.get_or_create(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            defaults={
                "visibility_json": copy.deepcopy(global_row.visibility_json),
                "source_global_id": global_row.id,
                "is_customized": False,
            },
        )
        return obj

    def replace_workspace(
        self, ctx: AuthContext, workspace_id: UUID | str, mapping: object
    ) -> WorkspaceNavigationVisibility:
        """Override a workspace map (sets ``is_customized=True``)."""
        self._set_tenant_context(ctx)
        normalised = validate_visibility_map(mapping)
        with transaction.atomic():
            obj = self.get_or_create_workspace(ctx.tenant_id, workspace_id)
            obj.visibility_json = normalised
            obj.is_customized = True
            obj.version = obj.version + 1
            obj.save(
                update_fields=[
                    "visibility_json",
                    "is_customized",
                    "version",
                    "modified_at",
                ]
            )
            self._audit(
                ctx,
                operation="update",
                entity_type="WorkspaceNavigationVisibility",
                entity_id=obj.id,
                details={
                    "action": "replace_visibility",
                    "workspace_id": str(workspace_id),
                },
            )
        return obj

    def reset_workspace(
        self, ctx: AuthContext, workspace_id: UUID | str
    ) -> WorkspaceNavigationVisibility:
        """Reset a workspace map back to its linked global default.

        Raises:
            NoNavigationGlobalSourceError: ``source_global`` is null or gone.
        """
        self._set_tenant_context(ctx)
        with transaction.atomic():
            obj = self.get_or_create_workspace(ctx.tenant_id, workspace_id)
            global_row = (
                GlobalNavigationVisibility.unscoped.filter(
                    id=obj.source_global_id
                ).first()
                if obj.source_global_id
                else None
            )
            if global_row is None:
                raise NoNavigationGlobalSourceError(
                    "Workspace navigation visibility has no linked global "
                    "default to reset to."
                )
            obj.visibility_json = copy.deepcopy(global_row.visibility_json)
            obj.is_customized = False
            obj.version = obj.version + 1
            obj.save(
                update_fields=[
                    "visibility_json",
                    "is_customized",
                    "version",
                    "modified_at",
                ]
            )
            self._audit(
                ctx,
                operation="update",
                entity_type="WorkspaceNavigationVisibility",
                entity_id=obj.id,
                details={
                    "action": "reset_to_default",
                    "workspace_id": str(workspace_id),
                },
            )
        return obj

    # ---------- Provisioning (workspace creation) ----------

    def provision_workspace(
        self, tenant_id: UUID | str, workspace_id: UUID | str
    ) -> WorkspaceNavigationVisibility:
        """Link a newly created workspace to the tenant navigation global.

        Idempotent (``get_or_create`` all the way down), so a repeat run never
        overwrites an existing, possibly customised row.
        """
        return self.get_or_create_workspace(tenant_id, workspace_id)


__all__ = [
    "ALLOWED_REQUIRED_ROLES",
    "MAX_NAV_ITEM_KEYS",
    "NavigationVisibilityError",
    "NavigationVisibilityService",
    "NoNavigationGlobalSourceError",
    "validate_visibility_map",
]
```

Add to `backend/auth_tenancy/services/__init__.py` (alphabetical position, after the `.item_permission` import):

```python
from .navigation_visibility import (
    NavigationVisibilityError,
    NavigationVisibilityService,
    NoNavigationGlobalSourceError,
    validate_visibility_map,
)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm backend-test pytest auth_tenancy/tests/test_navigation_visibility_service.py -v`
Expected: PASS (13 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/auth_tenancy/services/navigation_visibility.py backend/auth_tenancy/services/__init__.py backend/auth_tenancy/tests/test_navigation_visibility_service.py
git commit -m "feat: add NavigationVisibilityService with global/workspace scopes"
```

---

## Task 7: REST endpoints for navigation visibility

**Files:**
- Modify: `backend/rest_api/global_default_views.py` (append a new section before `__all__`, currently line 760)
- Modify: `backend/rest_api/urls.py` (import block near line 105; route block near line 546)
- Test: `backend/rest_api/tests/test_navigation_visibility_api.py`

**Interfaces:**
- Consumes: `NavigationVisibilityService`, `validate_visibility_map`, `NavigationVisibilityError`, `NoNavigationGlobalSourceError` (Task 6)
- Produces:
  - `GET/PUT /api/v1/navigation-visibility-defaults/` — admin only. Body/response: `{"tenant_id", "visibility_json", "version", "updated_at"}`; `PUT` response additionally carries `"propagated_workspace_count"`.
  - `GET/PUT /api/v1/workspaces/<workspace_id>/navigation-visibility/` — **GET: any authenticated role** (the sidebar reads it), **PUT: admin only**. Response: `{"workspace_id", "visibility_json", "is_customized", "source_global_id", "version", "updated_at"}`.
  - `POST /api/v1/workspaces/<workspace_id>/navigation-visibility/reset/` — admin only.

- [ ] **Step 1: Write the failing test**

Create `backend/rest_api/tests/test_navigation_visibility_api.py`:

```python
"""Rollenbasierte Sichten §3.1/§6 — navigation-visibility REST contract."""
from __future__ import annotations

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from application.workspace_service import WorkspaceService
from auth_tenancy.context import AuthContext, AuthMethod
from persistence.models import Tenant, User
from persistence.tenancy import TenantContext

_JWT = dict(
    AUTH_JWT_SECRET="test-secret-not-a-real-key",
    AUTH_JWT_ISSUER="reqflow",
    AUTH_JWT_AUDIENCE="reqflow-api",
    AUTH_JWT_TTL_SECONDS=3600,
)


def _login(client: APIClient, username: str, password: str) -> None:
    with override_settings(**_JWT):
        resp = client.post(
            "/api/v1/auth/login/",
            {"username": username, "password": password},
            format="json",
        )
        assert resp.status_code == 200, resp.content
        token = resp.json()["token"]
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")


@pytest.fixture
def nav_api(db):
    from auth_tenancy.models import UserRole

    tenant = Tenant.objects.create(name="NavApiTenant")
    TenantContext.set_tenant(tenant.id)
    admin = User.objects.create(
        tenant=tenant, username="navapiadmin", email="naa@x.io", is_active=True
    )
    admin.set_password("navpass123456")
    admin.save()
    ctx = AuthContext(
        user_id=admin.id,
        tenant_id=tenant.id,
        active_roles=("admin",),
        auth_method=AuthMethod.BEARER_TOKEN,
    )
    ws = WorkspaceService().create_workspace(ctx, name="NavApiWS", preset="standard")

    viewer = User.objects.create(
        tenant=tenant, username="navapiviewer", email="nav@x.io", is_active=True
    )
    viewer.set_password("navpass123456")
    viewer.save()
    UserRole.objects.create(
        tenant=tenant, user=viewer, workspace_id=ws.id, role="viewer"
    )
    TenantContext.clear_tenant()

    admin_client = APIClient()
    _login(admin_client, "navapiadmin", "navpass123456")
    viewer_client = APIClient()
    _login(viewer_client, "navapiviewer", "navpass123456")
    return admin_client, viewer_client, ws


@override_settings(**_JWT)
@pytest.mark.django_db
def test_global_get_returns_an_empty_map_by_default(nav_api):
    admin_client, _viewer_client, _ws = nav_api
    resp = admin_client.get("/api/v1/navigation-visibility-defaults/")
    assert resp.status_code == 200, resp.content
    assert resp.json()["visibility_json"] == {}


@override_settings(**_JWT)
@pytest.mark.django_db
def test_global_put_stores_and_reports_propagation(nav_api):
    admin_client, _viewer_client, _ws = nav_api
    resp = admin_client.put(
        "/api/v1/navigation-visibility-defaults/",
        {"visibility_json": {"audit": "admin", "workflows": None}},
        format="json",
    )
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["visibility_json"] == {"audit": "admin", "workflows": None}
    assert body["propagated_workspace_count"] >= 1


@override_settings(**_JWT)
@pytest.mark.django_db
def test_global_put_rejects_an_unknown_role(nav_api):
    admin_client, _viewer_client, _ws = nav_api
    resp = admin_client.put(
        "/api/v1/navigation-visibility-defaults/",
        {"visibility_json": {"audit": "superuser"}},
        format="json",
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


@override_settings(**_JWT)
@pytest.mark.django_db
def test_global_put_requires_a_body_key(nav_api):
    admin_client, _viewer_client, _ws = nav_api
    resp = admin_client.put(
        "/api/v1/navigation-visibility-defaults/", {}, format="json"
    )
    assert resp.status_code == 400


@override_settings(**_JWT)
@pytest.mark.django_db
def test_global_is_admin_only(nav_api):
    _admin_client, viewer_client, _ws = nav_api
    assert viewer_client.get("/api/v1/navigation-visibility-defaults/").status_code == 403


@override_settings(**_JWT)
@pytest.mark.django_db
def test_workspace_get_is_readable_by_a_viewer(nav_api):
    """The sidebar renders for EVERY role, so its config read cannot be admin-only."""
    _admin_client, viewer_client, ws = nav_api
    resp = viewer_client.get(f"/api/v1/workspaces/{ws.id}/navigation-visibility/")
    assert resp.status_code == 200, resp.content
    assert resp.json()["is_customized"] is False


@override_settings(**_JWT)
@pytest.mark.django_db
def test_workspace_put_is_admin_only(nav_api):
    _admin_client, viewer_client, ws = nav_api
    resp = viewer_client.put(
        f"/api/v1/workspaces/{ws.id}/navigation-visibility/",
        {"visibility_json": {"audit": None}},
        format="json",
    )
    assert resp.status_code == 403


@override_settings(**_JWT)
@pytest.mark.django_db
def test_workspace_put_then_reset(nav_api):
    admin_client, _viewer_client, ws = nav_api
    admin_client.put(
        "/api/v1/navigation-visibility-defaults/",
        {"visibility_json": {"audit": "admin"}},
        format="json",
    )
    resp = admin_client.put(
        f"/api/v1/workspaces/{ws.id}/navigation-visibility/",
        {"visibility_json": {"audit": "editor"}},
        format="json",
    )
    assert resp.status_code == 200, resp.content
    assert resp.json()["is_customized"] is True

    resp = admin_client.post(
        f"/api/v1/workspaces/{ws.id}/navigation-visibility/reset/", {}, format="json"
    )
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["is_customized"] is False
    assert body["visibility_json"] == {"audit": "admin"}


@override_settings(**_JWT)
@pytest.mark.django_db
def test_workspace_with_a_malformed_id_is_rejected(nav_api):
    admin_client, _viewer_client, _ws = nav_api
    resp = admin_client.get("/api/v1/workspaces/not-a-uuid/navigation-visibility/")
    assert resp.status_code in (400, 404)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm backend-test pytest rest_api/tests/test_navigation_visibility_api.py -v`
Expected: FAIL — every request returns 404 (the routes do not exist)

- [ ] **Step 3: Write minimal implementation**

Append to `backend/rest_api/global_default_views.py`, immediately before `__all__`:

```python
# ---------------------------------------------------------------------------
# 6. Navigation visibility (Rollenbasierte Sichten §3.1)
# ---------------------------------------------------------------------------


def _serialize_global_navigation(obj: Any, *, propagated: int | None = None) -> dict[str, Any]:
    data: dict[str, Any] = {
        "tenant_id": str(obj.tenant_id),
        "visibility_json": obj.visibility_json,
        "version": obj.version,
        "updated_at": obj.modified_at,
    }
    if propagated is not None:
        data["propagated_workspace_count"] = propagated
    return data


def _serialize_workspace_navigation(obj: Any) -> dict[str, Any]:
    return {
        "workspace_id": str(obj.workspace_id),
        "visibility_json": obj.visibility_json,
        "is_customized": obj.is_customized,
        "source_global_id": (
            str(obj.source_global_id) if obj.source_global_id else None
        ),
        "version": obj.version,
        "updated_at": obj.modified_at,
    }


def _parse_workspace_uuid(workspace_id: str, lang: str):
    """Return a ``UUID`` or a 404 Response for a malformed path segment."""
    try:
        return UUID(str(workspace_id))
    except (TypeError, ValueError):
        return Response(
            build_error_response("NOT_FOUND", lang),
            status=status.HTTP_404_NOT_FOUND,
        )


class NavigationVisibilityDefaultsView(APIView):
    """GET/PUT /navigation-visibility-defaults/ (tenant singleton, admin-only)."""

    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        gate = _require_admin(request)
        if isinstance(gate, Response):
            return gate
        ctx, _lang = gate
        obj = NavigationVisibilityService().get_or_create_global(ctx.tenant_id)
        return Response(_serialize_global_navigation(obj))

    def put(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        gate = _require_admin(request)
        if isinstance(gate, Response):
            return gate
        ctx, lang = gate
        body = request.data if isinstance(request.data, dict) else {}
        if "visibility_json" not in body:
            return _validation(lang, "visibility_json is required")
        try:
            obj, propagated = NavigationVisibilityService().replace_global(
                ctx, body["visibility_json"]
            )
        except NavigationVisibilityError as exc:
            return _validation(lang, str(exc))
        return Response(_serialize_global_navigation(obj, propagated=propagated))


class WorkspaceNavigationVisibilityView(APIView):
    """GET/PUT /workspaces/{workspace_id}/navigation-visibility/.

    GET is open to EVERY authenticated role on purpose: the sidebar renders for
    viewers too and must be able to read its own visibility configuration. The
    payload carries no privileged data (it is a role->menu-entry map, and the
    real access gate stays server-side on each route). PUT stays admin-only.
    """

    def get(self, request: Request, workspace_id: str, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        ctx = get_auth_context(request)
        parsed = _parse_workspace_uuid(workspace_id, lang)
        if isinstance(parsed, Response):
            return parsed
        obj = NavigationVisibilityService().get_or_create_workspace(
            ctx.tenant_id, parsed
        )
        return Response(_serialize_workspace_navigation(obj))

    def put(self, request: Request, workspace_id: str, **kwargs: Any) -> Response:
        gate = _require_admin(request)
        if isinstance(gate, Response):
            return gate
        ctx, lang = gate
        parsed = _parse_workspace_uuid(workspace_id, lang)
        if isinstance(parsed, Response):
            return parsed
        body = request.data if isinstance(request.data, dict) else {}
        if "visibility_json" not in body:
            return _validation(lang, "visibility_json is required")
        try:
            obj = NavigationVisibilityService().replace_workspace(
                ctx, parsed, body["visibility_json"]
            )
        except NavigationVisibilityError as exc:
            return _validation(lang, str(exc))
        return Response(_serialize_workspace_navigation(obj))


class WorkspaceNavigationVisibilityResetView(APIView):
    """POST /workspaces/{workspace_id}/navigation-visibility/reset/ (admin-only)."""

    def post(self, request: Request, workspace_id: str, **kwargs: Any) -> Response:
        gate = _require_admin(request)
        if isinstance(gate, Response):
            return gate
        ctx, lang = gate
        parsed = _parse_workspace_uuid(workspace_id, lang)
        if isinstance(parsed, Response):
            return parsed
        try:
            obj = NavigationVisibilityService().reset_workspace(ctx, parsed)
        except NoNavigationGlobalSourceError as exc:
            return Response(
                build_error_response("NO_GLOBAL_SOURCE", lang, message=str(exc)),
                status=status.HTTP_409_CONFLICT,
            )
        return Response(_serialize_workspace_navigation(obj))
```

Extend the module's imports at the top:

```python
from auth_tenancy.services.navigation_visibility import (
    NavigationVisibilityError,
    NavigationVisibilityService,
    NoNavigationGlobalSourceError,
)
```

Add the three names to `__all__`.

Wire the routes in `backend/rest_api/urls.py` — extend the existing `from rest_api.global_default_views import (...)` block with the three new view names, and add next to the `workflow-defaults/` routes:

```python
    # Navigation visibility (Rollenbasierte Sichten §3.1). The workspace GET is
    # deliberately NOT admin-only — every role's sidebar reads it.
    path(
        "navigation-visibility-defaults/",
        NavigationVisibilityDefaultsView.as_view(),
        name="navigation-visibility-defaults",
    ),
    path(
        "workspaces/<str:workspace_id>/navigation-visibility/reset/",
        WorkspaceNavigationVisibilityResetView.as_view(),
        name="workspace-navigation-visibility-reset",
    ),
    path(
        "workspaces/<str:workspace_id>/navigation-visibility/",
        WorkspaceNavigationVisibilityView.as_view(),
        name="workspace-navigation-visibility",
    ),
```

Note the ordering: the `/reset/` route must be registered **before** the bare route, matching the existing `workflow-defaults/.../states/{state_id}/`-before-`states/` convention in this file.

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm backend-test pytest rest_api/tests/test_navigation_visibility_api.py rest_api/tests/test_global_default_smoke.py -v`
Expected: PASS (9 new + the pre-existing smoke tests)

- [ ] **Step 5: Commit**

```bash
git add backend/rest_api/global_default_views.py backend/rest_api/urls.py backend/rest_api/tests/test_navigation_visibility_api.py
git commit -m "feat: add navigation-visibility REST endpoints"
```

---

## Task 8: Provision navigation visibility on workspace creation

**Files:**
- Modify: `backend/application/workspace_provisioning.py:62-128` (`provision_workspace_defaults`)
- Test: `backend/auth_tenancy/tests/test_navigation_visibility_service.py` (append)

**Interfaces:**
- Consumes: `NavigationVisibilityService.provision_workspace(tenant_id, workspace_id)` (Task 6)
- Produces: every workspace created through `WorkspaceService.create_workspace` / `clone_workspace` has a linked `WorkspaceNavigationVisibility` row with `is_customized=False`

- [ ] **Step 1: Write the failing test**

Append to `backend/auth_tenancy/tests/test_navigation_visibility_service.py`:

```python
@pytest.mark.django_db
def test_workspace_creation_provisions_a_navigation_row(nav_ctx):
    from application.workspace_service import WorkspaceService

    ctx, _ws = nav_ctx
    TenantContext.set_tenant(ctx.tenant_id)
    try:
        fresh = WorkspaceService().create_workspace(
            ctx, name="ProvisionedWS", preset="standard"
        )
    finally:
        TenantContext.clear_tenant()

    row = WorkspaceNavigationVisibility.unscoped.filter(
        tenant_id=ctx.tenant_id, workspace_id=fresh.id
    ).first()
    assert row is not None
    assert row.is_customized is False
    assert row.source_global_id is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm backend-test pytest auth_tenancy/tests/test_navigation_visibility_service.py -k provisions -v`
Expected: FAIL with `assert None is not None`

- [ ] **Step 3: Write minimal implementation**

In `backend/application/workspace_provisioning.py`, at the end of `provision_workspace_defaults` (after the existing permission-definition provisioning call), add:

```python
    # Rollenbasierte Sichten §3.1 — link the workspace to the tenant navigation
    # global so an admin edit at the global level propagates into it. Idempotent
    # (get_or_create), so re-provisioning never clobbers a customised row.
    from auth_tenancy.services.navigation_visibility import (
        NavigationVisibilityService,
    )

    NavigationVisibilityService().provision_workspace(tenant_id, workspace_id)
```

Note: the import is function-local, matching the existing lazy-import style used elsewhere in this module to keep app-loading order free of cycles.

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm backend-test pytest auth_tenancy/tests/test_navigation_visibility_service.py application/tests/test_workspace_service.py -v`
Expected: PASS (14 nav tests + no workspace-service regression)

- [ ] **Step 5: Commit**

```bash
git add backend/application/workspace_provisioning.py backend/auth_tenancy/tests/test_navigation_visibility_service.py
git commit -m "feat: provision navigation visibility on workspace creation"
```

---

## Task 9: `useViewRole` + a widened `RequiredRole`

**Files:**
- Modify: `frontend/src/hooks/useHasRole.ts`
- Test: `frontend/src/test/useViewRole.test.tsx`

**Interfaces:**
- Consumes: `useAuth().roles: string[]` (`frontend/src/context/AuthContext.tsx`)
- Produces:
  - `export type RequiredRole = 'admin' | 'editor' | 'viewer' | 'approver'` (widened from `'admin' | 'editor'`)
  - `export type ViewRole = 'reader' | 'author' | 'expert'`
  - `export function useViewRole(): ViewRole`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/test/useViewRole.test.tsx`:

```tsx
/**
 * Rollenbasierte Sichten §2 — three views derived from four RBAC roles.
 */
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { AuthContext, type AuthState } from "../context/AuthContext";
import { useViewRole } from "../hooks/useHasRole";

function authState(roles: string[]): AuthState {
  return {
    isAuthenticated: true,
    status: "authenticated",
    user: null,
    tenantId: null,
    roles,
    isTenantAdmin: false,
    login: async () => undefined,
    updateProfile: async () => undefined,
    logout: () => undefined,
  } as unknown as AuthState;
}

function Probe(): JSX.Element {
  return <span data-testid="view-role">{useViewRole()}</span>;
}

function renderWithRoles(roles: string[]): void {
  render(
    <AuthContext.Provider value={authState(roles)}>
      <Probe />
    </AuthContext.Provider>
  );
}

describe("useViewRole", () => {
  it("maps viewer to reader", () => {
    renderWithRoles(["viewer"]);
    expect(screen.getByTestId("view-role")).toHaveTextContent("reader");
  });

  it("maps editor to author", () => {
    renderWithRoles(["editor"]);
    expect(screen.getByTestId("view-role")).toHaveTextContent("author");
  });

  it("maps admin to expert", () => {
    renderWithRoles(["admin"]);
    expect(screen.getByTestId("view-role")).toHaveTextContent("expert");
  });

  it("maps approver to expert", () => {
    renderWithRoles(["approver"]);
    expect(screen.getByTestId("view-role")).toHaveTextContent("expert");
  });

  it("takes the highest view when several roles are held", () => {
    renderWithRoles(["viewer", "editor", "approver"]);
    expect(screen.getByTestId("view-role")).toHaveTextContent("expert");
  });

  it("falls back to reader with no roles at all", () => {
    renderWithRoles([]);
    expect(screen.getByTestId("view-role")).toHaveTextContent("reader");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm frontend-test sh -c "npm install && npx vitest run src/test/useViewRole.test.tsx --testTimeout=30000"`
Expected: FAIL with `"useViewRole" is not exported by "src/hooks/useHasRole.ts"`

- [ ] **Step 3: Write minimal implementation**

Replace the body of `frontend/src/hooks/useHasRole.ts` below the existing docstring with:

```ts
import { useAuth } from '../context/AuthContext';

/**
 * A workspace role a UI element may require. Widened from `admin | editor`
 * (R2/T1) to the full RBAC set so navigation visibility, which is now
 * runtime-configurable data, can name any role the backend accepts
 * (`backend/auth_tenancy/models.py` ROLE_* constants).
 */
export type RequiredRole = 'admin' | 'editor' | 'viewer' | 'approver';

/** The three deliberate UI views of Rollenbasierte Sichten §2. */
export type ViewRole = 'reader' | 'author' | 'expert';

export function useHasRole(): (required?: RequiredRole | null) => boolean {
  const { roles } = useAuth();
  return (required?: RequiredRole | null): boolean =>
    !required || roles.includes(required) || roles.includes('admin');
}

/**
 * Resolve the caller's view from their workspace roles (Rollenbasierte
 * Sichten §2): `viewer` -> reader, `editor` -> author, `admin`/`approver` ->
 * expert. When several roles are held the highest view wins.
 *
 * UX-only, exactly like `useHasRole`: this decides display density and default
 * form mode, never authorization. Real enforcement is server-side.
 */
export function useViewRole(): ViewRole {
  const { roles } = useAuth();
  if (roles.includes('admin') || roles.includes('approver')) return 'expert';
  if (roles.includes('editor')) return 'author';
  return 'reader';
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm frontend-test sh -c "npm install && npx vitest run src/test/useViewRole.test.tsx src/test/SidebarNavigation.test.tsx --testTimeout=30000"`
Expected: PASS (6 new tests; SidebarNavigation unaffected)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/hooks/useHasRole.ts frontend/src/test/useViewRole.test.tsx
git commit -m "feat: add useViewRole and widen RequiredRole to all RBAC roles"
```

---

## Task 10: `api/navigation-visibility.ts` client

**Files:**
- Create: `frontend/src/api/navigation-visibility.ts`
- Test: `frontend/src/test/navigationVisibility.test.tsx`

**Interfaces:**
- Consumes: `apiClient` (`frontend/src/api/client.ts`); the endpoints from Task 7
- Produces:
  - `export type NavRequiredRole = RequiredRole | null`
  - `export type NavVisibilityMap = Record<string, NavRequiredRole>`
  - `export interface GlobalNavigationVisibility { tenant_id: UUID; visibility_json: NavVisibilityMap; version: number; updated_at?: string | null; propagated_workspace_count?: number }`
  - `export interface WorkspaceNavigationVisibility { workspace_id: UUID; visibility_json: NavVisibilityMap; is_customized: boolean; source_global_id?: UUID | null; version: number; updated_at?: string | null }`
  - `export const navigationVisibilityApi = { getGlobal, replaceGlobal, getWorkspace, replaceWorkspace, resetWorkspace }`
  - `export function resolveRequiredRole(key: string, codeDefault: RequiredRole | undefined, map: NavVisibilityMap | null): RequiredRole | null`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/test/navigationVisibility.test.tsx`:

```tsx
/**
 * Rollenbasierte Sichten §3.1 — data overrides the coded default, absence
 * falls back to it (DECISION 2: fail-safe, no bootstrap seed).
 */
import { describe, it, expect } from "vitest";
import { resolveRequiredRole } from "../api/navigation-visibility";

describe("resolveRequiredRole", () => {
  it("uses the coded default when the key is absent from the map", () => {
    expect(resolveRequiredRole("system-settings", "admin", {})).toBe("admin");
  });

  it("uses the coded default when there is no map at all", () => {
    expect(resolveRequiredRole("system-settings", "admin", null)).toBe("admin");
  });

  it("lets data tighten an ungated entry", () => {
    expect(resolveRequiredRole("audit", undefined, { audit: "admin" })).toBe("admin");
  });

  it("lets data loosen a coded default to everyone", () => {
    expect(resolveRequiredRole("settings", "admin", { settings: null })).toBeNull();
  });

  it("lets data replace one role with another", () => {
    expect(resolveRequiredRole("workflows", "admin", { workflows: "editor" })).toBe(
      "editor"
    );
  });

  it("returns null for an ungated entry with no data", () => {
    expect(resolveRequiredRole("dashboard", undefined, {})).toBeNull();
  });

  it("ignores an unknown role value from the server and keeps the coded default", () => {
    const hostile = { settings: "superuser" } as unknown as Record<string, never>;
    expect(resolveRequiredRole("settings", "admin", hostile)).toBe("admin");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm frontend-test sh -c "npm install && npx vitest run src/test/navigationVisibility.test.tsx --testTimeout=30000"`
Expected: FAIL with `Failed to resolve import "../api/navigation-visibility"`

- [ ] **Step 3: Write minimal implementation**

Create `frontend/src/api/navigation-visibility.ts`:

```ts
/**
 * ARCH-L1-001 ReactFrontend — Navigation Visibility API
 * (Rollenbasierte Sichten §3.1/§6).
 *
 * leaf_id: COMP-RF-001 (NavigationShell — System / Workspace Settings scope)
 *
 * Wraps:
 *   GET/PUT /navigation-visibility-defaults/                  tenant default (admin)
 *   GET     /workspaces/{id}/navigation-visibility/           resolved (ANY role)
 *   PUT     /workspaces/{id}/navigation-visibility/           override (admin)
 *   POST    /workspaces/{id}/navigation-visibility/reset/     back to default (admin)
 *
 * NOT a security boundary: hiding a nav entry does not block the route behind
 * it. The server-side RBAC check on each route/API is the actual gate.
 */

import { apiClient } from "./client";
import type { UUID } from "../types";
import type { RequiredRole } from "../hooks/useHasRole";

/** `null` = visible to every authenticated role. */
export type NavRequiredRole = RequiredRole | null;

/** `{nav_item_key: required_role | null}`. An ABSENT key means "coded default". */
export type NavVisibilityMap = Record<string, NavRequiredRole>;

const VALID_ROLES: readonly string[] = ["admin", "editor", "viewer", "approver"];

export interface GlobalNavigationVisibility {
  tenant_id: UUID;
  visibility_json: NavVisibilityMap;
  version: number;
  updated_at?: string | null;
  /** Present on PUT responses — how many on-default workspaces were updated. */
  propagated_workspace_count?: number;
}

export interface WorkspaceNavigationVisibility {
  workspace_id: UUID;
  visibility_json: NavVisibilityMap;
  is_customized: boolean;
  source_global_id?: UUID | null;
  version: number;
  updated_at?: string | null;
}

/**
 * Resolve the role required to SEE a navigation entry.
 *
 * Resolution order (DECISION 2): an explicitly stored value wins, otherwise the
 * value coded in `NAV_ITEMS[].requires`. A stored value the client does not
 * recognise is discarded in favour of the coded default — that keeps a corrupt
 * or forward-versioned payload from failing OPEN on an admin-only entry.
 */
export function resolveRequiredRole(
  key: string,
  codeDefault: RequiredRole | undefined,
  map: NavVisibilityMap | null
): RequiredRole | null {
  if (map && Object.prototype.hasOwnProperty.call(map, key)) {
    const stored = map[key];
    if (stored === null) return null;
    if (typeof stored === "string" && VALID_ROLES.includes(stored)) {
      return stored as RequiredRole;
    }
  }
  return codeDefault ?? null;
}

export const navigationVisibilityApi = {
  /** GET /api/v1/navigation-visibility-defaults/ (admin). */
  getGlobal(): Promise<GlobalNavigationVisibility> {
    return apiClient.get<GlobalNavigationVisibility>(
      "/navigation-visibility-defaults/"
    );
  },

  /** PUT /api/v1/navigation-visibility-defaults/ (admin, full replace). */
  replaceGlobal(map: NavVisibilityMap): Promise<GlobalNavigationVisibility> {
    return apiClient.put<GlobalNavigationVisibility>(
      "/navigation-visibility-defaults/",
      { visibility_json: map }
    );
  },

  /** GET /api/v1/workspaces/{id}/navigation-visibility/ (any authenticated role). */
  getWorkspace(workspaceId: UUID): Promise<WorkspaceNavigationVisibility> {
    return apiClient.get<WorkspaceNavigationVisibility>(
      `/workspaces/${workspaceId}/navigation-visibility/`
    );
  },

  /** PUT /api/v1/workspaces/{id}/navigation-visibility/ (admin, full replace). */
  replaceWorkspace(
    workspaceId: UUID,
    map: NavVisibilityMap
  ): Promise<WorkspaceNavigationVisibility> {
    return apiClient.put<WorkspaceNavigationVisibility>(
      `/workspaces/${workspaceId}/navigation-visibility/`,
      { visibility_json: map }
    );
  },

  /** POST /api/v1/workspaces/{id}/navigation-visibility/reset/ (admin). */
  resetWorkspace(workspaceId: UUID): Promise<WorkspaceNavigationVisibility> {
    return apiClient.post<WorkspaceNavigationVisibility>(
      `/workspaces/${workspaceId}/navigation-visibility/reset/`,
      {}
    );
  },
};
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm frontend-test sh -c "npm install && npx vitest run src/test/navigationVisibility.test.tsx --testTimeout=30000"`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/navigation-visibility.ts frontend/src/test/navigationVisibility.test.tsx
git commit -m "feat: add navigation-visibility API client and role resolver"
```

---

## Task 11: SidebarNavigation reads the resolved visibility map

**Files:**
- Modify: `frontend/src/components/NavigationShell/SidebarNavigation.tsx:66-134` (NavItem type + `NAV_ITEMS`), `:408-419` (`visibleItems`)
- Test: `frontend/src/test/SidebarNavigation.test.tsx` (append a describe block)

**Interfaces:**
- Consumes: `navigationVisibilityApi.getWorkspace(workspaceId)`, `resolveRequiredRole(key, codeDefault, map)` (Task 10); `useHasRole()` with the widened `RequiredRole` (Task 9)
- Produces: `NavItem.key: string` (stable slug, decoupled from `path`)

- [ ] **Step 1: Write the failing test**

Append to `frontend/src/test/SidebarNavigation.test.tsx`:

```tsx
// ---------------------------------------------------------------------------
// Rollenbasierte Sichten §3.1: nav visibility is runtime-configurable data.
// The coded `requires` stays as the fallback (DECISION 2), so an empty map
// reproduces today's behaviour exactly.
// ---------------------------------------------------------------------------

import { navigationVisibilityApi } from "../api/navigation-visibility";

vi.mock("../api/navigation-visibility", async (importOriginal) => {
  const actual = await importOriginal<
    typeof import("../api/navigation-visibility")
  >();
  return {
    ...actual,
    navigationVisibilityApi: {
      getGlobal: vi.fn(),
      replaceGlobal: vi.fn(),
      getWorkspace: vi.fn(async () => ({
        workspace_id: "ws-test",
        visibility_json: {},
        is_customized: false,
        source_global_id: null,
        version: 1,
      })),
      replaceWorkspace: vi.fn(),
      resetWorkspace: vi.fn(),
    },
  };
});

function setVisibilityMap(map: Record<string, string | null>): void {
  (
    navigationVisibilityApi.getWorkspace as ReturnType<typeof vi.fn>
  ).mockResolvedValue({
    workspace_id: "ws-test",
    visibility_json: map,
    is_customized: false,
    source_global_id: null,
    version: 1,
  });
}

describe("SidebarNavigation — data-driven nav visibility", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    installLocalStorageStub();
    sessionStorage.clear();
    setVisibilityMap({});
  });

  it("keeps the coded default when the map is empty", async () => {
    stubAuthFetch(["viewer"]);
    setListWorkspace(true);
    renderSidebar();

    await waitFor(() => {
      expect(screen.getByText("Dashboard")).toBeInTheDocument();
    });
    expect(screen.queryByText("System Settings")).not.toBeInTheDocument();
  });

  it("hides an entry the map newly gates against the caller's role", async () => {
    stubAuthFetch(["editor"]);
    setListWorkspace(true);
    setVisibilityMap({ audit: "admin" });
    renderSidebar();

    await waitFor(() => {
      expect(screen.getByText("Dashboard")).toBeInTheDocument();
    });
    await waitFor(() => {
      expect(screen.queryByText("SE-Auditor")).not.toBeInTheDocument();
    });
  });

  it("shows an entry the map opens up to everyone", async () => {
    stubAuthFetch(["editor"]);
    setListWorkspace(true);
    setVisibilityMap({ "system-settings": null });
    renderSidebar();

    await waitFor(() => {
      expect(screen.getByText("System Settings")).toBeInTheDocument();
    });
  });

  it("falls back to the coded default when the config request fails", async () => {
    stubAuthFetch(["viewer"]);
    setListWorkspace(true);
    (
      navigationVisibilityApi.getWorkspace as ReturnType<typeof vi.fn>
    ).mockRejectedValue(new Error("boom"));
    renderSidebar();

    await waitFor(() => {
      expect(screen.getByText("Dashboard")).toBeInTheDocument();
    });
    // Fail-safe: a failed config read must never expose an admin page.
    expect(screen.queryByText("System Settings")).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm frontend-test sh -c "npm install && npx vitest run src/test/SidebarNavigation.test.tsx --testTimeout=30000"`
Expected: FAIL — "hides an entry the map newly gates" and "shows an entry the map opens up" both fail (the component ignores the map)

- [ ] **Step 3: Write minimal implementation**

(a) In `frontend/src/components/NavigationShell/SidebarNavigation.tsx`, extend the `NavItem` interface:

```ts
interface NavItem {
  /**
   * Stable slug used as the `nav_item_key` of the navigation-visibility
   * system object (Rollenbasierte Sichten §3.1). Deliberately independent of
   * `path`: a route rename must not silently orphan an admin's stored
   * visibility configuration.
   */
  key: string;
  path: string;
  labelKey: string;
  feature: string; // key in PRESET_VISIBILITY
  group: NavGroupId; // issue #317 — section grouping
  /**
   * CODE-LEVEL default role gate (R2/T1). Rollenbasierte Sichten §3.1 makes
   * this overridable at runtime through WorkspaceNavigationVisibility, but the
   * coded value REMAINS the fallback for any key the configuration does not
   * mention — so a missing/failed/renamed configuration still gates the admin
   * pages instead of failing open.
   */
  requires?: RequiredRole;
}
```

Add `key` to every entry of `NAV_ITEMS`, using the path slug (`"/"` → `"dashboard"`):

```ts
const NAV_ITEMS: NavItem[] = [
  { key: "dashboard", path: "/", labelKey: "nav.dashboard", feature: "dashboard", group: "overview" },
  { key: "goals", path: "/goals", labelKey: "nav.goals", feature: "dashboard", group: "overview" },
  { key: "metrics", path: "/metrics", labelKey: "nav.metrics", feature: "metrics", group: "overview" },
  { key: "interviews", path: "/interviews", labelKey: "nav.interviews", feature: "dashboard", group: "overview" },

  { key: "needs", path: "/needs", labelKey: "nav.needs", feature: "requirements", group: "requirements" },
  { key: "requirements", path: "/requirements", labelKey: "nav.requirements", feature: "requirements", group: "requirements" },
  { key: "adrs", path: "/adrs", labelKey: "nav.adrs", feature: "adr", group: "requirements" },
  { key: "risks", path: "/risks", labelKey: "nav.risks", feature: "risk", group: "requirements" },
  { key: "issues", path: "/issues", labelKey: "nav.issues", feature: "issue", group: "requirements" },
  { key: "glossary", path: "/glossary", labelKey: "nav.glossary", feature: "dashboard", group: "requirements" },

  { key: "architecture", path: "/architecture", labelKey: "nav.architecture", feature: "architecture", group: "architecture" },
  { key: "traceability", path: "/traceability", labelKey: "nav.traceability", feature: "traceability", group: "architecture" },
  { key: "impact", path: "/impact", labelKey: "nav.impact", feature: "impact", group: "architecture" },
  { key: "icds", path: "/icds", labelKey: "nav.icds", feature: "icds", group: "architecture" },
  { key: "diagrams", path: "/diagrams", labelKey: "nav.diagrams", feature: "diagrams", group: "architecture" },

  { key: "testcases", path: "/testcases", labelKey: "nav.testCases", feature: "testCases", group: "test" },
  { key: "test-runs", path: "/test-runs", labelKey: "nav.testRuns", feature: "testRuns", group: "test" },
  { key: "baselines", path: "/baselines", labelKey: "nav.baselines", feature: "baselines", group: "test" },
  { key: "reviews", path: "/reviews", labelKey: "nav.reviews", feature: "approver_ui", group: "test" },

  { key: "import", path: "/import", labelKey: "nav.import", feature: "csv_import", group: "admin" },
  { key: "workflows", path: "/workflows", labelKey: "nav.workflows", feature: "dashboard", group: "admin" },
  { key: "audit", path: "/audit", labelKey: "nav.audit", feature: "dashboard", group: "admin" },
  { key: "settings", path: "/settings", labelKey: "nav.settings", feature: "dashboard", group: "admin", requires: "admin" },
  { key: "system-settings", path: "/system-settings", labelKey: "nav.systemSettings", feature: "dashboard", group: "admin", requires: "admin" },
  { key: "user-management", path: "/user-management", labelKey: "nav.userManagement", feature: "dashboard", group: "admin" },
];
```

Keep the existing explanatory comments above the entries they belong to.

(b) Add the imports:

```ts
import { useHasRole, type RequiredRole } from "../../hooks/useHasRole";
import {
  navigationVisibilityApi,
  resolveRequiredRole,
  type NavVisibilityMap,
} from "../../api/navigation-visibility";
```

(c) Inside the component, after `const hasRole = useHasRole();`, load the map:

```tsx
  // Rollenbasierte Sichten §3.1 — the role a nav entry requires is data now.
  // `null` while loading (and after a failed load) means "use the coded
  // defaults", which is the fail-safe direction: an admin-only entry stays
  // admin-only even if this request never lands.
  const [navVisibility, setNavVisibility] =
    React.useState<NavVisibilityMap | null>(null);

  React.useEffect(() => {
    const workspaceId = activeWorkspace?.id;
    if (!workspaceId || activeWorkspace === DEFAULT_WORKSPACE) {
      setNavVisibility(null);
      return;
    }
    let cancelled = false;
    void navigationVisibilityApi
      .getWorkspace(workspaceId)
      .then((resp) => {
        if (!cancelled) setNavVisibility(resp.visibility_json ?? {});
      })
      .catch(() => {
        // Non-blocking: keep the coded defaults rather than hiding the whole
        // sidebar or, worse, showing every entry to every role.
        if (!cancelled) setNavVisibility(null);
      });
    return () => {
      cancelled = true;
    };
  }, [activeWorkspace]);
```

(d) Replace the `.filter((item) => hasRole(item.requires))` line in `visibleItems`:

```tsx
    .filter((item) =>
      hasRole(resolveRequiredRole(item.key, item.requires, navVisibility))
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm frontend-test sh -c "npm install && npx vitest run src/test/SidebarNavigation.test.tsx src/test/navigationVisibility.test.tsx --testTimeout=30000"`
Expected: PASS (4 new tests plus all pre-existing SidebarNavigation tests)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/NavigationShell/SidebarNavigation.tsx frontend/src/test/SidebarNavigation.test.tsx
git commit -m "feat: gate sidebar entries by configurable navigation visibility"
```

---

## Task 12: `NavigationVisibilityEditor` component

**Files:**
- Create: `frontend/src/components/SystemSettings/NavigationVisibilityEditor.tsx`
- Test: `frontend/src/test/NavigationVisibilityEditor.test.tsx`

**Interfaces:**
- Consumes: `navigationVisibilityApi` (Task 10), `NAV_ITEM_KEYS` (exported from `SidebarNavigation.tsx` in Step 3)
- Produces: `export function NavigationVisibilityEditor(props: { scope: "global" } | { scope: "workspace"; workspaceId: UUID }): JSX.Element`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/test/NavigationVisibilityEditor.test.tsx`:

```tsx
/**
 * Rollenbasierte Sichten §3.1/§6.5 — runtime editor for nav visibility.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { NavigationVisibilityEditor } from "../components/SystemSettings/NavigationVisibilityEditor";
import { navigationVisibilityApi } from "../api/navigation-visibility";

vi.mock("../api/navigation-visibility", async (importOriginal) => {
  const actual = await importOriginal<
    typeof import("../api/navigation-visibility")
  >();
  return {
    ...actual,
    navigationVisibilityApi: {
      getGlobal: vi.fn(),
      replaceGlobal: vi.fn(),
      getWorkspace: vi.fn(),
      replaceWorkspace: vi.fn(),
      resetWorkspace: vi.fn(),
    },
  };
});

const mocked = navigationVisibilityApi as unknown as Record<
  string,
  ReturnType<typeof vi.fn>
>;

describe("NavigationVisibilityEditor", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocked.getGlobal.mockResolvedValue({
      tenant_id: "t-1",
      visibility_json: { audit: "admin" },
      version: 2,
    });
    mocked.replaceGlobal.mockResolvedValue({
      tenant_id: "t-1",
      visibility_json: { audit: "admin" },
      version: 3,
      propagated_workspace_count: 4,
    });
    mocked.getWorkspace.mockResolvedValue({
      workspace_id: "ws-1",
      visibility_json: {},
      is_customized: false,
      source_global_id: "g-1",
      version: 1,
    });
    mocked.resetWorkspace.mockResolvedValue({
      workspace_id: "ws-1",
      visibility_json: { audit: "admin" },
      is_customized: false,
      source_global_id: "g-1",
      version: 2,
    });
  });

  it("renders one row per nav item and preselects the stored role", async () => {
    render(<NavigationVisibilityEditor scope="global" />);
    const select = await screen.findByTestId("nav-visibility-select-audit");
    expect((select as HTMLSelectElement).value).toBe("admin");
    // A key with no stored value shows the "inherit coded default" option.
    const dashboard = await screen.findByTestId("nav-visibility-select-dashboard");
    expect((dashboard as HTMLSelectElement).value).toBe("__default__");
  });

  it("saves the whole map on Save and reports the propagation count", async () => {
    render(<NavigationVisibilityEditor scope="global" />);
    const select = await screen.findByTestId("nav-visibility-select-workflows");
    fireEvent.change(select, { target: { value: "editor" } });
    fireEvent.click(screen.getByTestId("nav-visibility-save"));

    await waitFor(() => {
      expect(mocked.replaceGlobal).toHaveBeenCalledWith({
        audit: "admin",
        workflows: "editor",
      });
    });
    expect(await screen.findByTestId("nav-visibility-status")).toHaveTextContent("4");
  });

  it("drops a key from the payload when it is set back to the coded default", async () => {
    render(<NavigationVisibilityEditor scope="global" />);
    const select = await screen.findByTestId("nav-visibility-select-audit");
    fireEvent.change(select, { target: { value: "__default__" } });
    fireEvent.click(screen.getByTestId("nav-visibility-save"));

    await waitFor(() => {
      expect(mocked.replaceGlobal).toHaveBeenCalledWith({});
    });
  });

  it("offers reset only in workspace scope", async () => {
    const { unmount } = render(<NavigationVisibilityEditor scope="global" />);
    await screen.findByTestId("nav-visibility-save");
    expect(screen.queryByTestId("nav-visibility-reset")).not.toBeInTheDocument();
    unmount();

    render(<NavigationVisibilityEditor scope="workspace" workspaceId="ws-1" />);
    fireEvent.click(await screen.findByTestId("nav-visibility-reset"));
    await waitFor(() => {
      expect(mocked.resetWorkspace).toHaveBeenCalledWith("ws-1");
    });
  });

  it("surfaces a load failure instead of rendering an empty editor", async () => {
    mocked.getGlobal.mockRejectedValue(new Error("nope"));
    render(<NavigationVisibilityEditor scope="global" />);
    expect(await screen.findByTestId("nav-visibility-error")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm frontend-test sh -c "npm install && npx vitest run src/test/NavigationVisibilityEditor.test.tsx --testTimeout=30000"`
Expected: FAIL with `Failed to resolve import "../components/SystemSettings/NavigationVisibilityEditor"`

- [ ] **Step 3: Write minimal implementation**

First export the key/label catalogue from `frontend/src/components/NavigationShell/SidebarNavigation.tsx` (add below `NAV_ITEMS`):

```ts
/**
 * The nav_item_key + label of every navigation entry, in render order — the
 * catalogue the NavigationVisibilityEditor lists. WHICH pages exist is code;
 * WHICH role may see them is data (Rollenbasierte Sichten §3.1).
 */
export const NAV_ITEM_KEYS: ReadonlyArray<{
  key: string;
  labelKey: string;
  codeDefault: RequiredRole | null;
}> = NAV_ITEMS.map((item) => ({
  key: item.key,
  labelKey: item.labelKey,
  codeDefault: item.requires ?? null,
}));
```

Create `frontend/src/components/SystemSettings/NavigationVisibilityEditor.tsx`:

```tsx
/**
 * Rollenbasierte Sichten §3.1/§6.5 — runtime editor for navigation visibility.
 *
 * leaf_id: COMP-RF-001 (NavigationShell — System / Workspace Settings scope)
 *
 * One row per navigation entry, one <select> per row: "inherit coded default"
 * or an explicit required role (or "everyone"). Saving PUTs the WHOLE map, so a
 * row switched back to "inherit" is dropped from the payload rather than stored
 * as an explicit value — that keeps the stored map to actual deltas.
 *
 * NOT a permission editor. The copy states this explicitly: hiding an entry
 * does not block the route behind it; the server-side RBAC check does.
 */

import React from "react";
import { useTranslation } from "react-i18next";
import {
  navigationVisibilityApi,
  type NavRequiredRole,
  type NavVisibilityMap,
} from "../../api/navigation-visibility";
import { NAV_ITEM_KEYS } from "../NavigationShell/SidebarNavigation";
import type { RequiredRole } from "../../hooks/useHasRole";
import type { UUID } from "../../types";

/** Sentinel <option> value meaning "no stored override — use the coded default". */
const INHERIT = "__default__";
/** Sentinel <option> value meaning "stored override: visible to every role". */
const EVERYONE = "__everyone__";

const ROLE_OPTIONS: readonly RequiredRole[] = [
  "admin",
  "approver",
  "editor",
  "viewer",
];

export type NavigationVisibilityEditorProps =
  | { scope: "global" }
  | { scope: "workspace"; workspaceId: UUID };

function toSelectValue(stored: NavRequiredRole | undefined, present: boolean): string {
  if (!present) return INHERIT;
  if (stored === null) return EVERYONE;
  return stored;
}

function toStoredValue(selectValue: string): NavRequiredRole | undefined {
  if (selectValue === INHERIT) return undefined;
  if (selectValue === EVERYONE) return null;
  return selectValue as RequiredRole;
}

export function NavigationVisibilityEditor(
  props: NavigationVisibilityEditorProps
): JSX.Element {
  const { t } = useTranslation();
  const [draft, setDraft] = React.useState<Record<string, string>>({});
  const [isLoading, setIsLoading] = React.useState<boolean>(true);
  const [error, setError] = React.useState<string | null>(null);
  const [statusText, setStatusText] = React.useState<string | null>(null);
  const [isSaving, setIsSaving] = React.useState<boolean>(false);

  const applyMap = React.useCallback((map: NavVisibilityMap): void => {
    const next: Record<string, string> = {};
    for (const item of NAV_ITEM_KEYS) {
      const present = Object.prototype.hasOwnProperty.call(map, item.key);
      next[item.key] = toSelectValue(map[item.key], present);
    }
    setDraft(next);
  }, []);

  const load = React.useCallback(async (): Promise<void> => {
    setIsLoading(true);
    setError(null);
    try {
      const resp =
        props.scope === "global"
          ? await navigationVisibilityApi.getGlobal()
          : await navigationVisibilityApi.getWorkspace(props.workspaceId);
      applyMap(resp.visibility_json ?? {});
    } catch {
      setError(
        t(
          "navVisibility.loadFailed",
          "Die Navigations-Sichtbarkeit konnte nicht geladen werden."
        )
      );
    } finally {
      setIsLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [applyMap, props.scope, props.scope === "workspace" ? props.workspaceId : null, t]);

  React.useEffect(() => {
    void load();
  }, [load]);

  const buildPayload = (): NavVisibilityMap => {
    const map: NavVisibilityMap = {};
    for (const item of NAV_ITEM_KEYS) {
      const stored = toStoredValue(draft[item.key] ?? INHERIT);
      if (stored !== undefined) map[item.key] = stored;
    }
    return map;
  };

  const handleSave = async (): Promise<void> => {
    setIsSaving(true);
    setError(null);
    setStatusText(null);
    try {
      const payload = buildPayload();
      if (props.scope === "global") {
        const resp = await navigationVisibilityApi.replaceGlobal(payload);
        applyMap(resp.visibility_json ?? {});
        setStatusText(
          t("navVisibility.savedGlobal", {
            count: resp.propagated_workspace_count ?? 0,
            defaultValue:
              "Gespeichert. In {{count}} Workspace(s) ohne eigene Anpassung übernommen.",
          })
        );
      } else {
        const resp = await navigationVisibilityApi.replaceWorkspace(
          props.workspaceId,
          payload
        );
        applyMap(resp.visibility_json ?? {});
        setStatusText(t("navVisibility.savedWorkspace", "Gespeichert."));
      }
    } catch {
      setError(t("navVisibility.saveFailed", "Speichern fehlgeschlagen."));
    } finally {
      setIsSaving(false);
    }
  };

  const handleReset = async (): Promise<void> => {
    if (props.scope !== "workspace") return;
    setIsSaving(true);
    setError(null);
    setStatusText(null);
    try {
      const resp = await navigationVisibilityApi.resetWorkspace(props.workspaceId);
      applyMap(resp.visibility_json ?? {});
      setStatusText(
        t("navVisibility.resetDone", "Auf die Tenant-Vorgabe zurückgesetzt.")
      );
    } catch {
      setError(t("navVisibility.resetFailed", "Zurücksetzen fehlgeschlagen."));
    } finally {
      setIsSaving(false);
    }
  };

  if (error && isLoading === false && Object.keys(draft).length === 0) {
    return (
      <p data-testid="nav-visibility-error" role="alert">
        {error}
      </p>
    );
  }

  return (
    <section data-testid="nav-visibility-editor">
      <p>
        {t(
          "navVisibility.hint",
          "Steuert nur, welche Menüeinträge eine Rolle SIEHT. Das ist keine Zugriffskontrolle — der Server prüft die Berechtigung weiterhin selbst."
        )}
      </p>

      {isLoading && <p>{t("loading.generic", "Lädt...")}</p>}

      <ul>
        {NAV_ITEM_KEYS.map((item) => (
          <li key={item.key}>
            <label htmlFor={`nav-visibility-select-${item.key}`}>
              {t(item.labelKey)}
            </label>
            <select
              id={`nav-visibility-select-${item.key}`}
              data-testid={`nav-visibility-select-${item.key}`}
              value={draft[item.key] ?? INHERIT}
              onChange={(e) =>
                setDraft((prev) => ({ ...prev, [item.key]: e.target.value }))
              }
            >
              <option value={INHERIT}>
                {item.codeDefault
                  ? t("navVisibility.inheritRole", {
                      role: item.codeDefault,
                      defaultValue: "Standard ({{role}})",
                    })
                  : t("navVisibility.inheritOpen", "Standard (alle Rollen)")}
              </option>
              <option value={EVERYONE}>
                {t("navVisibility.everyone", "Alle Rollen")}
              </option>
              {ROLE_OPTIONS.map((role) => (
                <option key={role} value={role}>
                  {t(`navVisibility.role.${role}`, role)}
                </option>
              ))}
            </select>
          </li>
        ))}
      </ul>

      <button
        type="button"
        data-testid="nav-visibility-save"
        disabled={isSaving}
        onClick={() => void handleSave()}
      >
        {t("actions.save", "Speichern")}
      </button>

      {props.scope === "workspace" && (
        <button
          type="button"
          data-testid="nav-visibility-reset"
          disabled={isSaving}
          onClick={() => void handleReset()}
        >
          {t("navVisibility.reset", "Auf Tenant-Vorgabe zurücksetzen")}
        </button>
      )}

      {statusText && (
        <p data-testid="nav-visibility-status" role="status">
          {statusText}
        </p>
      )}
      {error && (
        <p data-testid="nav-visibility-error" role="alert">
          {error}
        </p>
      )}
    </section>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm frontend-test sh -c "npm install && npx vitest run src/test/NavigationVisibilityEditor.test.tsx --testTimeout=30000"`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/SystemSettings/NavigationVisibilityEditor.tsx frontend/src/components/NavigationShell/SidebarNavigation.tsx frontend/src/test/NavigationVisibilityEditor.test.tsx
git commit -m "feat: add navigation-visibility editor component"
```

---

## Task 13: Mount the editor in System Settings and Workspace Settings

**Files:**
- Modify: `frontend/src/components/SystemSettings/SystemSettings.tsx:33-44,75-80,155-177`
- Modify: `frontend/src/components/WorkspaceSettings/WorkspaceSettings.tsx` (tab list + panel switch)
- Test: `frontend/src/test/NavigationVisibilityEditor.test.tsx` (append a mounting test)

**Interfaces:**
- Consumes: `NavigationVisibilityEditor` (Task 12)
- Produces: tab id `"navigation-visibility"` on both settings surfaces; testids `system-settings-tab-navigation-visibility`, `workspace-settings-tab-navigation-visibility`

- [ ] **Step 1: Write the failing test**

Append to `frontend/src/test/NavigationVisibilityEditor.test.tsx`:

```tsx
import { MemoryRouter } from "react-router-dom";
import SystemSettings from "../components/SystemSettings/SystemSettings";
import { AuthContext, type AuthState } from "../context/AuthContext";

function adminAuth(): AuthState {
  return {
    isAuthenticated: true,
    status: "authenticated",
    user: null,
    tenantId: "t-1",
    roles: ["admin"],
    isTenantAdmin: true,
    login: async () => undefined,
    updateProfile: async () => undefined,
    logout: () => undefined,
  } as unknown as AuthState;
}

describe("SystemSettings — navigation visibility tab", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocked.getGlobal.mockResolvedValue({
      tenant_id: "t-1",
      visibility_json: {},
      version: 1,
    });
  });

  it("mounts the editor when the tab is selected", async () => {
    render(
      <MemoryRouter initialEntries={["/system-settings?tab=navigation-visibility"]}>
        <AuthContext.Provider value={adminAuth()}>
          <SystemSettings />
        </AuthContext.Provider>
      </MemoryRouter>
    );

    expect(
      await screen.findByTestId("system-settings-tab-navigation-visibility")
    ).toBeInTheDocument();
    expect(await screen.findByTestId("nav-visibility-editor")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm frontend-test sh -c "npm install && npx vitest run src/test/NavigationVisibilityEditor.test.tsx --testTimeout=30000"`
Expected: FAIL with `Unable to find an element by: [data-testid="system-settings-tab-navigation-visibility"]`

- [ ] **Step 3: Write minimal implementation**

In `frontend/src/components/SystemSettings/SystemSettings.tsx`:

```tsx
import { NavigationVisibilityEditor } from "./NavigationVisibilityEditor";

type SystemTabId =
  | "administration"
  | "workflow-defaults"
  | "permission-defaults"
  | "navigation-visibility"
  | "memory";

const TAB_IDS: SystemTabId[] = [
  "administration",
  "workflow-defaults",
  "permission-defaults",
  "navigation-visibility",
  "memory",
];
```

Add to `TABS`:

```tsx
    {
      id: "navigation-visibility",
      label: t("systemSettings.tabs.navigationVisibility", "Navigation"),
    },
```

Add to the panel switch:

```tsx
        {activeTab === "navigation-visibility" && (
          <NavigationVisibilityEditor scope="global" />
        )}
```

In `frontend/src/components/WorkspaceSettings/WorkspaceSettings.tsx`, follow the same three edits against that file's own tab-id union / `TAB_IDS` / `TABS` / panel switch, using the active workspace id:

```tsx
        {activeTab === "navigation-visibility" && activeWorkspace && (
          <NavigationVisibilityEditor
            scope="workspace"
            workspaceId={activeWorkspace.id}
          />
        )}
```

with the tab entry:

```tsx
    {
      id: "navigation-visibility",
      label: t("settings.tabs.navigationVisibility", "Navigation"),
    },
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm frontend-test sh -c "npm install && npx vitest run src/test/NavigationVisibilityEditor.test.tsx --testTimeout=30000"`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/SystemSettings/SystemSettings.tsx frontend/src/components/WorkspaceSettings/WorkspaceSettings.tsx frontend/src/test/NavigationVisibilityEditor.test.tsx
git commit -m "feat: add navigation-visibility tabs to settings surfaces"
```

---

## Task 14: Expert-mode state + toggle

**Files:**
- Modify: `frontend/src/context/AuthContext.tsx:35-44` (`AuthUser`), `:87-102` (`AuthState`), `:237-250` (`value`)
- Create: `frontend/src/components/shared/ExpertModeToggle.tsx`
- Test: `frontend/src/test/ExpertModeToggle.test.tsx`

**Interfaces:**
- Consumes: `PATCH /auth/me/ {expert_mode_enabled}` (Task 4)
- Produces:
  - `AuthUser.expert_mode_enabled: boolean`
  - `AuthState.expertModeEnabled: boolean`
  - `AuthState.setExpertMode: (enabled: boolean) => Promise<void>`
  - `export function ExpertModeToggle(): JSX.Element | null`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/test/ExpertModeToggle.test.tsx`:

```tsx
/**
 * Rollenbasierte Sichten §5 — expert mode is a preference, visible only to
 * admin/approver, and grants no rights.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { AuthContext, type AuthState } from "../context/AuthContext";
import { ExpertModeToggle } from "../components/shared/ExpertModeToggle";

function authState(
  roles: string[],
  expertModeEnabled: boolean,
  setExpertMode: (v: boolean) => Promise<void>
): AuthState {
  return {
    isAuthenticated: true,
    status: "authenticated",
    user: null,
    tenantId: "t-1",
    roles,
    isTenantAdmin: false,
    expertModeEnabled,
    setExpertMode,
    login: async () => undefined,
    updateProfile: async () => undefined,
    logout: () => undefined,
  } as unknown as AuthState;
}

describe("ExpertModeToggle", () => {
  let setExpertMode: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    setExpertMode = vi.fn(async () => undefined);
  });

  it("renders for an admin", () => {
    render(
      <AuthContext.Provider value={authState(["admin"], false, setExpertMode)}>
        <ExpertModeToggle />
      </AuthContext.Provider>
    );
    expect(screen.getByTestId("expert-mode-toggle")).toBeInTheDocument();
  });

  it("renders for an approver", () => {
    render(
      <AuthContext.Provider value={authState(["approver"], false, setExpertMode)}>
        <ExpertModeToggle />
      </AuthContext.Provider>
    );
    expect(screen.getByTestId("expert-mode-toggle")).toBeInTheDocument();
  });

  it("does not render for an editor", () => {
    render(
      <AuthContext.Provider value={authState(["editor"], false, setExpertMode)}>
        <ExpertModeToggle />
      </AuthContext.Provider>
    );
    expect(screen.queryByTestId("expert-mode-toggle")).not.toBeInTheDocument();
  });

  it("does not render for a viewer", () => {
    render(
      <AuthContext.Provider value={authState(["viewer"], false, setExpertMode)}>
        <ExpertModeToggle />
      </AuthContext.Provider>
    );
    expect(screen.queryByTestId("expert-mode-toggle")).not.toBeInTheDocument();
  });

  it("reflects the current state and persists a flip", async () => {
    render(
      <AuthContext.Provider value={authState(["admin"], false, setExpertMode)}>
        <ExpertModeToggle />
      </AuthContext.Provider>
    );
    const toggle = screen.getByTestId("expert-mode-toggle");
    expect(toggle).toHaveAttribute("aria-checked", "false");
    fireEvent.click(toggle);
    await waitFor(() => {
      expect(setExpertMode).toHaveBeenCalledWith(true);
    });
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm frontend-test sh -c "npm install && npx vitest run src/test/ExpertModeToggle.test.tsx --testTimeout=30000"`
Expected: FAIL with `Failed to resolve import "../components/shared/ExpertModeToggle"`

- [ ] **Step 3: Write minimal implementation**

(a) In `frontend/src/context/AuthContext.tsx` add `expert_mode_enabled: boolean;` to `AuthUser`, then add to `AuthState`:

```ts
  /**
   * Rollenbasierte Sichten §5 — display-density preference: expands
   * `audience="expert"` form sections by default. NOT a permission.
   */
  expertModeEnabled: boolean;
  /** PATCH /api/v1/auth/me/ — persist the expert-mode preference. */
  setExpertMode: (enabled: boolean) => Promise<void>;
```

Add the callback next to `updateProfile`:

```tsx
  /** Persists the expert-mode preference (Rollenbasierte Sichten §5). */
  const setExpertMode = useCallback(
    async (enabled: boolean): Promise<void> => {
      const data = await apiClient.patch<{ user: AuthUser }>("/auth/me/", {
        expert_mode_enabled: enabled,
      });
      setUser(data.user);
    },
    []
  );
```

and extend the memoised `value`:

```tsx
      expertModeEnabled: user?.expert_mode_enabled ?? false,
      setExpertMode,
```

with `setExpertMode` added to the dependency array.

(b) Create `frontend/src/components/shared/ExpertModeToggle.tsx`:

```tsx
/**
 * Rollenbasierte Sichten §5 — Expert-mode switch.
 *
 * Visible only to `admin`/`approver` (the Experte view). Flipping it expands
 * `audience="expert"` form sections by default and nothing else: it grants no
 * capability and hides no field. The copy says so explicitly, because the spec
 * flags "mistaken for a permission level" as a real risk (§8).
 */

import { useTranslation } from "react-i18next";
import { useAuth } from "../../context/AuthContext";
import { useViewRole } from "../../hooks/useHasRole";

export function ExpertModeToggle(): JSX.Element | null {
  const { t } = useTranslation();
  const { expertModeEnabled, setExpertMode } = useAuth();
  const viewRole = useViewRole();

  if (viewRole !== "expert") return null;

  return (
    <button
      type="button"
      role="switch"
      aria-checked={expertModeEnabled}
      data-testid="expert-mode-toggle"
      title={t(
        "expertMode.hint",
        "Zeigt Expertenbereiche standardmäßig aufgeklappt. Ändert keine Berechtigungen."
      )}
      onClick={() => void setExpertMode(!expertModeEnabled)}
    >
      {t("expertMode.label", "Expertenmodus")}
    </button>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm frontend-test sh -c "npm install && npx vitest run src/test/ExpertModeToggle.test.tsx src/test/useViewRole.test.tsx --testTimeout=30000"`
Expected: PASS (5 + 6 passed)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/context/AuthContext.tsx frontend/src/components/shared/ExpertModeToggle.tsx frontend/src/test/ExpertModeToggle.test.tsx
git commit -m "feat: add expert-mode preference state and toggle"
```

---

## Task 15: `audience` toggle in `AttributeEditorPage`

> **PRECONDITION — Spec 2 (Attribut-Definition) must be implemented first.** `AttributeEditorPage` and the `definition_json.attributes[]` write path do not exist on `main`. If the file below is absent, stop and report this task as blocked rather than creating a parallel editor.

**Files:**
- Modify: `frontend/src/components/AttributeEditor/AttributeEditorPage.tsx` (per-attribute meta-property row)
- Test: `frontend/src/test/AttributeEditorAudience.test.tsx`

**Interfaces:**
- Consumes: the attribute-definition PUT path from Spec 2 §5 (`attribute-defaults/{item_type}/{preset}/` and `workspaces/<id>/attribute-definitions/{item_type}/`), with `attributes[].audience: "basic" | "expert"` (Spec 2 §3.1)
- Produces: the same PUT payload, now carrying `audience` per attribute

- [ ] **Step 1: Write the failing test**

Create `frontend/src/test/AttributeEditorAudience.test.tsx`:

```tsx
/**
 * Rollenbasierte Sichten §4 — `audience` is a native property of the SAME
 * attribute-definition structure, set through the SAME editor.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { AttributeEditorPage } from "../components/AttributeEditor/AttributeEditorPage";
import { attributeDefinitionsApi } from "../api/attribute-definitions";

vi.mock("../api/attribute-definitions");

const mocked = attributeDefinitionsApi as unknown as Record<
  string,
  ReturnType<typeof vi.fn>
>;

const DEFINITION = {
  item_type: "Requirement",
  preset: "standard",
  version: 1,
  definition_json: {
    attributes: [
      {
        name: "title",
        kind: "core",
        type: "text",
        section: "general",
        order: 1,
        required: true,
        visible: true,
        locked: false,
        audience: "basic",
      },
      {
        name: "verification_method",
        kind: "core",
        type: "enum",
        section: "classification",
        order: 2,
        required: false,
        visible: true,
        locked: false,
        audience: "basic",
      },
    ],
  },
};

describe("AttributeEditorPage — audience toggle", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocked.getGlobal?.mockResolvedValue(DEFINITION);
    mocked.replaceGlobal?.mockResolvedValue(DEFINITION);
  });

  it("renders an expert-only toggle per attribute, off by default", async () => {
    render(<AttributeEditorPage scope="global" itemType="Requirement" preset="standard" />);
    const toggle = await screen.findByTestId(
      "attribute-audience-toggle-verification_method"
    );
    expect(toggle).toHaveAttribute("aria-checked", "false");
  });

  it("writes audience=expert through the existing save path", async () => {
    render(<AttributeEditorPage scope="global" itemType="Requirement" preset="standard" />);
    fireEvent.click(
      await screen.findByTestId("attribute-audience-toggle-verification_method")
    );
    fireEvent.click(screen.getByTestId("attribute-editor-save"));

    await waitFor(() => {
      expect(mocked.replaceGlobal).toHaveBeenCalled();
    });
    const payload = mocked.replaceGlobal.mock.calls[0].at(-1) as {
      attributes: Array<{ name: string; audience: string }>;
    };
    const changed = payload.attributes.find(
      (a) => a.name === "verification_method"
    );
    const untouched = payload.attributes.find((a) => a.name === "title");
    expect(changed?.audience).toBe("expert");
    expect(untouched?.audience).toBe("basic");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm frontend-test sh -c "npm install && npx vitest run src/test/AttributeEditorAudience.test.tsx --testTimeout=30000"`
Expected: FAIL with `Unable to find an element by: [data-testid="attribute-audience-toggle-verification_method"]`

- [ ] **Step 3: Write minimal implementation**

In the per-attribute row of `AttributeEditorPage.tsx`, next to the existing `required` / `visible` toggles, add:

```tsx
              {/* Rollenbasierte Sichten §4 — display density, NOT visibility.
                  `visible` remains the property that hides a field; this only
                  decides whether the section starts collapsed. */}
              <button
                type="button"
                role="switch"
                aria-checked={attribute.audience === "expert"}
                data-testid={`attribute-audience-toggle-${attribute.name}`}
                title={t(
                  "attributeEditor.audienceHint",
                  "Nur für Experten: Sektion startet eingeklappt. Verbirgt das Feld nicht."
                )}
                onClick={() =>
                  updateAttribute(attribute.name, {
                    audience: attribute.audience === "expert" ? "basic" : "expert",
                  })
                }
              >
                {t("attributeEditor.audienceLabel", "Nur für Experten")}
              </button>
```

`updateAttribute(name, partial)` is the same local draft mutator the `required`/`visible` toggles already use in that component (Spec 2 §6.1) — no new save path.

Ensure the TypeScript type for an attribute (Spec 2's `AttributeDefinitionEntry`) carries `audience: "basic" | "expert"` with `"basic"` as the parse default, so an entry written before this amendment normalises correctly.

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm frontend-test sh -c "npm install && npx vitest run src/test/AttributeEditorAudience.test.tsx --testTimeout=30000"`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/AttributeEditor/AttributeEditorPage.tsx frontend/src/test/AttributeEditorAudience.test.tsx
git commit -m "feat: set attribute audience from the attribute editor"
```

---

## Task 16: `ArtifactForm` collapses `audience="expert"` sections

> **PRECONDITION — Spec 2 (Attribut-Definition) must be implemented first.** `frontend/src/components/shared/ArtifactForm/ArtifactForm.tsx` does not exist on `main`.

**Files:**
- Modify: `frontend/src/components/shared/ArtifactForm/ArtifactForm.tsx` (section rendering)
- Test: `frontend/src/test/ArtifactFormAudience.test.tsx`

**Interfaces:**
- Consumes: `attributes[].audience` (Task 15), `useAuth().expertModeEnabled` (Task 14), `useViewRole()` (Task 9)
- Produces: `export function isSectionInitiallyExpanded(sectionAudience: "basic" | "expert", viewRole: ViewRole, expertModeEnabled: boolean): boolean` (exported from `ArtifactForm.tsx` so it is unit-testable without a full mount)

- [ ] **Step 1: Write the failing test**

Create `frontend/src/test/ArtifactFormAudience.test.tsx`:

```tsx
/**
 * Rollenbasierte Sichten §4 — expert sections default to COLLAPSED, never
 * hidden, and are always manually expandable by anyone who can see the form.
 */
import { describe, it, expect } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import {
  ArtifactForm,
  isSectionInitiallyExpanded,
} from "../components/shared/ArtifactForm/ArtifactForm";

describe("isSectionInitiallyExpanded", () => {
  it("always expands a basic section", () => {
    expect(isSectionInitiallyExpanded("basic", "reader", false)).toBe(true);
    expect(isSectionInitiallyExpanded("basic", "author", false)).toBe(true);
    expect(isSectionInitiallyExpanded("basic", "expert", true)).toBe(true);
  });

  it("collapses an expert section for reader and author", () => {
    expect(isSectionInitiallyExpanded("expert", "reader", true)).toBe(false);
    expect(isSectionInitiallyExpanded("expert", "author", true)).toBe(false);
  });

  it("collapses an expert section for an expert who has NOT enabled expert mode", () => {
    expect(isSectionInitiallyExpanded("expert", "expert", false)).toBe(false);
  });

  it("expands an expert section only for an expert with expert mode on", () => {
    expect(isSectionInitiallyExpanded("expert", "expert", true)).toBe(true);
  });
});

const DEFINITION = {
  attributes: [
    { name: "title", kind: "core", type: "text", section: "general", order: 1, visible: true, required: true, locked: false, editable: true, audience: "basic" },
    { name: "complexity", kind: "core", type: "enum", section: "classification", order: 2, visible: true, required: false, locked: false, editable: true, audience: "expert", options: [{ value: "low", label_de: "Niedrig", label_en: "Low" }] },
  ],
};

describe("ArtifactForm — expert sections are collapsed, not hidden", () => {
  it("keeps a collapsed expert section reachable via its disclosure control", () => {
    render(
      <ArtifactForm
        definition={DEFINITION}
        value={{ title: "T", complexity: "low" }}
        mode="edit"
        viewRole="author"
        expertModeEnabled={false}
        onChange={() => undefined}
        onSubmit={() => undefined}
      />
    );

    // Collapsed: the field is not rendered...
    expect(screen.queryByTestId("artifact-field-complexity")).not.toBeInTheDocument();
    // ...but the section header IS, so it is collapsed and never hidden.
    const header = screen.getByTestId("artifact-section-toggle-classification");
    expect(header).toHaveAttribute("aria-expanded", "false");

    fireEvent.click(header);
    expect(screen.getByTestId("artifact-field-complexity")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm frontend-test sh -c "npm install && npx vitest run src/test/ArtifactFormAudience.test.tsx --testTimeout=30000"`
Expected: FAIL with `"isSectionInitiallyExpanded" is not exported by ".../ArtifactForm.tsx"`

- [ ] **Step 3: Write minimal implementation**

In `frontend/src/components/shared/ArtifactForm/ArtifactForm.tsx` add `import { useViewRole, type ViewRole } from "../../../hooks/useHasRole";` and `import { useAuth } from "../../../context/AuthContext";`, then add the exported predicate and use it for the initial state of each section's disclosure:

```tsx
/**
 * Rollenbasierte Sichten §4 — decides whether a section starts EXPANDED.
 *
 * A section's audience is the strictest audience of its attributes ("expert"
 * if any attribute in it is expert). Expert sections start collapsed for
 * everyone except an expert-view user who has switched expert mode on. This is
 * display density only — a collapsed section is always manually expandable and
 * fully editable once open; `visible` and RBAC remain the real boundaries.
 */
export function isSectionInitiallyExpanded(
  sectionAudience: "basic" | "expert",
  viewRole: ViewRole,
  expertModeEnabled: boolean
): boolean {
  if (sectionAudience === "basic") return true;
  return viewRole === "expert" && expertModeEnabled;
}

/** Strictest audience across a section's attributes ("expert" wins). */
export function sectionAudience(
  attributes: ReadonlyArray<{ audience?: "basic" | "expert" }>
): "basic" | "expert" {
  return attributes.some((a) => a.audience === "expert") ? "expert" : "basic";
}
```

In the renderer, initialise the per-section open state once from the predicate and render a disclosure button per section:

```tsx
  const [openSections, setOpenSections] = React.useState<Record<string, boolean>>(
    () =>
      Object.fromEntries(
        sections.map((s) => [
          s.name,
          isSectionInitiallyExpanded(
            sectionAudience(s.attributes),
            viewRole,
            expertModeEnabled
          ),
        ])
      )
  );
```

```tsx
        <button
          type="button"
          data-testid={`artifact-section-toggle-${section.name}`}
          aria-expanded={openSections[section.name] === true}
          aria-controls={`artifact-section-panel-${section.name}`}
          onClick={() =>
            setOpenSections((prev) => ({
              ...prev,
              [section.name]: !prev[section.name],
            }))
          }
        >
          {sectionLabel(section)}
        </button>
```

When `ArtifactForm` is used without explicit props, default `viewRole` from `useViewRole()` and `expertModeEnabled` from `useAuth().expertModeEnabled`; the explicit props exist so the component stays unit-testable without providers.

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm frontend-test sh -c "npm install && npx vitest run src/test/ArtifactFormAudience.test.tsx --testTimeout=30000"`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/shared/ArtifactForm/ArtifactForm.tsx frontend/src/test/ArtifactFormAudience.test.tsx
git commit -m "feat: collapse expert-audience sections by default in ArtifactForm"
```

---

## Task 17: `ArtifactForm.mode` from role AND workflow state

> **PRECONDITION — Spec 2 (Attribut-Definition) must be implemented first.**

**Files:**
- Modify: `frontend/src/components/shared/ArtifactForm/ArtifactForm.tsx`
- Modify: `frontend/src/api/workflow-transitions.ts:59-64` (`WorkflowTransitionsResponse`)
- Test: `frontend/src/test/ArtifactFormMode.test.tsx`

**Interfaces:**
- Consumes: `WorkflowTransitionsResponse.fields_locked: boolean` (Task 2), `useViewRole()` (Task 9)
- Produces: `export function deriveFormMode(viewRole: ViewRole, fieldsLocked: boolean): "read" | "edit"`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/test/ArtifactFormMode.test.tsx`:

```tsx
/**
 * Rollenbasierte Sichten §3.2 — the form mode derives from role AND workflow
 * state: a locked state is field-read-only even for an author, while status
 * changes stay available through an allowed transition.
 */
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import {
  ArtifactForm,
  deriveFormMode,
} from "../components/shared/ArtifactForm/ArtifactForm";

describe("deriveFormMode", () => {
  it("puts a reader in read mode regardless of state", () => {
    expect(deriveFormMode("reader", false)).toBe("read");
    expect(deriveFormMode("reader", true)).toBe("read");
  });

  it("lets an author edit an unlocked artifact", () => {
    expect(deriveFormMode("author", false)).toBe("edit");
  });

  it("locks an author out of a locked state", () => {
    expect(deriveFormMode("author", true)).toBe("read");
  });

  it("locks an expert out of a locked state too", () => {
    expect(deriveFormMode("expert", true)).toBe("read");
  });

  it("lets an expert edit an unlocked artifact", () => {
    expect(deriveFormMode("expert", false)).toBe("edit");
  });
});

const DEFINITION = {
  attributes: [
    { name: "title", kind: "core", type: "text", section: "general", order: 1, visible: true, required: true, locked: false, editable: true, audience: "basic" },
  ],
};

describe("ArtifactForm — read mode renders no write affordances", () => {
  it("omits Save and Delete in read mode", () => {
    render(
      <ArtifactForm
        definition={DEFINITION}
        value={{ title: "T" }}
        mode="read"
        viewRole="reader"
        expertModeEnabled={false}
        onChange={() => undefined}
        onSubmit={() => undefined}
        onDelete={() => undefined}
      />
    );
    // Not rendered — never merely disabled (Global Constraints).
    expect(screen.queryByTestId("artifact-form-save")).not.toBeInTheDocument();
    expect(screen.queryByTestId("artifact-form-delete")).not.toBeInTheDocument();
    expect(screen.getByTestId("artifact-field-title")).toHaveAttribute("readonly");
  });

  it("renders Save in edit mode", () => {
    render(
      <ArtifactForm
        definition={DEFINITION}
        value={{ title: "T" }}
        mode="edit"
        viewRole="author"
        expertModeEnabled={false}
        onChange={() => undefined}
        onSubmit={() => undefined}
        onDelete={() => undefined}
      />
    );
    expect(screen.getByTestId("artifact-form-save")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm frontend-test sh -c "npm install && npx vitest run src/test/ArtifactFormMode.test.tsx --testTimeout=30000"`
Expected: FAIL with `"deriveFormMode" is not exported by ".../ArtifactForm.tsx"`

- [ ] **Step 3: Write minimal implementation**

(a) In `frontend/src/api/workflow-transitions.ts`, extend the response interface:

```ts
/** Response of GET /{resource}/{id}/transitions/. */
export interface WorkflowTransitionsResponse {
  current_state: string | null;
  states: string[];
  /**
   * Rollenbasierte Sichten §3.2 — the CURRENT state freezes field edits
   * (status changes remain possible through an allowed transition). Optional
   * so a backend that predates this field degrades to "not locked".
   */
  fields_locked?: boolean;
  allowed_transitions: WorkflowAllowedTransition[];
}
```

(b) In `ArtifactForm.tsx`:

```tsx
/**
 * Rollenbasierte Sichten §3.2 — form mode from role AND workflow state.
 *
 * A reader never edits. An author or expert edits only while the artifact's
 * current workflow state is not `fields_locked` — an approved artifact is
 * field-read-only for everyone, and is moved on via an explicit transition
 * (which the status control still offers) rather than a direct field edit.
 *
 * UX-only: the server re-checks every write. This just stops rendering write
 * affordances that would be rejected.
 */
export function deriveFormMode(
  viewRole: ViewRole,
  fieldsLocked: boolean
): "read" | "edit" {
  if (viewRole === "reader") return "read";
  return fieldsLocked ? "read" : "edit";
}
```

The renderer takes `mode` as a prop (already in the signature). Where `ArtifactForm` is mounted by an artifact editor, compute it:

```tsx
  const mode = deriveFormMode(
    useViewRole(),
    transitions?.fields_locked === true
  );
```

Add `import { useViewRole, type ViewRole } from "../../hooks/useHasRole";` to `ArtifactForm.tsx` (Tasks 16 and 17 both reference the `ViewRole` type).

Inside the renderer, `mode === "read"` must:
- render every field with `readOnly` (inputs/textareas) or `disabled` (selects),
- **not render** `artifact-form-save`, `artifact-form-delete`, or any other field-write action, and
- **keep rendering** the three actions §3.2 explicitly allows a reader: the status/transition control (a locked state still allows a legal transition), Export, and Impact analysis. The Comments tab (Menschen-im-System Spec §"UI") is likewise a reader-permitted write and must not be gated by `mode`; when that spec lands, mount its tab unconditionally rather than behind `mode === "edit"`.

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm frontend-test sh -c "npm install && npx vitest run src/test/ArtifactFormMode.test.tsx src/test/ArtifactFormAudience.test.tsx --testTimeout=30000"`
Expected: PASS (7 + 5 passed)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/shared/ArtifactForm/ArtifactForm.tsx frontend/src/api/workflow-transitions.ts frontend/src/test/ArtifactFormMode.test.tsx
git commit -m "feat: derive artifact form mode from role and workflow state"
```

---

## Task 18: Reader default entry is the document read mode

> **PRECONDITION — Spec 10 (Dokumentensicht) must be implemented first.** The route `/documents/:id/read` and the `/documents` list do not exist on `main`.

**Files:**
- Modify: `frontend/src/components/NavigationShell/NavigationShell.tsx:130` (the `/` route)
- Test: `frontend/src/test/ReaderDefaultEntry.test.tsx`

**Interfaces:**
- Consumes: `useViewRole()` (Task 9); the `/documents` route (Spec 10)
- Produces: no new exported symbol — a route-level redirect only

- [ ] **Step 1: Write the failing test**

Create `frontend/src/test/ReaderDefaultEntry.test.tsx`:

```tsx
/**
 * Rollenbasierte Sichten §3.2 — the document read mode is the reader's default
 * entry, not the split-view form.
 */
import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { AuthContext, type AuthState } from "../context/AuthContext";
import { NavigationShell } from "../components/NavigationShell/NavigationShell";

vi.mock("../components/NavigationShell/SidebarNavigation", () => ({
  SidebarNavigation: () => <nav data-testid="sidebar-stub" />,
  NAV_ITEM_KEYS: [],
}));

function auth(roles: string[]): AuthState {
  return {
    isAuthenticated: true,
    status: "authenticated",
    user: null,
    tenantId: "t-1",
    roles,
    isTenantAdmin: false,
    expertModeEnabled: false,
    setExpertMode: async () => undefined,
    login: async () => undefined,
    updateProfile: async () => undefined,
    logout: () => undefined,
  } as unknown as AuthState;
}

function renderAtRoot(roles: string[]): void {
  render(
    <MemoryRouter initialEntries={["/"]}>
      <AuthContext.Provider value={auth(roles)}>
        <NavigationShell />
      </AuthContext.Provider>
    </MemoryRouter>
  );
}

describe("reader default entry", () => {
  it("sends a viewer to the documents list", async () => {
    renderAtRoot(["viewer"]);
    await waitFor(() => {
      expect(screen.getByTestId("documents-list")).toBeInTheDocument();
    });
  });

  it("keeps the dashboard for an editor", async () => {
    renderAtRoot(["editor"]);
    await waitFor(() => {
      expect(screen.queryByTestId("documents-list")).not.toBeInTheDocument();
    });
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm frontend-test sh -c "npm install && npx vitest run src/test/ReaderDefaultEntry.test.tsx --testTimeout=30000"`
Expected: FAIL — the viewer case renders the dashboard, not `documents-list`

- [ ] **Step 3: Write minimal implementation**

In `frontend/src/components/NavigationShell/NavigationShell.tsx`, replace the root route with a small role-aware element:

```tsx
/**
 * Rollenbasierte Sichten §3.2 — the reader view enters through the document
 * read surface, not the split-view editing shell. Everyone else keeps the
 * dashboard. `replace` so the redirect never traps the back button.
 */
function RootEntry(): JSX.Element {
  const viewRole = useViewRole();
  if (viewRole === "reader") return <Navigate to="/documents" replace />;
  return <DashboardViews />;
}
```

```tsx
              <Route path="/" element={<RootEntry />} />
```

Add `import { useViewRole } from "../../hooks/useHasRole";` (Task 9 exports `useViewRole` from that module). `Navigate` is already imported in this file.

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm frontend-test sh -c "npm install && npx vitest run src/test/ReaderDefaultEntry.test.tsx --testTimeout=30000"`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/NavigationShell/NavigationShell.tsx frontend/src/test/ReaderDefaultEntry.test.tsx
git commit -m "feat: route readers to the document read mode by default"
```

---

## Task 19: i18n keys, E2E coverage, and closing #848

**Files:**
- Modify: `frontend/src/i18n/locales/de.json`
- Modify: `frontend/src/i18n/locales/en.json`
- Create: `e2e/tests/role-based-views.spec.ts`

**Interfaces:**
- Consumes: every `t()` key introduced by Tasks 12, 13, 14, 15
- Produces: no code interface — translations plus one E2E spec

- [ ] **Step 1: Write the failing test**

Create `e2e/tests/role-based-views.spec.ts`:

```ts
/**
 * Rollenbasierte Sichten — end-to-end: a viewer sees no admin navigation and
 * no write affordance; an admin can retune navigation visibility at runtime.
 *
 * Covers GitHub issue #848 (T1) at the browser level.
 */
import { test, expect } from "@playwright/test";
import { login } from "../helpers/auth";

test.describe("role-based views", () => {
  test("a viewer sees neither admin navigation nor a create button", async ({ page }) => {
    await login(page, "viewer");
    await page.goto("/requirements");

    await expect(page.getByTestId("sidebar-nav-scroll-content")).toBeVisible();
    await expect(page.getByText("System-Einstellungen")).toHaveCount(0);
    await expect(page.getByText("Workspace-Einstellungen")).toHaveCount(0);
    // No write affordance anywhere on the list surface.
    await expect(page.getByTestId("create-requirement-btn")).toHaveCount(0);
  });

  test("an admin can hide a nav entry at runtime and a viewer stops seeing it", async ({
    page,
  }) => {
    await login(page, "admin");
    await page.goto("/system-settings?tab=navigation-visibility");
    await expect(page.getByTestId("nav-visibility-editor")).toBeVisible();

    await page
      .getByTestId("nav-visibility-select-baselines")
      .selectOption("admin");
    await page.getByTestId("nav-visibility-save").click();
    await expect(page.getByTestId("nav-visibility-status")).toBeVisible();

    await page.goto("/");
    await expect(page.getByText("Baselines")).toBeVisible();
  });

  test("the expert-mode toggle is admin-only and grants no rights", async ({ page }) => {
    await login(page, "admin");
    await page.goto("/requirements");
    await expect(page.getByTestId("expert-mode-toggle")).toBeVisible();

    await login(page, "editor");
    await page.goto("/requirements");
    await expect(page.getByTestId("expert-mode-toggle")).toHaveCount(0);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd e2e && node node_modules/@playwright/test/cli.js test tests/role-based-views.spec.ts --reporter=line`
Expected: FAIL — the navigation-visibility editor is unreachable and/or German labels resolve to their English fallback because the keys are missing

(Note: use the local `@playwright/test` cli.js explicitly; a stray root-level `node_modules/playwright` at a different version makes every spec die at `test.describe()`.)

- [ ] **Step 3: Write minimal implementation**

Add to `frontend/src/i18n/locales/de.json` at the top level (nested objects, **not** dotted flat keys inside an object — `keySeparator` is `"."`, so `{"navVisibility": {"role.admin": "..."}}` would never resolve):

```json
  "navVisibility": {
    "hint": "Steuert nur, welche Menüeinträge eine Rolle SIEHT. Das ist keine Zugriffskontrolle — der Server prüft die Berechtigung weiterhin selbst.",
    "inheritRole": "Standard ({{role}})",
    "inheritOpen": "Standard (alle Rollen)",
    "everyone": "Alle Rollen",
    "reset": "Auf Tenant-Vorgabe zurücksetzen",
    "resetDone": "Auf die Tenant-Vorgabe zurückgesetzt.",
    "resetFailed": "Zurücksetzen fehlgeschlagen.",
    "savedGlobal": "Gespeichert. In {{count}} Workspace(s) ohne eigene Anpassung übernommen.",
    "savedWorkspace": "Gespeichert.",
    "saveFailed": "Speichern fehlgeschlagen.",
    "loadFailed": "Die Navigations-Sichtbarkeit konnte nicht geladen werden.",
    "role": {
      "admin": "Admin",
      "approver": "Freigeber",
      "editor": "Bearbeiter",
      "viewer": "Leser"
    }
  },
  "expertMode": {
    "label": "Expertenmodus",
    "hint": "Zeigt Expertenbereiche standardmäßig aufgeklappt. Ändert keine Berechtigungen."
  },
```

and inside the existing `systemSettings` object add `"tabs": {"navigationVisibility": "Navigation"}` (merging with the existing `tabs` entries), plus the same under `settings` for the workspace surface. Add to the existing `attributeEditor` block (created by Spec 2):

```json
    "audienceLabel": "Nur für Experten",
    "audienceHint": "Nur für Experten: Sektion startet eingeklappt. Verbirgt das Feld nicht."
```

Mirror all of the above in `frontend/src/i18n/locales/en.json`:

```json
  "navVisibility": {
    "hint": "Controls only which menu entries a role SEES. This is not access control — the server still checks permissions itself.",
    "inheritRole": "Default ({{role}})",
    "inheritOpen": "Default (all roles)",
    "everyone": "All roles",
    "reset": "Reset to tenant default",
    "resetDone": "Reset to the tenant default.",
    "resetFailed": "Reset failed.",
    "savedGlobal": "Saved. Applied to {{count}} workspace(s) without their own override.",
    "savedWorkspace": "Saved.",
    "saveFailed": "Save failed.",
    "loadFailed": "Navigation visibility could not be loaded.",
    "role": {
      "admin": "Admin",
      "approver": "Approver",
      "editor": "Editor",
      "viewer": "Viewer"
    }
  },
  "expertMode": {
    "label": "Expert mode",
    "hint": "Expands expert sections by default. Grants no additional permissions."
  },
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm frontend-test sh -c "npm install && npx vitest run src/test --testTimeout=30000"`
Expected: PASS (no missing-key regressions in the existing suites)

Then restart the frontend container (Vite has no working HMR on Windows — E2E otherwise tests stale code) and run the targeted spec:

Run: `docker compose -f deploy/docker-compose.yml --project-directory . restart frontend && cd e2e && node node_modules/@playwright/test/cli.js test tests/role-based-views.spec.ts --reporter=line`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/i18n/locales/de.json frontend/src/i18n/locales/en.json e2e/tests/role-based-views.spec.ts
git commit -m "feat: add role-based-view translations and e2e coverage"
```

---

## Post-implementation notes for the human reviewer

- **GitHub issue #848 can be closed once this plan is complete.** Its hard minimal fix (`NAV_ITEMS.requires`, role-gated buttons, not-rendered instead of disabled) was already merged in commit `54b09760`; Tasks 11, 12, 13 and 17 supersede that fix with a runtime-configurable version and extend it to the workflow-state dimension the issue never covered. No commit in this plan references #848 — closing it is a manual step after review, exactly as the spec's §8 risk note asks.
- **The OFFENE FRAGE above needs a decision before rollout, not before implementation.** The shipped default is "no change to what a viewer sees". Turning §3.2's 5-area reader navigation into the actual default is one `PUT /navigation-visibility-defaults/` — no code, no migration, no deploy.
- **Deliberately not built** (flagged so the omission is a decision, not an oversight): an MCP tool group for navigation visibility (the spec never asks for one, and the surface is a settings screen); a `PATCH` variant of the navigation endpoints (`PUT` + `reset` covers every UI flow); an OpenAPI addendum file (drf-spectacular generates the schema from the views); the per-user filter on `/reviews` implied by §3.2's "Freigaben (nur eigene)" (no such filter exists today — a separate change).
- **Tasks 15, 16, 17 are blocked on Spec 2** and **Task 18 is blocked on Spec 10**. Tasks 1-14 and 19 are independently shippable against `main` today.
