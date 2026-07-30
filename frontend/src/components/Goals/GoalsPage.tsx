/**
 * ARCH-L1-001 ReactFrontend — GoalsPage (REQ-L2-TE-020).
 *
 * Page-level wrapper composing MainGoalPanel (approved main goal + AI draft)
 * and GoalsPanel (list/create of individual goals) for the active workspace.
 * Route: /goals (only reachable when the workspace's `goals_enabled` toggle
 * is on — gated in SidebarNavigation, see NAV_ITEMS).
 */

import { useTranslation } from "react-i18next";
import { useWorkspace } from "../../context/WorkspaceContext";
import { GoalsPanel } from "./GoalsPanel";
import { MainGoalPanel } from "./MainGoalPanel";

export default function GoalsPage(): JSX.Element {
  const { t } = useTranslation();
  const { activeWorkspace, isLoadingWorkspace } = useWorkspace();

  if (isLoadingWorkspace || !activeWorkspace) {
    return (
      <p role="status" style={{ padding: "var(--space-8)", color: "var(--color-text-muted)" }}>
        {t("loading", "Laden...")}
      </p>
    );
  }

  return (
    <div data-testid="goals-page">
      <h2 style={{ marginBottom: "var(--space-4)" }}>{t("nav.goals", "Ziele")}</h2>
      <section style={{ marginBottom: "var(--space-6)" }}>
        <MainGoalPanel
          workspaceId={activeWorkspace.id}
          aiEnabled={!!activeWorkspace.goals_ai_enabled}
        />
      </section>
      <section>
        <GoalsPanel workspaceId={activeWorkspace.id} />
      </section>
    </div>
  );
}
