/**
 * ARCH-L1-001 ReactFrontend — Login Page.
 *
 * leaf_id: COMP-RF-001 (NavigationShell)
 * req_id:  REQ-L2-RF-010 (Authentication, 401/403 → redirect to login)
 *
 * Credential-based login form (username + password).
 * Calls POST /api/v1/auth/login/ via AuthContext.login().
 * On success: stores token + user, navigates to the originally requested route.
 * On failure: displays i18n error message.
 */

import { useEffect, useState, type FormEvent } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth, type LoginOutcome } from "../../context/AuthContext";
import { MfaLoginError } from "../../api/mfa";
import { versionApi, type VersionInfo } from "../../api/version";
import { bannersApi, type LoginBanner } from "../../api/banners";
import { APP_NAME } from "../../config/app-name";
import { safeSessionStorage } from "../../utils/safeStorage";
import styles from "./LoginPage.module.css";

const LOGIN_BANNER_CLASS: Record<LoginBanner["level"], string> = {
  neutral: styles.bannerNeutral,
  info: styles.bannerInfo,
  warning: styles.bannerWarning,
  critical: styles.bannerCritical,
};

/**
 * Dismiss key for the login-page banner.
 *
 * Same scheme as `BannerStack`'s (`banner-dismissed-<scope>-<id>-<updated_at>`)
 * with `scope=global-login`, per the design spec. Deliberately duplicated
 * rather than shared: `BannerStack`'s helpers are module-private, and hoisting
 * five lines into a shared module for two call sites that already differ in
 * their scope literal would be more indirection than it removes.
 *
 * `sessionStorage`, not `localStorage`: the dismissal must reset on the next
 * login. Keying on `updated_at` means an admin editing the message
 * automatically invalidates every prior dismissal.
 */
function loginDismissKey(banner: LoginBanner): string {
  return `banner-dismissed-global-login-${banner.id}-${banner.updated_at ?? ""}`;
}

function isLoginBannerDismissed(banner: LoginBanner): boolean {
  return safeSessionStorage.getItem(loginDismissKey(banner)) === "1";
}

