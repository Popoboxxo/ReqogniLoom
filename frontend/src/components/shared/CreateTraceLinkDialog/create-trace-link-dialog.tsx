/**
 * CreateTraceLinkDialog — Unified modal dialog for creating trace links (REQ-005).
 *
 * leaf_id: COMP-RF-CTL-001
 * req_id:  REQ-005 (unified trace-link creation dialog)
 *
 * Replaces separate inline forms in ArchitectureEditors, AdrEditors and
 * TraceabilityView. Features:
 *   - Search field: client-side filtering of element list by title
 *   - Element type filter: tabs to narrow by artifact type
 *   - Element list: shows resolved titles (target_title from REQ-002 API fix)
 *   - Link type selector: all backend link types
 *   - Consistent modal design: same overlay layout in every view
 *   - Optional sourceId: when absent, a source picker (select) is shown too
 */

import React, {
  useState,
  useEffect,
  useMemo,
  useCallback,
} from 'react';
import { useTranslation } from 'react-i18next';
import { requirementsApi } from '../../../api/requirements';
import { architectureApi } from '../../../api/architecture';
import { testcasesApi } from '../../../api/testcases';
import { adrsApi } from '../../../api/adrs';
import { risksApi } from '../../../api/risks';
import { issuesApi } from '../../../api/issues';
import { tracelinksApi } from '../../../api/tracelinks';
import { ALL_LINK_TYPES, getLinkTypeLabel } from '../../../constants/traceLinkLabels';
import type { LinkType } from '../../../types';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type ArtifactTypeKey = 'all' | 'requirement' | 'architecture' | 'testcase' | 'adr' | 'risk' | 'issue';

interface TargetElement {
  id: string;
  title: string;
  artifactType: ArtifactTypeKey;
}

export interface CreateTraceLinkDialogProps {
  /** Workspace to load elements from. */
  workspaceId: string;
  /**
   * Source artifact ID (will be excluded from the target list).
   * When omitted, a source picker (select + search) is shown above the
   * target picker — use this in global views like TraceabilityView.
   */
  sourceId?: string;
  /** Controls dialog visibility. */
  isOpen: boolean;
  /** Called when the user closes the dialog without creating. */
  onClose: () => void;
  /** Called after a trace link has been successfully created. */
  onCreated: () => void;
  /** Optional: restrict which artifact types appear in the target list. */
  allowedTypes?: ArtifactTypeKey[];
  /** Optional: pre-selected link type (defaults to "derives-from"). */
  defaultLinkType?: LinkType;
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const overlayStyle: React.CSSProperties = {
  position: 'fixed',
  inset: 0,
  background: 'rgba(0, 0, 0, 0.45)',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  zIndex: 1000,
};

const dialogStyle: React.CSSProperties = {
  background: 'var(--color-surface)',
  borderRadius: 'var(--radius-lg)',
  boxShadow: 'var(--shadow-md)',
  width: '100%',
  maxWidth: '560px',
  maxHeight: '90vh',
  display: 'flex',
  flexDirection: 'column',
  overflow: 'hidden',
};

const headerStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  padding: 'var(--space-4) var(--space-5)',
  borderBottom: '1px solid var(--color-border)',
};

const bodyStyle: React.CSSProperties = {
  padding: 'var(--space-4) var(--space-5)',
  overflowY: 'auto',
  flex: 1,
  display: 'flex',
  flexDirection: 'column',
  gap: 'var(--space-3)',
};

const footerStyle: React.CSSProperties = {
  display: 'flex',
  justifyContent: 'flex-end',
  gap: 'var(--space-2)',
  padding: 'var(--space-4) var(--space-5)',
  borderTop: '1px solid var(--color-border)',
};

const inputStyle: React.CSSProperties = {
  width: '100%',
  padding: 'var(--space-2) var(--space-3)',
  borderRadius: 'var(--radius-md)',
  border: '1px solid var(--color-border)',
  fontSize: 'var(--font-size-sm)',
  background: 'var(--color-surface)',
  color: 'var(--color-text)',
  boxSizing: 'border-box',
  fontFamily: 'var(--font-sans)',
};

const labelStyle: React.CSSProperties = {
  fontWeight: 600,
  display: 'block',
  marginBottom: 'var(--space-1)',
  color: 'var(--color-text)',
  fontSize: 'var(--font-size-sm)',
};

