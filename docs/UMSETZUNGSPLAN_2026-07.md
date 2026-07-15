# Umsetzungsplan — ReqFlow Härtung & SysEng-Vervollständigung

> Erstellt: 2026-07-15 · Basis: Codebase-Analyse (Backend, Frontend, Docs) vom 2026-07-15
> Zweck: Arbeitspakete (AP) so zuschneiden, dass sie **einzeln an kostengünstige
> Agenten** (Haiku/Sonnet) übergeben werden können — in sich abgeschlossen, mit
> konkreten Datei-Ankern, Schritten und Akzeptanzkriterien.
>
> **Konventionen für alle APs:**
> - Ein AP = ein Branch = ein PR. Branch-Schema: `fix/REQ-XXX-<slug>` bzw. `feat/REQ-XXX-<slug>`.
> - Commit-Messages Englisch, mit REQ-Referenz (`fix(REQ-115): …`).
> - DoD immer: bestehende Tests grün (`docker-compose exec backend pytest`,
>   `frontend: npx vitest run`), neue Tests für neues Verhalten, REQUIREMENTS.md-Status aktualisieren.
> - Neue Anforderungen (ReqIF, Review-UI, …) bekommen neue REQ-IDs ab **REQ-141**
>   in `docs/REQUIREMENTS.md` (höchste vergebene ID ist derzeit REQ-140).

---

## Übersicht & Reihenfolge

| Phase | Arbeitspakete | Ziel | Parallelisierbar |
|---|---|---|---|
| 0 — Security-Blocker | AP-01 … AP-05 | Produktions-/Vertrauensblocker schließen | AP-01–04 parallel; AP-05 nach AP-03 |
| 1 — AI-Korrektheit | AP-06 | Halluzinationsrisiko der AI-Zerlegung beheben | unabhängig |
| 2 — Halbfertiges verdrahten | AP-07 … AP-11 | Vorhandenes Backend im UI nutzbar machen | AP-07/08 parallel; AP-09→AP-10; AP-11 zuletzt |
| 3 — Interoperabilität | AP-12, AP-13 | ReqIF-Export, dann -Import | AP-12 vor AP-13 |
| 4 — Schuldenabbau | AP-14 … AP-18 | Monolith-Zerlegung, Rest-Migrationen, Tenancy | weitgehend parallel |

