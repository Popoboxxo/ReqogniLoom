---
type: Plan
title: "Plan E — Security, API-Vertrag (WP E1–E3) — Umsetzungsplan"
scope: "backend/rest_api, backend/auth_tenancy, backend/application, backend/mcp_server, integrations/hermes-agent-plugin, frontend/src (nur E3)"
status: proposed
date: 2026-10-21
base_head: b175c970
qs_base: "QS, v1.8.0-beta.22, Commit dc7ee14"
author_agent: senior-developer
language: de
index: docs/plans/2026-10-21-backlog-umsetzung-index.md
decisions: docs/plans/2026-10-21-entscheidungen-offen.md
integration: "Stufe 2 (Korrekturaufträge KA-E-01…14, KA-ALL-01/02/03/06/07/08/09/11) eingearbeitet, siehe Änderungsprotokoll Stufe 2"
---

# Plan E — Security, API-Vertrag (E1 Key-Prinzipale, E2 API-Vertrag, E3 2FA/TOTP)

> **Reiner Umsetzungsplan. Kein Code, keine Migration, keine Config-Änderung.**
> Grundlage: Planbasis `docs/superpowers/specs/2026-10-21-backlog-umsetzungsplaene-design.md`
> (§1 Q4, §2 Plan E, §3 Wellen). Jede `datei:zeile`-Angabe ist gegen den Arbeitsbaum bei
> `b175c970` (= `origin/main`) verifiziert. Live-Messwerte (Check-IDs `E-L*`) stammen von der
> QS (`1.8.0-beta.22`/`dc7ee14`), nur lesend; Rohbelege:
> `docs/test-reports/plan-review-2026-10-21/plan-e/`.
> **Belege:** Belege unter `docs/test-reports/` sind gitignored (`.gitignore:91`); DoD-Nachweise
> stehen im PR-Text bzw. als CI-Artefakt (vorläufig, ENT-X3 = C). Nach ENT-X3 = B gehen neue
> DoD-Artefakte nach `docs/se/reports/` bzw. `docs/reviews/` (Index §f.6). QS-Adressen in
> Verifikationsbefehlen nur als `$QS_URL`.
> **Vorrang:** Planbasis > [Plan-Index](2026-10-21-backlog-umsetzung-index.md) > dieser Plan. Offene
> Nutzerentscheidungen heißen `ENT-*` ([Entscheidungsliste](2026-10-21-entscheidungen-offen.md));
> Stellen mit „vorläufig, ENT-…“ tragen deren Empfehlung bis zur Entscheidung.

