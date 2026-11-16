/**
 * Task 4.1 — table view API wrapper (plan 2026-11-04-tabellenansicht-s4).
 *
 * Pins the wire format of the slice-1/2/3 endpoints the table builds on:
 * JSON-serialised `filters`/`sort`, the bulk-update body/answer exactly as the
 * merged backend declares it (`{workspace_id, entries}` → `{updated, errors}`,
 * 409 mapped to `committed:false`), and the saved-view/state paths.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

const mockGet = vi.fn();
const mockPost = vi.fn();
const mockPatch = vi.fn();
const mockPut = vi.fn();
const mockDelete = vi.fn();

vi.mock("../api/client", () => ({
  apiClient: {
    get: (...a: unknown[]) => mockGet(...a),
    post: (...a: unknown[]) => mockPost(...a),
    patch: (...a: unknown[]) => mockPatch(...a),
    put: (...a: unknown[]) => mockPut(...a),
    delete: (...a: unknown[]) => mockDelete(...a),
  },
  getList: vi.fn(),
  extractErrorMessage: (err: unknown) => String(err),
}));

import { getList } from "../api/client";
import {
  EMPTY_TABLE_VIEW_STATE,
  savedViewsApi,
  tableApi,
  tableViewStateApi,
} from "../api/table-views";

const WS = "11111111-1111-1111-1111-111111111111";
const VIEW = "22222222-2222-2222-2222-222222222222";

describe("tableApi", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("serialises filters and sort as JSON query parameters", async () => {
    (getList as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      count: 0,
      results: [],
    });

    await tableApi.query({
      workspace_id: WS,
      item_type: "Requirement",
      filters: { status: { op: "in", value: ["draft"] } },
      sort: [{ field: "title", dir: "asc" }],
      page: 2,
      page_size: 50,
    });

    const [path, params] = (getList as unknown as ReturnType<typeof vi.fn>).mock
      .calls[0] as [string, Record<string, string>];
    expect(path).toBe("/artifacts/table/");
    expect(params.workspace_id).toBe(WS);
    expect(params.item_type).toBe("Requirement");
    expect(JSON.parse(params.filters)).toEqual({
      status: { op: "in", value: ["draft"] },
    });
    expect(JSON.parse(params.sort)).toEqual([{ field: "title", dir: "asc" }]);
    expect(params.page).toBe("2");
    expect(params.page_size).toBe("50");
  });

  it("always carries filters and sort, even when they are empty", async () => {
    // The e2e guardrail reads the *parsed* term out of the query string and
    // treats an absent parameter as "no sort at all", so the parameters must be
    // present from the first request on — not omitted until the user clicks.
    (getList as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      count: 0,
      results: [],
    });

    await tableApi.query({
      workspace_id: WS,
      item_type: "Requirement",
      filters: {},
      sort: [],
    });

    const [, params] = (getList as unknown as ReturnType<typeof vi.fn>).mock
      .calls[0] as [string, Record<string, string>];
    expect(params.sort).toBe("[]");
    expect(params.filters).toBe("{}");
  });

  it("serialises a single constraint as the frozen DSL object", async () => {
    (getList as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      count: 0,
      results: [],
    });

    await tableApi.query({
      workspace_id: WS,
      item_type: "Requirement",
      filters: { title: { op: "contains", value: "Alpha" } },
      sort: [{ field: "title", dir: "asc" }],
    });

    const [, params] = (getList as unknown as ReturnType<typeof vi.fn>).mock
      .calls[0] as [string, Record<string, string>];
    // `{"<field>": {"op": …, "value": …}}`, not a bare `{field: value}` search.
    expect(JSON.parse(params.filters)).toEqual({
      title: { op: "contains", value: "Alpha" },
    });
    expect(JSON.parse(params.sort)).toEqual([{ field: "title", dir: "asc" }]);
  });

  it("sends the backend body: workspace_id + entries", async () => {
    mockPatch.mockResolvedValue({
      updated: [{ artifact_id: "artifact-1", version: 5 }],
      errors: [],
    });

    const result = await tableApi.bulkUpdate({
      workspace_id: WS,
      entries: [
        { artifact_id: "artifact-1", expected_version: 4, fields: { title: "New" } },
      ],
    });

    const [path, body] = mockPatch.mock.calls[0];
    expect(path).toBe("/artifacts/bulk-update/");
    expect(body).toEqual({
      workspace_id: WS,
      entries: [
        { artifact_id: "artifact-1", expected_version: 4, fields: { title: "New" } },
      ],
    });
    expect(result.committed).toBe(true);
    expect(result.updated).toEqual([{ artifact_id: "artifact-1", version: 5 }]);
    expect(result.failed).toEqual([]);
  });

  it("maps a 409 refusal body to committed:false with the per-entry errors", async () => {
    const errors = [
      { index: 0, artifact_id: "artifact-1", code: "CONFLICT", message: "stale version" },
      { index: 1, artifact_id: "artifact-2", code: "FIELD_FROZEN", message: "frozen", field: "title" },
    ];
    mockPatch.mockRejectedValue({ updated: [], errors });

    const result = await tableApi.bulkUpdate({
      workspace_id: WS,
      entries: [
        { artifact_id: "artifact-1", expected_version: 1, fields: { title: "a" } },
        { artifact_id: "artifact-2", expected_version: 1, fields: { title: "b" } },
      ],
    });

    expect(result.committed).toBe(false);
    expect(result.updated).toEqual([]);
    expect(result.failed).toEqual(errors);
    expect(result.failed[1].field).toBe("title");
  });

  it("throws on a malformed 400 and on 403 instead of reporting a refusal", async () => {
    mockPatch
      .mockRejectedValueOnce({
        error: { code: "VALIDATION_ERROR", message: "bad body", details: [] },
      })
      .mockRejectedValueOnce({ error: { code: "FORBIDDEN", message: "no role" } });

    await expect(
      tableApi.bulkUpdate({ workspace_id: WS, entries: [] })
    ).rejects.toEqual({
      error: { code: "VALIDATION_ERROR", message: "bad body", details: [] },
    });
    await expect(
      tableApi.bulkUpdate({ workspace_id: WS, entries: [] })
    ).rejects.toEqual({ error: { code: "FORBIDDEN", message: "no role" } });
  });

  it("posts the bulk transition body without a workspace_id", async () => {
    mockPost.mockResolvedValue({
      transitioned: [{ artifact_id: "artifact-1", state: "approved" }],
      failed: [],
    });

    const result = await tableApi.bulkTransition({
      item_type: "Requirement",
      ids: ["artifact-1"],
      to_state: "approved",
      change_reason: "ok",
    });

    const [path, body] = mockPost.mock.calls[0];
    expect(path).toBe("/artifacts/bulk-transition/");
    expect(body).toEqual({
      item_type: "Requirement",
      ids: ["artifact-1"],
      to_state: "approved",
      change_reason: "ok",
    });
    expect(body).not.toHaveProperty("workspace_id");
    expect(result.transitioned).toEqual([
      { artifact_id: "artifact-1", state: "approved" },
    ]);
    expect(result.failed).toEqual([]);
  });
});

describe("savedViewsApi", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("uses the documented CRUD paths", async () => {
    mockGet.mockResolvedValue({ results: [] });
    await savedViewsApi.list(WS, "Requirement");
    expect(mockGet.mock.calls[0][0]).toContain(
      `/saved-views/?workspace_id=${WS}&item_type=Requirement`
    );

    mockPost.mockResolvedValue({ id: VIEW });
    await savedViewsApi.create(WS, "Requirement", {
      name: "Mine",
      columns: [],
      filters: {},
      sort: [],
    });
    const [postPath, postBody] = mockPost.mock.calls[0];
    expect(postPath).toBe("/saved-views/");
    expect(postBody).toMatchObject({
      workspace_id: WS,
      item_type: "Requirement",
      name: "Mine",
    });

    mockPatch.mockResolvedValue({ id: VIEW });
    await savedViewsApi.update(VIEW, { name: "Renamed" });
    expect(mockPatch.mock.calls[0][0]).toBe(`/saved-views/${VIEW}/`);

    mockGet.mockResolvedValue({ id: VIEW });
    await savedViewsApi.get(VIEW);
    expect(mockGet.mock.calls[1][0]).toBe(`/saved-views/${VIEW}/`);

    mockDelete.mockResolvedValue(undefined);
    await savedViewsApi.remove(VIEW);
    expect(mockDelete.mock.calls[0][0]).toBe(`/saved-views/${VIEW}/`);

    mockGet.mockResolvedValue({ results: [], warnings: [] });
    await savedViewsApi.apply(VIEW, { workspace_id: WS, page: 1 });
    expect(mockGet.mock.calls[2][0]).toContain(`/saved-views/${VIEW}/apply/`);
  });
});

describe("tableViewStateApi", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("PUT path has workspace and item type and defaults a missing record", async () => {
    mockPut.mockResolvedValue(EMPTY_TABLE_VIEW_STATE);
    await tableViewStateApi.put(WS, "Requirement", {
      columns: [{ field: "title", order: 0 }],
      filters: {},
      sort: [],
    });
    const [path, body] = mockPut.mock.calls[0];
    expect(path).toContain(
      `/users/me/table-view-state/?workspace_id=${WS}&item_type=Requirement`
    );
    expect(body.columns).toHaveLength(1);

    mockGet.mockResolvedValue({});
    const result = await tableViewStateApi.get(WS, "Requirement");
    expect(result).toEqual(EMPTY_TABLE_VIEW_STATE);
  });
});
