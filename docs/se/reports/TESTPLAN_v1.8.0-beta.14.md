---
type: STRATEGY
scope: Testplan v1.8.0-beta.14
status: final
date: 2026-09-21
author_agent: documenter
---

# Testplan v1.8.0-beta.14

> **Hand-off-Testplan.** Dieses Dokument ist für eine:n **externe:n Tester:in ohne Vorkenntnisse** geschrieben.
> Alle Schritte sind so formuliert, dass sie ohne Repository-Wissen, ohne Agenten-Kontext und ohne
> Vorwissen über die Historie ausgeführt werden können. Jeder Testfall hat einen **Negativfall** und
> eine **Evidence**-Zeile. Die Pass/Fail-Spalte wird während der Durchführung ausgefüllt.

**Durchführungshinweise**

- **Test-IDs** sind stabil: `MEM-*`, `UID-*`, `ATTR-*`, `TRC-*`, `LNK-*`, `BKP-*`, `OCS-*`, `REG-*`.
  In Fehlermeldungen immer die Test-ID mitnennen.
- **Evidence** wird pro Testfall als Datei abgelegt: Screenshot als `evidence/<TEST-ID>_<nr>.png`,
  Response-Body als `evidence/<TEST-ID>_<nr>.json` bzw. `.txt`.
- **UI-Klickwege** beginnen jeweils mit der Annahme: angemeldet, korrektes Workspace geöffnet.
- **REST-Beispiele** sind gegen `http://localhost:8001/api/v1/` gedacht (bzw. den konfigurierten `BACKEND_PORT`).
  Mit `Authorization`-Header des angemeldeten Users (JWT) ausführen, sofern nicht anders angegeben.
- **MCP-Beispiele** sind JSON-RPC-2.0-Bodies gegen `http://localhost:8001/mcp/`
  (alternativ `/api/v1/mcp/`). Der MCP-Server ist an **beiden** Pfaden gemountet.
- **Verbot von Erfundenen:** Es werden ausschließlich die in diesem Dokument genannten Routen, Tools
  und Variablen verwendet. Für Bereiche ohne verifizierte Angabe steht ausdrücklich
  „nicht im Scope / nicht verifiziert".

---

## 1. Ziel & Prüfgegenstand

| Feld | Wert |
|---|---|
| Release | **1.8.0-beta.14** |
| Backend-Image | `ghcr.io/popoboxxo/reqogniloom-backend:1.8.0-beta.14` |
| Frontend-Image | `ghcr.io/popoboxxo/reqogniloom-frontend:1.8.0-beta.14` |
| Commit-SHA | `06978ba4549bb170276cb9f0e78d822bffd4c0b4` |
| Datum | 2026-09-21 |
| Branch | `chore/release-v1.8.0-beta.14` |
| Vorgänger-Release | `1.8.0-beta.13` (Vergleichsbasis) |

### 1.1 Im Scope (Delta seit `1.8.0-beta.13`)

