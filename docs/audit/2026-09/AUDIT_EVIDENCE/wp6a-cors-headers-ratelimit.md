---
type: EVIDENCE
scope: wp6a-cors-headers-ratelimit
status: success
date: 2026-09-29
author_agent: security-auditor
---

# WP-6a Evidenz — CORS, Security-Header, CSRF, Rate-Limiting

Alle Messwerte live gegen `http://localhost:8001` (nur GET/OPTIONS bzw. ein bewusst fehlschlagender Login).

---

## 1. CORS

### 1.1 Konfiguration (Settings) vs. Wirklichkeit

`settings.py:143-160` definiert `CORS_ALLOWED_ORIGINS`, `CORS_EXPOSE_HEADERS` (REQ-081) —
und **nichts liest sie auf dem REST-Pfad.**

| Prüfung | Kommando / Ort | Ergebnis |
|---|---|---|
| Dependency vorhanden? | `rg -i 'django-cors\|cors' backend/requirements.txt backend/requirements.lock backend/pyproject.toml` | **0 Treffer** |
| `INSTALLED_APPS` | `settings.py:180-235` | **kein `corsheaders`** |
| `MIDDLEWARE` | `settings.py:240-273` | **kein `corsheaders.middleware.CorsMiddleware`** |
| irgendwo im Code referenziert? | `rg -i 'corsheaders' backend/` | **0 Treffer** |

