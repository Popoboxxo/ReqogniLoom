/**
 * ARCH-L1-001 ReactFrontend — AI prompt template admin section (REQ-L2-PT-001).
 *
 * leaf_id: COMP-RF-001 (WorkspaceSettings — admin configuration)
 * req_id:  REQ-L2-PT-001 (Tenant-scoped editable LLM prompt templates)
 *
 * Issue #119: this section previously read/wrote a flat `workspace.ai_prompts`
 * blob with two hand-written level slots, while the backend had long since
 * moved to a named, versioned `PromptTemplate` model covering every
 * AI-derivation slot with a global-default + per-workspace-override
 * resolution. It now renders one editor per slot the backend reports —
 * including the four (`testcase_derive`, `architecture_to_risk`,
 * `workspace_to_glossary`, `decision_to_adr`) that were previously reachable
 * only via MCP — and can write either scope:
 *
 *   - Scope "workspace" (workspace settings): saving publishes a workspace
 *     override; resetting deletes it so the slot falls back to the
 *     tenant-global default.
 *   - Scope "global" (system settings prompt tab): saving publishes the
 *     tenant-wide default; resetting falls back to the factory text.
 *
 * Issue #1968: the two scopes are now *separate surfaces*. This component no
 * longer renders a scope switcher — a caller mounts it with a fixed `scope`,
 * so workspace settings can never write the tenant default. A 403 (or an
 * explicit `canEdit={false}`) turns the whole section read-only with a clear
 * message instead of leaving controls that fail on every save.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  promptTemplatesApi,
  KNOWN_PROMPT_SLOTS,
  type PromptSlotState,
} from "../../api/prompt-templates";
import { promptVariablesApi, type PromptVariableState } from "../../api/prompt-variables";
import { PromptVariableTable } from "./PromptVariableTable";
import styles from "./AiPromptsSection.module.css";
import {
  classifyUserError,
  toUserErrorMessage,
} from "../../utils/userErrorMessage";

interface Props {
  /** Workspace whose overrides are edited when scope is "workspace". */
  workspaceId?: string;
  /**
   * The one scope this surface owns (issue #1968). Workspace settings passes
   * "workspace", the system settings prompt tab passes "global". No runtime
   * switcher: mixing the two is exactly the defect being fixed.
   */
  scope?: EditScope;
  /** False when the caller already knows the user may not write here. */
  canEdit?: boolean;
}

/** Which scope this mounted surface edits. */
type EditScope = "workspace" | "global";

/** Human-readable label fallbacks for the slots the product ships with. */
const SLOT_LABELS: Record<string, string> = {
  need_to_sysreq: "Stakeholder Need → System Requirements",
  sysreq_to_arch_assign: "System Requirement → Architecture Assignment",
  sysreq_decompose_next_level: "Decompose to Next Architecture Level",
  goal_aggregate: "Ziel-Aggregation",
  testcase_derive: "Requirement → Test Cases",
  architecture_to_risk: "Architecture Element → Risks",
  workspace_to_glossary: "Workspace → Glossary Terms",
  decision_to_adr: "Decision → ADR",
  // Plan B/B5-T2 (#378): the four advisory quality-assessment slots.
  quality_requirement: "Quality assessment: requirement",
  quality_adr: "Quality assessment: ADR",
  quality_testcase: "Quality assessment: test case",
  quality_risk: "Quality assessment: risk",
  "interview.chat_turn": "Interview: Chat Turn Generation",
};

const INTERVIEW_PROTOCOL_PREFIX = "interview.protocol.";

/**
 * Generates a label for `interview.protocol.<Type>` slots without a
 * per-type `SLOT_LABELS` entry -- `<Type>` is already PascalCase
 * (Artifact.artifact_type convention, engine spec §3.1), so no
 * transformation is needed beyond string concatenation. Covers future
 * artifact types automatically (interview-management web widget plan
 * Task 8).
 */
