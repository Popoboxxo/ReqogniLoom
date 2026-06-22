---
step: architecture
agent: se-architect
iteration: 1
status: done
timestamp: "2026-06-22T13:15:00Z"
schema_version: "1.0.0"
---
# L3 SchemaMigrationEngine Architecture

> **Level:** L3 (Component white-box / Terminal)
> **Component:** COMP-PL-004_SchemaMigrationEngine
> **Parent:** L2_PersistenceLayerSystem_Architecture.md
> **Datum:** 2026-06-22
> **Status:** entworfen
> **Designation:** component (terminal)
> **decomposition_status:** terminal

---

## 1. Verantwortlichkeit

Die SchemaMigrationEngine verwaltet die Django-Migrationen für alle 13 Entity-Modelle. Sie stellt sicher, dass das Datenbankschema deterministisch aus dem Quellcode reproduzierbar ist, dass Migrationen idempotent sind, und dass jede Migration rückwärts abrollbar ist. Sie integriert mit dem CI/CD-Pipeline für Validierung.

---

## 2. White-Box Design (Interne Struktur)

### 2.1 Klassen und Module

- **Migration Files:** `requirements_app/migrations/000X_<description>.py` — Django Auto-Migrations
- **`django.db.migrations.Migration` (Subklassen):** Jede Migration erbt von Django's Migration-Klasse
- **Reverse-Methoden:** Explizite `reverse_migration()` für komplexe Operationen (RawSQL, RunPython)
- **CI-Gate-Skript:** `scripts/ci/migration-check.sh` — prüft Migrationen im Deployment-Prozess

### 2.2 Datenstrukturen

**Migrations-Struktur:**
```
requirements_app/migrations/
  __init__.py
  0001_initial.py  → CreateModel (Tenant, User, Role, Workspace)
  0002_artifact.py → CreateModel (Artifact with parent FK)
  0003_indexes.py  → AddIndex (parent_id BTree, ...)
  0004_requirement.py → CreateModel (Requirement, TraceLink)
  0005_...py  → weitere Modelle und Indizes
  ...
```

**Migrations-Typen:**
- `CreateModel` — definiert neue Entity-Tabelle (auto-reverse via Django)
- `AddField` — fügt Spalte zu bestehender Tabelle (auto-reverse via Django)
- `AddIndex` — erstellt Index (auto-reverse via RemoveIndex)
- `RunPython` — benutzerdefinierte Python-Logik (MUSS explizite Reverse implementieren)
- `RunSQL` — Raw SQL-Operationen (MUSS explizite Reverse implementieren)

---

## 3. Erfüllung der Anforderungen

| REQ-L3 | Implementierungs-Ansatz |
|--------|-------------------------|
| REQ-L3-PL004-001 (Vollständige, Squash-freie Migrationshistorie) | Migrations-Dateien in `requirements_app/migrations/` ohne Lücken. `makemigrations --check` bestätigt Synchronisierung. Keine Squash-Migrationen in aktiven Deployments. |
| REQ-L3-PL004-002 (Rückwärtspfad für jede Migration) | Django-generierte Reverse (CreateModel, AddField) automatisch. RunPython- und RunSQL-Operationen mit expliziten Reverse-Methoden. `migrate <app> zero` erfolgreich auf vollständig migrierten DB. |
| REQ-L3-PL004-003 (Migrations-CI-Gate) | CI-Schritt "migration-check" prüft `makemigrations --check`, Forward-Migration auf Test-DB, Rollback zu zero. Fehlschlag blockiert Build. |

---

## 4. Schnittstellen-Implementierung

**Eingänge (Inbound):**
- **IF-PL-INT-003:** COMP-PL-001 stellt Modell-Definitionen bereit, aus denen `makemigrations` automatisch Migrations-Dateien generiert.
- **IF-PL-INT-004:** COMP-PL-005 fordert ggf. Migrationen mit Index-Operationen (AddIndex, RemoveIndex).

**Ausgänge (Outbound):**
- **IF-PL-EXT-OUT-001:** Migrations werden auf PostgreSQL-Datenbank via psycopg2 / Django Backend ausgeführt (DDL-Statements: CREATE TABLE, ALTER TABLE, CREATE INDEX).

---

## 5. Architectural Rationale

**ADR-L3-PL-005 — Auto-Migration mit explizitem Reverse für komplexe Ops**

*Entscheidung:* Django's `makemigrations` wird für Standard-Modell-Änderungen verwendet. Für komplexe Operationen (Datenmigration, Schema-Transformation) werden explizite `RunPython`/`RunSQL` mit Reverse implementiert.

*Alternative (abgelehnt):* Alle Migrationen manuell schreiben. Grund: Fehleranfälligkeit, höherer Maintenance-Aufwand, leicht zu vergessen.

*Rationale:* REQ-L3-PL004-001 und REQ-L3-PL004-002 werden erfüllt: Automatische Generierung für 90% der Fälle, explizite Kontrolle wo nötig.

---

**ADR-L3-PL-006 — CI-Gate mit drei Prüfschritten**

*Entscheidung:* CI-Check führt `makemigrations --check`, Forward-Migration auf Test-DB, und Rollback zu zero aus. Alle drei müssen bestehen.

*Alternative (abgelehnt):* Nur `makemigrations --check` prüfen. Grund: Nicht ausreichend — Check sagt nur, dass Migrationen generierbar sind, nicht dass sie auf echten Datenbanken funktionieren.

*Rationale:* REQ-L3-PL004-003 fordert explizit alle drei Schritte. Dieser umfassende Check verhindert unerwartete Fehler im Deployment.

---

*Erstellt durch se-architect-Agent | ReqFlow SE-Kaskade L2→L3 | 2026-06-22*
*Designation: component (terminal) — decomposition_status: terminal*
