# Interview-Management Hermes Plugin Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a structured-form interview UI to the Hermes IDE plugin, driven by the `interview.*` MCP tool group over the plugin's existing REST-only network channel.

**Architecture:** A new minimal JSON-RPC 2.0 client (`mcpClient.ts`) POSTs to the backend's `/mcp/` HTTP transport (not the SSE one) using the same `X-API-Key` header the plugin's REST calls already send — no host-platform change needed. The panel renders the interview as a real form (one input per missing field, typed via `type`/`choices` from `interview.get_state`) instead of simulating a chat, because the panel is a real React surface and the field types are already structured data.

**Tech Stack:** TypeScript, React (Hermes plugin panel API), Vitest.

**Spec:** `docs/superpowers/specs/2026-08-14-interview-management-hermes-plugin-design.md` (Spec 2 of 3).

## Global Constraints

- **Hard dependency on the engine plan** (`docs/superpowers/plans/2026-08-14-interview-management-engine.md`, PR #534): the `interview.*` MCP tools this plan calls do not exist in the codebase yet. Do not start this plan's tasks against a real backend until that plan's Tasks 1-7 are implemented and deployed to whatever environment this plugin is tested against. Tasks 1-2 below (the `mcpClient.ts` wrapper) can be written and unit-tested against a mocked `network.fetch` without the real backend; Tasks 3-6 (state wiring + components) can also be fully unit-tested against a mocked `mcpClient`. Nothing in this plan requires a live server until manual/integration verification.
- `missing_fields` from `interview.get_state` is `list[{"name": str, "type": "text"|"textarea"|"enum"|"number", "choices": list[str] | None}]` — NOT bare strings (confirmed against the engine plan's corrected Task 3, commit `bb7647c`).
- The MCP HTTP transport is `POST {baseUrl}/mcp/` (JSON-RPC 2.0, request/response, no streaming) — NOT `POST {baseUrl}/mcp/sse/`. Auth header is `X-API-Key`, identical to existing REST calls.
- Tool-execution errors (e.g. `NOT_FOUND`, `VALIDATION_ERROR` raised by an `interview.*` handler) come back as a standard JSON-RPC error object `{code: <int>, message: <str>, details?: {...}}` in the response body — this plan uses "direct method dispatch" (`method` is literally the tool name, e.g. `"interview.start"`, not the wrapped `"tools/call"` convention), which keeps errors in that plain shape rather than MCP's `isError` content-block wrapper.
- `interview.answer` has no batch variant — submitting a form means one `interview.answer` call per changed field, sequentially (spec §3).
- No streaming, no E2E coverage in this plan (spec §6) — Vitest unit/component tests only, matching the rest of `integrations/hermes-plugin`.

---

## Task 1: `mcpClient.ts` — JSON-RPC core (request/response + error handling)

**Files:**
- Create: `integrations/hermes-plugin/reqogniloom/src/mcpClient.ts`
- Test: `integrations/hermes-plugin/reqogniloom/src/__tests__/mcpClient.test.ts`

**Interfaces:**
- Consumes: `HermesNetworkAPI` (`integrations/hermes-plugin/reqogniloom/src/api.ts`, already defines `{fetch(url, options?): Promise<unknown>}`), `Connection` type (same file: `{baseUrl, apiKey, workspaceId}`).
- Produces: `mcpClient.ts` exports `McpRpcError extends Error` (fields: `code: number`, `data?: unknown`), `callMcpTool(network: HermesNetworkAPI, connection: Connection, toolName: string, params: Record<string, unknown>): Promise<unknown>` (returns the JSON-RPC `result` field's contents on success, throws `McpRpcError` on a JSON-RPC error object, throws a generic `Error` on a transport failure).

- [ ] **Step 1: Write the failing test**

```typescript
// integrations/hermes-plugin/reqogniloom/src/__tests__/mcpClient.test.ts
import { describe, expect, it, vi } from "vitest";
import { callMcpTool, McpRpcError } from "../mcpClient";

const CONNECTION = { baseUrl: "https://example.com", apiKey: "reqlo_abc", workspaceId: "ws-1" };

describe("callMcpTool", () => {
  it("POSTs a JSON-RPC 2.0 envelope with the tool name as method and X-API-Key header", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      JSON.stringify({ jsonrpc: "2.0", id: 1, result: { session_id: "abc" } })
    );

    await callMcpTool({ fetch: fetchMock }, CONNECTION, "interview.start", {
      artifact_type: "Requirement",
      workspace_id: "ws-1",
    });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toBe("https://example.com/mcp/");
    expect(options.headers["X-API-Key"]).toBe("reqlo_abc");
    const body = JSON.parse(options.body as string);
    expect(body.jsonrpc).toBe("2.0");
    expect(body.method).toBe("interview.start");
    expect(body.params).toEqual({ artifact_type: "Requirement", workspace_id: "ws-1" });
    expect(typeof body.id).not.toBe("undefined");
  });

  it("returns the result field on success", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      JSON.stringify({ jsonrpc: "2.0", id: 1, result: { session_id: "abc" } })
    );

    const result = await callMcpTool({ fetch: fetchMock }, CONNECTION, "interview.get", {
      session_id: "abc",
    });

    expect(result).toEqual({ session_id: "abc" });
  });

  it("strips a trailing slash from baseUrl before appending /mcp/", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      JSON.stringify({ jsonrpc: "2.0", id: 1, result: {} })
    );

    await callMcpTool(
      { fetch: fetchMock },
      { ...CONNECTION, baseUrl: "https://example.com/" },
      "interview.get",
      {}
    );

    expect(fetchMock.mock.calls[0][0]).toBe("https://example.com/mcp/");
  });

  it("throws McpRpcError with code/message on a JSON-RPC error response", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      JSON.stringify({
        jsonrpc: "2.0",
        id: 1,
        error: { code: -32001, message: "InterviewSession abc not found" },
      })
    );

    await expect(
      callMcpTool({ fetch: fetchMock }, CONNECTION, "interview.get", { session_id: "abc" })
    ).rejects.toMatchObject({
      message: "InterviewSession abc not found",
      code: -32001,
    });
    await expect(
      callMcpTool({ fetch: fetchMock }, CONNECTION, "interview.get", { session_id: "abc" })
    ).rejects.toBeInstanceOf(McpRpcError);
  });

  it("handles a Response return shape (network.fetch returns a Response-like object)", async () => {
    const body = JSON.stringify({ jsonrpc: "2.0", id: 1, result: { ok: true } });
    const fakeResponse = { status: 200, text: async () => body };
    const fetchMock = vi.fn().mockResolvedValue(fakeResponse);

    const result = await callMcpTool({ fetch: fetchMock }, CONNECTION, "interview.get", {});

    expect(result).toEqual({ ok: true });
  });

  it("throws a plain Error when the transport itself fails to return valid JSON", async () => {
    const fetchMock = vi.fn().mockResolvedValue("not json");

    await expect(
      callMcpTool({ fetch: fetchMock }, CONNECTION, "interview.get", {})
    ).rejects.toThrow();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd integrations/hermes-plugin/reqogniloom && npx vitest run src/__tests__/mcpClient.test.ts`
Expected: FAIL — `Cannot find module '../mcpClient'`

- [ ] **Step 3: Implement `mcpClient.ts`**

Model the network-result parsing on `api.ts`'s `parseNetworkResult` (same ambiguous-return-shape problem: `network.fetch` may resolve to a raw string or a `Response`-like object per the Hermes plugin API's own inconsistent documentation, already handled once in `api.ts` — do not re-derive that logic differently here, port it):

```typescript
// integrations/hermes-plugin/reqogniloom/src/mcpClient.ts
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd integrations/hermes-plugin/reqogniloom && npx vitest run src/__tests__/mcpClient.test.ts`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add integrations/hermes-plugin/reqogniloom/src/mcpClient.ts integrations/hermes-plugin/reqogniloom/src/__tests__/mcpClient.test.ts
git commit -m "feat: add MCP JSON-RPC client for the Hermes plugin"
```

---

## Task 2: Typed `interview.*` wrapper functions

**Files:**
- Modify: `integrations/hermes-plugin/reqogniloom/src/mcpClient.ts`
- Test: `integrations/hermes-plugin/reqogniloom/src/__tests__/mcpClient.test.ts`

**Interfaces:**
- Consumes: `callMcpTool` (Task 1).
- Produces: `mcpClient.ts` exports `InterviewField` (`{name: string; type: "text" | "textarea" | "enum" | "number"; choices: string[] | null}`), `InterviewState` (`{session_id: string; status: "in_progress" | "completed" | "abandoned"; phase: string; collected_fields: Record<string, unknown>; missing_fields: InterviewField[]; grounding_snapshot: {candidates: {artifact_id: string; title: string; score: number | null}[]}}`), `InterviewSummary` (`{id: string; workspace_id: string; artifact_type: string; status: string}`), and functions: `interviewStart(network, connection, artifactType: string): Promise<InterviewState>`, `interviewGetState(network, connection, sessionId: string): Promise<InterviewState>`, `interviewAnswer(network, connection, sessionId: string, field: string, value: unknown): Promise<InterviewState>`, `interviewGroundingContext(network, connection, sessionId: string): Promise<InterviewState["grounding_snapshot"]>`, `interviewFormalize(network, connection, sessionId: string): Promise<{resulting_artifact_ids: string[]; status: string}>`, `interviewList(network, connection, status?: string): Promise<InterviewSummary[]>`, `interviewGet(network, connection, sessionId: string): Promise<InterviewSummary>`.

- [ ] **Step 1: Write the failing test**

```typescript
// Add to integrations/hermes-plugin/reqogniloom/src/__tests__/mcpClient.test.ts
import {
  interviewAnswer,
  interviewFormalize,
  interviewGetState,
  interviewGroundingContext,
  interviewList,
  interviewStart,
} from "../mcpClient";

describe("interview.* wrappers", () => {
  it("interviewStart calls interview.start with artifact_type and workspace_id from the connection", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      JSON.stringify({
        jsonrpc: "2.0",
        id: 1,
        result: {
          session_id: "s-1",
          status: "in_progress",
          phase: "elicitation",
          collected_fields: {},
          missing_fields: [{ name: "title", type: "text", choices: null }],
          grounding_snapshot: { candidates: [] },
        },
      })
    );

    const state = await interviewStart({ fetch: fetchMock }, CONNECTION, "Requirement");

    const body = JSON.parse(fetchMock.mock.calls[0][1].body as string);
    expect(body.method).toBe("interview.start");
    expect(body.params).toEqual({ artifact_type: "Requirement", workspace_id: "ws-1" });
    expect(state.session_id).toBe("s-1");
    expect(state.missing_fields[0].type).toBe("text");
  });

  it("interviewAnswer sends session_id/field/value and returns the refreshed state", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      JSON.stringify({
        jsonrpc: "2.0",
        id: 1,
        result: {
          session_id: "s-1",
          status: "in_progress",
          phase: "elicitation",
          collected_fields: { title: "SSO login" },
          missing_fields: [],
          grounding_snapshot: { candidates: [] },
        },
      })
    );

    const state = await interviewAnswer({ fetch: fetchMock }, CONNECTION, "s-1", "title", "SSO login");

    const body = JSON.parse(fetchMock.mock.calls[0][1].body as string);
    expect(body.params).toEqual({ session_id: "s-1", field: "title", value: "SSO login" });
    expect(state.collected_fields.title).toBe("SSO login");
  });

  it("interviewFormalize returns resulting_artifact_ids and status", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      JSON.stringify({
        jsonrpc: "2.0",
        id: 1,
        result: { resulting_artifact_ids: ["art-1"], status: "completed" },
      })
    );

    const result = await interviewFormalize({ fetch: fetchMock }, CONNECTION, "s-1");

    expect(result.resulting_artifact_ids).toEqual(["art-1"]);
    expect(result.status).toBe("completed");
  });

  it("interviewList passes status through as a query param when given", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      JSON.stringify({ jsonrpc: "2.0", id: 1, result: { sessions: [] } })
    );

    await interviewList({ fetch: fetchMock }, CONNECTION, "in_progress");

    const body = JSON.parse(fetchMock.mock.calls[0][1].body as string);
    expect(body.params).toEqual({ workspace_id: "ws-1", status: "in_progress" });
  });

  it("interviewList omits status when not given", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      JSON.stringify({ jsonrpc: "2.0", id: 1, result: { sessions: [] } })
    );

    await interviewList({ fetch: fetchMock }, CONNECTION);

    const body = JSON.parse(fetchMock.mock.calls[0][1].body as string);
    expect(body.params).toEqual({ workspace_id: "ws-1" });
  });

  it("interviewGroundingContext returns the candidates list", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      JSON.stringify({
        jsonrpc: "2.0",
        id: 1,
        result: { candidates: [{ artifact_id: "art-1", title: "Existing req", score: null }] },
      })
    );

    const snapshot = await interviewGroundingContext({ fetch: fetchMock }, CONNECTION, "s-1");

    expect(snapshot.candidates).toHaveLength(1);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd integrations/hermes-plugin/reqogniloom && npx vitest run src/__tests__/mcpClient.test.ts`
Expected: FAIL — the new named exports don't exist yet

- [ ] **Step 3: Implement the wrapper functions**

Append to `mcpClient.ts`:

```typescript
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
  grounding_snapshot: { candidates: { artifact_id: string; title: string; score: number | null }[] };
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

