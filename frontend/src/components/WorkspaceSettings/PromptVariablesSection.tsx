/**
 * ARCH-L1-001 ReactFrontend — central prompt variable management (spec §5).
 *
 * leaf_id: COMP-RF-001 (WorkspaceSettings — admin configuration)
 * req_id:  REQ-L2-PT-001
 *
 * The one place where a variable's value is edited, deliberately separate
 * from the per-slot tables in `AiPromptsSection`: a variable is shared by
 * every prompt that references it, so editing it inside one prompt's editor
 * would misrepresent the blast radius of the change.
 *
 * Scope switch mirrors `AiPromptsSection`: "workspace" writes an override for
 * the active workspace, "global" writes the tenant-wide default.
 * `kind: "data"` rows render read-only with a "code-bound" note.
 *
 * All styles are hoisted module constants (no inline style-object literals) —
 * the `ui-ratchet` test asserts the project-wide count with strict equality.
 */

import type { CSSProperties } from "react";
import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { extractErrorMessage } from "../../api/client";
import {
  promptVariablesApi,
  type PromptVariableState,
  type PromptVariableType,
} from "../../api/prompt-variables";

export interface PromptVariablesSectionProps {
  /** Workspace whose overrides are edited when the scope is "workspace". */
  workspaceId: string;
}

/** Which scope the admin is currently editing. */
type EditScope = "workspace" | "global";

const VARIABLE_TYPES: readonly PromptVariableType[] = [
  "str",
  "int",
  "bool",
  "json",
] as const;

const sectionStyle: CSSProperties = {
  background: "var(--color-surface)",
  border: "1px solid var(--color-border)",
  borderRadius: "var(--radius-lg)",
  padding: "var(--space-5)",
  marginBottom: "var(--space-5)",
  boxShadow: "var(--shadow-card)",
};

const headingStyle: CSSProperties = {
  fontSize: "var(--font-size-lg)",
  fontWeight: 600,
  color: "var(--color-text)",
  margin: "0 0 var(--space-4) 0",
};

const hintStyle: CSSProperties = {
  fontSize: "var(--font-size-sm)",
  color: "var(--color-text-muted)",
  marginBottom: "var(--space-4)",
};

const rowStyle: CSSProperties = {
  display: "flex",
  alignItems: "flex-start",
  gap: "var(--space-3)",
  flexWrap: "wrap",
  padding: "var(--space-2) 0",
  borderTop: "1px solid var(--color-border)",
};

const nameStyle: CSSProperties = {
  fontFamily: "var(--font-mono, monospace)",
  fontSize: "var(--font-size-sm)",
  color: "var(--color-text)",
  minWidth: "14rem",
};

const descriptionStyle: CSSProperties = {
  flex: 1,
  minWidth: "16rem",
  fontSize: "var(--font-size-sm)",
  color: "var(--color-text-muted)",
};

const inputStyle: CSSProperties = {
  width: "10rem",
  padding: "var(--space-1) var(--space-2)",
  background: "var(--color-surface-raised)",
  border: "1px solid var(--color-border)",
  borderRadius: "var(--radius-md)",
  color: "var(--color-text)",
  fontSize: "var(--font-size-sm)",
};

const selectStyle: CSSProperties = {
  padding: "var(--space-2) var(--space-3)",
  background: "var(--color-surface-raised)",
  border: "1px solid var(--color-border)",
  borderRadius: "var(--radius-md)",
  color: "var(--color-text)",
  fontSize: "var(--font-size-sm)",
};

const primaryButtonStyle: CSSProperties = {
  background: "var(--color-primary)",
  color: "white",
  border: "none",
  borderRadius: "var(--radius-md)",
  padding: "var(--space-1) var(--space-3)",
  fontSize: "var(--font-size-sm)",
  fontWeight: 600,
  cursor: "pointer",
};

const secondaryButtonStyle: CSSProperties = {
  background: "transparent",
  color: "var(--color-text-muted)",
  border: "1px solid var(--color-border)",
  borderRadius: "var(--radius-md)",
  padding: "var(--space-1) var(--space-3)",
  fontSize: "var(--font-size-sm)",
  cursor: "pointer",
};

const badgeStyle: CSSProperties = {
  display: "inline-block",
  padding: "0 var(--space-2)",
  borderRadius: "var(--radius-sm, 4px)",
  border: "1px solid var(--color-border)",
  fontSize: "var(--font-size-xs, 0.75rem)",
  color: "var(--color-text-muted)",
  fontWeight: 500,
};

const errorStyle: CSSProperties = {
  color: "var(--color-danger)",
  marginBottom: "var(--space-3)",
};

const scopeRowStyle: CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: "var(--space-3)",
  marginBottom: "var(--space-4)",
};

const createRowStyle: CSSProperties = {
  display: "flex",
  alignItems: "flex-end",
  gap: "var(--space-2)",
  flexWrap: "wrap",
  marginTop: "var(--space-4)",
  paddingTop: "var(--space-3)",
  borderTop: "1px solid var(--color-border)",
};

