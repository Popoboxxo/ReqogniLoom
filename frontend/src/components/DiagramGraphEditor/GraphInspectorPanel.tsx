/**
 * GH-353 Task 8 — GraphInspectorPanel: right-hand details/edit panel.
 *
 * Modelled on `WorkflowEditor/InspectorPanel.tsx`: shows an empty prompt, a
 * Node inspector, or an Edge inspector depending on the current selection.
 * In edit mode, node/edge properties (label, type, style, artifact_ref) are
 * editable inline — there is no separate modal dialog, mirroring the
 * DiagramDetailView "inline edit" affordance rather than WorkflowEditor's
 * dialog-heavy flow (this editor has no backend-validated named-transition
 * rules to gate behind a confirm step).
 */

import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link2, Trash2, Unlink, Workflow } from "lucide-react";
import type { GraphFlowEdge, GraphFlowNode } from "./graph-layout";
import {
  GRAPH_ARTIFACT_ENTITY_TYPES,
  GRAPH_EDGE_TYPES,
  GRAPH_NODE_TYPES,
  GRAPH_STYLE_ACCENTS,
  type Selection,
} from "./constants";
import type {
  GraphArtifactEntityType,
  GraphEdge,
  GraphEdgeLineStyle,
  GraphEdgeType,
  GraphHandlePosition,
  GraphNode,
  GraphNodeType,
  GraphStyleAccent,
} from "../../types";
import styles from "./DiagramGraphEditor.module.css";

const HANDLE_POSITIONS: readonly GraphHandlePosition[] = ["top", "right", "bottom", "left"];

interface GraphInspectorPanelProps {
  nodes: GraphFlowNode[];
  edges: GraphFlowEdge[];
  selection: Selection;
  onSelect: (selection: Selection) => void;
  editMode: boolean;
  onUpdateNode: (id: string, patch: Partial<GraphNode>) => void;
  onUpdateEdge: (id: string, patch: Partial<GraphEdge>) => void;
  onDeleteNode: (id: string) => void;
  onDeleteEdge: (id: string) => void;
}

export function GraphInspectorPanel({
  nodes,
  edges,
  selection,
  onSelect,
  editMode,
  onUpdateNode,
  onUpdateEdge,
  onDeleteNode,
  onDeleteEdge,
}: GraphInspectorPanelProps): JSX.Element {
  const { t } = useTranslation();

  const selectedNode = useMemo<GraphFlowNode | null>(() => {
    if (selection.kind !== "node") return null;
    return nodes.find((n) => n.id === selection.id) ?? null;
  }, [nodes, selection]);

  const selectedEdge = useMemo<GraphFlowEdge | null>(() => {
    if (selection.kind !== "edge") return null;
    return edges.find((e) => e.id === selection.id) ?? null;
  }, [edges, selection]);

  return (
    <aside
      className={styles.inspector}
      aria-label={t("diagramGraph.inspector.ariaLabel")}
      data-testid="graph-inspector"
    >
      <header className={styles.inspectorHeader}>
        <span className={styles.inspectorTitle}>{t("diagramGraph.inspector.title")}</span>
      </header>

      <div className={styles.inspectorBody} aria-live="polite">
        {selectedNode ? (
          <NodeInspector
            flowNode={selectedNode}
            groupNodes={nodes.filter((n) => n.data.node.type === "group" && n.id !== selectedNode.id)}
            editMode={editMode}
            onUpdate={(patch) => onUpdateNode(selectedNode.id, patch)}
            onDelete={() => onDeleteNode(selectedNode.id)}
          />
        ) : selectedEdge ? (
          <EdgeInspector
            flowEdge={selectedEdge}
            editMode={editMode}
            onUpdate={(patch) => onUpdateEdge(selectedEdge.id, patch)}
            onDelete={() => onDeleteEdge(selectedEdge.id)}
          />
        ) : (
          <div className={styles.inspectorEmpty}>
            <Workflow size={32} aria-hidden="true" />
            <div className={styles.overlayText}>{t("diagramGraph.inspector.emptyPrompt")}</div>
          </div>
        )}
      </div>
      {(selectedNode || selectedEdge) && (
        <button
          type="button"
          className={styles.inspectorClearSelection}
          onClick={() => onSelect({ kind: "none" })}
          data-testid="graph-inspector-clear-selection"
        >
          {t("diagramGraph.inspector.clearSelection")}
        </button>
      )}
    </aside>
  );
}

