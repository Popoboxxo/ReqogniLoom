---
type: THREAT-MODEL
scope: audit-review-2026-09-sec-04
status: final
date: 2026-10-03
author_agent: senior-developer
epic: SEC — Security & Authorization
unit: SEC-04
related_adr: [ADR-011, ADR-013]
findings: [AUD-2026-09-223, AUD-2026-09-N1, AUD-2026-09-240]
---

# SEC-04 — Privilegierte Key-Widerrufung & Admin-Härtung (Threat Model)

> Nur maskierte Kennungen. Es sind **keine** Key-Werte, Token oder Secrets in
> diesem Dokument enthalten. Kein Produktcode in diesem Dokument; die Umsetzung
> liegt in den unten genannten Dateien.

## 1. Ausgangslage

Zwei zusammenhängende Befunde aus dem Audit 2026-09:

- **AUD-2026-09-223 / N1** — `/admin/` ist exponiert und ohne Brute-Force-Schutz;
  die Django-Admin-Registrierungen arbeiten mit `unscoped()`, d. h. ein
  Staff-User von Tenant A kann Tenant-B-Zeilen lesen und ändern. Zusätzlich
  liegt `WebhookSubscription.secret` (HMAC-Signaturgeheimnis) im Klartext im
  Admin-Formular.
- **Residuum Key-Widerruf** (verifiziert in
  `docs/audit/2026-09/review/plan/SECURITY_TRACK_EXECUTION.md`, Phase 2-Rest) —
  `AuthenticationService.revoke_api_key(*, api_key_id, user_id=None)`
  (`backend/auth_tenancy/services/authentication.py:718`) prüft Eigentum nur,
  wenn `user_id` übergeben wird. Der REST-Endpunkt
  `DELETE /api/v1/api-keys/<pk>/` übergibt immer die `user_id` des Aufrufers
  (`backend/rest_api/api_key_views.py:424`) und ist damit **self-scoped**: ein
  fremder Key liefert `404`. Es gab **keinen** Management-Command-Pfad. Aktive
  Legacy-Keys ohne `expires_at` und ohne Workspace-Fence, deren Owner nicht mehr
  verfügbar ist (z. B. `34e0aeae…`, Owner `e2e-user-…`, Scope `admin`), waren
  damit ohne direkten DB-Write **nicht widerrufbar**.

## 2. Was ein Operator heute legitim tun kann (ohne direkten DB-Write)

| Pfad | Verhalten | Deckt fremde/legacy Keys? |
|---|---|---|
| `inventory_api_keys` (read-only) | Inventar aller Keys, Scope/Fence/Expiry/Usage | nur Beobachtung |
| `cleanup_revoked_api_keys` | löscht **bereits widerrufene** Rows | nein |
| `DELETE /api/v1/api-keys/<pk>/` | self-scoped; `404` bei fremdem Owner | nein |
| MCP | exponiert **kein** Key-Management | nein |
| Django-Admin (Superuser, `unscoped`) | manueller Spalten-Edit, umgeht Service + Fence | ja, aber nicht auditierbar |

Der einzige funktionierende Weg war also ein manueller Admin-Spalten-Edit mit
vollständigem Cross-Tenant-Bypass — semantisch ein direkter DB-Write und im
Audit als „braucht gesonderte Freigabe“ markiert. **Das ist die Lücke.**

## 3. Warum Owner-scoped Widerruf für fremde/legacy/fence-lose Keys nicht reicht

Ein Key ist kein reines Nutzer-Artefakt. Er trägt einen `scope`
(`admin`/`author`/`read_only`) und wirkt im Namen des Owners; Governance-Keys
(`admin`) sind eine **Ressource des Tenants**, nicht des Kontos. Die
Ownership-Achse beantwortet „wer darf **diesen** Key widerrufen“ aus dem
Request-Kontext (wer fragt) statt aus der Ressource (welcher Key). Damit gilt:

- Ist der Owner deaktiviert/gelöscht/nicht verfügbar, ist ein aktiver
  Governance-Key **unkontrollierbar** — obwohl der Tenant ihn weiter trägt.
- `expires_at=NULL` (nie ablaufend) und `workspace_ids=[]` (kein Fence)
  verschärfen das: der Key bleibt unbegrenzt gültig.
- ADR-011 Punkt 6 benennt genau diese Achse: Governance ist eine **deklarierte
  Ressourceneigenschaft**, kein Request-Feld; die Minimalregel verlangt einen
  Tenant-Admin-Pfad unabhängig vom Owner. ADR-011 verweist die vollständige
  Rollen-/Scope-Matrix ausdrücklich auf eine Folge-ADR (Ownership-/Governance-ADR)
  zu SEC-04/SECTRACK-01.