function labelForSlot(name: string): string {
  if (name.startsWith(INTERVIEW_PROTOCOL_PREFIX)) {
    return `Interview: ${name.slice(INTERVIEW_PROTOCOL_PREFIX.length)}`;
  }
  return SLOT_LABELS[name] ?? name;
}

/**
 * Order slots by the curated list first, then any unknown (MCP-created) name
 * alphabetically, so a runtime-added template is still reachable.
 */
function orderSlots(slots: PromptSlotState[]): PromptSlotState[] {
  const rank = (name: string): number => {
    const i = KNOWN_PROMPT_SLOTS.indexOf(name);
    return i === -1 ? KNOWN_PROMPT_SLOTS.length : i;
  };
  return [...slots].sort(
    (a, b) => rank(a.name) - rank(b.name) || a.name.localeCompare(b.name)
  );
}

/** The content to show for a slot at the scope currently being edited. */
function contentForScope(slot: PromptSlotState, scope: EditScope): string {
  if (scope === "workspace") return slot.effective_content;
  return slot.global_content ?? slot.factory_default ?? "";
}

/** Where the shown content comes from, at the scope being edited. */
function originForScope(slot: PromptSlotState, scope: EditScope): string {
  if (scope === "workspace") return slot.effective_scope;
  return slot.global_content === null ? "factory" : "global";
}

