/**
 * `<AiDerivationDialog>` — the ONE review step every AI derivation shares
 * (issue #1360, W12c).
 *
 * The defect this component closes: AI derivations behaved differently per
 * flow. Some persisted immediately, some dropped their (paid) drafts, some
 * had no entry point at all — and the user was never asked, in one place,
 * which of "save it now", "keep it for later review" or "throw it away" they
 * meant. This dialog is that one place:
 *
 *   - **Confirm**     — persist the reviewed draft(s) through the flow's own
 *                       write seam.
 *   - **Review later**— persist the same way, then park them for the queue:
 *                       the drafts are born `proposed` and show up under
 *                       Reviews → "Nur KI-Vorschläge".
 *   - **Discard**     — close and persist nothing. Discard is also what the
 *                       close button / backdrop / Escape do: the only way a
 *                       draft reaches the repository is one of the two
 *                       explicit save actions above.
 *
 * Why Confirm and Review later share a seam: every canonical write path in
 * this app (the `proposed` seam, #1089) lands a derived artefact in the
 * workflow's proposal state, where `_auto_approve` deliberately stops — "a
 * proposal is a human decision". The two actions therefore differ in *what
 * the reviewer is saying* (I checked this now / keep it and I will look at it
 * in the queue), not in whether a later approval is still needed, and the
 * dialog's copy says exactly that instead of implying an auto-approval that
 * cannot happen.
 *
 * The component is deliberately presentational and controlled: the caller
 * owns the preview request, the write seam and the result messaging, so the
 * dialog can back every flow (glossary/ADR/risk through the `preview|write`
 * REST seam, requirement decomposition through its accept action) without a
 * second implementation per type.
 *
 * States: loading / error / empty / ready are rendered explicitly; `drafts`
 * is `null` while the preview has not run yet (the ADR flow asks for the
 * decision text first), and `[]` is the "provider proposed nothing" answer —
 * both distinct from "still loading".
 */

