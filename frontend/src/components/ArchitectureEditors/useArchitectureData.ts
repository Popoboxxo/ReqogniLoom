/**
 * ARCH-L1-001 ReactFrontend — Architecture Data Hook.
 *
 * leaf_id: COMP-RF-004 (ArchitectureEditors)
 * req_id:  REQ-L3-RF004-001 (CRUD-Operationen),
 *          REQ-L3-RF004-003 (Verknüpfte Requirements in Seitenleiste)
 */

import { useState, useEffect } from "react";
import { architectureApi } from "../../api/architecture";
import { tracelinksApi } from "../../api/tracelinks";
import type { ArchitectureElement, TraceLink } from "../../types";
import { useWorkspace } from "../../context/WorkspaceContext";

export interface ArchitectureData {
  elements: ArchitectureElement[];
  element: ArchitectureElement | null;
  linkedTraceLinks: TraceLink[];
  isLoading: boolean;
  error: string | null;
  refresh: () => void;
}

export function useArchitectureData(selectedId?: string): ArchitectureData {
  const { activeWorkspace } = useWorkspace();
  const [elements, setElements] = useState<ArchitectureElement[]>([]);
  const [element, setElement] = useState<ArchitectureElement | null>(null);
  const [linkedTraceLinks, setLinkedTraceLinks] = useState<TraceLink[]>([]);
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
        // Full (paginated-exhaustive) list — the decomposition tree needs
        // every element to resolve parent_id chains (REQ-001).
        const all = await architectureApi.listAll(activeWorkspace.id);
        if (cancelled) return;
        setElements(all);
      } catch {
        // list errors are non-fatal
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    }

    setIsLoading(true);
    void loadList();
    return () => { cancelled = true; };
  }, [activeWorkspace, tick]);

  // Effect 2: Load the selected element detail + tracelinks (independent of list)
  useEffect(() => {
    if (!activeWorkspace || !selectedId) {
      setElement(null);
      setLinkedTraceLinks([]);
      return;
    }

    let cancelled = false;

    async function loadDetail(): Promise<void> {
      if (!activeWorkspace || !selectedId) return;
      try {
        const el = await architectureApi.get(selectedId);
        if (cancelled) return;
        setElement(el);

        const links = await tracelinksApi.listForArtifact(activeWorkspace.id, el.id);
        if (cancelled) return;
        setLinkedTraceLinks(links.results);
      } catch (err: unknown) {
        if (cancelled) return;
        const msg =
          (err as { error?: { message?: string } })?.error?.message ??
          String(err);
        setError(msg);
        setElement(null);
      }
    }

    void loadDetail();
    return () => { cancelled = true; };
  }, [activeWorkspace, selectedId, tick]);

  return { elements, element, linkedTraceLinks, isLoading, error, refresh };
}
