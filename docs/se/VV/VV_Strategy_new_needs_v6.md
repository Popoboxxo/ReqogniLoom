# V&V Strategie — Neue Needs v6 (SN-30 bis SN-35)

> **Level:** System V&V (L1 Akzeptanz + L2 Integration + Ln Unit)
> **Scope:** REQ-L0-030, REQ-L0-032 bis REQ-L0-035 -> REQ-L1-043 bis REQ-L1-048
> **Datum:** 2026-06-28
> **Erstellt durch:** se-requirements-Agent | SE-Kaskade V&V

---

## 1. Kontext & Kaskaden-Ueberblick

Diese Strategie dokumentiert den rechten Fluegel des V-Modells fuer alle Anforderungen,
die aus dem User-Feedback zur reqflow_ontology_analysis.md (2026-06-28) entstanden sind.

## 2. Traceability-Zusammenfassung (L0 -> L1 -> L2 -> V&V)

| REQ-L0 | REQ-L1 | REQ-L2 | L1-SAT |
|--------|--------|--------|--------|
| REQ-L0-030 | REQ-L1-043 | REQ-L2-TE-016 | L1-SAT-043 |
| REQ-L0-032 | REQ-L1-044 | REQ-L2-AS-033 | L1-SAT-044 |
| REQ-L0-033 | REQ-L1-045 | REQ-L2-BL-010, REQ-L2-RF-017 | L1-SAT-045 |
| REQ-L0-034 | REQ-L1-046 | REQ-L2-BL-011, REQ-L2-RF-017 | L1-SAT-046 |
| REQ-L0-035 | REQ-L1-047 | REQ-L2-TE-017 | L1-SAT-047 |
| REQ-L1-001 (Feedback) | REQ-L1-048 | REQ-L2-RF-016 | L1-SAT-048 |

## 3. L1 System-Akzeptanztests

- L1-SAT-043: Suspect-Link-Propagierung E2E
- L1-SAT-044: Semantisches Glossar E2E (API + UI)
- L1-SAT-045: Sandbox Branching + Merge E2E
- L1-SAT-046: Backup/Restore + Baseline-Diff E2E
- L1-SAT-047: Cross-Level-TraceLink mit/ohne Begruendung
- L1-SAT-048: Level View alle Artefakttypen (Playwright)

## 4. Offene ADR-Entscheidungen vor Implementierungsstart

- ADR-Sandbox-Mechanismus: Git-intern vs. Event-Sourcing vs. Copy-on-Write
- ADR-Event-Bus: Django Signals vs. Celery vs. Redis Pub/Sub fuer requirement.updated
- ADR-GlossaryStorage: Separate DB-Tabelle vs. JSONB-Feld im Workspace-Modell

---

*Erstellt durch se-requirements-Agent | 2026-06-28 | SE-Kaskade V&V neue Needs v6*
