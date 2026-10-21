/**
 * ARCH-L1-001 ReactFrontend — DiagramCreateForm (Presenter).
 *
 * leaf_id: COMP-RF-005 (DiagramView)
 * req_id:  REQ-L2-DS-001 (DiagramService REST API),
 *          REQ-050 (Container/Presenter decomposition)
 *
 * Right-panel create form for a new diagram. Owns only the form field state;
 * the create request goes through useCreateDiagram (TanStack Query mutation).
 */

import { useState, type RefObject } from "react";
import { useTranslation } from "react-i18next";
import { useWorkspace } from "../../context/WorkspaceContext";
import { FormField } from "../shared/FormField";
import { useFieldContract } from "../../hooks/useFieldContract";
import { useCreateDiagram } from "./useDiagramData";
import {
  DEFAULT_CONTENT,
  DIAGRAM_TYPES,
  EMPTY_FORM,
  PAYLOAD_FORMATS,
  type FormState,
} from "./diagram-view-shared";
import type { DiagramType, PayloadFormat } from "../../types";
import styles from "./DiagramCreateForm.module.css";

export interface DiagramCreateFormProps {
  onCreated: (diagramId: string) => Promise<void> | void;
  onCancel: () => void;
  // F-08 (Dialog migration): lets the caller wire this form's name input up
  // as a Dialog's `initialFocusRef`, so the pre-existing autoFocus UX
  // survives being wrapped in Dialog (whose own focus trap otherwise
  // defaults to the first focusable element — Dialog's × close button).
  // React 19 made `RefObject<T>.current` non-nullable, so a ref that may hold
  // null (every `useRef<T>(null)`) is now spelled `RefObject<T | null>` — the
  // same spelling the sibling Dialog/use-focus-trap props already use.
  nameInputRef?: RefObject<HTMLInputElement | null>;
}

/**
 * GitHub #1393/#1392: `Diagram` is NOT an attribute-catalogue item type (no
 * artifact lineage, so no definition to resolve), which is exactly what the
 * `staticContracts` slot is for — the contract is declared once here instead
 * of hand-writing `required` on the input. Both numbers are the model column's
 * own (`diagram/models.py`: `name = CharField(max_length=500)`).
 *
 * Module scope, not an inline literal: an inline object would be a new identity
 * on every render and would invalidate `useFieldContract`'s `field` callback on
 * every render, contradicting its documented stability.
 */
const DIAGRAM_STATIC_CONTRACTS = {
  name: { required: true, maxLength: 500 },
} as const;

