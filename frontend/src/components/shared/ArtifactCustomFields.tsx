/**
 * ARCH-L1-001 ReactFrontend — Workspace custom field editor (REQ-016).
 *
 * Renders the workspace-defined custom fields for a single artifact and lets the
 * user enter/edit their values. Values are loaded from and saved to the
 * per-artifact value endpoint independently of the host form's own save flow.
 *
 * Field controls are typed:
 *   - text     → text input
 *   - number   → number input
 *   - dropdown → select of the definition's options
 */

import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  customFieldsApi,
  type CustomFieldValueRow,
} from "../../api/custom-fields";
import { extractErrorMessage } from "../../api/client";
import type { UUID } from "../../types";

const labelStyle: React.CSSProperties = {
  display: "block",
  marginBottom: "var(--space-1)",
  fontWeight: 600,
  color: "var(--color-text)",
  fontSize: "var(--font-size-sm)",
};

const inputStyle: React.CSSProperties = {
  width: "100%",
  padding: "var(--space-2) var(--space-3)",
  background: "var(--color-surface-raised)",
  border: "1px solid var(--color-border)",
  borderRadius: "var(--radius-md)",
  color: "var(--color-text)",
  fontSize: "var(--font-size-sm)",
  marginBottom: "var(--space-3)",
};

interface ArtifactCustomFieldsProps {
  artifactId: UUID;
}

export function ArtifactCustomFields({
  artifactId,
}: ArtifactCustomFieldsProps): JSX.Element | null {
  const { t } = useTranslation();
  const [rows, setRows] = useState<CustomFieldValueRow[]>([]);
  const [draft, setDraft] = useState<Record<UUID, string>>({});
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedOk, setSavedOk] = useState(false);

  const load = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      // Defensive: this block is embedded in artifact editors, so a response
      // that is not the expected array (paginated envelope, error body,
      // stubbed client) must degrade to "no custom fields" instead of
      // throwing and tearing the whole host form out of the tree.
      const data = await customFieldsApi.getValues(artifactId);
      const safeRows = Array.isArray(data) ? data : [];
      setRows(safeRows);
      setDraft(
        Object.fromEntries(safeRows.map((r) => [r.definition_id, r.value]))
      );
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setIsLoading(false);
    }
  }, [artifactId]);

  useEffect(() => {
    void load();
  }, [load]);

  const setValue = (definitionId: UUID, value: string): void => {
    setSavedOk(false);
    setDraft((prev) => ({ ...prev, [definitionId]: value }));
  };

  const handleSave = async (): Promise<void> => {
    setIsSaving(true);
    setError(null);
    setSavedOk(false);
    try {
      const updated = await customFieldsApi.putValues(
        artifactId,
        rows.map((r) => ({
          definition_id: r.definition_id,
          value: draft[r.definition_id] ?? "",
        }))
      );
      // Same reasoning as in load(): keep the current rows rather than
      // crashing when the response is not the expected array.
      const safeUpdated = Array.isArray(updated) ? updated : rows;
      setRows(safeUpdated);
      setDraft(
        Object.fromEntries(safeUpdated.map((r) => [r.definition_id, r.value]))
      );
      setSavedOk(true);
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setIsSaving(false);
    }
  };

  // Nothing to render when no workspace custom fields are defined.
  if (!isLoading && rows.length === 0) {
    return null;
  }

  return (
    <div style={{ marginBottom: "var(--space-6)" }} data-testid="artifact-custom-fields">
      <h3
        style={{
          fontSize: "var(--font-size-md)",
          marginBottom: "var(--space-4)",
          borderBottom: "1px solid var(--color-border)",
          paddingBottom: "var(--space-2)",
        }}
      >
        {t("customFields.workspaceSection", "Workspace-Felder")}
      </h3>

      {isLoading ? (
        <p>{t("loading", "Loading...")}</p>
      ) : (
        <>
          {rows.map((row) => {
            const value = draft[row.definition_id] ?? "";
            const controlId = `cf-${row.definition_id}`;
            return (
              <div key={row.definition_id}>
                <label htmlFor={controlId} style={labelStyle}>
                  {row.name}{" "}
                  {row.is_required && (
                    <span style={{ color: "var(--color-danger)" }}>*</span>
                  )}
                </label>
                {row.field_type === "dropdown" ? (
                  <select
                    id={controlId}
                    data-testid={`cf-input-${row.definition_id}`}
                    value={value}
                    onChange={(e) => setValue(row.definition_id, e.target.value)}
                    style={inputStyle}
                  >
                    <option value="">--</option>
                    {row.options.map((opt) => (
                      <option key={opt} value={opt}>
                        {opt}
                      </option>
                    ))}
                  </select>
                ) : (
                  <input
                    id={controlId}
                    data-testid={`cf-input-${row.definition_id}`}
                    type={row.field_type === "number" ? "number" : "text"}
                    value={value}
                    onChange={(e) => setValue(row.definition_id, e.target.value)}
                    style={inputStyle}
                  />
                )}
              </div>
            );
          })}

          {error && (
            <p
              role="alert"
              data-testid="artifact-custom-fields-error"
              style={{ color: "var(--color-danger)", marginBottom: "var(--space-3)" }}
            >
              {error}
            </p>
          )}
          {savedOk && (
            <p
              data-testid="artifact-custom-fields-saved"
              style={{ color: "var(--color-success)", marginBottom: "var(--space-3)" }}
            >
              {t("settings.saved", "Saved")}
            </p>
          )}

          <button
            type="button"
            data-testid="artifact-custom-fields-save"
            onClick={() => void handleSave()}
            disabled={isSaving}
            style={{
              background: "var(--color-primary)",
              color: "white",
              border: "none",
              borderRadius: "var(--radius-md)",
              padding: "var(--space-2) var(--space-4)",
              fontSize: "var(--font-size-sm)",
              fontWeight: 600,
              cursor: isSaving ? "not-allowed" : "pointer",
              opacity: isSaving ? 0.7 : 1,
            }}
          >
            {isSaving
              ? t("actions.saving", "Saving...")
              : t("customFields.saveValues", "Felder speichern")}
          </button>
        </>
      )}
    </div>
  );
}
