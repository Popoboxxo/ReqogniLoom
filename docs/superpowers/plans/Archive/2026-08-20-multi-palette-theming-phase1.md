# Multi-Palette Theming — Phase 1 (Theme Registry Mechanics + Settings UI + Persistence) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every workspace a persisted, admin-configurable default theme
(`dark`/`light` today, extensible later) and let a signed-in user's own
session-local pick override it — exactly the same workspace-default +
user-override architecture the codebase already uses for `language`.

**Architecture:** `theme` is stored in the `Workspace.preset` JSON blob
(no DB migration — identical to how `language` is already stored there,
NOT in the dedicated-but-unused `language` model column). The frontend
`WorkspaceContext` gains a `hasLocalThemeOverride` flag and a restore
`useEffect` that calls `useTheme().setTheme(...)` from the active
workspace, mirroring the existing language-restore effect line-for-line.
`WorkspaceSettings.tsx` gets a Theme radiobutton section mirroring the
existing Language section. No new color values, no new palette, no
ESLint/ratchet changes — those are separate, later phases (see
`docs/superpowers/specs/2026-08-20-multi-palette-theming-design.md` §5).

**Tech Stack:** Django 4.2 / DRF (backend), React 18 + TypeScript 5.5 +
Vitest (frontend). No new dependencies.

**Spec:** `docs/superpowers/specs/2026-08-20-multi-palette-theming-design.md`

## Global Constraints

- No DB migration in this phase — `theme` lives in the existing `preset`
  JSONField, exactly like `language` (backend/persistence/models.py:611-621,
  the dedicated `language` column is legacy/unused per
  `WorkspaceSerializer`'s own docstring — do not touch it, do not add a
  dedicated `theme` column).
- Backend must NOT validate `theme` against a closed set of ids — `Theme` is
  a deliberately open string type on the frontend
  (`frontend/src/context/ThemeContext.tsx:33`); only sanitize + cap length,
  identical to how `language` is handled.
- Every new i18n key added must exist in BOTH `de.json` and `en.json` in the
  same commit (`i18n-parity.test.ts` fails the build otherwise).
- Commit after each task (user's standing instruction: every intermediate
  state gets saved).

---

### Task 1: Backend — persist `theme` on the workspace preset blob

**Files:**
- Modify: `backend/application/workspace_service.py:69` (constants block),
  `backend/application/workspace_service.py:567-646` (`update_metadata`)
- Test: `backend/application/tests/test_service_boundaries_req066.py`

**Interfaces:**
- Produces: `WorkspaceService.update_metadata(ctx, workspace_id, *, theme: object = _UNSET, ...) -> Workspace` — on success, `result.preset["theme"] == <sanitized value>`.

- [ ] **Step 1: Write the failing test**

Add to `backend/application/tests/test_service_boundaries_req066.py`, right
after `test_language_stored_on_preset_blob` (line 392-393):

```python
    def test_theme_stored_on_preset_blob(self):
        tenant, user = _tenant_user("ws")
        ws = _workspace(tenant)
        ctx = _make_ctx(tenant_id=tenant.id, user_id=user.id)
        result = WorkspaceService().update_metadata(ctx, ws.id, theme="light")
        assert result.preset.get("theme") == "light"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && DB_USER=postgres pytest application/tests/test_service_boundaries_req066.py::TestUpdateMetadata::test_theme_stored_on_preset_blob -v`

(Adjust the exact test class name to whatever wraps `test_language_stored_on_preset_blob` in that file if it differs from `TestUpdateMetadata` — check with `grep -n "^class" backend/application/tests/test_service_boundaries_req066.py`.)

Expected: FAIL with `TypeError: update_metadata() got an unexpected keyword argument 'theme'`.

- [ ] **Step 3: Write minimal implementation**

In `backend/application/workspace_service.py`, add the constant next to the
other `_MAX_LENGTH` constants (line 69):

```python
_LANGUAGE_MAX_LENGTH = 8
_THEME_MAX_LENGTH = 32
```

Add `theme: object = _UNSET` to the `update_metadata` signature (alongside
`language: object = _UNSET` at line 574), and add this block right after the
existing `language` handling block (after line 618, before the
`decomposition_link_type` block):

