/**
 * Plan B B6-T2 (#879) — Milestone API wire contract.
 *
 * The backend emits `ETag: "<version>"` and refuses a stale `If-Match` with
 * 412. A silently dropped header would look like a successful save while the
 * concurrent edit is overwritten, so this pins the exact header format and the
 * `expected_version` body field of the two domain actions.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";

const mockGetList = vi.fn();
const mockPost = vi.fn();
const mockPatch = vi.fn();

vi.mock("./client", () => ({
  apiClient: {
    get: vi.fn(),
    post: (...args: unknown[]) => mockPost(...args),
    patch: (...args: unknown[]) => mockPatch(...args),
    delete: vi.fn(),
  },
  getList: (...args: unknown[]) => mockGetList(...args),
}));

import { milestonesApi } from "./milestones";

const MILESTONE = "33333333-3333-3333-3333-333333333333";
const BASELINE = "44444444-4444-4444-4444-444444444444";

describe("milestonesApi (Plan B B6-T2)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetList.mockResolvedValue({
      count: 0,
      next: null,
      previous: null,
      results: [],
    });
    mockPost.mockResolvedValue({ id: MILESTONE });
    mockPatch.mockResolvedValue({ id: MILESTONE });
  });

  it("lists milestones for one workspace", async () => {
    await milestonesApi.list({ workspace_id: "ws-1" });

    expect(mockGetList).toHaveBeenCalledWith("/milestones/", {
      workspace_id: "ws-1",
    });
  });

  it("sends If-Match with the last-read version on update", async () => {
    await milestonesApi.update(MILESTONE, { name: "CDR" }, 7);

    const [path, body, , headers] = mockPatch.mock.calls[0];
    expect(path).toBe(`/milestones/${MILESTONE}/`);
    expect(body).toEqual({ name: "CDR" });
    expect(headers).toEqual({ "If-Match": '"7"' });
  });

  it("sends no If-Match when no version is supplied", async () => {
    await milestonesApi.update(MILESTONE, { name: "CDR" });

    const [, , , headers] = mockPatch.mock.calls[0];
    expect(headers).toBeUndefined();
  });

  it("guards bind-baseline with the entity version in the body", async () => {
    await milestonesApi.bindBaseline(MILESTONE, BASELINE, 4);

    expect(mockPost).toHaveBeenCalledWith(
      `/milestones/${MILESTONE}/bind-baseline/`,
      { baseline_id: BASELINE, expected_version: 4 }
    );
  });

  it("guards record-audit with the entity version in the body", async () => {
    await milestonesApi.recordAudit(MILESTONE, 5);

    expect(mockPost).toHaveBeenCalledWith(
      `/milestones/${MILESTONE}/record-audit/`,
      { expected_version: 5 }
    );
  });
});