// ---------------------------------------------------------------------------
// Node inspector
// ---------------------------------------------------------------------------

function NodeInspector({
  flowNode,
  groupNodes,
  editMode,
  onUpdate,
  onDelete,
}: {
  flowNode: GraphFlowNode;
  groupNodes: GraphFlowNode[];
  editMode: boolean;
  onUpdate: (patch: Partial<GraphNode>) => void;
  onDelete: () => void;
}): JSX.Element {
  const { t } = useTranslation();
  const node = flowNode.data.node;

  return (
    <div data-testid="graph-inspector-node">
      <label className={styles.sectionLabel} htmlFor="graph-inspector-node-label">{t("diagramGraph.inspector.label")}</label>
      <input
        id="graph-inspector-node-label"
        className={styles.fieldInput}
        value={node.label}
        disabled={!editMode}
        onChange={(e) => onUpdate({ label: e.target.value })}
        data-testid="graph-inspector-node-label"
      />

      <label className={styles.sectionLabel} htmlFor="graph-inspector-node-type">{t("diagramGraph.inspector.type")}</label>
      <select
        id="graph-inspector-node-type"
        className={styles.fieldSelect}
        value={node.type}
        disabled={!editMode}
        onChange={(e) => onUpdate({ type: e.target.value as GraphNodeType })}
        data-testid="graph-inspector-node-type"
      >
        {GRAPH_NODE_TYPES.map((tp) => (
          <option key={tp} value={tp}>
            {t(`diagramGraph.nodeTypes.${tp}`)}
          </option>
        ))}
      </select>

      <label className={styles.sectionLabel} htmlFor="graph-inspector-node-accent">{t("diagramGraph.inspector.accent")}</label>
      <select
        id="graph-inspector-node-accent"
        className={styles.fieldSelect}
        value={node.style?.accent ?? "default"}
        disabled={!editMode}
        onChange={(e) => onUpdate({ style: { accent: e.target.value as GraphStyleAccent } })}
        data-testid="graph-inspector-node-accent"
      >
        {GRAPH_STYLE_ACCENTS.map((accent) => (
          <option key={accent} value={accent}>
            {t(`diagramGraph.accents.${accent}`)}
          </option>
        ))}
      </select>

      {groupNodes.length > 0 && (
        <>
          <label className={styles.sectionLabel} htmlFor="graph-inspector-node-parent">{t("diagramGraph.inspector.parentGroup")}</label>
          <select
            id="graph-inspector-node-parent"
            className={styles.fieldSelect}
            value={node.parent_id ?? ""}
            disabled={!editMode}
            onChange={(e) => onUpdate({ parent_id: e.target.value || null })}
            data-testid="graph-inspector-node-parent"
          >
            <option value="">{t("diagramGraph.inspector.noParent")}</option>
            {groupNodes.map((g) => (
              <option key={g.id} value={g.id}>
                {g.data.node.label}
              </option>
            ))}
          </select>
        </>
      )}

      {/* key=node.id (I3, final review): NodeInspector is not remounted when
          the selected node changes (React reuses the instance and updates
          props), so ArtifactRefPicker's own local draft state (see below)
          must be reset by a key change, or switching the selected node would
          keep showing the PREVIOUS node's in-progress, uncommitted draft. */}
      <ArtifactRefPicker key={node.id} node={node} editMode={editMode} onUpdate={onUpdate} />

      {editMode && (
        <div className={styles.editActions} data-testid="graph-inspector-node-actions">
          <button
            type="button"
            className={`${styles.editActionButton} ${styles.editActionDanger}`}
            onClick={onDelete}
            data-testid="graph-inspector-delete-node"
          >
            <Trash2 size={14} aria-hidden="true" />
            {t("diagramGraph.inspector.deleteNode")}
          </button>
        </div>
      )}
    </div>
  );
}

