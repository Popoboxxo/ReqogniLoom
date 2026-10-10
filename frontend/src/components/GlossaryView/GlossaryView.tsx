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
 *
 * Structure after the code-health decomposition (pure behavior refactor):
 * list/detail/form/synonym rendering lives in the sibling components
 * (GlossaryTermList, GlossaryDetailPanel, GlossaryTermForm,
 * GlossarySynonyms), the filter/sort/synonym-lookup logic in
 * glossary-view-shared.ts — this file keeps the state wiring and composition.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useWorkspace } from "../../context/WorkspaceContext";
import { glossaryApi } from "../../api/glossary";
import type { GlossaryTerm, LinkType } from "../../types";
import { Link2 } from "lucide-react";
import { SplitView } from "../SplitView/SplitView";
import { PageHeader } from "../shared/PageHeader";
import { ListToolbar } from "../shared/ListToolbar";
import { EmptyState } from "../shared/EmptyState";
import { CreateTraceLinkDialog } from "../shared/CreateTraceLinkDialog/create-trace-link-dialog";
import { Dialog } from "../shared/Dialog";
import { WorkflowStatusEditor } from "../WorkflowStatusEditor";
import { extractErrorMessage } from "../../api/client";
import styles from "./GlossaryView.module.css";
import {
  GLOSSARY_LIFECYCLE_STATUSES,
  buildSynonymLinkIndex,
  filterTerms,
  sortTerms,
} from "./glossary-view-shared";
import type { FilterMode, SortKey } from "./glossary-view-shared";
import { GlossaryTermList } from "./GlossaryTermList";
import { GlossaryDetailPanel } from "./GlossaryDetailPanel";
import { GlossaryTermForm } from "./GlossaryTermForm";
import type { GlossaryFormData } from "./GlossaryTermForm";
import { GlossarySynonyms } from "./GlossarySynonyms";

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
  // #802: the create form now lives inside the shared <Dialog>, which moves the
  // initial focus itself — target the term field explicitly (the dialog's
  // first tabbable element is its close button otherwise).
  const termInputRef = useRef<HTMLInputElement | null>(null);
  const [formData, setFormData] = useState<GlossaryFormData>({
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

  // C10 (REQ-006): case-insensitive term-text index backing
  // resolveSynonymLink — see glossary-view-shared.ts.
  const termsByName = useMemo(() => buildSynonymLinkIndex(terms), [terms]);

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

  /**
   * Single close path for both the create dialog and the in-pane edit form
   * (#802) — a failed save keeps the form open with the message visible (UI
   * standards §12.11), so the error has to be cleared here, not on open only.
   */
  const closeForm = () => {
    setIsFormOpen(false);
    setFormError(null);
  };

  const resetForm = () => {
    setFormData({ term: "", definition: "", synonyms: "", abbreviation: "" });
    setEditingId(null);
  };

  const updateFormField = (field: keyof GlossaryFormData, value: string) => {
    setFormData((prev) => ({ ...prev, [field]: value }));
  };

  const resetFilters = (): void => {
    setSearchTerm("");
    setFilterMode("workspace");
    setStatusFilter("");
  };

  // C10: open the picker for (termId, index); clicking the open picker's
  // trigger again closes it and resets the picker query.
  const toggleSynonymLinking = (termId: string, index: number) => {
    const isLinking = linkingSynonym?.termId === termId && linkingSynonym?.index === index;
    setLinkingSynonym(isLinking ? null : { termId, index });
    setSynonymLinkQuery("");
  };

  const filteredTerms = useMemo(
    () =>
      sortTerms(
        filterTerms(terms, {
          searchTerm,
          filterMode,
          statusFilter,
          workspaceId: activeWorkspace?.id,
        }),
        sortKey,
      ),
    [terms, searchTerm, filterMode, statusFilter, sortKey, activeWorkspace?.id],
  );

  const hasActiveListControls = Boolean(searchTerm || filterMode !== "workspace" || statusFilter);

  if (!activeWorkspace) return <div className={styles.workspacePrompt}>{t("workspace.selectFirst")}</div>;

  const selectedTerm = selectedId ? terms.find((term) => term.id === selectedId) : null;

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
          actions={[{ label: t("glossary.addTerm"), prefixWithPlus: true, onClick: openCreateForm, testId: "glossary-empty-create" }]}
        />
      ) : filteredTerms.length === 0 ? (
        // ch. 13.3: "there is something, just not under this filter" — only a
        // filter/search reset, never a create action.
        <EmptyState variant="no-match" testId="glossary-no-match" onResetFilters={resetFilters} />
      ) : (
        <GlossaryTermList
          terms={filteredTerms}
          selectedId={selectedId}
          onSelect={handleSelect}
          onEdit={handleEdit}
          onDelete={handleDelete}
        />
      )}
    </div>
  );

  // ---------------------------------------------------------------------------
  // Right panel: create/edit form (relocated, unchanged behavior) OR
  // read-only detail (definition, synonyms, abbreviation, usages).
  //
  // #802: *creating* a term now happens in the shared <Dialog> primitive, like
  // every other artifact route's create action (Requirement/ADR/Risk/Issue/
  // TestCase) — same overlay, focus trap and Escape-to-close behaviour. Editing
  // an existing term keeps the in-pane form (the edit surface of the other
  // routes is their right-pane form too), which is why the fields below are
  // rendered from one shared markup source instead of being duplicated.
  // ---------------------------------------------------------------------------

  // #802: the create flow, rendered through the shared Dialog primitive. The
  // term field takes the initial focus explicitly — the trap's first tabbable
  // element would otherwise be the dialog's close button.
  const createDialog =
    isFormOpen && !editingId ? (
      <Dialog
        title={t("glossary.addTerm")}
        onClose={closeForm}
        testId="glossary-create-dialog"
        initialFocusRef={termInputRef}
      >
        <GlossaryTermForm
          formData={formData}
          editingId={editingId}
          errorMessage={formError}
          termInputRef={termInputRef}
          onSubmit={handleSubmit}
          onFieldChange={updateFormField}
          onClose={closeForm}
        />
      </Dialog>
    ) : null;

  const detailPanel = isFormOpen && editingId ? (
    <GlossaryTermForm
      formData={formData}
      editingId={editingId}
      heading={t("glossary.editTerm")}
      errorMessage={formError}
      termInputRef={termInputRef}
      onSubmit={handleSubmit}
      onFieldChange={updateFormField}
      onClose={closeForm}
    >
      {/* REQ-173: WorkflowEngine-driven status editor. Only for existing
          entries — a term being created has no artifact ID yet. Since #831 the
          Glossary API exposes `status` like every other artifact, so the
          freshly loaded value is passed as the pre-transitions badge fallback;
          the editor still resolves the authoritative state from the workflow
          endpoint. */}
      {editingId && (
        <div className={styles.marginBottom4}>
          <WorkflowStatusEditor
            artifactType="glossary"
            artifactId={editingId}
            currentStatus={terms.find((term) => term.id === editingId)?.status}
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
    </GlossaryTermForm>
  ) : selectedTerm ? (
    <GlossaryDetailPanel
      term={selectedTerm}
      onEdit={handleEdit}
      onDelete={handleDelete}
      synonyms={
        <GlossarySynonyms
          term={selectedTerm}
          terms={terms}
          synonymLinkIndex={termsByName}
          linkingSynonym={linkingSynonym}
          synonymLinkQuery={synonymLinkQuery}
          onToggleLinking={toggleSynonymLinking}
          onSynonymLinkQueryChange={setSynonymLinkQuery}
          onCancelLinking={() => setLinkingSynonym(null)}
          onLinkSynonym={handleLinkSynonym}
          onEditLinked={handleEdit}
        />
      }
    />
  ) : (
    <EmptyState
      variant="empty"
      testId="glossary-select-prompt"
      title={t("glossary.selectTitle", "Kein Begriff ausgewählt")}
      description={t("glossary.selectTerm", "Begriff aus der Liste auswählen, um Details anzuzeigen.")}
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

      {/* #802: sibling of the SplitView — <Dialog> portals into document.body
          itself, so the create form is not clipped by either pane. */}
      {createDialog}

      <div className={styles.splitViewWrap}>
        <SplitView leftPanel={listPanel} rightPanel={detailPanel} initialLeftWidth={380} moduleType="glossary" />
      </div>
    </div>
  );
}
