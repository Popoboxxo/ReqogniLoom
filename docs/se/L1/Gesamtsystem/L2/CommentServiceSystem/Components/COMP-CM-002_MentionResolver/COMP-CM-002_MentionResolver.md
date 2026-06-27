---
component_id: COMP-CM-002
parent_requirement: REQ-L2-CM-002
parent_system: CommentServiceSystem
designation: component
status: draft
timestamp: "2026-06-27T21:00:00Z"
---
# COMP-CM-002 — MentionResolver

## Verantwortlichkeit

Der MentionResolver parst @Mention-Syntax in Kommentar-Texten und löst Mention-Namen auf registrierte Nutzer auf. Bei nicht-registrierten Namen wird ein Validierungshinweis erzeugt, der Kommentar jedoch trotzdem gespeichert.

## Schnittstellen

| IF-ID | Richtung | Gegenstelle | Vertrag |
|-------|----------|-------------|---------|
| IF-CM-EXT-IN-001 | eingehend | ApplicationService | `resolve_mentions(comment_id, text, ctx) -> MentionResult` |
| IF-CM-EXT-OUT-002 | ausgehend | AuthAndTenancySystem | `lookup_user(username, tenant_id) -> User?` |
| IF-CM-EXT-OUT-003 | ausgehend | PersistenceLayer | Django ORM — Mention-Einträge speichern |

## Teststrategie

- Mention-Test: @registrierter_nutzer → Mention-Eintrag mit user_id
- Nicht-registriert-Test: @unbekannt → Validierungshinweis, Kommentar trotzdem gespeichert
- Deduplizierungs-Test: Doppelte @Mentions → dedupliziert

---

*Erstellt durch se-architect-Agent | ReqFlow SE-Kaskade Phase 3 | 2026-06-27*
