import { useTranslation } from "react-i18next";
import { Plus, Trash2 } from "lucide-react";

import styles from "../ArtifactForm.module.css";
import type { WidgetProps } from "../widget-registry";
import type { TestCaseStep } from "../../../../api/testcases";

/**
 * Normalizes one raw steps-array entry into `TestCaseStep`. Defends against
 * data that never went through this editor:
 * - a bare string (this widget's OWN pre-fix `string[]` shape, or any other
 *   hand-authored/legacy value) becomes `{ step: <string>, expected_result: "" }`.
 * - a dict missing/mistyping either key falls back to `""` per key instead of
 *   crashing (no `String(undefined)` -> "undefined" artifacts).
 */
function normalizeStep(entry: unknown): TestCaseStep {
  if (entry && typeof entry === "object" && !Array.isArray(entry)) {
    const record = entry as Record<string, unknown>;
    return {
      step: typeof record.step === "string" ? record.step : "",
      expected_result:
        typeof record.expected_result === "string" ? record.expected_result : "",
    };
  }
  return { step: String(entry), expected_result: "" };
}

/**
 * Ordered list editor for ``TestCase.steps``. Closes audit finding V: the
 * column exists but no form ever offered an editor for it, so steps could only
 * be written through the API.
 *
 * Bound value shape is `TestCaseStep[]` (`{ step, expected_result }` dicts),
 * matching the backend contract (`rest_api/serializers.py`:
 * `steps = serializers.ListField(child=serializers.DictField(), ...)`) and
 * the same type `DeriveTestCasePanel` already writes. A bare `string[]` is
 * REJECTED by the backend with a 400 ("Expected a dictionary of items but got
 * type 'str'.") — do not regress to that shape. `normalizeStep` tolerates it
 * on READ only, for pre-existing data that predates this editor.
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
  const steps: TestCaseStep[] = Array.isArray(raw) ? raw.map(normalizeStep) : [];

  const write = (next: TestCaseStep[]): void => onChange(field, next);

  return (
    <div className={styles.widget} data-testid={testId}>
      {steps.map((step, index) => (
        <div key={index} className={styles.stepRow}>
          <span className={styles.stepIndex}>{index + 1}</span>
          <input
            className={styles.control}
            data-testid={`${testId}-step-${index}`}
            type="text"
            value={step.step}
            disabled={disabled}
            placeholder={t("deriveTestcase.stepPlaceholder")}
            aria-label={t("testcases.step", { index: index + 1 })}
            onChange={(event) =>
              write(
                steps.map((s, i) =>
                  i === index ? { ...s, step: event.target.value } : s
                )
              )
            }
          />
          <input
            className={styles.control}
            data-testid={`${testId}-expected-${index}`}
            type="text"
            value={step.expected_result}
            disabled={disabled}
            placeholder={t("deriveTestcase.expectedResultPlaceholder")}
            aria-label={`${t("deriveTestcase.expectedResultPlaceholder")} ${index + 1}`}
            onChange={(event) =>
              write(
                steps.map((s, i) =>
                  i === index ? { ...s, expected_result: event.target.value } : s
                )
              )
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
        onClick={() => write([...steps, { step: "", expected_result: "" }])}
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
