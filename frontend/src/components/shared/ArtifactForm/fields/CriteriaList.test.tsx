/**
 * #1288 — the `criteria-list` field widget: ordered rows, per-item checkbox,
 * add/remove. The value contract is `{text, fulfilled, evidence_ref?}[]`.
 */
import { describe, it, expect, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import type { AttributeSpec } from "../../../../api/attribute-definitions";
import { CriteriaList } from "./CriteriaList";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    i18n: { language: "en" },
    // The required word is resolved to its real English value so the test can
    // compute the group's accessible name instead of comparing a raw key.
    t: (k: string) => (k === "artifactForm.requiredField" ? "Required field" : k),
  }),
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

  // H2 (#1393 review): `aria-required` is invalid on `role="group"` (ARIA 1.2),
  // so a gate-required `acceptance_criteria` used to announce nothing. The
  // required state now rides in the group's accessible NAME, and the group is
  // named by `aria-labelledby` (a `<label htmlFor>` cannot label a div).
  it("carries requiredness in the group's accessible name, not aria-required", () => {
    render(
      <CriteriaList
        attribute={spec({ required: false, is_required: true })}
        value={[]}
        onChange={vi.fn()}
        disabled={false}
        testId="criteria"
      />
    );
    const group = screen.getByTestId("criteria");
    expect(group).not.toHaveAttribute("aria-required");
    expect(group).toHaveAttribute(
      "aria-labelledby",
      "criteria-label criteria-required"
    );
    expect(document.getElementById("criteria-label")).toHaveTextContent(
      "Acceptance criteria"
    );
    const requiredWord = document.getElementById("criteria-required");
    expect(requiredWord).toHaveTextContent("Required field");

    // SC 1.3.1/4.1.2 (A11Y minor): the required word must be a SIBLING of the
    // group. Inside the container it was both part of the accessible name and
    // group CONTENT, so browse mode read "Required field" twice.
    expect(group.contains(requiredWord)).toBe(false);

    // …while still contributing to the computed accessible name (en).
    expect(group).toHaveAccessibleName("Acceptance criteria Required field");
  });

  it("leaves an optional criteria list without a required word", () => {
    render(
      <CriteriaList
        attribute={spec()}
        value={[]}
        onChange={vi.fn()}
        disabled={false}
        testId="criteria"
      />
    );
    const group = screen.getByTestId("criteria");
    expect(group).toHaveAttribute("aria-labelledby", "criteria-label");
    expect(document.getElementById("criteria-required")).toBeNull();
  });

  // B2 (#1394): the per-row checkbox is wrapped in a real `<label>` so the
  // 24x24 hit-area floor in `.checkboxRow` covers a clickable element.
  it("wraps the per-row fulfilled checkbox in a label", () => {
    render(
      <CriteriaList
        attribute={spec()}
        value={[{ text: "a", fulfilled: false, evidence_ref: null }]}
        onChange={vi.fn()}
        disabled={false}
        testId="f"
      />
    );
    const checkbox = screen.getByTestId("f-fulfilled-0");
    expect(checkbox.closest("label")).not.toBeNull();
  });
});
