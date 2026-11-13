export interface HermesNetworkAPI {
  fetch(url: string, options?: RequestInit): Promise<unknown>;
}

export interface Connection {
  baseUrl: string;
  apiKey: string;
  workspaceId: string;
}

export interface Workspace {
  id: string;
  name: string;
}

interface WorkspaceListResponse {
  count: number;
  next: string | null;
  previous: string | null;
  results: Workspace[];
}

// Backend errors go through rest_api/error_envelope.py and arrive nested:
// {"error": {"code", "message", "details"}}. Since the 2026-08-27 system audit
// (P1 item 13) auth failures use that same envelope — auth_tenancy/errors.py::
// build_error_body() used to emit a flat body where "error" was a plain string
// (the error code) rather than an object, with "doc_url" at the top level. A
// bad/expired API key now arrives as
// {"error": {"code": "invalid_api_key", "message": "...",
//            "details": [{"doc_url": "..."}]}}.
//
// The flat shape is still handled below on purpose, for two reasons: several
// REST modules outside that audit item's scope (auth_tenancy/
// rest_workspace_members.py, rest_item_permission.py, admin_ops/rest.py and
// banner_rest.py) still answer flat, and this plugin is versioned separately
// from the backend it talks to, so it may face an older server.
export interface NestedErrorEnvelope {
  error: {
    code: string;
    message: string;
    details: { field: string; errors: string[] }[];
  };
}

export interface FlatErrorEnvelope {
  error: string;
  message: string;
  doc_url?: string;
}

export type ErrorEnvelope = NestedErrorEnvelope | FlatErrorEnvelope;

function isNestedErrorEnvelope(envelope: ErrorEnvelope): envelope is NestedErrorEnvelope {
  return typeof envelope.error === "object" && envelope.error !== null;
}

function extractErrorMessage(envelope: ErrorEnvelope): string {
  return isNestedErrorEnvelope(envelope) ? envelope.error.message : envelope.message;
}

export class ReqogniLoomApiError extends Error {
  status: number;
  envelope: ErrorEnvelope | null;

  constructor(status: number, envelope: ErrorEnvelope | null, message: string) {
    super(message);
    this.name = "ReqogniLoomApiError";
    this.status = status;
    this.envelope = envelope;
  }
}

// api.network.fetch()'s actual return shape is ambiguous: the official Hermes
// Plugin API docs say it returns Promise<string> (response body as text, no
// HTTP status observable), but at least one reference plugin's own bundled
// type declares Promise<Response> instead. Handle both rather than gambling
// on one.
function isResponseLike(value: unknown): value is Response {
  return typeof value === "object" && value !== null && typeof (value as { text?: unknown }).text === "function";
}

async function parseNetworkResult(raw: unknown, label: string): Promise<{ status: number; body: unknown }> {
  if (typeof raw === "string") {
    let body: unknown = null;
    let parseError = false;
    try {
      body = raw ? JSON.parse(raw) : null;
    } catch {
      parseError = true;
      body = null;
    }
    // A non-empty string that fails to parse as JSON (e.g. a plain-text error
    // body from a proxy/502/504) must not be silently treated as success.
    if (parseError && raw !== "") {
      return { status: 0, body: null };
    }
    const isErrorShaped = !!(body && typeof body === "object" && "error" in (body as Record<string, unknown>));
    return { status: isErrorShaped ? 400 : 200, body };
  }
  if (!isResponseLike(raw)) {
    throw new Error(`${label} returned a non-Response value`);
  }
  const text = await raw.text();
  let body: unknown = null;
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    body = null;
  }
  return { status: raw.status, body };
}

const REQUEST_TIMEOUT_MS = 15_000;

async function reqloFetch(
  network: HermesNetworkAPI,
  baseUrl: string,
  apiKey: string,
  path: string,
  options: RequestInit = {}
): Promise<unknown> {
  // `path` is normally app-relative, but a paginated `next` link is an
  // absolute URL built by DRF — accept both so the pagination loop can pass
  // `next` straight through.
  const url = /^https?:\/\//i.test(path) ? path : `${baseUrl.replace(/\/$/, "")}${path}`;
  const raw = await network.fetch(url, {
    ...options,
    signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
    headers: {
      "X-API-Key": apiKey,
      "Content-Type": "application/json",
      ...(options.headers as Record<string, string> | undefined),
    },
  });
  const { status, body } = await parseNetworkResult(raw, `${options.method ?? "GET"} ${path}`);
  if (status < 200 || status >= 300) {
    const envelope =
      body && typeof body === "object" && "error" in (body as Record<string, unknown>)
        ? (body as ErrorEnvelope)
        : null;
    throw new ReqogniLoomApiError(status, envelope, envelope ? extractErrorMessage(envelope) : `HTTP ${status}`);
  }
  return body;
}

