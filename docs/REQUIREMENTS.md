# Requirements — ReqFlow

> **INFO:** Das ursprüngliche Backlog wurde aufgelöst (2026-07-04).
> Alle bisherigen Anforderungen wurden in die strukturierte **SE-Kaskade (L0 bis L3)** überführt.
>
> Neue L1/L2-Anforderungen, die noch nicht in die SE-Kaskade integriert sind, werden unten im Abschnitt
> **Neues Feature-Backlog** erfasst und stehen zur Überführung bereit.
>
> Kanonische Quelle der Wahrheit: `docs/se/L0/SN_Stakeholder_Needs.md` (Einstiegspunkt SE-Kaskade)

---

## Neues Feature-Backlog (aufgenommen 2026-07-10)

> Diese Anforderungen sind noch nicht in die SE-Kaskade überführt.
> Status: **Backlog / Not Implemented**

---

### REQ-L2-BL-012: Baseline Full-State-Snapshot in BaselineDeltaIndexEntry

Der BaselineService MUSS das vollständige Entity-Zustandsbild (alle persistierten Felder) zum
Zeitpunkt der Baseline-Erstellung in einem `state`-JSONField innerhalb von
`BaselineDeltaIndexEntry` speichern. Das Feld ist nach dem ersten Schreiben unveränderlich
(Immutability gemäß IcdVersion-Pattern). Der `VersionReconstructor` nutzt dieses Feld
bevorzugt für die Zustandsrekonstruktion; ein History-Lookup ist nur als Fallback erlaubt.

**Implementation State:** Not Implemented
**Review Findings:** BaselineDeltaIndexEntry speichert derzeit nur die Versionsnummer (int) — vollständige Baseline-Rekonstruktion ist ohne separaten History-Lookup nicht möglich.
**Test Status:** Missing
**Remarks:** Neu aufgenommen 2026-07-10. Zur Überführung in L2_BaselineServiceSystem_Requirements.md vorgesehen.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] `BaselineDeltaIndexEntry.state` (JSONField, nullable, default=None) existiert und wird bei der Baseline-Erstellung mit dem vollständigen Entity-Payload befüllt
- [ ] Das `state`-Feld ist nach dem ersten Schreiben unveränderlich (Django-Signal oder Model-Override verhindert Überschreiben)
- [ ] `VersionReconstructor.reconstruct(item_id, baseline_id)` liest bevorzugt aus `state`, fällt bei `state=None` auf History-Tabelle zurück
- [ ] Bestehende Baselines mit `state=None` bleiben gültig (Rückwärtskompatibilität gesichert)
- [ ] Integrationstest: Baseline erstellen → Entity ändern → Rekonstruktion liefert Zustand zum Baseline-Zeitpunkt ohne History-Query

**Traceability:** REQ-L2-BL-001 (Baseline Scope Resolution), REQ-L2-BL-002 (Baseline Immutability), REQ-L2-BL-004 (VersionReconstructor)
**Rationale:** Ohne vollständigen Entity-Zustand im Snapshot ist Baseline-Rekonstruktion auf die History-Tabelle angewiesen. Bei großen Workspaces erzeugt das inakzeptable Latenz und N+1-Query-Probleme.

---

### REQ-L2-TE-019: TraceLink Read-Model mit rekursiven CTE-Abfragen

Die `traceability/models.py`-Schicht MUSS ein Read-Modell für Traceability-Abfragen
bereitstellen. Dieses Read-Modell MUSS drei dedizierte Query-Methoden via rekursiver
PostgreSQL-CTEs implementieren: (a) Impact-Analyse (welche Artefakte sind betroffen, wenn
sich X ändert?), (b) Vorwärts- und Rückwärtspfadsuche über den TraceLink-Graphen,
(c) Zykluserkennung im Trace-Graphen. Alle drei Methoden MÜSSEN über einen REST-Endpunkt
und ein MCP-Tool aufrufbar sein.

**Implementation State:** Not Implemented
**Review Findings:** `traceability/models.py` ist ein leerer Stub ohne Read-Modell. Impact-Analyse, Pfadsuche und Zykluserkennung fehlen vollständig.
**Test Status:** Missing
**Remarks:** Neu aufgenommen 2026-07-10. Zur Überführung in L2_TraceabilityEngineSystem_Requirements.md vorgesehen.

