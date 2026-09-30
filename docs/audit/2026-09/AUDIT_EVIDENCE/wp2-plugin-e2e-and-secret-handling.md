---
type: REVIEW
scope: wp-2-plugin-e2e-and-secret-handling
status: final
date: 2026-09-29
author_agent: senior-developer
---

# WP-2 Evidenz 3 — E2E-Testprotokoll und Secret-Handling

Alle Schlüssel/JWT in diesem Dokument sind **maskiert** (nur die letzten 4 Zeichen).
Verwendeter Audit-Key: `reqlo_…16fG` (scope `admin`, user `wp2probe`, eigens für dieses
Audit erzeugt und am Ende **widerrufen**, s. §8).

## 1. Wie der Host das Plugin wirklich lädt — Installationsweg Schritt für Schritt

### Schritt 1 — Versioniertes Artefakt prüfen
```
$ git check-ignore -v integrations/hermes-plugin/reqogniloom/dist/plugin.js
integrations/hermes-plugin/reqogniloom/.gitignore:2:dist/   integrations/hermes-plugin/reqogniloom/dist/plugin.js
```
→ Das Manifest (`hermes-plugin.json:7`, `"main": "dist/plugin.js"`) zeigt auf eine
**nicht versionierte** Datei. In einem frischen Clone gibt es keinen Einstiegspunkt.

### Schritt 2 — Dokumentierten Build fahren (der einzige Weg zu einem Bundle)
```
$ cd integrations/hermes-plugin/reqogniloom && npm run build

> @reqogniloom/hermes-plugin@1.8.0-beta.17 build
> vite build
vite v8.2.1 building client environment for production...
✓ 11 modules transformed.
dist/plugin.js  27.84 kB │ gzip: 6.60 kB
✓ built in 30ms

> @reqogniloom/hermes-plugin@1.8.0-beta.17 postbuild
> npm run verify-build
> node --experimental-vm-modules scripts/verify-build.mjs
verify-build: token check passed
verify-build: smoke-load passed (register() ran, id="reqogniloom.reqogniloom",
             registered 2 item(s): reqogniloom-panel (panes), reqogniloom.status (statusBar.right))
verify-build: OK
```
✔ Build reproduzierbar, ✔ der mitgelieferte Guard (`scripts/verify-build.mjs`) ist
ein **echter** Smoke-Test: er lädt das Bundle als ES-Modul, ruft `register(ctx)`
und prüft, dass mindestens ein Panel registriert wurde.

### Schritt 3 — Host emulieren und das Bundle über seinen Deklarierten Einstiegspunkt laden
Der Audit-Harness (`host-emulator.mjs`, außerhalb des Repos) macht genau das, was ein
Hermes-Desktop-Host tut: bare-ESM-`import()` der `main`-Datei, `default`-Export
`{id, name, register}`, Host liefert `ctx` (`register()`, `storage` als async
String-get/set/remove). Netzwerkpfad unverändert: `activate.ts:48-50` reicht den
globalen `fetch` durch, also ging **jeder** Request in diesem Audit durch den
Plugin-Code, nicht durch den Harness.

```
[host] manifest.main = dist/plugin.js
[host] manifest.id   = reqogniloom.reqogniloom
[host] manifest.engines = {"hermes":">=3.0.0"}
[host] default export keys = ["id","name","register"]           <- Vertrag erfüllt
[host] registered = [{"id":"reqogniloom-panel","area":"panes"},
                     {"id":"reqogniloom.status","area":"statusBar.right"}]
[host] panel.render() -> valid React element
```

### Schritt 4 — Das Panel genauso rendern und bedienen, wie der Host es täte
`panel.render()` → React-Element, gerendert mit **echtem** `react-dom@18` in jsdom,
Bedienung über `data-testid` (ConnectScreen.tsx:64, ConnectedView.tsx:13-20,
InterviewListView.tsx:17,58, InterviewFormView.tsx:21,118,131).

