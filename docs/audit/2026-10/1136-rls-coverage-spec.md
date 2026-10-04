# RLS-Coverage-Erweiterung (Pre-Auth + `as_*` Worker-Tabellen) — Spec
> Status: Entwurf (2026-10-04) · Revision: Iteration 1 (Review-Loop)
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
- Jeder Schritt reverse-fähig als **eine Reversibility-Unit** (Code + SSOT + Migration
  gemeinsam); die Pipeline (Migrations) bleibt der Rollback-Träger.

### Nicht-Ziele

- **`audit_entry` bleibt außen vor.** Es steht weder in diesem Issue noch im Approved Plan
  zur Schließung (`RLS_EXEMPT_TABLES["audit_entry"]`, `test_rls_coverage.py:99-110`); es
  behält seinen Ausnahme-Eintrag unverändert.
- **Kein `FORCE ROW LEVEL SECURITY`** und keine Aktivierung von Enforcement im Default.
  `FORCE` auf `at_api_key`/`at_user_role` würde zudem die `SECURITY DEFINER`-Funktionen
  nicht retten (sie sind superuser-owned), sondern nur die Owner-Verbindungen binden — siehe
  R-8.
- **Keine Änderung am Refresh-Token-Schreibpfad** in diesem Change — siehe **STOPP-S1**
  (§Risk). `at_refresh_token` bleibt ausgenommen.
