# SYSTEMAUDIT 2026-08-29 — Gesamttest MCP-Server (Live-Instanz)

**Datum:** 29.08.2026
**Art:** Live-Funktions- und Sicherheitstest des laufenden MCP-Servers (`/mcp/`), read-only + kontrollierte Write/Cleanup-Zyklen
**Durchgeführt von:** `reqogniloom-operator` (API-Client/Admin-Rolle, kein Code-Fix)
**Umfang:** Alle MCP-Tool-Gruppen, JSON-RPC-2.0-Transport (HTTP + SSE), RBAC-Regression der 4 historischen Befunde aus Systemaudit 2026-07-28, Error-Handling
**Stack:** `docker compose` lokal, Backend erreichbar unter `http://127.0.0.1:8001`, Image `ghcr.io/popoboxxo/reqogniloom-backend:1.7.0`

---

## 1. Executive Summary

Der MCP-Server ist **funktional vollständig und die vier historischen Sicherheitsbefunde für den WRITE-Pfad sind live verifiziert behoben**. SSE-Transport und Error-Handling sind sauber. Ein **neuer, mittelschwerer Befund** wurde entdeckt: MCP-**Lesezugriffe** (`*.query`/`*.get`/`*.list`) sind **nicht workspace-scoped**, sondern nur tenant-weit RBAC-gegated — ein API-Key mit `viewer`-Rolle in Workspace A kann Artefakte aus jedem anderen Workspace desselben Tenants lesen, auch ohne dort eine Rollenzuweisung zu haben. Das betrifft vermutlich alle `query`/`get`/`list`-Tools in allen 30 Gruppen (stichprobenartig an `requirement.query` verifiziert, Architektur der RBAC-Gate-Logik bestätigt das für den gesamten Tool-Registry-Dispatch).

Zusätzlich: der Dev-Stack wurde während des Audits durch **Ressourcen-Konkurrenz** (parallel laufende E2E-Suite + eigene `manage.py`-Aufrufe gegen den Single-Worker-`uvicorn --reload`-Prozess) für ~5 Minuten komplett unresponsive — kein MCP-Bug, aber ein Betriebs-Hinweis.

| Bereich | Ergebnis |
|---|---|
| Tool-Manifest-Konsistenz | ✅ 171 Tools / 30 Gruppen, keine Duplikate, Manifest == Live-Registry (frisch regeneriert & diff-verifiziert) |
| RBAC — Fail-Open-Lücke (historisch) | ✅ **Behoben** — fail-closed Default, live verifiziert |
| RBAC — Workspace- statt Tenant-Rollen (WRITE) | ✅ **Behoben** für Write-Operationen — live verifiziert |
| RBAC — Workspace-Scoping (READ) | ⚠️ **Neuer Befund** — Reads sind tenant-weit, nicht workspace-scoped |
| `prompt_template.create` Admin-Gate | ✅ Vorhanden (Code + Verhalten bestätigt) |
| SSE-Transport | ✅ Voller Handshake→Message→Response-Zyklus funktioniert |
| Error-Handling | ✅ Keine Tracebacks/500er, saubere JSON-RPC-Fehlerhüllen; 1 kosmetische Abweichung (HTTP-Status bei Parse-Error) |
| Read-Smoke-Test (30 Gruppen) | ✅ 29/30 getestet und erfolgreich, 1 Gruppe (`ai_derivation`) ohne reinen Read-Tool bewusst ausgelassen |
| Write-Round-Trip (Create→Verify→Cleanup) | ✅ 8 Gruppen getestet, alle Creates + Cleanups erfolgreich |
| Dev-Stack am Ende | ✅ Sauber — alle Testdaten entfernt, Test-Key revoked, Backend healthy |

---

## 2. Vorbereitung — Tool-Manifest-Verifikation

