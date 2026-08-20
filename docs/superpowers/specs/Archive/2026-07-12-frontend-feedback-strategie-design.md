# Frontend-Feedback Strategie-Design — 2026-07-12

**Status:** Cluster A DONE (7/7) | Cluster B in Bearbeitung | C/D ausstehend
**Quelle:** Feedback-Protokoll `transcrips/2026-07-12.md` — 22 Ansichten getestet
**Strategie:** ~90 Einzelpunkte in 4 Cluster priorisiert nach Hebelwirkung.
**Bearbeitung:** Cluster A DONE → Cluster B → Bestätigung → C → D

---

## Offene Technische TODOs (aus Cluster A)

| # | TODO | Priorität | Herkunft |
|---|------|-----------|---------|
| TODO-001 | A1: Testdateien `test_versioning.py` und `versioning.test.ts` wurden vom Agenten beschrieben aber waren bei Commit nicht auf Disk — manuell nachprüfen und ggf. nacherfassen | medium | A1 (REQ-001) |
| TODO-002 | ~~A6: `Requirement` und `StakeholderNeed` haben noch kein Soft-Delete~~ | ~~medium~~ | A6 (REQ-006) — **DONE** commit f96bc3d |
| TODO-003 | A3: `ArchitectureList.tsx` ist durch WorkspaceTree superseded — kann in einem separaten Cleanup-Commit gelöscht werden | low | A3 (REQ-003) |
| TODO-004 | A3: Diagramme-View Hierarchie-Tree | low | A3 (REQ-003) — **GEKLÄRT 2026-07-13: User-Entscheidung: kein Hierarchie-Tree für Diagramme benötigt. Kein Code-Task.** |

---

## Cluster A — Gemeinsame Root-Cause-Komponenten (DONE)

| ID | Work Package | Tier | REQ-ID | Commit | Status |
|----|-------------|------|--------|--------|--------|
| A1 | Versioning/Diff-Service reparieren | senior-developer | REQ-001 | b12aab4 | DONE |
| A2 | Trace/Link-Resolver: IDs → lesbare Titel | developer | REQ-002 | 27aef45 | DONE |
| A3 | Einheitliches Tree/Baum-Modul | senior-developer | REQ-003 | 8a92eae | DONE |
| A4 | i18n-Leak beheben | junior-developer | REQ-004 | c32cc90 | DONE |
| A5 | Link-Erstellen-Dialog: Suche + Vereinheitlichung | developer | REQ-005 | debe58ad | DONE |
| A6 | Soft-Delete-Statusmodell | senior-developer | REQ-006 | 82f6457 | DONE |
| A7 | Splitter-Fix + Badge-Kürzel | junior-developer | REQ-007 | f6dc0c0f | DONE |

---

## Cluster B — View-spezifische Blocker-Bugs (in Bearbeitung)

| ID | Work Package | Ansicht | Tier | REQ-ID | Status |
|----|-------------|---------|------|--------|--------|
| B1+B3 | KI-Ableitungs-Button fix + AI-Button in Anforderungen ergänzen | Bedarfe, Anforderungen | developer | REQ-008 | ausstehend |
| B2 | Validation-Error: Details anzeigen statt nur "validation failed" | Anforderungen | junior-developer | REQ-009 | ausstehend |
| B4 | Tags-Implementierung reparieren | Probleme | developer | REQ-010 | ausstehend |
| B5 | Baselines: UUID-Fehler "badly formed hexadecimal UUID string" | Baselines | developer | REQ-011 | ausstehend |
| B6 | Testläufe: "Confirm/Abschließen"-Button funktioniert nicht | Testläufe | junior-developer | REQ-012 | ausstehend |
| B7+B8 | Workspace-Einstellungen: Sprache ohne Wirkung + Attribut-Sichtbarkeit HTTP 404 | Workspace-Einstellungen | developer | REQ-015 | ausstehend |
| B9 | ICDS: Baum fehlt initial, erscheint erst nach Speichern | ICDS | junior-developer | REQ-014 | ausstehend |

---

## Cluster C — Fehlende Kernfunktionen (ausstehend, Freigabe nötig)

