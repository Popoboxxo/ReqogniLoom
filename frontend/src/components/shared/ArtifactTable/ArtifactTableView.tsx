/**
 * Task 4.9 — composition and Requirements-page integration
 * (plan 2026-11-04-tabellenansicht-s4).
 *
 * Self-fetching view: resolved definition → columns, persisted table state →
 * filters/sort/column order, server query → rows (page size 50). The grid,
 * filters, column picker, saved views, bulk bar and inline editor are wired
 * here; every missing slice-1/2/3 endpoint degrades to an empty state with a
 * visible hint instead of a loading loop.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import type { AttributeItemType } from "../../../api/attribute-definitions";
import type { SavedView, SortTerm, TableRow } from "../../../api/table-views";
import { extractApiErrorMessage } from "../../../api/client";
import { workflowTransitionsApi } from "../../../api/workflow-transitions";
import type { WorkflowArtifactType } from "../../../api/workflow-transitions";
import { useActiveWorkspace } from "../../../hooks/useActiveWorkspace";
import { useTableRows, TABLE_PAGE_SIZE } from "../../../queries/tableViews";
import { useArtifactDefinition } from "../ArtifactForm/useArtifactDefinition";
import { Dialog } from "../Dialog";
import { ActiveFilterChips } from "./ActiveFilterChips";
import { ArtifactTable } from "./ArtifactTable";
import { BulkActionBar } from "./BulkActionBar";
import { ColumnFilterPopover } from "./ColumnFilterPopover";
import { ColumnPicker } from "./ColumnPicker";
import { SavedViewBar } from "./SavedViewBar";
import { buildColumns } from "./columnModel";
import { InlineCellEditor, updateCellValue } from "./InlineCellEditor";
import { constraintsFor, withConstraints } from "./filters";
import { useTableViewState } from "./useTableViewState";
import styles from "./ArtifactTable.module.css";

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

export interface ArtifactTableViewProps {
  itemType: AttributeItemType;
}

export function ArtifactTableView({ itemType }: ArtifactTableViewProps): JSX.Element {
  const { t, i18n } = useTranslation();
  const workspace = useActiveWorkspace();
  const workspaceId = workspace?.id;

  const { definition, loading: definitionLoading, error: definitionError } =
    useArtifactDefinition(itemType);
  const { state, setState, ready, error: stateError } = useTableViewState(
    workspaceId,
    itemType
  );

  const [page, setPage] = useState(1);
  const [selection, setSelection] = useState<ReadonlySet<string>>(new Set());
  const [filterOpen, setFilterOpen] = useState<string | null>(null);
  const [editing, setEditing] = useState<{ rowId: string; column: string } | null>(null);
  const [statusRow, setStatusRow] = useState<TableRow | null>(null);
  const [statusStates, setStatusStates] = useState<string[]>([]);
  const [statusTarget, setStatusTarget] = useState("");
  const [statusReason, setStatusReason] = useState("");
  const [statusError, setStatusError] = useState<string | null>(null);
  const [columnPickerOpen, setColumnPickerOpen] = useState(false);

  const filters = state.filters;
  const sort = state.sort;
  const filterKey = JSON.stringify(filters);
  const sortKey = JSON.stringify(sort);

  const columns = useMemo(
    () =>
      buildColumns(definition?.attributes ?? [], state, i18n.language),
    [definition, state, i18n.language]
  );

  const rowsQuery = useTableRows(workspaceId, itemType, filters, sort, page);
  const rows = rowsQuery.data?.results ?? [];
  const count = rowsQuery.data?.count ?? 0;

  // A filter/sort change starts at page 1; keep the previous page out of the
  // new result set. (Derived string keys avoid an effect on object identity.)
  useEffect(() => {
    setPage(1);
  }, [filterKey, sortKey]);

  const activeFilterFields = useMemo(
    () => new Set(Object.keys(filters)),
    [filters]
  );

  const filterColumn = columns.find((column) => column.name === filterOpen) ?? null;

  const applyView = useCallback(
    (view: SavedView): void => {
      setState({
        columns: view.columns ?? [],
        filters: view.filters ?? {},
        sort: view.sort ?? [],
      });
    },
    [setState]
  );

  async function openStatus(row: TableRow): Promise<void> {
    setStatusRow(row);
    setStatusTarget("");
    setStatusReason("");
    setStatusError(null);
    setStatusStates([]);
    const type = WORKFLOW_TYPE[row.item_type];
    if (!type) {
      setStatusError(t("table.changeStatusUnavailable"));
      return;
    }
    try {
      const response = await workflowTransitionsApi.getTransitions(type, row.id);
      setStatusStates(response.allowed_transitions.map((entry) => entry.target_state));
    } catch (exc) {
      setStatusError(extractApiErrorMessage(exc));
    }
  }

  async function submitStatus(): Promise<void> {
    if (!statusRow || !statusTarget || statusReason.trim() === "") return;
    const type = WORKFLOW_TYPE[statusRow.item_type];
    if (!type) return;
    try {
      await workflowTransitionsApi.transition(
        type,
        statusRow.id,
        statusTarget,
        statusReason.trim()
      );
      setStatusRow(null);
      await rowsQuery.refetch();
    } catch (exc) {
      setStatusError(extractApiErrorMessage(exc));
    }
  }

  const errorMessage = rowsQuery.error
    ? extractApiErrorMessage(rowsQuery.error)
    : null;

  return (
    <div className={styles.view} data-testid="artifact-table-view">
      <div className={styles.toolbar}>
        <button
          type="button"
          className={`btn btn-secondary ${styles.secondaryButton}`}
          data-testid="column-picker-toggle"
          aria-expanded={columnPickerOpen}
          onClick={() => setColumnPickerOpen((open) => !open)}
        >
          {t("table.columnsButton")}
        </button>
        {definition && columnPickerOpen && (
          <ColumnPicker
            attributes={definition.attributes}
            state={state}
            onChange={(next) => setState(next)}
          />
        )}
        {workspaceId && (
          <SavedViewBar
            workspaceId={workspaceId}
            itemType={itemType}
            current={state}
            onApply={applyView}
          />
        )}
      </div>

      <ActiveFilterChips
        columns={columns}
        filters={filters}
        onChange={(next) => setState({ ...state, filters: next })}
      />

      {stateError && (
        <p className={styles.warning} role="status" data-testid="table-state-error">
          {stateError}
        </p>
      )}

      {filterColumn && (
        <div className={styles.filterAnchor}>
          <ColumnFilterPopover
            column={filterColumn}
            constraints={constraintsFor(filters, filterColumn.name)}
            onChange={(next) =>
              setState({
                ...state,
                filters: withConstraints(filters, filterColumn.name, next),
              })
            }
            onClose={() => setFilterOpen(null)}
          />
        </div>
      )}

      {(definitionError || (!definitionLoading && definition === null)) && (
        <p className={styles.warning} role="alert" data-testid="artifact-table-definition-error">
          {definitionError ?? t("table.definitionUnavailable")}
        </p>
      )}

      {errorMessage && (
        <p className={styles.warning} role="alert" data-testid="artifact-table-error">
          {errorMessage}
        </p>
      )}

      <ArtifactTable
        columns={columns}
        rows={rows}
        sort={sort}
        onSortChange={(next: SortTerm[]) => setState({ ...state, sort: next })}
        selectedIds={selection}
        onSelectionChange={setSelection}
        loading={definitionLoading || !ready || rowsQuery.isLoading}
        onFilterClick={(column) => setFilterOpen(column.name)}
        activeFilterFields={activeFilterFields}
        onStartInlineEdit={(rowId, columnName) => {
          const row = rows.find((entry) => entry.id === rowId) ?? null;
          const column = columns.find((entry) => entry.name === columnName) ?? null;
          if (!row || !column || row.locked) return;
          if (columnName === "status" || column.editable !== true) {
            void openStatus(row);
            return;
          }
          setEditing({ rowId, column: columnName });
        }}
        renderCellEditor={(column, row) =>
          editing && editing.rowId === row.id && editing.column === column.name ? (
            <InlineCellEditor
              column={column}
              row={row}
              onCancel={() => setEditing(null)}
              onSave={async (value) => {
                await updateCellValue(row, column.name, value);
                setEditing(null);
                await rowsQuery.refetch();
              }}
            />
          ) : (
            <button
              type="button"
              className={`btn btn-ghost ${styles.cellButton}`}
              data-testid={`cell-${row.id}-${column.name}`}
              onClick={() => setEditing({ rowId: row.id, column: column.name })}
            >
              {String(row.values[column.name] ?? "") || t("table.emptyCell")}
            </button>
          )
        }
      />

      {rows.length === 0 && !rowsQuery.isLoading && (
        <p className={styles.hint} data-testid="artifact-table-empty-state">
          {t("table.empty")}
        </p>
      )}

      <div className={styles.pager}>
        <button
          type="button"
          className={`btn btn-secondary ${styles.secondaryButton}`}
          data-testid="table-page-prev"
          disabled={page <= 1 || rowsQuery.isFetching}
          onClick={() => setPage((current) => Math.max(1, current - 1))}
        >
          {t("table.previousPage")}
        </button>
        <span data-testid="table-page-info">
          {t("table.pageInfo", {
            page,
            pages: Math.max(1, Math.ceil(count / TABLE_PAGE_SIZE)),
          })}
        </span>
        <button
          type="button"
          className={`btn btn-secondary ${styles.secondaryButton}`}
          data-testid="table-page-next"
          disabled={page * TABLE_PAGE_SIZE >= count || rowsQuery.isFetching}
          onClick={() => setPage((current) => current + 1)}
        >
          {t("table.nextPage")}
        </button>
      </div>

      {selection.size > 0 && workspaceId && (
        <BulkActionBar
          workspaceId={workspaceId}
          selectedRows={rows.filter((row) => selection.has(row.id))}
          columns={columns}
          onDone={() => {
            setSelection(new Set());
            void rowsQuery.refetch();
          }}
        />
      )}

      {statusRow && (
        <Dialog
          title={t("table.changeStatus")}
          onClose={() => setStatusRow(null)}
          testId="status-change-dialog"
          size="sm"
        >
          <p className={styles.hint}>
            {t("table.statusFor", { title: String(statusRow.values.title ?? statusRow.id) })}
          </p>
          <label className={styles.filterLabel}>
            {t("table.bulkTargetState")}
            <select
              className={styles.select}
              data-testid="status-target"
              value={statusTarget}
              onChange={(event) => setStatusTarget(event.target.value)}
            >
              <option value="">{t("table.bulkNoCommonState")}</option>
              {statusStates.map((state) => (
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
              data-testid="status-reason"
              value={statusReason}
              onChange={(event) => setStatusReason(event.target.value)}
            />
          </label>
          {statusError && (
            <p className={styles.warning} role="alert" data-testid="status-error">
              {statusError}
            </p>
          )}
          <div className={styles.dialogActions}>
            <button
              type="button"
              className={`btn btn-secondary ${styles.secondaryButton}`}
              data-testid="status-cancel"
              onClick={() => setStatusRow(null)}
            >
              {t("table.cancel")}
            </button>
            <button
              type="button"
              className={`btn btn-primary ${styles.primaryButton}`}
              data-testid="status-submit"
              disabled={!statusTarget || statusReason.trim() === ""}
              onClick={() => void submitStatus()}
            >
              {t("table.bulkSubmit")}
            </button>
          </div>
        </Dialog>
      )}
    </div>
  );
}