export async function interviewGet(
  network: HermesNetworkAPI,
  connection: Connection,
  sessionId: string
): Promise<InterviewSummary> {
  return callMcpTool(network, connection, "interview.get", {
    session_id: sessionId,
  }) as Promise<InterviewSummary>;
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd integrations/hermes-plugin/reqogniloom && npx vitest run src/__tests__/mcpClient.test.ts`
Expected: PASS (12 tests)

- [ ] **Step 5: Commit**

```bash
git add integrations/hermes-plugin/reqogniloom/src/mcpClient.ts integrations/hermes-plugin/reqogniloom/src/__tests__/mcpClient.test.ts
git commit -m "feat: add typed interview.* wrapper functions"
```

---

## Task 3: `state.ts` — `"interviews"` view + session state

**Files:**
- Modify: `integrations/hermes-plugin/reqogniloom/src/state.ts`
- Test: `integrations/hermes-plugin/reqogniloom/src/__tests__/state.test.ts` (new file — no existing `state.test.ts`; check `src/__tests__/` for one before creating, in case it was added since this plan was written)

**Interfaces:**
- Consumes: `interviewStart`/`interviewGetState`/`interviewAnswer`/`interviewList`/`interviewFormalize` (Task 2), `InterviewState`/`InterviewSummary` types (Task 2).
- Produces: `AppState.view` extended to include `"interviews"`, new `AppState` fields `activeInterview: InterviewState | null`, `interviewList: InterviewSummary[]`, `interviewError: string | null`, `interviewBusy: boolean`; new exported functions `openInterviews(): Promise<void>`, `startNewInterview(artifactType: string): Promise<void>`, `resumeInterview(sessionId: string): Promise<void>`, `answerInterviewField(field: string, value: unknown): Promise<void>`, `formalizeInterview(): Promise<{resulting_artifact_ids: string[]} | null>`, `closeInterview(): void`.

- [ ] **Step 1: Write the failing test**

```typescript
// integrations/hermes-plugin/reqogniloom/src/__tests__/state.test.ts
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../mcpClient", () => ({
  interviewStart: vi.fn(),
  interviewGetState: vi.fn(),
  interviewAnswer: vi.fn(),
  interviewList: vi.fn(),
  interviewFormalize: vi.fn(),
}));

