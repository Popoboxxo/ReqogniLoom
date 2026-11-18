/**
 * RequirementEditors — pure view helpers (S3.2 WP-5 split by cohesion).
 *
 * Extracted verbatim from `RequirementEditors.tsx`: the Artifact-id
 * translation used by tree reparenting, the current-version anchor and the
 * role-gated AI-action list. Plain functions of their inputs (translator and
 * callbacks injected), so they are unit-testable without mounting the route;
 * the component keeps the hooks, the write callbacks and all JSX.
 *
 * No behaviour change: bodies, defaults and ordering are the ones that used to
 * live in the component.
 */

import type { TFunction } from "i18next";

import type { Requirement } from "../../types";
import type { VersionRef } from "../shared/ArtifactInspector";
import type { AiActionDescriptor } from "../shared/AiActions";

/** Requirement id → backing Artifact id (with an identity fallback). */
export function buildArtifactIdMap(
  requirements: Requirement[],
): Map<string, string> {
  return new Map<string, string>(
    requirements.map((req) => [req.id, req.artifact_id ?? req.id]),
  );
}

/** Resolve a tree node id to the Artifact id the move endpoint expects. */
export function resolveArtifactId(
  map: Map<string, string>,
  nodeId: string | null,
): string | null {
  return nodeId === null ? null : (map.get(nodeId) ?? nodeId);
}

/** Feed the ArtifactInspector with the current version row. */
export function buildCurrentVersion(
  requirement: Requirement | null | undefined,
): VersionRef | undefined {
  if (!requirement) return undefined;
  return {
    version: requirement.version,
    label: `v${requirement.version}`,
    createdAt: requirement.updated_at ?? requirement.created_at,
    baselineIds: [],
  };
}

/**
 * The route's complete AI-action set, gated by the workspace role. A viewer
 * gets an empty list, and `<AiActionSection>` renders nothing at all for an
 * empty list — the triggers are absent from the DOM, not merely disabled.
 */
export function buildAiActions(
  canUseAi: boolean,
  t: TFunction,
  handleAiDerive: () => void,
  isAiDeriving: boolean,
  openDeriveTestcasePanel: () => void,
): AiActionDescriptor[] {
  if (!canUseAi) return [];
  return [
    {
      label: t('actions.deriveAi', 'KI-Ableitung'),
      busyLabel: t('actions.derivingAi', 'KI-Ableitung läuft…'),
      hint: t(
        'actions.deriveAiHint',
        'Die KI erzeugt Entwürfe zur Prüfung – gespeichert wird erst nach deiner Bestätigung'
      ),
      onClick: () => void handleAiDerive(),
      disabled: isAiDeriving,
      testId: 'req-ai-derive-btn',
    },
    {
      // SysEng 2.0 N5: AI-generate a TestCase draft for this requirement.
      label: t('actions.deriveAiTestcase', 'KI-Testfall'),
      busyLabel: t('actions.derivingAiTestcase', 'KI-Testfall wird erzeugt…'),
      hint: t(
        'actions.deriveAiTestcaseHint',
        'Die KI erzeugt einen Testfall-Entwurf zur Prüfung – gespeichert wird erst nach deiner Bestätigung'
      ),
      onClick: openDeriveTestcasePanel,
      testId: 'req-derive-testcase-btn',
    },
  ];
}
