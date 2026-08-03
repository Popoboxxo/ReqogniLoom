# Systemaudit ReqogniLoom

**Prüfdatum:** 2026-08-03  
**System:** ReqogniLoom  
**Prüfumfang:** Backend, REST API, MCP Server, Frontend, laufende Instanz, UI-Konzept  
**Referenzdokument:** `docs/UI_KONZEPT.md`, Stand 2026-07-31  
**Prüfergebnis:** Nicht releasefähig ohne Behebung der kritischen Sicherheits- und Betriebsbefunde

## 1. Management Summary

Das System ist funktional weit entwickelt und besitzt bereits zahlreiche gemeinsame UI-Primitives, eine umfangreiche REST-API sowie eine große MCP-Tool-Landschaft. Die Grundarchitektur ist erkennbar und mehrere ursprüngliche UI-Probleme wurden behoben.

Gleichzeitig bestehen kritische Abweichungen zwischen Zielbild, Implementierung und laufender Umgebung. Die wichtigsten Risiken sind:

1. Die laufende API zeigt bei einem nicht gefundenen Pfad eine vollständige Django-Debug-Seite.
2. Der Metrics-Bereich akzeptiert jeden nichtleeren `Authorization`-Header und verwendet einen festen Default-Tenant.
3. Ein API-Key wurde außerhalb eines sicheren Secrets-Kontexts offengelegt und muss widerrufen werden.
4. Die dokumentierten Metrics-Workspace-Endpunkte sind nicht korrekt registriert.
5. MCP stellt deutlich mehr Funktionen bereit als die UI. Dadurch können Agenten Daten erzeugen oder verändern, die normale Nutzer nicht vollständig sehen oder verwalten können.
6. MCP verwendet innerhalb fachlich ähnlicher Update-Operationen unterschiedliche Payload-Formate.
7. Das UI-Konzept ist bei benannten Themes, Fehlerkommunikation, Typografie, responsiven Regeln und automatischer Durchsetzung noch nicht vollständig umgesetzt.

Die Anwendung ist daher als Entwicklungs-/Pilotstand brauchbar, aber nicht als sicherer Produktionsstand einzustufen.

## 2. Prüfmethodik und Einschränkungen

Geprüft wurden:

- `docs/UI_KONZEPT.md`
- `frontend/src/`
- `backend/`
- `e2e/`
- REST-Routing und OpenAPI-Schema
- MCP-Tool-Registry und Toolgruppen
- Laufende Frontend-Instanz auf Port `5173`
- Laufende API auf Port `8001`
- Health- und Authentifizierungsverhalten per HTTP

Die laufende Frontend-Instanz lieferte erfolgreich den Vite-HTML-Shell mit HTTP 200. Eine pixelgenaue Browser- und Mobile-Prüfung mit Playwright war nicht möglich, weil auf der Prüfmaschine die Chromium-Distribution fehlte. Deshalb beruhen die UI-Befunde auf Quellcodeanalyse, vorhandenen Tests, dem ausgelieferten HTML und dem statischen Abgleich mit dem Konzept. Die fehlende Browserausführung ist selbst eine Testinfrastruktur-Lücke und kein Nachweis für korrektes visuelles Verhalten.

Es wurden keine schreibenden API-Operationen gegen produktive Daten ausgeführt.

## 3. Reproduzierte Laufzeitbefunde

### 3.1 Kritisch: Django-Debug-Seite auf der laufenden API

Der Aufruf eines nicht registrierten Metrics-Pfades lieferte eine Django-Debug-Fehlerseite. Die Antwort enthielt unter anderem die vollständige URL-Auflistung und den Hinweis, dass `DEBUG = True` aktiv ist.

Beispielpfad:

```text
/api/v1/metrics/workspace/not-a-uuid/
```

Betroffene Konfiguration:

- `backend/reqogniloom/settings.py`
- laufende Deployment-Umgebung

Risiken:

