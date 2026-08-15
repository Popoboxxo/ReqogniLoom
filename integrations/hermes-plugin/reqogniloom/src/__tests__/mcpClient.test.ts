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
