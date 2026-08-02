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
 *
 * UI concept rollout: identity row (StatusBadge + VersionBadge) above the
 * content, an empty state that offers the next step instead of reporting a
 * condition (ch. 3.5 / 12.7), and action labels that name the result
 * (ch. 14.2).
 */

import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { extractErrorMessage } from "../../api/client";
import { mainGoalApi } from "../../api/main-goal";
import { StatusBadge } from "../shared/StatusBadge";
import { VersionBadge } from "../shared/VersionBadge";
import type { MainGoal, UUID } from "../../types";

interface MainGoalPanelProps {
  workspaceId: UUID;
  aiEnabled: boolean;
}

const sectionStyle: React.CSSProperties = {
  border: "1px solid var(--color-border)",
  borderRadius: "var(--radius-md)",
  background: "var(--color-surface-raised)",
  padding: "var(--space-4)",
};

const bodyStyle: React.CSSProperties = {
  margin: 0,
  maxWidth: "var(--measure)",
  fontSize: "var(--font-size-base)",
  lineHeight: "var(--leading-relaxed)",
  color: "var(--color-text)",
  whiteSpace: "pre-wrap",
};

export function MainGoalPanel({ workspaceId, aiEnabled }: MainGoalPanelProps): JSX.Element {
  const { t } = useTranslation();
  const [current, setCurrent] = useState<MainGoal | null>(null);
  const [draft, setDraft] = useState<MainGoal | null>(null);
  const [manualContent, setManualContent] = useState("");
  const [manualOpen, setManualOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    mainGoalApi
      .current(workspaceId)
      // "No approved main goal yet" is an empty result, not an error
      // (ch. 13.3): the endpoint answers 200 with an empty body, so normalise
      // undefined to null and let the empty state speak.
      .then((mg) => setCurrent(mg ?? null))
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
    <div data-testid="main-goal-panel" style={sectionStyle}>
      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          alignItems: "center",
          justifyContent: "space-between",
          gap: "var(--space-2)",
          marginBottom: "var(--space-3)",
        }}
      >
        <h2
          style={{
            margin: 0,
            fontSize: "var(--font-size-xl)",
            lineHeight: "var(--leading-tight)",
            letterSpacing: "var(--tracking-tight)",
            fontWeight: "var(--weight-semibold)",
            color: "var(--color-text)",
          }}
        >
          {t("goals.mainGoal", "Haupt-Ziel")}
        </h2>
        {current && (
          <div style={{ display: "flex", alignItems: "center", gap: "var(--space-2)" }}>
            <StatusBadge status={current.status} testId="main-goal-status" />
            <VersionBadge version={current.sequence_number} hideWhenFirst />
          </div>
        )}
      </div>

      {error && (
        <p
          data-testid="main-goal-error"
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

      {current ? (
        <p style={bodyStyle}>{current.content}</p>
      ) : (
        <div data-testid="main-goal-empty">
          <p
            style={{
              margin: 0,
              fontSize: "var(--font-size-lg)",
              fontWeight: "var(--weight-semibold)",
              color: "var(--color-text)",
            }}
          >
            {t("goals.mainGoalNone", "Noch kein Haupt-Ziel freigegeben.")}
          </p>
          <p
            style={{
              margin: "var(--space-2) 0 0",
              maxWidth: "var(--measure)",
              fontSize: "var(--font-size-sm)",
              lineHeight: "var(--leading-normal)",
              color: "var(--color-text-muted)",
            }}
          >
            {t(
              "goals.mainGoalNoneHint",
              "Das Haupt-Ziel fasst die freigegebenen Ziele des Workspace zusammen.",
            )}
          </p>
        </div>
      )}

      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          gap: "var(--space-2)",
          marginTop: "var(--space-4)",
        }}
      >
        <button
          type="button"
          className="btn-secondary"
          data-testid="main-goal-generate-button"
          onClick={() => void handleGenerate()}
          title={
            aiEnabled
              ? undefined
              : t(
                  "goals.generateDisabledHint",
                  "KI-Generierung ist fuer diesen Workspace deaktiviert.",
                )
          }
        >
          {t("goals.generate", "Haupt-Ziel per KI erzeugen")}
        </button>
        <button
          type="button"
          className="btn-secondary"
          data-testid="main-goal-manual-toggle-button"
          aria-expanded={manualOpen}
          onClick={() => {
            setError(null);
            setManualOpen((open) => !open);
          }}
        >
          {manualOpen
            ? t("goals.manualCancel", "Eingabe abbrechen")
            : t("goals.manualOpen", "Haupt-Ziel selbst schreiben")}
        </button>
      </div>

      {manualOpen && (
        <form
          data-testid="main-goal-manual-form"
          onSubmit={(e) => {
            e.preventDefault();
            void handleCreateManual();
          }}
          style={{
            display: "flex",
            flexDirection: "column",
            gap: "var(--space-2)",
            marginTop: "var(--space-3)",
          }}
        >
          <label
            htmlFor="main-goal-manual"
            style={{
              fontSize: "var(--font-size-sm)",
              fontWeight: "var(--weight-semibold)",
              color: "var(--color-text)",
            }}
          >
            {t("goals.manualPlaceholder", "Haupt-Ziel")}
          </label>
          <textarea
            id="main-goal-manual"
            data-testid="main-goal-manual-input"
            value={manualContent}
            rows={5}
            onChange={(e) => setManualContent(e.target.value)}
            style={{
              padding: "var(--space-2) var(--space-3)",
              borderRadius: "var(--radius-md)",
              border: "1px solid var(--color-border)",
              background: "var(--color-surface)",
              color: "var(--color-text)",
              fontFamily: "var(--font-sans)",
              fontSize: "var(--font-size-sm)",
              lineHeight: "var(--leading-normal)",
              resize: "vertical",
            }}
          />
          <div style={{ display: "flex", justifyContent: "flex-end" }}>
            <button
              type="submit"
              className="btn-primary"
              data-testid="main-goal-manual-create-button"
            >
              {t("goals.manualCreate", "Entwurf anlegen")}
            </button>
          </div>
        </form>
      )}

      {draft && (
        <div
          data-testid="main-goal-draft"
          style={{
            marginTop: "var(--space-4)",
            padding: "var(--space-3)",
            borderRadius: "var(--radius-md)",
            border: "1px dashed var(--color-border-hover)",
            background: "var(--color-surface)",
          }}
        >
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "var(--space-2)",
              marginBottom: "var(--space-2)",
            }}
          >
            <StatusBadge status={draft.status} testId="main-goal-draft-status" />
            <VersionBadge version={draft.sequence_number} hideWhenFirst />
          </div>
          <p style={bodyStyle}>{draft.content}</p>
          <button
            type="button"
            className="btn-primary"
            data-testid="main-goal-approve-button"
            style={{ marginTop: "var(--space-3)" }}
            onClick={() => void handleApprove(draft.id)}
          >
            {t("goals.approve", "Freigeben")}
          </button>
        </div>
      )}
    </div>
  );
}
