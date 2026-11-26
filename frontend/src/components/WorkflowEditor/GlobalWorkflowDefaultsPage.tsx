/**
 * REQ-178/REQ-179 — global-scope container for the workflow editor (SCR-205).
 *
 * P2.4: this container owns everything specific to System Settings → Workflow
 * Defaults — the entity type and the preset both live in the query string, the
 * requested preset is validated against the selected entity's canonical choices
 * and the address bar is kept canonical on every resolution.
 *
 * An unknown ``entityType`` parameter yields no entity type and therefore no
 * graph: the container renders the shared invalid-entity notice rather than an
 * editor for an arbitrary type.
 */

import { useEffect } from "react";
import { useSearchParams } from "react-router-dom";
import type { WorkflowPresetKey } from "../../api/workflows";
import {
  DEFAULT_ENTITY_TYPE,
  defaultWorkflowPreset,
  entityTypeFromSlug,
  isWorkflowPresetForEntity,
  workflowPresetsForEntity,
} from "./constants";
import { WorkflowEditorContent } from "./WorkflowEditorContent";
import { WorkflowEditorInvalidEntity } from "./WorkflowEditorInvalidEntity";

const BACK_TO = "/system-settings?tab=workflow-defaults";

export function GlobalWorkflowDefaultsPage(): JSX.Element {
  const [searchParams, setSearchParams] = useSearchParams();
  const rawSlug = searchParams.get("entityType");
  const hasEntitySlug = rawSlug != null && rawSlug.length > 0;
  const entityType = hasEntitySlug
    ? entityTypeFromSlug(rawSlug)
    : DEFAULT_ENTITY_TYPE;

  const requestedPreset = searchParams.get("preset");
  const presetOptions = entityType ? workflowPresetsForEntity(entityType) : [];
  const fallbackPreset = entityType
    ? defaultWorkflowPreset(entityType)
    : "standard";
  const globalPreset: WorkflowPresetKey =
    entityType && isWorkflowPresetForEntity(entityType, requestedPreset)
      ? requestedPreset
      : fallbackPreset;

  // Keep deep links canonical: never request a generic Document tier or an
  // unprefixed WorkItem tier just because the URL carries one.
  useEffect(() => {
    if (!entityType) return;
    if (
      requestedPreset === globalPreset &&
      searchParams.get("entityType") === entityType
    ) {
      return;
    }
    const next = new URLSearchParams(searchParams);
    next.set("entityType", entityType);
    next.set("preset", globalPreset);
    setSearchParams(next, { replace: true });
  }, [entityType, requestedPreset, globalPreset, searchParams, setSearchParams]);

  if (!entityType) {
    return <WorkflowEditorInvalidEntity slug={rawSlug} backTo={BACK_TO} />;
  }

  return (
    <WorkflowEditorContent
      entityType={entityType}
      preset={globalPreset}
      presetOptions={presetOptions}
      isGlobal={true}
    />
  );
}
