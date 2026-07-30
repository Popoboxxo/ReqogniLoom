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
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { AuthProvider } from "../context/AuthContext";
import { WorkspaceProvider } from "../context/WorkspaceContext";
import { ThemeProvider } from "../context/ThemeContext";
import { SidebarNavigation } from "../components/NavigationShell/SidebarNavigation";
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
  versionApi: { getVersion: vi.fn(async () => ({ app_version: "0.0.0", commit: "abc", commit_short: "abc", build_time: null })) },
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

describe("SidebarNavigation — Goals nav item (REQ-L2-TE-020)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    installLocalStorageStub();
    sessionStorage.clear();
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        status: 200,
        json: async () => ({
          user: { id: "u-1", username: "tester", email: "t@x", first_name: "", last_name: "", is_active: true, tenant_id: null, roles: ["admin"] },
          tenant_id: null,
          roles: ["admin"],
        }),
      }) as unknown as Response)
    );
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
