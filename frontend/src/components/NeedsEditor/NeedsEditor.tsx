/**
 * NeedsEditor — UI for Stakeholder Needs (Level 0) and AI Derivations.
 *
 * Implements the split-view for managing Bedarfe and executing AI Derivation
 * to System Requirements (REQ-L0-056).
 */
import React, { useState, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { useWorkspace } from "../../context/WorkspaceContext";
import { StakeholderNeed } from "../../types";
import { needsApi } from "../../api/needs";
import { NeedsDerivationPanel } from "./NeedsDerivationPanel";
import { MarkdownPreview } from "../RequirementEditors/MarkdownPreview";
import "./NeedsEditor.css";

export function NeedsEditor(): JSX.Element {
  const { t } = useTranslation();
  const { activeWorkspace } = useWorkspace();
  const [needs, setNeeds] = useState<StakeholderNeed[]>([]);
  const [selectedNeed, setSelectedNeed] = useState<StakeholderNeed | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    if (!activeWorkspace) return;
    setIsLoading(true);
    needsApi.list(activeWorkspace.id)
      .then((res) => {
        setNeeds(res.results || []);
      })
      .catch((err) => console.error("Failed to load needs", err))
      .finally(() => setIsLoading(false));
  }, [activeWorkspace]);

  if (!activeWorkspace) {
    return <div className="needs-editor-error">{t("errors.generic")}</div>;
  }

  return (
    <div className="needs-editor-layout">
      {/* Sidebar: List of Needs */}
      <aside className="needs-list-sidebar">
        <header className="needs-list-header">
          <h3>{t("needs.title", "Stakeholder Needs")}</h3>
          <button className="btn-primary" onClick={() => {/* TODO: Create Need */}}>+</button>
        </header>
        <div className="needs-list">
          {isLoading ? (
            <p>Loading...</p>
          ) : needs.length === 0 ? (
            <p className="no-needs">{t("needs.empty", "No needs found.")}</p>
          ) : (
            needs.map(need => (
              <div 
                key={need.id} 
                className={`need-list-item ${selectedNeed?.id === need.id ? 'active' : ''}`}
                onClick={() => setSelectedNeed(need)}
              >
                <div className="need-title">{need.title}</div>
                <div className="need-status">{need.status}</div>
              </div>
            ))
          )}
        </div>
      </aside>

      {/* Main Area: Editor */}
      <main className="needs-main-content">
        {selectedNeed ? (
          <div className="need-detail-view">
            <header className="need-detail-header">
              <h2>{selectedNeed.title}</h2>
              <span className={`badge status-${selectedNeed.status}`}>{selectedNeed.status}</span>
            </header>
            
            <section className="need-description-section">
              <h4>{t("needs.description", "Description")}</h4>
              <div className="markdown-container">
                <MarkdownPreview content={selectedNeed.description || "*No description provided*"} />
              </div>
            </section>
          </div>
        ) : (
          <div className="needs-empty-state">
            <p>{t("needs.selectPrompt", "Select a Stakeholder Need to view details or derive System Requirements.")}</p>
          </div>
        )}
      </main>

      {/* Right Sidebar: AI Derivation Panel */}
      {selectedNeed && (
        <aside className="needs-derivation-sidebar">
          <NeedsDerivationPanel need={selectedNeed} />
        </aside>
      )}
    </div>
  );
}
