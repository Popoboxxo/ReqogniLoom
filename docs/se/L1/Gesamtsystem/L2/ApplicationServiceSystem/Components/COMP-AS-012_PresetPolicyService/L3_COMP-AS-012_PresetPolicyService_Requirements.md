---
step: requirements
agent: se-requirements
iteration: 1
status: done
timestamp: "2026-06-22T14:30:00Z"
schema_version: "1.0.0"
---
# L3 PresetPolicyService Requirements

> **Level:** L3 (Component-Anforderungen)
> **Component:** COMP-AS-012_PresetPolicyService
> **Parent:** L2_ApplicationServiceSystem_Requirements.json
> **Datum:** 2026-06-22
> **Status:** formalisiert
> **Designation:** component (terminal)
> **decomposition_status:** terminal

---

## Traceability

- Abgeleitet von: REQ-L2-AppSvc-020 (primär)
- Ziel: terminal (implementierungsbereit)

---

## Systemzweck

Der PresetPolicyService ist die zentrale Querschnitts-Komponente für Configurable-Rigor-Enforcement. Er validiert Preset-Regeln (Scope-Erlaubnis, change_reason-Pflicht, Downgrade-Inkompatibilität) und wird von BaselineFacade, WorkflowFacade und allen schreibenden Domain-Services konsultiert. Single Source of Truth für Preset-Policy-Entscheidungen.

---

## Externe Schnittstellen (Komponentengrenze)

| ID | Richtung | Typ | Beschreibung |
|----|----------|-----|--------------|
| IF-AS-INT-006 | input | control | Scope-Erlaubnis-Anfrage von COMP-AS-006 (BaselineFacade) |
| IF-AS-INT-007 | input | control | Transition-Role-Validierungsanfrage von COMP-AS-007 (WorkflowFacade) |
| IF-AS-INT-008 | input | control | change_reason-Anforderungsabfrage von COMP-AS-002, 013, 014, 015 |
| IF-AS-EXT-OUT-004 | output | data | Preset-Config abrufen von PresetConfigEngine (ARCH-L1-008) |
| IF-AS-EXT-OUT-007 | output | data | Workspace-Zustand abfragen (Artefakt-Count, etc.) vom PersistenceLayer |

---

## L3 Component-Anforderungen

### REQ-L3-PPL-001: Scope-Validierung für Baseline-Erstellung

Der PresetPolicyService SHALL vor Baseline-Erstellung verifizieren, ob der angeforderte Scope (document, project, global) im aktiven Preset erlaubt ist:
- `is_scope_allowed(workspace_id, scope) -> boolean`

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Preset-Definition wird von PresetConfigEngine abgerufen
- [ ] Erlaubte Scopes werden gegen Anfrage validiert
- [ ] `true` wenn Scope erlaubt, `false` wenn blockiert
- [ ] Error-Nachricht erklärt Blockierungsgrund

**Interfaces:** IF-AS-INT-006, IF-AS-EXT-OUT-004
**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

**Traceability:** REQ-L2-AppSvc-020
**Rationale:** Preset-Scopes begrenzen Baseline-Erstellung auf konzeptuell erlaubte Ebenen.

---

### REQ-L3-PPL-002: Change-Reason-Requirement-Prüfung

Der PresetPolicyService SHALL abfragen, ob change_reason für Requirement-Updates im aktiven Preset erforderlich ist:
- `is_change_reason_required(workspace_id) -> boolean`

Returns `true` wenn Preset Enhanced oder Extended ist und change_reason Pflichtfeld verlangt.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Preset wird von PresetConfigEngine abgerufen
- [ ] `true` für Enhanced/Extended Presets
- [ ] `false` für Basic/Standard Presets
- [ ] Workspace-spezifisches Preset wird konsultiert (nicht Global)

**Interfaces:** IF-AS-INT-008, IF-AS-EXT-OUT-004
**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

**Traceability:** REQ-L2-AppSvc-020
**Rationale:** Configurable Rigor auf Requirement-Mutation-Ebene.

