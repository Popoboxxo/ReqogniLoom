/**
 * ARCH-L1-001 ReactFrontend — Query error normalization.
 *
 * req_id: REQ-049 (TanStack Query migration of the hand-rolled use*Data hooks)
 *
 * apiClient rejects with either a plain ApiError object ({ error: { message } })
 * or a real Error subclass (e.g. ForbiddenError). The legacy hooks normalized
 * these into an `Error` instance so consumers could read `error.message`.
 * This helper preserves that contract for the migrated TanStack Query hooks.
 */

import { extractErrorMessage } from "../api/client";

export function asError(err: unknown): Error {
  return err instanceof Error ? err : new Error(extractErrorMessage(err));
}
