/**
 * ARCH-L1-001 ReactFrontend — TestCasesView (COMP-RF-003).
 *
 * leaf_id: COMP-RF-003
 * req_id:  REQ-L2-RA-001 (Test Cases),
 *          REQ-L1-035 (Trace Links: TestCase verifies Requirement),
 *          REQ-002 (Masken-Standardisierung: split-view layout)
 *
 * Split-view test-case catalog with resizable panels. Provides:
 *   - Left panel: List view of all TestCases for the active workspace + create form
 *   - Right panel: Detail/edit view with linked-requirements multi-select
 *   - Trace-link wiring via the generic trace_links API (link_type=verifies)
 */

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useWorkspace } from "../../context/WorkspaceContext";
import { testcasesApi, type TestCase } from "../../api/testcases";
import { requirementsApi } from "../../api/requirements";
import { tracelinksApi } from "../../api/tracelinks";
import type { Requirement, UUID } from "../../types";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const STATUS_OPTIONS = ["draft", "active", "deprecated"] as const;
type TestCaseStatus = (typeof STATUS_OPTIONS)[number];

const PRIORITY_OPTIONS = ["low", "med", "high"] as const;
type TestCasePriority = (typeof PRIORITY_OPTIONS)[number];

// ---------------------------------------------------------------------------
// Shared style helpers
// ---------------------------------------------------------------------------

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
  display: "block",
  fontSize: "var(--font-size-sm)",
  fontWeight: 600,
  color: "var(--color-text)",
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

// ---------------------------------------------------------------------------
// Status badge
// ---------------------------------------------------------------------------

const STATUS_COLORS: Record<string, { bg: string; color: string }> = {
  draft: { bg: "rgba(100,116,139,0.15)", color: "#64748b" },
  active: { bg: "rgba(34,197,94,0.15)", color: "#22c55e" },
  deprecated: { bg: "rgba(239,68,68,0.15)", color: "#ef4444" },
};

function StatusBadge({ status }: { status: string }): JSX.Element {
  const colors = STATUS_COLORS[status] ?? STATUS_COLORS.draft;
  return (
    <span
      style={{
        display: "inline-block",
        padding: "2px var(--space-2)",
        borderRadius: "var(--radius-sm)",
        background: colors.bg,
        color: colors.color,
        fontSize: "0.75rem",
        fontWeight: 600,
        textTransform: "uppercase",
        letterSpacing: "0.05em",
      }}
    >
      {status}
    </span>
  );
}

// ---------------------------------------------------------------------------
// TestCasesView — main component
// ---------------------------------------------------------------------------

