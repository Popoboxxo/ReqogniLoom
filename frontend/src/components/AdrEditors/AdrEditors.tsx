import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { SplitView } from '../SplitView/SplitView';
import { AdrList } from './AdrList';
import { AdrForm } from './AdrForm';
import { RightSidebar } from '../shared/ArtifactInspector';
import type { VersionRef } from '../shared/ArtifactInspector';
import { useAdrData } from './useAdrData';
import { useWorkspace } from '../../context/WorkspaceContext';
import { adrsApi } from '../../api/adrs';

export default function AdrEditors(): JSX.Element {
  const { t } = useTranslation();
  const { id: selectedId } = useParams<{ id?: string }>();
  const navigate = useNavigate();
  const { activeWorkspace } = useWorkspace();
  const { items, item, isLoading, error, refresh } = useAdrData(selectedId);
  const [showCreate, setShowCreate] = useState(false);
  const [newTitle, setNewTitle] = useState('');
  const [createError, setCreateError] = useState<string | null>(null);

  const handleCreateNew = async () => {
    if (!activeWorkspace) return;
    if (!newTitle.trim()) return;
    setCreateError(null);
    try {
      const resp = await adrsApi.create({ workspace_id: activeWorkspace.id, title: newTitle.trim() });
      setNewTitle('');
      setShowCreate(false);
      refresh();
      navigate(`/adrs/${resp.id}`);
    } catch (e) {
      console.error(e);
      const msg = (e as { error?: { message?: string } })?.error?.message ?? t('adrs.createFailed');
      setCreateError(msg);
    }
  };

  const handleSaved = () => { refresh(); };
  const handleDeleted = () => { navigate('/adrs'); refresh(); };

  // Page-level loading / error states — only gate the full view on the
  // initial load (no data yet), keeping the list visible on detail reloads.
  if (isLoading && items.length === 0) {
    return (
      <p role="status" style={{ padding: 'var(--space-8)', color: 'var(--color-text-muted)' }}>
        {t('loading', 'Laden...')}
      </p>
    );
  }

  if (error && items.length === 0) {
    return (
      <div role="alert" style={{ padding: 'var(--space-8)' }}>
        <p style={{ color: 'var(--color-danger)', marginBottom: 'var(--space-4)' }}>
          {error.message}
        </p>
        <button className="btn-secondary" onClick={refresh}>
          {t('actions.reload', 'Erneut versuchen')}
        </button>
      </div>
    );
  }

  return (
    <SplitView
      leftPanel={
        <AdrList
          items={items}
          selectedId={selectedId}
          onCreateNew={() => { setCreateError(null); setShowCreate(true); }}
          showCreateForm={showCreate}
          setShowCreateForm={(show: boolean) => { if (!show) setCreateError(null); setShowCreate(show); }}
          newTitle={newTitle}
          setNewTitle={setNewTitle}
          onSubmitCreate={handleCreateNew}
          createError={createError}
        />
      }
      rightPanel={
        <div style={{ display: 'flex', height: '100%', minHeight: 0, gap: 'var(--space-3)' }}>
          <div style={{ flex: '1 1 auto', minWidth: 0, overflow: 'auto' }}>
            <AdrForm adr={item} onSaved={handleSaved} onDeleted={handleDeleted} />
          </div>
          {item && (() => {
            const ver: VersionRef = { version: item.version, label: `v${item.version}`, createdAt: null, baselineIds: [] };
            return <RightSidebar kind="adr" artifactId={item.id} currentVersion={ver} />;
          })()}
        </div>
      }
      initialLeftWidth={350}
      moduleType="adrs"
    />
  );
}