| Feld | Wert |
|---|---|
| **Status** | proposed |
| **Issues** | #1444, #1443, #1439 (E1) · #1380, #1388, #1396, #1397 (E2) · #1308 (E3) |
| **ADR-Bezug** | ADR-011 (Autorisierungsachse, SEC-03 Fence), ADR-021 O5 (2FA-Residuum, Nachtrag) |
| **Wellen** | E1, E2 in Welle 0; E2-Burn-down (WP E2.8) und E2.9 (Listen-Parameter) in Welle 2; E3 in Welle 3 (Sicherheitsgate vor Welle 3: QR-S01, QR-S10, Index §b) |
| **Migrationen** | siehe [Plan-Index §e](2026-10-21-backlog-umsetzung-index.md#e-konsolidierte-migrationsvergabe-bindend). Dieser Plan legt an: `auth_tenancy` · `0031_user_mfa` (E3.1) · `audit` · `0016_alter_auditentry_op_mfa` (E3.1). Nummer = höchste Nummer der App auf `main` + 1 beim Merge; `dependencies` zeigen auf die zuletzt gemergte Migration der App (erwartet `auth_tenancy 0030_backfill_show_readable_ids` aus Plan C, `audit 0015_alter_auditentry_op`). Beide Tabellen sind global (kein `TenantScopedModel`, Begründung E3.1) → keine RLS-Policy; `persistence/tests/test_rls_coverage.py` bleibt Pflicht-Check und grün. E1/E2: keine Migration. |

---

## (i) Ziel und Nicht-Ziele

**Ziel.**
1. **E1:** Ein workspace-gebundener API-Key (`principal_type=agent`, `workspace_ids=[…]`) verhält
   sich an REST und MCP gleich (Q4: Workspace-Fence statt RBAC-Überraschung). `GET /api/v1/workspaces/`
   und MCP `workspace.list` liefern ihm **seine** Workspaces. Fehler nennen den echten Grund.
   `POST /api/v1/api-keys/` meldet alle Feldfehler in **einer** 400 und ist im OpenAPI beschrieben.
   Das Hermes-Plugin zeigt den Ablehnungsgrund statt „none visible".
2. **E2:** Jeder im Schema deklarierte Pfad ist erreichbar und antwortet wie deklariert;
   `If-Match` wird strikt nach RFC 9110 ausgewertet; `ETag` gibt es für jeden Typ, dessen
   Service eine Versionsprüfung kennt; das Schema deklariert `If-Match`/`ETag`/412 ehrlich;
   stille Schema-Beschneidung wird als Ratchet sichtbar und abgebaut.
3. **E3:** TOTP-2FA (RFC 6238, `pyotp`) mit Recovery-Codes für Staff-Konten auf beiden
   Login-Flächen (`/api/v1/auth/login/`, `/admin/login/`), nach Sign-off und
   `dependency-check`; ADR-021 O5 erhält den Nachtrag „Residuum geschlossen".
   Nicht eingeschriebene Staff-Konten können unter `required` nicht selbst einschreiben, sondern nur
   mit einmaligem Enrollment-Grant (E3.4/E3.6, vorläufig, ENT-E7 = A). Vor dem Umschalten auf
   `required` widerruft ein Cutover-Command passwort-only entstandene Staff-Sitzungen (E3.9).

**Nicht-Ziele.**
- Kein Rollen-Mitprovisionieren für Agent-Keys (#1444 Option 1) — Q4 hat Option 2 gewählt.
- Kein Wechsel des Plugins auf den Human-Key für die Workspace-Liste (#1443 Soll 2); nach E1
  liefert der Agent-Key seinen Scope selbst, das ist die gewünschte Betreiber-Sicht.
- Keine MFA für API-Keys oder MCP (Keys bleiben Bearer-Credentials; Härtung nur bei der
  Key-**Anlage**, Task E3.6). Staff-API-Keys ohne zweiten Faktor sind ein **akzeptiertes
  Restrisiko mit Inventur und Ablaufpflicht** (vorläufig, ENT-E8 = A): E3.9 listet Staff-Keys beim
  Cutover, E3.6 verlangt `expires_at` für neue Staff-Keys. Das Übergangsfenster bis `required` ist
  befristet; das Datum steht im ADR-021-Nachtrag (vorläufig, ENT-E6 = A + Befristung; E3.0).
- Kein WebAuthn/FIDO2, keine SMS/E-Mail-OTP, kein QR-Rendering in v1 (vorläufig, ENT-E5 = A).
- Kein Umbau der Workflow-Transition-Preconditions (zählen gegen `WorkflowItemState.version`,
  siehe Befund RB-09).
- Präferenzdienst (Q1), Memory-Port (A0b), Link-Typ-Katalog: nicht Teil dieses Plans
  (Besitz: Plan C/C2, Plan A, Plan B/F).

## (ii) Entscheidungen (aus der Planbasis, unverändert zitiert)

| # | Wortlaut (Planbasis) |
|---|---|
| Q4 | „Key-Prinzipale folgen **MCP-Semantik** (Workspace-Fence statt RBAC)" — Wirkung: #1444, #1443, #1439 |
| E1 | „Key-Prinzipale: REST-Fence wie MCP, `GET /workspaces/` liefert eigene Workspaces, sprechende Fehler, Matrix-Test REST+MCP je Key; Fehlersammlung in `api-keys` (alle Fehler in einer 400, OpenAPI-Body); Plugin-Dashboard zeigt 403-Grund" |
| E2 | „API-Vertrag ehrlich: `baselines/`-Routenreihenfolge, 124 beschnittene View-Klassen im Schema, If-Match strikt (nur starke Validatoren, sonst 400/412), ETag für alle mutablen Typen oder Zusage einschränken, `If-Match` im OpenAPI deklarieren" |
| E3 | „2FA/TOTP für Staff mit `pyotp` (Sign-off + `dependency-check` vor Merge), Recovery-Codes, ADR-021 O5 Nachtrag" |
| Welle | „Welle 0 (klein, parallel): C0, D2 (Promptfoo), G1, E2, E1." · „Welle 3: … E3 …" |

**Entscheidungs-Konflikt (gemeldet, nicht umgebogen):** E2 nennt „`baselines/`-Routenreihenfolge"
als Ursache. Die Messung widerlegt das (E-L3). Der Plan behebt die **tatsächliche** Ursache
(Task E2.1) und lässt die Routenreihenfolge unverändert (vorläufig, ENT-E3 = A). Optionen siehe
(ix) ENT-E3 (vormals D-E2c).

## (iii) Ist-Stand (verifiziert)

### E1 — Key-Prinzipale

| Befund | Beleg |
|---|---|
| Rollen eines API-Keys = Rollen des **Key-Owners** (`IdentityClaims.user_id=api_key.user_id`, `roles=()` → später aus `UserRole` aufgelöst) | `backend/auth_tenancy/services/authentication.py:627-640` |
| Gefencter Key ohne Workspace-Kontext bekommt `active_roles=()` | `backend/auth_tenancy/services/tenant_context.py:76-85` |
| REST prüft **zuerst RBAC**, danach erst den Fence → Meldung „RBAC denied: no active role permits 'read'" | `backend/rest_api/auth_enforcer.py:114-146` (RBAC `:114-136`, Fence `:138-146`); Zwilling `backend/auth_tenancy/rest.py:476-502` |
| REST-Fence existiert bereits (ADR-011 SEC-03), gemeinsame Implementierung mit MCP | `backend/auth_tenancy/resource_scope.py:671-697` (`workspace_fence_denial`), `:881-923` (`enforce_request_scope`); MCP `backend/mcp_server/tool_registry.py:1915-1943` |
| Gefencter Key im eigenen Workspace über REST erlaubt (Test vorhanden) | `backend/rest_api/tests/test_sec02_sec03_workspace_fence.py:239` |
| `WorkspaceService.list_workspaces` liefert **alle** Tenant-Workspaces | `backend/application/workspace_service.py:177-187`; REST `backend/rest_api/views.py:6318-6330`; MCP `backend/mcp_server/tools/cross_cutting.py:1567-1599` |
| MCP verweigert gefencten Keys jeden workspace-losen Aufruf, auch `workspace.list` | `backend/mcp_server/tool_registry.py:1508-1531`; `workspace.list` steht in `TENANT_SCOPED_READ_TOOLS` `backend/mcp_server/workspace_scope.py:376-380` |
| Plugin ruft MCP `workspace.list` (nicht REST) mit dem Agent-Key; Fehler wird als `200 {"error":…}` durchgereicht und im UI als Leerzustand gerendert | `integrations/hermes-agent-plugin/reqogniloom_client.py:111,732-738`; `dashboard/plugin_api.py:125-133,191-198`; `dashboard/dist/index.js:1816-1822,2042-2044,2191` |
| `POST /api/v1/api-keys/` validiert seriell (je Request ein Fehler) — View: `:262-357`; Agent-Regeln im Service: `authentication.py:687-714` | `backend/rest_api/api_key_views.py:229-391` |
| Kein Request-Body im Schema für `POST /api-keys/` | E-L13 |
| Live: Human-Token `GET /workspaces/` → 200, 2 Workspaces | E-L10 |
| Live: Agent-Key-Verhalten | E-L11 NICHT PRÜFBAR (Key-Anlage = POST); Code-Beleg oben |

### E2 — API-Vertrag

| Befund | Beleg |
|---|---|
| `GET /baselines/` → 404; mit `?workspace_id=` → 200; nested → 200 | E-L1, E-L3 |
| Ursache: Preset-Gate setzt die **Tenant-ID** als Workspace-ID ein, `check_endpoint` scheitert → `Http404`, roh durchgereicht | `backend/rest_api/preset_guard.py:229-254` (Fallback `:236-240`), `backend/rest_api/views.py:4737-4745,4756,4774-4779`; gleiche Wurzel wie #398 (`views.py:4796-4808`) |
| Einziger Nutzer von `_guard_preset` mit nicht-leerem Key: `BaselineViewSet` (`preset_endpoint_key = "baselines"`) | `backend/rest_api/views.py:4717`; alle übrigen `preset_endpoint_key = ""` (`:1202,2354,2587,3428,3845,5133,6313,6879`) |
| `include(baseline_urlpatterns)` enthält nur `scope-preview/`; Django-`include` fällt bei Nichttreffer auf die nächsten Muster durch | `backend/baseline/urls.py:29-37`, `backend/rest_api/urls.py:312-314,1115` |
| `/comments/`: Router registriert Collection, View antwortet 405 + `VALIDATION_ERROR`, `Allow: GET, POST` | `backend/rest_api/urls.py:284`, `backend/rest_api/collaboration_views.py:104-140`; E-L5 |
| `/tracelinks/{id}/` GET ist fester 404-Stub, PATCH fester 405-Stub; Schema deklariert get/patch/delete | `backend/rest_api/views.py:4060-4063,4093-4098`; E-L6 |
| If-Match: weak/garbage/leer/`*`/Liste → `None` → Fallback auf Body-`expected_version` → stiller Last-Writer-Wins | `backend/rest_api/mixins/etag.py:97-113,116-148,178-208`; E-L9 |
| `uses_if_match` ist für jeden nicht-leeren Header wahr → bei `If-Match: *` würde ein veraltetes Body-`expected_version` als 412 statt 409 gemeldet | `backend/rest_api/mixins/etag.py:162-165` + Mapping `views.py:1551-1555` |
| ETag-Opt-in nur Requirement, TestCase, Baseline, Workspace | `views.py:1345,1430,1534,1561` · `3498,3585,3659,3674` · `4820,4874,5064` · `6350,6540,6559` |
| Services mit `expected_version`, aber View reicht nur den Body durch (kein ETag) | Need `views.py:887`, Architecture `:2898`, ADR `:7200`, Risk `:7530`, Issue `:8565`, ChangeRequest `:8837`, Glossary `:10660` |
| Ohne Versionsprüfung im Service: Goal, MainGoal, TestRun, Artifact, TraceLink, WorkflowDefinition | `views.py` partial_update `:7948,8360,9035,2423,4093,5519` |
| Live: ETag nur bei requirements/testcases/workspaces | E-L8 |
| Schema: 0 Ops mit `If-Match`, 412 in 5 Pfaden, 0 Ops mit `ETag`-Response-Header | E-L7 |
| Frontend nutzt If-Match nur bei Requirements, starke Tags | `frontend/src/api/requirements.ts:284` |
| Schema-Generator: 267/528 Ops ohne 2xx-Body; statisch 107 View-Klassen ohne Serializer-Angabe; 9 operationId-Kollisionen; `workspaces/{id}` ohne `format: uuid` | E-L14, E-L13, E-L15; Liste `views-without-serializer-static.txt` |
| drf-spectacular 0.30.0, Postprocessing-Hook-Mechanik vorhanden | `backend/requirements.txt:43`; `backend/reqogniloom/settings.py:694-718`; `backend/rest_api/openapi.py:151` |

### E3 — 2FA

| Befund | Beleg |
|---|---|
| ADR-021 `accepted`; O5-Nachtrag 2026-10-14: Risiko-Akzeptanz, 2FA als eigenes Vorhaben | `docs/se/ADR/ADR-021_admin_login_lockout.md:1-8,335-339` |
| Admin-Lockout global (kein Tenant), `AdminLoginLockout` | `backend/auth_tenancy/models.py:907-969`; Form `backend/auth_tenancy/admin_login.py:102-188` |
| `User.is_staff`/`is_superuser` vorhanden; Bootstrap-Admin ist Staff | `backend/persistence/models.py:552-563`; `backend/auth_tenancy/provisioning.py:174` |
| REST-Login: Passwort → Token sofort | `backend/rest_api/auth_views.py:291-346` (Token `:312-313`) ; Refresh `:404-470` |
| Feldverschlüsselung (Fernet) vorhanden; `decrypt_secret` reicht Klartext durch (fail-soft) | `backend/persistence/encryption.py:31-60` |
| Gepfefferter HMAC-Hash vorhanden | `backend/auth_tenancy/services/authentication.py:104-107,138-164` |
| Kein 2FA-Paket; `pip-audit` läuft in CI (`set-1-core`) | `backend/requirements.txt`; `.github/workflows/ci.yml:158-165` |
| `pyotp` 2.10.0, MIT, keine Laufzeit-Abhängigkeiten, Release 2026-06-14, PyPI-Vulnerabilities `[]` | PyPI JSON-API, abgerufen 2026-10-21 |
| Live: Login liefert sofort Cookies + Body-Token; `/auth/mfa/status/` → 404 | E-L16 |
| Höchste Migrationen: `auth_tenancy/0027_create_form_config.py`, `audit/0015_alter_auditentry_op.py`; bis Welle 3 belegt Plan C `auth_tenancy` 0028–0030 (Index §e) | Arbeitsbaum = `origin/main` |
| Generisches Mapping `OptimisticLockError` → **409** `CONFLICT`; 412 entsteht nur in View-Zweigen mit `uses_if_match` | `backend/rest_api/views.py:278` (`_EXC_TO_STATUS`), `:359` (`_service_error_response`), `:1551-1555`; `backend/rest_api/mixins/etag.py:163,237` |
| Refresh-Familien widerrufbar; Admin-Sitzungen in `django.contrib.sessions` (DB) | `backend/auth_tenancy/services/refresh_token_store.py:117` (`revoke_refresh_family`); `backend/reqogniloom/settings.py:184` |
| Key-Inventur existiert (read-only) | `backend/auth_tenancy/management/commands/inventory_api_keys.py:342` (`collect_inventory`) |
| Django-Cache = Redis (für Challenge-Nonce E3.2) | `backend/reqogniloom/settings.py:1123-1131` |

## (iv) Arbeitspakete und Tasks

Konventionen: Fehlerumschlag immer `build_error_response` (`{"error":{"code","message","details"}}`).
„TDD" = zuerst der genannte Test, rot gegen `b175c970`, dann Code. Tests laufen gegen echte
DB/Views (pytest-django, `APIClient`), kein Mocking von Auth, Fence oder Service.
Verifikation lokal immer mit Superuser-DB-User über das Makro `BT` aus Index §f.3.
Rollen laut Index §g (`frontend-component-engineer`, `ui-reviewer`; ADR-Text „Rolle laut ENT-X4 + Nutzer“).

### WP E1 — Key-Prinzipale (Welle 0)

#### E1.1 — Gemeinsamer Fence-Helfer (senior-developer)

- **Ändern:** `backend/auth_tenancy/resource_scope.py`.
- **Neu (Signaturen):**
  - `API_KEY_FENCE_FILTER = "filter"` — Wert für das View-Attribut `api_key_fence_mode`.
  - `def fenced_visible_workspace_ids(auth_context: AuthContext) -> tuple[UUID, ...]` —
    Schnittmenge aus `api_key_workspace_ids`, Workspaces des Tenants und Workspaces, in denen
    der Key-Owner eine nicht suspendierte Rolle hält (eine Query auf `UserRole` mit
    `workspace_id__in=…`); hält der Owner die Tenant-Admin-Rolle, entfällt die Rollenbedingung
    (gleiche Elevation wie `test_tenant_admin_elevation_still_reaches_workspace_named_route`,
    `test_sec02_sec03_workspace_fence.py:672`). Leeres Tupel für ungefencte Keys ist **nicht**
    zulässig: Aufruf nur bei gefenctem Key (Assertion).
  - `def fenced_collection_roles(auth_context: AuthContext) -> tuple[str, ...]` — Vereinigung
    der Owner-Rollen über `fenced_visible_workspace_ids`.
  - `def is_fence_filtered_list(view: Any) -> bool` —
    `getattr(view, "api_key_fence_mode", None) == API_KEY_FENCE_FILTER and getattr(view, "action", None) == "list"`.
  - `def api_key_fence_precheck(request: Any, view: Any, auth_context: AuthContext) -> str | None`
    — für gefencte Keys: `None` bei `is_fence_filtered_list`, sonst
    `workspace_fence_denial(ids, resolve_target_workspace_id(request, view))`.
- **Änderung `enforce_request_scope` (`:917-923`):** Fence-Denial entfällt, wenn
  `is_fence_filtered_list(view)`.
- **TDD:** `backend/auth_tenancy/tests/test_fenced_visible_workspaces_1444.py` — (a) Owner mit
  Rolle in A und B, Key auf [A, C] → `(A,)`; (b) Owner Tenant-Admin → `(A, C)` sofern beide im
  Tenant; (c) Fremd-Tenant-UUID im Fence wird nie geliefert; (d) suspendierte Rolle zählt nicht.
- **DoD:** 4 Tests grün; keine neue Query für ungefencte Keys (Test mit
  `django_assert_num_queries` auf einen Bearer-Request, unverändert gegenüber Basis).

#### E1.2 — REST: Fence vor RBAC, gefilterte Workspace-Liste, sprechende Fehler (senior-developer)

- **Ändern:**
  - `backend/rest_api/auth_enforcer.py:114` (vor `decide_access`) und
    `backend/auth_tenancy/rest.py:480` (Zwilling): bei `auth_context.api_key_workspace_ids`
    zuerst `api_key_fence_precheck` → `PermissionDenied(detail=<Fence-Text>)`. Bei
    `is_fence_filtered_list(view)` RBAC mit `fenced_collection_roles(ctx)` statt
    `ctx.active_roles` entscheiden.
  - Denial-Text für gefencten Key, dessen Owner im Ziel-Workspace keine Rolle hat:
    `"RBAC denied: the API key owner holds no active role in workspace <uuid> (the key is workspace-scoped)."`
    statt `"RBAC denied: no active role permits 'read'"`.
  - `backend/rest_api/views.py:6303` `WorkspaceViewSet`: `api_key_fence_mode = "filter"`.
  - `backend/application/workspace_service.py:177-187` `list_workspaces`: bei gefenctem `ctx`
    zusätzlich `.filter(id__in=fenced_visible_workspace_ids(ctx))`. Die Filterung sitzt im
    Service, damit REST und MCP (E1.3) dieselbe Liste bekommen.
- **REST-Vertrag `GET /api/v1/workspaces/` (X-API-Key, gefenct):** 200
  `{"count":1,"next":null,"previous":null,"page_size":25,"max_page_size":100,"results":[{"id":"<A>","name":"…",…}]}`;
  Owner ohne Rolle in irgendeinem Fence-Workspace → 403
  `{"error":{"code":"PERMISSION_DENIED","message":"RBAC denied: the API key owner holds no active role in any workspace of this key's scope.","details":[]}}`.
  Bearer/ungefencter Key: unverändert.
- **REST-Vertrag workspace-loser Aufruf außerhalb der Liste** (z. B. `GET /api/v1/search/?q=x`
  ohne `workspace_id`): 403 mit Fence-Text aus `resource_scope.py:693-697` statt „RBAC denied".
- **TDD:** `backend/rest_api/tests/test_api_key_fence_rest_1444.py`:
  `test_fenced_key_lists_only_its_workspaces`, `test_fenced_key_without_owner_role_gets_specific_403`,
  `test_fenced_key_workspaceless_call_names_the_fence`, `test_bearer_list_unchanged`.
- **DoD:** Tests grün; `test_sec02_sec03_workspace_fence.py` vollständig grün (keine Regression).

#### E1.3 — MCP: `workspace.list` fence-gefiltert (senior-developer)

- **Ändern:**
  - `backend/mcp_server/workspace_scope.py`: neue Konstante
    `FENCE_FILTERED_TOOLS: frozenset[str] = frozenset({"workspace.list"})`.
  - `backend/mcp_server/tool_registry.py:1515-1531`: Fence-Denial entfällt, wenn
    `tool_name in FENCE_FILTERED_TOOLS and context.scope_workspace_id is None`; die Filterung
    leistet `list_workspaces` (E1.2).
  - `backend/mcp_server/tools/cross_cutting.py:540` Tool-Beschreibung um „For a
    workspace-scoped API key: only the workspaces the key is issued for and its owner holds a
    role in." ergänzen. **Delta 0 Tools, 0 Präfixe**; die geänderte Beschreibung erfordert
    `python manage.py export_tool_manifest` (nur Manifest); Doku-Zähler bleiben unverändert (Index §f.1).
- **MCP-Vertrag:** `tools/call workspace.list {}` mit gefenctem Key →
  `result.content[0].text` = `{"workspaces":[{"id":"<A>","name":"…","description":"…"}],"count":1}`;
  `workspace.query {}` (global) bleibt `-32001` (unverändert).
- **TDD:** `backend/mcp_server/tests/test_workspace_list_fenced_1444.py`.
- **DoD:** Test grün. Tool-PR-Zeile (Index §f.1): `python manage.py export_tool_manifest`;
  Zahl in `README.md`, `docs/api/MCP-SURFACE.md`, `clients/registry.yaml` prüfen (Delta 0 → keine
  Änderung, sonst angleichen und `python3 scripts/clients/render.py`); `.meta-config/project.yaml`
  nur über `agent-meta-manager` (hier unverändert, ENT-X5); `pytest docs/agent-templates dist -q` und
  `pytest mcp_server/tests/test_tool_manifest_drift.py -q` grün; Merge über die globale Tool-Queue
  (Index §d.2).

#### E1.4 — Matrix-Test REST+MCP je Key (tester, Review senior-developer)

- **Neu:** `backend/rest_api/tests/test_api_key_principal_matrix_1444.py`.
- **Matrix:** Keys {Bearer-User, ungefencter User-Key `write`, gefencter Agent-Key `read_only`,
  gefencter Agent-Key `author`, gefencter Agent-Key `admin`} × Aufrufe {Liste Workspaces
  (REST `GET /workspaces/`, MCP `workspace.list`), Lesen im Fence (REST
  `GET /requirements/?workspace_id=A`, MCP `requirement.query {workspace_id:A}`), Lesen
  außerhalb (B), Schreiben im Fence (REST `PATCH /requirements/<id>/`, MCP `requirement.update`),
  Schreiben außerhalb}.
- **Prüfgegenstand:** je Zeile **gleiche Entscheidungsklasse** an beiden Türen (allow/deny) und
  bei deny gleiche Fehlerkategorie (`PERMISSION_DENIED` ↔ JSON-RPC `-32001`) mit Fence- bzw.
  Scope-Text. Die erwartete Tabelle steht als Literal im Test (keine abgeleiteten Erwartungen).
- **MCP-Aufruf:** echter `POST /mcp/` mit Header `X-API-Key` (JSON-RPC 2.0), kein Dispatcher-Mock.
- **DoD:** Matrix grün; der Test schlägt gegen `b175c970` für die Zeile „Liste Workspaces ×
  gefencter Key" fehl (Nachweis im PR).

#### E1.5 — `POST /api/v1/api-keys/`: gesammelte Validierung + OpenAPI-Body (developer)

- **Neu:** `backend/rest_api/api_key_serializers.py`:
  - `class ApiKeyCreateSerializer(UnknownFieldRejectionMixin, serializers.Serializer)` mit
    `name` (CharField, required, trim), `principal_type` (ChoiceField `user|agent`, default
    `user`), `agent_label` (CharField, max 255, default ""), `scope` (CharField, optional,
    normalisiert über `normalize_api_key_scope`), `workspace_ids` (ListField[UUIDField], default
    []), `expires_at` (DateTimeField, optional).
  - `validate()` sammelt die Agent-Regeln in **ein** `ValidationError`-Dict: `scope` fehlt/
    ungültig, `workspace_ids` leer, `expires_at` fehlt/naiv/nicht in der Zukunft — Texte
    wortgleich zu `authentication.py:691,694-696,711-713`.
  - Unbekannte Felder: zusätzlich Vorschlag per `difflib.get_close_matches(field, allowed, n=1, cutoff=0.6)`:
    `"Unknown field 'workspace_id' — did you mean 'workspace_ids'?"`.
  - `class ApiKeyCreatedSerializer` (Response-Schema: `id, name, plaintext, warning, principal_type, agent_label, scope`).
- **Ändern:** `backend/rest_api/api_key_views.py:229-391` — `create` validiert über den
  Serializer, `@extend_schema(request=ApiKeyCreateSerializer, responses={201: ApiKeyCreatedSerializer, 400: ErrorResponseSerializer})`;
  `_ALLOWED_CREATE_FIELDS` (`:47-56`) wird aus den Serializer-Feldern abgeleitet. Der
  Service (`create_api_key`) behält seine Prüfungen als zweite Linie; Key-Limit bleibt eigener
  400 nach erfolgreicher Validierung.
- **REST-Vertrag:** Request `{"name":"x","principal_type":"agent","workspace_id":"<uuid>"}` → 400
  ```json
  {"error":{"code":"VALIDATION_ERROR","message":"4 field errors.","details":[
    {"field":"workspace_id","errors":["Unknown field 'workspace_id' — did you mean 'workspace_ids'?"]},
    {"field":"scope","errors":["Agent API keys require an explicit valid scope."]},
    {"field":"workspace_ids","errors":["Agent API keys require at least one canonical workspace UUID."]},
    {"field":"expires_at","errors":["Agent API keys require a strictly future timezone-aware expires_at."]}]}}
  ```
  Hinweis: DRF führt `validate()` erst aus, wenn alle Felder für sich gültig sind; deshalb
  prüft der Serializer die Unknown-Field-Regel in `to_internal_value` **zusammen** mit den
  Agent-Regeln (Mixin-Fehler werden gesammelt, nicht sofort geworfen). Erfolgreich: 201 wie
  bisher (`api_key_views.py:378-391`).
- **TDD:** `backend/rest_api/tests/test_api_key_create_collected_errors_1439.py` —
  (a) obige Anfrage → genau eine 400 mit 4 `details`; (b) gültiger Agent-Key → 201;
  (c) `user`-Key nur mit `name` → 201 (Rückwärtskompatibilität); (d) Schema-Test:
  `paths["/api/v1/api-keys/"]["post"]["requestBody"]` enthält `workspace_ids`, `expires_at`.
- **DoD:** Tests grün; `test_api_key_agent_fields.py`, `test_readonly_and_unknown_field_rejection_915_916.py`,
  `test_api_key_limit_vs_scope_917.py` grün.

#### E1.6 — Hermes-Plugin zeigt den Ablehnungsgrund (developer)

- **Ändern:** `integrations/hermes-agent-plugin/dashboard/dist/index.js` (keine Build-Quelle im
  Repo; `dist/` ist die Quelle): in `loadAll` (`:1816-1822`) und beim Serverwechsel
  (`:2042-2044`) `workspaceResult.error` auswerten → State `workspaceError`
  (`{message, code}`); im Picker (`:2181-2192`) bei Fehler statt „none visible" ein
  `h("p", {"data-testid": "reqlo-workspace-error", role: "alert"}, text)` mit
  `text = "Workspaces could not be loaded: " + message` und bei `code === "PERMISSION_DENIED"`
  dem Zusatz `"The configured key is workspace-scoped or lacks read access."`.
  Leere, fehlerfreie Liste bleibt „none visible".
- **TDD:** `integrations/hermes-agent-plugin/tests/plugin_ui_flow.mjs` neuer Fall „workspaces
  error is rendered, not empty"; `tests/test_plugin_api.py` neuer Fall: `/workspaces` reicht
  `code` aus dem MCP-Fehler durch.
- **DoD:** CI-Job `hermes-plugin-test` grün (pytest + „Drive the dashboard components").

### WP E2 — API-Vertrag ehrlich (Welle 0; E2.8, E2.9 Welle 2)

#### E2.1 — Baselines: Tenant-Fallback im Preset-Gate entfernen (developer)

- **Ändern:** `backend/rest_api/preset_guard.py:236-240` — der Fallback
  `str(auth_ctx.tenant_id)` entfällt; ohne Workspace gilt der vorhandene Zweig
  `if workspace_id is None: return` (`:241-242`), danach validiert die View.
- **Folge:** `GET /api/v1/baselines/` ohne `workspace_id` → **400**
  `{"error":{"code":"VALIDATION_ERROR","message":"'workspace_id' is required.","details":[]}}`
  (Text aus `parse_workspace_id`, `backend/rest_api/query_params.py:88-89`); mit
  `workspace_id` → 200 (unverändert). Routenreihenfolge in `urls.py:312-314` bleibt.
- **TDD:** `backend/rest_api/tests/test_baseline_workspace_routing.py` neu
  `test_flat_list_without_workspace_id_is_400_not_404` und
  `test_flat_list_with_workspace_id_is_200`; Ratchet gegen die Klasse aus #1380:
  `backend/rest_api/tests/test_declared_list_paths_reachable_1380.py` — für jeden Schema-Pfad
  ohne Pfadparameter mit `get` gilt: Antwort ∈ {200, 204, 400}, nie 404/405 (Admin-Bearer,
  echte Views; Pfade, die ohne Query nicht sinnvoll sind, liefern 400).
- **DoD:** beide Tests grün; `test_baseline_detail_route_398.py`, `test_baseline_views.py` grün.

#### E2.2 — Comments: Routen ehrlich (developer)

- **Ändern:** `backend/rest_api/urls.py:284` Router-Registrierung entfernen; vor
  `path("", include(router.urls))` (`:1115`) explizit:
  `path("comments/<uuid:pk>/", CommentViewSet.as_view({"delete": "destroy"}), name="comment-detail")`,
  `path("comments/<uuid:pk>/resolve/", CommentViewSet.as_view({"post": "resolve"}), name="comment-resolve")`.
  `backend/rest_api/collaboration_views.py:115-140` (Stubs `list/create/retrieve/partial_update`) löschen.
- **Vertrag (Breaking, benannt):** `GET|POST /api/v1/comments/` 405 → **404** (Route existiert
  nicht); `GET|PATCH /api/v1/comments/<pk>/` → 405 mit `Allow: DELETE, OPTIONS`;
  `POST …/resolve/` und `DELETE …/<pk>/` unverändert (Frontend `frontend/src/api/comments.ts:74,79`).
- **TDD:** `backend/rest_api/tests/test_comment_endpoints.py:141-181` ersetzen durch geroutete
  Tests (`APIClient`): 404 für Collection, 405 + `Allow` für Detail-GET/PATCH; Schema-Test:
  `/api/v1/comments/` fehlt im Schema.
- **DoD:** `test_comment_endpoints.py` grün; Frontend-Kommentar-Tests (`npm test -- comments`) grün.

#### E2.3 — TraceLink-Detail: echtes GET, kein PATCH (developer)

- **Neu:** `backend/application/trace_link_service.py` `def get_trace_link(self, link_id: UUID, ctx: AuthContext) -> TraceLink`
  (Tenant-Kontext setzen, `NotFoundError` bei fehlendem/fremdem Link; Muster wie
  `delete_trace_link` `:1160`).
- **Ändern:** `backend/rest_api/views.py:4060-4063` `retrieve` nutzt den Service +
  `_tracelink_to_dict` (Titel via `_resolve_artifact_titles`); `:4093-4098` Stub
  `partial_update` löschen und am `TraceLinkViewSet` `http_method_names = ["get", "post", "delete", "head", "options"]`.
- **Vertrag:** `GET /api/v1/tracelinks/<id>/` (und Alias `trace-links`) → 200 TraceLink-JSON,
  404 bei unbekannt/fremd; `PATCH` → 405 durch DRF, Schema ohne `patch`.
- **Ziel-Sichtbarkeit (QR-S20):** Der Fence leitet den Workspace aus der **Quelle** ab
  (`resource_scope.py:339-350`). Titel und UID des Link-**Ziels** gibt `retrieve` nur aus, wenn der
  Aufrufer READ auf den Ziel-Workspace hat; sonst `target_title: null` (`_tracelink_to_dict`,
  `views.py:5905-5909`) und UID-Felder des Ziels, falls vorhanden, `"—"`.
  Gleiche Regel wie Plan A T-A3-3 (KA-A-20).
- **TDD:** `backend/rest_api/tests/test_tracelink_crud_rest.py:150-154` ersetzen durch
  `test_retrieve_returns_the_link` und `test_retrieve_foreign_tenant_is_404`; zusätzlich
  `test_retrieve_roleless_workspace_is_403_or_404`, `test_retrieve_hides_target_title_of_unreadable_workspace`
  und `test_retrieve_fenced_key_foreign_workspace_link_is_403` (gefencter Key auf Link mit Quelle
  außerhalb des Fence).
- **DoD:** alle `test_tracelink_*` grün.

#### E2.4 — If-Match strikt (senior-developer)

- **Ändern:** `backend/rest_api/mixins/etag.py`:
  - `class IfMatchKind(StrEnum)`: `ABSENT, ANY, STRONG, WEAK, MALFORMED`;
    `def classify_if_match(header: str | None) -> tuple[IfMatchKind, str | None]` —
    Header fehlt → ABSENT; leer/Whitespace, Liste mit >1 Tag, nicht RFC-konform → MALFORMED;
    `*` → ANY; `W/"…"` → WEAK; `"…"` → STRONG(value).
  - `ETagMixin.etag_supported: ClassVar[bool] = False`.
  - `def validate_if_match(self, request: Request) -> None` — nur für PATCH/PUT/DELETE/POST auf
    Detailrouten: MALFORMED → `MalformedPrecondition` (400); WEAK → `PreconditionFailed` (412);
    STRONG auf View mit `etag_supported=False` → 412; STRONG bei `DELETE` → 400 (`If-Match is
    evaluated on PATCH/PUT only.`; vorläufig, ENT-E4 = A); ANY/ABSENT → weiter. Exceptions nach Muster
    `MalformedUuidInPath` (`backend/rest_api/views.py:453-463`, Body = fertiger Umschlag).
  - `uses_if_match` → nur noch `True` bei STRONG (behebt die 412/409-Verwechslung bei `*`).
  - `resolve_expected_version`: STRONG mit Nicht-Ganzzahl → `-1` (passt nie → Service wirft
    `OptimisticLockError` → bestehender 412-Zweig, z. B. `views.py:1551-1555`).
  - **Abbildung `OptimisticLockError` → 409/412 (verbindlich, plan-übergreifend; Plan B B6 und
    Plan F F2/F3 verlassen sich darauf):** neue Methode
    `def optimistic_lock_response(self, request: Request, exc: OptimisticLockError, lang: str) -> Response`
    am `ETagMixin`:
    - Request trägt **STRONG** `If-Match` (`uses_if_match` = True) → **412** `PRECONDITION_FAILED`
      über `precondition_failed` (`etag.py:237`).
    - sonst (Body-`expected_version`, `If-Match: *`, kein Header) → **409** `CONFLICT` über
      `_service_error_response(exc, lang)`; das generische Mapping
      `OptimisticLockError: HTTP_409_CONFLICT` in `_EXC_TO_STATUS` (`views.py:278`) bleibt
      **unverändert**.
    - Jede View mit `etag_supported=True` fängt `OptimisticLockError` **vor** dem generischen
      `except Exception` und ruft `optimistic_lock_response`. Der bestehende Zweig
      `views.py:1551-1555` (Requirement) und die Zwillinge `views.py:3667` (TestCase), `:5058`
      (Baseline), `:6552` (Workspace) werden auf den Helfer umgestellt (gleiches Verhalten). Ein bis `_service_error_response`
      durchgereichter `OptimisticLockError` bei STRONG `If-Match` wäre ein Vertragsbruch (409 statt
      412) — dagegen steht der Ratchet-Test unten.
- **Ändern:** `backend/rest_api/views.py:516-527` `BaseEntityViewSet.initial`: nach
  `_reject_malformed_uuid_path_kwargs` `self.validate_if_match(request)`.
- **Vertrag (Matrix, Requirement mit Version 6):** `"6"`→200 · `"1"`/`"999"`→412 ·
  `W/"6"`/`W/"1"`→412 · `garbage`/`""`/`"6", "7"`→400 · `*`→200 · ohne Header→200
  (Last-Writer-Wins, unverändert) · Body `expected_version: 1` ohne Header → 409 (unverändert) ·
  `*` + Body `expected_version: 1` → **409** (bisher 412).
  Ressource ohne ETag (z. B. Goal): `"1"`→412, `*`→200, ohne Header→200.
  Fehlerumschläge: 400 `{"error":{"code":"VALIDATION_ERROR","message":"If-Match must be '*' or exactly one strong entity-tag such as \"3\".","details":[{"field":"If-Match","errors":["malformed"]}]}}`;
  412 `{"error":{"code":"PRECONDITION_FAILED",…}}` (vorhandener Text, `serializers.py:144`).
- **TDD:** `backend/rest_api/tests/test_if_match_strict_1396.py` (obige Matrix, echte PATCHes,
  Datenbankzustand nach 412/400 unverändert); `test_etag_optimistic_locking_868.py:137-146`
  Parametrisierung um `classify_if_match` erweitern; `test_if_match_star_is_an_existence_check`
  (`:266`) bleibt gültig. Neu `backend/rest_api/tests/test_optimistic_lock_status_mapping.py`:
  `test_optimistic_lock_with_strong_if_match_is_412`, `test_optimistic_lock_with_body_version_is_409`,
  `test_optimistic_lock_with_star_if_match_is_409` (Unit am Helfer) und
  `test_every_etag_view_routes_optimistic_lock_through_helper` (statisch: jede im Router
  registrierte View mit `etag_supported=True` ruft in `partial_update`/`update`
  `optimistic_lock_response` auf, geprüft über `inspect.getsource`; schlägt fehl, sobald ein Plan eine
  neue ETag-View ohne den Helfer anlegt; nicht-leer ab E2.5, beide im selben PR P1-2). Das
  Laufzeitverhalten je Typ prüft E2.5 (c)/(d).
- **Hinweis Workflow-Transitions:** die POST-Detail-Aktionen (`workflow_transitions.py:236,494`)
  bekommen nur das Syntax-Gate (400/412 für malformed/weak); ihre Semantik (Engine-Version) bleibt
  (Befund RB-09). Das Schema deklariert dort **kein** `If-Match` (E2.6).
- **DoD:** Tests grün; `test_workspace_etag_412_1244.py`, `test_etag_on_create_1079.py`,
  `frontend/src/api/requirements-etag.test.ts` grün.

#### E2.5 — ETag für alle Typen mit Versionsprüfung (developer)

- **Ändern `backend/rest_api/views.py`** je ViewSet: `etag_supported = True`; `retrieve` und
  `partial_update` antworten über `self.with_etag(…, <entity mit version>)`;
  `expected_version=data.get("expected_version")` → `self.resolve_expected_version(request, data)`;
  `except OptimisticLockError as exc: return self.optimistic_lock_response(request, exc, lang)` vor
  dem generischen `except Exception` (Abbildung 409/412 aus E2.4). Umfang vorläufig, ENT-E2 = A
  (Hybrid).

  | ViewSet | retrieve | partial_update | expected_version-Zeile |
  |---|---|---|---|
  | StakeholderNeedViewSet | `:788` | `:862` | `:887` (pop) |
  | ArchitectureElementViewSet | `:2652` | `:2854` | `:2898` |
  | AdrViewSet | `:6929` | `:7158` | `:7200` |
  | RiskViewSet | `:7403` | `:7475` | `:7530` |
  | IssueViewSet | `:8447` | `:8509` | `:8565` |
  | ChangeRequestViewSet | `:8727` | `:8796` | `:8837` |
  | GlossaryTermViewSet | `:10405` | `:10613` | `:10660` |

  Zusätzlich `etag_supported = True` an Requirement (`:1189`), TestCase (`:3424`), Baseline
  (`:4707`), Workspace (`:6303`). Ohne Versionsprüfung bleiben `False`: Goal, MainGoal, TestRun,
  Artifact, TraceLink, WorkflowDefinition (Zusage eingeschränkt, im Schema dokumentiert, E2.6).
- **Korrektur aus Review (RB-07):** `compute_etag` fällt auf Zeitstempel zurück, wenn das
  übergebene Objekt kein `version` trägt (`etag.py:85-93`). Für die 7 Typen muss das an
  `with_etag` übergebene Objekt `version` tragen (ORM-Instanz oder DTO mit `version`); sonst
  wäre der Tag ein Zeitstempel und jedes `If-Match` liefe auf 412.
- **Plan-übergreifende Regel (QR-T13):** Neue mutable Typen anderer Pläne setzen
  `etag_supported=True` **nur** mit `version`-Feld am Modell und `expected_version` im Service und
  nutzen `optimistic_lock_response` (E2.4); sonst `etag_supported=False` mit ehrlicher 412-Zusage
  (E2.6). Betroffen: Plan B B6 (`Milestone`, KA-B-06), Plan F F2/F3 (`Document`, `WorkItem`).
  Index §f.8 verweist hierauf.
- **TDD:** `backend/rest_api/tests/test_etag_all_versioned_types_1397.py` — je Typ:
  (a) GET → `ETag == '"%d"' % body["version"]`; (b) PATCH mit aktuellem Tag → 200 + neuer Tag;
  (c) PATCH mit veraltetem Tag → 412, DB unverändert; (d) Body-`expected_version` veraltet ohne
  Header → 409.
- **DoD:** 7×4 Fälle grün; bestehende Entity-Tests der 7 Typen grün;
  `test_optimistic_lock_status_mapping.py` (E2.4) grün.

#### E2.6 — OpenAPI deklariert `If-Match`, `ETag`, 412 ehrlich (senior-developer)

- **Ändern:** `backend/rest_api/openapi.py` neuer Postprocessing-Hook
  `def declare_conditional_requests(result: dict[str, Any], generator: Any, request: Any, public: bool) -> dict[str, Any]`;
  Registrierung `backend/reqogniloom/settings.py:716-718` nach `enforce_common_error_responses`.
  Der Hook liest `generator.endpoints` (Pfad, Methode, View-Klasse) und je View `etag_supported`:
  - `etag_supported=True`: PATCH/PUT bekommen Header-Parameter
    `{"name":"If-Match","in":"header","required":false,"schema":{"type":"string"},"description":"Strong entity-tag from ETag, e.g. \"3\", or *. Weak tags fail with 412, malformed values with 400."}`,
    Responses 400/412; GET-Detail und PATCH-200 bekommen `headers.ETag`.
  - `etag_supported=False`: PATCH/PUT erhalten nur 412 mit Beschreibung „This resource carries
    no ETag; any If-Match entity-tag fails (RFC 9110 §13.1.1)."; kein `If-Match`-Parameter.
  - Transition-POSTs: keine Deklaration (RB-09).
  - Die Deklaration folgt allein `etag_supported`; neue Views anderer Pläne (B6, F2/F3) werden ohne
    Änderung am Hook korrekt beschrieben. Umfang vorläufig, ENT-E2 = A.
- **TDD:** `backend/rest_api/tests/test_openapi_conditional_requests_1396.py` — Schema per
  `SchemaGenerator().get_schema(request=None, public=True)`: alle PATCH-Ops der 11
  ETag-Views (inkl. Alias-Pfade `test-cases`, `change-requests`/`changerequests`) haben
  `If-Match` + 412; GET-Detail hat `ETag`; keine Op einer `etag_supported=False`-View hat
  `If-Match`.
- **DoD:** Test grün; `test_openapi.py` grün.

#### E2.7 — Ratchet gegen stille Schema-Beschneidung (#1388) (developer)

- **Neu:** `backend/rest_api/tests/test_openapi_generation_warnings_1388.py` und
  `backend/rest_api/tests/openapi_warning_baseline.json`
  (`{"unable_to_guess_serializer": [<ViewName>…], "path_param_type": […], "operation_id_collision": […]}`).
- **Mechanik:** `GENERATOR_STATS.reset()` (`drf_spectacular.drainage`), dann
  `call_command("spectacular", "--file", str(tmp_path / "schema.yaml"))` mit
  `contextlib.redirect_stderr`; Zeilen `^(Warning|Error) \[(\w+)\]: (.*)$` klassifizieren.
  Neuer Eintrag ⇒ Fehlschlag („add serializer_class or @extend_schema"); verschwundener
  Eintrag ⇒ Fehlschlag („shrink the baseline") — die Liste kann nur schrumpfen.
- **Erstbefüllung:** einmalige Generierung im PR; erwartete Größenordnung 107–124
  `unable_to_guess_serializer` (E-L14), 1 `path_param_type` (`WorkspaceViewSet`), 9 Kollisionen (E-L13).
- **Plan-übergreifende Regel (QR-T12):** `openapi_warning_baseline.json` ist ab dem Merge von
  P1-7 **Konfliktdatei aller Pläne** (Index §d.2). Jeder spätere REST-PR (A, B, C, F, G und E2.8)
  - versieht neue Views mit `serializer_class` oder `@extend_schema` (neue Einträge = Fehlschlag;
    der PR löst sie im Code, nie durch Anheben der Baseline),
  - aktualisiert die Baseline selbst, wenn seine Änderung Einträge entfernt (**nur Shrink**),
  - rebased vor dem Merge auf `main`, erzeugt die Baseline neu und merged **seriell** in der Queue
    (Index §d.2). Die DoD-Zeile dafür steht in den anderen Plänen (KA-ALL-04).
- **DoD:** Test grün mit Baseline; PR-Beschreibung nennt die Zählung.

#### E2.8 — Burn-down der Baseline (developer; Welle 2, je Batch ein PR)

- **Eintritt:** P1-7 gemergt; Ziel „Burn-down bis 0“ vorläufig, ENT-E1 = A (bei B: dauerhafte
  Allowlist, E2.8 entfällt). Welle-2-Priorität laut Index §d.1: E2.8 zuletzt.

- Je View: `serializer_class` (wenn ein Serializer existiert) oder
  `@extend_schema(request=…, responses=…)`; reine Aktions-Views ohne Body:
  `@extend_schema(request=None, responses={204: None})`. Kollisionen über
  `@extend_schema(operation_id="…")`. `WorkspaceViewSet`: `lookup_value_regex` UUID +
  `OpenApiParameter("id", OpenApiTypes.UUID, OpenApiParameter.PATH)`.
- **Batches (aus `views-without-serializer-static.txt`):** B1 `memory/` (12) · B2 `admin_ops/` (13)
  · B3 `auth_tenancy/` + `reqogniloom/` + `rest_api/api_key_views.py` (≈5, inkl. Kollisionen)
  · B4–B7 `rest_api/` (78) nach Datei in 4 Batches à ≤ 20 Views.
- **TDD je Batch:** E2.7 schlägt fehl, bis die Baseline-Einträge des Batches entfernt sind;
  zusätzlich je Batch ein Schema-Assert, dass die Ops nun 2xx-Content haben.
- **DoD je Batch:** Baseline um die Batch-Views kürzer; Zahl der Ops ohne 2xx-Body sinkt
  (Gegenprobe auf QS nach Deploy: Auswertung wie E-L14).

#### E2.9 — Listen-Query-Parameter (`status`, `include_deleted`) im OpenAPI deklarieren (developer; Welle 2, nach G PR 6)

- **Herkunft:** Übergabe Plan G §4.1 (G-L16 / R9): `/testcases/?status=` wird still ignoriert; das
  OpenAPI deklariert für `/testcases/` und `/requirements/` nur `page`, `page_size` (Beleg G-L16).
- **Eintritt:** Plan G PR 6 (G2.1) gemergt (gleiche Datei `rest_api/views.py`, W2-Queue
  G PR 6 → **E2.9** → G PR 19, Index §d.2); P1-7 gemergt (OpenAPI-Baseline existiert);
  Soft-Delete-Vertrag nach ENT-G1 (vorläufig A, Plan G G1.5 V4).
- **Ändern:** `backend/rest_api/views.py` — `@extend_schema(parameters=[…])` auf den `list`-Aktionen,
  die `parse_include_deleted` (`rest_api/query_params.py:110`) bzw. einen `status`-Filter
  (`views.py:1298`, `:8704`) auswerten: `OpenApiParameter("include_deleted", OpenApiTypes.BOOL)`,
  `OpenApiParameter("status", OpenApiTypes.STR)` nur dort, wo der Service filtert, dazu `workspace_id`,
  `page`, `page_size` laut bestehendem `_paginate`-Vertrag. ViewSets, die `?status=` heute still
  ignorieren (`TestCaseViewSet`), filtern entweder über den Service oder antworten `400`
  `VALIDATION_ERROR` (`unsupported filter`) — nie stilles Ignorieren.
- **TDD:** neu `backend/rest_api/tests/test_openapi_list_params.py` — (a) Schema per
  `SchemaGenerator().get_schema(request=None, public=True)`: jede `list`-Op eines soft-deletenden
  ViewSets deklariert `include_deleted`; jede Op mit Status-Filter deklariert `status`;
  (b) `GET /api/v1/testcases/?workspace_id=<ws>&status=outdated` liefert nur `outdated`-Zeilen oder `400`;
  (c) Menge der deklarierten Pfade wird über die Registry/den Generator ermittelt, keine feste Zahl.
- **DoD:** Test grün; `test_openapi.py` und E2.7-Ratchet grün; `openapi_warning_baseline.json` nur
  Shrink, Merge seriell (Index §d.2); Liste deterministisch sortiert (Plan G G2.1); CHANGELOG nennt
  `400` für bisher ignorierte Filter als sichtbare Änderung. Fallback, falls E2.9 nicht umgesetzt
  wird: Plan G PR 19 deklariert nur `include_deleted` (Plan G §4.1).

### WP E3 — 2FA/TOTP für Staff (Welle 3)

#### E3.0 — Gate: Sign-off + dependency-check + ADR-Nachtrag-Entwurf (Nutzer, dependency-auditor, Rolle laut ENT-X4)

- **Sign-off (Nutzer-Gate U-2):** neue Dependency `pyotp==2.10.0` (Pin exakt, Lizenz MIT, keine
  Laufzeit-Abhängigkeiten). Ohne Sign-off startet E3.1 nicht.
- **dependency-check (dependency-auditor):** manueller Paved-Road-Lauf (kein CI-Job, Index §f.2):
  `pip-audit` gegen die geänderte `backend/requirements.txt`, Lizenzprüfung, SBOM-Eintrag, Prüfung
  der Wheel-Herkunft (PyPI Trusted Publishing/Hash). Ergebnis als Kommentar im PR P3-1. CI-Nachweis
  über pip-audit im Job `backend-test` Set `set-1-core`.
- **ADR (Rolle laut ENT-X4 + Nutzer; vorläufig, ENT-X4 = A: `documenter` Text, `concept-reviewer`
  Review):** Nachtrag O5 in `docs/se/ADR/ADR-021_admin_login_lockout.md:335-339`:
  „2026-…: Residuum durch TOTP-2FA (#1308, Plan E/E3) geschlossen. Übergangsfenster `optional`
  befristet bis **<Datum>**; danach `MFA_STAFF_ENFORCEMENT=required` nach Cutover (E3.9). Die
  Risiko-Akzeptanz endet mit `required`. Staff-API-Keys ohne zweiten Faktor bleiben akzeptiertes
  Restrisiko mit Inventur und `expires_at`-Pflicht (ENT-E8)." Datum und Befristung vorläufig,
  ENT-E6 = A + Befristung; Staff-Key-Satz vorläufig, ENT-E8 = A. Kein Statuswechsel des ADR.
- **DoD:** Sign-off dokumentiert (Issue #1308, durch den Nutzer), pip-audit 0 Funde,
  Nachtrag-Text mit Datum im PR P3-1.

#### E3.1 — Datenmodell + Migrationen (senior-developer)

- **Ändern:** `backend/auth_tenancy/models.py` (nach `AdminLoginLockout`, `:907-969`):
  - `class UserTotpDevice(AuditableModel)`, `db_table = "at_user_totp_device"`:
    `user = OneToOneField(settings.AUTH_USER_MODEL, on_delete=CASCADE, related_name="totp_device")`,
    `secret_ciphertext = TextField()` (Fernet über `encrypt_secret`),
    `confirmed_at = DateTimeField(null=True)`, `last_used_step = BigIntegerField(null=True)`,
    `failed_attempts = PositiveSmallIntegerField(default=0)`, `locked_until = DateTimeField(null=True)`.
  - `class UserRecoveryCode(AuditableModel)`, `db_table = "at_user_recovery_code"`:
    `user = ForeignKey(AUTH_USER_MODEL, CASCADE, related_name="recovery_codes")`,
    `code_hash = CharField(max_length=80, unique=True)`, `used_at = DateTimeField(null=True)`.
  - `class UserMfaEnrollmentGrant(AuditableModel)`, `db_table = "at_user_mfa_enrollment_grant"`
    (vorläufig, ENT-E7 = A; entfällt bei ENT-E7 = B):
    `user = ForeignKey(AUTH_USER_MODEL, CASCADE, related_name="mfa_enrollment_grants")`,
    `expires_at = DateTimeField()` (≤ 24 h nach Anlage), `used_at = DateTimeField(null=True)`,
    `created_by = CharField(max_length=150)`, `reason = TextField()`. Gültig = `used_at IS NULL` und
    `expires_at > now`; höchstens ein gültiger Grant je User (neuer Grant setzt ältere auf `used_at`).
  - Scope global wie `AdminLoginLockout` (Pre-Auth-Pfad, kein Tenant bekannt) → keine RLS;
    Docstring nennt die Begründung; `persistence/tests/test_rls_coverage.py` betrifft nur
    `TenantScopedModel`, ist Pflicht-Check des PRs und bleibt grün.
- **Migration** `backend/auth_tenancy/migrations/0031_user_mfa.py` (Name/Nummer laut Index §e;
  CreateModel ×3, rein additiv; `dependencies` = zuletzt gemergte `auth_tenancy`-Migration, erwartet
  `0030_backfill_show_readable_ids`; merged Plan C `0032_…` vorher, gilt max+1, Index §e Regel 1).
- **Ändern:** `backend/audit/models.py:212-246` neue Ops `user.mfa_enroll`, `user.mfa_disable`,
  `user.mfa_recovery_used`, `user.mfa_recovery_regenerate`, `user.mfa_reset`,
  `user.mfa_enroll_grant` (ENT-E7), `user.mfa_cutover` (E3.9); Migration
  `backend/audit/migrations/0016_alter_auditentry_op_mfa.py` (AlterField choices, `dependencies`
  `0015_alter_auditentry_op`).
- **Rollback:** Revert + `python manage.py migrate auth_tenancy <name-der-vorgänger-migration>`
  (erwartet `0030_backfill_show_readable_ids`) und `python manage.py migrate audit 0015_alter_auditentry_op`
  (löscht Enrollments und Grants; vorher `MFA_STAFF_ENFORCEMENT=off`). Expand-only,
  rückwärtskompatibel zum vorigen Release.
- **TDD:** `backend/auth_tenancy/tests/test_mfa_models.py` — OneToOne-Eindeutigkeit,
  `code_hash` unique, Cascade beim User-Löschen, ein gültiger Grant je User; Rückwärts-Probe per
  `MigrationExecutor` mit Migrationsnamen (`loader.graph.leaf_nodes()`), keine nackten Nummern.
- **DoD:** `python manage.py makemigrations --check --dry-run` → `No changes detected`;
  Rückwärts-Probe `migrate auth_tenancy <vorgänger>` → `migrate auth_tenancy` rund.

#### E3.2 — `MfaService` (senior-developer, Review security-auditor)

- **Neu:** `backend/auth_tenancy/services/mfa.py`.
- **Settings** (`backend/reqogniloom/settings.py`, neben `:568-582`, alle per Env):
  `MFA_STAFF_ENFORCEMENT` (`off|optional|required`, Default `optional`),
  `MFA_TOTP_ISSUER` (Default `"ReqogniLoom"`), `MFA_MAX_FAILED_ATTEMPTS` (5),
  `MFA_LOCKOUT_SECONDS` (900), `MFA_CHALLENGE_TTL_SECONDS` (300), `MFA_TOTP_VALID_WINDOW` (1),
  `MFA_ENROLL_GRANT_TTL_SECONDS` (86400, Obergrenze 86400 — größere Werte → `ImproperlyConfigured`;
  vorläufig, ENT-E7 = A).
- **Schnittstelle:**
  - `def mfa_required(user: User) -> bool` — `off` → False; `optional` → bestätigtes Gerät
    vorhanden; `required` → `user.is_staff or user.is_superuser` oder bestätigtes Gerät.
  - `def begin_enrollment(user: User) -> EnrollmentData` (`secret_b32`, `otpauth_uri`) —
    `pyotp.random_base32(length=32)` (160 Bit), `TOTP(...).provisioning_uri(name=user.username, issuer_name=MFA_TOTP_ISSUER)`;
    ersetzt ein unbestätigtes Gerät; bei bestätigtem Gerät `MfaAlreadyEnrolledError`.
    Nur Staff (`is_staff or is_superuser`), sonst `MfaNotAllowedError`.
  - `def confirm_enrollment(user: User, code: str) -> list[str]` — prüft Code, setzt
    `confirmed_at`, erzeugt 10 Recovery-Codes (`secrets.choice` über Base32-Alphabet, 16 Zeichen
    = 80 Bit, Format `XXXX-XXXX-XXXX-XXXX`), speichert `hash_api_key(normalize(code))`
    (gepfefferter HMAC, `authentication.py:138-164`), gibt Klartexte **einmalig** zurück.
  - `def verify(user: User, *, code: str | None = None, recovery_code: str | None = None) -> Literal["totp", "recovery"]`.
  - `def regenerate_recovery_codes(user: User, code: str) -> list[str]`,
    `def disable(user: User, *, password: str, code: str) -> None`,
    `def reset(user: User, *, actor: str) -> None` (Break-glass, E3.7).
  - `def issue_challenge(user: User, *, purpose: Literal["verify", "enroll"]) -> str` und
    `def read_challenge(token: str) -> tuple[User, str]` —
    `django.core.signing.TimestampSigner(salt="reqlo.mfa.challenge.v1")`, Inhalt
    `{"uid", "purpose", "n": secrets.token_urlsafe(16)}`, `max_age=MFA_CHALLENGE_TTL_SECONDS`.
    `def consume_challenge(token: str) -> tuple[User, str]` — wie `read_challenge`, markiert die
    Nonce nach **erfolgreichem** zweiten Faktor als verbraucht:
    `cache.add(f"mfa:challenge:used:{n}", 1, timeout=MFA_CHALLENGE_TTL_SECONDS)`; liefert `add`
    False → 401 `MFA_CHALLENGE_INVALID`. Cache-Ausfall → `MfaUnavailableError` (fail-closed).
  - `def grant_enrollment(user: User, *, actor: str, reason: str) -> UserMfaEnrollmentGrant` und
    `def has_valid_enrollment_grant(user: User) -> bool` (vorläufig, ENT-E7 = A) — Anlage nur über
    E3.7 (`mfa_reset`, Admin-Aktion); Audit `user.mfa_enroll_grant`; der Grant wird in
    `confirm_enrollment` unter `select_for_update` verbraucht (`used_at`).
- **Sicherheitsregeln (verbindlich):**
  1. **Secret-Speicherung:** nur als Fernet-Ciphertext (`FIELD_ENCRYPTION_KEY`), nie im Klartext,
     nie in Logs/Audit/Responses nach der Enrollment-Antwort. Entschlüsselung **strikt**:
     fehlendes Fernet-Präfix oder `InvalidToken` → `MfaUnavailableError` (fail-closed, Login
     verweigert) — `decrypt_secret`s Klartext-Durchreichung (`encryption.py:51-60`) wird dafür
     nicht verwendet (eigener Helper `_decrypt_totp_secret`).
  2. **Replay:** Zeitschritt des akzeptierten Codes muss `> last_used_step` sein; Update unter
     `select_for_update()` auf das Gerät (zwei parallele Requests mit demselben Code: genau einer gewinnt).
  3. **Brute-Force:** Fenster ±1 Schritt (3 gültige Codes/1e6). Jeder Fehlschlag
     `failed_attempts += 1`; ab `MFA_MAX_FAILED_ATTEMPTS` → `locked_until = now + MFA_LOCKOUT_SECONDS`
     (Recovery-Codes eingeschlossen); Erfolg setzt zurück. Zusätzlich DRF-Throttles
     `LoginRateThrottle`/`LoginIpRateThrottle` auf dem MFA-Endpunkt (E3.4). Erwartete
     Erfolgschance eines Angreifers bei 5 Versuchen/15 min: ≤ 1,5e-5 pro Sperrfenster.
  4. **Vergleich:** `hmac.compare_digest` für TOTP-Kandidaten. Recovery-Lookup **immer**
     user-gebunden: `UserRecoveryCode.objects.select_for_update().get(user=user, code_hash=…)` —
     nie global per Hash (QR-S11).
  4a. **Challenge einmalig:** Eine Challenge-Nonce ist nach Erfolg bis zum Ablauf der TTL verbraucht
     (`consume_challenge`); ein zweiter Erfolg mit derselben Challenge → 401 (QR-S11).
  5. **Recovery-Codes:** einmalig (`used_at` unter `select_for_update`), Normalisierung
     (Großschreibung, `-`/Leerzeichen entfernen); Regenerierung invalidiert alle alten.
  6. **Audit:** Enroll/Disable/Recovery-Nutzung/Regenerierung/Reset als `AuditEntry` (wenn der
     User einen Tenant hat), immer zusätzlich Logger `reqogniloom.security` (ohne Codes/Secret).
- **TDD:** `backend/auth_tenancy/tests/test_mfa_service.py` — echte Codes über
  `pyotp.TOTP(secret).at(t)`: Annahme gültig, Replay abgewiesen, ±1 Fenster, Sperre nach 5,
  Recovery einmalig, strikter Decrypt (manipulierter Ciphertext → `MfaUnavailableError`),
  Nicht-Staff-Enrollment abgewiesen, Regenerierung invalidiert alte Codes, paralleler
  Doppel-Verify (zwei Threads, `transaction=True`) → genau ein Erfolg;
  `test_recovery_code_of_other_user_rejected`, `test_mfa_challenge_single_use`,
  `test_enroll_grant_is_single_use_and_expires` (ENT-E7), `test_grant_ttl_above_24h_is_rejected`.
- **DoD:** Tests grün; `ruff` lokal sauber (kein CI-Job, Index §f.2); security-auditor-Review ohne
  offene `high`.

#### E3.3 — `amr` im Token (senior-developer)

- **Ändern:** `backend/auth_tenancy/services/password_authentication.py:176` und `:219`:
  `issue_token(user, roles=None, *, amr: tuple[str, ...] = ("pwd",))`,
  `issue_refresh_token(user, *, session_id=None, amr=("pwd",))` — Claim `amr` (RFC 8176).
  Validierung übernimmt `amr` in `IdentityClaims`; `AuthContext` (`backend/auth_tenancy/context.py:100-140`)
  bekommt `amr: tuple[str, ...] = ()`. `RefreshView` (`backend/rest_api/auth_views.py:404-470`)
  überträgt `amr` aus dem alten Refresh-Token.
- **Rückwärtskompatibel:** Tokens ohne `amr` gelten als `("pwd",)`.
- **Step-up beim Refresh (QR-S10):** Ist `mfa_required(user)` wahr und fehlt `"otp"` im `amr` des
  Refresh-Tokens, verweigert `RefreshView` (`backend/rest_api/auth_views.py:379`) mit 401
  `{"error":{"code":"MFA_STEP_UP_REQUIRED",…}}` und widerruft die Familie nicht (der Nutzer meldet
  sich neu mit zweitem Faktor an). Alt-Tokens ohne Claim fallen damit für MFA-Nutzer heraus.
- **TDD:** `backend/auth_tenancy/tests/test_token_amr.py` (Roundtrip, Refresh behält `amr`,
  Alt-Token ohne Claim); `backend/rest_api/tests/test_login_mfa_1308.py::test_refresh_without_otp_rejected_when_required`.

#### E3.4 — REST-Login zweistufig (senior-developer)

- **Ändern:** `backend/rest_api/auth_views.py:291-346` `LoginView.post`: nach
  `authenticate_credentials` (`:311`) bei `mfa_required(user)`:
  - Gerät bestätigt → 200 `{"mfa_required": true, "mfa_challenge": "<signed>", "methods": ["totp", "recovery_code"]}`,
    **keine** Cookies, **kein** Body-Token, `reset_login_throttle` (`:324`) **nicht** aufrufen.
  - `required` und kein Gerät **und gültiger Enrollment-Grant** → 200
    `{"mfa_enrollment_required": true, "mfa_challenge": "<signed purpose=enroll>"}`.
  - `required` und kein Gerät **ohne** Grant → 403
    `{"error":{"code":"MFA_ENROLLMENT_REQUIRES_GRANT","message":"A second factor is required. Ask an administrator for an enrollment grant.","details":[]}}`;
    keine Challenge, keine Cookies, kein Token (QR-S01; vorläufig, ENT-E7 = A). Bei ENT-E7 = B:
    Grace-Fenster nur für Konten jünger als N h plus Benachrichtigung, Risikoakzeptanz im
    ADR-021-Nachtrag.
  - sonst unverändert.
- **Eintritt:** ENT-E7 entschieden (Sicherheitsgate vor Welle 3).
- **Neu:** `LoginMfaView` → `POST /api/v1/auth/login/mfa/` (`backend/rest_api/urls.py` neben `:298`),
  `permission_classes=[AllowAny]`, `throttle_classes=[LoginRateThrottle, LoginIpRateThrottle]`.
  - Request `{"mfa_challenge": "…", "code": "123456"}` oder `{"mfa_challenge": "…", "recovery_code": "ABCD-EFGH-IJKL-MNOP"}`.
  - 200: identisch zur heutigen Login-Erfolgsantwort (Cookies + Body-Felder), Token mit
    `amr=("pwd","otp")`.
  - Fehler: 400 `VALIDATION_ERROR` (beide/kein Faktor) · 401 `MFA_CHALLENGE_INVALID`
    (Signatur/abgelaufen) · 401 `MFA_INVALID_CODE` · 429 `MFA_LOCKED` mit `Retry-After` ·
    503 `MFA_UNAVAILABLE` (Secret nicht entschlüsselbar).
- **Neue Fehlercodes** in `backend/rest_api/serializers.py` (Katalog neben `:144`) DE/EN.
- **TDD:** `backend/rest_api/tests/test_login_mfa_1308.py` — Staff mit Gerät: Schritt 1 ohne
  Cookie/Token, Schritt 2 mit gültigem Code → Cookies + `amr`; abgelaufene Challenge 401;
  Sperre 429; Recovery-Code einmalig; Nicht-Staff ohne Gerät unverändert;
  `test_required_unenrolled_staff_cannot_self_enroll_without_grant` (403, keine Cookies);
  `test_mfa_challenge_single_use` (Login-Schritt 2 zweimal → 401);
  `test_login_body_token_deprecation_696.py` und `test_auth_login.py` grün.

#### E3.5 — Django-Admin-Login mit zweitem Faktor (developer)

- **Ändern:** `backend/auth_tenancy/admin_login.py`: `class MfaAdminAuthenticationForm(LockoutAdminAuthenticationForm)`
  mit `otp_code = CharField(required=False, widget=TextInput(attrs={"autocomplete": "one-time-code", "inputmode": "numeric"}))`;
  `clean()`: `super().clean()` (Lockout + Passwort, `:114`), danach bei `mfa_required(user)`
  `MfaService.verify` (6 Ziffern → TOTP, sonst Recovery); Fehlschlag sendet
  `user_login_failed` mit `credentials={"username": …}`, damit der ADR-021-Zähler greift;
  `required` ohne Gerät → `ValidationError("Enroll a second factor in the web app first.")`
  (Web-Enrollment unter `required` nur mit Enrollment-Grant, E3.4/E3.7; vorläufig, ENT-E7 = A).
  `install()` (`:188`) setzt `admin.site.login_form = MfaAdminAuthenticationForm`.
- **Neu:** `backend/auth_tenancy/templates/admin/login.html` (erweitert Djangos Template,
  rendert `form.otp_code`; ohne Override zeigt das Standard-Template das Feld nicht).
- **TDD:** `backend/auth_tenancy/tests/test_admin_login_mfa.py` (Client-POST auf `/admin/login/`:
  ohne Code → Fehler, falscher Code zählt im Lockout, richtiger Code → Session).
  `test_admin_login_lockout.py` grün.

#### E3.6 — Enrollment-API + Härtung der Key-Anlage (senior-developer)

- **Neu:** `backend/rest_api/mfa_views.py`, Routen in `backend/rest_api/urls.py`:

  | Methode + Pfad | Request | 2xx | Fehler |
  |---|---|---|---|
  | `GET /api/v1/auth/mfa/status/` | – | 200 `{"enrolled":bool,"confirmed_at":str\|null,"recovery_codes_remaining":int,"enforcement":"off\|optional\|required","required":bool}` | 401 |
  | `POST /api/v1/auth/mfa/totp/enroll/` | `{}` (Session) oder Header `X-MFA-Challenge` (purpose=enroll) | 201 `{"secret":"BASE32…","otpauth_uri":"otpauth://totp/ReqogniLoom:admin?secret=…&issuer=ReqogniLoom","digits":6,"period":30}` | 403 `MFA_NOT_ALLOWED`, 403 `MFA_ENROLLMENT_REQUIRES_GRANT` (`required` ohne Grant), 409 `MFA_ALREADY_ENROLLED` |
  | `POST /api/v1/auth/mfa/totp/confirm/` | `{"code":"123456"}` | 200 `{"confirmed_at":"…","recovery_codes":["XXXX-…" ×10]}`; im Challenge-Fluss (nur mit Grant) zusätzlich Login-Erfolg (Cookies, `amr=("pwd","otp")`) | 400, 401 `MFA_INVALID_CODE`, 401 `MFA_CHALLENGE_INVALID` (verbraucht/abgelaufen), 403 `MFA_ENROLLMENT_REQUIRES_GRANT`, 429 `MFA_LOCKED` |
  | `POST /api/v1/auth/mfa/recovery-codes/regenerate/` | `{"code":"123456"}` | 200 `{"recovery_codes":[…]}` | 401, 429 |
  | `POST /api/v1/auth/mfa/disable/` | `{"password":"…","code":"123456"}` | 204 | 401, 409 `MFA_REQUIRED` (Staff bei `required`) |

  - **Enrollment-Grant (QR-S01; vorläufig, ENT-E7 = A):** Unter `MFA_STAFF_ENFORCEMENT=required`
    stellen `enroll` und `confirm` nur bei gültigem Grant (`has_valid_enrollment_grant`) eine
    Enrollment aus — gilt für den Challenge-Fluss (`X-MFA-Challenge`, purpose=enroll) **und** für
    eine Session. Ohne Grant → 403 `MFA_ENROLLMENT_REQUIRES_GRANT`. `confirm` verbraucht den Grant
    und schreibt Audit `user.mfa_enroll` mit `details.source = "challenge" | "session"`. Unter
    `optional` bleibt Session-Enrollment ohne Grant (der Nutzer ist bereits voll angemeldet). Die
    Challenge wird bei erfolgreichem `confirm` per `consume_challenge` verbraucht.
  - Enrollment ohne QR-Code (Secret + `otpauth://`-Link; vorläufig, ENT-E5 = A).
  - Alle schreibenden MFA-Routen: nur interaktive Sessions (Bearer/Cookie); `auth_method == API_KEY`
    → 403 `MFA_REQUIRES_INTERACTIVE_SESSION` (ein geleakter Key kann kein Gerät umschreiben).
  - `Cache-Control: no-store` auf enroll/confirm/regenerate.
  - Permission wie `LogoutView` (`backend/rest_api/auth_views.py:364`, `HasOperationPermission`
    ohne `required_operation` → authentifiziert genügt); `drf-spectacular`-Serializer für jede
    Route (kein neuer Eintrag in der E2.7-Baseline).
- **Ändern:** `backend/rest_api/api_key_views.py` `create`: bei `MFA_STAFF_ENFORCEMENT=required`
  und Staff-Owner ohne `"otp" in ctx.amr` → 403 `MFA_REQUIRED` (sonst umgeht ein per
  Passwort-only-Altsession erzeugter Key die 2FA).
- **Ändern (vorläufig, ENT-E8 = A):** `backend/auth_tenancy/services/authentication.py:644`
  `create_api_key`: bei `MFA_STAFF_ENFORCEMENT=required` und Staff-Owner (`is_staff or is_superuser`)
  ist `expires_at` Pflicht (timezone-aware, in der Zukunft) — auch für `principal_type=user`; sonst
  400 `VALIDATION_ERROR` mit Feldfehler `expires_at` (in der Sammel-400 aus E1.5). Bindung an
  `required` (nicht `optional`), weil das heutige UI (`frontend/src/components/UserProfileSettings/ApiKeysSection.tsx`)
  kein Ablaufdatum sendet; E3.8 ergänzt das Feld vor dem Umschalten. Bestehende Staff-Keys bleiben
  gültig und erscheinen in der Cutover-Inventur (E3.9).
- **Eintritt:** ENT-E7 entschieden (wie E3.4).
- **TDD:** `backend/rest_api/tests/test_mfa_views_1308.py` (alle Zeilen der Tabelle, API-Key → 403,
  `no-store`-Header, `test_required_unenrolled_staff_cannot_self_enroll_without_grant` für Session
  und Challenge, `test_enroll_via_challenge_writes_audit_with_source_challenge`),
  `test_api_key_create_requires_mfa_session_1308.py` (inkl. `test_staff_key_without_expires_at_is_400`).
- **DoD:** Jede neue Route mit `drf-spectacular`-Serializer; `openapi_warning_baseline.json` ohne
  neuen Eintrag, Merge seriell in der Baseline- und `urls.py`-Queue (Index §d.2).

#### E3.7 — Break-glass-Reset (developer)

- **Neu:** `backend/auth_tenancy/management/commands/mfa_reset.py` —
  `python manage.py mfa_reset <username> --reason "<text>"`: löscht Gerät + Codes (falls vorhanden),
  schreibt `user.mfa_reset`-Audit + `reqogniloom.security`-Log; Exit 1 bei unbekanntem User.
  Zusätzlich (vorläufig, ENT-E7 = A) legt der Command einen Enrollment-Grant an
  (`MfaService.grant_enrollment`, TTL `MFA_ENROLL_GRANT_TTL_SECONDS` ≤ 24 h, Audit
  `user.mfa_enroll_grant`). Das ist die „Admin-Aktion“ für neue Staff-Konten (Bootstrap-Admin,
  Admin-Anlage) und für verlorene Geräte; kein eigenes UI in v1.
- **TDD:** `backend/auth_tenancy/tests/test_mfa_reset_command.py` (inkl.
  `test_reset_creates_single_use_grant`, `test_reset_for_never_enrolled_staff_creates_grant`).
- **Doku:** `deploy/README.md` Abschnitt „2FA: Gerät verloren / neues Staff-Konto".

#### E3.8 — Frontend (frontend-component-engineer)

- **Eintritt:** Plan D P3-1 (D6.2, `seed_demo`-Guard) gemergt; `seed_demo.py` und
  `test_seed_demo.py` werden auf `main` rebased (Merge-Queue **D P3-1 → E P3-5**, Index §d.2, QR-T19).
  CSS-Änderungen unterliegen dem Design-System-Ratchet (`frontend/src/test/design-system-ratchet.baseline.json`,
  Deckel nur senken; Rebase nach den C1-PRs); `i18n/locales/{de,en}.json` in der seriellen
  i18n-Queue mit Paritätstest (Index §d.2).

- **Neu:** `frontend/src/api/mfa.ts` (`getMfaStatus`, `enrollTotp`, `confirmTotp`,
  `regenerateRecoveryCodes`, `disableMfa`, `loginMfa`), `frontend/src/components/UserProfileSettings/SecuritySection.tsx`
  (+ `.module.css`, `SecuritySection.test.tsx`), Export in `index.ts`, Einbindung in
  `UserProfileSettings.tsx`. CSS nur aus `styles/tokens.css`.
- **Ändern (vorläufig, ENT-E8 = A):** `frontend/src/components/UserProfileSettings/ApiKeysSection.tsx`
  + `frontend/src/api/api-keys.ts` — optionales Feld „Ablaufdatum“ (`expires_at`,
  `data-testid="api-key-expires-input"`), Pflicht, wenn `GET /auth/mfa/status/`
  `enforcement: "required"` und `required: true` meldet (Server-Regel E3.6); `frontend/src/test/ApiKeysSection.test.tsx` erweitern.
- **Ändern:** `frontend/src/context/AuthContext.tsx:234-260` — `login()` erkennt
  `mfa_required`/`mfa_enrollment_required` und liefert `{kind: "mfa", challenge}` bzw.
  `{kind: "enroll", challenge}`; `frontend/src/components/NavigationShell/LoginPage.tsx:127-180`
  zweiter Schritt.
- **data-testid:** `login-mfa-step`, `login-mfa-code-input`, `login-mfa-recovery-toggle`,
  `login-mfa-recovery-input`, `login-mfa-submit`, `login-mfa-error`, `mfa-section`,
  `mfa-status`, `mfa-enroll-btn`, `mfa-secret`, `mfa-otpauth-link`, `mfa-confirm-code-input`,
  `mfa-confirm-btn`, `mfa-recovery-codes`, `mfa-recovery-copy-btn`, `mfa-recovery-download-btn`,
  `mfa-regenerate-btn`, `mfa-disable-btn`, `mfa-disable-password-input`, `mfa-disable-code-input`.
- **i18n (DE / EN)** in `frontend/src/i18n/locales/{de,en}.json`:
  `login.mfa.title` „Zweiter Faktor" / „Second factor" · `login.mfa.codeLabel` „6-stelliger Code" / „6-digit code" ·
  `login.mfa.useRecovery` „Recovery-Code verwenden" / „Use a recovery code" ·
  `login.mfa.recoveryLabel` „Recovery-Code" / „Recovery code" · `login.mfa.submit` „Bestätigen" / „Verify" ·
  `login.mfa.invalidCode` „Code ungültig." / „Invalid code." ·
  `login.mfa.locked` „Zu viele Fehlversuche. Erneut in {{minutes}} min." / „Too many attempts. Try again in {{minutes}} min." ·
  `login.mfa.expired` „Anmeldung abgelaufen, bitte neu anmelden." / „Sign-in expired, please sign in again." ·
  `login.mfa.enrollRequired` „Für dieses Konto ist ein zweiter Faktor Pflicht." / „This account requires a second factor." ·
  `mfa.title` „Zwei-Faktor-Anmeldung" / „Two-factor sign-in" · `mfa.statusOn` „Aktiv seit {{date}}" / „Active since {{date}}" ·
  `mfa.statusOff` „Nicht eingerichtet" / „Not set up" · `mfa.enroll` „Einrichten" / „Set up" ·
  `mfa.secretHint` „Secret in der Authenticator-App eintragen oder Link öffnen." / „Enter the secret in your authenticator app or open the link." ·
  `mfa.confirm` „Code bestätigen" / „Confirm code" ·
  `mfa.recoveryTitle` „Recovery-Codes — jetzt sichern, sie werden nicht erneut angezeigt." / „Recovery codes — save them now, they are not shown again." ·
  `mfa.copy` „Kopieren" / „Copy" · `mfa.download` „Herunterladen" / „Download" ·
  `mfa.regenerate` „Neue Recovery-Codes" / „New recovery codes" · `mfa.disable` „Deaktivieren" / „Disable" ·
  `mfa.requiredByPolicy` „Durch Richtlinie vorgeschrieben" / „Required by policy" ·
  `mfa.remaining` „{{count}} Recovery-Codes übrig" / „{{count}} recovery codes left".
- **TDD:** `SecuritySection.test.tsx`, `LoginPage.test.tsx` (MFA-Schritt), Vitest gegen
  MSW-freie Fetch-Stubs wie in bestehenden Tests.
- **E2E:** `e2e/tests/mfa-totp.spec.ts` mit eigenem Staff-User `e2e-mfa` (siehe Korrektur
  RB-12), TOTP im Test über Node-`crypto` (`e2e/helpers/totp.ts`, RFC 6238, keine npm-Dependency);
  Fluss: Enroll → Confirm → Logout → Login mit Code → Recovery-Code → Disable.
- **Korrektur aus Review (RB-12):** E2E darf den gemeinsamen `admin` nicht enrollen (parallele
  Shards würden beim Login in den MFA-Schritt laufen). `seed_demo` legt `e2e-mfa` (Staff, Rolle
  im Demo-Workspace) **nur** an, wenn `E2E_MFA_PASSWORD` gesetzt ist (nur
  `testing/docker-compose.test.yml` und Playwright-CI); idempotent. Der Opt-in ist unabhängig von
  `SEED_DEMO_ALLOW_DEFAULT_PASSWORD` aus D6.2 (vorläufig, ENT-D9 = B); `e2e-mfa` nutzt nie das
  Default-Passwort. Die E2E-Umgebung läuft mit `MFA_STAFF_ENFORCEMENT=optional`, das
  Session-Enrollment braucht dort keinen Grant (E3.6).

#### E3.9 — Cutover vor `required`: `mfa_enforce_cutover` (senior-developer, Review security-auditor)

- **Neu:** `backend/auth_tenancy/management/commands/mfa_enforce_cutover.py` —
  `python manage.py mfa_enforce_cutover [--dry-run] [--format text|json]` (QR-S10):
  1. **Refresh-Tokens:** widerruft je Tenant (TenantContext per Kontextmanager, vorheriger Wert im
     `finally` wiederhergestellt, Index §f.8) alle lebenden Refresh-Familien von Staff-Usern
     (`is_staff or is_superuser`) — ohne Ausnahme, weil `amr` nur im Token und nicht in der Tabelle
     steht; Staff mit Gerät meldet sich einmal neu mit Code an — über
     `revoke_refresh_family(session_id, reason="mfa_cutover")`
     (`backend/auth_tenancy/services/refresh_token_store.py:117`).
  2. **Django-Admin-Sessions:** löscht `django.contrib.sessions`-Zeilen, deren `_auth_user_id` ein
     Staff-User ist.
  3. **Staff-API-Keys:** listet alle nicht widerrufenen Keys mit Staff-Owner über `collect_inventory`
     (`backend/auth_tenancy/management/commands/inventory_api_keys.py:342`), ohne Key-Material.
     Kein Widerruf (vorläufig, ENT-E8 = A: Inventur + `expires_at`-Pflicht für neue Staff-Keys, E3.6);
     bei ENT-E8 = B zusätzlich Option `--revoke-staff-keys`.
  4. Audit `user.mfa_cutover` je betroffenem User mit Tenant; Logger `reqogniloom.security` mit
     Summen (ohne Token/Key-Material). `--dry-run` zählt nur.
- **Runbook:** `deploy/README.md` Abschnitt „2FA: Umschalten auf `required`“: (1) Enrollment aller
  Staff prüfen (`GET /api/v1/auth/mfa/status/` je Konto bzw. Command-Ausgabe), (2)
  `mfa_enforce_cutover --dry-run`, (3) `mfa_enforce_cutover`, (4) `MFA_STAFF_ENFORCEMENT=required`
  in der Env setzen und `make up` (kein `restart`). Restrisiko: bereits ausgestellte Access-Tokens
  laufen bis zu ihrem Ablauf weiter.
- **TDD:** `backend/auth_tenancy/tests/test_mfa_enforce_cutover.py` — `test_cutover_revokes_staff_sessions`
  (Refresh-Familie widerrufen, Admin-Session gelöscht, Nicht-Staff unberührt),
  `test_cutover_lists_staff_api_keys` (kein Key-Material in der Ausgabe),
  `test_cutover_dry_run_changes_nothing`, `test_cutover_restores_tenant_context`.
- **DoD:** Tests grün; Runbook-Abschnitt im selben PR.

## (v) Abhängigkeiten

**Task → Task:** E1.1 → E1.2 → E1.3 → E1.4 · E1.5 unabhängig · E1.6 unabhängig (fachlich nach
E1.3 sinnvoll, technisch nicht) · E2.4 → E2.5 → E2.6 · E2.7 → E2.8 · E2.7 → E2.9 (nach Plan G PR 6) ·
E2.1, E2.2, E2.3 unabhängig ·
E3.0 → E3.1 → E3.2 → {E3.3, E3.7} → E3.4 → E3.5 → E3.6 → E3.8 · E3.2 → E3.9 (vor dem
Umschalten auf `required`; fachlich nach E3.3/E3.6) · ENT-E7 → E3.1 (Grant-Modell), E3.4, E3.6, E3.7.

**Plan → Plan** (bindend: Index §c/§d.2):
- **`backend/rest_api/views.py`, Welle-0-Queue (QR-T14):** E P1-1 → E P1-2 → E P1-4 → **Plan G
  PR 5 (G1.5)** → E P1-3 → E P1-7 (P1-7 zusätzlich nach P1-5). G1.5 ändert `destroy`/Listen-Zweige
  derselben ViewSets wie E2.3/E2.4/E2.5; wer später merged, rebased und läuft die gezielten Tests neu.
- **OpenAPI-Ratchet (QR-T12):** Ab P1-7 ist `openapi_warning_baseline.json` Konfliktdatei aller
  REST-PRs (A, B, C, F, G, E2.8, E3.4/E3.6): nur Shrink, seriell (E2.7).
- **ETag/If-Match (QR-T13):** Plan B B6 (`Milestone`) und Plan F F2/F3 übernehmen den Vertrag aus
  E2.4–E2.6: `etag_supported=True` nur mit `version` + `expected_version` + `optimistic_lock_response`
  (412 bei STRONG `If-Match`, 409 bei Body-`expected_version`), sonst `etag_supported=False`. Plan B
  stützt sich auf `views.py:278` (409) und den E2.4-Helfer (412).
- **E2.1 → Plan F:** F4.2/F4.4 und `baseline 0012_baselinetag` (PR-F9) mergen nach E P1-1 (Index §e).
- **MCP-Manifest:** P1-4 (E1.3, nur Beschreibung, Delta 0) läuft in der globalen Tool-Queue (Index §d.2).
- **`auth_tenancy`-Migrationen (QR-T03):** Plan C belegt 0028–0030 (Welle 1/2); E3.1 nimmt
  `0031_user_mfa` nach PR-C7a (Index §e). Merged der C-Contract `0032_…` vorher, tauschen die Nummern.
- **`seed_demo.py` (QR-T19):** Plan D P3-1 (D6.2) → E P3-5 (E3.8), beide Welle 3.
- **`backend/requirements.txt`:** Plan A PR-A1 (Welle 1) → E P3-1 (Welle 3), `requirements-drift-check`.
- **`backend/rest_api/urls.py`:** E P1-1 (Welle 0), E P3-3/P3-4 (Welle 3) in der seriellen Queue.
- **Frontend:** E P3-5 in der Design-System-Ratchet- und i18n-Queue (Index §d.2). Plan C0 (#598
  ErrorBoundary) und E3.8 haben keine gemeinsamen Dateien.
- **#1407 R3-08** („API-Key im `Authorization: Bearer`“): **erledigt durch Plan G G5.3** (by design,
  REQ-L2-AT-002, Pin-Test nach E P1-4); keine E1-Task. Bedingung an E1: der Fence wirkt über
  `validate_api_key` für `X-API-Key` und `Authorization: Bearer reqlo_…` gleich (Plan G §4.1).
- **Listen-Query-Parameter (Plan G G-L16 / R9):** E2.9 (Welle 2), `views.py`-W2-Queue
  G PR 6 → E2.9 → G PR 19 (Index §d.2).

## (vi) Rollout, Feature-Flags, Fallback

| Bereich | Schalter | Verhalten bei nicht verfügbarer Komponente |
|---|---|---|
| E1 Fence | bestehendes `AUTHZ_API_KEY_WORKSPACE_FENCE_ENFORCED` (`resource_scope.py:711-716`, Default True) | Schalter aus → kein Fence, Liste wieder tenant-weit (Altverhalten). Kein neuer Schalter. |
| E1 Plugin | – | Server ohne E1 → Plugin zeigt den Fehlertext (E1.6 wirkt unabhängig). |
| E2.4 If-Match strikt | kein Flag (Vertragsfix); Rollback = Revert | Clients, die heute `W/…` oder Müll senden, bekommen 412/400 statt stillem 200 — gewollt, im CHANGELOG als Breaking benannt. |
| E2.2 Comments | – | Breaking 405→404 für `/comments/` (Collection) im CHANGELOG. |
| E3 | `MFA_STAFF_ENFORCEMENT=off\|optional\|required` (Default `optional`) | `off`: Login wie heute. `FIELD_ENCRYPTION_KEY` falsch/rotiert → `MFA_UNAVAILABLE` 503 für betroffene Konten, **fail-closed**; Notweg `mfa_reset` (E3.7). Redis (Django-Cache) trägt die Challenge-Nonce (E3.2 Regel 4a): Ausfall → 503 `MFA_UNAVAILABLE` im zweiten Login-Schritt, fail-closed. Celery nicht beteiligt. |
| E3 Einführung | Release N: `optional`; Übergangsfenster **befristet** (Datum im ADR-021-Nachtrag, E3.0; vorläufig, ENT-E6 = A + Befristung). Nach Enrollment aller Staff-Konten: Cutover `mfa_enforce_cutover` (E3.9), dann setzt der Betreiber `required` (`make up`, kein `restart`). Neue Staff-Konten danach nur per Enrollment-Grant (`mfa_reset`, E3.7; vorläufig, ENT-E7 = A). Staff-API-Keys: Inventur beim Cutover, `expires_at`-Pflicht für neue (vorläufig, ENT-E8 = A). | Fällt der Sign-off für `pyotp` aus, ruht E3 (Fallback ohne Dependency: RFC-6238 mit `hmac`/`struct`, ~25 Zeilen — nur nach neuer Nutzerentscheidung). Rückweg von `required`: Env auf `optional`, `make up`. |

## (vii) Risiken und Gegenmaßnahmen

| Risiko | Gegenmaßnahme |
|---|---|
| Fence-Liste öffnet einem Key Workspaces, in denen der Owner keine Rolle hat | Schnittmenge mit Owner-Rollen (E1.1), Test (a)/(d) |
| RBAC-Union für die Liste wird auf andere Views übertragen | Flag nur an `WorkspaceViewSet`, nur `action == "list"` (E1.1 `is_fence_filtered_list`) |
| Strikte If-Match-Regeln brechen Fremd-Clients | Breaking im CHANGELOG; Frontend nutzt nur starke Tags (`requirements.ts:284`) |
| ETag aus Zeitstempel statt Version (RB-07) | E2.5 Test (a) je Typ |
| Ratchet zu laut (Warn-Texte ändern sich mit drf-spectacular-Upgrade) | Klassifikation nur über `[ViewName]` + Kategorie, nicht über Volltext; Pin `<1.0` (`requirements.txt:43`) |
| Ratchet blockiert REST-PRs anderer Pläne (QR-T12) | Plan-übergreifende Regel E2.7: neue Views mit Serializer/`@extend_schema`, Baseline nur Shrink, Merge seriell (Index §d.2); DoD-Zeile in A/B/C/F/G (KA-ALL-04) |
| ETag-View eines anderen Plans liefert 409 statt 412 oder Zeitstempel-Tag (QR-T13) | `optimistic_lock_response` + statischer Test (E2.4), `version`-Pflicht (E2.5-Regel) |
| Angreifer mit Staff-Passwort schreibt eigenes Gerät ein (QR-S01) | Enrollment-Grant unter `required` (E3.4/E3.6/E3.7; vorläufig, ENT-E7 = A) |
| Passwort-only-Altsitzungen laufen nach `required` weiter (QR-S10) | Refresh-Step-up (E3.3), Cutover-Command (E3.9); Restrisiko Access-Token-Laufzeit |
| Staff-API-Keys ohne zweiten Faktor (Sicherheits-Risiko 2) | akzeptiertes Restrisiko mit Inventur (E3.9) und `expires_at`-Pflicht (E3.6); vorläufig, ENT-E8 = A |
| Übergangsfenster `optional` ohne Ende (Sicherheits-Risiko 3) | Befristung im ADR-021-Nachtrag (E3.0; vorläufig, ENT-E6 = A + Befristung) |
| Recovery-Code eines fremden Kontos / Challenge-Wiederverwendung (QR-S11) | user-gebundener Lookup, Nonce-Verbrauch (E3.2 Regel 4/4a) |
| Link-Ziel-Titel aus fremdem Workspace sichtbar (QR-S20) | READ-Prüfung auf den Ziel-Workspace (E2.3) |
| Staff sperrt sich aus | Recovery-Codes, `mfa_reset`-Command, Default `optional` |
| MFA-Sperre als DoS gegen Admins | Sperre nur nach gültigem Passwort (Challenge setzt Passwort voraus); ADR-021-Lockout bleibt davor |
| Challenge-Replay innerhalb TTL | per-User-Fehlzähler über alle Challenges; TTL 300 s |
| Secret-Leak über Logs | Logger-Regel E3.2/6; Test, dass `caplog` weder Secret noch Codes enthält |
| Passwort-only-Altsession erzeugt API-Key nach `required` | E3.6 `amr`-Prüfung bei der Key-Anlage |
| E2E-Interferenz durch MFA am `admin` | eigener User `e2e-mfa` (RB-12) |

## (viii) Aufwand je WP (grob)

| WP | Aufwand | Annahmen |
|---|---|---|
| E1 (E1.1–E1.6) | 3,5–4,5 PT | Fence-Code existiert; Matrix-Test ist der größte Einzelposten (≈1 PT) |
| E2 (E2.1–E2.7) | 4–5 PT | Services der 7 Typen kennen `expected_version` bereits |
| E2.8 Burn-down | 6–8 PT | ≈107–124 Views, ≈15–20 Views/PT, 7 Batches |
| E3 (E3.0–E3.9) | 10–13 PT | ohne Wartezeit auf Sign-off; Frontend ≈3 PT, E2E ≈1 PT; Stufe 2: +≈1 PT für Enrollment-Grant (ENT-E7) und Cutover E3.9 (Index §a nennt noch die Summe vor Stufe 2) |

Zahlen sind Schätzungen des Plan-Autors; Schärfung durch `effort-estimator` (Planbasis O5).

## (ix) Entscheidung nötig

IDs laut [Entscheidungsliste](2026-10-21-entscheidungen-offen.md); alte Plan-IDs in Klammern.

| ID | Frage | Optionen | Empfehlung | Vorläufig im Plan | blockiert |
|---|---|---|---|---|---|
| ENT-E1 (D-E2a) | Ziel für #1388 | A) Ratchet + Burn-down bis 0 (E2.7 + E2.8) · B) Ratchet + dauerhafte Allowlist | **A** — B lässt die 124 Lücken für Client-Generatoren dauerhaft offen. | ja (A) | E2.8 |
| ENT-E2 (D-E2b) | „ETag für alle mutablen Typen **oder** Zusage einschränken" | A) Hybrid: ETag für die 11 Typen mit Versionsprüfung, ehrliche 412-Zusage für die übrigen 6 (E2.5/E2.6) · B) Versionsprüfung auch in Goal/MainGoal/TestRun/Artifact/TraceLink/WorkflowDefinition nachrüsten (+≈3 PT, Service-Änderungen) | **A** | ja (A) | E2.5, E2.6; wirkt auf B6, F2/F3 |
| ENT-E3 (D-E2c) ⚠ | Entscheidungs-Konflikt „`baselines/`-Routenreihenfolge" | A) Ursache beheben (E2.1), Routen unverändert · B) zusätzlich `include` hinter `router.urls` verschieben (wirkungslos, Risiko für `scope-preview/`) | **A** | ja (A) | E2.1 → F4.2/F4.4 |
| ENT-E4 (D-E2d) | `If-Match` auf `DELETE` | A) 400 „nur PATCH/PUT" (E2.4) · B) auswerten (je `destroy` laden + vergleichen, nicht atomar) | **A** | ja (A) | E2.4 |
| ENT-E5 (D-E3a) | QR-Code im Enrollment | A) v1 ohne QR (Secret + `otpauth://`-Link) · B) QR mit weiterer Dependency (Backend `segno` oder Frontend-QR-Paket, eigener Sign-off) | **A** | ja (A) | P3-4, P3-5 |
| ENT-E6 (D-E3b) | Zeitpunkt `MFA_STAFF_ENFORCEMENT=required` und Befristung des Übergangs | A) Betreiber nach Enrollment aller Staff · B) Default `required` ab Release N+1; Zusatz: Datum im ADR-021-Nachtrag | **A + Befristung** | ja (A + Befristung) | E3-Rollout, ADR-Nachtrag (E3.0) |
| ENT-E7 (neu, QR-S01) | Selbst-Enrollment unter `required` | A) nur mit einmaligem Enrollment-Grant (`mfa_reset`, TTL ≤ 24 h, Audit), ohne Grant 403 · B) Grace-Fenster für Konten jünger als N h + Benachrichtigung, Risikoakzeptanz | **A** | Text vorläufig A; **Umsetzung erst nach Entscheidung** | P3-2 (Grant-Modell), P3-3, P3-4 |
| ENT-E8 (neu, Sicherheits-Risiko 2, QR-S10) | Staff-API-Keys ohne zweiten Faktor | A) akzeptieren + Inventur + `expires_at`-Pflicht für Staff-Keys · B) beim Cutover widerrufen · C) akzeptieren ohne Zusatz | **A** | ja (A) | E3.9 (Key-Regel), E3.6 (`expires_at`) |

