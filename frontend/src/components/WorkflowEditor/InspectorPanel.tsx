/**
 * REQ-176 — InspectorPanel: right-hand details panel (read-only, Phase 1).
 *
 * Collapsible + resizable (280–400px, persisted under
 * ``reqflow_workflow_inspector_width``) following the RightSidebar pattern.
 * Shows an empty prompt, a State inspector, or a Transition inspector depending
 * on the current selection (design brief §8). Edit actions are Phase 2 and are
 * intentionally absent here.
 */

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
} from "react";
import { useTranslation } from "react-i18next";
import {
  ArrowRight,
  MousePointerClick,
  Pencil,
  Trash2,
  Workflow,
} from "lucide-react";
import type {
  WorkflowGraph,
  WorkflowState,
  WorkflowStateType,
  WorkflowTransition,
} from "../../api/workflows";
import type { Selection } from "./constants";
import styles from "./WorkflowEditor.module.css";

const DEFAULT_WIDTH_PX = 320;
const MIN_WIDTH_PX = 280;
const MAX_WIDTH_PX = 400;
const COLLAPSED_WIDTH_PX = 40;
const WIDTH_KEY = "reqflow_workflow_inspector_width";

const TYPE_BADGE_CLASS: Record<WorkflowStateType, string> = {
  initial: styles.typeBadgeInitial,
  active: styles.typeBadgeActive,
  terminal: styles.typeBadgeTerminal,
  error: styles.typeBadgeError,
};

function readWidth(): number {
  if (typeof window === "undefined") return DEFAULT_WIDTH_PX;
  try {
    const raw = window.localStorage.getItem(WIDTH_KEY);
    if (raw !== null) {
      const n = parseInt(raw, 10);
      if (Number.isFinite(n)) return Math.min(MAX_WIDTH_PX, Math.max(MIN_WIDTH_PX, n));
    }
  } catch {
    /* localStorage may be disabled */
  }
  return DEFAULT_WIDTH_PX;
}

interface InspectorEditActions {
  onEditState: (name: string) => void;
  onDeleteState: (name: string) => void;
  onEditTransition: (fromState: string, toState: string) => void;
  onDeleteTransition: (fromState: string, toState: string) => void;
}

interface InspectorPanelProps {
  graph: WorkflowGraph | null;
  selection: Selection;
  onSelect: (selection: Selection) => void;
  /** REQ-177 — when true the inspector shows Edit/Delete actions. */
  editMode?: boolean;
  edit?: InspectorEditActions;
}

