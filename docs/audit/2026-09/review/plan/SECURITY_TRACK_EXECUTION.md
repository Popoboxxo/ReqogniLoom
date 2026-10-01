# SECURITY_TRACK — Ausführungsprotokoll

Read-only ergänzt; alle Schlüssel-Kennungen sind **maskiert** (erste 8 Zeichen + `…`).
Es werden **keine** Key-Werte, Token oder Secrets dokumentiert.

---

## Phase 2 — SECTRACK-01 Key-Rotation

- **Datum:** 2026-10-01
- **Branch:** `chore/audit-review-2026-09`
- **Stack:** Compose-Projekt `ai-native-reqflow-poc`, Backend `http://localhost:8001`
- **Policy-Ziel:** aktive Legacy-`user`-Keys mit `scope ∈ {write, admin}` und
  `expires_at=NULL` (F5) sowie der explizit benannte Live-Key `ff77bbd0…`.
- **Revision:** `revoke` ist irreversibel; kein User wurde gelöscht. Kein Push.

### Endpoint-Beleg (verifiziert, nicht geraten)

| Aspekt | Beleg |
|---|---|
| Router-Registrierung | `backend/rest_api/urls.py:234` — `router.register(r"api-keys", ApiKeyViewSet, basename="api-key")` |
| DELETE-Handler | `backend/rest_api/api_key_views.py:371-410` — `destroy()` → `DELETE /api/v1/api-keys/<pk>/` → **204 No Content** |
| Authentifizierung | `backend/rest_api/api_key_views.py:66` — Bearer-Token via `AuthTenancyAuthentication` (DRF-Default-Klassen) |
| Auth für diesen Lauf | `POST /api/v1/auth/login/` (`backend/rest_api/auth_views.py:6`) → Admin-JWT; das JWT ist **kein** API-Key und damit **nicht** im Widerrufs-Set |
| Capability-Gate | `backend/rest_api/api_key_views.py:98-118` — Mutationen (`POST`/`DELETE`) verlangen `Operation.ASSIGN_ROLE`; ein JWT-Bearer trägt `scope="write"` → Tier ADMIN (`backend/auth_tenancy/services/authorization.py:87-92,124-131`) → erlaubt |
| Eigentums-Fence | `backend/auth_tenancy/services/authentication.py:718-736` — `revoke_api_key(api_key_id, user_id)` prüft `api_key.user_id == user_id`; fremde Keys → 404 |

**Exakter Endpoint:** `DELETE /api/v1/api-keys/<id>/` (Bearer-JWT, 204 bei Erfolg).
`/health/` ist der Health-Pfad; der Key-Widerruf läuft ausschließlich über den
oben belegten REST-Pfad.

### Inventar (read-only, `python manage.py inventory_api_keys --format json`)

- **Vorher:** 202 Rows, 10 aktiv (nicht widerrufen); 202 Rotation-Kandidaten.
- **Nachher:** 203 Rows, 6 aktiv; 203 Rotation-Kandidaten (eine zusätzliche
  Kontroll-Probe-Row wurde angelegt und im selben Lauf widerrufen).
- Kein Plaintext im Inventar; nur stabile ID, Metadaten und `revoked_at`.

#### Widerrufene Keys (Kandidaten)

| id (maskiert) | name | principal_type | scope | expires_at | revoked_at (UTC) | DELETE | 401-Nachweis |
|---|---|---|---|---|---|---|---|
| `ff77bbd0…` | audit-live-probe | user | readwrite | NULL | 2026-10-01 19:32:06.964539+00:00 | **204** | nicht messbar (Plaintext redigiert); DB `revoked_at` NOT NULL + API `revoked=true` |
| `bffd186c…` | MCP-UI-Campaign-REQ129-1790534380621 | user | write | NULL | 2026-10-01 19:32:07.004400+00:00 | **204** | nicht messbar (kein Plaintext); DB + API `revoked=true` |
| `05ffb7e7…` | admin_key | user | admin | NULL | 2026-10-01 19:32:07.035036+00:00 | **204** | nicht messbar (kein Plaintext); DB + API `revoked=true` |
| `1e656a1a…` | legacy_write_key | user | write | NULL | 2026-10-01 19:32:07.064485+00:00 | **204** | nicht messbar (kein Plaintext); DB + API `revoked=true` |

**Summe widerrufen: 4** (4× HTTP 204). `ff77bbd0…` wurde **zuerst** widerrufen.

#### DB-Gegenprobe

```
SELECT id, revoked_at FROM at_api_key WHERE id IN (<Kandidaten>);
```

