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
import { ThemeProvider, useTheme } from "../context/ThemeContext";
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

describe("Returning visitor's stored theme preference is not overwritten by the workspace default (#568 final-review fix)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    installLocalStorageStub();
    sessionStorage.clear();
    stubAuthFetch(["viewer"]);
  });

  it("keeps an existing localStorage theme preference after the workspace list resolves with a different default", async () => {
    // Seed the stub's underlying store BEFORE renderApp() so ThemeProvider's
    // initial mount (resolveInitialTheme) actually reads it.
    window.localStorage.setItem("reqflow-theme", "light");
    setListWorkspace("dark");
    renderApp();

    await waitFor(() => {
      expect(screen.getByText("Dashboard")).toBeInTheDocument();
    });
    await waitFor(() => {
      expect(workspacesApi.list).toHaveBeenCalled();
    });

    // Give the theme-restore effect a chance to (wrongly) fire if the bug
    // were still present.
    await waitFor(() => {
      expect(document.documentElement.dataset.theme).toBe("light");
    });
    expect(window.localStorage.getItem("reqflow-theme")).toBe("light");

    // Re-review finding: the first waitFor success above can be a false
    // positive if a later effect (e.g. the bootstrap effect's own
    // auth-resolution re-run) still overwrites the value shortly after —
    // exactly how this test passed once before against unfixed code that
    // reset the override, then the restore effect reapplied the workspace
    // default a tick later. Flush pending effects and assert the value is
    // still correct afterward, not just at first success.
    await new Promise((resolve) => setTimeout(resolve, 300));
    expect(document.documentElement.dataset.theme).toBe("light");
    expect(window.localStorage.getItem("reqflow-theme")).toBe("light");
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

describe("A persisted theme choice survives a logout/re-login cycle (#568 final-review fix)", () => {
  // Originally written mirroring language's R-02 test (which asserts the
  // OPPOSITE: an override is cleared by logout). That assertion was wrong
  // for theme once ported verbatim: language's override is deliberately
  // session-local and never persisted anywhere, so clearing it on logout
  // correctly stops it leaking to the next user on the same tab. Theme's
  // override instead gates an ALREADY-persisted `localStorage` value (see
  // WorkspaceContext.tsx's bootstrap-effect comment, #568 final-review
  // fix) — the same way a browser's own light/dark setting isn't reset by
  // logging out of one account on it. This test now asserts the behavior
  // that's actually correct for a persisted, device-level preference.
  beforeEach(() => {
    vi.clearAllMocks();
    installLocalStorageStub();
    sessionStorage.clear();
  });

  it("a re-login in the same tab keeps the toggled-and-persisted theme, not the newly loaded workspace's default", async () => {
    stubAuthFetch(["viewer"]);
    setListWorkspace("light");
    renderAppWithAuthSwitch();

    await waitFor(() => expect(document.documentElement.dataset.theme).toBe("light"));
    fireEvent.click(await screen.findByTestId("theme-toggle"));
    await waitFor(() => expect(document.documentElement.dataset.theme).toBe("dark"));
    expect(window.localStorage.getItem("reqflow-theme")).toBe("dark");

    fireEvent.click(screen.getByTestId("test-logout-trigger"));
    fireEvent.click(screen.getByTestId("test-login-trigger"));

    await waitFor(() => {
      expect(screen.getByText("Dashboard")).toBeInTheDocument();
    });
    await waitFor(() => {
      expect(workspacesApi.list).toHaveBeenCalledTimes(2);
    });

    // The new session's workspace default is "light" (same mock), but the
    // browser's own persisted "dark" choice must win — settle-and-recheck,
    // not just a first waitFor success (see the "Returning visitor" test
    // above for why that matters).
    await new Promise((resolve) => setTimeout(resolve, 300));
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(window.localStorage.getItem("reqflow-theme")).toBe("dark");
  });
});

describe("ThemeContext.setTheme falls back on an unregistered theme id (#568 final-review fix)", () => {
  beforeEach(() => {
    installLocalStorageStub();
  });

  function SetBogusThemeHarness(): JSX.Element {
    const { theme, setTheme } = useTheme();
    return (
      <button
        data-testid="set-bogus-theme"
        onClick={() => setTheme("bogus-unregistered-id")}
      >
        current: {theme}
      </button>
    );
  }

  it("resolves an unregistered theme id to FALLBACK_THEME (dark) instead of applying it verbatim", async () => {
    render(
      <ThemeProvider>
        <SetBogusThemeHarness />
      </ThemeProvider>
    );

    fireEvent.click(screen.getByTestId("set-bogus-theme"));

    await waitFor(() => {
      expect(document.documentElement.dataset.theme).toBe("dark");
    });
    expect(screen.getByTestId("set-bogus-theme").textContent).toBe(
      "current: dark"
    );
  });
});
