/**
 * ARCH-L1-001 ReactFrontend — RequirementEditors (COMP-RF-003)
 *
 * leaf_id: COMP-RF-003
 * req_id: REQ-L2-RF-003 (Requirements-Editor mit Inline-Editing und Markdown),
 * REQ-L3-RF003-001 (Inline-Editing — Title, Description, Category),
 * REQ-L3-RF003-002 (Workflow-State-Anzeige + Transition),
 * REQ-L3-RF003-003 (TraceabilityPanel),
 * REQ-L3-RF003-004 (Editor-Performance < 500ms),
 * REQ-L3-RF003-005 (Type-dependent mask rendering),
 * REQ-003 (skalierbare Listen-Toolbar — Suche/Filter/Sortierung)
 *
 * Interfaces implemented:
 * IF-RF-INT-001 ← NavigationShell activates
 * IF-RF-INT-002 ← I18nService via useTranslation
 * IF-RF-INT-003 ← artifact_id URL params
 * IF-RF-EXT-OUT-001 → GET/POST/PATCH/DELETE /api/v1/requirements/
 *
 * Refactored to use:
 * - SplitView component for resizable list/detail layout
 * - RequirementList (left panel) — searchable list with filtering
 * - RequirementForm (right panel) — type-dependent form with Moscow/Fibonacci/Verification fields
 * - EntityTypeProvider for context-aware field rendering
 */

import React, { useState, useCallback, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useRequirementData } from './useRequirementData';
import { useCreateRequirement, useDeleteRequirement } from '../../queries/requirements';
import { requirementsApi } from '../../api/requirements';
import { workspacesApi } from '../../api/workspaces';
import { useWorkspace } from '../../context/WorkspaceContext';
import { EntityTypeProvider } from '../../context/EntityTypeContext';
import { SplitView } from '../SplitView/SplitView';
import { RequirementList } from './RequirementList';
import { RequirementForm } from './RequirementForm';
import type { UUID, RequirementType } from '../../types';

/**
 * RequirementEditors — main view with SplitView (list | detail)
 */
