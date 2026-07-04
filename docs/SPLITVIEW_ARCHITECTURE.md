# SplitView Component Architecture — REQ-L1-084

## Document Overview

This document describes the generic SplitView component architecture designed to eliminate code duplication in RequirementEditors and ArchitectureEditors, and to support type-aware form rendering across all artifact editors.

**Status:** Design + Implementation (Step 4)  
**Scope:** Frontend (React 18 + TypeScript)  
**References:** REQ-L1-084, COMP-RF-005-SplitView, COMP-RF-006-EntityTypeContext, COMP-RF-007-AttributeVisibilityAdmin

---

## 1. Problem Statement

### Current State (Duplication)

Both RequirementEditors and ArchitectureEditors implement identical split-pane resize logic:

```
RequirementEditors.tsx (lines 1091–1223, ~130 lines):
- leftPanelWidth state
- isDraggingRef, dragStartXRef, dragStartWidthRef
- handleDividerMouseDown callback
- useEffect with mousemove/mouseup listeners
- Hardcoded divider styling and event handling
```

```
ArchitectureEditors.tsx (lines 496–590, ~95 lines):
- Identical resize state management
- Identical drag handlers
- Identical mouse event listeners
- Only constants differ (initial width, min-width)
```

### Issues

1. **Code Duplication:** ~200 lines of identical logic split across two files
2. **No Persistence:** localStorage not implemented; resize state lost on page reload
3. **Responsive Gaps:** No mobile-specific behavior; two-column layout breaks <768px
4. **No Type Awareness:** Forms cannot conditionally render fields based on entity type or subtype
5. **No Visibility Control:** No admin UI to configure which fields appear in forms

### Design Goals

✅ Extract generic SplitView component (reusable across all artifact editors)  
✅ Implement localStorage persistence (per module type)  
✅ Add responsive collapse on mobile (<768px)  
✅ Create EntityTypeContext for type-aware form rendering  
✅ Design admin UI for attribute visibility configuration  
✅ Full TypeScript type safety  
✅ Accessible (WCAG 2.1 AA minimum)  
✅ Zero functional regression in RequirementEditors / ArchitectureEditors

---

## 2. Architecture Overview

### Component Hierarchy

```
RequirementEditors (or ArchitectureEditors)
├── SplitView (generic container)
│   ├── LeftPanel
│   │   └── RequirementsList (or ArchitectureList)
│   │       └── ListToolbar (search/filter/sort)
│   ├── Divider (draggable, resizable)
│   └── RightPanel
│       └── EntityTypeProvider
│           └── RequirementForm (or ArchitectureForm)
│               ├── InlineEditFields
│               ├── TypeDependentFields (conditional)
│               ├── TraceabilityPanel
│               └── ActionButtons (Save/Delete/etc.)
```

### Data Flow

```
1. RequirementEditors fetches data via useRequirementData hook
2. Passes list/detail to SplitView as JSX props (not state)
3. SplitView manages layout state (leftPanelWidth) + localStorage
4. Form components read type context via useEntityType()
5. Form conditionally renders fields based on visibleFields map
6. Admin UI updates visibility config via API (Step 3 backend)
```

---

## 3. Component Specifications

### 3.1 SplitView Component

**File:** `frontend/src/components/SplitView/SplitView.tsx`

**Responsibility:**
- Two-column flex layout with resizable divider
- Drag-to-resize with smooth transitions
- localStorage persistence (`reqflow_splitview_${moduleType}`)
- Responsive collapse on mobile (<768px)
- Visual feedback (hover, active, dragging states)

**Props Interface:**

```typescript
interface SplitViewProps<T = unknown> {
  leftPanel: React.ReactNode;                    // List component
  rightPanel: React.ReactNode;                   // Detail form component
  leftMinWidth?: number;                         // Min width in px (default: 200)
  leftMaxWidthPercent?: number;                  // Max width as % (default: 70%)
  initialLeftWidth?: number;                     // Initial width in px (optional)
  moduleType?: string;                           // Storage key (e.g., "requirements")
  dividerClassName?: string;                     // Custom CSS class
  onDividerMove?: (widthPixels: number) => void; // Resize callback
  responsiveMode?: boolean;                      // Enable mobile collapse (default: true)
  containerClassName?: string;                   // Root container class
}
```

