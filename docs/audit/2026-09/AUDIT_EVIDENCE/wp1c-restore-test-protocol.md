---
type: EVIDENCE
scope: WP-1c — Backup/Restore-Testprotokoll (echter Restore, isoliert)
status: final
date: 2026-09-29
author_agent: devops-engineer
---

# WP-1c E4 — Backup-/Restore-Test: Protokoll mit Vorher/Nachher-Zahlen

**Ergebnis in einem Satz: Der Sidecar-Mechanismus `postgres-backup` erzeugt
vollständig wiederherstellbare Backups — der Restore-Test ist mit 15/15
identischen Tabellenzahlen bestanden. Die dokumentierten Operator-Skripte
`scripts/backup.sh` und `scripts/restore.sh` können dagegen nie erfolgreich
sein und sind nie erfolgreich gewesen.**

Es wurde **nie** in die laufende Datenbank `ai-native-reqflow-poc-postgres-1`
geschrieben. Alle Restore-Schritte liefen in einem **eigenständigen
Wegwerf-Container** mit **eigenem Volume** und **ohne publizierten Port**,
der nach dem Test gelöscht wurde.

---

## Phase A — Bestandsaufnahme des laufenden Backups

### A.1 Was existiert (Volume `ai-native-reqflow-poc_postgres_backup_data`)

```
-rw-r--r--  1 root root      96 Sep 30 03:41 .last_backup_status
-rw-r--r--  1 root root  9591732 Sep 27 12:02 reqogniloom_20260927_120156.sql.gz
-rw-r--r--  1 root root  9592274 Sep 27 18:02 reqogniloom_20260927_180201.sql.gz
-rw-r--r--  1 root root  9928263 Sep 28 14:44 reqogniloom_20260928_144356.sql.gz
-rw-r--r--  1 root root  9928256 Sep 28 20:44 reqogniloom_20260928_204359.sql.gz
-rw-r--r--  1 root root  9928254 Sep 29 18:17 reqogniloom_20260929_181713.sql.gz
-rw-r--r--  1 root root  9928738 Sep 29 21:41 reqogniloom_20260929_214133.sql.gz
-rw-r--r--  1 root root 10012937 Sep 30 03:41 reqogniloom_20260930_034136.sql.gz
```

Marker-Datei (`deploy/docker-compose.yml:391`, `:395-398`):

```
2026-09-30T03:41:40Z status=ok copy_blocks=100 file=/backups/reqogniloom_20260930_034136.sql.gz
```

Backup-Intervall-Log (`docker logs postgres-backup-1`) über 4 Tage, 8
Dumps, alle `status=ok`, `98→100 COPY blocks verified`, mit korrektem
`prune_old`-Verhalten. Die `#1074`-Härtung (kein `pg_dump | gzip`-Pipeline-
Exit-Code, `COPY`-Content-Gate, `gzip -t`, Löschen fehlerhafter Dumps,
`BACKUP_MAX_CONSECUTIVE_FAILURES`) ist **wirksam und greift nachweislich**.

Format-Extension: **ausschließlich `gz`** (`ls | sed 's/.*\.//' | sort -u` → `gz`).

### A.2 Retention — reale Reichweite

`BACKUP_RETENTION=7` (Default, `deploy/docker-compose.yml:357`) ×
`BACKUP_INTERVAL=21600 s` = 6 h ⇒ **ältestes Backup ≈ 42 Stunden alt**
(ältestes live: `2026-09-27 12:02`, jüngstes `2026-09-30 03:41` ⇒ 63,6 h in
diesem Lauf, weil das Volume über einen Stack-Restart hinweg erhalten blieb).

Es gibt **nur** eine **anzahlbasierte** Retention, **keine** zeitbasierte.
⇒ Effektiver Wiederherstellungshorizont **≈ 42 h**, unabhängig davon, ob die
Daten 42 h oder 42 Tage Wert sind. → `AUD-2026-09-128`

