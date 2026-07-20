/**
 * ARCH-L1-001 ReactFrontend — Derive TestCase Panel (SysEng 2.0 N5).
 *
 * UMSETZUNGSPLAN_SYSENG_2.0.md §3.2 + §4 Phase 4a ("KI-Copilot",
 * `test.derive_from_requirement`). Human-in-the-loop copilot, scoped down
 * from the N1 diff-style review (single TestCase, not a tree) to a simple
 * pre-filled, editable form:
 *
 *   1. "Generate" asks the backend to propose a TestCase draft (title,
 *      description, steps) for the given Requirement. Nothing is persisted —
 *      the draft lives in this component's state until confirmed.
 *   2. The draft is shown as an editable form so the user can correct the
 *      title/description/steps before creating anything.
 *   3. "Create" persists the (possibly edited) draft via the existing,
 *      already-validated TestCase creation path (testcasesApi.create) and
 *      auto-links it to the source requirement via a 'verifies' TraceLink.
 *
 * data-testid is set on every interactive element (E2E convention).
 */
import type { CSSProperties } from "react";
import { useCallback, useState } from "react";
import { useTranslation } from "react-i18next";

import { extractErrorMessage } from "../../api/client";
import { requirementsApi } from "../../api/requirements";
import { testcasesApi } from "../../api/testcases";
import type { TestCase, TestCaseStep } from "../../api/testcases";

export interface DeriveTestCasePanelProps {
  workspaceId: string;
  requirement: { id: string; title: string };
  /** Called after the draft was successfully persisted. */
  onCreated?: (testCase: TestCase) => void;
  /** Called when the user closes the panel. */
  onClose?: () => void;
}

type Phase = "idle" | "generating" | "review" | "creating" | "done";

interface DraftState {
  title: string;
  description: string;
  steps: TestCaseStep[];
}

const styles: Record<string, CSSProperties> = {
  panel: {
    display: "flex",
    flexDirection: "column",
    gap: "var(--space-4)",
    padding: "var(--space-5)",
    background: "var(--color-surface)",
    border: "1px solid var(--color-border)",
    borderRadius: "var(--radius-lg)",
    color: "var(--color-text)",
  },
  header: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    gap: "var(--space-3)",
  },
  field: { display: "flex", flexDirection: "column", gap: "var(--space-1)" },
  input: {
    padding: "var(--space-2) var(--space-3)",
    border: "1px solid var(--color-border)",
    borderRadius: "var(--radius-sm)",
    background: "var(--color-surface-raised)",
    color: "var(--color-text)",
  },
  textarea: {
    padding: "var(--space-2) var(--space-3)",
    border: "1px solid var(--color-border)",
    borderRadius: "var(--radius-sm)",
    background: "var(--color-surface-raised)",
    color: "var(--color-text)",
    minHeight: "5rem",
    resize: "vertical",
  },
  stepRow: {
    display: "flex",
    gap: "var(--space-2)",
    alignItems: "flex-start",
  },
  error: {
    background: "var(--color-badge-danger-bg)",
    color: "var(--color-badge-danger-text)",
    borderRadius: "var(--radius-sm)",
    padding: "var(--space-2) var(--space-3)",
  },
  success: {
    background: "var(--color-badge-success-bg)",
    color: "var(--color-badge-success-text)",
    borderRadius: "var(--radius-sm)",
    padding: "var(--space-3)",
  },
  actions: { display: "flex", gap: "var(--space-3)", flexWrap: "wrap" },
  muted: { color: "var(--color-text-muted)", fontSize: "var(--font-size-sm)" },
};

