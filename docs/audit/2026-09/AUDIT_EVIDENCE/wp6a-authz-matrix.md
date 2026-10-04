---
type: EVIDENCE
scope: wp6a-authz-matrix
status: success
date: 2026-09-29
author_agent: security-auditor
---

# WP-6a Evidenz — AuthZ-Matrix

Quelle der Routen-Daten: `docs/audit/2026-09/AUDIT_EVIDENCE/wp1d-resolved-routes.json` (759 aufgelöste Routen,
487 davon unter `/api/v1/`). Code-Belege aus `backend/`.

---

## 1. Mechanik-Schichten (was prüft was)

| Schicht | Ort | Prüft | Fail-Verhalten |
|---|---|---|---|
| L1 AuthN | `auth_tenancy/rest.py:225-296` `AuthTenancyAuthentication.authenticate` | Credential gültig, Tenant aktiviert | **fail-closed** (401) |
| L1a CSRF | `auth_tenancy/rest.py:243-244` → `_enforce_csrf` (`:357`) | nur bei Cookie-Auth | fail-closed (403) |
| L2 Capability-Tier | `rest_api/auth_enforcer.py:109-118` `scope_denial_reason` | `read_only`/`author`/`admin`-Scope des Keys | **fail-closed**, liegt **über** der Matrix |
| L3 RBAC-Matrix | `rest_api/auth_enforcer.py:120` `decide_access(active_roles, operation)` | HTTP-Methode → Operation → Rollen | fail-closed (403) |
| L4 Workspace-Fence | `auth_tenancy/rest.py:259-271` | nur wenn `resolve_request_workspace_id()` ≠ `None` | **fail-open** → tenant-weite UNION |
| L5 Tenant-Fence | `persistence/tenancy.py:117-158` `TenantManager` + Postgres-RLS | `tenant_id` | fail-closed (`TenantContextNotSetError`) |
| L6 Objekt-/Service-Gate | `application/*.py`, `memory/policy.py` | fachliche Rechte (Rolle im Ziel-Workspace, Admin, Item-Permission) | variabel — **überwiegend vorhanden** |

**Die Lücke liegt zwischen L3 und L4**, nicht in L3.

---

## 2. Die kritische Bedingung — `auth_tenancy/rest.py:259-277`

```python
workspace_id = resolve_request_workspace_id(request)          # :259
if workspace_id is not None:
    active_roles = _resolve_roles_from_db(claims.user_id, workspace_id)   # :261  ← Workspace-gefiltert
    if not active_roles and not _workspace_exists(workspace_id):
        workspace_id = None
        active_roles = _resolve_roles_from_db(claims.user_id)             # :271
else:
    if claims.auth_method in (AuthMethod.BEARER_TOKEN, AuthMethod.API_KEY):
        active_roles = _resolve_roles_from_db(claims.user_id)             # :277  ← TENANT-WEITE UNION
```

`_resolve_roles_from_db(user_id)` ohne Workspace-Argument aggregiert über **alle** `UserRole`-Zeilen des Users
(`authorization.py:395-408`, Docstring: *"every non-suspended role the user holds in any workspace"*).

---

## 3. `resolve_request_workspace_id` — client-gesteuerte Auflösung

`auth_tenancy/workspace_scope.py:114-131`:

| Priorität | Quelle | Code | Trigger |
|---|---|---|---|
| 1 | URL-Kwargs `workspace_id` / `workspace_pk` | `:61-71` | Route enthält den KWarg |
| 2 | URL-KWarg `pk`, **nur** wenn `ResolverMatch.route == "workspaces/<uuid:pk>"` | `:73-76` | verschachtelte Workspace-Route |
| 3 | Query-Parameter `workspace_id` | `:79-86` | **Client muss ihn senden** |
| 4 | JSON-Body `workspace_id`, nur POST/PUT/PATCH **und** nur `application/json` | `:89-111` | **Client muss ihn senden** + Content-Type json |

Fehlt der Wert → `None` → tenant-weite UNION.

---

## 4. Matrix: mutierende Routen × Workspace-Fence

Aus `wp1d-resolved-routes.json` (Methoden `POST|PUT|PATCH|DELETE`):