**Domain:** software
**Priority:** must
**Acceptance Criteria:**
- [ ] `TraceabilityReadService.impact(artifact_id, max_depth=5)` gibt alle transitiv betroffenen Artefakte zurück (rekursive CTE, Tiefenlimit konfigurierbar)
- [ ] `TraceabilityReadService.path(source_id, target_id, direction)` gibt den kürzesten Pfad zwischen zwei Artefakten zurück (`direction` ∈ {forward, backward, both})
- [ ] `TraceabilityReadService.detect_cycles(workspace_id)` gibt alle zyklischen TraceLink-Ketten zurück; bei einem zyklusfreien Graphen ist das Ergebnis leer
- [ ] REST-Endpunkt `GET /workspaces/{id}/traceability/impact/{artifact_id}` liefert Impact-Analyse als JSON
- [ ] MCP-Tool `traceability.impact` und `traceability.path` sind registriert und nutzbar
- [ ] Alle drei Methoden sind performant bei bis zu 10.000 TraceLinks (p95 < 500 ms)

**Traceability:** REQ-L2-TE-001 (TraceLinkManager), REQ-L2-TE-002 (QueryEngine), REQ-L2-TE-004 (Upstream/Downstream-Graph-Query)
**Rationale:** Ohne Read-Modell und CTE-basierte Graphabfragen ist Impact-Analyse und Zykluserkennung nur durch ineffiziente ORM-Iterationen möglich, die bei realen Trace-Graphen versagen.

---

### REQ-L2-AS-037: Dynamische Custom-Attribute (JSONB) pro Artefakttyp

Das System MUSS nutzerdefinierte Zusatzfelder (Custom Attributes) pro Artefakttyp
unterstützen. Das `Artifact`-Modell erhält dafür ein `custom_fields`-JSONField (nullable,
default=`{}`). Ein GIN-Index auf diesem Feld gewährleistet Abfrageperformance. Die Werte
werden serverseitig per JSON-Schema-Validierung gegen ein typspezifisches Schema geprüft.
DRF-Serializer exponieren das Feld in der API. Das Frontend stellt einen generischen
Custom-Attribute-Editor bereit.

**Implementation State:** Not Implemented
**Review Findings:** Kein Mechanismus für nutzerdefinierte Felder pro Artefakttyp vorhanden. `AttributeVisibilityConfig` kontrolliert nur die Sichtbarkeit fixer Felder.
**Test Status:** Missing
**Remarks:** Neu aufgenommen 2026-07-10. Zur Überführung in L2_ApplicationServiceSystem_Requirements.md vorgesehen.

**Domain:** software
**Priority:** should
**Acceptance Criteria:**
- [ ] `Artifact.custom_fields` (JSONField, nullable, default=`{}`) ist im Django-Modell vorhanden und per Migration erstellt
- [ ] PostgreSQL-GIN-Index auf `Artifact.custom_fields` ist aktiv
- [ ] Schreiben in `custom_fields` wird gegen ein artefakttypspezifisches JSON-Schema validiert; ungültige Werte werden mit HTTP 400 abgelehnt
- [ ] DRF-Serializer für alle Artefakttypen exponieren `custom_fields` als les- und schreibbares Feld
- [ ] Frontend: Generische Custom-Attribute-Editor-Komponente rendert Felder aus `custom_fields` dynamisch (Typ: string, number, boolean, date)
- [ ] `custom_fields` ist in Baseline-Snapshots enthalten (REQ-L2-BL-012)
- [ ] Integrationstest: Custom Attribute anlegen → per API abfragen → im Baseline-Snapshot vorhanden

**Traceability:** REQ-L2-AS-001 (ArtifactService), REQ-L2-BL-012 (Baseline Full-State-Snapshot), REQ-L2-RF-007 (Preset-basierte UI-Sichtbarkeit)
**Rationale:** Ohne nutzerdefinierte Felder müssen projektspezifische Metadaten in Freitextfeldern oder externen Systemen abgelegt werden — das verhindert maschinenlesbare Auswertung und Traceability.

---

### REQ-L2-VS-004: pgvector-Extension und Embedding-Datenmodell

Das System MUSS die PostgreSQL-Extension `pgvector` aktivieren und ein dediziertes
Embedding-Feld auf dem `Requirement`-Modell bereitstellen. Bei Erstellung und Änderung
einer Anforderung MUSS automatisch (asynchron via Celery) ein Embedding über den
konfigurierten LLM-Adapter generiert und persistiert werden. Ein REST-Endpunkt für
Ähnlichkeitssuche MUSS implementiert werden. Die Suche auf dem Mock-Adapter liefert
einen definierten Fallback.

**Implementation State:** Not Implemented
**Review Findings:** Keine pgvector-Extension, kein Embedding-Feld, keine Ähnlichkeitssuche vorhanden. Nur deutschsprachige Volltextsuche auf Requirements implementiert.
**Test Status:** Missing
**Remarks:** Neu aufgenommen 2026-07-10. Konkretisierung der Implementierungsebene für REQ-L2-VS-001 und REQ-L2-VS-002. Zur Überführung in L2_VectorSearchServiceSystem_Requirements.md vorgesehen.

