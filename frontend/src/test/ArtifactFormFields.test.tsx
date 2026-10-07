import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { resolveLocaleKey } from "./i18n-test-helpers";

// DEVIATION from the plan brief: the brief's test rendered field components
// (which call the real `useTranslation()`) with no i18next setup at all. The
// shared i18next singleton is never initialised in unit tests (see
// `EmptyState.test.tsx` for the same, documented, established pattern) — the
// literal-brief version crashes on `i18n.language.startsWith(...)` because
// `i18n.language` is `undefined` when i18next was never `.init()`-ed.
// Mirrors `EmptyState.test.tsx`'s real-locale-wins mock so a wrong-key bug
// (e.g. `artifactForm.unkownValue`) surfaces as a failing assertion rather
// than being silently masked by an always-return-the-fallback mock.
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, string>) => {
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

import {
  BooleanToggle,
  DateField,
  EnumSelect,
  MultiEnum,
  NumberField,
  TextArea,
  TextField,
  attributeLabel,
} from "../components/shared/ArtifactForm/fields";
import type { AttributeSpec } from "../api/attribute-definitions";

function spec(over: Partial<AttributeSpec> = {}): AttributeSpec {
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
    label: { de: "Titel", en: "Title" },
    help_text: { de: "", en: "" },
    default: null,
    validation: {},
    ai_elicit: false,
    export: false,
    audience: "basic",
    ...over,
  };
}

