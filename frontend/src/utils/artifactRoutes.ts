/**
 * ARCH-L1-001 ReactFrontend — artifact route resolution.
 *
 * req_id: REQ-L1-003 (Traceability-Engine), REQ-L2-RF-006 (Traceability-Anzeige)
 *
 * Maps an artifact's entity/type string to its SPA route prefix so trace-link
 * navigation lands on the correct editor instead of always assuming
 * `/requirements/`. Route prefixes are verified against the router in
 * NavigationShell.tsx.
 *
 * The backend exposes the Artifact-backed `artifact_type` in PascalCase
 * (Requirement, ArchitectureElement, TestCase, StakeholderNeed). The
 * snake_case aliases (requirement, test_case, ...) are kept so callers can
 * pass either representation.
 */

export const ARTIFACT_ROUTE_MAP: Record<string, string> = {
  // snake_case entity_type aliases
  requirement: "/requirements",
  architecture: "/architecture",
  architecture_element: "/architecture",
  test_case: "/testcases",
  adr: "/adrs",
  risk: "/risks",
  issue: "/issues",
  stakeholder_need: "/needs",
  icd: "/icds",
  // PascalCase backend artifact_type values
  Requirement: "/requirements",
  ArchitectureElement: "/architecture",
  TestCase: "/testcases",
  StakeholderNeed: "/needs",
  // PascalCase entity_type values as returned by GET /traceability/resolve/
  // (Task 3.2a/3.3) — the quartet and Goal were previously missing here and
  // fell through to the "/requirements" fallback.
  Adr: "/adrs",
  Risk: "/risks",
  Issue: "/issues",
  Goal: "/goals",
  MainGoal: "/goals",
  // camelCase ArtifactKind aliases (ArtifactInspector)
  testCase: "/testcases",
  stakeholderNeed: "/needs",
  // Legacy TestCase sub-type tags (DATA-08, audit finding 181/189). Residual
  // artifacts created before/outside the backend normaliser still carry a
  // "TestCase:<Type>" artifact_type; every sub-type belongs on the TestCase
  // editor, not the "/requirements" fallback. The canonical writer emits
  // Title-case suffixes, listed explicitly so ARTIFACT_ROUTE_MAP consumers
  // (e.g. api/artifactRefs.ts) resolve them too.
  "TestCase:Unit": "/testcases",
  "TestCase:System": "/testcases",
  "TestCase:Integration": "/testcases",
  "TestCase:Inspection": "/testcases",
  "TestCase:Analysis": "/testcases",
  "TestCase:Demonstration": "/testcases",
};

/** Prefix of the deprecated `"TestCase:<Type>"` artifact_type tag. */
const TEST_CASE_SUBTYPE_PREFIX = "TestCase:";

/**
 * Builds the SPA route for a linked artifact. Falls back to `/requirements`
 * when the entity type is unknown so navigation never breaks.
 */
export const getArtifactRoute = (entityType: string, id: string): string => {
  const prefix =
    ARTIFACT_ROUTE_MAP[entityType] ??
    // Defensive: any residual case/type variant (e.g. "TestCase:unit") of the
    // legacy TestCase sub-type tag still lands on the TestCase editor.
    (entityType.startsWith(TEST_CASE_SUBTYPE_PREFIX) ? "/testcases" : undefined) ??
    "/requirements";
  return `${prefix}/${id}`;
};
