/**
 * ARCH-L1-001 ReactFrontend — GoalDetail (REQ-L2-TE-020).
 *
 * Detail pane of the Goals split view (UI concept ch. 12.4 / 12.6 / 12.11).
 * Until now the route had no detail view at all — title, status and version
 * were crammed into a list row and nothing else about a Goal was reachable.
 *
 * Shows, in the order the concept prescribes:
 *   1. identity row  — <ArtifactId>, <StatusBadge>, <VersionBadge>
 *   2. title + description
 *   3. actions       — edit (= new lineage version) plus one button per move
 *                      the WorkflowEngine currently allows (issue #220: never
 *                      gated on hardcoded state names — a workspace may
 *                      customise its Goal state machine, ADR-06). The archive
 *                      move is separated out and danger-styled (issue #238):
 *                      it takes the goal out of the list, so it must not look
 *                      like the approve/rework buttons beside it.
 *   4. workspace-defined attributes via <ArtifactCustomFields> (ch. 12.11)
 *
 * Version history is NOT rendered here any more (issue #219): it now lives in
 * the `<ArtifactInspector>` sidebar the page mounts next to this pane, whose
 * `VersionPanel` reads the very same `GET /goals/{id}/versions/` endpoint and
 * additionally offers switch/compare. Two surfaces for one job is exactly
 * what ch. 3.4 ("Eine Fläche, eine Aufgabe") forbids — same reason
 * RiskEditors keeps its version list only in the sidebar.
 *
 * Mutations are delegated upwards: the page owns the API calls so that a
 * rejected action surfaces in exactly one place (ch. 12.12).
 */

import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { goalsApi } from "../../api/goals";
import { ArtifactCustomFields } from "../shared/ArtifactCustomFields";
import { ArtifactId } from "../shared/ArtifactId";
import { StatusBadge } from "../shared/StatusBadge";
import { VersionBadge } from "../shared/VersionBadge";
import { TraceSpine, useDerivationChain } from "../shared/TraceSpine";
import type { ChainArtifact } from "../shared/TraceSpine";
import { getArtifactRoute } from "../../utils/artifactRoutes";
import { isArchiveTransition } from "./goal-workflow";
import type { WorkflowAllowedTransition } from "../../api/workflow-transitions";
import type { Goal } from "../../types";

export interface GoalDetailProps {
  goal: Goal;
  onEdit: (goal: Goal) => void;
  /**
   * Perform one of the moves the WorkflowEngine currently allows. The whole
   * transition descriptor is handed over (not just the target state) so the
   * page can honour `requires_change_reason` without re-deriving it, and can
   * confirm the archive move before it runs.
   */
  onTransition: (goal: Goal, transition: WorkflowAllowedTransition) => void;
}