| id (maskiert) | revoked_at NOT NULL |
|---|---|
| `ff77bbd0…` | true |
| `bffd186c…` | true |
| `05ffb7e7…` | true |
| `1e656a1a…` | true |
| `34e0aeae…` | **false** (nicht widerrufen) |

#### `3dcc80d8`-Key

Der aus Commit `3dcc80d8` stammende `reqlo_`-Key ist `7eb7adab…`
(name=`wp1d-probe-dup`, scope=`write`, Owner `admin`) und war **bereits** am
2026-09-30 19:07:05.581479+00:00 widerrufen — kein Handlungsbedarf.

### 401-Nachweis

Der Widerruf-Pfad wurde end-to-end über MCP (`POST /mcp/`, `X-API-Key`) belegt
mit einer **frischen Kontroll-Probe** (Plaintext nur einmalig, nie protokolliert):

| Messung | Endpoint | Status |
|---|---|---|
| Kontrolle vor Widerruf | `POST /mcp/` `tools/list` | **200** |
| Kontroll-Widerruf | `DELETE /api/v1/api-keys/<probe>/` | **204** |
| nach Widerruf, Messung 1 | `POST /mcp/` `tools/list` | **401** |
| nach Widerruf, Messung 2 (≥60 s Abstand) | `POST /mcp/` `tools/list` | **401** |

**Abweichung (kein Improvisieren):** Für `ff77bbd0…` (und die übrigen
Kandidaten) ist **kein Plaintext mehr verfügbar** — die Datei
`AUDIT_EVIDENCE/stack-seeds.md` wurde laut Incident §3.3 redigiert
(`reqlo_…REDACTED-ejYR`), und die DB speichert konstruktiv nur Hashes. Ein
Live-401-Aufruf mit dem Original-Secret ist daher **nicht ausführbar**. Ersatz-
und Beweisweg: DB-`SELECT` (`revoked_at` NOT NULL), `list_api_keys`
(`revoked=true`) und der Kontroll-Probe-Nachweis (200 → 204 → 401 ×2), der den
Widerrufs-Pfad als solchen end-to-end belegt.

### BLOCKER — Kandidat nicht widerrufbar

| id (maskiert) | name | scope | expires_at | DELETE | Grund |
|---|---|---|---|---|---|
| `34e0aeae…` | wp1a-tenantb | admin | NULL | **404** | Owner ist `e2e-user-1789804477653`, **nicht** `admin`. Der DELETE-Endpoint ist selbst-scoped (`authentication.py:718-736`); ein Admin-JWT erhält 404. Es liegt **kein** Credential des e2e-Users vor. Nicht improvisiert (kein direkter DB-Write, kein User-Delete). |

### Noch offene / nicht widerrufene Keys (nicht-Kandidaten)

Aktiv geblieben (alle `expires_at=NULL`, kein Workspace-Fence):

- `05968310…` — audit-live-probe, scope `readwrite`, Owner `admin`.
  **Restrisiko:** Zwilling von `ff77bbd0…`, gleiche Defektklasse; `readwrite`
  ist **nicht** in `{write, admin}` und war nicht explizit benannt → bewusst
  nicht automatisch widerrufen.
- `51b93187…` — bogus_key, scope `readwrite`, Owner `admin` (Negativ-Fixture).
- `7650dcf7…` — empty_scope_key, scope `''`, Owner `admin` (Negativ-Fixture).
- `252789b4…` — read_key, scope `read_only`, Owner `admin` (e2e-Fixture).
- `8293c9a1…` — author_key, scope `author`, Owner `admin` (e2e-Fixture).
- `34e0aeae…` — wp1a-tenantb, scope `admin`, Owner `e2e-user…` (**BLOCKER**, s. o.).

### Restrisiko / Empfehlungen

1. **`05968310…`** ist ein weiterer live `readwrite`-Probe-Key ohne Ablauf;
   explizite Entscheidung zum Widerruf oder zur Fence/Expiry-Nachrüstung nötig.
2. **`34e0aeae…`** bleibt als aktiver `admin`-Key ohne Ablauf bestehen
   (fremder Owner); Widerruf nur mit Credential des Owners oder durch einen
   bewusst autorisierten Admin-Pfad möglich.
3. Alle verbleibenden 6 aktiven Keys haben **kein `expires_at`** und **keinen
   Workspace-Fence** (AUD-2026-09-240) — die Policy-Durchsetzung auf dem
   REST-/MCP-Automatisierungspfad (SEC-03) ist weiterhin offen.
