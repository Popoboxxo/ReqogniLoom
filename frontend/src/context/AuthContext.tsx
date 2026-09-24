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
 * - On login the server sets the cookie; the body token is ignored — the field
 *   is deprecated server-side (#696) and not declared in `LoginResponse`, so
 *   the SPA cannot depend on it.
 * - On logout the server clears the cookie via POST /auth/logout/.
 * - On 401/403 the API client clears state and the caller redirects to /login.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import {
  advanceAuthSessionGeneration,
  apiClient,
  resetUnauthorizedGuard,
  setUnauthorizedHandler,
} from "../api/client";
import {
  installBluepencilReviewLayer,
  teardownBluepencilReviewLayer,
} from "../bluepencil/loader";
import {
  bluepencilIdentityFromUser,
  installBluepencilHost,
  setBluepencilIdentitySource,
} from "../bluepencil/host";

const AUTH_TRANSITION_TIMEOUT_MS = 30_000;

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

/**
 * Shape returned by POST /api/v1/auth/login/ — identity only.
 *
 * The backend additionally returns a `token` field for API/CI tooling. That
 * field is DEPRECATED (#696), can be switched off server-side with
 * `AUTH_LOGIN_INCLUDE_BODY_TOKEN=False`, and is deliberately NOT declared here
 * so TypeScript rejects any attempt to read or persist it — storing it in JS
 * would re-open the XSS token-theft vector REQ-052 closed. The SPA
 * authenticates through the httpOnly cookie the login response sets.
 */
export interface LoginResponse {
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

// Exported (not just via the `useAuth` hook) so ThemeContext can read it
// with `useContext` directly and tolerate being rendered without an
// AuthProvider ancestor (existing unit tests render `<ThemeProvider>`
// standalone) — see ThemeContext.tsx for why that fallback is safe.
export const AuthContext = createContext<AuthState | null>(null);

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
  const authGeneration = useRef(0);
  const cookieTransitionInFlight = useRef(0);
  const cookieTransitionTail = useRef<Promise<void>>(Promise.resolve());
  const loginAbortController = useRef<AbortController | null>(null);

  const clearAuth = useCallback(() => {
    setUser(null);
    setTenantId(null);
    setRoles([]);
    setIsTenantAdmin(false);
    setStatus("anonymous");
    setBluepencilIdentitySource(null);
  }, []);

  const invalidateAuth = useCallback(
    (teardownLayer = true) => {
      authGeneration.current += 1;
      if (teardownLayer) teardownBluepencilReviewLayer();
      clearAuth();
    },
    [clearAuth],
  );

  const enqueueCookieTransition = useCallback((operation: () => Promise<void>): Promise<void> => {
    const transition = cookieTransitionTail.current.then(async () => {
      cookieTransitionInFlight.current += 1;
      try {
        await operation();
      } finally {
        cookieTransitionInFlight.current = Math.max(0, cookieTransitionInFlight.current - 1);
      }
    });
    cookieTransitionTail.current = transition.catch(() => undefined);
    return transition;
  }, []);

  const applyIdentity = useCallback((data: IdentityPayload, generation: number) => {
    if (generation !== authGeneration.current) return;
    advanceAuthSessionGeneration();
    setUser(data.user);
    setTenantId(data.tenant_id ?? null);
    setRoles(data.roles ?? []);
    setIsTenantAdmin(data.is_tenant_admin ?? false);
    setStatus("authenticated");
    installBluepencilHost();
    setBluepencilIdentitySource(() => bluepencilIdentityFromUser(data.user));
    void installBluepencilReviewLayer();
    resetUnauthorizedGuard();
  }, []);

  // Restore the session from the httpOnly cookie via GET /auth/me/ (REQ-052).
  // A 401 (no/expired cookie) simply resolves to the anonymous state.
  useEffect(() => {
    let cancelled = false;
    const generation = authGeneration.current;
    (async () => {
      try {
        const data = await apiClient.get<IdentityPayload>("/auth/me/", {
          suppressUnauthorizedNotification: true,
        });
        if (cancelled) return;
        if (generation !== authGeneration.current) return;
        if (data?.user) applyIdentity(data, generation);
        else clearAuth();
      } catch {
        if (!cancelled && generation === authGeneration.current) clearAuth();
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [applyIdentity, clearAuth]);

  // Wire 401/403 handler (REQ-L2-RF-010)
  useEffect(() => {
    setUnauthorizedHandler(() => {
      if (cookieTransitionInFlight.current > 0) return;
      advanceAuthSessionGeneration();
      invalidateAuth();
      onUnauthorized?.();
    });
  }, [onUnauthorized, invalidateAuth]);

  const login = useCallback(
    (credentials: LoginCredentials): Promise<void> => {
      advanceAuthSessionGeneration();
      loginAbortController.current?.abort();
      const controller = new AbortController();
      loginAbortController.current = controller;
      const generation = authGeneration.current + 1;
      authGeneration.current = generation;
      return enqueueCookieTransition(async () => {
        let timedOut = false;
        const timeout = setTimeout(() => {
          timedOut = true;
          controller.abort();
        }, AUTH_TRANSITION_TIMEOUT_MS);
        try {
          const response = await fetch("/api/v1/auth/login/", {
            method: "POST",
            credentials: "same-origin",
            headers: {
              "Content-Type": "application/json",
              Accept: "application/json",
            },
            body: JSON.stringify(credentials),
            signal: controller.signal,
          });

          if (!response.ok) {
            let message = "Invalid credentials";
            try {
              const body = await response.json();
              if (typeof body?.error?.message === "string") message = body.error.message;
              else if (typeof body?.message === "string") message = body.message;
              else if (typeof body?.error === "string") message = body.error;
            } catch {
              message = "Invalid credentials";
            }
            throw new Error(message);
          }

          const data: LoginResponse = await response.json();
          if (generation !== authGeneration.current) return;
          applyIdentity(
            {
              user: data.user,
              tenant_id: data.tenant_id ?? null,
              roles: data.roles ?? [],
              is_tenant_admin: data.is_tenant_admin ?? false,
            },
            generation,
          );
        } catch (error) {
          if (timedOut) {
            if (generation === authGeneration.current) {
              try {
                await apiClient.post("/auth/logout/", {});
              } catch {
                void 0;
              }
            }
            throw new Error("Login request timed out", { cause: error });
          }
          throw error;
        } finally {
          clearTimeout(timeout);
          if (loginAbortController.current === controller) loginAbortController.current = null;
        }
      });
    },
    [applyIdentity, enqueueCookieTransition]
  );

  /** Updates the current user's profile via PATCH /api/v1/auth/me/ (REQ-006). */
  const updateProfile = useCallback(
    async (update: ProfileUpdate): Promise<void> => {
      const generation = authGeneration.current;
      const data = await apiClient.patch<{ user: AuthUser }>("/auth/me/", update);
      if (generation !== authGeneration.current) return;
      setUser(data.user);
      installBluepencilHost();
      setBluepencilIdentitySource(() => bluepencilIdentityFromUser(data.user));
    },
    []
  );

  const logout = useCallback(() => {
    advanceAuthSessionGeneration();
    loginAbortController.current?.abort();
    loginAbortController.current = null;
    invalidateAuth();
    void enqueueCookieTransition(async () => {
      try {
        await apiClient.post("/auth/logout/", {});
      } catch {
        return;
      }
    });
  }, [enqueueCookieTransition, invalidateAuth]);

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