export function DeriveTestCasePanel({
  workspaceId,
  requirement,
  onCreated,
  onClose,
}: DeriveTestCasePanelProps): JSX.Element {
  const { t } = useTranslation();

  const [phase, setPhase] = useState<Phase>("idle");
  const [draft, setDraft] = useState<DraftState | null>(null);
  const [created, setCreated] = useState<TestCase | null>(null);
  const [error, setError] = useState<string | null>(null);

  const busy = phase === "generating" || phase === "creating";

  const handleGenerate = useCallback(async () => {
    setError(null);
    setCreated(null);
    setPhase("generating");
    try {
      const result = await requirementsApi.aiDeriveTestcase(requirement.id);
      setDraft({
        title: result.draft.title,
        description: result.draft.description,
        steps: result.draft.steps ?? [],
      });
      setPhase("review");
    } catch (err) {
      setError(extractErrorMessage(err));
      setPhase("idle");
    }
  }, [requirement.id]);

  const handleCreate = useCallback(async () => {
    if (!draft) return;
    setError(null);
    setPhase("creating");
    try {
      const testCase = await testcasesApi.create({
        workspace_id: workspaceId,
        title: draft.title,
        description: draft.description,
        steps: draft.steps,
        linked_requirement_id: requirement.id,
      });
      setCreated(testCase);
      setDraft(null);
      setPhase("done");
      onCreated?.(testCase);
    } catch (err) {
      setError(extractErrorMessage(err));
      setPhase("review");
    }
  }, [draft, workspaceId, requirement.id, onCreated]);

  const handleDiscard = useCallback(() => {
    setDraft(null);
    setError(null);
    setPhase("idle");
  }, []);

  const updateDraft = useCallback((patch: Partial<DraftState>) => {
    setDraft((prev) => (prev ? { ...prev, ...patch } : prev));
  }, []);

  const updateStep = useCallback(
    (index: number, patch: Partial<TestCaseStep>) => {
      setDraft((prev) => {
        if (!prev) return prev;
        const steps = prev.steps.map((s, i) =>
          i === index ? { ...s, ...patch } : s
        );
        return { ...prev, steps };
      });
    },
    []
  );

  const addStep = useCallback(() => {
    setDraft((prev) =>
      prev
        ? { ...prev, steps: [...prev.steps, { step: "", expected_result: "" }] }
        : prev
    );
  }, []);

  const removeStep = useCallback((index: number) => {
    setDraft((prev) =>
      prev ? { ...prev, steps: prev.steps.filter((_, i) => i !== index) } : prev
    );
  }, []);

  return (
    <section style={styles.panel} data-testid="derive-testcase-panel">
      <header style={styles.header}>
        <div>
          <strong>{t("deriveTestcase.title")}</strong>
          <div style={styles.muted} data-testid="derive-testcase-req-title">
            {requirement.title}
          </div>
        </div>
        {onClose && (
          <button
            type="button"
            onClick={onClose}
            data-testid="derive-testcase-close"
          >
            {t("deriveTestcase.close")}
          </button>
        )}
      </header>

      {error && (
        <div style={styles.error} role="alert" data-testid="derive-testcase-error">
          {error}
        </div>
      )}

      {phase === "idle" && (
        <div style={styles.actions}>
          <button
            type="button"
            onClick={handleGenerate}
            disabled={busy}
            data-testid="derive-testcase-generate"
          >
            {t("deriveTestcase.generate")}
          </button>
        </div>
      )}

      {phase === "generating" && (
        <p style={styles.muted} data-testid="derive-testcase-generating">
          {t("deriveTestcase.generating")}
        </p>
      )}

      {draft && (phase === "review" || phase === "creating") && (
        <div data-testid="derive-testcase-draft">
          <label style={styles.field}>
            <span style={styles.muted}>{t("deriveTestcase.fieldTitle")}</span>
            <input
              type="text"
              value={draft.title}
              disabled={busy}
              onChange={(e) => updateDraft({ title: e.target.value })}
              style={styles.input}
              data-testid="derive-testcase-title-input"
            />
          </label>
          <label style={styles.field}>
            <span style={styles.muted}>{t("deriveTestcase.fieldDescription")}</span>
            <textarea
              value={draft.description}
              disabled={busy}
              onChange={(e) => updateDraft({ description: e.target.value })}
              style={styles.textarea}
              data-testid="derive-testcase-description-input"
            />
          </label>

          <div style={styles.field}>
            <span style={styles.muted}>{t("deriveTestcase.fieldSteps")}</span>
            {draft.steps.map((s, i) => (
              <div key={i} style={styles.stepRow} data-testid={`derive-testcase-step-${i}`}>
                <input
                  type="text"
                  value={s.step}
                  disabled={busy}
                  placeholder={t("deriveTestcase.stepPlaceholder")}
                  onChange={(e) => updateStep(i, { step: e.target.value })}
                  style={{ ...styles.input, flex: 1 }}
                  data-testid={`derive-testcase-step-action-${i}`}
                />
                <input
                  type="text"
                  value={s.expected_result}
                  disabled={busy}
                  placeholder={t("deriveTestcase.expectedResultPlaceholder")}
                  onChange={(e) => updateStep(i, { expected_result: e.target.value })}
                  style={{ ...styles.input, flex: 1 }}
                  data-testid={`derive-testcase-step-expected-${i}`}
                />
                <button
                  type="button"
                  onClick={() => removeStep(i)}
                  disabled={busy}
                  data-testid={`derive-testcase-step-remove-${i}`}
                >
                  {t("deriveTestcase.removeStep")}
                </button>
              </div>
            ))}
            <button
              type="button"
              onClick={addStep}
              disabled={busy}
              data-testid="derive-testcase-add-step"
            >
              {t("deriveTestcase.addStep")}
            </button>
          </div>

          <div style={styles.actions}>
            <button
              type="button"
              onClick={handleCreate}
              disabled={busy || !draft.title.trim()}
              data-testid="derive-testcase-create"
            >
              {phase === "creating"
                ? t("deriveTestcase.creating")
                : t("deriveTestcase.create")}
            </button>
            <button
              type="button"
              onClick={handleDiscard}
              disabled={busy}
              data-testid="derive-testcase-discard"
            >
              {t("deriveTestcase.discard")}
            </button>
          </div>
        </div>
      )}

      {created && (
        <div style={styles.success} data-testid="derive-testcase-result">
          {t("deriveTestcase.created", { title: created.title })}
        </div>
      )}
    </section>
  );
}
