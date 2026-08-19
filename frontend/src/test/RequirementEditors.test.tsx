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

vi.mock("../api/client", async (importActual) => ({
  ...(await importActual<typeof import("../api/client")>()),
  getList: vi.fn().mockResolvedValue({ results: [], count: 0 }),
  extractErrorMessage: vi.fn().mockReturnValue("Error"),
  // #340: NOT stubbed on purpose — the create/delete handlers under test must
  // be exercised against the real extraction logic, so a test that shows the
  // server's own message really proves the envelope is read correctly.
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
    // Task 3.3: <TraceSpine>'s useDerivationChain calls impact() on mount —
    // without a mock this throws synchronously and gets swallowed into the
    // hook's own error state, stealing the extractErrorMessage() mock queue
    // from unrelated save-error assertions below.
    impact: vi.fn().mockResolvedValue([]),
  },
}));

vi.mock("../api/traceability", () => ({
  traceabilityApi: {
    resolve: vi.fn().mockResolvedValue([]),
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
import { workspacesApi } from "../api/workspaces";
import { extractErrorMessage } from "../api/client";
import { AuthProvider } from "../context/AuthContext";
import { WorkspaceProvider } from "../context/WorkspaceContext";
import { getWorkflowStatusLabel } from "../utils/workflowStatus";

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

  // Issue #311: zero drafts used to render the *success* message — both
  // branches of the status ternary were literally identical, so "the AI
  // returned nothing" was indistinguishable from "derivation worked".
  it("reports an empty AI derivation as a problem, not as success (issue #311)", async () => {
    const user = userEvent.setup();
    vi.mocked(requirementsApi.aiDecomposeNextLevel).mockResolvedValue({
      drafts: [],
      parent_requirement_id: MOCK_REQUIREMENT.id,
      note: "The LLM returned an empty list.",
    });
    renderEditor(MOCK_REQUIREMENT.id);

    await waitFor(() => {
      expect(screen.getByTestId("req-ai-derive-btn")).toBeInTheDocument();
    });
    await user.click(screen.getByTestId("req-ai-derive-btn"));

    const status = await screen.findByTestId("req-ai-derive-status");
    await waitFor(() => {
      expect(status).toHaveAttribute("role", "alert");
    });
    expect(status.textContent ?? "").toMatch(/aiDeriveEmpty|proposed no|keine/i);
  });

  it("reports a non-empty AI derivation as success (issue #311)", async () => {
    const user = userEvent.setup();
    vi.mocked(requirementsApi.aiDecomposeNextLevel).mockResolvedValue({
      drafts: [
        {
          title: "Child requirement",
          description: "d",
          rationale: "r",
          suggested_arch_element_id: null,
        },
      ],
      parent_requirement_id: MOCK_REQUIREMENT.id,
    });
    renderEditor(MOCK_REQUIREMENT.id);

    await waitFor(() => {
      expect(screen.getByTestId("req-ai-derive-btn")).toBeInTheDocument();
    });
    await user.click(screen.getByTestId("req-ai-derive-btn"));

    const status = await screen.findByTestId("req-ai-derive-status");
    await waitFor(() => {
      expect(status).toHaveAttribute("role", "status");
    });
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

// ---------------------------------------------------------------------------
// Task 3.1 — ArtifactRow list rows + EmptyState empty/no-match distinction
// ---------------------------------------------------------------------------

describe("RequirementEditors Task 3.1 (ArtifactRow / EmptyState)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();

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

  it("renders each requirement as an ArtifactRow with id, status and title", async () => {
    renderEditor();

    await waitFor(() => {
      expect(screen.getByTestId(`req-row-${MOCK_REQUIREMENT.id}`)).toBeInTheDocument();
    });
    const row = screen.getByTestId(`req-row-${MOCK_REQUIREMENT.id}`);
    expect(row).toHaveTextContent(MOCK_REQUIREMENT.title);
    // GH-453: the badge renders the human-readable *label*, not the raw API
    // value — `status="approved"` shows as "Approved". The raw value stays the
    // filter/compare key (see utils/workflowStatus).
    expect(screen.getByTestId(`req-row-${MOCK_REQUIREMENT.id}-status`)).toHaveTextContent(
      getWorkflowStatusLabel(MOCK_REQUIREMENT.status)
    );
  });

  it("shows the empty variant with a create action when there are no requirements at all", async () => {
    vi.mocked(requirementsApi.list).mockResolvedValue({ results: [], count: 0 } as any);
    vi.mocked(requirementsApi.listAll).mockResolvedValue([]);
    renderEditor();

    await waitFor(() => {
      expect(screen.getByTestId("req-list-empty")).toBeInTheDocument();
    });
    expect(screen.getByTestId("req-list-empty-create")).toBeInTheDocument();
    expect(screen.queryByTestId("req-list-no-match")).not.toBeInTheDocument();
  });

  it("shows the no-match variant with only a reset-filters action when the filter matches nothing", async () => {
    renderEditor();
    await waitFor(() => {
      expect(screen.getByTestId(`req-row-${MOCK_REQUIREMENT.id}`)).toBeInTheDocument();
    });

    const user = userEvent.setup();
    await user.type(screen.getByTestId("req-list-search-input"), "no such requirement title");

    await waitFor(() => {
      expect(screen.getByTestId("req-list-no-match")).toBeInTheDocument();
    });
    expect(screen.getByTestId("req-list-no-match-reset-filters")).toBeInTheDocument();
    expect(screen.queryByTestId("req-list-empty")).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// GitHub #339 / #340 — the UI must never swallow a server rejection
//
// Both issues share one root cause: the list-level write handlers in
// RequirementEditors caught their rejection into `console.error` and had no
// UI surface at all, so a rejected create/delete was indistinguishable from a
// no-op. Every sibling artifact container (Need/Risk/TestCase/Adr/Issue)
// already rendered a `createError`; Requirements was the one that did not.
// ---------------------------------------------------------------------------

describe("RequirementEditors — server validation errors are visible (#339/#340)", () => {
  /** The exact 400 body the free-text guard produces for markup in a title. */
  const XSS_REJECTION = {
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
  };

  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();

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

  it("renders the server's rejection reason when a create is refused", async () => {
    vi.mocked(requirementsApi.create).mockRejectedValueOnce(XSS_REJECTION);
    const user = userEvent.setup();
    renderEditor();

    await waitFor(() =>
      expect(screen.getByTestId("create-req-btn")).toBeInTheDocument()
    );
    await user.click(screen.getByTestId("create-req-btn"));
    await user.type(
      screen.getByTestId("req-new-title-input"),
      "<script>alert(1)</script>"
    );
    await user.click(screen.getByTestId("req-new-save-btn"));

    const alert = await screen.findByTestId("req-create-error");
    expect(alert).toHaveAttribute("role", "alert");
    expect(alert).toHaveTextContent(
      "HTML markup is not permitted in free-text fields."
    );
  });

  it("keeps the create form (and the typed title) open after a refused create", async () => {
    vi.mocked(requirementsApi.create).mockRejectedValueOnce(XSS_REJECTION);
    const user = userEvent.setup();
    renderEditor();

    await waitFor(() =>
      expect(screen.getByTestId("create-req-btn")).toBeInTheDocument()
    );
    await user.click(screen.getByTestId("create-req-btn"));
    await user.type(screen.getByTestId("req-new-title-input"), "<b>x</b>");
    await user.click(screen.getByTestId("req-new-save-btn"));

    await screen.findByTestId("req-create-error");
    // Nothing was lost: the user can correct the title in place.
    expect(screen.getByTestId("req-new-title-input")).toHaveValue("<b>x</b>");
  });

  it("clears the create error once the user starts correcting the title", async () => {
    vi.mocked(requirementsApi.create).mockRejectedValueOnce(XSS_REJECTION);
    const user = userEvent.setup();
    renderEditor();

    await waitFor(() =>
      expect(screen.getByTestId("create-req-btn")).toBeInTheDocument()
    );
    await user.click(screen.getByTestId("create-req-btn"));
    await user.type(screen.getByTestId("req-new-title-input"), "<b>x</b>");
    await user.click(screen.getByTestId("req-new-save-btn"));
    await screen.findByTestId("req-create-error");

    await user.type(screen.getByTestId("req-new-title-input"), "y");

    await waitFor(() =>
      expect(screen.queryByTestId("req-create-error")).not.toBeInTheDocument()
    );
  });

  it("falls back to localised copy when the rejection carries no message", async () => {
    vi.mocked(requirementsApi.create).mockRejectedValueOnce({ weird: true });
    const user = userEvent.setup();
    renderEditor();

    await waitFor(() =>
      expect(screen.getByTestId("create-req-btn")).toBeInTheDocument()
    );
    await user.click(screen.getByTestId("create-req-btn"));
    await user.type(screen.getByTestId("req-new-title-input"), "Fine title");
    await user.click(screen.getByTestId("req-new-save-btn"));

    const alert = await screen.findByTestId("req-create-error");
    // Never an "[object Object]" dump — the container's own i18n key wins.
    expect(alert.textContent).not.toContain("object Object");
    expect(alert.textContent?.trim().length).toBeGreaterThan(0);
  });

  it("surfaces a refused list-level action in the page banner", async () => {
    // The PDF export is the reachable list-level action on this page (the
    // list's own delete confirmation is currently unreachable — its
    // `setConfirmDeleteId` has no caller, tracked separately). It used to
    // fail with a console.error and no download, i.e. invisibly.
    vi.mocked(workspacesApi.downloadPdfReport).mockRejectedValueOnce({
      error: {
        code: "PERMISSION_DENIED",
        message: "You do not have permission to perform this action.",
        details: [],
      },
    });
    const user = userEvent.setup();
    renderEditor();

    await waitFor(() =>
      expect(screen.getByTestId("export-pdf-btn")).toBeEnabled()
    );
    await user.click(screen.getByTestId("export-pdf-btn"));

    const alert = await screen.findByTestId("req-action-error");
    expect(alert).toHaveAttribute("role", "alert");
    expect(alert).toHaveTextContent(
      "You do not have permission to perform this action."
    );
  });
});

/**
 * BUG-11 (Systemaudit 2026-08-18, §4, Mittel) — the create-requirement form
 * only ever had a title input; `description` and `category` are ordinary
 * `requirementsApi.create()` fields (backend already accepts them) but had
 * no editor at all, so every requirement started life with an empty
 * description and no category, forcing an immediate follow-up edit.
 */
describe("RequirementEditors — create form has description/category fields (BUG-11)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();
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

  it("sends the typed description and category alongside the title on create", async () => {
    vi.mocked(requirementsApi.create).mockResolvedValueOnce({
      ...MOCK_REQUIREMENT,
      id: "req-new",
    } as any);
    const user = userEvent.setup();
    renderEditor();

    await waitFor(() =>
      expect(screen.getByTestId("create-req-btn")).toBeInTheDocument()
    );
    await user.click(screen.getByTestId("create-req-btn"));

    await user.type(screen.getByTestId("req-new-title-input"), "New Req");
    await user.type(
      screen.getByTestId("req-new-description-input"),
      "Some description"
    );
    await user.selectOptions(
      screen.getByTestId("req-new-category-select"),
      "functional"
    );
    await user.click(screen.getByTestId("req-new-save-btn"));

    await waitFor(() =>
      expect(requirementsApi.create).toHaveBeenCalledWith(
        expect.objectContaining({
          title: "New Req",
          description: "Some description",
          category: "functional",
        })
      )
    );
  });
});
