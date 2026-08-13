/**
 * Shared TraceLink endpoint resolution (issues #413, #415, #416).
 *
 * Every trace-related surface (TraceabilityView, ImpactView, ReqTraceLinkPanel,
 * RequirementTreeNode) has to answer the same three questions about a
 * `TraceLink`:
 *
 *   1. Which endpoint is "the other side" relative to the artifact I render?
 *   2. What is that endpoint's human-readable title and artifact type?
 *   3. Is this link part of the requirement hierarchy / of test coverage?
 *
 * Each surface used to answer them inline, and each got it wrong in a
 * different way:
 *
 * - **Identity.** `TraceLink.source_id` / `target_id` are always **Artifact**
 *   ids, never the domain-entity id (`Requirement.id`, `TestCase.id`, ...).
 *   A component holding a Requirement id therefore matches *neither* endpoint,
 *   so `link.source_id === currentId ? target : source` silently resolved to
 *   the artifact itself (#416) and title maps keyed by entity id never hit
 *   (#413). `selfIds` here is a *set*, so callers can pass both the entity id
 *   and the backing `artifact_id` and stop caring which one the API used.
 * - **Titles.** The backend already ships `source_title` / `target_title` /
 *   `source_type` / `target_type` on every TraceLink (REQ-002). Re-deriving
 *   them from separately fetched entity lists is both redundant and, because
 *   of the identity mismatch above, wrong.
 * - **Hierarchy.** `derived-by` is not a backend link type — filtering on it
 *   dropped every real hierarchy link (`decomposes`, `parent-child`).
 *
 * Mirrors `backend/traceability/types.py::LinkType` and the SE endpoint
 * semantics in `frontend/src/utils/seLinkSemantics.ts`.
 */

import type { LinkType, TraceLink, UUID } from "../types";

/** Number of leading UUID characters shown when no title is available. */
const SHORT_ID_LENGTH = 8;

/** A resolved endpoint of a trace link: id plus display metadata. */
export interface TraceEndpoint {
  id: UUID;
  /** Backend-resolved title; empty string when the artifact has none. */
  title: string;
  /** Backend-resolved artifact type ("Requirement", "TestCase", ...). */
  artifactType: string;
}

/** Direction of a link as seen from the artifact currently being rendered. */
export type TraceDirection = "outgoing" | "incoming";

/** The far endpoint of a link plus how it is reached from the current node. */
export interface TraceNeighbor {
  link: TraceLink;
  direction: TraceDirection;
  endpoint: TraceEndpoint;
}

/** Position of a neighbour in the requirement decomposition hierarchy. */
export type HierarchyRelation = "parent" | "child";

/**
 * Link types that express a requirement/architecture decomposition hierarchy.
 * `derived-by` deliberately absent — it never existed in the backend enum.
 */
export const HIERARCHY_LINK_TYPES: readonly LinkType[] = [
  "derives-from",
  "decomposes",
  "parent-child",
];

/** Link types that constitute verification coverage (TestCase -> artifact). */
export const VERIFICATION_LINK_TYPES: readonly LinkType[] = ["verifies"];

/** Shorten a UUID for display: `9c706550-…` -> `9c706550…`. */
export function formatShortId(id: UUID): string {
  return `${id.slice(0, SHORT_ID_LENGTH)}…`;
}

/** Read one side of a link as a {@link TraceEndpoint}. */
export function endpointOf(link: TraceLink, side: "source" | "target"): TraceEndpoint {
  return side === "source"
    ? {
        id: link.source_id,
        title: link.source_title ?? "",
        artifactType: link.source_type ?? "",
      }
    : {
        id: link.target_id,
        title: link.target_title ?? "",
        artifactType: link.target_type ?? "",
      };
}

/**
 * Resolve the endpoint on the *far* side of `link` relative to `selfIds`.
 *
 * `selfIds` should contain every id the current node may be known by — its
 * Artifact id and, where applicable, its domain-entity id. Returns `null` when
 * the link touches neither (a link that does not belong to this node) and for
 * self-links, which carry no information for a neighbour list.
 */
