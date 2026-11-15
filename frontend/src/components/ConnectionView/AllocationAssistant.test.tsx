/**
 * P3 Task 3.5 / P4.4 / V.4 — the allocation action bar.
 *
 * V.4 moved the selection out of the assistant into the page-level
 * `useAllocationSelection` hook. These tests therefore drive the selection
 * through that hook (the same one the tree checkboxes write to) and pin the
 * contracts that remain the bar's own:
 *
 * - there is **no** second requirement list in the bar;
 * - the four controls are always rendered; only "Allokieren auf …" waits for a
 *   selection, "Vorschläge" never does;
 * - a multi-selection is sent as exactly ONE atomic bulk call;
 * - a rejected bulk write is surfaced verbatim and explicitly states that
 *   nothing was written (all-or-nothing);
 * - suggestions only hit the write path after an explicit confirmation;
 * - frozen rows are not selectable, frozen elements stay valid targets.
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

/**
 * The page owns the selection; this harness wires the same hook the tree
 * renderer's checkboxes write to, so the tests never invent a second state.
 */
function Harness({
  requirements,
  elements,
  allocateBulk,
  suggestArchitecture,
  canEdit,
}: {
  requirements: AllocationRow[];
  elements: AllocationRow[];
  allocateBulk: (items: BulkAllocationItem[]) => Promise<{ allocated: [] }>;
  suggestArchitecture: (
    requirementId: string
  ) => Promise<SuggestArchitectureResponse>;
  canEdit: boolean;
}): JSX.Element {
  const selection = useAllocationSelection(requirements);
  return (
    <>
      <AllocationAssistant
        selection={selection}
        requirements={requirements}
        elements={elements}
        allocateBulk={allocateBulk}
        suggestArchitecture={suggestArchitecture}
        canEdit={canEdit}
      />
      <div>
        <button
          type="button"
          data-testid="harness-select-all"
          onClick={() => selection.selectAll()}
        >
          harness select all
        </button>
        {requirements.map((requirementRow) => (
          <button
            key={requirementRow.id}
            type="button"
            data-testid={`harness-toggle-${requirementRow.id}`}
            onClick={() => selection.toggle(requirementRow.id)}
          >
            harness toggle {requirementRow.id}
          </button>
        ))}
      </div>
    </>
  );
}

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
    <Harness
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

describe("AllocationAssistant — presentational bar (V.4)", () => {
  it("assistant_has_no_list", () => {
    renderAssistant();

    expect(screen.getByTestId("allocation-assistant")).toBeInTheDocument();
    // The second requirement list is gone: no rows, no row checkboxes.
    expect(screen.queryByTestId("assistant-row-r1")).not.toBeInTheDocument();
    expect(screen.queryByTestId("assistant-check-r1")).not.toBeInTheDocument();
    expect(screen.queryByTestId("assistant-list")).not.toBeInTheDocument();
  });

  it("action_bar_visible_without_selection", () => {
    renderAssistant();

    expect(screen.getByTestId("assistant-selection-count")).toHaveTextContent(
      "0 ausgewählt"
    );
    expect(screen.getByTestId("assistant-select-all")).toBeEnabled();
    // Only the write needs a selection; the ephemeral suggestion read does not.
    expect(screen.getByTestId("assistant-allocate")).toBeDisabled();
    expect(screen.getByTestId("assistant-suggest")).toBeEnabled();
  });

  it("select_all_counts_visible_unlocked_only", () => {
    const frozen = row({
      id: "r3",
      title: "Gesperrt",
      locked: "Freigegeben",
      sort_key: "c",
    });
    renderAssistant({ requirements: [R1, R2, frozen] });

    fireEvent.click(screen.getByTestId("harness-select-all"));

    // r3 is frozen and stays unselectable, so the visible selection is 2.
    expect(screen.getByTestId("assistant-selection-count")).toHaveTextContent(
      "2 ausgewählt"
    );
    expect(screen.getByTestId("assistant-select-all")).toHaveAttribute(
      "aria-pressed",
      "true"
    );
  });

  it("keeps the suggestion read available without a write role", () => {
    renderAssistant({ canEdit: false });

    expect(screen.getByTestId("assistant-allocate")).toBeDisabled();
    expect(screen.getByTestId("assistant-suggest")).toBeEnabled();
  });
});

describe("AllocationAssistant — multi-select bulk allocation", () => {
  it("sends the whole selection as exactly one atomic bulk call", async () => {
    const { allocateBulk } = renderAssistant();

    fireEvent.click(screen.getByTestId("harness-toggle-r1"));
    fireEvent.click(screen.getByTestId("harness-toggle-r2"));
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
    // A successful write consumes the page-level selection.
    expect(screen.getByTestId("assistant-selection-count")).toHaveTextContent(
      "0 ausgewählt"
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

    fireEvent.click(screen.getByTestId("harness-toggle-r1"));
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

    fireEvent.click(screen.getByTestId("harness-toggle-r1"));
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

  it("falls back to all unallocated requirements when nothing is selected", async () => {
    const suggestArchitecture = vi
      .fn<(requirementId: string) => Promise<SuggestArchitectureResponse>>()
      .mockResolvedValue({ suggested_arch_element_ids: ["e1"] });
    renderAssistant({ suggestArchitecture });

    fireEvent.click(screen.getByTestId("assistant-suggest"));

    await waitFor(() =>
      expect(suggestArchitecture).toHaveBeenCalledTimes(2)
    );
    expect(suggestArchitecture).toHaveBeenCalledWith("r1");
    expect(suggestArchitecture).toHaveBeenCalledWith("r2");
  });

  it("accepts a single candidate through the same bulk confirmation", async () => {
    const suggestArchitecture = vi
      .fn<(requirementId: string) => Promise<SuggestArchitectureResponse>>()
      .mockResolvedValue({ suggested_arch_element_ids: ["e2"] });
    const { allocateBulk } = renderAssistant({ suggestArchitecture });

    fireEvent.click(screen.getByTestId("harness-toggle-r1"));
    fireEvent.click(screen.getByTestId("assistant-suggest"));
    fireEvent.click(await screen.findByTestId("assistant-accept-r1-e2"));
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

    fireEvent.click(screen.getByTestId("harness-toggle-r1"));
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
