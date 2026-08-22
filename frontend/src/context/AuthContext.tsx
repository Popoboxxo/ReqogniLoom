/**
 * ARCH-L1-001 ReactFrontend — Authentication Context.
 *
 * leaf_id: COMP-RF-001 (NavigationShell / AuthGate / TokenManager)
 * req_id:  REQ-L2-RF-010 (auth), REQ-L3-RF001-001, REQ-052 (httpOnly-cookie XSS-fix)
 *
 * The access token lives in an httpOnly cookie the browser attaches
 * automatically (REQ-052) — it is never stored in sessionStorage/JS, closing
 * the XSS token-theft vector. Consequently:
 * - On mount the session is restored by calling GET /auth/me/ (not storage).
 *   A "restoring" status prevents a login-flash on reload.
 * - On login the server sets the cookie; the body token is ignored.
 * - On logout the server clears the cookie via POST /auth/logout/.
 * - On 401/403 the API client clears state and the caller redirects to /login.
 */

import { createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  useMemo,
  type ReactNode,
} from "react";
import {
  apiClient,
  resetUnauthorizedGuard,
  setUnauthorizedHandler,
} from "../api/client";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface AuthUser {
  id: string;
  username: string;
  email: string;
  first_name: string;
  last_name: string;
  is_active: boolean;
  tenant_id: string | null;
  roles: string[];
}

/** Editable subset of the user profile (REQ-006). */
export interface ProfileUpdate {
  first_name: string;
  last_name: string;
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
  is_tenant_admin: boolean;
}

/**
 * Session restore lifecycle:
 * - "restoring"     — GET /auth/me/ in flight; AuthGate must not redirect yet.
 * - "authenticated" — a valid session cookie resolved to a user.
 * - "anonymous"     — no/invalid session.
 */
export type AuthStatus = "restoring" | "authenticated" | "anonymous";

/** Shape returned by GET /auth/me/ and POST /auth/login/. */
interface IdentityPayload {
  user: AuthUser;
  tenant_id: string | null;
  roles: string[];
  /**
   * Multi-user management design spec: whether the caller holds an active
   * tenant-admin role (`TenantRole`) — a tenant-wide concept distinct from
   * the workspace-scoped `roles` above. Optional/defaulted for backward
   * compatibility with any caller/mock that predates this field.
   */
  is_tenant_admin?: boolean;
}

export interface AuthState {
  isAuthenticated: boolean;
  status: AuthStatus;
  user: AuthUser | null;
  tenantId: string | null;
  roles: string[];
  /** Whether the caller holds an active tenant-admin role (`TenantRole`) —
   * gates the tenant-admin-only User Management surface. UX-only: real
   * enforcement lives server-side (`UserViewSet` / MCP `users` tool group). */
  isTenantAdmin: boolean;
  /** POST /api/v1/auth/login/ — resolves on success, rejects with error message on failure */
  login: (credentials: LoginCredentials) => Promise<void>;
  /** PATCH /api/v1/auth/me/ — update editable profile fields (REQ-006) */
  updateProfile: (update: ProfileUpdate) => Promise<void>;
  logout: () => void;
}

// ---------------------------------------------------------------------------
// Context
// ---------------------------------------------------------------------------

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({
  children,
  onUnauthorized,
}: {
  children: ReactNode;
  onUnauthorized?: () => void;
}): JSX.Element {
  const [status, setStatus] = useState<AuthStatus>("restoring");
  const [user, setUser] = useState<AuthUser | null>(null);
  const [tenantId, setTenantId] = useState<string | null>(null);
  const [roles, setRoles] = useState<string[]>([]);
  const [isTenantAdmin, setIsTenantAdmin] = useState<boolean>(false);

  const clearAuth = useCallback(() => {
    setUser(null);
    setTenantId(null);
    setRoles([]);
    setIsTenantAdmin(false);
    setStatus("anonymous");
  }, []);

  const applyIdentity = useCallback((data: IdentityPayload) => {
    setUser(data.user);
    setTenantId(data.tenant_id ?? null);
    setRoles(data.roles ?? []);
    setIsTenantAdmin(data.is_tenant_admin ?? false);
    setStatus("authenticated");
    // Re-arm the 401 notification guard (GitHub #135): a fresh/restored
    // session must be able to trigger the unauthorized handler again the
    // next time its access token actually expires and the refresh fails.
    resetUnauthorizedGuard();
  }, []);

  // Restore the session from the httpOnly cookie via GET /auth/me/ (REQ-052).
  // A 401 (no/expired cookie) simply resolves to the anonymous state.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await apiClient.get<IdentityPayload>("/auth/me/");
        if (cancelled) return;
        if (data?.user) applyIdentity(data);
        else clearAuth();
      } catch {
        if (!cancelled) clearAuth();
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [applyIdentity, clearAuth]);

  // Wire 401/403 handler (REQ-L2-RF-010)
  useEffect(() => {
    setUnauthorizedHandler(() => {
      clearAuth();
      onUnauthorized?.();
    });
  }, [onUnauthorized, clearAuth]);

  /** Performs credential-based login via POST /api/v1/auth/login/ */
  const login = useCallback(
    async (credentials: LoginCredentials): Promise<void> => {
      const response = await fetch("/api/v1/auth/login/", {
        method: "POST",
        // Persist the Set-Cookie the server returns on success (REQ-052).
        credentials: "same-origin",
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
      // The token is delivered as an httpOnly cookie by the server; the body
      // token is ignored here (Phase-1 backward-compat only, REQ-052).
      applyIdentity({
        user: data.user,
        tenant_id: data.tenant_id ?? null,
        roles: data.roles ?? [],
        is_tenant_admin: data.is_tenant_admin ?? false,
      });
    },
    [applyIdentity]
  );

  /** Updates the current user's profile via PATCH /api/v1/auth/me/ (REQ-006). */
  const updateProfile = useCallback(
    async (update: ProfileUpdate): Promise<void> => {
      const data = await apiClient.patch<{ user: AuthUser }>("/auth/me/", update);
      setUser(data.user);
    },
    []
  );

  const logout = useCallback(() => {
    // Best-effort server-side cookie clear (REQ-052); local state is cleared
    // regardless so the UI logs out even if the request fails.
    void apiClient.post("/auth/logout/", {}).catch(() => undefined);
    clearAuth();
  }, [clearAuth]);

  const value = useMemo<AuthState>(
    () => ({
      isAuthenticated: user !== null,
      status,
      user,
      tenantId,
      roles,
      isTenantAdmin,
      login,
      updateProfile,
      logout,
    }),
    [status, user, tenantId, roles, isTenantAdmin, login, updateProfile, logout]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
