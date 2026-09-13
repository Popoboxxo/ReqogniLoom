/**
 * <RevealValue> (Attribut v3 WS3, #937) — generic value display engine.
 *
 * Implements the four generic display/interaction properties from the
 * implementation spec section 5 for **any** value, independent of the field
 * that produced it:
 *
 * - `reveal="always"`  — permanently visible (the default: an attribute
 *   without special properties renders exactly as it did before).
 * - `reveal="click"`   — the value starts behind a placeholder and is revealed
 *   by activating a focusable button.
 * - `reveal="shortcut"`— same, plus a documented keyboard shortcut
 *   (`Alt+Shift+R`). `event.code` is used (not `event.key`) so the shortcut
 *   works on keyboard layouts where Alt+Shift remaps the letter.
 * - `copyable`         — a copy button AND a double-click on the value copy
 *   the **full** value (`copyValue`), even when the label is masked.
 * - `mask="short"`     — the rendered label is shortened (e.g. a UUID to its
 *   first 8 characters); copying is unaffected.
 * - `display_format`   — purely visual: `text` | `mono` | `chips`.
 *
 * Accessibility baseline (not an audit verdict): semantic buttons, a visible
 * focus ring (global `:focus-visible`), a meaningful accessible name for every
 * control, `aria-live` announcements for reveal/copy, and a `data-testid` on
 * every interactive element. When `reveal` hides the value the copy control's
 * accessible name deliberately stays generic, so the full value is not leaked
 * to assistive technology before the user reveals it.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { ClipboardCopy, Eye, EyeOff } from "lucide-react";

import type {
  AttributeDisplayFormat,
  AttributeMask,
  AttributeReveal,
} from "../../api/attribute-definitions";
import styles from "./RevealValue.module.css";

export interface RevealValueProps {
  /**
   * The display value. When `mask="short"` and it is longer than
   * {@link SHORT_MASK_LENGTH}, only a shortened label is rendered.
   */
  value?: string | null;
  /** Rendered when `value` is empty, e.g. the first 8 chars of a UUID. */
  fallback?: string | null;
  /** The *full* value copied by the copy affordance, if it differs from the
   * (possibly masked) label. */
  copyValue?: string | null;
  reveal?: AttributeReveal;
  mask?: AttributeMask;
  copyable?: boolean;
  displayFormat?: AttributeDisplayFormat;
  /** Entries rendered as chips when `displayFormat="chips"`. */
  chips?: readonly string[] | null;
  /** Context noun for the copy control's accessible name, e.g. "Bezeichner". */
  label?: string;
  /** Suppresses the copy affordance (e.g. inside an already-clickable row). */
  readOnly?: boolean;
  testId?: string;
}

/** Characters kept when `mask="short"` (spec section 5: "z.B. UUID 8 Zeichen"). */
export const SHORT_MASK_LENGTH = 8;

/**
 * The keyboard shortcut for `reveal="shortcut"`. Chosen `Alt+Shift+R`
 * ("Reveal"): no browser binds it, it does not collide with Ctrl/Cmd+R
 * (reload), and it is reachable one-handed on both common layouts. Matched via
 * `event.code === "KeyR"` so it survives Alt+Shift letter remapping.
 */
export const REVEAL_SHORTCUT = "Alt+Shift+R";

const CONFIRMATION_MS = 1500;

function isRevealShortcut(event: KeyboardEvent): boolean {
  return event.altKey && event.shiftKey && event.code === "KeyR";
}

