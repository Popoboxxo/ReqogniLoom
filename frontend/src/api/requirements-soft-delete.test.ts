/**
 * GH-443 — the requirements API must be able to ask for soft-deleted records.
 *
 * DELETE is a soft-delete: the requirement survives with `status: "outdated"`
 * and the list endpoint hides it by default. Without an explicit opt-in a
 * deleted requirement is unreachable from the UI, and the list's status filter
 * — whose options are derived from the loaded items — can never offer
 * "outdated" at all. These tests pin the wire format of that opt-in, since a
 * silently dropped query parameter looks exactly like "there are no deleted
 * requirements".
 */

import { describe, it, expect, vi, beforeEach } from "vitest";

const mockGetList = vi.fn();
const mockPost = vi.fn();

vi.mock("./client", () => ({
  apiClient: {
    get: vi.fn(),
    post: (...a: unknown[]) => mockPost(...a),
    patch: vi.fn(),
    delete: vi.fn(),
  },
  getList: (...a: unknown[]) => mockGetList(...a),
  extractErrorMessage: (err: unknown) => String(err),
}));

import { requirementsApi } from "./requirements";

const WORKSPACE = "11111111-1111-1111-1111-111111111111";
const REQUIREMENT = "22222222-2222-2222-2222-222222222222";

function emptyPage() {
  return { results: [], count: 0, next: null, previous: null };
}

describe("requirementsApi soft-delete visibility (GH-443)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetList.mockResolvedValue(emptyPage());
  });

  it("omits include_deleted by default so deleted items stay hidden", async () => {
    await requirementsApi.list(WORKSPACE);

    const [, params] = mockGetList.mock.calls[0];
    expect(params).not.toHaveProperty("include_deleted");
  });

  it("sends include_deleted=true when asked", async () => {
    await requirementsApi.list(WORKSPACE, undefined, { includeDeleted: true });

    const [path, params] = mockGetList.mock.calls[0];
    expect(path).toBe("/requirements/");
    expect(params).toMatchObject({
      workspace_id: WORKSPACE,
      include_deleted: "true",
    });
  });

  it("does not send include_deleted when the flag is explicitly false", async () => {
    await requirementsApi.list(WORKSPACE, undefined, { includeDeleted: false });

    const [, params] = mockGetList.mock.calls[0];
    expect(params).not.toHaveProperty("include_deleted");
  });

  it("keeps the status filter usable alongside the flag", async () => {
    await requirementsApi.list(WORKSPACE, "outdated");

    const [, params] = mockGetList.mock.calls[0];
    // `status=outdated` implies include_deleted server-side, so the client does
    // not have to send both — but it must still send the status itself.
    expect(params).toMatchObject({ status: "outdated" });
  });

  it("threads the flag through listAll, which is what the list view uses", async () => {
    await requirementsApi.listAll(WORKSPACE, { includeDeleted: true });

    const [, params] = mockGetList.mock.calls[0];
    expect(params).toMatchObject({
      workspace_id: WORKSPACE,
      page_size: "100",
      include_deleted: "true",
    });
  });

  it("listAll omits the flag by default", async () => {
    await requirementsApi.listAll(WORKSPACE);

    const [, params] = mockGetList.mock.calls[0];
    expect(params).not.toHaveProperty("include_deleted");
  });

  it("exposes reactivate as the documented way back from a soft-delete", async () => {
    mockPost.mockResolvedValue({
      id: REQUIREMENT,
      previous_state: "outdated",
      new_state: "draft",
    });

    const result = await requirementsApi.reactivate(REQUIREMENT);

    expect(mockPost).toHaveBeenCalledWith(
      `/requirements/${REQUIREMENT}/reactivate/`,
      {},
    );
    expect(result.new_state).toBe("draft");
  });
});
