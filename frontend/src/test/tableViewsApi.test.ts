/**
 * Task 4.1 — table view API wrapper (plan 2026-11-04-tabellenansicht-s4).
 *
 * Pins the wire format of the slice-1/2/3 endpoints the table builds on:
 * JSON-serialised `filters`/`sort`, the atomic-failure body that must not be
 * thrown away, and the saved-view/state paths.
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

  it("defaults the bulk mode to atomic", async () => {
    mockPatch.mockResolvedValue({
      committed: true,
      mode: "atomic",
      updated: [],
      failed: [],
    });

    await tableApi.bulkUpdate({ items: [] });

    const [path, body] = mockPatch.mock.calls[0];
    expect(path).toBe("/artifacts/bulk-update/");
    expect(body.mode).toBe("atomic");
  });

  it("returns the failure body on 409/400 with committed:false instead of throwing", async () => {
    const failed = [
      { index: 1, artifact_id: "a", code: "CONFLICT", reason: "version" },
    ];
    mockPatch
      .mockRejectedValueOnce({ committed: false, mode: "atomic", failed })
      .mockRejectedValueOnce({ committed: false, mode: "partial", failed });

    const atomic = await tableApi.bulkUpdate({ items: [] });
    const partial = await tableApi.bulkUpdate({ mode: "partial", items: [] });
    expect(atomic.committed).toBe(false);
    expect(atomic.failed).toEqual(failed);
    expect(partial.committed).toBe(false);
  });

  it("throws on 403", async () => {
    mockPatch.mockRejectedValue({ error: { code: "FORBIDDEN" } });
    await expect(tableApi.bulkUpdate({ items: [] })).rejects.toEqual({
      error: { code: "FORBIDDEN" },
    });
  });

  it("posts the bulk transition body", async () => {
    mockPost.mockResolvedValue({ transitioned: [], failed: [] });

    await tableApi.bulkTransition({
      item_type: "Requirement",
      ids: ["a"],
      to_state: "approved",
      change_reason: "ok",
    });

    const [path, body] = mockPost.mock.calls[0];
    expect(path).toBe("/artifacts/bulk-transition/");
    expect(body).toEqual({
      item_type: "Requirement",
      ids: ["a"],
      to_state: "approved",
      change_reason: "ok",
    });
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
