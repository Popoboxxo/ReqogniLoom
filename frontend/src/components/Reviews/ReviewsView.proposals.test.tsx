import { describe, expect, it, vi } from "vitest";

import { pendingStateFor } from "./useReviewsData";
import { bulkConfirm } from "./ReviewsView";

describe("proposals queue mode", () => {
  it("queries the proposed state in proposals mode", () => {
    expect(pendingStateFor("requirement", "proposals")).toBe("proposed");
    expect(pendingStateFor("goal", "proposals")).toBe("proposed");
  });

  it("keeps the historical review states in review mode", () => {
    expect(pendingStateFor("requirement", "review")).toBe("in_review");
    expect(pendingStateFor("goal", "review")).toBe("Entwurf");
  });

  it("defaults to review mode", () => {
    expect(pendingStateFor("requirement")).toBe("in_review");
  });
});

describe("bulkConfirm", () => {
  it("confirms every selected id", async () => {
    const fn = vi.fn().mockResolvedValue(undefined);
    const result = await bulkConfirm(["a", "b", "c"], fn);
    expect(fn).toHaveBeenCalledTimes(3);
    expect(result.confirmed).toEqual(["a", "b", "c"]);
    expect(result.failed).toEqual([]);
  });

  it("keeps going after a failure and reports it", async () => {
    const fn = vi
      .fn()
      .mockResolvedValueOnce(undefined)
      .mockRejectedValueOnce(new Error("409"))
      .mockResolvedValueOnce(undefined);
    const result = await bulkConfirm(["a", "b", "c"], fn);
    expect(fn).toHaveBeenCalledTimes(3);
    expect(result.confirmed).toEqual(["a", "c"]);
    expect(result.failed).toEqual(["b"]);
  });

  it("is a no-op for an empty selection", async () => {
    const fn = vi.fn();
    const result = await bulkConfirm([], fn);
    expect(fn).not.toHaveBeenCalled();
    expect(result).toEqual({ confirmed: [], failed: [] });
  });
});
