/**
 * ARCH-L1-001 ReactFrontend — Custom Fields admin section (REQ-016).
 *
 * Lets workspace administrators define custom fields (name, type, required flag
 * and — for dropdowns — a fixed option set) that apply workspace-wide to all
 * artifacts. Non-admins see the list read-only (write controls are hidden and
 * the backend enforces the admin gate on writes).
 */

import { useEffect, useState, useCallback } from "react";
import { useTranslation } from "react-i18next";
import {
  customFieldsApi,
  CUSTOM_FIELD_TYPES,
  type CustomFieldDefinition,
  type CustomFieldType,
} from "../../api/custom-fields";
import { extractErrorMessage } from "../../api/client";
import { useAuth } from "../../context/AuthContext";
import { ConfirmDialog } from "../shared/ConfirmDialog";
import type { UUID } from "../../types";

const sectionStyle: React.CSSProperties = {
  background: "var(--color-surface)",
  border: "1px solid var(--color-border)",
  borderRadius: "var(--radius-lg)",
  padding: "var(--space-5)",
  marginBottom: "var(--space-5)",
  boxShadow: "var(--shadow-card)",
};

const headingStyle: React.CSSProperties = {
  fontSize: "var(--font-size-lg)",
  fontWeight: 600,
  color: "var(--color-text)",
  margin: "0 0 var(--space-4) 0",
};

const inputStyle: React.CSSProperties = {
  padding: "var(--space-2) var(--space-3)",
  background: "var(--color-surface-raised)",
  border: "1px solid var(--color-border)",
  borderRadius: "var(--radius-md)",
  color: "var(--color-text)",
  fontSize: "var(--font-size-sm)",
};

const buttonStyle: React.CSSProperties = {
  background: "var(--color-primary)",
  color: "var(--color-on-primary)",
  border: "none",
  borderRadius: "var(--radius-md)",
  padding: "var(--space-2) var(--space-4)",
  fontSize: "var(--font-size-sm)",
  fontWeight: 600,
  cursor: "pointer",
};

// Visually-hidden but screen-reader-accessible label — the inline create-form
// below has no room for a visible "Type" caption next to the select (the
// column header above the table already conveys it visually), but the
// control still needs a programmatic accessible name (WCAG 4.1.2).
const visuallyHiddenStyle: React.CSSProperties = {
  position: "absolute",
  width: "1px",
  height: "1px",
  padding: 0,
  margin: "-1px",
  overflow: "hidden",
  clip: "rect(0, 0, 0, 0)",
  whiteSpace: "nowrap",
  border: 0,
};

interface CustomFieldsSectionProps {
  workspaceId: UUID;
}

