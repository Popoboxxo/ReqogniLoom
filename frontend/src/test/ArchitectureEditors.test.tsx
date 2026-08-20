/**
 * ARCH-L1-001 ReactFrontend — ArchitectureEditors unit test.
 *
 * leaf_id: COMP-RF-004 (ArchitectureEditors)
 * req_id:  REQ-L2-RF-004 (Architecture-Editor),
 *          REQ-L3-RF004-001 (CRUD — all fields visible and editable),
 *          REQ-L3-RF004-002 (Markdown-Description-Editing)
 *
 * Acceptance criterion (REQ-L2-RF-004 AC):
 *   Unit-Test: Render ArchitectureEditor with Mock-ArchitectureElement →
 *   alle Felder sichtbar und editierbar.
 *
 * REST mocked: architectureApi.list, architectureApi.update, tracelinksApi.listForArtifact
 */

import React from "react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";

// ---------------------------------------------------------------------------
// Mock API modules
// ---------------------------------------------------------------------------

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

vi.mock("../api/architecture", () => ({
  architectureApi: {
    list: vi.fn(),
    listAll: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
    get: vi.fn(),
    reparent: vi.fn(),
    versions: vi.fn().mockResolvedValue([]),
    diff: vi.fn().mockResolvedValue({ fields: [], unchanged: [] }),
  },
}));

