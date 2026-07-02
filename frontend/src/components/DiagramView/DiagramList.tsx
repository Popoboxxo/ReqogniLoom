/**
 * ARCH-L1-001 ReactFrontend — DiagramList (COMP-RF-005).
 *
 * leaf_id: COMP-RF-005
 * req_id:  REQ-L1-040 (Unified ModalDialogBase pattern), REQ-L2-DS-001 (DiagramService REST API)
 *
 * Lists all Diagrams for the active workspace and provides a create form.
 * Uses unified ModalDialogBase for form pattern (REQ-L1-040).
 * Type-specific format templates pre-populate content field.
 */

import React, { useState, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { useWorkspace } from "../../context/WorkspaceContext";
import { diagramsApi } from "../../api/diagrams";
import ModalDialogBase, { SHARED_STYLES } from "../RequirementsList/ModalDialogBase";
import type { Diagram, DiagramType, PayloadFormat } from "../../types";

const DIAGRAM_TYPES: DiagramType[] = ["block", "flow", "context"];
const PAYLOAD_FORMATS: PayloadFormat[] = ["mermaid", "plantuml", "json"];

const DEFAULT_CONTENT: Record<PayloadFormat, string> = {
  mermaid:
    "graph TD\n  A[Start] --> B{Decision}\n  B -- yes --> C[Process]\n  B -- no --> D[End]",
  plantuml:
    "@startuml\n  actor User\n  User -> App : request\n  App --> User : response\n@enduml",
  json: JSON.stringify(
    {
      nodes: [
        { id: "n1", label: "Start" },
        { id: "n2", label: "End" },
      ],
      edges: [{ from: "n1", to: "n2" }],
    },
    null,
    2
  ),
};

export default function DiagramList(): JSX.Element {
  const { t } = useTranslation();
  const { activeWorkspace } = useWorkspace();
  const [items, setItems] = useState<Diagram[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [name, setName] = useState("");
  const [diagramType, setDiagramType] = useState<DiagramType>("block");
  const [payloadFormat, setPayloadFormat] = useState<PayloadFormat>("mermaid");
  const [content, setContent] = useState(DEFAULT_CONTENT.mermaid);
  const [description, setDescription] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const loadList = async (): Promise<void> => {
    if (!activeWorkspace) return;
    setIsLoading(true);
    try {
      const resp = await diagramsApi.list(activeWorkspace.id);
      setItems(resp.results);
    } catch (err) {
      console.error(err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    void loadList();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeWorkspace]);

  const resetForm = (): void => {
    setName("");
    setDiagramType("block");
    setPayloadFormat("mermaid");
    setContent(DEFAULT_CONTENT.mermaid);
    setDescription("");
    setFormError(null);
  };

  const handlePayloadFormatChange = (format: PayloadFormat): void => {
    setPayloadFormat(format);
    setContent(DEFAULT_CONTENT[format]);
  };

  const handleSubmit = async (
    e: React.FormEvent<HTMLFormElement>
  ): Promise<void> => {
    e.preventDefault();
    if (!activeWorkspace) return;
    if (!name.trim()) {
      setFormError("Name is required");
      return;
    }
    setIsSubmitting(true);
    setFormError(null);
    try {
      await diagramsApi.create({
        workspace_id: activeWorkspace.id,
        name: name.trim(),
        diagram_type: diagramType,
        payload_format: payloadFormat,
        content,
        description: description.trim() || undefined,
      });
      resetForm();
      setShowCreate(false);
      await loadList();
    } catch (err: unknown) {
      const msg =
        (err as { error?: { message?: string } })?.error?.message ??
        String(err);
      setFormError(msg);
    } finally {
      setIsSubmitting(false);
    }
  };

  if (isLoading) return <p>{t("loading")}</p>;

  return (
    <>
      <ModalDialogBase
        title={t("nav.diagrams", "Diagrams")}
        isOpen={showCreate}
        onToggle={() => {
          if (showCreate) {
            resetForm();
            setShowCreate(false);
          } else {
            setShowCreate(true);
          }
        }}
        onSubmit={handleSubmit}
        onCancel={() => {
          resetForm();
          setShowCreate(false);
        }}
        error={formError}
        isSubmitting={isSubmitting}
        itemCount={items.length}
        testIdPrefix="diagram"
        buttonTestIdPrefix="diagram"
      >
        <div>
          <label htmlFor="diagram-name" style={SHARED_STYLES.label}>
            {t("editor.name", "Name")} *
          </label>
          <input
            id="diagram-name"
            data-testid="diagram-name-input"
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
            autoFocus
            disabled={isSubmitting}
            placeholder="Diagram name"
            style={SHARED_STYLES.input}
          />
        </div>
        <div>
          <label htmlFor="diagram-type" style={SHARED_STYLES.label}>
            {t("editor.type", "Type")}
          </label>
          <select
            id="diagram-type"
            data-testid="diagram-type-select"
            value={diagramType}
            onChange={(e) => setDiagramType(e.target.value as DiagramType)}
            disabled={isSubmitting}
            style={SHARED_STYLES.input}
          >
            {DIAGRAM_TYPES.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="diagram-format" style={SHARED_STYLES.label}>
            {t("editor.format", "Format")}
          </label>
          <select
            id="diagram-format"
            data-testid="diagram-format-select"
            value={payloadFormat}
            onChange={(e) => handlePayloadFormatChange(e.target.value as PayloadFormat)}
            disabled={isSubmitting}
            style={SHARED_STYLES.input}
          >
            {PAYLOAD_FORMATS.map((f) => (
              <option key={f} value={f}>
                {f}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="diagram-content" style={SHARED_STYLES.label}>
            {t("editor.content", "Content")}
          </label>
          <textarea
            id="diagram-content"
            data-testid="diagram-content-input"
            value={content}
            onChange={(e) => setContent(e.target.value)}
            disabled={isSubmitting}
            rows={6}
            placeholder="Diagram source code"
            style={{ ...SHARED_STYLES.input, fontFamily: "monospace", resize: "vertical" }}
          />
        </div>
        <div>
          <label htmlFor="diagram-description" style={SHARED_STYLES.label}>
            {t("editor.description", "Description")}
          </label>
          <textarea
            id="diagram-description"
            data-testid="diagram-description-input"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            disabled={isSubmitting}
            rows={3}
            placeholder="Describe the diagram..."
            style={{ ...SHARED_STYLES.input, fontFamily: "inherit", resize: "vertical" }}
          />
        </div>
      </ModalDialogBase>

      {/* Item list (rendered outside modal) */}
      {items.length > 0 && (
        <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
          {items.map((item) => (
            <li
              key={item.id}
              data-testid={`diagram-item-${item.id}`}
              style={{
                padding: "var(--space-3) var(--space-4)",
                marginBottom: "var(--space-2)",
                background: "var(--color-surface)",
                borderRadius: "var(--radius-md)",
                border: "1px solid var(--color-border)",
              }}
            >
              <strong>{item.name}</strong>{" "}
              <span
                style={{
                  color: "var(--color-text-muted)",
                  fontSize: "var(--font-size-sm)",
                }}
              >
                — {item.diagram_type}
              </span>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
