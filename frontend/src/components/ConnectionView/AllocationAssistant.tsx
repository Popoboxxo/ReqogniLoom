/**
 * P3 Task 3.5 / P4.4 — multi-select allocation assistant.
 *
 * The assistant is the selection toolbar of the connection view:
 *
 * - select any number of requirement rows (frozen rows are not selectable);
 * - "Allokieren auf …" opens the shared element picker and sends **one** atomic
 *   `POST /trace-links/bulk/` for the whole selection. The endpoint is
 *   all-or-nothing, so a failure means nothing was written and the UI says so;
 * - "Vorschläge" asks the backend suggestion endpoint for the selected (or all
 *   unallocated) requirements, shows target + reason, and writes only after an
 *   explicit confirmation in the dialog.
 *
 * Frozen requirements show a lock icon whose tooltip carries the workflow
 * state name; frozen elements stay valid targets.
 */

import { useCallback, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Lock } from "lucide-react";

import type {
  AllocationRow,
  BulkAllocationItem,
  BulkAllocationResult,
  SuggestArchitectureResponse,
} from "../../api/allocation-view";
import {
  isRowLocked,
  lockStateName,
  toArchitectureSuggestions,
} from "../../utils/allocation";
import { Dialog } from "../shared/Dialog";
import { toAllocationError } from "../AllocationGraph/errors";
import styles from "./ConnectionView.module.css";

export interface AllocationAssistantProps {
  /** Requirements after the active filters. */
  requirements: AllocationRow[];
  /** Full element catalogue (picker + suggestion target titles). */
  elements: AllocationRow[];
  /** Atomic all-or-nothing write path. */
  allocateBulk: (items: BulkAllocationItem[]) => Promise<BulkAllocationResult>;
  /** Ephemeral LLM suggestion (persists nothing). */
  suggestArchitecture: (
    requirementId: string
  ) => Promise<SuggestArchitectureResponse>;
  /** Write authority; false renders the toolbar read-only. */
  canEdit: boolean;
}

interface SuggestionGroup {
  requirement: AllocationRow;
  candidates: Array<{ element: AllocationRow; reason: string }>;
}

interface PendingWrite {
  items: BulkAllocationItem[];
  successMessage: string;
}

function sortByTitle(rows: AllocationRow[]): AllocationRow[] {
  return rows
    .slice()
    .sort((a, b) => a.title.localeCompare(b.title));
}

