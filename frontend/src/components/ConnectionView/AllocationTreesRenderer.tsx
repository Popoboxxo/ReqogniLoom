/**
 * ARCH-L1-001 ReactFrontend — connection view "Bäume" renderer (V.3).
 *
 * Two hierarchies side by side — requirements on the left, architecture
 * elements on the right — plus allocation edges drawn across the corridor
 * between them. The renderer is **additive**: it is one more view mode next to
 * `Baum` / `Zwei Spalten` / `Matrix` / `Graph`, and every existing mode keeps
 * working untouched.
 *
 * Layout contract (plan V.3):
 *
 * - **one** scroll container holds both columns (no scroll sync); each column
 *   is a `<section aria-label>` with a heading, rows are `<li>`, a subtree is
 *   `<ul role="group" aria-labelledby>` and it is expanded through a
 *   `<button aria-expanded aria-controls>`.
 * - The hierarchy comes from the pure `buildRequirementTree` (V.1), reused for
 *   the element column too: both hierarchies are `parent_id` links over
 *   Artifact ids with `sort_key` ordering. The edges come from
 *   `buildAllocationEdges` (V.1) and their SVG paths from `buildEdgePaths`
 *   (V.2) — no geometry lives in this file.
 * - The corridor is measured, not guessed: `useLayoutEffect` reads
 *   `getBoundingClientRect()` for every mounted row (`[data-alloc-row]`) and
 *   for the two column boxes, and re-measures on `scroll`, `resize`,
 *   expand/collapse and filter change. Scroll/resize go through
 *   `requestAnimationFrame`, so a burst of scroll events costs one measurement
 *   per frame.
 * - Only **mounted** rows are measured. A collapsed subtree therefore draws no
 *   edge, which is the intended behaviour (design §S9) — and the reason every
 *   requirement row carries its target text even with `showEdges={false}`.
 *
 * Accessibility baseline (not a WCAG verdict — that belongs to
 * `accessibility-specialist`):
 *
 * - Semantic lists and real `<button>`s; the disclosure is the APG
 *   disclosure pattern (`aria-expanded` + `aria-controls` + a `role="group"`
 *   subtree labelled by the row title), deliberately **not** the `tree` widget
 *   pattern, which would demand arrow-key navigation this renderer does not
 *   implement.
 * - The collapsed subtree stays in the DOM (`hidden`) so `aria-controls`
 *   always resolves to a real element; it is skipped during measurement
 *   because a `display: none` row has no box.
 * - Selection is a real checkbox with a `<label>`, frozen rows disable it.
 *
 * Page-level state: loading and read failures stay with `ConnectionView`, which
 * renders its own loading/status/error surface above the renderer. What this
 * file owns is the write path's failure (`allocation-error`) — the same contract
 * the other renderers follow.
 */

import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type DragEvent,
} from "react";
import { useTranslation } from "react-i18next";
import { ChevronRight, Lock, X } from "lucide-react";

import type { AllocationRow } from "../../api/allocation-view";
import { isRowLocked, lockStateName } from "../../utils/allocation";
import { toAllocationError } from "../AllocationGraph/errors";
import {
  buildAllocationEdges,
  buildRequirementTree,
  type AllocationRequirementNode,
} from "./allocation-trees";
import { buildEdgePaths, type RowRect } from "./edge-geometry";
import type { AllocationSelection } from "./useAllocationSelection";
import styles from "./AllocationTreesRenderer.module.css";

export interface AllocationTreesRendererProps {
  /** Requirement rows after the active filters (the left tree). */
  requirements: AllocationRow[];
  /** Element rows of the element read (the right tree). */
  elements: AllocationRow[];
  /** Selection state owned by the page (shared with the action bar later). */
  selection: AllocationSelection;
  /** Whether the edge overlay is drawn; the target text is always rendered. */
  showEdges: boolean;
  /** Atomic allocate/re-allocate, both arguments are **entity** ids. */
  onAllocate: (requirementId: string, elementId: string) => Promise<void>;
  /** Deallocate by the `allocated-to` TraceLink id. */
  onDeallocate: (allocationTraceLinkId: string) => Promise<void>;
  /** Write authority: without it rows are neither draggable nor tickable. */
  canEdit: boolean;
}

