---
type: REVIEW
scope: wp-1a-mcp-server-tool-count-drift
status: final
date: 2026-09-29
author_agent: senior-developer
---

# WP-1a Evidence — Tool-Count-Drift (Issue #1104) — Auflösung

**Status: aufgelöst. Es gibt KEINEN Registrierungsfehler. 219/35 ist die Wahrheit.
Die 80 aus `tools/list` sind ein korrekter RBAC-/Scope-Filter.**

Alle Zahlen unten sind gemessen, nicht abgeschrieben:

| Quelle | Befehl | Ergebnis |
|---|---|---|
| Registry (offline, ungefiltert) | `python manage.py export_tool_manifest --out /tmp/wp1a-manifest.json` | **219 Tools / 35 Präfixe** |
| Committetes Manifest | `docs/agent-templates/tool-manifest.json` | `tool_count = 219`, `len(tools) = 219` |
| Registry ↔ Manifest | Namensmenge | **identisch** (0 fehlend, 0 stale) |
| Registry ↔ Manifest | Feldweise (`is_write`, `prefix`, `description`, `inputSchema`) | **0 Abweichungen** |
| `tools/list` mit `scope=admin`-Key | live `POST /mcp/` | **219 Tools / 35 Präfixe** |
| `tools/list` mit `scope=readwrite`-Key (der Key aus `stack-seeds.md`) | live `POST /mcp/` | **80 Tools / 34 Präfixe** |
| Schnittmenge der beiden Kataloge | | 80 ⊂ 219, `len(A ∩ B) = 80` |

## Der Mechanismus

`ToolRegistry.list_tools` filtert zweimal (`backend/mcp_server/tool_registry.py:1038-1064`):

```python
can_write = scope_allows(auth_ctx.scope, Operation.WRITE) \
            and self._authz_service.decide_access(roles, Operation.WRITE).allow
...
if not can_write:
    tools = [t for t in tools
             if not self._is_write_tool(t.get("name", ""))
             or self._is_tenant_admin_exempt(t.get("name", ""), auth_ctx)]
if not can_govern:
    tools = [t for t in tools
             if self._required_scope_operation(t.get("name", "")) is not Operation.WORKSPACE_CONFIG]
```

Gemessen für beide Keys (derselbe User `7298a00b-…`, derselbe Tenant `7a539397-…`):

| `is_write` | versteckt (139) | angeboten (80) |
|---|---|---|
| `true` | **139** | 0 |
| `false` | 0 | **80** |

→ Die 139 verborgenen Tools sind **exakt** die 139 `is_write=true`-Tools; die 80
angebotenen sind **exakt** die 80 `is_write=false`-Tools. Kein einziger
Read-Tool fehlt, kein einziger Write-Tool ist sichtbar. **Kein Registrierungsfehler.**

Zusätzlichbeweis, dass das angebotene Menü wirklich ausführbar ist
(Invariant „advertised surface matches executable surface",
`tool_registry.py:975-978`): `requirement.create`, `glossary.create` und
`baseline.create` mit dem `admin`-Key erreichen den Handler
(`glossary.create` legte real eine Zeile an); mit dem `readwrite`-Key antworten
dieselben Calls:

```
HTTP 403  {"code": -32001, "message": "API key scope 'readwrite' is not
 recognised; this credential may perform no operation. Re-issue the key with
 scope 'read_only', 'author' or 'admin'."}
```

## Warum genau dieser Key 80 sieht

`auth_tenancy/services/authorization.py:78-97` kennt nur die Tiers
`read_only`/`read` (0), `author` (1), `admin`/`write` (2). Der in
`docs/audit/2026-09/AUDIT_EVIDENCE/stack-seeds.md` dokumentierte Audit-Key
wurde mit `scope="readwrite"` erzeugt — ein **nicht anerkanntes Tier**.
`_UNKNOWN_SCOPE_TIER = -1` ⇒ `scope_allows` ⇒ `False` ⇒ `can_write = False` ⇒
alle 139 Write-Tools ausgefiltert. Zusätzlich fällt der ganze Namespace
`ai_derivation` (6 Tools, alle Write) weg — deshalb 34 statt 35 Präfixe.

Das ist kein Produktfehler an der Filterlogik, sondern ein **Fehler im
Test-Credential**. Er ist reproduzierbar: `create_api_key(..., scope="readwrite")`
wird für `principal_type="user"` ohne Validierung persistiert
(`auth_tenancy/services/authentication.py:616`) — siehe
[wp1a-mcp-auth-and-key-tenant.md](wp1a-mcp-auth-and-key-tenant.md).

## Was tatsächlich driftet

