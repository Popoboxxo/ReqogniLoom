/**
 * ProposalPreviewGraph — display-only React Flow preview of a multi-artifact
 * interview proposal (plan Task 10, docs/superpowers/plans/
 * 2026-08-24-multi-artifact-interview.md).
 *
 * Pure presentation: no interaction handlers, nodes/edges are derived from the
 * proposal via useMemo and rendered non-draggable/non-selectable. One node per
 * ProposalItem; links become labelled edges between zero-based item indices.
 */

import { useMemo } from "react";
import { ReactFlow, Background, type Edge, type Node, type NodeTypes, type EdgeTypes } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import type { ProposalItem } from "../../api/interviews";
import styles from "./ProposalPreviewGraph.module.css";

// Per-type border color as a plain CSS-module class (keeps the ui-ratchet
// inline-style ratchet untouched). Unknown types fall back to .typeDefault,
// mirroring getArtifactTypeColorVar()'s fallback token.
const TYPE_CLASS: Record<string, string> = {
  StakeholderNeed: styles.typeStakeholderNeed,
  Requirement: styles.typeRequirement,
  ArchitectureElement: styles.typeArchitectureElement,
  Risk: styles.typeRisk,
  TestCase: styles.typeTestCase,
  Adr: styles.typeAdr,
  Issue: styles.typeIssue,
  Goal: styles.typeGoal,
  GlossaryTerm: styles.typeGlossaryTerm,
};

// Defined at module scope -- React Flow needs a stable reference for
// NODE_TYPES/EDGE_TYPES across renders, same reasoning as GraphCanvas.tsx.
function ProposalNode({ data }: { data: { title: string; type: string } }) {
  return (
    <div className={`${styles.node} ${TYPE_CLASS[data.type] ?? styles.typeDefault}`}>
      <span className={styles.nodeType}>{data.type}</span>
      <span className={styles.nodeTitle}>{data.title}</span>
    </div>
  );
}

const NODE_TYPES: NodeTypes = { proposalNode: ProposalNode };
const EDGE_TYPES: EdgeTypes = {};

interface ProposalPreviewGraphProps {
  proposal: ProposalItem[];
}

export function ProposalPreviewGraph({ proposal }: ProposalPreviewGraphProps): JSX.Element {
  const nodes: Node[] = useMemo(
    () =>
      proposal.map((item, index) => ({
        id: String(index),
        type: "proposalNode",
        position: { x: (index % 3) * 220, y: Math.floor(index / 3) * 120 },
        data: { title: item.title, type: item.type },
        draggable: false,
        selectable: false,
      })),
    [proposal]
  );

  const edges: Edge[] = useMemo(
    () =>
      proposal.flatMap((item, index) =>
        item.links.map((link, linkIndex) => ({
          id: `${index}-${link.from}-${link.to}-${linkIndex}`,
          source: String(link.from),
          target: String(link.to),
          label: link.type,
          selectable: false,
        }))
      ),
    [proposal]
  );

  return (
    <div className={styles.container} data-testid="proposal-preview-graph">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={NODE_TYPES}
        edgeTypes={EDGE_TYPES}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={false}
        fitView
      >
        <Background />
      </ReactFlow>
    </div>
  );
}
