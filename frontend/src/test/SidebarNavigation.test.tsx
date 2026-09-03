/**
 * ARCH-L1-001 ReactFrontend — SidebarNavigation Goals nav-item gating.
 *
 * leaf_id: COMP-RF-001 (NavigationShell)
 * req_id:  REQ-L2-TE-020 (Goals/MainGoal)
 *
 * Verifies that the "/goals" nav link (nav.goals) is rendered when the
 * active workspace has `goals_enabled: true` and absent when it is false
 * or unset — mirroring the workspace-owned toggle in WorkspaceSettings
 * rather than the generic preset-visibility system.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { AuthProvider } from "../context/AuthContext";
import { WorkspaceProvider } from "../context/WorkspaceContext";
import { ThemeProvider } from "../context/ThemeContext";
import { SidebarNavigation } from "../components/NavigationShell/SidebarNavigation";
import { themePalettesApi } from "../api/themePalettes";
import type { Workspace } from "../types";

vi.mock("../api/themePalettes");

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
    // reloadWorkspaces (Task 1 fix) now calls listAll() instead of list() to
    // avoid silently truncating the workspace switcher to page 1 — mirror
    // the same single-page `nextListResult.results` here for these tests.
    listAll: vi.fn(async () => (nextListResult as { results?: unknown[] }).results ?? []),
    create: vi.fn(),
    update: vi.fn(),
    setPreset: vi.fn(),
    closeWorkspace: vi.fn(),
    reactivateWorkspace: vi.fn(),
    deleteWorkspace: vi.fn(),
  },
}));

function setListWorkspace(goalsEnabled: boolean | undefined): void {
  const ws: Partial<Workspace> = {
    id: "ws-test",
    name: "Test",
    preset: "standard",
    terminology_profile: "se_mode",
    language: "en",
    is_active: true,
    closed_at: null,
    closed_by: null,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    goals_enabled: goalsEnabled,
  };
  nextListResult = { count: 1, next: null, previous: null, results: [ws] };
}

function renderSidebar(): void {
  render(
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

// jsdom in this test runtime does not provide window.localStorage (Node's
// --localstorage-file experimental flag is not set), which ThemeProvider
// (a SidebarNavigation dependency) reads synchronously on mount. Polyfill a
// minimal in-memory implementation so ThemeProvider does not throw.
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

describe("SidebarNavigation — Goals nav item (REQ-L2-TE-020)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    installLocalStorageStub();
    sessionStorage.clear();
    stubAuthFetch(["admin"]);
  });

  it("shows the Goals nav link when goals_enabled is true", async () => {
    setListWorkspace(true);
    renderSidebar();

    await waitFor(() => {
      expect(screen.getByText("Goals")).toBeInTheDocument();
    });
    const link = screen.getByText("Goals").closest("a");
    expect(link).toHaveAttribute("href", "/goals");
  });

  it("hides the Goals nav link when goals_enabled is false", async () => {
    setListWorkspace(false);
    renderSidebar();

    await waitFor(() => {
      // Wait for some stable, always-visible item to confirm the nav rendered.
      expect(screen.getByText("Dashboard")).toBeInTheDocument();
    });
    expect(screen.queryByText("Goals")).not.toBeInTheDocument();
  });

  it("hides the Goals nav link when goals_enabled is undefined", async () => {
    setListWorkspace(undefined);
    renderSidebar();

    await waitFor(() => {
      expect(screen.getByText("Dashboard")).toBeInTheDocument();
    });
    expect(screen.queryByText("Goals")).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Theme Presets — mode-only quick toggle (Task 6 Part B)
// ---------------------------------------------------------------------------

describe("SidebarNavigation — theme mode quick toggle", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    installLocalStorageStub();
    sessionStorage.clear();
    stubAuthFetch(["viewer"]);
    document.documentElement.style.cssText = "";
    delete document.documentElement.dataset.theme;
    delete document.documentElement.dataset.themeMode;

    // Server state: user preference = bauhaus/dark.
    (themePalettesApi.list as ReturnType<typeof vi.fn>).mockResolvedValue({
      results: [
        {
          key: "bauhaus",
          label: "Bauhaus",
          is_system: true,
          dark_tokens: { "--color-primary": "#222222" },
          light_tokens: { "--color-primary": "#dddddd" },
        },
      ],
    });
    (
      themePalettesApi.getPreference as ReturnType<typeof vi.fn>
    ).mockResolvedValue({ palette_key: "bauhaus", mode: "dark" });
    (
      themePalettesApi.getTenantDefault as ReturnType<typeof vi.fn>
    ).mockResolvedValue({ palette_key: "default", mode: "dark" });
  });

  it("flips the mode without changing the palette", async () => {
    renderSidebar();

    await waitFor(() => {
      expect(document.documentElement.dataset.themeMode).toBe("dark");
    });
    // Wait for the server resolution (user preference bauhaus/dark) too.
    await waitFor(() => {
      expect(document.documentElement.dataset.theme).toBe("bauhaus");
    });

    fireEvent.click(await screen.findByTestId("sidebar-theme-mode-toggle"));

    // Mode flipped, palette untouched...
    await waitFor(() => {
      expect(document.documentElement.dataset.themeMode).toBe("light");
    });
    expect(document.documentElement.dataset.theme).toBe("bauhaus");
    // ...and the full (paletteKey, mode) pair persisted server-side.
    await waitFor(() => {
      expect(themePalettesApi.setPreference).toHaveBeenCalledWith("bauhaus", "light");
    });
  });
});

// ---------------------------------------------------------------------------
// Scroll region (issue #449 / #720): the sidebar's own <nav> intentionally has
// `overflow-y: hidden` (only .scrollContent, one level down, scrolls — see
// SidebarNavigation.module.css) so the footer stays pinned. Several QA
// re-reports measured the outer <nav> instead of the inner scroll region and
// concluded the sidebar was "not scrollable". jsdom does not compute real
// CSS layout/overflow, so this cannot assert actual scrolling here (that is
// covered by e2e/tests/sidebar-scroll.spec.ts) — this only pins the two DOM
// facts a jsdom test *can* verify: (1) the dedicated scroll-content element
// exists as the single container all nav items live in, and (2) every nav
// item — including the ones repeatedly reported as "unreachable" (Baselines,
// Import, Workflows, SE-Auditor, System Settings, User Management, ...) —
// is actually present in the DOM regardless of viewport size, so a real
// scroll (verified by the e2e test) can always reach them.
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Role-gated admin nav items (R2/T1 systemaudit 2026-09-02): a "viewer" saw
// every nav item — including admin-only pages — with only the server
// rejecting the actual request. Hide those links from roles that cannot use
// the page behind them.
// ---------------------------------------------------------------------------

describe("SidebarNavigation — role-gated admin nav items (R2/T1)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    installLocalStorageStub();
    sessionStorage.clear();
  });

  it("does not render admin-only items for a viewer", async () => {
    stubAuthFetch(["viewer"]);
    setListWorkspace(true);
    renderSidebar();

    await waitFor(() => {
      expect(screen.getByText("Dashboard")).toBeInTheDocument();
    });
    expect(screen.queryByText("Workspace Settings")).not.toBeInTheDocument();
    expect(screen.queryByText("System Settings")).not.toBeInTheDocument();
    expect(screen.queryByText("User Management")).not.toBeInTheDocument();
  });

  it("renders admin-only items for an admin", async () => {
    stubAuthFetch(["admin"]);
    setListWorkspace(true);
    renderSidebar();

    await waitFor(() => {
      expect(screen.getByText("Workspace Settings")).toBeInTheDocument();
    });
    expect(screen.getByText("System Settings")).toBeInTheDocument();
    expect(screen.getByText("User Management")).toBeInTheDocument();
  });
});

describe("SidebarNavigation — scroll region contains all nav items (#449/#720)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    installLocalStorageStub();
    sessionStorage.clear();
    stubAuthFetch(["admin"]);
  });

  it("renders the scrollable nav-content container with every nav item nested inside it", async () => {
    setListWorkspace(true);
    // Use the "extended" preset so every preset-gated nav item (baselines,
    // reviews, icds, diagrams, testCases, ...) is visible, not just the
    // always-on ones — this is the scenario in which the sidebar has enough
    // items to overflow a short viewport in the first place.
    (nextListResult as { results: Array<Record<string, unknown>> }).results[0].preset = "extended";
    renderSidebar();

    const scrollContent = await screen.findByTestId("sidebar-nav-scroll-content");

    // Items from every group, including the ones the bug reports named as
    // "unreachable below the fold" in the admin section.
    const expectedLabels = [
      "Dashboard",
      "Goals",
      "Stakeholder Needs",
      "System Requirements",
      "Architecture",
      "Test Cases",
      "Test Runs",
      "Baselines",
      "Reviews",
      "Import",
      "Workflows",
      "SE-Auditor",
      "Workspace Settings",
      "System Settings",
      "User Management",
    ];

    for (const label of expectedLabels) {
      const link = await screen.findByText(label);
      expect(link.closest("a")).toBeInTheDocument();
      // Every nav link must live inside the single scrollable container —
      // not e.g. next to it as a sibling that would sit outside the scroll
      // region and stay permanently clipped.
      expect(scrollContent.contains(link)).toBe(true);
    }
  });
});
