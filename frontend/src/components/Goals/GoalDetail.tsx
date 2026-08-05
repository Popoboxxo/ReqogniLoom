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
 *                      customise its Goal state machine, ADR-06)
 *   4. workspace-defined attributes via <ArtifactCustomFields> (ch. 12.11)
 *   5. the version list of the lineage (GET /goals/{id}/versions/)
 *
 * Mutations are delegated upwards: the page owns the API calls so that a
 * rejected action surfaces in exactly one place (ch. 12.12).
 */

import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { extractErrorMessage } from "../../api/client";
import { goalsApi } from "../../api/goals";
import { ArtifactCustomFields } from "../shared/ArtifactCustomFields";
import { ArtifactId } from "../shared/ArtifactId";
import { StatusBadge } from "../shared/StatusBadge";
import { VersionBadge } from "../shared/VersionBadge";
import { TraceSpine, useDerivationChain } from "../shared/TraceSpine";
import type { ChainArtifact } from "../shared/TraceSpine";
import { getArtifactRoute } from "../../utils/artifactRoutes";
import type { WorkflowAllowedTransition } from "../../api/workflow-transitions";
import type { ArtifactVersion, Goal } from "../../types";

export interface GoalDetailProps {
  goal: Goal;
  onEdit: (goal: Goal) => void;
  /**
   * Perform one of the moves the WorkflowEngine currently allows. The whole
   * transition descriptor is handed over (not just the target state) so the
   * page can honour `requires_change_reason` without re-deriving it.
   */
  onTransition: (goal: Goal, transition: WorkflowAllowedTransition) => void;
}

const sectionLabelStyle: React.CSSProperties = {
  display: "block",
  margin: "0 0 var(--space-2)",
  fontSize: "var(--font-size-sm)",
  fontWeight: "var(--weight-semibold)",
  color: "var(--color-text)",
};

export function GoalDetail({ goal, onEdit, onTransition }: GoalDetailProps): JSX.Element {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [versions, setVersions] = useState<ArtifactVersion[]>([]);
  const [versionsError, setVersionsError] = useState<string | null>(null);
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

  useEffect(() => {
    let cancelled = false;
    setVersionsError(null);
    void (async () => {
      try {
        const list = await goalsApi.versions(goal.id);
        if (cancelled) return;
        // The endpoint may be unavailable on older backends and is
        // auto-mocked away in unit tests — never let a non-array through.
        setVersions(Array.isArray(list) ? list : []);
      } catch (err) {
        if (cancelled) return;
        setVersions([]);
        setVersionsError(extractErrorMessage(err));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [goal.id]);

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
        // detail pane rather than an error banner — the versions list and
        // the edit action stay usable (WorkflowStatusEditor does the same).
        if (!cancelled) setTransitions([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [goal.id, goal.status]);

  return (
    <article data-testid="goal-detail">
      {/* Trace spine (Task 3.3). Goals has no RightSidebar today, so there is
          no trace-link duplication to remove here — this is a pure addition. */}
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
        {transitions.map((transition, index) => (
          <button
            key={transition.target_state}
            type="button"
            // The first available move is the primary one; a customised
            // workflow may offer several (e.g. approve / archive).
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
      </div>

      {/* 4. Workspace-defined attributes — ch. 12.11. Renders nothing when
             the workspace defines no fields. */}
      {goal.artifact_id && (
        <div data-testid="goal-custom-fields" style={{ marginBottom: "var(--space-5)" }}>
          <ArtifactCustomFields artifactId={goal.artifact_id} />
        </div>
      )}

      {/* 5. Versions of this lineage. An "edit" appends a row here rather
             than overwriting the current one (design spec 2.3). */}
      <section data-testid="goal-versions">
        <h3 style={sectionLabelStyle}>{t("goals.versions", "Versionen")}</h3>
        {versionsError ? (
          <p
            role="alert"
            data-testid="goal-versions-error"
            style={{
              margin: 0,
              color: "var(--color-danger)",
              fontSize: "var(--font-size-sm)",
            }}
          >
            {versionsError}
          </p>
        ) : versions.length === 0 ? (
          <p
            style={{
              margin: 0,
              color: "var(--color-text-muted)",
              fontSize: "var(--font-size-sm)",
            }}
          >
            {t("goals.versionsNone", "Nur die aktuelle Version.")}
          </p>
        ) : (
          <ol
            style={{
              listStyle: "none",
              margin: 0,
              padding: 0,
              display: "flex",
              flexDirection: "column",
              gap: "var(--space-1)",
            }}
          >
            {versions.map((v) => (
              <li
                key={v.version}
                data-testid="goal-version-row"
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "var(--space-2)",
                  fontSize: "var(--font-size-sm)",
                  color: "var(--color-text-muted)",
                }}
              >
                <VersionBadge
                  version={v.version}
                  isCurrent={v.version === goal.sequence_number}
                />
                <span>{v.label}</span>
                {v.modified_at && (
                  <span style={{ fontVariantNumeric: "tabular-nums" }}>
                    {new Date(v.modified_at).toLocaleString()}
                  </span>
                )}
              </li>
            ))}
          </ol>
        )}
      </section>
    </article>
  );
}

GoalDetail.displayName = "GoalDetail";
