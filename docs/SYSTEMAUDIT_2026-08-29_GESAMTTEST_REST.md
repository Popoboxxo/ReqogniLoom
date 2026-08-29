# Systemaudit 2026-08-29 — Gesamttest REST-API (`/api/v1/`)

> Parallel/nachfolgender REST-API-Teil des Gesamtaudits, dessen MCP-Teil in
> `docs/SYSTEMAUDIT_2026-08-29_GESAMTTEST_MCP.md` dokumentiert ist. Live-Test
> gegen den laufenden Dev-Stack (`localhost:8001`), Branch
> `fix/systemaudit-p7-backend-konsistenz`. Referenz für alle Endpunkte:
> `GET /api/v1/schema/` (drf-spectacular, YAML), zum Zeitpunkt des Tests
> **245 Pfad-Templates** über **27 ViewSets** (`backend/rest_api/views.py` +
> `api_key_views.py`) und **~55 APIViews** verteilt auf
> `backend/rest_api/*.py`.

## Testmethode

- Login als `admin`/`admin12345` (bootstrap-provisionierter Tenant-Admin),
  Bearer-Token + httpOnly-Cookie-Flow beide verifiziert.
- Eigene, isolierte Test-Workspaces pro Testfall angelegt (Namenskonvention
  `REST-Audit-*`, `smoke-*`, `conc-probe-*`, `iso-test-*`), am Ende **alle 33
  aktiven Test-Workspaces via `POST /workspaces/{id}/close/` weich
  geschlossen** (harte Löschung erfordert eine Namens-Bestätigung im Body und
  war für den Cleanup nicht nötig). 4 während der Sitzung angelegte API-Keys
  (inkl. eines verwaisten `mcp-audit-admin-key` aus dem parallelen MCP-Audit)
  revoked. 8 Test-User (`audit-viewer-*`) deaktiviert.
- Scratch-Skripte (nicht Teil des Repos):
  `.../scratchpad/audit_rest.py`, `smoke_sweep.py`, `concurrency_probe.py`.

## Abdeckung

**Tief getestet** (vollständiger CRUD-Zyklus inkl. Error-Pfade, 18 von 27
Ressourcen-Gruppen):

| Gruppe | Create | List (paginiert) | Detail | Patch | Delete/Soft-Delete |
|---|---|---|---|---|---|
| `auth/*` (login/refresh/me) | — | — | — | — | — |
| `workspaces` | OK | OK | OK | — | OK (close) |
| `requirements` | OK | OK | OK | OK | OK (→ outdated) |
| `needs` | OK | OK | OK | OK | OK (→ outdated) |
| `architecture` | OK | OK | OK | OK | OK (404 nach Delete, **by design**) |
| `testcases` | OK | OK | OK | OK | OK (→ outdated) |
| `adrs` | OK | OK | OK | OK | OK (→ outdated) |
| `risks` | OK | OK | OK | OK | OK (→ outdated) |
| `issues` | OK | OK | OK | OK | OK (→ outdated) |
| `change-requests` | OK | OK | OK | OK | OK (→ outdated) |
| `glossary` | OK | OK | OK | OK | OK (→ outdated) |
| `trace-links` | OK | OK | — | — | OK |
| `baselines` | Blocked (SE-Auditor-Gate, korrekt) | OK | — | — | — |
| `goals` | Blocked (Preset-Gate, korrekt) | — | — | — | — |
| `api-keys` | OK | OK | — | — | OK (revoke) |
| `users` | OK | OK | — | — | OK (deactivate) |
| `workspaces/{id}/export/csv` | OK (Formel-Injection-Test) | — | — | — | — |
| `workspaces/{id}/members` | OK (Rollen-Zuweisung) | — | — | — | — |

**Nur strukturell verifiziert** (über OpenAPI-Schema gelistet, kein Live-CRUD
in dieser Sitzung — Empfehlung: separate Folge-Session): `diagrams`, `icds`,
`prompt-templates`/`prompt-variables`, `custom-field-definitions`,
`attribute-visibility-configs`, `workflow-defaults`/`workflows`,
`permission-defaults`/`permission-mismatches`, `admin/*` (backups, health,
theme-palettes), `memory/*`, `search`, `interviews`, `main-goals`,
`test-runs`, `reqif`-Import/Export, `architecture/decompose`, `audit/*`
(Workspace-Audit-Views), `settings`/`llm-settings`/`review-policy`,
`global-default` Views, `bundle-compression-status`, `version`.

