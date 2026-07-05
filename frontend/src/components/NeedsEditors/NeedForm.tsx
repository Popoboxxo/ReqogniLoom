import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import type { StakeholderNeed } from '../../types';
import { stakeholderNeedApi } from '../../api/stakeholder-need';
import { TraceLinkPanel } from '../shared/TraceLinkPanel';
import { VersionBadge } from '../shared/VersionBadge';

interface NeedFormProps {
  need: StakeholderNeed | null;
  onSaved: () => void;
  onDeleted: () => void;
  attributeVisibility?: Record<string, boolean>;
  onNeedsChanged?: () => void;
}

export function NeedForm({ need, onSaved, onDeleted, attributeVisibility = {}, onNeedsChanged }: NeedFormProps): JSX.Element {
    const [formData, setFormData] = useState<Partial<StakeholderNeed>>({});
  const [isSaving, setIsSaving] = useState(false);
  const [isDeriving, setIsDeriving] = useState(false);
  const [derivationStatus, setDerivationStatus] = useState<string | null>(null);

  const handleDerive = async () => {
    if (!need) return;
    setIsDeriving(true);
    setDerivationStatus("Starting AI Derivation task...");
    try {
      const res = await stakeholderNeedApi.deriveRequirements(need.id);
      setDerivationStatus(`Task started: ${res.task_id}. Polling for completion...`);
      
      setTimeout(() => {
        setDerivationStatus("System Requirements derived successfully!");
        setIsDeriving(false);
        if (onNeedsChanged) onNeedsChanged();
      }, 3000);
    } catch (err) {
      console.error(err);
      setDerivationStatus("Derivation failed.");
      setIsDeriving(false);
    }
  };

  useEffect(() => {
    if (need) {
      setFormData({ ...need });
    } else {
      setFormData({});
    }
  }, [need]);

  const handleChange = (field: keyof StakeholderNeed, value: any) => {
    setFormData(prev => ({ ...prev, [field]: value }));
  };

  const handleSave = async () => {
    if (!need) return;
    setIsSaving(true);
    try {
      await stakeholderNeedApi.update(need.id, {
        title: formData.title,
        description: formData.description,
        category: formData.category,
        moscow_priority: formData.moscow_priority,
        status: formData.status,
      });
      onSaved();
    } catch (err) {
      console.error(err);
      alert('Failed to save');
    } finally {
      setIsSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!need) return;
    if (window.confirm('Delete this need?')) {
      try {
        await stakeholderNeedApi.delete(need.id);
        onDeleted();
      } catch (err) {
        console.error(err);
      }
    }
  };

  if (!need) {
    return (
      <p
        style={{
          color: 'var(--color-text-muted)',
          fontSize: 'var(--font-size-lg)',
          textAlign: 'center',
          padding: 'var(--space-8)',
        }}
      >
        Select a need from the list to view details
      </p>
    );
  }

  // Styles to match RequirementForm
  const inputStyle: React.CSSProperties = {
    width: '100%',
    border: '1px solid var(--color-border)',
    borderRadius: 'var(--radius-md)',
    padding: 'var(--space-3)',
    fontFamily: 'var(--font-sans)',
    fontSize: 'var(--font-size-base)',
    marginBottom: 'var(--space-4)',
    color: 'var(--color-text)',
    background: 'var(--color-surface)',
    boxSizing: 'border-box',
  };

  const labelStyle: React.CSSProperties = {
    fontWeight: 500,
    color: 'var(--color-text)',
    display: 'block',
    marginBottom: 'var(--space-1)',
  };

  return (
    <div
      style={{
        background: 'var(--color-surface)',
        borderRadius: 'var(--radius-lg)',
        boxShadow: 'var(--shadow-card)',
        padding: 'var(--space-6)',
        flex: 1,
        display: 'flex',
        gap: 'var(--space-6)',
        alignItems: 'flex-start',
      }}
    >
      <div style={{ flex: 1 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--space-6)' }}>
          <div>
            <span style={{ fontSize: '0.9rem', color: 'var(--color-text-muted)', fontFamily: 'monospace', marginRight: 'var(--space-2)' }}>
              {need.uid}
            </span>
            <span style={{ 
              fontSize: '0.8rem', 
              padding: '4px 8px', 
              borderRadius: '99px',
              background: 'rgba(255,255,255,0.1)',
              color: 'var(--color-text)',
            }}>
              {need.status}
            </span>
            {need.version && <VersionBadge version={need.version} />}
          </div>
          <div style={{ display: 'flex', gap: 'var(--space-2)' }}>
            <button onClick={handleDelete} className="btn-danger" style={{ padding: "4px 8px", fontSize: "0.85rem" }}>Delete</button>
            <button onClick={handleSave} className="btn-primary" style={{ padding: "4px 8px", fontSize: "0.85rem" }} disabled={isSaving}>
              {isSaving ? 'Saving...' : 'Save Changes'}
            </button>
          </div>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
          <div>
            <label style={labelStyle}>
              Title
            </label>
            <input
              type="text"
              value={formData.title || ''}
              onChange={(e) => handleChange('title', e.target.value)}
              style={inputStyle}
            />
          </div>

          <div>
            <label style={labelStyle}>
              Description
            </label>
            <textarea
              value={formData.description || ''}
              onChange={(e) => handleChange('description', e.target.value)}
              rows={8}
              style={{ ...inputStyle, resize: 'vertical' }}
            />
          </div>

          <div style={{ display: 'flex', gap: 'var(--space-4)' }}>
            <div style={{ flex: 1 }}>
              <label style={labelStyle}>
                Category
              </label>
              <input
                type="text"
                value={formData.category || ''}
                onChange={(e) => handleChange('category', e.target.value)}
                style={inputStyle}
              />
            </div>

            <div style={{ flex: 1 }}>
              {attributeVisibility.moscow_priority !== false && (
                <>
                  <label style={labelStyle}>
                    MoSCoW Priority
                  </label>
                  <select
                    value={formData.moscow_priority || ''}
                    onChange={(e) => handleChange('moscow_priority', e.target.value || null)}
                    style={inputStyle}
                  >
                    <option value="">None</option>
                    <option value="Must">Must</option>
                    <option value="Should">Should</option>
                    <option value="Could">Could</option>
                    <option value="Won't">Won't</option>
                  </select>
                </>
              )}
            </div>
          </div>
        </div>

        <TraceLinkPanel 
          workspaceId={need.workspace_id} 
          artifactId={need.artifact_id} 
          onDerive={handleDerive}
          isDeriving={isDeriving}
        />
        {derivationStatus && (
          <div style={{ marginTop: 'var(--space-2)', fontSize: '0.9rem', color: 'var(--color-text-muted)' }}>
            {derivationStatus}
          </div>
        )}
      </div>
    </div>
  );
}
