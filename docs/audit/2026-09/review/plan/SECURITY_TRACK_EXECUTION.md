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

---

## Phase 3 — SECTRACK-02 History-Rewrite

- **Datum:** 2026-10-01
- **Branch:** `chore/audit-review-2026-09`
- **Werkzeug:** `git-filter-repo` **2.47.0** (`python -m git_filter_repo`)
- **Aufruf:** `--replace-text <externe Datei> --force` (Fresh-Clone-Safety — **kein** Push-`--force`)
- **Ziel:** Entfernen des `reqlo_*`-Keys aus Commit `3dcc80d8` aus **allen lokalen Refs** — rein lokal; der Commit war nie auf einem Remote-Ref.
- **Revision:** Rewrite ist irreversibel; Bundle-Backup vorhanden und unangetastet; **kein Push**, kein `push --force`, kein `--no-verify`.

### Methode

Ersatzdatei **außerhalb** des Repos (nach dem Lauf gelöscht), eine Zeile:

```
regex:reqlo_[A-Za-z0-9]{40}\b==>reqlo_REDACTED
```

Boundary-anchored: ersetzt **nur** echte 40-Zeichen-Keys. Das 44-Zeichen-README-Beispiel (`reqlo_` + 44 Alnum) und `<40`-Fixtures matchen **nicht**. Es wurde **kein** Klartext-Secret gehalten, ausgegeben oder in eine getrackte Datei geschrieben.

Aufruf über **alle** Refs (bewusst **kein** `--refs <branch>`):

```
python -m git_filter_repo --replace-text <externer-pfad> --force
```

### filter-repo-Ausführung

