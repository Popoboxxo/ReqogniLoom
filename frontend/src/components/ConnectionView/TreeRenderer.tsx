/**
 * ARCH-L1-001 ReactFrontend — connection view "Baum" renderer (P3 Task 3.3).
 *
 * Architecture tree by `parent_id`/`sort_key` with the requirements allocated
 * to each element as a sub-list and a "Nicht allokiert" block. Interactions:
 *
 * - drag a requirement onto an element -> atomic bulk allocate (re-allocation
 *   included, the backend replaces the existing edge);
 * - drag an allocated requirement onto "Nicht allokiert" -> deallocate;
 * - keyboard path "Allokieren auf …" opens the shared <Dialog> with an element
 *   search;
 * - a frozen requirement (`locked` non-null) is neither draggable nor
 *   allocatable;
 * - a rejected write is shown verbatim in `allocation-error`.
 */

import { useMemo, useState, type DragEvent } from "react";
import { useTranslation } from "react-i18next";

import { extractErrorMessage } from "../../api/client";
import type { AllocationRow } from "../../api/allocation-view";
import { Dialog } from "../shared/Dialog";
import styles from "./ConnectionView.module.css";

export interface AllocationRendererProps {
  requirements: AllocationRow[];
  elements: AllocationRow[];
  allocate: (requirementId: string, elementId: string) => Promise<void>;
  deallocate: (allocationTraceLinkId: string) => Promise<void>;
}

interface ElementNode {
  row: AllocationRow;
  children: ElementNode[];
  requirements: AllocationRow[];
}

function compareElementRows(a: AllocationRow, b: AllocationRow): number {
  const keyA = a.sort_key ?? "";
  const keyB = b.sort_key ?? "";
  if (keyA !== keyB) return keyA < keyB ? -1 : 1;
  return a.title.localeCompare(b.title);
}

function buildElementTree(
  elements: AllocationRow[],
  requirements: AllocationRow[]
): { roots: ElementNode[]; unallocated: AllocationRow[] } {
  const nodes = new Map<string, ElementNode>();
  for (const element of elements) {
    nodes.set(element.id, { row: element, children: [], requirements: [] });
  }
  const roots: ElementNode[] = [];
  for (const element of elements) {
    const node = nodes.get(element.id);
    if (!node) continue;
    const parent =
      element.parent_id && nodes.has(element.parent_id)
        ? nodes.get(element.parent_id)
        : undefined;
    if (parent) parent.children.push(node);
    else roots.push(node);
  }

  const unallocated: AllocationRow[] = [];
  for (const requirement of requirements) {
    const target = requirement.element_id
      ? nodes.get(requirement.element_id)
      : undefined;
    if (target) target.requirements.push(requirement);
    else unallocated.push(requirement);
  }

  const sortNode = (node: ElementNode): void => {
    node.children.sort((a, b) => compareElementRows(a.row, b.row));
    node.requirements.sort((a, b) => compareElementRows(a, b));
    node.children.forEach(sortNode);
  };
  roots.sort((a, b) => compareElementRows(a.row, b.row));
  roots.forEach(sortNode);

  return { roots, unallocated };
}

