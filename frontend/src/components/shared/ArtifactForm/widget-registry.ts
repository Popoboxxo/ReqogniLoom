/**
 * Widget registry (spec section 6.3).
 *
 * A `type: "widget"` attribute names a `widget_key`; this map turns that key
 * into a component. Deliberately an open extension point: a new special case
 * discovered during the form rollout adds a key here and to
 * `attribute_definitions/schema.py::WIDGET_KEYS`, instead of weakening the
 * renderer's field contract.
 *
 * The map is `Partial<...>` on purpose. `Record<WidgetKey, ...>` claims every
 * registered key has a component, which is a lie the moment the backend's
 * `WIDGET_KEYS` grows a key this frontend build predates (or an older frontend
 * is served against a newer backend). Under the total type the renderer would
 * hand React `undefined` as an element type and take the ENTIRE form tree down
 * with an unrecovered error; under `Partial` the lookup is `| undefined` and
 * the caller is forced to handle the miss — see `resolveWidget`.
 */

import type { AttributeSpec, WidgetKey } from "../../../api/attribute-definitions";
import { MarkdownTabGroup } from "./widgets/MarkdownTabGroup";
import { RiskMatrixRpz } from "./widgets/RiskMatrixRpz";
import { StepsEditor } from "./widgets/StepsEditor";

export interface WidgetProps {
  attribute: AttributeSpec;
  /** Values of the attributes named in `attribute.fields`, keyed by name. */
  values: Record<string, unknown>;
  onChange: (fieldName: string, next: unknown) => void;
  disabled: boolean;
  errors?: Record<string, string[]>;
  /** `artifact-widget-<attribute.name>`. */
  testId: string;
}

export type WidgetComponent = (props: WidgetProps) => JSX.Element;

export const WIDGET_REGISTRY: Partial<Record<WidgetKey, WidgetComponent>> = {
  risk_matrix_rpz: RiskMatrixRpz,
  markdown_tab_group: MarkdownTabGroup,
  steps_editor: StepsEditor,
};

/** Field names `RiskMatrixRpz` hardcodes (it ignores `attribute.fields`). */
const RISK_MATRIX_FIELDS = ["probability", "impact", "detection"] as const;

/**
 * Whether a widget can actually render the `fields[]` an admin bound to it.
 *
 * The backend does NOT enforce that a widget attribute's `fields` match its
 * `widget_key`: `validate_meta_only_change` never consults
 * `CORE_EDITABLE_META_PROPERTIES`, so a tenant admin can freely swap either
 * half of the pair through `PUT /attribute-defaults/…` (proven live during the
 * Task 17 review). Two concrete, reachable mismatches:
 *
 * - `steps_editor` pointed at Risk's `["probability", "impact", "detection"]`:
 *   the widget only ever touches `fields[0]`, so `impact`/`detection` would be
 *   suppressed as "a widget draws them" while nothing draws them — silently
 *   uneditable data — and writing `probability` as a step list is rejected 400.
 * - `risk_matrix_rpz` pointed at Adr's `["description", "context",
 *   "consequences"]`: the widget writes the three names it hardcodes, none of
 *   which exist on Adr (400), while the three real markdown fields become
 *   unreachable.
 *
 * Neither mismatch crashes, which is exactly why it needs a check: it degrades
 * to a rejected save with no explanation. A widget that fails its contract is
 * not rendered at all and its bound fields fall back to their individual
 * controls, so the data stays editable while an admin fixes the definition.
 */
export const WIDGET_FIELD_CONTRACTS: Partial<
  Record<WidgetKey, (fields: string[]) => boolean>
> = {
  // Hardcodes its three field names; anything else is unrenderable.
  risk_matrix_rpz: (fields) => RISK_MATRIX_FIELDS.every((name) => fields.includes(name)),
  // Fields-driven: one tab per bound field, so any non-empty list renders.
  markdown_tab_group: (fields) => fields.length > 0,
  // Reads `fields[0]` only; extra fields would be hidden AND uneditable.
  steps_editor: (fields) => fields.length === 1,
};

/**
 * The component for `attribute`, or `null` when the definition cannot be
 * rendered as a widget — unknown/absent `widget_key`, or a `fields` list the
 * widget cannot honour.
 */
export function resolveWidget(attribute: AttributeSpec): WidgetComponent | null {
  const key = attribute.widget_key;
  if (!key) return null;
  const component = WIDGET_REGISTRY[key];
  const isCompatible = WIDGET_FIELD_CONTRACTS[key];
  if (!component || !isCompatible) return null;
  return isCompatible(attribute.fields) ? component : null;
}

export { computeRpn, RISK_IMPACT_SCORE, RISK_PROBABILITY_SCORE } from "./widgets/RiskMatrixRpz";
