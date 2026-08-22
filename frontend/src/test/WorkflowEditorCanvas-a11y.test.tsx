/**
 * a11y regression — WorkflowEditor canvas keyboard reachability.
 *
 * GESAMTTEST_BERICHT_2026-08-21.md §10.1 (Blocker, WCAG 2.1.1): StateNode and
 * TransitionEdge declare role="button" (StateNode: tabIndex=0, TransitionEdge:
 * tabIndex=-1) but had no onKeyDown handler at all, so a keyboard-only user
 * could tab to (or, for the edge, be focused onto) the element and had no way
 * to activate it. Verifies Enter and Space now trigger the same behavior the
 * existing pointer interaction (double-click / click) already triggers.
 */

import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import {
  Position,
  ReactFlow,
  ReactFlowProvider,
  type EdgeTypes,
  type NodeTypes,
} from "@xyflow/react";
import { StateNode } from "../components/WorkflowEditor/StateNode";
import { TransitionEdge } from "../components/WorkflowEditor/TransitionEdge";
import type { StateFlowNode, TransitionFlowEdge } from "../components/WorkflowEditor/layout";
import type { WorkflowState, WorkflowTransition } from "../api/workflows";

const NODE_TYPES: NodeTypes = { stateNode: StateNode };
const EDGE_TYPES: EdgeTypes = { transition: TransitionEdge };

// jsdom never fires ResizeObserver, so React Flow never measures real handle
// positions. Pre-declaring the four handles StateNode renders (see its JSX)
// lets React Flow compute a valid edge path without relying on measurement —
// needed only for the TransitionEdge tests below, which must get past
// getEdgePosition() returning null for un-positioned handles.
function stubbedHandles() {
  return [
    { id: "top", type: "target" as const, position: Position.Top, x: 0, y: 0 },
    { id: "left", type: "target" as const, position: Position.Left, x: 0, y: 0 },
    { id: "bottom", type: "source" as const, position: Position.Bottom, x: 0, y: 0 },
    { id: "right", type: "source" as const, position: Position.Right, x: 0, y: 0 },
  ];
}

function makeState(overrides: Partial<WorkflowState> = {}): WorkflowState {
  return {
    id: "draft",
    name: "Draft",
    type: "initial",
    outgoingCount: 1,
    incomingCount: 0,
    isInitial: true,
    ...overrides,
  };
}

function makeTransition(overrides: Partial<WorkflowTransition> = {}): WorkflowTransition {
  return {
    id: "draft->review",
    name: "submit",
    from_state: "draft",
    to_state: "review",
    change_reason_required: false,
    signature_gate: false,
    ...overrides,
  };
}

