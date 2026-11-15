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

// ---------------------------------------------------------------------------
// Reading view (R4, plan 2026-11-15-document-view-on-document.md)
//
// Mirrors `DocumentReadingSerializer` / `DocumentViewResult.to_dict()`
// (backend/rest_api/serializers.py, backend/application/
// document_reading_service.py). The object is read-only by construction:
// writes stay on `PATCH /api/v1/documents/{id}/`.
// ---------------------------------------------------------------------------

/** One chapter of the reading view (`application.markdown_chapters.Chapter`). */
export interface ReadingChapter {
  /** Display number ("1", "1.1"); empty for the unnumbered preamble. */
  number: string;
  /** Heading level 1..3, or 0 for the text before the first heading. */
  level: number;
  /** Heading text without the leading `#`s; empty for the preamble. */
  title: string;
  /** Stable, document-unique slug used as the DOM id. */
  anchor: string;
  /** Chapter Markdown without its heading (and without subsections). */
  body: string;
}

/** Why a document field is not writable (`DocumentReadingLockedSerializer`). */
export interface ReadingLockedField {
  /** `PERMISSION` | `REPO_EXTERNAL` | `FIELD_FROZEN`. */
  code: string;
  /** Human sentence the surface shows without inventing its own wording. */
  detail: string;
}

/** One field of the reading view plus its write verdict (`fields[]`). */
export interface ReadingField {
  /** `title` | `description` | `body` | `doc_date` | `custom_fields`. */
  name: string;
  /** Polymorphic wire value: string, ISO date, or the `custom_fields` map. */
  value: unknown;
  /** Matches what `PATCH /documents/{id}/` actually accepts. */
  editable: boolean;
  locked: ReadingLockedField | null;
}

/** Document-level write capability of the caller (`capabilities`). */
export interface ReadingCapabilities {
  can_write: boolean;
  /** `PERMISSION` | `REPO_EXTERNAL` when nothing may be written, else `null`. */
  read_only_reason: string | null;
}

/** Read-only projection bookkeeping (`projection`). */
export interface ReadingProjection {
  projection_mode: string;
  source_path: string;
  projected_sha256: string;
}

/**
 * Response of `GET /api/v1/documents/{id}/view/` — the chaptered reading
 * object. Flat on purpose: every key here has a consumer on the surface.
 */
export interface DocumentReading {
  id: UUID;
  artifact_id: UUID | null;
  uid: string | null;
  title: string;
  kind: DocumentKind;
  description: string;
  /** Full Markdown body; `chapters` is the split view of it. */
  body: string;
  doc_date: string | null;
  version: number;
  status: string;
  frozen_at: ISODateTime | null;
  frozen_fields: string[];
  /** Flat list of field names reported as editable in `fields`. */
  editable_fields: string[];
  fields: ReadingField[];
  capabilities: ReadingCapabilities;
  chapters: ReadingChapter[];
  projection: ReadingProjection;
}
