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

**Implementation State:** Not Implemented
**Review Findings:** Keine Implementierung oder Tests im Code gefunden.
**Test Status:** Missing
**Remarks:** Sollte implementiert werden.

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

**Implementation State:** Not Implemented
**Review Findings:** Keine Implementierung oder Tests im Code gefunden.
**Test Status:** Missing
**Remarks:** Sollte implementiert werden.

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

**Implementation State:** Not Implemented
**Review Findings:** Keine Implementierung oder Tests im Code gefunden.
**Test Status:** Missing
**Remarks:** Sollte implementiert werden.

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

---

## Erweiterung v2 — Vollständige Requirement-Beschreibungen (REQ-L2-CM-001..003)

> **Datum:** 2026-06-28 | **Quelle:** REQ-L0-025 → REQ-L1-037

---

### REQ-L2-CM-001: Kommentar-CRUD mit Thread-Struktur

**Implementation State:** Not Implemented
**Review Findings:** Kein Code-Äquivalent. CommentService nicht implementiert.
**Test Status:** Missing
**Remarks:** Abgeleitet von REQ-L1-037 (← REQ-L0-025, SN-25). Priority: optional (v1 Post-Launch).

Der CommentService MUSS Kommentare direkt an einzelnen Artefakten (Requirements,
Architecture Elements, TestCases) als kontextbezogene Threads speichern.
Jeder Kommentar enthält: Autor, Inhalt (Markdown), Zeitstempel, Artefakt-Referenz,
optionale parent_comment_id (für Antworten im Thread).
Kommentare MÜSSEN editierbar (nur durch Autor) und löschbar (Autor oder Admin) sein.
Die Versionshistorie eines Artefakts SOLL Kommentar-Aktivität nicht beeinflussen.

**Schnittstellen:**
- `POST /requirements/{id}/comments` → Comment erstellen
- `GET /requirements/{id}/comments` → Thread-Liste (hierarchisch)
- `PATCH /comments/{id}` → Editieren (nur Autor)
- `DELETE /comments/{id}` → Löschen (Autor oder Admin)
- Body: `{ "content": "...", "parent_comment_id": null }`

**Akzeptanzkriterien:**
- AC1: Kommentar an Requirement erstellen → persistiert mit Autor + Zeitstempel
- AC2: Antwort auf Kommentar (parent_comment_id) → Thread-Hierarchie korrekt
- AC3: Edit durch fremden Nutzer → HTTP 403
- AC4: Kommentar-Liste sortiert nach created_at ASC (älteste zuerst)
- AC5: Gelöschter Kommentar zeigt Platzhalter `[deleted]` (kein Hard-Delete im Thread)

**Verifikationsmethode:** Integrationstest — Thread erstellen, Antworten, Berechtigungen prüfen
**Verifikiert durch:** L2-CM-Test-001
**Abgeleitet von:** REQ-L1-037
**Übergeordnete REQ-L0:** REQ-L0-025

---

### REQ-L2-CM-002: @Mention-Auflösung (Nutzer-Erwähnungen in Kommentaren)

**Implementation State:** Not Implemented
**Review Findings:** Kein Code-Äquivalent.
**Test Status:** Missing
**Remarks:** Abgeleitet von REQ-L1-037 (← REQ-L0-025, SN-25).

Der CommentService MUSS @Mentions (Format: `@username`) in Kommentar-Inhalten
parsen und die erwähnten Nutzer identifizieren. Die Auflösung erfolgt beim Speichern
des Kommentars. Für jeden aufgelösten @Mention MUSS ein Notification-Event
(REQ-L2-CM-003) ausgelöst werden. Nicht auflösbare Mentions SOLLEN als reiner Text
behandelt werden (kein Fehler).

**Schnittstellen:**
- Intern: `MentionParser.extract_mentions(content) → List[username]`
- Event: `mention.created { comment_id, mentioned_user_id, artefact_ref }`
- `GET /workspaces/{id}/users?q=prefix` → Autocomplete für @Mentions (UI-Support)

**Akzeptanzkriterien:**
- AC1: `@alice` in Kommentar → Alice wird als Mention aufgelöst → Notification-Event
- AC2: `@unknown_user` → kein Fehler, wird als Text gespeichert
- AC3: Autocomplete-Endpunkt liefert Nutzer des Workspaces gefiltert nach Prefix

**Verifikationsmethode:** Unit-Test (Parser) + Integrationstest (Event-Auslösung)
**Verifikiert durch:** L2-CM-Test-002
**Abgeleitet von:** REQ-L1-037
**Übergeordnete REQ-L0:** REQ-L0-025

---

### REQ-L2-CM-003: In-App-Notification (Benachrichtigung bei Mentions und Antworten)

**Implementation State:** Not Implemented
**Review Findings:** Kein Code-Äquivalent.
**Test Status:** Missing
**Remarks:** Abgeleitet von REQ-L1-037 (← REQ-L0-025, SN-25).

Wenn ein Nutzer per @Mention (REQ-L2-CM-002) erwähnt wird oder auf seinen Kommentar
geantwortet wird, MUSS eine Notification erstellt werden. Notifications MÜSSEN über
die API abrufbar sein (Inbox-Konzept) und als `read`/`unread` markierbar sein.
Push-Notifications (WebSocket/SSE) SOLLTEN implementiert werden, sind aber nicht Pflicht für v1.

**Schnittstellen:**
- `GET /notifications?user_id=me` → Inbox-Liste (unread zuerst)
- `PATCH /notifications/{id}` → `{ "read": true }`
- Intern: Notification-Service konsumiert `mention.created`- und `comment.replied`-Events

**Akzeptanzkriterien:**
- AC1: @Mention → Notification in Inbox des erwähnten Nutzers
- AC2: Antwort auf Kommentar → Notification beim Ursprungsautor
- AC3: Notifications als `read` markierbar
- AC4: Unread-Count über API abrufbar

**Verifikationsmethode:** Integrationstest — Mention erstellen, Notification prüfen
**Verifikiert durch:** L2-CM-Test-003
**Abgeleitet von:** REQ-L1-037
**Übergeordnete REQ-L0:** REQ-L0-025

---

*Erweiterung durch se-requirements-Agent | 2026-06-28 (REQ-L2-CM-001..003 vollständig ausgearbeitet)*


## Master Traceability Matrix

| REQ-L2 | Abgeleitet von REQ-L1 |
|---------|----------------------|
| REQ-L2-CM-001 | REQ-L1-037 |
| REQ-L2-CM-002 | REQ-L1-037 |
| REQ-L2-CM-003 | REQ-L1-037 |

