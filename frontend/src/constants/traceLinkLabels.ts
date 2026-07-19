/**
 * ARCH-L1-001 ReactFrontend — shared trace-link type Tri-Label system.
 *
 * req_id: REQ-L1-003 (Traceability-Engine), REQ-L2-RF-006 (Traceability-Anzeige)
 *
 * Single source of truth for human-readable LinkType labels across the
 * traceability UI (TracePanel, TraceabilityView, TraceLinkPanel,
 * ReqTraceLinkPanel, the Admin Tri-Label overview). Mirrors backend
 * `backend/traceability/types.py::LinkType` (14 values, incl. `decomposes`).
 *
 * Tri-Label system (see docs/UMSETZUNGSPLAN_SYSENG_2.0.md §1.3, Decision
 * 2026-07-19): every one of the 14 LinkType values has a DE and an EN label
 * for each of the three perspectives:
 *   - downstream — read "from source to target" (e.g. "satisfies")
 *   - upstream   — read "from target to source" (e.g. "is satisfied by")
 *   - neutral    — direction-agnostic short name for badges/dropdowns
 * This is the ONLY display scheme for TraceLink types — a pure lookup-table
 * access, no `if type in LABELED_SET ... else raw enum` fallback branch.
 */

import type { LinkType } from "../types";

export type SupportedLang = "de" | "en";
export type LinkDirection = "downstream" | "upstream" | "neutral";

export interface TriLabelEntry {
  de: { downstream: string; upstream: string; neutral: string };
  en: { downstream: string; upstream: string; neutral: string };
}

/**
 * Full Tri-Label table — all 14 backend LinkType values, DE + EN,
 * downstream/upstream/neutral. Order mirrors the backend enum
 * (`backend/traceability/types.py::LinkType`), with `decomposes` appended
 * last (additive, see UMSETZUNGSPLAN §1.4).
 */
export const LINK_TYPE_TRI_LABELS: Record<LinkType, TriLabelEntry> = {
  "parent-child": {
    de: {
      downstream: "ist übergeordnet zu",
      upstream: "ist untergeordnet zu",
      neutral: "Eltern-Kind (legacy)",
    },
    en: {
      downstream: "is parent of",
      upstream: "is child of",
      neutral: "Parent-Child (legacy)",
    },
  },
  "derives-from": {
    de: { downstream: "leitet sich ab von", upstream: "ist Grundlage für", neutral: "Ableitung" },
    en: { downstream: "derives from", upstream: "is basis for", neutral: "Derivation" },
  },
  satisfies: {
    de: { downstream: "erfüllt", upstream: "wird erfüllt von", neutral: "Erfüllung" },
    en: { downstream: "satisfies", upstream: "is satisfied by", neutral: "Satisfaction" },
  },
  verifies: {
    de: { downstream: "verifiziert", upstream: "wird verifiziert von", neutral: "Verifikation" },
    en: { downstream: "verifies", upstream: "is verified by", neutral: "Verification" },
  },
  implements: {
    de: { downstream: "implementiert", upstream: "wird implementiert von", neutral: "Implementierung" },
    en: { downstream: "implements", upstream: "is implemented by", neutral: "Implementation" },
  },
  refines: {
    de: { downstream: "verfeinert", upstream: "wird verfeinert von", neutral: "Verfeinerung" },
    en: { downstream: "refines", upstream: "is refined by", neutral: "Refinement" },
  },
  documents: {
    de: { downstream: "dokumentiert", upstream: "wird dokumentiert von", neutral: "Dokumentation" },
    en: { downstream: "documents", upstream: "is documented by", neutral: "Documentation" },
  },
  realizes: {
    de: { downstream: "realisiert", upstream: "wird realisiert von", neutral: "Realisierung" },
    en: { downstream: "realizes", upstream: "is realized by", neutral: "Realization" },
  },
  traces: {
    de: { downstream: "verweist auf", upstream: "wird referenziert von", neutral: "Verweis" },
    en: { downstream: "traces to", upstream: "is traced by", neutral: "Trace" },
  },
  "copy-of": {
    de: { downstream: "ist Kopie von", upstream: "hat Kopie", neutral: "Kopie" },
    en: { downstream: "is copy of", upstream: "has copy", neutral: "Copy" },
  },
  "allocated-to": {
    de: { downstream: "allokiert zu", upstream: "erhält Allokation von", neutral: "Allokation" },
    en: { downstream: "allocated to", upstream: "receives allocation from", neutral: "Allocation" },
  },
  "uses-term": {
    de: { downstream: "verwendet Begriff", upstream: "wird verwendet in", neutral: "Begriffsverwendung" },
    en: { downstream: "uses term", upstream: "is used in", neutral: "Term usage" },
  },
  decides: {
    de: { downstream: "entscheidet über", upstream: "wird entschieden durch", neutral: "Entscheidung" },
    en: { downstream: "decides on", upstream: "is decided by", neutral: "Decision" },
  },
  decomposes: {
    de: { downstream: "zerlegt sich in", upstream: "ist Zerlegung von", neutral: "Dekomposition" },
    en: { downstream: "decomposes into", upstream: "is decomposition of", neutral: "Decomposition" },
  },
};

/** Canonical list of all 14 link types (backend enum order, incl. `decomposes`). */
export const ALL_LINK_TYPES: LinkType[] = Object.keys(
  LINK_TYPE_TRI_LABELS
) as LinkType[];

/**
 * Pure lookup-table access to a single directional/neutral label.
 * All 14 LinkType values are covered — no fallback path.
 */
export function getTriLabel(
  linkType: LinkType,
  lang: SupportedLang,
  direction: LinkDirection
): string {
  return LINK_TYPE_TRI_LABELS[linkType][lang][direction];
}

/**
 * Backward-compatible flat label map (EN neutral form) — consumed by
 * badge/dropdown UI that is not yet direction-aware (TraceLinkPanel,
 * TracePanel, TraceabilityView, CreateTraceLinkDialog, WorkspaceSettings).
 * Derived from the Tri-Label table so both stay in sync automatically.
 */
export const LINK_TYPE_LABELS: Record<string, string> = Object.fromEntries(
  ALL_LINK_TYPES.map((lt) => [lt, LINK_TYPE_TRI_LABELS[lt].en.neutral])
);

/**
 * Returns the human-readable (EN neutral) label for a link type.
 * Pure lookup-table access — all 14 backend LinkType values are covered,
 * so no fallback to the raw enum value is needed anymore.
 */
export const getLinkTypeLabel = (lt: string): string => LINK_TYPE_LABELS[lt];
