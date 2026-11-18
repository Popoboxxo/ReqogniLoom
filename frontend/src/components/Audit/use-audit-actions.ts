/**
 * Audit dashboard — finding actions and their dialogs (S3.2 WP-5 split by
 * cohesion).
 *
 * Extracted verbatim from `audit-dashboard.tsx`: Adopt (confirm + remediate),
 * Modify (navigate to the resolved artifact) and Waive (justified suppression,
 * including the required-field validation and the post-waive focus hand-off),
 * plus the success toast and its auto-dismiss timer. All three are reactions to
 * a *user decision on one finding*; they share the per-finding action state and
 * mutate the run through its setters. The run, the filters and the view
 * selectors stay in their own modules.
 *
 * The dialog markup and every data-testid / ARIA attribute remain in the
 * component — this hook only owns state and callbacks.
 */

import { useCallback, useEffect, useState } from "react";
import type { Dispatch, SetStateAction } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { auditApi } from "../../api/audit";
import type {
  AuditFinding,
  AuditScopeKind,
  WaiveRequest,
} from "../../api/audit";
import { UnprocessableEntityError } from "../../api/errors";
import { useRequiredValidation } from "../shared/useRequiredValidation";
import type { RequiredValidation } from "../shared/useRequiredValidation";
import { useFindingTargets } from "./use-finding-targets";
import type { FindingTarget, FindingTargetMap } from "./use-finding-targets";
import {
  findingIdentity,
  resolveErrorMessage,
} from "./use-audit-run";
import type { ActionStateMap } from "./use-audit-run";
import { waiverErrorCode } from "./audit-dashboard.logic";

export interface UseAuditActionsOptions {
  workspaceId: string | undefined;
  scope: AuditScopeKind;
  scopeArtifactId: string;
  findings: AuditFinding[];
  loadWaivers: () => void | Promise<void>;
  setFindings: Dispatch<SetStateAction<AuditFinding[]>>;
  setActionState: Dispatch<SetStateAction<ActionStateMap>>;
  setAdoptedSinceRun: Dispatch<SetStateAction<AuditFinding[]>>;
  setWaivedSinceRun: Dispatch<SetStateAction<AuditFinding[]>>;
  setNextOffset: Dispatch<SetStateAction<number | null>>;
}

export interface UseAuditActionsResult {
  toast: string | null;
  targets: FindingTargetMap;
  pendingAdopt: AuditFinding | null;
  requestAdopt: (finding: AuditFinding) => void;
  cancelAdopt: () => void;
  confirmAdopt: () => void;
  handleModify: (target: FindingTarget) => void;
  pendingWaive: AuditFinding | null;
  waiveReason: string;
  setWaiveReason: Dispatch<SetStateAction<string>>;
  waiveExpiresAt: string;
  setWaiveExpiresAt: Dispatch<SetStateAction<string>>;
  waiveError: string | null;
  isWaiving: boolean;
  requestWaive: (finding: AuditFinding) => void;
  cancelWaive: () => void;
  confirmWaive: () => Promise<void>;
  validation: RequiredValidation;
}

