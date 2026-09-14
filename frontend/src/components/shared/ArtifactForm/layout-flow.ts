/**
 * 12-column layout engine — pure, shared by the renderer and the editor
 * (Attribut v3 WS4 #938, spec section 7).
 *
 * The backend owns the vocabulary (`attribute_definitions/schema.py`:
 * `GRID_COLUMNS`, `SPAN_COLUMNS`, `SECTION_SPAN_COLUMNS`, `SPACER_COLUMNS`,
 * `materialize_section_flow`, `materialize_attribute_flow`,
 * `effective_section_flow`, `effective_attribute_flow`). These helpers mirror
 * that logic client-side so the renderer and the layout editor derive the
 * SAME default a backend consumer would: a definition without a flow renders
 * exactly as it did before this engine existed.
 *
 * Both `undefined` (no stored flow) and `[]` (a genuinely empty stored flow)
 * are legal inputs, and they are NOT equivalent: `undefined` derives the
 * order-based default, while `[]` is a real stored value that positions no
 * token (the backend's `effective_*` return a stored `[]` verbatim). Callers
 * that write a flow back must preserve that distinction (`undefined` omits the
 * key), which is why the mutators below accept and return
 * `LayoutToken[] | undefined`.
 */

import type {
  AttributeSpan,
  AttributeSpec,
  LayoutToken,
  SectionLayout,
  SectionSpec,
  SpacerSize,
} from "../../../api/attribute-definitions";

/** Column count every span/spacer resolves inside (spec section 7). */
export const GRID_COLUMNS = 12;

/** `span` token -> columns (`full`=12, `half`=6, `quarter`=3). */
export const SPAN_COLUMNS: Record<AttributeSpan, number> = {
  full: 12,
  half: 6,
  quarter: 3,
};

/** A section's own width (`layout`) on the same 12 columns. */
export const SECTION_LAYOUT_COLUMNS: Record<SectionLayout, number> = {
  full: 12,
  half: 6,
};

/** `spacer.size` -> columns (`sm`=1, `md`=2, `lg`=4). */
export const SPACER_COLUMNS: Record<SpacerSize, number> = {
  sm: 1,
  md: 2,
  lg: 4,
};

export const ATTRIBUTE_SPANS: readonly AttributeSpan[] = ["full", "half", "quarter"];
export const SPACER_SIZES: readonly SpacerSize[] = ["sm", "md", "lg"];
export const SECTION_LAYOUTS: readonly SectionLayout[] = ["full", "half"];

/** The default span of an attribute token that omits one — mirrors the
 * backend's `_DEFAULT_ATTRIBUTE_SPAN` and therefore the pre-WS4 rendering. */
export const DEFAULT_ATTRIBUTE_SPAN: AttributeSpan = "full";

export interface ResolvedAttributeEntry {
  kind: "attribute";
  attribute: AttributeSpec;
  span: AttributeSpan;
  columns: number;
}

export interface ResolvedSpacerEntry {
  kind: "spacer";
  size: SpacerSize;
  columns: number;
}

export type ResolvedFlowEntry = ResolvedAttributeEntry | ResolvedSpacerEntry;

export function attributeSpanColumns(span: AttributeSpan | undefined): number {
  return SPAN_COLUMNS[span ?? DEFAULT_ATTRIBUTE_SPAN] ?? GRID_COLUMNS;
}

export function sectionLayoutColumns(layout: SectionLayout | undefined): number {
  return SECTION_LAYOUT_COLUMNS[layout ?? "full"] ?? GRID_COLUMNS;
}

export function spacerColumns(size: SpacerSize | undefined): number {
  return SPACER_COLUMNS[size ?? "md"] ?? SPACER_COLUMNS.md;
}

/**
 * CSS-module span class suffix for `columns`, clamped to the grid: 1..12.
 * The renderer maps it through `styles[\`span${suffix}\`]` — CSS owns the
 * actual `grid-column` declaration so there is no inline style.
 */
export function spanClassSuffix(columns: number): number {
  return Math.max(1, Math.min(GRID_COLUMNS, Math.round(columns)));
}

function isAttributeToken(
  token: LayoutToken
): token is Extract<LayoutToken, { kind: "attribute" }> {
  return token.kind === "attribute";
}

