---
step: architecture
agent: se-architect
iteration: 1
status: done
timestamp: "2026-06-22T13:10:00Z"
schema_version: "1.0.0"
---
# L3 TransactionCoordinator Architecture

> **Level:** L3 (Component white-box / Terminal)
> **Component:** COMP-PL-003_TransactionCoordinator
> **Parent:** L2_PersistenceLayerSystem_Architecture.md
> **Datum:** 2026-06-22
> **Status:** entworfen
> **Designation:** component (terminal)
> **decomposition_status:** terminal

---

## 1. Verantwortlichkeit

Der TransactionCoordinator stellt sicher, dass alle schreibenden ORM-Operationen (INSERT, UPDATE, DELETE) innerhalb von `transaction.atomic()`-Blöcken ausgefuehrt werden. Er garantiert ACID-Konformität und verhindert Teilzustände in der Datenbank. Sein Design unterstützt Single-Entity- und Multi-Entity-Transaktionen sowie Rollback bei Fehlern.

---

## 2. White-Box Design (Interne Struktur)

### 2.1 Klassen und Module

- **`AtomicTransactionDecorator` (Dekorator):** Wraps Service-Methoden in `transaction.atomic()`.
- **`TransactionContextManager` (Klasse):** Explizites Context-Manager-Interface für manuelle Kontrolle.
- **`TransactionTimeoutError` (Exception-Klasse):** Signalisiert Timeout bei langdauernden Transaktionen.
- **Service-Layer-Methoden:** Alle Methoden, die ORM-Writes ausführen, nutzen entweder den Dekorator oder den Context Manager.

### 2.2 Datenstrukturen

**Dekorator-Signatur:**
```python
@atomic_transaction
def create_requirement(self, title, description, ...):
    # Implizites transaction.atomic() wrapping
    requirement = Requirement(title=title, ...)
    requirement.save()  # atomic
    return requirement
```

**Context Manager-Signatur:**
```python
def batch_decompose(self, artifacts):
    with TransactionContextManager(timeout_seconds=30) as txn:
        for artifact in artifacts:
            # Alle Saves/Deletes implizit atomic
            child = Artifact.objects.create(parent=artifact, ...)
        # Bei Exception: rollback; bei erfolgreicher Iteration: commit
```

**Timeout-Konfiguration:**
- `DB_TRANSACTION_TIMEOUT_SECONDS` Umgebungsvariable (Standard: 30 Sekunden)
- Implementiert via `signal.alarm()` (Unix) oder Thread-Timeout (Cross-Platform)

---

## 3. Erfüllung der Anforderungen

| REQ-L3 | Implementierungs-Ansatz |
|--------|-------------------------|
| REQ-L3-PL003-001 (Verpflichtende Transaktionskapslung) | Alle schreibenden Service-Methoden sind mit `@atomic_transaction` Dekorator versehen ODER nutzen `with TransactionContextManager()`. Django's Autocommit ist deaktiviert für Single-Entity-Ops. Multi-Entity-Ops nutzen einen übergreifenden `atomic()`-Block. |
| REQ-L3-PL003-002 (Vollständiger Rollback bei Fehlern) | Bei jeder unbehandelten Exception in `atomic()` wird Rollback garantiert. Keine Teilzustände persistiert. Nested `atomic()` verwendet Savepoints korrekt. |
| REQ-L3-PL003-003 (Transaktions-Timeout) | `DB_TRANSACTION_TIMEOUT_SECONDS` steuert Timeout. Nach Timeout wird `TransactionTimeoutError` geworfen und Rollback erzwungen. Default: 30 Sekunden. |

---

## 4. Schnittstellen-Implementierung

**Eingänge (Inbound):**
- **IF-PL-INT-002:** Service-Layer-Methoden wenden Dekorator oder Context Manager an (kein expliziter Aufruf durch Gegenstelle, sondern Framework-Pattern).

**Ausgänge (Outbound):**
- **Keine direkten Ausgänge.** Der TransactionCoordinator ist ein Cross-Cutting Concern; er modifiziert Service-Methoden, delegiert aber letztendlich zu COMP-PL-001 (EntitySchemaManager) für ORM-Operationen.

---

## 5. Architectural Rationale

**ADR-L3-PL-003 — Dekorator + Context Manager Hybrid-Pattern**

*Entscheidung:* Zwei parallele Muster: Dekorator für typische Service-Methoden, Context Manager für komplexe mehrstufige Operationen. Beide nutzen Django's `transaction.atomic()`.

*Alternative (abgelehnt):* Nur ein Pattern (z.B. nur Dekorator). Grund: Service-Layer ist heterogen — manche Methoden sind einfach, andere brauchen mehrere Save-Zyklen und Fehlerprüfung dazwischen.

*Rationale:* REQ-L3-PL003-001 und REQ-L3-PL003-002 sind flexibel genug, um beide Patterns zu erlauben. Hybrid-Ansatz deckt alle Use-Cases ab.

---

**ADR-L3-PL-004 — Timeout via Umgebungsvariable statt Hardcode**

*Entscheidung:* Timeout-Wert ist konfigurierbar via `DB_TRANSACTION_TIMEOUT_SECONDS`.

*Alternative (abgelehnt):* Hardcoded 30 Sekunden überall. Grund: Nicht alle Operationen brauchen die gleiche Timeout-Länge; Deployment-Szenarien können unterschiedliche Werte erfordern.

*Rationale:* REQ-L3-PL003-003 fordert explizit Konfigurierbarkeit. Environment-basierte Konfiguration ist Standard in Django.

---

*Erstellt durch se-architect-Agent | ReqFlow SE-Kaskade L2→L3 | 2026-06-22*
*Designation: component (terminal) — decomposition_status: terminal*