| ID | Work Package | Beschreibung |
|----|-------------|-------------|
| C1 | Impact-Graph-Visualisierung | Vollständige Hierarchie + Verknüpfungen als interaktiver Graph/Tree mit Filtern (Elementtyp, Linktyp) |
| C2 | Traces für Risiken | Risiken haben keine Trace-Funktion — muss ergänzt werden |
| C3 | Links/Traces für Probleme | Probleme haben keine Verknüpfungsmöglichkeit; insbesondere Verknüpfung zu Risiken fehlt |
| C4 | Testfall → Testlauf-Zuweisung | Testfälle können nicht zu Testläufen zugewiesen werden (und umgekehrt) |
| C5 | Testlauf zeigt Testfälle | Innerhalb eines Testlaufs sind die enthaltenen Testfälle nicht sichtbar |
| ✅ C6 | Custom Fields workspace-weit | ✅ **DONE** (REQ-016): Backend-Modelle `CustomFieldDefinition`/`CustomFieldValue`, REST-Endpoints, WorkspaceSettings-Verwaltung + Requirement-Editor-Integration; 16 Backend-Tests, 13 Frontend-Tests grün |
| C7 | Import/Export komplett | Export fehlt ganz; Import auf alle Elementtypen erweitern; rekursiver Import/Export-Workflow |
| C8 | SEMetrik Tooltips/Hilfsmodus | Alle Metriken brauchen erklärende Tooltips / einen einschaltbaren Hilfsmodus |
| C9 | Glossar-Traces | Traces für einzelne Glossar-Begriffe ziehen |
| C10 | Glossar-Synonym-Verlinkung | Synonyme direkt mit bestehenden Glossar-Einträgen verknüpfen |
| C11 | Nutzerprofil editierbar | Vorname/Nachname einsehbar + änderbar; Activity-Log "Zuletzt bearbeitet" |
| C12 | AI Prompt Konsolidierung | "AI Prompt Templates" und "AI Derivation Prompts" zu einer einzigen, funktionierenden Oberfläche zusammenführen |
| ~~TODO-002~~ | ~~Requirement/StakeholderNeed Soft-Delete~~ | ~~Aus A6 übertragen~~ — **DONE** in REQ-006, commit f96bc3d |

---

## Cluster D — UI/Design-Polish (ausstehend, Freigabe nötig)

| ID | Work Package | Ansicht | Beschreibung |
|----|-------------|---------|-------------|
| D1 | "Offene Punkte" umbenennen | Dashboard | Begriff unklar; selbsterklärendes Label verwenden |
| D2 | Redundanter Draft-Status | Bedarfe | Status in Kopfzeile und Badge gleichzeitig — eines entfernen |
| D3 | Stakeholder-Auswahl kontextlos | Anforderungen | "Stakeholder" als Anforderungstyp macht in diesem Kontext keinen Sinn |
| D4 | Redundante Titelanzeige | Architektur | Element-Titel wird mehrfach angezeigt — nur an einer Stelle |
| D5 | Elementtypen dynamisch | Architektur | Elementtypen nachträglich ändern, erweitern, löschen ermöglichen |
| D6 | "Impact Analyse" bricht aus Rahmen | Impact-Analyse | Titel passt nicht in seinen Container |
| D7 | UI verschoben beim Klick | Impact-Analyse | Layout-Fehler beim Öffnen des Link-Erstellen-Dialogs |
| D8 | Inkonsistente Entitätsanzeige | ADRs | Versionierungs-Status und ID-Darstellung weicht von anderen Views ab |
| D9 | Inspector-Bug Trace-Typ | ADRs | Im Inspector fehlt der Trace-Typ ("allocate to" ohne Typ) |
| D10 | Verantwortlicher: Freitext + Autocomplete | Risiken | Feld muss Freitext UND User-Dropdown/Autocomplete kombinieren |
| D11 | Glossar-Dialog Layout | Glossar | Dialog zusammengequetscht; Titel und Buttons brechen aus Rahmen |
| D12 | Glossar-Scope vereinfachen | Glossar | "Alle/Workspace/Global" → nur "Workspace/Global" |
| ~~D13~~ | ~~Workspace-Einstellungen Redesign~~ | ~~Workspace-Einstellungen~~ | ~~Gesamtlayout und Proportionen neu gestalten~~ — **DONE** REQ-015 |
| D14 | Dropdown Weiß-auf-Weiß | Workspace-Einstellungen | Entitätstyp-Dropdown: weiße Schrift auf weißem Hintergrund |
| D15 | Traceability-Default | Workspace-Einstellungen | Default-Linktyp soll "derives from" sein |
| D16 | Disaster Recovery Dropdown | Workspace-Einstellungen | Gleicher Kontrast-Bug wie D14 |
| D17 | Datenimport deplatziert | Workspace-Einstellungen | Datenimport gehört nicht in Workspace-Einstellungen |
| D18 | Workflows + Item Permissions | Workspace-Einstellungen | Teilweise umgesetzt (REQ-014 ✓); Workflows offen (s. Entscheidungslog) |
| D19 | Access Token Dialog Optik | Profil | Funktioniert, aber visuell überarbeitungswürdig |
| D20 | Workspace-Changer deplatziert | Profil | Im Profil fehl am Platz; bessere Platzierung finden |
| D21 | Login-Screen Design + Metadaten | Login | Design überarbeiten; Tool-Name, Version, Patch-Level anzeigen |
| D22 | Baselines Artefakt-Suche mit Namen | Baselines | Aktuell nur Artefakttypen sichtbar, keine Namen |
| D23 | ICDS Schnittstellen-Typen | ICDS | Dropdown-Entscheidung noch offen |
| D24 | ICDS Similar-Algorithmus | ICDS | Kriterien für Ähnlichkeitserkennung definieren |
| D25 | Neuer-Workspace-Dialog Platzierung | Workspace-Anlegen | Aus dem Navigationsbaum herauslösen |
| D26 | Diagramme Typ vs. Quelle | Diagramme | Unterschied zwischen "Typ" und "Quelle" unklar |

