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

// A JSON-RPC error frame carries a non-null `error` *object*; `error: null`
// (or a primitive) is not an error frame. The previous `"error" in frame`
// check accepted `{jsonrpc,id,error:null}`, which then blew up in
// callMcpTool()'s `frame.error.code` access with a TypeError instead of a
// catchable McpRpcError.
function isJsonRpcError(frame: unknown): frame is JsonRpcError {
  if (typeof frame !== "object" || frame === null) return false;
  const candidate = (frame as { error?: unknown }).error;
  return typeof candidate === "object" && candidate !== null;
}

function isJsonRpcSuccess(frame: unknown): frame is JsonRpcSuccess {
  return typeof frame === "object" && frame !== null && !isJsonRpcError(frame) && "result" in frame;
}

function isResponseLike(value: unknown): value is Response {
  return typeof value === "object" && value !== null && typeof (value as { text?: unknown }).text === "function";
}

// Mirrors api.ts's parseNetworkResult -- network.fetch's actual return shape
// is ambiguous (raw string vs. Response-like object) per the Hermes plugin
// API's own inconsistent documentation; both must be handled rather than
// gambling on one. Duplicated rather than imported from api.ts because that
// function's REST-specific status-inference (isErrorShaped -> 400) doesn't
// apply here -- JSON-RPC always answers 200 with an error *object* inside a
// 200 body, never via HTTP status.
async function readBody(raw: unknown, toolName: string): Promise<string> {
  if (typeof raw === "string") return raw;
  if (!isResponseLike(raw)) {
    throw new Error(`MCP call to ${toolName} returned a non-Response value`);
  }
  return raw.text();
}

let requestCounter = 0;

