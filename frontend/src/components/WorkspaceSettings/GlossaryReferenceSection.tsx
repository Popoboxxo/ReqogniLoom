/**
 * ARCH-L1-001 ReactFrontend — Workspace glossary-reference settings (#1266).
 *
 * Controls `glossary_reference_mode`, the workspace-wide resolution rule for
 * version-bound reference tokens `[[glossary:<uuid>@<revision>]]` embedded in
 * markdown/text fields:
 *
 * - `pinned` (default): a reference keeps the term version stored at insertion
 *   time; the UI flags it when the term's head moves on.
 * - `always_head`: references always resolve against the term's current head;
 *   the stored `@<revision>` suffix is ignored (and left untouched, so
 *   switching back is non-destructive).
 *
 * Styled via a co-located CSS module (no inline style objects), matching the
 * shared-settings-section pattern.
 */

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { workspacesApi } from "../../api/workspaces";
import { extractErrorMessage } from "../../api/client";
import type { GlossaryReferenceMode, UUID } from "../../types";
import styles from "./GlossaryReferenceSection.module.css";

interface Props {
  workspaceId: UUID;
  mode: GlossaryReferenceMode;
  /** Reload the workspace so the new mode propagates to the editors. */
  onSaved: () => void | Promise<void>;
}

const MODES: GlossaryReferenceMode[] = ["pinned", "always_head"];

export function GlossaryReferenceSection({ workspaceId, mode, onSaved }: Props): JSX.Element {
  const { t } = useTranslation();
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedOk, setSavedOk] = useState(false);

  const handleChange = async (next: GlossaryReferenceMode): Promise<void> => {
    if (next === mode) return;
    setIsSaving(true);
    setError(null);
    setSavedOk(false);
    try {
      await workspacesApi.update(workspaceId, { glossary_reference_mode: next });
      await onSaved();
      setSavedOk(true);
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <section className={styles.section} data-testid="glossary-reference-section">
      <h3 className={styles.heading}>
        {t("settings.glossaryReference.title")}
      </h3>
      <p className={styles.description}>
        {t("settings.glossaryReference.description")}
      </p>

      <div className={styles.options} data-testid="glossary-reference-mode">
        {MODES.map((option) => (
          <label key={option} className={styles.optionRow}>
            <input
              type="radio"
              name="glossary_reference_mode"
              value={option}
              checked={mode === option}
              disabled={isSaving}
              data-testid={`glossary-reference-mode-${option}`}
              onChange={() => void handleChange(option)}
            />
            <span>
              <span className={styles.optionTitle}>
                {option === "pinned"
                  ? t("settings.glossaryReference.pinned")
                  : t("settings.glossaryReference.alwaysHead")}
              </span>
              <span className={styles.optionHint}>
                {option === "pinned"
                  ? t("settings.glossaryReference.pinnedHint")
                  : t("settings.glossaryReference.alwaysHeadHint")}
              </span>
            </span>
          </label>
        ))}
      </div>

      {error && (
        <p role="alert" className={styles.error} data-testid="glossary-reference-error">
          {error}
        </p>
      )}
      {savedOk && (
        <p className={styles.saved} data-testid="glossary-reference-saved">
          {t("settings.saved")}
        </p>
      )}
    </section>
  );
}
