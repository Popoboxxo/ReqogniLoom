---
type: REVIEW
scope: security-track-review
status: final
date: 2026-10-01
author_agent: security-auditor
branch: chore/audit-review-2026-09
parent: docs/audit/2026-09/review/plan/SECURITY_TRACK.md
sources:
  - docs/audit/2026-09/review/plan/SECURITY_TRACK.md
  - docs/audit/2026-09/AUDIT_EVIDENCE/secret-incident-2026-09-30.md
  - docs/audit/2026-09/review/AUDIT_REVIEW_SUMMARY.md
  - docs/audit/2026-09/review/evidence/REVIEW_WP6A.md
  - docs/audit/2026-09/review/plan/IMPLEMENTATION_PLAN.md
  - docs/audit/2026-09/review/plan/SECURITY_AUTHZ.md
---

# SECURITY_TRACK_REVIEW — Verifikation & Schärfung des P0-Security-Tracks

> **Rolle.** Statische, read-only Verifikation des P0-Tracks `SECTRACK-01…05` aus
> `plan/SECURITY_TRACK.md` aus Sicht des Security-Audits. Kein Produktcode geändert,
> keine Git-Mutation, keine bestehenden Dateien geändert, **kein Klartext-Secret**
> (ausschließlich maskierte IDs, letzte 4 Zeichen). Alle Aussagen wurden am HEAD
> `chore/audit-review-2026-09` neu gegen Repository-Zustand, Produktcode und
> Evidenz abgeleitet.

---

## 1. Verdikt

**Der Track ist richtig priorisiert (P0), aber in der Ausführung an drei Stellen
blockierend unter-spezifiziert.** Die Reihenfolge Rotation → History-Rewrite →
Scan-Gate → Redactor ist sachlich vertretbar; die größte Schwäche liegt in
**SECTRACK-02**: die dort vorgegebene Befehlszeile würde den Leak auf dem aktuell
ausgecheckten Branch **nicht** entfernen (F1), die Vorbedingungen sind unvollständig
(F2), und das Bundle/Ersatztextfile werden nicht als neue Secret-Stores behandelt
(F3). **SECTRACK-01** zielt policy-seitig auf das falsche Objekt: die
Agent-Key-Pflicht (`expires_at`, `workspace_ids`) ist **bereits** implementiert —
die reale Lücke sind Legacy-`user`-Keys mit `scope=write` (legacy ADMIN-Tier) und
`expires_at=NULL` (F5).

| Einheit | Verdikt | Kern |
|---|---|---|
| SECTRACK-01 | **bestätigt, Ziel geändert** | Notwendigkeit bestätigt; Policy-Achse falsch adressiert, Inventar-Tool + Klassifikation fehlen |
| SECTRACK-02 | **geändert** | Ref-Scope fehlerhaft, Vorbedingungen unvollständig, neue Secret-Stores unbenannt |
| SECTRACK-03 | **bestätigt, ergänzt** | Kern korrekt; Config/Regex/Version/Ordering/CI-Ort fehlen |
| SECTRACK-04 | **bestätigt, geändert** | Denylist „`key`" zu breit; konkretes Modul + Test fehlen |
| SECTRACK-05 | **bestätigt, geändert** | Anker/Werte ungenau; zusätzliche getrackte Weak-Defaults fehlen |

---

## 2. Methodik & verifizierte Evidenz

**Read-only Git-Proben (keine Mutation):**

| Prüfung | Ergebnis |
|---|---|
| `git rev-parse --abbrev-ref HEAD` | `chore/audit-review-2026-09` |
| `git cat-file -t 3dcc80d8` | `commit` |
| `git for-each-ref --contains 3dcc80d8` | **`refs/heads/chore/audit-review-2026-09`** **und** `refs/heads/chore/system-audit-2026-09` |
| `git merge-base --is-ancestor 3dcc80d8 origin/main` | **exit 1** (nie gepusht) |
| `git check-ignore -v …/stack-seeds.md` | **exit 1** → **nicht ignoriert** |
| `git status --porcelain` | `?? .kimi-code/`, `?? …/stack-seeds.md`, `?? …/EFFORT_ESTIMATES.md` |
| Blob `3dcc80d8:…auth-pagination…json` | enthält `body_head` mit `plaintext` (40 Zeichen) **neben** `top_keys` (Ursache bestätigt) |

**Produktcode-Proben:**

| Prüfung | Ergebnis |
|---|---|
| `auth_tenancy/models.py:142,160,162` | `revoked_at` (nullable), `workspace_ids` Default `[]`, `expires_at` Default `NULL` |
| `auth_tenancy/models.py:154-157` | `scope` Default `write` = **legacy widest (ADMIN) tier** |
| `auth_tenancy/services/authentication.py:552-558` | Agent-Key-AuthN erzwingt Scope + `workspace_ids` + `expires_at` **bereits** |
| `authentication.py:619-646` | `create_api_key` erzwingt Agent-Policy **bereits** |
| `authentication.py:718-736` | `revoke_api_key` setzt `revoked_at`, nur wenn `NULL` |
| `authentication.py:698-716` | `list_api_keys` liefert **auch widerrufene** Keys mit `revoked`-Flag |
| `auth_tenancy/management/commands/inventory_api_keys.py` | **existiert** (read-only Inventar, CR-03, kein `--fix`) |
| `.woodpecker.yml:76-81` | nur `safety check` (Dependency), **kein** Secret-Scan |
| `.github/workflows/{ci,playwright,docker-publish,pages,version-drift-check}.yml` | vorhanden; kein Secret-Scan |
| `.pre-commit-config.yaml` | **nicht vorhanden** |
| `.gitignore` | `.env` vorhanden; `stack-seeds.md`/`.kimi-code/` **nicht** ignore-regeln |

