import { describe, expect, it, vi } from "vitest";
import { listWorkspaces, ReqogniLoomApiError } from "../api";

describe("listWorkspaces", () => {
  it("sends the X-API-Key header and returns results", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      JSON.stringify({
        count: 1,
        next: null,
        previous: null,
        results: [{ id: "ws-1", name: "Alpha" }],
      })
    );

    const workspaces = await listWorkspaces(
      { fetch: fetchMock },
      { baseUrl: "https://example.com", apiKey: "reqlo_abc" }
    );

    expect(workspaces).toEqual([{ id: "ws-1", name: "Alpha" }]);
    expect(fetchMock).toHaveBeenCalledWith(
      "https://example.com/api/v1/workspaces/",
      expect.objectContaining({
        headers: expect.objectContaining({ "X-API-Key": "reqlo_abc" }),
      })
    );
  });

  it("strips a trailing slash from baseUrl before appending the path", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      JSON.stringify({ count: 0, next: null, previous: null, results: [] })
    );

    await listWorkspaces({ fetch: fetchMock }, { baseUrl: "https://example.com/", apiKey: "reqlo_abc" });

    expect(fetchMock).toHaveBeenCalledWith("https://example.com/api/v1/workspaces/", expect.anything());
  });

  it("handles a string return shape (network.fetch returns response body as text)", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      JSON.stringify({
        count: 2,
        next: null,
        previous: null,
        results: [
          { id: "ws-1", name: "Alpha" },
          { id: "ws-2", name: "Beta" },
        ],
      })
    );

    const workspaces = await listWorkspaces(
      { fetch: fetchMock },
      { baseUrl: "https://example.com", apiKey: "reqlo_abc" }
    );

    expect(workspaces).toHaveLength(2);
  });

  it("handles a Response return shape (network.fetch returns a Response-like object)", async () => {
    const body = JSON.stringify({
      count: 1,
      next: null,
      previous: null,
      results: [{ id: "ws-1", name: "Alpha" }],
    });
    const fakeResponse = {
      status: 200,
      text: async () => body,
    };
    const fetchMock = vi.fn().mockResolvedValue(fakeResponse);

    const workspaces = await listWorkspaces(
      { fetch: fetchMock },
      { baseUrl: "https://example.com", apiKey: "reqlo_abc" }
    );

    expect(workspaces).toEqual([{ id: "ws-1", name: "Alpha" }]);
  });

  it("throws ReqogniLoomApiError for a non-JSON, non-empty string response", async () => {
    const fetchMock = vi.fn().mockResolvedValue("<html>502 Bad Gateway</html>");

    await expect(
      listWorkspaces({ fetch: fetchMock }, { baseUrl: "https://example.com", apiKey: "reqlo_abc" })
    ).rejects.toBeInstanceOf(ReqogniLoomApiError);
  });

  it("propagates the error message from a bad-key error envelope", async () => {
    const errorBody = JSON.stringify({
      error: {
        code: "AUTHENTICATION_FAILED",
        message: "Invalid API key",
        details: [],
      },
    });
    const fetchMock = vi.fn().mockResolvedValue(errorBody);

    await expect(
      listWorkspaces({ fetch: fetchMock }, { baseUrl: "https://example.com", apiKey: "reqlo_bad" })
    ).rejects.toMatchObject({
      message: "Invalid API key",
    });
  });

  it("propagates a Response-shaped error status with envelope message", async () => {
    const errorBody = JSON.stringify({
      error: {
        code: "AUTHENTICATION_FAILED",
        message: "Invalid API key",
        details: [],
      },
    });
    const fakeResponse = {
      status: 401,
      text: async () => errorBody,
    };
    const fetchMock = vi.fn().mockResolvedValue(fakeResponse);

    await expect(
      listWorkspaces({ fetch: fetchMock }, { baseUrl: "https://example.com", apiKey: "reqlo_bad" })
    ).rejects.toMatchObject({
      message: "Invalid API key",
      status: 401,
    });
  });

  it("propagates the top-level message from a FLAT auth-failure error body (invalid API key)", async () => {
    // The flat body {"error": "<code>", "message": "...", "doc_url": "..."}.
    // build_error_body() emitted this until the 2026-08-27 system audit (P1
    // item 13) and now uses the nested envelope, but several other REST
    // modules still answer flat (rest_workspace_members.py,
    // rest_item_permission.py, admin_ops/rest.py, banner_rest.py) and this
    // plugin may face an older backend — so the flat path stays covered.
    const errorBody = JSON.stringify({
      error: "invalid_api_key",
      message: "Invalid or expired API key.",
      doc_url: "https://docs.reqogniloom.dev/errors/invalid_api_key",
    });
    const fakeResponse = {
      status: 401,
      text: async () => errorBody,
    };
    const fetchMock = vi.fn().mockResolvedValue(fakeResponse);

    await expect(
      listWorkspaces({ fetch: fetchMock }, { baseUrl: "https://example.com", apiKey: "reqlo_bad" })
    ).rejects.toMatchObject({
      message: "Invalid or expired API key.",
      status: 401,
    });
  });

  it.each([null, undefined])(
    "throws a named error, not a TypeError, when network.fetch resolves to %s",
    async (value) => {
      const fetchMock = vi.fn().mockResolvedValue(value);

      await expect(
        listWorkspaces({ fetch: fetchMock }, { baseUrl: "https://example.com", apiKey: "reqlo_abc" })
      ).rejects.toThrow(new Error("GET /api/v1/workspaces/ returned a non-Response value"));
    }
  );

  it("throws a typed ReqogniLoomApiError when a 200 body is an array instead of a paginated envelope", async () => {
    const fetchMock = vi.fn().mockResolvedValue(JSON.stringify([{ id: "ws-1", name: "Alpha" }]));

    await expect(
      listWorkspaces({ fetch: fetchMock }, { baseUrl: "https://example.com", apiKey: "reqlo_abc" })
    ).rejects.toMatchObject({
      name: "ReqogniLoomApiError",
      message: "GET /api/v1/workspaces/ returned a body with no results array",
    });
  });

  it("throws a typed ReqogniLoomApiError when a 200 body lacks a results key", async () => {
    const fetchMock = vi.fn().mockResolvedValue(JSON.stringify({ count: 0, next: null, previous: null }));

    await expect(
      listWorkspaces({ fetch: fetchMock }, { baseUrl: "https://example.com", apiKey: "reqlo_abc" })
    ).rejects.toBeInstanceOf(ReqogniLoomApiError);
  });

  it("aborts the request after a timeout so a hung server cannot wedge the panel", async () => {
    const timeoutSpy = vi.spyOn(AbortSignal, "timeout");
    const fetchMock = vi.fn().mockResolvedValue(
      JSON.stringify({ count: 0, next: null, previous: null, results: [] })
    );

    await listWorkspaces({ fetch: fetchMock }, { baseUrl: "https://example.com", apiKey: "reqlo_abc" });

    expect(timeoutSpy).toHaveBeenCalledWith(15_000);
    expect(fetchMock.mock.calls[0][1].signal).toBeInstanceOf(AbortSignal);
    timeoutSpy.mockRestore();
  });

  it("propagates an aborted request as the abort error", async () => {
    const fetchMock = vi.fn().mockRejectedValue(new DOMException("The operation was aborted", "TimeoutError"));

    await expect(
      listWorkspaces({ fetch: fetchMock }, { baseUrl: "https://example.com", apiKey: "reqlo_abc" })
    ).rejects.toThrow(/aborted/);
  });

  it("follows next across pages and returns every workspace", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        JSON.stringify({
          count: 3,
          next: "https://example.com/api/v1/workspaces/?page=2",
          previous: null,
          results: [
            { id: "ws-1", name: "Alpha" },
            { id: "ws-2", name: "Beta" },
          ],
        })
      )
      .mockResolvedValueOnce(
        JSON.stringify({
          count: 3,
          next: null,
          previous: null,
          results: [{ id: "ws-3", name: "Gamma" }],
        })
      );

    const workspaces = await listWorkspaces(
      { fetch: fetchMock },
      { baseUrl: "https://example.com", apiKey: "reqlo_abc" }
    );

    expect(workspaces.map((w) => w.id)).toEqual(["ws-1", "ws-2", "ws-3"]);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock.mock.calls[1][0]).toBe("https://example.com/api/v1/workspaces/?page=2");
  });

  it("stops when the server repeats a next link", async () => {
    const loopUrl = "https://example.com/api/v1/workspaces/?page=2";
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        JSON.stringify({ count: 2, next: loopUrl, previous: null, results: [{ id: "ws-1", name: "A" }] })
      )
      .mockResolvedValueOnce(
        JSON.stringify({ count: 2, next: loopUrl, previous: null, results: [{ id: "ws-2", name: "B" }] })
      );

    const workspaces = await listWorkspaces(
      { fetch: fetchMock },
      { baseUrl: "https://example.com", apiKey: "reqlo_abc" }
    );

    expect(workspaces.map((w) => w.id)).toEqual(["ws-1", "ws-2"]);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});
