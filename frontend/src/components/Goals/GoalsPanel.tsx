/**
 * ARCH-L1-001 ReactFrontend — GoalsPanel (REQ-L2-TE-020).
 *
 * Lists the Goals of a workspace and lets an editor create a new one.
 */

import { useEffect, useState } from "react";
import { goalsApi } from "../../api/goals";
import type { Goal, UUID } from "../../types";

interface GoalsPanelProps {
  workspaceId: UUID;
}

export function GoalsPanel({ workspaceId }: GoalsPanelProps): JSX.Element {
  const [goals, setGoals] = useState<Goal[]>([]);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");

  useEffect(() => {
    void goalsApi.list(workspaceId).then(setGoals);
  }, [workspaceId]);

  const handleCreate = async (): Promise<void> => {
    const created = await goalsApi.create(workspaceId, { title, description });
    setGoals((prev) => [...prev, created]);
    setTitle("");
    setDescription("");
  };

  return (
    <div data-testid="goals-panel">
      <ul>
        {goals.map((g) => (
          <li key={g.id} data-testid="goal-list-item">
            {g.title}
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
      <button data-testid="goal-create-button" onClick={() => void handleCreate()}>
        Ziel anlegen
      </button>
    </div>
  );
}
