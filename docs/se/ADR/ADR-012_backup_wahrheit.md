---
adr_id: ADR-012
title: "Sidecar ist die verbindliche Backup-Quelle — die Operator-Skripte werden zurückgebaut"
status: accepted
date: "2026-10-01"
deciders: [user, database-engineer]
affected_reqs: [REQ-L0-034, REQ-L1-046, REQ-L2-BL-011]
superseded_by: null
---

# ADR-012: Sidecar ist die verbindliche Backup-Quelle — die Operator-Skripte werden zurückgebaut

**Status:** accepted
**Datum:** 2026-10-01
**Entscheider:** user, database-engineer
**Betroffene REQs:** REQ-L2-BL-011 (Instanz-Backup, Full Restore & Baseline-Soft-Restore,
`docs/se/L1/Gesamtsystem/L2/BaselineServiceSystem/L2_BaselineServiceSystem_Requirements.md:536-568`),
REQ-L1-046 (Instanz-Backup, Disaster Recovery & Baseline-Restore,
`docs/se/L1/Gesamtsystem/L1_Gesamtsystem_Requirements.md:1544-1563`),
REQ-L0-034 (Instanz-Backup, Disaster Recovery & Baseline-Vergleich,
`docs/se/traceability-matrix.md:62`)
**Bezug:** Audit-Kandidat **#5** (`docs/audit/2026-09/AUDIT_ADR_CANDIDATES.md:220-266`),
Implementation-Plan-Slot **ADR iii** (`docs/audit/2026-09/review/IMPLEMENTATION_PLAN.md:216`),
Findings **`AUD-2026-09-122`, `-123`, `-124`, `-127`, `-128`, `-345`**;
`deploy/docker-compose.yml:348-505` (`postgres-backup`-Sidecar);
`scripts/backup.sh:79-87`; `scripts/restore.sh:49,116,183,186,198-213`;
`docs/DEPLOY_RUNBOOK.md:24-77`; `docs/audit/2026-09/AUDIT_EVIDENCE/wp1c-restore-test-protocol.md:306`

**Review-/Lifecycle-Vermerk:** Statuswechsel `proposed → accepted` am 2026-10-01.
Review-Verdikt `concept-reviewer` **APPROVED**, `validator` **COMPLIANT** (MADR-Lifecycle,
Datum + Grund dokumentiert). `deciders` bleiben `user, database-engineer`; die Reviewer
ändern den Status nicht.

---

## Kontext

**Es gibt zwei Backup-Wege, und sie sind auf verschiedene Art defekt.**

**1. Der Sidecar (`postgres-backup`) funktioniert und ist restore-verifiziert.**
`deploy/docker-compose.yml:348-505` beschreibt einen Sidecar, der per `pg_dump --file=` in
eine Klartextdatei dumpt, die `COPY`-Blockzahl prüft, `gzip -9` komprimiert und das gzip
testet (`:413-454`). Ein **echter** Restore des Sidecar-Dumps in eine isolierte
PG-16-Datenbank reproduzierte **15/15 Tabellenzahlen mit 0 Fehlern** — belegt in
`docs/audit/2026-09/AUDIT_EVIDENCE/wp1c-restore-test-protocol.md:306` und
`docs/audit/2026-09/AUDIT_SUMMARY.md:61,114`. Das ist die **einzige** Evidenz im
Repository, die einen Restore überhaupt belegt.

**2. `scripts/backup.sh` kann nie erfolgreich sein.** `check_prerequisites` läuft vor
jedem Subkommando (`scripts/backup.sh:157`) und bricht hart ab, wenn
`${PROJECT_ROOT}/docker-compose.backup.yml` fehlt (`:84-87`); der Kommentar `:79-83`
hält ausdrücklich fest, dass diese Datei **nie existiert hat** und der Pfad vom
`postgres-backup`-Sidecar abgelöst wurde. Der Fix ist daher kein Bugfix, sondern die
Frage, ob der Pfad überhaupt existieren soll.

