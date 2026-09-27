/**
 * Issue #1094 — `<IdChip>`, the ONE identifier chip of the app.
 *
 * An artifact has two identities (see #1003 for why they must both stay in the
 * API response):
 *
 *   - `uid`  — the readable, workspace-local, monotonically increasing
 *              identifier (`REQ-001`, `ARCH-001`). Human-facing, and only
 *              meaningful inside one workspace.
 *   - `id` / `artifact_id` — the system id (UUID). Tenant-wide, stable, and the
 *              identity every API, MCP tool and ReqIF round-trip speaks.
 *
 * The component exists because those two answers were previously not
 * distinguished at the point of interaction: a chip that shows one identifier
 * and copies the other is indistinguishable from a chip that does both, so the
 * user pastes a workspace-local `REQ-001` into a script and it 404s. Here the
 * contract is fixed and documented on the control itself:
 *
 *   - **shown**: `uid` by default, `systemId` on request, with the other one as
 *     fallback when the preferred one does not exist.
 *   - **copied**: ALWAYS the system id, when there is one. When there is not,
 *     the uid is copied and the announcement says so out loud
 *     (`idChip.copiedUidFallback`) — the user is never left guessing which of
 *     the two strings is now on their clipboard.
 *
 * The result of a copy is announced through an `aria-live` region, not only
 * drawn: a copy button whose only feedback is a transient icon swap is silent
 * for a screen-reader user, and clipboard feedback is exactly the kind of
 * state change that must be announced (the repo's existing `aria-live` usage in
 * `RevealValue` / `EmptyState` / the workflow inspector).
 *
 * Why this is a new component and not an option on `<RevealValue>`:
 * `<RevealValue>` copies whatever `copyValue` it is handed, which is the right
 * generic behaviour for a *value* attribute but leaves the uid/system-id
 * distinction to every call site. Issue #92 ("show the UUID in the UI and
 * copy-paste it") wants the same affordance for a workspace token. Two
 * call-site-configured copies of the same idea is how they drift; one component
 * that owns the distinction is the fix. #92's surface should consume THIS
 * component rather than build a sibling.
 *
 * Accessibility baseline (not an audit verdict):
 *   - the copy affordance is a real `<button>` with a meaningful accessible
 *     name and a visible focus ring (global `:focus-visible`);
 *   - the result is a `role="status" aria-live="polite"` region;
 *   - the identifier itself is plain text, never a pseudo-button, and
 *     `user-select: all` so a pointer user can select it without the chip
 *     pretending to be interactive;
 *   - the copy control uses the design system's `btn-ghost` chrome rather than
 *     an ad-hoc fill (design-system ratchet, #1093).
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { ClipboardCopy } from "lucide-react";

import styles from "./IdChip.module.css";

/** Which identity the chip *shows*. Copying is unaffected by this. */
export type IdChipDisplay = "uid" | "system";

/** Outcome of one copy attempt, reported through `onCopyResult` and `aria-live`. */
export type IdChipCopyStatus = "system" | "uid" | "failed";

export interface IdChipCopyResult {
  status: IdChipCopyStatus;
  /** The exact string handed to the clipboard, or `null` when none could be. */
  value: string | null;
}

export interface IdChipProps {
  /** Readable, workspace-local identifier (`uid`), e.g. "ARCH-001". */
  uid?: string | null;
  /** System id (UUID) — the artifact's `id` / `artifact_id`. */
  systemId?: string | null;
  /**
   * Last-resort text when neither identity is present, e.g. the first 8
   * characters of the UUID for a row whose `uid` has not been allocated yet.
   * Never copied — it is a display placeholder, not an identity.
   */
  fallback?: string | null;
  /** Rendered when there is nothing at all to show. */
  placeholder?: string | null;
  /** Which identity to show. Default `"uid"` (the readable one). */
  display?: IdChipDisplay;
  /**
   * Hide the identifier text while keeping the copy affordance — the display
   * preference from issue #1094. Reading is a per-artifact decision; copying
   * the system id stays available either way.
   */
  hideReadable?: boolean;
  /**
   * Accessible context noun for the copy control, e.g. "Anforderung". When
   * omitted the control is named after the identity kind alone.
   */
  label?: string;
  /** Notified once per copy attempt. Never throws into the caller. */
  onCopyResult?: (result: IdChipCopyResult) => void;
  testId?: string;
}

