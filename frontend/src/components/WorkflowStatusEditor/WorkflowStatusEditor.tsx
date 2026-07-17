/**
 * ARCH-L1-001 ReactFrontend — Unified Workflow Status Editor.
 *
 * leaf_id: COMP-RF-003
 * req_id:  REQ-160 (WorkflowFacade-driven transitions), REQ-161 (unified editor)
 *
 * A single, reusable control that renders the current WorkflowEngine state as a
 * status badge and the allowed transitions as an accessible dropdown menu, and
 * performs the transition through the WorkflowFacade transitions API. It replaces
 * the per-form hardcoded status <select> dropdowns so every artifact type shares
 * one lifecycle UI and one error-handling contract (REQ-161).
 *
 * States handled uniformly (REQ-160/161):
 *   - loading           → aria-busy badge while transitions are fetched/posted
 *   - error             → inline, role="alert" message (network / validation)
 *   - no transitions    → read-only badge (terminal state or `disabled`)
 *   - not initialized   → read-only badge + "workflow not initialized" hint when
 *                         the item has no WorkflowItemState / definition yet
 *   - change_reason     → inline required-reason input before the transition posts
 *
 * Accessibility:
 *   - role="status" on the badge; aria-busy during async work
 *   - trigger: aria-haspopup="menu" + aria-expanded; aria-label announces the move
 *   - keyboard: Enter/Space open, Arrow keys move, Escape closes; focus returns
 *     to the trigger after close/transition
 */

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import type { KeyboardEvent as ReactKeyboardEvent } from "react";
import { useTranslation } from "react-i18next";
import { ChevronDown, AlertCircle, Loader2 } from "lucide-react";
import {
  workflowTransitionsApi,
  type WorkflowArtifactType,
  type WorkflowAllowedTransition,
  type WorkflowTransitionsResponse,
} from "../../api/workflow-transitions";
import { extractErrorMessage } from "../../api/client";
import { getStatusBadgeStyle } from "../../utils/statusBadge";

export interface WorkflowStatusEditorProps {
  /** Artifact type — selects the backend transitions endpoint. */
  artifactType: WorkflowArtifactType;
  /** UUID of the artifact whose lifecycle is edited. */
  artifactId: string;
  /**
   * Current status mirror, used as the fallback label before transitions load.
   * Optional: artifacts without a status field (e.g. GlossaryTerm) pass
   * ``undefined`` and the control degrades to the workflow-driven state only.
   */
  currentStatus?: string;
  /** When true the control is read-only (badge only, no menu). */
  disabled?: boolean;
  /** Called with the new status after a successful transition. */
  onTransitionComplete?: (newStatus: string) => void;
  /** Optional wrapper className for layout composition. */
  className?: string;
}

/**
 * WorkflowStatusEditor — badge + accessible transitions dropdown (REQ-161).
 */