## 2. Vollständiger Erfolgsdurchlauf — vier echte MCP-Calls, Restful-Connect

Ablauf: `ConnectScreen` ausfüllen (URL + Key, Key-Feld `type=password`) → `Connect`
klicken → Workspace wählen → `Interviews` → `Requirement` starten → Feld beantworten.

```
[drive] filling ConnectScreen: Workspace URL + API Key (type=password)
[dom:filled] inputs=[{"type":"text","ph":"https://reqogniloom.example.com","valLen":21,"valTail":"8001"},
                     {"type":"password","ph":"reqlo_...","valLen":46,"valTail":"16fG"}]
[drive] connect-submit-button disabled=false
```

### net#1 — REST (ConnectScreen → `api.ts:143 listWorkspaces`)
```
GET http://localhost:8001/api/v1/workspaces/
headers: X-API-Key: <<masked:16fG len=46>>, Content-Type: application/json
-> 200 (69 ms, 13390 B)
{"count":401,"next":"http://localhost:8001/api/v1/workspaces/?page=2","previous":null,
 "page_size":25,"max_page_size":100,"results":[{"id":"7d46f102-…","name":"e2e-isolated-…"} …]}
```
Anschließend Workspace-Auswahl (26 Buttons im gerenderten DOM) und
Statusleiste-Update:
```
[statusbar] updates = [{"text":"ReqogniLoom","tooltip":"Open ReqogniLoom panel"},
                       {"text":"ReqogniLoom: <workspace>","tooltip":"Connected to <workspace>"}]
```

### net#2 — MCP `interview.list` (ConnectedView → `state.ts:194`)
```
POST http://localhost:8001/mcp/
headers: X-API-Key: <<masked:16fG len=46>>, Content-Type: application/json
-> 200 (46 ms, 226 B)
{"jsonrpc":"2.0","id":1,"result":{"sessions":[
  {"id":"24be6e81-7a9d-49d9-a14d-66c3c5ceb5a7","workspace_id":"4eee7ca1-eedd-4a7e-bb14-47e6493cbf88",
   "artifact_type":"Requirement","status":"in_progress"}, …],"count":0}}
[dom:after-interviews] Back | "Requirement — in_progress" | Start new: Requirement
                      ArchitectureElement StakeholderNeed Risk TestCase Adr Issue Goal
```
✔ **Alle 8 Start-Buttons sind `enabled=true`** — die in PR #1118 entfernte
`FORMALIZABLE_ARTIFACT_TYPES`-Schranke ist damit wirksam weg. Dieser Teil des
Merges ist **verifiziert vollständig**.

### net#3 — MCP `interview.start`
```
POST http://localhost:8001/mcp/   -> 200 (46 ms, 474 B)
{"jsonrpc":"2.0","id":2,"result":{"id":"24be6e81-7a9d-49d9-a14d-66c3c5ceb5a7",
 "workspace_id":"4eee7ca1-eedd-4a7e-bb14-47e6493cbf88","artifact_type":"Requirement",
 "status":"in_progress","session_id":"24be6e81-…","session_kind":"single","phase":"content",
 "collected_fields":{},"missing_fields":[{"name":"description","type":"textarea","choices":null}]}}
```

### net#4 — MCP `interview.grounding_context` (`state.ts:206 withGroundingContext`)
```
POST http://localhost:8001/mcp/   -> 200 (25 ms, 57 B)
{"jsonrpc":"2.0","id":3,"result":{"candidates":[]}}
```

### net#5 — MCP `interview.answer` (Blur-Handler `InterviewFormView.tsx:26-28`)
```
POST http://localhost:8001/mcp/   -> 200 (45 ms, 389 B)
{"jsonrpc":"2.0","id":4,"result":{"session_id":"24be6e81-…","status":"in_progress",
 "session_kind":"single","phase":"identification",
 "collected_fields":{"description":"Audit-Probe-Antwort"},
 "missing_fields":[{"name":"title","type":"text","choices":null}],
 "grounding_snapshot":{"candidates":[]},"transcript":[],"transcript_summary":""}}
[dom:after-blur] identification | Answered | description: Audit-Probe-Antwort | title | Formalize | Cancel
```
✔ **Zustandsübergang `content → identification` mit fortschreitendem `missing_fields`
über das Plugin bestätigt — echter End-to-End-Durchlauf, nicht Manifest-Lesen.**

