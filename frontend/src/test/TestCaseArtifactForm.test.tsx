import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { resolveLocaleKey } from "./i18n-test-helpers";
import { testcasesApi } from "../api/testcases";
import { attributeDefinitionsApi } from "../api/attribute-definitions";
import {
  TestCaseArtifactForm,
  formValuesToTestCasePatch,
  testCaseToFormValues,
} from "../components/TestCaseEditors/TestCaseArtifactForm";

// Same convention as RiskArtifactForm/IssueArtifactForm tests (Tasks 19/20):
// the real `useTranslation()` hook needs a real i18next instance
// (`i18n.language` set) to avoid `FieldShell`'s `helpText`/`attributeLabel`
// crashing on `undefined.startsWith`. Mocking the hook directly, resolved
// against the real German locale, avoids spinning up the full i18n stack.
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown>) => {
      const { defaultValue, ...interpolation } = options ?? {};
      const resolved =
        resolveLocaleKey(key) ??
        (typeof defaultValue === "string" ? defaultValue : key);
      return Object.entries(interpolation).reduce(
        (acc, [name, value]) => acc.replace(`{{${name}}}`, String(value)),
        resolved
      );
    },
    i18n: { language: "de" },
  }),
}));

vi.mock("../api/testcases", () => ({
  testcasesApi: { update: vi.fn(), delete: vi.fn() },
}));
vi.mock("../api/attribute-definitions", () => ({
  attributeDefinitionsApi: { getWorkspace: vi.fn() },
}));
vi.mock("../context/WorkspaceContext", () => ({
  useWorkspace: () => ({ activeWorkspace: { id: "ws-1", preset: "standard" } }),
}));

const TEST_CASE = {
  id: "t-1",
  workspace_id: "ws-1",
  title: "Login works",
  description: "d",
  steps: ["open", "click"],
  test_type: "functional",
  custom_fields: {},
  version: 1,
} as never;

function attr(over: Record<string, unknown>) {
  return {
    name: "title", kind: "core", type: "text", widget_key: null, fields: [],
    options: [], required: false, visible: true, locked: false, editable: true,
    section: "general", order: 1, label: { de: "", en: "" },
    help_text: { de: "", en: "" }, default: null, validation: {},
    ai_elicit: false, export: true, audience: "basic", ...over,
  };
}

describe("TestCaseArtifactForm", () => {
  beforeEach(() => {
    vi.mocked(attributeDefinitionsApi.getWorkspace).mockResolvedValue({
      item_type: "TestCase",
      preset: "standard",
      is_customized: false,
      version: 1,
      attributes: [
        attr({ name: "title" }),
        attr({
          name: "steps", type: "widget", widget_key: "steps_editor",
          fields: ["steps_data"], order: 2,
        }),
      ],
    } as never);
    vi.mocked(testcasesApi.update).mockReset();
    vi.mocked(testcasesApi.delete).mockReset();
  });

  it("aliases the wire field steps onto the form field steps_data", () => {
    const values = testCaseToFormValues(TEST_CASE);
    expect(values.steps_data).toEqual(["open", "click"]);
    expect(values).not.toHaveProperty("steps");
  });

  it("translates steps_data back to steps on the way out", () => {
    const patch = formValuesToTestCasePatch({
      title: "T",
      steps_data: ["a"],
      custom_fields: {},
    });
    expect(patch.steps).toEqual(["a"]);
    expect(patch).not.toHaveProperty("steps_data");
  });

  it("renders the steps editor and appends a step", async () => {
    render(
      <TestCaseArtifactForm
        testCase={TEST_CASE}
        onSaved={vi.fn()}
        onDeleted={vi.fn()}
      />
    );
    expect(await screen.findByTestId("artifact-widget-steps")).toBeInTheDocument();
    expect(screen.getByTestId("artifact-widget-steps-step-0")).toHaveValue("open");
    await userEvent.click(screen.getByTestId("artifact-widget-steps-add"));
    expect(screen.getByTestId("artifact-widget-steps-step-2")).toBeInTheDocument();
  });

  it("saves the edited steps through testcasesApi.update", async () => {
    // StepsEditor's bound value shape is `{ step, expected_result }[]`
    // (rest_api/serializers.py: `steps = ListField(child=DictField())`,
    // StepsEditor.tsx docstring) — NOT bare strings. The widget normalizes
    // any raw entry (including this fixture's legacy `["open", "click"]`)
    // to that shape on the very first write (e.g. the Add-step click below),
    // so the saved PATCH carries dicts, not strings.
    vi.mocked(testcasesApi.update).mockResolvedValue(TEST_CASE);
    render(
      <TestCaseArtifactForm
        testCase={TEST_CASE}
        onSaved={vi.fn()}
        onDeleted={vi.fn()}
      />
    );
    await userEvent.click(await screen.findByTestId("artifact-widget-steps-add"));
    await userEvent.click(screen.getByTestId("artifact-form-save"));
    await waitFor(() =>
      expect(testcasesApi.update).toHaveBeenCalledWith(
        "t-1",
        expect.objectContaining({
          steps: [
            { step: "open", expected_result: "" },
            { step: "click", expected_result: "" },
            { step: "", expected_result: "" },
          ],
        })
      )
    );
  });
});
