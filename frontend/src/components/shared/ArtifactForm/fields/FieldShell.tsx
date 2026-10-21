/**
 * Shared chrome for every definition-driven field: label, required marker,
 * help text and the server-side error list, wired for accessibility.
 *
 * Every field component renders its control inside this shell so label/error
 * association is implemented once instead of eight times.
 */

import type { ReactNode } from "react";

import type { AttributeOption, AttributeSpec } from "../../../../api/attribute-definitions";
import { isEffectiveRequired } from "../../../../utils/attributeRequired";
import { FieldErrorText, RequiredMark } from "../../FormField";
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

/**
 * Visible data-error marker for an attribute that has NO label at all (#1090).
 *
 * Rendered instead of the label, never alongside it, and never mixed with the
 * raw field name — a raw field name reads as a perfectly normal label, which is
 * exactly how the German label gap stayed invisible for so long. The brackets
 * and the wording are deliberate: the string must not be mistakable for
 * product copy, and it must name the LANGUAGE whose label is missing, because
 * the gap is per-locale data.
 *
 * Deliberately NOT an i18n resource: it is a report about broken data, not a
 * translatable string — a localized version of it would hide the defect behind
 * plausible UI copy in every locale but the one an operator happens to read.
 *
 * No emoji/pictograph: this file is scanned by the `emoji-as-ui-glyph` ratchet
 * check (`src/test/design-system-ratchet.test.ts`).
 */
function missingLabelMarker(language: string): string {
  return language.startsWith("de") ? "[de-Label fehlt]" : "[en label missing]";
}

/**
 * True when the label chain fell through to the data-error marker for
 * *this* language, i.e. neither the localized label nor the ``label.en``
 * fallback exists.
 *
 * Exposed so the caller can mark the rendered label element (a `title` naming
 * the offending attribute plus a `data-` flag) without changing
 * :func:`attributeLabel`'s `string` return type — `ArtifactForm.tsx` and
 * `DisplayField.tsx` both consume it and are outside this change's file scope.
 */
export function hasLabelDataGap(attribute: AttributeSpec, language: string): boolean {
  const localized = language.startsWith("de")
    ? attribute.label?.de
    : attribute.label?.en;
  return !localized && !attribute.label?.en;
}

/**
 * The definition label for the active language, as a THREE-step chain:
 *
 *   1. `label[lang]`  — the localized label
 *   2. `label.en`     — the English label
 *   3. a visible data-error marker
 *
 * The field name is NOT in that chain. It used to be the final fallback, which
 * made a missing label indistinguishable from a correctly-labelled field whose
 * name happens to be a word — a German workspace rendered "level"/"title"/
 * "description"/"uid" and nothing anywhere said the data was broken. Step 3
 * exists so the NEXT such gap is visible at the point of use instead of silent.
 *
 * The backend data is fixed (#1090 shipped 47 German core-attribute labels), so
 * the normal path never reaches step 3.
 */
export function attributeLabel(attribute: AttributeSpec, language: string): string {
  const localized = language.startsWith("de") ? attribute.label?.de : attribute.label?.en;
  if (localized) return localized;
  if (attribute.label?.en) return attribute.label.en;
  return missingLabelMarker(language);
}

export function optionLabel(option: AttributeOption, language: string): string {
  const localized = language.startsWith("de") ? option.label_de : option.label_en;
  return localized || option.value;
}

export function helpText(attribute: AttributeSpec, language: string): string {
  return (language.startsWith("de")
    ? attribute.help_text?.de
    : attribute.help_text?.en) ?? "";
}

interface FieldShellProps {
  attribute: AttributeSpec;
  language: string;
  errors?: string[];
  testId: string;
  /**
   * `false` when the child is not a labelable control (e.g. the read-only
   * `<RevealValue>` display): a `<label htmlFor>` would point at a non-focusable
   * `<span>` and do nothing. In that case the label text renders as a plain
   * element with the same `id`, so the display path can associate it via
   * `aria-labelledby` instead.
   */
  associateLabel?: boolean;
  /**
   * `true` when no editable control follows (`DisplayField`'s read-only
   * `<RevealValue>`). The `*` marker is then suppressed: it would announce a
   * required state no control carries.
   */
  readOnly?: boolean;
  children: ReactNode;
}

