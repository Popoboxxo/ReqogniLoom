# Frontend SplitView Migration Plan — REQ-L1-084

## Overview

This document outlines the migration strategy to refactor `RequirementEditors` and `ArchitectureEditors` to use the new generic `SplitView` component (REQ-L1-084).

**Current State:**
- Both components implement duplicate split-pane resize logic (~100 lines each)
- State: `leftPanelWidth`, `isDraggingRef`, `dragStartXRef`, `dragStartWidthRef`
- Each has separate `handleDividerMouseDown` and `useEffect` for mouse events
- localStorage persistence is not implemented (but SplitView will handle it)

**Target State:**
- Single reusable `<SplitView>` component
- RequirementEditors extracts list/form into separate sub-components
- ArchitectureEditors extracts tree/form into separate sub-components
- Both use `<EntityTypeProvider>` to provide type-aware rendering context
- Admin UI for attribute visibility configuration

---

## Phase 1: Component Extraction (No functional changes)

### Step 1a: Extract RequirementsList (from RequirementEditors.tsx)

**Source:** `frontend/src/components/RequirementEditors/RequirementEditors.tsx` (lines 1239–1500+)

Create `frontend/src/components/RequirementEditors/RequirementsList.tsx`:

```typescript
/**
 * REQ-L1-084 Step 5: Extracted list component for SplitView left panel
 * Renders requirements list with search/filter/sort toolbar
 */
export interface RequirementsListProps {
  requirements: Requirement[];
  selectedId?: string;
  onSelect: (id: string) => void;
  onCreate: () => void;
  onDelete: (id: string) => void;
  isLoading: boolean;
  error?: string | null;
}

export const RequirementsList: React.FC<RequirementsListProps> = ({
  requirements,
  selectedId,
  onSelect,
  onCreate,
  onDelete,
  isLoading,
  error,
}) => {
  // Move all list-panel logic from RequirementEditors here:
  // - ListToolbar (search, filter, sort)
  // - Create form inline
  // - List item rendering
  // - State: listSearch, categoryFilter, statusFilter, sortKey, showCreateForm, newTitle, isCreating
  
  return (
    <div>
      {/* List toolbar, create form, list items */}
    </div>
  );
};
```

**What to Move:**
- Lines 1250–1327: Header with buttons (Export PDF, Import, New)
- Lines 1328–1420: Create form
- Lines 1421–1600+: List item rendering and event handlers
- State variables: `hoveredId`, `newBtnHovered`, `showCreateForm`, `newTitle`, `isCreating`
- State variables: `listSearch`, `categoryFilter`, `statusFilter`, `sortKey` (list toolbar)
- Handler: `openCreateForm`, `cancelCreateForm`, `handleCreate`
- Utility: `sortRequirements`, `getStatusBadgeStyle`

**Keep in RequirementEditors:**
- Data fetching: `useRequirementData`, `useCreateRequirement`, `useDeleteRequirement`
- Layout: `<SplitView>` wrapper
- Detail panel: `<RequirementForm>` (to be extracted in Step 1b)

### Step 1b: Extract RequirementForm (from RequirementEditors.tsx)

Create `frontend/src/components/RequirementEditors/RequirementForm.tsx`:

```typescript
/**
 * REQ-L1-084 Step 5: Extracted detail form component for SplitView right panel
 * Renders requirement form with inline editing and traceability panel
 */
export interface RequirementFormProps {
  requirement: Requirement | null;
  isLoading: boolean;
  error?: string | null;
  onSave: (data: Partial<Requirement>) => Promise<void>;
  onDelete: (id: string) => Promise<void>;
  linkedTitles: Record<UUID, string>;
  linkedRoutes: Record<UUID, string>;
  upstreamLinks: TraceLink[];
  downstreamLinks: TraceLink[];
}

export const RequirementForm: React.FC<RequirementFormProps> = ({
  requirement,
  isLoading,
  error,
  onSave,
  onDelete,
  linkedTitles,
  linkedRoutes,
  upstreamLinks,
  downstreamLinks,
}) => {
  // Move detail-form logic here:
  // - Title/description/category inline editing
  // - Status badge and workflow transitions
  // - TraceabilityPanel
  // - Markdown preview toggle
  // - Save/Delete buttons
  
  return (
    <form>
      {/* Detail form with all inline-edit controls */}
    </form>
  );
};
```