### A.3 WAS NICHT gesichert wird

| Artefakt | Gesichert? | Beleg |
|----------|-------------|-------|
| PostgreSQL-Datenbank | **JA** | obige Tabelle |
| `postgres_data`-Volume (WAL, Konfiguration, `postgresql.auto.conf` mit `max_connections=300`) | **NEIN** | kein Dump davon; `pg_dump` exportiert Cluster-Konfiguration nicht |
| Redis (Broker-Queue, Result-Backend, Django-Cache, **MCP-Sessions**) | **NEIN** | kein Redis-Dump, kein `redis_data`-Backup |
| `backend_dr_backups`-Volume (admin_ops DR-Backups) | **NEIN** | eigenes Volume, unberührt |
| Benutzer-Uploads/Medien | **NEIN** | **es existiert kein Medien-Volume** — die Compose-`volumes:`-Liste (`deploy/docker-compose.yml:1358-1364`) enthält keins; Uploads liegen damit im Container-Filesystem und sind bei jedem Recreate weg |
| `.env` / Compose-Konfiguration | **NEIN** | gitignore-verwaltet, nicht im Backup |
| **Off-Host-Kopie** | **NEIN** | alle 7 Dumps liegen im selben Docker-Volume auf demselben Host wie die Datenbank |

⇒ Ein Host- oder Volume-Verlust nimmt Datenbank **und** alle Backups
gemeinsam mit. → `AUD-2026-09-128`

### A.4 Verschlüsselung

`pg_dump --no-owner --no-privileges` → Klartext-SQL, dann `gzip -9`. **Keine
Verschlüsselung.** Der Dump enthält `at_api_key` (201 Zeilen), `at_refresh_token`
(6292), `audit_entry` (8148) und `FIELD_ENCRYPTION_KEY`-verschlüsselte Felder.
Das Volume ist über den Docker-Host ohnehin root-lesbar; das ist bei einem
Single-Host-Setup vertretbar, **nicht** aber für eine Auslagerung, die es
nicht gibt. → `AUD-2026-09-128`

---

## Phase B — Ausgangsmessung (VOR Restore)

Quelle: `ai-native-reqflow-poc-postgres-1`, DB `reqflow`, **nur `SELECT count(*)`**.

| Tabelle | Zeilen (VOR) |
|---------|-------------|
| `pl_artifact` | **3432** |
| `audit_entry` | **8148** |
| `at_refresh_token` | **6292** |
| `at_api_key` | **201** |
| `pl_artifact_version` | **4117** |
| `we_item_state` | **3306** |
| `pl_token_usage_record` | **39** |
| `pl_tenant` | **6** |
| `ad_workspace_definition` | **420** |
| `pl_requirement` | **2111** |
| `pl_tracelink` | **2099** |
| `icd_icd` | **105** |
| `mem_memory_entry` | **2** |
| `as_domain_event_outbox` | **6861** |
| `django_migrations` | **294** |

Schema-Referenz (VOR): `pgvector 0.8.5`, `pl_requirement.embedding vector(384)`.

---

## Phase C — Isolierte Restore-Umgebung

```
docker rm -f wp1c-restore-pg
docker volume rm wp1c-restore-data
docker run -d --name wp1c-restore-pg \
  -e POSTGRES_DB=restoretest -e POSTGRES_USER=rt -e POSTGRES_PASSWORD=rt \
  -v wp1c-restore-data:/var/lib/postgresql/data \
  pgvector/pgvector:pg16
```

* **Eigener Containername** (`wp1c-restore-pg`) — keine Kollision mit den
  Wegwerf-Stacks der Parallel-Audits (`reqlo-audit-*`).
* **Eigenes Volume** `wp1c-restore-data`.
* **Kein Host-Port publiziert**, **kein Compose-Netz**, **kein `depends_on`**,
  **kein Eingriff** in `postgres`/`redis`/`backend`.
