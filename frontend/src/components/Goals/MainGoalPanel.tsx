/**
 * ARCH-L1-001 ReactFrontend — MainGoalPanel (REQ-L2-TE-020).
 *
 * Shows the currently approved (Freigegeben) MainGoal of a workspace and lets
 * an editor produce a new draft either
 *   - via LLM aggregation of the workspace's approved Goals, or
 *   - by authoring it manually (`mainGoalApi.createManual`),
 * and then approve that draft.
 *
 * AI-toggle behaviour (design spec 6): the generate entry point stays VISIBLE
 * even when the workspace's AI toggle is off. The backend answers with an
 * explicit "AI generation is disabled for this workspace" error, which is
 * surfaced here — the button is deliberately not hidden client-side, so the
 * user learns why it is unavailable instead of the feature silently vanishing.
 */

import { useEffect, useState } from "react";
import { extractErrorMessage } from "../../api/client";
import { mainGoalApi } from "../../api/main-goal";
import type { MainGoal, UUID } from "../../types";

interface MainGoalPanelProps {
  workspaceId: UUID;
  aiEnabled: boolean;
}

export function MainGoalPanel({ workspaceId, aiEnabled }: MainGoalPanelProps): JSX.Element {
  const [current, setCurrent] = useState<MainGoal | null>(null);
  const [draft, setDraft] = useState<MainGoal | null>(null);
  const [manualContent, setManualContent] = useState("");
  const [manualOpen, setManualOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    mainGoalApi
      .current(workspaceId)
      .then(setCurrent)
      .catch((err: unknown) => setError(extractErrorMessage(err)));
  }, [workspaceId]);

  const handleGenerate = async (): Promise<void> => {
    setError(null);
    try {
      setDraft(await mainGoalApi.generate(workspaceId));
    } catch (err) {
      setError(extractErrorMessage(err));
    }
  };

  const handleCreateManual = async (): Promise<void> => {
    setError(null);
    try {
      setDraft(await mainGoalApi.createManual(workspaceId, manualContent));
      setManualContent("");
      setManualOpen(false);
    } catch (err) {
      setError(extractErrorMessage(err));
    }
  };

  const handleApprove = async (id: string): Promise<void> => {
    setError(null);
    try {
      // The backend returns the FULLY serialized MainGoal (including
      // `content`), so this can replace the panel state directly.
      const approved = await mainGoalApi.approve(id);
      setCurrent(approved);
      setDraft(null);
    } catch (err) {
      setError(extractErrorMessage(err));
    }
  };

  return (
    <div data-testid="main-goal-panel">
      {error && (
        <p
          data-testid="main-goal-error"
          role="alert"
          style={{ color: "var(--color-danger)" }}
        >
          {error}
        </p>
      )}
      {current ? <p>{current.content}</p> : <p>Kein Haupt-Ziel freigegeben.</p>}
      <button
        data-testid="main-goal-generate-button"
        onClick={() => void handleGenerate()}
        title={
          aiEnabled
            ? undefined
            : "KI-Generierung ist fuer diesen Workspace deaktiviert."
        }
      >
        Haupt-Ziel per KI generieren
      </button>
      <button
        data-testid="main-goal-manual-toggle-button"
        onClick={() => {
          setError(null);
          setManualOpen((open) => !open);
        }}
      >
        {manualOpen ? "Manuelle Eingabe abbrechen" : "Haupt-Ziel manuell eingeben"}
      </button>
      {manualOpen && (
        <div data-testid="main-goal-manual-form">
          <textarea
            data-testid="main-goal-manual-input"
            value={manualContent}
            onChange={(e) => setManualContent(e.target.value)}
            placeholder="Haupt-Ziel"
          />
          <button
            data-testid="main-goal-manual-create-button"
            onClick={() => void handleCreateManual()}
          >
            Entwurf anlegen
          </button>
        </div>
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
