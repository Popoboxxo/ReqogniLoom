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

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
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

// Plan C / T-C4-4: the sidebar reads and writes its collapsed-group state
// through the Q1 preference service (TanStack Query), so the harness needs a
// QueryClient — one per render, so no state leaks between cases.
function renderSidebar(initialEntries: string[] = ["/"]): void {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={initialEntries}>
        <AuthProvider>
          <ThemeProvider>
            <WorkspaceProvider>
              <SidebarNavigation />
            </WorkspaceProvider>
          </ThemeProvider>
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>
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


function stubAuthFetch(roles: string[], isTenantAdmin?: boolean): void {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input?: unknown) => {
      // Plan C / T-C4-4: the sidebar now also reads the Q1 preference
      // service. The auth stub answers a user payload, which would leave
      // `values` undefined and break that read — answer the preference
      // route with the registry default (`[]`, nothing collapsed) instead.
      // The dedicated groups suite installs its own router.
      if (String(input ?? "").includes("/preference-values/")) {
        return {
          ok: true,
          status: 200,
          headers: { get: () => null },
          json: async () => ({ workspace_id: null, values: {} }),
        } as unknown as Response;
      }
      return {
        ok: true,
        status: 200,
        json: async () => ({
          user: { id: "u-1", username: "tester", email: "t@x", first_name: "", last_name: "", is_active: true, tenant_id: null, roles },
          tenant_id: null,
          roles,
          is_tenant_admin: isTenantAdmin,
        }),
      } as unknown as Response;
    })
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

  // Tenant-admin is independent of the workspace `admin` role (see the
  // NAV_ITEMS comment on /user-management) — this is exactly the case the
  // dedicated isTenantAdmin OR-branch exists for, as opposed to the generic
  // `requires` mechanism used for /settings and /system-settings.
  it("renders User Management for a tenant-admin who lacks the workspace admin role, but still hides workspace/system settings", async () => {
    stubAuthFetch(["viewer"], true);
    setListWorkspace(true);
    renderSidebar();

    await waitFor(() => {
      expect(screen.getByText("User Management")).toBeInTheDocument();
    });
    expect(screen.queryByText("Workspace Settings")).not.toBeInTheDocument();
    expect(screen.queryByText("System Settings")).not.toBeInTheDocument();
  });
});

