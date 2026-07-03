/**
 * ARCH-L1-001 ReactFrontend — generic artifact reference resolution.
 *
 * leaf_id: COMP-RF-003 (RequirementEditors), COMP-RF-004 (ArchitectureEditors)
 * req_id:  REQ-L2-RF-006 (Traceability-Anzeige), REQ-L1-003 (Traceability-Engine)
 *
 * TraceLinks connect Requirement, ArchitectureElement and TestCase artifacts
 * (the three Artifact-backed entity types — see backend/persistence/models.py).
 * Resolves a linked artifact's display title and route generically instead of
 * assuming every trace target is a Requirement.
 */

import { artifactsApi } from "./artifacts";
import { requirementsApi } from "./requirements";
import { architectureApi } from "./architecture";
import { testcasesApi } from "./testcases";
import type { UUID } from "../types";

export interface ArtifactRef {
  title: string;
  route: string;
}

const ROUTE_BASE_BY_TYPE: Record<string, string> = {
  Requirement: "/requirements",
  ArchitectureElement: "/architecture",
  TestCase: "/testcases",
};

function fallbackRef(id: UUID): ArtifactRef {
  return { title: `(${id.slice(0, 8)}…)`, route: `/requirements/${id}` };
}

/** Resolves title + route for an arbitrary linked artifact id. Never throws. */
export async function resolveArtifactRef(id: UUID): Promise<ArtifactRef> {
  try {
    const artifact = await artifactsApi.get(id);
    const routeBase = ROUTE_BASE_BY_TYPE[artifact.artifact_type];
    if (!routeBase) return fallbackRef(id);

    switch (artifact.artifact_type) {
      case "Requirement": {
        const r = await requirementsApi.get(id);
        return { title: r.title || "(untitled)", route: `${routeBase}/${id}` };
      }
      case "ArchitectureElement": {
        const a = await architectureApi.get(id);
        return { title: a.title || "(untitled)", route: `${routeBase}/${id}` };
      }
      case "TestCase": {
        const tc = await testcasesApi.get(id);
        return { title: tc.title || "(untitled)", route: `${routeBase}/${id}` };
      }
      default:
        return fallbackRef(id);
    }
  } catch {
    return fallbackRef(id);
  }
}
