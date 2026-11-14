/**
 * ArtifactInspector — shared contract of the tabbed shell (issue #1762, M1).
 *
 * leaf_id: COMP-RF-014 (ArtifactInspector)
 * req_id:  REQ-L0-062, REQ-L1-089, REQ-L1-093, REQ-L1-094, REQ-L1-095
 *
 * One module owns every name the shell, its rail, its tabs and its tests have
 * to agree on:
 *
 *  - the four tab keys and the order they are rendered in,
 *  - the DOM ids (`inspector-tab-<key>` / `inspector-panel-<key>`, spec §7),
 *  - the `data-testid` inventory (spec §8.4 point 7),
 *  - the per-kind type matrix (spec §3) — **derived from `kind` only**, never
 *    from a prop or a route switch,
 *  - the storage keys (spec §5.4) and the width defaults (spec §4.2).
 *
 * The matrix is the whole answer to "which kind gets which tab": Version and
 * Diff exist for every `ArtifactKind` (`DIFF_SUPPORTED_KINDS` in `./types`),
 * the Links tab exists for every kind except `mainGoal`, and the Comments tab
 * exists only when the route could hand over the backing generic Artifact UUID
 * (spec §4.3 / D5). A kind without that UUID gets no comments tab — not an
 * empty one, not a disabled one.
 *
 * Nothing in here touches the DOM or React; it is the pure contract the rest
 * of the shell consumes.
 */

import type { ArtifactKind } from "./types";

// ---------------------------------------------------------------------------
// Tabs
// ---------------------------------------------------------------------------

/** The four areas of the inspector, in rendered order (spec §2.1). */
export type InspectorTabKey = "version" | "diff" | "links" | "comments";

export const INSPECTOR_TAB_ORDER: readonly InspectorTabKey[] = [
  "version",
  "diff",
  "links",
  "comments",
] as const;

/** Default tab for every kind: "Version" (spec §3). */
export const INSPECTOR_DEFAULT_TAB: InspectorTabKey = "version";

// ---------------------------------------------------------------------------
// Type matrix (spec §3) — kind-only logic
// ---------------------------------------------------------------------------

/**
 * Kinds with a trace spine. Every kind except the four that have no
 * derivation chain at all: `mainGoal` (no trace graph, spec §3), `glossary`,
 * `icd` and `diagram` (soft-edge/embedded artifacts, no V-Modell position).
 */
export const HAS_SPINE: ReadonlySet<ArtifactKind> = new Set<ArtifactKind>([
  "requirement",
  "stakeholderNeed",
  "risk",
  "adr",
  "issue",
  "testCase",
  "architecture",
  "goal",
]);

/**
 * Kinds that get a Links tab. Only `mainGoal` is excluded: it has no
 * `artifact_id` and no trace graph, so there is nothing to inventory
 * (spec §3, D2).
 */
export const HAS_LINKS_TAB: ReadonlySet<ArtifactKind> = new Set<ArtifactKind>([
  "requirement",
  "stakeholderNeed",
  "risk",
  "adr",
  "issue",
  "testCase",
  "architecture",
  "goal",
  "glossary",
  "icd",
  "diagram",
]);

/**
 * Kinds **without** a spine. For them the Links tab is the only place a link
 * is readable as a row, so it lists *every* type instead of summarising the
 * derivation group (spec §2.3 rule 5).
 */
export const LINKS_ROWS_ONLY: ReadonlySet<ArtifactKind> = new Set<ArtifactKind>([
  "glossary",
  "icd",
  "diagram",
]);

/**
 * Link types that are read as rows **only** in the spine (spec §2.3 rule 1).
 * Keys are compared after the same `_` → `-` normalisation the API wrappers
 * apply (`derives_from` arrives with an underscore).
 */
export const SPINE_LINK_TYPES: ReadonlySet<string> = new Set<string>([
  "derives-from",
  "decomposes",
  "refines",
  "satisfies",
  "realizes",
  "allocated-to",
  "verifies",
]);

/** Normalise a backend link-type key for the matrix (`derives_from` → `derives-from`). */
export function normalizeLinkTypeKey(raw: string): string {
  return raw.replace(/_/g, "-");
}

/** True when this link type belongs to the spine-only group. */
export function isSpineLinkType(raw: string): boolean {
  return SPINE_LINK_TYPES.has(normalizeLinkTypeKey(raw));
}

// ---------------------------------------------------------------------------
// Tabs for one artifact
// ---------------------------------------------------------------------------

/**
 * The tab keys to render for this artifact, in spec order.
 *
 * `artifactPk` is the backing generic Artifact UUID (D5 id space). `null`
 * means "this kind's REST response does not publish it", which removes the
 * comments tab entirely (spec §4.3) instead of rendering a tab that cannot
 * load.
 */
export function inspectorTabKeys(
  kind: ArtifactKind,
  artifactPk: string | null,
): InspectorTabKey[] {
  return INSPECTOR_TAB_ORDER.filter((key) => {
    if (key === "links") return HAS_LINKS_TAB.has(kind);
    if (key === "comments") return artifactPk !== null && artifactPk !== "";
    return true;
  });
}

// ---------------------------------------------------------------------------
// DOM ids and data-testids (spec §7, §8.4)
// ---------------------------------------------------------------------------

export const INSPECTOR_HEADING_ID = "inspector-heading";

