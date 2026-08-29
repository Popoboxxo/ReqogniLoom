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
import type { VersionRef } from "../shared/ArtifactInspector";
import { CreateTraceLinkDialog } from "../shared/CreateTraceLinkDialog/create-trace-link-dialog";
import { WorkflowStatusEditor } from "../WorkflowStatusEditor";
import { extractErrorMessage } from "../../api/client";
import styles from "./GlossaryView.module.css";

type FilterMode = "" | "workspace" | "global";

// GESAMTTEST_BERICHT_2026-08-21.md §6 "Glossar-Toolbar-Lücke": every sibling
// artifact list (Adr/Risk/Issue/...) offers a lifecycle-status filter and a
// sort dropdown via ListToolbar — Glossary only had the workspace/global
// filter. Mirrors ArchitectureEditors.tsx's ARCH_LIFECYCLE_STATUSES (same
// GlossaryTerm.lifecycle_status vocabulary, "deleted" excluded since deleted
// terms are already hidden from the loaded list — see the type's own
// comment in types/index.ts).
const GLOSSARY_LIFECYCLE_STATUSES = ["active", "outdated", "deprecated"] as const;

type SortKey = "default" | "term" | "status" | "updated";

function sortTerms(list: GlossaryTerm[], sortKey: SortKey): GlossaryTerm[] {
  const sorted = [...list];
  switch (sortKey) {
    case "term":
      sorted.sort((a, b) => a.term.localeCompare(b.term));
      break;
    case "status":
      sorted.sort(
        (a, b) =>
          (a.lifecycle_status ?? "active").localeCompare(b.lifecycle_status ?? "active") ||
          a.term.localeCompare(b.term),
      );
      break;
    case "updated":
      sorted.sort((a, b) => (b.updated_at || "").localeCompare(a.updated_at || ""));
      break;
  }
  return sorted;
}

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
  const [statusFilter, setStatusFilter] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("default");

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
    setStatusFilter("");
  };

  const filteredTerms = useMemo(() => {
    const filtered = terms.filter((term) => {
      const matchesSearch =
        term.term.toLowerCase().includes(searchTerm.toLowerCase()) ||
        term.definition.toLowerCase().includes(searchTerm.toLowerCase());

      let matchesMode = true;
      if (filterMode === "workspace") {
        matchesMode = term.workspace_id === activeWorkspace?.id;
      } else if (filterMode === "global") {
        matchesMode = term.workspace_id === null;
      }

      const matchesStatus = !statusFilter || (term.lifecycle_status ?? "active") === statusFilter;

      return matchesSearch && matchesMode && matchesStatus;
    });
    return sortTerms(filtered, sortKey);
  }, [terms, searchTerm, filterMode, statusFilter, sortKey, activeWorkspace?.id]);

  const hasActiveListControls = Boolean(searchTerm || filterMode !== "workspace" || statusFilter);

  if (!activeWorkspace) return <div className={styles.workspacePrompt}>{t("workspace.selectFirst")}</div>;

  const selectedTerm = selectedId ? terms.find((term) => term.id === selectedId) : null;

  function renderSynonyms(term: GlossaryTerm): JSX.Element | null {
    if (!term.synonyms || term.synonyms.length === 0) return null;
    return (
      <div className={styles.synonyms}>
        <strong>{t("glossary.synonymsLabel", "Synonyms")}:</strong>
        {term.synonyms.map((syn, idx) => {
          const linked = resolveSynonymLink(syn, term.id);
          const isLinking = linkingSynonym?.termId === term.id && linkingSynonym?.index === idx;
          return (
            <span key={`${term.id}-syn-${idx}`} className={styles.synonymWrap}>
              {linked ? (
                <button
                  type="button"
                  data-testid={`glossary-synonym-link-${term.id}-${idx}`}
                  onClick={() => handleEdit(linked)}
                  title={t("glossary.synonymLinkedTooltip", "Zu verlinktem Eintrag springen")}
                  className={styles.synonymLinkedBtn}
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
                    aria-label={`${t("glossary.linkSynonym", "Mit bestehendem Eintrag verlinken")}: ${syn}`}
                    className={styles.synonymLinkBtn}
                  >
                    <Link2 size={12} />
                  </button>
                </>
              )}
              {isLinking && (
                <div className={styles.synonymPicker}>
                  <input
                    autoFocus
                    data-testid={`glossary-synonym-search-${term.id}-${idx}`}
                    className={`${styles.input} ${styles.inputMarginBottom}`}
                    placeholder={t("glossary.searchPlaceholder")}
                    value={synonymLinkQuery}
                    onChange={(e) => setSynonymLinkQuery(e.target.value)}
                  />
                  <div className={styles.synonymPickerList}>
                    {terms
                      .filter((candidate) => candidate.id !== term.id && candidate.term.toLowerCase().includes(synonymLinkQuery.trim().toLowerCase()))
                      .slice(0, 20)
                      .map((candidate) => (
                        <button
                          key={candidate.id}
                          type="button"
                          data-testid={`glossary-synonym-option-${term.id}-${idx}-${candidate.id}`}
                          onClick={() => handleLinkSynonym(term, idx, candidate)}
                          className={styles.synonymPickerOption}
                        >
                          {candidate.term}
                        </button>
                      ))}
                    {terms.filter((candidate) => candidate.id !== term.id && candidate.term.toLowerCase().includes(synonymLinkQuery.trim().toLowerCase())).length === 0 && (
                      <p className={styles.synonymPickerEmpty}>
                        {t("glossary.noTerms")}
                      </p>
                    )}
                  </div>
                  <button
                    type="button"
                    data-testid={`glossary-synonym-cancel-${term.id}-${idx}`}
                    onClick={() => setLinkingSynonym(null)}
                    className={styles.synonymPickerCancel}
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
          {
            // GESAMTTEST_BERICHT_2026-08-21.md §6: status filter, matching
            // every sibling artifact list's ListToolbar.
            id: "status",
            allLabel: t("editor.allStatuses", "All Statuses"),
            value: statusFilter,
            options: GLOSSARY_LIFECYCLE_STATUSES.map((s) => ({
              value: s,
              label: t(`glossary.lifecycleStatus.${s}`, s),
            })),
            onChange: setStatusFilter,
          },
        ]}
        sortValue={sortKey}
        sortOptions={[
          { value: "default", label: t("editor.sortDefault", "Default") },
          { value: "term", label: t("editor.sortTitleAsc", "Title (A-Z)") },
          { value: "status", label: t("editor.sortStatus", "Status") },
          { value: "updated", label: t("editor.sortUpdatedDesc", "Recently Updated") },
        ]}
        onSortChange={(v) => setSortKey(v as SortKey)}
        sortLabel={t("editor.sortLabel", "Sort by")}
        countLabel={hasActiveListControls ? t("editor.filteredCount", { shown: filteredTerms.length, total: terms.length }) : String(terms.length)}
      />

      {loadError && (
        <p role="alert" data-testid="glossary-load-error" className={styles.alert}>
          {loadError}
        </p>
      )}
      {rowError && (
        <p role="alert" data-testid="glossary-row-error" className={styles.alert}>
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
        <div data-testid="glossary-rows" className={styles.rowsList}>
          {filteredTerms.map((term) => {
            const isSelected = term.id === selectedId;
            return (
              <div
                key={term.id}
                data-testid={`glossary-row-${term.id}`}
                role="button"
                tabIndex={0}
                aria-pressed={isSelected}
                onClick={() => handleSelect(term)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    handleSelect(term);
                  }
                }}
                className={`${styles.row} ${isSelected ? styles.rowSelected : styles.rowIdle}`}
              >
                <div className={styles.minWidth0}>
                  <div className={styles.rowTitleLine}>
                    <span className={styles.rowTerm}>{term.term}</span>
                    {term.abbreviation && (
                      <span className={styles.abbreviationBadge}>
                        {term.abbreviation}
                      </span>
                    )}
                    {term.workspace_id === null && (
                      <span className={styles.globalBadge}>
                        {t("glossary.global")}
                      </span>
                    )}
                  </div>
                  <p className={styles.rowDefinition}>
                    {term.definition}
                  </p>
                </div>
                <div className={styles.rowActions}>
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      handleEdit(term);
                    }}
                    className={`${styles.iconBtn} ${styles.iconBtnMuted}`}
                    // #741: icon-only row action — was an untranslated,
                    // aria-label-less `title`, i.e. no reliable accessible
                    // name at all. Names the term so the per-row buttons are
                    // distinguishable in a screen reader's element list.
                    title={t("actions.edit")}
                    aria-label={`${t("actions.edit")}: ${term.term}`}
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
                    className={`${styles.iconBtn} ${styles.iconBtnDanger}`}
                    title={t("actions.delete")}
                    aria-label={`${t("actions.delete")}: ${term.term}`}
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
      <h2 className={styles.formHeading}>
        {editingId ? t("glossary.editTerm") : t("glossary.addTerm")}
      </h2>
      <div className={styles.formGrid}>
        <div>
          <label className={styles.fieldLabel} htmlFor="glossary-term-input">
            {t("glossary.term")} *
          </label>
          <input id="glossary-term-input" required className={styles.input} value={formData.term} onChange={(e) => setFormData({ ...formData, term: e.target.value })} disabled={!!editingId} />
        </div>
        <div>
          <label className={styles.fieldLabel} htmlFor="glossary-abbreviation-input">
            {t("glossary.abbreviation")}
          </label>
          <input id="glossary-abbreviation-input" className={styles.input} value={formData.abbreviation} onChange={(e) => setFormData({ ...formData, abbreviation: e.target.value })} />
        </div>
        <div className={styles.formGridFullRow}>
          <label className={styles.fieldLabel} htmlFor="glossary-definition-input">
            {t("glossary.definition")} *
          </label>
          <textarea id="glossary-definition-input" required rows={3} className={`${styles.input} ${styles.textareaResize}`} value={formData.definition} onChange={(e) => setFormData({ ...formData, definition: e.target.value })} />
        </div>
        <div className={styles.formGridFullRow}>
          <label className={styles.fieldLabel} htmlFor="glossary-synonyms-input">
            {t("glossary.synonyms")}
          </label>
          <input id="glossary-synonyms-input" className={styles.input} value={formData.synonyms} onChange={(e) => setFormData({ ...formData, synonyms: e.target.value })} />
        </div>
      </div>

      {/* REQ-173: WorkflowEngine-driven status editor. Only for existing
          entries — a term being created has no artifact ID yet. GlossaryTerm
          has no status field, so currentStatus is undefined and the editor
          degrades to the workflow-driven state. */}
      {editingId && (
        <div className={styles.marginBottom4}>
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
        <div className={styles.marginBottom4}>
          <button
            type="button"
            data-testid="glossary-create-link-button"
            onClick={() => setShowLinkDialog(true)}
            className={`${styles.btn} ${styles.btnOutlinePrimary}`}
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
        <p role="alert" data-testid="glossary-form-error" className={styles.alert}>
          {formError}
        </p>
      )}

      <div className={styles.formActions}>
        <button
          type="button"
          data-testid="glossary-form-cancel"
          onClick={() => {
            setIsFormOpen(false);
            setFormError(null);
          }}
          className={`${styles.btn} ${styles.btnOutline}`}
        >
          {t("actions.cancel", "Cancel")}
        </button>
        <button type="submit" data-testid="glossary-form-save" className={styles.btn}>
          {t("actions.save", "Save")}
        </button>
      </div>
    </form>
  ) : selectedTerm ? (
    <div data-testid="glossary-detail" className={styles.detail}>
      <div className={styles.detailHeader}>
        <div>
          <div className={styles.detailTitleRow}>
            <h2 className={styles.detailTitle}>{selectedTerm.term}</h2>
            {selectedTerm.abbreviation && (
              <span className={styles.abbreviationBadge}>
                {selectedTerm.abbreviation}
              </span>
            )}
            {selectedTerm.workspace_id === null && (
              <span className={styles.globalBadgeDetail}>
                {t("glossary.global")}
              </span>
            )}
          </div>
        </div>
        <div className={styles.detailActions}>
          <button
            type="button"
            data-testid="glossary-detail-edit-btn"
            onClick={() => handleEdit(selectedTerm)}
            className={`${styles.btn} ${styles.btnOutline}`}
          >
            {t("actions.edit", "Bearbeiten")}
          </button>
          <button
            type="button"
            data-testid="glossary-detail-delete-btn"
            onClick={() => handleDelete(selectedTerm.id)}
            className={`${styles.btn} ${styles.btnOutlineDanger}`}
          >
            {t("actions.delete", "Löschen")}
          </button>
        </div>
      </div>

      <p className={styles.detailDefinition}>{selectedTerm.definition}</p>

      {renderSynonyms(selectedTerm)}

      {/* Usages + Versions/Diff (REQ-142, UI-59): trace links referencing this
          glossary entry (C9), plus the version history + field-level diff
          that the shared VersionPanel/DiffPanel already support for
          kind="glossary" — only wiring `currentVersion` was missing, which
          previously forced this panel into its undefined/degraded state. */}
      <div className={styles.usagesSection}>
        <h3 className={styles.usagesHeading}>
          {t("glossary.usages", "Verwendungen")}
        </h3>
        <RightSidebar
          kind="glossary"
          artifactId={selectedTerm.id}
          currentVersion={
            typeof selectedTerm.version === "number"
              ? ({
                  version: selectedTerm.version,
                  label: `v${selectedTerm.version}`,
                  createdAt: selectedTerm.updated_at ?? null,
                  baselineIds: [],
                } satisfies VersionRef)
              : undefined
          }
        />
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
    <div data-testid="glossary-view" className={styles.viewRoot}>
      {/* No `secondaryActions` here on purpose: the interview CTA that the
          other artifact routes carry is deliberately absent, because a
          glossary term is not an interview-capable artifact type — see
          INTERVIEW_ARTIFACT_TYPES in constants/interviewArtifactTypes.ts,
          which lists the eight types the interview engine can produce and
          does not include glossary terms. This is a real gap in the header's
          action row, not an oversight; please do not "fix" it by adding a
          CTA that would navigate to a `?start=` value the engine rejects. */}
      <PageHeader
        title={t("nav.glossary", "Glossary")}
        summary={t("glossary.summary", { count: terms.length, defaultValue: "{{count}} Begriffe" })}
        primaryAction={{
          label: t("glossary.addTerm"),
          prefixWithPlus: true,
          onClick: openCreateForm,
          testId: "create-glossary-term-btn",
        }}
      />

      <div className={styles.splitViewWrap}>
        <SplitView leftPanel={listPanel} rightPanel={detailPanel} initialLeftWidth={380} moduleType="glossary" />
      </div>
    </div>
  );
}
