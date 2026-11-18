# Migrations-Sicherheits-Runbook (S5.3 WP-4)

**Status:** BESTÄTIGT · **Owner:** `sre-engineer` · **Geltung:** alle Django-Schema-/Datenmigrationen vor Deployment und Promotion
**Verifiziert gegen:** Worktree `.tmp/wt-s53/`, Branch `fix/s5-3-ops-maturity`, Basis `f60697d2` — Stand 2026-11-18
**Umfang:** Dokumentation. Dieses Runbook ändert **keinen** Migrationscode und führt **keine** Migration aus.

> **Einordnung:** Dieses Dokument ist die in `docs/deploy/STAGING_PROMOTION.md` §8
> (S5.2, PR #1938, gemergt als `05c4f1c`) angekündigte S5.3-Leerstelle. Der
> Restore-Rehearsal in **§6 jenes Dokuments** ist der interimistische Sicherheits-Gate;
> dieses Runbook ersetzt ihn nicht, sondern ergänzt ihn um die Migrationsebene.
> Die AWMS-Systematik (`docs/se/attribut/attribut-migrationssystematik.md`, Frontmatter
> `scope: attribut-migrationssystematik`, `status: draft`) ist **domänenspezifisch für
> Attribut-/Wert-Migrationen** und kein allgemeines Migrations-Runbook — nicht als solches verwenden.

---

## 0. Verifikationsstand — was behauptet wird und was nicht

Alle unten genannten Datei-/Zeilangaben wurden im aktuellen Worktree geprüft.

| Behauptung | Verifikation | Ergebnis |
|---|---|---|
| Anzahl Migrationen | `find backend -type d -name migrations … -name '0*.py' \| wc -l` | **375** |
| 0141-Reverse destruktiv? | `grep -rn "DELETE FROM pl_allocation" backend/*/migrations/` | **kein Treffer** — Reverse ist `migrations.RunSQL.noop` (`0141_backfill_allocations.py:222`) |
| L0-002 behoben? | Modul-Docstring `:20-31`, Guard-Test `persistence/tests/test_backfill_allocations_reverse_guard.py:19-38` | **im aktuellen Code verifiziert behoben** (S0.3-A) |
| L0-001 behoben? | `audit/archive.py:345-364` (`_PURGE_SQL = "SELECT audit_ops.purge_entries_before(%s)"`), `audit/migrations/0020_retention_purge_function.py:1,74,226` | **im aktuellen Code verifiziert behoben** (S0.3-A) |
| Compose-Migrationsreihenfolge | `deploy/docker-compose.yml:885, 902-906, 925, 783, 588, 1027, 1146` | korrekt, siehe §7 |
| Restore-Gate vorhanden? | `deploy/verify-restore.sh:1-27, 109-137, 209-305` | vorhanden (ADR-012 / DATA-01/02) |

> **Wichtig — historische Fundstellen:** `docs/audit/2026-11-16-deep-dive-findings.md:86-87`
> nennt für L0-001 `backend/audit/archive.py:329-358` und für L0-002
> `backend/persistence/migrations/0141_backfill_allocations.py:34,43` mit dem
> Reverse `_DELETE_SQL = "DELETE FROM pl_allocation;"`. **Diese Zeilennummern und dieser
> Code beschreiben den Zustand vor S0.3** (Fix-Commit `7d6593a3`, Merge `cecde079`,
> belegt in `:19`). Im aktuellen Code stehen an `:34,43` Importe/Konstanten; ein
> `DELETE FROM pl_allocation` existiert nirgends mehr. Die Fundstelle ist als
> historischer Audit-Trail zu lesen, nicht als aktuelle Fehlermeldung.

---

## 1. Klassifikation: destruktiv vs. additiv

Vor **jeder** Migration ist die Operation in eine der beiden Klassen einzuordnen. Die
Klassifikation bestimmt Rehearsal-Tiefe, Backup-Pflicht und Reverse-Strategie.

| Klasse | Kriterium | Beispiele im Repo | Konsequenz |
|---|---|---|---|
| **Additiv** | Bestehende Zeilen/Spalten bleiben unverändert; neue Objekte oder Werte werden ergänzt; idempotent wiederholbar | `CREATE TABLE`, `ADD COLUMN NULL`, `CREATE INDEX CONCURRENTLY` (`0080`, `0116`), Backfill mit `ON CONFLICT DO NOTHING` (`0141:68,87`) | Standard-Rehearsal (§7); Reverse muss nicht destruktiv sein |
| **Destruktiv** | Löscht Zeilen, entfernt Spalten/Tabellen, setzt Werte um, zieht `NOT NULL`- oder Constraint-Contract nach, oder verändert geteilte Infrastruktur | `DELETE`/`TRUNCATE`, `DROP COLUMN/TABLE`, `SET NOT NULL`, `DROP EXTENSION` (R2D-006, `docs/audit/2026-11-16-deep-dive-findings.md:997`), Append-only- vs. Retention-Konflikt (L0-001) | Erweitertes Rehearsal: Reverse-Test auf Wegwerf-DB (§5), Lock-Analyse (§6), expliziter Freigabepunkt, Backup zwingend (§4) |
| **One-way-door** | Korrekte Rückwärtsbewegung ist unmöglich oder würde Live-Daten vernichten | `0141_backfill_allocations.py:20-31` (L0-002) | Reverse = `noop`, **bewusst dokumentiert**; kein `migrate <app> <vorherige>` als Rollback — Forward-Fix oder Restore (§8) |

**Entscheidungsregel:** Kann ein Reverse mehr löschen als die Migration selbst angelegt
hat, ist er **unzulässig**. Dann ist die Migration als One-way-door zu dokumentieren
(§3), nicht mit einem „probably fine"-DELETE zu versehen. Der Präzedenzfall ist L0-002.

---

## 2. Expand / Contract (Parallel Change)

Die Reihenfolge ist verbindlich (belegt als gelebte Praxis in
`docs/audit/2026-11-16-deep-dive-findings.md:1003`: `diagram/0005`, `icd/0012`→`0013`,
`application/0022`→`0023`).

1. **Expand** — Neue Spalte/Tabelle **nullable** und ohne Constraint anlegen; ggf.
   Index `CONCURRENTLY` (§6). Alte und neue Form existieren parallel. *Kein* Feature
   liest die neue Form bereits. (`diagram/0005:1-23` ergänzt nullable FK + Index und
   verschiebt Backfill und NOT NULL ausdrücklich in spätere Migrationen.)
2. **Backfill** — Daten in Batches überführen, idempotent (`ON CONFLICT DO NOTHING`),
   mit RLS-Abschaltung pro Seite (`0141:104-171`, `:109`), Transcript und
   Trockenzählung (`_dry_run_count`, `:113-119`). Kein Update/Delete auf dem heißen
   Pfad der Anwendung.
3. **Contract** — Erst nachdem alle Schreiber die neue Form nutzen: `SET NOT NULL`,
   Constraint, Drop der alten Form — als **eigene** Migration, nie im selben Schritt
   wie ein Feature-Rollout. `0118_uid_workspace_unique_constraints.py:53-58` dokumentiert
   den `CREATE UNIQUE INDEX CONCURRENTLY` + `ADD CONSTRAINT … USING INDEX`-Weg für
   große Tabellen.

> **Anti-Pattern:** `ADD COLUMN … NOT NULL DEFAULT …` auf einer großen Tabelle in
> einem Schritt (lange ACCESS-EXCLUSIVE-Locks) — stattdessen Expand/Contract.
> **Anti-Pattern:** destruktive DDL im selben Release wie die Feature-Umschaltung;
> damit gibt es keinen Zwischenzustand, in dem ein Rollback sicher möglich ist.

---

## 3. One-way-door: `noop`-Reverse als dokumentierte Entscheidung

**Präzedenzfall L0-002 / S0.3.** Der ursprüngliche Reverse von `0141` war ein
unqualifizierter `DELETE FROM pl_allocation` und hätte auch später über die API
erzeugte, ggf. `released`-Allokationen gelöscht (Audit-Finding
`docs/audit/2026-11-16-deep-dive-findings.md:87`, vgl. Remediation-Plan
`docs/superpowers/plans/2026-11-16-deep-dive-remediation.md:59-60,187-197`).
Da Backfill-Drafts keine Provenance-Kennzeichnung tragen, ist ein zielgerichteter
Reverse nicht möglich. Der S0.3-Fix macht den Reverse deshalb bewusst zu einem
**noop** — dokumentiert in `0141_backfill_allocations.py:20-31`, implementiert als
`migrations.RunSQL.noop` (`:222`).

Zur Pattern-Benennung: Django stellt für solche Fälle `RunPython.noop` *und*
`RunSQL.noop` bereit; beide drücken „bewusst keine Rückwärtsoperation" aus. **0141
verwendet `RunSQL.noop`**, weil die Operation eine `RunSQL`-Subklasse ist
(`:174-186`) — die Struktur ist von einem Guard-Test festgeschrieben:

- `backend/persistence/tests/test_backfill_allocations_reverse_guard.py:19-28` —
  genau eine `RunSQL`-Operation, deren `reverse_sql is migrations.RunSQL.noop`;
- `:30-38` — der Quelltext darf die Zeichenkette `DELETE FROM pl_allocation` nicht
  enthalten (scheitert also auch an einem „harmlos" umformulierten Bulk-Delete).

**Regel für neue Migrationen:** Ein noop-Reverse ist nur zulässig, wenn
1. im Modul-Docstring steht, **warum** kein Reverse möglich ist (Datenverlust-Risiko
   konkret benennen), 2. ein Struktur-Guard-Test wie oben existiert und 3. der
   Eintrag in die Klassifikation (§1) aufgenommen wird. Ohne diese drei Punkte gilt
   die Migration als nicht freigabereif.

> **Nicht verwechseln:** L0-001 (`audit`-Retention vs. append-only-Trigger,
> `docs/audit/2026-11-16-deep-dive-findings.md:86`) ist ebenfalls S0.3-owner und im
> aktuellen Code behoben — jedoch über eine **rechte Maintenance-Funktion**, nicht
> über noop: `audit/archive.py:345-364` ruft `audit_ops.purge_entries_before(%s)`,
> installiert in `audit/migrations/0020_retention_purge_function.py:74,226`. Der
> append-only-Trigger (`audit/migrations/0002_append_only_trigger.py:40-42`) bleibt
> dabei aktiv. Lehre: destruktive Wirkung darf nie „nebenbei" an einem Trigger
> vorbeilaufen; sie braucht einen expliziten, berechtigten Pfad.

---

## 4. Backup vor Migration (ADR-012)

ADR-012 (`docs/se/ADR/ADR-012_backup_wahrheit.md:144-171`) legt fest: es gibt
**einen** Backup-Erzeuger — den `postgres-backup`-Sidecar — und ein Backup ist
**nur bewiesen, wenn der Restore bewiesen ist** (`:162-171`: 15/15 Tabellenzahlen,
0 Fehler, isolierte Zieldatenbank, atomare Einzeltransaktion). Der zugehörige
Gate ist `deploy/verify-restore.sh` (Kopf `:1-27`: extrahiert den *realen*
Compose-Befehlsblock, restored atomar in eine Wegwerf-DB, prüft 15/15 + pgvector +
injierten Fehler-Rollback; Live-DB wird nie kontaktiert).

**Vor jeder destruktiven Migration:**

1. Aktuellen Sidecar-Dump verifizieren — `deploy/verify-restore.sh` muss Exit 0
   liefern (Äquivalent: `docs/DEPLOY_RUNBOOK.md:303, 345-360`, §6.3 atomarer
   Restore in isoliertes Ziel). **Kein** Restore in die Live-DB, **kein**
   `--clean --if-exists` dort.
2. Alter des jüngsten Dumps prüfen: `BACKUP_RETENTION × BACKUP_INTERVAL` ist der
   Horizont — Default 7 × 6 h = **42 h** (ADR-012 `:64-72, 203-212`,
   `docs/DEPLOY_RUNBOOK.md:314-321`). Bei kürzerem Zyklus oder geplantem
   Wartungsfenster: manuellen `BACKUP_ONCE`-Dump erzwingen
   (`docs/DEPLOY_RUNBOOK.md:50-54`).
3. Bekannte Restrisiken benennen, nicht verschweigen: Dump liegt host-lokal im
   Named Volume, `gzip` ist keine Verschlüsselung, Medien/Uploads sind nicht
   enthalten, Minimal-Variante hat keinen Sidecar (ADR-012 `:203-212, 257-258`).
   Ohne Off-Host-Kopie ist ein Restore nach Volume-Verlust nicht garantiert.

> **Regel:** Ohne bestandenen Restore-Gate **keine** destruktive Migration. Ein
> „wird schon funktionieren"-Backup ist kein Backup (ADR-012 `:102-107`).

---

## 5. Reversibilitätstest — nur auf Wegwerf-DB

**Niemals** einen Reverse auf der Produktionsdatenbank testen. Für jeden Reverse
(außer dokumentierte One-way-doors, die stattdessen den Guard-Test aus §3 laufen
lassen) gilt:

1. **Wegwerf-Instanz** mit eigenem Compose-Projekt und eigenen Volumes starten,
   z. B. `docker compose -p reqlo-mig-rehearsal -f deploy/docker-compose.yml up -d postgres redis`.
   Nie das Produktionsprojekt oder `postgres_data` verwenden (Volume-Locks!).
2. **Vorwärts migrieren** mit dem *exakt selben signierten Image-Digest* wie
   Produktion (Digest-Pinning siehe S5.2 §3). `DB_STATEMENT_TIMEOUT_MS=0` ist im
   `migrate`-Service bereits gesetzt (`deploy/docker-compose.yml:902-906`) und darf
   dort nicht „aufgeräumt" werden — Index-Builds dürfen nicht nach 30 s abbrechen.
3. **Reverse ausführen**: `docker compose -p reqlo-mig-rehearsal … run --rm migrate python manage.py migrate <app> <vorherige migration>`.
4. **Ergebnis prüfen**: Zeilenzahlen der betroffenen Tabellen vor/nach Reverse
   vergleichen; `django_migrations`-Einträge konsistent; anschließend Forward
   erneut laufen lassen (Idempotenz). Bei One-way-door: erwartet ist `noop` +
   unveränderte Daten, und der Guard-Test (§3) muss grün sein.
5. **Aufräumen** nur innerhalb des Wegwerf-Projekts; die Produktions-Volumes
   bleiben unangetastet.

Der Rehearsal ist **nicht** bestanden, wenn der Reverse stillschweigend Daten
verliert, eine Tabelle leer zurücklässt oder der Forward danach nicht mehr
idempotent ist. `0141` ist bewusst die Ausnahme: sein Reverse tut nichts — der
Test besteht aus Guard-Test + Bestätigung, dass keine Allokation verschwand.

---

## 6. Lock-Analyse für große Tabellen

Vor jeder DDL auf einer Tabelle mit relevanter Größe (Faustregel: ab ~10^6 Zeilen,
bei FORCE-RLS-Tenant-Tabellen früher) ist die Lock-Wirkung explizit zu prüfen.

| Operation | Gefahr | Bewährtes Muster im Repo |
|---|---|---|
| `CREATE INDEX` | blockiert Schreiber für die Dauer des Builds | `atomic = False` + `AddIndexConcurrently` — `persistence/migrations/0080_tracelink_semantics_fields.py:15-16,49,74`; `0116_index_hygiene_1411.py:15-20,37,45`. `AddIndexConcurrently` ist selbst-reversibel; bei Teilfehler invalid index + `migrate --fake` (in den Modulen dokumentiert). |
| `ADD COLUMN … NOT NULL` | ACCESS-EXCLUSIVE über die ganze Tabelle | Expand/Contract (§2): nullable anlegen → backfill → `SET NOT NULL` in eigener Migration. |
| `ADD CONSTRAINT … UNIQUE` | baut Index unter SHARE-Lock | `CREATE UNIQUE INDEX CONCURRENTLY` + `ADD CONSTRAINT … USING INDEX` — `0118_uid_workspace_unique_constraints.py:53-58`. |
| Massen-`UPDATE`/`INSERT … SELECT` | lange Row-Locks, WAL-Bloat, Replikationslag | Keyset-Pagination nach PK, Commit zwischen Seiten, `atomic = False`, Trockenzählung — `0141:44-49,104-171,216-217` (R2D-004, `docs/audit/2026-11-16-deep-dive-findings.md:995`). |
| `DROP`/große Löschung | ERROR bei abhängigen Objekten / Trigger, Live-Datenverlust | Keine geteilte Infrastruktur aus Feature-Migration löschen (R2D-006, `:997`); destruktive Fälle nach §1/§3/§4. |

Zusätzlich: `SET LOCAL row_security = off` **pro Page** (niemals global), sonst
liefert ein Scan unter FORCE RLS stillschweigend 0 Zeilen und die Migration
„erfolgreich" ohne Daten (`0141:106-110`; Stärke east implementiert, vgl.
`docs/audit/2026-11-16-deep-dive-findings.md:1005`). `statement_timeout=0` gilt
nur für den `migrate`-One-shot (`:902-906`), nicht für Backend/Celery.

---

## 7. Staging-Rehearsal über den S5.2-Workflow

> S5.2 ist zum Erstellungszeitpunkt **nicht auf `f60697d` merged**. Die nachstehenden
> Abschnitte beziehen sich auf `docs/deploy/STAGING_PROMOTION.md` und
> `.github/workflows/deploy-staging.yml` auf Branch `fix/s5-2-ci-ops` @ `f7d1c6f9`
> (beide dort verifiziert; im Basis-Worktree noch nicht vorhanden). Nach dem Merge
> sind die Pfade ohne Branch-Präfix gültig. Bis dahin: **§6 von S5.2 ist der
> Interims-Gate** (dessen §8 explizit auf dieses Runbook zeigt).

Der Rehearsal folgt S5.2 §6 (Staging-Rehearsal) und §3 (Same-Digest-Invariante):

1. **Gleiche signierte Digests:** `resolve` ermittelt die `sha256:`-Digests beider
   Images **einmal**, verifiziert die Cosign-Signatur erneut; Staging *und*
   Produktion konsumieren exakt diese beiden Outputs (S5.2 §3). Kein Rebuild, kein
   Tag erneut auflösen.
2. **Compose-Apply ohne Rebuild:** `compose pull`, dann `compose up -d postgres redis`.
3. **Migrate-One-shot mit hartem Wait:** `compose up -d migrate`, Container via
   `compose ps -aq migrate` finden, **`docker wait <id>`** blockieren; jeder
   Exit-Code ≠ 0 bricht den Job ab (S5.2 §6 Schritt 3).
4. **Restore-Rehearsal:** `deploy/verify-restore.sh` gegen Wegwerf-Postgres; die
   Live-DB wird nie kontaktiert (S5.2 §6 Schritt 4, Details §4/§5 dieses Runbooks).
5. **HTTP-Smoke:** `curl -fsS` gegen `/health/live` und `/health/ready` mit
   begrenzten Retries (S5.2 §6 Schritt 5).

Erst nach 1–5 wird der `production`-Job mit `environment: production` und
Required Reviewers freigegeben. Produktion wiederholt Apply/Migrate/Smoke,
**nicht** den Restore-Rehearsal (staging-only Gate). Rollback = Redeploy eines
zuvor signierten Digests via `repository_dispatch` (S5.2 §7) — nie ein Rebuild.

**Verifizierte Compose-Abhängigkeiten (Basis `f60697d2`):**

- `deploy/docker-compose.yml:885` — `migrate`-Service (One-shot, `
  exec python manage.py migrate --no-input`), `restart: "no"`;
- `:925` — `migrate.depends_on.postgres.condition: service_healthy` (DB-Gate);
- `:902-906` — `DB_STATEMENT_TIMEOUT_MS: "0"` nur für Migrationen;
- `:783` — `backend.depends_on.migrate: service_completed_successfully`
  (**der** kritische Gate: kein Traffic vor Abschluss der Migration);
- `:588` — `postgres-backup.depends_on.migrate: service_completed_successfully`
  (kein Dump vor existierendem Schema);
- `:1027` / `:1146` — `celery` / `celery-beat` hängen an `llm-preflight`
  (`service_completed_successfully`), **nicht direkt** an `migrate`. `llm-preflight`
  ist ein reiner Shell-Konfigurations-Gate ohne `depends_on` (`:812-868`).

> **Reliability-Hinweis (kein behobener Defekt):** Der direkte Migrate-Gate liegt
> bei `backend` und `postgres-backup`. Wer Worker-Start vor Migrationen vermeiden
> will, muss im Rehearsal beobachten, dass `celery`/`celery-beat` beim Boot keine
> schemaabhängigen Queries stellen — andernfalls ist der Gate auf diese Dienste
> zu erweitern (Änderung wäre S5.2/devops-engineer, nicht Teil dieses WP).

---

## 8. Abort- vs. Forward-Fix-Kriterien

| Situation | Entscheidung | Begründung |
|---|---|---|
| Restore-Gate (§4) fehlgeschlagen | **ABORT** vor Migration | Kein nachgewiesener Wiederherstellungsweg |
| `docker wait migrate` ≠ 0 (§7) | **ABORT** Promotion; Staging-Logs sichern | Migration nicht vollständig—Promotion ist fail-closed |
| Reverse-Test (§5) verliert Daten | **ABORT**, Migration als destruktiv neu klassifizieren | Reverse ist unzulässig (§1) |
| One-way-door (§3) mit intaktem Forward | **FORWARD-FIX** — keine Rückwärtsmigration | Reverse würde Live-Daten vernichten (L0-002) |
| Von Migration erzeugte Zeilen fehlerhaft, aber identifizierbar | **FORWARD-FIX** als neue korrigierende Migration | Gezielte Reparatur statt Table-wide Delete |
| Lock-Analyse (§6) zeigt langen EXCLUSIVE-Lock | **ABORT** Release, Expand/Contract nacharbeiten | Verfügbarkeitsrisiko für schreibende User |
| Fehler erst **nach** produktiver Migration | Siehe ADR-012: atomarer Restore in **isoliertes** Ziel zur Analyse; danach Forward-Fix oder digest-pinnter Rollback (S5.2 §7) | Niemals `--clean` gegen Live-DB; niemals ungetesteten Reverse „probieren" |
| Error Budget der betroffenen Journey aufgebraucht | Feature-Release pausieren, Reliability-Arbeit Vorrang | Google-SRE-Regel: Budget ist decision rule, nicht guideline. Ein migrationsbedingter Rollback zählt als Budget-Verbrauch; konkrete SLO-Zahlen werden hier **nicht** erfunden (keine Messdaten in diesem WP). |

**Freigaberegel:** Destruktive Migrationen benötigen zusätzlich zum grünen
Staging-Rehearsal eine namentliche Freigabe (Owner `sre-engineer` + Migration-Owner).
One-way-doors sind im Freigabeprotokoll explizit als solche zu kennzeichnen.

---

## 9. Eskalationskette

1. **Stufe 1 — `sre-engineer`** (Owner dieses Runbooks): Klassifikation, Rehearsal,
   Backup-Gate, Abort/Fix-Entscheidung, Freigabeprotokoll.
2. **Stufe 2 — Migration-Owner / `database-engineer`**: Lock-Analyse, Reverse-Design,
   Reparaturmigration; bei AWMS-spezifischen Wert-Migrationen zusätzlich
   `docs/se/attribut/attribut-migrationssystematik.md` (domänen-, nicht
   betriebsverantwortlich).
3. **Stufe 3 — `devops-engineer`**: Änderungen an CI/Deploy-Workflow
   (`.github/workflows/deploy-staging.yml`, Compose-Abhängigkeiten, Environment-Freigaben).
   S5.2-Owner bleibt für §6/§7 des Promotion-Dokuments zuständig.
4. **Stufe 4 — `incident-responder`**: **nur** bei laufendem Produktionsvorfall
   (reaktive Koordination). Dieses Runbook ist präventiv und endet mit der
   Übergabe an den Incident-Prozess; es ersetzt ihn nicht.
5. **Stufe 5 — User / MANAGEMENT (via `main_chat`)**: Freigabe von
   Wartungsfenstern, Off-Host-Backup-Nachrüstung, Reviewer-Bestellung für
   `environment: production` (S5.2 §4 — bewusst out-of-band konfiguriert).

Dokumentations-Updates (SLO/Runbook-Index) → `documenter`; Code-/Migrationsfix →
`developer` / `database-engineer` mit SLI + betroffenem Modul als Kontext.

---

## 10. Pre-Flight-Checkliste (zum Abhaken)

- [ ] Migration klassifiziert: additiv / destruktiv / one-way-door (§1)
- [ ] Expand/Contract-Sequenz eingehalten, destruktive DDL nicht im Feature-Release (§2)
- [ ] Bei one-way-door: Docstring + Guard-Test + Registereintrag vorhanden (§3)
- [ ] `deploy/verify-restore.sh` Exit 0, Dump jünger als Horizont (§4)
- [ ] Rehearsal auf Wegwerf-DB inkl. Reverse (oder Guard-Test) grün (§5)
- [ ] Lock-Analyse für große Tabellen dokumentiert; `statement_timeout=0` im migrate-Service intakt (§6)
- [ ] S5.2-Staging-Rehearsal grün: gleiche Digests, `docker wait migrate` = 0, Restore, HTTP-Smoke (§7)
- [ ] Abort-/Forward-Fix-Kriterium vorbestimmt, Freigabe namentlich (§8)
- [ ] Eskalationskette und Reviewer für `production` benannt (§9)

---

## Referenzen (alle aktual geprüft)

- `docs/deploy/STAGING_PROMOTION.md` (S5.2, Branch `fix/s5-2-ci-ops` @ `f7d1c6f9`, unmerged): §3 Same-Digest, §4 Environment-Schutz, §6 Staging-Rehearsal, §7 Rollback, §8 Pointer auf dieses Runbook
- `.github/workflows/deploy-staging.yml` (dort vorhanden, auf `f60697d2` noch nicht)
- `docs/se/ADR/ADR-012_backup_wahrheit.md` (accepted, 2026-10-01) — Backup-Wahrheit / Restore-Gate
- `docs/se/ADR/ADR-014_import_erfolgssemantik_idempotenz.md` (accepted, Amendment 2026-10-04) — Idempotenz-/Dedupe-Vertrag; relevant für wiederholbare Datenmigrationen
- `docs/audit/2026-11-16-deep-dive-findings.md:19, 86-87, 995, 997, 1003-1007` — L0-001/L0-002, R2D-004/006, Expand/Contract-Praxis
- `docs/superpowers/plans/2026-11-16-deep-dive-remediation.md:59-60, 187-197` — S0.3-Gate und L0-002-Präzedenz
- `backend/persistence/migrations/0141_backfill_allocations.py:20-31, 104-171, 174-186, 216-224`
- `backend/persistence/tests/test_backfill_allocations_reverse_guard.py:19-38`
- `backend/audit/archive.py:345-364`; `backend/audit/migrations/0020_retention_purge_function.py:1,74,226`; `backend/audit/migrations/0002_append_only_trigger.py:40-42`
- `deploy/verify-restore.sh:1-27, 109-137, 209-305`; `docs/DEPLOY_RUNBOOK.md:25-77, 303, 345-360`
- `deploy/docker-compose.yml:588, 783, 787, 885, 902-906, 925, 1027, 1146`
- `backend/persistence/migrations/0080_tracelink_semantics_fields.py:15-16,49,74`; `0116_index_hygiene_1411.py:15-20,37,45`; `0118_uid_workspace_unique_constraints.py:53-58`
- `docs/se/attribut/attribut-migrationssystematik.md:1-9` — AWMS-spezifisch, nicht dieses Runbook

*Erstellt: 2026-11-18 · Autor: `sre-engineer` · S5.3 WP-4 · Kein Migrationscode geändert.*
