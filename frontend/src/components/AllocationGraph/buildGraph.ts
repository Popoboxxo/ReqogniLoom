/**
 * P5 Task 5.1 — card graph model builder.
 *
 * Turns the flat `allocation-view` rows (one per Requirement and per
 * ArchitectureElement) into positioned React Flow nodes/edges:
 *
 *  - Requirement cards sit in the left band, element cards in the right one.
 *  - `parent_id` becomes a grey hierarchy edge inside each band; sibling order
 *    follows the persisted `Artifact.sort_key` (the same fractional index the
 *    trees use) and never the order the rows happen to arrive in.
 *  - At most one blue, dashed allocation edge leaves a Requirement (N:1, see
 *    plan improvement #1 / the partial unique index).
 *  - A collapsed row keeps its own card, hides every descendant and carries
 *    the aggregate descendant count on its node data. Collapsing never
 *    filters rows: the model owns visibility, the caller owns the row set.
 *  - `opts.dimmed` is a marker only. A dimmed row stays in the graph.
 *
 * The layout reuses the repo's dagre dependency (`@dagrejs/dagre`, already
 * used by `DiagramGraphEditor/graph-layout.ts` and `WorkflowEditor/layout.ts`)
 * for rank/slot geometry, then re-assigns the horizontal slots within a rank
 * by the deterministic tree order. Dagre alone preserves insertion order only
 * incidentally; the reassignment makes "siblings follow sort_key" a contract
 * instead of a dagre implementation detail.
 */

import dagre from '@dagrejs/dagre';
import { MarkerType, Position, type Edge, type Node } from '@xyflow/react';

/** Requirement card width in graph units. */
export const NODE_WIDTH = 220;
/** Requirement card height in graph units. */
export const NODE_HEIGHT = 88;
/** Horizontal gap between sibling cards inside one band. */
const SIBLING_GAP = 48;
/** Vertical gap between hierarchy levels inside one band. */
const LEVEL_GAP = 56;
/** Gap between the requirement band and the element band. */
const COLUMN_GAP = 240;
/** Margin dagre keeps around a band. */
const BAND_MARGIN = 24;
/**
 * Dagre's crossing/ordering pass is super-linear in the number of levels, so a
 * 250-level chain alone costs ~400 ms. Very deep or very large bands fall back
 * to the deterministic layered placement below (O4 in the plan: measure, do
 * not let a pathological page blow the layout budget).
 */
const DAGRE_MAX_NODES = 400;
const DAGRE_MAX_DEPTH = 60;

/** Grey stroke for parent → child edges. */
export const HIERARCHY_STROKE = 'var(--color-border, #94a3b8)';
/** Blue stroke for the allocation edges between the two bands. */
export const ALLOCATION_STROKE = 'var(--color-primary, #2563eb)';

export type AllocationRowKind = 'requirement' | 'element';

/**
 * One row of the flat allocation view
 * (`backend/application/allocation_view_service.py`).
 *
 * `parent_id` is kind-specific: for a requirement it is the parent's
 * **Artifact** id; for an element it is the parent element's **entity** id.
 * `allocated_to` on a requirement is the target element's **Artifact** id.
 */
export interface AllocationRow {
  kind: AllocationRowKind;
  id: string;
  artifact_id: string;
  parent_id: string | null;
  sort_key: string | null;
  title: string;
  allocated_to: string | null;
  allocation_intent?: string | null;
  /** Optimised read-object shape is `{state}`; the boolean/string forms are
   * kept for callers that pass a flat flag. */
  locked?: string | boolean | { state?: string | null } | null;
  tier_key?: string | null;
  tier_name?: string | null;
  level?: number | null;
  type?: string | null;
  category?: string | null;
  state?: string | null;
  element_id?: string | null;
  allocation_trace_link_id?: string | null;
  findings?: unknown[];
  group?: string | null;
  [key: string]: unknown;
}

