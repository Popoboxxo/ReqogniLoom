# Architecture Editors Refactoring — Dynamic Masks & SplitView Integration

**REQ-L3-RF004-004** | **REQ-L1-084** | **Date:** 2026-07-04

## Summary

Refactored `ArchitectureEditors.tsx` to:
1. **Use SplitView Component** — Generic two-column layout with resizable divider, localStorage persistence
2. **Extract ArchitectureList** — Hierarchical element display with tree expand/collapse, type badges, ASIL indicators
3. **Extract ArchitectureForm** — Editable form with ASIL/Make-or-Buy dropdowns, UID+Version read-only header
4. **Add Dynamic Field Visibility** — ASIL & Make-or-Buy shown/hidden via EntityTypeContext
5. **ASIL Utilities** — Color-coded badges, labels, and helper functions for ASIL levels (QM, A, B, C, D)
6. **Type Extensions** — ArchitectureElement now includes asil_level, make_or_buy, uid, version, level

## File Structure

### New Files

| File | Purpose |
|------|---------|
| `frontend/src/utils/asilUtils.ts` | ASIL helper functions (colors, labels, dropdown options) |
| `frontend/src/components/ArchitectureEditors/ArchitectureForm.tsx` | Form component with ASIL/Make-or-Buy fields |
| `frontend/src/components/ArchitectureEditors/ArchitectureList.tsx` | Hierarchical list with tree rendering |
| `docs/ARCHITECTURE_EDITORS_REFACTORING.md` | This file |

### Modified Files

| File | Changes |
|------|---------|
| `frontend/src/types/index.ts` | Added ASILLevel, MakeOrBuyDecision types; extended ArchitectureElement |
| `frontend/src/components/ArchitectureEditors/ArchitectureEditors.tsx` | Refactored to use SplitView, new components |

### Unchanged

- `frontend/src/components/SplitView/SplitView.tsx` — Already exists (generic)
- `frontend/src/context/EntityTypeContext.tsx` — Already exists (supports visibility config)
- Backend API — No changes (already supports asil_level, make_or_buy, uid)

## Integration Checklist

### Backend API Contract (Already Implemented)

- `GET /api/v1/architecture-elements/{id}/` → Returns `asil_level`, `make_or_buy`, `uid`, `version`, `level`
- `PATCH /api/v1/architecture-elements/{id}/` → Accepts `asil_level`, `make_or_buy`, plus standard fields
- `GET /api/v1/attribute-visibility-config/?entity_type=architecture_element` → Returns field visibility config

### Frontend Integration Steps

1. **Visibility Config Fetching** (Optional, Phase 2)
   - If admin-dialog is activated, load `attribute-visibility-config` and pass to EntityTypeProvider
   - Currently, ASIL & Make-or-Buy are hardcoded as visible

2. **Admin Dialog Wiring** (Optional, Phase 2)
   - Admin can toggle ASIL/Make-or-Buy visibility per workspace/preset
   - On change, ArchitectureForm re-renders (fields appear/disappear)

3. **Custom Styling** (Optional)
   - ASIL badge colors are inline-defined in asilUtils.ts
   - Adjust colors via getAsilBadgeStyle() if design system changes

## Component Architecture

```
ArchitectureEditors (Main Container)
├── SplitView (Generic Layout)
│   ├── leftPanel: ArchitectureList
│   │   ├── Tree hierarchy with expand/collapse
│   │   ├── Type badges (component, interface, subsystem, layer, module)
│   │   ├── ASIL badges (QM, A, B, C, D)
│   │   └── Hierarchy level indicator
│   │
│   └── rightPanel: DetailPanel
│       ├── EntityTypeProvider (Visibility Config)
│       ├── ArchitectureForm
│       │   ├── UID + Version (read-only)
│       │   ├── Standard Fields (title, type, parent, description)
│       │   ├── ASIL Dropdown (if visible)
│       │   ├── Make-or-Buy Dropdown (if visible)
│       │   └── Actions (Save, Delete, Diff)
│       │
│       └── ArchTraceLinkPanel + Linked Requirements Sidebar
```

## ASIL Level Reference

| Level | Label | Color | Meaning |
|-------|-------|-------|---------|
| QM | No Functional Safety | Gray | Quality Management only |
| A | Low | Yellow | Low functional safety integrity |
| B | Medium | Orange | Medium functional safety integrity |
| C | High | Red | High functional safety integrity |
| D | Highest | Dark Red | Highest functional safety integrity |

## Known Limitations

1. **Tree Rendering** — Currently uses flat list with indentation. Full drag-drop reordering kept in `DecompositionTree` (not removed from codebase, but not used by new ArchitectureList).
2. **Visibility Config Persistence** — AdminDialog to configure visibility not yet implemented; hardcoded to show ASIL & Make-or-Buy.
3. **Mobile Responsive** — SplitView handles responsive collapse on <768px; ArchitectureList not tested on mobile.

## Testing Notes

- No tests included (per user override)
- Manually verify:
  - ASIL dropdown appears/populated with options
  - Make-or-Buy dropdown appears/populated with options
  - UID/Version read-only in header
  - SplitView divider resizable, width persists in localStorage
  - Tree expand/collapse works
  - Element selection navigates and loads form
  - Save/Delete/Diff buttons work as before

## Future Enhancements

1. **AdminDialog Integration** — Toggle ASIL/Make-or-Buy visibility per workspace
2. **Drag-Drop Reordering** — Enhance ArchitectureList to support tree drag-drop (currently in DecompositionTree)
3. **Batch Operations** — Multi-select elements and bulk update ASIL/Make-or-Buy
4. **Search/Filter** — Filter list by ASIL level, element type, hierarchy level
5. **Custom Field Rules** — Define which element types require ASIL (e.g., "component" always, "interface" optional)
