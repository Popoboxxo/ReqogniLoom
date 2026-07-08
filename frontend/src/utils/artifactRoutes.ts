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
  // camelCase ArtifactKind aliases (ArtifactInspector)
  testCase: "/testcases",
  stakeholderNeed: "/needs",
};

/**
 * Builds the SPA route for a linked artifact. Falls back to `/requirements`
 * when the entity type is unknown so navigation never breaks.
 */
export const getArtifactRoute = (entityType: string, id: string): string => {
  const prefix = ARTIFACT_ROUTE_MAP[entityType] ?? "/requirements";
  return `${prefix}/${id}`;
};
