decomposition_status: terminal

---
component_id: COMP-AT-005
parent_requirement: REQ-L2-AT-017, REQ-L2-AT-018
parent_system: AuthAndTenancySystem
designation: component
status: draft
timestamp: "2026-06-27T21:00:00Z"
---
# COMP-AT-005 — ItemPermissionStore

## Verantwortlichkeit

Der ItemPermissionStore verwaltet Item-Level-Berechtigungsregeln (Subsystem- oder Artefakt-Ebene) und stellt diese als PostgreSQL Row-Level Security (RLS) Policies bereit. Er implementiert einen Permission-Cache (TTL: 60s) zur Reduktion der Evaluierungs-Latenz und invalidiert den Cache bei Regel-Änderungen sofort.

## Schnittstellen

| IF-ID | Richtung | Gegenstelle | Vertrag |
|-------|----------|-------------|---------|
| IF-AT-EXT-IN-001 | eingehend | RestApiAdapter | `POST /permissions/item` (Admin-Request) |
| IF-AT-EXT-OUT-003 | ausgehend | RestApiAdapter / McpServer | Berechtigungsentscheid allow/deny |
| IF-AT-EXT-OUT-004 | ausgehend | PersistenceLayer | Django ORM — Regel-CRUD + RLS-Policy-Management |

## Teststrategie

- Regel-Test: Admin konfiguriert Regel → Nutzer sieht nur erlaubte Artefakte
- Vorrang-Test: Workspace-Admin → Item-Level-Regel überschrieben (Vorrang)
- Performance-Test: 100 Regeln → max. 10% Overhead auf API-Response-Zeiten
- Cache-Test: Regel geändert → Cache sofort invalidiert

---

*Erstellt durch se-architect-Agent | ReqFlow SE-Kaskade Phase 3 | 2026-06-27*