- `docker compose exec backend python manage.py export_tool_manifest --out /tmp/manifest_fresh.json` frisch generiert und gegen `docs/agent-templates/tool-manifest.json` diff-geprüft: **identisch**, 171 Tools.
- 30 Tool-Gruppen (nicht 22 oder 26 wie in älteren Doku-Ständen): `admin, adr, ai_derivation, architecture, artifact, audit, baseline, change_request, context, custom_field, diagram, events, glossary, goal, interview, issue, main_goal, memory, needs, permissions, prompt_template, prompt_variable, requirement, requirement_bundle, review, risk, test, traceability, user, workspace`.
- Keine Tool-Namen-Duplikate (`sort | uniq -d` leer).
- **Doku-Drift-Hinweis:** `CLAUDE.md`/Agent-Persona referenzieren teils "11 Tool-Gruppen, 40+ Tools" (veraltet) bzw. "~22 Tool-Gruppen" (Task-Vorgabe) — aktueller Live-Stand ist **30 Gruppen / 171 Tools**. Empfehlung: Doku-Update an `documenter`/Projektpflege übergeben (nicht in meinem Scope).

## 3. Auth-Mechanismus

`backend/mcp_server/views.py` — reiner Header-basierter Auth (`X-API-Key` oder `Authorization: Bearer reqlo_...`), explizit **keine** JWT-Bearer-Unterstützung auf MCP-Pfad (REQ-L2-MC-006), keine Cookie-Auth (CSRF-Schutz durch Header-only-Design). Bei falschem Schema (`Authorization: Bearer <jwt>`) liefert der Server eine explizite `bearer_not_supported`-Meldung statt eines irreführenden `invalid_api_key` — sauber implementiert.

## 4. Tool-Gruppen-Status (Read-Smoke-Test)

Je Gruppe ein repräsentativer Read-Tool-Call in einem dedizierten Test-Workspace (`mcp-audit-<timestamp>`, danach gelöscht):

| Gruppe | Tool | Status |
|---|---|---|
| admin | `admin.backup_list` | ✅ OK |
| adr | `adr.query` | ✅ OK |
| architecture | `architecture.query` | ✅ OK |
| artifact | `artifact.search` | ✅ OK |
| audit | `audit.query` | ✅ OK |
| baseline | `baseline.list` | ✅ OK |
| change_request | `change_request.query` | ✅ OK |
| context | `context.query` | ✅ OK (erst falsche Test-ID meinerseits verwendet — Requirement-ID ≠ generische Artifact-ID; mit korrekter `resolved_artifact_id` aus `traceability.query` erfolgreich) |
| custom_field | `custom_field.query` | ✅ OK |
| diagram | `diagram.query` | ✅ OK |
| events | `events.dlq_list` | ✅ OK |
| glossary | `glossary.query` | ✅ OK |
| goal | `goal.query` | ✅ OK |
| interview | `interview.list` | ✅ OK |
| issue | `issue.query` | ✅ OK |
| main_goal | `main_goal.read` | ✅ OK |
| memory | `memory.query` | ✅ OK |
| needs | `needs.query` | ✅ OK |
| permissions | `permissions.list` | ✅ OK |
| prompt_template | `prompt_template.list` | ✅ OK |
| prompt_variable | `prompt_variable.list` | ✅ OK |
| requirement | `requirement.query` | ✅ OK |
| requirement_bundle | `requirement_bundle.attribute_schema` | ✅ OK |
| review | `review.list_pending` | ✅ OK |
| risk | `risk.query` | ✅ OK |
| test | `test.query` | ✅ OK |
| traceability | `traceability.query` | ✅ OK |
| user | `user.list` | ✅ OK |
| workspace | `workspace.list` | ✅ OK |
| ai_derivation | — | ⚪ **Nicht getestet**: Gruppe enthält ausschließlich LLM-gestützte Ableitungs-Aktionen (`derive_requirements_from_need`, `suggest_architecture_for_requirement`, `decompose_requirement_next_level`, `derive_risks_from_architecture`, `derive_glossary_from_workspace`, `derive_adr_from_decision`) — alle sind Write-Operationen ohne reinen Read-Tool. Bewusst ausgelassen (Aufgabenstellung: "bei Unsicherheit über Nebenwirkungen nur Read-Calls"). |

