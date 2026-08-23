# Bugfix Session Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **This plan is self-contained** — every fact needed to execute it (root cause, exact file:line, exact code) was independently verified against the real ReqogniLoom source; no prior conversation context is required to implement it.

**Goal:** Fix a large batch of currently open, independently-scoped bugs (17 of 30 open `bug`-labeled GitHub issues) in one session — the remaining 13 are deliberately out of scope (see "Deliberately out of scope" at the end) because they either already have their own dedicated plan, are test-infrastructure/security-reverification work rather than application bugs, or are part of a larger Design-System-Konsolidierung effort that needs its own architectural brainstorming before any code is touched.

**Architecture:** No new subsystems — this is a batch of independent, small, verified fixes across frontend components, i18n locale files, and two backend endpoints. Tasks are grouped by code area (mirroring this project's established grouping convention from prior bugfix batches) so the same files aren't touched twice across separate PRs.

**Tech Stack:** Django REST Framework (backend), React 18 + TypeScript (frontend), react-i18next.

**Spec:** None — this is a bugfix batch against existing GitHub issues, not a new-feature spec. Each task cites its source issue number.

## Global Constraints

- Every new `t()` call MUST have both a `de.json` and `en.json` entry — `frontend/src/test/i18n-parity.test.ts`'s strict parity test (line 47-59) fails immediately otherwise, no ratchet tolerance there.
- `frontend/src/test/i18n-parity.test.ts`'s second test (`#619` coverage ratchet, line 137, `MISSING_KEY_BASELINE = 145`) must be re-measured and **lowered** (never raised) in the final task of this plan if any of the fixed keys reduce the count of code-referenced-but-locale-missing keys — per that test's own documented convention (see its comment at line 71-74).
- `data-testid` on every new/modified interactive element (project convention, E2E-required).
- Every GitHub issue this plan closes or comments on uses `gh issue comment <n> --body "..."` / `gh issue close <n> --reason ... -c "..."` — run these from the plan's own worktree checkout, they are read/write GitHub operations, not local git mutations, and don't need the repo's git-agent-delegation convention (that convention is about `git` commands, not `gh issue`).
- Commit messages MUST reference the issue they fix (`Fixes #NNN`) per this repo's issue-lifecycle convention (`.claude/rules/issue-lifecycle.md`).

---

## Task 1 (#662): Workspace name Save button stays enabled when the name is emptied

**Files:**
- Modify: `frontend/src/components/WorkspaceSettings/WorkspaceSettings.tsx:345-355`
- Test: `frontend/src/components/WorkspaceSettings/WorkspaceSettings.test.tsx`

**Root cause (verified):** the Save button's `disabled`/`opacity` logic only checks `isSaving || name === activeWorkspace.name` (line 348) — it never checks for an empty/whitespace-only name, even though `handleSaveName()` itself already silently no-ops on `!name.trim()` (line 157). Result: the button looks clickable and does nothing when clicked with an empty name, no error shown.

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/components/WorkspaceSettings/WorkspaceSettings.test.tsx
it("disables the save button when the name is emptied", () => {
  render(<WorkspaceSettings />);
  const input = screen.getByTestId("workspace-name-input");
  fireEvent.change(input, { target: { value: "" } });
  expect(screen.getByTestId("workspace-name-save")).toBeDisabled();
});

it("disables the save button when the name is only whitespace", () => {
  render(<WorkspaceSettings />);
  const input = screen.getByTestId("workspace-name-input");
  fireEvent.change(input, { target: { value: "   " } });
  expect(screen.getByTestId("workspace-name-save")).toBeDisabled();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/components/WorkspaceSettings/WorkspaceSettings.test.tsx`
Expected: FAIL — button is not disabled for an empty/whitespace name.

- [ ] **Step 3: Fix**

In `WorkspaceSettings.tsx`, change both the `disabled` prop and the matching `opacity` expression on the save button (line 348 and its neighboring `style` block) from:
```tsx
disabled={isSaving || name === activeWorkspace.name}
```
to:
```tsx
disabled={isSaving || !name.trim() || name === activeWorkspace.name}
```
and mirror the same `!name.trim() ||` addition in the `opacity: (isSaving || name === activeWorkspace.name) ? 0.5 : 1` expression right below it.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/components/WorkspaceSettings/WorkspaceSettings.test.tsx`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/WorkspaceSettings/WorkspaceSettings.tsx frontend/src/components/WorkspaceSettings/WorkspaceSettings.test.tsx
git commit -m "fix: disable workspace name save button for empty/whitespace name

Fixes #662"
```

---

## Task 2 (#667): ARIA treeitem violation — interactive buttons nested inside role="treeitem"

**Files:**
- Modify: `frontend/src/components/shared/WorkspaceTree/workspace-tree.tsx:908-1095` (toggle button ~976-1001, add-child button ~1076-1095)
- Test: `frontend/src/components/shared/WorkspaceTree/workspace-tree.test.tsx`

**Root cause (verified):** the `<li role="treeitem">` (line 908) directly nests two `<button>` elements (expand/collapse toggle, add-child) as immediate children. Per the ARIA APG Treeview pattern, a `treeitem` must not have focusable/interactive descendants — this breaks the roving-tabindex pattern (the `<li>` itself already manages `tabIndex={isFocused ? 0 : -1}`) and screen readers in tree-navigation mode can't reach these buttons independently.

**Fix approach (Option A from research — smallest diff, APG-compliant):** take both buttons out of the tab order and the accessibility tree (`tabIndex={-1}`, `aria-hidden="true"`) so they remain mouse-only affordances, and add keyboard equivalents on the `<li>` itself (ArrowRight to expand, matching the existing `onToggle` handler — add-child gets no keyboard equivalent in this minimal fix, it stays mouse/pointer-only, which is acceptable since it's a secondary action, not core tree navigation).

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/components/shared/WorkspaceTree/workspace-tree.test.tsx
it("does not expose the toggle/add-child buttons as tab-focusable or in the a11y tree", () => {
  render(<WorkspaceTree nodes={nodesWithChildren} onToggle={vi.fn()} onAddChild={vi.fn()} onSelect={vi.fn()} />);
  const toggleButton = screen.getByTestId(/tree-toggle-/);
  expect(toggleButton).toHaveAttribute("tabIndex", "-1");
  expect(toggleButton).toHaveAttribute("aria-hidden", "true");
});

it("expands a node via ArrowRight on the focused treeitem", () => {
  const onToggle = vi.fn();
  render(<WorkspaceTree nodes={nodesWithChildren} onToggle={onToggle} onSelect={vi.fn()} />);
  const treeitem = screen.getAllByRole("treeitem")[0];
  fireEvent.keyDown(treeitem, { key: "ArrowRight" });
  expect(onToggle).toHaveBeenCalled();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/components/shared/WorkspaceTree/workspace-tree.test.tsx`
Expected: FAIL — buttons currently have no `tabIndex`/`aria-hidden`, no ArrowRight handler exists on the `<li>`.

- [ ] **Step 3: Fix**

On both button elements (toggle ~line 976, add-child ~line 1076), add:
```tsx
tabIndex={-1}
aria-hidden="true"
```
On the `<li role="treeitem">` element (line 908), add an `onKeyDown` handler (if one doesn't already exist — check for an existing handler on this element first and extend it rather than adding a second one):
```tsx
onKeyDown={(e) => {
  if (e.key === "ArrowRight" && hasChildren && !isExpanded) {
    e.preventDefault();
    onToggle(node.id);
  }
  if (e.key === "ArrowLeft" && hasChildren && isExpanded) {
    e.preventDefault();
    onToggle(node.id);
  }
  // preserve any existing onKeyDown behavior here
}}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/components/shared/WorkspaceTree/workspace-tree.test.tsx`
Expected: PASS

- [ ] **Step 5: Run the full WorkspaceTree test suite and any consumer snapshot tests to confirm no regression**

Run: `cd frontend && npx vitest run -t "WorkspaceTree"` (or the equivalent broader pattern covering all files that render this shared component — check `ArchitectureEditors.test.tsx` and other consumers for tree-interaction assertions that might reference the old tabIndex).
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/shared/WorkspaceTree/workspace-tree.tsx frontend/src/components/shared/WorkspaceTree/workspace-tree.test.tsx
git commit -m "fix: remove interactive descendants from ARIA treeitem, add keyboard expand/collapse

Fixes #667"
```

---

## Task 3 (#664): Chat-support floating button too visually dominant

**Files:**
- Modify: `frontend/src/components/InterviewWidget/InterviewWidget.module.css:1-14`
- Test: `frontend/src/components/InterviewWidget/InterviewWidget.test.tsx`

**Root cause (verified):** `.toggle` uses `background: var(--color-primary)` (the system's highest-contrast brand/CTA color), `box-shadow: var(--shadow-card)` (the heaviest shadow token, normally reserved for panels/cards), and `z-index: 900` (the highest hardcoded z-index anywhere in the frontend) on a permanently-visible 48×48px floating button — visually competing with actual primary CTAs.

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/components/InterviewWidget/InterviewWidget.test.tsx
it("uses a secondary (non-primary-brand) surface style for the floating toggle", () => {
  render(<InterviewWidget />);
  const toggle = screen.getByTestId("interview-widget-toggle");
  const styles = getComputedStyle(toggle);
  // Computed style resolution of CSS custom properties isn't reliable in jsdom,
  // so this test asserts against the module.css source directly instead.
});
```

Note for the implementer: jsdom does not resolve CSS custom properties from an imported `.module.css` file reliably for `getComputedStyle` assertions — write this as a source-file assertion instead, following the pattern already used elsewhere in this repo for CSS-token-compliance checks (e.g. `frontend/src/test/ui-ratchet.test.ts`'s hex-literal scan):

```tsx
// frontend/src/components/InterviewWidget/toggle-style.test.ts
import { readFileSync } from "fs";
import { describe, it, expect } from "vitest";

describe("InterviewWidget toggle button style", () => {
  const css = readFileSync("src/components/InterviewWidget/InterviewWidget.module.css", "utf-8");
  const toggleBlock = css.match(/\.toggle\s*\{[^}]*\}/)?.[0] ?? "";

  it("does not use the primary brand color for the floating toggle background", () => {
    expect(toggleBlock).not.toMatch(/background:\s*var\(--color-primary\)/);
  });

  it("does not use the heaviest card shadow token", () => {
    expect(toggleBlock).not.toMatch(/box-shadow:\s*var\(--shadow-card\)/);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/components/InterviewWidget/toggle-style.test.ts`
Expected: FAIL — both assertions currently match.

- [ ] **Step 3: Fix**

In `InterviewWidget.module.css`, change `.toggle` (lines 1-14) from:
```css
.toggle {
  position: fixed;
  bottom: var(--space-4);
  right: var(--space-4);
  z-index: 900;
  width: 48px;
  height: 48px;
  border-radius: var(--radius-full);
  background: var(--color-primary);
  color: white;
  border: none;
  cursor: pointer;
  box-shadow: var(--shadow-card);
}
```
to:
```css
.toggle {
  position: fixed;
  bottom: var(--space-4);
  right: var(--space-4);
  z-index: 100;
  width: 40px;
  height: 40px;
  border-radius: var(--radius-full);
  background: var(--color-surface-raised);
  color: var(--color-text);
  border: 1px solid var(--color-border);
  cursor: pointer;
  box-shadow: var(--shadow-sm);
}
```
Also check `.panel`'s `z-index: 900` (also in this file, per research finding — same stacking context) — lower it to `z-index: 100` as well so the panel still layers above the toggle button consistently, unless the panel legitimately needs to sit above other floating UI (verify visually that the panel still appears above the sidebar/other page chrome at `z-index: 100` before committing to that exact value — this project has no other `z-index` above 100 anywhere else per the research grep, so 100 is safely still the highest layer).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/components/InterviewWidget/toggle-style.test.ts`
Expected: PASS

- [ ] **Step 5: Manual visual check**

Per project convention for UI changes: start the dev server, open the app, confirm the floating button now reads as a secondary affordance (not competing with primary CTAs) and the panel still opens above all other page content.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/InterviewWidget/InterviewWidget.module.css frontend/src/components/InterviewWidget/toggle-style.test.ts
git commit -m "fix: tone down chat-support floating button to a secondary style

Fixes #664"
```

---

## Task 4 (#663): Workspace preset feature list uses inconsistent notation

**Files:**
- Modify: `frontend/src/components/WorkspaceSettings/WorkspaceSettings.tsx:386-393`
- Test: `frontend/src/components/WorkspaceSettings/WorkspaceSettings.test.tsx`

**Root cause (verified):** the preset feature summary mixes three notation styles in one line — `Baselines: ✓/✗` (label+symbol), `change_reason: optional|required` (raw snake_case property name + raw value, no i18n), and `{features.workflow}` (bare freetext, no label/symbol at all).

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/components/WorkspaceSettings/WorkspaceSettings.test.tsx
it("renders preset features with a consistent symbol-prefixed format", () => {
  render(<WorkspaceSettings />);
  const summary = screen.getByTestId("preset-features-extended");
  expect(summary).not.toHaveTextContent("change_reason:");
  expect(summary.textContent).toMatch(/✓ Baselines/);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/components/WorkspaceSettings/WorkspaceSettings.test.tsx`
Expected: FAIL — current markup has no `data-testid="preset-features-*"` and shows the raw `change_reason:` label.

- [ ] **Step 3: Fix**

Replace the block at lines 386-393:
```tsx
<div style={{ fontSize: "var(--font-size-sm)", color: "var(--color-text-muted)", marginTop: "2px" }}>
  Baselines: {features.baselines ? "✓" : "✗"} &nbsp;|&nbsp;
  change_reason: {features.changeReason} &nbsp;|&nbsp;
  {features.workflow}
</div>
```
with:
```tsx
<div
  data-testid={`preset-features-${preset}`}
  style={{ fontSize: "var(--font-size-sm)", color: "var(--color-text-muted)", marginTop: "2px" }}
>
  <div>{features.baselines ? "✓" : "✗"} {t("workspaceSettings.presets.baselines")}</div>
  <div>
    {features.changeReason === "required" ? "✓" : "✗"}{" "}
    {t("workspaceSettings.presets.changeReason")}{" "}
    ({features.changeReason === "required" ? t("workspaceSettings.presets.required") : t("workspaceSettings.presets.optional")})
  </div>
  <div>✓ {t("workspaceSettings.presets.workflow")}: {features.workflow}</div>
</div>
```
Add the four new i18n keys to both `de.json`/`en.json`:
- `workspaceSettings.presets.baselines` — DE: `"Baselines"` / EN: `"Baselines"`
- `workspaceSettings.presets.changeReason` — DE: `"Änderungsgrund"` / EN: `"Change Reason"`
- `workspaceSettings.presets.required` — DE: `"erforderlich"` / EN: `"required"`
- `workspaceSettings.presets.optional` — DE: `"optional"` / EN: `"optional"`
- `workspaceSettings.presets.workflow` — DE: `"Workflow"` / EN: `"Workflow"`

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/components/WorkspaceSettings/WorkspaceSettings.test.tsx`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/WorkspaceSettings/WorkspaceSettings.tsx frontend/src/i18n/locales/en.json frontend/src/i18n/locales/de.json
git commit -m "fix: use consistent symbol-prefixed notation for workspace preset features

Fixes #663"
```

---

## Task 5 (#724): malformed `document_id` on `baseline.create scope=document` leaks a 500

**Files:**
- Modify: `backend/application/baseline_facade.py:118-120`
- Test: `backend/application/tests/test_baseline_facade_malformed_document_id.py`

**Root cause (verified):** `BaselineFacade.create_baseline` converts `document_id` via bare `UUID(str(document_id))` (line 118-120) with no `try/except` — a non-UUID string raises an ungefangen `ValueError`, which isn't in `rest_api/views.py`'s `_EXC_TO_HTTP`/`_EXC_TO_CODE` maps (only `ValidationError`/`NotFoundError`/`PermissionDeniedError`/etc. are mapped), so it falls through to the generic `except Exception` handler and returns a `500 INTERNAL_SERVER_ERROR` instead of a client-input `400`.

- [ ] **Step 1: Write the failing test**

```python
# backend/application/tests/test_baseline_facade_malformed_document_id.py
import pytest

from application.baseline_facade import BaselineFacade
from application.base import ValidationError
from persistence.tests.factories import active_tenant, make_workspace, editor_ctx


@pytest.mark.django_db
class TestMalformedDocumentId:
    def test_malformed_document_id_raises_validation_error_not_value_error(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            ctx = editor_ctx(tenant, ws)
            with pytest.raises(ValidationError, match="document_id"):
                BaselineFacade().create_baseline(
                    workspace_id=ws.id, scope="document", document_id="not-a-uuid", ctx=ctx,
                )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/application/tests/test_baseline_facade_malformed_document_id.py -v`
Expected: FAIL — raises `ValueError`, not `ValidationError`.

- [ ] **Step 3: Fix**

In `baseline_facade.py`, change lines 118-120 from:
```python
doc_id: Optional[UUID] = (
    UUID(str(document_id)) if document_id is not None else None
)
```
to:
```python
try:
    doc_id: Optional[UUID] = (
        UUID(str(document_id)) if document_id is not None else None
    )
except (ValueError, AttributeError, TypeError) as exc:
    raise ValidationError(
        "Baseline cannot be created: document_id is not a valid UUID."
    ) from exc
```
(`ValidationError` is already imported in this file per the research — verify the import at the top of `baseline_facade.py` before assuming it, but it is used elsewhere in the same method per the existing `scope == "document" and doc_id is None` check at line 131.)

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/application/tests/test_baseline_facade_malformed_document_id.py -v`
Expected: PASS

- [ ] **Step 5: Add a REST-level regression test confirming the HTTP status**

```python
# Add to backend/rest_api/tests/test_baseline_views.py (or create if no such file exists for baselines)
def test_malformed_document_id_returns_400_not_500(self):
    with active_tenant() as tenant:
        ws = make_workspace(tenant)
        user, token = editor_user_and_token(tenant, ws)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        response = client.post(
            "/api/v1/baselines/",
            {"workspace_id": str(ws.id), "scope": "document", "document_id": "not-a-uuid"},
            format="json",
        )
        assert response.status_code == 400
```

Run: `pytest backend/rest_api/tests/test_baseline_views.py -k malformed_document_id -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/application/baseline_facade.py backend/application/tests/test_baseline_facade_malformed_document_id.py backend/rest_api/tests/test_baseline_views.py
git commit -m "fix: reject malformed document_id with 400 instead of leaking a 500

Fixes #724"
```

---

## Task 6 (#659): Admin "Permission Defaults" — hardcoded/missing English labels

**Files:**
- Modify: `frontend/src/components/SystemSettings/SystemSettings.tsx:70-72`
- Modify: `frontend/src/components/SystemSettings/PermissionDefaultsTab.tsx:104-108`
- Modify: `frontend/src/components/PermissionMatrix/PermissionMatrixEditor.tsx:36-43,128,195,217,227`
- Modify: `frontend/src/components/SystemSettings/EnforcementModePanel.tsx:101-103,128,153,157,161,203`
- Test: `frontend/src/components/SystemSettings/PermissionDefaultsTab.test.tsx`, `frontend/src/components/PermissionMatrix/PermissionMatrixEditor.test.tsx`

**Root cause (verified, 4 separate spots):**
1. `SystemSettings.tsx:70-72` — three tab labels use `t(key, "English default")` where the keys (`systemSettings.tabs.administration`/`.workflowDefaults`/`.permissionDefaults`) don't exist in either locale file.
2. `PermissionDefaultsTab.tsx:104-108` — heading and hint text are bare hardcoded English strings, no `t()` call at all.
3. `PermissionMatrixEditor.tsx` — `CAPABILITY_LABELS` (lines 36-43) is a hardcoded English `Record`, plus bare strings `"Role"` (128), `"Saved."` (195), `"Save"`/`"…"` (217), `"Cancel"` (227). This component is shared between `PermissionDefaultsTab.tsx` and `WorkspaceSettings/WorkflowPermissionsSection.tsx:428` — fixing it here fixes both surfaces.
4. `EnforcementModePanel.tsx` — `"Enforcement Mode"` heading (128), `"Roll Back to Shadow"` button (203), plus (same file, same bug type, include in this task) `window.confirm(...)` text (101-103), `"Authoritative"`/`"Shadow"` pills (153), pending-mismatch count strings (157, 161).

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/components/SystemSettings/PermissionDefaultsTab.test.tsx
it("renders the localized heading, not the raw English fallback text", () => {
  i18n.changeLanguage("de");
  render(<PermissionDefaultsTab />);
  expect(screen.getByText("Globale Berechtigungsmatrix")).toBeInTheDocument();
  expect(screen.queryByText("Global Permission Matrix")).not.toBeInTheDocument();
});
```

```tsx
// frontend/src/components/PermissionMatrix/PermissionMatrixEditor.test.tsx
it("renders capability column headers in German when locale is de", () => {
  i18n.changeLanguage("de");
  render(<PermissionMatrixEditor matrix={sampleMatrix} onChange={vi.fn()} />);
  expect(screen.getByText("Lesen")).toBeInTheDocument();
  expect(screen.getByText("Schreiben")).toBeInTheDocument();
  expect(screen.queryByText("Read")).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx vitest run src/components/SystemSettings/PermissionDefaultsTab.test.tsx src/components/PermissionMatrix/PermissionMatrixEditor.test.tsx`
Expected: FAIL

- [ ] **Step 3: Add the i18n keys**

Add to both `de.json`/`en.json`:
```json
{
  "systemSettings": {
    "tabs": {
      "administration": "Administration" ,
      "workflowDefaults": "Workflow-Standards" ,
      "permissionDefaults": "Berechtigungs-Standards"
    },
    "permissionDefaults": {
      "globalMatrixTitle": "Globale Berechtigungsmatrix",
      "globalMatrixHint": "Die tenant-weite Standard-Matrix aus Rolle→Capability, die jeder neue Workspace erbt. Speichern überträgt die Änderung auf alle Workspaces, die aktuell den Standard verwenden."
    },
    "enforcementMode": {
      "title": "Durchsetzungsmodus",
      "rollbackButton": "Zurück zu Shadow wechseln",
      "confirmRollback": "Zurück zu Shadow-Durchsetzung wechseln? ...",
      "authoritative": "Autoritativ",
      "shadow": "Shadow",
      "zeroMismatches": "0 ausstehende Abweichungen — bereit zum Umschalten",
      "pendingMismatches": "{{count}} ausstehend — Prüfung vor dem Umschalten empfohlen"
    }
  },
  "permissionMatrix": {
    "roleColumn": "Rolle",
    "capability": {
      "read": "Lesen",
      "write": "Schreiben",
      "workflow_transition": "Übergang",
      "workflow_approval": "Freigabe",
      "workspace_config": "Konfig",
      "assign_role": "Rolle zuweisen"
    }
  }
}
```
(English values mirror the existing hardcoded EN strings exactly — `"Administration"`, `"Workflow Defaults"`, `"Permission Defaults"`, `"Global Permission Matrix"`, the exact hint text already in the code, `"Enforcement Mode"`, `"Roll Back to Shadow"`, etc. — copy verbatim from the current source for the `en.json` side so no visible English-locale behavior changes, only German gets fixed.)

- [ ] **Step 4: Wire the keys into the four files**

`SystemSettings.tsx:70-72` — no code change needed, the keys now resolve (the `t(key, "fallback")` calls already reference the right key names, they were just missing from the locale files).

`PermissionDefaultsTab.tsx:104-108` — change:
```tsx
<h3 style={headingStyle}>Global Permission Matrix</h3>
<p style={hintStyle}>
  The tenant-wide default role→capability matrix that every new workspace
  inherits. Saving propagates into all workspaces currently on the default.
</p>
```
to:
```tsx
<h3 style={headingStyle}>{t("systemSettings.permissionDefaults.globalMatrixTitle")}</h3>
<p style={hintStyle}>{t("systemSettings.permissionDefaults.globalMatrixHint")}</p>
```

`PermissionMatrixEditor.tsx` — replace the hardcoded `CAPABILITY_LABELS` record (lines 36-43) with a function that calls `t()`, e.g.:
```tsx
const CAPABILITY_LABEL_KEYS: Record<CapabilityKey, string> = {
  read: "permissionMatrix.capability.read",
  write: "permissionMatrix.capability.write",
  workflow_transition: "permissionMatrix.capability.workflow_transition",
  workflow_approval: "permissionMatrix.capability.workflow_approval",
  workspace_config: "permissionMatrix.capability.workspace_config",
  assign_role: "permissionMatrix.capability.assign_role",
};
// at each render call site that used CAPABILITY_LABELS[key], use t(CAPABILITY_LABEL_KEYS[key]) instead
```
Replace bare `"Role"` (128) with `{t("permissionMatrix.roleColumn")}`, `"Saved."` (195) with `{t("actions.saved")}` (existing key, reuse per research finding), `"Save"`/`"…"` (217) with `{saving ? "…" : t("actions.save")}` (existing key), `"Cancel"` (227) with `{t("actions.cancel")}` (existing key).

`EnforcementModePanel.tsx` — replace each hardcoded string cited above with the matching new `systemSettings.enforcementMode.*` key.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/components/SystemSettings/PermissionDefaultsTab.test.tsx src/components/PermissionMatrix/PermissionMatrixEditor.test.tsx`
Expected: PASS

- [ ] **Step 6: Run the i18n parity test**

Run: `cd frontend && npx vitest run src/test/i18n-parity.test.ts`
Expected: PASS (strict parity test passes since every new key was added to both files; note the coverage-ratchet count for the final Task 15 baseline update)

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/SystemSettings/SystemSettings.tsx frontend/src/components/SystemSettings/PermissionDefaultsTab.tsx frontend/src/components/PermissionMatrix/PermissionMatrixEditor.tsx frontend/src/components/SystemSettings/EnforcementModePanel.tsx frontend/src/i18n/locales/en.json frontend/src/i18n/locales/de.json frontend/src/components/SystemSettings/PermissionDefaultsTab.test.tsx frontend/src/components/PermissionMatrix/PermissionMatrixEditor.test.tsx
git commit -m "fix: localize Permission Defaults admin panel (tabs, matrix, enforcement mode)

Fixes #659"
```

---

## Task 7 (#658): ADR title placeholder hardcoded in English

**Files:**
- Modify: `frontend/src/components/AdrEditors/AdrEditors.tsx:242`
- Test: `frontend/src/components/AdrEditors/AdrEditors.test.tsx`

**Root cause (verified):** line 242 uses `t('editor.newNeedTitle', 'e.g. As a user, I need...')` — a key copy-pasted from `NeedList.tsx`, which doesn't exist in either locale file and is semantically wrong for an ADR (it's a Need-shaped placeholder). The identical copy-paste mistake also exists in `RiskEditors.tsx:241` and `IssueEditors.tsx:242` with their own different English fallback texts — those two are explicitly **not** part of this task (out of scope for issue #658), noted as a follow-up.

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/components/AdrEditors/AdrEditors.test.tsx
it("shows an ADR-appropriate placeholder, translated to German", () => {
  i18n.changeLanguage("de");
  render(<AdrEditors />);
  const input = screen.getByPlaceholderText("z.B. Als Benutzer möchte ich...");
  expect(input).toBeInTheDocument();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/components/AdrEditors/AdrEditors.test.tsx`
Expected: FAIL — placeholder is currently the English fallback regardless of locale.

- [ ] **Step 3: Fix**

Add to both `de.json`/`en.json`:
- `adr.newTitlePlaceholder` — DE: `"z.B. Als Benutzer möchte ich..."` / EN: `"e.g. As a user, I need..."`

Change `AdrEditors.tsx:242` from:
```tsx
placeholder={t('editor.newNeedTitle', 'e.g. As a user, I need...')}
```
to:
```tsx
placeholder={t('adr.newTitlePlaceholder')}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/components/AdrEditors/AdrEditors.test.tsx`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/AdrEditors/AdrEditors.tsx frontend/src/i18n/locales/en.json frontend/src/i18n/locales/de.json frontend/src/components/AdrEditors/AdrEditors.test.tsx
git commit -m "fix: give ADR title placeholder its own i18n key instead of the wrong Need copy

Fixes #658"
```

---

## Task 8 (#657): Import page — ReqIF section CamelCase entity-type labels

**Files:**
- Modify: `frontend/src/components/CsvImport/CsvImport.tsx:248-262,515-529`
- Test: `frontend/src/components/CsvImport/CsvImport.test.tsx`

**Note:** the literal strings originally quoted in #657 ("Select ReqIF File", "Click to select a .reqif or .xml file", "Dry run...", "Import ReqIF") are **already fixed** (commit `38076e1`, keys `import.reqifSelectFile`/`.reqifDropHint`/`.reqifDryRun`/`.reqifUpload` exist in both locale files) — do not re-implement those. The remaining, still-open part of #657 is the CamelCase entity-type radio labels (`"Requirement"`, `"ArchitectureElement"`, `"TestCase"`, `"StakeholderNeed"` rendered as-is from the raw API enum value, no `t()`, no spacing).

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/components/CsvImport/CsvImport.test.tsx
it("renders entity type labels as readable localized text, not raw CamelCase enum values", () => {
  i18n.changeLanguage("de");
  render(<CsvImport />);
  expect(screen.getByText("Anforderung")).toBeInTheDocument();
  expect(screen.getByText("Architekturelement")).toBeInTheDocument();
  expect(screen.queryByText("ArchitectureElement")).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/components/CsvImport/CsvImport.test.tsx`
Expected: FAIL — raw enum strings are currently rendered.

- [ ] **Step 3: Fix**

Add to both `de.json`/`en.json` under a shared, reusable namespace (also usable by `AttributeVisibilityAdmin.tsx:358-376`, which has the identical unmet need per research — add all 7 keys now even though only 4 are used by this task, so the namespace is complete for that other consumer to adopt later without another locale-file edit):
```json
{
  "admin": {
    "entityType": {
      "requirement": "Anforderung",
      "architectureElement": "Architekturelement",
      "testCase": "Testfall",
      "stakeholderNeed": "Stakeholder-Bedarf",
      "adr": "ADR",
      "risk": "Risiko",
      "issue": "Issue"
    }
  }
}
```
(English values: `"Requirement"`, `"Architecture Element"`, `"Test Case"`, `"Stakeholder Need"`, `"ADR"`, `"Risk"`, `"Issue"`.)

In `CsvImport.tsx`, add a small mapping near `ENTITY_TYPES`/`EXPORT_ENTITY_TYPES` (lines 34-38, 42-46):
```tsx
const ENTITY_TYPE_LABEL_KEYS: Record<string, string> = {
  Requirement: "admin.entityType.requirement",
  ArchitectureElement: "admin.entityType.architectureElement",
  TestCase: "admin.entityType.testCase",
  StakeholderNeed: "admin.entityType.stakeholderNeed",
};
```
Replace the bare `{type}` render at line 261 and line 528 with `{t(ENTITY_TYPE_LABEL_KEYS[type] ?? type)}` (falls back to the raw value for any type not in the map, so this never crashes on an unexpected enum value).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/components/CsvImport/CsvImport.test.tsx`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/CsvImport/CsvImport.tsx frontend/src/i18n/locales/en.json frontend/src/i18n/locales/de.json frontend/src/components/CsvImport/CsvImport.test.tsx
git commit -m "fix: render localized entity-type labels instead of raw CamelCase enum values

Fixes #657"
```

---

## Task 9 (#651, #653, #654): Sidebar i18n language-mix claims — not reproducible, GitHub housekeeping only

**No code changes in this task.** Research (independently reading the exact commit `6b327df` these three issues cite, plus the current `SidebarNavigation.tsx`/`.module.css`/locale files) found:
- `SidebarNavigation.tsx` renders every label exclusively via `t(item.labelKey)`/`t(NAV_GROUP_LABEL_KEYS[group.id])` — no hardcoded strings anywhere.
- The specific keys the issues' commit reference (`nav.architecture`, `nav.audit`, `nav.groupArchitecture`) already had correct German values (`"Architektur"`) at that exact commit.
- The visual "ALL CAPS" impression the issues describe is `text-transform: uppercase` in CSS, applied uniformly to all group headers — not a language-mix bug.
- `#653` is a verbatim duplicate of `#651` (identical title, author, date, repro steps — only difference is ASCII-transliterated vs. real umlauts in the body text, a re-post artifact).
- `#654`'s claim is the same underlying "sidebar DE/EN mix" assertion as `#651`/`#653`, also not reproducible against current source.

**Task:**

- [ ] **Step 1: Close #653 as a duplicate of #651**

```bash
gh issue close 653 --reason "not planned" -c "Duplicate of #651 — identical title/author/date/repro steps, only difference is ASCII-transliterated umlauts in the body (re-post artifact). Closing here, tracking continues on #651."
```

- [ ] **Step 2: Comment on #651 with the non-reproduction finding, leave open for QA re-verification**

```bash
gh issue comment 651 -b "Investigated against the exact commit this issue cites (\`6b327df\`) and current \`main\`: \`SidebarNavigation.tsx\` renders every nav label exclusively through \`t(item.labelKey)\`/\`t(NAV_GROUP_LABEL_KEYS[group.id])\` — no hardcoded strings found anywhere in the component. The specific keys referenced in the cited commit (\`nav.architecture\`, \`nav.audit\`, \`nav.groupArchitecture\`) already had correct German values at that commit. The uppercase visual impression is \`text-transform: uppercase\` in CSS, applied uniformly — not a language-mix issue.

Could not reproduce the reported DE/EN mix against the current source. Possible explanation: a stale QA build, or a transient render captured mid-i18n-reseed on reload (see the BUG-01 comment at \`SidebarNavigation.tsx:316-327\` about i18n reseeding on reload, which is a separate, already-tracked concern). Leaving this open for QA to re-verify against a fresh build with exact repro steps (which page, which locale switch sequence, screenshot) rather than closing outright — please re-open/reconfirm with fresh evidence if still reproducible."
```

- [ ] **Step 3: Comment on #654 pointing at #651 as the tracking issue for this claim**

```bash
gh issue comment 654 -b "Same underlying claim as #651/#653 (sidebar DE/EN language mix) — investigated there, not reproducible against current source (see comment on #651 for the detailed finding). Consolidating tracking on #651 to avoid triplicate investigation; please add fresh repro evidence there if this is still observed."
```

---

## Task 10 (#652, #650): `ai_derivation` cold-start "LLM response was not valid JSON" — duplicate + fix

**Files:**
- Modify: `backend/application/ai_derivation_service.py:1834-1846` (`_complete_json_list`), `:1997` area (`_parse_json_object`/`_complete_json_object`, mirror the same change)
- Test: `backend/application/tests/test_ai_derivation_cold_start_retry.py`

**Duplicate status (verified):** `#650` and `#652` are identical (same title, author, version, repro steps, reporter). Close `#650` as a duplicate of `#652` (the more completely-formatted of the two, per research).

**Root cause (verified, with an explicitly-flagged unprovable remote-side hypothesis):** `_complete_json_list()` has no retry on `LlmResponseError` (raised when `json.loads()` fails on the raw completion text) — it evicts the cache entry and immediately re-raises. The observed behavior (fails once, a manual retry always succeeds) is exactly what a cache-evict-with-no-retry produces. The most likely underlying cause (not provable from this repo alone, since `mimo-v2.5`/`opencode.ai` is a remote provider) is that the upstream gateway occasionally returns HTTP 200 with an empty/truncated `content` field on a cold request — `OpencodeGoProvider._chat()` sets no `max_tokens`, unlike `AnthropicProvider`'s calls elsewhere in this file, which could compound the issue but isn't provably the root cause either.

**Fix (addresses the observed, reproducible symptom regardless of the unprovable remote root cause):** add one automatic retry with a short backoff inside `_complete_json_list`/`_complete_json_object` when `LlmResponseError` occurs on empty/unparsable content — this automates exactly the manual retry users already do successfully, without touching `resilient_transport.py`'s unrelated transport-level retry logic. Additionally, distinguish "empty completion" from "malformed JSON" in the error message so future diagnosis doesn't have to re-derive this.

- [ ] **Step 1: Close #650 as a duplicate**

```bash
gh issue close 650 --reason "not planned" -c "Duplicate of #652 — identical title/author/version/repro steps. Fix tracked and landing under #652."
```

- [ ] **Step 2: Write the failing test**

```python
# backend/application/tests/test_ai_derivation_cold_start_retry.py
from unittest.mock import MagicMock, patch

import pytest

from application.ai_derivation_service import AiDerivationService
from application.base import LlmResponseError


class TestColdStartRetry:
    def test_retries_once_on_empty_completion_then_succeeds(self):
        service = AiDerivationService()
        empty_then_valid = ["", '[{"title": "Derived requirement"}]']
        with patch.object(service, "_complete", side_effect=empty_then_valid):
            result = service._complete_json_list(prompt="derive from need X", purpose="need_to_sysreq")
        assert result == [{"title": "Derived requirement"}]

    def test_raises_a_distinct_error_for_empty_completion_vs_malformed_json(self):
        service = AiDerivationService()
        with patch.object(service, "_complete", return_value=""):
            with pytest.raises(LlmResponseError, match="empty completion"):
                service._complete_json_list(prompt="x", purpose="need_to_sysreq", max_retries=0)

    def test_raises_malformed_json_error_for_non_empty_unparsable_content(self):
        service = AiDerivationService()
        with patch.object(service, "_complete", return_value="not json at all"):
            with pytest.raises(LlmResponseError, match="not valid JSON"):
                service._complete_json_list(prompt="x", purpose="need_to_sysreq", max_retries=0)

    def test_gives_up_after_one_retry_if_still_failing(self):
        service = AiDerivationService()
        with patch.object(service, "_complete", return_value="") as mocked:
            with pytest.raises(LlmResponseError):
                service._complete_json_list(prompt="x", purpose="need_to_sysreq")
        assert mocked.call_count == 2  # original attempt + exactly 1 retry
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/application/tests/test_ai_derivation_cold_start_retry.py -v`
Expected: FAIL — no retry parameter/behavior exists yet, no distinct empty-completion error message.

- [ ] **Step 3: Implement**

In `ai_derivation_service.py`, modify `_parse_json_list` (around line 1916-1935) to distinguish empty content:

```python
def _parse_json_list(text: str) -> list:
    stripped = text.strip() if text else ""
    if not stripped:
        raise LlmResponseError("The LLM response was empty completion (cold-start or truncation).")
    # ... existing MOCK_FALLBACK_MARKER / codefence stripping unchanged ...
    try:
        parsed = json.loads(stripped)
    except (json.JSONDecodeError, TypeError) as exc:
        raise LlmResponseError("The LLM response was not valid JSON.") from exc
    return parsed
```

Apply the identical `if not stripped: raise LlmResponseError("...was empty completion...")` guard to `_parse_json_object` (the sibling function around line 1997).

In `_complete_json_list()` (line 1834-1846), add a bounded retry around the existing cache-evict-and-raise logic:

```python
def _complete_json_list(self, prompt: str, purpose: str, max_retries: int = 1) -> list:
    last_error = None
    for attempt in range(max_retries + 1):
        raw = self._complete(prompt, purpose=purpose)
        try:
            return _parse_json_list(raw)
        except LlmResponseError as exc:
            last_error = exc
            self._discard_cached_completion(prompt, purpose)
            if attempt < max_retries:
                continue
            raise
    raise last_error  # unreachable in practice, satisfies static analysis
```

Apply the same `max_retries`-bounded-retry wrapper to `_complete_json_object()`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/application/tests/test_ai_derivation_cold_start_retry.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Run the full ai_derivation test suite to confirm no regression**

Run: `pytest backend/application/tests/ -k ai_derivation -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/application/ai_derivation_service.py backend/application/tests/test_ai_derivation_cold_start_retry.py
git commit -m "fix: retry once on empty/unparsable LLM completion, distinguish empty from malformed-JSON errors

Fixes #652"
```

---

## Task 11 (#710): Inconsistent UUID error handling (400 vs 404) — documented as intentional, not a code fix

**Files:**
- Modify: `backend/rest_api/urls.py` (comment near the `needs`/`goals` route registration, if not already sufficiently commented — verify against the existing comments at `views.py:348-352` and `:5058-5067` first, which research found already explain this)
- Create: `backend/rest_api/tests/test_uuid_error_asymmetry_is_intentional.py`
- Modify: `docs/API.md` or equivalent API reference doc, if one exists with an error-handling section

**Decision (made in this plan, since the executing AI cannot ask the user):** **Option (b) — keep current behavior, document it as intentional, add a regression test that pins the asymmetry so future QA passes don't re-flag it.** Research confirmed this is not an oversight: `needs`/`goals` use a UUID-shaped `lookup_value_regex` specifically so a custom-action path segment like `derive-requirements` (missing its pk) 404s at the router level instead of reaching `retrieve()` and 500ing on `UUID(pk)` — this was itself a deliberate fix for REQ-128 and Issue #460 Finding 4, each with its own passing regression test (`test_non_uuid_detail_segment_returns_404`, `test_req128_non_uuid_action_segment_still_routes_to_404_not_400`, `test_goals_main_returns_404_not_a_uuid_validation_error`). Removing the regex (Option a) would flip those three tests' expected status from 404 to 400, un-fixing two previously-fixed bugs to fix a third, cosmetic inconsistency. Not worth that trade.

- [ ] **Step 1: Add a test that documents and pins the asymmetry as intentional**

```python
# backend/rest_api/tests/test_uuid_error_asymmetry_is_intentional.py
"""Pins the documented, intentional difference between requirements' 400
and needs'/goals' 404 for a malformed (non-UUID-shaped) path segment.

See #710 for the QA report that initially flagged this as inconsistent,
and #128 / #460 (Finding 4) for why needs/goals deliberately differ:
their lookup_value_regex must 404 on non-UUID segments so a custom-action
path (e.g. /needs/derive-requirements/, missing its pk) doesn't get
mistaken for a malformed pk and reach retrieve()'s UUID(pk) call.

DO NOT "fix" this asymmetry by removing needs'/goals' lookup_value_regex —
doing so re-opens #128 and #460 Finding 4 (a 500 on custom-action paths
without a pk). If a future decision changes this trade-off, update this
test's expectations deliberately, not accidentally.
"""
import pytest
from rest_framework.test import APIClient

from persistence.tests.factories import active_tenant, editor_user_and_token, make_workspace


@pytest.mark.django_db
class TestUuidErrorAsymmetryIsIntentional:
    def test_requirements_400s_on_malformed_pk(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            user, token = editor_user_and_token(tenant, ws)
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
            response = client.get("/api/v1/requirements/not-a-uuid/")
            assert response.status_code == 400

    def test_needs_404s_on_non_uuid_shaped_pk_by_design(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            user, token = editor_user_and_token(tenant, ws)
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
            response = client.get("/api/v1/needs/not-a-uuid/")
            assert response.status_code == 404

    def test_goals_404s_on_non_uuid_shaped_pk_by_design(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            user, token = editor_user_and_token(tenant, ws)
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
            response = client.get("/api/v1/goals/not-a-uuid/")
            assert response.status_code == 404
```

- [ ] **Step 2: Run the test to verify it documents current (correct, intentional) behavior**

Run: `pytest backend/rest_api/tests/test_uuid_error_asymmetry_is_intentional.py -v`
Expected: PASS immediately (no code change — this test documents existing intentional behavior)

- [ ] **Step 3: Comment on the issue with the decision and close it**

```bash
gh issue close 710 --reason "not planned" -c "Investigated: this is not an oversight. \`needs\`/\`goals\` deliberately use a UUID-shaped \`lookup_value_regex\` (see comments at \`backend/rest_api/views.py:348-352\` and \`:5058-5067\`) so that a custom-action path missing its pk (e.g. \`/needs/derive-requirements/\`) 404s at the router level instead of reaching \`retrieve()\` and 500ing on \`UUID(pk)\` — this was itself the deliberate fix for #128 and #460 (Finding 4), each pinned by its own regression test. Making \`needs\`/\`goals\` match \`requirements\`' 400-on-malformed-pk contract would require removing that regex, which would re-open both of those previously-fixed bugs to resolve a cosmetic inconsistency. Documented the asymmetry as intentional with a pinning regression test (\`test_uuid_error_asymmetry_is_intentional.py\`) so future QA passes don't re-flag it. Closing as working-as-intended."
```

- [ ] **Step 4: Commit the test**

```bash
git add backend/rest_api/tests/test_uuid_error_asymmetry_is_intentional.py
git commit -m "test: pin the intentional 400-vs-404 UUID error asymmetry between requirements and needs/goals

Related to #710 (closed as working-as-intended, not a bug)"
```

---

## Task 12 (#720): Sidebar not scrollable at small viewport heights — verify before fixing

**Files:**
- Create: `e2e/tests/sidebar-scroll.spec.ts`

**Why this task is verification-first, not a direct fix:** research found the sidebar's scroll region (`.scrollContent`, `SidebarNavigation.module.css:97-115`, with `min-height: 0` on its flex parent `.scrollWrapper`) is already correctly built for scrolling — the `overflow: hidden` the QA report measured belongs to the **outer** `<nav>` wrapper (`.navRoot`, line 88), which is a deliberate, different-purpose value (keeps the footer pinned, doesn't scroll with the nav items) already covered by an existing comment referencing issue #449. There is no unit/component test covering scroll behavior today, and the QA tooling may have measured the wrong DOM node. Blindly changing `overflow: hidden` on `.navRoot` risks breaking the pinned-footer behavior that was itself a deliberate prior fix — exactly the same category of mistake Task 11 above explicitly avoided.

- [ ] **Step 1: Write an E2E test that actually exercises the reported scenario**

```typescript
// e2e/tests/sidebar-scroll.spec.ts
import { test, expect } from "@playwright/test";

test.describe("Sidebar scroll at small viewport heights", () => {
  test("all nav links are reachable via scroll at 437px viewport height", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 437 }); // height from the #720 QA report
    await page.goto("/");
    // log in via existing E2E auth helper, navigate to a page with the full sidebar rendered
    const scrollContent = page.locator('[data-testid="sidebar-nav-scroll-content"]');
    // If this data-testid doesn't exist yet on .scrollContent, add it in Step 2 below
    // before this test can even run -- that's expected, not a bug in the test.
    const scrollHeight = await scrollContent.evaluate((el) => el.scrollHeight);
    const clientHeight = await scrollContent.evaluate((el) => el.clientHeight);
    expect(scrollHeight).toBeGreaterThan(clientHeight); // confirms content actually overflows

    await scrollContent.evaluate((el) => { el.scrollTop = el.scrollHeight; });
    const scrollTopAfter = await scrollContent.evaluate((el) => el.scrollTop);
    expect(scrollTopAfter).toBeGreaterThan(0); // confirms scrolling actually moved the content

    // Confirm the last nav link is now visible/reachable.
    const lastNavLink = page.locator('[data-testid^="nav-link-"]').last();
    await expect(lastNavLink).toBeInViewport();
  });
});
```

- [ ] **Step 2: Add the missing `data-testid` if `.scrollContent` doesn't already expose one**

Check `SidebarNavigation.tsx:447` (`<div ref={navScrollRef} className={styles.scrollContent}>`) — if it has no `data-testid`, add `data-testid="sidebar-nav-scroll-content"` there (a pure test-infrastructure addition, not a behavior change).

- [ ] **Step 3: Run the E2E test**

Run: `cd e2e && npx playwright test sidebar-scroll.spec.ts`

**Two possible outcomes, both are valid completions of this task — do not force a specific one:**
- **PASS**: the scroll region already works correctly; the original QA report's tooling measured the wrong (outer) DOM node. Comment on #720 explaining this with the test as evidence, and close it as a QA-tooling false positive (not a code bug) — same closing pattern as Task 9/11 above.
- **FAIL**: there is a genuine regression. In that case, investigate why `.scrollContent` isn't overflowing/scrolling as expected at this viewport height (check `.footer`'s `flex: 0 0 auto` sizing vs. available height, check whether `100vh` behaves unexpectedly under `position: fixed` at this breakpoint) and add a real CSS fix task here, following this plan's TDD pattern (failing E2E test → fix → passing E2E test → commit). Do not guess the fix in advance — the research explicitly could not determine which outcome is correct without live verification.

- [ ] **Step 4: Commit (whichever branch was taken)**

```bash
git add e2e/tests/sidebar-scroll.spec.ts frontend/src/components/NavigationShell/SidebarNavigation.tsx
git commit -m "test: add E2E coverage for sidebar scroll at small viewport heights

Fixes #720 (if PASS: confirms working-as-intended, closed as QA-tooling false positive; if FAIL: see accompanying CSS fix)"
```

---

## Task 13 (#661): Architecture tree missing visual connector lines

**Files:**
- Modify: `frontend/src/components/shared/WorkspaceTree/workspace-tree.module.css`
- Modify: `frontend/src/components/shared/WorkspaceTree/workspace-tree.tsx` (row wrapper element, to hang the connector pseudo-elements off)
- Test: `frontend/src/components/shared/WorkspaceTree/workspace-tree.test.tsx`

**Note:** research found no existing tree-line CSS anywhere in the frontend to copy — every tree implementation (`WorkspaceTree`, `RequirementTreeNode.tsx`) uses pure indentation (`paddingLeft`/`marginLeft` scaled by depth), no connector lines. This is new CSS, not a port of an existing pattern. `WorkspaceTree` is shared across multiple editors (not just `/architecture`), so this fix benefits all of them — but also means visual regression risk across all consumers, not just Architecture.

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/components/shared/WorkspaceTree/workspace-tree.test.tsx
it("renders a connector-line class on non-root tree rows", () => {
  render(<WorkspaceTree nodes={nestedNodes} onSelect={vi.fn()} />);
  const childRow = screen.getByTestId(/tree-row-child-node-id/);
  expect(childRow.className).toMatch(/treeLine/);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/components/shared/WorkspaceTree/workspace-tree.test.tsx`
Expected: FAIL — no `treeLine`-matching class exists yet.

- [ ] **Step 3: Implement**

Add to `workspace-tree.module.css`:
```css
.treeLine {
  position: relative;
}

.treeLine::before {
  content: "";
  position: absolute;
  left: calc(var(--tree-depth, 0) * 16px - 8px);
  top: 0;
  bottom: 50%;
  width: 1px;
  background: var(--color-border);
}

.treeLine::after {
  content: "";
  position: absolute;
  left: calc(var(--tree-depth, 0) * 16px - 8px);
  top: 50%;
  width: 8px;
  height: 1px;
  background: var(--color-border);
}
```
In `workspace-tree.tsx`, on the row element (near line 941 where `paddingLeft: \`${8 + depth * 16}px\`` is set), add the `treeLine` class conditionally (root-level nodes, `depth === 0`, don't get a connector since they have no parent to connect to) and set the CSS custom property inline:
```tsx
className={depth > 0 ? styles.treeLine : undefined}
style={{ paddingLeft: `${8 + depth * 16}px`, ["--tree-depth" as any]: depth }}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/components/shared/WorkspaceTree/workspace-tree.test.tsx`
Expected: PASS

- [ ] **Step 5: Visual regression check across all `WorkspaceTree` consumers**

Per project convention: since `WorkspaceTree` is shared, manually check (or run existing visual-regression E2E specs if any cover tree views) at least the Architecture tree AND one other consumer (e.g. Requirements tree view) to confirm the new connector lines render sensibly in both, not just Architecture.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/shared/WorkspaceTree/workspace-tree.module.css frontend/src/components/shared/WorkspaceTree/workspace-tree.tsx frontend/src/components/shared/WorkspaceTree/workspace-tree.test.tsx
git commit -m "feat: add visual connector lines to the shared workspace tree

Fixes #661"
```

---

## Task 14 (#594): CTA button label inconsistency — unify to the dominant `+ Neu(e/r/s) <Artefakt>` pattern

**Files:**
- Modify: `frontend/src/components/NeedsEditors/NeedList.tsx:305`, `frontend/src/components/RiskEditors/RiskEditors.tsx:219`, `frontend/src/components/AdrEditors/AdrEditors.tsx:220`, `frontend/src/components/Settings/UserManagement/UserManagement.tsx:327`, `frontend/src/components/ArchitectureEditors/ArchitectureEditors.tsx:532`, `frontend/src/components/TestCaseEditors/TestCaseEditors.tsx:220`, `frontend/src/components/IssueEditors/IssueEditors.tsx:220`
- Modify: `frontend/src/components/Settings/PromptVariablesSection.tsx:599`
- Modify: `frontend/src/components/AdminDialog/ApiKeysSection.tsx:214`
- Test: extend each touched component's existing test file with one assertion each (see Step 1 pattern, repeated per file)

**Convention decided in this plan:** entity-creation trigger buttons (list headers, empty states) all use the existing `+ Neu(e/r/s) <Entity>` pattern already implemented in `ModalDialogBase.tsx:122` (`+ ${t("actions.new")} ${title}`) and already the dominant style (17 of ~21 existing CTA keys already follow it). Form-submit buttons inside an already-open create dialog keep the existing bare `t("actions.create")` ("Erstellen") — that stays as-is, it's a different UI context (submit, not trigger) and is itself already consistent. This task only touches the **trigger** buttons currently using the wrong pattern.

- [ ] **Step 1: Write the failing tests (one per file, same shape)**

```tsx
// Example for frontend/src/components/NeedsEditors/NeedList.test.tsx — repeat this shape
// for RiskEditors.test.tsx, AdrEditors.test.tsx, UserManagement.test.tsx,
// ArchitectureEditors.test.tsx, TestCaseEditors.test.tsx, IssueEditors.test.tsx
it("uses the unified + New <Entity> trigger label instead of bare Erstellen", () => {
  i18n.changeLanguage("de");
  render(<NeedList />);
  expect(screen.getByTestId("need-list-create-trigger")).toHaveTextContent("+ Neuer Bedarf");
  expect(screen.queryByText("Erstellen")).not.toBeInTheDocument(); // only for the TRIGGER button, not any submit button also on screen
});
```

```tsx
// frontend/src/components/Settings/PromptVariablesSection.test.tsx
it("uses actions.create (Erstellen) instead of the removed Anlegen key", () => {
  i18n.changeLanguage("de");
  render(<PromptVariablesSection />);
  expect(screen.getByTestId("prompt-variable-create-submit")).toHaveTextContent("Erstellen");
});
```

```tsx
// frontend/src/components/AdminDialog/ApiKeysSection.test.tsx
it("uses the unified + New API Key trigger label", () => {
  i18n.changeLanguage("de");
  render(<ApiKeysSection />);
  expect(screen.getByTestId("api-key-create-trigger")).toHaveTextContent("+ Neuer API-Key");
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx vitest run -t "unified"` (or list each test file explicitly)
Expected: FAIL across all touched files.

- [ ] **Step 3: Fix each file**

For each of the 7 trigger-button files (`NeedList.tsx:305`, `RiskEditors.tsx:219`, `AdrEditors.tsx:220`, `UserManagement.tsx:327`, `ArchitectureEditors.tsx:532`, `TestCaseEditors.tsx:220`, `IssueEditors.tsx:220`): change the button text from `{t("actions.create")}` (or equivalent bare-"Erstellen" usage) to the existing per-domain `*.new<Entity>` key where one already exists (`needs.newNeed`, `risks.newRisk`, `adrs.newAdr`, `arch.newElement`, `testcases.newTestCase`, `issues.newIssue` — all confirmed to already exist per research) prefixed with `+ `:
```tsx
{`+ ${t("needs.newNeed")}`}
```
For `UserManagement.tsx:327`, no `users.newUser` key exists yet — add it to both locale files (DE: `"Neuer Nutzer"`, EN: `"New User"`) and use `` {`+ ${t("users.newUser")}`} ``.

For `PromptVariablesSection.tsx:599`: this is a **submit** button (inside an open create form, not a list-header trigger) — change from the standalone `"Anlegen"` (key `settings.promptVariables.create`) to the shared `actions.create` key (`"Erstellen"`), consistent with every other form's submit button. Remove the now-unused `settings.promptVariables.create` key from both locale files if nothing else references it (grep to confirm before deleting).

For `ApiKeysSection.tsx:214`: change from `` `+ ${t("actions.create", "Create")}` `` to `` `+ ${t("actions.new")} ${t("apiKeys.newKeyLabel")}` `` — add `apiKeys.newKeyLabel` to both locale files (DE: `"API-Key"`, EN: `"API Key"`). (`actions.new` already exists per `ModalDialogBase.tsx`'s usage.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npx vitest run -t "unified"`
Expected: PASS

- [ ] **Step 5: Run the i18n parity test**

Run: `cd frontend && npx vitest run src/test/i18n-parity.test.ts`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/NeedsEditors/NeedList.tsx frontend/src/components/RiskEditors/RiskEditors.tsx frontend/src/components/AdrEditors/AdrEditors.tsx frontend/src/components/Settings/UserManagement/UserManagement.tsx frontend/src/components/ArchitectureEditors/ArchitectureEditors.tsx frontend/src/components/TestCaseEditors/TestCaseEditors.tsx frontend/src/components/IssueEditors/IssueEditors.tsx frontend/src/components/Settings/PromptVariablesSection.tsx frontend/src/components/AdminDialog/ApiKeysSection.tsx frontend/src/i18n/locales/en.json frontend/src/i18n/locales/de.json
git commit -m "fix: unify CTA trigger-button labels to the + New <Entity> pattern

Fixes #594"
```

---

## Task 15: Full regression check + i18n coverage-ratchet baseline update

**Files:** none (verification-only task)

- [ ] **Step 1: Run the full backend test suite**

Run: `pytest backend/ -x -q`
Expected: PASS

- [ ] **Step 2: Run the full frontend test suite**

Run: `cd frontend && npx vitest run`
Expected: PASS

- [ ] **Step 3: Run the E2E suite (or at least the sidebar/tree/import specs touched by this plan)**

Run: `cd e2e && npx playwright test`
Expected: PASS

- [ ] **Step 4: Re-measure and lower the i18n coverage-ratchet baseline**

Run the same code-to-locale coverage scan `frontend/src/test/i18n-parity.test.ts` performs (line 139-156) manually or via the test itself, and update `MISSING_KEY_BASELINE` (currently `145`, line 137) down to the new, lower actual count — per that test's own documented convention. Do not skip this: several tasks in this plan (6, 7, 8, 9's investigation aside) fixed keys that were counted in the original 145.

Run: `cd frontend && npx vitest run src/test/i18n-parity.test.ts`
Expected: PASS with the new, lower baseline committed.

- [ ] **Step 5: Verify the ui-ratchet test (hex-literal/inline-style baselines) hasn't regressed**

Run: `cd frontend && npx vitest run src/test/ui-ratchet.test.ts`
Expected: PASS — this plan's CSS changes (Tasks 3, 13) use CSS custom properties throughout, no new hardcoded hex values or inline styles were introduced.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/test/i18n-parity.test.ts
git commit -m "chore: lower i18n MISSING_KEY_BASELINE after this session's locale fixes"
```

---

## Deliberately out of scope (this bugfix session)

- **#707, #161, #140** — Theming/design-token architecture. Already has its own approved spec + implementation plan (`docs/superpowers/specs/2026-08-24-theme-presets-design.md`, `docs/superpowers/plans/2026-08-24-theme-presets.md`) — implement that plan, don't duplicate work here.
- **#414** — Two unbridged ID spaces (Entity-ID vs Artifact-ID). Architectural, needs its own brainstorming per `docs/UMSETZUNGSPLAN_POST-1.7.0-BACKLOG.md` Group Q.
- **#682, #504, #711, #708** — Test infrastructure (E2E hang investigation, pre-existing shard failures, CI housekeeping) and a security finding already investigated and found non-reproducible pending QA re-verification (#708) — none of these are application code bugs fixable by this plan's task shape.
- **#719, #718, #660, #656, #655, #596** — UI-audit findings that are symptoms of the same missing Design-System-Konsolidierung (unified header/card/CTA component system) per `docs/UMSETZUNGSPLAN_POST-1.7.0-BACKLOG.md` Group M — bundling them into isolated single-issue fixes would mean touching the same header/layout primitives repeatedly across unrelated PRs; they need one coherent redesign plan of their own, not inclusion here.
