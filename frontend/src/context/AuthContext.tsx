/**
 * ARCH-L1-001 ReactFrontend — Authentication Context.
 *
 * leaf_id: COMP-RF-001 (NavigationShell / AuthGate / TokenManager)
 * req_id:  REQ-L2-RF-010 (Bearer-Token auth), REQ-L3-RF001-001
 *
 * Manages auth state and token lifecycle.
 * On mount: restores token from sessionStorage.
 * On 401/403: clears token, redirects to /login.
 */

import { createContext,
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

export interface AuthUser {
  id: string;
  username: string;
  email: string;
  is_active: boolean;
  tenant_id: string | null;
  roles: string[];
}

export interface LoginCredentials {
  username: string;
  password: string;
}

export interface LoginResponse {
  token: string;
  user: AuthUser;
  tenant_id: string;
  roles: string[];
}

export interface AuthState {
  isAuthenticated: boolean;
  token: string | null;
  user: AuthUser | null;
  tenantId: string | null;
  roles: string[];
  /** POST /api/v1/auth/login/ — resolves on success, rejects with error message on failure */
  login: (credentials: LoginCredentials) => Promise<void>;
  logout: () => void;
}

// ---------------------------------------------------------------------------
// Context
// ---------------------------------------------------------------------------

const AuthContext = createContext<AuthState | null>(null);

const TOKEN_KEY = "reqflow_token";
const USER_KEY = "reqflow_user";

function parseStoredUser(): AuthUser | null {
  try {
    const raw = sessionStorage.getItem(USER_KEY);
    return raw ? (JSON.parse(raw) as AuthUser) : null;
  } catch {
    return null;
  }
}

export function AuthProvider({
  children,
  onUnauthorized,
}: {
  children: ReactNode;
  onUnauthorized?: () => void;
}): JSX.Element {
  const [token, setToken] = useState<string | null>(() => {
    const t = sessionStorage.getItem(TOKEN_KEY);
    // Sync immediately so WorkspaceContext can call the API on first render
    if (t) setAuthToken(t);
    return t;
  });
  const [user, setUser] = useState<AuthUser | null>(() => parseStoredUser());
  const [tenantId, setTenantId] = useState<string | null>(null);
  const [roles, setRoles] = useState<string[]>(() => {
    const stored = parseStoredUser();
    return stored?.roles ?? [];
  });

  // Keep API client in sync on subsequent token changes
  useEffect(() => {
    setAuthToken(token);
  }, [token]);

  // Wire 401/403 handler (REQ-L2-RF-010)
  useEffect(() => {
    setUnauthorizedHandler(() => {
      setToken(null);
      setUser(null);
      setTenantId(null);
      setRoles([]);
      sessionStorage.removeItem(TOKEN_KEY);
      sessionStorage.removeItem(USER_KEY);
      onUnauthorized?.();
    });
  }, [onUnauthorized]);

  /** Performs credential-based login via POST /api/v1/auth/login/ */
  const login = useCallback(
    async (credentials: LoginCredentials): Promise<void> => {
      const response = await fetch("/api/v1/auth/login/", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
        },
        body: JSON.stringify(credentials),
      });

      if (!response.ok) {
        let message = "Invalid credentials";
        try {
          const body = await response.json();
          if (body?.message) message = body.message;
          else if (body?.error) message = body.error;
        } catch {
          // use default
        }
        throw new Error(message);
      }

      const data: LoginResponse = await response.json();

      sessionStorage.setItem(TOKEN_KEY, data.token);
      sessionStorage.setItem(USER_KEY, JSON.stringify(data.user));
      // Sync token into apiClient BEFORE setToken triggers re-render + WorkspaceContext
      setAuthToken(data.token);
      setToken(data.token);
      setUser(data.user);
      setTenantId(data.tenant_id ?? null);
      setRoles(data.roles ?? []);
    },
    []
  );

  const logout = useCallback(() => {
    sessionStorage.removeItem(TOKEN_KEY);
    sessionStorage.removeItem(USER_KEY);
    setToken(null);
    setUser(null);
    setTenantId(null);
    setRoles([]);
  }, []);

  const value: AuthState = {
    isAuthenticated: !!token,
    token,
    user,
    tenantId,
    roles,
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
