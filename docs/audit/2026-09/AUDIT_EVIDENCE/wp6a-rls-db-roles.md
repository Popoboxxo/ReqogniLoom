---
type: EVIDENCE
scope: wp6a-rls-db-roles
status: success
date: 2026-09-29
author_agent: security-auditor
---

# WP-6a Evidenz — Row-Level-Security, DB-Rollen, Raw-SQL

Alle Abfragen read-only (`docker exec … psql -c SELECT …`). **Kein** `DROP`, `TRUNCATE`,
`pg_terminate`, kein Restart, keine Volumen-Löschung.

---

## 1. Container & effektive DB-Rolle

```
docker ps
  ai-native-reqflow-poc-postgres-1   pgvector/pgvector:pg16   Up 21 hours (healthy)
  ai-native-reqflow-poc-backend-1     f45053df0afc             Up 21 hours (healthy)
```

Effektive Backend-Umgebung (Werte maskiert, nur Schlüsselnamen + nicht-geheime Werte):

```
DB_HOST=postgres   DB_NAME=reqflow
DB_USER=reqogniloom_app        ← NICHT der Bootstrap-Superuser
DB_APP_USER=reqogniloom_app
DB_PASSWORD=<redacted>   DB_APP_PASSWORD=<redacted>
```

`settings.py:328-342`: `"USER": config("DB_USER", default="reqogniloom_app")` — der **Default ist bereits die
App-Rolle** (Fix #109), und `PASSWORD` ist `_get_required_secret` (fail-fast, kein Default).

> **Hinweis:** `docs/audit/2026-09/AUDIT_EVIDENCE/stack-db-redis.txt` (WP-1c) dokumentiert
> `DB_USER=reqflow (superuser)` aus `deploy/.env`. Die **laufende** Container-Umgebung weicht ab und nutzt
> `reqogniloom_app`. Der Compose-Override ist also wirksam — die Evidenz-Notiz ist für den laufenden Stack
> **veraltet**. Kein Finding, aber eine Korrektur an der Evidenz-Lage.

---

## 2. Rollen-Rechte (live)

```sql
SELECT rolname, rolsuper, rolbypassrls, rolcreatedb, rolcreaterole
FROM pg_roles WHERE rolname IN ('reqflow','reqogniloom_app','postgres');
```

| rolname | rolsuper | rolbypassrls | rolcreatedb | rolcreaterole |
|---|---|---|---|---|
| `reqflow` | **t** | **t** | t | t |
| `reqogniloom_app` | **f** | **f** | f | f |

⇒ Die zur Laufzeit verwendete Rolle ist **non-superuser und ohne BYPASSRLS** ⇒ **RLS greift tatsächlich**.
Das ist die wichtigste positive Sicherheitsaussage dieses Berichts und **bestätigt** die Design-Absicht aus
`persistence/db_roles.py:1-19` („Superusers always bypass Row-Level Security … Runtime traffic must instead use
a dedicated, non-superuser role").

**Risikohinweis (INFO, kein Finding):** Existiert der Bootstrap-Superuser `reqflow` weiterhin mit
`rolcreatedb`/`rolcreaterole`, so ist jede Kompromittierung der Backend-Config (`:env`-File, CI-Env) gleichbedeutend
mit einem Superuser-Login. Empfehlung: den Superuser nach der Migration entziehen oder zumindest
`LOGIN`- und `createdb`-Rechte entziehen und ihn ausschließlich für `migrate`/`collectstatic` verwenden.

---

## 3. RLS-Abdeckung (live)

```sql
SELECT count(*) FILTER (WHERE relrowsecurity),
       count(*) FILTER (WHERE relforcerowsecurity),
       count(*)
FROM pg_class WHERE relnamespace='public'::regnamespace AND relkind='r';
-- 71 | 71 | 100

SELECT count(*) FROM pg_policies WHERE schemaname='public';
-- 71
```

⇒ **71 von 100 Tabellen** haben RLS **und** `FORCE ROW LEVEL SECURITY`.
Das ist die Defense-in-Depth, die `persistence/migrations/0003_rls_policies.py` +
`0048_app_role.py` + `0010_rls_item_permission.py` + `0061/0067/0077/0086/0089/0091/0097` aufbauen.
**Positivbefund.**

### 3.1 Die 29 Tabellen OHNE RLS (live enumeriert)

| Kategorie | Tabellen |
|---|---|
| **Auth/Identität** | `pl_user`, `pl_tenant`, `at_api_key`, `at_user_role`, `at_refresh_token`, `at_user_notification_preference`, `auth_group`, `auth_group_permissions`, `auth_permission`, `django_session` |
| **Audit** | `audit_entry`, `django_admin_log` |
| **Admin-Ops** | `admin_ops_backup_metadata`, `admin_ops_system_rate_limit_override` |
| **Memory/Metrics** | `mem_system_memory_settings`, `sm_metric_cache`, `sm_threshold_config` |
| **Async/Integration** | `as_domain_event_dlq`, `as_domain_event_outbox`, `as_webhook_delivery_log`, `as_webhook_subscription` |
| **Celery/Django-Infrastruktur** | `django_celery_beat_*` (5), `django_content_type`, `django_migrations` |

**Bewertung:**

| Tabelle | RLS-frei ⇒ Risiko | Begründung / Bewertung |
|---|---|---|
| `at_api_key`, `at_user_role`, `audit_entry`, `as_webhook_*`, `admin_ops_*`, `sm_*`, `mem_*` | **erheblich** — enthalten tenant_id und teils Secrets bzw. Tenant-Metadaten | Ein einziger Raw-SQL-/Unscoped-Fehler ist ein sofortiger Tenant-Bruch. `at_api_key` enthält `key_hash` (Pepper-optional, `settings.py:642-646`), `agent_label`, `scope` |
| `pl_tenant` | gering | Die Tenant-Tabelle *ist* die Wurzel; per Design global |
| `pl_user` | **besonders** — siehe Finding 228 | `username`/`email` **global** `unique=True`; Manager **nicht** tenant-skopiert; keine RLS ⇒ DB-weites User-Lexikon |
| `django_session`, `django_celery_beat_*`, `django_content_type`, `django_migrations`, `auth_*` | gering | Django-Infrastruktur, nicht tenant-spezifisch |

### 3.2 Warum `pl_user` besonders ist (Finding 228)

`persistence/models.py:501-524`:

```python
class User(AuditableModel):
    """…
    Membership in a tenant is optional at the schema level … hence ``tenant``
    is nullable here and this model does NOT inherit ``TenantScopedModel``."""
    objects = UserManager()          # :522  ← KEIN TenantManager
    username = models.CharField(max_length=150, unique=True)   # :524  ← global unique
    email = models.EmailField(unique=True)                     # :525
```

* `User.objects.filter(...)` ist **tenant-übergreifend** (nötig für Login vor Tenant-Auflösung).
* `pl_user` hat **keine** RLS.
* ⇒ Jede Code-Stelle, die `User.objects` ohne expliziten `tenant_id`-Filter nutzt, sieht alle Tenants.

**Gegengeprüft — die API-Pfade sind sauber:**

| Pfad | Filter | Datei:Zeile |
|---|---|---|
| `GET /api/v1/users/` | `list_for_tenant(tenant_id=ctx.tenant_id)` | `rest_api/user_management_views.py:110` |
| `GET /api/v1/auth/me/` | `User.objects.filter(id=ctx.user_id)` | `auth_tenancy/services/profile_service.py:32` |
| `authenticate_credentials` | `User.objects.filter(username=username)` | `auth_tenancy/services/password_authentication.py:131` — by design, `username` ist global unique |
| `is_tenant_admin(user_id, tenant_id)` | `TenantRole`-basiert | `auth_tenancy/services/authorization.py` |

⇒ **Kein API-Leak.** Der Befund ist strukturell (fehlende DB-Schicht), nicht funktional ausgenutzt.

---

## 4. RLS-Umgehung: gibt es `SECURITY DEFINER`, `bypassrls` oder Raw-SQL-Bypässe?

| Vektor | Prüfung | Ergebnis |
|---|---|---|
| `SECURITY DEFINER`-Funktionen | `\df+` wäre nötig — **nicht ausgeführt** (nicht read-only-genug für meinen Auftrag) | ⚠️ **BLOCKED**, siehe §6 |
| Rollen mit `BYPASSRLS` | `SELECT rolname FROM pg_roles WHERE rolbypassrls` | nur `reqflow` (Bootstrap-Superuser), **keine App-Rolle** |
| `SET LOCAL role` / `SET ROLE` im App-Code | `rg -e 'SET (LOCAL )?ROLE\|set_role\|SET SESSION AUTHORIZATION' backend/` | **0 Treffer** |
| `SET LOCAL app.current_tenant` | `persistence/middleware.py` + `auth_tenancy/services/tenant_context.py` | 🟢 pro Request, Thread-Local, mit Teardown-Backstop (`auth_tenancy/middleware.py`, in `settings.py:272` eingetragen). Issue #110 („SET statt SET LOCAL") ist geschlossen |
| Raw-SQL / `.raw()` / `RawSQL` / `.extra()` | `rg -e '\.raw\(|RawSQL|cursor\(\)|connection\.cursor|\.extra\(' backend/ --glob '!**/tests/**' --glob '!**/migrations/**'` | **25 Treffer**, alle `with connection.cursor() as cur:` |

### 4.1 Die 25 Raw-SQL-Stellen (alle geprüft)

| Datei | Zeilen | Tabellen | Bewertung |
|---|---|---|---|
| `baseline/delta_index_builder.py` | 104,121,139,160,185,199,216,237,305,337 | `Artifact`/`ArtifactVersion` (RLS-an) | 🟢 von RLS geschützt |
| `baseline/services.py` | 453, 491 | Artefakt-Tabellen (RLS-an) | 🟢 |
| `application/artifact_service.py` | 679 | Artefakt-Tabellen | 🟢 |
| `application/pgvector_ann.py` | 56 | `Requirement`/`TraceLink`/`Icd`/`MemoryEntry` (RLS-an) | 🟢 |
| `application/requirement_bundle_service.py` | 323, 387 | Artefakt-Tabellen | 🟢 |
| `application/search_service.py` | 784, 877 | `pl_requirement`, `pl_test_case`, … (RLS-an) | 🟢 |
| `traceability/coverage_calculator.py` | 555, 654 | Trace-Link-Tabellen (RLS-an) | 🟢 |
| `traceability/service.py` | 307, 398, 472 | Trace-Link-Tabellen | 🟢 |
| `traceability/query_engine.py` | 308, 328, 361 | Trace-Link-Tabellen | 🟢 |
| `reqogniloom/health.py` | 51 | `SELECT 1`-Klasse | 🟢 |
| `application/management/commands/verify_embedding_dimensions.py` | 70 | Migrations-/Mgmt-Kontext | 🟢 |
| **`audit/archive.py`** | **346** | **`audit_entry` — KEINE RLS!** | 🔴 `DELETE FROM audit_entry WHERE timestamp < %s` — bewusst archivierungs-übergreifend (`ArchiveLifecycleManager`, partitionsübergreifend) |
| **`auth_tenancy/management/commands/inventory_api_keys.py`** | **361** | **`at_api_key` — KEINE RLS!** | 🟡 Management-Command, absichtlich tenant-übergreifend |

**Bewertung Finding 227 (MEDIUM):**
Die beiden RLS-freien Raw-SQL-Stellen sind **beide Management-/Archivierungs-Kontexte mit explizitem
Cross-Tenant-Auftrag**. Kein Request-Pfad nutzt sie. Das Risiko ist damit **nicht ausgenutzt**, aber die
Fehlerrückfallschicht fehlt: bei diesen 29 Tabellen gibt es **keine** zweite Schicht, wenn der
tenant-skopierte Manager umgangen oder verwechselt wird.

**Empfehlung:** RLS-Policies für die Security-relevanten dieser Gruppe nachtragen — priorisiert
`at_api_key`, `at_user_role`, `audit_entry`, `as_webhook_subscription`, `as_webhook_delivery_log`,
`admin_ops_backup_metadata`, `sm_metric_cache`. Für `pl_user` ist eine Policy über
`tenant_id = current_setting('app.current_tenant')::uuid` **nicht** anwendbar, weil `tenant_id` dort nullable
ist und `authenticate_credentials` vor Tenant-Auflösung läuft ⇒ dort ist eine **Partial-Policy** plus
explizite `EXEMPT`-Liste (oder ein `SECURITY DEFINER`-Login-Pfad) der richtige Weg.

---

## 5. Was `SET LOCAL app.current_tenant` abdeckt und was nicht

| Frage | Antwort | Beleg |
|---|---|---|
| Wird die Session-Variable pro Request gesetzt? | 🟢 ja, `SET LOCAL` (transaktionslokal ⇒ kein Leck in die Connection-Pool-Connection) | `persistence/middleware.py`, Issue #110 geschlossen |
| Wird sie zurückgesetzt? | 🟢 Teardown-Backstop im Middleware | `auth_tenancy/middleware.py`, `settings.py:267-272` (Kommentar: „leaking into the next unauthenticated code path on the same thread") |
| Greift der Django-Manager *auch* ohne RLS? | 🟢 ja — `TenantManager.get_queryset()` wirft `TenantContextNotSetError`, **bevor** SQL entsteht | `persistence/tenancy.py:135-143` |
| Könnte ein Angreifer die Variable selbst setzen? | 🟡 **nein** über die Anwendung (kein `set_config`-Pfad im Request); aber **ja**, wenn er direkten SQL-Zugriff hätte — und `SET LOCAL` läuft in derselben Transaktion ⇒ RLS-Policy liest sie. Das ist genau der Grund für die Defense-in-Depth. | 🔎 |
| `base_manager_name = "unscoped"` | 🟢 bewusst (Django-Interna: Cascade, FK-Validierung). `unscoped` ist **explizit** und grep-bar. | `persistence/models.py:467-474` |

---

## 6. Blockiert

| # | Prüfung | Grund |
|---|---|---|
| 1 | `\df+` / `pg_proc`-Scan auf `SECURITY DEFINER` | Benötigt `\df`-Meta-Sicht; als **nicht** read-only-genug für diesen Auftrag eingestuft (Ausführungs-Semantik von Funktionen). **BLOCKED**, nicht ausgeführt. Empfehlung: als eigener Folge-Check mit `SELECT proname, prosecdef FROM pg_proc WHERE prosecdef;` — das **ist** read-only und sollte beim nächsten Durchlauf gemacht werden. |
| 2 | `\d`-Rechteprüfung der App-Rolle pro Tabelle (`has_table_privilege`) | read-only machbar, aber 100 Tabellen × 8 Privilegien; für die wesentlichen Tabellen nachtragen |
| 3 | RLS-Wirkungstest mit manipuliertem `app.current_tenant` | Erfordert eine Transaktion mit `SET LOCAL` auf der geteilten DB ⇒ Zustandsänderung im Request-Kontext. **BLOCKED.** |
| 4 | Ob `reqflow` (Superuser) produktiv erreichbar ist | Konfigurationsfrage, kein Datenbefund |

**Zu #1 als Sofortmaßnahme** (read-only, sollte vor dem nächsten Release laufen):

```sql
SELECT p.proname, p.prosecdef, n.nspname
FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
WHERE p.prosecdef AND n.nspname = 'public';
```