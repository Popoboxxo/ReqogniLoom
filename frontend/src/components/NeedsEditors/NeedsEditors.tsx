import React, { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { SplitView } from '../SplitView/SplitView';
import { NeedList } from './NeedList';
import { NeedForm } from './NeedForm';
import { useNeedData } from './useNeedData';
import { useWorkspace } from '../../context/WorkspaceContext';
import { stakeholderNeedApi } from '../../api/stakeholder-need';

export default function NeedsEditors(): JSX.Element {
  const { id: selectedId } = useParams<{ id?: string }>();
  const navigate = useNavigate();
  const { activeWorkspace } = useWorkspace();
  const { needs, need, refresh } = useNeedData(selectedId);
  const [showCreate, setShowCreate] = useState(false);
  const [newTitle, setNewTitle] = useState('');

  const handleCreateNew = async () => {
    if (!activeWorkspace) return;
    const title = window.prompt("Enter Title for new Need:");
    if (!title) return;
    try {
      const resp = await stakeholderNeedApi.create(activeWorkspace.id, { title });
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
          onCreateNew={handleCreateNew} 
        />
      }
      rightPanel={
        <NeedForm 
          need={need} 
          onSaved={handleSaved} 
          onDeleted={handleDeleted} 
        />
      }
      initialLeftWidth={350}
    />
  );
}