export function InspectorPanel({
  graph,
  selection,
  onSelect,
  editMode = false,
  edit,
}: InspectorPanelProps): JSX.Element {
  const { t } = useTranslation();
  const [collapsed, setCollapsed] = useState(false);
  const [width, setWidth] = useState<number>(readWidth);

  useEffect(() => {
    try {
      window.localStorage.setItem(WIDTH_KEY, String(width));
    } catch {
      /* ignore */
    }
  }, [width]);

  // ---- resize (handle on the left edge; dragging left widens) -------------
  const isResizingRef = useRef(false);
  const startXRef = useRef(0);
  const startWidthRef = useRef(0);

  const onResizeMouseDown = useCallback(
    (e: React.MouseEvent<HTMLDivElement>): void => {
      isResizingRef.current = true;
      startXRef.current = e.clientX;
      startWidthRef.current = width;
      document.body.style.userSelect = "none";
      document.body.style.cursor = "col-resize";
      e.preventDefault();
    },
    [width]
  );

  useEffect(() => {
    function onMove(e: MouseEvent): void {
      if (!isResizingRef.current) return;
      const delta = startXRef.current - e.clientX; // drag left → wider
      const next = Math.max(
        MIN_WIDTH_PX,
        Math.min(MAX_WIDTH_PX, startWidthRef.current + delta)
      );
      setWidth(next);
    }
    function onUp(): void {
      if (!isResizingRef.current) return;
      isResizingRef.current = false;
      document.body.style.userSelect = "";
      document.body.style.cursor = "";
    }
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
  }, []);

  const selectedState = useMemo<WorkflowState | null>(() => {
    if (!graph || selection.kind !== "state") return null;
    return graph.states.find((s) => s.id === selection.id) ?? null;
  }, [graph, selection]);

  const selectedTransition = useMemo<WorkflowTransition | null>(() => {
    if (!graph || selection.kind !== "transition") return null;
    return graph.transitions.find((t) => t.id === selection.id) ?? null;
  }, [graph, selection]);

  const effectiveWidth = collapsed ? COLLAPSED_WIDTH_PX : width;
  const asideStyle: CSSProperties = {
    width: `${effectiveWidth}px`,
    flex: `0 0 ${effectiveWidth}px`,
  };

  if (collapsed) {
    return (
      <aside
        className={styles.inspector}
        style={asideStyle}
        aria-label={t("workflow.inspector.ariaLabelCollapsed")}
        data-testid="workflow-inspector"
      >
        <div className={styles.inspectorCollapsed}>
          <button
            type="button"
            className={styles.iconButton}
            aria-label={t("workflow.inspector.expand")}
            title={t("workflow.inspector.expand")}
            onClick={() => setCollapsed(false)}
            data-testid="workflow-inspector-expand"
          >
            «
          </button>
        </div>
      </aside>
    );
  }

  return (
    <aside
      className={styles.inspector}
      style={asideStyle}
      aria-label={t("workflow.inspector.ariaLabelExpanded")}
      data-testid="workflow-inspector"
    >
      <div
        className={styles.inspectorResize}
        role="separator"
        aria-orientation="vertical"
        aria-label={t("workflow.inspector.resize")}
        onMouseDown={onResizeMouseDown}
        data-testid="workflow-inspector-resize"
      />
      <header className={styles.inspectorHeader}>
        <span className={styles.inspectorTitle}>{t("workflow.inspector.title")}</span>
        <button
          type="button"
          className={styles.iconButton}
          aria-label={t("workflow.inspector.collapse")}
          title={t("workflow.inspector.collapse")}
          onClick={() => setCollapsed(true)}
          data-testid="workflow-inspector-collapse"
        >
          »
        </button>
      </header>

      <div className={styles.inspectorBody} aria-live="polite">
        {selectedState && graph ? (
          <StateInspector
            state={selectedState}
            graph={graph}
            onSelect={onSelect}
            editMode={editMode}
            edit={edit}
          />
        ) : selectedTransition ? (
          <TransitionInspector
            transition={selectedTransition}
            editMode={editMode}
            edit={edit}
          />
        ) : (
          <div className={styles.inspectorEmpty}>
            <Workflow size={32} aria-hidden="true" />
            <div className={styles.overlayText}>
              {t("workflow.inspector.emptyPrompt")}
            </div>
          </div>
        )}
      </div>
    </aside>
  );
}

// ---------------------------------------------------------------------------
// State inspector
// ---------------------------------------------------------------------------

function StateInspector({
  state,
  graph,
  onSelect,
  editMode,
  edit,
}: {
  state: WorkflowState;
  graph: WorkflowGraph;
  onSelect: (selection: Selection) => void;
  editMode: boolean;
  edit?: InspectorEditActions;
}): JSX.Element {
  const { t } = useTranslation();
  const outgoing = graph.transitions.filter((tr) => tr.from_state === state.id);
  const incoming = graph.transitions.filter((tr) => tr.to_state === state.id);

  return (
    <div data-testid="workflow-inspector-state">
      <div className={styles.inspectorStateHeader}>
        <span className={styles.stateDot} aria-hidden="true" />
        <span className={styles.inspectorStateName}>{state.name}</span>
        <span className={`${styles.typeBadge} ${TYPE_BADGE_CLASS[state.type]}`}>
          {state.type}
        </span>
      </div>

      <div className={styles.sectionLabel}>
        {t("workflow.inspector.outgoingTransitions", { count: outgoing.length })}
      </div>
      {outgoing.length === 0 ? (
        <div className={styles.emptyHint}>
          {t("workflow.inspector.terminalStateHint")}
        </div>
      ) : (
        outgoing.map((tr) => (
          <TransitionRow key={tr.id} transition={tr} onSelect={onSelect} />
        ))
      )}

      <div className={styles.sectionLabel}>
        {t("workflow.inspector.incomingTransitions", { count: incoming.length })}
      </div>
      {incoming.length === 0 ? (
        <div className={styles.emptyHint}>
          {t("workflow.inspector.initialStateHint")}
        </div>
      ) : (
        incoming.map((tr) => (
          <TransitionRow key={tr.id} transition={tr} onSelect={onSelect} showSource />
        ))
      )}

      {editMode && edit && (
        <div className={styles.editActions} data-testid="workflow-inspector-state-actions">
          <button
            type="button"
            className={styles.editActionButton}
            onClick={() => edit.onEditState(state.id)}
            data-testid="workflow-inspector-edit-state"
          >
            <Pencil size={14} aria-hidden="true" />
            {t("workflow.inspector.editState")}
          </button>
          <button
            type="button"
            className={`${styles.editActionButton} ${styles.editActionDanger}`}
            onClick={() => edit.onDeleteState(state.id)}
            data-testid="workflow-inspector-delete-state"
          >
            <Trash2 size={14} aria-hidden="true" />
            {t("workflow.inspector.deleteState")}
          </button>
        </div>
      )}
    </div>
  );
}

