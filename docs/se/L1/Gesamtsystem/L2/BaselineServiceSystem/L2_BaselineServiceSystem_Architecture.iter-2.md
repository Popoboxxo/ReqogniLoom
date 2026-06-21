---
step: architecture
agent: se-architect
iteration: 2
status: done
timestamp: "2026-06-21T23:55:00+02:00"
schema_version: "1.0.0"
---

# L2 BaselineService Architecture

> **Level:** L2 (Subsystem white-box)
> **System:** BaselineServiceSystem (ARCH-L1-006)
> **Parent:** L1_Gesamtsystem_Architecture.md
> **Datum:** 2026-06-20
> **Status:** entworfen

---

## 1. Verantwortlichkeit

Erstellung unveraenderlicher, benannter Baselines auf drei Scopes (document, project, global). Ermittelt betroffene Item-IDs und Versionen, persistiert als schlanke Delta-Index-Tabelle (item_id, version) und stellt Diff-Vergleiche sowie historische Zustandsrekonstruktion zwischen Baselines bereit.

---

## 2. Black-Box (Eingebettete Sicht)

### Externe Schnittstellen

| ID | Richtung | Gegenstelle | Typ | Vertrag |
|----|----------|-------------|-----|---------|
| IF-BL-EXT-IN-001 | eingehend | ApplicationService | In-Process Python | `build(scope, workspace_id, name, description, ctx)`, `diff(baseline_a_id, baseline_b_id)`, `get(baseline_id)`, `list(workspace_id, scope?)` |
| IF-BL-EXT-OUT-002 | ausgehend | PresetConfigEngine | In-Process Python | Preset-Regeln (Scope-Verfuegbarkeit) |
| IF-BL-EXT-OUT-003 | ausgehend | TraceabilityEngine | In-Process Python | `collect_trace_graph(workspace_id) -> item_ids, versionen, trace_links` |
| IF-BL-EXT-OUT-004 | ausgehend | AuditLog / VersionHistory | Django ORM | `get_version(item_id, version) -> ItemPayload` |
| IF-BL-EXT-OUT-005 | ausgehend | IcdManagement | In-Process Python | `get_icd_versions(workspace_id, scope) -> icd_ids, versionen` |
| IF-BL-EXT-OUT-006 | ausgehend | IcdManagement | In-Process Python | `get_icd_payload(icd_id, version) -> IcdPayload` |
| IF-BL-EXT-OUT-001 | ausgehend | PersistenceLayer | Django ORM | Baseline-Entitaet (INSERT/SELECT, immutable) |

---

## 3. White-Box (Komponenten-Zerlegung)

### Komponenten

| Komp-ID | Name | Verantwortlichkeit | Domain |
|---------|------|--------------------|--------|
| COMP-BL-001 | DeltaIndexBuilder | Scope-Aufloesung, Item-ID/Version- sowie ICD-Version-Ermittlung, Immutability-Enforcement, Naming/Metadata-Validierung; persistiert ausschliesslich Identifikatoren (`item_id`, `icd_id`) und `version`-Tupel ohne Payload | software |
| COMP-BL-002 | DiffEngine | Vergleich zweier Baselines desselben Scopes (added/removed/changed mit Versions-Delta) auf Basis von Item/ICD-Versions-Paaren, Scope-Kompatibilitaetspruefung | software |
| COMP-BL-003 | BaselineStore | Baseline-Persistenz (INSERT/SELECT), Retrieval und Listing der Delta-Index-Tabelle (fuer Items und ICDs), Tenant-Isolation, atomare Transaktionen | software |
| COMP-BL-004 | VersionReconstructor | Laedt fuer ein Item/ICD den historischen Payload aus AuditLog / VersionHistory-Tabelle; implementiert `get_entity_at_baseline(baseline_id, entity_id) -> Payload` | software |

### Interne Schnittstellen

| ID | Richtung | Quelle -> Ziel | Typ | Vertrag |
|----|----------|----------------|-----|---------|
| IF-BL-INT-001 | intern | COMP-BL-001 -> COMP-BL-003 | In-Process Python | `persist_delta_index(delta_index, metadata) -> baseline_id` |
| IF-BL-INT-002 | intern | COMP-BL-002 -> COMP-BL-003 | In-Process Python | `load_delta_index(baseline_id) -> list[tuple[entity_id, version, type]]` |
| IF-BL-INT-003 | intern | COMP-BL-001 -> COMP-BL-002 | In-Process Python | `get_delta_index(baseline_id) -> list[tuple[entity_id, version, type]]` (optionaler direkter Zugriff) |
| IF-BL-INT-004 | intern | COMP-BL-004 -> COMP-BL-003 | In-Process Python | `lookup_entity_version(baseline_id, entity_id) -> version` |

### Komponentendiagramm (Mermaid)

```mermaid
flowchart TD
    subgraph BaselineServiceSystem
        C001["COMP-BL-001: DeltaIndexBuilder<br/>Scope-Aufloesung + Delta-Index"]
        C002["COMP-BL-002: DiffEngine<br/>Baseline-Vergleich (item_id/version)"]
        C003["COMP-BL-003: BaselineStore<br/>Persistenz + Retrieval"]
        C004["COMP-BL-004: VersionReconstructor<br/>Historischer Payload-Abruf"]
    end

    ext_in1["ApplicationService"] -->|IF-BL-EXT-IN-001| C001
    ext_in1 -->|IF-BL-EXT-IN-001| C002
    ext_in1 -->|IF-BL-EXT-IN-001| C004

    C001 -->|IF-BL-EXT-OUT-002| ext_out2["PresetConfigEngine"]
    C001 -->|IF-BL-EXT-OUT-003| ext_out3["TraceabilityEngine"]
    C004 -->|IF-BL-EXT-OUT-004| ext_out4["AuditLog / VersionHistory"]
    C001 -->|IF-BL-EXT-OUT-005| ext_out5["IcdManagement"]
    C004 -->|IF-BL-EXT-OUT-006| ext_out5

    C001 -->|IF-BL-INT-001| C003
    C002 -->|IF-BL-INT-002| C003
    C001 -.->|IF-BL-INT-003| C002
    C004 -->|IF-BL-INT-004| C003

    C003 -->|IF-BL-EXT-OUT-001| ext_db["PersistenceLayer"]
```

