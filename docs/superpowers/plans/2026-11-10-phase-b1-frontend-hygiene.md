# Phase B1 — Frontend-Hygiene Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Die wirklich offenen Reste aus #598 (S2 Gott-Komponenten, S3 Data-Fetching) umsetzen, #1287, #1094 und #186 mit Beleg schließen, #598 abschließen.

**Architecture:** Zuerst Beleg und Schließen dessen, was auf beta.29 schon erledigt ist. Dann S3 (react-query) für MetricsDashboard. S2 wird nicht nach Zeilenzahl, sondern nach technischer Zuständigkeit angegangen: ein Analyse-Skript clustert die Deklarationen jeder Komponente nach gemeinsamen Bezeichnern (Kohäsionsgraph), kombiniert das mit Churn und Komplexität (Hotspot-Analyse), und nur Dateien mit mehreren unabhängigen Zuständigkeiten werden zerlegt. `audit-dashboard.tsx` ist der erste, schon verstandene Fall und nimmt S3 gleich mit.

**Tech Stack:** React 19, TypeScript 5.5 (Compiler-API für die Analyse), Vitest 5, `@tanstack/react-query` 5.104, ESLint 10, `gh` CLI (`export PATH=$PATH:~/.local/bin`).

**Spec:** `docs/superpowers/plans/2026-11-10-backlog-roadmap.md`, Phase B, Entscheidungen 3 und 5 (5 ist gegenstandslos, siehe Befund), plus Daniels Vorgabe vom 2026-11-10: "Best Practice aus der Literatur, Clusterung nach technischen Zuständigkeiten, kein harter Zeilenwert".

## Befund (auf origin/main 4f8aa29f, beta.29, verifiziert)

| Punkt | Stand | Beleg |
|---|---|---|
| #598 W1/S6 | erledigt | `frontend/src/api/artifactRefs.ts:94` `resolveArtifactRefs` löst per `traceabilityApi.resolve` in Batches |
| #598 W2 | erledigt | `grep -c "#[0-9a-fA-F]\{6\}" MetricsDashboard.tsx` = 0 |
| #598 W3 | erledigt | `MetricsDashboard.tsx:663` `t(\`metrics.help.${spec.name}\`, …)` |
| #598 W4 | erledigt | `ErrorBoundary.tsx` hält die Message nicht im State, nur `referenceId` |
| #598 W5 | erledigt | `WorkflowEditor.module.css:43` `flex-wrap: wrap` (#596) |
| #598 S4 | erledigt | `NavigationShell.tsx:216-224` `<Navigate>` für `/trace-links`, `/test-cases`, `/impact-analysis` |
| #598 S5 | erledigt | alle CTA-Labels sind "New …"/"Neues …" (`testRuns.create` = "New Test Run") |
| #598 S3 | **offen** | `MetricsDashboard.tsx:441-505` `useState`+`useEffect`+Hand-`isStale`; `audit-dashboard.tsx` 6+ `useEffect` |
| #598 S2 | **offen** | 20 Dateien über 700 Zeilen, größte `workspace-tree.tsx` 1933, `audit-dashboard.tsx` 1726, `CanvasEditor.tsx` 1448 |
| #1094 | erledigt | #1096 (geschlossen): `GET/PATCH /users/me/display-preferences/`, `PreferencesHydrator`, `IdentifiersSection` |
| #1287 | wahrscheinlich erledigt | `shared/MarkdownField/MarkdownField.tsx` mit Preference `ui.markdown.toolbar` (auto/on/off), verwendet in `MarkdownTabGroup` und `MarkdownPreview`. Einsatz ist zu prüfen |
| #186 | Tracker ohne Arbeit | alle 19 Sub-Issues geschlossen, `src/test/ui-ratchet.test.ts` friert Kennzahlen ein |

## Global Constraints

