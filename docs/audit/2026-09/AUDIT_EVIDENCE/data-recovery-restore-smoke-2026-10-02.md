---
type: EVIDENCE
scope: DATA-01 / DATA-02 — ADR-012 Umsetzung: Skript-Rückbau, atomarer Restore, Restore-Smoke
status: final
date: 2026-10-02
author_agent: database-engineer
branch: fix/data-recovery-integrity
---

# DATA-01 / DATA-02 — Evidenz: Sidecar-Restore, atomar und isoliert

**Ergebnis in einem Satz: `scripts/backup.sh` und `scripts/restore.sh` sind
entfernt; der Restore läuft jetzt gegen eine isolierte Zieldatenbank in einer
einzigen Transaktion (Fehler ⇒ Rollback) und ist als wiederholbarer Smoke
(`deploy/verify-restore.sh`) verankert — 15/15 Tabellen, 0 Fehler, Rollback
nachgewiesen; der echte Sidecar-Dump restaurierte 100/100 Tabellen mit 0 Fehlern.**

---

## 1. Umgesetzte Findings

| Finding | Schwere (Review) | Umsetzung |
|---------|------------------|-----------|
| `AUD-2026-09-122` | High (dead legacy code) | `scripts/backup.sh` entfernt — der tote `docker-compose.backup.yml`-Pfad existiert nicht mehr. |
| `AUD-2026-09-123` | Critical | `scripts/restore.sh` entfernt; ersetzt durch atomaren Runbook-Befehl (`docs/DEPLOY_RUNBOOK.md` §6.3) und Smoke `deploy/verify-restore.sh`. |
| `AUD-2026-09-124` | High (Format/Ort) | Format-/Ortsvertrag dokumentiert (`.sql.gz` im Named Volume `postgres_backup_data`, `.last_backup_status`); kein `./backups`-Pfad mehr. |
| `AUD-2026-09-127` | High (nicht atomar) | Restore nutzt `psql --single-transaction -v ON_ERROR_STOP=1` in eine isolierte Zieldatenbank; kein `--clean --if-exists` auf der Live-DB. Negativfall beweist Rollback. |
| `AUD-2026-09-128` | High (Retention/Off-Host) | Off-Host-Ziel konfigurierbar via `deploy/docker-compose.offhost.yml` + `BACKUP_OFFHOST_DIR`; Restrisiken (Verschlüsselung, Remote-Retention, Medien, Minimal-Variante) benannt. |
| `AUD-2026-09-345` (=123) | Medium | Duplikat von 123; Matrix-Widerspruch bleibt `DOC-01`, hier nicht geändert. |

---

## 2. Entfernte / geänderte / neue Dateien

**Entfernt:** `scripts/backup.sh`, `scripts/restore.sh`

**Neu:**
- `deploy/verify-restore.sh` — atomarer Restore-Smoke (Gate)
- `deploy/docker-compose.offhost.yml` — optionales Off-Host-Overlay
- `docs/audit/2026-09/AUDIT_EVIDENCE/data-recovery-restore-smoke-2026-10-02.md` (dieses Dokument)

**Geändert:**
- `deploy/docker-compose.yml` — dormanter Off-Host-Export-Hook im Sidecar (standardmäßig aus)
- `docs/DEPLOY_RUNBOOK.md` — §6 Format-/Ortsvertrag, Off-Host, atomarer Restore; Gate-Summary
- `README.md` — Backup-/Restore-Abschnitt auf den Runbook-Befehl umgestellt
- `deploy/README.md` — Restore-Smoke referenziert
- `.env.example` — Off-Host-Variablen + Formatvertrag
- `scripts/build.sh` — toten Verweis entfernt
- `.gitignore`, `backend/.dockerignore`, `.meta-config/project.yaml` — Verweise auf die entfernten Skripte bereinigt

---

## 3. Restore-Smoke — echtes Ergebnis