export function TreeRenderer({
  requirements,
  elements,
  allocate,
  deallocate,
}: AllocationRendererProps): JSX.Element {
  const { t } = useTranslation();
  const [draggingRequirementId, setDraggingRequirementId] = useState<
    string | null
  >(null);
  const [dropTarget, setDropTarget] = useState<string | null>(null);
  const [pickerRequirement, setPickerRequirement] =
    useState<AllocationRow | null>(null);
  const [pickerQuery, setPickerQuery] = useState("");
  const [error, setError] = useState<string | null>(null);

  const { roots, unallocated } = useMemo(
    () => buildElementTree(elements, requirements),
    [elements, requirements]
  );

  const run = async (action: () => Promise<void>): Promise<boolean> => {
    setError(null);
    try {
      await action();
      return true;
    } catch (err) {
      setError(extractErrorMessage(err));
      return false;
    }
  };

  const requirementById = (id: string): AllocationRow | undefined =>
    requirements.find((row) => row.id === id);

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
  };

  const resolveDragged = (event: DragEvent<HTMLElement>): string | null => {
    return event.dataTransfer?.getData("text/plain") || draggingRequirementId;
  };

  const handleDropOnElement = async (
    elementId: string,
    event: DragEvent<HTMLElement>
  ): Promise<void> => {
    event.preventDefault();
    const requirementId = resolveDragged(event);
    setDraggingRequirementId(null);
    setDropTarget(null);
    if (!requirementId) return;
    const requirement = requirementById(requirementId);
    if (!requirement || requirement.locked !== null) return;
    await run(() => allocate(requirementId, elementId));
  };

  const handleDropOnUnallocated = async (
    event: DragEvent<HTMLElement>
  ): Promise<void> => {
    event.preventDefault();
    const requirementId = resolveDragged(event);
    setDraggingRequirementId(null);
    setDropTarget(null);
    if (!requirementId) return;
    const requirement = requirementById(requirementId);
    if (!requirement || requirement.locked !== null) return;
    if (!requirement.allocation_trace_link_id) return;
    await run(() =>
      deallocate(requirement.allocation_trace_link_id as string)
    );
  };

  const pickerElements = useMemo(() => {
    const needle = pickerQuery.trim().toLowerCase();
    return elements
      .slice()
      .sort(compareElementRows)
      .filter(
        (element) =>
          !needle || element.title.toLowerCase().includes(needle)
      );
  }, [elements, pickerQuery]);

  const chooseElement = async (element: AllocationRow): Promise<void> => {
    if (!pickerRequirement) return;
    const requirement = pickerRequirement;
    const ok = await run(() => allocate(requirement.id, element.id));
    if (ok) {
      setPickerRequirement(null);
      setPickerQuery("");
    }
  };

  const renderRequirement = (row: AllocationRow): JSX.Element => {
    const locked = row.locked !== null;
    return (
      <li
        key={row.id}
        data-testid={`req-row-${row.id}`}
        data-locked={locked ? "true" : "false"}
        className={[
          styles.reqRow,
          locked ? styles.reqRowLocked : styles.reqRowDraggable,
        ].join(" ")}
        draggable={!locked}
        onDragStart={(event) => handleDragStart(row, event)}
        onDragEnd={() => setDraggingRequirementId(null)}
      >
        <span className={styles.reqTitle} title={row.title}>
          {row.title}
        </span>
        {row.tier_name && (
          <span className={styles.badge} data-testid={`req-tier-${row.id}`}>
            {row.tier_name}
          </span>
        )}
        {row.state && (
          <span className={styles.badge} data-testid={`req-state-${row.id}`}>
            {row.state}
          </span>
        )}
        {locked && (
          <span className={styles.badge} data-testid={`req-locked-${row.id}`}>
            {t("connectionView.locked")}
          </span>
        )}
        <button
          type="button"
          className={`btn-ghost ${styles.actionButton}`}
          data-testid={`allocate-open-${row.id}`}
          disabled={locked}
          onClick={() => {
            setPickerQuery("");
            setPickerRequirement(row);
          }}
        >
          {t("connectionView.allocateTo")}
        </button>
      </li>
    );
  };

  const renderNode = (node: ElementNode): JSX.Element => {
    const isDropTarget = dropTarget === node.row.id;
    return (
      <li key={node.row.id}>
        {/* A drop target is pointer-only by nature; the keyboard path is the
            "Allokieren auf …" button on every requirement row. */}
        {/* eslint-disable-next-line jsx-a11y/no-static-element-interactions */}
        <div
          className={[
            styles.elementNode,
            isDropTarget ? styles.elementNodeDropTarget : "",
          ]
            .filter(Boolean)
            .join(" ")}
          data-testid={`element-node-${node.row.id}`}
          onDragOver={(event) => {
            event.preventDefault();
            if (draggingRequirementId) setDropTarget(node.row.id);
          }}
          onDragLeave={() => setDropTarget(null)}
          onDrop={(event) => void handleDropOnElement(node.row.id, event)}
        >
          <div className={styles.elementHeader}>
            <span className={styles.elementTitle}>{node.row.title}</span>
            {node.row.type && (
              <span className={styles.badge}>{node.row.type}</span>
            )}
            <span
              className={styles.countBadge}
              data-testid={`element-count-${node.row.id}`}
            >
              {node.requirements.length}
            </span>
          </div>
          {node.requirements.length > 0 && (
            <ul className={styles.reqList}>
              {node.requirements.map(renderRequirement)}
            </ul>
          )}
        </div>
        {node.children.length > 0 && (
          <ul className={styles.treeList}>
            {node.children.map(renderNode)}
          </ul>
        )}
      </li>
    );
  };

  return (
    <div className={styles.tree} data-testid="tree-renderer">
      {error && (
        <div role="alert" className={styles.error} data-testid="allocation-error">
          {error}
        </div>
      )}

      {roots.length === 0 && unallocated.length === 0 ? (
        <p className={styles.empty} data-testid="tree-empty">
          {t("connectionView.empty")}
        </p>
      ) : (
        <ul className={styles.treeList}>
          {roots.map(renderNode)}
        </ul>
      )}

      {/* Pointer drop target; the keyboard path is the picker button on the
          requirement row. */}
      {/* eslint-disable-next-line jsx-a11y/no-static-element-interactions */}
      <section
        className={[
          styles.unallocated,
          dropTarget === "unallocated" ? styles.unallocatedDropTarget : "",
        ]
          .filter(Boolean)
          .join(" ")}
        data-testid="unallocated-block"
        onDragOver={(event) => {
          event.preventDefault();
          if (draggingRequirementId) setDropTarget("unallocated");
        }}
        onDragLeave={() => setDropTarget(null)}
        onDrop={(event) => void handleDropOnUnallocated(event)}
      >
        <h2 className={styles.sectionTitle}>
          {t("connectionView.unallocated")}
          <span
            className={styles.countBadge}
            data-testid="unallocated-count"
          >
            {unallocated.length}
          </span>
        </h2>
        {unallocated.length > 0 ? (
          <ul className={styles.reqList}>
            {unallocated.map(renderRequirement)}
          </ul>
        ) : (
          <p className={styles.status}>
            {t("connectionView.unallocatedEmpty")}
          </p>
        )}
      </section>

      {pickerRequirement && (
        <Dialog
          title={t("connectionView.pickerTitle", {
            title: pickerRequirement.title,
          })}
          onClose={() => {
            setPickerRequirement(null);
            setPickerQuery("");
          }}
          testId="element-picker"
        >
          <input
            type="search"
            className={styles.pickerSearch}
            data-testid="element-picker-search"
            placeholder={t("connectionView.pickerSearch")}
            aria-label={t("connectionView.pickerSearch")}
            value={pickerQuery}
            onChange={(event) => setPickerQuery(event.target.value)}
          />
          {pickerElements.length === 0 ? (
            <p className={styles.status} data-testid="element-picker-empty">
              {t("connectionView.pickerEmpty")}
            </p>
          ) : (
            <ul className={styles.pickerList}>
              {pickerElements.map((element) => (
                <li key={element.id}>
                  <button
                    type="button"
                    className={`btn-ghost ${styles.pickerOption}`}
                    data-testid={`element-picker-option-${element.id}`}
                    onClick={() => void chooseElement(element)}
                  >
                    {element.title}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Dialog>
      )}
    </div>
  );
}
