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
});
