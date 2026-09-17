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
import { render, screen, fireEvent } from "@testing-library/react";
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

describe("WorkspaceCard nested-interactive-elements a11y fix (GESAMTTEST_BERICHT_2026-08-21.md §5 finding 6)", () => {
  it("does not nest the preset/mode-change button inside the card's role=button region", () => {
    render(
      <WorkspaceCard
        workspace={makeWorkspace()}
        onSelect={vi.fn()}
        onOpenSettings={vi.fn()}
        isActive={false}
      />
    );

    // The outer `workspace-card` element is a plain (non-interactive)
    // wrapper — several e2e specs read its innerText() expecting it to
    // include BOTH the card content and the preset badge text, and click()
    // it expecting the click to land on the card's actual clickable region
    // (below), so it deliberately does NOT carry role="button" itself.
    const card = screen.getByTestId("workspace-card");
    expect(card).not.toHaveAttribute("role", "button");

    const clickableRegion = screen.getByTestId("workspace-card-clickable-region");
    expect(clickableRegion).toHaveAttribute("role", "button");

    // The preset/mode-change button must exist (still reachable, still
    // clickable) but must NOT be a DOM descendant of the clickable region's
    // role="button" element — a real <button> nested inside another
    // role="button" element is an invalid, screen-reader-confusing
    // accessibility-tree state. It IS a descendant of the outer wrapper
    // (see above), just a sibling of the clickable region, not nested in it.
    const presetBadge = screen.getByTestId("workspace-card-preset-badge");
    expect(presetBadge.tagName).toBe("BUTTON");
    expect(clickableRegion.contains(presetBadge)).toBe(false);
    expect(card.contains(presetBadge)).toBe(true);

    // Equivalent check via testing-library's own role query: exactly one
    // "button" role match overall for this card+badge pair (not two nested
    // ones under a single ancestor), and neither is an ancestor of the
    // other.
    const buttons = screen.getAllByRole("button");
    expect(buttons).toHaveLength(2);
    expect(buttons).toContain(clickableRegion);
    expect(buttons).toContain(presetBadge);
  });

  it("still routes preset-badge clicks to onOpenSettings without also triggering onSelect", () => {
    const onSelect = vi.fn();
    const onOpenSettings = vi.fn();
    render(
      <WorkspaceCard
        workspace={makeWorkspace()}
        onSelect={onSelect}
        onOpenSettings={onOpenSettings}
        isActive={false}
      />
    );

    fireEvent.click(screen.getByTestId("workspace-card-preset-badge"));

    expect(onOpenSettings).toHaveBeenCalledTimes(1);
    expect(onSelect).not.toHaveBeenCalled();
  });

  it("still routes clicks on the card's clickable region to onSelect (mirrors a real click landing on the card body, as in e2e's firstCard.click())", () => {
    const onSelect = vi.fn();
    render(
      <WorkspaceCard
        workspace={makeWorkspace()}
        onSelect={onSelect}
        onOpenSettings={vi.fn()}
        isActive={false}
      />
    );

    fireEvent.click(screen.getByTestId("workspace-card-clickable-region"));

    expect(onSelect).toHaveBeenCalledTimes(1);
  });
});

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
