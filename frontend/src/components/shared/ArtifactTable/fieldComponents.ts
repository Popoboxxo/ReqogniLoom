/**
 * Task 4.4 — the single seam between the shared field library and the filter
 * UI (plan 2026-11-04-tabellenansicht-s4).
 *
 * The form field components (`ArtifactForm/fields/*`) are built around
 * `FieldProps` (definition + label shell + error list) and are a poor fit
 * inside a compact popover. The seam therefore declares which control a column
 * type maps to and how an option is labelled; the popover renders those
 * controls with the shared token-based classes. Nothing here duplicates
 * validation — the backend stays the authority.
 */

import type { AttributeOption, AttributeType } from "../../../api/attribute-definitions";
import type { FilterOperator } from "../../../api/table-views";

export type FilterControl =
  | "text"
  | "enum"
  | "number-range"
  | "date-range"
  | "boolean"
  | "reference";

export function filterControlFor(type: AttributeType): FilterControl | null {
  switch (type) {
    case "text":
    case "textarea":
      return "text";
    case "enum":
    case "multi-enum":
      return "enum";
    case "number":
      return "number-range";
    case "date":
      return "date-range";
    case "boolean":
      return "boolean";
    case "reference":
    case "user":
    case "actor":
      return "reference";
    default:
      return null;
  }
}

export function operatorForControl(control: FilterControl): FilterOperator | null {
  switch (control) {
    case "text":
      return "contains";
    case "enum":
    case "reference":
      return "in";
    case "boolean":
      return "eq";
    case "number-range":
    case "date-range":
      return null;
  }
}

export function optionLabel(option: AttributeOption, language: string): string {
  if (language.startsWith("de")) return option.label_de || option.label_en || option.value;
  return option.label_en || option.label_de || option.value;
}
