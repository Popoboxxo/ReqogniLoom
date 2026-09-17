/**
 * ProposalPreviewGraph — display-only xyflow preview of a multi-artifact
 * interview proposal (plan Task 10, docs/superpowers/plans/
 * 2026-08-24-multi-artifact-interview.md).
 *
 * Renders real React Flow under jsdom (same convention as
 * WorkflowEditorCanvas-a11y.test.tsx; ResizeObserver is polyfilled in
 * src/test/setup.ts).
 */
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { ProposalPreviewGraph } from "./ProposalPreviewGraph";
import type { ProposalItem } from "../../api/interviews";

const proposal: ProposalItem[] = [
  { type: "StakeholderNeed", title: "Need A", fields: { title: "Need A" }, links: [] },
  { type: "Requirement", title: "Req B", fields: { title: "Req B" }, links: [{ from: 1, to: 0, type: "derives-from" }] },
];

describe("ProposalPreviewGraph", () => {
  it("renders one node per proposal item", () => {
    render(<ProposalPreviewGraph proposal={proposal} />);
    expect(screen.getByTestId("proposal-preview-graph")).toBeInTheDocument();
    expect(screen.getByText("Need A")).toBeInTheDocument();
    expect(screen.getByText("Req B")).toBeInTheDocument();
  });

  it("renders a type badge per node", () => {
    render(<ProposalPreviewGraph proposal={proposal} />);
    expect(screen.getByText("StakeholderNeed")).toBeInTheDocument();
    expect(screen.getByText("Requirement")).toBeInTheDocument();
  });
});
