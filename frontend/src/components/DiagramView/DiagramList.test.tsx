/**
 * DiagramList — type grouping (Phase 6 / decision E2-D1).
 *
 * req_id: REQ-L2-DS-001, REQ-002
 *
 * Guards the shape the decision actually picked: a FLAT list with
 * `diagram_type` section headings (D1), explicitly not a tree (D2 was
 * rejected because a synthetic type level invents a hierarchy the data model
 * does not have). "Flat" is asserted structurally — every row stays a sibling
 * under its section and there is no expand/collapse control — so a later
 * migration onto WorkspaceTree cannot pass silently.
 */
import { describe, it, expect, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import type { Diagram } from "../../types";

vi.mock("react-i18next", () => {
  const t = (
    key: string,
    fallbackOrOptions?: string | Record<string, unknown>,
  ): string => (typeof fallbackOrOptions === "string" ? fallbackOrOptions : key);
  return { useTranslation: () => ({ t }) };
});

import { DiagramList } from "./DiagramList";

function makeDiagram(over: Partial<Diagram> & { id: string }): Diagram {
  return {
    name: `Diagram ${over.id}`,
    diagram_type: "block",
    description: "",
    current_version: null,
    created_at: "2026-02-01T10:00:00Z",
    version_count: 1,
    ...over,
  } as Diagram;
}

const ITEMS: Diagram[] = [
  makeDiagram({ id: "d-flow-1", name: "Checkout Flow", diagram_type: "flow" }),
  makeDiagram({ id: "d-block-1", name: "Power Block", diagram_type: "block" }),
  makeDiagram({ id: "d-flow-2", name: "Auth Flow", diagram_type: "flow" }),
  makeDiagram({ id: "d-ctx-1", name: "System Context", diagram_type: "context" }),
];

const renderList = (items: Diagram[] = ITEMS) =>
  render(
    <DiagramList
      items={items}
      onSelect={vi.fn()}
      onCreateNew={vi.fn()}
      onDelete={vi.fn()}
    />,
  );

describe("DiagramList type grouping (E2-D1)", () => {
  it("renders one section per present diagram_type, none for absent types", () => {
    renderList();

    expect(screen.getByTestId("diagram-group-block")).toBeInTheDocument();
    expect(screen.getByTestId("diagram-group-flow")).toBeInTheDocument();
    expect(screen.getByTestId("diagram-group-context")).toBeInTheDocument();
    // No diagram of these types is present -> no empty section.
    expect(screen.queryByTestId("diagram-group-canvas")).not.toBeInTheDocument();
    expect(screen.queryByTestId("diagram-group-mermaid")).not.toBeInTheDocument();
  });

  it("puts every diagram in the section matching its type, with a count", () => {
    renderList();

    const flow = screen.getByTestId("diagram-group-flow");
    expect(within(flow).getByTestId("diagram-item-d-flow-1")).toBeInTheDocument();
    expect(within(flow).getByTestId("diagram-item-d-flow-2")).toBeInTheDocument();
    expect(within(flow).queryByTestId("diagram-item-d-block-1")).not.toBeInTheDocument();
    expect(within(flow).getByRole("heading", { level: 2 })).toHaveTextContent("2");
  });

  it("orders sections by the canonical DIAGRAM_TYPES order, not by first appearance", () => {
    // "flow" appears first in the input, but "block" precedes it canonically.
    renderList();

    const sections = screen
      .getByTestId("diagrams-list")
      .querySelectorAll("[data-testid^='diagram-group-']");
    expect([...sections].map((s) => s.getAttribute("data-testid"))).toEqual([
      "diagram-group-block",
      "diagram-group-flow",
      "diagram-group-context",
    ]);
  });

  it("keeps rows with an unknown or missing type reachable in a trailing section", () => {
    renderList([
      makeDiagram({ id: "d-ok", diagram_type: "block" }),
      // Deliberately off-contract: older records / fixtures do produce these,
      // and dropping the row would hide a diagram the user owns.
      makeDiagram({ id: "d-weird", diagram_type: "sequence" as Diagram["diagram_type"] }),
      makeDiagram({ id: "d-none", diagram_type: undefined as unknown as Diagram["diagram_type"] }),
    ]);

    expect(screen.getByTestId("diagram-item-d-weird")).toBeInTheDocument();
    expect(screen.getByTestId("diagram-item-d-none")).toBeInTheDocument();
    expect(screen.getByTestId("diagram-group-__ungrouped__")).toBeInTheDocument();
  });

  it("stays a flat list: no expand/collapse control and no nested rows (D2 rejected)", () => {
    renderList();

    // A tree would need per-node disclosure controls; a grouped flat list
    // must not have any.
    expect(screen.queryByRole("button", { expanded: true })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { expanded: false })).not.toBeInTheDocument();
    expect(screen.queryByRole("treeitem")).not.toBeInTheDocument();

    // Rows are direct siblings inside their section, never nested in each other.
    const flowRow = screen.getByTestId("diagram-item-d-flow-1");
    expect(
      flowRow.closest("[data-testid='diagram-item-d-flow-2']"),
    ).toBeNull();
  });
});
