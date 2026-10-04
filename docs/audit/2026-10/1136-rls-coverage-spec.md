# RLS-Coverage-Erweiterung (Pre-Auth + `as_*` Worker-Tabellen) — Spec
> Status: Entwurf (2026-10-04)
> Issue: #1136 · Trace-Anker: `spec-id: SPEC-1136-rls-coverage`
> Autor: concept-specifier · Sprache: Deutsch (DDL/Identifier englisch)

## Problem / Ziel / Nicht-Ziele

### Problem

Zwei Klassen von Tabellen sind heute von Row-Level-Security ausgenommen, weil ihr
primärer Produktionspfad **ohne `app.current_tenant`** läuft:

1. **Pre-Auth-Lookups** (`at_api_key`, `at_user_role`) — der Credential-/Rollen-Lookup
   läuft über `.unscoped`, *bevor* ein Tenant-Kontext existieren kann
   (`backend/auth_tenancy/migrations/0011_rls_policies.py:43-64` nennt genau diese zwei
   als „DELIBERATELY NOT INCLUDED").
2. **Vier worker-owned `as_*`-Tabellen** ohne `tenant_id`-Spalte
   (`as_domain_event_outbox`, `as_domain_event_dlq`, `as_webhook_subscription`,
   `as_webhook_delivery_log`; `backend/application/models.py:45-237`). Sie sind die
   offenen CR-17-Restrisiken und in `RLS_EXEMPT_TABLES` benannt
   (`backend/persistence/tests/test_rls_coverage.py:75-262`, Plain-Set `:269-276`).

Sicherheitsinvariante (Plan, bindend): **„Nichts scharf schalten, was die Auth bricht."**
Es wird ausschließlich gestaged (nullable Spalte + Backfill + Policy hinter Flag DEFAULT
OFF); kein `FORCE` im Default.

### Ziel

- Pre-auth **read-only**-Lookups (`at_api_key`, `at_user_role`) hinter `SECURITY DEFINER`-
  Funktionen ziehen und die Tabellen mit einer GUC-guarded RLS-Policy ausstatten
  (Enforcement hinter Flag DEFAULT OFF).
- Die vier `as_*`-Tabellen erhalten eine **nullable** `tenant_id`-Spalte, Backfill aus
  `workspace_id` → `Workspace.tenant_id`, und eine GUC-guarded Policy (ENABLE, **kein**
  FORCE), Enforcement hinter Flag DEFAULT OFF.
- SSOT (`RLS_EXEMPT_TABLES` / `test_rls_coverage.py`) korrekt nachführen; die veraltete
  CR-17-Admin-Exposure-Prosa gegen den heutigen Admin-Code neu ableiten.
- Jeder Schritt reverse-fähig; die Pipeline (Migrations) bleibt der Rollback-Träger.

### Nicht-Ziele

- **`audit_entry` bleibt außen vor.** Es steht weder in diesem Issue noch im Approved Plan
  zur Schließung (`RLS_EXEMPT_TABLES["audit_entry"]`, `test_rls_coverage.py:99-110`); es
  behält seinen Ausnahme-Eintrag unverändert.
- **Kein `FORCE ROW LEVEL SECURITY`** und keine Aktivierung von Enforcement im Default.
- **Keine Änderung am Refresh-Token-Schreibpfad** in diesem Change — siehe **STOPP-S1**
  (§7). `at_refresh_token` bleibt ausgenommen.
- Keine Änderung an der Auth-Semantik (HMAC-Vergleich bleibt in Python, Rotation/
  Family-Burn-Semantik unberührt, „last_used_at" wird weiterhin nicht geschrieben).
- Keine neue Runtime-Feature-Flag-Registry (recon D: existiert nicht, wird nicht gebaut).

---

## Interface Contracts

Alle Contracts benennen Ziel-Datei + Ziel-Symbol und sind vollständig typisiert.

### IC-1 — Pre-Auth `SECURITY DEFINER`-Funktionen (Owner = Tabellen-Owner / Migrationsrolle)

**Owner & Sicherheit (für jede Funktion identisch):**
- `SECURITY DEFINER`; Owner ist die **Tabellen-Eigentümerrolle** (die Migrationsrolle,
  die `at_api_key`/`at_user_role` besitzt — vgl. `persistence/migrations/0048_app_role.py:16-20`).
  Der Owner darf **nicht** `APP_DB_ROLE` sein, sonst wäre `SECURITY DEFINER` wirkungslos
  (APP_DB_ROLE unterliegt der Policy).
- `SET search_path = pg_catalog, pg_temp` (hijack-safe: `pg_catalog` implizit zuerst,
  `pg_temp` zuletzt; **`public` bewusst NICHT** im Pfad). Alle Tabellen-/Objekt-Referenzen
  im Funktionskörper sind schema-qualifiziert (`public.at_api_key`, `public.pl_user`).
- `REVOKE ALL ON FUNCTION ... FROM PUBLIC;` und anschließend
  `GRANT EXECUTE ON FUNCTION ... TO "<APP_DB_ROLE>";`
  (`APP_DB_ROLE` = `persistence.db_roles.APP_DB_ROLE`, `backend/persistence/db_roles.py:19`).
  `0048_app_role.py:36-78` vergibt nur SELECT/INSERT/UPDATE/DELETE + Sequenzen, **keine**
  `EXECUTE`-Grants — daher sind die Grants hier Pflicht.

**IC-1a — ApiKey-Lookup (kein Boolean-Oracle; `hmac.compare_digest` bleibt in Python)**

```sql
CREATE FUNCTION public.auth_api_key_lookup(p_candidates text[])
RETURNS TABLE (
    id uuid, user_id uuid, key_hash text,
    revoked_at timestamptz, expires_at timestamptz,
    principal_type text, scope text, workspace_ids jsonb, agent_label text,
    tenant_id uuid, user_is_active boolean
)
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
    SELECT k.id, k.user_id, k.key_hash, k.revoked_at, k.expires_at,
           k.principal_type, k.scope, k.workspace_ids, k.agent_label,
           u.tenant_id, u.is_active
    FROM public.at_api_key AS k
    JOIN public.pl_user AS u ON u.id = k.user_id
    WHERE k.key_hash = ANY (p_candidates)
    LIMIT 1;
$$;
```
- Die Funktion liefert die **Zeile** (nicht `bool`) und genau die Spalten, die
  `validate_api_key` heute über `select_related("user")` liest
  (`backend/auth_tenancy/services/authentication.py:511-515`, `:537`, `:541-550`).
- Der Python-Aufrufer behält die Konstante-Zeit-Schleife
  `hmac.compare_digest(api_key.key_hash, candidate)` (`authentication.py:522-524`)
  unverändert. Die Funktion darf `key_hash` nicht weglassen.
- `LIMIT 1` spiegelt das heutige `.first()` (ohne explizite Ordnung).

**IC-1b — Rollenauflösung (pre-auth Token-Ausstellung)**

```sql
CREATE FUNCTION public.auth_resolve_roles(p_user_id uuid)
RETURNS TABLE (role text)
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
    SELECT r.role
    FROM public.at_user_role AS r
    WHERE r.user_id = p_user_id AND r.suspended_at IS NULL;
$$;
```
Ersetzt `UserRole.unscoped.filter(user_id=..., suspended_at__isnull=True).values_list("role", flat=True)`
(`backend/auth_tenancy/services/password_authentication.py:164-167`).

**IC-1c — Refresh-Token-Funktionen (designt, aber in diesem Change NICHT aktiviert — STOPP-S1)**

Design-Vertrag (für das Folge-Review; **keine** Aktivierung / kein Code-Switch hier):

```sql
-- Lesen + Zeilensperre; VOLATILE ist Pflicht (FOR UPDATE).
CREATE FUNCTION public.auth_refresh_token_claim(p_jti uuid)
RETURNS TABLE (id uuid, user_id uuid, tenant_id uuid, jti uuid, session_id uuid,
               used_at timestamptz, revoked_at timestamptz)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
    RETURN QUERY
      SELECT t.id, t.user_id, t.tenant_id, t.jti, t.session_id, t.used_at, t.revoked_at
      FROM public.at_refresh_token AS t
      WHERE t.jti = p_jti
      FOR UPDATE;
END; $$;

CREATE FUNCTION public.auth_refresh_token_spend(p_jti uuid) RETURNS void
LANGUAGE sql VOLATILE SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$ UPDATE public.at_refresh_token SET used_at = now() WHERE jti = p_jti; $$;

CREATE FUNCTION public.auth_revoke_refresh_family(p_session_id uuid, p_reason text)
RETURNS integer
LANGUAGE sql VOLATILE SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
  WITH upd AS (
    UPDATE public.at_refresh_token
       SET revoked_at = now(), revoked_reason = p_reason
     WHERE session_id = p_session_id AND revoked_at IS NULL
     RETURNING 1)
  SELECT count(*)::int FROM upd;
$$;

CREATE FUNCTION public.auth_refresh_token_insert(
  p_user_id uuid, p_tenant_id uuid, p_jti uuid, p_session_id uuid, p_expires_at timestamptz
) RETURNS uuid
LANGUAGE sql VOLATILE SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
  INSERT INTO public.at_refresh_token
    (id, user_id, tenant_id, jti, session_id, expires_at, created_at, updated_at)
  VALUES (gen_random_uuid(), p_user_id, p_tenant_id, p_jti, p_session_id,
          p_expires_at, now(), now())
  RETURNING id;
$$;
```

**Beantwortung der M1-Mechanismusfragen (verbindlich):**
- **`SELECT ... FOR UPDATE` in `SECURITY DEFINER`:** Die Zeilensperre wird von der
  **aufrufenden Transaktion** gehalten. `SECURITY DEFINER` ändert nur den
  Privilegienkontext, nicht die Transaktionsidentität; die Sperre endet mit COMMIT/
  ROLLBACK des Django-`transaction.atomic()`-Blocks. Semantik identisch zum heutigen
  `RefreshToken.unscoped.select_for_update()` (`authentication.py:387-391`).
- **Burn-UPDATE/INSERT: Grant genügt NICHT.** Sobald RLS auf `at_refresh_token` aktiv ist,
  unterliegt `APP_DB_ROLE` der Policy; ohne `app.current_tenant` matcht ein direktes
  `UPDATE`/`INSERT` null Zeilen bzw. wird vom `WITH CHECK` verworfen (still, ohne Fehler).
  Der Schreibvorgang **muss** daher mit Owner-Privilegien laufen — also **in** der Funktion.
- **`VOLATILE` ist Pflicht** für alle vier Funktionen: PostgreSQL verbietet `FOR UPDATE`
  in `STABLE`/`IMMUTABLE`, und Daten-modifizierende Funktionen dürfen nicht stabil sein.
- **`REVOKE ... FROM PUBLIC`** zwingend (Default-`EXECUTE` liegt sonst bei `PUBLIC`).

**Aufrufer, die umzustellen sind (nur IC-1a/1b in diesem Change):**
| Datei:Zeile | Heute | Neu |
|---|---|---|
| `backend/auth_tenancy/services/authentication.py:511-515` | `ApiKey.unscoped.select_related("user")...first()` | `cursor.execute("SELECT * FROM public.auth_api_key_lookup(%s)", [list(candidates)])` |
| `backend/auth_tenancy/services/password_authentication.py:164-167` | `UserRole.unscoped.filter(...).values_list(...)` | `cursor.execute("SELECT role FROM public.auth_resolve_roles(%s)", [user.id])` |

Der Python-seitige Konstantzeit-Vergleich (`authentication.py:522-524`) und alle
Status-Prüfungen (`:528-558`) bleiben erhalten; die Funktion **kürzt** die Entscheidung
nicht ab.

### IC-2 — `as_*`: nullable `tenant_id` + staged Policy

Modellfelder (in `backend/application/models.py`), jeweils an den vier Plain-Models
(`DomainEventOutbox`, `DomainEventDLQ`, `WebhookSubscription`, `WebhookDeliveryLog`):

```python
tenant_id = models.UUIDField(null=True, blank=True, db_index=True)
```
- Nullable per Design (Staging). Die Models bleiben **plain `models.Model`** (KEINE
  `TenantScopedModel`-Subklasse) — der Poller liest heute über `objects` ohne
  Tenant-Kontext; ein Wechsel zur TenantManager-Default-Bindung würde ihn brechen.
- FK auf `pl_tenant(id)` als **`NOT VALID`** zunächst, `VALIDATE` nach Backfill (siehe M4).

Policy-DDL je Tabelle `T` (ENABLE, **kein FORCE**):

```sql
ALTER TABLE T ENABLE ROW LEVEL SECURITY;
CREATE POLICY T_tenant_isolation ON T
    USING (
        current_setting('app.rls_as_enforced', true) IS DISTINCT FROM 'on'
        OR tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid
    )
    WITH CHECK (
        current_setting('app.rls_as_enforced', true) IS DISTINCT FROM 'on'
        OR tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid
    );
```
- **Kein FORCE**: `APP_DB_ROLE` ist nicht Owner und daher **ohne** FORCE an die Policy
  gebunden. FORCE würde nur Owner-Verbindungen (Migrationsläufer, Superuser-Testverbindung)
  binden — bewusst nicht, solange gestaged.
- Die Prädikat-Form ist **permissiv-wenn-unset**: `NULL IS DISTINCT FROM 'on'` → TRUE.
  Erst `SET app.rls_as_enforced = 'on'` aktiviert die Tenant-Bedingung.

Reverse je Tabelle `T`: `DROP POLICY IF EXISTS T_tenant_isolation ON T;`
`ALTER TABLE T NO FORCE ROW LEVEL SECURITY;` `ALTER TABLE T DISABLE ROW LEVEL SECURITY;`
(byte-gleiche Konvention wie `persistence/migrations/0067_rls_remaining_pl_tables.py:98-107`).

### IC-3 — Flag/GUC (M3-Auflösung: Option (i), GUC-guarded permissive Policy)

Zwei unabhängige Flags, Muster wie `settings.py:610-618` (`AUTHZ_*_ENFORCED`):

```python
# backend/reqogniloom/settings.py
RLS_AS_ENFORCED: bool = config("RLS_AS_ENFORCED", default=False, cast=bool)
RLS_PREAUTH_ENFORCED: bool = config("RLS_PREAUTH_ENFORCED", default=False, cast=bool)
```

Die GUCs werden am **App-Role-Connection** gesetzt — in den `DATABASES[...]["OPTIONS"]`
(`settings.py:331-359`, heute nur `-c statement_timeout=...`) als zusätzliche
`-c app.rls_as_enforced=on` bzw. `-c app.rls_preauth_enforced=on`, **nur wenn** das
jeweilige Flag `True` ist. Damit tragen **alle** App-Role-Verbindungen (Django + Celery +
Skripte) die GUC konsistent; kein Pfad kann sie versehentlich umgehen.

Semantik pro Tabelle:
| Zustand | `app.rls_as_enforced` | `as_*`-Sichtbarkeit (App-Role) | Poller |
|---|---|---|---|
| **OFF (Default)** | unset | alle Zeilen sichtbar (Prädikat TRUE) | **unverändert** |
| **ON** | `'on'` | nur `tenant_id = app.current_tenant` | nur nach A4-Fix (siehe §7) |

**Kaveat (ehrlich, keine Vermutung):** Ein Flag-Flip ist ein Config-Change + **Restart**
der App-/Celery-Prozesse (Django lädt `settings` beim Start). „Ohne neuen Deploy" ist
erfüllt im Sinne von „ohne neues Schema/Migration/Code-Release"; ein **echter Hot-Toggle
ohne Restart** ist mit der bestehenden Projektmechanik (keine Runtime-Flag-Registry, recon D)
nicht möglich → siehe Offene Frage O-1.

---

## Datenfluss

### Pre-Auth (IC-1a/1b)
```
HTTP /auth/login/ oder API-Key-Request
  → validate_api_key(plaintext)
      → api_key_hash_candidates(plaintext)  [Python, unverändert]
      → SELECT * FROM public.auth_api_key_lookup(candidates)   [Owner-Privileg, RLS-bypass]
      → hmac.compare_digest(key_hash, candidate)               [Python, unverändert]
      → Status-/Tenant-/Active-Prüfungen                       [Python, unverändert]
  → resolve_roles(user)
      → SELECT role FROM public.auth_resolve_roles(user_id)    [Owner-Privileg]
```
Kein `app.current_tenant` nötig; die Privilegien-Eskalation ist auf die zwei read-only
Funktionen begrenzt.

### `as_*` (IC-2/IC-3)
```
Mutation (Service, Tenant-Kontext aktiv)
  → DomainEventOutbox.objects.create(..., tenant_id=<Stamp>)   [neu, Writer-seitig]
       → noch offen, siehe A4; bis dahin tenant_id NULL → WITH CHECK nur bei ON relevant
Celery-Poller (kein Tenant-Kontext)
  → candidates = SELECT pk FROM as_domain_event_outbox WHERE published=false ...   [OFF: wie heute]
  → _claim_event(pk)  SELECT FOR UPDATE ...                                        [OFF: unverändert]
  → WebhookDispatcher._load_webhook_configs(workspace_id) ...                      [OFF: unverändert]
  → write-backs (published / retry / DLQ)                                          [OFF: unverändert]
```
Bei Flag ON erfordert jeder dieser Schritte einen Tenant-Kontext **pro Zeile** (A4,
§7 – precondition, nicht Teil des OFF-Ships).

### Backfill (M5)
```
as_domain_event_outbox.tenant_id   ← pl_workspace.tenant_id via workspace_id
as_domain_event_dlq.tenant_id      ← pl_workspace.tenant_id via workspace_id
as_webhook_subscription.tenant_id  ← pl_workspace.tenant_id via workspace_id
as_webhook_delivery_log.tenant_id  ← pl_workspace.tenant_id via
                                      as_webhook_subscription.workspace_id
```
- Migrationen laufen als **Owner** → RLS-Bypass ist erwartet und nötig.
- **Orphan-Definition (nicht geraten):** Löst eine `workspace_id` zu **keinem** Tenant auf
  (keine passende `pl_workspace`-Zeile), bleibt `tenant_id` **NULL**. Die Migration
  **löscht nichts** und wirft nicht; sie zählt die Orphans und loggt eine WARNING mit der
  Tabelle und der Anzahl. Orphan-Zeilen sind bei Flag ON unsichtbar (USING: `NULL = ...`
  ist NULL → kein Match) und fail-closed; im OFF-Zustand bleiben sie wie heute sichtbar.

---

## Staged Rollout / Migrationen

Reihenfolge ist bindend; jeder Schritt ist einzeln reverse-fähig.

**P1 — Pre-Auth-Funktionen** (`auth_tenancy/0018`): IC-1a/1b anlegen + Grants.
**P2 — Pre-Auth-Code-Switch** (Python, kein Migrationsschritt): die zwei Aufrufer aus
IC-1 auf die Funktionen umstellen. Voraussetzung für `RLS_PREAUTH_ENFORCED=on`.
**P3 — Pre-Auth-Staged-Policy** (`auth_tenancy/0019`): ENABLE + GUC-guarded Policy auf
`at_api_key`, `at_user_role`. Kein FORCE. Enforcement hinter `RLS_PREAUTH_ENFORCED`.
**P4 — `as_*` Spalte** (`application/0030`): nullable `tenant_id` + FK `NOT VALID` ×4.
**P5 — Backfill + VALIDATE** (`application/0031`): UPDATE aus `pl_workspace` (bzw. über
Subscription), `VALIDATE CONSTRAINT`; Orphan-Zählung/Log.
**P6 — `as_*` Staged-Policy** (`application/0032`): ENABLE + GUC-guarded Policy ×4,
kein FORCE. Enforcement hinter `RLS_AS_ENFORCED`.
**P7 — SSOT/Tests** (§4).
**A4 — Poller-Tenant-Arming** (deferred, Voraussetzung für Flag ON, §7): designt, **nicht**
Teil des OFF-Ships.

---

## SSOT + Test-Änderungen

SSOT bleiben `backend/persistence/tests/test_rls_coverage.py` (`RLS_EXEMPT_TABLES`) und
`backend/persistence/tests/test_rls_plain_child_models.py`. Invariante: **eine Tabelle
niemals gleichzeitig covered UND exempt**.

1. `RLS_EXEMPT_TABLES` (`test_rls_coverage.py:75-262`) verliert `at_api_key`,
   `at_user_role`, `as_domain_event_outbox`, `as_domain_event_dlq`,
   `as_webhook_subscription`, `as_webhook_delivery_log`.
   Behalten: `at_refresh_token` (STOPP-S1), `audit_entry` (Nicht-Ziel).
2. Neuer State `RLS_STAGED_TABLES: dict[str, str]` mit den sechs verschobenen Tabellen;
   Wert nennt je Tabelle: Flag/GUC, tenant_id-Quelle, Enforcement OFF/ON, Orphan-Verhalten.
3. `RLS_EXEMPT_PLAIN_TABLES` (`:269-276`) → `frozenset()`.
4. Neuer Invariantentest:
   ```python
   def test_no_table_is_covered_and_exempt_or_staged():
       declared = _tables_with_policy_in_migrations()
       assert not (set(RLS_EXEMPT_TABLES) & declared)
       assert not (set(RLS_EXEMPT_TABLES) & set(RLS_STAGED_TABLES))
       assert set(RLS_STAGED_TABLES) <= declared
   ```
5. `test_rls_policies_exist_on_the_live_schema` (`:430-464`): Policy-Menge =
   `tenant_tables - EXEMPT` (Staged enthalten); FORCE-Menge =
   `tenant_tables - EXEMPT - STAGED` (Staged haben bewusst kein FORCE).
6. `test_rls_plain_child_models.py`:
   - `WORKER_OWNED_TABLES` (`:90-97`) → `STAGED_PLAIN_CHILD_TABLES` (dieselben vier).
   - `_arm_app_role` (`:316-318`) setzt zusätzlich
     `SET app.rls_as_enforced = 'on'` (und `app.rls_preauth_enforced = 'on'`), damit die
     „leer ohne GUC"-Assertion (`:642-667`) den **scharfgeschalteten** Zustand prüft.
   - `test_module_inventory_matches_the_rls_exemption_registry` (`:816-842`): an den neuen
     State angepasst; `RLS_GUARDED_TABLES == set(PLAIN_CHILD_TABLES) - set(RLS_EXEMPT_TABLES)`.
   - `test_worker_owned_table_cannot_carry_a_tenant_keyed_policy` (`:900-942`) **ersetzt**
     durch `test_staged_plain_child_table_carries_tenant_key_and_policy`: assertet
     `tenant_id` ist vorhanden, Policy ist vorhanden, Tabelle ist NICHT in
     `RLS_EXEMPT_TABLES`.
   - `CR17_JUSTIFICATION_CLAIMS` (`:199-251`) → `STAGED_JUSTIFICATION_CLAIMS` mit
     Verbatim-Markern (Flag-Name, `tenant_id`-Herkunft, Orphan-Verhalten,
     „enforcement behind flag", „still not enforced in production default").
7. Admin-Prosa-Neuableitung (M6): Die CR-17-Texte behaupten, die vier ModelAdmins läsen
   cross-tenant. Das ist gegen den heutigen Code **STALE**: Alle vier registrieren über
   `TenantScopedAdminMixin` (`backend/persistence/tenant_admin.py:65-115`,
   `backend/application/admin.py:55-206`), dessen `get_queryset`/`has_*_permission` per
   `request.user.tenant_id` filtern (fail-closed bei `tenant_id=None`).
   Konkret:
   - `DomainEventOutboxAdmin` (`admin.py:55-84`), `DomainEventDLQAdmin` (`:87-126`),
     `WebhookSubscriptionAdmin` (`:134-160`, `exclude=("secret",)`, `has_add_permission=False`,
     `readonly_fields=("created_at","workspace_id")`), `WebhookDeliveryLogAdmin`
     (`:163-206`, read-only) sind **tenant-gescoped**.
   - Die neuen SSOT-Texte sagen daher: der Admin ist heute tenant-gescoped per **App-Code**,
     das ist **keine DB-Garantie**, und eine künftige Registrierung ohne den Mixin
     öffnet den Pfad erneut. Die alten Marker (`_ADMIN_*`, `:143-165`) werden durch
     passende neue Marker ersetzt; die Verbatim-Contract-Mechanik bleibt.

---

## Migrations-Inventar

| App | Nr. | Deps | Forward | Reverse |
|---|---|---|---|---|
| `auth_tenancy` | `0018` | `0017_admin_lockout_expiry_index`, `persistence 0048_app_role` | IC-1a/1b-Funktionen, REVOKE PUBLIC, GRANT EXECUTE an `APP_DB_ROLE` | `DROP FUNCTION IF EXISTS` (beide) |
| `auth_tenancy` | `0019` | `0018` | ENABLE + GUC-guarded Policy auf `at_api_key`, `at_user_role` | DROP POLICY, DISABLE |
| `application` | `0030` | `0029_drop_redundant_idem_expires_index` | `tenant_id` nullable + FK `NOT VALID` ×4 | `RemoveField` ×4 (FK fällt mit) |
| `application` | `0031` | `0030` | Backfill aus `pl_workspace`; `VALIDATE CONSTRAINT`; Orphan-Log | `RunPython` setzt `tenant_id = NULL` |
| `application` | `0032` | `0031` | ENABLE + GUC-guarded Policy ×4, kein FORCE | DROP POLICY, DISABLE |

`persistence` benötigt **keine** Migration: Grants sind per-Funktion explizit (least
privilege) statt per `ALTER DEFAULT PRIVILEGES GRANT EXECUTE ON FUNCTIONS`. Ein optionaler
`persistence/0107` für Default-Function-Privileges ist bewusst **nicht** Teil dieses Changes.
`settings.py`-Flag-/OPTIONS-Änderung ist kein Migrationsschritt.

---

## Acceptance Criteria (nummeriert, testbar)

1. **AC-1** — Statisch: `set(RLS_EXEMPT_TABLES) ∩ declared-policies == ∅` und
   `set(RLS_EXEMPT_TABLES) ∩ set(RLS_STAGED_TABLES) == ∅` und
   `set(RLS_STAGED_TABLES) ⊆ declared-policies`.
2. **AC-2** — Für jede Funktion aus IC-1: `pg_get_userbyid(proowner)` == Tabellen-Eigentümer,
   `prosecdef = true`, `proconfig` enthält `search_path=pg_catalog, pg_temp`; `EXECUTE` ist
   für `PUBLIC` entzogen und für `APP_DB_ROLE` vorhanden.
3. **AC-3** — Als `APP_DB_ROLE`, `app.current_tenant` unset: `auth_api_key_lookup` liefert
   für einen geseedeten Key genau eine Zeile mit identischem `key_hash`; der Aufrufer
   bestätigt per `hmac.compare_digest`.
4. **AC-4** — Als `APP_DB_ROLE`: `auth_resolve_roles(user)` liefert exakt die nicht-
   suspended Rollen aus `at_user_role`.
5. **AC-5** — Mit `app.rls_preauth_enforced='on'` und `app.current_tenant` unset liefert
   `SELECT count(*) FROM at_api_key` (bzw. `at_user_role`) als `APP_DB_ROLE` **0**.
6. **AC-6** — Flag OFF: Login und API-Key-Authentifizierung funktionieren unverändert
   (bestehende Auth-Tests grün; keine neue 401/403-Klasse).
7. **AC-7** — Alle vier `as_*`-Tabellen haben eine nullable `tenant_id`-Spalte mit
   FK auf `pl_tenant(id)`.
8. **AC-8** — Nach Backfill haben alle Zeilen mit auflösbarer `workspace_id` eine
   `tenant_id`; Orphans bleiben NULL, werden gezählt und geloggt; keine Zeile wurde
   gelöscht.
9. **AC-9** — Flag OFF: die vier `as_*`-Tabellen liefern als `APP_DB_ROLE` dieselbe
   Zeilenzahl wie vor der Migration (Poller unbeeinflusst). Mit
   `app.rls_as_enforced='on'` + `app.current_tenant=X` liefern sie nur X' Zeilen.
10. **AC-10** — `WITH CHECK`: GUC `'on'` + fremder Tenant → INSERT/UPDATE wird abgelehnt;
    GUC unset → INSERT/UPDATE gelingt.
11. **AC-11** — `RLS_AS_ENFORCED` und `RLS_PREAUTH_ENFORCED` default `False` in
    `settings.py` und explizit `False` in `settings_test.py` gepinnt (kein Env-Leak).
12. **AC-12** — Flag per Env auf `True` + Restart setzt die GUC auf allen App-Role-
    Verbindungen ohne Migrationsschritt; kein `FORCE` wird gesetzt.
13. **AC-13** — Jede Migration aus dem Inventar reverse-fähig: nach `migrate <app> <prior>`
    sind Policy, Spalte und Funktionen wieder entfernt; die SSOT-Tests bleiben konsistent.
14. **AC-14** — SSOT: die sechs verschobenen Tabellen sind aus `RLS_EXEMPT_TABLES`
    entfernt und in `RLS_STAGED_TABLES`; `at_refresh_token` und `audit_entry` bleiben exempt.
15. **AC-15** — `test_rls_plain_child_models.py` neu abgeleitet: die vier `as_*` sind in
    `RLS_GUARDED_TABLES`; `_arm_app_role` armiert die Enforcement-GUC; die
    `STAGED_JUSTIFICATION_CLAIMS`-Marker sind in allen vier Entry-Strings verbatim vorhanden.
16. **AC-16** — Admin-Neuableitung: kein SSOT-Text behauptet mehr cross-tenant-Admin-Reads
    der vier Tabellen; die Texte nennen `TenantScopedAdminMixin` als tenant-scoping
    App-Kontrolle und deren Nicht-DB-Garantie.
17. **AC-17** — CI-Harness (F) grün:
    `docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -T backend-test pytest -q backend/persistence/tests/test_rls_coverage.py backend/persistence/tests/test_rls_plain_child_models.py`
18. **AC-18** — `at_refresh_token` hat **keine** Policy und **keinen** Code-Switch; die
    STOPP-S1-Begründung steht in `RLS_EXEMPT_TABLES["at_refresh_token"]` und im Risk-Register.

---

## Risk-Register + STOPP-Marker

| ID | Risiko | Wirkung | Umgang |
|---|---|---|---|
| R-1 | **STOPP-S1 — Refresh-Token-Pfad nicht risikofrei schließbar in diesem Change.** `rotate_refresh_token` verdichtet Lesen (`authentication.py:387-391`), Sperren, Spend-UPDATE (`:424-425`), Family-Burn (`:455-459`) und Insert (`password_authentication.py:271-277`) zu einer auth-kritischen Transaktion; Reuse-Detection/Grace (`:402-422`) und die Logout-Best-Effort-Semantik (`:461-485`) sind load-bearing. Ein Code-Switch in dieselbe Change würde Auth-Verhalten ändern, ohne dedizierte Regression-Suite. | Auth könnte brechen | **Nicht scharf schalten.** Minimaler sicherer Teilsatz = `at_api_key` + `at_user_role` (read-only). `at_refresh_token` bleibt exempt; IC-1c ist nur Design-Vertrag für ein Folge-Review. |
| R-2 | Flag ON bricht den Outbox-Poller (Kandidatenliste + Write-backs ohne Tenant) | Event-Bus steht | **Enforcement DEFAULT OFF.** ON erst nach A4 (Poller-Tenant-Arming + `SECURITY DEFINER`-Kandidatenliste). A4 ist Voraussetzung, nicht Teil des OFF-Ships. |
| R-3 | Weitere `.unscoped`-Leser von `at_api_key` außerhalb des Funktionpfads | RLS würde sie still leeren | Vor `RLS_PREAUTH_ENFORCED=on`: `grep`-Inventar aller `ApiKey.unscoped`/`UserRole.unscoped`-Leser; nicht verifizierte Fundstellen blockieren den Flip. (In diesem Change nicht vollständig verifiziert.) |
| R-4 | Orphan-Zeilen mit NULL-`tenant_id` | Bei ON unsichtbar (fail-closed), bis sie gestampt sind | Backfill zählt + loggt; Writer-Stamp (A4) nötig; kein Delete. |
| R-5 | Flag-Flip erfordert Restart, kein echter Hot-Toggle | Betriebsfenster | Offene Frage O-1; als Restriktion dokumentiert, nicht als Bug. |
| R-6 | FK `NOT VALID` → `VALIDATE` | Lock auf großer Tabelle | `ADD CONSTRAINT ... NOT VALID` sperrt schwach; `VALIDATE` nach Backfill; reverse-fähig. |

**Residual, das dokumentiert-exempt bleibt, falls nicht geschlossen:** `at_refresh_token`
und `audit_entry` bleiben in `RLS_EXEMPT_TABLES` mit explizitem, weiterhin gültigem
Justification-Text. Kein „covered AND exempt"-Zustand entsteht.

### M2-Verdikt (explizit)
Die **full pre-auth replacement ist NICHT vollständig risikofrei** (R-1, R-3). Der minimale
sichere Teilsatz ist: `at_api_key`-Lookup + `at_user_role`-Rollenauflösung über
`SECURITY DEFINER` (IC-1a/1b) mit GUC-guarded Staged-Policy (IC-2/3). Der Refresh-Pfad wird
per **STOPP-S1** abgetrennt und in einem eigenen, review-ten Change mit dedizierter
Auth-Regression-Suite nachgezogen.

### M3-Verdikt (explizit)
Gewählt: **Option (i)** — GUC-guarded permissive Policy. Begründung: (a) OFF lässt den
Poller unberührt (Prädikat TRUE bei unset GUC); (b) ON erfordert kein Schema-/Policy-Update;
(c) reversibel durch `DROP POLICY`. Option (ii) „Policy anlegen, RLS DISABLED" scheitert an
(b) (ENABLE bräuchte eine Migration/Deploy). Option (iii) „permissiv, dann verschärfen"
scheitert ebenfalls an (b) und lässt eine permissive Phase ohne GUC-Treiber. `NOT FORCE`
ist hier korrekt, weil `APP_DB_ROLE` nicht Owner ist; `NOT VALID` gilt **nicht** für
Policies (M4).

### M4-Verdikt (explizit)
`NOT VALID` → `VALIDATE` betrifft **keine Policy**, sondern die **FK-Constraint**
`FOREIGN KEY (tenant_id) REFERENCES pl_tenant(id)`: sie wird `NOT VALID` angelegt
(`application/0030`) und nach dem Backfill `VALIDATED` (`application/0031`). Eine
`CHECK`/`NOT NULL`-Constraint auf `tenant_id` wird **nicht** angelegt, weil die Spalte im
Staging nullable bleiben muss. Policies kennen kein `NOT VALID`.

---

## Offene Fragen (User-Freigabe)

- **O-1** — Ist „ON ohne neuen Deploy" akzeptabel als **Env-Flag + Restart** (kein neues
  Schema/Code), oder wird ein echter Hot-Toggle ohne Restart gefordert? Letzteres wäre ein
  eigenes Thema (Runtime-Flag-Registry existiert nicht, recon D) und ein BLOCKER für M3.
- **O-2** — Orphan-Politik bestätigen: `tenant_id` bleibt NULL (fail-closed bei ON), kein
  Delete, nur Zählung/Log? (Spec-Default; braucht Freigabe.)
- **O-3** — Ist der STOPP-S1-Rest (Refresh-Pfad abgetrennt) für dieses Issue akzeptiert,
  oder soll der Refresh-Schreibpfad in #1136 mitgenommen werden (dann mit dedizierter Suite)?
- **O-4** — Soll die FK auf `pl_tenant(id)` mit `ON DELETE`-Verhalten versehen werden
  (Default `NO ACTION` vorgeschlagen), oder ohne?

---

## ADR-Entwürfe (Kurzform, im Spec dokumentiert — keine separaten Files)

- **ADR-E1** — *GUC-guarded permissive Policy für gestagte RLS-Erweiterung.* Kontext:
  App-Role ist nicht Owner, `NOT FORCE` schützt nur Owner, `NOT VALID` gilt für Policies
  nicht. Entscheidung: permissiv-wenn-GUC-unset, Flag steuert GUC. Folge: Enforcement ohne
  Schemawechsel; Restart-Kaveat (O-1).
- **ADR-E2** — *Pre-Auth-Credentials hinter `SECURITY DEFINER` mit Owner-Privileg,
  `hmac.compare_digest` bleibt in Python.* Kontext: Credential-Lookup ist die Ursache des
  Tenant-Kontexts. Entscheidung: read-only Lookup-Funktionen, fixer `search_path`, minimale
  `EXECUTE`-Grants. Folge: Refresh-Writepfad bleibt offen (STOPP-S1).
- **ADR-E3** — *`as_*` bleiben plain Models mit expliziter `tenant_id`-Spalte, keine
  `TenantScopedModel`-Migration.* Kontext: Poller liest ohne Tenant-Kontext über `objects`.
  Entscheidung: additive Spalte + Policy. Folge: kein Manager-/Default-Binding-Bruch.

---

*Erstellt durch `concept-specifier` am 2026-10-04. Kein Produktcode, keine Migration, kein Push.
Nächster Schritt: Review durch `concept-reviewer` (Loop `concept-specify-loop`), danach
Planung; Implementierung erst nach Plan.*
