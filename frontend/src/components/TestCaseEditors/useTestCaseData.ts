import { useState, useEffect, useCallback } from 'react';
import { testcasesApi, type TestCase } from '../../api/testcases';
import { useWorkspace } from '../../context/WorkspaceContext';

export function useTestCaseData(selectedId?: string) {
  const { activeWorkspace, isLoadingWorkspace } = useWorkspace();
  const [items, setItems] = useState<TestCase[]>([]);
  const [item, setItem] = useState<TestCase | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  const loadList = useCallback(async () => {
    // Issue B: activeWorkspace starts as the DEFAULT_WORKSPACE placeholder
    // (truthy fake UUID) until isLoadingWorkspace flips to false, so a bare
    // `!activeWorkspace` guard fires against the fake id (401).
    if (!activeWorkspace || isLoadingWorkspace) return;
    setIsLoading(true);
    try {
      // Issue C: list() only returned page 1 (PAGE_SIZE=25) — listAll()
      // follows pagination until exhaustion.
      const results = await testcasesApi.listAll(activeWorkspace.id);
      setItems(results);
    } catch (err) {
      setError(err instanceof Error ? err : new Error(String(err)));
    } finally {
      setIsLoading(false);
    }
  }, [activeWorkspace, isLoadingWorkspace]);

  const loadDetail = useCallback(async () => {
    if (!selectedId) { setItem(null); return; }
    setIsLoading(true);
    try {
      const resp = await testcasesApi.get(selectedId);
      setItem(resp);
    } catch (err) {
      setError(err instanceof Error ? err : new Error(String(err)));
    } finally {
      setIsLoading(false);
    }
  }, [selectedId]);

  useEffect(() => { loadList(); }, [loadList]);
  useEffect(() => { loadDetail(); }, [loadDetail]);

  return { items, item, isLoading, error, refresh: () => { loadList(); loadDetail(); } };
}
