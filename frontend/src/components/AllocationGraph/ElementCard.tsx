/**
 * P5 Task 5.2/5.3 — architecture-element card.
 *
 * Right band of the allocation graph. Frozen elements stay valid allocation
 * *targets* (P4 decides by the requirement's state), so the target handle is
 * available in edit mode even when the element itself is locked. Elements
 * never trigger a write on their own — no allocation button here.
 */

import { Handle, Position } from "@xyflow/react";

import { CardActions, CardFieldRows, CardMarkers } from "./card-parts";
import { primaryCardField } from "./cardFields";
import styles from "./AllocationGraph.module.css";
import type { AllocationCardProps } from "./RequirementCard";

export function ElementCard({ nodeId, data }: AllocationCardProps): JSX.Element {
  const { row } = data;
  const primary = primaryCardField(data.cardFields);

  return (
    <article
      className={[
        styles.card,
        styles.elementCard,
        data.selected ? styles.cardSelected : "",
        data.dimmed ? styles.cardDimmed : "",
        data.frozen ? styles.cardFrozen : "",
      ]
        .filter(Boolean)
        .join(" ")}
      data-testid={`el-card-${row.id}`}
      data-card-kind="element"
      data-frozen={data.frozen ? "true" : "false"}
      data-selected={data.selected ? "true" : "false"}
      data-dimmed={data.dimmed ? "true" : "false"}
      data-node-id={nodeId}
    >
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
      {data.editMode && (
        <Handle
          type="target"
          position={Position.Left}
          id="allocate"
          className={styles.allocateHandle}
          data-testid={`el-allocate-handle-${row.id}`}
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
