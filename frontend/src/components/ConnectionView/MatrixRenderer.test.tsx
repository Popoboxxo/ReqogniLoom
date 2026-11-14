/**
 * P3 Task 3.4 — matrix renderer (C).
 *
 * One dot per requirement row at most, footer sums per column, and an
 * explicit page indicator with working paging.
 */

import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import de from "../../i18n/locales/de.json";

import type { AllocationRow } from "../../api/allocation-view";
import { MatrixRenderer } from "./MatrixRenderer";

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

function element(id: string, title: string): AllocationRow {
  return requirement({
    kind: "element",
    id,
    artifact_id: `art-${id}`,
    title,
    state: null,
    level: null,
    type: "component",
    category: null,
    allocation_intent: null,
  });
}

const ELEMENTS = [element("e1", "Bremse"), element("e2", "Lenkung")];

const ROWS = [
  requirement({
    id: "r1",
    title: "Bremsen",
    allocated_to: "e1",
    allocation_trace_link_id: "link-1",
  }),
  requirement({
    id: "r2",
    title: "Lenken",
    allocated_to: "e2",
    allocation_trace_link_id: "link-2",
    sort_key: "b",
  }),
  requirement({ id: "r3", title: "Offen", sort_key: "c" }),
];

describe("MatrixRenderer", () => {
  it("shows at most one dot per requirement row", () => {
    render(
      <MatrixRenderer
        requirements={ROWS}
        elements={ELEMENTS}
        page={1}
        pageSize={50}
        onPageChange={vi.fn()}
      />
    );

    const row = screen.getByTestId("matrix-row-r1");
    expect(within(row).getAllByTestId(/matrix-dot-/)).toHaveLength(1);
    expect(within(row).getByTestId("matrix-dot-r1-e1")).toBeInTheDocument();
    expect(
      within(screen.getByTestId("matrix-row-r3")).queryAllByTestId(/matrix-dot-/)
    ).toHaveLength(0);
  });

  it("matches a real read row by element_id, not by the artifact id", () => {
    const real = requirement({
      id: "r9",
      title: "Echte Zeile",
      // The committed read object sends the element's Artifact id in
      // `allocated_to` and its entity id in `element_id`.
      allocated_to: "art-e1",
      element_id: "e1",
      allocation_trace_link_id: "link-9",
      sort_key: "z",
    });
    render(
      <MatrixRenderer
        requirements={[real]}
        elements={ELEMENTS}
        page={1}
        pageSize={50}
        onPageChange={vi.fn()}
      />
    );

    expect(screen.getByTestId("matrix-dot-r9-e1")).toBeInTheDocument();
    expect(screen.getByTestId("matrix-sum-e1")).toHaveTextContent("1");
  });

  it("sums the visible window per column and in total", () => {
    render(
      <MatrixRenderer
        requirements={ROWS}
        elements={ELEMENTS}
        page={1}
        pageSize={50}
        onPageChange={vi.fn()}
      />
    );

    expect(screen.getByTestId("matrix-sum-e1")).toHaveTextContent("1");
    expect(screen.getByTestId("matrix-sum-e2")).toHaveTextContent("1");
    expect(screen.getByTestId("matrix-sum-total")).toHaveTextContent("2");
  });

  it("renders an explicit page indicator and pages the window", () => {
    const onPageChange = vi.fn();
    render(
      <MatrixRenderer
        requirements={ROWS}
        elements={ELEMENTS}
        page={1}
        pageSize={2}
        onPageChange={onPageChange}
      />
    );

    expect(screen.getByTestId("matrix-page-indicator")).toHaveTextContent(
      "Seite 1 von 2"
    );
    // Window of two rows: r1 and r2; r3 is on the next page.
    expect(screen.getByTestId("matrix-row-r1")).toBeInTheDocument();
    expect(screen.queryByTestId("matrix-row-r3")).not.toBeInTheDocument();

    fireEvent.click(screen.getByTestId("matrix-next"));
    expect(onPageChange).toHaveBeenCalledWith(2);
  });

  it("marks a frozen row with a lock icon and a state tooltip (P4.4)", () => {
    const locked = requirement({
      id: "r4",
      title: "Gesperrt",
      locked: "Freigegeben",
      sort_key: "d",
    });
    render(
      <MatrixRenderer
        requirements={[...ROWS, locked]}
        elements={ELEMENTS}
        page={1}
        pageSize={50}
        onPageChange={vi.fn()}
      />
    );

    const icon = screen.getByTestId("matrix-lock-r4");
    expect(icon).toHaveAttribute("title", "Freigegeben");
    expect(screen.getByTestId("matrix-row-r4")).toHaveAttribute(
      "data-locked",
      "true"
    );
    expect(screen.getByTestId("matrix-row-r1")).toHaveAttribute(
      "data-locked",
      "false"
    );
  });

  it("shows the second page and disables 'next' on the last page", () => {
    render(
      <MatrixRenderer
        requirements={ROWS}
        elements={ELEMENTS}
        page={2}
        pageSize={2}
        onPageChange={vi.fn()}
      />
    );

    expect(screen.getByTestId("matrix-page-indicator")).toHaveTextContent(
      "Seite 2 von 2"
    );
    expect(screen.getByTestId("matrix-row-r3")).toBeInTheDocument();
    expect(screen.getByTestId("matrix-next")).toBeDisabled();
  });

  // V6 (triage 2026-11-10 §V6): the level was readable in the requirement
  // list only. The read object already carries `level`/`tier_name`, so the
  // matrix row shows the same neutral badge.
  it("[V6] renders the level badge in the row header", () => {
    render(
      <MatrixRenderer
        requirements={[requirement({ id: "r5", title: "Level row", level: 3, tier_name: "Subsystem" })]}
        elements={ELEMENTS}
        page={1}
        pageSize={10}
        onPageChange={vi.fn()}
      />
    );

    const row = screen.getByTestId("matrix-row-r5");
    const badge = within(row).getByTestId("matrix-level-r5");
    expect(badge).toHaveTextContent("L3");
    expect(badge).toHaveAttribute("title", "Subsystem");
  });

  it("[V6] renders no level badge for a row without a level", () => {
    render(
      <MatrixRenderer
        requirements={[requirement({ id: "r6", level: null, tier_name: null })]}
        elements={ELEMENTS}
        page={1}
        pageSize={10}
        onPageChange={vi.fn()}
      />
    );

    expect(
      within(screen.getByTestId("matrix-row-r6")).queryByTestId("matrix-level-r6")
    ).not.toBeInTheDocument();
  });
});
