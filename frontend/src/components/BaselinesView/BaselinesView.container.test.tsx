/**
 * Smoke tests for BaselinesView container + useBaselinesData hook
 * (REQ-050 decomposition, REQ-053 coverage).
 *
 * req_id: REQ-053, REQ-L1-018, REQ-L1-049, REQ-050
 *
 * Verifies:
 *   - BaselinesView renders loading state while data is in-flight
 *   - BaselinesView renders baseline list after data resolves
 *   - Create-baseline button is present
 *   - Compare button is present
 *   - Error state renders when the API call fails
 *
 * Uses QueryClientProvider (useBaselinesData — TanStack Query).
 * No routing required (BaselinesView does not use useParams/useNavigate).
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";

// ---------------------------------------------------------------------------
// Module mocks (must precede component import)
// ---------------------------------------------------------------------------

vi.mock("../../api/baselines");
vi.mock("../../api/artifacts");
vi.mock("../../context/WorkspaceContext");
// UI-21: BaselinesView now reads `roles` to gate the GH-513 override panel.
vi.mock("../../context/AuthContext", () => ({
  useAuth: () => ({ roles: ["admin"] }),
}));
vi.mock("react-i18next", () => {
  // Second arg is either a string fallback or an i18n interpolation options object.
  // In tests we just return the key so the component renders without crashing.
  const t = (key: string, fallbackOrOptions?: string | Record<string, unknown>): string =>
    typeof fallbackOrOptions === "string" ? fallbackOrOptions : key;
  return { useTranslation: () => ({ t }) };
});

import * as baselinesModule from "../../api/baselines";
import * as artifactsModule from "../../api/artifacts";
import * as workspaceContext from "../../context/WorkspaceContext";

import BaselinesView from "./BaselinesView";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const MOCK_WORKSPACE = { id: "ws-bl-001", name: "Release Engineering WS", preset: "standard" };

const MOCK_BASELINES = [
  {
    id: "bl-001",
    workspace_id: "ws-bl-001",
    name: "Sprint-12 Freeze",
    scope: "project",
    artifact_id: null,
    created_at: "2026-04-01T00:00:00Z",
  },
  {
    id: "bl-002",
    workspace_id: "ws-bl-001",
    name: "Mission CDR Baseline",
    scope: "global",
    artifact_id: null,
    created_at: "2026-04-15T00:00:00Z",
  },
];

// ---------------------------------------------------------------------------
// Render helper
// ---------------------------------------------------------------------------

const renderBaselinesView = () => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <BaselinesView />
    </QueryClientProvider>
  );
};

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("BaselinesView container (REQ-053 smoke tests)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(workspaceContext.useWorkspace).mockReturnValue({
      activeWorkspace: MOCK_WORKSPACE,
    } as any);
    vi.mocked(artifactsModule.artifactsApi.list).mockResolvedValue({
      results: [],
    } as any);
  });

  it("[REQ-053] shows loading status while baseline data is in-flight", () => {
    vi.mocked(baselinesModule.baselinesApi.list).mockReturnValue(new Promise(() => {}));

    renderBaselinesView();

    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("[REQ-053] renders baseline names after list resolves", async () => {
    vi.mocked(baselinesModule.baselinesApi.list).mockResolvedValue({
      results: MOCK_BASELINES,
    } as any);

    renderBaselinesView();

    await waitFor(() => {
      expect(screen.getByText("Sprint-12 Freeze")).toBeInTheDocument();
    });
    expect(screen.getByText("Mission CDR Baseline")).toBeInTheDocument();
  });

  it("[REQ-053] renders without crashing when baseline list is empty", async () => {
    vi.mocked(baselinesModule.baselinesApi.list).mockResolvedValue({ results: [] } as any);

    renderBaselinesView();

    await waitFor(() => {
      expect(screen.queryByRole("status")).not.toBeInTheDocument();
    });
    expect(screen.getByTestId("baselines-view")).toBeInTheDocument();
  });

  it("[REQ-053] create-baseline button opens the create form with a save button", async () => {
    vi.mocked(baselinesModule.baselinesApi.list).mockResolvedValue({ results: [] } as any);
    vi.mocked(baselinesModule.baselinesApi.previewScope).mockResolvedValue({
      count: 0,
      artifact_ids: [],
    } as any);
    const user = userEvent.setup();

    renderBaselinesView();

    await waitFor(() => {
      expect(screen.queryByRole("status")).not.toBeInTheDocument();
    });

    // Task 5.2: baseline creation is an overflow action, not a primary
    // header button — open the "..." menu first.
    await user.click(screen.getByTestId("page-header-overflow-trigger"));
    await user.click(screen.getByTestId("create-baseline-btn"));

    // Create form appears with scope selector and save button
    await waitFor(() => {
      expect(screen.getByTestId("create-baseline-form")).toBeInTheDocument();
    });
    expect(screen.getByTestId("baseline-submit-btn")).toBeInTheDocument();
    expect(screen.getByTestId("baseline-scope-group")).toBeInTheDocument();
  });

  it("[REQ-053] renders error alert when API returns an error", async () => {
    vi.mocked(baselinesModule.baselinesApi.list).mockRejectedValue(
      { error: { message: "baseline service unavailable" } }
    );

    renderBaselinesView();

    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeInTheDocument();
    });
  });
});
