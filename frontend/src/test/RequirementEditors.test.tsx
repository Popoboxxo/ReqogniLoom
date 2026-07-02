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
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";

// ---------------------------------------------------------------------------
// Mock API modules
// ---------------------------------------------------------------------------

vi.mock("../api/requirements", () => ({
  requirementsApi: {
    list: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
    get: vi.fn(),
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

// Must import AFTER vi.mock
import RequirementEditors from "../components/RequirementEditors/RequirementEditors";
import { requirementsApi } from "../api/requirements";
import { tracelinksApi } from "../api/tracelinks";
import { workspacesApi } from "../api/workspaces";
import { testcasesApi } from "../api/testcases";
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

  return render(
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
      count: 1,
      next: null,
      previous: null,
      results: [MOCK_REQUIREMENT],
    });

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
      const divider = screen.getByTestId("requirement-editor-divider");
      expect(divider).toBeInTheDocument();
      expect(divider).toHaveStyle("cursor: col-resize");
      expect(divider).toHaveStyle("width: 4px");
    });
  });
});