export function WorkflowStatusEditor({
  artifactType,
  artifactId,
  currentStatus,
  disabled = false,
  onTransitionComplete,
  className,
}: WorkflowStatusEditorProps): JSX.Element {
  const { t } = useTranslation();

  const [data, setData] = useState<WorkflowTransitionsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  // Transition awaiting a mandatory change reason before it can be posted.
  const [pendingReason, setPendingReason] =
    useState<WorkflowAllowedTransition | null>(null);
  const [reason, setReason] = useState("");

  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const menuRef = useRef<HTMLDivElement | null>(null);
  const reasonInputRef = useRef<HTMLTextAreaElement | null>(null);

  const allowed = useMemo(() => data?.allowed_transitions ?? [], [data]);
  const currentState = data?.current_state ?? currentStatus;
  // "not initialized": the item has neither a state nor a configured workflow.
  const notInitialized =
    data !== null &&
    data.current_state === null &&
    data.states.length === 0;
  const interactive = !disabled && allowed.length > 0;

  const loadTransitions = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await workflowTransitionsApi.getTransitions(
        artifactType,
        artifactId
      );
      setData(resp);
    } catch {
      // A missing endpoint / uninitialized workflow degrades to read-only —
      // surface nothing noisy, just fall back to the current status badge.
      setData({ current_state: null, states: [], allowed_transitions: [] });
    } finally {
      setLoading(false);
    }
  }, [artifactType, artifactId]);

  useEffect(() => {
    void loadTransitions();
  }, [loadTransitions]);

  // Close the menu on outside click.
  useEffect(() => {
    if (!menuOpen) return undefined;
    const onDown = (e: MouseEvent): void => {
      if (
        menuRef.current &&
        !menuRef.current.contains(e.target as Node) &&
        triggerRef.current &&
        !triggerRef.current.contains(e.target as Node)
      ) {
        setMenuOpen(false);
      }
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [menuOpen]);

  // Focus the reason input when a change-reason transition is pending.
  useEffect(() => {
    if (pendingReason) reasonInputRef.current?.focus();
  }, [pendingReason]);

  const closeMenu = useCallback((): void => {
    setMenuOpen(false);
    triggerRef.current?.focus();
  }, []);

  const runTransition = useCallback(
    async (tr: WorkflowAllowedTransition, changeReason: string): Promise<void> => {
      setBusy(true);
      setError(null);
      try {
        const result = await workflowTransitionsApi.transition(
          artifactType,
          artifactId,
          tr.target_state,
          changeReason
        );
        setPendingReason(null);
        setReason("");
        await loadTransitions();
        onTransitionComplete?.(result.new_state);
      } catch (err: unknown) {
        setError(extractErrorMessage(err));
      } finally {
        setBusy(false);
        triggerRef.current?.focus();
      }
    },
    [artifactType, artifactId, loadTransitions, onTransitionComplete]
  );

  const selectTransition = useCallback(
    (tr: WorkflowAllowedTransition): void => {
      setMenuOpen(false);
      if (tr.requires_change_reason) {
        // Defer the POST until the mandatory reason is supplied.
        setPendingReason(tr);
        return;
      }
      void runTransition(tr, "");
    },
    [runTransition]
  );

  const onTriggerKeyDown = useCallback(
    (e: ReactKeyboardEvent<HTMLButtonElement>): void => {
      if (e.key === "Enter" || e.key === " " || e.key === "ArrowDown") {
        e.preventDefault();
        setActiveIndex(0);
        setMenuOpen(true);
      }
    },
    []
  );

  const onMenuKeyDown = useCallback(
    (e: ReactKeyboardEvent<HTMLDivElement>): void => {
      if (e.key === "Escape") {
        e.preventDefault();
        closeMenu();
      } else if (e.key === "ArrowDown") {
        e.preventDefault();
        setActiveIndex((i) => (i + 1) % allowed.length);
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setActiveIndex((i) => (i - 1 + allowed.length) % allowed.length);
      } else if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        const tr = allowed[activeIndex];
        if (tr) selectTransition(tr);
      }
    },
    [allowed, activeIndex, selectTransition, closeMenu]
  );

  // --- Styles (token-based, theme-safe) ---
  const badgeStyle = {
    ...getStatusBadgeStyle(currentState || "draft"),
    display: "inline-flex",
    alignItems: "center",
    gap: "var(--space-1)",
    fontWeight: 600,
  } as const;

  const triggerStyle = {
    display: "inline-flex",
    alignItems: "center",
    gap: "var(--space-2)",
    padding: "var(--space-1) var(--space-3)",
    border: "1px solid var(--color-border)",
    borderRadius: "var(--radius-md)",
    background: "var(--color-surface-raised)",
    color: "var(--color-text)",
    fontSize: "var(--font-size-sm)",
    fontFamily: "var(--font-sans)",
    cursor: interactive ? "pointer" : "default",
    transition: "border-color var(--transition-fast), box-shadow var(--transition-fast)",
  } as const;

  return (
    <div
      className={className}
      data-testid="workflow-status-editor"
      style={{ display: "inline-flex", flexDirection: "column", gap: "var(--space-2)" }}
    >
      {/* Scoped keyframe for the loading spinner (no global `spin` exists). */}
      <style>{"@keyframes wf-spin{to{transform:rotate(360deg)}}"}</style>
      <div
        style={{ display: "flex", alignItems: "center", gap: "var(--space-2)", position: "relative" }}
      >
        {/* Current state badge */}
        <span
          role="status"
          aria-busy={loading || busy}
          data-testid="workflow-current-status"
          style={badgeStyle}
        >
          {(loading || busy) && (
            <Loader2
              size={12}
              aria-hidden="true"
              style={{ animation: "wf-spin 1s linear infinite" }}
            />
          )}
          {currentState || "—"}
        </span>

        {/* Transition trigger (only when interactive) */}
        {interactive && (
          <button
            type="button"
            ref={triggerRef}
            data-testid="workflow-transition-trigger"
            className="btn-secondary"
            onClick={() => {
              setActiveIndex(0);
              setMenuOpen((o) => !o);
            }}
            onKeyDown={onTriggerKeyDown}
            disabled={busy}
            aria-haspopup="menu"
            aria-expanded={menuOpen}
            aria-label={t("workflowEditor.changeStatusFrom", {
              from: currentState,
              defaultValue: `Change status (current: ${currentState})`,
            })}
            style={triggerStyle}
          >
            {t("workflowEditor.changeStatus", "Change status")}
            <ChevronDown size={14} aria-hidden="true" />
          </button>
        )}

        {/* Transitions menu */}
        {menuOpen && interactive && (
          <div
            ref={menuRef}
            role="menu"
            data-testid="workflow-transition-menu"
            tabIndex={-1}
            onKeyDown={onMenuKeyDown}
            style={{
              position: "absolute",
              top: "calc(100% + 4px)",
              left: 0,
              zIndex: 20,
              minWidth: "200px",
              padding: "var(--space-1)",
              background: "var(--color-surface-raised)",
              border: "1px solid var(--color-border)",
              borderRadius: "var(--radius-md)",
              boxShadow: "var(--shadow-card)",
            }}
          >
            {allowed.map((tr, idx) => (
              <button
                type="button"
                key={tr.target_state}
                role="menuitem"
                data-testid={`workflow-transition-option-${tr.target_state}`}
                onClick={() => selectTransition(tr)}
                onMouseEnter={() => setActiveIndex(idx)}
                aria-label={t("workflowEditor.transitionTo", {
                  from: currentState,
                  to: tr.target_state,
                  defaultValue: `Change status from ${currentState} to ${tr.target_state}`,
                })}
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  width: "100%",
                  padding: "var(--space-2) var(--space-3)",
                  border: "none",
                  borderRadius: "var(--radius-sm)",
                  background:
                    idx === activeIndex ? "var(--color-card-active-bg)" : "transparent",
                  color: "var(--color-text)",
                  fontSize: "var(--font-size-sm)",
                  fontFamily: "var(--font-sans)",
                  cursor: "pointer",
                  textAlign: "left",
                }}
              >
                <span>{`→ ${tr.target_state}`}</span>
                {tr.requires_change_reason && (
                  <span
                    aria-hidden="true"
                    title={t("workflowEditor.reasonRequired", "Reason required")}
                    style={{ color: "var(--color-text-muted)", fontSize: "var(--font-size-xs)" }}
                  >
                    *
                  </span>
                )}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Not-initialized hint (read-only) */}
      {notInitialized && !loading && (
        <span
          data-testid="workflow-not-initialized"
          style={{ fontSize: "var(--font-size-xs)", color: "var(--color-text-muted)" }}
        >
          {t("workflowEditor.notInitialized", "Workflow not initialized")}
        </span>
      )}

      {/* Read-only, no-moves hint for an initialized-but-terminal state */}
      {!interactive && !notInitialized && !loading && !disabled && (
        <span
          data-testid="workflow-no-transitions"
          style={{ fontSize: "var(--font-size-xs)", color: "var(--color-text-muted)" }}
        >
          {t("workflowEditor.noTransitions", "No transitions available")}
        </span>
      )}

      {/* Mandatory change-reason prompt before posting the transition */}
      {pendingReason && (
        <div
          data-testid="workflow-reason-prompt"
          style={{
            display: "flex",
            flexDirection: "column",
            gap: "var(--space-2)",
            padding: "var(--space-3)",
            border: "1px solid var(--color-border)",
            borderRadius: "var(--radius-md)",
            background: "var(--color-surface-raised)",
          }}
        >
          <label
            htmlFor="workflow-reason-input"
            style={{ fontSize: "var(--font-size-sm)", color: "var(--color-text)" }}
          >
            {t("workflowEditor.reasonFor", {
              to: pendingReason.target_state,
              defaultValue: `Reason for → ${pendingReason.target_state}`,
            })}
          </label>
          <textarea
            id="workflow-reason-input"
            ref={reasonInputRef}
            data-testid="workflow-reason-input"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            rows={2}
            style={{
              width: "100%",
              border: "1px solid var(--color-border)",
              borderRadius: "var(--radius-md)",
              padding: "var(--space-2)",
              fontFamily: "var(--font-sans)",
              fontSize: "var(--font-size-sm)",
              color: "var(--color-text)",
              background: "var(--color-surface)",
              resize: "vertical",
              boxSizing: "border-box",
            }}
          />
          <div style={{ display: "flex", gap: "var(--space-2)" }}>
            <button
              type="button"
              data-testid="workflow-reason-confirm"
              className="btn-primary"
              disabled={busy || !reason.trim()}
              onClick={() => void runTransition(pendingReason, reason.trim())}
            >
              {t("workflowEditor.confirm", "Confirm")}
            </button>
            <button
              type="button"
              data-testid="workflow-reason-cancel"
              className="btn-secondary"
              disabled={busy}
              onClick={() => {
                setPendingReason(null);
                setReason("");
                triggerRef.current?.focus();
              }}
            >
              {t("actions.cancel", "Cancel")}
            </button>
          </div>
        </div>
      )}

      {/* Error state */}
      {error && (
        <span
          role="alert"
          data-testid="workflow-error"
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: "var(--space-1)",
            fontSize: "var(--font-size-xs)",
            color: "var(--color-danger)",
          }}
        >
          <AlertCircle size={12} aria-hidden="true" />
          {error}
        </span>
      )}
    </div>
  );
}

WorkflowStatusEditor.displayName = "WorkflowStatusEditor";
