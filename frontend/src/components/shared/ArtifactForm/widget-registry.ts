/**
 * Widget registry (spec section 6.3).
 *
 * A `type: "widget"` attribute names a `widget_key`; this map turns that key
 * into a component. Deliberately an open extension point: a new special case
 * discovered during the form rollout adds a key here and to
 * `attribute_definitions/schema.py::WIDGET_KEYS`, instead of weakening the
 * renderer's field contract.
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

export const WIDGET_REGISTRY: Record<WidgetKey, (props: WidgetProps) => JSX.Element> = {
  risk_matrix_rpz: RiskMatrixRpz,
  markdown_tab_group: MarkdownTabGroup,
  steps_editor: StepsEditor,
};

export { computeRpn, RISK_IMPACT_SCORE, RISK_PROBABILITY_SCORE } from "./widgets/RiskMatrixRpz";
