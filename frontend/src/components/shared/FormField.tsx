/**
 * The single field primitive for the hand-written create dialogs — and the
 * single required/error renderer shared with `ArtifactForm`.
 *
 * WHY THIS EXISTS (GitHub #1393 / #1392)
 * --------------------------------------
 * The required marker and the `maxlength` mirror already worked inside
 * `ArtifactForm` — `FieldShell` renders from the attribute definition and
 * `TextField`/`TextArea` copy `validation.length` onto the control. The defect
 * was the seam: 9 of the 11 artifact routes have bespoke create dialogs that
 * render labels and raw `<input>`s by hand and never consult that definition,
 * so the behaviour had to be re-invented (and was not) on every route.
 *
 * The abstraction is deliberately small because the dialogs differ in layout
 * and CSS module: `FormField` owns the label -> control association, the
 * visible required marker and the field-bound error text; `useFieldContract`
 * (see `hooks/useFieldContract.ts`) owns *which* fields are required and how
 * long they may be. A dialog renders
 *
 *     <FormField htmlFor="adr-new-title" label={...} required={title.required} error={errors.title}>
 *       <input id="adr-new-title" {...title.controlProps} />
 *     </FormField>
 *
 * and a newly added dialog inherits both behaviours by construction.
 *
 * `FormField` renders a FRAGMENT, not a wrapper element: the create-dialog DOM
 * shape (and every E2E locator built on it) must not change. Only the marker
 * and the error node are additive.
 *
 * The marker is a real DOM node on purpose. Both the previous implementations
 * put `content: " *"` in a CSS `::after`, which is invisible to `textContent`
 * — that is exactly how #1393's "no visible marker" finding survived review.
 */

import {
  Children,
  cloneElement,
  isValidElement,
  type ReactElement,
  type ReactNode,
} from "react";

import styles from "./FieldHints.module.css";

/**
 * The required marker. `aria-hidden` because the *control* carries the
 * machine-readable flag (`aria-required` / `required`) — announcing a bare
 * asterisk would only add noise to the accessible name.
 */
export function RequiredMark(): JSX.Element {
  return (
    <span className={styles.requiredMarker} data-required-marker="true" aria-hidden="true">
      {"*"}
    </span>
  );
}

export interface FormFieldProps {
  /** `id` of the control this label describes. */
  htmlFor: string;
  /** Already-translated label text. */
  label: string;
  /** Renders the marker when true. Comes from `useFieldContract`. */
  required: boolean;
  /**
   * Server-side message for THIS field (`details[].field` matched). Shown as a
   * `role="alert"` paragraph directly under the control, so a rejected save
   * says what is wrong where it is wrong instead of only in the banner
   * (issue #1392's second half, #977's finding applied to the create dialogs).
   */
  error?: string | null;
  /** The host dialog's own label class (each route has its own layout). */
  labelClassName?: string;
  /** The control. */
  children: ReactNode;
}

export function FormField({
  htmlFor,
  label,
  required,
  error,
  labelClassName,
  children,
}: FormFieldProps): JSX.Element {
  const errorId = `${htmlFor}-error`;
  return (
    <>
      <label htmlFor={htmlFor} className={labelClassName}>
        {/* Text and marker share ONE inline wrapper. A host label class may be a
            `flex-direction: column` container (e.g. `DiagramCreateForm`'s
            `.label` wraps label+control that way); without the wrapper the
            marker becomes a second flex item and renders as a lone `*` on the
            line BELOW the label text. */}
        <span>
          {label}
          {required ? <RequiredMark /> : null}
        </span>
      </label>
      {associateError(children, error ? errorId : null)}
      <FieldErrorText error={error} testId={errorId} />
    </>
  );
}

/**
 * GitHub #1393/#1392 follow-up: the error text is rendered with
 * `role="alert"`, which announces it ONCE — a user who tabs away and back to
 * the control gets nothing, because nothing links the control to the message.
 * `FieldShell` solves that with `ariaProps` (`aria-describedby` +
 * `aria-invalid`); this is the same wiring for the hand-written dialogs.
 *
 * Deliberately tolerant: the control is the caller's own element and there are
 * callers that pass more than one node, so anything that is not exactly one
 * valid element is returned untouched instead of throwing. An
 * `aria-describedby` the caller already set is preserved (the error id is
 * appended), and with no error NOTHING is added — `aria-invalid` must not
 * appear on a healthy field.
 */
type ErrorBoundProps = {
  "aria-describedby"?: string;
  "aria-invalid"?: boolean | "true" | "false";
};

function associateError(children: ReactNode, errorId: string | null): ReactNode {
  if (errorId === null) return children;
  if (Children.count(children) !== 1 || !isValidElement(children)) return children;
  const element = children as ReactElement<ErrorBoundProps>;
  const existing = element.props["aria-describedby"];
  const describedBy =
    typeof existing === "string" && existing.length > 0
      ? existing.split(/\s+/).includes(errorId)
        ? existing
        : `${existing} ${errorId}`
      : errorId;
  return cloneElement(element, {
    "aria-describedby": describedBy,
    "aria-invalid": true,
  });
}

export interface FieldErrorTextProps {
  error?: string | null;
  /** `data-testid` of the message (`<control id>-error` by default). */
  testId: string;
  /**
   * DOM `id` of the message. Defaults to `testId` — the conventional
   * `<control id>-error` — so a control's `aria-describedby` can point at it
   * without the host repeating the string.
   */
  id?: string;
  /** The host's own error class (`FieldShell` keeps its `ArtifactForm` rules). */
  className?: string;
}

/** The one renderer for a field-bound error, used by `FormField` and `FieldShell`. */
export function FieldErrorText({
  error,
  testId,
  id,
  className,
}: FieldErrorTextProps): JSX.Element | null {
  if (!error) return null;
  return (
    <p
      role="alert"
      // `role="alert"` is the standard assertive live region, but older
      // Safari/VoiceOver only honours an explicit `aria-live` — the markup
      // carried `aria-live="assertive"` before this component existed and it
      // is kept alongside the role for that reason.
      aria-live="assertive"
      id={id ?? testId}
      data-testid={testId}
      className={className ?? styles.fieldError}
    >
      {error}
    </p>
  );
}
