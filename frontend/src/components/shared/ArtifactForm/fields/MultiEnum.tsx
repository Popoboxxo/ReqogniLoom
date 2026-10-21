import { useTranslation } from "react-i18next";

import styles from "../ArtifactForm.module.css";
import {
  FieldShell,
  ariaProps,
  isEffectiveRequired,
  optionLabel,
  type FieldProps,
} from "./FieldShell";

export function MultiEnum({
  attribute,
  value,
  onChange,
  disabled,
  errors,
  testId,
}: FieldProps<string[] | null>): JSX.Element {
  const { t, i18n } = useTranslation();
  const selected = value ?? [];
  // GitHub #1392 follow-up (H2): `aria-required` is not supported on
  // `role="group"` in ARIA 1.2 — AT ignores it, so a gate-required
  // `acceptance_criteria`/`stakeholder` announced nothing. The container is a
  // group of toggle buttons (neither a radiogroup nor a listbox), so instead of
  // re-typing the role the required state travels in the group's accessible
  // NAME via the visually-hidden "${testId}-required" word. CriteriaList uses
  // the SAME contract, so both group widgets stay consistent.
  const required = isEffectiveRequired(attribute);
  return (
    <FieldShell
      attribute={attribute}
      language={i18n.language}
      errors={errors}
      testId={testId}
      // A group container is not labelable: `<label htmlFor>` pointing at a
      // `<div role="group">` gives it no accessible name. The label renders as
      // a `<span id="${testId}-label">` and the group names itself through
      // `aria-labelledby` — the path `DisplayField` already uses.
      associateLabel={false}
    >
      {/* SC 1.3.1/4.1.2 (A11Y minor): the visually-hidden required word must
          NOT sit inside the `role="group"` container — there it was both part
          of the group's accessible name (through `aria-labelledby`) and
          content of the group, so a screen-reader user in browse mode heard
          "Pflichtfeld" twice. As a SIBLING it still contributes to the name via
          the id below, but is no longer group content. */}
      {required ? (
        <span id={`${testId}-required`} className={styles.srOnly}>
          {t("artifactForm.requiredField")}
        </span>
      ) : null}
      <div
        className={styles.optionList}
        id={testId}
        data-testid={testId}
        role="group"
        aria-labelledby={
          required ? `${testId}-label ${testId}-required` : `${testId}-label`
        }
        // GitHub #1192: `ariaProps` still carries the help/error
        // `aria-describedby` wiring every other control in the shell gets; the
        // required flag is suppressed here (`groupContainer`) because it is
        // carried by the name above.
        {...ariaProps(attribute, testId, errors, { groupContainer: true })}
      >
        {attribute.options.map((option) => {
          const isOn = selected.includes(option.value);
          return (
            <button
              key={option.value}
              type="button"
              data-testid={`${testId}-option-${option.value}`}
              className={`btn-ghost ${styles.optionChip} ${isOn ? styles.optionChipSelected : ""}`}
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
