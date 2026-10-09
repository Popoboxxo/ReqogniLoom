/**
 * REQ-L2-AI-001 / REQ-L2-AI-002 — Co-located tests for the Stakeholder Need
 * AI derivation wrappers.
 *
 * `deriveRequirements` must hit the synchronous Draft/Accept endpoint
 * (`/needs/{id}/derive-requirements/`) which returns proposed system
 * requirements — NOT the fire-and-forget async task endpoint
 * (`/needs/{id}/derive/`), whose Celery result is never persisted and never
 * read back by the client.
 *
 * `acceptDerivedRequirements` is the issue #1095 half: the persist step runs
 * server-side, so the client must NOT fall back to `requirementsApi.create` +
 * a hand-built TraceLink. That call is what seeded `draft` instead of
 * `proposed` and kept the accepted drafts out of the pending-review queue
 * (#1089). These assertions pin the URL and the body shape (only `drafts` is
 * an accepted top-level key) so a drift back to a client-side persist surfaces
 * here first.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { stakeholderNeedApi } from "./stakeholder-need";

const mockPost = vi.fn();

vi.mock("./client", () => ({
  apiClient: {
    get: vi.fn(),
    post: (...a: unknown[]) => mockPost(...a),
    patch: vi.fn(),
    delete: vi.fn(),
  },
  getAllPages: vi.fn(),
  extractErrorMessage: (err: unknown) => String(err),
}));

const NEED = "22222222-2222-2222-2222-222222222222";

describe("stakeholderNeedApi.deriveRequirements", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("POSTs to the Draft/Accept endpoint and returns the drafts", async () => {
    mockPost.mockResolvedValue({
      drafts: [
        {
          title: "SysReq A",
          description: "Beschreibung A",
          rationale: "weil",
          suggested_parent_id: NEED,
        },
      ],
    });

    const res = await stakeholderNeedApi.deriveRequirements(NEED);

    expect(mockPost).toHaveBeenCalledWith(
      `/needs/${NEED}/derive-requirements/`,
      { n: 3 }
    );
    expect(res.drafts).toHaveLength(1);
    expect(res.drafts[0].title).toBe("SysReq A");
  });

  it("forwards an explicit draft count", async () => {
    mockPost.mockResolvedValue({ drafts: [] });

    await stakeholderNeedApi.deriveRequirements(NEED, 5);

    expect(mockPost).toHaveBeenCalledWith(
      `/needs/${NEED}/derive-requirements/`,
      { n: 5 }
    );
  });

  it("keeps the async task endpoint available under derive()", async () => {
    mockPost.mockResolvedValue({ task_id: "task-1", message: "ok" });

    const res = await stakeholderNeedApi.derive(NEED);

    expect(mockPost).toHaveBeenCalledWith(`/needs/${NEED}/derive/`, {});
    expect(res.task_id).toBe("task-1");
  });
});

describe("stakeholderNeedApi.acceptDerivedRequirements (#1095)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("POSTs the accepted drafts to the server-side persist endpoint", async () => {
    mockPost.mockResolvedValue({
      count: 1,
      created: [],
      proposal: {},
    });

    const drafts = [
      { title: "SysReq A", description: "Beschreibung A", rationale: "weil A" },
      { title: "SysReq B" },
    ];
    const res = await stakeholderNeedApi.acceptDerivedRequirements(NEED, drafts);

    expect(mockPost).toHaveBeenCalledWith(
      `/needs/${NEED}/derive-requirements/accept/`,
      { drafts }
    );
    // The wrapper adds nothing of its own to the body: `drafts` is the only
    // accepted top-level key, so a client-set `status`/`from_ai` would be a 400.
    expect(mockPost.mock.calls[0][1]).toEqual({ drafts });
    expect(res.count).toBe(1);
  });

  it("accepts an empty drafts body (the server is the validation authority)", async () => {
    mockPost.mockResolvedValue({ count: 0, created: [], proposal: {} });

    await stakeholderNeedApi.acceptDerivedRequirements(NEED, []);

    expect(mockPost).toHaveBeenCalledWith(
      `/needs/${NEED}/derive-requirements/accept/`,
      { drafts: [] }
    );
  });
});
