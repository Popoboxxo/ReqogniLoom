---
type: STRATEGY
scope: Testplan v1.8.0-beta.15
status: final
date: 2026-09-23
author_agent: release
---

# Testplan v1.8.0-beta.15

> **Hand-off-Testplan.** Dieses Dokument ist für eine:n **externe:n Tester:in ohne Vorkenntnisse** geschrieben.
> Alle Schritte sind so formuliert, dass sie ohne Repository-Wissen, ohne Agenten-Kontext und ohne
> Vorwissen über die Historie ausgeführt werden können. Jeder Testfall hat einen **Negativfall** und
> eine **Evidence**-Zeile. Die Pass/Fail-Spalte wird während der Durchführung ausgefüllt.

**Durchführungshinweise**

- **Test-IDs** sind stabil: `VAL-*`, `WAV-*`, `EMB-*`, `EMP-*`, `TLK-*`, `CSS-*`, `SED-*`, `TRC-*`, `REG-*`.
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

> **Kein Testlauf in diesem Branch.** Dieser Plan ist eine **Vorbereitung**; die Pass/Fail-Spalten
> sind leer. Es werden hier **keine** Testergebnisse behauptet.

---

## 1. Ziel & Prüfgegenstand

| Feld | Wert |
|---|---|
| Release | **1.8.0-beta.15** |
| Backend-Image | `ghcr.io/popoboxxo/reqogniloom-backend:1.8.0-beta.15` |
| Frontend-Image | `ghcr.io/popoboxxo/reqogniloom-frontend:1.8.0-beta.15` |
| Commit-SHA (Basis) | `851955ec3ce2c7dd4c40de05a05e1ca2102b2756` |
| Datum | 2026-09-23 |
| Branch | `chore/release-v1.8.0-beta.15` |
| Vorgänger-Release | `1.8.0-beta.14` (Vergleichsbasis) |

### 1.1 Im Scope (Delta seit `1.8.0-beta.14`)

| Delta (PR) | Thema | Testbereich |
|---|---|---|
| #1035 | Validation als Säule: TestCase-Provenienz, Goal-Regeln, Baseline-Drift | §4.1 (`VAL-*`) |
| #1037 | SE-Auditor Waivers/Suppression | §4.2 (`WAV-*`) |
| #1030 | TRACE-P1 bei zyklischer Hierarchie | §4.8 (`TRC-*`) |
| #1029 | Embedding-Dimensionen im Image-Deployment, `/health/`-Spiegelung | §4.3 (`EMB-*`) |
| #1038 | `seed_demo` bootstrappt Attribute-Definitions | §4.7 (`SED-*`) |
| #1039 | Empty-State-Anleitung | §4.4 (`EMP-*`) |
| #1033 | Barrierefreies Trace-Link-Dropdown | §4.5 (`TLK-*`) |
| #1040–#1047 | Inline-Style→CSS-Module + ESLint-Gate | §4.6 (`CSS-*`) |
| #1034 | E2E-Härtung + tenant_id-Guard | §5 (`REG-*`) |
| #1032 | Bluepencil-Re-Vendoring (`alpha.2`) | §5 (`REG-*`) |
| #1036 | Build-Artefakte ignoriert | §5 (`REG-*`) |

### 1.2 Nicht im Scope

- **`bluepencil`** — die optionale selbst-gehostete Review-Sidecar ist **DEBUG/QS-only**
  und wird im Standard-Testlauf **nicht aktiviert und nicht getestet** (siehe Warnbox §2.6).
- **Live-only-Punkte** — benötigen echte Provider-Konnektivität (LLM, Honcho, Embedding-Endpoint)
  und sind offline nicht validierbar.
- **Last-, Performance- und Sicherheits-Penetrationstests** — nicht Bestandteil dieses Testplans.
- **Interne Architektur-Invarianten** (z. B. `tenant_id`-Prädikate im CTE, ESLint-Baseline-Zahlen)
  sind über automatisierte Suiten abgedeckt und **nicht** manuell zu prüfen; sie erscheinen hier nur
  als Regressionseintrag (§5).

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

### 2.4 Stack starten (kanonisch)

