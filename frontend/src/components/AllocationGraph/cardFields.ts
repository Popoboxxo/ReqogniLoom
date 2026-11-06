/**
 * P5 Task 5.2 — configurable card fields for the allocation graph.
 *
 * The card graph renders two card types (requirement cards, element cards).
 * Which *informational* fields each card shows is a workspace preference:
 * order and the number of visual rows are configurable per card type.
 *
 * Three markers are deliberately NOT part of that preference:
 *
 * - `lock`   — a frozen card must always be recognisable (P4 freeze),
 * - `finding` — an open finding must always be visible (SE-Auditor),
 * - `unallocated` — a requirement without an allocation must always be
 *   recognisable (that is the whole point of the view).
 *
 * `finding`/`unallocated` have no field key at all (they are rendered by the
 * card components unconditionally). `lock` IS a field key so a settings
 * document can order it, but `validateCardFieldConfig` rejects hiding it —
 * the settings editor and the persistence layer both call that validator.
 *
 * There is no backend card-field store yet, so the configuration is persisted
 * through the existing three-level preference API (workspace scope). A
 * deployment that does not know the key rejects the write; exactly like the
 * connection view's saved views, the module then degrades to `localStorage`
 * and never blocks the view. `load()` never rejects.
 */

import { preferenceValuesApi } from "../../api/preference-values";

/** The two card kinds the graph renders. */
export type CardKind = "requirement" | "element";

/** One configurable field of a card. */
export type CardFieldKey =
  | "id"
  | "title"
  | "state"
  | "tier"
  | "type"
  | "category"
  | "group"
  | "allocationCount"
  | "lock"
  | "owner";

/** One entry of a card's field list. */
export interface CardFieldSetting {
  key: CardFieldKey;
  visible: boolean;
}

/** Per-card-type configuration: ordered fields + number of visual rows. */
export interface CardFieldConfig {
  fields: CardFieldSetting[];
  rows: number;
}

/** Both card types in one document. */
export type CardFieldConfigMap = Record<CardKind, CardFieldConfig>;

/** Every field a settings editor may offer, in the canonical order. */
export const CARD_FIELD_KEYS: Record<CardKind, readonly CardFieldKey[]> = {
  requirement: [
    "id",
    "title",
    "state",
    "tier",
    "type",
    "category",
    "group",
    "allocationCount",
    "lock",
    "owner",
  ],
  element: [
    "id",
    "title",
    "state",
    "tier",
    "type",
    "category",
    "group",
    "allocationCount",
    "lock",
    "owner",
  ],
};

/**
 * Field keys that carry a mandatory marker. Their entry may be reordered but
 * never hidden; `validateCardFieldConfig` throws for `visible: false`.
 */
export const MANDATORY_CARD_FIELDS: readonly CardFieldKey[] = ["lock"];

/** Allowed number of visual field rows per card. */
export const MIN_CARD_ROWS = 1;
export const MAX_CARD_ROWS = 4;

/** Preference key holding the serialized configuration (workspace scope). */
export const CARD_FIELDS_PREFERENCE_KEY = "ui.allocation_graph.card_fields";

/** `localStorage` fallback prefix (one entry per workspace). */
const LOCAL_STORAGE_PREFIX = "reqlo.allocation_graph.card_fields";

function defaultFields(kind: CardKind): CardFieldSetting[] {
  if (kind === "requirement") {
    return [
      { key: "id", visible: true },
      { key: "title", visible: true },
      { key: "state", visible: true },
      { key: "tier", visible: true },
      { key: "allocationCount", visible: true },
      { key: "lock", visible: true },
    ];
  }
  return [
    { key: "id", visible: true },
    { key: "title", visible: true },
    { key: "type", visible: true },
    { key: "allocationCount", visible: true },
    { key: "lock", visible: true },
  ];
}

/** Fresh default configuration for one card type (never shared objects). */
export function defaultCardFieldConfig(kind: CardKind): CardFieldConfig {
  return {
    fields: defaultFields(kind).map((field) => ({ ...field })),
    rows: 2,
  };
}

/** Fresh default configuration for both card types. */
export function defaultCardFieldConfigMap(): CardFieldConfigMap {
  return {
    requirement: defaultCardFieldConfig("requirement"),
    element: defaultCardFieldConfig("element"),
  };
}

