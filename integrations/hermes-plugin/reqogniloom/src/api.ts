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

export type RequirementType = "SyReq" | "UseCase" | "FeatureReq";
export type VerificationMethod = "Test" | "Review" | "Analysis" | "Inspection" | "Demonstration";

export interface Requirement {
  id: string;
  workspace_id: string;
  parent_id: string | null;
  title: string;
  description: string;
  acceptance_criteria: string;
  category: string;
  status: string;
  type: RequirementType;
  complexity_fibonacci: number | null;
  verification_method: VerificationMethod | null;
  level: number | null;
  uid: string | null;
  version: number;
  change_reason?: string;
  created_at: string;
  updated_at: string;
}

export interface RequirementListResponse {
  count: number;
  next: string | null;
  previous: string | null;
  results: Requirement[];
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

export interface CreateRequirementInput {
  title: string;
  description?: string;
  acceptance_criteria?: string;
  category?: string;
  type?: RequirementType;
  complexity_fibonacci?: number;
  verification_method?: VerificationMethod;
  level?: number;
  parent_id?: string;
}

export type UpdateRequirementInput = Partial<CreateRequirementInput> & { change_reason?: string };

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

// api.network.fetch()'s actual return shape is ambiguous: the official docs
// (hermes-hq/plugins/docs/PLUGIN-API.md, checked 2026-08-13) say it returns
// Promise<string> (response body as text, no status code observable), but
// the `github` reference plugin's own bundled HermesPluginAPI type declares
// Promise<Response> instead. Handle both rather than gambling on one — see
// plan Task 9 for where this gets confirmed empirically against a real
// Hermes IDE build.
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
    // If raw is non-empty but failed to parse as JSON (e.g., plain-text error body),
    // treat it as a failure to avoid silently returning null as a successful response.
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

export async function listRequirements(
  network: HermesNetworkAPI,
  connection: Connection,
  params: { search?: string; page?: number; pageSize?: number } = {}
): Promise<RequirementListResponse> {
  const query = new URLSearchParams();
  query.set("workspace_id", connection.workspaceId);
  query.set("page", String(params.page ?? 1));
  query.set("page_size", String(params.pageSize ?? 25));
  if (params.search) query.set("search", params.search);
  const body = await reqloFetch(
    network,
    connection.baseUrl,
    connection.apiKey,
    `/api/v1/requirements/?${query.toString()}`
  );
  return body as RequirementListResponse;
}

export async function getRequirement(
  network: HermesNetworkAPI,
  connection: Connection,
  id: string
): Promise<Requirement> {
  const body = await reqloFetch(network, connection.baseUrl, connection.apiKey, `/api/v1/requirements/${id}/`);
  return body as Requirement;
}

export async function createRequirement(
  network: HermesNetworkAPI,
  connection: Connection,
  input: CreateRequirementInput
): Promise<Requirement> {
  const body = await reqloFetch(network, connection.baseUrl, connection.apiKey, "/api/v1/requirements/", {
    method: "POST",
    body: JSON.stringify({ ...input, workspace_id: connection.workspaceId }),
  });
  return body as Requirement;
}

export async function updateRequirement(
  network: HermesNetworkAPI,
  connection: Connection,
  id: string,
  input: UpdateRequirementInput
): Promise<Requirement> {
  const body = await reqloFetch(network, connection.baseUrl, connection.apiKey, `/api/v1/requirements/${id}/`, {
    method: "PATCH",
    body: JSON.stringify(input),
  });
  return body as Requirement;
}
