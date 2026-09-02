/**
 * Co-located tests for artifactRefs (resolveArtifactRef / resolveArtifactRefs).
 *
 * req_id: REQ-L2-RF-006 (Traceability-Anzeige), REQ-L1-003 (Traceability-Engine)
 *
 * #414 — the two id spaces. A TraceLink endpoint id is an **Artifact** id;
 * `/api/v1/requirements/<id>/` and the `/requirements/<id>` SPA route take the
 * **domain-entity** id. These are different UUIDs for the same object, so
 * passing the Artifact id to either produced a 404 on an artifact that exists.
 * The tests below pin that the detail call and the route are both built from
 * the *entity* id returned by `GET /api/v1/traceability/resolve/`, and that the
 * Artifact id is never used as an entity id.
 *
 * UI-05: a lookup failure or an unmapped artifact_type must not fake a
 * Requirement route. The fallback contract stays: route is the empty string
 * ("not resolvable"), never a guessed `/requirements/{id}` path.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { resolveArtifactRefs } from "./artifactRefs";

const mockResolve = vi.fn();
const mockRequirementsGet = vi.fn();
const mockArchitectureGet = vi.fn();
const mockTestcasesGet = vi.fn();
const mockAdrsGet = vi.fn();

vi.mock("./traceability", () => ({
  traceabilityApi: { resolve: (...a: unknown[]) => mockResolve(...a) },
  // artifactRefs chunks its batches by this constant; vitest raises on a
  // missing export from a mocked module, so it has to be declared here.
  RESOLVE_BATCH_LIMIT: 200,
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

/** Artifact id — what a TraceLink endpoint carries. */
const ARTIFACT_ID = "55fa608c-721f-4134-8143-5a319c2a41d1";
/** Entity id — what the detail endpoint and the editor route expect. */
const ENTITY_ID = "5541df0a-1111-2222-3333-444444444444";

function resolvesTo(entityType: string, entityId = ENTITY_ID) {
  mockResolve.mockResolvedValue([
    {
      artifact_id: ARTIFACT_ID,
      resolved: true,
      entity_type: entityType,
      entity_id: entityId,
    },
  ]);
}

describe("resolveArtifactRefs (batch)", () => {
  beforeEach(() => vi.clearAllMocks());

  it("[#414] resolves the whole set in one request, not one per id", async () => {
    const second = "66fa608c-721f-4134-8143-5a319c2a41d2";
    mockResolve.mockResolvedValue([
      {
        artifact_id: ARTIFACT_ID,
        resolved: true,
        entity_type: "Requirement",
        entity_id: ENTITY_ID,
      },
      {
        artifact_id: second,
        resolved: true,
        entity_type: "TestCase",
        entity_id: "77000000-0000-0000-0000-000000000001",
      },
    ]);
    mockRequirementsGet.mockResolvedValue({ title: "R" });
    mockTestcasesGet.mockResolvedValue({ title: "T" });

    const refs = await resolveArtifactRefs([ARTIFACT_ID, second]);

    expect(mockResolve).toHaveBeenCalledTimes(1);
    expect(refs[ARTIFACT_ID].route).toBe(`/requirements/${ENTITY_ID}`);
    expect(refs[second].route).toBe(
      "/testcases/77000000-0000-0000-0000-000000000001"
    );
  });

  it("returns a non-navigable entry for every id the backend omits", async () => {
    mockResolve.mockResolvedValue([]);

    const refs = await resolveArtifactRefs([ARTIFACT_ID]);

    expect(refs[ARTIFACT_ID]).toEqual({
      title: `(${ARTIFACT_ID.slice(0, 8)}…)`,
      route: "",
    });
  });

  it("makes no request for an empty id set", async () => {
    const refs = await resolveArtifactRefs([]);

    expect(refs).toEqual({});
    expect(mockResolve).not.toHaveBeenCalled();
  });

  it("de-duplicates repeated ids into a single request entry", async () => {
    resolvesTo("Requirement");
    mockRequirementsGet.mockResolvedValue({ title: "R" });

    await resolveArtifactRefs([ARTIFACT_ID, ARTIFACT_ID, ARTIFACT_ID]);

    expect(mockResolve).toHaveBeenCalledWith([ARTIFACT_ID]);
  });
});

