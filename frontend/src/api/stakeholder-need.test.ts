/**
 * REQ-L2-AI-001 / REQ-L2-AI-002 — Co-located tests for the Stakeholder Need
 * AI derivation wrappers.
 *
 * `deriveRequirements` must hit the synchronous Draft/Accept endpoint
 * (`/needs/{id}/derive-requirements/`) which returns proposed system
 * requirements — NOT the fire-and-forget async task endpoint
 * (`/needs/{id}/derive/`), whose Celery result is never persisted and never
 * read back by the client.
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
