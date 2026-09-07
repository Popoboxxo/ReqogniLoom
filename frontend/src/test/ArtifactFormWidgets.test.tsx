import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { resolveLocaleKey } from "./i18n-test-helpers";

// DEVIATION from the plan brief (same class as ArtifactFormFields.test.tsx /
// Task 16): the shared i18next singleton is never initialised in unit tests,
// so the widgets' real `useTranslation()` calls need a mock, not a live
// instance — verified live: without this mock, `t("risks.rpn", ...)` renders
// the literal key instead of the interpolated string.
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, string | number>) => {
      const resolved = resolveLocaleKey(key) ?? key;
      if (!options) return resolved;
      return Object.entries(options).reduce(
        (acc, [name, value]) => acc.replace(`{{${name}}}`, String(value)),
        resolved
      );
    },
    i18n: { language: "de" },
  }),
}));

// DEVIATION from the plan brief: MarkdownTabGroup renders MarkdownPreview,
// which calls `useWorkspace()` unconditionally — verified live: without this
// mock every markdown-tab-group test throws "useWorkspace must be used
// within WorkspaceProvider". Mirrors the established fixed-workspace mock in
// AdrEditors.test.tsx.
vi.mock("../context/WorkspaceContext", () => ({
  useWorkspace: () => ({ activeWorkspace: { id: "ws-001", name: "WS" } }),
}));

import {
  WIDGET_REGISTRY,
  computeRpn,
} from "../components/shared/ArtifactForm/widget-registry";
import type { AttributeSpec } from "../api/attribute-definitions";

function widgetSpec(over: Partial<AttributeSpec>): AttributeSpec {
  return {
    name: "w",
    kind: "core",
    type: "widget",
    widget_key: null,
    fields: [],
    options: [],
    required: false,
    visible: true,
    locked: false,
    editable: true,
    section: "general",
    order: 0,
    label: { de: "W", en: "W" },
    help_text: { de: "", en: "" },
    default: null,
    validation: {},
    ai_elicit: false,
    export: false,
    audience: "basic",
    ...over,
  };
}

