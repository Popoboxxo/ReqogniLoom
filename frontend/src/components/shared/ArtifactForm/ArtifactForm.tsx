/**
 * Definition-driven artifact form (spec section 6).
 *
 * Replaces the seven hand-written forms. Everything it draws comes from the
 * resolved attribute definition: sections and their order, fields and their
 * order, labels, help text, requiredness, enum options, widgets and the
 * default expand density (`audience`).
 *
 * Parity policy (spec section 6.3): dirty warning, delete-in-form, status as
 * badge + transition buttons and definition-driven visibility are available for
 * EVERY type here — the migration unifies upward onto the best behaviour any of
 * the seven forms had, it never cuts one.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { AlertCircle, ChevronDown, ChevronRight } from "lucide-react";

import type {
  AttributeAudience,
  AttributeItemType,
  AttributeSpec,
} from "../../../api/attribute-definitions";
import { extractErrorMessage } from "../../../api/client";
import type { WorkflowArtifactType } from "../../../api/workflow-transitions";
import { useFormDirty } from "../../../hooks/use-form-dirty";
import { ConfirmDialog } from "../ConfirmDialog";
import { WorkflowStatusEditor } from "../../WorkflowStatusEditor";
import styles from "./ArtifactForm.module.css";
import { fieldErrorsFromException } from "./field-errors";
import {
  BooleanToggle,
  DateField,
  EnumSelect,
  MultiEnum,
  NumberField,
  ReferencePicker,
  TextArea,
  TextField,
  UserPicker,
} from "./fields";
import { useArtifactDefinition } from "./useArtifactDefinition";
import { resolveWidget } from "./widget-registry";

export interface ArtifactFormValues {
  [name: string]: unknown;
  custom_fields?: Record<string, unknown>;
}

export interface ArtifactFormProps {
  /** Attribute-definition item type, e.g. "Risk". */
  itemType: AttributeItemType;
  /** `null` = create mode: no delete affordance, no workflow status editor. */
  artifactId: string | null;
  initialValues: ArtifactFormValues;
  onSave: (values: ArtifactFormValues) => Promise<void>;
  onDelete?: () => Promise<void>;
  onDirtyChange?: (isDirty: boolean) => void;
  /** `"read"` disables every control (Rollenbasierte-Sichten spec). */
  mode?: "edit" | "read";
  /** Enables the workflow status editor for `editable: "workflow"` attributes. */
  workflowArtifactType?: WorkflowArtifactType;
}

export interface FormSection {
  name: string;
  audience: AttributeAudience;
  attributes: AttributeSpec[];
}

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

function readValue(values: ArtifactFormValues, attribute: AttributeSpec): unknown {
  return attribute.kind === "extended"
    ? (values.custom_fields ?? {})[attribute.name]
    : values[attribute.name];
}