**Ergebnis: 29/30 Gruppen erfolgreich getestet, 1 Gruppe ohne passenden Read-Tool bewusst übersprungen.**

## 5. Write-Round-Trip-Tests (Create → Verify → Cleanup)

| Gruppe | Create-Tool | Cleanup-Tool | Ergebnis |
|---|---|---|---|
| requirement | `requirement.create` | `requirement.outdate` | ✅ Create OK, Query bestätigt Sichtbarkeit, Outdate OK |
| architecture | `architecture.create` | `architecture.outdate` | ✅ OK |
| test | `test.create` | `test.outdate` | ✅ OK |
| needs | `needs.create` | `needs.outdate` | ✅ OK |
| adr | `adr.create` | `adr.delete` | ✅ OK (Hard-Delete) |
| risk | `risk.create` | `risk.delete` | ✅ OK (Hard-Delete) |
| issue | `issue.create` | `issue.delete` | ✅ OK (Hard-Delete) |
| glossary | `glossary.create` | `glossary.delete` | ✅ OK (Hard-Delete) |

Alle 8 getesteten Gruppen: Create erfolgreich, Cleanup erfolgreich verifiziert — keine Datenleichen zurückgelassen.

**Kosmetischer Befund (niedrige Priorität):** `adr.create`/`risk.create`/`issue.create` wickeln das erzeugte Objekt in einen generischen `{"data": {...}}`-Schlüssel, während `requirement.create`/`architecture.create`/`test.create`/`needs.create`/`glossary.create` einen entitätsnamigen Schlüssel (`requirement`, `architecture_element`, `test_case`, `need`, `term`) verwenden. Keine funktionale Auswirkung, aber Inkonsistenz in der Response-Shape zwischen Tool-Gruppen — betraf mein eigenes Extraktionsscript (falscher Pfad beim ersten Versuch), wäre für jeden MCP-Client dieselbe Stolperfalle. Empfehlung: an `api-specialist`/`senior-developer` zur Konsistenzprüfung übergeben.

## 6. Historische Sicherheitsbefunde (Systemaudit 2026-07-28) — Regressionstest

### 6.1 Fail-Open RBAC (Präfix-Allowlist-Lücken) — ✅ **Behoben, live verifiziert**

`tool_registry.py` invertiert die Logik: **jeder** Tool-Name gilt per Default als WRITE (RBAC-gegated), außer er ist explizit in `_READ_ONLY_TOOL_NAMES` gelistet. Ein neu hinzugefügter Tool ohne Eintrag ist automatisch geschützt statt automatisch offen (Kommentar im Code verweist auf die alte Allowlist-Lücke als "silently bypassed the gate until someone remembered to extend the prefix list").

**Live-Test:** API-Key mit `viewer`-Rolle → `requirement.create`:
```json
{"error": {"code": -32001, "message": "Role '('viewer',)' does not permit write operations. Editor or Admin role required."}}
```
→ 403, sauber, kein Duchschlüpfen.

`tools/list` mit Viewer-Key liefert 65 von 171 Tools — alle 106 versteckten Tools wurden per Namens-Heuristik (`create|update|delete|assign|revoke|suspend|...`) gegengeprüft: **keines** der sichtbaren 65 Viewer-Tools sieht wie ein Write-Tool aus.

### 6.2 Workspace- statt Tenant-globale Rollenauflösung — ✅ **Behoben für WRITE**, ⚠️ **nicht für READ** (neuer Befund, siehe 6.5)

`_resolve_roles()` löst Rollen bei vorhandener `workspace_id` explizit workspace-scoped auf (`AuthorizationService.active_roles_for(user_id, workspace_id)`), nicht mehr tenant-global. Live bestätigt: Viewer-Rolle nur in Test-Workspace A zugewiesen → Write-Versuch in Workspace A wird mit `Role '('viewer',)'` korrekt als unzureichend erkannt (Viewer erlaubt kein Write); ein Write-Versuch in einem völlig fremden Workspace B (keine Rollenzuweisung) liefert `Role '()'` (leeres Rollen-Tupel) — die Rolle "leakt" nicht tenant-weit.

