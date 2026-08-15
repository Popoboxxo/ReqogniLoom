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
 *
 * Issue #238: goal rows render through the shared `<ArtifactRow>` (via
 * `WorkspaceTree`'s `renderRow` slot, same wiring as RiskList/IssueList/
 * NeedList), so a goal shows its lineage handle, its status as an own badge
 * element and its version — instead of the name+badge default row. The two
 * static roots are not artifacts and keep a plain grouping label. The empty
 * and the no-match state render through the shared `<EmptyState>`, which is
 * the component that keeps "there is nothing" (offer *create*) and "nothing
 * matches this filter" (offer *reset*) visibly different (ch. 13.3).
 */

import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { ArtifactRow } from "../shared/ArtifactRow";
import { EmptyState } from "../shared/EmptyState";
import { ListToolbar } from "../shared/ListToolbar";
import { WorkspaceTree } from "../shared/WorkspaceTree";
import type { WorkspaceTreeNode } from "../shared/WorkspaceTree";
import { getWorkflowStatusLabel } from "../../utils/workflowStatus";
import { workflowsApi } from "../../api/workflows";
import type { Goal } from "../../types";
import styles from "./Goals.module.css";

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

/**
 * `<ArtifactRow>`'s two-line id/title layout is taller than WorkspaceTree's
 * default single-line row estimate (34px) — same value RiskList/IssueList
 * hand the virtualizer.
 */
const VIRTUAL_ROW_HEIGHT_PX = 64;

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
  /**
   * Opens the create dialog. Offered by the empty state (ch. 12.7 — an empty
   * list states the next step instead of only reporting a condition); the
   * no-match state deliberately never gets it.
   */
  onCreateNew?: () => void;
}

export function GoalsTree({
  goals,
  selectedId,
  onSelect,
  workspaceId,
  onCreateNew,
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
    const children = visibleGoals.map(
      (g): WorkspaceTreeNode => ({
        id: g.id,
        name: g.title || t("goals.untitled", "Ohne Titel"),
        parentId: GOALS_ROOT_NODE_ID,
      }),
    );
    return [...roots, ...children];
  }, [visibleGoals, t]);

  /** Lookup used by `renderRow` to hydrate `<ArtifactRow>` from a node id. */
  const goalById = useMemo(() => {
    const map = new Map<string, Goal>();
    for (const goal of visibleGoals) map.set(goal.id, goal);
    return map;
  }, [visibleGoals]);

  const hasActiveControls = Boolean(search || statusFilter);

  const resetFilters = (): void => {
    setSearch("");
    setStatusFilter("");
  };

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
            options: goalStates.map((s) => ({
              value: s,
              label: getWorkflowStatusLabel(s),
            })),
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
            ? t("editor.filteredCount", { shown: visibleGoals.length, total: goals.length })
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
        virtualRowHeight={VIRTUAL_ROW_HEIGHT_PX}
        emptyLabel={t("goals.empty", "Noch keine Ziele")}
        noMatchesLabel={t("editor.noMatches", "Keine Treffer.")}
        renderRow={(node, { isSelected }) => {
          const goal = goalById.get(node.id);
          if (!goal) {
            // The two static roots are grouping/anchor rows, not artifacts.
            return (
              <span
                data-testid={`goals-root-label-${node.id}`}
                className={`${styles.rootRow} ${isSelected ? styles.rootRowSelected : ""}`}
              >
                {node.name}
              </span>
            );
          }
          return (
            <ArtifactRow
              // A Goal has no semantic uid; the lineage prefix is the stable
              // handle that survives across all versions of one goal — same
              // value <GoalDetail>'s identity row shows.
              idFallback={goal.lineage_id.slice(0, 8)}
              title={goal.title || t("goals.untitled", "Ohne Titel")}
              status={goal.status}
              statusLabel={getWorkflowStatusLabel(goal.status)}
              version={goal.sequence_number}
              selected={isSelected}
              testId={`goal-row-${goal.id}`}
            />
          );
        }}
      />

      {/* ch. 13.3 — "empty" and "no match" are different states and get
          different next steps. Both sit below the tree because the two roots
          always exist, so the tree itself is never empty. */}
      {goals.length === 0 && (
        <EmptyState
          variant="empty"
          testId="goals-empty"
          title={t("goals.empty", "Noch keine Ziele")}
          description={t(
            "goals.emptyHint",
            "Ziele halten fest, was der Workspace erreichen soll.",
          )}
          actions={
            onCreateNew
              ? [
                  {
                    label: t("goals.newGoal", "Neues Ziel"),
                    onClick: onCreateNew,
                    testId: "goals-empty-create",
                  },
                ]
              : undefined
          }
        />
      )}

      {goals.length > 0 && visibleGoals.length === 0 && (
        <EmptyState
          variant="no-match"
          testId="goals-no-matches"
          onResetFilters={resetFilters}
        />
      )}
    </div>
  );
}

GoalsTree.displayName = "GoalsTree";
