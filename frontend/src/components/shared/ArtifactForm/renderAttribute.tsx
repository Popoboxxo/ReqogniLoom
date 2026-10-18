/**
 * Per-attribute renderer of the definition-driven artifact form.
 *
 * Extracted from `ArtifactForm.tsx` (Phase 5b decomposition, FE-01 / F-01).
 * Pure presentational dispatch: given one `AttributeSpec` and the current form
 * values/errors, it returns the control, the display engine, the workflow
 * status editor or the widget that draws it. No state of its own.
 */

import type { AttributeSpec } from "../../../api/attribute-definitions";
import type { WorkflowArtifactType } from "../../../api/workflow-transitions";
import { RevealValue } from "../RevealValue";
import { WorkflowStatusEditor } from "../../WorkflowStatusEditor";
import styles from "./ArtifactForm.module.css";
import {
  BooleanToggle,
  CriteriaList,
  DateField,
  DisplayField,
  EnumSelect,
  MultiEnum,
  NumberField,
  ReferencePicker,
  TextArea,
  TextField,
  UserPicker,
  ActorPicker,
  attributeLabel,
  hasConfiguredDisplay,
  resolveDisplayProps,
  type ActorFieldValue,
  type CriteriaItem,
} from "./fields";
import type { ArtifactFormValues } from "./artifact-form-types";
import { readValue } from "./form-helpers";
import { resolveWidget } from "./widget-registry";

interface RenderArgs {
  attribute: AttributeSpec;
  values: ArtifactFormValues;
  fieldErrors: Record<string, string[]>;
  specByName: Map<string, AttributeSpec>;
  disabled: boolean;
  /** `data-testid` for the control — defaults to `artifact-field-<name>`. */
  testId: string;
  /**
   * `true` when the attribute is shown outside an editable context (read mode
   * or a non-editable policy) — the trigger for the generic display path.
   * Separate from `disabled` because `saving` also disables controls without
   * changing how a configured value should be rendered.
   */
  displayOnly: boolean;
  /** Active UI language — needed by the `system` static-text branch. */
  language: string;
  /** Rendered for an empty `system` attribute value. */
  systemUnsetLabel: string;
  artifactId: string | null;
  workflowArtifactType?: WorkflowArtifactType;
  unsupportedLabel: string;
  update: (attribute: AttributeSpec, next: unknown) => void;
}

