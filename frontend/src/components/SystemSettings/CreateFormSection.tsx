/**
 * Issue #1263 — the tenant-wide level of the create-dialog form definition.
 *
 * Rendered in `SystemSettings`'s "Darstellung" tab, beside the navigation-tree
 * configuration. The default every workspace inherits unless it overrides it.
 * Writes need the `admin` role; the service re-asserts that on top of the view's
 * ADMIN-tier API-key capability gate.
 */

import { CreateFormFieldsSection } from "../shared/CreateFormFields/CreateFormFieldsSection";

export function CreateFormSection(): JSX.Element {
  return (
    <CreateFormFieldsSection
      scope="global"
      titleKey="createForm.global.title"
      hintKey="createForm.global.hint"
      testId="global-create-form"
    />
  );
}
