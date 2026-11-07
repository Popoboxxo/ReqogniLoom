/**
 * Test double for `@xyflow/react` (P5 graph tests).
 *
 * jsdom never measures nodes, so the real viewport cannot drive drag/connect
 * interactions deterministically. This stub renders the *registered node
 * components* exactly as React Flow would (so handle/marker assertions stay
 * real), renders one connect button per ordered node pair, and forwards
 * `onConnect`/`onNodeClick`. Tests opt in with:
 *
 *   vi.mock("@xyflow/react", async () =>
 *     (await import("../../test/xyflow-stub")).createXyflowStub()
 *   );
 *
 * It is a test helper but lives under `src/` so the dynamic import resolves
 * from the same module graph; it is never imported by production code.
 */

import { createElement, type ReactNode } from "react";

interface StubNode {
  id: string;
  type?: string;
  data?: Record<string, unknown>;
}

interface StubEdge {
  id: string;
  source: string;
  target: string;
  className?: string;
}

interface StubConnection {
  source: string;
  target: string;
  sourceHandle?: string | null;
  targetHandle?: string | null;
}

interface StubNodeComponentProps {
  id: string;
  data?: Record<string, unknown>;
  selected?: boolean;
}

interface StubReactFlowProps {
  nodes?: StubNode[];
  edges?: StubEdge[];
  nodeTypes?: Record<string, (props: StubNodeComponentProps) => ReactNode>;
  onConnect?: (connection: StubConnection) => void;
  onNodeClick?: (event: unknown, node: StubNode) => void;
  nodesConnectable?: boolean;
  children?: ReactNode;
}

interface StubHandleProps {
  id?: string;
  type?: string;
  position?: string;
  isConnectable?: boolean;
  className?: string;
  "data-testid"?: string;
}

export function createXyflowStub(): Record<string, unknown> {
  const Position = {
    Top: "top",
    Bottom: "bottom",
    Left: "left",
    Right: "right",
  } as const;

  const MarkerType = {
    Arrow: "arrow",
    ArrowClosed: "arrowclosed",
  } as const;

  const BackgroundVariant = {
    Dots: "dots",
    Lines: "lines",
    Cross: "cross",
  } as const;

  function ReactFlow(props: StubReactFlowProps): ReactNode {
    const nodes = props.nodes ?? [];
    const edges = props.edges ?? [];
    const nodeTypes = props.nodeTypes ?? {};
    const connectable = props.nodesConnectable !== false;

    return (
      <div
        data-testid="xyflow-stub"
        data-connectable={connectable ? "true" : "false"}
      >
        {nodes.map((node) => {
          const Component = node.type ? nodeTypes[node.type] : undefined;
          if (!Component) return null;
          return createElement(Component, {
            key: node.id,
            id: node.id,
            data: node.data,
            selected: false,
          });
        })}
        {edges.map((edge) => (
          <div
            key={edge.id}
            data-testid={`stub-edge-${edge.id}`}
            data-classname={edge.className ?? ""}
          />
        ))}
        {nodes.map((source) => (
          <button
            key={`select-${source.id}`}
            type="button"
            data-testid={`stub-select-${source.id}`}
            onClick={() => props.onNodeClick?.({}, source)}
          />
        ))}
        {connectable &&
          nodes.map((source) =>
            nodes.map((target) => (
              <button
                key={`connect-${source.id}-${target.id}`}
                type="button"
                data-testid={`stub-connect-${source.id}__${target.id}`}
                onClick={() =>
                  props.onConnect?.({
                    source: source.id,
                    target: target.id,
                    sourceHandle: null,
                    targetHandle: null,
                  })
                }
              />
            ))
          )}
        {props.children}
      </div>
    );
  }

  function ReactFlowProvider({ children }: { children?: ReactNode }): ReactNode {
    return <>{children}</>;
  }

  function Background(): ReactNode {
    return <div data-testid="xyflow-background" />;
  }

  function Controls(): ReactNode {
    return <div data-testid="xyflow-controls" />;
  }

  function MiniMap(): ReactNode {
    return <div data-testid="xyflow-minimap" />;
  }

  function Handle(props: StubHandleProps): ReactNode {
    return (
      <span
        data-testid={props["data-testid"]}
        data-handle-id={props.id}
        data-handle-type={props.type}
        data-handle-position={props.position}
        data-connectable={props.isConnectable === false ? "false" : "true"}
        className={props.className}
      />
    );
  }

  function useReactFlow(): Record<string, unknown> {
    return {
      fitView: () => undefined,
      zoomIn: () => undefined,
      zoomOut: () => undefined,
    };
  }

  return {
    ReactFlow,
    ReactFlowProvider,
    Background,
    BackgroundVariant,
    Controls,
    MiniMap,
    Handle,
    Position,
    MarkerType,
    useReactFlow,
  };
}
