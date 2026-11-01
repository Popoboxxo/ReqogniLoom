/**
 * F4.5 — Baseline rollback panel (REQ-L1-018, ADR-025, Plan F).
 *
 * leaf_id: COMP-RF-002 (BaselinesView)
 *
 * Drives the three backend routes the additive rollback exposes (F4.4):
 *
 *   1. `GET  /baselines/{id}/rollback-preview/` — the read-only plan
 *      (`restore` / `reactivate` / `unchanged` / `unsupported` /
 *      `created_since`, per-item field diffs and the fields the snapshot
 *      cannot supply).
 *   2. `POST /baselines/{id}/rollback-request/` — opens the CCB change
 *      request the rollback must pass through (ADR-025 R2).
 *   3. `POST /baselines/{id}/rollback/` — executes the approved plan.
 *
 * Nothing is implicit: the panel never applies a rollback the CCB has not
 * approved, and it never invents an approval — it only re-reads the status of
 * the change request it opened (there is no ChangeRequest view in this SPA,
 * see `changeRequestsApi.get`). The confirmation names the number of
 * artifacts that will be written as new versions; the server's own R5
 * protection stays the authority.
 *
 * One CR at a time (F4.5 review F-04): once the panel has opened a change
 * request, the request form is replaced by an "already opened" notice, so a
 * second submit cannot silently orphan an approved CR that this SPA has no
 * view for. The form only returns after the server reports
 * `ROLLBACK_PLAN_STALE` — the one case in which the opened CR is no longer
 * the applicable request.
 *
 * Accessibility baseline: a real `<table>` with column headers for the plan,
 * labelled controls (including a real `<button>` for the CR id copy, with its
 * result announced through `role="status"`), `role="alert"` on the error
 * region, `role="status"` on the result region, and a shared
 * `<ConfirmDialog>` (focus trap, Escape, focus return) for the destructive
 * step. No WCAG conformance claim — the binding verdict is
 * `accessibility-specialist`'s.
 */

import { useCallback, useEffect, useId, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ClipboardCopy } from 'lucide-react';
import { ConfirmDialog } from '../shared/ConfirmDialog';
import { StatusBadge } from '../shared/StatusBadge';
import {
  ROLLBACK_CODES,
  baselinesApi,
  type RollbackItemAction,
  type RollbackPlanItem,
  type RollbackPreview,
  type RollbackResult,
} from '../../api/baselines';
import { changeRequestsApi } from '../../api/change-requests';
import { extractApiErrorMessage } from '../../api/client';
import type { UUID } from '../../types';
import styles from './BaselineRollbackPanel.module.css';

export interface BaselineRollbackPanelProps {
  /** Baseline whose captured state a rollback would restore. */
  baselineId: UUID;
  /**
   * Write authority (admin/editor). A viewer keeps the read-only preview —
   * the backend opens `rollback-preview` to every workspace member — but never
   * sees the request/apply controls.
   */
  canEdit: boolean;
}

/** The change request this panel opened, and its last known workflow state. */
interface OpenedChangeRequest {
  id: string;
  status: string;
}

interface RollbackErrorShape {
  error?: { code?: string; message?: string; details?: unknown };
}

function rollbackErrorCode(err: unknown): string | null {
  const code = (err as RollbackErrorShape | null)?.error?.code;
  return typeof code === 'string' && code !== '' ? code : null;
}

/** `details` of a rollback refusal — an object for `ROLLBACK_TOO_LARGE`. */
function rollbackErrorDetails(err: unknown): Record<string, unknown> | null {
  const details = (err as RollbackErrorShape | null)?.error?.details;
  return details !== null && typeof details === 'object' && !Array.isArray(details)
    ? (details as Record<string, unknown>)
    : null;
}

