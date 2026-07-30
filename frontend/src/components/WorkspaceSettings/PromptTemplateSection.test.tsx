/**
 * Tests for PromptTemplateSection (REQ-L2-PT-001).
 *
 * Verifies:
 * - the four slot textareas render after the templates load (including the
 *   `goal_aggregate` slot, REQ-L2-TE-020)
 * - Save PATCHes all four slots
 * - a per-slot Reset button calls the reset endpoint with that slot
 */

import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { PromptTemplateSection } from "./PromptTemplateSection";
import * as promptTemplatesModule from "../../api/prompt-templates";

vi.mock("../../api/prompt-templates");
vi.mock("react-i18next", () => {
  const t = (_key: string, fallback?: string): string => fallback ?? _key;
  return { useTranslation: () => ({ t }) };
});

const DEFAULTS = {
  need_to_sysreq: "default need prompt",
  sysreq_to_arch_assign: "default assign prompt",
  sysreq_decompose_next_level: "default decompose prompt",
  goal_aggregate: "default goal aggregate prompt",
};

const TEMPLATE = {
  need_to_sysreq: "current need prompt",
  sysreq_to_arch_assign: "current assign prompt",
  sysreq_decompose_next_level: "current decompose prompt",
  goal_aggregate: "current goal aggregate prompt",
  defaults_dict: DEFAULTS,
};

describe("PromptTemplateSection (REQ-L2-PT-001)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(promptTemplatesModule.promptTemplatesApi.get).mockResolvedValue(
      TEMPLATE
    );
    vi.mocked(promptTemplatesModule.promptTemplatesApi.update).mockResolvedValue(
      TEMPLATE
    );
    vi.mocked(promptTemplatesModule.promptTemplatesApi.reset).mockResolvedValue({
      ...TEMPLATE,
      need_to_sysreq: DEFAULTS.need_to_sysreq,
    });
    (
      promptTemplatesModule as { PROMPT_SLOTS: readonly string[] }
    ).PROMPT_SLOTS = [
      "need_to_sysreq",
      "sysreq_to_arch_assign",
      "sysreq_decompose_next_level",
      "goal_aggregate",
    ];
  });

  it("renders the four slot textareas once loaded", async () => {
    render(<PromptTemplateSection />);
    await waitFor(() =>
      expect(screen.getByTestId("prompt-template-save")).toBeInTheDocument()
    );
    expect(screen.getByTestId("prompt-need_to_sysreq-input")).toBeInTheDocument();
    expect(
      screen.getByTestId("prompt-sysreq_to_arch_assign-input")
    ).toBeInTheDocument();
    expect(
      screen.getByTestId("prompt-sysreq_decompose_next_level-input")
    ).toBeInTheDocument();
    expect(
      screen.getByTestId("prompt-goal_aggregate-input")
    ).toBeInTheDocument();
  });

  it("renders the goal_aggregate slot with its human-readable label", async () => {
    render(<PromptTemplateSection />);
    await waitFor(() =>
      expect(screen.getByTestId("prompt-template-save")).toBeInTheDocument()
    );
    expect(screen.getByLabelText(/Ziel-Aggregation/i)).toBeInTheDocument();
  });

  it("calls PATCH (update) with all four slots on Save", async () => {
    render(<PromptTemplateSection />);
    const saveBtn = await screen.findByTestId("prompt-template-save");
    await userEvent.click(saveBtn);

    await waitFor(() =>
      expect(
        promptTemplatesModule.promptTemplatesApi.update
      ).toHaveBeenCalled()
    );
    const payload = vi.mocked(promptTemplatesModule.promptTemplatesApi.update)
      .mock.calls[0][0];
    expect(payload).toMatchObject({
      need_to_sysreq: "current need prompt",
      sysreq_to_arch_assign: "current assign prompt",
      sysreq_decompose_next_level: "current decompose prompt",
      goal_aggregate: "current goal aggregate prompt",
    });
  });

  it("calls the reset endpoint with the slot when Reset is clicked", async () => {
    render(<PromptTemplateSection />);
    const resetBtn = await screen.findByTestId("prompt-need_to_sysreq-reset");
    await userEvent.click(resetBtn);

    await waitFor(() =>
      expect(promptTemplatesModule.promptTemplatesApi.reset).toHaveBeenCalledWith(
        "need_to_sysreq"
      )
    );
  });
});
