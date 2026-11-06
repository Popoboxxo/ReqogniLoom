/**
 * P5 Task 5.3/5.4 — interactive allocation card graph.
 *
 * Renders the pure `buildGraph` model with React Flow (dagre geometry already
 * computed by the model) and adds only interaction:
 *
 * - **Ansicht** (default) hides every write handle and passes
 *   `nodesConnectable={false}` — no drag can reach `allocate`.
 * - **Bearbeiten** requires write authority (`canEdit`); dragging from a
 *   requirement's right handle onto an element card calls the atomic bulk
 *   endpoint, which also replaces an existing allocation (N:1 re-allocation).
 *   Frozen requirements have no handle at all.
 * - Clicking a card highlights its hierarchy/allocation edges; collapsing a
 *   card hides its descendants but keeps the aggregate count (the model owns
 *   that, not this component).
 * - "Allokieren auf …" on each requirement card is the keyboard path for the
 *   same write.
 * - A rejected write renders the REST envelope's code AND message verbatim
 *   (lock 409 WORKFLOW_FROZEN, cycle 400 VALIDATION_ERROR, N:1 409 CONFLICT).
 *
 * The graph stores nothing of its own: rows come from the read object, card
 * fields from the preference-backed configuration, and every write goes
 * through the caller's mutation (which invalidates the read object).
 */

import { useCallback, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  Background,
  BackgroundVariant,
  Controls,
  MiniMap,
  ReactFlow,
  ReactFlowProvider,
  type Connection,
  type NodeTypes,
} from "@xyflow/react";

import type { AllocationRow as ApiAllocationRow } from "../../api/allocation-view";
import { Dialog } from "../shared/Dialog";
import { AllocationCard } from "./AllocationCard";
import {
  buildGraph,
  type AllocationRow as ModelAllocationRow,
} from "./buildGraph";
import {
  defaultCardFieldConfigMap,
  type CardFieldConfigMap,
} from "./cardFields";
import { toAllocationError, type AllocationErrorInfo } from "./errors";
import styles from "./AllocationGraph.module.css";

// Defined once at module scope — React Flow warns on unstable type maps.
const NODE_TYPES: NodeTypes = { allocationCard: AllocationCard };
// Stable default so an absent `cardFields` prop does not invalidate the
// decorated-node memo on every render.
const DEFAULT_CARD_FIELDS = defaultCardFieldConfigMap();

export interface AllocationGraphProps {
  /** Requirements after the active filters, sorted by `sort_key`. */
  requirements: ApiAllocationRow[];
  /** Full element catalogue. */
  elements: ApiAllocationRow[];
  /** Atomic bulk allocate (also replaces an existing allocation). */
  allocate: (requirementId: string, elementId: string) => Promise<void>;
  /** Write authority for the Bearbeiten mode (server enforces regardless). */
  canEdit: boolean;
  /** Preference-backed card fields; defaults are used when omitted. */
  cardFields?: CardFieldConfigMap;
  /** Marks rows that do not match a filter without removing them. */
  dimmed?: (row: ApiAllocationRow) => boolean;
}

function sortElements(elements: ApiAllocationRow[]): ApiAllocationRow[] {
  return elements.slice().sort((a, b) => {
    const keyA = a.sort_key ?? "";
    const keyB = b.sort_key ?? "";
    if (keyA !== keyB) return keyA < keyB ? -1 : 1;
    return a.title.localeCompare(b.title);
  });
}