export function useAuditActions({
  workspaceId,
  scope,
  scopeArtifactId,
  findings,
  loadWaivers,
  setFindings,
  setActionState,
  setAdoptedSinceRun,
  setWaivedSinceRun,
  setNextOffset,
}: UseAuditActionsOptions): UseAuditActionsResult {
  const { t } = useTranslation();
  const navigate = useNavigate();

  const [toast, setToast] = useState<string | null>(null);
  // UI-57: Adopt applies an automatic correction with no undo — interpose a
  // confirmation instead of firing the remediation call straight from the
  // row button.
  const [pendingAdopt, setPendingAdopt] = useState<AuditFinding | null>(null);
  // #569: the Waive action opens a dialog that requires a justification before
  // it can be confirmed — a suppression without a reason must not be possible.
  const [pendingWaive, setPendingWaive] = useState<AuditFinding | null>(null);
  const [waiveReason, setWaiveReason] = useState<string>("");
  const [waiveExpiresAt, setWaiveExpiresAt] = useState<string>("");
  const [waiveError, setWaiveError] = useState<string | null>(null);
  // #1732: the mandatory justification is validated on click and marked at the
  // textarea; the Waive button is only disabled while a request is in flight.
  const validation = useRequiredValidation();
  const { validate, focusFirstInvalid } = validation;
  const [isWaiving, setIsWaiving] = useState<boolean>(false);
  // UI-569-03: a successful waive unmounts the row's Waive trigger, so the
  // dialog's focus trap cannot restore focus to it. This carries the index of
  // the row that should take focus instead.
  const [focusFindingIndex, setFocusFindingIndex] = useState<number | null>(null);

  // Auto-dismiss the success toast.
  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(() => setToast(null), 4000);
    return () => clearTimeout(timer);
  }, [toast]);

  // UI-569-03: after a successful waive the finding flips to `suppressed` and
  // its Waive trigger unmounts — so the dialog's focus trap skips the restore
  // (`previouslyFocused.isConnected` is false) and keyboard focus falls to
  // `<body>`. Move it explicitly onto the still-mounted finding row
  // (`tabIndex={-1}`, so it stays out of the Tab cycle), which keeps the user's
  // place in the list after the decision.
  useEffect(() => {
    if (focusFindingIndex === null) return;
    const row = document.querySelector<HTMLElement>(
      `[data-testid="audit-finding-${focusFindingIndex}"]`
    );
    if (!row) return;
    row.focus();
    setFocusFindingIndex(null);
  }, [focusFindingIndex, findings]);

  // ---- Adopt workflow ----
  const handleAdopt = useCallback(
    async (finding: AuditFinding): Promise<void> => {
      if (!workspaceId) return;
      // NFA-2: every local bookkeeping entry is addressed by the
      // run-independent identity. `index` is only the row's position in the
      // run that produced *its* window, so a shifted window can reuse the
      // index of a row that is already mounted.
      const identity = findingIdentity(finding);
      setActionState((prev) => ({ ...prev, [identity]: { status: "pending" } }));
      try {
        await auditApi.remediate(workspaceId, {
          rule_id: finding.rule_id,
          artifact_ids: finding.artifact_ids,
          scope,
          scope_artifact_id: scope === "document" ? scopeArtifactId : undefined,
        });
        setFindings((prev) => prev.filter((f) => findingIdentity(f) !== identity));
        // #1383: the report's counts are a snapshot from the last run — record
        // the local resolution so the badges can still shrink (see `counts`).
        setAdoptedSinceRun((prev) => [...prev, finding]);
        // NF-A/NFA-1: an Adopt removes one row from the run, so every finding
        // behind it shifts down by one position. `nextOffset` is a server
        // cursor and is honoured verbatim otherwise, but this LOCAL mutation
        // invalidates it: paging from the old cursor would skip the finding
        // that moved into the adopted row's slot. The adopted row is always a
        // *mounted* row that the cursor already covers, so every successful
        // Adopt moves the cursor by exactly one and no index comparison is
        // needed — `finding.index` is a position in the stale snapshot and is
        // not comparable with a cursor that an earlier adopt already
        // decremented (that comparison under-decremented from the second
        // adopt on the same page and skipped a finding permanently).
        setNextOffset((prev) => (prev === null ? prev : Math.max(0, prev - 1)));
        setActionState((prev) => {
          const next = { ...prev };
          delete next[identity];
          return next;
        });
        setToast(t("audit.adoptSuccess", "Resolved — the correction was applied."));
      } catch (err) {
        if (err instanceof UnprocessableEntityError) {
          // Not automatically fixable (anymore) — flip this finding into the
          // manual "Modify" state in-place instead of leaving a dead button.
          setFindings((prev) =>
            prev.map((f) =>
              findingIdentity(f) === identity
                ? { ...f, remediation: { ...f.remediation, automatic: false, reason: err.message } }
                : f
            )
          );
          setActionState((prev) => ({
            ...prev,
            [identity]: { status: "error", message: err.message },
          }));
        } else {
          setActionState((prev) => ({
            ...prev,
            [identity]: {
              status: "error",
              message: resolveErrorMessage(err, t("audit.actionError")),
            },
          }));
        }
      }
    },
    [
      workspaceId,
      scope,
      scopeArtifactId,
      t,
      setActionState,
      setAdoptedSinceRun,
      setFindings,
      setNextOffset,
    ]
  );

  // UI-57: Adopt has no undo (it PATCHes/creates trace links straight away) —
  // the row button opens the confirmation, the confirmation fires the actual
  // mutation. Mirrors UserManagement's request/confirm split.
  const requestAdopt = useCallback((finding: AuditFinding): void => {
    setPendingAdopt(finding);
  }, []);

  const cancelAdopt = useCallback((): void => {
    setPendingAdopt(null);
  }, []);

  const confirmAdopt = useCallback((): void => {
    if (!pendingAdopt) return;
    const finding = pendingAdopt;
    setPendingAdopt(null);
    void handleAdopt(finding);
  }, [pendingAdopt, handleAdopt]);

  // ---- Modify workflow (GitHub #451) ----
  // A finding is cleared by correcting the artifact it points at, so "Modify"
  // is a navigation, not a mutation — there is no finding to PATCH.
  const targets = useFindingTargets(findings);

  const handleModify = useCallback(
    (target: FindingTarget): void => {
      navigate(target.route);
    },
    [navigate]
  );

  // ---- Waive workflow (#569) ----
  // The third action: record a justified suppression for a reported BLOCKER
  // finding. Unlike Adopt it removes nothing — the finding stays in the list,
  // marked as suppressed, so the decision stays visible.
  const waiveErrorMessage = useCallback(
    (err: unknown): string => {
      // The stable `error.code` decides the message. A rejected justification
      // must be reason-specific, and a waive failure must NEVER fall through
      // into the Adopt/Modify flip (that flip belongs to a 422 from
      // `remediate` alone — the waive paths never emit 422, spec E18).
      switch (waiverErrorCode(err)) {
        case "WAIVER_REASON_REJECTED":
          return t(
            "audit.waiveReasonRejected",
            "The justification does not satisfy the policy."
          );
        case "WAIVER_FINDING_NOT_BLOCKING":
          return t("audit.waiveNotBlocking", "This finding is not a blocker right now.");
        case "SUPPRESSION_EXPIRED":
          return t(
            "audit.waiveExpired",
            "An expired suppression already exists for this finding."
          );
        case "PERMISSION_DENIED":
          return t("audit.waiveForbidden", "You are not allowed to suppress findings.");
        default:
          // VALIDATION_ERROR (field-level feedback) and anything else: prefer
          // the server's concrete message over a generic one.
          return resolveErrorMessage(err, t("audit.actionError"));
      }
    },
    [t]
  );

  const requestWaive = useCallback((finding: AuditFinding): void => {
    setPendingWaive(finding);
    setWaiveReason("");
    setWaiveExpiresAt("");
    setWaiveError(null);
  }, []);

  const cancelWaive = useCallback((): void => {
    if (isWaiving) return;
    setPendingWaive(null);
    setWaiveError(null);
  }, [isWaiving]);

  const confirmWaive = useCallback(async (): Promise<void> => {
    if (!workspaceId || !pendingWaive) return;
    const finding = pendingWaive;
    const reason = waiveReason.trim();
    // "No silent suppression": a justification is mandatory in the UI too.
    const fields = [
      {
        name: "waiveReason",
        value: waiveReason,
        inputId: "audit-waive-reason-input",
        message: t("audit.waiveReasonRequired", "Please provide a justification."),
      },
    ];
    const invalid = validate(fields);
    if (invalid.length > 0) {
      focusFirstInvalid(fields, invalid);
      setWaiveError(t("audit.waiveReasonRequired", "Please provide a justification."));
      return;
    }
    setIsWaiving(true);
    setWaiveError(null);
    try {
      const body: WaiveRequest = {
        rule_id: finding.rule_id,
        artifact_ids: finding.artifact_ids,
        reason,
      };
      // C1: the engine scope of the clicked row must travel with the request
      // so the existence check runs over the same scope the finding was
      // reported in — a document-scoped finding is otherwise unreachable.
      if (finding.scope) body.scope = finding.scope;
      if (finding.scope === "document" && finding.scope_artifact_id) {
        body.scope_artifact_id = finding.scope_artifact_id;
      }
      if (waiveExpiresAt) {
        // <input type="datetime-local"> yields a *naive* local value; the
        // backend rejects naive timestamps, so normalise to UTC ISO-8601.
        body.expires_at = new Date(waiveExpiresAt).toISOString();
      }
      const view = await auditApi.waive(workspaceId, body);
      // Mark the finding in-place as suppressed — it is NOT removed, so the
      // suppression stays visible (Nachvollziehbarkeit statt Verstecken).
      // NFA-2: matched by identity, not by `index` — after a shifted window a
      // second, *different* row can carry the same numeric index, and keying on
      // it would mark both as suppressed.
      const identity = findingIdentity(finding);
      setFindings((prev) =>
        prev.map((f) =>
          findingIdentity(f) === identity
            ? {
                ...f,
                suppressed: true,
                suppressed_until: view.expires_at,
                suppression_reason: view.reason,
                suppression_id: view.waiver_id,
              }
            : f
        )
      );
      setPendingWaive(null);
      // #1383: the snapshot predates this waiver, so the suppressed badges
      // would otherwise stay at their pre-waive value.
      setWaivedSinceRun((prev) => [...prev, finding]);
      setToast(t("audit.waiveSuccess", "Suppression saved."));
      // UI-569-03: the trigger that opened the dialog is about to unmount.
      setFocusFindingIndex(finding.index);
      void loadWaivers();
    } catch (err) {
      // Deliberately NOT `instanceof UnprocessableEntityError`: the waive
      // paths never emit 422, and routing a failure here into the Modify
      // flip would misreport a rejected reason as an Adopt conflict.
      setWaiveError(waiveErrorMessage(err));
    } finally {
      setIsWaiving(false);
    }
  }, [
    workspaceId,
    pendingWaive,
    waiveReason,
    waiveExpiresAt,
    t,
    waiveErrorMessage,
    loadWaivers,
    validate,
    focusFirstInvalid,
    setFindings,
    setWaivedSinceRun,
  ]);

  return {
    toast,
    targets,
    pendingAdopt,
    requestAdopt,
    cancelAdopt,
    confirmAdopt,
    handleModify,
    pendingWaive,
    waiveReason,
    setWaiveReason,
    waiveExpiresAt,
    setWaiveExpiresAt,
    waiveError,
    isWaiving,
    requestWaive,
    cancelWaive,
    confirmWaive,
    validation,
  };
}
