/**
 * ARCH-L1-001 ReactFrontend — GoalsPanel (REQ-L2-TE-020).
 *
 * Lists the Goals of a workspace with their workflow status and lets an
 * editor
 *   - create a new Goal (new lineage),
 *   - edit an existing Goal, which creates a NEW immutable version row within
 *     the same lineage (`goalsApi.createVersion`, design spec 2.3 — there is
 *     no in-place update path),
 *   - approve a draft via the generic WorkflowEngine transitions endpoint
 *     (`Entwurf -> Freigegeben`). Only approved Goals feed MainGoal
 *     aggregation (design spec 3/4.2), so this control is the entry point
 *     that makes a Goal effective at all.
 *
 * Every action that can be rejected server-side (role gate, feature toggle,
 * validation) surfaces its error message inline instead of leaving the
 * promise rejection unhandled.
 *
 * UI concept rollout (ch. 12.3/12.4/12.7): every row is a two-line
 * <ArtifactRow>-shaped entry — identity above (ArtifactId + LevelBadge for
 * the lineage position, StatusBadge, VersionBadge), title below. The bare
 * <ul> with an inline status string is gone.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { extractErrorMessage } from "../../api/client";
import { goalsApi } from "../../api/goals";
import { ArtifactId } from "../shared/ArtifactId";
import { ArtifactCustomFields } from "../shared/ArtifactCustomFields";
import { ListToolbar } from "../shared/ListToolbar";
import { StatusBadge } from "../shared/StatusBadge";
import { VersionBadge } from "../shared/VersionBadge";
import type { Goal, UUID } from "../../types";

interface GoalsPanelProps {
  workspaceId: UUID;
  /**
   * Controlled visibility of the create/edit form. When omitted the form is
   * always shown — that is the standalone behaviour the panel had before the
   * page header took over the primary action.
   */
  isFormOpen?: boolean;
  onFormOpenChange?: (open: boolean) => void;
  /** Lets the page header render an always-visible summary (ch. 12.1). */
  onGoalsChange?: (goals: Goal[]) => void;
}

/** Workflow state a Goal must reach to count as aggregation input. */
const APPROVED_STATE = "Freigegeben";
/** Initial workflow state of every newly created Goal version. */
const DRAFT_STATE = "Entwurf";

/** Workflow states a Goal can be in (backend/workflow/definition_store.py). */
const GOAL_STATES = ["Entwurf", "Freigegeben", "Archiviert"] as const;

type GoalSortKey = "default" | "title" | "status";

function sortGoals(list: Goal[], sortKey: GoalSortKey): Goal[] {
  const sorted = [...list];
  switch (sortKey) {
    case "title":
      sorted.sort((a, b) => a.title.localeCompare(b.title));
      break;
    case "status":
      sorted.sort(
        (a, b) =>
          GOAL_STATES.indexOf(a.status as (typeof GOAL_STATES)[number]) -
            GOAL_STATES.indexOf(b.status as (typeof GOAL_STATES)[number]) ||
          a.title.localeCompare(b.title),
      );
      break;
    default:
      break;
  }
  return sorted;
}