```bash
docker compose -f deploy/docker-compose.yml --project-directory . up -d
```

> Für §4.3 (Embedding-Dimensionen) ist der Stack **aus dem Image** zu starten — genau dieser Pfad
> wurde in #1029 korrigiert. Ein Source-Checkout (`make up`) prüft einen anderen Pfad.

### 2.5 Health-Check

```bash
curl localhost:8001/health/
```

Der Health-Endpoint liegt auf Pfad **`/health/`** (Backend-Root-URLconf; **mit** Trailing Slash).
Erwartet: HTTP `200` mit `{"status": "ok", "checks": {...}, "warnings": [...]}`.

Relevante Felder für diesen Testlauf:

| Feld | Erwartung | Testfall |
|---|---|---|
| `checks.database` | `"ok"` | §4.3 |
| `checks.memory_backend` | `"ok"` | §4.3 |
| `checks.embedding_dimensions` | `"ok"` (bei ausgerichtetem Stack) | `EMB-02` |
| `warnings` | leer im ausgerichteten Zustand | `EMB-03` |

Zusätzlich der Admin-Systemstatus (Dashboard-Sicht): `GET /api/v1/admin/health/` → HTTP `200`.

### 2.6 ⚠ WARNUNG: `bluepencil`

> **`bluepencil` (optionale selbst-gehostete Review-Sidecar) ist DEBUG/QS-only.**
> Sie darf im **Standard-Testlauf nicht aktiviert und nicht getestet** werden. Es gibt **keinen**
> Auth- und **keinen** Tenant-Isolation-Schutz, und eine einzige JSON-Datei hält die Notizen
> **aller** Workspaces. `BLUEPENCIL_ENABLED=0` muss im Testlauf gesetzt bleiben.
> Ein Bluepencil-Befund ist **kein** Release-Blocker für `1.8.0-beta.15` — er ist außerhalb des Scopes.

### 2.7 Optional: Honcho-Profil (nur für `EMB-04`)

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
| 3.2 | Workspace anlegen, Name: `TP-b15 Workspace` | Workspace erscheint in der Workspace-Liste | Screenshot |
| 3.3 | Goal anlegen, Titel: `GOAL-TP-001 Goal beta.15` | Goal aktiv, Artefakt angelegt | Screenshot |
| 3.4 | Stakeholder-Need anlegen, Titel: `SN-TP-001 Stakeholder Need beta.15` | Artefakt angelegt | Screenshot |
| 3.5 | Requirement anlegen, Titel: `REQ-TP-001 Requirement beta.15` | Artefakt angelegt | Screenshot |
| 3.6 | TestCase anlegen, Titel: `TC-TP-001 Testfall beta.15` | TestCase angelegt, `origin` sichtbar (§4.1) | Screenshot |
| 3.7 | Zweiten Workspace anlegen, Name: `TP-b15 Workspace B` | Zweiter Workspace existiert | Screenshot |
| 3.8 | Zweiten User anlegen (System-Admin-Bereich), Name: `tp-b15-user-b`, Rolle **Viewer** | User existiert, ist Mitglied von `TP-b15 Workspace` | Screenshot |

> **REST-Pfade für die Artefaktanlage der Typen aus 3.3–3.6 (außer `requirements/` und `testcases/`)
> sind nicht im Scope / nicht verifiziert.** Diese Testdaten werden ausschließlich über die UI angelegt.
> Verifizierte Schreibpfade: `POST /api/v1/requirements/`, `POST /api/v1/testcases/`.

---

## 4. Schwerpunkttests — Neuerungen seit `beta.14`

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

### 4.1 Validation als gleichwertige Säule (#1035)

**Verifizierte Oberflächen**

| Oberfläche | Referenz |
|---|---|
| Review-Flag setzen | `POST /api/v1/testcases/{id}/review/` |
| TestCase-Felder | `origin` (`manual` \| `ai_generated`), `reviewed`, `scenario_kind` |
| Coverage-Report | `GET /api/v1/requirements/coverage-report/?workspace_id=<uuid>` |
| Baseline-Drift | `GET /api/v1/artifacts/{id}/baseline-membership/` |