**Bewertungsbasis:** `AUDIT_REVIEW_SUMMARY.md` §7, `secret-incident-2026-09-30.md`
§1.5/§2.3/§5/§7/§9, `REVIEW_WP6A.md` §2/§6. Docker-Daemon-Status unbekannt → keine
Live-Messung; der Widerruf `7eb7adab…` bleibt „dokumentiert, nicht live bestätigt".

---

## 3. Einheiten — Verdikt, Akzeptanz, Verifikation, Rollback, Deps

### SECTRACK-01 — Key-Rotation: `ff77bbd0…` + aktive `admin`-Keys

**Verdikt: Notwendigkeit BESTÄTIGT; Zielverhalten GEÄNDERT.**

- **Befund:** `ff77bbd0-e99c-…` (Owner `admin`, `readwrite`, `expires_at=NULL`,
  `revoked_at=NULL`) ist **live** und nur in `stack-seeds.md` (untracked) — er wird
  vom History-Rewrite **nicht** erwischt. Zusätzlich existieren laut Evidenz §1.6
  **9 aktive Keys am `admin`-Konto** (einschließlich `ff77bbd0…`), alle ohne
  `expires_at`/Workspace-Fence. Der geleakte `7eb7adab…` hatte `scope=write` =
  legacy ADMIN-Tier.
- **Korrektur am Plan:** „Policy: Agent-Keys benötigen `expires_at` und
  `workspace_ids`" beschreibt **bereits implementiertes** Verhalten
  (`authentication.py:552-558,619-646`). Die real offene Policy ist:
  1. **Legacy-`user`-Keys** mit `scope=write` (ADMIN) und `expires_at=NULL` sind
     unbeschränkt; ein Key ohne `principal_type=agent` umgeht die Pflichten.
  2. Neue **Automatisierungs-Keys** müssen auf `principal_type=agent` gezwungen
     werden (oder `expires_at`+`workspace_ids` müssen für **alle** Keys mit
     `scope ∈ {write, admin}` Pflicht werden).
- **Zielverhalten (geändert):** `ff77bbd0…` über den Produktionspfad
  `DELETE /api/v1/api-keys/ff77bbd0…/` widerrufen
  (nicht User löschen); die 9 aktiven `admin`-Keys **zuerst inventarisieren und
  klassifizieren** (Test-Fixture vs. echter Agent-Key), dann widerrufen bzw.
  rotieren; Default-Policy für Legacy-`user`-Keys nachziehen.
