---
component_id: COMP-CM-003
parent_requirement: REQ-L2-CM-003
parent_system: CommentServiceSystem
designation: component
status: draft
timestamp: "2026-06-27T21:00:00Z"
---
# COMP-CM-003 — NotificationDispatcher

## Verantwortlichkeit

Der NotificationDispatcher erzeugt In-App-Benachrichtigungen bei @Mentions registrierter Nutzer. Benachrichtigungen enthalten Kommentar-ID, Artefakt-Referenz und Mention-Autor. Sie sind via REST-API abrufbar und als gelesen markierbar.

## Schnittstellen

| IF-ID | Richtung | Gegenstelle | Vertrag |
|-------|----------|-------------|---------|
| IF-CM-EXT-IN-001 | eingehend | COMP-CM-002 (MentionResolver) | `dispatch_notification(user_id, comment_id, artifact_id, ctx)` |
| IF-CM-EXT-OUT-001 | ausgehend | AuditLogSystem | `log_write(op="notification_created", entity_id, ctx)` |
| IF-CM-EXT-OUT-003 | ausgehend | PersistenceLayer | Django ORM — Notification-CRUD |

## Teststrategie

- Notification-Test: @Mention → Notification für genannten Nutzer erzeugt
- Abruf-Test: GET /notifications → Notification mit korrekten Metadaten
- Gelesen-Test: PUT /notifications/{id}/read → Status auf "read" gesetzt

---

*Erstellt durch se-architect-Agent | ReqFlow SE-Kaskade Phase 3 | 2026-06-27*
