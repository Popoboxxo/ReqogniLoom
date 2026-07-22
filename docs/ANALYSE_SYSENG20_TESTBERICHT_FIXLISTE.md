# Analyse: SysEng 2.0 Testbericht — Konsolidierte Fixliste

> Status: **P0 (Sicherheit/Crashes/Workflow-Init) + P1 (MCP) + P2-REST umgesetzt, verifiziert,
> committed. P2-UI teilweise (UI-03/UI-05/UI-06 gefixt, UI-01/02 kein Fix nötig; UI-04 offen).
> P3 (SE-Prozess) noch offen.** Fix-Fortschritt live getrackt in
> `project_syseng20_testbericht_fixliste`-Memory. Konsolidiert alle Befunde aus
> `test-results/` (5 Dateien, 3 Workspace-Presets × UI-Sweep + REST API + MCP Deep Dive +
> SE-Expert-Review) in eine priorisierte, handlungsfähige Liste.
>
> Version getestet: 0.2.0-syseng20 (Commit `b6afb7e`)
> Datum: 20.07.2026
> Quelldateien: `reqflow-syseng20-ultimativer-testbericht.md`, `reqflow-syseng20-assessment.md`,
> `reqflow-standard-preset-assessment.md`, `reqflow_rest_api_bug_report.json`,
> `reqflow-mcp-deep-dive-findings.json`, `export_issues.md` (Codeberg-Issue-Export)
> Backend-Tests zum Zeitpunkt der Prüfung: 386 passed / 1 failed (ReqIF-Regression, nicht Teil
> dieser Analyse)
>
> **Hinweis Codeberg-Export (aktualisiert):** Ein vollständigerer Export unter
> `test-results/export_issues.md` wurde nachgereicht und enthält tatsächlich **#89–#120** (32
> Issues, nicht nur 4). Die ursprüngliche Fixliste unten deckt nur #117–#120 ab. Die
> zusätzlichen Befunde #89–#116 sind in "Anhang: Weitere Codeberg-Findings (#89–#116)" erfasst
> und werden schrittweise abgearbeitet.

---

## Executive Summary

