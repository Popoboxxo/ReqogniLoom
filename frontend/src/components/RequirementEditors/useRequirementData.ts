/**
 * ARCH-L1-001 ReactFrontend — Requirement Data Hook.
 *
 * leaf_id: COMP-RF-003 (RequirementEditors)
 * req_id:  REQ-L3-RF003-001 (Inline-Editing),
 *          REQ-L3-RF003-004 (Editor-Performance < 500ms)
 */

import { useState, useEffect } from "react";
import { requirementsApi } from "../../api/requirements";
import { tracelinksApi } from "../../api/tracelinks";
import type { Requirement, TraceLink } from "../../types";
import { useWorkspace } from "../../context/WorkspaceContext";

export interface RequirementData {
  requirements: Requirement[];
  requirement: Requirement | null;
  upstreamLinks: TraceLink[];
  downstreamLinks: TraceLink[];
  isLoading: boolean;
  error: string | null;
  refresh: () => void;
}

export function useRequirementData(selectedId?: string): RequirementData {
  const { activeWorkspace } = useWorkspace();
  const [requirements, setRequirements] = useState<Requirement[]>([]);
  const [requirement, setRequirement] = useState<Requirement | null>(null);
  const [upstreamLinks, setUpstreamLinks] = useState<TraceLink[]>([]);
  const [downstreamLinks, setDownstreamLinks] = useState<TraceLink[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  const refresh = (): void => setTick((t) => t + 1);

  useEffect(() => {
    if (!activeWorkspace) return;

    let cancelled = false;
    setIsLoading(true);
    setError(null);

    async function load(): Promise<void> {
      if (!activeWorkspace) return;
      try {
        const resp = await requirementsApi.list(activeWorkspace.id);
        if (cancelled) return;
        setRequirements(resp.results);

        if (selectedId) {
          let req: Requirement | null = null;
          try {
            req = await requirementsApi.get(selectedId);
          } catch {
            req = null;
          }
          setRequirement(req);

          if (req) {
            // Load tracelinks for this requirement
            const links = await tracelinksApi.listForArtifact(
              activeWorkspace.id,
              req.id
            );
            if (cancelled) return;
            // Partition into upstream (target = req) and downstream (source = req)
            setUpstreamLinks(
              links.results.filter((l) => l.target_id === req.id)
            );
            setDownstreamLinks(
              links.results.filter((l) => l.source_id === req.id)
            );
          }
        }
      } catch (err: unknown) {
        if (cancelled) return;
        const msg =
          (err as { error?: { message?: string } })?.error?.message ??
          String(err);
        setError(msg);
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, [activeWorkspace, selectedId, tick]);

  return {
    requirements,
    requirement,
    upstreamLinks,
    downstreamLinks,
    isLoading,
    error,
    refresh,
  };
}