**Domain:** software
**Priority:** could
**Acceptance Criteria:**
- [ ] `pgvector`-Extension ist in der Django-Migration aktiviert (`CREATE EXTENSION IF NOT EXISTS vector`)
- [ ] `Requirement.embedding` (VectorField, dimension=konfigurierbar, nullable) ist im Django-Modell vorhanden
- [ ] Celery-Task `generate_embedding` wird nach `requirement.created` und `requirement.updated` ausgelöst und speichert das Embedding via LLM-Adapter
- [ ] Mock-Adapter gibt Null-Vektor der korrekten Dimension zurück (kein Absturz ohne echten LLM)
- [ ] REST-Endpunkt `POST /workspaces/{id}/requirements/similar` nimmt `requirement_id` oder `query`-Text und gibt Top-N ähnlichste Anforderungen mit Ähnlichkeits-Score zurück
- [ ] HNSW-Index auf `Requirement.embedding` ist aktiv (Performance: p95 < 200 ms bei 10.000 Anforderungen)
- [ ] Integrationstest: Anforderung erstellen → Embedding generiert → Ähnlichkeitssuche findet semantisch ähnliche Anforderung

**Traceability:** REQ-L2-VS-001 (Semantische Vektorsuche), REQ-L2-VS-002 (Embedding-Pipeline), REQ-L2-PL-005 (PerformanceOptimizationLayer)
**Rationale:** REQ-L2-VS-001 und VS-002 definieren das Systemverhalten; REQ-L2-VS-004 konkretisiert die Datenmodell- und Infrastrukturebene, ohne die höherstufige Spezifikation zu ersetzen.

---

### REQ-L2-AI-001: AI Derivation Service — Draft/Accept-Infrastruktur

Alle KI-gestützten Ableitungsflows MÜSSEN als ApplicationService-Methoden implementiert, über REST und MCP exponiert werden; Ergebnisse sind stets Entwürfe und werden nur nach expliziter User-Bestätigung persistiert — automatische Übernahme ist verboten.

**Implementation State:** Not Implemented
**Domain:** software
**Priority:** must
**Remarks:** Neu aufgenommen 2026-07-11. WP3 Aufgabe 3a — Infrastruktur und Draft/Accept-Pattern.

---

### REQ-L2-AI-002: AI Derivation Flows — Konkrete Ableitungsschritte

Das System MUSS drei nutzerseitig auslösbare KI-Flows bereitstellen: (1) StakeholderNeed → n SystemRequirement-Entwürfe, (2) SystemRequirement → Vorschlag zur ArchitectureElement-Zuordnung, (3) SystemRequirement (mit Architektur) → Dekomposition auf Level n+1, wobei Ergebnisse mehrere ArchitectureElements umspannen können.

**Implementation State:** Not Implemented
**Domain:** software
**Priority:** must
**Remarks:** Neu aufgenommen 2026-07-11. WP3 Aufgabe 3a — spezifische Flow-Implementierungen; setzt REQ-L2-AI-001 voraus.

---

### REQ-L2-TE-020: ADR ↔ ArchitectureElement TraceLink

Das System MUSS einen TraceLink-Typ zwischen ADR und ArchitectureElement unterstützen (Erweiterung der bestehenden 8 Typen oder neuer Typ); UI-Integration in AdrEditor und ArchitectureEditor; REST und MCP exponiert.

**Implementation State:** Not Implemented
**Domain:** software
**Priority:** should
**Remarks:** Neu aufgenommen 2026-07-11. WP3 Aufgabe 3b.

---

### REQ-L2-LLM-001: LlmSettings — Mandanten-konfigurierbarer LLM-Provider

Das System MUSS ein Singleton-Modell `LlmSettings` pro Mandant bereitstellen (Felder: provider, base_url, api_key verschlüsselt/write-only, model als Freitext) mit Fallback auf Umgebungsvariablen; REST-Zugriff nur für Admin-Rolle; api_key niemals in GET-Antworten; Admin-UI im Settings-Bereich.

**Implementation State:** Not Implemented
**Domain:** software
**Priority:** must
**Remarks:** Neu aufgenommen 2026-07-11. WP3 Aufgabe 3c.

---

### REQ-L2-PT-001: PromptTemplate — Admin-editierbare Prompt-Slots

Das System MUSS ein Modell `PromptTemplate` mit den Slots `need_to_sysreq`, `sysreq_to_arch_assign` und `sysreq_decompose_next_level` bereitstellen; jeder Slot hat einen unveränderlichen Default-Prompt (Seed-Migration), kann vom Admin überschrieben und auf Default zurückgesetzt werden; Derivation-Flows (REQ-L2-AI-002) verwenden diese Slots; REST und MCP exponiert; Admin-UI im Settings-Bereich.

**Implementation State:** Not Implemented
**Domain:** software
**Priority:** must
**Remarks:** Neu aufgenommen 2026-07-11. WP3 Aufgabe 3d.
