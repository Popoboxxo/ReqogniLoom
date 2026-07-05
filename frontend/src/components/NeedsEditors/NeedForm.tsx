import React, { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { Button } from '../Button/Button';
import type { StakeholderNeed, MoscowPriority } from '../../types';
import { stakeholderNeedApi } from '../../api/stakeholder-need';

interface NeedFormProps {
  need: StakeholderNeed | null;
  onSaved: () => void;
  onDeleted: () => void;
}

export function NeedForm({ need, onSaved, onDeleted }: NeedFormProps): JSX.Element {
  const { t } = useTranslation();
  const [formData, setFormData] = useState<Partial<StakeholderNeed>>({});
  const [isSaving, setIsSaving] = useState(false);

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
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--color-text-muted)' }}>
        Select a need from the list to view details
      </div>
    );
  }

  return (
    <div style={{ padding: 'var(--space-6)', maxWidth: '800px', margin: '0 auto' }}>
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
        </div>
        <div style={{ display: 'flex', gap: 'var(--space-2)' }}>
          <Button onClick={handleDelete} variant="danger" size="small">Delete</Button>
          <Button onClick={handleSave} variant="primary" size="small" disabled={isSaving}>
            {isSaving ? 'Saving...' : 'Save Changes'}
          </Button>
        </div>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
        <div>
          <label style={{ display: 'block', marginBottom: 'var(--space-2)', fontSize: '0.9rem', fontWeight: 500, color: 'var(--color-text-muted)' }}>
            Title
          </label>
          <input
            type="text"
            value={formData.title || ''}
            onChange={(e) => handleChange('title', e.target.value)}
            style={{
              width: '100%',
              padding: 'var(--space-3)',
              borderRadius: 'var(--radius-md)',
              border: '1px solid rgba(255,255,255,0.1)',
              background: 'rgba(0,0,0,0.2)',
              color: 'var(--color-text)',
              fontSize: '1.2rem',
              fontWeight: 600,
              outline: 'none',
            }}
          />
        </div>

        <div>
          <label style={{ display: 'block', marginBottom: 'var(--space-2)', fontSize: '0.9rem', fontWeight: 500, color: 'var(--color-text-muted)' }}>
            Description
          </label>
          <textarea
            value={formData.description || ''}
            onChange={(e) => handleChange('description', e.target.value)}
            rows={8}
            style={{
              width: '100%',
              padding: 'var(--space-3)',
              borderRadius: 'var(--radius-md)',
              border: '1px solid rgba(255,255,255,0.1)',
              background: 'rgba(0,0,0,0.2)',
              color: 'var(--color-text)',
              fontSize: '1rem',
              fontFamily: 'inherit',
              resize: 'vertical',
              outline: 'none',
            }}
          />
        </div>

        <div style={{ display: 'flex', gap: 'var(--space-4)' }}>
          <div style={{ flex: 1 }}>
            <label style={{ display: 'block', marginBottom: 'var(--space-2)', fontSize: '0.9rem', fontWeight: 500, color: 'var(--color-text-muted)' }}>
              Category
            </label>
            <input
              type="text"
              value={formData.category || ''}
              onChange={(e) => handleChange('category', e.target.value)}
              style={{
                width: '100%',
                padding: 'var(--space-3)',
                borderRadius: 'var(--radius-md)',
                border: '1px solid rgba(255,255,255,0.1)',
                background: 'rgba(0,0,0,0.2)',
                color: 'var(--color-text)',
                outline: 'none',
              }}
            />
          </div>

          <div style={{ flex: 1 }}>
            <label style={{ display: 'block', marginBottom: 'var(--space-2)', fontSize: '0.9rem', fontWeight: 500, color: 'var(--color-text-muted)' }}>
              MoSCoW Priority
            </label>
            <select
              value={formData.moscow_priority || ''}
              onChange={(e) => handleChange('moscow_priority', e.target.value || null)}
              style={{
                width: '100%',
                padding: 'var(--space-3)',
                borderRadius: 'var(--radius-md)',
                border: '1px solid rgba(255,255,255,0.1)',
                background: 'rgba(0,0,0,0.2)',
                color: 'var(--color-text)',
                outline: 'none',
                appearance: 'none',
              }}
            >
              <option value="">None</option>
              <option value="Must">Must</option>
              <option value="Should">Should</option>
              <option value="Could">Could</option>
              <option value="Won't">Won't</option>
            </select>
          </div>
        </div>
      </div>
    </div>
  );
}