/** The inspector surface itself — the `aria-controls` target of rail and tabs. */
export const INSPECTOR_SURFACE_ID = "inspector-surface";

export const inspectorTabId = (key: InspectorTabKey): string => `inspector-tab-${key}`;
export const inspectorPanelId = (key: InspectorTabKey): string => `inspector-panel-${key}`;

/**
 * The `data-testid` inventory of the shell. IDs and testids are deliberately
 * the same strings (spec §7/§8.4) — one name to grep for, in tests and in the
 * E2E suite alike.
 */
export const INSPECTOR_TEST_IDS = {
  root: "inspector-shell",
  surface: "inspector-surface",
  tabs: "inspector-tabs",
  tab: (key: InspectorTabKey): string => inspectorTabId(key),
  panel: (key: InspectorTabKey): string => inspectorPanelId(key),
  rail: "inspector-rail",
  railOpen: "inspector-rail-open",
  railCount: (key: InspectorTabKey): string => `inspector-rail-count-${key}`,
  close: "inspector-close",
  splitter: "inspector-splitter",
  live: "inspector-live",
  alert: "inspector-alert",
  diffPair: "inspector-diff-pair",
  baselineSelect: "inspector-baseline-select",
} as const;

// ---------------------------------------------------------------------------
// Persistence (spec §5.4) and widths (spec §4.2)
// ---------------------------------------------------------------------------

/**
 * One storage slot for the two Goal kinds — switching between a goal and the
 * main goal must not move the tab selection (I-14).
 */
export const GOALS_TAB_STORAGE_KEY = "reqflow_inspector_tab_goals";

/** Storage key of the remembered tab for one artifact. */
export function inspectorTabStorageKey(
  kind: ArtifactKind,
  artifactId: string | number,
): string {
  if (kind === "goal" || kind === "mainGoal") return GOALS_TAB_STORAGE_KEY;
  return `reqflow_inspector_tab_${kind}_${artifactId}`;
}

/** Storage key of the remembered panel width for one kind. */
export function inspectorWidthStorageKey(kind: ArtifactKind): string {
  return `reqflow_inspector_width_${kind}`;
}

/**
 * The four width aliases of spec §4.1/§6.1. They are the only places a pixel
 * width for the inspector is allowed to exist; the CSS module redeclares them
 * as component aliases (`design-tokens.test.ts` requires local declarations).
 */
export const INSPECTOR_WIDTHS = {
  min: 280,
  default: 320,
  wide: 360,
  max: 520,
} as const;

/** Resize step of the splitter (`←`/`→`, spec §5.2 — `--space-4` = 16 px). */
export const INSPECTOR_RESIZE_STEP_PX = 16;

/**
 * Viewport breakpoints of the five width states (spec §4.2).
 * `sheetOpen` is the width from which the R3 sheet starts open.
 */
export const INSPECTOR_BREAKPOINTS = {
  wide: 1600,
  default: 1440,
  sheetOpen: 1280,
  sheet: 1024,
  rail: 768,
} as const;

export type InspectorRegion = "R1" | "R2" | "R3" | "R4" | "R5";
export type InspectorForm = "panel" | "rail" | "sheet" | "fullscreen";

/** The width state for a viewport width (spec §4.2). */
export function inspectorRegionFor(viewportWidth: number): InspectorRegion {
  if (viewportWidth >= INSPECTOR_BREAKPOINTS.wide) return "R1";
  if (viewportWidth >= INSPECTOR_BREAKPOINTS.default) return "R2";
  if (viewportWidth >= INSPECTOR_BREAKPOINTS.sheet) return "R3";
  if (viewportWidth >= INSPECTOR_BREAKPOINTS.rail) return "R4";
  return "R5";
}

/**
 * Whether the inspector starts open in a region (spec §4.2 "Default").
 *
 * R3 is the only region whose default depends on the *width* inside it:
 * "offen ab 1280 px, sonst Rail". The width therefore has to be passed in —
 * deriving it from the region alone would silently open the sheet at 1024 px,
 * where the spec wants the rail.
 */
export function inspectorDefaultsOpen(
  region: InspectorRegion,
  viewportWidth: number = Number.POSITIVE_INFINITY,
): boolean {
  if (region === "R1" || region === "R2") return true;
  if (region === "R3") return viewportWidth >= INSPECTOR_BREAKPOINTS.sheetOpen;
  return false;
}

/** The default width of a region: 360 in R1, 320 everywhere else. */
export function inspectorDefaultWidth(region: InspectorRegion): number {
  return region === "R1" ? INSPECTOR_WIDTHS.wide : INSPECTOR_WIDTHS.default;
}

/**
 * The rendered form for a region + open state.
 *
 * Rail and sheet are one component in two states (spec §2.1): "closed" always
 * means rail; only R5 turns an open inspector into a full-screen surface.
 */
export function inspectorFormFor(
  region: InspectorRegion,
  open: boolean,
): InspectorForm {
  if (!open) return "rail";
  if (region === "R1" || region === "R2") return "panel";
  if (region === "R5") return "fullscreen";
  return "sheet";
}

/** Clamp a width into the four-alias scale. */
export function clampInspectorWidth(width: number): number {
  if (!Number.isFinite(width)) return INSPECTOR_WIDTHS.default;
  return Math.max(INSPECTOR_WIDTHS.min, Math.min(INSPECTOR_WIDTHS.max, width));
}