| | Anzahl | Anteil |
|---|---|---|
| mutierende Routen gesamt | **311** | 100 % |
| **mit `workspace` im Pfad** ⇒ L4 zwingend aktiv | **42** | 13,5 % |
| **ohne `workspace` im Pfad** ⇒ L4 nur bei freiwilligem Query-Param | **269** | **86,5 %** |
| betroffene View-Klassen (ohne ws-Pfad) | **73** | von 99 |

### 4.1 Top-View-Klassen ohne Workspace-Pfad (mutierend)

| Anzahl | View-Klasse |
|---|---|
| 16 | `rest_api.views.RequirementViewSet` |
| 16 | `rest_api.views.TraceLinkViewSet` |
| 16 | `rest_api.views.WorkflowDefinitionViewSet` |
| 12 | `rest_api.icd_views.IcdViewSet` |
| 12 | `rest_api.views.MainGoalViewSet` |
| 12 | `rest_api.views.StakeholderNeedViewSet` |
| 12 | `rest_api.views.TestRunViewSet` |
| 10 | `rest_api.views.GoalViewSet`, `ChangeRequestViewSet`, `TestCaseViewSet`, `AdrViewSet`, `interview_views.InterviewViewSet` |
| 8 | `GlossaryTermViewSet`, `DiagramViewSet`, `RiskViewSet`, `NotificationViewSet`, `IssueViewSet`, `ArchitectureElementViewSet` |
| 6 | `collaboration_views.CommentViewSet` |
| 4 | `ApiKeyViewSet`, `ArtifactViewSet`, `UserViewSet`, `BaselineViewSet` |

### 4.2 Beispielrouten ohne Workspace-Pfad (alle mutierend)

```
PATCH|DELETE  /api/v1/requirements/{pk}/
POST         /api/v1/requirements/{pk}/derive/
POST         /api/v1/requirements/{pk}/derive-testcase/
POST         /api/v1/requirements/{pk}/decompose-next-level/
POST         /api/v1/requirements/{pk}/suggest-architecture/
POST         /api/v1/requirements/{pk}/reactivate/
PATCH|DELETE  /api/v1/artifacts/{pk}/
POST         /api/v1/needs/{pk}/derive-requirements/
PATCH|DELETE  /api/v1/trace-links/{pk}/
POST         /api/v1/diagrams/{pk}/
POST         /api/v1/artifacts/{artifact_id}/comments/
POST         /api/v1/artifacts/{artifact_id}/memory/
PATCH|DELETE  /api/v1/test-runs/{pk}/
```

---

## 5. Warum L6 den Ausfall nicht kompensiert

