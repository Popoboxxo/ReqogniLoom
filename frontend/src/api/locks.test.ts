/**
 * P4.4 — wire contract of the batch workflow-lock read.
 *
 * The two trees pass the ids their nodes already carry, so the only thing that
 * can silently break here is the `type` query parameter (a wrong or missing
 * value is a 400 server-side). These tests pin the route, the query parameter
 * and the unwrapping of the `{locks: {...}}` envelope.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";

const mockGet = vi.fn();

vi.mock("./client", () => ({
  apiClient: {
    get: (...args: unknown[]) => mockGet(...args),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
  getList: vi.fn(),
}));

import { fetchLocks, locksApi } from "./locks";

const WORKSPACE = "11111111-1111-1111-1111-111111111111";
const REQ = "22222222-2222-2222-2222-222222222222";

describe("locksApi (P4.4)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("reads the workspace-scoped locks route with the requirement type", async () => {
    mockGet.mockResolvedValue({ locks: { [REQ]: "frozen" } });

    await fetchLocks(WORKSPACE, "requirement");

    expect(mockGet).toHaveBeenCalledWith(
      `/workspaces/${WORKSPACE}/locks/?type=requirement`,
    );
  });

  it("reads the same route with the architecture type", async () => {
    mockGet.mockResolvedValue({ locks: {} });

    await locksApi.list(WORKSPACE, "architecture");

    expect(mockGet).toHaveBeenCalledWith(
      `/workspaces/${WORKSPACE}/locks/?type=architecture`,
    );
  });

  it("returns the id → state-name map verbatim", async () => {
    mockGet.mockResolvedValue({ locks: { [REQ]: "Freigegeben" } });

    await expect(fetchLocks(WORKSPACE, "requirement")).resolves.toEqual({
      [REQ]: "Freigegeben",
    });
  });

  it("treats a missing locks envelope as 'nothing is locked'", async () => {
    mockGet.mockResolvedValue({});

    await expect(fetchLocks(WORKSPACE, "requirement")).resolves.toEqual({});
  });

  it("propagates a rejected read so the caller can degrade deliberately", async () => {
    mockGet.mockRejectedValue(new Error("boom"));

    await expect(fetchLocks(WORKSPACE, "requirement")).rejects.toThrow("boom");
  });
});