/** Render an arbitrary JSON field value for the diff cell. */
function formatValue(value: unknown): string {
  if (value === null || value === undefined) return '—';
  if (typeof value === 'string') return value;
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

/**
 * Which copy the status row shows for a given CCB state (F4.5 review F-02).
 *
 * Only the states that still need a CCB decision may speak about a required
 * approval; an `approved`/`implemented`/`rejected` request would otherwise
 * render "must be approved (approved)" — true-looking, and wrong.
 */
function statusHintKey(status: string): string {
  switch (status) {
    case 'draft':
    case 'submitted':
    case 'under_review':
      return 'baselines.rollback.awaitApproval';
    case 'approved':
      return 'baselines.rollback.approvedHint';
    case 'implemented':
      return 'baselines.rollback.implementedHint';
    case 'rejected':
      return 'baselines.rollback.rejectedHint';
    default:
      // Unknown/workspace-defined state: keep the neutral "needs approval"
      // wording rather than inventing a label for it.
      return 'baselines.rollback.awaitApproval';
  }
}

/** The copy affordance's transient announcement (F4.5 review F-06). */
type CopyState = 'idle' | 'copied' | 'failed';

const ACTION_LABEL_KEYS: Record<RollbackItemAction, string> = {
  restore: 'baselines.rollback.actionRestore',
  reactivate: 'baselines.rollback.actionReactivate',
  unchanged: 'baselines.rollback.actionUnchanged',
  unsupported: 'baselines.rollback.actionUnsupported',
  created_since: 'baselines.rollback.actionCreatedSince',
};

/** The five actions in the order the summary lists them. */
const ACTION_ORDER: readonly RollbackItemAction[] = [
  'restore',
  'reactivate',
  'unchanged',
  'unsupported',
  'created_since',
];

export function BaselineRollbackPanel({
  baselineId,
  canEdit,
}: BaselineRollbackPanelProps): JSX.Element {
  const { t } = useTranslation();
  const headingId = useId();
  const reasonId = useId();

  const [preview, setPreview] = useState<RollbackPreview | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [reason, setReason] = useState('');
  const [requesting, setRequesting] = useState(false);
  const [changeRequest, setChangeRequest] = useState<OpenedChangeRequest | null>(null);
  // F-04: a new request is only reachable after the opened CR stopped being
  // applicable (the server said the plan went stale).
  const [allowNewRequest, setAllowNewRequest] = useState(false);
  const [statusRefreshing, setStatusRefreshing] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [applying, setApplying] = useState(false);
  const [copyState, setCopyState] = useState<CopyState>('idle');
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<RollbackResult | null>(null);
  // Synchronous in-flight guards: a second click can land before the matching
  // state update has been committed. The apply route must never run twice and
  // neither the plan computation nor the CR creation may be fired twice
  // (F-05 — same hardening for all three write-ish controls).
  const previewInFlight = useRef(false);
  const requestInFlight = useRef(false);
  const applyInFlight = useRef(false);
  const copyResetTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(
    () => () => {
      if (copyResetTimer.current !== null) clearTimeout(copyResetTimer.current);
    },
    []
  );

  /**
   * Localised copy for a rollback refusal, keyed on the stable
   * `error.code` (SEC-RB-05) rather than the HTTP status. Unknown codes fall
   * back to the server's own message so a 403/404 never renders as nothing.
   */
  const describeError = useCallback(
    (err: unknown): string => {
      const code = rollbackErrorCode(err);
      const details = rollbackErrorDetails(err);
      switch (code) {
        case ROLLBACK_CODES.planStale:
          return t('baselines.rollback.stale');
        case ROLLBACK_CODES.alreadyApplied:
          return t('baselines.rollback.alreadyApplied');
        case ROLLBACK_CODES.notApproved:
          return t('baselines.rollback.notApproved');
        case ROLLBACK_CODES.tooLarge:
          return t('baselines.rollback.tooLarge', {
            count: details?.count ?? '—',
            max: details?.max ?? '—',
          });
        default:
          return extractApiErrorMessage(err) ?? String(err);
      }
    },
    [t]
  );

  const loadPreview = useCallback(async (): Promise<void> => {
    if (previewInFlight.current) return;
    previewInFlight.current = true;
    setPreviewLoading(true);
    setError(null);
    setResult(null);
    try {
      setPreview(await baselinesApi.rollbackPreview(baselineId));
    } catch (err: unknown) {
      setPreview(null);
      setError(describeError(err));
    } finally {
      previewInFlight.current = false;
      setPreviewLoading(false);
    }
  }, [baselineId, describeError]);

  /**
   * Re-read the change request's workflow state. The CCB decides elsewhere
   * (there is no ChangeRequest view in this SPA), so this is the only way the
   * panel learns that the CR became `approved`.
   */
  const refreshStatus = useCallback(
    async (id: string): Promise<void> => {
      setStatusRefreshing(true);
      try {
        const cr = await changeRequestsApi.get(id);
        setChangeRequest({ id: cr.id, status: cr.status });
      } catch (err: unknown) {
        setError(describeError(err));
      } finally {
        setStatusRefreshing(false);
      }
    },
    [describeError]
  );

  const createRequest = useCallback(async (): Promise<void> => {
    const trimmed = reason.trim();
    if (!preview || trimmed === '' || requestInFlight.current) return;
    requestInFlight.current = true;
    setRequesting(true);
    setError(null);
    try {
      const created = await baselinesApi.rollbackRequest(baselineId, {
        change_reason: trimmed,
      });
      setChangeRequest({ id: created.change_request_id, status: created.status });
      // A fresh request is the only open one again — the form folds away.
      setAllowNewRequest(false);
      // The CR starts in `draft`; a status read makes the hint authoritative
      // even when the backend already answered something else.
      void refreshStatus(created.change_request_id);
    } catch (err: unknown) {
      setError(describeError(err));
    } finally {
      requestInFlight.current = false;
      setRequesting(false);
    }
  }, [baselineId, describeError, preview, reason, refreshStatus]);

  /**
   * F-06: put the CR id on the clipboard. This SPA has no ChangeRequest view,
   * so the id is the only handle an operator can carry to the CCB tooling —
   * it needs a real control, not a `<code>` that merely looks selectable.
   */
  const copyChangeRequestId = useCallback(async (): Promise<void> => {
    const id = changeRequest?.id;
    if (!id) return;
    try {
      await navigator.clipboard.writeText(id);
      setCopyState('copied');
    } catch {
      setCopyState('failed');
    }
    if (copyResetTimer.current !== null) clearTimeout(copyResetTimer.current);
    copyResetTimer.current = setTimeout(() => setCopyState('idle'), 2000);
  }, [changeRequest]);

  const requestApply = useCallback((): void => {
    if (!changeRequest || changeRequest.status !== 'approved' || applying) return;
    setConfirming(true);
  }, [applying, changeRequest]);

  const confirmApply = useCallback(async (): Promise<void> => {
    if (!changeRequest || applyInFlight.current) return;
    applyInFlight.current = true;
    setApplying(true);
    setError(null);
    try {
      const applied = await baselinesApi.rollbackApply(baselineId, {
        change_request_id: changeRequest.id,
      });
      setResult(applied);
      setChangeRequest({ id: changeRequest.id, status: applied.change_request_status });
    } catch (err: unknown) {
      setError(describeError(err));
      // 409 ROLLBACK_ALREADY_APPLIED: the CR moved on without this panel — show
      // the state it actually reached instead of a stale `approved`.
      if (rollbackErrorCode(err) === ROLLBACK_CODES.alreadyApplied) {
        void refreshStatus(changeRequest.id);
      }
      // 409 ROLLBACK_PLAN_STALE: the opened CR no longer describes the plan, so
      // this is the one documented moment a NEW request becomes reachable
      // (F-04). Any other failure keeps the form folded away.
      if (rollbackErrorCode(err) === ROLLBACK_CODES.planStale) {
        setAllowNewRequest(true);
      }
    } finally {
      applyInFlight.current = false;
      setApplying(false);
      setConfirming(false);
    }
  }, [baselineId, changeRequest, describeError, refreshStatus]);

  const restoreCount = preview
    ? preview.summary.restore + preview.summary.reactivate
    : 0;

  const renderItemRow = (item: RollbackPlanItem): JSX.Element => (
    <tr key={item.item_id} data-testid="baseline-rollback-item-row">
      <td className={styles.cellItem}>
        <code title={item.item_id}>{item.item_id.slice(0, 8)}…</code>
      </td>
      <td className={styles.cellType}>{item.artifact_type || '—'}</td>
      <td className={styles.cellAction}>
        {t(ACTION_LABEL_KEYS[item.action] ?? ACTION_LABEL_KEYS.unsupported)}
      </td>
      <td className={styles.cellChanges}>
        {Object.keys(item.field_changes).length > 0 && (
          <ul className={styles.changeList}>
            {Object.entries(item.field_changes).map(([field, change]) => (
              <li key={field}>
                <code>{field}</code>
                {`: ${formatValue(change.current)} → ${formatValue(change.baseline)}`}
              </li>
            ))}
          </ul>
        )}
        {item.unrestorable_fields.length > 0 && (
          <p className={styles.unrestorable}>
            {t('baselines.rollback.unrestorable', {
              fields: item.unrestorable_fields.join(', '),
            })}
          </p>
        )}
      </td>
    </tr>
  );

  return (
    <section
      data-testid="baseline-rollback-panel"
      className={styles.panel}
      aria-labelledby={headingId}
    >
      <h3 id={headingId} className={styles.heading}>
        {t('baselines.rollback.title')}
      </h3>

      <button
        type="button"
        data-testid="baseline-rollback-preview-btn"
        className="btn-secondary"
        disabled={previewLoading}
        aria-busy={previewLoading || undefined}
        onClick={() => void loadPreview()}
      >
        {previewLoading
          ? t('baselines.rollback.previewLoading')
          : t('baselines.rollback.preview')}
      </button>

      {error && (
        <p role="alert" data-testid="baseline-rollback-error" className={styles.error}>
          {error}
        </p>
      )}

      {preview && (
        <>
          {/* Counts first: this is also the empty state — a plan with nothing
              to restore still renders its zeros instead of an empty box. */}
          <dl className={styles.summary}>
            {ACTION_ORDER.map((action) => (
              <div key={action} className={styles.summaryRow}>
                <dt className={styles.summaryTerm}>{t(ACTION_LABEL_KEYS[action])}</dt>
                <dd className={styles.summaryValue}>{preview.summary[action]}</dd>
              </div>
            ))}
          </dl>

          {preview.items.length > 0 && (
            <table
              data-testid="baseline-rollback-preview-table"
              className={styles.table}
              aria-label={t('baselines.rollback.preview')}
            >
              <thead>
                <tr>
                  <th scope="col" className={styles.th}>
                    {t('baselines.rollback.columnItem')}
                  </th>
                  <th scope="col" className={styles.th}>
                    {t('baselines.rollback.columnType')}
                  </th>
                  <th scope="col" className={styles.th}>
                    {t('baselines.rollback.columnAction')}
                  </th>
                  <th scope="col" className={styles.th}>
                    {t('baselines.rollback.columnChanges')}
                  </th>
                </tr>
              </thead>
              <tbody>{preview.items.map(renderItemRow)}</tbody>
            </table>
          )}

          {canEdit && (!changeRequest || allowNewRequest) && (
            <div className={styles.requestForm}>
              <label htmlFor={reasonId} className={styles.reasonLabel}>
                {t('baselines.rollback.reason')}
              </label>
              <input
                id={reasonId}
                type="text"
                data-testid="baseline-rollback-reason-input"
                className={styles.reasonInput}
                value={reason}
                maxLength={2000}
                aria-required="true"
                disabled={requesting}
                onChange={(event) => {
                  setReason(event.target.value);
                  setError(null);
                }}
              />
              <button
                type="button"
                data-testid="baseline-rollback-request-btn"
                className="btn-primary"
                disabled={requesting || reason.trim() === ''}
                aria-busy={requesting || undefined}
                onClick={() => void createRequest()}
              >
                {requesting ? t('actions.saving') : t('baselines.rollback.request')}
              </button>
            </div>
          )}

          {canEdit && changeRequest && !allowNewRequest && (
            /* F-04: one open CR at a time — a second submit would replace it
               and leave the first (possibly already approved) request
               unreachable, since this SPA has no CR view. */
            <p
              data-testid="baseline-rollback-request-locked"
              className={styles.requestLocked}
            >
              {t('baselines.rollback.requestOpen', { status: changeRequest.status })}
            </p>
          )}
        </>
      )}

      {changeRequest && (
        <div className={styles.changeRequest}>
          {/* The CR reference. This SPA has no ChangeRequest view, so the id
              (plus the copy control next to it) is the only handle — no route
              is invented for it. */}
          <div className={styles.crRefRow}>
            <p data-testid="baseline-rollback-cr-link" className={styles.crRef}>
              <code title={changeRequest.id}>{changeRequest.id}</code>
            </p>
            <button
              type="button"
              data-testid="baseline-rollback-cr-copy"
              className="btn-icon"
              aria-label={t('baselines.rollback.copyId')}
              title={t('baselines.rollback.copyId')}
              onClick={() => void copyChangeRequestId()}
            >
              <ClipboardCopy size={14} aria-hidden="true" />
            </button>
          </div>
          {copyState !== 'idle' && (
            <p
              role="status"
              data-testid="baseline-rollback-cr-copy-status"
              className={styles.copyStatus}
            >
              {copyState === 'copied'
                ? t('baselines.rollback.copied')
                : t('baselines.rollback.copyFailed')}
            </p>
          )}
          <p className={styles.statusRow}>
            <StatusBadge
              status={changeRequest.status}
              testId="baseline-rollback-cr-status"
            />
            <span className={styles.statusHint}>
              {t(statusHintKey(changeRequest.status), { status: changeRequest.status })}
            </span>
          </p>
          <div className={styles.applyRow}>
            <button
              type="button"
              data-testid="baseline-rollback-cr-refresh"
              className="btn-secondary"
              disabled={statusRefreshing}
              aria-busy={statusRefreshing || undefined}
              onClick={() => void refreshStatus(changeRequest.id)}
            >
              {t('baselines.rollback.refreshStatus')}
            </button>
            {canEdit && changeRequest.status === 'approved' && (
              <button
                type="button"
                data-testid="baseline-rollback-apply-btn"
                className="btn-danger"
                disabled={applying}
                aria-busy={applying || undefined}
                onClick={requestApply}
              >
                {t('baselines.rollback.apply')}
              </button>
            )}
          </div>
        </div>
      )}

      {result && (
        <p
          role="status"
          data-testid="baseline-rollback-result"
          className={styles.result}
        >
          {t('baselines.rollback.done', {
            restored: result.restored,
            reactivated: result.reactivated,
            links: result.links_recreated,
          })}
        </p>
      )}

      {confirming && (
        <ConfirmDialog
          title={t('baselines.rollback.apply')}
          message={t('baselines.rollback.confirm', { count: restoreCount })}
          confirmLabel={t('baselines.rollback.apply')}
          onConfirm={() => void confirmApply()}
          onCancel={() => {
            if (!applying) setConfirming(false);
          }}
          testId="baseline-rollback-confirm"
          isSubmitting={applying}
        />
      )}
    </section>
  );
}
