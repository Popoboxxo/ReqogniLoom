/**
 * Section + attribute list with native HTML5 drag reorder (Task 26, spec
 * section 6.1).
 *
 * Native drag events on purpose: one reorderable list does not justify a
 * drag-and-drop dependency, and the browser already gives keyboard users the
 * up/down buttons rendered alongside.
 */

import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { ChevronDown, ChevronUp, Lock, Pencil, Trash2 } from "lucide-react";

import type { AttributeSpec, SectionLayout, SectionSpec } from "../../api/attribute-definitions";
import styles from "./AttributeEditor.module.css";
import { sectionNames } from "./attribute-edits";

export interface AttributeListProps {
  attributes: AttributeSpec[];
  /** Task 8: visibility/layout per section. A name absent here defaults to
   * visible/full, same "additive" convention the backend uses. */
  sections: SectionSpec[];
  /** Sections with no attributes — they exist only in editor state until a
   *  field is dragged/moved into them, so the list must be told about them. */
  emptySections: string[];
  selected: string | null;
  onSelect: (name: string) => void;
  onMove: (name: string, toSection: string, toIndex: number) => void;
  onRenameSection: (from: string, to: string) => void;
  onDeleteSection: (name: string) => void;
  onMoveSection: (name: string, toIndex: number) => void;
  onAddAttribute: (section: string) => void;
  /** Only ever offered for `kind: "extended"` attributes — a core attribute
   * is always rejected server-side, so the row never renders the button for
   * one (Task 5). */
  onDeleteAttribute: (name: string) => void;
  onToggleSectionVisible: (name: string) => void;
  onSetSectionLayout: (name: string, layout: SectionLayout) => void;
  readOnly: boolean;
}

