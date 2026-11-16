/**
 * Task 4.7 — bulk action bar (plan 2026-11-04-tabellenansicht-s4).
 *
 * Two actions on a selection, both against the merged backend contract:
 * - **Edit fields** → one `PATCH /artifacts/bulk-update/` with
 *   `{workspace_id, entries}`; each entry carries the row's own
 *   `expected_version` and the edited fields plus `change_reason` (the batch is
 *   all-or-nothing, so one stale row rejects the whole write and the dialog
 *   stays open with the per-entry error list).
 * - **Change status** → `POST /artifacts/bulk-transition/` with
 *   `{item_type, ids, to_state, change_reason}` — the target states reachable
 *   from *every* selected row's current state, never a direct status write.
 *
 * The workspace is sent on the update (its serializer demands it) and *not* on
 * the transition (the backend derives it from the ids).
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import {
  tableApi,
  type BulkFailure,
  type BulkUpdateEntry,
  type BulkUpdateResult,
  type BulkTransitionResult,
  type TableRow,
} from "../../../api/table-views";
import { extractApiErrorMessage } from "../../../api/client";
import { workflowTransitionsApi } from "../../../api/workflow-transitions";
import type { WorkflowArtifactType } from "../../../api/workflow-transitions";
import type { UUID } from "../../../types";
import { Dialog } from "../Dialog";
import type { TableColumn } from "./columnModel";
import styles from "./ArtifactTable.module.css";

export const BULK_MAX_ITEMS = 100;

export interface BulkActionBarProps {
  /** Scope of the write; `BulkUpdateRequestSerializer` requires it. */
  workspaceId: UUID;
  selectedRows: TableRow[];
  columns: TableColumn[];
  onDone(): void;
}

const WORKFLOW_TYPE: Record<string, WorkflowArtifactType> = {
  Requirement: "requirement",
  StakeholderNeed: "need",
  Adr: "adr",
  TestCase: "test-case",
  Risk: "risk",
  Issue: "issue",
  ArchitectureElement: "architecture",
  GlossaryTerm: "glossary",
};

function failureLabel(failure: BulkFailure, t: (key: string, opts?: Record<string, unknown>) => string): string {
  const id = failure.artifact_id ?? `#${failure.index}`;
  return t("table.bulkFailureLine", { id, code: failure.code, reason: failure.message });
}