---

## 4. Zugeordnete REQ-L2

| REQ-L2 | Komponente |
|--------|-----------|
| REQ-L2-BL-001 | COMP-BL-001 |
| REQ-L2-BL-002 | COMP-BL-003 |
| REQ-L2-BL-003 | COMP-BL-002 |
| REQ-L2-BL-004 | COMP-BL-001 |
| REQ-L2-BL-005 | COMP-BL-001 |
| REQ-L2-BL-006 | COMP-BL-003 |
| REQ-L2-BL-007 | COMP-BL-003 |
| REQ-L2-BL-008 | COMP-BL-001, COMP-BL-002, COMP-BL-003 |
| REQ-L2-BL-009 | COMP-BL-004 |

---

## 5. ADRs (lokal)

**ADR-BL-01 — Vier Komponenten statt monolithischem BaselineService**
*Entscheidung:* DeltaIndexBuilder, DiffEngine, BaselineStore und VersionReconstructor als eigenstaendige Komponenten.
*Rationale:* Scope-Aufloesung (rekursive CTEs), Diff-Berechnung, Persistenz (ORM/Constraints) und Payload-Rekonstruktion (AuditLog-Zugriff) sind orthogonal genug, um separate Module zu rechtfertigen. Ermoeglicht unabhaengige Testisolation und zukuenftige Optimierungen je Belang.
*Verworfene Alternative:* Monolithischer BaselineService — abgelehnt wegen SRP-Verletzung und schlechter Testisolation.

**ADR-BL-02 — Delta-Storage statt JSON-Snapshot**
*Entscheidung:* Baseline speichert ausschliesslich Identifikatoren und Versionen (z. B. `(entity_id, version, type)`) in einer schlanken Delta-Index-Tabelle. Der vollstaendige Payload (title, description, content) von Items oder ICDs wird nicht persistiert. Zur Rekonstruktion eines historischen Zustands verwendet COMP-BL-004 (VersionReconstructor) das AuditLog bzw. die Versions-Tabellen.
*Rationale:* Ein vollstaendiger JSON-Payload-Snapshot pro Baseline erzeugt bei 10.000 Entitaeten massives DB-Wachstum und ein OOM-Risiko. Delta-Storage reduziert den Speicherbedarf auf wenige Bytes pro Eintrag. Die Payload-Rekonstruktion aus der ohnehin vorhandenen Versionshistorie ist deterministisch und guenstig.
*Verworfene Alternativen:*
- JSON-Snapshot (vollstaendiger Payload in Baseline-Zeile) — abgelehnt wegen Speicher-Overhead und OOM-Risiko bei grossen Projekten.
- Event-Sourcing (Baseline als Marker auf AuditLog-Zeitstrahl) — als Alternativmodell erwaehnt; nicht gewaehlt, da Delta-Storage mit expliziten `(item_id, version)`-Eintraegen einfacher nachvollziehbar und unabhaengig von einer lueckenlosen AuditLog-Kette ist.

**ADR-BL-03 — VersionReconstructor als eigenstaendige Komponente**
*Entscheidung:* Die Rekonstruktion historischer Item-Payloads wird in COMP-BL-004 (VersionReconstructor) isoliert; sie wird nicht in DeltaIndexBuilder oder BaselineStore eingebettet.
*Rationale:* Indexierung (welche Items sind Teil einer Baseline) und Rekonstruktion (wie war der Zustand eines Items zur Baseline-Zeit) sind orthogonale Verantwortlichkeiten. Die Trennung erlaubt unabhaengige Caching-Strategien fuer den VersionReconstructor (z.B. LRU-Cache auf `(item_id, version)`-Ebene) und vereinfacht die Testisolation beider Belange. Die externe Abhaengigkeit zu AuditLog / RequirementVersion ist klar auf eine Komponente begrenzt.
*Verworfene Alternative:* Payload-Rekonstruktion direkt im BaselineStore oder DeltaIndexBuilder — abgelehnt wegen SRP-Verletzung, erschwerter Testbarkeit und unklarer Abhaengigkeitsrichtung zur Versionshistorie.

---

## 6. Resilience (Failure Handling für externe Aufrufe)

Da das BaselineServiceSystem stark von externen Domänen (TraceabilityEngine, IcdManagement, PresetConfigEngine) abhängig ist, gelten folgende Resilience-Regeln:
- **Timeouts:** Alle Aufrufe an In-Process APIs oder den AuditLog erhalten definierte Timeouts.
- **Circuit Breaker / Fallback:** Schlägt der Abruf von historischen Payloads über `VersionReconstructor` fehl, wird ein definierter Fehlerzustand zurückgegeben (keine Endlosschleife, kein vollständiger Systemabsturz).
- **Transaktionsklammern:** Das Erstellen einer Baseline (`COMP-BL-001`) wird atomar durchgeführt. Schlägt ein externer Abruf während der Evaluierung fehl (z.B. Traceability nicht erreichbar), schlägt die gesamte Baseline-Erstellung fehl (Rollback) ohne inkonsistente Zwischenstände zu hinterlassen.

---

*Erstellt durch se-architect-Agent | ReqFlow SE-Kaskade | 2026-06-20*