- Offenlegung interner Routen
- Offenlegung von Framework- und Implementierungsdetails
- Offenlegung von Stacktraces bei zukünftigen Fehlern
- bessere Vorbereitung gezielter Angriffe

Maßnahme:

- `DEBUG=False` im Deployment erzwingen
- Deployment beim Start mit `manage.py check --deploy` prüfen
- Debug-Seiten in Smoke-Tests ausdrücklich verbieten

### 3.2 Positiv: Health-Endpunkt

```text
GET /health/ -> HTTP 200
```

Die Datenbank wurde als erreichbar gemeldet. Der Health-Endpunkt prüft jedoch nur den vorhandenen Umfang der Checks; Redis, Celery, MCP-Erreichbarkeit und externe Abhängigkeiten sind in der Antwort nicht ersichtlich.

### 3.3 Positiv: REST-Authentifizierung außerhalb Metrics

Ein REST-Aufruf ohne Credentials wurde mit HTTP 403 abgewiesen. Ein syntaktisch ungültiger Bearer-Token wurde mit HTTP 401 und `invalid_token` abgewiesen.

Diese positive Beobachtung gilt nicht für den separat implementierten Metrics-View, der eigene Authentifizierungslogik verwendet.

### 3.4 Frontend-Shell erreichbar, aber keine visuelle Live-Abnahme

```text
GET http://<host>:5173/ -> HTTP 200
```

Das ausgelieferte statische HTML verwendet `lang="en"`. Ob der Wert zur Laufzeit durch die i18n-Initialisierung geändert wird, konnte ohne Browserausführung nicht bestätigt werden.

### 3.5 MCP-Verbindungsdiagnose und OpenCode-Konfiguration

Die ursprüngliche Verbindungskonfiguration verwendete die Umgebungsvariable
`MCP_REQOGNILOOM_URL`. Die lokale Konfiguration dieser Variable zeigte auf den
Frontend-Port `5173`. Dieser Port liefert ausschließlich die React/Vite-Anwendung und
ist kein MCP-Endpunkt.

Der tatsächlich laufende MCP-Server befindet sich auf der API unter:

```text
http://172.20.5.120:8001/mcp/
http://172.20.5.120:8001/mcp/sse/
```

Die OpenCode-Projektkonfiguration wurde deshalb in `opencode.json` auf folgende
Verbindung korrigiert:

```json
{
  "mcp": {
    "reqogniloom": {
      "type": "remote",
      "enabled": true,
      "oauth": false,
      "url": "http://172.20.5.120:8001/mcp/sse/",
      "headers": {
        "Authorization": "Bearer {env:MCP_REQOGNILOOM_API_KEY}"
      }
    }
  }
}
```

Reproduzierte Ergebnisse:

| Prüfung | Ergebnis | Bedeutung |
|---|---:|---|
| `GET /mcp/` ohne Authentifizierung | HTTP 200 | Server erreichbar, Serverinformationen werden ausgeliefert |
| `GET /mcp/sse/` ohne Authentifizierung | HTTP 401 | Authentifizierung wird am SSE-Handshake verlangt |
| Frontend `GET /` | HTTP 200 | UI-Server erreichbar |
| API `GET /health/` | HTTP 200 | API und Datenbank grundsätzlich erreichbar |

Die Verbindung war daher nicht primär ein Netzwerkproblem. Die Ursachen waren:

1. falscher Zielport in der OpenCode-Konfiguration
2. fehlende API-Key-Umgebungsvariable im OpenCode-Prozess
3. korrekte Authentifizierung am SSE-Endpunkt war erforderlich
4. Browser-/Chromium-Fehlen betraf nur die UI-Prüfung und nicht die MCP-Verbindung

Bei der weiteren Diagnose wurde ein zusätzlicher Konfigurationsfehler gefunden: Der
API-Key war zwischenzeitlich fälschlich innerhalb des Ausdrucks
`{env:...}` eingetragen. Dadurch interpretierte OpenCode den kompletten Key als Namen
einer Umgebungsvariable und übergab keinen gültigen Header. Der Eintrag wurde auf die
Variable `MCP_REQOGNILOOM_API_KEY` korrigiert. Der zuvor im Klartext eingetragene Key
muss aus Sicherheitsgründen widerrufen werden.

