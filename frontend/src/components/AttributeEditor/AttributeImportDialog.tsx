/**
 * AttributeImportDialog (Task 11, spec section 6).
 *
 * The file picker itself lives in AttributeEditorPage (a plain hidden
 * `<input type="file">` — no dialog needed for that step); this dialog only
 * covers the collision-resolution choice once a file has already been
 * selected and parsed.
 */

import { useState } from "react";
import { useTranslation } from "react-i18next";

import type { OnCollision } from "../../api/attribute-definitions";
import { Dialog } from "../shared/Dialog";
import editorStyles from "./AttributeEditor.module.css";
import styles from "./AttributeImportDialog.module.css";

export interface AttributeImportDialogProps {
  fileName: string;
  onConfirm: (onCollision: OnCollision) => Promise<void>;
  onClose: () => void;
}

const CHOICES: OnCollision[] = ["skip", "overwrite", "rename"];

export function AttributeImportDialog({
  fileName,
  onConfirm,
  onClose,
}: AttributeImportDialogProps): JSX.Element {
  const { t } = useTranslation();
  const [onCollision, setOnCollision] = useState<OnCollision>("skip");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleConfirm = async (): Promise<void> => {
    setSubmitting(true);
    setError(null);
    try {
      await onConfirm(onCollision);
      onClose();
    } catch (exc: unknown) {
      setError(exc instanceof Error ? exc.message : String(exc));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog
      title={t("attributes.import.title")}
      onClose={onClose}
      testId="attribute-import-dialog"
      closeOnBackdropClick={!submitting}
      footer={
        <>
          <button
            type="button"
            data-testid="attribute-import-dialog-cancel"
            onClick={onClose}
            disabled={submitting}
          >
            {t("actions.cancel")}
          </button>
          <button
            type="button"
            data-testid="attribute-import-dialog-confirm"
            onClick={() => void handleConfirm()}
            disabled={submitting}
          >
            {t("actions.import")}
          </button>
        </>
      }
    >
      <p>{t("attributes.import.fileLabel", { name: fileName })}</p>

      {error ? (
        <div className={editorStyles.error} role="alert" data-testid="attribute-import-dialog-error">
          {error}
        </div>
      ) : null}

      <fieldset>
        <legend>{t("attributes.import.onCollisionLabel")}</legend>
        {CHOICES.map((choice) => (
          <label key={choice} className={styles.radioLabel}>
            <input
              type="radio"
              name="on-collision"
              data-testid={`attribute-import-dialog-on-collision-${choice}`}
              checked={onCollision === choice}
              disabled={submitting}
              onChange={() => setOnCollision(choice)}
            />
            {t(`attributes.import.onCollision.${choice}`)}
          </label>
        ))}
      </fieldset>
    </Dialog>
  );
}
