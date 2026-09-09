import { useTranslation } from "react-i18next";

import styles from "../ArtifactForm.module.css";
import { FieldShell, ariaProps, type FieldProps } from "./FieldShell";

export function TextArea({
  attribute,
  value,
  onChange,
  disabled,
  errors,
  testId,
}: FieldProps<string | null>): JSX.Element {
  const { i18n } = useTranslation();
  return (
    <FieldShell
      attribute={attribute}
      language={i18n.language}
      errors={errors}
      testId={testId}
    >
      <textarea
        id={testId}
        data-testid={testId}
        className={`${styles.control} ${errors?.length ? styles.controlInvalid : ""}`}
        rows={6}
        value={value ?? ""}
        disabled={disabled}
        maxLength={attribute.validation.length}
        onChange={(event) => onChange(event.target.value)}
        {...ariaProps(attribute, testId, errors)}
      />
    </FieldShell>
  );
}
