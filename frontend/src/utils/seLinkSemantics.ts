/**
 * SE endpoint semantics for trace links (se_mode rigor).
 *
 * Mirror of backend/traceability/types.py::SE_LINK_SEMANTICS — keep in sync.
 * See docs/se/workspace_modes_er_model.md (finding F1) for the rationale.
 *
 * Semantics:
 * - Link types absent from the matrix are unrestricted (traces, realizes,
 *   uses-term — deliberately generic).
 * - "*" is a wildcard endpoint.
 * - SAME_TYPE requires both endpoints to share the artifact type.
 * - Artifact types outside SE_CORE_ARTIFACT_TYPES are never constrained
 *   (permissive default, e.g. ICD or import artifacts).
 */

import type { LinkType } from "../types";

const REQ = "Requirement";
const ARCH = "ArchitectureElement";
const TC = "TestCase";
const SN = "StakeholderNeed";
const DIAG = "Diagram";

export const SE_CORE_ARTIFACT_TYPES: ReadonlySet<string> = new Set([
  REQ,
  ARCH,
  TC,
  SN,
  DIAG,
]);

const SAME_TYPE = "same-type" as const;

type EndpointPair = readonly [string, string];
type Rule = readonly EndpointPair[] | typeof SAME_TYPE;

export const SE_LINK_SEMANTICS: Readonly<Partial<Record<LinkType, Rule>>> = {
  "derives-from": [
    [REQ, REQ],
    [REQ, SN],
    [SN, SN],
  ],
  satisfies: [
    [ARCH, REQ],
    [REQ, SN],
  ],
  verifies: [
    [TC, REQ],
    [TC, ARCH],
  ],
  implements: [[ARCH, REQ]],
  refines: [
    [REQ, REQ],
    [ARCH, ARCH],
  ],
  "allocated-to": [
    [REQ, ARCH],
    [ARCH, ARCH],
  ],
  documents: [[DIAG, "*"]],
  "parent-child": SAME_TYPE,
  "copy-of": SAME_TYPE,
};

/** Strip sub-type tags: "TestCase:unit" → "TestCase". */
export function normalizeArtifactType(artifactType?: string | null): string {
  if (!artifactType) return "";
  return artifactType.split(":")[0];
}

/**
 * Return true if the link type is SE-conform between the two artifact types.
 * Unknown/non-core artifact types and unconstrained link types always pass.
 */
export function isSeConformLink(
  linkType: LinkType,
  sourceType?: string | null,
  targetType?: string | null
): boolean {
  const rule = SE_LINK_SEMANTICS[linkType];
  if (rule === undefined) return true;

  const src = normalizeArtifactType(sourceType);
  const tgt = normalizeArtifactType(targetType);
  if (!SE_CORE_ARTIFACT_TYPES.has(src) || !SE_CORE_ARTIFACT_TYPES.has(tgt)) {
    return true;
  }

  if (rule === SAME_TYPE) return src === tgt;

  return rule.some(
    ([ps, pt]) => (ps === "*" || ps === src) && (pt === "*" || pt === tgt)
  );
}

/**
 * Filter a list of link types down to the SE-conform ones for the given
 * endpoint artifact types. If nothing is selected yet, everything passes.
 */
export function allowedSeLinkTypes(
  linkTypes: readonly LinkType[],
  sourceType?: string | null,
  targetType?: string | null
): LinkType[] {
  return linkTypes.filter((lt) => isSeConformLink(lt, sourceType, targetType));
}
