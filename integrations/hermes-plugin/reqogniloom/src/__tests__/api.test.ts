import { describe, expect, it, vi } from "vitest";
import {
  createRequirement,
  getRequirement,
  listRequirements,
  listWorkspaces,
  updateRequirement,
  type Requirement,
  type HermesNetworkAPI,
  ReqogniLoomApiError,
} from "../api";

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

// ---------------------------------------------------------------------------
// Requirements (Phase H / #1701, Task 2)
// ---------------------------------------------------------------------------

const CONN = { baseUrl: "https://x", apiKey: "KEY", workspaceId: "WS" };

const REQ: Requirement = {
  id: "req-1",
  artifact_id: "art-1",
  global_uuid: "art-1",
  workspace_id: "WS",
  parent_id: null,
  uid: "REQ-1",
  title: "Login must work",
  description: "",
  acceptance_criteria: "",
  category: "security",
  type: "SyReq",
  complexity_fibonacci: 3,
  verification_method: "Test",
  level: 2,
  tier_key: "system",
  tier_name: "System",
  released_tier_key: null,
  level_source: "derived",
  allocation_intent: "unassigned",
  status: "draft",
  suspect: false,
  atomicity_warning: null,
  version: 7,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-02T00:00:00Z",
};

type RecordedCall = {
  url: string;
  method: string;
  headers: Record<string, string>;
  body: string;
};

// Same shape as the plan's `fakeNetwork`: one JSON body for every call, plus
// normalized access to what actually went over the wire.
function fakeNetwork(body: unknown): { network: HermesNetworkAPI; calls: RecordedCall[] } {
  const calls: RecordedCall[] = [];
  const network: HermesNetworkAPI = {
    fetch: async (url, options) => {
      calls.push({
        url,
        method: (options?.method as string | undefined) ?? "GET",
        headers: (options?.headers ?? {}) as Record<string, string>,
        body: typeof options?.body === "string" ? options.body : "",
      });
      return JSON.stringify(body);
    },
  };
  return { network, calls };
}

function responseWith(status: number, body: unknown): { status: number; text: () => Promise<string> } {
  return { status, text: async () => JSON.stringify(body) };
}

describe("listRequirements", () => {
  it("lists requirements for the workspace with page, page_size and search in that order", async () => {
    const fake = fakeNetwork({ count: 1, next: null, previous: null, results: [REQ] });

    const response = await listRequirements(fake.network, CONN, { page: 2, pageSize: 25, search: "login" });

    expect(fake.calls[0].url).toBe(
      "https://x/api/v1/requirements/?workspace_id=WS&page=2&page_size=25&search=login"
    );
    expect(fake.calls[0].method).toBe("GET");
    expect(fake.calls[0].headers["X-API-Key"]).toBe("KEY");
    expect(response.results).toEqual([REQ]);
    expect(response.count).toBe(1);
  });

  it("defaults to page 1 and page_size 25 and omits an empty search", async () => {
    const fake = fakeNetwork({ count: 0, next: null, previous: null, results: [] });

    await listRequirements(fake.network, CONN);

    expect(fake.calls[0].url).toBe("https://x/api/v1/requirements/?workspace_id=WS&page=1&page_size=25");
  });

  it("passes an absolute next link through unchanged instead of rebuilding it", async () => {
    const fake = fakeNetwork({ count: 30, next: null, previous: null, results: [] });
    const nextLink = "https://x/api/v1/requirements/?workspace_id=WS&page=2&page_size=25&search=login";

    await listRequirements(fake.network, CONN, { url: nextLink });

    expect(fake.calls[0].url).toBe(nextLink);
    expect(fake.calls[0].headers["X-API-Key"]).toBe("KEY");
  });

  it("throws a typed error when a 200 body has no results array", async () => {
    const fake = fakeNetwork({ count: 0, next: null, previous: null });

    await expect(listRequirements(fake.network, CONN)).rejects.toMatchObject({
      name: "ReqogniLoomApiError",
      message: "GET /api/v1/requirements/?workspace_id=WS&page=1&page_size=25 returned a body with no results array",
    });
  });

  it("keeps the nested error envelope's field details on the thrown error", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      responseWith(400, {
        error: {
          code: "VALIDATION_ERROR",
          message: "Invalid request.",
          details: [{ field: "search", errors: ["Unsupported search term."] }],
        },
      })
    );

    await expect(listRequirements({ fetch: fetchMock }, CONN)).rejects.toMatchObject({
      name: "ReqogniLoomApiError",
      status: 400,
      message: "Invalid request.",
      envelope: {
        error: {
          details: [{ field: "search", errors: ["Unsupported search term."] }],
        },
      },
    });
  });
});

