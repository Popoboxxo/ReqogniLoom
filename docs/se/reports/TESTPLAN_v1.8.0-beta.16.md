---
type: STRATEGY
scope: Testplan v1.8.0-beta.16
status: final
date: 2026-09-26
author_agent: release
---

# Testplan v1.8.0-beta.16

> **Hand-off-Testplan.** Dieses Dokument ist für eine:n **externe:n Tester:in ohne Vorkenntnisse** geschrieben.
> Alle Schritte sind so formuliert, dass sie ohne Repository-Wissen, ohne Agenten-Kontext und ohne
> Vorwissen über die Historie ausgeführt werden können. Jeder Testfall hat einen **Negativfall** und
> eine **Evidence**-Zeile. Die Pass/Fail-Spalte wird während der Durchführung ausgefüllt.

> ⚠️ **Dieser Plan ist KEINE externe Production- oder QS-Freigabe.** Er beschreibt
> **QS-Testfälle** für eine:n externe:n Tester:in. Eine Freigabe des Cuts `1.8.0-beta.16`
> ist damit **nicht** erteilt — der Schnitt ist ein interner Beta-Cut, W0/W1/W2 sind
> **teilweise** umgesetzt, kein Track ist `VERIFIZIERT`, und W3–W5 sind **nicht
> begonnen** (siehe §6.2).

**Durchführungshinweise**

- **Test-IDs** sind stabil: `WF-*`, `GLB-*`, `ITV-*`, `SEC-*`, `KEY-*`, `PLT-*`, `REG-*`.
  In Fehlermeldungen immer die Test-ID mitnennen.
- **Evidence** wird pro Testfall als Datei abgelegt: Screenshot als `evidence/<TEST-ID>_<nr>.png`,
  Response-Body als `evidence/<TEST-ID>_<nr>.json` bzw. `.txt`.
- **UI-Klickwege** beginnen jeweils mit der Annahme: angemeldet, korrektes Workspace geöffnet.
- **REST-Beispiele** sind gegen `http://localhost:8001/api/v1/` gedacht (bzw. den konfigurierten `BACKEND_PORT`).
  Mit `Authorization`-Header des angemeldeten Users (JWT) ausführen, sofern nicht anders angegeben.
- **MCP-Beispiele** sind JSON-RPC-2.0-Bodies gegen `http://localhost:8001/mcp/`
  (alternativ `/api/v1/mcp/`). Der MCP-Server ist an **beiden** Pfaden gemountet.
- **Verbot von Erfundenem:** Es werden ausschließlich die in diesem Dokument genannten Routen, Tools
  und Variablen verwendet. Für Bereiche ohne verifizierte Angabe steht ausdrücklich
  „nicht im Scope / nicht verifiziert".

> **Kein Testlauf für diesen Plan.** Dieser Plan ist eine **Vorbereitung**; die Pass/Fail-Spalten
> sind leer. Es werden hier **keine** Testergebnisse behauptet.

---

## 1. Ziel & Prüfgegenstand

| Feld | Wert |
|---|---|
| Release | **1.8.0-beta.16** (interner Beta-Cut, **keine** externe Freigabe) |
| Backend-Image | **nicht gebaut** — es existiert **kein** Image `1.8.0-beta.16` und **kein** Digest (siehe 1.3) |
| Frontend-Image | **nicht gebaut** — es existiert **kein** Image `1.8.0-beta.16` und **kein** Digest (siehe 1.3) |
| Commit-SHA (Basis) | `73892571751ca88b8cdf4d45c5700bab322ae31f` |
| Datum | 2026-09-26 |
| Branch | `release/v1.8.0-beta.16` (Basis: `origin/main` = `73892571`) |
| Vorgänger-Release | `1.8.0-beta.15` (Commit `6606b6f0`, Tag-Objekt `90f91063`) — Vergleichsbasis |
| CI auf dem Basis-Commit | **grün** — 2 Runs, 14/14 Check-Runs `success` (Nachweis im Release-Bericht §7) |

### 1.1 Im Scope (Delta seit `1.8.0-beta.15`)

| Delta (PR) | Thema | Testbereich |
|---|---|---|
| #1073 | Workflow-Transition im Row-Lock, `expected_version` wird erzwungen (CR-08) | §4.1 (`WF-*`) |
| #1073 | Globale Definition: atomare Propagation + Orphan-Gate auf `delete_state` (CR-09/CR-10) | §4.2 (`GLB-*`) |
| #1073 | Interview-Formalisierung: Lock, Audit, Outbox, Multi-Parität REST/MCP (CR-05/CR-06/CR-07) | §4.3 (`ITV-*`) |
| #1070, #1071 | W0/W1 Security-Slice, RLS-Exit-Evidenz, Workspace-Fence-Härtung, Negativtests | §4.4 (`SEC-*`) |
| #1071 | Strikt read-only Legacy-API-Key-Inventar | §4.5 (`KEY-*`) |
| #1055 | Bluepencil-Host-Identitätsbrücke, Login-Timeout-Ursache | §4.6 (`PLT-*`) |
| #1069, #1072 | Dokumentation und Projekt-Metadaten (keine Produktverhaltensänderung) | §5 (`REG-*`) |

### 1.2 Nicht im Scope

- **`bluepencil`** — die optionale selbst-gehostete Review-Sidecar ist **DEBUG/QS-only**
  und wird im Standard-Testlauf **nicht aktiviert und nicht getestet** (siehe Warnbox §2.6).
  `PLT-01`/`PLT-02` prüfen ausschließlich, dass Bluepencil **deaktiviert bleibt** bzw. die
  Host-Brücke im Dev-Modus greift — **nicht** die Sidecar selbst.
