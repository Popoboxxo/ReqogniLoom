/**
 * ARCH-L1-001 ReactFrontend — Risk list view (COMP-RF-003).
 *
 * leaf_id: COMP-RF-003
 * req_id:  REQ-L1-029 (ADR/Risk/Issue REST API)
 *
 * Lists all Risks for the active workspace and provides a create form.
 */

import React, { useState, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { useWorkspace } from "../../context/WorkspaceContext";
import { risksApi } from "../../api/risks";
import type { Risk, RiskImpact, RiskProbability, RiskSeverity } from "../../types";

const SEVERITY_OPTIONS: RiskSeverity[] = ["low", "medium", "high"];
const PROBABILITY_OPTIONS: RiskProbability[] = ["low", "medium", "high"];
const IMPACT_OPTIONS: RiskImpact[] = ["low", "medium", "high"];

const inputStyle: React.CSSProperties = {
  width: "100%",
  padding: "var(--space-2) var(--space-3)",
  borderRadius: "var(--radius-md)",
  border: "1px solid var(--color-border)",
  fontSize: "var(--font-size-sm)",
  background: "var(--color-surface)",
  color: "var(--color-text)",
  fontFamily: "var(--font-sans)",
  boxSizing: "border-box",
};

const labelStyle: React.CSSProperties = {
  fontWeight: 600,
  fontSize: "var(--font-size-sm)",
  color: "var(--color-text)",
  display: "block",
  marginBottom: "var(--space-1)",
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
    <div>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginTop: 0,
          marginBottom: "var(--space-6)",
        }}
      >
        <h2
          style={{
            fontSize: "var(--font-size-2xl)",
            fontWeight: 700,
            color: "var(--color-text)",
            margin: 0,
          }}
        >
          {t("nav.risks")}
        </h2>
        <button
          type="button"
          data-testid="risk-create-btn"
          onClick={() => {
            if (showCreate) {
              resetForm();
              setShowCreate(false);
            } else {
              setShowCreate(true);
            }
          }}
          style={primaryButtonStyle}
        >
          {showCreate ? t("actions.cancel") : `+ ${t("actions.new", "New Risk")}`}
        </button>
      </div>

      {showCreate && (
        <form
          data-testid="risk-create-form"
          onSubmit={(e) => void handleSubmit(e)}
          style={{
            display: "flex",
            flexDirection: "column",
            gap: "var(--space-3)",
            padding: "var(--space-4)",
            marginBottom: "var(--space-4)",
            background: "var(--color-surface-raised)",
            border: "1px solid var(--color-border)",
            borderRadius: "var(--radius-lg)",
          }}
        >
          <div>
            <label htmlFor="risk-title" style={labelStyle}>
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
              style={inputStyle}
            />
          </div>
          <div>
            <label htmlFor="risk-description" style={labelStyle}>
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
              style={{ ...inputStyle, fontFamily: "inherit", resize: "vertical" }}
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
              <label htmlFor="risk-severity" style={labelStyle}>
                Severity
              </label>
              <select
                id="risk-severity"
                data-testid="risk-severity-select"
                value={severity}
                onChange={(e) => setSeverity(e.target.value as RiskSeverity)}
                disabled={isSubmitting}
                style={inputStyle}
              >
                {SEVERITY_OPTIONS.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor="risk-probability" style={labelStyle}>
                Probability
              </label>
              <select
                id="risk-probability"
                data-testid="risk-probability-select"
                value={probability}
                onChange={(e) => setProbability(e.target.value as RiskProbability)}
                disabled={isSubmitting}
                style={inputStyle}
              >
                {PROBABILITY_OPTIONS.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor="risk-impact" style={labelStyle}>
                Impact
              </label>
              <select
                id="risk-impact"
                data-testid="risk-impact-select"
                value={impact}
                onChange={(e) => setImpact(e.target.value as RiskImpact)}
                disabled={isSubmitting}
                style={inputStyle}
              >
                {IMPACT_OPTIONS.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
            </div>
          </div>
          {formError && (
            <p
              role="alert"
              style={{
                color: "var(--color-danger)",
                fontSize: "var(--font-size-sm)",
                margin: 0,
              }}
            >
              {formError}
            </p>
          )}
          <div style={{ display: "flex", gap: "var(--space-2)", justifyContent: "flex-end" }}>
            <button
              type="button"
              data-testid="risk-cancel-btn"
              onClick={() => {
                resetForm();
                setShowCreate(false);
              }}
              disabled={isSubmitting}
              style={{
                background: "var(--color-surface)",
                color: "var(--color-text)",
                border: "1px solid var(--color-border)",
                borderRadius: "var(--radius-md)",
                padding: "var(--space-2) var(--space-4)",
                fontSize: "var(--font-size-sm)",
                fontWeight: 600,
                cursor: isSubmitting ? "not-allowed" : "pointer",
              }}
            >
              {t("actions.cancel")}
            </button>
            <button
              type="submit"
              data-testid="risk-save-btn"
              disabled={isSubmitting}
              style={{
                ...primaryButtonStyle,
                opacity: isSubmitting ? 0.6 : 1,
                cursor: isSubmitting ? "not-allowed" : "pointer",
              }}
            >
              {isSubmitting ? t("actions.saving") : t("actions.save")}
            </button>
          </div>
        </form>
      )}

      {items.length === 0 ? (
        <p
          style={{
            fontSize: "var(--font-size-base)",
            color: "var(--color-text-muted)",
            padding: "var(--space-6)",
            background: "var(--color-surface-raised)",
            borderRadius: "var(--radius-lg)",
            border: "1px dashed var(--color-border)",
          }}
        >
          {t("editor.empty")}
        </p>
      ) : (
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
    </div>
  );
}
