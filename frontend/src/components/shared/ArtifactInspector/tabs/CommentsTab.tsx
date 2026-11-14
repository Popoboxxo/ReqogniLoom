/**
 * ArtifactInspector — "Comments" tab (issue #1762, M1).
 *
 * leaf_id: COMP-RF-014 (ArtifactInspector)
 * req_id:  REQ-L1-089
 *
 * Mounted only when the route handed over the backing generic Artifact UUID
 * (`artifactPk`). A kind without that UUID gets no comments tab at all — the
 * tab list is built from `inspectorTabKeys(kind, artifactPk)`, so this
 * component never has to render a "not available" state (spec §4.3).
 */

import { CommentPanel } from "../CommentPanel";
import type { ArtifactKind } from "../types";

export interface CommentsTabProps {
  kind: ArtifactKind;
  /** Backing generic Artifact UUID — never the domain-entity id (D5). */
  artifactPk: string;
}

export function CommentsTab({ kind, artifactPk }: CommentsTabProps): JSX.Element {
  return <CommentPanel kind={kind} artifactId={artifactPk} variant="tab" />;
}