**What to Move:**
- Entire detail-form JSX section (lines ~600–1090 in original RequirementEditors)
- State variables: `editingTitle`, `editingDescription`, `editingCategory`, `isSaving`, `saveError`, `showDeleteDialog`, `showDiffPanel`, `showMarkdown`
- Handlers: `handleSave`, `handleDelete`, `handleExportPdf` (moved up from RequirementEditors)
- Sub-components: `<TraceabilityPanel>`, `<MarkdownPreview>`, `<ArtifactDiff>`

**Wrap with EntityTypeProvider:**
```typescript
<EntityTypeProvider 
  entityType="requirement" 
  entitySubType={detectSubType(requirement)}
  visibleFields={visibilityConfig}
>
  <RequirementForm {...props} />
</EntityTypeProvider>
```

### Step 1c: Extract ArchitectureList (from ArchitectureEditors.tsx)

Create `frontend/src/components/ArchitectureEditors/ArchitectureList.tsx`:

```typescript
export interface ArchitectureListProps {
  elements: ArchitectureElement[];
  selectedId?: string;
  onSelect: (id: string) => void;
  onCreate: (parentId?: string) => void;
  onDelete: (el: ArchitectureElement) => void;
  onReparent: (elementId: string, newParentId: string | null) => Promise<void>;
  isLoading: boolean;
  error?: string | null;
  reparentError?: string | null;
  onReparentErrorDismiss: () => void;
}

export const ArchitectureList: React.FC<ArchitectureListProps> = ({
  elements,
  selectedId,
  onSelect,
  onCreate,
  onDelete,
  onReparent,
  isLoading,
  error,
  reparentError,
  onReparentErrorDismiss,
}) => {
  // Move tree-panel logic here:
  // - DecompositionTree component
  // - Header with "New" button
  // - Reparent error banner
  
  return (
    <div>
      {/* Tree header, error banner, DecompositionTree */}
    </div>
  );
};
```

**What to Move:**
- Lines 650–800+: Tree header, create button, reparent error banner, DecompositionTree

### Step 1d: Extract ArchitectureForm (from ArchitectureEditors.tsx)

Create `frontend/src/components/ArchitectureEditors/ArchitectureForm.tsx`:

```typescript
export interface ArchitectureFormProps {
  element: ArchitectureElement | null;
  isLoading: boolean;
  error?: string | null;
  onSave: (data: Partial<ArchitectureElement>) => Promise<void>;
  onDelete: (id: string) => Promise<void>;
  linkedTraceLinks: TraceLink[];
}

export const ArchitectureForm: React.FC<ArchitectureFormProps> = ({
  element,
  isLoading,
  error,
  onSave,
  onDelete,
  linkedTraceLinks,
}) => {
  // Move detail-form logic here:
  // - Title/description/element_type inline editing
  // - Parent dropdown
  // - ArchTraceLinkPanel
  // - Markdown preview toggle
  // - Save/Delete/View Diff buttons
  
  return (
    <form>
      {/* Detail form with all inline-edit controls */}
    </form>
  );
};
```

**What to Move:**
- Lines ~200–476 (original ArchitectureEditors): entire detail-form section
- State: `editingTitle`, `editingDescription`, `editingElementType`, `editingParentId`, `isSaving`, `saveError`, `showDeleteDialog`, `showDiff`
- Handlers: `handleSave`, `handleDelete`
- Sub-components: `<ArchTraceLinkPanel>`, `<MarkdownPreview>`, `<ArtifactDiff>`

**Wrap with EntityTypeProvider:**
```typescript
<EntityTypeProvider 
  entityType="architecture_element" 
  entitySubType={element?.element_type}
  visibleFields={visibilityConfig}
>
  <ArchitectureForm {...props} />
</EntityTypeProvider>
```

---

## Phase 2: Integration with SplitView

### Step 2a: Refactor RequirementEditors to use SplitView

**File:** `frontend/src/components/RequirementEditors/RequirementEditors.tsx`

**Changes:**
1. Remove split-pane state: `leftPanelWidth`, `isDraggingRef`, `dragStartXRef`, `dragStartWidthRef`
2. Remove `handleDividerMouseDown` and related `useEffect`
3. Extract data-fetching and top-level state into RequirementEditors (keep it as container)
4. Replace JSX with:

```typescript
export default function RequirementEditors(): JSX.Element {
  // Keep data-fetching logic
  const { requirements, requirement, upstreamLinks, downstreamLinks, ... } = useRequirementData(selectedId);
  const createRequirement = useCreateRequirement();
  const deleteRequirement = useDeleteRequirement();

  // Keep handlers for CRUD operations
  const handleCreate = useCallback(...);
  const handleDelete = useCallback(...);
  const handleSave = useCallback(...);

  // Load visibility config (TODO: API call when endpoint is ready)
  const [visibilityConfig, setVisibilityConfig] = useState<VisibleFieldsMap>({});

  return (
    <SplitView
      moduleType="requirements"
      leftPanel={
        <RequirementsList
          requirements={visibleRequirements}
          selectedId={selectedId}
          onSelect={(id) => navigate(`/requirements/${id}`)}
          onCreate={() => { /* show create form */ }}
          onDelete={handleDelete}
          isLoading={isLoading}
          error={error}
        />
      }
      rightPanel={
        requirement ? (
          <EntityTypeProvider
            entityType="requirement"
            entitySubType={detectReqSubType(requirement)}
            visibleFields={visibilityConfig}
          >
            <RequirementForm
              requirement={requirement}
              isLoading={isLoading}
              error={error}
              onSave={handleSave}
              onDelete={handleDelete}
              linkedTitles={linkedTitles}
              linkedRoutes={linkedRoutes}
              upstreamLinks={upstreamLinks}
              downstreamLinks={downstreamLinks}
            />
          </EntityTypeProvider>
        ) : (
          <p>{t('editor.selectToEdit')}</p>
        )
      }
      initialLeftWidth={340} // Based on current default
    />
  );
}
```

**Removed Code Count:** ~130 lines (split-pane state + handlers + render layout)

### Step 2b: Refactor ArchitectureEditors to use SplitView

**File:** `frontend/src/components/ArchitectureEditors/ArchitectureEditors.tsx`

**Changes:**
1. Remove split-pane state and handlers (same as 2a)
2. Keep data-fetching and CRUD handlers
3. Replace JSX with:

```typescript
export default function ArchitectureEditors(): JSX.Element {
  const { elements, element, linkedTraceLinks, ... } = useArchitectureData(selectedId);
  
  // Keep CRUD handlers
  const handleCreate = useCallback(...);
  const handleDelete = useCallback(...);
  const handleSave = useCallback(...);
  const handleReparent = useCallback(...);

  // Load visibility config
  const [visibilityConfig, setVisibilityConfig] = useState<VisibleFieldsMap>({});

  return (
    <SplitView
      moduleType="architecture"
      leftPanel={
        <ArchitectureList
          elements={elements}
          selectedId={selectedId}
          onSelect={(id) => navigate(`/architecture/${id}`)}
          onCreate={handleCreate}
          onDelete={(el) => setTreeDeleteTarget(el)}
          onReparent={handleReparent}
          isLoading={isLoading}
          error={error}
          reparentError={reparentError}
          onReparentErrorDismiss={() => setReparentError(null)}
        />
      }
      rightPanel={
        element ? (
          <EntityTypeProvider
            entityType="architecture_element"
            entitySubType={element.element_type}
            visibleFields={visibilityConfig}
          >
            <ArchitectureForm
              element={element}
              isLoading={isLoading}
              error={error}
              onSave={handleSave}
              onDelete={handleDelete}
              linkedTraceLinks={linkedTraceLinks}
            />
          </EntityTypeProvider>
        ) : (
          <p>{t('editor.selectToEdit')}</p>
        )
      }
      initialLeftWidth={280} // Based on current default
    />
  );
}
```

**Removed Code Count:** ~110 lines (split-pane state + handlers + render layout)

---

## Phase 3: Form Type-Aware Rendering (Step 5 in Detailed Task)

### Step 3a: RequirementForm Type-Dependent Fields

**File:** `frontend/src/components/RequirementEditors/RequirementForm.tsx`

Add conditional rendering in form:

```typescript
const { entitySubType, visibleFields } = useEntityType();

return (
  <form>
    {/* Always visible */}
    <Field name="title" />
    <Field name="description" />
    <Field name="category" />
    
    {/* StReq-specific: Moscow Priority */}
    {entitySubType === 'StReq' && visibleFields['moscow_priority'] && (
      <div>
        <label>{t('req.moscowPriority')}</label>
        <Select
          options={['Must', 'Should', 'Could', 'Wont']}
          value={requirement.moscow_priority}
          onChange={(v) => onSave({ moscow_priority: v })}
        />
      </div>
    )}
    
    {/* SyReq-specific: Complexity + Verification */}
    {entitySubType === 'SyReq' && (
      <>
        {visibleFields['complexity_fibonacci'] && (
          <Field 
            name="complexity_fibonacci" 
            type="fibonacci-slider" 
            min={1} max={233}
          />
        )}
        {visibleFields['verification_method'] && (
          <Field
            name="verification_method"
            type="select"
            options={['test', 'analysis', 'inspection', 'demonstration']}
          />
        )}
      </>
    )}
    
    {/* Standard fields (always visible after config) */}
    {visibleFields['traceability_links'] && (
      <TraceabilityPanel upstreamLinks={...} downstreamLinks={...} />
    )}
  </form>
);
```

### Step 3b: ArchitectureForm Type-Dependent Fields

**File:** `frontend/src/components/ArchitectureEditors/ArchitectureForm.tsx`

Add conditional rendering in form:

```typescript
const { visibleFields } = useEntityType();

return (
  <form>
    {/* Always visible */}
    <Field name="title" />
    <Field name="description" />
    <Field name="element_type" type="select" />
    
    {/* Architecture-specific attributes (if visible) */}
    {visibleFields['uid'] && (
      <Field name="uid" readOnly />
    )}
    
    {visibleFields['asil_level'] && (
      <Select
        label={t('arch.asilLevel')}
        options={['ASIL_A', 'ASIL_B', 'ASIL_C', 'ASIL_D']}
        value={element.asil_level}
        onChange={(v) => onSave({ asil_level: v })}
      />
    )}
    
    {visibleFields['make_or_buy'] && (
      <Select
        label={t('arch.makeOrBuy')}
        options={['make', 'buy', 'cots']}
        value={element.make_or_buy}
        onChange={(v) => onSave({ make_or_buy: v })}
      />
    )}
    
    {visibleFields['traceability_links'] && (
      <ArchTraceLinkPanel linkedTraceLinks={...} />
    )}
  </form>
);
```

---

## Phase 4: Admin UI Integration

### Step 4a: Add AttributeVisibilityAdmin to Settings/Admin Modal

**File:** `frontend/src/components/WorkspaceSettings/WorkspaceSettings.tsx` (or new Admin route)

Add tab/section:

```typescript
import { AttributeVisibilityAdmin } from '../AdminDialog/AttributeVisibilityAdmin';

export const WorkspaceSettings: React.FC = () => {
  const [activeTab, setActiveTab] = useState('general');
  const [visibilityConfigs, setVisibilityConfigs] = useState<AttributeVisibilityConfig[]>([]);

  // TODO: Load from API when endpoint is ready
  // const { data: configs } = useQuery(['attribute-visibility'], () => 
  //   attributeVisibilityApi.getAll()
  // );

  return (
    <div>
      <Tabs value={activeTab} onChange={setActiveTab}>
        <Tab label="General">{/* existing UI */}</Tab>
        <Tab label="Permissions">{/* existing UI */}</Tab>
        <Tab label="Attribute Visibility">
          <AttributeVisibilityAdmin
            initialConfigs={visibilityConfigs}
            onSave={(configs) => {
              // TODO: API call to persist
              setVisibilityConfigs(configs);
            }}
          />
        </Tab>
      </Tabs>
    </div>
  );
};
```

---

## Migration Timeline

| Phase | Step | Effort | Duration | Dependencies |
|-------|------|--------|----------|--------------|
| **Phase 1** | 1a–1d Extract | Small | 1–2 days | None (non-breaking) |
| **Phase 2** | 2a–2b SplitView integration | Small | 1–2 days | Phase 1 complete |
| **Phase 3** | 3a–3b Type-aware rendering | Medium | 2–3 days | Phase 2 complete + Step 3 Backend (AttributeVisibilityConfig API) |
| **Phase 4** | 4a Admin UI | Small | 1 day | Phase 3 complete |

---

## Code Changes Summary

### Files to Create
- `frontend/src/components/SplitView/SplitView.tsx` ✅
- `frontend/src/components/SplitView/SplitView.module.scss` ✅
- `frontend/src/components/RequirementEditors/RequirementsList.tsx` (Phase 1a)
- `frontend/src/components/RequirementEditors/RequirementForm.tsx` (Phase 1b)
- `frontend/src/components/ArchitectureEditors/ArchitectureList.tsx` (Phase 1c)
- `frontend/src/components/ArchitectureEditors/ArchitectureForm.tsx` (Phase 1d)
- `frontend/src/components/AdminDialog/AttributeVisibilityAdmin.tsx` ✅
- `frontend/src/context/EntityTypeContext.tsx` ✅