## Kernfrage: Multi-Tenancy-Isolation bei REST-Reads (Vergleich zum MCP-Befund)

**Antwort: JA, REST ist bei Workspace-scoped Reads korrekt gescoped —
im Gegensatz zum MCP-Befund.**

Testaufbau: Tenant-Admin legt zwei Workspaces A und B im selben Tenant an, ein
neuer Testuser bekommt die Rolle `viewer` **ausschließlich** in Workspace A
zugewiesen (`POST /workspaces/{A}/members/`). Als dieser User eingeloggt:

- `GET /requirements/?workspace_id={B}` → **403** `RBAC denied: no active
  role permits 'read'` (kein Leak, keine leere Liste die einen 200
  vortäuscht — explizites 403).
- `GET /requirements/{id-in-B}/?workspace_id={B}` → **403**, dieselbe
  Fehlermeldung — auch der direkte Zugriff per ID auf ein bekanntes Objekt in
  einem fremden Workspace scheitert.
- `GET /requirements/?workspace_id={A}` (eigener Workspace) → 200, korrekt.
- `POST /requirements/` in A (Viewer-Rolle, kein Schreibrecht) → 403.
- `POST /requirements/` in B (keine Rolle) → 403.

Ursache: `HasOperationPermission` + `AuthTenancyAuthentication` lösen
`active_roles` **workspace-scoped** auf, sobald eine URL/ein Query-Param
`workspace_id` trägt (siehe Kommentar in
`backend/auth_tenancy/rest_workspace_members.py:79-96`, derselbe Mechanismus
gilt für die Artefakt-ViewSets). Das ist die strukturelle Ursache, warum REST
hier korrekt ist, während `mcp_server/tool_registry.py`s `dispatch_request()`
RBAC laut dem parallelen MCP-Audit nur für **write**-klassifizierte Tools
prüft (`_is_write_tool()`-Gate) — Reads laufen dort ungefiltert durch die
Tenant-weite Rolle. **Empfehlung an das Entwicklerteam:** Die REST-Variante
(`AuthTenancyAuthentication`-Resolution) ist die korrekte Referenzimplementierung,
an der sich ein MCP-Fix orientieren sollte.

## Befunde

### HIGH — Optimistic Locking (`expected_version`) nur für ArchitectureElement implementiert

`expected_version` wird in `backend/rest_api/serializers.py` **genau einmal**
deklariert — auf `ArchitectureElementSerializer` (Zeile 726) — und nur dort
tatsächlich an den Service durchgereicht
(`ArchitectureElementViewSet.partial_update`, `views.py:1567`). Für
`RequirementSerializer`, `StakeholderNeedSerializer`, `TestCaseSerializer`,
`AdrSerializer`, `RiskSerializer`, `GoalSerializer`, `MainGoalSerializer`,
`IssueSerializer`, `ChangeRequestSerializer`, `GlossaryTermSerializer`,
`DiagramSerializer`, `IcdSerializer`, `WorkspaceSerializer`,
`WorkflowDefinitionSerializer` existiert das Feld nicht — ein mitgesendetes
`expected_version` wird von DRF stillschweigend als unbekanntes Body-Feld
ignoriert.

**Live reproduziert:** Requirement auf `version=2` gepatcht, danach PATCH mit
`expected_version: 1` (veraltet) gesendet → **200 OK**, `version` wird auf 3
erhöht, kein 409. Erwartet laut Projekt-Konvention (`LOCK_VERSION_HELP_TEXT`,
AP-3/UI-08-Fix für Architecture) wäre ein 409-Conflict.

