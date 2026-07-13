import { useState, useEffect, useCallback } from 'react';
import { testcasesApi, type TestCase } from '../../api/testcases';
import { useWorkspace } from '../../context/WorkspaceContext';

export function useTestCaseData(selectedId?: string) {
  const { activeWorkspace } = useWorkspace();
  const [items, setItems] = useState<TestCase[]>([]);
  const [item, setItem] = useState<TestCase | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  const loadList = useCallback(async () => {
    if (!activeWorkspace) return;
    setIsLoading(true);
    try {
      const resp = await testcasesApi.list(activeWorkspace.id);
      setItems(resp.results || []);
    } catch (err) {
      setError(err instanceof Error ? err : new Error(String(err)));
    } finally {
      setIsLoading(false);
    }
  }, [activeWorkspace]);

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