| Ort | Behauptung | Ist | Status |
|---|---|---|---|
| `README.md:77`, `README.md:114` | 35 Präfixe / 219 Tools | 35 / 219 | **korrekt** |
| `docs/api/MCP-SURFACE.md:26-27,100` | 219 / 35 | 219 / 35 | **korrekt** |
| `docs/api/MCP-SURFACE.md:39` | „215 — wrong" | korrekt als falsch markiert | **korrekt** |
| `AGENTS.md:8` | 31 Präfixe, 215 Tools | 35 / 219 | **DRIFT** (CR-21) |
| `AGENTS.md:30` | 31 Tool-Gruppen-Präfixe, 215 Tools | 35 / 219 | **DRIFT** (CR-21) |
| `AGENTS.md:58` | 31 Tool-Gruppen-Präfixe | 35 | **DRIFT** (CR-21) |
| `README.md:1191` | „Tool Groups (25 prefixes)" | 35 | **DRIFT**, **interne README-Widersprüchlichkeit** (Zeile 77 vs. 1191) |
| `README.md:482`, `:1060`, `:1072` | `"transports":["http","sse","stdio"]` | live `["http","sse"]` | **DRIFT / Phantom** (CR-21) |
| `README.md:1163`, `:1182` | Config-URL `http://localhost:8000/mcp/stdio/` | Route existiert nicht (404) | **DRIFT / Phantom** (CR-21) |
| `README.md:1291` | „JSON-RPC 2.0 (HTTP, SSE, stdio)" | stdio nicht HTTP-routbar | **DRIFT** (CR-21) |
| `docs/api/MCP-SURFACE.md:48-50` | „needs a key whose user has write + governance capability" | korrekt, aber der Hinweis ist der einzige Ort, der die 80er-Zahl erklärt | korrekt |

Live-Belege:

```
GET /mcp/ -> 200 {"server":"ReqogniLoom MCP Server","protocol":"JSON-RPC 2.0",
                 "transports":["http","sse"],"version":"1.0.0"}
GET /mcp/stdio/        -> 404 (Django-HTML-404)
GET /api/v1/mcp/stdio/ -> 404 (DRF-JSON-404)
```

**Antwort auf die offene Frage:** 80 ist rollen-/scopebedingt gefiltert und damit
**kein Drift**; der Drift liegt ausschließlich in `AGENTS.md` (215/31) und in
den README-Transport-/Präfix-Behauptungen. `README.md:77/114` und
`docs/api/MCP-SURFACE.md` sind korrekt. Issue **#1104** sollte entsprechend
auf „Doku-Drift in `AGENTS.md` + README-Transportbehauptungen" verengt und mit
`CR-21` zusammengeführt werden.

## Guard-Status

`backend/mcp_server/tests/test_tool_manifest_drift.py` wurde **nicht** über
pytest ausgeführt (Grund: [CR-30](#nicht-ausführbarkeit-im-laufenden-stack)),
sondern durch eine 1:1-Nachbildung seiner Assertions gegen
`build_manifest()` — plus **12 Mutationstests**. Alle 12 verhielten sich wie
spezifiziert:

| # | Mutation | Erwartet | Ergebnis |
|---|---|---|---|
| M1 | falsche `description` bei 1 Tool | FAIL | CAUGHT (`description`) |
| M2 | `is_write` auf Write-Tool geflippt | FAIL | CAUGHT (`is_write`) |
| M3 | `is_write` auf Read-Tool geflippt | FAIL | CAUGHT (`is_write`) |
| M4 | zusätzlicher `required`-Param in `inputSchema` | FAIL | CAUGHT (`inputSchema`) |
| M5 | Property-Typ in `inputSchema` geändert | FAIL | CAUGHT (`inputSchema`) |
| M6 | falscher `prefix` | FAIL | CAUGHT (`prefix`) |
| M7 | Tool aus dem Manifest gelöscht | FAIL | CAUGHT (`missing=1`) |
| M8 | Tool dupliziert | FAIL | CAUGHT (`tool_count 219 != 220`) |
| M9 | nur `tool_count` veraltet (215) | FAIL | CAUGHT (`tool_count 215 != 219`) |
| M10 | zwei `description` vertauscht | FAIL | CAUGHT (`drifted=2`) |
| M11 | leere `description` | FAIL | CAUGHT (`description`) |
| M12 | nur `inputSchema`-Schlüsselreihenfolge | PASS | PASS (kosmetisch ignoriert) |

**Mutation Score 12/12.** Der Guard erkennt eine absichtlich eingefügte falsche
Tool-Beschreibung — die im Task geforderte Mutationsprobe ist damit positiv
beantwortet. Rohdaten: `wp1a-mcp-registry-manifest-219.json`,
Mutationstabelle im Hauptbericht.