4. Der Live-401-Beleg mit dem Original-Secret `ff77bbd0…` ist wegen der
   Redaktion dauerhaft nicht reproduzierbar; die Widerrufs-Beweiskette stützt
   sich auf DB + Application-API + Kontroll-Probe.

### Bestätigungen

- Es sind **keine** Key-Werte/Token/Secrets in diesem Dokument oder im Output
  enthalten — ausschließlich maskierte IDs.
- **Kein Push**, kein `--force`, kein `--no-verify`, kein User-Delete.
- Widerruf ausschließlich über den Produktionspfad
  `DELETE /api/v1/api-keys/<id>/`.

---

## Phase 2-Rest — SECTRACK-01 Rest-Keys

- **Datum:** 2026-10-01
- **Branch:** `chore/audit-review-2026-09`
- **Stack:** Compose-Projekt `ai-native-reqflow-poc`, Backend `http://localhost:8001`
- **Auftrag:** Rest-Keys aus der Phase-2-Vorlage behandeln — `05968310…`
  (Scope-Erweiterung genehmigt) und `34e0aeae…` (Best-Effort über legitimes
  Credential; sonst Residuum).
- **Revision:** `revoke` ist irreversibel; kein User gelöscht; **keine** direkte
  SQL-Schreibung; kein Push.

### Bestandsaufnahme (vor den Aktionen)

`python manage.py inventory_api_keys --format json` bestätigte beide Keys als
**aktiv**:

| id (maskiert) | name | scope | expires_at | owner | tenant | status |
|---|---|---|---|---|---|---|
| `05968310…` | audit-live-probe | readwrite | NULL | `admin` | `demo` | active |
| `34e0aeae…` | wp1a-tenantb | admin | NULL | `e2e-user-1789804477653` | `t-5e4905` | active |

Beide `never_used`, kein Workspace-Fence.

### `05968310…` — widerrufen (HTTP 204)

| Aspekt | Ergebnis |
|---|---|
| Endpoint | `DELETE /api/v1/api-keys/05968310-…/` (vollständige UUID; hier maskiert) |
| Auth | Bearer-JWT aus `POST /api/v1/auth/login/` (`admin`); kein API-Key, daher nicht im Widerrufs-Set |
| **DELETE-Status** | **204 No Content** |
| **DB-Nachweis** | `revoked_at = 2026-10-01 19:58:19.401045+00:00` (**NOT NULL**, vorher NULL) |
| **`list_api_keys`** | `revoked=true`, `name=audit-live-probe`, `scope=readwrite` |
| **Inventar danach** | `status=revoked`, `not_revoked=false` |

**401-Nachweis (Kontroll-Probe, weil der Original-Plaintext redigiert ist):**
frische Probe über den Produktionspfad erzeugt und widerrufen — beweist den
Revoke-Pfad end-to-end:

| Messung | Endpoint | Status |
|---|---|---|
| Probe angelegt | `POST /api/v1/api-keys/` (scope `write`) | **201** |
| Kontrolle vor Widerruf | `POST /mcp/` `tools/list` | **200** |
| Kontroll-Widerruf | `DELETE /api/v1/api-keys/<probe>/` | **204** |
| nach Widerruf, Messung 1 | `POST /mcp/` `tools/list` | **401** |
| nach Widerruf, Messung 2 (≥3 s Abstand) | `POST /mcp/` `tools/list` | **401** |
| DB-Gegenprobe Probe | `revoked_at` NOT NULL | **true** |

Die Kontroll-Probe (`16d4ad44…`) wurde im selben Lauf widerrufen; ihr Plaintext
wurde nur einmalig gehalten und **nie** protokolliert.

### `34e0aeae…` — Legitimitätsprüfung (Ergebnis: **kein legitimer App-Pfad**)

Geprüft wurden alle in Frage kommenden App-Oberflächen:

| Pfad | Beleg | Ergebnis |
|---|---|---|
| REST `DELETE /api/v1/api-keys/<id>/` | `rest_api/api_key_views.py:371-410`, `auth_tenancy/services/authentication.py:718-736` | **404** — selbst-scoped (`api_key.user_id != user_id → AuthenticationFailed`); live erneut gemessen mit `admin`-JWT |
| Anderer Aufrufer von `revoke_api_key` | `rg revoke_api_key backend/**/*.py` → **genau ein** Caller (`api_key_views.py:403`), immer mit Caller-`user_id` | keiner |
| MCP | `mcp_server/tool_registry.py:543-545` — „MCP exposes no key-management tool“; kein `api_key.*`-Tool | keiner |
| Management-Commands | `inventory_api_keys` (explizit read-only, `inventory_api_keys.py:11-13`); `cleanup_revoked_api_keys` löscht **nur bereits widerrufene** Rows (`cleanup_revoked_api_keys.py:57-70`); kein Revoke-Command in `backend/**/management/commands/` | keiner |
| Tenant-Admin-JWT | kein Cross-User-Key-Endpoint; `user.revoke_tenant_admin`/`permissions.revoke` betreffen Rollen/Regeln, nicht API-Keys | keiner |