/** Data carried by a card node. */
export interface AllocationNodeData extends Record<string, unknown> {
  row: AllocationRow;
  kind: AllocationRowKind;
  /** The row did not match the active filter — kept, only marked. */
  dimmed: boolean;
  /** Requirement without an `allocated-to` edge. */
  unallocated: boolean;
  /** The row is frozen (`locked` is set). */
  frozen: boolean;
  /** This row is collapsed; its descendants are not in the graph. */
  collapsed: boolean;
  /** Total descendants, regardless of collapse state. */
  descendantCount: number;
  /** Descendants hidden because this row is collapsed; 0 when expanded. */
  hiddenDescendantCount: number;
  /** Hierarchy depth inside its own band (roots are 0). */
  depth: number;
}

/** Data carried by a hierarchy or allocation edge. */
export interface AllocationEdgeData extends Record<string, unknown> {
  kind: 'hierarchy' | 'allocation';
  /** Set for allocation edges only. */
  requirementId?: string;
  /** Set for allocation edges only. */
  elementId?: string;
}

export type AllocationFlowNode = Node<AllocationNodeData, 'allocationCard'>;
export type AllocationFlowEdge = Edge<AllocationEdgeData>;

export interface BuildGraphOptions {
  /** Row ids (or node ids) whose descendants are hidden but counted. */
  collapsed: Set<string>;
  /** Marks a row as not matching the active filter. Never removes it. */
  dimmed: (row: AllocationRow) => boolean;
}

export interface AllocationGraphModel {
  nodes: AllocationFlowNode[];
  edges: AllocationFlowEdge[];
}

interface IndexedRow {
  row: AllocationRow;
  index: number;
}

interface RankEntry {
  key: string;
  x: number;
  y: number;
}

function nodeKey(row: AllocationRow): string {
  return `${row.kind === 'requirement' ? 'req' : 'el'}:${row.id}`;
}

function compareRows(a: IndexedRow, b: IndexedRow): number {
  const aKey = a.row.sort_key;
  const bKey = b.row.sort_key;
  if (aKey != null && bKey != null) {
    if (aKey !== bKey) return aKey < bKey ? -1 : 1;
  } else if (aKey == null && bKey != null) {
    // Rows without a persisted key are appended after ordered siblings.
    return 1;
  } else if (aKey != null && bKey == null) {
    return -1;
  }
  // Stable fallback: keep the input order for equal/missing keys.
  return a.index - b.index;
}

/** True when `collapsed` names this row, its node id or its artifact id. */
function isCollapsed(row: AllocationRow, collapsed: Set<string>): boolean {
  return collapsed.has(row.id) || collapsed.has(nodeKey(row)) || collapsed.has(row.artifact_id);
}

/**
 * Build the card graph for a filtered allocation-view page.
 *
 * Pure and synchronous: no React, no store, no network. The caller decides
 * which rows exist (filters/saved views); this model decides their geometry,
 * hierarchy edges, allocation edges and collapse visibility.
 */