vi.mock("../api/tracelinks", () => ({
  tracelinksApi: {
    list: vi.fn(),
    listForArtifact: vi.fn(),
    create: vi.fn(),
    delete: vi.fn(),
    // <TraceSpine> composes the derivation chain from two neighbourhood
    // queries (UI concept ch. 5). Empty results are the correct fixture
    // here: this spec is about the editor fields, not about the chain.
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
import { architectureApi } from "../api/architecture";
import { tracelinksApi } from "../api/tracelinks";
import { requirementsApi } from "../api/requirements";
import { AuthProvider } from "../context/AuthContext";
import { WorkspaceProvider } from "../context/WorkspaceContext";
import { ThemeProvider } from "../context/ThemeContext";

// jsdom in this test runtime does not provide window.localStorage (Node's
// --localstorage-file experimental flag is not set), which ThemeProvider
// (now a WorkspaceProvider dependency, #568 phase 1) reads synchronously on
// mount. Polyfill a minimal in-memory implementation so it does not throw.
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

// ---------------------------------------------------------------------------
// Mock data
// ---------------------------------------------------------------------------

const MOCK_ELEMENT = {
  id: "arch-001",
  workspace_id: "ws-001",
  title: "AuthService",
  description: "## Auth\nHandles authentication.",
  element_type: "component",
  version: 1,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

// ---------------------------------------------------------------------------
// Render helper
// ---------------------------------------------------------------------------

function renderEditor(elementId?: string): ReturnType<typeof render> {
  sessionStorage.setItem("reqflow_token", "test-token");

  const path = elementId ? `/architecture/${elementId}` : "/architecture";

  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[path]}>
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

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("ArchitectureEditors (COMP-RF-004 / REQ-L2-RF-004)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();

    // Default mock implementations
    vi.mocked(architectureApi.list).mockResolvedValue({
      count: 1,
      next: null,
      previous: null,
      results: [MOCK_ELEMENT],
    });

    vi.mocked(architectureApi.list).mockResolvedValue({
      results: [MOCK_ELEMENT],
      count: 1,
    } as any);
    vi.mocked(architectureApi.listAll).mockResolvedValue([MOCK_ELEMENT] as any);

    vi.mocked(requirementsApi.list).mockResolvedValue({
      results: [],
      count: 0,
    });
    vi.mocked(requirementsApi.listAll).mockResolvedValue([]);

    vi.mocked(architectureApi.get).mockResolvedValue(MOCK_ELEMENT);

    vi.mocked(tracelinksApi.listForArtifact).mockResolvedValue({
      count: 0,
      next: null,
      previous: null,
      results: [],
    });
  });

  it("renders element list with mock element", async () => {
    renderEditor();

    await waitFor(() => {
      expect(screen.getByText("AuthService")).toBeInTheDocument();
    });
  });

  it("renders all editable fields when element is selected (REQ-L3-RF004-001 AC)", async () => {
    renderEditor(MOCK_ELEMENT.id);

    await waitFor(() => {
      // Title field
      expect(screen.getByTestId("arch-title")).toBeInTheDocument();
      // Element-type autocomplete input (REQ-006 / D5: free text, not a fixed dropdown)
      expect(screen.getByTestId("arch-element-type-select")).toBeInTheDocument();
      // Save button
      expect(screen.getByTestId("arch-save-btn")).toBeInTheDocument();
      // Delete button
      expect(screen.getByTestId("arch-delete-btn")).toBeInTheDocument();
    });

    // Title field should display mock element title
    const titleInput = screen.getByTestId("arch-title") as HTMLInputElement;
    expect(titleInput.value).toBe("AuthService");

    // Element type should be set to "component"
    const typeInput = screen.getByTestId("arch-element-type-select") as HTMLInputElement;
    expect(typeInput.value).toBe("component");
  });

  it("can change element type via free-text autocomplete (REQ-006 / D5 — Type-Auswahl)", async () => {
    const user = userEvent.setup();
    renderEditor(MOCK_ELEMENT.id);

    await waitFor(() => {
      expect(screen.getByTestId("arch-element-type-select")).toBeInTheDocument();
    });

    const typeInput = screen.getByTestId("arch-element-type-select") as HTMLInputElement;
    await user.clear(typeInput);
    await user.type(typeInput, "subsystem");
    expect(typeInput.value).toBe("subsystem");
  });

  it("allows entering a brand-new element type not present in the workspace (REQ-006 / D5)", async () => {
    const user = userEvent.setup();
    renderEditor(MOCK_ELEMENT.id);

    await waitFor(() => {
      expect(screen.getByTestId("arch-element-type-select")).toBeInTheDocument();
    });

    const typeInput = screen.getByTestId("arch-element-type-select") as HTMLInputElement;
    await user.clear(typeInput);
    await user.type(typeInput, "Actor");
    expect(typeInput.value).toBe("Actor");
  });

  it("calls architectureApi.update on save (REQ-L3-RF004-001 — Update)", async () => {
    const user = userEvent.setup();

    vi.mocked(architectureApi.update).mockResolvedValue({
      ...MOCK_ELEMENT,
      title: "AuthService Updated",
    });

    renderEditor(MOCK_ELEMENT.id);

    await waitFor(() => {
      expect(screen.getByTestId("arch-title")).toBeInTheDocument();
    });

    const titleInput = screen.getByTestId("arch-title");
    await user.clear(titleInput);
    await user.type(titleInput, "AuthService Updated");

    const saveBtn = screen.getByTestId("arch-save-btn");
    await user.click(saveBtn);

    await waitFor(() => {
      expect(architectureApi.update).toHaveBeenCalledWith(
        MOCK_ELEMENT.id,
        expect.objectContaining({ title: "AuthService Updated" })
      );
    });
  });

  it("shows delete confirmation dialog before delete (ADR-L3-RF-008)", async () => {
    const user = userEvent.setup();
    renderEditor(MOCK_ELEMENT.id);

    await waitFor(() => {
      expect(screen.getByTestId("arch-delete-btn")).toBeInTheDocument();
    });

    await user.click(screen.getByTestId("arch-delete-btn"));

    // Dialog should appear
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByTestId("confirm-delete-btn")).toBeInTheDocument();
  });

  it("renders split-pane divider for resizing (REQ-L3-RF-***: enable split-pane resizing)", async () => {
    renderEditor(MOCK_ELEMENT.id);

    await waitFor(() => {
      const divider = screen.getByTestId("splitview-divider");
      expect(divider).toBeInTheDocument();
      expect(divider).toHaveStyle("cursor: col-resize");
    });
  });

  // ---------------------------------------------------------------------
  // Task 4.4 — Virtualisierung überall (REQ-091)
  // ---------------------------------------------------------------------
  describe("virtualization (Task 4.4)", () => {
    // jsdom does not run layout, so the WorkspaceTree scroll container's
    // offsetHeight is always 0 and @tanstack/react-virtual would compute an
    // empty visible range. Patch a realistic container size (same technique
    // as workspace-tree.test.tsx's "real container size" block) so the
    // assertions exercise an actual windowed render.
    let offsetHeightSpy: ReturnType<typeof vi.spyOn>;
    let offsetWidthSpy: ReturnType<typeof vi.spyOn>;

    beforeEach(() => {
      offsetHeightSpy = vi
        .spyOn(HTMLElement.prototype, "offsetHeight", "get")
        .mockReturnValue(340);
      offsetWidthSpy = vi
        .spyOn(HTMLElement.prototype, "offsetWidth", "get")
        .mockReturnValue(800);
    });

    afterEach(() => {
      offsetHeightSpy.mockRestore();
      offsetWidthSpy.mockRestore();
    });

    it("mounts far fewer DOM tree rows than elements when the list is large (500 elements)", async () => {
      const LARGE_ELEMENTS = Array.from({ length: 500 }, (_, i) => ({
        ...MOCK_ELEMENT,
        id: `arch-${i}`,
        title: `Element ${i}`,
      }));
      vi.mocked(architectureApi.listAll).mockResolvedValue(LARGE_ELEMENTS as any);

      renderEditor();

      await waitFor(() => {
        expect(screen.getByTestId("arch-tree")).toBeInTheDocument();
      });

      // The WorkspaceTree windows the 500 rows down to a small on-screen
      // subset instead of mounting one DOM row per element.
      await waitFor(() => {
        const rows = screen.queryAllByRole("treeitem");
        expect(rows.length).toBeGreaterThan(0);
        expect(rows.length).toBeLessThan(LARGE_ELEMENTS.length);
      });

      // The last element is far outside the initial window.
      expect(screen.queryByTestId("arch-tree-node-arch-499")).not.toBeInTheDocument();
    });
  });
});

// ---------------------------------------------------------------------------
// GitHub #340 — same swallow-the-rejection defect as RequirementEditors
// ---------------------------------------------------------------------------

describe("ArchitectureEditors — server validation errors are visible (#340)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();

    vi.mocked(architectureApi.list).mockResolvedValue({
      results: [MOCK_ELEMENT],
      count: 1,
    } as any);
    vi.mocked(architectureApi.listAll).mockResolvedValue([MOCK_ELEMENT] as any);
    vi.mocked(architectureApi.get).mockResolvedValue(MOCK_ELEMENT as any);
    vi.mocked(requirementsApi.list).mockResolvedValue({
      results: [],
      count: 0,
    } as any);
    vi.mocked(requirementsApi.listAll).mockResolvedValue([]);
    vi.mocked(tracelinksApi.listForArtifact).mockResolvedValue({
      count: 0,
      next: null,
      previous: null,
      results: [],
    });
  });

  it("renders the server's rejection reason when a create is refused", async () => {
    vi.mocked(architectureApi.create).mockRejectedValueOnce({
      error: {
        code: "VALIDATION_ERROR",
        message: "Validation failed.",
        details: [
          {
            field: "title",
            errors: [
              "contains disallowed content: HTML markup is not permitted in free-text fields.",
            ],
          },
        ],
      },
    });
    const user = userEvent.setup();
    renderEditor();

    await waitFor(() =>
      expect(screen.getByTestId("create-arch-btn")).toBeInTheDocument()
    );
    await user.click(screen.getByTestId("create-arch-btn"));
    await user.type(
      screen.getByTestId("arch-new-title-input"),
      "<script>alert(1)</script>"
    );
    await user.click(screen.getByTestId("arch-new-save-btn"));

    const alert = await screen.findByTestId("arch-action-error");
    expect(alert).toHaveAttribute("role", "alert");
    expect(alert).toHaveTextContent(
      "HTML markup is not permitted in free-text fields."
    );
  });
});

