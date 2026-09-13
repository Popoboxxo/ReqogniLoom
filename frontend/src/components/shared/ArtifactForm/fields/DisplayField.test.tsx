/**
 * <DisplayField> accessibility tests (Attribut v3 WS3, #937).
 *
 * The display path renders no labelable control, so `FieldShell`'s usual
 * `<label htmlFor>` used to point at a non-focusable `<span>`. These tests pin
 * the replacement contract: the label text is associated with the value through
 * `aria-labelledby`, and help/error through `aria-describedby`.
 */

import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown>) => {
      const { defaultValue, ...interpolation } = options ?? {};
      const resolved = typeof defaultValue === "string" ? defaultValue : key;
      return Object.entries(interpolation).reduce(
        (acc, [name, value]) => acc.replace(`{{${name}}}`, String(value)),
        resolved
      );
    },
    i18n: { language: "de" },
  }),
}));

import { DisplayField } from "./DisplayField";
import type { AttributeSpec } from "../../../../api/attribute-definitions";

function spec(over: Partial<AttributeSpec> = {}): AttributeSpec {
  return {
    name: "uid",
    kind: "core",
    type: "text",
    widget_key: null,
    fields: [],
    options: [],
    required: false,
    visible: true,
    locked: false,
    editable: "system",
    section: "general",
    order: 0,
    label: { de: "ID", en: "ID" },
    help_text: { de: "", en: "" },
    default: null,
    validation: {},
    ai_elicit: false,
    export: false,
    audience: "basic",
    reveal: "click",
    copyable: true,
    mask: "short",
    ...over,
  };
}

describe("DisplayField accessibility (WS3 #937)", () => {
  it("associates the label via aria-labelledby, not a dead htmlFor", () => {
    render(
      <DisplayField
        attribute={spec()}
        value="12345678-1234-4abc-8def-1234567890ab"
        testId="artifact-field-uid"
      />
    );
    const root = screen.getByTestId("artifact-field-uid");
    expect(root).toHaveAttribute("role", "group");
    expect(root).toHaveAttribute("aria-labelledby", "artifact-field-uid-label");
    // The label text is not a `<label htmlFor>` pointing at a non-labelable span.
    const label = document.getElementById("artifact-field-uid-label");
    expect(label?.tagName).toBe("SPAN");
    expect(label).toHaveTextContent("ID");
  });

  it("wires help and error text through aria-describedby", () => {
    render(
      <DisplayField
        attribute={spec({ help_text: { de: "Die ID.", en: "The id." } })}
        value="x"
        errors={["kaputt"]}
        testId="artifact-field-uid"
      />
    );
    expect(
      screen.getByTestId("artifact-field-uid").getAttribute("aria-describedby")
    ).toBe("artifact-field-uid-help artifact-field-uid-error");
  });
});
