import { useTranslation } from "react-i18next";

import styles from "../ArtifactForm.module.css";
import { FieldShell, ariaProps, isEffectiveRequired, type FieldProps } from "./FieldShell";

export function DateField({
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
      {/* Native date input on purpose: no picker dependency, and the browser
          already handles locale, keyboard and screen-reader semantics. */}
      <input
        id={testId}
        data-testid={testId}
        className={`${styles.control} ${errors?.length ? styles.controlInvalid : ""}`}
        type="date"
        required={isEffectiveRequired(attribute)}
        value={value ? String(value).slice(0, 10) : ""}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value || null)}
        {...ariaProps(attribute, testId, errors)}
      />
    </FieldShell>
  );
}
