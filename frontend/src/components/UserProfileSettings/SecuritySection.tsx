/**
 * ARCH-L1-001 ReactFrontend — SecuritySection (UserProfileSettings).
 *
 * leaf_id: COMP-RF-006 (UserProfileSettings — second factor)
 * req_id:  REQ-L2-RF-010 (auth), Plan E / WP E3.8 (#1308)
 *
 * Self-service TOTP management for the authenticated user:
 *   - status (enrolled / not set up, recovery codes left, policy requirement)
 *   - enroll (secret + otpauth URI, no QR — ENT-E5 = A)
 *   - confirm with the first authenticator code (returns the recovery codes)
 *   - rotate recovery codes (requires a current code)
 *   - disable (password + current code)
 *
 * State matrix: loading / error / not-enrolled / enrolled. No component-level
 * QR rendering; the otpauth URI is offered as a plain link per ENT-E5 = A.
 */

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import {
  confirmTotp,
  disableMfa,
  enrollTotp,
  getMfaStatus,
  regenerateRecoveryCodes,
  type MfaStatus,
  type TotpEnrollment,
} from "../../api/mfa";
import styles from "./SecuritySection.module.css";

type Phase = "loading" | "ready" | "error";

function formatConfirmedAt(iso: string | null): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleDateString();
  } catch {
    return iso;
  }
}

