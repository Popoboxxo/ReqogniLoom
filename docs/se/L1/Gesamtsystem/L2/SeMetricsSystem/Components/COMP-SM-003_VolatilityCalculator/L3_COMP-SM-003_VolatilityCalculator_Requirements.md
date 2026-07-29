---
step: architecture
agent: se-architect
iteration: 1
status: done
timestamp: "2026-06-22T10:35:00Z"
schema_version: "1.0.0"
---

# L3 VolatilityCalculator Architecture

> **Level:** L3 (Component white-box / Terminal)
> **Component:** COMP-SM-003_VolatilityCalculator
> **Parent:** L2_SeMetricsSystem_Architecture.md
> **Datum:** 2026-06-22
> **Status:** entworfen
> **Designation:** component (terminal)
> **decomposition_status:** terminal — component-level leaf, no further SE decomposition

---

## 1. Verantwortlichkeit

Der VolatilityCalculator berechnet die Requirements-Volatilität aus AuditLog-Quelldaten. Er zählt Änderungsereignisse (operations update/workflow_transition auf entity_type Requirement) je Requirement, berechnet Gesamt-Änderungsrate (total_changes / total_requirements) und erstellt eine Top-10-Volatile-Liste, sortiert absteigend nach Änderungszahl.

---

## 2. White-Box Design (Interne Struktur)

Da dies eine terminale Komponente ist, beschreibt die White-Box hier die internen Software-Klassen und Module.

### 2.1 Klassen und Module

- **`VolatilityCalculator` (Klasse):** Hauptklasse mit Methode `calculate(audit_entries: list[AuditEntry], timeframe) -> VolatilityResult`.
- **`AuditEntryFilter` (Klasse):** Filtert Entries auf entity_type="Requirement" und operation in ["update", "workflow_transition"].
- **`ChangeCountAggregator` (Klasse):** Zählt Changes pro Requirement-ID. Berechnet total_changes, total_requirements, avg_changes_per_req.
- **`Top10Extractor` (Klasse):** Sortiert nach Änderungszahl, extrahiert Top 10. Bei Gleichstand: deterministisch nach requirement_id.

### 2.2 Datenstrukturen

- **`AuditEntry` (Pydantic Model):** {entity_id, entity_type, operation, timestamp, actor_id}.
- **`VolatilityResult` (Pydantic Model):** {total_changes, total_requirements, avg_changes_per_req (float, 2 Dezimalstellen), top10_volatile: [{requirement_id, change_count}]}.

---

## 3. Erfüllung der Anforderungen

| REQ-L3 | Implementierungs-Ansatz |
|--------|-------------------------|
| REQ-L3-SM003-001 (Gesamt-Änderungsrate) | AuditEntryFilter filtert auf entity_type="Requirement" und operation in ["update", "workflow_transition"]. ChangeCountAggregator zählt gefilterte Einträge → total_changes, distinct entity_ids → total_requirements, Ratio → avg_changes_per_req (2 Dezimalstellen). Bei total_requirements=0: avg=0.0 (kein ZeroDivisionError). |
| REQ-L3-SM003-002 (Top-10-Liste) | Top10Extractor sortiert Requirements nach Änderungszahl absteigend. Limitiert auf 10 Einträge. Jeder Eintrag: {requirement_id, change_count}. Bei Gleichstand: deterministisch nach requirement_id aufsteigend. |

---

## 4. Schnittstellen-Implementierung

**Eingänge (Inbound):**
- **IF-SM-INT-002:** Von COMP-SM-002 (MetricsAggregator): `calculate(audit_entries: list[AuditEntry], timeframe) -> VolatilityResult`.

**Ausgänge (Outbound):**
- Keine externen Schnittstellen. Calculator operiert stateless auf Input-Daten.

---

## 5. Architectural Rationale

**ADR-L3-SM3-01 — Separate Filter-, Aggregator-, Extractor-Klassen**

*Entscheidung:* VolatilityCalculator delegiert an spezialisierte Klassen (Filter, Aggregator, Extractor) statt inline-Logik.

*Rationale:* Erfüllt Single-Responsibility und Testbarkeit. Jede Klasse hat eine klare Rolle. Alternative: Monolithische Methode → würde bei Changes und Erweiterungen fragil werden.

---

**ADR-L3-SM3-02 — Zwei-Dezimalstellen-Rounding für avg_changes_per_req**

*Entscheidung:* avg_changes_per_req wird auf 2 Dezimalstellen gerundet (Standard-Python round()).

*Rationale:* Erfüllt REQ-L3-SM003-001 ("auf zwei Nachkommastellen gerundet"). Konsistent mit Common-Precision für Metriken. Alternative: Unbegrenzte Dezimalstellen → würde JSON-Response bloaten und Vergleiche schwächen.

---

**ADR-L3-SM3-03 — Deterministische Sortierung bei Top-10-Gleichstand**

*Entscheidung:* Bei mehreren Requirements mit gleichem change_count: stabiles Sekundär-Sorting nach requirement_id aufsteigend.

*Rationale:* Erfüllt REQ-L3-SM003-002 ("ordered deterministically (e.g., by requirement_id ascending)"). Verhindert nicht-deterministische Ergebnisse. Alternative: Beliebige Reihenfolge → würde Tests und Debugging erschweren.

---

*Erstellt durch se-architect-Agent | ReqFlow SE-Kaskade L2→L3 | 2026-06-22*
*Designation: component (terminal) — decomposition_status: terminal*
