/**
 * ARCH-L1-001 ReactFrontend — Risk list view (COMP-RF-003).
 *
 * leaf_id: COMP-RF-003
 * req_id:  REQ-L1-029 (ADR/Risk/Issue REST API)
 *
 * Lists all Risks for the active workspace and provides a create form.
 * Uses unified ModalDialogBase for form pattern (REQ-L1-040).
 */

import React, { useState, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { useWorkspace } from "../../context/WorkspaceContext";
import { risksApi } from "../../api/risks";
import ModalDialogBase, { SHARED_STYLES } from "../RequirementsList/ModalDialogBase";
import type { Risk, RiskImpact, RiskProbability, RiskSeverity } from "../../types";

const SEVERITY_OPTIONS: RiskSeverity[] = ["low", "medium", "high"];
const PROBABILITY_OPTIONS: RiskProbability[] = ["low", "medium", "high"];
const IMPACT_OPTIONS: RiskImpact[] = ["low", "medium", "high"];

export default function RiskList(): JSX.Element {
  const { t } = useTranslation();
  const { activeWorkspace } = useWorkspace();
  const [items, setItems] = useState<Risk[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [severity, setSeverity] = useState<RiskSeverity>("medium");
  const [probability, setProbability] = useState<RiskProbability>("medium");
  const [impact, setImpact] = useState<RiskImpact>("medium");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const loadList = async (): Promise<void> => {
    if (!activeWorkspace) return;
    setIsLoading(true);
    try {
      const resp = await risksApi.list(activeWorkspace.id);
      setItems(resp.results);
    } catch (err) {
      console.error(err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    void loadList();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeWorkspace]);

  const resetForm = (): void => {
    setTitle("");
    setDescription("");
    setSeverity("medium");
    setProbability("medium");
    setImpact("medium");
    setFormError(null);
  };

  const handleSubmit = async (
    e: React.FormEvent<HTMLFormElement>
  ): Promise<void> => {
    e.preventDefault();
    if (!activeWorkspace) return;
    if (!title.trim()) {
      setFormError("Title is required");
      return;
    }
    setIsSubmitting(true);
    setFormError(null);
    try {
      await risksApi.create({
        workspace_id: activeWorkspace.id,
        title: title.trim(),
        description: description.trim() || undefined,
        severity,
        probability,
        impact,
      });
      resetForm();
      setShowCreate(false);
      await loadList();
    } catch (err: unknown) {
      const msg =
        (err as { error?: { message?: string } })?.error?.message ??
        String(err);
      setFormError(msg);
    } finally {
      setIsSubmitting(false);
    }
  };

  if (isLoading) return <p>{t("loading")}</p>;

  return (
    <>
      <ModalDialogBase
        title={t("nav.risks")}
        isOpen={showCreate}
        onToggle={() => {
          if (showCreate) {
            resetForm();
            setShowCreate(false);
          } else {
            setShowCreate(true);
          }
        }}
        onSubmit={handleSubmit}
        onCancel={() => {
          resetForm();
          setShowCreate(false);
        }}
        error={formError}
        isSubmitting={isSubmitting}
        itemCount={items.length}
        testIdPrefix="risk"
        buttonTestIdPrefix="risk"
      >
        <div>
          <label htmlFor="risk-title" style={SHARED_STYLES.label}>
            {t("editor.title", "Title")} *
          </label>
          <input
            id="risk-title"
            data-testid="risk-title-input"
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            required
            autoFocus
            disabled={isSubmitting}
            placeholder="Risk title"
            style={SHARED_STYLES.input}
          />
        </div>
        <div>
          <label htmlFor="risk-description" style={SHARED_STYLES.label}>
            {t("editor.description", "Description")}
          </label>
          <textarea
            id="risk-description"
            data-testid="risk-description-input"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            disabled={isSubmitting}
            rows={3}
            placeholder="Describe the risk..."
            style={{ ...SHARED_STYLES.input, fontFamily: "inherit", resize: "vertical" }}
          />
        </div>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "1fr 1fr 1fr",
            gap: "var(--space-3)",
          }}
        >
          <div>
            <label htmlFor="risk-severity" style={SHARED_STYLES.label}>
              Severity
            </label>
            <select
              id="risk-severity"
              data-testid="risk-severity-select"
              value={severity}
              onChange={(e) => setSeverity(e.target.value as RiskSeverity)}
              disabled={isSubmitting}
              style={SHARED_STYLES.input}
            >
              {SEVERITY_OPTIONS.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor="risk-probability" style={SHARED_STYLES.label}>
              Probability
            </label>
            <select
              id="risk-probability"
              data-testid="risk-probability-select"
              value={probability}
              onChange={(e) => setProbability(e.target.value as RiskProbability)}
              disabled={isSubmitting}
              style={SHARED_STYLES.input}
            >
              {PROBABILITY_OPTIONS.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor="risk-impact" style={SHARED_STYLES.label}>
              Impact
            </label>
            <select
              id="risk-impact"
              data-testid="risk-impact-select"
              value={impact}
              onChange={(e) => setImpact(e.target.value as RiskImpact)}
              disabled={isSubmitting}
              style={SHARED_STYLES.input}
            >
              {IMPACT_OPTIONS.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </div>
        </div>
      </ModalDialogBase>

      {/* Item list (rendered outside modal) */}
      {items.length > 0 && (
        <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
          {items.map((item) => (
            <li
              key={item.id}
              data-testid={`risk-item-${item.id}`}
              style={{
                padding: "var(--space-3) var(--space-4)",
                marginBottom: "var(--space-2)",
                background: "var(--color-surface)",
                borderRadius: "var(--radius-md)",
                border: "1px solid var(--color-border)",
              }}
            >
              <strong>{item.title}</strong>{" "}
              <span
                style={{
                  color: "var(--color-text-muted)",
                  fontSize: "var(--font-size-sm)",
                }}
              >
                — {item.severity} | prob {item.probability} | impact {item.impact} | {item.status}
              </span>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
