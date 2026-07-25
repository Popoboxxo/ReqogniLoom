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
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";

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
    status: "Draft",
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

function renderEditor(): ReturnType<typeof render> {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[`/adrs/${ADR.id}`]}>
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