---

### REQ-L3-PPL-003: Transition-Role-Validierung

Der PresetPolicyService SHALL verifizieren, dass der aktuelle Nutzer die erforderlichen Rollen für eine Workflow-Transition besitzt:
- `validate_transition_roles(auth_context, item_id, target_state) -> boolean`

Basierend auf dem WorkflowDefinition des Items und den Rollen im auth_context.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] WorkflowDefinition wird konsultiert (via TraceabilityEngine oder Cache)
- [ ] Target-State wird überprüft auf erforderliche Rollen
- [ ] User-Rollen aus auth_context werden abgeglichen
- [ ] `true` wenn User alle erforderlichen Rollen hat
- [ ] `false` + Error-Nachricht wenn Rollen fehlen

**Interfaces:** IF-AS-INT-007, IF-AS-EXT-OUT-004
**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

**Traceability:** REQ-L2-AppSvc-020
**Rationale:** Zugriffskontrolle auf Workflow-State-Transitions.

---

### REQ-L3-PPL-004: Downgrade-Inkompatibilität-Check

Der PresetPolicyService SHALL vor Preset-Downgrade (z.B. von Extended zu Basic) prüfen, ob existierende Artefakte mit dem neuen Preset kompatibel sind:
- `check_downgrade_compatibility(workspace_id, target_preset) -> (compatible: boolean, incompatible_items: [...])`

Beispiel: Extended-Preset erlaubt Enumerationen, Basic nicht → Downgrade blockiert, wenn Enumerationen existieren.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Alle Artefakte der Workspace werden gegen Target-Preset überprüft
- [ ] Inkompatible Items werden in Result-Array aufgelistet
- [ ] Downgrade blockiert wenn Inkompatibilitäten gefunden
- [ ] Item-ID und Inkompatibilitäts-Grund werden gemeldet

**Interfaces:** IF-AS-INT-008, IF-AS-EXT-OUT-004, IF-AS-EXT-OUT-007
**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

**Traceability:** REQ-L2-AppSvc-020
**Rationale:** Datenintegrität bei Preset-Änderungen (OP-02 Handling).

---

### REQ-L3-PPL-005: Preset-Cache mit TTL

Der PresetPolicyService SHALL Preset-Definitionen für bis zu 5 Minuten im In-Memory-Cache halten, um Mehrfach-Konsultationen der PresetConfigEngine zu reduzieren.

**Domain:** software
**Priority:** desired
**Acceptance Criteria:**
- [ ] Cache-TTL ist 5 Minuten (konfigurierbar)
- [ ] Cache wird bei Preset-Update invalidiert (Event-Listener)
- [ ] Cache-Hit reduziert PresetConfigEngine-Aufrufe um ≥70%
- [ ] Cache-Fehler triggert Fallback zu Live-Query

**Interfaces:** IF-AS-EXT-OUT-004
**Implementation State:** Not Implemented
**Review Findings:** Keine Implementierung oder Tests im Code gefunden.
**Test Status:** Missing
**Remarks:** Sollte implementiert werden.

**Traceability:** REQ-L2-AppSvc-023
**Rationale:** Performance-Optimierung für häufige Policy-Abfragen.

---

### REQ-L3-PPL-006: Workspace-spezifisches Preset

Der PresetPolicyService SHALL immer das Preset der angeforderten Workspace konsultieren (nicht Global-Default), sofern Workspace-spezifisches Preset existiert.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Workspace-Preset wird gelesen (falls konfiguriert)
- [ ] Bei fehlender Workspace-Config: Fallback zu Tenant-Default
- [ ] workspace_id ist eingangsseitig vorhanden
- [ ] Keine Cross-Workspace-Policy-Anwendung

**Interfaces:** IF-AS-INT-006, IF-AS-INT-007, IF-AS-INT-008
**Implementation State:** Not Implemented
**Review Findings:** Keine Implementierung oder Tests im Code gefunden.
**Test Status:** Missing
**Remarks:** Sollte implementiert werden.

