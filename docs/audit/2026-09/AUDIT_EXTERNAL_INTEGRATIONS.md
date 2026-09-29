---
type: REVIEW
scope: wp-1a-mcp-server
status: final
date: 2026-09-29
author_agent: senior-developer
---

# System-Audit 2026-09 — External Integrations

Dieses Dokument sammelt die Workpackage-Abschnitte der externen Integrationen.
Jeder Agent schreibt ausschließlich seinen eigenen Abschnitt; die
Finding-IDs `AUD-2026-09-NNN` sind global fortlaufend und werden nicht
überschrieben.

| Workpackage | Agent | Abschnitt |
|---|---|---|
| WP-1a | senior-developer | [MCP-Server](#wp-1a--mcp-server) |
| WP-1b | senior-developer | _folgt_ |

---

## WP-1a — MCP-Server

**Scope:** `backend/mcp_server/` (Views, ProtocolHandler, ToolRegistry,
Tool-Gruppen, Throttling, SSE), live gegen `http://localhost:8001`.
**Methode:** 82 Roh-Request/Response-Paare gegen die laufende Instanz,
39-Fall-Validierungsmatrix, 65-Fall-Tenant-Isolationsmatrix gegen einen
**echten** zweiten Tenant, 12-Mutationstest des Manifest-Guards,
Redis-Ausfall-Simulation mit Wiederherstellung.
**Evidenz:** [`AUDIT_EVIDENCE/wp1a-mcp-*.md|json`](AUDIT_EVIDENCE/) —
siehe [Index](AUDIT_EVIDENCE/wp1a-mcp-evidence-index.md).

### Ampel: **GELB-ORANGE**

| Prüfpunkt | Ergebnis |
|---|---|
| Tenant-Isolation (65 Fälle, echter 2. Tenant) | 🟢 **sauber** — 0 Leaks, 0 5xx |
| Manifest-Drift-Guard (12 Mutationen) | 🟢 **wirksam** — 12/12 |
| Tool-Eingabevalidierung (39 Fälle) | 🟡 0 Stacktrace-Leaks, 0 5xx, aber 3× `-32603` statt `-32602` |
| JSON-RPC 2.0 (82 Fälle) | 🟡 9 Abweichungen von der Spezifikation |
| Auth / beide Pfade | 🟡 identisch, aber 2 Key-Metadaten-Defekte |
| Transports | 🟡 HTTP + SSE real, **stdio nicht geroutet** (Doku behauptet es) |
| Graceful Degradation | 🔴 **Ausfall** — Redis down ⇒ MCP-Oberfläche hängt unbegrenzt |
| Health-Gate | 🔴 meldet „ok" während die App unbenutzbar ist |

### 1. JSON-RPC 2.0 Konformität (live)

Standard-Fehlercodes sind vorhanden und werden benutzt: `-32700`
(`protocol_handler.py:146`), `-32600` (`:147`), `-32601` (`:148`), `-32602`
(`:149`), `-32603` (`:150`). `ping` **existiert** (`protocol_handler.py:492`) —
es ist kein 404-Fall. Die neun Abweichungen:

| Fall | Erwartet | Ist | Beleg |
|---|---|---|---|
| Top-Level JSON `"hello"` / `42` / `true` | `-32600` | **HTTP 500** `INTERNAL_ERROR` | `protocol_handler.py:469` — `frame.get(...)` auf einem `str`/`int`/`bool` wirft `AttributeError`; `views.py:311` fängt es als generischen 500 |
| Top-Level `null` | `-32600` | **`-32700`** | `protocol_handler.py:469` — `frame is None` wird als Parse-Error fehlklassifiziert |
| `params` = `str`/`list`/`int` | `-32600`/`-32602` | **HTTP 500** | `protocol_handler.py:536` — `{k: v for k, v in params.items()}` liegt **außerhalb** jedes `try` |
| `tools/call` `arguments: null/str/list` | `-32602` | **`-32603` „An internal server error occurred."** | `protocol_handler.py:577` — `.get("arguments", {})` liefert `None`, `dispatch_request` wirft |
| `tools/call` `name: 123` | `-32602` | **`-32603`** | `protocol_handler.py:572` — Router ruft `.split(".")` auf einem `int` |
| `notifications/cancelled` (ohne `id`) | keine Antwort (202) | **`-32600`** | `protocol_handler.py:239` — nur `notifications/initialized` ist von der `id`-Pflicht ausgenommen, während `:515` generisch auf `notifications/` prüft |
| `notifications/initialized` **mit** `id` | Antwort (ist ein Request) | **202, leer** | `protocol_handler.py:515` — der Client wartet vergeblich auf seine Response |
| `id: true` / `[1,2]` / `{...}` | `-32600` | **200, echoed** | `protocol_handler.py:226-241` — der Validator prüft den `id`-Typ nicht |
| Batch (Array) | optional | **400 `INVALID_REQUEST`** mit *String*-`error_code` statt numerischem `code` | `views.py:291-304` — bewusste Entscheidung, aber andere Fehler-Hülle als der Rest desselben Endpunkts |

**Positiv:** `id: null` wird korrekt nach `string`/`number`/`null` akzeptiert
(Spec erlaubt null, wenn auch discouraged); `null`, leere und boolesche `method`
werden sauber mit `-32600` abgelehnt; `initialize` antwortet vollständig
(`protocolVersion 2024-11-05`, `capabilities.tools`, `serverInfo`); ein Frame
ohne `id` auf einer Nicht-Notification-Methode wird nicht stillschweigend als
Notification akzeptiert.

### 2. Transports

| Transport | Route | Live |
|---|---|---|
| HTTP | `POST /mcp/`, `POST /api/v1/mcp/` | ✅ 200, JSON-RPC |
| SSE | `GET /mcp/sse/`, `/mcp/sse`, `/api/v1/mcp/sse/` | ✅ 200 `text/event-stream`; `endpoint`-Event und Keepalive-Frames kommen an (Roh-Bytes in `wp1a-mcp-jsonrpc-and-transports.json`); Auth-Pflicht 401 ohne/mit ungültigem Key |
| SSE-Nachrichten | `POST /mcp/messages/?session_id=…` | ✅ 202; unbekannte Session ⇒ 401 `SESSION_EXPIRED` mit Reconnect-Hinweis; ohne `session_id` ⇒ 400 `INVALID_REQUEST` |
| **stdio** | **keine Route** | ❌ `GET /mcp/stdio/` und `/mcp/stdio` ⇒ **404**; `/api/v1/mcp/stdio/` ⇒ DRF-JSON-404 |

Der Code ist hier **korrekt und ehrlich**: `StdioTransportAdapter` existiert
(`protocol_handler.py:344`), wird aber nur von `TransportAdapter.extract_api_key`
für den Body-Key-Kanal unterschieden (`:338-341`), und
`views.py:425-430` sagt explizit, stdio sei absichtlich nicht im
Discovery-Array, weil es keine Route hat. **Der Drift liegt in der Doku:**
`README.md:482`, `:1060`, `:1072`, `:1163`, `:1182`, `:1291` behaupten stdio
als nutzbaren Transport bzw. nennen `http://localhost:8000/mcp/stdio/` als
Konfigurations-URL. Das ist **CR-21**, bestätigt.

Zusätzlich: `GET /mcp/` mit `Accept: text/event-stream` ⇒ **405** (bewusst,
`views.py:395-396`) — die StreamableHTTP-Reconnect-Loop aus dem
SYSTEMAUDIT-2026-09-02-Befund ist damit tatsächlich behoben.

### 3. Tool-Count-Drift — **die offene Frage ist beantwortet**

**Ergebnis: 219 Tools / 35 Präfixe sind die Wahrheit. `tools/list` liefert 80
weil der benutzte Key ein nicht anerkanntes Scope-Tier hat. Das ist kein
Registrierungsfehler.**

Beweis mit demselben User, demselben Tenant, derselben Instanz:

| Key-Scope | `tools/list` | Präfixe |
|---|---|---|
| `readwrite` (der Key aus `stack-seeds.md`) | **80** | 34 |
| `admin` (temporär für dieses Audit) | **219** | 35 |

Die 139 verdeckten Tools sind **exakt** die 139 Tools mit `is_write=true`; die
80 angebotenen sind **exakt** die `is_write=false`-Tools. Mechanik:
`tool_registry.py:1038-1064` (`can_write` / `can_govern`), anerkannte Tiers in
`auth_tenancy/services/authorization.py:78-97`. Invariant „advertised surface
matches executable surface" (`tool_registry.py:975-978`) **hält**: dieselben
Write-Calls, die der Admin-Key ausführt, lehnt der `readwrite`-Key mit
`PERMISSION_DENIED` ab.

Der eigentliche Drift: `AGENTS.md:8`, `:30`, `:58` sagen „31 Tool-Gruppen-Präfixe,
215 Tools" (ist 35/219). `README.md:77`/`:114` (35/219) und
`docs/api/MCP-SURFACE.md:26-27` (219/35) sind **korrekt**; `MCP-SURFACE.md:39`
markiert „215" bereits korrekt als falsch. `README.md:1191` („Tool Groups
(25 prefixes)") widerspricht `README.md:77` innerhalb derselben Datei.

**Issue #1104** sollte damit auf „Doku-Drift in `AGENTS.md` + README-Transport-
und Präfixbehauptungen" verengt und mit CR-21 zusammengeführt werden.
Vollständige Rechnung: [wp1a-mcp-tool-count-resolution.md](AUDIT_EVIDENCE/wp1a-mcp-tool-count-resolution.md).

### 4. Tool-Eingabevalidierung (39 Fälle, 12 Tools)

`0 × HTTP 5xx`, `0 × Stacktrace/Interna-Leak` in **irgendeiner** Antwort
(Regex auf `Traceback`, `site-packages`, `psycopg2`, `django.db.`, `SQLSTATE`,
`/app/*.py`, `DETAIL:`). `is_error: true` trägt alle erwarteten Fälle.
**Keine Teilmutation beobachtet** (ein abgelehnter Create hat keine Zeile
angelegt; Kontroll-Creates daneben haben angelegt).

Sehr gut abgedeckt: UUID-Format, fehlende Pflichtfelder, Enum-Werte,
`limit` als String, unbekannte Tools, `attribute_migration.plan` Typprüfung,
`audit.query` Typprüfung.

Drei echte Lücken:

1. **Falscher Typ ⇒ „internal error" statt Validierungsfehler.**
   `glossary.create` mit `term: 42` ⇒ clientseitig
   `"Error: An internal error occurred."`; serverseitig
   `AttributeError: 'int' object has no attribute 'strip'` in
   `application/glossary_service.py:166`.
2. **Domänen-`ValidationError` wird maskiert.** Ein doppelter Glossary-Term
   (`Glossary term 'X' already exists in this workspace.`,
   `application/glossary_service.py:174`) kommt beim Client als
   `"An internal error occurred."` an. `mcp_server/tools/generic.py:512-515`
   fängt `Exception` ohne Typ-Map; dieselbe Datei mappt `ValidationError` in
   `apply_system_fields` **korrekt** (`:496-497`) — die Lücke ist also
   nachweisbar inkonsistent. REST mappt dieselbe Exception
   (`rest_api/views.py:217`, `_EXC_TO_CODE[ValidationError] = "VALIDATION_ERROR"`)
   auf HTTP 400 mit weitergeleiteter Meldung. **Transport-Parität verletzt**;
   `NotFoundError`, `PermissionDeniedError`, `OptimisticLockError`/`CONFLICT`
   fehlen im MCP-`generic.py` ebenfalls.
3. **Keine Längenbegrenzung.** `glossary.create` mit 20 000-Zeichen-`definition`
   wird persistiert. SQL-Metazeichen (`'; DROP TABLE glossary_term; --`,
   `1' OR '1'='1`) werden korrekt **parametrisiert** gespeichert — keine
   Injection, aber auch keine Sanitisierung/Begrenzung.

### 5. Tenant-Isolation (wichtigste Einzelprüfung)

**Ergebnis: sauber.** 65 Fälle, Tenant-A-Key gegen **einen eigens angelegten
zweiten Tenant** (`Tenant` + `User` + `UserRole(admin)` + `TenantRole(admin)` +
eigener `Workspace` + `admin`-Key):

| Gruppe | Fälle | Ergebnis |
|---|---|---|
| By-id-Reads auf Tenant-A-Artefakte (`requirement.get`, `needs.read`, `architecture.get`, `test.get`, `adr.read`, `risk.read`, `issue.read`, `icd.read`, `diagram.get`, `baseline.get`, `glossary.read`, `interview.get`, `goal.read`, `main_goal.read`, `link_type.get`, `attribute_definition.get`) | 16 | alle `isError: true` („… not found" / „Workspace … does not exist") — **kein Datenleck, kein 403-Orakel-Unterschied** |
| Workspace-scoped Reads auf Tenant-A-`workspace_id` (30 Tools) | 30 | alle „Workspace '4eee7ca1-…' does not exist" |
| Tenant-globale Reads | 5 | `workspace.list`/`user.list` liefern **nur** Tenant B; `events.dlq_list`/`artifact.search` isError |
| Writes (`glossary.create`, `workspace.close`, `review.approve`, `audit.waive_finding`, `requirement_bundle.export`, `traceability.suggest_links`) auf Tenant A | 7 | alle blockiert |
| Kontrollen B→B / A→A | 5 | alle erfolgreich |
| HTTP 5xx | — | **0** |

Die Isolation ist **zweistufig** und beide Stufen greifen: der
Workspace-Fence in `tool_registry.py:1220` (`_check_workspace_fence`) und der
RLS-Backstop in der Datenbank (`pl_workspace` hat `rowsecurity=True`,
`forcerowsecurity=True`, Policy
`tenant_id = NULLIF(current_setting('app.current_tenant',''),'')::uuid`;
DB-Rolle `reqogniloom_app` ist weder Superuser noch `BYPASSRLS`).

**Wichtige Methodik-Notiz (siehe AUD-2026-09-050):** ein erster
Isolationstest mit einem vermeintlichen Tenant-B-Key schien einen
Cross-Tenant-Leak über `workspace.list` zu zeigen (identische 401 Workspaces
für beide Keys). Die Ursache war ein **Test-Setup-Fehler**: der vermeintliche
Tenant-B-Besitzer war ein E2E-User, dessen `User.tenant_id` auf Tenant A zeigt,
und `validate_api_key` leitet den Tenant aus dem **Owner-User** ab
(`auth_tenancy/services/authentication.py:562`), nicht aus `ApiKey.tenant_id`.
Der Verdacht ist damit **widerlegt** — und die Ursache ist selbst ein Befund
(AUD-2026-09-035).

### 6. Auth auf beiden Pfaden

Beide Routen verhalten sich **identisch** (`X-API-Key` und
`Authorization: Bearer <API-Key>` ⇒ je 200/80 Tools). 15 Fallbreiten der
Auth-Matrix getestet: kein Key, leerer Key, ungültiger Key, falsches Präfix,
abgeschnitten, +1 Zeichen, kleingeschrieben, Bearer/Basic/ohne Schema, Bearer-JWT,
`params.api_key` nur im Body, `?api_key=`-Query-String, nur Cookie, Cookie+Key.
**Keine unerwartete Auth-Durchlässigkeit.** Cookie-only ⇒ 403 mit klarer
Begründung (CSRF-Prämisse wird erzwungen, `views.py:79-141`); CORS reflektiert
keinen fremden Origin und setzt nie `Allow-Credentials` ohne Allowlist.
Einziger Unterschied: 404-Format (HTML unter `/mcp/`, JSON unter
`/api/v1/mcp/`) — kosmetisch.

Zwei echte Befunde: die selbstwidersprechliche Meldung
`bearer_not_supported` (Bearer funktioniert ja) und der API-Key im
uvicorn-Access-Log. Details:
[wp1a-mcp-auth-and-key-tenant.md](AUDIT_EVIDENCE/wp1a-mcp-auth-and-key-tenant.md).

### 7. Manifest-Drift-Gate

`backend/mcp_server/tests/test_tool_manifest_drift.py` vergleicht die
**komplette Tool-Signatur** — `name`, `is_write`, `prefix`, `description`,
`inputSchema` (feldweise, key-order-insensitiv über `_canonical`) — plus
`tool_count` gegen `len(tools)` und gegen die Registry, und **fail-closed**, wenn
das Manifest nicht auffindbar ist (`:86-100`, mit explizitem Opt-out-Env).

**Nicht über pytest ausführbar** im laufenden Stack: 18 `ERROR`s, Ursache
`psycopg2.errors.InsufficientPrivilege: permission denied to create database`
beim `CREATE DATABASE "test_reqflow"` — die App-DB-Rolle hat kein `CREATEDB`.
Das ist selbst ein Befund (AUD-2026-09-048, CR-30-nah): `build_manifest()`
braucht **keine** Datenbank, der Guard hängt aber an `@pytest.mark.django_db`.

Deshalb wurde die Guard-Logik 1:1 nachgebaut und **12 Mutationen** unterzogen:
falsche Beschreibung, `is_write` in beide Richtungen geflippt, zusätzlicher
`required`-Param, Property-Typ geändert, falscher `prefix`, Tool gelöscht, Tool
dupliziert, veralteter `tool_count`, zwei Beschreibungen vertauscht, leere
Beschreibung, kosmetische Schlüsselreihenfolge.
**Score 12/12** — „erkennt der Test eine absichtlich eingefügte falsche
Tool-Beschreibung?" ⇒ **Ja, zuverlässig.**

### 8. Graceful Degradation

Simuliert wurde **Redis down** (`docker stop ai-native-reqflow-poc-redis-1`,
danach wieder gestartet, Health-Check danach 200).

| Probe | Redis an | Redis aus |
|---|---|---|
| `tools/list` | 200 (0.04 s) | **Hänger (>8 s)** |
| `workspace.list` | 200 | **Hänger** |
| `requirement.query` | 200 (0.29 s) | **Hänger** |
| `memory.digest` / `memory.list` | 200 | **Hänger** |
| `requirement_bundle.compression_status` | 200 | **Hänger** |
| `events.dlq_list` | 200 | **Hänger** |
| `traceability.suggest_links` (LLM, `mock`) | 200 (0.99 s) | **Hänger** |
| `audit.se_audit` | 200 (0.69 s) | **Hänger** |
| `glossary.create` (Write) | 200 | **Hänger** |
| `permissions.check` | 200 | **Hänger** |
| `admin.backup_list` | 200 | **Hänger** |
| `GET /mcp/sse/` | 200 stream | Hänger |
| **13/13** | ok | **kein Timeout, kein Fehler, keine Degradation** |

Ursache: `CACHES["default"]` in `reqogniloom/settings.py:879-883` nutzt
`django.core.cache.backends.redis.RedisCache` **ohne `OPTIONS`/`SOCKET_TIMEOUT`**
⇒ jeder Cache-Zugriff blockiert unbegrenzt. Jeder der drei MCP-Views ruft
allerdings zuerst `check_mcp_rate_limit()` (`views.py:272`, `:401`, `:505`,
`:736`), das über `SimpleRateThrottle` in genau diesen Cache schreibt
(`throttling.py:164`) — deshalb bleibt **auch** `tools/list` hängen, obwohl es
nur Postgres braucht. Dasselbe Muster hat das Projekt an anderer Stelle
korrekt: `admin_ops/health_rest.py:103-104` setzt `socket_connect_timeout` und
`socket_timeout` für seine Health-Checks.

**Nicht simulierbar:** LLM-Provider down (`LLM_PROVIDER=mock` ist eine
Umgebungsvariable des laufenden Containers; Umschalten hätte den Stack
verändert) und Datenbank down (Postgres-Ausfall hätte alle 8 Container und
den laufenden Parallel-Audits geschädigt). Klassifiziert als **BLOCKED**, nicht
als PASS. Für beide gilt: der Pfad geht durch dieselbe
`except Exception` → `INTERNAL_ERROR`-Maskierung, die in §4 als Maskierungs-
lücke belegt ist — ein plausibles, aber **nicht gemessenes** Risiko.

### Finding-Tabelle WP-1a

| ID | Schwere | Klassifikation | CR/Issue | Ort | Kurztitel |
|---|---|---|---|---|---|
| AUD-2026-09-030 | **Critical** | NEU | — | `backend/reqogniloom/settings.py:879`; `backend/mcp_server/views.py:272`; `backend/mcp_server/throttling.py:164` | Redis-Ausfall hängt alle 13 MCP-Endpoints unbegrenzt (kein Timeout) |
| AUD-2026-09-031 | **Critical** | NEU | — | `backend/reqogniloom/health.py:118-190` | `/health/` meldet „ok", während App+Auth+Schema unbenutzbar hängen |
| AUD-2026-09-033 | **High** | NEU | — | `backend/mcp_server/protocol_handler.py:536` | Nicht-dict `params` ⇒ HTTP 500 statt `-32600`/`-32602` (AttributeError außerhalb jedes try) |
| AUD-2026-09-034 | **High** | NEU | — | `backend/auth_tenancy/services/authentication.py:616` | `create_api_key` persistiert beliebige Scope-Strings für User-Keys; Key ist stumm schreibunfähig |
| AUD-2026-09-035 | **High** | NEU | — | `backend/auth_tenancy/services/authentication.py:562` | `ApiKey.tenant_id` ist dekorativ — `validate_api_key` nutzt `api_key.user.tenant_id` |
| AUD-2026-09-036 | **High** | NEU | — | `backend/mcp_server/tools/generic.py:512-515` | Domänen-`ValidationError`/`NotFoundError` als „internal error" maskiert; REST mappt dieselbe Exception auf 400 |
| AUD-2026-09-032 | **High** | BESTAETIGT | **CR-22** | `backend/mcp_server/views.py:291-304` vs. `:311-325` | Zwei inkompatible Fehler-Hüllen (`code` int vs. `error_code` str) auf demselben Endpunkt |
| AUD-2026-09-039 | Medium | NEU | — | `backend/mcp_server/protocol_handler.py:469` | Top-Level `null` ⇒ `-32700`; `str`/`int`/`bool` ⇒ 500 statt `-32600` |
| AUD-2026-09-040 | Medium | NEU | — | `backend/mcp_server/protocol_handler.py:572-577` | `tools/call` mit `arguments: null/str/list` oder `name: <int>` ⇒ `-32603` statt `-32602` |
| AUD-2026-09-038 | Medium | NEU | — | `backend/mcp_server/protocol_handler.py:239` vs. `:515` | Nur `notifications/initialized` ist von der `id`-Pflicht befreit; mit `id` ⇒ 202 ohne Antwort |
| AUD-2026-09-041 | Medium | BESTAETIGT | **CR-28** (verwandt) | `backend/mcp_server/views.py:176-190` | Klartext-API-Key im uvicorn-Access-Log; die Ablehnungs-Begründung ist damit unvollständig |
| AUD-2026-09-042 | Medium | BESTAETIGT | **CR-05** | `backend/mcp_server/tools/interview.py:181-202` | `interview.start` mit `mode: "multi"` ignoriert; verlangt `artifact_type` — Multi-Interview über MCP nicht startbar |
| AUD-2026-09-043 | Medium | NEU | — | `docs/agent-templates/tool-manifest.json` (`comment.*`) | `comment.create/list/resolve` deklarieren kein `workspace_id`; Create auf gültiges Artefakt ⇒ „Artifact not found" |
| AUD-2026-09-044 | Medium | NEU | — | `backend/mcp_server/protocol_handler.py:264` | Fehlermeldung `bearer_not_supported` widerspricht dem Verhalten und legt einen internen Code offen |
| AUD-2026-09-037 | Medium | BESTAETIGT | **CR-21** | `AGENTS.md:8,30,58`; `README.md:482,1060,1072,1163,1182,1191,1291` | Stale Zahlen (215/31), interner README-Widerspruch (25 vs. 35), stdio-Phantom |
| AUD-2026-09-045 | Low | NEU | — | `backend/mcp_server/protocol_handler.py:226-241` | `id: bool/array/object` akzeptiert und echoed (Spec: String/Number/null) |
| AUD-2026-09-046 | Low | NEU | — | `backend/mcp_server/tools/generic.py:493`; `backend/application/glossary_service.py:166` | Falsch typisierte Felder ⇒ `AttributeError` ⇒ „internal error" statt Validierungsfehler |
| AUD-2026-09-047 | Low | NEU | — | `backend/application/glossary_service.py:166` | Keine Längenbegrenzung: 20 000-Zeichen-Strings werden persistiert |
| AUD-2026-09-048 | Low | BESTAETIGT | **CR-30** | `backend/mcp_server/tests/test_tool_manifest_drift.py:83` | Guard im laufenden Stack nicht ausführbar (DB-Rolle ohne `CREATEDB`), obwohl `build_manifest()` keine DB braucht |
| AUD-2026-09-049 | Info | NEU | — | `backend/mcp_server/views.py:311-325` vs. `rest_api` 404-Handler | `/mcp/`-404 ist HTML, `/api/v1/mcp/`-404 ist JSON |
| AUD-2026-09-050 | Info | **WIDERLEGT** | — | (Test-Setup, kein Produktfehler) | Verdachtiger Cross-Tenant-Leak via `workspace.list`/`artifact.search` — Ursache war ein User in Tenant A; Isolation 65/65 sauber |
| AUD-2026-09-051 | Info | NEU | — | `backend/mcp_server/tests/test_tool_manifest_drift.py` | Manifest-Guard besteht 12/12 Mutationen inkl. falscher Tool-Beschreibung |

**Zählung:** 0 Critical-P1-Bereitstellung, aber 2 Critical (Availability),
4 High, 8 Medium, 4 Low, 5 Info — **23 Findings**.

### Ampel-Kurzfassung

🟢 **Belastbar:** Tenant-Isolation (zweistufig: App-Fence + DB-RLS,
65/65 sauber), Manifest-Guard (12/12 Mutationen), Fehler-Maskierung gegen
Stacktrace-Leaks (0 von 39 Validierungsfällen, 0 von 65 Isolationsfällen),
Header/Body/Query-Key-Ablehnung, CORS, SSE-Session-Binding, HTTP↔`/api/v1/mcp/`-Parität.

🔴 **Sofort relevant:** Redis-Ausfall legt die komplette MCP-Oberfläche lahm
ohne Timeout, und das Health-Gate erkennt das nicht. Beides ist Availability,
nicht Funktionalität, und beides ist billig zu beheben (Socket-Timeout in
`CACHES` + ein Cache-Check im Health-Endpoint).

### Nicht geprüft (BLOCKED, ausdrücklich nicht als PASS gewertet)

| Punkt | Grund |
|---|---|
| Abgelaufener / revokierter API-Key | Klartext existiert nur einmal bei Erzeugung; `at_api_key` speichert nur `key_hash`. Ein solcher Key hätte neu gemintet werden müssen — für Agent-Keys erzwingt `create_api_key` ein **zukünftiges** `expires_at`, User-Keys nicht. |
| Rate-Limit-Auslösung (`MCP_RATE_LIMIT_KEY`/`_IP`) | Bewusst nicht ausgelöst, um parallel laufende Audit-Agenten nicht zu blockieren. |
| LLM-Provider down | `LLM_PROVIDER=mock` ist eine Umgebungsvariable des laufenden Containers; Umschalten hätte den geteilten Stack verändert. |
| Datenbank down | hätte Postgres, alle 8 Container und laufende Parallel-Audits geschädigt. |
| WSGI-Betrieb (`manage.py runserver`) | Der Stack läuft unter ASGI/uvicorn; der SSE-Befund aus issue #455 (wsgiref-Hop-by-Hop) ist damit nicht reproduzierbar. |
| `test_tool_manifest_drift.py` via pytest | DB-Rolle ohne `CREATEDB`; Guard-Logik stattdessen 1:1 nachgebaut + 12 Mutationen. |
| `comment.resolve`-Workspace-Fence (**CR-04**) | `comment.create` auf ein Artefakt eines **anderen Workspace im selben Tenant** antwortet „Artifact … not found" — das ist ein Fail-Closed, kein Cross-Workspace-Write, also **nicht reproduziert**. Ob das der richtige Grund ist oder ein Scope-Fehler, der zufällig blockiert, konnte ich mit den `comment.*`-Schemas (kein `workspace_id`) nicht entscheiden — siehe AUD-2026-09-043. |
