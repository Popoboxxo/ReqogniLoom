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