- **Exit-Code `0`** (erfolgreich); „New history written in 12,03 seconds“, komplett nach 16,27 s.
- „**Parsed 2843 commits**“; „**Rewrote the stash.**“
- Der `origin`-Remote wurde entfernt — **dokumentiertes** Verhalten (filter-repo `--partial`-Hilfe: nur `--partial`/`--refs` deaktivieren „rewriting refs/remotes/origin/* to refs/heads/*“ und „removing of the 'origin' remote“).
- Da **kein** `--refs` gesetzt war, griff `_migrate_origin_to_heads()` (`git_filter_repo.py:4389-4412`): jedes `refs/remotes/origin/*` wird nach `refs/heads/*` migriert, sofern dort kein gleichnamiger Branch liegt; `origin/HEAD` und der Remote werden gelöscht. Folge: **+45** lokale Branches (kein Datenverlust, keine Warnungen).
- **Stashes:** `refs/stash` wurde rewritet (`157106cd…` → `d713e2d6…`). Im Non-`--partial`-Modus führt filter-repo jedoch `git reflog expire --expire=now --all` aus (`git_filter_repo.py:3530`), sodass die **Stash-Records** (Reflog) entfallen. Die Stash-**Spitze** bleibt erhalten; `git stash clear` wurde **nicht** ausgeführt.

### Verifikation (Kommando → Ergebnis)

| # | Kommando | Ergebnis |
|---|---|---|
| V1 | `git for-each-ref --contains 3dcc80d8` | **leer (0)** — `error: malformed object name 3dcc80d8` (Objekt entfernt) |
| V2 | `git cat-file -e 3dcc80d8` | **Exit 128** (Objekt fehlt) |
| V3 | `git log --all -G 'reqlo_[A-Za-z0-9]{40}\b'` | **0 Treffer** |
| V4 | Baum-Ebene: `git grep -lE 'reqlo_[A-Za-z0-9]{40}\b'` über alle **2728** `git rev-list --all`-Commits | **0 Treffer** |
| V5 | `git count-objects -v` | `count=0`, `garbage=0`, `in-pack=33189`, `packs=1`, `size-pack=198938` |
| V6 | `git fsck --full` | keine Ausgabe → **sauber** (0 dangling/error/missing) |
| V7 | `git status --porcelain` | nur 2 erwartete untracked (`?? .kimi-code/`, `?? docs/audit/2026-09/AUDIT_EVIDENCE/stack-seeds.md`) |
| V8 | Regex-Gegenprobe auf `HEAD` | 40-Zeichen-Muster = **0**, 44-Zeichen-Muster = **1** (README-Beispiel unangetastet) |

Der HEAD-/Arbeitsbaum-Inhalt ist abgesehen von der Regex-Ersetzung unverändert (`--replace-text` ist die einzige Transformation).

### Ref-Struktur vorher/nachher

| Namespace | vorher | nachher | Delta |
|---|---|---|---|
| `refs/heads` (Branches) | 56 | **101** | **+45** (alle vormals `origin`-Tracking-Refs) |
| `refs/tags` | 39 | 39 | 0 (Namens-Set identisch) |
| `refs/remotes` (Tracking) | 99 (origin 90 + codeberg 9) | **9** (nur codeberg) | **−90** origin |
| Stash-Records (Reflog) | 45 | **0** | **−45** |
| `refs/stash` (Spitze) | 1 | 1 | 0 (`157106cd…` → `d713e2d6…`) |
| **Total `for-each-ref`** | **195** | **150** | **−45** |

Bundle-Bestand: 200 Refs (195 obige + `HEAD` + 4× `worktrees/*/HEAD`).

**Exakt benannte Abweichungen:**

1. **+45 Branches** — migrierte `origin`-Tracking-Refs ohne lokales Pendant (kein Branch entfernt):
   ```
   chore/agent-meta-config-tuning
   chore/archive-implemented-specs-plans
   chore/release-checklist-github-step
   chore/upgrade-agent-meta-v1.1.0
   dependabot/github_actions/actions/configure-pages-6
   dependabot/github_actions/actions/deploy-pages-5
   dependabot/github_actions/actions/upload-pages-artifact-5
   dependabot/npm_and_yarn/frontend/jsdom-29.1.1
   dependabot/npm_and_yarn/frontend/jsdom-30.1.0
   dependabot/pip/backend/honcho-ai-2.5.0
   docs/attribute-definition-spec
   docs/bugfix-session-plan
   docs/compose-optimization-plan-792
   docs/p0-soforthaertung-spec
   docs/requirement-bundle-export-design
   feat/ai-memory-and-search
   feat/goals-ui-redesign-238-219
   feat/hermes-plugin-requirements-crud
   feat/mcp-plugin-distribution
   feat/menschen-im-system
   feat/multi-artifact-interview
   feat/requirement-bundle-export-ui-panel
   feat/se-l2-diagramservice
   feat/se-l2-icdmanagement
   feat/se-l2-semetrics
   feat/ui-konzept-phase6-diagrams
   feat/ui-konzept-redesign
   feat/ui-konzept-vollrollout-phase3
   feat/ui-konzept-vollrollout-phase4
   fix/bugfix-batch-2026-09-02
   fix/bugfix-create-endpoints-ui-layout
   fix/ci-red-2026-08-25
   fix/deployment-example-drift
   fix/docker-backend-setuptools-cve
   fix/llm-provider-save-and-mcp-schemas
   fix/low-severity-batch
   fix/p0-soforthaertung
   fix/quick-batch-3
   fix/systemaudit-p1-fachlichkeit
   fix/ui-consistency-p1-header-dashboard-tracelink
   refactor/diagram-node-graph
   refactor/system-admin-env-vars
   se-run
   worktree-agent-a780fb1bb701f6500
   worktree-agent-aba26fc3bfdbd73dc
   ```
2. **−90 `origin`-Refs** — 45 davon wurden zu Branches (Punkt 1), **44** kollidierten mit bestehenden lokalen Branches und wurden verworfen (Werte identisch → kein Verlust, keine Warnung), **1× `origin/HEAD`** gelöscht.
3. **−45 Stash-Records** — Folge des Non-`--partial`-Modus; die Stash-Ref bleibt. Reflog-Records sind **nicht** bundle-fähig und damit nicht gesichert. Abweichung zur Auftragsannahme „45 Stash-Entries nachher“.

### Neue Hashes der zentralen Refs

| Ref | pre-rewrite (nur Historik) | post-rewrite |
|---|---|---|
| `HEAD` = `chore/audit-review-2026-09` | `ba06e92dfe2638233d8ab5c1b21e1799a9aeca8f` | **`e9644e1967167f3162a39e15a3779d594216916c`** |
| `main` | `abd61aed7eb8e385de67dc85fde6923328441bac` | **`d330f666ebba942017ccdbdf20b49ccab1925fa6`** |
| `release/v1.8.0-beta.18` | `38da915f148843f1052c1a6d5732279aa69206ca` | **`73d90e1b80edf309983b558a97f618c498db2004`** |
| Tag `v1.8.0-beta.18` | `bf918f15bce34e97e9f88189213c1ecc4179f506` | **`b2420d58b42b89a4a90d86c68ea707812cfaa150`** |

> Der Ref-Snapshot `reqlo-pre-rewrite-refs.txt` führt `chore/audit-review-2026-09` noch mit `5aa55260…` (einen Commit vor dem Rewrite-Stand); verbindlich sind die `ref-map`-Altwerte.

### Remote-Wiederanbindung + Divergenz

Nach dem Rewrite **ohne** Push/Fetch wieder angebunden:

```
git remote add origin   https://github.com/Popoboxxo/ReqogniLoom.git
git remote add codeberg https://codeberg.org/dduchrow/ai-native-reqflow-POC.git
```

- **origin:** 0 Remote-Tracking-Refs. Ein späterer Push wäre **non-fast-forward** (History umgeschrieben) — **bewusst unterlassen**.
- **codeberg:** 9 Tracking-Refs (inkl. `HEAD`); `codeberg/main` = `c4cb7ea801d78b67511ede4fed6177f65e3acb73` vs. lokales `main` = `d330f666ebba942017ccdbdf20b49ccab1925fa6` → divergiert, Push **non-fast-forward** — **bewusst unterlassen**.

### Artefakte / Bestätigungen

- Bundle `…\opencode\reqlo-pre-rewrite.bundle` **unangetastet** (`Length=202431414`, `LastWriteTime=2026-10-01 21:24:32`; `git bundle verify` = „The bundle records a complete history“).
- Ersatzdatei `…\opencode\reqlo-replacements.txt` nach dem Lauf **gelöscht**.
- **Kein Push**, kein `push --force`, kein `--no-verify`. Keine Key-Werte/Secrets in diesem Abschnitt.

---

## Phase 4 — SECTRACK-03 Secret-Scan-Gate

- **Datum:** 2026-10-01
- **Branch:** `chore/audit-review-2026-09`
- **Auftrag:** reproduzierbares Secret-Scan-Gate (rewrite-first, harte 0 Treffer)
  + Nachweis beider Richtungen (Erkennung erzwungen / echter Stand clean).
- **Revision:** rein additive Gate-Artefakte, **kein** Product-Code; **kein Push**,
  kein `--force`, kein `--no-verify`.

### Scanner + Version + Installationsweg

| Aspekt | Wert |
|---|---|
| Scanner | gitleaks (begründete Wahl) |
| Version | **exakt 8.30.1** (gepinnt) |
| Subkommandos (am Binary verifiziert) | `gitleaks git [repo]` (History; `--staged` für den Index) und `gitleaks dir [path]` (Arbeitsbaum). **`detect`/`protect` existieren in 8.30.1 nicht mehr** (`gitleaks --help` geprüft) — die Vorgabe-Subkommandos wurden entsprechend auf `git`/`dir` abgebildet |
| Download Windows | `gitleaks_8.30.1_windows_x64.zip`, sha256 `d29144de…afc4e` |
| Download Linux | `gitleaks_8.30.1_linux_x64.tar.gz`, sha256 `551f6fc8…470eb` |
| Lokaler Install | portables Binary entpackt und auf `PATH` gelegt; **kein** globaler Systemumbau |
| CI | sha256-verifizierter Download des gepinnten Release-Archivs |

### Ort (CI + lokal)

| Ort | Datei | Aufruf |
|---|---|---|
| lokal — pre-commit | `.pre-commit-config.yaml` | `gitleaks git --staged --redact --config .gitleaks.toml --enable-rule reqlo-api-key` |
| lokal — manuell | `.gitleaks.toml` | `gitleaks git . …` (History) bzw. `gitleaks dir . …` (Arbeitsbaum) |
| CI — GitHub Actions | `.github/workflows/ci.yml`, Job `secret-scan` | `dir` **und** `git`, je `--exit-code 1`; `fetch-depth: 0` |
| CI — Woodpecker | `.woodpecker.yml`, Step `secret-scan` | `dir` **und** `git`, je `--exit-code 1` |

### Konfiguration (`.gitleaks.toml`)

`[extend] useDefault = true` + Custom-Regel `id=reqlo-api-key`,
`regex = reqlo_[A-Za-z0-9]{40}\b`, `keywords=["reqlo_"]`. **Keine** Pfad-Allowlist
(History ist clean). Der Boundary-Anker matcht GENAU 40 Alnum nach `reqlo_`:
Live-Incident-Key → Treffer; 44-Zeichen-README-Beispiel und `<40`-Test-Fixtures
→ kein Treffer.

**Begründete Abweichung (Default-Regeln nicht im blockierenden Pfad):** Ein Lauf
mit Default-Regeln liefert auf diesem Repo deterministisch **84 Treffer** (79×
`generic-api-key`, 3× `curl-auth-header`, 2× `sourcegraph-access-token`) —
ausschließlich intentionale Test-Fixtures (`VALID_API_KEY = "…"`,
`DB_PASSWORD=…`) und das README-Dokumentationsbeispiel. Ein hartes 0-Gate mit
Defaults bräuchte eine breite Allowlist oder eine große Baseline — beides laut
Auftrag untersagt. Das **blockierende** Gate läuft daher mit
`--enable-rule reqlo-api-key` (deterministisch, hard 0); die Default-Regeln
bleiben in der Config für optionale Voll-Scans erhalten. Die 84
Heuristik-Treffer sind als Triage-Follow-up notiert (ohne Bezug zum
Incident-Muster).

### Positiv-Nachweis (Erkennung erzwungen)

Temporär (nicht committet) eine Datei mit synthetischem `reqlo_` + 40 Alnum
erzeugt (`docs/audit/.scan-positive-probe.tmp`; Wert bewusst **nicht** abgedruckt):

| Kanal | Kommando | Ergebnis |
|---|---|---|
| gitleaks `dir` | `gitleaks dir <probe> --config .gitleaks.toml --enable-rule reqlo-api-key --redact --exit-code 1` | **1 Finding** (`reqlo-api-key`), **Exit 1** |
| gitleaks `git --staged` | `gitleaks git . --staged --redact --config .gitleaks.toml --enable-rule reqlo-api-key --exit-code 1` | **1 Finding**, **Exit 1** |
| pre-commit | Probe gestaged, dann `pre-commit run gitleaks` | **Failed (Exit 1)**, 1 Leak (redigiert) |

Die Probe wurde anschließend **entfernt und nie committet** (`git reset` +
Delete; `git status` ohne Probe). Boundary-Kontrollprobe: 44- und
39-Zeichen-Varianten → **0 Findings** (nur exakt 40 matcht).

**Hook-Detail (verifiziert):** Der Upstream-Entry `gitleaks-system` nutzt
`--pre-commit` (Diff Arbeitsbaum↔Index). Nach dem pre-commit-Stash ist dieser
Diff leer, wodurch gestagte Secrets übersehen werden — der Hook meldete mit
diesem Entry fälschlich „Passed“. Daher ein expliziter lokaler Hook mit
`--staged`, der die Probe zuverlässig blockt.

### Negativ-Nachweis (echter Stand clean)

| # | Prüfung | Ergebnis |
|---|---|---|
| N1 | `gitleaks git . --enable-rule reqlo-api-key` über **2375 Commits** | **0 Findings**, Exit 0 |
| N2 | `gitleaks dir <clean HEAD-Checkout> --enable-rule reqlo-api-key` | **0 Findings**, Exit 0 |
| N3 | `git log --all -G 'reqlo_[A-Za-z0-9]{40}\b'` | **0** |
| N4 | README-44-Zeichen-Beispiel unter der Custom-Regel | **nicht gemeldet** (N1/N2 = 0) |

**Lokaler Hinweis (nicht Repo-Scope):** Ein roher `gitleaks dir .` über das
Entwickler-Arbeitsverzeichnis findet zusätzlich **2** echte `reqlo_<40>`-Keys in
**git-ignorierten** Dateien (`.claude/settings.local.json`,
`.meta-config/secrets.local.yaml`; siehe `.gitignore`). Sie sind nicht getrackt
und nicht in der History; das Repo-Gate (N1/N2) bleibt 0. Empfehlung: diese
lokalen Dateien bei Gelegenheit rotieren.

### Bestätigungen (Phase 4)

- **Kein Push**, kein `push --force`, kein `--no-verify`.
- Keine Key-Werte/Secrets in diesem Abschnitt oder in den committeten Dateien;
  die Positiv-Probe war synthetisch und wurde gelöscht.
- Keine Änderung an Product-Code; nur Gate-Artefakte (`.gitleaks.toml`,
  `.pre-commit-config.yaml`, CI-Workflows).

---

## Phase 5 — Hausmeister lokale Keys

- **Datum:** 2026-10-01
- **Branch:** `chore/audit-review-2026-09`
- **Stack:** Compose-Projekt `ai-native-reqflow-poc`, Backend `http://localhost:8001`
- **Auftrag:** Widerruf der in Phase 4 gemeldeten lokalen `reqlo_`-Keys aus den
  gitignorierten Dateien `.claude/settings.local.json` und
  `.meta-config/secrets.local.yaml` über den legitimen Produktionspfad, 401-Nachweis,
  Bereinigung der Dateien, Dokumentation.
- **Revision:** kein Push, kein `--force`, kein `--no-verify`; **keine** direkte
  SQL-Schreibung; kein User-Delete; nur die Doku-Änderung wird committet. Die beiden
  genannten Dateien bleiben gitignoriert und werden **nicht** committet.

### Bestandsaufnahme (read-only, Regex `reqlo_[A-Za-z0-9]{40}`)

| Datei | Vorkommen | Wert-Identität |
|---|---|---|
| `.claude/settings.local.json` | 1 | `reqlo_3z…` |
| `.meta-config/secrets.local.yaml` | 1 | `reqlo_3z…` (identisch) |

**Abweichung zur Auftragsannahme „zwei Keys":** Es handelt sich um **genau einen
distinkten Key** (`reqlo_3z…`, sha256-Kurzform `61af6f43810e`), der in **beiden**
Dateien mit demselben Wert steht — nicht um zwei verschiedene Credentials. (Deckt
sich mit Phase 4: zwei gitleaks-*Findings* = zwei Datei-Vorkommen, ein Wert.) In der
Ziel-Instanz finden sich **keine** weiteren `reqlo_`-Tokens anderer Länge in den
beiden Dateien.

### Auflösung der Key-ID (read-only)

Die Zuordnung Plaintext → `at_api_key.id` ist über die REST-Oberfläche **nicht**
möglich (der Key authentifiziert nicht, s. u.). Daher read-only über den
App-eigenen Hash des Authentifizierungspfads
(`auth_tenancy.services.authentication.api_key_hash_candidates`) gegen **alle** Rows
von `at_api_key` (Ausführung im Backend-Container, `manage.py shell`):

| Prüfung | Ergebnis |
|---|---|
| `at_api_key` Rows gesamt | **204** |
| davon Legacy-Format `sha256:` (unpeppered) | **204** (⇒ Hash-Matching ist autoritativ) |
| davon peppered `sha256p1:` | 0 |
| aktive (nicht widerrufene) Keys | 5 (`admin` ×4, `e2e-user-…` ×1) |
| **Hash-Treffer für `reqlo_3z…`** | **0** |

**Fazit:** Der Key ist in der lokalen Datenbank **nicht vorhanden** (weder aktiv noch
bereits widerrufen). Er wurde in einer früheren Rotation/`cleanup_revoked_api_keys`
entfernt bzw. stammt aus einer anderen Instanz (Config-Ziel `http://172.20.5.120:5173`).

### DELETE-Status

| Aspekt | Ergebnis |
|---|---|
| `DELETE /api/v1/api-keys/<id>/` | **n/a — nicht ausführbar** |
| Grund | Kein auflösbarer Key-Datensatz → keine `<id>`. Der selbst-scoped Produktionspfad verlangt zuerst eine erfolgreiche Authentifizierung mit dem Key (401 ⇒ nicht erreichbar). |
| Bewusst **nicht** getan | Kein blinder DELETE auf die 5 aktiven Fremd-Keys; kein direkter SQL-Write; kein User-Delete. |

### 401-Nachweis (mit Positiv-Kontrolle)

Positiv-Kontrolle über den dokumentierten Login-Pfad
(`POST /api/v1/auth/login/` → Admin-JWT), damit 401 nicht auf einen generell
defekten Endpoint zurückzuführen ist. Der Original-Plaintext des Ziel-Keys ist
vorhanden; es wurde **nichts** protokolliert.

| Messung | Credential | Endpoint | Zeit (UTC) | Status / Code |
|---|---|---|---|---|
| Positiv-Kontrolle | Admin-JWT (nicht im Widerrufs-Set) | `GET /api/v1/auth/me/` | 21:12:57 | **200** (user=`admin`) |
| Positiv-Kontrolle | Admin-JWT | `GET /api/v1/api-keys/` | 21:12:57 | **200** |
| **bereits 401 vor Widerruf — Messung 1** | Ziel-Key | `GET /api/v1/auth/me/` | 21:12:57 | **401** `invalid_api_key` |
| Messung 1 (Fortsetzung) | Ziel-Key | `GET /api/v1/api-keys/` | 21:12:57 | **401** `invalid_api_key` |
| **bereits 401 vor Widerruf — Messung 2** | Ziel-Key | `GET /api/v1/auth/me/` | 21:13:05 | **401** `invalid_api_key` |
| Messung 2 (Fortsetzung) | Ziel-Key | `POST /mcp/` `tools/list` | 21:13:05 | **401** (`-32000`) |

Zusätzlich wurde das in der Config hinterlegte Ziel `172.20.5.120` geprüft:
`:8001` und `:5173` erreichbar, beide mit dem Key → **401** `invalid_api_key`.

### Bereinigung der Dateien

Beide Vorkommen wurden durch den Platzhalter `reqlo_REVOKED_PLACEHOLDER` ersetzt
(Werte wurden **nicht** ausgegeben/protokolliert).

| Datei | Platzhalter gesetzt | Struktur-Validierung | `rg "reqlo_[A-Za-z0-9]{40}"` |
|---|---|---|---|
| `.claude/settings.local.json` | ja (`Bearer reqlo_REVOKED_PLACEHOLDER`) | JSON valid | **0 Treffer** |
| `.meta-config/secrets.local.yaml` | ja (`MCP_REQOGNILOOM_API_KEY: reqlo_REVOKED_PLACEHOLDER`) | YAML valid | **0 Treffer** |

### Risiko / Residuum

| Dimension | Bewertung |
|---|---|
| Credential lebendig? | **Nein** — 401 auf allen erreichbaren Backends; kein DB-Datensatz lokal |
| Widerruf möglich? | **Nein** — kein auflösbarer Key; nichts zu widerrufen („bereits 401 vor Widerruf") |
| Vorkommen in Git? | **Nein** — beide Dateien gitignoriert, nicht getrackt, nicht in der History (Phase 3/4) |
| Residuum | Der ehemalige Plaintext war in zwei gitignorierten Arbeitsdateien abgelegt (jetzt Platzhalter). Falls je eine **andere** Instanz denselben Wert als aktiven Key führt, ist er dort weiterhin gültig und muss dort rotiert werden — in dieser Umgebung nicht erreichbar/nachweisbar. |
| Restrisiko | **Niedrig** für diese Umgebung (Credential tot, Dateien clean) |

### Bestätigungen (Phase 5)

- Es sind **keine** Key-Werte/Token/Secrets in diesem Abschnitt enthalten — nur
  maskierte Kennung (`reqlo_3z…`) und die Platzhalter; JWT/Passwort nie ausgegeben.
- **Kein Push**, kein `--force`, kein `--no-verify`, kein User-Delete, **keine**
  direkte SQL-Schreibung; kein blind durchgeführter DELETE.
- Widerruf/Verifikation ausschließlich über den Produktionspfad bzw. read-only
  Verifikation; nur die vorliegende Doku-Datei wird committet.