| Test-ID | Ziel | Vorbedingung | Schritte | Erwartetes Ergebnis | Negativfall | Evidence | Pass/Fail |
|---|---|---|---|---|---|---|---|
| `VAL-01` | `origin`/`reviewed` sind sichtbar und `reviewed` wird nur über die Review-Aktion gesetzt | `TC-TP-001` existiert | UI: TestCase öffnen → Provenienz-Anzeige lesen. Dann `POST /api/v1/testcases/{id}/review/` mit `{}` | `reviewed` springt auf `true`; die Anzeige aktualisiert sich | PATCH auf `testcases/{id}` mit `{"reviewed": false}` → **400** (`reviewed is set via POST /api/v1/testcases/{id}/review/`) | Screenshot + Response-Body | |
| `VAL-02` | Nicht-Objekt-Body wird abgelehnt | `TC-TP-001` existiert | `POST /api/v1/testcases/{id}/review/` mit Body `[]` (bzw. `"x"`) | **400** `VALIDATION_ERROR`, `reviewed` **unverändert** | leerer Body `{}` bleibt erlaubt und setzt den Default `reviewed=true` | Response-Body | |
| `VAL-03` | Ein ungeprüfter AI-TestCase zählt **nicht** als Verifikationsnachweis | TestCase mit `origin="ai_generated"`, `reviewed=false` | Coverage-Report für den Workspace abrufen | `pending_ai_review` > 0; der TestCase fehlt in der Coverage-Zählung | `VAL-01` ausführen (`reviewed=true`) → Report erneut abrufen: `pending_ai_review` sinkt, Coverage steigt | JSON-Report | |
| `VAL-04` | `goals_enabled` defaultet auf `true` und VAL-P1 greift | Neuer Workspace | `GET /api/v1/workspaces/{id}/` → Feld `goals_enabled` lesen | `true` ohne explizite Setzung | Workspace mit `goals_enabled=false` → VAL-P1 wird **nicht** gemeldet | JSON + Screenshot | |
| `VAL-05` | VAL-P1 ist advisory (blockiert keinen Baseline-Build) | Workspace mit `goals_enabled=true`, mindestens ein aktives Goal, ein aktives StakeholderNeed **ohne** `satisfies`-Link zu einem Goal | Validation ausführen, dann Baseline bauen | VAL-P1 erscheint als **Warning**, nicht als Blocker; der Baseline-Build läuft durch | Goal verlinken → VAL-P1 verschwindet | Screenshot Validation + Baseline-Ergebnis | |
| `VAL-06` | Edit an baselined Artefakt erzeugt Drift statt Fehler | `REQ-TP-001` ist in einer Baseline enthalten | Requirement-Titel ändern und speichern | Save gelingt; `GET /api/v1/artifacts/{id}/baseline-membership/` meldet Drift; `baseline_drift` erscheint im `retrieve` | PATCH mit `baseline_drift` im Payload → **400** `Unknown field` (Feld ist read-only) | Screenshot + 2 Response-Bodies | |

### 4.2 SE-Auditor Waivers / Suppression (#1037)

**Verifizierte Oberflächen**

| Oberfläche | Referenz |
|---|---|
| Waiver anlegen/lesen | `POST` / `GET /api/v1/workspaces/{id}/audit/waivers/` |
| Audit-Report inkl. Suppressed | `GET /api/v1/workspaces/{id}/audit/?include_suppressed=true` |
| MCP | `audit.waive_finding` (write, ADMIN-Tier), `audit.waivers` (read) |
| Fehlercodes (MCP) | `-32008` (WAIVER_REASON_REJECTED), `-32009` (WAIVER_FINDING_NOT_BLOCKING), `-32010` (SUPPRESSION_EXPIRED) |
| UI | Audit-Dashboard: Aktion *Waive*, Show-Suppressed-Filter, Suppressed-Badge, Waivers-Panel |

