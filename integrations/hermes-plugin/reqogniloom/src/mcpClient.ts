import type { Connection } from "./api";

export interface HermesNetworkAPI {
  fetch(url: string, options?: RequestInit): Promise<unknown>;
}

export class McpRpcError extends Error {
  code: number;
  data?: unknown;

  constructor(code: number, message: string, data?: unknown) {
    super(message);
    this.name = "McpRpcError";
    this.code = code;
    this.data = data;
  }
}

interface JsonRpcSuccess {
  jsonrpc: "2.0";
  id: number;
  result: unknown;
}

interface JsonRpcError {
  jsonrpc: "2.0";
  id: number;
  error: { code: number; message: string; data?: unknown };
}

type JsonRpcResponse = JsonRpcSuccess | JsonRpcError;

function isJsonRpcError(frame: JsonRpcResponse): frame is JsonRpcError {
  return "error" in frame;
}

// Mirrors api.ts's parseNetworkResult -- network.fetch's actual return shape
// is ambiguous (raw string vs. Response-like object) per the Hermes plugin
// API's own inconsistent documentation; both must be handled rather than
// gambling on one. Duplicated rather than imported from api.ts because that
// function's REST-specific status-inference (isErrorShaped -> 400) doesn't
// apply here -- JSON-RPC always answers 200 with an error *object* inside a
// 200 body, never via HTTP status.
async function readBody(raw: unknown): Promise<string> {
  if (typeof raw === "string") return raw;
  const res = raw as Response;
  return res.text();
}

let requestCounter = 0;

export async function callMcpTool(
  network: HermesNetworkAPI,
  connection: Connection,
  toolName: string,
  params: Record<string, unknown>
): Promise<unknown> {
  const url = `${connection.baseUrl.replace(/\/$/, "")}/mcp/`;
  const id = ++requestCounter;

  const raw = await network.fetch(url, {
    method: "POST",
    headers: {
      "X-API-Key": connection.apiKey,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ jsonrpc: "2.0", id, method: toolName, params }),
  });

  const text = await readBody(raw);
  let frame: JsonRpcResponse;
  try {
    frame = JSON.parse(text) as JsonRpcResponse;
  } catch {
    throw new Error(`MCP call to ${toolName} returned non-JSON response: ${text.slice(0, 200)}`);
  }

  if (isJsonRpcError(frame)) {
    throw new McpRpcError(frame.error.code, frame.error.message, frame.error.data);
  }
  return frame.result;
}

export interface InterviewField {
  name: string;
  type: "text" | "textarea" | "enum" | "number";
  choices: string[] | null;
}

export interface InterviewState {
  session_id: string;
  status: "in_progress" | "completed" | "abandoned";
  phase: string;
  collected_fields: Record<string, unknown>;
  missing_fields: InterviewField[];
  grounding_snapshot: { candidates?: { artifact_id: string; title: string; score: number | null }[] };
}

export interface InterviewSummary {
  id: string;
  workspace_id: string;
  artifact_type: string;
  status: string;
}

export async function interviewStart(
  network: HermesNetworkAPI,
  connection: Connection,
  artifactType: string
): Promise<InterviewState> {
  return callMcpTool(network, connection, "interview.start", {
    artifact_type: artifactType,
    workspace_id: connection.workspaceId,
  }) as Promise<InterviewState>;
}

export async function interviewGetState(
  network: HermesNetworkAPI,
  connection: Connection,
  sessionId: string
): Promise<InterviewState> {
  return callMcpTool(network, connection, "interview.get_state", {
    session_id: sessionId,
  }) as Promise<InterviewState>;
}

export async function interviewAnswer(
  network: HermesNetworkAPI,
  connection: Connection,
  sessionId: string,
  field: string,
  value: unknown
): Promise<InterviewState> {
  return callMcpTool(network, connection, "interview.answer", {
    session_id: sessionId,
    field,
    value,
  }) as Promise<InterviewState>;
}

export async function interviewGroundingContext(
  network: HermesNetworkAPI,
  connection: Connection,
  sessionId: string
): Promise<InterviewState["grounding_snapshot"]> {
  return callMcpTool(network, connection, "interview.grounding_context", {
    session_id: sessionId,
  }) as Promise<InterviewState["grounding_snapshot"]>;
}

export async function interviewFormalize(
  network: HermesNetworkAPI,
  connection: Connection,
  sessionId: string
): Promise<{ resulting_artifact_ids: string[]; status: string }> {
  return callMcpTool(network, connection, "interview.formalize", {
    session_id: sessionId,
  }) as Promise<{ resulting_artifact_ids: string[]; status: string }>;
}

export async function interviewList(
  network: HermesNetworkAPI,
  connection: Connection,
  status?: string
): Promise<InterviewSummary[]> {
  const params: Record<string, unknown> = { workspace_id: connection.workspaceId };
  if (status) params.status = status;
  const result = (await callMcpTool(network, connection, "interview.list", params)) as {
    sessions: InterviewSummary[];
  };
  return result.sessions;
}

export async function interviewSetTarget(
  network: HermesNetworkAPI,
  connection: Connection,
  sessionId: string,
  artifactId: string
): Promise<InterviewState> {
  return callMcpTool(network, connection, "interview.set_target", {
    session_id: sessionId,
    artifact_id: artifactId,
  }) as Promise<InterviewState>;
}

export async function interviewGet(
  network: HermesNetworkAPI,
  connection: Connection,
  sessionId: string
): Promise<InterviewSummary> {
  return callMcpTool(network, connection, "interview.get", {
    session_id: sessionId,
  }) as Promise<InterviewSummary>;
}
