/**
 * ARCH-L1-001 ReactFrontend — WorkspaceCard active-indicator tests.
 *
 * leaf_id: COMP-RF-002 (DashboardViews)
 * req_id:  REQ-L3-RF002-001 (Workspace-Kartenliste mit Metriken)
 *
 * BUG-18 regression (docs/SYSTEMAUDIT_2026-08-18.md §4): with 25+ workspaces
 * on the Dashboard, there was no way to tell which card represented the
 * currently active workspace — unlike the sidebar workspace switcher, which
 * already marks its active entry. Verifies the new `isActive` prop renders
 * a visible "active" badge and marks the card via `data-active`.
 */

import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { WorkspaceCard } from "../components/DashboardViews/WorkspaceCard";
import type { WorkspaceWithMetrics } from "../types";

vi.mock("../context/WorkspaceContext", () => ({
  useWorkspace: () => ({ terminologyLabel: (key: string) => key }),
}));

function makeWorkspace(
  overrides: Partial<WorkspaceWithMetrics> = {}
): WorkspaceWithMetrics {
  return {
    id: "ws-001",
    name: "Test Workspace",
    preset: "standard",
    terminology_profile: "se_mode",
    language: "en",
    is_active: true,
    closed_at: null,
    closed_by: null,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    requirement_count: 3,
    open_item_count: 1,
    ...overrides,
  } as WorkspaceWithMetrics;
}

describe("WorkspaceCard active-workspace indicator (BUG-18)", () => {
  it("shows no active badge and data-active=false when not the active workspace", () => {
    render(
      <WorkspaceCard
        workspace={makeWorkspace()}
        onSelect={vi.fn()}
        onOpenSettings={vi.fn()}
        isActive={false}
      />
    );

    expect(
      screen.queryByTestId("workspace-card-active-badge")
    ).not.toBeInTheDocument();
    expect(screen.getByTestId("workspace-card")).toHaveAttribute(
      "data-active",
      "false"
    );
  });

  it("shows an active badge and data-active=true for the active workspace", () => {
    render(
      <WorkspaceCard
        workspace={makeWorkspace()}
        onSelect={vi.fn()}
        onOpenSettings={vi.fn()}
        isActive={true}
      />
    );

    expect(
      screen.getByTestId("workspace-card-active-badge")
    ).toBeInTheDocument();
    expect(screen.getByTestId("workspace-card")).toHaveAttribute(
      "data-active",
      "true"
    );
  });
});
