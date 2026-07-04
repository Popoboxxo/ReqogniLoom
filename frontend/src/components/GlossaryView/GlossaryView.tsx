import React, { useEffect, useState } from "react";
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
    if (confirm(t("actions.confirmDelete"))) {
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

  const filteredTerms = terms.filter(t => 
    t.term.toLowerCase().includes(searchTerm.toLowerCase()) || 
    t.definition.toLowerCase().includes(searchTerm.toLowerCase())
  );

  if (!activeWorkspace) return <div>{t("workspace.selectFirst")}</div>;

  return (
    <div className="flex flex-col h-full bg-white dark:bg-gray-900 rounded-lg shadow-sm border border-gray-200 dark:border-gray-800 p-6">
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-2xl font-semibold text-gray-900 dark:text-gray-100">
          {t("glossary.title", "Project Glossary")}
        </h1>
        <button
          onClick={() => { resetForm(); setIsFormOpen(true); }}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 transition-colors"
        >
          <PlusCircle size={18} />
          <span>{t("glossary.addTerm", "Add Term")}</span>
        </button>
      </div>

      {isFormOpen && (
        <form onSubmit={handleSubmit} className="mb-8 bg-gray-50 dark:bg-gray-800 p-4 rounded-lg border border-gray-200 dark:border-gray-700">
          <h2 className="text-lg font-medium mb-4 text-gray-900 dark:text-white">
            {editingId ? t("glossary.editTerm", "Edit Term") : t("glossary.newTerm", "New Term")}
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
            <div>
              <label className="block text-sm font-medium mb-1 text-gray-700 dark:text-gray-300">{t("glossary.term", "Term")} *</label>
              <input
                required
                type="text"
                value={formData.term}
                onChange={e => setFormData({ ...formData, term: e.target.value })}
                className="w-full px-3 py-2 border rounded dark:bg-gray-700 dark:border-gray-600 dark:text-white"
                disabled={!!editingId} // Cannot change term name once created to preserve trace links easily
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1 text-gray-700 dark:text-gray-300">{t("glossary.abbreviation", "Abbreviation")}</label>
              <input
                type="text"
                value={formData.abbreviation}
                onChange={e => setFormData({ ...formData, abbreviation: e.target.value })}
                className="w-full px-3 py-2 border rounded dark:bg-gray-700 dark:border-gray-600 dark:text-white"
              />
            </div>
            <div className="md:col-span-2">
              <label className="block text-sm font-medium mb-1 text-gray-700 dark:text-gray-300">{t("glossary.definition", "Definition")} *</label>
              <textarea
                required
                rows={3}
                value={formData.definition}
                onChange={e => setFormData({ ...formData, definition: e.target.value })}
                className="w-full px-3 py-2 border rounded dark:bg-gray-700 dark:border-gray-600 dark:text-white"
              />
            </div>
            <div className="md:col-span-2">
              <label className="block text-sm font-medium mb-1 text-gray-700 dark:text-gray-300">{t("glossary.synonyms", "Synonyms (comma separated)")}</label>
              <input
                type="text"
                value={formData.synonyms}
                onChange={e => setFormData({ ...formData, synonyms: e.target.value })}
                className="w-full px-3 py-2 border rounded dark:bg-gray-700 dark:border-gray-600 dark:text-white"
                placeholder="e.g. Requirement, Spec"
              />
            </div>
          </div>
          <div className="flex justify-end gap-2">
            <button
              type="button"
              onClick={() => setIsFormOpen(false)}
              className="px-4 py-2 border rounded text-gray-600 hover:bg-gray-100 dark:text-gray-300 dark:border-gray-600 dark:hover:bg-gray-700"
            >
              {t("actions.cancel")}
            </button>
            <button
              type="submit"
              className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700"
            >
              {t("actions.save")}
            </button>
          </div>
        </form>
      )}

      <div className="relative mb-6">
        <Search className="absolute left-3 top-2.5 text-gray-400" size={18} />
        <input
          type="text"
          placeholder={t("glossary.search", "Search glossary...")}
          value={searchTerm}
          onChange={e => setSearchTerm(e.target.value)}
          className="w-full pl-10 pr-4 py-2 border rounded-lg dark:bg-gray-800 dark:border-gray-700 dark:text-white"
        />
      </div>

      {loading ? (
        <div className="text-center py-8">{t("loading")}</div>
      ) : (
        <div className="flex-1 overflow-auto">
          <div className="grid grid-cols-1 gap-4">
            {filteredTerms.map(term => (
              <div key={term.id} className="p-4 border rounded-lg hover:shadow-md transition-shadow dark:border-gray-700 bg-gray-50 dark:bg-gray-800/50 group">
                <div className="flex justify-between items-start">
                  <div>
                    <h3 className="text-lg font-bold text-gray-900 dark:text-white flex items-center gap-2">
                      {term.term}
                      {term.abbreviation && (
                        <span className="text-sm font-normal px-2 py-0.5 bg-gray-200 dark:bg-gray-700 rounded text-gray-600 dark:text-gray-300">
                          {term.abbreviation}
                        </span>
                      )}
                    </h3>
                    <p className="mt-2 text-gray-700 dark:text-gray-300 whitespace-pre-wrap">
                      {term.definition}
                    </p>
                    {term.synonyms && term.synonyms.length > 0 && (
                      <div className="mt-3 text-sm text-gray-500 dark:text-gray-400">
                        <strong>{t("glossary.synonyms", "Synonyms")}:</strong> {term.synonyms.join(', ')}
                      </div>
                    )}
                  </div>
                  <div className="flex gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                    <button
                      onClick={() => handleEdit(term)}
                      className="p-1.5 text-gray-500 hover:text-blue-600 hover:bg-blue-50 rounded dark:hover:bg-gray-700"
                      title={t("actions.edit")}
                    >
                      <Edit2 size={16} />
                    </button>
                    <button
                      onClick={() => handleDelete(term.id)}
                      className="p-1.5 text-gray-500 hover:text-red-600 hover:bg-red-50 rounded dark:hover:bg-gray-700"
                      title={t("actions.delete")}
                    >
                      <Trash2 size={16} />
                    </button>
                  </div>
                </div>
              </div>
            ))}
            
            {filteredTerms.length === 0 && (
              <div className="text-center py-8 text-gray-500">
                {t("glossary.noTerms", "No terms found.")}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