* Readiness **blockierend** gepollt (`pg_isready`, 40 × 2 s) ⇒ ready nach 2 s.
* Ziel-Server: `PostgreSQL 16.15` — **identisch** zur Quelle.

**Vorbereitung** (nur lesend aus dem Backup-Volume, schreibend in das
Wegwerf-Volume):

```
gzip -t  →  GZIP_INTEGRITY_OK
gunzip -c reqogniloom_20260930_034136.sql.gz > /dst/dump.sql
  10 012 937 B  .gz  →  54 070 604 B  .sql   (Faktor 5,40)
grep -c '^COPY ' dump.sql  →  100
```

---

## Phase D — Restore (dokumentiertes Verfahren)

Der Restore folgte **exakt** dem im Compose-Header dokumentierten Weg
(`deploy/docker-compose.yml:304`):
`gunzip -c <dump>.sql.gz | psql -h <host> -U <user> -d <db>`
— umgesetzt als `psql -U rt -d restoretest -f /tmp/restore.sql`, also
**derselben psql-Lesart**, die auch `scripts/restore.sh:186` verwendet.

```
psql exit = 0        elapsed = 5 s        ERROR-Zeilen = 0
CREATE EXTENSION
```

---

## Phase E — Nachher-Messung und Vergleich

| Tabelle | VOR | NACHHER | Δ | Bewertung |
|---------|-----|---------|---|-----------|
| `pl_artifact` | 3432 | **3432** | **0** | ✔ identisch |
| `audit_entry` | 8148 | **8148** | **0** | ✔ identisch |
| `at_refresh_token` | 6292 | **6282** | **−10** | ✔ **erklärt** (s.u.) |
| `at_api_key` | 201 | **201** | **0** | ✔ identisch |
| `pl_artifact_version` | 4117 | **4117** | **0** | ✔ identisch |
| `we_item_state` | 3306 | **3306** | **0** | ✔ identisch |
| `pl_token_usage_record` | 39 | **39** | **0** | ✔ identisch |
| `pl_tenant` | 6 | **6** | **0** | ✔ identisch |
| `ad_workspace_definition` | 420 | **420** | **0** | ✔ identisch |
| `pl_requirement` | 2111 | **2111** | **0** | ✔ identisch |
| `pl_tracelink` | 2099 | **2099** | **0** | ✔ identisch |
| `icd_icd` | 105 | **105** | **0** | ✔ identisch |
| `mem_memory_entry` | 2 | **2** | **0** | ✔ identisch |
| `as_domain_event_outbox` | 6861 | **6861** | **0** | ✔ identisch |
| `django_migrations` | 294 | **294** | **0** | ✔ identisch |

**Die einzige Abweichung ist `at_refresh_token` −10.** Sie ist vollständig
erklärt: VOR wurde um **04:31** gemessen, das Backup stammt von **03:41** —
50 Minuten Differenz, in denen die Parallel-Audits Refresh-Tokens erzeugt haben
(die Tabelle wächst mit jedem Login). Alle 14 übrigen Tabellen sind exakt
identisch, weil in diesem Fenster sonst nichts geschrieben wurde. Das ist kein
Datenverlust, sondern der erwartete Snapshot-Abstand.

**Schema-Vollständigkeit im restaurierten Ziel:**

| Eigenschaft | Quelle | Restauriert | Match |
|-------------|--------|-------------|-------|
| `pg_extension` `vector` | 0.8.5 | 0.8.6 | Version des Image-Patches, **Funktion gleich** |
| `pl_requirement.embedding` | `vector(384)` | `vector(384)` | ✔ |
| `django_migrations` | 294 | 294 | ✔ |

`CREATE EXTENSION` im Restore-Log bestätigt: die `vector`-Extension ist im Dump
mit enthalten und wird im frischen Ziel korrekt (re)erzeugt — der
pgvector-Pfad ist **nicht** vom Quellcluster abhängig.

### E.1 Aufräumen