- Keine Änderung an der Auth-Semantik (HMAC-Vergleich bleibt in Python, Rotation/
  Family-Burn-Semantik unberührt, „last_used_at" wird weiterhin nicht geschrieben).
- Keine neue Runtime-Feature-Flag-Registry (recon D: existiert nicht, wird nicht gebaut).
- **Kein `BYPASSRLS`-Rollenumbau** in diesem Change (nur als getrackter Follow-up, R-7).

---

## Interface Contracts

Alle Contracts benennen Ziel-Datei + Ziel-Symbol und sind vollständig typisiert.

### IC-1 — Pre-Auth `SECURITY DEFINER`-Funktionen (Owner = Tabellen-Owner)

**Owner & Sicherheit (für jede Funktion identisch):**
- `SECURITY DEFINER`; Owner ist die **Tabellen-Eigentümerrolle** (die Migrationsrolle,
  die `at_api_key`/`at_user_role` besitzt — vgl. `persistence/migrations/0048_app_role.py:16-20`).
  Der Owner darf **nicht** `APP_DB_ROLE` sein, sonst wäre `SECURITY DEFINER` wirkungslos
  (APP_DB_ROLE unterliegt der Policy).
- **Owner ist in diesem Deployment ein Superuser (F-05/F8, ehrlich benannt):** Der
  Migrations-/Tabellen-Owner ist der Bootstrap-`POSTGRES_USER` (`0048_app_role.py:6-20`
  beschreibt genau diesen Superuser). `APP_DB_ROLE` ist `NOSUPERUSER` (`:57-61`), aber
  die **Funktion** ist superuser-owned. Ein `NOT rolsuper` ist daher **nicht** zusicherbar
  und wird **nicht** geprüft — das ist ein dokumentiertes Residual (R-8). Bevorzugte
  Härtung (getrackter Follow-up, nicht hier): dedizierte NOLOGIN-Owner-Rolle bzw.
  Ownership-Transfer. Bis dahin gelten harte Constraints für die Funktionskörper:
  1. **kein dynamisches SQL** (`EXECUTE`, `format()`, `quote_ident`-Bau) — Funktionen
     bleiben `LANGUAGE sql` (IC-1a/1b) bzw. statisches `plpgsql` ohne dynamische Ausführung
     (IC-1c);
  2. fixer `search_path`;
  3. jede Relation schema-qualifiziert.
  **Reviewer-Obligation:** Der Reviewer prüft den Funktionskörper gegen (1)-(3) und
  dokumentiert das Ergebnis im Review-Protokoll.
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
    ORDER BY k.id          -- deterministisch; ersetzt die zufällige .first()-Ordnung (F-14)
    LIMIT 1;
$$;
```
- Die Funktion liefert die **Zeile** (nicht `bool`) und genau die Spalten, die
  `validate_api_key` heute über `select_related("user")` liest
  (`backend/auth_tenancy/services/authentication.py:511-515`, `:537`, `:541-550`).
- Die Funktion darf `key_hash` nicht weglassen; ohne ihn würde der Python-Vergleich zum
  Boolean-Oracle.

**IC-1a-caller — Ergebnisstruktur & Feld-Mapping (F-06)**

Der Aufrufer ersetzt das `RefreshToken`/`ApiKey`-ORM-Objekt durch eine explizite,
typisierte Struktur. In `backend/auth_tenancy/services/authentication.py`:

```python
class ApiKeyLookupRow(NamedTuple):        # Ziel-Symbol: AuthenticatedApiKeyRow
    id: UUID
    user_id: UUID
    key_hash: str
    revoked_at: datetime | None
    expires_at: datetime | None
    principal_type: str
    scope: str | None
    workspace_ids: list[str]
    agent_label: str
    tenant_id: UUID | None
    user_is_active: bool
```
- **Kein `SELECT *`.** Der Aufruf nennt die Spalten explizit in fester Reihenfolge
  (`SELECT id, user_id, key_hash, revoked_at, expires_at, principal_type, scope,
  workspace_ids, agent_label, tenant_id, user_is_active FROM public.auth_api_key_lookup(%s)`),
  und mappt sie positionsbasiert auf `ApiKeyLookupRow`.
- `api_key.is_expired` ist heute eine **Model-Property** (`auth_tenancy/models.py:181-186`),
  keine Spalte. Der Aufrufer berechnet sie aus `expires_at` in Python:
  `expires_at is not None and expires_at <= timezone.now()`.
- Der Python-seitige Konstantzeit-Vergleich (`authentication.py:522-524`) bleibt. Die
  Statusprüfungen (`:528-558`) laufen **über die neue Struktur** weiter (AC-21). Die Funktion
  **kürzt** die Entscheidung nicht ab.

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
- Ersetzt `UserRole.unscoped.filter(user_id=..., suspended_at__isnull=True).values_list("role", flat=True)`
  (`password_authentication.py:164-167`).
- **Normalisierung bleibt (F4):** Der Aufrufer behält
  `tuple(sorted({str(r).lower() for r in rows}))` (`password_authentication.py:168`) —
  Dedup, Sortierung und Kleinschreibung sind identisch.
- **Residual (security F10):** `auth_resolve_roles` ist nach Pre-Auth-Enforcement ein
  **tenant-agnostischer RLS-Bypass-Read** (die Funktion liefert die Rollen des Users über
  alle Workspaces, exakt wie heute `UserRole.unscoped`). Das ist bewusst faithful und
  wird als Residual R-9 dokumentiert; ein optionales `tenant_id`-Join wäre eine
  Verhaltensänderung und ist nicht Teil dieses Changes.

**IC-1c — Refresh-Token-Funktionen (designt, aber in diesem Change NICHT aktiviert — STOPP-S1)**

Design-Vertrag (für das Folge-Review; **keine** Aktivierung / kein Code-Switch hier).
Alle Built-ins schema-qualifiziert (F7): `pg_catalog.gen_random_uuid()`, `pg_catalog.now()`.

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
AS $$ UPDATE public.at_refresh_token SET used_at = pg_catalog.now() WHERE jti = p_jti; $$;

CREATE FUNCTION public.auth_revoke_refresh_family(p_session_id uuid, p_reason text)
RETURNS integer
LANGUAGE sql VOLATILE SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
  WITH upd AS (
    UPDATE public.at_refresh_token
       SET revoked_at = pg_catalog.now(), revoked_reason = p_reason
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
  VALUES (pg_catalog.gen_random_uuid(), p_user_id, p_tenant_id, p_jti, p_session_id,
          p_expires_at, pg_catalog.now(), pg_catalog.now())
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
| `backend/auth_tenancy/services/authentication.py:511-515` | `ApiKey.unscoped.select_related("user")...first()` | expliziter Spalten-`SELECT` aus `public.auth_api_key_lookup(%s)` → `ApiKeyLookupRow` |
| `backend/auth_tenancy/services/password_authentication.py:164-168` | `UserRole.unscoped.filter(...).values_list(...)` | `SELECT role FROM public.auth_resolve_roles(%s)` + Normalisierung |

### IC-1d — Pre-Auth-Staged-Policy (GUC `app.rls_preauth_enforced`) (F-01)

Eigene DDL für die Pre-Auth-Tabellen; **nicht** das `as_*`-Template. Je Tabelle
`T ∈ {at_api_key, at_user_role}` (ENABLE, **kein FORCE**):

```sql
ALTER TABLE T ENABLE ROW LEVEL SECURITY;
CREATE POLICY T_tenant_isolation ON T
    USING (
        current_setting('app.rls_preauth_enforced', true) IS DISTINCT FROM 'on'
        OR tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid
    )
    WITH CHECK (
        current_setting('app.rls_preauth_enforced', true) IS DISTINCT FROM 'on'
        OR tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid
    );
```
Reverse je `T`: `DROP POLICY IF EXISTS T_tenant_isolation ON T;`
`ALTER TABLE T NO FORCE ROW LEVEL SECURITY;` `ALTER TABLE T DISABLE ROW LEVEL SECURITY;`
(live in `auth_tenancy/migrations/0019`).

### IC-2 — `as_*`: nullable `tenant_id` + staged Policy

Modellfelder (in `backend/application/models.py`), jeweils an den vier Plain-Models
(`DomainEventOutbox`, `DomainEventDLQ`, `WebhookSubscription`, `WebhookDeliveryLog`):

```python
tenant_id = models.UUIDField(null=True, blank=True, db_index=True)
```
- Nullable per Design (Staging). Die Models bleiben **plain `models.Model`** (KEINE
  `TenantScopedModel`-Subklasse) — der Poller liest heute über `objects` ohne
  Tenant-Kontext; ein Wechsel zur TenantManager-Default-Bindung würde ihn brechen.
- **Kein Python-FK-Feld.** Die referentielle Integrität wird **nur per raw SQL** gesetzt
  (`ADD CONSTRAINT ... FOREIGN KEY ... NOT VALID`, dann `VALIDATE`). Dadurch entsteht
  **keine Model-State-Divergenz** und `makemigrations --check` bleibt sauber (AC-24, F-09).
- **`ON DELETE RESTRICT`** (F-13): spiegelt `TenantScopedModel.tenant = models.ForeignKey(
  ..., on_delete=models.PROTECT, ...)` (`persistence/models.py:457-462`, REQ-L2-PL-009).

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

**Zentrale GUC-Verdrahtung (F5):** Es gibt **genau eine** Stelle, die die OPTIONS baut
(z. B. ein Helper `_db_options()` in `settings.py`), der `-c statement_timeout=...`
(`settings.py:359`) mit `-c app.rls_as_enforced=on` bzw. `-c app.rls_preauth_enforced=on`
kombiniert — **nur wenn** das jeweilige Flag `True` ist. Kein zweiter Codepfad darf die
OPTIONS überschreiben. Absicherung:
- `settings_test.py` pinnt beide Flags explizit auf `False` (sonst übernimmt
  `settings_test.py` `DATABASES` ohne OPTIONS → Config-Drift; security F5).
- Ein `django check`-Hook (System check) verifiziert: `flag is True ⇒ GUC-String in
  `DATABASES['default']['OPTIONS']['options']` enthalten` (AC-25).

Damit tragen **alle** App-Role-Verbindungen (Django + Celery + Skripte) die GUC konsistent.
**Ehrliche Einschränkung (security F1):** Die GUC ist ein *placeholder custom GUC* und
damit **app-role-settable und fail-open**. Jede App-Role-Session (inkl. SQL-Injection)
kann `SET app.rls_as_enforced=''` ausführen → Prädikat TRUE → vollständig permissiv.
PostgreSQL bietet ohne Extension keinen rollen-fixierten Custom-GUC; `FORCE` hilft nicht.
Das ist konsistent mit dem bestehenden `app.current_tenant`-Vertrauensmodell (RLS ist
Defense-in-Depth gegen ORM-Fehler, nicht gegen eine kompromittierte Session) — **aber es
darf nicht als „kein Bypass" gelesen werden.** → Residual **R-7**, getrackter Follow-up
(dedizierte Worker-Rolle mit `BYPASSRLS` oder owner-only-writable Control-Row-Prädikat);
**kein Blocker** für den DEFAULT-OFF-Ship, **dokumentiertes Residual** für den ON-Flip.

Semantik pro Tabelle:
| Zustand | GUC (as_/preauth) | Sichtbarkeit (App-Role) | Poller/Auth |
|---|---|---|---|
| **OFF (Default)** | unset | alle Zeilen sichtbar (Prädikat TRUE) | **unverändert** |
| **ON** | `'on'` | nur `tenant_id = app.current_tenant` | as_*: nur nach A4-Fix; preauth: nur über die Funktionen |

**Aktivierungs-Runbook (Notiz, O-1):** „ON" = Env-Flag setzen **und die App-/Celery-
Prozesse neu starten** (Django lädt `settings` beim Start; kein Hot-Toggle, keine Runtime-
Flag-Registry, recon D). Preconditions für ON sind in §Risk (R-2, R-3) und im
Runbook-Kasten unten festgehalten.

```
Aktivierungs-Runbook (Kurzfassung)
  PRE  (preauth) : P2-Code-Switch deployt; R-3-grep-Inventar aller ApiKey/UserRole-
                   .unscoped-Leser leer/erklärt; Auth-Regression grün; STOPP-S1 als
                   eigenes Issue angelegt.
  PRE  (as_*)    : A4 (Poller-Tenant-Arming) deployt; Writer-Stamp tenant_id aktiv;
                   kein Orphan-Rückstau offen.
  FLIP           : RLS_PREAUTH_ENFORCED=true / RLS_AS_ENFORCED=true setzen, Services
                   neu starten, Health-Check; `django check` bestätigt GUC in OPTIONS.
  ROLLBACK       : Flag zurück auf false + Restart (GUC fällt weg → wieder permissiv);
                   bei Bedarf Migrationen rückwärts in der Reversibility-Unit (unten).
```

---

## Datenfluss

### Pre-Auth (IC-1a/1b)
```
HTTP /auth/login/ oder API-Key-Request
  → validate_api_key(plaintext)
      → api_key_hash_candidates(plaintext)  [Python, unverändert]
      → expliziter Spalten-SELECT aus public.auth_api_key_lookup(candidates)  [Owner-Privileg]
      → ApiKeyLookupRow (NamedTuple, kein ORM)
      → hmac.compare_digest(key_hash, candidate)               [Python, unverändert]
      → Status-/Tenant-/Active-/Expiry-/Agent-Scope-Prüfungen  [Python, unverändert]
  → resolve_roles(user)
      → SELECT role FROM public.auth_resolve_roles(user_id)    [Owner-Privileg]
      → tuple(sorted({str(r).lower() for r in rows}))          [Python, unverändert]
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
§Risk – precondition, nicht Teil des OFF-Ships).

