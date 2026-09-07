import { useTranslation } from "react-i18next";
import { Plus, Trash2 } from "lucide-react";

import styles from "../ArtifactForm.module.css";
import type { WidgetProps } from "../widget-registry";

/**
 * Ordered list editor for ``TestCase.steps``. Closes audit finding V: the
 * column exists but no form ever offered an editor for it, so steps could only
 * be written through the API.
 */
export function StepsEditor({
  attribute,
  values,
  onChange,
  disabled,
  errors,
  testId,
}: WidgetProps): JSX.Element {
  const { t } = useTranslation();
  const field = attribute.fields[0] ?? "steps_data";
  const raw = values[field];
  const steps: string[] = Array.isArray(raw) ? raw.map((s) => String(s)) : [];

  const write = (next: string[]): void => onChange(field, next);

  return (
    <div className={styles.widget} data-testid={testId}>
      {steps.map((step, index) => (
        <div key={index} className={styles.stepRow}>
          <span className={styles.stepIndex}>{index + 1}</span>
          <input
            className={styles.control}
            data-testid={`${testId}-step-${index}`}
            type="text"
            value={step}
            disabled={disabled}
            aria-label={t("testcases.step", { index: index + 1 })}
            onChange={(event) =>
              write(steps.map((s, i) => (i === index ? event.target.value : s)))
            }
          />
          <button
            type="button"
            data-testid={`${testId}-remove-${index}`}
            disabled={disabled}
            aria-label={t("testcases.removeStep", { index: index + 1 })}
            onClick={() => write(steps.filter((_, i) => i !== index))}
          >
            <Trash2 aria-hidden="true" size={16} />
          </button>
        </div>
      ))}
      <button
        type="button"
        data-testid={`${testId}-add`}
        disabled={disabled}
        onClick={() => write([...steps, ""])}
      >
        <Plus aria-hidden="true" size={16} />
        {t("testcases.addStep")}
      </button>
      {(errors?.[field] ?? []).map((message) => (
        <span key={message} className={styles.errors} role="alert">
          {message}
        </span>
      ))}
    </div>
  );
}
