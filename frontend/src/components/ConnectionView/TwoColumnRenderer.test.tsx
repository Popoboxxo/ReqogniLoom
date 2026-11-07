/**
 * P3 Task 3.4 — two-column renderer (A).
 *
 * Selection highlights the counterpart on the other side; dragging from the
 * requirement column onto an element allocates.
 */

import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import de from "../../i18n/locales/de.json";

import type { AllocationRow } from "../../api/allocation-view";
import { TwoColumnRenderer } from "./TwoColumnRenderer";

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

const R1 = requirement({
  id: "r1",
  title: "Bremsen",
  allocated_to: "e1",
  allocation_trace_link_id: "link-1",
});
const R2 = requirement({
  id: "r2",
  title: "Lenken",
  allocated_to: "e2",
  allocation_trace_link_id: "link-2",
  sort_key: "b",
});

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

function renderTwoColumn(
  allocate = vi.fn<(requirementId: string, elementId: string) => Promise<void>>()
): void {
  render(
    <TwoColumnRenderer
      requirements={[R1, R2]}
      elements={[element("e1", "Bremse"), element("e2", "Lenkung")]}
      allocate={allocate as (requirementId: string, elementId: string) => Promise<void>}
      deallocate={vi.fn()}
    />
  );
}

describe("TwoColumnRenderer", () => {
  it("highlights the allocated element when a requirement is selected", () => {
    renderTwoColumn();
    fireEvent.click(screen.getByTestId("twocol-req-select-r1"));

    expect(screen.getByTestId("twocol-element-e1")).toHaveAttribute(
      "data-highlighted",
      "true"
    );
    expect(screen.getByTestId("twocol-element-e2")).toHaveAttribute(
      "data-highlighted",
      "false"
    );
  });

  it("highlights every allocated requirement when an element is selected", () => {
    renderTwoColumn();
    fireEvent.click(screen.getByTestId("twocol-element-select-e2"));

    expect(screen.getByTestId("twocol-req-r2")).toHaveAttribute(
      "data-highlighted",
      "true"
    );
    expect(screen.getByTestId("twocol-req-r1")).toHaveAttribute(
      "data-highlighted",
      "false"
    );
  });

  it("allocates when a requirement is dragged onto an element", async () => {
    const allocate = vi.fn<
      (requirementId: string, elementId: string) => Promise<void>
    >();
    renderTwoColumn(allocate);
    const dataTransfer = fakeDataTransfer();

    fireEvent.dragStart(screen.getByTestId("twocol-req-r1"), { dataTransfer });
    fireEvent.drop(screen.getByTestId("twocol-element-e2"), { dataTransfer });

    await waitFor(() =>
      expect(allocate).toHaveBeenCalledWith("r1", "e2")
    );
  });
});
