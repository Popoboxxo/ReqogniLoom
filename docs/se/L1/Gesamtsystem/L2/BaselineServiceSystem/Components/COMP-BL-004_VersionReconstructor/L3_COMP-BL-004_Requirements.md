# L3 VersionReconstructor Requirements

> **Level:** L3 (Komponenten-Anforderungen)
> **Komponente:** COMP-BL-004 — VersionReconstructor
> **Parent-System:** BaselineServiceSystem (L2)
> **Status:** Entwurf

---

## Verantwortlichkeit

Laedt fuer ein `(item_id, version)`-Paar den historischen Payload aus AuditLog / RequirementVersion-Tabelle; implementiert `get_item_at_baseline(baseline_id, item_id) -> ItemPayload`.

## Zugeordnete L2-Anforderungen

| REQ-L2 | Anforderungstext (Kurzform) |
|--------|-----------------------------|
| REQ-L2-BL-009 | Baseline-Rekonstruktion aus Versionshistorie |

## Interne Schnittstellen

| IF-ID | Richtung | Gegenstelle | Vertrag |
|-------|----------|-------------|---------|
| IF-BL-INT-004 | ausgehend | COMP-BL-003 (BaselineStore) | `lookup_item_version(baseline_id, item_id) -> version` |

## Externe Schnittstellen (Systemgrenze)

| IF-ID | Richtung | Gegenstelle | Vertrag |
|-------|----------|-------------|---------|
| IF-BL-EXT-IN-001 | eingehend | ApplicationService | `get_item_at_baseline(baseline_id, item_id)` |
| IF-BL-EXT-IN-004 | eingehend | AuditLog / VersionHistory (Django ORM) | `get_version(item_id, version) -> ItemPayload` |

## L3 Komponenten-Anforderungen

### REQ-L3-BL004-001: Historische Item-Payload-Rekonstruktion


**Implementation State:** Implemented
**Review Findings:** Implementierung gefunden, aber keine Tests.
**Test Status:** Missing
**Remarks:** Testabdeckung fehlt.


Der VersionReconstructor SHALL fuer einen gegebenen `(baseline_id, item_id)`-Schluessel den vollstaendigen historischen Item-Payload (title, description, content) zum in der Baseline gespeicherten Versionszeitpunkt zurueckliefern. Dazu SHALL er zunaechst die Versions-Nummer ueber den BaselineStore ermitteln und anschliessend den Payload aus dem AuditLog bzw. der `RequirementVersion`-Tabelle laden.

**Priority:** mandatory
**Acceptance Criteria:**
- [ ] `get_item_at_baseline(bl_id, item_id)` → returns ItemPayload with title, description, content of the stored version
- [ ] Item modified after baseline creation → function returns the old state at baseline time, not the current state
- [ ] Payload retrieval uses the version number from BaselineStore, not the current item version

---

### REQ-L3-BL004-002: Fehlerbehandlung fuer fehlende Eintraege


**Implementation State:** Implemented
**Review Findings:** Implementierung gefunden, aber keine Tests.
**Test Status:** Missing
**Remarks:** Testabdeckung fehlt.


Der VersionReconstructor SHALL fuer Fehlerszenarien klar definierte Fehler ausloesen: wenn das Item nicht in der Baseline enthalten ist oder wenn die gespeicherte Version nicht in der Versionshistorie vorhanden ist.

**Priority:** mandatory
**Acceptance Criteria:**
- [ ] item_id not in baseline → raises error `"Item not part of this baseline"` (delegated from BaselineStore)
- [ ] version not found in AuditLog/RequirementVersion → raises error `"Version not found in history"`
- [ ] Error message clearly distinguishes between the two failure cases

---

### REQ-L3-BL004-003: Payload-Caching fuer wiederholte Rekonstruktionen


**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.


Der VersionReconstructor SOLLTE haeufig abgerufene `(item_id, version)`-Paare im Arbeitsspeicher zwischenspeichern (LRU-Cache), um wiederholte AuditLog-Abfragen fuer identische Versionen zu vermeiden.

**Priority:** optional
**Acceptance Criteria:**
- [ ] Repeated `get_item_at_baseline` calls for the same (item_id, version) pair → second call served from cache without DB query
- [ ] Cache is bounded (LRU eviction) to prevent unbounded memory growth
- [ ] Cache invalidation is not required (payloads are immutable once versioned)

---

*Erstellt durch se-requirements-Agent (L3-Component) | ReqFlow SE-Kaskade | 2026-06-21*