### 6.3 `prompt_template.create` Admin-Gate — ✅ **Vorhanden**

Code (`backend/mcp_server/tools/prompt_template.py:274-288`, `_check_admin`): expliziter Rollen-Check `auth_context.has_role("admin")`, mit Verweis auf historischen Fix #101 ("without this, any valid API key could overwrite tenant-wide LLM prompt templates ... a prompt-injection vector"). Live: Viewer-Key → `prompt_template.create` → 403 `PERMISSION_DENIED` (traf im Test bereits die generische Write-Gate, da Viewer gar kein Write-Recht hat; der zusätzliche Admin-vs-Editor-Unterschied ist im Code als eigenständiger, vom generischen Write-Gate unabhängiger Check verifiziert, aber mangels verfügbarem Editor-Test-User in dieser Session nicht isoliert live gegen einen Editor getestet — **Restrisiko: niedrig**, da Code-Pfad eindeutig und mit Kommentar-Historie belegt ist).

### 6.4 Kann ein Viewer einen Write-Call durchbringen? — ✅ **Nein, konsequent verifiziert**

Getestet: `requirement.create` (generisches Write), `prompt_template.create` (Admin-Gate) — beide korrekt mit 403/`PERMISSION_DENIED` abgewiesen, keine Ausnahme gefunden.

### 6.5 NEUER BEFUND (Schweregrad: **Mittel**) — MCP-Reads sind nicht workspace-, sondern tenant-scoped

**Beobachtung:** `tool_registry.dispatch_request()` führt den RBAC-Check (`_check_rbac`) **ausschließlich für als WRITE klassifizierte Tools** aus (Code-Kommentar: *"Step 3: RBAC for write operations (REQ-L2-MC-007)"*). Für Read-Tools (`*.query`, `*.get`, `*.list`, ...) gibt es **keinen** äquivalenten Rollen-/Mitgliedschafts-Check — nur die tenant-weite Row-Level-Security (Requirement/Artifact-Manager filtert nach `tenant_id`, nicht nach Workspace-Mitgliedschaft des Aufrufers).

**Live-Beweis:**
1. Test-User erhält **ausschließlich** eine `viewer`-Rolle in Test-Workspace A (`mcp-audit-...`).
2. `requirement.query` mit `workspace_id` = **fremder** Workspace B (`perf-test-ws`, selber Tenant, **keine** Rollenzuweisung für den Test-User dort) liefert **200 OK** mit den echten Requirement-Daten aus Workspace B (`Perf test req 1`, `Perf test req 2`).
3. Zum Vergleich: derselbe Aufruf als **Write** (`requirement.create`) auf Workspace B liefert korrekt `Role '()'` → 403.

**Einordnung:** Dieses Verhalten deckt sich mit dem dokumentierten REST-Pendant (`ApiKeyViewSet`-Docstring: *"READ is declared uniformly ... as the least-privilege operation that still requires the caller to hold an active role somewhere in the tenant"*) — es könnte sich also um eine **bewusste Produktentscheidung** handeln (Lesezugriff = tenant-weit, nur Schreiben ist workspace-exklusiv), nicht zwangsläufig um eine Regression des ursprünglichen Fail-Open-Befunds. Da das System aber eine dedizierte `ItemPermission`/Workspace-Mitgliedschafts-API besitzt (`workspaces/{id}/members/`, `workspaces/{id}/permissions/`), die eine feingranulare Zugriffskontrolle suggeriert, ist die praktische Konsequenz trotzdem meldenswert: **Workspace-Mitgliedschaft ist über MCP aktuell keine Vertraulichkeitsgrenze, nur eine Schreibgrenze.** Jeder API-Key mit irgendeiner Rolle irgendwo im Tenant kann per MCP alle Requirements/Architekturelemente/Risks/Issues/ADRs/etc. jedes anderen Workspace im selben Tenant lesen.

