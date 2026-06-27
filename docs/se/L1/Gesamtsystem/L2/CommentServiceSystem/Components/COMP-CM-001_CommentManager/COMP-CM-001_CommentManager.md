---
component_id: COMP-CM-001
parent_requirement: REQ-L2-CM-001
parent_system: CommentServiceSystem
designation: component
status: draft
timestamp: "2026-06-27T21:00:00Z"
---
# COMP-CM-001 — CommentManager

## Verantwortlichkeit

Der CommentManager verwaltet CRUD-Operationen für Kommentare an Artefakten (Requirement, ArchitectureElement, TestCase). Er unterstützt Thread-Strukturen (Top-Level-Kommentar oder Antwort) und versioniert Kommentar-Änderungen.

## Schnittstellen

| IF-ID | Richtung | Gegenstelle | Vertrag |
|-------|----------|-------------|---------|
| IF-CM-EXT-IN-001 | eingehend | ApplicationService | `create_comment(artifact_id, text, parent_comment_id?, ctx) -> Comment` |
| IF-CM-EXT-OUT-001 | ausgehend | AuditLogSystem | `log_write(op, entity_id, ctx)` |
| IF-CM-EXT-OUT-003 | ausgehend | PersistenceLayer | Django ORM — Kommentar-CRUD |

## Teststrategie

- Thread-Test: Top-Level-Kommentar + Antwort → Thread-Struktur korrekt
- Versionierungs-Test: Kommentar bearbeiten → alte Version bleibt erhalten
- Berechtigungs-Test: Nicht-Autor versucht Bearbeitung → HTTP 403

---

*Erstellt durch se-architect-Agent | ReqFlow SE-Kaskade Phase 3 | 2026-06-27*
