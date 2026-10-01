---
type: PLAN
scope: audit-review-2026-09-security-track
status: final
date: 2026-10-01
author_agent: planner
epic: SECTRACK — Offener Secret-Vorgang (P0)
branch: chore/audit-review-2026-09
parent: IMPLEMENTATION_PLAN.md
---

# Epic SECTRACK — Offener Secret-Vorgang (eigener P0-Track)

> **Push-Blocker.** Kein Push, bis SECTRACK-02 ausgeführt und verifiziert ist. Keine
> Klartext-Secrets in Doku/Plan; nur maskierte IDs. **F4:** `stack-seeds.md` und
> `.kimi-code/` sind **nicht** ignore-regeln (`git check-ignore` exit 1) → ein `git add -A`
> würde sie committen. `stack-seeds.md` nach Nutzung **sicher löschen**; `.kimi-code/` in
> `.git/info/exclude` aufnehmen und **read-only scannen** (bisher nie geprüfte
> Secret-Fläche). Kein Klartext-Secret in Doku.
>
> **Verifiziert/geschärft durch `plan/SECURITY_TRACK_REVIEW.md`** (security-auditor, 9
> Findings / 12 Plan-Lücken). Die dortigen materialen Korrekturen (F1–F10) sind unten
> eingearbeitet und im Zweifel maßgeblich: **F1** Rewrite-**Ref-Scope über beide lokalen
> Branches** (`chore/system-audit-2026-09` **und** der ausgecheckte
> `chore/audit-review-2026-09`; `--refs <eine Branch>` ist FALSCH), **F2**
> Rewrite-Vorbedingungen (`--force`, Reflog+GC, Remote-Re-Add, Unerreichbarkeitsbeweis),
> **F3** Bundle/Ersatztext als Klartext-Secret, **F4** `stack-seeds.md`/`.kimi-code/`,
> **F5** Policy-Ziel (Legacy-`user`-Keys mit `write`/ADMIN + `NULL`-Expiry), **F6**
> Scan-Gate-Ordering (History-`detect` erst nach dem Rewrite), **F7** Redactor-Denylist
> (exakte Feldnamen statt Substring `key`), **F8** Compose-Default
> `honcho-dev-password` + `:1020` + Override-Datei, **F10** SHA-Sweep (`git grep -l`, ≥13
> Dateien). **Aufwand:** verbindliche PT-Spannen `plan/EFFORT_ESTIMATES.md` §1. Ein Commit
> erfolgt erst durch den Orchestrator nach Validierung.

## SECTRACK-01 — Key-Rotation: `ff77bbd0…` + Legacy-`admin`-Keys (P0, W1)

- **Findings:** 220, 240
- **Ort:** `docs/audit/2026-09/AUDIT_EVIDENCE/stack-seeds.md` (`ff77bbd0-e99c-…`,
  untracked); aktive Keys am `admin`-Konto (Evidenz §1.6: 9 inkl. `ff77bbd0…`, alle
  `expires_at=NULL`, `workspace_ids=[]`); Produktionspfad `DELETE /api/v1/api-keys/<id>/`;
  Inventar `python manage.py inventory_api_keys --format json` (bereits vorhanden, bisher
  ungenutzt).
- **Korrektur (F5):** Die frühere Policy-Aussage „Agent-Keys benötigen `expires_at` und
  `workspace_ids`" beschreibt **bereits implementiertes** Verhalten
  (`authentication.py:552-558,619-646`). Das reale Ziel sind **Legacy-`user`-Keys** mit
  `scope ∈ {write, admin}` (= legacy ADMIN-Tier) und `expires_at=NULL`.
- **Zielverhalten:** `ff77bbd0…` **zuerst und unabhängig** widerrufen (nicht User löschen);
  die aktiven `admin`-Keys **inventarisieren und klassifizieren** (Test-Fixture vs. echter
  Client), dann widerrufen/rotieren; Default-Policy für Legacy-`user`-Keys nachziehen
  (`principal_type=agent` erzwingen bzw. `expires_at`+`workspace_ids` für
  `scope∈{write,admin}` Pflicht).
- **Akzeptanz:** `POST /mcp/` mit `ff77bbd0…` ⇒ **401** (zwei Messungen, ≥60 s Abstand);
  `revoked_at` **NOT NULL** (DB-`SELECT`; **nicht** `is_active` — read-only Property);
  `list_api_keys` liefert den Key mit `revoked == true` (die API liefert auch widerrufene
  Keys); Inventar-Vor-/Nachlauf dokumentiert; Policy-Test: neuer Key mit `scope=write` +
  `expires_at=NULL` wird auf dem Automatisierungspfad **abgelehnt** (rot vor Fix).
