import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useWorkspace } from "../../context/WorkspaceContext";
import { glossaryApi } from "../../api/glossary";
import type { GlossaryTerm } from "../../types";
import { PlusCircle, Search, Edit2, Trash2 } from "lucide-react";

export default function GlossaryView(): JSX.Element {
  const { t } = useTranslation();
  const { activeWorkspace } = useWorkspace();
  const [terms, setTerms] = useState<GlossaryTerm[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState("");
  const [filterMode, setFilterMode] = useState<"all" | "workspace" | "global">("all");
  
  // Form state
  const [isFormOpen, setIsFormOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [formData, setFormData] = useState({
    term: "",
    definition: "",
    synonyms: "",
    abbreviation: ""
  });

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

  return (
    <div style={{ padding: "var(--space-6)", height: "100%", display: "flex", flexDirection: "column", boxSizing: "border-box" }}>
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
          <div style={{ display: "flex", justifyContent: "flex-end", gap: "var(--space-3)" }}>
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
          {(["all", "workspace", "global"] as const).map(mode => (
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
              {mode === "all" ? t("glossary.all") : mode === "workspace" ? t("glossary.workspace") : t("glossary.global")}
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
                    <div style={{ marginTop: "var(--space-3)", fontSize: "var(--font-size-sm)", color: "var(--color-text-muted)" }}>
                      <strong>Synonyms:</strong> {term.synonyms.join(', ')}
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
  );
}
