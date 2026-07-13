/**
 * ARCH-L1-001 ReactFrontend — shared trace-link type labels.
 *
 * req_id: REQ-L1-003 (Traceability-Engine), REQ-L2-RF-006 (Traceability-Anzeige)
 *
 * Single source of truth for human-readable LinkType labels across the
 * traceability UI (TracePanel, TraceabilityView, TraceLinkPanel,
 * ReqTraceLinkPanel). Mirrors backend/traceability/types.py::LinkType
 * (13 values). Keeping the map here avoids each component re-deriving its
 * own label strings and drifting apart.
 */

/** Raw backend link_type -> human-readable label. */
export const LINK_TYPE_LABELS: Record<string, string> = {
  "parent-child": "Parent / Child",
  "derives-from": "Derives From",
  satisfies: "Satisfies",
  verifies: "Verifies",
  implements: "Implements",
  refines: "Refines",
  documents: "Documents",
  realizes: "Realizes",
  traces: "Traces",
  "copy-of": "Copy Of",
  "allocated-to": "Allocated To",
  "uses-term": "Uses Term",
  decides: "Decides",
};

/** Returns the human-readable label for a link type, or the raw value as fallback. */
export const getLinkTypeLabel = (lt: string): string => LINK_TYPE_LABELS[lt] ?? lt;

/** Canonical list of all link types (backend enum order). */
export const ALL_LINK_TYPES = Object.keys(LINK_TYPE_LABELS);