```python
        if theme is not _UNSET:
            clean_theme = _sanitize_and_cap(
                str(theme), max_length=_THEME_MAX_LENGTH, field_name="theme"
            )
            preset_blob["theme"] = clean_theme
            ws.preset = preset_blob
            if "preset" not in update_fields:
                update_fields.append("preset")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && DB_USER=postgres pytest application/tests/test_service_boundaries_req066.py -k theme -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/application/workspace_service.py backend/application/tests/test_service_boundaries_req066.py
git commit -m "feat: persist workspace-default theme on preset blob"
```

---

### Task 2: Backend — expose `theme` over the REST API

**Files:**
- Modify: `backend/rest_api/serializers.py:1107` (`WorkspaceSerializer`)
- Modify: `backend/rest_api/views.py:3991` (`_workspace_to_dict`)
- Modify: `backend/rest_api/views.py:4256-4264` (accepted PATCH fields)
- Test: new file `backend/rest_api/tests/test_workspace_theme_api.py`

**Interfaces:**
- Consumes: `WorkspaceService.update_metadata(..., theme=...)` from Task 1.
- Produces: `GET/PATCH /api/v1/workspaces/{id}/` response now includes
  `"theme": "<id>"` (default `"dark"`, matching
  `ThemeContext.tsx`'s `FALLBACK_THEME`).

- [ ] **Step 1: Write the failing test**

Create `backend/rest_api/tests/test_workspace_theme_api.py`:

```python
"""API test for workspace-default theme persistence (multi-palette theming, #568 phase 1)."""
import pytest
from rest_framework.test import APIClient

from auth_tenancy.models import Tenant
from persistence.models import Workspace


@pytest.mark.django_db
class TestWorkspaceThemeApi:
    def test_patch_theme_persists_and_is_returned(self, django_user_model):
        tenant = Tenant.objects.create(name="theme-api-tenant")
        user = django_user_model.objects.create_user(
            username="theme-api-user", password="pw12345!", tenant_id=tenant.id
        )
        ws = Workspace.objects.create(
            name="Theme API WS", tenant_id=tenant.id, preset={"tier": "standard"}
        )
        client = APIClient()
        client.force_authenticate(user=user)

        resp = client.patch(f"/api/v1/workspaces/{ws.id}/", {"theme": "light"}, format="json")
        assert resp.status_code == 200
        assert resp.data["theme"] == "light"

        resp = client.get(f"/api/v1/workspaces/{ws.id}/")
        assert resp.status_code == 200
        assert resp.data["theme"] == "light"

    def test_default_theme_is_dark_when_unset(self, django_user_model):
        tenant = Tenant.objects.create(name="theme-default-tenant")
        user = django_user_model.objects.create_user(
            username="theme-default-user", password="pw12345!", tenant_id=tenant.id
        )
        ws = Workspace.objects.create(
            name="Theme Default WS", tenant_id=tenant.id, preset={"tier": "standard"}
        )
        client = APIClient()
        client.force_authenticate(user=user)

        resp = client.get(f"/api/v1/workspaces/{ws.id}/")
        assert resp.status_code == 200
        assert resp.data["theme"] == "dark"
```

(Match the existing `Tenant`/`django_user_model`/`force_authenticate` setup
pattern used by neighboring files in `backend/rest_api/tests/` — if any of
those three calls need adjusting to match the exact tenant/auth fixtures
this codebase uses elsewhere in `test_workspace_*` files, mirror whichever
existing workspace API test file follows that pattern instead of inventing
a new one.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && DB_USER=postgres pytest rest_api/tests/test_workspace_theme_api.py -v`

Expected: FAIL — `resp.data` has no `"theme"` key (`KeyError`), since the
serializer doesn't declare it yet.

- [ ] **Step 3: Write minimal implementation**

In `backend/rest_api/serializers.py`, add right after the `language` field
(line 1107):

```python
    language = serializers.CharField(required=False, default="en", max_length=8)
    theme = serializers.CharField(required=False, default="dark", max_length=32)
```

In `backend/rest_api/views.py`, `_workspace_to_dict()` (around line 3991),
add right after the `language` line:

```python
        "language": (ws.preset or {}).get("language", "de"),  # REQ-013: language stored in preset blob
        "theme": (ws.preset or {}).get("theme", "dark"),  # #568: theme stored in preset blob, mirrors language
```

In `backend/rest_api/views.py`, the accepted-fields tuple in the PATCH
handler (around line 4256-4264), add `"theme"`:

```python
                for key in (
                    "name",
                    "language",
                    "theme",
                    "decomposition_link_type",
                    "default_link_type",
                    "terminology_profile",
                    "goals_enabled",
                    "goals_ai_enabled",
                )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && DB_USER=postgres pytest rest_api/tests/test_workspace_theme_api.py -v`

Expected: PASS.

- [ ] **Step 5: Run the full backend test suite to check for regressions**

Run: `cd backend && DB_USER=postgres pytest application/tests/test_service_boundaries_req066.py rest_api/tests/test_workspace_theme_api.py rest_api/tests/ -k workspace -v`

Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/rest_api/serializers.py backend/rest_api/views.py backend/rest_api/tests/test_workspace_theme_api.py
git commit -m "feat: expose workspace theme field over the REST API"
```

---

### Task 3: Frontend — `theme` on the `Workspace` type and API client

**Files:**
- Modify: `frontend/src/types/index.ts:36-59` (`Workspace` interface)
- Modify: `frontend/src/context/WorkspaceContext.tsx:126-137` (`DEFAULT_WORKSPACE`)
- Modify: `frontend/src/api/workspaces.ts:38-49` (`update()` payload type)

**Interfaces:**
- Consumes: backend `theme` field from Task 2 (string, default `"dark"`).
- Produces: `Workspace.theme: string`, `workspacesApi.update(id, { theme })`.

- [ ] **Step 1: Add `theme` to the `Workspace` interface**

In `frontend/src/types/index.ts`, add right after `language: string;`
(line 40):

```ts
  language: string;
  /** Workspace-default theme id (multi-palette theming, #568). Matches a
   *  `ThemeDefinition.id` from `context/ThemeContext.tsx`'s `THEMES`
   *  registry; defaults to `"dark"` server-side. */
  theme: string;
```

- [ ] **Step 2: Add `theme` to `DEFAULT_WORKSPACE`**

In `frontend/src/context/WorkspaceContext.tsx`, add to the object literal
(line 126-137):

```ts
export const DEFAULT_WORKSPACE: Workspace = {
  id: _storedWorkspaceId ?? "00000000-0000-0000-0000-000000000000",
  name: "",
  preset: "standard",
  terminology_profile: "se_mode",
  language: "en",
  theme: "dark",
  is_active: true,
  ...
```

- [ ] **Step 3: Add `theme` to the `update()` payload type**

In `frontend/src/api/workspaces.ts`, add to the `Partial<{...}>` type
(line 38-49):

```ts
  update(
    id: UUID,
    data: Partial<{
      name: string;
      language: string;
      theme: string;
      terminology_profile: TerminologyProfile;
      decomposition_link_type: string;
      default_link_type: string;
      ai_prompts: Record<string, string>;
      goals_enabled: boolean;
      goals_ai_enabled: boolean;
    }>
  ): Promise<Workspace> {
```

- [ ] **Step 4: Type-check**

Run: `cd frontend && npx tsc --noEmit`

Expected: no new errors. (Existing call sites that construct a `Workspace`
object — e.g. test fixtures — will now be missing the required `theme`
field; Step 5 fixes those.)

- [ ] **Step 5: Fix any test fixtures the compiler flags**

Run: `cd frontend && npx tsc --noEmit 2>&1 | grep -i "workspace"` and add
`theme: "dark",` to every object-literal `Workspace` fixture the compiler
flags as missing the property (mirror how each fixture already sets
`language: "en"` or similar — same object, one more field).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/context/WorkspaceContext.tsx frontend/src/api/workspaces.ts
git commit -m "feat: add theme field to Workspace type and API client"
```

(If Step 5 touched additional test files, `git add` those too before
committing — list them explicitly, do not use `git add -A`.)

---

### Task 4: Frontend — workspace-default theme restore + local-override guard

**Files:**
- Modify: `frontend/src/context/WorkspaceContext.tsx`
- Modify: `frontend/src/components/NavigationShell/SidebarNavigation.tsx`
- Test: create `frontend/src/test/workspace-theme-persistence.test.tsx`

**Interfaces:**
- Consumes: `useTheme()` from `frontend/src/context/ThemeContext.tsx`
  (`{ theme: string, setTheme: (t: string) => void }`); `Workspace.theme`
  from Task 3.
- Produces: `WorkspaceState.markThemeOverrideActive: () => void` (new
  context API), consumed by the sidebar toggle in this same task.

This task is a mirror of the existing `hasLocalLanguageOverride` /
`markLanguageOverrideActive` / language-restore-`useEffect` mechanism
already in `WorkspaceContext.tsx` (lines 99-323, and its dedicated
regression-test file `frontend/src/test/workspace-language-persistence.test.tsx`)
— same bug class (BUG-01 / F-04-Residual / R-02), same fix shape, applied
to `theme` instead of `language`.

**Deliberate scope reduction vs. the language mechanism:** the sidebar's
quick theme toggle (`data-testid="theme-toggle"`,
`SidebarNavigation.tsx:663-669`) stays exactly what it is today — a
personal, client-only preference that never calls
`workspacesApi.update()` and is not admin-gated. It is NOT being changed
into a shared, persisted, PATCH-backed control the way the language
toggle is. That means the language mechanism's F-02 (admin-only gate +
notice) and F-04 (PATCH-failure notice) pieces do not apply here — there
is no PATCH to gate or fail. Only the parts that DO apply are built:
restoring the workspace-default on load (BUG-01), a local toggle
surviving an unrelated `reloadWorkspaces()` (F-04-Residual), and clearing
the override on logout (R-02).

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/test/workspace-theme-persistence.test.tsx`:

```tsx
/**
 * ARCH-L1-001 ReactFrontend — Workspace theme persistence (#568 phase 1).
 *
 * Mirrors workspace-language-persistence.test.tsx's BUG-01/F-04-Residual/R-02
 * coverage, applied to `theme` instead of `language`. Unlike language, the
 * sidebar's quick theme toggle is deliberately NOT admin-gated and does NOT
 * PATCH the backend — a personal, client-only preference (unchanged from its
 * pre-#568 behavior) — so the F-02/F-04 notice-and-admin-gate machinery the
 * language toggle needed does not apply here. What DOES apply, and is
 * covered below: the workspace-default theme is restored on load (BUG-01),
 * a session-local toggle choice survives an unrelated reloadWorkspaces()
 * call (F-04-Residual), and it is cleared on logout (R-02).
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { AuthProvider, useAuth } from "../context/AuthContext";
import { WorkspaceProvider, useWorkspace } from "../context/WorkspaceContext";
import { ThemeProvider } from "../context/ThemeContext";
import { SidebarNavigation } from "../components/NavigationShell/SidebarNavigation";
import { workspacesApi } from "../api/workspaces";
import type { Workspace } from "../types";

vi.mock("../api/preferences", () => ({
  preferencesApi: {
    get: vi.fn(async () => null),
    update: vi.fn(async () => ({})),
  },
  OPTIONAL_FEATURES: ["adr", "risk", "issue", "diagrams", "icds", "metrics"] as const,
}));

vi.mock("../api/search", () => ({
  searchApi: { search: vi.fn(async () => ({ results: [], total_count: 0, page: 1, limit: 10, query: "" })) },
}));

vi.mock("../api/version", () => ({
  versionApi: { getVersion: vi.fn(async () => ({ app_version: "0.0.0", commit_short: "abc" })) },
}));

let nextListResult: unknown = { count: 0, next: null, previous: null, results: [] };

vi.mock("../api/workspaces", () => ({
  workspacesApi: {
    list: vi.fn(async () => nextListResult),
    create: vi.fn(),
    update: vi.fn(),
    setPreset: vi.fn(),
    closeWorkspace: vi.fn(),
    reactivateWorkspace: vi.fn(),
    deleteWorkspace: vi.fn(),
  },
}));

function stubAuthFetch(roles: string[]): void {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => ({
        user: { id: "u-1", username: "tester", email: "t@x", first_name: "", last_name: "", is_active: true, tenant_id: null, roles },
        tenant_id: null,
        roles,
      }),
    }) as unknown as Response)
  );
}

function setListWorkspace(theme: string): void {
  const ws: Partial<Workspace> = {
    id: "ws-test",
    name: "Test",
    preset: "standard",
    terminology_profile: "se_mode",
    language: "en",
    theme,
    is_active: true,
    closed_at: null,
    closed_by: null,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  };
  nextListResult = { count: 1, next: null, previous: null, results: [ws] };
}

function renderApp(): ReturnType<typeof render> {
  return render(
    <MemoryRouter>
      <AuthProvider>
        <ThemeProvider>
          <WorkspaceProvider>
            <SidebarNavigation />
          </WorkspaceProvider>
        </ThemeProvider>
      </AuthProvider>
    </MemoryRouter>
  );
}

function IndependentReloadTrigger(): JSX.Element {
  const { activeWorkspace, reloadWorkspaces } = useWorkspace();
  return (
    <button
      data-testid="independent-reload-trigger"
      onClick={() => void reloadWorkspaces(activeWorkspace?.id)}
    >
      trigger unrelated reload
    </button>
  );
}

function renderAppWithIndependentReloadTrigger(): ReturnType<typeof render> {
  return render(
    <MemoryRouter>
      <AuthProvider>
        <ThemeProvider>
          <WorkspaceProvider>
            <SidebarNavigation />
            <IndependentReloadTrigger />
          </WorkspaceProvider>
        </ThemeProvider>
      </AuthProvider>
    </MemoryRouter>
  );
}

function AuthSwitchHarness(): JSX.Element {
  const { logout, login } = useAuth();
  return (
    <>
      <button data-testid="test-logout-trigger" onClick={() => logout()}>logout</button>
      <button data-testid="test-login-trigger" onClick={() => void login({ username: "user-b", password: "irrelevant" })}>login</button>
    </>
  );
}

function renderAppWithAuthSwitch(): ReturnType<typeof render> {
  return render(
    <MemoryRouter>
      <AuthProvider>
        <ThemeProvider>
          <WorkspaceProvider>
            <SidebarNavigation />
            <AuthSwitchHarness />
          </WorkspaceProvider>
        </ThemeProvider>
      </AuthProvider>
    </MemoryRouter>
  );
}

function installLocalStorageStub(): void {
  const store = new Map<string, string>();
  Object.defineProperty(window, "localStorage", {
    configurable: true,
    value: {
      getItem: (key: string) => store.get(key) ?? null,
      setItem: (key: string, value: string) => void store.set(key, value),
      removeItem: (key: string) => void store.delete(key),
      clear: () => store.clear(),
    },
  });
}

describe("Workspace theme restore on load (#568)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    installLocalStorageStub();
    sessionStorage.clear();
    stubAuthFetch(["viewer"]);
  });

  it("applies the workspace-default theme even though the local default is dark", async () => {
    setListWorkspace("light");
    renderApp();

    await waitFor(() => {
      expect(screen.getByText("Dashboard")).toBeInTheDocument();
    });
    await waitFor(() => {
      expect(document.documentElement.dataset.theme).toBe("light");
    });
  });
});

describe("Local theme toggle survives an unrelated reloadWorkspaces() call (#568)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    installLocalStorageStub();
    sessionStorage.clear();
    stubAuthFetch(["viewer"]);
  });

  it("keeps a manually-toggled theme after an unrelated reload re-fetches the workspace-default", async () => {
    setListWorkspace("light");
    renderAppWithIndependentReloadTrigger();

    await waitFor(() => expect(document.documentElement.dataset.theme).toBe("light"));

    fireEvent.click(await screen.findByTestId("theme-toggle"));
    await waitFor(() => expect(document.documentElement.dataset.theme).toBe("dark"));

    fireEvent.click(screen.getByTestId("independent-reload-trigger"));
    await waitFor(() => {
      expect(workspacesApi.list).toHaveBeenCalledTimes(2);
    });

    expect(document.documentElement.dataset.theme).toBe("dark");
  });
});

describe("Logout clears a local/unpersisted theme override (#568, mirrors R-02)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    installLocalStorageStub();
    sessionStorage.clear();
  });

  it("a re-login in the same tab follows the newly loaded workspace's theme, not a stale override", async () => {
    stubAuthFetch(["viewer"]);
    setListWorkspace("light");
    renderAppWithAuthSwitch();

    await waitFor(() => expect(document.documentElement.dataset.theme).toBe("light"));
    fireEvent.click(await screen.findByTestId("theme-toggle"));
    await waitFor(() => expect(document.documentElement.dataset.theme).toBe("dark"));

    fireEvent.click(screen.getByTestId("test-logout-trigger"));
    fireEvent.click(screen.getByTestId("test-login-trigger"));

    await waitFor(() => {
      expect(screen.getByText("Dashboard")).toBeInTheDocument();
    });
    await waitFor(() => {
      expect(document.documentElement.dataset.theme).toBe("light");
    });
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx vitest run src/test/workspace-theme-persistence.test.tsx`

Expected: all 3 FAIL — `document.documentElement.dataset.theme` never
becomes `"light"` (no restore effect exists yet), and the second/third
tests additionally fail because nothing marks a local override, so the
manually-toggled `"dark"` gets silently reverted once the restore effect
IS added in a naive form without the guard (make sure to observe THIS
specific failure mode after Step 3's first half, before adding the guard —
see the note in Step 3).

- [ ] **Step 3: Write minimal implementation**

In `frontend/src/context/WorkspaceContext.tsx`:

Add the import:

```ts
import { useTheme } from "./ThemeContext";
```

Add to the `WorkspaceState` interface (after `clearLanguageOverride` at
line 107):

```ts
  markThemeOverrideActive: () => void;
```

Inside `WorkspaceProvider`, add state + callback (after the
`hasLocalLanguageOverride` block, lines 193-200):

```ts
  const [hasLocalThemeOverride, setHasLocalThemeOverride] =
    useState<boolean>(false);
  const markThemeOverrideActive = useCallback((): void => {
    setHasLocalThemeOverride(true);
  }, []);
  const { setTheme } = useTheme();
```

In `setActiveWorkspace` (lines 202-211), reset the theme override alongside
the language one:

```ts
  const setActiveWorkspace = useCallback((ws: Workspace | null) => {
    setActiveWorkspaceState(ws);
    setHasLocalLanguageOverride(false);
    setHasLocalThemeOverride(false);
    if (ws && typeof sessionStorage !== "undefined") {
      sessionStorage.setItem("reqflow_workspace_id", ws.id);
    }
  }, []);
```

In the logout branch of the bootstrap effect (lines 248-261), reset it
there too (this is what R-02's mirror test in Step 1 verifies):

```ts
      setHasLocalLanguageOverride(false);
      setHasLocalThemeOverride(false);
      return;
```

Add a new restore effect right after the existing language-restore effect
(after line 323):

```ts
  // Theme mirror of the language-restore effect immediately above — same
  // BUG-01/F-04-Residual shape, applied to `theme` (#568 phase 1).
  useEffect(() => {
    if (!isWorkspaceReady) return;
    if (activeWorkspace === DEFAULT_WORKSPACE) return;
    if (hasLocalThemeOverride) return;
    const nextTheme = activeWorkspace?.theme;
    if (!nextTheme) return;
    setTheme(nextTheme);
  }, [isWorkspaceReady, activeWorkspace, hasLocalThemeOverride, setTheme]);
```

Add `markThemeOverrideActive` to the context value object (find the
`markLanguageOverrideActive,` entries at lines 526 and 543 — add
`markThemeOverrideActive,` next to each, including the surrounding
`useMemo` dependency array).

In `frontend/src/components/NavigationShell/SidebarNavigation.tsx`, add
`markThemeOverrideActive` to the `useWorkspace()` destructure (mirroring
line 120's `markLanguageOverrideActive,`), and change the toggle button's
handler (line 664) from:

```tsx
          onClick={toggleTheme}
```

to:

```tsx
          onClick={() => {
            markThemeOverrideActive();
            toggleTheme();
          }}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/test/workspace-theme-persistence.test.tsx`

Expected: all 3 PASS.

- [ ] **Step 5: Run the full WorkspaceContext and SidebarNavigation test files to check for regressions**

Run: `cd frontend && npx vitest run src/test/WorkspaceContext.test.tsx src/test/SidebarNavigation.test.tsx src/test/workspace-language-persistence.test.tsx`

Expected: all PASS — in particular every existing language-persistence
test must remain green, since the new theme-restore effect runs
independently of it.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/context/WorkspaceContext.tsx frontend/src/components/NavigationShell/SidebarNavigation.tsx frontend/src/test/workspace-theme-persistence.test.tsx
git commit -m "feat: restore workspace-default theme with local-override guard"
```

---

### Task 5: Frontend — Theme section in Workspace Settings (admin default)

**Files:**
- Modify: `frontend/src/components/WorkspaceSettings/WorkspaceSettings.tsx`
- Modify: `frontend/src/i18n/locales/de.json`, `frontend/src/i18n/locales/en.json`
- Test: `frontend/src/components/WorkspaceSettings/WorkspaceSettings.test.tsx`

**Interfaces:**
- Consumes: `workspacesApi.update(id, { theme })` (Task 3),
  `THEMES` registry from `ThemeContext.tsx` (existing, 2 entries:
  `dark`/`light`).
- Produces: an admin-facing radiobutton group that sets the workspace's
  default theme, in the same `general` tab as the existing Language
  section.

- [ ] **Step 1: Write the failing test**

`WorkspaceSettings.test.tsx` mocks `../../context/WorkspaceContext` and
`../../context/AuthContext` already (lines 39-49) but does not yet mock
`../../context/ThemeContext` — add that mock block right after the
`AuthContext` mock (after line 49):

```tsx
vi.mock("../../context/ThemeContext", () => ({
  useTheme: () => ({ setTheme: vi.fn() }),
  THEMES: [
    { id: "dark", labelKey: "nav.darkMode" },
    { id: "light", labelKey: "nav.lightMode" },
  ],
}));
```

Add the import at the top of the file, alongside the existing
`WorkspaceSettings` import (line 12):

```tsx
import { workspacesApi } from "../../api/workspaces";
```

Add `theme: "dark"` to the `activeWorkspace` fixture object (line 29-37,
alongside the existing `language: "de",`):

```tsx
const activeWorkspace = {
  id: "ws-1",
  name: "Demo Workspace",
  preset: "standard",
  terminology_profile: "dev_mode",
  language: "de",
  theme: "dark",
  decomposition_link_type: "parent-child",
  is_active: true,
};
```

Add a new test to the `"WorkspaceSettings tabs (REQ-015)"` describe block
(after the existing tab-switching tests, e.g. after line 134):

```tsx
  it("lets an admin change the workspace-default theme (#568)", async () => {
    render(<WorkspaceSettings />);
    await userEvent.click(screen.getByTestId("theme-option-light"));
    expect(workspacesApi.update).toHaveBeenCalledWith("ws-1", { theme: "light" });
  });
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/components/WorkspaceSettings/WorkspaceSettings.test.tsx -t "workspace-default theme"`

Expected: FAIL — no `theme-option-light` testid exists yet.

- [ ] **Step 3: Add the i18n keys**

In `frontend/src/i18n/locales/de.json`, inside the `"settings"` block, add
right after `"language": "Sprache",` (line 595):

```json
    "language": "Sprache",
    "theme": "Theme",
    "themeDark": "Dunkel",
    "themeLight": "Hell",
```

In `frontend/src/i18n/locales/en.json`, at the same position (line 595):

```json
    "language": "Language",
    "theme": "Theme",
    "themeDark": "Dark",
    "themeLight": "Light",
```

- [ ] **Step 4: Write minimal implementation**

In `frontend/src/components/WorkspaceSettings/WorkspaceSettings.tsx`, add a
`handleThemeChange` callback right after `handleLanguageChange` (after line
136), reusing the already-imported `useTheme` hook:

```tsx
  const { setTheme } = useTheme();

  const handleThemeChange = useCallback(async (nextTheme: string): Promise<void> => {
    setTheme(nextTheme);
    if (!activeWorkspace || nextTheme === activeWorkspace.theme) return;
    setSaveError(null);
    setSavedOk(false);
    try {
      await workspacesApi.update(activeWorkspace.id, { theme: nextTheme });
      await reloadWorkspaces(activeWorkspace.id);
      setSavedOk(true);
    } catch (err: unknown) {
      setSaveError((err as { error?: { message?: string } })?.error?.message ?? String(err));
    }
  }, [activeWorkspace, reloadWorkspaces, setTheme]);
```

Add the import at the top of the file (alongside the other context
imports, near line 27-28):

```tsx
import { useTheme, THEMES } from "../../context/ThemeContext";
```

Add a Theme section in the `general` tab, right after the Language section
(after line 433, before the "Ziele" section):

```tsx
            {/* Theme (#568 phase 1) */}
            <section style={cardStyle}>
              <h3 style={headingStyle}>{t("settings.theme")}</h3>
              {THEMES.map((themeDef) => (
                <label key={themeDef.id} style={{ ...labelStyle, marginBottom: "var(--space-1)" }}>
                  <input
                    type="radio"
                    name="theme"
                    value={themeDef.id}
                    checked={(activeWorkspace.theme ?? "dark") === themeDef.id}
                    onChange={() => void handleThemeChange(themeDef.id)}
                    data-testid={`theme-option-${themeDef.id}`}
                  />
                  {themeDef.id === "dark" ? t("settings.themeDark") : t("settings.themeLight")}
                </label>
              ))}
            </section>
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/components/WorkspaceSettings/WorkspaceSettings.test.tsx -t "workspace-default theme"`

Expected: PASS.

- [ ] **Step 6: Run the i18n parity test**

Run: `cd frontend && npx vitest run src/test/i18n-parity.test.ts`

Expected: PASS (both new keys exist in both locale files).

- [ ] **Step 7: Run the full WorkspaceSettings test file to check for regressions**

Run: `cd frontend && npx vitest run src/components/WorkspaceSettings/WorkspaceSettings.test.tsx`

Expected: all PASS.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/components/WorkspaceSettings/WorkspaceSettings.tsx frontend/src/components/WorkspaceSettings/WorkspaceSettings.test.tsx frontend/src/i18n/locales/de.json frontend/src/i18n/locales/en.json
git commit -m "feat: add workspace-default theme selector to Settings UI"
```

---

### Task 6: Full-suite verification and phase close-out

**Files:** none (verification only)

- [ ] **Step 1: Run the full frontend test suite**

Run: `cd frontend && npx vitest run`

Expected: all PASS, no regressions in unrelated files.

- [ ] **Step 2: Run the full frontend type check and lint**

Run: `cd frontend && npx tsc --noEmit && npx eslint src`

Expected: no errors.

- [ ] **Step 3: Run the full backend test suite for the touched apps**

Run: `cd backend && DB_USER=postgres pytest application/ rest_api/ -v`

Expected: all PASS. (Use the superuser `DB_USER` override — plain `pytest`
without it fails every RLS-dependent test in this repo, per this project's
established local-test-run convention.)

- [ ] **Step 4: Manually verify in the running stack (optional but recommended)**

Run: `docker-compose up -d` (if not already running), open the app, go to
Workspace Settings → General tab as an admin, switch the Theme radio, and
confirm: (a) the UI re-themes immediately, (b) a page reload keeps the
picked theme, (c) a different (non-admin) browser/session opening the same
workspace for the first time also gets that theme as its starting point.

- [ ] **Step 5: Update the design spec's status**

In `docs/superpowers/specs/2026-08-20-multi-palette-theming-design.md`,
change the Phase 1 row's status in §5's table (or add a short "Phase 1:
done, see PR <link>" note) so the spec reflects reality for whoever reads
it next — this repo's other specs use exactly this kind of trailing
progress note.

- [ ] **Step 6: Commit and open the PR**

```bash
git add docs/superpowers/specs/2026-08-20-multi-palette-theming-design.md
git commit -m "docs: mark theming Phase 1 (registry + settings UI) complete"
git push -u origin docs/multi-palette-theming-spec
gh pr create --title "feat: workspace-default theme (multi-palette theming Phase 1, #568)" --body "Phase 1 of #568 — see docs/superpowers/specs/2026-08-20-multi-palette-theming-design.md. Adds a persisted, admin-configurable workspace-default theme plus a session-local user override, mirroring the existing language mechanism exactly. No new palette, no color changes, no ESLint/ratchet changes — those are Phase 2/3."
```

(This step is a git mutation — delegate it to the `git` subagent per this
project's `Git Delegation` rule rather than running it directly.)