function TransitionRow({
  transition,
  onSelect,
  showSource = false,
}: {
  transition: WorkflowTransition;
  onSelect: (selection: Selection) => void;
  showSource?: boolean;
}): JSX.Element {
  const { t } = useTranslation();
  return (
    <button
      type="button"
      className={styles.transitionRow}
      onClick={() => onSelect({ kind: "transition", id: transition.id })}
      data-testid={`workflow-inspector-transition-${transition.id}`}
    >
      <ArrowRight size={14} className={styles.transitionRowArrow} aria-hidden="true" />
      <span className={styles.transitionRowLabel}>
        {showSource ? transition.from_state : transition.to_state}
      </span>
      {transition.change_reason_required && (
        <span
          aria-label={t("workflow.inspector.requiresChangeReason")}
          title={t("workflow.inspector.requiresChangeReason")}
        >
          🔒
        </span>
      )}
    </button>
  );
}

// ---------------------------------------------------------------------------
// Transition inspector
// ---------------------------------------------------------------------------

function TransitionInspector({
  transition,
  editMode,
  edit,
}: {
  transition: WorkflowTransition;
  editMode: boolean;
  edit?: InspectorEditActions;
}): JSX.Element {
  const { t } = useTranslation();
  return (
    <div data-testid="workflow-inspector-transition">
      <div className={styles.inspectorStateHeader}>
        <MousePointerClick size={16} aria-hidden="true" />
        <span className={styles.inspectorStateName}>{transition.name}</span>
      </div>

      <div className={styles.sectionLabel}>{t("workflow.inspector.flow")}</div>
      <div className={styles.flowRow}>
        <span className={styles.flowState}>{transition.from_state}</span>
        <ArrowRight size={14} aria-hidden="true" />
        <span className={styles.flowState}>{transition.to_state}</span>
      </div>

      <div className={styles.sectionLabel}>{t("workflow.inspector.rules")}</div>
      <div className={styles.rulesGrid}>
        <span className={styles.ruleKey}>{t("workflow.inspector.requiredRole")}</span>
        <span className={styles.ruleValue}>{transition.required_role ?? "—"}</span>
        <span className={styles.ruleKey}>{t("workflow.inspector.changeReason")}</span>
        <span className={styles.ruleValue}>
          {transition.change_reason_required ? (
            <>
              {t("workflow.inspector.required")}
              <span aria-hidden="true">🔒</span>
            </>
          ) : (
            t("workflow.inspector.optional")
          )}
        </span>
        <span className={styles.ruleKey}>{t("workflow.inspector.signatureGate")}</span>
        <span className={styles.ruleValue}>
          {transition.signature_gate ? t("workflow.inspector.required") : "—"}
        </span>
      </div>

      {editMode && edit && (
        <div
          className={styles.editActions}
          data-testid="workflow-inspector-transition-actions"
        >
          <button
            type="button"
            className={styles.editActionButton}
            onClick={() =>
              edit.onEditTransition(transition.from_state, transition.to_state)
            }
            data-testid="workflow-inspector-edit-transition"
          >
            <Pencil size={14} aria-hidden="true" />
            {t("workflow.inspector.editTransition")}
          </button>
          <button
            type="button"
            className={`${styles.editActionButton} ${styles.editActionDanger}`}
            onClick={() =>
              edit.onDeleteTransition(transition.from_state, transition.to_state)
            }
            data-testid="workflow-inspector-delete-transition"
          >
            <Trash2 size={14} aria-hidden="true" />
            {t("workflow.inspector.deleteTransition")}
          </button>
        </div>
      )}
    </div>
  );
}