/**
 * Artifact-ref picker (Task 8 brief): entity-type select populated from the
 * known artifact entity types (backend/diagram/node_graph.py
 * KNOWN_ARTIFACT_ENTITY_TYPES) + a UUID input for the target id. Existence of
 * the referenced entity is intentionally NOT verified client-side — the
 * backend reconciler (Task 3) is the source of truth at write time, matching
 * the schema module's own doc comment.
 */
/** Syntactically-valid-UUID check (any RFC 4122 variant/version). */
const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function isValidGraphArtifactRefId(value: string): boolean {
  return UUID_PATTERN.test(value);
}

function ArtifactRefPicker({
  node,
  editMode,
  onUpdate,
}: {
  node: GraphNode;
  editMode: boolean;
  onUpdate: (patch: Partial<GraphNode>) => void;
}): JSX.Element {
  const { t } = useTranslation();

  // I3 (final review): local draft state, NOT derived straight from
  // `node.artifact_ref` on every render. Touching the entity-type select or
  // typing a partial/invalid id must never leave a save-blocking
  // `{ id: "" }` / partial-UUID `artifact_ref` on the node (validate_node_graph
  // rejects that with no indication of which control caused it) — so
  // `onUpdate` only ever receives a populated `artifact_ref` once the typed
  // id is a syntactically valid UUID, and `undefined` otherwise. Deriving the
  // *displayed* value straight from that same committed `node.artifact_ref`
  // would make the id input un-typeable: every keystroke before the UUID is
  // complete would round-trip through `undefined` and reset the field back to
  // empty. Local draft state decouples "what the user is typing" from "what
  // has actually been committed upstream". Reset when the selected node
  // changes via the `key={node.id}` on this component (GraphInspectorPanel).
  const [draftEntityType, setDraftEntityType] = useState<GraphArtifactEntityType>(
    node.artifact_ref?.entity_type ?? GRAPH_ARTIFACT_ENTITY_TYPES[0]
  );
  const [draftRefId, setDraftRefId] = useState<string>(node.artifact_ref?.id ?? "");

  const commit = (nextEntityType: GraphArtifactEntityType, nextRefId: string): void => {
    onUpdate({
      artifact_ref: isValidGraphArtifactRefId(nextRefId)
        ? { entity_type: nextEntityType, id: nextRefId }
        : undefined,
    });
  };

  return (
    <div data-testid="graph-inspector-artifact-ref">
      <label className={styles.sectionLabel} htmlFor="graph-inspector-artifact-entity-type">{t("diagramGraph.inspector.artifactRef")}</label>
      <select
        id="graph-inspector-artifact-entity-type"
        className={styles.fieldSelect}
        value={draftEntityType}
        disabled={!editMode}
        onChange={(e) => {
          const next = e.target.value as GraphArtifactEntityType;
          setDraftEntityType(next);
          commit(next, draftRefId);
        }}
        data-testid="graph-inspector-artifact-entity-type"
      >
        {GRAPH_ARTIFACT_ENTITY_TYPES.map((et) => (
          <option key={et} value={et}>
            {et}
          </option>
        ))}
      </select>
      <input
        id="graph-inspector-artifact-id"
        className={styles.fieldInput}
        placeholder={t("diagramGraph.inspector.artifactIdPlaceholder")}
        aria-label={t("diagramGraph.inspector.artifactIdPlaceholder")}
        value={draftRefId}
        disabled={!editMode}
        onChange={(e) => {
          setDraftRefId(e.target.value);
          commit(draftEntityType, e.target.value);
        }}
        data-testid="graph-inspector-artifact-id"
      />
      <div className={styles.artifactRefActions}>
        {node.artifact_ref ? (
          <button
            type="button"
            className={styles.editActionButton}
            disabled={!editMode}
            onClick={() => {
              setDraftEntityType(GRAPH_ARTIFACT_ENTITY_TYPES[0]);
              setDraftRefId("");
              onUpdate({ artifact_ref: undefined });
            }}
            data-testid="graph-inspector-artifact-clear"
          >
            <Unlink size={14} aria-hidden="true" />
            {t("diagramGraph.inspector.artifactClear")}
          </button>
        ) : (
          <span className={styles.emptyHint}>
            <Link2 size={12} aria-hidden="true" /> {t("diagramGraph.inspector.artifactUnlinked")}
          </span>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Edge inspector
// ---------------------------------------------------------------------------

function EdgeInspector({
  flowEdge,
  editMode,
  onUpdate,
  onDelete,
}: {
  flowEdge: GraphFlowEdge;
  editMode: boolean;
  onUpdate: (patch: Partial<GraphEdge>) => void;
  onDelete: () => void;
}): JSX.Element {
  const { t } = useTranslation();
  const edge = flowEdge.data?.edge;
  if (!edge) return <></>;

  return (
    <div data-testid="graph-inspector-edge">
      <label className={styles.sectionLabel} htmlFor="graph-inspector-edge-label">{t("diagramGraph.inspector.label")}</label>
      <input
        id="graph-inspector-edge-label"
        className={styles.fieldInput}
        value={edge.label ?? ""}
        disabled={!editMode}
        onChange={(e) => onUpdate({ label: e.target.value })}
        data-testid="graph-inspector-edge-label"
      />

      <label className={styles.sectionLabel} htmlFor="graph-inspector-edge-type">{t("diagramGraph.inspector.type")}</label>
      <select
        id="graph-inspector-edge-type"
        className={styles.fieldSelect}
        value={edge.type}
        disabled={!editMode}
        onChange={(e) => onUpdate({ type: e.target.value as GraphEdgeType })}
        data-testid="graph-inspector-edge-type"
      >
        {GRAPH_EDGE_TYPES.map((tp) => (
          <option key={tp} value={tp}>
            {t(`diagramGraph.edgeTypes.${tp}`)}
          </option>
        ))}
      </select>

      <label className={styles.sectionLabel} htmlFor="graph-inspector-edge-line">{t("diagramGraph.inspector.lineStyle")}</label>
      <select
        id="graph-inspector-edge-line"
        className={styles.fieldSelect}
        value={edge.style?.line ?? "solid"}
        disabled={!editMode}
        onChange={(e) => onUpdate({ style: { line: e.target.value as GraphEdgeLineStyle } })}
        data-testid="graph-inspector-edge-line"
      >
        <option value="solid">{t("diagramGraph.lineStyles.solid")}</option>
        <option value="dashed">{t("diagramGraph.lineStyles.dashed")}</option>
      </select>

      <div className={styles.rulesGrid}>
        <label className={styles.ruleKey} htmlFor="graph-inspector-edge-source-handle">{t("diagramGraph.inspector.sourceHandle")}</label>
        <select
          id="graph-inspector-edge-source-handle"
          className={styles.fieldSelect}
          value={edge.source_handle ?? "bottom"}
          disabled={!editMode}
          onChange={(e) => onUpdate({ source_handle: e.target.value as GraphHandlePosition })}
          data-testid="graph-inspector-edge-source-handle"
        >
          {HANDLE_POSITIONS.map((h) => (
            <option key={h} value={h}>
              {h}
            </option>
          ))}
        </select>
        <label className={styles.ruleKey} htmlFor="graph-inspector-edge-target-handle">{t("diagramGraph.inspector.targetHandle")}</label>
        <select
          id="graph-inspector-edge-target-handle"
          className={styles.fieldSelect}
          value={edge.target_handle ?? "top"}
          disabled={!editMode}
          onChange={(e) => onUpdate({ target_handle: e.target.value as GraphHandlePosition })}
          data-testid="graph-inspector-edge-target-handle"
        >
          {HANDLE_POSITIONS.map((h) => (
            <option key={h} value={h}>
              {h}
            </option>
          ))}
        </select>
      </div>

      {editMode && (
        <div className={styles.editActions} data-testid="graph-inspector-edge-actions">
          <button
            type="button"
            className={`${styles.editActionButton} ${styles.editActionDanger}`}
            onClick={onDelete}
            data-testid="graph-inspector-delete-edge"
          >
            <Trash2 size={14} aria-hidden="true" />
            {t("diagramGraph.inspector.deleteEdge")}
          </button>
        </div>
      )}
    </div>
  );
}
