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
async function parseNetworkResult(raw: unknown): Promise<{ status: number; body: unknown }> {
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
  const res = raw as Response;
  const text = await res.text();
  let body: unknown = null;
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    body = null;
  }
  return { status: res.status, body };
}

async function reqloFetch(
  network: HermesNetworkAPI,
  baseUrl: string,
  apiKey: string,
  path: string,
  options: RequestInit = {}
): Promise<unknown> {
  const url = `${baseUrl.replace(/\/$/, "")}${path}`;
  const raw = await network.fetch(url, {
    ...options,
    headers: {
      "X-API-Key": apiKey,
      "Content-Type": "application/json",
      ...(options.headers as Record<string, string> | undefined),
    },
  });
  const { status, body } = await parseNetworkResult(raw);
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
  const body = await reqloFetch(network, credentials.baseUrl, credentials.apiKey, "/api/v1/workspaces/");
  return (body as WorkspaceListResponse).results;
}
