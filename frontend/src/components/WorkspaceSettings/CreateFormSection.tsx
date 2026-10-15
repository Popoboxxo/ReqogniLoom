/**
 * Issue #1263 — the workspace level of the create-dialog form definition.
 *
 * Rendered in `WorkspaceSettings`'s "Darstellung" tab. The override applies to
 * every member of the workspace and therefore needs write authority, which the
 * server re-asserts (`CreateFormConfigService.set_config(scope="workspace")`).
 */

import { CreateFormFieldsSection } from "../shared/CreateFormFields/CreateFormFieldsSection";

export interface CreateFormSectionProps {
  /** The workspace whose override this section edits. */
  workspaceId: string;
}

export function CreateFormSection({
  workspaceId,
}: CreateFormSectionProps): JSX.Element {
  return (
    <CreateFormFieldsSection
      scope="workspace"
      workspaceId={workspaceId}
      titleKey="createForm.workspace.title"
      hintKey="createForm.workspace.hint"
      testId="workspace-create-form"
    />
  );
}
