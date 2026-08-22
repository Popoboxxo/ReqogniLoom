/**
 * REQ-187 — Guarded Shadow → Authoritative flip dialog (SCR-206 Card 2).
 *
 * Reuses the editor's ``ConfirmDialog`` frame (title/message/busy/error +
 * children slot for the required checkbox), NOT a new modal system. On open it
 * re-fetches the live enforcement status (never trusts a stale count already on
 * the page), shows the current ``pending_mismatch_count`` prominently, requires
 * an explicit acknowledgement checkbox, and sends that exact count as
 * ``confirm_pending_mismatch_count``. A 409 MISMATCH_COUNT_STALE does NOT retry
 * silently — it surfaces the fresh count, unchecks the box, and forces a
 * re-confirm (mirrors the contract's "re-fetch and re-confirm" intent).
 */

import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { ConfirmDialog } from "../WorkflowEditor/ConfirmDialog";
import {
  permissionDefaultsApi,
  extractStaleMismatchCount,
} from "../../api/permission-defaults";

function extractErrorMessage(err: unknown): string {
  const e = err as { error?: { message?: string }; message?: string };
  return e?.error?.message ?? e?.message ?? String(err);
}

interface EnforcementFlipDialogProps {
  windowDays: number;
  onClose: () => void;
  onFlipped: () => void;
}

export function EnforcementFlipDialog({
  windowDays,
  onClose,
  onFlipped,
}: EnforcementFlipDialogProps): JSX.Element {
  const { t } = useTranslation();
  const [count, setCount] = useState<number | null>(null);
  const [acknowledged, setAcknowledged] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loadingCount, setLoadingCount] = useState(true);

  // Step 1: on open, re-fetch fresh so the shown count is never stale.
  useEffect(() => {
    let cancelled = false;
    setLoadingCount(true);
    permissionDefaultsApi
      .getEnforcement(windowDays)
      .then((status) => {
        if (!cancelled) setCount(status.pending_mismatch_count);
      })
      .catch((err) => {
        if (!cancelled) setError(extractErrorMessage(err));
      })
      .finally(() => {
        if (!cancelled) setLoadingCount(false);
      });
    return () => {
      cancelled = true;
    };
  }, [windowDays]);

  const handleViewMismatches = useCallback((): void => {
    document
      .getElementById("mismatch-review-card")
      ?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, []);

  const handleConfirm = useCallback(async (): Promise<void> => {
    if (count == null) return;
    setBusy(true);
    setError(null);
    try {
      await permissionDefaultsApi.flipEnforcement("authoritative", count);
      onFlipped();
    } catch (err) {
      const stale = extractStaleMismatchCount(err);
      if (stale != null) {
        // Count changed between open and submit — re-confirm required.
        setCount(stale);
        setAcknowledged(false);
        setError(
          t("systemSettings.enforcementFlip.staleCountError", { count: stale })
        );
      } else {
        setError(extractErrorMessage(err));
      }
    } finally {
      setBusy(false);
    }
  }, [count, onFlipped, t]);

  return (
    <ConfirmDialog
      title={t("systemSettings.enforcementFlip.title")}
      message={
        loadingCount
          ? t("systemSettings.enforcementFlip.loadingCount")
          : t("systemSettings.enforcementFlip.message", {
              count: count ?? 0,
              days: windowDays,
            })
      }
      confirmLabel={t("systemSettings.enforcementFlip.confirmLabel")}
      confirmDisabled={loadingCount || count == null || !acknowledged}
      busy={busy}
      errorMessage={error}
      onClose={onClose}
      onConfirm={handleConfirm}
    >
      <div style={{ margin: "var(--space-3) 0" }}>
        <button
          type="button"
          data-testid="flip-view-mismatches"
          onClick={handleViewMismatches}
          style={{
            background: "transparent",
            color: "var(--color-primary)",
            border: "none",
            padding: 0,
            fontSize: "var(--font-size-sm)",
            textDecoration: "underline",
            cursor: "pointer",
          }}
        >
          {t("systemSettings.enforcementFlip.viewMismatches", { count: count ?? 0 })}
        </button>
      </div>
      <label
        style={{
          display: "flex",
          alignItems: "flex-start",
          gap: "var(--space-2)",
          fontSize: "var(--font-size-sm)",
          cursor: "pointer",
        }}
      >
        <input
          type="checkbox"
          data-testid="flip-acknowledge"
          checked={acknowledged}
          onChange={(e) => setAcknowledged(e.target.checked)}
          disabled={loadingCount || busy}
        />
        <span>
          {t("systemSettings.enforcementFlip.acknowledgeLabel", { count: count ?? 0 })}
        </span>
      </label>
    </ConfirmDialog>
  );
}
