/**
 * Artifact-type color tokens for the multi-artifact interview proposal
 * preview graph (plan Task 9).
 *
 * Maps each in-scope artifact type to a --color-artifacttype-* CSS custom
 * property declared in styles/tokens.css. Consumers wrap the name via
 * getArtifactTypeColorVar so unknown types degrade to the default token
 * instead of producing an undefined var() reference.
 */
export const ARTIFACT_TYPE_COLOR_VAR: Record<string, string> = {
  StakeholderNeed: "--color-artifacttype-stakeholderneed",
  Requirement: "--color-artifacttype-requirement",
  ArchitectureElement: "--color-artifacttype-architectureelement",
  Risk: "--color-artifacttype-risk",
  TestCase: "--color-artifacttype-testcase",
  Adr: "--color-artifacttype-adr",
  Issue: "--color-artifacttype-issue",
  Goal: "--color-artifacttype-goal",
  GlossaryTerm: "--color-artifacttype-glossaryterm",
};

/**
 * Resolve the CSS var() wrapper for an artifact type's node color.
 * Unknown types fall back to --color-artifacttype-default.
 */
export function getArtifactTypeColorVar(type: string): string {
  const varName = ARTIFACT_TYPE_COLOR_VAR[type] ?? "--color-artifacttype-default";
  return `var(${varName})`;
}
