/**
 * ARCH-L1-001 ReactFrontend — SE-Auditor context data (#598 S2).
 *
 * Three independent reads the audit dashboard needs beside the run itself:
 * the workspace's artifacts (document-scope picker), the audit rule catalogue
 * (rule-id popover) and the persisted suppressions (`#569`).
 *
 * These are a *move* of the dashboard's own effects, not a react-query
 * migration: the dashboard's 60+ behavioural tests pin their lifecycles
 * (independent loading/error/empty states, reload after a waive) and the plan's
 * stronger constraint is "the refactor changes no behaviour". Mapping them onto
 * the query cache would change those lifecycles and is left to a separate
 * change.
 *
 * Every read degrades on purpose:
 *   - artifacts and the rule catalogue are non-critical; a failure leaves the
 *     feature usable (empty picker, bare rule id),
 *   - the suppression list is critical to *its own* panel, so it keeps its own
 *     loading/error state instead of looking like "none on file" (UI-569-02).
 */

import { useCallback, useEffect, useState } from "react";
import type { TFunction } from "i18next";

import { artifactsApi } from "../../api/artifacts";
import { auditApi } from "../../api/audit";
import type { AuditRuleInfo, SuppressionView } from "../../api/audit";
import type { Artifact } from "../../types";

import { resolveErrorMessage } from "./use-audit-run";

/**
 * Load the workspace's artifacts once per workspace identity.
 *
 * Only the document-scope picker consumes the list; project/global runs must
 * not fail when the request does.
 */
export function useScopeArtifacts(workspaceId: string | undefined): Artifact[] {
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);

  useEffect(() => {
    if (!workspaceId) {
      setArtifacts([]);
      return;
    }
    let cancelled = false;
    void artifactsApi
      .list(workspaceId)
      .then((resp) => {
        if (!cancelled) setArtifacts(resp.results);
      })
      .catch(() => {
        // Non-critical for project/global scope — document scope will simply
        // show an empty picker and the user can switch scope back.
      });
    return () => {
      cancelled = true;
    };
  }, [workspaceId]);

  return artifacts;
}

/**
 * The rule catalogue backing the rule-id popover (#1262).
 *
 * Non-critical: on failure the popover degrades to the bare rule id.
 */
export function useAuditRules(): Record<string, AuditRuleInfo> {
  const [ruleInfo, setRuleInfo] = useState<Record<string, AuditRuleInfo>>({});

  useEffect(() => {
    let cancelled = false;
    void Promise.resolve(auditApi.rules?.())
      .then((resp) => {
        if (cancelled) return;
        const map: Record<string, AuditRuleInfo> = {};
        for (const rule of resp?.rules ?? []) map[rule.rule_id] = rule;
        setRuleInfo(map);
      })
      .catch(() => {
        // Non-critical: popover falls back to the rule id.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return ruleInfo;
}

export interface UseAuditWaiversResult {
  /** Every persisted suppression, both lifecycles (#569). */
  waivers: SuppressionView[];
  waiversLoading: boolean;
  waiversError: string | null;
  /** Re-read after a waive, so the new suppression appears immediately. */
  loadWaivers: () => Promise<void>;
}

/**
 * Load every suppression (both lifecycles).
 *
 * Non-critical to the audit run — a failure must not blank the findings list —
 * but it must not be indistinguishable from "no suppressions on file" either
 * (UI-569-02), hence the dedicated flags.
 */
export function useAuditWaivers(
  workspaceId: string | undefined,
  t: TFunction
): UseAuditWaiversResult {
  const [waivers, setWaivers] = useState<SuppressionView[]>([]);
  const [waiversLoading, setWaiversLoading] = useState<boolean>(false);
  const [waiversError, setWaiversError] = useState<string | null>(null);

  const loadWaivers = useCallback(async (): Promise<void> => {
    if (!workspaceId) return;
    setWaiversLoading(true);
    setWaiversError(null);
    try {
      const resp = await auditApi.waivers(workspaceId, "all");
      setWaivers(resp?.waivers ?? []);
    } catch (err) {
      setWaiversError(
        resolveErrorMessage(
          err,
          t("audit.waivers.loadError", "Could not load suppressions.")
        )
      );
    } finally {
      setWaiversLoading(false);
    }
  }, [workspaceId, t]);

  useEffect(() => {
    void loadWaivers();
    // Reload only when the workspace identity changes, matching the previous
    // dashboard effect (`activeWorkspace?.id`), not the object identity.
  }, [workspaceId]); // eslint-disable-line react-hooks/exhaustive-deps

  return { waivers, waiversLoading, waiversError, loadWaivers };
}
