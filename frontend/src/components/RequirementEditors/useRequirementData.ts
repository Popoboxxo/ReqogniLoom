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

  // Effect 1: Load the list (sidebar)
  useEffect(() => {
    if (!activeWorkspace) return;
    let cancelled = false;

    async function loadList(): Promise<void> {
      if (!activeWorkspace) return;
      try {
        const all = await requirementsApi.listAll(activeWorkspace.id);
        if (cancelled) return;
        setRequirements(all);
      } catch {
        // list errors are non-fatal — detail effect handles its own errors
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    }

    setIsLoading(true);
    void loadList();
    return () => { cancelled = true; };
  }, [activeWorkspace, selectedId, tick]);

  // Effect 2: Load the selected requirement detail + tracelinks (independent of list)
  useEffect(() => {
    if (!activeWorkspace || !selectedId) {
      setRequirement(null);
      setUpstreamLinks([]);
      setDownstreamLinks([]);
      return;
    }

    let cancelled = false;

    async function loadDetail(): Promise<void> {
      if (!activeWorkspace || !selectedId) return;
      try {
        const req = await requirementsApi.get(selectedId);
        if (cancelled) return;
        setRequirement(req);

        const links = await tracelinksApi.listForArtifact(activeWorkspace.id, req.id);
        if (cancelled) return;
        setUpstreamLinks(links.results.filter((l) => l.target_id === req.id));
        setDownstreamLinks(links.results.filter((l) => l.source_id === req.id));
      } catch (err: unknown) {
        if (cancelled) return;
        const msg =
          (err as { error?: { message?: string } })?.error?.message ??
          String(err);
        setError(msg);
        setRequirement(null);
      }
    }

    void loadDetail();
    return () => { cancelled = true; };
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
