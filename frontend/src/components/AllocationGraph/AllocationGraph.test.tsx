/**
 * P5 Task 5.3 — interactive allocation card graph.
 *
 * Covers the contracts the plan names: view mode renders no write handle and
 * exposes no connect path, edit mode's drag calls the atomic bulk allocate,
 * frozen cards have no handle, the keyboard "Allokieren auf …" path works, and
 * collapse/expand hides descendants while keeping the card.
 *
 * `@xyflow/react` is replaced by `src/test/xyflow-stub.tsx`: it renders the
 * real card components (handles and markers stay real) and exposes one connect
 * button per ordered node pair.
 */

import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import de from "../../i18n/locales/de.json";

import type { AllocationRow } from "../../api/allocation-view";
import {
  defaultCardFieldConfigMap,
  type CardFieldConfigMap,
} from "./cardFields";
import { AllocationGraph } from "./AllocationGraph";

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

vi.mock("@xyflow/react", async () =>
  (await import("../../test/xyflow-stub")).createXyflowStub()
);

function row(overrides: Partial<AllocationRow>): AllocationRow {
  return {
    kind: "requirement",
    id: "r1",
    artifact_id: "art-r1",
    parent_id: null,
    sort_key: "a",
    title: "Bremsdruck regeln",
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
  return row({
    kind: "element",
    id: "e1",
    artifact_id: "art-e1",
    title: "Bremse",
    state: null,
    level: null,
    type: "component",
    category: null,
    allocation_intent: null,
    ...overrides,
  });
}

const R1 = row({ id: "r1", sort_key: "a", title: "Bremsdruck regeln" });
const R2 = row({
  id: "r2",
  sort_key: "b",
  title: "Bremsweg messen",
  allocated_to: "art-e1",
  allocation_trace_link_id: "link-2",
  element_id: "e1",
});
const E1 = element({ id: "e1", artifact_id: "art-e1", sort_key: "a", title: "Bremse" });
const E2 = element({ id: "e2", artifact_id: "art-e2", sort_key: "b", title: "Lenkung" });

function renderGraph(options: {
  requirements?: AllocationRow[];
  elements?: AllocationRow[];
  canEdit?: boolean;
  cardFields?: CardFieldConfigMap;
  allocate?: ReturnType<typeof vi.fn>;
} = {}): { allocate: ReturnType<typeof vi.fn> } {
  const allocate =
    options.allocate ??
    vi
      .fn<(requirementId: string, elementId: string) => Promise<void>>()
      .mockResolvedValue(undefined);
  render(
    <AllocationGraph
      requirements={options.requirements ?? [R1, R2]}
      elements={options.elements ?? [E1, E2]}
      allocate={
        allocate as unknown as (
          requirementId: string,
          elementId: string
        ) => Promise<void>
      }
      canEdit={options.canEdit ?? true}
      cardFields={options.cardFields}
    />
  );
  return { allocate };
}

beforeEach(() => {
  window.localStorage.clear();
});

describe("AllocationGraph — view/edit mode", () => {
  it("renders no allocation handle and no connect path in the default view mode", () => {
    renderGraph();

    expect(screen.getByTestId("graph-mode-view")).toHaveAttribute(
      "aria-pressed",
      "true"
    );
    expect(screen.queryByTestId("req-allocate-handle-r1")).not.toBeInTheDocument();
    expect(
      screen.queryByTestId("stub-connect-req:r1__el:e1")
    ).not.toBeInTheDocument();
    expect(screen.getByTestId("xyflow-stub")).toHaveAttribute(
      "data-connectable",
      "false"
    );
  });

  it("requires write authority for the Bearbeiten mode", () => {
    renderGraph({ canEdit: false });

    const edit = screen.getByTestId("graph-mode-edit");
    expect(edit).toBeDisabled();
    fireEvent.click(edit);
    expect(screen.getByTestId("graph-mode-view")).toHaveAttribute(
      "aria-pressed",
      "true"
    );
    expect(screen.queryByTestId("req-allocate-handle-r1")).not.toBeInTheDocument();
  });
});

describe("AllocationGraph — drag allocates and re-allocates", () => {
  it("allocates an unallocated requirement through the atomic bulk write", async () => {
    const { allocate } = renderGraph();

    fireEvent.click(screen.getByTestId("graph-mode-edit"));
    expect(screen.getByTestId("req-allocate-handle-r1")).toBeInTheDocument();

    fireEvent.click(screen.getByTestId("stub-connect-req:r1__el:e2"));

    await waitFor(() => expect(allocate).toHaveBeenCalledWith("r1", "e2"));
  });

  it("re-allocates an already allocated requirement onto another element", async () => {
    const { allocate } = renderGraph();

    fireEvent.click(screen.getByTestId("graph-mode-edit"));
    fireEvent.click(screen.getByTestId("stub-connect-req:r2__el:e2"));

    await waitFor(() => expect(allocate).toHaveBeenCalledWith("r2", "e2"));
  });
});

describe("AllocationGraph — connection highlighting", () => {
  it("highlights the edges of the clicked card", () => {
    renderGraph();

    const edge = screen.getByTestId("stub-edge-allocation:r2");
    expect(edge.getAttribute("data-classname")).not.toContain("highlighted");

    fireEvent.click(screen.getByTestId("stub-select-req:r2"));

    expect(
      screen.getByTestId("stub-edge-allocation:r2").getAttribute("data-classname")
    ).toContain("allocationEdge--highlighted");
  });
});

describe("AllocationGraph — frozen cards", () => {
  it("gives a frozen requirement no allocation handle and no write path", async () => {
    const frozen = row({
      id: "r3",
      sort_key: "c",
      title: "Gespert",
      locked: { state: "Freigegeben" },
    });
    const { allocate } = renderGraph({ requirements: [R1, frozen] });

    fireEvent.click(screen.getByTestId("graph-mode-edit"));

    expect(screen.queryByTestId("req-allocate-handle-r3")).not.toBeInTheDocument();
    expect(screen.getByTestId("card-lock-r3")).toBeInTheDocument();

    // Even if a connection event reaches the graph, the frozen guard drops it.
    fireEvent.click(screen.getByTestId("stub-connect-req:r3__el:e1"));
    await waitFor(() => expect(allocate).not.toHaveBeenCalled());
  });
});

describe("AllocationGraph — keyboard path", () => {
  it("allocates through the 'Allokieren auf …' picker", async () => {
    const { allocate } = renderGraph();

    fireEvent.click(screen.getByTestId("graph-mode-edit"));
    fireEvent.click(screen.getByTestId("card-allocate-r1"));

    const search = await screen.findByTestId("graph-element-picker-search");
    fireEvent.change(search, { target: { value: "lenk" } });
    fireEvent.click(screen.getByTestId("graph-element-picker-option-e2"));

    await waitFor(() => expect(allocate).toHaveBeenCalledWith("r1", "e2"));
  });
});

describe("AllocationGraph — collapse and fields", () => {
  it("collapses descendants and expands them again", () => {
    const parent = row({ id: "r0", artifact_id: "art-r0", sort_key: "a" });
    const child = row({
      id: "r1",
      artifact_id: "art-r1",
      parent_id: "art-r0",
      sort_key: "a0",
    });
    renderGraph({ requirements: [parent, child] });

    expect(screen.getByTestId("req-card-r1")).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("card-collapse-r0"));

    expect(screen.queryByTestId("req-card-r1")).not.toBeInTheDocument();
    const toggle = screen.getByTestId("card-collapse-r0");
    expect(toggle).toHaveAttribute("aria-expanded", "false");

    fireEvent.click(toggle);
    expect(screen.getByTestId("req-card-r1")).toBeInTheDocument();
  });

  it("renders exactly the configured fields per card", () => {
    const cardFields = defaultCardFieldConfigMap();
    cardFields.requirement = {
      rows: 1,
      fields: [
        { key: "title", visible: true },
        { key: "owner", visible: true },
        { key: "type", visible: false },
        { key: "lock", visible: true },
      ],
    };
    const owned = row({
      id: "r9",
      sort_key: "z",
      title: "Mit Eigentümer",
      owner: "Alice",
      locked: { state: "Freigegeben" },
    });
    renderGraph({ requirements: [owned], cardFields });

    const card = screen.getByTestId("req-card-r9");
    expect(within(card).getByTestId("card-field-owner")).toHaveTextContent("Alice");
    expect(within(card).queryByTestId("card-field-type")).not.toBeInTheDocument();
    // Lock is a mandatory marker, not a hideable field row.
    expect(within(card).queryByTestId("card-field-lock")).not.toBeInTheDocument();
    expect(within(card).getByTestId("card-lock-r9")).toBeInTheDocument();
  });
});
