/**
 * ARCH-L1-001 ReactFrontend — GoalsPage (REQ-L2-TE-020).
 *
 * Route: /goals (only reachable when the workspace's `goals_enabled` toggle
 * is on — gated in SidebarNavigation, see NAV_ITEMS).
 *
 * UI concept ch. 6 / 12.6: the route is a split view, not a stack of panels.
 *
 * Layout:
 *   PageHeader (one <h1>, always-visible summary, one primary action)
 *   SplitView
 *     left  — <GoalsTree>: "Haupt-Ziel" and "Ziele" as the two roots,
 *              with ListToolbar search/status-filter/sort above them
 *     right — <MainGoalPanel> | <GoalDetail>, with the shared
 *              <ArtifactInspector> sidebar beside it
 *   <GoalFormDialog>        — create / edit, modal (issue #238)
 *   <ArchiveConfirmDialog>  — the archive move (issue #238)
 *
 * Issue #238 brought the route onto the same shape every other artifact route
 * has: creation happens in a modal instead of inside the detail pane, the
 * archive move is confirmed and danger-styled instead of sitting unlabelled
 * among the lifecycle buttons, and the list rows/empty states are the shared
 * <ArtifactRow>/<EmptyState> primitives (see GoalsTree).
 *
 * Issue #219: the `<ArtifactInspector>` sidebar is mounted here for both
 * artifact types of this route — `kind="goal"` next to a selected Goal and
 * `kind="mainGoal"` next to the main goal panel. Its VersionPanel is what
 * finally makes Goal/MainGoal version history reachable; the wiring
 * (VERSION_SUPPORTED_KINDS / VERSIONS_FETCHERS) had existed but no component
 * rendered the sidebar. Trace links stay hidden there: <GoalDetail> already
 * shows them through <TraceSpine>, and MainGoal has no artifact-level trace
 * links at all (no `artifact_id` on the type).
 *
 * The page owns all Goal mutations so that a rejected create / edit /
 * transition surfaces in exactly one place (ch. 12.12) — inside the dialog
 * while one is open, in the detail pane otherwise. MainGoal keeps its own
 * state inside <MainGoalPanel>: AI generation, manual authoring, release and
 * archiving are a self-contained flow on a different artifact type.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { extractErrorMessage } from "../../api/client";
import { goalsApi } from "../../api/goals";
import { useWorkspace } from "../../context/WorkspaceContext";
import { PageHeader } from "../shared/PageHeader";
import { RightSidebar } from "../shared/ArtifactInspector";
import type { VersionRef } from "../shared/ArtifactInspector";
import { SplitView } from "../SplitView/SplitView";
import { resolveBadgeVariant } from "../../utils/statusBadge";
import { ArchiveConfirmDialog } from "./ArchiveConfirmDialog";
import { GoalDetail } from "./GoalDetail";
import { GoalFormDialog } from "./GoalFormDialog";
import type { GoalFormValues } from "./GoalFormDialog";
import { isArchiveTransition } from "./goal-workflow";
import { GOALS_ROOT_NODE_ID, GoalsTree, MAIN_GOAL_NODE_ID } from "./GoalsTree";
import { MainGoalPanel } from "./MainGoalPanel";
import type { WorkflowAllowedTransition } from "../../api/workflow-transitions";
import type { Goal, MainGoal } from "../../types";
import styles from "./Goals.module.css";

/** Create/edit form state. `null` = no dialog, `{ editing: null }` = create. */
interface FormState {
  editing: Goal | null;
}

/** A confirmed-before-it-runs transition (currently only the archive move). */
interface PendingTransition {
  goal: Goal;
  transition: WorkflowAllowedTransition;
}

