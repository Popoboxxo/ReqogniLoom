/**
 * ARCH-L1-001 ReactFrontend — Workspace language persistence regression (BUG-01).
 *
 * leaf_id: COMP-RF-001 (NavigationShell / WorkspaceContext)
 * req_id:  REQ-133 (Workspace language), REQ-L2-RF-001 (i18n DE/EN)
 *
 * SYSTEMAUDIT_2026-08-18 §4 BUG-01: the language switch only affected the
 * current page; after navigating to another route the UI fell back to
 * German. Root cause (verified in code, not the audit's own guess):
 *
 *  1. `frontend/src/i18n/index.ts` seeds `i18n.language` once from
 *     `navigator.language` at module load and is never re-synced from the
 *     persisted `workspace.language` after the real workspace loads — so a
 *     fresh navigation/reload (a real browser navigation, e.g. Playwright's
 *     `page.goto()`, or an actual user reload) always resets the UI to the
 *     browser locale, discarding whatever was persisted via
 *     `PATCH /workspaces/{id}/`.
 *  2. The quick language toggle in the sidebar footer
 *     (`data-testid="lang-switch"`, `SidebarNavigation.handleLanguageToggle`)
 *     never called `PATCH /workspaces/{id}/` at all — unlike the dedicated
 *     radio buttons on the Workspace Settings page — so using the toggle
 *     never persisted anything to begin with.
 *
 * These two tests reproduce both gaps against the *pre-fix* code (both are
 * expected to fail before the fix in WorkspaceContext.tsx / SidebarNavigation.tsx).
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent, cleanup } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { AuthProvider, useAuth } from "../context/AuthContext";
import { WorkspaceProvider, useWorkspace } from "../context/WorkspaceContext";
import { ThemeProvider } from "../context/ThemeContext";
import { SidebarNavigation } from "../components/NavigationShell/SidebarNavigation";
import { i18n } from "../i18n/index";
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

// `nextListResult` is mutable so a test can simulate the backend having
// persisted a prior language change before a simulated reload (a fresh
// `workspacesApi.list()` call, mirroring a new WorkspaceProvider mount).
// `vi.mock` factories are hoisted above imports, so any mock function they
// reference must be created via `vi.hoisted` — a plain top-level `const`
// would be a TDZ reference at the time the factory actually runs.
const { updateMock } = vi.hoisted(() => ({
  updateMock: vi.fn(async (_id: string, data: Record<string, unknown>) => data),
}));

let nextListResult: unknown = { count: 0, next: null, previous: null, results: [] };

vi.mock("../api/workspaces", () => ({
  workspacesApi: {
    list: vi.fn(async () => nextListResult),
    // reloadWorkspaces (Task 1 fix) now calls listAll() instead of list() to
    // avoid silently truncating the workspace switcher to page 1 — mirror
    // the same single-page `nextListResult.results` here for these tests.
    listAll: vi.fn(async () => (nextListResult as { results?: unknown[] }).results ?? []),
    create: vi.fn(),
    update: updateMock,
    setPreset: vi.fn(),
    closeWorkspace: vi.fn(),
    reactivateWorkspace: vi.fn(),
    deleteWorkspace: vi.fn(),
  },
}));

// Reflect a PATCH into the "backend" list result so a subsequent mount (=
// simulated navigation/reload) observes the persisted value, exactly like
// the real PATCH /workspaces/{id}/ + GET /workspaces/ round-trip.
updateMock.mockImplementation(async (_id: string, data: Record<string, unknown>) => {
  const current = nextListResult as { results: Partial<Workspace>[] };
  if (current.results[0] && typeof data.language === "string") {
    current.results[0] = { ...current.results[0], language: data.language };
  }
  return { ...current.results[0] };
});

/** Point the auth-restore fetch stub at a given role set (default: admin). */
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

