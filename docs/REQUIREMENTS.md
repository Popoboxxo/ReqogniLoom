# ReqFlow — Anforderungsregister

> **Quelle:** Abgeleitet aus L1-Gesamtsystem-Anforderungen, SE-Kaskade L1→L2.
> **ID-Präfix:** `REQ-L2-RF-xxx` (ReactFrontendSystem, COMP-RF-001..006)
> **Letzte Aktualisierung:** 2026-06-30

---

## Erweiterung v3 — REQ-L2-RF-018..023 (Frontend-Features und Refactorings)

> **Datum:** 2026-06-30 | **Quelle:** wk-bug-fixes branch

---

### REQ-L2-RF-018: TestCasesView — CRUD für Test Cases

**Implementation State:** Not Implemented
**Test Status:** Missing
**Domain:** software
**Priority:** mandatory

Das Frontend MUSS eine TestCasesView-Komponente bereitstellen, die CRUD-Operationen für TestCases unterstützt. Die Komponente MUSS über die Sidebar unter „Test Cases" erreichbar sein und folgende Ansichten bereithalten:

1. **Listenansicht:** Alle TestCases des aktiven Workspaces in einer Liste mit Status-Badge (draft/active/deprecated), Klick öffnet Detailansicht.
2. **Erstellungsformular:** Titel, Description, Status, Priority sowie Multi-Select für verknüpfte Requirements. Nach dem Anlegen MÜSSEN verifies-TraceLinks zu den ausgewählten Requirements automatisch erstellt werden.
3. **Detailansicht:** Inline-Editing von Titel, Description, Status; Anzeige der verknüpften Requirements. Speichern über PATCH-Endpunkt.

**Acceptance Criteria:**
- [ ] AC1: Sidebar-Link „Test Cases" navigiert zur Listenansicht
- [ ] AC2: Liste zeigt alle TestCases des aktiven Workspaces mit Status-Badge
- [ ] AC3: Erstellungsformular mit Titel, Description, Status, Priority, Linked-Requirements-Auswahl
- [ ] AC4: Nach Create werden verifies-TraceLinks automatisch angelegt
- [ ] AC5: Detailansicht mit Inline-Editing und Speicher-Button
- [ ] AC6: Detailansicht zeigt verknüpfte Requirements als Liste

**Verifikationsmethode:** UI-E2E-Test — Liste render, Create, Detail Edit, TraceLink-Prüfung
**Verifikiert durch:** L2-RF-Test-018
**Abgeleitet von:** REQ-L2-RA-001, REQ-L1-035

---

### REQ-L2-RF-019: RiskList refaktorieren (COMP-RF-003)

**Implementation State:** Not Implemented
**Test Status:** Missing
**Domain:** software
**Priority:** should

Das Frontend MUSS die RiskList-Komponente refaktorieren. Die aktuelle Implementierung enthält duplizierte Inline-Styles und Formular-Logik, die in wiederverwendbare Utilities extrahiert werden MÜSSEN. Folgende Verbesserungen sind erforderlich:

1. **Shared-Style-Extraktion:** Inline-Style-Blöcke (`inputStyle`, `labelStyle`, `primaryButtonStyle`) in CSS-Module oder Theme-Constants auslagern.
2. **Detailansicht:** Klick auf ein Risiko öffnet eine Detailansicht mit Editierfunktion für Titel, Description, Severity, Probability, Impact, Status.
3. **Filter/Sort:** Liste MUSS filterbar nach Severity und sortierbar nach Titel/Datum sein.
4. **Status-Badge:** Einheitlicher Status-Badge wie in TestCasesView.

**Acceptance Criteria:**
- [ ] AC1: Shared-Styles sind extrahiert, keine duplizierten `inputStyle`-Blöcke mehr
- [ ] AC2: Detailansicht mit Inline-Editing aller Risiko-Felder
- [ ] AC3: Filter nach Severity (low/medium/high)
- [ ] AC4: Einheitlicher Status-Badge (Identified/Monitored/Mitigated/Accepted/Closed)
- [ ] AC5: Leeres State-Rendering vorhanden

**Verifikationsmethode:** Unit-Test + UI-E2E-Test
**Verifikiert durch:** L2-RF-Test-019
**Abgeleitet von:** REQ-L1-029

---

### REQ-L2-RF-020: AdrList refaktorieren (COMP-RF-003)

**Implementation State:** Not Implemented
**Test Status:** Missing
**Domain:** software
**Priority:** should

Das Frontend MUSS die AdrList-Komponente refaktorieren. Analog zu REQ-L2-RF-019 sind duplizierte Inline-Styles zu extrahieren und die Komponente um eine Detailansicht sowie Filter-Funktionen zu erweitern:

1. **Shared-Style-Extraktion:** Identisch zu REQ-L2-RF-019.
2. **Detailansicht:** Klick auf einen ADR-Eintrag öffnet Detailansicht mit Editierfunktion für Titel, Context, Decision, Status.
3. **Status-Badge:** Einheitlicher Status-Badge (Draft/In Review/Approved/Rejected/Superseded).

**Acceptance Criteria:**
- [ ] AC1: Shared-Styles sind extrahiert
- [ ] AC2: Detailansicht mit Inline-Editing (Titel, Context, Decision, Status)
- [ ] AC3: Status-Badge konsistent mit RiskList/TestCasesView
- [ ] AC4: Leeres State-Rendering vorhanden

