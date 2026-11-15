/**
 * G1 (spec 2026-11-08 §4.1/§4.2/§4.5, plan 2026-11-15 G1.1) — the group
 * administration is a **dialog**, not a permanently mounted panel.
 *
 * Before this change `RequirementList` rendered `<GroupManager>` above the
 * toolbar through a `groupPanel` slot: ~110px of chrome plus ~110px per group
 * and ~20px per member stood between the toolbar and the first tree row, on a
 * column the same spec shares with the detail form. The tree now starts
 * directly under the toolbar and the manager opens on demand from
 * `req-list-groups-btn` (spec §4.2).
 *
 * Acceptance covered here (§4.5.1, §4.5.2, §4.5.5):
 *  - idle state: no `group-manager` in the DOM,
 *  - the toolbar trigger opens `group-manager-dialog`,
 *  - Escape closes it and returns focus to the trigger,
 *  - a viewer sees no trigger at all (not merely a disabled one),
 *  - the left column holds only the show-deleted toggle and the tree,
 *  - the unchanged `GroupManager` surface (create form, existing groups) is
 *    still reachable inside the dialog.
 */

import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";

// Mutable so a test can simulate a non-editor session without re-declaring the
// whole client mock (same pattern as include-deleted-toggle.test.tsx).
let mockAuthRoles: string[] = ["editor"];

// Real copy from the German locale instead of a full i18next stack: the
// trigger's accessible name IS its visible label, so the assertion has to see
// translation, not the key. `i18n.language` is read directly by
// `FieldShell`/`ArtifactForm`, hence the stub field (same shape as
// RequirementList.roleGate.test.tsx, plus the shared key resolver).
vi.mock("react-i18next", async (importActual) => {
  const actual = await importActual<typeof import("react-i18next")>();
  return {
    ...actual,
    useTranslation: () => ({
      t: (key: string, fallback?: string) =>
        resolveLocaleKey(key) ?? fallback ?? key,
      i18n: { language: "de", t: (key: string) => resolveLocaleKey(key) ?? key },
      ready: true,
    }),
  };
});

// Partial mock: `AuthContext` also imports the session-generation plumbing
// (`advanceAuthSessionGeneration`, `resetUnauthorizedGuard`). Replacing the
// whole module would leave those `undefined`, and the identity restore would
// throw into its own `catch` — leaving every role gate closed and making a
// "no trigger" assertion pass for the wrong reason.
vi.mock("../../api/client", async (importActual) => {
  const actual = await importActual<typeof import("../../api/client")>();
  return {
    ...actual,
    getList: vi.fn().mockResolvedValue({ results: [], count: 0 }),
    extractErrorMessage: vi.fn().mockReturnValue("Error"),
    setAuthToken: vi.fn(),
    setUnauthorizedHandler: vi.fn(),
    apiClient: {
      get: vi.fn((path?: string) =>
        Promise.resolve(
          path === "/auth/me/"
            ? {
                user: {
                  id: "u-1",
                  username: "tester",
                  email: "t@x.test",
                  first_name: "",
                  last_name: "",
                  is_active: true,
                  tenant_id: "t-1",
                  roles: mockAuthRoles,
                },
                tenant_id: "t-1",
                roles: mockAuthRoles,
              }
            : {},
        ),
      ),
      post: vi.fn().mockResolvedValue({}),
      put: vi.fn().mockResolvedValue({}),
      patch: vi.fn().mockResolvedValue({}),
      delete: vi.fn().mockResolvedValue({}),
    },
  };
});

vi.mock("../../api/requirements", () => ({
  requirementsApi: {
    list: vi.fn(),
    listAll: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
    get: vi.fn(),
    versions: vi.fn().mockResolvedValue([]),
    diff: vi.fn().mockResolvedValue({ fields: [], unchanged: [] }),
    getTransitions: vi.fn().mockResolvedValue({
      current_state: "draft",
      states: ["draft"],
      allowed_transitions: [],
    }),
    transition: vi.fn().mockResolvedValue({}),
    aiDecomposeNextLevel: vi
      .fn()
      .mockResolvedValue({ drafts: [], parent_requirement_id: "req-1" }),
  },
}));

vi.mock("../../api/tracelinks", () => ({
  tracelinksApi: {
    list: vi.fn(),
    listForArtifact: vi.fn().mockResolvedValue({ results: [] }),
    create: vi.fn(),
    delete: vi.fn(),
    impact: vi.fn().mockResolvedValue([]),
  },
}));

vi.mock("../../api/traceability", () => ({
  traceabilityApi: { resolve: vi.fn().mockResolvedValue([]) },
}));

