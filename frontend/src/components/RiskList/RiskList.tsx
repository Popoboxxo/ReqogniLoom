/**
 * ARCH-L1-001 ReactFrontend — Risk list view (COMP-RF-003).
 *
 * leaf_id: COMP-RF-003
 * req_id:  REQ-L1-029 (ADR/Risk/Issue REST API),
 *          REQ-002 (Masken-Standardisierung auf Split-View-Layout)
 *
 * Split-View layout with resizable divider:
 * - Left panel: Risk list with create button
 * - Divider: 4px resizable
 * - Right panel: Risk detail editor
 */

import { useState, useEffect, useRef, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useWorkspace } from "../../context/WorkspaceContext";
import { risksApi } from "../../api/risks";
import type { Risk, RiskImpact, RiskProbability, RiskSeverity, RiskStatus, RiskCategory } from "../../types";

const SEVERITY_OPTIONS: RiskSeverity[] = ["low", "medium", "high"];
const PROBABILITY_OPTIONS: RiskProbability[] = ["low", "medium", "high"];
const IMPACT_OPTIONS: RiskImpact[] = ["low", "medium", "high"];
const STATUS_OPTIONS: RiskStatus[] = ["Identified", "Monitored", "Mitigated", "Accepted", "Closed"];
const CATEGORY_OPTIONS: RiskCategory[] = ["technical", "operational", "organizational", "business"];

const inputStyle: React.CSSProperties = {
  width: "100%",
  fontSize: "var(--font-size-base)",
  padding: "var(--space-2) var(--space-3)",
  marginBottom: "var(--space-4)",
  boxSizing: "border-box",
  background: "var(--color-surface)",
  border: "1px solid var(--color-border)",
  borderRadius: "var(--radius-md)",
  color: "var(--color-text)",
  fontFamily: "var(--font-sans)",
};

const labelStyle: React.CSSProperties = {
  fontWeight: 600,
  display: "block",
  marginBottom: "var(--space-2)",
  color: "var(--color-text)",
  fontSize: "var(--font-size-sm)",
};

const primaryButtonStyle: React.CSSProperties = {
  background: "var(--color-primary)",
  color: "#ffffff",
  border: "none",
  borderRadius: "var(--radius-md)",
  padding: "var(--space-2) var(--space-4)",
  fontSize: "var(--font-size-sm)",
  fontWeight: 600,
  cursor: "pointer",
  transition: "var(--transition-fast)",
  fontFamily: "var(--font-sans)",
};

// ---------------------------------------------------------------------------
// RiskDetailEditor — right panel content
// ---------------------------------------------------------------------------

interface RiskDetailEditorProps {
  risk: Risk;
  onSaved: () => void;
}

