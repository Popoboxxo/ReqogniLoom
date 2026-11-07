/**
 * P5 Task 5.2 — resolve the workspace's card-field configuration for the graph.
 *
 * The graph itself stores nothing: this hook only reads the preference-backed
 * configuration and falls back to the built-in defaults (see `cardFields.ts`).
 */

import { useEffect, useState } from "react";

import {
  cardFieldsApi,
  defaultCardFieldConfigMap,
  type CardFieldConfigMap,
} from "./cardFields";

export function useCardFields(
  workspaceId: string | null | undefined
): CardFieldConfigMap {
  const [config, setConfig] = useState<CardFieldConfigMap>(() =>
    defaultCardFieldConfigMap()
  );

  useEffect(() => {
    let active = true;
    setConfig(defaultCardFieldConfigMap());
    if (!workspaceId) {
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
  }, [workspaceId]);

  return config;
}
