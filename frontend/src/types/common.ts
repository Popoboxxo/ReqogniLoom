/**
 * Shared primitives and generic API envelope types.
 *
 * Split out of the monolithic `types/index.ts` (F-16); re-exported by the
 * `@/types` barrel so existing import paths stay stable. Definitions are
 * moved verbatim.
 */

// ---------------------------------------------------------------------------
// Primitives
// ---------------------------------------------------------------------------

export type UUID = string;
export type ISODateTime = string;

/**
 * #1266: how a version-bound glossary reference token
 * (`[[glossary:<uuid>@<revision>]]`) resolves in a rendered text field.
 * `pinned` = the revision stored in the token wins (drift is reported when the
 * term's head moved on); `always_head` = resolve against the current head.
 */
export type GlossaryReferenceMode = "pinned" | "always_head";

// ---------------------------------------------------------------------------
// Custom Fields (REQ-L2-AS-037) — user-defined flat key-value attributes,
// stored on the shared Artifact and exposed on every artifact-backed entity.
// ---------------------------------------------------------------------------

export type CustomFieldValue = string | number | boolean | null;

export type CustomFields = Record<string, CustomFieldValue>;

// ---------------------------------------------------------------------------
// Actor wire values (Attribut v3 WS2, #936, spec section 4)
//
// `owner`/`reporter` are artifact-level system fields of the `actor` attribute
// type; `priority` is the artifact-level `enum`. The wire form below is exactly
// what `ActorService.validate_actor_value` accepts (and what
// `ArtifactAttributeGateway.actor_to_value` emits):
//
//   single    {"kind": "user", "id": "<user-or-actor-uuid>"} | {"kind": "external", "name": "..."}
//   multiple  {"multiple": true, "items": [<single>, ...]}
// ---------------------------------------------------------------------------

/** One actor entry in the wire form the backend's `actor` validator accepts. */
export type ActorValue =
  | { kind: "user"; id: string; name?: string }
  | { kind: "external"; name: string };

/**
 * Artifact-level system fields every artifact type carries since WS2 (#936).
 * Optional on the entity interfaces because a type only exposes them once its
 * transport has been wired in (`SYSTEM_FIELDS_ENABLED_ITEM_TYPES`); the
 * resolved attribute definition decides whether the field is visible.
 */
export interface SystemFieldValues {
  owner?: ActorValue | null;
  reporter?: ActorValue | null;
  priority?: string | null;
}

// ---------------------------------------------------------------------------
// Paginated response (mirrors StandardPagination format)
// ---------------------------------------------------------------------------

export interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  /**
   * Page size actually applied by the backend (issue #571). Differs from the
   * requested `page_size` whenever that value exceeded the endpoint's
   * `max_page_size` — the clamp used to be silent. Optional because older
   * backends (and hand-built test fixtures) omit it.
   */
  page_size?: number;
  /** Hard upper bound the endpoint accepts for `page_size` (issue #571). */
  max_page_size?: number;
  results: T[];
}

// ---------------------------------------------------------------------------
// API error format (mirrors build_error_response)
// ---------------------------------------------------------------------------

export interface ApiErrorDetail {
  field?: string;
  errors?: string[];
}

export interface ApiError {
  error: {
    code: string;
    message: string;
    details: ApiErrorDetail[];
  };
}