function RiskDetailEditor({ risk, onSaved }: RiskDetailEditorProps): JSX.Element {
  const { t } = useTranslation();
  const [title, setTitle] = useState(risk.title);
  const [description, setDescription] = useState(risk.description ?? "");
  const [severity, setSeverity] = useState<RiskSeverity>(risk.severity ?? "medium");
  const [probability, setProbability] = useState<RiskProbability>(risk.probability ?? "medium");
  const [impact, setImpact] = useState<RiskImpact>(risk.impact ?? "medium");
  const [status, setStatus] = useState(risk.status ?? "Identified");
  const [category, setCategory] = useState(risk.category ?? "technical");
  const [owner, setOwner] = useState(risk.owner ?? "");
  const [mitigationStrategy, setMitigationStrategy] = useState(risk.mitigation_strategy ?? "");
  const [isSaving, setIsSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const handleSave = useCallback(async (): Promise<void> => {
    setIsSaving(true);
    setSaveError(null);
    try {
      await risksApi.update(risk.id, {
        title: title.trim(),
        description: description.trim() || undefined,
        severity,
        probability,
        impact,
        status,
        category,
        owner: owner.trim(),
        mitigation_strategy: mitigationStrategy.trim(),
      });
      onSaved();
    } catch (err: unknown) {
      const msg =
        (err as { error?: { message?: string } })?.error?.message ?? String(err);
      setSaveError(msg);
    } finally {
      setIsSaving(false);
    }
  }, [risk.id, title, description, severity, probability, impact, status, category, owner, mitigationStrategy, onSaved]);

  const handleDelete = useCallback(async (): Promise<void> => {
    if (!window.confirm(t("editor.deleteConfirm"))) return;
    try {
      await risksApi.delete(risk.id);
      onSaved();
    } catch (err: unknown) {
      console.error("Delete failed:", err);
    }
  }, [risk.id, t, onSaved]);

  return (
    <div style={{ padding: "var(--space-6)", overflow: "auto" }}>
      <h2 style={{ fontSize: "var(--font-size-xl)", fontWeight: 700, marginBottom: "var(--space-4)" }}>
        {risk.title || t("editor.untitled")}
      </h2>

      <div>
        <label htmlFor="risk-title" style={labelStyle}>
          {t("editor.title")} *
        </label>
        <input
          id="risk-title"
          data-testid="risk-title-input"
          type="text"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          disabled={isSaving}
          style={inputStyle}
        />
      </div>

      <div>
        <label htmlFor="risk-description" style={labelStyle}>
          {t("editor.description")}
        </label>
        <textarea
          id="risk-description"
          data-testid="risk-description-input"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          disabled={isSaving}
          rows={4}
          style={{ ...inputStyle, fontFamily: "inherit", resize: "vertical" }}
        />
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr 1fr",
          gap: "var(--space-3)",
          marginBottom: "var(--space-4)",
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
            disabled={isSaving}
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
            disabled={isSaving}
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
            disabled={isSaving}
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
      
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: "var(--space-3)",
          marginBottom: "var(--space-4)",
        }}
      >
        <div>
          <label htmlFor="risk-status" style={labelStyle}>
            Status
          </label>
          <select
            id="risk-status"
            data-testid="risk-status-select"
            value={status}
            onChange={(e) => setStatus(e.target.value as any)}
            disabled={isSaving}
            style={inputStyle}
          >
            {STATUS_OPTIONS.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="risk-category" style={labelStyle}>
            Category
          </label>
          <select
            id="risk-category"
            data-testid="risk-category-select"
            value={category}
            onChange={(e) => setCategory(e.target.value as any)}
            disabled={isSaving}
            style={inputStyle}
          >
            {CATEGORY_OPTIONS.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div>
        <label htmlFor="risk-owner" style={labelStyle}>
          Owner
        </label>
        <input
          id="risk-owner"
          data-testid="risk-owner-input"
          type="text"
          value={owner}
          onChange={(e) => setOwner(e.target.value)}
          disabled={isSaving}
          style={inputStyle}
        />
      </div>

      <div>
        <label htmlFor="risk-mitigation" style={labelStyle}>
          Mitigation Strategy
        </label>
        <textarea
          id="risk-mitigation"
          data-testid="risk-mitigation-input"
          value={mitigationStrategy}
          onChange={(e) => setMitigationStrategy(e.target.value)}
          disabled={isSaving}
          rows={3}
          style={{ ...inputStyle, fontFamily: "inherit", resize: "vertical" }}
        />
      </div>

      {saveError && (
        <p style={{ color: "var(--color-danger)", marginBottom: "var(--space-3)" }}>
          {saveError}
        </p>
      )}

      <div style={{ display: "flex", gap: "var(--space-2)" }}>
        <button
          data-testid="risk-save-btn"
          onClick={() => void handleSave()}
          disabled={isSaving}
          style={primaryButtonStyle}
        >
          {isSaving ? t("actions.saving") : t("actions.save")}
        </button>
        <button
          data-testid="risk-delete-btn"
          onClick={() => void handleDelete()}
          style={{
            background: "var(--color-danger)",
            color: "#ffffff",
            border: "none",
            borderRadius: "var(--radius-md)",
            padding: "var(--space-2) var(--space-4)",
            fontSize: "var(--font-size-sm)",
            fontWeight: 600,
            cursor: "pointer",
            transition: "var(--transition-fast)",
            fontFamily: "var(--font-sans)",
          }}
        >
          {t("actions.delete")}
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// RiskList — main view with split-pane
// ---------------------------------------------------------------------------

export default function RiskList(): JSX.Element {
  const { t } = useTranslation();
  const { id: selectedId } = useParams<{ id?: string }>();
  const navigate = useNavigate();
  const { activeWorkspace } = useWorkspace();
  const [items, setItems] = useState<Risk[]>([]);
  const [selectedRisk, setSelectedRisk] = useState<Risk | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Split-pane resize state
  const [leftPanelWidth, setLeftPanelWidth] = useState(280);
  const isDraggingRef = useRef(false);
  const dragStartXRef = useRef(0);
  const dragStartWidthRef = useRef(0);

  const loadList = useCallback(async (): Promise<void> => {
    if (!activeWorkspace) return;
    setIsLoading(true);
    setError(null);
    try {
      const resp = await risksApi.list(activeWorkspace.id);
      setItems(resp.results);
      // Auto-select first item or navigate to selectedId if it exists
      if (selectedId) {
        const risk = resp.results.find((r) => r.id === selectedId);
        setSelectedRisk(risk || null);
      }
    } catch (err: unknown) {
      const msg = (err as { error?: { message?: string } })?.error?.message ?? String(err);
      setError(msg);
      console.error(err);
    } finally {
      setIsLoading(false);
    }
  }, [activeWorkspace, selectedId]);

  useEffect(() => {
    void loadList();
  }, [loadList]);

  const handleCreate = useCallback(async (): Promise<void> => {
    if (!activeWorkspace) return;
    try {
      const created = await risksApi.create({
        workspace_id: activeWorkspace.id,
        title: t("editor.newRequirementTitle"),
      });
      navigate(`/risks/${created.id}`);
    } catch (err: unknown) {
      console.error("Create failed:", err);
    }
  }, [activeWorkspace, t, navigate]);

  // Split-pane resize handlers
  const handleDividerMouseDown = (e: React.MouseEvent): void => {
    isDraggingRef.current = true;
    dragStartXRef.current = e.clientX;
    dragStartWidthRef.current = leftPanelWidth;
    document.body.style.userSelect = "none";
    document.body.style.cursor = "col-resize";
    e.preventDefault();
  };

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent): void => {
      if (!isDraggingRef.current) return;
      const delta = e.clientX - dragStartXRef.current;
      const newWidth = Math.max(280, dragStartWidthRef.current + delta);
      setLeftPanelWidth(newWidth);
    };

    const handleMouseUp = (): void => {
      if (!isDraggingRef.current) return;
      isDraggingRef.current = false;
      document.body.style.userSelect = "";
      document.body.style.cursor = "";
    };

    document.addEventListener("mousemove", handleMouseMove);
    document.addEventListener("mouseup", handleMouseUp);

    return () => {
      document.removeEventListener("mousemove", handleMouseMove);
      document.removeEventListener("mouseup", handleMouseUp);
    };
  }, []);

  if (isLoading) {
    return <p role="status">{t("loading")}</p>;
  }

  if (error) {
    return (
      <div role="alert">
        <p style={{ color: "var(--color-danger)" }}>{error}</p>
        <button onClick={() => void loadList()}>{t("actions.reload")}</button>
      </div>
    );
  }

  return (
    <div style={{ display: "flex", height: "100%", overflow: "hidden" }}>
      {/* Left panel: Risk list */}
      <div
        style={{
          width: `${leftPanelWidth}px`,
          minWidth: "280px",
          maxWidth: "70%",
          overflow: "auto",
          paddingRight: "var(--space-4)",
        }}
      >
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            marginBottom: "var(--space-3)",
          }}
        >
          <h3
            style={{
              fontSize: "var(--font-size-lg)",
              fontWeight: 600,
              margin: 0,
              color: "var(--color-text)",
            }}
          >
            {t("nav.risks")}
          </h3>
          <button
            type="button"
            data-testid="create-risk-btn"
            onClick={() => void handleCreate()}
            style={primaryButtonStyle}
          >
            + {t("actions.new")}
          </button>
        </div>

        {items.length === 0 ? (
          <p style={{ color: "var(--color-text-muted)", fontSize: "var(--font-size-sm)" }}>
            {t("editor.empty")}
          </p>
        ) : (
          <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
            {items.map((item) => {
              const isSelected = selectedRisk?.id === item.id;
              return (
                <li
                  key={item.id}
                  data-testid={`risk-item-${item.id}`}
                  onClick={() => {
                    setSelectedRisk(item);
                    navigate(`/risks/${item.id}`);
                  }}
                  style={{
                    padding: "var(--space-3) var(--space-4)",
                    marginBottom: "var(--space-2)",
                    background: isSelected ? "var(--color-surface-raised)" : "var(--color-surface)",
                    borderRadius: "var(--radius-md)",
                    border: isSelected ? "1px solid var(--color-primary)" : "1px solid var(--color-border)",
                    cursor: "pointer",
                    transition: "var(--transition-fast)",
                  }}
                >
                  <strong style={{ color: "var(--color-text)" }}>{item.title}</strong>
                  <br />
                  <span style={{ color: "var(--color-text-muted)", fontSize: "var(--font-size-sm)" }}>
                    {item.severity} | {item.probability} | {item.impact} | {item.status}
                  </span>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      {/* Divider for split-pane resize */}
      <div
        onMouseDown={handleDividerMouseDown}
        data-testid="risk-editor-divider"
        style={{
          width: "4px",
          backgroundColor: "var(--color-border)",
          cursor: "col-resize",
          userSelect: "none",
          transition: isDraggingRef.current ? "none" : "background-color var(--transition-fast)",
          flexShrink: 0,
        }}
        onMouseEnter={(e) => {
          (e.currentTarget as HTMLDivElement).style.backgroundColor = "var(--color-border-hover)";
        }}
        onMouseLeave={(e) => {
          if (!isDraggingRef.current) {
            (e.currentTarget as HTMLDivElement).style.backgroundColor = "var(--color-border)";
          }
        }}
      />

      {/* Right panel: Risk detail editor */}
      <div
        style={{
          flex: 1,
          overflow: "hidden",
          background: "var(--color-surface)",
        }}
      >
        {selectedRisk ? (
          <RiskDetailEditor risk={selectedRisk} onSaved={() => void loadList()} />
        ) : (
          <p
            style={{
              color: "var(--color-text-muted)",
              fontSize: "var(--font-size-lg)",
              padding: "var(--space-8)",
              textAlign: "center",
            }}
          >
            {t("risks.selectRisk")}
          </p>
        )}
      </div>
    </div>
  );
}