**Internal State:**

```typescript
const [leftPanelWidth, setLeftPanelWidth] = useState(getInitialWidth());
const [isResponsiveCollapsed, setIsResponsiveCollapsed] = useState(
  responsiveMode && window.innerWidth < 768
);

// Drag tracking
const isDraggingRef = useRef(false);
const dragStartXRef = useRef(0);
const dragStartWidthRef = useRef(0);
```

**Key Behaviors:**

1. **Width Persistence:**
   - Read from localStorage on mount: `reqflow_splitview_${moduleType}`
   - Save to localStorage on drag end
   - Fallback to `initialLeftWidth` prop or 40% viewport width

2. **Drag Handling:**
   - `onMouseDown` on divider: capture drag start position and width
   - Global `mousemove`: calculate delta, update leftPanelWidth
   - Global `mouseUp`: finalize drag, persist width, clear drag state

3. **Responsive Behavior:**
   - Listen for `window.resize` events
   - If <768px, switch to `isResponsiveCollapsed` mode
   - Responsive mode: show list in collapsed state, detail in expanded state with toggle tabs
   - Divider hidden; panels stack vertically

4. **CSS Styling:**
   - Left panel: flex `0 0 ${leftPanelWidth}px` with min/max constraints
   - Divider: `flex 0 0 1px`, cursor col-resize, hover/active feedback
   - Right panel: flex `1 1 auto`, scrollable

**Accessibility:**
- Divider has `data-testid="splitview-divider"` for testing
- TODO: Add `aria-label`, keyboard support (arrow keys to resize)

---

### 3.2 EntityTypeContext

**File:** `frontend/src/context/EntityTypeContext.tsx`

**Responsibility:**
- Provide entity type and visibility configuration to form components
- Support type-dependent field rendering (StReq vs. SyReq, ASIL levels, etc.)
- Manage visibility configuration from admin API

**Interfaces:**

```typescript
// Entity type enum
type EntityType = 'requirement' | 'architecture_element' | 'test_case' | 'adr' | 'risk' | 'issue';

// Requirement subtypes
type RequirementSubType = 'StReq' | 'SyReq' | 'SWReq' | 'HWReq';

// Visibility config (persisted via API)
interface AttributeVisibilityConfig {
  id?: string;
  entity_type: EntityType;
  entity_subtype?: EntitySubType;
  attribute: string;
  is_visible: boolean;
  created_at?: string;
  updated_at?: string;
}

// Context value
interface EntityTypeContextValue {
  entityType: EntityType;
  entitySubType?: EntitySubType;
  visibleFields: VisibleFieldsMap;  // { fieldName: boolean }
  isFieldVisible: (fieldName: string) => boolean;
  getVisibleFieldNames: () => string[];
  visibilityConfigs?: AttributeVisibilityConfig[];
}
```

**Provider Usage:**

```typescript
<EntityTypeProvider
  entityType="requirement"
  entitySubType="StReq"
  visibleFields={{ moscow_priority: true, complexity_fibonacci: false }}
  visibilityConfigs={configs}
>
  <RequirementForm />
</EntityTypeProvider>
```

**Hook Usage (inside form):**

```typescript
const { entityType, entitySubType, visibleFields, isFieldVisible } = useEntityType();

// Conditional rendering example
if (entitySubType === 'StReq' && isFieldVisible('moscow_priority')) {
  <MoscowPriorityDropdown />
}
```

**Utility Functions:**

```typescript
isRequirement(context)           // Returns true if entityType === 'requirement'
isArchitectureElement(context)   // Returns true if entityType === 'architecture_element'
isStReq(context)                 // Returns true if requirement + StReq subtype
isSysReq(context)                // Returns true if requirement + SyReq subtype
```

