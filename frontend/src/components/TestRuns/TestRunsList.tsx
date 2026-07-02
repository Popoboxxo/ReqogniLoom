/**
 * ARCH-L1-001 ReactFrontend — TestRunsList (COMP-RF-003).
 *
 * leaf_id: COMP-RF-003
 * req_id:  REQ-L1-040 (Unified ModalDialogBase pattern), REQ-L2-AS-030 (Test-Run-Protokollierung)
 *
 * Lists all Test Runs for the active workspace and provides a create form.
 * Uses unified ModalDialogBase for form pattern (REQ-L1-040).
 */

import React, { useState, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { useWorkspace } from "../../context/WorkspaceContext";
import { testRunsApi } from "../../api/test-runs";
import ModalDialogBase, { SHARED_STYLES } from "../RequirementsList/ModalDialogBase";
import type { TestRun } from "../../types";

export default function TestRunsList(): JSX.Element {
  const { t } = useTranslation();
  const { activeWorkspace } = useWorkspace();
  const [items, setItems] = useState<TestRun[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const loadList = async (): Promise<void> => {
    if (!activeWorkspace) return;
    setIsLoading(true);
    try {
      const resp = await testRunsApi.list(activeWorkspace.id);
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
    setName("");
    setDescription("");
    setFormError(null);
  };

  const handleSubmit = async (
    e: React.FormEvent<HTMLFormElement>
  ): Promise<void> => {
    e.preventDefault();
    if (!activeWorkspace) return;
    if (!name.trim()) {
      setFormError("Name is required");
      return;
    }
    setIsSubmitting(true);
    setFormError(null);
    try {
      await testRunsApi.create({
        workspace_id: activeWorkspace.id,
        name: name.trim(),
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
        title={t("nav.testRuns", "Test Runs")}
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
        testIdPrefix="testrun"
        buttonTestIdPrefix="testrun"
      >
        <div>
          <label htmlFor="testrun-name" style={SHARED_STYLES.label}>
            {t("editor.name", "Name")} *
          </label>
          <input
            id="testrun-name"
            data-testid="testrun-name-input"
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
            autoFocus
            disabled={isSubmitting}
            placeholder="Test run name"
            style={SHARED_STYLES.input}
          />
        </div>
        <div>
          <label htmlFor="testrun-description" style={SHARED_STYLES.label}>
            {t("editor.description", "Description")}
          </label>
          <textarea
            id="testrun-description"
            data-testid="testrun-description-input"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            disabled={isSubmitting}
            rows={3}
            placeholder="Describe the test run..."
            style={{ ...SHARED_STYLES.input, fontFamily: "inherit", resize: "vertical" }}
          />
        </div>
      </ModalDialogBase>

      {/* Item list (rendered outside modal) */}
      {items.length > 0 && (
        <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
          {items.map((item) => (
            <li
              key={item.id}
              data-testid={`testrun-item-${item.id}`}
              style={{
                padding: "var(--space-3) var(--space-4)",
                marginBottom: "var(--space-2)",
                background: "var(--color-surface)",
                borderRadius: "var(--radius-md)",
                border: "1px solid var(--color-border)",
              }}
            >
              <strong>{item.name}</strong>{" "}
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