⇒ **Finding 226 (MEDIUM):** `django-cors-headers` ist keine Abhängigkeit. `CORS_ALLOWED_ORIGINS` und
`CORS_EXPOSE_HEADERS` sind **tote Konfiguration**; REQ-081 („CORS-Allowlist aus Env") ist auf REST **nicht durchgesetzt**.

### 1.2 Live-Messung

```
OPTIONS /api/v1/requirements/   Origin: http://localhost:5173, ACRM: PATCH
  → 401   (kein Access-Control-Allowed-Origin)

OPTIONS /api/v1/requirements/   Origin: https://evil.example.com, ACRM: PATCH
  → 401   (kein Access-Control-Allowed-Origin)

GET /api/v1/auth/me/            Origin: http://localhost:5173  + Bearer
  → 200,  vary: Accept, Accept-Language     (KEIN access-control-allow-origin)

GET /api/v1/auth/me/            Origin: https://evil.example.com + Bearer
  → 200,  vary: Accept, Accept-Language     (KEIN access-control-allow-origin)

OPTIONS /mcp/                   Origin: https://evil.example.com
  → 200   access-control-allow-methods: POST, GET, OPTIONS
          access-control-allow-headers: Content-Type, Authorization, X-API-Key
          vary: Accept-Language
          (KEIN access-control-allow-origin, KEIN allow-credentials)   ← korrekt
```

**Interpretation:**

* **REST ist fail-closed** — es gibt schlicht keinen `Access-Control-Allow-Origin`, also blockiert der Browser
  jeden Cross-Origin-Read. Das ist *kein* direktes Leck, aber:
  1. Die SPA funktioniert nur, weil Vite dev einen `/api`-Proxy auf den Backend setzt
     (`frontend/vite.config.ts:16-27`) — **same-origin**, CORS nie beteiligt.
  2. Für ein Produktions-Deployment ohne Proxy (Frontend :5173, Backend :8001 getrennt) ist die App
     **funktional kaputt** — ein Betriebsrisiko, das als Sicherheits-Feature missverstanden werden kann.
  3. Sobald jemand `CorsMiddleware` „repariert", ist die Falle `CORS_ALLOW_ALL_ORIGINS=True` +
     `CORS_ALLOW_CREDENTIALS=True` der naheliegende Fehlgriff (die Settings-Kommentare warnen davor —
     `settings.py:145-148` — aber es gibt keine technische Schranke).

* **MCP hat eine eigene, korrekte Implementierung:** `mcp_server/views.py:208-230 _apply_cors_headers`
  echot den Origin **nur** bei Allowlist-Treffer und setzt `Access-Control-Allow-Credentials: true`
  **nur dann**. Live bestätigt: feindlicher Origin ⇒ kein `allow-origin`, kein `allow-credentials`.
  ⇒ **Negativbefund N-13.**

**Empfehlung:** Entweder `django-cors-headers>=4` aufnehmen und `CorsMiddleware` **oben** in die
`MIDDLEWARE`-Liste setzen (vor `CommonMiddleware`), **oder** `CORS_ALLOWED_ORIGINS`/`CORS_EXPOSE_HEADERS`
aus `settings.py` entfernen und stattdessen einen Proxy-Pflicht-Vermerk in der Deployment-Doku führen.
Ein dritter, billiger Weg: `CORS_ALLOWED_ORIGINS` auswerten und manuell `Access-Control-Allow-Origin` in
einem eigenen Middleware emittieren — dann greift die bestehende Allowlist-Logik für **beide** Pfade.

### 1.3 CSRF

| Kontrolle | Ort | Status |
|---|---|---|
| `CsrfViewMiddleware` global | `settings.py:260` | 🟢 |
| Cookie-Auth erzwingt CSRF | `auth_tenancy/rest.py:243-244` → `_enforce_csrf` (`:357`) | 🟢 |
| `RefreshView` erzwingt CSRF explizit | `rest_api/auth_views.py:413-416` | 🟢 |
| `CSRF_TRUSTED_ORIGINS` aus Env | `settings.py:168-175` (Default `localhost:5173,127.0.0.1:5173,:3000,:127.0.0.1:3000`) | 🟢 |
| MCP-Transport `csrf_exempt` | `mcp_server/views.py:247,438,615` | 🟢 **mit erzwungener Invariante**: `_reject_ambient_cookie_auth` (`:79-141`) lehnt jeden Request ab, der nur ein Cookie-Credential mitbringt |

**Negativbefund N-11.** Die `csrf_exempt`-Anwendung ist ausdrücklich *bewacht* — genau die Art von
„unguarded invariant", die der Vor-Audit zu Recht bemängelt, wenn sie unbewacht wäre.

### 1.4 Security-Header

Live gemessen an **zwei** Endpunkten (authentifiziert + anonym):

| Header | `GET /api/v1/auth/me/` (auth) | `GET /api/schema/` (anon) | Quelle |
|---|---|---|---|
| `content-security-policy` | `default-src 'self'; frame-ancestors 'none'; base-uri 'self'` | identisch | `settings.py:289-292` + `reqogniloom/security_middleware.py` |
| `x-frame-options` | `DENY` | `DENY` | `XFrameOptionsMiddleware` (Django-Default) |
| `x-content-type-options` | `nosniff` | `nosniff` | SecurityMiddleware |
| `referrer-policy` | `same-origin` | `same-origin` | SecurityMiddleware |
| `cross-origin-opener-policy` | `same-origin` | `same-origin` | SecurityMiddleware |
| `cross-origin-embedder-policy` | — | — | nicht gesetzt |
| `strict-transport-security` | **fehlt** | **fehlt** | `SECURE_HSTS_SECONDS=31536000` (Default bei `DEBUG=False`) greift nur bei `request.is_secure()` ⇒ bei reinem HTTP korrekt nicht gesetzt |
| `permissions-policy` | fehlt | fehlt | nicht konfiguriert |
| `server` | `uvicorn` | `uvicorn` | Finding 235 |

**Negativbefund N-12:** CSP + XFO + nosniff + Referrer-Policy + COOP sind **vollständig und live bestätigt**.
Damit ist die im Auftrag befürchtete Kette „Token im localStorage ohne CSP" **nicht** zutreffend:
Es gibt **keinen** Token im localStorage (`wp6a-input-validation-parser.md` §N-06 im Hauptbericht),
und die CSP ist restriktiv.

**Einschränkung (Blocker für Produktion):** Der Stack hat **kein TLS** (8 Compose-Services, kein nginx,
`.env`: `AUTH_COOKIE_SECURE=False`, `DJANGO_ENV=development`). HSTS ist damit gegenstandslos, und die
httpOnly-Cookies werden im Klartext übertragen ⇒ Finding 236. Das ist **kein Code-Defekt**, sondern
ein Deployment-Gate.

---

## 2. Rate-Limiting

### 2.1 Ist es aktiv?

**Ja, global und runtime-konfigurierbar.**

| Schicht | Ort | Wirkt auf |
|---|---|---|
| `DEFAULT_THROTTLE_CLASSES` | `settings.py:547-550` | **jede** DRF-Route (nicht nur die Auth-Routen) |
| `DynamicRateThrottle` | `rest_api/throttling.py:101-176` | löst die Rate **pro Request** neu auf (`_refresh_rate`), überliest `admin_ops.rate_limits.resolve_rate` (Tenant-Override > Global-Override > Settings > aus) |
| MCP | `mcp_server/throttling.py:139-169` | delegiert an dieselben Klassen (`McpApiKeyRateThrottle`, `McpIpRateThrottle`) |
| Memory-Writes | `memory/ratelimit.py` → `MemoryWriteRateLimitExceeded` → 429 + `Retry-After` | eigener Fixed-Window |

### 2.2 Rate-Matrix (Defaults, `settings.py:445-488`)

| Scope | Prod-Default | Non-Prod-Default | Key | Zählt |
|---|---|---|---|---|
| `user` | 600/min | 20 000/min | API-Key-ID **oder** User-ID | **alle** Requests |
| `anon` | 120/min | 20 000/min | `get_ident()` (= IP) | alle anon. Requests |
| `login` | 10/min | 1000/min | (IP, SHA256(username)) | **nur Fehlversuche** |
| `login_ip` | 60/min | 5000/min | IP | **nur Fehlversuche**, nicht bei Erfolg resettet |
| `refresh` | 30/min | 1000/min | IP | alle Requests |
| `mcp_key` | 240/min | 20 000/min | API-Key | alle |
| `mcp_ip` | 1200/min | 20 000/min | IP | alle |

**Fail-Policy:** bewusst **fail-open** bei Cache-Ausfall (`throttling.py:48-64, 164-176, 291-314`) —
dokumentiert, mit WARNING-Log. Für Brute-Force ist das vertretbar (AuthN/RBAC hängen nicht am Cache),
für DoS ist es der Kern von Finding 221.

**Gute Details (Negativbefund N-09):**
* Fehlversuche werden **nach** der Validierung gezählt, nicht bei jedem Request ⇒ richtige Logins verbrauchen kein Budget.
* Erfolgreicher Login resettet **nur** das (IP, username)-Bucket, **nicht** das IP-Spray-Bucket ⇒ keine Refill-Lücke.
* Der Login-Key hasht den Usernamen (`_username_digest`, `:367-379`) ⇒ kein User-Verzeichnis im Cache-Dump.

### 2.3 Lücke: `get_ident()` hinter Reverse Proxy (Finding 229)

`SimpleRateThrottle.get_ident()` (DRF-Standard) liest `X-Forwarded-For` **nur** wenn `NUM_PROXIES` gesetzt ist.

| Prüfung | Ergebnis |
|---|---|
| `rg 'NUM_PROXIES' backend/reqogniloom/settings.py` | **nur ein Kommentar** (`:483`), **keine Zuweisung** |
| `rg 'USE_X_FORWARDED_FOR\|USE_X_FORWARDED_HOST' settings.py` | **0 Treffer** |

Der eigene Code kommentiert das sogar (`settings.py:483`: „NUM_PROXIES is unset, so behind a proxy …").

**Konsequenz hinter einem Reverse Proxy:**
* `anon` (120/min) ⇒ **alle** nicht-autentifizierten Clients teilen **ein** Bucket ⇒ Falsch-Positive bei
  gemeinsam genutztem Egress (Büro-NAT, Cloud-NAT-Gateway).
* `login_ip` (60/min) ⇒ **ein** Bucket für alle ⇒ ein unauthentifizierter Angreifer, der 60 Fehlversuche
  sendet, sperrt **alle** Nutzer hinter demselben Proxy für das Restfenster aus ⇒ **globaler Auth-DoS**.
  Das ist genau der Fehler, den #269 finding 2 („Login-Throttle blockiert korrekte Logins / Auth-DoS",
  Issue-Status GESCHLOSSEN) behoben hat — auf Proxy-Ebene wieder erzeugt.
* `refresh` (30/min), `mcp_ip` (1200/min) ⇒ gleiches Muster.

**Empfehlung:** `NUM_PROXIES=<Anzahl der Proxy-Hops>` **pro Deployment** setzen (nicht global defaulten —
die Zahl ist netzwerkabhängig), alternativ ein eigenes Middleware, das `REMOTE_ADDR` aus
`X-Forwarded-For` **nur** für Verbindungen aus `INTERNAL_IPS` ableitet.

### 2.4 DoS-Verstärkung: Rate-Limit vor AuthN (Finding 221, CRITICAL)

| Glied | Beleg |
|---|---|
| 1. Cache blockiert bei Redis-Störung | `settings.py:879-884` — `CACHES["default"]` = `RedisCache` **ohne** `OPTIONS.socket_timeout` ⇒ `redis-py`-Default `None` ⇒ blockiert bis OS-Connect-Timeout |
| 2. Rate-Limit vor AuthN | `mcp_server/views.py:265` (`_reject_ambient_cookie_auth`, prüft nur die *Form*) → `:272 check_mcp_rate_limit(request)` → `:307 handler.handle_http_request(...)` (**hier** authentifiziert) |
| 3. 2 Cache-Ops pro unauth. Request | `mcp_server/throttling.py:164` — zwei `SimpleRateThrottle`-Instanzen ⇒ je `get` + `set` |
| 4. Gleiches für jede anon. REST-Route | `settings.py:547-550` + `throttling.py:250-256` |

**Beantwortung der Auftragsfrage:** *„WP-1a fand, dass der MCP-Rate-Limit-Check in genau den Cache schreibt,
der bei Redis-Ausfall hängt — ist das eine DoS-Verstärkung?"*
⇒ **Ja. Und sie ist unauthentifiziert.** Ohne gültige Credential erreicht jeder Request die zwei blockierenden
Cache-Zugriffe; das Rate-Limit, das den Angriff begrenzen soll, **ist** der Angriffsvektor.

**Nicht ausgeführt:** Live-Reproduktion erfordert einen Redis-Stopp bzw. eine Netzwerkpartition — auftragsgemäß
untersagt. Die Kette ist vollständig statisch belegt (4 Glieder, je Datei:Zeile).

**Fix-Reihenfolge:**
1. `CACHES["default"]["OPTIONS"] = {"socket_connect_timeout": 1, "socket_timeout": 1}` (Ursache, behebt auch AUD-2026-09-030).
2. Im MCP-Transport: **vor** `check_mcp_rate_limit` ein gültiges, nicht-leeres Header-Credential verlangen
   (der MCP-Pfad braucht ohnehin zwingend ein Key ⇒ verlustfrei).
3. Circuit-Breaker: nach N fehlgeschlagenen Cache-Zugriffen für M Sekunden „limits not enforced" **stateful** machen
   und dabei **den Header `Retry-After` mit einem Backup-Limit** ausgeben, statt still zu erlauben.

### 2.5 Nicht abgedeckte gefährliche Pfade?

| Pfad | Limit vorhanden? | Bewertung |
|---|---|---|
| `POST /auth/login/` | 🟢 `login` + `login_ip` | — |
| `POST /auth/refresh/` | 🟢 `refresh` | — |
| `POST /workspaces/{pk}/import/csv/` | 🟡 nur `user`/`anon` (600/min) | 🟢 zusätzlich `_MAX_ROWS=1000` + Django-2,5-MB-Upload-Cap |
| `POST /workspaces/{pk}/import/reqif/` | 🟡 dito | 🟢 zusätzlich `_MAX_SPEC_OBJECTS=5000` + 20-MB-Text-Cap |
| PDF-Report-Export (synchron) | 🟡 nur `user` (600/min) | 🟡 **kein** eigenes Budget für den teuren 888-Requirement-Export; `CONN_MAX_AGE=60` + `statement_timeout=30000ms` (`settings.py:352-358`) begrenzen die DB-Seite |
| LLM-/Derivation-Endpunkte | 🟡 nur `user` (600/min) | 🟡 **kein** LLM-spezifisches Request-Rate-Limit ⇒ Finding 231 |
| MCP-Transport | 🟢 `mcp_key` + `mcp_ip` | 🟡 aber vor AuthN ⇒ 221 |
| `/admin/login/` | 🔴 **keins** (Django-Views kennen DRF-Throttles nicht) | ⇒ Finding 223 |
| `/health/`, `/api/schema/` | 🟢 `anon` (120/min) wenn über DRF; `/health/` ist Plain-Django-`View` ⇒ **kein** Limit | 🟡 `/health/` ist ungedrosselt ⇒ Health-Check-DoS möglich (gering, da read-only) |

---

## 3. AuthN-Matrix (Nebenbefund zu WP-6a.2)

| Kontrolle | Beleg | Live |
|---|---|---|
| Timing-resistente User-Enumeration | `password_authentication.py:38-41` (`_dummy_password_hash`), `:102-144` | `admin` 266/208/210/211/209 ms vs. `zz_no_such_user_zz` 215/210/212/223/219 ms → **identisch** |
| Einheitlicher Fehlercode | `invalid_credentials` für Malformed-Body, falsches Passwort, inaktives Konto | Code (`auth_views.py:298-304`, `password_authentication.py:138-144`) |
| Access-Token-TTL | 1 h (`aud=reqogniloom-api`, `iss=reqogniloom`) | Login-Antwort bestätigt |
| Refresh-Rotation + Familien-Widerruf | `authentication.py:441-455`, `auth_views.py:438-449` | Code |
| Logout widerruft die Familie | `auth_views.py:363-373` | Code |
| Session-Fixation | kein `sessionid`-Login-Flow; Session-Login nur via Django-Admin (`/admin/` = 500) | 🟢 n/a |
| Token-Speicherung Frontend | **kein** localStorage/sessionStorage; httpOnly-Cookie + CSRF-Cookie | Code (`AuthContext.tsx:8`, `client.ts:32`) |
| Registrierung / Passwort-Reset | **existieren nicht** (nur `bootstrap_admin`, `seed_*`, `UserViewSet.create` als Tenant-Admin-Aktion) | `urls.py`, `auth_views.py` |
| Account-Lockout | kein persistenter Lockout; nur Rate-Limit-Buckets | bewusste Entscheidung (Doku in `throttling.py:22-37`) |

**Nebenbefund:** `AUTH_LOGIN_INCLUDE_BODY_TOKEN` Default `True` (`auth_views.py:329`) ⇒ die Login-Antwort enthält
weiterhin `token` im Body (live bestätigt: 364 Zeichen) plus `Deprecation: true`. Das Frontend ignoriert es
(`AuthContext.tsx:8`), aber jedes nicht-konforme Client (Skript, CI, MCP-Client) bekommt einen
JavaScript-lesbaren Token zusätzlich zum httpOnly-Cookie ⇒ Finding 233 (LOW).