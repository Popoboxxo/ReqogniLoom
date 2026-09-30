---
type: EVIDENCE
scope: secret-incident
status: remediiert-history-offen
date: 2026-09-30
author_agent: security-auditor
---

# Secret-Incident 2026-09-30 — `AUD-2026-09-220`

**Klasse:** Hardcoded Credential (CWE-798) im Git-Arbeitsbaum + Git-Historie
**Auslöser:** WP-6a-Security-Audit, Finding `AUD-2026-09-220`
**Ursache:** Der Audit-Prozess selbst (WP-1d) hat ein live gültiges API-Key in eine JSON-Evidenzdatei geschrieben.
**Status:** Credential **widerrufen** (belegt) · Arbeitsbaum **redigiert** (belegt) · Historie **offen** (Entscheidungsvorlage §5)

> **Grundsatz dieser Datei:** Es werden ausschließlich Pfade, Zeilennummern, Mustertypen und
> Key-IDs dokumentiert. **Keine Klartext-Credentials.** Wo ein Wert zur Identifizierung nötig ist,
> stehen nur die letzten 4 Zeichen.

---

## 1. Sofort-Remediation: Key widerrufen

### 1.1 Betroffenes Objekt (vor der Aktion, per API + DB verifiziert)

| Feld | Wert |
|---|---|
| `ApiKey.id` | `7eb7adab-2abd-42e3-a848-8f5988405819` |
| `ApiKey.name` | `wp1d-probe-dup` |
| **Eigentümer** | **`admin`** (`pl_user.id = 7298a00b-f228-4269-9b89-31f55794af5d`) |
| `principal_type` | `user` |
| `scope` | **`write`** — laut `auth_tenancy/models.py:153-157` der **legacy ADMIN-Tier** („the legacy, widest (ADMIN) tier") |
| `workspace_ids` | `[]` — **keine** Workspace-Einschränkung ⇒ jeder Workspace, in dem `admin` eine Rolle hat |
| `expires_at` | `NULL` ⇒ **läuft nie ab** |
| `revoked_at` (vorher) | `NULL` |

> **Verschärfung gegenüber dem ursprünglichen Befund:** Der Key gehört nicht zu einem Wegwerf-Probe-User,
> sondern zu **`admin`** — dem Tenant-Admin-Konto des geteilten Stacks. Das war im ersten Bericht
> nicht erkennbar (die Evidenzdatei enthält nur `name`/`scope`, nicht den Eigentümer).

### 1.2 Falsches Feld vermieden

Das Feld heißt **`revoked_at`**, nicht `.revoked`. `is_active` ist ein **read-only `@property`**
(`auth_tenancy/models.py:174-176`) und **kein** DB-Feld — ein `UPDATE … SET is_active = false`
wäre ein Fehler gewesen. Der Produktionspfad setzt korrekt `revoked_at`
(`auth_tenancy/services/authentication.py:734-736`).

### 1.3 Ausgeführte Aktion (genau eine Datenänderung)

Produktionspfad, **kein** direktes SQL:

```
POST   /api/v1/auth/login/                       → JWT (Owner = admin, daher Eigentümerprüfung erfüllt)
DELETE /api/v1/api-keys/7eb7adab-2abd-42e3-a848-8f5988405819/   → HTTP 204
```

`ApiKeyViewSet.destroy` → `AuthenticationService.revoke_api_key(api_key_id=…, user_id=ctx.user_id)`
(`rest_api/api_key_views.py:380-403`, `auth_tenancy/services/authentication.py:718-736`).
Die Eigentümerprüfung (`api_key.user_id != user_id → AuthenticationFailed`) ist damit **passiert**,
weil `admin` der Eigentümer ist — der Key wurde also über genau den Pfad widerrufen, der auch
in Produktion greift.

### 1.4 Belegkette (3 unabhängige Nachweise)

| # | Nachweis | Ergebnis |
|---|---|---|
| **a1** | `POST /mcp/` `tools/list` **mit dem Key, VOR** dem Revoke | **HTTP 200**, `tools=219` ⇒ **live gültig** |
| **a2** | `POST /mcp/` `tools/list` **mit demselben Key, NACH** dem Revoke | **HTTP 401** ⇒ abgewiesen |
| **b** | `SELECT id, name, principal_type, scope, revoked_at, expires_at FROM at_api_key WHERE id = '7eb7adab-…'` | `revoked_at = 2026-09-30 19:07:05.581479+00` (vorher `NULL`) |

**Ergebnis: widerrufen. Nicht blockiert.**

Kontrollprobe zur Bestätigung der Nachhaltigkeit: Key → **HTTP 401** (unverändert, 3 Messungen über den
Zeitraum der Remediation).

### 1.5 ⚠️ ESKALATION — zweiter live Key gefunden, NICHT widerrufen (Constraint)

Der Sweep (§2) hat in `docs/audit/2026-09/AUDIT_EVIDENCE/stack-seeds.md` einen **weiteren live
gültigen** Key derselben Klasse gefunden:

| Feld | Wert |
|---|---|
| `ApiKey.id` | `ff77bbd0-e99c-4d78-a0cf-314a2011ce6b` |
| `ApiKey.name` | `audit-live-probe` |
| Eigentümer | **`admin`** |
| `scope` | `readwrite` |
| `expires_at` | `NULL` |
| `revoked_at` | `NULL` ⇒ **live** |
| Live-Prüfung | **HTTP 200** auf `tools/list` |
| Getrackt? | **nein** (Datei untracked ⇒ **nicht** in der Git-Historie) |
| Redigiert? | **ja** (§3.3) |

**Ich habe ihn NICHT widerrufen**, weil der Auftrag die DB-Änderung ausdrücklich auf **genau einen**
Key begrenzt. **Das ist eine bewusste Entscheidung gegen die vollständige Behebung und muss
unverzüglich nachgeholt werden.**

**Einzeiler für den Orchestrator (ausführen, nicht delegieren):**

```powershell
# 1) Admin-JWT holen
$l = Invoke-WebRequest -Uri "http://localhost:8001/api/v1/auth/login/" -Method Post `
     -ContentType "application/json" -Body '{"username":"admin","password":"<PW>"}' -UseBasicParsing
$t = ($l.Content | ConvertFrom-Json).token
# 2) Key widerrufen
Invoke-WebRequest -Uri "http://localhost:8001/api/v1/api-keys/ff77bbd0-e99c-4d78-a0cf-314a2011ce6b/" `
  -Method Delete -Headers @{Authorization="Bearer $t"} -UseBasicParsing   # -> 204
# 3) Beleg
Invoke-WebRequest -Uri "http://localhost:8001/mcp/" -Method Post `
  -Headers @{ "X-API-Key" = "<der Key aus stack-seeds.md>" } `
  -ContentType "application/json" -Body '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' `
  -UseBasicParsing   # -> 401
```

### 1.6 Zusatzbefund: 9 weitere aktive `admin`-Keys (Kontext, **keine** Aktion)

```
bffd186c-…| MCP-UI-Campaign-REQ129-… | write    | ohne_expiry | workspace_ids=[]
05968310-…| audit-live-probe          | readwrite| ohne_expiry | workspace_ids=[]
ff77bbd0-…| audit-live-probe          | readwrite| ohne_expiry | workspace_ids=[]   <-- live, siehe 1.5
05ffb7e7-…| admin_key                 | admin    | ohne_expiry | workspace_ids=[]
252789b4-…| read_key                  | read_only| ohne_expiry | workspace_ids=[]
8293c9a1-…| author_key                | author   | ohne_expiry | workspace_ids=[]
51b93187-…| bogus_key                 | readwrite| ohne_expiry | workspace_ids=[]
7650dcf7-…| empty_scope_key           | (leer)   | ohne_expiry | workspace_ids=[]
1e656a1a-…| legacy_write_key          | write    | ohne_expiry | workspace_ids=[]
```

`admin` hat **9 aktive Keys**, **alle** ohne `expires_at` und **alle** ohne Workspace-Fence. Das ist
derselbe Fehlerklassen-Defekt wie der geleakte Key (nur ohne den Historie-Faktor). Siehe
`AUD-2026-09-239` (Prozessursache) und die Empfehlung in §7.

---

## 2. Repo-weiter Sweep — vollständige Trefferliste

**Suchumfang (belegt):**

| Dimension | Wert |
|---|---|
| Wurzel | `.` (gesamtes Arbeitsverzeichnis) |
| Ausgeschlossen | `.git/`, `.kimi-code/` (auftragsgemäß nie angefasst), `**/node_modules/**`, `**/package-lock.json`, `*.lock` |
| Enthalten | `docs/audit/**`, `docs/se/**`, `docs/archive/**`, `backend/**`, `frontend/**`, `e2e/**`, `testing/**`, `deploy/**`, `scripts/**`, `.github/**`, `.claude/**`, `.agents/**`, `.opencode/**`, `.gemini/**`, `README.md`, `.env`, `.env.example`, `VERSION`, `.woodpecker.yml` |
| Muster | 8 Regex-Gruppen (siehe unten) |
| Werkzeug | `rg` (ripgrep) |
| Historie | zusätzlich `git log --all -G<reqlo_…>` und `-G<JWT>` über **alle** Refs |

```
M1  reqlo_[A-Za-z0-9]{15,}                    M5  ghp_[A-Za-z0-9]{30,} | github_pat_[A-Za-z0-9_]{20,}
M2  eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{5,}    M6  -----BEGIN [A-Z ]*PRIVATE KEY-----
M3  sk-(ant|proj)-[A-Za-z0-9_-]{15,}           M7  AIza[0-9A-Za-z_-]{30,}
M4  AKIA[0-9A-Z]{16}                          M8  xox[baprs]-[A-Za-z0-9-]{10,}
```

### 2.1 Ergebnis-Tabelle

| # | Pfad:Zeile | Typ | Tracked? | In Historie? | Live gültig? | Bewertung |
|---|---|---|---|---|---|---|
| 1 | `docs/audit/2026-09/AUDIT_EVIDENCE/wp1d-auth-pagination-filter-errors-live.json:2246` | `reqlo_` 40 Z., `scope=write`, Owner `admin` | **ja** | **ja — `3dcc80d8`** | **JA (HTTP 200) → jetzt widerrufen (§1)** | 🔴 **AUD-2026-09-220** |
| 2 | `docs/audit/2026-09/AUDIT_EVIDENCE/wp1d-tenant-leak-matrix.json:101` | `reqlo_` 40 Z., `scope=write`, Owner `wp1d_probe_b` | **ja** | **ja — `3dcc80d8`** | nein (HTTP 401, bereits widerrufen) | 🔴 **AUD-2026-09-220** |
| 3 | `docs/audit/2026-09/AUDIT_EVIDENCE/stack-seeds.md:26,126,131` | `reqlo_` 40 Z., `readwrite`, Owner `admin` | **nein** (untracked) | **nein** | **JA (HTTP 200) → ⚠️ Eskalation §1.5** | 🔴 |
| 4 | `docs/audit/2026-09/AUDIT_EVIDENCE/stack-seeds.md:102` | JWT-**Fragment** (2/3 Segmente, 65 Zeichen, kein Signatursegment) | **nein** | **nein** | **nein** — Fragment ist als Credential unbrauchbar; ausgestellt 2026-09-29 23:42, `ACCESS_TOKEN_TTL=1h` ⇒ **abgelaufen** | 🟡 Hygiene |
| 5 | `README.md:1130,1140,1164,1183` | `reqlo_` **44** Zeichen (Produktformat ist 40) | **ja** | **ja — seit `29417feb` (2026-08-03)** | **nein (HTTP 401)** — Formatlänge schließt Gültigkeit aus | 🟢 **Fehlalarm** (Doku-Beispiel `Ab12Cd34Ef56…`) |
| 6 | `backend/auth_tenancy/tests/test_api_key_pepper.py:105` | `reqlo_` 35 Z., `…legacy_key_issued_before_the_pepper` | ja | ja | n/a | 🟢 Test-Fixture |
| 7 | `backend/auth_tenancy/tests/test_api_key_header_precedence_1076.py:194` | `reqlo_` 29 Z. | ja | ja | n/a | 🟢 Test-Fixture |
| 8 | `backend/mcp_server/tests/test_transition_version_conflict_cr08.py:52` | `reqlo_` 24 Z., `…placeholder_testkey_cr08` | ja | ja | n/a | 🟢 Test-Fixture |
| 9 | `backend/mcp_server/tests/test_interview_tool_group_formalize_parity.py:43` | `reqlo_` 23 Z., `…placeholder_testkey1234` | ja | ja | n/a | 🟢 Test-Fixture |
| 10 | `backend/mcp_server/tests/test_interview_tool_group.py:33` | `reqlo_` 23 Z. | ja | ja | n/a | 🟢 Test-Fixture |
| 11 | `backend/mcp_server/tests/test_mcp_workspace_id_header_decorative.py:53` | `reqlo_` 22 Z., `reqlo_test_placeholder_token` | ja | ja | n/a | 🟢 Test-Fixture |
| 12 | `backend/mcp_server/tests/test_tenant_context_activation.py:59,60` | `reqlo_` 23 + 15 Z. | ja | ja | n/a | 🟢 Test-Fixture |
| 13 | `backend/mcp_server/tests/conftest.py:369` | `reqlo_` 15 Z. | ja | ja | n/a | 🟢 Test-Fixture |
| 14 | `backend/mcp_server/tests/test_audit_tool_group.py:97` | `reqlo_` 15 Z. | ja | ja | n/a | 🟢 Test-Fixture |
| 15 | `deploy/verify-backup-command.sh:90,103` | `POSTGRES_PASSWORD=<20 Zeichen Klartext>` | **ja** | **ja — `56d8f511` (2026-09-27)** | n/a (Wegwerf-Container für `pg_dump`-Verifikation) | 🟡 **LOW** — CWE-1392 Hardcoded Credential; **≠** `.env:DB_PASSWORD` (Gleichheit geprüft: `False`) |
| 16 | `deploy/docker-compose.yml:73,1053` | `HONCHO_DB_PASSWORD:-honcho` — Default = **der Rollenname selbst** | **ja** | **ja** (13 Commits) | n/a | 🟡 **LOW** — schwaches Default-Passwort in einem getrackten Compose-File (CWE-1392) |
| 17 | `deploy/docker-compose.override.yml` (5 Secret-Zuweisungen) | alle `${VAR:-…}` | **ja** (getrackt!) | ja | n/a | 🟢 Platzhalter/Variablen |
| 18 | `.github/workflows/{ci,playwright}.yml`, `.woodpecker.yml`, `testing/docker-compose.test.yml`, `deploy/docker-compose.{yml,minimal.yml}` | 52 Secret-Zuweisungen | ja | ja | n/a | 🟢 **52/55** sind `${…}`-Parameter; die 3 Literale sind `ci-test-secret-key`, `test-only-jwt-key` (CI-only, 7–20 Z., keine Produktionswerte) |

**Null-Treffer (belegt, 0 Treffer im gesamten Suchumfang):**
`AKIA[0-9A-Z]{16}` · `sk-ant-*` · `sk-proj-*` · `ghp_*` · `github_pat_*` · `AIza*` · `xox[baprs]-*` ·
**PEM-Private-Keys** · **JWT nach Redaktion** (0 in `docs/audit/`) · `reqlo_[A-Za-z0-9]{30,}` nach Redaktion in `docs/audit/` (0)

### 2.2 Historie-Sweep

```
git log --all -G'reqlo_[A-Za-z0-9]{30,}'
  3dcc80d8  2026-09-30  docs(audit): WP-1d deep audit …          <-- der echte Leak
  29417feb  2026-08-03  docs Update                             <-- nur README-Doku-Beispiel (Treffer #5)

git log --all -G'eyJ[A-Za-z0-9_-]{15,}\.'
  e559175d  2026-07-22  api_key="eyJ<masked>.fake.jwt"           <-- Literal ".fake.jwt", kein Secret
  bad447fd  2026-07-13  -MCP_HA_TOKEN: "eyJ<masked>..."         <-- abgeschnitten
  0154cedc  2026-07-04  +MCP_HA_TOKEN: "eyJ<masked>..."         <-- abgeschnitten
```

⇒ **In 2707 Commits über alle Refs existiert genau EINE echte Credential-Leckage in der Historie:
`3dcc80d8`, Dateien `wp1d-auth-pagination-filter-errors-live.json` und `wp1d-tenant-leak-matrix.json`.**

### 2.3 Push-Status (entscheidend für §5)

```
git for-each-ref --contains 3dcc80d8
  refs/heads/chore/system-audit-2026-09          <-- NUR der lokale Branch

git merge-base --is-ancestor 3dcc80d8 origin/chore/system-audit-2026-09
  exit=1                                            <-- NICHT gepusht

ahead  = 30 Commits        behind = 0 Commits
```

⇒ **Der Commit `3dcc80d8` ist NIE auf ein Remote übertragen worden.** Die gesamte Audit-Kette
(WP-1a, WP-1c, WP-1d, WP-2, WP-3, WP-4) liegt **30 Commits vor** dem Remote-Ref. **Kein Dritter
besitzt eine Kopie.** Remotes konfiguriert: `origin` = `github.com/Popoboxxo/ReqogniLoom`,
`codeberg` = `codeberg.org/dduchrow/ai-native-reqflow-POC`.

---

## 3. Redaktion des Arbeitsbaums (Changelog)

**Keine History-Rewrite. Nur Arbeitsbaum-Dateien.** Alle übrigen Test- und Nutzdaten wurden
unangetastet belassen (IDs, Namen, `scope`, `warning`, `principal_type`, `agent_label`, Zeitstempel).

| # | Datei | Zeile | Vorher (Typ) | Nachher | Prüfung |
|---|---|---|---|---|---|
| R1 | `docs/audit/2026-09/AUDIT_EVIDENCE/wp1d-auth-pagination-filter-errors-live.json` | 2246 | `reqlo_` + 40 Z. | `reqlo_…REDACTED-78ES` | JSON parst weiterhin ✅ |
| R2 | `docs/audit/2026-09/AUDIT_EVIDENCE/wp1d-tenant-leak-matrix.json` | 101 | `reqlo_` + 40 Z. | `reqlo_…REDACTED-ESUZ` | JSON parst weiterhin ✅ |
| R3 | `docs/audit/2026-09/AUDIT_EVIDENCE/stack-seeds.md` | 26 | `reqlo_` + 40 Z. (**LIVE**) | `reqlo_…REDACTED-ejYR` | 3 identische Vorkommen ersetzt ✅ |
| R4 | `docs/audit/2026-09/AUDIT_EVIDENCE/stack-seeds.md` | 126 | `reqlo_` + 40 Z. (**LIVE**) | `reqlo_…REDACTED-ejYR` | ✅ |
| R5 | `docs/audit/2026-09/AUDIT_EVIDENCE/stack-seeds.md` | 131 | `reqlo_` + 40 Z. (**LIVE**) | `reqlo_…REDACTED-ejYR` | ✅ |
| R6 | `docs/audit/2026-09/AUDIT_EVIDENCE/stack-seeds.md` | 102 | JWT-Fragment (2/3 Seg., 65 Z.) | `eyJ…REDACTED-JWTFRAGMENT(2/3 Segmente, unbrauchbar)` | JSON-Fragment weiterhin parsebar ✅ |

**Bewusst NICHT redigiert (mit Begründung):**

| Datei:Zeile | Grund |
|---|---|
| `README.md:1130,1140,1164,1183` | Dokumentations-Beispiel, **kein** gültiges Format (44 statt 40 Z.), live geprüft **401**. Ein Redigieren würde die API-Doku unbrauchbar machen. Gehört in die Scanner-Ausnahmeliste. |
| 8 × `backend/**/tests/*.py` | Test-Fixtures mit sprechenden Namen (`placeholder`, `testkey`, `test_key`). **FP-Guard des Auftrags.** Gehören in die Scanner-Ausnahmeliste. |
| `deploy/verify-backup-command.sh:90,103` | Passwort eines **Wegwerf**-Backup-Verifikations-Containers, ≠ Produktionspasswort. Ist ein eigener LOW-Befund (CWE-1392), keine Redaktionsfrage — gehört durch eine `${VAR:?}`-Pflichtvariante ersetzt, nicht maskiert. |
| `docs/audit/2026-09/AUDIT_EVIDENCE/wp6a-secrets-scan.md:109-111` | Zitiert Fixture-**Namen** aus meinem eigenen Sweep. Kein Credential, aber Scanner-Rauschen ⇒ Ausnahmelisteneintrag. |

### 3.1 Validierung nach Redaktion

| Prüfung | Ergebnis |
|---|---|
| `wp1d-auth-pagination-filter-errors-live.json` → `ConvertFrom-Json` | **JSON OK**, 6 Top-Level-Keys |
| `wp1d-tenant-leak-matrix.json` → `ConvertFrom-Json` | **JSON OK**, 10 Top-Level-Keys |
| `rg -c 'reqlo_[A-Za-z0-9]{30,}' docs/audit/` | **0 Treffer** ✅ |
| `rg 'eyJ[A-Za-z0-9_-]{10,}\.' docs/audit/` | **0 Treffer** ✅ |
| `rg 'reqlo_[A-Za-z0-9]{30,}' .` (Gesamtrepo) | 4 Treffer — **alle** `README.md` (Doku-Beispiel, Fehlalarm) |
| `rg 'eyJ[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{5,}' .` | **0 Treffer** ✅ |
| `git diff` der beiden JSON-Dateien | **2 Zeilen geändert**, ausschließlich der `plaintext`-Wert; alle übrigen Felder byte-identisch |

---

## 4. Was NICHT getan wurde (Constraint-Treue)

| Aktion | Status | Grund |
|---|---|---|
| `git filter-repo` / `filter-branch` | **nicht ausgeführt** | destruktiv, nicht autorisiert |
| `git push` (auch ohne `--force`) | **nicht ausgeführt** | nicht freigegeben |
| Branch-Mutation, `--amend`, `rebase`, `reset` | **nicht ausgeführt** | nicht autorisiert |
| Revoke des zweiten live Keys (`ff77bbd0-…`) | **nicht ausgeführt** | Auftrag begrenzt DB-Änderung auf **genau einen** Key ⇒ **eskaliert** (§1.5) |
| Revoke der 8 weiteren aktiven `admin`-Keys | **nicht ausgeführt** | dito; Bestandsaufnahme dokumentiert (§1.6) |
| Änderung an `.kimi-code/` | **nicht angefasst** | auftragsgemäß |
| Änderung an Produktivcode / `.env` / CI-Definitionen | **nicht angefasst** | auftragsgemäß |
| Neustart Postgres/Redis/Backend | **nicht ausgeführt** | auftragsgemäß |

---

## 5. Entscheidungsvorlage: History-Rewrite (nicht ausgeführt)

### 5.1 Sachstand

* **Eindeutig betroffen:** genau **1 Commit** (`3dcc80d8`) mit genau **2 Dateien** mit je **1 Zeile**.
* **Der Commit ist nicht gepusht** (§2.3). Kein Remote-Ref enthält ihn.
* **Das Credential ist widerrufen** (§1.4). Es gibt kein laufendes Expositionsfenster.
* **30 lokale Commits** liegen vor dem Remote-Ref und sind **gemeinsame Arbeit anderer Agents**
  (WP-1a, WP-1c, WP-1d, WP-2, WP-3, WP-4 + 24 ältere).

### 5.2 Option A — `git filter-repo` (History umschreiben)

**Vorgehen (nur zur Freigabe-Vorbereitung, nicht ausgeführt):**

```bash
# 1) Sicherung des Zustands VORHER (Pflicht, sonst unwiderruflich)
git branch backup/pre-secret-rewrite-2026-09-30
git bundle create ../backup-pre-secret-rewrite.bundle --all

# 2) replace-text-Datei — WICHTIG: die Klartextwerte werden bewusst NICHT
#    in dieses Audit-Dokument geschrieben (das waere derselbe Fehler wie
#    AUD-2026-09-220). Der Operator traegt sie lokal ein, z. B.:
#
#      git show 3dcc80d8:docs/audit/2026-09/AUDIT_EVIDENCE/wp1d-auth-pagination-filter-errors-live.json \
#        | grep -o 'reqlo_[A-Za-z0-9]\{40\}' > ../secret-replacements.txt
#      git show 3dcc80d8:docs/audit/2026-09/AUDIT_EVIDENCE/wp1d-tenant-leak-matrix.json \
#        | grep -o 'reqlo_[A-Za-z0-9]\{40\}'  >> ../secret-replacements.txt
#      sed -i 's/$/==>reqlo_...REDACTED/' ../secret-replacements.txt
#
#    Ergebnis (maskiert, so steht es hier):
#      reqlo_…REDACTED-78ES==>reqlo_...REDACTED-78ES
#      reqlo_…REDACTED-ESUZ==>reqlo_...REDACTED-ESUZ
#
#    ../secret-replacements.txt liegt AUSSERHALB des Repos und wird nicht committet.

# 3) Rewrite
git filter-repo --replace-text ../secret-replacements.txt --refs chore/system-audit-2026-09

# 4) Verifikation
git log --all -G'reqlo_[A-Za-z0-9]{30,}'          # erwartet: nur noch 29417feb (README-Beispiel)
rg -c 'reqlo_[A-Za-z0-9]{30,}' docs/audit/          # erwartet: 0
```

| Risiko | Bewertung |
|---|---|
| **Geteilte Commits anderer Agents** | 🔴 `filter-repo` schreibt **alle** betroffenen Commit-Hashes um. 30 lokale Commits ⇒ 30 neue SHAs. Jede Referenz anderer Agents (Berichte, Findings, `request_id` in Logs, Chat-Verweise) auf die alten SHAs wird **ungültig**. Da die Commits nicht gepusht sind, ist der Schaden lokal begrenzt — aber die parallel laufenden Agents arbeiten auf diesem Branch. |
| **`docs/audit/`-Evidenzverweise brechen** | 🟡 Die Evidenzdateien referenzieren `3dcc80d8` in `AUDIT_SECURITY.md`, `wp6a-secrets-scan.md` und hier. Diese Verweise müßten auf den neuen SHA aktualisiert werden — sonst dokumentiert das Audit einen Commit, den es nicht mehr gibt. |
| **Force-Push** | 🔴 **Nicht anwendbar**, weil nichts gepusht ist ⇒ **kein** Force-Push nötig. Das ist der entscheidende Vorteil. |
| **`refs/original/`-Backup** | 🟡 `filter-repo` legt standardmäßig **kein** `refs/original/` an (anders als `filter-branch`), sondern **löscht** `origin`-Remote und `reflog`. ⇒ **vorher** ein Bundle erstellen (siehe Schritt 1), sonst existiert der alte Commit im `reflog` weiter. |
| Aufwand | 🟢 **S** (ein Kommando + Verifikation, ca. 5 min) |
| Schadensbegrenzung | 🟢 **hoch** — entfernt ein dauerhaft lesbares Admin-Credential aus einem Repo, dessen Remote `github.com/Popoboxxo/ReqogniLoom` ist |

### 5.3 Option B — Historie belassen, Key widerrufen, Restrisiko dokumentieren

| Merkmal | Bewertung |
|---|---|
| Aufwand | 🟢 XS (nur dieses Dokument) |
| Risiko für laufende Agents | 🟢 keiner |
| Restrisiko | 🟡 Der Klartext-Key bleibt in `3dcc80d8` **unbegrenzt** lesbar für jeden mit Zugriff auf das lokale Repo, alle Clones, alle lokalen Bundles und — falls der Branch **doch** einmal gepusht wird — für die Öffentlichkeit. |
| Restrisiko-Höhe | 🟢 **Gering**, weil (a) der Key widerrufen ist, (b) der Commit nie gepusht war, (c) das `ApiKey`-Modell nur Hashes speichert und (d) keine andere Kopie existiert. |

### 5.4 Empfehlung

> **Option A — aber als koordinierte Einmal-Operation durch den Orchestrator, _vor_ dem ersten Push
> dieses Branches.**

**Begründung in einem Satz:** Der Key ist widerrufen und der Commit war nie gepusht, deshalb ist die
Schadensbegrenzung nicht eilig — aber die Rewrite-Kosten sind **jetzt** minimal (kein Force-Push,
keine externe Kopie, keine geteilten *gepushten* Commits), und in sechs Monaten, wenn der Branch
lange gepusht ist, sind dieselben Kosten um Größenordnungen höher; die Option A ist deshalb **jetzt**
zu ziehen, nicht später.

**Bedingungen (zwingend):**
1. Nur wenn die **parallelen Agents abgeschlossen sind** — `filter-repo` darf nicht unter laufenden
   Agenten auf einem gemeinsamen Branch operieren.
2. `git bundle`-Backup **vor** dem Rewrite (Schritt 1).
3. Nach dem Rewrite: alle SHA-Verweise in `AUDIT_SECURITY.md`, `wp6a-secrets-scan.md` und in
   diesem Dokument aktualisieren.
4. Der Sweep-Abschnitt §2.3 („nicht gepusht") ist danach **falsch** und muss angepasst werden.

**Falls der Orchestrator die Koordination nicht sicherstellen kann, ist Option B die korrekte Wahl** —
mit der ausdrücklichen Folge, dass `AUD-2026-09-220` als „akzeptiertes Restrisiko, widerrufen,
nicht in der Historie bereinigt" im Abschlussbericht steht und **nicht** als „geschlossen".

---

## 6. Gegenprüfung `AUD-2026-09-221` — weiterhin gültig, jetzt **live belegt**

Die Feststellung aus §1 (401 nach Revoke) berührt die Reihenfolge nicht. Sie ist nun **empirisch**
statt nur codeseitig belegt.

### 6.1 Code-Reihenfolge (`mcp_server/views.py`)

```
265  cookie_rejection = _reject_ambient_cookie_auth(request)   # prüft nur die FORM des Credentials
272  retry_after = check_mcp_rate_limit(request)               # <-- RATE-LIMIT, VOR AuthN
     …
307  response_frame = handler.handle_http_request(body, headers)   # <-- AUTHN passiert HIER
```

`_reject_ambient_cookie_auth` gibt bei vorhandenem Header-Key `None` zurück (`views.py:110-118`) und
ruft `api_key_from_request(request)` **nur zum Auslesen des Headers** auf — es validiert nichts.

### 6.2 Live-Messung (Redis DB 1 = Django-Cache, read-only `TYPE`/`STRLEN`/`TTL`)

| Schritt | Beobachtung |
|---|---|
| Bucket identifiziert | `:1:throttle_mcp_ip_172.18.0.1` (Typ `string`, 187 Bytes, TTL 46 s) |
| 5 × `POST /mcp/` mit **absichtlich ungültiger** Credential | 5 × **HTTP 401** |
| `STRLEN` desselben Buckets danach | **205 Bytes** (von 187 ⇒ **+18 Bytes**) |

⇒ **Der Rate-Limit-Zähler ist für Requests gestiegen, deren Authentifizierung fehlgeschlagen ist.**
Das beweist: die Drosselung läuft **vor** der Authentifizierung.

### 6.3 Verknüpfung mit dem Cache-Timeout

Jeder dieser unauthentifizierten 401-Requests hat **zwei** Cache-Zugriffe ausgelöst
(`mcp_server/throttling.py:164`, zwei `SimpleRateThrottle`-Instanzen ⇒ je `get` + `set`), gegen
`CACHES["default"]` **ohne** `socket_timeout` (`settings.py:879-884`). Bei gestörtem Redis blockiert
jeder Zugriff bis zum OS-Connect-Timeout. Der Drosselungsmechanismus, der den Missbrauch begrenzen
soll, **ist** damit der Vektor.

### 6.4 Status

**`AUD-2026-09-221` bleibt unverändert CRITICAL und ist jetzt stärker belegt als im Erstbericht.**
Die Revokation des Keys ändert daran nichts — sie eliminiert gerade den *gültigen*-Credential-Pfad,
während der *ungültige*-Pfad (401) weiterhin zuerst gedrosselt wird.

---

## 7. Prophylaxe-Runbook: `revoke-and-rotate` für Audits

### 7.1 Sofortregeln (gelten ab dem nächsten Audit-Track)

1. **Nie einen Response-Body ungefiltert in eine Evidenzdatei schreiben.** `POST /api/v1/api-keys/`
   liefert `plaintext` **einmalig**; ab dem Moment ist der Key ein persistiertes Secret.
2. **Immer `top_keys` statt `body_head`.** WP-1d hatte das richtige Verfahren bereits
   (`wp1d-auth-pagination-filter-errors-live.json:2237-2245`) und hat es bei `body_head` (`:2246`)
   nicht durchgezogen. Die Regel lautet: **Wertfelder nie, Schlüsselnamen immer.**
3. **Jedes Finding-Belegformat ist maskierungspflichtig.** Bei Credential-Nennungen nur
   `reqlo_…REDACTED-<letzte-4>`; bei JWT nur `eyJ…<Segmenten>-<REDACTED>`; bei Passwörtern nur
   Typ + Länge + Gleichheitsvergleich.
4. **Ein Secret, das in einen Evidence-Store wandert, gilt ab dem Moment als kompromittiert** —
   unabhängig davon, ob die Datei getrackt ist oder nicht.
5. **Vor dem Commit: Secret-Scan.** Siehe §7.3 — derzeit existiert keiner (AUD-2026-09-224).

### 7.2 Cleanup-Verifikation: die konkrete Lücke

`docs/audit/2026-09/AUDIT_EVIDENCE/wp1d-cleanup-verification.md` verifiziert:

| Geprüft | Ergebnis | Lücke |
|---|---|---|
| `POST /auth/login/` als Probe-User | 401 ⇒ User existiert nicht mehr | ✅ korrekt |
| `GET /api/v1/api-keys/` | 200, count | ❌ **nur gezählt, nie inhaltlich geprüft** |
| **Wurde der API-Key widerrufen?** | — | ❌ **nie geprüft** |

⇒ Genau diese Lücke ließ `ff77bbd0-…` und `7eb7adab-…` weiterleben. Ein User-Delete via `CASCADE`
(`ApiKey.user` → `on_delete=CASCADE`, `models.py:132-136`) hätte die Keys mitgeräumt — aber beide
gehören `admin`, einem **gelöschten** Probe-User zugehörigen Key gab es nie.

**Verbindliche Cleanup-Checkliste (für jeden Audit-Track):**

```
[ ] Für JEDEN erzeugten Key:  DELETE /api/v1/api-keys/<id>/   (nicht "User löschen und hoffen")
[ ] Verifikation A:  POST /mcp/ mit dem Key  →  HTTP 401
[ ] Verifikation B:  SELECT revoked_at FROM at_api_key WHERE id = '<id>'  → NOT NULL
[ ] Verifikation C:  GET /api/v1/api-keys/ → enthält die ID NICHT in der aktiven Liste
[ ] Evidenz-Datei:   rg 'reqlo_[A-Za-z0-9]{30,}' docs/audit/  →  0 Treffer
[ ] Key-Liste:       alle erzeugten Key-IDs + Erstellungs- + Widerrufungszeitpunkt protokollieren
```

### 7.3 Verhinderung durch Automatisierung (Priorität)

| Maßnahme | Wirkung | Aufwand |
|---|---|---|
| `pre-commit`-Hook: `gitleaks protect --staged --redact` | verhindert Commit von Credentials | S |
| **Custom-Regel `reqlo_[A-Za-z0-9]{40}`** | **ohne sie findet kein Standard-Scan den Projekt-Key** | XS |
| CI-Step `gitleaks detect` + `gitleaks detect --no-git` (History + Arbeitsbaum) | verhindert Push | S |
| **Evidenz-Wrapper** mit Pflicht-Redaktion: `safe_dump(response)` entfernt automatisch `plaintext`, `token`, `password`, `key`, `secret` aus jedem Wert, schreibt nur `top_keys` + maskierte Values | verhindert den Fehler an der **Quelle** | M |
| Cleanup-Checkliste §7.2 in die Audit-Task-Definition | verhindert das Wiederleben | XS |

Der Evidenz-Wrapper ist die **einzige** Maßnahme, die den Fehler an der Wurzel behebt. Ein Scanner
findet den Secret-Scan-zeitpunkt; nur der Redactor verhindert, dass er entsteht.

---

## 8. Finding-Status nach dieser Remediation

| ID | Status | Änderung |
|---|---|---|
| `AUD-2026-09-220` | **TEILWEISE BEHOBEN** | Key **widerrufen** (3-facher Beleg), Arbeitsbaum **redigiert** (verifiziert). **Offen:** History-Option (§5), zweiter live Key `ff77bbd0-…` (§1.5), 8 weitere aktive `admin`-Keys (§1.6). |
| `AUD-2026-09-221` | **WEITER BESTÄTIGT, jetzt live belegt** | §6: Zähler stieg um 3 unauthentifizierte 401er ⇒ Drosselung vor AuthN. |
| `AUD-2026-09-239` (neu) | **NEU** | Prozessursache: Audit erzeugte selbst den Leak (fehlender Evidenz-Redactor + unvollständige Cleanup-Verifikation). Details in `AUDIT_SECURITY.md` §1 und §2.6. |
| `AUD-2026-09-240` (neu) | **NEU** | 9 aktive `admin`-Keys, alle ohne `expires_at` und ohne Workspace-Fence (§1.6). |
| `AUD-2026-09-241` (neu) | **NEU** | Hardcoded Credentials in getrackten Deploy-Dateien (`deploy/verify-backup-command.sh:90,103`; `deploy/docker-compose.yml:73,1053`) — CWE-1392, LOW. |

**Kein Befund wurde geschlossen.** MERGE_SCORE bleibt unverändert.