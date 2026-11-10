# Phase H — Hermes-Plugin Requirements-CRUD Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Das Hermes-Plugin `integrations/hermes-plugin/reqogniloom` bekommt Requirements-Ansichten (Liste, Detail, Anlegen, Bearbeiten), gebaut auf dem aktuellen `main`. Danach #1701 schließen.

**Architecture:** `ConnectedView` bleibt der Hub. Drei neue `View`-Zustände (`requirements`, `requirement-detail`, `requirement-form`) mit Rückweg nach `connected`. Die REST-Funktionen kommen in `src/api.ts` (gleiches `reqloFetch` mit Timeout, Fehlerhülle und Seitenfolge wie `listWorkspaces`), der Zustand in `src/state.ts` (Muster der Interview-Aktionen), die Ansichten in je einer neuen Datei. Der alte Branch `e0219a76` dient nur als Referenz für Struktur und Texte. Der Code wird neu geschrieben, weil das Backend sich geändert hat (Ebene ist abgeleitet, siehe Befund).

**Tech Stack:** React 18 (Plugin-Paket, nicht React 19 des Hauptfrontends), TypeScript, Vite, Vitest mit Testing Library, REST `/api/v1/requirements/`, `X-API-Key`.

**Spec:** `docs/superpowers/plans/2026-11-10-backlog-roadmap.md` Phase H. Issue #1701.

## Befund (origin/main 3563515f)

| Punkt | Stand | Beleg |
|---|---|---|
| Requirements-Ansichten im Plugin | **fehlen** | `integrations/hermes-plugin/reqogniloom/src/` enthält Connect, Connected, Interviews, keine Requirements. `View = "connect" \| "connected" \| "interviews"` (`state.ts:17`) |
| Hub und Hilfen | vorhanden | `ConnectedView.tsx` (Buttons Open ReqogniLoom, Interviews, Disconnect), `uiKit.tsx` (`buttonStyle`, `ErrorBanner`), `ReqogniLoomPanel.tsx` (Rendern nach `state.view`) |
| API-Schicht | gehärtet, zu erhalten | `api.ts`: verschachtelte und flache Fehlerhüllen (`ErrorEnvelope`), Seitenfolge in `listWorkspaces` (PLUG-02), `REQUEST_TIMEOUT_MS = 15_000`, Nicht-JSON-Bodies (`parseNetworkResult`) |
| Alter Branch | nicht mergebar | `e0219a76` (Aug 2026): 7 von 13 Code-Dateien konfliktieren, `ConnectedView` gelöscht, `api.ts` ohne die Härtung, `hermes-api-types.ts` ohne `shell` |
| **Backend-Änderung seit dem alten Branch** | **wichtig** | `Requirement.level` ist **abgeleitet und schreibgeschützt** (ADR-005, ADR-027): Die Antwort trägt `level`, `tier_key`, `tier_name`, `level_source`, `allocation_intent`, `suspect`, `atomicity_warning`; `level_override` existiert als manueller Override (`rest_api/serializers.py:1285-1560`). Der alte `CreateRequirementInput.level` würde ignoriert oder abgelehnt |
| CI | vorhanden | Job "Hermes Agent Plugin" in der CI, Paket-Skripte `build`, `verify-build`, `test` (`package.json`) |
| Interviews im Plugin | per MCP | `src/mcpClient.ts`, nicht REST. Requirements nutzen REST wie `listWorkspaces` |

## Global Constraints

