/**
 * Per-attribute meta-property editor (Task 26, spec section 6.1). Every
 * control it renders is one the backend accepts for that attribute —
 * `isMetaPropertyLocked` mirrors `validate_meta_only_change`, so the UI never
 * offers an edit that would 400.
 */

import { useTranslation } from "react-i18next";
import { Lock, ChevronDown, ChevronUp, Trash2 } from "lucide-react";

import type { AttributeOption, AttributeSpec } from "../../api/attribute-definitions";
import styles from "./AttributeEditor.module.css";
import { isMetaPropertyLocked, sectionNames } from "./attribute-edits";

const ENUM_TYPES = new Set(["enum", "multi-enum"]);

export interface AttributeInspectorProps {
  attribute: AttributeSpec;
  allAttributes: AttributeSpec[];
  onPatch: (patch: Partial<AttributeSpec>) => void;
  /** Moves `attribute` into a (possibly new) section — routed separately from
   * `onPatch` because it must renumber `order` (via `moveAttribute`), not
   * just overwrite the field. */
  onSectionChange: (nextSection: string) => void;
  /** Task 6: removing an option is routed here instead of straight through
   * `onPatch` — the caller checks `count_usages(..., option_value)` and
   * confirms before the actual removal (mirrors Task 5's delete-attribute
   * flow, which needs the same server round-trip this pure component has no
   * business making). Add/edit/reorder stay local `onPatch` calls: they
   * never destroy data, so they need no confirmation. */
  onRequestRemoveOption: (optionValue: string) => void;
  readOnly: boolean;
}

export function AttributeInspector({
  attribute,
  allAttributes,
  onPatch,
  onSectionChange,
  onRequestRemoveOption,
  readOnly,
}: AttributeInspectorProps): JSX.Element {
  const { t } = useTranslation();
  const frozen = (property: keyof AttributeSpec): boolean =>
    readOnly || isMetaPropertyLocked(attribute, property);

  const patchOption = (index: number, patch: Partial<AttributeOption>): void => {
    onPatch({
      options: attribute.options.map((option, i) =>
        i === index ? { ...option, ...patch } : option
      ),
    });
  };

  const moveOption = (index: number, toIndex: number): void => {
    if (toIndex < 0 || toIndex >= attribute.options.length) return;
    const next = [...attribute.options];
    [next[index], next[toIndex]] = [next[toIndex], next[index]];
    onPatch({ options: next });
  };

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

      {ENUM_TYPES.has(attribute.type) ? (
        <div className={styles.field} data-testid="attribute-inspector-options">
          <span>{t("attributes.options.title")}</span>
          {attribute.options.map((option, index) => (
            <div key={index} className={styles.optionRow}>
              <input
                className={styles.control}
                type="text"
                placeholder={t("attributes.options.value")}
                data-testid={`attribute-inspector-option-${index}-value`}
                value={option.value}
                disabled={readOnly}
                onChange={(event) => patchOption(index, { value: event.target.value })}
              />
              <input
                className={styles.control}
                type="text"
                placeholder={t("attributes.options.labelDe")}
                data-testid={`attribute-inspector-option-${index}-label-de`}
                value={option.label_de}
                disabled={readOnly}
                onChange={(event) => patchOption(index, { label_de: event.target.value })}
              />
              <input
                className={styles.control}
                type="text"
                placeholder={t("attributes.options.labelEn")}
                data-testid={`attribute-inspector-option-${index}-label-en`}
                value={option.label_en}
                disabled={readOnly}
                onChange={(event) => patchOption(index, { label_en: event.target.value })}
              />
              <button
                type="button"
                disabled={readOnly || index === 0}
                aria-label={t("attributes.moveUp")}
                data-testid={`attribute-inspector-option-${index}-up`}
                onClick={() => moveOption(index, index - 1)}
              >
                <ChevronUp aria-hidden="true" size={14} />
              </button>
              <button
                type="button"
                disabled={readOnly || index === attribute.options.length - 1}
                aria-label={t("attributes.moveDown")}
                data-testid={`attribute-inspector-option-${index}-down`}
                onClick={() => moveOption(index, index + 1)}
              >
                <ChevronDown aria-hidden="true" size={14} />
              </button>
              <button
                type="button"
                disabled={readOnly}
                aria-label={t("attributes.options.remove")}
                data-testid={`attribute-inspector-option-${index}-remove`}
                onClick={() => onRequestRemoveOption(option.value)}
              >
                <Trash2 aria-hidden="true" size={14} />
              </button>
            </div>
          ))}
          <button
            type="button"
            disabled={readOnly}
            data-testid="attribute-inspector-option-add"
            onClick={() =>
              onPatch({
                options: [...attribute.options, { value: "", label_de: "", label_en: "" }],
              })
            }
          >
            {t("attributes.options.add")}
          </button>
        </div>
      ) : null}
    </aside>
  );
}