**Beobachtung (bewusst NICHT genutzt):** `auth_tenancy/admin.py:23-35` registriert
`ApiKey` im Django-Admin mit `ApiKey.unscoped.all()` (Kommentar: „for maintenance
operations“), `revoked_at` ist dort **editierbar**; `admin` ist
`is_staff=true, is_superuser=true`. Dieser Superuser-Wartungspfad ist **kein**
API-/Command-Pfad: er umgeht den selbst-scoped Domain-Service und die
Tenant-/Ownership-Fence und ist semantisch ein manueller Spalten-Edit. Er wurde
daher **nicht** ausgeführt — eine Nutzung bräuchte eine **explizite, gesonderte
Freigabe** für einen privilegierten Cross-Tenant-Write.

**Fazit:** `34e0aeae…` ist über die legitime Oberfläche nicht widerrufbar und
bleibt als **Residuum** bestehen (kein SQL-Write, kein User-Delete).

### Verbleibende Residuen + Risikoeinordnung

Aktive Keys nach diesem Lauf: **5** (Inventar 204 Rows, 199 revoked).

**Residuum `34e0aeae…` (wp1a-tenantb, scope `admin`, owner `e2e-user…`, tenant `t-5e4905`):**

| Dimension | Bewertung |
|---|---|
| Plaintext verfügbar? | **Nein** — `at_api_key` speichert konstruktiv nur `key_hash`; kein Plaintext im Repo/Arbeitsbaum |
| Jemals benutzt? | **Nein** — `last_used_at = NULL`, `usage_state=never_used` |
| Erreichbarkeit | Nur lokal (Compose-Host-Ports `8001`/`5173`); **nicht** internet-exponiert; LLM-Provider `mock` |
| Blast-Radius bei Leak | `scope=admin`, `workspace_ids=[]` ⇒ innerhalb von Tenant `t-5e4905` (isoliertes E2E-Tenant) volle Admin-Aktionen bis `expires_at=NULL` |
| Greift das Bedrohungsmodell? | **Nur bedingt:** ohne Plaintext kein direkter Missbrauch; kein Live-Expositionsfenster. Ein Leak-Szenario setzt Zugriff auf das E2E-Tenant-Credential voraus, das hier nirgends persistiert ist |
| Was greift **nicht**? | Kein Remote-Angreifer-Pfad (localhost-only), kein Credential in Git/Arbeitsbaum, kein Rotationszwang durch laufende Clients |
| Restrisiko | **Niedrig** in dieser Umgebung; **mittel**, falls der Stack je exponiert oder das E2E-Tenant in eine Produktivinstanz überführt wird |
| Empfehlung | Explizite Operator-Entscheidung: (a) Widerruf via Django-Admin/Superuser mit separater Freigabe, oder (b) `expires_at`/Workspace-Fence nachrüsten, oder (c) E2E-Tenant `t-5e4905` als Ganzes bereinigen. Bis dahin als **akzeptiertes Restrisiko** (AUD-2026-09-240) führen |

**Weitere aktive Legacy-Keys (nicht-Kandidaten, unverändert):** `51b93187…`
(bogus_key), `7650dcf7…` (empty_scope_key), `252789b4…` (read_key),
`8293c9a1…` (author_key) — alle `expires_at=NULL`, kein Fence.
Alle 5 verbleibenden aktiven Keys haben weiterhin **kein `expires_at`** und
**keinen Workspace-Fence** (AUD-2026-09-240) — die Policy-Durchsetzung auf dem
REST-/MCP-Automatisierungspfad (SEC-03) bleibt offen.

### Bestätigungen (Phase 2-Rest)

- Es sind **keine** Key-Werte/Token/Secrets in diesem Abschnitt enthalten —
  ausschließlich maskierte IDs; die Kontroll-Probe wurde nur einmalig gehalten.
- **Kein Push**, kein `--force`, kein `--no-verify`, kein User-Delete, **keine**
  direkte SQL-Schreibung.
- Widerruf ausschließlich über den Produktionspfad
  `DELETE /api/v1/api-keys/<id>/` bzw. read-only-Verifikation.
