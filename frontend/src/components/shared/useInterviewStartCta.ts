/**
 * `useInterviewStartCta` — the shared "create it in a guided dialog" CTA that
 * sits next to the primary action in every artifact route's <PageHeader>.
 *
 * req_id: REQ-L2-RF-030 (generic reusable frontend components)
 *
 * Why a hook instead of eight object literals: the same action object was
 * copy-pasted into RequirementEditors, AdrEditors, RiskEditors, IssueEditors,
 * NeedsEditors, ArchitectureEditors, TestCaseEditors and GoalsPage. Every
 * copy repeated the label key, the `/interviews?start=` URL shape, the
 * "disabled without an active workspace" rule and the `interview-start-cta`
 * test id, so a change to any of them (and the copies had already started to
 * drift in quoting and formatting) had to be made eight times. Centralising
 * the object keeps the CTA identical across routes by construction — which is
 * the point of the shared page header in the first place.
 *
 * The `artifactType` is typed against INTERVIEW_ARTIFACT_TYPES rather than
 * `string`: an interview can only be started for a type the interview engine
 * actually knows, and a typo previously produced a CTA that navigated to a
 * dead `?start=` value with no compile-time complaint.
 */

import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import type { InterviewArtifactType } from "../../constants/interviewArtifactTypes";
import { useWorkspace } from "../../context/WorkspaceContext";
import type { PageHeaderAction } from "./PageHeader";

/**
 * Builds the `secondaryActions` entry that starts a guided interview for
 * `artifactType`.
 *
 * @param artifactType - Artifact type the interview should produce.
 * @returns A ready-to-spread {@link PageHeaderAction} for <PageHeader>.
 */
export function useInterviewStartCta(
  artifactType: InterviewArtifactType,
): PageHeaderAction {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { activeWorkspace } = useWorkspace();

  return useMemo(
    () => ({
      label: t("interviews.startCta"),
      onClick: () => navigate(`/interviews?start=${artifactType}`),
      // An interview writes its result into the active workspace; without one
      // there is nothing to write to.
      disabled: !activeWorkspace,
      testId: "interview-start-cta",
    }),
    [t, navigate, artifactType, activeWorkspace],
  );
}