import {
  answerInterviewField,
  closeInterview,
  formalizeInterview,
  getState,
  initState,
  openInterviews,
  resumeInterview,
  startNewInterview,
  __resetStateForTesting,
} from "../state";
import * as mcpClient from "../mcpClient";

const FAKE_HERMES_API = {
  ui: { registerPanel: vi.fn(), showPanel: vi.fn(), hidePanel: vi.fn(), togglePanel: vi.fn(), showToast: vi.fn(), updateStatusBarItem: vi.fn() },
  commands: { register: vi.fn(), execute: vi.fn() },
  storage: { get: vi.fn().mockResolvedValue(null), set: vi.fn(), delete: vi.fn() },
  network: { fetch: vi.fn() },
  shell: { openExternal: vi.fn() },
  subscriptions: [],
};

async function connectedState() {
  __resetStateForTesting();
  await initState(FAKE_HERMES_API as never);
  // Directly seed a connection the way finalizeConnection would, without
  // going through the REST connect flow this test doesn't need.
  const stateModule = await import("../state");
  (stateModule as unknown as { __setConnectionForTesting: (c: unknown, n: string) => void }).__setConnectionForTesting(
    { baseUrl: "https://example.com", apiKey: "reqlo_abc", workspaceId: "ws-1" },
    "My Workspace"
  );
}

