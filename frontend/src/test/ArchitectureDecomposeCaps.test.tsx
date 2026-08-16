/**
 * ARCH-L1-001 ReactFrontend — decompose caps come from the catalog (spec §4).
 */
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { ArchitectureDecomposePanel } from "../components/ArchitectureDecompose/ArchitectureDecomposePanel";
import type { PromptVariableState } from "../api/prompt-variables";

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

const listVariables = vi.fn();
vi.mock("../api/prompt-variables", () => ({
  promptVariablesApi: {
    list: (...args: unknown[]) => listVariables(...args),
    save: vi.fn(),
    clear: vi.fn(),
  },
}));

function capVariable(name: string, value: number): PromptVariableState {
  return {
    name,
    kind: "config",
    var_type: "int",
    description: `desc ${name}`,
    factory_default: value,
    global_value: null,
    global_version: null,
    workspace_value: null,
    workspace_version: null,
    has_workspace_override: false,
    effective_value: value,
    effective_scope: "factory",
    is_editable: true,
  };
}

function renderPanel() {
  return render(
    <ArchitectureDecomposePanel
      workspaceId="ws-1"
      element={{ id: "el-1", title: "Payment Subsystem" }}
    />
  );
}

describe("ArchitectureDecomposePanel caps (spec §4)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    listVariables.mockResolvedValue({
      variables: [capVariable("max_breadth", 5), capVariable("max_depth", 3)],
      count: 2,
      workspace_id: "ws-1",
    });
    generate.mockResolvedValue({
      workspace_id: "ws-1",
      root_element_id: "el-1",
      parent_requirement_id: "req-1",
      provider: "mock",
      degraded: false,
      nodes: [],
    });
  });

  it("seeds the inputs from the catalog instead of hard-coded 2/1", async () => {
    renderPanel();

    await waitFor(() =>
      expect(
        (screen.getByTestId("arch-decompose-breadth") as HTMLInputElement).value
      ).toBe("5")
    );
    expect(
      (screen.getByTestId("arch-decompose-depth") as HTMLInputElement).value
    ).toBe("3");
  });

  it("resolves the caps for the panel's workspace", async () => {
    renderPanel();

    await waitFor(() => expect(listVariables).toHaveBeenCalledWith("ws-1"));
  });

  it("sends the renamed cap parameters", async () => {
    const user = userEvent.setup();
    renderPanel();
    await waitFor(() =>
      expect(
        (screen.getByTestId("arch-decompose-breadth") as HTMLInputElement).value
      ).toBe("5")
    );

    await user.click(screen.getByTestId("arch-decompose-generate"));

    await waitFor(() =>
      expect(generate).toHaveBeenCalledWith("ws-1", "el-1", {
        maxBreadth: 5,
        maxDepth: 3,
      })
    );
  });

  it("explains that the numbers are upper bounds, not targets", async () => {
    renderPanel();

    expect(
      (await screen.findByTestId("arch-decompose-caps-hint")).textContent
    ).toContain("archDecompose.capsHint");
  });

  it("falls back to 5/3 when the catalog cannot be read", async () => {
    listVariables.mockRejectedValue(new Error("nope"));
    renderPanel();

    await waitFor(() =>
      expect(
        (screen.getByTestId("arch-decompose-breadth") as HTMLInputElement).value
      ).toBe("5")
    );
    expect(
      (screen.getByTestId("arch-decompose-depth") as HTMLInputElement).value
    ).toBe("3");
  });
});
