import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { SplitView } from '../SplitView/SplitView';
import { RiskList } from './RiskList';
import { RiskForm } from './RiskForm';
import { RightSidebar } from '../shared/ArtifactInspector';
import type { VersionRef } from '../shared/ArtifactInspector';
import { CreateTraceLinkDialog } from '../shared/CreateTraceLinkDialog/create-trace-link-dialog';
import { useRiskData } from './useRiskData';
import { useWorkspace } from '../../context/WorkspaceContext';
import { risksApi } from '../../api/risks';

export default function RiskEditors(): JSX.Element {
  const { t } = useTranslation();
  const { id: selectedId } = useParams<{ id?: string }>();
  const navigate = useNavigate();
  const { activeWorkspace } = useWorkspace();
  const { items, item, isLoading, error, refresh } = useRiskData(selectedId);
  const [showCreate, setShowCreate] = useState(false);
  const [newTitle, setNewTitle] = useState('');
  const [createError, setCreateError] = useState<string | null>(null);
  const [showLinkDialog, setShowLinkDialog] = useState(false);

  const handleCreateNew = async () => {
    if (!activeWorkspace) return;
    if (!newTitle.trim()) return;
    setCreateError(null);
    try {
      const resp = await risksApi.create({ workspace_id: activeWorkspace.id, title: newTitle.trim() });
      setNewTitle(''); setShowCreate(false); refresh();
      navigate(`/risks/${resp.id}`);
    } catch (e) {
      console.error(e);
      const msg = (e as { error?: { message?: string } })?.error?.message ?? t('risks.createFailed');
      setCreateError(msg);
    }
  };

  const handleSaved = () => { refresh(); };
  const handleDeleted = () => { navigate('/risks'); refresh(); };

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
        <RiskList
          items={items} selectedId={selectedId}
          onCreateNew={() => { setCreateError(null); setShowCreate(true); }}
          showCreateForm={showCreate}
          setShowCreateForm={(show: boolean) => { if (!show) setCreateError(null); setShowCreate(show); }}
          newTitle={newTitle} setNewTitle={setNewTitle} onSubmitCreate={handleCreateNew}
          createError={createError}
        />
      }
      rightPanel={
        <div style={{ display: 'flex', height: '100%', minHeight: 0, gap: 'var(--space-3)' }}>
          <div style={{ flex: '1 1 auto', minWidth: 0, overflow: 'auto' }}>
            <RiskForm risk={item} onSaved={handleSaved} onDeleted={handleDeleted} />
            {item && activeWorkspace && (
              <>
                <button
                  type="button"
                  data-testid="risk-create-link-button"
                  onClick={() => setShowLinkDialog(true)}
                  style={{ marginTop: 'var(--space-3)', padding: 'var(--space-2) var(--space-4)', background: 'var(--color-primary)', color: 'white', border: 'none', borderRadius: 'var(--radius-md)', cursor: 'pointer', fontSize: 'var(--font-size-sm)' }}
                >
                  {t('traceability.create', 'Neue Verknüpfung')}
                </button>
                <CreateTraceLinkDialog
                  workspaceId={activeWorkspace.id}
                  sourceId={item.id}
                  isOpen={showLinkDialog}
                  onClose={() => setShowLinkDialog(false)}
                  onCreated={() => { setShowLinkDialog(false); refresh(); }}
                />
              </>
            )}
          </div>
          {item && (() => {
            const ver: VersionRef = { version: item.version, label: `v${item.version}`, createdAt: null, baselineIds: [] };
            return <RightSidebar kind="risk" artifactId={item.id} currentVersion={ver} />;
          })()}
        </div>
      }
      initialLeftWidth={350}
      moduleType="risks"
    />
  );
}