export function AiPromptsSection({
  workspaceId,
  scope = "workspace",
  canEdit = true,
}: Props): JSX.Element {
  const { t } = useTranslation();
  const [slots, setSlots] = useState<PromptSlotState[]>([]);
  const [variables, setVariables] = useState<PromptVariableState[]>([]);
  // Only slots the admin actually edited appear here — an absent entry means
  // "show whatever the server last reported", so a scope switch or a reset
  // does not have to reconcile stale local copies.
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [isLoading, setIsLoading] = useState(true);
  const [busySlot, setBusySlot] = useState<string | null>(null);
  const [savedSlot, setSavedSlot] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Issue #1968: an RBAC-denied request makes the rest of the form useless.
  // Remember it so every control can be disabled with one clear message.
  const [accessDenied, setAccessDenied] = useState(false);
  const readOnly = !canEdit || accessDenied;

  const load = useCallback(async (): Promise<void> => {
    setError(null);
    // Fetched independently via allSettled, not Promise.all: the variable
    // catalog only feeds the supplementary per-slot variable table, so a
    // failure there (endpoint not yet deployed everywhere, a permission
    // gap, a transient 500) must never block the core, already-productive
    // prompt editor (save/reset) — which worked off a single `listSlots`
    // fetch before this feature existed and must keep doing so even if the
    // new catalog call errors.
    const [slotsResult, variablesResult] = await Promise.allSettled([
      promptTemplatesApi.listSlots(workspaceId),
      promptVariablesApi.list(workspaceId),
    ]);

    if (slotsResult.status === "fulfilled") {
      setSlots(orderSlots(slotsResult.value.slots));
      setDrafts({});
    } else {
      if (classifyUserError(slotsResult.reason) === "unauthorized") {
        setAccessDenied(true);
      }
      setError(toUserErrorMessage(slotsResult.reason, t));
    }

    // Best-effort: on failure the variable table simply has nothing to show
    // for any slot instead of surfacing a global error.
    setVariables(
      variablesResult.status === "fulfilled" ? variablesResult.value.variables : []
    );

    setIsLoading(false);
  }, [workspaceId]);

  useEffect(() => {
    void load();
  }, [load]);

  const orderedSlots = useMemo(() => orderSlots(slots), [slots]);

  const handleChange = (name: string, next: string): void => {
    setDrafts((prev) => ({ ...prev, [name]: next }));
    setSavedSlot(null);
  };

  /** Fail closed: a workspace-scope mount must never fall back to a global write. */
  const targetScopeId = (): string | null => {
    if (scope === "global") return null;
    if (!workspaceId) {
      throw new Error("A workspaceId is required for workspace-scope prompt writes");
    }
    return workspaceId;
  };

  /** Replace one slot in local state with the server's post-write truth. */
  const applyUpdated = (updated: PromptSlotState): void => {
    setSlots((prev) =>
      prev.map((s) => (s.name === updated.name ? updated : s))
    );
    setDrafts((prev) => {
      const next = { ...prev };
      delete next[updated.name];
      return next;
    });
  };

  /**
   * A global-scope write omits `workspace_id`, so the server's response does
   * not resolve that workspace's rows. Refetch with the workspace id instead
   * of merging a partial state that would blank out its overrides in the UI.
   */
  const applyWriteResult = async (updated: PromptSlotState): Promise<void> => {
    if (scope === "global") {
      await load();
      return;
    }
    applyUpdated(updated);
  };

  const handleSave = async (slot: PromptSlotState): Promise<void> => {
    if (readOnly) return;
    setBusySlot(slot.name);
    setError(null);
    setSavedSlot(null);
    try {
      const updated = await promptTemplatesApi.saveSlot(
        slot.name,
        drafts[slot.name] ?? contentForScope(slot, scope),
        targetScopeId()
      );
      await applyWriteResult(updated);
      setSavedSlot(slot.name);
    } catch (err) {
      if (classifyUserError(err) === "unauthorized") setAccessDenied(true);
      setError(toUserErrorMessage(err, t));
    } finally {
      setBusySlot(null);
    }
  };

  const handleReset = async (slot: PromptSlotState): Promise<void> => {
    if (readOnly) return;
    setBusySlot(slot.name);
    setError(null);
    setSavedSlot(null);
    try {
      const updated = await promptTemplatesApi.clearSlot(
        slot.name,
        targetScopeId()
      );
      await applyWriteResult(updated);
    } catch (err) {
      if (classifyUserError(err) === "unauthorized") setAccessDenied(true);
      setError(toUserErrorMessage(err, t));
    } finally {
      setBusySlot(null);
    }
  };

  const originLabel = (origin: string): string => {
    if (origin === "workspace") {
      return t("settings.promptTemplates.origin.workspace", "Workspace-Override");
    }
    if (origin === "global") {
      return t("settings.promptTemplates.origin.global", "Globaler Standard");
    }
    return t("settings.promptTemplates.origin.factory", "Werkseinstellung");
  };

  if (isLoading) {
    return (
      <section className={styles.section} data-testid="prompt-template-section">
        <h3 className={styles.heading}>
          {t("settings.promptTemplates.title", "AI Prompt Templates")}
        </h3>
        <p>{t("loading", "Loading...")}</p>
      </section>
    );
  }

  return (
    <section className={styles.section} data-testid="prompt-template-section">
      <h3 className={styles.heading}>
        {t("settings.promptTemplates.title", "AI Prompt Templates")}
      </h3>
      <p className={styles.hint}>
        {t(
          "settings.promptTemplates.description",
          "Customise the prompts used for AI-assisted derivation. Available placeholders: " +
            "{n} (number of drafts requested), {need_title} and {need_description} " +
            "(stakeholder need), {req_title} and {req_description} (requirement), and " +
            "{arch_elements_json} (candidate architecture elements). Unknown or omitted " +
            "placeholders are left as-is, so existing templates keep working (REQ-046)."
        )}
      </p>

      {orderedSlots.some((s) => s.name.startsWith("interview.")) && (
        <p className={styles.hint}>
          {t(
            "settings.promptTemplates.interviewDescription",
            "Interview prompt placeholders differ by slot. " +
              "interview.protocol.<Type> (phase prompt_fragment): {artifact_type}, {phase_name}, " +
              "{collected_fields_json}, {missing_fields_json}, {grounding_snapshot_json}. " +
              "interview.chat_turn: {transcript_json}, {transcript_summary}, {user_message}, " +
              "{current_phase_fragment}, {missing_fields_json}, {grounding_snapshot_json}, " +
              "{memory_context}. " +
              "interview.transcript_summary: {previous_summary}, {overflow_json}."
          )}
        </p>
      )}

      {/* Issue #1968: no scope switcher — the mounting surface owns the
          scope. The note replaces the former dropdown's orientation. */}
      <p className={styles.hint} data-testid="prompt-template-scope-note">
        {scope === "workspace"
          ? t("settings.promptTemplates.scopeWorkspaceNote")
          : t("settings.promptTemplates.scopeGlobalNote")}
      </p>

      {readOnly && (
        <p
          role="alert"
          data-testid="prompt-template-readonly"
          className={styles.warning}
        >
          {t("settings.promptTemplates.readOnly")}
        </p>
      )}

      {error && (
        <p
          role="alert"
          data-testid="prompt-template-error"
          className={styles.errorText}
        >
          {error}
        </p>
      )}

      {orderedSlots.map((slot) => {
        const origin = originForScope(slot, scope);
        const value = drafts[slot.name] ?? contentForScope(slot, scope);
        const isBusy = busySlot === slot.name;
        // Nothing to clear when the shown value is already inherited.
        const canReset = origin === scope;
        return (
          <div key={slot.name} className={styles.slot}>
            <label className={styles.fieldLabel} htmlFor={`prompt-${slot.name}`}>
              {t(
                `settings.promptTemplates.slot.${slot.name}`,
                // The quality-assessment slots reuse the short
                // `aiPrompts.slots.*` namespace (Plan B/B5-T2); the English
                // constant remains the last resort, so a new slot never
                // renders its raw name.
                t(`aiPrompts.slots.${slot.name}`, labelForSlot(slot.name))
              )}
              <span className={styles.badge} data-testid={`prompt-${slot.name}-origin`}>
                {originLabel(origin)}
              </span>
            </label>
            <textarea
              id={`prompt-${slot.name}`}
              data-testid={`prompt-${slot.name}-input`}
              value={value}
              onChange={(e) => handleChange(slot.name, e.target.value)}
              disabled={readOnly}
              className={styles.textarea}
            />
            <div className={styles.buttonRow}>
              <button
                type="button"
                data-testid={`prompt-${slot.name}-save`}
                onClick={() => void handleSave(slot)}
                disabled={isBusy || readOnly}
                className="btn-primary"
              >
                {isBusy ? t("actions.saving") : t("actions.save")}
              </button>
              <button
                type="button"
                data-testid={`prompt-${slot.name}-reset`}
                onClick={() => void handleReset(slot)}
                disabled={isBusy || readOnly || !canReset}
                className="btn-secondary"
              >
                {scope === "workspace"
                  ? t(
                      "settings.promptTemplates.resetToGlobal",
                      "Override entfernen"
                    )
                  : t("settings.promptTemplates.reset", "Reset to default")}
              </button>
              {savedSlot === slot.name && (
                <span
                  data-testid={`prompt-${slot.name}-saved`}
                  className={styles.savedText}
                >
                  {t("settings.saved", "Saved")}
                </span>
              )}
            </div>
            <PromptVariableTable
              slotName={slot.name}
              variableNames={[...slot.data_variables, ...slot.config_variables]}
              variables={variables}
            />
            {slot.unknown_placeholders.length > 0 && (
              <p
                className={styles.warning}
                data-testid={`prompt-${slot.name}-unknown-placeholders`}
              >
                {t(
                  "settings.promptTemplates.unknownPlaceholders",
                  "Unbekannte Platzhalter — sie bleiben im Prompt-Text stehen:"
                )}{" "}
                {slot.unknown_placeholders.map((p) => `{${p}}`).join(", ")}
              </p>
            )}
          </div>
        );
      })}
    </section>
  );
}
