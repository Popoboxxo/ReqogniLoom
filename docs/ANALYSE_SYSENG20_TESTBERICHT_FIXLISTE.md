# Analyse: SysEng 2.0 Testbericht — Konsolidierte Fixliste

> Status: **P0 (Sicherheit/Crashes/Workflow-Init) + P1 (MCP) + P2-REST umgesetzt, verifiziert,
> committed. P2-UI teilweise (UI-06 gefixt, UI-01/02 kein Fix nötig; UI-03/04/05 offen).
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
> **Hinweis Codeberg-Export:** `export_issues.md` enthält zum Prüfzeitpunkt nur 4 Issues
> (#117–#120), Issue #117 ist im Export mitten im Fehlertext abgeschnitten. Unklar, ob dies
> bereits alle im Tracker offenen QA-Issues sind — bei Bedarf erneuten Export anfordern.

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
| Codeberg-Issues eingearbeitet | 4 (#117–#120) | siehe Anhang |
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
| UI-03 | ADRs/Risks-Seiten laden Daten, aber kein `<h2>`/`<h3>` Heading | extended | Heading-Komponente ergänzen (auch Accessibility-relevant) | 🔲 Offen — noch nicht bearbeitet |
| UI-04 | SPA verliert Auth-Session nach ca. 5 Navigationen | alle | Token-Refresh/Session-Handling im Frontend debuggen | 🔲 Offen — noch nicht bearbeitet |
| UI-05 | Stale-Ref-Navigation — Ref-IDs ändern sich zwischen Snapshots | alle | Ursache in State-Management/Caching prüfen | 🔲 Offen — noch nicht bearbeitet |
| UI-06 | Dashboard-Card zeigt aktiven SE-Mode (z.B. "extended SE Mode") an, bietet aber keinen direkten Wechsel — nur über Settings-Seite erreichbar | alle (**Codeberg #118**) | Mode-Switcher direkt auf der Dashboard-Card ergänzen oder Card mit Link zu Settings versehen | ✅ Gefixt (`ffc6f4b6`), live verifiziert: Preset-Badge ist jetzt Button, navigiert zu `/settings` mit korrektem Workspace-Kontext — Codeberg #118 geschlossen |

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
7. **P2 UI** — UI-01/UI-02 verifiziert (kein Fix nötig), UI-06 erledigt (`ffc6f4b6`); UI-03,
   UI-04, UI-05 noch offen
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
| `test-results/export_issues.md` | Codeberg-Issue-Export (4 Issues #117-#120, unvollständig/abgeschnitten) |

---

## Anhang: Codeberg-Issue-Tracking

Issue-Tracker: `https://codeberg.org/dduchrow/ai-native-reqflow-POC/issues` (Titel-Tag `[QA][SEVERITY]`)

| Codeberg-# | Titel | Severity | Fixliste-ID | Status |
|---|---|---|---|---|
| #117 | needs.get_traces crashed - list_incoming Methode fehlt | MEDIUM | MCP-05 | ✅ Gefixt (siehe MCP-05 oben) — geschlossen |
| #118 | Dashboard-Card zeigt 'extended SE Mode' - kein Wechsel moeglich | MEDIUM | UI-06 | ✅ Gefixt (siehe UI-06 oben, `ffc6f4b6`) — geschlossen |
| #119 | Issue-Status ist case-sensitive | MEDIUM | REST-06 | ✅ Bereits vorher gelöst (siehe REST-06 oben, `ad658662`) — geschlossen |
| #120 | test-runs Detail-Endpunkt braucht workspace_id als Query-Param | MEDIUM | REST-07 | ✅ Bereits korrekt implementiert (siehe REST-07 oben, `cb90136f`) — geschlossen |

**Offen:** Export-Datei ist unvollständig (nur 4 Issues, #117 inhaltlich abgeschnitten) — es ist
nicht auszuschließen, dass weitere Issues im Tracker existieren, die im aktuellen Export fehlen.