| Test-ID | Ziel | Vorbedingung | Schritte | Erwartetes Ergebnis | Negativfall | Evidence | Pass/Fail |
|---|---|---|---|---|---|---|---|
| `WAV-01` | Ein Blocker-Finding lässt sich mit Begründung waiven | Audit-Lauf mit mindestens einem **Blocker** | UI: Audit-Dashboard → Finding → *Waive* → Begründung eingeben → bestätigen | Finding wird in-place als suppressed markiert; `counts.suppressed` steigt; Eintrag im Waivers-Panel | *Waive* **ohne** Begründung absenden → Dialog blockiert / `WAIVER_REASON_REJECTED` | Screenshot + Response | |
| `WAV-02` | Waive-Fehler landen **nicht** im Adopt→Modify-Pfad | Wie `WAV-01` | Eine ungültige Begründung absenden und danach die Aktionen am Finding prüfen | Finding bleibt auf *Adopt*; es erscheint **kein** *Modify*; kein Suppression-Eintrag; Fehlermeldung im Waive-Kanal | — (dies ist der Regressionskern) | Screenshot | |
| `WAV-03` | Ein Nicht-Blocker-Finding ist nicht waivbar | Audit-Lauf mit nur **Warnings** | Waive auf ein Warning-Finding versuchen | `WAIVER_FINDING_NOT_BLOCKING` (REST: entsprechender Code, **nicht** 422) | — | Response-Body | |
| `WAV-04` | `include_suppressed` filtert strikt | Mindestens ein gewaivtes Finding | `GET .../audit/` mit und ohne `include_suppressed=true` | Ohne Flag: suppressed Findings fehlen und die Zählung ist entsprechend kleiner; mit Flag: sie erscheinen markiert | Ungültiger Wert (z. B. `include_suppressed=maybe`) → **400** | 2 JSON-Bodies | |
| `WAV-05` | Waivers sind rollen-gated | `tp-b15-user-b` (Viewer) | `GET /api/v1/workspaces/{id}/audit/waivers/` als Viewer, dann als Admin | Viewer → **403** `PERMISSION_DENIED`; Admin → **200** | MCP `audit.waivers` als Editor → `PERMISSION_DENIED` (Approval-Authority) | 2 Response-Bodies | |
| `WAV-06` | Fremder Workspace antwortet `NOT_FOUND` | Zwei Workspaces | Waiver für ein Finding aus `TP-b15 Workspace B` über die Route von `TP-b15 Workspace` anfordern | **404** `NOT_FOUND` (**nicht** `WAIVER_FINDING_NOT_BLOCKING`) | nicht-string Begründung → **400** `VALIDATION_ERROR` | Response-Body | |

**Beispiel: Waiver anlegen**

```http
POST /api/v1/workspaces/<workspace_id>/audit/waivers/
Content-Type: application/json

{
  "finding_key": "<finding_key aus dem Audit-Report>",
  "reason": "<Begründung, Pflicht>"
}
```

### 4.3 Embedding-Dimensionen & `/health/`-Spiegelung (#1029)

**Verifizierte Oberflächen**

| Oberfläche | Referenz |
|---|---|
| Health-Signal | `GET /health/` → `checks.embedding_dimensions` = `"ok"` \| `"mismatch"` (+ `warnings`) |
| Management-Command (Image-Deployment) | `python manage.py align_embedding_dimensions` |
| Diagnose | `python manage.py verify_embedding_dimensions` |

| Test-ID | Ziel | Vorbedingung | Schritte | Erwartetes Ergebnis | Negativfall | Evidence | Pass/Fail |
|---|---|---|---|---|---|---|---|
| `EMB-01` | Stack aus dem Image startet mit ausgerichteten Spalten | `deploy/docker-compose.yml` gestartet | `docker compose ... logs migrate` und `honcho-migrate` prüfen (sofern Honcho-Profil) | Migrationen laufen fehlerfrei; **keine** Dimension-Mismatch-Meldung | — | Log-Auszug | |
| `EMB-02` | `/health/` meldet `embedding_dimensions: "ok"` | `EMB-01` grün | `curl localhost:8001/health/` | `checks.embedding_dimensions == "ok"`, `status == "ok"` | — | JSON-Body | |
| `EMB-03` | Mismatch wird **als Warning** sichtbar, **ohne** 503 | Testinstanz mit absichtlich abweichender `EMBEDDING_VECTOR_DIMENSIONS` | `curl localhost:8001/health/` | HTTP **200**; `checks.embedding_dimensions == "mismatch"`; `warnings` enthält den Hinweis auf `verify_embedding_dimensions` / `align_embedding_dimensions` | Der Stack darf **nicht** in einen Restart-Loop laufen (Mismatch ist bewusst **kein** `degraded`) | JSON-Body + Container-Status | |
| `EMB-04` | `honcho-migrate` richtet die Spalten idempotent aus | Honcho-Profil, abweichende Breite | `honcho-migrate` ausführen, danach erneut `EMB-02` prüfen | Spaltenbreite entspricht der konfigurierten Provider-Breite; ein zweiter Lauf ändert nichts | Vorsicht: `align_embedding_dimensions` bei **veralteter** `EMBEDDING_VECTOR_DIMENSIONS` würde die Spalten auf die falsche Breite umschreiben und Vektoren verwerfen — vorher die Zielbreite setzen | Log + `/health/` | |