Die lokale Prüfung mit `opencode mcp list` ergab nach der Korrektur:

```text
reqogniloom: failed
SSE error: Non-200 status code (401)
```

Das bestätigt, dass URL und Transport jetzt erreicht werden; die Umgebungsvariable ist
im OpenCode-Prozess jedoch noch nicht gesetzt. Die verbleibende 401 ist daher ein
fehlender Authentifizierungswert und kein Netzwerk- oder Routingfehler.

Vor dem OpenCode-Start muss der Schlüssel als Prozessvariable gesetzt werden, ohne ihn
in `opencode.json`, Git, Logs oder Dokumentation abzulegen:

```powershell
$env:MCP_REQOGNILOOM_API_KEY = "<lokal einzusetzender API-Key>"
opencode
```

Bei einer späteren Konfigurationsprüfung war der Schlüssel erneut direkt in
`opencode.json` innerhalb eines ungültigen Ausdrucks (`{...}` ohne `env:`-Präfix)
eingetragen. Dadurch wurde kein gültiger Umgebungsvariablenwert interpoliert. Der
Header wurde deshalb auf `X-API-Key: {env:MCP_REQOGNILOOM_API_KEY}` korrigiert. Der
zwischenzeitlich im Klartext konfigurierte Schlüssel muss widerrufen werden.

Nach Änderungen an `opencode.json` muss OpenCode vollständig beendet und neu gestartet
werden, da MCP-Konfigurationen beim Start geladen werden.

### 3.6 Mittel: MCP-Serverinformationen widersprechen dem tatsächlichen Transport

`GET /mcp/` meldet aktuell:

```json
{"transports": ["http", "stdio"]}
```

Der Server besitzt jedoch zusätzlich eine funktionierende SSE-Route unter
`/mcp/sse/`. Dadurch ist die Transportbeschreibung unvollständig bzw. irreführend.

Betroffene Stellen:

- `backend/mcp_server/views.py:210-212`
- `backend/mcp_server/urls.py:22-25`
- `opencode.json`
- `README.md:820-823`

Empfehlung:

- Servermetadaten um `sse` ergänzen, falls SSE der unterstützte Remote-Transport ist.
- Alternativ die Dokumentation und Clientbeispiele konsequent auf HTTP oder SSE
  beschränken.
- stdio nur bewerben, wenn ein tatsächlich startbarer stdio-Entrypoint existiert.

## 4. Kritische Sicherheits- und Mandantenbefunde

### 4.1 Kritisch: Metrics-Authentifizierung ist nur ein Header-Präsenzcheck

`backend/se_metrics/views.py:91-97` prüft ausschließlich, ob ein nichtleerer `Authorization`-Header vorhanden ist. `authentication_classes` und `permission_classes` sind in `:122-123` leer.

Damit wird kein JWT, kein API-Key und keine Benutzeridentität validiert. Ein beliebiger Wert im Header genügt, um die Prüfung zu passieren.

### 4.2 Kritisch: Metrics verwendet einen festen Default-Tenant

`backend/se_metrics/views.py:66-88` setzt den Tenant aus `DEFAULT_TENANT_ID`. In `backend/reqogniloom/settings.py:591-593` ist dieser standardmäßig Tenant `1`.

Die Anfrageidentität wird nicht verwendet, um den Tenant sicher aufzulösen. Das widerspricht der vorgesehenen Row-Level-Isolation.

Risiko:

- tenantübergreifende Datenzugriffe
- falsche Metriken bei mehreren Mandanten
- potenziell unautorisierte Threshold-Änderungen

### 4.3 Kritisch: API-Key-Exposure

