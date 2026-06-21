# L3 TerminologyProfileService Requirements

> **Level:** L3 (Komponenten-Anforderungen)
> **Komponente:** COMP-PC-002 — TerminologyProfileService
> **Parent-System:** PresetConfigEngineSystem (L2)
> **Status:** Entwurf

---

## Verantwortlichkeit

Verwaltung von Terminologie-Profilen (Dev-Modus / SE-Modus). Liefert vollständige Mappings von generischen Entity-Namen zu domänenspezifischen Labels. REST API und MCP nutzen immer generische Namen — Terminologie-Transformation erfolgt ausschließlich an der Präsentationsschicht.

## Zugeordnete L2-Anforderungen

| REQ-L2 | Anforderungstext (Kurzform) |
|--------|-----------------------------|
| REQ-L2-PC-009 | Terminologie-Profil-Verwaltung: Dev-Modus / SE-Modus mit vollständigem Label-Mapping |
| REQ-L2-PC-010 | Terminologie-Profil-Wechsel ohne Datenmigration, < 1 Sekunde |

## Interne Schnittstellen

| IF-ID | Richtung | Gegenstelle | Vertrag |
|-------|----------|-------------|---------|
| IF-PC-INT-002 | ausgehend | COMP-PC-003 (FeatureGateService) | `get_terminology_profile(workspace_id) -> TerminologyMapping` |

## Externe Schnittstellen (falls Komponente an Systemgrenze)

| ID | Richtung | Gegenstelle | Typ | Beschreibung |
|----|----------|-------------|-----|--------------|
| IF-PC-EXT-IN-002 | eingehend | ApplicationService | In-Process Python | `get_terminology_profile(workspace_id)` |
| IF-PC-EXT-IN-003 | eingehend | ApplicationService | In-Process Python | `switch_terminology_profile(workspace_id, target_profile)` |
| IF-PC-EXT-OUT-001 | ausgehend | PersistenceLayer | Django ORM | Lesen/Schreiben von TerminologyProfile-Objekten |

---

## L3 Komponenten-Anforderungen

### REQ-L3-PC002-001: Vollständiges Label-Mapping pro Terminologie-Profil

Der TerminologyProfileService SHALL für jedes registrierte Profil (Dev-Modus, SE-Modus) ein vollständiges Mapping aller generischen Entity-Namen auf domänenspezifische Labels bereitstellen. Ein unvollständiges Mapping ist abzulehnen.

**Priority:** mandatory

**Acceptance Criteria:**
- [ ] `get_terminology_profile("dev_mode")` returns `{artifact_l1: "Epic", artifact_l2: "Story", requirement: "Acceptance Criterion"}`
- [ ] `get_terminology_profile("se_mode")` returns `{artifact_l1: "System Requirement", artifact_l2: "Function", architecture_element: "Subsystem"}`
- [ ] Profile with any missing mandatory key raises `IncompleteProfileError`
- [ ] REST API and MCP response content is identical regardless of active profile

---

### REQ-L3-PC002-002: Profil-Wechsel ohne Datenmigration in unter 1 Sekunde

Der TerminologyProfileService SHALL Profilwechsel (z.B. Dev → SE) ohne DB-Schema-Änderung, Datenmigration oder Änderung der API-Antwortstruktur vollziehen. Der Wechsel muss in unter 1 Sekunde abgeschlossen sein.

**Priority:** mandatory

**Acceptance Criteria:**
- [ ] Switch Dev → SE → API response structure unchanged, only UI labels differ
- [ ] Switch completes within < 1 second wall-clock time
- [ ] No DB migration script is executed after profile switch
- [ ] All requirement data remains unchanged after profile switch

---

### REQ-L3-PC002-003: Profil-Persistenz pro Workspace

Der TerminologyProfileService SHALL das aktive Terminologie-Profil workspace-spezifisch persistieren, sodass ein Neustart des Systems das zuletzt gesetzte Profil wiederherstellt.

**Priority:** mandatory

**Acceptance Criteria:**
- [ ] Set profile "se_mode" for workspace A → system restart → `get_terminology_profile(workspace_A)` still returns "se_mode"
- [ ] Different workspaces can have different active profiles simultaneously
- [ ] Profile setting is stored via IF-PC-EXT-OUT-001 (PersistenceLayer)

---

---
*Erstellt durch se-requirements-Agent (L3-Component) | ReqFlow SE-Kaskade | 2026-06-21*