export function BulkActionBar({
  workspaceId,
  selectedRows,
  columns,
  onDone,
}: BulkActionBarProps): JSX.Element {
  const { t } = useTranslation();
  const [editing, setEditing] = useState(false);
  const [statusEditing, setStatusEditing] = useState(false);
  const [changeReason, setChangeReason] = useState("");
  const [values, setValues] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);
  const [failures, setFailures] = useState<BulkFailure[]>([]);
  const [message, setMessage] = useState<string | null>(null);
  const [conflict, setConflict] = useState(false);

  const editableColumns = useMemo(
    () => columns.filter((column) => column.inlineEditable),
    [columns]
  );
  const tooMany = selectedRows.length > BULK_MAX_ITEMS;

  const reset = useCallback((): void => {
    setValues({});
    setFailures([]);
    setMessage(null);
    setConflict(false);
    setChangeReason("");
  }, []);

  /**
   * One entry per selected row. `change_reason` is not a batch-level field on
   * the wire: the artifact services take it per write, so it joins `fields`.
   */
  function buildEntries(): BulkUpdateEntry[] {
    const fields: Record<string, unknown> = {};
    for (const [field, raw] of Object.entries(values)) {
      if (raw !== "") fields[field] = raw;
    }
    const reason = changeReason.trim();
    return selectedRows.map((row) => ({
      artifact_id: row.artifact_id,
      expected_version: row.version,
      fields: reason ? { ...fields, change_reason: reason } : { ...fields },
    }));
  }

  async function submitEdit(): Promise<void> {
    setSubmitting(true);
    setFailures([]);
    setMessage(null);
    setConflict(false);
    try {
      const result: BulkUpdateResult = await tableApi.bulkUpdate({
        workspace_id: workspaceId,
        entries: buildEntries(),
      });
      if (!result.committed) {
        setFailures(result.failed);
        setConflict(
          result.failed.length > 0 && result.failed.every((f) => f.code === "CONFLICT")
        );
        return;
      }
      setEditing(false);
      reset();
      onDone();
    } catch (exc) {
      setMessage(extractApiErrorMessage(exc));
    } finally {
      setSubmitting(false);
    }
  }

  // --- Change status -------------------------------------------------------

  const [commonStates, setCommonStates] = useState<string[]>([]);
  const [statesLoading, setStatesLoading] = useState(false);
  const [targetState, setTargetState] = useState("");

  // The parent rebuilds `selectedRows` (a `.filter()` over the current page) on
  // every render, so its identity is not a stable dependency: keying the load
  // on it re-ran the effect on any unrelated parent update and wiped the target
  // state the user had just picked (the submit button then stayed disabled and
  // the transition was never posted). The selection *content* is the stable
  // key; the rows themselves come from a ref so the effect body stays current
  // without re-subscribing.
  const rowsRef = useRef(selectedRows);
  rowsRef.current = selectedRows;
  const selectionKey = selectedRows
    .map((row) => `${row.id}:${row.item_type}`)
    .join(",");

  useEffect(() => {
    if (!statusEditing) return undefined;
    const rows = rowsRef.current;
    if (rows.length === 0) return undefined;
    let cancelled = false;
    setStatesLoading(true);
    setCommonStates([]);
    setTargetState("");
    const loads = rows.map(async (row) => {
      const type = WORKFLOW_TYPE[row.item_type];
      if (!type) return null;
      const response = await workflowTransitionsApi.getTransitions(type, row.id);
      return response.allowed_transitions.map((entry) => entry.target_state);
    });
    Promise.all(loads)
      .then((lists) => {
        if (cancelled) return;
        const usable = lists.filter((list): list is string[] => Array.isArray(list));
        if (usable.length === 0) {
          setCommonStates([]);
          return;
        }
        const [first, ...rest] = usable;
        setCommonStates(
          first.filter((state) => rest.every((list) => list.includes(state)))
        );
      })
      .catch(() => {
        if (!cancelled) setCommonStates([]);
      })
      .finally(() => {
        if (!cancelled) setStatesLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [statusEditing, selectionKey]);

  async function submitTransition(): Promise<void> {
    if (!targetState || !changeReason.trim()) return;
    setSubmitting(true);
    setFailures([]);
    setMessage(null);
    setConflict(false);
    try {
      const itemType = selectedRows[0]?.item_type ?? "";
      const result: BulkTransitionResult = await tableApi.bulkTransition({
        item_type: itemType,
        ids: selectedRows.map((row) => row.artifact_id),
        to_state: targetState,
        change_reason: changeReason.trim(),
      });
      if (result.failed.length > 0) {
        setFailures(result.failed);
        setMessage(
          t("table.bulkTransitionResult", {
            updated: result.transitioned.length,
            total: selectedRows.length,
            failed: result.failed.length,
          })
        );
      }
      onDone();
      if (result.failed.length === 0) {
        setStatusEditing(false);
        reset();
      }
    } catch (exc) {
      setMessage(extractApiErrorMessage(exc));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className={styles.bulkBar} data-testid="bulk-action-bar">
      <span data-testid="bulk-selection-count">
        {t("table.bulkSelected", { count: selectedRows.length })}
      </span>
      <button
        type="button"
        className={`btn btn-secondary ${styles.secondaryButton}`}
        data-testid="bulk-edit-fields"
        onClick={() => {
          reset();
          setEditing(true);
        }}
      >
        {t("table.bulkEditFields")}
      </button>
      <button
        type="button"
        className={`btn btn-secondary ${styles.secondaryButton}`}
        data-testid="bulk-change-status"
        onClick={() => {
          reset();
          setStatusEditing(true);
        }}
      >
        {t("table.bulkChangeStatus")}
      </button>

      {editing && (
        <Dialog
          title={t("table.bulkEditFields")}
          onClose={() => setEditing(false)}
          testId="bulk-edit-dialog"
          size="md"
        >
          <div className={styles.bulkFieldList}>
            {editableColumns.map((column) => (
              <label key={column.name} className={styles.filterLabel}>
                {column.label}
                <input
                  className={styles.input}
                  data-testid={`bulk-field-${column.name}`}
                  value={values[column.name] ?? ""}
                  onChange={(event) =>
                    setValues((current) => ({
                      ...current,
                      [column.name]: event.target.value,
                    }))
                  }
                />
              </label>
            ))}
          </div>

          <label className={styles.filterLabel}>
            {t("table.bulkChangeReason")}
            <input
              className={styles.input}
              data-testid="bulk-change-reason"
              value={changeReason}
              onChange={(event) => setChangeReason(event.target.value)}
            />
          </label>

          {tooMany && (
            <p className={styles.warning} data-testid="bulk-too-many">
              {t("table.bulkTooMany", { max: BULK_MAX_ITEMS })}
            </p>
          )}

          {failures.length > 0 && (
            <ul className={styles.failureList} data-testid="bulk-failures">
              {failures.map((failure, index) => (
                <li key={`${failure.artifact_id}-${index}`}>
                  {failureLabel(failure, t)}
                </li>
              ))}
            </ul>
          )}

          {message && (
            <p className={styles.warning} role="status" data-testid="bulk-result-message">
              {message}
            </p>
          )}

          {conflict && (
            <button
              type="button"
              className={`btn btn-secondary ${styles.secondaryButton}`}
              data-testid="bulk-reload"
              onClick={() => {
                onDone();
                setEditing(false);
              }}
            >
              {t("table.bulkReload")}
            </button>
          )}

          <div className={styles.dialogActions}>
            <button
              type="button"
              className={`btn btn-secondary ${styles.secondaryButton}`}
              data-testid="bulk-cancel"
              onClick={() => setEditing(false)}
            >
              {t("table.cancel")}
            </button>
            <button
              type="button"
              className={`btn btn-primary ${styles.primaryButton}`}
              data-testid="bulk-submit"
              disabled={
                submitting ||
                tooMany ||
                Object.values(values).every((value) => value === "")
              }
              onClick={() => void submitEdit()}
            >
              {t("table.bulkSubmit")}
            </button>
          </div>
        </Dialog>
      )}

      {statusEditing && (
        <Dialog
          title={t("table.bulkChangeStatus")}
          onClose={() => setStatusEditing(false)}
          testId="bulk-status-dialog"
          size="sm"
        >
          <label className={styles.filterLabel}>
            {t("table.bulkTargetState")}
            <select
              className={styles.select}
              data-testid="bulk-target-state"
              value={targetState}
              disabled={statesLoading || commonStates.length === 0}
              onChange={(event) => setTargetState(event.target.value)}
            >
              <option value="">
                {statesLoading ? t("table.loading") : t("table.bulkNoCommonState")}
              </option>
              {commonStates.map((state) => (
                <option key={state} value={state}>
                  {state}
                </option>
              ))}
            </select>
          </label>
          <label className={styles.filterLabel}>
            {t("table.bulkChangeReason")}
            <input
              className={styles.input}
              data-testid="bulk-status-change-reason"
              value={changeReason}
              onChange={(event) => setChangeReason(event.target.value)}
            />
          </label>
          {message && (
            <p className={styles.warning} role="status" data-testid="bulk-result-message">
              {message}
            </p>
          )}
          {failures.length > 0 && (
            <ul className={styles.failureList} data-testid="bulk-failures">
              {failures.map((failure, index) => (
                <li key={`${failure.artifact_id}-${index}`}>
                  {failureLabel(failure, t)}
                </li>
              ))}
            </ul>
          )}
          <div className={styles.dialogActions}>
            <button
              type="button"
              className={`btn btn-secondary ${styles.secondaryButton}`}
              data-testid="bulk-cancel"
              onClick={() => setStatusEditing(false)}
            >
              {t("table.cancel")}
            </button>
            <button
              type="button"
              className={`btn btn-primary ${styles.primaryButton}`}
              data-testid="bulk-transition-submit"
              disabled={submitting || !targetState || changeReason.trim() === ""}
              onClick={() => void submitTransition()}
            >
              {t("table.bulkSubmit")}
            </button>
          </div>
        </Dialog>
      )}
    </div>
  );
}
