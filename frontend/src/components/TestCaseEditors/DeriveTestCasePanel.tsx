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
 *
 * Issue #1091 — the panel rendered seven unstyled browser-default buttons
 * ("Entfernen" ×4, "Schritt hinzufügen", "Testfall anlegen", "Verwerfen") and
 * nested a second card inside the shared <Dialog>'s own card. Three changes:
 *   - every control now carries a global `.btn-*` class (#954 convention);
 *   - the per-row "Entfernen" is an icon-only control at the RIGHT EDGE OF
 *     ITS OWN STEP ROW with a unique accessible name ("Schritt 1 entfernen"),
 *     so four of them can no longer collapse into one ambiguous button row —
 *     and, unlike the old text button, it no longer steals ~90px from the two
 *     step inputs, which is what actually made four steps unreadable;
 *   - the outer card is gone (see `.panel`), because the dialog panel is
 *     already the card; keeping a second background/border/radius inside it
 *     is what pushed the action row against the dialog edge.
 */
import { useCallback, useState } from "react";
import { useTranslation } from "react-i18next";
import { Plus, Trash2 } from "lucide-react";

import { extractErrorMessage } from "../../api/client";
import { requirementsApi } from "../../api/requirements";
import { testcasesApi } from "../../api/testcases";
import type { TestCase, TestCaseStep } from "../../api/testcases";
import { AiActionIcon } from "../shared/AiActions";
import styles from "./DeriveTestCasePanel.module.css";

export interface DeriveTestCasePanelProps {
  workspaceId: string;
  requirement: { id: string; title: string };
  /** Called after the draft was successfully persisted. */
  onCreated?: (testCase: TestCase) => void;
}

type Phase = "idle" | "generating" | "review" | "creating" | "done";

interface DraftState {
  title: string;
  description: string;
  steps: TestCaseStep[];
}

export function DeriveTestCasePanel({
  workspaceId,
  requirement,
  onCreated,
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
        // #424 (spec section 4.6): this path persists LLM output, so it must
        // declare its provenance explicitly. `reviewed` is read-only on the
        // serializer and is derived server-side from `origin` (false here).
        origin: "ai_generated",
        scenario_kind: "nominal",
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
    <section className={styles.panel} data-testid="derive-testcase-panel">
      {error && (
        <div className={styles.error} role="alert" data-testid="derive-testcase-error">
          {error}
        </div>
      )}

      {/* #424: the persisted row is AI-generated and unreviewed. State that
          plainly wherever a draft or a result is on screen, so the human
          review step is discoverable (reviewed only via the TestCase editor). */}
      {(draft || created) && (
        <p className={styles.notice} data-testid="derive-testcase-ai-notice">
          {t("deriveTestcase.aiNotice")}
        </p>
      )}

      {phase === "idle" && (
        <div className={styles.actions}>
          <button
            type="button"
            className="btn-primary"
            onClick={handleGenerate}
            disabled={busy}
            data-testid="derive-testcase-generate"
          >
            <AiActionIcon />
            {t("deriveTestcase.generate")}
          </button>
        </div>
      )}

      {phase === "generating" && (
        <p className={styles.muted} data-testid="derive-testcase-generating">
          {t("deriveTestcase.generating")}
        </p>
      )}

      {draft && (phase === "review" || phase === "creating") && (
        <div data-testid="derive-testcase-draft">
          <label className={styles.field}>
            <span className={styles.muted}>{t("deriveTestcase.fieldTitle")}</span>
            <input
              type="text"
              value={draft.title}
              disabled={busy}
              onChange={(e) => updateDraft({ title: e.target.value })}
              className={styles.input}
              data-testid="derive-testcase-title-input"
            />
          </label>
          <label className={styles.field}>
            <span className={styles.muted}>{t("deriveTestcase.fieldDescription")}</span>
            <textarea
              value={draft.description}
              disabled={busy}
              onChange={(e) => updateDraft({ description: e.target.value })}
              className={styles.textarea}
              data-testid="derive-testcase-description-input"
            />
          </label>

          <div className={styles.field}>
            <span className={styles.muted}>{t("deriveTestcase.fieldSteps")}</span>
            {draft.steps.map((s, i) => (
              <div key={i} className={styles.stepRow} data-testid={`derive-testcase-step-${i}`}>
                <input
                  type="text"
                  value={s.step}
                  disabled={busy}
                  placeholder={t("deriveTestcase.stepPlaceholder")}
                  onChange={(e) => updateStep(i, { step: e.target.value })}
                  className={styles.stepInput}
                  data-testid={`derive-testcase-step-action-${i}`}
                />
                <input
                  type="text"
                  value={s.expected_result}
                  disabled={busy}
                  placeholder={t("deriveTestcase.expectedResultPlaceholder")}
                  onChange={(e) => updateStep(i, { expected_result: e.target.value })}
                  className={styles.stepInput}
                  data-testid={`derive-testcase-step-expected-${i}`}
                />
                <button
                  type="button"
                  // #1091: destructive but per-row, so it stays out of the
                  // primary action hierarchy. Icon-only with a per-row
                  // accessible name — four identical "Entfernen" buttons in
                  // one row were ambiguous for a screen-reader user, and a
                  // tooltip alone is not an accessible name.
                  className={`btn-ghost ${styles.stepRemove}`}
                  onClick={() => removeStep(i)}
                  disabled={busy}
                  data-testid={`derive-testcase-step-remove-${i}`}
                  aria-label={t("deriveTestcase.removeStep", { index: i + 1 })}
                  title={t("deriveTestcase.removeStep", { index: i + 1 })}
                >
                  <Trash2 aria-hidden="true" size={16} />
                </button>
              </div>
            ))}
            <button
              type="button"
              className="btn-secondary btn-sm"
              onClick={addStep}
              disabled={busy}
              data-testid="derive-testcase-add-step"
            >
              <Plus aria-hidden="true" size={16} />
              {t("deriveTestcase.addStep")}
            </button>
          </div>

          <div className={styles.actions}>
            <button
              type="button"
              className="btn-primary"
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
              className="btn-secondary"
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
        <div className={styles.success} data-testid="derive-testcase-result">
          {t("deriveTestcase.created", { title: created.title })}
        </div>
      )}
    </section>
  );
}