**Traceability:** REQ-L2-AppSvc-020
**Rationale:** Granulare Konfigurierbarkeit auf Workspace-Ebene.

---

### REQ-L3-PPL-007: Zentrale Policy-Query-Schnittstelle

Der PresetPolicyService SHALL eine einzige generische Schnittstelle anbieten, die beliebige Preset-Policy-Abfragen ermöglicht:
- `get_policy(workspace_id, policy_key) -> policy_value`

Dies ermöglicht zukünftige Policy-Erweiterungen ohne Schnittstellen-Änderungen.

**Domain:** software
**Priority:** desired
**Acceptance Criteria:**
- [ ] Policy-Keys sind dokumentiert (scope_allowed, change_reason_required, etc.)
- [ ] Unbekannte Policy-Keys werfen Error
- [ ] Preset wird konsultiert für Key-Abfrage
- [ ] Default-Wert wird zurückgegeben wenn Key nicht im Preset definiert

**Interfaces:** IF-AS-EXT-OUT-004
**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

**Traceability:** REQ-L2-AppSvc-020
**Rationale:** Extensibilität für zukünftige Policy-Typen.

---

### REQ-L3-PPL-008: Fehlerbehandlung und Audit-Logging

Der PresetPolicyService SHALL bei Policy-Violations Fehler mit strukturierter Nachricht zurückgeben und optional AuditLog-Einträge schreiben (für Downgrade-Versuche).

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Error-Nachrichten sind aussagekräftig (z.B. "Scope 'document' not allowed in Extended preset")
- [ ] Fehlgeschlagene Transitions oder Downgrades werden geloggt
- [ ] Keine sensitiven Daten in Error-Messages
- [ ] AuditLog optional per config aktivierbar

**Interfaces:** IF-AS-INT-006, IF-AS-INT-007, IF-AS-INT-008
**Implementation State:** Not Implemented
**Review Findings:** Keine Implementierung oder Tests im Code gefunden.
**Test Status:** Missing
**Remarks:** Sollte implementiert werden.

**Traceability:** REQ-L2-AppSvc-020
**Rationale:** Transparenz und Debugging.

---

## Traceability-Matrix: REQ-L3-PPL → REQ-L2

| REQ-L3 | Primäre REQ-L2 |
|--------|----------------|
| REQ-L3-PPL-001 | REQ-L2-AppSvc-020 |
| REQ-L3-PPL-002 | REQ-L2-AppSvc-020 |
| REQ-L3-PPL-003 | REQ-L2-AppSvc-020 |
| REQ-L3-PPL-004 | REQ-L2-AppSvc-020 |
| REQ-L3-PPL-005 | REQ-L2-AppSvc-023 |
| REQ-L3-PPL-006 | REQ-L2-AppSvc-020 |
| REQ-L3-PPL-007 | REQ-L2-AppSvc-020 |
| REQ-L3-PPL-008 | REQ-L2-AppSvc-020 |

---

*Erstellt durch se-requirements-Agent | ReqFlow SE-Kaskade L2→L3 | 2026-06-22*
*Designation: component (terminal) — decomposition_status: terminal*


## Master Traceability Matrix

| REQ-L3 | Abgeleitet von REQ-L2 |
|---------|----------------------|
| REQ-L3-PPL-001 | REQ-L2-AppSvc-020 |
| REQ-L3-PPL-002 | REQ-L2-AppSvc-020 |
| REQ-L3-PPL-003 | REQ-L2-AppSvc-020 |
| REQ-L3-PPL-004 | REQ-L2-AppSvc-020 |
| REQ-L3-PPL-005 | REQ-L2-AppSvc-023 |
| REQ-L3-PPL-006 | REQ-L2-AppSvc-020 |
| REQ-L3-PPL-007 | REQ-L2-AppSvc-020 |
| REQ-L3-PPL-008 | REQ-L2-AppSvc-020 |