Solange diese Folge-ADR nicht entschieden ist, braucht es einen **eng gefassten,
expliziten** Operator-Pfad, der die Fähigkeit freischaltet, ohne die
self-scoped REST-Semantik zu verwässern.

## 4. Umsetzung in diesem Unit (SEC-04)

### 4.1 Admin-Härtung (Tenant-Isolation + Key-Material)

- Neuer, wiederverwendbarer `TenantScopedAdminMixin`
  (`backend/persistence/tenant_admin.py`): leitet den Tenant **ausschließlich**
  aus `request.user.tenant_id` ab (nie aus Body/URL/Query), filtert
  `get_queryset` und ergänzt explizite `has_view_permission` /
  `has_change_permission` / `has_delete_permission`-Prüfungen je Objekt.
  Ohne Tenant: fail-closed (`.none()`).
- Angewandt in `backend/auth_tenancy/admin.py` (ApiKey, UserRole,
  ItemPermission, UserWorkspacePreference) und `backend/application/admin.py`
  (WebhookSubscription/-DeliveryLog, DomainEventOutbox/-DLQ, Adr, Risk, Issue).
  Modelle mit `tenant_id` werden direkt gefiltert, Modelle ohne Tenant-Spalte
  über die Workspaces ihres Tenants.
- `ApiKey.key_hash`: aus Formular **und** Suche entfernt (`exclude`, nicht nur
  read-only); `WebhookSubscription.secret`: aus dem Formular entfernt;
  `workspace_id` der Subscription read-only (kein Retargeting in fremde
  Workspaces); `has_add_permission=False` für beide (kein zweiter
  Key-/Secret-Erzeugungspfad über das Admin).
- `list_filter` um `tenant` bereinigt, damit die Filter-Liste keine fremden
  Tenant-Namen enumeriert.

### 4.2 Privilegierter Operator-Pfad (Management-Command)

`backend/auth_tenancy/management/commands/revoke_api_key.py`:

- `--key-id` akzeptiert volle UUID oder 8+ Zeichen-Präfix; mehrdeutiges Präfix
  wird abgelehnt (nie geraten).
- `--reason` (Pflicht) und `--actor` (Default `system:revoke_api_key`).
- Nutzt den **bestehenden** Service `AuthenticationService.revoke_api_key`
  **ohne** `user_id` — der dokumentierte, ownership-unabhängige Modus. Der
  REST-Pfad bleibt unverändert self-scoped (`api_key_views.py:424`).
- **Idempotent**: bereits widerrufene Keys werden nur gemeldet, kein zweiter
  Audit-Eintrag.
- **Dry-run per Default**; `--apply` ist der explizite Mutationsschalter.
- Schreibt genau einen append-only `AuditEntry` im Tenant des Keys
  (`op=delete`, `entity_type=ApiKey`, `change_reason=--reason`, Metadaten ohne
  Geheimnis). Widerruf und Audit teilen eine Transaktion.
- Gibt **niemals** Key-Material aus (nur UUID und nicht-geheime Metadaten).

## 5. Threat Model — die 4 Fragen

### 5.1 Was bauen wir?

Einen tenant-skopierten Django-Admin (Isolationshülle ADR-011) und einen
expliziten, auditierten CLI-Pfad zum Widerruf **eines** API-Keys unabhängig von
dessen Owner. Betroffen: Admin-Registrierungen der Apps `auth_tenancy` und
`application`; ein neuer Management-Command; ein bestehender Domain-Service
wird genutzt, nicht verändert. Keine Schema-/RLS-Änderung.

### 5.2 Was kann schiefgehen?

| # | Szenario | Wirkung |
|---|---|---|
| S1 | Staff-User Tenant A liest/ändert Tenant-B-Daten im Admin | Cross-Tenant-Datenleck / -Manipulation |
| S2 | `secret`/`key_hash` aus dem Admin auslesbar | Offenlegung von Signier-/Credential-Material |
| S3 | Operator widerruft versehentlich den falschen Key | Verfügbarkeitsverlust; schwer rückgängig |
| S4 | Privilegierter Command wird zum Umgehungsvektor für beliebige Keys | Missbrauch der Governance-Achse |
| S5 | Audit-Eintrag fehlt/fälscht den Vorgang | Keine Nachvollziehbarkeit des Widerrufs |
| S6 | Brute-Force gegen `/admin/login/` | Kontoübernahme der zweiten Admin-Fläche |

