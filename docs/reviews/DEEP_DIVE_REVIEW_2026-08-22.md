# Deep-Dive Code Review — ReqogniLoom (2026-08-22)

**Umfang:** Backend (Layer 0–3), REST API, MCP Server, Frontend (React/TS)
**Methode:** Manuelle Quellcode-Analyse im Chat (keine Delegation). Jedes Finding ist mit
Datei:Zeile belegt und begründet.
**Bewertungsskala:** 🔴 Hoch / 🟠 Mittel / 🟡 Niedrig / ⚪ Hinweis

---

## Zusammenfassung

Der Code ist insgesamt auf ungewöhnlich hohem Niveau: Security-Entscheidungen sind
begründet und nachvollziehbar dokumentiert (JWT, Cookies, Throttling, RLS), die
Test-Abdeckung der kritischen Pfade ist umfangreich. Die Findings konzentrieren sich
auf drei Cluster:

1. **Toter/broken Code in `persistence/managers.py`** (Finding B-1, 🔴)
2. **Inkonsistente Fehlerbehandlung**: `str(exc)`-Leaks an Clients in REST, während MCP maskiert (B-2, M-3)
3. **Fail-open vs. fail-closed-Inkonsistenzen** in den MCP-Gates (M-2)

---

## A. Positivbefunde (ausdrücklich verifiziert)

