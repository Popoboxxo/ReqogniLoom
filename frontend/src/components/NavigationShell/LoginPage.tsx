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
import { useAuth } from "../../context/AuthContext";
import { versionApi, type VersionInfo } from "../../api/version";
import { bannersApi, type LoginBanner } from "../../api/banners";
import { APP_NAME } from "../../config/app-name";

const LOGIN_BANNER_COLORS: Record<LoginBanner["level"], string> = {
  neutral: "var(--color-text-muted)",
  info: "var(--color-primary)",
  warning: "var(--color-warning)",
  critical: "var(--color-danger)",
};

export function LoginPage(): JSX.Element {
  const { t } = useTranslation();
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  // Deployed version, fetched from the public /api/v1/version/ endpoint
  // (AllowAny — works pre-login). Non-blocking and non-critical: a slow or
  // failed fetch must never gate the login form.
  const [versionInfo, setVersionInfo] = useState<VersionInfo | null>(null);

  // System/workspace banner, fetched from the public /api/v1/public/banners/login/
  // endpoint. Non-blocking and non-critical: a slow or failed fetch must never gate
  // the login form.
  const [loginBanner, setLoginBanner] = useState<LoginBanner | null>(null);

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
        if (!cancelled) setLoginBanner(banner);
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
      await login({ username: username.trim(), password });
      navigate(from, { replace: true });
    } catch {
      setError(t("login.invalidCredentials"));
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div
      style={{
        display: "flex",
        justifyContent: "center",
        alignItems: "center",
        minHeight: "100vh",
        fontFamily: "var(--font-sans)",
        background: "var(--color-surface)",
      }}
    >
      {loginBanner && (
        <div
          data-testid="login-page-banner"
          role="status"
          style={{
            position: "fixed",
            top: 0,
            left: 0,
            right: 0,
            padding: "var(--space-2) var(--space-4)",
            borderBottom: `3px solid ${LOGIN_BANNER_COLORS[loginBanner.level]}`,
            background: "var(--color-surface-raised)",
            color: "var(--color-text)",
            fontSize: "var(--font-size-sm)",
            textAlign: "center",
          }}
        >
          {loginBanner.message}
        </div>
      )}
      <form
        onSubmit={handleSubmit}
        style={{
          display: "flex",
          flexDirection: "column",
          gap: "var(--space-4)",
          minWidth: "320px",
          padding: "var(--space-8)",
          background: "var(--color-surface-raised)",
          border: "1px solid var(--color-border)",
          borderRadius: "var(--radius-lg)",
          boxShadow: "var(--shadow-card)",
        }}
      >
        <div style={{ textAlign: "center", marginBottom: "var(--space-2)" }}>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              gap: "var(--space-2)",
              marginBottom: "var(--space-2)",
            }}
          >
            <span
              aria-hidden="true"
              style={{
                display: "inline-block",
                width: "10px",
                height: "10px",
                borderRadius: "var(--radius-full)",
                background: "var(--color-primary)",
                boxShadow: "0 0 0 3px rgba(99,102,241,0.20)",
              }}
            />
            <h1 style={{ fontSize: "var(--font-size-2xl)", fontWeight: 700, margin: 0, color: "var(--color-text)" }}>
              {APP_NAME}
            </h1>
          </div>
          <p style={{ fontSize: "var(--font-size-sm)", color: "var(--color-text-muted)", margin: 0 }}>
            AI-native Requirements Management
          </p>
          {versionLabel && (
            <span
              data-testid="login-version-indicator"
              style={{ fontSize: "var(--font-size-xs)", color: "var(--color-text-muted)", opacity: 0.7 }}
            >
              {versionLabel}
            </span>
          )}
        </div>
        <h2 style={{ fontSize: "var(--font-size-md)", fontWeight: 600, margin: 0, color: "var(--color-text)" }}>
          {t("login.title")}
        </h2>
        {error && (
          <p role="alert" style={{ color: "var(--color-danger)", fontSize: "var(--font-size-sm)", margin: 0 }}>
            {error}
          </p>
        )}
        {!error && sessionExpired && (
          <p
            role="alert"
            data-testid="login-session-expired-notice"
            style={{ color: "var(--color-text-muted)", fontSize: "var(--font-size-sm)", margin: 0 }}
          >
            {t("login.sessionExpired")}
          </p>
        )}
        <label htmlFor="username-input" style={{ fontSize: "var(--font-size-sm)", fontWeight: 600, color: "var(--color-text)" }}>
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
          style={{
            padding: "var(--space-2) var(--space-3)",
            fontSize: "var(--font-size-sm)",
            borderRadius: "var(--radius-md)",
            border: "1px solid var(--color-border)",
            background: "var(--color-surface)",
            color: "var(--color-text)",
          }}
        />
        <label htmlFor="password-input" style={{ fontSize: "var(--font-size-sm)", fontWeight: 600, color: "var(--color-text)" }}>
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
          style={{
            padding: "var(--space-2) var(--space-3)",
            fontSize: "var(--font-size-sm)",
            borderRadius: "var(--radius-md)",
            border: "1px solid var(--color-border)",
            background: "var(--color-surface)",
            color: "var(--color-text)",
          }}
        />
        <button
          type="submit"
          data-testid="login-submit-button"
          disabled={isLoading}
          className="btn-primary"
          style={{ justifyContent: "center", width: "100%", fontSize: "var(--font-size-sm)" }}
        >
          {isLoading ? t("loading") : t("login.submit")}
        </button>
      </form>
    </div>
  );
}