### 4.4 Empty-State-Anleitung (#1039)

| Test-ID | Ziel | Vorbedingung | Schritte (UI) | Erwartetes Ergebnis | Negativfall | Evidence | Pass/Fail |
|---|---|---|---|---|---|---|---|
| `EMP-01` | Leere ICD-Liste erklärt die Anlage | Neuer Workspace ohne ICD | ICD-Bereich öffnen | Statt einer leeren Fläche erscheint eine Anleitung zum Anlegen des ersten ICD | Nach Anlage eines ICD verschwindet die Anleitung | Screenshot (vorher/nachher) | |
| `EMP-02` | Leerer Custom-Fields-Editor erklärt die Anlage | Artefakt ohne Custom Fields | Artefakt öffnen → Custom Fields | Anleitung sichtbar | Nach Hinzufügen eines Feldes verschwindet sie | Screenshot | |
| `EMP-03` | Leerer Trace-Link-Panel erklärt die Anlage | Requirement ohne Trace-Links | Requirement öffnen → Trace-Links | Anleitung sichtbar | Nach Anlegen eines Links verschwindet sie | Screenshot | |
| `EMP-04` | Beide Sprachen sind vollständig | Sprache DE und EN | UI auf EN umstellen, `EMP-01`–`EMP-03` wiederholen | Alle neuen Texte existieren auf DE **und** EN, keine Fallback-Platzhalter | — | 2 Screenshots | |

### 4.5 Barrierefreies Trace-Link-Dropdown (#1033)

| Test-ID | Ziel | Vorbedingung | Schritte (UI) | Erwartetes Ergebnis | Negativfall | Evidence | Pass/Fail |
|---|---|---|---|---|---|---|---|
| `TLK-01` | Dropdown ist per Tastatur bedienbar | Requirement-Detail geöffnet | Mit `Tab` den Trace-Link-Typ fokussieren, mit `Enter`/`Space` öffnen, mit Pfeiltasten navigieren, mit `Enter` wählen | Fokus sichtbar, Auswahl möglich, Fokus kehrt sinnvoll zurück; kein Fokusverlust auf `<body>` | `Esc` schließt das Dropdown ohne Auswahl und behält den Fokus am Auslöser | Screenshot + ggf. kurze Bildschirmaufnahme | |
| `TLK-02` | Keine hartkodierten Farben/Größen | Wie `TLK-01` | Sichtprüfung des Dropdowns | Darstellung nutzt die Design-Tokens (konsistent mit dem Rest der UI) | — | Screenshot | |

### 4.6 Inline-Style→CSS-Module & ESLint-Gate (#1040–#1047)

> Diese Etappen sind **Refactorings ohne Verhaltens- oder Sichtänderung**. Ziel der manuellen
> Prüfung ist ausschließlich, dass **keine visuelle Regression** entstanden ist.

