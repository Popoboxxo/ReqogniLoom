/**
 * ARCH-L1-001 ReactFrontend — connection view "Zwei Spalten" renderer
 * (P3 Task 3.4, renderer A).
 *
 * Requirements on the left, architecture elements on the right. Selecting one
 * side highlights the counterpart(s): a requirement highlights the element it
 * is allocated to, an element highlights every requirement allocated to it.
 * Dragging a requirement from the left onto an element on the right performs
 * the atomic bulk allocate (which also re-allocates).
 */

import { useMemo, useState, type DragEvent } from "react";
import { useTranslation } from "react-i18next";

import { extractErrorMessage } from "../../api/client";
import type { AllocationRow } from "../../api/allocation-view";
import styles from "./ConnectionView.module.css";
import type { AllocationRendererProps } from "./TreeRenderer";

function sortRows(a: AllocationRow, b: AllocationRow): number {
  const keyA = a.sort_key ?? "";
  const keyB = b.sort_key ?? "";
  if (keyA !== keyB) return keyA < keyB ? -1 : 1;
  return a.title.localeCompare(b.title);
}

export function TwoColumnRenderer({
  requirements,
  elements,
  allocate,
}: AllocationRendererProps): JSX.Element {
  const { t } = useTranslation();
  const [selectedRequirementId, setSelectedRequirementId] = useState<
    string | null
  >(null);
  const [selectedElementId, setSelectedElementId] = useState<string | null>(
    null
  );
  const [draggingRequirementId, setDraggingRequirementId] = useState<
    string | null
  >(null);
  const [dropTarget, setDropTarget] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const sortedRequirements = useMemo(
    () => requirements.slice().sort(sortRows),
    [requirements]
  );
  const sortedElements = useMemo(() => elements.slice().sort(sortRows), [elements]);

  const highlightedElementId = selectedRequirementId
    ? sortedRequirements.find((row) => row.id === selectedRequirementId)
        ?.allocated_to ?? null
    : null;

  const handleDragStart = (
    row: AllocationRow,
    event: DragEvent<HTMLElement>
  ): void => {
    if (row.locked !== null) {
      event.preventDefault();
      return;
    }
    event.dataTransfer?.setData("text/plain", row.id);
    if (event.dataTransfer) event.dataTransfer.effectAllowed = "move";
    setDraggingRequirementId(row.id);
    setSelectedRequirementId(row.id);
    setSelectedElementId(null);
  };

  const handleDrop = async (
    elementId: string,
    event: DragEvent<HTMLElement>
  ): Promise<void> => {
    event.preventDefault();
    const requirementId =
      event.dataTransfer?.getData("text/plain") || draggingRequirementId;
    setDraggingRequirementId(null);
    setDropTarget(null);
    if (!requirementId) return;
    const requirement = sortedRequirements.find(
      (row) => row.id === requirementId
    );
    if (!requirement || requirement.locked !== null) return;
    setError(null);
    try {
      await allocate(requirementId, elementId);
    } catch (err) {
      setError(extractErrorMessage(err));
    }
  };

  return (
    <div className={styles.twoColumn} data-testid="two-column-renderer">
      {error && (
        <div
          role="alert"
          className={styles.error}
          data-testid="allocation-error"
        >
          {error}
        </div>
      )}

      <section className={styles.column} aria-label={t("connectionView.requirements")}>
        <h2 className={styles.columnTitle}>{t("connectionView.requirements")}</h2>
        <ul className={styles.columnList}>
          {sortedRequirements.map((row) => {
            const locked = row.locked !== null;
            const highlighted = selectedElementId
              ? row.allocated_to === selectedElementId
              : undefined;
            return (
              <li
                key={row.id}
                data-testid={`twocol-req-${row.id}`}
                data-highlighted={highlighted === undefined ? undefined : String(highlighted)}
                data-locked={locked ? "true" : "false"}
                className={[
                  styles.listItem,
                  highlighted ? styles.listItemHiglighted : "",
                  locked ? styles.reqRowLocked : "",
                ]
                  .filter(Boolean)
                  .join(" ")}
                draggable={!locked}
                onDragStart={(event) => handleDragStart(row, event)}
                onDragEnd={() => setDraggingRequirementId(null)}
              >
                <button
                  type="button"
                  className={`btn-ghost ${styles.savedViewName}`}
                  data-testid={`twocol-req-select-${row.id}`}
                  onClick={() => {
                    setSelectedRequirementId(row.id);
                    setSelectedElementId(null);
                  }}
                >
                  {row.title}
                </button>
              </li>
            );
          })}
        </ul>
      </section>

      <section className={styles.column} aria-label={t("connectionView.elements")}>
        <h2 className={styles.columnTitle}>{t("connectionView.elements")}</h2>
        <ul className={styles.columnList}>
          {sortedElements.map((element) => {
            const highlighted = highlightedElementId === element.id;
            const isDropTarget = dropTarget === element.id;
            return (
              <li
                key={element.id}
                data-testid={`twocol-element-${element.id}`}
                data-highlighted={String(highlighted)}
                className={[
                  styles.listItem,
                  highlighted ? styles.listItemHiglighted : "",
                  isDropTarget ? styles.listItemDropTarget : "",
                ]
                  .filter(Boolean)
                  .join(" ")}
                onDragOver={(event) => {
                  event.preventDefault();
                  if (draggingRequirementId) setDropTarget(element.id);
                }}
                onDragLeave={() => setDropTarget(null)}
                onDrop={(event) => void handleDrop(element.id, event)}
              >
                <button
                  type="button"
                  className={`btn-ghost ${styles.listItemButton}`}
                  data-testid={`twocol-element-select-${element.id}`}
                  onClick={() => {
                    setSelectedElementId(element.id);
                    setSelectedRequirementId(null);
                  }}
                >
                  {element.title}
                </button>
              </li>
            );
          })}
        </ul>
      </section>
    </div>
  );
}