describe("ArtifactForm field library", () => {
  it("prefers the definition label over the raw attribute name", () => {
    expect(attributeLabel(spec(), "de")).toBe("Titel");
    expect(attributeLabel(spec(), "en")).toBe("Title");
  });

  it("never falls back to the raw attribute name when a label is missing", () => {
    // #1090: the field name is not a label. A missing translation is a catalog
    // data error and must surface as one instead of rendering "title".
    expect(attributeLabel(spec({ label: { de: "", en: "" } }), "de")).toBe("[de-Label fehlt]");
    expect(attributeLabel(spec({ label: { de: "", en: "" } }), "en")).toBe("[en label missing]");
    expect(attributeLabel(spec({ label: { de: "", en: "Title" } }), "de")).toBe("Title");
  });

  it("renders a text field and reports edits", () => {
    const onChange = vi.fn();
    render(
      <TextField
        attribute={spec()}
        value="a"
        onChange={onChange}
        disabled={false}
        testId="artifact-field-title"
      />
    );
    fireEvent.change(screen.getByTestId("artifact-field-title"), {
      target: { value: "b" },
    });
    expect(onChange).toHaveBeenCalledWith("b");
  });

  it("marks a required field with aria-required", () => {
    render(
      <TextField
        attribute={spec({ required: true })}
        value=""
        onChange={vi.fn()}
        disabled={false}
        testId="artifact-field-title"
      />
    );
    expect(screen.getByTestId("artifact-field-title")).toHaveAttribute(
      "aria-required",
      "true"
    );
  });

  it("associates server errors with the input via aria-describedby", () => {
    render(
      <TextField
        attribute={spec()}
        value=""
        onChange={vi.fn()}
        disabled={false}
        errors={["is required"]}
        testId="artifact-field-title"
      />
    );
    const input = screen.getByTestId("artifact-field-title");
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByRole("alert")).toHaveTextContent("is required");
    expect(input.getAttribute("aria-describedby")).toContain("artifact-field-title");
  });

  it("disables the control when disabled is set", () => {
    render(
      <TextArea
        attribute={spec({ type: "textarea" })}
        value=""
        onChange={vi.fn()}
        disabled
        testId="artifact-field-description"
      />
    );
    expect(screen.getByTestId("artifact-field-description")).toBeDisabled();
  });

  it("emits a number, not a string, from the number field", () => {
    const onChange = vi.fn();
    render(
      <NumberField
        attribute={spec({ type: "number", name: "effort" })}
        value={1}
        onChange={onChange}
        disabled={false}
        testId="artifact-field-effort"
      />
    );
    fireEvent.change(screen.getByTestId("artifact-field-effort"), {
      target: { value: "8" },
    });
    expect(onChange).toHaveBeenCalledWith(8);
  });

  it("emits null when the number field is cleared", () => {
    const onChange = vi.fn();
    render(
      <NumberField
        attribute={spec({ type: "number", name: "effort" })}
        value={1}
        onChange={onChange}
        disabled={false}
        testId="artifact-field-effort"
      />
    );
    fireEvent.change(screen.getByTestId("artifact-field-effort"), {
      target: { value: "" },
    });
    expect(onChange).toHaveBeenCalledWith(null);
  });

  it("emits a boolean from the toggle", () => {
    const onChange = vi.fn();
    render(
      <BooleanToggle
        attribute={spec({ type: "boolean", name: "suspect" })}
        value={false}
        onChange={onChange}
        disabled={false}
        testId="artifact-field-suspect"
      />
    );
    fireEvent.click(screen.getByTestId("artifact-field-suspect"));
    expect(onChange).toHaveBeenCalledWith(true);
  });

  it("keeps an unknown enum value instead of silently coercing to option 0", () => {
    // #274: a <select> shows option[0] for an unknown value, so Save would
    // downgrade a working configuration. The unknown value stays selectable.
    render(
      <EnumSelect
        attribute={spec({
          type: "enum",
          name: "category",
          options: [
            { value: "a", label_de: "A", label_en: "A" },
            { value: "b", label_de: "B", label_en: "B" },
          ],
        })}
        value="legacy"
        onChange={vi.fn()}
        disabled={false}
        testId="artifact-field-category"
      />
    );
    const select = screen.getByTestId("artifact-field-category") as HTMLSelectElement;
    expect(select.value).toBe("legacy");
    expect(screen.getByRole("option", { name: /legacy/ })).toBeInTheDocument();
  });

  it("toggles a value in and out of a multi-enum", () => {
    const onChange = vi.fn();
    render(
      <MultiEnum
        attribute={spec({
          type: "multi-enum",
          name: "tags",
          options: [
            { value: "a", label_de: "A", label_en: "A" },
            { value: "b", label_de: "B", label_en: "B" },
          ],
        })}
        value={["a"]}
        onChange={onChange}
        disabled={false}
        testId="artifact-field-tags"
      />
    );
    fireEvent.click(screen.getByTestId("artifact-field-tags-option-b"));
    expect(onChange).toHaveBeenCalledWith(["a", "b"]);
    fireEvent.click(screen.getByTestId("artifact-field-tags-option-a"));
    expect(onChange).toHaveBeenCalledWith([]);
  });

  // Fix F1 (#1192 follow-up): a multi-enum can be definition-`required: false`
  // yet demanded by the active preset's approval gate (`is_required: true`, the
  // canonical case is `acceptance_criteria`/`stakeholder`). The group must
  // announce the *effective* flag — FieldShell/EnumSelect already do; the old
  // manual `attribute.required` on this group did not.
  it("announces a gate-required multi-enum as required", () => {
    render(
      <MultiEnum
        attribute={spec({
          type: "multi-enum",
          name: "stakeholder",
          required: false,
          is_required: true,
          options: [
            { value: "customer", label_de: "Kunde", label_en: "Customer" },
          ],
        })}
        value={[]}
        onChange={vi.fn()}
        disabled={false}
        testId="artifact-field-stakeholder"
      />
    );
    expect(screen.getByTestId("artifact-field-stakeholder")).toHaveAttribute(
      "aria-required",
      "true"
    );
  });

  it("keeps a definition-optional, non-gated multi-enum announced as not required", () => {
    render(
      <MultiEnum
        attribute={spec({
          type: "multi-enum",
          name: "tags",
          required: false,
          options: [{ value: "a", label_de: "A", label_en: "A" }],
        })}
        value={[]}
        onChange={vi.fn()}
        disabled={false}
        testId="artifact-field-tags"
      />
    );
    expect(screen.getByTestId("artifact-field-tags")).toHaveAttribute(
      "aria-required",
      "false"
    );
  });

  it("links a multi-enum group to its validation error via aria-describedby", () => {
    render(
      <MultiEnum
        attribute={spec({
          type: "multi-enum",
          name: "tags",
          options: [{ value: "a", label_de: "A", label_en: "A" }],
        })}
        value={[]}
        onChange={vi.fn()}
        disabled={false}
        errors={["ist erforderlich"]}
        testId="artifact-field-tags"
      />
    );
    expect(screen.getByTestId("artifact-field-tags")).toHaveAttribute(
      "aria-describedby",
      "artifact-field-tags-error"
    );
    // The error node is owned by `FieldShell` (no testid of its own); resolve it
    // by the id the group now points at.
    expect(document.getElementById("artifact-field-tags-error")).toHaveTextContent(
      "ist erforderlich"
    );
  });

  it("uses a native date input", () => {
    render(
      <DateField
        attribute={spec({ type: "date", name: "due_date" })}
        value="2026-09-04"
        onChange={vi.fn()}
        disabled={false}
        testId="artifact-field-due_date"
      />
    );
    expect(screen.getByTestId("artifact-field-due_date")).toHaveAttribute(
      "type",
      "date"
    );
  });
});
