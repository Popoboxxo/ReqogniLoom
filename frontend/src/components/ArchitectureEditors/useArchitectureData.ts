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

  useEffect(() => {
    if (!activeWorkspace) return;

    let cancelled = false;
    setIsLoading(true);
    setError(null);

    async function load(): Promise<void> {
      if (!activeWorkspace) return;
      try {
        const resp = await architectureApi.list(activeWorkspace.id);
        if (cancelled) return;
        setElements(resp.results);

        if (selectedId) {
          let el: ArchitectureElement | null = null;
          try {
            el = await architectureApi.get(selectedId);
          } catch {
            el = null;
          }
          setElement(el);

          if (el) {
            const links = await tracelinksApi.listForArtifact(
              activeWorkspace.id,
              el.id
            );
            if (cancelled) return;
            setLinkedTraceLinks(links.results);
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

  return { elements, element, linkedTraceLinks, isLoading, error, refresh };
}