- Branch von `origin/main`, nie lokales `main`. Git-Mutationen nur über den `git`-Agenten.
- Commits: Conventional Commits, Englisch, höchstens 72 Zeichen. Trailer `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>` und `Claude-Session: https://claude.ai/code/session_01JYx6yrB2hSodcXeSkA5mAq`.
- Refactoring ändert kein Verhalten. Vorher grüne Tests bleiben ohne Änderung grün. Neue Tests pinnen das Verhalten der extrahierten Einheit.
- `data-testid` aller interaktiven Elemente bleibt unverändert.
- Keine hartcodierten Farben/Größen (`styles/tokens.css`), kein neuer Text ohne i18n-Schlüssel in `de.json` und `en.json`.
- Kein neues npm-Paket.
- Volle Testläufe nur sequentiell (Host hat ~5,8 GiB RAM). Zielgerichtet: `cd frontend && npx vitest run <Pfad>`.
- Vor jedem Commit: `cd frontend && npx tsc --noEmit -p . && npx eslint <geänderte Dateien>`.
- Schließen von Issues erst nach Freigabe durch Daniel.

## Review Focus

- Charakterisierungslücke: Eine Zerlegung ändert still Verhalten, weil die bestehenden Tests nur einen Teil der Datei abdecken. Tests: Task 5 schreibt vor jedem Refactoring einen Test, der den Zustand der extrahierten Zuständigkeit festnagelt (Fehlerpfad, Abbruch beim Unmount, Wechsel des Workspace).
- Stale Daten nach Wechsel: Beim Wechsel von Workspace oder Filter zeigt das Dashboard kurz Werte des alten Kontexts. Test: Task 3.
- Fehlerzustand mit Altdaten: Ein Refresh schlägt fehl, die letzten Werte bleiben sichtbar und werden als veraltet markiert (heutiges `isStale`). Test: Task 3.
- Race: Antwort einer überholten Anfrage überschreibt neuere. Test: Task 6 (Audit-Lauf, Scope-Wechsel während des Laufs).
- Hotspot-Skript liefert für Dateien mit sehr kleinen Komponenten oder reinen Typmodulen unsinnige Cluster. Test: Task 4 prüft das Skript an zwei Fixture-Dateien (eine kohäsiv, eine mit drei unabhängigen Zuständigkeiten).

---

### Task 1: Erledigtes belegen und schließen (#1094, #186)

**Files:** keine.

**Interfaces:** Produces: #1094 und #186 geschlossen. Zähler −2.

- [ ] **Step 1: Beleg für #1094 prüfen**

Run: `cd frontend && grep -n "display-preferences\|show_readable_ids" src/api/display-preferences.ts src/components/PreferencesHydrator.tsx src/components/UserProfileSettings/IdentifiersSection.tsx | head`
Expected: Treffer in allen drei Dateien. Zusätzlich `gh issue view 1096 --json state --jq .state` = `CLOSED`.

- [ ] **Step 2: Freigabe von Daniel einholen, dann schließen**

```bash
gh issue close 1094 --reason completed --comment "Erledigt. Der damals fehlende Profil-Endpunkt existiert seit #1096: GET/PATCH /api/v1/users/me/display-preferences/ (Q1-Schlüssel ui.ids.show_readable), PreferencesHydrator hydriert beim App-Start, IdentifiersSection schreibt. IdChip kopiert immer die System-ID. localStorage ist nur noch First-Render-Cache (useReadableIdsVisible)."
gh issue close 186 --reason completed --comment "Alle 19 Sub-Issues der Umsetzungstabelle sind geschlossen, die Kennzahlen sind per frontend/src/test/ui-ratchet.test.ts eingefroren. Der Epic hat keine Arbeit mehr. Rest geht in das Inspector-Konzept (Trace-Spine, docs/UI_KONZEPT.md §5, siehe Phase B2 der Backlog-Roadmap) und in kleine Issues für Button-Höhen und Radien (Audit vom 2026-10-13)."
```

- [ ] **Step 3: Verifizieren**

Run: `gh issue view 1094 --json state --jq .state; gh issue view 186 --json state --jq .state`
Expected: zweimal `CLOSED`

---

### Task 2: #1287 prüfen und schließen

**Files:**
- Read: `frontend/src/components/shared/MarkdownField/MarkdownField.tsx`
- Read: `frontend/src/components/shared/ArtifactForm/widgets/MarkdownTabGroup.tsx`
- Test: `frontend/src/components/shared/MarkdownField/MarkdownField.coverage.test.tsx` (neu, bleibt im Repo)

**Interfaces:** Produces: Nachweis, dass jedes Markdown-Eingabefeld über `MarkdownField` läuft, sonst Liste der Lücken.

- [ ] **Step 1: Alle Markdown-Eingabestellen finden**

