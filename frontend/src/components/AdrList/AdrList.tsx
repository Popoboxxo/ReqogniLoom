/**
 * ARCH-L1-001 ReactFrontend — ADR list view (COMP-RF-003).
 *
 * leaf_id: COMP-RF-003
 * req_id:  REQ-L1-029 (ADR/Risk/Issue REST API)
 *
 * Lists all ADRs for the active workspace and provides a create form.
 */

import React, { useState, useEffect } from "react";
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

export default function AdrList(): JSX.Element {
  const { t } = useTranslation();
  const { activeWorkspace } = useWorkspace();
  const [items, setItems] = useState<Adr[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [title, setTitle] = useState("");
  const [context, setContext] = useState("");
  const [decision, setDecision] = useState("");
  const [status, setStatus] = useState<AdrStatus>("Draft");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

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
      // Backend maps `decision` -> `description` (the consequence / outcome
      // field) and `context` -> `context` directly. The serializer on
      // /api/v1/adrs/ accepts both shapes; we send `description` for the
      // decision text and keep `context` separate.
      await adrsApi.create({
        workspace_id: activeWorkspace.id,
        title: title.trim(),
        description: decision.trim() || undefined,
        context: context.trim() || undefined,
        status,
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
          {t("nav.adrs")}
        </h2>
        <button
          type="button"
          data-testid="adr-create-btn"
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
          {showCreate ? t("actions.cancel") : `+ ${t("actions.new", "New ADR")}`}
        </button>
      </div>

      {showCreate && (
        <form
          data-testid="adr-create-form"
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
              Context
            </label>
            <textarea
              id="adr-context"
              data-testid="adr-context-input"
              value={context}
              onChange={(e) => setContext(e.target.value)}
              disabled={isSubmitting}
              rows={3}
              placeholder="What is the context / problem?"
              style={{ ...inputStyle, fontFamily: "inherit", resize: "vertical" }}
            />
          </div>
          <div>
            <label htmlFor="adr-decision" style={labelStyle}>
              Decision
            </label>
            <textarea
              id="adr-decision"
              data-testid="adr-decision-input"
              value={decision}
              onChange={(e) => setDecision(e.target.value)}
              disabled={isSubmitting}
              rows={3}
              placeholder="What is the decision and its consequences?"
              style={{ ...inputStyle, fontFamily: "inherit", resize: "vertical" }}
            />
          </div>
          <div>
            <label htmlFor="adr-status" style={labelStyle}>
              Status
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
                margin: 0,
              }}
            >
              {formError}
            </p>
          )}
          <div style={{ display: "flex", gap: "var(--space-2)", justifyContent: "flex-end" }}>
            <button
              type="button"
              data-testid="adr-cancel-btn"
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
              data-testid="adr-save-btn"
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
              data-testid={`adr-item-${item.id}`}
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
                — {item.status}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