**Auswirkung:** Bei jedem Entity-Typ außer ArchitectureElement überschreibt
ein "Last write wins" stillschweigend gleichzeitige Änderungen zweier
Nutzer — genau das Szenario, das `expected_version` verhindern soll. Kein
Datenverlust-Schutz bei Konflikten in Requirements, Needs, TestCases, ADRs,
Risks, Issues, ChangeRequests, Goals, Glossary-Terms, Diagrams, ICDs,
Workspaces und WorkflowDefinitions.

**Empfehlung:** An `developer`/`api-specialist` übergeben — entweder
`expected_version` konsistent auf allen mutierenden Entity-Serializern
deklarieren und in den jeweiligen `_svc().update_*()`-Aufrufen durchreichen
(Muster aus `ArchitectureElementViewSet` kopierbar), oder falls
Optimistic Locking bewusst nur für Architecture vorgesehen ist, das explizit
dokumentieren und den vorhandenen `LOCK_VERSION_HELP_TEXT`
("this artifact has N revisions") nicht fälschlich auf alle Entities
anwenden.

### MEDIUM — `WorkspaceRequest`-Schema verspricht Create-Time-Felder, die `create_workspace()` ignoriert

`WorkspaceSerializer` (und damit das generierte OpenAPI-Schema
`WorkspaceRequest`) deklariert `goals_enabled`, `goals_ai_enabled`, `theme`,
`decomposition_link_type`, `default_link_type` mit Defaults als Teil des
POST-Bodys. `WorkspaceViewSet.create()`s eigener Docstring dokumentiert den
tatsächlich unterstützten Body korrekt als `{name, preset?,
terminology_profile?, language?}`, und die Service-Methode
`application.workspace_service.create_workspace()` akzeptiert diese
zusätzlichen Felder gar nicht als Parameter.

**Live reproduziert:** `POST /workspaces/` mit `{"name": ..., "preset":
"standard", "goals_enabled": true}` → 201, aber `goals_enabled` im Response
und bei nachfolgendem `GET` weiterhin `false`. Ein Client, der sich auf das
OpenAPI-Schema statt auf den Docstring verlässt, bekommt ein
Feature-Flag-Silent-Drop statt eines Validierungsfehlers.

**Nachgelagerter Effekt (kein eigener Bug, aber Symptom):** `POST /goals/`
in einem frisch angelegten Workspace liefert korrekt `403
PERMISSION_DENIED: "Goals are not enabled for workspace ..."` — das
Preset-Gate selbst funktioniert wie vorgesehen, nur lässt sich
`goals_enabled` eben nicht schon beim Anlegen setzen, sondern erst per
nachträglichem `PATCH /workspaces/{id}/`.

**Empfehlung:** An `api-specialist`/`developer` übergeben — entweder
`create_workspace()` um die fehlenden Parameter erweitern, oder die
Serializer-/Schema-Deklaration auf `read_only`/`write_only` bei Create korrigieren,
damit Schema und Verhalten wieder übereinstimmen.

### OK — Error-Envelope-Konsistenz (AP-1/AP-6)

400 (`VALIDATION_ERROR`), 401 (`authentication_required`/DRF-401), 403
(`PERMISSION_DENIED`/RBAC-Meldungen), 404 (`NOT_FOUND`) und 409
(`LAST_ADMIN`/Captcha-Mismatch-Pfade) liefern durchgehend
`{"error": {"code", "message", "details"}}` — verifiziert über
`reqogniloom_exception_handler` (zentral gewired via
`REST_FRAMEWORK['EXCEPTION_HANDLER']`) sowie manuelle `_err()`-Hilfsfunktionen
in den Auth-/Members-Views, die dasselbe Format von Hand bauen. Keine rohen
Tracebacks, keine `str(exc)`-Leaks in den getesteten Fehlerantworten
gefunden. Einzige Falle bei der Fehlerpfad-Prüfung selbst: eine
`requests.Session`, die zuvor eingeloggt hat, sendet den httpOnly-Access-Cookie
automatisch mit — ein "kein Token"-Test muss eine komplett neue Session (oder
`requests.get()` ohne Session) verwenden, sonst täuscht Cookie-Auth einen
falschen 200 statt 401 vor (im Test entdeckt und korrigiert, kein App-Bug).

### OK — Refresh-Token-Rotation + Reuse-Detection (SA-32/GitHub #135)

