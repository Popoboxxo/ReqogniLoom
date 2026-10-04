---
type: PLAN
scope: interface-contracts
status: final
author_agent: api-specialist
date: 2026-10-01
parent: IMPLEMENTATION_PLAN.md
branch: chore/audit-review-2026-09
epic: INT / RES
sources:
  - docs/audit/2026-09/review/plan/INTEGRATION_LLM.md
  - docs/audit/2026-09/review/plan/RESILIENCE_HEALTH.md
  - docs/audit/2026-09/review/IMPLEMENTATION_PLAN.md
  - docs/audit/2026-09/AUDIT_ADR_CANDIDATES.md
  - docs/audit/2026-09/review/AUDIT_REVIEW_FINDINGS.md
---

# INTERFACE_CONTRACTS — Vertragsvorschläge für INT-01/04, RES-03, INT-05, INT-07

> **Rolle dieses Dokuments.** Contract-First-Vorlage für die Schnittstellen-Arbeitseinheiten,
> die öffentliche Verträge berühren. Es beschreibt **Sollmodelle, messbare Akzeptanzkriterien,
> Deprecation-Fenster und ADR-Abhängigkeiten** — es ist **kein Implementierungsplan und kein
> Code**. Änderungen, die durch ADR **i** (Health-Vertrag) bzw. ADR **v** (Fehler-/Idempotenz-
> semantik) blockiert sind, stehen hier ausschließlich als **Vertragsvorschlag** und dürfen
> **nicht** als Sofort-Fix umgesetzt werden.
>
> **Kein Git, keine bestehenden Dateien geändert.** Diese Datei ist der einzige neue
> Artefakt dieses Auftrags.

---

## 0. Scope, Quellen und Grundregeln

**Vertragsgegenstand:**

| Vertrag | Arbeitseinheit | ADR-Abhängigkeit | Sofort umsetzbar? |
|---|---|---|---|
| Import-Ergebnismodell | INT-01 (ReqIF), INT-04 (CSV) | **ADR v** (blockiert) | nein |
| Health-/Readiness-Vertrag | RES-03 (+ RES-05, RES-07) | **ADR i** (blockiert) | nein |
| REST-Pagination & Envelope | INT-05 | — | ja, hinter Deprecation-Fenster |
| MCP-Fehlerkontrakt | INT-07 (+ INT-06) | — (spec-getrieben) | ja, hinter Deprecation-Fenster |

**Querschnitt.** Das REST-Fehler-Envelope (`rest_api/openapi.py:71-98`,
`COMMON_ERROR_RESPONSES` unbenutzt; `serializers.py:241-257` ohne `request_id`) ist die
gemeinsame Klammer um alle vier Verträge. Es wird hier nur soweit beschrieben, wie die
einzelnen Verträge es benötigen; die Vollausarbeitung bleibt **INT-06 / RES-07**.

**Grundregeln (verbindlich für alle Verträge):**

1. **Keine Breaking Change ohne Deprecation-Fenster** (mindestens 2 Minor-Releases **oder**
   90 Tage, whichever is longer) mit `Deprecation: true`- und `Sunset`-Header sowie
   Changelog-Eintrag.
2. **Additiv zuerst**: neue Felder/Envelope-Keys werden hinzugefügt, alte bleiben im Fenster
   erhalten.
3. **Maschinenlesbare Fehlerursache**: jede Fehlermeldung trägt einen stabilen
   `code` (SCREAMING_SNAKE), die Klartext-`message` ist lokalisiert.
4. **Keine Secrets/DSN in Antworten** (CWE-209); Details nur als statische Marker,
   Ursache ins Log.
5. **ADR-blockierte Punkte bleiben Vorschlag** — siehe §6.

---

## 1. Querschnitt: gemeinsames Fehlermodell (Referenz INT-06)

