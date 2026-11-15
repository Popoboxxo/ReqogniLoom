/**
 * V.4 — the two-row connection filter bar.
 *
 * Row 1 (quick filters, search, the "Weitere Filter" trigger and the counters)
 * is always rendered; the free filters and the saved views live in the
 * popover (`filter-more`). The open/closed state is owned by `ConnectionView`
 * (preference-backed), so this component only renders `expanded` and reports
 * the toggle — these tests pin that contract plus the badge count and the
 * failed-write message that must not close the popover.
 */

import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import de from "../../i18n/locales/de.json";

import type { AllocationRow } from "../../api/allocation-view";
import type { SavedConnectionView } from "../../api/connection-views";
import { FilterBar, type FilterBarProps } from "./FilterBar";
import type { ConnectionFilters } from "./useAllocationView";

vi.mock("react-i18next", () => {
  function lookup(key: string): string | undefined {
    const value = key
      .split(".")
      .reduce<unknown>(
        (node, segment) =>
          node && typeof node === "object"
            ? (node as Record<string, unknown>)[segment]
            : undefined,
        de
      );
    return typeof value === "string" ? value : undefined;
  }
  return {
    useTranslation: () => ({
      t: (key: string, options?: Record<string, unknown>) => {
        const template = lookup(key) ?? key;
        if (!options) return template;
        return Object.entries(options).reduce(
          (acc, [name, value]) => acc.replace(`{{${name}}}`, String(value)),
          template
        );
      },
    }),
  };
});

function requirement(overrides: Partial<AllocationRow> = {}): AllocationRow {
  return {
    kind: "requirement",
    id: "r1",
    artifact_id: "art-r1",
    parent_id: null,
    sort_key: "a",
    title: "Bremsen",
    state: "draft",
    tier_key: null,
    tier_name: null,
    level: 1,
    type: "SyReq",
    category: "functional",
    allocated_to: null,
    allocation_trace_link_id: null,
    element_id: null,
    allocation_intent: "unassigned",
    locked: null,
    findings: [],
    group: null,
    ...overrides,
  };
}

const ELEMENT = requirement({
  kind: "element",
  id: "e1",
  artifact_id: "art-e1",
  title: "Bremse",
  state: null,
  level: null,
  type: "component",
  category: null,
  allocation_intent: null,
});

function filters(overrides: Partial<ConnectionFilters> = {}): ConnectionFilters {
  return { page: 1, pageSize: 50, ...overrides };
}

const SAVED_VIEW: SavedConnectionView = {
  id: "v1",
  name: "Offene Bremsen",
  params: { q: "bremse" },
};

function renderBar(options: Partial<FilterBarProps> = {}): {
  onChange: ReturnType<typeof vi.fn>;
  onToggleExpanded: ReturnType<typeof vi.fn>;
  onReset: ReturnType<typeof vi.fn>;
} {
  const onChange = vi.fn();
  const onToggleExpanded = vi.fn();
  const onReset = vi.fn();
  render(
    <FilterBar
      filters={filters()}
      meta={{ total: 4, unallocated: 2, locked: 1, findings: 3 }}
      tiers={[{ tier_key: "L1", name: { de: "System", en: "System" } } as never]}
      elements={[ELEMENT]}
      groups={[{ id: "g1", title: "Bremssystem" }]}
      states={["draft", "approved"]}
      categories={["functional"]}
      savedViews={[SAVED_VIEW]}
      expanded={false}
      onToggleExpanded={onToggleExpanded}
      onChange={onChange}
      onReset={onReset}
      onSaveView={vi.fn()}
      onApplyView={vi.fn()}
      onDeleteView={vi.fn()}
      {...options}
    />
  );
  return { onChange, onToggleExpanded, onReset };
}

