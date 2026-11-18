/**
 * Audit dashboard — scope selection (S3.2 WP-5 split by cohesion).
 *
 * Extracted verbatim from `audit-dashboard.tsx`: the project/document/global
 * scope, the document-scope artifact pick and the "first artifact is selected
 * automatically" effect. This state feeds the run query, not the finding
 * actions or the view selectors, so itowns its own module.
 */

import { useEffect, useState } from "react";
import type { Dispatch, SetStateAction } from "react";
import type { AuditScopeKind } from "../../api/audit";
import type { Artifact } from "../../types";

export interface UseAuditScopeOptions {
  /** Artifacts available for the document-scope picker. */
  artifacts: Artifact[];
}

export interface UseAuditScopeResult {
  scope: AuditScopeKind;
  setScope: Dispatch<SetStateAction<AuditScopeKind>>;
  scopeArtifactId: string;
  setScopeArtifactId: Dispatch<SetStateAction<string>>;
}

export function useAuditScope({ artifacts }: UseAuditScopeOptions): UseAuditScopeResult {
  const [scope, setScope] = useState<AuditScopeKind>("project");
  const [scopeArtifactId, setScopeArtifactId] = useState<string>("");

  // Auto-pick the first artifact when the user switches to document scope
  // without one selected yet (mirrors BaselinesView's create-form behaviour).
  useEffect(() => {
    if (scope === "document" && !scopeArtifactId && artifacts.length > 0) {
      setScopeArtifactId(artifacts[0].id);
    }
  }, [scope, scopeArtifactId, artifacts]);

  return { scope, setScope, scopeArtifactId, setScopeArtifactId };
}