function isCardFieldKey(value: unknown): value is CardFieldKey {
  return (
    typeof value === "string" &&
    (CARD_FIELD_KEYS.requirement as readonly string[]).includes(value)
  );
}

function clampRows(value: unknown): number {
  const parsed =
    typeof value === "number"
      ? value
      : typeof value === "string"
        ? Number.parseInt(value, 10)
        : Number.NaN;
  if (!Number.isFinite(parsed)) return 2;
  return Math.min(MAX_CARD_ROWS, Math.max(MIN_CARD_ROWS, Math.round(parsed)));
}

/**
 * Coerce a stored/imported document into a valid configuration.
 *
 * Unknown keys are dropped, duplicates collapse to their first occurrence and
 * a missing mandatory marker is appended (visible). The result is safe to
 * render; it does not pretend that a hidden mandatory entry was requested.
 */
export function normalizeCardFieldConfig(
  kind: CardKind,
  raw: unknown
): CardFieldConfig {
  const source =
    raw && typeof raw === "object" && !Array.isArray(raw)
      ? (raw as { fields?: unknown; rows?: unknown })
      : {};
  const fields: CardFieldSetting[] = [];
  const seen = new Set<CardFieldKey>();

  if (Array.isArray(source.fields)) {
    for (const entry of source.fields) {
      const candidate =
        typeof entry === "string"
          ? { key: entry, visible: true }
          : entry && typeof entry === "object"
            ? (entry as { key?: unknown; visible?: unknown })
            : null;
      const allowed = CARD_FIELD_KEYS[kind] as readonly string[];
      if (
        !candidate ||
        !isCardFieldKey(candidate.key) ||
        !allowed.includes(candidate.key) ||
        seen.has(candidate.key)
      ) {
        continue;
      }
      seen.add(candidate.key);
      fields.push({
        key: candidate.key,
        visible: candidate.visible !== false,
      });
    }
  }

  for (const key of MANDATORY_CARD_FIELDS) {
    const existing = fields.find((field) => field.key === key);
    if (existing) existing.visible = true;
    else fields.push({ key, visible: true });
  }

  return { fields, rows: clampRows(source.rows) };
}

/** Normalize a whole document; unknown/malformed entries fall back to defaults. */
export function normalizeCardFieldConfigMap(raw: unknown): CardFieldConfigMap {
  const source =
    raw && typeof raw === "object" && !Array.isArray(raw)
      ? (raw as Record<string, unknown>)
      : {};
  return {
    requirement: normalizeCardFieldConfig("requirement", source.requirement),
    element: normalizeCardFieldConfig("element", source.element),
  };
}

/**
 * Validate a configuration before it is persisted.
 *
 * Throws when a mandatory marker would be hidden (the plan's explicit
 * "settings API rejects hiding them" rule), when a field occurs twice, or when
 * the row count is outside the supported range.
 */
export function validateCardFieldConfig(
  kind: CardKind,
  config: CardFieldConfig
): void {
  if (
    !Number.isInteger(config.rows) ||
    config.rows < MIN_CARD_ROWS ||
    config.rows > MAX_CARD_ROWS
  ) {
    throw new Error(
      `Card field rows must be an integer between ${MIN_CARD_ROWS} and ${MAX_CARD_ROWS}`
    );
  }

  const seen = new Set<CardFieldKey>();
  for (const field of config.fields) {
    if (!isCardFieldKey(field.key)) {
      throw new Error(`Unknown card field "${String(field.key)}"`);
    }
    if (seen.has(field.key)) {
      throw new Error(`Duplicate card field "${field.key}"`);
    }
    seen.add(field.key);
  }

  for (const key of MANDATORY_CARD_FIELDS) {
    const field = config.fields.find((candidate) => candidate.key === key);
    if (!field || !field.visible) {
      throw new Error(
        `Mandatory card marker "${key}" cannot be hidden on a ${kind} card`
      );
    }
  }
}

/** Visible field keys in configured order, without marker-only entries. */
export function visibleCardFields(config: CardFieldConfig): CardFieldKey[] {
  return config.fields
    .filter((field) => field.visible && !MANDATORY_CARD_FIELDS.includes(field.key))
    .map((field) => field.key);
}

/**
 * Distribute the visible fields over the configured number of rows.
 * Contiguous chunks in configured order; an empty list yields no rows.
 */
