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
  const { items, item, refresh } = useAdrData(selectedId);
  const [showCreate, setShowCreate] = useState(false);
  const [newTitle, setNewTitle] = useState('');

  const handleCreateNew = async () => {
    if (!activeWorkspace) return;
    if (!newTitle.trim()) return;
    try {
      const resp = await adrsApi.create({ workspace_id: activeWorkspace.id, title: newTitle.trim() });
      setNewTitle('');
      setShowCreate(false);
      refresh();
      navigate(`/adrs/${resp.id}`);
    } catch (e) {
      console.error(e);
      alert(t('adrs.createFailed'));
    }
  };

  const handleSaved = () => { refresh(); };
  const handleDeleted = () => { navigate('/adrs'); refresh(); };

  return (
    <SplitView
      leftPanel={
        <AdrList
          items={items}
          selectedId={selectedId}
          onCreateNew={() => setShowCreate(true)}
          showCreateForm={showCreate}
          setShowCreateForm={setShowCreate}
          newTitle={newTitle}
          setNewTitle={setNewTitle}
          onSubmitCreate={handleCreateNew}
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
    />
  );
}
