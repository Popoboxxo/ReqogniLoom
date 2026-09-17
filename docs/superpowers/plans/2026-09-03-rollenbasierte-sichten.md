# Rollenbasierte Sichten Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the three existing workspace roles into three real UI views — a read-only Leser view, an unchanged Autor view and an Experte view with an expert-mode density toggle — by making navigation visibility a runtime-editable system object, deriving the artifact form's read/edit mode from role plus workflow state, and hiding (not disabling) every write affordance a role cannot use.

**Architecture:** Navigation visibility becomes a fifth Global/Workspace system object in `auth_tenancy` (one JSON map per scope, materialized copy + `is_customized`, byte-identical to the `GlobalPermissionDefinition`/`WorkspacePermissionDefinition` pair that already lives in that app), so a tenant admin changes which role sees which nav entry at runtime without a deploy. Form density and form mode stay code logic as the spec demands: `ArtifactForm` derives its effective mode from the caller's role and the artifact's workflow state, and expands `audience="expert"` sections only when an `admin`/`approver` has switched on the persisted `User.expert_mode_enabled` preference. Every write affordance that a role may not use is filtered out of `PageHeader` at the single shared seam all 15 artifact routes already route through, instead of being disabled per page.

**Tech Stack:** Django 5.2 + DRF (`APIView`, no ORM in views — ADR-01), PostgreSQL 16 with row-level security, React 18 + TypeScript 5.5 strict, `react-i18next`, Vitest + Testing Library, CSS Modules with `styles/tokens.css` custom properties.

**Spec:** docs/superpowers/specs/2026-09-03-rollenbasierte-sichten-design.md

## Global Constraints

- Role strings are exactly `admin`, `editor`, `viewer`, `approver` (`backend/auth_tenancy/models.py:35-45`, `ROLE_CHOICES`). No new role is introduced; this spec is a pure UX consequence of the existing RBAC.
- View mapping: **Leser** = `viewer`, **Autor** = `editor`, **Experte** = `admin` + `approver`.
- `admin` is a superset of every lesser role in every UI gate (`frontend/src/hooks/useHasRole.ts:23`). Do not change that rule.
- An entry a role may not see is **not rendered** — never CSS-hidden, never merely `disabled`.
- Neither navigation visibility nor `audience` nor the expert mode is a security boundary. The server-side RBAC check on the route/API remains the only enforcement. Every new module carries that sentence in its docstring.
- `audience` is `"basic" | "expert"`, default `"basic"`, and lives in `definition_json.attributes[]` of the Attribute-Definition system object. It controls **only** the default expand density in `ArtifactForm`; `visible` remains the visibility property.
- `expert_mode_enabled` is a `BooleanField(default=False)` on `persistence.User`, additive, and changes only what is initially expanded — never what is editable.
- New `TenantScopedModel` tables ship their own RLS migration (ENABLE + FORCE ROW LEVEL SECURITY + one `ALL` policy on `app.current_tenant`), or `backend/persistence/tests/test_rls_coverage.py` fails.
- No ORM in `backend/rest_api/**` — `backend/rest_api/tests/test_architecture.py::test_no_new_direct_orm_access` gives every new view file a ceiling of **0** `.objects.` / `.unscoped.` lines.
- No new inline `style={{` in `frontend/src/components/**` — `frontend/src/test/ui-ratchet.test.ts:830` asserts `toBe(STYLE_BRACE_BASELINE)` (currently `1015`), an exact match in both directions. New UI ships as CSS Modules.
- Every new i18n key exists in both `frontend/src/i18n/locales/de.json` and `en.json` as **nested objects**, never dotted flat keys (`keySeparator` is `"."`).
- Only the already-declared `AuditEntry.OP_UPDATE` (`"update"`) is used for audit writes. `AuditEntry.OP_CHOICES` is validated by `full_clean()`; an undeclared string 500s the service *after* its mutation succeeded.
- `data-testid` on every new interactive element. Existing test ids are never moved (nine e2e specs reference `create-arch-btn` alone).
- Commits follow Conventional Commits; branch is `feat/rollenbasierte-sichten` (never `main`).

---

## Preconditions and verified deviations from the spec

Verified against the working tree on 2026-09-04 (branch `chore/archive-implemented-specs-plans`, spec read from `main`). Each one changes what a task must do; none blocks the plan.

### P1 — Commit `54b09760` already shipped part of T1/#848 (scope reduction)

The user asked explicitly whether the P0-hardening commit already introduced role-gating for navigation. It did. Verified in the tree:

* `frontend/src/hooks/useHasRole.ts` **exists** (`export type RequiredRole = 'admin' | 'editor'`, `useHasRole(): (required?: RequiredRole) => boolean`), created by that commit as the shared gate.
* `NAV_ITEMS` **exists** in `frontend/src/components/NavigationShell/SidebarNavigation.tsx:74-134` and already carries `requires?: "admin" | "editor"` (line 71), set on `/settings` (line 118) and `/system-settings` (line 122). The filter is `.filter((item) => hasRole(item.requires))` at line 412.
* `/user-management` is filtered separately at lines 416-419 against `isTenantAdmin || isAdmin`, because tenant-admin is a tenant-wide concept the workspace `roles` array cannot express.
* Requirement write controls are already gated: `RequirementForm.tsx:140`, `RequirementList.tsx:175`, `RequirementEditors.tsx:73/420/681/702`, `ReqTraceLinkPanel.tsx:180`.

**Consequence for this plan:** Phase C is an **extension of an existing hardcoded gate into a data-driven one**, not a new build, and the "hide viewer write buttons" work (Phase E) is a rollout of an established idiom to the 14 routes that commit did not reach — not a from-scratch mechanism. The plan is roughly half the size the spec implies.

### P2 — Hard ordering dependency on the Attribute-Definition plan

`frontend/src/components/shared/ArtifactForm/ArtifactForm.tsx` does **not exist yet**. It is created by `docs/superpowers/plans/2026-09-03-attribute-definition.md` Task 18, which also already delivers, verbatim:

* the `audience: AttributeAudience` field on `AttributeSpec` (plan lines 5942, 8234) and its `"basic"` default plus `AUDIENCE_VALUES` validation (lines 953-957),
* the `mode?: "edit" | "read"` prop on `ArtifactFormProps` with the comment `/** "read" disables every control (Rollenbasierte-Sichten spec). */`,
* `groupIntoSections()` returning a per-section `audience` (`"expert"` only when **every** attribute in the section is), and `isSectionOpen()` whose last line is `return section.audience !== "expert";` (line 8341),
* the `AttributeInspector` toggle `data-testid="attribute-inspector-audience"` that writes `audience` (lines 11270-11274).

**Consequence:** spec section 4 needs **no new work in this plan** — it is already implemented by plan #2. This plan only *consumes* it: Task 13 replaces the one line `return section.audience !== "expert";` with an expert-mode-aware version and adds the toggle. Phase D must not start before plan #2's Task 18 has landed. Phases A, B, C and E have no such dependency and can proceed independently.

### P3 — There are 25 nav items today, not 26

The spec says "die 26 heutigen Nav-Einträge". Counted in `NAV_ITEMS` (`SidebarNavigation.tsx:74-134`): 25 entries (`/`, `/goals`, `/metrics`, `/interviews`, `/needs`, `/requirements`, `/adrs`, `/risks`, `/issues`, `/glossary`, `/architecture`, `/traceability`, `/impact`, `/icds`, `/diagrams`, `/testcases`, `/test-runs`, `/baselines`, `/reviews`, `/import`, `/workflows`, `/audit`, `/settings`, `/system-settings`, `/user-management`). No task hardcodes a count; the catalogue is derived from the array itself (see D2).

### P4 — There is no per-state "frozen" concept anywhere in the workflow engine

Spec §3.2 requires an `approved` artifact to be read-only for the Autor role. Verified: workflow states are plain strings (`workflow/definition_store.py:599-811`), the `/{resource}/{id}/transitions/` GET returns only `{current_state, states, allowed_transitions[]}` (`backend/rest_api/mixins/workflow_transitions.py:142`), and nothing in `workflow/`, `presets/` or `application/preset_policy_service.py` marks a state as edit-freezing. The shipped default state names are also mixed-case and partly German (`["Draft", "In Review", "Approved", "Rejected", "Superseded"]`, `["Entwurf", "Freigegeben", "Archiviert"]`), and a workspace admin can rename them at runtime in the Workflow Editor.

**Consequence:** the frozen set is derived by a documented case-insensitive name heuristic, exactly mirroring the precedent already in the codebase for this same problem — `ERROR_STATE_PATTERN` in `frontend/src/api/workflows.ts:141`, whose own comment reads *"no dedicated 'error' type exists in the backend model"*. See D5.

### P5 — `UserProfileService` stringifies every editable field

`backend/auth_tenancy/services/profile_service.py:55` writes `setattr(user, field, str(validated_data[field]).strip())`. Adding `expert_mode_enabled` to `_EDITABLE_PROFILE_FIELDS` would persist the **string** `"True"` into a `BooleanField`. Task 5 adds a separate boolean branch instead of extending that tuple.

### P6 — `UserProfileSerializer` rejects unknown keys with 400

`backend/rest_api/serializers.py:1915-1994`: `WRITABLE_FIELDS = ("first_name", "last_name")` and `validate()` raises `"Unknown field."` for anything else (QIRK-002/#73). A `PATCH /auth/me/ {"expert_mode_enabled": true}` therefore 400s today. Task 5 must extend `WRITABLE_FIELDS` **and** declare the field, or the endpoint stays closed.

### P7 — `at_api_key` / `at_user_role` are deliberately RLS-exempt

`backend/auth_tenancy/migrations/0011_rls_policies.py` documents why. The two new tables here are read strictly *after* authentication (the sidebar and the editor both run inside an authenticated request), so they get the standard policy and need **no** `RLS_EXEMPT_TABLES` entry.

---

## Open questions

**OFFENE FRAGE (non-blocking, deferred by decision):** spec §3.2 names the Dokument-Lesemodus as the Leser role's default entry point. That route (`/documents/<id>/read`, Dokumentensicht spec §4) does not exist and has no implementation plan yet — Dokumentensicht is #10 in the series and is unplanned. A redirect to it today would fall through `NavigationShell`'s `<Route path="*" element={<Navigate to="/" replace />} />` and silently land on the dashboard, which is already the viewer's landing page. **Resolution:** no task is spent on it; the switch is a one-line change to a single constant once `/documents` exists. Recorded as D7 and repeated in the rollout notes so the Dokumentensicht plan picks it up.

No other ambiguity blocks implementation. Six spec ambiguities are resolved by explicit decision below rather than by guessing.

---

## Decisions

**D1 — One JSON map per scope, not one row per nav item.** The spec sketches `nav_item_key` as a column with `unique(tenant, nav_item_key)` — 25 rows per tenant plus 25 per workspace, and a 25-row read on every sidebar render. But it justifies the design as "demselben Muster wie Attribut-Definition, Workflow-Defaults und Link-Type-Definition", and all three of those store a **single JSON document per scope** (`workflow_json`, `permission_json`, `definition_json`). Following the invoked pattern therefore means `visibility_json: {nav_item_key: required_role | null}` on a per-tenant and per-workspace singleton. This is both lazier and more consistent than the literal sketch. `version`, `source_global`, `is_customized` and the materialized-copy semantics are kept exactly as the spec asks.

**D2 — The nav-item catalogue stays in the frontend only; the backend validates shape, not membership.** The spec itself says "welche **Seiten** existieren, ist Code, nicht Daten". Mirroring the 25 keys into a backend constant would create a second source of truth that silently drifts every time a route is added. Instead: the backend validates that keys match `^[a-z0-9][a-z0-9-]{0,63}$` and that values are `null` or a member of `ROLE_CHOICES`; the editor renders one row per frontend `NAV_ITEMS` entry; the sidebar ignores map keys it does not know. Adding a nav item needs no migration and no backend change.

**D3 — The seed is the model default `{"settings": "admin", "system-settings": "admin"}`, not a bootstrap command.** Those are the only two entries carrying `requires` today (`SidebarNavigation.tsx:118,122`); a missing key means "no role required", which is exactly the current behaviour of `hasRole(undefined) === true`. The Ist-Zustand is therefore a two-entry dict and needs no management command, no data migration and no per-tenant backfill. `/user-management` is deliberately **not** in the map — its gate is `isTenantAdmin`, which the workspace-role map cannot express (P1); it keeps its dedicated filter.

**D4 — The models live in `auth_tenancy`, not in a new app.** `GlobalPermissionDefinition`/`WorkspacePermissionDefinition` already live there and are the exact structural template. Reusing the app avoids a new `REQFLOW_APPS` entry, a new `apps.py`, a new test package and a new RLS-migration home. Nav visibility is role→visibility mapping, i.e. permission-adjacent, so the app boundary is also semantically right.

**D5 — Frozen-state detection is a documented case-insensitive substring heuristic in the frontend.** See P4. Spec §6 explicitly states the form-mode derivation "bleibt Code-Logik, keine Konfigurationsdaten", so this is not a system object. The fragment list is derived from the shipped defaults in `workflow/definition_store.py`. **Known ceiling, named in the code:** a workspace that renames a state to something outside the list loses the freeze, and a hypothetical `"Nicht freigegeben"` would be falsely frozen. The upgrade path is a `frozen: true` flag per state in `workflow_json` plus a checkbox in the existing Workflow Editor — strictly more work than this spec funds, and pointless before anyone hits the limitation.

**D6 — The expert-mode toggle lives inside `ArtifactForm`, not in each of the seven detail routes.** Spec §5 says "ein Umschalter in der Detailansicht". `ArtifactForm` *is* the detail view for all seven artifact types after plan #2, so one placement covers all of them, needs no prop threading through seven call sites, and cannot drift between them. `ArtifactForm` reads `useAuth().expertModeEnabled` directly for the same reason.

**D7 — The Leser default-entry redirect is deferred to the Dokumentensicht plan.** See the Open Questions block.

**D8 — Viewer write-affordance hiding is implemented once in `PageHeader`, not once per route.** All 15 artifact/list routes render their create button through `PageHeader.primaryAction` (`frontend/src/components/shared/PageHeader.tsx:66`, consumers verified by grep). A `requiresRole?: RequiredRole` field on `PageHeaderAction` filtered inside `PageHeader` is one guard in the shared component instead of fifteen guards in fifteen callers, and it also covers `secondaryActions`/`overflowActions` for free. `RequirementEditors.tsx:419-430` already hand-rolls this with a ternary and is simplified onto the shared field in the same task, so exactly one idiom survives.

---

## File Structure

### Backend — new files

| File | Responsibility |
|---|---|
| `backend/auth_tenancy/navigation_catalogue.py` | Pure, DB-free vocabulary: `NAVIGATION_ROLE_VALUES`, `NAV_ITEM_KEY_PATTERN`, `DEFAULT_NAVIGATION_VISIBILITY`, `NavigationVisibilityError`, `normalize_visibility_map` |
| `backend/auth_tenancy/services/navigation_visibility.py` | `NavigationVisibilityService` — global get/replace + propagation, workspace get/replace/reset |
| `backend/auth_tenancy/migrations/0013_navigation_visibility.py` | The two tables |
| `backend/auth_tenancy/migrations/0014_navigation_visibility_rls_policies.py` | RLS policies for both tables |
| `backend/auth_tenancy/tests/test_navigation_catalogue.py` | Vocabulary + normalization tests |
| `backend/auth_tenancy/tests/test_navigation_visibility_service.py` | Service tests (seed, propagation, customization, reset) |
| `backend/rest_api/navigation_visibility_views.py` | 3 `APIView`s, zero ORM |
| `backend/rest_api/tests/test_navigation_visibility_rest.py` | REST contract tests |
| `backend/persistence/migrations/0070_user_expert_mode_enabled.py` | `User.expert_mode_enabled` |
| `backend/auth_tenancy/tests/test_expert_mode_preference.py` | Profile-service boolean-write tests |

### Backend — changed files

| File | Change |
|---|---|
| `backend/auth_tenancy/models.py:645-665` | add `GlobalNavigationVisibility`, `WorkspaceNavigationVisibility` + `__all__` entries |
| `backend/persistence/models.py:499-522` | add `expert_mode_enabled = models.BooleanField(default=False)` to `User` |
| `backend/auth_tenancy/services/profile_service.py:24,52-58` | `_EDITABLE_BOOLEAN_PROFILE_FIELDS` + a boolean write branch |
| `backend/rest_api/serializers.py:1929,1959` | `UserProfileSerializer.WRITABLE_FIELDS` + `expert_mode_enabled` field + `update()` branch |
| `backend/rest_api/auth_views.py:154-165` | `_user_payload` exposes `expert_mode_enabled` |
| `backend/rest_api/urls.py` | register the 3 navigation-visibility routes |
| `backend/application/cache_invalidation.py:66-82` | `navigation_visibility_cache_key` + include it in `_workspace_keys` |

### Frontend — new files

| File | Responsibility |
|---|---|
| `frontend/src/api/navigation-visibility.ts` | `navigationVisibilityApi` + `NavigationVisibilityMap` / scope payload types |
| `frontend/src/components/NavigationShell/nav-items.ts` | `NavItem`, `NavGroupId`, `NAV_GROUP_ORDER`, `NAV_GROUP_LABEL_KEYS`, `NAV_ITEMS` (extracted, now with `key`) |
| `frontend/src/hooks/useNavigationVisibility.ts` | Resolved workspace map + `FALLBACK_NAVIGATION_VISIBILITY` |
| `frontend/src/components/NavigationVisibilityEditor/NavigationVisibilityEditor.tsx` | `scope`-parameterized editor (global / workspace) |
| `frontend/src/components/NavigationVisibilityEditor/NavigationVisibilityEditor.module.css` | styling (no inline `style={{`) |
| `frontend/src/components/NavigationVisibilityEditor/index.ts` | named re-exports |
| `frontend/src/components/shared/ArtifactForm/form-mode.ts` | `FROZEN_STATE_FRAGMENTS`, `isFrozenState`, `deriveFormMode` |
| `frontend/src/components/shared/ArtifactForm/form-mode.test.ts` | pure-function tests |
| `frontend/src/test/NavigationVisibility.test.tsx` | sidebar consumption tests |
| `frontend/src/components/NavigationVisibilityEditor/NavigationVisibilityEditor.test.tsx` | editor tests |

### Frontend — changed files

| File | Change |
|---|---|
| `frontend/src/hooks/useHasRole.ts:18` | widen `RequiredRole` to all four roles |
| `frontend/src/components/NavigationShell/SidebarNavigation.tsx:31-134,408-419` | import the extracted catalogue; resolve `requires` from the fetched map |
| `frontend/src/context/AuthContext.tsx:77-96,124-249` | `expertModeEnabled` + `setExpertMode` |
| `frontend/src/components/shared/PageHeader.tsx:30-50,137-138` | `PageHeaderAction.requiresRole` + filtering |
| `frontend/src/components/shared/ArtifactForm/ArtifactForm.tsx` | effective mode, expert-mode collapse, expert toggle |
| `frontend/src/components/SystemSettings/SystemSettings.tsx:33-79,150-175` | `navigation-visibility` tab |
| `frontend/src/components/WorkspaceSettings/WorkspaceSettings.tsx` | `navigation-visibility` tab |
| 15 route files (Task 15) | `requiresRole: "editor"` on the create affordance |
| `frontend/src/i18n/locales/{de,en}.json` | `navigationVisibility.*`, `artifactForm.expertMode*` key trees |
| `frontend/src/api/index.ts` | export `navigationVisibilityApi` |

---

## Phase A — Backend: navigation visibility as a system object

### Task 1: Navigation-visibility vocabulary

**Files:**
- Create: `backend/auth_tenancy/navigation_catalogue.py`
- Test: `backend/auth_tenancy/tests/test_navigation_catalogue.py`

**Interfaces:**
- Consumes: `auth_tenancy.models.ROLE_ADMIN/ROLE_EDITOR/ROLE_VIEWER/ROLE_APPROVER`
- Produces: `NAVIGATION_ROLE_VALUES: frozenset[str]`, `NAV_ITEM_KEY_PATTERN: re.Pattern[str]`, `DEFAULT_NAVIGATION_VISIBILITY: dict[str, str]`, `NavigationVisibilityError(ValueError)`, `normalize_visibility_map(raw: object) -> dict[str, str | None]`

- [ ] **Step 1: Write the failing test**

Create `backend/auth_tenancy/tests/test_navigation_catalogue.py`:

```python
"""Vocabulary + normalization for the navigation-visibility map."""
from __future__ import annotations

import pytest

from auth_tenancy.navigation_catalogue import (
    DEFAULT_NAVIGATION_VISIBILITY,
    NAVIGATION_ROLE_VALUES,
    NavigationVisibilityError,
    normalize_visibility_map,
)


def test_default_seed_is_todays_hardcoded_state() -> None:
    assert DEFAULT_NAVIGATION_VISIBILITY == {
        "settings": "admin",
        "system-settings": "admin",
    }


def test_role_values_are_the_four_rbac_roles() -> None:
    assert NAVIGATION_ROLE_VALUES == frozenset(
        {"admin", "editor", "viewer", "approver"}
    )


def test_normalize_accepts_null_for_no_requirement() -> None:
    assert normalize_visibility_map({"glossary": None}) == {"glossary": None}


def test_normalize_returns_a_copy_not_the_input() -> None:
    raw = {"settings": "admin"}
    out = normalize_visibility_map(raw)
    out["settings"] = "editor"
    assert raw["settings"] == "admin"


def test_normalize_rejects_a_non_mapping() -> None:
    with pytest.raises(NavigationVisibilityError, match="JSON object"):
        normalize_visibility_map(["settings"])


def test_normalize_rejects_an_unknown_role() -> None:
    with pytest.raises(NavigationVisibilityError, match="required_role"):
        normalize_visibility_map({"settings": "superuser"})


def test_normalize_rejects_a_malformed_key() -> None:
    with pytest.raises(NavigationVisibilityError, match="nav_item_key"):
        normalize_visibility_map({"System Settings": "admin"})


def test_normalize_rejects_a_key_over_64_chars() -> None:
    with pytest.raises(NavigationVisibilityError, match="nav_item_key"):
        normalize_visibility_map({"a" * 65: None})


def test_normalize_accepts_the_empty_map() -> None:
    assert normalize_visibility_map({}) == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -e DB_NAME=test_navvis backend-test pytest auth_tenancy/tests/test_navigation_catalogue.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'auth_tenancy.navigation_catalogue'`

- [ ] **Step 3: Write minimal implementation**

Create `backend/auth_tenancy/navigation_catalogue.py`:

```python
"""Navigation-visibility vocabulary (Rollenbasierte-Sichten spec, section 3.1).

Pure, DB-free validation for the ``visibility_json`` map carried by
:class:`auth_tenancy.models.GlobalNavigationVisibility` and
:class:`auth_tenancy.models.WorkspaceNavigationVisibility`.

Design note (plan decision D2): WHICH pages exist stays code — the catalogue of
``nav_item_key`` values lives in the frontend's ``NAV_ITEMS`` array and nowhere
else, so adding a route never needs a migration. This module therefore validates
the SHAPE of a key (and the membership of a role), never the membership of a
key. A key the sidebar does not know is simply ignored when rendering.

NOT A SECURITY BOUNDARY: hiding a nav entry does not stop a direct URL call. The
server-side RBAC check on the route/API is the only enforcement, exactly as it
is today.
"""
from __future__ import annotations

import re
from typing import Any

from auth_tenancy.models import (
    ROLE_ADMIN,
    ROLE_APPROVER,
    ROLE_EDITOR,
    ROLE_VIEWER,
)

#: Roles a nav entry may require. ``None`` means "no role required".
NAVIGATION_ROLE_VALUES = frozenset(
    {ROLE_ADMIN, ROLE_EDITOR, ROLE_VIEWER, ROLE_APPROVER}
)

#: Shape of a ``nav_item_key`` — the frontend derives it from the route path
#: ("/system-settings" -> "system-settings", "/" -> "dashboard").
NAV_ITEM_KEY_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")

#: Bootstrap seed (plan decision D3): the Ist-Zustand of the two entries that
#: carry a hardcoded ``requires`` in SidebarNavigation.tsx today. Every other
#: entry is absent, which resolves to "no role required" — byte-identical to
#: today's ``hasRole(undefined) === true``.
DEFAULT_NAVIGATION_VISIBILITY: dict[str, str] = {
    "settings": ROLE_ADMIN,
    "system-settings": ROLE_ADMIN,
}


class NavigationVisibilityError(ValueError):
    """Raised when a supplied visibility map is not a valid document."""


def normalize_visibility_map(raw: Any) -> dict[str, str | None]:
    """Validate *raw* and return a defensive copy of the map.

    Args:
        raw: The caller-supplied ``{nav_item_key: required_role | None}`` map.

    Returns:
        A new dict with the same entries.

    Raises:
        NavigationVisibilityError: On a non-mapping, a malformed key or an
            unknown role value.
    """
    if not isinstance(raw, dict):
        raise NavigationVisibilityError("visibility must be a JSON object.")

    out: dict[str, str | None] = {}
    for key, value in raw.items():
        if not isinstance(key, str) or not NAV_ITEM_KEY_PATTERN.match(key):
            raise NavigationVisibilityError(
                f"Invalid nav_item_key {key!r}: expected lowercase "
                f"letters/digits/hyphens, 1-64 characters."
            )
        if value is None:
            out[key] = None
            continue
        if not isinstance(value, str) or value not in NAVIGATION_ROLE_VALUES:
            raise NavigationVisibilityError(
                f"Invalid required_role {value!r} for {key!r}: expected null "
                f"or one of {sorted(NAVIGATION_ROLE_VALUES)}."
            )
        out[key] = value
    return out


__all__ = [
    "DEFAULT_NAVIGATION_VISIBILITY",
    "NAVIGATION_ROLE_VALUES",
    "NAV_ITEM_KEY_PATTERN",
    "NavigationVisibilityError",
    "normalize_visibility_map",
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -e DB_NAME=test_navvis backend-test pytest auth_tenancy/tests/test_navigation_catalogue.py -v`
Expected: PASS (9 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/auth_tenancy/navigation_catalogue.py backend/auth_tenancy/tests/test_navigation_catalogue.py
git commit -m "feat: add navigation-visibility vocabulary and map normalization"
```

---

### Task 2: Navigation-visibility models, migration and RLS

**Files:**
- Modify: `backend/auth_tenancy/models.py:643-665`
- Create: `backend/auth_tenancy/migrations/0013_navigation_visibility.py`
- Create: `backend/auth_tenancy/migrations/0014_navigation_visibility_rls_policies.py`
- Test: `backend/auth_tenancy/tests/test_navigation_visibility_models.py`

**Interfaces:**
- Consumes: `navigation_catalogue.DEFAULT_NAVIGATION_VISIBILITY`
- Produces: `GlobalNavigationVisibility` (table `at_global_navigation_visibility`), `WorkspaceNavigationVisibility` (table `at_workspace_navigation_visibility`)

- [ ] **Step 1: Write the failing test**

Create `backend/auth_tenancy/tests/test_navigation_visibility_models.py`:

```python
"""Schema-level guarantees of the two navigation-visibility tables."""
from __future__ import annotations

import pytest
from django.db import connection

from auth_tenancy.models import (
    GlobalNavigationVisibility,
    WorkspaceNavigationVisibility,
)
from persistence.tests.test_rls_coverage import RLS_EXEMPT_TABLES


def test_tables_are_named_after_the_at_prefix_convention() -> None:
    assert GlobalNavigationVisibility._meta.db_table == (
        "at_global_navigation_visibility"
    )
    assert WorkspaceNavigationVisibility._meta.db_table == (
        "at_workspace_navigation_visibility"
    )


def test_version_is_inherited_not_redeclared() -> None:
    # AuditableModel already supplies `version`; redeclaring it would be a
    # Django field clash (same finding as the attribute-definition plan, P3).
    own = {f.name for f in GlobalNavigationVisibility._meta.local_fields}
    assert "version" not in own


def test_workspace_row_carries_the_inheritance_signals() -> None:
    names = {f.name for f in WorkspaceNavigationVisibility._meta.local_fields}
    assert {"workspace", "visibility_json", "source_global", "is_customized"} <= names


def test_neither_table_claims_an_rls_exemption() -> None:
    assert "at_global_navigation_visibility" not in RLS_EXEMPT_TABLES
    assert "at_workspace_navigation_visibility" not in RLS_EXEMPT_TABLES


@pytest.mark.django_db
@pytest.mark.skipif(
    connection.vendor != "postgresql", reason="PostgreSQL-only assertion"
)
def test_rls_is_enabled_and_forced_on_both_tables() -> None:
    with connection.cursor() as cur:
        cur.execute(
            "SELECT relname, relrowsecurity, relforcerowsecurity "
            "FROM pg_class WHERE relname IN (%s, %s)",
            ["at_global_navigation_visibility", "at_workspace_navigation_visibility"],
        )
        rows = {name: (enabled, forced) for name, enabled, forced in cur.fetchall()}
    assert rows["at_global_navigation_visibility"] == (True, True)
    assert rows["at_workspace_navigation_visibility"] == (True, True)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -e DB_NAME=test_navvis backend-test pytest auth_tenancy/tests/test_navigation_visibility_models.py -v --create-db`
Expected: FAIL with `ImportError: cannot import name 'GlobalNavigationVisibility' from 'auth_tenancy.models'`

- [ ] **Step 3: Write the models**

In `backend/auth_tenancy/models.py`, insert immediately before the `__all__` block at line 645:

```python
# ---------------------------------------------------------------------------
# Navigation visibility (Rollenbasierte-Sichten spec, section 3.1)
# ---------------------------------------------------------------------------
#
# Which ROLE may see which nav entry becomes data; which PAGES exist stays code
# (plan decision D2). Structurally identical to the Global/Workspace permission
# definition pair above: materialized copy, `source_global` back-link,
# `is_customized` on-default signal, inherited optimistic-lock `version`.
#
# NOT A SECURITY BOUNDARY — hiding a nav entry does not block the route; the
# server-side RBAC check on the route/API is the enforcement, unchanged.


class GlobalNavigationVisibility(TenantScopedModel):
    """Tenant-wide default nav-entry -> required-role map.

    ``visibility_json`` holds ``{nav_item_key: required_role | null}``, e.g.::

        {"settings": "admin", "system-settings": "admin"}

    A key that is absent requires no role. Exactly one row per tenant.
    """

    visibility_json = models.JSONField(default=dict)

    class Meta:
        db_table = "at_global_navigation_visibility"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant"],
                name="uq_global_nav_vis_tenant",
            )
        ]

    def __str__(self) -> str:
        return (
            f"GlobalNavigationVisibility(tenant:{self.tenant_id}, "
            f"{len(self.visibility_json or {})} entries)"
        )