- Branch von `origin/main` (Fetch nur mit `git fetch origin +refs/heads/main:refs/remotes/origin/main`). Git-Mutationen nur über den `git`-Agenten. Commits englisch, Conventional Commits, höchstens 72 Zeichen, Trailer `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>` und `Claude-Session: https://claude.ai/code/session_01JYx6yrB2hSodcXeSkA5mAq`. Commit-Nachricht als Datei vorgeben, mit `git commit -F`.
- `ConnectedView` bleibt, nur um einen Einstieg "Requirements" ergänzt. `api.ts` behält die Härtung vollständig (siehe Befund). `hermes-api-types.ts` behält `shell`.
- Plugin-UI bleibt englischer Text ohne i18n (bewusste Entscheidung, Kopfkommentar in `ReqogniLoomPanel.tsx`). Alle interaktiven Elemente tragen `data-testid`.
- Keine neue Abhängigkeit. `package-lock.json` bleibt unverändert, außer die Version in `hermes-plugin.json` wird vom Release-Skript gepflegt (nicht von Hand ändern).
- Die API-Key-Rechte sind die des Nutzers: Ein Read-Key bekommt beim Speichern HTTP 403, die UI zeigt das als Fehlerbanner, nicht als Absturz.
- Tests: `cd integrations/hermes-plugin/reqogniloom && npx vitest run <Pfad>`. Vor jedem Commit `npm run build` (führt `verify-build` aus) und `npx tsc --noEmit`, falls ein `tsconfig` es vorsieht.
- Schließen von Issues erst nach Freigabe durch Daniel.

## Review Focus

- Schreibgeschütztes `level`: Das Formular sendet `level` und der Server lehnt ab oder ignoriert still. Test: Task 2, der Create-/Update-Body enthält nie `level`, `tier_key` oder `level_source`.
- Fehlerhüllen: 400 mit `details` je Feld (verschachtelt) und flacher Fehler werden nicht angezeigt. Test: Task 2, beide Hüllen erscheinen als lesbare Meldung, Feldfehler am Feld.
- Optimistic Lock: Update ohne aktuelle `version` überschreibt fremde Änderungen. Test: Task 2, `PATCH` sendet `version`, 409 zeigt "changed elsewhere, reload" und behält die Eingabe.
- Change-Reason-Pflicht: Im Standard- und Extended-Preset verlangt ein Update einen Änderungsgrund. Test: Task 2, 400 wegen `change_reason` zeigt ein Pflichtfeld im Formular, kein stilles Scheitern.
- Seitenfolge: Liste mit mehr als einer Seite. Test: Task 2, "Next"/"Previous" laden Seite 2 und zurück, `page_size=25`, eine wiederholte `next`-URL beendet die Kette.
- Leerer Workspace und Netzfehler: Test: Task 3, Leerzustand mit Anlegen-Button, Netzfehler als Banner mit Retry.
- Verlust von Eingaben beim Zurück: Test: Task 3, "Back" aus dem Formular mit ungespeicherten Änderungen fragt nach oder behält den Entwurf bis zum Verlassen.

---

### Task 1: API-Vertrag prüfen und festschreiben

**Files:**
- Read: `backend/rest_api/serializers.py:1285-1560` (`RequirementSerializer`), `backend/rest_api/views.py` (Requirement-ViewSet), OpenAPI `/api/schema/`

**Interfaces:** Produces: bestätigte Feldliste für Create, Update und Liste.

- [ ] **Step 1: Felder bestätigen**

Run: `cd backend && grep -n "class RequirementSerializer" -A260 rest_api/serializers.py | grep -n "required\|read_only" | head -40`
Expected: schreibbar: `workspace_id` (nur Create), `parent_id`, `title`, `description`, `acceptance_criteria`, `category`, `type` (`SyReq|UseCase|FeatureReq`), `complexity_fibonacci`, `verification_method`, `change_reason` (Update). Schreibgeschützt: `id`, `artifact_id`, `uid`, `level`, `tier_key`, `tier_name`, `level_source`, `allocation_intent`, `suspect`, `version`, `created_at`, `updated_at`, `atomicity_warning`. Abweichungen hier im Typmodul festhalten, nicht im Plan raten.

- [ ] **Step 2: Statusfeld und Liste prüfen**