Run: `cd frontend/src && grep -rln "MarkdownToolbar\|markdown_tab_group\|<MarkdownPreview" . --include=*.tsx | grep -v test`
Expected: jede Datei bindet `MarkdownField` ein oder nutzt `MarkdownTabGroup`/`MarkdownPreview`, die es einbinden.

- [ ] **Step 2: Test schreiben, der die Regel festhält**

```tsx
// MarkdownField.coverage.test.tsx
it("no component renders <MarkdownToolbar> outside MarkdownField", () => {
  const offenders = collectTsx("src/components")
    .filter((f) => !f.includes("shared/MarkdownField/") && !f.endsWith(".test.tsx"))
    .filter((f) => readFileSync(f, "utf8").includes("<MarkdownToolbar"));
  expect(offenders).toEqual([]);
});
```
`collectTsx` analog zu `collectFiles` in `src/test/ui-ratchet.test.ts`. Run: `cd frontend && npx vitest run src/components/shared/MarkdownField`. Expected: PASS. Bei FAIL: die Offender sind die Lücken, ein Fix-Task pro Offender (nutze `MarkdownField` statt direkter Toolbar).

- [ ] **Step 3: Verhalten per Test belegen**

Ein Test pro Modus (`auto`, `on`, `off`) existiert in `MarkdownField.test.tsx`. Prüfen mit `npx vitest run src/components/shared/MarkdownField -t "mode"`. Fehlende Modi ergänzen.

- [ ] **Step 4: Nach Freigabe schließen**

```bash
gh issue close 1287 --reason completed --comment "Erledigt. shared/MarkdownField löst die Preference ui.markdown.toolbar (auto/on/off, Q1 auf System/Workspace/User) auf und schaltet die Formatierungszeile. Alle Markdown-Eingabestellen laufen darüber, abgesichert durch MarkdownField.coverage.test.tsx."
```

- [ ] **Step 5: Commit** (über `git`-Agent): `test(editor): pin all markdown fields to MarkdownField`

---

### Task 3: S3 — MetricsDashboard auf react-query

**Files:**
- Create: `frontend/src/queries/metrics.ts`
- Create: `frontend/src/queries/metrics.test.ts`
- Modify: `frontend/src/components/MetricsDashboard/MetricsDashboard.tsx:441-505` (Laden, History, `isStale`)
- Test: `frontend/src/components/MetricsDashboard/MetricsDashboard.test.tsx` (bestehend, bleibt unverändert grün)

**Interfaces:**
- Consumes: `metricsApi.list(workspaceId: UUID, options: MetricsQueryOptions): Promise<MetricsResult>` aus `frontend/src/api/metrics.ts:177`; Muster der Query-Hooks in `frontend/src/queries/preferences.ts` (`preferenceKeys`, `useQuery`).
- Produces: `metricsKeys.list(workspaceId: UUID, type?: string): readonly unknown[]` und `useMetricsQuery(workspaceId: UUID | undefined, options: { type?: string }): UseQueryResult<MetricsResult>` (`enabled: !!workspaceId`).

- [ ] **Step 1: Failing Tests für den Hook**

```ts
// queries/metrics.test.ts
it("fetches metrics for the workspace and type", async () => {
  metricsApi.list = vi.fn().mockResolvedValue(RESULT);
  const { result } = renderHook(() => useMetricsQuery(WS, { type: "requirement" }), { wrapper });
  await waitFor(() => expect(result.current.data).toEqual(RESULT));
  expect(metricsApi.list).toHaveBeenCalledWith(WS, { type: "requirement" });
});
it("is disabled without a workspace", () => {
  const { result } = renderHook(() => useMetricsQuery(undefined, {}), { wrapper });
  expect(result.current.fetchStatus).toBe("idle");
});
it("keeps previous data and flags error when a refetch fails", async () => { /* data bleibt, isError true */ });
```
Run: `cd frontend && npx vitest run src/queries/metrics.test.ts` — Expected: FAIL, `useMetricsQuery` fehlt.

- [ ] **Step 2: `queries/metrics.ts` implementieren**

`useQuery` mit `queryKey: metricsKeys.list(...)`, `queryFn: () => metricsApi.list(workspaceId, options)`, `staleTime` wie `PREFERENCES_STALE_TIME_MS`-Muster, aber 0 (Dashboard soll beim Öffnen frisch laden), `placeholderData` bleibt aus (Wechsel des Workspace zeigt keine Altwerte).

