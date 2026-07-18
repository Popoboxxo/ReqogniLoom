# ReqFlow SysEng 2.0 — Detaillierter technischer Implementierungsplan

> **Datum:** 2026-07-18 | **Status:** User Review Required
> **Scope:** Ontologie-Refactoring, zweisprachiges Link-Naming, Traceability-Auditor, AI-Erweiterungen & **Perfekte Redaktionelle Workflows**

---

## 1. Ontologie 2.0 (Das Fundament)

### 1.1 Auflösung der doppelten Hierarchie (Finding F2)
Single Source of Truth für alle Hierarchien wird `Artifact.parent`. Das Feld `ArchitectureElement.parent` wird deprecated.

### 1.2 Kontrolliertes, rekursives Architektur-Vokabular
Die Architektur wird streng rekursiv zerlegt (Regel HIER-003):
- `system` (L0) darf keinen Parent haben.
- `subsystem` (L1..Ln-1) ist Kind eines `system` oder `subsystem`.
- `component` (Ln) ist zwingend Kind eines `subsystem` und darf **keine weiteren architektonischen Kinder** haben.

### 1.3 Neues TraceLink-Konzept: Dynamisches Tri-Label-System (DE/EN)
Der generische Typ `parent-child` wird durch `decomposes` ersetzt. TraceLinks werden dynamisch aus der Upstream-/Downstream-Perspektive gelabelt.

| Interner Typ | Sprache | Downstream (Source → Target) | Upstream (Target → Source) | Neutral |
|--------------|---------|------------------------------|-----------------------------|---------|
| `decomposes` | **DE** | **"zerlegt sich in"** | **"ist Zerlegung von"** | Dekomposition |
| | **EN** | **"decomposes into"** | **"is decomposition of"** | Decomposition |
| `allocated-to` | **DE** | **"allokiert zu"** | **"erhält Allokation von"** | Allokation |
| | **EN** | **"allocated to"** | **"receives allocation from"** | Allocation |

---

## 2. Der SE-Auditor (Regelwerk & Engine)

### 2.1 Die Pflichtmatrix
Die Architektur-Dekomposition muss die Req-Ebene nachziehen.

| Regel-ID | Beschreibung (Pflicht im SE-Modus) |
|----------|------------------------------------|
| **TRACE-P1** | Jeder `StakeholderNeed` leitet `SystemRequirements` ab (`derives-from`). |
| **TRACE-P2** | Jedes Requirement (ab L1) ist auf ein `ArchitectureElement` allokiert (`allocated-to`). |
| **TRACE-P3** | Jedes `ArchitectureElement` erfüllt (`satisfies`/`implements`) mindestens ein Requirement. |
| **ARCH-003** | Architektur-Dekomposition (`decomposes`) erzeugt immer Requirement-Ableitungen (`derives-from`) auf der neuen Ebene. |
| **VERIF-P8** | Jedes Requirement (Blattebene) hat einen verknüpften `TestCase` (`verifies`). |

---

## 3. Workflows: Aktueller Systemstand vs. Neues Konzept

### 3.1 Analyse: Der aktuelle Systemstand
Aktuell lädt die Methode `initialize_definition` in `backend/workflow/services.py` das JSON-Schema für die Workflows in die Workspace-Datenbank (`we_engine_definition`). 

**Das Problem im Ist-Zustand:**
Nur `Requirements` reagieren auf das eingestellte Rigor-Level (`active_tier`). 
- Req (Minimal): `draft`, `done`
- Req (Standard): `draft`, `approved`, `deprecated`
- Req (Extended): `draft`, `in_review`, `approved`, `implemented`, `verified`, `deprecated`

Alle anderen Artefakte ignorieren das Tier und laden dumme, statische Defaults:
- `ArchitectureElements`: `["draft", "in_review", "approved", "deprecated"]`
- `TestCases`: `["Draft", "Ready", "Approved", "Deprecated"]`

Zudem enthält der alte Extended-Workflow für Requirements den Status `verified`. Das ist ein Anti-Pattern, da Verifikation eine berechenbare System-Metrik ist (Testausführung).

### 3.2 Das neue Konzept: Menschlicher Workflow vs. Berechneter Badge
> [!IMPORTANT]
> **Trennungsprinzip:** Die Workflow-Engine verwaltet NUR noch Zustände, die **menschliche Arbeitsschritte** und **Verantwortlichkeiten** abbilden (inkl. "Implemented" als "Dev-Team ist fertig mit Coden"). 
>
> Berechenbare Fakten (wie "Verified" oder "Baselined") verschwinden aus den manuellen Status-Transitions und werden vom UI als Badge `[✅ Verified]` berechnet.

### 3.3 Das "Perfekte" Workflow-Modell (Je Modus, Je Artefakt)

Hier ist die detaillierte Aufschlüsselung der menschlichen Zustände. Jeder Workspace erhält bei der Initialisierung genau diese JSON-States aus `definition_store.py`:

#### 📄 Artefakt: Requirement (System / Subsystem / Component Req)
* **Minimal (Agile):** 
  `Draft` ➔ `Done` ➔ `Deprecated`
  *(Sehr schnell. Erfasst -> Umgesetzt. Kein separates Approved).*