Wo `status` herkommt (Workflow-Zustand, `status` im Serializer-Mixin) und welche Filter die Liste kennt (`search`, `page`, `page_size`, `workspace_id`, unbekannte Parameter werden abgelehnt, #1509).
Run: `cd backend && grep -n "extra=" rest_api/views.py | sed -n 1,6p`
Expected: Liste der erlaubten Parameter. `search` und `page_size` müssen dazugehören, sonst entfällt die Suche im Plugin.

---

### Task 2: API-Funktionen und Zustand

**Files:**
- Modify: `integrations/hermes-plugin/reqogniloom/src/api.ts`, `src/state.ts`, `src/hermes-api-types.ts` (nur falls ein Typ fehlt, `shell` erhalten)
- Test: `src/__tests__/api.test.ts` (ergänzen, bestehende Fälle unverändert), `src/__tests__/state.test.ts` (ergänzen)

**Interfaces:**
- Consumes: `reqloFetch(network, baseUrl, apiKey, path, options)`, `Connection { baseUrl, apiKey, workspaceId }`, `ReqogniLoomApiError(status, envelope, message)`.
- Produces:
  - Typen: `RequirementType = "SyReq" | "UseCase" | "FeatureReq"`, `VerificationMethod = "Test" | "Review" | "Analysis" | "Inspection" | "Demonstration"`, `Requirement` (lesende Felder aus Task 1 Step 1), `RequirementListResponse { count; next; previous; results }`, `CreateRequirementInput { title; description?; acceptance_criteria?; category?; type?; complexity_fibonacci?; verification_method?; parent_id? }` (**ohne `level`**), `UpdateRequirementInput = Partial<CreateRequirementInput> & { version: number; change_reason?: string }`.
  - API: `listRequirements(network, connection, params: { search?: string; page?: number; pageSize?: number }) => Promise<RequirementListResponse>`, `getRequirement(network, connection, id: string) => Promise<Requirement>`, `createRequirement(network, connection, input: CreateRequirementInput) => Promise<Requirement>`, `updateRequirement(network, connection, id: string, input: UpdateRequirementInput) => Promise<Requirement>`.
  - Zustand: `View` erweitert um `"requirements" | "requirement-detail" | "requirement-form"`; `AppState` um `requirements: Requirement[]`, `requirementsPage: number`, `requirementsNext: string | null`, `requirementsPrevious: string | null`, `requirementsCount: number`, `requirementsSearch: string`, `activeRequirement: Requirement | null`, `requirementForm: { mode: "create" | "edit"; values: RequirementFormValues; fieldErrors: Record<string, string>; changeReason: string } | null`, `requirementError: string | null`, `requirementBusy: boolean`.
  - Aktionen: `openRequirements(): Promise<void>`, `searchRequirements(term: string): Promise<void>`, `requirementsPageNext(): Promise<void>`, `requirementsPagePrevious(): Promise<void>`, `selectRequirement(id: string): Promise<void>`, `openCreateForm(): void`, `openEditForm(): void`, `updateFormField(name: string, value: string): void`, `submitForm(): Promise<void>`, `backToList(): void`, `backToConnected(): void`.

- [ ] **Step 1: Failing Tests**

```ts
// api.test.ts
it("lists requirements for the workspace with page and page_size", async () => {
  const { network, calls } = fakeNetwork({ body: { count: 1, next: null, previous: null, results: [REQ] } });
  await listRequirements(network, CONN, { page: 2, pageSize: 25, search: "login" });
  expect(calls[0].url).toBe("https://x/api/v1/requirements/?workspace_id=WS&page=2&page_size=25&search=login");
  expect(calls[0].headers["X-API-Key"]).toBe("KEY");
});
it("create sends workspace_id and never level/tier_key/level_source", async () => {
  await createRequirement(network, CONN, { title: "T", ...({ level: 3 } as object) });
  const body = JSON.parse(calls[0].body); expect(body.workspace_id).toBe("WS"); expect(body).not.toHaveProperty("level");
});
it("update sends version and change_reason", async () => {...});
it("maps nested and flat error envelopes to ReqogniLoomApiError", async () => {...});
// state.test.ts
it("openRequirements loads page 1 and switches the view", ...);
it("submitForm in edit mode PATCHes with the loaded version", ...);
it("submitForm shows field errors from a 400 details array", ...);
it("submitForm on 409 keeps the form values and shows the reload hint", ...);
it("submitForm on 403 shows a permission banner and stays in the form", ...);
it("pagination follows next and previous and stops on a repeated next", ...);
```
Run: `cd integrations/hermes-plugin/reqogniloom && npx vitest run src/__tests__/api.test.ts src/__tests__/state.test.ts` — Expected: FAIL, Funktionen fehlen.

- [ ] **Step 2: API-Funktionen implementieren**

In `api.ts` nach dem Muster von `listWorkspaces` (`reqloFetch`, gleiche Fehlerhülle). `createRequirement` filtert schreibgeschützte Felder defensiv heraus (`level`, `tier_key`, `level_source`, `id`, `uid`, `version`) und setzt `workspace_id` aus der Verbindung. Der alte Branch dient als Strukturvorlage (`git show e0219a76:integrations/hermes-plugin/reqogniloom/src/api.ts`), die Typen kommen aus Task 1.

- [ ] **Step 3: Zustand implementieren**

In `state.ts` Aktionen nach dem Muster von `openInterviews`/`startNewInterview` (Busy-Flag, Fehlertext in `requirementError`, `notify()` bei jeder Änderung, `ReqogniLoomApiError.status === 409` und `403` gesondert). `__resetStateForTesting` setzt die neuen Felder zurück.

- [ ] **Step 4: Tests grün**

Run: `cd integrations/hermes-plugin/reqogniloom && npx vitest run src/__tests__/api.test.ts src/__tests__/state.test.ts`
Expected: PASS, bestehende Fälle (Interviews, Restore, Seitenfolge, Fehlerhüllen) unverändert.

- [ ] **Step 5: Commit** (über `git`-Agent): `feat(hermes-plugin): add requirements API and state`

---

### Task 3: Ansichten

**Files:**
- Create: `src/RequirementsList.tsx`, `src/RequirementDetail.tsx`, `src/RequirementForm.tsx`
- Modify: `src/ConnectedView.tsx` (Button "Requirements"), `src/ReqogniLoomPanel.tsx` (Rendern nach `state.view`)
- Test: `src/__tests__/RequirementsList.test.tsx`, `RequirementDetail.test.tsx`, `RequirementForm.test.tsx`, `ConnectedView.test.tsx` (ergänzen), `ReqogniLoomPanel.test.tsx` (ergänzen)

**Interfaces:**
- Consumes: Aktionen und Zustand aus Task 2, `buttonStyle`, `ErrorBanner` aus `uiKit.tsx`.
- Produces: `RequirementsList({ state })`, `RequirementDetail({ state })`, `RequirementForm({ state })`. `data-testid`: `open-requirements-button`, `requirements-search-input`, `requirements-list`, `requirement-row-<id>`, `requirements-next-button`, `requirements-previous-button`, `requirements-new-button`, `requirements-back-button`, `requirement-edit-button`, `requirement-form-title`, `requirement-form-description`, `requirement-form-acceptance`, `requirement-form-category`, `requirement-form-type`, `requirement-form-change-reason`, `requirement-form-submit`, `requirement-form-cancel`, `requirement-error`.

- [ ] **Step 1: Failing Tests**

```tsx
it("ConnectedView offers a Requirements entry next to Interviews", ...);
it("list renders rows with uid, title, status and tier name, and opens the detail on click", ...);
it("list shows an empty state with a New button for an empty workspace", ...);
it("list shows the network error banner with a retry", ...);
it("detail shows level, tier name, level source and the suspect flag read-only", ...);
it("form in edit mode prefills values and has no level field", () => { expect(screen.queryByTestId("requirement-form-level")).toBeNull(); });
it("form shows a required change-reason field when the server demanded one", ...);
it("form shows field errors next to the field", ...);
it("back from a dirty form asks for confirmation", ...);
it("panel renders the requirements view for state.view === 'requirements'", ...);
```
Run: `cd integrations/hermes-plugin/reqogniloom && npx vitest run src/__tests__/RequirementsList.test.tsx src/__tests__/RequirementDetail.test.tsx src/__tests__/RequirementForm.test.tsx` — Expected: FAIL.

- [ ] **Step 2: Ansichten implementieren**

Strukturvorlage: die drei View-Dateien im alten Branch (`git show e0219a76:integrations/hermes-plugin/reqogniloom/src/RequirementsList.tsx` usw.), Stil über CSS-Variablen der Host-App (`var(--text-sm)` usw., wie die bestehenden Views), keine neuen Farben. `ConnectedView` bekommt `open-requirements-button` vor dem Interviews-Button.

- [ ] **Step 3: Tests grün, Build**

Run: `cd integrations/hermes-plugin/reqogniloom && npx vitest run && npm run build`
Expected: PASS, `verify-build` grün, das gebaute `dist/plugin.js` enthält den Requirements-Einstieg.

- [ ] **Step 4: Commit** (über `git`-Agent): `feat(hermes-plugin): add requirements list, detail and form views`

---

### Task 4: Dokumentation, Verteilung, Schließen

**Files:**
- Modify: `integrations/hermes-plugin/reqogniloom/README.md` (Funktionsumfang), ggf. `docs/clients/hermes.md` und `docs/clients/hermes.de.md`
- Generated: Verteil-Artefakte nur über `python scripts/clients/render.py` falls die Doku daraus erzeugt wird

**Interfaces:** Consumes: Tasks 2 und 3 gemergt.

- [ ] **Step 1: README und Clientdoku**

Requirements-Ansichten, Rechte (Read-Key kann nur lesen), bekannte Grenzen (kein Löschen, keine Allokation, Ebene nur lesend).

- [ ] **Step 2: Gates**

Run: `python scripts/clients/render.py --check && cd integrations/hermes-plugin/reqogniloom && npx vitest run && npm run build`
Expected: PASS.

- [ ] **Step 3: Schließen (nach Freigabe)**

```bash
gh issue close 1701 --reason completed --comment "Erledigt auf aktuellem main: Requirements-Liste, -Detail und -Formular im Hermes-Plugin (ConnectedView bleibt Hub, api.ts-Härtung erhalten). Level wird nur gelesen (abgeleitet, ADR-005/027). Der alte Branch e0219a76 war nicht mergebar und diente nur als Referenz. PRs: #<N>."
```

- [ ] **Step 4: Aufräumen (nur auf Anweisung von Daniel)**

Der alte Remote-Branch `feat/hermes-plugin-requirements-crud` ist durch diese Umsetzung überholt. Löschen nur über den `git`-Agenten und nur mit ausdrücklicher Freigabe.

- [ ] **Step 5: Endstand**

Run: `gh issue view 1701 --json state --jq .state`
Expected: `CLOSED`.

---

## Self-Review

- **Abdeckung:** Alle Punkte aus #1701: neuer Branch von `main`, `ConnectedView` als Hub mit neuem Einstieg, `requirements`/`requirement-detail`/`requirement-form` als Zustände mit Rückweg, `uiKit` (`buttonStyle`, `ErrorBanner`), `data-testid`, Härtung von `api.ts` erhalten, `shell` erhalten, Tests ergänzt statt ersetzt.
- **Neu gegenüber dem Issue:** Das Backend hat sich seit dem alten Branch geändert (Ebene ist abgeleitet und schreibgeschützt, Optimistic Lock über `version`, Pflicht für `change_reason` je Preset). Der Plan trägt das in Typen, Tests und Formular nach. Der alte Code wäre in diesen drei Punkten falsch.
- **Typkonsistenz:** `UpdateRequirementInput` (Task 2) verlangt `version`, die Aktion `submitForm` liest sie aus `activeRequirement.version`. Die `data-testid`-Namen in Task 3 stehen nur dort.
- **Unsicher, im Step zu bestätigen:** (a) erlaubte Listenparameter und `status`-Herkunft (Task 1 Step 2), (b) ob der Hermes-Host einen `confirm`-Dialog erlaubt (für "Back" aus dem Formular; sonst Entwurf im State behalten), (c) Name und Pfad der Clientdoku für Hermes.
- **Nicht ausgeführt:** Kein Befehl dieses Plans lief. Die Plugin-Struktur stammt aus der Lektüre von beta.29 (`src/` mit 12 Dateien, 1293 Zeilen).