describe("SidebarNavigation — no notification row (ADR-009)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    installLocalStorageStub();
    sessionStorage.clear();
    stubAuthFetch(["admin"]);
  });

  // ADR-009 moved the notification feed into the assistant entry point
  // (InterviewWidget) as a tab. The failure mode this pins is a *duplicate*
  // entry point: the sidebar row left behind next to the new one. So the
  // assertion is the bell's absence, not the feed's presence.
  it("no longer renders the notification bell in the footer", async () => {
    setListWorkspace(true);
    renderSidebar();

    // A stable, always-visible footer row confirms the footer itself rendered
    // — otherwise "the bell is missing" would pass on a broken render.
    await screen.findByTestId("sidebar-theme-mode-toggle");
    expect(screen.getByTestId("nav-profile")).toBeInTheDocument();

    expect(screen.queryByTestId("notification-bell-toggle")).not.toBeInTheDocument();
    expect(screen.queryByTestId("notification-bell-dropdown")).not.toBeInTheDocument();
    expect(screen.queryByTestId("notification-bell-badge")).not.toBeInTheDocument();
  });

  it("does not import the deleted bell component any more", () => {
    const source = readFileSync(
      join(__dirname, "..", "components", "NavigationShell", "SidebarNavigation.tsx"),
      "utf-8"
    );
    expect(source).not.toMatch(/NotificationBell/);
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

// ---------------------------------------------------------------------------
// Mobile drawer modality (M-1, plan Phase 6 step 4).
//
// The drawer is an off-canvas overlay below the tablet breakpoint: there it
// must behave as a modal dialog (`role="dialog"` + `aria-modal`, focus trap,
// initial focus into the panel, Escape/close control, focus return to the
// burger). Above the breakpoint the same element is the static desktop rail
// and MUST stay non-modal.
// ---------------------------------------------------------------------------

describe("SidebarNavigation — mobile drawer modality (M-1)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    installLocalStorageStub();
    sessionStorage.clear();
    stubAuthFetch(["admin"]);
    setListWorkspace(true);
  });

  afterEach(() => {
    // Drop the own descriptor so the environment's own `matchMedia` (if any)
    // is visible again for the other suites in this file.
    Reflect.deleteProperty(window, "matchMedia");
  });

  /** Pin the viewport query the drawer's modality is derived from. */
  function installViewport(mobile: boolean): void {
    Object.defineProperty(window, "matchMedia", {
      configurable: true,
      writable: true,
      value: vi.fn(() => ({
        matches: mobile,
        media: "",
        onchange: null,
        addEventListener: () => {},
        removeEventListener: () => {},
        addListener: () => {},
        removeListener: () => {},
        dispatchEvent: () => true,
      })),
    });
  }

  it("keeps the desktop rail non-modal when the burger opens it", async () => {
    installViewport(false);
    renderSidebar();

    const burger = await screen.findByTestId("sidebar-burger");
    fireEvent.click(burger);

    const nav = document.querySelector("nav");
    expect(nav).not.toBeNull();
    expect(nav).not.toHaveAttribute("role");
    expect(nav).not.toHaveAttribute("aria-modal");
    expect(screen.queryByTestId("sidebar-drawer-close")).not.toBeInTheDocument();
    // The pointer affordance is unchanged on the desktop path.
    expect(screen.getByTestId("sidebar-overlay")).toBeInTheDocument();
  });

  it("makes the open drawer a modal dialog on a mobile viewport", async () => {
    installViewport(true);
    renderSidebar();

    const burger = await screen.findByTestId("sidebar-burger");
    fireEvent.click(burger);

    const nav = document.querySelector("nav");
    expect(nav).toHaveAttribute("role", "dialog");
    expect(nav).toHaveAttribute("aria-modal", "true");

    // Initial focus moves into the drawer, onto its close control.
    const closeButton = screen.getByTestId("sidebar-drawer-close");
    await waitFor(() => expect(closeButton).toHaveFocus());
  });

  // N10 (SC 2.4.3/2.4.7): below the breakpoint the closed drawer is only
  // translated off-screen, so without `inert` every nav link stayed tabbable
  // while invisible. Pin both halves: inert while closed, gone while open.
  it("hides the closed mobile drawer from focus and AT with inert", async () => {
    installViewport(true);
    renderSidebar();

    const burger = await screen.findByTestId("sidebar-burger");
    const nav = document.querySelector("nav");
    expect(nav).not.toBeNull();
    expect(nav).toHaveAttribute("inert");

    fireEvent.click(burger);

    await waitFor(() => expect(document.querySelector("nav")).not.toHaveAttribute("inert"));
  });

  it("keeps the desktop rail interactive (no inert)", async () => {
    installViewport(false);
    renderSidebar();

    await screen.findByTestId("sidebar-burger");
    const nav = document.querySelector("nav");
    expect(nav).not.toBeNull();
    expect(nav).not.toHaveAttribute("inert");
  });

  it("closes the modal drawer on Escape and returns focus to the burger", async () => {
    installViewport(true);
    renderSidebar();

    const burger = await screen.findByTestId("sidebar-burger");
    fireEvent.click(burger);
    await screen.findByTestId("sidebar-drawer-close");

    fireEvent.keyDown(document, { key: "Escape" });

    await waitFor(() => {
      expect(document.querySelector("nav")).not.toHaveAttribute("role");
    });
    expect(burger).toHaveFocus();
  });

  it("closes the modal drawer from its own close control (keyboard-reachable)", async () => {
    installViewport(true);
    renderSidebar();

    const burger = await screen.findByTestId("sidebar-burger");
    fireEvent.click(burger);
    const closeButton = await screen.findByTestId("sidebar-drawer-close");

    fireEvent.click(closeButton);

    await waitFor(() => {
      expect(screen.queryByTestId("sidebar-drawer-close")).not.toBeInTheDocument();
    });
    expect(burger).toHaveFocus();
  });
});