const REQUEST_TIMEOUT_MS = 15_000;

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
    signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
  });

  const text = await readBody(raw, toolName);
  let frame: unknown;
  try {
    frame = JSON.parse(text) as unknown;
  } catch {
    throw new Error(`MCP call to ${toolName} returned non-JSON response: ${text.slice(0, 200)}`);
  }

  if (isJsonRpcError(frame)) {
    throw new McpRpcError(frame.error.code, frame.error.message, frame.error.data);
  }
  if (!isJsonRpcSuccess(frame)) {
    throw new McpRpcError(-32603, `MCP call to ${toolName} returned a JSON-RPC frame with no result field`);
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
  // NULL backend-side for multi-artifact discovery sessions only
  // (persistence/models.py), and interview.list does not filter on session
  // kind, so this plugin can see sessions it cannot resume by type.
  artifact_type: string | null;
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
  const result: unknown = await callMcpTool(network, connection, "interview.list", params);
  if (typeof result !== "object" || result === null || !Array.isArray((result as { sessions?: unknown }).sessions)) {
    throw new McpRpcError(-32603, "MCP call to interview.list returned a result with no sessions array");
  }
  return (result as { sessions: InterviewSummary[] }).sessions;
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

// GitHub #1152: interview.abandon is registered server-side (write-gated),
// so Cancel can actually end the session instead of leaving it in_progress.
export async function interviewAbandon(
  network: HermesNetworkAPI,
  connection: Connection,
  sessionId: string
): Promise<InterviewState> {
  return callMcpTool(network, connection, "interview.abandon", {
    session_id: sessionId,
  }) as Promise<InterviewState>;
}

// ---------------------------------------------------------------------------
// Memory (AI long-term memory) MCP tools
// ---------------------------------------------------------------------------
//
// Backend contract (backend/mcp_server/tools/memory.py): tool names use DOTS
// (`memory.query`, not `memory.query` under a group namespace). Every read
// envelope carries `backend`, `ok`, `detail` and `degraded` -- F9's whole
// point is that a read which legitimately returns no rows still answers
// `degraded=true` when the backend is unhealthy, so a client can tell
// "nothing remembered" apart from "backend down". `detail` carries the
// degradation cause. `digest_available`/`ask_available` are passed through as
// capability flags (pgvector reports `ask_available=false` because it degrades
// `ask` by design); the panel currently always renders the Ask control and
// relies on `degraded`/`detail` to explain a degraded answer rather than
// hiding the surface, so no consumer reads these two flags yet.

export type MemoryScope = "workspace" | "user" | "artifact";

export interface MemoryEntry {
  entry_id: string;
  content: string;
  scope: MemoryScope;
  workspace_id?: string | null;
  user_id?: string | null;
  artifact_id?: string | null;
  entity_type?: string | null;
  contributor_user_id?: string | null;
  source_event_id?: string | null;
  source_session_id?: string | null;
  confidence?: number | null;
  language?: string | null;
  created_at?: string | null;
  degraded?: boolean;
  detail?: string | null;
  [key: string]: unknown;
}

export interface MemoryQueryResult {
  entries: MemoryEntry[];
  query?: string;
  scopes?: MemoryScope[];
  backend?: string;
  ok?: boolean;
  detail?: string | null;
  degraded?: boolean;
  digest_available?: boolean;
  ask_available?: boolean;
  derivation_status?: string;
}

export interface MemoryDigestResult {
  digest: string;
  generated_at?: string;
  backend?: string;
  degraded?: boolean;
  derivation_status?: string;
  derived_count?: number | null;
}

export interface MemoryAskResult {
  answer: string;
  generated_at?: string;
  backend?: string;
  degraded?: boolean;
  detail?: string | null;
}

export interface MemoryQueryParams {
  query: string;
  scope?: MemoryScope;
  scopes?: MemoryScope[];
  workspace_id?: string;
  artifact_id?: string;
  top_k?: number;
}

export interface MemoryDigestParams {
  workspace_id: string;
  artifact_id?: string;
}

export interface MemoryAskParams {
  query: string;
  workspace_id: string;
  artifact_id?: string;
  reasoning_level?: "minimal" | "low" | "medium" | "high" | "max";
}

export interface MemoryWriteParams {
  content: string;
  scope: MemoryScope;
  workspace_id?: string;
  artifact_id?: string;
  confidence?: number;
  change_reason?: string;
}

function requireObjectResult(result: unknown, toolName: string): Record<string, unknown> {
  if (typeof result !== "object" || result === null) {
    throw new McpRpcError(-32603, `MCP call to ${toolName} returned a non-object result`);
  }
  return result as Record<string, unknown>;
}

export async function memoryQuery(
  network: HermesNetworkAPI,
  connection: Connection,
  params: MemoryQueryParams
): Promise<MemoryQueryResult> {
  const result = requireObjectResult(
    await callMcpTool(network, connection, "memory.query", {
      query: params.query,
      ...(params.scope !== undefined ? { scope: params.scope } : {}),
      ...(params.scopes !== undefined ? { scopes: params.scopes } : {}),
      ...(params.workspace_id !== undefined ? { workspace_id: params.workspace_id } : {}),
      ...(params.artifact_id !== undefined ? { artifact_id: params.artifact_id } : {}),
      ...(params.top_k !== undefined ? { top_k: params.top_k } : {}),
    }),
    "memory.query"
  );
  if (!Array.isArray(result.entries)) {
    throw new McpRpcError(-32603, "MCP call to memory.query returned a result with no entries array");
  }
  return result as unknown as MemoryQueryResult;
}

export async function memoryDigest(
  network: HermesNetworkAPI,
  connection: Connection,
  params: MemoryDigestParams
): Promise<MemoryDigestResult> {
  const result = requireObjectResult(
    await callMcpTool(network, connection, "memory.digest", {
      workspace_id: params.workspace_id,
      ...(params.artifact_id !== undefined ? { artifact_id: params.artifact_id } : {}),
    }),
    "memory.digest"
  );
  if (typeof result.digest !== "string") {
    throw new McpRpcError(-32603, "MCP call to memory.digest returned a result with no digest string");
  }
  return result as unknown as MemoryDigestResult;
}

export async function memoryAsk(
  network: HermesNetworkAPI,
  connection: Connection,
  params: MemoryAskParams
): Promise<MemoryAskResult> {
  const result = requireObjectResult(
    await callMcpTool(network, connection, "memory.ask", {
      query: params.query,
      workspace_id: params.workspace_id,
      ...(params.artifact_id !== undefined ? { artifact_id: params.artifact_id } : {}),
      ...(params.reasoning_level !== undefined ? { reasoning_level: params.reasoning_level } : {}),
    }),
    "memory.ask"
  );
  if (typeof result.answer !== "string") {
    throw new McpRpcError(-32603, "MCP call to memory.ask returned a result with no answer string");
  }
  return result as unknown as MemoryAskResult;
}

// memory.write is the only memory tool that mutates server state and the only
// one RBAC write-gated on the backend. This wrapper deliberately performs no
// auto-submit -- the caller (state.ts) only invokes it after the user has
// explicitly confirmed a reviewed draft.
export async function memoryWrite(
  network: HermesNetworkAPI,
  connection: Connection,
  params: MemoryWriteParams
): Promise<MemoryEntry> {
  const result = requireObjectResult(
    await callMcpTool(network, connection, "memory.write", {
      content: params.content,
      scope: params.scope,
      ...(params.workspace_id !== undefined ? { workspace_id: params.workspace_id } : {}),
      ...(params.artifact_id !== undefined ? { artifact_id: params.artifact_id } : {}),
      ...(params.confidence !== undefined ? { confidence: params.confidence } : {}),
      ...(params.change_reason !== undefined ? { change_reason: params.change_reason } : {}),
    }),
    "memory.write"
  );
  return result as unknown as MemoryEntry;
}
