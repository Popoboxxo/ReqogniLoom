/**
 * Shared chrome for every definition-driven field: label, required marker,
 * help text and the server-side error list, wired for accessibility.
 *
 * Every field component renders its control inside this shell so label/error
 * association is implemented once instead of eight times.
 */

import type { ReactNode } from "react";

import type { AttributeOption, AttributeSpec } from "../../../../api/attribute-definitions";
import styles from "../ArtifactForm.module.css";

export interface FieldProps<T = unknown> {
  attribute: AttributeSpec;
  value: T;
  onChange: (next: T) => void;
  disabled: boolean;
  /** Server-side validation messages for this attribute, if any. */
  errors?: string[];
  /** Stable `data-testid` for the control itself: `artifact-field-<name>`. */
  testId: string;
}

/** Definition label for the active language, falling back to the raw name. */
export function attributeLabel(attribute: AttributeSpec, language: string): string {
  const localized = language.startsWith("de") ? attribute.label.de : attribute.label.en;
  return localized || attribute.name;
}

export function optionLabel(option: AttributeOption, language: string): string {
  const localized = language.startsWith("de") ? option.label_de : option.label_en;
  return localized || option.value;
}

export function helpText(attribute: AttributeSpec, language: string): string {
  return language.startsWith("de") ? attribute.help_text.de : attribute.help_text.en;
}

interface FieldShellProps {
  attribute: AttributeSpec;
  language: string;
  errors?: string[];
  testId: string;
  children: ReactNode;
}

export function FieldShell({
  attribute,
  language,
  errors,
  testId,
  children,
}: FieldShellProps): JSX.Element {
  const help = helpText(attribute, language);
  return (
    <div className={styles.field}>
      <label
        className={`${styles.label} ${attribute.required ? styles.required : ""}`}
        htmlFor={testId}
      >
        {attributeLabel(attribute, language)}
      </label>
      {children}
      {help ? (
        <span className={styles.help} id={`${testId}-help`}>
          {help}
        </span>
      ) : null}
      {errors?.length ? (
        <span className={styles.errors} id={`${testId}-error`} role="alert">
          {errors.join(", ")}
        </span>
      ) : null}
    </div>
  );
}

/** ARIA wiring shared by every control inside a `FieldShell`. */
export function ariaProps(
  attribute: AttributeSpec,
  testId: string,
  errors?: string[]
): Record<string, string | boolean | undefined> {
  const described = [
    helpText(attribute, "en") || helpText(attribute, "de") ? `${testId}-help` : null,
    errors?.length ? `${testId}-error` : null,
  ].filter(Boolean);
  return {
    "aria-required": attribute.required,
    "aria-invalid": Boolean(errors?.length),
    "aria-describedby": described.length ? described.join(" ") : undefined,
  };
}