Gate (kein Optionspunkt): Sign-off `pyotp==2.10.0` durch den Nutzer = **Nutzer-Gate U-2** (E3.0).
Plan-übergreifend relevant: ENT-X3 (Belege, vorläufig C), ENT-X4 (ADR-Rolle, E3.0), ENT-X5
(`.meta-config/project.yaml`; P1-4 ändert dort nichts, Delta 0), ENT-D9 (`seed_demo`, E3.8).

## (x) Review-Befunde

| ID | Schwere | Beleg | Auswirkung | Korrigiert in |
|---|---|---|---|---|
| RB-01 | hoch | E-L3; `preset_guard.py:236-240` | #1380-Ursache falsch; ein Routing-Umbau hätte nichts behoben | E2.1 |
| RB-02 | hoch | `auth_enforcer.py:114-146`; `tenant_context.py:76-85` | „REST-Fence fehlt" falsch; echtes Problem: Reihenfolge + Meldung + Liste | E1.1, E1.2 |
| RB-03 | hoch | E-L12; `reqogniloom_client.py:111,732-738` | #1443-Pfad ist MCP; REST-Fix allein hätte das Plugin nicht repariert | E1.3, E1.6 |
| RB-04 | mittel | E-L6; `views.py:4060-4063,4093-4098` | `GET /tracelinks/{id}/` deklariert, aber fester 404 — gleiche Klasse wie #1380 | E2.3 |
| RB-05 | mittel | E-L5; `collaboration_views.py:115-140` | `/comments/` bewirbt GET/POST, liefert 405 | E2.2 |
| RB-06 | mittel | `etag.py:162-165`, `views.py:1551-1555` | `If-Match: *` + veraltetes Body-Feld → 412 statt 409 | E2.4 (`uses_if_match` nur STRONG) |
| RB-07 | mittel | `etag.py:85-93` | ETag kann still zum Zeitstempel werden → jedes If-Match 412 | E2.5 (Test a) |
| RB-08 | mittel | E-L8 | Issue-Liste ohne ETag unvollständig (needs, goals, test-runs) | E2.5 Tabelle, E2.6 |
| RB-09 | mittel | `workflow_transitions.py:220-236,485-498` | If-Match auf Transitions vergleicht `WorkflowItemState.version`, nicht den ETag | E2.4 (nur Syntax-Gate), E2.6 (nicht deklariert); Nicht-Ziel |
| RB-10 | mittel | `encryption.py:51-60` | `decrypt_secret` reicht Klartext durch → für TOTP fail-open | E3.2 Regel 1 |
| RB-11 | hoch | `api_key_views.py:229-391`; E3-Design | Staff könnte per Passwort-only-Session einen Key ziehen und 2FA umgehen | E3.3, E3.6 |
| RB-12 | mittel | E2E-Login als `admin` in allen Shards | Enrollment am `admin` bricht parallele E2E | E3.8 (User `e2e-mfa`) |
| RB-13 | niedrig | Django `admin/login.html` rendert nur `username`/`password` | OTP-Feld wäre unsichtbar | E3.5 Template-Override |
| RB-14 | niedrig | E-L14 | „Views fehlen im Schema" ungenau: sie fehlen nicht, sie sind ohne Body | E2.7 Klassifikation, E2.8 DoD |
| RB-15 | niedrig | E-L4 | Pfadzahl wächst (353→357) — Zahlen im Issue sind Momentaufnahmen | E2.7 (Ratchet statt fester Zahl) |
| RB-16 | niedrig | DRF `validate()` läuft erst nach gültigen Feldern | Sammel-400 wäre sonst wieder seriell | E1.5 (Sammlung in `to_internal_value`) |

