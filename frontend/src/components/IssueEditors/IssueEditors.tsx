import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { SplitView } from '../SplitView/SplitView';
import { IssueList } from './IssueList';
import { IssueForm } from './IssueForm';
import { RightSidebar } from '../shared/ArtifactInspector';
import { useIssueData } from './useIssueData';
import { useWorkspace } from '../../context/WorkspaceContext';
import { issuesApi } from '../../api/issues';

export default function IssueEditors(): JSX.Element {
  const { t } = useTranslation();
  const { id: selectedId } = useParams<{ id?: string }>();
  const navigate = useNavigate();
  const { activeWorkspace } = useWorkspace();
  const { items, item, refresh } = useIssueData(selectedId);
  const [showCreate, setShowCreate] = useState(false);
  const [newTitle, setNewTitle] = useState('');

  const handleCreateNew = async () => {
    if (!activeWorkspace) return;
    if (!newTitle.trim()) return;
    try {
      const resp = await issuesApi.create({ workspace_id: activeWorkspace.id, title: newTitle.trim() });
      setNewTitle(''); setShowCreate(false); refresh();
      navigate(`/issues/${resp.id}`);
    } catch (e) {
      console.error(e);
      alert(t('issues.createFailed'));
    }
  };

  const handleSaved = () => { refresh(); };
  const handleDeleted = () => { navigate('/issues'); refresh(); };

  return (
    <SplitView
      leftPanel={
        <IssueList
          items={items} selectedId={selectedId}
          onCreateNew={() => setShowCreate(true)}
          showCreateForm={showCreate} setShowCreateForm={setShowCreate}
          newTitle={newTitle} setNewTitle={setNewTitle} onSubmitCreate={handleCreateNew}
        />
      }
      rightPanel={
        <div style={{ display: 'flex', height: '100%', minHeight: 0, gap: 'var(--space-3)' }}>
          <div style={{ flex: '1 1 auto', minWidth: 0, overflow: 'auto' }}>
            <IssueForm issue={item} onSaved={handleSaved} onDeleted={handleDeleted} />
          </div>
          {item && <RightSidebar kind="issue" artifactId={item.id} currentVersion={undefined} />}
        </div>
      }
      initialLeftWidth={350}
    />
  );
}
