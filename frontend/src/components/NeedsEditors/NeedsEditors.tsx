import React, { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { SplitView } from '../SplitView/SplitView';
import { NeedList } from './NeedList';
import { NeedForm } from './NeedForm';
import { useNeedData } from './useNeedData';
import { useWorkspace } from '../../context/WorkspaceContext';
import { stakeholderNeedApi } from '../../api/stakeholder-need';
import { attributeVisibilityApi } from '../../api';

export default function NeedsEditors(): JSX.Element {
  const { id: selectedId } = useParams<{ id?: string }>();
  const navigate = useNavigate();
  const { activeWorkspace } = useWorkspace();
  const { needs, need, refresh } = useNeedData(selectedId);
  const [showCreate, setShowCreate] = useState(false);
  const [newTitle, setNewTitle] = useState('');

  const [attributeVisibility, setAttributeVisibility] = useState<Record<string, boolean>>({
    moscow_priority: true,
  });

  React.useEffect(() => {
    let isMounted = true;
    attributeVisibilityApi.list()
      .then((data) => {
        if (!isMounted) return;
        const vMap: Record<string, boolean> = {};
        data.filter(cfg => cfg.entity_type === 'stakeholder_need').forEach(cfg => {
          vMap[cfg.attribute_name] = cfg.is_visible;
        });
        if (!('moscow_priority' in vMap)) vMap['moscow_priority'] = true;
        setAttributeVisibility(vMap);
      })
      .catch(err => console.error('Failed to load attribute configs', err));
    return () => { isMounted = false; };
  }, []);

  const handleCreateNew = async () => {
    if (!activeWorkspace) return;
    if (!newTitle.trim()) return;
    try {
      const resp = await stakeholderNeedApi.create(activeWorkspace.id, { title: newTitle.trim() });
      setNewTitle('');
      setShowCreate(false);
      refresh();
      navigate(`/needs/${resp.id}`);
    } catch (e) {
      console.error(e);
      alert('Failed to create need');
    }
  };

  const handleSaved = () => {
    refresh();
  };

  const handleDeleted = () => {
    navigate('/needs');
    refresh();
  };

  return (
    <SplitView
      leftPanel={
        <NeedList 
          needs={needs} 
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
        <NeedForm 
          need={need} 
          onSaved={handleSaved} 
          onDeleted={handleDeleted}
          attributeVisibility={attributeVisibility}
        />
      }
      initialLeftWidth={350}
    />
  );
}
