/**
 * P3 Task 3.5 / P4.4 — allocation assistant.
 *
 * The contracts under test:
 * - a multi-selection is sent as exactly ONE atomic bulk call;
 * - a rejected bulk write is surfaced verbatim and explicitly states that
 *   nothing was written (all-or-nothing);
 * - suggestions only hit the write path after an explicit confirmation;
 * - frozen rows are not selectable and expose the workflow state via tooltip,
 *   while frozen elements stay valid targets.
 */

import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import de from "../../i18n/locales/de.json";

import type {
  AllocationRow,
  BulkAllocationItem,
  SuggestArchitectureResponse,
} from "../../api/allocation-view";
import { AllocationAssistant } from "./AllocationAssistant";

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
    title: "Bremse",
    state: null,
    level: null,
    type: "component",
    category: null,
    allocation_intent: null,
    ...overrides,
  });
}

const R1 = row({ id: "r1", title: "Bremsdruck regeln" });
const R2 = row({ id: "r2", title: "Bremsweg messen", sort_key: "b" });
const E1 = element({ id: "e1", title: "Bremse" });
const E2 = element({ id: "e2", title: "Lenkung", sort_key: "b" });

function renderAssistant(options: {
  requirements?: AllocationRow[];
  elements?: AllocationRow[];
  allocateBulk?: ReturnType<typeof vi.fn>;
  suggestArchitecture?: ReturnType<typeof vi.fn>;
  canEdit?: boolean;
} = {}): {
  allocateBulk: ReturnType<typeof vi.fn>;
  suggestArchitecture: ReturnType<typeof vi.fn>;
} {
  const allocateBulk =
    options.allocateBulk ??
    vi.fn<(items: BulkAllocationItem[]) => Promise<{ allocated: [] }>>(
      async () => ({ allocated: [] })
    );
  const suggestArchitecture =
    options.suggestArchitecture ??
    vi.fn<(requirementId: string) => Promise<SuggestArchitectureResponse>>(
      async () => ({ suggested_arch_element_ids: [] })
    );

  render(
    <AllocationAssistant
      requirements={options.requirements ?? [R1, R2]}
      elements={options.elements ?? [E1, E2]}
      allocateBulk={
        allocateBulk as unknown as (
          items: BulkAllocationItem[]
        ) => Promise<{ allocated: [] }>
      }
      suggestArchitecture={
        suggestArchitecture as unknown as (
          requirementId: string
        ) => Promise<SuggestArchitectureResponse>
      }
      canEdit={options.canEdit ?? true}
    />
  );
  return { allocateBulk, suggestArchitecture };
}

describe("AllocationAssistant — multi-select bulk allocation", () => {
  it("sends the whole selection as exactly one atomic bulk call", async () => {
    const { allocateBulk } = renderAssistant();

    fireEvent.click(screen.getByTestId("assistant-check-r1"));
    fireEvent.click(screen.getByTestId("assistant-check-r2"));
    expect(screen.getByTestId("assistant-selection-count")).toHaveTextContent(
      "2 ausgewählt"
    );

    fireEvent.click(screen.getByTestId("assistant-allocate"));
    fireEvent.click(
      await screen.findByTestId("assistant-element-picker-option-e1")
    );

    await waitFor(() =>
      expect(allocateBulk).toHaveBeenCalledWith([
        { requirement_id: "r1", element_id: "e1" },
        { requirement_id: "r2", element_id: "e1" },
      ])
    );
    expect(allocateBulk).toHaveBeenCalledTimes(1);
    expect(await screen.findByTestId("assistant-notice")).toHaveTextContent(
      "2 Anforderung(en) auf „Bremse“ allokiert."
    );
  });

  it("reports a rejected batch verbatim and says nothing was written", async () => {
    const allocateBulk = vi
      .fn<(items: BulkAllocationItem[]) => Promise<{ allocated: [] }>>()
      .mockRejectedValue({
        error: {
          code: "WORKFLOW_FROZEN",
          message: "Requirement ist durch den Workflow gesperrt",
        },
      });
    renderAssistant({ allocateBulk });

    fireEvent.click(screen.getByTestId("assistant-check-r1"));
    fireEvent.click(screen.getByTestId("assistant-allocate"));
    fireEvent.click(
      await screen.findByTestId("assistant-element-picker-option-e1")
    );

    const alert = await screen.findByTestId("assistant-error");
    expect(alert).toHaveAttribute("data-error-code", "WORKFLOW_FROZEN");
    expect(
      within(alert).getByTestId("assistant-error-message")
    ).toHaveTextContent("Requirement ist durch den Workflow gesperrt");
    expect(alert).toHaveTextContent(
      "Es wurde nichts geschrieben — der Batch ist alles-oder-nichts."
    );
    expect(screen.queryByTestId("assistant-notice")).not.toBeInTheDocument();
    expect(allocateBulk).toHaveBeenCalledTimes(1);
  });
});

