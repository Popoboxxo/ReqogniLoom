/**
 * ArchitectureEditors — list-level write actions (S3.2 WP-5).
 *
 * Extracted verbatim from `ArchitectureEditors.tsx`: reparenting via the tree
 * and deleting from the list context menu, plus the shared inline error banner
 * and the delete-confirmation target. Both writes are list-level (the create
 * dialog has its own hook) and both report refusal through the same banner
 * (#340), which is the cohesion boundary here.
 *
 * The tree applies moves optimistically and rolls back on rejection; this hook
 * deliberately lets the error propagate so the tree's own toast also fires.
 */

import { useCallback, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import type { TFunction } from "i18next";

import { architectureApi } from "../../api/architecture";
import { artifactsApi } from "../../api/artifacts";
import { extractApiErrorMessage } from "../../api/client";
import type { ArchitectureElement } from "../../types";
import {
  buildArtifactIdMap,
  resolveArtifactId,
} from "./architecture-editors.logic";

export interface UseArchitectureListActionsOptions {
  elements: ArchitectureElement[];
  refresh: () => void;
  t: TFunction;
}

export interface UseArchitectureListActionsResult {
  listActionError: string | null;
  setListActionError: (message: string | null) => void;
  deleteTarget: ArchitectureElement | null;
  setDeleteTarget: (target: ArchitectureElement | null) => void;
  handleReorder: (
    id: string,
    newParentId: string | null,
    afterId: string | null | undefined,
  ) => Promise<void>;
  handleDelete: (id: string) => Promise<void>;
}

export function useArchitectureListActions({
  elements,
  refresh,
  t,
}: UseArchitectureListActionsOptions): UseArchitectureListActionsResult {
  const navigate = useNavigate();

  // #340: rejected create/delete calls used to end in a bare console.error,
  // leaving the list unchanged and the user without any reason. One banner in
  // the list panel serves both — they are the only two list-level writes.
  const [listActionError, setListActionError] = useState<string | null>(null);

  // Delete-confirmation target from list context menu
  const [deleteTarget, setDeleteTarget] = useState<ArchitectureElement | null>(null);

  /**
   * Drag & drop reordering/reparenting from the tree (P1 Task 1.7).
   *
   * The move endpoint keys on the backing Artifact id, while the tree's nodes
   * carry the ArchitectureElement id (`el.id`, used by the route/selection),
   * so every id in the triple is translated here. The rejection path is the
   * tree's toast, which is why this handler lets the error propagate.
   */
  const artifactIdByElementId = useMemo(
    () => buildArtifactIdMap(elements),
    [elements],
  );

  const handleReorder = useCallback(
    async (
      id: string,
      newParentId: string | null,
      afterId: string | null | undefined,
    ): Promise<void> => {
      setListActionError(null);
      const toArtifactId = (nodeId: string | null): string | null =>
        resolveArtifactId(artifactIdByElementId, nodeId);
      const artifactId = toArtifactId(id);
      if (artifactId === null) return;
      try {
        await artifactsApi.move(artifactId, {
          parent_id: toArtifactId(newParentId),
          ...(afterId === undefined
            ? {}
            : { after_id: toArtifactId(afterId) }),
        });
        refresh();
      } catch (err: unknown) {
        // Keep the inline banner (#340) for a refused move while the tree
        // rolls its optimistic order back; rethrow so the tree also surfaces
        // the failure.
        setListActionError(
          extractApiErrorMessage(err) ?? t("arch.reparentFailed"),
        );
        throw err;
      }
    },
    [artifactIdByElementId, refresh, t],
  );

  const handleDelete = useCallback(
    async (id: string): Promise<void> => {
      setListActionError(null);
      try {
        await architectureApi.delete(id);
        refresh();
        navigate("/architecture");
      } catch (err: unknown) {
        // #340: a refused delete used to leave the element in the tree with
        // no explanation. Shares the list-panel banner with create.
        setListActionError(extractApiErrorMessage(err) ?? t("arch.deleteFailed"));
      }
    },
    [refresh, navigate, t]
  );

  return {
    listActionError,
    setListActionError,
    deleteTarget,
    setDeleteTarget,
    handleReorder,
    handleDelete,
  };
}
