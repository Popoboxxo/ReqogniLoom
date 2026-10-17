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

import type {
  AttributeOrigin,
  AttributeSpec,
  SectionLayout,
  SectionSpec,
} from "../../api/attribute-definitions";
import styles from "./AttributeEditor.module.css";
import { sectionNames } from "./attribute-edits";
import { ATTRIBUTE_TYPE_ICONS } from "./attribute-type-icons";

const ORIGIN_BADGE_CLASS: Record<AttributeOrigin, string | undefined> = {
  global: undefined,
  global_customized: "originBadgeCustomized",
  workspace_only: "originBadgeWorkspaceOnly",
};

export interface AttributeListProps {
  attributes: AttributeSpec[];
  /** Task 8: visibility/layout per section. A name absent here defaults to
   * visible/full, same "additive" convention the backend uses. */
  sections: SectionSpec[];
  /** Task 4/12: `attribute.name` -> origin, for the badge next to each row.
   * Omitted in global scope, where every row is simply "global" (same
   * optionality as AttributeTable's identical prop). */
  origins?: Record<string, AttributeOrigin>;
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
  origins,
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
          // Pointer-only drop target: the section accepts a dragged row, and
          // HTML5 drag-and-drop has no keyboard trigger by construction. The
          // keyboard path for reordering is the explicit controls the section
          // already renders — per-row up/down buttons and the move-to-section
          // select (feature #1260) — so this element adds no unreachable
          // action.
          // eslint-disable-next-line jsx-a11y/no-static-element-interactions
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
                <span className={styles.badges}>
                  {(() => {
                    const TypeIcon = ATTRIBUTE_TYPE_ICONS[attribute.type];
                    return (
                      <TypeIcon
                        aria-hidden="true"
                        size={14}
                        className={styles.typeIcon}
                        data-testid={`attribute-row-${attribute.name}-type-icon`}
                      />
                    );
                  })()}
                  <span>{attribute.label.en || attribute.name}</span>
                  {(() => {
                    const origin = origins?.[attribute.name] ?? "global";
                    const modifier = ORIGIN_BADGE_CLASS[origin];
                    return (
                      <span
                        className={`${styles.originBadge} ${modifier ? styles[modifier] : ""}`}
                        data-testid={`attribute-row-${attribute.name}-origin`}
                      >
                        {t(`attributes.table.origin.${origin}`)}
                      </span>
                    );
                  })()}
                </span>
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
                  {/* Feature #1260: the keyboard path for a CROSS-section move.
                      Up/down only walk within a section, so without this a
                      keyboard-only user could never reach another section —
                      drag & drop alone is not accessible (WCAG 2.1). Moving to
                      another section appends at its end; up/down then refine
                      the position. No onClick handler on purpose: it would make
                      the ratchet see a second "button" and the row's own click
                      (selecting the row) is harmless here. */}
                  <select
                    data-testid={`attribute-row-${attribute.name}-section`}
                    value={attribute.section}
                    disabled={readOnly}
                    aria-label={t("attributes.moveToSection")}
                    onChange={(event) =>
                      onMove(attribute.name, event.target.value, Number.MAX_SAFE_INTEGER)
                    }
                  >
                    {allSections.map((candidate) => (
                      <option key={candidate} value={candidate}>
                        {t(`sections.${candidate}`, { defaultValue: candidate })}
                      </option>
                    ))}
                  </select>
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