- **Live-only-Punkte** — benötigen echte Provider-Konnektivität (LLM, Honcho, Embedding-Endpoint)
  und sind offline nicht validierbar.
- **Last-, Performance- und Sicherheits-Penetrationstests** — nicht Bestandteil dieses Testplans.
- **Dokumentations-PRs** (#1069, #1072) — reine Doku- bzw. Metadatenlieferung ohne
  Produktverhaltensänderung; nur als Regressionseintrag (§5).

### 1.3 ⚠️ Kein Image vorhanden — Auswirkung auf die Testumgebung

Für diesen Schnitt wurde **kein Image gebaut** und **kein Image-Digest dokumentiert**.
Ein image-basierter Testlauf ist deshalb **nicht möglich**. `make build` erzeugt
per Konstruktion **kein** Image: `deploy/docker-compose.yml` enthält **0 `build:`-
Sektionen** und pinnt ausschließlich fertige Images; die `build:`-Sektionen liegen im
Dev-Overlay `deploy/docker-compose.override.yml`, das `scripts/build.sh`
**absichtlich ausschließt**.

**Konsequenz für die QS:** §2.4 ist zwingend über den **Source-Checkout** zu
starten (`make up`). Ein image-basierter Deployment-Pfad ist für `1.8.0-beta.16`
**nicht verfügbar** und darf **nicht** als geprüft gemeldet werden.

---

## 2. Vorbedingungen (exakt)

### 2.1 Host-Voraussetzungen

- **Docker Engine** (aktuell, lauffähig).
- **Docker Compose v2 als Plugin** — das Kommando ist `docker compose` (Leerzeichen),
  **nicht** `docker-compose` (Bindestrich). Prüfen: `docker compose version`.
- Freie Ports `8001` (Backend) und `5173` (Frontend), sofern nicht via env überschrieben (§2.3).
- Source-Checkout des Repositories auf Branch `release/v1.8.0-beta.16` (siehe 1.3).

### 2.2 `.env` anlegen

```bash
cp .env.example .env
```

Danach `.env` editieren. Folgende Variablen sind für einen erfolgreichen Start **erforderlich**:

| Variable | Zweck | Hinweis zur Erzeugung |
|---|---|---|
| `SECRET_KEY` | Django-Secret | `python3 -c "import secrets; print(secrets.token_urlsafe(64))"` |
| `AUTH_JWT_SECRET` | Signatur der JWT-Tokens | `python3 -c "import secrets; print(secrets.token_urlsafe(64))"` |
| `FIELD_ENCRYPTION_KEY` | Feldverschlüsselung at rest (REQUIRED, kein Default) | wie in `.env.example` dokumentiert erzeugen |
| `DB_PASSWORD` | Postgres-Superuser-Passwort (nur `migrate`-Service) | starkes Zufallspasswort |
| `DB_APP_PASSWORD` | Passwort der Least-Privilege-App-Rolle (RLS greift nur hier) | starkes Zufallspasswort |
| `SYSTEM_ADMIN_USERNAME` | legt den initialen Admin an | z. B. `admin` |
| `SYSTEM_ADMIN_EMAIL` | E-Mail des initialen Admin | z. B. `admin@demo.local` |
| `SYSTEM_ADMIN_PASSWORD` | Passwort des initialen Admin | **Pflicht bei frischem System** |

> **Hinweis:** `SYSTEM_ADMIN_USERNAME` / `SYSTEM_ADMIN_EMAIL` haben Defaults; `SYSTEM_ADMIN_PASSWORD`
> ist auf einem frischen System **zwingend**. Die Admin-Anlage ist create-only: wird das Passwort
> später im UI geändert, überschreibt ein Neustart es nicht.

### 2.3 Ports & Multi-Instanz

| Variable | Default | Bedeutung |
|---|---|---|
| `BACKEND_PORT` | `8001` | Host-Port des Backends |
| `FRONTEND_PORT` | (Compose-Default) | Host-Port des Frontends |

> **Multi-Instanz-Hinweis:** Soll die Instanz **neben einer bereits laufenden** Instanz betrieben werden,
> müssen **beide** Ports geändert werden (`BACKEND_PORT` **und** `FRONTEND_PORT`). Ein einzelner
> geänderter Port genügt nicht.

### 2.4 Stack starten (kanonisch für diesen Schnitt)

```bash
# Source-Checkout-Pfad — zwingend, da kein Image 1.8.0-beta.16 existiert (siehe 1.3)
make up
```

### 2.5 Health-Check

```bash
curl localhost:8001/health/
```

Der Health-Endpoint liegt auf Pfad **`/health/`** (Backend-Root-URLconf; **mit** Trailing Slash).
Erwartet: HTTP `200` mit `{"status": "ok", "checks": {...}, "warnings": [...]}`.
Zusätzlich der Admin-Systemstatus (Dashboard-Sicht): `GET /api/v1/admin/health/` → HTTP `200`.

### 2.6 ⚠ WARNUNG: `bluepencil`

> **`bluepencil` (optionale selbst-gehostete Review-Sidecar) ist DEBUG/QS-only.**
> Sie darf im **Standard-Testlauf nicht aktiviert und nicht getestet** werden. Es gibt **keinen**
> Auth- und **keinen** Tenant-Isolation-Schutz, und eine einzige JSON-Datei hält die Notizen
> **aller** Workspaces. `BLUEPENCIL_ENABLED=0` muss im Testlauf gesetzt bleiben.
> Ein Bluepencil-Befund ist **kein** Release-Blocker für `1.8.0-beta.16` — er ist außerhalb des Scopes.

### 2.7 Optional: Honcho-Profil

Für die Testfälle dieses Plans **nicht** erforderlich. Nur falls ein Provider-abhängiger
Gegencheck gewünscht ist:

```bash
docker compose -f deploy/docker-compose.yml --profile honcho --project-directory . up -d
```

| Variable | Zweck |
|---|---|
| `HONCHO_BASE_URL` | Basis-URL der Honcho-Instanz |
| `HONCHO_API_KEY` | API-Key der Honcho-Instanz |
| `HONCHO_EMBEDDING_BASE_URL` | Embedding-Endpoint (inkl. `/v1`-Suffix) |
| `HONCHO_EMBEDDING_MODEL` | Embedding-Modell |
| `HONCHO_EMBEDDING_VECTOR_DIMENSIONS` | Vektorbreite (muss zum Modell passen) |

---

## 3. Vorbereitung Testdaten

Alle Testdaten werden in einem **eigenen Workspace** angelegt.

| Schritt | Aktion (UI) | Erwartetes Ergebnis | Evidence |
|---|---|---|---|
| 3.1 | Anmelden mit `SYSTEM_ADMIN_USERNAME` / `SYSTEM_ADMIN_PASSWORD` | Login erfolgreich, Dashboard sichtbar | Screenshot |
| 3.2 | Workspace anlegen, Name: `TP-b16 Workspace` | Workspace erscheint in der Workspace-Liste | Screenshot |
| 3.3 | Requirement anlegen, Titel: `REQ-TP-001 Requirement beta.16` | Artefakt angelegt; Workflow-Status sichtbar | Screenshot |
| 3.4 | Zweites Requirement anlegen, Titel: `REQ-TP-002 Requirement beta.16` | Artefakt angelegt (Ziel für `WF-*`-Konkurrenztests) | Screenshot |
| 3.5 | Interview-Session starten, Titel: `ITV-TP-001 Interview beta.16` | Session angelegt, Status `in_progress` | Screenshot |
| 3.6 | Zweiten Workspace anlegen, Name: `TP-b16 Workspace B` | Zweiter Workspace existiert | Screenshot |
| 3.7 | Zweiten User anlegen (System-Admin-Bereich), Name: `tp-b16-user-b`, Rolle **Viewer** | User existiert, ist Mitglied von `TP-b16 Workspace` | Screenshot |
| 3.8 | Einen API-Key anlegen (API-Key-Management), Name `TP-b16-key-1` | Key angelegt, Präfix `reqlo_*` sichtbar | Screenshot |

> **REST-Pfade für die Artefaktanlage der Typen aus 3.3–3.5 (außer `requirements/`)
> sind nicht im Scope / nicht verifiziert.** Diese Testdaten werden ausschließlich über die UI angelegt.
> Verifizierter Schreibpfad: `POST /api/v1/requirements/`.

---

## 4. Schwerpunkttests — Neuerungen seit `beta.15`

**MCP-Aufrufschablone** (JSON-RPC 2.0, gilt für alle MCP-Beispiele dieses Abschnitts):

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": { "name": "<tool-name>", "arguments": { } }
}
```

Verfügbare JSON-RPC-Methoden am MCP-Endpoint: `ping`, `initialize`, `tools/list`, `tools/filter`,
`tools/call`. SSE-Endpoint: `.../sse/`.

> **Authentifizierung MCP:** Der API-Key trägt das Präfix `reqlo_*` und wird über das
> API-Key-Management der UI erzeugt. Der **exakte HTTP-Header-Name für den MCP-Transport ist
> nicht verifiziert** — bei der Durchführung den Header der Instanz-Doku/UI entnehmen.

### 4.1 Workflow-Transition: `expected_version` wird erzwungen (CR-08, PR #1073)

> **⚠️ Breaking Change.** Vor diesem Release wurde ein client-gelieferter
> `expected_version` bzw. ein `If-Match`-Header von der View gelesen und
> **stillschweigend verworfen** — solche Requests erhielten `200`. Jetzt antworten sie
> mit **`409 CONFLICT`**, wenn der Workflow-Revisionsstand des Items weitergelaufen ist.
> Clients, die auf das stille Ignorieren vertraut haben, **müssen `409` behandeln**.

**Verifizierte Oberflächen**

| Oberfläche | Referenz |
|---|---|
| Transition ausführen | `POST /api/v1/<entity>/{id}/transitions/` |
| Revision im Antwort-Body | Feld `version` (GET **und** POST der `transitions/`-Route) |
| Revisionsstand im Request-Body | Feld `expected_version` |
| Bedingter Write per Header | `If-Match` |

> **Wichtig — Tag-Semantik:** Auf **dieser** Route (`transitions/`) bezeichnet der Tag
> den **Workflow-Revisionsstand** (`version`). Er ist **nicht** der Entity-ETag, den
> `If-Match` auf `PATCH` trägt und der mit **`412 PRECONDITION_FAILED`** beantwortet wird.

| Test-ID | Ziel | Vorbedingung | Schritte | Erwartetes Ergebnis | Negativfall | Evidence | Pass/Fail |
|---|---|---|---|---|---|---|---|
| `WF-01` | Revision wird im Response der Transition-Route zurückgegeben | `REQ-TP-001` | `GET /api/v1/requirements/{id}/` → Feld `version` notieren; dann `POST .../transitions/` | Der POST-Body enthält `version` mit dem **neuen** Revisionsstand; der Wert ist um genau 1 größer als der GET-Stand vor dem Transition | `version` als **schreibbares** Feld im Request-Body der `transitions/`-Route senden → **400** (read-only) | 2 JSON-Bodies | |
| `WF-02` | Ein **veralteter** `expected_version` ergibt `409 CONFLICT` | `REQ-TP-002` mit bekanntem `version` | Erst `GET` → `version = N`. Danach `POST .../transitions/` mit `expected_version = N - 1` | **`409 CONFLICT`**; der Workflow-Status des Items ist **unverändert** | derselbe Request **ohne** `expected_version` → `200` (last-writer-wins bleibt unverändert) | 3 JSON-Bodies + Screenshot | |
| `WF-03` | Ein **aktueller** `expected_version` ergibt `200` | `REQ-TP-001`, `version = N` | `POST .../transitions/` mit `expected_version = N` | **`200`**; Status wechselt wie erwartet | denselben Request **ein zweites Mal** mit dem jetzt veralteten `N` senden → **`409`** | 2 JSON-Bodies | |
| `WF-04` | Konkurrenzfall: zwei Clients, eine Revision | `REQ-TP-002` | Client A liest `version = N`. Client B führt mit `expected_version = N` eine Transition aus (`200`). Jetzt Client A mit `expected_version = N` | Client A erhält **`409`** — genau **eine** der beiden Transitions hat gewonnen; es entsteht **keine** History-Kante zu einem nie validierten Zielzustand | History des Items prüfen: **genau eine** neue Kante, kein unvalidierter Übergang | 2 JSON-Bodies + Screenshot History | |
| `WF-05` | `If-Match` auf `transitions/` wird ebenfalls ausgewertet | `REQ-TP-001` | `POST .../transitions/` mit veraltetem `If-Match` | **`409 CONFLICT`** | **Abgrenzung:** `If-Match` auf `PATCH` antwortet bei veraltetem Stand mit **`412`**, **nicht** `409` — die beiden Routen unterscheiden sich bewusst | 2 JSON-Bodies | |
| `WF-06` | Ein **ungültiger** Revisionswert wird abgelehnt | `REQ-TP-001` | `POST .../transitions/` mit `expected_version = "abc"` | **400** `VALIDATION_ERROR`; **kein** Statuswechsel | `expected_version` weggelassen bzw. `null` → `200` (unverändert erlaubt) | JSON-Bodies | |

### 4.2 Globale Definition: Atomarität und Orphan-Gate (CR-09/CR-10, PR #1073)

> **⚠️ Breaking Change.** Die Global-Default-State-Endpunkte antworten nun mit
> **`409`**, wenn ein Delete ein **Live-Item verwaissen** würde.

**Verifizierte Oberflächen**

| Oberfläche | Referenz |
|---|---|
| Globaler Default (Liste) | `GET /api/v1/workflow-defaults/` |
| Globaler Default (Detail) | `GET /api/v1/workflow-defaults/{item_type}/{preset}/` |
| States (Liste) | `GET /api/v1/workflow-defaults/{item_type}/{preset}/states/` |
| State (Detail, **Delete**-Ziel) | `DELETE /api/v1/workflow-defaults/{item_type}/{preset}/states/{state_id}/` |
| Transitions | `GET` / `POST /api/v1/workflow-defaults/{item_type}/{preset}/transitions/` |
| Initialisierung | `POST /api/v1/workflow-defaults/{item_type}/{preset}/initialize/` |
| Fehlercode | `409` bei verweigertem Orphan-Delete |

| Test-ID | Ziel | Vorbedingung | Schritte | Erwartetes Ergebnis | Negativfall | Evidence | Pass/Fail |
|---|---|---|---|---|---|---|---|
| `GLB-01` | Ein Delete, der **kein** Live-Item verwaist, funktioniert | Globaler State, der **kein** Item in `TP-b16 Workspace` trägt | `DELETE .../states/{state_id}/` | **`200`/`204`**; der State verschwindet aus der globalen Liste | derselbe Delete als `tp-b16-user-b` (Viewer) → **`403`** `PERMISSION_DENIED` | 2 JSON-Bodies | |
| `GLB-02` | Ein Delete, der ein **Live-Item verwaissen würde**, wird **fail-closed** verweigert | Globaler State, in dem **mindestens ein** Item in `TP-b16 Workspace` liegt | `DELETE .../states/{state_id}/` | **`409`**; der State **existiert weiterhin**; **kein** Item wird verwaist | Item vorher in einen anderen State verschieben, Delete erneut → Delete **gelingt** | 3 JSON-Bodies + Screenshot Item | |
| `GLB-03` | Das Gate ist **atomar** mit dem Write | Wie `GLB-02` | `DELETE` ausführen und **unmittelbar** danach `GET .../states/` | Entweder State **und** alle abgeleiteten Workspace-Zeilen sind weg, **oder** der State ist **vollständig** noch da — **niemals** ein Zwischenzustand, in dem globale Definition und abgeleitete Zeilen auseinanderlaufen | Prüfung über alle Workspaces des Tenants wiederholen: überall derselbe Zustand | 2 JSON-Bodies | |
| `GLB-04` | Ein **customisierter** Workspace wird vom Delete nicht angefasst | Workspace mit eigener State-Anpassung im betroffenen State | `DELETE .../states/{state_id}/`, wobei das verwaissernde Item in einem **anderen** Workspace liegt | `409` — der Item-Blocker gilt **global**, unabhängig von der Customisierung des Ziel-Workspace | Nach dem `409`: die customisierte Zeile des anderen Workspace ist **unverändert** | JSON + Screenshot | |
| `GLB-05` | Propagation in alle erbenden Workspaces | Globaler State-Edit | State umbenennen, dann `GET .../states/` **und** die abgeleiteten States je Workspace lesen | Global und alle nicht-customisierten erbenden Workspaces zeigen **denselben** neuen Namen | Ein customisierter Workspace weicht ab → das ist **erwartet**, kein Fehler | 3+ JSON-Bodies | |
| `GLB-06` | `initialize` und `transitions` bleiben funktionsfähig | Globaler Default für ein `item_type`/`preset`-Paar | `POST .../initialize/`, danach `GET`/`POST .../transitions/` | Initialize legt die Defaults an; Transitions antworten wie bisher | `initialize` für ein **fremdes** `item_type`/`preset`-Paar → **404**/Fehler, **kein** Anlegen | 3 JSON-Bodies | |

### 4.3 Interview-Formalisierung: Lock, Audit, Outbox, Multi-Parität (PR #1073)

**Verifizierte Oberflächen**

| Oberfläche | Referenz |
|---|---|
| Session (Liste/Detail) | `GET /api/v1/interviews/`, `GET /api/v1/interviews/{id}/` |
| Antworten | `POST /api/v1/interviews/{id}/answer/` |
| Vorschlag abrufen | `GET /api/v1/interviews/{id}/propose/` |
| Formalisieren | `POST /api/v1/interviews/{id}/formalize/` |
| Aufgeben | `POST /api/v1/interviews/{id}/abandon/` |
| Zustand | `GET /api/v1/interviews/{id}/state/` |
| MCP | `interview.formalize`, `interview.abandon` |
| Outbox-Event bei `abandon()` | `INTERVIEW_ABANDONED` |

| Test-ID | Ziel | Vorbedingung | Schritte | Erwartetes Ergebnis | Negativfall | Evidence | Pass/Fail |
|---|---|---|---|---|---|---|---|
| `ITV-01` | Single-Formalize schreibt einen `AuditEntry` | `ITV-TP-001` in `in_progress` | `POST /api/v1/interviews/{id}/formalize/` | **`200`**; Session-Status ist abgeschlossen; **genau ein** `AuditEntry` für die Session | Formalisieren einer **nicht** `in_progress`-Session → Fehler, **kein** zusätzlicher Audit-Eintrag | JSON + Screenshot Audit | |
| `ITV-02` | Ein **veraltetes** `abandon()` kann eine frisch formalisierte Session nicht kippen | Session wie `ITV-01`, **danach** `abandon()` senden | `POST /api/v1/interviews/{id}/abandon/` **nach** erfolgreichem `formalize()` | **`409`**/Fehler — der deklarierte Übergang `completed -> abandoned` darf **nicht** greifen; Session bleibt abgeschlossen | ein `abandon()` auf eine **echte** `in_progress`-Session → **gelingt** | 2 JSON-Bodies | |
| `ITV-03` | `abandon()` erzeugt das Outbox-Event `INTERVIEW_ABANDONED` | `in_progress`-Session | `POST .../abandon/`, danach Outbox prüfen | Event `INTERVIEW_ABANDONED` ist **genau einmal** für die Session vorhanden | `abandon()` auf einer bereits abgeschlossenen Session → **kein** zusätzliches Event | 2 JSON-Bodies | |
| `ITV-04` | Ein verschluckter Transition-Pfad bleibt unterscheidbar | Transition, die **nicht** angewendet werden kann | Transition auslösen, die an einer Kante scheitert | Es erscheint eine **Warnung** im Log und der Eintrag ist als `workflow_transition_applied` erfasst — Erfolg und Fehlschlag sind unterscheidbar | derselbe Pfad im Erfolgsfall → **kein** solcher Eintrag | Log-Auszug + JSON | |
| `ITV-05` | Multi-Formalize über **REST** nimmt `confirmed_proposal` an | Multi-Artifact-Session | `GET .../propose/`, dann `POST .../formalize/` mit `{"confirmed_proposal": [...]}` | **`200`**; Antwort enthält eine `created`-Liste und einen `status` | `POST .../formalize/` **ohne** `confirmed_proposal` bei einer Multi-Session → **Fehler** mit dem Hinweis `confirmed_proposal is required for a multi-mode interview` | 2 JSON-Bodies | |
| `ITV-06` | Multi-Formalize über **MCP** ist mit REST **paritätisch** | Multi-Artifact-Session, `TP-b16-key-1` | MCP `tools/call` mit `interview.formalize` und `confirmed_proposal` | **`200`** mit `created`-Liste + `status` — **identisches** Verhalten zu `ITV-05`; der publizierte Multi-Pfad ist **nicht** mehr blockiert | Single-MCP-Aufruf **ohne** Proposal → **gelingt** weiterhin; `confirmed_proposal` ist **optional** im Schema | 2 JSON-Bodies | |

### 4.4 W0/W1 Security-Slice (PR #1070, #1071)

> **Einordnung:** W0 ist **teilweise** umgesetzt — Evidenz-Baseline und W0/W1-Slice
> stehen, die W0-Abschlusskriterien sind **nicht** vollständig erfüllt. W1 liefert
> RLS-Exit-Evidenz, ein strikt read-only Inventar-Command, digest-gelistetes
> actionlint und Negativtests, die bei Regression einer Sicherheitskontrolle
> fehlschlagen. Grüne Tests allein setzen einen Track **nie** auf `VERIFIZIERT`.

| Test-ID | Ziel | Vorbedingung | Schritte | Erwartetes Ergebnis | Negativfall | Evidence | Pass/Fail |
|---|---|---|---|---|---|---|---|
| `SEC-01` | Tenant-Isolation auf Artefakten bleibt gewahrt | `TP-b16 Workspace` **und** `TP-b16 Workspace B`, User in **beiden** mit unterschiedlichen Rollen | Artefakt aus `TP-b16 Workspace B` per ID über den Kontext von `TP-b16 Workspace` anfordern | **Kein** fremdes Artefakt wird ausgeliefert (404/403 je nach Regel) | Rolle im Ziel-Workspace **entziehen** und erneut anfordern → weiterhin kein Zugriff | 2 JSON-Bodies | |
| `SEC-02` | RLS greift auf der Least-Privilege-Rolle | `DB_APP_PASSWORD` gesetzt | Als App-Rolle direkt gegen Postgres connecten, ohne Tenant-Kontext | Abfragen tenant-skoped liefern **keine** fremden Zeilen | Abfrage als **Superuser**-Rolle → andere Sichtbarkeit; das ist erwartet und kein Defekt | SQL-Transkript | |
| `SEC-03` | Workspace-Fence akzeptiert nur kanonische UUIDs | Zwei Workspaces | Fence mit einer nicht-kanonischen Schreibweise einer Workspace-ID übergeben | Der Fence gilt als **gesetzt**; die nicht-kanonische Form wird **nicht** stillschweigend als leer behandelt | Fence mit einer **gültigen kanonischen** UUID eines fremden Workspace → kein Zugriff | 2 JSON-Bodies | |
| `SEC-04` | Security-Negativtests schlagen bei Regression an | Source-Checkout | `python manage.py test` **bzw.** die Backend-Suite ausführen | Die W1-Negativtests sind **grün** im unveränderten Zustand | Eine der tenant-isolierenden Bedingungen lokal verletzen → der zugehörige Test wird **rot** | Test-Ausgabe | |
| `SEC-05` | actionlint-Gate ist aktiv und digest-gelistet | `.github/workflows/` | Workflow-Lint-Job im CI auf dem Basis-Commit ansehen | Job **grün**; das Image ist digest-gelistet (nicht frei beweglich) | ein Workflow mit ungültiger Action-Pin-Definition → Lint meldet den Befund | CI-Link + Log | |

### 4.5 Legacy-API-Key-Inventar (PR #1071)

> **Sicherheitsauflage:** Das Command ist **strikt read-only**. Es darf weder
> Secret-Material **ausgeben** noch irgendeinen Key **verändern**. Wer ein
> Klartext-Secret in der Ausgabe findet, meldet das **sofort** als Blocker.

| Test-ID | Ziel | Vorbedingung | Schritte | Erwartetes Ergebnis | Negativfall | Evidence | Pass/Fail |
|---|---|---|---|---|---|---|---|
| `KEY-01` | Das Inventar listet Legacy-Keys **ohne** Secret-Material | Source-Checkout, gestarteter Stack | `python manage.py inventory_api_keys` im Backend ausführen | Übersicht der vorhandenen Keys mit **maskierten**/identifizierenden Angaben; **kein** Plaintext, **kein** vollständiger Hash | Command-Output nach Secret-Material durchsuchen → **nichts** Gefunden | Terminal-Ausgabe (redigiert) | |
| `KEY-02` | Das Inventar verändert **nichts** | Keys `TP-b16-key-1` und weitere vorhanden | Vorher-/Nachher-Zustand aller Keys vergleichen | **Identischer** Zustand: gleiche Anzahl, gleiche Aktiv-/Revoked-Status | Command **zweimal** ausführen → Zustand bleibt identisch | 2 Command-Ausgaben | |
| `KEY-03` | Der reguläre Key-Lebenszyklus bleibt unverändert | `TP-b16-key-1` | `GET /api/v1/api-keys/`, dann einen Key über die UI/API **revoken** | Key erscheint revoked; nach `cleanup_revoked_api_keys` ist er bereinigt | revoken einen **fremden** Key → **`403`** | JSON-Bodies | |

### 4.6 Bluepencil-Brücke und Login-Timeout-Ursache (PR #1055)

| Test-ID | Ziel | Vorbedingung | Schritte | Erwartetes Ergebnis | Negativfall | Evidence | Pass/Fail |
|---|---|---|---|---|---|---|---|
| `PLT-01` | Bluepencil bleibt im Standardlauf **deaktiviert** | `BLUEPENCIL_ENABLED=0` | Stack starten, Browser-Netzwerkverkehr beobachten | **Kein** Bluepencil-Loader im Netzwerkverkehr; keine Sidecar-Anfragen | `BLUEPENCIL_ENABLED=1` gesetzt → Loader erscheint (erwartet, aber **außerhalb** des Standardlaufs) | Network-Log | |
| `PLT-02` | Die Host-Identitätsbrücke greift im Dev-Modus | Source-Checkout (Dev-Overlay aktiv) | Review-Anker in der Oberfläche prüfen | Anker lösen gegen den **richtigen** Host auf | Review-Anker gegen die Sidecar ohne aktivierte Brücke → **nicht** testbar (DEBUG/QS-only, s. §2.6) | Screenshot | |
| `PLT-03` | Ein Login-Timeout behält seine **Ursache** | Netzwerk zum Backend gezielt stören | Login mit absichtlich erzeugter Timeout-Bedingung auslösen | Die Fehlermeldung **nennt die Ursache** (Timeout) und wird nicht zu einem generischen „Login fehlgeschlagen" | Erneuter Versuch ohne Störung → Login **gelingt** | Screenshot + Log | |

### 4.7 ⚠ Bewusst OFFENE Punkte — nicht testbar, nicht erfüllt

> **Diese Punkte sind absichtlich offen.** Sie sind **keine** Testfälle und
> **keine** Findings für die:n Tester:in. Ein Testlauf **darf** sie nicht als
> „bestanden" oder „geprüft" melden. Sie sind hier vollständig aufgeführt, damit
> die Abgrenzung zwischen „geprüft" und „offen" eindeutig ist.

| Punkt | Status | Bedeutung / was die:n Tester:in daraus **nicht** ableiten darf |
|---|---|---|
| **D1-Constraint** (`UniqueConstraint(session, artifact)`) | **offen** — bewusst zurückgestellt, als benannter Follow-up geführt | Doppelte Zuordnung eines Artefakts zu einer Interview-Session ist **nicht** verhindert. Kein Testfall prüft das. |
| **Correlation-Feld** | **offen** — fehlt vollständig | Das W2-Abschlusskriterium „Tenant, Workspace, Actor, Version **und Correlation**" ist **nicht** erfüllt. Ohne Correlation ist keine Ende-zu-Ende-Korrelation eines Vorgangs über die Kaskade prüfbar. |
| **W2-Negativtest 6** (Chat-/Provider-Ausfall) | **fehlt vollständig** | Es existiert **kein** Negativtest für den Ausfall des Chat-/LLM-Providers. Ein Provider-Ausfall ist **nicht** abgedeckt. |
| **CR-13** | **unberührt** — keine Implementierung, kein Test | Weder implementiert noch getestet. Ein Befund hierzu ist kein Regressionsbeleg. |
| **CR-17**, **CR-22**, **CR-26** | **offen** — von W2 **keines** geschlossen | W2 hat keinen dieser Befunde abgeschlossen. Sie sind als offene bekannte Befunde geführt. |
| **`pl_user`** | **offen** — priorisierter Follow-up | Der Punkt `pl_user` ist unverändert offen. |
| **Service-Wrapper-`expected_version`-Lücke** | **offen** | `WF-*` prüft die **REST-/MCP-Aufrufer** der `WorkflowFacade.transition`. Die **Lücke im Service-Wrapper selbst** ist damit **nicht** abgedeckt — `WF-*` darf nicht als Beweis für sie gewertet werden. |
| **Orphan-Gate-Restfenster** | **offen** — bewusst nicht geschlossen, im Code dokumentiert | `GLB-02`/`GLB-04` prüfen das fail-closed-Gate für **Items**. Das **Restfenster** ist bewusst offen gelassen und **nicht** durch diese Testfälle abgedeckt. |
| **Error-/Status-Semantik über REST + MCP + UI** | **nicht erfüllt** | Das W2-Kriterium „gleiche versionierte Error-/Status-Semantik" über REST, MCP **und UI** ist **nicht** met: die **UI-Schicht wurde nicht angefasst**. Fehlende UI-Abbildung einer Fehlersemantik ist deshalb **kein** QS-Finding. |
| **W3** (Contract/SE-SSOT und Integrationsverträge) | **nicht begonnen** | Kein W3-Artefakt im Delta. |
| **W4** (CI, Release, Resilience, Operations) | **nicht begonnen** | Kein W4-Artefakt im Delta. |
| **W5** (UX, Accessibility, externe Reifeentscheidung) | **nicht begonnen** | Kein W5-Artefakt im Delta. Insbesondere ist die **externe Reifeentscheidung** nicht getroffen. |

---

## 5. Regression-Kurzcheckliste

| Test-ID | Prüfung | Erwartetes Ergebnis | Evidence | Pass/Fail |
|---|---|---|---|---|
| `REG-01` | Login/Logout, Workspace-Wechsel | Funktionieren unverändert | Screenshot | |
| `REG-02` | Requirements-CRUD inkl. PATCH | Anlegen, Ändern, Löschen funktionieren | Screenshot | |
| `REG-03` | TestCase-CRUD | Anlegen, Ändern funktionieren; `origin` bleibt **nicht** editierbar (read-only) | Screenshot | |
| `REG-04` | `GET /health/` und `GET /api/v1/admin/health/` | Beide HTTP `200` | JSON | |
| `REG-05` | MCP `ping` / `initialize` / `tools/list` | Antworten gemäß JSON-RPC 2.0 | JSON | |
| `REG-06` | Bluepencil bleibt deaktiviert | Kein Bluepencil-Loader im Netzwerkverkehr | Network-Log | |
| `REG-07` | `docker compose config -q` für beide Deployment-Dateien | Exit 0 (im Repo verifiziert) | Terminal | |
| `REG-08` | Build-Artefakte erscheinen nicht im Git-Status | `frontend/tsconfig*.tsbuildinfo` und `frontend/vite.config.{js,d.ts}` sind ignoriert | `git status` | |
| `REG-09` | CI auf dem Release-Basis-Commit | **grün** — 2 Runs, 14/14 Check-Runs `success` (bereits verifiziert, nicht manuell nachzufahren) | CI-Link | |
| `REG-10` | Versions-Carrier sind konsistent | `VERSION`, `frontend/package.json`, Hermes-Plugin, `dist`-Plugins, `.env.example`, beide Compose-Dateien und Site tragen **alle** `1.8.0-beta.16` | `git grep "1.8.0-beta.16"` | |
| `REG-11` | Keine Produktverhaltensänderung aus den Meta-PRs | #1069 (Doku) und #1072 (nur `.meta-config/project.yaml`) ändern **kein** Produktverhalten | Diff der beiden PRs | |

---

## 6. Bekannte Grenzen & Hinweise

### 6.1 Umgebungs- und Known-Gate-Hinweise

| Punkt | Status |
|---|---|
| **Kein Image `1.8.0-beta.16` / kein Digest** | Für diesen Schnitt wurde **kein Image gebaut**. Ein image-basierter Testlauf ist **nicht möglich**; §2.4 nutzt zwingend den Source-Checkout (siehe 1.3) |
| **CI-Skip des Live-Stack-Testmoduls** | `backend/mcp_server/tests/test_mcp_api_key_roles.py` ist in CI **bewusst übersprungen** (`skipif` auf `CI`/`GITHUB_ACTIONS`). Ein Fehlen dieser Tests in CI ist **erwartet** und **kein** Befund |
| **Lokales Test-Gate ist kein Release-Gate** | Das maßgebliche Gate ist der **CI-Lauf auf dem Release-Basis-Commit**. `make test` ist laut Projektkonvention **kein** Release-Gate (Release-Bericht §6.4) |
| **Bekannte lokale Reds** | 4 Backend-Errors (Live-Stack-Testvoraussetzung) und 2–3 Frontend-Timeouts in Dateisystem-Ratchets sind **nicht attributierbar** und **keine Produktdefekte** (Release-Bericht §6.1/§6.2) |
| **Frontend-Volllauf ist nicht deterministisch** | Derselbe Volllauf ergab einmal 2 und einmal 3 Timeout-Failures (lastinduziert). Ein einzelner Volllauf ist **kein** verlässliches QS-Signal; isolierte Läufe sind aussagekräftiger |
| **MCP-HTTP-Header-Name für API-Keys** | **nicht verifiziert** — der Instanz-Doku/UI entnehmen |
| **Pre-Release-Gate-Hook unter Windows** | Der deployte Hook kann CRLF-Zeilenenden haben; für reproduzierbare Läufe unter Linux ist eine LF-Normalisierung nötig (Release-Bericht, entsprechender Abschnitt) |

### 6.2 Nicht-QS-Freigabe

Dieser Testplan **erteilt keine Freigabe**. Er **beschreibt** QS-Testfälle für
einen internen Beta-Cut, dessen Wellen W0/W1/W2 **teilweise** umgesetzt sind, dessen
regressionssuiten **nicht** grün sind und dessen W3–W5 **nicht begonnen** wurden.
Die vollständige Liste der bewusst offenen Punkte steht in §4.7. Eine
Production-, Staging- oder QA-Freigabe für `1.8.0-beta.16` ist damit **nicht**
erteilt.

---

## 7. Defekt-Meldevorlage

### Defekt <ID / laufende Nummer>

| Feld | Inhalt |
|---|---|
| **Test-ID** | z. B. `WF-04` |
| **Release** | `1.8.0-beta.16` |
| **Image-Tag** | **keiner** — es existiert kein Image dieses Cuts; Umgebung ist ein Source-Checkout (siehe 1.3) |
| **Umgebung** | OS, Browser, `BACKEND_PORT`/`FRONTEND_PORT`, Profil (Standard/Honcho) |
| **Schritte** | 1. … 2. … 3. … |
| **Erwartet** | … |
| **Beobachtet** | … |
| **HTTP-Status / Fehlercode** | z. B. `409 CONFLICT` bzw. MCP-Fehlercode |
| **Evidence** | `evidence/<TEST-ID>_<nr>.png` / `.json` |
| **Reproduzierbar** | immer / manchmal / einmalig |
| **Gehört zu §4.7?** | ja/nein — falls **ja**, ist der Befund **kein** QS-Finding (siehe 6.2) |

---

## 8. Abnahme / Sign-off

### 8.1 Prüfübersicht

| Bereich | Testfälle | Bestanden | Fehlgeschlagen | Offen |
|---|---|---|---|---|
| §4.1 Workflow-Transition (`WF-*`) | 6 | | | |
| §4.2 Globale Definition (`GLB-*`) | 6 | | | |
| §4.3 Interview-Formalisierung (`ITV-*`) | 6 | | | |
| §4.4 W0/W1 Security-Slice (`SEC-*`) | 5 | | | |
| §4.5 Legacy-API-Key-Inventar (`KEY-*`) | 3 | | | |
| §4.6 Bluepencil/Login (`PLT-*`) | 3 | | | |
| §5 Regression (`REG-*`) | 11 | | | |
| **Summe Testfälle** | **40** | | | |
| §4.7 bewusst offene Punkte (Dokumentation, **keine** Testfälle) | 12 Einträge | — | — | 12 |

> Die 12 Einträge in §4.7 sind **keine** Testfälle und gehen **nicht** in die
> Summe der 40 ein. Sie sind vollständig offen und dürfen nicht als geprüft
> gemeldet werden.

### 8.2 Release-Empfehlung

- [ ] Freigabe ohne Einschränkung
- [ ] Freigabe mit bekannten Einschränkungen (siehe §6)
- [ ] Keine Freigabe (Blocker siehe Defektliste)

> **Ausgangslage:** Die W0/W1/W2-Abschlusskriterien sind **nicht** met, kein Track
> ist `VERIFIZIERT`, W3–W5 sind **nicht begonnen** (siehe §4.7 und §6.2). Dieser
> Plan ist daher **keine** Freigabeempfehlung für `1.8.0-beta.16`.

### 8.3 Unterschriften

| Rolle | Name | Datum | Unterschrift |
|---|---|---|---|
| Tester:in | | | |
| Release-Owner | | | |
