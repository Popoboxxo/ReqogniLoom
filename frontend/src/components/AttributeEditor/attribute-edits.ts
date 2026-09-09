/**
 * Pure list edits for the attribute editor (spec section 6.1, Task 26).
 *
 * Every function returns a NEW array — the page keeps the edited definition in
 * React state and must never mutate it in place, or the "unsaved changes"
 * comparison against the loaded definition would always read clean.
 */

import type { AttributeSpec } from "../../api/attribute-definitions";

const CORE_IMMUTABLE: ReadonlySet<keyof AttributeSpec> = new Set([
  "name",
  "type",
  "kind",
  "locked",
  "widget_key",
  "fields",
]);

const LOCKED_IMMUTABLE: ReadonlySet<keyof AttributeSpec> = new Set([
  "visible",
  "required",
  "editable",
]);

/** Sections in first-appearance order, which is the order the list renders. */
export function sectionNames(attributes: AttributeSpec[]): string[] {
  const seen: string[] = [];
  for (const attribute of attributes) {
    if (!seen.includes(attribute.section)) seen.push(attribute.section);
  }
  return seen;
}

function renumber(attributes: AttributeSpec[]): AttributeSpec[] {
  const counters = new Map<string, number>();
  return attributes.map((attribute) => {
    const next = counters.get(attribute.section) ?? 0;
    counters.set(attribute.section, next + 1);
    return { ...attribute, order: next };
  });
}

/**
 * Move `name` to position `toIndex` within `toSection`.
 *
 * A `locked` attribute is deliberately NOT exempt: only
 * visible/required/editable are frozen on it, order and section stay editable
 * because they are cosmetic (spec section 3.1).
 */
export function moveAttribute(
  attributes: AttributeSpec[],
  name: string,
  toSection: string,
  toIndex: number
): AttributeSpec[] {
  const moving = attributes.find((a) => a.name === name);
  if (!moving) return attributes;
  const rest = attributes.filter((a) => a.name !== name);
  const target = rest.filter((a) => a.section === toSection);
  const others = rest.filter((a) => a.section !== toSection);
  const clamped = Math.max(0, Math.min(toIndex, target.length));
  target.splice(clamped, 0, { ...moving, section: toSection });

  // Preserve section order: rebuild by walking the original section sequence.
  const order = sectionNames([...attributes, { ...moving, section: toSection }]);
  const rebuilt: AttributeSpec[] = [];
  for (const section of order) {
    rebuilt.push(
      ...(section === toSection ? target : others.filter((a) => a.section === section))
    );
  }
  return renumber(rebuilt);
}

export function renameSection(
  attributes: AttributeSpec[],
  from: string,
  to: string
): AttributeSpec[] {
  const clean = to.trim();
  if (!clean) throw new Error("A section name may not be empty.");
  return attributes.map((a) => (a.section === from ? { ...a, section: clean } : a));
}

/** Delete an EMPTY section. Throws when it still holds attributes. */
export function deleteSection(
  attributes: AttributeSpec[],
  name: string
): AttributeSpec[] {
  if (attributes.some((a) => a.section === name)) {
    throw new Error(`Section '${name}' is not empty.`);
  }
  return attributes;
}

/** Move a whole section to `toIndex` in the section sequence. */
export function moveSection(
  attributes: AttributeSpec[],
  name: string,
  toIndex: number
): AttributeSpec[] {
  const order = sectionNames(attributes).filter((s) => s !== name);
  const clamped = Math.max(0, Math.min(toIndex, order.length));
  order.splice(clamped, 0, name);
  const rebuilt: AttributeSpec[] = [];
  for (const section of order) {
    rebuilt.push(...attributes.filter((a) => a.section === section));
  }
  return renumber(rebuilt);
}

export function patchAttribute(
  attributes: AttributeSpec[],
  name: string,
  patch: Partial<AttributeSpec>
): AttributeSpec[] {
  return attributes.map((a) => (a.name === name ? { ...a, ...patch } : a));
}

/**
 * Whether the editor must render `property` as read-only for `attribute`.
 *
 * Mirrors the backend rules of `attribute_definitions/schema.py`
 * (`validate_meta_only_change`) so the UI never offers an edit the API will
 * reject with 400. NOTE (gap #5, see ledger): the backend itself does not
 * enforce `CORE_EDITABLE_META_PROPERTIES` — `widget_key`/`fields` are frozen
 * here client-side for every `kind: "core"` attribute as a conservative UX
 * choice, but `AttributeInspector` never renders a control for either
 * property anyway, so this function's coverage of them is inert today, not a
 * live gap this task introduces or depends on.
 */
export function isMetaPropertyLocked(
  attribute: AttributeSpec,
  property: keyof AttributeSpec
): boolean {
  if (attribute.kind === "core" && CORE_IMMUTABLE.has(property)) return true;
  if (attribute.locked && LOCKED_IMMUTABLE.has(property)) return true;
  return false;
}
