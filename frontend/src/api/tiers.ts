/**
 * P2 (V4/V5/B5) — per-workspace requirement tier ladder API.
 *
 * Wraps the two methods of `GET|PUT /api/v1/workspaces/<id>/tiers/`
 * (`WorkspaceViewSet.tiers`, backed by `application.tier_ladder_service`):
 *
 * | Method | Who may call | Answer |
 * |--------|--------------|--------|
 * | GET | any workspace member | the ladder, seeded with the default four positions on first read |
 * | PUT | workspace admin | the ladder after a full replacement |
 *
 * The ladder is the ordered list of named positions a requirement's tier can
 * take. `tier_key` is the stable machine key stored on `Requirement.tier_key`
 * (renaming a tier changes `name`, never the key); `position` is 0-based and
 * the requirement's integer alias `level` is `position + 1`.
 *
 * Server-side invariants every PUT must satisfy — the server is the authority
 * and rejects a violating ladder with `VALIDATION_ERROR`, which the editor
 * surfaces inline rather than pre-empting:
 *   - exactly one `rule: "first"` (the tree root),
 *   - at most one `rule: "middle"`,
 *   - exactly one `rule: "from_end"` with `from_end: 0` (the leaf),
 *   - `tier_key` unique and non-empty; `from_end` values unique/non-negative.
 *
 * Deleting a position that requirements still reference is refused unless the
 * entry carries `merge_into` (the surviving key). The editor does not send it
 * yet, so the server's message is what the admin sees.
 *
 * Consumed by direct import (`components/WorkspaceSettings/TierLadderSection`)
 * and deliberately NOT re-exported from `api/index.ts`, exactly like the other
 * single-surface settings modules (`tree-display-config.ts`, `#1257`).
 */

import { apiClient } from "./client";

/** How a ladder position maps a tree height onto a tier. */
export type TierRule = "first" | "middle" | "from_end";

/** The editable display label per language. */
export interface TierName {
  de: string;
  en: string;
}

/** One ladder position as the server returns it. */
export interface TierEntry {
  /** Stable machine key written to `Requirement.tier_key`. */
  tier_key: string;
  /** Editable `{de, en}` label — renaming never touches requirement data. */
  name: TierName;
  /** 0-based order in the ladder. */
  position: number;
  rule: TierRule;
  /** Only meaningful for `rule: "from_end"`; `null` otherwise. */
  from_end: number | null;
  /** Integer alias derived from `position` (`position + 1`). */
  level: number;
}

/** Wire shape for both GET and PUT. */
export interface TierLadderPayload {
  workspace_id: string;
  tiers: TierEntry[];
}

/**
 * One ladder position as the PUT body accepts it — `position` and `level` are
 * derived by the server from the array order, so a caller must not send them.
 */
export interface TierWriteEntry {
  tier_key: string;
  name: TierName;
  rule: TierRule;
  from_end: number | null;
  /** Only on removal: move the requirements of this key to the surviving key. */
  merge_into?: string;
}

/** The three keys the "three names" shortcut builds. */
export const THREE_NAME_KEYS = ["erste", "dazwischen", "letzte"] as const;

/** One label per position, for {@link buildThreeNameLadder}. */
export interface ThreeNameLabels {
  erste: string;
  dazwischen: string;
  letzte: string;
}

/**
 * Build the minimal three-position ladder from three names — the same shape
 * `TierLadderService.apply_three_names` writes server-side: `erste` (root),
 * `dazwischen` (middle) and `letzte` (leaf, `from_end: 0`).
 *
 * `apply_three_names` stores the entered label in both language slots; this
 * helper mirrors that so a quick-start ladder never shows an empty label when
 * the interface language is switched.
 */
export function buildThreeNameLadder(
  names: ThreeNameLabels
): TierWriteEntry[] {
  const label = (value: string): TierName => ({ de: value, en: value });
  return [
    {
      tier_key: "erste",
      name: label(names.erste),
      rule: "first",
      from_end: null,
    },
    {
      tier_key: "dazwischen",
      name: label(names.dazwischen),
      rule: "middle",
      from_end: null,
    },
    {
      tier_key: "letzte",
      name: label(names.letzte),
      rule: "from_end",
      from_end: 0,
    },
  ];
}

function pathFor(workspaceId: string): string {
  return `/workspaces/${workspaceId}/tiers/`;
}

export const tiersApi = {
  /**
   * GET — the workspace ladder. A workspace that has never been configured is
   * seeded with the default four positions by the server, so the answer is
   * always a usable ladder and the caller never re-derives a default.
   */
  async get(workspaceId: string): Promise<TierLadderPayload> {
    return apiClient.get<TierLadderPayload>(pathFor(workspaceId));
  },

  /**
   * PUT — replace the whole ladder (workspace admin only). Returns the stored
   * ladder with server-derived `position`/`level`, which is what the editor
   * must render (never a locally guessed order).
   */
  async replace(
    workspaceId: string,
    tiers: TierWriteEntry[]
  ): Promise<TierLadderPayload> {
    return apiClient.put<TierLadderPayload>(pathFor(workspaceId), { tiers });
  },
};
