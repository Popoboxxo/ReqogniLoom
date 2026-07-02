/**
 * ARCH-L1-001 ReactFrontend — Issue list view (COMP-RF-003).
 *
 * leaf_id: COMP-RF-003
 * req_id:  REQ-L1-029 (ADR/Risk/Issue REST API)
 *
 * Lists all Issues for the active workspace and provides a create form.
 * Uses unified ModalDialogBase for form pattern (REQ-L1-040).
 */

import React, { useState, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { useWorkspace } from "../../context/WorkspaceContext";
import { issuesApi } from "../../api/issues";
import ModalDialogBase, { SHARED_STYLES } from "../RequirementsList/ModalDialogBase";
import type { Issue, IssueSeverity, IssueStatus } from "../../types";

const SEVERITY_OPTIONS: IssueSeverity[] = ["low", "medium", "high", "critical"];
const STATUS_OPTIONS: IssueStatus[] = ["Open", "In Progress", "Resolved", "Closed", "Wontfix"];

export default function IssueList(): JSX.Element {
  const { t } = useTranslation();
  const { activeWorkspace } = useWorkspace();
  const [items, setItems] = useState<Issue[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [severity, setSeverity] = useState<IssueSeverity>("medium");
  const [status, setStatus] = useState<IssueStatus>("Open");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const loadList = async (): Promise<void> => {
    if (!activeWorkspace) return;
    setIsLoading(true);
    try {
      const resp = await issuesApi.list(activeWorkspace.id);
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
    setStatus("Open");
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
      await issuesApi.create({
        workspace_id: activeWorkspace.id,
        title: title.trim(),
        description: description.trim() || undefined,
        severity,
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
    <>
      <ModalDialogBase
        title={t("nav.issues")}
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
        testIdPrefix="issue"
        buttonTestIdPrefix="issue"
      >
        <div>
          <label htmlFor="issue-title" style={SHARED_STYLES.label}>
            {t("editor.title", "Title")} *
          </label>
          <input
            id="issue-title"
            data-testid="issue-title-input"
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            required
            autoFocus
            disabled={isSubmitting}
            placeholder="Issue title"
            style={SHARED_STYLES.input}
          />
        </div>
        <div>
          <label htmlFor="issue-description" style={SHARED_STYLES.label}>
            {t("editor.description", "Description")}
          </label>
          <textarea
            id="issue-description"
            data-testid="issue-description-input"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            disabled={isSubmitting}
            rows={3}
            placeholder="Describe the issue..."
            style={{ ...SHARED_STYLES.input, fontFamily: "inherit", resize: "vertical" }}
          />
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--space-3)" }}>
          <div>
            <label htmlFor="issue-severity" style={SHARED_STYLES.label}>
              Severity
            </label>
            <select
              id="issue-severity"
              data-testid="issue-severity-select"
              value={severity}
              onChange={(e) => setSeverity(e.target.value as IssueSeverity)}
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
            <label htmlFor="issue-status" style={SHARED_STYLES.label}>
              Status
            </label>
            <select
              id="issue-status"
              data-testid="issue-status-select"
              value={status}
              onChange={(e) => setStatus(e.target.value as IssueStatus)}
              disabled={isSubmitting}
              style={SHARED_STYLES.input}
            >
              {STATUS_OPTIONS.map((s) => (
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
              data-testid={`issue-item-${item.id}`}
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
                — {item.severity} | {item.status}
              </span>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
