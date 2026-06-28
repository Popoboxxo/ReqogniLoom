# L3 SchemaMigrationEngine Requirements

> **Level:** L3 (Komponenten-Anforderungen)
> **Komponente:** COMP-PL-004 — SchemaMigrationEngine
> **Parent-System:** PersistenceLayerSystem (L2)
> **Status:** Entwurf

---

## Verantwortlichkeit

Django-Migrationen (Vorwaerts/Rueckwaerts), idempotentes Schema-Management, Deployment-Reproduzierbarkeit. Stellt sicher, dass das Datenbankschema deterministisch aus dem Quellcode reproduzierbar ist und jede Migration rueckwaerts abrollbar ist.

## Zugeordnete L2-Anforderungen

| REQ-L2 | Anforderungstext (Kurzform) |
|--------|-----------------------------|
| REQ-L2-PL-006 | Idempotente Datenbank-Migrationen (Vorwaerts + Rueckwaerts) |

## Interne Schnittstellen

| IF-ID | Richtung | Gegenstelle | Vertrag |
|-------|----------|-------------|---------|
| IF-PL-INT-003 | ausgehend | COMP-PL-001 | Django-Migrationen generiert aus `models.py` |
| IF-PL-INT-004 | ausgehend | COMP-PL-005 | Migrationen enthalten `AddIndex`, `RemoveIndex` Operationen |

## Externe Schnittstellen (falls Komponente an Systemgrenze)

| IF-ID | Richtung | Gegenstelle | Typ | Vertrag |
|-------|----------|-------------|-----|---------|
| IF-PL-EXT-IN-009 | eingehend | PostgreSQL-Verbindung | physical | TCP, .env Konfiguration |
| IF-PL-EXT-OUT-001 | ausgehend | PostgreSQL | TCP / psycopg2 | DDL-Statements (CREATE TABLE, ALTER TABLE, CREATE INDEX) |

## L3 Komponenten-Anforderungen

### REQ-L3-PL004-001: Vollstaendige und Squash-freie Migrationshistorie


**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.


Die SchemaMigrationEngine MUSS eine lueckenlose Migrationshistorie in `requirements_app/migrations/` bereitstellen, die auf einer leeren Datenbank das vollstaendige Schema aller 13 Entitaeten erzeugt. `python manage.py makemigrations --check` MUSS ohne Fehler und ohne neue Migrationen enden (Schema und Migrationen sind synchron). Keine Migration DARF durch Squash-Migrationen ersetzt werden, solange die Originalmigrationen noch in produktiven Deployments aktiv sind.

**Priority:** mandatory
**Acceptance Criteria:**
- [ ] `python manage.py makemigrations --check` exits with code 0
- [ ] `python manage.py migrate` on empty DB creates all 13 entity tables
- [ ] Migration chain has no gaps (each migration references exactly one previous migration)
- [ ] `python manage.py showmigrations` shows all migrations as applied

---

### REQ-L3-PL004-002: Rueckwaertspfad fuer jede Migration


**Implementation State:** Implemented
**Review Findings:** Implementierung gefunden, aber keine Tests.
**Test Status:** Missing
**Remarks:** Testabdeckung fehlt.


Die SchemaMigrationEngine MUSS fuer jede Migration eine `reverse_migration`-Methode bereitstellen, die den Vorwaertspfad vollstaendig umkehrt. Automatisch generierte Rueckwaertspfade von Django DUERFEN nur dann verwendet werden, wenn sie von Django garantiert sind (AddField, CreateModel); fuer komplexe Operationen (RawSQL, RunPython) MUSS ein expliziter Rueckwaertspfad implementiert werden. `python manage.py migrate <app> zero` MUSS auf einer vollstaendig migrierten Datenbank fehlerfrei ausfuehren.

**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Every migration has a non-`migrations.RunSQL.noop` reverse operation
- [ ] `python manage.py migrate requirements_app zero` succeeds on fully migrated DB
- [ ] All tables removed after migrate to zero
- [ ] CI: forward migration + rollback to zero + re-migration completes without errors

---

### REQ-L3-PL004-003: Migrations-CI-Gate im Deployment-Pipeline


**Implementation State:** Not Implemented
**Review Findings:** Keine Implementierung oder Tests im Code gefunden.
**Test Status:** Missing
**Remarks:** Sollte implementiert werden.


Die SchemaMigrationEngine MUSS in der CI-Pipeline einen automatisierten Gate-Check ausfuehren, der (1) `makemigrations --check` prueft, (2) `migrate` auf einer leeren Test-DB ausfuehrt und (3) `migrate <app> zero` zur Verifikation des Rueckwaertspfads ausfuehrt. Der Gate-Check MUSS fehlschlagen und den Build blockieren, wenn einer der drei Schritte einen Nicht-Null-Exit-Code zurueckgibt.

**Priority:** mandatory
**Acceptance Criteria:**
- [ ] CI step "migration-check" exists and runs on every PR
- [ ] Missing migration (`makemigrations --check` fails): CI build blocked
- [ ] Forward migration fails: CI build blocked
- [ ] Reverse migration fails: CI build blocked

---

---
*Erstellt durch se-requirements-Agent (L3-Component) | ReqFlow SE-Kaskade | 2026-06-21*
