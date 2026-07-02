/**
 * ARCH-L1-001 ReactFrontend — TestcaseList (COMP-RF-003).
 *
 * leaf_id: COMP-RF-003
 * req_id:  REQ-L1-040 (Unified ModalDialogBase pattern), REQ-L2-RA-001 (Test Cases)
 *
 * Lists all TestCases for the active workspace and provides a create form.
 * Uses unified ModalDialogBase for form pattern (REQ-L1-040).
 */

import React, { useState, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { useWorkspace } from "../../context/WorkspaceContext";
import { testcasesApi } from "../../api/testcases";
import ModalDialogBase, { SHARED_STYLES } from "../RequirementsList/ModalDialogBase";
import type { TestCase } from "../../api/testcases";

const STATUS_OPTIONS = ["draft", "active", "deprecated"] as const;
type TestCaseStatus = (typeof STATUS_OPTIONS)[number];

export default function TestcaseList(): JSX.Element {
  const { t } = useTranslation();
  const { activeWorkspace } = useWorkspace();
  const [items, setItems] = useState<TestCase[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [status, setStatus] = useState<TestCaseStatus>("draft");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const loadList = async (): Promise<void> => {
    if (!activeWorkspace) return;
    setIsLoading(true);
    try {
      const resp = await testcasesApi.list(activeWorkspace.id);
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
    setStatus("draft");
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
      await testcasesApi.create({
        workspace_id: activeWorkspace.id,
        title: title.trim(),
        description: description.trim() || undefined,
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
        title={t("nav.testCases", "Test Cases")}
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
        testIdPrefix="testcase"
        buttonTestIdPrefix="testcase"
      >
        <div>
          <label htmlFor="testcase-title" style={SHARED_STYLES.label}>
            {t("editor.title", "Title")} *
          </label>
          <input
            id="testcase-title"
            data-testid="testcase-title-input"
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            required
            autoFocus
            disabled={isSubmitting}
            placeholder="Test case title"
            style={SHARED_STYLES.input}
          />
        </div>
        <div>
          <label htmlFor="testcase-description" style={SHARED_STYLES.label}>
            {t("editor.description", "Description")}
          </label>
          <textarea
            id="testcase-description"
            data-testid="testcase-description-input"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            disabled={isSubmitting}
            rows={3}
            placeholder="Describe the test scenario..."
            style={{ ...SHARED_STYLES.input, fontFamily: "inherit", resize: "vertical" }}
          />
        </div>
        <div>
          <label htmlFor="testcase-status" style={SHARED_STYLES.label}>
            {t("editor.status", "Status")}
          </label>
          <select
            id="testcase-status"
            data-testid="testcase-status-select"
            value={status}
            onChange={(e) => setStatus(e.target.value as TestCaseStatus)}
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
      </ModalDialogBase>

      {/* Item list (rendered outside modal) */}
      {items.length > 0 && (
        <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
          {items.map((item) => (
            <li
              key={item.id}
              data-testid={`testcase-item-${item.id}`}
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
    </>
  );
}