describe("FilterBar — row 1 is always visible", () => {
  it("renders the quick filters, search, trigger and counters without the popover", () => {
    renderBar();

    expect(screen.getByTestId("quick-open")).toBeInTheDocument();
    expect(screen.getByTestId("quick-unallocated")).toBeInTheDocument();
    expect(screen.getByTestId("quick-locked")).toBeInTheDocument();
    expect(screen.getByTestId("quick-findings")).toBeInTheDocument();
    expect(screen.getByTestId("filter-q")).toBeInTheDocument();
    expect(screen.getByTestId("filter-more-toggle")).toBeInTheDocument();
    expect(screen.getByTestId("counter-total")).toHaveTextContent("4");
    expect(screen.getByTestId("counter-unallocated")).toHaveTextContent("2");
    expect(screen.getByTestId("counter-locked")).toHaveTextContent("1");
    expect(screen.getByTestId("counter-findings")).toHaveTextContent("3");

    // The second row is a popover: closed means not rendered.
    expect(screen.queryByTestId("filter-more")).not.toBeInTheDocument();
    expect(screen.queryByTestId("filter-tier")).not.toBeInTheDocument();
    expect(screen.queryByTestId("saved-view-name")).not.toBeInTheDocument();
  });

  it("reports the toggle instead of keeping its own open state", () => {
    const { onToggleExpanded } = renderBar();

    fireEvent.click(screen.getByTestId("filter-more-toggle"));

    expect(onToggleExpanded).toHaveBeenCalledTimes(1);
    // Still closed: the component renders the prop it is given.
    expect(screen.queryByTestId("filter-more")).not.toBeInTheDocument();
  });

  it("counts only the active popover filters in the badge", () => {
    renderBar({
      filters: filters({ tier: "L1", state: "draft", q: "bremse" }),
    });

    // `q` lives in row 1, so it is not part of the badge.
    expect(screen.getByTestId("filter-more-toggle")).toHaveTextContent(
      "Weitere Filter (2)"
    );
  });

  it("shows the plain label when no popover filter is active", () => {
    renderBar();
    expect(screen.getByTestId("filter-more-toggle")).toHaveTextContent(
      "Weitere Filter"
    );
  });
});

describe("FilterBar — the popover", () => {
  it("renders the free filters and the saved views when expanded", () => {
    renderBar({ expanded: true });

    const popover = screen.getByTestId("filter-more");
    expect(within(popover).getByTestId("filter-tier")).toBeInTheDocument();
    expect(within(popover).getByTestId("filter-type")).toBeInTheDocument();
    expect(within(popover).getByTestId("filter-category")).toBeInTheDocument();
    expect(within(popover).getByTestId("filter-state")).toBeInTheDocument();
    expect(
      within(popover).getByTestId("filter-element-subtree")
    ).toBeInTheDocument();
    expect(within(popover).getByTestId("filter-group")).toBeInTheDocument();
    expect(within(popover).getByTestId("saved-view-name")).toBeInTheDocument();
    expect(
      within(popover).getByTestId("saved-view-apply-v1")
    ).toHaveTextContent("Offene Bremsen");
  });

  it("carries aria-expanded and a resolvable aria-controls", () => {
    renderBar({ expanded: true });

    const toggle = screen.getByTestId("filter-more-toggle");
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    const controls = toggle.getAttribute("aria-controls");
    expect(controls).toBeTruthy();
    expect(document.getElementById(controls as string)).toBe(
      screen.getByTestId("filter-more")
    );
  });

  it("reports a filter patch from inside the popover", () => {
    const { onChange } = renderBar({ expanded: true });

    fireEvent.change(screen.getByTestId("filter-tier"), {
      target: { value: "L1" },
    });

    expect(onChange).toHaveBeenCalledWith({ tier: "L1" });
  });

  it("keeps the popover open and shows a failed preference write", () => {
    renderBar({
      expanded: true,
      expandedError: "Der Filterzustand konnte nicht gespeichert werden: offline",
    });

    expect(screen.getByTestId("filter-more")).toBeInTheDocument();
    expect(screen.getByTestId("filter-more-error")).toHaveTextContent(
      "konnte nicht gespeichert werden"
    );
  });
});