export function layoutCardFields(config: CardFieldConfig): CardFieldKey[][] {
  const keys = visibleCardFields(config);
  if (keys.length === 0) return [];
  const rows = Math.min(config.rows, keys.length);
  const perRow = Math.ceil(keys.length / rows);
  const result: CardFieldKey[][] = [];
  for (let index = 0; index < keys.length; index += perRow) {
    result.push(keys.slice(index, index + perRow));
  }
  return result;
}

/**
 * The primary field shown in the card header: the first configured, visible
 * entry among `title` and `id` (in the user's order). `null` when both are
 * hidden — the card then shows only markers/fields.
 */
export function primaryCardField(config: CardFieldConfig): CardFieldKey | null {
  for (const field of config.fields) {
    if (!field.visible) continue;
    if (field.key === "title" || field.key === "id") return field.key;
  }
  return null;
}

/** Serialize for the preference store (`str_list` of JSON documents). */
export function serializeCardFieldConfigMap(config: CardFieldConfigMap): string[] {
  return (["requirement", "element"] as const).map((kind) =>
    JSON.stringify({ kind, ...config[kind] })
  );
}

/** Parse a stored `str_list`; malformed items are ignored individually. */
export function parseCardFieldConfigMap(raw: unknown): CardFieldConfigMap {
  const result = defaultCardFieldConfigMap();
  const items = Array.isArray(raw) ? raw : typeof raw === "string" ? [raw] : [];
  for (const item of items) {
    if (typeof item !== "string") continue;
    try {
      const parsed = JSON.parse(item) as { kind?: unknown };
      if (parsed?.kind === "requirement" || parsed?.kind === "element") {
        result[parsed.kind] = normalizeCardFieldConfig(parsed.kind, parsed);
      }
    } catch {
      // A malformed item must never take the whole configuration down.
    }
  }
  return result;
}

function localKey(workspaceId: string | null | undefined): string {
  return `${LOCAL_STORAGE_PREFIX}.${workspaceId ?? "default"}`;
}

function readLocal(workspaceId: string | null | undefined): CardFieldConfigMap | null {
  if (typeof window === "undefined") return null;
  try {
    const stored = window.localStorage.getItem(localKey(workspaceId));
    if (!stored) return null;
    return parseCardFieldConfigMap(JSON.parse(stored));
  } catch {
    return null;
  }
}

function writeLocal(
  workspaceId: string | null | undefined,
  serialized: string[]
): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(localKey(workspaceId), JSON.stringify(serialized));
  } catch {
    // Quota/private-mode failures must not break the graph.
  }
}

export const cardFieldsApi = {
  /**
   * Resolve the caller's effective card fields for a workspace. Preference
   * store first, `localStorage` fallback; never rejects.
   */
  async load(workspaceId?: string | null): Promise<CardFieldConfigMap> {
    try {
      const effective = await preferenceValuesApi.effective(workspaceId ?? null);
      const stored = effective.values[CARD_FIELDS_PREFERENCE_KEY];
      if (stored?.value !== undefined) {
        return parseCardFieldConfigMap(stored.value);
      }
    } catch {
      // Unregistered key or unavailable backend -> local mirror.
    }
    return readLocal(workspaceId) ?? defaultCardFieldConfigMap();
  },

  /**
   * Persist the configuration at the workspace level. Validates first (a
   * hidden mandatory marker never reaches the server), mirrors locally in
   * every case, and swallows the "key not registered" rejection exactly like
   * the saved connection views.
   */
  async save(
    workspaceId: string,
    config: CardFieldConfigMap
  ): Promise<void> {
    validateCardFieldConfig("requirement", config.requirement);
    validateCardFieldConfig("element", config.element);
    const serialized = serializeCardFieldConfigMap(config);
    writeLocal(workspaceId, serialized);
    try {
      await preferenceValuesApi.patchLevel(
        "workspace",
        { [CARD_FIELDS_PREFERENCE_KEY]: serialized },
        workspaceId
      );
    } catch {
      // Degraded (unregistered key): the local mirror is already written.
    }
  },

  /** Restore the local mirror's default (used by the settings editor). */
  resetLocal(workspaceId: string): CardFieldConfigMap {
    const defaults = defaultCardFieldConfigMap();
    writeLocal(workspaceId, serializeCardFieldConfigMap(defaults));
    return defaults;
  },
};
