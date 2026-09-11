/**
 * AttributeTable (Task 4, spec section 4.2) — column view alternative to
 * AttributeList. Reads the same resolved-definition state the list view
 * does; sorting is client-side and intentionally does not persist (order
 * only matters for the list view's section layout).
 */

import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import type { AttributeOrigin, AttributeSpec } from "../../api/attribute-definitions";
import styles from "./AttributeEditor.module.css";

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
      <thead>
        <tr>
          {COLUMNS.map((column) => (
            <th
              key={column}
              data-testid={`attribute-table-sort-${column}`}
              onClick={() => handleSort(column)}
            >
              {t(column === "origin" ? "attributes.table.originHeader" : `attributes.table.${column}`)}
              {sortKey === column ? (ascending ? " ▲" : " ▼") : ""}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {sorted.map(({ attribute, origin }) => (
          <tr
            key={attribute.name}
            data-testid={`attribute-table-row-${attribute.name}`}
            className={selected === attribute.name ? styles.rowSelected : ""}
            onClick={() => onSelect(attribute.name)}
          >
            <td>{attribute.name}</td>
            <td>{t(`attributes.types.${attribute.type}`, { defaultValue: attribute.type })}</td>
            <td>{attribute.section}</td>
            <td>
              <input type="checkbox" checked={attribute.required} readOnly />
            </td>
            <td>
              <input type="checkbox" checked={attribute.visible} readOnly />
            </td>
            <td>{attribute.audience}</td>
            <td>{t(`attributes.table.origin.${origin}`)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