/** How long the "copied" announcement stays in the live region. */
const CONFIRMATION_MS = 2500;

function clean(value: string | null | undefined): string {
  return (value ?? "").trim();
}

export function IdChip({
  uid,
  systemId,
  fallback = null,
  placeholder = null,
  display = "uid",
  hideReadable = false,
  label,
  onCopyResult,
  testId = "id-chip",
}: IdChipProps): JSX.Element | null {
  const { t } = useTranslation();
  const [status, setStatus] = useState<IdChipCopyStatus | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // A pending announcement must not fire into an unmounted component (React
  // StrictMode double-mounts in development).
  useEffect(
    () => () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    },
    []
  );

  const trimmedUid = clean(uid);
  const trimmedSystemId = clean(systemId);
  const trimmedFallback = clean(fallback);

  // The shown identity is the requested one; the other is the fallback so a
  // chip never renders empty just because the caller asked for the other kind.
  const preferred = display === "system" ? trimmedSystemId : trimmedUid;
  const other = display === "system" ? trimmedUid : trimmedSystemId;
  const shownValue = preferred || other || trimmedFallback || clean(placeholder);
  // What lands on the clipboard: the system id whenever it exists. The `uid`
  // fallback is announced as such — see the file header.
  const copiesSystemId = trimmedSystemId !== "";
  const copyValue = copiesSystemId ? trimmedSystemId : trimmedUid;

  const report = useCallback(
    (next: IdChipCopyStatus, value: string | null): void => {
      setStatus(next);
      if (timerRef.current) clearTimeout(timerRef.current);
      timerRef.current = setTimeout(() => setStatus(null), CONFIRMATION_MS);
      onCopyResult?.({ status: next, value });
    },
    [onCopyResult]
  );

  const handleCopy = useCallback((): void => {
    if (!copyValue) {
      report("failed", null);
      return;
    }
    // `navigator.clipboard` is undefined on insecure origins and in jsdom.
    // A refused copy is a real outcome here (the user is told whether they got
    // a UUID), so it is reported rather than swallowed.
    const write = navigator.clipboard?.writeText?.(copyValue);
      void Promise.resolve(write)
        .then(() => {
          report(copiesSystemId ? "system" : "uid", copyValue);
        })
        .catch(() => {
          report("failed", null);
        });
  }, [copyValue, copiesSystemId, report]);

  if (!shownValue && !copyValue) return null;

  const kindLabel = copiesSystemId
    ? t("idChip.systemIdTerm", "System-ID")
    : t("idChip.readableIdTerm", "Lesbare ID");
  const copyAriaLabel = label
    ? t("idChip.copyWithLabel", {
        label,
        kind: kindLabel,
        defaultValue: "{{label}}: {{kind}} kopieren",
      })
    : t("idChip.copy", {
        kind: kindLabel,
        defaultValue: "{{kind}} kopieren",
      });

  const statusMessage =
    status === "system"
      ? t("idChip.copiedSystemId", "UUID kopiert")
      : status === "uid"
        ? t("idChip.copiedUidFallback", "UID kopiert, weil keine System-ID vorhanden")
        : status === "failed"
          ? t("idChip.copyFailed", "Kopieren fehlgeschlagen")
          : "";

  return (
    <span className={styles.root} data-testid={testId}>
      {hideReadable ? null : (
        <span className={styles.value} data-testid={`${testId}-value`}>
          {shownValue}
        </span>
      )}
      {copyValue ? (
        <button
          type="button"
          className={`btn-ghost btn-sm ${styles.copyButton}`}
          data-testid={`${testId}-copy`}
          aria-label={copyAriaLabel}
          title={copyAriaLabel}
          onClick={handleCopy}
        >
          <ClipboardCopy aria-hidden="true" size={14} />
        </button>
      ) : null}
      {/*
        Announced, not merely drawn. Always mounted (not conditionally
        rendered) so assistive technology has a live region to observe from the
        first copy onwards.
      */}
      <span
        className={styles.status}
        role="status"
        aria-live="polite"
        data-testid={`${testId}-status`}
      >
        {statusMessage}
      </span>
    </span>
  );
}

IdChip.displayName = "IdChip";
