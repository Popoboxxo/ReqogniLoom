/**
 * B1 — the review queue only ever saw the backend's first page.
 *
 * ``GET /api/v1/requirements/?status=in_review`` answers the standard DRF
 * pagination envelope with ``PAGE_SIZE=25`` (settings.py) and ``page_size``
 * capped at 100. ``requirementsApi.list()`` used to issue exactly one request
 * and hand back that single page, so a workspace with 28 ``in_review``
 * requirements silently hid the newest three from the reviewer — the item was
 * created and transitioned, yet never appeared in the queue.
 *
 * These tests pin the two halves of the fix: an adequate ``page_size`` on the
 * first request, and a walk over the paginator's ``next`` link until
 * exhaustion. They fail against the pre-fix implementation (which neither sent
 * ``page_size`` nor followed ``next``) and pass afterwards.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";

const mockGetList = vi.fn();
const mockClientGet = vi.fn();

vi.mock("./client", () => ({
  apiClient: {
    get: (...a: unknown[]) => mockClientGet(...a),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
  getList: (...a: unknown[]) => mockGetList(...a),
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

describe("requirementsApi.list full pagination (B1)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("asks for an adequate page_size and keeps the status filter", async () => {
    mockGetList.mockResolvedValue({
      count: 1,
      next: null,
      previous: null,
      results: [requirement(1)],
    });

    const resp = await requirementsApi.list(WORKSPACE, "in_review");

    expect(mockGetList).toHaveBeenCalledWith("/requirements/", {
      workspace_id: WORKSPACE,
      status: "in_review",
      page_size: "100",
    });
    expect(resp.results).toHaveLength(1);
  });

  it("follows next and returns more than a single page worth of items", async () => {
    // Page 1 carries the backend default (25) and a next link; page 2 carries
    // the three items that used to be invisible to the queue.
    const page1 = Array.from({ length: 25 }, (_, i) => requirement(i + 1));
    const page2 = Array.from({ length: 3 }, (_, i) => requirement(i + 26));

    mockGetList.mockResolvedValue({
      count: 28,
      next: "http://localhost:8001/api/v1/requirements/?page=2&page_size=100&status=in_review",
      previous: null,
      results: page1,
    });
    mockClientGet.mockResolvedValue({
      count: 28,
      next: null,
      previous: "http://localhost:8001/api/v1/requirements/?page=1&page_size=100&status=in_review",
      results: page2,
    });

    const resp = await requirementsApi.list(WORKSPACE, "in_review");

    // >25 items across pages — the assertion the pre-fix implementation fails.
    expect(resp.results).toHaveLength(28);
    expect(resp.count).toBe(28);
    // Everything has been merged, so no dangling next link remains.
    expect(resp.next).toBeNull();
    // `next` is fetched through apiClient.get with the /api/v1 prefix stripped,
    // matching how the rest of the codebase walks pagination.
    expect(mockClientGet).toHaveBeenCalledTimes(1);
    expect(mockClientGet).toHaveBeenCalledWith(
      "/requirements/?page=2&page_size=100&status=in_review"
    );
  });

  it("does not request a second page when the first page is the only one", async () => {
    mockGetList.mockResolvedValue({
      count: 2,
      next: null,
      previous: null,
      results: [requirement(1), requirement(2)],
    });

    const resp = await requirementsApi.list(WORKSPACE);

    expect(resp.results).toHaveLength(2);
    expect(mockClientGet).not.toHaveBeenCalled();
  });

  // F2: `list` used to read only its positional `status` and silently ignore
  // `options.status`, so `list(ws, undefined, { status: "in_review" })`
  // returned unfiltered results. These pin both the honor and the precedence.
  it("honors options.status when no positional status is given (F2)", async () => {
    mockGetList.mockResolvedValue({
      count: 0,
      next: null,
      previous: null,
      results: [],
    });

    await requirementsApi.list(WORKSPACE, undefined, { status: "in_review" });

    expect(mockGetList).toHaveBeenCalledWith("/requirements/", {
      workspace_id: WORKSPACE,
      status: "in_review",
      page_size: "100",
    });
  });

  it("lets the positional status win over options.status (F2)", async () => {
    mockGetList.mockResolvedValue({
      count: 0,
      next: null,
      previous: null,
      results: [],
    });

    await requirementsApi.list(WORKSPACE, "approved", { status: "in_review" });

    expect(mockGetList).toHaveBeenCalledWith("/requirements/", {
      workspace_id: WORKSPACE,
      status: "approved",
      page_size: "100",
    });
  });

  // F3: hitting the intentional 100-page cap used to exit silently. Parity with
  // client.ts::getAllPages means a truncated list is surfaced via console.warn.
  it("warns when the 100-page cap is reached (F3)", async () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    mockGetList.mockResolvedValue({
      count: 1,
      next: "/requirements/?page=2",
      previous: null,
      results: [requirement(1)],
    });
    mockClientGet.mockResolvedValue({
      count: 1,
      // Always non-null, so the walk is bounded only by the 100-page cap.
      next: "/requirements/?page=next",
      previous: null,
      results: [],
    });

    await requirementsApi.list(WORKSPACE, "in_review");

    expect(mockClientGet).toHaveBeenCalledTimes(100);
    expect(warn).toHaveBeenCalledTimes(1);
    expect(warn.mock.calls[0][0]).toContain("cap reached");
    warn.mockRestore();
  });
});
