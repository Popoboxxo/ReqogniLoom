import { useTranslation } from "react-i18next";

import styles from "../ArtifactForm.module.css";
import { FieldShell, ariaProps, type FieldProps } from "./FieldShell";

export function BooleanToggle({
  attribute,
  value,
  onChange,
  disabled,
  errors,
  testId,
}: FieldProps<boolean | null>): JSX.Element {
  const { i18n } = useTranslation();
  return (
    <FieldShell
      attribute={attribute}
      language={i18n.language}
      errors={errors}
      testId={testId}
    >
      <span className={styles.checkboxRow}>
        <input
          id={testId}
          data-testid={testId}
          type="checkbox"
          checked={Boolean(value)}
          disabled={disabled}
          onChange={(event) => onChange(event.target.checked)}
          {...ariaProps(attribute, testId, errors)}
        />
      </span>
    </FieldShell>
  );
}