export function AttributeList({
  attributes,
  sections,
  emptySections,
  selected,
  onSelect,
  onMove,
  onRenameSection,
  onDeleteSection,
  onMoveSection,
  onAddAttribute,
  onDeleteAttribute,
  onToggleSectionVisible,
  onSetSectionLayout,
  readOnly,
}: AttributeListProps): JSX.Element {
  const { t } = useTranslation();
  const [dragging, setDragging] = useState<string | null>(null);
  const [renaming, setRenaming] = useState<string | null>(null);

  const allSections = useMemo(() => {
    const populated = sectionNames(attributes);
    return [...populated, ...emptySections.filter((s) => !populated.includes(s))];
  }, [attributes, emptySections]);

  const sectionMeta = useMemo(() => {
    const map = new Map<string, SectionSpec>();
    for (const s of sections) map.set(s.name, s);
    return map;
  }, [sections]);

  return (
    <div className={styles.list}>
      {allSections.map((section, sectionIndex) => {
        const rows = attributes.filter((a) => a.section === section);
        return (
          <section
            key={section}
            className={styles.section}
            data-testid={`attribute-section-${section}`}
            onDragOver={(event) => event.preventDefault()}
            onDrop={() => {
              if (dragging && !readOnly) onMove(dragging, section, rows.length);
              setDragging(null);
            }}
          >
            <div className={styles.sectionHeader}>
              {renaming === section ? (
                <input
                  className={styles.control}
                  data-testid={`attribute-section-${section}-name`}
                  defaultValue={section}
                  autoFocus
                  onBlur={(event) => {
                    onRenameSection(section, event.target.value);
                    setRenaming(null);
                  }}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") {
                      onRenameSection(section, event.currentTarget.value);
                      setRenaming(null);
                    }
                    if (event.key === "Escape") setRenaming(null);
                  }}
                />
              ) : (
                <h3>{t(`sections.${section}`, { defaultValue: section })}</h3>
              )}
              <span className={styles.badges}>
                <button
                  type="button"
                  disabled={readOnly}
                  data-testid={`attribute-section-${section}-rename`}
                  aria-label={t("attributes.renameSection")}
                  onClick={() => setRenaming(section)}
                >
                  <Pencil aria-hidden="true" size={14} />
                </button>
                <label>
                  <input
                    type="checkbox"
                    data-testid={`attribute-section-${section}-visible`}
                    checked={sectionMeta.get(section)?.visible ?? true}
                    disabled={readOnly}
                    aria-label={t("attributes.sectionVisible")}
                    onChange={() => onToggleSectionVisible(section)}
                  />
                </label>
                <select
                  data-testid={`attribute-section-${section}-layout`}
                  value={sectionMeta.get(section)?.layout ?? "full"}
                  disabled={readOnly}
                  aria-label={t("attributes.sectionLayout")}
                  onChange={(event) =>
                    onSetSectionLayout(section, event.target.value as "full" | "half")
                  }
                >
                  <option value="full">{t("attributes.sectionLayoutFull")}</option>
                  <option value="half">{t("attributes.sectionLayoutHalf")}</option>
                </select>
                <button
                  type="button"
                  disabled={readOnly || sectionIndex === 0}
                  data-testid={`attribute-section-${section}-up`}
                  aria-label={t("attributes.moveSectionUp")}
                  onClick={() => onMoveSection(section, sectionIndex - 1)}
                >
                  <ChevronUp aria-hidden="true" size={14} />
                </button>
                <button
                  type="button"
                  disabled={readOnly || sectionIndex === allSections.length - 1}
                  data-testid={`attribute-section-${section}-down`}
                  aria-label={t("attributes.moveSectionDown")}
                  onClick={() => onMoveSection(section, sectionIndex + 1)}
                >
                  <ChevronDown aria-hidden="true" size={14} />
                </button>
                <button
                  type="button"
                  disabled={readOnly}
                  data-testid={`attribute-section-${section}-delete`}
                  aria-label={t("attributes.deleteSection")}
                  onClick={() => onDeleteSection(section)}
                >
                  <Trash2 aria-hidden="true" size={14} />
                </button>
                <button
                  type="button"
                  disabled={readOnly}
                  data-testid={`attribute-section-${section}-add`}
                  onClick={() => onAddAttribute(section)}
                >
                  {t("attributes.addAttribute")}
                </button>
              </span>
            </div>
            {rows.map((attribute, index) => (
              <div
                key={attribute.name}
                role="button"
                tabIndex={0}
                data-testid={`attribute-row-${attribute.name}`}
                className={`${styles.row} ${
                  selected === attribute.name ? styles.rowSelected : ""
                } ${attribute.locked ? styles.rowLocked : ""}`}
                draggable={!readOnly}
                onDragStart={() => setDragging(attribute.name)}
                onDragOver={(event) => event.preventDefault()}
                onDrop={(event) => {
                  event.stopPropagation();
                  if (dragging && !readOnly) onMove(dragging, section, index);
                  setDragging(null);
                }}
                onClick={() => onSelect(attribute.name)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    onSelect(attribute.name);
                  }
                }}
              >
                <span>{attribute.label.en || attribute.name}</span>
                <span className={styles.badges}>
                  {attribute.locked ? (
                    <Lock
                      aria-hidden="true"
                      size={14}
                      data-testid={`attribute-row-${attribute.name}-lock`}
                    />
                  ) : (
                    <>
                      <input
                        type="checkbox"
                        data-testid={`attribute-row-${attribute.name}-visible`}
                        checked={attribute.visible}
                        readOnly
                        aria-label={t("attributes.visible")}
                      />
                      <input
                        type="checkbox"
                        data-testid={`attribute-row-${attribute.name}-required`}
                        checked={attribute.required}
                        readOnly
                        aria-label={t("attributes.required")}
                      />
                    </>
                  )}
                  <button
                    type="button"
                    disabled={readOnly || index === 0}
                    aria-label={t("attributes.moveUp")}
                    data-testid={`attribute-row-${attribute.name}-up`}
                    onClick={(event) => {
                      event.stopPropagation();
                      onMove(attribute.name, section, index - 1);
                    }}
                  >
                    <ChevronUp aria-hidden="true" size={14} />
                  </button>
                  <button
                    type="button"
                    disabled={readOnly || index === rows.length - 1}
                    aria-label={t("attributes.moveDown")}
                    data-testid={`attribute-row-${attribute.name}-down`}
                    onClick={(event) => {
                      event.stopPropagation();
                      onMove(attribute.name, section, index + 1);
                    }}
                  >
                    <ChevronDown aria-hidden="true" size={14} />
                  </button>
                  {attribute.kind === "extended" ? (
                    <button
                      type="button"
                      disabled={readOnly}
                      aria-label={t("attributes.deleteAttribute.action")}
                      data-testid={`attribute-row-${attribute.name}-delete`}
                      onClick={(event) => {
                        event.stopPropagation();
                        onDeleteAttribute(attribute.name);
                      }}
                    >
                      <Trash2 aria-hidden="true" size={14} />
                    </button>
                  ) : null}
                </span>
              </div>
            ))}
          </section>
        );
      })}
    </div>
  );
}
