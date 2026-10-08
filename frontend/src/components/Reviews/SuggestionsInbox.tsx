/**
 * ARCH-L1-001 ReactFrontend — SuggestionsInbox (ADR-019 / WP6).
 *
 * leaf_id: COMP-RF-SUG-001
 * req_id:  ADR-019 (generischer Vorschlags-Lebenszyklus, WP6),
 *          #1155 Aspekt 2
 *
 * Renders the persisted suggestion inbox — the human-readable side of the
 * "knowledge → suggestion → human confirms" loop (ADR-019). O6: it is mounted
 * inside the existing ReviewsView surface (its "suggestions" mode), not a new
 * page, so there is no second queue/route to keep in sync.
 *
 * Each row shows its provenance ("Vorschlag von …", from the server-set
 * `proposed_by`/`producer`/`proposed_at`) and offers Annehmen/Ablehnen.
 * Ablehnen is a two-step action: a confirmation dialog collects a mandatory
 * reason before the reject is POSTed, so a suggestion is never discarded by a
 * stray click.
 *
 * States: loading / error / empty / success are all handled explicitly; no
 * branch assumes data is present.
 *
 * Accessibility (review round 2): the inbox is a labelled region, every
 * row action carries a contextual accessible name, the reject reason is a
 * required + `aria-describedby`-linked field, and a polite live region
 * announces the decision while focus is parked on the stable inbox container
 * after the decided row disappears.
 */

