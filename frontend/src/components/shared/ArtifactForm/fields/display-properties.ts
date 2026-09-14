/**
 * Generic display/interaction property resolution (Attribut v3 WS3, #937).
 *
 * The backend normalizes `copyable`/`reveal`/`mask`/`display_format` onto
 * every attribute, but the frontend types mark them optional so pre-existing
 * `AttributeSpec` literals (fixtures, older tests) stay valid. This module is
 * the single place that applies the backend's documented defaults
 * (`attribute_definitions.schema._DEFAULTS`), so no renderer has to repeat
 * them and an attribute without special properties resolves to the exact
 * pre-WS3 rendering.
 */

import type {
  AttributeDisplayFormat,
  AttributeMask,
  AttributeReveal,
  AttributeSpec,
} from "../../../../api/attribute-definitions";
import { optionLabel } from "./FieldShell";

export interface ResolvedDisplayProps {
  copyable: boolean;
  reveal: AttributeReveal;
  mask: AttributeMask;
  displayFormat: AttributeDisplayFormat;
}

/** Resolve the four properties with the backend's own defaults. */
export function resolveDisplayProps(attribute: AttributeSpec): ResolvedDisplayProps {
  return {
    copyable: attribute.copyable ?? false,
    reveal: attribute.reveal ?? "always",
    mask: attribute.mask ?? "none",
    displayFormat: attribute.display_format ?? "text",
  };
}

/**
 * `true` when at least one display property deviates from the default — i.e.
 * the attribute needs the generic `<RevealValue>` treatment instead of its
 * ordinary control. An attribute without special properties returns `false`
 * and therefore renders exactly as it did before WS3.
 */
export function hasConfiguredDisplay(display: ResolvedDisplayProps): boolean {
  return (
    display.copyable ||
    display.reveal !== "always" ||
    display.mask !== "none" ||
    display.displayFormat !== "text"
  );
}

export interface FormattedAttributeValue {
  /** Plain-text rendering, used for `display_format: "text" | "mono"`. */
  text: string;
  /** Individual entries, used for `display_format: "chips"`. */
  chips: string[];
}

function formatScalar(
  attribute: AttributeSpec,
  value: unknown,
  language: string
): string {
  if (value == null || value === "") return "";
  if (attribute.type === "enum" || attribute.type === "multi-enum") {
    const raw = String(value);
    const option = attribute.options.find((entry) => entry.value === raw);
    return option ? optionLabel(option, language) : raw;
  }
  return String(value);
}

/**
 * Render any attribute value as text plus an optional list of chips. Lists
 * (`multi-enum`, repeated actors) become one chip per entry; everything else
 * becomes a single string. Enum values are mapped to their localized option
 * labels, mirroring the editable controls.
 */
export function formatAttributeValue(
  attribute: AttributeSpec,
  value: unknown,
  language: string
): FormattedAttributeValue {
  if (Array.isArray(value)) {
    const chips = value.map((entry) => formatScalar(attribute, entry, language));
    return { text: chips.join(", "), chips };
  }
  const text = formatScalar(attribute, value, language);
  return { text, chips: text ? [text] : [] };
}