function writeValue(
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

export function ArtifactForm({
  itemType,
  artifactId,
  initialValues,
  onSave,
  onDelete,
  onDirtyChange,
  mode = "edit",
  workflowArtifactType,
}: ArtifactFormProps): JSX.Element {
  const { t } = useTranslation();
  const { definition, loading, error: loadError } = useArtifactDefinition(itemType);
  const [values, setValues] = useState<ArtifactFormValues>(initialValues);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});

  const { isDirty, markClean } = useFormDirty(values, initialValues);
  const isReadOnly = mode === "read";

  // `initialValues` is an object prop and every realistic call site builds it
  // inline from the fetched artifact, so its IDENTITY changes on every parent
  // render. Re-anchoring on identity would discard whatever the user has typed
  // whenever the parent re-renders for an unrelated reason; the serialized
  // value is the only signal that the edited artifact actually changed.
  const initialSignature = JSON.stringify(initialValues);
  const initialRef = useRef(initialValues);
  initialRef.current = initialValues;

  useEffect(() => {
    setValues(initialRef.current);
    markClean(initialRef.current);
    // A rejected save's errors belong to the artifact that was open at the
    // time. The rollout waves reuse one mounted form across a list selection,
    // so leaving them would pin a red "title: is required" onto the next
    // artifact the user clicks.
    setFieldErrors({});
    setFormError(null);
  }, [artifactId, initialSignature, markClean]);

  useEffect(() => {
    onDirtyChange?.(isDirty);
  }, [isDirty, onDirtyChange]);

  const visible = useMemo(
    () => (definition?.attributes ?? []).filter((a) => a.visible),
    [definition]
  );

  const specByName = useMemo(() => {
    const map = new Map<string, AttributeSpec>();
    for (const attribute of definition?.attributes ?? []) map.set(attribute.name, attribute);
    return map;
  }, [definition]);

  // Rule 2: a field a widget draws is not rendered on its own. Only a widget we
  // can ACTUALLY render claims its fields — an unknown `widget_key` or a
  // `fields`/`widget_key` mismatch (which the backend does not prevent, see
  // `resolveWidget`) would otherwise suppress controls with nothing drawing
  // them, turning a definition typo into silently uneditable data.
  const widgetOwned = useMemo(() => {
    const owned = new Set<string>();
    for (const attribute of visible) {
      if (attribute.type === "widget" && resolveWidget(attribute)) {
        attribute.fields.forEach((name) => owned.add(name));
      }
    }
    return owned;
  }, [visible]);

  const sections = useMemo(
    () => groupIntoSections(visible.filter((a) => !widgetOwned.has(a.name))),
    [visible, widgetOwned]
  );

  const isSectionOpen = useCallback(
    (section: FormSection): boolean => {
      if (section.name in expanded) return expanded[section.name];
      // Rule 5: an error anywhere in the section forces it open so the message
      // is reachable without hunting. A widget's errors belong to its bound
      // fields, which live in the same section by construction.
      if (section.attributes.some((a) => fieldErrors[a.name]?.length)) return true;
      if (
        section.attributes.some((a) =>
          a.fields.some((name) => fieldErrors[name]?.length)
        )
      ) {
        return true;
      }
      return section.audience !== "expert";
    },
    [expanded, fieldErrors]
  );

  const update = useCallback((attribute: AttributeSpec, next: unknown): void => {
    setValues((current) => writeValue(current, attribute, next));
  }, []);

  const handleSave = useCallback(async (): Promise<void> => {
    setSaving(true);
    setFormError(null);
    setFieldErrors({});
    try {
      await onSave(values);
      markClean(values);
    } catch (exc: unknown) {
      const message = extractErrorMessage(exc);
      const parsed = fieldErrorsFromException(exc, message);
      setFieldErrors(parsed);
      if (!Object.keys(parsed).length) setFormError(message);
    } finally {
      setSaving(false);
    }
  }, [markClean, onSave, values]);

  const handleDelete = useCallback(async (): Promise<void> => {
    if (!onDelete) return;
    try {
      await onDelete();
      setConfirmDelete(false);
    } catch (exc: unknown) {
      setConfirmDelete(false);
      setFormError(extractErrorMessage(exc));
    }
  }, [onDelete]);

  if (loading) {
    return <div data-testid="artifact-form-loading" aria-busy="true" />;
  }
  if (loadError || !definition) {
    return (
      <div className={styles.errors} role="alert" data-testid="artifact-form-load-error">
        <AlertCircle aria-hidden="true" size={16} />
        {loadError ?? t("artifactForm.definitionUnavailable")}
      </div>
    );
  }

  return (
    <form
      className={styles.form}
      data-testid="artifact-form"
      onSubmit={(event) => {
        event.preventDefault();
        void handleSave();
      }}
    >
      {formError ? (
        <div className={styles.errors} role="alert" data-testid="artifact-form-error">
          {formError}
        </div>
      ) : null}

      {sections.map((section) => {
        const open = isSectionOpen(section);
        return (
          <section key={section.name} className={styles.section}>
            <button
              type="button"
              className={styles.sectionHeader}
              data-testid={`artifact-section-toggle-${section.name}`}
              aria-expanded={open}
              aria-label={t(
                open ? "artifactForm.collapseSection" : "artifactForm.expandSection",
                { section: t(`sections.${section.name}`, { defaultValue: section.name }) }
              )}
              onClick={() =>
                setExpanded((current) => ({ ...current, [section.name]: !open }))
              }
            >
              <span>{t(`sections.${section.name}`, { defaultValue: section.name })}</span>
              {open ? (
                <ChevronDown aria-hidden="true" size={16} />
              ) : (
                <ChevronRight aria-hidden="true" size={16} />
              )}
            </button>

            {open ? (
              <div className={styles.sectionBody}>
                {section.attributes.map((attribute) =>
                  renderAttribute({
                    attribute,
                    values,
                    fieldErrors,
                    specByName,
                    disabled: isReadOnly || attribute.editable === false || saving,
                    artifactId,
                    workflowArtifactType,
                    unsupportedLabel: t("artifactForm.unsupportedWidget", {
                      widget: attribute.widget_key ?? "",
                    }),
                    update,
                  })
                )}
              </div>
            ) : null}
          </section>
        );
      })}

      {!isReadOnly ? (
        <div className={styles.actions}>
          {onDelete ? (
            <button
              type="button"
              data-testid="artifact-form-delete"
              disabled={saving}
              onClick={() => setConfirmDelete(true)}
            >
              {t("actions.delete")}
            </button>
          ) : null}
          <button type="submit" data-testid="artifact-form-save" disabled={saving}>
            {saving ? t("actions.saving") : t("actions.save")}
          </button>
        </div>
      ) : null}

      {confirmDelete ? (
        <ConfirmDialog
          title={t("artifactForm.deleteTitle")}
          message={t("artifactForm.deleteConfirm")}
          confirmLabel={t("actions.delete")}
          cancelLabel={t("actions.cancel")}
          testId="artifact-form-delete-dialog"
          confirmTestId="artifact-form-delete-confirm"
          cancelTestId="artifact-form-delete-cancel"
          onConfirm={() => void handleDelete()}
          onCancel={() => setConfirmDelete(false)}
        />
      ) : null}
    </form>
  );
}

