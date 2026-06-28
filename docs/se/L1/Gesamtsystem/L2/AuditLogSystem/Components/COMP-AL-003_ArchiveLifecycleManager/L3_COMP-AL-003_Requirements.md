# L3 ArchiveLifecycleManager Requirements

> **Level:** L3 (Komponenten-Anforderungen)
> **Komponente:** COMP-AL-003 — ArchiveLifecycleManager
> **Parent-System:** AuditLogSystem (L2)
> **Status:** Entwurf

---

## Verantwortlichkeit

Periodischer Celery-Beat-Job; exportiert Eintraege aelter als 2 Jahre als komprimierte JSON-Archive nach Cold Storage (konfigurierbar); loescht exportierte Partition nach erfolgreichem Export aus Primaer-DB; Fail-Safe: kein Loeschen ohne bestaedigten Export.

## Zugeordnete L2-Anforderungen

| REQ-L2 | Anforderungstext (Kurzform) |
|--------|-----------------------------|
| REQ-L2-AL-009 | Cold-Storage-Archivierung: Export aelterer als 2 Jahre, gzip-komprimiert, fail-safe Loeschung |

## Interne Schnittstellen

| IF-ID | Richtung | Gegenstelle | Vertrag |
|-------|----------|-------------|---------|
| IF-AL-INT-002 | ausgehend | COMP-AL-002 (AuditLogQuery) | Lesezugriff auf AuditLogEntry-Eintraege gefiltert nach `timestamp < (now - 2 Jahre)`, paginiert fuer speichereffizienten Export |

## Externe Schnittstellen (Komponente an Systemgrenze)

| IF-ID | Richtung | Gegenstelle | Vertrag |
|-------|----------|-------------|---------|
| IF-AL-EXT-OUT-001 | ausgehend | PersistenceLayer (Django ORM) | Partition-Drop nach bestaetigtem Export |
| IF-AL-EXT-OUT-002 | ausgehend | Cold Storage (S3 oder konfigurierbar) | Komprimierte JSON-Archive (`audit_YYYY_MM.json.gz`); Schreib-Bestaetigung erforderlich vor Loeschung |

---

## L3 Komponenten-Anforderungen

### REQ-L3-AL003-001: Periodische Ausfuehrung via Celery-Beat


**Implementation State:** Implemented
**Review Findings:** Implementierung gefunden, aber keine Tests.
**Test Status:** Missing
**Remarks:** Testabdeckung fehlt.


Der ArchiveLifecycleManager SHALL als Celery-Beat-Task konfiguriert sein und monatlich (am 1. eines jeden Monats) automatisch ausgefuehrt werden. Das Cold-Storage-Ziel und der Archivierungs-Cutoff (Standard: 2 Jahre) MUSSEN per Environment-Variable oder Django-Setting konfigurierbar sein.

**Priority:** desired

**Acceptance Criteria:**
- [ ] Celery Beat schedule shows task with monthly cron trigger (`0 0 1 * *` or equivalent)
- [ ] Task executes without manual trigger on scheduled date
- [ ] `AUDIT_COLD_STORAGE_BACKEND`, `AUDIT_RETENTION_YEARS` are read from environment/settings
- [ ] Default retention period is 2 years when not configured

---

### REQ-L3-AL003-002: Fail-Safe Export-vor-Loeschung-Protokoll


**Implementation State:** Implemented
**Review Findings:** Implementierung gefunden, aber keine Tests.
**Test Status:** Missing
**Remarks:** Testabdeckung fehlt.


Der ArchiveLifecycleManager SHALL Audit-Eintraege erst nach bestaedigtem, erfolgreichem Export in den Cold Storage loeschen. Schlaegt der Export fehl (z.B. Cold Storage nicht erreichbar, HTTP-Fehler, Schreib-Timeout), MUSS der Job ohne Loeschung abbrechen und den Fehler protokollieren. Partial-Export (nur Teil der Eintraege exportiert) gilt als Fehler.

**Priority:** desired

**Acceptance Criteria:**
- [ ] Successful export to Cold Storage → confirmation received → partition drop executed
- [ ] Cold Storage unreachable (simulated network error) → no partition drop, error logged
- [ ] Partial upload (connection interrupted mid-transfer) → no partition drop, error logged
- [ ] Log entry for every export attempt contains: timestamp, partition identifier, outcome (success/failure), error details if any

---

### REQ-L3-AL003-003: Archiv-Format und Datei-Konvention


**Implementation State:** Implemented
**Review Findings:** Implementierung gefunden, aber keine Tests.
**Test Status:** Missing
**Remarks:** Testabdeckung fehlt.


Der ArchiveLifecycleManager SHALL exportierte Audit-Eintraege im JSON-Format, gzip-komprimiert, mit der Dateinamens-Konvention `audit_YYYY_MM.json.gz` in den Cold Storage schreiben. Jeder Eintrag in der JSON-Datei MUSS alle Pflichtfelder enthalten: `actor`, `actor_type`, `operation`, `entity_type`, `entity_id`, `timestamp`, `version`, `tenant_id`, `source`.

**Priority:** desired

**Acceptance Criteria:**
- [ ] Exported file name matches `audit_YYYY_MM.json.gz` for the archived month
- [ ] File is valid gzip-compressed JSON (parseable after decompression)
- [ ] Every JSON object in the file contains all 9 mandatory fields
- [ ] No raw API keys or secrets present in any exported JSON object
- [ ] Archive for month 2024-01 contains only entries with `timestamp` in January 2024

---

*Erstellt durch se-requirements-Agent (L3-Component) | ReqFlow SE-Kaskade | 2026-06-21*