export function AllocationAssistant({
  requirements,
  elements,
  allocateBulk,
  suggestArchitecture,
  canEdit,
}: AllocationAssistantProps): JSX.Element {
  const { t } = useTranslation();
  const [selectedIds, setSelectedIds] = useState<Set<string>>(
    () => new Set()
  );
  const [pickerOpen, setPickerOpen] = useState(false);
  const [pickerQuery, setPickerQuery] = useState("");
  const [suggestions, setSuggestions] = useState<SuggestionGroup[]>([]);
  const [suggestionsLoading, setSuggestionsLoading] = useState(false);
  const [pendingWrite, setPendingWrite] = useState<PendingWrite | null>(null);
  const [error, setError] = useState<{ code: string; message: string } | null>(
    null
  );
  const [notice, setNotice] = useState<string | null>(null);

  const elementById = useMemo(
    () => new Map(elements.map((element) => [element.id, element])),
    [elements]
  );

  const selectableIds = useMemo(() => {
    const ids = new Set<string>();
    for (const row of requirements) {
      if (!isRowLocked(row.locked)) ids.add(row.id);
    }
    return ids;
  }, [requirements]);

  const selectedRows = useMemo(
    () =>
      requirements.filter(
        (row) => selectedIds.has(row.id) && selectableIds.has(row.id)
      ),
    [requirements, selectedIds, selectableIds]
  );

  const selectedRowIds = useMemo(
    () => new Set(selectedRows.map((row) => row.id)),
    [selectedRows]
  );

  const unallocatedRows = useMemo(
    () =>
      sortByTitle(
        requirements.filter(
          (row) => !row.allocated_to && !isRowLocked(row.locked)
        )
      ),
    [requirements]
  );

  const clearError = (): void => {
    setError(null);
    setNotice(null);
  };

  const showFailure = useCallback((err: unknown): void => {
    const info = toAllocationError(err);
    setNotice(null);
    setError({ code: info.code, message: info.message });
  }, []);

  const toggleSelected = (id: string): void => {
    if (!selectableIds.has(id)) return;
    setSuggestions([]);
    setSelectedIds((previous) => {
      const next = new Set(previous);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleAll = (): void => {
    setSuggestions([]);
    if (selectableIds.size > 0 && selectedRows.length === selectableIds.size) {
      setSelectedIds(new Set());
      return;
    }
    setSelectedIds(new Set(selectableIds));
  };

  const pickerElements = useMemo(() => {
    const needle = pickerQuery.trim().toLowerCase();
    return sortByTitle(elements).filter(
      (element) => !needle || element.title.toLowerCase().includes(needle)
    );
  }, [elements, pickerQuery]);

  const runBulk = async (
    items: BulkAllocationItem[],
    successMessage: string
  ): Promise<boolean> => {
    clearError();
    try {
      await allocateBulk(items);
      setSelectedIds(new Set());
      setSuggestions([]);
      setNotice(successMessage);
      return true;
    } catch (err) {
      showFailure(err);
      return false;
    }
  };

  const allocateSelection = async (element: AllocationRow): Promise<void> => {
    if (selectedRows.length === 0) return;
    await runBulk(
      selectedRows.map((row) => ({
        requirement_id: row.id,
        element_id: element.id,
      })),
      t("connectionView.assistant.allocatedNotice", {
        count: selectedRows.length,
        element: element.title,
      })
    );
    // Close either way so a rejection is visible in the assistant's alert.
    setPickerOpen(false);
    setPickerQuery("");
  };

  const requestSuggestions = async (): Promise<void> => {
    clearError();
    const targets =
      selectedRows.length > 0
        ? selectedRows.filter((row) => !row.allocated_to)
        : unallocatedRows;
    if (targets.length === 0) {
      setNotice(t("connectionView.assistant.suggestEmpty"));
      return;
    }

    setSuggestionsLoading(true);
    setSuggestions([]);
    const groups: SuggestionGroup[] = [];
    let firstFailure: unknown = null;
    for (const requirement of targets) {
      try {
        const response = await suggestArchitecture(requirement.id);
        const candidates = toArchitectureSuggestions(response)
          .map((candidate, index) => {
            const element = elementById.get(candidate.element_id);
            if (!element) return null;
            return {
              element,
              reason:
                candidate.reason ??
                t("connectionView.assistant.suggestionReason", {
                  rank: index + 1,
                }),
            };
          })
          .filter(
            (candidate): candidate is { element: AllocationRow; reason: string } =>
              candidate !== null
          );
        if (candidates.length > 0) {
          groups.push({ requirement, candidates });
        }
      } catch (err) {
        if (!firstFailure) firstFailure = err;
      }
    }
    setSuggestionsLoading(false);
    setSuggestions(groups);
    if (groups.length === 0 && !firstFailure) {
      setNotice(t("connectionView.assistant.suggestEmpty"));
    }
    if (firstFailure) showFailure(firstFailure);
  };

  const requestSingleSuggestion = (
    group: SuggestionGroup,
    index: number
  ): void => {
    const candidate = group.candidates[index];
    if (!candidate) return;
    setPendingWrite({
      items: [
        { requirement_id: group.requirement.id, element_id: candidate.element.id },
      ],
      successMessage: t("connectionView.assistant.suggestionApplied", {
        count: 1,
      }),
    });
  };

  const requestAllSuggestions = (): void => {
    const items: BulkAllocationItem[] = [];
    for (const group of suggestions) {
      const candidate = group.candidates[0];
      if (!candidate) continue;
      items.push({
        requirement_id: group.requirement.id,
        element_id: candidate.element.id,
      });
    }
    if (items.length === 0) return;
    setPendingWrite({
      items,
      successMessage: t("connectionView.assistant.suggestionApplied", {
        count: items.length,
      }),
    });
  };

  const confirmPendingWrite = async (): Promise<void> => {
    if (!pendingWrite) return;
    // Close either way: on failure the assistant's alert (with the server
    // code/message and the all-or-nothing notice) must be visible, not hidden
    // behind the confirmation dialog.
    await runBulk(pendingWrite.items, pendingWrite.successMessage);
    setPendingWrite(null);
  };

  const allSelected =
    selectableIds.size > 0 && selectedRows.length === selectableIds.size;

  return (
    <section
      className={styles.assistant}
      data-testid="allocation-assistant"
      aria-label={t("connectionView.assistant.title")}
    >
      <header className={styles.assistantHeader}>
        <div>
          <h2 className={styles.assistantTitle}>
            {t("connectionView.assistant.title")}
          </h2>
          <p className={styles.assistantHint}>
            {canEdit
              ? t("connectionView.assistant.hint")
              : t("allocationGraph.readOnly")}
          </p>
        </div>
        <div className={styles.assistantActions}>
          <span
            className={styles.assistantCount}
            data-testid="assistant-selection-count"
          >
            {t("connectionView.assistant.selected", {
              count: selectedRows.length,
            })}
          </span>
          <button
            type="button"
            className={`btn-ghost ${styles.actionButton}`}
            data-testid="assistant-select-all"
            aria-pressed={allSelected}
            disabled={!canEdit || requirements.length === 0}
            onClick={toggleAll}
          >
            {t("connectionView.assistant.selectAll")}
          </button>
          <button
            type="button"
            className={`btn-ghost ${styles.actionButton}`}
            data-testid="assistant-allocate"
            disabled={!canEdit || selectedRows.length === 0}
            onClick={() => {
              clearError();
              setPickerQuery("");
              setPickerOpen(true);
            }}
          >
            {t("connectionView.allocateTo")}
          </button>
          <button
            type="button"
            className={`btn-ghost ${styles.actionButton}`}
            data-testid="assistant-suggest"
            disabled={!canEdit || suggestionsLoading}
            onClick={() => void requestSuggestions()}
          >
            {t("connectionView.assistant.suggest")}
          </button>
        </div>
      </header>

      {error && (
        <div
          role="alert"
          className={styles.error}
          data-testid="assistant-error"
          data-error-code={error.code}
        >
          <span className={styles.errorCode} data-testid="assistant-error-code">
            {error.code}
          </span>
          <span data-testid="assistant-error-message">{error.message}</span>
          <span className={styles.assistantNothingWritten}>
            {t("connectionView.assistant.nothingWritten")}
          </span>
        </div>
      )}

      {notice && (
        <p
          role="status"
          className={styles.status}
          data-testid="assistant-notice"
        >
          {notice}
        </p>
      )}

      <ul className={styles.assistantList}>
        {requirements.length === 0 ? (
          <li className={styles.status} data-testid="assistant-empty">
            {t("connectionView.empty")}
          </li>
        ) : (
          requirements.map((row) => {
            const lockedState = lockStateName(row.locked);
            const locked = isRowLocked(row.locked);
            const checked = selectedRowIds.has(row.id);
            return (
              <li
                key={row.id}
                className={styles.assistantRow}
                data-testid={`assistant-row-${row.id}`}
                data-locked={locked ? "true" : "false"}
              >
                <input
                  type="checkbox"
                  id={`assistant-check-${row.id}`}
                  data-testid={`assistant-check-${row.id}`}
                  checked={checked}
                  disabled={locked || !canEdit}
                  onChange={() => toggleSelected(row.id)}
                />
                <label
                  htmlFor={`assistant-check-${row.id}`}
                  className={styles.assistantRowTitle}
                >
                  {row.title}
                </label>
                {row.allocated_to && (
                  <span className={styles.badge}>
                    {elementById.get(row.element_id ?? "")
                      ?.title ?? t("connectionView.allocated")}
                  </span>
                )}
                {locked && (
                  <span
                    className={styles.lockIcon}
                    data-testid={`assistant-lock-${row.id}`}
                    title={lockedState ?? t("connectionView.locked")}
                    aria-label={t("connectionView.assistant.lockedTooltip", {
                      state: lockedState ?? t("connectionView.locked"),
                    })}
                  >
                    <Lock aria-hidden="true" size={14} />
                    {lockedState && (
                      <span className={styles.lockState}>{lockedState}</span>
                    )}
                  </span>
                )}
              </li>
            );
          })
        )}
      </ul>

      {suggestionsLoading && (
        <p className={styles.status} data-testid="assistant-suggest-loading">
          {t("connectionView.assistant.suggestLoading")}
        </p>
      )}

      {suggestions.length > 0 && (
        <div
          className={styles.suggestionPanel}
          data-testid="assistant-suggestions"
        >
          <div className={styles.suggestionHeader}>
            <h3 className={styles.assistantTitle}>
              {t("connectionView.assistant.suggestionsTitle")}
            </h3>
            <button
              type="button"
              className={`btn-ghost ${styles.actionButton}`}
              data-testid="assistant-accept-all"
              onClick={requestAllSuggestions}
            >
              {t("connectionView.assistant.acceptAll")}
            </button>
          </div>
          <ul className={styles.suggestionList}>
            {suggestions.map((group) => (
              <li
                key={group.requirement.id}
                className={styles.suggestionRow}
                data-testid={`assistant-suggestion-${group.requirement.id}`}
              >
                <span className={styles.assistantRowTitle}>
                  {group.requirement.title}
                </span>
                <ul className={styles.suggestionCandidates}>
                  {group.candidates.map((candidate, index) => (
                    <li
                      key={candidate.element.id}
                      className={styles.suggestionCandidate}
                      data-testid={`assistant-candidate-${group.requirement.id}-${candidate.element.id}`}
                    >
                      <span className={styles.suggestionTarget}>
                        {candidate.element.title}
                      </span>
                      <span
                        className={styles.suggestionReason}
                        data-testid={`assistant-reason-${group.requirement.id}-${candidate.element.id}`}
                      >
                        {candidate.reason}
                      </span>
                      <button
                        type="button"
                        className={`btn-ghost ${styles.actionButton}`}
                        data-testid={`assistant-accept-${group.requirement.id}-${candidate.element.id}`}
                        onClick={() => requestSingleSuggestion(group, index)}
                      >
                        {t("connectionView.assistant.accept")}
                      </button>
                    </li>
                  ))}
                </ul>
              </li>
            ))}
          </ul>
        </div>
      )}

      {pickerOpen && (
        <Dialog
          title={t("connectionView.assistant.pickerTitle", {
            count: selectedRows.length,
          })}
          onClose={() => {
            setPickerOpen(false);
            setPickerQuery("");
          }}
          testId="assistant-element-picker"
        >
          <input
            type="search"
            className={styles.pickerSearch}
            data-testid="assistant-element-picker-search"
            placeholder={t("connectionView.pickerSearch")}
            aria-label={t("connectionView.pickerSearch")}
            value={pickerQuery}
            onChange={(event) => setPickerQuery(event.target.value)}
          />
          {pickerElements.length === 0 ? (
            <p className={styles.status} data-testid="assistant-element-picker-empty">
              {t("connectionView.pickerEmpty")}
            </p>
          ) : (
            <ul className={styles.pickerList}>
              {pickerElements.map((element) => (
                <li key={element.id}>
                  <button
                    type="button"
                    className={`btn-ghost ${styles.pickerOption}`}
                    data-testid={`assistant-element-picker-option-${element.id}`}
                    onClick={() => void allocateSelection(element)}
                  >
                    {element.title}
                    {isRowLocked(element.locked) && (
                      <span
                        className={styles.lockIcon}
                        title={
                          lockStateName(element.locked) ??
                          t("connectionView.locked")
                        }
                        aria-label={t(
                          "connectionView.assistant.lockedTooltip",
                          {
                            state:
                              lockStateName(element.locked) ??
                              t("connectionView.locked"),
                          }
                        )}
                      >
                        <Lock aria-hidden="true" size={12} />
                      </span>
                    )}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Dialog>
      )}

      {pendingWrite && (
        <Dialog
          title={t("connectionView.assistant.confirmTitle")}
          onClose={() => setPendingWrite(null)}
          testId="assistant-suggestion-confirm"
        >
          <p>{t("connectionView.assistant.confirmHint")}</p>
          <ul className={styles.pendingList}>
            {pendingWrite.items.map((item) => {
              const requirement = requirements.find(
                (row) => row.id === item.requirement_id
              );
              const element = elementById.get(item.element_id);
              return (
                <li
                  key={`${item.requirement_id}-${item.element_id}`}
                  data-testid={`assistant-pending-${item.requirement_id}-${item.element_id}`}
                >
                  {requirement?.title ?? item.requirement_id} →{" "}
                  {element?.title ?? item.element_id}
                </li>
              );
            })}
          </ul>
          <div className={styles.assistantActions}>
            <button
              type="button"
              className={`btn-ghost ${styles.actionButton}`}
              data-testid="assistant-confirm-cancel"
              onClick={() => setPendingWrite(null)}
            >
              {t("connectionView.assistant.cancel")}
            </button>
            <button
              type="button"
              className={`btn-primary ${styles.actionButton}`}
              data-testid="assistant-confirm-write"
              onClick={() => void confirmPendingWrite()}
            >
              {t("connectionView.assistant.confirm")}
            </button>
          </div>
        </Dialog>
      )}
    </section>
  );
}
