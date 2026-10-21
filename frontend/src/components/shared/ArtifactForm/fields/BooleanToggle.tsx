import { useTranslation } from "react-i18next";

import styles from "../ArtifactForm.module.css";
import { FieldShell, ariaProps, isEffectiveRequired, type FieldProps } from "./FieldShell";

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
      {/* GitHub #1394: the input must sit inside a real `<label>` so the 24x24
          floor in `.checkboxRow` enlarges an actually clickable box. This is a
          SIBLING of `FieldShell`'s own `<label htmlFor>` (nesting labels is
          invalid); both point at the same control, which HTML allows. */}
      <label className={styles.checkboxRow}>
        <input
          id={testId}
          data-testid={testId}
          type="checkbox"
          required={isEffectiveRequired(attribute)}
          checked={Boolean(value)}
          disabled={disabled}
          onChange={(event) => onChange(event.target.checked)}
          {...ariaProps(attribute, testId, errors)}
        />
      </label>
    </FieldShell>
  );
}
