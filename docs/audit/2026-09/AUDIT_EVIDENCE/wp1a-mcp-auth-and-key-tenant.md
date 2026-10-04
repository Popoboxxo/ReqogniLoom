---
type: REVIEW
scope: wp-1a-mcp-server-auth-and-key-tenant
status: final
date: 2026-09-29
author_agent: senior-developer
---

# WP-1a Evidence — Auth-Pfade und API-Key-Tenant-Bindung

## 1. Zwei Routen, identische Auth

`backend/reqogniloom/urls.py:51` mountet dieselbe URLConf doppelt:

```python
path("api/v1/mcp/", include("mcp_server.urls")),   # urls.py:51
# + mcp_server/urls.py unter /mcp/
```

Gemessen (beide Header-Varianten, beide Pfade):

| Pfad | `X-API-Key` | `Authorization: Bearer <key>` | `tools/list` |
|---|---|---|---|
| `POST /mcp/` | 200 / 80 Tools | 200 / 80 Tools | identisch |
| `POST /api/v1/mcp/` | 200 / 80 Tools | 200 / 80 Tools | identisch |

**Keine Auth-Divergenz zwischen den beiden Pfaden** — das ist ein PASS. Ein
kosmetischer Unterschied bleibt: nicht existierende Subpfade antworten unter
`/mcp/` mit Djangos HTML-404-Seite, unter `/api/v1/mcp/` mit dem DRF-JSON-404
(`{"error":{"code":"NOT_FOUND",...}}`). Info, kein Sicherheitsbefund.

## 2. Auth-Matrix (live, `tools/list`)