### Zusatzbeleg: Direktaufruf-Shorthand funktioniert serverseitig
`mcpClient.ts:77` setzt `method: toolName` (nicht `tools/call`). Live gegen dieselbe
Instanz mit demselben Key:
```
A) {"method":"interview.list","params":{…}} -> 200 {"result":{"sessions":[],"count":0}}
B) {"method":"tools/call","params":{"name":"interview.list","arguments":{…}}}
   -> 200 {"result":{"content":[{"type":"text","text":"{\n  \"sessions\": [],\n  \"count\": 0\n}"}]}}
```
Beide Formen sind live gleichwertig nutzbar. **Kein Finding.**

### Write-Pfad über den Python-Client (damit `interview.formalize` nicht ungeprüft bleibt)
```
POST /api/v1/interviews/<id>/formalize/  (Authorization: Bearer reqlo_…16fG)
-> 200 {"resulting_artifact_ids":["538097f4-a079-4c5a-a291-1f9897622773"],"status":"completed"}
```
✔ Der Write-Pfad des Interview-Flows ist real und funktionsfähig.

## 3. Isolation — vollständiges Netlog des Erfolgslaufs

```
[netlog]
  seq 1  GET  http://localhost:8001/api/v1/workspaces/   200
  seq 2  POST http://localhost:8001/mcp/                200
  seq 3  POST http://localhost:8001/mcp/                200
  seq 4  POST http://localhost:8001/mcp/                200
  seq 5  POST http://localhost:8001/mcp/                200
[openExternal] = []        <- "Open ReqogniLoom" nie geklickt
```

**5 Requests, alle gegen den konfigurierten `baseUrl`.** Keine Drittanbieter-URL,
kein Analytics, kein Telemetrie-Endpoint, kein Hintergrund-Polling nach `register()`.
Die `window.open`-Brücke (`activate.ts:51-55`) wird nur bei Nutzeraktion ausgelöst.
✔ Isolation bestätigt, nicht nur behauptet.

## 4. Fehlerpfade

### E1 — Ungültiger Token (401)
```
GET http://localhost:8001/api/v1/workspaces/  (X-API-Key: reqlo_…0000)
-> 401 (32 ms, 344 B)
{"error":{"code":"invalid_api_key","message":"Request rejected because of the
 X-API-Key header: the API key it carries is not valid. No other credential was
 presented, so the request is unauthenticated — send a valid X-API-Key or an
 Authorization: Bearer token.","details":[{"doc_url":"…/errors/invalid_api_key"}]}}
```
Sichtbar im Panel:
```
[dom:after-connect] REQOGNILOOM | Workspace URL | API Key |
  Request rejected because of the X-API-Key header: the API key it carries is not
  valid. … | Connect
```
✔ **Gute Fehlerübersetzung.** `api.ts:23-59` versteht sowohl die nested als auch die
flache Fehler-Hülle; der Backend nutzt die nested Form. Sauber.

### E2 — Server nicht erreichbar (Connection refused)
```
GET http://localhost:9999/api/v1/workspaces/  -> THREW TypeError: fetch failed (13 ms)
[dom:after-connect] … API Key | Connection failed. | Connect
```
⚠️ Die **Typdiagnose geht verloren**: `state.ts:140` fällt auf den generischen String
`"Connection failed."` zurück; `console.error` wird nicht aufgerufen. Der Host-Operator
sieht weder `TypeError: fetch failed` noch eine Protokollzeile. → **AUD-2026-09-116 (Low).**