function isSectionToken(
  token: LayoutToken
): token is Extract<LayoutToken, { kind: "section" }> {
  return token.kind === "section";
}

/**
 * Derive the default `section_flow` from a section-name list: one section
 * token per name in order, no spacers (the backend's
 * `materialize_section_flow`).
 */
export function materializeSectionFlow(sectionNames: string[]): LayoutToken[] {
  return sectionNames.map((name) => ({ kind: "section", name }));
}

/**
 * Derive the default `attribute_flow` from an attribute list: one
 * full-span attribute token per attribute in order (the backend's
 * `materialize_attribute_flow`).
 */
export function materializeAttributeFlow(attributes: AttributeSpec[]): LayoutToken[] {
  return attributes.map((attribute) => ({
    kind: "attribute",
    name: attribute.name,
    span: DEFAULT_ATTRIBUTE_SPAN,
  }));
}

/**
 * The ordered section tokens a renderer/editor should use for *sectionNames*.
 *
 * `undefined` (no stored flow) derives the default: one section token per name
 * in *sectionNames* order, no spacers.
 *
 * A stored flow — including the explicitly empty `[]` — is used as-is: its
 * section tokens in their stored order, spacers kept, tokens naming an
 * unknown/duplicate section dropped. An explicitly empty stored flow therefore
 * positions NO section and must not fall back to the default derivation
 * (mirrors the backend's `effective_section_flow`, which returns a stored `[]`
 * verbatim). For a non-empty stored flow, sections not positioned by it are
 * appended in *sectionNames* order — a stale flow must never make a section
 * disappear (additive derivation, spec section 7).
 */
export function orderedSectionTokens(
  flow: LayoutToken[] | undefined,
  sectionNames: string[]
): LayoutToken[] {
  if (flow === undefined) return materializeSectionFlow(sectionNames);
  const known = new Set(sectionNames);
  const seen = new Set<string>();
  const tokens: LayoutToken[] = [];
  for (const token of flow) {
    if (isSectionToken(token)) {
      if (!known.has(token.name) || seen.has(token.name)) continue;
      seen.add(token.name);
      tokens.push(token);
    } else if (token.kind === "spacer") {
      tokens.push(token);
    }
  }
  // An explicitly empty stored flow positions nothing — do not derive.
  if (flow.length === 0) return tokens;
  for (const name of sectionNames) {
    if (!seen.has(name)) tokens.push({ kind: "section", name });
  }
  return tokens;
}

/**
 * The ordered attribute tokens for one section — mirrors
 * `orderedSectionTokens` one level down (the backend's
 * `effective_attribute_flow`), with `span` defaulted to `full` on every
 * attribute token and, for a non-empty stored flow, unpositioned attributes
 * appended in *attributes* order.
 *
 * `undefined` (the section carries no `attribute_flow` key) derives the
 * default: every attribute at full span. An explicitly empty stored flow `[]`
 * positions no attribute and must not fall back to that derivation — only the
 * absence of the key is a "derive" signal.
 */
export function effectiveAttributeFlowTokens(
  section: SectionSpec | undefined,
  attributes: AttributeSpec[]
): LayoutToken[] {
  const flow = section?.attribute_flow;
  if (flow === undefined) return materializeAttributeFlow(attributes);
  const known = new Set(attributes.map((attribute) => attribute.name));
  const seen = new Set<string>();
  const tokens: LayoutToken[] = [];
  for (const token of flow) {
    if (isAttributeToken(token)) {
      if (!known.has(token.name) || seen.has(token.name)) continue;
      seen.add(token.name);
      tokens.push({ ...token, span: token.span ?? DEFAULT_ATTRIBUTE_SPAN });
    } else if (token.kind === "spacer") {
      tokens.push(token);
    }
  }
  // An explicitly empty stored flow positions nothing — do not derive.
  if (flow.length === 0) return tokens;
  for (const attribute of attributes) {
    if (!seen.has(attribute.name)) {
      tokens.push({
        kind: "attribute",
        name: attribute.name,
        span: DEFAULT_ATTRIBUTE_SPAN,
      });
    }
  }
  return tokens;
}

/**
 * The renderer's enriched, ordered attribute flow for one section: the
 * effective tokens resolved against the actual `AttributeSpec` objects, so
 * each entry already carries its column count.
 */