function setListWorkspace(language: string): void {
  const ws: Partial<Workspace> = {
    id: "ws-test",
    name: "Test",
    preset: "standard",
    terminology_profile: "se_mode",
    language,
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

/**
 * Stand-in for any *unrelated* `reloadWorkspaces()` call site — e.g.
 * `WorkspaceSettings.handlePresetChange`/`handleSaveName` or
 * `WorkspaceAdminSection`'s admin actions all call
 * `reloadWorkspaces(activeWorkspace.id)` after their own PATCH, with nothing
 * to do with the language toggle. Renders a button that fires exactly that
 * call, so a test can reproduce "some other action refreshed the workspace
 * while a local-only/unpersisted language choice was active" (F-04-Residual)
 * without needing to mount the real Settings page and its own API mocks.
 */
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

/**
 * Stand-in for an EXPLICIT workspace switch — e.g. clicking a different
 * workspace in the sidebar's own switcher dropdown
 * (`SidebarNavigation.tsx`'s `setActiveWorkspace(ws)` call). Unlike
 * `IndependentReloadTrigger` above, this is the one action that is allowed
 * to clear a local/unpersisted language override, per the fix's contract.
 */
function ExplicitWorkspaceSwitchTrigger({
  workspace,
}: {
  workspace: Workspace;
}): JSX.Element {
  const { setActiveWorkspace } = useWorkspace();
  return (
    <button
      data-testid="explicit-workspace-switch-trigger"
      onClick={() => setActiveWorkspace(workspace)}
    >
      switch workspace
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

function renderAppWithExplicitSwitch(otherWorkspace: Workspace): ReturnType<typeof render> {
  return render(
    <MemoryRouter>
      <AuthProvider>
        <ThemeProvider>
          <WorkspaceProvider>
            <SidebarNavigation />
            <ExplicitWorkspaceSwitchTrigger workspace={otherWorkspace} />
          </WorkspaceProvider>
        </ThemeProvider>
      </AuthProvider>
    </MemoryRouter>
  );
}

/**
 * Stand-in for a real logout→login cycle in the same tab (R-02):
 * `WorkspaceProvider` also wraps `/login`, and `AuthContext.logout()` does
 * not reload the page, so `isAuthenticated` simply flips false then true
 * again within the same React tree.
 */
function AuthSwitchHarness(): JSX.Element {
  const { logout, login } = useAuth();
  return (
    <>
      <button data-testid="test-logout-trigger" onClick={() => logout()}>
        logout
      </button>
      <button
        data-testid="test-login-trigger"
        onClick={() => void login({ username: "user-b", password: "irrelevant" })}
      >
        login
      </button>
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

// jsdom does not provide window.localStorage in this test runtime; ThemeProvider
// reads it synchronously on mount (see SidebarNavigation.test.tsx for precedent).
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

describe("Workspace language persistence across navigation (BUG-01, REQ-133)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    updateMock.mockClear();
    installLocalStorageStub();
    sessionStorage.clear();
    // jsdom's default navigator.language is "en-US" — start the in-memory
    // i18n singleton on "en" too, so a later assertion that it ends up "de"
    // can only be explained by restoration-from-workspace, not by luck.
    void i18n.changeLanguage("en");
    stubAuthFetch(["admin"]);
  });

  it("restores the persisted workspace language on load, even though the browser default is English", async () => {
    setListWorkspace("de");
    renderApp();

    await waitFor(() => {
      expect(screen.getByText("Dashboard")).toBeInTheDocument();
    });

    await waitFor(() => {
      expect(i18n.language).toBe("de");
    });
  });

  it("persists a language change via the sidebar quick-toggle, and a fresh mount (= navigation/reload) restores it instead of falling back to German", async () => {
    // Start on "de" like a freshly-seeded workspace so the toggle flips it
    // to "en" — matching the audit's exact wording ("fällt auf Deutsch
    // zurück"): the regression is that the toggle's choice does not survive.
    setListWorkspace("de");
    const { unmount } = renderApp();

    await waitFor(() => {
      expect(i18n.language).toBe("de");
    });

    const toggle = await screen.findByTestId("lang-switch");
    fireEvent.click(toggle);

    await waitFor(() => {
      expect(i18n.language).toBe("en");
    });

    // The toggle must persist the choice to the backend — not just flip the
    // in-memory i18next instance (this is the gap the audit suspected but
    // did not pin down: PATCH is never even attempted from this control).
    await waitFor(() => {
      expect(workspacesApi.update).toHaveBeenCalledWith(
        "ws-test",
        expect.objectContaining({ language: "en" })
      );
    });

    // Simulate a real navigation/reload: unmount the whole provider tree
    // (as a full browser navigation would tear down all in-memory JS state)
    // and mount a fresh one, which re-fetches the workspace from the
    // "backend" (nextListResult, now mutated to "en" by the update mock).
    unmount();
    cleanup();
    // A real reload also re-seeds `i18n.language` purely from the browser
    // locale (see `i18n/index.ts`'s `lng: navigator.language...`), which in
    // the audited environment evaluates to "de" — reproduce that starting
    // point explicitly so the assertion below can only pass if the fresh
    // mount actively restores "en" from the persisted workspace, not by
    // accident of whatever the singleton happened to hold already.
    void i18n.changeLanguage("de");
    renderApp();

    await waitFor(() => {
      expect(screen.getByText("Dashboard")).toBeInTheDocument();
    });
    await waitFor(() => {
      expect(i18n.language).toBe("en");
    });
  });
});

// ---------------------------------------------------------------------------
// Code-review F-02 (High): the sidebar quick-toggle must respect the same
// admin-only gate as the Workspace Settings language radios — a non-admin
// must not be able to change the shared `workspace.language` for everyone.
// ---------------------------------------------------------------------------

describe("Sidebar language toggle — admin-only persistence (F-02)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    updateMock.mockClear();
    installLocalStorageStub();
    sessionStorage.clear();
    void i18n.changeLanguage("en");
  });

  it("a non-admin's toggle only changes the local view — no PATCH, and a visible notice explains why", async () => {
    stubAuthFetch(["viewer"]);
    setListWorkspace("de");
    renderApp();

    await waitFor(() => expect(i18n.language).toBe("de"));

    const toggle = await screen.findByTestId("lang-switch");
    fireEvent.click(toggle);

    // The user's own view still changes immediately...
    await waitFor(() => expect(i18n.language).toBe("en"));
    // ...but the shared workspace setting is never touched.
    expect(workspacesApi.update).not.toHaveBeenCalled();

    // Not silent: a visible, non-alert notice explains the scope limitation.
    const notice = await screen.findByTestId("lang-switch-notice");
    expect(notice).toHaveAttribute("role", "status");
  });

  it("an admin's toggle still persists to the backend (unaffected by the gate)", async () => {
    stubAuthFetch(["admin"]);
    setListWorkspace("de");
    renderApp();

    await waitFor(() => expect(i18n.language).toBe("de"));

    const toggle = await screen.findByTestId("lang-switch");
    fireEvent.click(toggle);

    await waitFor(() => {
      expect(workspacesApi.update).toHaveBeenCalledWith(
        "ws-test",
        expect.objectContaining({ language: "en" })
      );
    });
    expect(screen.queryByTestId("lang-switch-notice")).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Code-review F-03 (Medium): the DEFAULT_WORKSPACE placeholder (used while
// loading, or as the fallback when `GET /workspaces/` fails / returns no
// workspaces) must never force the UI to English — that placeholder's
// hardcoded `language: "en"` is not a real, user-chosen value.
// ---------------------------------------------------------------------------

describe("Workspace-load-failure does not force English (F-03)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    updateMock.mockClear();
    installLocalStorageStub();
    sessionStorage.clear();
    stubAuthFetch(["admin"]);
    // Simulate a German-browser starting point (matches the audited
    // environment) that must survive an unrelated workspace-load failure.
    void i18n.changeLanguage("de");
  });

  it("keeps the current language when GET /workspaces/ fails (falls back to DEFAULT_WORKSPACE)", async () => {
    vi.mocked(workspacesApi.listAll).mockRejectedValueOnce(new Error("network down"));
    renderApp();

    await waitFor(() => {
      expect(screen.getByText("Dashboard")).toBeInTheDocument();
    });

    // Give the restore effect a chance to run (it must choose not to fire).
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(i18n.language).toBe("de");
  });

  it("keeps the current language when the workspace list is empty", async () => {
    nextListResult = { count: 0, next: null, previous: null, results: [] };
    renderApp();

    await waitFor(() => {
      expect(screen.getByText("Dashboard")).toBeInTheDocument();
    });

    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(i18n.language).toBe("de");
  });
});

// ---------------------------------------------------------------------------
// Code-review F-04 (Medium): a failed persist must be surfaced, not
// swallowed, and the toggle must never PATCH the DEFAULT_WORKSPACE
// placeholder's fake UUID.
// ---------------------------------------------------------------------------

describe("Sidebar language toggle — visible failure, no placeholder PATCH (F-04)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    updateMock.mockClear();
    installLocalStorageStub();
    sessionStorage.clear();
    stubAuthFetch(["admin"]);
    void i18n.changeLanguage("en");
  });

  it("shows a visible error notice when the PATCH fails, instead of silently discarding it", async () => {
    setListWorkspace("de");
    updateMock.mockRejectedValueOnce(new Error("500"));
    renderApp();

    await waitFor(() => expect(i18n.language).toBe("de"));

    const toggle = await screen.findByTestId("lang-switch");
    fireEvent.click(toggle);

    // The local view still flips immediately...
    await waitFor(() => expect(i18n.language).toBe("en"));
    // ...but the failure is surfaced as an alert, not swallowed.
    const notice = await screen.findByTestId("lang-switch-notice");
    expect(notice).toHaveAttribute("role", "alert");
  });

  it("never PATCHes the DEFAULT_WORKSPACE placeholder's fake UUID", async () => {
    vi.mocked(workspacesApi.listAll).mockRejectedValueOnce(new Error("network down"));
    renderApp();

    await waitFor(() => {
      expect(screen.getByText("Dashboard")).toBeInTheDocument();
    });

    const toggle = await screen.findByTestId("lang-switch");
    fireEvent.click(toggle);

    // Local view still changes...
    await waitFor(() => expect(i18n.language).toBe("de"));
    // ...but no PATCH was ever attempted against the placeholder workspace.
    expect(workspacesApi.update).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// Code-review F-04-Residual (Medium, re-review): the visible-error fix alone
// did not address the actual root cause — the restore effect re-fires on
// *any* `reloadWorkspaces()` call (dep array `[isWorkspaceReady,
// activeWorkspace]`), not just ones the toggle itself triggered. An
// unrelated reload (preset change, name save, ...) re-applied the persisted
// `activeWorkspace.language`, silently reverting a non-admin's session-local
// choice or a failed admin PATCH — reproducing BUG-01's original symptom in
// a new scenario. N-01: this also made the "changed for your view only"
// notice text a broken promise, since "your view" reverted on the very next
// unrelated reload.
// ---------------------------------------------------------------------------

describe("Local/unpersisted language survives an unrelated reloadWorkspaces() call (F-04-Residual)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    updateMock.mockClear();
    installLocalStorageStub();
    sessionStorage.clear();
  });

  it("a non-admin's session-local toggle is NOT reverted by an unrelated reload", async () => {
    stubAuthFetch(["viewer"]);
    setListWorkspace("de");
    void i18n.changeLanguage("en"); // pre-toggle baseline, distinct from "de"
    renderAppWithIndependentReloadTrigger();

    await waitFor(() => expect(i18n.language).toBe("de"));

    fireEvent.click(await screen.findByTestId("lang-switch"));
    await waitFor(() => expect(i18n.language).toBe("en"));
    expect(workspacesApi.update).not.toHaveBeenCalled();

    // Simulate an UNRELATED reload (e.g. someone else's preset change) —
    // `nextListResult` still says "de", since the toggle above never
    // persisted anything for this non-admin.
    fireEvent.click(screen.getByTestId("independent-reload-trigger"));

    // The independent reload really did run (list() called again)...
    await waitFor(() => {
      expect(workspacesApi.listAll).toHaveBeenCalledTimes(2);
    });
    // ...but the local, unpersisted "en" choice must survive it.
    expect(i18n.language).toBe("en");
  });

  it("a failed admin PATCH is NOT silently re-applied by a later unrelated reload", async () => {
    stubAuthFetch(["admin"]);
    setListWorkspace("de");
    void i18n.changeLanguage("en");
    updateMock.mockRejectedValueOnce(new Error("500"));
    renderAppWithIndependentReloadTrigger();

    await waitFor(() => expect(i18n.language).toBe("de"));

    fireEvent.click(await screen.findByTestId("lang-switch"));
    await waitFor(() => expect(i18n.language).toBe("en"));
    await screen.findByTestId("lang-switch-notice");

    // `nextListResult` is still "de" — the PATCH above was rejected and
    // never mutated it. An unrelated reload re-fetches that stale "de"...
    fireEvent.click(screen.getByTestId("independent-reload-trigger"));

    await waitFor(() => {
      expect(workspacesApi.listAll).toHaveBeenCalledTimes(2);
    });
    // ...but must not silently snap the UI back to it.
    expect(i18n.language).toBe("en");
  });

  it("clears the override and lets an explicit workspace switch bring its own language back", async () => {
    // A non-admin toggles the language locally...
    stubAuthFetch(["viewer"]);
    setListWorkspace("de");
    void i18n.changeLanguage("en");

    const otherWorkspace: Workspace = {
      id: "ws-other",
      name: "Other",
      preset: "standard",
      terminology_profile: "se_mode",
      language: "de",
      theme: "dark",
      is_active: true,
      closed_at: null,
      closed_by: null,
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    };
    renderAppWithExplicitSwitch(otherWorkspace);

    await waitFor(() => expect(i18n.language).toBe("de"));
    fireEvent.click(await screen.findByTestId("lang-switch"));
    await waitFor(() => expect(i18n.language).toBe("en"));

    // ...then an EXPLICIT workspace switch (the sidebar switcher's own
    // `setActiveWorkspace(ws)` — unlike the unrelated-reload tests above,
    // this call site is allowed to clear the override) lands the language
    // on the newly selected workspace's own persisted value.
    fireEvent.click(screen.getByTestId("explicit-workspace-switch-trigger"));

    await waitFor(() => {
      expect(i18n.language).toBe("de");
    });
  });
});

