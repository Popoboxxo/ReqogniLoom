---
type: REVIEW
scope: WP-6a (Security) — adversarial second review
status: final
date: 2026-10-01
author_agent: security-auditor
branch: chore/audit-review-2026-09
method: read-only static verification; Docker daemon DOWN → no live tests
targets: [AUD-2026-09-220, -221, -222, -223, -224, -225, -239, -226, -227, -228, -229, -231, -238, -240, -232, -234, -236, -241]
---

# REVIEW_WP6A — adversariale Zweitprüfung der WP-6a-Security-Findings

**Scope.** Unabhängiger, read-only Falsifikationsversuch der WP-6a-Beiträge aus
`docs/audit/2026-09/AUDIT_FINDINGS.md` §3/§5 (Volltext in `AUDIT_SECURITY.md`).
Ziel-IDs: Critical `220`, `221`; High `222`, `223`, `224`, `225`, `239`;
Medium-Stichprobe `226`, `227`, `228`, `229`, `231`, `238`, `240`;
Low-Stichprobe `232`, `234`, `236`, `241` — **18/18 Ziele, alle Critical+High vollständig,
Medium 7/8 (87 %), Low 4/7 (57 %)**.

**Methodik.** Alles aus echtem Produktcode/-config am HEAD `10dc620f` neu abgeleitet.
Das audit-eigene `AUDIT_EVIDENCE/*` wurde **nicht als Beweis** verwendet; die einzige
Ausnahme ist `wp1d-resolved-routes.json` als *Django-generiertes*
Routen-Inventar, das gegen `rest_api/urls.py` gegengeprüft und ausdrücklich als
Gegenstand der Zahlenkritik (siehe §3) behandelt wird. Docker-Daemon ist DOWN →
alle Live-Messungen (Stack, DB-Rollen, `pg_class`, HTTP-Status) sind als
**NICHT VERIFIKABAR** markiert. `.kimi-code/` und `AUDIT_EVIDENCE/stack-seeds.md`
wurden nicht angefasst; es wurde kein Key-Wert in diese Datei geschrieben (nur maskiert).

---

## 2. Gegenbeweis-Tabelle