export async function listWorkspaces(
  network: HermesNetworkAPI,
  credentials: { baseUrl: string; apiKey: string }
): Promise<Workspace[]> {
  const path = "/api/v1/workspaces/";
  const workspaces: Workspace[] = [];
  // Follow `next` to the last page so a workspace beyond the first page is
  // reachable (PLUG-02). A repeated `next` ends the chain, so a misbehaving
  // server cannot spin this loop forever.
  const seen = new Set<string>();
  let next: string | null = path;
  while (next) {
    if (seen.has(next)) {
      break;
    }
    seen.add(next);
    const body: unknown = await reqloFetch(network, credentials.baseUrl, credentials.apiKey, next);
    if (typeof body !== "object" || body === null || !Array.isArray((body as { results?: unknown }).results)) {
      throw new ReqogniLoomApiError(200, null, `GET ${path} returned a body with no results array`);
    }
    const page = body as WorkspaceListResponse;
    workspaces.push(...page.results);
    next = typeof page.next === "string" && page.next.length > 0 ? page.next : null;
  }
  return workspaces;
}

// ---------------------------------------------------------------------------
// Requirements — confirmed wire contract (Phase H / #1701, Task 1)
//
// Verified against backend/rest_api/serializers.py::RequirementSerializer,
// rest_api/views.py::RequirementViewSet and rest_api/mixins/*:
//
// Writable on create: workspace_id (always taken from `Connection`, never from
// the call site — see createRequirement), parent_id, title, description,
// rationale, source, acceptance_criteria, category, type,
// complexity_fibonacci, verification_method, acceptance_criteria_items.
// Writable on update only: change_reason, level_override.
// Read-only: id, artifact_id, global_uuid, uid, level, tier_key, tier_name,
//   released_tier_key, level_source, suspect, allocation_intent*,
//   atomicity_warning, version, status, created_at, updated_at.
//
// Three deviations from the pre-#1701 plan are deliberate:
//
// 1. `level` is DERIVED (ADR-005 / ADR-027): it is recomputed from the
//    hierarchy on every hierarchy change, and `RequirementViewSet.create`/
//    `partial_update` answer a field-level 400 for a *differing* value. No
//    request built here carries it. `level_override` (1..4, write-only) is the
//    only manual path; this plugin does not offer it — the form has no level
//    field, so the value stays whatever the hierarchy derives.
// 2. `allocation_intent` is a *writable* ChoiceField in the serializer, but
//    this plugin treats it as read-only and never sends it: allocations are
//    out of scope for Phase H.
// 3. Optimistic locking is enforced under a different key than it is read.
//    The response field is `version`; the field the RequirementViewSet
//    actually honours is `expected_version`
//    (rest_api/mixins/etag.py::resolve_expected_version — the same value can
//    ride as `If-Match`). Echoing `version` back as `version` is silently
//    ignored (DRF drops read-only fields on write), which would make every
//    update last-writer-wins — exactly what the guard exists to prevent.
//    UpdateRequirementInput therefore carries `version` (the client-facing
//    name, the value the caller read) and updateRequirement renames it to
//    `expected_version` on the wire.
//
// `change_reason` is optional on the wire; in the standard/extended preset a
// PATCH without one is refused by RequirementService with a 400
// VALIDATION_ERROR ("change_reason required by workspace preset policy"). The
// UI turns that into a required field rather than a generic banner.
// ---------------------------------------------------------------------------

export type RequirementType = "SyReq" | "UseCase" | "FeatureReq";

export type VerificationMethod = "Test" | "Review" | "Analysis" | "Inspection" | "Demonstration";

/** Allocation intent (#P2). Read-only in this plugin — see the block above. */
export type AllocationIntent = "allocated" | "not_allocatable" | "unassigned";

/** One entry of the structured acceptance-criteria list (#1288). */
export interface AcceptanceCriterion {
  text: string;
  fulfilled?: boolean;
  evidence_ref?: string | null;
}

