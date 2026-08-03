/**
 * ARCH-L1-001 ReactFrontend — IssueEditors Task 2.3 concept remodel test.
 *
 * Mirrors AdrEditors.test.tsx (Task 2.1) and RiskEditors.test.tsx (Task 2.2):
 * PageHeader / ArtifactRow / Dialog / EmptyState conventions, plus the
 * Task 2.3-specific relocation of the "Neue Verknüpfung" ("new link") button
 * out of IssueEditors and into TraceLinkPanel's own header.
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
const { ISSUE } = vi.hoisted(() => ({
  ISSUE: {
    id: "issue-001",
    workspace_id: "ws-001",
    title: "Login fails on retry",
    description: "Retrying login after a token refresh throws a 500.",
    severity: "high" as const,
    category: "defect" as const,
    status: "Open" as const,
    tags: [],
    version: 1,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  },
}));

vi.mock("../api/issues", () => ({
  issuesApi: {
    list: vi.fn().mockResolvedValue({ results: [ISSUE], count: 1, next: null, previous: null }),
    listAll: vi.fn().mockResolvedValue([ISSUE]),
    get: vi.fn().mockResolvedValue(ISSUE),
    create: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
    versions: vi.fn().mockResolvedValue([]),
    diff: vi.fn().mockResolvedValue({ fields: [], unchanged: [] }),
  },
}));

vi.mock("../api/tracelinks", () => ({
  tracelinksApi: {
    list: vi.fn(),
    listForArtifact: vi.fn().mockResolvedValue({ count: 0, next: null, previous: null, results: [] }),
    create: vi.fn(),
    delete: vi.fn(),
  },
}));

vi.mock("../api/artifacts", () => ({
  artifactsApi: {
    get: vi.fn(),
  },
}));

// Isolate from the ArtifactInspector sidebar (its own data fetching is out of
// scope for this test).
vi.mock("../components/shared/ArtifactInspector", () => ({
  RightSidebar: () => null,
}));

// Provide a fixed active workspace instead of the real fetch-driven provider.
vi.mock("../context/WorkspaceContext", () => ({
  useWorkspace: () => ({ activeWorkspace: { id: "ws-001", name: "WS" }, isLoadingWorkspace: false }),
  WorkspaceProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

// Must import AFTER vi.mock
import IssueEditors from "../components/IssueEditors/IssueEditors";
import { tracelinksApi } from "../api/tracelinks";
import { issuesApi } from "../api/issues";

function renderEditor(initialPath = `/issues/${ISSUE.id}`): ReturnType<typeof render> {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialPath]}>
        <Routes>
          <Route path="/issues" element={<IssueEditors />} />
          <Route path="/issues/:id" element={<IssueEditors />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("IssueEditors Task 2.3 concept remodel (PageHeader / ArtifactRow / Dialog / EmptyState)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(tracelinksApi.listForArtifact).mockResolvedValue({
      count: 0,
      next: null,
      previous: null,
      results: [],
    } as any);
    vi.mocked(issuesApi.list).mockResolvedValue({ results: [ISSUE], count: 1, next: null, previous: null });
    vi.mocked(issuesApi.listAll).mockResolvedValue([ISSUE]);
    vi.mocked(issuesApi.get).mockResolvedValue(ISSUE);
  });

  it("renders exactly one <h1> with an always-visible summary (12.1)", async () => {
    renderEditor("/issues");

    await waitFor(() => {
      expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    });
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Issues");
    // Summary is visible without any active search/filter.
    expect(screen.getByTestId("page-header-count")).toHaveTextContent("1 issue");
  });

  it("moves the primary create action into the PageHeader, named after the result", async () => {
    renderEditor("/issues");
    await waitFor(() => {
      expect(screen.getByTestId("page-header")).toBeInTheDocument();
    });
    const createButton = screen.getByTestId("create-issue-btn");
    expect(screen.getByTestId("page-header")).toContainElement(createButton);
    expect(createButton).toHaveTextContent("New Issue");
    // No inline create form in the list anymore — creation only happens
    // through the Dialog, not yet open.
    expect(screen.queryByTestId("issue-new-title-input")).not.toBeInTheDocument();
  });

  it("renders each issue as an ArtifactRow with id, status and title", async () => {
    renderEditor("/issues");
    await waitFor(() => {
      expect(screen.getByTestId(`issue-row-${ISSUE.id}`)).toBeInTheDocument();
    });
    const row = screen.getByTestId(`issue-row-${ISSUE.id}`);
    expect(row).toHaveTextContent(ISSUE.title);
    expect(screen.getByTestId(`issue-row-${ISSUE.id}-status`)).toHaveTextContent(ISSUE.status);
  });

  it("shows the empty variant with a create action when there are no issues at all", async () => {
    vi.mocked(issuesApi.listAll).mockResolvedValue([]);
    renderEditor("/issues");

    await waitFor(() => {
      expect(screen.getByTestId("issue-list-empty")).toBeInTheDocument();
    });
    expect(screen.getByTestId("issue-list-empty-create")).toBeInTheDocument();
    expect(screen.queryByTestId("issue-list-no-match")).not.toBeInTheDocument();
  });

  it("shows the no-match variant with only a reset-filters action when the filter matches nothing", async () => {
    renderEditor("/issues");
    await waitFor(() => {
      expect(screen.getByTestId(`issue-row-${ISSUE.id}`)).toBeInTheDocument();
    });

    const user = userEvent.setup();
    await user.type(screen.getByTestId("issue-list-search-input"), "no such issue title");

    await waitFor(() => {
      expect(screen.getByTestId("issue-list-no-match")).toBeInTheDocument();
    });
    expect(screen.getByTestId("issue-list-no-match-reset-filters")).toBeInTheDocument();
    expect(screen.queryByTestId("issue-list-empty")).not.toBeInTheDocument();
  });

  it("opens the create dialog from the header action, titled after the button label, and creates via shared/Dialog", async () => {
    vi.mocked(issuesApi.create).mockResolvedValue({ ...ISSUE, id: "issue-new-1" });
    renderEditor("/issues");

    await waitFor(() => {
      expect(screen.getByTestId("create-issue-btn")).toBeInTheDocument();
    });

    const user = userEvent.setup();
    await user.click(screen.getByTestId("create-issue-btn"));

    const dialog = await screen.findByTestId("issue-create-dialog");
    expect(dialog).toHaveAttribute("role", "dialog");
    expect(dialog).toHaveAttribute("aria-modal", "true");
    // Dialog title repeats the button's label (ch. 12.8).
    expect(screen.getByRole("heading", { name: "New Issue" })).toBeInTheDocument();

    await user.type(screen.getByTestId("issue-new-title-input"), "Session cookie not cleared on logout");
    await user.click(screen.getByTestId("issue-new-save-btn"));

    await waitFor(() => {
      expect(issuesApi.create).toHaveBeenCalledWith({
        workspace_id: "ws-001",
        title: "Session cookie not cleared on logout",
      });
    });
  });

  it("relocates the trace-link creation action into TraceLinkPanel's own header, not a freestanding button under the form (Task 2.3)", async () => {
    renderEditor();

    await waitFor(() => {
      expect(screen.getByText("Trace Links")).toBeInTheDocument();
    });

    // The old freestanding "Neue Verknüpfung" button no longer exists.
    expect(screen.queryByTestId("issue-create-link-button")).not.toBeInTheDocument();
    // TraceLinkPanel owns the new-link action in its own header instead.
    expect(screen.getByTestId("trace-link-panel-open-dialog")).toBeInTheDocument();
  });
});
