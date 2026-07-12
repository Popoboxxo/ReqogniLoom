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
| REQ-L2-BL-012 | Baseline Delta-Storage Index mit JSON-Snapshots |

## Interne Schnittstellen

| IF-ID | Richtung | Gegenstelle | Vertrag |
|-------|----------|-------------|---------|
| IF-BL-INT-004 | ausgehend | COMP-BL-003 (BaselineStore) | `lookup_item_snapshot(baseline_id, item_id) -> snapshot_json` |

## Externe Schnittstellen (Systemgrenze)

| IF-ID | Richtung | Gegenstelle | Vertrag |
|-------|----------|-------------|---------|
| IF-BL-EXT-IN-001 | eingehend | ApplicationService | `get_item_at_baseline(baseline_id, item_id)` |

## L3 Komponenten-Anforderungen

### REQ-L3-BL004-001: Historische Item-Payload-Rekonstruktion


**Implementation State:** Implemented
**Review Findings:** Implementierung gefunden, aber keine Tests.
**Test Status:** Missing
**Remarks:** Testabdeckung fehlt.


Der VersionReconstructor SHALL fuer einen gegebenen `(baseline_id, item_id)`-Schluessel den vollstaendigen historischen Item-Payload zum in der Baseline gespeicherten Zeitpunkt zurueckliefern. Dazu SHALL er den Snapshot (JSONField) direkt ueber den BaselineStore (aus dem BaselineDeltaIndexEntry) abfragen und de-serialisieren. Ein Abruf aus dem AuditLog ist explizit untersagt (gemäß REQ-L2-BL-012).

**Priority:** mandatory
**Acceptance Criteria:**
- [ ] `get_item_at_baseline(bl_id, item_id)` → returns ItemPayload populated from JSON snapshot
- [ ] No queries are made to AuditLog or VersionHistory tables.
- [ ] Function throws an error if no JSON snapshot is available in the DeltaIndex.

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
- [ ] snapshot cannot be deserialized or is missing → raises error `"Valid JSON Snapshot not found in baseline index"`

---

### REQ-L3-BL004-003: Payload-Caching fuer wiederholte Rekonstruktionen


**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.


Der VersionReconstructor SOLLTE haeufig abgerufene JSON-Snapshots (deserialisierte Objekte) im Arbeitsspeicher zwischenspeichern (LRU-Cache), um wiederholte JSON-Deserialisierung für dasselbe `(baseline_id, item_id)` Paar zu vermeiden.

**Priority:** optional
**Acceptance Criteria:**
- [ ] Repeated `get_item_at_baseline` calls for the same baseline/item_id → second call served from cache

- [ ] Cache is bounded (LRU eviction) to prevent unbounded memory growth
- [ ] Cache invalidation is not required (payloads are immutable once versioned)

---

*Erstellt durch se-requirements-Agent (L3-Component) | ReqFlow SE-Kaskade | 2026-06-21*
