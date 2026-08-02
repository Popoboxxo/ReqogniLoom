/**
 * ARCH-L1-001 ReactFrontend — <ArtifactId> (UI concept ch. 12.4).
 *
 * The identifier is the *name* of an artifact, not a metadatum (ch. 2). It
 * therefore gets one canonical representation that is identical in lists,
 * trees, trace panels and detail headers — mono, selectable in one gesture,
 * and copyable by click with a visible confirmation.
 *
 * Replaces four inline duplicates that each rendered `uid` slightly
 * differently (`fontFamily: 'monospace'` + an ad-hoc muted colour).
 *
 * Deliberately neutral: colour encodes workflow status and nothing else
 * (ch. 3.3), so an identifier never carries a hue of its own.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

export interface ArtifactIdProps {
  /**
   * The semantic identifier (`uid`). When absent, `fallback` is rendered
   * instead — artifacts without an assigned uid still need a stable handle.
   */
  value?: string | null;
  /** Shown when `value` is empty, e.g. the first 8 chars of the UUID. */
  fallback?: string | null;
  /** Copy the *full* value to the clipboard, if it differs from the label. */
  copyValue?: string | null;
  /** Suppresses the copy interaction — used inside already-clickable rows. */
  readOnly?: boolean;
  testId?: string;
}

const CONFIRMATION_MS = 1500;

export function ArtifactId({
  value,
  fallback,
  copyValue,
  readOnly = false,
  testId = "artifact-id",
}: ArtifactIdProps): JSX.Element | null {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // A pending confirmation timer must not fire after unmount (React 18
  // StrictMode double-mounts this component in development).
  useEffect(
    () => () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    },
    [],
  );

  const label = (value && value.trim()) || (fallback && fallback.trim()) || "";
  const clipboardText = copyValue?.trim() || label;

  const handleCopy = useCallback(() => {
    if (!clipboardText) return;
    // navigator.clipboard is undefined on insecure origins and in jsdom —
    // failing to copy must never break the surrounding view.
    const write = navigator.clipboard?.writeText?.(clipboardText);
    Promise.resolve(write)
      .then(() => {
        setCopied(true);
        if (timerRef.current) clearTimeout(timerRef.current);
        timerRef.current = setTimeout(() => setCopied(false), CONFIRMATION_MS);
      })
      .catch(() => {
        /* clipboard unavailable — silently keep the plain label */
      });
  }, [clipboardText]);

  if (!label) return null;

  const sharedStyle: React.CSSProperties = {
    fontFamily: "var(--font-mono)",
    fontSize: "var(--font-size-sm)",
    fontVariantNumeric: "tabular-nums",
    letterSpacing: "var(--tracking-normal)",
    color: "var(--color-text)",
    userSelect: "all",
    whiteSpace: "nowrap",
  };

  if (readOnly) {
    return (
      <span data-testid={testId} style={sharedStyle}>
        {label}
      </span>
    );
  }

  return (
    <button
      type="button"
      data-testid={testId}
      onClick={handleCopy}
      title={
        copied
          ? t("artifactId.copied", "Bezeichner kopiert")
          : t("artifactId.copyHint", "Bezeichner kopieren")
      }
      aria-label={t("artifactId.copyLabel", "Bezeichner {{id}} kopieren", {
        id: label,
      })}
      style={{
        ...sharedStyle,
        background: "transparent",
        border: "1px solid transparent",
        borderRadius: "var(--radius-sm)",
        padding: "0 var(--space-1)",
        cursor: "pointer",
        display: "inline-flex",
        alignItems: "center",
        gap: "var(--space-1)",
      }}
    >
      {label}
      {copied && (
        <span
          data-testid={`${testId}-copied`}
          role="status"
          style={{
            fontFamily: "var(--font-sans)",
            fontSize: "var(--font-size-xs)",
            color: "var(--color-text-muted)",
          }}
        >
          {t("artifactId.copied", "Bezeichner kopiert")}
        </span>
      )}
    </button>
  );
}