describe("ArtifactForm widget registry", () => {
  it("registers exactly the three spec widget keys", () => {
    expect(Object.keys(WIDGET_REGISTRY).sort()).toEqual([
      "markdown_tab_group",
      "risk_matrix_rpz",
      "steps_editor",
    ]);
  });

  it("computes the RPN the same way the backend does", () => {
    expect(computeRpn("low", "low", 1)).toBe(1);
    expect(computeRpn("high", "high", 10)).toBe(90);
    expect(computeRpn("medium", "high", null)).toBe(30); // detection falls back to 5
    expect(computeRpn("unknown", "high", 2)).toBe(6); // unknown probability -> 1
  });

  it("renders the risk matrix and updates the RPN live", () => {
    const onChange = vi.fn();
    const Widget = WIDGET_REGISTRY.risk_matrix_rpz;
    const attribute = widgetSpec({
      name: "risk_matrix",
      widget_key: "risk_matrix_rpz",
      fields: ["probability", "impact", "detection"],
    });
    const { rerender } = render(
      <Widget
        attribute={attribute}
        values={{ probability: "low", impact: "low", detection: 1 }}
        onChange={onChange}
        disabled={false}
        testId="artifact-widget-risk_matrix"
      />
    );
    expect(screen.getByTestId("artifact-widget-risk_matrix-rpn")).toHaveTextContent("1");

    rerender(
      <Widget
        attribute={attribute}
        values={{ probability: "high", impact: "high", detection: 10 }}
        onChange={onChange}
        disabled={false}
        testId="artifact-widget-risk_matrix"
      />
    );
    expect(screen.getByTestId("artifact-widget-risk_matrix-rpn")).toHaveTextContent("90");
  });

  it("reports a risk-matrix edit under the bound field name", () => {
    const onChange = vi.fn();
    const Widget = WIDGET_REGISTRY.risk_matrix_rpz;
    render(
      <Widget
        attribute={widgetSpec({
          name: "risk_matrix",
          widget_key: "risk_matrix_rpz",
          fields: ["probability", "impact", "detection"],
        })}
        values={{ probability: "low", impact: "low", detection: 1 }}
        onChange={onChange}
        disabled={false}
        testId="artifact-widget-risk_matrix"
      />
    );
    fireEvent.change(screen.getByTestId("artifact-widget-risk_matrix-detection"), {
      target: { value: "7" },
    });
    expect(onChange).toHaveBeenCalledWith("detection", 7);
  });

  it("renders one markdown tab per bound field and switches between them", () => {
    const Widget = WIDGET_REGISTRY.markdown_tab_group;
    render(
      <Widget
        attribute={widgetSpec({
          name: "decision_record",
          widget_key: "markdown_tab_group",
          fields: ["description", "context", "consequences"],
        })}
        values={{ description: "d", context: "c", consequences: "q" }}
        onChange={vi.fn()}
        disabled={false}
        testId="artifact-widget-decision_record"
      />
    );
    // DEVIATION from the plan brief: `getAllByRole("tab")` also picks up
    // MarkdownPreview's own edit/preview toggle tabs (verified live: 5, not
    // 3, since only the active field's MarkdownPreview is mounted at a
    // time) — scoped to this widget's own tab test-ids instead.
    expect(
      screen.getAllByTestId(/^artifact-widget-decision_record-tab-/)
    ).toHaveLength(3);
    fireEvent.click(screen.getByTestId("artifact-widget-decision_record-tab-context"));
    expect(
      screen.getByTestId("artifact-widget-decision_record-tab-context")
    ).toHaveAttribute("aria-selected", "true");
  });

  it("adds, edits and removes a test step", () => {
    const onChange = vi.fn();
    const Widget = WIDGET_REGISTRY.steps_editor;
    render(
      <Widget
        attribute={widgetSpec({
          name: "steps",
          widget_key: "steps_editor",
          fields: ["steps_data"],
        })}
        values={{ steps_data: [{ step: "first", expected_result: "ok" }] }}
        onChange={onChange}
        disabled={false}
        testId="artifact-widget-steps"
      />
    );
    fireEvent.click(screen.getByTestId("artifact-widget-steps-add"));
    expect(onChange).toHaveBeenCalledWith("steps_data", [
      { step: "first", expected_result: "ok" },
      { step: "", expected_result: "" },
    ]);

    fireEvent.click(screen.getByTestId("artifact-widget-steps-remove-0"));
    expect(onChange).toHaveBeenCalledWith("steps_data", []);
  });

  it("round-trips both step and expected_result independently (C-1 regression)", () => {
    // Guards against the fixed CRITICAL bug: the widget used to treat the
    // bound value as `string[]`, rendering every dict entry as the literal
    // text "[object Object]" and writing back a `string[]` the backend
    // rejects with a 400 (DRF `ListField(child=DictField())`).
    const onChange = vi.fn();
    const Widget = WIDGET_REGISTRY.steps_editor;
    render(
      <Widget
        attribute={widgetSpec({
          name: "steps",
          widget_key: "steps_editor",
          fields: ["steps_data"],
        })}
        values={{ steps_data: [{ step: "open the app", expected_result: "app loads" }] }}
        onChange={onChange}
        disabled={false}
        testId="artifact-widget-steps"
      />
    );

    // Renders as two real inputs, not "[object Object]".
    expect(screen.getByTestId("artifact-widget-steps-step-0")).toHaveValue("open the app");
    expect(screen.getByTestId("artifact-widget-steps-expected-0")).toHaveValue("app loads");

    fireEvent.change(screen.getByTestId("artifact-widget-steps-step-0"), {
      target: { value: "open the app v2" },
    });
    expect(onChange).toHaveBeenLastCalledWith("steps_data", [
      { step: "open the app v2", expected_result: "app loads" },
    ]);

    fireEvent.change(screen.getByTestId("artifact-widget-steps-expected-0"), {
      target: { value: "app loads within 2s" },
    });
    expect(onChange).toHaveBeenLastCalledWith("steps_data", [
      { step: "open the app", expected_result: "app loads within 2s" },
    ]);
  });

  it("tolerates a non-array steps value", () => {
    const Widget = WIDGET_REGISTRY.steps_editor;
    render(
      <Widget
        attribute={widgetSpec({
          name: "steps",
          widget_key: "steps_editor",
          fields: ["steps_data"],
        })}
        values={{ steps_data: null }}
        onChange={vi.fn()}
        disabled={false}
        testId="artifact-widget-steps"
      />
    );
    expect(screen.queryAllByTestId(/artifact-widget-steps-step-/)).toHaveLength(0);
  });

  it("degrades a legacy string[]/malformed entry to {step, expected_result: ''} instead of crashing", () => {
    const Widget = WIDGET_REGISTRY.steps_editor;
    render(
      <Widget
        attribute={widgetSpec({
          name: "steps",
          widget_key: "steps_editor",
          fields: ["steps_data"],
        })}
        values={{ steps_data: ["legacy plain string", 42, { step: "ok", expected_result: "fine" }] }}
        onChange={vi.fn()}
        disabled={false}
        testId="artifact-widget-steps"
      />
    );
    expect(screen.getByTestId("artifact-widget-steps-step-0")).toHaveValue("legacy plain string");
    expect(screen.getByTestId("artifact-widget-steps-expected-0")).toHaveValue("");
    expect(screen.getByTestId("artifact-widget-steps-step-1")).toHaveValue("42");
    expect(screen.getByTestId("artifact-widget-steps-expected-1")).toHaveValue("");
    expect(screen.getByTestId("artifact-widget-steps-step-2")).toHaveValue("ok");
    expect(screen.getByTestId("artifact-widget-steps-expected-2")).toHaveValue("fine");
  });
});
