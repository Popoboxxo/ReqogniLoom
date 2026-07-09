import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { SplitView } from '../SplitView/SplitView';
import { TestCaseList } from './TestCaseList';
import { TestCaseForm } from './TestCaseForm';
import { RightSidebar } from '../shared/ArtifactInspector';
import type { VersionRef } from '../shared/ArtifactInspector';
import { useTestCaseData } from './useTestCaseData';
import { useWorkspace } from '../../context/WorkspaceContext';
import { testcasesApi } from '../../api/testcases';

export default function TestCaseEditors(): JSX.Element {
  const { t } = useTranslation();
  const { id: selectedId } = useParams<{ id?: string }>();
  const navigate = useNavigate();
  const { activeWorkspace } = useWorkspace();
  const { items, item, isLoading, error, refresh } = useTestCaseData(selectedId);
  const [showCreate, setShowCreate] = useState(false);
  const [newTitle, setNewTitle] = useState('');
  const [createError, setCreateError] = useState<string | null>(null);

  const handleCreateNew = async () => {
    if (!activeWorkspace) return;
    if (!newTitle.trim()) return;
    setCreateError(null);
    try {
      const resp = await testcasesApi.create({ workspace_id: activeWorkspace.id, title: newTitle.trim() });
      setNewTitle(''); setShowCreate(false); refresh();
      navigate(`/testcases/${resp.id}`);
    } catch (e) {
      console.error(e);
      const msg = (e as { error?: { message?: string } })?.error?.message ?? t('testcases.createFailed');
      setCreateError(msg);
    }
  };

  const handleSaved = () => { refresh(); };
  const handleDeleted = () => { navigate('/testcases'); refresh(); };

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
        <TestCaseList
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
            <TestCaseForm testCase={item} onSaved={handleSaved} onDeleted={handleDeleted} />
          </div>
          {item && (() => {
            const ver: VersionRef = { version: item.version, label: `v${item.version}`, createdAt: null, baselineIds: [] };
            return <RightSidebar kind="testCase" artifactId={item.id} currentVersion={ver} />;
          })()}
        </div>
      }
      initialLeftWidth={350}
      moduleType="testcases"
    />
  );
}