export function FieldShell({
  attribute,
  language,
  errors,
  testId,
  associateLabel = true,
  readOnly = false,
  children,
}: FieldShellProps): JSX.Element {
  const help = helpText(attribute, language);
  const isRequired = isEffectiveRequired(attribute);
  // Issue #1393: the marker used to be `content: " *"` on `.required`, i.e. a
  // CSS pseudo-element that no `textContent` and no measurement tool can see —
  // which is how "no visible marker" stayed invisible. It is now the SAME
  // `<RequiredMark>` node the hand-written create dialogs render. The
  // `.required` class stays on the label as the styling/query hook it always
  // was (`ArtifactForm.test.tsx` pins it); it no longer draws anything itself.
  const labelClassName = `${styles.label} ${isRequired ? styles.required : ""}`;
  // #1090 follow-up: when the label chain fell through to the data-error
  // marker, the raw field name is moved into the element's `title` — the
  // attribute an operator has to look up — and flagged via `data-label-gap`, so
  // the defect is identifiable in devtools and on hover WITHOUT the name ever
  // being rendered as the visible label text.
  const labelGap = hasLabelDataGap(attribute, language);
  const labelText = attributeLabel(attribute, language);
  // Only an editable control can carry required semantics; in the read-only
  // path the marker would be a glyph with no programmatic counterpart.
  const showRequiredMark = isRequired && !readOnly;
  const labelProps = labelGap
    ? { "data-label-gap": "true" as const, title: attribute.name }
    : {};
  return (
    <div className={styles.field}>
      {associateLabel ? (
        <label
          className={labelClassName}
          htmlFor={testId}
          id={`${testId}-label`}
          {...labelProps}
        >
          {labelText}
          {showRequiredMark ? <RequiredMark /> : null}
        </label>
      ) : (
        <span className={labelClassName} id={`${testId}-label`} {...labelProps}>
          {labelText}
          {showRequiredMark ? <RequiredMark /> : null}
        </span>
      )}
      {children}
      {help ? (
        <span className={styles.help} id={`${testId}-help`}>
          {help}
        </span>
      ) : null}
      {errors?.length ? (
        // GitHub #677: server-side validation messages appear only after a
        // rejected save, i.e. purely dynamically. Assertive live region so the
        // reason a save was refused is announced instead of only turning red.
        // Issue #1393 (follow-up): the node itself is the shared
        // `FieldErrorText` — one renderer for every field error in the app, so
        // the `role="alert"` + `data-testid` + `id` contract cannot drift
        // between `ArtifactForm` and the hand-written create dialogs.
        <FieldErrorText
          error={errors.join(", ")}
          testId={`${testId}-error`}
          className={styles.errors}
        />
      ) : null}
    </div>
  );
}

/**
 * The effective requiredness of one attribute.
 *
 * GitHub #1192: the marker/`aria-required` reflect the *effective* approval
 * gate too — a field can be definition-`required: false` yet demanded by Rule 5
 * (e.g. `acceptance_criteria` under the standard/extended preset). Other
 * `required`-driven behaviours (create-mode expansion, enum "none" option,
 * ActorPicker clearing) intentionally stay definition-only.
 *
 * Issue #1393 (follow-up): a native control must also carry the native
 * `required` flag — `aria-required` alone is not what `:required` styling and
 * the browser's own constraint state read. `ArtifactForm` is `noValidate`, so
 * the flag adds the semantics without the browser bubble pre-empting the
 * app's error flow.
 *
 * The predicate itself lives in `utils/attributeRequired` so
 * `hooks/useFieldContract` (the create dialogs) uses the same one; re-exported
 * here because every field widget imports it from the shell.
 */
export { isEffectiveRequired };

/** ARIA wiring shared by every control inside a `FieldShell`. */
export interface AriaPropsOptions {
  /**
   * `true` for a `role="group"` container. ARIA 1.2 does not support
   * `aria-required` on `group` (AT ignores it), so the flag is left off there
   * and the required state is carried by the group's accessible name instead —
   * see `MultiEnum`/`CriteriaList`, which add a visually-hidden
   * `"${testId}-required"` word to `aria-labelledby`.
   */
  groupContainer?: boolean;
}

export function ariaProps(
  attribute: AttributeSpec,
  testId: string,
  errors?: string[],
  options: AriaPropsOptions = {}
): Record<string, string | boolean | undefined> {
  const described = [
    helpText(attribute, "en") || helpText(attribute, "de") ? `${testId}-help` : null,
    errors?.length ? `${testId}-error` : null,
  ].filter(Boolean);
  return {
    "aria-required": options.groupContainer
      ? undefined
      : isEffectiveRequired(attribute),
    "aria-invalid": Boolean(errors?.length),
    "aria-describedby": described.length ? described.join(" ") : undefined,
  };
}
