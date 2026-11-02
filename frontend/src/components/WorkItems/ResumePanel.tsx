/**
 * ARCH-L1-001 ReactFrontend — resume panel (Plan F F3-T9).
 *
 * Renders `work_item.resume` exactly as an agent reads it: the newest
 * checkpoint first ("hier weiter"), then every open item sorted by the server
 * `(ordinal, id)`. Read-only — selecting an item only navigates the panel, it
 * never writes a heartbeat.
 */

import { useTranslation } from "react-i18next";

import { Badge } from "../shared/Badge";
import { StatusBadge } from "../shared/StatusBadge";
import type { WorkItemResume, WorkItemResumeEntry } from "../../types";
import {
  workItemKindLabel,
  workItemKindVariant,
  workItemStatusLabel,
} from "./workItemLabels";
import styles from "./WorkItems.module.css";

export interface ResumePanelProps {
  resume: WorkItemResume | undefined;
  isLoading: boolean;
  error: Error | null;
  onRetry: () => void;
  onSelect: (id: string) => void;
  testId?: string;
}

function ResumeRow({
  entry,
  onSelect,
  testIdPrefix,
}: {
  entry: WorkItemResumeEntry;
  onSelect: (id: string) => void;
  testIdPrefix: string;
}): JSX.Element {
  const { t } = useTranslation();
  return (
    <li>
      <button
        type="button"
        className={`${styles.resumeItem} btn-ghost`}
        data-testid={`${testIdPrefix}-item-${entry.id}`}
        onClick={() => onSelect(entry.id)}
      >
        <Badge variant={workItemKindVariant(entry.kind)}>
          {workItemKindLabel(t, entry.kind)}
        </Badge>
        <StatusBadge
          status={entry.status}
          label={workItemStatusLabel(t, entry.status)}
          testId={`${testIdPrefix}-status-${entry.id}`}
        />
        <span>{entry.uid ?? entry.id.slice(0, 8)}</span>
        {entry.next_action && <span>{entry.next_action}</span>}
        {entry.blocked_reason && (
          <span className={styles.error}>{entry.blocked_reason}</span>
        )}
      </button>
    </li>
  );
}

export function ResumePanel({
  resume,
  isLoading,
  error,
  onRetry,
  onSelect,
  testId = "work-item-resume",
}: ResumePanelProps): JSX.Element {
  const { t } = useTranslation();

  if (isLoading) {
    return (
      <div className={styles.resume} data-testid={testId}>
        <p role="status" className={styles.hint} data-testid={`${testId}-loading`}>
          {t("work_items.resume.loading")}
        </p>
      </div>
    );
  }

  if (error) {
    return (
      <div className={styles.resume} data-testid={testId}>
        <p role="alert" className={styles.error} data-testid={`${testId}-error`}>
          {t("work_items.resume.loadFailed")}
        </p>
        <button
          type="button"
          className="btn-secondary"
          data-testid={`${testId}-retry`}
          onClick={onRetry}
        >
          {t("work_items.retry")}
        </button>
      </div>
    );
  }

  const checkpoint = resume?.checkpoint ?? null;
  const openItems = resume?.open_items ?? [];

  return (
    <section className={styles.resume} data-testid={testId}>
      <div className={styles.resumeHeader}>
        <h4 className={styles.sectionTitle}>{t("work_items.resume.title")}</h4>
        <span className={styles.hint} data-testid={`${testId}-count`}>
          {t("work_items.resume.openCount", { count: openItems.length })}
        </span>
      </div>

      <div>
        <p className={styles.hint}>{t("work_items.resume.checkpoint")}</p>
        {checkpoint ? (
          <ul className={styles.resumeList}>
            <ResumeRow
              entry={checkpoint}
              onSelect={onSelect}
              testIdPrefix={`${testId}-checkpoint`}
            />
          </ul>
        ) : (
          <p className={styles.hint} data-testid={`${testId}-checkpoint-none`}>
            {t("work_items.resume.checkpointNone")}
          </p>
        )}
      </div>

      <div>
        <p className={styles.hint}>{t("work_items.resume.openItems")}</p>
        {openItems.length === 0 ? (
          <p className={styles.hint} data-testid={`${testId}-empty`}>
            {t("work_items.resume.empty")}
          </p>
        ) : (
          <ul className={styles.resumeList}>
            {openItems.map((entry) => (
              <ResumeRow
                key={entry.id}
                entry={entry}
                onSelect={onSelect}
                testIdPrefix={testId}
              />
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