| # | Bereich | Beleg |
|---|---------|-------|
| A-1 | JWT-Verifikation: nur HS256 (alg-pinning, `none` abgelehnt), konstante Zeit via `hmac.compare_digest`, `exp` zwingend, `nbf` geprüft | `backend/auth_tenancy/jwt_tokens.py:96-125` |
| A-2 | Refresh-Tokens strikt von Access-Tokens getrennt (`typ="refresh"` darf nicht authentifizieren und umgekehrt) | `authentication.py:130-131, 182-183` |
| A-3 | Login-Throttle zählt nur **fehlversuche**, keyed per (IP, Username)-Pair + separater IP-Spray-Zähler; Erfolgslogin resettet nur den Pair-Bucket — durchdachter Anti-Lockout-/Anti-Spray-Kompromiss | `backend/rest_api/throttling.py:24-41, 146-205` |
| A-4 | httpOnly-Cookie-Auth + CSRF + SameSite=Lax; Token landet nie im JS-Storage des SPA (XSS-Vektor geschlossen) | `auth_views.py:61-97`, `frontend/src/context/AuthContext.tsx:7-14` |
| A-5 | RLS-Doppelschicht (Thread-local Filter + `SET app.current_tenant`) mit sauber begründeter `SET`/`RESET`-Paarung inkl. dokumentierter Versagensgrenzen (#522) | `persistence/middleware.py:34-73` |
| A-6 | MCP-Write-Gate ist fail-closed: unbekannte Tool-Namen gelten als WRITE und werden RBAC-geprüft (#99-Fix) | `mcp_server/tool_registry.py:174-265, 838-853` |
| A-7 | Mermaid-Preview wird vor `dangerouslySetInnerHTML` sanitisiert (`foreignObject` entfernt) | `frontend/src/components/mermaid/MermaidEditor.tsx:297, 428` |
| A-8 | Frontend-API-Client: Single-Flight-Refresh, Request-Timeouts (30s/180s), CSRF-Header, 401≠403-Semantik | `frontend/src/api/client.ts:82-119, 278-334` |
| A-9 | DEBUG ist in Produktion hart ausgeschaltet (`DJANGO_ENV`-Gate), APPEND_SLASH=False gegen POST-Body-Verlust/CWE-200 | `settings.py:60-101` |

---

## B. Backend — Persistence & Tenancy

### B-1 🔴 Totes Modul mit kaputtem Import und Laufzeitfehler: `persistence/managers.py`

**Befund:** Das Modul ist in diesem Zustand nicht importierbar und enthält zusätzlich einen zweiten, unabhängigen Defekt.

1. **Kaputter Import:** `managers.py:18` → `from persistence.base import TenantManager`.
   `backend/persistence/base.py` existiert nicht (verifiziert per Glob); `TenantManager`
   lebt in `backend/persistence/tenancy.py:117`. Jeder Import des Moduls würde mit
   `ModuleNotFoundError` crashen.
2. **Laufzeitfehler im CTE-Code:** `ArchitectureElementQuerySet.get_with_level()`
   übergibt `OuterRef('tenant_id')`-Objekte als RawSQL-Params (`managers.py:103`).
   Django kompiliert RawSQL-Params nicht — sie gehen 1:1 an den DB-Cursor; ein
   `OuterRef`-Objekt würde zur Ausführungszeit mit „cannot adapt type" fehlschlagen.
   Korrekt wäre eine Korrelation über `pl_architecture_element.tenant_id` direkt im SQL.
3. **Nie verdrahtet:** `ArchitectureElement` nutzt den plain `TenantManager`
   (`models.py`, `objects = TenantManager()`); `ArchitectureElementManager` wird
   nirgends importiert (verifiziert per Repo-Grep).
4. **Irreführende Doku:** Mehrere Stellen behaupten, der CTE-Manager existiere:
   `models.py:980` („manager.get_with_level()"), `serializers.py:681`,
   `views.py:3753`. Auch `trace_link_service.py:947` räumt ein, dass `get_with_level`
   „dead code" war — das Modul selbst wurde aber nie entfernt.

**Begründung Schwere 🔴:** Dead Code mit kaputtem Import ist kein kosmetisches Problem,
sondern eine Falle: Der nächste Entwickler, der `get_with_level()` laut Docstring
nutzt, zieht sich einen Import-Crash bzw. einen Laufzeitfehler in Produktion. Zudem
widersprechen vier Dokumentationsstellen dem tatsächlichen Code.

**Empfehlung:** Modul löschen oder reparieren (Import auf
`persistence.tenancy.TenantManager`, SQL-Korrelation fixen, Manager in `models.py`
verdrahten) und die drei irreführenden Docstring-Stellen korrigieren.

### B-2 🟡 `ApiKey.unscoped`-Lookups korrekt, aber `validate_api_key` macht einen no-op Compare

**Befund:** `backend/auth_tenancy/services/authentication.py:245`:
`hmac.compare_digest(computed_hash, computed_hash)` — vergleicht denselben Wert mit
sich selbst. Das ist ein bewusster Timing-Padding-No-op, aber funktional wirkungslos
(der Kommentar suggeriert sonst).

**Begründung:** Reiner Klarheits-Finding; kein Sicherheitsdefekt, da der eigentliche
Lookup über den Hash-Index erfolgt und der zweite Compare (:249) echt ist.

---

## C. REST API (Layer 3)

### C-1 🟠 Systemisches Info-Leak: `str(exc)` in 500er-Antworten

**Befund:** Viele Views antworten auf unerwartete Exceptions mit der rohen
Exception-Message an den Client:

- `rest_api/diagram_canvas_views.py:188, 267, 345, 406, 484, 545` —
  `build_error_response("INTERNAL_SERVER_ERROR", lang, message=str(exc))`
- `rest_api/audit_views.py:241`
- weitere Treffer in `diagram_views.py:148, 221, 251`

**Begründung:** Eine interne Exception (z. B. `psycopg2.errors.*`, Pfadangaben,
Stackdetails aus Library-Messages) fliegt so ungefiltert zum Client — klassischer
CWE-209 (Information Exposure Through Error Messages). Inkonsistent zum eigenen
Standard: Die MCP-Schicht maskiert bewusst („An internal error occurred.",
`tool_registry.py:706`) und auch `error_envelope.py` normiert Fehler. Das
Logging (`logger.exception`) ist jeweils vorhanden — der Leak ist vermeidbar.

**Empfehlung:** Interne Message nur loggen; dem Client generisch
„Internal server error." liefern (wie MCP). Ggf. zentral im Envelope/View-Mixin lösen.

### C-2 🟡 Direkte ORM-Imports in Views (Konventionsverstoß)

**Befund:** `diagram_canvas_views.py:43`, `diagram_views.py:49`, `icd_views.py:51`
importieren `from persistence.models import Tenant, User` und queryen direkt
(`_resolve_tenant`, `_resolve_user`).

**Begründung:** AGENTS.md-Konvention: „Keine direkten Model-Queries in DRF-Views
(immer via Serializer + Service)". Es sind nur Identitäts-Lookups für Service-Aufrufe
— geringes Risiko, aber es etabliert ein Muster, das die Layer-Grenze (ADR-01:
application/ als einzige Fassade) erodiert.

### C-3 🟡 Login liefert den Bearer-Token weiterhin im Response-Body

**Befund:** `auth_views.py:188-201` gibt `token` im Body zurück (dokumentiert als
Backward-Compatibility für E2E/API-Tooling; SPA ignoriert ihn).

**Begründung:** Solange nur Tools ihn nutzen, unkritisch — aber jeder künftige
Aufrufer, der ihn in JS speichert, reaktiviert exakt den XSS-Vektor, den REQ-052
geschlossen hat. Empfehlung: langfristig entfernen oder per Flag deaktivierbar machen.

### C-4 ⚪ Öffentliche Schema-Endpunkte

`/api/v1/schema/` und Swagger-UI sind ohne Auth erreichbar (`urls.py:498-508`,
`settings.py:451`). Explizit dokumentierte Entscheidung (REQ-L3-RA005-001); in
streng geschützten Deployments sollte das per Env abschaltbar sein.

---

## D. MCP Server

### D-1 🟠 API-Key wird weiterhin über `params.api_key` akzeptiert

**Befund:** `protocol_handler.py:250-267`: Priorität 3 der Key-Extraktion ist
`params.api_key` („all transports"). Gleichzeitig lehnt dasselbe System den
Query-Parameter-Fallback bewusst ab, weil Keys in Logs landen
(`views.py:82-91`, REQ-018 / SYSTEM_AUDIT P-05).

**Begründung:** JSON-RPC-Body-Parameter werden von MCP-Clients, Debug-Proxies und
Tracing-Frameworks häufig mitgeloggt — dieselbe Leckklasse wie Query-Strings.
Die Mitigation (`clean_params` strippt den Key vor dem Dispatch,
`protocol_handler.py:462`) schützt nur die Weitergabe, nicht die Loggbarkeit des
eingehenden Frames. Die eigene Audit-Policy wird hier inkonsistent angewendet.

**Empfehlung:** `params.api_key` nur für den stdio-Transport zulassen (dort gibt es
keine Header); HTTP/SSE strikt header-only.

### D-2 🟡 Preset-Gate ist fail-open

**Befund:** `tool_registry.py:910-913`: Schlägt der Preset-Lookup fehl, wird der
Call erlaubt (Kommentar: „fail-open for preset; auth is the hard gate").

**Begründung:** Für die RBAC-Gate gilt seit #99 bewusst fail-closed; das
Feature-Gate (`FEATURE_NOT_ENABLED`, ADR-04 Rigor-Presets) dagegen fail-open.
Ein DB/Ausnahmefehler deaktiviert damit stillschweigend die Preset-Politik
(z. B. LLM-Features in einem minimal-Workspace plötzlich aufrufbar — mit
Kostenfolge bei LLM-Calls). Mindestens sollte der Fail-open geloggt werden
(war: nur `logger.debug`) oder per TTL-Cache der letzte bekannte Stand genutzt werden.

### D-3 🟡 Unerwartete Auth-Exceptions geben `str(exc)` an den Client

**Befund:** `tool_registry.py:748-750`: Im `except Exception`-Zweig von
`_validate_api_key` wird `str(exc)` als Fehlermeldung zurückgegeben und landet im
JSON-RPC-Error beim Aufrufer.

**Begründung:** Gleiche CWE-209-Klasse wie C-1; besonders unschön, weil die
Nachricht unter `AUTH_FAILED` läuft und damit authentifizierte Infrastrukturdetails
(DSN-Fragmente etc.) preisgeben kann. Maskieren wie in Step 6 (`tool_registry.py:706`).

### D-4 🟡 CORS-Fallback spiegelt ersten Allowlist-Origin an jeden Origin

**Befund:** `views.py:116-119`: Wenn der Request-Origin nicht auf der Allowlist
steht, wird trotzdem `Access-Control-Allow-Origin: <erste konfigurierte Origin>`
gesetzt statt den Header zu omitieren.

**Begründung:** Kein direkter Exploit (der Browser blockt credentialed Reads, weil
der gespiegelte Origin ≠ Anfragen-Origin), aber semantisch falsch: Ein Nicht-Browser-
oder Same-origin-Client erhält irreleitende CORS-Metadaten, und bei mehreren
Allowlist-Einträgen wird willkürlich der erste exportiert. Korrekt: Header weglassen.

### D-5 ⚪ SSE-Session-Binding: nicht-konstanter Vergleich + stilles Speicher-Versagen

- `views.py:487`: `bound_key == api_key` statt `hmac.compare_digest`. Impact gering
  (Session-IDs sind UUIDs, der Key wurde bereits valide authentifiziert), aber der
  Codebase-Standard ist sonst konstante Zeit.
- `sse_pubsub.py:94-95`: `store_session_api_key` verschluckt Redis-Fehler — der
  Client bekommt eine Session-ID, die dann zwangsläufig mit SESSION_EXPIRED endet.
  Zumindest Warn-Log ist vorhanden; besser: Session-Erzeugung fehlschlagen lassen.

### D-6 ⚪ Executor-Threads ohne Connection-Hygiene

**Befund:** `views.py:59-62, 403-420`: Der gebundene ThreadPoolExecutor (10 Threads)
führt kompletten ORM-Code aus, ohne `django.db.close_old_connections()`.

**Begründung:** Django verwaltet Connections pro Thread und räumt nur über
Request-Signale auf. Langlebige Pool-Threads halten Connections unbegrenzt offen;
nach einem Postgres-Restart bedienen sie stale Connections. Durch das harte Limit
von 10 Threads begrenztes Risiko — Standardfix ist ein `close_old_connections`
am Anfang/Ende von `_process`.

### D-7 ⚪ Kleinigkeiten

- `views.py:260`: GET `/mcp/` advertised `"stdio"` als HTTP-Transport — für einen
  HTTP-Client missverständlich.
- `protocol_handler.py:512`: `import json` redundant innerhalb der Methode (oben schon importiert).
- `JsonRpcValidator` akzeptiert Batch-Frames nicht (ok laut MCP-Spec, aber nicht dokumentiert).

---

## E. Frontend (React 18 + TS)

### E-1 🟡 `getAllPages` bricht still bei Seite 100 ab

**Befund:** `frontend/src/api/client.ts:514`: `while (nextUrl && pageCount < 100)`
— bei >10.000 Entities (100 × page_size=100) wird ohne Warnung abgeschnitten.

**Begründung:** Das Projekt unterstützt CSV-Bulk-Import; große Workspaces sind das
angesprochene Szenario (der Kommentar zu „issue C" beschreibt genau diesen
Truncation-Bug für Seite 1). Ein stiller Cut bei 10k reproduziert dieselbe
Bugklasse in größer. Empfehlung: Warnung/loggen oder Ergebnis als „incomplete"
kennzeichnen.

### E-2 ⚪ Legacy `_token`-In-Memory-Bearer im Client

**Befund:** `client.ts:43-55, 225-227`: Der In-Memory-Bearer-Pfad ist tot für den SPA-
Flow, aber aktiv im Code.

**Begründung:** Nur Verwirrungsrisiko (zwei Auth-Wege). Sobald kein Nicht-Browser-
Caller mehr bekannt ist: entfernen.

### E-3 ⚪ Positiv verifiziert

- Kein Token in `localStorage`/`sessionStorage` (nur Workspace-ID/Theme/UI-State) —
  Repo-weiter Grep bestätigt.
- `data-testid` auf interaktiven Elementen breit vorhanden (166 Dateien in components/) — E2E-Pflicht eingehalten.
- Error-Extraktion rendert niemals `[object Object]` (`client.ts:447-467`).

---

## F. Konsolidierte Empfehlungen (Priorität)

1. 🔴 `persistence/managers.py` löschen oder reparieren + Docstrings in
   `models.py`/`serializers.py`/`views.py` korrigieren (B-1).
2. 🟠 `str(exc)`-Leaks entfernen: REST-Views (C-1) und MCP-Auth-Pfad (D-3) auf
   generische Messages umstellen.
3. 🟠 `params.api_key` auf stdio-Transport beschränken (D-1).
4. 🟡 Preset-Gate fail-open zumindest loggen bzw. letzten Cache-Stand nutzen (D-2).
5. 🟡 CORS-Fallback: ACAO-Header weglassen statt ersten Allowlist-Origin spiegeln (D-4).
6. 🟡 `getAllPages` truncation sichtbar machen (E-1).
7. 🟡 Body-Token im Login-Response mittelfristig entfernen (C-3).

---

*Review durchgeführt am 2026-08-22 im Hauptchat (ox-alpha-free), ohne Subagenten-Delegation.*
