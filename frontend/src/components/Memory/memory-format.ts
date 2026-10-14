/**
 * ARCH-L1-001 ReactFrontend — shared formatting for the memory surfaces
 * (RFC #1002, PR D). Kept in one place so the workspace page, the artifact
 * panel and the profile list render dates/contributors identically.
 */

import type { TFunction } from "i18next";
import { extractApiErrorMessage } from "../../api/client";
import type { MemoryEntry } from "../../api/memory";

/** First 8 characters of a UUID, or an em dash for a missing id. */
export function shortId(id: string | null | undefined): string {
  if (!id) return "—";
  return id.length > 8 ? id.slice(0, 8) : id;
}

/** Locale date/time, falling back to the raw string for an unparseable value. */
export function formatMemoryDate(iso: string | null): string {
  if (!iso) return "—";
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleString();
}

/**
 * Provenance label for a memory entry: a short contributor id, or "Agent"
 * when the fact was written without a human contributor (agent-authored).
 */
export function contributorLabel(entry: MemoryEntry, t: TFunction): string {
  if (!entry.contributor_user_id) return t("memory.contributorAgent", "Agent");
  return `${t("memory.contributorUser", "Nutzer")} ${shortId(entry.contributor_user_id)}`;
}

/** HTTP status carried by a thrown API/typed error, or `null`. */
function extractHttpStatus(err: unknown): number | null {
  const e = err as { status?: unknown; response?: { status?: unknown } } | null;
  if (typeof e?.status === "number") return e.status;
  if (typeof e?.response?.status === "number") return e.response.status;
  return null;
}

/** Stable backend error code (`error.code`), or a typed error's name, or `null`. */
function extractErrorCode(err: unknown): string | null {
  const e = err as
    | { error?: { code?: unknown }; code?: unknown; name?: unknown }
    | null;
  if (typeof e?.error?.code === "string" && e.error.code) return e.error.code;
  if (typeof e?.code === "string" && e.code) return e.code;
  // Typed client errors (ForbiddenError / UnprocessableEntityError / …) carry
  // no `error.code`, but their `name` is a stable machine-readable code.
  if (typeof e?.name === "string" && e.name && e.name !== "Error") return e.name;
  return null;
}

/**
 * User-facing message for a failed memory request, enriched with the HTTP
 * status / backend error code carried by the thrown value (#1296).
 *
 * `extractApiErrorMessage` alone returns `null` for a plain network/JS failure
 * (and drops the status entirely for a typed error), which is exactly the case
 * where "all endpoints answered 200" cannot be verified from the UI. Appending
 * `(HTTP <status>)` / `(<CODE>)` makes such a failure attributable.
 */
export function formatMemoryErrorMessage(err: unknown, fallback: string): string {
  const base = extractApiErrorMessage(err) ?? fallback;
  const status = extractHttpStatus(err);
  const code = extractErrorCode(err);
  const suffix = status !== null ? `(HTTP ${status})` : code ? `(${code})` : "";
  // Never duplicate a suffix the base message already spells out.
  if (!suffix || base.includes(suffix)) return base;
  return `${base} ${suffix}`;
}

