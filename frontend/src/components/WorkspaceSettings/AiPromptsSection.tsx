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
 *   - Scope "workspace": saving publishes a workspace override; resetting
 *     deletes it so the slot falls back to the tenant-global default.
 *   - Scope "global": saving publishes the tenant-wide default; resetting
 *     falls back to the factory text shipped with the product.
 *
 * The scope switch exists because the previous section was the only UI able to
 * edit tenant-wide prompts; dropping to workspace-only editing would have
 * traded one gap for another.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  promptTemplatesApi,
  KNOWN_PROMPT_SLOTS,
  type PromptSlotState,
} from "../../api/prompt-templates";
import { extractErrorMessage } from "../../api/client";

interface Props {
  /** Workspace whose overrides are edited when scope is "workspace". */
  workspaceId: string;
}

/** Which scope the admin is currently editing. */
type EditScope = "workspace" | "global";

const sectionStyle: React.CSSProperties = {
  background: "var(--color-surface)",
  border: "1px solid var(--color-border)",
  borderRadius: "var(--radius-lg)",
  padding: "var(--space-5)",
  marginBottom: "var(--space-5)",
  boxShadow: "var(--shadow-card)",
};

const headingStyle: React.CSSProperties = {
  fontSize: "var(--font-size-lg)",
  fontWeight: 600,
  color: "var(--color-text)",
  margin: "0 0 var(--space-4) 0",
};

const hintStyle: React.CSSProperties = {
  fontSize: "var(--font-size-sm)",
  color: "var(--color-text-muted)",
  marginBottom: "var(--space-4)",
};

const fieldLabelStyle: React.CSSProperties = {
  display: "block",
  marginBottom: "var(--space-2)",
  fontWeight: 600,
  color: "var(--color-text)",
  fontSize: "var(--font-size-sm)",
};

const textareaStyle: React.CSSProperties = {
  width: "100%",
  minHeight: "120px",
  padding: "var(--space-2) var(--space-3)",
  background: "var(--color-surface-raised)",
  border: "1px solid var(--color-border)",
  borderRadius: "var(--radius-md)",
  color: "var(--color-text)",
  fontSize: "var(--font-size-sm)",
  fontFamily: "var(--font-mono, monospace)",
  resize: "vertical",
};

const primaryButtonStyle: React.CSSProperties = {
  background: "var(--color-primary)",
  color: "white",
  border: "none",
  borderRadius: "var(--radius-md)",
  padding: "var(--space-2) var(--space-4)",
  fontSize: "var(--font-size-sm)",
  fontWeight: 600,
  cursor: "pointer",
};

const secondaryButtonStyle: React.CSSProperties = {
  background: "transparent",
  color: "var(--color-text-muted)",
  border: "1px solid var(--color-border)",
  borderRadius: "var(--radius-md)",
  padding: "var(--space-2) var(--space-3)",
  fontSize: "var(--font-size-sm)",
  cursor: "pointer",
};

const badgeStyle: React.CSSProperties = {
  display: "inline-block",
  padding: "2px var(--space-2)",
  borderRadius: "var(--radius-sm, 4px)",
  border: "1px solid var(--color-border)",
  fontSize: "var(--font-size-xs, 0.75rem)",
  color: "var(--color-text-muted)",
  marginLeft: "var(--space-2)",
  fontWeight: 500,
};

const selectStyle: React.CSSProperties = {
  padding: "var(--space-2) var(--space-3)",
  background: "var(--color-surface-raised)",
  border: "1px solid var(--color-border)",
  borderRadius: "var(--radius-md)",
  color: "var(--color-text)",
  fontSize: "var(--font-size-sm)",
};

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
};

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

