import { useState, useEffect, useCallback } from 'react';
import { stakeholderNeedApi } from '../../api/stakeholder-need';
import { useWorkspace } from '../../context/WorkspaceContext';
import type { StakeholderNeed } from '../../types';

export function useNeedData(selectedId?: string) {
  const { activeWorkspace } = useWorkspace();
  const [needs, setNeeds] = useState<StakeholderNeed[]>([]);
  const [need, setNeed] = useState<StakeholderNeed | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  const loadList = useCallback(async () => {
    if (!activeWorkspace) return;
    setIsLoading(true);
    try {
      const resp = await stakeholderNeedApi.listByWorkspace(activeWorkspace.id);
      setNeeds(resp.results || []);
    } catch (err) {
      setError(err instanceof Error ? err : new Error(String(err)));
    } finally {
      setIsLoading(false);
    }
  }, [activeWorkspace]);

  const loadDetail = useCallback(async () => {
    if (!selectedId) {
      setNeed(null);
      return;
    }
    setIsLoading(true);
    try {
      const resp = await stakeholderNeedApi.get(selectedId);
      setNeed(resp);
    } catch (err) {
      setError(err instanceof Error ? err : new Error(String(err)));
    } finally {
      setIsLoading(false);
    }
  }, [selectedId]);

  useEffect(() => {
    loadList();
  }, [loadList]);

  useEffect(() => {
    loadDetail();
  }, [loadDetail]);

  return {
    needs,
    need,
    isLoading,
    error,
    refresh: () => {
      loadList();
      loadDetail();
    },
  };
}
