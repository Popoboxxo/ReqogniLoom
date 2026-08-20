/**
 * In-scope artifact types for interview sessions -- fixed at design time,
 * mirrors the Hermes plugin's `InterviewListView` (spec §1 of the engine
 * design). Not fetched from an API. Shared between `InterviewWidget` (the
 * floating start picker) and `InterviewEditors` (the workflow-tracked list
 * page, plan Task 6) so the two "start an interview" entry points never
 * drift apart.
 */
export const INTERVIEW_ARTIFACT_TYPES = [
  "Requirement",
  "ArchitectureElement",
  "StakeholderNeed",
  "Risk",
  "TestCase",
  "Adr",
  "Issue",
  "Goal",
] as const;

export type InterviewArtifactType = (typeof INTERVIEW_ARTIFACT_TYPES)[number];
