/**
 * ArtifactInspector — "Links" tab (issue #1762, M1).
 *
 * leaf_id: COMP-RF-014 (ArtifactInspector)
 * req_id:  REQ-L2-RF-037
 *
 * Spec §2.3 splits the trace surface by question, not by object:
 *
 *  - derivation/verification links (`derives-from`, `decomposes`, `refines`,
 *    `satisfies`, `realizes`, `allocated-to`, `verifies`) are read as rows
 *    **only** in the spine; this tab shows one summary line with a jump;
 *  - every other link type is read as rows **only** here.
 *
 * The partitioning itself lives in `TracePanel` (`variant="tab"`), because
 * that is the component that owns the fetch and the link-type catalog — a
 * second fetch here would be a second source of truth.
 */

import { TracePanel } from "../TracePanel";
import type { ArtifactKind } from "../types";

export interface LinksTabProps {
  kind: ArtifactKind;
  entityId: string | number;
  /** Jump to the spine (spec §2.3 rule 1). Omitted where there is no spine. */
  onShowInSpine?: () => void;
}

export function LinksTab({ kind, entityId, onShowInSpine }: LinksTabProps): JSX.Element {
  return (
    <TracePanel
      kind={kind}
      entityId={entityId}
      variant="tab"
      onShowInSpine={onShowInSpine}
    />
  );
}