export function RevealValue({
  value,
  fallback,
  copyValue,
  reveal = "always",
  mask = "none",
  copyable = false,
  displayFormat = "text",
  chips = null,
  label,
  readOnly = false,
  testId = "reveal-value",
}: RevealValueProps): JSX.Element | null {
  const { t } = useTranslation();
  const [revealed, setRevealed] = useState(reveal === "always");
  const [copied, setCopied] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    setRevealed(reveal === "always");
  }, [reveal]);

  // A pending confirmation timer must not fire after unmount (React StrictMode
  // double-mounts in development — same guard the pre-WS3 ArtifactId used).
  useEffect(
    () => () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    },
    []
  );

  // `reveal="shortcut"`: a document-level listener is the honest keyboard
  // equivalent — the value can be revealed without first tabbing to it. It is
  // only mounted while the value is still hidden, so a revealed field stops
  // listening.
  useEffect(() => {
    if (reveal !== "shortcut" || revealed) return;
    const onKeyDown = (event: KeyboardEvent): void => {
      if (isRevealShortcut(event)) {
        event.preventDefault();
        setRevealed(true);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [reveal, revealed]);

  const rawLabel = (value && value.trim()) || (fallback && fallback.trim()) || "";
  const fullValue = (copyValue && copyValue.trim()) || (value && value.trim()) || rawLabel;
  const displayLabel =
    mask === "short" && rawLabel.length > SHORT_MASK_LENGTH
      ? `${rawLabel.slice(0, SHORT_MASK_LENGTH)}…`
      : rawLabel;

  const handleCopy = useCallback(() => {
    if (!fullValue) return;
    // navigator.clipboard is undefined on insecure origins and in jsdom —
    // failing to copy must never break the surrounding view.
    const write = navigator.clipboard?.writeText?.(fullValue);
    Promise.resolve(write)
      .then(() => {
        setCopied(true);
        if (timerRef.current) clearTimeout(timerRef.current);
        timerRef.current = setTimeout(() => setCopied(false), CONFIRMATION_MS);
      })
      .catch(() => {
        /* clipboard unavailable — silently keep the plain label */
      });
  }, [fullValue]);

  if (!rawLabel) return null;

  const copyAllowed = copyable && !readOnly && Boolean(fullValue);
  const revealControlled = reveal !== "always";
  const showValue = !revealControlled || revealed;

  const monoClass = displayFormat === "mono" ? styles.mono : "";
  const valueClass = `${styles.value} ${monoClass}`;
  const copyAriaLabel = label
    ? t("revealValue.copyLabel", { label, defaultValue: "{{label}} kopieren" })
    : t("revealValue.copy", "Wert kopieren");

  let body: JSX.Element;
  if (!showValue) {
    body = (
      <span className={styles.hidden} aria-hidden="true">
        {"•".repeat(SHORT_MASK_LENGTH)}
      </span>
    );
  } else if (displayFormat === "chips" && chips && chips.length > 0) {
    body = (
      <span className={styles.chips} data-testid={`${testId}-chips`}>
        {chips.map((chip, index) => (
          <span key={`${chip}-${index}`} className={styles.chip} data-testid={`${testId}-chip`}>
            {chip}
          </span>
        ))}
      </span>
    );
  } else {
    body = (
      // Double-click is a pointer-only convenience; the keyboard-accessible
      // copy control is the adjacent `<button data-testid={`${testId}-copy`}>`,
      // so this text is deliberately not itself a tab stop.
      // eslint-disable-next-line jsx-a11y/no-static-element-interactions
      <span
        className={`${valueClass} ${copyAllowed ? styles.copyable : ""}`}
        data-testid={`${testId}-value`}
        title={copyAllowed ? t("revealValue.copyHint", "Zum Kopieren doppelklicken") : undefined}
        onDoubleClick={copyAllowed ? handleCopy : undefined}
      >
        {displayLabel}
      </span>
    );
  }

  return (
    <span className={styles.root} id={testId} data-testid={testId}>
      {body}
      {revealControlled && (
        <button
          type="button"
          className={styles.iconButton}
          data-testid={`${testId}-reveal`}
          aria-pressed={revealed}
          aria-label={
            revealed
              ? t("revealValue.hide", "Wert verbergen")
              : t("revealValue.show", "Wert anzeigen")
          }
          title={
            revealed
              ? t("revealValue.hide", "Wert verbergen")
              : t("revealValue.revealHint", {
                  shortcut: REVEAL_SHORTCUT,
                  defaultValue: `Zum Anzeigen klicken oder ${REVEAL_SHORTCUT} drücken`,
                })
          }
          onClick={() => setRevealed((current) => !current)}
        >
          {revealed ? (
            <EyeOff aria-hidden="true" size={14} />
          ) : (
            <Eye aria-hidden="true" size={14} />
          )}
        </button>
      )}
      {copyAllowed && (
        <button
          type="button"
          className={styles.iconButton}
          data-testid={`${testId}-copy`}
          aria-label={copyAriaLabel}
          title={copyAriaLabel}
          onClick={handleCopy}
        >
          <ClipboardCopy aria-hidden="true" size={14} />
        </button>
      )}
      {copied && (
        <span
          className={styles.status}
          role="status"
          aria-live="polite"
          data-testid={`${testId}-copied`}
        >
          {t("revealValue.copied", "Kopiert")}
        </span>
      )}
      {revealControlled && revealed && (
        <span
          className={styles.srOnly}
          role="status"
          aria-live="polite"
          data-testid={`${testId}-revealed`}
        >
          {t("revealValue.revealed", "Wert angezeigt")}
        </span>
      )}
    </span>
  );
}

RevealValue.displayName = "RevealValue";
