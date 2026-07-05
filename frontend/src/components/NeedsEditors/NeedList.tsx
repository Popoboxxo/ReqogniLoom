import React, { useState } from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import type { StakeholderNeed } from '../../types';

interface NeedListProps {
  needs: StakeholderNeed[];
  selectedId?: string;
  onCreateNew: () => void;
}

export function NeedList({ needs, selectedId, onCreateNew }: NeedListProps): JSX.Element {
  const { t } = useTranslation();
  const [search, setSearch] = useState('');

  const filtered = needs.filter(n => 
    n.title.toLowerCase().includes(search.toLowerCase()) || 
    (n.uid && n.uid.toLowerCase().includes(search.toLowerCase()))
  );

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      height: '100%',
      background: 'rgba(255, 255, 255, 0.02)',
      backdropFilter: 'blur(10px)',
      borderRight: '1px solid rgba(255,255,255,0.05)',
    }}>
      <div style={{ padding: 'var(--space-4)', borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--space-3)' }}>
          <h2 style={{ margin: 0, fontSize: '1.2rem', fontWeight: 600, color: 'var(--color-text)' }}>
            Stakeholder Needs
          </h2>
          <button onClick={onCreateNew} className="btn-primary" style={{ padding: "4px 8px", fontSize: "0.85rem" }}>
            + {t('common.new', 'New')}
          </button>
        </div>
        <input
          type="text"
          placeholder={t('common.search', 'Search...')}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          style={{
            width: '100%',
            padding: 'var(--space-2) var(--space-3)',
            borderRadius: 'var(--radius-md)',
            border: '1px solid rgba(255,255,255,0.1)',
            background: 'rgba(0,0,0,0.2)',
            color: 'var(--color-text)',
            fontSize: 'var(--font-size-sm)',
            outline: 'none',
          }}
        />
      </div>
      
      <div style={{ flex: 1, overflowY: 'auto', padding: 'var(--space-2)' }}>
        {filtered.map(need => {
          const isActive = need.id === selectedId;
          return (
            <NavLink
              key={need.id}
              to={`/needs/${need.id}`}
              style={{
                display: 'block',
                padding: 'var(--space-3)',
                marginBottom: 'var(--space-2)',
                borderRadius: 'var(--radius-md)',
                textDecoration: 'none',
                background: isActive ? 'rgba(79, 110, 247, 0.15)' : 'rgba(255,255,255,0.03)',
                border: isActive ? '1px solid rgba(79, 110, 247, 0.3)' : '1px solid rgba(255,255,255,0.05)',
                transition: 'all 0.2s ease',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '4px' }}>
                <span style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)', fontFamily: 'monospace' }}>
                  {need.uid || 'NEW'}
                </span>
                <span style={{ 
                  fontSize: '0.7rem', 
                  padding: '2px 6px', 
                  borderRadius: '99px',
                  background: 'rgba(255,255,255,0.1)',
                  color: 'var(--color-text)',
                }}>
                  {need.status}
                </span>
              </div>
              <div style={{ 
                color: isActive ? 'var(--color-primary-light)' : 'var(--color-text)',
                fontSize: '0.9rem',
                fontWeight: 500,
              }}>
                {need.title}
              </div>
            </NavLink>
          );
        })}
        {filtered.length === 0 && (
          <div style={{ textAlign: 'center', padding: 'var(--space-4)', color: 'var(--color-text-muted)', fontSize: '0.9rem' }}>
            {t('common.noData', 'No needs found')}
          </div>
        )}
      </div>
    </div>
  );
}
