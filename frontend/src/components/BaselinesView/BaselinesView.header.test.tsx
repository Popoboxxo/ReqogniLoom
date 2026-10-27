/**
 * BaselinesView header action placement (#1405 R1-04).
 *
 * req_id: REQ-L1-018, REQ-L2-RF-030
 *
 * The create action used to live behind the PageHeader overflow menu, so
 * "Neue Baseline" was only reachable after opening "⋯" even though it is the
 * page's single create action. It now renders as a visible secondary header
 * action — present and clickable without any menu interaction — while staying
 * deliberately non-primary (the compare action owns that slot's sibling).
 *
 * Uses QueryClientProvider (useBaselinesData — TanStack Query) and the same
 * module-boundary mocks as BaselinesView.container.test.tsx.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";

vi.mock("../../api/baselines");
vi.mock("../../api/artifacts");
vi.mock("../../context/WorkspaceContext");
vi.mock("../../context/AuthContext", () => ({
  useAuth: () => ({ roles: ["admin"] }),
}));
vi.mock("react-i18next", () => {
  const t = (key: string, fallbackOrOptions?: string | Record<string, unknown>): string =>
    typeof fallbackOrOptions === "string" ? fallbackOrOptions : key;
  return { useTranslation: () => ({ t }) };
});

import * as baselinesModule from "../../api/baselines";
import * as artifactsModule from "../../api/artifacts";
import * as workspaceContext from "../../context/WorkspaceContext";

import BaselinesView from "./BaselinesView";

const MOCK_WORKSPACE = { id: "ws-bl-header", name: "Header WS", preset: "standard" };

const renderBaselinesView = () => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <BaselinesView />
    </QueryClientProvider>,
  );
};

describe("BaselinesView page header (#1405 R1-04)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(workspaceContext.useWorkspace).mockReturnValue({
      activeWorkspace: MOCK_WORKSPACE,
    } as any);
    vi.mocked(artifactsModule.artifactsApi.list).mockResolvedValue({
      results: [],
    } as any);
    vi.mocked(baselinesModule.baselinesApi.list).mockResolvedValue({
      results: [],
    } as any);
  });

  it("shows the create action without opening the overflow menu", async () => {
    renderBaselinesView();

    // No menu interaction at all: the trigger is either absent (no overflow
    // actions left) or must stay closed.
    expect(screen.queryByTestId("page-header-overflow-menu")).not.toBeInTheDocument();

    const createBtn = await screen.findByTestId("create-baseline-btn");
    expect(createBtn).toBeVisible();
    // Secondary, not primary: it renders in the header's secondary row.
    expect(createBtn).toHaveClass("btn-secondary");
  });
});