export function GoalDetail({ goal, onEdit, onTransition }: GoalDetailProps): JSX.Element {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [transitions, setTransitions] = useState<WorkflowAllowedTransition[]>([]);

  // Trace spine (Task 3.3 — UI concept ch. 5). Goal is one of the nine
  // types the `/traceability/resolve/` endpoint covers (Task 3.2a); it has
  // no special station/level handling of its own in useDerivationChain,
  // which is fine — it falls back to a single generic "Goal" station.
  const derivationChain = useDerivationChain(
    goal.artifact_id ?? goal.id,
    'Goal',
    null,
    { enabled: !!goal },
  );

  const handleOpenChainArtifact = useCallback(
    (artifact: ChainArtifact): void => {
      const entry = derivationChain.resolveEntry(artifact);
      if (entry) navigate(getArtifactRoute(entry.entityType, entry.entityId));
    },
    [derivationChain, navigate],
  );

  // Issue #220: the lifecycle controls are driven by the WorkflowEngine, not
  // by string equality against hardcoded German state names. A workspace may
  // customise its Goal state machine (ADR-06), so which moves exist — and
  // what they are called — is only knowable from the server. Same contract
  // and same "render allowed_transitions as actions" shape ReviewsView and
  // WorkflowStatusEditor use for every other artifact type.
  //
  // `goal.status` is in the dependency list on purpose: a completed
  // transition changes it, which must re-fetch the now-different move set.
  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const resp = await goalsApi.getTransitions(goal.id);
        if (cancelled) return;
        setTransitions(
          Array.isArray(resp?.allowed_transitions) ? resp.allowed_transitions : []
        );
      } catch {
        // A 404 means "no workflow configured for this workspace/type"; a
        // 403 means the caller may not move it. Both degrade to a read-only
        // detail pane rather than an error banner — the edit action stays
        // usable (WorkflowStatusEditor does the same).
        if (!cancelled) setTransitions([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [goal.id, goal.status]);

  // The archive move is destructive from the user's point of view (the goal
  // leaves the list), so it is pulled out of the lifecycle row and rendered
  // last, danger-styled — see goal-workflow.ts for why this is classified
  // rather than name-matched.
  const lifecycleTransitions = transitions.filter(
    (tr) => !isArchiveTransition(tr.target_state),
  );
  const archiveTransitions = transitions.filter((tr) =>
    isArchiveTransition(tr.target_state),
  );

  return (
    <article data-testid="goal-detail">
      {/* Trace spine (Task 3.3). Trace links are shown here and deliberately
          NOT again in the inspector sidebar (`hideTraceLinks`). */}
      <TraceSpine
        stations={derivationChain.stations}
        isLoading={derivationChain.isLoading}
        error={derivationChain.error}
        onOpenArtifact={handleOpenChainArtifact}
        isOpenable={derivationChain.isOpenable}
      />

      {/* 1. Identity — ch. 12.4, same order and representation as the tree. */}
      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          alignItems: "center",
          gap: "var(--space-2)",
          marginBottom: "var(--space-3)",
        }}
      >
        <ArtifactId
          testId="goal-artifact-id"
          // A Goal has no semantic uid; the lineage prefix is the stable
          // handle that survives across all versions of one goal.
          fallback={goal.lineage_id.slice(0, 8)}
          copyValue={goal.lineage_id}
        />
        <StatusBadge status={goal.status} testId="goal-status" />
        <VersionBadge version={goal.sequence_number} />
      </div>

      {/* 2. Title + description */}
      <h2
        data-testid="goal-detail-title"
        style={{
          margin: "0 0 var(--space-2)",
          fontSize: "var(--font-size-xl)",
          lineHeight: "var(--leading-tight)",
          letterSpacing: "var(--tracking-tight)",
          fontWeight: "var(--weight-semibold)",
          color: "var(--color-text)",
        }}
      >
        {goal.title}
      </h2>

      <p
        data-testid="goal-detail-description"
        style={{
          margin: "0 0 var(--space-4)",
          maxWidth: "var(--measure)",
          fontSize: "var(--font-size-base)",
          lineHeight: "var(--leading-relaxed)",
          color: goal.description
            ? "var(--color-text)"
            : "var(--color-text-muted)",
          whiteSpace: "pre-wrap",
        }}
      >
        {goal.description || t("goals.noDescription", "Keine Beschreibung.")}
      </p>

      {/* 3. Actions */}
      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          gap: "var(--space-2)",
          marginBottom: "var(--space-5)",
        }}
      >
        <button
          type="button"
          className="btn-secondary"
          data-testid="goal-edit-button"
          onClick={() => onEdit(goal)}
        >
          {t("goals.edit", "Bearbeiten")}
        </button>
        {lifecycleTransitions.map((transition, index) => (
          <button
            key={transition.target_state}
            type="button"
            // The first available move is the primary one; a customised
            // workflow may offer several (e.g. approve / rework).
            className={index === 0 ? "btn-primary" : "btn-secondary"}
            data-testid={`goal-transition-${transition.target_state}`}
            onClick={() => onTransition(goal, transition)}
          >
            {/* Label comes from the target state, with a translation only
                for the states the stock `goal_default` preset ships. Any
                custom state falls back to its own name, which is still
                better than a wrong hardcoded label. */}
            {t(`goals.transition.${transition.target_state}`, {
              defaultValue: transition.target_state,
            })}
          </button>
        ))}
        {archiveTransitions.map((transition) => (
          <button
            key={transition.target_state}
            type="button"
            className="btn-danger"
            data-testid={`goal-transition-${transition.target_state}`}
            onClick={() => onTransition(goal, transition)}
          >
            {t(`goals.transition.${transition.target_state}`, {
              defaultValue: transition.target_state,
            })}
          </button>
        ))}
      </div>

      {/* 4. Workspace-defined attributes — ch. 12.11. Renders nothing when
             the workspace defines no fields. */}
      {goal.artifact_id && (
        <div data-testid="goal-custom-fields" style={{ marginBottom: "var(--space-5)" }}>
          <ArtifactCustomFields artifactId={goal.artifact_id} />
        </div>
      )}
    </article>
  );
}

GoalDetail.displayName = "GoalDetail";
