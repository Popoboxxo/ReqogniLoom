/**
 * #1282 — live length feedback for definition-bounded text fields.
 *
 * `TextField`/`TextArea` already mirror the attribute definition's
 * `validation.length` onto the control's `maxLength`, so the browser stops the
 * user at the boundary. That is invisible until the boundary is hit, though:
 * a long description simply stops accepting characters with no indication how
 * close to the limit the text was, and a save rejected by a *backend* length
 * rule gives no way to see the overage. This renders `used / max` once the
 * value reaches 80% of its limit.
 *
 * Deliberately rendered from the definition, never a hardcoded constant: an
 * unbounded attribute (`validation.length` unset) shows nothing, so the
 * counter can never claim a limit the backend does not enforce.
 */

import styles from "../ArtifactForm.module.css";

interface LengthFeedbackProps {
  /** Current field value; `null` is treated as empty. */
  value: string | null;
  /** Definition limit. `undefined`/non-positive means "unbounded" → no counter. */
  maxLength?: number;
  /** Same test id as the control, suffixed with `-length`. */
  testId: string;
}

/** Fraction of the limit at which the counter appears. */
const VISIBILITY_THRESHOLD = 0.8;

export function LengthFeedback({
  value,
  maxLength,
  testId,
}: LengthFeedbackProps): JSX.Element | null {
  if (typeof maxLength !== "number" || maxLength <= 0) return null;
  const length = (value ?? "").length;
  if (length < Math.ceil(maxLength * VISIBILITY_THRESHOLD)) return null;

  return (
    <span
      data-testid={`${testId}-length`}
      aria-live="polite"
      className={`${styles.lengthFeedback} ${
        length >= maxLength ? styles.lengthFeedbackAtLimit : ""
      }`}
    >
      {length} / {maxLength}
    </span>
  );
}