- [ ] **Step 3: Tests grün**

Run: `cd frontend && npx vitest run src/queries/metrics.test.ts` — Expected: PASS.

- [ ] **Step 4: MetricsDashboard umstellen**

Ersetze `useState`/`useCallback load`/`useEffect` durch `useMetricsQuery`. `metrics = query.data ?? null`, `isLoading = query.isFetching`, `error` aus `query.error`, `isStale = query.isError && query.data !== undefined` (gleiche Semantik wie `MetricsDashboard.tsx:497-500`). History: ein `useEffect` auf `query.dataUpdatedAt` hängt einen Messwert je Kachel an (Obergrenze `MAX_HISTORY`), Reset bei Wechsel von Workspace oder Typfilter. Der Refresh-Button ruft `query.refetch()`.

- [ ] **Step 5: Bestehende und neue Tests**

Run: `cd frontend && npx vitest run src/components/MetricsDashboard src/queries/metrics.test.ts`
Expected: alle PASS, die bestehenden ohne Änderung. Zusätzlich ein Test: Typfilter wechseln löscht die History.

- [ ] **Step 6: Typen, Lint, Commit** (über `git`-Agent): `refactor(metrics): load the dashboard through react-query`

---

### Task 4: S2 — Hotspot-Analyse nach Zuständigkeit

**Files:**
- Create: `frontend/scripts/analyze-component-hotspots.mjs`
- Modify: `frontend/vite.config.ts` (Zeile 36): `test.include` um `"scripts/**/*.test.mjs"` erweitern. Der heutige Wert `src/**/*.{test,spec}.{ts,tsx}` würde einen Test unter `frontend/scripts/` nicht finden (im Review festgestellt). Die Skripte liegen außerhalb des `tsc`-Programms, die Änderung beeinflusst `tsc` nicht.
- Test: `frontend/scripts/analyze-component-hotspots.test.mjs` plus Fixtures `frontend/scripts/fixtures/{cohesive,three-concerns}.tsx`
- Create (Ergebnis, wird committet): `docs/analysis/2026-11-frontend-hotspots.md`

**Interfaces:**
- Produces: `analyzeFile(path: string): { path: string; lines: number; cyclomatic: number; hooks: number; clusters: Cluster[] }` mit `Cluster = { names: string[]; kinds: ("state"|"effect"|"callback"|"memo"|"query")[]; apiCalls: string[] }`, sowie `churn(path: string, since = "6 months ago"): number` (Anzahl Commits). CLI: `node scripts/analyze-component-hotspots.mjs src/components > out.md`.

Methodik (Literatur, in das Ergebnis-Dokument als Quellenabschnitt übernehmen): Hotspot = Änderungshäufigkeit × Komplexität (Tornhill, "Your Code as a Crime Scene"). Zuständigkeitsschnitt nach Single Responsibility und dem "Large Class"-Smell (Fowler, "Refactoring"). Kohäsion als Verbindungsgraph der Deklarationen einer Komponente: zwei Deklarationen sind verbunden, wenn die eine einen Bezeichner der anderen verwendet. Zusammenhangskomponenten sind Kandidaten für eigene Hooks (die React-Docs "Reusing Logic with Custom Hooks"). Zeilenzahl ist nur Vorfilter (> 300), nie Entscheidungskriterium.

- [ ] **Step 1: Failing Tests mit Fixtures**

```js
// analyze-component-hotspots.test.mjs
test("cohesive component yields one cluster", () => {
  expect(analyzeFile("scripts/fixtures/cohesive.tsx").clusters).toHaveLength(1);
});
test("component with three unrelated state groups yields three clusters", () => {
  const r = analyzeFile("scripts/fixtures/three-concerns.tsx");
  expect(r.clusters).toHaveLength(3);
});
```
Fixture `three-concerns.tsx`: drei Gruppen (Daten laden mit `useState`+`useEffect`, Dialog-Zustand, Timer-Toast), die untereinander keine Bezeichner teilen.
Run: `cd frontend && npx vitest run scripts` — Expected: FAIL (nach der Include-Erweiterung wird die Datei gefunden, die Funktion fehlt noch).

- [ ] **Step 2: Skript implementieren**

