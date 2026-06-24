/**
 * ARCH-L1-001 ReactFrontend — Login Page.
 *
 * leaf_id: COMP-RF-001 (NavigationShell)
 * req_id:  REQ-L2-RF-010 (Authentication, 401 → redirect to login)
 *
 * Simple token-based login form.
 * Accepts a Bearer token directly (no username/password OAuth in scope).
 * The backend's auth mechanism is Bearer token; login stores the token.
 */

import React, { useState, type FormEvent } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth } from "../../context/AuthContext";

export function LoginPage(): JSX.Element {
  const { t } = useTranslation();
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [token, setToken] = useState("");
  const [error, setError] = useState<string | null>(null);

  const from = (location.state as { from?: { pathname: string } })?.from?.pathname ?? "/";

  const handleSubmit = (e: FormEvent): void => {
    e.preventDefault();
    if (!token.trim()) {
      setError(t("login.tokenRequired"));
      return;
    }
    login(token.trim());
    navigate(from, { replace: true });
  };

  return (
    <div
      style={{
        display: "flex",
        justifyContent: "center",
        alignItems: "center",
        minHeight: "100vh",
        fontFamily: "sans-serif",
      }}
    >
      <form
        onSubmit={handleSubmit}
        style={{
          display: "flex",
          flexDirection: "column",
          gap: "1rem",
          minWidth: "320px",
          padding: "2rem",
          border: "1px solid #ddd",
          borderRadius: "8px",
        }}
      >
        <h2>{t("login.title")}</h2>
        {error && (
          <p role="alert" style={{ color: "red" }}>
            {error}
          </p>
        )}
        <label htmlFor="token-input">{t("login.tokenLabel")}</label>
        <input
          id="token-input"
          type="password"
          value={token}
          onChange={(e) => setToken(e.target.value)}
          placeholder={t("login.tokenPlaceholder")}
          autoComplete="current-password"
          style={{ padding: "0.5rem", fontSize: "1rem" }}
        />
        <button type="submit" style={{ padding: "0.75rem", fontSize: "1rem" }}>
          {t("login.submit")}
        </button>
      </form>
    </div>
  );
}