/** `EdgePath.id` is documented as `allocation:<requirementId>` (V.2). */
const EDGE_ID_PREFIX = "allocation:";

/** Stable hook for the measurement walk. */
const ROW_SELECTOR = "[data-alloc-row]";

function requirementIdOfPath(pathId: string): string {
  return pathId.startsWith(EDGE_ID_PREFIX)
    ? pathId.slice(EDGE_ID_PREFIX.length)
    : pathId;
}

export function AllocationTreesRenderer({
  requirements,
  elements,
  selection,
  showEdges,
  onAllocate,
  onDeallocate,
  canEdit,
}: AllocationTreesRendererProps): JSX.Element {
  const { t } = useTranslation();

  const scrollRef = useRef<HTMLDivElement | null>(null);
  const canvasRef = useRef<HTMLDivElement | null>(null);
  const requirementColumnRef = useRef<HTMLElement | null>(null);
  const elementColumnRef = useRef<HTMLElement | null>(null);
  const frameRef = useRef<number | null>(null);

  /** Collapsed subtrees are listed, so the default (expanded) needs no state. */
  const [collapsedIds, setCollapsedIds] = useState<ReadonlySet<string>>(
    () => new Set<string>()
  );
  const [draggingRequirementId, setDraggingRequirementId] = useState<
    string | null
  >(null);
  const [dropTargetId, setDropTargetId] = useState<string | null>(null);
  const [error, setError] = useState<{ code: string; message: string } | null>(
    null
  );
  const [edgePaths, setEdgePaths] = useState<
    Array<{ requirementId: string; d: string }>
  >([]);

  const requirementRoots = useMemo(
    () => buildRequirementTree(requirements),
    [requirements]
  );
  const elementRoots = useMemo(
    () => buildRequirementTree(elements),
    [elements]
  );
  const edges = useMemo(
    () => buildAllocationEdges(requirements, elements),
    [requirements, elements]
  );

  /** `allocated_to` carries the element's **Artifact** id (V.1 contract). */
  const targetTitleByArtifact = useMemo(() => {
    const map = new Map<string, string>();
    for (const element of elements) {
      const artifactId = element.artifact_id;
      // Artifact id first (the read object's contract); the entity id is a
      // fallback so an older payload is not mislabelled "outside the filter".
      if (artifactId && !map.has(artifactId)) {
        map.set(artifactId, element.title);
      }
      if (!map.has(element.id)) map.set(element.id, element.title);
    }
    return map;
  }, [elements]);

  const measure = useCallback((): void => {
    if (!showEdges) {
      setEdgePaths([]);
      return;
    }
    const canvas = canvasRef.current;
    if (!canvas) {
      setEdgePaths([]);
      return;
    }
    const canvasRect = canvas.getBoundingClientRect();
    const from = new Map<string, RowRect>();
    const to = new Map<string, RowRect>();

    for (const node of Array.from(
      canvas.querySelectorAll<HTMLElement>(ROW_SELECTOR)
    )) {
      const id = node.dataset.allocRow;
      if (!id) continue;
      // A collapsed subtree stays in the DOM for `aria-controls` but has no
      // box; measuring it would draw an edge to y=0.
      if (node.closest("[hidden]")) continue;
      const rect = node.getBoundingClientRect();
      const entry: RowRect = {
        top: rect.top - canvasRect.top,
        height: rect.height,
      };
      const side = node.dataset.allocKind;
      if (side === "requirement") {
        if (!from.has(id)) from.set(id, entry);
      } else if (side === "element") {
        if (!to.has(id)) to.set(id, entry);
      }
    }

    const requirementColumn = requirementColumnRef.current;
    const elementColumn = elementColumnRef.current;
    const x1 = requirementColumn
      ? requirementColumn.getBoundingClientRect().right - canvasRect.left
      : 0;
    const x2 = elementColumn
      ? elementColumn.getBoundingClientRect().left - canvasRect.left
      : x1;

    setEdgePaths(
      buildEdgePaths(edges, from, to, { x1, x2 }).map((path) => ({
        requirementId: requirementIdOfPath(path.id),
        d: path.d,
      }))
    );
  }, [edges, showEdges]);

  // Layout effect: the rows are in the DOM, so their boxes are the ones the
  // overlay has to match. Re-runs on expand/collapse, filter change and a
  // showEdges toggle — i.e. on every change that moves a row.
  useLayoutEffect(() => {
    measure();
  }, [measure, requirements, elements, collapsedIds]);

  /** Scroll/resize are throttled to one measurement per animation frame. */
  const scheduleMeasure = useCallback((): void => {
    if (
      typeof window === "undefined" ||
      typeof window.requestAnimationFrame !== "function"
    ) {
      measure();
      return;
    }
    if (frameRef.current !== null) return;
    frameRef.current = window.requestAnimationFrame(() => {
      frameRef.current = null;
      measure();
    });
  }, [measure]);

  useEffect(() => {
    const scroll = scrollRef.current;
    if (!scroll) return;
    scroll.addEventListener("scroll", scheduleMeasure, { passive: true });
    window.addEventListener("resize", scheduleMeasure);
    return () => {
      scroll.removeEventListener("scroll", scheduleMeasure);
      window.removeEventListener("resize", scheduleMeasure);
    };
  }, [scheduleMeasure]);

  useEffect(
    () => () => {
      if (frameRef.current !== null) {
        window.cancelAnimationFrame(frameRef.current);
        frameRef.current = null;
      }
    },
    []
  );

  const run = async (action: () => Promise<void>): Promise<void> => {
    setError(null);
    try {
      await action();
    } catch (err) {
      const info = toAllocationError(err);
      setError({ code: info.code, message: info.message });
    }
  };

  const toggleCollapsed = (id: string): void => {
    setCollapsedIds((previous) => {
      const next = new Set(previous);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const handleDragStart = (
    row: AllocationRow,
    event: DragEvent<HTMLElement>
  ): void => {
    if (!canEdit || isRowLocked(row.locked)) {
      event.preventDefault();
      return;
    }
    // `text/plain` is the row's **entity** id, the value the bulk endpoint
    // expects (`requirement_id`), matching the other renderers.
    event.dataTransfer?.setData("text/plain", row.id);
    if (event.dataTransfer) event.dataTransfer.effectAllowed = "move";
    setDraggingRequirementId(row.id);
  };

  const handleDropOnElement = (
    elementId: string,
    event: DragEvent<HTMLElement>
  ): void => {
    event.preventDefault();
    const requirementId =
      event.dataTransfer?.getData("text/plain") || draggingRequirementId;
    setDraggingRequirementId(null);
    setDropTargetId(null);
    if (!canEdit || !requirementId) return;
    const requirement = requirements.find((row) => row.id === requirementId);
    if (!requirement || isRowLocked(requirement.locked)) return;
    void run(() => onAllocate(requirementId, elementId));
  };

  const renderRowChrome = (
    row: AllocationRow,
    expanded: boolean,
    hasChildren: boolean,
    subtreeId: string,
    labelId: string
  ): JSX.Element => {
    if (!hasChildren) {
      // Same inline size as the toggle so titles line up across levels.
      return <span className={styles.expanderSpacer} aria-hidden="true" />;
    }
    return (
      <button
        type="button"
        className={`btn-ghost ${styles.expander}`}
        aria-expanded={expanded}
        aria-controls={subtreeId}
        aria-labelledby={labelId}
        data-testid={`alloc-expand-${row.id}`}
        onClick={() => toggleCollapsed(row.id)}
      >
        <ChevronRight
          aria-hidden="true"
          size={14}
          className={expanded ? styles.iconOpen : styles.icon}
        />
      </button>
    );
  };

  const renderRequirementNode = (
    node: AllocationRequirementNode
  ): JSX.Element => {
    const row = node.row;
    const locked = isRowLocked(row.locked);
    const lockedState = lockStateName(row.locked);
    const expanded = !collapsedIds.has(row.id);
    const hasChildren = node.children.length > 0;
    const selected = selection.isSelected(row.id);
    const labelId = `alloc-label-${row.id}`;
    const subtreeId = `alloc-subtree-${row.id}`;
    const targetTitle = row.allocated_to
      ? targetTitleByArtifact.get(row.allocated_to) ?? null
      : null;
    // `allocated_to` set but no element in the rendered set: the row is assigned
    // to something the current element filter hides — "outside the filter", not
    // "unallocated" (design §5.3/§5.6).
    const targetExternal = Boolean(row.allocated_to) && targetTitle === null;

    return (
      <li
        key={row.id}
        data-testid={`alloc-req-${row.id}`}
        data-locked={locked ? "true" : "false"}
        data-selected={selected ? "true" : "false"}
        className={[
          styles.node,
          selected ? styles.nodeSelected : "",
          locked ? styles.nodeLocked : "",
        ]
          .filter(Boolean)
          .join(" ")}
        draggable={canEdit && !locked}
        onDragStart={(event) => handleDragStart(row, event)}
        onDragEnd={() => setDraggingRequirementId(null)}
      >
        {/*
         * The measured line, not the <li>: the <li> also contains the
         * subtree, so its box would centre an edge on the middle of the whole
         * branch instead of on the row itself.
         */}
        <div
          className={styles.rowLine}
          data-alloc-row={row.id}
          data-alloc-kind="requirement"
        >
          {renderRowChrome(row, expanded, hasChildren, subtreeId, labelId)}
          {!row.allocated_to && (
            <span
              className={styles.unallocatedMarker}
              data-testid={`unallocated-marker-${row.id}`}
              title={t("connectionView.unallocated")}
              aria-hidden="true"
            />
          )}
          <input
            type="checkbox"
            id={`alloc-check-${row.id}`}
            data-testid={`alloc-select-${row.id}`}
            checked={selected}
            disabled={locked || !canEdit}
            onChange={() => selection.toggle(row.id)}
          />
          <label
            htmlFor={`alloc-check-${row.id}`}
            id={labelId}
            className={styles.rowTitle}
            title={row.title}
          >
            {row.title}
          </label>
          {row.tier_name && (
            <span className={styles.badge} data-testid={`alloc-tier-${row.id}`}>
              {row.tier_name}
            </span>
          )}
          {locked && (
            <span
              className={styles.lock}
              data-testid={`alloc-locked-${row.id}`}
              title={lockedState ?? t("connectionView.locked")}
              aria-label={t("connectionView.lockedTooltip", {
                state: lockedState ?? t("connectionView.locked"),
              })}
            >
              <Lock aria-hidden="true" size={12} />
            </span>
          )}
          {canEdit && row.allocation_trace_link_id && (
            <button
              type="button"
              className={`btn-ghost ${styles.rowAction}`}
              data-testid={`alloc-deallocate-${row.id}`}
              aria-label={t("connectionView.trees.deallocate", {
                title: row.title,
              })}
              onClick={() =>
                void run(() =>
                  onDeallocate(row.allocation_trace_link_id as string)
                )
              }
            >
              <X aria-hidden="true" size={12} />
            </button>
          )}
          {/* Last in the row: the target text is the column that sits next to
              the corridor, so the eye can follow the edge back to the row. */}
          <span
            className={`${styles.target} ${targetExternal ? styles.targetExternal : ""}`}
            data-testid={
              targetExternal
                ? `alloc-target-external-${row.id}`
                : `alloc-target-${row.id}`
            }
            data-external={targetExternal ? "true" : "false"}
            title={
              targetExternal
                ? t("connectionView.targetExternal")
                : targetTitle ?? t("connectionView.unallocated")
            }
          >
            {targetExternal
              ? t("connectionView.targetExternal")
              : targetTitle ?? t("connectionView.unallocated")}
          </span>
        </div>
        {hasChildren && (
          <ul
            id={subtreeId}
            role="group"
            aria-labelledby={labelId}
            className={styles.subtree}
            hidden={!expanded}
          >
            {node.children.map(renderRequirementNode)}
          </ul>
        )}
      </li>
    );
  };

  const renderElementNode = (node: AllocationRequirementNode): JSX.Element => {
    const row = node.row;
    const locked = isRowLocked(row.locked);
    const expanded = !collapsedIds.has(row.id);
    const hasChildren = node.children.length > 0;
    const isDropTarget = dropTargetId === row.id;
    const labelId = `alloc-label-${row.id}`;
    const subtreeId = `alloc-subtree-${row.id}`;

    return (
      <li
        key={row.id}
        data-testid={`alloc-el-${row.id}`}
        data-drop-target={isDropTarget ? "true" : "false"}
        className={isDropTarget ? styles.nodeDropTarget : styles.node}
        onDragOver={(event) => {
          if (!canEdit) return;
          event.preventDefault();
          if (draggingRequirementId) setDropTargetId(row.id);
        }}
        onDragLeave={() => setDropTargetId(null)}
        onDrop={(event) => handleDropOnElement(row.id, event)}
      >
        {/* Measured line only — see the requirement row's comment. */}
        <div
          className={styles.rowLine}
          data-alloc-row={row.id}
          data-alloc-kind="element"
        >
          {renderRowChrome(row, expanded, hasChildren, subtreeId, labelId)}
          <span
            id={labelId}
            className={`${styles.rowTitle} ${styles.elementTitle}`}
            title={row.title}
          >
            {row.title}
          </span>
          {row.type && <span className={styles.badge}>{row.type}</span>}
          {locked && (
            <span
              className={styles.lock}
              data-testid={`alloc-el-locked-${row.id}`}
              title={lockStateName(row.locked) ?? t("connectionView.locked")}
              aria-label={t("connectionView.lockedTooltip", {
                state: lockStateName(row.locked) ?? t("connectionView.locked"),
              })}
            >
              <Lock aria-hidden="true" size={12} />
            </span>
          )}
          {/* The element column has no right-aligned column of its own, so the
              type badge stays next to the title instead of drifting to the far
              edge of the 50%-wide column. */}
          <span className={styles.fill} aria-hidden="true" />
        </div>
        {hasChildren && (
          <ul
            id={subtreeId}
            role="group"
            aria-labelledby={labelId}
            className={styles.subtree}
            hidden={!expanded}
          >
            {node.children.map(renderElementNode)}
          </ul>
        )}
      </li>
    );
  };

  return (
    <div className={styles.trees} data-testid="allocation-trees-renderer">
      {error && (
        <div
          role="alert"
          className={styles.error}
          data-testid="allocation-error"
          data-error-code={error.code}
        >
          <span className={styles.errorCode}>{error.code}</span>
          <span>{error.message}</span>
        </div>
      )}

      <div className={styles.scroll} ref={scrollRef} data-testid="trees-scroll">
        <div className={styles.canvas} ref={canvasRef}>
          {showEdges && (
            <svg
              className={styles.edges}
              aria-hidden="true"
              data-testid="allocation-edges"
            >
              {edgePaths.map((path) => (
                <path
                  key={path.requirementId}
                  className={styles.edge}
                  d={path.d}
                  data-testid={`allocation-edge-${path.requirementId}`}
                />
              ))}
            </svg>
          )}

          <section
            className={styles.column}
            aria-label={t("connectionView.requirements")}
            ref={requirementColumnRef}
          >
            <h2 className={styles.columnTitle}>
              {t("connectionView.requirements")}
              <span className={styles.count}>{requirements.length}</span>
            </h2>
            {requirementRoots.length === 0 ? (
              <p className={styles.empty} data-testid="trees-requirements-empty">
                {t("connectionView.empty")}
              </p>
            ) : (
              <ul className={styles.treeList}>
                {requirementRoots.map(renderRequirementNode)}
              </ul>
            )}
          </section>

          <section
            className={styles.column}
            aria-label={t("connectionView.elements")}
            ref={elementColumnRef}
          >
            <h2 className={styles.columnTitle}>
              {t("connectionView.elements")}
              <span className={styles.count}>{elements.length}</span>
            </h2>
            {elementRoots.length === 0 ? (
              <p className={styles.empty} data-testid="trees-elements-empty">
                {t("connectionView.elementsEmpty")}
              </p>
            ) : (
              <ul className={styles.treeList}>
                {elementRoots.map(renderElementNode)}
              </ul>
            )}
          </section>
        </div>
      </div>
    </div>
  );
}
