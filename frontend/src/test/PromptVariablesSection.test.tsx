/**
 * ARCH-L1-001 ReactFrontend — central prompt variable management (spec §5).
 */
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { PromptVariablesSection } from "../components/WorkspaceSettings/PromptVariablesSection";
import type { PromptVariableState } from "../api/prompt-variables";
import { resolveLocaleKey } from "./i18n-test-helpers";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, fallback?: unknown, options?: Record<string, string>) => {
      const fallbackStr = typeof fallback === "string" ? fallback : undefined;
      const params = typeof fallback === "object" && fallback !== null ? (fallback as Record<string, string>) : options;
      const resolved = resolveLocaleKey(key) ?? fallbackStr ?? key;
      if (!params) return resolved;
      return Object.entries(params).reduce(
        (acc, [name, value]) => acc.replace(`{{${name}}}`, String(value)),
        resolved
      );
    },
  }),
}));
vi.mock("../api/client", () => ({
  extractErrorMessage: (e: unknown) => (e instanceof Error ? e.message : "error"),
}));

const list = vi.fn();
const save = vi.fn();
const clear = vi.fn();
vi.mock("../api/prompt-variables", () => ({
  promptVariablesApi: {
    list: (...args: unknown[]) => list(...args),
    save: (...args: unknown[]) => save(...args),
    clear: (...args: unknown[]) => clear(...args),
  },
}));

const WORKSPACE_ID = "11111111-1111-1111-1111-111111111111";

function variable(
  name: string,
  overrides: Partial<PromptVariableState> = {}
): PromptVariableState {
  return {
    name,
    kind: "config",
    var_type: "int",
    description: `desc ${name}`,
    factory_default: 5,
    global_value: null,
    global_version: null,
    workspace_value: null,
    workspace_version: null,
    has_workspace_override: false,
    effective_value: 5,
    effective_scope: "factory",
    is_editable: true,
    ...overrides,
  };
}

const VARIABLES: PromptVariableState[] = [
  variable("max_breadth"),
  variable("req_title", {
    kind: "data",
    var_type: "str",
    factory_default: "",
    effective_value: "",
    is_editable: false,
  }),
];

