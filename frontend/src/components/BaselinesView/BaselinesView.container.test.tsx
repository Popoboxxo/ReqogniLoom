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

  // Issue #48: the create form had no name field, so every baseline got the
  // backend's `Baseline <ISO timestamp>` fallback and the list was a wall of
  // indistinguishable timestamps.
  describe("issue #48 — naming a baseline", () => {
    const openCreateForm = async (): Promise<ReturnType<typeof userEvent.setup>> => {
      vi.mocked(baselinesModule.baselinesApi.list).mockResolvedValue({ results: [] } as never);
      vi.mocked(baselinesModule.baselinesApi.previewScope).mockResolvedValue({
        count: 0,
        artifact_ids: [],
      } as never);
      const user = userEvent.setup();
      renderBaselinesView();
      await waitFor(() => {
        expect(screen.queryByRole("status")).not.toBeInTheDocument();
      });
      await user.click(screen.getByTestId("page-header-overflow-trigger"));
      await user.click(screen.getByTestId("create-baseline-btn"));
      await waitFor(() => {
        expect(screen.getByTestId("create-baseline-form")).toBeInTheDocument();
      });
      return user;
    };

    it("sends the typed name on create", async () => {
      const user = await openCreateForm();
      vi.mocked(baselinesModule.baselinesApi.create).mockResolvedValue({
        id: "bl-new",
        name: "Release 1.2 sign-off",
      } as never);

      await user.type(screen.getByTestId("baseline-name-input"), "Release 1.2 sign-off");
      await user.click(screen.getByTestId("baseline-submit-btn"));

      await waitFor(() => {
        expect(baselinesModule.baselinesApi.create).toHaveBeenCalledWith(
          expect.objectContaining({ name: "Release 1.2 sign-off" }),
        );
      });
    });

    it("omits the field entirely when left blank, keeping the generated name", async () => {
      // Sending `name: ""` would store an empty name instead of letting the
      // backend generate its timestamp default.
      const user = await openCreateForm();
      vi.mocked(baselinesModule.baselinesApi.create).mockResolvedValue({ id: "bl-new" } as never);

      await user.click(screen.getByTestId("baseline-submit-btn"));

      await waitFor(() => {
        expect(baselinesModule.baselinesApi.create).toHaveBeenCalled();
      });
      const payload = vi.mocked(baselinesModule.baselinesApi.create).mock.calls[0]![0];
      expect(payload).not.toHaveProperty("name");
    });

    it("treats a whitespace-only name as blank", async () => {
      const user = await openCreateForm();
      vi.mocked(baselinesModule.baselinesApi.create).mockResolvedValue({ id: "bl-new" } as never);

      await user.type(screen.getByTestId("baseline-name-input"), "   ");
      await user.click(screen.getByTestId("baseline-submit-btn"));

      await waitFor(() => {
        expect(baselinesModule.baselinesApi.create).toHaveBeenCalled();
      });
      expect(vi.mocked(baselinesModule.baselinesApi.create).mock.calls[0]![0]).not.toHaveProperty(
        "name",
      );
    });

    it("surfaces the backend's unique-name rejection", async () => {
      // `uq_baseline_ws_name` — the one error a user can actually act on.
      const user = await openCreateForm();
      vi.mocked(baselinesModule.baselinesApi.create).mockRejectedValue({
        error: { code: "VALIDATION_ERROR", message: "Baseline name must be unique" },
      });

      await user.type(screen.getByTestId("baseline-name-input"), "Sprint-12 Freeze");
      await user.click(screen.getByTestId("baseline-submit-btn"));

      await waitFor(() => {
        expect(screen.getByText("Baseline name must be unique")).toBeInTheDocument();
      });
      // The form stays open so the name can be corrected in place.
      expect(screen.getByTestId("create-baseline-form")).toBeInTheDocument();
    });
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