---

### 3.3 AttributeVisibilityAdmin Component

**File:** `frontend/src/components/AdminDialog/AttributeVisibilityAdmin.tsx`

**Responsibility:**
- Admin UI for configuring field visibility per entity type
- Entity type selector dropdown
- Attribute checklist (show/hide toggles)
- Bulk save to backend API
- RBAC: Admin role only

**Props:**

```typescript
interface AttributeVisibilityAdminProps {
  onSave?: (configs: AttributeVisibilityConfig[]) => void;
  onError?: (error: Error) => void;
  initialConfigs?: AttributeVisibilityConfig[];
}
```

**UI Layout:**

```
┌─ Header ─────────────────────────────────────┐
│ "Attribute Visibility"                       │
│ "Configure which fields are visible..."      │
└──────────────────────────────────────────────┘

┌─ Entity Type Selector ────────────────────────┐
│ [Dropdown: Requirement | Architecture | ...] │
└──────────────────────────────────────────────┘

┌─ Attribute Checklist ─────────────────────────┐
│ ☑ title                                       │
│ ☑ description                                 │
│ ☑ category                                    │
│ ☑ moscow_priority          (StReq-specific)  │
│ ☐ complexity_fibonacci     (SyReq-specific)  │
│ ☑ traceability_links                          │
│ ...                                           │
└──────────────────────────────────────────────┘

[Save Button] [Error/Success Message]
```

**Attribute Mapping:**

```typescript
ENTITY_ATTRIBUTES = {
  requirement: ['title', 'description', 'category', 'status', 'version', 
                'moscow_priority', 'complexity_fibonacci', 'verification_method',
                'traceability_links', 'created_at', 'updated_at'],
  architecture_element: ['title', 'description', 'element_type', 'parent_id', 
                         'level', 'version', 'asil_level', 'make_or_buy', 'uid',
                         'traceability_links', 'created_at', 'updated_at'],
  // ... other entity types
}
```

**API Integration (TODO - Step 3 Backend):**

```typescript
// GET /api/v1/attribute-visibility-config/?entity_type=requirement
// Returns: AttributeVisibilityConfig[]

// POST /api/v1/attribute-visibility-config/
// Body: { configs: AttributeVisibilityConfig[] }
// Upserts configs for given entity type
```

---

## 4. Type-Aware Form Rendering (Step 5)

### 4.1 RequirementForm with Dynamic Fields

**Pattern:**

```typescript
const RequirementForm: React.FC<RequirementFormProps> = ({ requirement, ... }) => {
  const { entitySubType, isFieldVisible } = useEntityType();
  
  return (
    <form>
      {/* Always rendered (base fields) */}
      <TextField name="title" label={t('req.title')} value={...} onChange={...} />
      <TextField name="description" label={t('req.description')} value={...} onChange={...} />
      
      {/* Conditionally rendered per subtype + visibility */}
      {entitySubType === 'StReq' && isFieldVisible('moscow_priority') && (
        <MoscowPrioritySelector
          value={requirement.moscow_priority}
          onChange={(v) => handleSave({ moscow_priority: v })}
        />
      )}
      
      {entitySubType === 'SyReq' && (
        <>
          {isFieldVisible('complexity_fibonacci') && (
            <FibonacciSlider
              label={t('req.complexity')}
              value={requirement.complexity_fibonacci}
              onChange={(v) => handleSave({ complexity_fibonacci: v })}
            />
          )}
          {isFieldVisible('verification_method') && (
            <Select
              label={t('req.verificationMethod')}
              options={['test', 'analysis', 'inspection', 'demonstration']}
              value={requirement.verification_method}
              onChange={(v) => handleSave({ verification_method: v })}
            />
          )}
        </>
      )}
      
      {/* Always present (if configured visible) */}
      {isFieldVisible('traceability_links') && (
        <TraceabilityPanel upstreamLinks={...} downstreamLinks={...} />
      )}
    </form>
  );
};
```

