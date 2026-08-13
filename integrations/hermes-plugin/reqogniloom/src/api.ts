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

export interface ErrorEnvelope {
  error: {
    code: string;
    message: string;
    details: { field: string; errors: string[] }[];
  };
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
    throw new ReqogniLoomApiError(status, envelope, envelope?.error.message ?? `HTTP ${status}`);
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
