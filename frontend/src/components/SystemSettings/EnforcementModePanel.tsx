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

function extractErrorMessage(err: unknown): string {
  const e = err as { error?: { message?: string }; message?: string };
  return e?.error?.message ?? e?.message ?? String(err);
}

const WINDOW_DAYS = 30;

const cardStyle: React.CSSProperties = {
  background: "var(--color-surface)",
  border: "1px solid var(--color-border)",
  borderRadius: "var(--radius-lg)",
  padding: "var(--space-5)",
  marginBottom: "var(--space-5)",
  boxShadow: "var(--shadow-card)",
};

const headingStyle: React.CSSProperties = {
  fontSize: "var(--font-size-lg)",
  fontWeight: 600,
  color: "var(--color-text)",
  margin: "0 0 var(--space-4) 0",
};

const hintStyle: React.CSSProperties = {
  fontSize: "var(--font-size-sm)",
  color: "var(--color-text-muted)",
  margin: "var(--space-2) 0",
};

const pillBase: React.CSSProperties = {
  display: "inline-block",
  padding: "1px var(--space-2)",
  borderRadius: "var(--radius-full)",
  fontSize: "var(--font-size-xs)",
  fontWeight: 600,
};

const primaryButtonStyle: React.CSSProperties = {
  background: "var(--color-primary)",
  color: "var(--color-on-primary)",
  border: "none",
  borderRadius: "var(--radius-md)",
  padding: "var(--space-2) var(--space-4)",
  fontSize: "var(--font-size-sm)",
  fontWeight: 600,
  cursor: "pointer",
};

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
    if (
      !window.confirm(
        t("systemSettings.enforcementMode.confirmRollback")
      )
    ) {
      return;
    }
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

  const isAuthoritative = status?.enforcement_mode === "authoritative";

  return (
    <section style={cardStyle} data-testid="enforcement-mode-section">
      <h3 style={headingStyle}>{t("systemSettings.enforcementMode.title")}</h3>

      {loading ? (
        <p style={{ color: "var(--color-text-muted)" }}>…</p>
      ) : error && !status ? (
        <p role="alert" data-testid="enforcement-error" style={{ color: "var(--color-danger)" }}>
          {error}
        </p>
      ) : (
        status && (
          <>
            <div style={{ display: "flex", alignItems: "center", gap: "var(--space-3)" }}>
              <span
                data-testid="enforcement-mode-badge"
                data-mode={status.enforcement_mode}
                style={{
                  ...pillBase,
                  background: isAuthoritative
                    ? "rgba(var(--color-success-rgb), 0.12)"
                    : "var(--color-surface-raised)",
                  color: isAuthoritative
                    ? "var(--color-success)"
                    : "var(--color-text-muted)",
                }}
              >
                {isAuthoritative ? t("systemSettings.enforcementMode.authoritative") : t("systemSettings.enforcementMode.shadow")}
              </span>
              {status.ready_for_authoritative ? (
                <span style={{ fontSize: "var(--font-size-sm)", color: "var(--color-success)" }}>
                  {t("systemSettings.enforcementMode.zeroMismatches")}
                </span>
              ) : (
                <span style={{ fontSize: "var(--font-size-sm)", color: "var(--color-warning)" }}>
                  {t("systemSettings.enforcementMode.pendingMismatches", { count: status.pending_mismatch_count })}
                </span>
              )}
            </div>

            <p style={hintStyle} data-testid="enforcement-meta">
              {t("systemSettings.enforcementMode.meta", {
                count: status.pending_mismatch_count,
                days: status.mismatch_window_days,
                lastAt: fmtRelative(status.last_mismatch_at, t("systemSettings.enforcementMode.never")),
              })}
            </p>
            {status.advisory_note && (
              <p style={hintStyle} data-testid="enforcement-advisory">
                {status.advisory_note}
              </p>
            )}

            {error && (
              <p role="alert" style={{ color: "var(--color-danger)", fontSize: "var(--font-size-sm)" }}>
                {error}
              </p>
            )}

            <div style={{ marginTop: "var(--space-3)" }}>
              {isAuthoritative ? (
                <button
                  type="button"
                  data-testid="enforcement-rollback-btn"
                  onClick={() => void handleRollback()}
                  disabled={rollingBack}
                  style={{
                    background: "transparent",
                    color: "var(--color-warning)",
                    border: "1px solid var(--color-warning)",
                    borderRadius: "var(--radius-md)",
                    padding: "var(--space-2) var(--space-4)",
                    fontSize: "var(--font-size-sm)",
                    fontWeight: 600,
                    cursor: rollingBack ? "not-allowed" : "pointer",
                    opacity: rollingBack ? 0.5 : 1,
                  }}
                >
                  {rollingBack ? "…" : t("systemSettings.enforcementMode.rollbackButton")}
                </button>
              ) : (
                <button
                  type="button"
                  data-testid="enforcement-flip-btn"
                  onClick={() => setShowFlipDialog(true)}
                  style={primaryButtonStyle}
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
    </section>
  );
}
