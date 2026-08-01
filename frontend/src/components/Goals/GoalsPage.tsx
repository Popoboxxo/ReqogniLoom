/**
 * ARCH-L1-001 ReactFrontend — GoalsPage (REQ-L2-TE-020).
 *
 * Page-level wrapper composing MainGoalPanel (approved main goal + AI draft)
 * and GoalsPanel (list/create of individual goals) for the active workspace.
 * Route: /goals (only reachable when the workspace's `goals_enabled` toggle
 * is on — gated in SidebarNavigation, see NAV_ITEMS).
 *
 * UI concept ch. 12.1: the route now owns exactly one <h1> via <PageHeader>,
 * the summary is always visible (not only under an active filter) and the
 * single primary action lives top right. The previous bare <h2> is gone.
 */

import { useCallback, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useWorkspace } from "../../context/WorkspaceContext";
import { PageHeader } from "../shared/PageHeader";
import { GoalsPanel } from "./GoalsPanel";
import { MainGoalPanel } from "./MainGoalPanel";
import type { Goal } from "../../types";

const APPROVED_STATE = "Freigegeben";

export default function GoalsPage(): JSX.Element {
  const { t } = useTranslation();
  const { activeWorkspace, isLoadingWorkspace } = useWorkspace();
  const [goals, setGoals] = useState<Goal[]>([]);
  const [isFormOpen, setIsFormOpen] = useState(false);

  // Stable identity — GoalsPanel calls this from an effect keyed on the
  // callback, so an inline arrow would re-run it on every render.
  const handleGoalsChange = useCallback((next: Goal[]) => setGoals(next), []);

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

  if (isLoadingWorkspace || !activeWorkspace) {
    return (
      <p role="status" style={{ padding: "var(--space-8)", color: "var(--color-text-muted)" }}>
        {t("loading", "Laden...")}
      </p>
    );
  }

  return (
    <div data-testid="goals-page" style={{ padding: "var(--space-4)" }}>
      <PageHeader
        title={t("goals.title", "Ziele")}
        summary={summary}
        primaryAction={{
          label: t("goals.newGoal", "Neues Ziel"),
          onClick: () => setIsFormOpen(true),
          disabled: isFormOpen,
          testId: "create-goal-btn",
        }}
      />
      <section style={{ marginBottom: "var(--space-6)" }}>
        <MainGoalPanel
          workspaceId={activeWorkspace.id}
          aiEnabled={!!activeWorkspace.goals_ai_enabled}
        />
      </section>
      <section>
        <GoalsPanel
          workspaceId={activeWorkspace.id}
          isFormOpen={isFormOpen}
          onFormOpenChange={setIsFormOpen}
          onGoalsChange={handleGoalsChange}
        />
      </section>
    </div>
  );
}
