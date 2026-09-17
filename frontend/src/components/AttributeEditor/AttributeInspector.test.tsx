/**
 * AttributeInspector.test.tsx — options editor (Task 6, spec section 4.3).
 */

import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

import { AttributeInspector } from "./AttributeInspector";
import type { AttributeSpec } from "../../api/attribute-definitions";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

function attr(overrides: Partial<AttributeSpec>): AttributeSpec {
  return {
    name: "category",
    kind: "extended",
    type: "text",
    widget_key: null,
    fields: [],
    options: [],
    required: false,
    visible: true,
    locked: false,
    editable: true,
    section: "general",
    order: 0,
    label: { de: "", en: "" },
    help_text: { de: "", en: "" },
    default: null,
    validation: {},
    ai_elicit: false,
    export: false,
    audience: "basic",
    ...overrides,
  };
}

const ENUM_OPTIONS = [
  { value: "low", label_de: "Niedrig", label_en: "Low" },
  { value: "high", label_de: "Hoch", label_en: "High" },
];

function renderInspector(overrides: Partial<AttributeSpec> = {}, props: Partial<{
  onPatch: (patch: Partial<AttributeSpec>) => void;
  onRequestRemoveOption: (optionValue: string) => void;
  readOnly: boolean;
}> = {}) {
  const attribute = attr(overrides);
  const onPatch = props.onPatch ?? vi.fn();
  const onRequestRemoveOption = props.onRequestRemoveOption ?? vi.fn();
  render(
    <AttributeInspector
      attribute={attribute}
      allAttributes={[attribute]}
      onPatch={onPatch}
      onSectionChange={vi.fn()}
      onRequestRemoveOption={onRequestRemoveOption}
      readOnly={props.readOnly ?? false}
    />
  );
  return { attribute, onPatch, onRequestRemoveOption };
}

describe("AttributeInspector options editor", () => {
  it("hides the options section for a non-enum type", () => {
    renderInspector({ type: "text" });
    expect(screen.queryByTestId("attribute-inspector-options")).toBeNull();
  });

  it("shows the options section for an enum type", () => {
    renderInspector({ type: "enum", options: ENUM_OPTIONS });
    expect(screen.getByTestId("attribute-inspector-options")).toBeTruthy();
    expect(screen.getByTestId("attribute-inspector-option-0-value")).toBeTruthy();
    expect(screen.getByTestId("attribute-inspector-option-1-value")).toBeTruthy();
  });

  it("shows the options section for a multi-enum type", () => {
    renderInspector({ type: "multi-enum", options: ENUM_OPTIONS });
    expect(screen.getByTestId("attribute-inspector-options")).toBeTruthy();
  });

  it("adds a new empty option row via onPatch", () => {
    const { onPatch } = renderInspector({ type: "enum", options: ENUM_OPTIONS });
    fireEvent.click(screen.getByTestId("attribute-inspector-option-add"));
    expect(onPatch).toHaveBeenCalledWith({
      options: [...ENUM_OPTIONS, { value: "", label_de: "", label_en: "" }],
    });
  });

  it("edits an option's value/label fields via onPatch", () => {
    const { onPatch } = renderInspector({ type: "enum", options: ENUM_OPTIONS });
    fireEvent.change(screen.getByTestId("attribute-inspector-option-0-label-en"), {
      target: { value: "Very low" },
    });
    expect(onPatch).toHaveBeenCalledWith({
      options: [
        { value: "low", label_de: "Niedrig", label_en: "Very low" },
        ENUM_OPTIONS[1],
      ],
    });
  });

  it("reorders options up/down via onPatch", () => {
    const { onPatch } = renderInspector({ type: "enum", options: ENUM_OPTIONS });
    fireEvent.click(screen.getByTestId("attribute-inspector-option-1-up"));
    expect(onPatch).toHaveBeenCalledWith({
      options: [ENUM_OPTIONS[1], ENUM_OPTIONS[0]],
    });
  });

  it("requests confirmation instead of patching directly when removing an option", () => {
    const { onPatch, onRequestRemoveOption } = renderInspector({
      type: "enum",
      options: ENUM_OPTIONS,
    });
    fireEvent.click(screen.getByTestId("attribute-inspector-option-0-remove"));
    expect(onRequestRemoveOption).toHaveBeenCalledWith("low");
    expect(onPatch).not.toHaveBeenCalled();
  });

  it("disables all option controls when readOnly", () => {
    renderInspector({ type: "enum", options: ENUM_OPTIONS }, { readOnly: true });
    expect(screen.getByTestId("attribute-inspector-option-add")).toBeDisabled();
    expect(screen.getByTestId("attribute-inspector-option-0-remove")).toBeDisabled();
    expect(screen.getByTestId("attribute-inspector-option-0-value")).toBeDisabled();
  });
});
