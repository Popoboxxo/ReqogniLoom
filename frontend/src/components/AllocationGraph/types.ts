/**
 * P5 Task 5.3 — the extra data the interactive card graph injects into the
 * pure model produced by `buildGraph`.
 *
 * `buildGraph` deliberately knows nothing about React, callbacks or the active
 * view/edit mode; `AllocationGraph` decorates each node with that information
 * at render time.
 */

import type { AllocationNodeData, AllocationRow } from "./buildGraph";
import type { CardFieldConfig } from "./cardFields";

export interface AllocationCardData extends AllocationNodeData {
  /** View/edit mode AND write authority combined — the card's write gate. */
  editMode: boolean;
  /** Field selection for this card kind. */
  cardFields: CardFieldConfig;
  /** Number of allocations touching this card (requirement 0/1, element N). */
  allocationCount: number;
  /** This card's connections are currently highlighted. */
  selected: boolean;
  /** Collapse/expand this card's descendants. */
  onToggleCollapse?: (nodeId: string) => void;
  /** Open the keyboard allocation picker for this requirement. */
  onOpenAllocator?: (row: AllocationRow) => void;
}
