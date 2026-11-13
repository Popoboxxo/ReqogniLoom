import { useTranslation } from "react-i18next";
import { Plus, Trash2 } from "lucide-react";

import styles from "../ArtifactForm.module.css";
import type { WidgetProps } from "../widget-registry";
import type { StepType, TestCaseStep } from "../../../../api/testcases";
import {
  STEP_TYPES,
  newStep,
  normalizeSteps,
} from "../../../../utils/testSteps";

/**
 * Ordered list editor for ``TestCase.steps``, now with the typed step kinds of
 * Issue #1564.
 *
 * Bound value shape is `TestCaseStep[]` (`{ id?, step_type, text }`). A stored
 * legacy `{ step, expected_result }` row (or the even older bare `string[]`) is
 * normalised on READ into `when`/`then` rows, so editing an old test case never
 * writes the pair shape back. Every write carries typed steps; the backend
 * accepts that shape directly and validates it.
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
  const steps: TestCaseStep[] = normalizeSteps(values[field]);

  const write = (next: TestCaseStep[]): void => onChange(field, next);

  return (
    <div className={styles.widget} data-testid={testId}>
      {steps.map((step, index) => (
        <div key={step.id ?? index} className={styles.stepRow}>
          <span className={styles.stepIndex}>{index + 1}</span>
          <select
            className={styles.control}
            data-testid={`${testId}-type-${index}`}
            value={step.step_type}
            disabled={disabled}
            aria-label={t("testcases.stepType.label", { index: index + 1 })}
            onChange={(event) =>
              write(
                steps.map((s, i) =>
                  i === index
                    ? { ...s, step_type: event.target.value as StepType }
                    : s
                )
              )
            }
          >
            {STEP_TYPES.map((stepType) => (
              <option key={stepType} value={stepType}>
                {t(`testcases.stepType.${stepType}`)}
              </option>
            ))}
          </select>
          <input
            className={styles.control}
            data-testid={`${testId}-step-${index}`}
            type="text"
            value={step.text}
            disabled={disabled}
            placeholder={t("deriveTestcase.stepPlaceholder")}
            aria-label={t("testcases.step", { index: index + 1 })}
            onChange={(event) =>
              write(
                steps.map((s, i) =>
                  i === index ? { ...s, text: event.target.value } : s
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
            className="btn-icon"
          >
            <Trash2 aria-hidden="true" size={16} />
          </button>
        </div>
      ))}
      <button
        type="button"
        data-testid={`${testId}-add`}
        disabled={disabled}
        onClick={() => write([...steps, newStep()])}
        className="btn-secondary"
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