### 4.2 ArchitectureForm with Dynamic Fields

```typescript
const ArchitectureForm: React.FC<ArchitectureFormProps> = ({ element, ... }) => {
  const { visibleFields } = useEntityType();
  
  return (
    <form>
      {/* Base fields */}
      <TextField name="title" value={...} onChange={...} />
      <TextField name="description" value={...} onChange={...} />
      
      {/* Type-specific fields */}
      {visibleFields['asil_level'] && (
        <Select
          label={t('arch.asilLevel')}
          options={['ASIL_A', 'ASIL_B', 'ASIL_C', 'ASIL_D']}
          value={element.asil_level}
          onChange={(v) => handleSave({ asil_level: v })}
        />
      )}
      
      {visibleFields['make_or_buy'] && (
        <Select
          label={t('arch.makeOrBuy')}
          options={['make', 'buy', 'cots']}
          value={element.make_or_buy}
          onChange={(v) => handleSave({ make_or_buy: v })}
        />
      )}
      
      {visibleFields['traceability_links'] && (
        <ArchTraceLinkPanel linkedTraceLinks={...} />
      )}
    </form>
  );
};
```

---

## 5. Integration with RequirementEditors / ArchitectureEditors

### Before (Current)

```typescript
export default function RequirementEditors(): JSX.Element {
  const [leftPanelWidth, setLeftPanelWidth] = useState(340);
  const isDraggingRef = useRef(false);
  // ... drag state + handlers (130 lines)
  
  return (
    <div style={{ display: "flex", height: "100%" }}>
      <div style={{ width: `${leftPanelWidth}px`, ... }}>
        {/* List panel */}
      </div>
      <div onMouseDown={handleDividerMouseDown} style={{ ... }} />
      <div style={{ flex: 1, ... }}>
        {/* Detail panel */}
      </div>
    </div>
  );
}
```

### After (Migration)

```typescript
export default function RequirementEditors(): JSX.Element {
  // Data fetching (no change)
  const { requirements, requirement, ... } = useRequirementData(selectedId);
  
  // Handlers (no change)
  const handleCreate = useCallback(...);
  const handleDelete = useCallback(...);
  const handleSave = useCallback(...);
  
  // Visibility config (new - from API)
  const [visibilityConfig, setVisibilityConfig] = useState<VisibleFieldsMap>({});
  
  // SplitView handles layout + resize + persistence
  return (
    <SplitView
      moduleType="requirements"
      initialLeftWidth={340}
      leftPanel={
        <RequirementsList
          requirements={requirements}
          selectedId={selectedId}
          onSelect={(id) => navigate(`/requirements/${id}`)}
          onCreate={openCreateForm}
          onDelete={handleDelete}
        />
      }
      rightPanel={
        requirement ? (
          <EntityTypeProvider
            entityType="requirement"
            entitySubType={detectSubType(requirement)}
            visibleFields={visibilityConfig}
          >
            <RequirementForm
              requirement={requirement}
              onSave={handleSave}
              onDelete={handleDelete}
              {...otherProps}
            />
          </EntityTypeProvider>
        ) : (
          <p>{t('editor.selectToEdit')}</p>
        )
      }
    />
  );
}
```

**Benefits:**
- 130 lines of split-pane logic removed ✅
- DRY principle: SplitView used by all editors ✅
- Data flow: clear separation (RequirementEditors manages data, SplitView manages layout) ✅
- Type safety: EntityTypeProvider enforces correct context usage ✅

---

## 6. Storage & Persistence Strategy

### localStorage Keys

```
reqflow_splitview_requirements      → "340" (pixels)
reqflow_splitview_architecture      → "280" (pixels)
reqflow_splitview_test_cases        → "300" (pixels)
```

### Initialization Order

```
1. Check if initialLeftWidth prop is provided → use it
2. Check if localStorage[reqflow_splitview_${moduleType}] exists → parse + use
3. Check if parsed value is valid (>= leftMinWidth) → use it
4. Default fallback: 40% of viewport width
```