**REST (Soll):**

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "<lokalisiert>",
    "details": [ { "field": "title", "message": "…" } ],
    "request_id": "<uuid aus middleware.py:85>"
  }
}
```

- `code`, `message` sind Pflicht, `details` und `request_id` additiv (RES-07).
- Der `X-Request-ID`-Header existiert bereits (`middleware.py:85`); er wird **zusätzlich** in
  den Body gespiegelt. Das ist **additiv**, keine Breaking Change.
- Alle Responses deklarieren die Fehlerfälle über `COMMON_ERROR_RESPONSES` im OpenAPI-Schema.

**MCP (Soll):** JSON-RPC-2.0-Fehlerobjekt, siehe §5 — **nicht** das REST-Envelope.

---

## 2. Vertrag INT-01 / INT-04 — Import-Ergebnismodell

### 2.1 Ist-Zustand (belegt)

| Ort | Befund |
|---|---|
| `reqif_import_service.py:482-489` | `success=True` **hart** kodiert; Fehler nur in `needs/requirements/relations.errors` |
| `reqif_import_service.py:413-443` | pro-Objekt-Rettung zählt `skipped`/`errors`, bricht aber nicht auf `success` durch |
| `reqif_import_service.py:264-270` | `ReqifEntityReport` kennt `created/updated/skipped/errors` — kein `failed` |
| `import_service.py:300-314` | DB-Rollback liefert `success=False` mit **leerer** `errors`-Liste (Finding 079) |
| `import_service.py:662,695` | `Artifact.objects.create` ohne Dedupe (Finding 072) |
| `views.py:8018` | `decode("utf-8")` ⇒ BOM (`\ufeff`) landet im ersten Header-Feld (Finding 083) |
| `views.py:8060-8077` | CSV-Antwort 201/400 mit `success/imported_count/skipped_count/errors` |
| `views.py:8319` | ReqIF-Antwort **immer 200**, `success:true` |

### 2.2 Sollmodell (`ImportResultV2`)

Beide Importe liefern **dasselbe** Modell. `success` folgt **einer** Regel:
`success = (counts.failed == 0)`.

```json
{
  "success": false,
  "contract": "v2",
  "dry_run": false,
  "counts": { "succeeded": 12, "skipped": 3, "failed": 1, "total": 16 },
  "items": [
    {
      "row": 7,
      "identifier": "REQ-4711",
      "kind": "Requirement",
      "status": "failed",
      "cause": { "code": "PERSISTENCE_ERROR", "message": "<lokalisiert>" }
    }
  ],
  "warnings": ["Unrecognized column(s) ignored: Beschreibung"],
  "idempotent_replay": false,
  "request_id": "<uuid>"
}
```

**Statuswerte je Zeile/Objekt:** `succeeded | skipped | failed`.

**Ursachen-Codes (stabil, maschinenlesbar):**

| `cause.code` | Bedeutung | Status |
|---|---|---|
| `DUPLICATE` | fachliches Duplikat (Idempotenz-/Dedupe-Treffer) | `skipped` |
| `UNKNOWN_TYPE` | unbekannter SPEC-OBJECT-TYPE / entity_type | `skipped` |
| `MISSING_REQUIRED_FIELD` | Pflichtfeld leer | `failed` |
| `INVALID_VALUE` | Wert außerhalb des Wertebereichs, z. B. `_map_status` ohne gültigen Zustand | `failed` |
| `TYPE_MISMATCH` | falscher Typ (z. B. `term: 42`) | `failed` |
| `QUOTING_ERROR` | RFC-4180-Verstoß, Restzeile | `failed` |
| `PERSISTENCE_ERROR` | DB-/Integritätsfehler je Objekt | `failed` |
| `BOM_DETECTED` | BOM entfernt (Hinweis) | Warning |
| `UNKNOWN_COLUMN` | Spalte ignoriert | Warning |

**HTTP-Abbildung (Soll):**

| Situation | Status |
|---|---|
| `failed == 0` (skipped erlaubt) | 201 (CSV) / 200 (ReqIF, dry_run) |
| `0 < failed < total` (Teilerfolg) | **207 Multi-Status** |
| `failed == total` bzw. `failed > 0` ohne Erfolg | **422 Unprocessable Entity** |
| Request-Ebene: leere Datei, falsches Encoding, unbekannter `entity_type`, Größenlimit | 400 (unverändert) |

### 2.3 Idempotenz / Dedupe (offen bis ADR v)

- **`Idempotency-Key`-Header** (optional, opak, ≤ 255 Zeichen): Erste Anfrage speichert
  `key → Result-Fingerprint` für ein definiertes Fenster; ein Replay liefert **dasselbe**
  Ergebnis mit `"idempotent_replay": true` und demselben HTTP-Status.
- **Fachliche Dedupe** (wirkt auch ohne Key): natürlicher Schlüssel pro Entität
  (ReqIF: `reqif_identifier`; CSV: entity-spezifischer Natural Key). Treffer ⇒ `skipped`
  mit `DUPLICATE`. Konfigurierbar (`skip` Default | `error`).
- **BOM**: Einlesen mit `utf-8-sig`; das ist ein **Fix**, kein Vertragsbruch.
- **Rollback**: bei `status="rollback"` ist `counts.failed > 0` **und** `items` enthält
  mindestens einen `PERSISTENCE_ERROR` — `errors`/`items` darf nie leer sein (Finding 079).

### 2.4 Kompatibilitäts-/Deprecation-Fenster & was bricht

| Phase | Inhalt | Bricht |
|---|---|---|
| **1 — additiv** | `contract`, `counts`, `items`, `idempotent_replay`, `request_id` ergänzt; Legacy-Keys `imported_count`, `skipped_count`, `errors`, `status`, `needs/requirements/relations` bleiben; `success` noch **alt** (ReqIF weiter `true`). `Deprecation`/`Sunset`-Header. | nichts |
| **2 — Semantik** | `success = (failed == 0)`; Teilerfolg ⇒ 207, Totalfehler ⇒ 422. | Clients, die `success === true` auch bei `failed > 0` erwarten (genau der Defekt) |
| **3 — Cleanup** | Legacy-Keys entfernt. | Clients, die bis dahin nicht migriert haben |

**Was am Bestand bricht (bewusst):**

- ReqIF: `success` wechselt von `true` auf `false` bei Objektfehlern — das ist der
  Kern von Finding 071.
- CSV: Statuscode wechselt bei Teilerfolg von 201/400 auf 207/422.
- Wer die flache `errors`-Liste parst, muss auf `items[].cause` migrieren (Legacy bleibt
  bis Phase 3 erhalten).

### 2.5 Akzeptanzkriterien (messbar)

- `success == (counts.failed == 0)` gilt für **beide** Importe (Unit + Contract).
- ReqIF mit genau einem fehlerhaften Objekt: Antwort `success=false`, `counts.failed==1`,
  die übrigen Objekte sind persistiert (kein Gesamtabbruch).
- Zwei identische ReqIF-/CSV-Uploads mit gleichem `Idempotency-Key`: zweiter Aufruf
  `idempotent_replay=true`, keine neuen Zeilen (DB-Zähler identisch).
- Zweifacher CSV-Import **ohne** Key erzeugt keine Duplikate (Dedupe).
- BOM-Fixture importiert den Header korrekt; keine `title is missing or empty`-Meldung.
- `items` enthält bei `failed>0` mindestens einen Eintrag; bei Rollback nie leer.

### 2.6 Teststrategie

| Ebene | Test |
|---|---|
| Unit | `ReqifImportResult.to_dict`/`ImportResult`-Mapping, `cause`-Codes, `success`-Regel |
| Integration | ReqIF-Import mit 1 Fehlerobjekt (Bestand bleibt); CSV-Round-Trip; DB-Fehler → `items` nicht leer |
| Contract | Response-Schema gegen OpenAPI (INT-06); Statusmatrix 201/207/422 |
| E2E | Upload im Test-Workspace (Live-Nachtest, im Plan gefordert) mit Redis/DB up |

### 2.7 Rollback

- Feature-Flag `IMPORT_CONTRACT_V2` (Default in Phase 1 `off`); Abschalten stellt Phase-1-
  Verhalten wieder her. Kein Datenverlust, da Importe atomar sind. `Idempotency-Key`-Replay
  ist additiv und kann separat abgeschaltet werden.

### 2.8 ADR-Abhängigkeit

**ADR v blockiert** Semantikwechsel (`success`), HTTP-Status (207/422) und die
Idempotenz-Wahl (`Idempotency-Key` vs. fachliche Dedupe vs. beides). Bis zur Entscheidung
**nur §2.2/2.3 als Vorschlag**, keine Umsetzung. BOM-Fix (`utf-8-sig`) ist unabhängig und
nicht ADR-blockiert.

---

## 3. Vertrag RES-03 — Health / Readiness (Entscheidungsvorlage ADR i)

### 3.1 Ist-Zustand (belegt)

- Nur **ein** Endpunkt `path("health/", HealthView)` (`urls.py:28`); der Docstring
  (`health.py:4`) verspricht `/health/ready` + `/health/live` — **beide existieren nicht**
  (Finding 275).
- `HealthView.get` (`health.py:118-315`) prüft: `database`, `memory_backend`,
  `embedding_dimensions` (Warning/200), `llm_provider_env` (Warning/200),
  `csrf_cookie_secure_matches_auth` (Warning/200), Workflow-Definitionen.
  **Nicht geprüft:** Cache/Redis, Celery-Worker, Beat, Outbox (Finding 286; 5/10).
- `degraded` ⇒ **503** ist bereits implementiert (`health.py:134-135,160-161`) — die
  Audit-Behauptung „degraded → 200" ist widerlegt (`AUDIT_REVIEW_FINDINGS.md` WP-1c).
- Die **vollständige** Probe existiert admin-geschützt in `admin_ops/health_rest.py:96-198`
  (`_check_redis`, `_check_celery_worker`, `_check_celery_beat`, `_check_mcp_server`).
- `deploy/docker-compose.yml:642` prüft `curl -f /health/`.

### 3.2 Sollmodell — Endpunkte & Semantik

| Endpunkt | Zweck | Auth | Antwort |
|---|---|---|---|
| `GET /health/live` | **Liveness**: Prozess kann HTTP bedienen | nein | **immer 200** `{"status":"ok","checks":{}}`, keine Abhängigkeitsprobe |
| `GET /health/ready` | **Readiness**: App ist benutzbar | nein (statische Marker) | 200 nur wenn **alle Pflicht-Abhängigkeiten** gesund; sonst **503** |
| `GET /health/` | **Deprecation-Alias** | nein | Semantik gemäß ADR i (Vorschlag: Alias auf `ready`) |

**Pflicht-Abhängigkeiten für `/health/ready`:** `database`, `cache` (Redis),
`celery_worker`, `celery_beat`. Optional/beratend: `outbox`, `memory_backend`,
`llm_provider_env`, `embedding_dimensions`.

### 3.3 Body-Schema (verbindlich)

```json
{
  "status": "ok | degraded",
  "checks": {
    "database":      { "status": "ok",   "detail": "connected" },
    "cache":         { "status": "down", "detail": "dependency_down" },
    "celery_worker": { "status": "ok",   "detail": "1 worker(s) responding" },
    "celery_beat":   { "status": "unknown", "detail": "no heartbeat recorded" }
  },
  "dependencies": [
    { "name": "cache",       "status": "down",    "detail": "dependency_down" },
    { "name": "celery_beat", "status": "unknown", "detail": "no heartbeat recorded" }
  ],
  "warnings": ["embedding columns do not match the configured provider width"],
  "request_id": "<uuid>"
}
```

**Regeln:**

1. `status` ist **`ok`** genau dann, wenn jeder Eintrag in `checks` den Wert `ok` hat.
2. Wenn `status == "degraded"`, **MUSS** `dependencies` nicht leer sein und **jede** nicht-`ok`-
   Abhängigkeit enthalten (Name, Status, statischer Detail-Marker). Das ist das
   verpflichtende Element aus ADR-Kandidat #3, Option B.
3. `detail` enthält **niemals** DSN/Host/Port/Secret (CWE-209); reale Ursache ins Log
   (`logger.warning`).
4. `request_id` ist additiv (RES-07).

### 3.4 Statuscodes bei Ausfall

| Ausfall | `/health/live` | `/health/ready` |
|---|---|---|
| Redis/Cache | 200 | **503** (`cache=down`) |
| Celery-Worker | 200 | **503** (`celery_worker=down`) |
| Beat (Heartbeat fehlt/stale) | 200 | **503** (`celery_beat=unknown|down`) |
| Datenbank | 200 | **503** (`database=down`) |
| Embedding-Dimension / LLM-Env fehlt | 200 | 200 + `warnings` (bestehendes Verhalten, beibehalten) |
| CSRF-Cookie-Mismatch | 200 | 200 + `warnings` (beibehalten) |
| Outbox-Rückstau | 200 | ADR-Entscheidung: `warning` (200) oder `degraded` (503) |

### 3.5 Entscheidungsvorlage ADR i — Optionen

| Option | Beschreibung | Dafür | Dagegen |
|---|---|---|---|
| **A — Strikt fail-closed** | jede benötigte Abhängigkeit muss gesund sein, sonst 503 | klassische, gut verstandene Semantik; Gates können auf den Statuscode vertrauen | Redis-Ausfall nimmt die **gesamte** Oberfläche aus dem LB, auch redis-freie Teile |
| **B — Degraded-200 + Pflichtliste** | `/health/` bleibt 200, `status=degraded` + Pflicht-Liste; Gates werten die Liste aus | keine unnötige Verfügbarkeitsreduktion | genau die Lücke: ein nur-statuscode-lesendes Gate bleibt **falsch-grün**; braucht zwingend Gegenauswertung |
| **C — Zwei Endpunkte, harte Trennung** | `/health/live` (Prozess, billig), `/health/ready` (alle Abhängigkeiten, fail-closed) | trennt „Prozess lebt" von „App benutzbar" — die fehlende Unterscheidung; vollständige Probe existiert bereits in `health_rest.py` | zwei Konventionen ⇒ Doku-/Aufmerksamkeitsaufwand |

### 3.6 Akzeptanzkriterien (messbar)

- Bei gestopptem Redis liefert `/health/ready` **503** und `dependencies` enthält
  `{"name":"cache","status":"down"}`; `/health/live` liefert weiter **200**.
- `status == "degraded"` ⇒ `dependencies` ist nicht leer (Contract-Test über alle
  Abhängigkeits-Kombinationen).
- Compose-Health des Backends wird bei Redis-Stop **rot** (benötigt konsistente
  Alias-Entscheidung für `/health/`).
- Kein Response enthält DSN/Host/Secret (Regex-Scan im Test).
- Beat-Stale (Heartbeat älter als `HEARTBEAT_STALE_AFTER_SECONDS`) ⇒ `celery_beat` nicht `ok`.

### 3.7 Teststrategie

| Ebene | Test |
|---|---|
| Unit | Health-View je Abhängigkeit (gemockt), `status`/`dependencies`-Konsistenzregel |
| Integration | echte Probe gegen Postgres/Redis/Worker/Beat; Bounded-Timeout (RES-01) |
| Contract | Body-Schema + Statusmatrix gegen OpenAPI (INT-06) |
| E2E | Redis-Stop-Szenario mit `curl --max-time`, Live-Nachtest (Plan fordert 031) |

### 3.8 Rollback

Feature-Flag `HEALTH_STRICT_READINESS` (Default gemäß ADR i). Abschalten lässt
`/health/ready` in den degradierten 200-Modus (Option B) zurückfallen, ohne die neuen
Endpunkte zu entfernen. Kein Datenrisiko.

### 3.9 ADR-Abhängigkeit

**ADR i blockiert** die Endpunkt-Topologie (ein vs. zwei Endpunkte) sowie fail-closed vs.
degraded-200. RES-03, RES-05 (Beat-Heartbeat-Auswertung) und RES-07 (Gates) hängen daran.
Bis zur Entscheidung **nur §3.2–3.4 als Vorschlag**.

---

## 4. Vertrag INT-05 — REST-Pagination

### 4.1 Ist-Zustand (belegt)

- Ungepagte Listen (nackte Arrays): `api_key_views.py:147-158` (`GET /api/v1/api-keys/`),
  `user_management_views.py:104-126` (`GET …/users/`),
  `link_type_views.py:56-57` (`GET /api/v1/link-type-defaults/`),
  `link_type_views.py:93-97` (`GET …/workspaces/<uuid>/link-type-definitions/`).
- `500` statt `404`: bei `views.py:3111` (trace-links) und `views.py:8369` (glossary) läuft
  `paginate_queryset` **innerhalb** des `try/except Exception` ⇒ DRFs `NotFound` wird zu 500.
  `WorkspaceViewSet.list` (`views.py:5335-5337`) macht es richtig: Pagination außerhalb des `try`.
- Vorhandenes Envelope: `StandardPagination` (`serializers.py:328-476`) liefert
  `{count, next, previous, page_size, max_page_size, results}`.

### 4.2 Sollverhalten `page`

DRF-Standard (`PageNumberPagination`) wirft bei ungültigem `page` `NotFound` (404). Soll:
dieser Fehler propagiert als **404** mit JSON-Envelope (inkl. `request_id`).

| Eingabe | Soll-Status | Begründung |
|---|---|---|
| `page` fehlt | 200, Seite 1 | Default |
| `page=1` | 200 | gültig |
| `page=0` / `page=-1` (out of range / < 1) | **404** | `EmptyPage` → `NotFound`; konsistent mit `WorkspaceViewSet` |
| `page=abc` (nicht numerisch) | **404** | `PageNotAnInteger` → `NotFound`; Alternative 400 verworfen, weil der Rest der API 404 nutzt |
| `page=99999999` (out of range) | **404** | `EmptyPage` |
| `page_size>100` | 200, geklemmt; `page_size` echo der angewandten Größe | bestehendes #571-Verhalten |
| `page_size=0/-1/abc` | 200, Default 25 | DRF-Fallback |

**Mechanik:** `paginate_queryset`/`_paginate` **außerhalb** des `try/except Exception` in
`views.py:3111` und `views.py:8369` (Muster `views.py:5335-5337`). Kein `try/except`
schluckt mehr `NotFound`.

### 4.3 Pagination-Envelope für die 4 ungepagten Listen

Alle vier liefern künftig:

```json
{
  "count": 137, "next": "…&page=2", "previous": null,
  "page_size": 25, "max_page_size": 100,
  "results": [ … ]
}
```

- `StandardPagination` (Default 25, max 100), `page`/`page_size` mit OpenAPI-Doku.
- Bei aktivem `preset`-Gate bleibt die Array-Form unverändert, wenn Pagination explizit
  deaktiviert ist (`paginate_queryset → None`) — additive Regel bleibt erhalten.

### 4.4 Breaking-Change-Bewertung & Deprecation-Fenster

- **Array → Objekt** ist **breaking** für Clients, die `response[0]`/`len(response)` nutzen.
- Der **500→404**-Wechsel ist ein **Bugfix** (kein Client darf auf 500 bauen); trotzdem
  Changelog-Pflicht.

| Phase | Inhalt |
|---|---|
| **1 — opt-in (additiv)** | `page`/`page_size` vorhanden ⇒ Envelope; sonst Array wie bisher + `Deprecation: true`, `Sunset: <Datum+2 Minor>` |
| **2 — Default-Flip** | ohne Parameter ⇒ Envelope; Array nur noch mit `?legacy_array=1` (ein Minor) |
| **3 — Cleanup** | `legacy_array` entfällt |

### 4.5 Akzeptanzkriterien (messbar)

- `?page=0`, `?page=abc`, `?page=99999999` ⇒ **404** (JSON-Envelope, kein HTML) für
  `/api/v1/tracelinks/` und `/api/v1/glossary/`.
- Die 4 ungepagten Listen liefern nach dem Flip `count`, `next`, `previous`, `page_size`,
  `max_page_size`, `results`.
- In Phase 1 bleibt die Array-Antwort ohne Parameter byte-kompatibel (Golden-Test).
- `Sunset`/`Deprecation`-Header im Fenster vorhanden (Header-Test).

### 4.6 Teststrategie

| Ebene | Test |
|---|---|
| Unit | Paginator-Verhalten `page=0/abc/out-of-range` → 404 |
| Integration | 4 Listen-Endpunkte mit/ohne `page`, Envelope-Shape; trace-links/glossary-Status |
| Contract | Envelope-Schema in OpenAPI; Header-Test |
| E2E | Playwright/HTTP-Smoke: Liste lädt, Pagination navigiert |

### 4.7 Rollback

Reine Lese-Vertragsänderung, kein Datenrisiko. Flag `PAGINATION_ENVELOPE` steuert
Default-Flip; Zurücksetzen stellt Phase 1 (opt-in) wieder her. `legacy_array=1` bleibt im
Fenster verfügbar.

### 4.8 ADR-Abhängigkeit

**Keine ADR blockiert** INT-05. Umsetzung nach W2 möglich, sobald das Deprecation-Fenster
dokumentiert ist. Der 500→404-Fix ist sofort zulässig.

---

## 5. Vertrag INT-07 — MCP-Fehlerkontrakt (JSON-RPC 2.0)

### 5.1 Ist-Zustand (belegt)

- Zwei Envelopes: `mcp_server/views.py:291-325` nutzt **String**-`error_code` (kein `code`),
  `protocol_handler.py:264-268` nutzt **int** `code`. (Finding 032/033.)
- `clean_params = {k: v for k, v in params.items() …}` (`protocol_handler.py:536`) liegt
  **außerhalb** des `try`; nicht-dict `params` ⇒ `AttributeError` ⇒ HTML/500 (33).
- Unbekannte String-Codes fallen in `ERROR_CODE_MAP.get(code, -32603)` ⇒
  **`-32603 internal error` bei Validierung** (36/45/46).
- Tool-Handler `glossary_service.py:156-167` ohne Längengrenze; `term:42` ⇒ `AttributeError`
  ⇒ `INTERNAL_ERROR` (46/47).

### 5.2 Sollmodell — Wire-Format

Alle Fehler sind **JSON-RPC-2.0-Fehlerframes** mit **integer** `code`:

```json
{
  "jsonrpc": "2.0",
  "id": 17,
  "error": {
    "code": -32602,
    "message": "Invalid params: 'params' must be an object.",
    "data": { "error_code": "VALIDATION_ERROR", "details": { "field": "params" } }
  }
}
```

- `error.code` **immer int** (Pflicht).
- `error.data.error_code` trägt den bisherigen String-Code (maschinenlesbar).
- `error.data.details` optional. Das bisherige `error.details` bleibt als **deprecated
  Alias** im Fenster erhalten.

### 5.3 Code-Mapping (nur Spec-konforme Bereiche)

| Situation | `error_code` | `code` |
|---|---|---|
| unparsbarer JSON-Body | `PARSE_ERROR` | -32700 |
| defekter Request-Frame | `INVALID_REQUEST` | -32600 |
| unbekannte Methode/Tool | `UNKNOWN_TOOL` | -32601 |
| **ungültige Parameter** (nicht-dict `params`, nicht-dict `arguments`, fehlende Pflichtfelder, Typfehler, unbekannter Toolset/Filter) | `VALIDATION_ERROR` | **-32602** |
| echter Serverdefekt beim Dispatch | `INTERNAL_ERROR` | -32603 |
| Auth / Rechte / Feature / LLM / NotFound / Session / LastAdmin / RateLimit / Conflict | jeweiliger Code | -32000 … -32011 |

**Regeln:**

1. Validierungsfehler werden **nie** auf `-32603` abgebildet.
2. `params` und `tools/call.arguments` werden **vor** jedem `.items()`/Attributzugriff
   typgeprüft. Nicht-dict ⇒ `-32602`, nicht 500.
3. `id` wird gespiegelt; bei Parse-Fehlern `id: null`.
4. **Abgrenzung protocol-vs-tool-execution (MCP-Spec):** Fehler aus einem laufenden Tool
   (`tools/call`) bleiben ein **erfolgreiches** JSON-RPC-`result` mit `isError: true` und
   String-`error_code` (`_PROTOCOL_ERROR_CODES`, `protocol_handler.py:631`). Nur
   Protocol-Codes (`_PROTOCOL_ERROR_CODES`) werden als JSON-RPC-Fehlerframe gesendet.
5. Batch-Requests bleiben abgelehnt (`-32600`), Notification ohne Antwort (`202`).
6. Alle Fehlerframes sind garantiert JSON (kein HTML), auch bei interner
   Encoding-/Dispatch-Ausnahme (`views.py:352-379` vereinheitlichen).

### 5.4 Kein JSON-RPC-Spec-Bruch

- Es werden **nur reservierte Standard-Codes** (−32700…−32603) und der
  Server-definierte Bereich (−32000…−32099) genutzt.
- `data` bleibt optional; `isError`-Semantik und Notification-Regel bleiben.
- Die Vereinheitlichung des String-Envelopes hin zu `code`+`data.error_code` ist eine
  **Korrektur** auf Spec-Form, keine Protokollerweiterung.

### 5.5 Kompatibilität & Deprecation-Fenster

| Phase | Inhalt |
|---|---|
| **1 — additiv** | int `code` zusätzlich zum bisherigen String-`error_code`; `data.error_code` zusätzlich zu `error.details` |
| **2 — Default** | nur noch spec-konformes Frame (`code`, `data.error_code`); String-Alias entfernt nach 2 Minor |
| **3 — Cleanup** | Aliase entfernt |

- **Was bricht:** Clients, die `error.error_code` auf oberster Ebene bzw. `-32603` für
  Validierungsfehler matchen. Genau das ist Finding 032/036; Korrektur im Fenster.
- Nicht-dict `params` liefert statt 500 nun `-32602` — Bugfix, dennoch Changelog.

### 5.6 Akzeptanzkriterien (messbar)

- `params: "x"` bzw. `params: []` ⇒ HTTP 200/400 mit JSON-RPC `code == -32602`,
  **nicht** 500 und nicht `-32603`.
- `tools/call` mit `arguments: 42` ⇒ `-32602`.
- `glossary.term: 42` ⇒ definierter Validierungsfehler (kein `INTERNAL_ERROR`).
- Tool-Ausführungsfehler ⇒ `result.isError == true` **mit** String-`error_code`.
- Jede Fehlerantwort enthält `jsonrpc:"2.0"`, int `code`, gespiegelte `id`.
- Der Manifest-Drift-Test läuft **ohne** `django_db` (`test_tool_manifest_drift.py:83`).

### 5.7 Teststrategie

| Ebene | Test |
|---|---|
| Unit | `ErrorFormatter.format_error` für alle Codes inkl. Fallback |
| Integration | `ProtocolHandler` mit nicht-dict `params`/`arguments`, Tool-Attributfehler |
| Contract | Fehlerframe gegen JSON-RPC-2.0-Schema (int `code`, `data.error_code`) |
| E2E | MCP-HTTP/SSE: Validierungsfehler liefert 400/JSON, kein HTML |

### 5.8 Rollback

Flag `MCP_ERROR_SPEC_V2` steuert String-Alias vs. Spec-Form. Umschalten stellt Phase 1
wieder her; keine persistierenden Effekte.

### 5.9 ADR-Abhängigkeit

**Keine ADR blockiert** INT-07; die Regeln folgen direkt der JSON-RPC-2.0-Spezifikation.
Koordination mit **INT-06** (OpenAPI-Fehler-Response) und **RES-07** (`request_id`) ist
erforderlich, aber keine ADR-Entscheidung.

---

## 6. ADR-blockierte Änderungen — Markierung

| Änderung | Blockiert durch | Status in diesem Dokument |
|---|---|---|
| `success = (failed == 0)` für ReqIF/CSV | **ADR v** | Vorschlag, **kein** Sofort-Fix |
| HTTP 207/422 bei Teil-/Totalfehler | **ADR v** | Vorschlag |
| `Idempotency-Key` vs. fachliche Dedupe | **ADR v** | Vorschlag (Optionen offen) |
| `/health/live` vs. `/health/ready` Topologie | **ADR i** | Vorschlag |
| fail-closed Readiness vs. degraded-200 | **ADR i** | Vorschlag |
| `/health/` Alias-Semantik | **ADR i** | Vorschlag |
| BOM-Fix (`utf-8-sig`), `errors`-nie-leer, `request_id` | keine | **umsetzbar** (INT-04/INT-06) |
| `page=0/abc/out-of-range` ⇒ 404 | keine | **umsetzbar** (INT-05) |
| 4 Listen paginieren (mit Fenster) | keine | **umsetzbar** (INT-05) |
| MCP-Validierung ⇒ `-32602`, kein `-32603` | keine | **umsetzbar** (INT-07) |
| `initialize.serverInfo.version` / Tool-Zahl 219 | keine (INT/DOC) | außerhalb dieses Vertrags |

---

## 7. Empfehlung zu ADR i und ADR v

### 7.1 ADR i — Health-Vertrag

**Empfehlung: Option C (zwei Endpunkte) kombiniert mit fail-closed Readiness (A-Semantik
für `/health/ready`) und verpflichtender Ausfall-Liste.**

Begründung:

- **C löst die eigentliche Lücke** — es gibt heute keinen trennbaren Liveness-Punkt; der
  Docstring verspricht ihn bereits (`health.py:4`). `/health/live` (billig, kein DB/Redis)
  und `/health/ready` (vollständig) sind die einzige Konstruktion, die „Prozess lebt" von
  „App benutzbar" unterscheidet.
- **A für `/health/ready` schließt das falsch-grüne Gate.** Option B verschiebt die Lücke
  nur in die Gates: jedes Gate, das nur den Statuscode liest, bleibt grün. Die
  Pflicht-Liste allein genügt nicht, sie braucht eine **Gegenauswertung** — die ist teurer
  und fehleranfälliger als 503.
- **Die vollständige Probe existiert bereits** (`admin_ops/health_rest.py:96-198`); C
  reuse-t sie, statt Neues zu bauen. Das hält den Aufwand (RES-03, M–L) beherrschbar.
- **Risiko** (Redis-Ausfall nimmt die Oberfläche aus dem LB) wird über ein Feature-Flag
  `HEALTH_STRICT_READINESS` und eine konfigurierbare Abhängigkeitsliste abgefedert; der
  Betreiber entscheidet pro Umgebung.
- `/health/` wird **Deprecation-Alias auf `/health/ready`**, damit die bestehende
  Compose-Probe (`docker-compose.yml:642`) bei Redis-Stop rot wird (RES-03-Akzeptanz).

Falls der User einen **einzigen** Endpunkt bevorzugt: dann Option A (nicht B), damit der
Statuscode allein verlässlich ist.

### 7.2 ADR v — Fehler-/Erfolgssemantik & Idempotenz

**Empfehlung: Option A für die Importpfade (ein Ergebnismodell + `Idempotency-Key`),
kombiniert mit der MCP-Regel aus Option B (MCP bleibt strikt JSON-RPC 2.0).**

Begründung:

- **Ein Importmodell für ReqIF und CSV** beseitigt die heute divergierenden Antworten und
  generalisiert den P0-Kern von Finding 071 (`success:true` trotz Fehler). Der Aufrufer
  kann Erfolg von stillem Scheitern unterscheiden — genau Muster 2 des Audits.
- **`Idempotency-Key` ist für Retry-Sicherheit nötig** (ReqIF/CSV sind mehrfach auslösbar);
  zusätzlich sichert fachliche Dedupe den Fall ohne Key ab (Finding 072), konfigurierbar
  `skip`/`error`. Das ist robuster als Option C (nur verschärfte Bedingung), das keine
  programmatische Teil-Erfolgs-Auswertung liefert.
- **MCP wird bewusst ausgenommen (B):** JSON-RPC 2.0 ist ein öffentlicher Standard; ein
  Importmodell dort wäre ein Spec-Bruch. Stattdessen spec-konforme Codes (`-32602` etc.).
- Der Preis ist ein **Breaking Change** für `success:true`-Prüfer; deshalb das
  dreiphasige Deprecation-Fenster aus §2.4 (additiv → Semantik → Cleanup).

Damit sind die in `IMPLEMENTATION_PLAN.md` §5 genannten Pilot-Einheiten INT-01/04/06 sauber
an **eine** Entscheidung gebunden.

---

## 8. Zusammenfassung je Vertrag

| Vertrag | Sollmodell (Kurz) | Messbares Kernkriterium | Deprecation-Fenster | ADR |
|---|---|---|---|---|
| INT-01/04 | `succeeded/skipped/failed` + `cause`, `success⇔failed==0`, `Idempotency-Key` | ReqIF-1-Fehler ⇒ `success=false`, Rest persistiert; Replay keine Duplikate | 2 Minor / 90 Tage, 3-phasig | **v (blockiert)** |
| RES-03 | `/health/live` (200) + `/health/ready` (503), Pflicht-Ausfall-Liste | Redis-Stop ⇒ ready 503 + `dependencies[cache]`; live 200 | Flag `HEALTH_STRICT_READINESS` | **i (blockiert)** |
| INT-05 | Envelope `{count,next,…,results}`; `page<1/abc/out-of-range` ⇒ 404 | 3 ungültige `page`-Werte ⇒ 404; 4 Listen mit `count`/`next` | opt-in → Default-Flip → Cleanup | — |
| INT-07 | JSON-RPC `code` int + `data.error_code`; Validierung ⇒ -32602 | nicht-dict `params` ⇒ -32602, nie 500/-32603 | 2 Minor, additiv zuerst | — |

*Erstellt durch `api-specialist` am 2026-10-01. Contract-Vorschlag, kein Produktcode,
keine Migration, keine Git-Mutation. ADR-blockierte Punkte (§6) sind nicht umsetzbar,
solange ADR i/v nicht entschieden sind.*