describe("interview state", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("startNewInterview stores the returned InterviewState and switches view", async () => {
    await connectedState();
    const fakeState = {
      session_id: "s-1", status: "in_progress", phase: "elicitation",
      collected_fields: {}, missing_fields: [{ name: "title", type: "text", choices: null }],
      grounding_snapshot: { candidates: [] },
    };
    vi.mocked(mcpClient.interviewStart).mockResolvedValue(fakeState);

    await startNewInterview("Requirement");

    expect(getState().view).toBe("interviews");
    expect(getState().activeInterview).toEqual(fakeState);
  });

  it("answerInterviewField calls interviewAnswer and refreshes activeInterview", async () => {
    await connectedState();
    vi.mocked(mcpClient.interviewStart).mockResolvedValue({
      session_id: "s-1", status: "in_progress", phase: "elicitation",
      collected_fields: {}, missing_fields: [{ name: "title", type: "text", choices: null }],
      grounding_snapshot: { candidates: [] },
    });
    await startNewInterview("Requirement");
    vi.mocked(mcpClient.interviewAnswer).mockResolvedValue({
      session_id: "s-1", status: "in_progress", phase: "elicitation",
      collected_fields: { title: "SSO login" }, missing_fields: [],
      grounding_snapshot: { candidates: [] },
    });

    await answerInterviewField("title", "SSO login");

    expect(mcpClient.interviewAnswer).toHaveBeenCalledWith(
      expect.anything(), expect.anything(), "s-1", "title", "SSO login"
    );
    expect(getState().activeInterview?.collected_fields.title).toBe("SSO login");
  });

  it("a failed interviewStart sets interviewError and does not switch view", async () => {
    await connectedState();
    vi.mocked(mcpClient.interviewStart).mockRejectedValue(new Error("boom"));

    await startNewInterview("Requirement");

    expect(getState().interviewError).toBe("boom");
    expect(getState().view).not.toBe("interviews");
  });

  it("closeInterview clears activeInterview and returns to the connected view", async () => {
    await connectedState();
    vi.mocked(mcpClient.interviewStart).mockResolvedValue({
      session_id: "s-1", status: "in_progress", phase: "elicitation",
      collected_fields: {}, missing_fields: [], grounding_snapshot: { candidates: [] },
    });
    await startNewInterview("Requirement");

    closeInterview();

    expect(getState().activeInterview).toBeNull();
    expect(getState().view).toBe("connected");
  });
});
```

Note: `__setConnectionForTesting` does not exist yet in `state.ts` — check whether a simpler existing seam already lets a test reach the "connected" state (re-read `state.ts`'s current exports before assuming this helper is the right approach; it may be simpler to call the real `connectWithCredentials`/`chooseWorkspace` flow with a mocked `network.fetch` instead of adding a test-only backdoor — prefer that if it is not significantly more code, since it avoids growing the module's public surface for tests only). If a backdoor genuinely is simplest, add `__setConnectionForTesting` as a new test-only export following the existing `__resetStateForTesting` naming convention.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd integrations/hermes-plugin/reqogniloom && npx vitest run src/__tests__/state.test.ts`
Expected: FAIL — `openInterviews`/`startNewInterview`/etc. are not exported

- [ ] **Step 3: Implement the state extensions**

Modify `state.ts`:

```typescript
import type { PluginPanelProps } from "./hermes-api-types";
import { getState, subscribe } from "./state"; // (existing self-reference removed — this is illustrative of what NOT to duplicate; see full diff below)
```

