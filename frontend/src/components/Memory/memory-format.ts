/**
 * ARCH-L1-001 ReactFrontend — shared formatting for the memory surfaces
 * (RFC #1002, PR D). Kept in one place so the workspace page, the artifact
 * panel and the profile list render dates/contributors identically.
 */

import type { TFunction } from "i18next";
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