### 5.3 Was tun wir dagegen?

| # | Gegenmaßnahme |
|---|---|
| S1 | `TenantScopedAdminMixin`: `get_queryset` + per-Objekt-Permissions aus `request.user.tenant_id`, fail-closed ohne Tenant. Getestet über Changlist **und** Change-URL. |
| S2 | `exclude` (nicht read-only) für `key_hash`/`secret`, Entfernen aus Suche/`list_display`, `has_add_permission=False`. Test prüft Formularfelder. |
| S3 | Dry-run per Default; `--apply` als expliziter Schalter; mehrdeutiges Präfix wird abgelehnt; keine Bulk-Syntax. |
| S4 | Der Command ist die **einzige** Ergänzung der Ownership-Semantik; der REST-Endpunkt bleibt self-scoped (Regressionstest). Die vollständige Governance-Matrix ist als Folge-ADR markiert. |
| S5 | Append-only `AuditEntry` in derselben Transaktion; `--reason` Pflicht; `details.origin=management-command`. |
| S6 | **Nicht implementiert** — siehe §7. |

### 5.4 Was sind die Konsequenzen?

- **Positiv:** Das dokumentierte Residuum (`34e0aeae…`) ist über einen
  legitimen, auditierten Pfad widerrufbar; das Admin ist keine Cross-Tenant-
  Fläche mehr für die in SEC-04 erfassten Registrierungen; Signier-/Key-Material
  ist aus dem Admin entfernt.
- **Negativ / Restrisiko:** Der Command ist eine bewusst privilegierte,
  ownership-ignorierende Fähigkeit. Sein Schutz ist die CLI-Zugangsgrenze plus
  Audit-Trail — **kein** RBAC-Gate im Command selbst. Bis zur Ownership-/
  Governance-ADR (ADR-011 Punkt 6) bleibt „wer den Command ausführen darf“
  eine Umgebungs-/Betriebsentscheidung, keine technisch erzwungene Rolle.
- **Kein Ersatz für SEC-03:** Keys ohne `expires_at`/Workspace-Fence werden
  hierdurch widerrufbar, aber nicht automatisch abgesichert.

## 6. Scope-Grenze (bewusst, nicht versteckt)

- **Weitere Admin-Registrierungen** (persistence, workflow, baseline, diagram,
  icd, presets, se_metrics, resilience, audit, admin_ops) verwenden weiterhin
  `unscoped()` und sind **nicht** Teil dieses Units. `TenantScopedAdminMixin`
  ist als gemeinsamer Seam vorbereitet; die flächendeckende Anwendung ist ein
  eigener Sweep (Empfehlung: Folgearbeit, da dieselbe Klasse wie N1). Diese
  Grenze ist hier deklariert, damit der SEC-04-Nachweis nicht als globaler
  Admin-Isolationsnachweis überzeichnet wird.
- **RLS** wurde nicht angefasst; **keine Migration** erstellt
  (`makemigrations --check` → „No changes detected“).

## 7. HARD-STOP / nicht umgesetzt

- **Brute-Force-Schutz für `/admin/login/`** (Finding 223): nicht umgesetzt.
  Grund: `django-axes` o. ä. erfordert eine **neue Abhängigkeit plus
  Migrationen** und ist eine Entscheidung über die *Authentifizierungs*-
  Drosselung — nicht über die *Autorisierungsachse* von ADR-011/013. Unter der
  HARD-STOP-Regel (keine Migrationen außer strikt nötig; keine Entscheidung
  außerhalb ADR-011/013) wird dieser Teil gestoppt und zur eigenen Entscheidung
  gemeldet. Vorhandener Schutz bleibt `is_staff`/`is_superuser`; `/admin/` ist
  damit nicht anonym erreichbar.
- **Dedizierter `op` für Key-Widerruf**: statt eines neuen Vokabular-`op`
  nutzt der Command `OP_DELETE` mit `entity_type=ApiKey` — es entsteht **kein**
  Migrations- oder Vokabularbruch.

## 8. Nachweis

- Regressionstests: `backend/tests/test_sec_04_admin_key_revocation.py`
  (8 Tests, RED→GREEN belegt).
- Live-Dry-Run:
  `python manage.py revoke_api_key --key-id 34e0aeae --reason "…"` löst den
  realen Key `34e0aeae…` auf (`name=wp1a-tenantb`, `scope=admin`) und mutiert
  nichts.
