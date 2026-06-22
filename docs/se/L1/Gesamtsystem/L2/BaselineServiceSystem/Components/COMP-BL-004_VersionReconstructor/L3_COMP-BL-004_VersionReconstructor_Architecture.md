---
step: architecture
agent: se-architect
iteration: 1
status: done
timestamp: "2026-06-22T12:00:00Z"
schema_version: "1.0.0"
---
# L3 VersionReconstructor Architecture

> **Level:** L3 (Component white-box / Terminal)
> **Component:** COMP-BL-004_VersionReconstructor
> **Parent:** L2_BaselineServiceSystem_Architecture.md
> **Datum:** 2026-06-22
> **Status:** entworfen
> **Designation:** component (terminal)
> **decomposition_status:** terminal — component-level leaf, no further SE decomposition

---

## 1. Verantwortlichkeit

Der VersionReconstructor rekonstruiert den historischen Payload (title, description, content) eines Items auf den Versionszustand, der in einer Baseline gespeichert wurde. Er fungiert als Brücke zwischen dem BaselineStore (der nur `(item_id, version)`-Tupel speichert) und dem AuditLog / der RequirementVersion-Tabelle (der die tatsächlichen Payloads enthält). Er implementiert optionales Payload-Caching via LRU, um wiederholte Abrufe zu optimieren.

---

## 2. White-Box Design (Interne Struktur)

### 2.1 Klassen und Module

- **`VersionReconstructor` (Klasse):** Orchestriert Versions-Lookup und Payload-Rekonstruktion.
- **`LruPayloadCache` (Helfer-Klasse):** LRU-Cache für `(item_id, version)` → ItemPayload.
- **`ItemPayload` (Datenklasse):** Reprä­sentiert rekonstruierten Item-Payload mit title, description, content.
- **`CacheEntry` (Datenklasse):** Speichert Item-ID, Version, Payload, Access-Zeit.

### 2.2 Datenstrukturen

- **LRU-Cache (In-Memory):**
  - Max Size: konfigurierbar (default 1000 Einträge)
  - Key: `(item_id, version)` → Tuple
  - Value: ItemPayload (title, description, content)
  - Eviction: bei Überschreitung von max_size, älteste Access-Zeit entfernen

- **ItemPayload:**
  - `item_id`: str
  - `version`: int
  - `title`: str
  - `description`: str | None
  - `content`: str | None
  - `reconstructed_at`: datetime (Zeitstempel der Rekonstruktion)

---

## 3. Erfüllung der Anforderungen

| REQ-L3 | Implementierungs-Ansatz |
|--------|-------------------------|
| REQ-L3-BL004-001 (Historische Rekonstruktion) | Methode `get_item_at_baseline(baseline_id, item_id)`: (1) Ruft BaselineStore auf: `lookup_item_version(baseline_id, item_id) -> version`. (2) Cache-Check: Ist `(item_id, version)` im LRU? Wenn ja, ItemPayload zurückgeben. (3) Wenn nein: Query AuditLog/RequirementVersion nach item_id + version. (4) ItemPayload in Cache einfügen. (5) Zurückgeben. |
| REQ-L3-BL004-002 (Fehlerbehandlung) | BaselineStore-Fehler (Item nicht in Baseline) wird weitergeleitet. AuditLog-Fehler (Version nicht in History) wird mit klarer Nachricht geworfen. |
| REQ-L3-BL004-003 (LRU-Caching) | Cache-Hit: Payload-Rückgabe ohne DB-Query. Cache-Miss: DB-Query, dann Cache einfügen. Eviction: bei max_size Überschreitung, älteste Access-Zeit entfernen. |

---

## 4. Schnittstellen-Implementierung

- **Eingänge (Inbound):**
  - **IF-BL-EXT-IN-001:** Aufruf vom ApplicationService: `get_item_at_baseline(baseline_id, item_id)`.

- **Ausgänge (Outbound):**
  - **IF-BL-INT-004:** Aufruf an BaselineStore: `lookup_item_version(baseline_id, item_id) -> version`.
  - **IF-BL-EXT-IN-004:** Django ORM-Query auf RequirementVersion / AuditLog (SELECT item_id, version, title, description, content WHERE item_id=? AND version=?).

---

## 5. Architectural Rationale

**ADR-L3-BL004-01 — LRU-Payload-Caching**
*Entscheidung:* Rekonstruierte Payloads werden in einem LRU-Cache (max 1000 Einträge) gepuffert.
*Rationale:* Wiederholte Abrufe desselben `(item_id, version)`-Paars sparen DB-Queries. Payloads sind immutable (once versioned), Cache-Invalidierung nicht erforderlich. REQ-L3-BL004-003 (optional) wird vollständig erfüllt. LRU-Begrenzung verhindert unbegrenztes Speicherwachstum.
*Alternative abgelehnt:* Kein Caching — würde bei häufigen Abrufen zu redundanten DB-Queries führen.

**ADR-L3-BL004-02 — Fehler-Delegation vs. Fehler-Wrapping**
*Entscheidung:* BaselineStore-Fehler (Item nicht in Baseline) werden direkt weitergeleitet. AuditLog-Fehler (Version nicht in History) werden mit zusätzlichem Kontext geworfen.
*Rationale:* Klare Fehlerunterscheidung für Caller. REQ-L3-BL004-002 erfordert explizite Fehlerunterscheidung.
*Alternative abgelehnt:* Alle Fehler als generischer "Reconstruction failed" — würde Debugging erschweren.

---

*Erstellt durch se-architect-Agent | ReqFlow SE-Kaskade L2→L3 | 2026-06-22*
*Designation: component (terminal) — decomposition_status: terminal*