export function SecuritySection(): JSX.Element {
  const { t } = useTranslation();

  const [phase, setPhase] = useState<Phase>("loading");
  const [status, setStatus] = useState<MfaStatus | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [enrollment, setEnrollment] = useState<TotpEnrollment | null>(null);
  const [confirmCode, setConfirmCode] = useState("");
  const [recoveryCodes, setRecoveryCodes] = useState<string[] | null>(null);

  const [showRegenerate, setShowRegenerate] = useState(false);
  const [regenerateCode, setRegenerateCode] = useState("");
  const [showDisable, setShowDisable] = useState(false);
  const [disablePassword, setDisablePassword] = useState("");
  const [disableCode, setDisableCode] = useState("");

  /**
   * One-time plaintext recovery codes are never kept beyond the reveal they
   * belong to: not across a status refresh, and not across the component's
   * lifetime. Only the successful confirm/regenerate response may set them.
   */
  const clearRecoveryCodes = useCallback((): void => {
    setRecoveryCodes(null);
  }, []);

  // Drop the plaintext array when the settings panel unmounts.
  useEffect(() => clearRecoveryCodes, [clearRecoveryCodes]);

  const load = useCallback(async (): Promise<void> => {
    clearRecoveryCodes();
    setPhase("loading");
    setActionError(null);
    try {
      setStatus(await getMfaStatus());
      setPhase("ready");
    } catch {
      setPhase("error");
    }
  }, [clearRecoveryCodes]);

  useEffect(() => {
    void load();
  }, [load]);

  const runAction = useCallback(
    async (action: () => Promise<void>): Promise<void> => {
      setBusy(true);
      setActionError(null);
      try {
        await action();
      } catch {
        setActionError(t("mfa.error"));
      } finally {
        setBusy(false);
      }
    },
    [t]
  );

  /**
   * Best-effort re-read after a successful mutation. The optimistic state the
   * caller already wrote stays authoritative when this fails. A status refresh
   * also drops any plaintext recovery codes still on screen.
   */
  const refreshStatus = useCallback(async (): Promise<void> => {
    clearRecoveryCodes();
    try {
      setStatus(await getMfaStatus());
    } catch {
      // Keep the optimistic state.
    }
  }, [clearRecoveryCodes]);

  const handleEnroll = useCallback((): void => {
    void runAction(async () => {
      setEnrollment(await enrollTotp());
      setRecoveryCodes(null);
    });
  }, [runAction]);

  const handleConfirm = useCallback(
    (event: FormEvent): void => {
      event.preventDefault();
      if (!confirmCode.trim()) return;
      void runAction(async () => {
        const result = await confirmTotp(confirmCode.trim());
        setRecoveryCodes(result.recovery_codes);
        setEnrollment(null);
        setConfirmCode("");
        setStatus((previous) =>
          previous
            ? {
                ...previous,
                enrolled: true,
                confirmed_at: result.confirmed_at,
                recovery_codes_remaining: result.recovery_codes.length,
              }
            : previous
        );
      });
    },
    [confirmCode, runAction]
  );

  const handleRegenerate = useCallback(
    (event: FormEvent): void => {
      event.preventDefault();
      if (!regenerateCode.trim()) return;
      void runAction(async () => {
        const result = await regenerateRecoveryCodes(regenerateCode.trim());
        setRecoveryCodes(result.recovery_codes);
        setRegenerateCode("");
        setShowRegenerate(false);
        setStatus((previous) =>
          previous
            ? {
                ...previous,
                recovery_codes_remaining: result.recovery_codes.length,
              }
            : previous
        );
      });
    },
    [regenerateCode, runAction]
  );

  const handleDisable = useCallback(
    (event: FormEvent): void => {
      event.preventDefault();
      if (!disablePassword || !disableCode.trim()) return;
      void runAction(async () => {
        await disableMfa(disablePassword, disableCode.trim());
        setDisablePassword("");
        setDisableCode("");
        setShowDisable(false);
        clearRecoveryCodes();
        setEnrollment(null);
        setStatus((previous) =>
          previous
            ? {
                ...previous,
                enrolled: false,
                confirmed_at: null,
                recovery_codes_remaining: 0,
              }
            : previous
        );
        await refreshStatus();
      });
    },
    [disablePassword, disableCode, runAction, clearRecoveryCodes, refreshStatus]
  );

  const handleCopy = useCallback((): void => {
    if (!recoveryCodes) return;
    void navigator.clipboard?.writeText(recoveryCodes.join("\n"));
  }, [recoveryCodes]);

  const handleDownload = useCallback((): void => {
    if (!recoveryCodes) return;
    const blob = new Blob([recoveryCodes.join("\n") + "\n"], {
      type: "text/plain",
    });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "reqogniloom-recovery-codes.txt";
    anchor.click();
    URL.revokeObjectURL(url);
  }, [recoveryCodes]);

  return (
    <section className={styles.section} data-testid="mfa-section">
      <h2 className={styles.heading}>{t("mfa.title")}</h2>

      {phase === "loading" && (
        <p role="status" className={styles.loadingText}>
          {t("loading")}
        </p>
      )}

      {phase === "error" && (
        <p role="alert" className={styles.error} data-testid="mfa-error">
          {t("mfa.error")}
        </p>
      )}

      {phase === "ready" && status && (
        <>
          <div className={styles.statusRow}>
            <p className={styles.statusText} data-testid="mfa-status">
              {status.enrolled
                ? t("mfa.statusOn", {
                    date: formatConfirmedAt(status.confirmed_at),
                  })
                : t("mfa.statusOff")}
            </p>
            {status.required && (
              <span className={styles.policyBadge}>
                {t("mfa.requiredByPolicy")}
              </span>
            )}
          </div>

          {actionError && (
            <p role="alert" className={styles.error} data-testid="mfa-error">
              {actionError}
            </p>
          )}

          {/* --- Not enrolled: start enrollment -------------------------- */}
          {!status.enrolled && !enrollment && (
            <div className={styles.actions}>
              <button
                type="button"
                className="btn-primary"
                data-testid="mfa-enroll-btn"
                onClick={handleEnroll}
                disabled={busy}
              >
                {t("mfa.enroll")}
              </button>
            </div>
          )}

          {/* --- Pending enrollment: secret + first code ----------------- */}
          {!status.enrolled && enrollment && (
            <div className={styles.card}>
              <p className={styles.hint}>{t("mfa.secretHint")}</p>
              <code className={styles.secret} data-testid="mfa-secret">
                {enrollment.secret}
              </code>
              {/* Only a TOTP provisioning URI may become a link. Anything else
                  (a javascript:/data: URI, or a server bug) stays unrendered;
                  the secret above remains the usable provisioning material. */}
              {enrollment.otpauth_uri.startsWith("otpauth://totp/") && (
                <a
                  className={styles.link}
                  data-testid="mfa-otpauth-link"
                  href={enrollment.otpauth_uri}
                >
                  {enrollment.otpauth_uri}
                </a>
              )}
              <form onSubmit={handleConfirm}>
                <label className={styles.fieldLabel} htmlFor="mfa-confirm-code">
                  {t("login.mfa.codeLabel")}
                </label>
                <input
                  id="mfa-confirm-code"
                  className={styles.input}
                  data-testid="mfa-confirm-code-input"
                  type="text"
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  value={confirmCode}
                  onChange={(event) => setConfirmCode(event.target.value)}
                  disabled={busy}
                />
                <button
                  type="submit"
                  className="btn-primary"
                  data-testid="mfa-confirm-btn"
                  disabled={busy || !confirmCode.trim()}
                >
                  {t("mfa.confirm")}
                </button>
              </form>
            </div>
          )}

          {/* --- Enrolled: status, recovery codes, rotate / disable ------ */}
          {status.enrolled && (
            <>
              <p className={styles.statusText}>
                {t("mfa.remaining", {
                  count: status.recovery_codes_remaining,
                })}
              </p>

              {recoveryCodes && (
                <div className={styles.card} data-testid="mfa-recovery-codes">
                  <p className={styles.statusText}>{t("mfa.recoveryTitle")}</p>
                  <ul className={styles.codeList}>
                    {recoveryCodes.map((code) => (
                      <li key={code} className={styles.code}>
                        {code}
                      </li>
                    ))}
                  </ul>
                  <div className={styles.actions}>
                    <button
                      type="button"
                      className="btn-secondary"
                      data-testid="mfa-recovery-copy-btn"
                      onClick={handleCopy}
                    >
                      {t("mfa.copy")}
                    </button>
                    <button
                      type="button"
                      className="btn-secondary"
                      data-testid="mfa-recovery-download-btn"
                      onClick={handleDownload}
                    >
                      {t("mfa.download")}
                    </button>
                    <button
                      type="button"
                      className="btn-ghost"
                      data-testid="mfa-recovery-dismiss-btn"
                      onClick={clearRecoveryCodes}
                    >
                      {t("mfa.recoveryDismiss")}
                    </button>
                  </div>
                </div>
              )}

              <div className={styles.actions}>
                <button
                  type="button"
                  className="btn-secondary"
                  data-testid="mfa-regenerate-btn"
                  onClick={() => setShowRegenerate((visible) => !visible)}
                  disabled={busy}
                >
                  {t("mfa.regenerate")}
                </button>
                <button
                  type="button"
                  className="btn-danger"
                  data-testid="mfa-disable-btn"
                  onClick={() => setShowDisable((visible) => !visible)}
                  disabled={busy}
                >
                  {t("mfa.disable")}
                </button>
              </div>

              {showRegenerate && (
                <form className={styles.card} onSubmit={handleRegenerate}>
                  <label
                    className={styles.fieldLabel}
                    htmlFor="mfa-regenerate-code"
                  >
                    {t("login.mfa.codeLabel")}
                  </label>
                  <input
                    id="mfa-regenerate-code"
                    className={styles.input}
                    data-testid="mfa-regenerate-code-input"
                    type="text"
                    inputMode="numeric"
                    autoComplete="one-time-code"
                    value={regenerateCode}
                    onChange={(event) => setRegenerateCode(event.target.value)}
                    disabled={busy}
                  />
                  <button
                    type="submit"
                    className="btn-primary"
                    data-testid="mfa-regenerate-submit"
                    disabled={busy || !regenerateCode.trim()}
                  >
                    {t("mfa.regenerate")}
                  </button>
                </form>
              )}

              {showDisable && (
                <form className={styles.card} onSubmit={handleDisable}>
                  <label
                    className={styles.fieldLabel}
                    htmlFor="mfa-disable-password"
                  >
                    {t("login.passwordLabel")}
                  </label>
                  <input
                    id="mfa-disable-password"
                    className={styles.input}
                    data-testid="mfa-disable-password-input"
                    type="password"
                    autoComplete="current-password"
                    value={disablePassword}
                    onChange={(event) => setDisablePassword(event.target.value)}
                    disabled={busy}
                  />
                  <label className={styles.fieldLabel} htmlFor="mfa-disable-code">
                    {t("login.mfa.codeLabel")}
                  </label>
                  <input
                    id="mfa-disable-code"
                    className={styles.input}
                    data-testid="mfa-disable-code-input"
                    type="text"
                    inputMode="numeric"
                    autoComplete="one-time-code"
                    value={disableCode}
                    onChange={(event) => setDisableCode(event.target.value)}
                    disabled={busy}
                  />
                  <button
                    type="submit"
                    className="btn-danger"
                    data-testid="mfa-disable-submit"
                    disabled={busy || !disablePassword || !disableCode.trim()}
                  >
                    {t("mfa.disable")}
                  </button>
                </form>
              )}
            </>
          )}
        </>
      )}
    </section>
  );
}
