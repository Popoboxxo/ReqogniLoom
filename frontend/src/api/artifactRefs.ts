/**
 * ARCH-L1-001 ReactFrontend — generic artifact reference resolution.
 *
 * leaf_id: COMP-RF-003 (RequirementEditors), COMP-RF-004 (ArchitectureEditors)
 * req_id:  REQ-L2-RF-006 (Traceability-Anzeige), REQ-L1-003 (Traceability-Engine)
 *
 * TraceLinks connect Requirement, ArchitectureElement, TestCase and ADR
 * artifacts (the Artifact-backed entity types — see backend persistence and
 * application models; ADR backing added in REQ-L2-TE-020).
 * Resolves a linked artifact's display title and route generically instead of
 * assuming every trace target is a Requirement.
 */

import { artifactsApi } from "./artifacts";
import { requirementsApi } from "./requirements";
import { architectureApi } from "./architecture";
import { testcasesApi } from "./testcases";
import { adrsApi } from "./adrs";
import type { UUID } from "../types";

export interface ArtifactRef {
  title: string;
  route: string;
}

const ROUTE_BASE_BY_TYPE: Record<string, string> = {
  Requirement: "/requirements",
  ArchitectureElement: "/architecture",
  TestCase: "/testcases",
  Adr: "/adrs",
};

function fallbackRef(id: UUID): ArtifactRef {
  // UI-05: a lookup failure or an unmapped artifact_type must not fake a
  // Requirement route — that silently sent users to the wrong artifact
  // (the target route "changed" depending on whether the lookup happened
  // to succeed or fail). An empty route marks the ref as "not resolvable";
  // callers (TraceLinkPanel, TraceabilityPanel) already render/must render
  // a plain, non-navigable label instead of a clickable link for it.
  return { title: `(${id.slice(0, 8)}…)`, route: "" };
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
      case "Adr": {
        const adr = await adrsApi.get(id);
        return { title: adr.title || "(untitled)", route: `${routeBase}/${id}` };
      }
      default:
        return fallbackRef(id);
    }
  } catch {
    return fallbackRef(id);
  }
}
