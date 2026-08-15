/**
 * Tests for AiPromptsSection (REQ-L2-PT-001, issue #119).
 *
 * Verifies the data wiring the old section lacked:
 * - every slot the backend reports gets an editor, including the four that
 *   were previously reachable only via MCP
 * - the workspace scope shows the effective value and saves an override
 * - resetting a workspace override deletes it (falls back to the global value)
 * - switching to the global scope edits the tenant-wide default instead
 */

import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AiPromptsSection } from "./AiPromptsSection";
import * as promptTemplatesModule from "../../api/prompt-templates";
import type { PromptSlotState } from "../../api/prompt-templates";

vi.mock("../../api/prompt-templates", async () => {
  const actual = await vi.importActual<typeof promptTemplatesModule>(
    "../../api/prompt-templates"
  );
  return {
    ...actual,
    promptTemplatesApi: {
      listSlots: vi.fn(),
      saveSlot: vi.fn(),
      clearSlot: vi.fn(),
    },
  };
});
vi.mock("react-i18next", () => {
  const t = (_key: string, fallback?: string): string => fallback ?? _key;
  return { useTranslation: () => ({ t }) };
});

const WORKSPACE_ID = "11111111-1111-1111-1111-111111111111";

function slot(name: string, overrides: Partial<PromptSlotState> = {}): PromptSlotState {
  return {
    name,
    factory_default: `factory ${name}`,
    global_content: null,
    global_version: null,
    workspace_content: null,
    workspace_version: null,
    has_workspace_override: false,
    effective_content: `factory ${name}`,
    effective_scope: "factory",
    ...overrides,
  };
}

const ALL_SLOT_NAMES = [
  "need_to_sysreq",
  "sysreq_to_arch_assign",
  "sysreq_decompose_next_level",
  "goal_aggregate",
  "testcase_derive",
  "architecture_to_risk",
  "workspace_to_glossary",
  "decision_to_adr",
];

const SLOTS: PromptSlotState[] = [
  slot("need_to_sysreq", {
    global_content: "global need",
    global_version: 2,
    workspace_content: "ws need",
    workspace_version: 1,
    has_workspace_override: true,
    effective_content: "ws need",
    effective_scope: "workspace",
  }),
  ...ALL_SLOT_NAMES.filter((n) => n !== "need_to_sysreq").map((n) => slot(n)),
];

const api = promptTemplatesModule.promptTemplatesApi;

