/**
 * ARCH-L1-001 ReactFrontend — MilestoneList (Plan B B6-T2, #879).
 *
 * The UI half of Plan B B6: planned review milestones under the Baselines
 * route. The component is deliberately prop-driven (`workspaceId`, `canEdit`)
 * instead of reaching into WorkspaceContext/AuthContext itself, so the
 * Baselines container stays the single owner of both values.
 *
 * States are explicit: loading (`role="status"`), error (`role="alert"` with a
 * retry), empty, and the filled list. Every mutation surfaces its failure
 * inline instead of disappearing into a console.
 *
 * Optimistic locking: the edit form forwards the row's rendered `version` as
 * the `If-Match` precondition (see `api/milestones.ts`), and the two domain
 * actions pass the same value as `expected_version` — never a locally
 * incremented counter.
 *
 * Accessibility baseline: semantic section/heading, real `<form>`/`<label>`
 * pairs, native `<select>`/`<input type="date">`, and buttons that keep the
 * shared `btn-*` chrome. No WCAG conformance claim — that verdict belongs to
 * `accessibility-specialist`.
 */

import { useEffect, useMemo, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";

import { baselinesApi, type Baseline } from "../../api/baselines";
import { extractApiErrorMessage } from "../../api/client";
import {
  MILESTONE_REVIEW_TYPES,
  MILESTONE_STATUSES,
  type Milestone,
  type MilestoneCreatePayload,
  type MilestoneReviewType,
  type MilestoneStatus,
  type MilestoneUpdatePayload,
} from "../../api/milestones";
import {
  useBindMilestoneBaseline,
  useCreateMilestone,
  useMilestonesList,
  useRecordMilestoneAudit,
  useUpdateMilestone,
} from "../../queries/milestones";
import type { UUID } from "../../types";
import { baselineKeys } from "./useBaselinesData";
import styles from "./MilestoneList.module.css";

export interface MilestoneListProps {
  /** Owning workspace; the Baselines container supplies the active one. */
  workspaceId: UUID;
  /**
   * Whether the caller may write. Defaults to `false` (least privilege) — the
   * backend remains the authority; this only keeps a Viewer from filling in a
   * form that would fail with a 403.
   */
  canEdit?: boolean;
}

function formatTimestamp(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

interface CreateFormProps {
  busy: boolean;
  error: string | null;
  onCancel: () => void;
  onSubmit: (payload: Omit<MilestoneCreatePayload, "workspace_id">) => void;
}

function MilestoneCreateForm({
  busy,
  error,
  onCancel,
  onSubmit,
}: CreateFormProps): JSX.Element {
  const { t } = useTranslation();
  const [name, setName] = useState("");
  const [reviewType, setReviewType] = useState<MilestoneReviewType>("PDR");
  const [targetDate, setTargetDate] = useState("");
  const [status, setStatus] = useState<MilestoneStatus>("planned");
  const [validationError, setValidationError] = useState<string | null>(null);

  const handleSubmit = (event: FormEvent<HTMLFormElement>): void => {
    event.preventDefault();
    if (!name.trim()) {
      setValidationError(t("milestone.nameRequired"));
      return;
    }
    if (!targetDate) {
      setValidationError(t("milestone.targetDateRequired"));
      return;
    }
    setValidationError(null);
    onSubmit({
      name: name.trim(),
      review_type: reviewType,
      target_date: targetDate,
      status,
    });
  };

  const shownError = validationError ?? error;

  return (
    <form
      data-testid="milestone-create-form"
      className={styles.form}
      onSubmit={handleSubmit}
      noValidate
    >
      <div className={styles.formGrid}>
        <label htmlFor="milestone-name" className={styles.fieldLabel}>
          {t("milestone.name")}
        </label>
        <input
          id="milestone-name"
          data-testid="milestone-name-input"
          className={styles.input}
          type="text"
          maxLength={200}
          value={name}
          placeholder={t("milestone.namePlaceholder")}
          onChange={(event) => {
            setName(event.target.value);
            setValidationError(null);
          }}
        />

        <label htmlFor="milestone-review-type" className={styles.fieldLabel}>
          {t("milestone.reviewType")}
        </label>
        <select
          id="milestone-review-type"
          data-testid="milestone-review-type-select"
          className={styles.select}
          value={reviewType}
          onChange={(event) =>
            setReviewType(event.target.value as MilestoneReviewType)
          }
        >
          {MILESTONE_REVIEW_TYPES.map((value) => (
            <option key={value} value={value}>
              {t(`milestone.reviewTypes.${value}`)}
            </option>
          ))}
        </select>

        <label htmlFor="milestone-target-date" className={styles.fieldLabel}>
          {t("milestone.targetDate")}
        </label>
        <input
          id="milestone-target-date"
          data-testid="milestone-target-date-input"
          className={styles.input}
          type="date"
          value={targetDate}
          onChange={(event) => {
            setTargetDate(event.target.value);
            setValidationError(null);
          }}
        />

        <label htmlFor="milestone-status" className={styles.fieldLabel}>
          {t("milestone.status")}
        </label>
        <select
          id="milestone-status"
          data-testid="milestone-status-select"
          className={styles.select}
          value={status}
          onChange={(event) =>
            setStatus(event.target.value as MilestoneStatus)
          }
        >
          {MILESTONE_STATUSES.map((value) => (
            <option key={value} value={value}>
              {t(`milestone.statuses.${value}`)}
            </option>
          ))}
        </select>
      </div>

      {shownError && (
        <p role="alert" data-testid="milestone-create-error" className={styles.error}>
          {shownError}
        </p>
      )}

      <div className={styles.formActions}>
        <button
          type="submit"
          data-testid="milestone-create-submit"
          className="btn-primary"
          disabled={busy}
        >
          {busy ? t("milestone.saving") : t("milestone.createSubmit")}
        </button>
        <button
          type="button"
          data-testid="milestone-create-cancel"
          className="btn-secondary"
          onClick={onCancel}
          disabled={busy}
        >
          {t("milestone.cancel")}
        </button>
      </div>
    </form>
  );
}

interface EditFormProps {
  milestone: Milestone;
  busy: boolean;
  error: string | null;
  onCancel: () => void;
  onSubmit: (payload: MilestoneUpdatePayload) => void;
}

function MilestoneEditForm({
  milestone,
  busy,
  error,
  onCancel,
  onSubmit,
}: EditFormProps): JSX.Element {
  const { t } = useTranslation();
  const [name, setName] = useState(milestone.name);
  const [reviewType, setReviewType] = useState<MilestoneReviewType>(
    milestone.review_type
  );
  const [targetDate, setTargetDate] = useState(milestone.target_date);
  const [status, setStatus] = useState<MilestoneStatus>(milestone.status);
  const [validationError, setValidationError] = useState<string | null>(null);

  const handleSubmit = (event: FormEvent<HTMLFormElement>): void => {
    event.preventDefault();
    if (!name.trim()) {
      setValidationError(t("milestone.nameRequired"));
      return;
    }
    if (!targetDate) {
      setValidationError(t("milestone.targetDateRequired"));
      return;
    }
    setValidationError(null);
    onSubmit({
      name: name.trim(),
      review_type: reviewType,
      target_date: targetDate,
      status,
    });
  };

  const shownError = validationError ?? error;

  return (
    <form
      data-testid="milestone-edit-form"
      className={styles.form}
      onSubmit={handleSubmit}
      noValidate
    >
      <div className={styles.formGrid}>
        <label htmlFor="milestone-edit-name" className={styles.fieldLabel}>
          {t("milestone.name")}
        </label>
        <input
          id="milestone-edit-name"
          data-testid="milestone-edit-name"
          className={styles.input}
          type="text"
          maxLength={200}
          value={name}
          onChange={(event) => {
            setName(event.target.value);
            setValidationError(null);
          }}
        />

        <label
          htmlFor="milestone-edit-review-type"
          className={styles.fieldLabel}
        >
          {t("milestone.reviewType")}
        </label>
        <select
          id="milestone-edit-review-type"
          data-testid="milestone-edit-review-type"
          className={styles.select}
          value={reviewType}
          onChange={(event) =>
            setReviewType(event.target.value as MilestoneReviewType)
          }
        >
          {MILESTONE_REVIEW_TYPES.map((value) => (
            <option key={value} value={value}>
              {t(`milestone.reviewTypes.${value}`)}
            </option>
          ))}
        </select>

        <label htmlFor="milestone-edit-target-date" className={styles.fieldLabel}>
          {t("milestone.targetDate")}
        </label>
        <input
          id="milestone-edit-target-date"
          data-testid="milestone-edit-target-date"
          className={styles.input}
          type="date"
          value={targetDate}
          onChange={(event) => {
            setTargetDate(event.target.value);
            setValidationError(null);
          }}
        />

        <label htmlFor="milestone-edit-status" className={styles.fieldLabel}>
          {t("milestone.status")}
        </label>
        <select
          id="milestone-edit-status"
          data-testid="milestone-edit-status"
          className={styles.select}
          value={status}
          onChange={(event) =>
            setStatus(event.target.value as MilestoneStatus)
          }
        >
          {MILESTONE_STATUSES.map((value) => (
            <option key={value} value={value}>
              {t(`milestone.statuses.${value}`)}
            </option>
          ))}
        </select>
      </div>

      {shownError && (
        <p role="alert" data-testid="milestone-edit-error" className={styles.error}>
          {shownError}
        </p>
      )}

      <div className={styles.formActions}>
        <button
          type="submit"
          data-testid="milestone-update-submit"
          className="btn-primary"
          disabled={busy}
        >
          {busy ? t("milestone.saving") : t("milestone.save")}
        </button>
        <button
          type="button"
          data-testid="milestone-edit-cancel"
          className="btn-secondary"
          onClick={onCancel}
          disabled={busy}
        >
          {t("milestone.cancel")}
        </button>
      </div>
    </form>
  );
}

interface ActionPanelProps {
  milestone: Milestone;
  baselines: Baseline[];
  baselinesLoading: boolean;
  busy: boolean;
  error: string | null;
  canEdit: boolean;
  onEdit: () => void;
  onBind: (baselineId: UUID) => void;
  onAudit: () => void;
}

function MilestoneActionPanel({
  milestone,
  baselines,
  baselinesLoading,
  busy,
  error,
  canEdit,
  onEdit,
  onBind,
  onAudit,
}: ActionPanelProps): JSX.Element {
  const { t } = useTranslation();
  const [baselineId, setBaselineId] = useState("");

  const snapshot = milestone.audit_snapshot;

  return (
    <div data-testid="milestone-detail" className={styles.detail}>
      <div className={styles.detailHeader}>
        <h3 className={styles.detailTitle}>{milestone.name}</h3>
        {canEdit && (
          <button
            type="button"
            data-testid="milestone-edit-button"
            className="btn-secondary"
            onClick={onEdit}
            disabled={busy}
          >
            {t("milestone.edit")}
          </button>
        )}
      </div>

      <dl className={styles.detailGrid}>
        <dt className={styles.detailTerm}>{t("milestone.reviewType")}</dt>
        <dd className={styles.detailValue}>
          {t(`milestone.reviewTypes.${milestone.review_type}`)}
        </dd>

        <dt className={styles.detailTerm}>{t("milestone.targetDate")}</dt>
        <dd className={styles.detailValue}>{milestone.target_date}</dd>

        <dt className={styles.detailTerm}>{t("milestone.status")}</dt>
        <dd className={styles.detailValue}>
          {t(`milestone.statuses.${milestone.status}`)}
        </dd>

        <dt className={styles.detailTerm}>{t("milestone.baseline")}</dt>
        <dd className={styles.detailValue}>
          {milestone.baseline_id ? (
            <code className={styles.mono}>{milestone.baseline_id}</code>
          ) : (
            t("milestone.noBaseline")
          )}
        </dd>
      </dl>

      <p data-testid="milestone-audit-snapshot" className={styles.auditLine}>
        {snapshot
          ? `${t("milestone.auditCounts", {
              total: snapshot.counts.total,
              blockers: snapshot.counts.blockers,
              warnings: snapshot.counts.warnings,
            })} · ${formatTimestamp(snapshot.run_at)}`
          : t("milestone.noAuditSnapshot")}
      </p>

      {error && (
        <p role="alert" data-testid="milestone-action-error" className={styles.error}>
          {error}
        </p>
      )}

      {canEdit && (
        <div className={styles.actionPanel}>
          <label
            htmlFor="milestone-baseline-select"
            className={styles.fieldLabel}
          >
            {t("milestone.bindBaseline")}
          </label>
          <div className={styles.actionRow}>
            <select
              id="milestone-baseline-select"
              data-testid="milestone-baseline-select"
              className={styles.select}
              value={baselineId}
              onChange={(event) => setBaselineId(event.target.value)}
              disabled={baselinesLoading || busy || baselines.length === 0}
            >
              <option value="">
                {baselines.length === 0
                  ? t("milestone.noBaselines")
                  : t("milestone.selectBaseline")}
              </option>
              {baselines.map((baseline) => (
                <option key={baseline.id} value={baseline.id}>
                  {baseline.name || baseline.id}
                </option>
              ))}
            </select>
            <button
              type="button"
              data-testid="milestone-bind-baseline"
              className="btn-primary"
              onClick={() => onBind(baselineId)}
              disabled={!baselineId || busy}
            >
              {t("milestone.bindBaseline")}
            </button>
            <button
              type="button"
              data-testid="milestone-record-audit"
              className="btn-secondary"
              onClick={onAudit}
              disabled={busy}
            >
              {t("milestone.recordAudit")}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export function MilestoneList({
  workspaceId,
  canEdit = false,
}: MilestoneListProps): JSX.Element {
  const { t } = useTranslation();
  const milestonesQuery = useMilestonesList(workspaceId);
  const milestones = useMemo(
    () => milestonesQuery.data ?? [],
    [milestonesQuery.data]
  );

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [createError, setCreateError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const createMutation = useCreateMilestone();
  const updateMutation = useUpdateMilestone();
  const bindMutation = useBindMilestoneBaseline();
  const auditMutation = useRecordMilestoneAudit();
  const busy =
    createMutation.isPending ||
    updateMutation.isPending ||
    bindMutation.isPending ||
    auditMutation.isPending;

  // A workspace switch must not keep a row id (or a half-filled form) from the
  // previous workspace.
  useEffect(() => {
    setSelectedId(null);
    setShowCreate(false);
    setEditingId(null);
    setCreateError(null);
    setActionError(null);
  }, [workspaceId]);

  const selected = useMemo(
    () => milestones.find((milestone) => milestone.id === selectedId) ?? null,
    [milestones, selectedId]
  );

  // The bind picker is only needed once a row is selected, and it shares the
  // Baselines view's list cache so opening it costs no second request.
  const baselinesQuery = useQuery({
    queryKey: baselineKeys.list(workspaceId, ""),
    queryFn: async (): Promise<Baseline[]> => {
      const response = await baselinesApi.list({ workspace_id: workspaceId });
      return response.results;
    },
    enabled: Boolean(selectedId && workspaceId),
  });
  const baselines = baselinesQuery.data ?? [];

  const handleCreate = async (
    payload: Omit<MilestoneCreatePayload, "workspace_id">
  ): Promise<void> => {
    setCreateError(null);
    try {
      const created = await createMutation.mutateAsync({
        workspace_id: workspaceId,
        ...payload,
      });
      setShowCreate(false);
      setSelectedId(created.id);
    } catch (err: unknown) {
      setCreateError(
        extractApiErrorMessage(err) ?? t("milestone.createFailed")
      );
    }
  };

  const handleUpdate = async (
    milestone: Milestone,
    payload: MilestoneUpdatePayload
  ): Promise<void> => {
    setActionError(null);
    try {
      await updateMutation.mutateAsync({
        id: milestone.id,
        payload,
        expectedVersion: milestone.version,
      });
      setEditingId(null);
    } catch (err: unknown) {
      setActionError(
        extractApiErrorMessage(err) ?? t("milestone.updateFailed")
      );
    }
  };

  const handleBind = async (baselineId: UUID): Promise<void> => {
    if (!selected) return;
    setActionError(null);
    try {
      await bindMutation.mutateAsync({
        id: selected.id,
        baselineId,
        expectedVersion: selected.version,
      });
    } catch (err: unknown) {
      setActionError(
        extractApiErrorMessage(err) ?? t("milestone.bindFailed")
      );
    }
  };

  const handleAudit = async (): Promise<void> => {
    if (!selected) return;
    setActionError(null);
    try {
      await auditMutation.mutateAsync({
        id: selected.id,
        expectedVersion: selected.version,
      });
    } catch (err: unknown) {
      setActionError(
        extractApiErrorMessage(err) ?? t("milestone.auditFailed")
      );
    }
  };

  const selectRow = (id: string): void => {
    setShowCreate(false);
    setEditingId(null);
    setActionError(null);
    setSelectedId(id);
  };

  return (
    <section
      data-testid="milestone-list"
      className={styles.section}
      aria-labelledby="milestone-heading"
    >
      <div className={styles.header}>
        <div>
          <h2 id="milestone-heading" className={styles.heading}>
            {t("milestone.title")}
          </h2>
          <p className={styles.summary}>
            {t("milestone.summary", { count: milestones.length })}
          </p>
        </div>
        {canEdit && (
          <button
            type="button"
            data-testid="milestone-create-button"
            className="btn-primary"
            onClick={() => {
              setSelectedId(null);
              setEditingId(null);
              setCreateError(null);
              setActionError(null);
              setShowCreate(true);
            }}
            disabled={!workspaceId || busy}
          >
            {t("milestone.create")}
          </button>
        )}
      </div>

      {showCreate && canEdit && (
        <MilestoneCreateForm
          busy={busy}
          error={createError}
          onCancel={() => {
            setShowCreate(false);
            setCreateError(null);
          }}
          onSubmit={(payload) => void handleCreate(payload)}
        />
      )}

      {milestonesQuery.isLoading && (
        <p role="status" data-testid="milestone-loading" className={styles.loading}>
          {t("loading")}
        </p>
      )}

      {milestonesQuery.isError && (
        <div role="alert" data-testid="milestone-error" className={styles.errorPanel}>
          <p className={styles.error}>
            {extractApiErrorMessage(milestonesQuery.error) ??
              t("milestone.loadFailed")}
          </p>
          <button
            type="button"
            data-testid="milestone-retry"
            className="btn-secondary"
            onClick={() => void milestonesQuery.refetch()}
          >
            {t("actions.reload")}
          </button>
        </div>
      )}

      {!milestonesQuery.isLoading &&
        !milestonesQuery.isError &&
        milestones.length === 0 && (
          <p data-testid="milestone-empty" className={styles.empty}>
            {t("milestone.emptyDescription")}
          </p>
        )}

      {!milestonesQuery.isLoading &&
        !milestonesQuery.isError &&
        milestones.length > 0 && (
          <ul className={styles.list}>
            {milestones.map((milestone) => {
              const isSelected = milestone.id === selectedId;
              return (
                <li
                  key={milestone.id}
                  data-testid={`milestone-row-${milestone.id}`}
                  className={`${styles.row} ${isSelected ? styles.rowSelected : ""}`}
                >
                  <button
                    type="button"
                    data-testid={`milestone-row-select-${milestone.id}`}
                    className={`btn-ghost ${styles.rowSelect}`}
                    aria-pressed={isSelected}
                    onClick={() => selectRow(milestone.id)}
                  >
                    <span className={styles.rowName}>{milestone.name}</span>
                    <span className={styles.rowMeta}>
                      {t(`milestone.reviewTypes.${milestone.review_type}`)} ·{" "}
                      {milestone.target_date} ·{" "}
                      {t(`milestone.statuses.${milestone.status}`)}
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        )}

      {selected && editingId === selected.id && canEdit ? (
        <MilestoneEditForm
          key={`${selected.id}-${selected.version}`}
          milestone={selected}
          busy={busy}
          error={actionError}
          onCancel={() => {
            setEditingId(null);
            setActionError(null);
          }}
          onSubmit={(payload) => void handleUpdate(selected, payload)}
        />
      ) : selected ? (
        <MilestoneActionPanel
          key={selected.id}
          milestone={selected}
          baselines={baselines}
          baselinesLoading={baselinesQuery.isLoading}
          busy={busy}
          error={actionError}
          canEdit={canEdit}
          onEdit={() => {
            setActionError(null);
            setEditingId(selected.id);
          }}
          onBind={(baselineId) => void handleBind(baselineId)}
          onAudit={() => void handleAudit()}
        />
      ) : (
        milestones.length > 0 && (
          <p className={styles.selectPrompt}>{t("milestone.selectMilestone")}</p>
        )
      )}
    </section>
  );
}

export default MilestoneList;
