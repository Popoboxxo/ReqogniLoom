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

import { useMemo } from "react";
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
      <div className={styles.sectionLabel}>{t("diagramGraph.inspector.label")}</div>
      <input
        className={styles.fieldInput}
        value={node.label}
        disabled={!editMode}
        onChange={(e) => onUpdate({ label: e.target.value })}
        data-testid="graph-inspector-node-label"
      />

      <div className={styles.sectionLabel}>{t("diagramGraph.inspector.type")}</div>
      <select
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

      <div className={styles.sectionLabel}>{t("diagramGraph.inspector.accent")}</div>
      <select
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
          <div className={styles.sectionLabel}>{t("diagramGraph.inspector.parentGroup")}</div>
          <select
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

      <ArtifactRefPicker node={node} editMode={editMode} onUpdate={onUpdate} />

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
  const entityType = node.artifact_ref?.entity_type ?? GRAPH_ARTIFACT_ENTITY_TYPES[0];
  const refId = node.artifact_ref?.id ?? "";

  return (
    <div data-testid="graph-inspector-artifact-ref">
      <div className={styles.sectionLabel}>{t("diagramGraph.inspector.artifactRef")}</div>
      <select
        className={styles.fieldSelect}
        value={entityType}
        disabled={!editMode}
        onChange={(e) =>
          onUpdate({
            artifact_ref: { entity_type: e.target.value as GraphArtifactEntityType, id: refId },
          })
        }
        data-testid="graph-inspector-artifact-entity-type"
      >
        {GRAPH_ARTIFACT_ENTITY_TYPES.map((et) => (
          <option key={et} value={et}>
            {et}
          </option>
        ))}
      </select>
      <input
        className={styles.fieldInput}
        placeholder={t("diagramGraph.inspector.artifactIdPlaceholder")}
        value={refId}
        disabled={!editMode}
        onChange={(e) => onUpdate({ artifact_ref: { entity_type: entityType, id: e.target.value } })}
        data-testid="graph-inspector-artifact-id"
      />
      <div className={styles.artifactRefActions}>
        {node.artifact_ref ? (
          <button
            type="button"
            className={styles.editActionButton}
            disabled={!editMode}
            onClick={() => onUpdate({ artifact_ref: undefined })}
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
      <div className={styles.sectionLabel}>{t("diagramGraph.inspector.label")}</div>
      <input
        className={styles.fieldInput}
        value={edge.label ?? ""}
        disabled={!editMode}
        onChange={(e) => onUpdate({ label: e.target.value })}
        data-testid="graph-inspector-edge-label"
      />

      <div className={styles.sectionLabel}>{t("diagramGraph.inspector.type")}</div>
      <select
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

      <div className={styles.sectionLabel}>{t("diagramGraph.inspector.lineStyle")}</div>
      <select
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
        <span className={styles.ruleKey}>{t("diagramGraph.inspector.sourceHandle")}</span>
        <select
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
        <span className={styles.ruleKey}>{t("diagramGraph.inspector.targetHandle")}</span>
        <select
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