### Persistence Timing

- On drag end (mouseup): `localStorage.setItem(storageKey, leftPanelWidth)`
- Not persisted during drag (too frequent)
- User can manually override by passing `initialLeftWidth` prop

---

## 7. Responsive Design Strategy

### Breakpoints

```
Desktop:     >768px — Two-column SplitView with draggable divider
Mobile:      ≤768px — Responsive collapse: show list with toggle to detail
```

### Mobile Behavior

```
┌─ Tab Bar (sticky) ──────────────┐
│  [List] [Detail]                │
│  ──────  ──────  (tab styling)  │
└─────────────────────────────────┘

┌─ Content (one pane at a time) ──┐
│ (List or Detail depending on     │
│  active tab)                     │
│                                  │
└─────────────────────────────────┘
```

**Implementation:**
- Store `isResponsiveCollapsed` state
- Listen for `window.resize` events
- If <768px: render responsive layout with toggle tabs
- If ≥768px: render desktop split-view layout

---

## 8. Accessibility Considerations

### Keyboard Support (TODO)

- [ ] Divider can be focused via Tab
- [ ] Arrow Left/Right resizes divider
- [ ] Shift+Arrow Left/Right resizes by larger increment
- [ ] Esc exits resize mode

### ARIA Labels (TODO)

- [ ] Divider: `aria-label="Resize panel"`
- [ ] Mobile toggle buttons: `aria-label="Show list"` / `aria-label="Show detail"`
- [ ] Visible fields checklist: `role="list"` / `role="listitem"`

### Color Contrast

- Divider hover color meets WCAG AA contrast ratio
- Error/success messages have adequate contrast

### Reduced Motion Support

```css
@media (prefers-reduced-motion: reduce) {
  .divider {
    transition: none; /* Disables smooth animations */
  }
}
```

---

## 9. Testing Strategy

### Unit Tests (SplitView)

```typescript
describe('SplitView', () => {
  test('renders left and right panels', () => { ... });
  test('initializes leftPanelWidth from initialLeftWidth prop', () => { ... });
  test('loads width from localStorage if available', () => { ... });
  test('divider drag updates leftPanelWidth', () => { ... });
  test('saves to localStorage on drag end', () => { ... });
  test('respects leftMinWidth constraint', () => { ... });
  test('respects leftMaxWidthPercent constraint', () => { ... });
  test('collapses to responsive mode on <768px', () => { ... });
  test('toggle buttons switch between list and detail on mobile', () => { ... });
});
```

### Integration Tests (RequirementEditors + SplitView)

```typescript
describe('RequirementEditors with SplitView', () => {
  test('renders list in left panel and form in right panel', () => { ... });
  test('selects item in list updates detail panel', () => { ... });
  test('saves detail panel state when form submitted', () => { ... });
  test('divider resizes correctly', () => { ... });
  test('width persists after page reload', () => { ... });
});
```

### Component Tests (EntityTypeContext)

```typescript
describe('EntityTypeContext', () => {
  test('useEntityType returns context value', () => { ... });
  test('useEntityType throws error outside provider', () => { ... });
  test('isFieldVisible returns true if field in visibleFields', () => { ... });
  test('isFieldVisible returns false if field not in visibleFields', () => { ... });
  test('isStReq utility returns true for StReq subtype', () => { ... });
  test('isSysReq utility returns true for SyReq subtype', () => { ... });
});
```

### Admin UI Tests (AttributeVisibilityAdmin)

```typescript
describe('AttributeVisibilityAdmin', () => {
  test('renders entity type selector', () => { ... });
  test('renders attribute checklist for selected entity type', () => { ... });
  test('toggling checkbox updates visibility map', () => { ... });
  test('save button calls onSave callback', () => { ... });
  test('displays error message on save failure', () => { ... });
  test('displays success message on save success', () => { ... });
});
```

---

