/**
 * B1 / R2A-005 — the review queue only ever saw the backend's first page.
 *
 * ``GET /api/v1/requirements/?status=in_review`` answers the standard DRF
 * pagination envelope with ``PAGE_SIZE=25`` (settings.py) and ``page_size``
 * capped at 100. ``requirementsApi.list()`` used to issue exactly one request
 * and hand back that single page, so a workspace with 28 ``in_review``
 * requirements silently hid the newest three from the reviewer.
 *
 * The pagination walk itself now lives in `client.ts::getAllPagesWithCount`
 * (pinned in `pagination-walkers.test.ts`). This file pins the contract at the
 * `requirementsApi` seam: every list entry point must delegate to that helper
 * with the right filters, and must pass its `{ count, results }` through
 * unchanged — including the envelope shape callers rely on.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";

const mockGetAllPagesWithCount = vi.fn();

vi.mock("./client", () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
  getAllPagesWithCount: (...a: unknown[]) => mockGetAllPagesWithCount(...a),
  extractErrorMessage: (err: unknown) => String(err),
}));

import { requirementsApi } from "./requirements";

const WORKSPACE = "11111111-1111-1111-1111-111111111111";

function requirement(n: number) {
  return {
    id: `00000000-0000-0000-0000-${String(n).padStart(12, "0")}`,
    workspace_id: WORKSPACE,
    title: `Requirement ${n}`,
  };
}

describe("requirementsApi.list full pagination (B1 / R2A-005)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetAllPagesWithCount.mockResolvedValue({
      count: 0,
      results: [],
    });
  });

  it("delegates the whole walk to getAllPagesWithCount with the status filter", async () => {
    const results = [requirement(1)];
    mockGetAllPagesWithCount.mockResolvedValue({ count: 1, results });

    const resp = await requirementsApi.list(WORKSPACE, "in_review");

    // The walker adds page_size=100 and does the actual page walk; the wrapper
    // only owns the request filters.
    expect(mockGetAllPagesWithCount).toHaveBeenCalledWith("/requirements/", {
      workspace_id: WORKSPACE,
      status: "in_review",
    });
    expect(resp).toEqual({
      count: 1,
      next: null,
      previous: null,
      results,
    });
  });

  it("passes every merged page through, not just the first 25", async () => {
    const results = Array.from({ length: 28 }, (_, i) => requirement(i + 1));
    mockGetAllPagesWithCount.mockResolvedValue({ count: 28, results });

    const resp = await requirementsApi.list(WORKSPACE);

    expect(resp.results).toHaveLength(28);
    expect(resp.count).toBe(28);
    expect(resp.next).toBeNull();
  });

  it("does not add a second request of its own", async () => {
    await requirementsApi.list(WORKSPACE);

    expect(mockGetAllPagesWithCount).toHaveBeenCalledTimes(1);
  });

  // F2: `list` used to read only its positional `status` and silently ignore
  // `options.status`; the positional argument still wins on conflict.
  it("honors options.status when no positional status is given (F2)", async () => {
    await requirementsApi.list(WORKSPACE, undefined, { status: "in_review" });

    expect(mockGetAllPagesWithCount).toHaveBeenCalledWith("/requirements/", {
      workspace_id: WORKSPACE,
      status: "in_review",
    });
  });

  it("lets the positional status win over options.status (F2)", async () => {
    await requirementsApi.list(WORKSPACE, "approved", { status: "in_review" });

    expect(mockGetAllPagesWithCount).toHaveBeenCalledWith("/requirements/", {
      workspace_id: WORKSPACE,
      status: "approved",
    });
  });

  it("threads listAll's filters through the same helper", async () => {
    const results = [requirement(1)];
    mockGetAllPagesWithCount.mockResolvedValue({ count: 1, results });

    const all = await requirementsApi.listAll(WORKSPACE, {
      status: "approved",
      includeDeleted: true,
      allocated: false,
      level: 2,
    });

    expect(all).toEqual(results);
    expect(mockGetAllPagesWithCount).toHaveBeenCalledWith("/requirements/", {
      workspace_id: WORKSPACE,
      status: "approved",
      include_deleted: "true",
      allocated: "false",
      level: "2",
    });
  });

  // F3 is now covered in pagination-walkers.test.ts (the cap warning lives in
  // the central walker, shared by every listAll caller).
});
