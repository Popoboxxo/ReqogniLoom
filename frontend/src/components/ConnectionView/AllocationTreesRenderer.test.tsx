/**
 * V.3 — the "Bäume" renderer.
 *
 * Covers the contract of the new mode, not the pure modules beneath it
 * (`allocation-trees.test.ts` / `edge-geometry.test.ts` own those): two columns
 * with real hierarchy, selection that survives a filter change, locked rows,
 * the edge overlay and its off switch, the disclosure's ARIA contract and the
 * drag write path with **entity** ids.
 *
 * jsdom has no layout, so `getBoundingClientRect()` is all-zero here. That is
 * enough for the edge-count contract (one path per resolvable edge) but says
 * nothing about pixels — the visual check belongs to the browser/E2E layer.
 */

import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactElement } from "react";
import de from "../../i18n/locales/de.json";

import type { AllocationRow } from "../../api/allocation-view";
import { AllocationTreesRenderer } from "./AllocationTreesRenderer";
import { useAllocationSelection } from "./useAllocationSelection";

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

function requirement(overrides: Partial<AllocationRow>): AllocationRow {
  return {
    kind: "requirement",
    id: "r1",
    artifact_id: "art-r1",
    parent_id: null,
    sort_key: "a",
    title: "Requirement 1",
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

function element(overrides: Partial<AllocationRow>): AllocationRow {
  return requirement({
    kind: "element",
    id: "e1",
    artifact_id: "art-e1",
    title: "Element 1",
    state: null,
    level: null,
    type: "component",
    category: null,
    allocation_intent: null,
    ...overrides,
  });
}

/** Parent with one child, on both sides — the smallest real hierarchy. */
const R1 = requirement({
  id: "r1",
  title: "Bremsen",
  artifact_id: "art-r1",
  sort_key: "a",
  allocated_to: "art-e1",
  allocation_trace_link_id: "link-1",
});
const R1A = requirement({
  id: "r1a",
  title: "Bremsen regeln",
  artifact_id: "art-r1a",
  parent_id: "art-r1",
  sort_key: "a1",
});
const R2 = requirement({
  id: "r2",
  title: "Lenken",
  artifact_id: "art-r2",
  sort_key: "b",
  allocated_to: "art-e2",
  allocation_trace_link_id: "link-2",
});
const R_LOCKED = requirement({
  id: "r3",
  title: "Fahrwerk",
  artifact_id: "art-r3",
  sort_key: "c",
  locked: "approved",
});

const E1 = element({ id: "e1", artifact_id: "art-e1", title: "Bremse" });
const E1A = element({
  id: "e1a",
  artifact_id: "art-e1a",
  parent_id: "art-e1",
  sort_key: "a1",
  title: "Bremsbelag",
});
const E2 = element({
  id: "e2",
  artifact_id: "art-e2",
  sort_key: "b",
  title: "Lenkung",
});

interface HarnessProps {
  requirements: AllocationRow[];
  elements: AllocationRow[];
  showEdges?: boolean;
  canEdit?: boolean;
  onAllocate?: (requirementId: string, elementId: string) => Promise<void>;
  onDeallocate?: (allocationTraceLinkId: string) => Promise<void>;
}

/**
 * The renderer is selection-agnostic by design (the page owns the state), so
 * every render test goes through this stateful harness — otherwise a filter
 * change could not be shown to preserve a tick.
 */
function Harness({
  requirements,
  elements,
  showEdges = true,
  canEdit = true,
  onAllocate = async () => undefined,
  onDeallocate = async () => undefined,
}: HarnessProps): ReactElement {
  const selection = useAllocationSelection(requirements);
  return (
    <AllocationTreesRenderer
      requirements={requirements}
      elements={elements}
      selection={selection}
      showEdges={showEdges}
      onAllocate={onAllocate}
      onDeallocate={onDeallocate}
      canEdit={canEdit}
    />
  );
}

function renderTrees(props: Partial<HarnessProps> = {}): {
  rerender: (next: Partial<HarnessProps>) => void;
} {
  const base: HarnessProps = {
    requirements: [R1, R1A, R2, R_LOCKED],
    elements: [E1, E1A, E2],
  };
  const { rerender } = render(<Harness {...base} {...props} />);
  return {
    rerender: (next) => rerender(<Harness {...base} {...props} {...next} />),
  };
}

function fakeDataTransfer(): {
  setData: (key: string, value: string) => void;
  getData: (key: string) => string;
  effectAllowed: string;
} {
  const store: Record<string, string> = {};
  return {
    setData: (key: string, value: string) => {
      store[key] = value;
    },
    getData: (key: string) => store[key] ?? "",
    effectAllowed: "",
  };
}

describe("AllocationTreesRenderer — structure", () => {
  it("renders_two_columns_with_hierarchy", () => {
    renderTrees();

    const requirementColumn = screen.getByRole("region", {
      name: de.connectionView.requirements,
    });
    const elementColumn = screen.getByRole("region", {
      name: de.connectionView.elements,
    });

    // Both columns are real labelled sections inside the one scroll container.
    expect(requirementColumn).toBeInTheDocument();
    expect(elementColumn).toBeInTheDocument();
    expect(screen.getByTestId("trees-scroll")).toContainElement(
      requirementColumn
    );
    expect(screen.getByTestId("trees-scroll")).toContainElement(elementColumn);

    // The child row lives inside the parent's labelled group, not next to it.
    const requirementGroup = within(requirementColumn).getByRole("group", {
      name: "Bremsen",
    });
    expect(within(requirementGroup).getByTestId("alloc-req-r1a")).toBeInTheDocument();
    expect(within(requirementColumn).getByTestId("alloc-req-r1")).toBeInTheDocument();

    const elementGroup = within(elementColumn).getByRole("group", {
      name: "Bremse",
    });
    expect(within(elementGroup).getByTestId("alloc-el-e1a")).toBeInTheDocument();
  });

  it("renders an empty state per column instead of an empty list", () => {
    renderTrees({ requirements: [], elements: [] });

    expect(screen.getByTestId("trees-requirements-empty")).toBeInTheDocument();
    expect(screen.getByTestId("trees-elements-empty")).toBeInTheDocument();
  });
});

describe("AllocationTreesRenderer — selection", () => {
  it("checkbox_selection_survives_filter_change", () => {
    const { rerender } = renderTrees();

    fireEvent.click(screen.getByTestId("alloc-select-r1"));
    expect(screen.getByTestId("alloc-select-r1")).toBeChecked();

    // Filter narrows the visible rows: the tick is kept in state, hidden.
    rerender({ requirements: [R2], elements: [E2] });
    expect(screen.queryByTestId("alloc-select-r1")).not.toBeInTheDocument();
    expect(screen.getByTestId("alloc-select-r2")).not.toBeChecked();

    // Widening the filter brings the tick back.
    rerender({});
    expect(screen.getByTestId("alloc-select-r1")).toBeChecked();
  });

  it("locked_rows_are_not_selectable", () => {
    renderTrees();

    const checkbox = screen.getByTestId("alloc-select-r3");
    expect(checkbox).toBeDisabled();

    fireEvent.click(checkbox);
    expect(checkbox).not.toBeChecked();
    expect(screen.getByTestId("alloc-req-r3")).toHaveAttribute(
      "data-selected",
      "false"
    );
  });

  it("a frozen row is neither draggable nor a write source", () => {
    renderTrees();
    expect(screen.getByTestId("alloc-req-r1")).toHaveAttribute(
      "draggable",
      "true"
    );
    expect(screen.getByTestId("alloc-req-r3")).toHaveAttribute(
      "draggable",
      "false"
    );
  });
});

describe("AllocationTreesRenderer — edge overlay", () => {
  it("edge_count_equals_allocation_count", () => {
    renderTrees();

    expect(screen.getByTestId("allocation-edges")).toHaveAttribute(
      "aria-hidden",
      "true"
    );
    const edges = screen.getAllByTestId(/^allocation-edge-/);
    // One path per requirement whose target is part of the rendered set:
    // r1 -> e1 and r2 -> e2. r1a and r3 are unallocated.
    expect(edges).toHaveLength(2);
    expect(screen.getByTestId("allocation-edge-r1")).toBeInTheDocument();
    expect(screen.getByTestId("allocation-edge-r2")).toBeInTheDocument();
  });

  it("skips an edge whose element sits outside the filter", () => {
    // r1's target `art-e1` is no longer rendered, so no edge may be drawn —
    // an edge to nowhere is worse than a missing one.
    renderTrees({ elements: [E2] });

    expect(screen.queryByTestId("allocation-edge-r1")).not.toBeInTheDocument();
    expect(screen.getByTestId("allocation-edge-r2")).toBeInTheDocument();
  });

  it("show_edges_false_renders_no_svg_but_keeps_target_text", () => {
    renderTrees({ showEdges: false });

    expect(screen.queryByTestId("allocation-edges")).not.toBeInTheDocument();
    expect(screen.queryByTestId("allocation-edge-r1")).not.toBeInTheDocument();
    // The target text is the fallback that survives the overlay being off.
    expect(screen.getByTestId("alloc-target-r1")).toHaveTextContent("Bremse");
    expect(screen.getByTestId("alloc-target-r1a")).toHaveTextContent(
      de.connectionView.unallocated
    );
  });
});

describe("AllocationTreesRenderer — disclosure", () => {
  it("keyboard_expand_uses_button_with_aria_expanded", () => {
    renderTrees();

    const toggle = screen.getByTestId("alloc-expand-r1");
    expect(toggle.tagName).toBe("BUTTON");
    expect(toggle).toHaveAttribute("aria-expanded", "true");

    const subtreeId = toggle.getAttribute("aria-controls");
    expect(subtreeId).toBeTruthy();
    // While expanded the group is in the accessibility tree and named by the
    // row title.
    expect(screen.getByRole("group", { name: "Bremsen" })).toHaveAttribute(
      "id",
      subtreeId as string
    );
    const subtree = document.getElementById(subtreeId as string);
    expect(subtree).not.toBeNull();
    expect(subtree).not.toHaveAttribute("hidden");

    // The disclosure is reachable by Enter (a native button), so the keyboard
    // path is the button itself and no click handler has to mimic it.
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    // `hidden` keeps `aria-controls` resolving; a hidden group is out of the
    // accessibility tree, so it is queried by id from here on.
    expect(subtree).toHaveAttribute("hidden");

    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(subtree).not.toHaveAttribute("hidden");
  });

  it("a leaf row has no expander", () => {
    renderTrees();
    expect(screen.queryByTestId("alloc-expand-r2")).not.toBeInTheDocument();
  });
});

describe("AllocationTreesRenderer — write path", () => {
  it("drag_calls_allocate_with_entity_ids", async () => {
    const onAllocate = vi.fn<
      (requirementId: string, elementId: string) => Promise<void>
    >(async () => undefined);
    renderTrees({ onAllocate });

    const dataTransfer = fakeDataTransfer();
    fireEvent.dragStart(screen.getByTestId("alloc-req-r1"), { dataTransfer });
    fireEvent.drop(screen.getByTestId("alloc-el-e1"), { dataTransfer });

    // Entity ids (`r1` / `e1`), never the backing Artifact ids
    // (`art-r1` / `art-e1`) — the bulk endpoint expects the entity ids.
    await waitFor(() => expect(onAllocate).toHaveBeenCalledWith("r1", "e1"));
  });

  it("deallocate_passes_the_trace_link_id", async () => {
    const onDeallocate = vi.fn<
      (allocationTraceLinkId: string) => Promise<void>
    >(async () => undefined);
    renderTrees({ onDeallocate });

    fireEvent.click(screen.getByTestId("alloc-deallocate-r1"));

    await waitFor(() => expect(onDeallocate).toHaveBeenCalledWith("link-1"));
  });

  it("a rejected write is reported instead of swallowed", async () => {
    const onAllocate = vi.fn(async () => {
      throw new Error("allocation rejected");
    });
    renderTrees({ onAllocate });

    const dataTransfer = fakeDataTransfer();
    fireEvent.dragStart(screen.getByTestId("alloc-req-r2"), { dataTransfer });
    fireEvent.drop(screen.getByTestId("alloc-el-e2"), { dataTransfer });

    const alert = await screen.findByTestId("allocation-error");
    expect(alert).toHaveAttribute("role", "alert");
    expect(alert).toHaveTextContent("allocation rejected");
  });

  it("read_only_access_offers_no_write_affordance", () => {
    renderTrees({ canEdit: false });

    expect(screen.getByTestId("alloc-select-r1")).toBeDisabled();
    expect(screen.getByTestId("alloc-req-r1")).toHaveAttribute(
      "draggable",
      "false"
    );
    expect(screen.queryByTestId("alloc-deallocate-r1")).not.toBeInTheDocument();
  });
});
