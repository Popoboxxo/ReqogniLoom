/**
 * Smoke tests for DiagramView container (REQ-050 decomposition, REQ-053 coverage).
 *
 * req_id: REQ-053, REQ-L2-DS-001, REQ-050
 *
 * Verifies:
 *   - DiagramView renders without crashing when diagram list is empty
 *   - DiagramView shows loading indicator while data is in-flight
 *   - DiagramView shows diagram list after data resolves
 *   - "New" create button is present and toggles the create form
 *   - Empty state message appears when no diagrams exist
 *
 * Uses MemoryRouter (useParams + useNavigate) and QueryClientProvider
 * (useDiagramList — TanStack Query) as test infrastructure.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import React from "react";

// ---------------------------------------------------------------------------
// Module mocks (must precede component import)
// ---------------------------------------------------------------------------

vi.mock("../../api/diagrams");
vi.mock("../../context/WorkspaceContext");
vi.mock("react-i18next", () => {
  // `t(key, fallback)` (string) and `t(key, { count, ... })` (interpolation
  // options, e.g. PageHeader's summary) must both resolve to a renderable
  // string — passing the raw options object through as a React child would
  // crash the render.
  const t = (key: string, fallbackOrOptions?: string | Record<string, unknown>): string =>
    typeof fallbackOrOptions === "string" ? fallbackOrOptions : key;
  return { useTranslation: () => ({ t }) };
});
// Stub the whole detail presenter: this file is about the container's list /
// header / create-form wiring, and the detail pane has its own test file
// (DiagramDetailView.test.tsx). Since the E2-D4 preview change it no longer
// mounts the Fabric canvas editor, so the stub is scoping, not a jsdom
// workaround.
vi.mock("./DiagramDetailView", () => ({
  DiagramDetailView: ({ diagramId }: { diagramId: string }) =>
    React.createElement("div", { "data-testid": "diagram-detail-stub" }, diagramId),
}));
vi.mock("./DiagramCreateForm", () => ({
  DiagramCreateForm: ({ onCreated }: { onCreated: (id: string) => void }) =>
    React.createElement(
      "form",
      { "data-testid": "create-diagram-form", onSubmit: (e: React.FormEvent) => { e.preventDefault(); onCreated("new-diagram-id"); } },
      React.createElement("input", { "data-testid": "diagram-name-input", name: "name", placeholder: "Diagram name" }),
      React.createElement("button", { type: "submit" }, "Create"),
    ),
}));

import * as diagramsModule from "../../api/diagrams";
import * as workspaceContext from "../../context/WorkspaceContext";

import DiagramView from "./DiagramView";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const MOCK_WORKSPACE = { id: "ws-diag-001", name: "System Design WS", preset: "standard" };

const MOCK_DIAGRAMS = [
  {
    id: "diag-001",
    workspace_id: "ws-diag-001",
    name: "System Context Diagram (C4 Level 1)",
    diagram_type: "context",
    payload_format: "mermaid",
    created_at: "2026-02-01T10:00:00Z",
    updated_at: "2026-02-01T10:00:00Z",
  },
  {
    id: "diag-002",
    workspace_id: "ws-diag-001",
    name: "Navigation Subsystem State Machine",
    diagram_type: "flow",
    payload_format: "mermaid",
    created_at: "2026-02-05T14:30:00Z",
    updated_at: "2026-02-07T09:00:00Z",
  },
];

// ---------------------------------------------------------------------------
// Render helper
// ---------------------------------------------------------------------------

const renderDiagramView = (route = "/diagrams") => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[route]}>
        <Routes>
          <Route path="/diagrams" element={<DiagramView />} />
          <Route path="/diagrams/:id" element={<DiagramView />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
};

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("DiagramView (REQ-053 smoke tests)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(workspaceContext.useWorkspace).mockReturnValue({
      activeWorkspace: MOCK_WORKSPACE,
    } as any);
  });

  it("[REQ-053] shows loading indicator while diagram list is in-flight", () => {
    vi.mocked(diagramsModule.diagramsApi.list).mockReturnValue(new Promise(() => {}));

    renderDiagramView();

    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("[REQ-053] renders without crashing when diagram list is empty", async () => {
    vi.mocked(diagramsModule.diagramsApi.list).mockResolvedValue({ results: [] } as any);

    renderDiagramView();

    await waitFor(() => {
      expect(screen.getByTestId("diagrams-empty")).toBeInTheDocument();
    });
  });

  it("[REQ-053] renders diagram names after list resolves", async () => {
    vi.mocked(diagramsModule.diagramsApi.list).mockResolvedValue({
      results: MOCK_DIAGRAMS,
    } as any);

    renderDiagramView();

    await waitFor(() => {
      expect(screen.getByText("System Context Diagram (C4 Level 1)")).toBeInTheDocument();
    });
    expect(screen.getByText("Navigation Subsystem State Machine")).toBeInTheDocument();
  });

  it("[REQ-053] shows create-diagram button and opens create form on click", async () => {
    vi.mocked(diagramsModule.diagramsApi.list).mockResolvedValue({ results: [] } as any);
    const user = userEvent.setup();

    renderDiagramView();

    await waitFor(() => {
      expect(screen.getByTestId("create-diagram-btn")).toBeInTheDocument();
    });

    await user.click(screen.getByTestId("create-diagram-btn"));
    expect(screen.getByTestId("create-diagram-form")).toBeInTheDocument();
  });

  it("[REQ-053][Task 5.1] diagram count is shown in the always-visible PageHeader summary", async () => {
    vi.mocked(diagramsModule.diagramsApi.list).mockResolvedValue({
      results: MOCK_DIAGRAMS,
    } as any);

    renderDiagramView();

    await waitFor(() => {
      expect(screen.getByTestId("page-header-count")).toBeInTheDocument();
    });
  });

  it("[Task 5.1] renders exactly one <h1> and a ListToolbar with search input", async () => {
    vi.mocked(diagramsModule.diagramsApi.list).mockResolvedValue({
      results: MOCK_DIAGRAMS,
    } as any);

    renderDiagramView();

    await waitFor(() => {
      expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    });
    expect(screen.getByTestId("diagram-list-search-input")).toBeInTheDocument();
  });
});
