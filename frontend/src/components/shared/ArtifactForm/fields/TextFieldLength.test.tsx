/**
 * #1282 — definition-bounded text fields mirror the limit and show proximity.
 *
 * Pins the two halves of the contract on the real field components (not just
 * the counter): `maxLength` comes from `attribute.validation.length`, and the
 * counter appears only once the value is at 80%+ of it.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { AttributeSpec } from "../../../../api/attribute-definitions";
import { TextArea } from "./TextArea";
import { TextField } from "./TextField";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ i18n: { language: "de" }, t: (k: string) => k }),
}));

function spec(overrides: Partial<AttributeSpec> = {}): AttributeSpec {
  return {
    name: "description",
    kind: "core",
    type: "textarea",
    widget_key: null,
    fields: [],
    options: [],
    required: false,
    visible: true,
    locked: false,
    editable: true,
    section: "basic",
    order: 10,
    label: { de: "Beschreibung", en: "Description" },
    help_text: { de: "", en: "" },
    default: null,
    validation: {},
    ai_elicit: false,
    export: true,
    audience: "basic",
    ...overrides,
  };
}

describe("definition-bounded text fields (#1282)", () => {
  it("mirrors validation.length onto the input's maxLength", () => {
    render(
      <TextField
        attribute={spec({ validation: { length: 300 } })}
        value=""
        onChange={vi.fn()}
        disabled={false}
        testId="artifact-field-description"
      />,
    );
    expect(screen.getByTestId("artifact-field-description")).toHaveAttribute(
      "maxlength",
      "300",
    );
  });

  it("shows the counter at 80% of the limit on a textarea", () => {
    render(
      <TextArea
        attribute={spec({ validation: { length: 100 } })}
        value={"a".repeat(85)}
        onChange={vi.fn()}
        disabled={false}
        testId="artifact-field-description"
      />,
    );
    expect(screen.getByTestId("artifact-field-description-length")).toHaveTextContent(
      "85 / 100",
    );
  });

  it("shows no counter for an unbounded field", () => {
    render(
      <TextField
        attribute={spec({ validation: {} })}
        value={"a".repeat(5000)}
        onChange={vi.fn()}
        disabled={false}
        testId="artifact-field-description"
      />,
    );
    expect(
      screen.queryByTestId("artifact-field-description-length"),
    ).not.toBeInTheDocument();
  });
});
