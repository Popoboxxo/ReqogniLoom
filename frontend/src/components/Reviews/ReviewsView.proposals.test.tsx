import { describe, expect, it } from "vitest";

import { pendingStateFor } from "./useReviewsData";

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
