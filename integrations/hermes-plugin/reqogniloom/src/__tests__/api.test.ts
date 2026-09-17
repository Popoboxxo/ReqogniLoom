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
});
