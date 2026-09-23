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
 *   - Link type selector: non-native accessible listbox (#318)
 *   - Consistent modal design: same overlay layout in every view
 *   - Optional sourceId: when absent, a source ElementPicker is shown too
 */

import React, {
  useState,
  useEffect,
  useId,
  useMemo,
  useCallback,
  useRef,
} from 'react';
import { useTranslation } from 'react-i18next';
import { requirementsApi } from '../../../api/requirements';
import { architectureApi } from '../../../api/architecture';
import { testcasesApi } from '../../../api/testcases';
import { adrsApi } from '../../../api/adrs';
import { risksApi } from '../../../api/risks';
import { issuesApi } from '../../../api/issues';
import { tracelinksApi } from '../../../api/tracelinks';
import { useLinkTypes } from '../../../context/LinkTypeContext';
import { Dialog } from '../Dialog';
import { LinkTypeListbox } from './link-type-listbox';
import type { LinkType } from '../../../types';
import styles from './create-trace-link-dialog.module.css';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type ArtifactTypeKey = 'all' | 'requirement' | 'architecture' | 'testcase' | 'adr' | 'risk' | 'issue';

/**
 * `ArtifactTypeKey` -> the backend's PascalCase `artifact_type` spelling
 * (see `backend/link_types/builtin.py::_pairs`, `backend/application/issue_service.py`).
 * Needed to call `LinkTypeContext.isAllowedPair(key, sourceType, targetType)`,
 * which expects the backend spelling, not this component's internal short keys.
 * `'all'` is a filter-tab-only value, never an actual element's artifactType.
 */
const ARTIFACT_TYPE_KEY_TO_BACKEND: Record<Exclude<ArtifactTypeKey, 'all'>, string> = {
  requirement: 'Requirement',
  architecture: 'ArchitectureElement',
  testcase: 'TestCase',
  adr: 'Adr',
  risk: 'Risk',
  issue: 'Issue',
};

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
    <div className={styles.pickerColumn}>
      {/* Search input */}
      <input
        type="text"
        data-testid={`${testIdPrefix}-search`}
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        placeholder={t('createTraceLinkDialog.searchPlaceholder', 'Filter by title…')}
        className={styles.input}
        aria-label={t('createTraceLinkDialog.searchLabel', 'Search elements')}
      />

      {/* Type filter tabs */}
      {visibleTypeFilters.length > 1 && (
        <div
          role="group"
          aria-label={t('createTraceLinkDialog.typeFilterLabel', 'Filter by type')}
          className={styles.typeTabs}
        >
          {visibleTypeFilters.map((key) => (
            <button
              key={key}
              type="button"
              data-testid={`${testIdPrefix}-type-${key}`}
              onClick={() => setTypeFilter(key)}
              className={
                styles.typeTab +
                ' ' +
                (typeFilter === key ? styles.typeTabActive : styles.typeTabInactive)
              }
            >
              {t(TYPE_LABEL_KEYS[key], TYPE_DISPLAY_LABELS[key])}
            </button>
          ))}
        </div>
      )}

      {/* Element list */}
      <div data-testid={`${testIdPrefix}-list`} className={styles.elementList}>
        {isLoading ? (
          <p
            role="status"
            className={styles.listStatus}
          >
            {t('loading', 'Loading…')}
          </p>
        ) : filtered.length === 0 ? (
          <p
            data-testid={`${testIdPrefix}-empty`}
            className={styles.listStatus}
          >
            {search.trim()
              ? t('editor.noMatches', 'No matches found.')
              : t('traceability.noArtifacts', 'No artifacts available.')}
          </p>
        ) : (
          <ul className={styles.list}>
            {filtered.map((el) => {
              const isSelected = el.id === selectedId;
              return (
                <li key={el.id} className={styles.listItem}>
                  <button
                    type="button"
                    data-testid={`${testIdPrefix}-element-${el.id}`}
                    onClick={() => onSelect(el.id)}
                    className={
                      styles.elementButton +
                      ' ' +
                      (isSelected
                        ? styles.elementButtonSelected
                        : styles.elementButtonUnselected)
                    }
                  >
                    <span
                      className={
                        styles.typeBadge +
                        ' ' +
                        (isSelected
                          ? styles.typeBadgeSelected
                          : styles.typeBadgeUnselected)
                      }
                    >
                      {TYPE_DISPLAY_LABELS[el.artifactType]}
                    </span>
                    <span
                      data-testid={`${testIdPrefix}-title-${el.id}`}
                      className={styles.elementTitle}
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
 * source picker (searchable ElementPicker) and the searchable target picker
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
  const { t, i18n } = useTranslation();
  // Link-type neutral labels come from the dedicated Tri-Label table
  // (constants/traceLinkLabels.ts), not from the i18next locale JSON — that
  // table already carries real DE/EN pairs per link type, but the
  // now-replaced `getLinkTypeLabel()` helper always returned the EN neutral
  // form regardless of the active UI language (e.g. "Derivation" for
  // `derives-from`, shown even with a German UI). Resolve against the
  // active language instead, matching the `i18n.language.startsWith("de")`
  // convention used elsewhere (e.g. SidebarNavigation.tsx).
  const triLabelLang = i18n?.language?.startsWith('de') ? 'de' : 'en';

  const { creatableLinkTypes, isAllowedPair, labelFor } = useLinkTypes();

  // Keep the latest `t` in a ref so data-loading callbacks can read it without
  // taking a dependency on it. react-i18next normally returns a referentially
  // stable `t`, but a language switch (or an unstable test/wrapper) yields a
  // fresh `t` on every render. If `loadElements` depended on `t` directly, a
  // new `loadElements` identity each render would re-fire the open/reset effect
  // below (which calls it), producing an infinite re-render loop that starves
  // the event loop. Reading `t` via a ref keeps `loadElements` stable.
  const tRef = useRef(t);
  tRef.current = t;

  // All loaded elements (before filtering)
  const [allElements, setAllElements] = useState<TargetElement[]>([]);
  const [isLoadingElements, setIsLoadingElements] = useState(false);

  // Form state
  const [selectedSourceId, setSelectedSourceId] = useState('');
  const [selectedTargetId, setSelectedTargetId] = useState('');
  const [linkType, setLinkType] = useState<LinkType>(defaultLinkType);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  // #318: the link-type dropdown is a non-native listbox, so its open state
  // lives here and its visible label is referenced through `aria-labelledby`.
  const [isTypeMenuOpen, setIsTypeMenuOpen] = useState(false);
  const linkTypeLabelId = useId();
  const linkTypeHintId = useId();

  // The actual source to use in the API call
  const effectiveSourceId = sourceId ?? selectedSourceId;

  // Resolve the backend artifact_type of an endpoint by looking it up in the
  // loaded element list — the dialog only ever knows ids, never types, until
  // the corresponding element has been fetched.
  const effectiveSourceType = useMemo(() => {
    const el = allElements.find((e) => e.id === effectiveSourceId);
    return el ? ARTIFACT_TYPE_KEY_TO_BACKEND[el.artifactType as Exclude<ArtifactTypeKey, 'all'>] : undefined;
  }, [allElements, effectiveSourceId]);

  const selectedTargetType = useMemo(() => {
    const el = allElements.find((e) => e.id === selectedTargetId);
    return el ? ARTIFACT_TYPE_KEY_TO_BACKEND[el.artifactType as Exclude<ArtifactTypeKey, 'all'>] : undefined;
  }, [allElements, selectedTargetId]);

  // Only the types whose allowed_pairs actually fit the chosen endpoints
  // (spec section 4.1): offering a type the backend will reject turns a
  // preventable mistake into a 400 after the user hits Save.
  //
  // Both sides fall back to the wildcard when they cannot be resolved, for
  // the same "not yet known" reason. The source used to fall back to `''`,
  // which matches no real pair — and the dialog is opened with a `sourceId`
  // for StakeholderNeed (NeedsEditors/TraceLinkPanel) and GlossaryTerm
  // (GlossaryView), neither of which this dialog's element loader ever
  // fetches. For those the source stayed unresolved forever, every type got
  // filtered out, and the user saw "no link type connects these artifacts"
  // with Create permanently disabled. An offer the backend may still reject
  // is strictly better than an empty list that cannot be recovered from.
  const availableLinkTypes = useMemo(
    () =>
      creatableLinkTypes.filter((row) =>
        isAllowedPair(row.key, effectiveSourceType ?? '*', selectedTargetType ?? '*'),
      ),
    [creatableLinkTypes, isAllowedPair, effectiveSourceType, selectedTargetType],
  );

  // Keep the selection valid when the endpoints change under it.
  useEffect(() => {
    if (availableLinkTypes.length === 0) return;
    if (!availableLinkTypes.some((row) => row.key === linkType)) {
      setLinkType(availableLinkTypes[0].key);
    }
  }, [availableLinkTypes, linkType]);

  // Load all elements when dialog opens
  const loadElements = useCallback(async (): Promise<void> => {
    if (!workspaceId) return;
    setIsLoadingElements(true);
    try {
      // Issue C: testcases/adrs/risks/issues used to fetch only page 1
      // (PAGE_SIZE=25), silently dropping target options past the 25th
      // item. listAll() follows pagination until exhaustion, matching
      // requirementsApi/architectureApi above.
      const [reqs, archs, tcs, adrList, riskList, issueList] = await Promise.all([
        requirementsApi.listAll(workspaceId).catch(() => []),
        architectureApi.listAll(workspaceId).catch(() => []),
        testcasesApi.listAll(workspaceId).catch(() => []),
        adrsApi.listAll(workspaceId).catch(() => []),
        risksApi.listAll(workspaceId).catch(() => []),
        issuesApi.listAll(workspaceId).catch(() => []),
      ]);

      const untitled = tRef.current('editor.untitled');
      const all: TargetElement[] = [
        ...reqs.map((r) => ({ id: r.id, title: r.title || untitled, artifactType: 'requirement' as const })),
        ...archs.map((a) => ({ id: a.id, title: a.title || untitled, artifactType: 'architecture' as const })),
        ...tcs.map((tc) => ({ id: tc.id, title: tc.title || untitled, artifactType: 'testcase' as const })),
        ...adrList.map((a) => ({ id: a.id, title: a.title || untitled, artifactType: 'adr' as const })),
        ...riskList.map((r) => ({ id: r.id, title: r.title || untitled, artifactType: 'risk' as const })),
        ...issueList.map((i) => ({ id: i.id, title: i.title || untitled, artifactType: 'issue' as const })),
      ];

      // #832: the six listAll() calls may return the same artifact id more
      // than once (e.g. an id that shows up in both the requirement and the
      // architecture listing). Rendering every entry produced duplicate rows
      // and duplicate React keys (`key={el.id}` in ElementPicker). Dedup
      // centrally on the stable artifact id, right after concatenation.
      //
      // A `Map` keyed by id overwrites on re-insert, so the LAST duplicate
      // candidate (in the fixed reqs -> archs -> tcs -> adrs -> risks ->
      // issues order) wins for title/artifactType, while the id keeps the
      // position of its FIRST occurrence. That keeps the remaining order
      // deterministic and stable, and everything but the duplicated ids
      // untouched.
      const allById = new Map<string, TargetElement>();
      for (const el of all) {
        allById.set(el.id, el);
      }

      setAllElements(Array.from(allById.values()));
    } catch (err) {
      console.error('CreateTraceLinkDialog: failed to load elements', err);
    } finally {
      setIsLoadingElements(false);
    }
  }, [workspaceId]);

  // Reset form and load elements when the dialog opens
  useEffect(() => {
    if (!isOpen) return;
    setSelectedSourceId('');
    setSelectedTargetId('');
    setLinkType(defaultLinkType);
    setSubmitError(null);
    setIsTypeMenuOpen(false);
    void loadElements();
  }, [isOpen, defaultLinkType, loadElements]);

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

  if (!isOpen) return null;

  const isGlobalMode = sourceId === undefined;
  const formId = 'create-trace-link-form';

  // #53 Bug 3: the submit button used to disable silently with no
  // explanation. Surface the concrete missing piece as a tooltip.
  const submitDisabledReason = isSubmitting
    ? undefined
    : isGlobalMode && !selectedSourceId
      ? t('traceability.sourceRequired', 'Please select a source artifact.')
      : !selectedTargetId
        ? t('traceability.targetRequired', 'Please select a target artifact.')
        : undefined;

  return (
    <Dialog
      title={t('createTraceLinkDialog.title', 'Create Trace Link')}
      onClose={() => {
        // UI-24: Escape used to close the dialog even mid-submit, leaving
        // the create request running with nothing left to report its
        // result to.
        if (!isSubmitting) onClose();
      }}
      closeOnBackdropClick={!isSubmitting}
      size="md"
      testId="create-trace-link-dialog"
      footer={
        <div className={styles.footer}>
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
            form={formId}
            data-testid="create-trace-link-submit"
            className="btn-primary"
            disabled={
              isSubmitting ||
              !selectedTargetId ||
              (isGlobalMode && !selectedSourceId) ||
              availableLinkTypes.length === 0
            }
            title={submitDisabledReason}
          >
            {isSubmitting
              ? t('traceability.submitting', 'Creating...')
              : t('traceability.submit', 'Create')}
          </button>
        </div>
      }
    >
      <form id={formId} onSubmit={(e) => void handleSubmit(e)} className={styles.body}>
        {/* Source picker — only shown in global mode (no fixed sourceId).
            #53 Bug 2: uses the same searchable ElementPicker as the target
            list instead of a plain unfiltered <select>, for a consistent
            pattern on both sides of the dialog. */}
        {isGlobalMode && (
          <fieldset className={styles.fieldset}>
            <legend className={styles.legend}>
              {t('traceability.source', 'Source')}{' '}
              <span className={styles.requiredMark}>*</span>
            </legend>
            <ElementPicker
              elements={sourceElements}
              isLoading={isLoadingElements}
              selectedId={selectedSourceId}
              onSelect={(id) => {
                setSelectedSourceId(id);
                // Reset target if it happens to be the same as new source
                if (id === selectedTargetId) setSelectedTargetId('');
              }}
              testIdPrefix="create-trace-link-source"
              visibleTypeFilters={visibleTypeFilters}
            />
          </fieldset>
        )}

        {/* Target picker with search */}
        <fieldset className={styles.fieldset}>
          <legend className={styles.legend}>
            {t('traceability.target', 'Target')}{' '}
            <span className={styles.requiredMark}>*</span>
          </legend>
          <ElementPicker
            elements={targetElements}
            isLoading={isLoadingElements}
            selectedId={selectedTargetId}
            onSelect={setSelectedTargetId}
            testIdPrefix="create-trace-link-target"
            visibleTypeFilters={visibleTypeFilters}
          />
        </fieldset>

        {/* Link type selector — non-native accessible listbox (#318).
            Replaces the former native <select>: a programmatic DOM value-set
            never reached React state there, so the shown value and the
            submitted value could diverge. Selection now flows through a
            React handler, which also makes the Create button's enabled
            state deterministic. */}
        <div>
          <span id={linkTypeLabelId} className={styles.label}>
            {t('traceability.linkType', 'Link Type')}
          </span>
          <LinkTypeListbox
            options={availableLinkTypes.map((row) => ({
              key: row.key,
              label: labelFor(row.key, triLabelLang, 'neutral'),
            }))}
            value={linkType}
            onSelect={(key) => setLinkType(key as LinkType)}
            isOpen={isTypeMenuOpen}
            onOpenChange={setIsTypeMenuOpen}
            labelledBy={linkTypeLabelId}
            describedBy={availableLinkTypes.length === 0 ? linkTypeHintId : undefined}
            testId="create-trace-link-type-select"
            optionTestIdPrefix="create-trace-link-type"
            disabled={isSubmitting}
          />
          {availableLinkTypes.length === 0 && (
            <p id={linkTypeHintId} data-testid="create-trace-link-no-types" className={styles.noTypesHint}>
              {t(
                'traceability.noLinkTypeForPair',
                'No link type in this workspace connects these two artifact types.',
              )}
            </p>
          )}
        </div>

        {/* Error message */}
        {submitError && (
          <p
            role="alert"
            data-testid="create-trace-link-error"
            className={styles.errorText}
          >
            {submitError}
          </p>
        )}
      </form>
    </Dialog>
  );
}

CreateTraceLinkDialog.displayName = 'CreateTraceLinkDialog';