function GraphCanvas({
  requirements,
  elements,
  allocate,
  canEdit,
  cardFields,
  dimmed,
}: Required<Pick<AllocationGraphProps, "requirements" | "elements" | "allocate" | "canEdit">> &
  Pick<AllocationGraphProps, "cardFields" | "dimmed">): JSX.Element {
  const { t } = useTranslation();
  const [editMode, setEditMode] = useState(false);
  const [collapsed, setCollapsed] = useState<Set<string>>(() => new Set());
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [pickerRequirement, setPickerRequirement] =
    useState<ApiAllocationRow | null>(null);
  const [pickerQuery, setPickerQuery] = useState("");
  const [error, setError] = useState<AllocationErrorInfo | null>(null);

  const fields = cardFields ?? DEFAULT_CARD_FIELDS;
  const writeMode = editMode && canEdit;

  const rows = useMemo(
    () =>
      [...requirements, ...elements] as unknown as ModelAllocationRow[],
    [requirements, elements]
  );

  const model = useMemo(
    () =>
      buildGraph(rows, {
        collapsed,
        dimmed: (row) => dimmed?.(row as unknown as ApiAllocationRow) ?? false,
      }),
    [rows, collapsed, dimmed]
  );

  const allocationCounts = useMemo(() => {
    const counts = new Map<string, number>();
    for (const requirement of requirements) {
      if (!requirement.allocated_to) continue;
      // `allocated_to` is the element's Artifact id; the counts are keyed by
      // the element entity id so the card can look itself up directly.
      const elementKey = requirement.element_id ?? requirement.allocated_to;
      counts.set(elementKey, (counts.get(elementKey) ?? 0) + 1);
    }
    return counts;
  }, [requirements]);

  const run = useCallback(
    async (action: () => Promise<void>): Promise<boolean> => {
      setError(null);
      try {
        await action();
        return true;
      } catch (err) {
        setError(toAllocationError(err));
        return false;
      }
    },
    []
  );

  const toggleCollapse = useCallback((nodeId: string) => {
    setCollapsed((previous) => {
      const next = new Set(previous);
      if (next.has(nodeId)) next.delete(nodeId);
      else next.add(nodeId);
      return next;
    });
  }, []);

  const openAllocator = useCallback((row: ApiAllocationRow) => {
    setPickerQuery("");
    setPickerRequirement(row);
  }, []);

  const decoratedNodes = useMemo(
    () =>
      model.nodes.map((node) => {
        const row = node.data.row as unknown as ApiAllocationRow;
        const allocationCount =
          node.data.kind === "requirement"
            ? row.allocated_to
              ? 1
              : 0
            : (allocationCounts.get(row.id) ?? 0);
        return {
          ...node,
          data: {
            ...node.data,
            editMode: writeMode,
            cardFields:
              node.data.kind === "requirement"
                ? fields.requirement
                : fields.element,
            allocationCount,
            selected: selectedId === node.id,
            onToggleCollapse: toggleCollapse,
            onOpenAllocator: openAllocator,
          },
        };
      }),
    [
      model.nodes,
      writeMode,
      fields,
      allocationCounts,
      selectedId,
      toggleCollapse,
      openAllocator,
    ]
  );

  const decoratedEdges = useMemo(
    () =>
      model.edges.map((edge) => {
        const highlighted =
          selectedId !== null &&
          (edge.source === selectedId || edge.target === selectedId);
        if (!highlighted) return edge;
        return {
          ...edge,
          className: `${edge.className ?? ""} allocationEdge--highlighted`,
          animated: false,
          style: { ...edge.style, strokeWidth: 2.5 },
        };
      }),
    [model.edges, selectedId]
  );

  const handleConnect = useCallback(
    (connection: Connection) => {
      if (!writeMode) return;
      const source = model.nodes.find((node) => node.id === connection.source);
      const target = model.nodes.find((node) => node.id === connection.target);
      if (!source || !target) return;
      if (source.data.kind !== "requirement" || target.data.kind !== "element") {
        return;
      }
      if (source.data.frozen) return;
      const requirement = source.data.row as unknown as ApiAllocationRow;
      const element = target.data.row as unknown as ApiAllocationRow;
      void run(() => allocate(requirement.id, element.id));
    },
    [writeMode, model.nodes, run, allocate]
  );

  const pickerElements = useMemo(() => {
    const needle = pickerQuery.trim().toLowerCase();
    return sortElements(elements).filter(
      (element) => !needle || element.title.toLowerCase().includes(needle)
    );
  }, [elements, pickerQuery]);

  const chooseElement = async (element: ApiAllocationRow): Promise<void> => {
    if (!pickerRequirement) return;
    const requirement = pickerRequirement;
    const ok = await run(() => allocate(requirement.id, element.id));
    if (ok) {
      setPickerRequirement(null);
      setPickerQuery("");
    }
  };

  const canAllocateNow = writeMode;

  return (
    <div className={styles.graph} data-testid="allocation-graph">
      <div className={styles.toolbar}>
        <div
          className={styles.modeSwitcher}
          role="group"
          aria-label={t("allocationGraph.mode")}
        >
          <button
            type="button"
            className={`btn-ghost ${styles.modeButton} ${
              !editMode ? styles.modeButtonActive : ""
            }`}
            data-testid="graph-mode-view"
            aria-pressed={!editMode}
            onClick={() => setEditMode(false)}
          >
            {t("allocationGraph.viewMode")}
          </button>
          <button
            type="button"
            className={`btn-ghost ${styles.modeButton} ${
              editMode ? styles.modeButtonActive : ""
            }`}
            data-testid="graph-mode-edit"
            aria-pressed={editMode}
            disabled={!canEdit}
            title={!canEdit ? t("allocationGraph.readOnly") : undefined}
            onClick={() => setEditMode(true)}
          >
            {t("allocationGraph.editMode")}
          </button>
        </div>
        <p className={styles.modeHint}>
          {canEdit
            ? t("allocationGraph.modeHint")
            : t("allocationGraph.readOnly")}
        </p>
      </div>

      {error && (
        <div
          role="alert"
          className={styles.error}
          data-testid="allocation-graph-error"
          data-error-code={error.code}
        >
          <strong className={styles.errorTitle}>
            {t("allocationGraph.errorTitle")}
          </strong>
          <span
            className={styles.errorCode}
            data-testid="allocation-graph-error-code"
          >
            {error.code}
          </span>
          <span data-testid="allocation-graph-error-message">
            {error.message}
          </span>
        </div>
      )}

      {model.nodes.length === 0 ? (
        <p className={styles.empty} data-testid="allocation-graph-empty">
          {t("allocationGraph.empty")}
        </p>
      ) : (
        <div className={styles.canvas} data-testid="allocation-graph-canvas">
          <ReactFlow
            nodes={decoratedNodes}
            edges={decoratedEdges}
            nodeTypes={NODE_TYPES}
            onNodeClick={(_event, node) => setSelectedId(node.id)}
            onPaneClick={() => setSelectedId(null)}
            onConnect={handleConnect}
            nodesConnectable={canAllocateNow}
            nodesDraggable={false}
            elementsSelectable
            fitView
            fitViewOptions={{ padding: 0.2 }}
            minZoom={0.2}
            maxZoom={2}
            deleteKeyCode={null}
            zoomOnDoubleClick={false}
            proOptions={{ hideAttribution: true }}
          >
            <Background
              variant={BackgroundVariant.Dots}
              gap={20}
              size={1}
              color="var(--color-border)"
            />
            <MiniMap
              pannable
              zoomable
              nodeColor={(node) =>
                node.data?.kind === "requirement"
                  ? "var(--color-primary)"
                  : "var(--color-text-muted)"
              }
            />
            <Controls />
          </ReactFlow>
        </div>
      )}

      {pickerRequirement && (
        <Dialog
          title={t("allocationGraph.pickerTitle", {
            title: pickerRequirement.title,
          })}
          onClose={() => {
            setPickerRequirement(null);
            setPickerQuery("");
          }}
          testId="graph-element-picker"
        >
          <input
            type="search"
            className={styles.pickerSearch}
            data-testid="graph-element-picker-search"
            placeholder={t("allocationGraph.pickerSearch")}
            aria-label={t("allocationGraph.pickerSearch")}
            value={pickerQuery}
            onChange={(event) => setPickerQuery(event.target.value)}
          />
          {pickerElements.length === 0 ? (
            <p className={styles.status} data-testid="graph-element-picker-empty">
              {t("allocationGraph.pickerEmpty")}
            </p>
          ) : (
            <ul className={styles.pickerList}>
              {pickerElements.map((element) => (
                <li key={element.id}>
                  <button
                    type="button"
                    className={`btn-ghost ${styles.pickerOption}`}
                    data-testid={`graph-element-picker-option-${element.id}`}
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

export function AllocationGraph(props: AllocationGraphProps): JSX.Element {
  return (
    <ReactFlowProvider>
      <GraphCanvas {...props} />
    </ReactFlowProvider>
  );
}
