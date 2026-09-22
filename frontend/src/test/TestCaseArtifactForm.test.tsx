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
  testcasesApi: { update: vi.fn(), delete: vi.fn(), review: vi.fn() },
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
    vi.mocked(testcasesApi.review).mockReset();
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

  // GitHub #677 (the TestCase side of the reported a11y gap): a rejected save
  // must be announced, not just drawn — the banner is an assertive live region
  // on the TestCase form.
  it("announces a failed save with an assertive live region (#677)", async () => {
    vi.mocked(testcasesApi.update).mockRejectedValue(new Error("Server exploded"));
    render(
      <TestCaseArtifactForm
        testCase={TEST_CASE}
        onSaved={vi.fn()}
        onDeleted={vi.fn()}
      />
    );
    await userEvent.click(await screen.findByTestId("artifact-form-save"));
    const banner = await screen.findByTestId("artifact-form-error");
    expect(banner).toHaveTextContent("Server exploded");
    expect(banner).toHaveAttribute("role", "alert");
    expect(banner).toHaveAttribute("aria-live", "assertive");
  });

  // #402: the scenario select is this adapter's own control (fixed two-value
  // contract), not a definition-driven attribute.
  it("sends the selected scenario_kind on save (#402)", async () => {
    vi.mocked(testcasesApi.update).mockResolvedValue(TEST_CASE);
    render(
      <TestCaseArtifactForm
        testCase={TEST_CASE}
        onSaved={vi.fn()}
        onDeleted={vi.fn()}
      />
    );
    const select = await screen.findByTestId("tc-scenario-kind-select");
    expect(select).toHaveValue("nominal");
    await userEvent.selectOptions(select, "off_nominal");
    await userEvent.click(screen.getByTestId("artifact-form-save"));
    await waitFor(() =>
      expect(testcasesApi.update).toHaveBeenCalledWith(
        "t-1",
        expect.objectContaining({ scenario_kind: "off_nominal" })
      )
    );
  });

  // #424: the review action is wired to POST /testcases/{id}/review/ and asks
  // the host to refetch on success.
  it("marks the test case as reviewed via the review endpoint (#424)", async () => {
    vi.mocked(testcasesApi.review).mockResolvedValue({ ...TEST_CASE, reviewed: true });
    const onReviewed = vi.fn();
    render(
      <TestCaseArtifactForm
        testCase={TEST_CASE}
        onSaved={vi.fn()}
        onDeleted={vi.fn()}
        onReviewed={onReviewed}
      />
    );
    await userEvent.click(await screen.findByTestId("tc-review-button"));
    await waitFor(() =>
      expect(testcasesApi.review).toHaveBeenCalledWith("t-1", { reviewed: true })
    );
    expect(onReviewed).toHaveBeenCalledTimes(1);
  });

  it("shows the reviewed badge and no review button once reviewed (#424)", async () => {
    render(
      <TestCaseArtifactForm
        testCase={{ ...TEST_CASE, reviewed: true } as never}
        onSaved={vi.fn()}
        onDeleted={vi.fn()}
      />
    );
    expect(await screen.findByTestId("tc-reviewed-badge")).toBeInTheDocument();
    expect(screen.queryByTestId("tc-review-button")).toBeNull();
  });

  it("announces a failed review without hiding the button (#424)", async () => {
    vi.mocked(testcasesApi.review).mockRejectedValue(new Error("not allowed"));
    render(
      <TestCaseArtifactForm
        testCase={TEST_CASE}
        onSaved={vi.fn()}
        onDeleted={vi.fn()}
      />
    );
    await userEvent.click(await screen.findByTestId("tc-review-button"));
    const alert = await screen.findByTestId("tc-review-error");
    expect(alert).toHaveTextContent("not allowed");
    expect(alert).toHaveAttribute("role", "alert");
  });

  // #424: origin (write-once), reviewed (review endpoint only) and the
  // read-only baseline_drift annotation must never ride along on a PATCH.
  it("keeps origin, reviewed and baseline_drift out of the PATCH payload (#424)", () => {
    const patch = formValuesToTestCasePatch({
      title: "T",
      origin: "ai_generated",
      reviewed: false,
      baseline_drift: { drifted: true, count: 1 },
      custom_fields: {},
    });
    expect(patch).not.toHaveProperty("origin");
    expect(patch).not.toHaveProperty("reviewed");
    expect(patch).not.toHaveProperty("baseline_drift");
    expect(patch.title).toBe("T");
  });
});

