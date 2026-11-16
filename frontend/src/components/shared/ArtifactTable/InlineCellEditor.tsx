/**
 * Task 4.8 — inline cell editor (plan 2026-11-04-tabellenansicht-s4).
 *
 * Saves through the **single-item** PATCH of the artifact type (spec §4.3),
 * never through bulk-update. Enter saves, Escape cancels, a server rejection
 * keeps the editor open with its message, a 409/412 shows the reload hint.
 * A locked row and a non-inline-editable column (e.g. status) never open an
 * editor at all.
 */

import { useState, type KeyboardEvent } from "react";
import { useTranslation } from "react-i18next";

import { adrsApi } from "../../../api/adrs";
import { architectureApi } from "../../../api/architecture";
import { glossaryApi } from "../../../api/glossary";
import { issuesApi } from "../../../api/issues";
import { requirementsApi } from "../../../api/requirements";
import { risksApi } from "../../../api/risks";
import { stakeholderNeedApi } from "../../../api/stakeholder-need";
import { testcasesApi } from "../../../api/testcases";
import type { TableRow } from "../../../api/table-views";
import type { TableColumn } from "./columnModel";
import styles from "./ArtifactTable.module.css";

/** `<item_type>` → the single-item update wrapper (verification step 4.8.1). */
export const UPDATE_BY_ITEM_TYPE: Record<
  string,
  (row: TableRow, data: Record<string, unknown>, version: number) => Promise<unknown>
> = {
  Requirement: (row, data, version) =>
    requirementsApi.update(row.id, data, version),
  StakeholderNeed: (row, data, version) =>
    stakeholderNeedApi.update(row.id, { ...data, expected_version: version }),
  ArchitectureElement: (row, data, version) =>
    architectureApi.update(row.id, { ...data, expected_version: version }),
  TestCase: (row, data, version) =>
    testcasesApi.update(row.id, { ...data, expected_version: version }),
  Adr: (row, data, version) =>
    adrsApi.update(row.id, { ...data, expected_version: version } as never),
  Risk: (row, data, version) =>
    risksApi.update(row.id, { ...data, expected_version: version }),
  Issue: (row, data, version) =>
    issuesApi.update(row.id, { ...data, expected_version: version }),
  GlossaryTerm: (row, data, version) =>
    glossaryApi.update(row.id, { ...data, expected_version: version } as never),
};

/** The single-item write for one cell; throws when the type is unsupported. */
export async function updateCellValue(
  row: TableRow,
  field: string,
  value: unknown
): Promise<void> {
  const update = UPDATE_BY_ITEM_TYPE[row.item_type];
  if (!update) throw new Error(`Unsupported item type: ${row.item_type}`);
  await update(row, { [field]: value }, row.version);
}

export interface InlineCellEditorProps {
  column: TableColumn;
  row: TableRow;
  onSave(value: unknown): Promise<void>;
  onCancel(): void;
}

function classify(error: unknown): { conflict: boolean; message: string } {
  const body = error as
    | {
        error?: {
          code?: string;
          message?: string;
          details?: ReadonlyArray<{ field?: string; errors?: string[] }>;
        };
      }
    | null
    | undefined;
  const code = body?.error?.code;
  if (code === "PRECONDITION_FAILED" || code === "CONFLICT") {
    return { conflict: true, message: body?.error?.message ?? code };
  }
  const detail = body?.error?.details?.find(Boolean)?.errors?.[0];
  return {
    conflict: false,
    message: detail ?? body?.error?.message ?? String(error),
  };
}

export function InlineCellEditor({
  column,
  row,
  onSave,
  onCancel,
}: InlineCellEditorProps): JSX.Element | null {
  const { t } = useTranslation();
  const [value, setValue] = useState<string>(() => {
    const current = row.values[column.name];
    return current === null || current === undefined ? "" : String(current);
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [conflict, setConflict] = useState(false);

  if (!column.inlineEditable || row.locked) return null;

  async function save(): Promise<void> {
    if (saving) return;
    setSaving(true);
    setError(null);
    setConflict(false);
    try {
      await onSave(column.type === "number" ? Number(value) : value);
    } catch (exc) {
      const verdict = classify(exc);
      setConflict(verdict.conflict);
      setError(verdict.message);
    } finally {
      setSaving(false);
    }
  }

  function handleKeyDown(event: KeyboardEvent<HTMLElement>): void {
    if (event.key === "Escape") {
      event.preventDefault();
      onCancel();
      return;
    }
    if (event.key === "Enter" && column.type !== "textarea") {
      event.preventDefault();
      void save();
    }
  }

  const messageId = `inline-error-${row.id}-${column.name}`;
  const invalid = error !== null;

  return (
    <span className={styles.inlineEditor} data-testid={`inline-editor-${column.name}`}>
      {column.type === "enum" && column.options ? (
        <select
          className={styles.input}
          data-testid={`inline-input-${column.name}`}
          aria-label={column.label}
          aria-invalid={invalid || undefined}
          aria-describedby={invalid ? messageId : undefined}
          value={value}
          disabled={saving}
          onKeyDown={handleKeyDown}
          onChange={(event) => {
            setValue(event.target.value);
            void onSave(event.target.value).catch((exc) => {
              const verdict = classify(exc);
              setConflict(verdict.conflict);
              setError(verdict.message);
            });
          }}
        >
          <option value="">—</option>
          {column.options.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label_en || option.value}
            </option>
          ))}
        </select>
      ) : (
        <input
          className={styles.input}
          data-testid={`inline-input-${column.name}`}
          aria-label={column.label}
          aria-invalid={invalid || undefined}
          aria-describedby={invalid ? messageId : undefined}
          type={column.type === "number" ? "number" : "text"}
          value={value}
          disabled={saving}
          autoFocus
          onChange={(event) => setValue(event.target.value)}
          onKeyDown={handleKeyDown}
        />
      )}

      {error && (
        <span id={messageId} className={styles.inlineError} role="alert" data-testid="inline-error">
          {conflict ? t("table.inlineConflict") : error}
          {conflict && (
            <button
              type="button"
              className={`btn btn-ghost ${styles.chipRemove}`}
              data-testid="inline-reload"
              onClick={() => {
                setError(null);
                setConflict(false);
                onCancel();
              }}
            >
              {t("table.bulkReload")}
            </button>
          )}
        </span>
      )}
    </span>
  );
}