import { useCallback, useEffect, useId, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { ConfirmDialog } from "../shared/ConfirmDialog";
import { extractErrorMessage } from "../../api/client";
import type { Suggestion } from "../../api/suggestions";
import { useSuggestionsData } from "./useSuggestionsData";
import styles from "./SuggestionsInbox.module.css";

/** Stable id pairing the reject textarea with its validation message. */
const REJECT_ERROR_ID = "suggestion-reject-error";

/**
 * Format an ISO timestamp in the active UI language (not the OS locale).
 * Invalid input falls back to the raw string — `toLocaleString()` rendered
 * "Invalid Date" for a malformed value (FE review round 2, F5).
 */
function formatTimestamp(iso: string, locale?: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return new Intl.DateTimeFormat(locale, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

/** Provenance source: the server-set proposer, else the producer label. */
function provenanceSource(suggestion: Suggestion, fallback: string): string {
  return suggestion.proposed_by || suggestion.producer || fallback;
}

export function SuggestionsInbox(): JSX.Element {
  const { t, i18n } = useTranslation();
  const { suggestions, isLoading, error, accept, reject, isActing } =
    useSuggestionsData();

  const inboxRef = useRef<HTMLDivElement | null>(null);
  const rejectReasonRef = useRef<HTMLTextAreaElement | null>(null);
  // Synchronous in-flight guard: `isActing` only disables the buttons after
  // the next render, so a double-click would otherwise fire two POSTs and set
  // a spurious action error (FE review round 2, F2).
  const actingRef = useRef(false);

  const [actionError, setActionError] = useState<{
    id: string;
    message: string;
  } | null>(null);
  const [rejectTarget, setRejectTarget] = useState<Suggestion | null>(null);
  const [rejectReason, setRejectReason] = useState("");
  const [rejectError, setRejectError] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  // Bumped after a decision; the effect moves focus to the stable inbox
  // container once the decided row (and, for reject, the dialog) is gone.
  const [focusToken, setFocusToken] = useState(0);

  const headingId = useId();

  useEffect(() => {
    if (focusToken === 0) return;
    inboxRef.current?.focus();
  }, [focusToken]);

  const handleAccept = useCallback(
    async (id: string): Promise<void> => {
      if (actingRef.current) return;
      actingRef.current = true;
      setActionError(null);
      try {
        await accept(id);
        setStatusMessage(t("suggestions.accepted"));
        setFocusToken((token) => token + 1);
      } catch (err: unknown) {
        setActionError({
          id,
          message: extractErrorMessage(err) ?? t("suggestions.actionError"),
        });
      } finally {
        actingRef.current = false;
      }
    },
    [accept, t],
  );

  const openReject = useCallback((suggestion: Suggestion): void => {
    setRejectTarget(suggestion);
    setRejectReason("");
    setRejectError(null);
    setActionError(null);
  }, []);

  const closeReject = useCallback((): void => {
    setRejectTarget(null);
    setRejectReason("");
    setRejectError(null);
  }, []);

  const confirmReject = useCallback(async (): Promise<void> => {
    if (!rejectTarget) return;
    if (!rejectReason.trim()) {
      setRejectError(t("suggestions.rejectReasonRequired"));
      rejectReasonRef.current?.focus();
      return;
    }
    if (actingRef.current) return;
    actingRef.current = true;
    setRejectError(null);
    try {
      await reject(rejectTarget.id, rejectReason.trim());
      setStatusMessage(t("suggestions.rejected"));
      closeReject();
      setFocusToken((token) => token + 1);
    } catch (err: unknown) {
      setRejectError(extractErrorMessage(err) ?? t("suggestions.actionError"));
    } finally {
      actingRef.current = false;
    }
  }, [rejectTarget, rejectReason, reject, closeReject, t]);

  if (isLoading) {
    return (
      <p role="status" data-testid="suggestions-loading" className={styles.mutedText}>
        {t("loading")}
      </p>
    );
  }

  if (error) {
    return (
      <p role="alert" data-testid="suggestions-error" className={styles.errorText}>
        {t("suggestions.error")} ({error})
      </p>
    );
  }

  return (
    <div
      ref={inboxRef}
      data-testid="suggestions-inbox"
      role="region"
      aria-labelledby={headingId}
      tabIndex={-1}
    >
      <h3 id={headingId} data-testid="suggestions-heading" className={styles.heading}>
        {t("suggestions.heading")}
      </h3>

      {/* Always mounted so the announcement is reliably picked up (A-F2). */}
      <p
        role="status"
        aria-live="polite"
        data-testid="suggestions-status"
        className={styles.srOnly}
      >
        {statusMessage}
      </p>

      {suggestions.length === 0 ? (
        <p data-testid="suggestions-empty" className={styles.mutedText}>
          {t("suggestions.empty")}
        </p>
      ) : (
        <ul className={styles.list} data-testid="suggestions-list">
          {suggestions.map((suggestion) => {
            const kindLabel = t(`suggestions.kind.${suggestion.kind}`);
            const source = provenanceSource(
              suggestion,
              t("suggestions.unknownSource"),
            );
            return (
              <li
                key={suggestion.id}
                data-testid={`suggestion-row-${suggestion.id}`}
                className={styles.row}
              >
                <div className={styles.meta}>
                  <span
                    data-testid={`suggestion-kind-${suggestion.id}`}
                    className={styles.kindBadge}
                  >
                    {kindLabel}
                  </span>
                  <span
                    data-testid={`suggestion-provenance-${suggestion.id}`}
                    className={styles.provenance}
                  >
                    {t("suggestions.provenance", {
                      source,
                      time: formatTimestamp(
                        suggestion.proposed_at ?? suggestion.created_at,
                        i18n?.language,
                      ),
                    })}
                  </span>
                </div>

                {suggestion.target_item_type && (
                  <div
                    data-testid={`suggestion-target-${suggestion.id}`}
                    className={styles.target}
                  >
                    {t("suggestions.target")}: {suggestion.target_item_type}
                    {suggestion.target_item_id
                      ? ` (${suggestion.target_item_id})`
                      : ""}
                  </div>
                )}

                <div className={styles.actions}>
                  <button
                    type="button"
                    className="btn-primary"
                    data-testid={`suggestion-accept-${suggestion.id}`}
                    aria-label={t("suggestions.acceptLabel", {
                      kind: kindLabel,
                      source,
                    })}
                    disabled={isActing}
                    onClick={() => void handleAccept(suggestion.id)}
                  >
                    {t("suggestions.accept")}
                  </button>
                  <button
                    type="button"
                    className="btn-danger"
                    data-testid={`suggestion-reject-${suggestion.id}`}
                    aria-label={t("suggestions.rejectLabel", {
                      kind: kindLabel,
                      source,
                    })}
                    disabled={isActing}
                    onClick={() => openReject(suggestion)}
                  >
                    {t("suggestions.reject")}
                  </button>
                </div>

                {/* Action error lives in its own row, not in a detached banner
                    at the top of the inbox (FE review round 2, F3). */}
                {actionError?.id === suggestion.id && (
                  <p
                    role="alert"
                    data-testid="suggestions-action-error"
                    className={styles.errorText}
                  >
                    {actionError.message}
                  </p>
                )}
              </li>
            );
          })}
        </ul>
      )}

      {rejectTarget && (
        <ConfirmDialog
          testId="suggestion-reject-confirm"
          title={t("suggestions.rejectConfirmTitle")}
          message={t("suggestions.rejectConfirmMessage")}
          confirmLabel={t("suggestions.rejectConfirm")}
          cancelLabel={t("suggestions.cancel")}
          isSubmitting={isActing}
          onConfirm={() => void confirmReject()}
          onCancel={closeReject}
        >
          <label
            htmlFor="suggestion-reject-reason"
            className={styles.label}
          >
            {t("suggestions.rejectReasonLabel")}
          </label>
          <textarea
            ref={rejectReasonRef}
            id="suggestion-reject-reason"
            data-testid="suggestion-reject-reason"
            value={rejectReason}
            onChange={(e) => setRejectReason(e.target.value)}
            placeholder={t("suggestions.rejectReasonPlaceholder")}
            rows={3}
            className={styles.reasonInput}
            disabled={isActing}
            required
            aria-required="true"
            aria-invalid={!!rejectError}
            aria-describedby={rejectError ? REJECT_ERROR_ID : undefined}
          />
          {rejectError && (
            <p
              id={REJECT_ERROR_ID}
              role="alert"
              data-testid="suggestion-reject-error"
              className={styles.dialogErrorText}
            >
              {rejectError}
            </p>
          )}
        </ConfirmDialog>
      )}
    </div>
  );
}

SuggestionsInbox.displayName = "SuggestionsInbox";