Ein API-Key wurde in der Aufgabenkommunikation übermittelt. Zusätzlich wurde ein `reqlo_`-Wert in `.meta-config/secrets.local.yaml` gefunden.

Der Wert wird bewusst nicht in diesem Bericht wiederholt.

Maßnahmen:

1. alle betroffenen Schlüssel widerrufen
2. neue Schlüssel ausstellen
3. Git-Historie und Logs auf frühere Vorkommen prüfen
4. Secrets-Dateien aus Versionierung und Artefakten ausschließen
5. Secret-Scanning für `reqlo_`-Muster aktivieren

## 5. API- und Routingbefunde

### 5.1 Hoch: Dokumentierte Metrics-Workspace-Routen fehlen

`backend/se_metrics/views.py:8-18` dokumentiert Workspace-Routen wie:

```text
/metrics/workspace/{id}
/metrics/workspace/{id}/thresholds
```

Eine `backend/se_metrics/urls.py` existiert nicht. In `backend/rest_api/urls.py:151` ist stattdessen nur ein Router unter `/api/v1/metrics/` registriert.

Damit unterscheiden sich Quellcode-Dokumentation, erwarteter Pfad und tatsächlich registrierte Route.

### 5.2 Mittel: MCP doppelt gemountet

`backend/reqogniloom/urls.py:50-51` registriert MCP sowohl unter:

```text
/api/v1/mcp/
/mcp/
```

Das kann als Kompatibilitätsalias beabsichtigt sein, ist aber in API-Dokumentation und Client-Konfiguration eindeutig zu erklären. Andernfalls entstehen unterschiedliche Basis-URLs, unklare CORS-/CSRF-Regeln und doppelte Monitoringpfade.

### 5.3 Mittel: Veraltete URL-TODOs

`backend/reqogniloom/urls.py:8-10` und `:46-50` behaupten, REST- und MCP-Routen würden noch registriert werden, obwohl sie bereits eingebunden sind.

Das beeinträchtigt Wartbarkeit und erschwert Audits.

## 6. UI-Konzept und visuelle Konsistenz

### 6.1 Positiv umgesetzte Zielbausteine

Im Frontend sind zentrale gemeinsame Komponenten vorhanden und in vielen Routen im Einsatz:

- `PageHeader`
- `ListToolbar`
- `SplitView`
- `WorkspaceTree`
- `TraceSpine`
- `ArtifactRow`
- `ArtifactId`
- `LevelBadge`
- `StatusBadge`
- `VersionBadge`
- `EmptyState`
- `Dialog`

Die ursprüngliche Situation mit mehreren unabhängigen Header-, Baum- und Badge-Implementierungen wurde dadurch deutlich verbessert.

### 6.2 Hoch: Benannte Themes fehlen

Das Konzept fordert in Kapitel 8.6 Theme-IDs wie `default-dark` und `default-light` sowie erweiterbare Paletten.

Ist-Zustand:

- `frontend/src/context/ThemeContext.tsx:20` definiert nur `"dark" | "light"`
- `:32-38` akzeptiert nur diese beiden Werte
- `:49-51` kann nur zwischen diesen beiden Werten umschalten

Der Context ist daher nicht auf ein erweiterbares Theming-System umgestellt.

### 6.3 Mittel: Toolbar-Actions widersprechen der verbindlichen Regel

`frontend/src/components/shared/ListToolbar.tsx:56-61` besitzt ein `actions`-Prop und rendert dieses in `:159-163`.

Kapitel 12.2 des Konzepts verlangt, dass Primäraktionen ausschließlich im `PageHeader` liegen. Die dokumentierte Ausnahme ist technisch nachvollziehbar, aber als API-Schnittstelle weiterhin ein Rückfallrisiko.

### 6.4 Mittel: Stumme Fehler bei Hintergrundoperationen

Mehrere Fehler werden nur protokolliert. Besonders kritisch sind:

- `CanvasEditor.tsx:404`: Auto-Save
- `MermaidEditor.tsx:312`: Auto-Save
- `TestRuns.tsx:43,56`: Laden
- `TestRunDetailEditor.tsx:59,87`: Laden/Schließen
- `DiagramView.tsx:45`: Löschen
- `TraceLinkPanel.tsx:90,109`: Laden/Löschen

Das verletzt Kapitel 12.12. Nutzer erhalten nicht immer eine sichtbare Rückmeldung und können bei Auto-Save-Problemen von einem gespeicherten Stand ausgehen.

### 6.5 Mittel: Typografie weicht vom Zielbild ab

Das Konzept fordert IBM Plex Sans, IBM Plex Mono und IBM Plex Sans Condensed.

Ist-Zustand:

- `frontend/src/styles/tokens.css:58`: Outfit/Inter
- `frontend/src/styles/tokens.css:62-63`: System-Mono-Stack
- `--font-cond` fehlt
- `frontend/src/index.tsx:13-19`: Outfit und Inter werden lokal eingebunden

Das Selbsthosten wurde gegenüber einem externen Google-Fonts-Import verbessert, die vereinbarte Zieltypografie ist jedoch noch nicht umgesetzt.

### 6.6 Mittel: Theme-Umgehung durch harte Farbwerte

Harte Farbwerte befinden sich unter anderem in:

- `frontend/src/styles/global.css:51`
- `frontend/src/styles/global.css:115`
- `frontend/src/styles/global.css:140`
- `frontend/src/styles/global.css:181`
- `frontend/src/styles/tokens.css:102-107`

Das gefährdet zusätzliche Themes und kann kontrastabhängige Abweichungen verursachen.

### 6.7 Niedrig: Hover-Animation widerspricht Konzept

`frontend/src/styles/global.css:88-91` hebt `.glass-panel` mit `translateY(-2px)` an. Kapitel 11.2 untersagt dieses Verhalten für ruhige, dichte Arbeitslisten.

### 6.8 Niedrig: Breakpoint-System nicht vollständig einheitlich

Das Konzept nennt `1024px` und `768px` als zentrale Haltepunkte. `Dialog.module.css:122` verwendet zusätzlich `640px`. Solche Ausnahmen müssen explizit dokumentiert oder auf die Standardregeln zurückgeführt werden.

## 7. Responsive UI und Scrollmodell

Das Konzept fordert:

- feste Navigation
- 40:60-Liste/Detail-Aufteilung
- drei Scrollflächen
- Sticky Header und Filter
- Navigation als Off-Canvas unter 1024 px
- gestapeltes Layout unter 768 px
- horizontale Trace-Spine auf kleinen Fenstern

Die dafür erforderlichen Tokens sind in `tokens.css:114-131` vorhanden. Es fehlt jedoch ein vollständiger, dauerhaft ausgeführter E2E-Nachweis für alle Routen.

Nicht ausreichend abgesichert sind insbesondere:

- Anzahl der Scrollcontainer pro Route
- `overscroll-behavior: contain`
- Erhalt der Listenposition beim Wechsel in Details
- Verhalten bei halbierter Desktopbreite
- tatsächliche Bedienbarkeit auf mobilen Breiten

Die fehlende Chromium-Installation verhindert aktuell eine reproduzierbare Live-Abnahme dieser Punkte.

## 8. Accessibility und i18n

### 8.1 Positiv

- globaler `:focus-visible`-Indikator in `global.css:65-69`
- zahlreiche `role="alert"`-Verwendungen
- Dialog-Primitive mit `role="dialog"` ist vorhanden
- reduzierte Bewegung ist global berücksichtigt

### 8.2 Offene Accessibility-Risiken

- stille Fehlerpfade ohne `role="alert"`
- fehlender flächendeckender Screenreader-Test
- keine vollständige Ende-zu-Ende-Tastaturprüfung aller Bäume und Dialoge
- `waitForTimeout`-Nutzung in E2E-Tests bleibt laut Konzeptmessung vorhanden
- kontrastkritische harte Farbwerte umgehen die Token-Logik