/**
 * BUG-11 (Systemaudit 2026-08-18, §4, Mittel) — the quick create form only
 * had a title input; `description` is an ordinary architectureApi.create()
 * field the backend already accepts but had no editor here.
 */
describe("ArchitectureEditors — create form has a description field (BUG-11)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();

    vi.mocked(architectureApi.list).mockResolvedValue({
      results: [MOCK_ELEMENT],
      count: 1,
    } as any);
    vi.mocked(architectureApi.listAll).mockResolvedValue([MOCK_ELEMENT] as any);
    vi.mocked(architectureApi.get).mockResolvedValue(MOCK_ELEMENT as any);
    vi.mocked(requirementsApi.list).mockResolvedValue({
      results: [],
      count: 0,
    } as any);
    vi.mocked(requirementsApi.listAll).mockResolvedValue([]);
    vi.mocked(tracelinksApi.listForArtifact).mockResolvedValue({
      count: 0,
      next: null,
      previous: null,
      results: [],
    });
  });

  it("sends the typed description alongside the title on create", async () => {
    vi.mocked(architectureApi.create).mockResolvedValueOnce({
      ...MOCK_ELEMENT,
      id: "arch-new",
    } as any);
    const user = userEvent.setup();
    renderEditor();

    await waitFor(() =>
      expect(screen.getByTestId("create-arch-btn")).toBeInTheDocument()
    );
    await user.click(screen.getByTestId("create-arch-btn"));
    await user.type(screen.getByTestId("arch-new-title-input"), "New Element");
    await user.type(
      screen.getByTestId("arch-new-description-input"),
      "Some description"
    );
    await user.click(screen.getByTestId("arch-new-save-btn"));

    await waitFor(() =>
      expect(architectureApi.create).toHaveBeenCalledWith(
        expect.objectContaining({
          title: "New Element",
          description: "Some description",
        })
      )
    );
  });
});