| Test-ID | Ziel | Vorbedingung | Schritte | Erwartetes Ergebnis | Negativfall | Evidence | Pass/Fail |
|---|---|---|---|---|---|---|---|
| `CSS-01` | Keine visuelle Regression auf den Kernseiten | Standard-Stack | Nacheinander öffnen: Dashboard, Requirements-Liste/-Detail, Test-Runs-Liste/-Detail, Baselines + Artifact-Diff, Traceability, Impact, API-Keys, Audit-Dashboard | Layout, Farben und Abstände wie in `1.8.0-beta.14`; keine ungestylten Elemente | — | Screenshots je Seite | |
| `CSS-02` | Interaktionszustände bleiben erhalten | Wie `CSS-01` | Hover/Fokus/Auswahl auf Listenzeilen und Buttons prüfen (u. a. Test-Runs-Liste, Baselines) | Hover- und Selected-Zustände sichtbar; Hover auf Listeneinträgen funktioniert weiter | — | Screenshots | |
| `CSS-03` | Split-View-Drag funktioniert weiter | Eine Ansicht mit Split-View-Divider | Divider ziehen | Panel-Größe folgt der Maus; der Übergang ist animiert (nicht eingefroren) | Zurücksetzen der Größe möglich | Screenshot/Video | |
| `CSS-04` | ESLint-Gate ist aktiv | Source-Checkout | `npx eslint src` im `frontend/`-Verzeichnis | **0 Errors**; `local/no-static-inline-style` ist aktiv und die Exemption-Liste ist leer | Eine neu hinzugefügte statische `style={{…}}`-Angabe in einer `.tsx`-Datei → ESLint-Fehler | Terminal-Ausgabe | |

### 4.7 `seed_demo` bootstrappt Attribute-Definitions (#1038)

| Test-ID | Ziel | Vorbedingung | Schritte | Erwartetes Ergebnis | Negativfall | Evidence | Pass/Fail |
|---|---|---|---|---|---|---|---|
| `SED-01` | Eine nur via `seed_demo` befüllte DB hat globale Attribute-Definitions | Frische DB (nur Migrationen + `seed_demo`) | `python manage.py seed_demo` ausführen, dann Custom Fields in der UI öffnen | Globale Attribute-Definitions existieren; der Custom-Fields-Bereich ist **nicht** leer | — | Screenshot + Command-Ausgabe | |
| `SED-02` | `seed_demo` ist idempotent | `SED-01` ausgeführt | `seed_demo` ein **zweites Mal** ausführen und den Endzustand vergleichen | Identischer Endzustand (Definitions-Inhalte und Versionen unverändert), keine Duplikate | — | 2 Command-Ausgaben + Zählwerte | |

### 4.8 TRACE-P1 bei zyklischer Hierarchie (#1030)

| Test-ID | Ziel | Vorbedingung | Schritte | Erwartetes Ergebnis | Negativfall | Evidence | Pass/Fail |
|---|---|---|---|---|---|---|---|
| `TRC-01` | TRACE-P1 verstummt bei Zyklen nicht mehr | Workspace mit einer zyklischen Hierarchie (A → B → A) | Traceability-Validierung ausführen | TRACE-P1 liefert ein **Ergebnis** (Befund), keinen leeren/„stillen" Report | Zyklus auflösen → TRACE-P1 verhält sich wie bei azyklischer Hierarchie | Screenshot/JSON | |

---

## 5. Regression-Kurzcheckliste

| Test-ID | Prüfung | Erwartetes Ergebnis | Evidence | Pass/Fail |
|---|---|---|---|---|
| `REG-01` | Login/Logout, Workspace-Wechsel | Funktionieren unverändert | Screenshot | |
| `REG-02` | Requirements-CRUD inkl. PATCH | Anlegen, Ändern, Löschen funktionieren | Screenshot | |
| `REG-03` | TestCase-CRUD | Anlegen, Ändern funktionieren; `origin` ist **nicht** editierbar (read-only) | Screenshot | |
| `REG-04` | `GET /health/` und `GET /api/v1/admin/health/` | Beide HTTP `200` | JSON | |
| `REG-05` | MCP `ping` / `initialize` / `tools/list` | Antworten gemäß JSON-RPC 2.0 | JSON | |
| `REG-06` | Bluepencil bleibt deaktiviert | Kein Bluepencil-Loader im Netzwerkverkehr | Network-Log | |
| `REG-07` | `docker compose config -q` für beide Deployment-Dateien | Exit 0 (im Repo verifiziert, §6) | Terminal | |
| `REG-08` | Build-Artefakte erscheinen nicht im Git-Status | `frontend/tsconfig*.tsbuildinfo` und `frontend/vite.config.{js,d.ts}` sind ignoriert | `git status` | |
| `REG-09` | E2E-/CI-Suiten | Grün (Nachweis über CI des Release-PR, nicht manuell) | CI-Link | |
| `REG-10` | Bluepencil-Bundle-Hash | Re-Vendoring `alpha.2` ist byte-identisch / SHA-256-gepinnt | Konsolen-/Netzwerkprüfung | |