Kommando: `deploy/verify-restore.sh` (Git Bash, Windows/Docker Desktop)

```
PASS  sidecar command block exited 0
PASS  published dump: reqogniloom_20261002_060422.sql.gz
PASS  dump contains 15 COPY block(s) (>= 15)
PASS  restore exited 0
PASS  restore log: 0 error line(s)
PASS  source holds 15/15 tables
PASS  restored target holds 15/15 tables
PASS  all 15/15 table row counts are identical
PASS  pgvector column restored as vector(3)
PASS  injected error aborted the restore (exit 3)
PASS  failed restore left 0 tables — transaction rolled back, no half-restored DB

atomic restore smoke: ALL CASES PASSED (15/15 tables, 0 errors, rollback verified)
```

Der Smoke extrahiert den **echten** `postgres-backup`-Befehl aus
`deploy/docker-compose.yml` (er kann nicht gegen einen anderen Block bestehen),
erzeugt daraus einen Dump aus einer 15-Tabellen-Quelle mit bekannten
Zeilenzahlen (inkl. `vector(3)`-Spalte), restauriert ihn atomar in eine
isolierte Wegwerf-Ziel-Instanz und vergleicht alle Zeilenzahlen. Der Negativfall
injiziert `SELECT 1/0` in dieselbe Transaktion und weist nach, dass keine Tabelle
zurückbleibt.

## 4. Echter Sidecar-Dump — isolierter Restore (Live-DB unberührt)

Dump: `reqogniloom_20261002_045816.sql.gz` (100 COPY-Blöcke, Marker `status=ok`)
aus dem Volume `ai-native-reqflow-poc_postgres_backup_data`.

```
RESTORE_EXIT=0
ERROR_LINES=0
LIVE_TABLES=100
TARGET_TABLES=100
COPY_BLOCKS=100
ROWCOUNT_MATCH_TABLES=95/100
```

- **100/100 Tabellen** restauriert, **0 Fehler**.
- 95/100 Zeilenzahlen exakt identisch. Die 5 Abweichungen sind sämtlich
  `live > restored` (z. B. `we_item_state` 6054 vs. 3316, `audit_entry`
  8175 vs. 8167) und damit **Snapshot-Drift** seit 04:58, kein Datenverlust —
  dieselbe Erklärungsart wie `at_refresh_token −10` im WP-1c-Protokoll.
- Die Live-DB wurde ausschließlich per `SELECT count(*)` gelesen; die
  Ziel-Instanz war ein eigener Wegwerf-Container mit privatem Netz und wurde
  danach entfernt.

## 5. Off-Host-Export — verifiziert

Mit gebundenem Off-Host-Verzeichnis und `BACKUP_OFFHOST_ENABLED=true`:

```
[backup] exported reqogniloom_20261002_060402.sql.gz to off-host /offhost
LOCAL=1
OFFHOST_FILES=1
```

Der lokale Dump liegt weiterhin im Volume, die Kopie auf dem Off-Host-Mount.

---

## 6. Benannte Restrisiken (ADR-012, nicht durch diese Einheit gelöst)

1. **Keine Verschlüsselung:** `gzip` ist Kompression, keine Verschlüsselung; auch
   die Off-Host-Kopie ist Klartext.
2. **Remote-Retention fehlt:** gepruned wird nur das lokale Volume.
3. **Off-Host-Ziel nicht verifizierbar:** das Repo kann nicht prüfen, ob
   `BACKUP_OFFHOST_DIR` wirklich ein separates Filesystem/Host ist.
4. **42-h-Horizont** im Default (`7 × 6 h`) — für einen Totalausfall kurz.
5. **Medien/Uploads** sind nicht im Dump; **Minimal-Variante** hat keinen Sidecar.
6. **Matrix-Widerspruch `AUD-2026-09-345`** bleibt offen (Auflösung `DOC-01`).

*Keine Secrets, keine Zugangsdaten in diesem Dokument.*