export default function GoalsPage(): JSX.Element {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { activeWorkspace, isLoadingWorkspace } = useWorkspace();
  const workspaceId = activeWorkspace?.id;

  const [goals, setGoals] = useState<Goal[]>([]);
  const [error, setError] = useState<string | null>(null);
  // ch. 13.5: never show an empty detail pane — the main goal is the anchor
  // of this route, so it is what an arriving user sees.
  const [selectedId, setSelectedId] = useState<string>(MAIN_GOAL_NODE_ID);
  const [form, setForm] = useState<FormState | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [pendingArchive, setPendingArchive] = useState<PendingTransition | null>(null);
  // Issue #219: the MainGoal the panel currently shows, so the inspector can
  // be mounted beside it. Reported upwards because the inspector is a sibling
  // of the whole detail column, not of the panel card.
  const [activeMainGoal, setActiveMainGoal] = useState<MainGoal | null>(null);

  const loadGoals = useCallback(async (): Promise<void> => {
    if (!workspaceId) return;
    try {
      const list = await goalsApi.list(workspaceId);
      setGoals(Array.isArray(list) ? list : []);
      // Issue #221 finding 7: every caller of loadGoals happened to clear
      // `error` itself before calling it (handleSelect, runTransition, ...),
      // but loadGoals is also the effect that re-fetches on a bare
      // `workspaceId` change (workspace switch) — a stale error from the
      // previous workspace stayed on screen there even though the new
      // workspace's list loaded fine. A successful load must clear it here,
      // not rely on every future caller remembering to.
      setError(null);
    } catch (err) {
      setError(extractErrorMessage(err));
    }
  }, [workspaceId]);

  useEffect(() => {
    void loadGoals();
  }, [loadGoals]);

  const selectedGoal = useMemo(
    () => goals.find((g) => g.id === selectedId) ?? null,
    [goals, selectedId],
  );

  // Defensive fix (issue #238 review finding 3): fall back to the main-goal
  // anchor whenever the selected Goal is missing from a freshly loaded list,
  // regardless of which state it moved into. Previously this only ran for
  // moves classified as "archive" (`isArchiveTransition`), which depends on
  // `resolveBadgeVariant` recognising the target state's warning family — an
  // unrecognised/custom state that still drops the row from
  // `GoalService.list_current()` used to leave the detail pane silently
  // empty (not the empty state, nothing) instead of falling back (ch. 13.5).
  useEffect(() => {
    if (selectedId === MAIN_GOAL_NODE_ID) return;
    if (!goals.some((g) => g.id === selectedId)) {
      setSelectedId(MAIN_GOAL_NODE_ID);
    }
  }, [goals, selectedId]);

  const summary = useMemo(() => {
    // Issue #220: no hardcoded state name here either. `resolveBadgeVariant`
    // is the codebase's shared status-semantics classifier (ch. 8.2) —
    // "success" is the family of done/approved/released states across every
    // artifact type and both locales, so a workspace that renamed its
    // approved state still gets a truthful count instead of a constant 0.
    const approved = goals.filter(
      (g) => resolveBadgeVariant(g.status) === "success",
    ).length;
    return [
      t("goals.summary", { count: goals.length, defaultValue: `${goals.length} Ziele` }),
      t("goals.approvedSuffix", {
        count: approved,
        defaultValue: `${approved} freigegeben`,
      }),
    ].join(" · ");
  }, [goals, t]);

  const handleSelect = useCallback((id: string): void => {
    // The "Ziele" node is a grouping row, not an artifact — clicking it only
    // ever expands/collapses (the caret handles that itself).
    if (id === GOALS_ROOT_NODE_ID) return;
    setError(null);
    setSelectedId(id);
  }, []);

  const openCreateDialog = useCallback((): void => {
    setError(null);
    setForm({ editing: null });
  }, []);

  const closeFormDialog = useCallback((): void => {
    setError(null);
    setForm(null);
  }, []);

  const handleSubmit = useCallback(
    async (values: GoalFormValues): Promise<void> => {
      if (!workspaceId) return;
      setError(null);
      setIsSubmitting(true);
      const editing = form?.editing ?? null;
      try {
        if (editing) {
          // Immutable-row-per-version: an "edit" inserts into the same
          // lineage, starting again at `Entwurf`.
          const created = await goalsApi.createVersion(editing.lineage_id, {
            workspace_id: workspaceId,
            title: values.title,
            description: values.description,
          });
          await loadGoals();
          if (created?.id) setSelectedId(created.id);
        } else {
          const created = await goalsApi.create(workspaceId, values);
          setGoals((prev) => (created ? [...prev, created] : prev));
          if (created?.id) setSelectedId(created.id);
        }
        setForm(null);
      } catch (err) {
        // ch. 12.12: a failed action keeps the dialog open and states the
        // cause inside it, where the action was triggered.
        setError(extractErrorMessage(err));
      } finally {
        setIsSubmitting(false);
      }
    },
    [form, loadGoals, workspaceId],
  );

  const runTransition = useCallback(
    async (goal: Goal, transition: WorkflowAllowedTransition): Promise<void> => {
      setError(null);
      setIsSubmitting(true);
      try {
        // The WorkflowEngine rejects an empty reason where the transition
        // demands one (`requires_change_reason`), so send a canned one for
        // exactly those moves rather than for every move.
        //
        // Issue #221 finding 1 (scope boundary): this is a computed string,
        // not a real user-entered audit reason — it undermines the intent of
        // the change-reason gate for every non-archive transition. A real
        // fix would prompt for a reason the same way `ArchiveConfirmDialog`
        // confirms the archive move, but that dialog (see ArchiveConfirmDialog
        // .tsx) has no reason textarea to reuse today — it only confirms with
        // a static body text. Adding one, and wiring a reason prompt into
        // every `requires_change_reason` transition (here and in
        // MainGoalPanel.handleArchive), is a state-management change across
        // two components, not a one-line fix — out of scope for this polish
        // pass. Kept minimal-invasive: the fallback text below explicitly
        // reads as a mechanical status description ("Statuswechsel nach
        // X"), not as a human-authored justification, so an auditor reading
        // the change_reason later is not misled into thinking a person
        // typed it.
        const changeReason = transition.requires_change_reason
          ? t("goals.transitionReason", {
              state: transition.target_state,
              defaultValue: `Statuswechsel nach ${transition.target_state}.`,
            })
          : "";
        await goalsApi.transition(goal.id, transition.target_state, changeReason);
        // A goal dropped from `GoalService.list_current()` by this move (the
        // archive move today, potentially other states in a customised
        // workflow tomorrow) leaves the selection dangling — the defensive
        // effect above resets it to the route's anchor once `goals` reloads.
        await loadGoals();
      } catch (err) {
        setError(extractErrorMessage(err));
      } finally {
        setIsSubmitting(false);
      }
    },
    [loadGoals, t],
  );

  const handleTransition = useCallback(
    (goal: Goal, transition: WorkflowAllowedTransition): void => {
      // Archiving removes the goal from the list, so it is confirmed first;
      // every other move is immediate and reversible through the workflow.
      if (isArchiveTransition(transition.target_state)) {
        setError(null);
        setPendingArchive({ goal, transition });
        return;
      }
      void runTransition(goal, transition);
    },
    [runTransition],
  );

  const confirmArchive = useCallback((): void => {
    if (!pendingArchive) return;
    const { goal, transition } = pendingArchive;
    setPendingArchive(null);
    void runTransition(goal, transition);
  }, [pendingArchive, runTransition]);

  const handleEdit = useCallback((goal: Goal): void => {
    setError(null);
    setSelectedId(goal.id);
    setForm({ editing: goal });
  }, []);

  if (isLoadingWorkspace || !activeWorkspace) {
    return (
      <p role="status" className={styles.loading}>
        {t("loading", "Laden...")}
      </p>
    );
  }

  const isMainGoalSelected = selectedId === MAIN_GOAL_NODE_ID;

  /**
   * Subject of the inspector sidebar (issue #219). Both kinds resolve their
   * version list from the *entity* id: `GET /goals/{id}/versions/` looks the
   * lineage up from the row, `GET /main-goals/{id}/versions/` the workspace
   * chain — neither takes an `artifact_id`.
   */
  const inspector: {
    kind: "goal" | "mainGoal";
    artifactId: string;
    version: VersionRef;
  } | null = isMainGoalSelected
    ? activeMainGoal
      ? {
          kind: "mainGoal",
          artifactId: activeMainGoal.id,
          version: {
            version: activeMainGoal.sequence_number,
            label: `v${activeMainGoal.sequence_number}`,
            createdAt: activeMainGoal.created_at ?? null,
            baselineIds: [],
          },
        }
      : null
    : selectedGoal
      ? {
          kind: "goal",
          artifactId: selectedGoal.id,
          version: {
            version: selectedGoal.sequence_number,
            label: `v${selectedGoal.sequence_number}`,
            createdAt: selectedGoal.created_at ?? null,
            baselineIds: [],
          },
        }
      : null;

  const detailPane = (
    <div className={styles.detailPane}>
      <div className={styles.detailColumn}>
        {error && !form && (
          <p data-testid="goals-error" role="alert" className={styles.error}>
            {error}
          </p>
        )}

        {isMainGoalSelected ? (
          <MainGoalPanel
            workspaceId={activeWorkspace.id}
            aiEnabled={!!activeWorkspace.goals_ai_enabled}
            onActiveChange={setActiveMainGoal}
          />
        ) : selectedGoal ? (
          <GoalDetail
            goal={selectedGoal}
            onEdit={handleEdit}
            onTransition={handleTransition}
          />
        ) : null}
      </div>

      {inspector && (
        <RightSidebar
          kind={inspector.kind}
          artifactId={inspector.artifactId}
          currentVersion={inspector.version}
          hideTraceLinks
        />
      )}
    </div>
  );

  return (
    <div data-testid="goals-page" className={styles.pageRoot}>
      <PageHeader
        title={t("goals.title", "Ziele")}
        summary={summary}
        primaryAction={{
          label: t("goals.newGoal", "Neues Ziel"),
          onClick: openCreateDialog,
          disabled: Boolean(form),
          testId: "create-goal-btn",
        }}
        secondaryActions={[
          {
            label: t("interviews.startCta"),
            onClick: () => navigate("/interviews?start=Goal"),
            disabled: !activeWorkspace,
            testId: "interview-start-cta",
          },
        ]}
      />
      <div className={styles.splitHost}>
        <SplitView
          moduleType="goals"
          initialLeftWidth={350}
          leftPanel={
            <GoalsTree
              goals={goals}
              selectedId={selectedId}
              onSelect={handleSelect}
              workspaceId={workspaceId}
              onCreateNew={openCreateDialog}
            />
          }
          rightPanel={detailPane}
        />
      </div>

      {form && (
        <GoalFormDialog
          editing={form.editing}
          error={error}
          isSubmitting={isSubmitting}
          onSubmit={(values) => void handleSubmit(values)}
          onClose={closeFormDialog}
        />
      )}

      {pendingArchive && (
        <ArchiveConfirmDialog
          testId="goal-archive-dialog"
          itemLabel={pendingArchive.goal.title || t("goals.untitled", "Ohne Titel")}
          confirmLabel={t(
            `goals.transition.${pendingArchive.transition.target_state}`,
            { defaultValue: pendingArchive.transition.target_state },
          )}
          isSubmitting={isSubmitting}
          onConfirm={confirmArchive}
          onCancel={() => setPendingArchive(null)}
        />
      )}
    </div>
  );
}