describe("getRequirement", () => {
  it("GETs the detail route with a trailing slash and returns the requirement", async () => {
    const fake = fakeNetwork(REQ);

    const requirement = await getRequirement(fake.network, CONN, "req-1");

    expect(fake.calls[0].url).toBe("https://x/api/v1/requirements/req-1/");
    expect(fake.calls[0].headers["X-API-Key"]).toBe("KEY");
    expect(requirement).toEqual(REQ);
  });

  it("throws a typed error instead of returning a body with no requirement id", async () => {
    const fake = fakeNetwork({ detail: "Not found." });

    await expect(getRequirement(fake.network, CONN, "req-1")).rejects.toBeInstanceOf(ReqogniLoomApiError);
  });
});

describe("createRequirement", () => {
  it("sends workspace_id from the connection and never level, tier_key or level_source", async () => {
    const fake = fakeNetwork(REQ);

    await createRequirement(fake.network, CONN, {
      title: "Login must work",
      ...({ level: 3, tier_key: "system", level_source: "manual", id: "req-1", uid: "REQ-1", version: 9 } as object),
    });

    expect(fake.calls[0].method).toBe("POST");
    expect(fake.calls[0].url).toBe("https://x/api/v1/requirements/");
    const body = JSON.parse(fake.calls[0].body);
    expect(body.workspace_id).toBe("WS");
    expect(body.title).toBe("Login must work");
    expect(body).not.toHaveProperty("level");
    expect(body).not.toHaveProperty("tier_key");
    expect(body).not.toHaveProperty("level_source");
    expect(body).not.toHaveProperty("uid");
    expect(body).not.toHaveProperty("id");
    expect(body).not.toHaveProperty("version");
  });

  it("maps a flat error envelope to a ReqogniLoomApiError", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      responseWith(403, {
        error: "permission_denied",
        message: "This API key may not create requirements.",
        doc_url: "https://docs.reqogniloom.dev/errors/permission_denied",
      })
    );

    await expect(createRequirement({ fetch: fetchMock }, CONN, { title: "T" })).rejects.toMatchObject({
      name: "ReqogniLoomApiError",
      status: 403,
      message: "This API key may not create requirements.",
    });
  });
});

describe("updateRequirement", () => {
  it("PATCHes the detail route with expected_version and the change reason", async () => {
    const fake = fakeNetwork(REQ);

    await updateRequirement(fake.network, CONN, "req-1", {
      title: "Login must work twice",
      version: 7,
      change_reason: "clarified the login wording",
    });

    expect(fake.calls[0].method).toBe("PATCH");
    expect(fake.calls[0].url).toBe("https://x/api/v1/requirements/req-1/");
    const body = JSON.parse(fake.calls[0].body);
    // The backend compares `expected_version`; the read-back key is `version`
    // and DRF would silently drop it on write.
    expect(body.expected_version).toBe(7);
    expect(body.change_reason).toBe("clarified the login wording");
    expect(body.title).toBe("Login must work twice");
    expect(body).not.toHaveProperty("version");
    expect(body).not.toHaveProperty("level");
    expect(body).not.toHaveProperty("tier_key");
    expect(body).not.toHaveProperty("level_source");
    expect(body).not.toHaveProperty("workspace_id");
  });

  it("omits change_reason when the caller did not supply one", async () => {
    const fake = fakeNetwork(REQ);

    await updateRequirement(fake.network, CONN, "req-1", { title: "Renamed", version: 7 });

    const body = JSON.parse(fake.calls[0].body);
    expect(body).not.toHaveProperty("change_reason");
    expect(body.expected_version).toBe(7);
  });

  it("surfaces a 409 as a ReqogniLoomApiError with its status", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      responseWith(409, {
        error: { code: "CONFLICT", message: "Version mismatch.", details: [] },
      })
    );

    await expect(
      updateRequirement({ fetch: fetchMock }, CONN, "req-1", { title: "T", version: 6 })
    ).rejects.toMatchObject({ name: "ReqogniLoomApiError", status: 409, message: "Version mismatch." });
  });
});
