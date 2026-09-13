/**
 * LayoutFlowEditor.test.tsx — 12-column flow editor (WS4 #938, spec section 7).
 *
 * Covers the editor's local mutation surface only: every change must be
 * reported through the page callbacks (the normal Save PUT persists them),
 * never written to the API directly.
 */

import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

import { LayoutFlowEditor } from "./LayoutFlowEditor";
import type {
  AttributeSpec,
  SectionSpec,
} from "../../api/attribute-definitions";

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

function section(overrides: Partial<SectionSpec>): SectionSpec {
  return { name: "general", order: 0, visible: true, layout: "full", ...overrides };
}

function renderEditor(overrides: Partial<Parameters<typeof LayoutFlowEditor>[0]> = {}) {
  const onSectionFlowChange = vi.fn();
  const onAttributeFlowChange = vi.fn();
  render(
    <LayoutFlowEditor
      attributes={[attr({ name: "a", section: "general", order: 0 })]}
      sections={[]}
      sectionFlow={undefined}
      emptySections={[]}
      readOnly={false}
      onSectionFlowChange={onSectionFlowChange}
      onAttributeFlowChange={onAttributeFlowChange}
      {...overrides}
    />
  );
  return { onSectionFlowChange, onAttributeFlowChange };
}

describe("LayoutFlowEditor section flow", () => {
  it("derives every section when no flow is stored and appends a spacer", () => {
    const { onSectionFlowChange } = renderEditor({
      attributes: [
        attr({ name: "a", section: "general", order: 0 }),
        attr({ name: "b", section: "extra", order: 0 }),
      ],
    });
    expect(screen.getByTestId("section-flow-token-0")).toBeInTheDocument();
    expect(screen.getByTestId("section-flow-token-1")).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("section-flow-add-spacer"));
    expect(onSectionFlowChange).toHaveBeenCalledWith([
      { kind: "section", name: "general" },
      { kind: "section", name: "extra" },
      { kind: "spacer", size: "md" },
    ]);
  });

  it("changes a spacer size and removes it", () => {
    const { onSectionFlowChange } = renderEditor({
      attributes: [
        attr({ name: "a", section: "general", order: 0 }),
        attr({ name: "b", section: "extra", order: 0 }),
      ],
      sectionFlow: [
        { kind: "section", name: "general" },
        { kind: "spacer", size: "sm" },
        { kind: "section", name: "extra" },
      ],
    });
    expect(screen.getByTestId("section-flow-token-1-size")).toHaveValue("sm");
    fireEvent.change(screen.getByTestId("section-flow-token-1-size"), {
      target: { value: "lg" },
    });
    expect(onSectionFlowChange).toHaveBeenLastCalledWith([
      { kind: "section", name: "general" },
      { kind: "spacer", size: "lg" },
      { kind: "section", name: "extra" },
    ]);

    fireEvent.click(screen.getByTestId("section-flow-token-1-remove"));
    expect(onSectionFlowChange).toHaveBeenLastCalledWith([
      { kind: "section", name: "general" },
      { kind: "section", name: "extra" },
    ]);
  });

  it("moves a section token down", () => {
    const { onSectionFlowChange } = renderEditor({
      attributes: [
        attr({ name: "a", section: "general", order: 0 }),
        attr({ name: "b", section: "extra", order: 0 }),
      ],
    });
    fireEvent.click(screen.getByTestId("section-flow-token-0-down"));
    expect(onSectionFlowChange).toHaveBeenLastCalledWith([
      { kind: "section", name: "extra" },
      { kind: "section", name: "general" },
    ]);
  });
});

describe("LayoutFlowEditor attribute flow", () => {
  it("changes an attribute span and appends a spacer", () => {
    const { onAttributeFlowChange } = renderEditor({
      attributes: [
        attr({ name: "a", section: "general", order: 0 }),
        attr({ name: "b", section: "general", order: 1 }),
      ],
      sections: [
        section({
          name: "general",
          attribute_flow: [
            { kind: "attribute", name: "a", span: "half" },
            { kind: "spacer", size: "md" },
            { kind: "attribute", name: "b", span: "quarter" },
          ],
        }),
      ],
    });
    expect(screen.getByTestId("attribute-flow-general-token-0-span")).toHaveValue("half");
    fireEvent.change(screen.getByTestId("attribute-flow-general-token-0-span"), {
      target: { value: "quarter" },
    });
    expect(onAttributeFlowChange).toHaveBeenLastCalledWith("general", [
      { kind: "attribute", name: "a", span: "quarter" },
      { kind: "spacer", size: "md" },
      { kind: "attribute", name: "b", span: "quarter" },
    ]);

    fireEvent.click(screen.getByTestId("attribute-flow-general-add-spacer"));
    expect(onAttributeFlowChange).toHaveBeenLastCalledWith("general", [
      { kind: "attribute", name: "a", span: "half" },
      { kind: "spacer", size: "md" },
      { kind: "attribute", name: "b", span: "quarter" },
      { kind: "spacer", size: "md" },
    ]);
  });

  it("moves an attribute token and refuses to move past the ends", () => {
    const { onAttributeFlowChange } = renderEditor({
      attributes: [
        attr({ name: "a", section: "general", order: 0 }),
        attr({ name: "b", section: "general", order: 1 }),
      ],
      sections: [section({ name: "general" })],
    });
    fireEvent.click(screen.getByTestId("attribute-flow-general-token-0-down"));
    expect(onAttributeFlowChange).toHaveBeenLastCalledWith("general", [
      { kind: "attribute", name: "b", span: "full" },
      { kind: "attribute", name: "a", span: "full" },
    ]);
    // First token's up button is disabled — the handler must not fire again.
    expect(screen.getByTestId("attribute-flow-general-token-0-up")).toBeDisabled();
  });

  it("disables every control when readOnly", () => {
    renderEditor({
      readOnly: true,
      attributes: [attr({ name: "a", section: "general", order: 0 })],
      sections: [section({ name: "general" })],
    });
    expect(screen.getByTestId("section-flow-add-spacer")).toBeDisabled();
    expect(screen.getByTestId("attribute-flow-general-add-spacer")).toBeDisabled();
    expect(screen.getByTestId("attribute-flow-general-token-0-span")).toBeDisabled();
  });
});

describe("LayoutFlowEditor empty sections", () => {
  it("renders an empty section token", () => {
    renderEditor({ emptySections: ["stub"] });
    // general (from the attribute) + stub, in that order.
    expect(screen.getByTestId("section-flow-token-1")).toBeInTheDocument();
  });
});