**Querreview-Befunde** ([TECHNISCH](../reviews/PLAN_QUERREVIEW_2026-10-21_TECHNISCH.md),
[SICHERHEIT](../reviews/PLAN_QUERREVIEW_2026-10-21_SICHERHEIT.md)) — korrigiert in Stufe 2:

| ID | Schwere | Auswirkung | Korrigiert in |
|---|---|---|---|
| QR-T01 | kritisch | Migrationsnummern plan-übergreifend kollidierend | Kopf „Migrationen“, E3.1 — KA-ALL-01 |
| QR-T03 | hoch | `auth_tenancy 0028` widerspricht den Wellen (C vor E) | Kopf, E3.1 (`0031_user_mfa`), (v), (xii), P3-2 — KA-E-01 |
| QR-T04 | hoch | Rollback mit nackten Nummern | E3.1, P3-2 (Migrationsnamen) — KA-E-01, KA-ALL-02 |
| QR-T08 | hoch | absolute Tool-Gesamtzahl im Plan, Doku-Zähler nicht genannt | E1.3 (Delta 0, Tool-DoD), P1-4 — KA-E-10, KA-ALL-03 |
| QR-T12 | mittel | OpenAPI-Ratchet blockiert REST-PRs anderer Pläne | E2.7 (plan-übergreifende Regel), (v), (vii) — KA-E-09 |
| QR-T13 | mittel | ETag-Vertrag für neue Typen (B6, F2/F3) unklar | E2.4 (`optimistic_lock_response`, 409/412), E2.5 (Regel), E2.6, (v) — KA-E-12 |
| QR-T14 | mittel | `views.py`-Merge-Reihenfolge E ↔ G offen | (v), (xii), P1-Tabelle (W0-Queue) — KA-E-02 |
| QR-T17 | mittel | Fehlbelege `lint`/`dependency-check` als CI-Check | E3.0, E3.2-DoD, P1/P3-Tabellen — KA-E-11, KA-ALL-06 |
| QR-T18 | mittel | Belege unter gitignored `docs/test-reports/` | Kopf (Belege-Hinweis, `$QS_URL`) — KA-ALL-07 (vorläufig, ENT-X3 = C) |
| QR-T19 | mittel | `seed_demo`-Reihenfolge D6.2 ↔ E3.8 widerspricht Wellen | E3.8 (Eintritt), (xii), P3-5 — KA-E-03 |
| QR-T27 | niedrig | PR-Größen über Richtwert | (xiii) Vorspann, P3-2-Split-Regel — KA-ALL-08 |
| QR-S01 | hoch | Selbst-Enrollment mit gestohlenem Passwort unter `required` | E3.1 (Grant), E3.2, E3.4, E3.6, E3.7 — KA-E-04 (vorläufig, ENT-E7 = A) |
| QR-S03 | hoch | `secret-scan` deckt Env-Geheimnisse nicht ab | (xiii) Vorspann — KA-ALL-09 |
| QR-S10 | mittel | Altsitzungen und Staff-Keys nach `required` | E3.3 (Refresh-Step-up) — KA-E-05; E3.9 (Cutover) — KA-E-07 (Key-Regel vorläufig, ENT-E8 = A) |
| QR-S11 | niedrig | Recovery-Lookup global, Challenge wiederverwendbar | E3.2 Regel 4/4a — KA-E-06 |
| QR-S19 | – | RLS im selben PR | nicht zutreffend (globale Tabellen, E3.1); `test_rls_coverage.py` als Pflicht-Check genannt — KA-ALL-01 |
| QR-S20 | niedrig | Link-Ziel-Titel aus fremdem Workspace | E2.3 — KA-E-08 |
| Sicherheitsreview Risiken 2/3 | – | Staff-Keys ohne 2FA, unbefristeter Übergang | (i), (vi), E3.0 — KA-E-13 (vorläufig, ENT-E6/ENT-E8) |
| Index §g | – | Rollen `se-architect`, `frontend-developer`, `ux-reviewer` existieren nicht | E3.0, E3.8, (xii), P3-Tabelle — KA-ALL-11, KA-E-11 |

