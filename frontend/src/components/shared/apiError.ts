/**
 * Shape-tolerant readers for the `LAST_ADMIN` error body (#1081).
 *
 * Why this file exists
 * --------------------
 * `apiClient.apiFetch` throws the *response body itself* for a non-2xx answer
 * (see `api/client.ts`, the `if (!response.ok) { throw body; }` branch) — not
 * an axios-style `{response: {status, data}}` wrapper. So a component that
 * wants to branch on an error code reads that body directly.
 *
 * #1081 collapsed the API onto ONE envelope:
 *
 *     {"error": {"code": "LAST_ADMIN", "message": "...", "details": []}}
 *
 * `PermissionsSection.tsx` predates that change and read only the FLAT shape
 * (`{error: "LAST_ADMIN", message: "..."}`), so `candidate.error === "LAST_ADMIN"`
 * compared an *object* to a string and was `false` unconditionally: the
 * last-admin UX (scope/identifier parsing, localized copy) died silently, with
 * no failing test and no visible error anywhere — the component just fell
 * through to the generic message.
 *
 * `Settings/UserManagement/UserManagement.tsx` already read BOTH shapes but held
 * its own private copy of these functions — including the `(\S+)` identifier
 * regex that silently broke the localized copy for any multi-word workspace
 * name. Both call sites now import from this one module.
 *
 * Backward compatibility is kept on purpose, not by accident: the flat branch
 * is what a not-yet-migrated adapter, an older gateway or a recorded fixture
 * still answers, and it costs one `typeof` check. The canonical nested shape is
 * the primary read.
 */

/**
 * Both accepted body shapes. `details` is only on the canonical one; nothing
 * here reads it, so it stays optional rather than lying about the flat form.
 */
export type ApiErrorBody =
  | { error: { code: string; message: string; details?: unknown } }
  | { error: string; message: string };

/** Read the machine code out of either envelope shape; `null` if absent. */
export function errorCode(err: unknown): string | null {
  const candidate = err as { error?: unknown } | null | undefined;
  if (!candidate || typeof candidate !== "object") return null;
  const nested = candidate.error as { code?: unknown } | undefined;
  if (nested && typeof nested === "object" && typeof nested.code === "string") {
    return nested.code;
  }
  return typeof candidate.error === "string" ? candidate.error : null;
}

/**
 * Read the human-readable sentence out of either envelope shape.
 *
 * Kept separate from `client.ts`'s `extractApiErrorMessage`: that helper
 * prefers `details[0].errors[0]` (field-level serializer rejections), whereas
 * the `LAST_ADMIN` sentence `parseLastAdminMessage` needs verbatim lives in the
 * top-level `message`.
 */
export function extractMessage(err: unknown): string | null {
  const candidate = err as { error?: unknown; message?: unknown } | null | undefined;
  if (!candidate || typeof candidate !== "object") return null;
  const nested = candidate.error as { message?: unknown } | undefined;
  if (nested && typeof nested === "object" && typeof nested.message === "string") {
    return nested.message;
  }
  return typeof candidate.message === "string" ? candidate.message : null;
}

/**
 * `extractMessage` with the `String(err)` fallback every call site wants, so
 * the generic error paths in `PermissionsSection` stay one line.
 */
export function extractErrorMessage(err: unknown): string {
  return extractMessage(err) ?? String(err);
}

/** Whether this body is the last-admin refusal, in either shape. */
export function isLastAdminError(err: unknown): boolean {
  return errorCode(err) === "LAST_ADMIN" && extractMessage(err) !== null;
}

// Matches `LastAdminError.__init__`'s fixed message format
// (backend/auth_tenancy/services/authorization.py): "Cannot complete this
// action: it would leave {scope} {identifier} with no active admin."
//
// The identifier capture is `.+?`, not `\S+`, and that is load-bearing: the
// `identifier` is a workspace/tenant NAME, so it routinely contains spaces
// ("Team Alpha"). `\S+` stopped at the first space and the trailing
// " with no active admin" then failed to match, so `parseLastAdminMessage`
// returned null and the component fell back to echoing the backend's English
// sentence into the UI — the localized copy silently never rendered. Lazy
// `.+?` backtracks to the last position where the fixed tail still matches.
// (This module is the single home for both consumers; see the file docstring.)
const LAST_ADMIN_MESSAGE_RE = /leave (workspace|tenant) (.+?) with no active admin/i;

/**
 * Extract `{scope, identifier}` from the backend's English sentence so the UI
 * can render the LOCALIZED `permissions.members.lastAdminError` copy
 * (DE/EN) instead of leaking the backend sentence into a German UI.
 *
 * Returns `null` when the sentence does not match — the caller then shows the
 * raw message rather than a half-parsed one.
 */
export function parseLastAdminMessage(
  message: string,
): { scope: string; identifier: string } | null {
  const match = message.match(LAST_ADMIN_MESSAGE_RE);
  if (!match) return null;
  const [, scope, identifier] = match;
  return { scope: scope.charAt(0).toUpperCase() + scope.slice(1), identifier };
}
