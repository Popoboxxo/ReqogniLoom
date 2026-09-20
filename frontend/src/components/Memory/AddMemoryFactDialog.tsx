/**
 * ARCH-L1-001 ReactFrontend — AddMemoryFactDialog (RFC #1002, PR D, A4).
 *
 * The "Fakt hinzufügen" write dialog. Offers a scope choice and — for the
 * artifact scope — an artifact selector, mirroring the two REST write paths
 * that actually exist:
 *   - Team        → POST /workspaces/{ws}/memory/entries/
 *   - Artefakt    → POST /artifacts/{artifact_id}/memory/
 *
 * There is deliberately no "Meins" (user) scope here: the REST surface has no
 * user-scope create endpoint (`MemorySelfServiceView` is GET/DELETE only and
 * `POST /workspaces/{ws}/memory/entries/` hardcodes workspace scope), so user
 * facts are written by agents/MCP. See `api/memory.ts`'s module docstring.
 */

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { extractApiErrorMessage } from "../../api/client";
import {
  memoryApi,
  type MemoryScope,
  type MemoryWritePayload,
} from "../../api/memory";
import type { Artifact, UUID } from "../../types";
import { Dialog } from "../shared/Dialog";
import styles from "./MemoryPage.module.css";

export interface AddMemoryFactDialogProps {
  /** Required for the "Team" (workspace) scope; unused when `fixedArtifactId` is set. */
  workspaceId?: UUID;
  /** Selectable artifacts for the "Artefakt" scope. */
  artifacts: Artifact[];
  /** Initial scope; defaults to "workspace". */
  defaultScope?: Extract<MemoryScope, "workspace" | "artifact">;
  /**
   * When set, the dialog is bound to this artifact: the scope selector is
   * hidden and the fact is written to the artifact memory endpoint. Used by
   * `ArtifactMemoryPanel`.
   */
  fixedArtifactId?: UUID;
  onClose: () => void;
  onCreated: () => void;
}

export function artifactLabel(artifact: Artifact): string {
  return `${artifact.artifact_type} · ${artifact.id.slice(0, 8)}`;
}

export function AddMemoryFactDialog({
  workspaceId,
  artifacts,
  defaultScope = "workspace",
  fixedArtifactId,
  onClose,
  onCreated,
}: AddMemoryFactDialogProps): JSX.Element {
  const { t } = useTranslation();
  const [content, setContent] = useState("");
  const [scope, setScope] = useState<"workspace" | "artifact">(
    fixedArtifactId ? "artifact" : defaultScope
  );
  const [artifactId, setArtifactId] = useState<string>(
    fixedArtifactId ?? artifacts[0]?.id ?? ""
  );
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const targetArtifactId = fixedArtifactId ?? artifactId;
  const canSubmit = !isSaving && content.trim().length > 0;

  const handleSubmit = async (): Promise<void> => {
    const trimmed = content.trim();
    if (!trimmed) {
      setError(t("memory.add.contentRequired", "Bitte einen Inhalt eingeben."));
      return;
    }
    setIsSaving(true);
    setError(null);
    const payload: MemoryWritePayload = { content: trimmed };
    try {
      if (scope === "artifact") {
        if (!targetArtifactId) {
          setError(
            t("memory.add.artifactRequired", "Bitte ein Artefakt auswählen.")
          );
          return;
        }
        await memoryApi.createArtifactMemory(targetArtifactId, payload);
      } else {
        if (!workspaceId) {
          setError(
            t("memory.add.workspaceRequired", "Kein Workspace ausgewählt.")
          );
          return;
        }
        await memoryApi.createWorkspaceEntry(workspaceId, payload);
      }
      onCreated();
    } catch (err: unknown) {
      setError(
        extractApiErrorMessage(err) ??
          t("memory.add.error", "Fakt konnte nicht gespeichert werden.")
      );
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <Dialog
      title={t("memory.add.title", "Fakt hinzufügen")}
      onClose={onClose}
      size="sm"
      testId="memory-add-fact-dialog"
      footer={
        <div className={styles.dialogFooter}>
          <button
            type="button"
            data-testid="memory-add-cancel"
            onClick={onClose}
            disabled={isSaving}
          >
            {t("actions.cancel", "Abbrechen")}
          </button>
          <button
            type="button"
            className="btn-primary"
            data-testid="memory-add-submit"
            onClick={() => void handleSubmit()}
            disabled={!canSubmit}
          >
            {isSaving ? "…" : t("memory.add.submit", "Speichern")}
          </button>
        </div>
      }
    >
      <label className={styles.field}>
        {t("memory.add.contentLabel", "Inhalt")}
        <textarea
          data-testid="memory-add-content"
          className={styles.textarea}
          rows={3}
          value={content}
          onChange={(e) => setContent(e.target.value)}
          placeholder={t(
            "memory.add.contentPlaceholder",
            "Fakt, Präferenz oder Entscheidung …"
          )}
        />
      </label>

      {!fixedArtifactId && (
        <>
          <label className={styles.field}>
            {t("memory.add.scopeLabel", "Geltungsbereich")}
            <select
              data-testid="memory-add-scope"
              value={scope}
              onChange={(e) => setScope(e.target.value as "workspace" | "artifact")}
            >
              <option value="workspace">{t("memory.scope.workspace", "Team")}</option>
              <option value="artifact">{t("memory.scope.artifact", "Artefakt")}</option>
            </select>
          </label>

          {scope === "artifact" && (
            <label className={styles.field}>
              {t("memory.add.artifactLabel", "Artefakt")}
              <select
                data-testid="memory-add-artifact"
                value={artifactId}
                onChange={(e) => setArtifactId(e.target.value)}
              >
                {artifacts.length === 0 && (
                  <option value="">
                    {t("memory.add.noArtifacts", "Keine Artefakte vorhanden")}
                  </option>
                )}
                {artifacts.map((artifact) => (
                  <option key={artifact.id} value={artifact.id}>
                    {artifactLabel(artifact)}
                  </option>
                ))}
              </select>
            </label>
          )}
        </>
      )}

      {error && (
        <p role="alert" data-testid="memory-add-error" className={styles.error}>
          {error}
        </p>
      )}
    </Dialog>
  );
}
