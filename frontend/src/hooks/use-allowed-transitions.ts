import { useEffect, useState } from "react";

import {
  workflowTransitionsApi,
  type WorkflowAllowedTransition,
  type WorkflowArtifactType,
} from "../api/workflow-transitions";

export function useAllowedTransitions(
  artifactType: WorkflowArtifactType | undefined,
  artifactId: string | null,
): WorkflowAllowedTransition[] {
  const [transitions, setTransitions] = useState<WorkflowAllowedTransition[]>([]);

  useEffect(() => {
    if (!artifactType || !artifactId) {
      setTransitions([]);
      return;
    }
    let cancelled = false;
    const load = async (): Promise<void> => {
      try {
        const response = await workflowTransitionsApi.getTransitions(
          artifactType,
          artifactId,
        );
        if (!cancelled) setTransitions(response?.allowed_transitions ?? []);
      } catch {
        if (!cancelled) setTransitions([]);
      }
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, [artifactType, artifactId]);

  return transitions;
}