### E3 — Timeout (Server nimmt an, antwortet nie)
Gegen einen Testserver, der `Content-Length: 4096` ankündigt und offen lässt:
```
GET http://127.0.0.1:9978/api/v1/workspaces/  -> THREW TimeoutError:
     The operation was aborted due to timeout (15005ms)
[dom:after-connect] … API Key | Connection failed. | Connect
```
✔ Der deklarierte Timeout greift **exakt bei 15005 ms**
(`api.ts:113 REQUEST_TIMEOUT_MS = 15_000`, `mcpClient.ts:60` identisch) — der Wert ist
nicht dekorativ. ⚠️ Der User sieht aber dieselbe generische Meldung wie bei E2; ein
Timeout ist von einem DNS-Fehler nicht unterscheidbar. Teil desselben Findings 116.

### E4 — **Stiller Fehlschlag: MCP-Fehler wird nie angezeigt**
Verbindung erfolgreich (REST 200), MCP-Aufruf mit 403 (Key ohne Rolle im gewählten
Workspace):
```
net#2 POST http://localhost:8001/mcp/ -> 403 (24 ms, 179 B)
{"jsonrpc":"2.0","id":1,"error":{"code":-32001,"message":"Role '()' does not permit
 read access to the targeted workspace. An active role in that workspace is required."}}

[dom:after-interviews] REQOGNILOOM | Connected to <ws> | Open ReqogniLoom
                       | Interviews | Disconnect
```
→ **Kein Fehlertext im DOM.** Ursache: `state.ts:196-198` setzt `interviewError` und
lässt `view` auf `"connected"`; gerendert wird `ConnectedView`
(`ReqogniLoomPanel.tsx:57`), und **`ConnectedView.tsx` rendert `interviewError`
nirgends** — nur `InterviewListView.tsx:25` und `InterviewFormView.tsx:57/72` tun das,
und die werden bei `view !== "interviews"` nicht aufgebaut.

Der User klickt „Interviews", es passiert sichtbar nichts, kein Fehler, kein Ladehinweis
(der Busy-State endet korrekt). → **AUD-2026-09-117 (High).**

### Fehlerübersetzungen im MCP-Pfad (Code-seitig geprüft)
`mcpClient.ts:89-94`: JSON-RPC-`error` → `McpRpcError(code, message, data)`;
Frame ohne `result` → `McpRpcError(-32603, …)`; Nicht-JSON →
`Error(… returned non-JSON response: …)` mit 200-Zeichen-Abschneidung
(`mcpClient.ts:86`). Sauber und ohne Stacktrace-Leak.

## 5. Auth-Token-Weitergabe — Wege, Träger, Persistenz

### 5.1 Weg in das Plugin hinein

| Plugin | Mechanismus | Träger | Argument auf der Kommandozeile? |
|---|---|---|---|
| Hermes TS | **UI-Formular**, `type="password"` (`ConnectScreen.tsx:52-59`) | `state.connection.apiKey` im Modul-Speicher | **nein** — kein CLI, kein `--token=` |
| Hermes TS (Wiederherstellung) | Host-Storage, Key `reqogniloom-connection` | JSON-String | **nein** |
| Claude Code | Env-Variable `REQOGNILOOM_API_KEY`, `${…}`-Template in `.mcp.json:7` | Prozess-Env des Hosts | **nein** |
| Antigravity | Env-Variable `REQOGNILOOM_API_KEY`, `${…}` in `mcp_config.json:6` | Prozess-Env des Hosts | **nein** |
| Hermes Python | Env-Variable `REQOGNILOOM_API_KEY` (`reqogniloom_client.py:72`) | Prozess-Env | **nein** |
| Hermes Python Dash | Env `REQOGNILOOM_DASHBOARD_TOKEN` für **Inbound** (`plugin_api.py:83`) | Prozess-Env | **nein** |

