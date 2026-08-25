/**
 * ARCH-L1-001 ReactFrontend — Workspace theme decoupling (Theme Presets).
 *
 * Supersedes the #568 workspace-theme persistence tests: with Theme
 * Presets the theme is resolved inside ThemeContext (user preference >
 * tenant default > fallback) and WorkspaceContext no longer seeds a
 * workspace `theme` into it. `Workspace.theme` remains a backend field but
 * is functionally superseded — these tests pin exactly that: a themed
 * workspace row must have NO influence on the resolved theme, and mounting
 * the shell with one must stay free of console errors.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
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
    listAll: vi.fn(async () => (nextListResult as { results?: unknown[] }).results ?? []),
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

describe("Workspace theme decoupling (Theme Presets)", () => {
  let consoleErrors: string[];
  let consoleWarns: string[];

  beforeEach(() => {
    vi.clearAllMocks();
    installLocalStorageStub();
    sessionStorage.clear();
    stubAuthFetch(["viewer"]);
    document.documentElement.style.cssText = "";
    delete document.documentElement.dataset.theme;
    delete document.documentElement.dataset.themeMode;

    (themePalettesApi.list as ReturnType<typeof vi.fn>).mockResolvedValue({
      results: [
        {
          key: "default",
          label: "Default",
          is_system: true,
          dark_tokens: { "--color-primary": "#111111" },
          light_tokens: { "--color-primary": "#eeeeee" },
        },
      ],
    });
    (
      themePalettesApi.getPreference as ReturnType<typeof vi.fn>
    ).mockResolvedValue({ palette_key: null, mode: null });
    (
      themePalettesApi.getTenantDefault as ReturnType<typeof vi.fn>
    ).mockResolvedValue({ palette_key: "default", mode: "dark" });

    consoleErrors = [];
    consoleWarns = [];
    vi.spyOn(console, "error").mockImplementation((...args: unknown[]) => {
      consoleErrors.push(args.map(String).join(" "));
    });
    vi.spyOn(console, "warn").mockImplementation((...args: unknown[]) => {
      consoleWarns.push(args.map(String).join(" "));
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("a workspace-default theme no longer overrides the server-resolved theme", async () => {
    // Workspace says "light"; no user preference, tenant default = dark.
    // The workspace row must NOT flip the theme — only user preference /
    // tenant default / fallback decide.
    setListWorkspace("light");
    renderApp();

    await waitFor(() => {
      expect(screen.getByText("Dashboard")).toBeInTheDocument();
    });
    await waitFor(() => {
      expect(document.documentElement.dataset.themeMode).toBe("dark");
    });
    expect(document.documentElement.dataset.themeMode).toBe("dark");
  });

  it("mounting with a themed workspace produces no console errors or warnings", async () => {
    setListWorkspace("light");
    renderApp();

    await waitFor(() => {
      expect(screen.getByText("Dashboard")).toBeInTheDocument();
    });
    // Give every effect (including any wrongly-revived seeding effect) a
    // chance to fire before asserting silence.
    await new Promise((resolve) => setTimeout(resolve, 50));

    // React's act() advisories are test-harness timing noise, not app
    // behavior — everything else must be silent.
    const realErrors = consoleErrors.filter((m) => !m.includes("not wrapped in act("));
    const realWarns = consoleWarns.filter((m) => !m.includes("not wrapped in act("));
    expect(realErrors).toEqual([]);
    expect(realWarns).toEqual([]);
  });
});
