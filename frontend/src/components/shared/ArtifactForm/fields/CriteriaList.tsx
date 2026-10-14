/**
 * `criteria-list` field widget (#1288).
 *
 * Renders an ordered list of individually verifiable criteria
 * (`{text, fulfilled, evidence_ref?}`). Each row is a checkbox ("fulfilled")
 * plus a free-text field, with add/remove affordances — minimal and consistent
 * with the other definition-driven field widgets (they all render inside
 * `FieldShell` and honour the shared `disabled`/`errors`/`testId` contract).
 *
 * The individual-item write path (``.../acceptance-criteria/{index}/``) is a
 * separate REST/MCP surface; this widget edits the whole list value through the
 * form's normal `custom_fields`/core-field save the same way `MultiEnum` does.
 */
import { useTranslation } from "react-i18next";

import type { CriteriaItem } from "../../../../types";
import styles from "../ArtifactForm.module.css";
import { FieldShell, ariaProps, type FieldProps } from "./FieldShell";

export type { CriteriaItem };

export function CriteriaList({
  attribute,
  value,
  onChange,
  disabled,
  errors,
  testId,
}: FieldProps<CriteriaItem[] | null>): JSX.Element {
  const { t, i18n } = useTranslation();
  const items = value ?? [];

  const replace = (index: number, next: Partial<CriteriaItem>): void => {
    onChange(items.map((item, i) => (i === index ? { ...item, ...next } : item)));
  };
  const remove = (index: number): void => {
    onChange(items.filter((_, i) => i !== index));
  };
  const add = (): void => {
    onChange([...items, { text: "", fulfilled: false, evidence_ref: null }]);
  };

  return (
    <FieldShell
      attribute={attribute}
      language={i18n.language}
      errors={errors}
      testId={testId}
    >
      <div
        className={styles.criteriaList}
        id={testId}
        data-testid={testId}
        role="group"
        {...ariaProps(attribute, testId, errors)}
      >
        {items.map((item, index) => (
          <div
            key={index}
            className={`${styles.criteriaRow} ${item.fulfilled ? styles.criteriaDone : ""}`}
            data-testid={`${testId}-row-${index}`}
          >
            <input
              type="checkbox"
              checked={item.fulfilled}
              disabled={disabled}
              aria-label={t("artifactForm.criteria.fulfilled")}
              data-testid={`${testId}-fulfilled-${index}`}
              onChange={(event) => replace(index, { fulfilled: event.target.checked })}
            />
            <input
              type="text"
              className={styles.criteriaText}
              value={item.text}
              disabled={disabled}
              aria-label={t("artifactForm.criteria.text")}
              data-testid={`${testId}-text-${index}`}
              onChange={(event) => replace(index, { text: event.target.value })}
            />
            <button
              type="button"
              className="btn-ghost"
              disabled={disabled}
              data-testid={`${testId}-remove-${index}`}
              onClick={() => remove(index)}
            >
              {t("artifactForm.criteria.remove")}
            </button>
          </div>
        ))}
        <button
          type="button"
          className="btn-secondary"
          disabled={disabled}
          data-testid={`${testId}-add`}
          onClick={add}
        >
          {t("artifactForm.criteria.add")}
        </button>
      </div>
    </FieldShell>
  );
}