export function LoginPage(): JSX.Element {
  const { t } = useTranslation();
  const { login, completeMfaLogin } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  // Second step (Plan E / WP E3.8, #1308): the password step returned a
  // challenge instead of a session.
  const [mfaOutcome, setMfaOutcome] = useState<LoginOutcome | null>(null);
  const [mfaCode, setMfaCode] = useState("");
  const [useRecoveryCode, setUseRecoveryCode] = useState(false);
  const [mfaError, setMfaError] = useState<string | null>(null);
  const [isMfaSubmitting, setIsMfaSubmitting] = useState(false);

  // Deployed version, fetched from the public /api/v1/version/ endpoint
  // (AllowAny — works pre-login). Non-blocking and non-critical: a slow or
  // failed fetch must never gate the login form.
  const [versionInfo, setVersionInfo] = useState<VersionInfo | null>(null);

  // System/workspace banner, fetched from the public /api/v1/public/banners/login/
  // endpoint. Non-blocking and non-critical: a slow or failed fetch must never gate
  // the login form.
  const [loginBanner, setLoginBanner] = useState<LoginBanner | null>(null);
  const [bannerDismissed, setBannerDismissed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void versionApi
      .getVersion()
      .then((info) => {
        if (!cancelled) setVersionInfo(info);
      })
      .catch(() => {
        // Silently omit the version marker on failure.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    void bannersApi
      .getLoginBanner()
      .then((banner) => {
        if (cancelled) return;
        setLoginBanner(banner);
        // Check the stored dismissal on arrival, not on click only: a banner
        // already dismissed earlier in this browser session must stay hidden
        // across reloads of the login page.
        setBannerDismissed(banner ? isLoginBannerDismissed(banner) : false);
      })
      .catch(() => {
        // Silently omit the banner on failure — must never block the login form.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const versionLabel = versionInfo
    ? versionInfo.app_version && versionInfo.app_version !== "unknown"
      ? `v${versionInfo.app_version}`
      : versionInfo.commit_short !== "unknown"
        ? t("nav.buildVersion", { sha: versionInfo.commit_short, defaultValue: `Build ${versionInfo.commit_short}` })
        : null
    : null;

  const locationState = location.state as
    | { from?: { pathname: string }; sessionExpired?: boolean }
    | null;
  const from = locationState?.from?.pathname ?? "/";
  // GitHub #135: the token-refresh client redirects here with
  // sessionExpired=true when a mid-session token expiry could not be
  // silently refreshed — show that distinctly from a wrong-password error so
  // the user understands their in-progress work wasn't rejected, the session
  // simply timed out.
  const [sessionExpired] = useState(locationState?.sessionExpired ?? false);

  const handleSubmit = async (e: FormEvent): Promise<void> => {
    e.preventDefault();
    setError(null);

    if (!username.trim()) {
      setError(t("login.usernameRequired"));
      return;
    }
    if (!password) {
      setError(t("login.passwordRequired"));
      return;
    }

    setIsLoading(true);
    try {
      const outcome = await login({ username: username.trim(), password });
      if (outcome.kind === "authenticated") {
        navigate(from, { replace: true });
        return;
      }
      setMfaOutcome(outcome);
      setMfaCode("");
      setMfaError(null);
      setUseRecoveryCode(false);
    } catch {
      setError(t("login.invalidCredentials"));
    } finally {
      setIsLoading(false);
    }
  };

  const handleMfaSubmit = async (e: FormEvent): Promise<void> => {
    e.preventDefault();
    if (!mfaOutcome || mfaOutcome.kind !== "mfa") return;
    const value = mfaCode.trim();
    if (!value) return;

    setMfaError(null);
    setIsMfaSubmitting(true);
    try {
      await completeMfaLogin(
        mfaOutcome.challenge,
        useRecoveryCode ? { recoveryCode: value } : { code: value }
      );
      navigate(from, { replace: true });
    } catch (err) {
      const code = err instanceof MfaLoginError ? err.code : "";
      if (code === "MFA_LOCKED") {
        const seconds = err instanceof MfaLoginError ? err.retryAfterSeconds ?? 60 : 60;
        setMfaError(
          t("login.mfa.locked", { minutes: Math.max(1, Math.ceil(seconds / 60)) })
        );
      } else if (code === "MFA_CHALLENGE_INVALID") {
        // The challenge expired or was already used: start over at step 1.
        setMfaOutcome(null);
        setMfaCode("");
        setError(t("login.mfa.expired"));
      } else {
        setMfaError(t("login.mfa.invalidCode"));
      }
    } finally {
      setIsMfaSubmitting(false);
    }
  };

  return (
    <div className={styles.page}>
      {loginBanner && !bannerDismissed && (
        <div
          data-testid="login-page-banner"
          role="status"
          className={`${styles.banner} ${LOGIN_BANNER_CLASS[loginBanner.level]}`}
        >
          {/* Plain text, never Markdown: this endpoint is unauthenticated, so
              its content must not be able to render links or HTML on the login
              page. That is a deliberate, security-motivated divergence from
              BannerStack's in-app Markdown rendering. */}
          <span className={styles.bannerMessage}>{loginBanner.message}</span>
          {loginBanner.dismissible && (
            <button
              type="button"
              className={`btn-icon ${styles.bannerDismiss}`}
              data-testid="login-page-banner-dismiss"
              aria-label={t("banners.dismiss", "Dismiss")}
              onClick={() => {
                safeSessionStorage.setItem(loginDismissKey(loginBanner), "1");
                setBannerDismissed(true);
              }}
            >
              ×
            </button>
          )}
        </div>
      )}
      {mfaOutcome ? (
        <form
          onSubmit={handleMfaSubmit}
          className={styles.form}
          data-testid="login-mfa-step"
        >
          <h2 className={styles.formTitle}>{t("login.mfa.title")}</h2>
          {mfaOutcome.kind === "enroll" ? (
            <p role="alert" className={styles.mutedNotice}>
              {t("login.mfa.enrollRequired")}
            </p>
          ) : (
            <>
              <label htmlFor="login-mfa-code" className={styles.fieldLabel}>
                {useRecoveryCode
                  ? t("login.mfa.recoveryLabel")
                  : t("login.mfa.codeLabel")}
              </label>
              {useRecoveryCode ? (
                <input
                  id="login-mfa-code"
                  data-testid="login-mfa-recovery-input"
                  type="text"
                  autoComplete="one-time-code"
                  value={mfaCode}
                  onChange={(e) => setMfaCode(e.target.value)}
                  disabled={isMfaSubmitting}
                  className={styles.input}
                />
              ) : (
                <input
                  id="login-mfa-code"
                  data-testid="login-mfa-code-input"
                  type="text"
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  value={mfaCode}
                  onChange={(e) => setMfaCode(e.target.value)}
                  disabled={isMfaSubmitting}
                  className={styles.input}
                />
              )}
              <button
                type="button"
                data-testid="login-mfa-recovery-toggle"
                className={`btn-ghost ${styles.submitButton}`}
                onClick={() => {
                  setUseRecoveryCode((current) => !current);
                  setMfaCode("");
                  setMfaError(null);
                }}
                disabled={isMfaSubmitting}
              >
                {useRecoveryCode
                  ? t("login.mfa.codeLabel")
                  : t("login.mfa.useRecovery")}
              </button>
              {mfaError && (
                <p
                  role="alert"
                  data-testid="login-mfa-error"
                  className={styles.errorText}
                >
                  {mfaError}
                </p>
              )}
              <button
                type="submit"
                data-testid="login-mfa-submit"
                disabled={isMfaSubmitting || !mfaCode.trim()}
                className={`btn-primary ${styles.submitButton}`}
              >
                {isMfaSubmitting ? t("loading") : t("login.mfa.submit")}
              </button>
            </>
          )}
        </form>
      ) : (
        <form onSubmit={handleSubmit} className={styles.form}>
          <div className={styles.brandBlock}>
            <div className={styles.brandRow}>
              <span aria-hidden="true" className={styles.brandDot} />
              <h1 className={styles.appTitle}>{APP_NAME}</h1>
            </div>
            <p className={styles.tagline}>AI-native Requirements Management</p>
            {versionLabel && (
              <span data-testid="login-version-indicator" className={styles.version}>
                {versionLabel}
              </span>
            )}
          </div>
          <h2 className={styles.formTitle}>{t("login.title")}</h2>
          {error && (
            <p role="alert" className={styles.errorText}>
              {error}
            </p>
          )}
          {!error && sessionExpired && (
            <p
              role="alert"
              data-testid="login-session-expired-notice"
              className={styles.mutedNotice}
            >
              {t("login.sessionExpired")}
            </p>
          )}
          <label htmlFor="username-input" className={styles.fieldLabel}>
            {t("login.usernameLabel")}
          </label>
          <input
            id="username-input"
            data-testid="login-username-input"
            type="text"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            placeholder={t("login.usernamePlaceholder")}
            autoComplete="username"
            disabled={isLoading}
            className={styles.input}
          />
          <label htmlFor="password-input" className={styles.fieldLabel}>
            {t("login.passwordLabel")}
          </label>
          <input
            id="password-input"
            data-testid="login-password-input"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder={t("login.passwordPlaceholder")}
            autoComplete="current-password"
            disabled={isLoading}
            className={styles.input}
          />
          <button
            type="submit"
            data-testid="login-submit-button"
            disabled={isLoading}
            className={`btn-primary ${styles.submitButton}`}
          >
            {isLoading ? t("loading") : t("login.submit")}
          </button>
        </form>
      )}
    </div>
  );
}