export function GoalsPanel({
  workspaceId,
  isFormOpen,
  onFormOpenChange,
  onGoalsChange,
}: GoalsPanelProps): JSX.Element {
  const { t } = useTranslation();
  const [goals, setGoals] = useState<Goal[]>([]);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [editing, setEditing] = useState<Goal | null>(null);
  const [expandedId, setExpandedId] = useState<UUID | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [sortKey, setSortKey] = useState<GoalSortKey>("default");

  // Uncontrolled fallback: no host page owning the primary action means the
  // form stays open, exactly as before this component grew a page header.
  const formOpen = isFormOpen ?? true;
  const setFormOpen = useCallback(
    (open: boolean) => onFormOpenChange?.(open),
    [onFormOpenChange],
  );

  const loadGoals = useCallback(async (): Promise<void> => {
    try {
      setGoals(await goalsApi.list(workspaceId));
    } catch (err) {
      setError(extractErrorMessage(err));
    }
  }, [workspaceId]);

  useEffect(() => {
    void loadGoals();
  }, [loadGoals]);

  useEffect(() => {
    onGoalsChange?.(goals);
  }, [goals, onGoalsChange]);

  const resetForm = useCallback((): void => {
    setEditing(null);
    setTitle("");
    setDescription("");
    setFormOpen(false);
  }, [setFormOpen]);

  const handleSubmit = async (): Promise<void> => {
    setError(null);
    try {
      if (editing) {
        // Immutable-row-per-version: an "edit" is an insert into the same
        // lineage, starting again at `Entwurf`.
        await goalsApi.createVersion(editing.lineage_id, {
          workspace_id: workspaceId,
          title,
          description,
        });
        await loadGoals();
      } else {
        const created = await goalsApi.create(workspaceId, { title, description });
        setGoals((prev) => [...prev, created]);
      }
      resetForm();
    } catch (err) {
      // ch. 12.12: a failed action keeps the form open and states the cause.
      setError(extractErrorMessage(err));
    }
  };

  const handleEdit = (goal: Goal): void => {
    setError(null);
    setEditing(goal);
    setTitle(goal.title);
    setDescription(goal.description);
    setFormOpen(true);
  };

  const handleApprove = async (goal: Goal): Promise<void> => {
    setError(null);
    try {
      await goalsApi.transition(goal.id, APPROVED_STATE, "Ziel freigegeben.");
      await loadGoals();
    } catch (err) {
      setError(extractErrorMessage(err));
    }
  };

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
    return sortGoals(filtered, sortKey);
  }, [goals, search, statusFilter, sortKey]);

  const hasActiveControls = Boolean(search || statusFilter);

  return (
    <div data-testid="goals-panel">
      {error && (
        <p
          data-testid="goals-error"
          role="alert"
          style={{
            color: "var(--color-danger)",
            fontSize: "var(--font-size-sm)",
            marginTop: 0,
          }}
        >
          {error}
        </p>
      )}

      {goals.length > 0 && (
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
              options: GOAL_STATES.map((s) => ({ value: s, label: s })),
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
              ? `${visibleGoals.length} / ${goals.length}`
              : null
          }
        />
      )}

      {goals.length === 0 ? (
        // ch. 12.7 / 13.3 — "empty" (nothing exists) offers to create.
        <div
          data-testid="goals-empty"
          style={{
            padding: "var(--space-6)",
            border: "1px solid var(--color-border)",
            borderRadius: "var(--radius-md)",
            background: "var(--color-surface-raised)",
          }}
        >
          <p
            style={{
              margin: 0,
              fontSize: "var(--font-size-lg)",
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
            {t("goals.emptyHint", "Ziele halten fest, was der Workspace erreichen soll.")}
          </p>
        </div>
      ) : visibleGoals.length === 0 ? (
        // ch. 13.3 — "no match" is a different state: reset the filter.
        <div data-testid="goals-no-matches" style={{ padding: "var(--space-4)" }}>
          <p style={{ margin: 0, color: "var(--color-text-muted)" }}>
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
      ) : (
        <ul
          style={{
            listStyle: "none",
            margin: 0,
            padding: 0,
            display: "flex",
            flexDirection: "column",
            gap: "var(--space-2)",
          }}
        >
          {visibleGoals.map((g) => {
            const isExpanded = expandedId === g.id;
            return (
              <li
                key={g.id}
                data-testid="goal-list-item"
                style={{
                  border: "1px solid var(--color-border)",
                  borderLeft: `3px solid ${
                    isExpanded ? "var(--color-primary)" : "transparent"
                  }`,
                  borderRadius: "var(--radius-md)",
                  background: "var(--color-surface-raised)",
                  padding: "var(--space-3) var(--space-4)",
                }}
              >
                {/* Identity line — ch. 12.3: id, level, status, version. */}
                <div
                  style={{
                    display: "flex",
                    flexWrap: "wrap",
                    alignItems: "center",
                    gap: "var(--space-2)",
                    justifyContent: "space-between",
                  }}
                >
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "var(--space-2)",
                      minWidth: 0,
                    }}
                  >
                    <ArtifactId
                      testId="goal-artifact-id"
                      // Goal has no semantic uid; the lineage prefix is the
                      // stable handle across all versions of one goal.
                      fallback={g.lineage_id.slice(0, 8)}
                      copyValue={g.lineage_id}
                    />
                  </div>
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "var(--space-2)",
                    }}
                  >
                    <StatusBadge status={g.status} testId="goal-status" />
                    <VersionBadge version={g.sequence_number} hideWhenFirst />
                  </div>
                </div>

                {/* Title line */}
                <p
                  style={{
                    margin: "var(--space-1) 0 0",
                    fontSize: "var(--font-size-lg)",
                    lineHeight: "var(--leading-normal)",
                    color: "var(--color-text)",
                  }}
                >
                  {g.title}
                </p>
                {g.description && (
                  <p
                    style={{
                      margin: "var(--space-1) 0 0",
                      maxWidth: "var(--measure)",
                      fontSize: "var(--font-size-sm)",
                      lineHeight: "var(--leading-normal)",
                      color: "var(--color-text-muted)",
                    }}
                  >
                    {g.description}
                  </p>
                )}

                <div
                  style={{
                    display: "flex",
                    flexWrap: "wrap",
                    gap: "var(--space-2)",
                    marginTop: "var(--space-3)",
                  }}
                >
                  <button
                    type="button"
                    className="btn-secondary"
                    data-testid="goal-edit-button"
                    onClick={() => handleEdit(g)}
                  >
                    {t("goals.edit", "Bearbeiten")}
                  </button>
                  {g.status === DRAFT_STATE && (
                    <button
                      type="button"
                      className="btn-primary"
                      data-testid="goal-approve-button"
                      onClick={() => void handleApprove(g)}
                    >
                      {t("goals.approve", "Freigeben")}
                    </button>
                  )}
                  {/* ch. 12.11 — workspace-defined attributes, loaded on
                      demand so the list does not fan out one request per
                      row. Only rendered for goals whose Artifact id the API
                      exposes. */}
                  {g.artifact_id && (
                    <button
                      type="button"
                      className="btn-ghost"
                      data-testid="goal-custom-fields-toggle"
                      aria-expanded={isExpanded}
                      onClick={() => setExpandedId(isExpanded ? null : g.id)}
                    >
                      {t("customFields.workspaceSection", "Workspace-Felder")}
                    </button>
                  )}
                </div>

                {isExpanded && g.artifact_id && (
                  <div style={{ marginTop: "var(--space-3)" }}>
                    <ArtifactCustomFields artifactId={g.artifact_id} />
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}

      {formOpen && (
        <form
          data-testid="goal-form"
          onSubmit={(e) => {
            e.preventDefault();
            void handleSubmit();
          }}
          style={{
            display: "flex",
            flexDirection: "column",
            gap: "var(--space-2)",
            marginTop: "var(--space-4)",
            padding: "var(--space-4)",
            border: "1px solid var(--color-border)",
            borderRadius: "var(--radius-md)",
            background: "var(--color-surface-raised)",
          }}
        >
          <label
            htmlFor="goal-title"
            style={{
              fontSize: "var(--font-size-sm)",
              fontWeight: "var(--weight-semibold)",
              color: "var(--color-text)",
            }}
          >
            {t("goals.goalTitle", "Titel")}
          </label>
          <input
            id="goal-title"
            data-testid="goal-title-input"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            style={{
              padding: "var(--space-2) var(--space-3)",
              borderRadius: "var(--radius-md)",
              border: "1px solid var(--color-border)",
              background: "var(--color-surface)",
              color: "var(--color-text)",
              fontSize: "var(--font-size-sm)",
            }}
          />

          <label
            htmlFor="goal-description"
            style={{
              fontSize: "var(--font-size-sm)",
              fontWeight: "var(--weight-semibold)",
              color: "var(--color-text)",
            }}
          >
            {t("goals.goalDescription", "Beschreibung")}
          </label>
          <input
            id="goal-description"
            data-testid="goal-description-input"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            style={{
              padding: "var(--space-2) var(--space-3)",
              borderRadius: "var(--radius-md)",
              border: "1px solid var(--color-border)",
              background: "var(--color-surface)",
              color: "var(--color-text)",
              fontSize: "var(--font-size-sm)",
            }}
          />

          <div
            style={{
              display: "flex",
              gap: "var(--space-2)",
              justifyContent: "flex-end",
              marginTop: "var(--space-2)",
            }}
          >
            {editing && (
              <button
                type="button"
                className="btn-ghost"
                data-testid="goal-edit-cancel-button"
                onClick={resetForm}
              >
                {t("actions.cancel", "Abbrechen")}
              </button>
            )}
            <button
              type="submit"
              className="btn-primary"
              data-testid="goal-create-button"
            >
              {editing
                ? t("goals.saveVersion", "Neue Version speichern")
                : t("goals.create", "Ziel anlegen")}
            </button>
          </div>
        </form>
      )}
    </div>
  );
}