export function buildGraph(rows: AllocationRow[], opts: BuildGraphOptions): AllocationGraphModel {
  const { collapsed, dimmed } = opts;

  const requirementRows: IndexedRow[] = [];
  const elementRows: IndexedRow[] = [];
  const requirementByArtifact = new Map<string, AllocationRow>();
  const elementById = new Map<string, AllocationRow>();
  const elementByArtifact = new Map<string, AllocationRow>();
  const keyByRow = new Map<AllocationRow, string>();
  const seenKeys = new Set<string>();

  rows.forEach((row, index) => {
    const key = nodeKey(row);
    // The backend page is already unique per kind/id; keep the first row when
    // a caller passes duplicate ids anyway (one node, therefore at most one
    // allocation edge per requirement).
    if (seenKeys.has(key)) return;
    seenKeys.add(key);
    keyByRow.set(row, key);
    if (row.kind === 'requirement') {
      requirementRows.push({ row, index });
      if (!requirementByArtifact.has(row.artifact_id)) {
        requirementByArtifact.set(row.artifact_id, row);
      }
    } else {
      elementRows.push({ row, index });
      elementById.set(row.id, row);
      elementByArtifact.set(row.artifact_id, row);
    }
  });

  const parentOf = (row: AllocationRow): AllocationRow | null => {
    if (!row.parent_id) return null;
    const parent =
      row.kind === 'requirement'
        ? requirementByArtifact.get(row.parent_id)
        : elementById.get(row.parent_id);
    return parent && parent !== row ? parent : null;
  };

  const childrenByParent = new Map<string, IndexedRow[]>();
  const rootsByKind: Record<AllocationRowKind, IndexedRow[]> = {
    requirement: [],
    element: [],
  };

  for (const indexed of [...requirementRows, ...elementRows]) {
    const { row } = indexed;
    const parent = parentOf(row);
    if (parent) {
      const parentKey = keyByRow.get(parent);
      if (parentKey) {
        const bucket = childrenByParent.get(parentKey);
        if (bucket) bucket.push(indexed);
        else childrenByParent.set(parentKey, [indexed]);
      }
    } else {
      rootsByKind[row.kind].push(indexed);
    }
  }

  for (const bucket of childrenByParent.values()) {
    bucket.sort(compareRows);
  }

  const orderIndex = new Map<string, number>();
  const depth = new Map<string, number>();
  const visited = new Set<string>();
  let sequence = 0;

  const walk = (start: IndexedRow[]): void => {
    const stack = [...start].reverse();
    while (stack.length > 0) {
      const current = stack.pop();
      if (!current) break;
      const key = keyByRow.get(current.row);
      if (!key || visited.has(key)) continue;
      visited.add(key);
      orderIndex.set(key, sequence);
      sequence += 1;
      depth.set(key, depth.get(key) ?? 0);
      const level = depth.get(key) ?? 0;
      const children = childrenByParent.get(key) ?? [];
      for (let i = children.length - 1; i >= 0; i -= 1) {
        const childKey = keyByRow.get(children[i].row);
        if (childKey && !visited.has(childKey)) {
          depth.set(childKey, level + 1);
        }
        stack.push(children[i]);
      }
    }
  };

  // Pre-order follows the sort_key-sorted children, so `orderIndex` IS the
  // deterministic tree order used for slot assignment below.
  walk(rootsByKind.requirement);
  walk(rootsByKind.element);
  // Corrupted data can leave a cycle without a root; give it a stable place
  // instead of silently dropping the rows.
  for (const indexed of [...requirementRows, ...elementRows]) {
    walk([indexed]);
  }

  // Post-order (descending pre-order) descendant counts.
  const descendantCount = new Map<string, number>();
  const descending = [...visited].sort(
    (a, b) => (orderIndex.get(b) ?? 0) - (orderIndex.get(a) ?? 0)
  );
  for (const key of descending) {
    let count = 0;
    for (const child of childrenByParent.get(key) ?? []) {
      const childKey = keyByRow.get(child.row);
      if (!childKey || !visited.has(childKey)) continue;
      count += 1 + (descendantCount.get(childKey) ?? 0);
    }
    descendantCount.set(key, count);
  }

  const hidden = new Set<string>();
  for (const indexed of [...requirementRows, ...elementRows]) {
    const { row } = indexed;
    if (!isCollapsed(row, collapsed)) continue;
    const startKey = keyByRow.get(row);
    if (!startKey) continue;
    const seen = new Set<string>([startKey]);
    const stack = [...(childrenByParent.get(startKey) ?? [])];
    while (stack.length > 0) {
      const child = stack.pop();
      if (!child) break;
      const childKey = keyByRow.get(child.row);
      if (!childKey || seen.has(childKey)) continue;
      seen.add(childKey);
      hidden.add(childKey);
      stack.push(...(childrenByParent.get(childKey) ?? []));
    }
  }

  const layoutBand = (kindRows: IndexedRow[]): Map<string, { x: number; y: number }> => {
    const visible = kindRows.filter(({ row }) => {
      const key = keyByRow.get(row);
      return key ? !hidden.has(key) : false;
    });
    const positions = new Map<string, { x: number; y: number }>();
    if (visible.length === 0) return positions;

    // Deterministic layered fallback: rank = tree depth, slot = position in
    // the deterministic order within that rank. No dependency, linear time.
    const layeredFallback = (): Map<string, { x: number; y: number }> => {
      const byDepth = new Map<number, string[]>();
      for (const { row } of visible) {
        const key = keyByRow.get(row);
        if (!key) continue;
        const level = depth.get(key) ?? 0;
        const bucket = byDepth.get(level);
        if (bucket) bucket.push(key);
        else byDepth.set(level, [key]);
      }
      const layered = new Map<string, { x: number; y: number }>();
      for (const [level, keys] of byDepth) {
        keys.sort((a, b) => (orderIndex.get(a) ?? 0) - (orderIndex.get(b) ?? 0));
        keys.forEach((key, slot) => {
          layered.set(key, {
            x: slot * (NODE_WIDTH + SIBLING_GAP),
            y: level * (NODE_HEIGHT + LEVEL_GAP),
          });
        });
      }
      return layered;
    };

    let configuredMaxDepth = 0;
    for (const { row } of visible) {
      const key = keyByRow.get(row);
      if (!key) continue;
      configuredMaxDepth = Math.max(configuredMaxDepth, depth.get(key) ?? 0);
    }
    if (visible.length > DAGRE_MAX_NODES || configuredMaxDepth > DAGRE_MAX_DEPTH) {
      return layeredFallback();
    }

    const graph = new dagre.graphlib.Graph();
    graph.setDefaultEdgeLabel(() => ({}));
    graph.setGraph({
      rankdir: 'TB',
      nodesep: SIBLING_GAP,
      ranksep: LEVEL_GAP,
      marginx: BAND_MARGIN,
      marginy: BAND_MARGIN,
    });

    for (const { row } of visible) {
      const key = keyByRow.get(row);
      if (!key) continue;
      graph.setNode(key, { width: NODE_WIDTH, height: NODE_HEIGHT });
    }
    for (const { row } of visible) {
      const parent = parentOf(row);
      if (!parent) continue;
      const parentKey = keyByRow.get(parent);
      const key = keyByRow.get(row);
      if (!parentKey || !key || hidden.has(parentKey)) continue;
      graph.setEdge(parentKey, key);
    }

    dagre.layout(graph);

    // Dagre fixes the ranks (y) and the slot positions (x) but not the order
    // within a rank. Re-assign the sorted slots by our deterministic order so
    // siblings are always laid out in sort_key order.
    const ranks = new Map<number, RankEntry[]>();
    for (const { row } of visible) {
      const key = keyByRow.get(row);
      if (!key) continue;
      const node = graph.node(key) as { x: number; y: number } | undefined;
      if (!node) continue;
      const rank = Math.round(node.y);
      const entry: RankEntry = { key, x: node.x, y: node.y };
      const bucket = ranks.get(rank);
      if (bucket) bucket.push(entry);
      else ranks.set(rank, [entry]);
    }

    for (const entries of ranks.values()) {
      const slots = entries.map((entry) => entry.x).sort((a, b) => a - b);
      entries.sort((a, b) => (orderIndex.get(a.key) ?? 0) - (orderIndex.get(b.key) ?? 0));
      entries.forEach((entry, slotIndex) => {
        positions.set(entry.key, { x: slots[slotIndex], y: entry.y });
      });
    }

    // Normalise the band to the top-left origin. React Flow expects the
    // top-left corner, dagre returns the centre.
    const lefts: number[] = [];
    const tops: number[] = [];
    for (const position of positions.values()) {
      lefts.push(position.x - NODE_WIDTH / 2);
      tops.push(position.y - NODE_HEIGHT / 2);
    }
    const minLeft = Math.min(...lefts);
    const minTop = Math.min(...tops);
    for (const [key, position] of positions) {
      positions.set(key, {
        x: position.x - NODE_WIDTH / 2 - minLeft,
        y: position.y - NODE_HEIGHT / 2 - minTop,
      });
    }
    return positions;
  };

  const requirementPositions = layoutBand(requirementRows);
  const elementPositions = layoutBand(elementRows);

  let requirementBandWidth = 0;
  for (const position of requirementPositions.values()) {
    requirementBandWidth = Math.max(requirementBandWidth, position.x + NODE_WIDTH);
  }
  const elementOffsetX = requirementPositions.size > 0 ? requirementBandWidth + COLUMN_GAP : 0;

  const nodes: AllocationFlowNode[] = [];
  const edges: AllocationFlowEdge[] = [];

  for (const { row } of requirementRows) {
    const key = keyByRow.get(row);
    if (!key || hidden.has(key)) continue;
    const position = requirementPositions.get(key);
    if (!position) continue;
    const collapsedHere = isCollapsed(row, collapsed);
    const isDimmed = dimmed(row);
    nodes.push({
      id: key,
      type: 'allocationCard',
      position,
      width: NODE_WIDTH,
      height: NODE_HEIGHT,
      sourcePosition: Position.Bottom,
      targetPosition: Position.Top,
      className: isDimmed ? 'allocationNode allocationNode--dimmed' : 'allocationNode',
      data: {
        row,
        kind: 'requirement',
        dimmed: isDimmed,
        unallocated: row.allocated_to == null,
        frozen: Boolean(row.locked),
        collapsed: collapsedHere,
        descendantCount: descendantCount.get(key) ?? 0,
        hiddenDescendantCount: collapsedHere ? (descendantCount.get(key) ?? 0) : 0,
        depth: depth.get(key) ?? 0,
      },
    });
  }

  for (const { row } of elementRows) {
    const key = keyByRow.get(row);
    if (!key || hidden.has(key)) continue;
    const position = elementPositions.get(key);
    if (!position) continue;
    const collapsedHere = isCollapsed(row, collapsed);
    const isDimmed = dimmed(row);
    nodes.push({
      id: key,
      type: 'allocationCard',
      position: { x: position.x + elementOffsetX, y: position.y },
      width: NODE_WIDTH,
      height: NODE_HEIGHT,
      sourcePosition: Position.Bottom,
      targetPosition: Position.Top,
      className: isDimmed ? 'allocationNode allocationNode--dimmed' : 'allocationNode',
      data: {
        row,
        kind: 'element',
        dimmed: isDimmed,
        unallocated: false,
        frozen: Boolean(row.locked),
        collapsed: collapsedHere,
        descendantCount: descendantCount.get(key) ?? 0,
        hiddenDescendantCount: collapsedHere ? (descendantCount.get(key) ?? 0) : 0,
        depth: depth.get(key) ?? 0,
      },
    });
  }

  // Grey hierarchy edges (parent -> child) inside both bands.
  for (const { row } of [...requirementRows, ...elementRows]) {
    const parent = parentOf(row);
    if (!parent) continue;
    const parentKey = keyByRow.get(parent);
    const key = keyByRow.get(row);
    if (!parentKey || !key || hidden.has(parentKey) || hidden.has(key)) continue;
    edges.push({
      id: `hierarchy:${parentKey}->${key}`,
      source: parentKey,
      target: key,
      type: 'default',
      className: 'allocationEdge allocationEdge--hierarchy',
      style: { stroke: HIERARCHY_STROKE, strokeWidth: 1 },
      data: { kind: 'hierarchy' },
    });
  }

  // Blue, dashed allocation edges crossing from the requirement band to the
  // element band. Exactly one per requirement (N:1) — later duplicate rows for
  // the same requirement id can never add a second edge.
  const allocatedRequirementIds = new Set<string>();
  for (const { row } of requirementRows) {
    if (!row.allocated_to) continue;
    if (allocatedRequirementIds.has(row.id)) continue;
    const requirementKey = keyByRow.get(row);
    if (!requirementKey || hidden.has(requirementKey)) continue;
    const element = elementByArtifact.get(row.allocated_to);
    if (!element) continue;
    const elementKey = keyByRow.get(element);
    if (!elementKey || hidden.has(elementKey)) continue;
    allocatedRequirementIds.add(row.id);
    edges.push({
      id: `allocation:${row.id}`,
      source: requirementKey,
      target: elementKey,
      type: 'smoothstep',
      className: 'allocationEdge allocationEdge--allocation',
      style: {
        stroke: ALLOCATION_STROKE,
        strokeWidth: 1.5,
        strokeDasharray: '6 4',
      },
      markerEnd: {
        type: MarkerType.ArrowClosed,
        width: 16,
        height: 16,
        color: ALLOCATION_STROKE,
      },
      data: { kind: 'allocation', requirementId: row.id, elementId: element.id },
    });
  }

  return { nodes, edges };
}
