/**
 * P5 Task 5.2 — resolve the workspace's card-field configuration for the graph.
 *
 * The graph itself stores nothing: this hook only reads the preference-backed
 * configuration and falls back to the built-in defaults (see `cardFields.ts`).
 */

import { useEffect, useState } from "react";

import { useWorkspace } from "../../context/WorkspaceContext";
import { isPlaceholderWorkspaceId } from "../../utils/workspaceId";
import {
  cardFieldsApi,
  defaultCardFieldConfigMap,
  type CardFieldConfigMap,
} from "./cardFields";

export function useCardFields(
  workspaceId: string | null | undefined
): CardFieldConfigMap {
  const { activeWorkspace } = useWorkspace();
  // Derived boolean, not the object: context reads may return a fresh wrapper
  // per render (tests/memo-less providers), which would re-run the effect.
  const isPlaceholder = isPlaceholderWorkspaceId(activeWorkspace?.id);
  const [config, setConfig] = useState<CardFieldConfigMap>(() =>
    defaultCardFieldConfigMap()
  );

  useEffect(() => {
    let active = true;
    setConfig(defaultCardFieldConfigMap());
    // The caller's id is the truthy DEFAULT_WORKSPACE placeholder until a real
    // workspace resolves; loading it would hit a 404 preference route. Identity
    // also covers auth restore, where isLoadingWorkspace is already false.
    if (!workspaceId || isPlaceholder) {
      return () => {
        active = false;
      };
    }
    void cardFieldsApi.load(workspaceId).then((next) => {
      if (active) setConfig(next);
    });
    return () => {
      active = false;
    };
  }, [workspaceId, isPlaceholder]);

  return config;
}