TypeScript-Compiler-API (`typescript` ist installiert): je Komponentenfunktion Deklarationen (`useState`-Paare, `useEffect`, `useCallback`, `useMemo`, `use*Query`) sammeln, Bezeichner-Referenzen verbinden, Zusammenhangskomponenten bilden. `cyclomatic` = 1 + Anzahl `if`, `?:`, `&&`, `||`, `??`, Schleifen, `case`, `catch`. `churn` über `git log --since --format= --name-only -- <pfad>`.

- [ ] **Step 3: Tests grün**

Run: `cd frontend && npx vitest run scripts` — Expected: PASS.

- [ ] **Step 4: Gesamtlauf und Auswertung**

Run: `cd frontend && node scripts/analyze-component-hotspots.mjs src/components > ../docs/analysis/2026-11-frontend-hotspots.md`
Das Dokument enthält je Datei Zeilen, Churn, Komplexität, Cluster-Anzahl und die Cluster mit ihren Namen, sortiert nach Hotspot-Rang. Entscheidungsregel, im Dokument festgehalten: Zerlegen, wenn mindestens drei unabhängige Cluster mit eigenem Zustand existieren und die Datei im obersten Viertel des Hotspot-Rangs liegt. Alles andere bleibt, auch bei 1500 Zeilen.

- [ ] **Step 5: Daniel reviewt die Zerlegungsliste**

Die Liste der Dateien, die nach der Regel zerlegt werden, geht als Tabelle an Daniel. Jede Zeile wird Task 5.

- [ ] **Step 6: Commit** (über `git`-Agent): `docs(frontend): add component hotspot analysis by responsibility`

---

### Task 5: Zerlegung je Datei (Vorlage, eine Instanz pro Zeile der Liste aus Task 4)

**Files:**
- Modify: die Komponentendatei
- Create: je Cluster `frontend/src/components/<Bereich>/use<Cluster>.ts` (neben der Komponente, wie `components/Audit/use-finding-targets.ts`)
- Test: je neuer Hook `use<Cluster>.test.tsx`

**Interfaces:**
- Consumes: Cluster-Namen und -Grenzen aus `docs/analysis/2026-11-frontend-hotspots.md`.
- Produces: Hooks mit expliziter Signatur `use<Cluster>(inputs): { …state, …actions }`. Die Komponente behält nur Komposition und Darstellung.

- [ ] **Step 1: Charakterisierungstest zuerst**

Test, der das beobachtbare Verhalten der Zuständigkeit festnagelt, bevor sie bewegt wird (Eingabe → Aufruf der API → dargestellter Zustand, Fehlerpfad, Unmount während laufender Anfrage). Run: `cd frontend && npx vitest run src/components/<Bereich>` — Expected: PASS auf dem unveränderten Code.

- [ ] **Step 2: Cluster in Hook verschieben**

Reiner Move: Deklarationen unverändert in `use<Cluster>.ts`, Komponente ruft den Hook. Keine Umbenennung, keine Logikänderung im selben Commit.

- [ ] **Step 3: Tests grün, Typen, Lint**

Run: `cd frontend && npx vitest run src/components/<Bereich> && npx tsc --noEmit -p . && npx eslint src/components/<Bereich>`
Expected: alles PASS, bestehende Tests unverändert.

- [ ] **Step 4: Commit je Datei** (über `git`-Agent): `refactor(<bereich>): extract <cluster> hooks from <Komponente>`. Ein PR je Datei.

---

### Task 6: audit-dashboard — S2 und S3 zusammen (erster, verstandener Fall)

**Files:**
- Modify: `frontend/src/components/Audit/audit-dashboard.tsx` (1726 Zeilen)
- Create: `frontend/src/queries/audit.ts`, `frontend/src/components/Audit/use-audit-run.ts`, `use-audit-waivers.ts`
- Test: `frontend/src/components/Audit/use-audit-run.test.tsx`, `use-audit-waivers.test.tsx`, `frontend/src/queries/audit.test.ts`; bestehend `audit-dashboard.test.tsx`, `audit-filters-1262.test.tsx` bleiben unverändert grün

