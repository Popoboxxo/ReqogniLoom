/**
 * P5 Task 5.2/5.3 — requirement card.
 *
 * Left band of the allocation graph. Shows the configured fields, the three
 * mandatory markers (lock/finding/unallocated) and — in edit mode with write
 * authority only — the allocation handle plus the keyboard "Allokieren auf …"
 * button. A frozen requirement gets no allocation handle at all (P4: the
 * requirement's state decides).
 */

import { Handle, Position } from "@xyflow/react";

import {
  CardActions,
  CardFieldRows,
  CardMarkers,
} from "./card-parts";
import { primaryCardField } from "./cardFields";
import type { AllocationCardData } from "./types";
import styles from "./AllocationGraph.module.css";

export interface AllocationCardProps {
  nodeId: string;
  data: AllocationCardData;
}

export function RequirementCard({ nodeId, data }: AllocationCardProps): JSX.Element {
  const { row } = data;
  const primary = primaryCardField(data.cardFields);

  return (
    <article
      className={[
        styles.card,
        styles.requirementCard,
        data.selected ? styles.cardSelected : "",
        data.dimmed ? styles.cardDimmed : "",
        data.frozen ? styles.cardFrozen : "",
      ]
        .filter(Boolean)
        .join(" ")}
      data-testid={`req-card-${row.id}`}
      data-card-kind="requirement"
      data-frozen={data.frozen ? "true" : "false"}
      data-selected={data.selected ? "true" : "false"}
      data-dimmed={data.dimmed ? "true" : "false"}
      data-node-id={nodeId}
    >
      {/* Invisible hierarchy anchors keep the grey parent/child edges
          attachable; they are never interactive. */}
      <Handle
        type="target"
        position={Position.Top}
        id="hierarchy-in"
        className={styles.hierarchyHandle}
        isConnectable={false}
      />
      <Handle
        type="source"
        position={Position.Bottom}
        id="hierarchy-out"
        className={styles.hierarchyHandle}
        isConnectable={false}
      />
      {data.editMode && !data.frozen && (
        <Handle
          type="source"
          position={Position.Right}
          id="allocate"
          className={styles.allocateHandle}
          data-testid={`req-allocate-handle-${row.id}`}
          isConnectable
        />
      )}

      <header className={styles.cardHeader}>
        {primary && (
          <span className={styles.cardPrimary} title={row.title}>
            {primary === "title" ? row.title : row.id}
          </span>
        )}
        <CardMarkers data={data} />
      </header>

      <CardFieldRows
        row={row}
        config={data.cardFields}
        allocationCount={data.allocationCount}
        exclude={primary ?? undefined}
      />
      <CardActions nodeId={nodeId} data={data} />
    </article>
  );
}
