/**
 * ARCH-L1-001 ReactFrontend — MainGoalPanel (REQ-L2-TE-020).
 *
 * Shows the currently approved (Freigegeben) MainGoal of a workspace, offers
 * an AI-generated draft when `aiEnabled`, and lets an editor approve a draft.
 */

import { useEffect, useState } from "react";
import { mainGoalApi } from "../../api/main-goal";
import type { MainGoal, UUID } from "../../types";

interface MainGoalPanelProps {
  workspaceId: UUID;
  aiEnabled: boolean;
}

export function MainGoalPanel({ workspaceId, aiEnabled }: MainGoalPanelProps): JSX.Element {
  const [current, setCurrent] = useState<MainGoal | null>(null);
  const [draft, setDraft] = useState<MainGoal | null>(null);

  useEffect(() => {
    void mainGoalApi.current(workspaceId).then(setCurrent);
  }, [workspaceId]);

  const handleGenerate = async (): Promise<void> => {
    const result = await mainGoalApi.generate(workspaceId);
    setDraft(result);
  };

  const handleApprove = async (id: string): Promise<void> => {
    const approved = await mainGoalApi.approve(id);
    setCurrent(approved);
    setDraft(null);
  };

  return (
    <div data-testid="main-goal-panel">
      {current ? (
        <p>{current.content}</p>
      ) : (
        <p>Kein Haupt-Ziel freigegeben.</p>
      )}
      {aiEnabled && (
        <button data-testid="main-goal-generate-button" onClick={() => void handleGenerate()}>
          Haupt-Ziel per KI generieren
        </button>
      )}
      {draft && (
        <div data-testid="main-goal-draft">
          <p>{draft.content}</p>
          <button
            data-testid="main-goal-approve-button"
            onClick={() => void handleApprove(draft.id)}
          >
            Freigeben
          </button>
        </div>
      )}
    </div>
  );
}
