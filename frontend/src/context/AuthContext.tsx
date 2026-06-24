/**
 * ARCH-L1-001 ReactFrontend — Authentication Context.
 *
 * leaf_id: COMP-RF-001 (NavigationShell / AuthGate / TokenManager)
 * req_id:  REQ-L2-RF-010 (Bearer-Token auth), REQ-L3-RF001-001
 *
 * Manages auth state and token lifecycle.
 * On mount: restores token from sessionStorage.
 * On 401:   clears token, redirects to /login.
 */

import React, {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  type ReactNode,
} from "react";
import { setAuthToken, setUnauthorizedHandler } from "../api/client";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface AuthState {
  isAuthenticated: boolean;
  token: string | null;
  login: (token: string) => void;
  logout: () => void;
}

// ---------------------------------------------------------------------------
// Context
// ---------------------------------------------------------------------------

const AuthContext = createContext<AuthState | null>(null);

const TOKEN_KEY = "reqflow_token";

export function AuthProvider({
  children,
  onUnauthorized,
}: {
  children: ReactNode;
  onUnauthorized?: () => void;
}): JSX.Element {
  const [token, setToken] = useState<string | null>(() =>
    sessionStorage.getItem(TOKEN_KEY)
  );

  // Keep API client in sync
  useEffect(() => {
    setAuthToken(token);
  }, [token]);

  // Wire 401 handler (REQ-L2-RF-010)
  useEffect(() => {
    setUnauthorizedHandler(() => {
      setToken(null);
      sessionStorage.removeItem(TOKEN_KEY);
      onUnauthorized?.();
    });
  }, [onUnauthorized]);

  const login = useCallback((newToken: string) => {
    sessionStorage.setItem(TOKEN_KEY, newToken);
    setToken(newToken);
  }, []);

  const logout = useCallback(() => {
    sessionStorage.removeItem(TOKEN_KEY);
    setToken(null);
  }, []);

  const value: AuthState = {
    isAuthenticated: !!token,
    token,
    login,
    logout,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
