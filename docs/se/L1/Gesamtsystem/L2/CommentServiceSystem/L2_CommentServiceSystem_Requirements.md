# L2 CommentService Requirements

> **Level:** L2 (Subsystem-Anforderungen)
> **System:** CommentServiceSystem (NEU)
> **Parent:** L1_Gesamtsystem_Requirements.md
> **Datum:** 2026-06-27
> **Status:** formalisiert
> **Designation:** system (L3-Zerlegung erforderlich)

---

## Traceability

- Abgeleitet von: REQ-L1-037 (primär)
- Ziel: L3-Zerlegung in COMP-CM-001 (CommentManager), COMP-CM-002 (MentionResolver), COMP-CM-003 (NotificationDispatcher)

---

## Externe Schnittstellen (Systemgrenze)

| ID | Richtung | Typ | Beschreibung |
|----|----------|-----|--------------|
| IF-CM-EXT-IN-001 | input | data | Kommentar-CRUD vom ApplicationService (create/list/update) |
| IF-CM-EXT-OUT-001 | output | data | Audit-Log-Einträge an AuditLogSystem |
| IF-CM-EXT-OUT-002 | output | data | Nutzer-Lookup an AuthAndTenancySystem (@Mention-Auflösung) |
| IF-CM-EXT-OUT-003 | output | data | Persistenz an PersistenceLayer |

---

## L2 Subsystem-Anforderungen

### REQ-L2-CM-001: Kommentar-CRUD mit Thread-Struktur

Der CommentService SHALL CRUD-Operationen für Kommentare an Artefakten (Requirement, ArchitectureElement, TestCase) bereitstellen. Kommentare können als Top-Level-Kommentar oder als Antwort in einem bestehenden Thread erstellt werden. Jeder Kommentar enthält Autor, Zeitstempel und Text. Kommentar-Änderungen werden versioniert.

**Domain:** software
**Priority:** optional
**arch_impact:** false
**Acceptance Criteria:**
- [ ] Kommentar kann zu Requirement, ArchitectureElement und TestCase erstellt werden
- [ ] Antwort auf bestehenden Kommentar erzeugt Thread-Struktur (parent_comment_id)
- [ ] Kommentar-Änderungen werden versioniert (alte Versionen bleiben erhalten)
- [ ] Kommentar-Threads sind via REST-API lesbar (GET /artifacts/{id}/comments)
- [ ] Kommentar kann nur vom Autor oder Admin bearbeitet/gelöscht werden

**Interfaces:**
- Incoming: IF-CM-EXT-IN-001
- Outgoing: IF-CM-EXT-OUT-001, IF-CM-EXT-OUT-003

**Traceability:** REQ-L1-037
**Rationale:** Kommentar-Threads ermöglichen kontextgebundene Kommunikation am Artefakt.

---

### REQ-L2-CM-002: @Mention-Auflösung

Der CommentService SHALL @Mention-Syntax in Kommentar-Texten auflösen. Ein @Mention eines registrierten Nutzers SHALL validiert und als Notification-Trigger gespeichert werden. Ein @Mention eines nicht registrierten Namens SHALL einen Validierungshinweis erzeugen, aber den Kommentar trotzdem speichern.

**Domain:** software
**Priority:** optional
**arch_impact:** false
**Acceptance Criteria:**
- [ ] @Mention eines registrierten Nutzers → Mention-Eintrag mit user_id gespeichert
- [ ] @Mention eines nicht registrierten Namens → Validierungshinweis, Kommentar trotzdem gespeichert
- [ ] Mention-Auflösung erfolgt asynchron nach Kommentar-Speicherung
- [ ] Mention-Liste ist via REST-API abrufbar (GET /comments/{id}/mentions)
- [ ] Doppelte @Mentions desselben Nutzers werden dedupliziert

**Interfaces:**
- Incoming: IF-CM-EXT-IN-001
- Outgoing: IF-CM-EXT-OUT-002, IF-CM-EXT-OUT-003

**Traceability:** REQ-L1-037
**Rationale:** @Mentions ermöglichen gezielte Benachrichtigungen ohne externe Tools.

---

### REQ-L2-CM-003: In-App-Notification-Dispatch

Der CommentService SHALL bei jedem @Mention eines registrierten Nutzers eine In-App-Benachrichtigung erzeugen. Die Benachrichtigung enthält Kommentar-ID, Artefakt-Referenz und Mention-Autor. Benachrichtigungen sind via REST-API abrufbar (GET /notifications) und als gelesen markierbar.

**Domain:** software
**Priority:** optional
**arch_impact:** false
**Acceptance Criteria:**
- [ ] @Mention → In-App-Benachrichtigung für genannten Nutzer erzeugt
- [ ] Benachrichtigung enthält Kommentar-ID, Artefakt-Referenz, Mention-Autor
- [ ] Benachrichtigung ist via REST-API abrufbar (GET /notifications)
- [ ] Benachrichtigung kann als gelesen markiert werden (PUT /notifications/{id}/read)
- [ ] Benachrichtigung wird im Audit-Log erfasst

**Interfaces:**
- Incoming: IF-CM-EXT-IN-001 (Mention-Event von COMP-CM-002)
- Outgoing: IF-CM-EXT-OUT-001, IF-CM-EXT-OUT-003

**Traceability:** REQ-L1-037
**Rationale:** In-App-Notifications schließen den Kommunikationskreis ohne externe Tools.

---

## Traceability-Matrix: REQ-L2-CM → REQ-L1

| REQ-L2-CM | Titel | REQ-L1 | Priorität |
|-----------|-------|--------|-----------|
| REQ-L2-CM-001 | Kommentar-CRUD mit Thread | REQ-L1-037 | optional |
| REQ-L2-CM-002 | @Mention-Auflösung | REQ-L1-037 | optional |
| REQ-L2-CM-003 | In-App-Notification | REQ-L1-037 | optional |

---

*Erstellt durch se-architect-Agent | ReqFlow SE-Kaskade Phase 3 | 2026-06-27*
*Designation: system — decomposition_status: L3-Zerlegung erforderlich*
