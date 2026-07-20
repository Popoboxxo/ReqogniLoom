/**
 * ARCH-L1-001 ReactFrontend — ArchitectureDecomposePanel unit test.
 *
 * SysEng 2.0 N1 (architecture.decompose), UMSETZUNGSPLAN_SYSENG_2.0.md §3.1.
 *
 * Covers the Draft-Staging flow: generate populates a reviewable draft (nothing
 * committed yet), the mock-degraded banner shows, commit sends the draft back
 * and renders the result, and discard clears the draft.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { ArchitectureDecomposePanel } from "../components/ArchitectureDecompose/ArchitectureDecomposePanel";
import type {
  CommitResult,
  DecompositionDraft,
} from "../api/architectureDecompose";

// t() returns the key so assertions can rely on data-testid, not copy.
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock("../api/client", () => ({
  extractErrorMessage: (e: unknown) => (e instanceof Error ? e.message : "error"),
}));

const generate = vi.fn();
const commit = vi.fn();
vi.mock("../api/architectureDecompose", () => ({
  architectureDecomposeApi: {
    generate: (...args: unknown[]) => generate(...args),
    commit: (...args: unknown[]) => commit(...args),
  },
}));

const DRAFT: DecompositionDraft = {
  workspace_id: "ws-1",
  root_element_id: "el-1",
  parent_requirement_id: "req-anchor",
  provider: "mock",
  degraded: true,
  nodes: [
    {
      temp_id: "n1",
      parent_temp_id: null,
      title: "Child A",
      description: "desc A",
      element_type: "component",
      requirement: { title: "Req A", description: "", rationale: "" },
    },
    {
      temp_id: "n2",
      parent_temp_id: null,
      title: "Child B",
      description: "desc B",
      element_type: "component",
      requirement: { title: "Req B", description: "", rationale: "" },
    },
  ],
};

const COMMIT_RESULT: CommitResult = {
  committed: true,
  root_element_id: "el-1",
  created_element_ids: ["e1", "e2"],
  created_requirement_ids: ["r1", "r2"],
  created_link_ids: ["l1", "l2", "l3", "l4", "l5", "l6"],
  verified_rules: ["ARCH-003", "TRACE-P4", "TRACE-P5"],
  counts: { elements: 2, requirements: 2, links: 6 },
};

function renderPanel(onCommitted = vi.fn()) {
  return render(
    <ArchitectureDecomposePanel
      workspaceId="ws-1"
      element={{ id: "el-1", title: "Payment Subsystem" }}
      onCommitted={onCommitted}
    />
  );
}

describe("ArchitectureDecomposePanel", () => {
  beforeEach(() => {
    generate.mockReset();
    commit.mockReset();
  });

  it("stages a draft on generate without committing", async () => {
    generate.mockResolvedValue(DRAFT);
    const user = userEvent.setup();
    renderPanel();

    // Nothing staged initially.
    expect(screen.queryByTestId("arch-decompose-draft")).toBeNull();

    await user.click(screen.getByTestId("arch-decompose-generate"));

    await waitFor(() =>
      expect(screen.getByTestId("arch-decompose-draft")).toBeInTheDocument()
    );
    expect(generate).toHaveBeenCalledWith("ws-1", "el-1", {
      breadth: 2,
      depth: 1,
    });
    // Two node rows, mock-degraded banner, commit not yet called.
    expect(screen.getByTestId("arch-decompose-node-n1")).toBeInTheDocument();
    expect(screen.getByTestId("arch-decompose-node-n2")).toBeInTheDocument();
    expect(screen.getByTestId("arch-decompose-degraded")).toBeInTheDocument();
    expect(commit).not.toHaveBeenCalled();
  });

  it("commits the reviewed draft and renders the result", async () => {
    generate.mockResolvedValue(DRAFT);
    commit.mockResolvedValue(COMMIT_RESULT);
    const onCommitted = vi.fn();
    const user = userEvent.setup();
    renderPanel(onCommitted);

    await user.click(screen.getByTestId("arch-decompose-generate"));
    await screen.findByTestId("arch-decompose-draft");
    await user.click(screen.getByTestId("arch-decompose-commit"));

    await waitFor(() =>
      expect(screen.getByTestId("arch-decompose-result")).toBeInTheDocument()
    );
    expect(commit).toHaveBeenCalledWith("ws-1", DRAFT);
    expect(onCommitted).toHaveBeenCalledWith(COMMIT_RESULT);
    // Draft view is cleared after a successful commit.
    expect(screen.queryByTestId("arch-decompose-draft")).toBeNull();
  });

  it("shows an error and keeps the draft when commit fails", async () => {
    generate.mockResolvedValue(DRAFT);
    commit.mockRejectedValue(new Error("SE-Auditor verification failed"));
    const user = userEvent.setup();
    renderPanel();

    await user.click(screen.getByTestId("arch-decompose-generate"));
    await screen.findByTestId("arch-decompose-draft");
    await user.click(screen.getByTestId("arch-decompose-commit"));

    await waitFor(() =>
      expect(screen.getByTestId("arch-decompose-error")).toHaveTextContent(
        "SE-Auditor verification failed"
      )
    );
    // Draft stays so the user can retry / discard.
    expect(screen.getByTestId("arch-decompose-draft")).toBeInTheDocument();
  });

  it("discards a staged draft", async () => {
    generate.mockResolvedValue(DRAFT);
    const user = userEvent.setup();
    renderPanel();

    await user.click(screen.getByTestId("arch-decompose-generate"));
    await screen.findByTestId("arch-decompose-draft");
    await user.click(screen.getByTestId("arch-decompose-discard"));

    expect(screen.queryByTestId("arch-decompose-draft")).toBeNull();
  });
});