const elementListStyle: React.CSSProperties = {
  maxHeight: '200px',
  overflowY: 'auto',
  border: '1px solid var(--color-border)',
  borderRadius: 'var(--radius-md)',
  background: 'var(--color-surface)',
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const ALL_FILTER_TYPES: ArtifactTypeKey[] = [
  'all',
  'requirement',
  'architecture',
  'testcase',
  'adr',
  'risk',
  'issue',
];

/** Map artifact type key to i18n label key. */
const TYPE_LABEL_KEYS: Record<ArtifactTypeKey, string> = {
  all: 'createTraceLinkDialog.typeAll',
  requirement: 'createTraceLinkDialog.typeRequirement',
  architecture: 'createTraceLinkDialog.typeArchitecture',
  testcase: 'createTraceLinkDialog.typeTestCase',
  adr: 'createTraceLinkDialog.typeAdr',
  risk: 'createTraceLinkDialog.typeRisk',
  issue: 'createTraceLinkDialog.typeIssue',
};

/** Map artifact type key to a short display badge label. */
const TYPE_DISPLAY_LABELS: Record<ArtifactTypeKey, string> = {
  all: 'All',
  requirement: 'REQ',
  architecture: 'ARCH',
  testcase: 'TC',
  adr: 'ADR',
  risk: 'RISK',
  issue: 'ISSUE',
};

// ---------------------------------------------------------------------------
// Sub-component: ElementPicker
// ---------------------------------------------------------------------------

interface ElementPickerProps {
  /** All available elements (already filtered by allowedTypes at parent level). */
  elements: TargetElement[];
  /** Whether elements are still loading. */
  isLoading: boolean;
  /** Currently selected element ID. */
  selectedId: string;
  /** Called when the user selects an element. */
  onSelect: (id: string) => void;
  /** ID prefix for data-testid attributes. */
  testIdPrefix: string;
  /** Allow all types or restrict. */
  visibleTypeFilters: ArtifactTypeKey[];
}

function ElementPicker({
  elements,
  isLoading,
  selectedId,
  onSelect,
  testIdPrefix,
  visibleTypeFilters,
}: ElementPickerProps): JSX.Element {
  const { t } = useTranslation();
  const [search, setSearch] = useState('');
  const [typeFilter, setTypeFilter] = useState<ArtifactTypeKey>('all');

  const filtered = useMemo<TargetElement[]>(() => {
    let list = elements;
    if (typeFilter !== 'all') {
      list = list.filter((el) => el.artifactType === typeFilter);
    }
    const q = search.trim().toLowerCase();
    if (q) {
      list = list.filter((el) => el.title.toLowerCase().includes(q));
    }
    return list;
  }, [elements, typeFilter, search]);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
      {/* Search input */}
      <input
        type="text"
        data-testid={`${testIdPrefix}-search`}
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        placeholder={t('createTraceLinkDialog.searchPlaceholder', 'Filter by title…')}
        style={inputStyle}
        aria-label={t('createTraceLinkDialog.searchLabel', 'Search elements')}
      />

      {/* Type filter tabs */}
      {visibleTypeFilters.length > 1 && (
        <div
          role="group"
          aria-label={t('createTraceLinkDialog.typeFilterLabel', 'Filter by type')}
          style={{ display: 'flex', gap: 'var(--space-1)', flexWrap: 'wrap' }}
        >
          {visibleTypeFilters.map((key) => (
            <button
              key={key}
              type="button"
              data-testid={`${testIdPrefix}-type-${key}`}
              onClick={() => setTypeFilter(key)}
              style={{
                padding: '2px var(--space-3)',
                fontSize: 'var(--font-size-sm)',
                borderRadius: 'var(--radius-full)',
                border: '1px solid var(--color-border)',
                cursor: 'pointer',
                background: typeFilter === key ? 'var(--color-primary)' : 'var(--color-surface)',
                color: typeFilter === key ? 'var(--color-on-primary, #fff)' : 'var(--color-text)',
                fontWeight: typeFilter === key ? 600 : 400,
              }}
            >
              {t(TYPE_LABEL_KEYS[key], TYPE_DISPLAY_LABELS[key])}
            </button>
          ))}
        </div>
      )}

      {/* Element list */}
      <div data-testid={`${testIdPrefix}-list`} style={elementListStyle}>
        {isLoading ? (
          <p
            role="status"
            style={{ margin: 0, padding: 'var(--space-3)', fontSize: 'var(--font-size-sm)', color: 'var(--color-text-muted)' }}
          >
            {t('loading', 'Loading…')}
          </p>
        ) : filtered.length === 0 ? (
          <p
            data-testid={`${testIdPrefix}-empty`}
            style={{ margin: 0, padding: 'var(--space-3)', fontSize: 'var(--font-size-sm)', color: 'var(--color-text-muted)' }}
          >
            {search.trim()
              ? t('editor.noMatches', 'No matches found.')
              : t('traceability.noArtifacts', 'No artifacts available.')}
          </p>
        ) : (
          <ul style={{ listStyle: 'none', margin: 0, padding: 0 }}>
            {filtered.map((el) => {
              const isSelected = el.id === selectedId;
              return (
                <li key={el.id} style={{ borderBottom: '1px solid var(--color-border)' }}>
                  <button
                    type="button"
                    data-testid={`${testIdPrefix}-element-${el.id}`}
                    onClick={() => onSelect(el.id)}
                    style={{
                      width: '100%',
                      display: 'flex',
                      alignItems: 'center',
                      gap: 'var(--space-2)',
                      padding: 'var(--space-2) var(--space-3)',
                      background: isSelected ? 'var(--color-primary)' : 'transparent',
                      color: isSelected ? 'var(--color-on-primary, #fff)' : 'var(--color-text)',
                      border: 'none',
                      cursor: 'pointer',
                      textAlign: 'left',
                      fontSize: 'var(--font-size-sm)',
                    }}
                  >
                    <span
                      style={{
                        fontSize: '0.7rem',
                        background: isSelected ? 'rgba(255,255,255,0.25)' : 'var(--color-badge-draft)',
                        color: isSelected ? '#fff' : 'var(--color-badge-draft-text)',
                        padding: '1px 6px',
                        borderRadius: 'var(--radius-full)',
                        flexShrink: 0,
                      }}
                    >
                      {TYPE_DISPLAY_LABELS[el.artifactType]}
                    </span>
                    <span
                      data-testid={`${testIdPrefix}-title-${el.id}`}
                      style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
                    >
                      {el.title}
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

/**
 * Unified modal dialog for creating a single trace link (REQ-005).
 *
 * When `sourceId` is provided (single-artifact context like ArchitectureEditors,
 * AdrEditors), the dialog shows only a target picker with search.
 *
 * When `sourceId` is omitted (global context like TraceabilityView), both a
 * source picker (simple select with titles) and the searchable target picker
 * are shown, resulting in the same modal design.
 */
export function CreateTraceLinkDialog({
  workspaceId,
  sourceId,
  isOpen,
  onClose,
  onCreated,
  allowedTypes,
  defaultLinkType = 'derives-from',
}: CreateTraceLinkDialogProps): JSX.Element | null {
  const { t } = useTranslation();

  // All loaded elements (before filtering)
  const [allElements, setAllElements] = useState<TargetElement[]>([]);
  const [isLoadingElements, setIsLoadingElements] = useState(false);

  // Form state
  const [selectedSourceId, setSelectedSourceId] = useState('');
  const [selectedTargetId, setSelectedTargetId] = useState('');
  const [linkType, setLinkType] = useState<LinkType>(defaultLinkType);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  // The actual source to use in the API call
  const effectiveSourceId = sourceId ?? selectedSourceId;

  // Load all elements when dialog opens
  const loadElements = useCallback(async (): Promise<void> => {
    if (!workspaceId) return;
    setIsLoadingElements(true);
    try {
      const [reqs, archs, tcs, adrList, riskList, issueList] = await Promise.all([
        requirementsApi.listAll(workspaceId).catch(() => []),
        architectureApi.listAll(workspaceId).catch(() => []),
        testcasesApi.list(workspaceId).then((r) => r.results).catch(() => []),
        adrsApi.list(workspaceId).then((r) => r.results).catch(() => []),
        risksApi.list(workspaceId).then((r) => r.results).catch(() => []),
        issuesApi.list(workspaceId).then((r) => r.results).catch(() => []),
      ]);

      const all: TargetElement[] = [
        ...reqs.map((r) => ({ id: r.id, title: r.title || t('editor.untitled'), artifactType: 'requirement' as const })),
        ...archs.map((a) => ({ id: a.id, title: a.title || t('editor.untitled'), artifactType: 'architecture' as const })),
        ...tcs.map((tc) => ({ id: tc.id, title: tc.title || t('editor.untitled'), artifactType: 'testcase' as const })),
        ...adrList.map((a) => ({ id: a.id, title: a.title || t('editor.untitled'), artifactType: 'adr' as const })),
        ...riskList.map((r) => ({ id: r.id, title: r.title || t('editor.untitled'), artifactType: 'risk' as const })),
        ...issueList.map((i) => ({ id: i.id, title: i.title || t('editor.untitled'), artifactType: 'issue' as const })),
      ];

      setAllElements(all);
    } catch (err) {
      console.error('CreateTraceLinkDialog: failed to load elements', err);
    } finally {
      setIsLoadingElements(false);
    }
  }, [workspaceId, t]);

  // Reset form and load elements when the dialog opens
  useEffect(() => {
    if (!isOpen) return;
    setSelectedSourceId('');
    setSelectedTargetId('');
    setLinkType(defaultLinkType);
    setSubmitError(null);
    void loadElements();
  }, [isOpen, defaultLinkType, loadElements]);

  // Prevent layout shift by managing body overflow when dialog is open
  useEffect(() => {
    if (!isOpen) return;

    const scrollbarWidth = window.innerWidth - document.documentElement.clientWidth;

    document.body.style.overflow = 'hidden';
    document.body.style.paddingRight = `${scrollbarWidth}px`;

    // Cleanup: restore scroll and padding when dialog closes
    return () => {
      document.body.style.overflow = '';
      document.body.style.paddingRight = '';
    };
  }, [isOpen]);

  // Determine which type filter tabs are visible
  const visibleTypeFilters = useMemo<ArtifactTypeKey[]>(() => {
    if (!allowedTypes) return ALL_FILTER_TYPES;
    return ALL_FILTER_TYPES.filter((k) => k === 'all' || allowedTypes.includes(k));
  }, [allowedTypes]);

  // Elements available as targets (exclude the fixed/chosen source)
  const targetElements = useMemo<TargetElement[]>(() => {
    const excl = effectiveSourceId;
    let list = allElements.filter((el) => el.id !== excl);
    if (allowedTypes) {
      list = list.filter((el) => allowedTypes.includes(el.artifactType));
    }
    return list;
  }, [allElements, effectiveSourceId, allowedTypes]);

  // Elements available as sources (all except the currently chosen target)
  const sourceElements = useMemo<TargetElement[]>(() => {
    return allElements.filter((el) => el.id !== selectedTargetId);
  }, [allElements, selectedTargetId]);

  const handleSubmit = useCallback(
    async (e: React.FormEvent<HTMLFormElement>): Promise<void> => {
      e.preventDefault();

      if (!effectiveSourceId) {
        setSubmitError(t('traceability.sourceRequired'));
        return;
      }
      if (!selectedTargetId) {
        setSubmitError(t('traceability.targetRequired'));
        return;
      }
      if (effectiveSourceId === selectedTargetId) {
        setSubmitError(t('traceability.sameEndpoints'));
        return;
      }

      setIsSubmitting(true);
      setSubmitError(null);
      try {
        await tracelinksApi.create({
          source_id: effectiveSourceId,
          target_id: selectedTargetId,
          link_type: linkType,
        });
        onCreated();
        onClose();
      } catch (err: unknown) {
        const apiErr = err as { error?: { message?: string } };
        setSubmitError(apiErr?.error?.message ?? t('errors.generic', 'An unexpected error occurred.'));
      } finally {
        setIsSubmitting(false);
      }
    },
    [effectiveSourceId, selectedTargetId, linkType, t, onCreated, onClose]
  );

  const handleBackdropClick = useCallback(
    (e: React.MouseEvent<HTMLDivElement>): void => {
      if (e.target === e.currentTarget) onClose();
    },
    [onClose]
  );

  if (!isOpen) return null;

  const isGlobalMode = sourceId === undefined;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={t('createTraceLinkDialog.title', 'Create Trace Link')}
      data-testid="create-trace-link-dialog"
      style={overlayStyle}
      onClick={handleBackdropClick}
    >
      <div style={dialogStyle}>
        {/* Header */}
        <div style={headerStyle}>
          <h3
            style={{
              margin: 0,
              fontSize: 'var(--font-size-lg)',
              fontWeight: 700,
              color: 'var(--color-text)',
            }}
          >
            {t('createTraceLinkDialog.title', 'Create Trace Link')}
          </h3>
          <button
            type="button"
            data-testid="create-trace-link-dialog-close"
            onClick={onClose}
            aria-label={t('actions.close', 'Close')}
            style={{
              background: 'none',
              border: 'none',
              cursor: 'pointer',
              color: 'var(--color-text-muted)',
              fontSize: '1.25rem',
              lineHeight: 1,
              padding: 'var(--space-1)',
            }}
          >
            ×
          </button>
        </div>

        {/* Form */}
        <form onSubmit={(e) => void handleSubmit(e)} style={{ display: 'contents' }}>
          <div style={bodyStyle}>

            {/* Source picker — only shown in global mode (no fixed sourceId) */}
            {isGlobalMode && (
              <div>
                <label style={labelStyle}>
                  {t('traceability.source', 'Source')}{' '}
                  <span style={{ color: 'var(--color-danger)' }}>*</span>
                </label>
                <select
                  data-testid="create-trace-link-source-select"
                  value={selectedSourceId}
                  onChange={(e) => {
                    setSelectedSourceId(e.target.value);
                    // Reset target if it happens to be the same as new source
                    if (e.target.value === selectedTargetId) setSelectedTargetId('');
                  }}
                  disabled={isSubmitting}
                  style={inputStyle}
                >
                  <option value="">
                    {isLoadingElements ? t('loading', 'Loading…') : '—'}
                  </option>
                  {sourceElements.map((el) => (
                    <option key={el.id} value={el.id}>
                      {TYPE_DISPLAY_LABELS[el.artifactType]}: {el.title}
                    </option>
                  ))}
                </select>
              </div>
            )}

            {/* Target picker with search */}
            <div>
              <label style={labelStyle}>
                {t('traceability.target', 'Target')}{' '}
                <span style={{ color: 'var(--color-danger)' }}>*</span>
              </label>
              <ElementPicker
                elements={targetElements}
                isLoading={isLoadingElements}
                selectedId={selectedTargetId}
                onSelect={setSelectedTargetId}
                testIdPrefix="create-trace-link-target"
                visibleTypeFilters={visibleTypeFilters}
              />
            </div>

            {/* Link type selector */}
            <div>
              <label htmlFor="ctl-link-type" style={labelStyle}>
                {t('traceability.linkType', 'Link Type')}
              </label>
              <select
                id="ctl-link-type"
                data-testid="create-trace-link-type-select"
                value={linkType}
                onChange={(e) => setLinkType(e.target.value as LinkType)}
                disabled={isSubmitting}
                style={inputStyle}
              >
                {ALL_LINK_TYPES.map((lt) => (
                  <option key={lt} value={lt}>
                    {getLinkTypeLabel(lt)}
                  </option>
                ))}
              </select>
            </div>

            {/* Error message */}
            {submitError && (
              <p
                role="alert"
                data-testid="create-trace-link-error"
                style={{ margin: 0, color: 'var(--color-danger)', fontSize: 'var(--font-size-sm)' }}
              >
                {submitError}
              </p>
            )}
          </div>

          {/* Footer */}
          <div style={footerStyle}>
            <button
              type="button"
              data-testid="create-trace-link-cancel"
              className="btn-secondary"
              onClick={onClose}
              disabled={isSubmitting}
            >
              {t('actions.cancel', 'Cancel')}
            </button>
            <button
              type="submit"
              data-testid="create-trace-link-submit"
              className="btn-primary"
              disabled={isSubmitting || !selectedTargetId || (isGlobalMode && !selectedSourceId)}
            >
              {isSubmitting
                ? t('traceability.submitting', 'Creating...')
                : t('traceability.submit', 'Create')}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

CreateTraceLinkDialog.displayName = 'CreateTraceLinkDialog';
