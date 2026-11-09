/**
 * #1732 — submit-time required-field validation for the create/edit dialogs.
 *
 * The defect: 18 dialogs disabled their submit button while a required field
 * was empty (`disabled={isSubmitting || !title.trim()}`). A disabled control
 * with no stated reason is exactly the "accessible, but unexplained refusal"
 * class of bug — the user sees a greyed-out button, no message, and no hint
 * about which of the five fields is the problem. The already-correct
 * `/glossary` dialog did the opposite: keep the button active, validate on
 * click, mark the offending control and move focus there.
 *
 * This hook is the small shared piece of that pattern. It deliberately does
 * **not** introduce a form library: the repo's dialogs are hand-written
 * `<form>`s with their own CSS modules, `FormField` already owns label/error
 * rendering (including `role="alert"` and the `aria-describedby` wiring), and
 * a schema library would be a much larger change than the defect warrants.
 *
 * Usage:
 *
 * ```tsx
 * const { errors, validate, focusFirstInvalid, clearError } = useRequiredValidation();
 * const fields = [
 *   { name: 'title', value: title, inputId: 'goal-title' },
 * ];
 *
 * <button
 *   type="submit"
 *   disabled={isSubmitting}
 *   onClick={(event) => {
 *     const invalid = validate(fields);
 *     if (invalid.length > 0) {
 *       event.preventDefault();
 *       focusFirstInvalid(fields, invalid);
 *     }
 *   }}
 * >
 *
 * <FormField … error={errors.title}>
 *   <input id="goal-title" onChange={() => clearError('title')} … />
 * </FormField>
 * ```
 *
 * `FormField` already renders the message with `role="alert"` and adds
 * `aria-invalid`/`aria-describedby` to the control, so a caller that uses it
 * needs nothing else for the ARIA side. Callers with a hand-rolled control
 * (no `FormField`) wire `aria-invalid`/`aria-describedby` themselves — see
 * `fieldProps` below.
 */
import { useCallback, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

/** One field the submit click must check. */
export interface RequiredField {
  /** Stable key; also the default DOM id used for focus. */
  name: string;
  /** Current value. Strings are trimmed; `null`/`undefined`/`[]` count as empty. */
  value: unknown;
  /** DOM id of the control when it differs from `name`. */
  inputId?: string;
  /** Per-field message override (default: `validation.required`). */
  message?: string;
  /**
   * Optional extra predicate for values that are present but malformed (e.g. a
   * fractional count). `false` reports *this* field with `message` — the same
   * click-time channel as an empty required field, so the dialog needs one
   * validation path rather than a second ad-hoc one.
   */
  isValid?: boolean;
}

export interface RequiredValidation {
  /** field name -> message; empty while nothing was rejected. */
  errors: Record<string, string>;
  /**
   * Check `fields` and store the messages.
   *
   * Returns the invalid field names so the click handler can decide without
   * reading state: an `await`/`setState` boundary inside the same handler
   * would still see the previous `errors` value.
   */
  validate: (fields: readonly RequiredField[]) => readonly string[];
  /**
   * Move focus (and scroll) to the first invalid control.
   *
   * `invalid` defaults to the currently stored `errors`; the click handler
   * should pass the array `validate()` just returned, for the reason above.
   */
  focusFirstInvalid: (fields: readonly RequiredField[], invalid?: readonly string[]) => void;
  /** Drop one field's message (or all of them when called without a name). */
  clearError: (name?: string) => void;
  /**
   * ARIA wiring for a hand-rolled control (one that does not go through
   * `FormField`). Spread it onto the control.
   */
  fieldProps: (name: string) => {
    "aria-invalid": true | undefined;
    "aria-describedby": string | undefined;
  };
  /** DOM id of the rendered message (`<name>-required-error`). */
  errorId: (name: string) => string;
}

const NO_ERRORS: Record<string, string> = {};

function isBlank(value: unknown): boolean {
  if (value === null || value === undefined) return true;
  if (typeof value === "string") return value.trim().length === 0;
  if (Array.isArray(value)) return value.length === 0;
  return false;
}

export function useRequiredValidation(): RequiredValidation {
  const { t } = useTranslation();
  const [errors, setErrors] = useState<Record<string, string>>(NO_ERRORS);

  const requiredMessage = t("validation.required", "This field is required.");

  const validate = useCallback(
    (fields: readonly RequiredField[]): readonly string[] => {
      const next: Record<string, string> = {};
      for (const field of fields) {
        if (isBlank(field.value) || field.isValid === false) {
          next[field.name] = field.message ?? requiredMessage;
        }
      }
      setErrors(next);
      return Object.keys(next);
    },
    [requiredMessage],
  );

  const errorId = useCallback((name: string): string => `${name}-required-error`, []);

  const focusFirstInvalid = useCallback(
    (fields: readonly RequiredField[], invalid?: readonly string[]): void => {
      const names = invalid ?? Object.keys(errors);
      const first = fields.find((field) => names.includes(field.name));
      if (!first) return;
      const element = document.getElementById(first.inputId ?? first.name);
      if (!element) return;
      element.focus();
      element.scrollIntoView?.({ block: "nearest" });
    },
    [errors],
  );

  const clearError = useCallback((name?: string): void => {
    setErrors((previous) => {
      if (name === undefined) {
        return Object.keys(previous).length === 0 ? previous : NO_ERRORS;
      }
      if (!(name in previous)) return previous;
      const next = { ...previous };
      delete next[name];
      return next;
    });
  }, []);

  const fieldProps = useMemo(
    () =>
      (name: string) => ({
        "aria-invalid": errors[name] ? (true as const) : undefined,
        "aria-describedby": errors[name] ? errorId(name) : undefined,
      }),
    [errors, errorId],
  );

  return { errors, validate, focusFirstInvalid, clearError, fieldProps, errorId };
}
