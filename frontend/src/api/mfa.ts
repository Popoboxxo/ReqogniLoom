/**
 * ARCH-L1-001 ReactFrontend — TOTP second-factor (MFA) API.
 *
 * leaf_id: COMP-RF-001 / COMP-RF-006 (Auth + UserProfileSettings)
 * req_id:  REQ-L2-RF-010 (auth), Plan E / WP E3.8 (#1308)
 *
 * Wraps the backend MFA surface:
 *   GET  /api/v1/auth/mfa/status/                    caller's enrollment state
 *   POST /api/v1/auth/mfa/totp/enroll/               issue a pending TOTP secret
 *   POST /api/v1/auth/mfa/totp/confirm/              confirm with the first code
 *   POST /api/v1/auth/mfa/recovery-codes/regenerate/ rotate recovery codes
 *   POST /api/v1/auth/mfa/disable/                   remove the second factor
 *   POST /api/v1/auth/login/mfa/                     second login step
 *
 * `loginMfa` deliberately bypasses `apiClient`: the caller has no session yet,
 * so the client's 401 handling (silent refresh + "session expired" logout
 * notification) would mask the actionable MFA error codes (`MFA_INVALID_CODE`,
 * `MFA_LOCKED`, `MFA_CHALLENGE_INVALID`) that the login screen must render.
 * This mirrors `AuthContext.login()`'s raw-fetch path for the same reason.
 */

import { apiClient } from "./client";
import type { AuthUser } from "../context/AuthContext";

export type MfaEnforcement = "off" | "optional" | "required";

/** Body of `GET /api/v1/auth/mfa/status/`. */
export interface MfaStatus {
  enrolled: boolean;
  confirmed_at: string | null;
  recovery_codes_remaining: number;
  enforcement: MfaEnforcement;
  required: boolean;
}

/** 201 body of `POST /api/v1/auth/mfa/totp/enroll/` (no QR, ENT-E5 = A). */
export interface TotpEnrollment {
  /** Base32 secret — shown exactly once. */
  secret: string;
  otpauth_uri: string;
  digits: number;
  period: number;
}

/** 200 body of `POST /api/v1/auth/mfa/totp/confirm/` (session flow). */
export interface MfaConfirmResult {
  confirmed_at: string;
  /** The ten single-use codes — the only time they are readable. */
  recovery_codes: string[];
}

/** 200 body of `POST /api/v1/auth/mfa/recovery-codes/regenerate/`. */
export interface MfaRecoveryCodesResult {
  recovery_codes: string[];
}

/** Identity block returned by a successful `POST /api/v1/auth/login/mfa/`. */
export interface MfaLoginIdentity {
  user: AuthUser;
  tenant_id: string | null;
  roles: string[];
  is_tenant_admin: boolean;
}

/** Request body of `POST /api/v1/auth/login/mfa/` — exactly one factor. */
export interface MfaLoginRequest {
  mfa_challenge: string;
  code?: string;
  recovery_code?: string;
}

/** Typed failure of the second login step (wrong code, lockout, expiry). */
export class MfaLoginError extends Error {
  constructor(
    public readonly code: string,
    public readonly status: number,
    public readonly retryAfterSeconds?: number
  ) {
    super(code);
    this.name = "MfaLoginError";
  }
}

/** `GET /api/v1/auth/mfa/status/` — the caller's own enrollment state. */
export function getMfaStatus(): Promise<MfaStatus> {
  return apiClient.get<MfaStatus>("/auth/mfa/status/");
}

/** `POST /api/v1/auth/mfa/totp/enroll/` — issue a pending TOTP device. */
export function enrollTotp(): Promise<TotpEnrollment> {
  return apiClient.post<TotpEnrollment>("/auth/mfa/totp/enroll/", {});
}

/** `POST /api/v1/auth/mfa/totp/confirm/` — prove the first code. */
export function confirmTotp(code: string): Promise<MfaConfirmResult> {
  return apiClient.post<MfaConfirmResult>("/auth/mfa/totp/confirm/", { code });
}

/** `POST /api/v1/auth/mfa/recovery-codes/regenerate/` — rotate the codes. */
export function regenerateRecoveryCodes(code: string): Promise<MfaRecoveryCodesResult> {
  return apiClient.post<MfaRecoveryCodesResult>(
    "/auth/mfa/recovery-codes/regenerate/",
    { code }
  );
}

/** `POST /api/v1/auth/mfa/disable/` — password + current code remove the factor. */
export function disableMfa(password: string, code: string): Promise<void> {
  return apiClient.post<void>("/auth/mfa/disable/", { password, code });
}

/**
 * `POST /api/v1/auth/login/mfa/` — second step of the two-step login.
 *
 * Raw `fetch` on purpose (see the module docstring): a 401 here means "wrong
 * code", not "session expired". On success the server has already set the
 * httpOnly session cookies.
 */
export async function loginMfa(request: MfaLoginRequest): Promise<MfaLoginIdentity> {
  const response = await fetch("/api/v1/auth/login/mfa/", {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    let code = "MFA_LOGIN_FAILED";
    try {
      const body = await response.json();
      if (typeof body?.error?.code === "string") code = body.error.code;
      else if (typeof body?.error === "string") code = body.error;
    } catch {
      // Non-JSON body — keep the generic code.
    }
    const retryAfter = Number(response.headers.get("Retry-After"));
    throw new MfaLoginError(
      code,
      response.status,
      Number.isFinite(retryAfter) && retryAfter > 0 ? retryAfter : undefined
    );
  }

  return (await response.json()) as MfaLoginIdentity;
}

/** Object form, matching the `*Api` wrapper convention used across `src/api`. */
export const mfaApi = {
  getStatus: getMfaStatus,
  enrollTotp,
  confirmTotp,
  regenerateRecoveryCodes,
  disableMfa,
  loginMfa,
};
