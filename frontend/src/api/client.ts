/**
 * ARCH-L1-001 ReactFrontend — Central API client.
 *
 * leaf_id: COMP-RF-001 (TokenManager / AuthGate integration)
 * req_id:  REQ-L2-RF-010 (Bearer-Token auth), REQ-L2-RF-011 (Error rendering)
 *
 * All REST calls go through this module.
 * - Auth travels as the httpOnly ``reqflow_access`` cookie (REQ-052); requests
 *   are sent with credentials so the browser attaches it automatically. A
 *   legacy in-memory Bearer token is still supported for non-browser callers.
 * - Sends X-CSRFToken (from the ``csrftoken`` cookie) on unsafe methods, as the
 *   cookie auth path is CSRF-protected server-side.
 * - On 401 → attempts a single-flight silent refresh (POST /auth/refresh/,
 *   GitHub #135) and retries the original request once; only clears auth
 *   state and notifies the caller if the refresh also fails (or the request
 *   IS the refresh/login call). Parallel 401s share one refresh attempt and
 *   the unauthorized notification fires at most once per session.
 * - On 403 → throws ForbiddenError (permission error, no logout — REQ-051).
 * - Accepts/sends JSON; sends Accept-Language from i18n.
 */

import type { ApiError, PaginatedResponse } from "../types";
import { ForbiddenError, UnprocessableEntityError } from "./errors";

// ---------------------------------------------------------------------------
// CSRF helpers (REQ-052)
// ---------------------------------------------------------------------------

const UNSAFE_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);

/** Read a cookie value by name (returns null when absent). */
export function readCookie(name: string): string | null {
  const match = document.cookie.match(
    new RegExp("(?:^|;\\s*)" + name + "=([^;]*)")
  );
  return match ? decodeURIComponent(match[1]) : null;
}

// ---------------------------------------------------------------------------
// Token storage (IF-RF-INT — NavigationShell.TokenManager owns the token)
// ---------------------------------------------------------------------------

let _token: string | null = null;
let _onUnauthorized: (() => void) | null = null;
// Guards against firing the unauthorized handler more than once for a burst
// of parallel requests that all 401 around the same time (GitHub #135).
let _unauthorizedNotified = false;

export function setAuthToken(token: string | null): void {
  _token = token;
}

export function getAuthToken(): string | null {
  return _token;
}

export function setUnauthorizedHandler(handler: () => void): void {
  _onUnauthorized = handler;
}

/**
 * Re-arms the unauthorized notification (GitHub #135). Call this once a
 * session is (re-)established (login success, restored session) so a later
 * 401 can notify again.
 */
export function resetUnauthorizedGuard(): void {
  _unauthorizedNotified = false;
}

function notifyUnauthorized(): void {
  if (_unauthorizedNotified) return;
  _unauthorizedNotified = true;
  _onUnauthorized?.();
}

// ---------------------------------------------------------------------------
// Silent token refresh (GitHub #135)
// ---------------------------------------------------------------------------

// Single-flight guard: concurrent 401s share one in-flight refresh instead of
// each firing its own POST /auth/refresh/ (and each risking its own logout).
let _refreshPromise: Promise<boolean> | null = null;

async function doRefresh(): Promise<boolean> {
  try {
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      Accept: "application/json",
    };
    const csrf = readCookie("csrftoken");
    if (csrf) headers["X-CSRFToken"] = csrf;

    const response = await fetch(`${BASE_URL}/auth/refresh/`, {
      method: "POST",
      credentials: "same-origin",
      headers,
    });
    if (response.ok) {
      // A successful refresh re-establishes the session; allow a future
      // 401 (e.g. after the new access token itself expires) to notify again.
      resetUnauthorizedGuard();
      return true;
    }
    return false;
  } catch {
    // Network error while refreshing — treat as a failed refresh so the
    // caller falls back to the normal 401 handling instead of hanging.
    return false;
  }
}

function attemptRefresh(): Promise<boolean> {
  if (!_refreshPromise) {
    _refreshPromise = doRefresh().finally(() => {
      _refreshPromise = null;
    });
  }
  return _refreshPromise;
}

// ---------------------------------------------------------------------------
// Core fetch wrapper
// ---------------------------------------------------------------------------

const BASE_URL = "/api/v1";

