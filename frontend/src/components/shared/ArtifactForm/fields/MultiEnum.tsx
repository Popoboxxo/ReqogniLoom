import { useTranslation } from "react-i18next";

import styles from "../ArtifactForm.module.css";
import { FieldShell, optionLabel, type FieldProps } from "./FieldShell";

export function MultiEnum({
  attribute,
  value,
  onChange,
  disabled,
  errors,
  testId,
}: FieldProps<string[] | null>): JSX.Element {
  const { i18n } = useTranslation();
  const selected = value ?? [];
  return (
    <FieldShell
      attribute={attribute}
      language={i18n.language}
      errors={errors}
      testId={testId}
    >
      <div
        className={styles.optionList}
        id={testId}
        data-testid={testId}
        role="group"
        aria-required={attribute.required}
        aria-invalid={Boolean(errors?.length)}
      >
        {attribute.options.map((option) => {
          const isOn = selected.includes(option.value);
          return (
            <button
              key={option.value}
              type="button"
              data-testid={`${testId}-option-${option.value}`}
              className={`${styles.optionChip} ${isOn ? styles.optionChipSelected : ""}`}
              disabled={disabled}
              aria-pressed={isOn}
              onClick={() =>
                onChange(
                  isOn
                    ? selected.filter((v) => v !== option.value)
                    : [...selected, option.value]
                )
              }
            >
              {optionLabel(option, i18n.language)}
            </button>
          );
        })}
      </div>
    </FieldShell>
  );
}