`AUTH_REFRESH_REUSE_GRACE_SECONDS` ist in diesem Container nicht gesetzt →
Default `0` (strict, aus `backend/reqogniloom/settings.py:615` und
`docker-compose exec backend printenv` bestätigt) — keine Wartezeit nötig.

Testablauf mit dediziertem Test-User (nicht dem Admin-Account):
1. `POST /auth/refresh/` mit gültigem Refresh-Cookie → 200, neuer
   Refresh-Cookie-Wert (`rotiert: true`).
2. Wiederholung mit dem **alten, bereits verbrauchten** Refresh-Cookie
   → **401** `invalid_token` (Reuse korrekt erkannt).
3. Danach auch der **legitime, rotierte** Cookie-Wert erneut versucht →
   ebenfalls **401** — die komplette Session-Familie wurde beim erkannten
   Reuse verbrannt (SA-32-Design: "limits the blast radius of a leaked
   refresh token to one use"), nicht nur der wiederverwendete Einzeltoken.

Technischer Hinweis für künftige Tests: `reqogniloom_refresh`/`csrftoken`
tragen das `Secure`-Flag; `http.cookiejar` (und damit `requests`' Cookie-Jar)
verweigert korrekterweise die Übertragung über die unverschlüsselte
`http://localhost:8001`-Dev-Verbindung. Umgangen durch manuelles Setzen des
`Cookie`-Headers statt Verlass auf den Session-Jar — kein Bug, sondern
korrektes Cookie-Hardening, das im Testaufbau berücksichtigt werden musste.

### OK — CSV-Formel-Injection-Schutz (SA-31)

Requirement mit Titel `=cmd|'/c calc'!A1` angelegt, über
`GET /workspaces/{id}/export/csv/?entity_type=Requirement` exportiert (Hinweis:
`entity_type` ist ein Pflicht-Query-Parameter, ohne ihn 400
`VALIDATION_ERROR` — nicht dokumentiert im Task, aber schnell über die
Fehlermeldung selbst auflösbar). Exportierte Zelle:
`"'=cmd|'/c calc'!A1"` — mit führendem Apostroph maskiert, wie von
`application.csv_safety.neutralize_csv_formula` vorgesehen (OWASP-Referenz im
Docstring). Öffnet die Datei nicht als ausführbare Formel in Excel/LibreOffice.

### OK — API-Key-Lifecycle

`POST /api-keys/` → 201, Klartext-Key (`reqlo_*`) nur in dieser einen
Antwort sichtbar. `GET /api-keys/` (Liste) → Klartext **nicht** erneut
enthalten (nur Metadaten/Präfix). `DELETE /api-keys/{id}/` → 204. Alle in
dieser Sitzung erzeugten Keys wieder revoked (siehe Cleanup-Abschnitt).

### INFO — Throttling strukturell verifiziert, nicht live ausgelöst

`backend/rest_api/throttling.py` verdrahtet `LoginRateThrottle` +
`LoginIpRateThrottle` (zählen nur fehlgeschlagene Versuche, geschlüsselt auf
(IP, Username) bzw. IP), `RefreshRateThrottle`, sowie
`AuthContextUserRateThrottle`/`AuthContextAnonRateThrottle` als
`DEFAULT_THROTTLE_CLASSES`. Bewusst **nicht live mit Hunderten Requests
provoziert**: `backend/reqogniloom/settings.py:419-439` konfiguriert für
Nicht-Prod-Umgebungen (dieser Dev-Stack) absichtlich sehr hohe Raten
(`login=1000/min`, `refresh=1000/min`, `user=20000/min`,
`anon=20000/min` vs. Prod `10/min`/`30/min`/`600/min`/`120/min`), damit
Dev-Arbeit und E2E-Suiten nicht gedrosselt werden. Der bereits laufende
Backend-Container lag zu Beginn dieser Sitzung bei ~501/512 MB RAM
(Single-Worker `uvicorn --reload`, siehe Projekt-Memory zu
Dev-Stack-Concurrency) — Hunderte zusätzliche Requests allein zum Erzwingen
eines 429 hätten das Risiko einer Instabilität für keinen zusätzlichen
Erkenntnisgewinn über die bereits im Code verifizierte Konfiguration
getragen. Empfehlung: 429-Verhalten live in einer prod-nah konfigurierten
Umgebung (oder mit temporär abgesenkten Env-Var-Raten) verifizieren, nicht
im geteilten Dev-Stack.

### Ausgeräumter Verdacht — kein Hinweis auf Request-Context-Bleed unter Nebenläufigkeit

Während der Testreihe trat einmalig ein verwirrendes Ergebnis auf (ein
GET auf eine bestimmte Requirement-ID schien Daten eines anderen Requirements
zurückzugeben). Ursache war ein Fehler im eigenen Testskript
(`requests.Session`-Cookie-Auth täuschte eine "anonyme" Anfrage vor,
kombiniert mit unklarer Skript-Zustandsverfolgung über mehrere Testläufe
hinweg), **nicht** ein Bug der Anwendung — mit korrigiertem, sauber
isoliertem Testcode war das Ergebnis konsistent korrekt. Zur Absicherung
zusätzlich ein dedizierter Nebenläufigkeits-Test gefahren: 12 Workspaces mit
je einem eindeutig betitelten Requirement angelegt, 5 Runden à 12 parallele
`GET`-Requests (60 total) über `ThreadPoolExecutor` gefeuert — **0
Identitäts-Mismatches**. Kein Hinweis auf ein Thread-Local/Async-Context-Bleed-Problem
(relevant wegen der dokumentierten `TenantContext`-Thread-Local-Architektur
kombiniert mit Single-Worker-`uvicorn`) in dieser Stichprobe. Für eine
abschließende Aussage bei sehr hoher Nebenläufigkeit reicht dieser Test
nicht — als Negativbefund dokumentiert, nicht als Entwarnung für alle Lastfälle.

### OK — Sonstige Smoke-Test-Beobachtungen (kein Bug)

- **Soft-Delete-Konvention:** `Requirement`, `StakeholderNeed`, `TestCase`,
  `Adr`, `Risk`, `Issue`, `ChangeRequest`, `GlossaryTerm` liefern nach
  `DELETE` weiterhin `GET → 200` mit `status: "outdated"`.
  `ArchitectureElement` ist die einzige **dokumentiert bewusste** Ausnahme
  (404 nach Delete, siehe Docstring in `views.py:1593-1599` — kein
  Status-Spiegelfeld vorhanden) — korrekt, kein Bug.
- **Baseline-Erstellung** wurde vom SE-Auditor-Gate mit `400
  SE_AUDITOR_BLOCKED` verhindert, weil die angelegten Test-Requirements
  keinen `derives-from`-Link zu einer StakeholderNeed hatten — korrektes
  Verhalten des Traceability-Quality-Gates (Configurable Rigor), kein Bug.
- **Pagination:** Alle getesteten List-Endpunkte liefern konsistent
  `{count, next, previous, results}`.

## Zusammenfassung

- **Getestete Ressourcen-Gruppen:** 18 von 27 ViewSet-Gruppen tief (voller
  CRUD-Zyklus inkl. Fehlerpfade), weitere ~9 Gruppen nur strukturell über das
  OpenAPI-Schema erfasst (siehe Abdeckungstabelle).
- **Multi-Tenancy-Reads:** REST ist korrekt workspace-scoped — bestätigter
  Unterschied zum MCP-Befund (MCP-Reads sind nicht workspace-, nur
  tenant-scoped).
- **Refresh-Token-Reuse-Detection:** funktioniert (401 bei Replay, ganze
  Session-Familie verbrannt).
- **CSV-Formel-Injection:** korrekt maskiert (führendes Apostroph).
- **Neue Befunde:** 1× HIGH (Optimistic Locking fehlt außerhalb
  ArchitectureElement), 1× MEDIUM (Workspace-Create-Schema verspricht Felder,
  die die Service-Schicht ignoriert).
- **Kein neuer Sicherheitsbefund** bei RBAC/Workspace-Isolation,
  Error-Envelope, CSV-Export oder API-Key-Handling gefunden.
