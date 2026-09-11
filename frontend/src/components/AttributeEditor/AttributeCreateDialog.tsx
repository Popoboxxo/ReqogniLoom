/**
 * AttributeCreateDialog (Task 3, spec section 4.1).
 *
 * Creates one `kind: "extended"` attribute via `create_global`/
 * `create_workspace` (Task 1/2's new endpoints) — always an immediate API
 * call, not a locally-buffered edit like the rest of `AttributeEditorPage`'s
 * meta-property changes. The options field is intentionally minimal (a
 * comma-separated value list, each entry reused as `value`/`label_de`/
 * `label_en`) — just enough to satisfy `schema.py`'s "enum/multi-enum
 * requires a non-empty options list" rule; the real options editor is Task 6.
 */

import { useState } from "react";
import { useTranslation } from "react-i18next";

import type { AttributeType, NewAttributeInput } from "../../api/attribute-definitions";
import { Dialog } from "../shared/Dialog";
import editorStyles from "./AttributeEditor.module.css";
import styles from "./AttributeCreateDialog.module.css";

const ATTRIBUTE_TYPES: readonly AttributeType[] = [
  "text",
  "textarea",
  "number",
  "boolean",
  "enum",
  "multi-enum",
  "date",
  "reference",
  "user",
  "widget",
];

const ENUM_TYPES: ReadonlySet<AttributeType> = new Set(["enum", "multi-enum"]);

const NAME_RE = /^[a-z][a-z0-9_]*$/;

export interface AttributeCreateDialogProps {
  scope: "global" | "workspace";
  /** Pre-filled from the section the "+" button was clicked in. */
  section: string;
  /** Client-side collision pre-check — the server re-validates regardless. */
  existingNames: string[];
  onCreate: (attribute: NewAttributeInput) => Promise<void>;
  onClose: () => void;
}

export function AttributeCreateDialog({
  scope,
  section,
  existingNames,
  onCreate,
  onClose,
}: AttributeCreateDialogProps): JSX.Element {
  const { t } = useTranslation();
  const [name, setName] = useState("");
  const [type, setType] = useState<AttributeType>("text");
  const [required, setRequired] = useState(false);
  const [sectionValue, setSectionValue] = useState(section);
  const [optionsInput, setOptionsInput] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (): Promise<void> => {
    setError(null);
    const trimmedName = name.trim();
    if (!NAME_RE.test(trimmedName)) {
      setError(t("attributes.create.errorInvalidName"));
      return;
    }
    if (existingNames.includes(trimmedName)) {
      setError(t("attributes.create.errorNameExists"));
      return;
    }

    let options: NewAttributeInput["options"];
    if (ENUM_TYPES.has(type)) {
      const values = optionsInput
        .split(",")
        .map((value) => value.trim())
        .filter(Boolean);
      if (values.length === 0) {
        setError(t("attributes.create.errorOptionsRequired"));
        return;
      }
      options = values.map((value) => ({ value, label_de: value, label_en: value }));
    }

    const trimmedSection = sectionValue.trim() || section;
    setSubmitting(true);
    try {
      await onCreate({
        name: trimmedName,
        type,
        required,
        section: trimmedSection,
        ...(options ? { options } : {}),
      });
      onClose();
    } catch (exc: unknown) {
      setError(exc instanceof Error ? exc.message : String(exc));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog
      title={t("attributes.create.title")}
      onClose={onClose}
      testId="attribute-create-dialog"
      closeOnBackdropClick={!submitting}
      footer={
        <>
          <button
            type="button"
            data-testid="attribute-create-dialog-cancel"
            onClick={onClose}
            disabled={submitting}
          >
            {t("actions.cancel")}
          </button>
          <button
            type="button"
            data-testid="attribute-create-dialog-submit"
            onClick={() => void handleSubmit()}
            disabled={submitting}
          >
            {t("actions.create")}
          </button>
        </>
      }
    >
      <div className={styles.form}>
        {scope === "workspace" ? (
          <p className={styles.hint} data-testid="attribute-create-dialog-workspace-hint">
            {t("attributes.create.workspaceOnlyHint")}
          </p>
        ) : null}

        {error ? (
          <div
            className={editorStyles.error}
            role="alert"
            data-testid="attribute-create-dialog-error"
          >
            {error}
          </div>
        ) : null}

        <label className={editorStyles.field}>
          <span>{t("attributes.create.name")}</span>
          <input
            className={editorStyles.control}
            type="text"
            data-testid="attribute-create-dialog-name"
            value={name}
            autoFocus
            onChange={(event) => setName(event.target.value)}
          />
        </label>

        <label className={editorStyles.field}>
          <span>{t("attributes.create.type")}</span>
          <select
            className={editorStyles.control}
            data-testid="attribute-create-dialog-type"
            value={type}
            onChange={(event) => setType(event.target.value as AttributeType)}
          >
            {ATTRIBUTE_TYPES.map((option) => (
              <option key={option} value={option}>
                {t(`attributes.types.${option}`, { defaultValue: option })}
              </option>
            ))}
          </select>
        </label>

        {ENUM_TYPES.has(type) ? (
          <label className={editorStyles.field}>
            <span>{t("attributes.create.options")}</span>
            <input
              className={editorStyles.control}
              type="text"
              data-testid="attribute-create-dialog-options"
              value={optionsInput}
              placeholder={t("attributes.create.optionsPlaceholder")}
              onChange={(event) => setOptionsInput(event.target.value)}
            />
          </label>
        ) : null}

        <label className={editorStyles.field}>
          <span>{t("attributes.required")}</span>
          <input
            type="checkbox"
            data-testid="attribute-create-dialog-required"
            checked={required}
            onChange={(event) => setRequired(event.target.checked)}
          />
        </label>

        <label className={editorStyles.field}>
          <span>{t("attributes.section")}</span>
          <input
            className={editorStyles.control}
            type="text"
            data-testid="attribute-create-dialog-section"
            value={sectionValue}
            onChange={(event) => setSectionValue(event.target.value)}
          />
        </label>
      </div>
    </Dialog>
  );
}
