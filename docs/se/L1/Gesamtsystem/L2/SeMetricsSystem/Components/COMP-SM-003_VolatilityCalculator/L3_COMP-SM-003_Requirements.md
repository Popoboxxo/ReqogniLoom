# L3 VolatilityCalculator Requirements

> **Level:** L3 (Komponenten-Anforderungen)
> **Komponente:** COMP-SM-003 — VolatilityCalculator
> **Parent-System:** SeMetricsSystem (L2)
> **Status:** Entwurf

---

## Verantwortlichkeit

Berechnet Requirements Volatility: zählt Änderungsereignisse (Operation `update`/`workflow_transition`, EntityType `Requirement`) je Requirement aus AuditLog-Quelldaten, berechnet Gesamt-Änderungsrate (total_changes / total_requirements), erstellt geordnete Top-10-Volatile-Liste.

## Zugeordnete L2-Anforderungen

| REQ-L2 | Anforderungstext (Kurzform) |
|--------|-----------------------------|
| REQ-L2-SM-003 | Requirements-Volatility-Berechnung aus AuditLog-Quelldaten |
| REQ-L2-SM-008 | Read-Modell ohne Seiteneffekte |

## Interne Schnittstellen

| IF-ID | Richtung | Gegenstelle | Vertrag |
|-------|----------|-------------|---------|
| IF-SM-INT-002 | eingehend | COMP-SM-002 MetricsAggregator | `calculate(audit_entries: list[AuditEntry], timeframe) -> VolatilityResult` |

## Externe Schnittstellen (Systemgrenze)

Keine — der VolatilityCalculator operiert ausschließlich auf bereits abgerufenen Quelldaten; der Datenzugriff auf IF-L1-044 erfolgt durch COMP-SM-002.

---

## L3 Komponenten-Anforderungen

### REQ-L3-SM003-001: Berechnung von Gesamt-Änderungsrate und Durchschnitt

Der VolatilityCalculator SHALL aus der übergebenen Liste von `AuditEntry`-Objekten ausschließlich Einträge mit `entity_type = "Requirement"` und `operation IN ("update", "workflow_transition")` berücksichtigen. Er SHALL `total_changes` (Anzahl gefilterte Einträge), `total_requirements` (Anzahl distinkte `entity_id`-Werte) und `avg_changes_per_req` (total_changes / total_requirements, auf zwei Nachkommastellen gerundet) berechnen. Bei `total_requirements = 0` SHALL `avg_changes_per_req` als `0.0` zurückgegeben werden (keine Division durch Null).

**Priority:** mandatory
**Acceptance Criteria:**
- [ ] 100 requirements, 50 change entries → `{total_changes: 50, total_requirements: 100, avg_changes_per_req: 0.50}`
- [ ] Entries with `entity_type != "Requirement"` are excluded from counts
- [ ] Entries with `operation` not in `["update", "workflow_transition"]` are excluded
- [ ] 0 requirements in timeframe → `{total_changes: 0, total_requirements: 0, avg_changes_per_req: 0.0}` (no ZeroDivisionError)

---

### REQ-L3-SM003-002: Top-10-Volatile-Liste

Der VolatilityCalculator SHALL eine geordnete Liste der bis zu 10 Requirements mit der höchsten Änderungszahl im Berechnungszeitraum erstellen. Die Liste SHALL absteigend nach Änderungszahl sortiert sein. Jeder Eintrag SHALL `requirement_id` und `change_count` enthalten. Bei weniger als 10 Requirements mit Änderungen SHALL die Liste entsprechend kürzer sein.

**Priority:** mandatory
**Acceptance Criteria:**
- [ ] 15 requirements with changes → top-10 list contains exactly 10 entries, ordered descending by change_count
- [ ] 3 requirements with changes → list contains exactly 3 entries
- [ ] No changes in timeframe → `top10_volatile: []`
- [ ] Each entry contains `requirement_id` and `change_count`
- [ ] Requirements with equal change_count are ordered deterministically (e.g., by requirement_id ascending)

---

*Erstellt durch se-requirements-Agent (L3-Component) | ReqFlow SE-Kaskade | 2026-06-21*
