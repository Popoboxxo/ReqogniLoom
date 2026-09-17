import { describe, expect, it } from "vitest";

import { resolveBadgeVariant } from "./statusBadge";
import {
  compareWorkflowStatus,
  getWorkflowStatusLabel,
} from "./workflowStatus";

describe("proposed status vocabulary", () => {
  it("sorts before every other lifecycle state", () => {
    expect(compareWorkflowStatus("proposed", "draft")).toBeLessThan(0);
    expect(compareWorkflowStatus("proposed", "approved")).toBeLessThan(0);
  });

  it("renders a readable label", () => {
    expect(getWorkflowStatusLabel("proposed")).toBe("Proposed");
  });

  it("uses the info badge variant", () => {
    expect(resolveBadgeVariant("proposed")).toBe("info");
  });

  it("keeps rejected on the danger variant", () => {
    expect(resolveBadgeVariant("rejected")).toBe("danger");
  });
});