class WorkspaceNavigationVisibility(TenantScopedModel):
    """Per-workspace nav-entry -> required-role override.

    Materialized copy of :class:`GlobalNavigationVisibility`. ``source_global``
    is ``SET_NULL`` so deleting the tenant default never cascade-deletes a live
    override; ``is_customized`` is the on-default (False) / customized (True)
    signal, and reset copies ``source_global.visibility_json`` back in.
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
        related_name="derived_visibilities",
    )
    is_customized = models.BooleanField(default=False)

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
        state = "customized" if self.is_customized else "on-default"
        return f"WorkspaceNavigationVisibility(ws:{self.workspace_id}, {state})"
```

Then extend `__all__` (line 645) with `"GlobalNavigationVisibility",` and `"WorkspaceNavigationVisibility",` directly after `"WorkspacePermissionDefinition",`.

- [ ] **Step 4: Generate the schema migration**

Run: `docker-compose -f deploy/docker-compose.yml -f deploy/docker-compose.override.yml --project-directory . exec backend python manage.py makemigrations auth_tenancy --name navigation_visibility`
Expected: `Migrations for 'auth_tenancy': 0013_navigation_visibility.py — Create model GlobalNavigationVisibility, Create model WorkspaceNavigationVisibility`

- [ ] **Step 5: Write the RLS migration**

Create `backend/auth_tenancy/migrations/0014_navigation_visibility_rls_policies.py`:

```python
"""
COMP-PL-006 RLSPolicyEnforcer — RLS for the navigation-visibility tables.

Requirements:
- REQ-L2-PL-010 (RLS on all tenant-scoped tables)
- ADR-PL-03 (RLS as a second isolation layer behind the ORM tenant filter)

Both tables are ``TenantScopedModel`` subclasses and already carry a
``tenant_id`` UUID column, so this migration is purely additive DDL.

Policy semantics (byte-identical to auth_tenancy/0011 and persistence/0003):
    ENABLE + FORCE ROW LEVEL SECURITY plus one ``ALL`` policy keyed on the
    session variable ``app.current_tenant``. An unset/empty setting matches no
    rows (closed-world default).