### 8.3 i18n-Inkonsistenzen

Das Konzept nennt:

- fehlende Schlüssel in `de.json`
- englische und deutsche Texte innerhalb derselben Oberfläche
- vollständig oder teilweise unübersetzte Workflow-Editor-Dateien

Zusätzlich ist im statischen Frontend-Shell `lang="en"` gesetzt. Die tatsächliche Laufzeitumschaltung konnte ohne Browser nicht bestätigt werden.

Es fehlt ein automatischer Paritätstest zwischen `en.json` und `de.json` als verbindliches CI-Gate.

## 9. MCP-Funktionsabgleich

### 9.1 MCP-Funktionsumfang

Die MCP-Registry enthält unter anderem folgende Gruppen:

- `requirement`
- `needs`
- `architecture`
- `test`
- `traceability`
- `artifact`
- `context`
- `workspace`
- `permissions`
- `admin`
- `audit`
- `events`
- `user`
- `adr`
- `risk`
- `issue`
- `glossary`
- `change_request`
- `prompt_template`
- `ai_derivation`
- `diagram`
- `custom_field`
- `review`
- `baseline`
- `goal`
- `main_goal`

Die MCP-Oberfläche ist damit wesentlich größer als die sichtbare UI-Funktionsfläche.

### 9.2 Fehlende oder unvollständige UI-Gegenstücke

Folgende Funktionen sind MCP-seitig vorhanden, aber in der UI nicht gleichwertig abgebildet:

- `change_request.*`: REST vorhanden, vollständiger Frontend-Flow fehlt
- `ai_derivation.derive_risks_from_architecture`
- `ai_derivation.derive_glossary_from_workspace`
- `ai_derivation.derive_adr_from_decision`
- `traceability.suggest_links`
- `events.dlq_list`
- `events.dlq_replay`
- `user.create`
- `user.assign_role`
- `user.deactivate`
- `permissions.check`
- `review.list_pending`

Das ist besonders problematisch, wenn MCP-Agenten von außerhalb Änderungen vornehmen, die in der UI nicht auffindbar oder nicht rückgängig zu machen sind.

### 9.3 Hoch: Unterschiedliche Update-Payloads

Mit `data`-Wrapper:

- `requirement.update`
- `architecture.update`
- `test.update`

Ohne `data`-Wrapper:

- `needs.update`
- Generic CRUD Updates

Betroffene Dateien:

- `backend/mcp_server/tools/requirements.py:352`
- `backend/mcp_server/tools/architecture.py:342`
- `backend/mcp_server/tools/tests.py:436`
- `backend/mcp_server/tools/needs.py:262-264`
- `backend/mcp_server/tools/generic.py:233-234`

Ein generischer MCP-Client kann dadurch nicht zuverlässig dieselbe Payload-Strategie verwenden.

### 9.4 Hoch: Unterschiedliche Löschsemantik

MCP Generic CRUD bietet teilweise sowohl `delete` als auch `outdate`. REST und UI behandeln `DELETE` bei mehreren Entitäten als Soft-Delete.

Betroffene Bereiche:

- `backend/mcp_server/tools/generic.py:270-304`
- ADR-, Risiko- und Issue-Frontend-APIs
- REST-Delete-Handler

Die Operationen müssen eindeutig als Hard-Delete oder Soft-Delete spezifiziert werden. Ein Agent darf keine destruktive Operation auslösen können, die im UI nicht gleichbedeutend ist.

### 9.5 Mittel: Statuswerte sind nicht einheitlich

In `backend/mcp_server/tools/tests.py` werden sowohl PascalCase- als auch lowercase-Statuswerte verwendet:

- `Passed`, `Failed`, `Not Run`
- `passed`, `failed`, `blocked`, `not_run`

Die Werte müssen über ein gemeinsames Schema oder klar getrennte Typen abgesichert werden.

### 9.6 Mittel: Prompt-Templates nicht synchron