export function AiPromptsSection({ workspaceId }: Props): JSX.Element {
  const { t } = useTranslation();
  const [scope, setScope] = useState<EditScope>("workspace");
  const [slots, setSlots] = useState<PromptSlotState[]>([]);
  // Only slots the admin actually edited appear here — an absent entry means
  // "show whatever the server last reported", so a scope switch or a reset
  // does not have to reconcile stale local copies.
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [isLoading, setIsLoading] = useState(true);
  const [busySlot, setBusySlot] = useState<string | null>(null);
  const [savedSlot, setSavedSlot] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (): Promise<void> => {
    setError(null);
    try {
      const data = await promptTemplatesApi.listSlots(workspaceId);
      setSlots(orderSlots(data.slots));
      setDrafts({});
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setIsLoading(false);
    }
  }, [workspaceId]);

  useEffect(() => {
    void load();
  }, [load]);

  const orderedSlots = useMemo(() => orderSlots(slots), [slots]);

  const handleScopeChange = (next: EditScope): void => {
    // Drafts are scope-specific: keeping them would silently carry a
    // workspace-override edit into a tenant-wide save.
    setScope(next);
    setDrafts({});
    setSavedSlot(null);
    setError(null);
  };

  const handleChange = (name: string, next: string): void => {
    setDrafts((prev) => ({ ...prev, [name]: next }));
    setSavedSlot(null);
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

  const handleSave = async (slot: PromptSlotState): Promise<void> => {
    setBusySlot(slot.name);
    setError(null);
    setSavedSlot(null);
    try {
      const updated = await promptTemplatesApi.saveSlot(
        slot.name,
        drafts[slot.name] ?? contentForScope(slot, scope),
        scope === "workspace" ? workspaceId : null
      );
      applyUpdated(updated);
      setSavedSlot(slot.name);
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setBusySlot(null);
    }
  };

  const handleReset = async (slot: PromptSlotState): Promise<void> => {
    setBusySlot(slot.name);
    setError(null);
    setSavedSlot(null);
    try {
      const updated = await promptTemplatesApi.clearSlot(
        slot.name,
        scope === "workspace" ? workspaceId : null
      );
      applyUpdated(updated);
    } catch (err) {
      setError(extractErrorMessage(err));
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
      <section style={sectionStyle} data-testid="prompt-template-section">
        <h3 style={headingStyle}>
          {t("settings.promptTemplates.title", "AI Prompt Templates")}
        </h3>
        <p>{t("loading", "Loading...")}</p>
      </section>
    );
  }

  return (
    <section style={sectionStyle} data-testid="prompt-template-section">
      <h3 style={headingStyle}>
        {t("settings.promptTemplates.title", "AI Prompt Templates")}
      </h3>
      <p style={hintStyle}>
        {t(
          "settings.promptTemplates.description",
          "Customise the prompts used for AI-assisted derivation. Available placeholders: " +
            "{n} (number of drafts requested), {need_title} and {need_description} " +
            "(stakeholder need), {req_title} and {req_description} (requirement), and " +
            "{arch_elements_json} (candidate architecture elements). Unknown or omitted " +
            "placeholders are left as-is, so existing templates keep working (REQ-046)."
        )}
      </p>

      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "var(--space-3)",
          marginBottom: "var(--space-4)",
        }}
      >
        <label htmlFor="prompt-scope-select" style={{ ...fieldLabelStyle, marginBottom: 0 }}>
          {t("settings.promptTemplates.scope", "Geltungsbereich")}
        </label>
        <select
          id="prompt-scope-select"
          data-testid="prompt-scope-select"
          value={scope}
          onChange={(e) => handleScopeChange(e.target.value as EditScope)}
          style={selectStyle}
        >
          <option value="workspace">
            {t("settings.promptTemplates.scopeWorkspace", "Nur dieser Workspace")}
          </option>
          <option value="global">
            {t("settings.promptTemplates.scopeGlobal", "Global (alle Workspaces)")}
          </option>
        </select>
      </div>

      {error && (
        <p
          data-testid="prompt-template-error"
          style={{ color: "var(--color-danger)", marginBottom: "var(--space-3)" }}
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
          <div key={slot.name} style={{ marginBottom: "var(--space-4)" }}>
            <label style={fieldLabelStyle} htmlFor={`prompt-${slot.name}`}>
              {t(
                `settings.promptTemplates.slot.${slot.name}`,
                SLOT_LABELS[slot.name] ?? slot.name
              )}
              <span style={badgeStyle} data-testid={`prompt-${slot.name}-origin`}>
                {originLabel(origin)}
              </span>
            </label>
            <textarea
              id={`prompt-${slot.name}`}
              data-testid={`prompt-${slot.name}-input`}
              value={value}
              onChange={(e) => handleChange(slot.name, e.target.value)}
              style={textareaStyle}
            />
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: "var(--space-2)",
                marginTop: "var(--space-2)",
              }}
            >
              <button
                type="button"
                data-testid={`prompt-${slot.name}-save`}
                onClick={() => void handleSave(slot)}
                disabled={isBusy}
                style={{
                  ...primaryButtonStyle,
                  cursor: isBusy ? "not-allowed" : "pointer",
                  opacity: isBusy ? 0.7 : 1,
                }}
              >
                {isBusy ? t("saving", "Saving...") : t("save", "Save")}
              </button>
              <button
                type="button"
                data-testid={`prompt-${slot.name}-reset`}
                onClick={() => void handleReset(slot)}
                disabled={isBusy || !canReset}
                style={{
                  ...secondaryButtonStyle,
                  cursor: isBusy || !canReset ? "not-allowed" : "pointer",
                  opacity: isBusy || !canReset ? 0.5 : 1,
                }}
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
                  style={{ color: "var(--color-success)", fontSize: "var(--font-size-sm)" }}
                >
                  {t("settings.saved", "Saved")}
                </span>
              )}
            </div>
          </div>
        );
      })}
    </section>
  );
}