export function resolveAttributeFlow(
  section: SectionSpec | undefined,
  attributes: AttributeSpec[]
): ResolvedFlowEntry[] {
  const byName = new Map(attributes.map((attribute) => [attribute.name, attribute]));
  const entries: ResolvedFlowEntry[] = [];
  for (const token of effectiveAttributeFlowTokens(section, attributes)) {
    if (isAttributeToken(token)) {
      const attribute = byName.get(token.name);
      if (!attribute) continue;
      const span = token.span ?? DEFAULT_ATTRIBUTE_SPAN;
      entries.push({
        kind: "attribute",
        attribute,
        span,
        columns: attributeSpanColumns(span),
      });
    } else if (token.kind === "spacer") {
      const size = token.size in SPACER_COLUMNS ? token.size : ("md" as SpacerSize);
      entries.push({ kind: "spacer", size, columns: spacerColumns(size) });
    }
  }
  return entries;
}

/* ------------------------------------------------------------------------- */
/* Consistency maintenance (scope rule 5)                                    */
/* ------------------------------------------------------------------------- */

/** Only defined when there is at least one section name to validate against —
 * an empty name list means "no information", not "everything is stale", so a
 * flow is preserved rather than wiped. */
export function pruneSectionFlow(
  flow: LayoutToken[] | undefined,
  sectionNames: string[]
): LayoutToken[] | undefined {
  if (flow === undefined || sectionNames.length === 0) return flow;
  const known = new Set(sectionNames);
  return flow.filter((token) => !isSectionToken(token) || known.has(token.name));
}

/** Drop attribute tokens naming an attribute that no longer exists (e.g.
 * after an immediate attribute delete); spacers and attribute-less sections
 * are untouched. Also a no-op when *attributeNames* is empty. */
export function pruneAttributeFlows(
  sections: SectionSpec[],
  attributeNames: string[]
): SectionSpec[] {
  if (attributeNames.length === 0) return sections;
  const known = new Set(attributeNames);
  return sections.map((section) =>
    section.attribute_flow === undefined
      ? section
      : {
          ...section,
          attribute_flow: section.attribute_flow.filter(
            (token) => !isAttributeToken(token) || known.has(token.name)
          ),
        }
  );
}

/** Rename a section token. Renaming ONTO an existing section drops the source
 * token instead (the target's own position wins) — the same merge semantics
 * `renameSectionSpec` applies to the `SectionSpec` list. */
export function renameSectionToken(
  flow: LayoutToken[] | undefined,
  from: string,
  to: string
): LayoutToken[] | undefined {
  if (flow === undefined) return undefined;
  const clean = to.trim();
  if (!clean || clean === from) return flow;
  const targetExists = flow.some(
    (token) => isSectionToken(token) && token.name === clean
  );
  if (targetExists) {
    return flow.filter((token) => !(isSectionToken(token) && token.name === from));
  }
  return flow.map((token) =>
    isSectionToken(token) && token.name === from ? { ...token, name: clean } : token
  );
}

/** Remove a deleted section's token, keeping every spacer. */
export function deleteSectionToken(
  flow: LayoutToken[] | undefined,
  name: string
): LayoutToken[] | undefined {
  if (flow === undefined) return undefined;
  return flow.filter((token) => !(isSectionToken(token) && token.name === name));
}

/* ------------------------------------------------------------------------- */
/* Editor mutations                                                           */
/* ------------------------------------------------------------------------- */

/** Move the token at `from` to `to`, clamped, returning a new list. */
export function moveToken(
  flow: LayoutToken[],
  from: number,
  to: number
): LayoutToken[] {
  if (from < 0 || from >= flow.length) return flow;
  const next = [...flow];
  const [moved] = next.splice(from, 1);
  next.splice(Math.max(0, Math.min(to, next.length)), 0, moved);
  return next;
}

export function removeToken(flow: LayoutToken[], index: number): LayoutToken[] {
  return flow.filter((_, i) => i !== index);
}

export function replaceToken(
  flow: LayoutToken[],
  index: number,
  token: LayoutToken
): LayoutToken[] {
  return flow.map((current, i) => (i === index ? token : current));
}
