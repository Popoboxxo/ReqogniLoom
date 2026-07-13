# ReqFlow UI Style Guide

> **Scope:** Frontend — React 18 + TypeScript  
> **Derived from:** Analysis of the established Split-View pattern across NeedsEditors,
> RequirementEditors, ArchitectureEditors, and the shared `SplitView` component.  
> **Companion:** `docs/UI_STANDARDS.md` covers the ArtifactInspector (unified right
> sidebar) specifically; this document covers the broader component vocabulary.  
> **Status:** Design specification — implementations MUST follow this contract.

---

## Table of Contents

1. [Split-View Layout Pattern](#1-split-view-layout-pattern)
2. [ListToolbar Pattern](#2-listtoolbar-pattern)
3. [List Item / Card Pattern](#3-list-item--card-pattern)
4. [Form Pattern](#4-form-pattern)
5. [Error Handling Standards](#5-error-handling-standards)
6. [Confirmation Dialogs](#6-confirmation-dialogs)
7. [Loading States](#7-loading-states)
8. [Status Badges](#8-status-badges)
9. [Action Buttons](#9-action-buttons)
10. [Feedback / Toast Notifications](#10-feedback--toast-notifications)
11. [Design Tokens Reference](#11-design-tokens-reference)

---

## 1. Split-View Layout Pattern

Every artifact mask uses `SplitView` (`frontend/src/components/SplitView/SplitView.tsx`).
The left panel holds the list + toolbar; the right panel holds the detail form + the
ArtifactInspector sidebar.

### 1.1 Standard usage

```tsx
<SplitView
  leftPanel={<NeedList ... />}
  rightPanel={
    <div style={{ display: 'flex', height: '100%', minHeight: 0, gap: 'var(--space-3)' }}>
      <div style={{ flex: '1 1 auto', minWidth: 0, overflow: 'auto' }}>
        <NeedForm ... />
      </div>
      {need && <RightSidebar kind="stakeholderNeed" artifactId={need.id} currentVersion={...} />}
    </div>
  }
  moduleType="needs"           // ← REQUIRED: unique per mask for localStorage
  leftMinWidth={260}           // minimum 200px, recommended 260–350px per mask
  leftMaxWidthPercent={70}     // default; do not increase above 70
  initialLeftWidth={350}       // only if you want to override the stored width
/>
```

### 1.2 `moduleType` is mandatory

Every `SplitView` MUST receive a unique `moduleType` so that the left-panel width is
stored under a mask-specific localStorage key (`reqflow_splitview_<moduleType>`).

| Mask               | `moduleType`          |
|--------------------|-----------------------|
| Requirements       | `"requirements"`      |
| Architecture       | `"architecture"`      |
| Stakeholder Needs  | `"needs"`             |
| ADRs               | `"adrs"`              |
| Risks              | `"risks"`             |
| Test Cases         | `"testcases"`         |
| Test Runs          | `"testruns"`          |

Omitting `moduleType` defaults to `"default"`, which causes all masks that omit it
to share the same stored width — a persistent UX bug.

### 1.3 Dimensions

| Constraint          | Value                      |
|---------------------|----------------------------|
| Left panel min      | 260 px (Requirements); 350 px (Needs) |
| Left panel max      | 70% of container           |
| Right panel         | `flex: 1 1 auto` — fills remaining space |
| Divider             | 1 px, expands to 3 px on hover, color `var(--color-primary)` |
| Mobile breakpoint   | < 768 px → stacked tab layout (built into `SplitView`) |

### 1.4 Loading and error state wiring

The container component (e.g. `NeedsEditors`) MUST handle the loading and error
states returned by its data hook before rendering `SplitView`:

```tsx
const { needs, need, isLoading, error, refresh } = useNeedData(selectedId);

if (isLoading) {
  return <p role="status">{t('loading')}</p>;
}

if (error) {
  return (
    <div role="alert">
      <p style={{ color: 'var(--color-danger)' }}>{error.message}</p>
      <button className="btn-secondary" onClick={refresh}>{t('actions.reload')}</button>
    </div>
  );
}

return <SplitView ... />;
```

Reference: `RequirementEditors.tsx` lines 178–191 is the canonical implementation.

---

## 2. ListToolbar Pattern

All left-panel lists use the shared `ListToolbar` component
(`frontend/src/components/shared/ListToolbar.tsx`). Do not re-implement search/filter
inline — always delegate to `ListToolbar`.

### 2.1 Standard wiring

```tsx
<ListToolbar
  testIdPrefix="need-list"           // used for data-testid attributes in tests
  searchValue={listSearch}
  onSearchChange={setListSearch}
  searchPlaceholder={t('editor.searchPlaceholder', 'Search needs...')}
  filters={[
    {
      id: 'status',
      allLabel: t('editor.allStatuses'),
      value: statusFilter,
      options: WORKFLOW_STATES.map(s => ({ value: s, label: s })),
      onChange: setStatusFilter,
    },
  ]}
  sortValue={sortKey}
  sortOptions={[
    { value: 'default', label: t('editor.sortDefault') },
    { value: 'title',   label: t('editor.sortTitleAsc') },
    { value: 'status',  label: t('editor.sortStatus') },
    { value: 'updated', label: t('editor.sortUpdatedDesc') },
  ]}
  onSortChange={val => setSortKey(val as SortKey)}
  sortLabel={t('editor.sortLabel')}
  countLabel={
    hasActiveListControls
      ? t('editor.filteredCount', { shown: visible.length, total: all.length })
      : null
  }
/>
```

### 2.2 Create button placement

The "+ New" button lives **below** the `ListToolbar` and **above** the item list.
It should use `className="btn-primary"` (see §9) with `data-testid="create-<entity>-btn"`.

When the inline create form is shown, disable the create button (`disabled={showCreateForm}`)
so the user cannot open a second form.

### 2.3 Filter design

- **Maximum 2 filter dropdowns** in the filter row. Additional filters should use an
  "Advanced filters" popover (not yet implemented — design TBD).
- Each filter has an "All …" first option with `value=""` so the filter can be cleared.
- Active filter state is shown via the `countLabel` ("12 of 240 shown").

---

## 3. List Item / Card Pattern

### 3.1 Structure

Each list item is an `<li>` inside a `<ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>`.
The card is a clickable area that navigates to the detail view.

```tsx
<li
  style={getCardStyle(isActive, isHovered)}
  onMouseEnter={() => setHoveredId(item.id)}
  onMouseLeave={() => setHoveredId(null)}
>
  <a
    href={`/needs/${item.id}`}
    onClick={(e) => { e.preventDefault(); navigate(`/needs/${item.id}`); }}
    style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 'var(--space-2)',
             textDecoration: 'none', color: 'inherit' }}
  >
    <span style={{ fontWeight: 600, fontSize: 'var(--font-size-base)', color: 'var(--color-text)' }}>
      {item.title}
    </span>
    <div style={{ display: 'flex', gap: 'var(--space-2)', alignItems: 'center', flexWrap: 'wrap' }}>
      {item.uid && <span style={uidStyle}>{item.uid}</span>}
      <span style={getStatusBadgeStyle(item.status)}>{item.status}</span>
    </div>
  </a>
</li>
```

### 3.2 Card styles

```ts
function getCardStyle(isActive: boolean, isHovered: boolean): React.CSSProperties {
  return {
    background: isActive
      ? 'rgba(99, 102, 241, 0.15)'       // --color-primary at 15% opacity — theme-safe
      : isHovered
      ? 'var(--color-surface-raised)'
      : 'var(--color-surface)',
    borderLeft: isActive ? '3px solid var(--color-primary)' : '3px solid transparent',
    borderRadius: 'var(--radius-md)',
    boxShadow: isHovered || isActive ? 'var(--shadow-card)' : 'var(--shadow-sm)',
    padding: 'var(--space-3) var(--space-4)',
    marginBottom: 'var(--space-2)',
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    cursor: 'pointer',
    transition: 'var(--transition-fast)',
    wordBreak: 'break-word',
  };
}
```

**DO NOT** use `background: '#eef2ff'` (hardcoded hex, breaks dark mode). Use the
`rgba(99, 102, 241, 0.15)` form or add a `--color-card-selected` token to `tokens.css`.

### 3.3 UID style

```ts
const uidStyle: React.CSSProperties = {
  fontSize: '0.75rem',              // no --font-size-xs token exists; use literal
  color: 'var(--color-text-muted)',
  fontFamily: 'monospace',
};
```

Note: `var(--font-size-xs)` is **not** defined in `tokens.css` — use the literal
`'0.75rem'` until the token is added.

### 3.4 Hierarchy / indentation

When the data model has a `parent_id` field (Requirements, StakeholderNeeds), the list
SHOULD indent child items visually. Use `marginLeft: \`calc(${depth} * var(--space-4))\``.
The `getDepth` helper from `RequirementList.tsx` is the reference implementation.

### 3.5 Empty states

```tsx
// No items at all
{items.length === 0 && (
  <p style={{ color: 'var(--color-text-muted)', fontSize: 'var(--font-size-sm)' }}>
    {t('editor.empty', 'No items available.')}
  </p>
)}

// Items exist but none match the current filter
{items.length > 0 && visible.length === 0 && (
  <p data-testid="<entity>-list-no-matches"
     style={{ color: 'var(--color-text-muted)', fontSize: 'var(--font-size-sm)' }}>
    {t('editor.noMatches', 'No matches found.')}
  </p>
)}
```

---

## 4. Form Pattern

### 4.1 Field order (standard)

1. **Header bar** — UID (monospace, muted), status badge (read-only display), version badge, action buttons (Save, Delete)
2. **Section: General Information** — Title (required, with asterisk), Description (MarkdownPreview)
3. **Section: Classification & Properties** — grid of dropdowns (Category, Status/WorkflowState, Type, etc.)
4. **Section: Change Control** (extended preset only) — Change Reason textarea
5. **Inline error message** (`<p role="alert">`) — rendered directly above the action buttons when save fails
6. **Action buttons** — Save (primary), secondary actions (View Diff, etc.)
7. **TraceLink / Derive panel** — below the main form fields

The action buttons MUST also appear in the **form header** for long forms (so the user
does not need to scroll to save). The header placement is primary; the footer placement
is secondary.

### 4.2 Required fields

Mark required fields with `<span style={{ color: 'var(--color-danger)' }}>*</span>`
in the label. Validate client-side before the API call:

```tsx
const validateForm = (): string | null => {
  if (!title.trim()) return t('editor.titleRequired');
  // ... additional rules
  return null;
};

const handleSave = async () => {
  const err = validateForm();
  if (err) { setSaveError(err); return; }
  // ...
};
```

### 4.3 Label-to-input association

Every label MUST use `htmlFor` paired with a matching `id` on the input. This is
required for accessibility.

```tsx
<label htmlFor="need-title" style={labelStyle}>
  {t('editor.title')} <span style={{ color: 'var(--color-danger)' }}>*</span>
</label>
<input id="need-title" data-testid="need-title" value={title} onChange={...} style={inputStyle} />
```

### 4.4 Standard `inputStyle` and `labelStyle`

```ts
const inputStyle: React.CSSProperties = {
  width: '100%',
  border: '1px solid var(--color-border)',
  borderRadius: 'var(--radius-md)',
  padding: 'var(--space-3)',
  fontFamily: 'var(--font-sans)',
  fontSize: 'var(--font-size-base)',
  marginBottom: 'var(--space-4)',
  color: 'var(--color-text)',
  background: 'var(--color-surface)',
  boxSizing: 'border-box',
};

const labelStyle: React.CSSProperties = {
  fontWeight: 500,
  color: 'var(--color-text)',
  display: 'block',
  marginBottom: 'var(--space-1)',
};
```

### 4.5 Status field

All entity forms MUST expose a status/workflow-state `<select>` field that allows
the user to change the workflow state. The status badge in the header is read-only
(display only). Use `WORKFLOW_STATES` from `frontend/src/types/index.ts` for the
option list.

```tsx
<label htmlFor="need-status" style={labelStyle}>{t('editor.workflowState')}</label>
<select
  id="need-status"
  data-testid="need-status"
  value={formData.status || ''}
  onChange={(e) => handleChange('status', e.target.value)}
  style={inputStyle}
>
  {WORKFLOW_STATES.map(s => <option key={s} value={s}>{s}</option>)}
</select>
```

### 4.6 Form container

```tsx
<div style={{
  background: 'var(--color-surface)',
  borderRadius: 'var(--radius-lg)',
  boxShadow: 'var(--shadow-card)',
  padding: 'var(--space-6)',
  flex: 1,
}}>
  {/* Header, Sections, Error, Buttons */}
</div>
```

---

## 5. Error Handling Standards

### Hard rule: NEVER use `alert()` or `window.alert()`

`alert()` blocks the browser's event loop, cannot be styled, breaks in CSP-strict
and embedded environments, and cannot be dismissed programmatically. Replace every
occurrence with inline error state.

### 5.1 Inline save error (standard pattern)

```tsx
// State
const [saveError, setSaveError] = useState<string | null>(null);

// In handleSave catch block
} catch (err: unknown) {
  const msg = (err as { error?: { message?: string } })?.error?.message ?? String(err);
  setSaveError(msg);
} finally {
  setIsSaving(false);
}

// In JSX — render directly above the action buttons
{saveError && (
  <p
    role="alert"
    style={{ color: 'var(--color-danger)', marginBottom: 'var(--space-4)', fontSize: 'var(--font-size-sm)' }}
  >
    {saveError}
  </p>
)}
```

Reference: `RequirementForm.tsx` lines 420–425.

### 5.2 Inline create error

In the inline create form (e.g. `NeedList`), the create error belongs inside the
create form panel, rendered below the input:

```tsx
{createError && (
  <p role="alert" style={{ color: 'var(--color-danger)', fontSize: 'var(--font-size-sm)', margin: 0 }}>
    {createError}
  </p>
)}
```

The error state lives in the container component (e.g. `NeedsEditors`) and is passed
down as a prop to the list component. Clear the error when the form is closed.

### 5.3 Load error (page-level)

```tsx
if (error) {
  return (
    <div role="alert" style={{ padding: 'var(--space-8)' }}>
      <p style={{ color: 'var(--color-danger)', marginBottom: 'var(--space-4)' }}>
        {error instanceof Error ? error.message : String(error)}
      </p>
      <button className="btn-secondary" onClick={refresh}>{t('actions.reload')}</button>
    </div>
  );
}
```

### 5.4 Error clearing

Clear the save error when:
- The user starts editing any field (clear on first change after an error)
- The form is reset / a new item is selected

---

## 6. Confirmation Dialogs

### Hard rule: NEVER use `window.confirm()`

`window.confirm()` has the same blocking/styling problems as `alert()`. All delete
confirmations use an inline confirmation pattern.

### 6.1 Inline confirmation pattern (preferred)

Replace the delete button with a two-step confirmation rendered inline:

```tsx
const [confirmDelete, setConfirmDelete] = useState(false);

// In JSX — header action area
{!confirmDelete ? (
  <button
    className="btn-danger"
    onClick={() => setConfirmDelete(true)}
  >
    {t('actions.delete')}
  </button>
) : (
  <div style={{ display: 'flex', gap: 'var(--space-2)', alignItems: 'center' }}>
    <span style={{ fontSize: 'var(--font-size-sm)', color: 'var(--color-text-muted)' }}>
      {t('actions.deleteConfirmPrompt', 'Delete?')}
    </span>
    <button className="btn-danger" onClick={handleDelete} disabled={isDeleting}>
      {isDeleting ? t('actions.deleting') : t('actions.confirmDelete', 'Yes, delete')}
    </button>
    <button className="btn-ghost" onClick={() => setConfirmDelete(false)}>
      {t('actions.cancel')}
    </button>
  </div>
)}
```

### 6.2 When to use a modal

Use a modal confirmation dialog (not yet a shared component — design TBD) for
destructive operations that affect **multiple items** (e.g. bulk delete, clear
baseline). For single-item deletes, the inline pattern (§6.1) is preferred.

### 6.3 Delete error handling

A failed delete MUST display an error, never silently fail:

```tsx
const handleDelete = async () => {
  setIsDeleting(true);
  try {
    await api.delete(item.id);
    onDeleted();
  } catch (err: unknown) {
    const msg = (err as { error?: { message?: string } })?.error?.message ?? t('actions.deleteFailed');
    setDeleteError(msg);
    setConfirmDelete(false);  // reset to normal state
  } finally {
    setIsDeleting(false);
  }
};
```

---

## 7. Loading States

### 7.1 Page-level loading (initial data fetch)

```tsx
if (isLoading) {
  return <p role="status" style={{ padding: 'var(--space-8)', color: 'var(--color-text-muted)' }}>
    {t('loading')}
  </p>;
}
```

This is the minimal implementation. For a richer experience, a spinner or skeleton
screen is preferred (see §7.3).

### 7.2 Button loading state

When a mutation (save, create, delete) is in flight, the triggering button MUST show
a loading label and be `disabled`:

```tsx
<button className="btn-primary" onClick={handleSave} disabled={isSaving}>
  {isSaving ? t('actions.saving') : t('actions.save')}
</button>
```

All other action buttons in the same area SHOULD also be disabled while a mutation
is in flight to prevent concurrent submits.

### 7.3 Skeleton / spinner (future standard)

When a skeleton screen component is available, use it for list loading to avoid
layout shift. Until then, the `role="status"` text message is acceptable for the
initial load. **Never** show a blank screen with no loading indicator.

### 7.4 Async task status

For long-running backend tasks (e.g. AI-driven requirement derivation), do NOT use
`setTimeout` to fake completion. Instead:

1. Show an in-progress label with a spinner (`isDeriving` state).
2. Poll the task endpoint or use a WebSocket event.
3. On confirmed completion, show the success state (see §10 for notification pattern).

Hardcoded timeouts that pretend an async task succeeded are a blocking bug.

---

## 8. Status Badges

All entity status badges use the same shared function. Extract this to
`frontend/src/utils/statusBadge.ts` (to-do — currently duplicated in
`NeedList.tsx`, `RequirementList.tsx`, etc.).

### 8.1 Standard `getStatusBadgeStyle`

```ts
// frontend/src/utils/statusBadge.ts
export function getStatusBadgeStyle(status: string): React.CSSProperties {
  const base: React.CSSProperties = {
    borderRadius: 'var(--radius-full)',
    fontSize: 'var(--font-size-sm)',
    padding: '2px 8px',
    fontWeight: 500,
    whiteSpace: 'nowrap',
  };
  switch (status) {
    case 'approved':
      return { ...base, background: 'var(--color-badge-approved)', color: 'var(--color-badge-approved-text)' };
    case 'review':
      return { ...base, background: 'var(--color-badge-review)', color: 'var(--color-badge-review-text)' };
    case 'rejected':
    case 'deprecated':
      return { ...base, background: 'var(--color-badge-danger)', color: 'var(--color-badge-danger-text)' };
    default: // draft, new, etc.
      return { ...base, background: 'var(--color-badge-draft)', color: 'var(--color-badge-draft-text)' };
  }
}
```

### 8.2 Required tokens in `tokens.css`

The following tokens MUST be added to `tokens.css` (dark and light variants):

| Token (dark default)           | Value (dark)              | Value (light)            |
|--------------------------------|---------------------------|--------------------------|
| `--color-badge-review`         | `rgba(59, 130, 246, 0.2)` | `rgba(59, 130, 246, 0.12)` |
| `--color-badge-review-text`    | `#93c5fd`                 | `#1d4ed8`                |
| `--color-badge-danger`         | `rgba(239, 68, 68, 0.2)`  | `rgba(220, 38, 38, 0.12)` |
| `--color-badge-danger-text`    | `#fca5a5`                 | `#b91c1c`                |

**DO NOT** use hardcoded hex values like `#bee3f8`, `#2c5282`, `#fed7d7`, `#9b2c2c` in
badge styles — they break dark mode. All badge colors MUST go through CSS variables.

### 8.3 Status semantic meanings

| Status        | Color class  | Meaning                          |
|---------------|--------------|----------------------------------|
| `draft`       | badge-draft  | Work in progress, not reviewed   |
| `review`      | badge-review | Under formal review              |
| `approved`    | badge-approved | Signed off                     |
| `rejected`    | badge-danger | Rejected; see linked decision    |
| `deprecated`  | badge-danger | Superseded; do not use           |

### 8.4 Type badges (Requirements only)

Requirement type badges use solid colored backgrounds with white text:

| Type    | Color token / value             |
|---------|---------------------------------|
| `StReq` | `#6B7280` (gray)                |
| `SyReq` | `#10B981` (emerald)             |
| `SWReq` | `#8B5CF6` (violet)              |
| `HWReq` | `#F59E0B` (amber)               |

These values should be moved to CSS tokens in a future cleanup.

---

## 9. Action Buttons

ReqFlow uses CSS class-based buttons defined in `frontend/src/styles/global.css`.
Use these classes — do not recreate button styles with inline styles.

### 9.1 Button hierarchy

| Class          | Use case                                      | Color              |
|----------------|-----------------------------------------------|--------------------|
| `btn-primary`  | Primary confirm action (Save, Create, Submit) | `--color-primary`  |
| `btn-secondary`| Secondary action (View Diff, CSV Import)      | Bordered, no fill  |
| `btn-danger`   | Irreversible destructive action (Delete)      | `--color-danger`   |
| `btn-ghost`    | Cancel, dismiss, low-emphasis action          | No border, subtle  |

### 9.2 Button placement in forms

```
[header area]    [Delete btn-danger]  [Save btn-primary]
[footer area]    [Save btn-primary]   [Secondary btn-secondary]
```

- The **Delete** button is always to the **left** of the Save button.
- The **Save** button is always the **rightmost** primary action.
- On mobile (< 768 px), stack buttons vertically, full width.

### 9.3 Disabled state

- Disabled buttons use `opacity: 0.6` and `cursor: not-allowed`.
- Add a `title` tooltip to disabled buttons explaining why they are disabled when the
  reason is not self-evident.

### 9.4 Icon-only buttons

Icon-only buttons (delete × in list items, toolbar icons) MUST have a `title` attribute
for screen readers:

```tsx
<button
  data-testid="need-delete-btn"
  onClick={(e) => { e.stopPropagation(); onDelete(item.id); }}
  title={t('actions.delete')}
  style={{
    background: 'none', border: 'none', color: 'var(--color-danger)',
    cursor: 'pointer', fontSize: 'var(--font-size-base)', fontWeight: 700,
  }}
>
  ×
</button>
```

---

## 10. Feedback / Toast Notifications

ReqFlow does not yet have a shared Toast/Snackbar component. Until one is built,
use the inline error pattern (§5) for errors and the inline status text pattern for
async feedback.

### 10.1 Async derivation status (interim pattern)

Until a global toast provider is available, show async task status inline below the
triggering button:

```tsx
{derivationStatus && (
  <p
    role="status"
    style={{
      marginTop: 'var(--space-2)',
      fontSize: 'var(--font-size-sm)',
      color: derivationStatus.isError ? 'var(--color-danger)' : 'var(--color-text-muted)',
    }}
  >
    {derivationStatus.message}
  </p>
)}
```

### 10.2 Future Toast component contract

When a shared `<Toast>` component is added, it MUST:

- Be rendered in a portal above all other content (top-right or bottom-right corner)
- Support severity levels: `success` | `error` | `warning` | `info`
- Auto-dismiss after 5 s (success/info) or require explicit dismiss (error/warning)
- Use these tokens for backgrounds:

| Severity  | Background token         | Text                |
|-----------|--------------------------|---------------------|
| `success` | `--color-success`        | `white`             |
| `error`   | `--color-danger`         | `white`             |
| `warning` | `--color-warning`        | `white`             |
| `info`    | `--color-primary`        | `white`             |

- Expose a context hook: `const { toast } = useToast();` so any component can call
  `toast.success(t('needs.saved'))` without prop-drilling.
- Replace all `alert()` calls with `toast.error(msg)` when the component is available.

### 10.3 Success feedback (current interim)

Until the Toast component exists, a successful save does not need a visual confirmation
beyond the version badge incrementing (which is already visible in the form header).
Do **not** add a separate `alert('Saved!')` call — the absence of an error is sufficient
feedback for non-destructive operations.

---

## 11. Design Tokens Reference

All tokens are defined in `frontend/src/styles/tokens.css`. Dark is the default theme;
light is activated by `data-theme="light"` on `<html>`.

### 11.1 Colors

| Token                       | Dark value            | Light value           | Usage                         |
|-----------------------------|-----------------------|-----------------------|-------------------------------|
| `--color-primary`           | `#6366f1`             | `#4f46e5`             | Primary accent, active states |
| `--color-primary-dark`      | `#4f46e5`             | `#4338ca`             | Hover state for primary       |
| `--color-surface`           | `#0f172a`             | `#f8fafc`             | Page / card background        |
| `--color-surface-raised`    | `#1e293b`             | `#ffffff`             | Elevated card, form header    |
| `--color-border`            | `#334155`             | `#cbd5e1`             | Input borders, dividers       |
| `--color-border-hover`      | `#475569`             | `#94a3b8`             | Hover state for borders       |
| `--color-text`              | `#f8fafc`             | `#0f172a`             | Primary text                  |
| `--color-text-muted`        | `#94a3b8`             | `#475569`             | Secondary text, labels        |
| `--color-success`           | `#10b981`             | `#059669`             | Success indicators            |
| `--color-warning`           | `#f59e0b`             | `#b45309`             | Warning indicators            |
| `--color-danger`            | `#ef4444`             | `#dc2626`             | Errors, delete actions        |
| `--color-badge-draft`       | `rgba(255,255,255,.1)` | `rgba(15,23,42,.08)` | Draft badge background        |
| `--color-badge-draft-text`  | `#cbd5e1`             | `#334155`             | Draft badge text              |
| `--color-badge-approved`    | `rgba(16,185,129,.2)` | `rgba(5,150,105,.15)` | Approved badge background     |
| `--color-badge-approved-text`| `#34d399`            | `#047857`             | Approved badge text           |

### 11.2 Spacing (4 px scale)

| Token        | Value    |
|--------------|----------|
| `--space-1`  | 0.25 rem |
| `--space-2`  | 0.5 rem  |
| `--space-3`  | 0.75 rem |
| `--space-4`  | 1 rem    |
| `--space-6`  | 1.5 rem  |
| `--space-8`  | 2 rem    |

`--space-5` is not defined — skip from `--space-4` to `--space-6`.

### 11.3 Typography

| Token               | Value                                          |
|---------------------|------------------------------------------------|
| `--font-sans`       | `'Outfit', 'Inter', system-ui, sans-serif`     |
| `--font-size-sm`    | 0.875 rem (14 px)                              |
| `--font-size-base`  | 1 rem (16 px)                                  |
| `--font-size-lg`    | 1.125 rem (18 px)                              |
| `--font-size-xl`    | 1.25 rem (20 px)                               |
| `--font-size-2xl`   | 1.5 rem (24 px)                                |

**`--font-size-xs` does NOT exist.** Use the literal `'0.75rem'` for 12 px text
(e.g. UID badges, captions). Do not reference `var(--font-size-xs)`.

### 11.4 Borders and shadows

| Token           | Value                                                       |
|-----------------|-------------------------------------------------------------|
| `--radius-sm`   | 6 px                                                        |
| `--radius-md`   | 12 px                                                        |
| `--radius-lg`   | 16 px                                                        |
| `--radius-full` | 9999 px (pills, badges)                                     |
| `--shadow-sm`   | Subtle box shadow for list items                            |
| `--shadow-card` | Heavier shadow for form panels and hovered/active cards     |

### 11.5 Transitions

| Token                 | Value                               |
|-----------------------|-------------------------------------|
| `--transition-fast`   | 150 ms cubic-bezier(0.4, 0, 0.2, 1) |
| `--transition-normal` | 250 ms cubic-bezier(0.4, 0, 0.2, 1) |
| `--transition-slow`   | 400 ms cubic-bezier(0.4, 0, 0.2, 1) |

All interactive elements SHOULD use `transition: var(--transition-fast)`.

---

*End of document. All new masks and form components MUST follow this style guide.
Deviations require an update to this file and review by the ui-ux-designer agent.*
