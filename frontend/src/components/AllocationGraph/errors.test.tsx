/**
 * P5 Task 5.4 — UI ↔ REST error parity.
 *
 * For the three rejected-write classes the plan names (frozen requirement,
 * allocation cycle, N:1 conflict) the graph must show the **same code and
 * message** the REST call returned. Each case is driven from one fixture that
 * models the REST envelope (`status` + `body`); the assertions compare the
 * rendered text against that very fixture, not against local copy.
 */

import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import de from "../../i18n/locales/de.json";

import type { AllocationRow } from "../../api/allocation-view";
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

interface RestFixture {
  status: number;
  body: {
    error: {
      code: string;
      message: string;
      details: unknown[];
    };
  };
}

function requirement(): AllocationRow {
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
  };
}

function element(): AllocationRow {
  return {
    ...requirement(),
    kind: "element",
    id: "e1",
    artifact_id: "art-e1",
    title: "Bremse",
    state: null,
    level: null,
    type: "component",
    category: null,
    allocation_intent: null,
  };
}

const FIXTURES: Array<{ name: string; fixture: RestFixture }> = [
  {
    name: "lock (409 WORKFLOW_FROZEN)",
    fixture: {
      status: 409,
      body: {
        error: {
          code: "WORKFLOW_FROZEN",
          message: "Requirement is frozen in state 'Freigegeben'",
          details: [],
        },
      },
    },
  },
  {
    name: "cycle (400 VALIDATION_ERROR)",
    fixture: {
      status: 400,
      body: {
        error: {
          code: "VALIDATION_ERROR",
          message: "Allocation to an ancestor would create a cycle (I4)",
          details: [],
        },
      },
    },
  },
  {
    name: "N:1 conflict (409 CONFLICT)",
    fixture: {
      status: 409,
      body: {
        error: {
          code: "CONFLICT",
          message: "Requirement already has an allocated-to link",
          details: [],
        },
      },
    },
  },
];

describe("AllocationGraph — error parity with the REST envelope", () => {
  it.each(FIXTURES)("shows the REST code and message verbatim: $name", async ({ fixture }) => {
    const allocate = vi
      .fn<(requirementId: string, elementId: string) => Promise<void>>()
      .mockRejectedValue(fixture.body);

    render(
      <AllocationGraph
        requirements={[requirement()]}
        elements={[element()]}
        allocate={allocate}
        canEdit
      />
    );

    fireEvent.click(screen.getByTestId("graph-mode-edit"));
    fireEvent.click(screen.getByTestId("stub-connect-req:r1__el:e1"));

    const banner = await screen.findByTestId("allocation-graph-error");
    expect(banner).toHaveAttribute("data-error-code", fixture.body.error.code);
    expect(screen.getByTestId("allocation-graph-error-code")).toHaveTextContent(
      fixture.body.error.code
    );
    expect(
      screen.getByTestId("allocation-graph-error-message")
    ).toHaveTextContent(fixture.body.error.message);
  });

  it("keeps the write untouched while the request is rejected", async () => {
    const fixture = FIXTURES[0].fixture;
    const allocate = vi
      .fn<(requirementId: string, elementId: string) => Promise<void>>()
      .mockRejectedValue(fixture.body);

    render(
      <AllocationGraph
        requirements={[requirement()]}
        elements={[element()]}
        allocate={allocate}
        canEdit
      />
    );

    fireEvent.click(screen.getByTestId("graph-mode-edit"));
    fireEvent.click(screen.getByTestId("stub-connect-req:r1__el:e1"));

    await waitFor(() => expect(allocate).toHaveBeenCalledTimes(1));
    await screen.findByTestId("allocation-graph-error");
  });
});
