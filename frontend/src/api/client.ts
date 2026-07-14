/**
 * ARCH-L1-001 ReactFrontend — Central API client.
 *
 * leaf_id: COMP-RF-001 (TokenManager / AuthGate integration)
 * req_id:  REQ-L2-RF-010 (Bearer-Token auth), REQ-L2-RF-011 (Error rendering)
 *
 * All REST calls go through this module.
 * - Attaches Authorization: Bearer <token> to every request.
 * - On 401 → clears auth state; caller redirects to /login.
 * - On 403 → throws ForbiddenError (permission error, no logout — REQ-051).
 * - Accepts/sends JSON; sends Accept-Language from i18n.
 */

import type { ApiError, PaginatedResponse } from "../types";
import { ForbiddenError } from "./errors";

// ---------------------------------------------------------------------------
// Token storage (IF-RF-INT — NavigationShell.TokenManager owns the token)
// ---------------------------------------------------------------------------

let _token: string | null = null;
let _onUnauthorized: (() => void) | null = null;

export function setAuthToken(token: string | null): void {
  _token = token;
}

export function getAuthToken(): string | null {
  return _token;
}

export function setUnauthorizedHandler(handler: () => void): void {
  _onUnauthorized = handler;
}

// ---------------------------------------------------------------------------
// Core fetch wrapper
// ---------------------------------------------------------------------------

const BASE_URL = "/api/v1";

async function apiFetch<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    Accept: "application/json",
    ...(options.headers as Record<string, string>),
  };

  if (_token) {
    headers["Authorization"] = `Bearer ${_token}`;
  }

  // Send Accept-Language from document lang or i18n (REQ-L2-RF-011)
  const lang = document.documentElement.lang || "en";
  headers["Accept-Language"] = lang;

  const response = await fetch(`${BASE_URL}${path}`, {
    ...options,
    headers,
  });

  // 401 → not authenticated: clear auth state and redirect to login
  // (REQ-L2-RF-010).
  if (response.status === 401) {
    _onUnauthorized?.();
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
    throw new ForbiddenError();
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
    return undefined as unknown as T;
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

  delete(path: string, body?: unknown): Promise<void> {
    const options: RequestInit = { method: "DELETE" };
    if (body !== undefined) {
      options.body = JSON.stringify(body);
    }
    return apiFetch<void>(path, options);
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