**Verifikationsmethode:** Unit-Test + UI-E2E-Test
**Verifikiert durch:** L2-RF-Test-020
**Abgeleitet von:** REQ-L1-029

---

### REQ-L2-RF-021: IssueList refaktorieren (COMP-RF-003)

**Implementation State:** Not Implemented
**Test Status:** Missing
**Domain:** software
**Priority:** should

Das Frontend MUSS die IssueList-Komponente refaktorieren. Analog zu REQ-L2-RF-019/020 sind duplizierte Styles zu extrahieren und die Komponente um Detailansicht sowie Filter-Funktionen zu erweitern:

1. **Shared-Style-Extraktion:** Identisch zu REQ-L2-RF-019/020.
2. **Detailansicht:** Klick auf einen Issue-Eintrag öffnet Detailansicht mit Editierfunktion für Titel, Description, Severity, Status.
3. **Filter/Sort:** Filter nach Severity (low/medium/high/critical) und Status (Open/In Progress/Resolved/Closed/Wontfix).

**Acceptance Criteria:**
- [ ] AC1: Shared-Styles sind extrahiert
- [ ] AC2: Detailansicht mit Inline-Editing (Titel, Description, Severity, Status)
- [ ] AC3: Filter nach Severity und Status
- [ ] AC4: Status-Badge konsistent
- [ ] AC5: Leeres State-Rendering vorhanden

**Verifikationsmethode:** Unit-Test + UI-E2E-Test
**Verifikiert durch:** L2-RF-Test-021
**Abgeleitet von:** REQ-L1-029

---

### REQ-L2-RF-022: TestRuns refaktorieren (COMP-RF-003)

**Implementation State:** Not Implemented
**Test Status:** Missing
**Domain:** software
**Priority:** should

Das Frontend MUSS die TestRuns-Komponente refaktorieren. Die aktuelle Implementierung enthält duplizierte Inline-Styles und verwendet keine konsistente Status-Badge-Logik. Folgende Verbesserungen sind erforderlich:

1. **Shared-Style-Extraktion:** Inline-Styles in CSS-Module auslagern, konsistent mit REQ-L2-RF-019..021.
2. **Status-Badge:** Wiederverwendung der StatusBadge-Komponente aus TestCasesView.
3. **Detailansicht:** Verbesserte Detailansicht mit Result-Summary-Grid, CI-Job-ID-Anzeige und Ablaufsteuerung (Close-Button für in_progress-Runs).
4. **Erstellungsformular:** Extraktion der Formular-Logik in eigenen Hook/Component.

**Acceptance Criteria:**
- [ ] AC1: Shared-Styles sind extrahiert, konsistent mit anderen List-Komponenten
- [ ] AC2: StatusBadge wird wiederverwendet (kein eigener Badge-Code)
- [ ] AC3: Detailansicht zeigt Result-Summary (Total/Passed/Failed/Not Run)
- [ ] AC4: Close-Button nur sichtbar bei in_progress-Status
- [ ] AC5: Erstellungsformular als eigenständige Komponente

**Verifikationsmethode:** Unit-Test + UI-E2E-Test
**Verifikiert durch:** L2-RF-Test-022
**Abgeleitet von:** REQ-L2-AS-030

---

### REQ-L2-RF-023: Shared-Types-Erweiterung (types/index.ts)

**Implementation State:** Not Implemented
**Test Status:** Missing
**Domain:** software
**Priority:** mandatory

Das Frontend MUSS die zentralen Shared-Types in `frontend/src/types/index.ts` um folgende Typdefinitionen erweitern, die die korrespondierenden Backend-Serializer aus ARCH-L1-002 exakt abbilden:

1. **TestCase-Typen:** `TestCaseStatus` (draft/active/deprecated), `TestCasePriority` (low/med/high), `TestCase`-Interface mit allen Serializer-Feldern.
2. **Risk-Erweiterung:** Vervollständigung des Risk-Interfaces um `category` (technical/operational/organizational/business), `owner`, `mitigation_strategy`, `risk_score`.
3. **Issue-Erweiterung:** Vervollständigung des Issue-Interfaces um `category` (defect/improvement/documentation/question) und `tags`.
4. **ADR-Erweiterung:** Vervollständigung des Adr-Interfaces um `consequences`.
5. **TestRun-Typen:** `TestRunResult`, `TestRunResultSummary`, `TestRun`-Interface.

**Acceptance Criteria:**
- [ ] AC1: TestCase-Typen existieren und sind von der TestCasesView importierbar
- [ ] AC2: Risk-Interface enthält alle Serializer-Felder (category, owner, mitigation_strategy, risk_score)
- [ ] AC3: Issue-Interface enthält category und tags
- [ ] AC4: Adr-Interface enthält consequences
- [ ] AC5: TestRun-Typen (TestRun, TestRunResult, TestRunResultSummary) sind definiert
- [ ] AC6: Alle Typen sind mit JSDoc-Kommentaren dokumentiert

**Verifikationsmethode:** TypeScript-Compile-Prüfung, Unit-Test
**Verifikiert durch:** L2-RF-Test-023
**Abgeleitet von:** REQ-L2-RF-001..012 (Shared-Types-Erweiterung)

---

*Erweiterung durch requirements-Agent | 2026-06-30 (REQ-L2-RF-018..023 aus wk-bug-fixes)*
