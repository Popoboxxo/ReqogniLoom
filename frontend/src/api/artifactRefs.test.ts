/**
 * Co-located tests for artifactRefs (resolveArtifactRef / fallbackRef).
 *
 * req_id: REQ-L2-RF-006 (Traceability-Anzeige), REQ-L1-003 (Traceability-Engine)
 *
 * UI-05: a lookup failure or an unmapped artifact_type must not fake a
 * Requirement route. These tests pin the fallback contract: the returned
 * route is always the empty string ("not resolvable"), never a guessed
 * `/requirements/{id}` path — regardless of whether the failure was an
 * unknown artifact_type or a rejected lookup call.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { resolveArtifactRef } from "./artifactRefs";

const mockArtifactsGet = vi.fn();
const mockRequirementsGet = vi.fn();
const mockArchitectureGet = vi.fn();
const mockTestcasesGet = vi.fn();
const mockAdrsGet = vi.fn();

vi.mock("./artifacts", () => ({
  artifactsApi: { get: (...a: unknown[]) => mockArtifactsGet(...a) },
}));
vi.mock("./requirements", () => ({
  requirementsApi: { get: (...a: unknown[]) => mockRequirementsGet(...a) },
}));
vi.mock("./architecture", () => ({
  architectureApi: { get: (...a: unknown[]) => mockArchitectureGet(...a) },
}));
vi.mock("./testcases", () => ({
  testcasesApi: { get: (...a: unknown[]) => mockTestcasesGet(...a) },
}));
vi.mock("./adrs", () => ({
  adrsApi: { get: (...a: unknown[]) => mockAdrsGet(...a) },
}));

const ID = "aaaaaaaa-1111-2222-3333-444444444444";

describe("resolveArtifactRef", () => {
  beforeEach(() => vi.clearAllMocks());

  it("resolves a Requirement to its real route", async () => {
    mockArtifactsGet.mockResolvedValue({ artifact_type: "Requirement" });
    mockRequirementsGet.mockResolvedValue({ title: "REQ Title" });

    const ref = await resolveArtifactRef(ID);

    expect(ref).toEqual({ title: "REQ Title", route: `/requirements/${ID}` });
  });

  it("resolves an ArchitectureElement to its real route", async () => {
    mockArtifactsGet.mockResolvedValue({ artifact_type: "ArchitectureElement" });
    mockArchitectureGet.mockResolvedValue({ title: "Arch Title" });

    const ref = await resolveArtifactRef(ID);

    expect(ref).toEqual({ title: "Arch Title", route: `/architecture/${ID}` });
  });

  it("[UI-05] does not fake a Requirement route for an unknown artifact_type", async () => {
    mockArtifactsGet.mockResolvedValue({ artifact_type: "SomeFutureType" });

    const ref = await resolveArtifactRef(ID);

    expect(ref.route).toBe("");
    expect(ref.route).not.toBe(`/requirements/${ID}`);
    expect(mockRequirementsGet).not.toHaveBeenCalled();
  });

  it("[UI-05] does not fake a Requirement route when the artifact lookup rejects", async () => {
    mockArtifactsGet.mockRejectedValue(new Error("404 not found"));

    const ref = await resolveArtifactRef(ID);

    expect(ref.route).toBe("");
    expect(ref.route).not.toBe(`/requirements/${ID}`);
  });

  it("[UI-05] does not fake a Requirement route when the entity-detail lookup rejects", async () => {
    mockArtifactsGet.mockResolvedValue({ artifact_type: "TestCase" });
    mockTestcasesGet.mockRejectedValue(new Error("network error"));

    const ref = await resolveArtifactRef(ID);

    expect(ref.route).toBe("");
    expect(ref.route).not.toBe(`/requirements/${ID}`);
  });

  it("[UI-05] the unresolved fallback never throws and yields a stable, id-derived title", async () => {
    mockArtifactsGet.mockRejectedValue(new Error("boom"));

    const ref = await resolveArtifactRef(ID);

    expect(ref.title).toContain(ID.slice(0, 8));
  });
});