### Backfill (M5)
```
as_domain_event_outbox.tenant_id   ← pl_workspace.tenant_id via workspace_id
as_domain_event_dlq.tenant_id      ← pl_workspace.tenant_id via workspace_id
as_webhook_subscription.tenant_id  ← pl_workspace.tenant_id via workspace_id
as_webhook_delivery_log.tenant_id  ← pl_workspace.tenant_id via
                                      as_webhook_subscription.workspace_id
```
- Migrationen laufen als **Owner** → RLS-Bypass ist erwartet und nötig.
- **Orphan-Definition (entschieden, O-2):** Löst eine `workspace_id` zu **keinem** Tenant
  auf (keine passende `pl_workspace`-Zeile), bleibt `tenant_id` **NULL**. Die Migration
  **löscht nichts** und wirft nicht; sie zählt die Orphans und loggt eine WARNING mit der
  Tabelle und der Anzahl. Orphan-Zeilen sind bei Flag ON unsichtbar (USING: `NULL = ...`
  ist NULL → kein Match) und fail-closed; im OFF-Zustand bleiben sie wie heute sichtbar.

---

## Staged Rollout / Migrationen

Reihenfolge ist bindend. **Reversibility-Unit (F-04):** Code-Änderung (P2), SSOT/Tests
(P7) und die Migrationen werden **gemeinsam** als eine Unit zurückgerollt. Reverse-Order:
**erst** Code + SSOT, **dann** Migrationen rückwärts. Grund: die statische Invariante
`set(RLS_STAGED_TABLES) ⊆ declared` (AC-1) wird absichtlich rot, wenn Migrationen ohne die
SSOT-Änderung zurückgerollt werden — sie erzwingt genau die gemeinsame Rücknahme. Ein
partieller Rollback (nur `migrate <app> <prior>`) ist damit per Design rot, nicht ein Bug.

**P1 — Pre-Auth-Funktionen** (`auth_tenancy/0018`): IC-1a/1b anlegen + Grants.
**P2 — Pre-Auth-Code-Switch** (Python, kein Migrationsschritt): die zwei Aufrufer aus
IC-1 auf die Funktionen umstellen. Voraussetzung für `RLS_PREAUTH_ENFORCED=on`.
**P3 — Pre-Auth-Staged-Policy** (`auth_tenancy/0019`): IC-1d anwenden (ENABLE +
GUC-guarded Policy auf `at_api_key`, `at_user_role`). Kein FORCE.
Enforcement hinter `RLS_PREAUTH_ENFORCED`.
**P4 — `as_*` Spalte** (`application/0030`): nullable `tenant_id` + FK `NOT VALID` ×4.
**P5 — Backfill + VALIDATE** (`application/0031`): UPDATE aus `pl_workspace` (bzw. über
Subscription), `VALIDATE CONSTRAINT`; Orphan-Zählung/Log.
**P6 — `as_*` Staged-Policy** (`application/0032`): IC-2 anwenden (ENABLE + GUC-guarded
Policy ×4, kein FORCE). Enforcement hinter `RLS_AS_ENFORCED`.
**P7 — SSOT/Tests** (§SSOT).
**A4 — Poller-Tenant-Arming** (deferred, Voraussetzung für `RLS_AS_ENFORCED=on`): designt,
**nicht** Teil des OFF-Ships.

---

## SSOT + Test-Änderungen

