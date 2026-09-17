/**
 * REQ-176 — EntityTypeSelector: left panel listing the 7 workflow entity types.
 *
 * Each item shows the entity name and its state count in the active preset, and
 * a preset badge sits at the panel footer (design brief §4). The per-item state
 * count is read via the same cached ``useWorkflowData`` query the canvas uses,
 * so selecting an entity never triggers a second fetch.
 */

import { useTranslation } from "react-i18next";
import { Layers } from "lucide-react";
import { useWorkspace } from "../../context/WorkspaceContext";
import type { WorkflowEntityType } from "../../api/workflows";
import { WORKFLOW_ENTITY_TYPES, type WorkflowScope } from "./constants";
import { useWorkflowData } from "./useWorkflowData";
import styles from "./WorkflowEditor.module.css";

interface EntityTypeSelectorProps {
  selected: WorkflowEntityType;
  onSelect: (type: WorkflowEntityType) => void;
  /** Scope the counts/initialized dots are read for (default: workspace). */
  scope?: WorkflowScope;
}

interface EntityTypeItemProps {
  type: WorkflowEntityType;
  label: string;
  active: boolean;
  onSelect: (type: WorkflowEntityType) => void;
  scope?: WorkflowScope;
}

function EntityTypeItem({
  type,
  label,
  active,
  onSelect,
  scope,
}: EntityTypeItemProps): JSX.Element {
  const { t } = useTranslation();
  const { graph, isLoading } = useWorkflowData(type, scope);
  const count = graph?.states.length ?? 0;
  // In global scope, flag not-yet-seeded presets so the admin sees where to
  // initialize (SCR-205); in workspace scope the count already conveys this.
  const notInitialized =
    scope?.kind === "global" && !isLoading && graph !== null && !graph.initialized;
  const countLabel = isLoading
    ? t("workflow.entitySelector.loadingCount")
    : notInitialized
    ? t("workflow.entitySelector.notInitialized")
    : t("workflow.entitySelector.stateCount", { count });

  return (
    <li>
      <button
        type="button"
        className={`${styles.entityItem} ${active ? styles.entityItemActive : ""}`}
        aria-current={active ? "true" : undefined}
        onClick={() => onSelect(type)}
        data-testid={`workflow-entity-${type}`}
      >
        <span className={styles.entityItemName}>{label}</span>
        <span className={styles.entityItemCount}>{countLabel}</span>
      </button>
    </li>
  );
}

export function EntityTypeSelector({
  selected,
  onSelect,
  scope,
}: EntityTypeSelectorProps): JSX.Element {
  const { t } = useTranslation();
  const { activeWorkspace } = useWorkspace();
  const preset =
    scope?.kind === "global"
      ? scope.preset
      : activeWorkspace?.preset ?? "standard";

  return (
    <nav
      className={styles.entityPanel}
      aria-label={t("workflow.entitySelector.ariaLabel")}
      data-testid="workflow-entity-selector"
    >
      <div className={styles.entityPanelLabel}>{t("workflow.entitySelector.title")}</div>
      <ul className={styles.entityList}>
        {WORKFLOW_ENTITY_TYPES.map((e) => (
          <EntityTypeItem
            key={e.type}
            type={e.type}
            label={t(`workflow.entityTypes.${e.type}`)}
            active={e.type === selected}
            onSelect={onSelect}
            scope={scope}
          />
        ))}
      </ul>
      <div className={styles.entityPanelFooter}>
        <Layers size={14} className={styles.entityPanelFooterLabel} aria-hidden="true" />
        <span className={styles.entityPanelFooterLabel}>{t("workflow.entitySelector.preset")}</span>
        <span className={styles.presetBadge}>{preset}</span>
      </div>
    </nav>
  );
}
