/**
 * Issue #1193 — unit tests for the reviews aggregate API wrapper.
 *
 * Verifies the wrapper consumes the *existing* backend route
 * (``GET /api/v1/reviews/``) rather than inventing one, forwards the artifact
 * type as the backend's CamelCase ``item_type``, and returns the pagination
 * envelope's ``count`` (the aggregate the Reviews UI was missing).
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { reviewsApi, REVIEW_ITEM_TYPE } from "./reviews";

const mockGetList = vi.fn();

vi.mock("./client", () => ({
  getList: (...args: unknown[]) => mockGetList(...args),
}));

describe("reviewsApi.listPendingCount (#1193)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetList.mockResolvedValue({
      count: 68,
      next: null,
      previous: null,
      results: [],
    });
  });

  it("asks the collection root for the workspace-wide total", async () => {
    const count = await reviewsApi.listPendingCount("ws-1");

    expect(count).toBe(68);
    expect(mockGetList).toHaveBeenCalledWith("/reviews/", {
      workspace_id: "ws-1",
      page_size: "1",
    });
  });

  it("narrows the count with the backend's CamelCase item_type", async () => {
    await reviewsApi.listPendingCount("ws-1", "test-case");

    expect(mockGetList).toHaveBeenCalledWith("/reviews/", {
      workspace_id: "ws-1",
      page_size: "1",
      item_type: "TestCase",
    });
  });

  it("maps every UI artifact type to a backend WorkflowItemState item_type", () => {
    expect(REVIEW_ITEM_TYPE).toEqual({
      requirement: "Requirement",
      need: "StakeholderNeed",
      adr: "Adr",
      "test-case": "TestCase",
      risk: "Risk",
      issue: "Issue",
      architecture: "ArchitectureElement",
      icd: "Icd",
      glossary: "GlossaryTerm",
      diagram: "Diagram",
      goal: "Goal",
      "main-goal": "MainGoal",
    });
  });
});
