/**
 * ARCH-L1-001 ReactFrontend — RequirementEditors unit test.
 *
 * leaf_id: COMP-RF-003 (RequirementEditors)
 * req_id:  REQ-L2-RF-003 (Requirements-Editor with Inline-Editing and Markdown),
 *          REQ-L3-RF003-001 (Inline-Editing — Title, Description, Category),
 *          REQ-L3-RF003-002 (Workflow-State-Anzeige + Transition),
 *          REQ-L3-RF003-003 (TraceabilityPanel),
 *          REQ-L1-040 (Resizable split-pane divider, analog ArchitectureEditors)
 *
 * Acceptance criterion (REQ-L2-RF-003 AC):
 *   Unit-Test: Render RequirementEditor with Mock-Requirement →
 *   alle Felder sichtbar und editierbar.
 *
 * REST mocked: requirementsApi.list, requirementsApi.update, tracelinksApi.listForArtifact
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

vi.mock("../api/requirements", () => ({
  requirementsApi: {
    list: vi.fn(),
    listAll: vi.fn().mockResolvedValue([]),
    create: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
    get: vi.fn(),
    versions: vi.fn().mockResolvedValue([]),
    diff: vi.fn().mockResolvedValue({ fields: [], unchanged: [] }),
    // REQ-143: workflow transitions endpoint mocks (RequirementForm loads these).
    getTransitions: vi.fn().mockResolvedValue({
      current_state: "approved",
      states: ["draft", "approved", "deprecated"],
      allowed_transitions: [],
    }),
    transition: vi.fn().mockResolvedValue({}),
    // REQ-008: AI decompose endpoint mock
    aiDecomposeNextLevel: vi.fn().mockResolvedValue({
      drafts: [],
      parent_requirement_id: "req-001",
    }),
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

vi.mock("../api/workspaces", () => ({
  workspacesApi: {
    list: vi.fn(),
    downloadPdfReport: vi.fn(),
  },
}));

vi.mock("../api/testcases", () => ({
  testcasesApi: {
    list: vi.fn(),
  },
}));

// Stub the shared ArtifactInspector so the RightSidebar shell is countable.
// Preserves the rest of the barrel (VersionPanel, types, ...) via importActual
// and only replaces RightSidebar with a marker. This lets the test assert that
// the Inspector is rendered exactly ONCE at container level (REQ-TBD:
// remove duplicate ArtifactInspector rendering in editor components).
vi.mock("../components/shared/ArtifactInspector", async (importActual) => {
  const actual =
    await importActual<typeof import("../components/shared/ArtifactInspector")>();
  return {
    ...actual,
    RightSidebar: () => <div data-testid="artifact-inspector" />,
  };
});

// Must import AFTER vi.mock
import RequirementEditors from "../components/RequirementEditors/RequirementEditors";
import { requirementsApi } from "../api/requirements";
import { tracelinksApi } from "../api/tracelinks";
import { testcasesApi } from "../api/testcases";
import { extractErrorMessage } from "../api/client";
import { AuthProvider } from "../context/AuthContext";
import { WorkspaceProvider } from "../context/WorkspaceContext";

// ---------------------------------------------------------------------------
// Mock data
// ---------------------------------------------------------------------------

const MOCK_REQUIREMENT = {
  id: "req-001",
  workspace_id: "ws-001",
  title: "User Authentication",
  description: "## Auth\nSystem shall authenticate users.",
  category: "functional",
  status: "approved",
  change_reason: "",
  version: 1,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

// ---------------------------------------------------------------------------
// Render helper
// ---------------------------------------------------------------------------

function renderEditor(requirementId?: string): ReturnType<typeof render> {
  sessionStorage.setItem("reqflow_token", "test-token");

  const path = requirementId ? `/requirements/${requirementId}` : "/requirements";
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[path]}>
        <AuthProvider>
          <WorkspaceProvider>
            <Routes>
              <Route path="/requirements" element={<RequirementEditors />} />
              <Route path="/requirements/:id" element={<RequirementEditors />} />
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

describe("RequirementEditors (COMP-RF-003 / REQ-L2-RF-003)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();

    // Default mock implementations
    vi.mocked(requirementsApi.list).mockResolvedValue({
      results: [MOCK_REQUIREMENT],
      count: 1,
    } as any);
    vi.mocked(requirementsApi.listAll).mockResolvedValue([MOCK_REQUIREMENT] as any);

    vi.mocked(requirementsApi.get).mockResolvedValue(MOCK_REQUIREMENT);

    vi.mocked(tracelinksApi.listForArtifact).mockResolvedValue({
      count: 0,
      next: null,
      previous: null,
      results: [],
    });

    vi.mocked(testcasesApi.list).mockResolvedValue({
      count: 0,
      next: null,
      previous: null,
      results: [],
    });
  });

  // -------------------------------------------------------------------------
  // REQ-L1-040 — Resizable split-pane divider tests
  // -------------------------------------------------------------------------

  it("renders split-pane divider for resizing (REQ-L1-040 — enable split-pane resizing)", async () => {
    renderEditor(MOCK_REQUIREMENT.id);

    await waitFor(() => {
      const divider = screen.getByTestId("splitview-divider");
      expect(divider).toBeInTheDocument();
      expect(divider).toHaveStyle("cursor: col-resize");
    });
  });

  // -------------------------------------------------------------------------
  // REQ-TBD — ArtifactInspector must render exactly ONCE
  //
  // Regression guard: RequirementEditors (container) AND RequirementForm
  // (detail form) both used to render the shared RightSidebar, producing two
  // Inspector bars side by side in the requirements mask. The Inspector must
  // live at the container level only.
  // -------------------------------------------------------------------------

  // -------------------------------------------------------------------------
  // REQ-008 — AI-derive button in Anforderungen view
  // -------------------------------------------------------------------------

  it("renders AI-derive button (✨ Ableiten) in RequirementEditors (REQ-008)", async () => {
    renderEditor(MOCK_REQUIREMENT.id);

    await waitFor(() => {
      expect(screen.getByTestId("req-title")).toBeInTheDocument();
    });

    // AI-derive button must be present in the ReqTraceLinkPanel header
    expect(screen.getByTestId("req-ai-derive-btn")).toBeInTheDocument();
  });

  it("renders the ArtifactInspector exactly once — no duplicate RightSidebar (REQ-TBD)", async () => {
    renderEditor(MOCK_REQUIREMENT.id);

    // Wait until the detail form has loaded the requirement (title field).
    await waitFor(() => {
      expect(screen.getByTestId("req-title")).toBeInTheDocument();
    });

    // Exactly one Inspector instance — not zero (missing), not two (duplicate).
    expect(screen.getAllByTestId("artifact-inspector")).toHaveLength(1);
  });

  // -------------------------------------------------------------------------
  // REQ-009 — Validation error messages on save failure
  // -------------------------------------------------------------------------

  it("shows field-specific error message on save failure instead of generic fallback (REQ-009)", async () => {
    const fieldError = "Title: This field may not be blank.";
    // Configure extractErrorMessage mock to return the specific field error.
    vi.mocked(extractErrorMessage).mockReturnValueOnce(fieldError);
    vi.mocked(requirementsApi.update).mockRejectedValueOnce({
      error: {
        code: "VALIDATION_ERROR",
        message: "Validation failed.",
        details: [{ field: "title", errors: ["This field may not be blank."] }],
      },
    });

    renderEditor(MOCK_REQUIREMENT.id);

    await waitFor(() => {
      expect(screen.getByTestId("save-btn")).toBeInTheDocument();
    });

    await userEvent.click(screen.getByTestId("save-btn"));

    await waitFor(() => {
      const alert = screen.getByRole("alert");
      expect(alert).toBeInTheDocument();
      expect(alert).toHaveTextContent(fieldError);
    });
  });
});