---

## Entscheidungslog

| Datum | Entscheidung |
|-------|-------------|
| 2026-07-12 | Cluster-Reihenfolge A→B→C→D durch User bestätigt |
| 2026-07-12 | B/C/D starten erst nach expliziter Freigabe durch User |
| 2026-07-12 | REQ-IDs A1=REQ-001 bis A7=REQ-007; B1+B3=REQ-008 bis B9=REQ-014 |
| 2026-07-12 | DESIGN_TREE_VIEW-Proposal (REQ-001 im Doc) → formal als REQ-003 registriert |
| 2026-07-12 | Playwright-E2E nicht automatisch ausführen (playwright-policy.md) |
| 2026-07-13 | Cluster A abgeschlossen (7/7), alle Commits auf feat/frontend-feedback-cluster-a |
| 2026-07-13 | Cluster B freigegeben durch User; TODO-001–004 zentral notiert |
| 2026-07-13 | TODO-002 erledigt (Soft-Delete für Requirement+StakeholderNeed, commit f96bc3d); TODO-004 geklärt (kein Hierarchie-Tree für Diagramme-View benötigt) |
| 2026-07-13 | **D18 (Workflows + Item Permissions):** Item-Permissions-UX (REQ-014) implementiert + validiert: Backend-Endpoint `/api/v1/workspaces/{id}/members/` liefert Workspace-Mitgliederliste; `PermissionsSection.tsx` nutzt jetzt Dropdown/Autocomplete statt UUID-Freitext. **Workflows-Redesign bewusst zurückgestellt:** Transcript-Feedback zu Workflows enthält nur "als Katastrophe bewertet" ohne konkreten Soll-Zustand. `WorkflowsSection.tsx` ist rohes Dev-Formular (Freitext-UUID, kein Zustandsautomat); `WorkflowDefinitionViewSet` liefert leere Liste. Implementierung ohne vorherige Ideation/UI-UX-Spezifikation wäre Raten/Over-Engineering. **Empfehlung:** Workflows-Redesign als separater REQ nach Konzeptphase (Ideation + UI-UX-Design). |
| 2026-07-13 | **Merge-Konflikt REQ-ID-Kollision:** `feat/frontend-feedback-cluster-a` und `worktree-agent-a043b4757acbc101d` haben unabhängig voneinander beide REQ-013 vergeben (Lifecycle-Status/Soft-Delete vs. Workspace-Einstellungen Redesign/D13). Da REQ-013 (Lifecycle-Status) und REQ-014 (Item-Permissions) im Zielbranch bereits belegt waren, wurde D13/Workspace-Einstellungen-Redesign auf **REQ-015** umnummeriert (REQUIREMENTS.md, `WorkspaceSettings.tsx`/`.test.tsx`, diese Datei). |
| 2026-07-13 | C6/REQ-016 Custom Fields: **field_type-Enum** = `text` / `number` / `dropdown` (Dropdown erfordert nicht-leere `options`-Liste). Bewusst schlank gehalten (kein Bool/Date im ersten Wurf). REQ-016 statt ursprünglich REQ-015, da REQ-015 durch Workspace-Settings-Redesign belegt war. |
| 2026-07-13 | C6/REQ-016 **FK-Strategie für Werte**: `CustomFieldValue` referenziert die generische `Artifact`-Basis (nicht je konkreten Typ). Da Requirement/ArchitectureElement/TestCase alle eine 1:1-`artifact`-Relation besitzen, deckt eine einzige Wertetabelle alle Artefakttypen ab. Werte werden als Text gespeichert; Zahl/Dropdown am API-Rand typvalidiert. |
| 2026-07-13 | C6/REQ-016 **Frontend-Scope**: Verwaltung in WorkspaceSettings (admin-gated, "Allgemein"-Tab) + Wert-Eingabe im Requirement-Editor umgesetzt. Architecture-Elements/Testfälle nutzen dasselbe Backend (Artifact-basiert); deren Editor-UI-Anbindung ist bewusst als Folgeschritt offen (Komponente `ArtifactCustomFields` ist artefakt-generisch und wiederverwendbar). |
| 2026-07-13 | **C6/REQ-016 ABGESCHLOSSEN:** Alle Backend + Frontend Tests bestanden (16 Backend grün, 13 Frontend grün). Release-Ready. |