- **Messbare Akzeptanzkriterien:**
  - `ff77bbd0…`: `POST /mcp/` `tools/list` ⇒ **HTTP 401**; zweite Messung nach
    ≥ 60 s ebenfalls 401.
  - DB: `SELECT revoked_at FROM at_api_key WHERE id='ff77bbd0-…'` ⇒ **NOT NULL**
    (nicht `is_active` — das ist ein read-only Property, `models.py:174-177`).
  - `list_api_keys`-Antwort enthält den Key mit **`revoked == true`** (nicht bloß
    „nicht in Liste" — die API liefert auch widerrufene Keys, `:700-716`).
  - Inventory vor Rotation: `python manage.py inventory_api_keys --format json`
    listet die aktiven Keys; je Key liegt eine begründete Entscheidung
    (widerrufen / rotieren / behalten) vor.
  - Policy-Test: Neuer Key mit `scope=write` **und** `expires_at=NULL` wird auf
    Automatisierungspfad **abgelehnt** (rot-bewiesen vor Fix).
- **Verifikation:** Live-401 (2 Messungen) + DB-`SELECT` + `inventory_api_keys`
  Vor-/Nachlauf + pytest.
- **Risiko/Rollback:** Rotation der 9 Keys kann laufende Clients/e2e-Kampagnen
  brechen (Evidenz nennt `MCP-UI-Campaign-REQ129…`, `admin_key`, `read_key`).
  → Inventar + Ersatzkeys **vor** Widerruf; Rollback nur durch Neu-Ausstellen,
  **nie** durch Reaktivieren des widerrufenen Keys (`revoke` ist irreversibel).
- **Deps:** keine (blockiert nicht auf History-Rewrite). **Prio: P0, unabhängig —
  höchste zeitliche Dringlichkeit, weil `ff77bbd0…` live ist.**

### SECTRACK-02 — History-Blob Option A (`git filter-repo`)

**Verdikt: GEÄNDERT — so wie instruiert, unvollständig und teilweise wirkungslos.**

- **Befund F1 (blockierend):** Der Plan schreibt
  `git filter-repo --replace-text … --refs chore/system-audit-2026-09`. Der Leak
  `3dcc80d8` ist aber **auch** über `refs/heads/chore/audit-review-2026-09` (dem
  **aktuell ausgecheckten** Branch) erreichbar. Ein Rewrite nur von
  `chore/system-audit-2026-09` lässt den Blob auf dem aktuellen Branch bestehen;
  `git gc` kann ihn dann **nicht** prunen, und `git grep` am HEAD bleibt positiv.
- **Befund F2:** Vorbedingungen unvollständig (siehe §5).
- **Zielverhalten (geändert):** `--replace-text` über **alle** Refs (kein `--refs`
  oder explizit beide lokalen Branches), `--force`, danach `reflog expire` +
  `gc --prune=now`, Remote-Wiederanbindung **ohne Push**, Unerreichbarkeits-Beweis,
  vollständiger SHA-Verweis-Sweep.
- **Messbare Akzeptanzkriterien:**
  - `git for-each-ref --contains 3dcc80d8` ⇒ **leer** (Commit auf keinem Ref).
  - `git cat-file -e 3dcc80d8` ⇒ **schlägt fehl** (Objekt nach `gc` weg).
  - `git log --all -G 'reqlo_[A-Za-z0-9]{40}\b'` ⇒ 0; Baum-Ebene über alle
    erreichbaren Commits ⇒ 0 in `docs/audit/**`.
  - `git rev-list --all` + `git grep -lE 'reqlo_[A-Za-z0-9]{40}\b' <commit>` ⇒ 0
    (die README-Doku-Beispiele sind **44** Zeichen und werden durch `\b` nicht
    erfasst; siehe SECTRACK-03).
  - Bundle liegt **außerhalb** des Repos, ist als Secret klassifiziert und
    verschlüsselt/ACL-geschützt; Ersatztextfile sicher gelöscht (§5).
  - Alle SHA-Verweise aktualisiert (§5, F10).
- **Verifikation:** die obigen fünf Kommandos als Skript, Ergebnis als
  Evidenzdatei (via Redactor, SECTRACK-04).
- **Risiko/Rollback:** Umschreiben aller ~30 lokalen SHAs; Revert **nur** aus dem
  Bundle. Voraussetzung: parallele Agents beendet.
- **Deps:** keine fachliche; **Reihenfolge** zu SECTRACK-03 beachten (§6).

### SECTRACK-03 — Secret-Scan-Gate

**Verdikt: Kern BESTÄTIGT; Spezifikation ERGÄNZT (Config, Regex, Version, Ordering, CI-Ort).**

- **Befund:** Kein `.pre-commit-config.yaml`, kein Scanner, keine `.gitleaks.toml`;
  `.woodpecker.yml:76-81` scannt nur Dependencies. Der Projekt-Key
  (`reqlo_` + 40) wird von gitleaks-Standardregeln **nicht** erkannt.
- **Zielverhalten:** Pre-Commit + CI-Gate mit Custom-Regel und schmaler Allowlist;
  positive/negative Probe.
- **Messbare Akzeptanzkriterien:**
  - Positivprobe: ein Test-Commit mit synthetischem `reqlo_` + 40 Zeichen wird
    vom Pre-Commit-Hook **blockiert** und von CI **rot** bewertet.
  - Negativprobe: unverändertes `README.md` und die 9 Test-Fixtures werden
    **nicht** als Finding gemeldet.
  - `git grep`/`rg` über `docs/audit/**` nach Merge ⇒ 0.
- **Verifikation:** lokaler Hook-Lauf + CI-Lauf, beide mit `--redact`; Ergebnis
  in der Committung dokumentiert (Redactor).
- **Risiko/Rollback:** Fehlalarme blockieren Commits → Allowlist pflegen; Gate im
  Zweifel branch-/job-spezifisch abschaltbar, aber nie dauerhaft.
- **Deps:** inhaltlich unabhängig; **Ordering** siehe §6 (History-Detect vs.
  Rewrite).

### SECTRACK-04 — Evidenz-Redactor + Cleanup-Checkliste

**Verdikt: BESTÄTIGT; Denylist/Modul nachgeschärft.**

- **Befund F7:** Die Formulierung „entfernt `plaintext`/`token`/`password`/`key`/
  `secret` aus **jedem Wert**" ist gefährlich unscharf. `key` als **Substring**
  trifft `top_keys`, `key_hash`, `api_key_id` — also ausgerechnet die Felder, die
  als Evidenz erhalten bleiben müssen. Ziel muss eine **exakte Feldnamen-Denylist**
  sein; `top_keys` ist ein Schlüssel**namen**-Feld und wird **nicht** entfernt.
- **Zielverhalten:** konkreter Wrapper (z. B. `scripts/audit/evidence.py`)
  `safe_dump(response)` mit:
  1. **nie** Roh-Body serialisieren (`body_head` entfällt ersatzlos);
  2. nur `status`, `top_keys`, `value_types`, `body_len`, `redacted_value_keys`;
  3. exakte Denylist (normalisiert, case-insensitive): `plaintext`, `token`,
     `access_token`, `refresh_token`, `password`, `secret`, `api_key`, `apikey`,
     `key_hash`, `private_key`, `client_secret`, `authorization`, `cookie`,
     `session`;
  4. falls ein Wert gezeigt werden muss: `type + length + last4`, nur für
     nicht-sensitive Identifier.
- **Messbare Akzeptanzkriterien:**
  - Unit-Test mit synthetischer Response `{plaintext, token, password, secret,
    key_hash, name, id, top_keys}` ⇒ Output enthält **keinen** dieser Werte,
    **aber** `top_keys` und `name`.
  - `rg '"plaintext"\s*:\s*"reqlo_' docs/audit/**/*.json` ⇒ 0.
  - `rg 'reqlo_[A-Za-z0-9]{40}\b' docs/audit/` ⇒ 0.
  - Cleanup-Checkliste ist Bestandteil der Audit-Task-Definition und wird je Key
    abgehakt.
- **Verifikation:** Unit-Test + Repo-Grep; der Test beweist auch die
  Über-Redaktions-Grenze (`top_keys` überlebt).
- **Risiko/Rollback:** zu aggressiver Redactor zerstört Evidenz → exakte Namen
  statt Substring; Audit-Nutzdaten (IDs, Scope, Zeitstempel) bleiben.
- **Deps:** keine; sollte **vor** neuen Evidenzdateien aktiv sein.

### SECTRACK-05 — Hardcoded Deploy-Credentials

**Verdikt: BESTÄTIGT; Anker/Werte korrigiert, Umfang erweitert.**

- **Befund F8:** Plan zitiert `deploy/docker-compose.yml:73,1053`
  (`HONCHO_DB_PASSWORD:-honcho`). Tatsächlicher Default ist
  **`honcho-dev-password`**; zusätzlich enthält **`:1020`** denselben Default
  (`REVIEW_WP6A` §3.3, Duplikat `AUD-241↔148`). Nicht erfasst:
  `deploy/docker-compose.override.yml:13` `${DB_PASSWORD:-reqogniloom}` mit
  Kommentar „Weak password OK for dev" (getrackt).
- **Zielverhalten:** `${VAR:?}`-Pflichtvariablen; Compose-Defaults entfernen.
- **Messbare Akzeptanzkriterien:** `docker compose config` ohne gesetzte Variable
  ⇒ Fehlschlag mit klarer Meldung; `rg 'HONCHO_DB_PASSWORD:-' deploy/` ⇒ 0;
  `rg 'POSTGRES_PASSWORD=|PASSWORD=' deploy/verify-backup-command.sh` ⇒ 0.
- **Verifikation:** Compose-Config-Test + Grep; Deployment-Doku nennt Pflichtvariablen.
- **Risiko/Rollback:** Deployment muss Variablen setzen → dokumentieren.
- **Deps:** keine. **P2** bleibt korrekt (Wegwerf-Container + Dev-Override).

---

## 4. SECTRACK-01/02/03/04 — Kritikalität & Reihenfolge (Bestätigung)

- **SECTRACK-01 ist der einzige Einheit mit einem *live* Credential** (`ff77bbd0…`,
  HTTP 200). Sie ist damit zeitlich **vor** dem History-Rewrite zu erledigen — der
  Plan ordnet das korrekt ein. Sie ist aber **nicht** vom Rewrite abhängig.
- **SECTRACK-02 ist der einzige Parameter, der die Kritikalität von `220` senkt**
  (der Blob verschwindet). Ohne funktionierenden Rewrite bleibt `220` Critical.
- **SECTRACK-03/04 sind Prevention** und senken die Wiederholungswahrscheinlichkeit,
  aber nicht die aktuelle Exposition.
- **Empfohlene Reihenfolge (geschärft):**
  1. **SECTRACK-01** (Rotation `ff77bbd0…` + Klassifikation/Inventory der 9 Keys)
     — sofort, unabhängig.
  2. **SECTRACK-04** (Redactor) — vor jeder neuen Evidenzdatei; kein Blocker für 01.
  3. **SECTRACK-02** (History-Rewrite) — wenn alle parallelen Agents beendet sind.
  4. **SECTRACK-03** (Scan-Gate) — inhaltlich vor dem ersten Push; **History-Detect
     erst nach dem Rewrite** (sonst sofort rot, siehe §6).
  - **Prio-Korrektur:** 03/04 sind nicht „P0 vor Push" wegen aktueller Exposition,
    sondern Prozess-P0 (Audit erzeugte den Leak selbst). Das ändert die
    Reihenfolge 01 → 02 → 03 nicht, wohl aber die Begründung.

---

## 5. History-Rewrite (Option A) — zwingende Vorbedingungen & Restrisiko

### 5.1 Zwingende Vorbedingungen (Checkliste)

```
[ ] Parallele Agents/Prozesse beendet; keine offenen Schreib-Locks; kein Merge/Rebase im Gange
[ ] `git status` enthält nur bekannte untracked Dateien (.kimi-code/, stack-seeds.md, EFFORT_ESTIMATES.md)
[ ] `git for-each-ref --contains 3dcc80d8` dokumentiert (erwartet: BEIDE lokalen Branches)
[ ] Submodul-/gitlink-Status geprüft (.agent-meta bleibt unberührt; .gitmodules unverändert)
[ ] Bundle-Backup erstellt UND als Secret klassifiziert (verschlüsselt, außerhalb Repo, ACL)
[ ] Ersatztextfile liegt außerhalb des Repos und wird nach dem Rewrite sicher gelöscht
[ ] Remote-URL notiert (filter-repo entfernt `origin`) — NICHT pushen
[ ] SHA-Verweis-Sweep vollständig (siehe 5.2)
[ ] Kein Push bis nach Gesamt-DoD (IMPLEMENTATION_PLAN §9)
```

### 5.2 Korrigierte Befehlsfolge (read-only Beleg, nicht ausgeführt)

```bash
# 0. Freeze (siehe Checkliste)

# 1. Backup — das Bundle enthält den Klartext-Blob und ist damit ein SECRET
git bundle create <off-repo-pfad>/pre-rewrite.bundle --all
git bundle verify <off-repo-pfad>/pre-rewrite.bundle

# 2. Ersatzliste (Klartext!, außerhalb Repo, verzeichnet die letzten 4 Zeichen als Label)
#    <reqlo_+40>==>reqlo_...REDACTED-<last4>

# 3. Rewrite über ALLE Refs (KEIN --refs <eine Branch>) — filter-repo verlangt --force,
#    weil das Repo nicht frisch geklont ist und `origin` konfiguriert ist
git filter-repo --replace-text <off-repo-pfad>/replacements.txt --force

# 4. Reflog/Objekte entfernen (sonst bleibt der Blob lokal auflösbar)
git reflog expire --expire=now --all
git gc --prune=now --aggressive

# 5. Remote wieder anbinden (filter-repo hat origin entfernt) — NICHT pushen
git remote add origin <origin-url>

# 6. Verifikation
git for-each-ref --contains 3dcc80d8      # erwartet: leer
git cat-file -e 3dcc80d8                  # erwartet: Fehler (Objekt weg)
git log --all -G 'reqlo_[A-Za-z0-9]{40}\b'   # erwartet: 0
# Baum-Ebene über alle erreichbaren Commits:
git rev-list --all | ForEach-Object { git grep -lE 'reqlo_[A-Za-z0-9]{40}\b' $_ -- docs/audit }
# erwartet: keine Treffer
```

**Warum `\b`?** `reqlo_[A-Za-z0-9]{40}` matcht als Teilstring auch das
**44**-Zeichen-README-Beispiel und würde die Allowlist aufblähen. `{40}\b` trifft
nur echte 40-Zeichen-Keys (Produktformat), nicht die 44er-Doku und nicht die
15–35-Zeichen-Test-Fixtures. Damit wird die Allowlist minimal und ehrlich.

### 5.3 SHA-Verweis-Sweep (Plan unvollständig — F10)

Der Plan nennt **3** Zieldokumente (`AUDIT_SECURITY.md`, `wp6a-secrets-scan.md`,
`secret-incident-*.md`). Tatsächlich referenzieren `3dcc80d8` (Stand HEAD) u. a.:

`AUDIT_SECURITY.md`, `AUDIT_SUMMARY.md`, `AUDIT_BACKLOG.md`, `AUDIT_FINDINGS.md`,
`AUDIT_INFRASTRUCTURE.md`, `AUDIT_NATIVE_PLUGINS.md`, `verification-2026-09-30.md`,
`wp1c-compose-validation.md`, `wp2-plugin-inventory-and-manifest-matrix.md`,
`wp6a-secrets-scan.md`, `secret-incident-2026-09-30.md`,
`AUDIT_REVIEW_FINDINGS.md`, `AUDIT_REVIEW_SUMMARY.md` sowie
`review/plan/SECURITY_TRACK.md` und `IMPLEMENTATION_PLAN.md` (`base_head: 3da62d63`).
→ Der Sweep muss per `git grep -l 3dcc80d8` **erzeugt** werden, nicht manuell
aufgezählt; danach `git grep -c 3dcc80d8` ⇒ 0 (bis auf die bewusste, datierte
Incident-Historie-Notiz, die den *alten* SHA als „historisch, rewritten"
festhält).

### 5.4 Option B — Restrisiko (bewertet)

| Restkanal | Bewertung |
|---|---|
| Git-Blob `3dcc80d8` im lokalen Objektstore | **bleibt lesbar** für jeden mit Repo-Zugriff/Fork/Clone/Bundle |
| Remote | Kein Risiko **solange** nie gepusht; ein versehentliches `git push --all` exponiert den (widerrufenen) Key sofort |
| CI-Runner-Caches, IDE-Local-History, Windows Shadow Copies, Backup-Snapshots | **bleiben außerhalb der Reichweite von `filter-repo`** — auch Option A beseitigt sie nicht |
| Key-Material | `7eb7adab…` widerrufen ⇒ **kein laufendes Credential**; Scope/Format/Key-ID werden aber weiter offengelegt |
| Zweiter Key `ff77bbd0…` | **nicht betroffen** — liegt in untracked `stack-seeds.md` und wird durch Option A **nicht** bereinigt (SECTRACK-01!) |

**Restrisiko Option B: LOW–MEDIUM**, aber **nur akzeptabel** mit (a) datiertem
„accepted risk"-Eintrag, (b) hartem Verbot, das Key-Material je wiederzuverwenden,
(c) einem **datierten** `gitleaks`-Allowlist-Eintrag für `3dcc80d8` (sonst ist CI
dauerhaft rot), der nach einem etwaigen späteren Rewrite entfernt wird. Option A
bleibt die bessere Wahl (kein Force-Push nötig), **sofern §5.1/§5.2 eingehalten**.

---

## 6. Secret-Scan-Gate — Spezifikation

**Abgrenzung:** Pre-Commit schützt nur lokal; CI ist der Backstop. Beide CIs des
Repos existieren: GitHub Actions (`.github/workflows/ci.yml` u. a.) und Woodpecker
(`.woodpecker.yml`, nur `push` auf `main`). Das Gate gehört **in beide** (bzw. in
den PR-/Push-Pfad) — nicht nur nach `main`.

### 6.1 `.gitleaks.toml` (Custom-Regel, boundary-anchored)

```toml
title = "ReqogniLoom secret-scan config"

[extend]
useDefault = true

[[rules]]
id = "reqlo-api-key"
description = "ReqogniLoom API key (reqlo_ + exactly 40 alnum)"
regex = '''reqlo_[A-Za-z0-9]{40}\b'''
keywords = ["reqlo_"]

[allowlist]
description = "Nur dokumentierte Beispiel-/Fixture-Platzhalter — keine echten Keys"
# Boundary-anchored Rule trifft 44-Zeichen-README und <40-Zeichen-Fixtures bereits
# nicht; diese Regexes fangen nur Default-Regel-Rauschen ab.
regexes = [
  '''reqlo_[A-Za-z0-9]{41,}''',
  '''reqlo_test_placeholder_token''',
  '''reqlo_[A-Za-z0-9_]*placeholder[A-Za-z0-9_]*''',
  '''reqlo_[A-Za-z0-9_]*testkey[A-Za-z0-9_]*''',
]
paths = [
  '''README\.md$''',
  '''docs/audit/2026-09/AUDIT_EVIDENCE/wp6a-secrets-scan\.md$''',
]
```

**Pflicht:** Die Allowlist ist **schmal und begründet** (je Eintrag Datum + Grund).
Sie darf **keine** gesamten Test-Verzeichnisse pauschal freistellen — sonst bleibt
ein realer Key in einer Testdatei unentdeckt. Die 9 Fixture-Dateien aus Evidenz
§2.1 (Zeilen 6–14) sind über die Platzhalter-Regex abgedeckt; nur wenn das nicht
greift, werden exakte Pfade ergänzt.

### 6.2 Pre-Commit

```yaml
repos:
  - repo: https://github.com/gitleaks/gitleaks
    rev: v8.28.0          # PFLICHT: exakt pinnen
    hooks:
      - id: gitleaks
        args: ["protect", "--staged", "--redact", "--config", ".gitleaks.toml"]
```

- **Versions-Klausel:** Die gitleaks-v8-Subkommandos heißen je Version
  unterschiedlich (`protect`/`detect` vs. die neueren `git`/`dir`-Varianten). Der
  Plan darf die Befehlsnamen **nicht** ohne Versions-Pin festschreiben; die exakte
  Schreibweise ist gegen die gepinnte Version (`gitleaks --help`) zu bestätigen.
- **Bootstrap:** Der Hook wirkt nur nach `pre-commit install` → CI-Backstop ist
  zwingend.

### 6.3 CI (Backstop, History + Arbeitsbaum)

```yaml
# in .github/workflows/ci.yml und als Woodpecker-Step
- name: Secret scan (working tree)
  run: gitleaks detect --source . --no-git --redact --config .gitleaks.toml --exit-code 1
- name: Secret scan (history)
  run: gitleaks detect --source . --redact --config .gitleaks.toml --exit-code 1
```

- **Ordering-Falle (F6):** Solange `3dcc80d8` existiert, ist `gitleaks detect`
  (History) **sofort rot**. Der Plan nennt kein Ordering. Zulässig sind nur zwei
  Wege: **(a)** History-Rewrite zuerst, dann Historie-Scan ohne Ausnahme; oder
  **(b)** Historie-Scan zuerst mit **datiertem** Allowlist-Eintrag für `3dcc80d8`,
  der nach dem Rewrite **entfernt** wird. Ohne diese Entscheidung wird das Gate
  beim ersten Lauf rot und faktisch abgeschaltet.

### 6.4 Evidenz-Redactor (SECTRACK-04)

- `safe_dump()`: **nur** `status`/`top_keys`/`value_types`/`body_len`/
  `redacted_value_keys`; **nie** Body-Bytes; exakte Feldnamen-Denylist (nicht
  Substring „key"). `top_keys` überlebt als Schlüsselnamen-Feld.
- Kein Klartext in Evidenzdateien: `plaintext`, `token`, `access_token`,
  `refresh_token`, `password`, `secret`, `api_key`, `key_hash`, `client_secret`,
  `authorization`, `cookie`, `session`.
- **Cleanup-Checkliste (geschärft):**

```
[ ] Für JEDEN erzeugten Key: DELETE /api/v1/api-keys/<id>/ → HTTP 204
[ ] Verifikation A: POST /mcp/ mit dem Key → HTTP 401 (2 Messungen)
[ ] Verifikation B: SELECT revoked_at FROM at_api_key WHERE id='<id>' → NOT NULL
[ ] Verifikation C: list_api_keys → Eintrag mit revoked == true
    (NICHT „nicht in Liste": die API liefert auch widerrufene Keys, authentication.py:698-716)
[ ] Verifikation D: rg 'reqlo_[A-Za-z0-9]{40}\b' docs/audit/ → 0
[ ] Key-Register: id, name, principal_type, scope, Erstellungs-/Widerrufszeitpunkt
```

- **Test:** Unit-Test des Redactors (synthetische Response mit allen Denylist-Feldern
  + `top_keys`) ⇒ `rg reqlo_` auf Output = 0, `top_keys` vorhanden.

---

## 7. Was der Plan übersieht (Lücken)

1. **F1 — Rewrite-Ref-Scope:** `--refs chore/system-audit-2026-09` verfehlt den
   aktuellen Branch `chore/audit-review-2026-09`; der Leak überlebt am HEAD.
2. **F2 — Rewrite-Vorbedingungen:** `--force` fehlt (filter-repo verweigert bei
   konfiguriertem `origin`), Remote-Wiederanbindung fehlt, Unerreichbarkeits-Beweis
   (`git cat-file -e` / `for-each-ref --contains`) fehlt, `reflog expire`+`gc`
   nicht mit Prune-Verifikation verbunden.
3. **F3 — Neue Secret-Stores:** Bundle **und** Ersatztextfile enthalten den
   Klartext-Key; der Plan behandelt sie nicht als Secrets (keine Verschlüsselung,
   keine sichere Löschung, keine Retention). Der Bundle ist damit selbst ein
   neues Secret-at-Rest.
4. **F4 — `stack-seeds.md` und `.kimi-code/`:** beide untracked und **nicht
   ignore-regeln** (`git check-ignore` exit 1) → ein `git add -A` committet sie.
   `stack-seeds.md` nach Nutzung sicher löschen; `.kimi-code/` in
   `.git/info/exclude` aufnehmen (nicht committen) und **read-only** scannen —
   der Sweep hat `.kimi-code/` bewusst ausgelassen, es ist damit eine ungeprüfte
   Secret-Fläche.
5. **F5 — Policy falsch adressiert:** Agent-Key-Pflicht ist bereits implementiert;
   Lücke sind Legacy-`user`-Keys (`scope=write` = ADMIN, `expires_at=NULL`).
   Zusätzlich: das vorhandene `inventory_api_keys`-Command wird nicht genutzt, und
   die 9 Keys werden nicht klassifiziert (Test-Fixture vs. echter Client) — blinde
   Rotation bricht sonst e2e-Kampagnen.
6. **F6 — Scan-Gate-Ordering:** Historie-Detect ist vor dem Rewrite rot; ohne
   datierte Allowlist oder Rewrite-first wird das Gate abgeschaltet.
7. **F7 — Redactor-Spezifikation:** Substring „key" zerstört `top_keys`/`key_hash`
   vs. über-redigiert; kein konkretes Modul/Test benannt.
8. **F8 — SECTRACK-05-Anker/Werte:** Default ist `honcho-dev-password` (nicht
   `honcho`), `:1020` fehlt, `docker-compose.override.yml:13` nicht erfasst.
9. **F10 — SHA-Sweep unvollständig:** ≥ 13 Dokumente vs. 3 genannte.
10. **Kein Push-Verbot als technische Sperre:** Das Verbot steht nur in Prosa. Ein
    Guard/Hook, der `git push` während SECTRACK blockt, wäre belastbarer (der
    Konventions-Guard ist keine Security-Boundary, `.claude/rules/branch-guard.md`).
11. **`principal_type`-Default:** `create_api_key` defaultet auf `user`; ohne
    explizite Automatisierungs-Policy entstehen weiterhin ADMIN-weite Keys ohne
    Ablauf.
12. **Rotation des `admin`-Kontos selbst:** 9 Keys an einem `admin`-Konto ohne
    Expiry ist ein Single-Point-of-Failure; neben Key-Rotation fehlt eine Aussage
    zu MFA/Brute-Force am `admin`-Login (Querbezug `SEC-04`/`AUD-223`).

---

## 8. Findings

## Finding #1
**Severity:** HIGH
**File:** docs/audit/2026-09/review/plan/SECURITY_TRACK.md:36,44
**rule_id:** SEC-02
**Mapping:** OWASP-A02/A07 · CWE-798
**Confidence:** 96
**Evidence:** `git for-each-ref --contains 3dcc80d8` → `refs/heads/chore/audit-review-2026-09` **und** `refs/heads/chore/system-audit-2026-09`; Plan schreibt `--refs chore/system-audit-2026-09`.
**Risk:** Der Reward-Rewrite lässt den Leak-Blob auf dem aktuell ausgecheckten Branch erreichbar; `git gc` kann ihn nicht prunen, das Akzeptanzkriterium (`git grep` = nur README) bleibt verletzt.
**Recommendation:** `--refs` ohne Wert (alle Refs) oder explizit beide Branches; Akzeptanz auf `git for-each-ref --contains 3dcc80d8` = leer + `git cat-file -e 3dcc80d8` = Fehler verschärfen.

## Finding #2
**Severity:** HIGH
**File:** docs/audit/2026-09/review/plan/SECURITY_TRACK.md:36-44
**rule_id:** SEC-02
**Mapping:** OWASP-A02 · CWE-798
**Confidence:** 90
**Evidence:** Plan-Kommandofolge ohne `--force`, ohne Remote-Re-Add, ohne `git cat-file -e`-Unerreichbarkeitsnachweis; `filter-repo` entfernt `origin` und verweigert ohne `--force` bei nicht-frischem Klon.
**Risk:** Rewrite bricht mit Fehler ab oder hinterlässt `origin`-los; ohne `reflog expire`/`gc --prune=now` bleibt der Blob lokal auflösbar — das Kernziel (Blob entfernt) wird nicht belegt.
**Recommendation:** §5.2-Checkliste übernehmen; Unerreichbarkeit und Objekt-Vernichtung als messbare Akzeptanz aufnehmen.

## Finding #3
**Severity:** HIGH
**File:** docs/audit/2026-09/review/plan/SECURITY_TRACK.md:31-44
**rule_id:** SEC-02
**Mapping:** OWASP-A02 · CWE-798
**Confidence:** 88
**Evidence:** Plan: „Bundle-Backup zwingend" + `--replace-text`-Datei, beide mit Klartext-Secret; keine Aussage zu Verschlüsselung/Löschung/Retention.
**Risk:** Das Bundle ist ein neuer, vollständiger Klartext-Secret-Store; ohne Schutz/Löschung wird die Exposition verlängert bzw. verlagert.
**Recommendation:** Bundle als Secret klassifizieren (verschlüsselt, außerhalb Repo, ACL, begrenzte Retention); Ersatztextfile nach Rewrite sicher löschen; beides in die Akzeptanz.

## Finding #4
**Severity:** MEDIUM
**File:** docs/audit/2026-09/AUDIT_EVIDENCE/stack-seeds.md (untracked)
**rule_id:** SEC-02
**Mapping:** OWASP-A02 · CWE-798
**Confidence:** 92
**Evidence:** `git check-ignore -v …/stack-seeds.md` → exit 1 (nicht ignoriert); `git status --porcelain` → `?? …/stack-seeds.md`, `?? .kimi-code/`.
**Risk:** `git add -A` durch einen Agenten committet die Seed-Datei und ggf. `.kimi-code/`; `.kimi-code/` wurde zudem nie gescannt.
**Recommendation:** `stack-seeds.md` nach Nutzung sicher löschen; `.kimi-code/` in `.git/info/exclude` (lokal, nicht getrackt) aufnehmen und read-only scannen; Plan-Aussage „bleibt untracked" technisch absichern.

## Finding #5
**Severity:** HIGH
**File:** docs/audit/2026-09/review/plan/SECURITY_TRACK.md:17-29
**rule_id:** SEC-03
**Mapping:** OWASP-A01/A07 · CWE-798/613
**Confidence:** 90
**Evidence:** Agent-Pflicht bereits erzwungen (`authentication.py:552-558,619-646`); `models.py:154-162` `scope=write` = legacy ADMIN, `expires_at` Default `NULL`; `inventory_api_keys` existiert (read-only), wird im Plan nicht referenziert; Evidenz §1.6 listet 9 aktive `admin`-Keys inkl. seeded/e2e-Namen.
**Risk:** Der Plan adressiert die falsche Policy (Agent-Keys) und rotiert ggf. blind, wodurch laufende Clients/e2e-Kampagnen brechen, während die realen Legacy-ADMIN-Keys ohne Ablauf bestehen bleiben.
**Recommendation:** Legacy-`user`-Keys mit `scope ∈ {write,admin}` und `expires_at=NULL` als Policy-Ziel; `inventory_api_keys --format json` als Pflicht-Inventar; je Key Klassifikation (Test-Fixture/echter Client) + Entscheidung vor Widerruf.

## Finding #6
**Severity:** MEDIUM
**File:** docs/audit/2026-09/review/plan/SECURITY_TRACK.md:46-57
**rule_id:** SEC-05
**Mapping:** OWASP-A06/A02 · CWE-798
**Confidence:** 90
**Evidence:** Kein `.gitleaks.toml` im Plan; Rule `reqlo_[A-Za-z0-9]{40}` ohne `\b`; keine Versions-Klausel; kein CI-Ort; Historie-`detect` kollidiert mit `3dcc80d8`.
**Risk:** Reduzierte Erkennung (44-Zeichen-README vs. gezielte Allowlist) bzw. dauerhaft rotes Gate vor dem Rewrite → Gate wird abgeschaltet.
**Recommendation:** `{40}\b`, `.gitleaks.toml` mit `[extend] useDefault`, gitleaks-Version pinnen, Gate in GitHub Actions **und** Woodpecker, Ordering (a) Rewrite-first oder (b) datierte Allowlist dokumentieren.

## Finding #7
**Severity:** MEDIUM
**File:** docs/audit/2026-09/review/plan/SECURITY_TRACK.md:59-71
**rule_id:** SEC-02
**Mapping:** OWASP-A02 · CWE-798
**Confidence:** 90
**Evidence:** Plan-Denylist enthält Substring „`key`" → trifft `top_keys` (namentlich erhaltenes Feld) und `key_hash`; kein Modul/Test benannt.
**Risk:** Entweder Evidenz-Verlust (`top_keys` weg) oder unvollständige Redaktion; ohne konkretes Modul + Test ist das Gate nicht durchsetzbar.
**Recommendation:** Exakte Feldnamen-Denylist statt Substring; `top_keys` explizit erhalten; `scripts/audit/evidence.py` + Unit-Test als Pflicht; Roh-Body nie serialisieren.

## Finding #8
**Severity:** LOW
**File:** docs/audit/2026-09/review/plan/SECURITY_TRACK.md:73-81
**rule_id:** SEC-02
**Mapping:** OWASP-A02 · CWE-1392
**Confidence:** 93
**Evidence:** `deploy/docker-compose.yml:73,1020,1053` Default `honcho-dev-password` (Plan nennt `honcho`); `deploy/docker-compose.override.yml:13` `${DB_PASSWORD:-reqogniloom}` nicht erfasst.
**Risk:** Unpräziser Anker führt zu unvollständigem Fix; der Dev-Override-Default bleibt bestehen.
**Recommendation:** Anker auf `:73,1020,1053` + `override.yml:13`; `${VAR:?}`; Grep-Akzeptanz.

## Finding #9
**Severity:** LOW
**File:** docs/audit/2026-09/review/plan/SECURITY_TRACK.md:36-38
**rule_id:** SEC-02
**Confidence:** 86
**Evidence:** Plan nennt 3 Dokumente; `git grep -l 3dcc80d8` (HEAD) liefert ≥ 13 Dateien.
**Risk:** Nach dem Rewrite verweisen Audit-Dokumente auf einen nicht mehr existierenden Commit → Audit-Trail inkonsistent.
**Recommendation:** Sweep generieren (`git grep -l 3dcc80d8` → Dateiliste), danach `git grep -c 3dcc80d8` ⇒ 0 (bis auf datierte Historien-Notiz).

---

## 9. Gesamturteil / Empfehlung

Der Track ist **inhaltlich richtig geschnitten und korrekt priorisiert**, aber in
**SECTRACK-02** so nicht ausführbar (F1/F2/F3). Vor Ausführung sind F1, F2, F5 zu
beheben; F6/F7 sind für ein funktionierendes Gate erforderlich. **Kein Push** bis
zur verifizierten Option-A-Ausführung und aktivem Scan-Gate. `220` bleibt bis
dahin **Critical**; `ff77bbd0…` (unabhängig vom Rewrite) muss **zuerst** widerrufen
werden.

*Erstellt durch `security-auditor` am 2026-10-01. Read-only, keine Git-Mutation,
keine bestehenden Dateien geändert, keine Klartext-Secrets (nur maskierte IDs).*
