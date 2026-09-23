/**
 * REQ-178 — PresetSegmentedControl: 3-way preset selector for global workflow
 * defaults (SCR-205). A compact sibling of the Settings underline-tab pattern
 * (``role="tablist"``/``role="tab"``), rendered only in the editor's
 * ``scope="global"`` mode where a default is defined PER preset.
 *
 * No new design-system primitive: styling reuses the same token vocabulary and
 * underline-on-active treatment as ``WorkspaceSettings`` tabs, at a smaller
 * scale.
 */

import { useTranslation } from "react-i18next";
import type { WorkspacePreset } from "../../types";
import { WORKFLOW_PRESETS } from "./constants";
import { handleTablistKeyDown, tabRovingTabIndex } from "../shared/tablistKeyboardNav";
import styles from "./PresetSegmentedControl.module.css";

interface PresetSegmentedControlProps {
  value: WorkspacePreset;
  onChange: (preset: WorkspacePreset) => void;
}

export function PresetSegmentedControl({
  value,
  onChange,
}: PresetSegmentedControlProps): JSX.Element {
  const { t } = useTranslation();
  return (
    <div
      role="tablist"
      aria-label={t("workflow.preset.ariaLabel")}
      data-testid="workflow-preset-selector"
      onKeyDown={(e) => handleTablistKeyDown(e, WORKFLOW_PRESETS, value, onChange)}
      className={styles.tablist}
    >
      {WORKFLOW_PRESETS.map((preset) => {
        const isActive = preset === value;
        return (
          <button
            key={preset}
            type="button"
            role="tab"
            aria-selected={isActive}
            tabIndex={tabRovingTabIndex(preset, value)}
            data-testid={`workflow-preset-option-${preset}`}
            onClick={() => onChange(preset)}
            className={styles.tab}
          >
            {preset}
          </button>
        );
      })}
    </div>
  );
}
