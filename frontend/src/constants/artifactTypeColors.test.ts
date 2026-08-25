/**
 * Unit tests for the artifact-type color-token constants
 * (multi-artifact interview plan, Task 9).
 *
 * Verifies:
 *   - All 9 in-scope artifact types (incl. GlossaryTerm) are mapped to a
 *     --color-artifacttype-* CSS custom property
 *   - getArtifactTypeColorVar falls back to var(--color-artifacttype-default)
 *     for unknown types
 *   - Known types resolve to their mapped var() wrapper
 */
import { describe, it, expect } from "vitest";
import { ARTIFACT_TYPE_COLOR_VAR, getArtifactTypeColorVar } from "./artifactTypeColors";

describe("artifactTypeColors", () => {
  it("has an entry for all 9 in-scope types plus GlossaryTerm", () => {
    const expected = [
      "StakeholderNeed", "Requirement", "ArchitectureElement", "Risk",
      "TestCase", "Adr", "Issue", "Goal", "GlossaryTerm",
    ];
    expected.forEach((type) => expect(ARTIFACT_TYPE_COLOR_VAR[type]).toBeDefined());
  });

  it("getArtifactTypeColorVar falls back to default for unknown types", () => {
    expect(getArtifactTypeColorVar("Unknown")).toBe("var(--color-artifacttype-default)");
  });

  it("getArtifactTypeColorVar returns the mapped var() for known types", () => {
    expect(getArtifactTypeColorVar("Requirement")).toBe("var(--color-artifacttype-requirement)");
  });
});