export default function RequirementEditors(): JSX.Element {
  const { t } = useTranslation();
  const { id: selectedId } = useParams<{ id?: string }>();
  const navigate = useNavigate();
  const { activeWorkspace } = useWorkspace();
  const {
    requirements,
    requirement,
    upstreamLinks,
    downstreamLinks,
    linkedTitles,
    linkedRoutes,
    isLoading,
    error,
    refresh,
  } = useRequirementData(selectedId);

  const createRequirement = useCreateRequirement();
  const deleteRequirement = useDeleteRequirement();

  // Create form state
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [newTitle, setNewTitle] = useState('');
  const [isCreating, setIsCreating] = useState(false);

  // PDF export state
  const [isExportingPdf, setIsExportingPdf] = useState(false);

  // Split-view state for localStorage persistence
  const isDraggingRef = useRef(false);

  /**
   * Handle create new requirement.
   */
  const handleCreate = useCallback(async (): Promise<void> => {
    if (!activeWorkspace) return;
    const title = newTitle.trim() || t('editor.newRequirementTitle');
    setIsCreating(true);
    try {
      const created = await createRequirement.mutateAsync({
        workspace_id: activeWorkspace.id,
        title,
      });
      setShowCreateForm(false);
      setNewTitle('');
      navigate(`/requirements/${created.id}`);
    } catch (err: unknown) {
      console.error('Create failed:', err);
    } finally {
      setIsCreating(false);
    }
  }, [activeWorkspace, createRequirement, navigate, newTitle, t]);

  /**
   * Handle delete requirement with confirmation.
   */
  const handleDelete = useCallback(
    async (id: string): Promise<void> => {
      if (!activeWorkspace) return;
      if (!window.confirm(t('editor.deleteConfirm'))) return;
      try {
        await deleteRequirement.mutateAsync({ id, workspaceId: activeWorkspace.id });
        navigate('/requirements');
      } catch (err: unknown) {
        console.error('Delete failed:', err);
      }
    },
    [t, activeWorkspace, deleteRequirement, navigate]
  );

  /**
   * Handle PDF export of requirements.
   */
  const handleExportPdf = useCallback(async (): Promise<void> => {
    if (!activeWorkspace) return;
    setIsExportingPdf(true);
    try {
      const blob = await workspacesApi.downloadPdfReport(activeWorkspace.id);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `requirement_document_${activeWorkspace.id.slice(0, 8)}.pdf`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err: unknown) {
      console.error('PDF export failed:', err);
    } finally {
      setIsExportingPdf(false);
    }
  }, [activeWorkspace]);

  // Loading state
  if (isLoading) {
    return <p role="status">{t('loading')}</p>;
  }

  // Error state
  if (error) {
    return (
      <div role="alert">
        <p style={{ color: 'var(--color-danger)' }}>{error}</p>
        <button onClick={refresh}>{t('actions.reload')}</button>
      </div>
    );
  }

  /**
   * Left panel: Requirements list + toolbar
   */
  const leftPanel = (
    <div>
      {/* Toolbar: Export, Import, Create buttons */}
      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          justifyContent: 'space-between',
          alignItems: 'center',
          rowGap: 'var(--space-2)',
          marginBottom: 'var(--space-3)',
        }}
      >
        <h3
          style={{
            fontSize: 'var(--font-size-lg)',
            fontWeight: 600,
            margin: 0,
            color: 'var(--color-text)',
          }}
        >
          {t('nav.requirements')}
        </h3>
        <div style={{ display: 'flex', gap: 'var(--space-2)' }}>
          <button
            data-testid="export-pdf-btn"
            onClick={() => void handleExportPdf()}
            disabled={isExportingPdf || requirements.length === 0}
            style={{
              background: 'var(--color-surface)',
              color: 'var(--color-text)',
              border: '1px solid var(--color-border)',
              borderRadius: 'var(--radius-md)',
              padding: 'var(--space-2) var(--space-4)',
              fontSize: 'var(--font-size-sm)',
              cursor: isExportingPdf ? 'not-allowed' : 'pointer',
              opacity: isExportingPdf ? 0.6 : 1,
            }}
            title={t('editor.exportPdf', 'PDF')}
          >
            PDF
          </button>
          <button
            data-testid="csv-import-toolbar-btn"
            onClick={() => navigate('/import')}
            disabled={!activeWorkspace}
            style={{
              background: 'var(--color-surface)',
              color: 'var(--color-text)',
              border: '1px solid var(--color-border)',
              borderRadius: 'var(--radius-md)',
              padding: 'var(--space-2) var(--space-4)',
              fontSize: 'var(--font-size-sm)',
              cursor: 'pointer',
              opacity: !activeWorkspace ? 0.5 : 1,
            }}
          >
            {t('import.upload', 'CSV')}
          </button>
        </div>
      </div>

      {/* Create form */}
      {showCreateForm && (
        <form
          data-testid="create-req-form"
          onSubmit={(e) => {
            e.preventDefault();
            void handleCreate();
          }}
          style={{
            display: 'flex',
            flexDirection: 'column',
            gap: 'var(--space-2)',
            padding: 'var(--space-3)',
            marginBottom: 'var(--space-3)',
            background: 'var(--color-surface-raised)',
            border: '1px solid var(--color-border)',
            borderRadius: 'var(--radius-md)',
          }}
        >
          <label
            htmlFor="new-req-title"
            style={{
              fontSize: 'var(--font-size-sm)',
              fontWeight: 600,
              color: 'var(--color-text)',
            }}
          >
            {t('editor.title')}
          </label>
          <input
            id="new-req-title"
            data-testid="req-new-title-input"
            type="text"
            value={newTitle}
            onChange={(e) => setNewTitle(e.target.value)}
            autoFocus
            disabled={isCreating}
            placeholder={t('editor.newRequirementTitle')}
            style={{
              padding: 'var(--space-2) var(--space-3)',
              borderRadius: 'var(--radius-md)',
              border: '1px solid var(--color-border)',
              fontSize: 'var(--font-size-sm)',
              background: 'var(--color-surface)',
              color: 'var(--color-text)',
              fontFamily: 'var(--font-sans)',
              boxSizing: 'border-box',
            }}
          />
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 'var(--space-2)' }}>
            <button
              data-testid="req-new-cancel-btn"
              type="button"
              onClick={() => {
                setShowCreateForm(false);
                setNewTitle('');
              }}
              disabled={isCreating}
              style={{
                background: 'var(--color-surface)',
                color: 'var(--color-text)',
                border: '1px solid var(--color-border)',
                borderRadius: 'var(--radius-md)',
                padding: 'var(--space-2) var(--space-3)',
                fontSize: 'var(--font-size-sm)',
                cursor: isCreating ? 'not-allowed' : 'pointer',
                fontWeight: 600,
              }}
            >
              {t('actions.cancel')}
            </button>
            <button
              data-testid="req-new-save-btn"
              type="submit"
              disabled={isCreating}
              style={{
                background: 'var(--color-primary)',
                color: 'white',
                border: 'none',
                borderRadius: 'var(--radius-md)',
                padding: 'var(--space-2) var(--space-3)',
                fontSize: 'var(--font-size-sm)',
                cursor: isCreating ? 'not-allowed' : 'pointer',
                opacity: isCreating ? 0.6 : 1,
                fontWeight: 600,
              }}
            >
              {isCreating ? t('actions.saving') : t('actions.save')}
            </button>
          </div>
        </form>
      )}

      {/* Requirement list */}
      <RequirementList
        requirements={requirements}
        selectedId={selectedId}
        onSelect={(id) => navigate(`/requirements/${id}`)}
        onDelete={handleDelete}
        onCreateNew={() => setShowCreateForm(!showCreateForm)}
        isCreating={isCreating}
      />
    </div>
  );

  /**
   * Right panel: Requirement detail form
   */
  const rightPanel = requirement ? (
    <EntityTypeProvider
      entityType="requirement"
      entitySubType={(requirement.type || 'SyReq') as RequirementType}
      visibleFields={{
        moscow_priority: true,
        complexity_fibonacci: true,
        verification_method: true,
      }}
    >
      <RequirementForm
        requirement={requirement}
        upstreamLinks={upstreamLinks}
        downstreamLinks={downstreamLinks}
        linkedTitles={linkedTitles}
        linkedRoutes={linkedRoutes}
        requirements={requirements}
        workspaceId={activeWorkspace!.id}
        onSaved={refresh}
      />
    </EntityTypeProvider>
  ) : (
    <p
      style={{
        color: 'var(--color-text-muted)',
        fontSize: 'var(--font-size-lg)',
        textAlign: 'center',
        padding: 'var(--space-8)',
      }}
    >
      {t('editor.selectRequirement')}
    </p>
  );

  return (
    <SplitView
      leftPanel={leftPanel}
      rightPanel={rightPanel}
      leftMinWidth={260}
      leftMaxWidthPercent={70}
      moduleType="requirements"
      onDividerMove={(widthPixels) => {
        // localStorage is handled internally by SplitView
      }}
    />
  );
}
