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

/**
 * Sentinel `?start=` value for a multi-kind discovery session (spec L2.5) --
 * the one "type" the picker offers that is not an artifact type. Lives here
 * for the same reason the list above does: both entry points need it, and an
 * always-mounted overlay must not import from a route page module.
 */
export const MULTI_START_PARAM = "multi";
