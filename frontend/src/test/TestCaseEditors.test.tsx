/**
 * ARCH-L1-001 ReactFrontend — TestCaseEditors Task 2.4 concept remodel test.
 *
 * Mirrors AdrEditors.test.tsx (Task 2.1), RiskEditors.test.tsx (Task 2.2) and
 * IssueEditors.test.tsx (Task 2.3): PageHeader / ArtifactRow / Dialog /
 * EmptyState conventions. Unlike Risks/Issues, TestCases carry no
 * brief-mandated trace-link or version investigation — TestCaseEditors does
 * not render a TraceLinkPanel, so there is no equivalent relocation test
 * here.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import "../i18n/index";

// ---------------------------------------------------------------------------
// Mock API modules (must precede component import)
// ---------------------------------------------------------------------------

vi.mock("../api/client", () => ({
  getList: vi.fn().mockResolvedValue({ results: [], count: 0 }),
  getAllPages: vi.fn().mockResolvedValue([]),
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
    patch: vi.fn().mockResolvedValue({}),
    delete: vi.fn().mockResolvedValue({}),
  },
}));

// vi.hoisted so this is available inside the hoisted vi.mock factories below.
const { TEST_CASE } = vi.hoisted(() => ({
  TEST_CASE: {
    id: "tc-001",
    workspace_id: "ws-001",
    title: "Login succeeds with valid credentials",
    description: "Verifies the happy-path login flow.",
    status: "draft" as const,
    version: 1,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  },
}));

vi.mock("../api/testcases", () => ({
  testcasesApi: {
    list: vi.fn().mockResolvedValue({ results: [TEST_CASE], count: 1, next: null, previous: null }),
    listAll: vi.fn().mockResolvedValue([TEST_CASE]),
    get: vi.fn().mockResolvedValue(TEST_CASE),
    create: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
    versions: vi.fn().mockResolvedValue([]),
    diff: vi.fn().mockResolvedValue({ fields: [], unchanged: [] }),
  },
}));

vi.mock("../api/custom-fields", () => ({
  customFieldsApi: {
    getValues: vi.fn().mockResolvedValue([]),
    putValues: vi.fn().mockResolvedValue([]),
  },
}));

// Isolate from the ArtifactInspector sidebar (its own data fetching is out of
// scope for this test).
vi.mock("../components/shared/ArtifactInspector", () => ({
  RightSidebar: () => null,
}));

// Provide a fixed active workspace instead of the real fetch-driven provider.
// Referentially stable across renders (real WorkspaceContext holds this in
// useState, which React guarantees is stable) — useTestCaseData's loadList
// depends on the `activeWorkspace` object identity, and a mock that hands
// out a fresh literal per call would spin it into a render loop that never
// resolves, unlike the react-query-backed Adr/Risk/Issue data hooks.
const ACTIVE_WORKSPACE = { id: "ws-001", name: "WS" };
vi.mock("../context/WorkspaceContext", () => ({
  useWorkspace: () => ({ activeWorkspace: ACTIVE_WORKSPACE, isLoadingWorkspace: false }),
  WorkspaceProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

// Must import AFTER vi.mock
import TestCaseEditors from "../components/TestCaseEditors/TestCaseEditors";
import { testcasesApi } from "../api/testcases";
import { getWorkflowStatusLabel } from "../utils/workflowStatus";

function renderEditor(initialPath = `/testcases/${TEST_CASE.id}`): ReturnType<typeof render> {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialPath]}>
        <Routes>
          <Route path="/testcases" element={<TestCaseEditors />} />
          <Route path="/testcases/:id" element={<TestCaseEditors />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("TestCaseEditors Task 2.4 concept remodel (PageHeader / ArtifactRow / Dialog / EmptyState)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(testcasesApi.list).mockResolvedValue({ results: [TEST_CASE], count: 1, next: null, previous: null });
    vi.mocked(testcasesApi.listAll).mockResolvedValue([TEST_CASE]);
    vi.mocked(testcasesApi.get).mockResolvedValue(TEST_CASE);
  });

  it("renders exactly one <h1> with an always-visible summary (12.1)", async () => {
    renderEditor("/testcases");

    await waitFor(() => {
      expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    });
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Test Cases");
    // Summary is visible without any active search/filter.
    expect(screen.getByTestId("page-header-count")).toHaveTextContent("1 test case");
  });

  it("moves the primary create action into the PageHeader, named after the result", async () => {
    renderEditor("/testcases");
    await waitFor(() => {
      expect(screen.getByTestId("page-header")).toBeInTheDocument();
    });
    const createButton = screen.getByTestId("create-tc-btn");
    expect(screen.getByTestId("page-header")).toContainElement(createButton);
    expect(createButton).toHaveTextContent("New Test Case");
    // No inline create form in the list anymore — creation only happens
    // through the Dialog, not yet open.
    expect(screen.queryByTestId("tc-new-title-input")).not.toBeInTheDocument();
  });

  it("renders each test case as an ArtifactRow with id, status and title", async () => {
    renderEditor("/testcases");
    await waitFor(() => {
      expect(screen.getByTestId(`tc-row-${TEST_CASE.id}`)).toBeInTheDocument();
    });
    const row = screen.getByTestId(`tc-row-${TEST_CASE.id}`);
    expect(row).toHaveTextContent(TEST_CASE.title);
    // GH-453: the API value is lowercase ("draft"); the badge renders the
    // human-readable label ("Draft"). See utils/workflowStatus.
    expect(screen.getByTestId(`tc-row-${TEST_CASE.id}-status`)).toHaveTextContent(
      getWorkflowStatusLabel(TEST_CASE.status),
    );
  });

  it("shows the empty variant with a create action when there are no test cases at all", async () => {
    vi.mocked(testcasesApi.listAll).mockResolvedValue([]);
    renderEditor("/testcases");

    await waitFor(() => {
      expect(screen.getByTestId("tc-list-empty")).toBeInTheDocument();
    });
    expect(screen.getByTestId("tc-list-empty-create")).toBeInTheDocument();
    expect(screen.queryByTestId("tc-list-no-match")).not.toBeInTheDocument();
  });

  it("shows the no-match variant with only a reset-filters action when the filter matches nothing", async () => {
    renderEditor("/testcases");
    await waitFor(() => {
      expect(screen.getByTestId(`tc-row-${TEST_CASE.id}`)).toBeInTheDocument();
    });

    const user = userEvent.setup();
    await user.type(screen.getByTestId("tc-list-search-input"), "no such test case title");

    await waitFor(() => {
      expect(screen.getByTestId("tc-list-no-match")).toBeInTheDocument();
    });
    expect(screen.getByTestId("tc-list-no-match-reset-filters")).toBeInTheDocument();
    expect(screen.queryByTestId("tc-list-empty")).not.toBeInTheDocument();
  });

  it("opens the create dialog from the header action, titled after the button label, and creates via shared/Dialog", async () => {
    vi.mocked(testcasesApi.create).mockResolvedValue({ ...TEST_CASE, id: "tc-new-1" });
    renderEditor("/testcases");

    await waitFor(() => {
      expect(screen.getByTestId("create-tc-btn")).toBeInTheDocument();
    });

    const user = userEvent.setup();
    await user.click(screen.getByTestId("create-tc-btn"));

    const dialog = await screen.findByTestId("tc-create-dialog");
    expect(dialog).toHaveAttribute("role", "dialog");
    expect(dialog).toHaveAttribute("aria-modal", "true");
    // Dialog title repeats the button's label (ch. 12.8).
    expect(screen.getByRole("heading", { name: "New Test Case" })).toBeInTheDocument();

    await user.type(screen.getByTestId("tc-new-title-input"), "Login fails with invalid password");
    await user.click(screen.getByTestId("tc-new-save-btn"));

    await waitFor(() => {
      expect(testcasesApi.create).toHaveBeenCalledWith({
        workspace_id: "ws-001",
        title: "Login fails with invalid password",
      });
    });
  });

  /**
   * BUG-11 (Systemaudit 2026-08-18, §4, Mittel) — `description` is an
   * ordinary testcasesApi.create() field the backend already accepts but
   * had no editor in this dialog.
   */
  it("sends the typed description alongside the title on create (BUG-11)", async () => {
    vi.mocked(testcasesApi.create).mockResolvedValue({ ...TEST_CASE, id: "tc-new-2" });
    renderEditor("/testcases");

    await waitFor(() => {
      expect(screen.getByTestId("create-tc-btn")).toBeInTheDocument();
    });

    const user = userEvent.setup();
    await user.click(screen.getByTestId("create-tc-btn"));
    await screen.findByTestId("tc-create-dialog");

    await user.type(screen.getByTestId("tc-new-title-input"), "Login fails");
    await user.type(screen.getByTestId("tc-new-description-input"), "Steps to reproduce...");
    await user.click(screen.getByTestId("tc-new-save-btn"));

    await waitFor(() => {
      expect(testcasesApi.create).toHaveBeenCalledWith(
        expect.objectContaining({
          title: "Login fails",
          description: "Steps to reproduce...",
        })
      );
    });
  });
});