Access-path review: both tables are read and written exclusively by
``NavigationVisibilityService``, which runs inside request-scoped REST views —
i.e. strictly downstream of ``TenantContextService.activate``, which arms
``app.current_tenant`` during DRF authentication. There is no pre-auth reader
(unlike ``at_api_key``/``at_user_role``, see 0011's exemption note), so no
``RLS_EXEMPT_TABLES`` entry is needed.

leaf_id : COMP-PL-006
req_id  : REQ-L2-PL-010
"""
from __future__ import annotations

from django.db import migrations

_TENANT_TABLES = [
    "at_global_navigation_visibility",
    "at_workspace_navigation_visibility",
]


def _enable_sql() -> str:
    parts = []
    for table in _TENANT_TABLES:
        policy = f"{table}_tenant_isolation"
        parts.append(
            f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;\n"
            f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;\n"
            f"CREATE POLICY {policy} ON {table}\n"
            f"    USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)\n"
            f"    WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid);"
        )
    return "\n".join(parts)


def _disable_sql() -> str:
    parts = []
    for table in _TENANT_TABLES:
        policy = f"{table}_tenant_isolation"
        parts.append(
            f"DROP POLICY IF EXISTS {policy} ON {table};\n"
            f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;\n"
            f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;"
        )
    return "\n".join(parts)


class Migration(migrations.Migration):

    dependencies = [
        ("auth_tenancy", "0013_navigation_visibility"),
    ]

    operations = [
        migrations.RunSQL(sql=_enable_sql(), reverse_sql=_disable_sql()),
    ]
```

- [ ] **Step 6: Run test to verify it passes**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -e DB_NAME=test_navvis backend-test pytest auth_tenancy/tests/test_navigation_visibility_models.py persistence/tests/test_rls_coverage.py -v --create-db`
Expected: PASS (5 new tests, RLS coverage ratchet green)

- [ ] **Step 7: Commit**

```bash
git add backend/auth_tenancy/models.py backend/auth_tenancy/migrations/ backend/auth_tenancy/tests/test_navigation_visibility_models.py
git commit -m "feat: add navigation-visibility tables with RLS policies"
```

---

### Task 3: `NavigationVisibilityService`

**Files:**
- Create: `backend/auth_tenancy/services/navigation_visibility.py`
- Modify: `backend/auth_tenancy/services/__init__.py`
- Modify: `backend/application/cache_invalidation.py:66-82`
- Test: `backend/auth_tenancy/tests/test_navigation_visibility_service.py`

**Interfaces:**
- Consumes: `normalize_visibility_map`, `DEFAULT_NAVIGATION_VISIBILITY`, `NavigationVisibilityError`, `GlobalNavigationVisibility`, `WorkspaceNavigationVisibility`, `application.base.ServiceBase`, `auth_tenancy.context.AuthContext`
- Produces:
  - `NavigationVisibilityService.get_or_create_global(tenant_id: UUID | str) -> GlobalNavigationVisibility`
  - `NavigationVisibilityService.replace_global(ctx: AuthContext, visibility: dict) -> tuple[GlobalNavigationVisibility, int]`
  - `NavigationVisibilityService.get_or_create_workspace(ctx: AuthContext, workspace_id: UUID | str) -> WorkspaceNavigationVisibility`
  - `NavigationVisibilityService.replace_workspace(ctx: AuthContext, workspace_id: UUID | str, visibility: dict) -> WorkspaceNavigationVisibility`
  - `NavigationVisibilityService.reset_workspace(ctx: AuthContext, workspace_id: UUID | str) -> WorkspaceNavigationVisibility`
  - `NoGlobalNavigationSourceError`
  - `application.cache_invalidation.navigation_visibility_cache_key(workspace_id: str) -> str`

- [ ] **Step 1: Write the failing test**

Create `backend/auth_tenancy/tests/test_navigation_visibility_service.py`:

```python
"""NavigationVisibilityService — seed, propagation, customization, reset."""
from __future__ import annotations

import pytest

from auth_tenancy.models import ROLE_ADMIN, WorkspaceNavigationVisibility
from auth_tenancy.navigation_catalogue import NavigationVisibilityError
from auth_tenancy.services.navigation_visibility import (
    NavigationVisibilityService,
    NoGlobalNavigationSourceError,
)

pytestmark = pytest.mark.django_db


def test_global_is_seeded_with_todays_hardcoded_state(auth_ctx) -> None:
    svc = NavigationVisibilityService()
    glob = svc.get_or_create_global(auth_ctx.tenant_id)
    assert glob.visibility_json == {"settings": "admin", "system-settings": "admin"}


def test_global_get_is_idempotent(auth_ctx) -> None:
    svc = NavigationVisibilityService()
    first = svc.get_or_create_global(auth_ctx.tenant_id)
    second = svc.get_or_create_global(auth_ctx.tenant_id)
    assert first.pk == second.pk


def test_replace_global_bumps_version_and_returns_propagation_count(
    auth_ctx, workspace
) -> None:
    svc = NavigationVisibilityService()
    svc.get_or_create_workspace(auth_ctx, workspace.id)  # on-default derived row
    before = svc.get_or_create_global(auth_ctx.tenant_id).version

    glob, propagated = svc.replace_global(auth_ctx, {"audit": ROLE_ADMIN})

    assert glob.visibility_json == {"audit": "admin"}
    assert glob.version == before + 1
    assert propagated == 1


def test_propagation_skips_customized_workspaces(auth_ctx, workspace) -> None:
    svc = NavigationVisibilityService()
    svc.replace_workspace(auth_ctx, workspace.id, {"import": "editor"})

    _, propagated = svc.replace_global(auth_ctx, {"audit": ROLE_ADMIN})

    assert propagated == 0
    row = WorkspaceNavigationVisibility.objects.get(workspace_id=workspace.id)
    assert row.visibility_json == {"import": "editor"}
    assert row.is_customized is True


def test_workspace_materializes_from_the_global_on_first_read(
    auth_ctx, workspace
) -> None:
    svc = NavigationVisibilityService()
    row = svc.get_or_create_workspace(auth_ctx, workspace.id)
    assert row.is_customized is False
    assert row.source_global_id == svc.get_or_create_global(auth_ctx.tenant_id).pk
    assert row.visibility_json == {"settings": "admin", "system-settings": "admin"}


def test_replace_workspace_marks_it_customized(auth_ctx, workspace) -> None:
    svc = NavigationVisibilityService()
    row = svc.replace_workspace(auth_ctx, workspace.id, {"metrics": "viewer"})
    assert row.is_customized is True
    assert row.visibility_json == {"metrics": "viewer"}


def test_reset_copies_the_global_back_and_clears_the_flag(auth_ctx, workspace) -> None:
    svc = NavigationVisibilityService()
    svc.replace_workspace(auth_ctx, workspace.id, {"metrics": "viewer"})

    row = svc.reset_workspace(auth_ctx, workspace.id)

    assert row.is_customized is False
    assert row.visibility_json == {"settings": "admin", "system-settings": "admin"}


def test_reset_without_a_source_global_raises(auth_ctx, workspace) -> None:
    svc = NavigationVisibilityService()
    row = svc.replace_workspace(auth_ctx, workspace.id, {"metrics": "viewer"})
    WorkspaceNavigationVisibility.objects.filter(pk=row.pk).update(source_global=None)

    with pytest.raises(NoGlobalNavigationSourceError):
        svc.reset_workspace(auth_ctx, workspace.id)


def test_invalid_map_is_rejected_before_any_write(auth_ctx, workspace) -> None:
    svc = NavigationVisibilityService()
    with pytest.raises(NavigationVisibilityError):
        svc.replace_workspace(auth_ctx, workspace.id, {"metrics": "root"})
    assert not WorkspaceNavigationVisibility.objects.filter(
        workspace_id=workspace.id
    ).exists()
```

Add the two fixtures to `backend/auth_tenancy/tests/conftest.py` (the file already builds a tenant + user; append these):

```python
@pytest.fixture
def workspace(db, tenant):
    """A workspace inside the fixture tenant."""
    from persistence.models import Workspace

    return Workspace.objects.create(tenant=tenant, name="NavVis WS", preset="standard")


@pytest.fixture
def auth_ctx(db, tenant, user):
    """Authenticated admin context with the tenant RLS session armed."""
    from auth_tenancy.context import AuthContext
    from persistence.tenancy import set_request_tenant

    set_request_tenant(str(tenant.id))
    return AuthContext(
        user_id=user.id, tenant_id=tenant.id, roles=("admin",), workspace_id=None
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -e DB_NAME=test_navvis backend-test pytest auth_tenancy/tests/test_navigation_visibility_service.py -v --create-db`
Expected: FAIL with `ModuleNotFoundError: No module named 'auth_tenancy.services.navigation_visibility'`

- [ ] **Step 3: Write the service**

Create `backend/auth_tenancy/services/navigation_visibility.py`:

```python
"""Global/Workspace navigation-visibility service (Rollenbasierte-Sichten §3.1).

Structurally identical to
:mod:`auth_tenancy.services.permission_definition`: a tenant-wide source of
truth, a materialized per-workspace copy, an ``is_customized`` divergence flag
and a reset that copies the global back in.

NOT A SECURITY BOUNDARY — see the model docstrings. This module only decides
what the sidebar draws.
"""
from __future__ import annotations

import copy
from uuid import UUID

from django.db import transaction

from application.base import ServiceBase
from auth_tenancy.context import AuthContext
from auth_tenancy.models import (
    GlobalNavigationVisibility,
    WorkspaceNavigationVisibility,
)
from auth_tenancy.navigation_catalogue import (
    DEFAULT_NAVIGATION_VISIBILITY,
    normalize_visibility_map,
)


class NoGlobalNavigationSourceError(Exception):
    """Reset requested but ``source_global`` is null (nothing to reset to)."""


class NavigationVisibilityService(ServiceBase):
    """CRUD + inheritance for the navigation-visibility system object."""

    # ---------- Global (tenant-wide singleton) ----------

    def get_or_create_global(
        self, tenant_id: UUID | str
    ) -> GlobalNavigationVisibility:
        """Return the tenant's global map, seeding the Ist-Zustand if absent."""
        obj, _created = GlobalNavigationVisibility.objects.get_or_create(
            tenant_id=tenant_id,
            defaults={
                "visibility_json": copy.deepcopy(DEFAULT_NAVIGATION_VISIBILITY)
            },
        )
        return obj

    @transaction.atomic
    def replace_global(
        self, ctx: AuthContext, visibility: dict
    ) -> tuple[GlobalNavigationVisibility, int]:
        """Full-replace the tenant default and propagate to on-default rows.

        Returns:
            ``(row, propagated_count)`` — how many non-customized workspace
            rows were updated, so the REST layer can report it.
        """
        normalized = normalize_visibility_map(visibility)
        obj = self.get_or_create_global(ctx.tenant_id)
        obj.visibility_json = normalized
        obj.version = (obj.version or 0) + 1
        obj.save(update_fields=["visibility_json", "version", "updated_at"])
        propagated = self._propagate_global(obj)
        self._audit(
            ctx,
            operation="update",
            entity_type="GlobalNavigationVisibility",
            entity_id=str(obj.id),
        )
        return obj, propagated

    def _propagate_global(self, glob: GlobalNavigationVisibility) -> int:
        """Copy *glob* into every derived row that is still on-default."""
        derived = WorkspaceNavigationVisibility.objects.filter(
            source_global=glob, is_customized=False
        )
        count = 0
        for row in derived:
            row.visibility_json = copy.deepcopy(glob.visibility_json)
            row.version = (row.version or 0) + 1
            row.save(update_fields=["visibility_json", "version", "updated_at"])
            self._invalidate(row.workspace_id)
            count += 1
        return count

    # ---------- Workspace (per-workspace materialized copy) ----------

    def get_or_create_workspace(
        self, ctx: AuthContext, workspace_id: UUID | str
    ) -> WorkspaceNavigationVisibility:
        """Return the workspace map, materializing it from the global if absent."""
        glob = self.get_or_create_global(ctx.tenant_id)
        obj, _created = WorkspaceNavigationVisibility.objects.get_or_create(
            workspace_id=workspace_id,
            defaults={
                "visibility_json": copy.deepcopy(glob.visibility_json),
                "source_global": glob,
                "is_customized": False,
            },
        )
        return obj

    @transaction.atomic
    def replace_workspace(
        self, ctx: AuthContext, workspace_id: UUID | str, visibility: dict
    ) -> WorkspaceNavigationVisibility:
        """Full-replace the workspace override and flag it as customized.

        Validation runs BEFORE the get-or-create so an invalid payload never
        leaves a half-materialized row behind.
        """
        normalized = normalize_visibility_map(visibility)
        obj = self.get_or_create_workspace(ctx, workspace_id)
        obj.visibility_json = normalized
        obj.is_customized = True
        obj.version = (obj.version or 0) + 1
        obj.save(
            update_fields=[
                "visibility_json",
                "is_customized",
                "version",
                "updated_at",
            ]
        )
        self._invalidate(workspace_id)
        self._audit(
            ctx,
            operation="update",
            entity_type="WorkspaceNavigationVisibility",
            entity_id=str(obj.id),
        )
        return obj

    @transaction.atomic
    def reset_workspace(
        self, ctx: AuthContext, workspace_id: UUID | str
    ) -> WorkspaceNavigationVisibility:
        """Copy the tenant default back in and clear ``is_customized``."""
        obj = self.get_or_create_workspace(ctx, workspace_id)
        if obj.source_global is None:
            raise NoGlobalNavigationSourceError(
                "This workspace has no global navigation-visibility source."
            )
        obj.visibility_json = copy.deepcopy(obj.source_global.visibility_json)
        obj.is_customized = False
        obj.version = (obj.version or 0) + 1
        obj.save(
            update_fields=[
                "visibility_json",
                "is_customized",
                "version",
                "updated_at",
            ]
        )
        self._invalidate(workspace_id)
        self._audit(
            ctx,
            operation="update",
            entity_type="WorkspaceNavigationVisibility",
            entity_id=str(obj.id),
        )
        return obj

    # ---------- helpers ----------

    @staticmethod
    def _invalidate(workspace_id: UUID | str) -> None:
        """Drop the cross-worker cached copy of this workspace's nav map."""
        from application.cache_invalidation import invalidate_workspace_caches

        invalidate_workspace_caches(workspace_id)


__all__ = ["NavigationVisibilityService", "NoGlobalNavigationSourceError"]
```

- [ ] **Step 4: Register the cache key**

In `backend/application/cache_invalidation.py`, add after `workflow_def_cache_key` (line 70):

```python
def navigation_visibility_cache_key(workspace_id: str) -> str:
    """Return the shared-cache key for a workspace's resolved nav visibility."""
    return f"{_KEY_PREFIX}:nav-visibility:{workspace_id}"
```

and add `navigation_visibility_cache_key(workspace_id),` as the last entry of the list returned by `_workspace_keys` (line 74-82).

- [ ] **Step 5: Export the service**

In `backend/auth_tenancy/services/__init__.py`, add alongside the existing re-exports:

```python
from .navigation_visibility import (  # noqa: F401
    NavigationVisibilityService,
    NoGlobalNavigationSourceError,
)
```

and append `"NavigationVisibilityService"` and `"NoGlobalNavigationSourceError"` to that module's `__all__`.

- [ ] **Step 6: Run test to verify it passes**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -e DB_NAME=test_navvis backend-test pytest auth_tenancy/tests/test_navigation_visibility_service.py -v --create-db`
Expected: PASS (9 passed)

- [ ] **Step 7: Commit**

```bash
git add backend/auth_tenancy/services/ backend/application/cache_invalidation.py backend/auth_tenancy/tests/
git commit -m "feat: add NavigationVisibilityService with global-to-workspace propagation"
```

---

### Task 4: Navigation-visibility REST endpoints

**Files:**
- Create: `backend/rest_api/navigation_visibility_views.py`
- Modify: `backend/rest_api/urls.py`
- Test: `backend/rest_api/tests/test_navigation_visibility_rest.py`

**Interfaces:**
- Consumes: `NavigationVisibilityService`, `NoGlobalNavigationSourceError`, `NavigationVisibilityError`, `rest_api.auth_enforcer.get_auth_context`, `rest_api.serializers.build_error_response`, `rest_api.serializers.detect_lang`
- Produces: `GlobalNavigationVisibilityView`, `WorkspaceNavigationVisibilityView`, `WorkspaceNavigationVisibilityResetView`; routes `navigation-visibility-defaults/`, `workspaces/<uuid:workspace_id>/navigation-visibility/`, `workspaces/<uuid:workspace_id>/navigation-visibility/reset/`

**Response contract:**

```json
{"scope": "global",    "tenant_id": "…", "visibility": {…}, "version": 3, "updated_at": "…", "propagated": 4}
{"scope": "workspace", "workspace_id": "…", "visibility": {…}, "is_customized": false,
 "source_global_id": "…", "version": 1, "updated_at": "…"}
```

`propagated` appears on the global `PUT` response only.

- [ ] **Step 1: Write the failing test**

Create `backend/rest_api/tests/test_navigation_visibility_rest.py`:

```python
"""REST contract for the navigation-visibility system object."""
from __future__ import annotations

import pytest
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db


def _client(token: str) -> APIClient:
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return c


def test_get_global_seeds_and_returns_the_ist_zustand(admin_token) -> None:
    resp = _client(admin_token).get("/api/v1/navigation-visibility-defaults/")
    assert resp.status_code == 200
    assert resp.data["scope"] == "global"
    assert resp.data["visibility"] == {
        "settings": "admin",
        "system-settings": "admin",
    }


def test_put_global_replaces_and_reports_propagation(admin_token, workspace) -> None:
    client = _client(admin_token)
    client.get(f"/api/v1/workspaces/{workspace.id}/navigation-visibility/")

    resp = client.put(
        "/api/v1/navigation-visibility-defaults/",
        {"visibility": {"audit": "admin"}},
        format="json",
    )

    assert resp.status_code == 200
    assert resp.data["visibility"] == {"audit": "admin"}
    assert resp.data["propagated"] == 1


def test_put_global_rejects_an_unknown_role_with_400(admin_token) -> None:
    resp = _client(admin_token).put(
        "/api/v1/navigation-visibility-defaults/",
        {"visibility": {"audit": "root"}},
        format="json",
    )
    assert resp.status_code == 400
    assert resp.data["error"]["code"] == "VALIDATION_ERROR"


def test_put_global_is_admin_only(editor_token) -> None:
    resp = _client(editor_token).put(
        "/api/v1/navigation-visibility-defaults/",
        {"visibility": {}},
        format="json",
    )
    assert resp.status_code == 403


def test_get_workspace_is_readable_by_any_authenticated_role(
    viewer_token, workspace
) -> None:
    resp = _client(viewer_token).get(
        f"/api/v1/workspaces/{workspace.id}/navigation-visibility/"
    )
    assert resp.status_code == 200
    assert resp.data["is_customized"] is False


def test_put_workspace_is_admin_only(editor_token, workspace) -> None:
    resp = _client(editor_token).put(
        f"/api/v1/workspaces/{workspace.id}/navigation-visibility/",
        {"visibility": {}},
        format="json",
    )
    assert resp.status_code == 403


def test_put_workspace_marks_customized(admin_token, workspace) -> None:
    resp = _client(admin_token).put(
        f"/api/v1/workspaces/{workspace.id}/navigation-visibility/",
        {"visibility": {"metrics": "viewer"}},
        format="json",
    )
    assert resp.status_code == 200
    assert resp.data["is_customized"] is True
    assert resp.data["visibility"] == {"metrics": "viewer"}


def test_reset_restores_the_global(admin_token, workspace) -> None:
    client = _client(admin_token)
    client.put(
        f"/api/v1/workspaces/{workspace.id}/navigation-visibility/",
        {"visibility": {"metrics": "viewer"}},
        format="json",
    )

    resp = client.post(
        f"/api/v1/workspaces/{workspace.id}/navigation-visibility/reset/", {}, format="json"
    )

    assert resp.status_code == 200
    assert resp.data["is_customized"] is False
    assert resp.data["visibility"] == {
        "settings": "admin",
        "system-settings": "admin",
    }


def test_missing_visibility_key_is_400_not_500(admin_token) -> None:
    resp = _client(admin_token).put(
        "/api/v1/navigation-visibility-defaults/", {}, format="json"
    )
    assert resp.status_code == 400
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -e DB_NAME=test_navvis backend-test pytest rest_api/tests/test_navigation_visibility_rest.py -v --create-db`
Expected: FAIL — every request returns 404 (routes not registered)

- [ ] **Step 3: Write the views**

Create `backend/rest_api/navigation_visibility_views.py`:

```python
"""REST endpoints for the navigation-visibility system object.

Rollenbasierte-Sichten spec, sections 3.1 and 6:

* ``GET/PUT  /navigation-visibility-defaults/``                      (tenant default, PUT admin-only)
* ``GET/PUT  /workspaces/{id}/navigation-visibility/``               (workspace override, PUT admin-only)
* ``POST     /workspaces/{id}/navigation-visibility/reset/``         (reset to default, admin-only)

GET is open to any authenticated role — the sidebar of every user reads it.
PUT/POST are admin-only, using the same ``ctx.has_role(ROLE_ADMIN)`` gate as
``global_default_views._require_admin``.

Holds no ORM (ADR-01 / rest_api ORM ratchet ceiling 0): every read and write
goes through ``NavigationVisibilityService``.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from auth_tenancy.models import ROLE_ADMIN
from auth_tenancy.navigation_catalogue import NavigationVisibilityError
from auth_tenancy.services.navigation_visibility import (
    NavigationVisibilityService,
    NoGlobalNavigationSourceError,
)
from rest_api.auth_enforcer import get_auth_context
from rest_api.serializers import build_error_response, detect_lang


def _require_admin(request: Request):
    """Return ``(ctx, lang)`` or a 403 Response when the caller is not admin."""
    lang = detect_lang(request)
    ctx = get_auth_context(request)
    if not ctx.has_role(ROLE_ADMIN):
        return Response(
            build_error_response(
                "PERMISSION_DENIED", lang, message="Admin role required."
            ),
            status=status.HTTP_403_FORBIDDEN,
        )
    return ctx, lang


def _validation(lang: str, message: str) -> Response:
    return Response(
        build_error_response("VALIDATION_ERROR", lang, message=message),
        status=status.HTTP_400_BAD_REQUEST,
    )


def _read_visibility(request: Request, lang: str):
    """Extract the ``visibility`` body key or return a 400 Response."""
    if not isinstance(request.data, dict) or "visibility" not in request.data:
        return _validation(lang, "Body must contain a 'visibility' object.")
    return request.data["visibility"]


def _serialize_global(obj: Any, *, propagated: int | None = None) -> dict[str, Any]:
    data: dict[str, Any] = {
        "scope": "global",
        "tenant_id": str(obj.tenant_id),
        "visibility": obj.visibility_json or {},
        "version": obj.version,
        "updated_at": obj.updated_at.isoformat() if obj.updated_at else None,
    }
    if propagated is not None:
        data["propagated"] = propagated
    return data


def _serialize_workspace(obj: Any) -> dict[str, Any]:
    return {
        "scope": "workspace",
        "workspace_id": str(obj.workspace_id),
        "visibility": obj.visibility_json or {},
        "is_customized": obj.is_customized,
        "source_global_id": (
            str(obj.source_global_id) if obj.source_global_id else None
        ),
        "version": obj.version,
        "updated_at": obj.updated_at.isoformat() if obj.updated_at else None,
    }


class GlobalNavigationVisibilityView(APIView):
    """GET/PUT /navigation-visibility-defaults/ (tenant singleton)."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._svc = NavigationVisibilityService()

    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        ctx = get_auth_context(request)
        obj = self._svc.get_or_create_global(ctx.tenant_id)
        return Response(_serialize_global(obj))

    def put(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        guard = _require_admin(request)
        if isinstance(guard, Response):
            return guard
        ctx, lang = guard

        visibility = _read_visibility(request, lang)
        if isinstance(visibility, Response):
            return visibility
        try:
            obj, propagated = self._svc.replace_global(ctx, visibility)
        except NavigationVisibilityError as exc:
            return _validation(lang, str(exc))
        return Response(_serialize_global(obj, propagated=propagated))


class WorkspaceNavigationVisibilityView(APIView):
    """GET/PUT /workspaces/{workspace_id}/navigation-visibility/."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._svc = NavigationVisibilityService()

    def get(
        self, request: Request, workspace_id: UUID, *args: Any, **kwargs: Any
    ) -> Response:
        ctx = get_auth_context(request)
        obj = self._svc.get_or_create_workspace(ctx, workspace_id)
        return Response(_serialize_workspace(obj))

    def put(
        self, request: Request, workspace_id: UUID, *args: Any, **kwargs: Any
    ) -> Response:
        guard = _require_admin(request)
        if isinstance(guard, Response):
            return guard
        ctx, lang = guard

        visibility = _read_visibility(request, lang)
        if isinstance(visibility, Response):
            return visibility
        try:
            obj = self._svc.replace_workspace(ctx, workspace_id, visibility)
        except NavigationVisibilityError as exc:
            return _validation(lang, str(exc))
        return Response(_serialize_workspace(obj))


class WorkspaceNavigationVisibilityResetView(APIView):
    """POST /workspaces/{workspace_id}/navigation-visibility/reset/."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._svc = NavigationVisibilityService()

    def post(
        self, request: Request, workspace_id: UUID, *args: Any, **kwargs: Any
    ) -> Response:
        guard = _require_admin(request)
        if isinstance(guard, Response):
            return guard
        ctx, lang = guard

        try:
            obj = self._svc.reset_workspace(ctx, workspace_id)
        except NoGlobalNavigationSourceError as exc:
            return Response(
                build_error_response("CONFLICT", lang, message=str(exc)),
                status=status.HTTP_409_CONFLICT,
            )
        return Response(_serialize_workspace(obj))


__all__ = [
    "GlobalNavigationVisibilityView",
    "WorkspaceNavigationVisibilityView",
    "WorkspaceNavigationVisibilityResetView",
]
```

- [ ] **Step 4: Register the routes**

In `backend/rest_api/urls.py`, add the import next to the other view imports:

```python
from rest_api.navigation_visibility_views import (
    GlobalNavigationVisibilityView,
    WorkspaceNavigationVisibilityResetView,
    WorkspaceNavigationVisibilityView,
)
```

and add these three entries immediately after the `workspace-permission-definition` block (line 574-577). The reset route MUST precede the detail route so it is not shadowed:

```python
    path(
        "navigation-visibility-defaults/",
        GlobalNavigationVisibilityView.as_view(),
        name="navigation-visibility-defaults",
    ),
    path(
        "workspaces/<uuid:workspace_id>/navigation-visibility/reset/",
        WorkspaceNavigationVisibilityResetView.as_view(),
        name="workspace-navigation-visibility-reset",
    ),
    path(
        "workspaces/<uuid:workspace_id>/navigation-visibility/",
        WorkspaceNavigationVisibilityView.as_view(),
        name="workspace-navigation-visibility",
    ),
```

- [ ] **Step 5: Run test to verify it passes**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -e DB_NAME=test_navvis backend-test pytest rest_api/tests/test_navigation_visibility_rest.py -v --create-db`
Expected: PASS (9 passed)

- [ ] **Step 6: Verify the ORM ratchet still holds**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -e DB_NAME=test_navvis backend-test pytest rest_api/tests/test_architecture.py -v --create-db`
Expected: PASS — `navigation_visibility_views.py` contributes 0 direct-ORM lines

- [ ] **Step 7: Commit**

```bash
git add backend/rest_api/navigation_visibility_views.py backend/rest_api/urls.py backend/rest_api/tests/test_navigation_visibility_rest.py
git commit -m "feat: expose navigation-visibility defaults and workspace overrides over REST"
```

---

## Phase B — Backend: the expert-mode user preference

### Task 5: `User.expert_mode_enabled` end to end

**Files:**
- Modify: `backend/persistence/models.py:501` (after `is_active`)
- Create: `backend/persistence/migrations/0070_user_expert_mode_enabled.py`
- Modify: `backend/auth_tenancy/services/profile_service.py:24,52-58`
- Modify: `backend/rest_api/serializers.py:1929,1959,1994-2005`
- Modify: `backend/rest_api/auth_views.py:154-165`
- Test: `backend/auth_tenancy/tests/test_expert_mode_preference.py`

**Interfaces:**
- Consumes: `UserProfileService.update_profile(ctx, validated_data)`, `UserProfileSerializer`
- Produces: `User.expert_mode_enabled: bool`; `PATCH /api/v1/auth/me/ {"expert_mode_enabled": bool}`; `expert_mode_enabled` in the `user` object of both `GET /auth/me/` and `POST /auth/login/`

**Why `PATCH /auth/me/` and not a new `users/me/` route:** the spec says "`PATCH users/me/` (oder äquivalenter bestehender Profil-Endpoint)". `PATCH /api/v1/auth/me/` already exists (`auth_views.MeView.patch`, `UserProfileSerializer`, `UserProfileService.update_profile`) and is the caller's own profile write path. Adding a second endpoint for one boolean would be a parallel mechanism.

- [ ] **Step 1: Write the failing test**

Create `backend/auth_tenancy/tests/test_expert_mode_preference.py`:

```python
"""expert_mode_enabled — persisted as a real boolean, exposed on the identity."""
from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from auth_tenancy.services.profile_service import UserProfileService
from persistence.models import User

pytestmark = pytest.mark.django_db


def test_field_defaults_to_false(user) -> None:
    assert User.objects.get(pk=user.pk).expert_mode_enabled is False


def test_service_persists_a_real_boolean_not_a_string(auth_ctx, user) -> None:
    UserProfileService().update_profile(auth_ctx, {"expert_mode_enabled": True})
    refreshed = User.objects.get(pk=user.pk)
    assert refreshed.expert_mode_enabled is True


def test_service_can_switch_it_back_off(auth_ctx, user) -> None:
    svc = UserProfileService()
    svc.update_profile(auth_ctx, {"expert_mode_enabled": True})
    svc.update_profile(auth_ctx, {"expert_mode_enabled": False})
    assert User.objects.get(pk=user.pk).expert_mode_enabled is False


def test_service_leaves_names_untouched_when_only_the_flag_is_sent(
    auth_ctx, user
) -> None:
    user.first_name = "Ada"
    user.save(update_fields=["first_name"])
    UserProfileService().update_profile(auth_ctx, {"expert_mode_enabled": True})
    assert User.objects.get(pk=user.pk).first_name == "Ada"


def test_patch_auth_me_accepts_the_flag(admin_token) -> None:
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {admin_token}")

    resp = client.patch(
        "/api/v1/auth/me/", {"expert_mode_enabled": True}, format="json"
    )

    assert resp.status_code == 200
    assert resp.data["user"]["expert_mode_enabled"] is True


def test_get_auth_me_exposes_the_flag(admin_token) -> None:
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {admin_token}")
    resp = client.get("/api/v1/auth/me/")
    assert resp.status_code == 200
    assert resp.data["user"]["expert_mode_enabled"] is False


def test_patch_auth_me_still_rejects_protected_fields(admin_token) -> None:
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {admin_token}")
    resp = client.patch("/api/v1/auth/me/", {"roles": ["admin"]}, format="json")
    assert resp.status_code == 400


def test_patch_auth_me_rejects_a_non_boolean(admin_token) -> None:
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {admin_token}")
    resp = client.patch(
        "/api/v1/auth/me/", {"expert_mode_enabled": "yes please"}, format="json"
    )
    assert resp.status_code == 400
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -e DB_NAME=test_expertmode backend-test pytest auth_tenancy/tests/test_expert_mode_preference.py -v --create-db`
Expected: FAIL with `AttributeError: 'User' object has no attribute 'expert_mode_enabled'`

- [ ] **Step 3: Add the model field**

In `backend/persistence/models.py`, insert directly after `is_active` (line 501):

```python
    # Rollenbasierte-Sichten spec, section 5: a pure UI DENSITY preference, not
    # a permission. It only decides whether `audience="expert"` form sections
    # start expanded; it grants nothing. The toggle that writes it is rendered
    # for `admin`/`approver` only, but the column carries no authority of its
    # own — a viewer with the flag set still cannot edit anything.
    expert_mode_enabled = models.BooleanField(default=False)
```

- [ ] **Step 4: Generate the migration**

Run: `docker-compose -f deploy/docker-compose.yml -f deploy/docker-compose.override.yml --project-directory . exec backend python manage.py makemigrations persistence --name user_expert_mode_enabled`
Expected: `Migrations for 'persistence': 0070_user_expert_mode_enabled.py — Add field expert_mode_enabled to user`

- [ ] **Step 5: Teach the profile service to write booleans**

In `backend/auth_tenancy/services/profile_service.py`, replace line 24 with:

```python
# Text fields a user may edit on their own profile (trimmed on write).
_EDITABLE_PROFILE_FIELDS = ("first_name", "last_name")

# Boolean preference fields. Kept separate because the text branch below
# stringifies its value — `str(True).strip()` would persist "True" into a
# BooleanField (plan precondition P5).
_EDITABLE_BOOLEAN_PROFILE_FIELDS = ("expert_mode_enabled",)
```

and insert into `update_profile`, directly after the existing text loop (line 56, before `if updated_fields:`):

```python
        for field in _EDITABLE_BOOLEAN_PROFILE_FIELDS:
            if field in validated_data:
                setattr(user, field, bool(validated_data[field]))
                updated_fields.append(field)
```

- [ ] **Step 6: Open the serializer**

In `backend/rest_api/serializers.py`:

1. line 1929 — `WRITABLE_FIELDS = ("first_name", "last_name", "expert_mode_enabled")`
2. after the `is_active` declaration (line 1959) add:

```python
    # Rollenbasierte-Sichten spec section 5 — UI density preference. Declared
    # as a real BooleanField so a non-boolean payload is a 400, not a silent
    # truthiness coercion.
    expert_mode_enabled = serializers.BooleanField(required=False)
```

3. in `update()` (line 1994-2005) change the loop tuple to cover both kinds:

```python
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

- [ ] **Step 7: Expose it on the identity payload**

In `backend/rest_api/auth_views.py`, add one entry to `_user_payload` (line 156-165), after `"is_active"`:

```python
        # Rollenbasierte-Sichten section 5: the SPA needs the preference at
        # login time so ArtifactForm can decide the initial expand density
        # without a second round trip.
        "expert_mode_enabled": bool(getattr(user, "expert_mode_enabled", False)),
```

- [ ] **Step 8: Run test to verify it passes**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -e DB_NAME=test_expertmode backend-test pytest auth_tenancy/tests/test_expert_mode_preference.py auth_tenancy/tests/test_profile_service.py rest_api/tests/test_auth.py -v --create-db`
Expected: PASS (8 new tests, existing profile/auth tests unchanged)

- [ ] **Step 9: Commit**

```bash
git add backend/persistence/models.py backend/persistence/migrations/0070_user_expert_mode_enabled.py backend/auth_tenancy/services/profile_service.py backend/rest_api/serializers.py backend/rest_api/auth_views.py backend/auth_tenancy/tests/test_expert_mode_preference.py
git commit -m "feat: persist the expert-mode UI density preference on the user profile"
```

---

## Phase C — Frontend: runtime-configurable navigation

### Task 6: Navigation-visibility API wrapper

**Files:**
- Create: `frontend/src/api/navigation-visibility.ts`
- Modify: `frontend/src/api/index.ts`
- Test: `frontend/src/api/navigation-visibility.test.ts`

**Interfaces:**
- Consumes: `apiClient` from `frontend/src/api/client.ts`
- Produces: `NavigationRole`, `NavigationVisibilityMap`, `GlobalNavigationVisibility`, `WorkspaceNavigationVisibility`, `navigationVisibilityApi`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/api/navigation-visibility.test.ts`:

```ts
import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("./client", () => ({
  apiClient: {
    get: vi.fn(),
    put: vi.fn(),
    post: vi.fn(),
  },
}));

import { apiClient } from "./client";
import { navigationVisibilityApi } from "./navigation-visibility";

beforeEach(() => {
  vi.mocked(apiClient.get).mockReset();
  vi.mocked(apiClient.put).mockReset();
  vi.mocked(apiClient.post).mockReset();
});

describe("navigationVisibilityApi", () => {
  it("reads the tenant default", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ scope: "global" });
    await navigationVisibilityApi.getGlobal();
    expect(apiClient.get).toHaveBeenCalledWith("/navigation-visibility-defaults/");
  });

  it("wraps the map in a visibility key on the global PUT", async () => {
    vi.mocked(apiClient.put).mockResolvedValue({ scope: "global" });
    await navigationVisibilityApi.replaceGlobal({ settings: "admin" });
    expect(apiClient.put).toHaveBeenCalledWith(
      "/navigation-visibility-defaults/",
      { visibility: { settings: "admin" } }
    );
  });

  it("reads the workspace override", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ scope: "workspace" });
    await navigationVisibilityApi.getWorkspace("ws-1");
    expect(apiClient.get).toHaveBeenCalledWith(
      "/workspaces/ws-1/navigation-visibility/"
    );
  });

  it("wraps the map in a visibility key on the workspace PUT", async () => {
    vi.mocked(apiClient.put).mockResolvedValue({ scope: "workspace" });
    await navigationVisibilityApi.replaceWorkspace("ws-1", { audit: null });
    expect(apiClient.put).toHaveBeenCalledWith(
      "/workspaces/ws-1/navigation-visibility/",
      { visibility: { audit: null } }
    );
  });

  it("posts an empty body to reset", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({ scope: "workspace" });
    await navigationVisibilityApi.resetWorkspace("ws-1");
    expect(apiClient.post).toHaveBeenCalledWith(
      "/workspaces/ws-1/navigation-visibility/reset/",
      {}
    );
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm frontend-test sh -c "npm install && npx vitest run src/api/navigation-visibility.test.ts --testTimeout=30000"`
Expected: FAIL with `Failed to resolve import "./navigation-visibility"`

- [ ] **Step 3: Write the wrapper**

Create `frontend/src/api/navigation-visibility.ts`:

```ts
/**
 * ARCH-L1-001 ReactFrontend — Navigation-visibility system object.
 *
 * Rollenbasierte-Sichten spec, sections 3.1 and 6. Which role may see which
 * nav entry is data (tenant default + optional per-workspace override); which
 * pages exist stays code (see `NavigationShell/nav-items.ts`).
 *
 * NOT A SECURITY BOUNDARY — hiding a nav entry does not block the route. The
 * server-side RBAC check on the route/API remains the enforcement.
 */

import { apiClient } from "./client";
import type { UUID } from "../types";

/** Role a nav entry may require. `null` means "no role required". */
export type NavigationRole = "admin" | "editor" | "approver" | "viewer";

/** `{nav_item_key: required_role | null}`. A missing key requires no role. */
export type NavigationVisibilityMap = Record<string, NavigationRole | null>;

export interface GlobalNavigationVisibility {
  scope: "global";
  tenant_id: string;
  visibility: NavigationVisibilityMap;
  version: number;
  updated_at: string | null;
  /** Only present on the PUT response: derived rows updated by propagation. */
  propagated?: number;
}

export interface WorkspaceNavigationVisibility {
  scope: "workspace";
  workspace_id: string;
  visibility: NavigationVisibilityMap;
  is_customized: boolean;
  source_global_id: string | null;
  version: number;
  updated_at: string | null;
}

export const navigationVisibilityApi = {
  /** GET /api/v1/navigation-visibility-defaults/ */
  getGlobal(): Promise<GlobalNavigationVisibility> {
    return apiClient.get<GlobalNavigationVisibility>(
      "/navigation-visibility-defaults/"
    );
  },

  /** PUT /api/v1/navigation-visibility-defaults/ — full replace (admin only). */
  replaceGlobal(
    visibility: NavigationVisibilityMap
  ): Promise<GlobalNavigationVisibility> {
    return apiClient.put<GlobalNavigationVisibility>(
      "/navigation-visibility-defaults/",
      { visibility }
    );
  },

  /** GET /api/v1/workspaces/{id}/navigation-visibility/ — the resolved map. */
  getWorkspace(workspaceId: UUID): Promise<WorkspaceNavigationVisibility> {
    return apiClient.get<WorkspaceNavigationVisibility>(
      `/workspaces/${workspaceId}/navigation-visibility/`
    );
  },

  /** PUT /api/v1/workspaces/{id}/navigation-visibility/ (admin only). */
  replaceWorkspace(
    workspaceId: UUID,
    visibility: NavigationVisibilityMap
  ): Promise<WorkspaceNavigationVisibility> {
    return apiClient.put<WorkspaceNavigationVisibility>(
      `/workspaces/${workspaceId}/navigation-visibility/`,
      { visibility }
    );
  },

  /** POST /api/v1/workspaces/{id}/navigation-visibility/reset/ (admin only). */
  resetWorkspace(workspaceId: UUID): Promise<WorkspaceNavigationVisibility> {
    return apiClient.post<WorkspaceNavigationVisibility>(
      `/workspaces/${workspaceId}/navigation-visibility/reset/`,
      {}
    );
  },
};
```

- [ ] **Step 4: Re-export it**

In `frontend/src/api/index.ts`, add alongside the other named exports:

```ts
export { navigationVisibilityApi } from "./navigation-visibility";
export type {
  NavigationRole,
  NavigationVisibilityMap,
  GlobalNavigationVisibility,
  WorkspaceNavigationVisibility,
} from "./navigation-visibility";
```

- [ ] **Step 5: Run test to verify it passes**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm frontend-test sh -c "npm install && npx vitest run src/api/navigation-visibility.test.ts --testTimeout=30000"`
Expected: PASS (5 passed)

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api/navigation-visibility.ts frontend/src/api/navigation-visibility.test.ts frontend/src/api/index.ts
git commit -m "feat: add navigation-visibility API wrapper"
```

---

### Task 7: Nav-item catalogue, widened role gate, resolved-visibility hook

**Files:**
- Modify: `frontend/src/hooks/useHasRole.ts:18`
- Create: `frontend/src/components/NavigationShell/nav-items.ts`
- Create: `frontend/src/hooks/useNavigationVisibility.ts`
- Test: `frontend/src/test/useNavigationVisibility.test.tsx`

**Interfaces:**
- Consumes: `navigationVisibilityApi.getWorkspace`, `useWorkspace()`, `NavigationVisibilityMap`
- Produces:
  - `RequiredRole = "admin" | "editor" | "approver" | "viewer"`
  - `NavGroupId`, `NAV_GROUP_ORDER`, `NAV_GROUP_LABEL_KEYS`, `NavItem` (with the new `key: string`), `NAV_ITEMS`
  - `FALLBACK_NAVIGATION_VISIBILITY: NavigationVisibilityMap`
  - `useNavigationVisibility(): { visibility: NavigationVisibilityMap; isLoading: boolean }`

**Why `key` and not the path:** deriving `"dashboard"` from `"/"` needs a special case, and any later route rename would silently orphan the stored map entry. An explicit, never-renamed `key` decouples the stored data from the route string.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/test/useNavigationVisibility.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";

vi.mock("../api/navigation-visibility", () => ({
  navigationVisibilityApi: { getWorkspace: vi.fn() },
}));

const activeWorkspace: { id: string } | null = { id: "ws-1" };
vi.mock("../context/WorkspaceContext", () => ({
  useWorkspace: () => ({ activeWorkspace }),
}));

import { navigationVisibilityApi } from "../api/navigation-visibility";
import {
  FALLBACK_NAVIGATION_VISIBILITY,
  useNavigationVisibility,
} from "../hooks/useNavigationVisibility";
import { NAV_ITEMS } from "../components/NavigationShell/nav-items";

beforeEach(() => {
  vi.mocked(navigationVisibilityApi.getWorkspace).mockReset();
});

describe("nav-item catalogue", () => {
  it("gives every entry a unique, well-formed key", () => {
    const keys = NAV_ITEMS.map((i) => i.key);
    expect(new Set(keys).size).toBe(keys.length);
    for (const key of keys) expect(key).toMatch(/^[a-z0-9][a-z0-9-]{0,63}$/);
  });

  it("maps the dashboard root path to a named key", () => {
    expect(NAV_ITEMS.find((i) => i.path === "/")?.key).toBe("dashboard");
  });

  it("no longer carries a hardcoded requires field", () => {
    expect(NAV_ITEMS.every((i) => !("requires" in i))).toBe(true);
  });
});

describe("useNavigationVisibility", () => {
  it("returns the resolved workspace map", async () => {
    vi.mocked(navigationVisibilityApi.getWorkspace).mockResolvedValue({
      scope: "workspace",
      workspace_id: "ws-1",
      visibility: { audit: "admin" },
      is_customized: true,
      source_global_id: null,
      version: 2,
      updated_at: null,
    });

    const { result } = renderHook(() => useNavigationVisibility());

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.visibility).toEqual({ audit: "admin" });
  });

  it("falls back to today's hardcoded state when the request fails", async () => {
    vi.mocked(navigationVisibilityApi.getWorkspace).mockRejectedValue(
      new Error("offline")
    );

    const { result } = renderHook(() => useNavigationVisibility());

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.visibility).toEqual(FALLBACK_NAVIGATION_VISIBILITY);
  });

  it("keeps the two admin-only entries in the fallback", () => {
    expect(FALLBACK_NAVIGATION_VISIBILITY).toEqual({
      settings: "admin",
      "system-settings": "admin",
    });
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm frontend-test sh -c "npm install && npx vitest run src/test/useNavigationVisibility.test.tsx --testTimeout=30000"`
Expected: FAIL with `Failed to resolve import "../components/NavigationShell/nav-items"`

- [ ] **Step 3: Widen the role gate**

In `frontend/src/hooks/useHasRole.ts`, replace line 18:

```ts
/**
 * Every workspace role in `auth_tenancy.models.ROLE_CHOICES`. `approver` and
 * `viewer` were added for the Rollenbasierte-Sichten spec: the expert-mode
 * toggle is `admin`/`approver`-only, and a nav entry may be configured to
 * require any of the four roles at runtime.
 */
export type RequiredRole = 'admin' | 'editor' | 'approver' | 'viewer';
```

The implementation body (line 22-23) is unchanged — `roles.includes(required) || roles.includes('admin')` already handles the two new values, with `admin` staying a superset.

- [ ] **Step 4: Extract the catalogue**

Create `frontend/src/components/NavigationShell/nav-items.ts` and move `NavGroupId`, `NAV_GROUP_ORDER`, `NAV_GROUP_LABEL_KEYS`, `NavItem` and `NAV_ITEMS` verbatim out of `SidebarNavigation.tsx:38-134`, with two changes: `NavItem` loses `requires` and gains `key`.

```ts
/**
 * ARCH-L1-001 ReactFrontend — the nav-item catalogue.
 *
 * Extracted from SidebarNavigation.tsx so the NavigationVisibilityEditor can
 * render one row per entry without importing the sidebar component itself.
 *
 * Rollenbasierte-Sichten spec, section 3.1: WHICH pages exist is code (this
 * array); WHICH ROLE may see a page is data (`WorkspaceNavigationVisibility`,
 * keyed by `NavItem.key`). `requires` therefore no longer lives here — the
 * two hardcoded values it used to carry are now the server-side seed
 * `DEFAULT_NAVIGATION_VISIBILITY`.
 *
 * `key` is a stable identifier that must never be renamed: it is the primary
 * key of the stored visibility map. Renaming a route is safe; renaming a key
 * orphans the stored entry.
 */

// Nav-group ids (issue #317) — logical sections shown as headers above the
// flat item list. Order here defines render order.
export type NavGroupId =
  | "overview"
  | "requirements"
  | "architecture"
  | "test"
  | "admin";

export const NAV_GROUP_ORDER: NavGroupId[] = [
  "overview",
  "requirements",
  "architecture",
  "test",
  "admin",
];

export const NAV_GROUP_LABEL_KEYS: Record<NavGroupId, string> = {
  overview: "nav.groupOverview",
  requirements: "nav.groupRequirements",
  architecture: "nav.groupArchitecture",
  test: "nav.groupTest",
  admin: "nav.groupAdmin",
};

export interface NavItem {
  /** Stable visibility-map key. Never rename. */
  key: string;
  path: string;
  labelKey: string;
  /** key in PRESET_VISIBILITY */
  feature: string;
  /** issue #317 — section grouping */
  group: NavGroupId;
}

export const NAV_ITEMS: NavItem[] = [
  { key: "dashboard", path: "/", labelKey: "nav.dashboard", feature: "dashboard", group: "overview" },
  // REQ-L2-TE-020: visibility additionally depends on the workspace's own
  // `goals_enabled` toggle — applied in SidebarNavigation's `visibleItems`.
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
  // REQ-144: reuses the `approver_ui` preset-visibility flag (extended only).
  { key: "reviews", path: "/reviews", labelKey: "nav.reviews", feature: "approver_ui", group: "test" },

  { key: "import", path: "/import", labelKey: "nav.import", feature: "csv_import", group: "admin" },
  { key: "workflows", path: "/workflows", labelKey: "nav.workflows", feature: "dashboard", group: "admin" },
  { key: "audit", path: "/audit", labelKey: "nav.audit", feature: "dashboard", group: "admin" },
  // Seeded to `admin` in DEFAULT_NAVIGATION_VISIBILITY — the page itself also
  // blocks non-admins (`isAdmin` early-return in WorkspaceSettings).
  { key: "settings", path: "/settings", labelKey: "nav.settings", feature: "dashboard", group: "admin" },
  // REQ-184: likewise seeded to `admin`.
  { key: "system-settings", path: "/system-settings", labelKey: "nav.systemSettings", feature: "dashboard", group: "admin" },
  // Tenant-admin is a tenant-wide concept the workspace `roles` array cannot
  // express, so this entry is deliberately NOT part of the visibility map —
  // it keeps its dedicated `isTenantAdmin` filter in SidebarNavigation.
  { key: "user-management", path: "/user-management", labelKey: "nav.userManagement", feature: "dashboard", group: "admin" },
];
```

- [ ] **Step 5: Write the hook**

Create `frontend/src/hooks/useNavigationVisibility.ts`:

```ts
/**
 * Resolved navigation visibility for the active workspace.
 *
 * Rollenbasierte-Sichten spec, section 3.1. The sidebar reads this map at
 * render time instead of the hardcoded `NavItem.requires` field it used until
 * commit 54b09760.
 *
 * Failure policy: fall back to `FALLBACK_NAVIGATION_VISIBILITY`, which is the
 * exact pre-spec hardcoded state. Failing OPEN (empty map) would flash
 * `/settings` and `/system-settings` in front of a viewer on any network blip;
 * failing CLOSED (hide everything) would strand every user on a blank sidebar.
 * Reproducing the old constant is the only option that degrades to something
 * a user has already seen working.
 */

import { useEffect, useState } from "react";

import {
  navigationVisibilityApi,
  type NavigationVisibilityMap,
} from "../api/navigation-visibility";
import { useWorkspace } from "../context/WorkspaceContext";

/** The pre-spec hardcoded state, used when the request cannot be made. */
export const FALLBACK_NAVIGATION_VISIBILITY: NavigationVisibilityMap = {
  settings: "admin",
  "system-settings": "admin",
};

export function useNavigationVisibility(): {
  visibility: NavigationVisibilityMap;
  isLoading: boolean;
} {
  const { activeWorkspace } = useWorkspace();
  const [visibility, setVisibility] = useState<NavigationVisibilityMap>(
    FALLBACK_NAVIGATION_VISIBILITY
  );
  const [isLoading, setIsLoading] = useState<boolean>(true);

  useEffect(() => {
    if (!activeWorkspace) {
      setVisibility(FALLBACK_NAVIGATION_VISIBILITY);
      setIsLoading(false);
      return;
    }
    let cancelled = false;
    setIsLoading(true);
    void navigationVisibilityApi
      .getWorkspace(activeWorkspace.id)
      .then((resolved) => {
        if (!cancelled) setVisibility(resolved.visibility ?? {});
      })
      .catch(() => {
        if (!cancelled) setVisibility(FALLBACK_NAVIGATION_VISIBILITY);
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [activeWorkspace]);

  return { visibility, isLoading };
}
```

- [ ] **Step 6: Run test to verify it passes**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm frontend-test sh -c "npm install && npx vitest run src/test/useNavigationVisibility.test.tsx --testTimeout=30000"`
Expected: PASS (6 passed)

- [ ] **Step 7: Commit**

```bash
git add frontend/src/hooks/useHasRole.ts frontend/src/hooks/useNavigationVisibility.ts frontend/src/components/NavigationShell/nav-items.ts frontend/src/test/useNavigationVisibility.test.tsx
git commit -m "feat: extract nav catalogue and resolve visibility from the workspace map"
```

---

### Task 8: `SidebarNavigation` renders from the resolved map

**Files:**
- Modify: `frontend/src/components/NavigationShell/SidebarNavigation.tsx:31-134` (delete the moved block), `:408-419` (the filter chain)
- Test: `frontend/src/test/NavigationVisibility.test.tsx`

**Interfaces:**
- Consumes: `NAV_ITEMS`, `NAV_GROUP_ORDER`, `NAV_GROUP_LABEL_KEYS`, `NavGroupId`, `NavItem`, `useNavigationVisibility`, `useHasRole`
- Produces: no new export — behaviour change only

- [ ] **Step 1: Write the failing test**

Create `frontend/src/test/NavigationVisibility.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

const roles: string[] = [];
vi.mock("../context/AuthContext", () => ({
  useAuth: () => ({
    roles,
    isTenantAdmin: false,
    logout: vi.fn(),
    expertModeEnabled: false,
    setExpertMode: vi.fn(),
  }),
}));

const visibility: Record<string, string | null> = {};
vi.mock("../hooks/useNavigationVisibility", () => ({
  FALLBACK_NAVIGATION_VISIBILITY: { settings: "admin", "system-settings": "admin" },
  useNavigationVisibility: () => ({ visibility, isLoading: false }),
}));

vi.mock("../context/WorkspaceContext", () => ({
  DEFAULT_WORKSPACE: { id: "default" },
  useWorkspace: () => ({
    isFeatureVisible: () => true,
    activeWorkspace: { id: "ws-1", name: "WS", preset: "standard", goals_enabled: true },
    workspaces: [],
    isLoadingWorkspace: false,
    setActiveWorkspace: vi.fn(),
    terminologyLabel: () => "Requirement",
    reloadWorkspaces: vi.fn(),
    hideAllOptional: false,
    setHideAllOptional: vi.fn(),
    markLanguageOverrideActive: vi.fn(),
    clearLanguageOverride: vi.fn(),
  }),
}));

vi.mock("../context/ThemeContext", () => ({
  useTheme: () => ({ mode: "light", paletteKey: "default", setPreference: vi.fn() }),
}));

vi.mock("../api/search", () => ({
  searchApi: { search: vi.fn(async () => ({ results: [] })) },
}));
vi.mock("../api/version", () => ({
  versionApi: { getVersion: vi.fn(async () => ({ app_version: "0", commit_short: "a" })) },
}));
vi.mock("../api/workspaces", () => ({
  workspacesApi: { listAll: vi.fn(async () => []), update: vi.fn() },
}));

import { SidebarNavigation } from "../components/NavigationShell/SidebarNavigation";

function setState(nextRoles: string[], nextVisibility: Record<string, string | null>): void {
  roles.length = 0;
  roles.push(...nextRoles);
  for (const key of Object.keys(visibility)) delete visibility[key];
  Object.assign(visibility, nextVisibility);
}

function renderSidebar(): void {
  render(
    <MemoryRouter>
      <SidebarNavigation />
    </MemoryRouter>
  );
}

beforeEach(() => setState([], {}));

describe("SidebarNavigation visibility", () => {
  it("hides an entry whose configured role the user lacks", async () => {
    setState(["viewer"], { settings: "admin" });
    renderSidebar();
    await waitFor(() => expect(screen.getByTestId("nav-group-overview")).toBeTruthy());
    expect(screen.queryByText("nav.settings")).toBeNull();
  });

  it("shows an entry that requires no role", async () => {
    setState(["viewer"], {});
    renderSidebar();
    await waitFor(() => expect(screen.getByText("nav.settings")).toBeTruthy());
  });

  it("treats admin as a superset of an editor-gated entry", async () => {
    setState(["admin"], { import: "editor" });
    renderSidebar();
    await waitFor(() => expect(screen.getByText("nav.import")).toBeTruthy());
  });

  it("hides an entry newly gated at runtime without a deploy", async () => {
    setState(["editor"], { audit: "admin" });
    renderSidebar();
    await waitFor(() => expect(screen.getByTestId("nav-group-admin")).toBeTruthy());
    expect(screen.queryByText("nav.audit")).toBeNull();
  });

  it("ignores a map key that is not in the catalogue", async () => {
    setState(["viewer"], { "route-that-was-deleted": "admin" });
    renderSidebar();
    await waitFor(() => expect(screen.getByText("nav.dashboard")).toBeTruthy());
  });

  it("keeps /user-management on its tenant-admin gate, not the map", async () => {
    setState(["viewer"], { "user-management": null });
    renderSidebar();
    await waitFor(() => expect(screen.getByText("nav.dashboard")).toBeTruthy());
    expect(screen.queryByText("nav.userManagement")).toBeNull();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm frontend-test sh -c "npm install && npx vitest run src/test/NavigationVisibility.test.tsx --testTimeout=30000"`
Expected: FAIL — "hides an entry newly gated at runtime" fails because `SidebarNavigation` still reads the deleted `item.requires`

- [ ] **Step 3: Replace the inline catalogue with the import**

In `frontend/src/components/NavigationShell/SidebarNavigation.tsx`, delete lines 31-134 (the whole `// Navigation items` block through the closing `];` of `NAV_ITEMS`) and add to the import block:

```tsx
import { useNavigationVisibility } from "../../hooks/useNavigationVisibility";
import {
  NAV_GROUP_LABEL_KEYS,
  NAV_GROUP_ORDER,
  NAV_ITEMS,
  type NavGroupId,
  type NavItem,
} from "./nav-items";
```

- [ ] **Step 4: Resolve `requires` from the map**

Replace the filter chain at lines 408-419 with:

```tsx
  // Rollenbasierte-Sichten spec section 3.1: the role a nav entry requires is
  // DATA now (WorkspaceNavigationVisibility), not a hardcoded `requires`
  // field. A key that is absent from the map requires no role — byte-identical
  // to the previous `hasRole(undefined) === true`. An entry the role may not
  // see is NOT RENDERED (never CSS-hidden, never disabled).
  //
  // UX only: the server-side RBAC check on the route/API is the enforcement.
  const visibleItems = NAV_ITEMS.filter((item) => isFeatureVisible(item.feature))
    .filter((item) => item.path !== "/goals" || !!activeWorkspace?.goals_enabled)
    .filter((item) =>
      hasRole(navigationVisibility[item.key] ?? undefined)
    )
    // /user-management gates on tenant-admin, a tenant-wide concept the
    // workspace `roles` array (and therefore the visibility map) cannot
    // express — it keeps its own OR. See nav-items.ts.
    .filter(
      (item) => item.path !== "/user-management" || isAdmin || isTenantAdmin
    );
```

and add, next to the existing `const hasRole = useHasRole();` (line 157):

```tsx
  const { visibility: navigationVisibility } = useNavigationVisibility();
```

`navigationVisibility[item.key]` is typed `NavigationRole | null | undefined`; `?? undefined` converts the "no role required" `null` into the `undefined` that `hasRole` already treats as "always visible", so no cast is needed.

- [ ] **Step 5: Run test to verify it passes**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm frontend-test sh -c "npm install && npx vitest run src/test/NavigationVisibility.test.tsx src/test/SidebarNavigation.test.tsx --testTimeout=30000"`
Expected: PASS — 6 new tests plus the pre-existing `SidebarNavigation.test.tsx` suite still green

- [ ] **Step 6: Verify the sidebar in the browser**

Run: `docker-compose -f deploy/docker-compose.yml -f deploy/docker-compose.override.yml --project-directory . restart frontend`
Then open `http://localhost:5173`, log in as the seeded admin, confirm all 25 entries render; log in as a viewer and confirm "Einstellungen" / "Systemeinstellungen" / "Benutzerverwaltung" are absent from the DOM (not merely greyed out). Vite has no working HMR on Windows — the restart above is mandatory or the browser serves stale code.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/NavigationShell/SidebarNavigation.tsx frontend/src/test/NavigationVisibility.test.tsx
git commit -m "feat: render sidebar entries from the resolved navigation-visibility map"
```

---

### Task 9: `NavigationVisibilityEditor` in both settings shells

**Files:**
- Create: `frontend/src/components/NavigationVisibilityEditor/NavigationVisibilityEditor.tsx`
- Create: `frontend/src/components/NavigationVisibilityEditor/NavigationVisibilityEditor.module.css`
- Create: `frontend/src/components/NavigationVisibilityEditor/index.ts`
- Modify: `frontend/src/components/SystemSettings/SystemSettings.tsx:33-41,75-79,150-175`
- Modify: `frontend/src/components/WorkspaceSettings/WorkspaceSettings.tsx:77-93,309-316,731+`
- Modify: `frontend/src/i18n/locales/de.json`, `frontend/src/i18n/locales/en.json`
- Test: `frontend/src/components/NavigationVisibilityEditor/NavigationVisibilityEditor.test.tsx`

**Interfaces:**
- Consumes: `navigationVisibilityApi`, `NAV_ITEMS`, `NAV_GROUP_ORDER`, `NAV_GROUP_LABEL_KEYS`, `NavigationVisibilityMap`, `NavigationRole`, `useToast`
- Produces: `NavigationVisibilityEditor({ scope, workspaceId }: NavigationVisibilityEditorProps): JSX.Element`

**Why one `scope`-parameterized component and not two pages:** the Workflow Editor already proved this shape (`WorkflowEditorPage` with a `scope` prop, REQ-178..187). Two near-identical pages would drift.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/NavigationVisibilityEditor/NavigationVisibilityEditor.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

vi.mock("../../api/navigation-visibility", () => ({
  navigationVisibilityApi: {
    getGlobal: vi.fn(),
    replaceGlobal: vi.fn(),
    getWorkspace: vi.fn(),
    replaceWorkspace: vi.fn(),
    resetWorkspace: vi.fn(),
  },
}));

vi.mock("../shared/Toast/useToast", () => ({
  useToast: () => ({ show: vi.fn(), clear: vi.fn(), message: null }),
}));

import { navigationVisibilityApi } from "../../api/navigation-visibility";
import { NAV_ITEMS } from "../NavigationShell/nav-items";
import { NavigationVisibilityEditor } from "./NavigationVisibilityEditor";

beforeEach(() => {
  vi.mocked(navigationVisibilityApi.getGlobal).mockResolvedValue({
    scope: "global",
    tenant_id: "t-1",
    visibility: { settings: "admin" },
    version: 1,
    updated_at: null,
  });
  vi.mocked(navigationVisibilityApi.replaceGlobal).mockResolvedValue({
    scope: "global",
    tenant_id: "t-1",
    visibility: {},
    version: 2,
    updated_at: null,
    propagated: 0,
  });
  vi.mocked(navigationVisibilityApi.getWorkspace).mockResolvedValue({
    scope: "workspace",
    workspace_id: "ws-1",
    visibility: {},
    is_customized: false,
    source_global_id: "g-1",
    version: 1,
    updated_at: null,
  });
  vi.mocked(navigationVisibilityApi.replaceWorkspace).mockResolvedValue({
    scope: "workspace",
    workspace_id: "ws-1",
    visibility: { audit: "admin" },
    is_customized: true,
    source_global_id: "g-1",
    version: 2,
    updated_at: null,
  });
  vi.mocked(navigationVisibilityApi.resetWorkspace).mockResolvedValue({
    scope: "workspace",
    workspace_id: "ws-1",
    visibility: { settings: "admin" },
    is_customized: false,
    source_global_id: "g-1",
    version: 3,
    updated_at: null,
  });
});

describe("NavigationVisibilityEditor", () => {
  it("renders one select per catalogue entry except user-management", async () => {
    render(<NavigationVisibilityEditor scope="global" />);
    await waitFor(() =>
      expect(screen.getByTestId("nav-visibility-select-dashboard")).toBeTruthy()
    );
    const expected = NAV_ITEMS.filter((i) => i.key !== "user-management").length;
    expect(screen.getAllByTestId(/^nav-visibility-select-/)).toHaveLength(expected);
  });

  it("preselects the stored role for an entry", async () => {
    render(<NavigationVisibilityEditor scope="global" />);
    const select = (await screen.findByTestId(
      "nav-visibility-select-settings"
    )) as HTMLSelectElement;
    expect(select.value).toBe("admin");
  });

  it("preselects the empty 'no role' option for an absent entry", async () => {
    render(<NavigationVisibilityEditor scope="global" />);
    const select = (await screen.findByTestId(
      "nav-visibility-select-audit"
    )) as HTMLSelectElement;
    expect(select.value).toBe("");
  });

  it("sends the whole map on save, with the changed entry applied", async () => {
    render(<NavigationVisibilityEditor scope="global" />);
    const select = await screen.findByTestId("nav-visibility-select-audit");
    await userEvent.selectOptions(select, "editor");
    await userEvent.click(screen.getByTestId("nav-visibility-save"));

    await waitFor(() =>
      expect(navigationVisibilityApi.replaceGlobal).toHaveBeenCalledWith({
        settings: "admin",
        audit: "editor",
      })
    );
  });

  it("drops an entry from the map when it is set back to no role", async () => {
    render(<NavigationVisibilityEditor scope="global" />);
    const select = await screen.findByTestId("nav-visibility-select-settings");
    await userEvent.selectOptions(select, "");
    await userEvent.click(screen.getByTestId("nav-visibility-save"));

    await waitFor(() =>
      expect(navigationVisibilityApi.replaceGlobal).toHaveBeenCalledWith({})
    );
  });

  it("saves through the workspace endpoint in workspace scope", async () => {
    render(<NavigationVisibilityEditor scope="workspace" workspaceId="ws-1" />);
    const select = await screen.findByTestId("nav-visibility-select-audit");
    await userEvent.selectOptions(select, "admin");
    await userEvent.click(screen.getByTestId("nav-visibility-save"));

    await waitFor(() =>
      expect(navigationVisibilityApi.replaceWorkspace).toHaveBeenCalledWith("ws-1", {
        audit: "admin",
      })
    );
  });

  it("offers reset only in workspace scope", async () => {
    const { unmount } = render(<NavigationVisibilityEditor scope="global" />);
    await screen.findByTestId("nav-visibility-select-dashboard");
    expect(screen.queryByTestId("nav-visibility-reset")).toBeNull();
    unmount();

    render(<NavigationVisibilityEditor scope="workspace" workspaceId="ws-1" />);
    expect(await screen.findByTestId("nav-visibility-reset")).toBeTruthy();
  });

  it("surfaces a load failure instead of rendering an empty editor", async () => {
    vi.mocked(navigationVisibilityApi.getGlobal).mockRejectedValue(
      new Error("boom")
    );
    render(<NavigationVisibilityEditor scope="global" />);
    expect(await screen.findByTestId("nav-visibility-error")).toBeTruthy();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm frontend-test sh -c "npm install && npx vitest run src/components/NavigationVisibilityEditor --testTimeout=30000"`
Expected: FAIL with `Failed to resolve import "./NavigationVisibilityEditor"`

- [ ] **Step 3: Write the stylesheet**

Create `frontend/src/components/NavigationVisibilityEditor/NavigationVisibilityEditor.module.css`:

```css
/* Rollenbasierte-Sichten §3.1 — navigation-visibility editor.
   CSS Module, not inline styles: ui-ratchet.test.ts asserts the inline
   `style={{` count with `toBe`, so a new inline style fails the build. */

.wrapper {
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
}

.hint {
  margin: 0;
  font-size: var(--font-size-sm);
  color: var(--color-text-muted);
}

.group {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.groupLabel {
  font-size: var(--font-size-xs);
  font-weight: 600;
  letter-spacing: var(--tracking-wide);
  text-transform: uppercase;
  color: var(--color-text-muted);
}

.row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-4);
  padding: var(--space-2) 0;
  border-bottom: 1px solid var(--color-border);
}

.rowLabel {
  font-size: var(--font-size-sm);
  color: var(--color-text);
}

.select {
  min-width: 12rem;
  padding: var(--space-1) var(--space-2);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-surface);
  color: var(--color-text);
  font-size: var(--font-size-sm);
}

.actions {
  display: flex;
  gap: var(--space-3);
}

.error {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  color: var(--color-danger);
  font-size: var(--font-size-sm);
}

.toast {
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-surface-raised);
  color: var(--color-text);
  font-size: var(--font-size-sm);
}
```

- [ ] **Step 4: Write the editor**

Create `frontend/src/components/NavigationVisibilityEditor/NavigationVisibilityEditor.tsx`:

```tsx
/**
 * Rollenbasierte-Sichten spec, sections 3.1 and 6 — the navigation-visibility
 * editor. One row per catalogue entry, one `<select>` per row, a single
 * full-map save.
 *
 * `scope="global"` edits the tenant default (and propagates to every
 * non-customized workspace); `scope="workspace"` edits one workspace's
 * override and can reset it back to the default. Same shape as the Workflow
 * Editor's scope prop.
 *
 * NOT A SECURITY BOUNDARY: a wrongly configured entry makes a link visible
 * that the server still rejects — a UX defect, not a hole.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { AlertCircle } from "lucide-react";

import {
  navigationVisibilityApi,
  type NavigationRole,
  type NavigationVisibilityMap,
} from "../../api/navigation-visibility";
import {
  NAV_GROUP_LABEL_KEYS,
  NAV_GROUP_ORDER,
  NAV_ITEMS,
} from "../NavigationShell/nav-items";
import { useToast } from "../shared/Toast/useToast";
import styles from "./NavigationVisibilityEditor.module.css";

/**
 * Selectable roles, listed narrowest-audience-first so the dropdown reads as
 * "how restrictive". `admin` is last because it is treated as a superset of
 * every other role by `useHasRole`. `""` = no role required.
 */
const ROLE_OPTIONS: NavigationRole[] = ["viewer", "editor", "approver", "admin"];

/**
 * `/user-management` gates on tenant-admin, which the workspace-role map
 * cannot express — showing it here would offer a setting that does nothing.
 */
const UNCONFIGURABLE_KEYS = new Set<string>(["user-management"]);

export interface NavigationVisibilityEditorProps {
  scope: "global" | "workspace";
  /** Required when `scope === "workspace"`. */
  workspaceId?: string;
}

export function NavigationVisibilityEditor({
  scope,
  workspaceId,
}: NavigationVisibilityEditorProps): JSX.Element {
  const { t } = useTranslation();
  const toast = useToast();
  const [draft, setDraft] = useState<NavigationVisibilityMap>({});
  const [isCustomized, setIsCustomized] = useState<boolean>(false);
  const [loading, setLoading] = useState<boolean>(true);
  const [saving, setSaving] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (): Promise<void> => {
    setLoading(true);
    setError(null);
    try {
      if (scope === "global") {
        const resolved = await navigationVisibilityApi.getGlobal();
        setDraft(resolved.visibility ?? {});
        setIsCustomized(false);
      } else {
        const resolved = await navigationVisibilityApi.getWorkspace(workspaceId!);
        setDraft(resolved.visibility ?? {});
        setIsCustomized(resolved.is_customized);
      }
    } catch {
      setError(t("navigationVisibility.loadFailed"));
    } finally {
      setLoading(false);
    }
  }, [scope, t, workspaceId]);

  useEffect(() => {
    void load();
  }, [load]);

  const rows = useMemo(
    () =>
      NAV_GROUP_ORDER.map((group) => ({
        group,
        items: NAV_ITEMS.filter(
          (item) => item.group === group && !UNCONFIGURABLE_KEYS.has(item.key)
        ),
      })).filter((entry) => entry.items.length > 0),
    []
  );

  const change = useCallback((key: string, value: string): void => {
    setDraft((current) => {
      const next = { ...current };
      // An entry with no role requirement is ABSENT from the map, not stored
      // as null — that keeps the stored document minimal and makes "unset"
      // and "explicitly no role" the same thing, as the backend expects.
      if (value === "") delete next[key];
      else next[key] = value as NavigationRole;
      return next;
    });
  }, []);

  const save = useCallback(async (): Promise<void> => {
    setSaving(true);
    setError(null);
    try {
      if (scope === "global") {
        const saved = await navigationVisibilityApi.replaceGlobal(draft);
        toast.show(
          t("navigationVisibility.savedGlobal", {
            count: saved.propagated ?? 0,
          })
        );
      } else {
        const saved = await navigationVisibilityApi.replaceWorkspace(
          workspaceId!,
          draft
        );
        setIsCustomized(saved.is_customized);
        toast.show(t("navigationVisibility.saved"));
      }
    } catch {
      setError(t("navigationVisibility.saveFailed"));
    } finally {
      setSaving(false);
    }
  }, [draft, scope, t, toast, workspaceId]);

  const reset = useCallback(async (): Promise<void> => {
    setSaving(true);
    setError(null);
    try {
      const restored = await navigationVisibilityApi.resetWorkspace(workspaceId!);
      setDraft(restored.visibility ?? {});
      setIsCustomized(restored.is_customized);
      toast.show(t("navigationVisibility.reset"));
    } catch {
      setError(t("navigationVisibility.saveFailed"));
    } finally {
      setSaving(false);
    }
  }, [t, toast, workspaceId]);

  if (loading) {
    return <div data-testid="nav-visibility-loading" aria-busy="true" />;
  }

  return (
    <div className={styles.wrapper} data-testid="nav-visibility-editor">
      <p className={styles.hint}>{t("navigationVisibility.hint")}</p>
      {error ? (
        <div className={styles.error} role="alert" data-testid="nav-visibility-error">
          <AlertCircle aria-hidden="true" size={16} />
          {error}
        </div>
      ) : null}

      {rows.map(({ group, items }) => (
        <div key={group} className={styles.group}>
          <div className={styles.groupLabel}>{t(NAV_GROUP_LABEL_KEYS[group])}</div>
          {items.map((item) => (
            <div key={item.key} className={styles.row}>
              <label className={styles.rowLabel} htmlFor={`nav-vis-${item.key}`}>
                {t(item.labelKey)}
              </label>
              <select
                id={`nav-vis-${item.key}`}
                className={styles.select}
                data-testid={`nav-visibility-select-${item.key}`}
                value={draft[item.key] ?? ""}
                onChange={(event) => change(item.key, event.target.value)}
              >
                <option value="">{t("navigationVisibility.roleNone")}</option>
                {ROLE_OPTIONS.map((role) => (
                  <option key={role} value={role}>
                    {t(`navigationVisibility.role.${role}`)}
                  </option>
                ))}
              </select>
            </div>
          ))}
        </div>
      ))}

      {toast.message ? (
        <div className={styles.toast} role="status" data-testid="nav-visibility-toast">
          {toast.message}
        </div>
      ) : null}

      <div className={styles.actions}>
        <button
          type="button"
          className="btn-primary"
          data-testid="nav-visibility-save"
          disabled={saving}
          onClick={() => void save()}
        >
          {t("navigationVisibility.save")}
        </button>
        {scope === "workspace" ? (
          <button
            type="button"
            className="btn-secondary"
            data-testid="nav-visibility-reset"
            disabled={saving || !isCustomized}
            onClick={() => void reset()}
          >
            {t("navigationVisibility.resetToDefault")}
          </button>
        ) : null}
      </div>
    </div>
  );
}
```

Create `frontend/src/components/NavigationVisibilityEditor/index.ts`:

```ts
export { NavigationVisibilityEditor } from "./NavigationVisibilityEditor";
export type { NavigationVisibilityEditorProps } from "./NavigationVisibilityEditor";
```

- [ ] **Step 5: Add the i18n keys**

In `frontend/src/i18n/locales/de.json`, add a top-level `navigationVisibility` object (nested, never dotted keys):

```json
  "navigationVisibility": {
    "tabLabel": "Navigation",
    "hint": "Legt fest, welche Rolle einen Navigationseintrag sehen darf. Ein Eintrag ohne Rolle ist für alle angemeldeten Nutzer sichtbar. Das Ausblenden ersetzt keine Zugriffskontrolle — der Server prüft die Berechtigung weiterhin selbst.",
    "roleNone": "Keine Rolle erforderlich",
    "role": {
      "viewer": "Leser",
      "editor": "Bearbeiter",
      "approver": "Freigeber",
      "admin": "Administrator"
    },
    "save": "Speichern",
    "saved": "Navigations-Sichtbarkeit gespeichert.",
    "savedGlobal": "Standard gespeichert, {{count}} Workspace(s) übernommen.",
    "resetToDefault": "Auf Standard zurücksetzen",
    "reset": "Auf den Mandanten-Standard zurückgesetzt.",
    "loadFailed": "Navigations-Sichtbarkeit konnte nicht geladen werden.",
    "saveFailed": "Speichern fehlgeschlagen."
  },
```

and the mirror in `en.json`:

```json
  "navigationVisibility": {
    "tabLabel": "Navigation",
    "hint": "Defines which role may see a navigation entry. An entry without a role is visible to every signed-in user. Hiding an entry does not replace access control — the server still checks the permission itself.",
    "roleNone": "No role required",
    "role": {
      "viewer": "Viewer",
      "editor": "Editor",
      "approver": "Approver",
      "admin": "Administrator"
    },
    "save": "Save",
    "saved": "Navigation visibility saved.",
    "savedGlobal": "Default saved, adopted by {{count}} workspace(s).",
    "resetToDefault": "Reset to default",
    "reset": "Reset to the tenant default.",
    "loadFailed": "Could not load navigation visibility.",
    "saveFailed": "Save failed."
  },
```

- [ ] **Step 6: Mount the global tab in System Settings**

In `frontend/src/components/SystemSettings/SystemSettings.tsx`:

1. line 33 — `type SystemTabId = "administration" | "workflow-defaults" | "permission-defaults" | "navigation-visibility" | "memory";`
2. line 35-41 — add `"navigation-visibility",` to `TAB_IDS` between `"permission-defaults"` and `"memory"`
3. line 75-80 — add to `TABS` in the same position:

```tsx
    { id: "navigation-visibility", label: t("navigationVisibility.tabLabel", "Navigation") },
```

4. line 170 — add the panel next to the permission-defaults one:

```tsx
        {activeTab === "navigation-visibility" && (
          <NavigationVisibilityEditor scope="global" />
        )}
```

5. add the import: `import { NavigationVisibilityEditor } from "../NavigationVisibilityEditor";`

- [ ] **Step 7: Mount the workspace tab in Workspace Settings**

In `frontend/src/components/WorkspaceSettings/WorkspaceSettings.tsx`:

1. line 77-83 — add `| "navigation-visibility"` to `SettingsTabId` after `"visibility"`
2. line 86-93 — add `"navigation-visibility",` to `SETTINGS_TAB_IDS` in the same position
3. line 309-316 — add to `TABS`:

```tsx
    { id: "navigation-visibility", label: t("navigationVisibility.tabLabel", "Navigation") },
```

4. after the `activeTab === "visibility"` panel (line 702-712), add:

```tsx
        {activeTab === "navigation-visibility" && (
          <NavigationVisibilityEditor
            scope="workspace"
            workspaceId={activeWorkspace.id}
          />
        )}
```

5. add the import: `import { NavigationVisibilityEditor } from "../NavigationVisibilityEditor";`

- [ ] **Step 8: Run test to verify it passes**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm frontend-test sh -c "npm install && npx vitest run src/components/NavigationVisibilityEditor src/test/i18n-parity.test.ts src/test/ui-ratchet.test.ts --testTimeout=30000"`
Expected: PASS — 8 editor tests, i18n parity green (both locales carry the new tree), ui-ratchet green (`STYLE_BRACE_BASELINE` unchanged because the editor uses a CSS Module)

- [ ] **Step 9: Verify the editor in the browser**

Run: `docker-compose -f deploy/docker-compose.yml -f deploy/docker-compose.override.yml --project-directory . restart frontend`
Then as an admin: open `/system-settings?tab=navigation-visibility`, set "Audit" to "Administrator", save, and confirm the toast reports the propagation count. Log in as an editor in a second browser profile and confirm "Audit" is gone from the sidebar **without a deploy**. Switch to `/settings?tab=navigation-visibility`, change one entry, confirm the reset button becomes enabled, press it, and confirm the tenant default is restored.

- [ ] **Step 10: Commit**

```bash
git add frontend/src/components/NavigationVisibilityEditor/ frontend/src/components/SystemSettings/SystemSettings.tsx frontend/src/components/WorkspaceSettings/WorkspaceSettings.tsx frontend/src/i18n/locales/de.json frontend/src/i18n/locales/en.json
git commit -m "feat: add navigation-visibility editor to system and workspace settings"
```

---

## Phase D — Frontend: form mode and expert mode

> **Ordering:** Phase D depends on the Attribute-Definition plan's Task 18 (`ArtifactForm.tsx`) being merged — see precondition P2. Tasks 10 and 11 have no such dependency and may run earlier; only Task 12 touches `ArtifactForm.tsx`.

### Task 10: `expertModeEnabled` in `AuthContext`

**Files:**
- Modify: `frontend/src/context/AuthContext.tsx:35-44,88-100,124,131-147,243-249`
- Test: `frontend/src/test/AuthContext.expertMode.test.tsx`

**Interfaces:**
- Consumes: `apiClient.patch`, the `expert_mode_enabled` field of the `/auth/me/` and `/auth/login/` `user` payload (Task 5)
- Produces: `AuthUser.expert_mode_enabled: boolean`, `AuthState.expertModeEnabled: boolean`, `AuthState.setExpertMode: (enabled: boolean) => Promise<void>`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/test/AuthContext.expertMode.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";

vi.mock("../api/client", () => ({
  apiClient: { get: vi.fn(), patch: vi.fn(), post: vi.fn() },
  resetUnauthorizedGuard: vi.fn(),
}));

import { apiClient } from "../api/client";
import { AuthProvider, useAuth } from "../context/AuthContext";

const BASE_USER = {
  id: "u-1",
  username: "ada",
  email: "ada@example.com",
  first_name: "Ada",
  last_name: "L",
  is_active: true,
  tenant_id: "t-1",
  roles: ["admin"],
  expert_mode_enabled: false,
};

beforeEach(() => {
  vi.mocked(apiClient.get).mockResolvedValue({
    user: BASE_USER,
    tenant_id: "t-1",
    roles: ["admin"],
    is_tenant_admin: false,
  });
  vi.mocked(apiClient.patch).mockReset();
});

function wrapper({ children }: { children: React.ReactNode }): JSX.Element {
  return <AuthProvider>{children}</AuthProvider>;
}

describe("AuthContext expert mode", () => {
  it("exposes the restored preference", async () => {
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.status).toBe("authenticated"));
    expect(result.current.expertModeEnabled).toBe(false);
  });

  it("defaults to false when the server omits the field", async () => {
    const { expert_mode_enabled: _omit, ...legacy } = BASE_USER;
    vi.mocked(apiClient.get).mockResolvedValue({
      user: legacy,
      tenant_id: "t-1",
      roles: ["admin"],
      is_tenant_admin: false,
    });
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.status).toBe("authenticated"));
    expect(result.current.expertModeEnabled).toBe(false);
  });

  it("persists the flag through PATCH /auth/me/", async () => {
    vi.mocked(apiClient.patch).mockResolvedValue({
      user: { ...BASE_USER, expert_mode_enabled: true },
    });
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.status).toBe("authenticated"));

    await act(async () => {
      await result.current.setExpertMode(true);
    });

    expect(apiClient.patch).toHaveBeenCalledWith("/auth/me/", {
      expert_mode_enabled: true,
    });
    expect(result.current.expertModeEnabled).toBe(true);
  });

  it("keeps the previous value when the PATCH fails", async () => {
    vi.mocked(apiClient.patch).mockRejectedValue(new Error("offline"));
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.status).toBe("authenticated"));

    await act(async () => {
      await result.current.setExpertMode(true).catch(() => undefined);
    });

    expect(result.current.expertModeEnabled).toBe(false);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm frontend-test sh -c "npm install && npx vitest run src/test/AuthContext.expertMode.test.tsx --testTimeout=30000"`
Expected: FAIL with `TypeError: result.current.setExpertMode is not a function`

- [ ] **Step 3: Extend the types**

In `frontend/src/context/AuthContext.tsx`, add to `AuthUser` (after `roles`, line 43):

```ts
  /**
   * Rollenbasierte-Sichten spec section 5 — UI density preference, NOT a
   * permission. Optional so a mock/response that predates the field still
   * satisfies the type.
   */
  expert_mode_enabled?: boolean;
```

and to `AuthState` (after `isTenantAdmin`, line 96):

```ts
  /**
   * Whether `audience: "expert"` form sections start expanded. Pure display
   * density (Rollenbasierte-Sichten section 5): the toggle that writes it is
   * rendered for `admin`/`approver` only, but the flag itself grants nothing —
   * `visible` and RBAC remain the real boundaries.
   */
  expertModeEnabled: boolean;
  /** PATCH /api/v1/auth/me/ — persist the expert-mode preference. */
  setExpertMode: (enabled: boolean) => Promise<void>;
```

- [ ] **Step 4: Wire the state**

In the same file:

1. after line 125 add `const [expertModeEnabled, setExpertModeEnabled] = useState<boolean>(false);`
2. in `clearAuth` add `setExpertModeEnabled(false);`
3. in `applyIdentity` add `setExpertModeEnabled(data.user?.expert_mode_enabled ?? false);`
4. after `updateProfile` add:

```tsx
  /**
   * Persists the expert-mode density preference (Rollenbasierte-Sichten §5).
   * State is only advanced AFTER the server confirms, so a failed request
   * leaves the UI on the value that is actually stored rather than showing a
   * preference that was never saved.
   */
  const setExpertMode = useCallback(async (enabled: boolean): Promise<void> => {
    const data = await apiClient.patch<{ user: AuthUser }>("/auth/me/", {
      expert_mode_enabled: enabled,
    });
    setUser(data.user);
    setExpertModeEnabled(data.user?.expert_mode_enabled ?? enabled);
  }, []);
```

5. add `expertModeEnabled,` and `setExpertMode,` to the `value` object and to the `useMemo` dependency array (line 243-249)

- [ ] **Step 5: Run test to verify it passes**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm frontend-test sh -c "npm install && npx vitest run src/test/AuthContext.expertMode.test.tsx --testTimeout=30000"`
Expected: PASS (4 passed)

- [ ] **Step 6: Commit**

```bash
git add frontend/src/context/AuthContext.tsx frontend/src/test/AuthContext.expertMode.test.tsx
git commit -m "feat: expose and persist the expert-mode preference in AuthContext"
```

---

### Task 11: Form-mode derivation

**Files:**
- Create: `frontend/src/components/shared/ArtifactForm/form-mode.ts`
- Test: `frontend/src/components/shared/ArtifactForm/form-mode.test.ts`

**Interfaces:**
- Consumes: nothing (pure module)
- Produces: `FROZEN_STATE_FRAGMENTS: readonly string[]`, `isFrozenState(state: string | null | undefined): boolean`, `deriveFormMode(input: DeriveFormModeInput): "edit" | "read"`, `DeriveFormModeInput`

**Rationale (plan decision D5):** no `frozen` flag exists anywhere in the workflow engine (precondition P4), and spec §6 explicitly keeps form-mode derivation as code logic. The heuristic mirrors `ERROR_STATE_PATTERN` in `frontend/src/api/workflows.ts:141`, which solves the identical "the backend model has no such type" problem the same way.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/shared/ArtifactForm/form-mode.test.ts`:

```ts
import { describe, it, expect } from "vitest";
import { deriveFormMode, isFrozenState } from "./form-mode";

describe("isFrozenState", () => {
  it("treats a missing state as not frozen", () => {
    expect(isFrozenState(null)).toBe(false);
    expect(isFrozenState(undefined)).toBe(false);
    expect(isFrozenState("")).toBe(false);
  });

  it("keeps every working state editable", () => {
    for (const state of [
      "draft",
      "Draft",
      "in_review",
      "In Review",
      "submitted",
      "under_review",
      "Entwurf",
      "Identified",
      "Monitored",
      "Mitigated",
      "Open",
      "In Progress",
      "in_progress",
      "ready",
    ]) {
      expect(isFrozenState(state)).toBe(false);
    }
  });

  it("freezes every approved/terminal state shipped by the defaults", () => {
    for (const state of [
      "approved",
      "Approved",
      "Freigegeben",
      "deprecated",
      "Archiviert",
      "Superseded",
      "Rejected",
      "Closed",
      "implemented",
      "verified",
      "completed",
      "abandoned",
      "Resolved",
      "Wontfix",
      "done",
    ]) {
      expect(isFrozenState(state)).toBe(true);
    }
  });

  it("ignores surrounding whitespace and case", () => {
    expect(isFrozenState("  APPROVED  ")).toBe(true);
  });
});

describe("deriveFormMode", () => {
  it("is read when the caller has no edit right", () => {
    expect(deriveFormMode({ canEdit: false, currentState: "draft" })).toBe("read");
  });

  it("is edit for an editor on a working state", () => {
    expect(deriveFormMode({ canEdit: true, currentState: "draft" })).toBe("edit");
  });

  it("is read for an editor on an approved artifact", () => {
    expect(deriveFormMode({ canEdit: true, currentState: "approved" })).toBe("read");
  });

  it("is read for an admin on an approved artifact too", () => {
    // Role does not unfreeze a state — only an explicit transition does.
    expect(deriveFormMode({ canEdit: true, currentState: "Freigegeben" })).toBe(
      "read"
    );
  });

  it("honours an explicit read request regardless of state and role", () => {
    expect(
      deriveFormMode({ requestedMode: "read", canEdit: true, currentState: "draft" })
    ).toBe("read");
  });

  it("is edit in create mode where there is no state yet", () => {
    expect(deriveFormMode({ canEdit: true, currentState: null })).toBe("edit");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm frontend-test sh -c "npm install && npx vitest run src/components/shared/ArtifactForm/form-mode.test.ts --testTimeout=30000"`
Expected: FAIL with `Failed to resolve import "./form-mode"`

- [ ] **Step 3: Write the module**

Create `frontend/src/components/shared/ArtifactForm/form-mode.ts`:

```ts
/**
 * Read/edit derivation for `ArtifactForm` (Rollenbasierte-Sichten §3.2).
 *
 * The mode follows ROLE **and** WORKFLOW STATE, not role alone: an approved
 * artifact is read-only for the Autor role too. Changing the status stays
 * possible (that is the WorkflowStatusEditor's explicit transition); direct
 * field editing does not.
 *
 * ponytail: name-fragment heuristic, upgrade to a per-state `frozen: true`
 * flag in `workflow_json` if a workspace's renamed states start slipping
 * through. There is no per-state metadata in the workflow engine today
 * (`workflow/definition_store.py` stores plain state strings), so this mirrors
 * the pre-existing `ERROR_STATE_PATTERN` heuristic in `api/workflows.ts`,
 * which solves the same missing-metadata problem the same way. The fragments
 * are derived from the shipped default state sets. Known limits: a workspace
 * that renames "approved" to something unrelated loses the freeze, and a
 * hypothetical "Nicht freigegeben" would be frozen wrongly.
 *
 * UX only — the server still accepts a PATCH from anyone RBAC allows. This
 * decides what the form draws, not what the API permits.
 */

/**
 * Lowercase fragments that mark a state as no-longer-freely-editable. Matched
 * as substrings, so "Freigegeben", "approved" and "Approved" all hit.
 */
export const FROZEN_STATE_FRAGMENTS: readonly string[] = [
  "approv", // approved / Approved
  "freigegeben", // Goal / MainGoal
  "released",
  "deprecat", // deprecated
  "archiv", // Archiviert
  "supersed", // Superseded
  "reject", // Rejected
  "closed", // Closed
  "wontfix",
  "resolved",
  "implemented",
  "verified",
  "completed",
  "abandoned",
  "done",
];

/** Whether *state* is one in which fields must not be edited directly. */
export function isFrozenState(state: string | null | undefined): boolean {
  if (!state) return false;
  const normalized = state.trim().toLowerCase();
  if (!normalized) return false;
  return FROZEN_STATE_FRAGMENTS.some((fragment) =>
    normalized.includes(fragment)
  );
}

export interface DeriveFormModeInput {
  /** An explicit `"read"` from the host always wins. */
  requestedMode?: "edit" | "read";
  /** Whether the caller's role may write this artifact type at all. */
  canEdit: boolean;
  /** The artifact's current workflow state; `null` in create mode. */
  currentState?: string | null;
}

/** Resolve the effective form mode from the host request, role and state. */
export function deriveFormMode({
  requestedMode,
  canEdit,
  currentState,
}: DeriveFormModeInput): "edit" | "read" {
  if (requestedMode === "read") return "read";
  if (!canEdit) return "read";
  if (isFrozenState(currentState)) return "read";
  return "edit";
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm frontend-test sh -c "npm install && npx vitest run src/components/shared/ArtifactForm/form-mode.test.ts --testTimeout=30000"`
Expected: PASS (10 passed)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/shared/ArtifactForm/form-mode.ts frontend/src/components/shared/ArtifactForm/form-mode.test.ts
git commit -m "feat: derive artifact form mode from role and workflow state"
```

---

### Task 12: `ArtifactForm` — effective mode, expert collapse, expert toggle

**Files:**
- Modify: `frontend/src/components/shared/ArtifactForm/ArtifactForm.tsx` (props block, `isSectionOpen`, form header)
- Modify: `frontend/src/components/shared/ArtifactForm/ArtifactForm.module.css`
- Modify: `frontend/src/i18n/locales/de.json`, `frontend/src/i18n/locales/en.json`
- Test: `frontend/src/components/shared/ArtifactForm/ArtifactForm.roles.test.tsx`

**Interfaces:**
- Consumes: `deriveFormMode`, `useAuth()` (`expertModeEnabled`, `setExpertMode`), `useHasRole()`, the `mode?: "edit" | "read"` prop and `isSectionOpen`/`groupIntoSections` from the Attribute-Definition plan's Task 18
- Produces: no new export — the existing `ArtifactForm` gains the behaviour

**Three changes, all inside the existing component (plan decision D6):**

1. `mode` becomes the *requested* mode; the *effective* mode is `deriveFormMode({ requestedMode: mode, canEdit: hasRole("editor"), currentState })`.
2. `isSectionOpen`'s last line honours the expert mode.
3. A toggle in the form header, rendered for `admin`/`approver` only.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/shared/ArtifactForm/ArtifactForm.roles.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

let roles: string[] = ["editor"];
let expertModeEnabled = false;
const setExpertMode = vi.fn(async () => undefined);

vi.mock("../../../context/AuthContext", () => ({
  useAuth: () => ({ roles, expertModeEnabled, setExpertMode }),
}));

vi.mock("../../../hooks/useHasRole", () => ({
  useHasRole:
    () =>
    (required?: string): boolean =>
      !required || roles.includes(required) || roles.includes("admin"),
}));

const DEFINITION = {
  item_type: "Risk",
  version: 1,
  attributes: [
    {
      name: "title", kind: "core", type: "string", widget_key: null, fields: [],
      options: [], required: true, visible: true, locked: false, editable: true,
      section: "general", order: 1, label: "Title", help_text: "", default: null,
      validation: {}, ai_elicit: false, export: true, audience: "basic",
    },
    {
      name: "probability", kind: "core", type: "number", widget_key: null, fields: [],
      options: [], required: false, visible: true, locked: false, editable: true,
      section: "classification", order: 2, label: "Probability", help_text: "",
      default: null, validation: {}, ai_elicit: false, export: true,
      audience: "expert",
    },
  ],
};

vi.mock("./useArtifactDefinition", () => ({
  useArtifactDefinition: () => ({
    definition: DEFINITION,
    loading: false,
    error: null,
  }),
}));

import { ArtifactForm } from "./ArtifactForm";

function renderForm(overrides: Record<string, unknown> = {}): void {
  render(
    <ArtifactForm
      itemType="Risk"
      artifactId="r-1"
      initialValues={{ title: "T", status: "draft" }}
      onSave={vi.fn(async () => undefined)}
      {...overrides}
    />
  );
}

beforeEach(() => {
  roles = ["editor"];
  expertModeEnabled = false;
  setExpertMode.mockClear();
});

describe("ArtifactForm role and state gating", () => {
  it("is editable for an editor on a draft artifact", async () => {
    renderForm();
    const input = (await screen.findByTestId(
      "artifact-field-title"
    )) as HTMLInputElement;
    expect(input.disabled).toBe(false);
  });

  it("is read-only for a viewer", async () => {
    roles = ["viewer"];
    renderForm();
    const input = (await screen.findByTestId(
      "artifact-field-title"
    )) as HTMLInputElement;
    expect(input.disabled).toBe(true);
  });

  it("is read-only for an editor on an approved artifact", async () => {
    renderForm({ initialValues: { title: "T", status: "approved" } });
    const input = (await screen.findByTestId(
      "artifact-field-title"
    )) as HTMLInputElement;
    expect(input.disabled).toBe(true);
  });

  it("still hides the save button when the effective mode is read", async () => {
    roles = ["viewer"];
    renderForm();
    await screen.findByTestId("artifact-field-title");
    expect(screen.queryByTestId("artifact-form-save")).toBeNull();
  });

  it("collapses an expert section by default", async () => {
    roles = ["admin"];
    renderForm();
    const toggle = await screen.findByTestId(
      "artifact-section-toggle-classification"
    );
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
  });

  it("expands an expert section when expert mode is on", async () => {
    roles = ["admin"];
    expertModeEnabled = true;
    renderForm();
    const toggle = await screen.findByTestId(
      "artifact-section-toggle-classification"
    );
    expect(toggle.getAttribute("aria-expanded")).toBe("true");
  });

  it("keeps basic sections expanded regardless of expert mode", async () => {
    renderForm();
    const toggle = await screen.findByTestId("artifact-section-toggle-general");
    expect(toggle.getAttribute("aria-expanded")).toBe("true");
  });

  it("shows the expert toggle to an admin", async () => {
    roles = ["admin"];
    renderForm();
    expect(await screen.findByTestId("artifact-form-expert-toggle")).toBeTruthy();
  });

  it("shows the expert toggle to an approver", async () => {
    roles = ["approver"];
    renderForm();
    expect(await screen.findByTestId("artifact-form-expert-toggle")).toBeTruthy();
  });

  it("hides the expert toggle from an editor", async () => {
    renderForm();
    await screen.findByTestId("artifact-field-title");
    expect(screen.queryByTestId("artifact-form-expert-toggle")).toBeNull();
  });

  it("hides the expert toggle from a viewer", async () => {
    roles = ["viewer"];
    renderForm();
    await screen.findByTestId("artifact-field-title");
    expect(screen.queryByTestId("artifact-form-expert-toggle")).toBeNull();
  });

  it("persists the preference when the toggle is used", async () => {
    roles = ["admin"];
    renderForm();
    await userEvent.click(await screen.findByTestId("artifact-form-expert-toggle"));
    await waitFor(() => expect(setExpertMode).toHaveBeenCalledWith(true));
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm frontend-test sh -c "npm install && npx vitest run src/components/shared/ArtifactForm/ArtifactForm.roles.test.tsx --testTimeout=30000"`
Expected: FAIL — "is read-only for a viewer" fails (the form ignores the role) and every expert-toggle test fails with "Unable to find element by: [data-testid='artifact-form-expert-toggle']"

- [ ] **Step 3: Derive the effective mode**

In `ArtifactForm.tsx`, add the imports:

```tsx
import { useAuth } from "../../../context/AuthContext";
import { useHasRole } from "../../../hooks/useHasRole";
import { deriveFormMode } from "./form-mode";
```

Update the `mode` prop docstring in `ArtifactFormProps` to:

```tsx
  /**
   * The mode the HOST requests. `"read"` always wins; `"edit"` is a request
   * that the role/workflow-state derivation may still downgrade
   * (Rollenbasierte-Sichten §3.2).
   */
  mode?: "edit" | "read";
```

and replace the `const isReadOnly = mode === "read";` line with:

```tsx
  const { expertModeEnabled, setExpertMode } = useAuth();
  const hasRole = useHasRole();
  // Rollenbasierte-Sichten §3.2: role AND workflow state. An approved artifact
  // is read-only for the Autor role too — the status can still be moved via an
  // explicit transition (WorkflowStatusEditor below), the fields cannot.
  // UX only: the server-side RBAC check remains the enforcement.
  const effectiveMode = deriveFormMode({
    requestedMode: mode,
    canEdit: hasRole("editor"),
    currentState: (values.status as string | null | undefined) ?? null,
  });
  const isReadOnly = effectiveMode === "read";
  // §5: the density switch is offered to the Experte view only. It is a
  // PREFERENCE, not a right — it changes what starts expanded, never what is
  // editable.
  const canUseExpertMode = hasRole("admin") || hasRole("approver");
```

Every existing consumer of `isReadOnly` (field `disabled` props, the save button, the delete affordance) needs no change — it now carries the derived value.

- [ ] **Step 4: Honour expert mode in the collapse decision**

In `isSectionOpen`, replace the final line `return section.audience !== "expert";` with:

```tsx
      // Rollenbasierte-Sichten §4: an `audience: "expert"` section starts
      // COLLAPSED (not hidden — that stays `visible`) unless the user has
      // switched expert mode on. `viewer` and `editor` never can, which is the
      // spec's intent: for them the collapsed default simply always applies.
      if (section.audience !== "expert") return true;
      return expertModeEnabled;
```

and add `expertModeEnabled` to the `useCallback` dependency array (`[expanded, fieldErrors, expertModeEnabled]`).

- [ ] **Step 5: Render the toggle**

Directly inside the `<form>`, above the `formError` block, add:

```tsx
      {canUseExpertMode ? (
        <div className={styles.expertModeRow}>
          <button
            type="button"
            role="switch"
            aria-checked={expertModeEnabled}
            data-testid="artifact-form-expert-toggle"
            className={styles.expertModeToggle}
            onClick={() => {
              void setExpertMode(!expertModeEnabled).catch(() => undefined);
            }}
          >
            {t("artifactForm.expertMode")}
            <span
              aria-hidden="true"
              className={
                expertModeEnabled
                  ? `${styles.switchTrack} ${styles.switchTrackOn}`
                  : styles.switchTrack
              }
            >
              <span
                className={
                  expertModeEnabled
                    ? `${styles.switchKnob} ${styles.switchKnobOn}`
                    : styles.switchKnob
                }
              />
            </span>
          </button>
          <span className={styles.expertModeHint}>
            {t("artifactForm.expertModeHint")}
          </span>
        </div>
      ) : null}
```

- [ ] **Step 6: Add the styles**

Append to `frontend/src/components/shared/ArtifactForm/ArtifactForm.module.css`:

```css
/* Rollenbasierte-Sichten §5 — expert-mode density switch. */
.expertModeRow {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  justify-content: flex-end;
  margin-bottom: var(--space-3);
}

.expertModeToggle {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-1) var(--space-2);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-surface);
  color: var(--color-text);
  font-size: var(--font-size-sm);
  cursor: pointer;
}

.expertModeHint {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
}

.switchTrack {
  display: inline-block;
  width: 2rem;
  height: 1rem;
  border-radius: var(--radius-full);
  background: var(--color-border);
  position: relative;
  transition: background 120ms ease;
}

.switchTrackOn {
  background: var(--color-primary);
}

.switchKnob {
  position: absolute;
  top: 2px;
  left: 2px;
  width: 0.75rem;
  height: 0.75rem;
  border-radius: var(--radius-full);
  background: var(--color-surface);
  transition: transform 120ms ease;
}

.switchKnobOn {
  transform: translateX(1rem);
}
```

- [ ] **Step 7: Add the i18n keys**

Add to the existing `artifactForm` object in `frontend/src/i18n/locales/de.json`:

```json
    "expertMode": "Expertenmodus",
    "expertModeHint": "Zeigt Experten-Abschnitte aufgeklappt. Ändert keine Berechtigungen.",
```

and in `en.json`:

```json
    "expertMode": "Expert mode",
    "expertModeHint": "Expands expert sections by default. Grants no additional rights.",
```

- [ ] **Step 8: Run test to verify it passes**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm frontend-test sh -c "npm install && npx vitest run src/components/shared/ArtifactForm src/test/i18n-parity.test.ts src/test/ui-ratchet.test.ts --testTimeout=30000"`
Expected: PASS — 12 new tests plus the Attribute-Definition plan's own `ArtifactForm` suites still green; i18n parity and ui-ratchet green

- [ ] **Step 9: Verify in the browser**

Run: `docker-compose -f deploy/docker-compose.yml -f deploy/docker-compose.override.yml --project-directory . restart frontend`
As an admin: open a Risk, mark one attribute `audience: "expert"` in `/system-settings?tab=attributes` (Attribute-Definition plan Task 26), reload the Risk and confirm the "Klassifikation" section starts collapsed; flip the expert toggle and confirm it starts expanded after a full page reload (i.e. the preference persisted, not just component state). Then move the Risk to an approved state and confirm the fields become read-only while the status transition buttons stay available. Finally log in as a viewer and confirm the form renders read-only with no save/delete button and no expert toggle.

- [ ] **Step 10: Commit**

```bash
git add frontend/src/components/shared/ArtifactForm/ frontend/src/i18n/locales/de.json frontend/src/i18n/locales/en.json
git commit -m "feat: derive artifact form mode and expert density from role and state"
```

---

## Phase E — Frontend: the Leser view has no write affordances

### Task 13: `PageHeaderAction.requiresRole` — one gate for every route

**Files:**
- Modify: `frontend/src/components/shared/PageHeader.tsx:26-50,137-138`
- Test: `frontend/src/components/shared/PageHeader.roles.test.tsx`

**Interfaces:**
- Consumes: `useHasRole` (Task 7's widened `RequiredRole`)
- Produces: `PageHeaderAction.requiresRole?: RequiredRole`

**Rationale (plan decision D8):** 15 routes render their create affordance through `PageHeader`. Fifteen `{hasRole('editor') && …}` guards is fifteen places to forget one; one filter inside `PageHeader` covers primary, secondary and overflow actions at once. Opt-in (not opt-out), because `UserManagement`'s primary action is tenant-admin-gated and `TraceabilityView`'s compare/export actions are reads.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/shared/PageHeader.roles.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";

let roles: string[] = [];
vi.mock("../../hooks/useHasRole", () => ({
  useHasRole:
    () =>
    (required?: string): boolean =>
      !required || roles.includes(required) || roles.includes("admin"),
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (k: string, d?: string) => d ?? k }),
}));

import { PageHeader } from "./PageHeader";

beforeEach(() => {
  roles = [];
});

describe("PageHeader role gating", () => {
  it("renders an ungated primary action for anyone", () => {
    roles = ["viewer"];
    render(
      <PageHeader
        title="Risks"
        primaryAction={{ label: "New", onClick: vi.fn(), testId: "primary" }}
      />
    );
    expect(screen.getByTestId("primary")).toBeTruthy();
  });

  it("does not render a gated primary action for a viewer", () => {
    roles = ["viewer"];
    render(
      <PageHeader
        title="Risks"
        primaryAction={{
          label: "New",
          onClick: vi.fn(),
          testId: "primary",
          requiresRole: "editor",
        }}
      />
    );
    expect(screen.queryByTestId("primary")).toBeNull();
  });

  it("renders a gated primary action for an editor", () => {
    roles = ["editor"];
    render(
      <PageHeader
        title="Risks"
        primaryAction={{
          label: "New",
          onClick: vi.fn(),
          testId: "primary",
          requiresRole: "editor",
        }}
      />
    );
    expect(screen.getByTestId("primary")).toBeTruthy();
  });

  it("treats admin as a superset of editor", () => {
    roles = ["admin"];
    render(
      <PageHeader
        title="Risks"
        primaryAction={{
          label: "New",
          onClick: vi.fn(),
          testId: "primary",
          requiresRole: "editor",
        }}
      />
    );
    expect(screen.getByTestId("primary")).toBeTruthy();
  });

  it("filters gated secondary and overflow actions too", () => {
    roles = ["viewer"];
    render(
      <PageHeader
        title="Baselines"
        secondaryActions={[
          { label: "Compare", onClick: vi.fn(), testId: "secondary" },
          {
            label: "Edit", onClick: vi.fn(), testId: "secondary-gated",
            requiresRole: "editor",
          },
        ]}
        overflowActions={[
          {
            label: "Create", onClick: vi.fn(), testId: "overflow-gated",
            requiresRole: "editor",
          },
        ]}
      />
    );
    expect(screen.getByTestId("secondary")).toBeTruthy();
    expect(screen.queryByTestId("secondary-gated")).toBeNull();
    expect(screen.queryByTestId("overflow-gated")).toBeNull();
  });

  it("omits the whole actions row when every action is filtered out", () => {
    roles = ["viewer"];
    render(
      <PageHeader
        title="Risks"
        primaryAction={{
          label: "New", onClick: vi.fn(), testId: "primary",
          requiresRole: "editor",
        }}
      />
    );
    // Issue #718: an empty actions row must not exist in the DOM at all.
    expect(screen.queryByTestId("page-header-actions")).toBeNull();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm frontend-test sh -c "npm install && npx vitest run src/components/shared/PageHeader.roles.test.tsx --testTimeout=30000"`
Expected: FAIL — "does not render a gated primary action for a viewer" finds the button (the field is ignored today)

- [ ] **Step 3: Add the field**

In `frontend/src/components/shared/PageHeader.tsx`, add the import:

```tsx
import { useHasRole, type RequiredRole } from "../../hooks/useHasRole";
```

and add to `PageHeaderAction` (after `prefixWithPlus`, line 49):

```tsx
  /**
   * Rollenbasierte-Sichten spec §3.2: the workspace role required to see this
   * action at all. An action the caller may not perform is NOT RENDERED — not
   * disabled, not CSS-hidden. Absent = visible to any authenticated role.
   *
   * UX only: the server-side RBAC check on the write endpoint is the actual
   * enforcement, exactly as before.
   */
  requiresRole?: RequiredRole;
```

- [ ] **Step 4: Filter in the component**

In `PageHeader`, immediately after `const { t } = useTranslation();` (line 90) add:

```tsx
  const hasRole = useHasRole();
  const allowed = useCallback(
    (action: PageHeaderAction): boolean => hasRole(action.requiresRole),
    [hasRole]
  );
```

and replace the destructured action values with filtered ones — insert directly above the `hasActions` computation (line 137):

```tsx
  const visiblePrimaryAction =
    primaryAction && allowed(primaryAction) ? primaryAction : undefined;
  const visibleSecondaryActions = secondaryActions.filter(allowed);
  const visibleOverflowActions = overflowActions.filter(allowed);
  const hasActions =
    visibleSecondaryActions.length > 0 ||
    !!visiblePrimaryAction ||
    visibleOverflowActions.length > 0;
```

Then replace every render-side reference below: `secondaryActions` → `visibleSecondaryActions` (line 203 map), `primaryAction` → `visiblePrimaryAction` (lines 216-221), `overflowActions` → `visibleOverflowActions` (line 269 map and the menu-trigger condition). The pre-existing `hasActions` declaration at line 137-138 is deleted (replaced by the block above).

- [ ] **Step 5: Run test to verify it passes**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm frontend-test sh -c "npm install && npx vitest run src/components/shared/PageHeader --testTimeout=30000"`
Expected: PASS — 6 new tests plus the pre-existing `PageHeader.test.tsx` suite still green (no action there sets `requiresRole`, so every one stays visible)

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/shared/PageHeader.tsx frontend/src/components/shared/PageHeader.roles.test.tsx
git commit -m "feat: hide page-header actions the caller's role may not perform"
```

---

### Task 14: Gate every create affordance on `editor`

**Files:**
- Modify (one line each): `frontend/src/components/AdrEditors/AdrEditors.tsx:155-160`, `ArchitectureEditors/ArchitectureEditors.tsx:818-827`, `BaselinesView/BaselinesView.tsx:396-400`, `DiagramView/DiagramView.tsx`, `GlossaryView/GlossaryView.tsx`, `Goals/GoalsPage.tsx`, `IcdView/IcdView.tsx`, `InterviewEditors/InterviewEditors.tsx`, `IssueEditors/IssueEditors.tsx:138-143`, `NeedsEditors/NeedsEditors.tsx:231-243`, `RiskEditors/RiskEditors.tsx:138-143`, `TestCaseEditors/TestCaseEditors.tsx:193-198`, `TestRuns/TestRunsList.tsx`, `TraceabilityView/TraceabilityView.tsx:964-968`
- Modify (simplification): `frontend/src/components/RequirementEditors/RequirementEditors.tsx:419-430`
- Test: `frontend/src/test/ViewerWriteAffordances.test.tsx`

**Interfaces:**
- Consumes: `PageHeaderAction.requiresRole` (Task 13)
- Produces: no new export

**Deliberately NOT gated:** `Settings/UserManagement/UserManagement.tsx` (`user-management-create-btn`) — its gate is `isTenantAdmin`, a tenant-wide concept `requiresRole` cannot express, and the page already blocks non-tenant-admins.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/test/ViewerWriteAffordances.test.tsx`:

```tsx
/**
 * Rollenbasierte-Sichten §3.2 — the Leser view offers no create affordance.
 *
 * A source-level assertion rather than 14 render tests: every route's create
 * button is a `PageHeader` action object, and Task 13 proved the filtering
 * once. What can still regress is a route FORGETTING the `requiresRole` field
 * (or a new route shipping without it), which is exactly what this checks.
 */
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const ROOT = resolve(__dirname, "..");

/** file -> the create action's testId that must carry `requiresRole`. */
const GATED_CREATE_ACTIONS: Record<string, string> = {
  "components/AdrEditors/AdrEditors.tsx": "create-adr-btn",
  "components/ArchitectureEditors/ArchitectureEditors.tsx": "create-arch-btn",
  "components/BaselinesView/BaselinesView.tsx": "create-baseline-btn",
  "components/DiagramView/DiagramView.tsx": "create-diagram-btn",
  "components/GlossaryView/GlossaryView.tsx": "create-glossary-term-btn",
  "components/Goals/GoalsPage.tsx": "create-goal-btn",
  "components/IcdView/IcdView.tsx": "create-icd-btn",
  "components/InterviewEditors/InterviewEditors.tsx": "create-interview-btn",
  "components/IssueEditors/IssueEditors.tsx": "create-issue-btn",
  "components/NeedsEditors/NeedsEditors.tsx": "create-need-btn",
  "components/RequirementEditors/RequirementEditors.tsx": "create-req-btn",
  "components/RiskEditors/RiskEditors.tsx": "create-risk-btn",
  "components/TestCaseEditors/TestCaseEditors.tsx": "create-tc-btn",
  "components/TestRuns/TestRunsList.tsx": "testrun-create-btn",
  "components/TraceabilityView/TraceabilityView.tsx": "tracelink-create-btn",
};

describe("viewer write affordances", () => {
  for (const [file, testId] of Object.entries(GATED_CREATE_ACTIONS)) {
    it(`gates ${testId} on the editor role`, () => {
      const source = readFileSync(resolve(ROOT, file), "utf8");
      const index = source.indexOf(testId);
      expect(index, `${testId} not found in ${file}`).toBeGreaterThan(-1);
      // The action object is small; look at the 400 characters around the
      // test id rather than parsing TSX.
      const window = source.slice(Math.max(0, index - 400), index + 400);
      expect(window, `${file} is missing requiresRole near ${testId}`).toContain(
        'requiresRole: "editor"'
      );
    });
  }

  it("does not gate user management on a workspace role", () => {
    const source = readFileSync(
      resolve(ROOT, "components/Settings/UserManagement/UserManagement.tsx"),
      "utf8"
    );
    const index = source.indexOf("user-management-create-btn");
    const window = source.slice(Math.max(0, index - 400), index + 400);
    expect(window).not.toContain("requiresRole");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm frontend-test sh -c "npm install && npx vitest run src/test/ViewerWriteAffordances.test.tsx --testTimeout=30000"`
Expected: FAIL — 15 failures, each "is missing requiresRole near create-*-btn"

- [ ] **Step 3: Add the field to the 14 plain action objects**

In each file below, add `requiresRole: "editor",` as the last property of the action object carrying the named test id. Files using single quotes for props keep single quotes (`requiresRole: 'editor',`) so Prettier does not reformat neighbouring lines.

| File | Action object | Test id |
|---|---|---|
| `components/AdrEditors/AdrEditors.tsx:155-160` | `primaryAction` | `create-adr-btn` |
| `components/ArchitectureEditors/ArchitectureEditors.tsx:818-827` | `primaryAction` | `create-arch-btn` |
| `components/BaselinesView/BaselinesView.tsx:396-400` | `overflowActions[0]` | `create-baseline-btn` |
| `components/DiagramView/DiagramView.tsx` | `primaryAction` | `create-diagram-btn` |
| `components/GlossaryView/GlossaryView.tsx` | `primaryAction` | `create-glossary-term-btn` |
| `components/Goals/GoalsPage.tsx` | `primaryAction` | `create-goal-btn` |
| `components/IcdView/IcdView.tsx` | `primaryAction` | `create-icd-btn` |
| `components/InterviewEditors/InterviewEditors.tsx` | `primaryAction` | `create-interview-btn` |
| `components/IssueEditors/IssueEditors.tsx:138-143` | `primaryAction` | `create-issue-btn` |
| `components/NeedsEditors/NeedsEditors.tsx:231-243` | `primaryAction` | `create-need-btn` |
| `components/RiskEditors/RiskEditors.tsx:138-143` | `primaryAction` | `create-risk-btn` |
| `components/TestCaseEditors/TestCaseEditors.tsx:193-198` | `primaryAction` | `create-tc-btn` |
| `components/TestRuns/TestRunsList.tsx` | `primaryAction` | `testrun-create-btn` |
| `components/TraceabilityView/TraceabilityView.tsx:964-968` | `primaryAction` | `tracelink-create-btn` |

Worked example — `RiskEditors.tsx:138-143` becomes:

```tsx
        primaryAction={{
          label: newRiskLabel,
          prefixWithPlus: true,
          onClick: openCreateDialog,
          testId: 'create-risk-btn',
          // Rollenbasierte-Sichten §3.2 — the Leser view has no create action.
          requiresRole: 'editor',
        }}
```

- [ ] **Step 4: Simplify the hand-rolled guard in `RequirementEditors`**

`RequirementEditors.tsx:419-430` predates the shared field (commit 54b09760) and hand-rolls the same gate with a ternary. Replace it with:

```tsx
      primaryAction={{
        // Names the result, not the gesture (UI concept ch. 12.1 / 14.2,
        // GH-343): every other artifact route reads "New <Entity>".
        label: t('requirements.newRequirement'),
        prefixWithPlus: true,
        onClick: toggleCreateForm,
        testId: 'create-req-btn',
        // Rollenbasierte-Sichten §3.2 — was a `hasRole('editor') ? … :
        // undefined` ternary here; folded onto the shared PageHeader field so
        // exactly one idiom exists across all 15 routes.
        requiresRole: 'editor',
      }}
```

The local `const hasRole = useHasRole();` at line 73 stays — lines 681 and 702 still use it for the AI-derive and create-form gates.

- [ ] **Step 5: Run test to verify it passes**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm frontend-test sh -c "npm install && npx vitest run src/test/ViewerWriteAffordances.test.tsx --testTimeout=30000"`
Expected: PASS (16 passed)

- [ ] **Step 6: Run the affected route suites**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm frontend-test sh -c "npm install && npx vitest run src/components src/test --testTimeout=30000"`
Expected: no NEW failures. Roughly 14 vitest failures are pre-existing locally (green in CI); compare against a baseline run on the merge-base before assuming a regression.

- [ ] **Step 7: Check the e2e specs that click these buttons**

Run: `grep -rn "create-arch-btn\|create-req-btn\|create-risk-btn\|create-adr-btn\|create-issue-btn\|create-tc-btn\|create-need-btn\|create-goal-btn\|create-diagram-btn\|create-icd-btn\|tracelink-create-btn\|testrun-create-btn\|create-baseline-btn\|create-glossary-term-btn\|create-interview-btn" e2e/tests/`
Expected: a list of specs. Every one of them logs in as the seeded admin (which holds `admin`, a superset of `editor`), so no spec needs a change — confirm that by checking each hit's login fixture. If a spec logs in as a viewer, it must be updated in this commit, because the button it clicks no longer exists.

- [ ] **Step 8: Verify in the browser**

Run: `docker-compose -f deploy/docker-compose.yml -f deploy/docker-compose.override.yml --project-directory . restart frontend`
Log in as a viewer and walk `/requirements`, `/risks`, `/issues`, `/adrs`, `/testcases`, `/needs`, `/architecture`, `/goals`, `/glossary`, `/diagrams`, `/icds`, `/traceability`, `/test-runs`, `/baselines`, `/interviews`. Confirm that no create button renders on any of them (inspect the DOM, not just the visuals) and that reading, filtering and export still work.

- [ ] **Step 9: Commit**

```bash
git add frontend/src/components frontend/src/test/ViewerWriteAffordances.test.tsx
git commit -m "feat: hide create affordances from the viewer role on every artifact route"
```

---

## Phase F — Close-out

### Task 15: Document the three views and close #848

**Files:**
- Create: `docs/api/navigation-visibility.openapi.yaml`
- Modify: `docs/ARCHITECTURE.md`
- Test: `backend/rest_api/tests/test_navigation_visibility_openapi.py`

**Interfaces:**
- Consumes: the routes registered in Task 4
- Produces: the published contract document; no code interface

- [ ] **Step 1: Write the failing test**

Create `backend/rest_api/tests/test_navigation_visibility_openapi.py`:

```python
"""The three navigation-visibility routes appear in the generated schema."""
from __future__ import annotations

import pytest
from drf_spectacular.generators import SchemaGenerator

pytestmark = pytest.mark.django_db


def test_all_three_routes_are_documented() -> None:
    schema = SchemaGenerator().get_schema(request=None, public=True)
    paths = set(schema["paths"])
    assert "/api/v1/navigation-visibility-defaults/" in paths
    assert "/api/v1/workspaces/{workspace_id}/navigation-visibility/" in paths
    assert (
        "/api/v1/workspaces/{workspace_id}/navigation-visibility/reset/" in paths
    )


def test_the_global_route_exposes_get_and_put() -> None:
    schema = SchemaGenerator().get_schema(request=None, public=True)
    ops = schema["paths"]["/api/v1/navigation-visibility-defaults/"]
    assert set(ops) >= {"get", "put"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -e DB_NAME=test_navvis backend-test pytest rest_api/tests/test_navigation_visibility_openapi.py -v --create-db`
Expected: PASS if Task 4 registered the routes correctly; FAIL with a `KeyError` otherwise. A failure here means the URL registration in Task 4 Step 4 is wrong — fix that, not this test.

- [ ] **Step 3: Write the contract document**

Create `docs/api/navigation-visibility.openapi.yaml`, mirroring the structure of the existing `workflow-permissions-global-default.openapi.yaml`:

```yaml
openapi: 3.0.3
info:
  title: ReqogniLoom — Navigation Visibility
  version: "1.0.0"
  description: |
    Runtime-configurable navigation visibility (Rollenbasierte-Sichten spec,
    sections 3.1 and 6). Which ROLE may see which navigation entry is data;
    which PAGES exist stays code (the frontend `NAV_ITEMS` catalogue).

    NOT A SECURITY MECHANISM. Hiding a navigation entry does not prevent a
    direct URL call to the route behind it — the server-side RBAC check on the
    route/API remains the only access gate. A `required_role` set to `null` by
    mistake makes a link visible that the server then rejects: a UX defect, not
    a hole.
paths:
  /api/v1/navigation-visibility-defaults/:
    get:
      summary: Read the tenant-wide default map
      description: Any authenticated role. Seeds the row on first read.
      responses:
        "200":
          description: The tenant default
          content:
            application/json:
              schema: { $ref: "#/components/schemas/GlobalNavigationVisibility" }
    put:
      summary: Replace the tenant-wide default map
      description: |
        Admin only. Full replace, then propagation into every workspace row
        that is still `is_customized: false`. The response reports how many
        rows were updated in `propagated`.
      requestBody:
        required: true
        content:
          application/json:
            schema: { $ref: "#/components/schemas/VisibilityBody" }
      responses:
        "200":
          description: The updated tenant default
          content:
            application/json:
              schema: { $ref: "#/components/schemas/GlobalNavigationVisibility" }
        "400": { description: Malformed key or unknown role }
        "403": { description: Admin role required }
  /api/v1/workspaces/{workspace_id}/navigation-visibility/:
    parameters:
      - name: workspace_id
        in: path
        required: true
        schema: { type: string, format: uuid }
    get:
      summary: Read the resolved map for a workspace
      description: |
        Any authenticated role — this is what the sidebar reads on every
        render. Materializes the row from the tenant default on first read.
      responses:
        "200":
          description: The resolved workspace map
          content:
            application/json:
              schema:
                { $ref: "#/components/schemas/WorkspaceNavigationVisibility" }
    put:
      summary: Override the map for a workspace
      description: Admin only. Sets `is_customized: true`.
      requestBody:
        required: true
        content:
          application/json:
            schema: { $ref: "#/components/schemas/VisibilityBody" }
      responses:
        "200":
          description: The updated workspace override
          content:
            application/json:
              schema:
                { $ref: "#/components/schemas/WorkspaceNavigationVisibility" }
        "400": { description: Malformed key or unknown role }
        "403": { description: Admin role required }
  /api/v1/workspaces/{workspace_id}/navigation-visibility/reset/:
    parameters:
      - name: workspace_id
        in: path
        required: true
        schema: { type: string, format: uuid }
    post:
      summary: Reset a workspace back to the tenant default
      description: Admin only. Copies `source_global` back in and clears the flag.
      responses:
        "200":
          description: The restored workspace row
          content:
            application/json:
              schema:
                { $ref: "#/components/schemas/WorkspaceNavigationVisibility" }
        "403": { description: Admin role required }
        "409": { description: The workspace has no global source to reset to }
components:
  schemas:
    VisibilityMap:
      type: object
      description: |
        `{nav_item_key: required_role | null}`. A key that is ABSENT requires
        no role. Keys must match `^[a-z0-9][a-z0-9-]{0,63}$`; a key the sidebar
        does not know is ignored when rendering.
      additionalProperties:
        nullable: true
        type: string
        enum: [admin, editor, approver, viewer]
      example:
        settings: admin
        system-settings: admin
    VisibilityBody:
      type: object
      required: [visibility]
      properties:
        visibility: { $ref: "#/components/schemas/VisibilityMap" }
    GlobalNavigationVisibility:
      type: object
      properties:
        scope: { type: string, enum: [global] }
        tenant_id: { type: string, format: uuid }
        visibility: { $ref: "#/components/schemas/VisibilityMap" }
        version: { type: integer }
        updated_at: { type: string, format: date-time, nullable: true }
        propagated:
          type: integer
          description: PUT response only — derived rows updated by propagation.
    WorkspaceNavigationVisibility:
      type: object
      properties:
        scope: { type: string, enum: [workspace] }
        workspace_id: { type: string, format: uuid }
        visibility: { $ref: "#/components/schemas/VisibilityMap" }
        is_customized: { type: boolean }
        source_global_id: { type: string, format: uuid, nullable: true }
        version: { type: integer }
        updated_at: { type: string, format: date-time, nullable: true }
```

- [ ] **Step 4: Document the three views in the architecture doc**

Append to `docs/ARCHITECTURE.md`:

```markdown
## Rollenbasierte Sichten (Leser / Autor / Experte)

Drei Sichten auf dieselbe Oberfläche, abgeleitet aus den vier bestehenden
Workspace-Rollen. Kein eigenes Rechtesystem — reine UX-Konsequenz der
vorhandenen RBAC-Matrix.

| Sicht | Rollen | Navigation | Formular | Dichte |
|---|---|---|---|---|
| Leser | `viewer` | nur Einträge ohne Rollenanforderung | `read` — keine Schreib-Buttons außer Kommentar, Export, Impact-Analyse | Expert-Sektionen eingeklappt |
| Autor | `editor` | zusätzlich `editor`-Einträge | `edit`, außer in eingefrorenen Workflow-Zuständen | Expert-Sektionen eingeklappt |
| Experte | `admin`, `approver` | alle konfigurierten Einträge | wie Autor | Expertenmodus-Schalter klappt Expert-Sektionen auf |

**Navigations-Sichtbarkeit ist Konfiguration, kein Code.**
`GlobalNavigationVisibility` (Mandanten-Standard) und
`WorkspaceNavigationVisibility` (Workspace-Override, materialisierte Kopie mit
`is_customized`) speichern eine Map `{nav_item_key: required_role | null}`.
Editor: `/system-settings?tab=navigation-visibility` (global) und
`/settings?tab=navigation-visibility` (Workspace). Änderungen wirken ohne
Deploy. Welche **Seiten** existieren, bleibt Code (`NAV_ITEMS`); welche
**Rolle** eine Seite sehen darf, ist Daten.

**Formular-Modus** folgt Rolle UND Workflow-Zustand: ein freigegebenes Artefakt
ist auch für die Autor-Rolle schreibgeschützt; der Status lässt sich weiterhin
über eine explizite Transition ändern, die Felder nicht
(`ArtifactForm/form-mode.ts`).

**`audience` und Expertenmodus sind Anzeigedichte, keine Sicherheitsgrenze.**
`audience: "expert"` klappt eine Sektion standardmäßig **ein** (nicht aus —
Sichtbarkeit bleibt `visible`), der Expertenmodus-Schalter
(`User.expert_mode_enabled`, nur für `admin`/`approver` sichtbar) klappt sie
auf. Der Schalter zeigt mehr, gibt aber keine zusätzlichen Rechte.

**Keine dieser Ebenen ersetzt die Zugriffskontrolle.** Ein ausgeblendeter
Navigationseintrag verhindert nicht den direkten URL-Aufruf; die serverseitige
RBAC-Prüfung auf Route und API bleibt das einzige Gate.
```

- [ ] **Step 5: Run the full backend and frontend suites for the touched areas**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -e DB_NAME=test_rbsichten backend-test pytest auth_tenancy/ rest_api/ persistence/tests/test_rls_coverage.py -v --create-db`
Expected: PASS with no new failures

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm frontend-test sh -c "npm install && npx vitest run --testTimeout=30000"`
Expected: only the ~14 pre-existing local failures (green in CI); no new ones

- [ ] **Step 6: Commit**

```bash
git add docs/api/navigation-visibility.openapi.yaml docs/ARCHITECTURE.md backend/rest_api/tests/test_navigation_visibility_openapi.py
git commit -m "docs: document the three role-based views and the navigation-visibility API"
```

- [ ] **Step 7: Close GitHub issue #848**

The spec (§Verhältnis zu GitHub-Issue #848, §8) states that #848 — "Viewer sees all write buttons and admin navigation" — is solved structurally by this implementation and must not be worked a second time as a standalone bugfix. It is covered as follows:

* Navigation level — Task 8 (`SidebarNavigation` renders from the resolved map) and Task 9 (the entries are configurable at runtime), replacing the hardcoded `NAV_ITEMS.requires` that commit `54b09760` introduced as the interim fix.
* Form level — Task 12 (`ArtifactForm` derives `mode` from role and workflow state), so a viewer's form is read-only rather than server-rejected on save.
* Button level — Tasks 13 and 14 (create affordances are not rendered, not disabled) across all 15 artifact routes.

Run: `gh issue close 848 --comment "Structurally resolved by the Rollenbasierte-Sichten implementation (docs/superpowers/plans/2026-09-03-rollenbasierte-sichten.md): navigation visibility is now runtime-configurable data instead of a hardcoded requires field (Tasks 8-9), ArtifactForm derives its read/edit mode from role plus workflow state (Task 12), and every create affordance is filtered out for roles that may not use it rather than disabled (Tasks 13-14). Superseded the interim hardcoded gate from 54b09760."`

---

## Rollout notes

**Order.** Phases A, B, C and E are independent of the other specs in this series and can ship in any order. Phase D **must** follow the Attribute-Definition plan's Task 18 (`ArtifactForm.tsx` does not exist before it — precondition P2).

**Deferred, tracked here so it is not lost:**

* **Leser default entry (spec §3.2).** The Dokument-Lesemodus (`/documents/<id>/read`, Dokumentensicht spec §4) is meant to be the viewer's landing page instead of the split-view form. That route does not exist and Dokumentensicht has no plan yet, so no task is spent on it. When the Dokumentensicht plan lands, add the redirect there — it is one constant plus one `<Navigate>` in `NavigationShell`, gated on `hasRole('editor') === false`. Until then the viewer lands on the dashboard, which is the current behaviour.
* **Kommentar as the Leser's only write action (spec §3.2).** Comments come from the Menschen-im-System plan (#6 in the series). Its comment affordance must NOT carry `requiresRole: "editor"` — a viewer commenting is the explicit exception in this spec. Noted here because that plan's author will otherwise copy the `requiresRole` idiom from its neighbours.
* **`audience` curation (spec §8).** Nothing is `audience: "expert"` after this plan ships; every section stays expanded until a tenant admin marks sections deliberately in the Attribute Editor. That is the safe default, but it also means the expert mode has no visible effect until someone curates. Mention it in the release notes, do not "fix" it by guessing a default assignment.

**Known ceiling, named on purpose:** the frozen-state heuristic in `form-mode.ts` (decision D5). If a workspace renames its approved state to something the fragment list does not cover, direct editing stays available there — a UX regression, not a security one, since the server never enforced the freeze in the first place. The upgrade path is a per-state `frozen` flag in `workflow_json` plus a checkbox in the existing Workflow Editor.

**Not a security change.** None of this plan alters an access decision. Every gate it adds is a display decision on top of the unchanged server-side RBAC. A reviewer who reads it as hardening should reject that framing: the value here is that a viewer stops being offered actions that would fail, not that anything newly becomes impossible.

