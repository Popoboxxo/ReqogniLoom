import { describe, it, expect, vi } from "vitest";
import {
  listWorkspaces,
  listRequirements,
  getRequirement,
  createRequirement,
  updateRequirement,
  ReqogniLoomApiError,
  type HermesNetworkAPI,
  type Connection,
} from "../api";

const connection: Connection = {
  baseUrl: "https://reqo.example.com",
  apiKey: "reqlo_test123",
  workspaceId: "11111111-1111-1111-1111-111111111111",
};

function mockNetwork(impl: (url: string, options?: RequestInit) => unknown): HermesNetworkAPI {
  return { fetch: vi.fn(async (url: string, options?: RequestInit) => impl(url, options)) };
}

describe("listWorkspaces", () => {
  it("sends X-API-Key header and returns parsed workspaces (string-return shape)", async () => {
    const network = mockNetwork((url, options) => {
      expect(url).toBe("https://reqo.example.com/api/v1/workspaces/");
      expect((options?.headers as Record<string, string>)["X-API-Key"]).toBe("reqlo_test123");
      return JSON.stringify({
        count: 1,
        next: null,
        previous: null,
        results: [{ id: "w1", name: "Demo" }],
      });
    });
    const workspaces = await listWorkspaces(network, {
      baseUrl: connection.baseUrl,
      apiKey: connection.apiKey,
    });
    expect(workspaces).toEqual([{ id: "w1", name: "Demo" }]);
  });

  it("supports the Response-return shape too", async () => {
    const network = mockNetwork(() =>
      new Response(
        JSON.stringify({ count: 0, next: null, previous: null, results: [] }),
        { status: 200 }
      )
    );
    const workspaces = await listWorkspaces(network, {
      baseUrl: connection.baseUrl,
      apiKey: connection.apiKey,
    });
    expect(workspaces).toEqual([]);
  });

  it("throws ReqogniLoomApiError with the error envelope on 401 (Response shape)", async () => {
    const network = mockNetwork(
      () =>
        new Response(
          JSON.stringify({ error: { code: "AUTHENTICATION_FAILED", message: "Invalid API key", details: [] } }),
          { status: 401 }
        )
    );
    await expect(
      listWorkspaces(network, { baseUrl: connection.baseUrl, apiKey: connection.apiKey })
    ).rejects.toMatchObject({
      status: 401,
      envelope: { error: { code: "AUTHENTICATION_FAILED" } },
    });
  });

  it("throws ReqogniLoomApiError on 401 in the string-return shape too (no HTTP status observable)", async () => {
    const network = mockNetwork(() =>
      JSON.stringify({ error: { code: "AUTHENTICATION_FAILED", message: "Invalid API key", details: [] } })
    );
    await expect(
      listWorkspaces(network, { baseUrl: connection.baseUrl, apiKey: connection.apiKey })
    ).rejects.toBeInstanceOf(ReqogniLoomApiError);
  });

  it("throws ReqogniLoomApiError on non-JSON string responses (e.g., plain-text error bodies)", async () => {
    const network = mockNetwork(() => "Bad Gateway");
    await expect(
      listWorkspaces(network, { baseUrl: connection.baseUrl, apiKey: connection.apiKey })
    ).rejects.toBeInstanceOf(ReqogniLoomApiError);
  });
});

describe("listRequirements", () => {
  it("builds the query string with workspace_id, page, page_size, and search", async () => {
    const network = mockNetwork((url) => {
      expect(url).toContain("/api/v1/requirements/?");
      expect(url).toContain(`workspace_id=${connection.workspaceId}`);
      expect(url).toContain("page=2");
      expect(url).toContain("page_size=25");
      expect(url).toContain("search=login");
      return JSON.stringify({ count: 0, next: null, previous: null, results: [] });
    });
    await listRequirements(network, connection, { page: 2, search: "login" });
  });

  it("omits search when not provided", async () => {
    const network = mockNetwork((url) => {
      expect(url).not.toContain("search=");
      return JSON.stringify({ count: 0, next: null, previous: null, results: [] });
    });
    await listRequirements(network, connection);
  });
});

describe("getRequirement", () => {
  it("fetches the single-requirement endpoint", async () => {
    const network = mockNetwork((url) => {
      expect(url).toBe("https://reqo.example.com/api/v1/requirements/req-1/");
      return JSON.stringify({ id: "req-1", title: "Login must work" });
    });
    const req = await getRequirement(network, connection, "req-1");
    expect(req.id).toBe("req-1");
  });
});

describe("createRequirement", () => {
  it("POSTs with workspace_id injected and returns the created requirement", async () => {
    const network = mockNetwork((url, options) => {
      expect(options?.method).toBe("POST");
      const body = JSON.parse(options!.body as string);
      expect(body.workspace_id).toBe(connection.workspaceId);
      expect(body.title).toBe("New requirement");
      return JSON.stringify({ id: "req-2", title: "New requirement" });
    });
    const req = await createRequirement(network, connection, { title: "New requirement" });
    expect(req.id).toBe("req-2");
  });

  it("surfaces field-level 400 errors via the standard envelope", async () => {
    const network = mockNetwork(
      () =>
        new Response(
          JSON.stringify({
            error: {
              code: "VALIDATION_ERROR",
              message: "Validation failed",
              details: [{ field: "title", errors: ["This field is required."] }],
            },
          }),
          { status: 400 }
        )
    );
    await expect(createRequirement(network, connection, { title: "" })).rejects.toMatchObject({
      status: 400,
      envelope: {
        error: { details: [{ field: "title", errors: ["This field is required."] }] },
      },
    });
  });
});

describe("updateRequirement", () => {
  it("PATCHes without workspace_id (not part of update payload)", async () => {
    const network = mockNetwork((url, options) => {
      expect(url).toBe("https://reqo.example.com/api/v1/requirements/req-1/");
      expect(options?.method).toBe("PATCH");
      const body = JSON.parse(options!.body as string);
      expect(body).not.toHaveProperty("workspace_id");
      expect(body.title).toBe("Updated title");
      return JSON.stringify({ id: "req-1", title: "Updated title" });
    });
    const req = await updateRequirement(network, connection, "req-1", { title: "Updated title" });
    expect(req.title).toBe("Updated title");
  });
});