✔ **Kein Plugin nimmt einen Token als CLI-Argument entgegen.** Damit ist die
`ps`/`/proc/<pid>/cmdline`-Exposition, die im Auftrag als Verdachtsmotiv genannt war,
**gemessen nicht vorhanden** — es existiert überhaupt kein Argument-Pfad. (Für den
Audit-Scope: die *Bluepencil*-Seitenkette ist ein Compose-`command:`-String, dort steht
der Token ebenfalls nirgends; s. §7.)

### 5.2 Persistenz auf der Platte — **Klartext-Key im Host-Storage**

Gemessen, aus dem tatsächlich vom Plugin geschriebenen Storage-Inhalt
(`state.ts:157-158 finalizeConnection` → `storage.set(STORAGE_KEY, JSON.stringify({connection, workspaceName}))`):

```
[storage] persisted = {
  "reqogniloom-connection": {
    "rawLen": 203,
    "containsApiKey": true,
    "containsReqloPrefix": true,
    "masked": "{\"connection\":{\"baseUrl\":\"http://localhost:8001\",
              \"apiKey\":\"<<key:16fG>>\",
              \"workspaceId\":\"4eee7ca1-eedd-4a7e-bb14-47e6493cbf88\"},
              \"workspaceName\":\"Zahnbuerste SysEng Demo\"}"
  }
}
```

* `containsApiKey: true`, `containsReqloPrefix: true` → **der vollständige
  `reqlo_…`-Schlüssel liegt im Klartext im persistenten Host-Storage.**
* Keine Verschlüsselung, kein OS-Keychain, kein `sessionStorage`.
* Der Key überlebt Neustarts (`state.ts:101-118 initState` liest ihn und stellt die
  Verbindung ohne erneute Auth her) — die Persistenz ist beabsichtigt, die
  Klartextform ist es auch.
* **Entschärfung durch die Host-Grenze:** der Storage gehört dem Host
  (`ctx.storage.get/set/remove`, `activate.ts:43-47`), nicht dem Plugin. Ob Hermes
  diesen Store verschlüsselt, ist ohne installierten Host **nicht verifizierbar** →
  **BLOCKED**, s. §9. Als Finding bleibt: das Plugin legt ein langzeitgültiges
  Tenant-Credential im Klartext ab, ohne den Nutzer zu informieren oder eine
  Ablaufzeit zu setzen. → **AUD-2026-09-118 (Medium).**

### 5.3 Wird der Key geloggt?
Nein. `activate.ts:79-81` ist der **einzige** `console.*`-Aufruf im gesamten
Bundle (`console.error("ReqogniLoom: initState failed…", err)`) und loggt ein
`Error`-Objekt. Die in `api.ts:57-59`/`mcpClient.ts:90` konstruierten Fehler
enthalten **Servertexte und Statuscodes, nie den Schlüssel** (belegt: die in §4
protokollierten DOM-Texte enthalten keine `reqlo_`-Zeichenkette). Im Harness wurde
jeder Key-Header vor dem Log maskiert (`<<masked:16fG len=46>>`).
✔ **Kein Key im Log.**

### 5.4 Wird der Key über die Leitung geleakt?
* **Nein über TLS-Fehler:** keine.
* **Doch als URL-Bearer:** der MCP-SSE-Transport legt die Session-ID in die
  Query-String (`backend/mcp_server/urls.py:25` → `/mcp/messages/?session_id=…`).
  Live gemessen:
  ```
  GET /mcp/sse/  -> event: endpoint
                    data: /mcp/messages/?session_id=fb8fab7a-deaf-4cdc-bf7c-ab57e327f121
  ```
  → Die Session-ID ist damit ein **URL-Bearer-Credential mit 8-h-TTL** und taucht in
  Proxy-/Access-Logs und im Browser-Verlauf auf. Das ist **kein Plugin-Fehler** —
  es ist der Server-Transport, den die Plugins in `.mcp.json:5`/`mcp_config.json:4`
  selbst konfigurieren. Reconciliation: **CR-28 BESTAETIGT** (dort als
  „MCP-Session-ID ist ein URL-Bearer-Credential mit acht Stunden TTL" erfasst,
  `views.py:788-801`, `sse_pubsub.py:13-23,74-131`). Ich habe die Vorhersage des
  Vor-Audits **am laufenden System bestätigt**.

