import { useState } from "react";
import { useTranslation } from "react-i18next";

import { MarkdownPreview } from "../../../RequirementEditors/MarkdownPreview";
import { handleTablistKeyDown, tabRovingTabIndex } from "../../tablistKeyboardNav";
import styles from "../ArtifactForm.module.css";
import type { WidgetProps } from "../widget-registry";

/**
 * Groups several markdown fields under one tab strip — replaces AdrForm's three
 * stacked editors (description / context / consequences) without changing what
 * is stored: each tab writes its own bound field.
 */
export function MarkdownTabGroup({
  attribute,
  values,
  onChange,
  disabled,
  errors,
  testId,
}: WidgetProps): JSX.Element {
  const { t } = useTranslation();
  const [active, setActive] = useState<string>(attribute.fields[0] ?? "");

  return (
    <div className={styles.widget} data-testid={testId}>
      <div
        className={styles.tabList}
        role="tablist"
        onKeyDown={(event) =>
          handleTablistKeyDown(event, attribute.fields, active, setActive)
        }
      >
        {attribute.fields.map((field) => (
          <button
            key={field}
            type="button"
            role="tab"
            id={`${testId}-tab-${field}`}
            data-testid={`${testId}-tab-${field}`}
            aria-selected={active === field}
            aria-controls={`${testId}-panel-${field}`}
            tabIndex={tabRovingTabIndex(field, active)}
            className={`${styles.tab} ${active === field ? styles.tabActive : ""}`}
            onClick={() => setActive(field)}
          >
            {t(`artifactForm.field.${field}`, { defaultValue: field })}
          </button>
        ))}
      </div>
      {attribute.fields.map((field) =>
        active === field ? (
          <div
            key={field}
            role="tabpanel"
            id={`${testId}-panel-${field}`}
            aria-labelledby={`${testId}-tab-${field}`}
          >
            <MarkdownPreview
              id={`${testId}-editor-${field}`}
              value={String(values[field] ?? "")}
              onChange={(next: string) => onChange(field, next)}
              disabled={disabled}
            />
            {(errors?.[field] ?? []).map((message) => (
              <span key={message} className={styles.errors} role="alert">
                {message}
              </span>
            ))}
          </div>
        ) : null
      )}
    </div>
  );
}