export function neighborOf(
  link: TraceLink,
  selfIds: ReadonlySet<UUID>
): TraceNeighbor | null {
  const isSource = selfIds.has(link.source_id);
  const isTarget = selfIds.has(link.target_id);
  if (isSource === isTarget) return null; // neither side, or a self-link
  const direction: TraceDirection = isSource ? "outgoing" : "incoming";
  return { link, direction, endpoint: endpointOf(link, isSource ? "target" : "source") };
}

/**
 * Title for display, falling back to a shortened id when the backend could not
 * resolve one (dangling endpoint, or a pre-REQ-002 API response).
 * `fallbackTitle` lets callers inject a locally known title first.
 */
export function endpointLabel(
  endpoint: TraceEndpoint,
  fallbackTitle?: string
): string {
  if (endpoint.title) return endpoint.title;
  if (fallbackTitle) return fallbackTitle;
  return formatShortId(endpoint.id);
}

/**
 * Classify a link as parent/child relative to `selfIds`, or `null` when it is
 * not a hierarchy link at all.
 *
 * Reading direction (backend Tri-Labels, `constants/traceLinkLabels.ts`):
 *   - `A derives-from B`  -> B is A's parent
 *   - `A decomposes B`    -> B is A's child ("decomposes into")
 *   - `A parent-child B`  -> B is A's child
 */
export function hierarchyRelation(
  link: TraceLink,
  selfIds: ReadonlySet<UUID>
): { relation: HierarchyRelation; neighbor: TraceNeighbor } | null {
  if (!HIERARCHY_LINK_TYPES.includes(link.link_type as LinkType)) return null;
  const neighbor = neighborOf(link, selfIds);
  if (!neighbor) return null;
  const otherIsParentWhenOutgoing = link.link_type === "derives-from";
  const relation: HierarchyRelation =
    neighbor.direction === "outgoing"
      ? otherIsParentWhenOutgoing
        ? "parent"
        : "child"
      : otherIsParentWhenOutgoing
        ? "child"
        : "parent";
  return { relation, neighbor };
}

/**
 * Artifact ids that are verified by at least one test case (#413 coverage).
 *
 * SE semantics put the TestCase on the source side (`TestCase verifies
 * Requirement`), but links authored the other way round are tolerated: the
 * endpoint that is *not* the TestCase counts as verified.
 */
export function collectVerifiedArtifactIds(links: readonly TraceLink[]): Set<UUID> {
  const verified = new Set<UUID>();
  for (const link of links) {
    if (!VERIFICATION_LINK_TYPES.includes(link.link_type as LinkType)) continue;
    verified.add(link.source_type === "TestCase" ? link.target_id : link.source_id);
  }
  return verified;
}

/**
 * Best-effort recovery of the Artifact id a link list was fetched for.
 *
 * `GET /tracelinks/?artifact_id=<id>` returns only links touching that
 * artifact, so its id is the one endpoint every returned link has in common.
 * Used as a fallback when the caller knows the entity id but not the backing
 * `artifact_id` (older API responses). Returns `null` when the result is
 * ambiguous — with a single link both endpoints are equally plausible, and
 * guessing would resolve a neighbour to the artifact itself, which is exactly
 * the bug this module exists to prevent (#416).
 */
export function inferSelfArtifactId(links: readonly TraceLink[]): UUID | null {
  if (links.length < 2) return null;
  let candidates: Set<UUID> | null = null;
  for (const link of links) {
    const endpoints = new Set<UUID>([link.source_id, link.target_id]);
    if (candidates === null) {
      candidates = endpoints;
      continue;
    }
    candidates = new Set([...candidates].filter((id) => endpoints.has(id)));
    if (candidates.size === 0) return null;
  }
  if (!candidates || candidates.size !== 1) return null;
  return [...candidates][0];
}

/**
 * Build an `artifactId -> title` index from the endpoint metadata the backend
 * already ships on every link. Keyed by Artifact id, so it is safe to look up
 * with a TraceLink endpoint id — unlike a map built from entity list responses.
 */
export function buildArtifactTitleIndex(
  links: readonly TraceLink[]
): Record<UUID, string> {
  const titles: Record<UUID, string> = {};
  for (const link of links) {
    if (link.source_title) titles[link.source_id] = link.source_title;
    if (link.target_title) titles[link.target_id] = link.target_title;
  }
  return titles;
}
