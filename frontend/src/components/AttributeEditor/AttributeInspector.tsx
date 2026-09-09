/**
 * Per-attribute meta-property editor (Task 26, spec section 6.1). Every
 * control it renders is one the backend accepts for that attribute —
 * `isMetaPropertyLocked` mirrors `validate_meta_only_change`, so the UI never
 * offers an edit that would 400.
 */

import { useTranslation } from "react-i18next";
import { Lock } from "lucide-react";

import type { AttributeSpec } from "../../api/attribute-definitions";
import styles from "./AttributeEditor.module.css";
import { isMetaPropertyLocked, sectionNames } from "./attribute-edits";

export interface AttributeInspectorProps {
  attribute: AttributeSpec;
  allAttributes: AttributeSpec[];
  onPatch: (patch: Partial<AttributeSpec>) => void;
  /** Moves `attribute` into a (possibly new) section — routed separately from
   * `onPatch` because it must renumber `order` (via `moveAttribute`), not
   * just overwrite the field. */
  onSectionChange: (nextSection: string) => void;
  readOnly: boolean;
}

export function AttributeInspector({
  attribute,
  allAttributes,
  onPatch,
  onSectionChange,
  readOnly,
}: AttributeInspectorProps): JSX.Element {
  const { t } = useTranslation();
  const frozen = (property: keyof AttributeSpec): boolean =>
    readOnly || isMetaPropertyLocked(attribute, property);

  return (
    <aside className={styles.inspector} data-testid="attribute-inspector">
      <h3>{attribute.name}</h3>
      {attribute.locked ? (
        <p title={t("attributes.lockedHint")}>
          <Lock aria-hidden="true" size={14} /> {t("attributes.lockedHint")}
        </p>
      ) : null}

      <label className={styles.field}>
        <span>{t("attributes.visible")}</span>
        <input
          type="checkbox"
          data-testid="attribute-inspector-visible"
          checked={attribute.visible}
          disabled={frozen("visible")}
          onChange={(event) => onPatch({ visible: event.target.checked })}
        />
      </label>

      <label className={styles.field}>
        <span>{t("attributes.required")}</span>
        <input
          type="checkbox"
          data-testid="attribute-inspector-required"
          checked={attribute.required}
          disabled={frozen("required")}
          onChange={(event) => onPatch({ required: event.target.checked })}
        />
      </label>

      <label className={styles.field}>
        <span>{t("attributes.expertOnly")}</span>
        <input
          type="checkbox"
          data-testid="attribute-inspector-audience"
          checked={attribute.audience === "expert"}
          disabled={readOnly}
          onChange={(event) =>
            onPatch({ audience: event.target.checked ? "expert" : "basic" })
          }
        />
      </label>

      <label className={styles.field}>
        <span>{t("attributes.section")}</span>
        <input
          className={styles.control}
          type="text"
          list="attribute-sections"
          data-testid="attribute-inspector-section"
          value={attribute.section}
          disabled={readOnly}
          onChange={(event) => onSectionChange(event.target.value)}
        />
        <datalist id="attribute-sections">
          {sectionNames(allAttributes).map((section) => (
            <option key={section} value={section} />
          ))}
        </datalist>
      </label>

      <label className={styles.field}>
        <span>{t("attributes.labelDe")}</span>
        <input
          className={styles.control}
          type="text"
          data-testid="attribute-inspector-label-de"
          value={attribute.label.de}
          disabled={readOnly}
          onChange={(event) =>
            onPatch({ label: { ...attribute.label, de: event.target.value } })
          }
        />
      </label>

      <label className={styles.field}>
        <span>{t("attributes.labelEn")}</span>
        <input
          className={styles.control}
          type="text"
          data-testid="attribute-inspector-label-en"
          value={attribute.label.en}
          disabled={readOnly}
          onChange={(event) =>
            onPatch({ label: { ...attribute.label, en: event.target.value } })
          }
        />
      </label>

      <label className={styles.field}>
        <span>{t("attributes.aiElicit")}</span>
        <input
          type="checkbox"
          data-testid="attribute-inspector-ai-elicit"
          checked={attribute.ai_elicit}
          disabled={readOnly}
          onChange={(event) => onPatch({ ai_elicit: event.target.checked })}
        />
      </label>

      <label className={styles.field}>
        <span>{t("attributes.export")}</span>
        <input
          type="checkbox"
          data-testid="attribute-inspector-export"
          checked={attribute.export}
          disabled={readOnly}
          onChange={(event) => onPatch({ export: event.target.checked })}
        />
      </label>
    </aside>
  );
}
