/**
 * ARCH-L1-001 ReactFrontend — RiskEditors Task 2.2 concept remodel test.
 *
 * Mirrors AdrEditors.test.tsx (Task 2.1 reference): PageHeader / ArtifactRow
 * / Dialog / EmptyState conventions, plus the Task 2.2-specific relocation of
 * the "Neue Verknüpfung" ("new link") button out of RiskEditors and into
 * TraceLinkPanel's own header.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import "../i18n/index";
import { i18n } from "../i18n/index";

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
const { RISK } = vi.hoisted(() => ({
  RISK: {
    id: "risk-001",
    workspace_id: "ws-001",
    title: "Third-party outage",
    description: "Vendor API downtime.",
    probability: "medium" as const,
    impact: "high" as const,
    risk_score: 6,
    severity: "high" as const,
    category: "technical" as const,
    owner: "",
    mitigation_strategy: "",
    status: "Identified" as const,
    version: 1,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  },
}));

vi.mock("../api/risks", () => ({
  risksApi: {
    list: vi.fn().mockResolvedValue({ results: [RISK], count: 1, next: null, previous: null }),
    listAll: vi.fn().mockResolvedValue([RISK]),
    get: vi.fn().mockResolvedValue(RISK),
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
    // Task 3.3: <TraceSpine>'s useDerivationChain calls impact() on mount.
    impact: vi.fn().mockResolvedValue([]),
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
import RiskEditors from "../components/RiskEditors/RiskEditors";
import { tracelinksApi } from "../api/tracelinks";
import { risksApi } from "../api/risks";

function renderEditor(initialPath = `/risks/${RISK.id}`): ReturnType<typeof render> {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialPath]}>
        <Routes>
          <Route path="/risks" element={<RiskEditors />} />
          <Route path="/risks/:id" element={<RiskEditors />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("RiskEditors Task 2.2 concept remodel (PageHeader / ArtifactRow / Dialog / EmptyState)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(tracelinksApi.listForArtifact).mockResolvedValue({
      count: 0,
      next: null,
      previous: null,
      results: [],
    } as any);
    vi.mocked(risksApi.list).mockResolvedValue({ results: [RISK], count: 1, next: null, previous: null });
    vi.mocked(risksApi.listAll).mockResolvedValue([RISK]);
    vi.mocked(risksApi.get).mockResolvedValue(RISK);
  });

  it("renders exactly one <h1> with an always-visible summary (12.1)", async () => {
    renderEditor("/risks");

    await waitFor(() => {
      expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    });
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Risks");
    // Summary is visible without any active search/filter.
    expect(screen.getByTestId("page-header-count")).toHaveTextContent("1 risk");
  });

  it("moves the primary create action into the PageHeader, named after the result", async () => {
    renderEditor("/risks");
    await waitFor(() => {
      expect(screen.getByTestId("page-header")).toBeInTheDocument();
    });
    const createButton = screen.getByTestId("create-risk-btn");
    expect(screen.getByTestId("page-header")).toContainElement(createButton);
    expect(createButton).toHaveTextContent("New Risk");
    // No inline create form in the list anymore — creation only happens
    // through the Dialog, not yet open.
    expect(screen.queryByTestId("risk-new-title-input")).not.toBeInTheDocument();
  });

  it("renders each risk as an ArtifactRow with id, status and title", async () => {
    renderEditor("/risks");
    await waitFor(() => {
      expect(screen.getByTestId(`risk-row-${RISK.id}`)).toBeInTheDocument();
    });
    const row = screen.getByTestId(`risk-row-${RISK.id}`);
    expect(row).toHaveTextContent(RISK.title);
    expect(screen.getByTestId(`risk-row-${RISK.id}-status`)).toHaveTextContent(RISK.status);
  });

  it("shows the empty variant with a create action when there are no risks at all", async () => {
    vi.mocked(risksApi.listAll).mockResolvedValue([]);
    renderEditor("/risks");

    await waitFor(() => {
      expect(screen.getByTestId("risk-list-empty")).toBeInTheDocument();
    });
    expect(screen.getByTestId("risk-list-empty-create")).toBeInTheDocument();
    expect(screen.queryByTestId("risk-list-no-match")).not.toBeInTheDocument();
  });

  it("shows the no-match variant with only a reset-filters action when the filter matches nothing", async () => {
    renderEditor("/risks");
    await waitFor(() => {
      expect(screen.getByTestId(`risk-row-${RISK.id}`)).toBeInTheDocument();
    });

    const user = userEvent.setup();
    await user.type(screen.getByTestId("risk-list-search-input"), "no such risk title");

    await waitFor(() => {
      expect(screen.getByTestId("risk-list-no-match")).toBeInTheDocument();
    });
    expect(screen.getByTestId("risk-list-no-match-reset-filters")).toBeInTheDocument();
    expect(screen.queryByTestId("risk-list-empty")).not.toBeInTheDocument();
  });

  it("opens the create dialog from the header action, titled after the button label, and creates via shared/Dialog", async () => {
    vi.mocked(risksApi.create).mockResolvedValue({ ...RISK, id: "risk-new-1" });
    renderEditor("/risks");

    await waitFor(() => {
      expect(screen.getByTestId("create-risk-btn")).toBeInTheDocument();
    });

    const user = userEvent.setup();
    await user.click(screen.getByTestId("create-risk-btn"));

    const dialog = await screen.findByTestId("risk-create-dialog");
    expect(dialog).toHaveAttribute("role", "dialog");
    expect(dialog).toHaveAttribute("aria-modal", "true");
    // Dialog title repeats the button's label (ch. 12.8).
    expect(screen.getByRole("heading", { name: "New Risk" })).toBeInTheDocument();

    await user.type(screen.getByTestId("risk-new-title-input"), "Key supplier lock-in");
    await user.click(screen.getByTestId("risk-new-save-btn"));

    await waitFor(() => {
      expect(risksApi.create).toHaveBeenCalledWith({
        workspace_id: "ws-001",
        title: "Key supplier lock-in",
      });
    });
  });

  /**
   * BUG-11 (Systemaudit 2026-08-18, §4, Mittel) — description/category are
   * ordinary risksApi.create() fields the backend already accepts but had
   * no editor in this dialog.
   */
  it("sends the typed description and category alongside the title on create (BUG-11)", async () => {
    vi.mocked(risksApi.create).mockResolvedValue({ ...RISK, id: "risk-new-2" });
    renderEditor("/risks");

    await waitFor(() => {
      expect(screen.getByTestId("create-risk-btn")).toBeInTheDocument();
    });

    const user = userEvent.setup();
    await user.click(screen.getByTestId("create-risk-btn"));
    await screen.findByTestId("risk-create-dialog");

    await user.type(screen.getByTestId("risk-new-title-input"), "Key supplier lock-in");
    await user.type(screen.getByTestId("risk-new-description-input"), "Single-source dependency");
    await user.selectOptions(screen.getByTestId("risk-new-category-select"), "operational");
    await user.click(screen.getByTestId("risk-new-save-btn"));

    await waitFor(() => {
      expect(risksApi.create).toHaveBeenCalledWith(
        expect.objectContaining({
          title: "Key supplier lock-in",
          description: "Single-source dependency",
          category: "operational",
        })
      );
    });
  });

  it("relocates the trace-link creation action into TraceLinkPanel's own header, not a freestanding button under the form (Task 2.2)", async () => {
    renderEditor();

    await waitFor(() => {
      expect(screen.getByText("Trace Links")).toBeInTheDocument();
    });

    // The old freestanding "Neue Verknüpfung" button no longer exists.
    expect(screen.queryByTestId("risk-create-link-button")).not.toBeInTheDocument();
    // TraceLinkPanel owns the new-link action in its own header instead.
    expect(screen.getByTestId("trace-link-panel-open-dialog")).toBeInTheDocument();
  });

  it("uses the unified + New Risk trigger label instead of bare Erstellen", async () => {
    const previousLanguage = i18n.language;
    void i18n.changeLanguage("de");

    renderEditor();

    await waitFor(() => {
      expect(screen.getByTestId("create-risk-btn")).toBeInTheDocument();
    });

    expect(screen.getByTestId("create-risk-btn")).toHaveTextContent("+ Neues Risiko");
    expect(screen.queryByText("Erstellen")).not.toBeInTheDocument();

    void i18n.changeLanguage(previousLanguage);
  });
});
