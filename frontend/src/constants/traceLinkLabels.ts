/**
 * ARCH-L1-001 ReactFrontend — shared trace-link type Tri-Label system.
 *
 * req_id: REQ-L1-003 (Traceability-Engine), REQ-L2-RF-006 (Traceability-Anzeige)
 *
 * Single source of truth for human-readable LinkType labels across the
 * traceability UI (TracePanel, TraceabilityView, TraceLinkPanel,
 * ReqTraceLinkPanel, the Admin Tri-Label overview).
 *
 * Task 23: the per-workspace link-type catalog (`useLinkTypes()`,
 * `context/LinkTypeContext.tsx`) is now the source of truth — a tenant can
 * customize or add link types, so no static frontend table can cover every
 * key any more. `FALLBACK_TRI_LABELS` below is only the pre-load fallback
 * for the eight built-in keys (mirrors `backend/link_types/builtin.py`),
 * used before the catalog has loaded or by callers that have no catalog
 * label at hand. A key that is neither in the fallback table nor backed by
 * a catalog label renders as its own raw string — see `getTriLabel`.
 */

export type SupportedLang = "de" | "en";
export type LinkDirection = "downstream" | "upstream" | "neutral";

/** One perspective triple (downstream/upstream/neutral) for one language. */
export interface TriLabel {
  downstream: string;
  upstream: string;
  neutral: string;
}

export interface TriLabelEntry {
  de: TriLabel;
  en: TriLabel;
}

/**
 * Pre-load fallback for the eight built-in link types — label text mirrors
 * `backend/link_types/builtin.py::BUILTIN_LINK_TYPES` exactly, so there is
 * no visible flash of different text once the real catalog label arrives.
 * NOT exhaustive: a tenant-customized or tenant-invented type has no entry
 * here and falls back further to its raw key (see `getTriLabel`).
 */
export const FALLBACK_TRI_LABELS: Record<string, TriLabelEntry> = {
  "derives-from": {
    de: { downstream: "leitet sich ab von", upstream: "ist Grundlage für", neutral: "Ableitung" },
    en: { downstream: "derives from", upstream: "is basis for", neutral: "Derivation" },
  },
  decomposes: {
    de: { downstream: "zerlegt sich in", upstream: "ist Teil von", neutral: "Zerlegung" },
    en: { downstream: "decomposes into", upstream: "is part of", neutral: "Decomposition" },
  },
  "allocated-to": {
    de: { downstream: "ist zugewiesen an", upstream: "erfüllt", neutral: "Zuweisung" },
    en: { downstream: "is allocated to", upstream: "fulfils", neutral: "Allocation" },
  },
  verifies: {
    de: { downstream: "verifiziert", upstream: "wird verifiziert von", neutral: "Verifikation" },
    en: { downstream: "verifies", upstream: "is verified by", neutral: "Verification" },
  },
  decides: {
    de: { downstream: "entscheidet über", upstream: "wird entschieden durch", neutral: "Entscheidung" },
    en: { downstream: "decides", upstream: "is decided by", neutral: "Decision" },
  },
  mitigates: {
    de: { downstream: "mindert", upstream: "wird gemindert durch", neutral: "Risikominderung" },
    en: { downstream: "mitigates", upstream: "is mitigated by", neutral: "Mitigation" },
  },
  references: {
    de: { downstream: "verweist auf", upstream: "wird referenziert von", neutral: "Verweis" },
    en: { downstream: "references", upstream: "is referenced by", neutral: "Reference" },
  },
  "diagram-ref": {
    de: { downstream: "stellt dar", upstream: "wird dargestellt in", neutral: "Diagrammbezug" },
    en: { downstream: "depicts", upstream: "is depicted in", neutral: "Diagram reference" },
  },
};

/**
 * Resolve a link-type label.
 *
 * The catalog label wins. The static table above is only the pre-load
 * fallback for the eight built-in keys — a tenant-invented type has no
 * static entry and renders as its raw key until the catalog arrives.
 */
export function getTriLabel(
  key: string,
  lang: SupportedLang,
  direction: LinkDirection,
  catalogLabel?: TriLabel,
): string {
  if (catalogLabel) return catalogLabel[direction];
  return FALLBACK_TRI_LABELS[key]?.[lang]?.[direction] ?? key;
}

/**
 * Backward-compatible flat label map (EN neutral form) — consumed by
 * badge/dropdown UI that is not yet catalog-aware (ImpactView,
 * ReqTraceLinkPanel, TracePanel, TraceLinkPanel, trace-link-display,
 * TraceabilityView, plus the create-link dialog and workspace settings
 * before Task 23). Derived from `FALLBACK_TRI_LABELS`, so it only covers the
 * eight built-in keys — a tenant-invented type falls back to its raw key,
 * same as `getTriLabel`.
 */
export const LINK_TYPE_LABELS: Record<string, string> = Object.fromEntries(
  Object.keys(FALLBACK_TRI_LABELS).map((lt) => [lt, FALLBACK_TRI_LABELS[lt].en.neutral])
);

/**
 * Returns the human-readable (EN neutral) label for a link type, falling
 * back to the raw key for anything outside the eight built-in types.
 */
export const getLinkTypeLabel = (lt: string): string => LINK_TYPE_LABELS[lt] ?? lt;