Concretely, apply these changes to the existing `state.ts` (shown as the new/changed pieces, not a full file — merge into the existing structure from Spec 2's read of the file rather than replacing it wholesale):

```typescript
// Add to imports at the top:
import {
  interviewAnswer,
  interviewFormalize,
  interviewGetState,
  interviewList as fetchInterviewList,
  interviewStart,
  type InterviewState,
  type InterviewSummary,
} from "./mcpClient";

// Change:
export type View = "connect" | "connected" | "interviews";

// Extend AppState:
export interface AppState {
  view: View;
  connection: Connection | null;
  workspaceName: string | null;
  pendingCredentials: { baseUrl: string; apiKey: string } | null;
  pendingWorkspaces: Workspace[];
  connectError: string | null;
  connecting: boolean;
  activeInterview: InterviewState | null;
  interviewList: InterviewSummary[];
  interviewError: string | null;
  interviewBusy: boolean;
}

// Extend createInitialState():
function createInitialState(): AppState {
  return {
    view: "connect",
    connection: null,
    workspaceName: null,
    pendingCredentials: null,
    pendingWorkspaces: [],
    connectError: null,
    connecting: false,
    activeInterview: null,
    interviewList: [],
    interviewError: null,
    interviewBusy: false,
  };
}

// New functions, added after the existing disconnect()/openInBrowser():

export async function openInterviews(): Promise<void> {
  if (!state.connection) return;
  setState({ interviewBusy: true, interviewError: null });
  try {
    const list = await fetchInterviewList(api().network, state.connection, "in_progress");
    setState({ interviewList: list, view: "interviews", interviewBusy: false });
  } catch (err) {
    setState({ interviewBusy: false, interviewError: err instanceof Error ? err.message : "Failed to load interviews." });
  }
}

export async function startNewInterview(artifactType: string): Promise<void> {
  if (!state.connection) return;
  setState({ interviewBusy: true, interviewError: null });
  try {
    const interview = await interviewStart(api().network, state.connection, artifactType);
    setState({ activeInterview: interview, view: "interviews", interviewBusy: false });
  } catch (err) {
    setState({ interviewBusy: false, interviewError: err instanceof Error ? err.message : "Failed to start interview." });
  }
}

export async function resumeInterview(sessionId: string): Promise<void> {
  if (!state.connection) return;
  setState({ interviewBusy: true, interviewError: null });
  try {
    const interview = await interviewGetState(api().network, state.connection, sessionId);
    setState({ activeInterview: interview, view: "interviews", interviewBusy: false });
  } catch (err) {
    setState({ interviewBusy: false, interviewError: err instanceof Error ? err.message : "Failed to resume interview." });
  }
}

export async function answerInterviewField(field: string, value: unknown): Promise<void> {
  if (!state.connection || !state.activeInterview) return;
  const sessionId = state.activeInterview.session_id;
  setState({ interviewBusy: true, interviewError: null });
  try {
    const refreshed = await interviewAnswer(api().network, state.connection, sessionId, field, value);
    setState({ activeInterview: refreshed, interviewBusy: false });
  } catch (err) {
    setState({ interviewBusy: false, interviewError: err instanceof Error ? err.message : "Failed to save answer." });
  }
}

export async function formalizeInterview(): Promise<{ resulting_artifact_ids: string[] } | null> {
  if (!state.connection || !state.activeInterview) return null;
  const sessionId = state.activeInterview.session_id;
  setState({ interviewBusy: true, interviewError: null });
  try {
    const result = await interviewFormalize(api().network, state.connection, sessionId);
    setState({ interviewBusy: false });
    return result;
  } catch (err) {
    setState({ interviewBusy: false, interviewError: err instanceof Error ? err.message : "Failed to formalize interview." });
    return null;
  }
}

export function closeInterview(): void {
  setState({ activeInterview: null, view: "connected" });
}
```

Resolve the test-seam question from Step 1's note before finishing this step — either implement `__setConnectionForTesting` alongside `__resetStateForTesting`, or rewrite the test's `connectedState()` helper to drive the real connect flow.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd integrations/hermes-plugin/reqogniloom && npx vitest run src/__tests__/state.test.ts`
Expected: PASS (4 tests)

- [ ] **Step 5: Run the full existing test suite to confirm nothing broke**

Run: `cd integrations/hermes-plugin/reqogniloom && npx vitest run`
Expected: PASS (all existing tests plus the new ones)

- [ ] **Step 6: Commit**

```bash
git add integrations/hermes-plugin/reqogniloom/src/state.ts integrations/hermes-plugin/reqogniloom/src/__tests__/state.test.ts
git commit -m "feat: add interview state management (start/resume/answer/formalize)"
```

---

## Task 4: `InterviewListView` component

**Files:**
- Create: `integrations/hermes-plugin/reqogniloom/src/InterviewListView.tsx`
- Test: `integrations/hermes-plugin/reqogniloom/src/__tests__/InterviewListView.test.tsx`

**Interfaces:**
- Consumes: `AppState` (Task 3), `InterviewSummary` (Task 2), `startNewInterview`/`resumeInterview` (Task 3).
- Produces: `InterviewListView({state}: {state: AppState}): JSX.Element` — renders `state.interviewList`, a "start new" control per in-scope artifact type, and an error banner from `state.interviewError`.

Check the exact artifact-type list this component should offer for "start new" against the engine spec's scope (spec §1 of the engine design, mirrored in the Hermes spec's own framing): `Requirement, ArchitectureElement, StakeholderNeed, Risk, TestCase, Adr, Issue, Goal` — NOT `MainGoal`. Hardcode this list as a local constant in this component (it is the same static list Spec 1's plan hardcodes as `IN_SCOPE_ARTIFACT_TYPES` server-side — no API call needed to discover it, since it is fixed at design time, not per-workspace configuration).

- [ ] **Step 1: Write the failing test**

```typescript
// integrations/hermes-plugin/reqogniloom/src/__tests__/InterviewListView.test.tsx
import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { InterviewListView } from "../InterviewListView";
import type { AppState } from "../state";

vi.mock("../state", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../state")>();
  return { ...actual, startNewInterview: vi.fn(), resumeInterview: vi.fn() };
});
import { resumeInterview, startNewInterview } from "../state";

function makeState(overrides: Partial<AppState> = {}): AppState {
  return {
    view: "interviews", connection: { baseUrl: "https://x", apiKey: "k", workspaceId: "ws-1" },
    workspaceName: "WS", pendingCredentials: null, pendingWorkspaces: [],
    connectError: null, connecting: false, activeInterview: null,
    interviewList: [], interviewError: null, interviewBusy: false,
    ...overrides,
  };
}