**Interfaces:**
- Consumes: `auditApi.run(workspaceId, options)`, `auditApi.rules()`, `auditApi.waivers(...)`, `artifactsApi.list(workspaceId)`, bestehender Hook `use-finding-targets.ts` als Vorbild.
- Produces (aus der Lektüre: die erkennbaren Zuständigkeiten in der Datei): `useScopeArtifacts(workspaceId)` (`audit-dashboard.tsx:407`), `useAuditRules()` (`:511`, Regelkatalog, Fehler nur Degradation), `useAuditRun({workspaceId, scope, scopeArtifactId, artifactTypeFilter})` (`load`, Seite 1 bei Scope-Wechsel, #596), `useAuditWaivers(workspaceId)` (`loadWaivers`). Adopt/Remediate-Workflow, Toast (`:609`) und Fokus-Verwaltung (`:621`) bleiben vorerst in der Komponente.

- [ ] **Step 1: Charakterisierungstests**

Je Zuständigkeit ein Test auf dem unveränderten Code: Scope-Wechsel während eines laufenden Audits verwirft die alte Antwort; Regelkatalog-Fehler lässt die Rule-ID als Text stehen; Waiver-Liste lädt bei Workspace-Wechsel neu.
Run: `cd frontend && npx vitest run src/components/Audit` — Expected: PASS.

- [ ] **Step 2: `queries/audit.ts` mit Hooks für Regelkatalog, Artefaktliste, Waiver**

`useAuditRulesQuery()`, `useScopeArtifactsQuery(workspaceId)`, `useAuditWaiversQuery(workspaceId)` nach dem Muster aus Task 3. Der Audit-Lauf selbst bleibt imperativ (explizit ausgelöst, Fenster 1 bei Scope-Wechsel), er wird nur in `useAuditRun` gekapselt, nicht auf `useQuery` umgestellt.

- [ ] **Step 3: Hooks extrahieren und Komponente umstellen**

- [ ] **Step 4: Tests und Prüfungen**

Run: `cd frontend && npx vitest run src/components/Audit src/queries/audit.test.ts && npx tsc --noEmit -p . && npx eslint src/components/Audit src/queries/audit.ts`
Expected: alle PASS, `audit-dashboard.tsx` merklich kürzer, Verhalten gleich.

- [ ] **Step 5: Commit** (über `git`-Agent): `refactor(audit): split the dashboard into data hooks and use react-query`

---

### Task 7: #598 abschließen

**Files:** keine.

**Interfaces:** Consumes: Tasks 3, 5 und 6 gemergt.

- [ ] **Step 1: Kommentar mit Belegtabelle und Schließen** (nach Freigabe Daniel)

Der Kommentar enthält die Befundtabelle oben (W1–W5, S4, S5 schon erledigt, mit Datei:Zeile), plus PR-Nummern für S2 und S3 und den Verweis auf `docs/analysis/2026-11-frontend-hotspots.md` für Dateien, die bewusst nicht zerlegt wurden.
```bash
gh issue close 598 --reason completed --comment "<Tabelle und PR-Nummern aus den Tasks 3, 5, 6>"
```

- [ ] **Step 2: Endstand prüfen**

Run: `gh issue view 598 --json state --jq .state`
Expected: `CLOSED`.

---

## Self-Review

- **Abdeckung:** Roadmap Phase B Stränge 1 (#598), 3 (#1094, #1287), 4 (#186) sind abgedeckt. Strang 2 (Inspector) liegt in `2026-11-10-phase-b2-inspector-concept.md`.
- **Entscheidung 5 ("Profil-API bauen")** ist gegenstandslos, weil der Endpunkt seit #1096 existiert. Im Plan als Befund festgehalten.
- **Lücke:** Task 5 hat keine feste Dateiliste, sie entsteht aus Task 4. Das ist gewollt (Daniels Vorgabe: keine harte Zeilengrenze), ist aber der Teil des Plans, der erst nach der Analyse konkret wird. Ausnahme `audit-dashboard.tsx` (Task 6), dort sind die Cluster aus der Lektüre bekannt.
- **Typkonsistenz:** `useMetricsQuery` (Task 3) und `useAuditRulesQuery` usw. (Task 6) folgen demselben Muster. `analyzeFile` und `Cluster` (Task 4) werden in Task 5 nur gelesen.
- **Nicht ausgeführt:** Kein Befehl dieses Plans lief. Die Hypothesen zu `useScopeArtifacts` & Co. stammen aus der Lektüre von `audit-dashboard.tsx:400-640`, nicht aus einem Testlauf.
