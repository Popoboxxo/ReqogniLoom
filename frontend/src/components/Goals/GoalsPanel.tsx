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
 */

import { useCallback, useEffect, useState } from "react";
import { extractErrorMessage } from "../../api/client";
import { goalsApi } from "../../api/goals";
import type { Goal, UUID } from "../../types";

interface GoalsPanelProps {
  workspaceId: UUID;
}

/** Workflow state a Goal must reach to count as aggregation input. */
const APPROVED_STATE = "Freigegeben";
/** Initial workflow state of every newly created Goal version. */
const DRAFT_STATE = "Entwurf";

export function GoalsPanel({ workspaceId }: GoalsPanelProps): JSX.Element {
  const [goals, setGoals] = useState<Goal[]>([]);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [editing, setEditing] = useState<Goal | null>(null);
  const [error, setError] = useState<string | null>(null);

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

  const resetForm = (): void => {
    setEditing(null);
    setTitle("");
    setDescription("");
  };

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
      setError(extractErrorMessage(err));
    }
  };

  const handleEdit = (goal: Goal): void => {
    setError(null);
    setEditing(goal);
    setTitle(goal.title);
    setDescription(goal.description);
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

  return (
    <div data-testid="goals-panel">
      {error && (
        <p data-testid="goals-error" role="alert" style={{ color: "var(--color-danger)" }}>
          {error}
        </p>
      )}
      <ul>
        {goals.map((g) => (
          <li key={g.id} data-testid="goal-list-item">
            {g.title}
            <span data-testid="goal-status">{g.status}</span>
            <button data-testid="goal-edit-button" onClick={() => handleEdit(g)}>
              Bearbeiten
            </button>
            {g.status === DRAFT_STATE && (
              <button
                data-testid="goal-approve-button"
                onClick={() => void handleApprove(g)}
              >
                Freigeben
              </button>
            )}
          </li>
        ))}
      </ul>
      <input
        data-testid="goal-title-input"
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        placeholder="Titel"
      />
      <input
        data-testid="goal-description-input"
        value={description}
        onChange={(e) => setDescription(e.target.value)}
        placeholder="Beschreibung"
      />
      <button data-testid="goal-create-button" onClick={() => void handleSubmit()}>
        {editing ? "Neue Version speichern" : "Ziel anlegen"}
      </button>
      {editing && (
        <button data-testid="goal-edit-cancel-button" onClick={resetForm}>
          Abbrechen
        </button>
      )}
    </div>
  );
}
