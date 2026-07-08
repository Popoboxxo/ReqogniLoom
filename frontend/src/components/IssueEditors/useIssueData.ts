import { useState, useEffect, useCallback } from 'react';
import { issuesApi } from '../../api/issues';
import { useWorkspace } from '../../context/WorkspaceContext';
import type { Issue } from '../../types';

export function useIssueData(selectedId?: string) {
  const { activeWorkspace } = useWorkspace();
  const [items, setItems] = useState<Issue[]>([]);
  const [item, setItem] = useState<Issue | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  const loadList = useCallback(async () => {
    if (!activeWorkspace) return;
    setIsLoading(true);
    try {
      const resp = await issuesApi.list(activeWorkspace.id);
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
      const resp = await issuesApi.get(selectedId);
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