- **Test:** Live-Widerrufsbeleg (401 ×2 + DB) + `inventory_api_keys` + pytest
  (Expiry/Fence-Pflicht). · **Aufwand:** S · **Risiko/Rollback:** blinde Rotation bricht
  laufende Clients/e2e-Kampagnen (`MCP-UI-Campaign-REQ129…`, `admin_key`, `read_key`) →
  Inventar + Ersatzkeys vorher; `revoke` ist **irreversibel**, Rollback nur per
  Neu-Ausstellen. · **Deps:** — (nicht von SECTRACK-02 abhängig) · **ADR:** ii (Policy)

## SECTRACK-02 — History-Blob Option A (`git filter-repo`, Bundle-Backup) (P0, W1)

- **Findings:** 220
- **Ort:** Commit `3dcc80d8` (nie gepusht, `merge-base --is-ancestor origin/main` exit 1),
  **erreichbar über ZWEI lokale Branches**: `chore/system-audit-2026-09` **und** den
  aktuell ausgecheckten `chore/audit-review-2026-09`; `--replace-text` gegen Blob-Ebene;
  `docs/audit/.../wp1d-*.json`.
- **Korrektur (F1 — blockierend):** Der frühere Aufruf
  `git filter-repo --replace-text … --refs chore/system-audit-2026-09` ist **FALSCH** —
  da `3dcc80d8` auch Vorfahre des aktuellen Branch ist, bliebe der Leak-Blob am HEAD
  erreichbar, `git gc` könnte ihn nicht prunen und `git grep` am HEAD bliebe positiv.
- **Zielverhalten:** `git filter-repo --replace-text … --force` über **alle Refs** (kein
  `--refs <eine Branch>`); danach `git reflog expire --expire=now --all` +
  `git gc --prune=now`; Remote-Wiederanbindung **ohne Push**; anschließend
  **SHA-Verweis-Sweep generiert** (`git grep -l 3dcc80d8` → ≥13 Dokumente, nicht die drei
  früher genannten; bewusste datierte Historie-Notiz ausgenommen).
- **Korrektur (F3):** **Bundle und Ersatztextdatei sind selbst Klartext-Secret-Stores** —
  Bundle liegt **außerhalb** des Repos, ist als Secret klassifiziert und verschlüsselt/
  ACL-geschützt; Ersatztextdatei nach dem Rewrite **sicher löschen**.
- **Zielverhalten (Fortsetzung):** nur ausgeführt, wenn **parallele Agents beendet** sind
  und `git status` nur bekannte untracked Dateien zeigt (`.kimi-code/`, `stack-seeds.md`,
  `EFFORT_ESTIMATES.md`).
- **Akzeptanz:** `git for-each-ref --contains 3dcc80d8` ⇒ **leer**;
  `git cat-file -e 3dcc80d8` ⇒ **Fehler** (Objekt nach `gc` weg);
  `git log --all -G 'reqlo_[A-Za-z0-9]{40}\b'` ⇒ 0; Baum-Ebene über alle erreichbaren
  Commits (`git rev-list --all` + `git grep`) ⇒ 0 in `docs/audit/**` (README-Beispiel ist
  44 Zeichen und wird durch `\b` nicht erfasst); Bundle außerhalb Repo + geschützt;
  Ersatztextdatei gelöscht; `git grep -c 3dcc80d8` ⇒ 0 (außer datierter Historien-Notiz).
- **Test:** die Verifikationskommandos als Skript, Ergebnis als Evidenzdatei via Redactor. ·
  **Aufwand:** S · **Risiko/Rollback:** umschreibt alle ~30 lokalen Commit-SHAs; **Revert
  nur aus dem Bundle**; Restkanäle außerhalb `filter-repo` (CI-Caches, IDE-History,
  Shadow-Copies, Backups) werden **nicht** beseitigt. · **Deps:** keine fachliche;
  **Reihenfolge** zu SECTRACK-03 siehe unten. · **ADR:** —

## SECTRACK-03 — Secret-Scan-Gate (P0, W1)

- **Findings:** 224, 220
- **Ort:** kein `.pre-commit-config.yaml`; `rg gitleaks|trufflehog|detect-secrets` = 0;
  `.woodpecker.yml:76-80` (nur Dependency-Scan)
- **Zielverhalten (F6 geschärft):** Pre-Commit `gitleaks protect --staged --redact` +
  **Custom-Regel `reqlo_[A-Za-z0-9]{40}\b`** (Standardregeln finden den Projekt-Key nicht;
  `\b` verhindert, dass das 44-Zeichen-README-Beispiel erfasst wird) in `.gitleaks.toml`
  (`[extend] useDefault=true`); gitleaks-Version **exakt pinnen**; CI-`detect` in **GitHub
  Actions und Woodpecker** (Arbeitsbaum **und** History); schmale, begründete Allowlist
  (je Eintrag Datum + Grund — keine pauschalen Testverzeichnisse).