| Kategorie | Anzahl | Presets betroffen |
|---|---|---|
| Sicherheitslücken (kritisch/hoch) | 5 | extended, standard, minimal (alle) |
| Crashes / 500er (kritisch) | 8 | teils presetübergreifend |
| Workflow-Blocker (kritisch) | 2 | standard, minimal |
| MCP-Tool-Bugs (kritisch/hoch) | 9 | alle |
| REST-Inkonsistenzen (mittel/niedrig) | 7 | alle |
| UI-Bugs | 6 | alle |
| Codeberg-Issues eingearbeitet | 5 gefixt (#95, #117–#120) + 19 offen (#89–#116, davon 5 Duplikate) | siehe Anhang |
| SE-Prozess-Lücken (architektonisch, kein Quick-Fix) | 8 | konzeptionell, alle |

**Kernaussage:** Die Tool-Architektur (MCP + REST, 72 Tools) ist solide, aber (1) mehrere
Sicherheitslücken sind produktionskritisch, (2) das `standard`-Preset ist durch fehlende
Workflow-Initialisierung faktisch nicht nutzbar, (3) mehrere MCP-Tools sind durch
Schema/Implementierung-Mismatches komplett unbenutzbar, (4) auf SE-Prozessebene fehlt jeder
strukturelle Zwang zur Traceability (0 Trace-Links im gesamten System).

---

## P0 — Sicherheit (sofort, vor jedem Produktiv-Deployment)

| ID | Problem | Fund-Ort | Fix | Status |
|---|---|---|---|---|
| SEC-01 | `DEBUG=True` in Prod — SECRET_KEY, DB-Passwort, API-Keys, FIELD_ENCRYPTION_KEY leaken bei jedem 500er über Django-Debug-Seite (CWE-489, CWE-200) | B005, alle Presets | `DEBUG=False` in Prod-Settings erzwingen | ✅ Gefixt (`8e0bb5f5`) |
| SEC-02 | Permission Enforcement = `shadow` — RBAC wird geloggt, aber nicht durchgesetzt. Jeder Token kann alles | SEC002, alle Presets | `enforcement_mode` auf `authoritative` umstellen (laut Report: "keine unreviewed mismatches — safe to flip") | ✅ Gefixt (`9a96d3bd`) |
| SEC-03 | XSS/SQLi-Payloads werden ungefiltert gespeichert und zurückgegeben (`<script>` in title) | B006, extended | Input-Sanitization (strip_tags/HTML-Escape) auf allen Freitextfeldern | ✅ Gefixt (`fba87186`, alle Freitext-Serializer) |
| SEC-04 | API-Key-Auth via Query-Parameter (`?api_key=`) laut Swagger-Doku unterstützt, liefert aber 403 | SEC001, extended | Query-Param-Auth implementieren oder aus Doku entfernen | ⚪ Kein Fix nötig — geprüft: OpenAPI-Schema enthält kein Query-Param-Scheme, 403 ist korrektes Verhalten (Query-Param-Auth wäre Sicherheitsregression, API-Keys würden in Access-Logs leaken) |
| SEC-05 | MCP Bootstrap-Deadlock: API-Key-User ist kein Workspace-Mitglied → keine Schreiboperation via MCP möglich. `user.assign_role` selbst erfordert Write → kein Ausweg | M-M01 (minimal), M03 (extended, `user.assign_role`) | Seed/Bootstrap-Prozess muss API-Key-User automatisch Workspace-Rolle zuweisen, oder ein Admin-Bootstrap-Tool ohne Write-Gate schaffen | ✅ Gefixt (`5eb28a2e`, `a6f90e0d`; 3 Fix-Ebenen inkl. `_is_bootstrap_candidate`-Gate im Dispatcher) |
| SEC-06 | Nicht in der Codeberg-Liste — nachträglich im Gesamttestlauf erfasst. 3 Tests in `test_mcp_api_key_roles.py::TestMcpApiKeyRolePropagation` rot: `active_roles=[]` bei API-Key-Auth, Schreiboperation → `-32001 Role '()' does not permit write operations` (identisches Fehlerbild wie SEC-05). **Verdacht auf Regression durch `9a96d3bd` (Enforcement-Flip) widerlegt.** | Gesamttestlauf 2026-07-22, Live-Stack | **Keine Regression, kein Produktionscode-Bug.** Root-Cause: fragiler Test. Die `seeded_workspace_id`-Fixture nahm blind `workspaces[0]`; die List-API sortiert `-modified_at`, wodurch ein manuell erstellter Workspace ("Neur test", gleicher Tenant, keine Admin-Rolle) vor die geseedete "Demo Workspace" rutschte → `active_roles=[]` ist dort **faktisch korrekt**. Der MCP-Pfad (`active_roles_for` + hartkodierte `_RBAC_MATRIX`) berührt `GlobalPermissionDefinition` (Ziel des Flips) gar nicht. Fixture ankert jetzt am kanonischen `DEFAULT_WORKSPACE_NAME` ("Demo Workspace"). | ✅ Gefixt (Testkorrektur; 8/8 grün) |
| SEC-07 | Sporadische `403` auf `GET /api/v1/auth/me/` (beobachtet in 178 von 359 Aufrufen im Gesamttestlauf). Verdacht: Race Condition in `AuthTenancyAuthentication.authenticate()` (`backend/auth_tenancy/rest.py:105`) — Tenant-Context-Aktivierung (`self._tenancy.activate(tenant_context)`) und Rollen-Auflösung laufen thread-local, möglicherweise ohne saubere Isolation zwischen parallelen Requests auf demselben Worker-Thread. Zeitlich nach dem Enforcement-Flip (`9a96d3bd`) aufgefallen, Kausalität noch nicht belegt. | Gesamttestlauf 2026-07-22, Live-Stack | Reproduktion unter Last (parallele Requests auf `/auth/me/`) nötig, dann Thread-Local-Lifecycle in `authenticate()` / `TenantContextService` prüfen | 🔲 Offen — noch nicht reproduziert/verifiziert |

---

## P0 — Crashes / 500er

| ID | Endpoint | Problem | Presets | Fix | Status |
|---|---|---|---|---|---|
| CR-01 | `DELETE /api/v1/workspaces/{id}/` | `NotImplementedError` (500), `destroy()` nicht implementiert (`rest_api/views.py:207`) | extended | `destroy()`-Methode implementieren → 204 oder sauberes 405 | ✅ Gefixt (`e7a6acaa`) |
| CR-02 | `POST /api/v1/diagrams/` (`type=block`, ohne `nodes`) | 500 statt 400 Validation Error | extended (B002), standard (S04) | Validierung vor Persistenz, sauberer 400 | ✅ Gefixt (`dcce2ad6`) |
| CR-03 | `POST /api/v1/requirements` (ohne Trailing Slash) | Django `RuntimeError` (APPEND_SLASH kann POST nicht redirecten) → 500 + Settings-Leak | **alle Presets**, seit v0.1.0 ungefixt (B003, S06, bestätigt in minimal) | `APPEND_SLASH=False` für API-Routen ODER 301-Redirect vor POST-Body-Verlust abfangen | ✅ Gefixt (`bed42e54`) |
| CR-04 | `PATCH /api/v1/glossary/{id}/` | `'AuthContext' object has no attribute 'actor_id'` (500) | **alle Presets**, seit v0.1.0 ungefixt (B004, S02, M-R01) | `actor_id`-Attribut auf `AuthContext` ergänzen oder Aufrufstelle korrigieren | ✅ Gefixt (`6ac2ab17`) |
| CR-05 | `POST /api/v1/diagrams/` (`type=mermaid`) | Standard-Preset: 500 JSON-Parse-Error. Extended-Preset: funktioniert (201) | standard (S03) — inkonsistent zu extended | Ursache der Preset-Abhängigkeit klären, vereinheitlichen | ✅ Kein eigener Bug — gleiche Root Cause wie CR-02, dort mitgefixt. Regressionstests ergänzt (`471f0e72`) |
| CR-06 | `POST /api/v1/needs/` (flache URL, nicht nested) | 404 — Need-Erstellung nur über nested URL möglich | standard (S05) | Flache Route registrieren oder Doku klarstellen, dass nur nested erlaubt ist | ✅ Gefixt (`a6f90e0d`) |
| CR-07 | `POST /api/v1/needs/` | "Workspace None not found" — Need-Erstellung im minimal-Preset komplett broken | minimal (M-R02) | Root-Cause in Workspace-Resolution bei minimal-Preset prüfen | ✅ Identische Root Cause wie CR-06 (mitgefixt), Regressionstest (`bc4e36de`) |
| CR-08 | `PATCH /api/v1/requirements/{id}/`, `/testcases/{id}/`, `/issues/{id}/` | Status-Change wird **silently ignored** — HTTP 200, Version-Bump, aber Wert unverändert (Datenintegrität!) | minimal (M-R03/04/05) | Silent-Ignore ist am kritischsten aller Bugs: User denkt Status wurde geändert, wurde er aber nicht. Fix vor Workflow-Init (siehe P0 Workflow), da vermutlich gleiche Ursache | ✅ Bereits vorher gelöst durch REQ-165/166/167 Workflow-Engine. Doku-Lücke (`TestCaseSerializer.status` read_only) geschlossen (`5929da35`) |

---

## P0 — Workflow-Initialisierung (macht Presets unbenutzbar)

| ID | Problem | Presets | Fix | Status |
|---|---|---|---|---|
| WF-01 | **7 von 12 Item-Types** (Requirement, Issue, Adr, Risk, Need, TestCase, TestRun) haben `states=[]` und `allowed_transitions=[]` im `standard`-Preset. Nur ArchitectureElement, StakeholderNeed, GlossaryTerm, Icd, ChangeRequest sind korrekt initialisiert. `initialized: false`. Anforderungen bleiben **permanent in "draft"** stecken | standard (M-S01, S01, Standard-Assessment §1) | `POST /api/v1/workflow-defaults/{ItemType}/standard/initialize/` für alle 7 fehlenden Types ausführen bzw. Default-Seed-Migration ergänzen. Ziel: `draft → approved → deprecated` mit funktionierenden Transitions | ✅ Bereits vorher gelöst durch REQ-165/166/167 "Universal Configurable Workflow Engine" — kein Code-Fix in dieser Session nötig |
| WF-02 | Requirement/minimal-Preset ebenfalls `states=[]` (erwartet: `draft→done`) | minimal (M-M02) | Gleicher Fix wie WF-01, für minimal-Preset | ✅ Bereits vorher gelöst (gleiche Ursache wie WF-01) |

**Hinweis:** WF-01/02 sind vermutlich die Root-Cause für CR-08 (Status-Change wird ignoriert,
weil keine gültigen Transitionen definiert sind, statt einen Fehler zu werfen).

---

## P1 — MCP-Tool-Bugs (Tool komplett unbenutzbar)

| ID | Tool | Problem | Presets | Fix | Status |
|---|---|---|---|---|---|
| MCP-01 | `issue.create` | `TypeError` — datetime nicht JSON-serialisierbar. Nur MCP betroffen, REST funktioniert | alle, seit v0.1.0 ungefixt (M01, M-M03) | `_to_dict()` um `datetime`/`date`-Handling erweitern (siehe auch `docs/ANALYSE_MCP_LIVE_TEST_BUGS.md` §1 — identischer Root-Cause bei ADR/Risk) | ✅ Gefixt (`backend/mcp_server/tools/generic.py`, `_to_dict` konvertiert jetzt auch datetime/date) |
| MCP-02 | `workspace.reactivate` | Handler nicht registriert (MCP) / REST lehnt `op='workspace.reactivate'` als ungültige Choice ab | alle (M02, M-S02, json-Finding) | Op-Choice in REST-Enum ergänzen + MCP-Handler registrieren | ⚪ Kein Fix nötig — bereits vorher vollständig implementiert (Handler + REST-Action), verifiziert via Test-Suite |
| MCP-03 | `requirement.decompose` | Schema deklariert Parameter `id`, Backend erwartet `requirement_id` | alle (M04, M-S05, M-M04) | Schema-Parameter-Name an Backend angleichen (oder Backend akzeptiert beide) | ✅ Gefixt (`backend/mcp_server/tools/requirements.py`, Schema korrigiert) |
| MCP-04 | `requirement.derive` | Schema deklariert `id`, Backend erwartet `parent_requirement_id` + weitere Pflichtparameter | alle (M05, M-S06) | Wie MCP-03 | ✅ Gefixt (gleiche Datei wie MCP-03) |
| MCP-05 | `needs.get_traces` | `AttributeError: 'TraceLinkService' object has no attribute 'list_incoming'` | alle (M06, M-S04, json-Finding, **Codeberg #117**) | Methode `list_incoming` in `TraceLinkService` implementieren | ✅ Gefixt (`backend/application/trace_link_service.py`, `list_incoming`/`list_outgoing` + `TraceEdgeDTO` ergänzt) — Codeberg #117 geschlossen |
| MCP-06 | `issue.read` | JSON-RPC-Response hat `id: null` statt der Request-ID — Request-ID-Propagation kaputt | standard (json-Finding, HIGH) | Request-ID korrekt durchreichen in MCP-Handler | ⚪ Kein Fix nötig — `protocol_handler.py` propagiert Request-ID bereits korrekt, verifiziert (29/29 Tests grün) |
| MCP-07 | `audit.query` | Permission Denied — API-Key-User hat `active_roles: []`, Admin-Rolle fehlt | standard (M-S07, json-Finding) | Hängt an SEC-05 (Bootstrap-Deadlock) — gleiche Fix-Richtung | ⚪ Kein Fix nötig — bereits durch vorbestehenden REQ-127-Fix gelöst, per Live-curl verifiziert |
| MCP-08 | `adr.*`, `risk.*` (8 Tools) | Über MCP nicht implementiert, obwohl REST-CRUD für ADR/Risk funktioniert | extended (M07-M08) | MCP-ToolGroup für ADR/Risk analog zu bestehenden CRUD-Groups ergänzen | ⚪ Kein Fix nötig — bereits vorher als `GenericCrudToolGroup` registriert |
| MCP-09 | `permissions.*`-Schema | Unvollständige Parameter-Definitionen | extended (M10-M12) | Schema-Review gegen tatsächliche Handler-Signaturen | ⚪ Kein Fix nötig — alle 4 Schemas matchen Handler exakt, verifiziert |

**Kleinere MCP-Findings (nicht blockierend):**
- `requirement.update`-Schema listet `status` als schreibbares Feld, wird aber silent ignoriert → als `readOnly` markieren oder entfernen (json, MEDIUM)
- `test.run_get` mit ungültiger UUID → sauberer Fehler, kein Bug (LOW, informativ)
- `artifact.get_tree` mit Workspace-UUID als `root_id` → unklare Fehlermeldung (LOW)
- `admin.backup_create`/`backup_list` → `Permission denied: /backups` im Container (M09, LOW — Infrastruktur/Docker-Volume-Rechte)
- M13-M16, M-S08–M-S20, M-M08 → diverse kleinere Inkonsistenzen, siehe Rohdaten in `test-results/`

---

## P2 — REST-API-Inkonsistenzen

| ID | Problem | Presets | Fix | Status |
|---|---|---|---|---|
| REST-01 | Feldnamen inkonsistent: `name` (Test-Runs) vs. `title` (Requirements etc.) vs. `term` (Glossary) | alle (B007, S09) | Feldkonvention vereinheitlichen oder zumindest in OpenAPI-Schema klar dokumentieren | ✅ Dokumentiert (`cb90136f`) — bewusst nicht umbenannt (Breaking Change für bestehende Clients), stattdessen `help_text` auf `TestRunSerializer.name`/`GlossaryTermSerializer.term` ergänzt, das die Äquivalenz zu `title` erklärt (erscheint im OpenAPI-Schema) |
| REST-02 | `change_reason`-Pflicht inkonsistent: bei Needs/Glossary Pflicht, bei Requirements/Issues/Testcases optional — ohne dass die Fehlermeldung auf das fehlende Feld hinweist | extended (B008) | Entweder einheitliches Verhalten je Preset ODER Fehlermeldung verbessern (Feldname nennen) | ⚪ Kein Fix nötig — geprüft: Pflicht ist bereits einheitlich **preset-gesteuert** (`PresetPolicyService.is_change_reason_required`, nicht ad-hoc pro Entity-Typ), und alle Fehlermeldungen nennen `change_reason` bereits explizit im Text (`"change_reason is required by preset policy"` u.ä., vorbestehend) |
| REST-03 | `GET /api/v1/search/` ohne `workspace_id` → leise leeres Ergebnis statt 400 | alle (B009) | 400 mit `"workspace_id is required"` analog zu `/users/me/preferences/` | ✅ Gefixt (`cb90136f`), Regressionstest `test_search_views.py` |
| REST-04 | `PUT` auf Collection-Endpoints → 405, nirgends dokumentiert | alle (B010) | In OpenAPI-Doku als "nicht unterstützt" markieren oder implementieren | ⚪ Kein Fix nötig — Standard-DRF-Router-Verhalten: `PUT` wird für Collection-Routen (ohne `pk`) nie registriert, daher taucht es im generierten OpenAPI-Schema für diese Routen korrekt gar nicht erst auf. 405 ist somit kein Doku-Defizit, sondern erwartetes Framework-Verhalten |
| REST-05 | `POST /api/v1/diagrams/` — Preset-abhängiges Verhalten bei `mermaid`-Type (siehe CR-05) | standard | siehe CR-05 | ✅ Kein eigener Bug — siehe CR-05, dort mitgefixt |
| REST-06 | `POST /api/v1/issues/` — `status`-Feld ist case-sensitive: `'Open'` wird akzeptiert (201), `'open'` abgelehnt (400) ohne Liste gültiger Choices in der Fehlermeldung | alle (**Codeberg #119**) | Case-insensitive Normalisierung beim Speichern ODER Fehlermeldung mit gültigen Choices anreichern | ⚪ Kein Fix nötig — bereits vorher gelöst (`ad658662`, REQ-148, vor dieser Session): `IssueSerializer.status` ist ein `NormalizedChoiceField` mit case-insensitiver Normalisierung und einer Fehlermeldung, die alle gültigen Choices auflistet — Codeberg #119 geschlossen |
| REST-07 | `GET /api/v1/test-runs/{id}/` erfordert `?workspace_id=` als Query-Param, im Gegensatz zu allen anderen Detail-Endpoints (die die Workspace über den Auth-Kontext auflösen) | alle (**Codeberg #120**) | Workspace-Resolution für Test-Runs-Detail-Endpoint an übrige Detail-Endpoints angleichen | ⚪ Kein Fix nötig — geprüft: `TestRunService.get_test_run` löst den Test-Run bereits rein über `pk` im tenant-gescopten Queryset auf, kein `workspace_id`-Query-Param wird gelesen oder verlangt. Regressionstest `test_test_run_detail_view.py` (`cb90136f`) — Codeberg #120 geschlossen |

---

## P2 — UI-Bugs

| ID | Problem | Presets | Fix | Status |
|---|---|---|---|---|
| UI-01 | "Impact Analysis" Sidebar-Link → Redirect zu Dashboard (toter Link) | alle | Route/Component-Wiring prüfen | ⚪ Kein Fix nötig — live im Browser verifiziert: Route/Link ist korrekt verdrahtet, nicht reproduzierbar |
| UI-02 | "SE-Auditor" Seite → Redirect zu Dashboard, Frontend nicht verdrahtet | standard+ (neues Feature aus SysEng 2.0) | Frontend-Route für SE-Auditor implementieren/verlinken | ⚪ Kein Fix nötig — live im Browser verifiziert: Route ist verdrahtet, nicht reproduzierbar |
| UI-03 | ADRs/Risks/Issues-Seiten laden Daten, aber kein `<h2>`/`<h3>` Heading | extended (**Codeberg #101**, nennt explizit ADR/Issues/Risks) | Heading-Komponente ergänzen (auch Accessibility-relevant) | ✅ Gefixt (`4d730a9c`) — `<h3>` mit i18n-Key (`nav.adrs`/`nav.risks`/`nav.issues`) in `AdrList.tsx`, `RiskList.tsx`, `IssueList.tsx` ergänzt, UI-03-Fix in `AdrList`/`RiskList` live im Browser verifiziert — Codeberg #101 geschlossen |
| UI-04 | SPA verliert Auth-Session nach ca. 5 Navigationen | alle | Token-Refresh/Session-Handling im Frontend debuggen | 🔲 Offen — **eine** Hypothese widerlegt, Live-Verifikation ausstehend. Geprüft wurde die Vermutung, `AuthContext.tsx` löse denselben Render-Loop aus wie der Frontend-Test-Hang (siehe DX-01). Ergebnis: **kein gemeinsamer Root-Cause.** `AuthProvider` ist genau einmal an der App-Wurzel gemountet (`App.tsx:34`, innerhalb `BrowserRouter`); React-Router-Navigation remountet ihn nicht, der Restore-Effekt (`GET /auth/me/`, `AuthContext.tsx:121-136`) läuft daher nur beim initialen Mount, nicht pro Navigation. Beide Effekt-Dependencies (`applyIdentity`, `clearAuth`) sind `useCallback([])` → referenziell stabil; der `cancelled`-Guard ist korrekt. Es existiert dort kein Render-Loop. Der Session-Verlust nach ~5 Navigationen ist damit statisch im Frontend nicht reproduzierbar und deutet auf Backend-/Cookie-Verhalten hin (httpOnly-Cookie-Ablauf/Rotation, CSRF-Token-Rotation oder ein 401 aus einem der Requests, das `_onUnauthorized` → `clearAuth` + Redirect auslöst — `client.ts:107`). Nächster Schritt: Live-Reproduktion mit Network-/Cookie-Inspektion über 5+ Navigationen. |
| UI-05 | Stale-Ref-Navigation — Ref-IDs ändern sich zwischen Snapshots | alle | Ursache in State-Management/Caching prüfen | ✅ Gefixt (`7329ddd7`) — Root Cause: `fallbackRef()` in `frontend/src/api/artifactRefs.ts` routete bei Lookup-Fehlschlag oder unbekanntem `artifact_type` immer hart auf `/requirements/{id}`, egal welcher Artefakt-Typ tatsächlich gemeint war — das erzeugte den Eindruck "wechselnder" Ref-IDs, je nachdem ob der Lookup erfolgreich war oder nicht. Fix: `fallbackRef` liefert jetzt `route: ""` ("nicht auflösbar") statt einer geratenen Requirement-Route. `TraceLinkPanel.tsx` behandelte einen leeren Route-String bereits korrekt (Plain-Text statt Link). `TraceabilityPanel.tsx`s `LinkItem` nutzte dagegen `route ?? "/requirements/{id}"` — das `??` griff bei leerem String `""` nicht (nur bei `null`/`undefined`), daher zusätzlich dort den Navigations-Button bei fehlender Route auf `disabled` gesetzt (neuer i18n-Key `traceability.unresolved` als Tooltip). Tests: `frontend/src/api/artifactRefs.test.ts` (neu), `TraceabilityPanel.test.tsx` (Testfall ergänzt) |
| UI-06 | Dashboard-Card zeigt aktiven SE-Mode (z.B. "extended SE Mode") an, bietet aber keinen direkten Wechsel — nur über Settings-Seite erreichbar | alle (**Codeberg #118**) | Mode-Switcher direkt auf der Dashboard-Card ergänzen oder Card mit Link zu Settings versehen | ✅ Gefixt (`ffc6f4b6`), live verifiziert: Preset-Badge ist jetzt Button, navigiert zu `/settings` mit korrektem Workspace-Kontext — Codeberg #118 geschlossen |

---

## P2 — Test-Infra / Developer-Experience

| ID | Problem | Presets | Fix | Status |
|---|---|---|---|---|
| DX-01 | Frontend-Test-Suite (`npm test` / Vitest) hängt reproduzierbar (Busy-Hang, CPU 150–200%, kein neuer Output für 10+ min, kein Deadlock). Der Lauf schien an wechselnden Stellen zu hängen (u.a. nach `create-trace-link-dialog.test.tsx > "renders dialog when isOpen=true"`), begleitet von endlosen `act(...)`-Warnings für `CreateTraceLinkDialog` und `AuthProvider`. | alle (Dev/CI) | Root-Cause im Render-Loop von `CreateTraceLinkDialog` beheben | ✅ Gefixt — **Root Cause:** Infinite-Re-Render-Loop in `create-trace-link-dialog.tsx`. Der Test-Mock von `react-i18next` liefert bei **jedem** Render ein neues `t` (das echte react-i18next liefert eine referenziell stabile `t`). `loadElements` (`useCallback`, deps `[workspaceId, t]`) bekam dadurch pro Render eine neue Identität; der Öffnen/Reset-Effekt (deps enthielten `loadElements`) rief `loadElements()` → `setIsLoadingElements(true)` → Re-Render → neues `t` → neues `loadElements` → Effekt erneut … synchrone Endlosschleife, die die Node-Event-Loop aushungert (deshalb greifen Vitest-Timeouts nicht). Der Hang war auf **diese eine Datei** begrenzt; da Vitest Dateien parallel in Workern abarbeitet, wirkte er nur scheinbar "wandernd". **Fix:** `t` wird in `CreateTraceLinkDialog` über eine `useRef` gelesen (`tRef.current`), sodass `loadElements` referenziell stabil ist (deps `[workspaceId]`) — robust auch bei echtem Sprachwechsel bei offenem Dialog. Zusätzlich zwei synchrone Tests auf `await waitFor(...)` umgestellt, damit der asynchrone Element-Load innerhalb `act()` settlet. **Nachweis:** isolierter Lauf `create-trace-link-dialog.test.tsx` grün (19/19, 2.5 s statt Hang), **0** `act()`-Warnings; Gesamt-Suite läuft wieder durch (14,4 s, kein Hang). **Kein** gemeinsamer Root-Cause mit UI-04 (dort widerlegt, siehe UI-04). |
| DX-02 | `e2e/tests/toothbrush-syseng.spec.ts:11` ruft `execSync('docker-compose exec -T backend python seed_toothbrush.py', { encoding: 'utf-8' })` ohne `timeout`-Option auf — ein hängender Seed-Prozess (Container down, DB-Lock etc.) blockiert den Node-Event-Loop unbegrenzt statt mit klarem Fehler abzubrechen | e2e (Dev/CI) | `timeout`-Option (z.B. 30000ms) auf dem `execSync`-Aufruf ergänzen, Fehler sauber propagieren | 🔲 Offen |
| DX-03 | `CLAUDE.md:45` dokumentiert `e2e/ (111 Tests)` — tatsächlich enthält `e2e/tests/` aktuell 204 `test(...)`-Fälle über 43 Spec-Dateien. Zahl ist seit mind. einer agent-meta-Regeneration veraltet | Doku | Zahl in `CLAUDE.md` auf den tatsächlichen Stand aktualisieren (regelmäßig bei agent-meta-Sync erneut prüfen) | 🔲 Offen |

---

## P3 — SE-Prozess-Lücken (architektonische Entscheidungen, kein Quick-Fix)

Diese Punkte sind keine Bugs im klassischen Sinn, sondern fehlende SE-Prozess-Durchsetzung.
Die SE-Expert-Bewertung vergibt dafür Note **5- (mangelhaft)**. Erfordern Produktentscheidung,
nicht nur Code-Fix.

| ID | Befund | Norm-Bezug | Empfohlener Fix |
|---|---|---|---|
| SE-01 | **0 Trace-Links im gesamten System** bei >80 erwarteten (Need→Req, Req→Arch, Req→Test, Arch→Req) | ISO 15288 §6.4.4 | Trace-Link-Zwang beim Erstellen einführen (z.B. Pflichtfeld `parent_need_id` bei Requirements) — laut Assessment das wichtigste Fix (**Top-1-Empfehlung**) |
| SE-02 | Kein `acceptance_criteria`-Feld im Requirement-Schema | IEEE 29148 §5.2.7 | Feld ergänzen + Audit-Regel `REQ-AC-001` |
| SE-03 | `uid`-Feld existiert im Schema, ist aber überall `null` — kein Export/ReqIF möglich | IEEE 29148 §5.2.6 | Auto-Generierung nach Schema `{WS-Prefix}-{TYPE}-{NUMBER:04d}` |
| SE-04 | `verification_method`-Feld existiert, wird nie befüllt/validiert | IEEE 29148 §5.3 | Pflichtfeld bei Statuswechsel `approved`, oder Audit-Regel `REQ-VERIF-001` |
| SE-05 | Architektur-Hierarchie löchrig: Top-System "Kindernzimmer" hat keine Kinder, obwohl 5 Subsysteme existieren; `parent_id`-Kette nur in sinnloser Test-Kette | ISO 42010 | Validator, der `parent_id`-Konsistenz beim Anlegen erzwingt |
| SE-06 | Keine Architektursichten (Context/Logical/Physical/Behavioral) — nur ein Hierarchiebaum | ISO 42010 | Sichten-Konzept einführen (mind. Kontext- und logische Sicht) |
| SE-07 | `traceability.suggest_links` / `audit.ai_review` laufen nur mit `mock`-Provider — reiner Keyword-Overlap, fachlich nicht belastbar | — | Echten LLM-Provider als Default für produktive Nutzung vorsehen; Mock klar als Demo-Mode kennzeichnen |
| SE-08 | Fehlende Audit-Regeln: `REQ-ATOM-001` (Atomaritätsprüfung), `REQ-UID-001`, `TRACE-CYCL-001` (zirkuläre Links), `TRACE-SUSPECT-001` (Suspect-Links bei Änderung) | IEEE 29148 / ISO 15288 | Regeln im RuleEngine ergänzen |

**Zusatzbefund (nicht-atomar):** 5 von 25 Requirements im Demo-Workspace (20%) verstoßen gegen
das Atomaritätsgebot (IEEE 29148 §5.2.4) — Beispiele: "Sicherheit und Kindersicherung" (3
Einzelforderungen), "Gesundes Raumklima" (4 Aspekte). Manuell strukturierte Sub-Requirements
(S-01, K-01 etc.) sind dagegen korrekt atomar — zeigt, dass das Problem in der
KI-Decomposition liegt, nicht im Datenmodell.

---

## Positdruck: Was in SysEng 2.0 bereits funktioniert

- 72 MCP Tools (vorher 67), keine Duplikate in `tools/list`
- 386 Backend-Tests grün (+45 neue)
- API-Key-Fehler korrekt 400 statt 200
- `active_roles=['admin']` korrekt für JWT-Auth (nicht für API-Key, siehe SEC-05)
- Draft-Staging (`architecture.decompose` → `decompose_commit`) — Transaktions-Semantik
  korrekt (alles-oder-nichts), entspricht V-Modell-XT-Ansatz
- Auth-Matrix korrekt: no-auth=403, invalid-token=401, valid=200
- Preset-Pattern "gleiches Datenmodell, unterschiedliche Workflow-Strenge" — architektonisch
  vorbildlich, sofern WF-01/WF-02 gefixt sind

---

## Empfohlene Bearbeitungsreihenfolge

1. ✅ **P0 Sicherheit** (SEC-01 bis SEC-05) — erledigt (`8e0bb5f5`, `9a96d3bd`, `fba87186`,
   `5eb28a2e`, `a6f90e0d`; SEC-04 kein Fix nötig)
2. ✅ **P0 Crashes** (CR-01 bis CR-08) — erledigt (`e7a6acaa`, `dcce2ad6`, `bed42e54`,
   `6ac2ab17`, `471f0e72`, `a6f90e0d`, `bc4e36de`, `5929da35`)
3. ✅ **P0 Workflow-Init** (WF-01, WF-02) — bereits durch REQ-165/166/167 gelöst, kein Code-Fix
   nötig
4. ✅ **P1 MCP-Schema-Mismatches** (MCP-03, MCP-04) — erledigt
5. ✅ **P1 restliche MCP-Bugs** (MCP-01, MCP-02, MCP-05, MCP-06, MCP-07, MCP-08, MCP-09) —
   erledigt bzw. bereits vorher gelöst
6. ✅ **P2 REST** (REST-01 bis REST-07) — erledigt (`cb90136f`; REST-02/04/05/06/07 kein Fix
   nötig, jeweils geprüft/verifiziert)
7. **P2 UI** — UI-01/UI-02 verifiziert (kein Fix nötig), UI-06 erledigt (`ffc6f4b6`), UI-03
   erledigt (`4d730a9c`), UI-05 erledigt (siehe oben); UI-04 noch offen
8. **P3 SE-Prozess** — eigene Produktentscheidung/eigenes Ticket, kein Sprint-Nebenbei-Fix

**Detaillierter Fix-Fortschritt (Commits, Root-Cause-Analysen, Verifikation je Item):** siehe
`project_syseng20_testbericht_fixliste`-Memory (nicht Teil dieses Docs, um die Analyse
kompakt zu halten).

---

## Referenz: Rohdaten

| Datei | Inhalt |
|---|---|
| `test-results/reqflow-syseng20-ultimativer-testbericht.md` | Gesamtübersicht, 3 Presets, UI-Sweep-Tabellen |
| `test-results/reqflow-syseng20-assessment.md` | SE-Expert-Prüfung extended-Workspace gegen ISO 15288/42010, IEEE 29148 |
| `test-results/reqflow-standard-preset-assessment.md` | Workflow-Analyse standard-Preset, Audit-Findings, suggest_links-Qualität |
| `test-results/reqflow_rest_api_bug_report.json` | 62 REST-Tests, strukturiert, extended-Workspace (B001-B010, SEC001-002) |
| `test-results/reqflow-mcp-deep-dive-findings.json` | 20 MCP-Findings, strukturiert, standard-Workspace |
| `test-results/export_issues.md` | Codeberg-Issue-Export, vollständig: #89–#120 (32 Issues) |

---

## Anhang: Codeberg-Issue-Tracking

Issue-Tracker: `https://codeberg.org/dduchrow/ai-native-reqflow-POC/issues` (Titel-Tag `[QA][SEVERITY]`)

| Codeberg-# | Titel | Severity | Fixliste-ID | Status |
|---|---|---|---|---|
| #117 | needs.get_traces crashed - list_incoming Methode fehlt | MEDIUM | MCP-05 | ✅ Gefixt (siehe MCP-05 oben) — geschlossen |
| #118 | Dashboard-Card zeigt 'extended SE Mode' - kein Wechsel moeglich | MEDIUM | UI-06 | ✅ Gefixt (siehe UI-06 oben, `ffc6f4b6`) — geschlossen |
| #119 | Issue-Status ist case-sensitive | MEDIUM | REST-06 | ✅ Bereits vorher gelöst (siehe REST-06 oben, `ad658662`) — geschlossen |
| #120 | test-runs Detail-Endpunkt braucht workspace_id als Query-Param | MEDIUM | REST-07 | ✅ Bereits korrekt implementiert (siehe REST-07 oben, `cb90136f`) — geschlossen |
| #95 | MCP akzeptiert ungültige workspace_id klaglos — immer 200 statt 404/400 | MEDIUM | siehe Anhang unten | ✅ Gefixt (`363affaa`) — Codeberg-Schließung ausstehend (PAT nicht verfügbar) |

---

## Anhang: Weitere Codeberg-Findings (#89–#116, nachträglich erfasst)

Vollständiger Export (`test-results/export_issues.md`) enthält #89–#120. Oben bereits erfasst:
#117–#120. #101 ist jetzt oben unter UI-03 mitgefixt. Verbleibende neue Funde:

**Bereits abgedeckt / Duplikate (kein neuer Fix nötig):**

| Codeberg-# | Titel | Duplikat von | Anmerkung |
|---|---|---|---|
| #97 | `requirement.derive` Schema sagt `id`, Server braucht 3 Parameter | MCP-04 | bereits gefixt |
| #102 | Workflow Defaults: 0 States für 5/7 Entity-Types (standard) | WF-01 | bereits gelöst (REQ-165/166/167) |
| #107 | `requirement.decompose` Schema sagt `id`, Server braucht `requirement_id` | MCP-03 | bereits gefixt |
| #109 | `needs.update` crashte früher mit `AuthContext`-Bug | — | rein historisch, Issue selbst dokumentiert "bereits gefixt" |
| #114 | Trace Links: 0 Verbindungen im Workspace | SE-01 | P3, architektonische Entscheidung, kein Quick-Fix |

**Neue, noch offene Funde (Status wird schrittweise nachgetragen):**

| Codeberg-# | Titel | Severity | Kategorie | Status |
|---|---|---|---|---|
| #89 | `tenant_id` vs. `workspace_id` — Doku-Verwirrung im Login-Response | MEDIUM | API/Doku | ✅ Gefixt (`f0eb8f3`) — verifiziert in `backend/rest_api/auth_views.py`: das Response-Feld ist tatsächlich `tenant_id` (RLS-Isolationsgrenze), nicht `workspace_id` (CRUD-Scope innerhalb eines Tenants) — zwei echte, unterschiedliche Konzepte, keine Naming-Inkonsistenz. `LoginView`-Docstring und Inline-Kommentar am Response-Dict ergänzt, README an zwei Stellen klargestellt (Verweis auf `GET /api/v1/workspaces/` zur Ermittlung der `workspace_id`). Kein Verhaltens-Fix, nur Doku |
| #90 | "Optional-Artefakte"-Switch in Sidebar ohne Wirkung | MEDIUM | Frontend | ⚪ Kein Bug — Preset-Kontext-Artefakt: verifiziert in `WorkspaceContext.tsx:285-379` (`isFeatureVisible`) und `PRESET_VISIBILITY` (`frontend/src/types/index.ts:414-432`). Die vom Switch gesteuerten `OPTIONAL_FEATURES` (`adr`, `risk`, `issue`, `diagrams`, `icds`, `metrics`) sind im **minimal**-Preset bereits per Preset-Default auf `false` gesetzt — der Switch hat dort naturgemäß keine sichtbare Wirkung, weil es nichts mehr zu verstecken gibt. In `standard`/`extended` sind dieselben Features per Default `true`, dort schaltet der Switch sie sichtbar aus/ein (Code-Pfad `isFeatureVisible`: `isOptional && hideAllOptional → false`). Vermutlich wurde der Bug-Report im minimal-Preset-Kontext erstellt. Kein Code-Fix nötig |
| #91 | Kein `GET /api/v1/api-keys/{id}/` Detail-Endpoint | MEDIUM | REST | ⚪ Bereits gefixt vor dieser Session (`6bf4d3d4 fix(REQ-134): add retrieve action to ApiKeyViewSet`, bestätigt als Ancestor von HEAD) — `ApiKeyViewSet.retrieve()` (`backend/rest_api/api_key_views.py`) ist vollständig implementiert (401/404-Handling, Ownership-Scoping über `list_api_keys(user_id=...)`), Tests in `test_api_key_rest.py` (`test_retrieve_returns_key_metadata` u.a.) vorhanden und grün. Kein neuer Fix nötig |
| #92 | Dashboard-Daten stale nach Schreiboperation (kein Re-Fetch) | MEDIUM | Frontend | ⚪ Bereits behoben / kein Bug gefunden — verifiziert in `frontend/src/queries/requirements.ts:81-127`: `useCreateRequirement`/`useUpdateRequirement`/`useDeleteRequirement` invalidieren nach `onSuccess` bereits korrekt `requirementKeys.list(workspace_id)`. `useDashboardData` (`useDashboardData.ts:47-53`) verwendet exakt denselben Query-Key (`requirementKeys.list(ws.id)`) über `useQueries`, re-fetcht also automatisch bei jeder Requirement-Mutation. Regressionstest existiert bereits: `useDashboardData.test.tsx` ("re-fetches counts when requirementKeys.list cache is invalidated"). Kein Code-Fix nötig |
| #94 | MCP `tools/list`-Schema: einige Tools mit generischem `kwargs` statt konkreter Parameter | MEDIUM | MCP | ✅ Gefixt (f09eb8be) — `GenericCrudToolGroup` (adr/risk/issue/glossary) liefert jetzt konkrete Feldlisten pro Entität in `create`/`update`-Schemas (`backend/mcp_server/tools/generic.py`), Feldnamen aus den jeweiligen ApplicationService-Signaturen übernommen. `additionalProperties: True` bleibt erhalten — keine Verhaltensänderung, nur Discoverability. Test: `test_create_and_update_schemas_expose_concrete_fields` in `test_generic_tool_group.py` |
| #95 | MCP akzeptiert ungültige `workspace_id` klaglos — immer 200 statt 404/400 | MEDIUM | MCP (security-adjacent) | ✅ Gefixt (`363affaa`) — neues fail-closed `workspace_exists`-Gate in `ToolRegistry.dispatch_request`, DI-injectable (Konstruktor-Param, Default prüft `Workspace.objects.filter(id=...).exists()`), gibt `WORKSPACE_NOT_FOUND` statt stillem 200 zurück. 204 Tests grün, keine Regression. Codeberg-Schließung ausstehend (PAT nicht verfügbar) |
| #96 | `user.create` (MCP) ohne Workspace-Mitgliedschaft → `user.assign_role` schlägt fehl | MEDIUM | MCP | ⚪ Bereits gelöst durch SEC-05 (kein neuer Fix nötig) — `AuthorizationService.assign_role` (`backend/auth_tenancy/services/authorization.py:256-336`) hat die Membership-Gate bereits entfernt (`del target_is_member  # no longer a rejection gate (SEC-05)`); ein nicht-Mitglied als Ziel ist explizit der normale Onboarding-Fall. `UsersToolGroup` (`backend/mcp_server/tools/users.py`) delegiert korrekt. End-to-End per MCP live verifiziert: `user.create` → `user.assign_role` für einen frischen Non-Member-User funktioniert. 44 Tests in `test_users_tool_group.py` grün |
| #98 | React-Router-v7-Future-Flag-Warnings in Browser-Konsole | LOW | Frontend | ✅ Gefixt (`49df24d`) — `BrowserRouter` in `frontend/src/App.tsx` erhält jetzt `future={{ v7_startTransition: true, v7_relativeSplatPath: true }}`. `tsc` sauber, kein Verhaltensunterschied |
| #99 | `PytestCacheWarning` im Container (Non-Root-User, `.pytest_cache` nicht schreibbar) | LOW | Infra | ✅ Gefixt (`1a0f688`) — Bug live reproduziert (root-owned `.pytest_cache` erzeugt exakt die gemeldete `PytestCacheWarning: ... Permission denied: '/app/.pytest_cache/v'`), dann `ENV PYTEST_ADDOPTS="-p no:cacheprovider"` in `backend/Dockerfile` ergänzt und nach Image-Rebuild verifiziert, dass die Warnung verschwindet. Host-seitige `pytest`-Läufe (außerhalb Docker) unberührt |
| #103 | Sidebar-Link "SE Metrics" (`/metrics`) redirected auf `/profile` | MEDIUM | Frontend-Routing | ⚪ Nicht reproduzierbar per Code — Routing-Analyse in `NavigationShell.tsx:117-161` (Router-Config, absichtlich nicht angefasst) zeigt eine korrekt registrierte `<Route path="/metrics" element={<MetricsDashboard />} />` vor dem Catch-all (`<Route path="*" element={<Navigate to="/" replace />} />`, nicht `/profile`); `SidebarNavigation.tsx:58` verlinkt korrekt auf `/metrics` per `NavLink`. Kein Code-Pfad gefunden, der auf `/profile` umleiten würde. Live-Verifikation im Browser nötig (evtl. Browser-Cache/Service-Worker/veralteter Build zum Testzeitpunkt) |
| #104 | Kein Size-Limit für Textfelder (`description` etc.) — DoS-Risiko | MEDIUM | Backend (Security-adjacent) | ✅ Gefixt (`14dd2643`) — `max_length` auf allen bisher unbegrenzten Freitext-Feldern in `backend/rest_api/serializers.py` ergänzt (`change_reason` 2000, `context`/`consequences`/`mitigation_strategy`/`impact_assessment` 5000–10000, `owner`/`ci_job_id` 255 analog zum Model, `GlossaryTerm(Version).definition`/`CustomFieldValue.value` 20000/5000); DB-`TextField.max_length` (z.B. Adr) ist nur ein Form-Validator ohne `full_clean()`-Aufruf, daher greift der Serializer als eigentliche Grenze. `IcdViewSet` baut sein DTO ohne Serializer direkt aus `request.data` — dafür Längenprüfung für `semantic_description` in `ContractValidator.validate_syntax` (`backend/icd/contract_validator.py`) ergänzt und das resultierende `ValueError` in `icd_views.py` sauber auf 400 `VALIDATION_ERROR` statt 500 gemappt. Tests in `test_serializers.py`, `test_icd.py`, neu `test_icd_views.py`. Keine Migration nötig (nur Serializer-/Validator-Ebene). |
| #105 | Dashboard "18 Open Items" inkonsistent zu tatsächlich 6 Issues | MEDIUM | Frontend/Backend (Datenintegrität) | ✅ Teilweise gefixt (Label) — Root Cause: `useDashboardData.ts:76` zählt tatsächlich **draft-Requirements** (`requirements.filter(r => r.status === "draft").length`), nicht Issues; es wird gar kein Backend-Issue-Aggregations-Endpoint angefragt. Bewusst risikoarmer Fix: nur Label/i18n korrigiert (`frontend/src/i18n/locales/en.json:174` `"Open Items"` → `"Draft Requirements"`, `de.json:171` `"Offene Elemente"` → `"Anforderungsentwürfe (Entwurf)"`), Datenquelle **unverändert** gelassen. **Offene Produkt-Entscheidung:** ob "Open Items" tatsächlich eine echte Issue-Aggregation braucht (neuer Backend-Endpoint + Frontend-Anbindung) ist eine Produkt-/Scope-Entscheidung und wurde hier bewusst NICHT getroffen — das ist ein separates Feature, kein Label-Bugfix |
| #106 | `test.run_report_results` akzeptiert nur Array, kein einzelnes Result-Objekt | MEDIUM | MCP | ✅ Gefixt (f09eb8be) — `_handle_run_report_results` in `backend/mcp_server/tools/tests.py` wrapped ein einzelnes `dict`-Result-Objekt jetzt automatisch in `[results_raw]`, bevor die bestehende Listen-Validierung greift. Schema-Beschreibung ergänzt. Tests: `test_run_report_results_accepts_single_object`/`_accepts_list`/`_rejects_empty_list` in `test_tool_groups.py` |
| #108 | MCP akzeptiert seit REQ-126 keine Bearer-Token mehr, nur API-Key (kein Fallback) | MEDIUM | MCP/Auth | Kein Bug — beabsichtigt (REQ-052/REQ-L2-MC-006, e559175d). Die MCP-API-Key-Pflicht ist explizit gefordert (`docs/se/L1/Gesamtsystem/L2/McpServerSystem/Components/COMP-MC-002_ToolRegistry/L3_COMP-MC-002_Requirements.md:18`, REQ-L2-MC-006) und unabhängig von REQ-126 (das betrifft nur die REST-Bearer-Rollenauflösung, `docs/REQUIREMENTS.md:141`). Keine Verhaltensänderung — Fehlermeldung in `_validate_api_key` (`backend/mcp_server/tool_registry.py`) präzisiert: verweist jetzt explizit auf REQ-L2-MC-006/REQ-052 und stellt klar, dass kein Zusammenhang zu REQ-126 besteht. Test: `test_bearer_token_rejected_with_precise_req_reference` in `test_tool_registry.py` |
| #110 | `workspace.get_context`: `active_roles` liegt undokumentiert unter `result.workspace_context.active_roles` | MEDIUM | MCP/Doku | ✅ Gefixt (f09eb8be) — Tool-Description von `workspace.get_context` (`backend/mcp_server/tools/cross_cutting.py`) dokumentiert jetzt die vollständige Response-Struktur (`active_roles`, `preset`, `preset_features`, `terminology`, `open_requirements_count`). Nur Doku-Änderung, kein Verhaltens-Fix. Test: `test_workspace_get_context_description_documents_response_fields` in `test_tool_groups.py` |
| #111 | `prompt_template.get` mit unbekanntem Slot → unhilfreiche Fehlermeldung ohne Liste gültiger Slots | MEDIUM | MCP | Bereits behoben im Code, Regressionstest ergänzt (ede6a2fe) — `_handle_get` in `backend/mcp_server/tools/prompt_template.py` listete bereits alle gültigen Slots in der Fehlermeldung; `test_get_unknown_slot_is_validation_error` in `test_prompt_template_tool_group.py` prüfte das aber nicht. Assertion ergänzt, die den Message-Inhalt gegen `PROMPT_TEMPLATE_DEFAULTS` verifiziert |
| #112 | "Download React DevTools"-Hinweis erscheint auch im Production-Build | LOW | Frontend | ⚪ Kein Bug — verifiziert per `vite build` (Production-Pipeline aus `frontend/package.json`: `tsc -p tsconfig.build.json && vite build`) und Grep der Build-Assets nach `'Download the React DevTools'`/`reactjs.org/link/react-devtools`: keine Treffer im Production-Build. `frontend/Dockerfile`s `production`-Target (nginx, `dist/`) ist korrekt vom `development`-Target (Vite-Dev-Server) getrennt. Vermutlich wurde der Dev-Server (`docker-compose.override.yml`, lokal automatisch gemerged) getestet statt eines echten Production-Builds. Kein Code-Fix nötig |
| #113 | Custom Fields (5 definiert) nirgends befüllt, kein Onboarding-Hinweis | LOW | Feature-Lücke | ✅ Teilweise gefixt (`5082d91`) — Root Cause: `ArtifactCustomFields.tsx` ist ausschließlich in `RequirementForm.tsx` verdrahtet, nirgends sonst (TestCase/Need/Architecture/Adr/Risk/Issue-Formulare) — das ist aus der Definitions-UI nicht ersichtlich. Beschreibungs-/Empty-State-Text in `CustomFieldsSection.tsx` (`settings.customFields.description`/`empty`, de/en) präzisiert: definierte Felder erscheinen im Bearbeitungsformular jeder Anforderung. **Offene Architektur-Frage** (bewusst nicht in dieser Session gelöst): ob Custom Fields auch in weitere Artefakt-Formulare verdrahtet werden sollen, ist eine separate, größere Produktentscheidung. 6 Tests in `CustomFieldsSection.test.tsx` grün |
| #115 | ICD-Liste: leerer Zustand ohne Anleitung/Hinweistext | LOW | Frontend | ✅ Gefixt (`5082d91`) — der leere Zustand selbst hatte bereits einen brauchbaren Hinweistext (`icds.empty`); der eigentliche Guidance-Gap lag im Create-Formular: der Save-Button ist bei weniger als zwei Architekturelementen (`architectureElements.length < 2`) still deaktiviert, ohne dass die Quell-/Ziel-Dropdowns oder ein Hinweis erklären, warum. Neuer sichtbarer Hinweis (`icds.needsElementsHint`, de/en) im Create-Formular ergänzt, der auf den Architektur-Bereich verweist. 2 neue Tests in `IcdView.smoke.test.tsx` (Hinweis sichtbar bei <2 Elementen, ausgeblendet bei ≥2) |
| #116 | `needs.query` (MCP) gibt leeres Array zurück, obwohl Need per REST bestätigt angelegt wurde | MEDIUM | MCP | ✅ Gefixt (f09eb8be) — Root Cause war schwerwiegender als der Titel nahelegt: `needs.query` existierte in `StakeholderNeedsToolGroup._TOOL_MAP` (`backend/mcp_server/tools/needs.py`) gar nicht, jeder Aufruf schlug mit `UNKNOWN_TOOL` fehl. Handler + Schema ergänzt, analog zu `requirement.query`, ruft `StakeholderNeedService.list_by_workspace` auf. Tests: `test_needs_query_requires_workspace_id`/`_calls_service`/`_passes_include_deleted` in `test_tool_groups.py` |

**Nächste Schritte:** Diese Liste wird gemäß Standing-Instruction ("alle Probleme fixen")
schrittweise abgearbeitet, priorisiert nach Security-Nähe (#95, #104, #108) und
Datenintegrität (#105, #116) vor reinen Doku-/Kosmetik-Findings (#89, #98, #99, #112).
