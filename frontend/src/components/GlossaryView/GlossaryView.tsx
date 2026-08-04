/**
 * GlossaryView (issues #180/#181/#179 — UI-Konzept rollout remainder).
 *
 * Migrated from a single-column ad-hoc layout to the shared SplitView /
 * ListToolbar / EmptyState pattern used by AdrEditors, RiskEditors,
 * IssueEditors, TestCaseEditors etc. (UI_KONZEPT.md).
 *
 * - Left panel: flat list of glossary terms (no hierarchy — a term has no
 *   parent/child relation), driven by ListToolbar (search + workspace/global
 *   filter).
 * - Right panel: the create/edit form (relocated, unchanged behavior) when
 *   open, otherwise the read-only detail of the selected term (definition,
 *   synonyms incl. C10 synonym-linking, abbreviation, usages via the trace
 *   link inspector).
 *
 * All prior functionality is preserved: workspace/global filtering, search
 * across term + definition, inline create/edit form, C9 trace-link creation
 * for an existing entry, and C10 synonym-linking (free-text synonym ->
 * existing entry, normalized via PATCH since GlossaryTerm has no dedicated
 * synonym-link field on the backend).
 */
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useWorkspace } from "../../context/WorkspaceContext";
import { glossaryApi } from "../../api/glossary";
import type { GlossaryTerm, LinkType } from "../../types";
import { Edit2, Trash2, Link2 } from "lucide-react";
import { SplitView } from "../SplitView/SplitView";
import { PageHeader } from "../shared/PageHeader";
import { ListToolbar } from "../shared/ListToolbar";
import { EmptyState } from "../shared/EmptyState";
import { RightSidebar } from "../shared/ArtifactInspector";
import { CreateTraceLinkDialog } from "../shared/CreateTraceLinkDialog/create-trace-link-dialog";
import { WorkflowStatusEditor } from "../WorkflowStatusEditor";
import { extractErrorMessage } from "../../api/client";

type FilterMode = "" | "workspace" | "global";

const inputStyle: React.CSSProperties = {
  width: "100%",
  padding: "var(--space-2) var(--space-3)",
  background: "var(--color-surface-raised)",
  border: "1px solid var(--color-border)",
  borderRadius: "var(--radius-md)",
  color: "var(--color-text)",
  boxSizing: "border-box",
};

const btnStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: "var(--space-2)",
  padding: "var(--space-2) var(--space-4)",
  backgroundColor: "var(--color-primary)",
  color: "#fff",
  border: "none",
  borderRadius: "var(--radius-md)",
  cursor: "pointer",
  fontWeight: 600,
  fontSize: "var(--font-size-sm)",
};

