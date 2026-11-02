/**
 * ARCH-L1-001 ReactFrontend — Document artifact types (Plan F F2-T8, ADR-026).
 *
 * Mirrors `DocumentSerializer` (backend/rest_api/serializers.py). The
 * lifecycle state is exposed as the read-only `status` by the shared
 * `WorkflowStateSerializerMixin`; soft delete lives on the backing Artifact,
 * so a soft-deleted document still returns `status: "outdated"`.
 */

import type { CustomFields, ISODateTime, UUID } from "./common";

/** `persistence.models.Document.Kind` — the seven document kinds. */
export type DocumentKind =
  | "Spec"
  | "Plan"
  | "AuditReport"
  | "Review"
  | "Conclusion"
  | "Concept"
  | "Guide";

/** Every kind, in the backend's declaration order. */
export const DOCUMENT_KINDS: readonly DocumentKind[] = [
  "Spec",
  "Plan",
  "AuditReport",
  "Review",
  "Conclusion",
  "Concept",
  "Guide",
] as const;

export interface Document {
  id: UUID;
  workspace_id: UUID;
  /** Backing Artifact id — needed to attach trace links and comments. */
  artifact_id?: UUID | null;
  /** Local readable identifier (`DOC-NNN`), server-allocated. */
  uid?: string | null;
  title: string;
  kind: DocumentKind;
  description: string;
  /** Markdown content. */
  body: string;
  /** ISO date, e.g. derived from a source file name. */
  doc_date?: string | null;
  /** Set when the document entered `Freigegeben` (F-1). */
  frozen_at?: string | null;
  /** Content fields locked by the release (F-1/F-2). */
  frozen_fields: string[];
  custom_fields?: CustomFields;
  /** Workflow state from `WorkflowItemState` (`Entwurf`, `Freigegeben`, …). */
  status: string;
  /** Optimistic-lock counter — the ETag source, not a content revision. */
  version: number;
  created_at: ISODateTime;
  updated_at: ISODateTime;
}
