/**
 * ArtifactInspector (REQ-L2-RF-034..037) — shared types.
 *
 * leaf_id: COMP-RF-014 (ArtifactInspector)
 * req_id:  REQ-L2-RF-034 (RightSidebar shell),
 *          REQ-L2-RF-035 (VersionPanel),
 *          REQ-L2-RF-036 (DiffPanel),
 *          REQ-L2-RF-037 (TracePanel),
 *          REQ-L1-089..095 (UI standards baseline)
 *
 * The 10 artifact kinds that this sidebar is reused across. Order is fixed
 * and matches the design contract in docs/UI_STANDARDS.md §4.0.
 *
 * The first 7 kinds (icd, diagram, adr, risk, issue, glossary,
 * stakeholderNeed) do NOT yet expose a `/versions/` REST endpoint on the
 * backend — VersionPanel must render an empty state for those (UI standards
 * §5.1). The first 8 kinds do NOT expose a `/diff/` endpoint — DiffPanel
 * must render the "Diff not yet available for {kind}" empty state for
 * those (UI standards §4.5 / §11 open question #1).
 */
export type ArtifactKind =
  | "icd"
  | "diagram"
  | "adr"
  | "risk"
  | "issue"
  | "glossary"
  | "stakeholderNeed"
  | "requirement"
  | "architecture"
  | "testCase";

/**
 * The 8 link types that the TracePanel surfaces as filter chips
 * (UI standards §5.1 / §4.4). Mirrors the public LinkType union from
 * `frontend/src/types/index.ts`. The backend enum has 12 values; the
 * inspector subset is the public UI contract and any new type requires
 * a coordinated type + i18n update.
 */
export type LinkType =
  | "parent-child"
  | "derives-from"
  | "satisfies"
  | "verifies"
  | "implements"
  | "refines"
  | "documents"
  | "allocated-to";

/**
 * A single version entry surfaced by the VersionPanel. `baselineIds` is
 * the list of baselines that pin this version (resolved by the data hook
 * from `GET /api/v1/baselines/?artifact_id=<id>`).
 */
export interface VersionRef {
  version: number;
  label: string;
  createdAt: string | null;
  baselineIds: string[];
}

/**
 * A single trace-link row as rendered by the TracePanel. Direction is
 * pre-resolved by the data hook (inbound if the linked artifact is the
 * source, outbound if the current artifact is the source). The
 * `otherArtifact.route` is a SPA-relative path the panel can navigate to
 * via `useNavigate()`.
 *
 * Named `TraceLinkRow` to avoid clashing with the project-wide
 * `TraceLink` wire-format type in `frontend/src/types/index.ts`. The
 * design contract uses the same name (UI standards §4.0).
 */
export interface TraceLinkRow {
  id: string;
  direction: "inbound" | "outbound";
  linkType: LinkType;
  otherArtifact: {
    id: string;
    title: string;
    kind: ArtifactKind;
    route: string;
  };
  createdAt: string;
}

/**
 * A baseline summary used by the VersionPanel chip and the panel header
 * (UI standards §4.1). The `pinnedVersion` tells the panel which version
 * of the artifact is held by this baseline.
 */
export interface BaselineSummary {
  id: string;
  name: string;
  scope: "document" | "project" | "global";
  pinnedVersion: number;
}

/**
 * Narrow subset of the 10 ArtifactKind values for which the backend
 * actually exposes a `/diff/` endpoint today. Used by DiffPanel to
 * decide whether to render the "unsupported" empty state. The
 * `/versions/` endpoint is broader (requirement, architecture,
 * testCase) and the empty state collapses 404 + no-history into one
 * branch, so the VersionPanel does not need a matching constant.
 *
 * Source: `docs/UI_STANDARDS.md` §11 (Backend gaps column).
 */
export const DIFF_SUPPORTED_KINDS: ReadonlySet<ArtifactKind> = new Set([
  "requirement",
  "architecture",
]);

/** The 8 link types — exported as a stable list for chip rendering. */
export const ALL_LINK_TYPES: ReadonlyArray<LinkType> = [
  "parent-child",
  "derives-from",
  "satisfies",
  "verifies",
  "implements",
  "refines",
  "documents",
  "allocated-to",
];