export default function GlossaryView(): JSX.Element {
  const { t } = useTranslation();
  const { activeWorkspace } = useWorkspace();
  const [terms, setTerms] = useState<GlossaryTerm[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [rowError, setRowError] = useState<string | null>(null);
  const [searchTerm, setSearchTerm] = useState("");
  const [filterMode, setFilterMode] = useState<FilterMode>("workspace");

  // Detail-pane selection (view mode) — independent from `editingId` (the
  // edit-form target), so selecting a row for viewing never surfaces the
  // C9 create-link button (that only ever appears while actively editing).
  const [selectedId, setSelectedId] = useState<string | null>(null);

  // Form state
  const [isFormOpen, setIsFormOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [formData, setFormData] = useState({
    term: "",
    definition: "",
    synonyms: "",
    abbreviation: "",
  });

  // C9 (REQ-006): trace-link creation dialog for the selected glossary entry.
  const [showLinkDialog, setShowLinkDialog] = useState(false);

  // C10 (REQ-006): synonym-linking — the (termId, synonym index) currently
  // showing its "link to existing entry" picker, plus the picker's search query.
  const [linkingSynonym, setLinkingSynonym] = useState<{ termId: string; index: number } | null>(null);
  const [synonymLinkQuery, setSynonymLinkQuery] = useState("");

  const loadTerms = async () => {
    if (!activeWorkspace) return;
    try {
      setLoading(true);
      setLoadError(null);
      const data = await glossaryApi.list(activeWorkspace.id);
      setTerms(data);
    } catch (err) {
      console.error(err);
      setLoadError(extractErrorMessage(err) || t("glossary.loadFailed"));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadTerms();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeWorkspace?.id]);

  // C10 (REQ-006): case-insensitive lookup of term text -> GlossaryTerm, used to
  // detect when a free-text synonym already matches an existing entry (i.e. is
  // "linked" in the normalized-text sense — no dedicated backend link field exists
  // for GlossaryTerm, see handleLinkSynonym below).
  const termsByName = useMemo(() => {
    const map = new Map<string, GlossaryTerm>();
    terms.forEach((term) => map.set(term.term.trim().toLowerCase(), term));
    return map;
  }, [terms]);

  const resolveSynonymLink = (synonym: string, selfId: string): GlossaryTerm | null => {
    const match = termsByName.get(synonym.trim().toLowerCase());
    return match && match.id !== selfId ? match : null;
  };

  // C10 (REQ-006): "link" a synonym to an existing glossary entry. The backend
  // has no ID-based synonym-link field (GlossaryTerm.synonyms is a plain string[]
  // with no /tracelinks/ support — GlossaryTerm is not an Artifact subtype), so
  // linking is implemented by normalizing the synonym text to the target entry's
  // exact term string via the existing PATCH /glossary/{id}/ endpoint. Once the
  // strings match, resolveSynonymLink renders the synonym as a clickable link.
  const handleLinkSynonym = async (term: GlossaryTerm, index: number, target: GlossaryTerm) => {
    const newSynonyms = term.synonyms.map((s, i) => (i === index ? target.term : s));
    try {
      setRowError(null);
      await glossaryApi.update(term.id, { synonyms: newSynonyms });
      setLinkingSynonym(null);
      setSynonymLinkQuery("");
      loadTerms();
    } catch (err) {
      console.error("Failed to link synonym", err);
      setRowError(extractErrorMessage(err) || t("glossary.linkSynonymFailed"));
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!activeWorkspace) return;

    setFormError(null);
    try {
      const payload = {
        workspace_id: activeWorkspace.id,
        term: formData.term,
        definition: formData.definition,
        synonyms: formData.synonyms ? formData.synonyms.split(",").map((s) => s.trim()).filter(Boolean) : [],
        abbreviation: formData.abbreviation,
      };

      let saved: GlossaryTerm;
      if (editingId) {
        saved = await glossaryApi.update(editingId, payload);
      } else {
        saved = await glossaryApi.create(payload);
      }

      setIsFormOpen(false);
      resetForm();
      setSelectedId(saved.id);
      loadTerms();
    } catch (err) {
      console.error("Failed to save term", err);
      // Keep the form open on failure (UI standards §12.11) — the user's
      // input must not be lost and the form must not silently close.
      setFormError(extractErrorMessage(err) || t("glossary.saveFailed"));
    }
  };

  const handleDelete = async (id: string) => {
    if (confirm(t("glossary.deleteConfirm"))) {
      try {
        setRowError(null);
        await glossaryApi.delete(id);
        if (selectedId === id) setSelectedId(null);
        if (editingId === id) {
          setIsFormOpen(false);
          resetForm();
        }
        loadTerms();
      } catch (err) {
        console.error("Failed to delete term", err);
        setRowError(extractErrorMessage(err) || t("glossary.deleteFailed"));
      }
    }
  };

  const handleEdit = (term: GlossaryTerm) => {
    setFormData({
      term: term.term,
      definition: term.definition,
      synonyms: term.synonyms ? term.synonyms.join(", ") : "",
      abbreviation: term.abbreviation || "",
    });
    setEditingId(term.id);
    setSelectedId(term.id);
    setIsFormOpen(true);
  };

  const handleSelect = (term: GlossaryTerm) => {
    setSelectedId(term.id);
  };

  const openCreateForm = () => {
    resetForm();
    setIsFormOpen(true);
  };

  const resetForm = () => {
    setFormData({ term: "", definition: "", synonyms: "", abbreviation: "" });
    setEditingId(null);
  };

  const resetFilters = (): void => {
    setSearchTerm("");
    setFilterMode("workspace");
  };

  const filteredTerms = useMemo(
    () =>
      terms.filter((term) => {
        const matchesSearch =
          term.term.toLowerCase().includes(searchTerm.toLowerCase()) ||
          term.definition.toLowerCase().includes(searchTerm.toLowerCase());

        let matchesMode = true;
        if (filterMode === "workspace") {
          matchesMode = term.workspace_id === activeWorkspace?.id;
        } else if (filterMode === "global") {
          matchesMode = term.workspace_id === null;
        }

        return matchesSearch && matchesMode;
      }),
    [terms, searchTerm, filterMode, activeWorkspace?.id],
  );

  const hasActiveListControls = Boolean(searchTerm || filterMode !== "workspace");

  if (!activeWorkspace) return <div style={{ padding: "var(--space-6)" }}>{t("workspace.selectFirst")}</div>;

  const selectedTerm = selectedId ? terms.find((term) => term.id === selectedId) : null;

  function renderSynonyms(term: GlossaryTerm): JSX.Element | null {
    if (!term.synonyms || term.synonyms.length === 0) return null;
    return (
      <div
        style={{
          marginTop: "var(--space-3)",
          fontSize: "var(--font-size-sm)",
          color: "var(--color-text-muted)",
          display: "flex",
          flexWrap: "wrap",
          alignItems: "center",
          gap: "var(--space-2)",
        }}
      >
        <strong>{t("glossary.synonymsLabel", "Synonyms")}:</strong>
        {term.synonyms.map((syn, idx) => {
          const linked = resolveSynonymLink(syn, term.id);
          const isLinking = linkingSynonym?.termId === term.id && linkingSynonym?.index === idx;
          return (
            <span key={`${term.id}-syn-${idx}`} style={{ position: "relative", display: "inline-flex", alignItems: "center", gap: "2px" }}>
              {linked ? (
                <button
                  type="button"
                  data-testid={`glossary-synonym-link-${term.id}-${idx}`}
                  onClick={() => handleEdit(linked)}
                  title={t("glossary.synonymLinkedTooltip", "Zu verlinktem Eintrag springen")}
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    gap: "4px",
                    background: "var(--color-primary-soft)",
                    color: "var(--color-primary)",
                    border: "1px solid var(--color-primary)",
                    borderRadius: "var(--radius-full)",
                    padding: "1px 8px",
                    fontSize: "var(--font-size-xs)",
                    cursor: "pointer",
                  }}
                >
                  <Link2 size={12} />
                  {syn}
                </button>
              ) : (
                <>
                  <span>{syn}</span>
                  <button
                    type="button"
                    data-testid={`glossary-synonym-linkbtn-${term.id}-${idx}`}
                    onClick={() => {
                      setLinkingSynonym(isLinking ? null : { termId: term.id, index: idx });
                      setSynonymLinkQuery("");
                    }}
                    title={t("glossary.linkSynonym", "Mit bestehendem Eintrag verlinken")}
                    style={{ background: "transparent", border: "none", color: "var(--color-text-muted)", cursor: "pointer", padding: "0 2px", display: "inline-flex" }}
                  >
                    <Link2 size={12} />
                  </button>
                </>
              )}
              {isLinking && (
                <div
                  style={{
                    position: "absolute",
                    top: "100%",
                    left: 0,
                    zIndex: 10,
                    marginTop: "4px",
                    background: "var(--color-surface)",
                    border: "1px solid var(--color-border)",
                    borderRadius: "var(--radius-md)",
                    boxShadow: "var(--shadow-card)",
                    padding: "var(--space-2)",
                    width: "220px",
                  }}
                >
                  <input
                    autoFocus
                    data-testid={`glossary-synonym-search-${term.id}-${idx}`}
                    style={{ ...inputStyle, marginBottom: "var(--space-2)" }}
                    placeholder={t("glossary.searchPlaceholder")}
                    value={synonymLinkQuery}
                    onChange={(e) => setSynonymLinkQuery(e.target.value)}
                  />
                  <div style={{ maxHeight: "160px", overflowY: "auto" }}>
                    {terms
                      .filter((candidate) => candidate.id !== term.id && candidate.term.toLowerCase().includes(synonymLinkQuery.trim().toLowerCase()))
                      .slice(0, 20)
                      .map((candidate) => (
                        <button
                          key={candidate.id}
                          type="button"
                          data-testid={`glossary-synonym-option-${term.id}-${idx}-${candidate.id}`}
                          onClick={() => handleLinkSynonym(term, idx, candidate)}
                          style={{ display: "block", width: "100%", textAlign: "left", padding: "var(--space-1) var(--space-2)", background: "transparent", border: "none", cursor: "pointer", color: "var(--color-text)", fontSize: "var(--font-size-sm)" }}
                        >
                          {candidate.term}
                        </button>
                      ))}
                    {terms.filter((candidate) => candidate.id !== term.id && candidate.term.toLowerCase().includes(synonymLinkQuery.trim().toLowerCase())).length === 0 && (
                      <p style={{ margin: 0, padding: "var(--space-1) var(--space-2)", fontSize: "var(--font-size-sm)", color: "var(--color-text-muted)" }}>
                        {t("glossary.noTerms")}
                      </p>
                    )}
                  </div>
                  <button
                    type="button"
                    data-testid={`glossary-synonym-cancel-${term.id}-${idx}`}
                    onClick={() => setLinkingSynonym(null)}
                    style={{ marginTop: "var(--space-1)", background: "transparent", border: "none", color: "var(--color-text-muted)", cursor: "pointer", fontSize: "var(--font-size-xs)" }}
                  >
                    {t("actions.cancel", "Cancel")}
                  </button>
                </div>
              )}
            </span>
          );
        })}
      </div>
    );
  }

  // ---------------------------------------------------------------------------
  // Left panel: flat list (no hierarchy — glossary terms have no parent/child).
  // ---------------------------------------------------------------------------
  const listPanel = (
    <div data-testid="glossary-list">
      <ListToolbar
        testIdPrefix="glossary-list"
        searchValue={searchTerm}
        onSearchChange={setSearchTerm}
        searchPlaceholder={t("glossary.searchPlaceholder")}
        filters={[
          {
            id: "mode",
            allLabel: t("glossary.all", "Alle"),
            value: filterMode,
            options: [
              { value: "workspace", label: t("glossary.workspace", "Workspace") },
              { value: "global", label: t("glossary.global", "Global") },
            ],
            onChange: (v) => setFilterMode(v as FilterMode),
          },
        ]}
        countLabel={hasActiveListControls ? t("editor.filteredCount", { shown: filteredTerms.length, total: terms.length }) : null}
      />

      {loadError && (
        <p role="alert" data-testid="glossary-load-error" style={{ color: "var(--color-danger)", fontSize: "var(--font-size-sm)", marginBottom: "var(--space-4)" }}>
          {loadError}
        </p>
      )}
      {rowError && (
        <p role="alert" data-testid="glossary-row-error" style={{ color: "var(--color-danger)", fontSize: "var(--font-size-sm)", marginBottom: "var(--space-4)" }}>
          {rowError}
        </p>
      )}

      {loading ? (
        <EmptyState variant="loading" testId="glossary-loading" label={t("glossary.loading")} />
      ) : terms.length === 0 ? (
        // ch. 13.3: "there is nothing" — offer the create action.
        <EmptyState
          variant="empty"
          testId="glossary-empty"
          title={t("glossary.emptyTitle", "Noch keine Begriffe")}
          description={t("glossary.emptyDescription", "Glossarbegriffe halten Definitionen, Synonyme und Abkürzungen konsistent.")}
          actions={[{ label: t("glossary.addTerm"), onClick: openCreateForm, testId: "glossary-empty-create" }]}
        />
      ) : filteredTerms.length === 0 ? (
        // ch. 13.3: "there is something, just not under this filter" — only a
        // filter/search reset, never a create action.
        <EmptyState variant="no-match" testId="glossary-no-match" onResetFilters={resetFilters} />
      ) : (
        <div data-testid="glossary-rows" style={{ display: "flex", flexDirection: "column", gap: "var(--space-2)" }}>
          {filteredTerms.map((term) => {
            const isSelected = term.id === selectedId;
            return (
              <div
                key={term.id}
                data-testid={`glossary-row-${term.id}`}
                onClick={() => handleSelect(term)}
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  gap: "var(--space-2)",
                  padding: "var(--space-2) var(--space-3)",
                  background: isSelected ? "var(--color-surface-raised)" : "var(--color-surface)",
                  border: isSelected ? "1px solid var(--color-primary)" : "1px solid var(--color-border)",
                  borderRadius: "var(--radius-md)",
                  cursor: "pointer",
                }}
              >
                <div style={{ minWidth: 0 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: "var(--space-2)" }}>
                    <span style={{ fontWeight: 600, color: "var(--color-text)" }}>{term.term}</span>
                    {term.abbreviation && (
                      <span style={{ background: "var(--color-surface-raised)", border: "1px solid var(--color-border)", padding: "1px 6px", borderRadius: "var(--radius-sm)", fontSize: "var(--font-size-xs)" }}>
                        {term.abbreviation}
                      </span>
                    )}
                    {term.workspace_id === null && (
                      <span style={{ background: "var(--color-warning-soft)", color: "var(--color-warning)", padding: "1px 6px", borderRadius: "var(--radius-sm)", fontSize: "var(--font-size-xs)", fontWeight: 600 }}>
                        {t("glossary.global")}
                      </span>
                    )}
                  </div>
                  <p
                    style={{
                      margin: "2px 0 0",
                      fontSize: "var(--font-size-sm)",
                      color: "var(--color-text-muted)",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                    }}
                  >
                    {term.definition}
                  </p>
                </div>
                <div style={{ display: "flex", gap: "var(--space-1)", flexShrink: 0 }}>
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      handleEdit(term);
                    }}
                    style={{ background: "transparent", border: "none", color: "var(--color-text-muted)", cursor: "pointer", padding: "4px" }}
                    title="Edit"
                    data-testid={`glossary-edit-${term.id}`}
                  >
                    <Edit2 size={16} />
                  </button>
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      handleDelete(term.id);
                    }}
                    style={{ background: "transparent", border: "none", color: "var(--color-danger)", cursor: "pointer", padding: "4px" }}
                    title="Delete"
                    data-testid={`glossary-delete-${term.id}`}
                  >
                    <Trash2 size={16} />
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );

  // ---------------------------------------------------------------------------
  // Right panel: create/edit form (relocated, unchanged behavior) OR
  // read-only detail (definition, synonyms, abbreviation, usages).
  // ---------------------------------------------------------------------------
  const detailPanel = isFormOpen ? (
    <form onSubmit={handleSubmit} data-testid="glossary-form">
      <h2 style={{ margin: "0 0 var(--space-4) 0", fontSize: "var(--font-size-lg)" }}>
        {editingId ? t("glossary.editTerm") : t("glossary.addTerm")}
      </h2>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--space-4)", marginBottom: "var(--space-4)" }}>
        <div>
          <label style={{ display: "block", marginBottom: "var(--space-1)", fontSize: "var(--font-size-sm)", fontWeight: 600 }}>
            {t("glossary.term")} *
          </label>
          <input required style={inputStyle} value={formData.term} onChange={(e) => setFormData({ ...formData, term: e.target.value })} disabled={!!editingId} />
        </div>
        <div>
          <label style={{ display: "block", marginBottom: "var(--space-1)", fontSize: "var(--font-size-sm)", fontWeight: 600 }}>
            {t("glossary.abbreviation")}
          </label>
          <input style={inputStyle} value={formData.abbreviation} onChange={(e) => setFormData({ ...formData, abbreviation: e.target.value })} />
        </div>
        <div style={{ gridColumn: "1 / -1" }}>
          <label style={{ display: "block", marginBottom: "var(--space-1)", fontSize: "var(--font-size-sm)", fontWeight: 600 }}>
            {t("glossary.definition")} *
          </label>
          <textarea required rows={3} style={{ ...inputStyle, resize: "vertical" }} value={formData.definition} onChange={(e) => setFormData({ ...formData, definition: e.target.value })} />
        </div>
        <div style={{ gridColumn: "1 / -1" }}>
          <label style={{ display: "block", marginBottom: "var(--space-1)", fontSize: "var(--font-size-sm)", fontWeight: 600 }}>
            {t("glossary.synonyms")}
          </label>
          <input style={inputStyle} value={formData.synonyms} onChange={(e) => setFormData({ ...formData, synonyms: e.target.value })} />
        </div>
      </div>

      {/* REQ-173: WorkflowEngine-driven status editor. Only for existing
          entries — a term being created has no artifact ID yet. GlossaryTerm
          has no status field, so currentStatus is undefined and the editor
          degrades to the workflow-driven state. */}
      {editingId && (
        <div style={{ marginBottom: "var(--space-4)" }}>
          <WorkflowStatusEditor
            artifactType="glossary"
            artifactId={editingId}
            currentStatus={undefined}
            onTransitionComplete={loadTerms}
          />
        </div>
      )}

      {/* C9 (REQ-006): trace-link creation for the entry being edited.
          Only available for existing entries (editingId set) — a term
          being created has no artifact ID yet to link from. */}
      {editingId && activeWorkspace && (
        <div style={{ marginBottom: "var(--space-4)" }}>
          <button
            type="button"
            data-testid="glossary-create-link-button"
            onClick={() => setShowLinkDialog(true)}
            style={{ ...btnStyle, backgroundColor: "transparent", border: "1px solid var(--color-primary)", color: "var(--color-primary)" }}
          >
            <Link2 size={16} />
            <span>{t("traceability.create", "Neue Verknüpfung")}</span>
          </button>
          <CreateTraceLinkDialog
            workspaceId={activeWorkspace.id}
            sourceId={editingId}
            isOpen={showLinkDialog}
            onClose={() => setShowLinkDialog(false)}
            onCreated={() => {
              setShowLinkDialog(false);
              loadTerms();
            }}
            allowedTypes={["requirement", "architecture", "testcase"]}
            defaultLinkType={(activeWorkspace.default_link_type as LinkType) || "derives-from"}
          />
        </div>
      )}

      {formError && (
        <p role="alert" data-testid="glossary-form-error" style={{ color: "var(--color-danger)", fontSize: "var(--font-size-sm)", marginBottom: "var(--space-4)" }}>
          {formError}
        </p>
      )}

      <div style={{ display: "flex", justifyContent: "flex-end", gap: "var(--space-3)", flexWrap: "wrap" }}>
        <button
          type="button"
          onClick={() => {
            setIsFormOpen(false);
            setFormError(null);
          }}
          style={{ ...btnStyle, backgroundColor: "transparent", border: "1px solid var(--color-border)", color: "var(--color-text)" }}
        >
          {t("actions.cancel", "Cancel")}
        </button>
        <button type="submit" style={btnStyle}>
          {t("actions.save", "Save")}
        </button>
      </div>
    </form>
  ) : selectedTerm ? (
    <div data-testid="glossary-detail" style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "var(--space-3)" }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: "var(--space-3)" }}>
            <h2 style={{ margin: 0, fontSize: "var(--font-size-xl)", color: "var(--color-text)" }}>{selectedTerm.term}</h2>
            {selectedTerm.abbreviation && (
              <span style={{ background: "var(--color-surface-raised)", border: "1px solid var(--color-border)", padding: "2px 6px", borderRadius: "var(--radius-sm)", fontSize: "var(--font-size-xs)" }}>
                {selectedTerm.abbreviation}
              </span>
            )}
            {selectedTerm.workspace_id === null && (
              <span style={{ background: "var(--color-warning-soft)", color: "var(--color-warning)", padding: "2px 6px", borderRadius: "var(--radius-sm)", fontSize: "var(--font-size-xs)", fontWeight: 600 }}>
                {t("glossary.global")}
              </span>
            )}
          </div>
        </div>
        <div style={{ display: "flex", gap: "var(--space-2)", flexShrink: 0 }}>
          <button
            type="button"
            data-testid="glossary-detail-edit-btn"
            onClick={() => handleEdit(selectedTerm)}
            style={{ ...btnStyle, backgroundColor: "transparent", border: "1px solid var(--color-border)", color: "var(--color-text)" }}
          >
            {t("actions.edit", "Bearbeiten")}
          </button>
          <button
            type="button"
            data-testid="glossary-detail-delete-btn"
            onClick={() => handleDelete(selectedTerm.id)}
            style={{ ...btnStyle, backgroundColor: "transparent", border: "1px solid var(--color-danger)", color: "var(--color-danger)" }}
          >
            {t("actions.delete", "Löschen")}
          </button>
        </div>
      </div>

      <p style={{ margin: 0, color: "var(--color-text-muted)", whiteSpace: "pre-wrap" }}>{selectedTerm.definition}</p>

      {renderSynonyms(selectedTerm)}

      {/* Usages: trace links referencing this glossary entry (REQ-006 C9). */}
      <div style={{ marginTop: "var(--space-4)" }}>
        <h3 style={{ margin: "0 0 var(--space-2)", fontSize: "var(--font-size-base)", fontWeight: 600, color: "var(--color-text)" }}>
          {t("glossary.usages", "Verwendungen")}
        </h3>
        <RightSidebar kind="glossary" artifactId={selectedTerm.id} currentVersion={undefined} />
      </div>
    </div>
  ) : (
    <EmptyState
      variant="empty"
      testId="glossary-select-prompt"
      title={t("glossary.selectTitle", "Kein Begriff ausgewählt")}
      description={t("glossary.selectTerm", "Wähle einen Begriff aus der Liste, um Details anzuzeigen.")}
    />
  );

  return (
    <div data-testid="glossary-view" style={{ display: "flex", flexDirection: "column", height: "100%", minHeight: 0 }}>
      <PageHeader
        title={t("nav.glossary", "Glossary")}
        summary={t("glossary.summary", { count: terms.length, defaultValue: "{{count}} Begriffe" })}
        primaryAction={{
          label: t("glossary.addTerm"),
          onClick: openCreateForm,
          testId: "create-glossary-term-btn",
        }}
      />

      <div style={{ flex: "1 1 auto", minHeight: "60vh" }}>
        <SplitView leftPanel={listPanel} rightPanel={detailPanel} initialLeftWidth={380} moduleType="glossary" />
      </div>
    </div>
  );
}
