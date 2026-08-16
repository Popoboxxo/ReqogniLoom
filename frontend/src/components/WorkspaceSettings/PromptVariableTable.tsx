/**
 * ARCH-L1-001 ReactFrontend — per-slot prompt variable table (spec §5).
 *
 * leaf_id: COMP-RF-001 (WorkspaceSettings — admin configuration)
 * req_id:  REQ-L2-PT-001
 *
 * Renders, under one prompt editor, the variables that prompt actually uses:
 * its declared `data` variables (code-bound, documentation only) plus every
 * `config` variable its body references. Read-only by design — editing a
 * value happens in the central variable management section, so a value is
 * never editable in two places with two different scopes.
 *
 * All styles are hoisted module constants rather than inline object literals:
 * the `ui-ratchet` test asserts the project-wide inline-style-object count
 * with strict equality, so a new component must not add any.
 */

import type { CSSProperties } from "react";
import { useTranslation } from "react-i18next";

import type {
  PromptVariableScope,
  PromptVariableState,
} from "../../api/prompt-variables";

export interface PromptVariableTableProps {
  /** Slot the table belongs to — only used to build stable data-testids. */
  slotName: string;
  /** Variable names this slot references, in display order. */
  variableNames: string[];
  /** The full catalog, as loaded once by the parent section. */
  variables: PromptVariableState[];
}

const wrapperStyle: CSSProperties = {
  marginTop: "var(--space-2)",
  border: "1px solid var(--color-border)",
  borderRadius: "var(--radius-md)",
  overflow: "hidden",
};

const tableStyle: CSSProperties = {
  width: "100%",
  borderCollapse: "collapse",
  fontSize: "var(--font-size-xs, 0.75rem)",
};

const headCellStyle: CSSProperties = {
  textAlign: "left",
  padding: "var(--space-1) var(--space-2)",
  background: "var(--color-surface-raised)",
  color: "var(--color-text-muted)",
  fontWeight: 600,
};

const cellStyle: CSSProperties = {
  padding: "var(--space-1) var(--space-2)",
  borderTop: "1px solid var(--color-border)",
  color: "var(--color-text)",
  verticalAlign: "top",
};

const monoCellStyle: CSSProperties = {
  ...cellStyle,
  fontFamily: "var(--font-mono, monospace)",
};

const badgeStyle: CSSProperties = {
  display: "inline-block",
  padding: "0 var(--space-2)",
  borderRadius: "var(--radius-sm, 4px)",
  border: "1px solid var(--color-border)",
  color: "var(--color-text-muted)",
  fontWeight: 500,
};

/** Render a variable value for display without collapsing falsy values. */
function formatValue(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "string") return value;
  return JSON.stringify(value);
}

export function PromptVariableTable({
  slotName,
  variableNames,
  variables,
}: PromptVariableTableProps): JSX.Element | null {
  const { t } = useTranslation();

  const byName = new Map(variables.map((v) => [v.name, v]));
  const rows = variableNames
    .map((name) => byName.get(name))
    .filter((v): v is PromptVariableState => v !== undefined);

  if (rows.length === 0) return null;

  const originLabel = (origin: PromptVariableScope): string => {
    if (origin === "workspace") {
      return t("settings.promptVariables.origin.workspace", "Workspace-Override");
    }
    if (origin === "global") {
      return t("settings.promptVariables.origin.global", "Globaler Standard");
    }
    return t("settings.promptVariables.origin.factory", "Werkseinstellung");
  };

  return (
    <div style={wrapperStyle} data-testid={`prompt-vars-${slotName}`}>
      <table style={tableStyle}>
        <thead>
          <tr>
            <th style={headCellStyle}>
              {t("settings.promptVariables.columnName", "Variable")}
            </th>
            <th style={headCellStyle}>
              {t("settings.promptVariables.columnKind", "Art")}
            </th>
            <th style={headCellStyle}>
              {t("settings.promptVariables.columnType", "Typ")}
            </th>
            <th style={headCellStyle}>
              {t("settings.promptVariables.columnDescription", "Beschreibung")}
            </th>
            <th style={headCellStyle}>
              {t("settings.promptVariables.columnValue", "Effektiver Wert")}
            </th>
            <th style={headCellStyle}>
              {t("settings.promptVariables.columnOrigin", "Herkunft")}
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.name} data-testid={`prompt-var-${slotName}-${row.name}`}>
              <td style={monoCellStyle}>{`{${row.name}}`}</td>
              <td style={cellStyle}>
                {row.kind === "config"
                  ? t("settings.promptVariables.kindConfig", "konfigurierbar")
                  : t("settings.promptVariables.kindData", "code-gebunden")}
              </td>
              <td style={cellStyle}>{row.var_type}</td>
              <td style={cellStyle}>{row.description}</td>
              <td style={monoCellStyle}>
                {row.kind === "config"
                  ? formatValue(row.effective_value)
                  : t(
                      "settings.promptVariables.computedValue",
                      "wird vom System berechnet"
                    )}
              </td>
              <td style={cellStyle}>
                <span
                  style={badgeStyle}
                  data-testid={`prompt-var-${slotName}-${row.name}-origin`}
                >
                  {row.kind === "config"
                    ? originLabel(row.effective_scope)
                    : t("settings.promptVariables.originCode", "Code")}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