## (xi) Widerlegte Annahmen der Planbasis / Issues

1. **#1380 / E2 „`baselines/`-Routenreihenfolge":** widerlegt (E-L3). Ursache ist der
   Tenant-ID-Fallback des Preset-Gates.
2. **#1444 „REST greift RBAC statt Workspace-Beschränkung" / E1 „REST-Fence wie MCP":** teilweise
   widerlegt. Der REST-Fence existiert (ADR-011 SEC-03), Agent-Keys tragen die Rollen ihres
   Owners; nur workspace-lose Aufrufe scheitern — an beiden Türen (MCP `workspace.query` liefert
   laut Issue selbst `-32001`). Der „Widerspruch" verglich verschiedene Aufrufe.
3. **#1443 „Picker ruft `GET /workspaces` (REST)":** widerlegt; das Plugin nutzt MCP `workspace.list`.
4. **#1388 „Views erscheinen nicht im Schema":** präzisiert; sie erscheinen ohne Request-/Response-Body
   (267/528 Ops).
5. **#1396 „`If-Match: *` → 200 ist falsch":** widerlegt; nach RFC 9110 §13.1.1 ist `*` bei
   existierender Ressource erfüllt. Richtig bleibt: weak → 412, malformed → 400.
6. **#1397 Liste der Typen ohne ETag:** unvollständig (zusätzlich needs, goals, test-runs).
7. **Planbasis „124 beschnittene View-Klassen":** Zahl live nicht prüfbar (Log-Zugriff verboten);
   statisch 107 Kandidaten — Größenordnung bestätigt.

