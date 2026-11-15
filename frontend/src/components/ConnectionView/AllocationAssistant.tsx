/**
 * P3 Task 3.5 / P4.4 / V.4 — the allocation action bar.
 *
 * V.4 makes the assistant **presentational**: the second requirement list is
 * gone, and the selection lives in the page-level `useAllocationSelection` hook
 * (V.3), shared with the tree renderer's checkboxes. There is exactly one
 * selection in the connection view — ticking a row in the tree and reading the
 * counter in this bar are the same state, never two parallel ones.
 *
 * The bar therefore always shows its four controls:
 *
 * - the selection counter (`assistant-selection-count`);
 * - "Alle auswählen" (`assistant-select-all`) — adds every visible, unlocked
 *   row; hidden ticks are preserved by the hook;
 * - "Allokieren auf …" (`assistant-allocate`) — disabled without a selection;
 *   opens the shared element picker and sends **one** atomic
 *   `POST /trace-links/bulk/` for the whole selection. The endpoint is
 *   all-or-nothing, so a failure means nothing was written and the UI says so;
 * - "Vorschläge" (`assistant-suggest`) — always active; without a selection it
 *   works over all unallocated requirements (the pre-V.4 behaviour), with a
 *   selection over the selected rows. The answer is ephemeral and is written
 *   only after an explicit confirmation in the dialog.
 *
 * Frozen requirements are not selectable (the hook enforces that, this file
 * only renders the lock icon in the picker for frozen elements, which stay
 * valid targets).
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
import type { AllocationSelection } from "./useAllocationSelection";
import styles from "./ConnectionView.module.css";

/** One error shape for the bar's `role="alert"` surface. */
export interface AllocationAssistantError {
  code: string;
  message: string;
}

export interface AllocationAssistantProps {
  /**
   * Page-level selection (V.3). The bar never keeps its own selection state.
   */
  selection: AllocationSelection;
  /** Requirement rows after the active filters (suggestion fallback + labels). */
  requirements: AllocationRow[];
  /** Full element catalogue (picker + suggestion target titles). */
  elements: AllocationRow[];
  /** Atomic all-or-nothing write path. */
  allocateBulk: (items: BulkAllocationItem[]) => Promise<BulkAllocationResult>;
  /** Ephemeral LLM suggestion (persists nothing). */
  suggestArchitecture: (
    requirementId: string
  ) => Promise<SuggestArchitectureResponse>;
  /** Write authority; false keeps the picker closed and the rows untouchable. */
  canEdit: boolean;
  /**
   * Optional page-level error (e.g. a read/write failure owned by the page).
   * Rendered in the same alert surface as the bar's own write failures.
   */
  error?: AllocationAssistantError | null;
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
  selection,
  requirements,
  elements,
  allocateBulk,
  suggestArchitecture,
  canEdit,
  error: pageError = null,
}: AllocationAssistantProps): JSX.Element {
  const { t } = useTranslation();
  const [pickerOpen, setPickerOpen] = useState(false);
  const [pickerQuery, setPickerQuery] = useState("");
  const [suggestions, setSuggestions] = useState<SuggestionGroup[]>([]);
  const [suggestionsLoading, setSuggestionsLoading] = useState(false);
  const [pendingWrite, setPendingWrite] = useState<PendingWrite | null>(null);
  const [writeError, setWriteError] =
    useState<AllocationAssistantError | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const selectedRows = selection.selectedRows;
  const selectedCount = selectedRows.length;

  const elementById = useMemo(
    () => new Map(elements.map((element) => [element.id, element])),
    [elements]
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
    setWriteError(null);
    setNotice(null);
  };

  const showFailure = useCallback((err: unknown): void => {
    const info = toAllocationError(err);
    setNotice(null);
    setWriteError({ code: info.code, message: info.message });
  }, []);

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
      // The page owns the selection; a successful bulk write consumes it.
      selection.clear();
      setSuggestions([]);
      setNotice(successMessage);
      return true;
    } catch (err) {
      showFailure(err);
      return false;
    }
  };

  const allocateSelection = async (element: AllocationRow): Promise<void> => {
    if (selectedCount === 0) return;
    await runBulk(
      selectedRows.map((row) => ({
        requirement_id: row.id,
        element_id: element.id,
      })),
      t("connectionView.assistant.allocatedNotice", {
        count: selectedCount,
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
      selectedCount > 0
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
    selection.selectableIds.size > 0 &&
    selectedCount === selection.selectableIds.size;

  const shownError = writeError ?? pageError ?? null;

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
            {t("connectionView.assistant.selected", { count: selectedCount })}
          </span>
          <button
            type="button"
            className={`btn-ghost ${styles.actionButton}`}
            data-testid="assistant-select-all"
            aria-pressed={allSelected}
            disabled={!canEdit || selection.selectableIds.size === 0}
            onClick={() => {
              clearError();
              selection.selectAll();
            }}
          >
            {t("connectionView.assistant.selectAll")}
          </button>
          <button
            type="button"
            className={`btn-ghost ${styles.actionButton}`}
            data-testid="assistant-allocate"
            disabled={!canEdit || selectedCount === 0}
            onClick={() => {
              clearError();
              setPickerQuery("");
              setPickerOpen(true);
            }}
          >
            {t("connectionView.allocateTo")}
          </button>
          {/* Suggestions are an ephemeral read: they stay available without a
              write role (and without a selection, over all unallocated rows). */}
          <button
            type="button"
            className={`btn-ghost ${styles.actionButton}`}
            data-testid="assistant-suggest"
            disabled={suggestionsLoading}
            onClick={() => void requestSuggestions()}
          >
            {t("connectionView.assistant.suggest")}
          </button>
        </div>
      </header>

      {shownError && (
        <div
          role="alert"
          className={styles.error}
          data-testid="assistant-error"
          data-error-code={shownError.code}
        >
          <span className={styles.errorCode} data-testid="assistant-error-code">
            {shownError.code}
          </span>
          <span data-testid="assistant-error-message">{shownError.message}</span>
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
            count: selectedCount,
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