`frontend/src/api/prompt-templates.ts:20-28` kennt weniger Slots als die MCP-/Backend-Seite. Zusätzliche AI-Flows sind damit im Frontend nicht konfigurierbar.

### 9.7 Mittel: MCP-RBAC für Preview und Write nicht getrennt

`backend/mcp_server/tools/ai_derivation.py:51-56` schließt Viewer auch von Preview-Aufrufen aus. Wenn die UI Preview zulässt, entsteht ein widersprüchliches Rollenverhalten.

## 10. Architektur- und Wartbarkeitsbefunde

### 10.1 Direkte ORM-Zugriffe in Layer 3

Die ADR-01-Regel fordert Zugriff über die Application-Fassade. Direkte ORM-Zugriffe wurden gefunden in:

- `backend/mcp_server/tools/cross_cutting.py:1112,1140,1209,1234`
- `backend/mcp_server/tools/users.py:320,427,438,443,450,551,681,722`
- `backend/mcp_server/tool_registry.py:874`
- `backend/rest_api/diagram_views.py:138`
- `backend/rest_api/icd_views.py:174`
- `backend/rest_api/diagram_canvas_views.py:65-94`

Risiken:

- uneinheitliche Tenant-Prüfung
- uneinheitliche Berechtigungsprüfung
- uneinheitliches Audit-Verhalten
- erschwerte Testbarkeit

### 10.2 Synchroner Webhook-Versand

`backend/application/webhook_dispatcher.py:12,78,212` führt externe HTTP-Aufrufe synchron im Requestpfad durch.

Bei langsamen oder nicht erreichbaren Zielen blockiert dies API-Worker. Der vorhandene Celery-Stack sollte für diese Arbeit verwendet werden.

### 10.3 MCP-Transportangaben nicht eindeutig

`backend/mcp_server/views.py:210-212` bewirbt HTTP und stdio. SSE/HTTP ist implementiert; ein belastbarer stdio-Startpfad ist nicht ersichtlich.

Ein MCP-Client kann dadurch einen Transport wählen, der praktisch nicht startbar ist.

### 10.4 Testlücken

Besonders unzureichend abgesichert sind:

- `frontend/src/components/WorkflowEditor/`
- `frontend/src/components/DiagramView/`
- `frontend/src/components/IcdView/`
- `frontend/src/components/TraceabilityView/`
- `backend/application/audit_service.py`
- Metrics-Authentifizierung und Tenant-Isolation
- visuelle und responsive UI-Abnahme

Dauerhaft übersprungene E2E-Tests befinden sich unter anderem in:

- `e2e/tests/stakeholder-needs.spec.ts:247`
- `e2e/tests/se-workflow.spec.ts:85-201`
- `e2e/tests/waterkettle-fullblown.spec.ts:412-669`
- `e2e/tests/tracelink-creation.spec.ts:73`
- `e2e/tests/api-completeness.spec.ts:252`

## 11. Fehlende automatische Durchsetzung des UI-Konzepts

Kapitel 16 des Konzepts fordert folgende Gates, die nicht vollständig nachgewiesen wurden:

- jede `var(--token)`-Referenz muss existieren
- Schlüsselparität zwischen Deutsch und Englisch
- genau ein `<h1>` je Route
- keine Hex-Literale in Inline-Styles
- monotone Reduktion von `style={{}}`
- maximal drei Scrollcontainer pro Route
- keine instabilen `waitForTimeout`-E2E-Tests
- sichtbare Alerts für alle fehlgeschlagenen Aktionen
- konsistente Fokus- und Dialogregeln

Ohne diese Gates kann die UI trotz vorhandener gemeinsamer Komponenten wieder auseinanderlaufen.

## 12. Priorisierter Maßnahmenplan

### P0: Vor jedem produktiven Einsatz

