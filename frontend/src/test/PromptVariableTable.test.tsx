/**
 * ARCH-L1-001 ReactFrontend — per-slot prompt variable table (spec §5).
 */
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";

import { PromptVariableTable } from "../components/WorkspaceSettings/PromptVariableTable";
import type { PromptVariableState } from "../api/prompt-variables";

vi.mock("react-i18next", () => {
  const t = (_key: string, fallback?: string): string => fallback ?? _key;
  return { useTranslation: () => ({ t }) };
});

function variable(
  name: string,
  overrides: Partial<PromptVariableState> = {}
): PromptVariableState {
  return {
    name,
    kind: "data",
    var_type: "str",
    description: `desc ${name}`,
    factory_default: "",
    global_value: null,
    global_version: null,
    workspace_value: null,
    workspace_version: null,
    has_workspace_override: false,
    effective_value: "",
    effective_scope: "factory",
    is_editable: false,
    ...overrides,
  };
}

const VARIABLES: PromptVariableState[] = [
  variable("req_title"),
  variable("max_breadth", {
    kind: "config",
    var_type: "int",
    factory_default: 5,
    workspace_value: 2,
    workspace_version: 1,
    has_workspace_override: true,
    effective_value: 2,
    effective_scope: "workspace",
    is_editable: true,
  }),
];

describe("PromptVariableTable (spec §5)", () => {
  it("renders one row per referenced variable", () => {
    render(
      <PromptVariableTable
        slotName="testcase_derive"
        variableNames={["req_title", "max_breadth"]}
        variables={VARIABLES}
      />
    );

    expect(
      screen.getByTestId("prompt-var-testcase_derive-req_title")
    ).toBeTruthy();
    expect(
      screen.getByTestId("prompt-var-testcase_derive-max_breadth")
    ).toBeTruthy();
  });

  it("shows the effective value and its origin badge", () => {
    render(
      <PromptVariableTable
        slotName="testcase_derive"
        variableNames={["max_breadth"]}
        variables={VARIABLES}
      />
    );

    const row = screen.getByTestId("prompt-var-testcase_derive-max_breadth");
    expect(row.textContent).toContain("2");
    expect(
      screen.getByTestId("prompt-var-testcase_derive-max_breadth-origin")
        .textContent
    ).toContain("Workspace-Override");
  });

  it("labels a data variable as code-bound", () => {
    render(
      <PromptVariableTable
        slotName="testcase_derive"
        variableNames={["req_title"]}
        variables={VARIABLES}
      />
    );

    expect(
      screen.getByTestId("prompt-var-testcase_derive-req_title").textContent
    ).toContain("code-gebunden");
  });

  it("renders nothing when the slot references no known variable", () => {
    const { container } = render(
      <PromptVariableTable
        slotName="testcase_derive"
        variableNames={[]}
        variables={VARIABLES}
      />
    );

    expect(container.firstChild).toBeNull();
  });

  it("skips a referenced name the catalog does not know", () => {
    render(
      <PromptVariableTable
        slotName="testcase_derive"
        variableNames={["req_title", "ghost"]}
        variables={VARIABLES}
      />
    );

    expect(screen.queryByTestId("prompt-var-testcase_derive-ghost")).toBeNull();
  });
});