* **Standard (INCOSE):** 
  `Draft` ➔ `In Review` ➔ `Approved` ➔ `Implemented` ➔ `Deprecated`
  *(Review als Qualitätsschranke. Approved signalisiert Dev-Ready. Implemented signalisiert "Code fertig").*
* **Extended (Safety/DO-178C):** 
  `Draft` ➔ `In Independent Review` ➔ `Approved` ➔ `In Implementation` ➔ `Implemented` ➔ `Deprecated`
  *(Review erfordert Unabhängigkeit. Änderungen nach Approved erfordern oft einen Change Request. "In Implementation" macht sichtbar, woran gerade aktiv gebaut wird).*

#### 💡 Artefakt: Stakeholder Need (Epic / Safety Goal)
* **Minimal:** `Identified` ➔ `In Progress` ➔ `Done` ➔ `Deprecated`
* **Standard:** `Elicited` ➔ `Analyzed` ➔ `Specified` ➔ `Validated`
* **Extended:** `Defined` ➔ `Analyzed` (HARA zwingend) ➔ `Approved` ➔ `Validated`

#### 🏗️ Artefakt: Architecture Element & ICD
Architektur und ICDs sind Design-Spezifikationen. Ihr Workflow gleicht dem von Requirements, endet aber bei `Approved` (Architektur wird nicht "implementiert", sondern die ihr zugeordneten Requirements).
* **Minimal:** `Draft` ➔ `Published` ➔ `Deprecated`
* **Standard:** `Draft` ➔ `In Review` ➔ `Approved` ➔ `Deprecated`
* **Extended:** `Draft` ➔ `In Review` ➔ `CCB Approved` ➔ `Deprecated`

#### 🧪 Artefakt: TestCase
Ein TestCase durchläuft zwei Phasen: Spezifikation (manuell) und Ausführung (automatisiert). Der Workflow kümmert sich nur um die Spezifikationsfreigabe.
* **Minimal:** `Draft` ➔ `Active` ➔ `Deprecated`
* **Standard:** `Draft` ➔ `In Review` ➔ `Ready For Execution` ➔ `Deprecated`
  *(Erst bei 'Ready' darf der TestRunner das Skript ausführen)*
* **Extended:** `Draft` ➔ `In Verification` (Trace-Check bestanden) ➔ `Ready For Execution` ➔ `Deprecated`

#### 📝 Artefakt: ADR (Architecture Decision Record)
* **Minimal:** `Proposed` ➔ `Accepted` ➔ `Superseded`
* **Standard / Extended:** `Proposed` ➔ `Evaluated` ➔ `Approved` ➔ `Superseded`

#### ⚠️ Artefakt: Risk
Ein Risiko ist kein Design-Dokument, sondern ein Zustand der Projektwelt.
* **Minimal:** `Identified` ➔ `Mitigated` ➔ `Closed`
* **Standard:** `Identified` ➔ `Assessed` ➔ `Mitigating` ➔ `Closed`
* **Extended:** `Identified` ➔ `Assessed` ➔ `Mitigating` ➔ `Residual Risk Accepted` ➔ `Closed`

---

## 4. KI-Copilot (Die Automatisierung)

### 4.1 Das Kern-Feature (N1): `architecture.decompose`
* **Workflow:** User wählt ein L1-Subsystem. KI zerlegt es rekursiv **und** generiert die korrespondierenden abgeleiteten Requirements, inklusive aller internen TraceLinks (`decomposes`, `derives-from`, `allocated-to`).

### 4.2 Weitere KI-Funktionen
* **N3 (`traceability.suggest_links`):** KI nutzt Vektor-Embeddings (`pgvector`), um logische TraceLinks vorzuschlagen, die den Audit-Regeln fehlen.
* **N5 (`test.derive_from_requirement`):** Generiert komplette `TestCase`-Drafts inkl. Testschritten basierend auf Requirements.
* **N8 (`audit.ai_review`):** KI liest alle Auditor-Findings und bündelt sie zu strategischen Refactoring-Paketen.

---

## 5. Umsetzungs-Phasenplan

| Phase | Fokus | Zeitraum | Kern-Deliverables |
|-------|-------|----------|-------------------|
| **Phase 1** | Ontologie & Link-Naming | Woche 1 | - DB-Migration `parent-child` → `decomposes`<br>- Tri-Label (DE/EN) |
| **Phase 2** | Auditor Core | Woche 2 | - RuleEngine mit Preset-Vererbung<br>- Scanner für TRACE-P1 bis P7 |
| **Phase 3** | Auditor UI | Woche 3 | - Audit-Dashboard<br>- Adopt/Modify Workflow |
| **Phase 4** | KI Copilot | Woche 4 | - Tool: `architecture.decompose` (N1) |
| **Phase 5** | Workflows *(Letzte Prio)* | Woche 5 | - JSON-Schemas im `definition_store.py` für alle Artefakte auf `draft -> review -> released` umbauen.<br>- UI: Dynamische Badges für *Verified/Baselined* implementieren. |