// Auth endpoints must never trigger a refresh-and-retry on their own 401:
// retrying /auth/refresh/ after a failed refresh would loop, and /auth/login/
// 401s are simply "wrong credentials", not an expired session.
const _NO_REFRESH_PATHS = ["/auth/refresh/", "/auth/login/"];

async function apiFetch<T>(
  path: string,
  options: RequestInit = {},
  _isRetryAfterRefresh = false
): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    Accept: "application/json",
  };

  // Safely merge incoming headers: only record-like objects can be spread.
  // HeadersInit can be Record<string, string>, Headers, or string[][], so we
  // narrow to plain objects before merging.
  if (
    options.headers &&
    typeof options.headers === "object" &&
    !Array.isArray(options.headers) &&
    !(options.headers instanceof Headers)
  ) {
    Object.assign(headers, options.headers as Record<string, string>);
  }

  // Legacy in-memory Bearer token (non-browser callers). Browser auth flows
  // rely on the httpOnly cookie instead (REQ-052), so _token is normally null.
  if (_token) {
    headers["Authorization"] = `Bearer ${_token}`;
  }

  // Attach CSRF token on unsafe methods for the cookie auth path (REQ-052).
  const method = (options.method ?? "GET").toUpperCase();
  if (UNSAFE_METHODS.has(method)) {
    const csrf = readCookie("csrftoken");
    if (csrf) headers["X-CSRFToken"] = csrf;
  }

  // Send Accept-Language from document lang or i18n (REQ-L2-RF-011)
  const lang = document.documentElement.lang || "en";
  headers["Accept-Language"] = lang;

  const response = await fetch(`${BASE_URL}${path}`, {
    ...options,
    // Send the httpOnly access cookie on same-origin requests (REQ-052).
    credentials: "same-origin",
    headers,
  });

  // 401 → not authenticated. Before giving up, try a silent single-flight
  // refresh and retry the original request once (GitHub #135) — this is what
  // saves in-progress form content when the access token expires mid-session
  // instead of hard-logging the user out. Only clears auth state / notifies
  // the caller if the refresh also fails, or if this call already IS a retry
  // or an auth endpoint (avoids infinite loops / retrying login).
  if (response.status === 401) {
    const canTryRefresh =
      !_isRetryAfterRefresh && !_NO_REFRESH_PATHS.includes(path);
    if (canTryRefresh) {
      const refreshed = await attemptRefresh();
      if (refreshed) {
        return apiFetch<T>(path, options, true);
      }
    }
    // Refresh unavailable/failed (or not attempted) → clear auth state and
    // let the caller redirect to /login (REQ-L2-RF-010).
    notifyUnauthorized();
    const err: ApiError = {
      error: {
        code: "AUTHENTICATION_REQUIRED",
        message: "Authentication required",
        details: [],
      },
    };
    throw err;
  }

  // 403 → authenticated but lacking permission: surface the error without
  // logging the user out (REQ-051).
  if (response.status === 403) {
    // Pass through the server-provided detail (e.g. a CSRF failure reason)
    // instead of masking every 403 with a generic permission text (REQ-138).
    let detail: string | undefined;
    try {
      const body = await response.json();
      detail =
        (typeof body?.detail === "string" && body.detail) ||
        (typeof body?.error?.message === "string" && body.error.message) ||
        undefined;
    } catch {
      // Non-JSON body → fall back to the default message.
    }
    throw new ForbiddenError(detail);
  }

  // 422 → understood but not applicable (e.g. SE-Auditor remediate without
  // an unambiguous auto-fix). A typed error so callers can distinguish it
  // from a plain 400 and switch into a manual "Modify" state instead of
  // showing a generic validation error (UMSETZUNGSPLAN_SYSENG_2.0.md §4).
  if (response.status === 422) {
    let detail: string | undefined;
    try {
      const body = await response.json();
      detail =
        (typeof body?.error?.message === "string" && body.error.message) ||
        (typeof body?.detail === "string" && body.detail) ||
        undefined;
    } catch {
      // Non-JSON body → fall back to the default message.
    }
    throw new UnprocessableEntityError(detail);
  }

  if (!response.ok) {
    let body: ApiError;
    try {
      body = await response.json();
    } catch {
      body = {
        error: {
          code: "INTERNAL_SERVER_ERROR",
          message: `HTTP ${response.status}`,
          details: [],
        },
      };
    }
    throw body;
  }

  if (response.status === 204) {
    // HTTP 204 No Content: response body is empty. Callers should declare
    // their response type as void, undefined, or a union (T | undefined).
    // This cast is safe because 204 responses have no body by spec.
    return undefined as T;
  }

  // A 2xx with an empty body is NOT an error, but response.json() throws a
  // SyntaxError on it. DRF renders `Response(None)` as a zero-length body
  // (see MainGoalViewSet.current, which answers "no approved main goal yet"
  // exactly that way), so without this guard a legitimate empty result
  // reached the UI as "SyntaxError: Unexpected end of JSON input".
  // Optional access on purpose: not every caller/mock supplies a full
  // Headers object, and a missing header must never break a normal response.
  if (response.headers?.get?.("content-length") === "0") {
    return undefined as T;
  }

  return response.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// HTTP methods