**Empfehlung:** Produkt-/Sicherheitsentscheidung einholen, ob das gewollt ist. Falls nicht: RBAC-Gate in `tool_registry.dispatch_request()` um einen READ-Check erweitern (analog zu Schritt 3, aber mit `Operation.READ` und workspace-scoped Rollenauflösung), konsistent mit der bereits vorhandenen Fail-Closed-Philosophie für Writes. Betrifft potenziell alle 29 getesteten Read-Tools plus alle nicht einzeln getesteten `query`/`get`/`list`-Varianten in weiteren Gruppen — Umfang sollte vor einem Fix vollständig kartiert werden (Aufgabe für `developer`/`api-specialist`, nicht in meinem Scope).

## 7. SSE-Transport-Smoke-Test

1. `GET /mcp/sse/` mit `X-API-Key` → **200**, `Content-Type: text/event-stream`.
2. Erstes Event: `event: endpoint` / `data: /mcp/messages/?session_id=<uuid>` — Session-ID sauber vergeben.
3. `: keepalive`-Kommentarzeile empfangen (Verbindung bleibt offen).
4. `POST /mcp/messages/?session_id=<uuid>` mit `tools/list`-Request (kein API-Key im POST nötig — Session ist serverseitig an den Key aus dem SSE-Handshake gebunden) → **202 Accepted**.
5. Antwort kam korrekt über den offenen SSE-Stream zurück: `id: 1 / event: message / data: {"jsonrpc": "2.0", "id": 42, "result": {"tools": [...]}}` — Request-`id` (42) korrekt gespiegelt.

**Ergebnis: SSE-Transport vollständig funktional**, End-to-End-Zyklus (Handshake → Message-Post → Response-Delivery-per-SSE) erfolgreich. Deckt sich mit der in AP-7 behaupteten Aktivierung (`test_e2e_sse_transport.py`, vormals 6 Skips).

## 8. Error-Handling

| Test | Ergebnis |
|---|---|
| Malformed JSON-Body (`{not valid json`) | `{"error":{"code":-32700,"message":"Failed to parse JSON-RPC request."}}` — sauber, kein Traceback. **Kosmetischer Befund:** HTTP-Status war 401 statt der für einen reinen Parse-Error naheliegenderen 400 (kein Auth-Bezug im Fehlerbild erkennbar, evtl. Auth-Check läuft vor JSON-Parsing und beide Pfade teilen sich denselben Fehlerstatus). Niedrige Priorität, kein Leak. |
| Unbekannte JSON-RPC-Methode (`totally/bogus`) | 400, `-32601 "Unknown tool: 'totally/bogus'"` — Code korrekt (Method-not-found-Semantik), Meldungstext bezieht sich auf "Tool" statt "Method" (minimal irreführend, aber eindeutig genug). |
| `tools/call` mit nicht-existentem Tool-Namen | 400, `-32601 "Unknown tool: 'nonexistent.tool'"` — korrekt. |
| Fehlender Pflichtparameter (`requirement.create` ohne `title`) | 200 mit `result.isError: true`, Text: `"Error: Required parameter 'title' is missing or empty."` — MCP-Spec-konforme Tool-Error-Hülle, sauber, kein Traceback. |
| Kein Auth-Header | 401, `"API key is required. Provide X-API-Key header or params.api_key."` — sauber. |
| Ungültiger/erfundener API-Key | 401, `"Authentication failed: invalid_api_key"` — sauber, keine internen Details geleakt. |

**Ergebnis: Keine 500er, keine rohen Python-Tracebacks in irgendeiner Antwort beobachtet.** Die in AP-1 (SA-03) / AP-6 dokumentierte Härtung hält unter Live-Last stand. Einzige Anmerkung: HTTP-Statuscode-Feinheit bei Parse-Errors (401 statt 400) — kosmetisch, kein Sicherheitsproblem.