vi.mock("../../api/workspaces", () => ({
  workspacesApi: { list: vi.fn(), downloadPdfReport: vi.fn() },
}));

vi.mock("../../api/testcases", () => ({
  testcasesApi: { list: vi.fn().mockResolvedValue({ results: [], count: 0 }) },
}));

// P6 Task 6.3: the group surface is read through `loadGroupsWithMembers` and
// written through `groupsApi`. Stubbed so the page renders without a network
// round trip while the *unchanged* GroupManager contract stays exercised.
vi.mock("../../api/groups", () => ({
  loadGroupsWithMembers: vi.fn(),
  groupsApi: {
    list: vi.fn(),
    create: vi.fn(),
    members: vi.fn(),
    addMember: vi.fn(),
    removeMember: vi.fn(),
    moveMember: vi.fn(),
  },
}));

// Must be imported AFTER the vi.mock calls.
import RequirementEditors from "./RequirementEditors";
import { requirementsApi } from "../../api/requirements";
import { groupsApi, loadGroupsWithMembers } from "../../api/groups";
import { AuthProvider } from "../../context/AuthContext";
import { WorkspaceProvider } from "../../context/WorkspaceContext";
import { ThemeProvider } from "../../context/ThemeContext";
import { resolveLocaleKey } from "../../test/i18n-test-helpers";

// jsdom in this test runtime does not provide window.localStorage, which
// ThemeProvider (a WorkspaceProvider dependency) reads synchronously on mount.
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
installLocalStorageStub();