export interface Requirement {
  id: string;
  /** Canonical Artifact id — trace links use this, not `id` (#1270). */
  artifact_id: string | null;
  /** Stable global UUID (#1261); same value as `artifact_id`. */
  global_uuid?: string | null;
  workspace_id: string;
  parent_id: string | null;
  /** Workspace-local display id (REQ-…), reassigned on ReqIF import. */
  uid: string | null;
  title: string;
  description: string;
  rationale?: string;
  source?: string;
  acceptance_criteria: string;
  acceptance_criteria_items?: AcceptanceCriterion[];
  category: string;
  type: RequirementType;
  // Only present for type='SyReq' (to_representation drops them otherwise).
  complexity_fibonacci?: number | null;
  verification_method?: VerificationMethod | null;
  /** DERIVED V-model position (read-only, ADR-005). */
  level: number | null;
  tier_key: string | null;
  tier_name: string | null;
  released_tier_key?: string | null;
  /** 'derived' | 'manual' — provenance of `level` (#1289). */
  level_source: string;
  allocation_intent?: AllocationIntent;
  /** Workflow state, engine-resolved. Read-only: transitions own it. */
  status: string;
  suspect: boolean;
  /** Non-blocking IEEE 29148 §5.2.4 atomicity hint (#45). */
  atomicity_warning: string[] | null;
  version: number;
  custom_fields?: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface RequirementListResponse {
  count: number;
  next: string | null;
  previous: string | null;
  /** Serializer echoes the applied page size and its hard cap. */
  page_size?: number;
  max_page_size?: number;
  results: Requirement[];
}

export interface CreateRequirementInput {
  title: string;
  description?: string;
  acceptance_criteria?: string;
  category?: string;
  type?: RequirementType;
  complexity_fibonacci?: number;
  verification_method?: VerificationMethod;
  parent_id?: string;
}

/**
 * Update payload. `version` is the revision the caller last read (the
 * optimistic-lock guard); `change_reason` is mandatory in the standard and
 * extended presets.
 */
export type UpdateRequirementInput = Partial<CreateRequirementInput> & {
  version: number;
  change_reason?: string;
  /** Manual V-model override (1..4, `null` clears it). Not used by the form. */
  level_override?: number | null;
};

// What a write may actually carry. An allow-list (rather than filtering a
// spread of the caller's object) is what makes "never send `level`" a
// structural guarantee instead of a convention: a key that is not listed here
// cannot reach the request, even from an `as`-cast or a legacy call site.
const WRITABLE_REQUIREMENT_FIELDS = [
  "title",
  "description",
  "acceptance_criteria",
  "category",
  "type",
  "complexity_fibonacci",
  "verification_method",
  "parent_id",
] as const;

function pickWritableRequirementFields(input: CreateRequirementInput | UpdateRequirementInput): Record<string, unknown> {
  const body: Record<string, unknown> = {};
  for (const key of WRITABLE_REQUIREMENT_FIELDS) {
    const value = (input as Record<string, unknown>)[key];
    if (value !== undefined) {
      body[key] = value;
    }
  }
  return body;
}

function expectRequirementBody(body: unknown, label: string): Requirement {
  if (typeof body !== "object" || body === null || typeof (body as { id?: unknown }).id !== "string") {
    throw new ReqogniLoomApiError(200, null, `${label} returned a body with no requirement id`);
  }
  return body as Requirement;
}

export async function listRequirements(
  network: HermesNetworkAPI,
  connection: Connection,
  params: { search?: string; page?: number; pageSize?: number; url?: string } = {}
): Promise<RequirementListResponse> {
  // `url` is a `next`/`previous` link from a previous response: DRF builds it
  // as an absolute URL, so it is passed straight through (reqloFetch accepts
  // both absolute and app-relative paths) instead of being re-assembled from a
  // page number — that would drop any server-side ordering the link encodes.
  const path =
    params.url ??
    `/api/v1/requirements/?${new URLSearchParams({
      workspace_id: connection.workspaceId,
      page: String(params.page ?? 1),
      page_size: String(params.pageSize ?? 25),
      ...(params.search ? { search: params.search } : {}),
    }).toString()}`;
  const body = await reqloFetch(network, connection.baseUrl, connection.apiKey, path);
  if (typeof body !== "object" || body === null || !Array.isArray((body as { results?: unknown }).results)) {
    throw new ReqogniLoomApiError(200, null, `GET ${path} returned a body with no results array`);
  }
  return body as RequirementListResponse;
}

export async function getRequirement(
  network: HermesNetworkAPI,
  connection: Connection,
  id: string
): Promise<Requirement> {
  const path = `/api/v1/requirements/${encodeURIComponent(id)}/`;
  const body = await reqloFetch(network, connection.baseUrl, connection.apiKey, path);
  return expectRequirementBody(body, `GET ${path}`);
}

export async function createRequirement(
  network: HermesNetworkAPI,
  connection: Connection,
  input: CreateRequirementInput
): Promise<Requirement> {
  const path = "/api/v1/requirements/";
  const body = await reqloFetch(network, connection.baseUrl, connection.apiKey, path, {
    method: "POST",
    body: JSON.stringify({ ...pickWritableRequirementFields(input), workspace_id: connection.workspaceId }),
  });
  return expectRequirementBody(body, `POST ${path}`);
}

export async function updateRequirement(
  network: HermesNetworkAPI,
  connection: Connection,
  id: string,
  input: UpdateRequirementInput
): Promise<Requirement> {
  const path = `/api/v1/requirements/${encodeURIComponent(id)}/`;
  const body = await reqloFetch(network, connection.baseUrl, connection.apiKey, path, {
    method: "PATCH",
    body: JSON.stringify({
      ...pickWritableRequirementFields(input),
      // The server compares `expected_version`, not the read-back `version`.
      expected_version: input.version,
      ...(input.change_reason !== undefined ? { change_reason: input.change_reason } : {}),
      ...(input.level_override !== undefined ? { level_override: input.level_override } : {}),
    }),
  });
  return expectRequirementBody(body, `PATCH ${path}`);
}