describe("InterviewListView", () => {
  it("renders existing sessions and calls resumeInterview on click", () => {
    const state = makeState({
      interviewList: [{ id: "s-1", workspace_id: "ws-1", artifact_type: "Requirement", status: "in_progress" }],
    });

    render(<InterviewListView state={state} />);
    fireEvent.click(screen.getByText(/Requirement/i));

    expect(resumeInterview).toHaveBeenCalledWith("s-1");
  });

  it("renders a start button per in-scope artifact type and calls startNewInterview", () => {
    render(<InterviewListView state={makeState()} />);

    fireEvent.click(screen.getByTestId("interview-start-Risk"));

    expect(startNewInterview).toHaveBeenCalledWith("Risk");
  });

  it("does not offer MainGoal", () => {
    render(<InterviewListView state={makeState()} />);

    expect(screen.queryByTestId("interview-start-MainGoal")).not.toBeInTheDocument();
  });

  it("shows interviewError when present", () => {
    render(<InterviewListView state={makeState({ interviewError: "boom" })} />);

    expect(screen.getByText("boom")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd integrations/hermes-plugin/reqogniloom && npx vitest run src/__tests__/InterviewListView.test.tsx`
Expected: FAIL — module not found

- [ ] **Step 3: Implement the component**

```typescript
// integrations/hermes-plugin/reqogniloom/src/InterviewListView.tsx
import * as React from "react";
import type { AppState } from "./state";
import { resumeInterview, startNewInterview } from "./state";

// Mirrors the engine's IN_SCOPE_ARTIFACT_TYPES (Spec 1 plan,
// application/interview_protocol.py) -- fixed at design time, not fetched.
const IN_SCOPE_ARTIFACT_TYPES = [
  "Requirement", "ArchitectureElement", "StakeholderNeed", "Risk",
  "TestCase", "Adr", "Issue", "Goal",
] as const;

const buttonStyle: React.CSSProperties = {
  background: "var(--accent)",
  color: "var(--bg-1)",
  border: "none",
  borderRadius: "var(--radius-sm)",
  padding: "6px 12px",
  cursor: "pointer",
  fontSize: "var(--text-xs)",
};

export function InterviewListView({ state }: { state: AppState }): JSX.Element {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
      {state.interviewError && (
        <span style={{ color: "var(--danger, red)", fontSize: "var(--text-xs)" }}>
          {state.interviewError}
        </span>
      )}

      <div>
        <span style={{ fontSize: "var(--text-xs)", color: "var(--text-2)" }}>Active sessions</span>
        {state.interviewList.length === 0 && (
          <p style={{ fontSize: "var(--text-xs)", color: "var(--text-2)" }}>None yet.</p>
        )}
        <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
          {state.interviewList.map((session) => (
            <li key={session.id}>
              <button
                type="button"
                style={buttonStyle}
                onClick={() => void resumeInterview(session.id)}
              >
                {session.artifact_type} — {session.status}
              </button>
            </li>
          ))}
        </ul>
      </div>

      <div>
        <span style={{ fontSize: "var(--text-xs)", color: "var(--text-2)" }}>Start new</span>
        <div style={{ display: "flex", flexWrap: "wrap", gap: "6px" }}>
          {IN_SCOPE_ARTIFACT_TYPES.map((type) => (
            <button
              key={type}
              type="button"
              data-testid={`interview-start-${type}`}
              style={buttonStyle}
              onClick={() => void startNewInterview(type)}
              disabled={state.interviewBusy}
            >
              {type}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd integrations/hermes-plugin/reqogniloom && npx vitest run src/__tests__/InterviewListView.test.tsx`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add integrations/hermes-plugin/reqogniloom/src/InterviewListView.tsx integrations/hermes-plugin/reqogniloom/src/__tests__/InterviewListView.test.tsx
git commit -m "feat: add InterviewListView component"
```

---

## Task 5: `InterviewFormView` component (typed field rendering)

**Files:**
- Create: `integrations/hermes-plugin/reqogniloom/src/InterviewFormView.tsx`
- Test: `integrations/hermes-plugin/reqogniloom/src/__tests__/InterviewFormView.test.tsx`

**Interfaces:**
- Consumes: `AppState.activeInterview` (Task 3), `InterviewField`/`InterviewState` (Task 2), `answerInterviewField`/`formalizeInterview`/`closeInterview` (Task 3).
- Produces: `InterviewFormView({state}: {state: AppState}): JSX.Element` — renders one input per `missing_fields` entry, typed per `field.type`; a grounding-candidates hint list from `state.activeInterview.grounding_snapshot`; a "Formalize" button enabled only when `missing_fields` is empty; a completed/abandoned read-only view when `status !== "in_progress"`.

- [ ] **Step 1: Write the failing test**

```typescript
// integrations/hermes-plugin/reqogniloom/src/__tests__/InterviewFormView.test.tsx
import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { InterviewFormView } from "../InterviewFormView";
import type { AppState } from "../state";
import type { InterviewState } from "../mcpClient";

vi.mock("../state", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../state")>();
  return { ...actual, answerInterviewField: vi.fn(), formalizeInterview: vi.fn(), closeInterview: vi.fn() };
});
import { answerInterviewField, closeInterview, formalizeInterview } from "../state";

function makeInterview(overrides: Partial<InterviewState> = {}): InterviewState {
  return {
    session_id: "s-1", status: "in_progress", phase: "elicitation",
    collected_fields: {}, missing_fields: [], grounding_snapshot: { candidates: [] },
    ...overrides,
  };
}

function makeState(activeInterview: InterviewState): AppState {
  return {
    view: "interviews", connection: { baseUrl: "https://x", apiKey: "k", workspaceId: "ws-1" },
    workspaceName: "WS", pendingCredentials: null, pendingWorkspaces: [],
    connectError: null, connecting: false, activeInterview,
    interviewList: [], interviewError: null, interviewBusy: false,
  };
}

describe("InterviewFormView field rendering", () => {
  it("renders a textarea for a textarea field", () => {
    const interview = makeInterview({
      missing_fields: [{ name: "rationale", type: "textarea", choices: null }],
    });
    render(<InterviewFormView state={makeState(interview)} />);

    expect(screen.getByTestId("interview-field-rationale").tagName).toBe("TEXTAREA");
  });

  it("renders a select with the given choices for an enum field", () => {
    const interview = makeInterview({
      missing_fields: [{ name: "element_type", type: "enum", choices: ["component", "system"] }],
    });
    render(<InterviewFormView state={makeState(interview)} />);

    const select = screen.getByTestId("interview-field-element_type");
    expect(select.tagName).toBe("SELECT");
    expect(screen.getByText("component")).toBeInTheDocument();
    expect(screen.getByText("system")).toBeInTheDocument();
  });

  it("renders a number input for a number field", () => {
    const interview = makeInterview({
      missing_fields: [{ name: "priority", type: "number", choices: null }],
    });
    render(<InterviewFormView state={makeState(interview)} />);

    expect(screen.getByTestId("interview-field-priority")).toHaveAttribute("type", "number");
  });

  it("calls answerInterviewField on blur with the entered value", () => {
    const interview = makeInterview({
      missing_fields: [{ name: "title", type: "text", choices: null }],
    });
    render(<InterviewFormView state={makeState(interview)} />);

    const input = screen.getByTestId("interview-field-title");
    fireEvent.change(input, { target: { value: "SSO login" } });
    fireEvent.blur(input);

    expect(answerInterviewField).toHaveBeenCalledWith("title", "SSO login");
  });

  it("disables Formalize while any field is still missing", () => {
    const interview = makeInterview({
      missing_fields: [{ name: "title", type: "text", choices: null }],
    });
    render(<InterviewFormView state={makeState(interview)} />);

    expect(screen.getByTestId("interview-formalize-button")).toBeDisabled();
  });

  it("enables Formalize when no fields are missing and calls formalizeInterview + closeInterview on success", async () => {
    vi.mocked(formalizeInterview).mockResolvedValue({ resulting_artifact_ids: ["art-1"] });
    const interview = makeInterview({ missing_fields: [] });
    render(<InterviewFormView state={makeState(interview)} />);

    const button = screen.getByTestId("interview-formalize-button");
    expect(button).not.toBeDisabled();
    fireEvent.click(button);

    await screen.findByText(/art-1/i);
  });

  it("shows grounding candidates as a hint list", () => {
    const interview = makeInterview({
      grounding_snapshot: { candidates: [{ artifact_id: "art-9", title: "Similar existing req", score: null }] },
    });
    render(<InterviewFormView state={makeState(interview)} />);

    expect(screen.getByText(/Similar existing req/i)).toBeInTheDocument();
  });

  it("renders a read-only completed view instead of the form when status is completed", () => {
    const interview = makeInterview({ status: "completed", missing_fields: [] });
    render(<InterviewFormView state={makeState(interview)} />);

    expect(screen.queryByTestId("interview-formalize-button")).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd integrations/hermes-plugin/reqogniloom && npx vitest run src/__tests__/InterviewFormView.test.tsx`
Expected: FAIL — module not found

- [ ] **Step 3: Implement the component**

```typescript
// integrations/hermes-plugin/reqogniloom/src/InterviewFormView.tsx
import * as React from "react";
import { useState } from "react";
import type { AppState } from "./state";
import { answerInterviewField, closeInterview, formalizeInterview } from "./state";
import type { InterviewField } from "./mcpClient";

const inputStyle: React.CSSProperties = {
  width: "100%",
  padding: "4px 6px",
  background: "var(--bg-2, transparent)",
  border: "1px solid var(--border, #444)",
  borderRadius: "var(--radius-sm)",
  color: "var(--text-1)",
  fontSize: "var(--text-sm)",
};

const buttonStyle: React.CSSProperties = {
  background: "var(--accent)",
  color: "var(--bg-1)",
  border: "none",
  borderRadius: "var(--radius-sm)",
  padding: "6px 12px",
  cursor: "pointer",
  fontSize: "var(--text-xs)",
};

function FieldInput({ field }: { field: InterviewField }): JSX.Element {
  const [value, setValue] = useState("");
  const commonProps = {
    "data-testid": `interview-field-${field.name}`,
    style: inputStyle,
    value,
    onChange: (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) =>
      setValue(e.target.value),
    onBlur: () => {
      if (value !== "") void answerInterviewField(field.name, field.type === "number" ? Number(value) : value);
    },
  };

  if (field.type === "textarea") return <textarea {...commonProps} />;
  if (field.type === "enum") {
    return (
      <select {...commonProps}>
        <option value="" disabled>
          Select…
        </option>
        {(field.choices ?? []).map((choice) => (
          <option key={choice} value={choice}>
            {choice}
          </option>
        ))}
      </select>
    );
  }
  return <input {...commonProps} type={field.type === "number" ? "number" : "text"} />;
}

export function InterviewFormView({ state }: { state: AppState }): JSX.Element | null {
  const [result, setResult] = useState<{ resulting_artifact_ids: string[] } | null>(null);
  const interview = state.activeInterview;
  if (!interview) return null;

  if (interview.status !== "in_progress") {
    return (
      <div>
        <p>Session is {interview.status}.</p>
        {result && <p>Created/updated: {result.resulting_artifact_ids.join(", ")}</p>}
        <button type="button" style={buttonStyle} onClick={closeInterview}>
          Close
        </button>
      </div>
    );
  }

  const candidates = interview.grounding_snapshot.candidates;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
      <span style={{ fontSize: "var(--text-xs)", color: "var(--text-2)" }}>{interview.phase}</span>

      {candidates.length > 0 && (
        <ul style={{ fontSize: "var(--text-xs)", color: "var(--text-2)" }}>
          {candidates.map((c) => (
            <li key={c.artifact_id}>Possibly related: {c.title}</li>
          ))}
        </ul>
      )}

      {interview.missing_fields.map((field) => (
        <label key={field.name} style={{ display: "flex", flexDirection: "column", gap: "2px" }}>
          {field.name}
          <FieldInput field={field} />
        </label>
      ))}

      <button
        type="button"
        data-testid="interview-formalize-button"
        style={buttonStyle}
        disabled={interview.missing_fields.length > 0}
        onClick={async () => {
          const r = await formalizeInterview();
          if (r) setResult(r);
        }}
      >
        Formalize
      </button>

      {result && <p>Created/updated: {result.resulting_artifact_ids.join(", ")}</p>}
    </div>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd integrations/hermes-plugin/reqogniloom && npx vitest run src/__tests__/InterviewFormView.test.tsx`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add integrations/hermes-plugin/reqogniloom/src/InterviewFormView.tsx integrations/hermes-plugin/reqogniloom/src/__tests__/InterviewFormView.test.tsx
git commit -m "feat: add InterviewFormView component with typed field rendering"
```

---

## Task 6: Wire into `ReqogniLoomPanel.tsx` and `ConnectedView.tsx`

**Files:**
- Modify: `integrations/hermes-plugin/reqogniloom/src/ReqogniLoomPanel.tsx`
- Modify: `integrations/hermes-plugin/reqogniloom/src/ConnectedView.tsx`
- Test: `integrations/hermes-plugin/reqogniloom/src/__tests__/ReqogniLoomPanel.test.tsx` (new, or extend an existing one if present — check first)

**Interfaces:**
- Consumes: `InterviewListView` (Task 4), `InterviewFormView` (Task 5), `openInterviews` (Task 3), `AppState.view === "interviews"`.
- Produces: the panel now renders `InterviewListView` or `InterviewFormView` (depending on whether `state.activeInterview` is set) when `state.view === "interviews"`; `ConnectedView` gets an "Interviews" button that calls `openInterviews()`.

- [ ] **Step 1: Write the failing test**

```typescript
// integrations/hermes-plugin/reqogniloom/src/__tests__/ReqogniLoomPanel.test.tsx
import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { ReqogniLoomPanel } from "../ReqogniLoomPanel";
import * as state from "../state";

describe("ReqogniLoomPanel — interviews routing", () => {
  it("renders InterviewListView when view is interviews and no activeInterview is set", () => {
    vi.spyOn(state, "getState").mockReturnValue({
      view: "interviews", connection: { baseUrl: "x", apiKey: "k", workspaceId: "ws-1" },
      workspaceName: "WS", pendingCredentials: null, pendingWorkspaces: [],
      connectError: null, connecting: false, activeInterview: null,
      interviewList: [], interviewError: null, interviewBusy: false,
    });
    vi.spyOn(state, "subscribe").mockReturnValue(() => {});

    render(<ReqogniLoomPanel pluginId="p" panelId="reqogniloom" />);

    expect(screen.getByText(/Start new/i)).toBeInTheDocument();
  });

  it("renders InterviewFormView when an activeInterview is set", () => {
    vi.spyOn(state, "getState").mockReturnValue({
      view: "interviews", connection: { baseUrl: "x", apiKey: "k", workspaceId: "ws-1" },
      workspaceName: "WS", pendingCredentials: null, pendingWorkspaces: [],
      connectError: null, connecting: false,
      activeInterview: {
        session_id: "s-1", status: "in_progress", phase: "elicitation",
        collected_fields: {}, missing_fields: [{ name: "title", type: "text", choices: null }],
        grounding_snapshot: { candidates: [] },
      },
      interviewList: [], interviewError: null, interviewBusy: false,
    });
    vi.spyOn(state, "subscribe").mockReturnValue(() => {});

    render(<ReqogniLoomPanel pluginId="p" panelId="reqogniloom" />);

    expect(screen.getByTestId("interview-field-title")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd integrations/hermes-plugin/reqogniloom && npx vitest run src/__tests__/ReqogniLoomPanel.test.tsx`
Expected: FAIL — panel doesn't render either view yet for `view === "interviews"`

- [ ] **Step 3: Wire the panel**

In `ReqogniLoomPanel.tsx`, add imports for `InterviewListView`/`InterviewFormView` and extend the render:

```typescript
import { InterviewFormView } from "./InterviewFormView";
import { InterviewListView } from "./InterviewListView";

// ... inside the component, alongside the existing view checks:
      {state.view === "connect" && <ConnectScreen state={state} />}
      {state.view === "connected" && <ConnectedView state={state} />}
      {state.view === "interviews" && state.activeInterview && <InterviewFormView state={state} />}
      {state.view === "interviews" && !state.activeInterview && <InterviewListView state={state} />}
```

In `ConnectedView.tsx`, add an "Interviews" button:

```typescript
import { disconnect, openInBrowser, openInterviews } from "./state";

// ... in the JSX, alongside the existing "Open ReqogniLoom"/"Disconnect" buttons:
      <button style={buttonStyle} onClick={() => void openInterviews()}>
        Interviews
      </button>
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd integrations/hermes-plugin/reqogniloom && npx vitest run src/__tests__/ReqogniLoomPanel.test.tsx`
Expected: PASS (2 tests)

- [ ] **Step 5: Run the full test suite**

Run: `cd integrations/hermes-plugin/reqogniloom && npx vitest run`
Expected: PASS (every test in the package, old and new)

- [ ] **Step 6: Commit**

```bash
git add integrations/hermes-plugin/reqogniloom/src/ReqogniLoomPanel.tsx integrations/hermes-plugin/reqogniloom/src/ConnectedView.tsx integrations/hermes-plugin/reqogniloom/src/__tests__/ReqogniLoomPanel.test.tsx
git commit -m "feat: wire interview views into the Hermes plugin panel"
```

---

## Self-Review Notes (for whoever executes this plan)

- **This plan cannot be manually/integration-tested end-to-end until the engine plan (PR #534) is implemented and deployed.** Every task here is unit-testable in isolation against mocks; do not skip that isolation by trying to stand up a real backend prematurely.
- **Spec §5's "MCP session expired" error-message improvement (issue #427) is explicitly NOT part of this plan** — it was already fixed on `main` before this plan was written (see commit `1be452e`, issue #427 closed). The `McpRpcError` in Task 1 already surfaces whatever specific message the server sends, so no extra handling was needed here for that case.
- **Field value coercion is minimal** (Task 5's `FieldInput`: `number` fields get `Number(value)`, everything else stays a string). The spec does not specify richer client-side validation (e.g. rejecting non-numeric input before submit) and none was added — YAGNI; the server-side formalize/schema validation (engine plan Task 2 Step 6, Task 7) is the actual validation authority.
