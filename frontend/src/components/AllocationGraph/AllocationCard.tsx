/**
 * P5 Task 5.3 — single React Flow node type registered for the graph.
 *
 * `buildGraph` emits `type: 'allocationCard'` for both bands; this dispatcher
 * picks the requirement or element presentation by the row's kind.
 */

import { memo } from "react";
import type { NodeProps } from "@xyflow/react";

import { ElementCard } from "./ElementCard";
import { RequirementCard } from "./RequirementCard";
import type { AllocationCardData } from "./types";

function AllocationCardComponent({ id, data }: NodeProps): JSX.Element {
  const card = data as unknown as AllocationCardData;
  return card.kind === "requirement" ? (
    <RequirementCard nodeId={id} data={card} />
  ) : (
    <ElementCard nodeId={id} data={card} />
  );
}

export const AllocationCard = memo(AllocationCardComponent);
