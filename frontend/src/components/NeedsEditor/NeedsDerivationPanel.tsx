import React, { useState, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { useWorkspace } from "../../context/WorkspaceContext";
import { StakeholderNeed } from "../../types";
import { needsApi } from "../../api/needs";

interface Props {
  need: StakeholderNeed;
}

interface Trace {
  target?: string;
  source?: string;
  type: string;
}

export function NeedsDerivationPanel({ need }: Props): JSX.Element {
  const { t } = useTranslation();
  const { activeWorkspace } = useWorkspace();
  const [outgoingTraces, setOutgoingTraces] = useState<Trace[]>([]);
  const [isDeriving, setIsDeriving] = useState(false);
  const [derivationStatus, setDerivationStatus] = useState<string | null>(null);
  
  const loadTraces = () => {
    needsApi.getTraces(need.id)
      .then(res => {
        setOutgoingTraces(res.outgoing_traces || []);
      })
      .catch(err => console.error("Failed to load traces", err));
  };

  useEffect(() => {
    loadTraces();
  }, [need.id]);

  const handleDerive = async () => {
    setIsDeriving(true);
    setDerivationStatus("Starting AI Derivation task...");
    try {
      const res = await needsApi.deriveRequirements(need.id);
      setDerivationStatus(`Task started: ${res.task_id}. Polling for completion...`);
      
      // Simulating polling logic for the async task.
      // In a real implementation, you would poll the LLM task endpoint here.
      setTimeout(() => {
        setDerivationStatus("System Requirements derived successfully!");
        setIsDeriving(false);
        loadTraces();
      }, 3000);
    } catch (err) {
      console.error(err);
      setDerivationStatus("Derivation failed.");
      setIsDeriving(false);
    }
  };

  return (
    <div className="needs-derivation-panel">
      <h3>{t("needs.derivation.title", "Derived System Requirements")}</h3>
      
      <div className="derivation-actions">
        <button 
          className="btn-magic" 
          onClick={handleDerive} 
          disabled={isDeriving}
        >
          ✨ {isDeriving ? t("needs.derivation.deriving", "Deriving...") : t("needs.derivation.action", "AI Derive Requirements")}
        </button>
        {derivationStatus && <p className="derivation-status">{derivationStatus}</p>}
      </div>

      <div className="derived-list">
        {outgoingTraces.length === 0 ? (
          <p className="no-derived">{t("needs.derivation.empty", "No System Requirements derived yet.")}</p>
        ) : (
          <ul className="trace-list">
            {outgoingTraces.map((trace, idx) => (
              <li key={idx} className="trace-item">
                <span className="trace-type badge">{trace.type}</span>
                <a href={`/requirements/${trace.target}`} className="trace-target">{trace.target}</a>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
