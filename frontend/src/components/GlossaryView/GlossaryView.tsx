import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useWorkspace } from "../../context/WorkspaceContext";
import { glossaryApi } from "../../api/glossary";
import type { GlossaryTerm, LinkType } from "../../types";
import { PlusCircle, Search, Edit2, Trash2, Link2 } from "lucide-react";
import { RightSidebar } from "../shared/ArtifactInspector";
import { CreateTraceLinkDialog } from "../shared/CreateTraceLinkDialog/create-trace-link-dialog";
import { WorkflowStatusEditor } from "../WorkflowStatusEditor";

export default function GlossaryView(): JSX.Element {
  const { t } = useTranslation();
  const { activeWorkspace } = useWorkspace();
  const [terms, setTerms] = useState<GlossaryTerm[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState("");
  const [filterMode, setFilterMode] = useState<"workspace" | "global">("workspace");
  
  // Form state
  const [isFormOpen, setIsFormOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [formData, setFormData] = useState({
    term: "",
    definition: "",
    synonyms: "",
    abbreviation: ""
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
      const data = await glossaryApi.list(activeWorkspace.id);
      setTerms(data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadTerms();
  }, [activeWorkspace?.id]);

  // C10 (REQ-006): case-insensitive lookup of term text -> GlossaryTerm, used to
  // detect when a free-text synonym already matches an existing entry (i.e. is
  // "linked" in the normalized-text sense — no dedicated backend link field exists
  // for GlossaryTerm, see handleLinkSynonym below).
  const termsByName = useMemo(() => {
    const map = new Map<string, GlossaryTerm>();
    terms.forEach((t) => map.set(t.term.trim().toLowerCase(), t));
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
      await glossaryApi.update(term.id, { synonyms: newSynonyms });
      setLinkingSynonym(null);
      setSynonymLinkQuery("");
      loadTerms();
    } catch (err) {
      console.error("Failed to link synonym", err);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!activeWorkspace) return;

    try {
      const payload = {
        workspace_id: activeWorkspace.id,
        term: formData.term,
        definition: formData.definition,
        synonyms: formData.synonyms ? formData.synonyms.split(',').map(s => s.trim()).filter(Boolean) : [],
        abbreviation: formData.abbreviation
      };

      if (editingId) {
        await glossaryApi.update(editingId, payload);
      } else {
        await glossaryApi.create(payload);
      }
      
      setIsFormOpen(false);
      resetForm();
      loadTerms();
    } catch (err) {
      console.error("Failed to save term", err);
    }
  };

  const handleDelete = async (id: string) => {
    if (confirm(t("glossary.deleteConfirm"))) {
      try {
        await glossaryApi.delete(id);
        loadTerms();
      } catch (err) {
        console.error("Failed to delete term", err);
      }
    }
  };

  const handleEdit = (term: GlossaryTerm) => {
    setFormData({
      term: term.term,
      definition: term.definition,
      synonyms: term.synonyms ? term.synonyms.join(', ') : '',
      abbreviation: term.abbreviation || ''
    });
    setEditingId(term.id);
    setIsFormOpen(true);
  };

  const resetForm = () => {
    setFormData({ term: "", definition: "", synonyms: "", abbreviation: "" });
    setEditingId(null);
  };

  const filteredTerms = terms.filter(t => {
    const matchesSearch = t.term.toLowerCase().includes(searchTerm.toLowerCase()) || 
                          t.definition.toLowerCase().includes(searchTerm.toLowerCase());
    
    let matchesMode = true;
    if (filterMode === "workspace") {
      matchesMode = t.workspace_id === activeWorkspace?.id;
    } else if (filterMode === "global") {
      matchesMode = t.workspace_id === null;
    }

    return matchesSearch && matchesMode;
  });

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

  const inputStyle: React.CSSProperties = {
    width: "100%",
    padding: "var(--space-2) var(--space-3)",
    background: "var(--color-surface-raised)",
    border: "1px solid var(--color-border)",
    borderRadius: "var(--radius-md)",
    color: "var(--color-text)",
    boxSizing: "border-box",
  };

  if (!activeWorkspace) return <div style={{ padding: "var(--space-6)" }}>{t("workspace.selectFirst")}</div>;

  // Detail state: an existing term is being edited (REQ-L1-095).
  // GlossaryTerm has no `version` field, so currentVersion is undefined
  // — the VersionPanel in the inspector falls back to its empty state
  // (UI standards §5.1). The TracePanel (C9, REQ-006) renders whatever
  // /tracelinks/?artifact_id=<id> returns for this entry — note that
  // GlossaryTerm is not an Artifact subtype on the backend, so creating a
  // link from/to a glossary entry via CreateTraceLinkDialog will surface a
  // "source/target not found" error from the API until backend support for
  // glossary-as-artifact is added. The button and dialog are wired here so
  // the feature activates automatically once that backend support lands.
  const editingTerm = editingId ? terms.find((t) => t.id === editingId) : null;

  return (
    <div style={{ display: "flex", height: "100%", minHeight: 0, overflow: "hidden" }}>
      <div
        style={{
          flex: 1,
          minWidth: 0,
          padding: "var(--space-6)",
          display: "flex",
          flexDirection: "column",
          boxSizing: "border-box",
          overflowY: "auto",
        }}
      >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "var(--space-6)" }}>
        <h1 style={{ margin: 0, fontSize: "var(--font-size-2xl)", color: "var(--color-text)" }}>
          {t("nav.glossary", "Glossary")}
        </h1>
        <button onClick={() => { resetForm(); setIsFormOpen(true); }} style={btnStyle}>
          <PlusCircle size={18} />
          <span>{t("glossary.addTerm")}</span>
        </button>
      </div>

      {isFormOpen && (
        <form onSubmit={handleSubmit} style={{
          background: "var(--color-surface)",
          border: "1px solid var(--color-border)",
          borderRadius: "var(--radius-lg)",
          padding: "var(--space-5)",
          marginBottom: "var(--space-6)",
          boxShadow: "var(--shadow-card)",
          overflowY: "auto",
          maxHeight: "80vh",
          boxSizing: "border-box",
          width: "100%",
        }}>
          <h2 style={{ margin: "0 0 var(--space-4) 0", fontSize: "var(--font-size-lg)" }}>
            {editingId ? t("glossary.editTerm") : t("glossary.addTerm")}
          </h2>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--space-4)", marginBottom: "var(--space-4)" }}>
            <div>
              <label style={{ display: "block", marginBottom: "var(--space-1)", fontSize: "var(--font-size-sm)", fontWeight: 600 }}>
                {t("glossary.term")} *
              </label>
              <input required style={inputStyle} value={formData.term} onChange={e => setFormData({...formData, term: e.target.value})} disabled={!!editingId} />
            </div>
            <div>
              <label style={{ display: "block", marginBottom: "var(--space-1)", fontSize: "var(--font-size-sm)", fontWeight: 600 }}>
                {t("glossary.abbreviation")}
              </label>
              <input style={inputStyle} value={formData.abbreviation} onChange={e => setFormData({...formData, abbreviation: e.target.value})} />
            </div>
            <div style={{ gridColumn: "1 / -1" }}>
              <label style={{ display: "block", marginBottom: "var(--space-1)", fontSize: "var(--font-size-sm)", fontWeight: 600 }}>
                {t("glossary.definition")} *
              </label>
              <textarea required rows={3} style={{...inputStyle, resize: "vertical"}} value={formData.definition} onChange={e => setFormData({...formData, definition: e.target.value})} />
            </div>
            <div style={{ gridColumn: "1 / -1" }}>
              <label style={{ display: "block", marginBottom: "var(--space-1)", fontSize: "var(--font-size-sm)", fontWeight: 600 }}>
                {t("glossary.synonyms")}
              </label>
              <input style={inputStyle} value={formData.synonyms} onChange={e => setFormData({...formData, synonyms: e.target.value})} />
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
                onCreated={() => { setShowLinkDialog(false); loadTerms(); }}
                allowedTypes={["requirement", "architecture", "testcase"]}
                defaultLinkType={(activeWorkspace.default_link_type as LinkType) || 'derives-from'}
              />
            </div>
          )}

          <div style={{ display: "flex", justifyContent: "flex-end", gap: "var(--space-3)", flexWrap: "wrap" }}>
            <button type="button" onClick={() => setIsFormOpen(false)} style={{ ...btnStyle, backgroundColor: "transparent", border: "1px solid var(--color-border)", color: "var(--color-text)" }}>
              {t("actions.cancel", "Cancel")}
            </button>
            <button type="submit" style={btnStyle}>
              {t("actions.save", "Save")}
            </button>
          </div>
        </form>
      )}

      <div style={{ display: "flex", gap: "var(--space-4)", marginBottom: "var(--space-6)" }}>
        <div style={{ flex: 1, position: "relative" }}>
          <Search style={{ position: "absolute", left: "10px", top: "50%", transform: "translateY(-50%)", color: "var(--color-text-muted)" }} size={18} />
          <input
            style={{ ...inputStyle, paddingLeft: "36px" }}
            placeholder={t("glossary.searchPlaceholder")}
            value={searchTerm}
            onChange={e => setSearchTerm(e.target.value)}
          />
        </div>
        <div style={{ display: "flex", background: "var(--color-surface)", borderRadius: "var(--radius-md)", border: "1px solid var(--color-border)", overflow: "hidden" }}>
          {(["workspace", "global"] as const).map(mode => (
            <button
              key={mode}
              onClick={() => setFilterMode(mode)}
              style={{
                padding: "var(--space-2) var(--space-4)",
                border: "none",
                background: filterMode === mode ? "var(--color-primary-soft)" : "transparent",
                color: filterMode === mode ? "var(--color-primary)" : "var(--color-text)",
                fontWeight: filterMode === mode ? 600 : "normal",
                cursor: "pointer",
                borderRight: mode !== "global" ? "1px solid var(--color-border)" : "none",
              }}
            >
              {mode === "workspace" ? t("glossary.workspace") : t("glossary.global")}
            </button>
          ))}
        </div>
      </div>

      <div style={{ flex: 1, overflowY: "auto" }}>
        {loading ? (
          <div style={{ textAlign: "center", padding: "var(--space-8)", color: "var(--color-text-muted)" }}>{t("glossary.loading")}</div>
        ) : filteredTerms.length === 0 ? (
          <div style={{ textAlign: "center", padding: "var(--space-8)", color: "var(--color-text-muted)" }}>{t("glossary.noTerms")}</div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-4)" }}>
            {filteredTerms.map(term => (
              <div key={term.id} style={{
                background: "var(--color-surface)",
                border: "1px solid var(--color-border)",
                borderRadius: "var(--radius-md)",
                padding: "var(--space-4)",
                display: "flex",
                justifyContent: "space-between",
                alignItems: "flex-start",
              }}>
                <div>
                  <div style={{ display: "flex", alignItems: "center", gap: "var(--space-3)", marginBottom: "var(--space-2)" }}>
                    <h3 style={{ margin: 0, fontSize: "var(--font-size-lg)", color: "var(--color-text)" }}>{term.term}</h3>
                    {term.abbreviation && (
                      <span style={{ background: "var(--color-surface-raised)", border: "1px solid var(--color-border)", padding: "2px 6px", borderRadius: "var(--radius-sm)", fontSize: "var(--font-size-xs)" }}>
                        {term.abbreviation}
                      </span>
                    )}
                    {term.workspace_id === null && (
                      <span style={{ background: "var(--color-warning-soft)", color: "var(--color-warning)", padding: "2px 6px", borderRadius: "var(--radius-sm)", fontSize: "var(--font-size-xs)", fontWeight: 600 }}>
                        {t("glossary.global")}
                      </span>
                    )}
                  </div>
                  <p style={{ margin: 0, color: "var(--color-text-muted)", whiteSpace: "pre-wrap" }}>{term.definition}</p>
                  {term.synonyms && term.synonyms.length > 0 && (
                    <div style={{ marginTop: "var(--space-3)", fontSize: "var(--font-size-sm)", color: "var(--color-text-muted)", display: "flex", flexWrap: "wrap", alignItems: "center", gap: "var(--space-2)" }}>
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
                              <div style={{
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
                              }}>
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
                  )}
                </div>
                <div style={{ display: "flex", gap: "var(--space-2)" }}>
                  <button onClick={() => handleEdit(term)} style={{ background: "transparent", border: "none", color: "var(--color-text-muted)", cursor: "pointer", padding: "4px" }} title="Edit">
                    <Edit2 size={16} />
                  </button>
                  <button onClick={() => handleDelete(term.id)} style={{ background: "transparent", border: "none", color: "var(--color-danger)", cursor: "pointer", padding: "4px" }} title="Delete">
                    <Trash2 size={16} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
      </div>
      {/* Right pane: ArtifactInspector (REQ-L1-095, REQ-L2-RF-034).
          Glossary is an "Add" type (UI standards §11) — no prior inline
          sidebar existed. The inspector appears whenever a term is
          selected for editing (editingId set), which is the de-facto
          detail view in the current single-page layout. */}
      {editingTerm && (
        <RightSidebar
          kind="glossary"
          artifactId={editingTerm.id}
          currentVersion={undefined}
        />
      )}
    </div>
  );
}
