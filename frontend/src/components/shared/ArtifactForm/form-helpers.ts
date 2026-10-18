/**
 * Pure, React-free helpers of the definition-driven artifact form.
 *
 * Extracted from `ArtifactForm.tsx` (Phase 5b decomposition, FE-01 / F-01).
 * The three public names (`groupIntoSections`, `firstErroredField`,
 * `findFieldControl`) are re-exported from `ArtifactForm.tsx`, so the barrel
 * `index.ts` and every consumer stay unchanged.
 */

import type { AttributeSpec } from "../../../api/attribute-definitions";
import type { ArtifactFormValues, FormSection } from "./artifact-form-types";

/**
 * Group attributes into sections.
 *
 * Section order is first-appearance in the definition; attribute order inside a
 * section is the definition's own `order` (the backend already sorts by
 * `(section, order, name)`, but a hand-edited definition PUT through
 * `/attribute-defaults/` is not re-sorted, so the client sorts too — one
 * `.sort` is cheaper than a rendering order nobody can explain).
 */
export function groupIntoSections(attributes: AttributeSpec[]): FormSection[] {
  const order: string[] = [];
  const bySection = new Map<string, AttributeSpec[]>();
  for (const attribute of attributes) {
    if (!bySection.has(attribute.section)) {
      bySection.set(attribute.section, []);
      order.push(attribute.section);
    }
    bySection.get(attribute.section)!.push(attribute);
  }
  return order.map((name) => {
    const sectionAttributes = [...bySection.get(name)!].sort(
      (a, b) => a.order - b.order
    );
    return {
      name,
      // A section is "expert" only when EVERY attribute in it is — one basic
      // attribute would otherwise be hidden behind a collapsed header.
      audience: sectionAttributes.every((a) => a.audience === "expert")
        ? "expert"
        : "basic",
      attributes: sectionAttributes,
    };
  });
}

export function readValue(values: ArtifactFormValues, attribute: AttributeSpec): unknown {
  return attribute.kind === "extended"
    ? (values.custom_fields ?? {})[attribute.name]
    : values[attribute.name];
}

export function writeValue(
  values: ArtifactFormValues,
  attribute: AttributeSpec,
  next: unknown
): ArtifactFormValues {
  if (attribute.kind === "extended") {
    return {
      ...values,
      custom_fields: { ...(values.custom_fields ?? {}), [attribute.name]: next },
    };
  }
  return { ...values, [attribute.name]: next };
}

// ---------------------------------------------------------------------------
// Issue #1087 — error-to-field focus routing
// ---------------------------------------------------------------------------

/**
 * Elements that take focus without a `tabindex`. Anything else in a field cell
 * is a composite (a widget) and needs `tabindex="-1"` before a programmatic
 * focus can land on it.
 */
export const FOCUSABLE_SELECTOR = /^(INPUT|SELECT|TEXTAREA|BUTTON|A)$/;

/**
 * The first errored attribute in DEFINITION order, not in `Object.keys` order:
 * the definition is the order the fields are drawn in, so this is the topmost
 * offending control on screen. An error naming a field the definition does not
 * declare (e.g. a `custom_fields` key) still resolves, so the fallback is the
 * first key rather than nothing.
 */
export function firstErroredField(
  errors: Record<string, string[]>,
  attributes: readonly AttributeSpec[]
): string | null {
  const names = Object.keys(errors);
  if (names.length === 0) return null;
  const inDefinitionOrder = attributes
    .filter((attribute) => names.includes(attribute.name))
    .map((attribute) => attribute.name);
  return inDefinitionOrder[0] ?? names[0];
}

/**
 * Locate the focus target for the attribute named `name`.
 *
 * Two shapes, tried in this order:
 *   1. the field's own control — every `FieldShell`-based control takes its
 *      `id` AND its `data-testid` from the same `testId` (see
 *      `fields/FieldShell.tsx`), possibly renamed by the adapter's
 *      `fieldTestIds` (#583);
 *   2. the composite that draws it — an attribute with `type: "widget"` claims
 *      the fields in its `fields` list and is not rendered standalone
 *      (`widgetOwned` in the renderer), so the widget's own container is the
 *      only focusable thing on screen for a failure inside it. Widgets name
 *      their inner controls differently from each other, so resolving those
 *      per widget would be a second, drifting lookup table.
 */
export function findFieldControl(
  root: HTMLElement | null,
  name: string,
  fieldTestIds?: Record<string, string>,
  attributes?: readonly AttributeSpec[]
): HTMLElement | null {
  if (!root) return null;
  const testId = fieldTestIds?.[name] ?? `artifact-field-${name}`;
  const direct = root.querySelector<HTMLElement>(`[data-testid="${testId}"]`);
  if (direct) return direct;
  const owner = attributes?.find(
    (attribute) => attribute.type === "widget" && attribute.fields.includes(name)
  );
  return owner
    ? root.querySelector<HTMLElement>(`[data-testid="artifact-widget-${owner.name}"]`)
    : null;
}
