/**
 * ARCH-L1-001 ReactFrontend — GoalsPage (REQ-L2-TE-020).
 *
 * Route: /goals (only reachable when the workspace's `goals_enabled` toggle
 * is on — gated in SidebarNavigation, see NAV_ITEMS).
 *
 * UI concept ch. 6 / 12.6: the route is a split view, not a stack of panels.
 * It previously piled PageHeader + MainGoalPanel + a flat <ul> on top of
 * each other, which left the two things the concept insists on missing
 * entirely — a tree to navigate by and a detail pane to work in.
 *
 * Layout now:
 *   PageHeader (one <h1>, always-visible summary, one primary action)
 *   SplitView
 *     left  — <GoalsTree>: "Haupt-Ziel" and "Ziele" as the two roots
 *     right — <MainGoalPanel> | <GoalDetail> | <GoalForm>
 *
 * The page owns all Goal mutations so that a rejected create / edit /
 * approval surfaces in exactly one alert (ch. 12.12) instead of three.
 * MainGoal keeps its own state inside <MainGoalPanel>: AI generation,
 * manual authoring and release are a self-contained flow on a different
 * artifact type and are only re-seated here, not rewritten.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { extractErrorMessage } from "../../api/client";
import { goalsApi } from "../../api/goals";
import { useWorkspace } from "../../context/WorkspaceContext";
import { PageHeader } from "../shared/PageHeader";
import { SplitView } from "../SplitView/SplitView";
import { APPROVED_STATE, GoalDetail } from "./GoalDetail";
import { GoalForm } from "./GoalForm";
import { GOALS_ROOT_NODE_ID, GoalsTree, MAIN_GOAL_NODE_ID } from "./GoalsTree";
import { MainGoalPanel } from "./MainGoalPanel";
import type { Goal } from "../../types";

/** Create/edit form state. `null` = no form, `{ editing: null }` = create. */
interface FormState {
  editing: Goal | null;
}

export default function GoalsPage(): JSX.Element {
  const { t } = useTranslation();
  const { activeWorkspace, isLoadingWorkspace } = useWorkspace();
  const workspaceId = activeWorkspace?.id;

  const [goals, setGoals] = useState<Goal[]>([]);
  const [error, setError] = useState<string | null>(null);
  // ch. 13.5: never show an empty detail pane — the main goal is the anchor
  // of this route, so it is what an arriving user sees.
  const [selectedId, setSelectedId] = useState<string>(MAIN_GOAL_NODE_ID);
  const [form, setForm] = useState<FormState | null>(null);

  const loadGoals = useCallback(async (): Promise<void> => {
    if (!workspaceId) return;
    try {
      const list = await goalsApi.list(workspaceId);
      setGoals(Array.isArray(list) ? list : []);
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

  const summary = useMemo(() => {
    const approved = goals.filter((g) => g.status === APPROVED_STATE).length;
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
    setForm(null);
    setError(null);
    setSelectedId(id);
  }, []);

  const handleSubmit = useCallback(
    async (values: { title: string; description: string }): Promise<void> => {
      if (!workspaceId) return;
      setError(null);
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
        // ch. 12.12: a failed action keeps the form open and states the cause.
        setError(extractErrorMessage(err));
      }
    },
    [form, loadGoals, workspaceId],
  );

  const handleApprove = useCallback(
    async (goal: Goal): Promise<void> => {
      setError(null);
      try {
        await goalsApi.transition(goal.id, APPROVED_STATE, "Ziel freigegeben.");
        await loadGoals();
      } catch (err) {
        setError(extractErrorMessage(err));
      }
    },
    [loadGoals],
  );

  const handleEdit = useCallback((goal: Goal): void => {
    setError(null);
    setSelectedId(goal.id);
    setForm({ editing: goal });
  }, []);

  if (isLoadingWorkspace || !activeWorkspace) {
    return (
      <p role="status" style={{ padding: "var(--space-8)", color: "var(--color-text-muted)" }}>
        {t("loading", "Laden...")}
      </p>
    );
  }

  const detailPane = (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
      {error && (
        <p
          data-testid="goals-error"
          role="alert"
          style={{
            margin: 0,
            color: "var(--color-danger)",
            fontSize: "var(--font-size-sm)",
          }}
        >
          {error}
        </p>
      )}

      {form ? (
        <GoalForm
          editing={form.editing}
          onSubmit={(values) => void handleSubmit(values)}
          onCancel={() => {
            setError(null);
            setForm(null);
          }}
        />
      ) : selectedId === MAIN_GOAL_NODE_ID ? (
        <MainGoalPanel
          workspaceId={activeWorkspace.id}
          aiEnabled={!!activeWorkspace.goals_ai_enabled}
        />
      ) : selectedGoal ? (
        <GoalDetail
          goal={selectedGoal}
          onEdit={handleEdit}
          onApprove={(goal) => void handleApprove(goal)}
        />
      ) : null}
    </div>
  );

  return (
    <div
      data-testid="goals-page"
      style={{ display: "flex", flexDirection: "column", height: "100%", minHeight: 0 }}
    >
      <PageHeader
        title={t("goals.title", "Ziele")}
        summary={summary}
        primaryAction={{
          label: t("goals.newGoal", "Neues Ziel"),
          onClick: () => {
            setError(null);
            setForm({ editing: null });
          },
          disabled: Boolean(form),
          testId: "create-goal-btn",
        }}
      />
      {/* SplitView sizes itself to 100% of its box; the shell's <main> has no
          resolved height, so the pane needs a floor of its own. */}
      <div style={{ flex: "1 1 auto", minHeight: "60vh" }}>
        <SplitView
          moduleType="goals"
          initialLeftWidth={350}
          leftPanel={
            <GoalsTree goals={goals} selectedId={selectedId} onSelect={handleSelect} />
          }
          rightPanel={detailPane}
        />
      </div>
    </div>
  );
}