export default function TestCasesView(): JSX.Element {
  const { t } = useTranslation();
  const { activeWorkspace } = useWorkspace();
  const [items, setItems] = useState<TestCase[]>([]);
  const [requirements, setRequirements] = useState<Requirement[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);

  // Split-pane state (REQ-002: Masken-Standardisierung)
  const [leftPanelWidth, setLeftPanelWidth] = useState(260);
  const isDraggingRef = useRef(false);
  const dragStartXRef = useRef(0);
  const dragStartWidthRef = useRef(0);

  // Create-form state
  const [newTitle, setNewTitle] = useState("");
  const [newDescription, setNewDescription] = useState("");
  const [newStatus, setNewStatus] = useState<TestCaseStatus>("draft");
  const [newPriority, setNewPriority] = useState<TestCasePriority>("med");
  const [newLinkedReqIds, setNewLinkedReqIds] = useState<Set<UUID>>(
    new Set()
  );
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  // Detail-edit state (hydrated from selected test case)
  const [editTitle, setEditTitle] = useState("");
  const [editDescription, setEditDescription] = useState("");
  const [editStatus, setEditStatus] = useState<TestCaseStatus>("draft");
  const [editLinkedReqIds, setEditLinkedReqIds] = useState<Set<UUID>>(
    new Set()
  );
  const [isSaving, setIsSaving] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);

  // ---- Load list -----------------------------------------------------------

  const loadList = useCallback(async (): Promise<void> => {
    if (!activeWorkspace) return;
    setIsLoading(true);
    try {
      const resp = await testcasesApi.list(activeWorkspace.id);
      setItems(resp.results);
    } catch (err) {
      console.error("Failed to load test cases:", err);
    } finally {
      setIsLoading(false);
    }
  }, [activeWorkspace]);

  const loadRequirements = useCallback(async (): Promise<void> => {
    if (!activeWorkspace) return;
    try {
      const resp = await requirementsApi.list(activeWorkspace.id);
      setRequirements(resp.results);
    } catch (err) {
      console.error("Failed to load requirements:", err);
    }
  }, [activeWorkspace]);

  useEffect(() => {
    void loadList();
  }, [loadList]);

  useEffect(() => {
    void loadRequirements();
  }, [loadRequirements]);

  // ---- Load selected test-case + trace-links detail view -------------------

  const loadDetail = useCallback(
    async (id: UUID): Promise<void> => {
      try {
        const tc = await testcasesApi.get(id);
        setEditTitle(tc.title);
        setEditDescription(tc.description);
        setEditStatus((tc.status as TestCaseStatus) ?? "draft");

        // Hydrate linked requirements: pull all trace links for test case and
        // resolve "verifies" links to requirement artifacts.
        if (activeWorkspace) {
          const linksResp = await tracelinksApi.listForArtifact(
            activeWorkspace.id,
            id
          );
          const linkedIds = new Set<UUID>();
          for (const link of linksResp.results) {
            if (link.link_type === "verifies") {
              linkedIds.add(link.target_id);
            }
          }
          setEditLinkedReqIds(linkedIds);
        }
      } catch (err) {
        console.error("Failed to load test case detail:", err);
      }
    },
    [activeWorkspace]
  );

  useEffect(() => {
    if (selectedId) {
      void loadDetail(selectedId);
    }
  }, [selectedId, loadDetail]);

  // Split-pane resize handlers (REQ-002: Masken-Standardisierung)
  const handleDividerMouseDown = (e: React.MouseEvent): void => {
    isDraggingRef.current = true;
    dragStartXRef.current = e.clientX;
    dragStartWidthRef.current = leftPanelWidth;
    e.preventDefault();
  };

  useEffect(() => {
    if (!isDraggingRef.current) return;

    const handleMouseMove = (e: MouseEvent): void => {
      if (!isDraggingRef.current) return;
      const delta = e.clientX - dragStartXRef.current;
      setLeftPanelWidth(Math.max(260, dragStartWidthRef.current + delta));
    };

    const handleMouseUp = (): void => {
      isDraggingRef.current = false;
    };

    document.addEventListener("mousemove", handleMouseMove);
    document.addEventListener("mouseup", handleMouseUp);
    document.body.style.userSelect = "none";
    document.body.style.cursor = "col-resize";

    return () => {
      document.removeEventListener("mousemove", handleMouseMove);
      document.removeEventListener("mouseup", handleMouseUp);
      document.body.style.userSelect = "auto";
      document.body.style.cursor = "auto";
    };
  }, [leftPanelWidth]);

  // ---- Handlers ----

  const resetCreateForm = (): void => {
    setNewTitle("");
    setNewDescription("");
    setNewStatus("draft");
    setNewPriority("med");
    setNewLinkedReqIds(new Set());
    setFormError(null);
  };

  const handleCreate = async (
    e: React.FormEvent<HTMLFormElement>
  ): Promise<void> => {
    e.preventDefault();
    if (!activeWorkspace) return;
    if (!newTitle.trim()) {
      setFormError("Title required");
      return;
    }
    setIsSubmitting(true);
    setFormError(null);
    try {
      const created = await testcasesApi.create({
        workspace_id: activeWorkspace.id,
        title: newTitle.trim(),
        description: newDescription.trim() || undefined,
        status: newStatus,
        priority: newPriority,
      });

      // Auto-resolve REQ test-case verifies-link for each linked requirement.
      for (const reqId of newLinkedReqIds) {
        try {
          await tracelinksApi.create({
            source_id: created.id,
            target_id: reqId,
            link_type: "verifies",
            workspace_id: activeWorkspace.id,
          });
        } catch (err) {
          console.error("Failed to create trace link:", err);
        }
      }

      resetCreateForm();
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

  const handleSaveDetail = async (): Promise<void> => {
    if (!selectedId || !activeWorkspace) return;
    setIsSaving(true);
    setEditError(null);
    try {
      await testcasesApi.update(selectedId, {
        title: editTitle.trim(),
        description: editDescription,
        status: editStatus,
      });
      await loadList();
    } catch (err: unknown) {
      const msg =
        (err as { error?: { message?: string } })?.error?.message ??
        String(err);
      setEditError(msg);
    } finally {
      setIsSaving(false);
    }
  };

  const requirementsById = useMemo(() => {
    const m: Record<UUID, Requirement> = {};
    for (const r of requirements) m[r.id] = r;
    return m;
  }, [requirements]);

  // ---- Render: loading

  if (isLoading) {
    return (
      <div>
        <p
          role="status"
          style={{
            color: "var(--color-text-muted)",
            padding: "var(--space-6)",
          }}
        >
          {t("loading")}
        </p>
      </div>
    );
  }

  const selected = selectedId ? items.find((it) => it.id === selectedId) : null;

  // ---- Render: split-view layout (REQ-002: Masken-Standardisierung)

  return (
    <div style={{ display: "flex", height: "100%", overflow: "hidden" }}>
      {/* Left panel: TestCase list + create form */}
      <div
        style={{
          width: `${leftPanelWidth}px`,
          minWidth: "260px",
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
            {t("nav.testCases", "Test Cases")}
          </h2>
          <button
            type="button"
            data-testid="testcase-create-btn"
            onClick={() => {
              if (showCreate) {
                resetCreateForm();
                setShowCreate(false);
              } else {
                setShowCreate(true);
              }
            }}
            style={primaryButtonStyle}
          >
            {showCreate
              ? t("actions.cancel")
              : `+ ${t("actions.new", "New Test Case")}`}
          </button>
        </div>

        {showCreate && (
          <form
            data-testid="testcase-create-form"
            onSubmit={(e) => void handleCreate(e)}
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
              <label htmlFor="testcase-title" style={labelStyle}>
                {t("editor.title", "Title")} *
              </label>
              <input
                id="testcase-title"
                data-testid="testcase-title-input"
                type="text"
                value={newTitle}
                onChange={(e) => setNewTitle(e.target.value)}
                required
                autoFocus
                disabled={isSubmitting}
                placeholder="Test case title"
                style={inputStyle}
              />
            </div>
            <div>
              <label htmlFor="testcase-description" style={labelStyle}>
                {t("editor.description", "Description")}
              </label>
              <textarea
                id="testcase-description"
                data-testid="testcase-description-input"
                value={newDescription}
                onChange={(e) => setNewDescription(e.target.value)}
                disabled={isSubmitting}
                rows={3}
                placeholder="Describe the test scenario..."
                style={{
                  ...inputStyle,
                  fontFamily: "inherit",
                  resize: "vertical",
                }}
              />
            </div>
            <div>
              <label htmlFor="testcase-status" style={labelStyle}>
                {t("editor.status", "Status")}
              </label>
              <select
                id="testcase-status"
                data-testid="testcase-status-select"
                value={newStatus}
                onChange={(e) =>
                  setNewStatus(e.target.value as TestCaseStatus)
                }
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
            <div>
              <label htmlFor="testcase-priority" style={labelStyle}>
                {t("editor.priority", "Priority")}
              </label>
              <select
                id="testcase-priority"
                data-testid="testcase-priority-select"
                value={newPriority}
                onChange={(e) =>
                  setNewPriority(e.target.value as TestCasePriority)
                }
                disabled={isSubmitting}
                style={inputStyle}
              >
                {PRIORITY_OPTIONS.map((p) => (
                  <option key={p} value={p}>
                    {p}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor="testcase-link-req-select" style={labelStyle}>
                {t("traceability.linkedRequirements", "Link Requirements")}
              </label>
              <select
                id="testcase-link-req-select"
                data-testid="testcase-link-req-select"
                multiple
                value={[...newLinkedReqIds]}
                onChange={(e) => {
                  const selected = new Set<UUID>();
                  for (const opt of Array.from(e.target.selectedOptions)) {
                    selected.add(opt.value as UUID);
                  }
                  setNewLinkedReqIds(selected);
                }}
                disabled={isSubmitting}
                size={Math.min(6, Math.max(3, requirements.length))}
                style={{ ...inputStyle, fontFamily: "inherit" }}
              >
                {requirements.length === 0 && (
                  <option disabled value="">
                    No requirements in workspace
                  </option>
                )}
                {requirements.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.title || t("editor.untitled", "Untitled")}
                  </option>
                ))}
              </select>
              <p
                style={{
                  fontSize: "var(--font-size-sm)",
                  color: "var(--color-text-muted)",
                  margin: "var(--space-1) 0 0 0",
                }}
              >
                Hold Ctrl/Cmd select multiple. Each will be linked via
                verifies-trace after save.
              </p>
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
            <div
              style={{
                display: "flex",
                gap: "var(--space-2)",
                justifyContent: "flex-end",
              }}
            >
              <button
                type="button"
                data-testid="testcase-cancel-btn"
                onClick={() => {
                  resetCreateForm();
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
                  opacity: isSubmitting ? 0.6 : 1,
                }}
              >
                {t("actions.cancel")}
              </button>
              <button
                type="submit"
                data-testid="testcase-save-btn"
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
            data-testid="testcases-empty"
            style={{
              fontSize: "var(--font-size-base)",
              color: "var(--color-text-muted)",
              padding: "var(--space-6)",
              background: "var(--color-surface-raised)",
              borderRadius: "var(--radius-lg)",
              border: "1px solid var(--color-border)",
            }}
          >
            {t("editor.empty", "No test cases")}
          </p>
        ) : (
          <ul
            data-testid="testcases-list"
            style={{
              listStyle: "none",
              padding: 0,
              margin: 0,
            }}
          >
            {items.map((tc) => (
              <li key={tc.id} data-testid={`testcase-item-${tc.id}`}>
                <button
                  type="button"
                  onClick={() => setSelectedId(tc.id)}
                  style={{
                    width: "100%",
                    textAlign: "left",
                    padding: "var(--space-3) var(--space-4)",
                    background:
                      selectedId === tc.id
                        ? "var(--color-surface-raised)"
                        : "var(--color-surface)",
                    border: "1px solid var(--color-border)",
                    borderRadius: "var(--radius-md)",
                    boxShadow: "var(--shadow-card)",
                    cursor: "pointer",
                    fontFamily: "inherit",
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    gap: "var(--space-3)",
                    marginBottom: "var(--space-2)",
                  }}
                >
                  <div>
                    <div
                      style={{
                        fontWeight: 600,
                        color: "var(--color-text)",
                        fontSize: "var(--font-size-base)",
                      }}
                    >
                      {tc.title || t("editor.untitled", "Untitled")}
                    </div>
                    {tc.description && (
                      <div
                        style={{
                          color: "var(--color-text-muted)",
                          fontSize: "var(--font-size-sm)",
                          marginTop: "var(--space-1)",
                        }}
                      >
                        {tc.description.length > 120
                          ? tc.description.slice(0, 120) + "…"
                          : tc.description}
                      </div>
                    )}
                  </div>
                  <StatusBadge status={tc.status} />
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* Divider for split-pane resize */}
      <div
        onMouseDown={handleDividerMouseDown}
        data-testid="testcase-editor-divider"
        style={{
          width: "4px",
          backgroundColor: "var(--color-border)",
          cursor: "col-resize",
          userSelect: "none",
          transition: isDraggingRef.current
            ? "none"
            : "background-color var(--transition-fast)",
          flexShrink: 0,
        }}
        onMouseEnter={(e) => {
          (
            e.currentTarget as HTMLDivElement
          ).style.backgroundColor = "var(--color-border-hover)";
        }}
        onMouseLeave={(e) => {
          if (!isDraggingRef.current) {
            (
              e.currentTarget as HTMLDivElement
            ).style.backgroundColor = "var(--color-border)";
          }
        }}
      />

      {/* Right panel: detail editor or empty state */}
      <div
        style={{
          flex: 1,
          overflow: "auto",
          paddingLeft: "var(--space-4)",
        }}
      >
        {!selected ? (
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              height: "100%",
              color: "var(--color-text-muted)",
              fontSize: "var(--font-size-lg)",
            }}
          >
            {t("editor.selectItem", "Select a test case to edit")}
          </div>
        ) : (
          <div data-testid="testcase-detail">
            <h2
              data-testid="testcase-detail-title"
              style={{
                fontSize: "var(--font-size-2xl)",
                fontWeight: 700,
                color: "var(--color-text)",
                margin: 0,
                marginBottom: "var(--space-2)",
              }}
            >
              {editTitle || t("editor.untitled")}
            </h2>
            <div style={{ marginBottom: "var(--space-4)" }}>
              <StatusBadge status={editStatus} />
            </div>

            <div
              style={{
                background: "var(--color-surface)",
                border: "1px solid var(--color-border)",
                borderRadius: "var(--radius-lg)",
                boxShadow: "var(--shadow-card)",
                padding: "var(--space-6)",
                marginBottom: "var(--space-4)",
              }}
            >
              <label htmlFor="testcase-edit-title" style={labelStyle}>
                {t("editor.title", "Title")}
              </label>
              <input
                id="testcase-edit-title"
                data-testid="testcase-edit-title-input"
                type="text"
                value={editTitle}
                onChange={(e) => setEditTitle(e.target.value)}
                disabled={isSaving}
                style={inputStyle}
              />

              <label
                htmlFor="testcase-edit-description"
                style={{ ...labelStyle, marginTop: "var(--space-4)" }}
              >
                {t("editor.description", "Description")}
              </label>
              <textarea
                id="testcase-edit-description"
                data-testid="testcase-edit-description-input"
                value={editDescription}
                onChange={(e) => setEditDescription(e.target.value)}
                disabled={isSaving}
                rows={4}
                style={{
                  ...inputStyle,
                  fontFamily: "inherit",
                  resize: "vertical",
                }}
              />
              <label
                htmlFor="testcase-edit-status"
                style={{ ...labelStyle, marginTop: "var(--space-4)" }}
              >
                {t("editor.status", "Status")}
              </label>
              <select
                id="testcase-edit-status"
                data-testid="testcase-edit-status-select"
                value={editStatus}
                onChange={(e) =>
                  setEditStatus(e.target.value as TestCaseStatus)
                }
                disabled={isSaving}
                style={inputStyle}
              >
                {STATUS_OPTIONS.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
              {editError && (
                <p
                  role="alert"
                  style={{
                    color: "var(--color-danger)",
                    fontSize: "var(--font-size-sm)",
                    margin: "var(--space-2) 0 0 0",
                  }}
                >
                  {editError}
                </p>
              )}
              <div
                style={{
                  display: "flex",
                  gap: "var(--space-2)",
                  marginTop: "var(--space-4)",
                }}
              >
                <button
                  type="button"
                  data-testid="testcase-detail-save-btn"
                  onClick={() => void handleSaveDetail()}
                  disabled={isSaving}
                  style={{
                    ...primaryButtonStyle,
                    opacity: isSaving ? 0.6 : 1,
                    cursor: isSaving ? "not-allowed" : "pointer",
                  }}
                >
                  {isSaving ? t("actions.saving") : t("actions.save")}
                </button>
              </div>
            </div>

            <div
              data-testid="testcase-linked-reqs"
              style={{
                background: "var(--color-surface)",
                border: "1px solid var(--color-border)",
                borderRadius: "var(--radius-lg)",
                boxShadow: "var(--shadow-card)",
                padding: "var(--space-6)",
              }}
            >
              <h3
                style={{
                  margin: 0,
                  marginBottom: "var(--space-3)",
                  fontSize: "var(--font-size-lg)",
                  fontWeight: 600,
                  color: "var(--color-text)",
                }}
              >
                {t("traceability.linkedRequirements", "Linked Requirements")}
              </h3>
              {editLinkedReqIds.size === 0 ? (
                <p
                  style={{
                    color: "var(--color-text-muted)",
                    fontSize: "var(--font-size-sm)",
                    margin: 0,
                  }}
                >
                  {t("traceability.none", "None")}
                </p>
              ) : (
                <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
                  {[...editLinkedReqIds].map((rid) => {
                    const req = requirementsById[rid];
                    return (
                      <li
                        key={rid}
                        data-testid="testcase-linked-req-item"
                        style={{
                          padding: "var(--space-2) var(--space-3)",
                          marginBottom: "var(--space-2)",
                          background: "var(--color-surface-raised)",
                          borderRadius: "var(--radius-md)",
                          fontSize: "var(--font-size-sm)",
                          color: "var(--color-text)",
                        }}
                      >
                        → {req?.title ?? rid.slice(0, 8) + "…"}
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
