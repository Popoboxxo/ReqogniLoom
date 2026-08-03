/**
 * ARCH-L1-001 ReactFrontend — AdrEditors TraceLink unit test.
 *
 * leaf_id: COMP-RF-003 (ADR editors)
 * req_id:  REQ-L2-TE-020 (ADR <-> ArchitectureElement TraceLink UI)
 *
 * Acceptance criterion:
 *   Render AdrEditor with a mocked TraceLink response containing one
 *   ArchitectureElement link → the TraceLinkPanel renders and shows the
 *   linked ArchitectureElement.
 *
 * REST mocked: adrsApi, tracelinksApi.listForArtifact, artifactsApi.get,
 * architectureApi.get (via resolveArtifactRef).
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
// Real i18next instance (EN resources) so the Task 2.1 assertions below can
// check actual rendered copy (title, summary, dialog title) instead of raw
// keys — the suite above only ever checked testids/markup and never needed
// this, so it is a new, additive setup step for this file.
import "../i18n/index";

// ---------------------------------------------------------------------------
// Mock API modules (must precede component import)
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
    patch: vi.fn().mockResolvedValue({}),
    delete: vi.fn().mockResolvedValue({}),
  },
}));

// vi.hoisted so these are available inside the hoisted vi.mock factories below.
const { ADR, ARCH_ARTIFACT_ID } = vi.hoisted(() => ({
  ADR: {
    id: "adr-001",
    workspace_id: "ws-001",
    title: "Adopt event sourcing",
    description: "Append-only log.",
    context: "",
    consequences: "",
    status: "Draft" as const,
    version: 1,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  },
  ARCH_ARTIFACT_ID: "arch-artifact-999",
}));

vi.mock("../api/adrs", () => ({
  adrsApi: {
    list: vi.fn().mockResolvedValue({ results: [ADR], count: 1 }),
    get: vi.fn().mockResolvedValue(ADR),
    create: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
    versions: vi.fn().mockResolvedValue([]),
    diff: vi.fn().mockResolvedValue({ fields: [], unchanged: [] }),
    listAll: vi.fn().mockResolvedValue([ADR]),
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

vi.mock("../api/artifacts", () => ({
  artifactsApi: {
    get: vi.fn(),
  },
}));

vi.mock("../api/architecture", () => ({
  architectureApi: {
    get: vi.fn(),
    listAll: vi.fn().mockResolvedValue([]),
  },
}));

vi.mock("../api/requirements", () => ({
  requirementsApi: {
    get: vi.fn(),
    listAll: vi.fn().mockResolvedValue([]),
  },
}));

vi.mock("../api/testcases", () => ({
  testcasesApi: {
    get: vi.fn(),
    list: vi.fn().mockResolvedValue({ results: [], count: 0 }),
  },
}));

// Isolate from the ArtifactInspector sidebar (its own data fetching is out of
// scope for this test).
vi.mock("../components/shared/ArtifactInspector", () => ({
  RightSidebar: () => null,
}));

// Provide a fixed active workspace instead of the real fetch-driven provider.
vi.mock("../context/WorkspaceContext", () => ({
  useWorkspace: () => ({ activeWorkspace: { id: "ws-001", name: "WS" } }),
  WorkspaceProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

// Must import AFTER vi.mock
import AdrEditors from "../components/AdrEditors/AdrEditors";
import { tracelinksApi } from "../api/tracelinks";
import { artifactsApi } from "../api/artifacts";
import { architectureApi } from "../api/architecture";
import { adrsApi } from "../api/adrs";

function renderEditor(initialPath = `/adrs/${ADR.id}`): ReturnType<typeof render> {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialPath]}>
        <Routes>
          <Route path="/adrs" element={<AdrEditors />} />
          <Route path="/adrs/:id" element={<AdrEditors />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("AdrEditors TraceLinkPanel (REQ-L2-TE-020)", () => {
  beforeEach(() => {
    vi.clearAllMocks();

    // One downstream 'decides' link: ADR -> ArchitectureElement artifact.
    vi.mocked(tracelinksApi.listForArtifact).mockResolvedValue({
      count: 1,
      next: null,
      previous: null,
      results: [
        {
          id: "link-1",
          source_id: ADR.id,
          target_id: ARCH_ARTIFACT_ID,
          link_type: "decides",
          version: 1,
          created_at: "2026-01-01T00:00:00Z",
        },
      ],
    } as any);

    // resolveArtifactRef: artifact type lookup then entity title lookup.
    vi.mocked(artifactsApi.get).mockImplementation(async (id: string) => {
      if (id === ARCH_ARTIFACT_ID) {
        return { id, artifact_type: "ArchitectureElement" } as any;
      }
      return { id, artifact_type: "Adr" } as any;
    });
    vi.mocked(architectureApi.get).mockResolvedValue({
      id: ARCH_ARTIFACT_ID,
      title: "EventStore Component",
    } as any);
  });

  it("renders the TraceLinkPanel with the linked ArchitectureElement", async () => {
    renderEditor();

    // Panel heading renders.
    await waitFor(() => {
      expect(screen.getByText("Trace Links")).toBeInTheDocument();
    });

    // The linked ArchitectureElement title is resolved and shown.
    await waitFor(() => {
      expect(screen.getByText("EventStore Component")).toBeInTheDocument();
    });

    // The 'decides' link-type label is rendered (neutral EN label: "Decision").
    expect(screen.getByText("Decision")).toBeInTheDocument();

    // The panel queried links for the ADR's own id.
    expect(tracelinksApi.listForArtifact).toHaveBeenCalledWith("ws-001", ADR.id);
  });
});

describe("AdrEditors Task 2.1 concept remodel (PageHeader / ArtifactRow / Dialog / EmptyState)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(tracelinksApi.listForArtifact).mockResolvedValue({
      count: 0,
      next: null,
      previous: null,
      results: [],
    } as any);
    vi.mocked(adrsApi.list).mockResolvedValue({ results: [ADR], count: 1, next: null, previous: null });
    vi.mocked(adrsApi.listAll).mockResolvedValue([ADR]);
    vi.mocked(adrsApi.get).mockResolvedValue(ADR);
  });

  it("renders exactly one <h1> with an always-visible summary (12.1)", async () => {
    renderEditor("/adrs");

    await waitFor(() => {
      expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    });
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("ADRs");
    // Summary is visible without any active search/filter.
    expect(screen.getByTestId("page-header-count")).toHaveTextContent("1 ADR");
  });

  it("moves the primary create action into the PageHeader, named after the result", async () => {
    renderEditor("/adrs");
    await waitFor(() => {
      expect(screen.getByTestId("page-header")).toBeInTheDocument();
    });
    // Exactly one create action exists, inside the header, labelled after the
    // result ("New ADR") rather than the gesture ("+ New").
    const createButton = screen.getByTestId("create-adr-btn");
    expect(screen.getByTestId("page-header")).toContainElement(createButton);
    expect(createButton).toHaveTextContent("New ADR");
    // No inline create form in the list anymore — creation only happens
    // through the Dialog, not yet open.
    expect(screen.queryByTestId("adr-new-title-input")).not.toBeInTheDocument();
  });

  it("renders each ADR as an ArtifactRow with id, status and title", async () => {
    renderEditor("/adrs");
    await waitFor(() => {
      expect(screen.getByTestId(`adr-row-${ADR.id}`)).toBeInTheDocument();
    });
    const row = screen.getByTestId(`adr-row-${ADR.id}`);
    expect(row).toHaveTextContent(ADR.title);
    expect(screen.getByTestId(`adr-row-${ADR.id}-status`)).toHaveTextContent(ADR.status);
  });

  it("shows the empty variant with a create action when there are no ADRs at all", async () => {
    vi.mocked(adrsApi.listAll).mockResolvedValue([]);
    renderEditor("/adrs");

    await waitFor(() => {
      expect(screen.getByTestId("adr-list-empty")).toBeInTheDocument();
    });
    expect(screen.getByTestId("adr-list-empty-create")).toBeInTheDocument();
    expect(screen.queryByTestId("adr-list-no-match")).not.toBeInTheDocument();
  });

  it("shows the no-match variant with only a reset-filters action when the filter matches nothing", async () => {
    renderEditor("/adrs");
    await waitFor(() => {
      expect(screen.getByTestId(`adr-row-${ADR.id}`)).toBeInTheDocument();
    });

    const user = userEvent.setup();
    await user.type(screen.getByTestId("adr-list-search-input"), "no such adr title");

    await waitFor(() => {
      expect(screen.getByTestId("adr-list-no-match")).toBeInTheDocument();
    });
    // The no-match variant offers only "reset filters", never a create action.
    expect(screen.getByTestId("adr-list-no-match-reset-filters")).toBeInTheDocument();
    expect(screen.queryByTestId("adr-list-empty")).not.toBeInTheDocument();
  });

  it("opens the create dialog from the header action, titled after the button label, and creates via shared/Dialog", async () => {
    vi.mocked(adrsApi.create).mockResolvedValue({ ...ADR, id: "adr-new-1" });
    renderEditor("/adrs");

    await waitFor(() => {
      expect(screen.getByTestId("create-adr-btn")).toBeInTheDocument();
    });

    const user = userEvent.setup();
    await user.click(screen.getByTestId("create-adr-btn"));

    const dialog = await screen.findByTestId("adr-create-dialog");
    expect(dialog).toHaveAttribute("role", "dialog");
    expect(dialog).toHaveAttribute("aria-modal", "true");
    // Dialog title repeats the button's label (ch. 12.8).
    expect(screen.getByRole("heading", { name: "New ADR" })).toBeInTheDocument();

    await user.type(screen.getByTestId("adr-new-title-input"), "Adopt CQRS");
    await user.click(screen.getByTestId("adr-new-save-btn"));

    await waitFor(() => {
      expect(adrsApi.create).toHaveBeenCalledWith({
        workspace_id: "ws-001",
        title: "Adopt CQRS",
      });
    });
  });
});
