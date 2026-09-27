/**
 * Label-render rule for definition-driven fields (GitHub #1090 follow-up).
 *
 * The rule the UI must never break: **a raw field name is never rendered as a
 * label.** The chain is `label[lang]` -> `label.en` -> a visible data-error
 * marker. The field name used to be the last link, which made a missing label
 * indistinguishable from a correctly-labelled field — a German workspace showed
 * "level"/"title"/"uid" and nothing anywhere said the data was broken.
 *
 * Both branches are pinned:
 *   * the NORMAL branch (labels present) — the localized label wins;
 *   * the DATA-GAP branch (no label in any locale) — a visible marker renders,
 *     the field name is not in the visible text, and the name is still
 *     discoverable for an operator via `title` / `data-label-gap`.
 *
 * The de-partial case (only `label.en` present) is pinned too: the chain says
 * `label.en` is a legitimate step, so it must render, not the marker.
 */

import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import type { AttributeSpec } from "../../../../api/attribute-definitions";
import { attributeLabel, FieldShell, hasLabelDataGap } from "./FieldShell";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ i18n: { language: "de" }, t: (k: string) => k }),
}));

function spec(overrides: Partial<AttributeSpec> = {}): AttributeSpec {
  return {
    name: "level",
    kind: "core",
    type: "text",
    widget_key: null,
    fields: [],
    options: [],
    required: false,
    visible: true,
    locked: false,
    editable: true,
    section: "classification",
    order: 10,
    label: { de: "Ebene", en: "Level" },
    help_text: { de: "", en: "" },
    default: null,
    validation: {},
    ai_elicit: false,
    export: true,
    audience: "basic",
    ...overrides,
  };
}

describe("attributeLabel", () => {
  it("uses the localized label for the active language", () => {
    expect(attributeLabel(spec(), "de")).toBe("Ebene");
    expect(attributeLabel(spec(), "de-DE")).toBe("Ebene");
  });

  it("uses the English label for an English locale", () => {
    expect(attributeLabel(spec(), "en")).toBe("Level");
    expect(attributeLabel(spec(), "en-GB")).toBe("Level");
  });

  it("falls back to label.en when the German label is missing", () => {
    const germanGap = spec({ label: { de: "", en: "Level" } });

    expect(attributeLabel(germanGap, "de")).toBe("Level");
    // A de-only gap is NOT a data gap: `en` is a documented step in the chain.
    expect(hasLabelDataGap(germanGap, "de")).toBe(false);
  });

  it("renders a visible data-error marker when no locale has a label", () => {
    const noLabels = spec({ label: { de: "", en: "" } });

    expect(attributeLabel(noLabels, "de")).toBe("[de-Label fehlt]");
    expect(attributeLabel(noLabels, "en")).toBe("[en label missing]");
    expect(hasLabelDataGap(noLabels, "de")).toBe(true);
  });

  it("never returns the raw field name", () => {
    for (const labels of [
      { de: "", en: "" },
      { de: "", en: "Level" },
      { de: "Ebene", en: "" },
    ]) {
      for (const language of ["de", "en"]) {
        expect(attributeLabel(spec({ label: labels }), language)).not.toBe("level");
      }
    }
  });
});

describe("FieldShell label rendering", () => {
  it("renders the localized label and no data-gap marker", () => {
    render(
      <FieldShell attribute={spec()} language="de" testId="artifact-field-level">
        <input id="artifact-field-level" />
      </FieldShell>,
    );

    const label = screen.getByText("Ebene");
    expect(label).toBeInTheDocument();
    expect(label).not.toHaveAttribute("data-label-gap");
  });

  it("renders the data-error marker instead of the field name", () => {
    const noLabels = spec({ label: { de: "", en: "" } });

    render(
      <FieldShell attribute={noLabels} language="de" testId="artifact-field-level">
        <input id="artifact-field-level" />
      </FieldShell>,
    );

    const label = screen.getByText("[de-Label fehlt]");
    expect(label.tagName).toBe("LABEL");
    // The raw field name must not be the visible label text...
    expect(label).not.toHaveTextContent("level");
    // ...but an operator still needs to know WHICH attribute is broken, so the
    // name rides on the element's title / data attributes instead.
    expect(label).toHaveAttribute("data-label-gap", "true");
    expect(label).toHaveAttribute("title", "level");
  });
});
