import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import type { Adr } from '../../types';
import { adrsApi } from '../../api/adrs';
import { VersionBadge } from '../shared/VersionBadge';
import { MarkdownPreview } from '../RequirementEditors/MarkdownPreview';

interface AdrFormProps {
  adr: Adr | null;
  onSaved: () => void;
  onDeleted: () => void;
}

const STATUS_OPTIONS = ['Draft', 'In Review', 'Approved', 'Rejected', 'Superseded'];

export function AdrForm({ adr, onSaved, onDeleted }: AdrFormProps): JSX.Element {
  const { t } = useTranslation();
  const [formData, setFormData] = useState<Partial<Adr>>({});
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    if (adr) setFormData({ ...adr });
    else setFormData({});
  }, [adr]);

  const handleChange = (field: keyof Adr, value: any) => {
    setFormData(prev => ({ ...prev, [field]: value }));
  };

  const handleSave = async () => {
    if (!adr) return;
    setIsSaving(true);
    try {
      await adrsApi.update(adr.id, {
        title: formData.title,
        description: formData.description,
        context: formData.context,
        consequences: formData.consequences,
        status: formData.status,
      });
      onSaved();
    } catch (err) {
      console.error(err);
      alert(t('adrs.saveFailed'));
    } finally {
      setIsSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!adr) return;
    if (window.confirm(t('adrs.deleteConfirm'))) {
      try {
        await adrsApi.delete(adr.id);
        onDeleted();
      } catch (err) {
        console.error(err);
      }
    }
  };

  if (!adr) {
    return (
      <p style={{ color: 'var(--color-text-muted)', fontSize: 'var(--font-size-lg)', textAlign: 'center', padding: 'var(--space-8)' }}>
        {t('adrs.selectAdr')}
      </p>
    );
  }

  const inputStyle: React.CSSProperties = {
    width: '100%', border: '1px solid var(--color-border)', borderRadius: 'var(--radius-md)',
    padding: 'var(--space-3)', fontFamily: 'var(--font-sans)', fontSize: 'var(--font-size-base)',
    marginBottom: 'var(--space-4)', color: 'var(--color-text)', background: 'var(--color-surface)',
    boxSizing: 'border-box',
  };
  const labelStyle: React.CSSProperties = {
    fontWeight: 500, color: 'var(--color-text)', display: 'block', marginBottom: 'var(--space-1)',
  };

  return (
    <div style={{
      background: 'var(--color-surface)', borderRadius: 'var(--radius-lg)', boxShadow: 'var(--shadow-card)',
      padding: 'var(--space-6)', flex: 1, display: 'flex', gap: 'var(--space-6)', alignItems: 'flex-start',
    }}>
      <div style={{ flex: 1 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--space-6)' }}>
          <div>
            
            <span style={{ fontSize: '0.8rem', padding: '4px 8px', borderRadius: '99px', background: 'var(--color-surface-raised)', border: '1px solid var(--color-border)', color: 'var(--color-text)' }}>
              {adr.status}
            </span>
            {adr.version && <VersionBadge version={adr.version} />}
          </div>
          <div style={{ display: 'flex', gap: 'var(--space-2)' }}>
            <button onClick={handleDelete} className="btn-danger">{t('actions.delete')}</button>
            <button onClick={handleSave} className="btn-primary" disabled={isSaving}>
              {isSaving ? t('actions.saving') : t('actions.save')}
            </button>
          </div>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
          <div>
            <label style={labelStyle}>{t('editor.title')}</label>
            <input type="text" value={formData.title || ''} onChange={(e) => handleChange('title', e.target.value)} style={inputStyle} />
          </div>
          <div style={{ marginBottom: 'var(--space-4)' }}>
            <label style={labelStyle}>{t('editor.description')}</label>
            <MarkdownPreview value={formData.description || ''} onChange={(v) => handleChange('description', v)} />
          </div>
          <div>
            <label style={labelStyle}>{t('adrs.context')}</label>
            <MarkdownPreview value={formData.context || ''} onChange={(v) => handleChange('context', v)} />
          </div>
          <div>
            <label style={labelStyle}>{t('adrs.consequences')}</label>
            <MarkdownPreview value={formData.consequences || ''} onChange={(v) => handleChange('consequences', v)} />
          </div>
          <div style={{ display: 'flex', gap: 'var(--space-4)' }}>
            <div style={{ flex: 1 }}>
              <label style={labelStyle}>{t('editor.status')}</label>
              <select value={formData.status || 'Draft'} onChange={(e) => handleChange('status', e.target.value)} style={inputStyle}>
                {STATUS_OPTIONS.map((opt) => <option key={opt} value={opt}>{opt}</option>)}
              </select>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
