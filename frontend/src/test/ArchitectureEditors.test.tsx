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
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";

// ---------------------------------------------------------------------------
// Mock API modules
// ---------------------------------------------------------------------------

vi.mock("../api/client", () => ({
  getList: vi.fn().mockResolvedValue({ results: [], count: 0 }),
  extractErrorMessage: vi.fn().mockReturnValue("Error"),
  setAuthToken: vi.fn(),
  setUnauthorizedHandler: vi.fn(),
  apiClient: {
    get: vi.fn().mockResolvedValue({}),
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
          <WorkspaceProvider>
            <Routes>
              <Route path="/architecture" element={<ArchitectureEditors />} />
              <Route path="/architecture/:id" element={<ArchitectureEditors />} />
            </Routes>
          </WorkspaceProvider>
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
      // Element-type dropdown
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
    const typeSelect = screen.getByTestId("arch-element-type-select") as HTMLSelectElement;
    expect(typeSelect.value).toBe("component");
  });

  it("can change element type dropdown (REQ-L3-RF004-001 — Type-Auswahl)", async () => {
    const user = userEvent.setup();
    renderEditor(MOCK_ELEMENT.id);

    await waitFor(() => {
      expect(screen.getByTestId("arch-element-type-select")).toBeInTheDocument();
    });

    const typeSelect = screen.getByTestId("arch-element-type-select");
    await user.selectOptions(typeSelect, "subsystem");
    expect((typeSelect as HTMLSelectElement).value).toBe("subsystem");
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
});
