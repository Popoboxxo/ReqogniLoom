/**
 * Pure list edits for the attribute editor (spec section 6.1, Task 26).
 *
 * Every function returns a NEW array — the page keeps the edited definition in
 * React state and must never mutate it in place, or the "unsaved changes"
 * comparison against the loaded definition would always read clean.
 */

import type {
  AttributeSpec,
  LayoutToken,
  SectionLayout,
  SectionSpec,
} from "../../api/attribute-definitions";

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

/**
 * Distance between two freshly spaced ordering keys (feature #1260).
 *
 * Mirrors `backend/attribute_definitions/ordering.py::ORDER_STEP`. The ordering
 * key is deliberately SPARSE, not a list index: a move then rewrites exactly
 * one entry, which is what keeps two concurrent editors in the same section from
 * silently losing one of the two moves.
 */
export const ORDER_STEP = 1000;

/** Canonical row order of one section: `(order, name)`, matching the backend. */
function sortSection(attributes: AttributeSpec[]): AttributeSpec[] {
  return [...attributes].sort(
    (left, right) => left.order - right.order || left.name.localeCompare(right.name)
  );
}

/**
 * Rebuild the list in the backend's canonical order — sections in first
 * appearance, rows inside a section by `(order, name)`.
 *
 * The list is what `AttributeList`/`AttributeTable` filter per section, so the
 * array order (not just the `order` key) decides what the user sees. Rebuilding
 * here keeps the local buffer byte-identical to what a save/read round-trip
 * returns, so a persisted move does not leave the editor falsely "dirty".
 */
function canonicalize(attributes: AttributeSpec[]): AttributeSpec[] {
  const rebuilt: AttributeSpec[] = [];
  for (const section of sectionNames(attributes)) {
    rebuilt.push(...sortSection(attributes.filter((a) => a.section === section)));
  }
  return rebuilt;
}

/** Assign fresh, evenly spaced keys to every attribute of every section. */
function renumber(attributes: AttributeSpec[]): AttributeSpec[] {
  const counters = new Map<string, number>();
  return attributes.map((attribute) => {
    const next = (counters.get(attribute.section) ?? 0) + 1;
    counters.set(attribute.section, next);
    return { ...attribute, order: next * ORDER_STEP };
  });
}

/**
 * A free integer strictly between `previous` and `next`, or `null` when the two
 * neighbours hold adjacent keys and the section has to be re-spaced instead.
 *
 * Same rules as the backend's `_place_between`: head insertion never goes
 * negative (`null` triggers a re-space instead), tail insertion just adds one
 * step.
 */
function placeBetween(previous: number | null, next: number | null): number | null {
  if (previous === null && next === null) return ORDER_STEP;
  if (previous === null) {
    const candidate = (next as number) - ORDER_STEP;
    return candidate >= 0 ? candidate : null;
  }
  if (next === null) return previous + ORDER_STEP;
  const candidate = Math.floor((previous + next) / 2);
  return previous < candidate && candidate < next ? candidate : null;
}

/**
 * The attribute the moved one must follow to land at `toIndex` in `toSection`,
 * or `null` for "front of the section" (feature #1260).
 *
 * This is the value the atomic reorder call sends: the server resolves the
 * sparse key from the two neighbours instead of trusting a client-computed
 * index, which is what makes a parallel edit safe.
 */
export function moveAnchor(
  attributes: AttributeSpec[],
  name: string,
  toSection: string,
  toIndex: number
): string | null {
  const target = sortSection(
    attributes.filter((a) => a.name !== name && a.section === toSection)
  );
  const clamped = Math.max(0, Math.min(toIndex, target.length));
  return clamped === 0 ? null : target[clamped - 1]!.name;
}

/**
 * The attribute that currently precedes `name` inside its own section, or
 * `null` when it is first — the anchor that restores its old position after an
 * undo (feature #1260).
 */
export function anchorBefore(attributes: AttributeSpec[], name: string): string | null {
  const moving = attributes.find((a) => a.name === name);
  if (!moving) return null;
  const before = sortSection(
    attributes.filter((a) => a.section === moving.section && a.name !== name)
  ).filter(
    (candidate) =>
      candidate.order < moving.order ||
      (candidate.order === moving.order && candidate.name < moving.name)
  );
  return before.length ? before[before.length - 1]!.name : null;
}

/**
 * The `toIndex` (for {@link moveAttribute}) that places an attribute directly
 * behind `after` inside `section` — `after === null` means "front of the
 * section". Used by the undo path, which records an anchor rather than an index
 * (feature #1260).
 */
export function indexAfterAnchor(
  attributes: AttributeSpec[],
  name: string,
  section: string,
  after: string | null
): number {
  if (after === null) return 0;
  const target = sortSection(
    attributes.filter((a) => a.name !== name && a.section === section)
  );
  const position = target.findIndex((a) => a.name === after);
  return position === -1 ? target.length : position + 1;
}