| ID | orig_sev | REVIEW_VERDICT | corrected_sev | counter-evidence (file:line + quote) | note |
|---|---|---|---|---|---|
| AUD-2026-09-220 | Critical | **TEILWEISE** | Critical | Commit existiert: `git cat-file -t 3dcc80d8` → `commit`. Key in Historie: `git grep -l -E "reqlo_[A-Za-z0-9]{30,}" 3dcc80d8 --` → `README.md`, `…wp1d-auth-pagination-filter-errors-live.json`, `…wp1d-tenant-leak-matrix.json`. Arbeitsbaum redigiert: `git grep -lE "reqlo_[A-Za-z0-9]{30,}" HEAD -- docs/audit` → **0**; `git grep -c … HEAD -- docs/audit` → **0**. Nie gepusht: `git merge-base --is-ancestor 3dcc80d8 refs/remotes/origin/HEAD` (=`abd61aed`), `…/origin/main`, `…/origin/chore/system-audit-2026-09` (=`988294b6`) → **exit 1**; `git branch --contains 3dcc80d8` → `chore/audit-review-2026-09` (HEAD), `chore/system-audit-2026-09`. Beide JSON parsen weiterhin (`ConvertFrom-Json` OK). | Leak-Fakten (Commit, Historie, Redaktion, kein Push) **bestätigt**. Der **Widerruf ist nur behauptet**, nicht belegt: HTTP 204 / `revoked_at` / danach-401 stammen aus Audit-Evidenz und sind ohne DB **NICHT VERIFIKABAR**. Status „TEILWEISE BEHOBEN" ist damit korrekt; Critical bleibt, weil der Key in der lokalen Historie überlebt. |
| AUD-2026-09-221 | Critical | **BESTAETIGT** | Critical | `backend/mcp_server/views.py:272` `retry_after = check_mcp_rate_limit(request)` steht **vor** `:307` `handler.handle_http_request(...)`; davor nur `:265 _reject_ambient_cookie_auth` (Form, nicht Gültigkeit). `settings.py:879-884` `CACHES={"default":{…RedisCache…}}` **ohne** `OPTIONS`; `rg socket_timeout` in `backend/reqogniloom/settings.py` → 0. `mcp_server/throttling.py:164` `for throttle in (McpApiKeyRateThrottle(credential or ""), McpIpRateThrottle()):`; `:132-136` `McpIpRateThrottle.get_cache_key` liefert für **jeden** Request einen Key → Cache-`get`+`set`. `settings.py:547-550` `DEFAULT_THROTTLE_CLASSES` global mit `AuthContextAnonRateThrottle`; `rest_api/throttling.py:238-256`. | Statische Kette 4/4 Glieder belegt. Die Live-Messung „187 → 205 Bytes" ist ohne Stack **NICHT VERIFIKABAR**, für das Finding aber nicht tragend. Verfügbarkeits-Amplifikation (kein Confidentiality/Integrity-Impact); Critical im Register ist konsistent mit `AUD-2026-09-030` (dort ebenfalls Critical). |
| AUD-2026-09-222 | High | **BESTAETIGT** | High | `auth_tenancy/workspace_scope.py:114 resolve_request_workspace_id`; Reihenfolge client-gesteuert: `:79-86 _from_query` (`workspace_id`-Query), `:89-111 _from_body` (JSON-Body `workspace_id`, nur POST/PUT/PATCH). `auth_tenancy/rest.py:259-271` `if workspace_id is not None: active_roles = _resolve_roles_from_db(claims.user_id, workspace_id)` sonst `:272-277 … else: active_roles = _resolve_roles_from_db(claims.user_id)` (tenant-weite UNION). `application/requirement_service.py:754-757` `self._set_tenant_context(ctx); req = Requirement.objects.select_related("artifact").filter(id=requirement_id).first()` — **kein** Workspace-Filter. `rest_api/auth_enforcer.py:112-120` nur `scope_denial_reason(auth_context.scope, …)` + `decide_access(auth_context.active_roles, operation)`; `rg workspace_id auth_enforcer.py` → **0**. `rest_api/preset_guard.py:243-244`. | Mechanik sauber codebelegt. **Zahlenkritik:** „311/269" ist aus dem Django-Inventar exakt reproduzierbar (311 mutierend, 42 mit, 269 ohne `workspace` im Pfad, 99 View-Klassen) — **aber** 113 der 311 sind `.{format}`-Aliase; distinkte Pfade = **198**, ohne Workspace = **163 (82,3 %)**, Verhältnis bleibt. **Fence-Auslöser bestätigt:** ausschließlich client-gesteuert (Query/Body), nicht objekt-abgeleitet. **Caveat:** Für Cookie-Auth (nicht BEARER/API_KEY) ist der Pfad fail-closed (`rest.py:273-279` `raise AuthenticationFailed("invalid_token")`), betroffen sind also primär Bearer/API-Key-Clients (inkl. MCP). |
| AUD-2026-09-223 | High | **TEILWEISE** | High | `reqogniloom/urls.py:33` `path("admin/", admin.site.urls)`; `settings.py:181` `"django.contrib.admin"` in `INSTALLED_APPS`. Kein Brute-Force-Schutz: `rg -i "ADMIN_ATTEMPTS_BEFORE_LOCKOUT\|axes\|django-axes"` → **0**; kein `django-axes` in `backend/requirements.txt`; DRF-Throttles gelten nicht für Django-Admin. | Exposition + fehlender Lockout **bestätigt**. Der „**500-er**" ist eine Live-Beobachtung und ohne Stack **NICHT VERIFIKABAR**; statisch ist nur plausibel, dass `settings.py:400-407 STORAGES.staticfiles = whitenoise.storage.CompressedManifestStaticFilesStorage` ohne Manifest fehlschlägt (`backend/Dockerfile:223` führt `collectstatic` aus, `backend/staticfiles/` existiert im Repo nicht). Der zitierte Setting-Name `ADMIN_ATTEMPTS_BEFORE_LOCKOUT` ist **kein** Django-/Axes-Setting (Terminologie unpräzise; gemeint ist Lockout-fehlt). |
| AUD-2026-09-224 | High | **BESTAETIGT** | High | `.pre-commit-config.yaml` existiert nicht (`Test-Path` → False). `.agents/hooks.json` enthält genau `orchestrator-guard`. `rg -i "gitleaks\|trufflehog\|detect-secrets\|secret.?scan"` über Repo (ohne `.git/`, `.venv/`, `node_modules/`) → **0 Treffer außerhalb von Doku**. `.woodpecker.yml:76-80` „Security Scan Phase — Dependency Scanning" (Dependency, kein Secret-Scan). `backend/requirements.txt` ohne Scanner. | Vollständig bestätigt. Die projektspezifische Lücke (`reqlo_` ist kein Standard-gitleaks-Prefix) ist in `AUDIT_SECURITY.md` §2.4 korrekt beschrieben. |
| AUD-2026-09-225 | High | **TEILWEISE** | High | `.github/workflows/` enthält **34** `uses:`-Vorkommen und **15** distinkte Action-Referenzen; genau **1** ist Digest-gepinnt (`.github/workflows/ci.yml:343 docker://rhysd/actionlint:1.7.12@sha256:b1934ee…`). `docker-publish.yml:20-24` `permissions: contents: read / packages: write / security-events: write`. Kein `pull_request_target`/`workflow_run` (`rg` → 0). `docker-publish.yml:134` Shell-Injektionsstelle bestätigt (Nachbarfinding 230). | Kernaussage (SHA-Pinning fehlt durchgängig) **bestätigt**, aber die Zahl **„27 von 28 Actions" ist nicht reproduzierbar** (tatsächlich 34 Vorkommen bzw. 15 distinkte Aktionen, 1 gepinnt). Kein Workflow-Diff zwischen `abd61aed` und HEAD (`git diff --stat abd61aed..HEAD -- .github/workflows/` → leer), die Abweichung ist also nicht durch Baseline-Drift erklärbar. |
| AUD-2026-09-239 | High | **KEIN REQOGNILOOM-BEZUG** | — | Fundort und Ursache sind `docs/audit/2026-09/AUDIT_EVIDENCE/wp1d-auth-pagination-filter-errors-live.json:2237-2246` und `wp1d-cleanup-verification.md §2` — Evidenz-Erzeugung/Cleanup des **Audits**, nicht Produktcode. Beide Ursachen (kein Evidenz-Redactor; Cleanup prüft User-Löschung statt Key-Widerruf) sind Audit-Prozess. | Nach Protokollregel 5: betrifft Audit-Prozess/Tooling, nicht das ReqogniLoom-Softwareprodukt. Bleibt als Prozess-Lehre relevant, ist aber kein Produktfinding. |
| AUD-2026-09-226 | Medium | **BESTAETIGT** | Medium | `settings.py:143-160 CORS_ALLOWED_ORIGINS` / `CORS_EXPOSE_HEADERS` definiert; `INSTALLED_APPS:180-235` (DJANGO/THIRD_PARTY/REQFLOW) **ohne** `corsheaders`; `MIDDLEWARE:240-273` **ohne** `CorsMiddleware`; `backend/requirements.txt`/`pyproject.toml` ohne `django-cors-headers`. | „Tote Konfiguration" bestätigt. Für REST-Cross-Origin ist kein CORS aktiv. (MCP hat eine eigene `_apply_cors_headers`-Implementierung — N-13 — das entkräftet die REST-Aussage nicht.) |
| AUD-2026-09-227 | Medium | **TEILWEISE** | Medium | Die Exemption ist **dokumentiert und begründet**: `auth_tenancy/migrations/0011_rls_policies.py:43-64` „DELIBERATELY NOT INCLUDED — `at_api_key` and `at_user_role` … adding this policy to them would be an outage" (Pre-Auth-Chicken-and-Egg). Zentrale Known-Exception-Liste: `persistence/tests/test_rls_coverage.py:75-262 RLS_EXEMPT_TABLES` (9 Einträge) + `RLS_EXEMPT_PLAIN_TABLES:269-276`; der Test erzwingt, dass jede Ausnahme benannt bleibt. | Die **Tatsache** „`at_api_key`/`at_user_role`/`audit_entry`/`pl_user` ohne RLS" ist bestätigt. Die Live-Zahl **„29/100"** ist ohne DB **NICHT VERIFIKABAR**. Die Formulierung **„unkontrolliert cross-tenant" ist überzogen** — es sind benannte, reviewte Ausnahmen mit Compensating-Control-Status. Echte Residual-Risiken (Admin-Pfade) existieren jedoch → siehe NEU-AUDIT-LUECKE §6, Medium bleibt. |
| AUD-2026-09-228 | Medium | **UEBERZOGEN** | **Low** | `persistence/models.py:501-514` `class User(AuditableModel)` — explizit **nicht** TenantScopedModel: „a platform/admin user may exist without a tenant, hence `tenant` is nullable here and this model does NOT inherit `TenantScopedModel`"; `UserManager:68-101` ist ein normaler `models.Manager` (nicht tenant-skopiert). Keine RLS-Migration für `pl_user` (`rg pl_user **/migrations/**` → nur FK-Referenzen). **Aber:** der einzige Produkt-Lesepfad ist tenant-gefiltert: `rest_api/user_management_views.py:110` `self._accounts.list_for_tenant(tenant_id=ctx.tenant_id)`. | Beobachtung (kein RLS, nicht tenant-skopiert) stimmt, ist aber **dokumentierte Design-Entscheidung**; kein produkt-erreichbarer Cross-Tenant-Pfad gefunden (User-Liste ist tenant-gefiltert). „Cross-Tenant-User-Lexikon auf DB-Ebene" beschreibt eine Defense-in-Depth-Lücke, keinen ausnutzbaren Defekt → Low statt Medium. |
| AUD-2026-09-229 | Medium | **BESTAETIGT** | Medium | `rest_api/throttling.py:391` `ident = f"{self.get_ident(request)}:{_username_digest(request)}"`, `:404-408` `"ident": self.get_ident(request)`; `rg -i "NUM_PROXIES\|USE_X_FORWARDED_FOR"` über `backend/` → **nur Kommentare** (`settings.py:483-484`, `mcp_server/throttling.py:35-36`), **kein** Setting. | Mechanik bestätigt: ohne Proxy = `REMOTE_ADDR` korrekt; hinter Proxy kollabieren die Buckets. Im aktuellen Stack existiert kein Reverse Proxy (B0) → Risiko ist latent/produktionsabhängig; Medium ist vertretbar (Doku dokumentiert den Trade-off selbst). |
| AUD-2026-09-231 | Medium | **BESTAETIGT** | Medium | `settings.py:764-766` `TENANT_TOKEN_LIMIT_PER_DAY: int | None = config("TENANT_TOKEN_LIMIT_PER_DAY", default=None, …)`; `llm_adapter/token_tracking.py:233-243` `is_over_daily_limit()` → „Fail-open: returns False when no limit is configured, no tenant context is set, or the usage query fails". In `.env` ist `TENANT_TOKEN_LIMIT_PER_DAY` nicht gesetzt. | Bestätigt. Verschränkung mit `AUD-2026-09-055` (Retry-Amplifikation) korrekt benannt. |
| AUD-2026-09-238 | Medium | **BESTAETIGT** | Medium | `application/prompt_resolver.py:92-94` `rendered = content; for key, value in values.items(): rendered = rendered.replace("{" + key + "}", str(value))` (kein Escaping/Delimitation). `ai_derivation_service.py:671` `req_title=req.title` (roh) vs. `:672` `req_description=truncate_prompt_content(req.description or "")`; identisch `:787-788` und `:901-902`. | Vollständig codebelegt. Die MEDIUM-Einstufung ist nachvollziehbar begründet (Provider `mock`, Ableitungen landen im Review-Pfad). |
| AUD-2026-09-240 | Medium | **TEILWEISE** | Medium | `auth_tenancy/models.py:160` `workspace_ids = models.JSONField(default=list, blank=True)` („Empty list = every workspace the owning user holds a role in"); `:162` `expires_at … null=True, blank=True` („NULL = never expires"). `workspace_ids` **wird** durchgesetzt — aber **nur in MCP**: `mcp_server/tool_registry.py:1592-1601` `allowed = ctx.api_key_workspace_ids; … return "This API key is restricted to specific workspaces…"`; gesetzt in `auth_tenancy/services/authentication.py:569-571`. | Struktur bestätigt: Default = kein Expiry, Default = keine Workspace-Fence. Die Live-Zahl **„9 aktive `admin`-Keys" ist NICHT VERIFIKABAR** (DB down). „alle ohne Workspace-Fence" gilt nur bei leerem `workspace_ids` (Default) — der Fence-Mechanismus **existiert** und ist in MCP aktiv → siehe NEU-AUDIT-LUECKE §6.2. |
| AUD-2026-09-232 | Low | **BESTAETIGT** | Low | `reqogniloom/urls.py:31` `path("api/v1/version/", VersionView.as_view(), name="version")`; `version.py:124-125` `authentication_classes: list = []; permission_classes = [AllowAny]`; `:130` `commit_short = commit[:7]`. `urls.py:35` `SpectacularAPIView` ohne Permission-Override; `rest_api/urls.py:951-953` „OpenAPI schema — accessible without auth (REQ-L2-RA-002…)". | Öffentliches Schema + öffentliche Version bestätigt. Präzisierung: der „Commit-SHA" ist **bewusst auf 7 Zeichen gekürzt** (`version.py:114-121`, #74) → Informationsoffenlegung geringer als das Label „Commit-SHA" suggeriert. |
| AUD-2026-09-234 | Low | **TEILWEISE** | Low | `rest_api/serializers.py:328-356 StandardPagination` dokumentiert das **Gegenteil** der Behauptung: „DRF clamps an out-of-range `page_size` to `max_page_size` *silently* — `?page_size=5000` answered 200 with 100 results … The clamp itself is kept (returning 400 would break every existing caller…)". `limit` wird geklemmt, nicht 404: `rest_api/views.py:3447` `limit = min(max(limit, 1), MAX_LIMIT)`, ebenso `:3628`. | Zitat-Anker existiert, aber die beschriebene Wirkung „`page_size`/`limit` über `max_page_size` → **404 statt 400**" ist vom Produktcode **nicht gestützt** (dokumentiertes Verhalten: 200 mit geklemmtem Wert). Die „Contract-Klarheit"-Sorge (silent clamp) ist separat berechtigt; Neumessung nötig. Low bleibt defensiv, tendenziell Info. |
| AUD-2026-09-236 | Low | **TEILWEISE** | Low | `.env` (untracked, via `Select-String`): `DJANGO_ENV=development`, `AUTH_COOKIE_SECURE=False`. Gegenseite: `.env.example:33 DJANGO_ENV=production`, `:52 #AUTH_COOKIE_SECURE=True` (kommentierter Prod-Default); `settings.py:67-77` `DEBUG` default False bzw. `AUTH_COOKIE_SECURE = config(…, default=not DEBUG)`. | Fakten der lokalen Umgebung bestätigt. Das Label „wird bei Prod-Promotion still übernommen" ist **spekulativ** — `.env` ist untracked und `.env.example` liefert Prod-Defaults. Es handelt sich um lokale Umgebungs-Konfiguration, nicht um ein getracktes Produktartefakt. |
| AUD-2026-09-241 | Low | **BESTAETIGT** | Low | `deploy/verify-backup-command.sh:90` `export POSTGRES_PASSWORD=reqogniloom-selftest`; `:103` `-e POSTGRES_PASSWORD=reqogniloom-selftest` (Throwaway-Selbsttest-Container, Zeile 95 „postgres-backup self-check"). `deploy/docker-compose.yml:73` und `:1053` `postgresql+psycopg://honcho:${HONCHO_DB_PASSWORD:-honcho-dev-password}@…`. | Bestätigt. **Überlappung/Duplikat:** `AUD-2026-09-148` (WP-1c) führt dieselben Compose-Defaults (`:73,1020,1053`) — Inkonsistenz in der Register-Zählung, siehe §3. |

---

## 3. Register-Quercheck (Widersprüche / Fehlzitate / Duplikate / Zahlen)

### 3.1 Fehlzitate / irreführende Belege

1. **AUD-222, behaupteter fehlender Regressionstest — irreführend.**
   `AUDIT_SECURITY.md:215-216` behauptet: „Suche nach `test.*cross_workspace.*(403|forbidden)` → 0 Treffer" und „Dieser Test fehlt heute".
   Fakt: `backend/rest_api/tests/test_workspace_scoped_roles.py:1-192` existiert, ist eine dedizierte #103-Security-Regression-Suite und prüft für `session|jwt|api_key` Cross-Workspace-**403** (`:171-175`, `:189-192`).
   Die **Suchregex war falsch gewählt** (Testname enthält `cross-workspace` nicht; 403 steht im Body). Die *Schlussfolgerung* ist dennoch korrekt: alle Tests nutzen Routen **mit `workspace` im Pfad** (`/api/v1/workspaces/{id}/needs/`) und decken gerade **nicht** die Detail-Routen ohne Workspace-Pfad ab. Aussage präzisieren, Regex ersetzen.

2. **AUD-222, `preset_guard`-„fail-open" — sachlich falsch.**
   `AUDIT_SECURITY.md:176-177` zitiert `_guard_preset()` als `if workspace_id is None: return  # Cannot determine workspace — allow`.
   Die zitierten Zeilen `preset_guard.py:243-244` stimmen **wörtlich**, aber der davorliegende Fallback `:233-242` lautet:
   `workspace_id = (workspace_id_override or body_workspace_id or self.request.query_params.get("workspace_id") or (str(auth_ctx.tenant_id) if auth_ctx is not None else None))`.
   Für authentifizierte Requests ist `workspace_id` damit **nie None** (es wird die Tenant-ID übergeben) → der `return`-Zweig ist praktisch unerreichbar. Die Aussage „Preset-Gate fail-open auf denselben Routen" ist nicht belegt; tatsächlich wird die **Tenant-ID als Workspace-ID** an `guard.check_endpoint(...)` gereicht (eigener Korrektheitsverdacht, siehe 3.3).

3. **AUD-222, `rg`-Behauptung „0 Treffer in context.py" — falsch.**
   `AUDIT_SECURITY.md:180` behauptet 0 Treffer für `workspace_id` über `auth_enforcer.py` + `auth_tenancy/context.py`.
   Fakt: `auth_tenancy/context.py:77,111,118,129,141` enthält `workspace_id`/`api_key_workspace_ids`. Substanz der Aussage (wird in der Permission-Entscheidung **nicht ausgewertet**) bleibt richtig: `auth_enforcer.py` enthält **0** `workspace_id`; `RbacPermission` nutzt nur `scope` + `active_roles`. Präzisieren: „auth_context.workspace_id wird in `auth_enforcer.py`/`authorization.decide_access` nicht gelesen".

### 3.2 Zahlen-Behauptungen

4. **AUD-225 „27 von 28 Actions" — nicht reproduzierbar.** Gemessen: **34** `uses:`-Vorkommen, **15** distinkte Aktionen, **1** digest-gepinnt (`ci.yml:343`). Weder 27 noch 28 ist als Zähler herleitbar; Workflow-Diff zwischen Baseline `abd61aed` und HEAD ist leer.
5. **AUD-222 „311/269" — reproduzierbar, aber zählmethodisch aufgebläht.** Exakt 311/269 aus dem Django-Inventar; davon sind **113** `.{format}`-Aliase. Distinkte mutierende Pfade: **198**, ohne Workspace: **163 (82,3 %)**. Verhältnis-Aussage („~86 %") hält, absolute Zahl sollte als „Routen-Pattern" ausgewiesen werden.
6. **AUD-220 „docs/audit → 0 Treffer" — bestätigt (tracked).** `git grep -c -E "reqlo_[A-Za-z0-9]{30,}" HEAD -- docs/audit` → 0. README-Fehlalarm (`:1130,1140,1164,1183`, 44-Zeichen-Doku-Beispiele) wurde bestätigt — 4 Treffer, Länge 50 inkl. Prefix.
7. **AUD-220 Fundort veraltet.** Die Register-Zeile nennt `…live.json:2246` als Ort; am HEAD ist diese Datei redigiert (`git grep HEAD` → nur README). Der Anker ist historisch (Commit `3dcc80d8`) korrekt, am HEAD aber kein Beleg mehr.

### 3.3 Duplikate / Klassifikation

8. **Duplikat AUD-241 ↔ AUD-148.** Beide führen dieselben Compose-Defaults `honcho-dev-password` (`docker-compose.yml:73,1053`); AUD-148 zusätzlich `:1020`. Der WP-6a-Beitrag ist eine Teilmenge eines WP-1c-Findings.
9. **Querschnitts-Duplikate (im Register teils vermerkt):** `231` ↔ `055`/`063` (Cost-Amplification/Budget), `221` ↔ `030` (Cache-Timeout), `227` ↔ `184`/`185` (RLS). Die Verschränkungen sind korrekt benannt, erzeugen aber Mehrfachzählung im Gesamtbild.
10. **AUD-239 als Produktfinding klassifiziert, obwohl Prozessursache.** Das Register führt es als WP-6a-Security-Finding (Critical/High-Pool); es ist nach Regel 5 **KEIN REQOGNILOOM-BEZUG**.

### 3.4 Widerspruch im Regelwerk zu AUD-234

11. `AUDIT_SECURITY.md:386` empfiehlt „`page_size`-Überlauf → 400", während `serializers.py:348-356` explizit dokumentiert, dass der Silent-Clamp **bewusst beibehalten** wird und 400 bestehende Caller bräche. Finding und Produkt-Doku widersprechen sich in der Zielrichtung.

---

## 4. Verdikt-Zählung (n = 18 Ziele)

| Verdikt | Anzahl | IDs |
|---|---:|---|
| **BESTAETIGT** | 9 | 221, 222, 224, 226, 229, 231, 238, 232, 241 |
| **TEILWEISE** | 7 | 220, 223, 225, 227, 240, 234, 236 |
| **UEBERZOGEN** | 1 | 228 (Medium → Low) |
| **KEIN REQOGNILOOM-BEZUG** | 1 | 239 |
| FALSCH | 0 | — |
| UNTERSCHAETZT | 0 | — |
| NICHT VERIFIKABAR | 0 (vollständige Verdikte) | Live-Teilaspekte separat: 220-Widerruf, 221-187/205-Bytes, 223-500, 227-29/100, 240-9-Keys |

**Schweregrad-Korrekturen:** 1 × abgestuft (`228` Medium → **Low**). Keine Hochstufung.
**Wesentliche Befundlage bleibt:** 2 Critical + 5 High bestehen inhaltlich; `239` fällt als Nicht-Produktbefund heraus, wodurch der effektive WP-6a-Produktpool auf 21 Findings schrumpft.

---

## 5. Key-Verdikte (Top 3)

1. **AUD-220 TEILWEISE — der Key lebt in der Historie, der Widerruf ist unbelegt.**
   Commit `3dcc80d8` existiert, enthält den `reqlo_`-Key in zwei JSON-Evidenzdateien, und ist über HEAD erreichbar (`git branch --contains`). Der Arbeitsbaum ist sauber redigiert (`git grep -lE … HEAD -- docs/audit` → 0). „Nie gepusht" ist **hart belegt**: `git merge-base --is-ancestor 3dcc80d8` gegen `origin/HEAD`, `origin/main` **und** `origin/chore/system-audit-2026-09` jeweils **exit 1**. Die behauptete Widerrufung (HTTP 204 / `revoked_at`) ist ohne laufenden Stack reine Audit-Evidenz → **NICHT VERIFIKABAR**. Bis `filter-repo` läuft, ist Critical korrekt.

2. **AUD-222 BESTAETIGT — die Lücke ist die client-gesteuerte Fence-Auflösung, nicht die Matrix.**
   311/42/269 sind aus dem Django-Inventar exakt reproduzierbar (distinkt: 198/163), der Fence wird ausschließlich über client-gelieferte `workspace_id` (URL-kwarg/Query/JSON-Body) ausgelöst, `RbacPermission` wertet `auth_context.workspace_id` nicht aus, und `RequirementService.get_requirement` filtert nur tenant- + id-skopiert. Zwei Audit-*Belege* sind irreführend (Test-existiert-doch, preset_guard nicht fail-open), die Kernaussage trägt. Der Effekt betrifft BEARER/API-KEY, nicht Cookie-Auth (dort fail-closed).

3. **AUD-221 BESTAETIGT — Rate-Limit vor AuthN + Cache ohne Timeout, statisch 4/4 belegt.**
   `views.py:272` vor `:307`; `settings.py:879-884` RedisCache ohne `OPTIONS`; `throttling.py:164` zwei Throttles, `McpIpRateThrottle` keyt jeden Request; `settings.py:547-550` global. Die Live-Bytes-Messung (187→205) ist nicht reproduzierbar und nicht tragend.

**Weiteres Kernverdikt:** **AUD-225 TEILWEISE** — SHA-Pinning-Absenz stimmt, die Kennzahl „27/28" ist falsch (34 Vorkommen/15 Aktionen/1 Digest-Pin). **AUD-228 UEBERZOGEN** — dokumentierte, bewusste `pl_user`-Design-Entscheidung ohne produkt-erreichbaren Cross-Tenant-Pfad.

---

## 6. Neu gefundene, vom Audit übersehene ReqogniLoom-Lücken

### NEU-AUDIT-LUECKE N1 — `as_webhook_subscription.secret` im Klartext + Django-Admin-Cross-Tenant-Zugriff (Medium/High)

- `backend/application/models.py:178` `workspace_id = models.UUIDField(db_index=True)` (kein FK, keine Tenant-Zuordnung), `:183` `secret = models.CharField(max_length=255, blank=True)` — **Klartext, ungehasht**, keine RLS (Tabelle in `RLS_EXEMPT_TABLES`, `test_rls_coverage.py:190-228`).
- `backend/application/admin.py:117-131 WebhookSubscriptionAdmin`: `list_display` enthält `workspace_id`, aber **weder `get_queryset` noch `readonly_fields` für `secret`/`workspace_id`**; damit sind beide auf der Admin-Change-Page **editierbar** und für **jeden Tenant** sichtbar. Der Repo-Kommentar selbst hält das fest (`test_rls_coverage.py:202-219`: „the secret is a plain CharField, stored in the clear … an editable field on both the admin add form and the admin change form … the admin is a human-reachable cross-tenant AND cross-secret path").
- Kein WP-6a-Finding nennt diese Tabelle: `rg -i "webhook" docs/audit/2026-09/AUDIT_FINDINGS.md` → **0 Treffer**; die Evidenzdatei `wp6a-rls-db-roles.md:100,171` kennt `as_webhook_*` nur pauschal.
- **Wirkung:** kombiniert mit AUD-223 (offenes `/admin/` ohne Lockout) erlaubt eine einzige kompromittierte Staff-Session das Auslesen/Umleiten fremder Webhook-Secrets (HMAC-Fälschung). Empfehlung: `secret`/`workspace_id` read-only bzw. verschlüsselt/Maskierung im Admin, `get_queryset` tenant-filtern, RLS/Tenant-Spalte nachrüsten.

### NEU-AUDIT-LUECKE N2 — Workspace-gefencete API-Keys werden auf REST nicht durchgesetzt (High)

- `auth_tenancy/models.py:160 workspace_ids` und `auth_tenancy/services/authentication.py:552-571`: Agent-Keys **müssen** `workspace_ids` + `expires_at` setzen; das Feld wird in den AuthContext übernommen (`api_key_workspace_ids=…`, `:569-571`).
- Durchgesetzt wird es **nur** in MCP: `mcp_server/tool_registry.py:1592-1601` („This API key is restricted to specific workspaces…").
- Auf dem REST-Pfad wird `api_key_workspace_ids` **nirgends konsumiert** (`rg "api_key_workspace_ids|workspace_ids"` → nur `auth_tenancy/context.py`, `authentication.py`, `mcp_server/*`; **0** Treffer in `rest_api/` oder `auth_enforcer.py`).
- **Wirkung:** Ein Agent-Key, ausdrücklich auf Workspace A beschränkt, kann über REST-Detailrouten ohne Workspace-Pfad (`/api/v1/requirements/{id-in-B}/`) trotzdem in fremden Workspaces agieren — die Fence greift dort nicht (AUD-222), der Key-Scope aber ebenfalls nicht. Das ist eine schärfere, konkrete Ausprägung als „9 Keys ohne Workspace-Fence" (AUD-240). Empfehlung: dieselbe Fence-Prüfung wie `tool_registry._check_api_key_workspace_fence` in `RbacPermission`/`AuthTenancyAuthentication` verankern.

### NEU-AUDIT-LUECKE N3 — `preset_guard` reicht die Tenant-ID als Workspace-ID an den Guard (Low, Korrektheit)

- `rest_api/preset_guard.py:233-242` fällt bei fehlender Workspace-Angabe auf `str(auth_ctx.tenant_id)` zurück und ruft damit `guard.check_endpoint(key, tenant_id)` wie mit einer Workspace-ID auf. Das ist kein Ausnutzungspfad, widerspricht aber der Audit-Darstellung „fail-open bei unbekanntem Workspace" (siehe §3.1 Nr. 2) und kann Preset-/Sichtbarkeitsentscheidungen verfälschen. Empfehlung: bei fehlender Workspace-ID explizit ablehnen (400) statt Tenant-ID zu substituieren.

---

## 7. Blockierte Prüfschritte (exakt)

1. **Stack-/DB-Liveproben** (`/admin/`-500, `pg_class` 29/100, 9 aktive `admin`-Keys, `revoked_at`, 187→205 Bytes): Docker-Daemon DOWN; keine Container-/`psql`-Probe möglich. Erforderlich: gestarteter Stack + Postgres-Zugriff.
2. **Widerrufsbeleg AUD-220:** erfordert `SELECT revoked_at FROM at_api_key` bzw. einen MCP-`tools/list`-Aufruf mit dem (nicht zu exfiltrierenden) Key.
3. Keine dieser Lücken ändert die statisch belegten Verdikte; sie sind in der Zählung als Live-Teilaspekte ausgewiesen.