## (xii) Parallelisierungs-Matrix

Max. 4 Agenten gleichzeitig **über alle Pläne** (Host-RAM ~5,8 GiB; lokale Testläufe nur gezielt,
nie Voll-Suite parallel). Slot-Belegung laut Index §d.1: Welle 0 Slot 1 = E-Strang `views.py`
(P1-1 → P1-2 → P1-4 → P1-3 → P1-7), Slot 4 nach C0 = E P1-5, E P1-6; Welle 2 = E2.8 mit niedrigster
Priorität; Welle 3 Slot 1 = E3 (P3-5 nach D P3-1). Gleiche Konfliktdatei = Entwicklung parallel,
Merge seriell in der Queue (Index §d.2).

| Task | Voraussetzungen | parallel zu | Konflikt-Dateien / Migrationen | Rolle |
|---|---|---|---|---|
| E1.1 | – | E1.5, E1.6, E2.1, E2.2, E2.3, E2.4, E2.7 | `auth_tenancy/resource_scope.py` | senior-developer |
| E1.2 | E1.1 | E1.5, E1.6, E2.1, E2.2, E2.7 | `rest_api/auth_enforcer.py`, `auth_tenancy/rest.py`, `application/workspace_service.py`, `rest_api/views.py` (1 Zeile; W0-Queue Index §d.2: nach P1-2, vor G PR 5) — nicht parallel zu E2.3/E2.4/E2.5 | senior-developer |
| E1.3 | E1.2 | E1.5, E1.6, E2.x außer E2.6 | `mcp_server/tool_registry.py`, `mcp_server/workspace_scope.py`, `mcp_server/tools/cross_cutting.py`, `docs/agent-templates/tool-manifest.json` (globale Tool-Queue, Delta 0) | senior-developer |
| E1.4 | E1.3 | E1.5, E1.6, E2.x | nur neue Testdatei | tester |
| E1.5 | – | alle außer E3.6 | `rest_api/api_key_views.py`, neu `rest_api/api_key_serializers.py` | developer |
| E1.6 | – | alle | `integrations/hermes-agent-plugin/dashboard/dist/index.js`, Plugin-Tests | developer |
| E2.1 | – | alle außer E2.7 (Schema-Baseline) | `rest_api/preset_guard.py`, Baseline-Tests | developer |
| E2.2 | – | alle außer E2.7 | `rest_api/urls.py`, `rest_api/collaboration_views.py` | developer |
| E2.3 | – | E1.1, E1.5, E1.6, E2.1, E2.2 | `rest_api/views.py` (TraceLinkViewSet; W0-Queue, PR P1-1), `application/trace_link_service.py` | developer |
| E2.4 | – (vorläufig, ENT-E4 = A) | E1.1, E1.5, E1.6, E2.1, E2.2 | `rest_api/mixins/etag.py`, `rest_api/views.py` (`initial`, 4 bestehende 412-Zweige; W0-Queue, PR P1-2) | senior-developer |
| E2.5 | E2.4 (vorläufig, ENT-E2 = A) | E1.5, E1.6, E2.1, E2.2 | `rest_api/views.py` (7 ViewSets; W0-Queue, PR P1-2, vor G PR 5) | developer |
| E2.6 | E2.5 | E1.4, E1.5, E1.6 | `rest_api/openapi.py`, `reqogniloom/settings.py` (W0-Queue: nach G PR 5) | senior-developer |
| E2.7 | E2.1, E2.2, E2.3, E2.6, E1.5 (Schema stabil) | E1.4, E1.6 | neu `openapi_warning_baseline.json` (ab Merge plan-übergreifende Konfliktdatei, nur Shrink) | developer |
| E2.8 (B1…B7) | E2.7; ENT-E1 (vorläufig A) | Batches untereinander parallel, wenn verschiedene Dateien; je Batch Baseline-Konflikt → sequenziell mergen | jeweilige View-Dateien + Baseline | developer (×2 max, Slot-Grenze Index §d.1) |
| E2.9 | E2.7; Plan G PR 6 gemergt; ENT-G1 (vorläufig A) | E2.8-Batches ohne `views.py` | `rest_api/views.py` (W2-Queue G PR 6 → E2.9 → G PR 19), neu `rest_api/tests/test_openapi_list_params.py`, OpenAPI-Baseline (nur Shrink) | developer |
| E3.0 | Welle 3; Nutzer-Gate U-2; ENT-X4 (ADR-Text); ENT-E6 (Datum) | – | `backend/requirements.txt` (Queue nach A PR-A1), ADR-021 | Nutzer / dependency-auditor / Rolle laut ENT-X4 |
| E3.1 | E3.0; PR-C7a gemergt (Index §e); ENT-E7 (Grant-Modell) | – | Migrationen `auth_tenancy` `0031_user_mfa`, `audit` `0016_alter_auditentry_op_mfa` | senior-developer (Review database-engineer) |
| E3.2 | E3.1 | E3.7 | neu `auth_tenancy/services/mfa.py`, `settings.py` | senior-developer |
| E3.3 | E3.2 | E3.7, E3.9 | `password_authentication.py`, `context.py`, `auth_views.py` (Refresh) | senior-developer |
| E3.4 | E3.3; ENT-E7 | E3.7, E3.9 | `rest_api/auth_views.py` (Login), `urls.py` (Queue), `serializers.py` | senior-developer |
| E3.5 | E3.2 | E3.3, E3.7, E3.8, E3.9 | `auth_tenancy/admin_login.py`, Template | developer |
| E3.6 | E3.4; ENT-E7 | E3.5, E3.8, E3.9 | `rest_api/mfa_views.py`, `urls.py` (Queue), `api_key_views.py`, `auth_tenancy/services/authentication.py` (`create_api_key`), OpenAPI-Baseline | senior-developer |
| E3.7 | E3.2 | E3.3–E3.6, E3.9 | neu Command `mfa_reset` (Grant) | developer |
| E3.8 | E3.4 (Vertrag fix); **D P3-1 gemergt** | E3.5, E3.6, E3.7, E3.9 | `frontend/src/**` (inkl. `ApiKeysSection.tsx`), `e2e/**`, `seed_demo.py` + `test_seed_demo.py` (Queue D P3-1 → E P3-5), Design-System-Ratchet, i18n | frontend-component-engineer |
| E3.9 | E3.2; ENT-E8 (vorläufig A) | E3.3–E3.8 | neu Command `mfa_enforce_cutover`, `deploy/README.md` | senior-developer (Review security-auditor) |

