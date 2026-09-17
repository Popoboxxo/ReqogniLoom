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
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { ArchitectureDecomposePanel } from "../components/ArchitectureDecompose/ArchitectureDecomposePanel";
import type {
  CommitResult,
  DecomposeFinding,
  DecompositionDraft,
} from "../api/architectureDecompose";
import { UnprocessableEntityError } from "../api/errors";

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

vi.mock("../api/prompt-variables", () => ({
  promptVariablesApi: {
    list: vi.fn().mockResolvedValue({ variables: [], count: 0, workspace_id: null }),
    save: vi.fn(),
    clear: vi.fn(),
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
      maxBreadth: 5,
      maxDepth: 3,
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

  // -------------------------------------------------------------------
  // UI-40 (Systemaudit 2026-08-27 AP-5): breadth/depth client-side caps.
  // -------------------------------------------------------------------
  describe("breadth/depth input validation (UI-40)", () => {
    it("clamps a typed 0 up to the absolute minimum of 1 on blur", async () => {
      generate.mockResolvedValue(DRAFT);
      renderPanel();

      const breadthInput = screen.getByTestId("arch-decompose-breadth") as HTMLInputElement;
      // Let the async prompt-variable-catalog effect settle first — it also
      // calls setMaxBreadth/setMaxDepth on mount and would otherwise
      // overwrite a fireEvent.change fired before it resolves.
      await waitFor(() => expect(breadthInput.value).toBe("5"));
      fireEvent.change(breadthInput, { target: { value: "0" } });
      // Live-typing only enforces the upper bound (so clearing the field to
      // type a fresh multi-digit value stays usable) — the lower bound
      // finalizes on blur.
      expect(breadthInput.value).toBe("0");

      fireEvent.blur(breadthInput);
      expect(breadthInput.value).toBe("1");
    });

    it("resolves an unblurred 0 to the minimum before it ever reaches the backend", async () => {
      generate.mockResolvedValue(DRAFT);
      const user = userEvent.setup();
      renderPanel();

      const breadthInput = screen.getByTestId("arch-decompose-breadth") as HTMLInputElement;
      await waitFor(() => expect(breadthInput.value).toBe("5"));
      fireEvent.change(breadthInput, { target: { value: "0" } });
      // No blur here — clicking Generate must clamp defensively regardless
      // of whether the field ever lost focus first.
      await user.click(screen.getByTestId("arch-decompose-generate"));

      await waitFor(() =>
        expect(generate).toHaveBeenCalledWith(
          "ws-1",
          "el-1",
          expect.objectContaining({ maxBreadth: 1 })
        )
      );
    });

    it("clamps a typed value above the absolute ceiling down to the cap while typing", async () => {
      generate.mockResolvedValue(DRAFT);
      renderPanel();

      const breadthInput = screen.getByTestId("arch-decompose-breadth") as HTMLInputElement;
      await waitFor(() => expect(breadthInput.value).toBe("5"));
      fireEvent.change(breadthInput, { target: { value: "999" } });
      expect(breadthInput.value).toBe("10");

      const depthInput = screen.getByTestId("arch-decompose-depth") as HTMLInputElement;
      fireEvent.change(depthInput, { target: { value: "999" } });
      expect(depthInput.value).toBe("4");
    });

    it("never lets the input go to NaN when cleared, and clamps to the minimum on blur", async () => {
      generate.mockResolvedValue(DRAFT);
      renderPanel();

      const depthInput = screen.getByTestId("arch-decompose-depth") as HTMLInputElement;
      await waitFor(() => expect(depthInput.value).toBe("3"));
      fireEvent.change(depthInput, { target: { value: "" } });

      expect(depthInput.value).not.toBe("NaN");
      expect(depthInput.value).toBe("");

      fireEvent.blur(depthInput);
      expect(depthInput.value).toBe("1");
    });
  });

  // -------------------------------------------------------------------
  // UI-40: structured I1-I5/SE-Auditor findings on a rolled-back commit.
  // -------------------------------------------------------------------
  describe("structured invariant-violation findings on commit failure (UI-40)", () => {
    it("renders each finding as its own list item instead of one flat string", async () => {
      generate.mockResolvedValue(DRAFT);
      const findings: DecomposeFinding[] = [
        {
          rule_id: "ARCH-003",
          severity: "BLOCKER",
          message: "Element has no valid parent allocation.",
          artifact_ids: ["el-x"],
          scope: null,
          scope_artifact_id: null,
        },
        {
          rule_id: "TRACE-P4",
          severity: "BLOCKER",
          message: "Missing derives-from link to anchor requirement.",
          artifact_ids: ["el-y"],
          scope: null,
          scope_artifact_id: null,
        },
      ];
      commit.mockRejectedValue(
        new UnprocessableEntityError(
          "The generated decomposition failed SE-Auditor verification (ARCH-003, TRACE-P4).",
          findings as unknown as ReadonlyArray<Record<string, unknown>>
        )
      );
      const user = userEvent.setup();
      renderPanel();

      await user.click(screen.getByTestId("arch-decompose-generate"));
      await screen.findByTestId("arch-decompose-draft");
      await user.click(screen.getByTestId("arch-decompose-commit"));

      const findingsList = await screen.findByTestId("arch-decompose-error-findings");
      expect(findingsList).toBeInTheDocument();
      expect(screen.getByTestId("arch-decompose-error-finding-ARCH-003")).toHaveTextContent(
        "Element has no valid parent allocation."
      );
      expect(screen.getByTestId("arch-decompose-error-finding-TRACE-P4")).toHaveTextContent(
        "Missing derives-from link to anchor requirement."
      );
    });

    it("falls back to the flat message when no structured findings are present", async () => {
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
      expect(screen.queryByTestId("arch-decompose-error-findings")).not.toBeInTheDocument();
    });
  });
});
