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
import {
  FieldShell,
  ariaProps,
  isEffectiveRequired,
  type FieldProps,
} from "./FieldShell";

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
  // The *effective* flag (definition `required` OR the #1192 approval gate).
  const required = isEffectiveRequired(attribute);

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
      // Same contract as MultiEnum (H2): a `<div role="group">` is not
      // labelable, so the label renders as `<span id="${testId}-label">` and
      // the group names itself via `aria-labelledby`.
      associateLabel={false}
    >
      {/* SC 1.3.1/4.1.2 (A11Y minor): sibling of the `role="group"`, not a
          child — inside the container the required word was both part of the
          accessible name (via `aria-labelledby`) and group content, so browse
          mode announced it twice. `aria-labelledby` still references it. */}
      {required ? (
        <span id={`${testId}-required`} className={styles.srOnly}>
          {t("artifactForm.requiredField")}
        </span>
      ) : null}
      <div
        className={styles.criteriaList}
        id={testId}
        data-testid={testId}
        role="group"
        // `aria-required` on `role="group"` is invalid in ARIA 1.2 (AT ignores
        // it). This widget is a list of checkbox+text rows, not a radiogroup or
        // a listbox, so the required state is carried by the accessible NAME
        // through the visually-hidden "${testId}-required" word — the same
        // choice MultiEnum documents.
        aria-labelledby={
          required ? `${testId}-label ${testId}-required` : `${testId}-label`
        }
        {...ariaProps(attribute, testId, errors, { groupContainer: true })}
      >
        {items.map((item, index) => (
          <div
            key={index}
            className={`${styles.criteriaRow} ${item.fulfilled ? styles.criteriaDone : ""}`}
            data-testid={`${testId}-row-${index}`}
          >
            {/* GitHub #1394: a real wrapping `<label>` so the 24x24 floor in
                `.checkboxRow` enlarges a CLICKABLE box instead of the bare
                13px glyph. The name still comes from the input's aria-label. */}
            <label className={styles.checkboxRow}>
              <input
                type="checkbox"
                checked={item.fulfilled}
                disabled={disabled}
                aria-label={t("artifactForm.criteria.fulfilled")}
                data-testid={`${testId}-fulfilled-${index}`}
                onChange={(event) => replace(index, { fulfilled: event.target.checked })}
              />
            </label>
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