// ---------------------------------------------------------------------------
// Code-review R-01 (Important, re-review round 2): clearing the override
// BEFORE `reloadWorkspaces()` (instead of after it resolves) left a window
// where `hasLocalLanguageOverride` was already `false` but
// `activeWorkspace.language` was still the pre-toggle, stale value — the
// restore effect could fire in exactly that window and flash the UI back to
// the old language before flipping forward again once the reload landed.
// ---------------------------------------------------------------------------

describe("Sidebar language toggle — no flash-back while the post-save reload is pending (R-01)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    updateMock.mockClear();
    installLocalStorageStub();
    sessionStorage.clear();
    stubAuthFetch(["admin"]);
    void i18n.changeLanguage("en");
  });

  it("keeps the newly-toggled language while reloadWorkspaces()'s own GET is still pending", async () => {
    setListWorkspace("de");
    renderApp();
    await waitFor(() => expect(i18n.language).toBe("de"));

    // Delay reloadWorkspaces()'s own `GET /workspaces/` so the pending
    // window between "PATCH resolved" and "reload resolved" is observable.
    // This mock is installed AFTER the initial mount's own `listAll()` call
    // has already happened, so `listCallCount` here counts only calls made
    // from this point on — i.e. the toggle's own `reloadWorkspaces()` call
    // is the *first* one this counter observes.
    let releasePendingList: (() => void) | null = null;
    const pendingList = new Promise<void>((resolve) => {
      releasePendingList = resolve;
    });
    let listCallCount = 0;
    vi.mocked(workspacesApi.listAll).mockImplementation(async () => {
      listCallCount += 1;
      if (listCallCount === 1) {
        await pendingList;
      }
      return (nextListResult as { results: Awaited<ReturnType<typeof workspacesApi.listAll>> }).results;
    });

    fireEvent.click(await screen.findByTestId("lang-switch"));

    // Local flip is immediate...
    await waitFor(() => expect(i18n.language).toBe("en"));
    // ...the PATCH resolves (fast, no artificial delay on `updateMock`) and
    // `reloadWorkspaces()`'s own GET has started...
    await waitFor(() => expect(listCallCount).toBe(1));

    // ...but while that GET is still pending, the language must NOT have
    // flashed back to the stale `activeWorkspace.language` ("de"). Pre-R-01
    // this failed here: `clearLanguageOverride()` ran before
    // `reloadWorkspaces()`, so the restore effect fired against the
    // still-stale workspace object in exactly this window.
    expect(i18n.language).toBe("en");

    releasePendingList!();
    await waitFor(() => expect(i18n.language).toBe("en"));
  });
});