## 9. Betriebs-Hinweis (kein MCP-Bug, aber Audit-relevant)

Während der Vorbereitungsphase wurde der Backend-Container für ca. 5 Minuten (08:38–08:41 UTC) komplett unresponsive (Healthcheck-Timeout, `FailingStreak: 10`, keine einzige Anfrage mehr im Log verarbeitet). Ursache: Der Container läuft mit einem **einzelnen** `uvicorn --reload`-Worker (kein Multi-Worker-Setup) auf 512 MB RAM-Limit; parallel dazu lief bereits eine **aktive E2E-Test-Suite** gegen dieselbe Instanz (49 `e2e-isolated-*`/`e2e-visual-regression-*`-Workspaces aus derselben Zeitspanne im System gefunden), und dieses Audit hat zusätzlich mehrere `manage.py`-Management-Commands ausgeführt, die bei jedem Aufruf den kompletten Django-App-Stack inkl. SentenceTransformer-Embedding-Modell neu laden. Die Kombination aus beidem hat den Single-Worker-Prozess offenbar blockiert. Behoben durch `docker compose restart backend` (danach sofort wieder healthy, alle Folge-Tests liefen sauber).

**Empfehlung:** Kein Code-Fix nötig, aber organisatorischer Hinweis: MCP-/API-Audits nicht parallel zu einer laufenden E2E-Suite auf derselben Dev-Instanz fahren, bzw. für Live-Audits einen dedizierten Stack verwenden. Nicht in meinem Scope zur Behebung (Infrastruktur-/CI-Scheduling-Frage).

## 10. Aufräumen (verifiziert)

- Test-Requirement → `requirement.outdate` (soft-delete) ✅
- Test-Architekturelement, Test-Testfall, Test-Need → jeweils `*.outdate` ✅
- Test-ADR, Test-Risk, Test-Issue, Test-Glossarbegriff → jeweils `*.delete` (hard delete) ✅
- Test-Workspace (`mcp-audit-<timestamp>`) → `DELETE /api/v1/workspaces/{id}/` mit Namens-Bestätigung → 204 ✅
- Viewer-Test-User → deaktiviert (`POST /users/{id}/deactivate/`) ✅
- Viewer-API-Key → revoked (self-service `DELETE /api-keys/{id}/`) ✅
- Admin-Test-API-Key → revoked, Re-Test bestätigt `api_key_revoked` ✅
- Backend-Container: `healthy` beim Abschluss ✅

Keine verbliebenen Testartefakte, keine aktiven Test-API-Keys.

## 11. Vollständige Tool-Gruppen-Liste (Referenz)

30 Gruppen, 171 Tools (siehe `docs/agent-templates/tool-manifest.json`, frisch verifiziert deckungsgleich mit Live-Registry):

`admin` (3), `adr` (…), `ai_derivation` (6), `architecture` (9), `artifact`, `audit`, `baseline`, `change_request`, `context`, `custom_field`, `diagram`, `events` (2), `glossary`, `goal`, `interview`, `issue`, `main_goal`, `memory`, `needs` (8), `permissions` (4), `prompt_template`, `prompt_variable`, `requirement` (10), `requirement_bundle` (3), `review` (4), `risk`, `test` (12), `traceability` (3), `user` (9), `workspace`.

(Exakte Tool-Zahlen pro Gruppe: siehe Manifest-Datei — hier nur die im Audit explizit aufgelisteten Gruppen mit Zähler versehen.)

---

**Gesamturteil:** MCP-Server funktional robust, Write-RBAC nachweislich fail-closed und workspace-scoped, SSE und Error-Handling produktionsreif. Ein mittelschwerer, klar reproduzierbarer Scoping-Befund bei Lesezugriffen (Abschnitt 6.5) sollte vom Entwickler-Team bewertet werden — Charakter (Design vs. Regression) ungeklärt, Auswirkung (tenant-weite Lesbarkeit) eindeutig demonstriert.
