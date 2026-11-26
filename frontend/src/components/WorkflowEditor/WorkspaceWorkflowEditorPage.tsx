/**
 * REQ-176/REQ-177 — workspace-scope container for the workflow editor.
 *
 * P2.4: this container owns everything specific to ``/workflows/:entityType``
 * — the entity type comes from the route slug, the workspace definition has no
 * preset dimension, and there is no URL canonicalisation. Everything below the
 * resolution is the shared ``WorkflowEditorContent``.
 *
 * An unknown slug yields no entity type and therefore no graph: the container
 * renders the shared invalid-entity notice instead of silently falling back to
 * Requirement.
 */

import { useParams } from "react-router-dom";
import { DEFAULT_ENTITY_TYPE, entityTypeFromSlug } from "./constants";
import { WorkflowEditorContent } from "./WorkflowEditorContent";
import { WorkflowEditorInvalidEntity } from "./WorkflowEditorInvalidEntity";

export function WorkspaceWorkflowEditorPage(): JSX.Element {
  const { entityType: entitySlug } = useParams<{ entityType: string }>();
  const hasEntitySlug = entitySlug != null && entitySlug.length > 0;
  const entityType = hasEntitySlug
    ? entityTypeFromSlug(entitySlug)
    : DEFAULT_ENTITY_TYPE;

  if (!entityType) {
    return (
      <WorkflowEditorInvalidEntity slug={entitySlug ?? null} backTo="/workflows" />
    );
  }

  // A workspace definition is preset-less: the body derives the displayed
  // preset from the graph, and the global-only props of the shared content are
  // simply absent for this scope (the props are a discriminated union).
  return <WorkflowEditorContent entityType={entityType} isGlobal={false} />;
}