export function CustomFieldsSection({
  workspaceId,
}: CustomFieldsSectionProps): JSX.Element {
  const { t } = useTranslation();
  const { roles } = useAuth();
  const isAdmin = roles.includes("admin");

  const [definitions, setDefinitions] = useState<CustomFieldDefinition[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // New-field form state.
  const [name, setName] = useState("");
  const [fieldType, setFieldType] = useState<CustomFieldType>("text");
  const [isRequired, setIsRequired] = useState(false);
  const [optionsText, setOptionsText] = useState("");
  const [isSaving, setIsSaving] = useState(false);

  // UI-09 (system audit P4): deleting a custom field definition is
  // destructive and irreversible — require explicit confirmation.
  const [pendingDelete, setPendingDelete] = useState<CustomFieldDefinition | null>(null);

  const load = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      setDefinitions(await customFieldsApi.listDefinitions(workspaceId));
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setIsLoading(false);
    }
  }, [workspaceId]);

  useEffect(() => {
    void load();
  }, [load]);

  const parseOptions = (raw: string): string[] =>
    raw
      .split(",")
      .map((o) => o.trim())
      .filter((o) => o.length > 0);

  const handleCreate = async (): Promise<void> => {
    setIsSaving(true);
    setError(null);
    try {
      await customFieldsApi.createDefinition(workspaceId, {
        name: name.trim(),
        field_type: fieldType,
        is_required: isRequired,
        options: fieldType === "dropdown" ? parseOptions(optionsText) : [],
      });
      setName("");
      setFieldType("text");
      setIsRequired(false);
      setOptionsText("");
      await load();
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setIsSaving(false);
    }
  };

  const handleDelete = async (id: UUID): Promise<void> => {
    setError(null);
    try {
      await customFieldsApi.deleteDefinition(id);
      await load();
    } catch (err) {
      setError(extractErrorMessage(err));
    }
  };

  const confirmDelete = async (): Promise<void> => {
    if (!pendingDelete) return;
    const id = pendingDelete.id;
    setPendingDelete(null);
    await handleDelete(id);
  };

  const handleToggleRequired = async (
    def: CustomFieldDefinition
  ): Promise<void> => {
    setError(null);
    try {
      await customFieldsApi.updateDefinition(def.id, {
        is_required: !def.is_required,
      });
      await load();
    } catch (err) {
      setError(extractErrorMessage(err));
    }
  };

  const canSubmit =
    name.trim().length > 0 &&
    (fieldType !== "dropdown" || parseOptions(optionsText).length > 0);

  return (
    <section style={sectionStyle} data-testid="custom-fields-section">
      <h3 style={headingStyle}>
        {t("settings.customFields.title", "Benutzerdefinierte Felder")}
      </h3>
      <p
        style={{
          fontSize: "var(--font-size-sm)",
          color: "var(--color-text-muted)",
          marginBottom: "var(--space-4)",
        }}
      >
        {t(
          "settings.customFields.description",
          "Definiere zusätzliche Felder, die workspace-weit an allen Artefakten erscheinen."
        )}
      </p>

      {isLoading ? (
        <p>{t("loading", "Loading...")}</p>
      ) : (
        <table
          data-testid="custom-fields-table"
          style={{ width: "100%", borderCollapse: "collapse", marginBottom: "var(--space-4)" }}
        >
          <thead>
            <tr style={{ textAlign: "left", color: "var(--color-text-muted)", fontSize: "var(--font-size-sm)" }}>
              <th style={{ padding: "var(--space-2)" }}>{t("settings.customFields.name", "Name")}</th>
              <th style={{ padding: "var(--space-2)" }}>{t("settings.customFields.type", "Typ")}</th>
              <th style={{ padding: "var(--space-2)" }}>{t("settings.customFields.required", "Pflicht")}</th>
              <th style={{ padding: "var(--space-2)" }}>{t("settings.customFields.options", "Optionen")}</th>
              {isAdmin && <th style={{ padding: "var(--space-2)" }} />}
            </tr>
          </thead>
          <tbody>
            {definitions.length === 0 && (
              <tr>
                <td colSpan={isAdmin ? 5 : 4} style={{ padding: "var(--space-2)", color: "var(--color-text-muted)" }}>
                  {t("settings.customFields.empty", "Noch keine Felder definiert.")}
                </td>
              </tr>
            )}
            {definitions.map((def) => (
              <tr key={def.id} data-testid={`custom-field-row-${def.id}`} style={{ borderTop: "1px solid var(--color-border)" }}>
                <td style={{ padding: "var(--space-2)" }}>{def.name}</td>
                <td style={{ padding: "var(--space-2)" }}>{def.field_type}</td>
                <td style={{ padding: "var(--space-2)" }}>
                  {isAdmin ? (
                    <input
                      type="checkbox"
                      data-testid={`custom-field-required-${def.id}`}
                      checked={def.is_required}
                      onChange={() => void handleToggleRequired(def)}
                    />
                  ) : def.is_required ? (
                    "✓"
                  ) : (
                    "—"
                  )}
                </td>
                <td style={{ padding: "var(--space-2)", color: "var(--color-text-muted)", fontSize: "var(--font-size-sm)" }}>
                  {def.field_type === "dropdown" ? def.options.join(", ") : "—"}
                </td>
                {isAdmin && (
                  <td style={{ padding: "var(--space-2)", textAlign: "right" }}>
                    <button
                      type="button"
                      data-testid={`custom-field-delete-${def.id}`}
                      onClick={() => setPendingDelete(def)}
                      style={{
                        background: "transparent",
                        color: "var(--color-danger)",
                        border: "1px solid var(--color-border)",
                        borderRadius: "var(--radius-md)",
                        padding: "2px var(--space-2)",
                        cursor: "pointer",
                        fontSize: "var(--font-size-sm)",
                      }}
                    >
                      {t("actions.delete", "Löschen")}
                    </button>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {isAdmin && (
        <div
          data-testid="custom-field-create-form"
          style={{ display: "flex", flexWrap: "wrap", gap: "var(--space-2)", alignItems: "center" }}
        >
          <input
            data-testid="custom-field-name-input"
            placeholder={t("settings.customFields.name", "Name")}
            value={name}
            onChange={(e) => setName(e.target.value)}
            style={{ ...inputStyle, flex: "1 1 160px" }}
          />
          <label htmlFor="custom-field-type-select" style={visuallyHiddenStyle}>
            {t("settings.customFields.type", "Typ")}
          </label>
          <select
            id="custom-field-type-select"
            data-testid="custom-field-type-select"
            value={fieldType}
            onChange={(e) => setFieldType(e.target.value as CustomFieldType)}
            style={inputStyle}
          >
            {CUSTOM_FIELD_TYPES.map((tp) => (
              <option key={tp} value={tp}>
                {tp}
              </option>
            ))}
          </select>
          {fieldType === "dropdown" && (
            <input
              data-testid="custom-field-options-input"
              placeholder={t("settings.customFields.optionsHint", "Optionen, Komma-getrennt")}
              value={optionsText}
              onChange={(e) => setOptionsText(e.target.value)}
              style={{ ...inputStyle, flex: "1 1 200px" }}
            />
          )}
          <label style={{ display: "flex", alignItems: "center", gap: "var(--space-1)", fontSize: "var(--font-size-sm)" }}>
            <input
              type="checkbox"
              data-testid="custom-field-required-checkbox"
              checked={isRequired}
              onChange={(e) => setIsRequired(e.target.checked)}
            />
            {t("settings.customFields.required", "Pflicht")}
          </label>
          <button
            type="button"
            data-testid="custom-field-add-button"
            onClick={() => void handleCreate()}
            disabled={isSaving || !canSubmit}
            style={{ ...buttonStyle, opacity: isSaving || !canSubmit ? 0.5 : 1 }}
          >
            {t("actions.add", "Hinzufügen")}
          </button>
        </div>
      )}

      {error && (
        <p
          data-testid="custom-fields-error"
          role="alert"
          style={{ color: "var(--color-danger)", marginTop: "var(--space-3)" }}
        >
          {error}
        </p>
      )}

      {pendingDelete && (
        <ConfirmDialog
          title={t("settings.customFields.deleteConfirmTitle", "Feld löschen")}
          message={t(
            "settings.customFields.deleteConfirmMessage",
            "Feld \"{{name}}\" löschen? Bereits gespeicherte Werte gehen dabei unwiderruflich verloren.",
            { name: pendingDelete.name }
          )}
          confirmLabel={t("actions.delete", "Löschen")}
          onConfirm={() => void confirmDelete()}
          onCancel={() => setPendingDelete(null)}
          testId="custom-field-delete-confirm"
        />
      )}
    </section>
  );
}