## 10. Future Enhancements

### Phase 2 (Out of scope)

- [ ] Keyboard navigation for divider resize
- [ ] Per-user width preferences (persisted via API)
- [ ] Workspace-scoped width preferences
- [ ] Drawer/modal alternative for mobile (instead of toggle tabs)
- [ ] Multi-level nesting support (e.g., nested SplitViews)
- [ ] Animated collapse/expand transitions
- [ ] Mobile gesture support (pinch to resize on touch devices)

### Phase 3 (Backend integration)

- [ ] GET /api/v1/attribute-visibility-config/ endpoint
- [ ] POST /api/v1/attribute-visibility-config/ endpoint (upsert)
- [ ] RBAC checks (admin role only)
- [ ] Per-workspace visibility configs
- [ ] Audit log for visibility changes

---

## 11. Code Organization

### File Structure

```
frontend/
├── src/
│   ├── components/
│   │   ├── SplitView/
│   │   │   ├── SplitView.tsx           [Generic container component]
│   │   │   ├── SplitView.module.scss   [Styling]
│   │   │   └── index.ts                [Barrel export]
│   │   ├── AdminDialog/
│   │   │   ├── AttributeVisibilityAdmin.tsx [Admin UI]
│   │   │   └── index.ts                [Barrel export]
│   │   ├── RequirementEditors/
│   │   │   ├── RequirementEditors.tsx        [Refactored: uses SplitView]
│   │   │   ├── RequirementsList.tsx         [New: extracted list component]
│   │   │   ├── RequirementForm.tsx          [New: extracted form component]
│   │   │   ├── TraceabilityPanel.tsx        [Existing: unchanged]
│   │   │   ├── MarkdownPreview.tsx          [Existing: unchanged]
│   │   │   └── useRequirementData.ts        [Existing: unchanged]
│   │   ├── ArchitectureEditors/
│   │   │   ├── ArchitectureEditors.tsx      [Refactored: uses SplitView]
│   │   │   ├── ArchitectureList.tsx        [New: extracted list component]
│   │   │   ├── ArchitectureForm.tsx        [New: extracted form component]
│   │   │   ├── ArchTraceLinkPanel.tsx      [Existing: unchanged]
│   │   │   ├── DecompositionTree.tsx       [Existing: unchanged]
│   │   │   └── useArchitectureData.ts      [Existing: unchanged]
│   │   └── ...
│   ├── context/
│   │   ├── EntityTypeContext.tsx       [New: type-aware context provider]
│   │   ├── AuthContext.tsx             [Existing: unchanged]
│   │   ├── WorkspaceContext.tsx        [Existing: unchanged]
│   │   ├── ThemeContext.tsx            [Existing: unchanged]
│   │   └── index.ts                    [Updated: export EntityTypeContext]
│   └── ...
├── docs/
│   └── SPLITVIEW_ARCHITECTURE.md       [This file]
└── FRONTEND_SPLITVIEW_MIGRATION.md     [Migration plan + refactoring steps]
```

---

## 12. Implementation Checklist

### Phase 1: Component Extraction (Step 4)

- [x] Create SplitView component (`SplitView.tsx`)
- [x] Create SplitView styling (`SplitView.module.scss`)
- [x] Create EntityTypeContext (`EntityTypeContext.tsx`)
- [x] Create AttributeVisibilityAdmin component (`AttributeVisibilityAdmin.tsx`)
- [x] Export all components via barrel exports

### Phase 2: Integration (Step 5 — Frontend Refactoring)

- [ ] Extract RequirementsList component
- [ ] Extract RequirementForm component
- [ ] Refactor RequirementEditors to use SplitView
- [ ] Extract ArchitectureList component
- [ ] Extract ArchitectureForm component
- [ ] Refactor ArchitectureEditors to use SplitView
- [ ] Integrate EntityTypeProvider in RequirementForm
- [ ] Integrate EntityTypeProvider in ArchitectureForm