const REQUIREMENT = {
  id: "req-1",
  workspace_id: "ws-001",
  artifact_id: "art-req-1",
  title: "Brake pressure",
  description: "",
  category: "functional",
  status: "draft",
  change_reason: "",
  version: 1,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

const GROUP = {
  id: "grp-1",
  workspace_id: "ws-001",
  title: "Brake system",
  description: "Anything that slows the car",
  members: [
    {
      trace_link_id: "tl-1",
      requirement_artifact_id: "art-req-1",
      sort_key: "a",
    },
  ],
};

function renderEditor(): ReturnType<typeof render> {
  sessionStorage.setItem("reqflow_token", "test-token");
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/requirements"]}>
        <AuthProvider>
          <ThemeProvider>
            <WorkspaceProvider>
              <Routes>
                <Route path="/requirements" element={<RequirementEditors />} />
              </Routes>
            </WorkspaceProvider>
          </ThemeProvider>
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

/** Waits until the list (and therefore the toolbar) is on screen. */
async function renderReady(): Promise<ReturnType<typeof render>> {
  const view = renderEditor();
  await waitFor(() => {
    expect(screen.getByTestId("req-list-toolbar")).toBeInTheDocument();
  });
  return view;
}

/**
 * The trigger is role-gated, and the role only exists once `GET /auth/me/` has
 * resolved — so every editor-side assertion waits for the button itself rather
 * than for the toolbar (which is role-independent and appears earlier).
 */
async function findGroupsButton(): Promise<HTMLElement> {
  return screen.findByTestId("req-list-groups-btn");
}

describe("RequirementEditors — group management as a dialog (G1)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();
    mockAuthRoles = ["editor"];
    vi.mocked(requirementsApi.listAll).mockResolvedValue([REQUIREMENT]);
    vi.mocked(loadGroupsWithMembers).mockResolvedValue([GROUP]);
  });

  it("mounts no group manager in the idle state", async () => {
    await renderReady();

    expect(screen.queryByTestId("group-manager")).not.toBeInTheDocument();
    expect(screen.queryByTestId("group-manager-dialog")).not.toBeInTheDocument();
  });

  it("keeps the left column to the show-deleted toggle and the tree", async () => {
    await renderReady();

    // The left panel is the SplitView's list column: RequirementEditors renders
    // exactly <IncludeDeletedToggle> + <RequirementList> as its children.
    const leftColumn = screen.getByTestId("splitview-list");

    expect(within(leftColumn).getByTestId("req-list-tree")).toBeInTheDocument();
    expect(
      within(leftColumn).queryByTestId("group-manager"),
    ).not.toBeInTheDocument();
  });

  it("opens the group dialog from the toolbar button", async () => {
    const user = userEvent.setup();
    await renderReady();

    const trigger = await findGroupsButton();
    expect(trigger).toHaveAttribute("aria-haspopup", "dialog");
    expect(trigger).toHaveTextContent("Gruppen");

    await user.click(trigger);

    const dialog = screen.getByTestId("group-manager-dialog");
    expect(dialog).toHaveAttribute("role", "dialog");
    expect(within(dialog).getByTestId("group-manager")).toBeInTheDocument();
  });

  it("closes on Escape and returns focus to the trigger", async () => {
    const user = userEvent.setup();
    await renderReady();

    const trigger = await findGroupsButton();
    await user.click(trigger);
    expect(screen.getByTestId("group-manager-dialog")).toBeInTheDocument();

    await user.keyboard("{Escape}");

    await waitFor(() => {
      expect(
        screen.queryByTestId("group-manager-dialog"),
      ).not.toBeInTheDocument();
    });
    expect(screen.queryByTestId("group-manager")).not.toBeInTheDocument();
    expect(document.activeElement).toBe(trigger);
  });

  it("keeps the unchanged group functions reachable inside the dialog", async () => {
    const user = userEvent.setup();
    await renderReady();

    await user.click(await findGroupsButton());
    const dialog = screen.getByTestId("group-manager-dialog");

    // Read side: the existing group and its member render through GroupManager.
    await waitFor(() => {
      expect(within(dialog).getByTestId("group-item-grp-1")).toBeInTheDocument();
    });
    expect(within(dialog).getByTestId("group-member-grp-1-req-1")).toBeInTheDocument();

    // Write side: the create form is the GroupManager's own, unchanged.
    await user.type(within(dialog).getByTestId("group-title-input"), "Chassis");
    await user.click(within(dialog).getByTestId("group-create-btn"));

    await waitFor(() => {
      expect(groupsApi.create).toHaveBeenCalledWith(
        expect.any(String),
        "Chassis",
        "",
      );
    });
  });

  it("shows no group trigger to a viewer", async () => {
    mockAuthRoles = ["viewer"];
    await renderReady();

    // The tree being rendered proves the page settled; the editor counterpart
    // above proves the same setup *does* yield the trigger once the role is
    // there, so this absence is a role gate and not a timing artefact.
    await screen.findByTestId("req-list-tree");
    await waitFor(() => {
      expect(screen.queryByTestId("req-list-groups-btn")).not.toBeInTheDocument();
    });
  });

  /**
   * G2 (spec §4.5.3): the row action opens the dialog for *that* requirement,
   * and the membership write goes through the group hook — which re-reads the
   * groups, so the folder counter and the "in N Gruppen" marker update without
   * a route reload.
   */
  it("opens the add-to-group dialog from the row action and reloads groups after the add", async () => {
    const user = userEvent.setup();
    // A second group without the requirement in it: exactly the assign case.
    vi.mocked(loadGroupsWithMembers).mockResolvedValue([
      GROUP,
      {
        id: "grp-2",
        workspace_id: "ws-001",
        title: "Chassis",
        description: "",
        members: [],
      },
    ]);
    vi.mocked(groupsApi.addMember).mockResolvedValue([]);
    await renderReady();

    const rowAction = await screen.findByTestId("req-row-group-req-1");
    expect(rowAction).toHaveAttribute("aria-haspopup", "dialog");
    await user.click(rowAction);

    const dialog = await screen.findByTestId("add-to-group-dialog");
    // This suite's i18n stub does not interpolate, so the title is asserted on
    // its stable part; the interpolated name is covered in
    // src/test/AddToGroupDialog.test.tsx.
    expect(
      within(dialog).getByText(/Zu Gruppe hinzufügen/),
    ).toBeInTheDocument();
    // Existing membership is read from the same hook the manager uses.
    expect(within(dialog).getByTestId("group-add-member-grp-1")).toBeChecked();
    expect(within(dialog).getByTestId("group-add-member-grp-1")).toBeDisabled();

    const readsBefore = vi.mocked(loadGroupsWithMembers).mock.calls.length;
    await user.click(within(dialog).getByTestId("group-add-member-grp-2"));

    await waitFor(() => {
      expect(groupsApi.addMember).toHaveBeenCalledWith("grp-2", "req-1");
    });
    // The hook's reload: one more group read, no route navigation.
    await waitFor(() => {
      expect(vi.mocked(loadGroupsWithMembers).mock.calls.length).toBeGreaterThan(
        readsBefore,
      );
    });
    expect(screen.getByTestId("add-to-group-dialog")).toBeInTheDocument();
  });

  it("shows no row-level group action to a viewer", async () => {
    mockAuthRoles = ["viewer"];
    await renderReady();

    await screen.findByTestId("req-list-tree");
    expect(screen.queryByTestId("req-row-group-req-1")).not.toBeInTheDocument();
  });
});
