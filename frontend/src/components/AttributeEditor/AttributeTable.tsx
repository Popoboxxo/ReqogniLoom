/**
 * AttributeTable (Task 4, spec section 4.2) — column view alternative to
 * AttributeList. Reads the same resolved-definition state the list view
 * does; sorting is client-side and intentionally does not persist (order
 * only matters for the list view's section layout).
 */

import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import type { AttributeOrigin, AttributeSpec } from "../../api/attribute-definitions";
import { useActivationKeys } from "../../hooks/useActivationKeys";
import styles from "./AttributeEditor.module.css";
import { ATTRIBUTE_TYPE_ICONS } from "./attribute-type-icons";

const ORIGIN_BADGE_CLASS: Record<AttributeOrigin, string | undefined> = {
  global: undefined,
  global_customized: "originBadgeCustomized",
  workspace_only: "originBadgeWorkspaceOnly",
};

export interface AttributeTableProps {
  attributes: AttributeSpec[];
  /** `attribute.name` -> origin. Omitted in global scope, where every row is
   * simply "global". */
  origins?: Record<string, AttributeOrigin>;
  selected: string | null;
  onSelect: (name: string) => void;
}

type SortKey = "name" | "type" | "section" | "required" | "visible" | "audience" | "origin";

const COLUMNS: SortKey[] = [
  "name", "type", "section", "required", "visible", "audience", "origin",
];

function sortValue(
  attribute: AttributeSpec,
  origin: AttributeOrigin,
  key: SortKey
): string | number {
  switch (key) {
    case "required":
    case "visible":
      return attribute[key] ? 1 : 0;
    case "origin":
      return origin;
    default:
      return attribute[key];
  }
}

interface AttributeTableRowProps {
  attribute: AttributeSpec;
  origin: AttributeOrigin;
  selected: boolean;
  onSelect: (name: string) => void;
}

/**
 * A row is a native table row — it keeps its table semantics and is made
 * keyboard-operable by the shared activation contract. Previously this row
 * carried a bare `onClick` with no `tabIndex`/`onKeyDown` at all (UI-006), so
 * the whole hit area was unreachable without a pointer.
 */
function AttributeTableRow({
  attribute,
  origin,
  selected,
  onSelect,
}: AttributeTableRowProps): JSX.Element {
  const { t } = useTranslation();
  const activation = useActivationKeys(() => onSelect(attribute.name));
  const TypeIcon = ATTRIBUTE_TYPE_ICONS[attribute.type];
  const originModifier = ORIGIN_BADGE_CLASS[origin];

  return (
    <tr
      key={attribute.name}
      data-testid={`attribute-table-row-${attribute.name}`}
      className={selected ? styles.rowSelected : ""}
      {...activation}
    >
      <td>{attribute.name}</td>
      <td>
        <TypeIcon
          aria-hidden="true"
          size={14}
          className={styles.typeIcon}
          data-testid={`attribute-table-row-${attribute.name}-type-icon`}
        />
        {t(`attributes.types.${attribute.type}`, { defaultValue: attribute.type })}
      </td>
      <td>{attribute.section}</td>
      <td>
        <input type="checkbox" checked={attribute.required} readOnly />
      </td>
      <td>
        <input type="checkbox" checked={attribute.visible} readOnly />
      </td>
      <td>{attribute.audience}</td>
      <td>
        <span
          className={`${styles.originBadge} ${
            originModifier ? styles[originModifier] : ""
          }`}
        >
          {t(`attributes.table.origin.${origin}`)}
        </span>
      </td>
    </tr>
  );
}

export function AttributeTable({
  attributes,
  origins,
  selected,
  onSelect,
}: AttributeTableProps): JSX.Element {
  const { t } = useTranslation();
  const [sortKey, setSortKey] = useState<SortKey>("name");
  const [ascending, setAscending] = useState(true);

  const handleSort = (key: SortKey): void => {
    if (key === sortKey) {
      setAscending((current) => !current);
    } else {
      setSortKey(key);
      setAscending(true);
    }
  };

  const sorted = useMemo(() => {
    const withOrigin = attributes.map((attribute) => ({
      attribute,
      origin: origins?.[attribute.name] ?? "global",
    }));
    withOrigin.sort((a, b) => {
      const left = sortValue(a.attribute, a.origin, sortKey);
      const right = sortValue(b.attribute, b.origin, sortKey);
      const direction = ascending ? 1 : -1;
      return left < right ? -direction : left > right ? direction : 0;
    });
    return withOrigin;
  }, [attributes, origins, sortKey, ascending]);

  return (
    <table className={styles.table} data-testid="attribute-table">
      <caption className="visually-hidden">
        {t("common.tableCaption")}
      </caption>
      <thead>
        <tr>
          {COLUMNS.map((column) => (
            <th key={column} scope="col">
              {/* UI-006: a sortable header is a real button (native Enter/Space
                  activation, announced as a control) inside the native header
                  cell,
                  mirroring shared/ArtifactTable's sort-header pattern. The
                  design-system ratchet no longer needs a row-part exemption.
                  The stable test id moves to the control so existing click
                  assertions keep hitting the activated element. */}
              <button
                type="button"
                className="btn-ghost btn-sm"
                data-testid={`attribute-table-sort-${column}`}
                onClick={() => handleSort(column)}
              >
                {t(column === "origin" ? "attributes.table.originHeader" : `attributes.table.${column}`)}
                {sortKey === column ? (ascending ? " ▲" : " ▼") : ""}
              </button>
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {sorted.map(({ attribute, origin }) => (
          <AttributeTableRow
            key={attribute.name}
            attribute={attribute}
            origin={origin}
            selected={selected === attribute.name}
            onSelect={onSelect}
          />
        ))}
      </tbody>
    </table>
  );
}
