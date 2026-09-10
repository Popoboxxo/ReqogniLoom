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
// Task 24: ArchitectureArtifactForm's FieldShell reads `i18n.language`
// directly (`helpText()`, FieldShell.tsx) — without the real i18next
// singleton initialised, `language` is `undefined` and `.startsWith()`
// throws. Same import ArchitectureEditors.test.tsx already relies on.
import "../i18n/index";

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
    delete: vi.fn().mockResolvedValue({}),
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

// Task 23 (traceability-semantik): CreateTraceLinkDialog (mounted inside
// TraceLinkPanel, which this tree pulls in transitively) now reads the
// link-type catalog via useLinkTypes() — needs a provider-free mock here,
// same as every other non-dialog-focused test that renders it incidentally.
vi.mock("../context/LinkTypeContext", () => ({
  useLinkTypes: () => ({
    linkTypes: [],
    isLoading: false,
    error: null,
    reload: vi.fn(),
    creatableLinkTypes: [],
    definitionFor: () => undefined,
    isAllowedPair: () => false,
    labelFor: (key: string) => key,
  }),
}));

// Task 24 (attribute-definition): ArchitectureEditors now renders
// ArchitectureArtifactForm, which resolves its field set from the
// attribute-definition API — see the identical mock/rationale in
// ArchitectureEditors.test.tsx.
vi.mock("../api/attribute-definitions", () => ({
  attributeDefinitionsApi: {
    getWorkspace: vi.fn().mockResolvedValue({
      item_type: "ArchitectureElement",
      preset: "standard",
      is_customized: false,
      version: 1,
      attributes: [
        {
          name: "title", kind: "core", type: "text", widget_key: null, fields: [],
          options: [], required: true, visible: true, locked: false, editable: true,
          section: "general", order: 1, label: { de: "", en: "" },
          help_text: { de: "", en: "" }, default: null, validation: {},
          ai_elicit: false, export: true, audience: "basic",
        },
      ],
    }),
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

    await waitFor(() => expect(screen.getByTestId("artifact-field-title")).toHaveValue("Element A"));

    await user.clear(screen.getByTestId("artifact-field-title"));
    await user.type(screen.getByTestId("artifact-field-title"), "Unsaved edit");
    expect(screen.getByTestId("artifact-field-title")).toHaveValue("Unsaved edit");

    await user.click(screen.getByTestId(`arch-tree-node-${ELEMENT_B.id}`));

    const dialog = await screen.findByTestId("arch-unsaved-changes-dialog");
    expect(dialog).toBeInTheDocument();

    await user.click(screen.getByTestId("arch-unsaved-changes-dialog-cancel"));
    expect(screen.queryByTestId("arch-unsaved-changes-dialog")).not.toBeInTheDocument();
    expect(screen.getByTestId("artifact-field-title")).toHaveValue("Unsaved edit");
  });

  it("navigates and discards the unsaved edit once the user confirms", async () => {
    const user = userEvent.setup();
    renderEditor(ELEMENT_A.id);

    await waitFor(() => expect(screen.getByTestId("artifact-field-title")).toHaveValue("Element A"));

    await user.clear(screen.getByTestId("artifact-field-title"));
    await user.type(screen.getByTestId("artifact-field-title"), "Unsaved edit");

    await user.click(screen.getByTestId(`arch-tree-node-${ELEMENT_B.id}`));
    await screen.findByTestId("arch-unsaved-changes-dialog");

    await user.click(screen.getByTestId("arch-unsaved-changes-dialog-confirm"));

    await waitFor(() => expect(screen.getByTestId("artifact-field-title")).toHaveValue("Element B"));
    expect(screen.queryByTestId("arch-unsaved-changes-dialog")).not.toBeInTheDocument();
  });

  it("navigates immediately, without any dialog, when the form has no unsaved edits", async () => {
    const user = userEvent.setup();
    renderEditor(ELEMENT_A.id);

    await waitFor(() => expect(screen.getByTestId("artifact-field-title")).toHaveValue("Element A"));

    await user.click(screen.getByTestId(`arch-tree-node-${ELEMENT_B.id}`));

    await waitFor(() => expect(screen.getByTestId("artifact-field-title")).toHaveValue("Element B"));
    expect(screen.queryByTestId("arch-unsaved-changes-dialog")).not.toBeInTheDocument();
  });

  /**
   * Regression test for a stale-dirty-flag bug found in code review: the
   * `onDirtyChange` reporting effect had no cleanup, so unmounting
   * `ArchitectureForm` while `isDirty` was still `true` (e.g. via Delete,
   * which navigates away and unmounts the form without ever reporting
   * `isDirty(false)`) left the parent's `isFormDirty` state stuck at `true`.
   * The very next tree click then wrongly showed the unsaved-changes dialog
   * even though no form was open anymore.
   */
  it("does not show the unsaved-changes dialog for a tree click after Delete discarded the dirty form", async () => {
    const user = userEvent.setup();
    renderEditor(ELEMENT_A.id);

    await waitFor(() => expect(screen.getByTestId("artifact-field-title")).toHaveValue("Element A"));

    await user.clear(screen.getByTestId("artifact-field-title"));
    await user.type(screen.getByTestId("artifact-field-title"), "Unsaved edit");
    expect(screen.getByTestId("artifact-field-title")).toHaveValue("Unsaved edit");

    // Delete navigates to `/architecture` (no id), unmounting the dirty
    // ArchitectureForm without ever going through the confirm dialog.
    await user.click(screen.getByTestId("artifact-form-delete"));
    await user.click(screen.getByTestId("artifact-form-delete-confirm"));
    await waitFor(() => expect(screen.queryByTestId("artifact-field-title")).not.toBeInTheDocument());

    // A stale `isFormDirty=true` would now wrongly gate this click behind
    // the unsaved-changes dialog, even though no form is open anymore.
    await user.click(screen.getByTestId(`arch-tree-node-${ELEMENT_B.id}`));

    await waitFor(() => expect(screen.getByTestId("artifact-field-title")).toHaveValue("Element B"));
    expect(screen.queryByTestId("arch-unsaved-changes-dialog")).not.toBeInTheDocument();
  });
});