**3. `scripts/restore.sh` kann nie erfolgreich sein.** Er baut `pg_restore`/`psql`
gegen `/tmp/backup.dump` bzw. `/tmp/backup.sql` im Postgres-Container (`:183`, `:186`),
kopiert die Host-Datei aber nur nach **stdin** (`:198-201`, `:206-212`) — `/tmp/backup.*`
entsteht im Container nie. Zusätzlich: Format-/Ortsinkompatibilität (`.sql.gz` im
Named Volume `postgres_backup_data` laut `:372`, `:405` vs. `*.dump`/`*.sql` in
`./backups` laut `:49`, `:116`) und fehlende Atomarität (`--clean --if-exists`
in-place auf der Live-DB, `:183`).

**Die Randbedingungen des Sidecars (Restrisiken, die A nicht löst):**
`BACKUP_RETENTION=7` und `BACKUP_INTERVAL=21600` s (6 h) ergeben einen **42-h-Horizont**
(`deploy/docker-compose.yml:357,361`; `.env.example:586-587`). Der Dump liegt host-lokal
im Named Volume (`:372`) — **kein Off-Host**, `gzip` ist **keine** Verschlüsselung, und
es existiert **kein** Medien-/Upload-Volume im Backup (Suchtreffer `media|upload` in
`deploy/docker-compose.yml` = 0, belegt in
`docs/audit/2026-09/review/evidence/REVIEW_WP1C.md:31`). Die Minimal-Variante hat gar
keinen Sidecar (`deploy/docker-compose.minimal.yml:13`: „No scheduled DB backups …
take manual dumps").

**Die Anforderungswahrheit ist widersprüchlich.** In der Traceability-Matrix ist
`REQ-L2-BL-011` als **`Not Implemented` / `Missing`** geführt
(`docs/se/traceability-matrix.md:331`), während der Elternteil `REQ-L1-046` als
**`Implemented`** geführt wird (`:144`). Genau dieser Eltern/Kind-Widerspruch ist
**Finding `AUD-2026-09-345`** (`docs/audit/2026-09/AUDIT_FINDINGS.md:2143,2159`).

> **Korrektur der Aufgabenprämisse (gegen den Code geprüft).** Die Aufgabenstellung
> nennt `REQ-L2-BL-011` als in der Matrix auf `Implemented` geführt. Der verifizierte
> Ist-Zustand ist umgekehrt: `REQ-L2-BL-011` ist **`Not Implemented`** (`:331`); die
> `Implemented`-Zeile gehört dem **Parent** `REQ-L1-046` (`:144`). Beide Angaben sind
> hier belegt und werden nicht umgeschrieben (keine Änderung der Matrix in diesem ADR).

**Bisher kein ADR regelt Backup/Restore.** Das ist selbst die Feststellung: für einen
zertifizierungsrelevanten Betriebsbereich existiert keine akzeptierte Entscheidung.

---

## Alternativen

### Option A: Sidecar ist die Quelle; die Skripte werden zurückgebaut (GEWÄHLT)

**Beschreibung:** Der `postgres-backup`-Sidecar ist der **alleinige** Backup-Erzeuger.
`scripts/backup.sh` und `scripts/restore.sh` werden entfernt. Der Restore ist **keine
zweite Quelle**, sondern ein dokumentierter, atomarer Runbook-Befehl, der den
Sidecar-Dump in eine **isolierte Zieldatenbank** spielt (eine Transaktion, Fehler →
Rollback). Der Restore-Smoke (15/15, isolierte Zieldatenbank, eine Transaktion) wird
zum Release-Gate.

**Abwägung:** Nur dieser Weg hat einen **belegten erfolgreichen Restore** (15/15, 0
Fehler). Ein Backup, dessen Restore nicht nachgewiesen ist, ist kein Backup — die
Evidenz entscheidet, nicht die Existenz eines Skripts. Es gibt danach genau **einen**
Erzeuger und genau **ein** Format (`.sql.gz`), also keine zweite Fehlerquelle. Die
Restrisiken (Off-Host, Verschlüsselung, Medien) sind echte Lücken, aber sie sind
**Erweiterungen von A**, kein Grund, einen ungetesteten zweiten Pfad zu betreiben.

**Risiko:** NIEDRIG — auf der Mechanik-Seite; MITTEL für die noch offenen Restrisiken

---

### Option B: Die Skripte sind die Quelle — reparieren (VERWORFEN)

**Beschreibung:** `backup.sh` reaktivieren (Zielpfad `docker-compose.backup.yml`
anlegen oder entfernen), `restore.sh` korrigieren (Datei in den Container kopieren,
Formatvertrag definieren, atomar in eine Zieldatenbank spielen), Smoke als Gate.

**Abwägung:** Der Pfad ist bis zur Reparatur **ungetestet** — und er dupliziert den
Sidecar, der nachweislich schon funktioniert. Ein halb repariertes `restore.sh` ist
schlechter als ein entferntes, weil es gefährliches Vertrauen erzeugt. Die
Reparaturaufwände (Container-Kopie, Formatvertrag, Atomarität, Retention, Off-Host)
sind Aufwände an einer Parallelkonstruktion, nicht an der Evidenz.

**Risiko:** HOCH — ungetestete Recovery als einzige Quelle

---

### Option C: Beide Pfade mit Vergleichs-Smoke als Wahrheit (VERWORFEN)

**Beschreibung:** Sidecar für die Automatik, Skripte für den Notfall — mit einem
Restore-Smoke, der **beide** Wege ausführt und die Tabellenzahlen vergleicht.

**Abwägung:** Der Vergleich ist nur sinnvoll, wenn beide Wege unabhängig und
zuverlässig sind. Heute ist B (Skripte) nachweislich tot; C würde also einen toten Pfad
institutionalieren, statt ihn zu beenden. Zwei Pfade bedeuten zwei Formate, zwei
Fehlerquellen und zwei Betriebsrituale — der Mehrwert (Notfall-Redundanz) entstünde
erst nach vollständiger Reparatur von B und ist dann erneut zu begründen.

**Risiko:** MITTEL — doppelte Betriebs- und Testlast ohne zusätzliche Evidenz

---

## Entscheidung

**Option A. Der `postgres-backup`-Sidecar ist die verbindliche Backup-Quelle.**

1. **Ein Erzeuger:** Instanz-Snapshots werden ausschließlich vom Sidecar
   `postgres-backup` erzeugt (`deploy/docker-compose.yml:348-505`), Format `.sql.gz`
   im Named Volume `postgres_backup_data` (`:372`, `:405`).
2. **`scripts/backup.sh` wird entfernt** (zurückgebaut). Der Pfad kann heute nie
   erfolgreich sein (`:79-87`) und hat keinen Aufrufer in einem Makefile-Target.
3. **`scripts/restore.sh` wird entfernt** (konsistent zu Titel und Punkt 2). Er ist
   keine zweite Quelle, sondern wird durch einen dokumentierten, **atomaren**
   Runbook-Befehl ersetzt, der den Sidecar-Dump aus `postgres_backup_data` liest und
   in eine **isolierte Zieldatenbank** spielt. Der Restore läuft **atomar in einer
   einzigen Transaktion** (Fehler → Rollback, Live-DB bleibt unberührt) und darf
   **niemals** in-place (`--clean --if-exists`) auf der Live-DB arbeiten — er adressiert
   damit Finding `AUD-2026-09-127` (`scripts/restore.sh:183`). Er darf **niemals** aus
   einem `./backups`-Ordner lesen, den der Sidecar nicht schreibt. Die Ausführung ist
   Folgeaufgabe `DATA-01` (Owner: `database-engineer`).
4. **Der Restore-Smoke ist die eigentliche Wahrheit — mit expliziter Gate-Definition.**
   Das Gate ist bestanden, wenn ein restaurierter Sidecar-Dump die
   **15/15-Tabellenzahlen** mit **0 Fehlern** reproduziert
   (`wp1c-restore-test-protocol.md:306`). Das Gate führt den Restore **ausschließlich**
   gegen eine **isolierte Zieldatenbank** (eigene Test-DB/Instanz, nie die Live-DB) und
   **atomar in einer einzigen Transaktion** aus (Fehler → Rollback). Damit
   institutionalisiert es **nicht** die Nicht-Atomarität aus
   `scripts/restore.sh:183` (Finding `AUD-2026-09-127`), sondern ersetzt sie durch den
   atomaren Zieldatenbank-Vertrag. Ausführung als Release-Gate (CI/Operator, vgl.
   `docs/DEPLOY_RUNBOOK.md:52-53,63`).
5. **Die Restrisiken sind Teil von A, nicht Gründe gegen A:** Off-Host-Kopie,
   Verschlüsselung, Medien/Uploads und die Minimal-Variante ohne Sidecar werden als
   Folgeentscheidungen von A nachgezogen (siehe „Offene Punkte").

### Was diese Entscheidung *nicht* ist

Sie ist **keine** Aussage, dass Off-Host, Verschlüsselung und Medien entbehrlich sind.
Sie ist die Aussage, dass **genau ein** nachgewiesener Pfad die Quelle der Wahrheit
ist — und dass alle weiteren Fähigkeiten auf diesem Pfad ergänzt werden, nicht auf
einem zweiten, ungetesteten.

---

## Konsequenzen

**Positiv:**

- Die Backup-Wahrheit beruht auf der **einzigen** Evidenz mit erfolgreichem Restore
  (15/15, 0 Fehler); der Release-Smoke macht sie dauerhaft prüfbar.
- Genau **ein** Format (`.sql.gz`) und **ein** Erzeuger entfallen als zwei
  Fehlerquellen und zwei Betriebsrituale.
- Toter, gefährlicher Code (`backup.sh` `exit 1`; `restore.sh` /tmp-Problem) wird
  beendet, statt gepflegt — irreführende Operator-Skripte verschwinden.
- `docs/DEPLOY_RUNBOOK.md` trägt den Restore-Drill bereits (`:63`); die Lücke zwischen
  „Sidecar erzeugt" und „Operator spielt zurück" ist klein und dokumentierbar.

**Negativ:**

- **Der Operator-Einstiegspunkt `./backups` verschwindet.** Wer bisher
  `scripts/restore.sh --latest` erwartete, findet dort keinen Pfad mehr; das Runbook
  muss den atomaren Restore-Befehl vollständig tragen. Die Umstellung ist sichtbar.
- **Restrisiko bleibt ausdrücklich offen** und wird von A **nicht** gelöst: der
  Sidecar-Dump liegt host-lokal im Named Volume (`deploy/docker-compose.yml:372`) —
  **kein Off-Host**; `gzip -9` ist **Komprimierung, keine Verschlüsselung**; **Medien/
  Uploads** sind nicht im Backup; der **42-h-Horizont** (7 × 6 h, `:357`, `:361`) ist
  für einen Totalausfall kurz. Diese Lücken müssen benannt und separat geschlossen
  werden — sonst suggeriert „Sidecar ist die Quelle" eine Vollständigkeit, die sie
  nicht hat.
- **Die Minimal-Variante bleibt ohne Backup** (`docker-compose.minimal.yml:13`);
  gewählt wird der Full-Stack-Sidecar, die Minimal-Variante ist damit bewusst
  ungedeckt und muss dokumentiert/manuell abgedeckt werden.
- **Ein Restore-Smoke existiert heute nicht** (nur der statische Compose-Self-Check
  `deploy/verify-backup-command.sh`, #1074). Ohne ihn bleibt A eine Entscheidung mit
  Nachweis-Pflicht, nicht mit Nachweis.

### Impact auf `REQ-L2-BL-011`

- **`REQ-L2-BL-011` bleibt `Not Implemented` / `Missing`.** Die Anforderung verlangt
  nicht nur Backup und Full Restore, sondern auch **Soft-Restore** in einen
  Sandbox-Zweig (AC3), **Hard-Restore** mit Admin-Auth + Captcha (AC4), **Baseline-Diff**
  (AC5), **Audit-Log-Eintrag** (AC6) und die BaselineService-Schnittstellen
  (`POST /admin/backup`, `POST /admin/restore`, `POST /baselines/{id}/soft-restore`,
  `POST /admin/hard-restore`, `L2_BaselineServiceSystem_Requirements.md:550-563`).
  Der Sidecar liefert davon nur den **Instanz-Backup-/Full-Restore-Teil**; die
  Baseline-Soft-/Hard-Restore-Fähigkeiten sind BaselineService-Logik und **nicht**
  durch A abgedeckt. Ein Hochsetzen auf `Implemented` allein durch A wäre unwahr.
- **Der Eltern/Kind-Widerspruch (`AUD-2026-09-345`) bleibt bestehen und wird durch
  dieses ADR verschärft sichtbar:** `REQ-L1-046` `Implemented` (`:144`) mit dem
  einzigen Kind `REQ-L2-BL-011` `Not Implemented` (`:331`) ist nicht haltbar. Die
  korrekte Dokumentationsfolge ist die im Audit empfohlene **Trennung** von Backup
  und Baseline-Restore (`docs/audit/2026-09/AUDIT_TRACEABILITY.md:367`): der
  Backup-/Full-Restore-Teil kann nach bestandenem Restore-Smoke als abgedeckt gelten,
  der Baseline-Restore-Teil von `REQ-L2-BL-011` bleibt offen.
- **Dieses ADR ändert die Matrix nicht** (Auftragsumfang). Die Status-Korrektur bzw.
  Aufteilung ist Gegenstand von `DOC-01` / `DATA-01`
  (`docs/audit/2026-09/review/plan/DATA_RECOVERY.md:22-31`).

### `open_adrs`-Notiz (analog ADR-010)

Das Frontmatter-Feld `open_adrs` existiert repo-weit nicht (0/835 REQs,
`AUD-2026-09-333`; vgl. `ADR-010_health_vertrag.md:86-90`). Die REQ↔ADR-Verknüpfung
(`REQ-L0-034`, `REQ-L1-046`, `REQ-L2-BL-011`) kann daher **nicht** maschinell in den
REQ-Dateien eingetragen werden und bleibt Folgeaufgabe `DOC-01`. Es wird **keine**
REQ-Datei und **keine** Traceability-Matrix geändert.

---

## Offene Punkte

1. **Umsetzung `scripts/backup.sh` / `scripts/restore.sh`** — beide werden entfernt;
   der atomare Runbook-Restore (isolierte Zieldatenbank, eine Transaktion) wird
   dokumentiert. Keine offene Design-Frage mehr, nur Ausführung. Owner:
   `database-engineer` (`DATA-01`), Termin: Welle **W1** (`IMPLEMENTATION_PLAN.md:161`).
2. **Off-Host-Kopie, Verschlüsselung, Medien/Uploads** — als Erweiterungen von A
   nachziehen; ohne sie bleibt ein Restrisiko benannt, aber ungeschlossen.
3. **Minimal-Variante** ohne Sidecar (`docker-compose.minimal.yml:13`) braucht eine
   dokumentierte manuelle Backup-/Restore-Route oder einen Sidecar.
4. **Restore-Smoke als Gate** — in CI/Release verankern mit der Definition aus
   Entscheidung Punkt 4 (isolierte Zieldatenbank, atomare Einzeltransaktion,
   15/15-Tabellenzahlen); heute existiert nur der statische Self-Check
   `deploy/verify-backup-command.sh`. Owner: `database-engineer` (`DATA-01`),
   Termin: Welle **W1**.
5. **Matrix-Widerspruch `AUD-2026-09-345`** — Auflösung über `DOC-01` (Trennung
   Backup vs. Baseline-Restore), nicht durch dieses ADR.

---

*Erstellt: 2026-10-01 | Autor: database-engineer | Für: REQ-L0-034, REQ-L1-046, REQ-L2-BL-011*
*Status `accepted` seit 2026-10-01 — `concept-reviewer` APPROVED, `validator` COMPLIANT.*
*Kein Code-Äquivalent geändert; dieses Dokument ändert weder die Traceability-Matrix noch die Skripte.*