// ---------------------------------------------------------------------------
// Code-review R-02 (Medium, re-review round 2): `hasLocalLanguageOverride`
// was never reset on logout. `WorkspaceProvider` also wraps `/login`, and
// `AuthContext.logout()` does not reload the page, so a local/unpersisted
// override left by the previous session survived into the next login in the
// same tab and silently overrode that user's own persisted workspace
// language.
// ---------------------------------------------------------------------------

describe("Logout clears a local/unpersisted language override (R-02)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    updateMock.mockClear();
    installLocalStorageStub();
    sessionStorage.clear();
  });

  it("a re-login in the same tab follows the newly loaded workspace's language, not a stale override from the previous session", async () => {
    // "User A": non-admin, session-locally toggles to "en" against a
    // workspace whose persisted language is "de".
    stubAuthFetch(["viewer"]);
    setListWorkspace("de");
    void i18n.changeLanguage("de");
    renderAppWithAuthSwitch();

    await waitFor(() => expect(i18n.language).toBe("de"));
    fireEvent.click(await screen.findByTestId("lang-switch"));
    await waitFor(() => expect(i18n.language).toBe("en"));

    // Logout (no page reload — same in-memory i18next/WorkspaceContext).
    fireEvent.click(screen.getByTestId("test-logout-trigger"));

    // "User B" logs back in on the same tab; their own workspace's
    // persisted language ("de", set up via `setListWorkspace` above) is
    // deliberately different from the override ("en") the previous session
    // left behind — a passing assertion below can only be explained by the
    // restore effect actually running again (override cleared on logout),
    // not by the override happening to already match.
    fireEvent.click(screen.getByTestId("test-login-trigger"));

    await waitFor(() => {
      expect(screen.getByText("Dashboard")).toBeInTheDocument();
    });
    await waitFor(() => {
      expect(i18n.language).toBe("de");
    });
  });
});