- **Ordering (F6):** History-`detect` ist vor SECTRACK-02 **sofort rot** (Commit
  `3dcc80d8`). Zulässig nur **(a)** Rewrite zuerst, dann History-Scan ohne Ausnahme, oder
  **(b)** datierter Allowlist-Eintrag für `3dcc80d8`, der nach dem Rewrite **entfernt**
  wird. Ohne diese Entscheidung wird das Gate beim ersten Lauf rot und faktisch abgeschaltet.
- **Akzeptanz:** Ein Test-Commit mit Dummy-`reqlo_`-Key (40 Zeichen) wird **blockiert**;
  CI-Step läuft; `README.md` und die 9 Test-Fixtures werden **nicht** gemeldet; bekannte
  False Positives sind datiert in der Allowlist dokumentiert.
- **Test:** Negativ-/Positiv-Probe des Hooks + CI-Lauf. · **Aufwand:** S ·
  **Risiko/Rollback:** Fehlalarme blockieren Commits → Allowlist pflegen; Gate im Zweifel
  job-spezifisch, aber nie dauerhaft abschaltbar. · **Deps:** Reihenfolge zu SECTRACK-02 · **ADR:** —

## SECTRACK-04 — Evidenz-Redactor + Cleanup-Checkliste (P0, W1)

- **Findings:** 239, 220
- **Ort:** Ursache `AUDIT_EVIDENCE/*` (`top_keys` vs. `body_head`);
  `wp1d-cleanup-verification.md` (prüfte User-Löschung statt Key-Widerruf)
- **Zielverhalten (F7 geschärft):** konkreter Wrapper (z. B. `scripts/audit/evidence.py`)
  `safe_dump(response)`: serialisiert **nie** den Roh-Body (`body_head` entfällt ersatzlos),
  schreibt nur `status`/`top_keys`/`value_types`/`body_len`/`redacted_value_keys`; **exakte
  Feldnamen-Denylist** (normalisiert, case-insensitive) statt Substring `key` — sonst wird
  ausgerechnet `top_keys` zerstört. Denylist: `plaintext`, `token`, `access_token`,
  `refresh_token`, `password`, `secret`, `api_key`, `apikey`, `key_hash`, `private_key`,
  `client_secret`, `authorization`, `cookie`, `session`. `top_keys` ist ein
  Schlüssel**namen**-Feld und bleibt erhalten. Cleanup-Checkliste geschärft: je Key
  widerrufen → **zwei** 401-Messungen → `revoked_at` NOT NULL → `list_api_keys` liefert
  `revoked == true` (nicht „nicht in Liste": die API liefert auch widerrufene Keys) →
  `rg` 0 Treffer → Key-Register (id, name, principal_type, scope, Zeitstempel).
- **Akzeptanz:** Unit-Test mit synthetischer Response `{plaintext, token, password, secret,
  key_hash, name, id, top_keys}` ⇒ Output enthält **keinen** dieser Werte, **aber**
  `top_keys` und `name`; `rg 'reqlo_[A-Za-z0-9]{40}\b' docs/audit/` ⇒ 0; Checkliste ist
  Teil der Audit-Task-Definition.
- **Test:** Unit-Test des Redactors (beweist auch die Über-Redaktions-Grenze). ·
  **Aufwand:** M · **Risiko/Rollback:** Redactor zu aggressiv → exakte Namen statt
  Substring. · **Deps:** — · **ADR:** —

## SECTRACK-05 — Hardcoded Deploy-Credentials (P2, W3)

- **Findings:** 241 (=148, Duplikat), 148
- **Ort (F8 korrigiert):** `deploy/verify-backup-command.sh:90,103` (`POSTGRES_PASSWORD=…`);
  `deploy/docker-compose.yml:73,1020,1053` — tatsächlicher Default ist
  **`HONCHO_DB_PASSWORD:-honcho-dev-password`** (nicht `honcho`; `:1020` zusätzlich);
  nicht erfasst: `deploy/docker-compose.override.yml:13`
  `${DB_PASSWORD:-reqogniloom}` mit Kommentar „Weak password OK for dev" (getrackt).
- **Zielverhalten:** `${VAR:?}`-Pflichtvariablen statt Klartext/Defaults; Compose-Defaults
  entfernen.
- **Akzeptanz:** `docker compose config` ohne gesetzte Variable schlägt mit klarer Meldung
  fehl; `rg 'HONCHO_DB_PASSWORD:-' deploy/` ⇒ 0; `rg 'POSTGRES_PASSWORD=|PASSWORD=' deploy/verify-backup-command.sh` ⇒ 0;
  kein Klartext-Passwort getrackt. · **Test:** Compose-Config-Test + Grep. · **Aufwand:** S ·
  **Risiko/Rollback:** Deployment muss Variable setzen → dokumentiert. · **Deps:** — · **ADR:** —