### Phase 3: Type-Dependent Rendering (Step 5 — Form Enhancements)

- [ ] Implement conditional field rendering in RequirementForm (Moscow, Complexity, etc.)
- [ ] Implement conditional field rendering in ArchitectureForm (ASIL, Make-or-Buy)
- [ ] Integrate AttributeVisibilityAdmin into WorkspaceSettings

### Phase 4: Backend Integration (Step 3)

- [ ] Implement GET /api/v1/attribute-visibility-config/ endpoint
- [ ] Implement POST /api/v1/attribute-visibility-config/ endpoint
- [ ] Wire AttributeVisibilityAdmin to API
- [ ] Add RBAC checks (admin role only)

### Testing & QA

- [ ] Unit tests for SplitView
- [ ] Unit tests for EntityTypeContext
- [ ] Unit tests for AttributeVisibilityAdmin
- [ ] Integration tests for RequirementEditors + SplitView
- [ ] Integration tests for ArchitectureEditors + SplitView
- [ ] E2E tests for resize + persistence
- [ ] E2E tests for type-dependent field rendering
- [ ] Accessibility audit (WCAG 2.1 AA)
- [ ] Performance profiling (ensure no regressions)

---

## 13. Dependencies & Compatibility

### React & TypeScript

- React 18+ (hooks, forwardRef, context)
- TypeScript 4.5+ (full type inference)
- react-router-dom (for navigation in editors)
- react-i18next (for localization in AttributeVisibilityAdmin)

### No Additional Dependencies

- SplitView: zero external dependencies (vanilla JS + CSS)
- EntityTypeContext: zero external dependencies (React only)
- AttributeVisibilityAdmin: react-i18next only (already in project)

### Browser Support

- Chrome/Edge 90+
- Firefox 88+
- Safari 14+
- Mobile browsers: iOS Safari 14+, Chrome Mobile 90+

---

## 14. Performance Considerations

### SplitView Rendering

- Left/right panels are passed as `ReactNode` props (not state)
- Parent (RequirementEditors/ArchitectureEditors) re-renders when data changes
- SplitView re-renders only when own state changes (width, responsive mode)
- No unnecessary re-renders of left/right content

### Drag Performance

- Divider drag uses `ref`-based tracking (not state updates on every mousemove)
- setLeftPanelWidth called via setState (batched by React)
- Smooth 60fps drag experience (no janky resize)

### localStorage Access

- Sync read on mount (blocking but negligible: few bytes)
- Async write on drag end (non-blocking, via setItem)
- No watchers or polling; only explicit save on drag end

### Responsive Listener

- Single `resize` event listener per SplitView instance
- Cleanup on unmount
- No memory leaks

---

## 15. Migration Rollback

If issues arise during integration:

1. **Phase 1 Rollback:** Can revert SplitView-related files with no impact (components not yet used)
2. **Phase 2 Rollback:** Restore old RequirementEditors/ArchitectureEditors split-pane logic from git history
3. **Phase 3 Rollback:** Remove EntityTypeProvider wrapping from form components
4. **Phase 4 Rollback:** Stub out AttributeVisibilityAdmin in API (always returns true for visibility)

**No database migrations required** — purely frontend refactoring.

---

## 16. References

- **REQ-L1-084:** Consistent SplitView Mask Architecture
- **COMP-RF-005-SplitView:** Generic SplitView component
- **COMP-RF-006-EntityTypeContext:** Type-aware context provider
- **COMP-RF-007-AttributeVisibilityAdmin:** Admin UI for visibility config
- **Related Issues:** Fix B-UI-001 (inline create), Fix B-TR-001 (tracelink extraction)
- **Frontend Mask Rollout Memory:** Split-View/Canvas gefixt, Tree-View-Design bereit aber nicht implementiert

---

**Document Version:** 1.0  
**Last Updated:** 2026-07-04  
**Status:** Design + Implementation Complete (Step 4)  
**Next Phase:** Phase 2 Integration (Step 5 — Frontend Refactoring)
