/**
 * Unit tests for artifact route resolution (DATA-08, audit findings 181/189).
 *
 * Residual TestCase artifacts still carry a legacy `"TestCase:<Type>"`
 * artifact_type. Those must resolve to the TestCase editor instead of falling
 * through to the generic `/requirements` fallback, while every existing route
 * keeps working.
 */
import { describe, it, expect } from "vitest";
import { ARTIFACT_ROUTE_MAP, getArtifactRoute } from "./artifactRoutes";

const id = "3f9c1b2a-0000-0000-0000-000000000001";

describe("artifactRoutes", () => {
  describe("legacy TestCase sub-type tags", () => {
    it.each([
      "TestCase:Unit",
      "TestCase:System",
      "TestCase:Integration",
      "TestCase:Inspection",
      "TestCase:Analysis",
      "TestCase:Demonstration",
    ])("maps %s to the TestCase editor", (entityType) => {
      expect(getArtifactRoute(entityType, id)).toBe(`/testcases/${id}`);
    });

    it("registers the residual tags in ARTIFACT_ROUTE_MAP for map consumers", () => {
      expect(ARTIFACT_ROUTE_MAP["TestCase:Unit"]).toBe("/testcases");
      expect(ARTIFACT_ROUTE_MAP["TestCase:System"]).toBe("/testcases");
    });

    it("defensively routes any residual case variant to /testcases", () => {
      expect(getArtifactRoute("TestCase:unit", id)).toBe(`/testcases/${id}`);
      expect(getArtifactRoute("TestCase:SomeFutureType", id)).toBe(
        `/testcases/${id}`
      );
    });
  });

  describe("existing routes keep working", () => {
    it.each([
      ["Requirement", "/requirements"],
      ["requirement", "/requirements"],
      ["ArchitectureElement", "/architecture"],
      ["ArchitectureElement", "/architecture"],
      ["architecture", "/architecture"],
      ["TestCase", "/testcases"],
      ["test_case", "/testcases"],
      ["testCase", "/testcases"],
      ["StakeholderNeed", "/needs"],
      ["stakeholder_need", "/needs"],
      ["Adr", "/adrs"],
      ["adr", "/adrs"],
      ["Risk", "/risks"],
      ["Issue", "/issues"],
      ["Goal", "/goals"],
      ["MainGoal", "/goals"],
    ])("maps %s to %s", (entityType, prefix) => {
      expect(getArtifactRoute(entityType, id)).toBe(`${prefix}/${id}`);
    });

    it("falls back to /requirements for unknown types", () => {
      expect(getArtifactRoute("SomethingElse", id)).toBe(`/requirements/${id}`);
    });
  });
});