```
Welle 0:
  E1.1 ─▶ E1.2 ─▶ E1.3 ─▶ E1.4
  E1.5   E1.6                      (frei)
  E2.1   E2.2   E2.3               (frei)
  E2.4 ─▶ E2.5 ─▶ E2.6 ─┐
  {E2.1,E2.2,E2.3,E1.5} ┴▶ E2.7 ─▶ E2.8 (B1…B7, Welle 2)
                              └▶ E2.9 (Welle 2, nach G PR 6)
  Merge views.py: P1-1 ─▶ P1-2 ─▶ P1-4 ─▶ [G PR 5] ─▶ P1-3 ─▶ P1-7
Welle 3:
  E3.0 ─▶ E3.1 ─▶ E3.2 ─┬▶ E3.3 ─▶ E3.4 ─┬▶ E3.6
                        ├▶ E3.5           └▶ E3.8 (nach D P3-1)
                        ├▶ E3.7
                        └▶ E3.9 (vor `required`)
```

## (xiii) Phasen und PR-Grenzen

Alle PRs gegen `main` (Branch von `origin/main`), grün auf den realen CI-Jobs aus Index §f.2:
`backend-test` (Sets laut Spalte; pip-audit nur in `set-1-core`), `frontend-test`, `lint` (**nur
Frontend-ESLint**, nur bei Frontend-Änderung genannt), `requirements-drift-check`,
`agent-templates-test`, `hermes-plugin-test`, `secret-scan`; `e2e` (`playwright.yml`) wo genannt.
Kein `build`-/`dependency-check`-Check (gibt es nicht; `dependency-check` = manueller Paved-Road-Lauf
durch `dependency-auditor`, Ergebnis im PR-Kommentar). Python-Lint (`ruff`) nur lokal.
**PR-Größe:** Richtwert ≤ 400 geänderte Zeilen Produktivcode (ohne Tests/Migrationen), Obergrenze
600 → Split; additive und brechende Änderungen nie im selben PR (Index §f.7).
**Secrets:** `secret-scan` prüft bis zum Merge von KA-D-03 (Plan D) nur `reqlo_`-Keys;
Env-Geheimnisse deckt er nicht ab. Kein `git add -A`/`git add .`, nur explizite Pfade (Index §h).
**Merge-Queues:** `rest_api/views.py` W0 (P1-1 → P1-2 → P1-4 → G PR 5 → P1-3 → P1-7),
Tool-Queue (P1-4), `urls.py` (P1-1, P3-3, P3-4), OpenAPI-Baseline (ab P1-7), `seed_demo.py`
(D P3-1 → P3-5), `requirements.txt` (A PR-A1 → P3-1), Design-System-Ratchet und i18n (P3-5) —
alle laut Index §d.2.

**P1 — Vertrag und Key-Prinzipale (Welle 0).**
Eintritt: `origin/main` grün; ENT-E2/E3/E4 vorläufig A (Index §b: Welle 0 startet ohne sie).
Austritt: alle PRs P1 gemergt; auf QS nach Deploy:
`curl -s -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $TOKEN" "$QS_URL/api/v1/baselines/"` → `400`;
`curl -s -D - -o /dev/null -H "Authorization: Bearer $TOKEN" "$QS_URL/api/v1/risks/<id>/" | grep -i '^etag'` → `etag: "<n>"`;
Schema-Auswertung wie E-L7 → `ops declaring If-Match ≥ 11`.

| PR | Branch | Titel | Tasks | Merge-Reihenfolge | grün auf | Rollback | Größe | Reviewer |
|---|---|---|---|---|---|---|---|---|
| P1-1 | `fix/api-contract-routes-1380` | `fix(api): make declared baseline, comment and tracelink routes real` | E2.1, E2.2, E2.3 | `views.py`-Queue 1 | `backend-test` `set-2-api`, `set-1-core`, `frontend-test`, `secret-scan` | Revert; keine Migration | ≈220 (Breaking 405→404 `/comments/`, CHANGELOG) | code-reviewer, security-auditor (QR-S20) |
| P1-2 | `fix/if-match-strict-1396` | `fix(api): evaluate If-Match strictly and tag all versioned types` | E2.4, E2.5 | `views.py`-Queue 2 | `set-2-api`, `frontend-test` | Revert; keine Migration | ≈450 (> Richtwert; über 600 → E2.5 als Folge-PR in der Queue direkt danach) | code-reviewer |
| P1-4 | `fix/api-key-fence-1444` | `fix(auth): fence workspace-scoped keys before RBAC, list own scope` | E1.1, E1.2, E1.3, E1.4 | `views.py`-Queue 3 (parallel zu P1-2 reviewbar); Tool-Queue | `set-2-api`, `set-3-mcp`, `set-1-core`, `agent-templates-test`, `secret-scan` | Revert; keine Migration | ≈380 | security-auditor + code-reviewer |
| – | (Plan G PR 5, G1.5) | – | – | `views.py`-Queue 4 | – | – | – | – |
| P1-3 | `fix/openapi-conditional-1397` | `fix(openapi): declare If-Match, ETag and 412 per resource` | E2.6 | `views.py`-Queue 5 (nach G PR 5) | `set-2-api` | Revert | ≈150 | code-reviewer |
| P1-5 | `fix/api-key-create-validation-1439` | `fix(api): report all api-key creation errors in one 400` | E1.5 | frei (kein `views.py`), vor P1-7 | `set-2-api`, `secret-scan` | Revert | ≈200 | code-reviewer, security-auditor |
| P1-6 | `fix/hermes-plugin-workspace-error-1443` | `fix(plugin): show why the workspace list failed` | E1.6 | beliebig | `hermes-plugin-test` | Revert | ≈60 | code-reviewer |
| P1-7 | `chore/openapi-warning-ratchet-1388` | `chore(openapi): ratchet schema generator warnings` | E2.7 | `views.py`-Queue 6 (nach P1-1, P1-3, P1-5) | `set-2-api` | Revert | ≈120 + Baseline-JSON | code-reviewer |