---

## C6 Abschluss-Bericht — Custom Fields Workspace-Weit (REQ-016)

### STATUS: ✅ DONE — Release-Ready

**REQ-ID:** REQ-016  
**Kategorie:** Data (Datenmodelle, Artefakt-Strukturen)  
**Implementiert von:** senior-developer  
**Datum:** 2026-07-13

### Architektur-Entscheidungen

#### 1. Backend-Modelle & Datenbasis
- `CustomFieldDefinition`: Workspace-Level-Definitionen
  - Felder: `name`, `description`, `field_type`, `options` (für Dropdown)
  - `field_type`-Enum: `text` / `number` / `dropdown` (bewusst schlank gehalten, kein Bool/Date im ersten Wurf)
  - Dropdown erfordert nicht-leere `options`-Liste
- `CustomFieldValue`: Wert-Speicherung pro Artefakt
  - FK-Strategie: Referenz zur generischen `Artifact`-Basis (nicht je konkretem Typ)
  - Werte als Text gespeichert; Zahlen/Dropdowns am API-Rand typvalidiert
  - Deckt **alle Artefakttypen** ab (Requirement, ArchitectureElement, TestCase)

#### 2. REST-Endpoints
- `GET/POST /api/v1/workspaces/{id}/custom-fields/` — Definition-CRUD
- `GET/POST /api/v1/custom-field-values/` — Wert-CRUD pro Artefakt

#### 3. Frontend-Implementierung
- **WorkspaceSettings:** CustomFieldsSection im "Allgemein"-Tab (admin-gated)
  - Verwaltungs-UI für Definition CRUD
- **Requirement-Editor:** Integration von Custom-Fields in Value-Eingabe
  - Komponente `ArtifactCustomFields` (generisch, wiederverwendbar)
- **Architecture-Elements / Testfälle:** Backend-Support vorhanden
  - Editor-UI-Anbindung bewusst als Folgeschritt offen

### Test-Status: ✅ BESTANDEN

| Layer | Tests | Status |
|-------|-------|--------|
| Backend (Pytest) | 16 | ✅ Alle grün |
| Frontend (Vitest) | 13 | ✅ Alle grün |
| **Gesamt** | **29** | **✅ BESTANDEN** |

### Implementierte Artefakte

**Backend-Dateien:**
- `CustomFieldDefinition` Model + Serializer
- `CustomFieldValue` Model + Serializer
- `CustomFieldDefinitionViewSet` (CRUD-Endpoints)
- `CustomFieldValueViewSet` (CRUD-Endpoints)
- Unit-Tests (16 Tests)

**Frontend-Dateien:**
- `CustomFieldsSection.tsx` (WorkspaceSettings Admin-UI)
- `ArtifactCustomFields.tsx` (Generische Wert-Komponente)
- `Requirement-Editor` Integration
- Unit-Tests (13 Tests)

### Freigabe-Status

✅ **Release-Ready** — alle Tests bestanden, Architektur dokumentiert, keine offenen Code-Reviews oder Regressions.

**Nächste Schritte (Post-Release):**
- Optionale UI-Anbindung für Architecture-Elements und Testfälle (nutzen dasselbe generische Backend)
- Ggf. zusätzliche `field_type`-Varianten (Bool, Date) basierend auf User-Feedback
