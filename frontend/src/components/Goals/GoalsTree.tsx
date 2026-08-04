/**
 * ARCH-L1-001 ReactFrontend — GoalsTree (REQ-L2-TE-020).
 *
 * Left-hand navigation of the Goals route (UI concept ch. 12.2 / 12.5 /
 * 12.6). Replaces the flat <ul> the page used to stack below the main goal
 * panel: the route now has exactly one navigation primitive, and it is the
 * shared `WorkspaceTree`.
 *
 * Two roots, because the route holds two different artifact types:
 *   - "Haupt-Ziel"  — the single workspace-scoped MainGoal chain
 *   - "Ziele"       — the Goal lineages, one child node per lineage
 *
 * Search / status filter / sort stay in `ListToolbar` and are applied here;
 * the tree receives the already-filtered node list, exactly as `NeedList`
 * does. `WorkspaceTree`'s own search box is therefore switched off.
 */

import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { ListToolbar } from "../shared/ListToolbar";
import { WorkspaceTree } from "../shared/WorkspaceTree";
import type { WorkspaceTreeNode } from "../shared/WorkspaceTree";
import { getStatusBadgeStyle } from "../../utils/statusBadge";
import { workflowsApi } from "../../api/workflows";
import type { Goal } from "../../types";

/** Node id of the MainGoal root — not a real artifact id. */
export const MAIN_GOAL_NODE_ID = "__main-goal__";
/** Node id of the Goals root — not a real artifact id. */
export const GOALS_ROOT_NODE_ID = "__goals__";

/**
 * Fallback shown until the workspace's real Goal workflow states have
 * loaded (backend/workflow/services.py `_ENTITY_DEFAULT_PRESET["Goal"]` =
 * `goal_default`). Only used transiently — `GoalsTree` replaces this with
 * the live, workspace-configured state list from `workflowsApi.getGraph`
 * (issue #333) as soon as it resolves.
 */
const DEFAULT_GOAL_STATES = ["Entwurf", "Freigegeben", "Archiviert"];

type GoalSortKey = "default" | "title" | "status";

function sortGoals(list: Goal[], sortKey: GoalSortKey, states: string[]): Goal[] {
  const sorted = [...list];
  switch (sortKey) {
    case "title":
      sorted.sort((a, b) => a.title.localeCompare(b.title));
      break;
    case "status":
      sorted.sort((a, b) => {
        const ai = states.indexOf(a.status);
        const bi = states.indexOf(b.status);
        return (
          (ai === -1 ? states.length : ai) - (bi === -1 ? states.length : bi) ||
          a.title.localeCompare(b.title)
        );
      });
      break;
    default:
      break;
  }
  return sorted;
}

export interface GoalsTreeProps {
  goals: Goal[];
  /** `MAIN_GOAL_NODE_ID` or a Goal id. */
  selectedId: string;
  onSelect: (id: string) => void;
  /** Workspace scope for the live Goal workflow-states lookup (issue #333). */
  workspaceId?: string;
}

