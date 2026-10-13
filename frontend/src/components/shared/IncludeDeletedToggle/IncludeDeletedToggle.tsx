import { useTranslation } from "react-i18next";

import styles from "./IncludeDeletedToggle.module.css";

export interface IncludeDeletedToggleProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
  testIdPrefix: string;
}

export function IncludeDeletedToggle({
  checked,
  onChange,
  testIdPrefix,
}: IncludeDeletedToggleProps): JSX.Element {
  const { t } = useTranslation();
  return (
    <label
      data-testid={`${testIdPrefix}-include-deleted-label`}
      className={styles.toggle}
    >
      <input
        type="checkbox"
        data-testid={`${testIdPrefix}-include-deleted`}
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
      />
      {t("editor.showOutdated", "Show outdated")}
    </label>
  );
}

IncludeDeletedToggle.displayName = "IncludeDeletedToggle";