import { useEffect, useId, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { Dialog } from "../Dialog";
import { Spinner } from "../Spinner/Spinner";
import styles from "./AiDerivationDialog.module.css";

/** One reviewable draft. Deliberately the smallest common denominator. */
export interface AiDerivationDraft {
  title: string;
  description?: string;
  rationale?: string;
}

export interface AiDerivationDialogProps {
  open: boolean;
  /** Accessible dialog title; match the trigger's label where possible. */
  title: string;
  /** Human-readable source of the derivation ("Anforderung: …"). */
  sourceLabel?: string;
  /**
   * The preview's drafts. `null` = the preview has not run yet (render
   * `intro` + the preview trigger), `[]` = it ran and proposed nothing.
   */
  drafts: AiDerivationDraft[] | null;
  /** Preview request in flight. */
  isLoading: boolean;
  /** Preview request failed (message already extracted). */
  loadError?: string | null;
  /** Write request in flight. */
  isSubmitting: boolean;
  /** Write request failed (message already extracted). */
  submitError?: string | null;
  /** Optional per-draft checkboxes (default off: every draft is written). */
  selectable?: boolean;
  /** Optional input rendered above the drafts (e.g. the ADR decision text). */
  intro?: ReactNode;
  /** Renders the "create preview" action while `drafts` is `null`. */
  onPreview?: () => void;
  /** Extra reason to keep the two save actions disabled (e.g. empty intro). */
  confirmDisabled?: boolean;
  onConfirm: (selected: AiDerivationDraft[]) => void;
  onReviewLater: (selected: AiDerivationDraft[]) => void;
  onDiscard: () => void;
  testIdPrefix: string;
}

export function AiDerivationDialog({
  open,
  title,
  sourceLabel,
  drafts,
  isLoading,
  loadError,
  isSubmitting,
  submitError,
  selectable = false,
  intro,
  onPreview,
  confirmDisabled = false,
  onConfirm,
  onReviewLater,
  onDiscard,
  testIdPrefix,
}: AiDerivationDialogProps): JSX.Element | null {
  const { t } = useTranslation();
  const hintId = useId();
  const [deselected, setDeselected] = useState<ReadonlySet<number>>(new Set());

  // A new preview invalidates the previous selection: default is "all
  // selected", so a draft the user unchecked in the last run must not stay
  // silently dropped in the next one.
  useEffect(() => {
    setDeselected(new Set());
  }, [drafts]);

  if (!open) return null;

  // `readyDrafts` is the type-narrowed alias of `drafts`: non-null exactly
  // while the preview result is on screen (loading finished, no error path
  // pending). Everything below renders from this one value.
  const isReady = drafts !== null && !isLoading;
  const readyDrafts = isReady ? (drafts ?? []) : null;
  const selectedDrafts = (readyDrafts ?? []).filter(
    (_, index) => !deselected.has(index)
  );
  const nothingSelected = selectedDrafts.length === 0;
  const saveDisabled = isSubmitting || confirmDisabled || !isReady || nothingSelected;

  const toggleDraft = (index: number): void => {
    setDeselected((prev) => {
      const next = new Set(prev);
      if (next.has(index)) next.delete(index);
      else next.add(index);
      return next;
    });
  };

  const footer = (
    <>
      {drafts === null && onPreview ? (
        <button
          type="button"
          className="btn-primary"
          onClick={onPreview}
          disabled={isLoading || confirmDisabled}
          data-testid={`${testIdPrefix}-preview`}
        >
          {isLoading ? <Spinner label={t("aiDerivation.loading")} /> : t("aiDerivation.preview")}
        </button>
      ) : (
        <>
          <button
            type="button"
            className="btn-primary"
            onClick={() => onConfirm(selectedDrafts)}
            disabled={saveDisabled}
            data-testid={`${testIdPrefix}-confirm`}
          >
            {isSubmitting ? <Spinner label={t("aiDerivation.saving")} /> : t("aiDerivation.confirm")}
          </button>
          <button
            type="button"
            className="btn-secondary"
            onClick={() => onReviewLater(selectedDrafts)}
            disabled={saveDisabled}
            data-testid={`${testIdPrefix}-later`}
          >
            {t("aiDerivation.reviewLater")}
          </button>
        </>
      )}
      <button
        type="button"
        className="btn-ghost"
        onClick={onDiscard}
        disabled={isSubmitting}
        data-testid={`${testIdPrefix}-discard`}
      >
        {t("aiDerivation.discard")}
      </button>
    </>
  );

  return (
    <Dialog
      title={title}
      description={sourceLabel}
      onClose={onDiscard}
      footer={footer}
      size="lg"
      testId={`${testIdPrefix}-dialog`}
      closeOnBackdropClick={!isSubmitting}
    >
      {/* The honest preview contract, up front: nothing is stored until one
          of the two save actions above is taken (issue #1360 AC #3). */}
      <p className={styles.notice} data-testid={`${testIdPrefix}-notice`}>
        {t("aiDerivation.notice")}
      </p>

      {intro}

      {loadError && (
        <div role="alert" data-testid={`${testIdPrefix}-error`} className={styles.error}>
          {loadError}
        </div>
      )}

      {isLoading && (
        <p role="status" data-testid={`${testIdPrefix}-loading`} className={styles.muted}>
          {t("aiDerivation.loading")}
        </p>
      )}

      {readyDrafts && readyDrafts.length === 0 && (
        <p data-testid={`${testIdPrefix}-empty`} className={styles.muted}>
          {t("aiDerivation.empty")}
        </p>
      )}

      {readyDrafts && readyDrafts.length > 0 && (
        <>
          {selectable && (
            <p className={styles.muted} id={hintId}>
              {t("aiDerivation.selectHint")}
            </p>
          )}
          <ul
            className={styles.list}
            data-testid={`${testIdPrefix}-drafts`}
            {...(selectable ? { "aria-describedby": hintId } : {})}
          >
            {readyDrafts.map((draft, index) => {
              const rowId = index + 1;
              const selected = !deselected.has(index);
              return (
                <li
                  key={index}
                  className={styles.row}
                  data-testid={`${testIdPrefix}-draft-${index}`}
                >
                  <div className={styles.rowHeader}>
                    {selectable && (
                      <input
                        type="checkbox"
                        checked={selected}
                        disabled={isSubmitting}
                        onChange={() => toggleDraft(index)}
                        aria-label={t("aiDerivation.selectDraft", { index: rowId })}
                        data-testid={`${testIdPrefix}-select-${index}`}
                      />
                    )}
                    <span
                      className={styles.draftTitle}
                      data-testid={`${testIdPrefix}-title-${index}`}
                    >
                      {draft.title}
                    </span>
                  </div>
                  {draft.description && (
                    <p
                      className={styles.draftText}
                      data-testid={`${testIdPrefix}-description-${index}`}
                    >
                      {draft.description}
                    </p>
                  )}
                  {draft.rationale && (
                    <p
                      className={styles.rationale}
                      data-testid={`${testIdPrefix}-rationale-${index}`}
                    >
                      {t("aiDerivation.rationale")}: {draft.rationale}
                    </p>
                  )}
                </li>
              );
            })}
          </ul>
        </>
      )}

      {isReady && (
        <p className={styles.caveat} data-testid={`${testIdPrefix}-caveat`}>
          {t("aiDerivation.caveat")}
        </p>
      )}

      {submitError && (
        <div role="alert" data-testid={`${testIdPrefix}-submit-error`} className={styles.error}>
          {submitError}
        </div>
      )}
    </Dialog>
  );
}

AiDerivationDialog.displayName = "AiDerivationDialog";