export function GoalsTree({
  goals,
  selectedId,
  onSelect,
  workspaceId,
}: GoalsTreeProps): JSX.Element {
  const { t } = useTranslation();
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [sortKey, setSortKey] = useState<GoalSortKey>("default");
  // REQ-003/issue #333 — the filter/sort order must reflect the workspace's
  // actually configured Goal states, not a hardcoded snapshot of the
  // `goal_default` preset. Same live-lookup pattern the Workflow Editor uses
  // (`workflowsApi.getGraph`); falls back to the default preset's states
  // while the request is in flight or the workspace is not yet known.
  const [goalStates, setGoalStates] = useState<string[]>(DEFAULT_GOAL_STATES);

  useEffect(() => {
    if (!workspaceId) return;
    let cancelled = false;
    workflowsApi
      .getGraph("Goal", workspaceId)
      .then((graph) => {
        if (cancelled) return;
        const names = graph.states.map((s) => s.name);
        if (names.length > 0) setGoalStates(names);
      })
      .catch(() => {
        // Keep the default-preset fallback — a failed lookup should not
        // break the filter/sort dropdown.
      });
    return () => {
      cancelled = true;
    };
  }, [workspaceId]);

  const visibleGoals = useMemo(() => {
    const q = search.trim().toLowerCase();
    const filtered = goals.filter((g) => {
      if (statusFilter && g.status !== statusFilter) return false;
      if (!q) return true;
      return (
        g.title.toLowerCase().includes(q) ||
        (g.description ?? "").toLowerCase().includes(q)
      );
    });
    return sortGoals(filtered, sortKey, goalStates);
  }, [goals, search, statusFilter, sortKey, goalStates]);

  const nodes = useMemo((): WorkspaceTreeNode[] => {
    const roots: WorkspaceTreeNode[] = [
      {
        id: MAIN_GOAL_NODE_ID,
        name: t("goals.mainGoal", "Haupt-Ziel"),
        parentId: null,
      },
      {
        id: GOALS_ROOT_NODE_ID,
        name: t("goals.title", "Ziele"),
        parentId: null,
      },
    ];
    const children = visibleGoals.map((g): WorkspaceTreeNode => {
      const style = getStatusBadgeStyle(g.status);
      return {
        id: g.id,
        name: g.title || t("goals.untitled", "Ohne Titel"),
        parentId: GOALS_ROOT_NODE_ID,
        badge: {
          text: g.status,
          bg: style.background as string,
          color: style.color as string,
        },
      };
    });
    return [...roots, ...children];
  }, [visibleGoals, t]);

  const hasActiveControls = Boolean(search || statusFilter);

  return (
    <div data-testid="goals-tree-panel">
      <ListToolbar
        testIdPrefix="goal-list"
        searchValue={search}
        onSearchChange={setSearch}
        searchPlaceholder={t("editor.searchPlaceholder", "Suchen...")}
        filters={[
          {
            id: "status",
            allLabel: t("editor.allStatuses", "Alle Status"),
            value: statusFilter,
            options: goalStates.map((s) => ({ value: s, label: s })),
            onChange: setStatusFilter,
          },
        ]}
        sortValue={sortKey}
        sortOptions={[
          { value: "default", label: t("editor.sortDefault", "Standardreihenfolge") },
          { value: "title", label: t("editor.sortTitleAsc", "Titel (A-Z)") },
          { value: "status", label: t("editor.sortStatus", "Status") },
        ]}
        onSortChange={(value) => setSortKey(value as GoalSortKey)}
        sortLabel={t("editor.sortLabel", "Sortieren nach")}
        countLabel={
          hasActiveControls
            ? t('editor.filteredCount', { shown: visibleGoals.length, total: goals.length })
            : String(goals.length)
        }
      />

      <WorkspaceTree
        data-testid="goals-tree"
        nodes={nodes}
        selectedId={selectedId}
        onSelect={onSelect}
        showSearch={false}
        virtualize
        emptyLabel={t("goals.empty", "Noch keine Ziele")}
        noMatchesLabel={t("editor.noMatches", "Keine Treffer.")}
      />

      {/* ch. 13.3 — "empty" and "no match" are different states and get
          different next steps. Both sit below the tree because the two roots
          always exist, so the tree itself is never empty. */}
      {goals.length === 0 && (
        <div
          data-testid="goals-empty"
          style={{
            marginTop: "var(--space-3)",
            padding: "var(--space-4)",
            border: "1px solid var(--color-border)",
            borderRadius: "var(--radius-md)",
            background: "var(--color-surface-raised)",
          }}
        >
          <p
            style={{
              margin: 0,
              fontSize: "var(--font-size-sm)",
              fontWeight: "var(--weight-semibold)",
              color: "var(--color-text)",
            }}
          >
            {t("goals.empty", "Noch keine Ziele")}
          </p>
          <p
            style={{
              margin: "var(--space-2) 0 0",
              maxWidth: "var(--measure)",
              lineHeight: "var(--leading-normal)",
              color: "var(--color-text-muted)",
              fontSize: "var(--font-size-sm)",
            }}
          >
            {t(
              "goals.emptyHint",
              "Ziele halten fest, was der Workspace erreichen soll.",
            )}
          </p>
        </div>
      )}

      {goals.length > 0 && visibleGoals.length === 0 && (
        <div data-testid="goals-no-matches" style={{ marginTop: "var(--space-3)" }}>
          <p
            style={{
              margin: 0,
              color: "var(--color-text-muted)",
              fontSize: "var(--font-size-sm)",
            }}
          >
            {t("editor.noMatches", "Keine Treffer.")}
          </p>
          <button
            type="button"
            className="btn-secondary"
            data-testid="goal-reset-filters-button"
            style={{ marginTop: "var(--space-3)" }}
            onClick={() => {
              setSearch("");
              setStatusFilter("");
            }}
          >
            {t("editor.resetFilters", "Filter zurücksetzen")}
          </button>
        </div>
      )}
    </div>
  );
}

GoalsTree.displayName = "GoalsTree";
