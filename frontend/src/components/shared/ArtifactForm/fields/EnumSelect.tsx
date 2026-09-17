import { useTranslation } from "react-i18next";

import styles from "../ArtifactForm.module.css";
import { FieldShell, ariaProps, optionLabel, type FieldProps } from "./FieldShell";

export function EnumSelect({
  attribute,
  value,
  onChange,
  disabled,
  errors,
  testId,
}: FieldProps<string | null>): JSX.Element {
  const { i18n, t } = useTranslation();
  const current = value ?? "";
  // Issue #274: a <select> silently displays option[0] when its value matches
  // no option, so a Save would downgrade a legacy value the user never
  // touched. Keep the unknown value as a real option instead.
  const isUnknown = current !== "" && !attribute.options.some((o) => o.value === current);
  return (
    <FieldShell
      attribute={attribute}
      language={i18n.language}
      errors={errors}
      testId={testId}
    >
      <select
        id={testId}
        data-testid={testId}
        className={`${styles.control} ${errors?.length ? styles.controlInvalid : ""}`}
        value={current}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value || null)}
        {...ariaProps(attribute, testId, errors)}
      >
        {!attribute.required ? <option value="">{t("artifactForm.noneOption")}</option> : null}
        {isUnknown ? (
          <option value={current}>
            {t("artifactForm.unknownValue", { value: current })}
          </option>
        ) : null}
        {attribute.options.map((option) => (
          <option key={option.value} value={option.value}>
            {optionLabel(option, i18n.language)}
          </option>
        ))}
      </select>
    </FieldShell>
  );
}
