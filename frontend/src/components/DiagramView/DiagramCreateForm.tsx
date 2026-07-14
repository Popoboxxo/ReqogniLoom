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

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useWorkspace } from "../../context/WorkspaceContext";
import { useCreateDiagram } from "./useDiagramData";
import {
  DEFAULT_CONTENT,
  DIAGRAM_TYPES,
  EMPTY_FORM,
  PAYLOAD_FORMATS,
  formCancelButtonStyle,
  formInputStyle,
  formLabelStyle,
  formPrimaryButtonStyle,
  type FormState,
} from "./diagram-view-shared";
import type { DiagramType, PayloadFormat } from "../../types";

export interface DiagramCreateFormProps {
  onCreated: (diagramId: string) => Promise<void> | void;
  onCancel: () => void;
}

export function DiagramCreateForm({
  onCreated,
  onCancel,
}: DiagramCreateFormProps): JSX.Element {
  const { t } = useTranslation();
  const { activeWorkspace } = useWorkspace();
  const { createDiagram, isSaving } = useCreateDiagram();
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [error, setError] = useState<string | null>(null);

  const handleCreate = async (): Promise<void> => {
    if (!activeWorkspace) return;
    if (!form.name.trim()) {
      setError(t("diagrams.nameRequired", "Name is required."));
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

  return (
    <div data-testid="diagram-create-form">
      <h3
        style={{
          fontSize: "var(--font-size-lg)",
          fontWeight: 700,
          marginTop: 0,
          marginBottom: "var(--space-4)",
          color: "var(--color-text)",
        }}
      >
        + {t("diagrams.create", "New Diagram")}
      </h3>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: "var(--space-3)",
        }}
      >
        <label style={formLabelStyle}>
          {t("diagrams.name", "Name")}
          <input
            data-testid="diagram-name-input"
            type="text"
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            style={formInputStyle}
          />
        </label>

        <label style={formLabelStyle}>
          {t("diagrams.type", "Type")}
          <select
            data-testid="diagram-type-select"
            value={form.diagram_type}
            onChange={(e) =>
              setForm({ ...form, diagram_type: e.target.value as DiagramType })
            }
            style={formInputStyle}
          >
            {DIAGRAM_TYPES.map((tp) => (
              <option key={tp} value={tp}>
                {t(`diagrams.type.${tp}`, tp)}
              </option>
            ))}
          </select>
        </label>

        <label style={formLabelStyle}>
          {t("diagrams.source", "Source Format")}
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
            style={formInputStyle}
          >
            {PAYLOAD_FORMATS.map((fmt) => (
              <option key={fmt} value={fmt}>
                {fmt}
              </option>
            ))}
          </select>
        </label>

        <label style={formLabelStyle}>
          {t("diagrams.description", "Description")}
          <input
            data-testid="diagram-description-input"
            type="text"
            value={form.description}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
            style={formInputStyle}
          />
        </label>

        <label style={{ ...formLabelStyle, gridColumn: "1 / -1" }}>
          {t("diagrams.source", "Source")}
          <textarea
            data-testid="diagram-source-textarea"
            value={form.content}
            onChange={(e) => setForm({ ...form, content: e.target.value })}
            rows={8}
            style={{
              ...formInputStyle,
              fontFamily: "var(--font-mono)",
              fontSize: "var(--font-size-sm)",
              resize: "vertical",
            }}
          />
        </label>

        {error && (
          <div
            data-testid="diagram-create-error"
            role="alert"
            style={{
              gridColumn: "1 / -1",
              color: "var(--color-danger)",
              fontSize: "var(--font-size-sm)",
            }}
          >
            {error}
          </div>
        )}

        <div
          style={{
            gridColumn: "1 / -1",
            display: "flex",
            gap: "var(--space-2)",
            justifyContent: "flex-end",
          }}
        >
          <button
            type="button"
            onClick={() => {
              setForm(EMPTY_FORM);
              setError(null);
              onCancel();
            }}
            style={formCancelButtonStyle}
          >
            {t("actions.cancel", "Cancel")}
          </button>
          <button
            type="button"
            data-testid="diagram-save-btn"
            onClick={() => void handleCreate()}
            disabled={isSaving || !form.name.trim()}
            style={{
              ...formPrimaryButtonStyle,
              opacity: isSaving || !form.name.trim() ? 0.6 : 1,
              cursor: isSaving || !form.name.trim() ? "not-allowed" : "pointer",
            }}
          >
            {isSaving ? t("actions.saving", "Saving...") : t("actions.save", "Save")}
          </button>
        </div>
      </div>
    </div>
  );
}