// ---------------------------------------------------------------------------
// Drag & drop reparenting of the decomposition hierarchy.
//
// Reinstated by user decision 2026-08-15, reversing the "won't do" note that
// had sat on the tree since 2026-07-13. The tree itself only reports the drop;
// the PATCH and the error handling live here, sharing the list-level error
// banner with create/delete (#340).
// ---------------------------------------------------------------------------

describe("ArchitectureEditors — drag & drop reparenting", () => {
  const ROOT_ELEMENT = { ...MOCK_ELEMENT, id: "arch-001", title: "AuthService" };
  const SECOND_ELEMENT = {
    ...MOCK_ELEMENT,
    id: "arch-002",
    title: "TokenStore",
    parent_id: null,
  };

  /** Minimal DataTransfer stand-in — jsdom ships none. */
  function makeDataTransfer(): {
    setData: (format: string, value: string) => void;
    getData: (format: string) => string;
    dropEffect: string;
    effectAllowed: string;
  } {
    const store: Record<string, string> = {};
    return {
      setData: (format, value) => {
        store[format] = value;
      },
      getData: (format) => store[format] ?? "",
      dropEffect: "",
      effectAllowed: "",
    };
  }

  async function dragElementOnto(fromId: string, toId: string): Promise<void> {
    const from = await screen.findByTestId(`arch-tree-node-${fromId}`);
    const to = await screen.findByTestId(`arch-tree-node-${toId}`);
    const dataTransfer = makeDataTransfer();
    fireEvent.dragStart(from, { dataTransfer });
    fireEvent.dragOver(to, { dataTransfer });
    fireEvent.drop(to, { dataTransfer });
  }

  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();

    vi.mocked(architectureApi.list).mockResolvedValue({
      results: [ROOT_ELEMENT, SECOND_ELEMENT],
      count: 2,
    } as any);
    vi.mocked(architectureApi.listAll).mockResolvedValue([
      ROOT_ELEMENT,
      SECOND_ELEMENT,
    ] as any);
    vi.mocked(architectureApi.get).mockResolvedValue(ROOT_ELEMENT as any);
    vi.mocked(architectureApi.reparent).mockResolvedValue(SECOND_ELEMENT as any);
    vi.mocked(requirementsApi.list).mockResolvedValue({
      results: [],
      count: 0,
    } as any);
    vi.mocked(requirementsApi.listAll).mockResolvedValue([]);
    vi.mocked(tracelinksApi.listForArtifact).mockResolvedValue({
      count: 0,
      next: null,
      previous: null,
      results: [],
    });
  });

  it("PATCHes the new parent when an element is dropped onto another", async () => {
    renderEditor();

    await dragElementOnto("arch-002", "arch-001");

    await waitFor(() =>
      expect(architectureApi.reparent).toHaveBeenCalledWith(
        "arch-002",
        "arch-001"
      )
    );
  });

  it("detaches an element to root level when dropped on the root dropzone", async () => {
    // A child element, so that a drop on the root zone is a real change.
    const CHILD = { ...MOCK_ELEMENT, id: "arch-003", title: "SessionCache", parent_id: "arch-001" };
    vi.mocked(architectureApi.list).mockResolvedValue({
      results: [ROOT_ELEMENT, CHILD],
      count: 2,
    } as any);
    vi.mocked(architectureApi.listAll).mockResolvedValue([
      ROOT_ELEMENT,
      CHILD,
    ] as any);

    renderEditor();

    const child = await screen.findByTestId("arch-tree-node-arch-003");
    const dataTransfer = makeDataTransfer();
    fireEvent.dragStart(child, { dataTransfer });

    const dropzone = await screen.findByTestId("arch-tree-root-dropzone");
    fireEvent.dragOver(dropzone, { dataTransfer });
    fireEvent.drop(dropzone, { dataTransfer });

    await waitFor(() =>
      expect(architectureApi.reparent).toHaveBeenCalledWith("arch-003", null)
    );
  });

  it("shows the server's reason inline when the reparent is refused", async () => {
    // The backend owns the hierarchy invariant (cycles, depth); the tree
    // forwards such drops deliberately instead of second-guessing it.
    vi.mocked(architectureApi.reparent).mockRejectedValueOnce({
      error: {
        code: "VALIDATION_ERROR",
        message: "Validation failed.",
        details: [
          {
            field: "parent_id",
            errors: ["would create a cycle in the architecture hierarchy."],
          },
        ],
      },
    });

    renderEditor();

    await dragElementOnto("arch-002", "arch-001");

    const alert = await screen.findByTestId("arch-action-error");
    expect(alert).toHaveAttribute("role", "alert");
    expect(alert).toHaveTextContent(
      "would create a cycle in the architecture hierarchy."
    );
  });

  it("does not call the API when an element is dropped on itself", async () => {
    renderEditor();

    await dragElementOnto("arch-002", "arch-002");

    expect(architectureApi.reparent).not.toHaveBeenCalled();
  });

  it("does not call the API when an element is dropped on its own descendant", async () => {
    // Matches what the edit form already prevents by filtering descendants out
    // of its parent dropdown. Server-side invariant I1 only runs at
    // Standard/Extended rigor, so a Minimal workspace would otherwise persist
    // the cycle and lose the subtree from the tree view.
    const CHILD = {
      ...MOCK_ELEMENT,
      id: "arch-003",
      title: "SessionCache",
      parent_id: "arch-001",
    };
    const GRANDCHILD = {
      ...MOCK_ELEMENT,
      id: "arch-004",
      title: "CacheEntry",
      parent_id: "arch-003",
    };
    vi.mocked(architectureApi.list).mockResolvedValue({
      results: [ROOT_ELEMENT, CHILD, GRANDCHILD],
      count: 3,
    } as any);
    vi.mocked(architectureApi.listAll).mockResolvedValue([
      ROOT_ELEMENT,
      CHILD,
      GRANDCHILD,
    ] as any);

    renderEditor();

    // arch-003 is collapsed by default (only roots auto-expand).
    const toggle = await screen.findByTestId("arch-tree-toggle-arch-003");
    fireEvent.click(toggle);

    await dragElementOnto("arch-001", "arch-004");

    expect(architectureApi.reparent).not.toHaveBeenCalled();
  });
});
