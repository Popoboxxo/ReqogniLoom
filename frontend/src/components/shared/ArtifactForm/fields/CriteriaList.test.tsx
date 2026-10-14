/**
 * #1288 — the `criteria-list` field widget: ordered rows, per-item checkbox,
 * add/remove. The value contract is `{text, fulfilled, evidence_ref?}[]`.
 */
import { describe, it, expect, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import type { AttributeSpec } from "../../../../api/attribute-definitions";
import { CriteriaList } from "./CriteriaList";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ i18n: { language: "en" }, t: (k: string) => k }),
}));

function spec(overrides: Partial<AttributeSpec> = {}): AttributeSpec {
  return {
    name: "acceptance_criteria",
    kind: "core",
    type: "criteria-list",
    widget_key: null,
    fields: [],
    options: [],
    required: false,
    visible: true,
    locked: false,
    editable: true,
    section: "general",
    order: 10,
    label: { de: "Abnahmekriterien", en: "Acceptance criteria" },
    help_text: { de: "", en: "" },
    default: null,
    validation: {},
    ai_elicit: false,
    export: true,
    audience: "basic",
    ...overrides,
  };
}

describe("CriteriaList", () => {
  it("renders one row per criterion", () => {
    render(
      <CriteriaList
        attribute={spec()}
        value={[
          { text: "a", fulfilled: false, evidence_ref: null },
          { text: "b", fulfilled: true, evidence_ref: null },
        ]}
        onChange={vi.fn()}
        disabled={false}
        testId="artifact-field-acceptance_criteria"
      />
    );
    expect(screen.getByTestId("artifact-field-acceptance_criteria-row-0")).toBeTruthy();
    expect(screen.getByTestId("artifact-field-acceptance_criteria-row-1")).toBeTruthy();
    expect(
      (screen.getByTestId("artifact-field-acceptance_criteria-text-1") as HTMLInputElement)
        .value
    ).toBe("b");
  });

  it("toggles fulfilled for a single row", () => {
    const onChange = vi.fn();
    render(
      <CriteriaList
        attribute={spec()}
        value={[{ text: "a", fulfilled: false, evidence_ref: null }]}
        onChange={onChange}
        disabled={false}
        testId="f"
      />
    );
    fireEvent.click(screen.getByTestId("f-fulfilled-0"));
    expect(onChange).toHaveBeenCalledWith([
      { text: "a", fulfilled: true, evidence_ref: null },
    ]);
  });

  it("adds and removes a criterion", () => {
    const onChange = vi.fn();
    render(
      <CriteriaList
        attribute={spec()}
        value={[{ text: "a", fulfilled: false, evidence_ref: null }]}
        onChange={onChange}
        disabled={false}
        testId="f"
      />
    );
    fireEvent.click(screen.getByTestId("f-add"));
    expect(onChange).toHaveBeenCalledWith([
      { text: "a", fulfilled: false, evidence_ref: null },
      { text: "", fulfilled: false, evidence_ref: null },
    ]);
    fireEvent.click(screen.getByTestId("f-remove-0"));
    expect(onChange).toHaveBeenCalledWith([]);
  });
});
