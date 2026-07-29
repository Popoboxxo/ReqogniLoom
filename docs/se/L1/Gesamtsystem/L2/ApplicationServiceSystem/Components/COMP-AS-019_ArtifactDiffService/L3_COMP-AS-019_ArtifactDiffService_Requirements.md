decomposition_status: terminal

---
component_id: COMP-AS-019
parent_requirement: REQ-L2-AS-032
parent_system: ApplicationServiceSystem
designation: component
status: draft
timestamp: "2026-06-27T21:00:00Z"
---
# COMP-AS-019 — ArtifactDiffService

## Verantwortlichkeit

Der ArtifactDiffService berechnet ein strukturiertes JSON-Diff zwischen zwei beliebigen Versionen eines Artefakts. Er vergleicht Feld-Level-Änderungen (hinzugefügt, geändert, gelöscht) und stellt Markdown-Felder als Text-Diff dar.

## Schnittstellen

| IF-ID | Richtung | Gegenstelle | Vertrag |
|-------|----------|-------------|---------|
| IF-AS-EXT-IN-001 | eingehend | RestApiAdapter | `GET /artifacts/{id}/diff?from=v1&to=v2` |
| IF-AS-EXT-OUT-007 | ausgehend | PersistenceLayer | Django ORM — Versionshistorie laden |

## Teststrategie

- Diff-Test: Geändertes Feld → alt→neu im Diff enthalten
- Versions-Test: Vergleich nicht-aufeinanderfolgender Versionen → korrekt
- Markdown-Test: Markdown-Feld → Text-Diff (kein AST-Diff)
- Performance-Test: 50 Felder → Diff ≤ 500ms

---

*Erstellt durch se-architect-Agent | ReqFlow SE-Kaskade Phase 3 | 2026-06-27*