export function DiagramCreateForm({
  onCreated,
  onCancel,
  nameInputRef,
}: DiagramCreateFormProps): JSX.Element {
  const { t } = useTranslation();
  const { activeWorkspace } = useWorkspace();
  const { createDiagram, isSaving } = useCreateDiagram();
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [error, setError] = useState<string | null>(null);
  // `staticContracts` is a module-scope constant (see above) so `field` keeps
  // its documented identity across renders. `enabled: false` because `Diagram`
  // has no definition to fetch.
  const { field } = useFieldContract(null, {
    enabled: false,
    staticContracts: DIAGRAM_STATIC_CONTRACTS,
  });

  const handleCreate = async (): Promise<void> => {
    if (!activeWorkspace) return;
    if (!form.name.trim()) {
      setError(t("diagrams.nameRequired"));
      return;
    }
    setError(null);
    try {
      const created = await createDiagram({
        workspace_id: activeWorkspace.id,
        name: form.name.trim(),
        diagram_type: form.diagram_type,
        payload_format: form.payload_format,
        content: form.content,
        description: form.description,
      });
      setForm(EMPTY_FORM);
      await onCreated(created.id);
    } catch (err) {
      const msg =
        (err as { error?: { message?: string } })?.error?.message ??
        String(err);
      setError(msg);
    }
  };

  const submitDisabled = isSaving || !form.name.trim();

  return (
    <div data-testid="diagram-create-form">
      <h3 className={styles.heading}>
        + {t("diagrams.create")}
      </h3>
      <div className={styles.grid}>
        {/* `FormField` renders a FRAGMENT (label + control + error), so in this
            2-column grid its label would land in r1c1 and its control in r1c2 —
            label detached from control, and every following field shifted one
            cell. `.fieldCell` is the single grid cell that keeps the three
            nodes stacked, i.e. the same `<label class="label">` layout the
            four hand-written fields below use. */}
        <div className={styles.fieldCell}>
          <FormField
            htmlFor="diagram-name-input"
            label={t("diagrams.name")}
            required={field("name").required}
            labelClassName={styles.label}
          >
            <input
              id="diagram-name-input"
              data-testid="diagram-name-input"
              ref={nameInputRef}
              type="text"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              className={styles.input}
              {...field("name").controlProps}
            />
          </FormField>
        </div>

        <label className={styles.label}>
          {t("diagrams.type")}
          <select
            data-testid="diagram-type-select"
            value={form.diagram_type}
            onChange={(e) =>
              setForm({ ...form, diagram_type: e.target.value as DiagramType })
            }
            className={styles.input}
          >
            {DIAGRAM_TYPES.map((tp) => (
              <option key={tp} value={tp}>
                {t(`diagrams.typeLabels.${tp}`)}
              </option>
            ))}
          </select>
        </label>

        <label className={styles.label}>
          {t("diagrams.sourceFormat")}
          <select
            data-testid="diagram-format-select"
            value={form.payload_format}
            onChange={(e) => {
              const fmt = e.target.value as PayloadFormat;
              setForm({
                ...form,
                payload_format: fmt,
                content: DEFAULT_CONTENT[fmt],
              });
            }}
            className={styles.input}
          >
            {/* GH-353 Task 9: Filter to offer node_graph (structured) instead of json,
                keep canvas_stroke (freehand sketch) and mermaid/plantuml text formats. */}
            {PAYLOAD_FORMATS.filter((fmt) => fmt !== "json").map((fmt) => {
              const labels: Record<PayloadFormat, string> = {
                node_graph: t("diagrams.formatLabels.nodeGraph"),
                mermaid: t("diagrams.formatLabels.mermaid"),
                plantuml: t("diagrams.formatLabels.plantuml"),
                canvas_stroke: t("diagrams.formatLabels.canvasStroke"),
                json: "JSON", // filtered out but kept for type safety
              };
              return (
                <option key={fmt} value={fmt}>
                  {labels[fmt]}
                </option>
              );
            })}
          </select>
        </label>

        <label className={styles.label}>
          {t("diagrams.description")}
          <input
            data-testid="diagram-description-input"
            type="text"
            value={form.description}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
            className={styles.input}
          />
        </label>

        <label className={`${styles.label} ${styles.labelFull}`}>
          {t("diagrams.source")}
          <textarea
            data-testid="diagram-source-textarea"
            value={form.content}
            onChange={(e) => setForm({ ...form, content: e.target.value })}
            rows={8}
            className={`${styles.input} ${styles.textarea}`}
          />
        </label>

        {error && (
          <div
            data-testid="diagram-create-error"
            role="alert"
            className={styles.error}
          >
            {error}
          </div>
        )}

        <div className={styles.footer}>
          <button
            type="button"
            onClick={() => {
              setForm(EMPTY_FORM);
              setError(null);
              onCancel();
            }}
            className={`btn-secondary ${styles.cancelBtn}`}
          >
            {t("actions.cancel")}
          </button>
          <button
            type="button"
            data-testid="diagram-save-btn"
            onClick={() => void handleCreate()}
            disabled={submitDisabled}
            className={`btn-primary ${styles.submitBtn} ${submitDisabled ? styles.submitBtnDisabled : ""}`}
          >
            {isSaving ? t("actions.saving") : t("actions.save")}
          </button>
        </div>
      </div>
    </div>
  );
}