1. Debug-Modus deaktivieren und Deployment-Prüfung einführen.
2. Alle exponierten API-Keys widerrufen und rotieren.
3. Metrics-Authentifizierung auf zentrale AuthAndTenancy-Logik umstellen.
4. Metrics-Tenant aus der authentifizierten Identität auflösen.
5. Metrics-Routen registrieren und OpenAPI-/Dokumentationspfade angleichen.
6. PUT-Thresholds mit echter RBAC-Prüfung absichern.

### P1: Vor breiter Pilotnutzung

1. MCP-Update-Payloads vereinheitlichen.
2. Löschsemantik zwischen REST, UI und MCP vereinheitlichen.
3. MCP- und REST-Funktionen in einer Vertragsmatrix versionieren.
4. Stumme Auto-Save- und Hintergrundfehler sichtbar machen.
5. MCP-only-Schreibfunktionen entweder in die UI bringen oder restriktiv aus der Registry entfernen.
6. Direkte ORM-Zugriffe in Application-Services verschieben.
7. Review-Queue und DLQ-Administration in der UI ergänzen.

### P2: UI-Konzept vollständig umsetzen

1. ThemeContext auf benannte Theme-IDs umstellen.
2. Harte Farben durch semantische Tokens ersetzen.
3. IBM-Plex-Zieltypografie umsetzen.
4. Toolbar-Actions entfernen oder als explizite Konzeptausnahme modellieren.
5. Responsive und Scrollmodell per E2E auf allen relevanten Routen prüfen.
6. i18n-Schlüsselparität automatisieren.
7. Ein-`h1`-Regel, Dialogregeln und Fokusbedienung automatisieren.

### P3: Qualitäts- und Wartbarkeitsschritte

1. Dateiheader und TODOs aktualisieren.
2. Workflow-, Traceability-, ICD- und Diagrammtests vervollständigen.
3. Übersprungene E2E-Tests abbauen oder offiziell als nicht implementierte Anforderungen markieren.
4. Health-Endpunkt um Redis, Celery und MCP erweitern.
5. Einen reproduzierbaren Browser-Testcontainer in CI bereitstellen.

## 13. Abnahmekriterien für eine erneute Prüfung

Eine erneute Freigabeprüfung sollte mindestens bestätigen:

- keine Django-Debug-Ausgabe auf der laufenden Instanz
- ungültige Metrics-Tokens werden abgewiesen
- Tenant wird ausschließlich aus Authentifizierung abgeleitet
- alle dokumentierten Metrics-Routen antworten korrekt
- keine Secrets in Repository, Logs oder Auditbericht
- MCP- und REST-Payloads sind vertraglich synchron
- Hard-/Soft-Delete-Verhalten ist identisch oder eindeutig dokumentiert
- jeder MCP-Schreibpfad besitzt einen UI- oder bewusst dokumentierten Admin-Gegenpart
- alle sieben UI-Konzept-Gates aus Kapitel 16 laufen in CI
- responsive UI wurde bei mindestens 1440 px, 1024 px, 768 px und 375 px geprüft
- Workflow-, Traceability- und Audit-Funktionen besitzen positive und negative Tests

## 14. Schlussbewertung

ReqogniLoom besitzt eine gute funktionale Basis und sichtbare Fortschritte bei der Vereinheitlichung der UI. Die zentrale Richtung des UI-Konzepts ist richtig: gemeinsame Artefaktidentität, Split-View, Trace-Spine, Statussemantik und kontextbewusstes Arbeiten sind im Code bereits erkennbar.

Die größten Risiken liegen aktuell nicht in fehlenden Einzelkomponenten, sondern in fehlender Durchsetzung und in Inkonsistenzen zwischen den Interfaces. Die Kombination aus Debug-Modus, unvollständiger Metrics-Authentifizierung, festem Tenant, offengelegten API-Schlüsseln und MCP-Funktionen ohne gleichwertige UI-Kontrolle muss vor einem produktiven Betrieb behoben werden.

**Gesamtstatus:** Entwicklungs-/Pilotstand mit kritischen Sicherheits- und Konsistenzmängeln; nicht produktionsfreigegeben.