### Files to Modify
- `frontend/src/components/RequirementEditors/RequirementEditors.tsx` (Phase 2a)
  - Delete: ~130 lines (split-pane state + handlers + old JSX)
  - Add: SplitView wrapper + data-passing
  - Net: ~50 line reduction

- `frontend/src/components/ArchitectureEditors/ArchitectureEditors.tsx` (Phase 2b)
  - Delete: ~110 lines (split-pane state + handlers + old JSX)
  - Add: SplitView wrapper + data-passing
  - Net: ~40 line reduction

- `frontend/src/components/WorkspaceSettings/WorkspaceSettings.tsx` (Phase 4a)
  - Add: AttributeVisibilityAdmin tab/section

### Files Unchanged
- `frontend/src/components/RequirementEditors/TraceabilityPanel.tsx`
- `frontend/src/components/RequirementEditors/MarkdownPreview.tsx`
- `frontend/src/components/ArchitectureEditors/ArchTraceLinkPanel.tsx`
- `frontend/src/components/ArchitectureEditors/DecompositionTree.tsx`
- API integration modules (requirements, architecture, tracelinks, etc.)

---

## Testing Strategy

### Phase 1: Unit Tests (Extract, no logic changes)
- Test RequirementsList renders correctly with passed props
- Test RequirementForm saves/deletes correctly
- Test ArchitectureList handles reparenting correctly
- Test ArchitectureForm updates correctly

### Phase 2: Integration Tests (SplitView integration)
- Test SplitView divider drag resize
- Test localStorage persistence
- Test responsive collapse on <768px
- Test RequirementEditors / ArchitectureEditors with SplitView render correct panels
- Test onDividerMove callback fires on resize

### Phase 3: Type-Aware Rendering Tests
- Test RequirementForm conditionally renders Moscow dropdown for StReq
- Test RequirementForm conditionally renders Complexity + Verification for SyReq
- Test ArchitectureForm conditionally renders ASIL + Make-or-Buy
- Test EntityTypeProvider hook returns correct context
- Test useEntityType throws error if used outside provider

### Phase 4: Admin UI Tests
- Test AttributeVisibilityAdmin saves visibility config
- Test entity type selector changes field checklist
- Test checkbox toggle updates visibility map
- Test error/success feedback messages

---

## Known Limitations & Future Work

1. **localStorage Key Scope:** Currently scoped per `moduleType` (e.g., "requirements"). May need workspace/user scope for multi-workspace support.

2. **Responsive Collapse:** Currently switches to tab-like toggle at <768px. Could be enhanced with drawer/modal on mobile in future iterations.

3. **AttributeVisibilityConfig API:** Endpoints not yet implemented in backend (Step 3 from Detailed Task). Admin UI is fully functional but will no-op until API is ready.

4. **Divider Visual Feedback:** Currently uses inline `onMouseEnter`/`onMouseLeave`. Could be enhanced with CSS pseudo-classes if needed.

5. **Accessibility:** SplitView divider needs `aria-label` and keyboard support (arrow keys to resize) for full a11y compliance.

---

## Rollback Plan

If issues arise during Phase 2:

1. Revert to previous version of RequirementEditors / ArchitectureEditors
2. Keep extracted sub-components (RequirementsList, etc.) for future use
3. Re-implement inline split-pane logic temporarily
4. Investigate root cause before re-attempting SplitView integration

**No database migrations required** — this is purely frontend refactoring.

---

## Sign-Off Criteria (DoD)

- [ ] Phase 1: All sub-components extract without breaking RequirementEditors / ArchitectureEditors
- [ ] Phase 2: SplitView integrates; divider resizes and persists correctly
- [ ] Phase 2: Responsive collapse works at <768px
- [ ] Phase 3: Type-dependent fields render/hide correctly (requires API endpoint)
- [ ] Phase 4: Admin UI integrates; saves visibility config (requires API endpoint)
- [ ] All tests pass
- [ ] Code review approved
- [ ] No new console errors/warnings
- [ ] Accessibility scan passes (WCAG 2.1 AA minimum)
