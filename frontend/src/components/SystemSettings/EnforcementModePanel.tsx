/**
 * REQ-186/187 — EnforcementModePanel (SCR-206 Card 2).
 *
 * Shows the current permission enforcement phase (shadow/authoritative) and
 * governs the guarded cutover. Shadow → Authoritative is never a single click:
 * it opens the count-echo guarded dialog (``EnforcementFlipDialog``).
 * Authoritative → Shadow (rollback) is a plain single-step confirm — rollback is
 * always the safe direction (legacy rows are dual-written, per the contract).
 * ``ready_for_authoritative`` is a soft advisory hint only, never a hard gate on
 * the button.
 */

import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  permissionDefaultsApi,
  type EnforcementStatus,
} from "../../api/permission-defaults";
import { EnforcementFlipDialog } from "./EnforcementFlipDialog";
import { ConfirmDialog } from "../shared/ConfirmDialog";
import styles from "./EnforcementModePanel.module.css";

function extractErrorMessage(err: unknown): string {
  const e = err as { error?: { message?: string }; message?: string };
  return e?.error?.message ?? e?.message ?? String(err);
}

const WINDOW_DAYS = 30;

function fmtRelative(iso: string | null | undefined, neverLabel: string): string {
  if (!iso) return neverLabel;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString();
}

export function EnforcementModePanel(): JSX.Element {
  const { t } = useTranslation();
  const [status, setStatus] = useState<EnforcementStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [rollingBack, setRollingBack] = useState(false);
  const [showFlipDialog, setShowFlipDialog] = useState(false);
  // UI-20: unified on the shared ConfirmDialog instead of window.confirm.
  const [showRollbackConfirm, setShowRollbackConfirm] = useState(false);

  const load = useCallback(async (): Promise<void> => {
    setLoading(true);
    setError(null);
    try {
      const s = await permissionDefaultsApi.getEnforcement(WINDOW_DAYS);
      setStatus(s);
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const handleRollback = useCallback(async (): Promise<void> => {
    setRollingBack(true);
    setError(null);
    try {
      await permissionDefaultsApi.flipEnforcement("shadow");
      await load();
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setRollingBack(false);
    }
  }, [load]);

  const handleFlipped = useCallback((): void => {
    setShowFlipDialog(false);
    void load();
  }, [load]);

  const confirmRollback = useCallback((): void => {
    setShowRollbackConfirm(false);
    void handleRollback();
  }, [handleRollback]);

  const isAuthoritative = status?.enforcement_mode === "authoritative";

  return (
    <section className={styles.card} data-testid="enforcement-mode-section">
      <h3 className={styles.heading}>{t("systemSettings.enforcementMode.title")}</h3>

      {loading ? (
        <p className={styles.loadingText}>…</p>
      ) : error && !status ? (
        <p role="alert" data-testid="enforcement-error" className={styles.errorText}>
          {error}
        </p>
      ) : (
        status && (
          <>
            <div className={styles.modeRow}>
              <span
                data-testid="enforcement-mode-badge"
                data-mode={status.enforcement_mode}
                className={
                  styles.pill +
                  " " +
                  (isAuthoritative ? styles.pillAuthoritative : styles.pillShadow)
                }
              >
                {isAuthoritative ? t("systemSettings.enforcementMode.authoritative") : t("systemSettings.enforcementMode.shadow")}
              </span>
              {status.ready_for_authoritative ? (
                <span className={styles.successHint}>
                  {t("systemSettings.enforcementMode.zeroMismatches")}
                </span>
              ) : (
                <span className={styles.warningHint}>
                  {t("systemSettings.enforcementMode.pendingMismatches", { count: status.pending_mismatch_count })}
                </span>
              )}
            </div>

            <p className={styles.hint} data-testid="enforcement-meta">
              {t("systemSettings.enforcementMode.meta", {
                count: status.pending_mismatch_count,
                days: status.mismatch_window_days,
                lastAt: fmtRelative(status.last_mismatch_at, t("systemSettings.enforcementMode.never")),
              })}
            </p>
            {status.advisory_note && (
              <p className={styles.hint} data-testid="enforcement-advisory">
                {status.advisory_note}
              </p>
            )}

            {error && (
              <p
                role="alert"
                className={styles.errorText + " " + styles.textSm}
              >
                {error}
              </p>
            )}

            <div className={styles.actions}>
              {isAuthoritative ? (
                <button
                  type="button"
                  data-testid="enforcement-rollback-btn"
                  onClick={() => setShowRollbackConfirm(true)}
                  disabled={rollingBack}
                  className={
                    styles.rollbackButton +
                    " " +
                    (rollingBack ? styles.rollbackDisabled : styles.rollbackEnabled)
                  }
                >
                  {rollingBack ? "…" : t("systemSettings.enforcementMode.rollbackButton")}
                </button>
              ) : (
                <button
                  type="button"
                  data-testid="enforcement-flip-btn"
                  onClick={() => setShowFlipDialog(true)}
                  className={styles.primaryButton}
                >
                  {t("systemSettings.enforcementMode.flipButton")}
                </button>
              )}
            </div>
          </>
        )
      )}

      {showFlipDialog && (
        <EnforcementFlipDialog
          windowDays={WINDOW_DAYS}
          onClose={() => setShowFlipDialog(false)}
          onFlipped={handleFlipped}
        />
      )}

      {showRollbackConfirm && (
        <ConfirmDialog
          title={t("systemSettings.enforcementMode.rollbackButton")}
          message={t("systemSettings.enforcementMode.confirmRollback")}
          confirmLabel={t("systemSettings.enforcementMode.rollbackButton")}
          onConfirm={confirmRollback}
          onCancel={() => setShowRollbackConfirm(false)}
          testId="enforcement-rollback-confirm"
        />
      )}
    </section>
  );
}