| Komponente | Verhalten auf diesen Routen | Datei:Zeile |
|---|---|---|
| `RequirementService.get_requirement` | `Requirement.objects.select_related("artifact").filter(id=requirement_id)` — **nur** tenant-skaliert (Manager), **keine** Workspace-Mitgliedschaft | `application/requirement_service.py:755-757` (Docstring `:736-737`: „tenant-scoped") |
| `PresetGateMixin._guard_preset` | `if workspace_id is None: return` — **fail-open**, Preset-Gate (Rigor-Konfiguration) ebenfalls umgangen | `rest_api/preset_guard.py:243-244` |
| `RbacPermission` | wertet `auth_context.active_roles` aus, **`auth_context.workspace_id` wird nie gelesen** | `rest_api/auth_enforcer.py:109-120`; `rg` über `auth_enforcer.py` + `auth_tenancy/context.py`: 0 Treffer |

### 5.1 RBAC-Matrix (was die Rollen tatsächlich erlauben)

`auth_tenancy/services/authorization.py:262-276`:

| Rolle | erlaubte Operationen |
|---|---|
| `admin` | **alle** `Operation` (inkl. Governance) |
| `approver` | READ, WRITE, WORKFLOW_TRANSITION, WORKFLOW_APPROVAL |
| `editor` | READ, WRITE, WORKFLOW_TRANSITION |
| `viewer` | READ |

⇒ tenant-weite Union ⇒ **jeder** `viewer` eines Tenants liest alle Artefakte aller Workspaces per UUID;
jeder `editor` schreibt sie; jeder `approver` approved Transitions; jeder `admin` bearbeitet Governance-Objekte.

---

## 6. Berechtigungs-Klassen-Matrix (alle 99 mutierenden View-Klassen)

| Klasse | Anzahl Routen | Permission-Klasse | Funktionales Gate | Bewertung |
|---|---|---|---|---|
| Viewsets auf `BaseEntityViewSet` (19 Klassen) | 234 | `RbacPermission` (Default) | Service + TenantManager; **kein Workspace-Fence auf 269 Routen** | 🔴 Finding 222 |
| `admin_ops.*` (5 Views) | 6 | `HasOperationPermission` **+** `AdminScopeRequiredMixin` **+** In-Body-Admin-Check | dreifach | 🟢 |
| `memory.memory_rest.*` (17 Views) | 6 mutierend | `HasOperationPermission` bzw. Default | `memory/policy.py` (`resolve_artifact_workspace_id` + `active_roles_for` + `assert_can_*`) | 🟢 |
| `auth_tenancy.rest_workspace_members.*` | 3 | Default + Service | `active_roles_for` / Letzter-Admin-Invariant | 🟢 |
| `user_management_views.UserViewSet` | 4 | `HasOperationPermission` | `is_tenant_admin` je Aktion + `list_for_tenant(ctx.tenant_id)` | 🟢 |
| `settings_views`, `link_type_views`, `attribute_*`, `prompt_variable_views`, `global_default_views` | 22 | `AdminScopeRequiredMixin` → `required_scope_operation = WORKSPACE_CONFIG` für **alle** unsafe Methods | Admin-Scope-Gate | 🟢 |
| `collaboration_views` | 6 | Default | `comment_service.py:81 active_roles_for` | 🟡 nur 6 Routen |
| `mcp_server.views.*` (Django-`View`, **nicht** DRF) | 4 | **keine DRF-Permission-Klasse** | `_reject_ambient_cookie_auth` (Form) + `handle_http_request` (Validierung) + `ToolRegistry`-Gate | 🟡 eigener Pfad |
| `auth_views.LoginView` | 1 | `AllowAny` | Passwort + Dummy-Hash-Timing + `LoginRateThrottle`/`LoginIpRateThrottle` | 🟢 designiert |
| `auth_views.RefreshView` | 1 | `AllowAny` | httpOnly-Refresh-Cookie + `enforce_csrf` + `RefreshRateThrottle` | 🟢 designiert |

### 6.1 „Nur IsAuthenticated"-Endpunkte (9) — vollständig geprüft

| Endpoint | View (Zeile) | Service-Gate | Ergebnis |
|---|---|---|---|
| `POST /api/v1/artifacts/{artifact_id}/memory/` | `memory/memory_rest.py:875` | `MemoryEntryService.write` → `policy.assert_can_write` | 🟢 |
| `POST /api/v1/workspaces/{workspace_id}/memory/` | `memory/memory_rest.py:680` | dito (SCOPE_WORKSPACE) | 🟢 |
| `POST /api/v1/memory/{entry_id}/promote/` | `memory/memory_rest.py:819` | `MemoryEntryService.promote` → `policy` | 🟢 |
| `DELETE /api/v1/memory/{entry_id}/` | `memory/memory_rest.py:794` | `policy.assert_can_delete` | 🟢 |
| `DELETE /api/v1/memory/me/` | `memory/memory_rest.py:1047` | selbst-skaliert (eigene `scope="user"`-Rows) | 🟢 |
| `POST /api/v1/diagrams/{pk}/strokes/` | `diagram_canvas_views.py:209` | `get_auth_context` + Service | 🟡 |
| `PUT /api/v1/diagrams/{pk}/mermaid/` | `diagram_canvas_views.py:427` | dito | 🟡 |
| `POST /api/v1/artifacts/{artifact_id}/comments/` | `collaboration_views.py:79` | `comment_service.py:81` | 🟢 |
| `POST /api/v1/workspaces/{workspace_id}/traceability/suggest-links/` | `traceability_suggest_views.py:68` | Pfad enthält Workspace ⇒ L4 aktiv | 🟢 |

⇒ **Antwort auf Frage (c): 0 mutierende Endpoints ohne *jede* Authz-Berechtigungsklasse.**
Aber 269/311 mutierende Routen erreichen die Matrix mit tenant-weiten statt workspace-gefilterten Rollen.

---

## 7. Korrekt funktionierende Fence-Pfade (Positivkontrolle)

| Pfad | Erwartung | Beleg |
|---|---|---|
| `GET /api/v1/requirements/?workspace_id=B` | `_from_query` ⇒ L4 ⇒ Rollen aus B ⇒ **403** für Nicht-Mitglied | Code + `search_service`-Analogie live |
| `GET /api/v1/workspaces/{workspace_id}/needs/` | `_from_url` ⇒ L4 immer aktiv | Code |
| `POST /api/v1/workspaces/{pk}/import/csv/` | `_WORKSPACE_ROUTE_MARKER` matcht ⇒ L4 immer aktiv | `workspace_scope.py:38,74-75` |
| `GET /api/v1/search/?q=x` **ohne** `workspace_id` | `parse_workspace_id` pflicht ⇒ **400** | live |
| `GET /api/v1/search/?workspace_id=B` für Nicht-Mitglied | L4 ⇒ **403** | Code |
| `SearchService.search(scope="tenant")` | `accessible_workspace_ids()` ⇒ nur eigene Workspaces | `search_service.py:1000-1015` |
| `list_workspace_members` | `active_roles_for` ⇒ **PermissionDenied** | `authorization.py:465-468` |
| `UserViewSet.list` | `list_for_tenant(ctx.tenant_id)` ⇒ tenant-scoped | `user_management_views.py:110` |
| `MemoryPolicy.can_write/can_read/can_delete` | `resolve_artifact_workspace_id` + `_roles_for` | `memory/policy.py:98-297` |

---

## 8. Live-Messungen (nicht-mutierend)

| Probe | Ergebnis | Aussage |
|---|---|---|
| `GET /api/v1/auth/me/` mit Admin-Bearer | 200, Header-Set vollständig (siehe `wp6a-cors-headers-ratelimit.md`) | AuthN-Pfad gesund |
| `GET /api/v1/api-keys/` mit Admin-Bearer | 200, 54 452 B | Tenant-Scoped, paginiert |
| `GET /api/v1/users/?page_size=100` mit Admin-Bearer | 200, `count=401`, 25er-Seite | Tenant-Scoped + paginiert |
| `GET /api/v1/metrics/` anonym | **401** | WP-1as „782 KB unauthentifiziert" **widerlegt** |
| `GET /api/v1/metrics/?workspace_id=W` auth | 200, **7 228 B**; `page_size=100000` / `limit=100000` ⇒ **identisch** | begrenzt |
| `GET /api/v1/link-type-definitions/` | **404** (Route existiert nicht) | WP-1d-Befund widerlegt |
| `GET /api/v1/link-type-defaults/?page_size=100000` | 404 (Cap greift) | paginiert |
| `GET /api/v1/requirements/<uuid-fremd>/` (Admin) | 200 | **kein** Signal — Admin ist Mitglied aller Workspaces; die 403/200-Asymmetrie ist erst mit einer niedrigprivilegierten Identität messbar (siehe §9) |

---

## 9. Nicht durchgeführt (Begründung)

Der Runtime-Nachweis der Cross-Workspace-Exploitation benötigt **zwei** Identitäten in **zwei** Workspaces
**desselben** Tenants. API-Keys werden serverseitig unveränderlich für `ctx.user_id` erzeugt
(`rest_api/api_key_views.py:131-136, 341`) — es gibt keinen Weg, einen Key für einen bestehenden Nicht-Admin-User
zu minten. Es bliebe nur `POST /api/v1/users/` (User + UserRole anlegen) — das ist eine Zustandsänderung im
**geteilten** Stack und wurde auftragsgemäß unterlassen.

**Ersatz-Beweis (codebasiert, 3 Glieder, alle mit Datei:Zeile):**
1. L4 ist an `resolve_request_workspace_id() is not None` gekoppelt (`rest.py:259-261`).
2. Für 269/311 mutierende Routen liefert der Resolver `None` (kein `workspace` im Pfad; Query-Param optional).
3. Der Service filtert nicht nach Workspace-Mitgliedschaft (`requirement_service.py:755-757`).

Konfidenz: **90 %** auf die Mechanik, **nicht** auf die Ausnutzbarkeit im konkreten Deployment.