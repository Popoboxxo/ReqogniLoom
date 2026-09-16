/**
 * Payload contract for non-editable attributes (issue #886).
 *
 * `backend/attribute_definitions/field_validation.py::validate_values`
 * documents the contract explicitly: a form renderer must OMIT non-editable
 * attributes from its payload, not merely render them disabled. The backend
 * rejects an UPDATE carrying a value for an `editable === false` attribute
 * with "is not editable and must not be sent in an update payload" — even when
 * the value equals the stored one, because the REST path never compares.
 *
 * That rejection is deliberately NOT enforced on create (same docstring): a
 * `required` + `editable === false` attribute would otherwise be unsatisfiable
 * by any caller. A create payload therefore still carries such a field; only
 * an update drops it.
 *
 * `editable === "system"` is server-owned (spec section 6: "ID, Status;
 * nie schreibbar") and is never a payload field at all — it is dropped in both
 * modes, exactly like the backend's own `payload_names` excludes it.
 */

import type { AttributeSpec } from "../../../api/attribute-definitions";
import type { ArtifactFormValues } from "./ArtifactForm";

/**
 * Return a copy of *values* without the attributes the backend's payload
 * contract forbids.
 *
 * The discrimination is per-field and driven by the definition metadata
 * (`editable`, `kind`) — never a static key list, which cannot know about a
 * dynamically-declared `editable: false` attribute.
 *
 * - update (`mode === "update"`): drops `editable === false` attributes.
 * - create (`mode === "create"`): keeps them (the backend accepts them, see
 *   the module docstring).
 * - both modes: drops `editable === "system"` attributes.
 *
 * `kind: "extended"` attributes live in the `custom_fields` bag, so they are
 * removed from there rather than from the top level.
 */
export function stripNonEditableValues(
  values: ArtifactFormValues,
  attributes: AttributeSpec[],
  mode: "create" | "update"
): ArtifactFormValues {
  const dropCore = new Set<string>();
  const dropExtended = new Set<string>();
  for (const attribute of attributes) {
    const omit =
      attribute.editable === "system" ||
      (mode === "update" && attribute.editable === false);
    if (!omit) continue;
    if (attribute.kind === "extended") dropExtended.add(attribute.name);
    else dropCore.add(attribute.name);
  }
  if (!dropCore.size && !dropExtended.size) return values;

  const next: ArtifactFormValues = {};
  for (const [key, value] of Object.entries(values)) {
    if (dropCore.has(key)) continue;
    next[key] = value;
  }

  const customFields = values.custom_fields;
  if (!dropExtended.size || !customFields) return next;

  const filteredCustomFields: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(customFields)) {
    if (dropExtended.has(key)) continue;
    filteredCustomFields[key] = value;
  }
  next.custom_fields = filteredCustomFields;
  return next;
}
