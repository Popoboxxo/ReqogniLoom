import { useTranslation } from "react-i18next";

import styles from "../ArtifactForm.module.css";
import { FieldShell, ariaProps, type FieldProps } from "./FieldShell";

export function NumberField({
  attribute,
  value,
  onChange,
  disabled,
  errors,
  testId,
}: FieldProps<number | null>): JSX.Element {
  const { i18n } = useTranslation();
  return (
    <FieldShell
      attribute={attribute}
      language={i18n.language}
      errors={errors}
      testId={testId}
    >
      <input
        id={testId}
        data-testid={testId}
        className={`${styles.control} ${errors?.length ? styles.controlInvalid : ""}`}
        type="number"
        value={value ?? ""}
        disabled={disabled}
        min={attribute.validation.min}
        max={attribute.validation.max}
        onChange={(event) => {
          // Emit null (not NaN, not "") when cleared: the backend treats null
          // as "not supplied" and NaN would serialise as invalid JSON.
          const raw = event.target.value;
          onChange(raw === "" ? null : Number(raw));
        }}
        {...ariaProps(attribute, testId, errors)}
      />
    </FieldShell>
  );
}