export function renderAttribute({
  attribute,
  values,
  fieldErrors,
  specByName,
  disabled,
  testId,
  displayOnly,
  language,
  systemUnsetLabel,
  artifactId,
  workflowArtifactType,
  unsupportedLabel,
  update,
}: RenderArgs): JSX.Element | null {
  const errors = fieldErrors[attribute.name];

  // Rule 3b (Attribut v3 WS2, #936): a `system` attribute is server-owned —
  // the Artifact's own `id` is the carrier. It is NEVER an editable control:
  // it renders through the generic `<RevealValue>` display engine, so the WS3
  // (#937) display properties (`reveal="click"`, `copyable`, `mask="short"`)
  // take effect here too.
  //
  // Checked BEFORE the `workflow` comparison on purpose: comparing against the
  // first string literal narrows `editable` to its remaining string member, so
  // a `=== "system"` test placed after it would (correctly, but unhelpfully)
  // be reported as having no overlap with the narrowed `boolean | "system"`.
  if (attribute.editable === "system") {
    const current = readValue(values, attribute);
    const hasValue = current != null && current !== "";
    const display = resolveDisplayProps(attribute);
    return (
      <div key={attribute.name} className={styles.field}>
        <span className={styles.label} id={`${testId}-label`}>
          {attributeLabel(attribute, language)}
        </span>
        <RevealValue
          value={hasValue ? String(current) : null}
          fallback={systemUnsetLabel}
          copyValue={hasValue ? String(current) : null}
          displayFormat={display.displayFormat}
          reveal={display.reveal}
          mask={display.mask}
          copyable={display.copyable && hasValue}
          label={attributeLabel(attribute, language)}
          testId={testId}
        />
      </div>
    );
  }

  // Rule 3: a workflow-owned attribute is never an editable control. In create
  // mode there is no artifact to transition yet, so it is not rendered at all —
  // the backend assigns the initial state.
  if (attribute.editable === "workflow") {
    if (!workflowArtifactType || !artifactId) return null;
    const current = readValue(values, attribute);
    return (
      <WorkflowStatusEditor
        key={attribute.name}
        artifactType={workflowArtifactType}
        artifactId={artifactId}
        currentStatus={typeof current === "string" ? current : undefined}
        disabled={disabled}
      />
    );
  }

  if (attribute.type === "widget") {
    const Widget = resolveWidget(attribute);
    if (!Widget) {
      // Unknown `widget_key`, or one whose `fields` it cannot render. Both are
      // reachable through the unenforced `/attribute-defaults/` PUT, so this
      // must be a visible message rather than `null`: the fields are still
      // rendered individually (see `widgetOwned`), and an admin gets told which
      // widget is misconfigured instead of wondering why a save 400s.
      return (
        <div
          key={attribute.name}
          className={styles.errors}
          role="alert"
          data-testid={`artifact-widget-unsupported-${attribute.name}`}
        >
          {unsupportedLabel}
        </div>
      );
    }
    const boundValues: Record<string, unknown> = {};
    const boundErrors: Record<string, string[]> = {};
    for (const name of attribute.fields) {
      const bound = specByName.get(name);
      boundValues[name] = bound ? readValue(values, bound) : values[name];
      if (fieldErrors[name]) boundErrors[name] = fieldErrors[name];
    }
    return (
      <Widget
        key={attribute.name}
        attribute={attribute}
        values={boundValues}
        onChange={(fieldName, next) =>
          update(
            specByName.get(fieldName) ?? { ...attribute, name: fieldName, kind: "core" },
            next
          )
        }
        disabled={disabled}
        errors={boundErrors}
        testId={`artifact-widget-${attribute.name}`}
        artifactId={artifactId}
      />
    );
  }

  // Rule 4 (Attribut v3 WS3, #937): an attribute with at least one NON-default
  // display property (copyable/reveal/mask/display_format) is rendered through
  // the generic display engine whenever the field is not editable. An
  // attribute without special properties falls straight through to its
  // ordinary control below and keeps rendering exactly as before — the
  // "kein Big-Bang, Defaults verhalten sich wie vorher" requirement.
  const display = resolveDisplayProps(attribute);
  if (displayOnly && hasConfiguredDisplay(display)) {
    return (
      <DisplayField
        key={attribute.name}
        attribute={attribute}
        value={readValue(values, attribute)}
        errors={errors}
        testId={testId}
      />
    );
  }

  const shared = {
    attribute,
    disabled,
    errors,
    testId,
  } as const;
  const value = readValue(values, attribute);
  const onChange = (next: unknown): void => update(attribute, next);

  switch (attribute.type) {
    case "textarea":
      return <TextArea key={attribute.name} {...shared} value={value as string | null} onChange={onChange} />;
    case "number":
      return <NumberField key={attribute.name} {...shared} value={value as number | null} onChange={onChange} />;
    case "boolean":
      return <BooleanToggle key={attribute.name} {...shared} value={value as boolean | null} onChange={onChange} />;
    case "enum":
      return <EnumSelect key={attribute.name} {...shared} value={value as string | null} onChange={onChange} />;
    case "multi-enum":
      return <MultiEnum key={attribute.name} {...shared} value={value as string[] | null} onChange={onChange} />;
    case "criteria-list":
      // #1288: ordered, individually check-off-able criteria.
      return (
        <CriteriaList
          key={attribute.name}
          {...shared}
          value={value as CriteriaItem[] | null}
          onChange={onChange}
        />
      );
    case "date":
      return <DateField key={attribute.name} {...shared} value={value as string | null} onChange={onChange} />;
    case "reference":
      return <ReferencePicker key={attribute.name} {...shared} value={value as string | null} onChange={onChange} />;
    case "user":
      return <UserPicker key={attribute.name} {...shared} value={value as string | null} onChange={onChange} />;
    case "actor":
      // Attribut v3 WS2 (#936): `multiple` selects between the single entry
      // form (`{kind, id|name}`) and the `{multiple: true, items: [...]}` form;
      // `allow_external` gates the "create as external person" affordance.
      // Both are read from the attribute, never guessed here.
      return (
        <ActorPicker
          key={attribute.name}
          {...shared}
          value={value as ActorFieldValue}
          onChange={onChange}
        />
      );
    default:
      return <TextField key={attribute.name} {...shared} value={value as string | null} onChange={onChange} />;
  }
}