const labelStyle: CSSProperties = {
  display: "block",
  marginBottom: "var(--space-1)",
  fontWeight: 600,
  color: "var(--color-text)",
  fontSize: "var(--font-size-sm)",
};

/** The value shown for a variable at the scope currently being edited. */
function valueForScope(
  variable: PromptVariableState,
  scope: EditScope
): unknown {
  if (scope === "workspace") return variable.effective_value;
  return variable.global_value ?? variable.factory_default;
}

/** Where the shown value comes from, at the scope being edited. */
function originForScope(
  variable: PromptVariableState,
  scope: EditScope
): string {
  if (scope === "workspace") return variable.effective_scope;
  return variable.global_value === null ? "factory" : "global";
}

/** Turn the raw input text back into the variable's declared type. */
function parseValue(raw: string, varType: PromptVariableType): unknown {
  if (varType === "int") return Number.parseInt(raw, 10);
  if (varType === "bool") return raw === "true";
  if (varType === "json") {
    try {
      return JSON.parse(raw);
    } catch {
      return raw;
    }
  }
  return raw;
}

/** Render a value into the text an input field shows. */
function displayValue(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "string") return value;
  return JSON.stringify(value);
}

export function PromptVariablesSection({
  workspaceId,
}: PromptVariablesSectionProps): JSX.Element {
  const { t } = useTranslation();
  const [scope, setScope] = useState<EditScope>("workspace");
  const [variables, setVariables] = useState<PromptVariableState[]>([]);
  // Only variables the admin actually edited appear here — an absent entry
  // means "show whatever the server last reported".
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [isLoading, setIsLoading] = useState(true);
  const [busyName, setBusyName] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [newName, setNewName] = useState("");
  const [newType, setNewType] = useState<PromptVariableType>("str");
  const [newDescription, setNewDescription] = useState("");
  const [newValue, setNewValue] = useState("");

  const load = useCallback(async (): Promise<void> => {
    setError(null);
    try {
      const data = await promptVariablesApi.list(workspaceId);
      setVariables(data.variables);
      setDrafts({});
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setIsLoading(false);
    }
  }, [workspaceId]);

  useEffect(() => {
    void load();
  }, [load]);

  const targetScopeId = (): string | null =>
    scope === "workspace" ? workspaceId : null;

  const handleScopeChange = (next: EditScope): void => {
    // Drafts are scope-specific: keeping them would carry a workspace edit
    // into a tenant-wide save.
    setScope(next);
    setDrafts({});
    setError(null);
  };

  /** Replace one variable in local state with the server's post-write truth. */
  const applyUpdated = (updated: PromptVariableState): void => {
    setVariables((prev) => {
      const exists = prev.some((v) => v.name === updated.name);
      return exists
        ? prev.map((v) => (v.name === updated.name ? updated : v))
        : [...prev, updated].sort((a, b) => a.name.localeCompare(b.name));
    });
    setDrafts((prev) => {
      const next = { ...prev };
      delete next[updated.name];
      return next;
    });
  };

  const handleSave = async (variable: PromptVariableState): Promise<void> => {
    setBusyName(variable.name);
    setError(null);
    try {
      const raw = drafts[variable.name] ?? displayValue(valueForScope(variable, scope));
      const updated = await promptVariablesApi.save(
        variable.name,
        parseValue(raw, variable.var_type),
        targetScopeId()
      );
      applyUpdated(updated);
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setBusyName(null);
    }
  };

  const handleReset = async (variable: PromptVariableState): Promise<void> => {
    setBusyName(variable.name);
    setError(null);
    try {
      applyUpdated(await promptVariablesApi.clear(variable.name, targetScopeId()));
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setBusyName(null);
    }
  };

  const handleCreate = async (): Promise<void> => {
    const name = newName.trim();
    if (!name) return;
    setBusyName(name);
    setError(null);
    try {
      const updated = await promptVariablesApi.save(
        name,
        parseValue(newValue, newType),
        targetScopeId(),
        { varType: newType, description: newDescription }
      );
      applyUpdated(updated);
      setNewName("");
      setNewDescription("");
      setNewValue("");
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setBusyName(null);
    }
  };

  const originLabel = (origin: string): string => {
    if (origin === "workspace") {
      return t("settings.promptVariables.origin.workspace", "Workspace-Override");
    }
    if (origin === "global") {
      return t("settings.promptVariables.origin.global", "Globaler Standard");
    }
    return t("settings.promptVariables.origin.factory", "Werkseinstellung");
  };

  if (isLoading) {
    return (
      <section style={sectionStyle} data-testid="prompt-variables-section">
        <h3 style={headingStyle}>
          {t("settings.promptVariables.title", "Prompt-Variablen")}
        </h3>
        <p>{t("loading", "Loading...")}</p>
      </section>
    );
  }

  return (
    <section style={sectionStyle} data-testid="prompt-variables-section">
      <h3 style={headingStyle}>
        {t("settings.promptVariables.title", "Prompt-Variablen")}
      </h3>
      <p style={hintStyle}>
        {t(
          "settings.promptVariables.description",
          "Zentral verwaltete Werte, die in Prompt-Texten als {name} referenziert werden. 'code-gebunden' bedeutet: der Wert wird vom System aus echten Artefaktdaten berechnet."
        )}
      </p>

      <div style={scopeRowStyle}>
        <label htmlFor="prompt-variables-scope" style={labelStyle}>
          {t("settings.promptTemplates.scope", "Geltungsbereich")}
        </label>
        <select
          id="prompt-variables-scope"
          data-testid="prompt-variables-scope-select"
          value={scope}
          onChange={(e) => handleScopeChange(e.target.value as EditScope)}
          style={selectStyle}
        >
          <option value="workspace">
            {t("settings.promptTemplates.scopeWorkspace", "Nur dieser Workspace")}
          </option>
          <option value="global">
            {t("settings.promptTemplates.scopeGlobal", "Global (alle Workspaces)")}
          </option>
        </select>
      </div>

      {error && (
        <p data-testid="prompt-variables-error" style={errorStyle}>
          {error}
        </p>
      )}

      {variables.map((variable) => {
        const isBusy = busyName === variable.name;
        const origin = originForScope(variable, scope);
        const value = drafts[variable.name] ?? displayValue(valueForScope(variable, scope));
        return (
          <div
            key={variable.name}
            style={rowStyle}
            data-testid={`prompt-variable-row-${variable.name}`}
          >
            <span style={nameStyle}>{`{${variable.name}}`}</span>
            <span style={descriptionStyle}>{variable.description}</span>
            {variable.is_editable ? (
              <>
                <input
                  data-testid={`prompt-variable-${variable.name}-input`}
                  value={value}
                  disabled={isBusy}
                  onChange={(e) =>
                    setDrafts((prev) => ({ ...prev, [variable.name]: e.target.value }))
                  }
                  style={inputStyle}
                />
                <button
                  type="button"
                  data-testid={`prompt-variable-${variable.name}-save`}
                  onClick={() => void handleSave(variable)}
                  disabled={isBusy}
                  style={primaryButtonStyle}
                >
                  {t("save", "Save")}
                </button>
                <button
                  type="button"
                  data-testid={`prompt-variable-${variable.name}-reset`}
                  onClick={() => void handleReset(variable)}
                  disabled={isBusy || origin !== scope}
                  style={secondaryButtonStyle}
                >
                  {t("settings.promptTemplates.resetToGlobal", "Override entfernen")}
                </button>
                <span
                  style={badgeStyle}
                  data-testid={`prompt-variable-${variable.name}-origin`}
                >
                  {originLabel(origin)}
                </span>
              </>
            ) : (
              <span
                style={badgeStyle}
                data-testid={`prompt-variable-${variable.name}-origin`}
              >
                {t("settings.promptVariables.kindData", "code-gebunden")}
              </span>
            )}
          </div>
        );
      })}

      <div style={createRowStyle}>
        <label style={labelStyle} htmlFor="prompt-variable-new-name">
          {t("settings.promptVariables.newName", "Neue Variable")}
          <input
            id="prompt-variable-new-name"
            data-testid="prompt-variable-new-name"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            style={inputStyle}
          />
        </label>
        <label style={labelStyle} htmlFor="prompt-variable-new-type">
          {t("settings.promptVariables.columnType", "Typ")}
          <select
            id="prompt-variable-new-type"
            data-testid="prompt-variable-new-type"
            value={newType}
            onChange={(e) => setNewType(e.target.value as PromptVariableType)}
            style={selectStyle}
          >
            {VARIABLE_TYPES.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </label>
        <label style={labelStyle} htmlFor="prompt-variable-new-description">
          {t("settings.promptVariables.columnDescription", "Beschreibung")}
          <input
            id="prompt-variable-new-description"
            data-testid="prompt-variable-new-description"
            value={newDescription}
            onChange={(e) => setNewDescription(e.target.value)}
            style={inputStyle}
          />
        </label>
        <label style={labelStyle} htmlFor="prompt-variable-new-value">
          {t("settings.promptVariables.columnValue", "Effektiver Wert")}
          <input
            id="prompt-variable-new-value"
            data-testid="prompt-variable-new-value"
            value={newValue}
            onChange={(e) => setNewValue(e.target.value)}
            style={inputStyle}
          />
        </label>
        <button
          type="button"
          data-testid="prompt-variable-new-save"
          onClick={() => void handleCreate()}
          disabled={busyName !== null}
          style={primaryButtonStyle}
        >
          {t("settings.promptVariables.create", "Anlegen")}
        </button>
      </div>
    </section>
  );
}