interface RenderArgs {
  attribute: AttributeSpec;
  values: ArtifactFormValues;
  fieldErrors: Record<string, string[]>;
  specByName: Map<string, AttributeSpec>;
  disabled: boolean;
  artifactId: string | null;
  workflowArtifactType?: WorkflowArtifactType;
  unsupportedLabel: string;
  update: (attribute: AttributeSpec, next: unknown) => void;
}

function renderAttribute({
  attribute,
  values,
  fieldErrors,
  specByName,
  disabled,
  artifactId,
  workflowArtifactType,
  unsupportedLabel,
  update,
}: RenderArgs): JSX.Element | null {
  const testId = `artifact-field-${attribute.name}`;
  const errors = fieldErrors[attribute.name];

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
      />
    );
  }

  const shared = {
    key: attribute.name,
    attribute,
    disabled,
    errors,
    testId,
  } as const;
  const value = readValue(values, attribute);
  const onChange = (next: unknown): void => update(attribute, next);

  switch (attribute.type) {
    case "textarea":
      return <TextArea {...shared} value={value as string | null} onChange={onChange} />;
    case "number":
      return <NumberField {...shared} value={value as number | null} onChange={onChange} />;
    case "boolean":
      return <BooleanToggle {...shared} value={value as boolean | null} onChange={onChange} />;
    case "enum":
      return <EnumSelect {...shared} value={value as string | null} onChange={onChange} />;
    case "multi-enum":
      return <MultiEnum {...shared} value={value as string[] | null} onChange={onChange} />;
    case "date":
      return <DateField {...shared} value={value as string | null} onChange={onChange} />;
    case "reference":
      return <ReferencePicker {...shared} value={value as string | null} onChange={onChange} />;
    case "user":
      return <UserPicker {...shared} value={value as string | null} onChange={onChange} />;
    default:
      return <TextField {...shared} value={value as string | null} onChange={onChange} />;
  }
}
