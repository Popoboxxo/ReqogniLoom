/**
 * ARCH-L1-001 ReactFrontend — AI decompose panel lifecycle (#598 S2, UI-24).
 *
 * Extracted from `ArchitectureEditors.tsx`: the panel's open/close state and
 * the close confirmation. The decomposition itself still lives in
 * `ArchitectureDecomposePanel`; this hook only owns how it is opened and
 * closed.
 *
 * UI-24 contract kept verbatim: an Escape/backdrop close while a generated
 * draft is awaiting review (or a commit is in flight) must not discard it
 * silently — the panel asks first.
 */

import { useCallback, useState } from "react";

export interface UseArchitectureDecomposeResult {
  showDecomposePanel: boolean;
  decomposeHasPendingWork: boolean;
  showDecomposeCloseConfirm: boolean;
  openDecomposePanel: () => void;
  setDecomposeHasPendingWork: (value: boolean) => void;
  requestCloseDecomposePanel: () => void;
  confirmCloseDecomposePanel: () => void;
  cancelCloseDecomposePanel: () => void;
  handleCommitted: () => void;
}

export function useArchitectureDecompose(): UseArchitectureDecomposeResult {
  const [showDecomposePanel, setShowDecomposePanel] = useState(false);
  const [decomposeHasPendingWork, setDecomposeHasPendingWork] = useState(false);
  const [showDecomposeCloseConfirm, setShowDecomposeCloseConfirm] = useState(false);

  const openDecomposePanel = useCallback((): void => {
    setShowDecomposePanel(true);
  }, []);

  const requestCloseDecomposePanel = useCallback((): void => {
    if (decomposeHasPendingWork) {
      setShowDecomposeCloseConfirm(true);
      return;
    }
    setShowDecomposePanel(false);
  }, [decomposeHasPendingWork]);

  const confirmCloseDecomposePanel = useCallback((): void => {
    setShowDecomposeCloseConfirm(false);
    setDecomposeHasPendingWork(false);
    setShowDecomposePanel(false);
  }, []);

  /** A committed decomposition leaves the panel in a clean state. */
  const handleCommitted = useCallback((): void => {
    setDecomposeHasPendingWork(false);
    setShowDecomposePanel(false);
  }, []);

  const cancelCloseDecomposePanel = useCallback((): void => {
    setShowDecomposeCloseConfirm(false);
  }, []);

  return {
    showDecomposePanel,
    decomposeHasPendingWork,
    showDecomposeCloseConfirm,
    openDecomposePanel,
    setDecomposeHasPendingWork,
    requestCloseDecomposePanel,
    confirmCloseDecomposePanel,
    cancelCloseDecomposePanel,
    handleCommitted,
  };
}
