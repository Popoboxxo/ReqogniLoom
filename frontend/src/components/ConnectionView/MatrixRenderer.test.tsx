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
});