**Agenten-Eignung** (Spalte „Agent"):
- **H** = Haiku-tauglich: mechanisch, klar umrissen, wenig Design-Spielraum.
- **S** = Sonnet: braucht Kontextverständnis über mehrere Dateien, überschaubares Design.
- **S+R** = Sonnet mit Review durch stärkeres Modell/Menschen vor Merge (sicherheits- oder architekturkritisch).

---

## Phase 0 — Security-Blocker (P0)

### AP-01 · Secrets fail-fast statt CHANGE-ME-Defaults
**REQ:** REQ-115 · **Größe:** S · **Agent:** H · **Abhängigkeiten:** keine

**Problem:** `backend/reqflow/settings.py:32` (`SECRET_KEY`) und `:282` (`AUTH_JWT_SECRET`)
haben hardcodierte `CHANGE-ME…`-Defaults. Der HMAC-Signature-Seal der Freigaben
(`backend/workflow/signature_gate.py`) hängt am `SECRET_KEY` — mit bekanntem Default
sind Signaturen fälschbar.

**Schritte:**
1. In `settings.py` beide `config(..., default=…)`-Aufrufe ändern: Default entfernen.
   Bei fehlender Env-Var: `ImproperlyConfigured` mit klarer Meldung werfen
   (Vorbild: DB-Passwort-Handling, das bereits fail-fast ist — im selben File suchen).
2. Ausnahme für Tests: `settings_test.py` darf feste Test-Secrets setzen (prüfen, ob
   dort bereits Secrets gesetzt werden; sonst ergänzen).
3. `.env.example` (bzw. env_file-Vorlage, siehe `docker-compose.yml`) um beide
   Variablen mit Platzhalter + Generierungshinweis ergänzen
   (`python -c "import secrets; print(secrets.token_urlsafe(64))"`).
4. README-Abschnitt „How Start" um den Pflicht-Schritt ergänzen.

**Akzeptanz:**
- Backend-Start ohne `SECRET_KEY`/`AUTH_JWT_SECRET` bricht mit verständlicher Fehlermeldung ab.
- `pytest` läuft unverändert grün (Test-Settings).
- Neuer Test: Settings-Import ohne Env-Var → `ImproperlyConfigured` (z.B. via `importlib.reload` oder Subprozess).
- REQUIREMENTS.md: REQ-115 → Done.

---

### AP-02 · LLM-API-Keys verschlüsselt speichern
**REQ:** REQ-081 · **Größe:** M · **Agent:** S · **Abhängigkeiten:** AP-01 (Key-Ableitung vom Secret-Handling)

**Problem:** `persistence.LlmSettings.api_key` (`backend/persistence/models.py:1238` ff.)
liegt im Klartext in der DB.

**Schritte:**
1. Symmetrische Verschlüsselung mit `cryptography.Fernet`; Schlüssel aus neuer Env-Var
   `FIELD_ENCRYPTION_KEY` (fail-fast wie AP-01, Test-Default in `settings_test.py`).
2. Kapselung als Model-Property (`api_key` als Property über internem Feld
   `api_key_encrypted`) — Aufrufer (LLM-Adapter in `backend/llm_adapter/`,
   Serializer in `rest_api/settings_views.py`) dürfen sich nicht ändern müssen.
3. Datenmigration: bestehende Klartext-Werte verschlüsseln (idempotent, mit
   Erkennung „schon verschlüsselt" via Fernet-Prefix `gAAAA`).
4. Serializer: API-Key nur write-only, bei GET maskiert (`sk-…****`); prüfen, ob das
   bereits so ist, sonst nachziehen.
5. Tests: Roundtrip (set → DB-Wert ist nicht Klartext → get liefert Klartext),
   Migration auf Bestandsdaten, GET maskiert.

**Akzeptanz:** DB-Dump enthält keinen Klartext-Key mehr; alle `llm_adapter`- und
`settings_views`-Tests grün; REQ-081 → Done.

---

### AP-03 · Rollen-Auflösung für Bearer-Tokens & MCP-API-Keys
**REQ:** REQ-126, REQ-127 · **Größe:** M · **Agent:** S+R · **Abhängigkeiten:** keine

**Problem:** Requests mit Bearer-Token/MCP-API-Key lösen die Nutzerrollen nicht
korrekt auf → RBAC (`rest_api/auth_enforcer.py::RbacPermission`,
`backend/mcp_server/tool_registry.py` Write-Tool-Gating) greift für AI-Agenten
nicht wie spezifiziert.

**Schritte:**
1. Zuerst REQ-126/127 in `docs/REQUIREMENTS.md` lesen (genaue Findings der
   Hermes-Kampagne) und die dort beschriebenen Repro-Fälle als Tests formulieren
   (**test-first**, da sicherheitskritisch).
2. Rollen-Auflösung in `auth_tenancy` (AuthorizationService, `models.py::UserRole`,
   `ApiKey`) so korrigieren, dass JWT- und API-Key-Identitäten dieselbe
   Rollen-Pipeline durchlaufen wie Session-User.
3. MCP-Seite: `tool_registry.py` — Write-Tools (`_WRITE_TOOL_PREFIXES`) müssen für
   viewer-Rolle abgelehnt werden; Testfälle je Rolle × Tool-Klasse (read/write).
4. Regressionstests REST: je Rolle (admin/editor/viewer/approver) × Auth-Art
   (Session/JWT/API-Key) ein Matrix-Test auf einen Read- und einen Write-Endpoint.

**Akzeptanz:** Rollen-Matrix-Tests grün (REST + MCP); kein Endpoint erlaubt
viewer-Schreibzugriff via API-Key; REQ-126/127 → Done. **PR-Review durch Menschen/Opus vor Merge.**

---

### AP-04 · Container-Härtung: non-root, DB/Redis-Defaults
**REQ:** REQ-059, REQ-058, REQ-057 (Rest) · **Größe:** S–M · **Agent:** H · **Abhängigkeiten:** keine

**Schritte:**
1. `backend/Dockerfile` und `frontend/Dockerfile`: dedizierten User anlegen
   (`useradd -r app`), `USER app` vor `CMD`; Schreibpfade (static, media, tmp) per
   `chown` vorbereiten. nginx-Variante des Frontends: `nginx-unprivileged`-Pattern
   oder Port >1024.
2. `docker-compose.yml`: prüfen, welche Defaults für `POSTGRES_PASSWORD`/Redis
   `requirepass` noch trivial sind (REQ-058/057-Reststand in REQUIREMENTS.md
   nachlesen) und auf Pflicht-Env-Var ohne Default umstellen.
3. Smoke-Test: `docker-compose build && docker-compose up -d`, Healthchecks aller
   Services grün, `docker-compose exec backend id` ≠ uid 0.

**Akzeptanz:** Alle Container laufen non-root; Compose startet ohne gesetzte
Pflicht-Variablen **nicht**; Healthchecks grün; REQ-057/058/059 → Done.

---

### AP-05 · MCP-Restfehler der Hermes-Kampagne schließen
**REQ:** REQ-128 … REQ-140 (alle noch „Active") · **Größe:** M · **Agent:** S · **Abhängigkeiten:** AP-03

**Schritte:**
1. `docs/REQUIREMENTS.md`, Block „Hermes Bugfix Campaign (2026-07-15)" durchgehen;
   je REQ mit Status Active: Repro nachstellen (MCP-E2E-Suite,
   `backend/mcp_server/`-Tests), fixen, Test ergänzen.
2. Bekannte Einzelfälle laut Analyse: doppelte `tools/list`-Einträge,
   URL-Routing-500er, MCP-Spec-Abweichungen (REQ-086/107, `protocol_handler.py`).
3. Ein PR **pro REQ** (kleine, reviewbare Einheiten — gut für günstige Agenten).

**Akzeptanz:** MCP-E2E-Suite (150+ Tests) grün; jeder gefixte REQ → Done mit Testreferenz.

---

## Phase 1 — AI-Korrektheit

### AP-06 · Artefakt-Inhalt in LLM-Prompts aufnehmen
**REQ:** REQ-046 · **Größe:** M · **Agent:** S · **Abhängigkeiten:** keine

**Problem:** Die AI-Ableitung/Zerlegung (`backend/llm_adapter/`,
`mcp_server/tools/ai_derivation.py`, Prompt-Slots in `persistence.PromptTemplate`)
übergibt Titel, aber nicht den Beschreibungs-/Kontextinhalt der Artefakte →
das LLM halluziniert Anforderungsinhalte.

**Schritte:**
1. REQ-046 in REQUIREMENTS.md lesen; betroffene Prompt-Bau-Stellen lokalisieren
   (Suche nach Platzhaltern `{req_title}`, `{arch_elements_json}` — siehe auch
   Frontend `WorkspaceSettings/PromptTemplateSection.tsx` für die dokumentierten Platzhalter).
2. Neue Platzhalter einführen (`{req_description}`, `{need_description}`,
   `{parent_context}` o.ä.), Default-Templates in `presets`/`prompt_template`
   erweitern, Befüllung im Prompt-Builder ergänzen. Kürzung bei Überlänge
   (einfaches Zeichenlimit mit Ellipse, Limit als Konstante).
3. Bestehende benutzerdefinierte Templates dürfen nicht brechen: unbekannte
   Platzhalter tolerant behandeln (bereits so? testen).
4. Tests: Prompt-Snapshot-Test (Beschreibung erscheint im gebauten Prompt),
   Überlängen-Kürzung, Rückwärtskompatibilität alter Templates.

**Akzeptanz:** Gebaute Prompts enthalten nachweislich Artefakt-Beschreibungen;
`llm_adapter`- und `ai_derivation`-Tests grün; REQ-046 → Done.

---

## Phase 2 — Halbfertige Features verdrahten

### AP-07 · TracePanel im ArtifactInspector real anbinden
**REQ:** neu → REQ-141 anlegen · **Größe:** S · **Agent:** H · **Abhängigkeiten:** keine

**Problem:** `frontend/src/components/shared/ArtifactInspector/TracePanel.tsx:19`
nutzt `mockFetchTraceLinks` (liefert immer `[]`) — Nutzer sehen fälschlich
„keine Trace-Links". Der echte Endpoint existiert (`/api/v1/tracelinks/`,
Frontend-API `frontend/src/api/` — vorhandene Nutzung in
`TraceabilityView/` und `ReqTraceLinkPanel.tsx` als Vorbild).

**Schritte:**
1. Mock durch echten Fetch via bestehendes API-Modul ersetzen (TanStack-Query-Hook,
   Muster von `useRequirementData.ts` übernehmen); `resolveArtifactRef` verdrahten.
2. Loading-/Error-/Empty-State unterscheiden (Empty erst nach erfolgreichem Fetch).
3. Vitest: Hook-Test mit gemocktem API-Client (Links werden gerendert; Fehlerpfad).

**Akzeptanz:** Inspector zeigt echte Links für ein Artefakt mit Trace-Links;
kein `mockFetchTraceLinks` mehr im Code; REQ-141 → Done.

---

### AP-08 · Versions-/Diff-Endpoints für Diagramm & Glossar + DiffPanel verdrahten
**REQ:** neu → REQ-142 · **Größe:** M · **Agent:** S · **Abhängigkeiten:** keine

**Problem:** `api/glossary.ts:46-65` und `api/diagrams.ts:174-194` werfen
„Not Implemented"; `DiffPanel.tsx:15` / `ArtifactDiff.tsx:486` haben
`TODO(backend): wire real diff`; `VersionPanel.tsx:20-24` fällt für diese Typen auf Mock zurück.

**Schritte:**
1. Backend: `GlossaryTermVersion` und `DiagramVersion` existieren bereits als
   immutable Tabellen — nur Endpoints fehlen. `GET …/{pk}/versions/` und
   `GET …/{pk}/diff/?from_version=&to_version=` analog zu den bestehenden
   Requirement-Endpoints (`rest_api/views.py:603,636` als Vorbild) implementieren;
   Diff über `baseline/diff_engine.py` wiederverwenden.
2. Frontend: „Not Implemented"-Stubs in `api/glossary.ts`/`api/diagrams.ts` durch
   echte Calls ersetzen; Mock-Fallback in `VersionPanel.tsx` und die TODOs in
   `DiffPanel.tsx`/`ArtifactDiff.tsx` entfernen.
3. Tests: Backend-API-Tests je Endpoint (Versionen chronologisch, Diff Feld-genau);
   Vitest für VersionPanel/DiffPanel mit den neuen Endpoints.

**Akzeptanz:** Versions- und Diff-Ansicht funktioniert für alle Artefakttypen
inkl. Diagramm/Glossar ohne Mock; REQ-142 → Done.

---

### AP-09 · Status-Modell konsolidieren (Free-Text-Status vs. Workflow-Engine)
**REQ:** neu → REQ-143 · **Größe:** M · **Agent:** S+R · **Abhängigkeiten:** keine, aber **vor AP-10**

**Problem:** `Requirement.status` ist ein freies CharField (default „draft"),
parallel existiert `workflow.WorkflowItemState` als State-Machine — zwei
Wahrheiten für denselben Zustand.

**Schritte (Design-Entscheidung dokumentieren, ADR anlegen):**
1. Zielbild: Workflow-Engine ist die Quelle der Wahrheit; `status` wird zum
   denormalisierten Spiegel (read-only via API), gesetzt ausschließlich durch
   Workflow-Transitions (`workflow/lifecycle_manager.py`).
2. Schreibpfade finden: alle Stellen, die `status` direkt setzen
   (REST-Serializer `serializers.py`, MCP-Tools `requirement.update`) → auf
   Transition-Aufrufe umlenken oder `status` aus writable fields entfernen.
3. Datenmigration: bestehende `status`-Werte auf gültige Workflow-States mappen
   (unbekannte Werte → „draft", Mapping-Tabelle im ADR festhalten).
4. Frontend: Status-Dropdown in `RequirementForm.tsx:403` (u.a. Editors) auf die
   vom Workflow erlaubten Folge-Transitions einschränken (API muss erlaubte
   Transitions liefern — prüfen, ob `workflows/`-Endpoint das schon kann).
5. Tests: direkter Status-Write via API wird abgelehnt/ignoriert; Transition
   aktualisiert beide Repräsentationen konsistent.

**Akzeptanz:** Es gibt genau einen Schreibpfad für Statuswechsel; ADR in
`docs/architecture/` dokumentiert das Mapping; REQ-143 → Done. **Review vor Merge.**

---

### AP-10 · Review-/Approval-UI auf die Workflow-Engine setzen
**REQ:** neu → REQ-144 · **Größe:** L (in 3 Teil-PRs) · **Agent:** S · **Abhängigkeiten:** AP-09

**Problem:** Backend hat Workflow-Engine + Signature-Gate (HMAC-Seal,
Approver-Rolle, TOTP — `backend/workflow/signature_gate.py`), aber es gibt kein
Review-UI; im Frontend existieren nur Status-Werte.

**Teil-PRs:**
1. **AP-10a — API-Vertrag:** Endpoints prüfen/ergänzen: erlaubte Transitions je
   Item, Transition ausführen (mit Credential-Payload fürs Signature-Gate),
   Workflow-Historie je Item (`WorkflowHistoryEntry`). OpenAPI-Schema
   (`drf-spectacular`) aktuell halten. API-Tests.
2. **AP-10b — Review-Ansicht:** Neue Route `/reviews`: Liste aller Items im Zustand
   `in_review` (workspace-gefiltert), Detailansicht mit Artefakt-Inhalt, Diff zur
   letzten approved-Version (nutzt AP-08-Infrastruktur), Aktionen
   Approve/Reject(→draft). Bestehende UI-Muster (`ListToolbar`, Editors-Layout,
   i18n DE/EN, `data-testid`) übernehmen.
3. **AP-10c — Signature-Dialog:** Approve-Aktion öffnet Dialog für
   Passwort/TOTP-Bestätigung → Payload an Transition-Endpoint; Fehlerpfade
   (falsche Credentials, fehlende approver-Rolle) mit klaren Meldungen.
   Historie-Tab am Item zeigt `WorkflowHistoryEntry` inkl. Seal-Status.

**Akzeptanz:** Ein Requirement kann komplett im UI durch
draft→in_review→approved laufen, inkl. Signatur; Playwright-E2E-Szenario dafür;
Vitest für alle neuen Komponenten; REQ-144 → Done.

---

### AP-11 · PDF-Export-Stubs fertigstellen
**REQ:** neu → REQ-145 · **Größe:** S · **Agent:** H · **Abhängigkeiten:** keine

**Problem:** `traceability/vcrm_report_generator.py` wirft für PDF
`NotImplemented`; `application/export_service.py` (PDF-Zweig Z.280-303) teilweise Stub.

**Schritte:** Vorhandene reportlab-Nutzung in `traceability/pdf_report_generator.py`
als Vorbild nehmen; VCRM-PDF (Matrix-Tabelle) und Export-PDF vervollständigen;
Tests: PDF wird erzeugt, ist nicht leer, enthält Stichproben-Strings (pypdf-Extraktion).

**Akzeptanz:** Kein `NotImplemented` mehr in Export-Pfaden; REQ-145 → Done.

---

## Phase 3 — Interoperabilität (SysEng-Kernlücke)

### AP-12 · ReqIF-Export
**REQ:** neu → REQ-146 · **Größe:** L · **Agent:** S+R · **Abhängigkeiten:** keine (Export vor Import)

**Ziel:** Requirements (+ Needs, TraceLinks) eines Workspace als ReqIF 1.2
exportieren, importierbar in DOORS/Polarion.

**Schritte:**
1. Bibliothek: `strictdoc-reqif` bzw. `reqif` (PyPI, LGPL — Lizenz prüfen und im
   PR dokumentieren) statt Eigenbau des XML-Schemas.
2. Neues Modul `application/reqif_export_service.py` nach dem Muster von
   `export_service.py` (COMP-AS-008): Mapping-Tabelle ReqFlow→ReqIF im Modul-Docstring:
   - Requirement/Need → `SPEC-OBJECT` mit `SPEC-OBJECT-TYPE` je Artefakttyp;
     Attribute: uid, title, description (XHTML), status, verification_method,
     moscow_priority, custom_fields.
   - Workspace-/Parent-Hierarchie → `SPECIFICATION` mit `SPEC-HIERARCHY`.
   - TraceLinks → `SPEC-RELATION` mit Typ-Mapping (derives-from, satisfies, verifies, …).
   - Stabile `IDENTIFIER` aus Artifact-UUID (Re-Export ändert IDs nicht).
3. Endpoint `GET /api/v1/workspaces/{pk}/export/reqif/` (analog `CsvExportView`),
   RBAC wie CSV-Export; MCP-Tool optional als Folge-AP.
4. Tests: Roundtrip mit der Bibliotheks-eigenen Parse-Funktion (Export → Parse →
   Objekt-/Relations-Zahlen und Stichproben-Attribute stimmen); Schema-Validierung.
5. Frontend: Export-Button neben CSV-Export (kleiner Teil-PR).

**Akzeptanz:** Exportierte Datei validiert gegen ReqIF-Schema und ist in einem
Fremd-Tool (mind. StrictDoc als Referenz-Parser) lesbar; REQ-146 → Done. **Review vor Merge.**

---

### AP-13 · ReqIF-Import
**REQ:** neu → REQ-147 · **Größe:** L · **Agent:** S+R · **Abhängigkeiten:** AP-12 (nutzt dasselbe Mapping)

**Schritte:**
1. `application/reqif_import_service.py` nach Muster `import_service.py`
   (COMP-AS-009: atomar, Limit, Fehlerliste je Zeile → hier je SPEC-OBJECT).
2. Upsert-Strategie: `IDENTIFIER`-Matching gegen vorhandene UIDs
   (Re-Import aktualisiert statt dupliziert); unbekannte Attribute → custom_fields.
3. Dry-Run-Modus (`?dry_run=true`): Bericht ohne Persistenz.
4. Endpoint `POST /api/v1/workspaces/{pk}/import/reqif/`; Frontend-Anbindung an
   die bestehende `/import`-Seite (`CsvImport` als Vorbild, Teil-PR).
5. Tests: Import des eigenen Exports (Roundtrip verlustfrei für gemappte Felder),
   Import einer Fremd-Fixture, Fehlerfälle (kaputtes XML, unbekannte Typen).

**Akzeptanz:** Roundtrip Export→Import idempotent; Dry-Run liefert korrekten
Bericht; REQ-147 → Done. **Review vor Merge.**

---

## Phase 4 — Schuldenabbau & Restarbeiten

### AP-14 · `rest_api/views.py` zerlegen (4530 Zeilen)
**REQ:** REQ-111 (danach REQ-112 Serializers analog) · **Größe:** L (mechanisch, in Teil-PRs) · **Agent:** H (je Teil-PR) · **Abhängigkeiten:** idealerweise nach AP-10a (vermeidet Konflikte)

**Vorgehen (strikt mechanisch, kein Verhalten ändern):**
1. Paketstruktur `rest_api/views/` anlegen; je Domäne ein Modul
   (`requirements.py`, `needs.py`, `architecture.py`, `testcases.py`,
   `tracelinks.py`, `baselines.py`, `workspaces.py`, `adrs_risks_issues.py`, …).
2. Pro Teil-PR **eine** Domäne verschieben; `rest_api/views/__init__.py`
   re-exportiert alle Namen, damit `urls.py` und Tests unverändert bleiben.
3. Nach jedem Teil-PR: kompletter Backend-Testlauf + `GET /api/v1/schema/`-Diff
   (OpenAPI-Schema muss byte-identisch bleiben — als Regressionstest festhalten).

**Akzeptanz:** Kein Modul >800 Zeilen; OpenAPI-Schema unverändert; alle Tests grün;
REQ-111 → Done (REQ-112 als Folge-AP mit identischem Muster).

---

### AP-15 · Frontend-Monolithe zerlegen
**REQ:** REQ-113 (`CanvasEditor.tsx`), REQ-114 (`SidebarNavigation.tsx`) · **Größe:** M je Datei · **Agent:** S

Gleiche Regel wie AP-14: reine Struktur-Refactorings, ein Teil-PR pro extrahierter
Komponente/Hook, Vitest-Suite als Regressionsnetz, keine Verhaltensänderung
(`data-testid`s stabil halten, damit Playwright grün bleibt).

---

### AP-16 · Rest-Migrationen abschließen (vor RC markiert)
**REQ:** REQ-119 (React-Query, 2 Hooks offen), REQ-120 (Container/Presenter, ~90 %) · **Größe:** S · **Agent:** H

REQ-119/120 in REQUIREMENTS.md nennen die offenen Stellen; verbleibende Hooks auf
TanStack Query umstellen (Muster: `useRequirementData.ts`), letzte
Container/Presenter-Splits nachziehen. Akzeptanz: keine Direkt-Fetches außerhalb
der Query-Hooks mehr (grep-Check), REQ-119/120 → Done.

---

### AP-17 · Multi-Worker-Cache-Invalidierung & Tenancy-Rest
**REQ:** REQ-118, REQ-121 · **Größe:** M · **Agent:** S+R

1. REQ-118: Cache-Invalidierung (u.a. `se_metrics.MetricCache`) über Redis-Pub/Sub
   oder Redis-basierten Cache statt Prozess-lokal — sonst ist Skalierung auf >1
   Gunicorn-Worker/Container unsicher. Test mit zwei Prozessen (pytest-xdist-Szenario oder Integrationstest).
2. REQ-121: hardcodiertes `DEFAULT_TENANT_ID=1` eliminieren; Tenant-Kontext
   überall aus `auth_tenancy/context.py` beziehen; Testfall mit zweitem Tenant
   (Isolation: Tenant B sieht keine Artefakte von Tenant A).

---

### AP-18 · Backlog-Triage REQUIREMENTS.md
**REQ:** — (Prozess) · **Größe:** S · **Agent:** H · **Laufend nach jeder Phase**

~94 von 139 REQs stehen auf „Active". Aufgabe: je REQ prüfen, ob im Code bereits
umgesetzt (git log / Tests als Beleg) → Status auf Done mit Commit-Referenz;
echte Duplikate zusammenführen; Rest nach P0–P3 priorisieren. Ergebnis: eine
ehrliche, priorisierte Restliste als Steuerungsinstrument.

---

## Hinweise für die Agenten-Übergabe

1. **Ein AP pro Agent-Session**, Prompt = der jeweilige AP-Abschnitt dieses Dokuments
   (er ist selbsttragend: Problem, Dateien, Schritte, Akzeptanz).
2. **Reihenfolge:** Phase 0 zuerst; innerhalb der Phasen gilt die
   Abhängigkeits-Spalte. AP-01, AP-04, AP-07, AP-11, AP-16, AP-18 sind die
   „billigsten" Einstiege (Haiku-tauglich, klein, risikoarm).
3. **S+R-Pakete** (AP-03, AP-09, AP-12, AP-13, AP-17) vor dem Merge durch ein
   stärkeres Modell oder einen Menschen reviewen lassen — sie berühren Security,
   Datenmigrationen oder öffentliche Schnittstellen.
4. Jeder Agent aktualisiert am Ende `docs/REQUIREMENTS.md` (Status + ggf. neue
   REQ-IDs ab REQ-141 gemäß diesem Plan) — das hält die Traceability-Kette intakt.