describe("PromptVariablesSection (spec §5)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    list.mockResolvedValue({
      variables: VARIABLES,
      count: VARIABLES.length,
      workspace_id: WORKSPACE_ID,
    });
    save.mockImplementation(async (name: string, value: unknown) =>
      variable(name, {
        workspace_value: value,
        workspace_version: 1,
        has_workspace_override: true,
        effective_value: value,
        effective_scope: "workspace",
      })
    );
    clear.mockImplementation(async (name: string) => variable(name));
  });

  it("lists every catalog variable", async () => {
    render(<PromptVariablesSection workspaceId={WORKSPACE_ID} />);

    expect(
      await screen.findByTestId("prompt-variable-row-max_breadth")
    ).toBeTruthy();
    expect(screen.getByTestId("prompt-variable-row-req_title")).toBeTruthy();
  });

  it("renders data variables without an editable input", async () => {
    render(<PromptVariablesSection workspaceId={WORKSPACE_ID} />);
    await screen.findByTestId("prompt-variable-row-req_title");

    expect(screen.queryByTestId("prompt-variable-req_title-input")).toBeNull();
    expect(screen.queryByTestId("prompt-variable-req_title-save")).toBeNull();
  });

  it("saves a config value as a workspace override", async () => {
    const user = userEvent.setup();
    render(<PromptVariablesSection workspaceId={WORKSPACE_ID} />);
    const input = await screen.findByTestId("prompt-variable-max_breadth-input");

    await user.clear(input);
    await user.type(input, "2");
    await user.click(screen.getByTestId("prompt-variable-max_breadth-save"));

    await waitFor(() =>
      expect(save).toHaveBeenCalledWith("max_breadth", 2, WORKSPACE_ID)
    );
    expect(
      screen.getByTestId("prompt-variable-max_breadth-origin").textContent
    ).toContain("Workspace-Override");
  });

  it("writes the tenant default when the global scope is selected", async () => {
    const user = userEvent.setup();
    render(<PromptVariablesSection workspaceId={WORKSPACE_ID} />);
    await screen.findByTestId("prompt-variable-max_breadth-input");

    await user.selectOptions(
      screen.getByTestId("prompt-variables-scope-select"),
      "global"
    );
    await user.click(screen.getByTestId("prompt-variable-max_breadth-save"));

    await waitFor(() =>
      expect(save).toHaveBeenCalledWith("max_breadth", 5, null)
    );
  });

  it("drops an override via reset", async () => {
    const user = userEvent.setup();
    list.mockResolvedValue({
      variables: [
        variable("max_breadth", {
          workspace_value: 2,
          workspace_version: 1,
          has_workspace_override: true,
          effective_value: 2,
          effective_scope: "workspace",
        }),
      ],
      count: 1,
      workspace_id: WORKSPACE_ID,
    });
    render(<PromptVariablesSection workspaceId={WORKSPACE_ID} />);
    await screen.findByTestId("prompt-variable-max_breadth-input");

    await user.click(screen.getByTestId("prompt-variable-max_breadth-reset"));

    await waitFor(() =>
      expect(clear).toHaveBeenCalledWith("max_breadth", WORKSPACE_ID)
    );
  });

  it("creates a brand-new config variable", async () => {
    const user = userEvent.setup();
    render(<PromptVariablesSection workspaceId={WORKSPACE_ID} />);
    await screen.findByTestId("prompt-variable-new-name");

    await user.type(screen.getByTestId("prompt-variable-new-name"), "tone_hint");
    await user.selectOptions(screen.getByTestId("prompt-variable-new-type"), "str");
    await user.type(
      screen.getByTestId("prompt-variable-new-description"),
      "Style instruction."
    );
    await user.type(screen.getByTestId("prompt-variable-new-value"), "Be terse.");
    await user.click(screen.getByTestId("prompt-variable-new-save"));

    await waitFor(() =>
      expect(save).toHaveBeenCalledWith("tone_hint", "Be terse.", WORKSPACE_ID, {
        varType: "str",
        description: "Style instruction.",
      })
    );
  });

  it("surfaces a save error", async () => {
    const user = userEvent.setup();
    save.mockRejectedValue(new Error("boom"));
    render(<PromptVariablesSection workspaceId={WORKSPACE_ID} />);
    await screen.findByTestId("prompt-variable-max_breadth-input");

    await user.click(screen.getByTestId("prompt-variable-max_breadth-save"));

    expect(
      (await screen.findByTestId("prompt-variables-error")).textContent
    ).toContain("boom");
  });

  it("keeps the workspace override visible after a global-scope write (review fix #1)", async () => {
    // Root cause: the backend's state resolver skips workspace-row lookup
    // when workspace_id is omitted (global-scope write), so its response
    // reports has_workspace_override: false even though a workspace
    // override still exists. Merging that partial response in directly
    // would make the workspace view show the wrong effective value and
    // disable the reset button. The fix refetches the full list instead.
    const user = userEvent.setup();
    const withOverride = variable("max_breadth", {
      workspace_value: 2,
      workspace_version: 1,
      has_workspace_override: true,
      effective_value: 2,
      effective_scope: "workspace",
    });
    list
      .mockResolvedValueOnce({
        variables: [withOverride],
        count: 1,
        workspace_id: WORKSPACE_ID,
      })
      .mockResolvedValueOnce({
        variables: [
          variable("max_breadth", {
            global_value: 9,
            global_version: 1,
            workspace_value: 2,
            workspace_version: 1,
            has_workspace_override: true,
            effective_value: 2,
            effective_scope: "workspace",
          }),
        ],
        count: 1,
        workspace_id: WORKSPACE_ID,
      });
    // Simulates the real backend's partial response for a global-scope
    // write: it looks like the workspace override was dropped.
    save.mockResolvedValueOnce(
      variable("max_breadth", {
        global_value: 9,
        global_version: 1,
        workspace_value: null,
        has_workspace_override: false,
        effective_value: 9,
        effective_scope: "global",
      })
    );

    render(<PromptVariablesSection workspaceId={WORKSPACE_ID} />);
    await screen.findByTestId("prompt-variable-max_breadth-input");

    await user.selectOptions(
      screen.getByTestId("prompt-variables-scope-select"),
      "global"
    );
    const input = screen.getByTestId("prompt-variable-max_breadth-input");
    await user.clear(input);
    await user.type(input, "9");
    await user.click(screen.getByTestId("prompt-variable-max_breadth-save"));

    await waitFor(() =>
      expect(save).toHaveBeenCalledWith("max_breadth", 9, null)
    );
    // The fix requires a refetch after a global-scope write.
    await waitFor(() => expect(list).toHaveBeenCalledTimes(2));

    await user.selectOptions(
      screen.getByTestId("prompt-variables-scope-select"),
      "workspace"
    );

    expect(screen.getByTestId("prompt-variable-max_breadth-input")).toHaveValue(
      "2"
    );
    expect(
      screen.getByTestId("prompt-variable-max_breadth-origin").textContent
    ).toContain("Workspace-Override");
  });

  it("rejects invalid JSON in the create form instead of saving the raw string (review fix #2)", async () => {
    const user = userEvent.setup();
    render(<PromptVariablesSection workspaceId={WORKSPACE_ID} />);
    await screen.findByTestId("prompt-variable-new-name");

    await user.type(screen.getByTestId("prompt-variable-new-name"), "weird_cfg");
    await user.selectOptions(screen.getByTestId("prompt-variable-new-type"), "json");
    await user.type(
      screen.getByTestId("prompt-variable-new-value"),
      "{{not valid json"
    );
    await user.click(screen.getByTestId("prompt-variable-new-save"));

    expect(
      (await screen.findByTestId("prompt-variables-error")).textContent
    ).toBeTruthy();
    expect(save).not.toHaveBeenCalled();
  });

  it("uses a bounded true/false control for bool values (review fix #2)", async () => {
    list.mockResolvedValue({
      variables: [
        variable("enable_x", {
          var_type: "bool",
          factory_default: false,
          effective_value: false,
        }),
      ],
      count: 1,
      workspace_id: WORKSPACE_ID,
    });
    render(<PromptVariablesSection workspaceId={WORKSPACE_ID} />);

    const control = await screen.findByTestId("prompt-variable-enable_x-input");
    expect(control.tagName).toBe("SELECT");
  });

  it("uses actions.create (Erstellen) instead of the removed Anlegen key", async () => {
    list.mockResolvedValue({ variables: [], count: 0, workspace_id: WORKSPACE_ID });
    render(<PromptVariablesSection workspaceId={WORKSPACE_ID} />);

    await screen.findByTestId("prompt-variable-new-save");

    expect(screen.getByTestId("prompt-variable-new-save")).toHaveTextContent("Erstellen");
  });
});