| Delta (PR) | Thema | Testbereich |
|---|---|---|
| #1017 | Report-Finalisierung | §4.1 (Digest), §5 REG-12 |
| #1020 | Memory A: vereinheitlichter Store | §4.1 |
| #1022 | Memory B: Service/Policy/MCP/REST | §4.1 |
| #1023 | Memory C: Artefakt-Scope + Prompt-Injektion | §4.1 (MEM-05/06) |
| #1024 | Memory D: UI | §4.1 |
| #1025 | F6: Honcho-Sessions/Deriver/`digest` | §4.1 (MEM-07/12) |
| #1026 | Tool-Zahl 215 + `.playwright-mcp` ignoriert | §5 REG-15 |
| #1027 | `x-opencode-session` + DNS-Runbook | §4.7 |
| — | uid (#932) | §4.2 |
| — | INCOSE/IEEE-Attribute (#871/#583) | §4.3 |
| — | Trace-Katalog (#950) | §4.4 |
| — | Link-Defaults aus env (#989) | §4.5 |
| — | Admin-Backup gzip (#823) | §4.6 |

### 1.2 Nicht im Scope

- **`bluepencil`** — die optionale selbst-gehostete Review-Sidecar ist **DEBUG/QS-only**
  und wird im Standard-Testlauf **nicht aktiviert und nicht getestet** (siehe Warnbox §2.7).
- **Live-only-Punkte L1–L8** (siehe §6) — benötigen eine echte Instanz mit echter
  Provider-Konnektivität und sind offline nicht validierbar.
- **Last-, Performance- und Sicherheits-Penetrationstests** — nicht Bestandteil dieses Testplans.
- **REST-Pfade für Artefakttypen außerhalb der verifizierten Liste** — nicht im Scope / nicht verifiziert.
  Testdaten für diese Typen werden ausschließlich über die UI angelegt.

---

## 2. Vorbedingungen (exakt)

### 2.1 Host-Voraussetzungen

- **Docker Engine** (aktuell, lauffähig).
- **Docker Compose v2 als Plugin** — das Kommando ist `docker compose` (Leerzeichen),
  **nicht** `docker-compose` (Bindestrich). Prüfen: `docker compose version`.
- Freie Ports `8001` (Backend) und `5173` (Frontend), sofern nicht via env überschrieben (§2.3).
- Netzwerkzugriff auf `ghcr.io` zum Ziehen der Images.

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
| `SYSTEM_ADMIN_PASSWORD` | Passwort des initialen Admin | **Pflicht bei frischem System** — ohne Wert wird der Admin nicht angelegt |

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
> geänderter Port genügt nicht — es kommt sonst zu Portkollisionen bzw. inkonsistenten URLs.

### 2.4 Stack starten (kanonisch)

Standardstart:

```bash
docker compose -f deploy/docker-compose.yml --project-directory . up -d
```

Start **mit Honcho-Profil** (nur wenn Honcho-Tests durchgeführt werden, siehe §4.1 MEM-12):

```bash
docker compose -f deploy/docker-compose.yml --profile honcho --project-directory . up -d
```

### 2.5 Health-Check

```bash
curl localhost:8001/health/
```

Der Health-Endpoint liegt auf Pfad **`/health/`** (Backend-Root-URLconf; beachten: **mit** Trailing Slash).

Zusätzlich der Admin-Systemstatus (Dashboard-Sicht):

```
GET /api/v1/admin/health/
```

Erwartet: HTTP `200` und ein JSON-Body. In diesem Body prüft der Testlauf insbesondere die
Komponente `memory_backend` (§4.1 MEM-13). Über `curl localhost:8001/health/` ist zusätzlich
das Feld `csrf_cookie_secure_matches_auth` sichtbar; dieses darf **nicht** `"mismatch"` sein
(CSRF-/Cookie-Kopplung, siehe `deploy/README.md`, Abschnitt „First Stumbling Block").

### 2.6 Optionale Vorbedingungen

**Honcho (optional, nur mit `--profile honcho`):**

| Variable | Zweck |
|---|---|
| `HONCHO_BASE_URL` | Basis-URL der Honcho-Instanz |
| `HONCHO_API_KEY` | API-Key der Honcho-Instanz |
| `HONCHO_EMBEDDING_BASE_URL` | Embedding-Endpoint (inkl. `/v1`-Suffix) |
| `HONCHO_EMBEDDING_MODEL` | Embedding-Modell |
| `HONCHO_EMBEDDING_VECTOR_DIMENSIONS` | Vektorbreite (muss zum Modell passen) |
| `HONCHO_EMBEDDING_TRANSPORT` | Transport des Embedding-Endpoints |

**Ollama (optional, für lokale Embeddings):**

| Variable | Default | Zweck |
|---|---|---|
| `OLLAMA_BASE_URL` | `http://localhost:11434` | lokaler Ollama-Endpoint |

### 2.7 ⚠ WARNUNG: `bluepencil`

> **`bluepencil` (optionale selbst-gehostete Review-Sidecar) ist DEBUG/QS-only.**
> Sie darf im **Standard-Testlauf nicht aktiviert und nicht getestet** werden. Es gibt **keinen**
> Auth- und **keinen** Tenant-Isolation-Schutz, und eine einzige JSON-Datei hält die Notizen
> **aller** Workspaces. `BLUEPENCIL_ENABLED=0` muss im Testlauf gesetzt bleiben.
> Ein Bluepencil-Befund ist **kein** Release-Blocker für `1.8.0-beta.14` — er ist außerhalb des Scopes.

### 2.8 Memory-Backend & Schreib-Rate-Limit

| Variable | Werte | Default | Bedeutung |
|---|---|---|---|
| `MEMORY_BACKEND` | `pgvector` \| `honcho` | `pgvector` | Auswahl des Memory-Backends |
| `MEMORY_WRITE_RATE_LIMIT_PER_HOUR` | Ganzzahl, `0` = unbegrenzt | `60` | Fixed-Window-Schreiblimit für `memory.write`, pro `(tenant, user)` |

> **Wichtig für die Bewertung:** Ein Schreib-Burst oberhalb von 60 Schreibvorgängen pro Stunde ist
> **kein Defekt**, sondern das erwartete Rate-Limit. Für Purge-/Massen-Schreibtests entweder
> `MEMORY_WRITE_RATE_LIMIT_PER_HOUR=0` setzen oder die Einstellung über
> `PUT /api/v1/system/memory-settings/` (System-Admin) anheben und danach
> `POST /api/v1/system/memory-settings/reset/` verwenden.

---

## 3. Vorbereitung Testdaten

Alle Testdaten werden in einem **eigenen Workspace** angelegt, damit Purge-Tests (§4.1 MEM-11/12)
nichts anderes zerstören.

| Schritt | Aktion (UI) | Erwartetes Ergebnis | Evidence |
|---|---|---|---|
| 3.1 | Anmelden mit `SYSTEM_ADMIN_USERNAME` / `SYSTEM_ADMIN_PASSWORD` | Login erfolgreich, Dashboard sichtbar | Screenshot |
| 3.2 | Workspace anlegen, Name: `TP-b14 Workspace` | Workspace erscheint in der Workspace-Liste | Screenshot |
| 3.3 | Goal/Stakeholder-Need anlegen, Titel: `SN-TP-001 Stakeholder Need beta.14` | Artefakt angelegt, `uid` vergeben (vgl. §4.2) | Screenshot |
| 3.4 | Requirement anlegen, Titel: `REQ-TP-001 Requirement beta.14` | Artefakt angelegt, `uid` vergeben | Screenshot |
| 3.5 | Architecture Element anlegen, Titel: `ARCH-TP-001 Architektur beta.14` | Artefakt angelegt, `uid` vergeben | Screenshot |
| 3.6 | TestCase anlegen, Titel: `TC-TP-001 Testfall beta.14` | Artefakt angelegt, `uid` vergeben | Screenshot |
| 3.7 | Zweiten Workspace anlegen, Name: `TP-b14 Workspace B` | Zweiter Workspace existiert, eigener Zählerstand für `uid` (§4.2) | Screenshot |
| 3.8 | Zweiten User anlegen (System-Admin-Bereich), Name/Mail: `tp-b14-user-b` | User existiert und ist Mitglied von `TP-b14 Workspace` | Screenshot |

> **REST-Pfade für die Artefaktanlage der Typen aus 3.3–3.6 (außer `requirements/`) sind nicht im Scope
> / nicht verifiziert.** Diese Testdaten werden ausschließlich über die UI angelegt. Für Requirements
> darf zusätzlich der verifizierte Pfad `POST /api/v1/requirements/` (bzw. `PATCH /api/v1/requirements/`)
> genutzt werden.
>
> Die Namen `SN-TP-001`, `REQ-TP-001`, `ARCH-TP-001`, `TC-TP-001`, `TP-b14 Workspace`,
> `TP-b14 Workspace B` werden in späteren Testfällen referenziert.

---

## 4. Schwerpunkttests — Neuerungen seit `beta.13`

Jeder Testfall ist als Metadaten-Tabelle mit den Feldern **Test-ID**, **Ziel**, **Vorbedingung**,
**Schritte (UI)** und **Schritte (REST/MCP)**, **Erwartetes Ergebnis**, **Negativfall**, **Evidence**
und **Pass/Fail** dokumentiert. Beispiel-Payloads stehen als JSON-Block direkt unter der Tabelle.

**MCP-Aufrufschablone** (JSON-RPC 2.0, gilt für alle MCP-Beispiele dieses Abschnitts):

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "<tool-name>",
    "arguments": { }
  }
}
```

Verfügbare JSON-RPC-Methoden am MCP-Endpoint: `ping`, `initialize`, `tools/list`, `tools/filter`,
`tools/call`. SSE-Endpoint: `.../sse/`.

> **Authentifizierung MCP:** Der API-Key trägt das Präfix `reqlo_*` und wird über das
> API-Key-Management der UI erzeugt. Der **exakte HTTP-Header-Name für den MCP-Transport ist
> nicht verifiziert** — bei der Durchführung den Header der Instanz-Doku/UI entnehmen.

### 4.1 Workspace-Gedächtnis v2 (RFC #1002)

**Verifizierte REST-Routen** (Mount-Präfix `/api/v1/`):

| Methode(n) | Pfad |
|---|---|
| `GET`, `POST` | `/api/v1/workspaces/<workspace_id>/memory/entries/` |
| `GET` | `/api/v1/workspaces/<workspace_id>/memory/search/` |
| `GET` | `/api/v1/workspaces/<workspace_id>/memory/digest/` |
| `GET`, `DELETE` | `/api/v1/memory/entries/<entry_id>/` |
| `POST` | `/api/v1/memory/entries/<entry_id>/promote/` |
| `GET`, `POST` | `/api/v1/artifacts/<artifact_id>/memory/` |
| `GET` | `/api/v1/artifacts/<artifact_id>/memory/digest/` |
| `GET`, `PUT` | `/api/v1/workspaces/<workspace_id>/memory-settings/` |
| `GET`, `PUT` | `/api/v1/system/memory-settings/` |
| `POST` | `/api/v1/system/memory-settings/reset/` |
| `GET` | `/api/v1/system/memory/workspaces/` |
| `DELETE` | `/api/v1/system/memory/workspaces/<workspace_id>/` |
| `GET` | `/api/v1/system/memory/entries/` |
| `GET` | `/api/v1/system/memory/projection/` |
| `GET` | `/api/v1/system/memory/entries/export/?format=json\|csv` |
| `GET`, `DELETE` | `/api/v1/memory/me/` |

**Verifizierte MCP-Tools** (exakt diese sechs, Punktnotation):

| Tool | Parameter |
|---|---|
| `memory.write` | `content` (erforderlich), `scope` (erforderlich; `workspace`\|`user`\|`artifact`), `workspace_id`, `artifact_id`, `confidence` (Default `1.0`), `change_reason` |
| `memory.get` | `entry_id` (erforderlich) |
| `memory.digest` | `workspace_id` (erforderlich), `artifact_id` |
| `memory.query` | `query` (erforderlich), `scope`, `scopes[]`, `workspace_id`, `artifact_id`, `top_k` (Default `5`) |
| `memory.list` | `scope`, `workspace_id`, `artifact_id`, `limit`/`page`/`page_size`, `contributor_user_id` |
| `memory.forget` | `entry_id` (erforderlich), `change_reason` |

> **Achtung Schreibweise:** Das Tool heißt **`memory.forget`** (Punktnotation). Die Schreibweise
> `memory_forget` (Unterstrich) ist **falsch** und existiert nur als Tippfehler in `.env.example`.
>
> **Scope-Werte** sind exakt `user`, `workspace`, `artifact`.
>
> **Body-Felder `POST .../memory/entries/`:** `content` (erforderlich), `confidence` (Default `1.0`),
> `change_reason`. Der **Artefakt-Endpoint erzwingt Scope `artifact`**, der **Workspace-Endpoint
> erzwingt Scope `workspace`**.

#### MEM-01 — Bewusstes Schreiben über die UI

| Feld | Inhalt |
|---|---|
| **Test-ID** | MEM-01 |
| **Ziel** | Ein Fakt lässt sich explizit über die UI („Fakt hinzufügen") im Workspace-Scope anlegen. |
| **Vorbedingung** | `TP-b14 Workspace` geöffnet; `MEMORY_BACKEND=pgvector`. |
| **Schritte (UI)** | 1. Memory-Seite des Workspace öffnen.<br>2. Aktion „Fakt hinzufügen" wählen.<br>3. `content` = `Der Freigabeprozess erfordert zwei Reviewer.`, `confidence` = `0.9`, `change_reason` = `Testplan MEM-01`.<br>4. Speichern. |
| **Schritte (REST/MCP)** | Kontrollabruf: `GET /api/v1/workspaces/<workspace_id>/memory/entries/` |
| **Erwartetes Ergebnis** | Der Eintrag erscheint in der Liste mit `content`, `confidence=0.9`, `change_reason="Testplan MEM-01"`, Scope `workspace`. Ein `entry_id` ist vergeben. |
| **Negativfall** | Leerer `content` wird abgelehnt (Validierungsfehler, HTTP 400) und erzeugt **keinen** Eintrag. |
| **Evidence** | `evidence/MEM-01_1.png` (UI-Liste), `evidence/MEM-01_2.json` (GET-Response) |
| **Pass/Fail** | [ ] Pass [ ] Fail |

#### MEM-02 — Provenienz (wer/wann/warum)

| Feld | Inhalt |
|---|---|
| **Test-ID** | MEM-02 |
| **Ziel** | Beim Lesen sind Contributor und `change_reason` nachvollziehbar (Provenienz). |
| **Vorbedingung** | MEM-01 erfolgreich. |
| **Schritte (UI)** | 1. Memory-Eintrag aus MEM-01 öffnen (Detail-/Listenansicht mit Metadaten).<br>2. Contributor, Zeitstempel und `change_reason` ablesen. |
| **Schritte (REST/MCP)** | `GET /api/v1/workspaces/<workspace_id>/memory/entries/` und `GET /api/v1/memory/entries/<entry_id>/` |
| **Erwartetes Ergebnis** | Der Eintrag liefert Contributor (= angemeldeter User), Erstellzeitpunkt und `change_reason="Testplan MEM-01"` konsistent in UI und REST-Response. |
| **Negativfall** | Ein `change_reason` ohne inhaltlichen Bezug (z. B. leerer String) darf nicht als erfundenes Datum/Uhrzeit dargestellt werden — Provenienz bleibt bei fehlender Angabe leer/nicht gesetzt, nicht geraten. |
| **Evidence** | `evidence/MEM-02_1.png` (UI-Detailansicht), `evidence/MEM-02_2.json` |
| **Pass/Fail** | [ ] Pass [ ] Fail |

#### MEM-03 — Bewusstes Schreiben über MCP (`memory.write`, Scope `artifact`)

| Feld | Inhalt |
|---|---|
| **Test-ID** | MEM-03 |
| **Ziel** | `memory.write` legt mit explizitem Scope `artifact` einen Fakt an einem Artefakt an. |
| **Vorbedingung** | API-Key (`reqlo_*`) vorhanden; `artifact_id` von `REQ-TP-001` bekannt. |
| **Schritte (UI)** | 1. Requirement `REQ-TP-001` öffnen.<br>2. Artefakt-Memory-Panel aufrufen und prüfen, dass der per MCP geschriebene Fakt dort sichtbar ist. |
| **Schritte (REST/MCP)** | MCP `tools/call` mit `memory.write` (Payload unten). |
| **Erwartetes Ergebnis** | Neue `entry_id`, Scope `artifact`, Zuordnung zum Artefakt sichtbar im Artefakt-Panel und in `GET /api/v1/artifacts/<artifact_id>/memory/`. |
| **Negativfall** | `memory.write` mit `scope: "artifact"`, aber **ohne** `artifact_id` wird abgelehnt (HTTP-/JSON-RPC-Fehler) statt still im Workspace-Scope zu landen. |
| **Evidence** | `evidence/MEM-03_1.json` (MCP-Response), `evidence/MEM-03_2.json` (Artefakt-Memory-GET), `evidence/MEM-03_3.png` (Panel) |
| **Pass/Fail** | [ ] Pass [ ] Fail |

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "memory.write",
    "arguments": {
      "content": "REQ-TP-001 muss gegen SN-TP-001 verifizierbar sein.",
      "scope": "artifact",
      "artifact_id": 12345,
      "confidence": 0.8,
      "change_reason": "Testplan MEM-03"
    }
  }
}
```

#### MEM-04 — Lesen/Suchen: identische Semantik über UI, REST und MCP

| Feld | Inhalt |
|---|---|
| **Test-ID** | MEM-04 |
| **Ziel** | Für denselben Suchbegriff liefern UI, REST (`/memory/search/`) und MCP (`memory.query`) inhaltlich identische Treffer. |
| **Vorbedingung** | MEM-01 und MEM-03 erfolgreich (mindestens zwei Fakten). |
| **Schritte (UI)** | 1. Memory-Suche öffnen.<br>2. Suchbegriff `Reviewer` eingeben.<br>3. Treffermenge notieren. |
| **Schritte (REST/MCP)** | REST: `GET /api/v1/workspaces/<workspace_id>/memory/search/?q=Reviewer`<br>MCP: `tools/call` mit `memory.query` (Payload unten). |
| **Erwartetes Ergebnis** | Alle drei Wege liefern den/die Treffer zum Begriff `Reviewer`; die inhaltliche Treffermenge ist identisch (Top-k kann durch `top_k` variieren, Default `5`). Keine Abweichung in der Trefferzahl ohne erklärendes Argument. |
| **Negativfall** | Ein Suchbegriff ohne Treffer (z. B. `xyzzy-kein-treffer`) liefert in allen drei Wegen eine **leere** Treffermenge — und dies ist unterscheidbar von einem `degraded`-Fehler (siehe MEM-13). |
| **Evidence** | `evidence/MEM-04_1.png` (UI), `evidence/MEM-04_2.json` (REST), `evidence/MEM-04_3.json` (MCP) |
| **Pass/Fail** | [ ] Pass [ ] Fail |

```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "tools/call",
  "params": {
    "name": "memory.query",
    "arguments": { "query": "Reviewer", "workspace_id": 42, "top_k": 5 }
  }
}
```

#### MEM-05 — Artefakt-Scope über REST-Override

| Feld | Inhalt |
|---|---|
| **Test-ID** | MEM-05 |
| **Ziel** | Ein Fakt, der über den Artefakt-Endpoint geschrieben wird, ist dem Artefakt zugeordnet und im Artefakt-Panel sichtbar. |
| **Vorbedingung** | `artifact_id` von `REQ-TP-001`. |
| **Schritte (UI)** | 1. `REQ-TP-001` öffnen.<br>2. Artefakt-Memory-Panel öffnen.<br>3. Fakt mit `content` = `Der Fakt gilt nur für dieses Requirement.` anlegen. |
| **Schritte (REST/MCP)** | `POST /api/v1/artifacts/<artifact_id>/memory/` mit Payload unten; danach `GET /api/v1/artifacts/<artifact_id>/memory/`. |
| **Erwartetes Ergebnis** | Der Eintrag ist mit Scope `artifact` dem Artefakt zugeordnet. Ein im Request mitgeschickter abweichender Scope wird **ignoriert/überschrieben** (Endpoint erzwingt `artifact`). Kein globaler Workspace-Eintrag entsteht. |
| **Negativfall** | Request mit `scope: "workspace"` an den Artefakt-Endpoint darf **nicht** einen Workspace-Scope-Eintrag erzeugen (der Endpoint erzwingt `artifact`). Gegenprobe: Eintrag fehlt in `GET /api/v1/workspaces/<workspace_id>/memory/entries/`. |
| **Evidence** | `evidence/MEM-05_1.json` (POST-Response), `evidence/MEM-05_2.json` (Artefakt-GET) |
| **Pass/Fail** | [ ] Pass [ ] Fail |

```json
{
  "content": "Der Fakt gilt nur für dieses Requirement.",
  "confidence": 1.0,
  "change_reason": "Testplan MEM-05"
}
```

#### MEM-06 — Prompt-Injektion (artifact-first, fail-open)

| Feld | Inhalt |
|---|---|
| **Test-ID** | MEM-06 |
| **Ziel** | Artefakt- und Workspace-Fakten fließen als Kontext in LLM-Aktionen ein. |
| **Vorbedingung** | MEM-03/MEM-05 erfolgreich; `LLM_PROVIDER=mock` (sofern eine LLM-Aktion damit auslösbar ist). |
| **Schritte (UI)** | 1. `REQ-TP-001` öffnen.<br>2. Eine LLM-nutzende Aktion auslösen, z. B. Dekomposition oder Validierung.<br>3. Ergebnis/Log darauf prüfen, dass Kontextsektionen enthalten waren. |
| **Schritte (REST/MCP)** | Kein verifizierter REST/MCP-Endpoint für Prompt-Injektion im Scope. Prüfung erfolgt über die LLM-Aktion in der UI. |
| **Erwartetes Ergebnis** | Der aufgebaute Prompt enthält die Sektionen **`Artifact context:`**, **`Workspace context:`**, **`User context:`** — in **artifact-first**-Reihenfolge. Die Injektion ist **fail-open**: fehlt Kontext oder schlägt der Aufbau fehl, läuft die Aktion trotzdem durch (ohne Kontext), statt zu scheitern. |
| **Negativfall** | Bei **leerem** Memory (keine Fakten) darf die LLM-Aktion nicht fehlschlagen — sie läuft ohne Kontextsektionen durch (fail-open). |
| **Evidence** | `evidence/MEM-06_1.png` (Aktionsergebnis), `evidence/MEM-06_2.txt` (Prompt-/Kontext-Nachweis, soweit einsehbar) |
| **Pass/Fail** | [ ] Pass [ ] Fail |

> **Live-only:** Der inhaltliche Nachweis, dass die Sektionen mit **echten** Provider-Antworten
> befüllt werden, ist nur mit realer Provider-Konnektivität belastbar (siehe §6, L1).

#### MEM-07 — `digest` über MCP, REST und UI

| Feld | Inhalt |
|---|---|
| **Test-ID** | MEM-07 |
| **Ziel** | Die Digest-Funktion ist über alle drei Kanäle verfügbar und liefert eine Zusammenfassung des Workspace-Gedächtnisses. |
| **Vorbedingung** | Mindestens drei Fakten im `TP-b14 Workspace` (MEM-01/03/05). |
| **Schritte (UI)** | 1. Memory-Seite öffnen.<br>2. Digest anzeigen (Digest-Bereich/Aktion). |
| **Schritte (REST/MCP)** | REST: `GET /api/v1/workspaces/<workspace_id>/memory/digest/`<br>MCP: `memory.digest` mit `workspace_id` (Payload unten).<br>Artefaktbezogen: `GET /api/v1/artifacts/<artifact_id>/memory/digest/` |
| **Erwartetes Ergebnis** | Alle Kanäle liefern einen Digest; der Antwort-Umschlag enthält die Health-Keys (`digest_available` u. a., siehe MEM-13). Ist `digest_available` falsch, wird dies **explizit** ausgewiesen, nicht als leere Antwort verschwiegen. |
| **Negativfall** | `memory.digest` ohne `workspace_id` wird als Fehler zurückgegeben (Parameter ist erforderlich). |
| **Evidence** | `evidence/MEM-07_1.json` (REST), `evidence/MEM-07_2.json` (MCP), `evidence/MEM-07_3.png` (UI) |
| **Pass/Fail** | [ ] Pass [ ] Fail |

```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "method": "tools/call",
  "params": {
    "name": "memory.digest",
    "arguments": { "workspace_id": 42 }
  }
}
```

#### MEM-08 — Auflisten & Filtern (`memory.list`)

| Feld | Inhalt |
|---|---|
| **Test-ID** | MEM-08 |
| **Ziel** | Fakten lassen sich scoped und paginiert auflisten. |
| **Vorbedingung** | Fakten in Scope `workspace` und `artifact` vorhanden. |
| **Schritte (UI)** | 1. Memory-Seite öffnen.<br>2. Filter auf Scope `artifact` setzen.<br>3. Liste mit der MCP-Antwort vergleichen. |
| **Schritte (REST/MCP)** | MCP: `memory.list` mit `scope`/`workspace_id`/`limit` bzw. `page`/`page_size` und optional `contributor_user_id`. |
| **Erwartetes Ergebnis** | Der Scope-Filter wirkt; Paginierung (`limit` bzw. `page`/`page_size`) verändert die Treffermenge wie erwartet; `contributor_user_id` filtert auf den angegebenen Beitragenden. |
| **Negativfall** | `limit` mit unsinnigem Wert (z. B. negativ oder `0`) wird abgelehnt bzw. auf einen gültigen Bereich begrenzt — kein unbehandelter Serverfehler (HTTP 5xx). |
| **Evidence** | `evidence/MEM-08_1.json` (MCP-Response), `evidence/MEM-08_2.png` (UI-Filter) |
| **Pass/Fail** | [ ] Pass [ ] Fail |

#### MEM-09 — Forget einzelner Einträge

| Feld | Inhalt |
|---|---|
| **Test-ID** | MEM-09 |
| **Ziel** | Ein einzelner Fakt lässt sich über REST **und** MCP löschen. |
| **Vorbedingung** | `entry_id` eines Test-Faktums (z. B. aus MEM-01) bekannt. |
| **Schritte (UI)** | 1. Memory-Eintrag öffnen.<br>2. Löschen (mit Bestätigung, falls vorhanden). |
| **Schritte (REST/MCP)** | REST: `DELETE /api/v1/memory/entries/<entry_id>/`<br>MCP: `memory.forget` mit `entry_id` und `change_reason` (Payload unten). |
| **Erwartetes Ergebnis** | Nach REST-DELETE liefert `GET /api/v1/memory/entries/<entry_id>/` den Eintrag nicht mehr (404/leer); nach `memory.forget` ist der Fakt ebenfalls nicht mehr in Suche und Liste. `memory.get` mit der alten `entry_id` liefert „nicht gefunden". |
| **Negativfall** | `DELETE`/`memory.forget` mit **fremder** bzw. nicht existierender `entry_id` wird abgelehnt (kein stiller Erfolg, kein Löschen fremder Daten). |
| **Evidence** | `evidence/MEM-09_1.json` (DELETE-Response), `evidence/MEM-09_2.json` (MCP-Response), `evidence/MEM-09_3.json` (Nachweis Nicht-Vorhandensein) |
| **Pass/Fail** | [ ] Pass [ ] Fail |

```json
{
  "jsonrpc": "2.0",
  "id": 4,
  "method": "tools/call",
  "params": {
    "name": "memory.forget",
    "arguments": { "entry_id": 987, "change_reason": "Testplan MEM-09" }
  }
}
```

#### MEM-10 — Promotion `user` → `workspace`

| Feld | Inhalt |
|---|---|
| **Test-ID** | MEM-10 |
| **Ziel** | Ein Fakt im Scope `user` wird per Promotion zu Scope `workspace`. |
| **Vorbedingung** | Fakt im Scope `user` vorhanden (per UI oder `memory.write` mit `scope: "user"` angelegt). |
| **Schritte (UI)** | 1. Memory-Eintrag mit Scope `user` öffnen.<br>2. Aktion „Promote"/„Befördern" ausführen. |
| **Schritte (REST/MCP)** | `POST /api/v1/memory/entries/<entry_id>/promote/` (Payload unten); danach erneut lesen. |
| **Erwartetes Ergebnis** | Der Eintrag hat danach Scope `workspace` und ist für alle Mitglieder des Workspace sichtbar (Gegenprobe mit User B, vgl. MEM-14). |
| **Negativfall** | Promotion eines bereits im Scope `workspace` liegenden Eintrags ändert nichts fehlerhaft (idempotent oder saubere Fehlermeldung) und erzeugt **keinen** Duplikat-Eintrag. |
| **Evidence** | `evidence/MEM-10_1.json` (vorher/nachher GET) |
| **Pass/Fail** | [ ] Pass [ ] Fail |

```json
{ "change_reason": "Testplan MEM-10" }
```

#### MEM-11 — Purge & System-Sicht (Scope-/Workspace-Ebene)

| Feld | Inhalt |
|---|---|
| **Test-ID** | MEM-11 |
| **Ziel** | Workspace-weites Purge sowie die System-Sicht auf Memory funktionieren. |
| **Vorbedingung** | Wegwerf-Workspace `TP-b14 Workspace B` mit mindestens zwei Fakten. |
| **Schritte (UI)** | 1. System-Admin-Bereich → Memory-Sicht öffnen.<br>2. Workspace `TP-b14 Workspace B` auswählen.<br>3. Purge ausführen. |
| **Schritte (REST/MCP)** | Übersicht: `GET /api/v1/system/memory/workspaces/` und `GET /api/v1/system/memory/entries/`<br>Projektion: `GET /api/v1/system/memory/projection/`<br>Export: `GET /api/v1/system/memory/entries/export/?format=json` und `?format=csv`<br>Purge: `DELETE /api/v1/system/memory/workspaces/<workspace_id>/` (Payload unten) |
| **Erwartetes Ergebnis** | Vor dem Purge sind Workspace und Einträge in den System-Sichten gelistet; der Export liefert für `json` und `csv` parsebare Dateien. Nach dem Purge ist der Workspace nicht mehr in `GET /api/v1/system/memory/workspaces/` und seine Einträge nicht mehr in `GET /api/v1/system/memory/entries/`. |
| **Negativfall** | Purge darf **nur** den Ziel-Workspace treffen: `TP-b14 Workspace` bleibt nach dem Purge von `TP-b14 Workspace B` unverändert (Gegenprobe über `GET /api/v1/workspaces/<workspace_id>/memory/entries/`). |
| **Evidence** | `evidence/MEM-11_1.json` (vorher), `evidence/MEM-11_2.json` (nachher), `evidence/MEM-11_3.csv` (Export) |
| **Pass/Fail** | [ ] Pass [ ] Fail |

> **Scope-Level-Purge (Löschen eines einzelnen Scopes):** kein verifizierter Endpoint im Scope —
> **nicht im Scope / nicht verifiziert**. Nicht als Testfall anlegen.

#### MEM-12 — Honcho: Löschung nachweislich im externen Store

| Feld | Inhalt |
|---|---|
| **Test-ID** | MEM-12 |
| **Ziel** | Unter `MEMORY_BACKEND=honcho` entfernt ein Forget/Purge die Daten **nachweislich** auch im externen Dienst. |
| **Vorbedingung** | Stack mit `--profile honcho` gestartet; `MEMORY_BACKEND=honcho`; `HONCHO_BASE_URL`/`HONCHO_API_KEY` gesetzt; Schreib-/Lesezugriff auf die Honcho-Instanz für die Nachprüfung. |
| **Schritte (UI)** | 1. Fakt anlegen.<br>2. Suche/Digest ausführen und Fakt nachweisen.<br>3. Fakt über UI löschen.<br>4. Suche/Digest erneut ausführen. |
| **Schritte (REST/MCP)** | Anlegen: `POST /api/v1/workspaces/<workspace_id>/memory/entries/`<br>Nachweis vorher: `GET /api/v1/workspaces/<workspace_id>/memory/search/`, `GET .../memory/digest/`<br>Löschen: `DELETE /api/v1/memory/entries/<entry_id>/` bzw. MCP `memory.forget`<br>Nachweis nachher: dieselben GET-Aufrufe erneut, **plus** Prüfung im externen Honcho-Store. |
| **Erwartetes Ergebnis** | Nach dem Löschen liefern Suche **und** Digest den entfernten Fakt **nicht** mehr, **und** der externe Honcho-Store enthält die Daten nicht mehr. **Harte Abnahmebedingung:** „nicht mehr in der Suche" allein genügt nicht. |
| **Negativfall** | Wird das Backend auf `honcho` gestellt, aber die Honcho-Instanz ist nicht erreichbar, muss das Ergebnis als **`degraded`** ausgewiesen werden (MEM-13) — **nicht** als „erfolgreich gelöscht" und **nicht** als stille Leerliste. |
| **Evidence** | `evidence/MEM-12_1.json` (vorher), `evidence/MEM-12_2.json` (Suche/Digest nachher), `evidence/MEM-12_3.png`/`.txt` (externer Store nachher) |
| **Pass/Fail** | [ ] Pass [ ] Fail |

> **Live-only:** Der Nachweis im externen Honcho-Store erfordert eine reale Honcho-Instanz
> (siehe §6, L3/L4).

#### MEM-13 — `degraded`-Signal statt stiller Leerliste

| Feld | Inhalt |
|---|---|
| **Test-ID** | MEM-13 |
| **Ziel** | Fällt das Memory-Backend aus, signalisiert die API sichtbar `degraded` — sie liefert **keine** stille Leerliste. |
| **Vorbedingung** | `MEMORY_BACKEND=honcho` und Honcho-Dienst gestoppt (oder äquivalent: Backend gezielt unerreichbar machen). |
| **Schritte (UI)** | 1. Memory-Seite öffnen.<br>2. Banner-Zustand beobachten.<br>3. Artefakt-Panel eines Requirements öffnen und Banner-Zustand beobachten. |
| **Schritte (REST/MCP)** | `GET /api/v1/workspaces/<workspace_id>/memory/entries/`<br>`GET /api/v1/workspaces/<workspace_id>/memory/search/`<br>`GET /api/v1/workspaces/<workspace_id>/memory/digest/`<br>`GET /api/v1/admin/health/` (Komponente `memory_backend`) |
| **Erwartetes Ergebnis** | Jeder Memory-Response-Umschlag enthält die Keys **`backend`, `ok`, `detail`, `degraded`, `digest_available`**, wobei **`degraded = not ok or degraded`** gilt. Bei gestopptem Backend ist `degraded` wahr bzw. `ok` falsch und `detail` erklärt die Ursache. `GET /api/v1/admin/health/` weist die Komponente **`memory_backend`** als beeinträchtigt aus. In der Memory-Seite **und** im Artefakt-Panel erscheint ein UI-Banner. |
| **Negativfall** | **Hauptfehlerbild:** Das Backend fällt aus, aber die API liefert eine leere Liste/leeren Digest **ohne** `degraded`-Signal — das ist als Defekt zu melden (stille Leerheit). |
| **Evidence** | `evidence/MEM-13_1.json` (Memory-GET), `evidence/MEM-13_2.json` (admin/health), `evidence/MEM-13_3.png` (UI-Banner) |
| **Pass/Fail** | [ ] Pass [ ] Fail |

#### MEM-14 — Cross-User-Sichtbarkeit (`workspace` vs. `user`)

| Feld | Inhalt |
|---|---|
| **Test-ID** | MEM-14 |
| **Ziel** | `workspace`-Fakten sind für alle Mitglieder sichtbar, `user`-Fakten nur für den Besitzer. |
| **Vorbedingung** | User A und User B (§3.8), beide Mitglied von `TP-b14 Workspace`. |
| **Schritte (UI)** | 1. Als **User A** anmelden, Fakt mit Scope `workspace` anlegen (z. B. `Teamweite Entscheidung: Reviewer-Rotation.`).<br>2. Als **User A** einen zweiten Fakt mit Scope `user` anlegen (z. B. `Nur meine Notiz.`).<br>3. Abmelden, als **User B** anmelden, Memory-Seite öffnen. |
| **Schritte (REST/MCP)** | Als User A: `POST /api/v1/workspaces/<workspace_id>/memory/entries/` (Scope `workspace`) und MCP `memory.write` mit `scope: "user"`.<br>Als User B: `GET /api/v1/workspaces/<workspace_id>/memory/entries/` und `GET /api/v1/memory/me/`. |
| **Erwartetes Ergebnis** | User B sieht den `workspace`-Fakt von A. Der `user`-Fakt von A ist für B **nicht** sichtbar (weder in der Workspace-Liste noch in einer Suche). |
| **Negativfall** | Der `user`-Scope-Fakt von A darf auch über direkten REST-Zugriff (`GET /api/v1/memory/entries/<entry_id>/`) für B **nicht** lesbar sein (kein 200 mit Inhalt). |
| **Evidence** | `evidence/MEM-14_1.png` (Sicht B), `evidence/MEM-14_2.json` (Direktzugriff B) |
| **Pass/Fail** | [ ] Pass [ ] Fail |

#### MEM-15 — Memory-Settings (Workspace & System)

| Feld | Inhalt |
|---|---|
| **Test-ID** | MEM-15 |
| **Ziel** | Workspace- und System-Memory-Einstellungen sind les- und schreibbar; Reset funktioniert. |
| **Vorbedingung** | System-Admin-Rechte für den System-Teil. |
| **Schritte (UI)** | 1. Workspace-Einstellungen → Memory-Bereich öffnen.<br>2. Wert ändern und speichern.<br>3. System-Admin → Memory-Einstellungen öffnen.<br>4. Reset ausführen. |
| **Schritte (REST/MCP)** | `GET`/`PUT /api/v1/workspaces/<workspace_id>/memory-settings/`<br>`GET`/`PUT /api/v1/system/memory-settings/`<br>`POST /api/v1/system/memory-settings/reset/` |
| **Erwartetes Ergebnis** | Ein `PUT` ist nach erneutem `GET` sichtbar wirksam. `POST .../reset/` stellt die System-Defaults wieder her (nachfolgendes `GET` zeigt die Default-Werte). |
| **Negativfall** | Ein `PUT` mit ungültigem Wert wird mit Validierungsfehler abgelehnt und verändert die bestehende Einstellung **nicht**. |
| **Evidence** | `evidence/MEM-15_1.json` (PUT+GET), `evidence/MEM-15_2.json` (nach Reset) |
| **Pass/Fail** | [ ] Pass [ ] Fail |

#### MEM-16 — Schreib-Rate-Limit (`MEMORY_WRITE_RATE_LIMIT_PER_HOUR`)

| Feld | Inhalt |
|---|---|
| **Test-ID** | MEM-16 |
| **Ziel** | Das Schreiblimit greift wie konfiguriert und ist von einem Defekt unterscheidbar. |
| **Vorbedingung** | `MEMORY_WRITE_RATE_LIMIT_PER_HOUR=2` (Testwert) und Stack neu gestartet; alternativ via `PUT /api/v1/system/memory-settings/` gesetzt. |
| **Schritte (UI)** | 1. Zwei Fakten anlegen (erwartet: OK).<br>2. Dritten Fakt anlegen (erwartet: Limit).<br>3. Limit auf `0` setzen, Stack/Setting aktualisieren, erneut schreiben. |
| **Schritte (REST/MCP)** | `POST /api/v1/workspaces/<workspace_id>/memory/entries/` dreimal hintereinander (Payload unten). |
| **Erwartetes Ergebnis** | Die ersten 2 Writes gelingen; der 3. wird mit einem **Rate-Limit-Fehler** (HTTP 429 o. ä. mit erklärender Meldung) abgewiesen. Mit `0` (= unbegrenzt) gelingen weitere Writes. |
| **Negativfall** | Ein 429 darf **nicht** als generischer Serverfehler erscheinen, und der abgewiesene Write darf **keinen** Eintrag erzeugt haben (Nachprüfung per GET). |
| **Evidence** | `evidence/MEM-16_1.json` (3. Write, abgewiesen), `evidence/MEM-16_2.json` (kein Eintrag), `evidence/MEM-16_3.json` (mit `0`) |
| **Pass/Fail** | [ ] Pass [ ] Fail |

```json
{ "content": "Rate-Limit-Test.", "confidence": 1.0, "change_reason": "Testplan MEM-16" }
```

### 4.2 uid (#932)

`generate_local_uid` erzeugt pro `(workspace, item_type)` eine atomare Sequenz im Format
`{PREFIX}-{NNN}`. Präfix-Zuordnung:

| Artefakttyp | Präfix |
|---|---|
| StakeholderNeed | `NEED` |
| Requirement | `REQ` |
| ArchitectureElement | `ARCH` |
| TestCase | `TC` |
| TestRun | `RUN` |
| Adr | `ADR` |
| Risk | `RISK` |
| Issue | `ISSUE` |

Client-seitig mitgeschickte `uid` wird abgelehnt (HTTP 400, Meldung
`uid is system-generated and read-only; omit it.`) — enforced durch `ClientUidRejectionMixin`.

#### UID-01 — Auto-Vergabe mit korrektem Präfix

| Feld | Inhalt |
|---|---|
| **Test-ID** | UID-01 |
| **Ziel** | Jeder Artefakttyp erhält automatisch eine `uid` mit typgerechtem Präfix. |
| **Vorbedingung** | Workspace `TP-b14 Workspace` (§3.2). |
| **Schritte (UI)** | 1. Je ein Artefakt anlegen: StakeholderNeed, Requirement, ArchitectureElement, TestCase, TestRun, ADR, Risk, Issue.<br>2. Jeweils die angezeigte `uid` ablesen und notieren. |
| **Schritte (REST/MCP)** | Kein zusätzlicher verifizierter Endpoint nötig; Kontrolle über die UI sowie über die verifizierte Requirements-Route, sofern ein Requirement erneut gelesen wird. |
| **Erwartetes Ergebnis** | Acht Artefakte erhalten `uid` mit exakt den Präfixen `NEED-001`, `REQ-001`, `ARCH-001`, `TC-001`, `RUN-001`, `ADR-001`, `RISK-001`, `ISSUE-001`. Keine `uid` ist leer. |
| **Negativfall** | Zwei Artefakte desselben Typs erhalten **nicht** dieselbe `uid`. |
| **Evidence** | `evidence/UID-01_1.png` (Liste mit sichtbaren `uid`s) |
| **Pass/Fail** | [ ] Pass [ ] Fail |

#### UID-02 — Eindeutigkeit & getrennte Zähler pro Workspace

| Feld | Inhalt |
|---|---|
| **Test-ID** | UID-02 |
| **Ziel** | Die Sequenz ist pro Workspace eigenständig und monoton. |
| **Vorbedingung** | `TP-b14 Workspace` und `TP-b14 Workspace B` (§3.7). |
| **Schritte (UI)** | 1. Im ersten Workspace zwei Requirements anlegen.<br>2. Im zweiten Workspace ein Requirement anlegen.<br>3. Die drei `uid`s vergleichen. |
| **Schritte (REST/MCP)** | Kontroll-Lesen der Requirements in beiden Workspaces (Requirements-Route ist verifiziert: `GET /api/v1/requirements/`). |
| **Erwartetes Ergebnis** | Erstes Workspace: `REQ-001`, `REQ-002`. Zweites Workspace: `REQ-001` (eigener Zählerstand, startet bei `001`). Innerhalb eines Workspace ist jede `uid` eindeutig. |
| **Negativfall** | Das zweite Workspace darf **nicht** mit `REQ-003` fortfahren (Zähler darf nicht global sein). |
| **Evidence** | `evidence/UID-02_1.png` (beide Workspaces), `evidence/UID-02_2.json` |
| **Pass/Fail** | [ ] Pass [ ] Fail |

#### UID-03 — Client-`uid` wird abgelehnt (HTTP 400)

| Feld | Inhalt |
|---|---|
| **Test-ID** | UID-03 |
| **Ziel** | Eine vom Client gesetzte `uid` wird nicht übernommen. |
| **Vorbedingung** | `POST /api/v1/requirements/` ist der verifizierte Schreibpfad für Requirements. |
| **Schritte (UI)** | 1. Ein Formular mit `uid`-Feld suchen (falls vorhanden): Feld muss **read-only** sein oder gar nicht beschickt werden können. |
| **Schritte (REST/MCP)** | `POST /api/v1/requirements/` mit explizitem `uid` (Payload unten) sowie `PATCH /api/v1/requirements/<id>/` mit `uid`. |
| **Erwartetes Ergebnis** | Beide Aufrufe werden mit **HTTP 400** und der Meldung `uid is system-generated and read-only; omit it.` abgelehnt. Das Artefakt wird **nicht** angelegt bzw. **nicht** verändert. |
| **Negativfall** | Das Anlegen **ohne** `uid` gelingt weiterhin (HTTP 201) — die Sperre darf nicht das normale Arbeiten blockieren. |
| **Evidence** | `evidence/UID-03_1.json` (400-Antwort), `evidence/UID-03_2.json` (201 ohne uid) |
| **Pass/Fail** | [ ] Pass [ ] Fail |

```json
{
  "uid": "REQ-999",
  "title": "Darf nicht angelegt werden",
  "change_reason": "Testplan UID-03"
}
```

#### UID-04 — UI-Anzeige der `uid`

| Feld | Inhalt |
|---|---|
| **Test-ID** | UID-04 |
| **Ziel** | Die `uid` wird in der UI angezeigt und ist vom Legacy-Fallback unterscheidbar. |
| **Vorbedingung** | Artefakte aus UID-01. |
| **Schritte (UI)** | 1. Requirement `REQ-TP-001` öffnen.<br>2. `uid` in Liste und Detailansicht prüfen.<br>3. Für ein **Alt-Artefakt ohne** `uid` (falls vorhanden) die Anzeige prüfen. |
| **Schritte (REST/MCP)** | Kein zusätzlicher verifizierter Endpoint im Scope. |
| **Erwartetes Ergebnis** | Die Liste zeigt das `uid`-Schema (`REQ-001` …). Für Artefakte ohne `uid` zeigt die UI den dokumentierten **Legacy-Fallback** (kurzer UUID-Hash) — nicht ein leeres Feld. |
| **Negativfall** | Kein Artefakt wird mit einer **erfundenen** `uid` dargestellt, wenn keine vergeben wurde. |
| **Evidence** | `evidence/UID-04_1.png` |
| **Pass/Fail** | [ ] Pass [ ] Fail |

#### UID-05 — AWMS-Backfill für Bestands-Workspaces

| Feld | Inhalt |
|---|---|
| **Test-ID** | UID-05 |
| **Ziel** | Nachvollziehen, wie ein **vor** dem Feature angelegtes Workspace nachträglich `uid`s erhält. |
| **Vorbedingung** | Zugriff auf die Backfill-Dokumentation/Plan im Repo; für die Ausführung ein Workspace mit Artefakten **ohne** `uid`. |
| **Schritte (UI)** | Kein UI-Schritt; dies ist ein Betriebs-/Backfill-Verfahren. |
| **Schritte (REST/MCP)** | Kein REST/MCP-Endpoint im Scope. Beschreibung: Der Backfill ordnet die Sequenz über die Strategie **`value_strategy: sequence`** zu. |
| **Erwartetes Ergebnis** | Der Plan ist dokumentiert und beschreibt: pro `(workspace, item_type)` wird eine Sequenz vergeben, beginnend bei `001`, analog zur Neuanlage. Bestehende IDs/Referenzen bleiben unverändert; nur `uid` wird ergänzt. |
| **Negativfall** | Ein Backfill darf **keine** doppelten `uid`s innerhalb eines `(workspace, item_type)` erzeugen und keine bestehende Fremdschlüssel-Referenz verändern. |
| **Evidence** | `evidence/UID-05_1.txt` (Plan-Auszug/Nachweis) |
| **Pass/Fail** | [ ] Pass [ ] Fail |

> Hinweis: Der konkrete Ausführungsbefehl des Backfills ist **nicht im Scope / nicht verifiziert**.

### 4.3 INCOSE/IEEE-Attribute (#871/#583)

**Verifizierte Felder** auf Requirement:

| Feld | Typ | Constraints |
|---|---|---|
| `rationale` | TextField | darf leer sein, Maximum **20000** |
| `source` | CharField | Maximum **255** |

#### ATTR-01 — Anlegen & Lesen über die UI

| Feld | Inhalt |
|---|---|
| **Test-ID** | ATTR-01 |
| **Ziel** | `rationale` und `source` lassen sich in der UI erfassen und werden angezeigt. |
| **Vorbedingung** | Workspace `TP-b14 Workspace` geöffnet. |
| **Schritte (UI)** | 1. Neues Requirement anlegen.<br>2. `source` = `Stakeholder-Workshop 2026-09-10`.<br>3. `rationale` = `Sichert die Nachvollziehbarkeit der Anforderung.`<br>4. Speichern und Requirement erneut öffnen. |
| **Schritte (REST/MCP)** | Kontroll-Lesen über die Requirements-Route (`GET /api/v1/requirements/`). |
| **Erwartetes Ergebnis** | Beide Werte werden nach dem Speichern unverändert wieder angezeigt (keine Kürzung, keine Umlaut-/Encoding-Fehler). |
| **Negativfall** | Ein `source` mit Sonderzeichen/Umlauten wird korrekt gespeichert und angezeigt (kein Mojibake). |
| **Evidence** | `evidence/ATTR-01_1.png` |
| **Pass/Fail** | [ ] Pass [ ] Fail |

#### ATTR-02 — REST-Round-Trip (`POST`/`PATCH /api/v1/requirements/`)

| Feld | Inhalt |
|---|---|
| **Test-ID** | ATTR-02 |
| **Ziel** | Beide Felder überstehen den Round-Trip über die REST-Schnittstelle. |
| **Vorbedingung** | Bekannter Endpoint: `POST /api/v1/requirements/`, `PATCH /api/v1/requirements/<id>/`. |
| **Schritte (UI)** | Keine — reiner API-Test; Ergebnis danach in der UI gegenprüfen. |
| **Schritte (REST/MCP)** | 1. `POST /api/v1/requirements/` mit `source` und `rationale` (Payload unten).<br>2. Antwort auswerten.<br>3. `PATCH` mit geändertem `rationale`.<br>4. Requirement per `GET` lesen. |
| **Erwartetes Ergebnis** | `POST` gibt beide Felder im Response-Body zurück; `PATCH` aktualisiert genau das geänderte Feld; der anschließende `GET` bestätigt den neuen Wert. |
| **Negativfall** | `rationale` mit 20000+ Zeichen wird abgelehnt (Validierungsfehler), nicht still abgeschnitten. |
| **Evidence** | `evidence/ATTR-02_1.json` (POST), `evidence/ATTR-02_2.json` (PATCH+GET) |
| **Pass/Fail** | [ ] Pass [ ] Fail |

```json
{
  "title": "ATTR-TP-001 Round-Trip",
  "source": "Stakeholder-Workshop 2026-09-10",
  "rationale": "Sichert die Nachvollziehbarkeit der Anforderung.",
  "change_reason": "Testplan ATTR-02"
}
```

#### ATTR-03 — MCP-Round-Trip

| Feld | Inhalt |
|---|---|
| **Test-ID** | ATTR-03 |
| **Ziel** | Beide Felder sind über den MCP-Kanal schreib- und lesbar. |
| **Vorbedingung** | API-Key (`reqlo_*`) vorhanden. |
| **Schritte (UI)** | Ergebnis anschließend in der UI gegenprüfen. |
| **Schritte (REST/MCP)** | 1. `tools/list` aufrufen und das für Requirements zuständige Schreib-/Lesetool ermitteln.<br>2. Tool mit `source`/`rationale` aufrufen.<br>3. Werte über den MCP-Kanal zurücklesen. |
| **Erwartetes Ergebnis** | Beide Felder werden identisch zu REST/UI zurückgegeben (keine Feld-Verluste im MCP-Pfad). |
| **Negativfall** | Der MCP-Schreibpfad ohne `source`/`rationale` legt das Requirement **ohne Fehler** an (beide Felder sind optional). |
| **Evidence** | `evidence/ATTR-03_1.json` (MCP-Response) |
| **Pass/Fail** | [ ] Pass [ ] Fail |

> **Name des MCP-Requirements-Tools:** im Scope dieses Testplans **nicht verifiziert** — über
> `tools/list` bzw. `tools/filter` der Zielinstanz bestimmen und hier eintragen: `__________`.

#### ATTR-04 — Negativfälle (Grenzwerte & Optionalität)

| Feld | Inhalt |
|---|---|
| **Test-ID** | ATTR-04 |
| **Ziel** | Grenzwerte greifen; beide Felder sind optional. |
| **Vorbedingung** | `PATCH /api/v1/requirements/<id>/` verfügbar. |
| **Schritte (UI)** | 1. `source` mit 256+ Zeichen speichern (erwartet: Fehler).<br>2. `rationale` mit 20001 Zeichen speichern (erwartet: Fehler).<br>3. Beide Felder weglassen und speichern (erwartet: OK). |
| **Schritte (REST/MCP)** | `PATCH /api/v1/requirements/<id>/` mit den drei Varianten. |
| **Erwartetes Ergebnis** | `source` > 255 → Validierungsfehler (HTTP 400). `rationale` > 20000 → Validierungsfehler. Weglassen beider Felder → kein Fehler. |
| **Negativfall** | Ein Fehler darf **kein** Teil-Update hinterlassen (Feld bleibt auf dem alten Wert, nicht abgeschnitten auf 255). |
| **Evidence** | `evidence/ATTR-04_1.json`, `evidence/ATTR-04_2.json`, `evidence/ATTR-04_3.json` |
| **Pass/Fail** | [ ] Pass [ ] Fail |

### 4.4 Trace-Katalog (#950)

**Verifizierte Built-in-Link-Typen (11 insgesamt):** `derives-from`, `decomposes`, `refines`,
`satisfies`, `realizes`, `allocated-to`, `verifies`, `decides`, `mitigates`, `references`,
`diagram-ref`.

**Coverage-relevant sind ausschließlich:** `satisfies`, `allocated-to`, `verifies`.

| Link-Typ | Semantik (für diesen Test relevant) |
|---|---|
| `satisfies` | Requirement → Goal (**Coverage**) |
| `realizes` | Requirement → Goal (Realisierung) |
| `refines` | Requirement → Requirement |

#### TRC-01 — `satisfies` verändert die Coverage

| Feld | Inhalt |
|---|---|
| **Test-ID** | TRC-01 |
| **Ziel** | Eine `satisfies`-Verknüpfung Requirement → StakeholderNeed/Goal erhöht die Coverage-Kennzahl. |
| **Vorbedingung** | `REQ-TP-001` und `SN-TP-001` existieren; Coverage-Wert von `SN-TP-001` vor dem Link notiert. |
| **Schritte (UI)** | 1. Traceability-Ansicht von `SN-TP-001` öffnen, Coverage-Wert notieren.<br>2. Link mit Typ `satisfies` von `REQ-TP-001` auf `SN-TP-001` anlegen.<br>3. Ansicht neu laden, Coverage-Wert erneut ablesen. |
| **Schritte (REST/MCP)** | Kein zusätzlicher verifizierter Endpoint nötig; Kontrolle über die Traceability-Ansicht. |
| **Erwartetes Ergebnis** | Die Coverage-Kennzahl für `SN-TP-001` ändert sich entsprechend (vorher/nachher unterscheidbar). Der Link erscheint in der Traceability-Ansicht. |
| **Negativfall** | Wird der Link wieder entfernt, fällt die Kennzahl auf den Ausgangswert zurück (keine dauerhafte Erhöhung). |
| **Evidence** | `evidence/TRC-01_1.png` (vorher), `evidence/TRC-01_2.png` (nachher) |
| **Pass/Fail** | [ ] Pass [ ] Fail |

#### TRC-02 — `realizes` und `refines` in View & Impact-Analyse

| Feld | Inhalt |
|---|---|
| **Test-ID** | TRC-02 |
| **Ziel** | `realizes` (Requirement → Goal) und `refines` (Requirement → Requirement) sind sichtbar und Teil der Impact-Analyse. |
| **Vorbedingung** | `REQ-TP-001`, `SN-TP-001` sowie ein zweites Requirement (z. B. `REQ-TP-002`) existieren. |
| **Schritte (UI)** | 1. Link `realizes` von `REQ-TP-001` auf `SN-TP-001` anlegen.<br>2. Link `refines` von `REQ-TP-002` auf `REQ-TP-001` anlegen.<br>3. Traceability-Ansicht prüfen.<br>4. Impact-Analyse für `REQ-TP-001` öffnen. |
| **Schritte (REST/MCP)** | Kein zusätzlicher verifizierter Endpoint nötig; Kontrolle über UI. |
| **Erwartetes Ergebnis** | Beide Links erscheinen in der Traceability-Ansicht mit korrektem Typ. In der Impact-Analyse von `REQ-TP-001` erscheint `REQ-TP-002` als abhängiges Artefakt (gerichtet über `refines`). |
| **Negativfall** | Eine Impact-Analyse darf `refines` **nicht** als Coverage-Beitrag zählen (nur `satisfies`/`allocated-to`/`verifies` sind coverage-relevant). |
| **Evidence** | `evidence/TRC-02_1.png` (Traceability-View), `evidence/TRC-02_2.png` (Impact-Analyse) |
| **Pass/Fail** | [ ] Pass [ ] Fail |

#### TRC-03 — Nicht-Coverage-Link verändert die Coverage nicht

| Feld | Inhalt |
|---|---|
| **Test-ID** | TRC-03 |
| **Ziel** | Ein `references`-Link beeinflusst die Coverage-Kennzahl nicht. |
| **Vorbedingung** | Coverage-Wert von `SN-TP-001` notiert. |
| **Schritte (UI)** | 1. Link mit Typ `references` von `REQ-TP-002` auf `SN-TP-001` anlegen.<br>2. Coverage-Wert erneut ablesen. |
| **Schritte (REST/MCP)** | Kein zusätzlicher verifizierter Endpoint nötig; Kontrolle über UI. |
| **Erwartetes Ergebnis** | Die Coverage-Kennzahl bleibt **unverändert**. Der Link ist in der Traceability-Ansicht dennoch sichtbar (Referenz, keine Coverage). |
| **Negativfall** | Die Kennzahl darf sich **nicht** erhöhen — eine Erhöhung ist ein Defekt (Coverage-Verfälschung). |
| **Evidence** | `evidence/TRC-03_1.png` (vorher/nachher) |
| **Pass/Fail** | [ ] Pass [ ] Fail |

#### TRC-04 — Katalog-Vollständigkeit (11 Typen)

| Feld | Inhalt |
|---|---|
| **Test-ID** | TRC-04 |
| **Ziel** | Der Link-Typ-Katalog ist vollständig und nutzbar. |
| **Vorbedingung** | Workspace geöffnet. |
| **Schritte (UI)** | 1. Link-Anlage öffnen (Typ-Auswahl).<br>2. Alle angebotenen Typen auflisten. |
| **Schritte (REST/MCP)** | Kein zusätzlicher verifizierter Endpoint nötig. |
| **Erwartetes Ergebnis** | Alle 11 Built-ins sind vorhanden: `derives-from`, `decomposes`, `refines`, `satisfies`, `realizes`, `allocated-to`, `verifies`, `decides`, `mitigates`, `references`, `diagram-ref`. |
| **Negativfall** | Ein unbekannter Typ (z. B. `bogus-link`) kann **nicht** ausgewählt/gespeichert werden (Validierungsfehler). |
| **Evidence** | `evidence/TRC-04_1.png` (Typ-Auswahl vollständig) |
| **Pass/Fail** | [ ] Pass [ ] Fail |

### 4.5 Link-Defaults aus env (#989)

**Verifizierte Variablen:** `DEFAULT_TRACE_LINK_TYPE` / `DEFAULT_DECOMPOSITION_LINK_TYPE`.
Sie werden in `backend/reqogniloom/settings.py` gelesen und in `backend/link_types/defaults.py`
aufgelöst.

| Variable | Default | Erlaubte Werte |
|---|---|---|
| `DEFAULT_TRACE_LINK_TYPE` | `references` | die 11 Built-in-Keys aus §4.4 |
| `DEFAULT_DECOMPOSITION_LINK_TYPE` | `decomposes` | die 11 Built-in-Keys aus §4.4 |

Ein **unbekannter Wert wird ignoriert** (dokumentierter Fallback, kein Crash).

#### LNK-01 — Neue Workspaces übernehmen die env-Defaults

| Feld | Inhalt |
|---|---|
| **Test-ID** | LNK-01 |
| **Ziel** | Neue Workspaces starten mit den per env gesetzten Link-Defaults. |
| **Vorbedingung** | In `.env` gesetzt: `DEFAULT_TRACE_LINK_TYPE=satisfies` und `DEFAULT_DECOMPOSITION_LINK_TYPE=refines`; Stack neu gestartet (env-Änderungen erfordern Recreate, kein reiner `restart`). |
| **Schritte (UI)** | 1. **Neu** anlegen: `TP-b14 Workspace LNK`.<br>2. Link-Anlage öffnen und die vorausgewählte Spur-Spalte/den Standardtyp ablesen.<br>3. Dekompositions-Aktion öffnen und den Standardtyp ablesen.<br>4. Gegenprobe in `TP-b14 Workspace` (vor dem env-Wechsel angelegt). |
| **Schritte (REST/MCP)** | Kein zusätzlicher verifizierter Endpoint nötig; Kontrolle über UI. |
| **Erwartetes Ergebnis** | Im **neuen** Workspace ist `satisfies` als Spur-Standard und `refines` als Dekompositions-Standard vorausgewählt. Das alte Workspace behält seine eigenen gespeicherten Werte (per-Workspace überschreibbar). |
| **Negativfall** | Ein bereits bestehendes Workspace darf durch den env-Wechsel **nicht** rückwirkend umgestellt werden. |
| **Evidence** | `evidence/LNK-01_1.png` (neues Workspace), `evidence/LNK-01_2.png` (Bestands-Workspace) |
| **Pass/Fail** | [ ] Pass [ ] Fail |

#### LNK-02 — Fallback bei leerer Spalte

| Feld | Inhalt |
|---|---|
| **Test-ID** | LNK-02 |
| **Ziel** | Ist der Workspace-Wert leer, greift der dokumentierte Fallback. |
| **Vorbedingung** | Workspace mit geleertem/fehlendem Standard-Linktyp (Workspace-Einstellungen → Traceability). |
| **Schritte (UI)** | 1. Workspace-Einstellungen → Traceability öffnen.<br>2. Standard-Linktyp leeren/entfernen und speichern.<br>3. Link-Anlage öffnen und Vorauswahl prüfen. |
| **Schritte (REST/MCP)** | Kein zusätzlicher verifizierter Endpoint nötig; Kontrolle über UI. |
| **Erwartetes Ergebnis** | Bei leerer Spalte wird der dokumentierte Fallback verwendet (`references` bzw. `decomposes`) — es entsteht **kein** Fehler und **kein** leeres Pflichtfeld. |
| **Negativfall** | Eine leere Spalte darf nicht dazu führen, dass die Link-Anlage komplett blockiert ist. |
| **Evidence** | `evidence/LNK-02_1.png` |
| **Pass/Fail** | [ ] Pass [ ] Fail |

#### LNK-03 — Negativfall: unbekannter env-Wert (`bogus-link`)

| Feld | Inhalt |
|---|---|
| **Test-ID** | LNK-03 |
| **Ziel** | Ein ungültiger env-Wert führt zum dokumentierten Fallback und **nicht** zum Absturz. |
| **Vorbedingung** | In `.env` gesetzt: `DEFAULT_TRACE_LINK_TYPE=bogus-link`; Stack neu gestartet. |
| **Schritte (UI)** | 1. Ein **neues** Workspace anlegen.<br>2. Link-Anlage öffnen.<br>3. Backend-Logs auf Fehler prüfen. |
| **Schritte (REST/MCP)** | Kontrollaufruf `curl localhost:8001/health/` (Stack lebt). |
| **Erwartetes Ergebnis** | Der unbekannte Wert wird **ignoriert**; es greift der dokumentierte Fallback. Der Stack startet normal, `/health/` antwortet mit `200`, das Workspace ist anlegbar. |
| **Negativfall** | Kein `500`, kein Startabbruch, keine leere/kaputte Link-Auswahl. |
| **Evidence** | `evidence/LNK-03_1.txt` (Backend-Log ohne Traceback), `evidence/LNK-03_2.png` (Link-Auswahl) |
| **Pass/Fail** | [ ] Pass [ ] Fail |

### 4.6 Admin-Backup gzip (#823)

**Verifizierte MCP-Tools:**

| Tool | Parameter |
|---|---|
| `admin.backup_create` | optional `reason`, `backup_type` (`full` \| `partial`) |
| `admin.backup_list` | — |
| `admin.restore` | erforderlich `backup_id` **und** `confirmation_text` (Literal `RESTORE`); optional `restore_type` |

**Verifizierte REST-Routen:** `POST`/`GET /api/v1/admin/backups/`, `POST /api/v1/admin/restore/`.

**Verifiziertes Dateinamen-Muster:** `<id>.json.gz`

#### BKP-01 — Backup erstellen und gzip-Komprimierung nachweisen

| Feld | Inhalt |
|---|---|
| **Test-ID** | BKP-01 |
| **Ziel** | Ein Backup wird erzeugt, liegt gzip-komprimiert vor und trägt die Endung `.json.gz`. |
| **Vorbedingung** | System-Admin-Rechte. |
| **Schritte (UI)** | 1. System-Admin → Backup-Bereich öffnen.<br>2. Backup mit `reason` = `Testplan BKP-01` erzeugen.<br>3. Eintrag in der Liste prüfen. |
| **Schritte (REST/MCP)** | REST: `POST /api/v1/admin/backups/` (Payload unten), danach `GET /api/v1/admin/backups/`<br>MCP: `admin.backup_create` mit `reason` und `backup_type` = `full` |
| **Erwartetes Ergebnis** | Es entsteht ein Backup mit einer ID und einem Dateinamen nach dem Muster `<id>.json.gz`. Die Datei ist gzip-komprimiert (erkennbar am gzip-Magic / an `file`-Ausgabe) — kein Klartext-JSON. Das Backup erscheint in `GET /api/v1/admin/backups/` und in `admin.backup_list`. |
| **Negativfall** | Ein Backup ohne `reason` ist zulässig (`reason` optional) und darf **nicht** fehlschlagen. |
| **Evidence** | `evidence/BKP-01_1.json` (POST-Response), `evidence/BKP-01_2.json` (Liste), `evidence/BKP-01_3.txt` (gzip-Nachweis) |
| **Pass/Fail** | [ ] Pass [ ] Fail |

```json
{
  "reason": "Testplan BKP-01",
  "backup_type": "full"
}
```

#### BKP-02 — Backup-Liste

| Feld | Inhalt |
|---|---|
| **Test-ID** | BKP-02 |
| **Ziel** | Erzeugte Backups sind vollständig und korrekt aufgelistet. |
| **Vorbedingung** | BKP-01 erfolgreich. |
| **Schritte (UI)** | 1. Backup-Liste in der UI öffnen. |
| **Schritte (REST/MCP)** | REST: `GET /api/v1/admin/backups/`<br>MCP: `admin.backup_list` |
| **Erwartetes Ergebnis** | Das Backup aus BKP-01 ist in beiden Kanälen mit übereinstimmender ID, Zeitstempel und Dateiname `<id>.json.gz` enthalten. |
| **Negativfall** | Kein Phantom-Eintrag: ein nicht existierendes `backup_id` erscheint nicht in der Liste. |
| **Evidence** | `evidence/BKP-02_1.json`, `evidence/BKP-02_2.png` |
| **Pass/Fail** | [ ] Pass [ ] Fail |

#### BKP-03 — Restore mit korrektem Bestätigungstext

| Feld | Inhalt |
|---|---|
| **Test-ID** | BKP-03 |
| **Ziel** | Ein Backup lässt sich mit dem Literal `RESTORE` zurückspielen. |
| **Vorbedingung** | `backup_id` aus BKP-01. |
| **Schritte (UI)** | 1. Restore im Admin-Bereich auswählen.<br>2. Bestätigungstext `RESTORE` eingeben.<br>3. Ausführen.<br>4. Stichprobe: Testdaten sind unverändert vorhanden. |
| **Schritte (REST/MCP)** | REST: `POST /api/v1/admin/restore/` (Payload unten)<br>MCP: `admin.restore` mit `backup_id`, `confirmation_text` = `RESTORE`, optional `restore_type` |
| **Erwartetes Ergebnis** | Der Restore wird akzeptiert und erfolgreich abgeschlossen. Anschließend sind die Testartefakte (z. B. `REQ-TP-001`) wieder lesbar. |
| **Negativfall** | Siehe BKP-04. |
| **Evidence** | `evidence/BKP-03_1.json` (Restore-Response), `evidence/BKP-03_2.png` (Testdaten nach Restore) |
| **Pass/Fail** | [ ] Pass [ ] Fail |

```json
{
  "backup_id": 17,
  "confirmation_text": "RESTORE",
  "restore_type": "full"
}
```

#### BKP-04 — Negativfall: falscher Bestätigungstext

| Feld | Inhalt |
|---|---|
| **Test-ID** | BKP-04 |
| **Ziel** | Ein Restore mit abweichendem Bestätigungstext wird verweigert. |
| **Vorbedingung** | `backup_id` aus BKP-01. |
| **Schritte (UI)** | 1. Restore öffnen.<br>2. Bestätigungstext `restore` (Kleinschreibung) bzw. `RESTORE-ME` eingeben.<br>3. Ausführen. |
| **Schritte (REST/MCP)** | `POST /api/v1/admin/restore/` mit `confirmation_text` = `restore` (Payload unten). |
| **Erwartetes Ergebnis** | Der Restore wird abgelehnt (HTTP 400 bzw. Fehlerantwort); es werden **keine** Daten verändert. |
| **Negativfall** | Eine Ablehnung darf **keinen** Teil-Restore hinterlassen (Datenbestand identisch zum Zustand vor dem Aufruf). |
| **Evidence** | `evidence/BKP-04_1.json` (Ablehnung), `evidence/BKP-04_2.png` (unveränderter Bestand) |
| **Pass/Fail** | [ ] Pass [ ] Fail |

```json
{ "backup_id": 17, "confirmation_text": "restore" }
```

#### BKP-05 — Alt-Dump ohne Komprimierung restaurieren

| Feld | Inhalt |
|---|---|
| **Test-ID** | BKP-05 |
| **Ziel** | Ein **vor** der gzip-Umstellung erzeugter, unkomprimierter Dump ist weiterhin restaurierbar (Abwärtskompatibilität). |
| **Vorbedingung** | Ein unkomprimierter Alt-Dump (Dateiendung `.json`, ohne `.gz`) liegt im Backup-Verzeichnis und ist in `GET /api/v1/admin/backups/` bzw. `admin.backup_list` gelistet (ggf. manuell abgelegt). |
| **Schritte (UI)** | 1. Restore für den Alt-Dump auswählen.<br>2. `RESTORE` bestätigen. |
| **Schritte (REST/MCP)** | `POST /api/v1/admin/restore/` mit der `backup_id` des Alt-Dumps. |
| **Erwartetes Ergebnis** | Der unkomprimierte Alt-Dump wird erkannt und erfolgreich restauriert (kein Fehler „ungültiges gzip"). |
| **Negativfall** | Eine **korrupte** Datei im Backup-Verzeichnis wird mit klarer Fehlermeldung abgelehnt und verändert keine Daten. |
| **Evidence** | `evidence/BKP-05_1.json`, `evidence/BKP-05_2.txt` |
| **Pass/Fail** | [ ] Pass [ ] Fail |

### 4.7 `x-opencode-session` (#1027)

**Verifiziert:** Die env-Variable `LLM_OPENCODE_SESSION` wird in `backend/llm_adapter/providers.py`
gelesen. Der Header `x-opencode-session` wird **ausschließlich** für den Provider `opencode_go`
angehängt und **nur, wenn die Variable gesetzt ist**. Ist sie nicht gesetzt, wird **kein** Header
gesendet (Default).

#### OCS-01 — Ohne `LLM_OPENCODE_SESSION` wird kein Header gesendet

| Feld | Inhalt |
|---|---|
| **Test-ID** | OCS-01 |
| **Ziel** | Bei ungesetzter Variable geht kein `x-opencode-session`-Header raus. |
| **Vorbedingung** | `LLM_PROVIDER=opencode_go` konfiguriert; `LLM_OPENCODE_SESSION` **nicht** gesetzt (leer/auskommentiert); Stack neu gestartet. |
| **Schritte (UI)** | 1. Eine LLM-nutzende Aktion auslösen, die einen Outbound-Call zum Provider erzeugt. |
| **Schritte (REST/MCP)** | Kein verifizierter REST/MCP-Endpoint für den Outbound-Call; Nachweis erfolgt über Proxy/Log/tcpdump bzw. einen Provider-seitigen Echo. |
| **Erwartetes Ergebnis** | Der Outbound-Request enthält **keinen** Header `x-opencode-session`. |
| **Negativfall** | Ein **leerer** Wert für `LLM_OPENCODE_SESSION` darf ebenfalls **nicht** zu einem Header mit leerem Wert führen (kein Header). |
| **Evidence** | `evidence/OCS-01_1.txt` (captured Request-Header) |
| **Pass/Fail** | [ ] Pass [ ] Fail |

#### OCS-02 — Gesetzte Variable wird 1:1 als Header übertragen

| Feld | Inhalt |
|---|---|
| **Test-ID** | OCS-02 |
| **Ziel** | Bei gesetzter Variable trägt der Header exakt deren Wert. |
| **Vorbedingung** | `LLM_OPENCODE_SESSION=<test-session-wert>` gesetzt; Stack neu gestartet; `LLM_PROVIDER=opencode_go`. |
| **Schritte (UI)** | 1. Eine LLM-nutzende Aktion auslösen. |
| **Schritte (REST/MCP)** | Kein verifizierter REST/MCP-Endpoint; Nachweis wie OCS-01. |
| **Erwartetes Ergebnis** | Der Outbound-Request enthält `x-opencode-session` mit **exakt** dem gesetzten Wert (keine Trimmung, kein Präfix/Suffix, keine Umkodierung). |
| **Negativfall** | Wird `LLM_PROVIDER` auf einen **anderen** Provider als `opencode_go` gestellt, darf der Header **nicht** gesendet werden — auch wenn `LLM_OPENCODE_SESSION` gesetzt ist. |
| **Evidence** | `evidence/OCS-02_1.txt` (captured Request-Header), ggf. `evidence/OCS-02_2.txt` (Gegenprobe anderer Provider) |
| **Pass/Fail** | [ ] Pass [ ] Fail |

> **Live-only:** Das exakte **Wertformat** des Headers (welcher Session-Identifier-String ein
> Provider akzeptiert) lässt sich nur an einer realen Instanz mit echter Provider-Konnektivität
> validieren (siehe §6, L2).

#### OCS-03 — Container-DNS-Check (Runbook-Checkliste)

| Feld | Inhalt |
|---|---|
| **Test-ID** | OCS-03 |
| **Ziel** | Der dokumentierte Diagnose-/Fix-Weg für fehlschlagende LLM-Calls im Backend-Container (DNS) ist ausführbar und wirksam. |
| **Vorbedingung** | Ein LLM-Call schlägt fehl (`ConnectError`); Referenz-Runbook: `deploy/README.md`, Abschnitt **„Troubleshooting: LLM calls fail with ConnectError (backend container DNS)"**. |
| **Schritte (UI)** | 1. LLM-nutzende Aktion auslösen und Fehler beobachten.<br>2. Runbook in `deploy/README.md` öffnen und die enthaltenen Diagnosebefehle der Reihe nach ausführen.<br>3. Den dort dokumentierten Fix anwenden.<br>4. Aktion erneut auslösen. |
| **Schritte (REST/MCP)** | Die konkreten Diagnose-/Fix-Befehle sind dem Runbook zu entnehmen (hier nicht dupliziert, um Abweichungen zu vermeiden). |
| **Erwartetes Ergebnis** | Checkliste ausführbar: jede Runbook-Anweisung liefert eine deutbare Ausgabe, der Fix ist reproduzierbar, und der LLM-Call gelingt danach. `curl localhost:8001/health/` bleibt `200`. |
| **Negativfall** | Ohne Anwendung des Fixes bleibt der Fehler bestehen — das ist erwartet und **kein** Release-Defekt; zu melden ist nur, wenn der dokumentierte Fix **nicht** wirkt. |
| **Evidence** | `evidence/OCS-03_1.txt` (Diagnose-Ausgaben), `evidence/OCS-03_2.txt` (erfolgreicher Call nach Fix) |
| **Pass/Fail** | [ ] Pass [ ] Fail |

> **Runbook-Referenz:** `deploy/README.md` → Abschnitt
> „Troubleshooting: LLM calls fail with ConnectError (backend container DNS)".
> **Live-only** (siehe §6, L6).

---

## 5. Regression-Kurzcheckliste

Ziel: sicherstellen, dass die bestehende Kernfunktionalität durch das Delta seit `beta.13` nicht
gebrochen ist. Kurzcheck — je Zeile ein Durchlauf, kein vollständiger Test.

| Test-ID | Prüfbereich | Schritte (kurz) | Erwartetes Ergebnis | Evidence | Pass/Fail |
|---|---|---|---|---|---|
| REG-01 | Login + CSRF | Login im UI; danach `AUTH_COOKIE_SECURE`/`CSRF_COOKIE_SECURE` **gleich** setzen, Stack neu starten, Formular absenden. Anschließend bewusst **mismatch** erzeugen (einer `True`, einer `False`/unset) und erneut absenden. | Passender Zustand: Formular-Submit funktioniert. Mismatch: Django-403-CSRF-Fehler. `curl localhost:8001/health/` zeigt nicht `"mismatch"` bei `csrf_cookie_secure_matches_auth`. | `evidence/REG-01_1.txt` | [ ] Pass [ ] Fail |
| REG-02 | Requirements/Needs CRUD | Anlegen, Bearbeiten, Löschen je eines Requirements und eines StakeholderNeeds. | Alle Operationen erfolgreich; gelöschtes Artefakt verschwindet aus Listen. | `evidence/REG-02_1.png` | [ ] Pass [ ] Fail |
| REG-03 | Architecture CRUD | Architecture Element anlegen, bearbeiten, löschen. | Erfolgreich, keine Fehler im UI oder Log. | `evidence/REG-03_1.png` | [ ] Pass [ ] Fail |
| REG-04 | TestCase CRUD | TestCase anlegen, bearbeiten, löschen. | Erfolgreich; TestCase erscheint in der Testfall-Liste. | `evidence/REG-04_1.png` | [ ] Pass [ ] Fail |
| REG-05 | ADR CRUD | ADR anlegen, bearbeiten, löschen. | Erfolgreich; Status/Felder bleiben erhalten. | `evidence/REG-05_1.png` | [ ] Pass [ ] Fail |
| REG-06 | Risk CRUD | Risk anlegen, bearbeiten, löschen. | Erfolgreich. | `evidence/REG-06_1.png` | [ ] Pass [ ] Fail |
| REG-07 | Issue CRUD | Issue anlegen, bearbeiten, löschen. | Erfolgreich. | `evidence/REG-07_1.png` | [ ] Pass [ ] Fail |
| REG-08 | Workflow-Statusübergang | An einem Artefakt einen erlaubten Statusübergang ausführen; anschließend einen **nicht** erlaubten versuchen. | Erlaubter Übergang gelingt; nicht erlaubter wird mit klarer Meldung abgelehnt. | `evidence/REG-08_1.png` | [ ] Pass [ ] Fail |
| REG-09 | Traceability + Impact-Analyse | Traceability-Ansicht öffnen; Impact-Analyse für ein verlinktes Artefakt ausführen. | Beide Ansichten laden und zeigen die erwarteten Verknüpfungen (konsistent mit §4.4). | `evidence/REG-09_1.png` | [ ] Pass [ ] Fail |
| REG-10 | Baselines (create + diff) | Baseline anlegen; ein Artefakt ändern; Diff der Baseline gegen aktuellen Stand erzeugen. | Baseline wird erzeugt; Diff zeigt genau die Änderung (feld-level). | `evidence/REG-10_1.png` | [ ] Pass [ ] Fail |
| REG-11 | CSV-Bulk-Import | Import einer kleinen CSV mit Requirements über den Bulk-Import. | Import erfolgreich; Anzahl importierter Artefakte stimmt mit der CSV überein. | `evidence/REG-11_1.png`, `evidence/REG-11_2.csv` | [ ] Pass [ ] Fail |
| REG-12 | PDF-Report-Export | PDF-Export für Workspace/Requirement anstoßen. | PDF wird erzeugt, ist öffnbar und enthält die erwarteten Artefakt-Daten. | `evidence/REG-12_1.pdf` | [ ] Pass [ ] Fail |
| REG-13 | Suche | Globale Suche nach `REQ-TP-001` und nach einem Begriff aus einem `rationale`. | Treffer werden gefunden und sind anklickbar. | `evidence/REG-13_1.png` | [ ] Pass [ ] Fail |
| REG-14 | Audit-Log | Audit-Log öffnen und eine Aktion aus diesem Testlauf (z. B. Anlage von `REQ-TP-001`) finden. | Der Eintrag ist mit User, Zeitstempel und Aktion vorhanden. | `evidence/REG-14_1.png` | [ ] Pass [ ] Fail |
| REG-15 | MCP-Handshake `tools/list` | JSON-RPC `tools/list` gegen `/mcp/` (alternativ `/api/v1/mcp/`) aufrufen. | Der Katalog wird vollständig zurückgegeben; die Tool-Anzahl ist **215** (PR #1026) — **weiches** Kriterium: Abweichung dokumentieren, aber als Hinweis statt als harter Blocker behandeln. Zusätzlich `initialize` und `ping` aufrufen. | `evidence/REG-15_1.json` | [ ] Pass [ ] Fail |

```json
{
  "jsonrpc": "2.0",
  "id": 99,
  "method": "tools/list",
  "params": {}
}
```

> **Hinweis zur Tool-Anzahl:** Die erwartete Zahl **215** ist im Repo dokumentiert. Sie ist im
> vorliegenden Testplan als **weiches** Kriterium geführt (Katalog-Rückgabe zählt, Zahl dokumentieren).

---

## 6. Bekannte Grenzen & Hinweise

| # | Hinweis |
|---|---|
| 1 | **`bluepencil` = DEBUG/QS-only.** Nicht im Standard-Testlauf aktivieren, nicht testen (§2.7). Ein Bluepencil-Befund ist kein Release-Blocker. |
| 2 | **Live-only-Punkte L1–L8** (siehe unten) benötigen eine echte Instanz mit echter Provider-Konnektivität und sind offline **nicht** validierbar. Sie werden als „live-only" markiert und im Sign-off ausgewiesen. |
| 3 | **Honcho** läuft nur mit `--profile honcho`. Ohne Profil sind Honcho-Testfälle (MEM-12) nicht durchführbar. |
| 4 | **Multi-Instanz:** Für einen zweiten Stack **beide** Ports ändern (`BACKEND_PORT` **und** `FRONTEND_PORT`) — sonst Portkollision/inkonsistente URLs. |
| 5 | **Versions-Drift:** `REQOGNILOOM_VERSION` in `.env` überschreibt den Image-Tag-Default der Compose-Datei. Wird ein falsches Image gezogen, **zuerst diese Variable prüfen**. |
| 6 | **Schreib-Rate-Limit:** `MEMORY_WRITE_RATE_LIMIT_PER_HOUR` (Default `60`, `0` = unbegrenzt). Ein Burst über dem Limit ist erwartetes Verhalten, kein Defekt (§2.8, MEM-16). |
| 7 | **Memory-Umschlag-Keys:** `backend, ok, detail, degraded, digest_available` mit `degraded = not ok or degraded`. Fehlt eines dieser Keys, ist das ein Befund. |
| 8 | **`memory.forget`** (Punktnotation) ist korrekt; `memory_forget` (Unterstrich) ist falsch und existiert nur als Tippfehler in `.env.example`. |
| 9 | **Nicht verifiziert / nicht im Scope:** REST-Pfade für Artefakttypen außerhalb der verifizierten Liste; Scope-Level-Purge; der MCP-Toolname für Requirements-Schreibzugriffe; der HTTP-Header-Name des MCP-API-Keys; der konkrete uid-Backfill-Befehl. Diese Punkte nicht als Testfälle erzwingen. |

### Live-only-Punkte (L1–L8)

| ID | Live-only-Punkt | Begründung |
|---|---|---|
| L1 | Prompt-Injektion mit **echtem** LLM-Provider (Inhalt der Sektionen `Artifact context:` / `Workspace context:` / `User context:`) | Nur mit realer Provider-Konnektivität inhaltlich prüfbar (MEM-06). |
| L2 | **Exaktes Wertformat** des Headers `x-opencode-session` und der tatsächliche Outbound-Request | Provider akzeptiert nur bestimmte Session-Identifier (OCS-02). |
| L3 | Honcho: Schreiben über den echten externen Dienst | Erfordert laufende Honcho-Instanz (MEM-12). |
| L4 | Honcho: **Löschung** im externen Store nachweisbar | Harte Abnahmebedingung, nur am externen Store prüfbar (MEM-12). |
| L5 | Honcho Sessions/Deriver/`digest` (PR #1025) — server-seitige Hintergrundjobs | Läuft im Honcho-Server, nicht im ReqogniLoom-Backend. |
| L6 | Container-DNS `ConnectError`-Runbook (`deploy/README.md`) | Reproduzierbar nur mit realem Provider-Call (OCS-03). |
| L7 | Ollama-Embeddings inkl. Dimension-Resize (768) und semantischer Suche | Erfordert laufenden Ollama-Endpoint und Migrationsschritte. |
| L8 | LLM-Laufzeit-/Timeout-Verhalten an echten Providern (lang laufende Workspace-Tools) | Nur unter realer Provider-Latenz bewertbar. |

---

## 7. Defekt-Meldevorlage

```markdown
### Defekt <ID / laufende Nummer>

**Titel:** <kurz, präzise, mit Test-ID — z. B. "MEM-13: stille Leerliste statt degraded bei gestopptem Memory-Backend">

**Severity:** S1 | S2 | S3 | S4   (Definition siehe unten)

**Betroffene Version:** 1.8.0-beta.14
**Commit-SHA:** 06978ba4549bb170276cb9f0e78d822bffd4c0b4

**Umgebung:**
- Betriebssystem / Host:
- Docker Engine / Compose-Version (`docker compose version`):
- `MEMORY_BACKEND`:
- `LLM_PROVIDER`:
- Verwendetes Image (backend/frontend Tag):
- `REQOGNILOOM_VERSION` aus `.env`:
- Relevante weitere env-Variablen (ohne Secrets):

**Repro-Schritte:**
1.
2.
3.

**Erwartetes Verhalten:**

**Erhaltenes Verhalten:**

**Logs / Screenshot / Response-Body:**
- Datei:
- Auszug:

**Betroffene Route bzw. MCP-Tool:**
- REST: <z. B. GET /api/v1/workspaces/<workspace_id>/memory/digest/>
- MCP: <z. B. memory.digest>
- UI-Pfad:

**Häufigkeit:** immer | manchmal | einmalig

**Zusatzhinweis (optional):** <z. B. spezifische Datenlage, Workspace-Größe, Population>
```

**Severity-Definitionen**

| Severity | Definition |
|---|---|
| **S1** | Release-Blocker: Kernfunktion unbrauchbar, Datenverlust/-lecks, Sicherheitslücke, Crash/500 in zentralen Flows. |
| **S2** | Schwere Funktionseinschränkung ohne Datenverlust: relevanter Flow fehlerhaft, aber umgehbar; kein Workaround oder nur mit Aufwand. |
| **S3** | Kleinere Funktionseinschränkung mit einfachem Workaround; inkonsistente Anzeige/Fehlermeldung. |
| **S4** | Kosmetik, Textfehler, Doku-/Konsistenz-Hinweis ohne Funktionsbeeinträchtigung. |

---

## 8. Abnahme / Sign-off

### 8.1 Prüfübersicht

| Prüfbereich | Owner | Datum | Ergebnis (Pass/Fail) | Bemerkung |
|---|---|---|---|---|
| §4.1 Workspace-Gedächtnis v2 (MEM-01 … MEM-16) | | | | |
| §4.2 uid (UID-01 … UID-05) | | | | |
| §4.3 INCOSE/IEEE-Attribute (ATTR-01 … ATTR-04) | | | | |
| §4.4 Trace-Katalog (TRC-01 … TRC-04) | | | | |
| §4.5 Link-Defaults aus env (LNK-01 … LNK-03) | | | | |
| §4.6 Admin-Backup gzip (BKP-01 … BKP-05) | | | | |
| §4.7 `x-opencode-session` + DNS (OCS-01 … OCS-03) | | | | |
| §5 Regression (REG-01 … REG-15) | | | | |
| **Live-only L1–L8** (separat ausweisen) | | | | |
| **Defekte gesamt** | | | | S1: ___ / S2: ___ / S3: ___ / S4: ___ |

### 8.2 Release-Empfehlung

> **Empfehlung:** [ ] Freigabe (kein S1/S2 offen) &nbsp;|&nbsp; [ ] Freigabe mit Auflagen (nur S3/S4 offen) &nbsp;|&nbsp; [ ] Keine Freigabe (mindestens ein S1/S2 offen)
>
> **Begründung:** ________________________________________________________________
>
> **Offene Live-only-Punkte (L1–L8), die vor Produktivfreigabe separat validiert werden müssen:**
> ________________________________________________________________

### 8.3 Unterschriften

| Rolle | Name | Datum | Unterschrift |
|---|---|---|---|
| Testdurchführung | | | |
| Technische Abnahme | | | |
| Release-Verantwortung | | | |