---

## 6. Bekannte Grenzen & Hinweise

| Punkt | Status |
|---|---|
| `.env.example` (Zeile 314) benennt das MCP-Tool `memory_forget` (Unterstrich), real ist `memory.forget` (Punkt) | **Offener Follow-up** (dokumentarisch, kein Release-Blocker) — bereits im beta.14-Bericht geführt |
| Vorbestehende `tsc`-Fehler `DiagramCreateForm.tsx:88`, `MermaidEditor.test.tsx:117` | Out-of-scope laut PR #1047; Lint und vitest sind grün |
| MCP-HTTP-Header-Name für API-Keys | **nicht verifiziert** — der Instanz-Doku/UI entnehmen |
| Pre-Release-Gate-Hook unter Windows | Der deployte Hook hat CRLF-Zeilenenden; für reproduzierbare Läufe unter Linux ist eine LF-Normalisierung nötig (siehe Release-Bericht §6.1) |
| `docker-image-scan`-Gate | Self-Skip: kein `Dockerfile` im Repo-Root und `trivy` nicht installiert → **nicht gelaufen**, nicht „bestanden" |
| `artifact-freshness`-Gate | Self-Skip: kein `.agent-meta/generated-artifacts.yaml` konfiguriert → **nicht gelaufen** |

---

## 7. Defekt-Meldevorlage

### Defekt <ID / laufende Nummer>

| Feld | Inhalt |
|---|---|
| **Test-ID** | z. B. `WAV-02` |
| **Release** | `1.8.0-beta.15` |
| **Image-Tag** | z. B. `ghcr.io/popoboxxo/reqogniloom-backend:1.8.0-beta.15` |
| **Umgebung** | OS, Browser, `BACKEND_PORT`/`FRONTEND_PORT`, Profil (Standard/Honcho) |
| **Schritte** | 1. … 2. … 3. … |
| **Erwartet** | … |
| **Beobachtet** | … |
| **HTTP-Status / Fehlercode** | z. B. `400 VALIDATION_ERROR` bzw. MCP `-32009` |
| **Evidence** | `evidence/<TEST-ID>_<nr>.png` / `.json` |
| **Reproduzierbar** | immer / manchmal / einmalig |

---

## 8. Abnahme / Sign-off

### 8.1 Prüfübersicht

| Bereich | Testfälle | Bestanden | Fehlgeschlagen | Offen |
|---|---|---|---|---|
| §4.1 Validation (`VAL-*`) | 6 | | | |
| §4.2 Waivers (`WAV-*`) | 6 | | | |
| §4.3 Embedding (`EMB-*`) | 4 | | | |
| §4.4 Empty-State (`EMP-*`) | 4 | | | |
| §4.5 Trace-Link-Dropdown (`TLK-*`) | 2 | | | |
| §4.6 CSS-Module (`CSS-*`) | 4 | | | |
| §4.7 `seed_demo` (`SED-*`) | 2 | | | |
| §4.8 TRACE-P1 (`TRC-*`) | 1 | | | |
| §5 Regression (`REG-*`) | 10 | | | |
| **Summe** | **39** | | | |

### 8.2 Release-Empfehlung

- [ ] Freigabe ohne Einschränkung
- [ ] Freigabe mit bekannten Einschränkungen (siehe §6)
- [ ] Keine Freigabe (Blocker siehe Defektliste)

### 8.3 Unterschriften

| Rolle | Name | Datum | Unterschrift |
|---|---|---|---|
| Tester:in | | | |
| Release-Owner | | | |
