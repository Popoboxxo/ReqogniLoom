/**
 * P3 Task 3.3 — tree renderer.
 *
 * Covers grouping/counts, drag -> atomic bulk allocate, the keyboard element
 * picker, frozen requirements and verbatim backend errors.
 */

import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import de from "../../i18n/locales/de.json";

import type { AllocationRow } from "../../api/allocation-view";
import { TreeRenderer } from "./TreeRenderer";

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

function row(overrides: Partial<AllocationRow>): AllocationRow {
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
  return row({
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

const ELEMENT_A = element({ id: "e1", artifact_id: "art-e1", title: "Bremse" });
const ELEMENT_B = element({
  id: "e2",
  artifact_id: "art-e2",
  title: "Lenkung",
  sort_key: "b",
});

const R1 = row({
  id: "r1",
  title: "Bremsdruck regeln",
  allocated_to: "e1",
  allocation_trace_link_id: "link-1",
  element_id: "e1",
  sort_key: "a",
});
const R2 = row({
  id: "r2",
  title: "Bremsweg messen",
  allocated_to: "e1",
  allocation_trace_link_id: "link-2",
  element_id: "e1",
  sort_key: "b",
});
const R3 = row({ id: "r3", title: "Offene Anforderung", sort_key: "c" });

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

function renderTree(overrides: {
  requirements?: AllocationRow[];
  elements?: AllocationRow[];
  allocate?: (requirementId: string, elementId: string) => Promise<void>;
  deallocate?: (traceLinkId: string) => Promise<void>;
} = {}): {
  allocate: ReturnType<typeof vi.fn>;
  deallocate: ReturnType<typeof vi.fn>;
} {
  const allocate =
    overrides.allocate ?? vi.fn<(requirementId: string, elementId: string) => Promise<void>>();
  const deallocate =
    overrides.deallocate ?? vi.fn<(traceLinkId: string) => Promise<void>>();
  render(
    <TreeRenderer
      requirements={overrides.requirements ?? [R1, R2, R3]}
      elements={overrides.elements ?? [ELEMENT_A, ELEMENT_B]}
      allocate={allocate as (requirementId: string, elementId: string) => Promise<void>}
      deallocate={deallocate as (traceLinkId: string) => Promise<void>}
    />
  );
  return { allocate, deallocate };
}

describe("TreeRenderer — grouping and counts", () => {
  it("groups requirements under their element and counts them", () => {
    renderTree();

    const elementA = screen.getByTestId("element-node-e1");
    expect(elementA).toContainElement(screen.getByTestId("req-row-r1"));
    expect(elementA).toContainElement(screen.getByTestId("req-row-r2"));
    expect(screen.getByTestId("element-count-e1")).toHaveTextContent("2");
    expect(screen.getByTestId("element-count-e2")).toHaveTextContent("0");
  });

  it("renders the unallocated block with its own count", () => {
    renderTree();
    const block = screen.getByTestId("unallocated-block");
    expect(block).toContainElement(screen.getByTestId("req-row-r3"));
    expect(screen.getByTestId("unallocated-count")).toHaveTextContent("1");
  });
});

describe("TreeRenderer — drag and drop", () => {
  it("drops a requirement onto an element and calls the atomic bulk allocate", async () => {
    const { allocate } = renderTree();
    const dataTransfer = fakeDataTransfer();

    fireEvent.dragStart(screen.getByTestId("req-row-r3"), { dataTransfer });
    fireEvent.drop(screen.getByTestId("element-node-e2"), { dataTransfer });

    await waitFor(() =>
      expect(allocate).toHaveBeenCalledWith("r3", "e2")
    );
  });

  it("drops an allocated requirement onto 'Nicht allokiert' and deallocates by link id", async () => {
    const { deallocate } = renderTree();
    const dataTransfer = fakeDataTransfer();

    fireEvent.dragStart(screen.getByTestId("req-row-r1"), { dataTransfer });
    fireEvent.drop(screen.getByTestId("unallocated-block"), { dataTransfer });

    await waitFor(() =>
      expect(deallocate).toHaveBeenCalledWith("link-1")
    );
  });

  it("does not make a frozen requirement draggable", () => {
    const frozen = row({
      id: "r4",
      title: "Gesperrt",
      locked: { state: "Freigegeben" },
      sort_key: "d",
    });
    renderTree({ requirements: [frozen] });

    const req = screen.getByTestId("req-row-r4");
    expect(req).toHaveAttribute("draggable", "false");
    expect(req).toHaveAttribute("data-locked", "true");
    expect(screen.getByTestId("allocate-open-r4")).toBeDisabled();
  });

  it("shows a lock icon with the freeze state as its tooltip", () => {
    const frozen = row({
      id: "r5",
      title: "Freigegeben",
      locked: "Freigegeben",
      sort_key: "e",
    });
    renderTree({ requirements: [frozen] });

    const icon = screen.getByTestId("req-locked-r5");
    expect(icon).toHaveAttribute("title", "Freigegeben");
    expect(icon).toHaveTextContent("Freigegeben");
  });

  it("shows the backend error verbatim when the allocation is rejected", async () => {
    const allocate = vi
      .fn<(requirementId: string, elementId: string) => Promise<void>>()
      .mockRejectedValue({
        error: { code: "CONFLICT", message: "Requirement ist gesperrt" },
      });
    renderTree({ allocate });

    const dataTransfer = fakeDataTransfer();
    fireEvent.dragStart(screen.getByTestId("req-row-r3"), { dataTransfer });
    fireEvent.drop(screen.getByTestId("element-node-e2"), { dataTransfer });

    await waitFor(() =>
      expect(screen.getByTestId("allocation-error")).toHaveTextContent(
        "Requirement ist gesperrt"
      )
    );
    expect(screen.getByTestId("allocation-error")).toHaveAttribute(
      "data-error-code",
      "CONFLICT"
    );
  });

  it("shows the 409 code and reason when the backend rejects a frozen write", async () => {
    const allocate = vi
      .fn<(requirementId: string, elementId: string) => Promise<void>>()
      .mockRejectedValue({
        error: {
          code: "WORKFLOW_FROZEN",
          message: "Requirement ist durch den Workflow gesperrt",
        },
        status: 409,
      });
    renderTree({ allocate });

    const dataTransfer = fakeDataTransfer();
    fireEvent.dragStart(screen.getByTestId("req-row-r3"), { dataTransfer });
    fireEvent.drop(screen.getByTestId("element-node-e2"), { dataTransfer });

    const alert = await screen.findByTestId("allocation-error");
    expect(alert).toHaveAttribute("data-error-code", "WORKFLOW_FROZEN");
    expect(alert).toHaveTextContent("Requirement ist durch den Workflow gesperrt");
  });
});

describe("TreeRenderer — keyboard picker", () => {
  it("opens the element search and allocates through it", async () => {
    const { allocate } = renderTree();

    fireEvent.click(screen.getByTestId("allocate-open-r3"));
    const search = await screen.findByTestId("element-picker-search");
    fireEvent.change(search, { target: { value: "lenk" } });
    fireEvent.click(screen.getByTestId("element-picker-option-e2"));

    await waitFor(() =>
      expect(allocate).toHaveBeenCalledWith("r3", "e2")
    );
  });
});
