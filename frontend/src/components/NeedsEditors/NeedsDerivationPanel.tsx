import React, { useState, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { StakeholderNeed, TraceLink } from "../../types";
import { stakeholderNeedApi } from "../../api/stakeholder-need";
import { tracelinksApi } from "../../api/tracelinks";

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
  const [outgoingTraces, setOutgoingTraces] = useState<TraceLink[]>([]);
  const [isDeriving, setIsDeriving] = useState(false);
  const [derivationStatus, setDerivationStatus] = useState<string | null>(null);
  
  const loadTraces = () => {
    tracelinksApi.listForArtifact(need.workspace_id, need.artifact_id)
      .then(res => {
        setOutgoingTraces(res.results.filter(t => t.source_id === need.artifact_id));
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
      const res = await stakeholderNeedApi.deriveRequirements(need.id);
      setDerivationStatus(`Task started: ${res.task_id}. Polling for completion...`);
      
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
    <div style={{
      marginTop: 'var(--space-6)',
      padding: 'var(--space-4)',
      background: 'rgba(255, 255, 255, 0.03)',
      borderRadius: 'var(--radius-lg)',
      border: '1px solid var(--color-border)'
    }}>
      <h3 style={{ marginTop: 0, marginBottom: 'var(--space-4)' }}>
        {t("needs.derivation.title", "Derived System Requirements (AI)")}
      </h3>
      
      <div style={{ display: 'flex', gap: 'var(--space-4)', alignItems: 'center', marginBottom: 'var(--space-4)' }}>
        <button 
          className="btn-primary" 
          onClick={handleDerive} 
          disabled={isDeriving}
          style={{
            background: 'linear-gradient(135deg, #4f6ef7, #8e2de2)',
            border: 'none',
            padding: '8px 16px'
          }}
        >
          ✨ {isDeriving ? t("needs.derivation.deriving", "Deriving...") : t("needs.derivation.action", "AI Derive Requirements")}
        </button>
        {derivationStatus && (
          <span style={{ fontSize: '0.9rem', color: 'var(--color-text-muted)' }}>
            {derivationStatus}
          </span>
        )}
      </div>

      <div>
        {outgoingTraces.length === 0 ? (
          <p style={{ color: 'var(--color-text-muted)', fontSize: '0.9rem', margin: 0 }}>
            {t("needs.derivation.empty", "No System Requirements derived yet.")}
          </p>
        ) : (
          <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
            {outgoingTraces.map((trace, idx) => (
              <li key={idx} style={{
                background: 'var(--color-bg)',
                border: '1px solid var(--color-border)',
                padding: 'var(--space-3)',
                borderRadius: 'var(--radius-md)',
                display: 'flex',
                gap: 'var(--space-3)',
                alignItems: 'center'
              }}>
                <span style={{ 
                  fontSize: '0.75rem', 
                  background: 'rgba(255,255,255,0.1)', 
                  padding: '2px 6px', 
                  borderRadius: '4px' 
                }}>
                  {trace.link_type}
                </span>
                <a href={`/requirements/${trace.target_id}`} style={{ color: 'var(--color-primary)', textDecoration: 'none' }}>
                  {trace.target_id}
                </a>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
