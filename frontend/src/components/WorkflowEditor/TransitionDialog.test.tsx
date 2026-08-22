/**
 * TransitionDialog — a11y regression test (WCAG 4.1.2/3.3.2).
 *
 * GESAMTTEST_BERICHT_2026-08-21.md §5 finding 18 / §10.1: the "Von" (from)
 * field used a bare <span> as its visual label instead of a <label
 * htmlFor="...">, so the read-only source-state input had no accessible
 * name. Verifies the field is now queryable via its accessible name — a
 * passing getByLabelText query is direct proof the label association works.
 */

import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { TransitionDialog } from "./TransitionDialog";
import type { WorkflowState } from "../../api/workflows";

vi.mock("react-i18next", () => {
  const t = (_key: string, fallback?: string): string => fallback ?? _key;
  return {
    useTranslation: () => ({ t }),
    Trans: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
  };
});

const STATES: WorkflowState[] = [
  { id: "draft", name: "Draft", type: "initial", outgoingCount: 1, incomingCount: 0, isInitial: true },
  { id: "review", name: "Review", type: "active", outgoingCount: 0, incomingCount: 1, isInitial: false },
];

describe("TransitionDialog — a11y (WCAG 4.1.2/3.3.2)", () => {
  it("exposes the 'from' field via its accessible name", () => {
    render(
      <TransitionDialog
        mode="add"
        states={STATES}
        fromState="draft"
        onSubmit={vi.fn()}
        onClose={vi.fn()}
      />
    );

    const fromField = screen.getByLabelText("workflow.transitionDialog.from");
    expect(fromField).toBe(screen.getByTestId("workflow-transition-from"));
    expect(fromField).toHaveValue("draft");
  });
});
