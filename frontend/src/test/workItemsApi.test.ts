/**
 * F3-T9 — WorkItem REST wrapper contract.
 *
 * Pins the two things the UI can get wrong without a server: the document
 * scoping of the list/resume reads, and the strong `If-Match` tag on PATCH
 * (KA-F-08 — a stale version must answer 412, never a silent overwrite).
 */

import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("../api/client", () => ({
  getAllPages: vi.fn(),
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}));

import { workItemsApi } from "../api/workItems";
import { apiClient, getAllPages } from "../api/client";

const getAllPagesMock = getAllPages as ReturnType<typeof vi.fn>;
const getMock = apiClient.get as ReturnType<typeof vi.fn>;
const patchMock = apiClient.patch as ReturnType<typeof vi.fn>;
const postMock = apiClient.post as ReturnType<typeof vi.fn>;

describe("workItemsApi (F3-T9)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getAllPagesMock.mockResolvedValue([]);
    getMock.mockResolvedValue({});
    patchMock.mockResolvedValue({});
    postMock.mockResolvedValue({});
  });

  it("scopes the list to the workspace and document", async () => {
    await workItemsApi.listAll("ws-1", "doc-1", true);
    expect(getAllPagesMock).toHaveBeenCalledWith("/work-items/", {
      workspace_id: "ws-1",
      document_id: "doc-1",
      include_deleted: "true",
    });
  });

  it("omits document_id and include_deleted when not requested", async () => {
    await workItemsApi.listAll("ws-1");
    expect(getAllPagesMock).toHaveBeenCalledWith("/work-items/", {
      workspace_id: "ws-1",
    });
  });

  it("sends the item version as a strong If-Match tag", async () => {
    await workItemsApi.update("wi-1", { title: "Next" }, 7);
    expect(patchMock).toHaveBeenCalledWith(
      "/work-items/wi-1/",
      { title: "Next" },
      undefined,
      { "If-Match": '"7"' }
    );
  });

  it("builds the resume URL from workspace, document and actor", async () => {
    await workItemsApi.resume("ws-1", "doc-1", "agent:resume");
    expect(getMock).toHaveBeenCalledWith(
      "/work-items/resume/?workspace_id=ws-1&document_id=doc-1&actor=agent%3Aresume"
    );
  });

  it("forwards blocked_reason on a transition", async () => {
    await workItemsApi.transition("wi-1", "blocked", {
      blockedReason: "waiting for review",
      expectedVersion: 3,
    });
    expect(postMock).toHaveBeenCalledWith("/work-items/wi-1/transitions/", {
      target_state: "blocked",
      change_reason: "",
      credential: "",
      blocked_reason: "waiting for review",
      expected_version: 3,
    });
  });
});