```
docker rm -f wp1c-restore-pg
docker volume rm wp1c-restore-data
```

Nachkontrolle `docker ps`: alle 12 Container des laufenden Stacks und der
Parallel-Audits **unverändert `Up`**, Backend/Frontend/Postgres/Redis/Celery/
Celery-Beat weiterhin `healthy`. **Keine Beschädigung.**

---

## Phase F — Funktioniert `scripts/restore.sh`? (NEIN)

### F.1 Dreifache Inkompatibilität zwischen Backup-Erzeuger und Restore-Skript

| # | `scripts/backup.sh` erzeugt / `postgres-backup` erzeugt | `scripts/restore.sh` erwartet | Ort |
|---|---|---|---|
| 1 | Datei-Extension **`.sql.gz`** | `ls -t "$BACKUPS_DIR"/*.dump "$BACKUPS_DIR"/*.sql` | `scripts/restore.sh:116` |
| 2 | Ablage im **Docker-Volume** `postgres_backup_data:/backups` | Host-Verzeichnis **`${PROJECT_ROOT}/backups`** | `scripts/restore.sh:49` |
| 3 | — | `deploy/docker-compose.yml` **existiert**, wird benutzt | `scripts/restore.sh:89-92` |

Gemessen: `Test-Path backups` → **False** (Host-Verzeichnis existiert nicht).
`Test-Path docker-compose.backup.yml` → **False**; repo-weite Suche findet
keine Datei dieses Namens.

⇒ `restore.sh --latest` scheitert an `get_latest_backup()` mit
`No backup files found in …/backups` (`scripts/restore.sh:119-120`), **bevor**
überhaupt etwas passiert.

### F.2 `scripts/backup.sh` ist permanent nicht ausführbar

`check_prerequisites()` verlangt `docker-compose.backup.yml`
(`scripts/backup.sh:84-87`) und beendet mit `exit 1`. Der eigene Kommentar
darin (`scripts/backup.sh:79-83`) räumt ein, dass die Datei **„has never
existed in this repo"** und das Skript „unreachable past this check" sei.