SSOT bleiben `backend/persistence/tests/test_rls_coverage.py` (`RLS_EXEMPT_TABLES`) und
`backend/persistence/tests/test_rls_plain_child_models.py`. Invariante: **eine Tabelle
niemals gleichzeitig covered UND exempt**; `declared != enforced`.

1. `RLS_EXEMPT_TABLES` (`test_rls_coverage.py:75-262`) verliert `at_api_key`,
   `at_user_role`, `as_domain_event_outbox`, `as_domain_event_dlq`,
   `as_webhook_subscription`, `as_webhook_delivery_log`.
   Behalten: `at_refresh_token` (STOPP-S1), `audit_entry` (Nicht-Ziel).
2. Neuer State `RLS_STAGED_TABLES: dict[str, str]` mit den sechs verschobenen Tabellen.
   Der Text nennt je Tabelle: **GUC** (`app.rls_preauth_enforced` bzw.
   `app.rls_as_enforced`), `tenant_id`-Quelle, Enforcement OFF/ON, Orphan-Verhalten,
   **fail-open-Residual R-7** und **superuser-owner-Residual R-8**.
3. Neuer State `STAGED_POLICY_GUCS: dict[str, str]` (Tabelle → erwarteter GUC-Name) und
   ein statischer Test (F-01): für jeden `RLS_STAGED_TABLES`-Eintrag referenziert die
   Policy in der Migration **genau** den deklarierten GUC. Der Test extrahiert die
   `CREATE POLICY`-Fragmente (analog `_sql_fragments`, `test_rls_coverage.py:288-304`) und
   matcht `current_setting('<guc>', true)`.
4. `RLS_EXEMPT_PLAIN_TABLES` (`:269-276`) → `frozenset()`.
5. Neuer Invariantentest:
   ```python
   def test_no_table_is_covered_and_exempt_or_staged():
       declared = _tables_with_policy_in_migrations()
       forced = _forced_tables_on_live_schema()          # pg_class.relforcerowsecurity
       assert not (set(RLS_EXEMPT_TABLES) & declared)
       assert not (set(RLS_EXEMPT_TABLES) & set(RLS_STAGED_TABLES))
       assert set(RLS_STAGED_TABLES) <= declared         # declared != enforced
       assert set(RLS_STAGED_TABLES).isdisjoint(forced)  # F-10 / security F9:
       #   FORCE auf staged (pre-auth) Tabellen würde nur die Owner-Superuser-Bindung
       #   ändern und die DEFINER-Funktionen nicht retten — und das Signal verwischen.
   ```
6. `test_rls_policies_exist_on_the_live_schema` (`:430-464`): Policy-Menge =
   `tenant_tables - EXEMPT` (Staged enthalten); FORCE-Menge =
   `tenant_tables - EXEMPT - STAGED` (Staged haben bewusst kein FORCE).
