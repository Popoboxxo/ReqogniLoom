/**
 * ARCH-L1-001 ReactFrontend — ADR list view (COMP-RF-003).
 *
 * leaf_id: COMP-RF-003
 * req_id: REQ-L1-029 (ADR/Risk/Issue REST API)
 *        REQ-002 (Split-View Layout)
 *
 * Lists all ADRs for the active workspace in a split-view layout:
 * - Left pane: searchable list of ADRs
 * - Right pane: create/edit form with resizable divider
 */

import React, { useState, useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import { useWorkspace } from "../../context/WorkspaceContext";
import { adrsApi } from "../../api/adrs";
import type { Adr, AdrStatus } from "../../types";

const STATUS_OPTIONS: AdrStatus[] = [
  "Draft",
  "In Review",
  "Approved",
  "Rejected",
  "Superseded",
];

const labelStyle: React.CSSProperties = {
  fontWeight: 500,
  color: "var(--color-text)",
  display: "block",
  marginBottom: "var(--space-2)",
  fontSize: "var(--font-size-sm)",
};

const inputStyle: React.CSSProperties = {
  width: "100%",
  border: "1px solid var(--color-border)",
  borderRadius: "var(--radius-md)",
  padding: "var(--space-2) var(--space-3)",
  fontFamily: "var(--font-sans)",
  fontSize: "var(--font-size-sm)",
  marginBottom: "var(--space-3)",
  color: "var(--color-text)",
  background: "var(--color-surface)",
  boxSizing: "border-box",
};

export default function AdrList(): JSX.Element {
  const { t } = useTranslation();
  const { activeWorkspace } = useWorkspace();
  const [items, setItems] = useState<Adr[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  const [title, setTitle] = useState("");
  const [context, setContext] = useState("");
  const [decision, setDecision] = useState("");
  const [status, setStatus] = useState<AdrStatus>("Draft");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const [dividerPos, setDividerPos] = useState(50);
  const dividerRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const loadList = async (): Promise<void> => {
    if (!activeWorkspace) return;
    setIsLoading(true);
    try {
      const resp = await adrsApi.list(activeWorkspace.id);
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
    setContext("");
    setDecision("");
    setStatus("Draft");
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
      await adrsApi.create({
        workspace_id: activeWorkspace.id,
        title: title.trim(),
        description: decision.trim() || undefined,
        context: context.trim() || undefined,
        status,
      });
      resetForm();
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

  // Handle divider drag
  useEffect(() => {
    const handleMouseMove = (e: MouseEvent): void => {
      if (!dividerRef.current || !containerRef.current) return;
      const rect = containerRef.current.getBoundingClientRect();
      const newPos = ((e.clientX - rect.left) / rect.width) * 100;
      if (newPos > 20 && newPos < 80) {
        setDividerPos(newPos);
      }
    };

    const handleMouseUp = (): void => {
      document.removeEventListener("mousemove", handleMouseMove);
      document.removeEventListener("mouseup", handleMouseUp);
    };

    const handleMouseDown = (): void => {
      document.addEventListener("mousemove", handleMouseMove);
      document.addEventListener("mouseup", handleMouseUp);
    };

    const divider = dividerRef.current;
    if (divider) {
      divider.addEventListener("mousedown", handleMouseDown);
    }

    return () => {
      if (divider) divider.removeEventListener("mousedown", handleMouseDown);
    };
  }, []);

  if (isLoading) return <p>{t("loading")}</p>;

  return (
    <div
      ref={containerRef}
      style={{
        display: "grid",
        gridTemplateColumns: `${dividerPos}% 8px 1fr`,
        height: "100vh",
        gap: 0,
      }}
    >
      {/* Left pane: Item list */}
      <div
        style={{
          borderRight: "1px solid var(--color-border)",
          overflowY: "auto",
          padding: "var(--space-4)",
          background: "var(--color-surface-alt)",
        }}
      >
        <h2
          style={{
            fontSize: "var(--font-size-lg)",
            fontWeight: 700,
            marginBottom: "var(--space-4)",
            marginTop: 0,
            color: "var(--color-text)",
          }}
        >
          {t("nav.adrs")} ({items.length})
        </h2>

        {items.length === 0 ? (
          <p style={{ color: "var(--color-text-muted)" }}>
            {t("editor.empty", "No items")}
          </p>
        ) : (
          <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
            {items.map((item) => (
              <li
                key={item.id}
                data-testid={`adr-item-${item.id}`}
                style={{
                  padding: "var(--space-3)",
                  marginBottom: "var(--space-2)",
                  background: "var(--color-surface)",
                  borderRadius: "var(--radius-md)",
                  border: "1px solid var(--color-border)",
                  cursor: "pointer",
                  transition: "var(--transition-fast)",
                }}
              >
                <strong style={{ color: "var(--color-text)" }}>
                  {item.title}
                </strong>{" "}
                <span
                  style={{
                    color: "var(--color-text-muted)",
                    fontSize: "var(--font-size-xs)",
                  }}
                >
                  — {item.status}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* Resizable divider */}
      <div
        ref={dividerRef}
        data-testid="adr-divider"
        style={{
          background: "var(--color-border)",
          cursor: "col-resize",
          transition: "background 0.2s",
          hoverBackground: "var(--color-primary)",
        }}
        onMouseEnter={(e) => {
          (e.currentTarget as HTMLDivElement).style.background =
            "var(--color-primary)";
        }}
        onMouseLeave={(e) => {
          (e.currentTarget as HTMLDivElement).style.background =
            "var(--color-border)";
        }}
      />

      {/* Right pane: Form */}
      <div
        style={{
          overflowY: "auto",
          padding: "var(--space-6)",
          background: "var(--color-surface)",
        }}
      >
        <h3
          style={{
            fontSize: "var(--font-size-lg)",
            fontWeight: 700,
            marginBottom: "var(--space-4)",
            marginTop: 0,
            color: "var(--color-text)",
          }}
        >
          {t("actions.create", "Create ADR")}
        </h3>

        <form
          data-testid="adr-form"
          onSubmit={handleSubmit}
          style={{ display: "flex", flexDirection: "column", gap: "var(--space-4)" }}
        >
          <div>
            <label htmlFor="adr-title" style={labelStyle}>
              {t("editor.title", "Title")} *
            </label>
            <input
              id="adr-title"
              data-testid="adr-title-input"
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              required
              autoFocus
              disabled={isSubmitting}
              placeholder="ADR title"
              style={inputStyle}
            />
          </div>

          <div>
            <label htmlFor="adr-context" style={labelStyle}>
              {t("editor.context", "Context")}
            </label>
            <textarea
              id="adr-context"
              data-testid="adr-context-input"
              value={context}
              onChange={(e) => setContext(e.target.value)}
              disabled={isSubmitting}
              rows={4}
              placeholder="What is the context / problem?"
              style={{
                ...inputStyle,
                fontFamily: "inherit",
                resize: "vertical",
              }}
            />
          </div>

          <div>
            <label htmlFor="adr-decision" style={labelStyle}>
              {t("editor.decision", "Decision")}
            </label>
            <textarea
              id="adr-decision"
              data-testid="adr-decision-input"
              value={decision}
              onChange={(e) => setDecision(e.target.value)}
              disabled={isSubmitting}
              rows={4}
              placeholder="What is the decision and its consequences?"
              style={{
                ...inputStyle,
                fontFamily: "inherit",
                resize: "vertical",
              }}
            />
          </div>

          <div>
            <label htmlFor="adr-status" style={labelStyle}>
              {t("editor.status", "Status")}
            </label>
            <select
              id="adr-status"
              data-testid="adr-status-select"
              value={status}
              onChange={(e) => setStatus(e.target.value as AdrStatus)}
              disabled={isSubmitting}
              style={inputStyle}
            >
              {STATUS_OPTIONS.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </div>

          {formError && (
            <p
              role="alert"
              style={{
                color: "var(--color-danger)",
                fontSize: "var(--font-size-sm)",
                marginBottom: "var(--space-2)",
              }}
            >
              {formError}
            </p>
          )}

          <button
            type="submit"
            data-testid="adr-submit"
            disabled={isSubmitting}
            style={{
              background: isSubmitting
                ? "var(--color-text-muted)"
                : "var(--color-primary)",
              color: "white",
              border: "none",
              borderRadius: "var(--radius-md)",
              padding: "var(--space-3) var(--space-6)",
              fontSize: "var(--font-size-base)",
              cursor: isSubmitting ? "not-allowed" : "pointer",
              fontWeight: 600,
              opacity: isSubmitting ? 0.7 : 1,
            }}
          >
            {isSubmitting ? t("actions.saving") : t("actions.create")}
          </button>

          <button
            type="button"
            data-testid="adr-reset"
            onClick={resetForm}
            disabled={isSubmitting}
            style={{
              background: "transparent",
              color: "var(--color-text-muted)",
              border: "1px solid var(--color-border)",
              borderRadius: "var(--radius-md)",
              padding: "var(--space-2) var(--space-4)",
              fontSize: "var(--font-size-sm)",
              cursor: "pointer",
              fontWeight: 500,
            }}
          >
            {t("actions.clear", "Clear")}
          </button>
        </form>
      </div>
    </div>
  );
}
