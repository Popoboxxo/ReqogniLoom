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
      style={{
        display: "inline-flex",
        gap: "var(--space-1)",
        borderBottom: "1px solid var(--color-border)",
      }}
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
            style={{
              appearance: "none",
              background: "transparent",
              border: "none",
              borderBottom: isActive
                ? "2px solid var(--color-primary)"
                : "2px solid transparent",
              color: isActive ? "var(--color-text)" : "var(--color-text-muted)",
              fontWeight: isActive ? 600 : 500,
              fontSize: "var(--font-size-xs)",
              padding: "var(--space-1) var(--space-3)",
              marginBottom: "-1px",
              cursor: "pointer",
              textTransform: "capitalize",
            }}
          >
            {preset}
          </button>
        );
      })}
    </div>
  );
}