### 5.5 Zwei Auth-Konventionen nebeneinander
| Konvention | Wo | Akzeptiert vom Backend? (live) |
|---|---|---|
| `X-API-Key: reqlo_…` | beide `dist`-Pakete, Hermes-TS | ✔ 200 |
| `Authorization: Bearer reqlo_…` | `reqogniloom_client.py:95` | ✔ 200 (6/6 GET-Probes) |
| `Authorization: Bearer <JWT>` | `INSTALL.md:139` behauptet es | MCP: **401** (vom Auftrag vorgegeben und bestätigt) |

`INSTALL.md:130-158` („One convention, and one place it disagrees") dokumentiert
**Codex** als einzige Abweichung. Dass das **Hermes-Python-Plugin** eine zweite,
undokumentierte Bearer-Form benutzt, ist in diesem Abschnitt nicht erwähnt.
Kein Defekt (beides funktioniert), aber Doku-Lücke. → **AUD-2026-09-119 (Low).**

## 6. Live-Beweis für den `dist/`-Pfad: SSE-Round-Trip komplett

Die beiden `dist`-Pakete konfigurieren **SSE** (`mcp_config.json:4`, `.mcp.json:4-5`),
nicht HTTP. Der volle SSE-Handshake wurde live gefahren:

```
$ curl -N -H "X-API-Key: …" -H "Accept: text/event-stream" http://localhost:8001/mcp/sse/
event: endpoint
data: /mcp/messages/?session_id=ff2ea713-1925-4397-9dd5-469edc90f575

: keepalive
                                     (curl exit 28 = Stream blieb offen)

$ curl -X POST -H "X-API-Key: …" -H "Content-Type: application/json" \
       --data '{"jsonrpc":"2.0","id":7,"method":"tools/list","params":{}}' \
       "http://localhost:8001/mcp/messages/?session_id=fb8fab7a-…"
HTTP/1.1 202 Accepted
content-type: text/html; charset=utf-8
content-length: 0

$ … dieselbe POST mit session_id=00000000-0000-0000-0000-000000000000
HTTP/1.1 401 Unauthorized
```

✔ **Die von beiden `dist`-Paketen deklarierte SSE-Konfiguration ist live korrekt und
vollständig funktionsfähig.** `/mcp/sse/` ist **kein Phantom** — anders als
`/mcp/stdio/`, das laut WP-1a nicht geroutet ist. Fehlpfade:

```
GET /mcp/sse/  ohne Key      -> 401 {"error":{"code":"invalid_api_key", …}}
GET /mcp/sse/  ungültiger Key -> 401 (identisch)
POST /mcp/sse/               -> 405 Method Not Allowed   (SSE ist GET-only ✔ korrekt)
```

## 7. Bluepencil-Host-Bridge (CR-25) — gemessen

| Frage | Messung | Ergebnis |
|---|---|---|
| Profil registriert? | `deploy/docker-compose.yml:1325` `profiles: ["bluepencil"]`, `command: node /opt/bluepencil/server.js … --port 8787 --base /bluepencil/api` | ✔ registriert |
| Container läuft? | `docker ps` → `ai-native-reqflow-poc-bluepencil-1  Up 7 hours (healthy)` | ✔ **läuft** |
| Erreichbar? | `docker exec frontend node -e fetch('http://bluepencil:8787/bluepencil/api/health')` → `status 200 {"ok":true,"status":"ok","version":"0.1.0-alpha.1"}` | ✔ erreichbar |
| Host-Port publiziert? | `docker port ai-native-reqflow-poc-bluepencil-1` → **leer** | ✔ kein Host-Port |
| Frontend scharf? | `docker exec frontend printenv` → `VITE_BLUEPENCIL_ENABLED=0`, `VITE_BLUEPENCIL_ENVIRONMENT=dev` | ✖ **nicht scharf** |
| Default im Repo? | `.env.example:515` `BLUEPENCIL_ENABLED=0`; `:511` `# COMPOSE_PROFILES=bluepencil` (auskommentiert) | ✔ Default-off, dokumentiert |

**AuthN/Tenant-Isolation der Notiz-API (die P1-Bedingung aus CR-25):**
```
GET /bluepencil/api/health -> 200 {"ok":true,"status":"ok","version":"0.1.0-alpha.1"}
GET /bluepencil/api/notes  -> 200 {"notes":[{"id":"n-8e4665ce-…","schemaVersion":1,…}]}
POST /bluepencil/api/notes (ohne jede Credential) -> 400 {"error":{"code":"invalid_payload",
                              "message":"type must be one of text, design; anchor is required"}}
```
→ **`GET /notes` liefert ohne jede Authentifizierung 200 mit Notizen aller Workspaces.**
CR-25s P1-Bedingung („bei Aktivierung fehlen AuthN/Tenant-Isolation") ist damit
**am laufenden System bestätigt**. ⚠️ Die `POST`-Pfadform wurde bewusst **nicht**
zu Ende geführt, um den geteilten JSON-Store nicht zu verschmutzen; der `400` belegt
aber, dass auch der Schreibpfad **keine** Auth-Prüfung vor der Payload-Verifikation
hat (die Prüfung käme erst danach). → **CR-25 BESTAETIGT**, nicht WIDERLEGT.

**Antwort auf die Auftragsfrage „ist das aktiv/registriert, welche Fähigkeiten fehlen
wirklich?"**: Registriert **ja**, Sidecar **läuft und ist erreichbar**; es fehlt
**ausschließlich der Frontend-Schalter** `VITE_BLUEPENCIL_ENABLED=1` (ein Vite-Build-
Flag, `docker-compose.override.yml:195`). Der Sidecar bindet zusätzlich nur auf
`0.0.0.0` **innerhalb** des Compose-Netzes. *Fähigkeiten*, die serverseitig fehlen,
gibt es nicht — was fehlt, ist die eine Umschaltung.

## 8. Audit-Cleanup

```
$ POST /api/v1/interviews/<id>/abandon/  x8
  d4063ce6-… -> 200   456813b2-… -> 200   0cffb8db-… -> 200   384dc3e5-… -> 200
  e4868db2-… -> 200   0d8e84f7-… -> 200   28ef5db2-… -> 200   67861b4b-… -> 200
  (alle 8 in_progress-Sessions, die dieses Audit erzeugt hat)

$ DELETE /api/v1/api-keys/f1cb3d0a-95a2-4d37-a559-d80d038c5423/
-> 204
$ Django-Shell: wp2probe is_active = False
```
Kein Seeder-Datensatz gelöscht, kein bestehender Key widerrufen (der vorhandene
`reqlo_…ejYR`-Audit-Key blieb unangetastet, die 10er-Kapazität war bereits
erschöpft — deshalb der Weg über einen eigenen Probe-User).

## 9. Nicht verifizierbar (BLOCKED)

| Nr | Sachverhalt | Grund |
|---|---|---|
| B6 | Ob Hermes seinen `ctx.storage` verschlüsselt (entscheidet, ob Finding 118 Critical oder Medium ist) | Hermes nicht installiert |
| B7 | Ob der Hermes-Host den `engines.hermes >=3.0.0`-Check durchsetzt | Hermes nicht installiert; kein Repo-Code liest das Feld |
| B8 | Ob Antigravity `${VAR}` in `mcpServers` auflöst | Antigravity nicht installiert |
| B9 | Ob `claude plugin install` die Pakete annimmt (marketplace.json ohne `version`) | `claude` CLI nicht installiert |
| B10 | Ob die Hermes-Slash-Command-Registrierung im echten Host den Panel-Renderer aufruft | Hermes nicht installiert (der Handler selbst ist live getestet) |

**Keines dieser fünf wurde als PASS gewertet.**
