import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { SplitView } from '../SplitView/SplitView';
import { RiskList } from './RiskList';
import { RiskForm } from './RiskForm';
import { RightSidebar } from '../shared/ArtifactInspector';
import type { VersionRef } from '../shared/ArtifactInspector';
import { useRiskData } from './useRiskData';
import { useWorkspace } from '../../context/WorkspaceContext';
import { risksApi } from '../../api/risks';

export default function RiskEditors(): JSX.Element {
  const { t } = useTranslation();
  const { id: selectedId } = useParams<{ id?: string }>();
  const navigate = useNavigate();
  const { activeWorkspace } = useWorkspace();
  const { items, item, refresh } = useRiskData(selectedId);
  const [showCreate, setShowCreate] = useState(false);
  const [newTitle, setNewTitle] = useState('');

  const handleCreateNew = async () => {
    if (!activeWorkspace) return;
    if (!newTitle.trim()) return;
    try {
      const resp = await risksApi.create({ workspace_id: activeWorkspace.id, title: newTitle.trim() });
      setNewTitle(''); setShowCreate(false); refresh();
      navigate(`/risks/${resp.id}`);
    } catch (e) {
      console.error(e);
      alert(t('risks.createFailed'));
    }
  };

  const handleSaved = () => { refresh(); };
  const handleDeleted = () => { navigate('/risks'); refresh(); };

  return (
    <SplitView
      leftPanel={
        <RiskList
          items={items} selectedId={selectedId}
          onCreateNew={() => setShowCreate(true)}
          showCreateForm={showCreate} setShowCreateForm={setShowCreate}
          newTitle={newTitle} setNewTitle={setNewTitle} onSubmitCreate={handleCreateNew}
        />
      }
      rightPanel={
        <div style={{ display: 'flex', height: '100%', minHeight: 0, gap: 'var(--space-3)' }}>
          <div style={{ flex: '1 1 auto', minWidth: 0, overflow: 'auto' }}>
            <RiskForm risk={item} onSaved={handleSaved} onDeleted={handleDeleted} />
          </div>
          {item && (() => {
            const ver: VersionRef = { version: item.version, label: `v${item.version}`, createdAt: null, baselineIds: [] };
            return <RightSidebar kind="risk" artifactId={item.id} currentVersion={ver} />;
          })()}
        </div>
      }
      initialLeftWidth={350}
    />
  );
}