**Korrektur nach Ist-Stand-Abgleich (2026-10-22, gegen `origin/main`).** Verifizierter Abgleich des
P1-Stands; der Plan-Text bleibt als Soll, §0 bleibt bindend, es entstehen **keine** neuen `ENT-*`.

| PR | Ist-Stand auf `main` |
|---|---|
| P1-1 | teilweise: E2.2 ehrlich als **405** mit Verweis auf `/artifacts/<id>/comments/` (nicht 404); E2.1 nur im Schema deklariert (`workspace_id` als Pflicht-Query-Parameter), die Laufzeit behält den Tenant-Fallback und antwortet opak **404** (test-gepinnt); E2.3 halb (PATCH → 405 vorhanden, `GET /tracelinks/<id>/` harter 404). |
| P1-2 | teilweise und strenger: E2.4 über `parse_if_match`/`IfMatch`, `400 INVALID_IF_MATCH`, 412 nur bei Mismatch, je View verdrahtet; E2.5 (`etag_supported`) existiert auf `main` nicht — **offen/deferred**. |
| P1-3 | anders: kein `declare_conditional_requests`; Deklaration über die Allowlist `rest_api/conditional_requests.py` plus `test_conditional_request_contract_1397.py`. |
| P1-4 | auf `main` vollständig abwesend, in dieser Welle umgesetzt: gemeinsame Fence-Helfer, Fence vor RBAC, service-seitig gefilterte Workspace-Liste (REST + MCP), MCP `workspace.list`, Prinzipals-Matrix; Tool-Delta 0. |
| P1-5, P1-6 | auf `main` erledigt (API-Key-Serializer, Plugin-Fehleranzeige). |
| P1-7 | anders und strenger: **kein** `openapi_warning_baseline.json`; Gate ist `test_schema_completeness_1388.py` (0 Warnings) plus `tests/fixtures/openapi_operations_manifest.json`. |
| E2.3 | in Welle 0 nachgezogen: echtes TraceLink-GET, PATCH über `http_method_names` entfernt, QR-S20-Ziel-Sichtbarkeit; der alte 404-Stub-Test ist durch retrieve-/foreign-/visibility-Tests ersetzt. |

**Konflikte (Plan-Text korrigiert, `main`-Verhalten bleibt):** E2.1 will 400, `main` pinnt 404; E2.2
will 404, `main` pinnt 405. **E2.5 bleibt offen** und wird nicht als implementiert geführt.

**P2 — Schema-Burn-down (Welle 2).** Eintritt: P1-7 gemergt; ENT-E1 vorläufig A. Austritt: Baseline
`unable_to_guess_serializer` leer (Verifikation: `pytest rest_api/tests/test_openapi_generation_warnings_1388.py` grün mit leerer Liste).
PRs `chore/openapi-serializers-<batch>-1388` (B1 `memory`, B2 `admin-ops`, B3 `auth-misc`,
B4–B7 `rest-api-1..4`), Titel `chore(openapi): add schema for <batch> views`, Richtwert ≤ 400,
Obergrenze 600 Zeilen (sonst Batch teilen), grün auf `set-2-api` + jeweiligem Modul-Set
(`set-4-features` für memory/admin_ops), sequenzieller Merge in der Baseline-Queue (Index §d.2;
REST-PRs anderer Pläne ebenfalls), Revert-fähig, Reviewer code-reviewer. Batches mit `views.py`
rebasen nach den W2-PRs von Plan G (PR 6 → PR 19).

| PR | Branch | Titel | Tasks | Merge | grün auf | Rollback | Größe | Reviewer |
|---|---|---|---|---|---|---|---|---|
| P2-9 | `fix/openapi-list-query-params` | `fix(openapi): declare list filters and reject unsupported ones` | E2.9 | `views.py`-W2-Queue nach G PR 6, vor G PR 19; Baseline-Queue | `backend-test` `set-2-api` (OpenAPI-Ratchet) | Revert; keine Migration | ≈200 | code-reviewer |

**P3 — 2FA (Welle 3).** Eintritt: Nutzer-Gate U-2 (Sign-off) dokumentiert, `pip-audit` sauber,
Sicherheitsgate vor Welle 3 (QR-S01, QR-S10 im Plan) erfüllt; für P3-2/P3-3/P3-4 zusätzlich
**ENT-E7 entschieden**; P3-5 nach **D P3-1**. Austritt: auf QS mit `MFA_STAFF_ENFORCEMENT=optional`:
`curl -s -H "Authorization: Bearer $TOKEN" "$QS_URL/api/v1/auth/mfa/status/"` → 200
`{"enrolled":false,…,"enforcement":"optional"}`; E2E `mfa-totp.spec.ts` grün in CI;
`mfa_enforce_cutover --dry-run` auf QS listet Staff-Sitzungen/-Keys ohne Fehler.

| PR | Branch | Titel | Tasks | Merge | grün auf | Rollback | Größe | Reviewer |
|---|---|---|---|---|---|---|---|---|
| P3-1 | `chore/pyotp-dependency-1308` | `chore(deps): add pyotp 2.10.0 for TOTP (signed off)` | E3.0 (requirements + ADR-021-Nachtrag) | 1 (nach A PR-A1) | `requirements-drift-check`, `set-1-core` (pip-audit), `secret-scan`; `dependency-check` manuell (PR-Kommentar) | Revert | ≈30 | dependency-auditor, security-auditor, Rolle laut ENT-X4 + Nutzer (ADR-Text) |
| P3-2 | `feat/mfa-totp-core-1308` | `feat(auth): add TOTP device model and MFA service` | E3.1, E3.2, E3.7 | 2 (nach PR-C7a, Index §e) | `set-2-api`, `set-4-features` (audit), `set-1-core` (`test_rls_coverage.py`), `secret-scan` | Revert + `python manage.py migrate auth_tenancy <vorgänger, erwartet 0030_backfill_show_readable_ids>`, `python manage.py migrate audit 0015_alter_auditentry_op` (Expand-only) | ≈550 ohne Tests/Migrationen (> Richtwert; über 600 → E3.7 als PR P3-2b direkt danach) | security-auditor, database-engineer |
| P3-3 | `feat/mfa-login-flow-1308` | `feat(auth): require a second factor at login for MFA users` | E3.3, E3.4, E3.5 | 3 | `set-2-api`, `secret-scan` | Revert; Flag `off` als Sofort-Rollback | ≈450 | security-auditor |
| P3-4 | `feat/mfa-enrollment-api-1308` | `feat(auth): add MFA enrollment API and key-creation guard` | E3.6 | 4 | `set-2-api`, `secret-scan` | Revert | ≈350 | security-auditor |
| P3-5 | `feat/mfa-frontend-1308` | `feat(ui): add two-factor setup and login step` | E3.8 | 5 (nach P3-4 **und** D P3-1) | `frontend-test`, `lint`, `e2e` (`playwright.yml`, gezielte Spec lokal), `set-2-api` (`test_seed_demo.py`) | Revert | ≈550 (> Richtwert; über 600 → Login-Schritt und `SecuritySection` getrennt) | code-reviewer + ui-reviewer |
| P3-6 | `feat/mfa-enforce-cutover-1308` | `feat(auth): add cutover command before enforcing MFA` | E3.9 | 6 (nach P3-4; parallel zu P3-5) | `set-2-api`, `secret-scan` | Revert | ≈200 | security-auditor |

Regeln: jeder PR referenziert sein Issue (`Fixes #…`, bei #1388 erst im letzten Burn-down-PR;
#1308 erst mit P3-6); Migrationen nur in P3-2 (rückwärtskompatibel zum vorigen Release); kein PR
bündelt zwei unabhängige Features (P1-1 bündelt drei Routen-Fixes derselben Befundklasse #1380).
Umschalten auf `required` ist Betreiberhandlung nach P3-6 (Runbook E3.9), kein PR.

## Verifikationsbefehle (Auszug, erwartete Ausgabe)

Lokal über das Makro `BT` (Index §f.3) bzw. Frontend-Befehl aus Index §f.3; QS-Prüfungen nur mit `$QS_URL`.

| Nach | Befehl (im Backend-Container bzw. CI) | Erwartet |
|---|---|---|
| E1.4 | `pytest rest_api/tests/test_api_key_principal_matrix_1444.py -q` | `… passed` (0 failed) |
| E1.5 | `pytest rest_api/tests/test_api_key_create_collected_errors_1439.py -q` | `4 passed` |
| E2.1 | `pytest rest_api/tests/test_baseline_workspace_routing.py rest_api/tests/test_declared_list_paths_reachable_1380.py -q` | 0 failed |
| E2.3 | `pytest rest_api/tests/test_tracelink_crud_rest.py -q` | 0 failed (inkl. Ziel-Sichtbarkeit QR-S20) |
| E2.4 | `pytest rest_api/tests/test_if_match_strict_1396.py rest_api/tests/test_etag_optimistic_locking_868.py rest_api/tests/test_optimistic_lock_status_mapping.py -q` | 0 failed |
| E2.5 | `pytest rest_api/tests/test_etag_all_versioned_types_1397.py -q` | `28 passed` |
| E2.6 | `pytest rest_api/tests/test_openapi_conditional_requests_1396.py -q` | 0 failed |
| E2.7 | `pytest rest_api/tests/test_openapi_generation_warnings_1388.py -q` | `1 passed` |
| E1.3 | `pytest mcp_server/tests/test_workspace_list_fenced_1444.py mcp_server/tests/test_tool_manifest_drift.py -q`; `pytest docs/agent-templates dist -q` (Repo-Wurzel) ; `jq '.tool_count' docs/agent-templates/tool-manifest.json` vor/nach | 0 failed; Zahl unverändert (Delta 0) |
| E1.6 | CI-Job `hermes-plugin-test` | grün |
| E3.1 | `python manage.py makemigrations --check --dry-run`; `python manage.py migrate auth_tenancy <vorgänger-name>` → `python manage.py migrate auth_tenancy` | `No changes detected`; Rückwärts-Probe rund |
| E3.2–E3.6 | `pytest auth_tenancy/tests/test_mfa_service.py auth_tenancy/tests/test_token_amr.py auth_tenancy/tests/test_admin_login_mfa.py rest_api/tests/test_login_mfa_1308.py rest_api/tests/test_mfa_views_1308.py rest_api/tests/test_api_key_create_requires_mfa_session_1308.py -q` | 0 failed |
| E3.7, E3.9 | `pytest auth_tenancy/tests/test_mfa_reset_command.py auth_tenancy/tests/test_mfa_enforce_cutover.py -q` | 0 failed |
| E3.0 | `pip-audit -r backend/requirements.txt --desc` | `No known vulnerabilities found` |
| E3.8 | `npx vitest run src/components/UserProfileSettings/SecuritySection.test.tsx` (Frontend-Container, Index §f.3); `cd e2e && npx playwright test tests/mfa-totp.spec.ts` (gezielte Spec) | grün |

## Änderungsprotokoll Stufe 2

Integration der [Korrekturaufträge](2026-10-21-korrekturauftraege.md) (Abschnitt E und die für E
zutreffenden KA-ALL) am 2026-10-21. „vorläufig“ = Empfehlung der Entscheidungsliste eingearbeitet und
im Text als „vorläufig, ENT-…“ markiert; die betroffene Task trägt das Eintrittskriterium
„ENT-… entschieden“, wo die Entscheidungsliste „Vorläufig: nein“ führt (ENT-E7, ENT-X4).

| Auftrag | Task-ID / Stelle | Status | Anmerkung |
|---|---|---|---|
| KA-ALL-01 | Kopf „Migrationen“, E3.1, (v), (xii), P3-2 | erledigt | Index-Namen `0031_user_mfa`, `0016_alter_auditentry_op_mfa`; RLS nicht zutreffend (globale Tabellen), `test_rls_coverage.py` als Pflicht-Check |
| KA-ALL-02 | E3.1 (Rollback, TDD, DoD), P3-2, Verifikation E3.1 | erledigt | nur Migrationsnamen; Tests über `leaf_nodes()` |
| KA-ALL-03 | E1.3, P1-4, Verifikation E1.3, (x) | erledigt | Delta 0 Tools/Präfixe; keine Absolutzahl mehr |
| KA-ALL-06 | (xiii) Vorspann, P1-/P3-Tabellen, E3.0, E3.2-DoD | erledigt | `lint` nur ESLint und nur bei Frontend-PRs; `dependency-check` manuell; `ruff` nur lokal |
| KA-ALL-07 | Kopf (Belege, QS ohne Adresse, `qs_base`), P1-/P3-Austritt (`$QS_URL`) | vorläufig (ENT-X3 = C) | Umstellung auf `docs/se/reports/` nach ENT-X3 = B |
| KA-ALL-08 | (xiii) Vorspann, P1-2, P2, P3-2, P3-5 | erledigt | Split-Regeln bei > 600 |
| KA-ALL-09 | (xiii) Vorspann | erledigt | |
| KA-ALL-11 | E3.0, E3.8, (iv) Konventionen, (xii), P3-1, P3-5 | erledigt | `frontend-component-engineer`, `ui-reviewer`; ADR-Text „Rolle laut ENT-X4 + Nutzer“ (vorläufig ENT-X4 = A) |
| KA-E-01 | Kopf, (iii), E3.1, (v), (xii), P3-2, Verifikation | erledigt | `0031_user_mfa` nach PR-C7a; Rollback auf Vorgänger-Namen |
| KA-E-02 | (v), (xii) Vorspann + E1.2/E2.3–E2.6, Diagramm, P1-Tabelle | erledigt | W0-Queue P1-1 → P1-2 → P1-4 → G PR 5 → P1-3 → P1-7 |
| KA-E-03 | E3.8 (Eintritt), (xii), P3-Eintritt, P3-5 | erledigt | D P3-1 → E P3-5 |
| KA-E-04 | E3.1 (Grant-Modell), E3.2, E3.4, E3.5, E3.6, E3.7, (vi), (vii) | vorläufig (ENT-E7 = A) | Umsetzung P3-2/P3-3/P3-4 erst nach Entscheidung (Liste: „Vorläufig: nein“); Grant im selben Migrationsnamen `0031_user_mfa` |
| KA-E-05 | E3.3 | erledigt | 401 `MFA_STEP_UP_REQUIRED` |
| KA-E-06 | E3.2 Regel 4/4a, `consume_challenge`, TDD; E3.4 TDD | erledigt | Nonce-Verbrauch über Redis-Cache, fail-closed; (vi) angepasst |
| KA-E-07 | neue Task **E3.9**, (v), (vi), (xii), P3-6, Verifikation | vorläufig (ENT-E8 = A) | Command vollständig spezifiziert; nur die Staff-Key-Regel ist vorläufig; eigener PR P3-6 statt P3-2 (Größe) |
| KA-E-08 | E2.3 | erledigt | Ziel-Titel nur mit READ auf Ziel-Workspace; 3 Tests |
| KA-E-09 | E2.7 (Regel), (v), (vii), P2 | erledigt | Baseline = plan-übergreifende Konfliktdatei, nur Shrink, seriell |
| KA-E-10 | E1.3 | erledigt | Delta 0, `export_tool_manifest`, Zähler unverändert |
| KA-E-11 | E3.0, E3.8, P3-1, P3-5 | erledigt | |
| KA-E-12 | E2.4 (Abbildung 409/412, `optimistic_lock_response`, statischer Test), E2.5 (Regel), E2.6, (v) | erledigt | Auftrag „OptimisticLockError 409→412 bei If-Match explizit“: `views.py:278` bleibt 409, STRONG `If-Match` → 412 über den Helfer; Plan B B6 / Plan F F2/F3 binden daran |
| KA-E-13 | (i) Nicht-Ziele, (vi), (vii), E3.0, E3.6 (`expires_at` unter `required`), E3.8 (Ablaufdatum-Feld) | vorläufig (ENT-E6 = A + Befristung, ENT-E8 = A) | Datum im ADR-021-Nachtrag offen bis ENT-E6 |
| KA-E-14 | (ii), (ix), alle Verweise im Text | erledigt | D-E2a…D-E3b → ENT-E1…ENT-E6; neu ENT-E7, ENT-E8; Gate = U-2 |
| Abschluss-Integration (a) — Übergabe Plan G G-L16/R9 | neue Task **E2.9**, WP-E2-Überschrift, (v) Task→Task + Plan→Plan, (xii) Matrix + Diagramm, (xiii) P2-Tabelle (PR P2-9) | erledigt | Welle 2 nach G PR 6; `views.py`-W2-Queue G PR 6 → E2.9 → G PR 19 (Index §d.2) |
| Abschluss-Integration (b) — #1407 R3-08 | (v) Plan→Plan | erledigt | „offen“ ersetzt durch „erledigt durch Plan G G5.3“ (by design, Pin-Test) |

**Summe:** 22 Aufträge (14 KA-E + 8 KA-ALL) — 18 erledigt, 4 vorläufig, 0 abgelehnt; dazu 2 Punkte der
Abschluss-Integration (2026-10-22), beide erledigt.
**Zusätzlich angeglichen:** Aufwand E3 +≈1 PT (Grant, E3.9); neuer PR P3-6; `#1308` schließt erst mit
P3-6; Verifikationsbefehle über `BT` (Index §f.3).
