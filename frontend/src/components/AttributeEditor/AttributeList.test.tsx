/**
 * AttributeList.test.tsx — section visibility + layout controls (Task 8,
 * spec section 4.4/4.5). Covers only the new surface this task adds; the
 * rest of AttributeList (drag reorder, rename, delete) has no prior test
 * coverage either and is out of this task's scope.
 */

import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

import { AttributeList } from "./AttributeList";
import type { AttributeSpec } from "../../api/attribute-definitions";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

function attr(overrides: Partial<AttributeSpec>): AttributeSpec {
  return {
    name: "title",
    kind: "core",
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

const defaultProps = {
  attributes: [attr({ name: "title" })],
  sections: [],
  emptySections: [],
  selected: null,
  onSelect: vi.fn(),
  onMove: vi.fn(),
  onRenameSection: vi.fn(),
  onDeleteSection: vi.fn(),
  onMoveSection: vi.fn(),
  onAddAttribute: vi.fn(),
  onDeleteAttribute: vi.fn(),
  readOnly: false,
};

describe("AttributeList section visibility + layout", () => {
  it("defaults to checked/full when the section has no SectionSpec entry", () => {
    render(
      <AttributeList
        {...defaultProps}
        onToggleSectionVisible={vi.fn()}
        onSetSectionLayout={vi.fn()}
      />
    );
    expect(screen.getByTestId("attribute-section-general-visible")).toBeChecked();
    expect(screen.getByTestId("attribute-section-general-layout")).toHaveValue("full");
  });

  it("reflects the given SectionSpec's visible/layout values", () => {
    render(
      <AttributeList
        {...defaultProps}
        sections={[{ name: "general", order: 0, visible: false, layout: "half" }]}
        onToggleSectionVisible={vi.fn()}
        onSetSectionLayout={vi.fn()}
      />
    );
    expect(screen.getByTestId("attribute-section-general-visible")).not.toBeChecked();
    expect(screen.getByTestId("attribute-section-general-layout")).toHaveValue("half");
  });

  it("calls onToggleSectionVisible when the checkbox is clicked", () => {
    const onToggleSectionVisible = vi.fn();
    render(
      <AttributeList
        {...defaultProps}
        onToggleSectionVisible={onToggleSectionVisible}
        onSetSectionLayout={vi.fn()}
      />
    );
    fireEvent.click(screen.getByTestId("attribute-section-general-visible"));
    expect(onToggleSectionVisible).toHaveBeenCalledWith("general");
  });

  it("calls onSetSectionLayout when the layout select changes", () => {
    const onSetSectionLayout = vi.fn();
    render(
      <AttributeList
        {...defaultProps}
        onToggleSectionVisible={vi.fn()}
        onSetSectionLayout={onSetSectionLayout}
      />
    );
    fireEvent.change(screen.getByTestId("attribute-section-general-layout"), {
      target: { value: "half" },
    });
    expect(onSetSectionLayout).toHaveBeenCalledWith("general", "half");
  });

  it("disables both controls when readOnly", () => {
    render(
      <AttributeList
        {...defaultProps}
        readOnly
        onToggleSectionVisible={vi.fn()}
        onSetSectionLayout={vi.fn()}
      />
    );
    expect(screen.getByTestId("attribute-section-general-visible")).toBeDisabled();
    expect(screen.getByTestId("attribute-section-general-layout")).toBeDisabled();
  });
});
