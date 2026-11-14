/**
 * ArtifactInspector — the rail (issue #1762, M1).
 *
 * leaf_id: COMP-RF-014 (ArtifactInspector)
 * req_id:  REQ-L1-089, REQ-L1-093
 *
 * The collapsed state of the shell (spec §2.1, §3): a 40 px strip whose whole
 * job is to keep the inspector's function visible and its numbers readable
 * while the detail content has the room.
 *
 * Every counter is a real `<button>` — not a `<span>` — because clicking it
 * has to open the inspector **on that tab** (spec §3). The visible `V`/`D`/
 * `L`/`K` abbreviation is `aria-hidden`; the accessible name comes entirely
 * from the localised `aria-label` ("Kommentare, 3 offen"). Reading "V 9" out
 * loud was the defect this replaces (WCAG 4.1.2, I-20).
 *
 * Rail and sheet are one DOM node in two states (spec §2.1): when the sheet is
 * open this component is not rendered at all, so no second, invisible set of
 * counters exists in the accessibility tree.
 */

import { useTranslation } from "react-i18next";
import { ChevronLeft } from "lucide-react";

import {
  INSPECTOR_SURFACE_ID,
  INSPECTOR_TEST_IDS,
  inspectorTabLabelKey,
  type InspectorTabKey,
} from "./inspectorContract";
import type { ArtifactKind } from "./types";
import styles from "./InspectorShell.module.css";

/** Abbreviation per tab (spec §3 "V/D/L/K"). */
const RAIL_GLYPHS: Record<InspectorTabKey, string> = {
  version: "V",
  diff: "D",
  links: "L",
  comments: "K",
};

const TAB_LABEL_FALLBACKS: Record<InspectorTabKey, string> = {
  version: "Version",
  diff: "Diff",
  links: "Links",
  comments: "Comments",
};

export interface InspectorRailProps {
  /** The inspected kind — only the Links label depends on it (glossary). */
  kind: ArtifactKind;
  /** Tab keys this artifact actually has (comments may be absent). */
  tabs: readonly InspectorTabKey[];
  /** Known counter per tab; `undefined` renders the spec's `0`, not a gap. */
  counts: Partial<Record<InspectorTabKey, number>>;
  /** Which tab the panel will open on — pressing a counter also selects it. */
  activeTab: InspectorTabKey;
  /** Open the inspector, on `tab`. */
  onOpen: (tab: InspectorTabKey) => void;
}

export function InspectorRail({
  kind,
  tabs,
  counts,
  activeTab,
  onOpen,
}: InspectorRailProps): JSX.Element {
  const { t } = useTranslation();

  const tabLabel = (key: InspectorTabKey): string =>
    t(inspectorTabLabelKey(kind, key), TAB_LABEL_FALLBACKS[key]);

  return (
    <div className={styles.rail} data-testid="inspector-rail">
      <button
        type="button"
        className={`btn-icon ${styles.railButton}`}
        aria-label={t("sidebar.inspector.expand")}
        title={t("sidebar.inspector.expand")}
        aria-expanded={false}
        aria-controls={INSPECTOR_SURFACE_ID}
        onClick={(): void => onOpen(activeTab)}
        data-testid="inspector-rail-open"
      >
        <ChevronLeft aria-hidden="true" size={16} />
      </button>

      {tabs.map((key) => {
        const count = counts[key] ?? 0;
        return (
          <button
            key={key}
            type="button"
            className={`btn-icon ${styles.railButton}`}
            aria-label={t("sidebar.inspector.railCount", {
              tab: tabLabel(key),
              open: count,
              defaultValue: `${tabLabel(key)}, ${count}`,
            })}
            title={t("sidebar.inspector.railCount", {
              tab: tabLabel(key),
              open: count,
              defaultValue: `${tabLabel(key)}, ${count}`,
            })}
            aria-controls={INSPECTOR_SURFACE_ID}
            onClick={(): void => onOpen(key)}
            data-testid={INSPECTOR_TEST_IDS.railCount(key)}
          >
            <span className={styles.railGlyph} aria-hidden="true">
              {RAIL_GLYPHS[key]}
            </span>
            <span className={styles.railCount}>{count}</span>
          </button>
        );
      })}
    </div>
  );
}