/**
 * Move `name` to position `toIndex` within `toSection`.
 *
 * Sparse-key semantics (feature #1260), identical to the backend's `reorder`:
 * the moved attribute takes a free slot between its two new neighbours and only
 * its own `order` changes; the target section is re-spaced to multiples of
 * {@link ORDER_STEP} only when no integer slot is left.
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
  const neighbours = sortSection(
    attributes.filter((a) => a.name !== name && a.section === toSection)
  );
  const clamped = Math.max(0, Math.min(toIndex, neighbours.length));
  const previous = clamped > 0 ? neighbours[clamped - 1]!.order : null;
  const next = clamped < neighbours.length ? neighbours[clamped]!.order : null;
  const order = placeBetween(previous, next);

  if (order !== null) {
    return canonicalize(
      attributes.map((attribute) =>
        attribute.name === name
          ? { ...attribute, section: toSection, order }
          : attribute
      )
    );
  }

  // No integer slot left: the moved entry joins the section first, then the
  // whole section is re-spaced in the desired order.
  const placed = attributes.map((attribute) =>
    attribute.name === name ? { ...attribute, section: toSection } : attribute
  );
  const target = sortSection(placed.filter((a) => a.section === toSection));
  const withoutMoving = target.filter((a) => a.name !== name);
  const desired = [
    ...withoutMoving.slice(0, clamped),
    { ...moving, section: toSection },
    ...withoutMoving.slice(clamped),
  ];
  const respaced = new Map(
    desired.map((attribute, position) => [attribute.name, (position + 1) * ORDER_STEP])
  );
  return canonicalize(
    attributes.map((attribute) => {
      if (attribute.name === name) {
        return { ...attribute, section: toSection, order: respaced.get(name)! };
      }
      if (attribute.section === toSection && respaced.has(attribute.name)) {
        return { ...attribute, order: respaced.get(attribute.name)! };
      }
      return attribute;
    })
  );
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

/**
 * Post-review M6: `renameSection` only rewrites `attribute.section`, so the
 * matching `SectionSpec` has to be renamed alongside it. Without this the
 * renamed section has no spec at all and falls back to the default
 * visible/full — a deliberately hidden section silently becomes visible
 * again — while the entry under the old name survives forever as an orphan
 * that a later section of that name would silently inherit.
 *
 * Renaming ONTO an existing section name is a merge (that is what
 * `renameSection` does to the attributes): the target's own spec wins and the
 * source entry is dropped, because two entries of the same name are a
 * duplicate the backend rejects.
 */
export function renameSectionSpec(
  sections: SectionSpec[],
  from: string,
  to: string
): SectionSpec[] {
  const clean = to.trim();
  if (!clean || clean === from) return sections;
  if (!sections.some((s) => s.name === from)) return sections;
  if (sections.some((s) => s.name === clean)) {
    return sections.filter((s) => s.name !== from);
  }
  return sections.map((s) => (s.name === from ? { ...s, name: clean } : s));
}

/** Drop the `SectionSpec` of a deleted section — see {@link renameSectionSpec}
 * for why a leftover entry is not harmless. */
export function deleteSectionSpec(
  sections: SectionSpec[],
  name: string
): SectionSpec[] {
  return sections.filter((s) => s.name !== name);
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
/** Task 8: toggle one section's `visible` flag, upserting a new default
 * entry if this section has no `SectionSpec` yet (e.g. a workspace/global
 * row whose `sections` came back genuinely empty). */
export function toggleSectionVisible(sections: SectionSpec[], name: string): SectionSpec[] {
  if (sections.some((s) => s.name === name)) {
    return sections.map((s) => (s.name === name ? { ...s, visible: !s.visible } : s));
  }
  return [...sections, { name, order: sections.length, visible: false, layout: "full" }];
}

/** Task 8: set one section's `layout`, same upsert fallback as
 * {@link toggleSectionVisible}. */
export function setSectionLayout(
  sections: SectionSpec[],
  name: string,
  layout: SectionLayout
): SectionSpec[] {
  if (sections.some((s) => s.name === name)) {
    return sections.map((s) => (s.name === name ? { ...s, layout } : s));
  }
  return [...sections, { name, order: sections.length, visible: true, layout }];
}

/**
 * WS4 #938: replace one section's `attribute_flow` (the layout editor's write
 * path), same upsert fallback as {@link setSectionLayout}. The flow is the
 * editor's already-normalized effective list, so every token references a
 * real attribute of the section.
 */
export function setSectionAttributeFlow(
  sections: SectionSpec[],
  name: string,
  attributeFlow: LayoutToken[]
): SectionSpec[] {
  if (sections.some((s) => s.name === name)) {
    return sections.map((s) =>
      s.name === name ? { ...s, attribute_flow: attributeFlow } : s
    );
  }
  return [
    ...sections,
    { name, order: sections.length, visible: true, layout: "full", attribute_flow: attributeFlow },
  ];
}

export function isMetaPropertyLocked(
  attribute: AttributeSpec,
  property: keyof AttributeSpec
): boolean {
  if (attribute.kind === "core" && CORE_IMMUTABLE.has(property)) return true;
  if (attribute.locked && LOCKED_IMMUTABLE.has(property)) return true;
  return false;
}