describe("WorkflowEditor canvas keyboard accessibility", () => {
  it("StateNode: Enter opens inline rename in edit mode (mirrors onDoubleClick)", () => {
    const state = makeState();
    const nodes: StateFlowNode[] = [
      {
        id: state.id,
        type: "stateNode",
        position: { x: 0, y: 0 },
        data: { state, editMode: true, onRename: vi.fn() },
      },
    ];

    render(
      <ReactFlowProvider>
        <ReactFlow nodes={nodes} edges={[]} nodeTypes={NODE_TYPES} />
      </ReactFlowProvider>
    );

    const node = screen.getByTestId(`workflow-state-node-${state.id}`);
    expect(screen.queryByTestId(`workflow-state-rename-${state.id}`)).not.toBeInTheDocument();

    fireEvent.keyDown(node, { key: "Enter" });

    expect(screen.getByTestId(`workflow-state-rename-${state.id}`)).toBeInTheDocument();
  });

  it("StateNode: Space opens inline rename in edit mode (mirrors onDoubleClick)", () => {
    const state = makeState();
    const nodes: StateFlowNode[] = [
      {
        id: state.id,
        type: "stateNode",
        position: { x: 0, y: 0 },
        data: { state, editMode: true, onRename: vi.fn() },
      },
    ];

    render(
      <ReactFlowProvider>
        <ReactFlow nodes={nodes} edges={[]} nodeTypes={NODE_TYPES} />
      </ReactFlowProvider>
    );

    const node = screen.getByTestId(`workflow-state-node-${state.id}`);
    fireEvent.keyDown(node, { key: " " });

    expect(screen.getByTestId(`workflow-state-rename-${state.id}`)).toBeInTheDocument();
  });

  it("StateNode: Enter/Space are no-ops in read-only mode (no onDoubleClick either)", () => {
    const state = makeState();
    const nodes: StateFlowNode[] = [
      {
        id: state.id,
        type: "stateNode",
        position: { x: 0, y: 0 },
        data: { state, editMode: false },
      },
    ];

    render(
      <ReactFlowProvider>
        <ReactFlow nodes={nodes} edges={[]} nodeTypes={NODE_TYPES} />
      </ReactFlowProvider>
    );

    const node = screen.getByTestId(`workflow-state-node-${state.id}`);
    fireEvent.keyDown(node, { key: "Enter" });

    expect(screen.queryByTestId(`workflow-state-rename-${state.id}`)).not.toBeInTheDocument();
  });

  it("TransitionEdge: Enter triggers the same selection as a pointer click", () => {
    const draft = makeState({ id: "draft", name: "Draft" });
    const review = makeState({ id: "review", name: "Review", isInitial: false });
    const transition = makeTransition();
    const nodes: StateFlowNode[] = [
      {
        id: draft.id,
        type: "stateNode",
        position: { x: 0, y: 0 },
        measured: { width: 200, height: 64 },
        handles: stubbedHandles(),
        data: { state: draft },
      },
      {
        id: review.id,
        type: "stateNode",
        position: { x: 0, y: 150 },
        measured: { width: 200, height: 64 },
        handles: stubbedHandles(),
        data: { state: review },
      },
    ];
    const edges: TransitionFlowEdge[] = [
      {
        id: transition.id,
        source: transition.from_state,
        target: transition.to_state,
        sourceHandle: "bottom",
        targetHandle: "top",
        type: "transition",
        data: { transition },
      },
    ];
    const onEdgeClick = vi.fn();

    render(
      <ReactFlowProvider>
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={NODE_TYPES}
          edgeTypes={EDGE_TYPES}
          onEdgeClick={onEdgeClick}
        />
      </ReactFlowProvider>
    );

    const label = screen.getByTestId(`workflow-transition-edge-${transition.id}`);
    fireEvent.keyDown(label, { key: "Enter" });

    expect(onEdgeClick).toHaveBeenCalledTimes(1);
  });

  it("TransitionEdge: Space triggers the same selection as a pointer click", () => {
    const draft = makeState({ id: "draft", name: "Draft" });
    const review = makeState({ id: "review", name: "Review", isInitial: false });
    const transition = makeTransition();
    const nodes: StateFlowNode[] = [
      {
        id: draft.id,
        type: "stateNode",
        position: { x: 0, y: 0 },
        measured: { width: 200, height: 64 },
        handles: stubbedHandles(),
        data: { state: draft },
      },
      {
        id: review.id,
        type: "stateNode",
        position: { x: 0, y: 150 },
        measured: { width: 200, height: 64 },
        handles: stubbedHandles(),
        data: { state: review },
      },
    ];
    const edges: TransitionFlowEdge[] = [
      {
        id: transition.id,
        source: transition.from_state,
        target: transition.to_state,
        sourceHandle: "bottom",
        targetHandle: "top",
        type: "transition",
        data: { transition },
      },
    ];
    const onEdgeClick = vi.fn();

    render(
      <ReactFlowProvider>
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={NODE_TYPES}
          edgeTypes={EDGE_TYPES}
          onEdgeClick={onEdgeClick}
        />
      </ReactFlowProvider>
    );

    const label = screen.getByTestId(`workflow-transition-edge-${transition.id}`);
    fireEvent.keyDown(label, { key: " " });

    expect(onEdgeClick).toHaveBeenCalledTimes(1);
  });
});