describe("AiPromptsSection (issue #119)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.listSlots).mockResolvedValue({
      slots: SLOTS,
      count: SLOTS.length,
      workspace_id: WORKSPACE_ID,
    });
    vi.mocked(api.saveSlot).mockImplementation(async (name, content) =>
      slot(name, {
        workspace_content: content,
        workspace_version: 1,
        has_workspace_override: true,
        effective_content: content,
        effective_scope: "workspace",
      })
    );
    vi.mocked(api.clearSlot).mockImplementation(async (name) =>
      slot(name, {
        global_content: "global need",
        global_version: 2,
        effective_content: "global need",
        effective_scope: "global",
      })
    );
  });

  it("renders an editor for every slot the backend reports", async () => {
    render(<AiPromptsSection workspaceId={WORKSPACE_ID} />);
    await screen.findByTestId("prompt-need_to_sysreq-input");

    for (const name of ALL_SLOT_NAMES) {
      expect(screen.getByTestId(`prompt-${name}-input`)).toBeInTheDocument();
    }
  });

  it("loads the slots scoped to the active workspace", async () => {
    render(<AiPromptsSection workspaceId={WORKSPACE_ID} />);
    await waitFor(() =>
      expect(api.listSlots).toHaveBeenCalledWith(WORKSPACE_ID)
    );
  });

  it("shows the workspace override as the effective value and flags its origin", async () => {
    render(<AiPromptsSection workspaceId={WORKSPACE_ID} />);
    const input = await screen.findByTestId("prompt-need_to_sysreq-input");

    expect(input).toHaveValue("ws need");
    expect(screen.getByTestId("prompt-need_to_sysreq-origin")).toHaveTextContent(
      "Workspace-Override"
    );
  });

  it("falls back to the global default for slots without an override", async () => {
    render(<AiPromptsSection workspaceId={WORKSPACE_ID} />);
    const input = await screen.findByTestId("prompt-testcase_derive-input");

    expect(input).toHaveValue("factory testcase_derive");
    expect(screen.getByTestId("prompt-testcase_derive-origin")).toHaveTextContent(
      "Werkseinstellung"
    );
  });

  it("saves an edit as a workspace-scoped override", async () => {
    render(<AiPromptsSection workspaceId={WORKSPACE_ID} />);
    const input = await screen.findByTestId("prompt-testcase_derive-input");
    await userEvent.clear(input);
    await userEvent.type(input, "tuned");
    await userEvent.click(screen.getByTestId("prompt-testcase_derive-save"));

    await waitFor(() =>
      expect(api.saveSlot).toHaveBeenCalledWith(
        "testcase_derive",
        "tuned",
        WORKSPACE_ID
      )
    );
  });

  it("deletes the workspace override on reset", async () => {
    render(<AiPromptsSection workspaceId={WORKSPACE_ID} />);
    const resetBtn = await screen.findByTestId("prompt-need_to_sysreq-reset");
    await userEvent.click(resetBtn);

    await waitFor(() =>
      expect(api.clearSlot).toHaveBeenCalledWith("need_to_sysreq", WORKSPACE_ID)
    );
    await waitFor(() =>
      expect(screen.getByTestId("prompt-need_to_sysreq-input")).toHaveValue(
        "global need"
      )
    );
  });

  it("disables reset for a slot that has nothing to clear at this scope", async () => {
    render(<AiPromptsSection workspaceId={WORKSPACE_ID} />);
    await screen.findByTestId("prompt-testcase_derive-reset");

    expect(screen.getByTestId("prompt-testcase_derive-reset")).toBeDisabled();
    expect(screen.getByTestId("prompt-need_to_sysreq-reset")).toBeEnabled();
  });

  it("writes the tenant-global default when the scope is switched to global", async () => {
    render(<AiPromptsSection workspaceId={WORKSPACE_ID} />);
    await screen.findByTestId("prompt-scope-select");
    await userEvent.selectOptions(
      screen.getByTestId("prompt-scope-select"),
      "global"
    );

    // The global scope shows the tenant-wide row, not the workspace override.
    expect(screen.getByTestId("prompt-need_to_sysreq-input")).toHaveValue(
      "global need"
    );

    await userEvent.click(screen.getByTestId("prompt-need_to_sysreq-save"));
    await waitFor(() =>
      expect(api.saveSlot).toHaveBeenCalledWith(
        "need_to_sysreq",
        "global need",
        null
      )
    );
  });
});

describe("AiPromptsSection — interview slots (Spec 3 §7)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("generates a label for interview.protocol.<Type> slots without a hardcoded entry", async () => {
    vi.mocked(api.listSlots).mockResolvedValue({
      slots: [slot("interview.protocol.Requirement")],
      count: 1,
      workspace_id: WORKSPACE_ID,
    });

    render(<AiPromptsSection workspaceId={WORKSPACE_ID} />);

    expect(await screen.findByText(/Interview: Requirement/i)).toBeInTheDocument();
  });

  it("shows the interview-specific placeholder hint block distinct from the derivation one", async () => {
    vi.mocked(api.listSlots).mockResolvedValue({
      slots: [slot("interview.chat_turn")],
      count: 1,
      workspace_id: WORKSPACE_ID,
    });

    render(<AiPromptsSection workspaceId={WORKSPACE_ID} />);

    expect(await screen.findByText(/transcript_json/i)).toBeInTheDocument();
  });
});