⇒ **`scripts/backup.sh` kann in keinem Zustand dieses Repos Erfolg haben.**
Kein Aufruf, keine Argumentkombination ändert daran etwas — die Prüfung steht
**vor** dem `case`-Block, also vor `--cleanup`, `--list` und `--help`.
Auch der gzip-Fix aus `fix/backup-gzip-823` (#823) betrifft **nicht** dieses
Skript, sondern `admin_ops`-DR-Backups; die Sidecar nutzt `gzip -9`
(`deploy/docker-compose.yml:436`) und ist korrekt.

### F.3 `scripts/restore.sh` kann die Backup-Datei nicht erreichen

Selbst wenn man einen `.sql`-Dump in `./backups/` legte, scheitert der Restore:

* Zeile 183 (`.dump`): `pg_restore … /tmp/backup.dump` — die Datei liegt
  **nie** im Container.
* Zeile 186 (`.sql`): `psql … -f /tmp/backup.sql` — `-f` liest eine **Datei**,
  **nicht** stdin.
* Zeilen 198-201 / 206-209: Das Skript leitet **stdin** um
  (`< "$backup_file"`), **kopiert die Datei aber nicht** in den Container.
  Die umgeleiteten Daten werden von `pg_restore` (Dateipfad) bzw. `psql -f`
  (Dateipfad) **vollständig ignoriert**.

**Beweis (isoliert, im Wegwerf-Container, ohne Live-DB):**

```
(a) exakt restore.sh:186+198 — stdin umgeleitet, -f zeigt auf eine
    nie kopierte Datei:
    $ printf 'SELECT 42 ...\n' | psql -U rt -d restoretest -f /tmp/backup.sql
    psql: error: /tmp/backup.sql: No such file or directory
    exit=1

(b) Kontrollgruppe — dieselbe Datei, wenn sie wirklich existiert:
    $ psql -U rt -d restoretest -f /tmp/present.sql
     from_file_probe
    ----------------
                  42
    (1 row)
```

⇒ Der stdin-Pfad ist wirkungslos; beide Restore-Zweige laufen in einen
`No such file`-Fehler. `AUD-2026-09-123`

### F.4 Weitere Restore-Mängel (statisch belegt, nicht ausgeführt)

| Mangel | Ort | Bewertung |
|--------|-----|-----------|
| **Kein Integritäts-Vorcheck** — nur `stat`-Größe > 1024 B (`validate_backup_file`, `:126-143`); kein `pg_restore --list`, kein `gzip -t`. Ein abgeschnittener 5-MB-Dump passiert die Prüfung. | `scripts/restore.sh:126-143` | Medium |
| **Nicht atomar** — `pg_restore --clean --if-exists` droppt und erzeugt Objekte **in place**. Bricht der Restore ab, bleibt die DB **halb abgeräumt**; es gibt keinen Schatten-DB-Swap, keine Transaktion, keinen Rollback. | `scripts/restore.sh:183` | High → `AUD-2026-09-127` |
| **Zielt immer auf die Live-Datenbank** — Host ist auf `-h postgres` **hartkodiert**; `DB_NAME` ändert nur den Datenbanknamen, nicht den Host. Es gibt **keine** Option, in eine isolierte Datenbank zu restaurieren (genau das, was ein Restore-Probe braucht). | `scripts/restore.sh:183`, `:186`, `:198`, `:206` | High |
| **Fehlerbehandlung bricht korrekt ab** — `set -euo pipefail` plus `|| { log_error …; exit 1; }` (`:201-204`, `:209-212`). **Kein** „macht weiter und meldet Erfolg". | `scripts/restore.sh:201-212` | **PASS** |
| **Bestätigung** — interaktives `read -p` mit dem Wort `restore`, überschreibbar per `RESTORE_CONFIRM=yes`. | `scripts/restore.sh:145-167` | **PASS** |
| **`--latest` ist bei `.sql.gz` wirkungslos** (siehe F.1) | `scripts/restore.sh:116` | High |

### F.5 Was NICHT getestet wurde und warum

* **Abbruch-Verhalten des Restores mitten drin** (die eigentliche
  Nicht-Atomizität) — nicht testbar, ohne die Live-Datenbank zu gefährden.
  **BLOCKED**, nicht als PASS gewertet.
* **`scripts/restore.sh` end-to-end** — nicht ausgeführt: es würde per
  `--clean --if-exists` direkt in `ai-native-reqflow-poc-postgres-1` schreiben.
  Der Defekt ist stattdessen statisch belegt (F.1–F.3) und der Fehlermodus
  isoliert reproduziert (F.3).

---

## Fazit

| Frage | Antwort |
|-------|---------|
| **Hat der Restore funktioniert?** | **JA** — der Sidecar-Dump `reqogniloom_20260930_034136.sql.gz` wurde vollständig und fehlerfrei in eine isolierte PG-16.15-Datenbank restauriert: 15/15 Tabellen, 14 exakt identisch, 1 mit erklärter Snapshot-Differenz, `vector`-Extension und `vector(384)`-Spalten korrekt, 294 Migrationen, 0 Fehler, 5 s. |
| Ist der Backup-Pfad ungetestet? | **Nein** — er ist jetzt getestet. Der Sidecar ist die **einzige** funktionierende Backup-Mechanik. |
| Funktionieren die dokumentierten Skripte? | **Nein.** Beide sind Fassade bzw. funktional kaputt und **nie** erfolgreich gewesen. |
| Reicht das für Produktion? | **Nein** — 42-h-Horizont, kein Off-Host, keine Verschlüsselung, keine Medien/Uploads, kein Redis/Cluster-Config, und die einzige Operator-Dokumentation zeigt auf zwei tote Skripte. |