// ---------------------------------------------------------------------------
// Collapsible nav groups (Plan C / T-C4-4, C-L6 / finding R19).
//
// At 1366×768 only 11 of 27 links fit above the fold. Each group header is a
// disclosure button whose state is the user-level Q1 preference
// `ui.sidebar.collapsed_groups`; the group holding the active route is never
// collapsed, and a failed preference read degrades to "nothing collapsed".
// ---------------------------------------------------------------------------

const COLLAPSED_GROUPS_KEY = "ui.sidebar.collapsed_groups";

interface RecordedRequest {
  url: string;
  method: string;
  body: unknown;
}

const GROUP_IDS = ["overview", "requirements", "architecture", "test", "admin"] as const;

function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: { get: () => null },
    json: async () => body,
  } as unknown as Response;
}

describe("SidebarNavigation — collapsible nav groups (T-C4-4)", () => {
  let requests: RecordedRequest[] = [];
  /** The server-side *effective* preference values the stub answers with. */
  let effectiveValues: Record<string, unknown> = {};
  /** Status of the effective read; non-200 simulates an outage. */
  let effectiveStatus = 200;
  let patchStatus = 200;

  /**
   * One fetch router for auth + the Q1 preference routes, so a PATCH body can
   * be asserted and the effective read can be made to fail. Applied PATCHes
   * are reflected back in `effectiveValues`, mirroring the real server (a
   * write invalidates the effective read, which must then report the new
   * value — otherwise the group would spring open again on refetch).
   */
  function installFetchRouter(roles: string[] = ["admin"]): void {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: unknown, init?: RequestInit) => {
        const url = String(input);
        const method = (init?.method ?? "GET").toUpperCase();
        const body =
          typeof init?.body === "string" ? (JSON.parse(init.body) as unknown) : null;
        requests.push({ url, method, body });

        if (url.includes("/preference-values/")) {
          if (method === "PATCH") {
            if (patchStatus !== 200) {
              return jsonResponse(patchStatus, {
                error: { code: "INTERNAL_SERVER_ERROR", message: "boom" },
              });
            }
            const values =
              (body as { values?: Record<string, unknown> } | null)?.values ?? {};
            for (const [key, value] of Object.entries(values)) {
              if (value === null) delete effectiveValues[key];
              else effectiveValues[key] = value;
            }
            return jsonResponse(200, {
              scope: "user",
              workspace_id: null,
              values: effectiveValues,
            });
          }
          if (effectiveStatus !== 200) {
            return jsonResponse(effectiveStatus, {
              error: { code: "INTERNAL_SERVER_ERROR", message: "boom" },
            });
          }
          return jsonResponse(200, {
            workspace_id: null,
            values: Object.fromEntries(
              Object.entries(effectiveValues).map(([key, value]) => [
                key,
                { value, source: "user" },
              ])
            ),
          });
        }

        return jsonResponse(200, {
          user: {
            id: "u-1",
            username: "tester",
            email: "t@x",
            first_name: "",
            last_name: "",
            is_active: true,
            tenant_id: null,
            roles,
          },
          tenant_id: null,
          roles,
        });
      })
    );
  }

  /** The PATCHes that addressed the user level, in order. */
  function userLevelPatches(): RecordedRequest[] {
    return requests.filter(
      (request) =>
        request.method === "PATCH" &&
        request.url.includes("/users/me/preference-values/")
    );
  }

  beforeEach(() => {
    vi.clearAllMocks();
    installLocalStorageStub();
    sessionStorage.clear();
    requests = [];
    effectiveValues = {};
    effectiveStatus = 200;
    patchStatus = 200;
    installFetchRouter(["admin"]);
    setListWorkspace(true);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  function toggle(groupId: string): HTMLElement {
    return screen.getByTestId(`sidebar-group-toggle-${groupId}`);
  }

  it("collapses a group on click and PATCHes the full collapsed id list at user level", async () => {
    renderSidebar();

    const adminToggle = await screen.findByTestId("sidebar-group-toggle-admin");
    await waitFor(() => expect(adminToggle).toHaveAttribute("aria-expanded", "true"));
    // The disclosure wiring is the ARIA pattern the header has to follow.
    expect(adminToggle).toHaveAttribute(
      "aria-controls",
      "sidebar-nav-group-panel-admin"
    );

    fireEvent.click(adminToggle);

    await waitFor(() => expect(adminToggle).toHaveAttribute("aria-expanded", "false"));
    expect(
      document.getElementById("sidebar-nav-group-panel-admin")
    ).toHaveAttribute("hidden");
    // The collapsed panel is out of the accessibility tree — its links are no
    // longer reachable by role, not merely visually clipped.
    expect(screen.queryByRole("link", { name: "Import" })).not.toBeInTheDocument();

    await waitFor(() => expect(userLevelPatches()).toHaveLength(1));
    expect(userLevelPatches()[0].body).toEqual({
      values: { [COLLAPSED_GROUPS_KEY]: ["admin"] },
    });
  });

  it("keeps the collapsed list deduplicated and in navigation order", async () => {
    renderSidebar();

    fireEvent.click(await screen.findByTestId("sidebar-group-toggle-admin"));
    // Wait for the write to land and its refetch to be applied, so the next
    // toggle starts from the stored value rather than the stale `[]`.
    await waitFor(() => expect(toggle("admin")).toHaveAttribute("aria-expanded", "false"));
    await waitFor(() => expect(userLevelPatches()).toHaveLength(1));

    fireEvent.click(toggle("test"));
    await waitFor(() => expect(toggle("test")).toHaveAttribute("aria-expanded", "false"));
    await waitFor(() => expect(userLevelPatches()).toHaveLength(2));
    // "test" precedes "admin" in NAV_GROUP_ORDER — the payload follows the
    // render order, not click order, so the stored value stays comparable.
    expect(userLevelPatches()[1].body).toEqual({
      values: { [COLLAPSED_GROUPS_KEY]: ["test", "admin"] },
    });

    // Toggling the same group open again removes exactly that id.
    fireEvent.click(toggle("test"));
    await waitFor(() => expect(toggle("test")).toHaveAttribute("aria-expanded", "true"));
    await waitFor(() => expect(userLevelPatches()).toHaveLength(3));
    expect(userLevelPatches()[2].body).toEqual({
      values: { [COLLAPSED_GROUPS_KEY]: ["admin"] },
    });
  });

  it("renders a saved-collapsed group open when it contains the active route", async () => {
    effectiveValues = { [COLLAPSED_GROUPS_KEY]: ["requirements"] };
    renderSidebar(["/requirements"]);

    const requirementsToggle = await screen.findByTestId(
      "sidebar-group-toggle-requirements"
    );
    // A collapsed group would hide the very link the user is on.
    await waitFor(() =>
      expect(requirementsToggle).toHaveAttribute("aria-expanded", "true")
    );
    const link = screen.getByText("System Requirements").closest("a");
    expect(link).toHaveAttribute("href", "/requirements");
    expect(link).toBeVisible();
  });

  it("leaves every group open when the preference read fails", async () => {
    effectiveStatus = 500;
    effectiveValues = { [COLLAPSED_GROUPS_KEY]: ["admin", "test"] };
    renderSidebar();

    await screen.findByTestId("sidebar-group-toggle-overview");
    // Degradation is today's behaviour: no stored state, nothing collapsed.
    for (const groupId of GROUP_IDS) {
      expect(toggle(groupId)).toHaveAttribute("aria-expanded", "true");
    }
    expect(
      screen.getByTestId("sidebar-group-toggle-overview")
    ).toBeInTheDocument();
    expect(screen.getByText("Dashboard").closest("a")).toBeVisible();
  });
});
