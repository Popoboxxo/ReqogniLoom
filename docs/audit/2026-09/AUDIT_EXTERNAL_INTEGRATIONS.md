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
| WP-1d | api-specialist | [REST-API & Datenintegration](#wp-1d--rest-api--datenintegration) |

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

---

## WP-1d — REST-API & Datenintegration

> **Workpackage-Metadaten** — `type: REVIEW` · `scope: wp-1d-rest-api` ·
> `status: final` · `date: 2026-09-29` · `author_agent: api-specialist`
> **Status:** abgeschlossen. Rein lesender Audit, keine Produkt-Fixes.
> Finding-IDs dieses Abschnitts: `AUD-2026-09-070` … `AUD-2026-09-093`
> (Fortsetzung nach `AUD-2026-09-051`; `050`/`051` liegen in **WP-1a**, nicht in
> WP-1b — der Auftrag hatte sie WP-1b zugeordnet. Keine Kollision.)
> Evidenz: `docs/audit/2026-09/AUDIT_EVIDENCE/wp1d-*`.

### Ampel: **GELB-ORANGE**

Die Tenant-Isolation hält — **0 Leaks in 120 Cross-Tenant-Proben**. Auth, JWT-Ablehnung und
`StandardPagination` sind überdurchschnittlich sauber. Die Orange kommt aus drei
Round-Trip-Bruchstellen, die jeweils *stillschweigend* scheitern: CSV-Import meldet
`success: true` bei 0 importierten Zeilen, ReqIF-Import meldet `success: true` bei 915
Fehlern, und der CSV-Round-Trip des eigenen Exporters ist durch eine Kommentarzeile
unbrauchbar. Dazu ein 500er auf `?page=0` und 432/439 Operationen ohne deklarierte
Fehler-Schemata.

---

### 0. Architektur-Inventar — exakte Zahlen + Zählweg

**Zählmethode (reproduzierbar):** AST-Walk über `backend/rest_api/**/*.py`, `tests/`,
`__pycache__`, `migrations` ausgeschlossen; jedes modul-level `class X(...)` gesammelt;
Basse-Klassen transitiv aufgelöst (lokal + importiert) und klassifiziert als
ViewSet, sobald in der Kette `{ViewSet, GenericViewSet, ModelViewSet,
ReadOnlyModelViewSet}` vorkommt, bzw. APIView bei `APIView`. Jede konkrete
Blattklasse genau einmal gezählt.

| Zählung | Ergebnis |
|---|---|
| Klassen mit ViewSet in der Basis-Kette | **28** |
| davon abstrakte Basis `BaseEntityViewSet` (`views.py:304`, nie geroutet) | −1 |
| **Konkrete ViewSets** | **27** |
| **APIViews in `backend/rest_api/`** | **76** |
| APIViews in Sub-Apps (admin_ops 13, memory 17, auth_tenancy 3, reqogniloom 1) | 34 |
| APIViews backendweit | 110 |

**Reconciliation:**

| Quelle | ViewSets | APIViews | Verdikt |
|---|---|---|---|
| `AGENTS.md` | 27 | 67 | ViewSets **exakt richtig**. APIViews zu niedrig (−9) |
| Auftrag | 28 | 74 | ViewSets = 28 **inkl.** abstrakter `BaseEntityViewSet`; APIViews 74 vs. 76 gemessen |
| **Meine Messung** | **28 / 27 konkret** | **76** | — |

→ **Doku-Drift bestätigt**: `AGENTS.md` nennt „27 ViewSets + 67 APIViews", real sind
es 27 konkrete ViewSets (Zahl korrekt) und **76** APIViews (9 zu niedrig). Die
Auftragszahl 28 entsteht, wenn `BaseEntityViewSet` mitgezählt wird.

Beleg: `wp1d-viewset-apiview-inventory.json` (alle 28 + 76 Klassen mit
`file:line`).

---

### 1. OpenAPI-Schema-Drift (live, `GET /api/schema/` = 613 769 Bytes)

**Zahlen:** 296 Paths / 439 Operations / 106 Component-Schemas / 2 Security-Schemes.
Route-Vergleich gegen den *auflösten Django-URLResolver* (487 `/api/v1/*`-Routen,
486 mit Methoden).

| Richtung | Ergebnis |
|---|---|
| Im Schema, **nicht** geroutet | **0** |
| Geroutet, **nicht** im Schema | **7** |
| Methoden-Drift auf gemeinsamen Paths | **0** (nach Ausfilterung von `OPTIONS`/`HEAD` und DRF-Format-Suffix-Varianten) |

Die 7 nicht deklarierten Pfade sind alle erklärbar und je benannt:

| Pfad | Bewertung |
|---|---|
| `/api/v1` (DRF-API-Root) | **BUG (Low)** — Schema deklariert keinen Root, obwohl der Router sie ausliefert |
| `/api/v1/mcp/messages` | **Docs-Drift** — MCP-Ingress fehlt komplett im REST-Schema |
| `/api/v1/mcp/sse` | dito |
| `/api/v1/mcp` | dito (Alias-Registrierung, `reqogniloom/urls.py:51`) |
| `/api/v1/schema` | **Docs-Drift** — das Schema beschreibt sich selbst nicht |
| `/api/v1/schema/swagger-ui` | dito |
| `/api/v1/{}` | JSON-404-Catch-all (`reqogniloom/urls.py:59`), bewusst nicht im Schema |

**Pfad-/Methoden-Abdeckung ist damit ausgezeichnet.** Die Drift liegt woanders:

**(a) Fehler-Schemata: 432 von 439 Operationen (98,4 %) deklarieren keinen einzigen
Fehler-Fall.** Histogramm der deklarierten Fehlercodes:

```
[]              432   ← keine 4xx/5xx deklariert
['401']           1
['404']           3
['400','404']     3
```

Null Operationen deklarieren einen 5xx. `rest_api/openapi.py:71-98` definiert
`COMMON_ERROR_RESPONSES` mit 400/401/403/404/500 — **das Dict wird nirgends verwendet**
(`rg COMMON_ERROR_RESPONSES backend` findet nur die Definition). Der einzige
`ErrorResponseSerializer`-Einsatz ist `auth_views.py:281`.

**(b) `required`/Typen/Formate:** 0 Abweichungen zwischen Serializer und deklarierter
Response-Struktur gefunden; die Listen-Endpunkte deklarieren das
`{count, next, previous, results, page_size, max_page_size}`-Envelope korrekt, und
`StandardPagination` hängt `maximum: 100` an den `page_size`-Parameter
(`serializers.py:412`) — das ist rare Sorgfalt und sollte erhalten bleiben.

**(c) Security:** alle 439 Operationen tragen ein `security`-Attribut. Die drei
tatsächlich öffentlichen Endpunkte nutzen `security: [{BearerAuth: []}, {}]`
statt des kanonischen `security: []` — semantisch äquivalent, aber nicht
idiomatisch (`auth/login`, `auth/refresh`, `public/banners/login`).

**(d) `cookieAuth` ist als Security-Scheme deklariert** (`components.securitySchemes`,
`in: cookie, name: sessionid`), wird aber von **keiner** Operation referenziert — der
`sessionid`-Pfad ist im Request-Flow unbenutzt. Deklariert eine tote Auth-Variante.

Beleg: `wp1d-openapi-drift.json`, `wp1d-schema-vs-routes.md`.

---

### 2. Auth / JWT (live, 20 Fälle)

JWT-Claims: `user_id`, `tenant_id`, `roles`, `typ`, `iat`, `exp` (TTL 3600 s),
`iss=reqogniloom`, `aud=reqogniloom-api`. `AUTH_JWT_SECRET` = 86 Bytes (kein
Längenproblem; die 12-Byte-Warnung im Log stammt aus *meinem* Testschlüssel).

| Fall | Status | `error.code` | Bewertung |
|---|---|---|---|
| kein `Authorization` | 401 | `AUTHENTICATION_REQUIRED` | ✅ |
| `Bearer ` (leer) | 401 | `invalid_token` | ✅ |
| Müll-Token | 401 | `invalid_token` | ✅ |
| falsche Signatur | 401 | `invalid_signature` | ✅ |
| abgelaufen (korrekt signiert) | 401 | `invalid_signature`* | ⚠ s. u. |
| falsches `aud` | 401 | `invalid_signature`* | ⚠ s. u. |
| falsches `iss` | 401 | `invalid_signature`* | ⚠ s. u. |
| `alg=none` | 401 | `invalid_token` | ✅ |
| unbekannter `user_id` | 401 | `invalid_signature`* | ⚠ s. u. |
| `reqlo_…` als Bearer | 401 | `invalid_api_key` | ✅ eigene Code-Familie |
| `X-API-Key` auf REST | 401 | `invalid_api_key` | ✅ |
| `Cookie: sessionid=bogus` | 401 | `AUTHENTICATION_REQUIRED` | ✅ |
| `Token <jwt>` (falsches Schema) | 401 | `AUTHENTICATION_REQUIRED` | ✅ |
| JWT in Query-String | 401 | `AUTHENTICATION_REQUIRED` | ✅ kein Token-Leak |
| doppelter `Authorization`-Header | 401 | `invalid_token` | ⚠ s. u. |
| Schreib-Endpoint ohne Auth | 401 | `AUTHENTICATION_REQUIRED` | ✅ |
| `/admin/health/` ohne Auth | 401 | `AUTHENTICATION_REQUIRED` | ✅ |
| `/admin/restore/` ohne Auth | 401 | `AUTHENTICATION_REQUIRED` | ✅ |

**Ergebnisse:**

- **401 vs. 403 wird durchgängig korrekt unterschieden** — fehlende/ungültige
  Credential immer 401, rollenbasierte Ablehnung immer 403. Kein Fall gefunden,
  in dem 403 statt 401 oder umgekehrt steht.
- **Keine internen Details in Fehlerantworten.** Kein Stacktrace, kein
  Exception-Klassenname, kein SQL. `_STATUS_TO_CODE` (`error_envelope.py:34-45`)
  ist ein sauberer Registry-Ansatz.
- **⚠ Ablauf / `aud` / `iss` sind nicht individuell unterscheidbar.** Alle vier Fälle
  melden `invalid_signature`, weil die Signaturprüfung *vor* der Claim-Prüfung läuft
  und ein manipulierter Token an der Signatur scheitert. Ich konnte **nicht**
  verifizieren, dass abgelaufene und `aud`-fremde Token mit *korrekter* Signatur
  ebenfalls `invalid_signature` liefern oder ob dort ein spezifischerer Code greift —
  ein korrekt signiertes Token hätte den echten `AUTH_JWT_SECRET` aus dem Container
  erfordert, den ich nicht ausleiten wollte. → **BLOCKED**, aber mit
  Definitionslücke im Fehlercode-Vertrag: ein Client kann `expired` nicht von
  `wrong-aud` unterscheiden.
- **⚠ Header-Smuggling-Verhalten:** zwei `Authorization`-Header (erster leer, zweiter
  gültig) → 401 `invalid_token`. Der Server wertet also *nicht* „erstes present-But-
  invalid, dann nächstes" auf, sondern bricht ab. Das deckt sich mit der im Schema
  dokumentierten Präzedenz, ist aber inkonsistent mit der dort ebenfalls
  dokumentierten Regel „present-but-invalid ⇒ 401, no other credential evaluated"
  *innerhalb* eines Headers. Kein Exploit, aber eine inkonsistente Erzählung.
- **Testlücke:** Token eines **deaktivierten Users** und **Token nach Rollenentzug**
  (CR-26) konnte ich nicht testen, ohne Tenant B / einen Tenant-A-User dauerhaft zu
  verändern. Der Probe-User wurde nach dem Test gelöscht; die deaktivieren/aktivieren-
  Sequenz ist bewusst **nicht** gefahren worden → siehe „Nicht geprüft".

Beleg: `wp1d-auth-matrix.md`.

---

### 3. Pagination

**Positiv (das stärkste Stück der REST-API):** `StandardPagination`
(`serializers.py:328-470`) ist server-seitig gedeckelt, klampft hart und **echo`t den
angewendeten Wert**:

| `?page_size=` | Resultat |
|---|---|
| `1` | 1 Element, `page_size: 1` |
| `100000` | **auf 100 geklemmt** |
| `99999999999999999999` | auf 100 geklemmt (kein Overflow-Fehler) |
| `0` / `-5` / `abc` / `1e400` | stiller Fallback auf Default 25 |
| `?limit=10000&offset=0` | still ignoriert, Fallback auf 25 |

`TraceLinkPagination` deckelt auf 500 (`serializers.py:497`).

**Aber: die Pagination ist nicht flächendeckend.** 44 List-Endpunkte probiert:

| Envelope | Anzahl | Beispiele |
|---|---|---|
| Standard-`{count, next, previous, results, page_size, max_page_size}` | **24** | requirements, artifacts, workspaces, trace-links, glossary |
| Eigenes Shape | **16** | search (`{results, total_count, page, limit}`), metrics, notifications, prompt-variables, attribute-catalog |
| **Nackte Liste, `page`/`page_size` komplett ignoriert** | **4** | `/api/v1/api-keys/`, `/api/v1/users/`, `/api/v1/link-type-defaults/`, `workspaces/{id}/link-type-definitions/` |

`/api/v1/api-keys/` liefert **alle 200 Keys in einer Antwort (54 KB)** —
`?page_size=1` ändert nichts. Das ist ein Skalierungs-/DoS-Risiko (High), sobald ein
Tenant viele Keys hat. `/api/v1/metrics/` antwortet mit **782 KB in einer Response**,
ohne jede Paginierung.

**⚠ 500er auf ungültigem `page`** — der wichtigste Einzelfund:

| Endpunkt | `page=0` | `page=-3` | `page=abc` | `page=99999999` |
|---|---|---|---|---|
| `/api/v1/workspaces/` | 404 `Invalid page.` | 404 | 404 | 404 |
| **`/api/v1/trace-links/`** | **500** | **500** | **500** | **500** |
| **`/api/v1/glossary/`** | **500** | **500** | **500** | **500** |
| `/api/v1/search/` | 400 `page must be >= 1.` | 400 | 400 `page and limit must be integers` | 200 (leer) |

DRFs `PageNumberPagination` wirft für eine ungültige Seite `NotFound` — das macht
`/api/v1/workspaces/` korrekt. `TraceLinkPagination` (`serializers.py:478`, erbt von
`StandardPagination`) und die Glossary-Liste liefern stattdessen einen **ungefangenen
500er**. Ein clientseitiger Tippfehler oder ein Crawler erzeugt so Serverfehler.

Beleg: `wp1d-pagination-filter-matrix.md`, `wp1d-pagination.json`.

---

### 4. Filter

60 Kombinationen aus 5 Endpunkten × 12 Proben.

| Probe | Verhalten |
|---|---|
| unbekannter Filter `?no_such_filter=1` | **still ignoriert, 200** (5/5 Endpunkte) |
| `?title=1' OR '1'='1` | 200, als Literal behandelt — **keine Injection** |
| `?ordering=title; DROP TABLE artifacts--` | 200 als Literal — keine Injection |
| `?search=%27%29%20OR%201%3D1%20--` | 200 als Literal — keine Injection |
| `?ordering=tenant_id` | 200 |
| `?ordering=created_by__password` | 200 |
| `?ordering=does_not_exist` | 400 `VALIDATION_ERROR` ✅ |
| `?ordering=id; --` | 400 ✅ |
| `?workspace_id=<fremde UUID>` | 200 mit `count: 0` (RLS filtert) ✅ |
| `?workspace_id=abc` | 400 ✅ |
| `?level=%00binary` | 200 |
| `?page_size=1e400` | stiller Fallback ✅ |

**Ergebnisse:**

- **Keine SQL-Injection.** Weder in Filter- noch in Ordering-Werten. Django-ORM
  parametrisiert; `ordering` wird gegen eine Allow-List geprüft.
- **Unbekannte Filter werden still verworfen** (200 statt 400). Das ist bewusste
  Praxis (Typo-Toleranz), aber es ist nicht dokumentiert: ein Tippfehler
  `?workpsace_id=` liefert still eine gefilterte Liste und sieht wie Erfolg aus.
  Medium, kein Security-Problem.
- **`ordering=tenant_id` und `ordering=created_by__password` werden mit 200
  quittiert.** Ob die Sortierung tatsächlich angewendet wird, ist aus der Antwort
  nicht ableitbar — ich habe es nicht verifiziert (→ BLOCKED). Wenn sie angewendet
  wird, erlaubt das Sortieren über ein Fremd-Feld einenordering-Seitenzähler; das wäre
  nur ein Minor.
- **`?ordering=does_not_exist` → 400** ist korrekt und konsistent.

Beleg: `wp1d-pagination-filter-matrix.md`.

---

### 5. Fehlerformat-Matrix

Das Projekt hat bewusst ein eigenes Envelope `{"error": {code, message, details}}`
(`error_envelope.py:48-68`) statt `{detail, code, trace_id}`. Ich bewerte deshalb die
**interne** Konsistenz, nicht die Best-Practice-Konformität.

**Konsistent (Klassen-basierte Views, Ausnahmerhandler greift):**

| Fall | Status | Top-Level-Keys | `error.code` |
|---|---|---|---|
| 404 Requirement | 404 | `error` | `NOT_FOUND` |
| 404 unbekannte Route | 404 | `error` | `NOT_FOUND` |
| 400 leerer Body | 400 | `error` | `VALIDATION_ERROR` |
| 400 unbekanntes Feld | 400 | `error` | `VALIDATION_ERROR` |
| 400 falscher Typ | 400 | `error` | `VALIDATION_ERROR` |
| 415 falscher Content-Type | 415 | `error` | `UNSUPPORTED_MEDIA_TYPE` |
| 405 falsche Methode | 405 | `error` | `METHOD_NOT_ALLOWED` |
| 403 kein Workspace-Mitglied | 403 | `error` | `PERMISSION_DENIED` |
| 401 kein Token | 401 | `error` | `AUTHENTICATION_REQUIRED` |

**Abweichungen (echte Matrix):**

| Quelle | Ort | Format | Auswirkung |
|---|---|---|---|
| `_handle()` Helfer | `rest_api/link_type_views.py:31-43` | **`{"detail": str(exc)}`** für 403/404/400 | umgeht `reqogniloom_exception_handler` komplett |
| `scope_preview()` | `baseline/views.py:101` | **`{"detail": ...}`** | dito |
| CSV-Import-Controller | `import_service.py:307-313` | **`{success, imported_count, skipped_count, status, errors, warnings}`** — flach, kein `error`-Key | Client muss drei Shapes kennen |
| ReqIF-Import-Controller | `reqif_import_service.py` | **`{success, dry_run, needs: {...}}`** | vierter Shape |
| MCP-Transport | `/mcp/sse` 401 | **`{"error": "Authentication required"}`** — flacher String | fünfter Shape; `error_envelope.py:8-9` behauptet das Gegenteil |

Damit existieren **5 Fehlerformate** über die 3 Transportformen. `error_envelope.py:8-9`
schreibt: „Wired via `REST_FRAMEWORK['EXCEPTION_HANDLER']` so REST responses stay
consistent with the MCP-server error format" — die MCP-Formate sind untereinander
und vom REST-Format verschieden, die Behauptung trifft nicht zu.

Zusätzlich: die Fehlerhülle enthält **kein `trace_id` / `request_id`**, obwohl die
Applikation durchgängig eine `request_id` im Log führt (`{"request_id": ...}` in jedem
Log-Record). Ein Client kann einen 500er nicht beim Support korrelieren. Medium.

Beleg: `wp1d-error-format-matrix.md`.

---

### 6. TENANT-LEAK — praktischer Test

**Setup (wie erzeugt):** Es existiert **kein** REST- oder Management-Pfad, der einen
zweiten Tenant anlegt (gesucht: `management/commands/*` in allen 12 Apps, `POST
/api/v1/*`). Deshalb: Tenant B, Tenant-Admin-User B (`wp1d_probe_b`) und Workspace B
über ein ORM-Skript mit `persistence.middleware.set_request_tenant()`; die Artefakte
in B anschließend **über die REST-API als B-User** (9 Objekte: Requirement, Arch,
TestCase, Need, ADR, Risk, Goal, Issue, Glossary-Term, Titel mit `ÄÖÜ 🚀`), damit der
reale Erzeugungspfad geprüft wird.

> ⚠ `set_request_tenant` ist zwingend: direktes ORM ohne Tenant-Kontext wird von der
> PostgreSQL-RLS-Policy geblockt (`new row violates row-level security policy for
> table "pl_workspace"`) — die DB-Isolation ist also echt und greift auch gegen
> fehlerhafte Anwendungs-Code-Pfade.

**120 Proben** (A-Token → B-Objekte: 84; B-Token → A-Objekte: 23; B-API-Key → A-Endpunkte: 4;
Detail/Liste/Suche/Aggregat/Export/Historie/Audit/Actions/Webhooks).

### **Ergebnis: NEIN — 0 Tenant-Leaks.**

Beide heuristischen LEAK-Treffer wurden verifiziert und sind **Falsch-Positive**:

| Kandidat | Rohbefund | Verifikation | Verdikt |
|---|---|---|---|
| `/api/v1/search/?q=…&workspace_id=B` | HTTP 200, Antwort enthält den Suchstring | A-Token: `total_count: 0`, `results: []`. B-Token: `total_count: 9` mit genau Bs 9 Titeln. Der Marker im A-Response ist der **echo-Query**, nicht ein Treffer | **Falsch-Positiv** |
| `/api/v1/api-keys/` mit B-Token | HTTP 200, Key-Name `WP1D-PROBE-B key2` | A-Token sieht **200 eigene Keys, 0 Probe-Keys**. B-Token sieht **genau seinen eigenen** Key. Das ist tenant-korrekt, mein `expect` war falsch gesetzt | **Falsch-Positiv** |

Vollständiger A-Token-Sweep gegen B-Daten (10 Endpunkte, inkl. aller drei Exports):

| Endpunkt | Status | B-Marker | B-WS-ID | B-Req-ID |
|---|---|---|---|---|
| `/requirements/?workspace_id=B` | 200 | nein | nein | nein |
| `/artifacts/?workspace_id=B` | 200 | nein | nein | nein |
| `/search/?q=…&workspace_id=B` | 200 | nein (nur Echo) | nein | nein |
| `/workspaces/B/export/csv/` | **200** | nein | nein | nein |
| `/workspaces/B/export/reqif/` | 404 `Workspace … not found.` | nein | nur im Fehlertext | nein |
| `/workspaces/B/reports/pdf/` | 404 | nein | nur im Fehlertext | nein |
| `/workspaces/B/audit/` | 404 `… not found in the caller's tenant.` | nein | nur im Fehlertext | nein |
| `/workspaces/B/members/` | **403** `You are not a member of this workspace.` | nein | nein | nein |
| `/trace-links/?workspace_id=B` | 200 `count: 0` | nein | nein | nein |
| `/workspaces/B/baselines/` | 404 | nein | nein | nein |

**Aber: drei Authorisierungs-Asymmetrien** (kein Leak, aber inkonsistent):

| Endpunkt | A-Token auf Workspace B | A-Token auf **nicht existierender** UUID | Bewertung |
|---|---|---|---|
| `/workspaces/{ws}/export/reqif/` | **404** | 404 | ✅ korrekt |
| `/workspaces/{ws}/reports/pdf/` | **404** | 404 | ✅ |
| `/workspaces/{ws}/audit/` | **404** `in the caller's tenant` | 404 | ✅ |
| **`/workspaces/{ws}/export/csv/`** | **200** (31 Bytes, nur Header) | **200** | ⚠ **keine Workspace-Prüfung** — RLS filtert auf 0 Zeilen, der Endpoint leckt nichts, verweigert aber auch nichts |
| **`/workspaces/{ws}/import/csv/`** | **400 `validation_error`** | 400 | ⚠ Validierungsfehler statt 403/404 für eine fremde Workspace-ID |
| **`/workspaces/{ws}/review-policy/`** | **200** `{mode, min_confidence}` | **200** | ⚠ liefert tenant-globale Defaults für *jede* ID. Kein Datenleck (`settings_service.py:672`: „A read never creates a row"), aber keine 403/404-Disziplin |
| `/workspaces/{ws}/memory/digest/`, `/banner/` | 200/204 | 200/204 | ⚠ dito |

Das ist zugleich eine **Tenant-Existenz-Orakel-Bewertung**: die drei 404-Pfade
unterscheiden „gehört fremdem Tenant" (`… in the caller's tenant.`) von „existiert
nicht" (`Workspace <id> not found.`) in der Fehlermeldung. Zwei der drei
404-Texte unterscheiden **nicht** — das ist der unauffälligere, aber inkonsistente
Fall. Ich habe keinen Endpoint gefunden, über den sich Tenant-IDs vollständig
enumerieren ließen (UUID-Raum), klassifiziert als **Info (Low)**.

Beleg: `wp1d-tenant-leak-matrix.md`, `wp1d-tenant-matrix.json`,
`wp1d-tenant-leak-verify.json`, `wp1d-oracle-and-envelope.json`.

---

### 7. Round-Trip-Datenintegration

#### 7a. ReqIF 1.2

**Export (Tenant A, 888 Requirements):** 2 059 496 Bytes, `application/xml`,
915 `SPEC-OBJECT`, gültiges UTF-8 inkl. `ÄÖÜ äöü ß € 🚀`.

**Import:** akzeptiert **ausschließlich `multipart/form-data`**.
`application/xml`, `text/xml`, `application/octet-stream` → alle **415**, obwohl der
**Export** genau `application/xml` ausliefert. Asymmetrie, und das OpenAPI-Schema
deklariert für den Import **keinen** `requestBody` — der korrekte Content-Type ist
nirgends dokumentiert.

**Import-Ergebnis: `success: true`, 0 created, 0 updated, 915 × „An internal error
occurred while importing this object."**

Root Cause (aus dem Backend-Log, 915× identisch):
`application/reqif_import_service.py:697` → `Artifact.objects.create()` →
`psycopg2.errors.UniqueViolation: duplicate key value violates unique constraint
"pl_artifact_pkey"` → Folgefehler
`django.db.transaction.TransactionManagementError: An error occurred in the current
transaction` (`:681`, `:415`).

**Ursache:** `SPEC-OBJECT/@IDENTIFIER` *ist* die `pl_artifact.id`. Beim Import in
einen anderen Tenant kollidieren diese IDs mit den globalen PKs des Quelltenants.
Der Importer fängt den Fehler **pro Objekt** ab, bricht aber die Transaktion nicht
sauber ab — jede weitere Zeile scheitert an der kaputten Transaktion.

**ReqIF-1.2-Konformität des Exports (gegen das XSD):**

| Merkmal | Erwartet ReqIF 1.2 | Ist | Bewertung |
|---|---|---|---|
| `REQ-IF-HEADER/@reqIFVersion` | Pflichtattribut | **fehlt** (`<REQ-IF-HEADER IDENTIFIER="_header-…">`) | **nicht 1.2-konform** |
| `SPEC-OBJECT/SPEC-OBJECT-CONTENT` | Pflicht (genau 1) | **0 in 915 Objekten** | **nicht 1.2-konform** |
| `THE-VERSION`-Attribut am Header | Pflicht | fehlt | dito |
| `ATTRIBUTE-DEFINITION-STRING` | vorhanden | 8 vorhanden ✅ | ✅ |
| `DATATYPE-DEFINITION-STRING` | vorhanden | `DT-String` ✅ | ✅ |
| UTF-8 deklariert | ja | `encoding="UTF-8"` ✅ | ✅ |

**UID/Identität:** Der Fix `#1003/#1004` (`a6541783`) **ist gemergt**
(`git merge-base --is-ancestor a6541783 HEAD` → 0) und **wirksam**: neu angelegte
Artefakte bekommen `uid` (`REQ-001`), und der Export schreibt `ATTR-UID=REQ-001`.
Der Fallback `external_uid or need.uid` (`reqif_export_service.py:662`) greift also.
**Aber:** die ~888 **vorbestehenden** Seed-Artefakte haben `uid = null` → ihr Export
schreibt `THE-VALUE=""`. Ein Round-Trip über diese Daten verliert die Identität.
Backfill-Lücke, kein Regressionsfehler.

**Idempotenz: nicht gegeben.** Ein zweiter Import liefert dasselbe `success: true`
mit denselben 915 Fehlern, aber **nicht** `updated` — es wird nichts erkannt.

Beleg: `wp1d-roundtrip-reqif.md`, `wp1d-reqif-A.xml`, `wp1d-reqif-B.xml`,
`wp1d-roundtrip2.json`.

#### 7b. CSV-Bulk-Import

**Der wichtigste Fund: der Round-Trip des eigenen Exporters ist kaputt.**

`GET /export/csv/` schreibt als **erste Zeile** `# terminology_profile: default`.
`import_csv` liest diese Zeile als **Header**. Folge: alle echten Spaltennamen
werden als „unbekannt" gemeldet, alle Zeilen als leer, und der Endpoint antwortet:

```
HTTP 201  {"success": true, "imported_count": 0, "skipped_count": 0,
           "status": "ok", "errors": [], "warnings":
           ["Unrecognized column(s) ignored, their data was NOT imported:
             , 1, CLEAN-1, SyReq, demo, draft, plain desc. …"]}
```

**201 „success" bei 0 importierten Zeilen.** Beweis der Kausalität: entfernt man
nur die Kommentarzeile, funktioniert derselbe Import (`imported_count: 1`).
Damit ist die im Code dokumentierte Zusage
`export_service.py:17-18` („`export_csv -> ImportService.import_csv` is a lossless
round-trip … self-migration safety net") **nicht erfüllt**.

**Weitere belegte Defekte (Kontrolltabelle mit korrektem Header):**

| Fall | Ergebnis | Bewertung |
|---|---|---|
| korrekter Header, 1 Zeile | 201, imported 1 | ✅ |
| **identische Datei 3× importiert** | 201, 201, 201 → **3 Zeilen mit identischem Titel `RTQ-IDEM`** | ⚠ **nicht idempotent, keine Duplikaterkennung** |
| **BOM** (`\xef\xbb\xbf`) | 400 `Required field 'title' is missing or empty.` | ⚠ BOM nicht erkannt; Meldung beschreibt die **Daten** statt der Ursache |
| **Semikolon** statt Komma | 400 `title is missing or empty` + Warnung | ⚠ kein Delimiter-Sniffing; Meldung irreführend |
| **kaputtes Quoting** (`"RTQ-11 unterminated,…`) | **201 success, imported 1**, Titel wird zu `RTQ-11 unterminated,demo,draft,SyReq,1,,,,,,,,` | ⚠ **kaputte Zeile still importiert** |
| **ungültiger `status`** (`NOT_A_STATUS`) | **201 success, imported 1** | ⚠ **Enum nicht validiert** |
| ungültiger `type` (`NOT_A_TYPE`) | 400 `status: "rollback"`, **`errors: []`** | ⚠ stiller Fehlschlag |
| ungültiges `level` (`NOT_AN_INT`) | 400 `status: "rollback"`, **`errors: []`** | ⚠ stiller Fehlschlag |
| fehlender Titel | 400 `validation_error` mit `row_number: 2, field: title` | ✅ vorbildlich |
| gemischt 1 gültig + 2 ungültig | 400, `skipped_count: 3`, aber **nur 1** Fehler gemeldet | ⚠ Fehlerliste unvollständig |
| unbekannte Spalte | 201 + Warnung mit Spaltennamen | ✅ vorbildlich (Fix #120) |
| Latin-1-Bytes | 400 `CSV file must be UTF-8 encoded.` | ✅ sauber |
| kein `file`-Part | 400 `No CSV file uploaded.` | ✅ |
| unbekannter `entity_type` | 400 mit erlaubten Werten | ✅ |
| `tenant_id` im Body | 400 `Unknown field.` | ✅ Positiv-Kontrolle |

**Root Cause des stillen Fehlschlags:** `application/import_service.py:300-314`
ist ein nacktes `except Exception:` → `logger.exception(...)` → Rückgabe
`ImportResult(errors=[], status="rollback")`. Der Client bekommt **null
Diagnose**. Die konkrete Ausnahme im Log ist
`ValueError: invalid literal for int() with base 10: 'SyReq'` aus
`import_service.py:101` (`_import_value`, `int()`-Zweig) aufgerufen von `:591`.
Fehler-Maskierung ist an sich richtig (vgl. `test_error_masking_cwe209.py`), eine
**leere** Fehlerliste ist es nicht.

**Transaktionsgrenze:** korrekt all-or-nothing — `atomic` + Rollback, `imported_count`
bleibt 0, Zählerstand in B unverändert nach jedem Fehlversuch. Das ist richtig.
Aber: `skipped_count` zählt *Zeilen*, nicht *Fehler*, und `errors` listet nicht alle
Fehler — die Status-Semantik (`rollback` vs. `validation_error`) ist damit nicht
zuverlässig interpretierbar.

Beleg: `wp1d-roundtrip-csv.md`, `wp1d-csv-decisive.json`, `wp1d-csv-clean.json`.

#### 7c. PDF-Report-Export

| Fall | Ergebnis |
|---|---|
| Tenant A, 888 Requirements | 200, **0,75 s**, 60 664 Bytes, `%PDF-1.4` |
| Tenant B, 1 Requirement | 200, 0,06 s, 2 202 Bytes |
| `?async=true` | 200 synchron, kein 202, kein Task-ID |
| Fremder Workspace mit A-Token | 404 (korrekt) |

- **Synchron gerendert** (reportlab, im Request-Thread). Bei 888 Requirements
  0,75 s — unkritisch. Ein Zeitmessungs-Beleg für den Timeout-Fall fehlt
  (→ BLOCKED, siehe unten).
- **Schriften:** ausschließlich `Helvetica`, `Helvetica-Bold` (+ `ZapfDingbats`),
  Encoding `WinAnsiEncoding`. **Kein eingebetteter Font** (`/FontFile*` fehlt),
  **kein Type0/CID-Font**, kein `ToUnicode`-CMap.
  → Jedes Zeichen außerhalb WinAnsi (Emoji, CJK, Kyrillisch, Griechisch) ist
  **nicht darstellbar**. Tenant Bs Testanforderung enthielt `ÄÖÜ 🚀`; das `🚀`
  (U+1F680) kann mit dieser Font nicht kodiert werden. Dass `ZapfDingbats` nur im
  Tenant-B-PDF auftaucht, nicht im Tenant-A-PDF (ASCII-Daten), ist ein
  korrespondierendes Indiz für einen Fallback. Den exakten Ersatz-Glyphen habe ich
  nicht extrahiert — die Font-Tabelle ist der Beleg.
- **Tenant-Fremddaten: nein.** Tenant-B-PDF enthält nur Bs 1 Requirement
  (2 202 Bytes), Tenant-A-PDF nur A-Daten.
- **`Content-Disposition` ohne RFC-5987-Kodierung:**
  `attachment; filename="Zahnbürste_SysEng_Demo_requirement_document.pdf"` —
  Nicht-ASCII im Dateinamen ohne `filename*=UTF-8''…`. Browser und HTTP-CLients
  interpretieren das nach eigener Locale → Ersatzzeichen im Dateinamen.
- **CSV-Export ebenfalls ohne `charset`:** `Content-Type: text/csv` ohne
  `charset=utf-8`. Die Bytes sind korrekt UTF-8 (verifiziert:
  `WP1D-PROBE-B Requirement \xc3\x84\xc3\x96\xc3\x9c \xf0\x9f\x9a\x80`), aber
  RFC-4180-Default ist mehrdeutig und Excel-DE/LibreOffice werden die Umlaute
  darstellen.

Beleg: `wp1d-roundtrip-pdf.md`, `wp1d-pdf-A_own_888reqs.pdf`,
`wp1d-pdf-B_own_small.pdf`.

---

### 8. Ingress-Referenz `/api/v1/mcp/`

**Ergebnis: die beiden Ingresses sind symmetrisch. Es gibt hier keinen Bug — WP-1as
Beobachtung ist zu relativieren.**

`reqogniloom/urls.py:51-52` registriert **beide** Pfade auf dieselbe URL-Muster-
Liste:

```python
path("api/v1/mcp/", include("mcp_server.urls")),
path("mcp/", include("mcp_server.urls")),
```

| Probe | `/mcp/` | `/api/v1/mcp/` | Symmetrie |
|---|---|---|---|
| `GET` ohne Credential | 200, Server-Deskriptor | 200, identisch | ✅ |
| `GET` mit Bearer-JWT | 200 | 200 | ✅ |
| `GET` mit `X-API-Key` | 200 | 200 | ✅ |
| `POST initialize` mit Bearer | 200 JSON-RPC-Result | 200 identisch | ✅ |
| `POST initialize` mit ungültigem Key | 200 | 200 identisch | ✅ |
| `POST initialize` ohne Credential | 200 | 200 identisch | ✅ |
| `GET /sse` mit Bearer | **401** `{"error": "Authentication required"}` | **401** identisch | ✅ |
| `GET /sse` ohne Credential | 401 | 401 identisch | ✅ |

**Was WP-1a tatsächlich sah:** die Asymmetrie besteht **innerhalb** der MCP-Server-
Transports (GET-SSE akzeptiert kein Bearer, POST-HTTP schon), **nicht** zwischen den
beiden Ingress-Präfixen. Beide Präfixe verhalten sich in jeder Probe byte-identisch.

**Zwei echte, kleine Befunde dabei:**

1. `GET /mcp/` ist **ohne jede Credential** öffentlich und liefert
   `{"server": "ReqogniLoom MCP Server", "protocol": "JSON-RPC 2.0",
   "transports": ["http","sse"], "version": "1.0.0"}` — Versions-Disclosure
   (Low, bewusste Server-Info nach MCP-Spec).
2. Die MCP-Fehlerhülle `{"error": "Authentication required"}` ist ein **flacher
   String**, nicht das REST-Envelope. Das ist ein fünfter Fehler-Shape (siehe §5).

Beleg: `wp1d-ingress-symmetry.json`.

---

### 9. Reconciliation mit Vor-Audit und Issue-Inventar

| Vor-Befund | WP-1d-Ergebnis | Klassifikation |
|---|---|---|
| `CR-11` Datenverträge | **BESTAETIGT und verschärft**: 5 Fehler-Shapes, 432/439 Ops ohne Fehler-Schema, `COMMON_ERROR_RESPONSES` tote Deklaration, CSV/ReqIF stille Fehlschläge | BESTAETIGT |
| `CR-12` Source-of-Truth | **BESTAETIGT**: Live-Verhalten weicht an 5 Stellen vom Schema ab (Ingress, Root, Schema selbst, Import-Content-Type, Fehler-Schemata) | BESTAETIGT |
| `CR-13` Workspace-Sprachspaltung | **WIDERLEGT für den Tenant-Leak-Teil**: `?workspace_id=<fremd>` liefert konsequent `count: 0`, keine Sprache, kein Leak. Bleibt als Doku-/Konzeptthema bestehen, nicht als Security-Fund | WIDERLEGT (Security-Teil) |
| `CR-21` Doku-/Manifest-Drift | **BESTAETIGT + erweitert**: `AGENTS.md` APIView-Zahl 67 vs. real 76; `rest_api/urls.py:30-31` dokumentiert `/api/v1/schema/`, real auch unter `/api/schema/`; OpenAPI kennt 7 geroutete Pfade nicht | BESTAETIGT |
| `CR-26` Workspaceless Bearer / stale Rollen | **BLOCKED** — nicht reproduziert, weil der Test dauerhafte Rollenmutation an Tenant A erfordert hätte. Mechanik identisch zu `authentication.py:175-220` ungeprüft | BLOCKED |
| `CR-42` | **BESTAETIGT** (round-trip Datenintegration): CSV- und ReqIF-Round-Trip sind die konkrete Ausprägung | BESTAETIGT |
| `CR-14` | **BESTAETIGT** (Error-Mapping-Asymmetrie): `views.py:217` mappt `ValidationError`→400, während `import_service.py:300` alle Exceptions auf „rollback mit leerer Fehlerliste" abbildet — dieselbe Exception-Klasse, zwei völlig verschiedene Verträge | BESTAETIGT |
| `AUD-2026-09-030` CACHES ohne SOCKET_TIMEOUT | nicht Gegenstand dieses Abschnitts | — |
| `AUD-2026-09-031` Health prüft Cache nicht | nicht Gegenstand dieses Abschnitts | — |
| `AUD-2026-09-034` API-Key-Scope nur für Agent-Keys | **BESTAETIGT, verschärft**: `X-API-Key` mit `reqlo_`-Präfix wird auch auf REST-Endpunkten ausgewertet (401 `invalid_api_key` statt Ignorieren) — die im Schema dokumentierte Präzedenz greift, aber die Scope-Validierung selbst bleibt auf Agent-Keys beschränkt | BESTAETIGT |
| `AUD-2026-09-035` `ApiKey.tenant_id` dekorativ | **im Rahmen dieses Abschnitts nicht nachmessbar** (benötigt zwei Tenants + API-Key-Vergleich; mein B-Key war nach Löschung nicht mehr testbar). Der Tenant-A/B-Vergleich der Key-Liste zeigte **korrekte** Trennung | BLOCKED |
| `AUD-2026-09-036` `views.py:217` ValidationError→400 vs. MCP 500 | **BESTAETIGT und um einen weiteren Fall erweitert**: dieselbe Exception, drei Verträge — REST-View (400), `import_service` (leere Fehlerliste, `status: rollback`), MCP (500) | BESTAETIGT |
| Issue-Inventar (608 Issues) | vor jedem `NEU` durchsucht; keine Kollision mit bestehenden Nummern, Start bei `AUD-2026-09-070` | — |

---

### 10. Finding-Tabelle WP-1d

| ID | Schwere | Klassifikation | CR-Track / Issue | Ort | Kurztitel |
|---|---|---|---|---|---|
| `AUD-2026-09-070` | **Critical** | Correctness / Datenverlust-Versprechen | CR-11, CR-42, CR-12 | `application/import_service.py:196-232` ↔ `views.py:8085` | CSV-Round-Trip des eigenen Exporters unbrauchbar: `# terminology_profile`-Kommentarzeile wird als Header gelesen → **HTTP 201 `success:true` bei 0 importierten Zeilen** |
| `AUD-2026-09-071` | **Critical** | Correctness / stiller Fehlschlag | CR-11, CR-42 | `application/reqif_import_service.py:697`, `:681`, `:415` | ReqIF-Import liefert `success:true` mit 915 × „internal error"; Ursache `pl_artifact_pkey`-UniqueViolation, weil `SPEC-OBJECT/@IDENTIFIER` die globale `Artifact.id` ist |
| `AUD-2026-09-072` | **High** | Correctness / Datenintegrität | CR-11 | live `POST /workspaces/B/import/csv/` | CSV-Import **nicht idempotent**: dreifacher Import derselben Datei erzeugt 3 Duplikate; keine Duplikaterkennung |
| `AUD-2026-09-073` | **High** | Robustheit / Verfügbarkeit | CR-14 | live `GET /trace-links/?page=0\|abc\|99999999`, `GET /glossary/?page=0\|abc` | **HTTP 500** auf ungültiges `page` (5 Werte je Endpunkt), während `/workspaces/` korrekt 404 liefert |
| `AUD-2026-09-074` | **High** | DoS / Skalierung | CR-11 | `rest_api/api_key_views.py:81`, `user_management_views.py:81`, `link_type_views.py:90` | 4 Listen-Endpunkte ohne Pagination: `/api-keys/` (200 Items, 54 KB), `/users/`, `/link-type-defaults/`, `workspaces/{id}/link-type-definitions/`; `page`/`page_size` werden komplett ignoriert |
| `AUD-2026-09-075` | **High** | Contract / OpenAPI | CR-12, CR-21 | `rest_api/openapi.py:71-98`; `GET /api/schema/` | **432 von 439 Operationen deklarieren keinen Fehler-Fall**, 0 deklarieren 5xx; `COMMON_ERROR_RESPONSES` ist tote Deklaration (nirgends verwendet) |
| `AUD-2026-09-076` | **High** | Interoperabilität / Standard | CR-11, CR-42 | `application/reqif_export_service.py:296` | ReqIF-Export ist **nicht ReqIF-1.2-konform**: `REQ-IF-HEADER/@reqIFVersion` fehlt, `THE-VERSION` fehlt, 0 von 915 `SPEC-OBJECT` enthalten das Pflicht-Element `SPEC-OBJECT-CONTENT` |
| `AUD-2026-09-077` | **High** | Observability | CR-11 | `rest_api/error_envelope.py:48-68` | Fehlerhülle enthält **kein `trace_id`/`request_id`**, obwohl die App durchgängig eine `request_id` loggt — 500er sind für Clients nicht korrelierbar |
| `AUD-2026-09-078` | **High** | Contract / Content-Type | CR-12 | `views.py:8176-8216` (Export) vs. `ReqifImportView` | ReqIF-Import akzeptiert nur `multipart/form-data`; Export liefert `application/xml` — asymmetrisch und im OpenAPI-Schema **ohne** `requestBody` dokumentiert |
| `AUD-2026-09-079` | **Medium** | Correctness / Datenintegrität | CR-11 | live `POST /workspaces/B/import/csv/` | Enum-Validierung **inkonsistent**: ungültiger `status` wird still akzeptiert (201 success), ungültiger `type`/`level` dagegen mit 400 `status:"rollback"` und **leerer** `errors`-Liste quittiert |
| `AUD-2026-09-080` | **Medium** | Correctness / Datenintegrität | CR-11 | live, `import_service.py:196` | Kaputtes CSV-Quoting wird **still importiert** (201 success), Restzeile landet im Titel |
| `AUD-2026-09-081` | **Medium** | Authorisierung / Inkonsistenz | CR-12 | `views.py:8085` (`CsvExportView`), `views.py:7951` (`CsvImportView`), `settings_views.py:579` | Workspace-fremde Operationen ohne Tenant-Prüfung: CSV-Export liefert **200** (nur wegen RLS leer), CSV-Import **400 validation_error**, `review-policy` **200** — drei Geschwister, drei Verhaltensweisen |
| `AUD-2026-09-082` | **Medium** | Fehlerkonsistenz | CR-14, CR-11 | `link_type_views.py:31-43`, `baseline/views.py:101`, `mcp_server` | **5 Fehlerformate** über 3 Transportformen; `{"detail": …}`-Pfade umgehen `reqogniloom_exception_handler`; `error_envelope.py:8-9` behauptet ein gemeinsames Format, das es nicht gibt |
| `AUD-2026-09-083` | **Medium** | Correctness / Round-Trip | CR-42, CR-21 | live, `import_csv` | CSV-Import: BOM nicht erkannt, kein Delimiter-Sniffing, und beide Fälle werden mit `title is missing or empty` quittiert — die Meldung beschreibt die Daten statt der Ursache |
| `AUD-2026-09-084` | **Medium** | Dokumentation / Zählwerk | CR-21 | `AGENTS.md` (Projektbeschreibung + Besondere Patterns) | `AGENTS.md` nennt „67 APIViews", real **76**; „27 ViewSets" ist exakt korrekt (zählt man `BaseEntityViewSet` mit, kommt man auf die 28 des Auftrags) |
| `AUD-2026-09-085` | **Medium** | Contract / OpenAPI | CR-12 | `GET /api/schema/`, `reqogniloom/urls.py:35,51-52` | 7 geroutete Pfade fehlen im Schema, darunter der komplette MCP-Ingress (`/api/v1/mcp{,/sse,/messages}`), der DRF-API-Root und das Schema selbst |
| `AUD-2026-09-086` | **Medium** | Rendering / Datenverlust | CR-11 | `application/pdf_report_generator` (reportlab) | PDF-Report nutzt nur `Helvetica`/`Helvetica-Bold` mit `WinAnsiEncoding`, **ohne eingebetteten Font** — Emoji/CJK/Kyrillisch sind nicht darstellbar |
| `AUD-2026-09-087` | **Medium** | Interoperabilität | CR-11 | live `GET /workspaces/A/export/csv/`, `…/reports/pdf/` | CSV-Export ohne `charset=utf-8`; PDF-`Content-Disposition` mit `Zahnbürste…` ohne RFC-5987-`filename*` → Ersatzzeichen im Dateinamen bei Nicht-UTF-8-Clients |
| `AUD-2026-09-088` | **Low** | Contract / Auth-Konsistenz | CR-26 | live, `auth_tenancy/services/authentication.py` (Claim-Reihenfolge) | Fehlercode-Granularität: abgelaufen, `aud`-fremd, `iss`-fremd und unbekannter `user_id` sind **nicht unterscheidbar** (alle `invalid_signature`) |
| `AUD-2026-09-089` | **Low** | Contract / Auth | — | `rest_api/urls.py:263`, `reqogniloom/urls.py:51-52` | MCP-Server-Deskriptor auf `/mcp/` und `/api/v1/mcp/` **ohne Credential** öffentlich (Versions-Disclosure, MCP-Spec-konform) |
| `AUD-2026-09-090` | **Low** | Contract / Schema-Hygiene | CR-12 | `GET /api/schema/` → `components.securitySchemes.cookieAuth` | `cookieAuth` (`sessionid`) ist deklariert, wird aber von **keiner** Operation referenziert — toter Auth-Pfad im Schema |
| `AUD-2026-09-091` | **Low** | Contract / Schema-Hygiene | CR-12 | `GET /api/schema/` → `auth/login`, `auth/refresh`, `public/banners/login` | Öffentliche Endpunkte nutzen `security: [{BearerAuth: []}, {}]` statt des kanonischen `security: []` |
| `AUD-2026-09-092` | **Low** | Datenqualität | CR-42 | live: `GET /requirements/?workspace_id=A` | `uid` ist bei ~888 vorbestehenden Seed-Artefakten `null` → ReqIF-Export schreibt `ATTR-UID THE-VALUE=""`; Backfill-Lücke nach `#932/#1005` (nicht der `#1003`-Fix, der ist gemergt und wirksam) |
| `AUD-2026-09-093` | **Info** | Sicherheit | CR-13 | live: 6 Workspace-Endpunkte | Zwei 404-Texte unterscheiden „gehört fremdem Tenant" **nicht** von „existiert nicht" (`Workspace <id> not found.` vs. `… in the caller's tenant.`) — kein vollständiges Enumerations-Orakel, aber inkonsistent |

---

### 11. Ampel-Kurzfassung

| Bereich | Ampel | Begründung |
|---|---|---|
| Tenant-Isolation | **GRÜN** | 120 Cross-Tenant-Proben, 0 Leaks, RLS greift zusätzlich auf DB-Ebene. 3 Authorisierungs-Asymmetrien ohne Datenabfluss. |
| Auth / JWT | **GRÜN-GELB** | Saubere 401/403-Trennung, kein Info-Leak, kein Injection. Offen: Fehlercode-Granularität, `CR-26` nicht reproduziert. |
| Pagination | **GELB** | Deckelung und Echo sind vorbildlich, aber 4 Endpunkte ohne Pagination, `/api-keys/` liefert 200 Items, 500er auf `page=0`. |
| Filter / Ordering | **GRÜN** | Keine Injection, Ordering-Allow-List greift. Offen: unbekannte Filter still verworfen. |
| Fehlerkonsistenz | **ORANGE** | 5 Formate, keine `trace_id`, 98,4 % der Operationen ohne deklariertes Fehler-Schema. |
| OpenAPI-Abdeckung | **GELB** | Pfad-/Methoden-Deckung praktisch perfekt (0 in der einen, 7 in der anderen Richtung) — die Drift steckt in den Fehler-Schemata und im Import-`requestBody`. |
| ReqIF 1.2 | **ORANGE** | Round-Trip funktioniert nicht, Export ist nicht 1.2-konform, `uid` nur für Neuanlagen. |
| CSV-Import | **ROT** | Eigen-Round-Trip kaputt, nicht idempotent, stille Fehlschläge mit leerer Fehlerliste, kaputte Zeilen still importiert, BOM/Semikolon falsch diagnostiziert. |
| PDF-Export | **GELB** | Schnell und tenant-sicher, aber keine Unicode-Font und fehlende RFC-5987-Kodierung. |

---

### 12. Nicht geprüft (BLOCKED — ausdrücklich kein PASS)

1. **Auth mit korrekt signierten Token-Varianten** (`exp` abgelaufen, `aud` fremd,
   `iss` fremd). Hätte den echten `AUTH_JWT_SECRET` aus dem Container-Environment
   gebraucht. Ersatzweise nur strukturell-manipulierte Tokens getestet (falsche
   Signatur) → alle `invalid_signature`.
2. **Token eines deaktivierten Users** und **Token nach Rollenentzug** (`CR-26`).
   Beide hätten dauerhafte Rollen-/Statusmutationen an Tenant A oder einen länger
   lebenden Probe-Tenant gebraucht. Der Probe-User wurde nach dem Test gelöscht;
   die Sequenz wurde bewusst **nicht** gefahren.
3. **`AUD-2026-09-035` (`ApiKey.tenant_id` dekorativ)** nicht nachmessbar: der
   Klartext-Key von Tenant B war nach dem Anlegen nicht mehr abrufbar, ein
   `reqlo_`-Key für Tenant A existierte nicht.
4. **PDF-Timeout/Abbruchverhalten bei großen Datenmengen.** Nur 888 Requirements
   (0,75 s) und 1 Requirement gemessen. Ob ein Sync-Render bei >10 k Artefakten in
   einen Request-Abbruch oder Worker-Timeout läuft, ist **nicht** belegt. Der
   vorhandene asynchrone Pfad (`bundle-compression-status/`, `consistency-status/`)
   zeigt, dass das Muster im Projekt bekannt ist — der PDF-Pfad nutzt es nicht.
5. **`ordering=tenant_id` / `ordering=created_by__password`**: ob die Sortierung
   tatsächlich angewendet wird, wurde nicht verifiziert (nur der Statuscode 200).
6. **ReqIF-Import in denselben Tenant** (statt nur tenant-übergreifend). Der
   PK-Kollisions-Pfad, der den Import scheitern ließ, wird dadurch *nicht*
   ausgelöst — der echte Same-Tenant-Round-Trip ist damit **unbelegt**.
7. **Webhooks**: `/api/v1/webhooks/` existiert nicht als REST-Route (404). Die
   Zustellung (`as_webhook_delivery_log`, `as_webhook_subscription`) hat keinen
   REST-Adapter; ein Tenant-Leak über Webhooks war deshalb **nicht** testbar.
8. **`/admin/restore/`** wurde nur auf die Auth-Gate geprüft (401 ohne Token), nicht
   auf Tenant-Isolation im Restore-Pfad.
9. **MCP-Rate-Limiting / SSE-Reconnect** — nicht Gegenstand dieses Abschnitts.

---

### 13. Aufräumen (verifiziert)

Alle Testdaten wurden entfernt und die Entfernung geprüft.

| Prüfung | Ergebnis |
|---|---|
| Tenant-B-User `wp1d_probe_b` | gelöscht (`pl_user` 13 → 12) |
| Tenant-B-`at_user_role` | gelöscht (412 → 411) |
| Tenant-B-Artefakte (19) + Unterobjekte + UID-Sequenzen + Preset-Config | gelöscht |
| Tenant-B-Workspace | gelöscht |
| Tenant-B-Login | 401 (nicht mehr möglich) |
| Tenant-A `pl_requirement` | **2111 → 2111** unverändert |
| Tenant-A `pl_artifact` | **3432 → 3432** unverändert |
| Tenant-A `pl_testcase` / `as_issue` / `as_risk` / `pl_tracelink` | 225 / 76 / 59 / 2099 — alle unverändert |
| Probe-Reste in Tenant A (9 Entitätstypen, Titelpräfix `WP1D`/`RTQ-`/`RT-CSV`) | **0** |
| **Rest** | 32 `audit_entry`-Zeilen + 1 `pl_tenant`-Zeile für Tenant B |

`audit_entry` hat einen **append-only DB-Trigger** — ein `DELETE` scheitert mit
`InternalError`. Das ist das korrekte Verhalten (Auftragshinweis), kein Restfehler.
Weil `AuditEntry.tenant` `on_delete=PROTECT` ist, bleibt die `pl_tenant`-Zeile als
Referenz für den Audit-Trail stehen. Sie ist funktional inert (kein User, keine
Daten, kein Login). Nebenbewegung, die **nicht** von diesem Audit stammt:
`at_refresh_token` +17, `as_domain_event_outbox` +8, `sm_metric_cache` +1 — normale
Churn aus meinen ~90 eigenen Logins.

Beleg: `wp1d-cleanup-verification.md`.
