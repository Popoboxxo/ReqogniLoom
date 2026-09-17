import { describe, expect, it, vi } from "vitest";
import {
  callMcpTool,
  McpRpcError,
  interviewAnswer,
  interviewFormalize,
  interviewGetState,
  interviewGroundingContext,
  interviewList,
  interviewSetTarget,
  interviewStart,
} from "../mcpClient";

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

  it("interviewSetTarget sends session_id/artifact_id and returns the refreshed state", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      JSON.stringify({
        jsonrpc: "2.0",
        id: 1,
        result: {
          session_id: "s-1",
          status: "in_progress",
          phase: "elicitation",
          collected_fields: {},
          missing_fields: [],
          grounding_snapshot: { candidates: [{ artifact_id: "art-9", title: "Existing req", score: null }] },
        },
      })
    );

    const state = await interviewSetTarget({ fetch: fetchMock }, CONNECTION, "s-1", "art-9");

    const body = JSON.parse(fetchMock.mock.calls[0][1].body as string);
    expect(body.method).toBe("interview.set_target");
    expect(body.params).toEqual({ session_id: "s-1", artifact_id: "art-9" });
    expect(state.session_id).toBe("s-1");
  });
});