7. `test_rls_plain_child_models.py`:
   - `WORKER_OWNED_TABLES` (`:90-97`) → `STAGED_PLAIN_CHILD_TABLES` (dieselben vier).
   - `_arm_app_role` (`:316-318`) setzt zusätzlich
     `SET app.rls_as_enforced = 'on'` (und `app.rls_preauth_enforced = 'on'`), damit die
     „leer ohne GUC"-Assertion (`:642-667`) den **scharfgeschalteten** Zustand prüft.
     **`_disarm_app_role` (`:321-324`) ergänzt `RESET app.rls_as_enforced` und
     `RESET app.rls_preauth_enforced`** — sonst leakt der session-scoped Wert in spätere
     Tests (F-07).
   - `test_module_inventory_matches_the_rls_exemption_registry` (`:816-842`): an den neuen
     State angepasst; `RLS_GUARDED_TABLES == set(PLAIN_CHILD_TABLES) - set(RLS_EXEMPT_TABLES)`.
   - `test_worker_owned_table_cannot_carry_a_tenant_keyed_policy` (`:900-942`) **ersetzt**
     durch `test_staged_plain_child_table_carries_tenant_key_and_policy`: assertet
     `tenant_id` ist vorhanden, Policy ist vorhanden, Tabelle ist NICHT in
     `RLS_EXEMPT_TABLES`.
   - **`test_worker_owned_table_is_declared_rls_exempt_with_a_justification` (`:845-897`)
     ersetzt (F-02):** Die Funktion liest heute `RLS_EXEMPT_TABLES[table]` und würde nach
     dem Verschieben mit `KeyError` scheitern. Ersatz:
     `test_staged_table_is_declared_staged_with_a_justification` — (a) assertet
     `table in RLS_STAGED_TABLES` und `table not in RLS_EXEMPT_TABLES`; (b) führt die
     Verbatim-Claim-Prüfung **gegen `RLS_STAGED_TABLES[table]`** und die Marker aus
     `STAGED_JUSTIFICATION_CLAIMS` durch; (c) behält die `>200`-Längenprüfung.
   - `CR17_JUSTIFICATION_CLAIMS` (`:199-251`) → `STAGED_JUSTIFICATION_CLAIMS` mit
     Verbatim-Markern (Flag-Name, GUC-Name, `tenant_id`-Herkunft, Orphan-Verhalten,
     „service-layer and code-path only", „enforcement behind flag", „still not enforced
     in production default").
   - **Fixture-Stamping (F-03):** `_seed_two_tenants` (`:537-610`) setzt beim Anlegen der
     vier `as_*`-Zeilen jetzt `tenant_id=<zugehöriger Tenant>`; für
     `WebhookDeliveryLog` aus der Subscription. Nur so ist die positive Filter-Assertion
     (Tenant X sieht X' Zeilen) überhaupt möglich.
   - **Prosa der Compensating-Control-Tests (F-08):** Die Docstrings von
     `test_webhook_table_has_no_reader_outside_the_worker_and_the_admin` (`:945-981`) und
     `test_outbox_table_has_no_reader_outside_the_poller_and_the_admin` (`:984-1090`) sagen
     heute „Raw Row-Level-Security … remains OPEN". Neu: „**staged — policy shipped,
     enforcement OFF by default; the allowlist is defense-in-depth until A4 + flag flip**;
     the compensating control is still not a database guarantee while the flag is OFF."
8. Admin-Prosa-Neuableitung (M6): Die CR-17-Texte behaupten, die vier ModelAdmins läsen
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
| `auth_tenancy` | `0019` | `0018` | IC-1d: ENABLE + GUC-guarded Policy (`app.rls_preauth_enforced`) auf `at_api_key`, `at_user_role` | DROP POLICY, DISABLE |
| `application` | `0030` | `0029_drop_redundant_idem_expires_index` | `AddField tenant_id` (nullable, `db_index=True`) ×4 + `RunSQL ADD CONSTRAINT <fk> FOREIGN KEY (tenant_id) REFERENCES pl_tenant(id) ON DELETE RESTRICT NOT VALID` | `RunSQL DROP CONSTRAINT IF EXISTS` (reverse_sql der RunSQL) **vor** `RemoveField` ×4 |
| `application` | `0031` | `0030` | Backfill aus `pl_workspace` (bzw. Sub-`workspace_id`); `ALTER TABLE ... VALIDATE CONSTRAINT`; Orphan-Zählung/WARNING | `RunPython` setzt `tenant_id = NULL` |
| `application` | `0032` | `0031` | IC-2: ENABLE + GUC-guarded Policy ×4, kein FORCE | DROP POLICY, DISABLE |

- **F-09-Konkretisierung:** Forward `0030` = `AddField` (Django-Model-State) + `RunSQL
  ADD CONSTRAINT ... NOT VALID` (raw, **nicht** im Model-State, da das Model kein FK-Feld
  deklariert). Reverse von `0030` läuft Operations in umgekehrter Reihenfolge: zuerst
  `DROP CONSTRAINT IF EXISTS <fk>` (reverse_sql der `RunSQL`), dann `RemoveField`.
  Das Entfernen der Spalte würde den FK ohnehin kaskadieren, der explizite Drop ist
  trotzdem geführt. Ergebnis: keine Model-State-Divergenz, `makemigrations --check` sauber
  (AC-24).
- `persistence` benötigt **keine** Migration: Grants sind per-Funktion explizit (least
  privilege) statt per `ALTER DEFAULT PRIVILEGES GRANT EXECUTE ON FUNCTIONS`. Ein optionaler
  `persistence/0107` für Default-Function-Privileges ist bewusst **nicht** Teil dieses Changes.
- `settings.py`-Flag-/OPTIONS-Änderung ist kein Migrationsschritt.

---

## Acceptance Criteria (nummeriert, testbar)

1. **AC-1** — Statisch: `set(RLS_EXEMPT_TABLES) ∩ declared-policies == ∅`,
   `set(RLS_EXEMPT_TABLES) ∩ set(RLS_STAGED_TABLES) == ∅`,
   `set(RLS_STAGED_TABLES) ⊆ declared-policies` **und**
   `set(RLS_STAGED_TABLES) ∩ forced-policies == ∅` (Kommentar: `declared != enforced`).
2. **AC-2** — Für jede IC-1-Funktion: `prosecdef = true`, `proconfig` enthält
   `search_path=pg_catalog, pg_temp`, Body enthält **kein** dynamisches SQL
   (`EXECUTE`/`format(`/`quote_ident`), alle Relationen schema-qualifiziert; `EXECUTE` für
   `PUBLIC` entzogen und für `APP_DB_ROLE` vorhanden. (`NOT rolsuper` wird **nicht**
   gefordert — Owner ist der Superuser-Migrations-User, R-8; die Reviewer-Obligation
   prüft den Body.)
3. **AC-3** — Als `APP_DB_ROLE`, `app.current_tenant` unset: `auth_api_key_lookup` liefert
   für einen geseedeten Key genau eine `ApiKeyLookupRow` mit identischem `key_hash`; der
   Aufrufer bestätigt per `hmac.compare_digest`.
4. **AC-4** — Als `APP_DB_ROLE`: `auth_resolve_roles(user)` liefert exakt die nicht-
   suspended Rollen aus `at_user_role`; der Aufrufer normalisiert zu
   `tuple(sorted({str(r).lower() for r in rows}))` (dedup/sort/lower).
5. **AC-5** — Mit `app.rls_preauth_enforced='on'` (IC-1d) und `app.current_tenant` unset
   liefert `SELECT count(*) FROM at_api_key` (bzw. `at_user_role`) als `APP_DB_ROLE` **0**;
   mit `app.current_tenant=X` nur X' Zeilen.
6. **AC-6** — Flag OFF: Login und API-Key-Authentifizierung funktionieren unverändert
   (bestehende Auth-Tests grün; keine neue 401/403-Klasse).
7. **AC-7** — Alle vier `as_*`-Tabellen haben eine nullable `tenant_id`-Spalte; die DB-FK
   auf `pl_tenant(id)` existiert mit `ON DELETE RESTRICT` und ist nach `0031` validiert.
8. **AC-8** — Nach Backfill haben alle Zeilen mit auflösbarer `workspace_id` eine
   `tenant_id`; Orphans bleiben NULL, werden gezählt und geloggt; keine Zeile wurde
   gelöscht.
9. **AC-9** — Fixture `_seed_two_tenants` stempelt `tenant_id` auf alle vier `as_*`-Zeilen.
   Flag OFF: dieselbe Zeilenzahl wie vor der Migration (Poller unbeeinflusst). Mit
   `app.rls_as_enforced='on'` + `app.current_tenant=X` liefern die vier Tabellen **nur X'
   Zeilen** (positiv) und **keine** Fremd-Tenant-Zeilen (negativ).
10. **AC-10** — `WITH CHECK`: GUC `'on'` + fremder Tenant → INSERT/UPDATE wird abgelehnt;
    GUC unset → INSERT/UPDATE gelingt.
11. **AC-11** — `RLS_AS_ENFORCED` und `RLS_PREAUTH_ENFORCED` default `False` in
    `settings.py` und explizit `False` in `settings_test.py` gepinnt (kein Env-Leak).
12. **AC-12** — Flag per Env auf `True` + Restart setzt die GUC auf allen App-Role-
    Verbindungen ohne Migrationsschritt; kein `FORCE` wird gesetzt.
13. **AC-13** — Reversibility-Unit (F-04): Rückrollen von P2 (Code), P7 (SSOT) und den
    Migrationen gemeinsam; dokumentierte Reihenfolge „erst Code + SSOT, dann Migrationen
    rückwärts"; nach vollständigem Rückrollen sind Policy, Spalte, FK und Funktionen
    entfernt und die statischen Invarianten grün. Ein partieller Migrations-Rollback macht
    AC-1 absichtlich rot (Schutz).
14. **AC-14** — SSOT: die sechs verschobenen Tabellen sind aus `RLS_EXEMPT_TABLES`
    entfernt und in `RLS_STAGED_TABLES`; `at_refresh_token` und `audit_entry` bleiben exempt.
15. **AC-15** — `test_rls_plain_child_models.py` neu abgeleitet: die vier `as_*` sind in
    `RLS_GUARDED_TABLES`; `_arm_app_role` armiert die Enforcement-GUC; `_disarm_app_role`
    resettet beide GUCs; die `STAGED_JUSTIFICATION_CLAIMS`-Marker sind in allen vier
    Entry-Strings verbatim vorhanden; die ersetzte Staged-Decl-Testfunktion wirft keinen
    `KeyError`.
16. **AC-16** — Admin-Neuableitung: kein SSOT-Text behauptet mehr cross-tenant-Admin-Reads
    der vier Tabellen; die Texte nennen `TenantScopedAdminMixin` als tenant-scoping
    App-Kontrolle und deren Nicht-DB-Garantie.
17. **AC-17** — CI-Harness (F) grün:
    `docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -T backend-test pytest -q backend/persistence/tests/test_rls_coverage.py backend/persistence/tests/test_rls_plain_child_models.py`
18. **AC-18** — `at_refresh_token` hat **keine** Policy und **keinen** Code-Switch; die
    STOPP-S1-Begründung steht in `RLS_EXEMPT_TABLES["at_refresh_token"]` und im Risk-Register.
19. **AC-19 (F-01)** — Statischer Test `test_staged_policy_uses_its_declared_guc`:
    für jeden `RLS_STAGED_TABLES`-Eintrag extrahiert er die `CREATE POLICY`-Fragmente aus
    der jeweiligen Migration und assertet genau einen `current_setting('<STAGED_POLICY_GUCS[t]>', true)`
    (as_* → `app.rls_as_enforced`; preauth → `app.rls_preauth_enforced`).
20. **AC-20 (F-05/F8)** — Für jede IC-1-Funktion: `pg_get_userbyid(proowner)` ==
    Tabellen-Owner; der Reviewer-Report enthält die Body-Prüfung „kein dynamisches SQL,
    schema-qualifiziert, fixer search_path". Residual R-8 (Owner ist Superuser) ist in
    `RLS_STAGED_TABLES` und im Risk-Register dokumentiert.
21. **AC-21 (F-06/F3)** — Über den neuen Raw-SQL-Pfad laufen alle Statusentscheidungen
    unverändert: revoked → `AuthenticationFailed("api_key_revoked")`; `expires_at` in der
    Vergangenheit → `api_key_expired`; `tenant_id is None` oder `user_is_active == False`
    → `invalid_api_key`; Agent-Key ohne `scope`/nicht-leere `workspace_ids`/`expires_at`
    → `invalid_api_key` (Spiegel von `authentication.py:528-558`).
22. **AC-22 (F4)** — Rollen-Normalisierung über den SQL-Pfad ist dedupliziert, sortiert
    und kleingeschrieben (eigener Test mit gemischter Groß-/Kleinschreibung und Duplikaten).
23. **AC-23 (F-07)** — `_disarm_app_role` resettet `app.rls_as_enforced` **und**
    `app.rls_preauth_enforced`; ein Nachfolgetest, der die GUC nicht explizit armiert,
    sieht einen leeren/neutralen GUC-Zustand.
24. **AC-24 (F-09)** — `makemigrations --check --dry-run` ist sauber (keine
    Model-State-Divergenz durch die raw-FK).
25. **AC-25 (F5)** — `django check`-Hook: ist ein RLS-Flag `True`, enthält
    `DATABASES['default']['OPTIONS']['options']` die passende `-c app.*=on`-Klausel; sonst
    schlägt der Check fehl. `settings_test.py` pinnt beide Flags `False`.
26. **AC-26 (F-11/O-3)** — Exit-Kriterium: sobald A4 landet und der jeweilige Flag
    geflippt ist, schrumpft `RLS_STAGED_TABLES` auf die noch nicht aktivierten Einträge
    (Ziel: `∅`), und für STOPP-S1 existiert ein **eigenes Folge-Issue** (Refresh-Writepfad
    + dedizierte Auth-Regression-Suite).

---

## Risk-Register + STOPP-Marker

| ID | Risiko | Wirkung | Umgang |
|---|---|---|---|
| R-1 | **STOPP-S1 — Refresh-Token-Pfad nicht risikofrei schließbar in diesem Change.** `rotate_refresh_token` verdichtet Lesen (`authentication.py:387-391`), Sperren, Spend-UPDATE (`:424-425`), Family-Burn (`:455-459`) und Insert (`password_authentication.py:271-277`) zu einer auth-kritischen Transaktion; Reuse-Detection/Grace (`:402-422`) und die Logout-Best-Effort-Semantik (`:461-485`) sind load-bearing. Ein Code-Switch in dieselbe Change würde Auth-Verhalten ändern, ohne dedizierte Regression-Suite. | Auth könnte brechen | **Nicht scharf schalten.** Minimaler sicherer Teilsatz = `at_api_key` + `at_user_role` (read-only). `at_refresh_token` bleibt exempt; IC-1c ist nur Design-Vertrag für ein Folge-Review. **Follow-up-Issue verpflichtend (O-3/AC-26).** |
| R-2 | Flag ON bricht den Outbox-Poller (Kandidatenliste + Write-backs ohne Tenant) | Event-Bus steht | **Enforcement DEFAULT OFF.** ON erst nach A4 (Poller-Tenant-Arming + `SECURITY DEFINER`-Kandidatenliste). A4 ist Voraussetzung, nicht Teil des OFF-Ships. |
| R-3 | Weitere `.unscoped`-Leser von `at_api_key` außerhalb des Funktionpfads | RLS würde sie still leeren | Vor `RLS_PREAUTH_ENFORCED=on`: grep-Inventar aller `ApiKey.unscoped`/`UserRole.unscoped`-Leser; nicht verifizierte Fundstellen blockieren den Flip. (In diesem Change nicht vollständig verifiziert.) |
| R-4 | Orphan-Zeilen mit NULL-`tenant_id` | Bei ON unsichtbar (fail-closed), bis sie gestampt sind | Backfill zählt + loggt; Writer-Stamp (A4) nötig; kein Delete (O-2 entschieden). |
| R-5 | Flag-Flip erfordert Restart, kein echter Hot-Toggle | Betriebsfenster | **O-1 entschieden: Env-Flag + Restart akzeptiert.** Runtime-Flag-Registry = eigenes Thema. Runbook-Notiz in IC-3. |
| R-6 | FK `NOT VALID` → `VALIDATE` | Lock auf großer Tabelle | `ADD CONSTRAINT ... NOT VALID` sperrt schwach; `VALIDATE` nach Backfill; reverse-fähig. `ON DELETE RESTRICT`. |
| **R-7** | **Staged GUC ist FAIL-OPEN und APP-ROLE-SETTABLE (security F1).** `app.rls_as_enforced`/`app.rls_preauth_enforced` sind placeholder custom GUCs; jede App-Role-Session (inkl. SQL-Injection) kann `SET app.rls_as_enforced=''` → Prädikat TRUE → vollständig permissiv. PostgreSQL hat ohne Extension keinen rollen-fixierten Custom-GUC; `FORCE` hilft nicht. | RLS ist im ON-Zustand nicht gegen eine kompromittierte Session dicht | **Kein Blocker für den DEFAULT-OFF-Ship; dokumentiertes Residual für den ON-Flip.** In `RLS_STAGED_TABLES`, hier und im Aktivierungs-Runbook benannt. Harte Mitigation als **getrackter Follow-up** (nicht hier implementieren): dedizierte Worker-Rolle mit `BYPASSRLS` **oder** owner-only-writable Control-Row-Prädikat. Konsistent mit dem `app.current_tenant`-Vertrauensmodell (Defense-in-Depth gegen ORM-Fehler, nicht gegen Session-Compromise). |
| **R-8** | **DEFINER-Owner ist der Bootstrap-/Migrations-Superuser (security F8 / F-05).** Die Funktionen sind superuser-owned → RLS-Bypass; `NOT rolsuper` ist nicht zusicherbar. | Größere Privilegien-Eskalation als nötig | Harte Body-Constraints (kein dynamisches SQL, fester `search_path`, schema-qualifiziert), Reviewer-Obligation (AC-2/AC-20); bevorzugte Härtung als getrackter Follow-up: dedizierte NOLOGIN-Owner-Rolle / Ownership-Transfer. |
| **R-9** | **`auth_resolve_roles` ist ein tenant-agnostischer RLS-Bypass-Read (security F10).** Nach Pre-Auth-ON liefert die Funktion die Rollen eines Users über alle Workspaces — faithful zu `UserRole.unscoped` (`password_authentication.py:164-167`), aber bewusst breiter als „eine Zeile". | Bypass-Read-Primitive | Dokumentiertes Residual; optionales `tenant_id`-Join wäre Verhaltensänderung und ist out of scope. |
| R-10 | Config-Drift: `settings_test.py` ersetzt `DATABASES` ohne OPTIONS (security F5) | Staged GUC fehlt unbemerkt | Zentrale GUC-Verdrahtung + `django check` (AC-25) + Flags in `settings_test.py` gepinnt. |

**Residual, das dokumentiert-exempt bleibt, falls nicht geschlossen:** `at_refresh_token`
und `audit_entry` bleiben in `RLS_EXEMPT_TABLES` mit explizitem, weiterhin gültigem
Justification-Text. Kein „covered AND exempt"-Zustand entsteht.

### M2-Verdikt (explizit)
Die **full pre-auth replacement ist NICHT vollständig risikofrei** (R-1, R-3). Der minimale
sichere Teilsatz ist: `at_api_key`-Lookup + `at_user_role`-Rollenauflösung über
`SECURITY DEFINER` (IC-1a/1b) mit GUC-guarded Staged-Policy (IC-1d/IC-3). Der Refresh-Pfad
wird per **STOPP-S1** abgetrennt und in einem eigenen, review-ten Change mit dedizierter
Auth-Regression-Suite nachgezogen (Folge-Issue, O-3/AC-26).

### M3-Verdikt (explizit)
Gewählt: **Option (i)** — GUC-guarded permissive Policy. Begründung: (a) OFF lässt den
Poller unberührt (Prädikat TRUE bei unset GUC); (b) ON erfordert kein Schema-/Policy-Update;
(c) reversibel durch `DROP POLICY`. Option (ii) „Policy anlegen, RLS DISABLED" scheitert an
(b) (ENABLE bräuchte eine Migration/Deploy). Option (iii) „permissiv, dann verschärfen"
scheitert ebenfalls an (b) und lässt eine permissive Phase ohne GUC-Treiber. `NOT FORCE`
ist hier korrekt, weil `APP_DB_ROLE` nicht Owner ist; `NOT VALID` gilt **nicht** für
Policies (M4). **Fail-open-Kaveat R-7** ist Teil dieses Verdikts.

### M4-Verdikt (explizit)
`NOT VALID` → `VALIDATE` betrifft **keine Policy**, sondern die **FK-Constraint**
`FOREIGN KEY (tenant_id) REFERENCES pl_tenant(id) ON DELETE RESTRICT`: sie wird `NOT VALID`
angelegt (`application/0030`) und nach dem Backfill `VALIDATED` (`application/0031`). Eine
`CHECK`/`NOT NULL`-Constraint auf `tenant_id` wird **nicht** angelegt, weil die Spalte im
Staging nullable bleiben muss. Policies kennen kein `NOT VALID`.

### Threat Model (4 Fragen, ADR-011-Traceabilität — F-12)
Gelabelt gegen 《Threat Model — die 4 Fragen》 (interne App, vereinfacht + customer-facing-
Teilaspekte):
1. **Was baust du?** Pre-Auth-Credential-Lookup (ApiKey, UserRole) hinter `SECURITY DEFINER`
   + gestagte RLS auf `at_api_key`/`at_user_role` und vier `as_*`-Tabellen.
2. **Was könnte schiefgehen?** (a) Auth-Outage durch zu frühes Enforcement (STOPP-S1/R-1);
   (b) Event-Bus-Stall bei as_*-ON (R-2); (c) fail-open GUC-Bypass (R-7); (d) Superuser-
   owned DEFINER (R-8). ADR-011-Kontext: Tenant bleibt Isolationshülle, Workspace ist die
   Objekt-Autorisierungsachse (`ADR-011...:168-192`) — dieser Change härtet nur die Hülle.
3. **Was tust du dagegen?** DEFAULT OFF, kein FORCE, `NOT VALID`-Staging, Reversibility-
   Unit, Body-Constraints, Runbook, AC-Gate.
4. **Konsequenzen?** Bis zum ON-Flip bleibt die gemessene DB-Lücke bestehen (wie heute),
   jetzt aber **als gestagter, benannter Rest** statt als undokumentierte Ausnahme;
   R-7/R-8 bleiben als getrackte Residuen offen.

---

## Offene Fragen — Entschieden (User-Freigabe 2026-10-04)

- **O-1 — ENTSCHIEDEN:** Env-Flag + **Restart** ist akzeptiert (kein Hot-Toggle). Runbook-
  Notiz in IC-3. Eine Runtime-Flag-Registry ist ein separates Change.
- **O-2 — ENTSCHIEDEN:** Orphan-Politik bestätigt — `tenant_id` bleibt NULL, kein Delete,
  Count + WARNING.
- **O-3 — ENTSCHIEDEN:** STOPP-S1-Split akzeptiert; der Refresh-Writepfad wird in einem
  **eigenen Change mit dedizierter Auth-Regression-Suite** nachgezogen. **Folge-Issue
  verpflichtend** (AC-26).
- **O-4 — ENTSCHIEDEN:** FK auf `pl_tenant(id)` mit **`ON DELETE RESTRICT`**.

Keine offenen Fragen mehr; nichts blieb unauflösbar ohne User-Entscheidung.

---

## ADR-Entwürfe (Kurzform, im Spec dokumentiert — keine separaten Files)

- **ADR-E1** — *GUC-guarded permissive Policy für gestagte RLS-Erweiterung.* Kontext:
  App-Role ist nicht Owner, `NOT FORCE` schützt nur Owner, `NOT VALID` gilt für Policies
  nicht. Entscheidung: permissiv-wenn-GUC-unset, Flag steuert GUC. Folge: Enforcement ohne
  Schemawechsel; Restart-Kaveat (O-1); **fail-open-Residual (R-7)**.
- **ADR-E2** — *Pre-Auth-Credentials hinter `SECURITY DEFINER` mit Owner-Privileg,
  `hmac.compare_digest` bleibt in Python.* Kontext: Credential-Lookup ist die Ursache des
  Tenant-Kontexts. Entscheidung: read-only Lookup-Funktionen, fixer `search_path`, minimale
  `EXECUTE`-Grants. Folge: Refresh-Writepfad bleibt offen (STOPP-S1); **superuser-owner-
  Residual (R-8)**.
- **ADR-E3** — *`as_*` bleiben plain Models mit expliziter `tenant_id`-Spalte, keine
  `TenantScopedModel`-Migration.* Kontext: Poller liest ohne Tenant-Kontext über `objects`.
  Entscheidung: additive Spalte + raw-FK + Policy. Folge: kein Manager-/Default-Binding-Bruch.

---

## Revision-Log (Iteration 1)

| Finding | Auflösung |
|---|---|
| F-01 / sec-F2 | IC-1d ergänzt (Pre-Auth-Policy, GUC `app.rls_preauth_enforced`); AC-5 verweist darauf; `STAGED_POLICY_GUCS` + statischer Test (AC-19). |
| F-02 | Expliziter Ersatz von `test_worker_owned_table_is_declared_rls_exempt_with_a_justification` durch `test_staged_table_is_declared_staged_with_a_justification` (§SSOT 7). |
| F-03 | `_seed_two_tenants` stempelt `tenant_id`; AC-9 fordert positive + negative Filter-Assertion. |
| F-04 | Reversibility-Unit + Reverse-Order (Code+SSOT vor Migrationen); AC-1/AC-13 angepasst. |
| F-05 / sec-F8 | Owner-Superuser-Residual offen benannt (R-8); Body-Constraints + Reviewer-Obligation; AC-2/AC-20 ohne `NOT rolsuper`. |
| F-06 / sec-F3 | `ApiKeyLookupRow`-NamedTuple + expliziter Spalten-SELECT (kein `SELECT *`) + `is_expired`-Berechnung; AC-3/AC-21. |
| F-07 | `_disarm_app_role` resettet beide GUCs; AC-23. |
| F-08 | Compensating-Control-Docstrings auf „staged, enforcement OFF by default" umgestellt (§SSOT 7). |
| F-09 | FK-Operationen explizit, kein Python-FK-Feld, `makemigrations --check` AC-24. |
| F-10 / sec-F9 | `set(RLS_STAGED_TABLES).isdisjoint(forced)` + `declared != enforced` (§SSOT 5). |
| F-11 | Exit-Kriterium + Follow-up (AC-26). |
| F-12 | Threat-Model-4-Fragen mit ADR-011-Trace ergänzt. |
| F-13 | `ON DELETE RESTRICT` (IC-2, M4, O-4). |
| F-14 | `ORDER BY k.id` (IC-1a). |
| sec-F1 | Fail-open/app-role-settable GUC als R-7 + Aktivierungs-Runbook dokumentiert; kein Blocker für OFF, Residual für ON. |
| sec-F4 | Rollen-Normalisierung erhalten + Test (AC-22). |
| sec-F5 | Zentrale GUC-Verdrahtung + `django check` (AC-25) + Flags in `settings_test.py` gepinnt. |
| sec-F7 | `pg_catalog.gen_random_uuid()` / `pg_catalog.now()` in IC-1c. |
| sec-F10 | Tenant-agnostischer `auth_resolve_roles`-Bypass als R-9 dokumentiert. |
| O-1..O-4 | In „Offene Fragen — Entschieden" übernommen. |

---

*Erstellt durch `concept-specifier` am 2026-10-04; Revision 1 (Review-Loop). Kein Produktcode,
keine Migration, kein Push. Nächster Schritt: Re-Review durch `concept-reviewer`
(Loop `concept-specify-loop`), danach Planung; Implementierung erst nach Plan.*
