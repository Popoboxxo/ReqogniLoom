/**
 * Issue #672 — "Silent data loss: no unsaved-changes warning".
 *
 * Clicking a different artifact in the left navigation tree while the open
 * RequirementForm has unsaved local edits used to call `navigate()`
 * straight away, swapping the URL (and therefore the `requirement` prop)
 * with no confirmation at all — the edit was silently discarded. These
 * tests exercise the full RequirementEditors + RequirementForm +
 * WorkspaceTree wiring to prove the confirmation now gates that navigation.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";

vi.mock("../api/client", async (importActual) => ({
  ...(await importActual<typeof import("../api/client")>()),
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
                roles: ["admin"],
              },
              tenant_id: "t-1",
              roles: ["admin"],
            }
          : {}
      )
    ),
    post: vi.fn().mockResolvedValue({}),
    put: vi.fn().mockResolvedValue({}),
    patch: vi.fn().mockResolvedValue({}),
    delete: vi.fn().mockResolvedValue({}),
  },
}));

// `vi.mock` factories are hoisted above the rest of the module — plain
// top-level `const`s referenced inside them are not yet initialized at that
// point. `vi.hoisted` runs its callback before the hoisted mocks instead.
const { REQ_A, REQ_B } = vi.hoisted(() => ({
  REQ_A: {
    id: "req-aaa",
    workspace_id: "ws-001",
    title: "Requirement A",
    description: "desc a",
    category: "functional",
    status: "approved",
    change_reason: "",
    version: 1,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  },
  REQ_B: {
    id: "req-bbb",
    workspace_id: "ws-001",
    title: "Requirement B",
    description: "desc b",
    category: "functional",
    status: "approved",
    change_reason: "",
    version: 1,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  },
}));

vi.mock("../api/requirements", () => ({
  requirementsApi: {
    list: vi.fn(),
    listAll: vi.fn().mockResolvedValue([REQ_A, REQ_B]),
    create: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
    get: vi.fn((id: string) => Promise.resolve(id === REQ_B.id ? REQ_B : REQ_A)),
    versions: vi.fn().mockResolvedValue([]),
    diff: vi.fn().mockResolvedValue({ fields: [], unchanged: [] }),
    getTransitions: vi.fn().mockResolvedValue({
      current_state: "approved",
      states: ["draft", "approved", "deprecated"],
      allowed_transitions: [],
    }),
    transition: vi.fn().mockResolvedValue({}),
    aiDecomposeNextLevel: vi.fn().mockResolvedValue({ drafts: [], parent_requirement_id: "req-aaa" }),
  },
}));

vi.mock("../api/tracelinks", () => ({
  tracelinksApi: {
    list: vi.fn(),
    listForArtifact: vi.fn().mockResolvedValue({ count: 0, next: null, previous: null, results: [] }),
    create: vi.fn(),
    delete: vi.fn(),
    impact: vi.fn().mockResolvedValue([]),
  },
}));

vi.mock("../api/traceability", () => ({
  traceabilityApi: { resolve: vi.fn().mockResolvedValue([]) },
}));

vi.mock("../api/workspaces", () => ({
  workspacesApi: { list: vi.fn(), downloadPdfReport: vi.fn() },
}));

vi.mock("../api/testcases", () => ({
  testcasesApi: { list: vi.fn().mockResolvedValue({ count: 0, next: null, previous: null, results: [] }) },
}));

vi.mock("../components/shared/ArtifactInspector", async (importActual) => {
  const actual = await importActual<typeof import("../components/shared/ArtifactInspector")>();
  return { ...actual, RightSidebar: () => <div data-testid="artifact-inspector" /> };
});

// Must import AFTER vi.mock
import RequirementEditors from "../components/RequirementEditors/RequirementEditors";
import { AuthProvider } from "../context/AuthContext";
import { WorkspaceProvider } from "../context/WorkspaceContext";
import { ThemeProvider } from "../context/ThemeContext";

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

function renderEditor(requirementId: string): ReturnType<typeof render> {
  sessionStorage.setItem("reqflow_token", "test-token");
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[`/requirements/${requirementId}`]}>
        <AuthProvider>
          <ThemeProvider>
            <WorkspaceProvider>
              <Routes>
                <Route path="/requirements" element={<RequirementEditors />} />
                <Route path="/requirements/:id" element={<RequirementEditors />} />
              </Routes>
            </WorkspaceProvider>
          </ThemeProvider>
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("RequirementEditors — unsaved-changes confirmation before tree navigation (#672)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();
  });

  it("warns before discarding an unsaved edit when a different tree item is clicked, and stays on the current item if canceled", async () => {
    const user = userEvent.setup();
    renderEditor(REQ_A.id);

    await waitFor(() => expect(screen.getByTestId("req-title")).toHaveValue("Requirement A"));

    await user.clear(screen.getByTestId("req-title"));
    await user.type(screen.getByTestId("req-title"), "Unsaved edit");
    expect(screen.getByTestId("req-title")).toHaveValue("Unsaved edit");

    await user.click(screen.getByTestId(`req-list-tree-node-${REQ_B.id}`));

    const dialog = await screen.findByTestId("req-unsaved-changes-dialog");
    expect(dialog).toBeInTheDocument();

    // Canceling must not navigate — the unsaved edit is still visible.
    await user.click(screen.getByTestId("req-unsaved-changes-dialog-cancel"));
    expect(screen.queryByTestId("req-unsaved-changes-dialog")).not.toBeInTheDocument();
    expect(screen.getByTestId("req-title")).toHaveValue("Unsaved edit");
  });

  it("navigates and discards the unsaved edit once the user confirms", async () => {
    const user = userEvent.setup();
    renderEditor(REQ_A.id);

    await waitFor(() => expect(screen.getByTestId("req-title")).toHaveValue("Requirement A"));

    await user.clear(screen.getByTestId("req-title"));
    await user.type(screen.getByTestId("req-title"), "Unsaved edit");

    await user.click(screen.getByTestId(`req-list-tree-node-${REQ_B.id}`));
    await screen.findByTestId("req-unsaved-changes-dialog");

    await user.click(screen.getByTestId("req-unsaved-changes-dialog-confirm"));

    await waitFor(() =>
      expect(screen.getByTestId("req-title")).toHaveValue("Requirement B")
    );
    expect(screen.queryByTestId("req-unsaved-changes-dialog")).not.toBeInTheDocument();
  });

  it("navigates immediately, without any dialog, when the form has no unsaved edits", async () => {
    const user = userEvent.setup();
    renderEditor(REQ_A.id);

    await waitFor(() => expect(screen.getByTestId("req-title")).toHaveValue("Requirement A"));

    await user.click(screen.getByTestId(`req-list-tree-node-${REQ_B.id}`));

    await waitFor(() =>
      expect(screen.getByTestId("req-title")).toHaveValue("Requirement B")
    );
    expect(screen.queryByTestId("req-unsaved-changes-dialog")).not.toBeInTheDocument();
  });

  /**
   * Regression test for a stale-dirty-flag bug found in code review: the
   * `onDirtyChange` reporting effect had no cleanup, so unmounting
   * `RequirementForm` while `isDirty` was still `true` (e.g. via Cancel,
   * which navigates away and unmounts the form without ever reporting
   * `isDirty(false)`) left the parent's `isFormDirty` state stuck at `true`.
   * The very next tree click then wrongly showed the unsaved-changes dialog
   * even though no form was open anymore.
   */
  it("does not show the unsaved-changes dialog for a tree click after Cancel discarded the dirty form", async () => {
    const user = userEvent.setup();
    renderEditor(REQ_A.id);

    await waitFor(() => expect(screen.getByTestId("req-title")).toHaveValue("Requirement A"));

    await user.clear(screen.getByTestId("req-title"));
    await user.type(screen.getByTestId("req-title"), "Unsaved edit");
    expect(screen.getByTestId("req-title")).toHaveValue("Unsaved edit");

    // Cancel navigates to `/requirements` (no id), unmounting the dirty
    // RequirementForm without ever going through the confirm dialog.
    await user.click(screen.getByTestId("cancel-btn"));
    await waitFor(() => expect(screen.queryByTestId("req-title")).not.toBeInTheDocument());

    // A stale `isFormDirty=true` would now wrongly gate this click behind
    // the unsaved-changes dialog, even though no form is open anymore.
    await user.click(screen.getByTestId(`req-list-tree-node-${REQ_B.id}`));

    await waitFor(() =>
      expect(screen.getByTestId("req-title")).toHaveValue("Requirement B")
    );
    expect(screen.queryByTestId("req-unsaved-changes-dialog")).not.toBeInTheDocument();
  });
});