describe("AllocationAssistant — suggestions", () => {
  it("shows target + reason and writes only after explicit confirmation", async () => {
    const suggestArchitecture = vi
      .fn<(requirementId: string) => Promise<SuggestArchitectureResponse>>()
      .mockResolvedValue({
        suggested_elements: [
          { element_id: "e1", reason: "Bremst das Fahrzeug ab" },
        ],
      });
    const { allocateBulk } = renderAssistant({ suggestArchitecture });

    fireEvent.click(screen.getByTestId("assistant-check-r1"));
    fireEvent.click(screen.getByTestId("assistant-suggest"));

    const panel = await screen.findByTestId("assistant-suggestions");
    expect(panel).toHaveTextContent("Bremse");
    expect(panel).toHaveTextContent("Bremst das Fahrzeug ab");
    expect(allocateBulk).not.toHaveBeenCalled();

    fireEvent.click(screen.getByTestId("assistant-accept-all"));
    expect(
      await screen.findByTestId("assistant-suggestion-confirm")
    ).toBeInTheDocument();
    expect(allocateBulk).not.toHaveBeenCalled();

    fireEvent.click(screen.getByTestId("assistant-confirm-write"));
    await waitFor(() =>
      expect(allocateBulk).toHaveBeenCalledWith([
        { requirement_id: "r1", element_id: "e1" },
      ])
    );
    expect(allocateBulk).toHaveBeenCalledTimes(1);
  });

  it("accepts a single candidate through the same bulk confirmation", async () => {
    const suggestArchitecture = vi
      .fn<(requirementId: string) => Promise<SuggestArchitectureResponse>>()
      .mockResolvedValue({ suggested_arch_element_ids: ["e2"] });
    const { allocateBulk } = renderAssistant({ suggestArchitecture });

    fireEvent.click(screen.getByTestId("assistant-check-r1"));
    fireEvent.click(screen.getByTestId("assistant-suggest"));
    fireEvent.click(
      await screen.findByTestId("assistant-accept-r1-e2")
    );
    expect(allocateBulk).not.toHaveBeenCalled();

    fireEvent.click(screen.getByTestId("assistant-confirm-write"));
    await waitFor(() =>
      expect(allocateBulk).toHaveBeenCalledWith([
        { requirement_id: "r1", element_id: "e2" },
      ])
    );
  });
});

describe("AllocationAssistant — locks (P4.4)", () => {
  it("does not let a frozen requirement be selected and shows the state", () => {
    const frozen = row({
      id: "r3",
      title: "Gesperrt",
      locked: "Freigegeben",
      sort_key: "c",
    });
    renderAssistant({ requirements: [R1, frozen] });

    const checkbox = screen.getByTestId("assistant-check-r3");
    expect(checkbox).toBeDisabled();
    const lock = screen.getByTestId("assistant-lock-r3");
    expect(lock).toHaveAttribute("title", "Freigegeben");
    expect(lock).toHaveTextContent("Freigegeben");
    expect(screen.getByTestId("assistant-row-r3")).toHaveAttribute(
      "data-locked",
      "true"
    );
  });

  it("keeps a frozen element as a valid allocation target", async () => {
    const frozenElement = element({
      id: "e3",
      title: "Gesperrte Bremse",
      sort_key: "c",
      locked: "Freigegeben",
    });
    const { allocateBulk } = renderAssistant({
      elements: [E1, frozenElement],
    });

    fireEvent.click(screen.getByTestId("assistant-check-r1"));
    fireEvent.click(screen.getByTestId("assistant-allocate"));

    const option = await screen.findByTestId(
      "assistant-element-picker-option-e3"
    );
    expect(option).toBeEnabled();
    fireEvent.click(option);

    await waitFor(() =>
      expect(allocateBulk).toHaveBeenCalledWith([
        { requirement_id: "r1", element_id: "e3" },
      ])
    );
  });
});
