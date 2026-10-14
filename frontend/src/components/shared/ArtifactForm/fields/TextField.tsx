import { useTranslation } from "react-i18next";

import styles from "../ArtifactForm.module.css";
import { FieldShell, ariaProps, type FieldProps } from "./FieldShell";
import { LengthFeedback } from "./LengthFeedback";

export function TextField({
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
      <input
        id={testId}
        data-testid={testId}
        className={`${styles.control} ${
          attribute.display_format === "mono" ? styles.controlMono : ""
        } ${errors?.length ? styles.controlInvalid : ""}`}
        type="text"
        value={value ?? ""}
        disabled={disabled}
        maxLength={attribute.validation?.length}
        onChange={(event) => onChange(event.target.value)}
        {...ariaProps(attribute, testId, errors)}
      />
      {/* #1282: show proximity to the definition's length limit (80%+). */}
      <LengthFeedback
        value={value}
        maxLength={attribute.validation?.length}
        testId={testId}
      />
    </FieldShell>
  );
}
