/**
 * RequirementEditors — list-level write actions (S3.2 WP-5).
 *
 * Extracted verbatim from `RequirementEditors.tsx`: reparenting via the tree,
 * deleting from the list (with its "did it really succeed" return value, issue
 * #811) and the shared inline error banner for both. The create form and its
 * mutation stay in the component/hook pair that owns that form.
 */

import { useCallback, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import type { TFunction } from "i18next";

import { artifactsApi } from "../../api/artifacts";
import { extractApiErrorMessage } from "../../api/client";
import { useDeleteRequirement } from "../../queries/requirements";
import type { Requirement } from "../../types";
import {
  buildArtifactIdMap,
  resolveArtifactId,
} from "./requirement-editors.logic";

export interface UseRequirementListActionsOptions {
  requirements: Requirement[];
  workspaceId: string | undefined;
  refresh: () => void;
  t: TFunction;
}

export interface UseRequirementListActionsResult {
  actionError: string | null;
  setActionError: (message: string | null) => void;
  handleReorder: (
    id: string,
    newParentId: string | null,
    afterId: string | null | undefined,
  ) => Promise<void>;
  handleDelete: (id: string, changeReason?: string) => Promise<boolean>;
}

export function useRequirementListActions({
  requirements,
  workspaceId,
  refresh,
  t,
}: UseRequirementListActionsOptions): UseRequirementListActionsResult {
  const navigate = useNavigate();
  const deleteRequirement = useDeleteRequirement();

  // #340: failures of the header actions (PDF export) and of the list's row
  // actions (delete) have no form to attach to — rendered as a banner under
  // the page header. The route actions hook writes into this state too.
  const [actionError, setActionError] = useState<string | null>(null);

  /**
   * P1 Task 1.7: the tree addresses nodes by Requirement id, the move route by
   * backing Artifact id. Both id spaces exist side by side here, so the
   * mapping is explicit rather than a cast.
   */
  const artifactIdByRequirementId = useMemo(
    () => buildArtifactIdMap(requirements),
    [requirements],
  );

  const handleReorder = useCallback(
    async (
      id: string,
      newParentId: string | null,
      afterId: string | null | undefined,
    ): Promise<void> => {
      const toArtifactId = (nodeId: string | null): string | null =>
        resolveArtifactId(artifactIdByRequirementId, nodeId);
      const artifactId = toArtifactId(id);
      if (artifactId === null) return;
      await artifactsApi.move(artifactId, {
        parent_id: toArtifactId(newParentId),
        ...(afterId === undefined
          ? {}
          : { after_id: toArtifactId(afterId) }),
      });
      refresh();
    },
    [artifactIdByRequirementId, refresh],
  );

  /**
   * Issue #811: returns whether the delete actually succeeded so the caller
   * (the confirm dialog in RequirementList) knows whether it may close itself.
   */
  const handleDelete = useCallback(
    async (id: string, changeReason?: string): Promise<boolean> => {
      if (!workspaceId) return false;
      setActionError(null);
      try {
        await deleteRequirement.mutateAsync({ id, workspaceId, changeReason });
        navigate('/requirements');
        return true;
      } catch (err: unknown) {
        // #340: a refused delete (permission, workflow gate) must not look
        // like the row simply stayed where it was.
        setActionError(extractApiErrorMessage(err) ?? t('req.deleteFailed'));
        return false;
      }
    },
    [workspaceId, deleteRequirement, navigate, t]
  );

  return {
    actionError,
    setActionError,
    handleReorder,
    handleDelete,
  };
}
