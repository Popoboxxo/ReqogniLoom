/**
 * #399 (spec section 6.4 / decision D7) — baseline drift badge + change-request
 * shortcut for the artifact **editor header**.
 *
 * Deliberately NOT rendered inside `shared/ArtifactRow`: a list-row badge
 * would fire one `baselineMembership(id)` request per row — an N+1 with no
 * batch endpoint (spec D7). The editor header shows exactly one artifact, so
 * one membership lookup is the whole cost.
 *
 * The badge knows drift from two additive sources, cheapest first:
 *  1. `summary` — the `{drifted, count}` the retrieve endpoints already attach
 *     (spec section 6.3). Absent on old payloads.
 *  2. `artifactsApi.baselineMembership(artifactId)` — the per-baseline detail,
 *     which also supplies the name for the tooltip.
 *
 * Fail-open: a failed membership lookup never blocks the editor. It only
 * means the name is unavailable; a `summary.drifted` still renders the badge.
 *
 * States handled: loading / error / empty (no drift → render nothing) /
 * success. Colors come from `styles/tokens.css` via `<Badge>`; no inline style
 * literals (ui-ratchet).
 */

import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { artifactsApi } from "../../../api/artifacts";
import type { ArtifactBaselineMembership } from "../../../api/artifacts";
import { changeRequestsApi } from "../../../api/change-requests";
import { extractErrorMessage } from "../../../api/client";
import { Badge } from "../Badge";
import styles from "./BaselineDriftBadge.module.css";

export interface BaselineDriftSummaryProp {
  drifted: boolean;
  count: number;
}

export interface BaselineDriftBadgeProps {
  /** The backing Artifact id (`requirement.artifact_id ?? requirement.id`). */
  artifactId: string;
  workspaceId: string;
  /** Human title of the artifact, used for the pre-filled CR title. */
  artifactTitle: string;
  /** Additive drift summary from the retrieve response (spec section 6.3). */
  summary?: BaselineDriftSummaryProp | null;
  /** Called after a change request was created successfully. */
  onCreated?: () => void;
}

export function BaselineDriftBadge({
  artifactId,
  workspaceId,
  artifactTitle,
  summary,
  onCreated,
}: BaselineDriftBadgeProps): JSX.Element | null {
  const { t } = useTranslation();
  const [memberships, setMemberships] = useState<ArtifactBaselineMembership[] | null>(null);
  const [creating, setCreating] = useState(false);
  const [created, setCreated] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setMemberships(null);
    // Fail-open even if the wrapper is unavailable (a partially mocked API in
    // a host test): the badge is advisory and must never break the editor.
    let request: Promise<unknown> | undefined;
    try {
      request = artifactsApi.baselineMembership(artifactId);
    } catch {
      request = undefined;
    }
    if (!request) {
      setMemberships([]);
      return () => {
        cancelled = true;
      };
    }
    Promise.resolve(request)
      .then((response) => {
        const memberships =
          (response as { memberships?: ArtifactBaselineMembership[] } | null)
            ?.memberships ?? [];
        if (!cancelled) setMemberships(memberships);
      })
      .catch(() => {
        // Fail-open: the badge is advisory. Keeping an empty list means
        // "unknown", which falls back to the retrieve summary below.
        if (!cancelled) setMemberships([]);
      });
    return () => {
      cancelled = true;
    };
  }, [artifactId]);

  const driftedMemberships = (memberships ?? []).filter((m) => m.drifted);
  // Drift wins as soon as ANY source reports it (M5): a fail-open
  // `summary = {drifted: false}` (the membership-error path on the retrieve
  // endpoint) must not suppress a membership list that is genuinely positive.
  // Using `??` here would let the false summary mask the list.
  const drifted = summary?.drifted === true || driftedMemberships.length > 0;

  const handleCreateChangeRequest = useCallback(async () => {
    if (creating) return;
    setCreating(true);
    setCreateError(null);
    try {
      await changeRequestsApi.create({
        workspace_id: workspaceId,
        title: t("baseline.crTitle", { title: artifactTitle }),
        affected_item_ids: [artifactId],
      });
      setCreated(true);
      onCreated?.();
    } catch (err) {
      setCreateError(extractErrorMessage(err) || t("baseline.crFailed"));
    } finally {
      setCreating(false);
    }
  }, [artifactId, artifactTitle, creating, onCreated, t, workspaceId]);

  if (!drifted) return null;

  const first = driftedMemberships[0];
  const tooltip = first
    ? t("baseline.driftTooltip", {
        name: first.baseline_name,
        baselined: first.baselined_version,
        current: first.current_version,
      })
    : t("baseline.driftTooltipUnknown");
  const badgeLabel = first
    ? t("baseline.driftBadge", { name: first.baseline_name })
    : t("baseline.driftBadgeFallback");

  return (
    <div className={styles.wrapper} data-testid="baseline-drift-header">
      <Badge variant="warning" title={tooltip} testId="baseline-drift-badge">
        {badgeLabel}
      </Badge>
      <button
        type="button"
        className="btn-secondary"
        data-testid="raise-cr-from-drift"
        onClick={() => void handleCreateChangeRequest()}
        disabled={creating}
        aria-busy={creating || undefined}
      >
        {creating ? t("actions.saving", "Saving...") : t("baseline.raiseChangeRequest")}
      </button>
      {created ? (
        <span role="status" className={styles.status} data-testid="baseline-drift-cr-status">
          {t("baseline.crCreated")}
        </span>
      ) : null}
      {createError ? (
        <span role="alert" className={styles.error} data-testid="baseline-drift-cr-error">
          {createError}
        </span>
      ) : null}
    </div>
  );
}

BaselineDriftBadge.displayName = "BaselineDriftBadge";
