/**
 * Issue #672 — "Silent data loss: no unsaved-changes warning".
 *
 * Clicking a different element in the left navigation tree while the open
 * ArchitectureForm has unsaved local edits used to call `navigate()`
 * straight away, swapping the URL (and therefore the `element` prop) with
 * no confirmation at all — the edit was silently discarded. These tests
 * exercise the full ArchitectureEditors + ArchitectureForm + WorkspaceTree
 * wiring to prove the confirmation now gates that navigation.
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

// See RequirementEditors.unsaved-changes.test.tsx for why `vi.hoisted` is
// needed here (`vi.mock` factories are hoisted above plain top-level consts).
const { ELEMENT_A, ELEMENT_B } = vi.hoisted(() => ({
  ELEMENT_A: {
    id: "arch-aaa",
    workspace_id: "ws-001",
    title: "Element A",
    description: "desc a",
    element_type: "component",
    version: 1,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  },
  ELEMENT_B: {
    id: "arch-bbb",
    workspace_id: "ws-001",
    title: "Element B",
    description: "desc b",
    element_type: "component",
    version: 1,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  },
}));

vi.mock("../api/architecture", () => ({
  architectureApi: {
    list: vi.fn(),
    listAll: vi.fn().mockResolvedValue([ELEMENT_A, ELEMENT_B]),
    create: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
    get: vi.fn((id: string) =>
      Promise.resolve(id === ELEMENT_B.id ? ELEMENT_B : ELEMENT_A)
    ),
    reparent: vi.fn(),
    versions: vi.fn().mockResolvedValue([]),
    diff: vi.fn().mockResolvedValue({ fields: [], unchanged: [] }),
  },
}));

vi.mock("../api/tracelinks", () => ({
  tracelinksApi: {
    list: vi.fn(),
    listForArtifact: vi
      .fn()
      .mockResolvedValue({ count: 0, next: null, previous: null, results: [] }),
    create: vi.fn(),
    delete: vi.fn(),
    impact: vi.fn().mockResolvedValue([]),
  },
}));

vi.mock("../api/requirements", () => ({
  requirementsApi: {
    list: vi.fn().mockResolvedValue({ results: [], count: 0 }),
    listAll: vi.fn().mockResolvedValue([]),
    get: vi.fn(),
  },
}));

// Must import AFTER vi.mock
import ArchitectureEditors from "../components/ArchitectureEditors/ArchitectureEditors";
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

function renderEditor(elementId: string): ReturnType<typeof render> {
  sessionStorage.setItem("reqflow_token", "test-token");
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[`/architecture/${elementId}`]}>
        <AuthProvider>
          <ThemeProvider>
            <WorkspaceProvider>
              <Routes>
                <Route path="/architecture" element={<ArchitectureEditors />} />
                <Route path="/architecture/:id" element={<ArchitectureEditors />} />
              </Routes>
            </WorkspaceProvider>
          </ThemeProvider>
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("ArchitectureEditors — unsaved-changes confirmation before tree navigation (#672)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();
  });

  it("warns before discarding an unsaved edit when a different tree item is clicked, and stays on the current item if canceled", async () => {
    const user = userEvent.setup();
    renderEditor(ELEMENT_A.id);

    await waitFor(() => expect(screen.getByTestId("arch-title")).toHaveValue("Element A"));

    await user.clear(screen.getByTestId("arch-title"));
    await user.type(screen.getByTestId("arch-title"), "Unsaved edit");
    expect(screen.getByTestId("arch-title")).toHaveValue("Unsaved edit");

    await user.click(screen.getByTestId(`arch-tree-node-${ELEMENT_B.id}`));

    const dialog = await screen.findByTestId("arch-unsaved-changes-dialog");
    expect(dialog).toBeInTheDocument();

    await user.click(screen.getByTestId("arch-unsaved-changes-dialog-cancel"));
    expect(screen.queryByTestId("arch-unsaved-changes-dialog")).not.toBeInTheDocument();
    expect(screen.getByTestId("arch-title")).toHaveValue("Unsaved edit");
  });

  it("navigates and discards the unsaved edit once the user confirms", async () => {
    const user = userEvent.setup();
    renderEditor(ELEMENT_A.id);

    await waitFor(() => expect(screen.getByTestId("arch-title")).toHaveValue("Element A"));

    await user.clear(screen.getByTestId("arch-title"));
    await user.type(screen.getByTestId("arch-title"), "Unsaved edit");

    await user.click(screen.getByTestId(`arch-tree-node-${ELEMENT_B.id}`));
    await screen.findByTestId("arch-unsaved-changes-dialog");

    await user.click(screen.getByTestId("arch-unsaved-changes-dialog-confirm"));

    await waitFor(() => expect(screen.getByTestId("arch-title")).toHaveValue("Element B"));
    expect(screen.queryByTestId("arch-unsaved-changes-dialog")).not.toBeInTheDocument();
  });

  it("navigates immediately, without any dialog, when the form has no unsaved edits", async () => {
    const user = userEvent.setup();
    renderEditor(ELEMENT_A.id);

    await waitFor(() => expect(screen.getByTestId("arch-title")).toHaveValue("Element A"));

    await user.click(screen.getByTestId(`arch-tree-node-${ELEMENT_B.id}`));

    await waitFor(() => expect(screen.getByTestId("arch-title")).toHaveValue("Element B"));
    expect(screen.queryByTestId("arch-unsaved-changes-dialog")).not.toBeInTheDocument();
  });
});