| Fall | HTTP | Body / Befund |
|---|---|---|
| kein Header | 401 | `code -32000` „API key is required. Provide X-API-Key header or **params.api_key**." |
| leerer `X-API-Key` | 401 | identisch |
| ungültiger Key | 401 | `Authentication failed: invalid_api_key` |
| falsches Präfix `reqk_` | 401 | `Authentication failed: bearer_not_supported — MCP requires an API key (X-API-Key …)` |
| Key abgeschnitten | 401 | `invalid_api_key` |
| Key + 1 Zeichen | 401 | `invalid_api_key` |
| Key kleingeschrieben | 401 | `invalid_api_key` |
| `Authorization: Bearer <gültiger API-Key>` | **200** | **funktioniert** |
| `Authorization: Bearer` (leer) | 401 | „API key is required" |
| `Authorization: Basic <key>` | 401 | „API key is required" |
| `Authorization: <key>` ohne Schema | 401 | „API key is required" |
| `Authorization: Bearer <JWT>` | 401 | `bearer_not_supported` |
| `params.api_key` nur im Body | 401 | „API key is required" |
| `?api_key=` Query-String | 401 | „API key is required" |
| nur `Cookie: reqogniloom_access=…`, kein Key | **403** | `error_code: UNAUTHORIZED` („headers only") |
| Cookie **+** Key | 200 | CSRF-Prämisse korrekt: 200, kein 403 |

### Befund A — self-contradicting auth error message (Medium)

`Authorization: Bearer <gültiger API-Key>` antwortet **200**. Sendet man
dasselbe Token mit einem abgeschnittenen Key oder als JWT, lautet die Meldung:

```
Authentication failed: bearer_not_supported — MCP requires an API key (X-API-Key …)
```

Der interne Fehlercode `bearer_not_supported` ist damit **falsch** (Bearer *ist*
supportet) und wird einem unauthentifizierten Aufrufer offengelegt. Ort:
`auth_tenancy/services/authentication.py` (Pfad, der `bearer_not_supported`
setzt) + `backend/mcp_server/protocol_handler.py:264` (Message-Weitergabe).

### Befund B — Bearer-JWT-Ablehnung ist by design, aber nicht dokumentiert

`Authorization: Bearer <JWT>` ⇒ 401. Das ist **konsistent** und beabsichtigt
(`protocol_handler.py:331-333` extrahiert `Bearer` als Key-Quelle; nur
`reqlo_*`-Keys validieren). Der Fehlerhinweis nennt den Grund aber nicht
verständlich und `docs/api/MCP-SURFACE.md` beschreibt den Auth-Vertrag nicht
explizit. Info/Low.

### Befund C — API-Key erscheint im Access-Log (Medium)

Der Grund, warum Query-String-Keys abgelehnt werden, ist im Code dokumentiert
(`protocol_handler.py:320-328`, `views.py:176-190`: *„query strings are
routinely written to proxy and web-server access logs … which would leak
long-lived `reqlo_*` API keys"*). Genau dieser Log-Eintrag entsteht aber, wenn
ein Client den Key trotzdem in die URL schreibt:

```
INFO:  172.18.0.1:35000 - "POST /mcp/?api_key=reqlo_***MASKED*** HTTP/1.1" 401 Unauthorized
```

Die App lehnt den Key korrekt ab (401) — aber das Geheimnis steht danach im
Access-Log. Es gibt **keine Redaction** von `reqlo_*` auf ASGI-/uvicorn- oder
Django-Logebene. Die Begründung „wir lehnen Query-Keys ab, damit sie nicht im
Log landen" ist damit unvollständig: die App verhindert nur die *Auswertung*,
nicht die *Aufzeichnung*. Verwandt mit **CR-28** (Session-ID als URL-Bearer,
8-h-TTL, Log-Redaction offen) — dort steht derselbe Mechanismus für die
Session-ID; dieser Beleg ist der API-Key-Pendant davon.

## 3. `ApiKey.tenant_id` ist nicht die maßgebliche Tenant-Bindung (High)

Gemessen in einem Container-Skript gegen `AuthenticationService`:

```
ApiKey row  : name=wp1a-tenantb  tenant_id=ef3b8a80-bd76-4889-a6ac-9676bcd85909
claims      : tenant_id=7a539397-6719-47bb-a6d5-5459016136fb
owner User  : tenant_id=7a539397-6719-47bb-a6d5-5459016136fb  (e2e-user-1789804477653)
>> claims.tenant == ApiKey.tenant_id ?  False
>> claims.tenant == OWNER.tenant_id   ?  True
```

`validate_api_key()` leitet den Tenant **aus dem Besitzer-User** ab, nicht aus
`ApiKey.tenant_id`. Ein per `create_api_key(user_id=<User in Tenant A>,
tenant_id=<Tenant B>)` erzeugter Key wird ohne Fehlermeldung persistiert und
operiert danach vollständig in Tenant A. Die Key-Zeile ist unter der RLS-Sicht
ihres *eigenen* Tenants unsichtbar, unter dem des Owners sichtbar.

Konsequenz: `ApiKey.tenant_id` ist dekorativ. Der REST-Pfad
(`rest_api/api_key_views.py:290`, `normalize_api_key_scope`/Tenant-Ableitung)
sichert das nicht ab — nur der Scope wird normalisiert, nicht die
Tenant-Konsistenz. **Kein Cross-Tenant-Leak** (die Isolation greift immer über
den Owner-Tenant), aber ein Integritäts- und Governance-Befund: die
Key-Metadaten können einen anderen Tenant ausweisen als den wirksamen.

## 4. `create_api_key` validiert den Scope nur für Agent-Keys (Medium)

`auth_tenancy/services/authentication.py:613-623`:

```python
if principal_type not in (PRINCIPAL_TYPE_USER, PRINCIPAL_TYPE_AGENT):
    raise ValueError(...)
effective_scope = "write" if scope is None else scope          # <- ungeprüft
if principal_type == PRINCIPAL_TYPE_AGENT:
    normalized_scope = normalize_api_key_scope(scope)
    if normalized_scope is None:
        raise ValueError("Agent API keys require an explicit valid scope.")
```

Gemessen — alle drei wurden für einen **User**-Key akzeptiert und persistiert:

| `scope` | Ergebnis |
|---|---|
| `"admin"` | angelegt, funktioniert (219 Tools) |
| `"readwrite"` | angelegt, **stumm schreibunfähig** |
| `""` (leerer String) | angelegt, **stumm schreibunfähig** |
| `"readwrite"` als **Agent**-Key | abgelehnt (`ValueError`) |

Der `ApiKey.scope`-Feldbereich hat `choices=API_KEY_SCOPE_CHOICES`
(`auth_tenancy/models.py:155-156`) — das greift aber nur bei
`full_clean()`/DRF-Serializern, nicht bei einem direkten ORM-Insert aus der
Service-API. Folge für den Betreiber: ein Key, der wie ein Vollzugriff-Key
aussieht, kann faktisch **keinen einzigen Write** ausführen. Die Fehlermeldung
dafür ist immerhin eindeutig:

```
API key scope 'readwrite' is not recognised; this credential may perform no
operation. Re-issue the key with scope 'read_only', 'author' or 'admin'.
```

## 5. CORS

`OPTIONS` mit `Origin: http://evil.example.com` auf allen drei MCP-Endpunkten:

```
/mcp/            200  access-control-allow-methods: POST, GET, OPTIONS
                      access-control-allow-headers: Content-Type, Authorization, X-API-Key
                      (KEIN access-control-allow-origin, KEIN allow-credentials)
/mcp/sse/        200  access-control-allow-methods: GET, OPTIONS   (dito)
/mcp/messages/   200  access-control-allow-methods: POST, GET, OPTIONS (dito)
```

Korrekt: ein nicht-allowlisteter Origin wird **nicht** reflektiert, und
`Access-Control-Allow-Credentials` fehlt. `views.py:215-230` erzwingt das
explizit (REQ-081). PASS.

Randnotiz: `Vary: Accept-Language` (LocaleMiddleware) ist auf allen MCP-Responses
gesetzt. `Vary: Origin` wird nur für allowlistete Origins ergänzt — für diese
Antworten also korrekt nicht. Kein Befund.

## 6. GET /mcp/ ist unauthentifiziert

```
GET /mcp/ (kein Key) -> 200 {"server":"ReqogniLoom MCP Server","protocol":"JSON-RPC 2.0",
                             "transports":["http","sse"],"version":"1.0.0"}
```

Bewusst als Discovery-Endpoint (kommentiert in `views.py:387-435`), nur
per-IP ratelimited. Enthält keine Tenants, Workspaces oder Tool-Namen. Info.

## Nicht ausgeführt

* **Abgelaufener / revokierter Key** — `expires_at`/`is_active` auf einem
  API-Key konnte nicht gezielt getestet werden, weil der Klartext nur einmal
  bei Erzeugung verfügbar ist und `at_api_key` nur `key_hash` speichert
  (`stack-seeds.md` §5). Ein Key mit `expires_at` in der Vergangenheit wäre
  nötig gewesen; `create_api_key` erzwingt für Agent-Keys ein **zukünftiges**
  `expires_at`, für User-Keys nicht. Klassifiziert als **BLOCKED** (nicht als PASS).
* **Rate-Limit-Auslösung** (`MCP_RATE_LIMIT_KEY`, `MCP_RATE_LIMIT_IP`) —
  nicht ausgelöst, um keinen laufenden Audit-Agenten zu blockieren.
