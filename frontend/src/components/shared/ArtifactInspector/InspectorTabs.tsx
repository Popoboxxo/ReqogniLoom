/**
 * ArtifactInspector — tablist with **manual** activation (issue #1762, M1).
 *
 * leaf_id: COMP-RF-014 (ArtifactInspector)
 * req_id:  REQ-L1-089, REQ-L1-093
 *
 * APG *tabs* has two activation models. The shared helper
 * `shared/tablistKeyboardNav.ts` implements the automatic one — every arrow
 * key calls `onChange` — which is right for the settings tabs and wrong here:
 * each tab of this inspector triggers a fetch (versions, diff, links,
 * comments), so browsing four tabs with the arrow keys would fire four
 * requests (spec §5.1/§5.2).
 *
 * Therefore:
 *  - `←`/`→`/`Home`/`End` move focus only — no `onChange`, no fetch;
 *  - `Enter`/`Space` activate the focused tab — exactly one fetch;
 *  - focus stays on the activated tab (it does not jump into the panel).
 *
 * Inactive panels are not rendered at all (a stricter stance than `hidden`):
 * "exactly one fetch per activation" is only true if the inactive areas are
 * not mounted.
 */

import { useRef } from "react";
import { useTranslation } from "react-i18next";

import {
  INSPECTOR_TEST_IDS,
  inspectorPanelId,
  inspectorTabId,
  type InspectorTabKey,
} from "./inspectorContract";
import styles from "./InspectorShell.module.css";

const TAB_LABEL_KEYS: Record<InspectorTabKey, { key: string; fallback: string }> = {
  version: { key: "sidebar.version.title", fallback: "Version" },
  diff: { key: "sidebar.diff.title", fallback: "Diff" },
  links: { key: "sidebar.inspector.tab.links", fallback: "Links" },
  comments: { key: "comments.heading", fallback: "Comments" },
};

export interface InspectorTabsProps {
  tabs: readonly InspectorTabKey[];
  activeTab: InspectorTabKey;
  onActivate: (tab: InspectorTabKey) => void;
}

export function InspectorTabs({
  tabs,
  activeTab,
  onActivate,
}: InspectorTabsProps): JSX.Element {
  const { t } = useTranslation();
  const tabRefs = useRef<Partial<Record<InspectorTabKey, HTMLButtonElement | null>>>({});

  function focusTab(key: InspectorTabKey): void {
    tabRefs.current[key]?.focus();
  }

  function onKeyDown(event: React.KeyboardEvent<HTMLButtonElement>, index: number): void {
    const last = tabs.length - 1;
    let nextIndex: number | null = null;
    if (event.key === "ArrowRight") nextIndex = index === last ? 0 : index + 1;
    else if (event.key === "ArrowLeft") nextIndex = index === 0 ? last : index - 1;
    else if (event.key === "Home") nextIndex = 0;
    else if (event.key === "End") nextIndex = last;

    if (nextIndex !== null) {
      event.preventDefault();
      const nextKey = tabs[nextIndex];
      if (nextKey) focusTab(nextKey);
      return;
    }

    if (event.key === "Enter" || event.key === " ") {
      // Manual activation: the button's own click handler runs `onActivate`.
      // handled centrally here so the panel never mounts on focus alone.
      event.preventDefault();
      onActivate(tabs[index] ?? activeTab);
    }
  }

  return (
    <div
      role="tablist"
      aria-label={t("sidebar.inspector.title")}
      className={styles.tabList}
      data-testid={INSPECTOR_TEST_IDS.tabs}
    >
      {tabs.map((key, index) => {
        const label = TAB_LABEL_KEYS[key];
        const selected = key === activeTab;
        return (
          <button
            key={key}
            ref={(element): void => {
              tabRefs.current[key] = element;
            }}
            type="button"
            role="tab"
            id={inspectorTabId(key)}
            aria-selected={selected}
            aria-controls={inspectorPanelId(key)}
            // Roving tabindex: only the selected tab is in the tab order; the
            // others are reachable with the arrow keys (spec §7 Id contract).
            tabIndex={selected ? 0 : -1}
            className={`btn-tab ${styles.tabBtn}`}
            onClick={(): void => onActivate(key)}
            onKeyDown={(event): void => onKeyDown(event, index)}
            data-testid={INSPECTOR_TEST_IDS.tab(key)}
          >
            {t(label.key, label.fallback)}
          </button>
        );
      })}
    </div>
  );
}