// ---------------------------------------------------------------------------

export const apiClient = {
  get<T>(path: string): Promise<T> {
    return apiFetch<T>(path);
  },

  post<T>(path: string, body: unknown): Promise<T> {
    return apiFetch<T>(path, {
      method: "POST",
      body: JSON.stringify(body),
    });
  },

  put<T>(path: string, body: unknown): Promise<T> {
    return apiFetch<T>(path, {
      method: "PUT",
      body: JSON.stringify(body),
    });
  },

  patch<T>(path: string, body: unknown): Promise<T> {
    return apiFetch<T>(path, {
      method: "PATCH",
      body: JSON.stringify(body),
    });
  },

  delete<T = void>(path: string, body?: unknown): Promise<T> {
    const options: RequestInit = { method: "DELETE" };
    if (body !== undefined) {
      options.body = JSON.stringify(body);
    }
    return apiFetch<T>(path, options);
  },
};

// ---------------------------------------------------------------------------
// Error message extraction (REQ-L2-RF-011)
// ---------------------------------------------------------------------------

/**
 * Extract a human-readable message from a thrown ApiError. Prefers the
 * first field-level detail (e.g. serializer validation on parent_id)
 * over the generic top-level message.
 */
export function extractErrorMessage(err: unknown): string {
  const apiErr = err as Partial<ApiError> | null;
  const detail = apiErr?.error?.details?.[0];
  const detailMsg = detail?.errors?.[0];
  if (detailMsg) return detailMsg;
  if (apiErr?.error?.message) return apiErr.error.message;
  return String(err);
}

// ---------------------------------------------------------------------------
// Paginated list helper
// ---------------------------------------------------------------------------

export async function getList<T>(
  path: string,
  params: Record<string, string> = {}
): Promise<PaginatedResponse<T>> {
  const qs = new URLSearchParams(params).toString();
  const fullPath = qs ? `${path}?${qs}` : path;
  return apiClient.get<PaginatedResponse<T>>(fullPath);
}

// ---------------------------------------------------------------------------
// Full-pagination list helper (issue C — the backend's default page size of
// 25 silently truncated workspace entity lists that only fetched page 1).
// Follows the paginator's `next` link until exhaustion and returns the
// de-duplicated full result set. Mirrors the listAll() pattern already used
// by requirementsApi.listAll / architectureApi.listAll.
// ---------------------------------------------------------------------------

export async function getAllPages<T extends { id: string }>(
  path: string,
  params: Record<string, string> = {}
): Promise<T[]> {
  const seen = new Set<string>();
  const all: T[] = [];
  const collect = (page: PaginatedResponse<T>): void => {
    for (const item of page.results) {
      if (!seen.has(item.id)) {
        seen.add(item.id);
        all.push(item);
      }
    }
  };

  const resp = await getList<T>(path, {
    ...params,
    page_size: params.page_size ?? "100",
  });
  collect(resp);

  let nextUrl: string | null = resp.next;
  let pageCount = 0;

  while (nextUrl && pageCount < 100) {
    pageCount += 1;
    // The backend may return `next` as an absolute URL, a path starting
    // with /api/v1, or a path relative to /api/v1. apiClient.get prepends
    // /api/v1, so we always need the path relative to that prefix.
    const m = nextUrl.match(/^(https?:\/\/[^/]+)?(\/api\/v1)?(\/.*)$/);
    const pathWithQuery = m ? m[3] : nextUrl;
    const nextResp = await apiClient.get<PaginatedResponse<T>>(
      pathWithQuery.startsWith("/") ? pathWithQuery : `/${pathWithQuery}`
    );
    collect(nextResp);
    nextUrl = nextResp.next;
  }
  return all;
}
