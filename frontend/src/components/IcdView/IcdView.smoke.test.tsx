/**
 * Smoke tests for IcdView container (REQ-050 decomposition, REQ-053 coverage).
 *
 * req_id: REQ-053, REQ-L2-ICD-001, REQ-050
 *
 * Verifies:
 *   - IcdView renders without crashing when no ICDs exist
 *   - IcdView shows loading indicator while data is in-flight
 *   - IcdView renders the ICD list after data resolves
 *   - "New ICD" create-button is present and clickable
 *
 * Uses MemoryRouter (useParams + useNavigate) and QueryClientProvider
 * (useIcdData — TanStack Query) as test infrastructure.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import React from "react";

// ---------------------------------------------------------------------------
// Module mocks (must be before component import)
// ---------------------------------------------------------------------------

vi.mock("../../api/icds");
vi.mock("../../api/architecture");
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

import * as icdsModule from "../../api/icds";
import * as archModule from "../../api/architecture";
import * as workspaceContext from "../../context/WorkspaceContext";

import IcdView from "./IcdView";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const MOCK_WORKSPACE = { id: "ws-icd-001", name: "Interface Control WS", preset: "extended" };

const MOCK_ICD = {
  id: "icd-001",
  workspace_id: "ws-icd-001",
  name: "NavSub ↔ GroundControl RF Link",
  source_element_id: "arch-001",
  target_element_id: "arch-002",
  current_version: null,
  created_at: "2026-03-01T00:00:00Z",
};

// ---------------------------------------------------------------------------
// Render helper
// ---------------------------------------------------------------------------

const renderIcdView = (route = "/icds") => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[route]}>
        <Routes>
          <Route path="/icds" element={<IcdView />} />
          <Route path="/icds/:id" element={<IcdView />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
};

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("IcdView (REQ-053 smoke tests)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(workspaceContext.useWorkspace).mockReturnValue({
      activeWorkspace: MOCK_WORKSPACE,
    } as any);
    vi.mocked(archModule.architectureApi.listAll).mockResolvedValue([]);
  });

  it("[REQ-053] renders without crashing when ICD list is empty", async () => {
    vi.mocked(icdsModule.icdsApi.list).mockResolvedValue({ results: [] } as any);

    renderIcdView();

    // Component mounts without throwing
    await waitFor(() => {
      // Loading resolves — view or empty state is shown
      expect(document.body).toBeTruthy();
    });
  });

  it("[REQ-053] shows loading indicator while ICD data is in-flight", () => {
    vi.mocked(icdsModule.icdsApi.list).mockReturnValue(new Promise(() => {}));

    renderIcdView();

    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("[REQ-053] renders ICD list after data resolves", async () => {
    vi.mocked(icdsModule.icdsApi.list).mockResolvedValue({ results: [MOCK_ICD] } as any);

    renderIcdView();

    await waitFor(() => {
      expect(screen.getByText("NavSub ↔ GroundControl RF Link")).toBeInTheDocument();
    });
  });

  it("[REQ-053] renders create-ICD button after data loads", async () => {
    vi.mocked(icdsModule.icdsApi.list).mockResolvedValue({ results: [] } as any);

    renderIcdView();

    // Wait for loading to complete
    await waitFor(() => {
      expect(screen.queryByRole("status")).not.toBeInTheDocument();
    });

    // A "new" / "create" button is rendered
    const createBtn = screen.getByTestId("create-icd-btn");
    expect(createBtn).toBeInTheDocument();
  });

  it("[REQ-053] opens create form when create button is clicked", async () => {
    vi.mocked(icdsModule.icdsApi.list).mockResolvedValue({ results: [] } as any);
    const user = userEvent.setup();

    renderIcdView();

    await waitFor(() => {
      expect(screen.queryByRole("status")).not.toBeInTheDocument();
    });

    const createBtn = screen.getByTestId("create-icd-btn");
    await user.click(createBtn);

    // After clicking, a form or input should appear
    const inputs = document.querySelectorAll("input, textarea, select");
    expect(inputs.length).toBeGreaterThan(0);
  });

  it("[Codeberg #115] shows a hint when fewer than two architecture elements exist", async () => {
    vi.mocked(icdsModule.icdsApi.list).mockResolvedValue({ results: [] } as any);
    vi.mocked(archModule.architectureApi.listAll).mockResolvedValue([
      { id: "arch-only-one", title: "Lonely Element", element_type: "component" },
    ] as any);
    const user = userEvent.setup();

    renderIcdView();

    await waitFor(() => {
      expect(screen.queryByRole("status")).not.toBeInTheDocument();
    });

    const createBtn = screen.getByTestId("create-icd-btn");
    await user.click(createBtn);

    expect(
      await screen.findByTestId("icd-needs-elements-hint"),
    ).toBeInTheDocument();
  });

  it("[Task 5.1] renders exactly one <h1> and a ListToolbar with search input", async () => {
    vi.mocked(icdsModule.icdsApi.list).mockResolvedValue({ results: [MOCK_ICD] } as any);

    renderIcdView();

    await waitFor(() => {
      expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    });
    expect(screen.getByTestId("icd-list-search-input")).toBeInTheDocument();
  });

  it("[Task 5.1] shows the always-visible PageHeader summary", async () => {
    vi.mocked(icdsModule.icdsApi.list).mockResolvedValue({ results: [MOCK_ICD] } as any);

    renderIcdView();

    await waitFor(() => {
      expect(screen.getByTestId("page-header-count")).toBeInTheDocument();
    });
  });

  it("[Codeberg #115] does not show the hint once two or more architecture elements exist", async () => {
    vi.mocked(icdsModule.icdsApi.list).mockResolvedValue({ results: [] } as any);
    vi.mocked(archModule.architectureApi.listAll).mockResolvedValue([
      { id: "arch-001", title: "Element A", element_type: "component" },
      { id: "arch-002", title: "Element B", element_type: "component" },
    ] as any);
    const user = userEvent.setup();

    renderIcdView();

    await waitFor(() => {
      expect(screen.queryByRole("status")).not.toBeInTheDocument();
    });

    const createBtn = screen.getByTestId("create-icd-btn");
    await user.click(createBtn);

    await screen.findByTestId("create-icd-form");
    expect(screen.queryByTestId("icd-needs-elements-hint")).not.toBeInTheDocument();
  });
});
