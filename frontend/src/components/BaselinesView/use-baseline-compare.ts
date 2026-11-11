/**
 * ARCH-L1-001 ReactFrontend — baseline compare dialog (#598 S2, REQ-L2-BL-003).
 *
 * Extracted from `BaselinesView.tsx`: selecting two baselines and reading their
 * field-level diff is independent of the list, the create form and the delete
 * confirmation. The hook keeps the two validation rules the dialog has always
 * had — both sides must be chosen, and they must differ — before the request.
 */

import { useCallback, useState } from "react";
import type { TFunction } from "i18next";

import { compareBaselines } from "../../api/baselines";
import type { BaselineDiff } from "../../api/baselines";

/** Read the server's message, falling back to its stringification. */
function compareErrorMessage(err: unknown): string {
  const apiErr = err as { error?: { message?: string } };
  if (apiErr?.error?.message) return apiErr.error.message;
  return err instanceof Error ? err.message : String(err);
}

export interface UseBaselineCompareResult {
  showCompare: boolean;
  compareAId: string;
  compareBId: string;
  diff: BaselineDiff | null;
  diffLoading: boolean;
  diffError: string | null;
  setCompareAId: (id: string) => void;
  setCompareBId: (id: string) => void;
  openCompare: () => void;
  closeCompare: () => void;
  handleCompare: () => Promise<void>;
}

export function useBaselineCompare(t: TFunction): UseBaselineCompareResult {
  const [showCompare, setShowCompare] = useState(false);
  const [compareAId, setCompareAId] = useState("");
  const [compareBId, setCompareBId] = useState("");
  const [diff, setDiff] = useState<BaselineDiff | null>(null);
  const [diffLoading, setDiffLoading] = useState(false);
  const [diffError, setDiffError] = useState<string | null>(null);

  const openCompare = useCallback((): void => {
    setShowCompare(true);
    setDiff(null);
    setDiffError(null);
  }, []);

  const closeCompare = useCallback((): void => {
    setShowCompare(false);
    setDiff(null);
    setDiffError(null);
  }, []);

  const handleCompare = useCallback(async (): Promise<void> => {
    if (!compareAId || !compareBId) {
      setDiffError(t("baselines.compareSelectBoth"));
      return;
    }
    if (compareAId === compareBId) {
      setDiffError(t("baselines.compareSameBaseline"));
      return;
    }
    setDiffLoading(true);
    setDiffError(null);
    try {
      const result = await compareBaselines(compareAId, compareBId);
      setDiff(result);
    } catch (err: unknown) {
      setDiffError(compareErrorMessage(err));
      setDiff(null);
    } finally {
      setDiffLoading(false);
    }
  }, [compareAId, compareBId, t]);

  return {
    showCompare,
    compareAId,
    compareBId,
    diff,
    diffLoading,
    diffError,
    setCompareAId,
    setCompareBId,
    openCompare,
    closeCompare,
    handleCompare,
  };
}
