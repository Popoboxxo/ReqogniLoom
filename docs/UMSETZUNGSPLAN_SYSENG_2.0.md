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

## 3. KI-Copilot (Die Automatisierung)

### 3.1 Das Kern-Feature (N1): `architecture.decompose`
* **Workflow:** User wählt ein L1-Subsystem. KI zerlegt es rekursiv **und** generiert die korrespondierenden abgeleiteten Requirements, inklusive aller internen TraceLinks (`decomposes`, `derives-from`, `allocated-to`).

### 3.2 Weitere KI-Funktionen
* **N3 (`traceability.suggest_links`):** KI nutzt Vektor-Embeddings (`pgvector`), um logische TraceLinks vorzuschlagen, die den Audit-Regeln fehlen.
* **N5 (`test.derive_from_requirement`):** Generiert komplette `TestCase`-Drafts inkl. Testschritten basierend auf Requirements.
* **N8 (`audit.ai_review`):** KI liest alle Auditor-Findings und bündelt sie zu strategischen Refactoring-Paketen.

---

## 4. Umsetzungs-Phasenplan

| Phase | Fokus | Zeitraum | Kern-Deliverables |
|-------|-------|----------|-------------------|
| **Phase 1** | Ontologie & Link-Naming | Woche 1 | - DB-Migration `parent-child` → `decomposes`<br>- Tri-Label (DE/EN) |
| **Phase 2** | Auditor Core | Woche 2 | - RuleEngine mit Preset-Vererbung<br>- Scanner für TRACE-P1 bis P7 |
| **Phase 3** | Auditor UI | Woche 3 | - Audit-Dashboard<br>- Adopt/Modify Workflow |
| **Phase 4** | KI Copilot | Woche 4 | - Tool: `architecture.decompose` (N1) |
| **Phase 5** | Architecture Decisions | Woche 5 | - MADR-Parser & Linting<br>- REST & MCP APIs für ADRs<br>- eADR Code-Scanner (`@ADR`)<br>- KI-Agenten (`adr-specialist`, `concept-reviewer`) |

---

## 5. Architecture Decision Management (MADR & eADR)

Basierend auf den Prinzipien von Michael Nygard und modernen Ansätzen (MADR, eADR) wird ReqFlow zu einer zentralen Plattform für Architekturentscheidungen **der Endanwender**.

### 5.1 MADR als Standard-Format für Nutzer-Projekte
ReqFlow befähigt seine Nutzer, die Architekturentscheidungen ihrer eigenen Projekte nach dem **MADR (Markdown Architectural Decision Records)** Standard zu verwalten.
* **Bite-Sized & Versionskontrolliert:** ADRs werden als leichte Markdown-Dateien nah am Code (z.B. in `docs/decisions/` oder `doc/arch/adr-NNN.md`) gespeichert.
* **Y-Statements:** Jede Entscheidung muss auf einem prägnanten Y-Statement basieren: *"In the context of [ctx], facing [concern], we decided for [option] and neglected [other options] to achieve [quality], accepting downside [consequence]."*
* **Pflicht-Struktur:** Titel, Context & Problem Statement, Decision Drivers, Considered Options (mit Pros/Cons), Decision Outcome (inkl. Justification), Consequences (Good/Bad).

### 5.2 eADR (Embedded ADRs) & MCP-Auflösung
Um für die Nutzer die Kluft zwischen ihrer Systemdokumentation und ihrem Quellcode zu schließen, stellt ReqFlow eADR-Funktionen bereit.
* Code-Elemente in den Repositories der Nutzer können direkt mit der zugehörigen Entscheidung verlinkt werden (z.B. via Annotationen wie `@ADR(9)` oder Kommentaren).
* **MCP Endpoint für eADRs:** ReqFlow agiert als MCP-Server für die Nutzer. Agenten oder IDEs der Nutzer, die im Code über eine `@ADR(ID)`-Referenz stolpern, können diese ID dynamisch über ReqFlows MCP-Endpunkt (`mcp.eadr.resolve(id)`) auflösen, um den vollen Architektur-Kontext (das MADR) abzurufen.

### 5.3 Agentische Services für ADRs (AI Copilot für Endanwender)
ReqFlow bietet den Nutzern spezialisierte LLM-Agenten, die sie bei ihren Architekturentscheidungen unterstützen:
* **Agent `adr-specialist` (Subagent):**
  * Beobachtet Pull Requests und Issue-Diskussionen in den Nutzer-Repositories.
  * Erkennt implizite Entscheidungen der Teams und draftet automatisch "saubere" MADRs inkl. vorformuliertem Y-Statement als Vorschlag.
* **Agent `concept-reviewer` / `se-critic`:**
  * Führt automatisierte Reviews von ADR-Entwürfen durch.
  * Erkennt und warnt vor Anti-Patterns (z.B. *Pass Through*, *Siding*, *Dead End*, *Groundhog Day*, *Offended Reaction*).
  * Linting der Markdown-Struktur auf Konformität zum "Bare Template" des MADR-Standards.

### 5.4 API & Integrationen (Zurückgestellt / AI-First Fokus)
*Hinweis: Die Bereitstellung klassischer REST-APIs für ADRs wird vorerst zurückgestellt. ReqFlow integriert sich stattdessen zu 100% agentisch in die Toolchain der Nutzer via MCP.*
* **MCP Endpunkte (Model Context Protocol):**
  * `mcp.adr.lint`: LLM-Tool zur Validierung eines Textes gegen die MADR-Regeln und Anti-Patterns.
  * `mcp.adr.draft_y_statement`: Generiert aus einem Problemkontext das formale Y-Statement.
  * `mcp.eadr.resolve`: Löst eine eADR-ID aus dem Quelltext auf und liefert das verknüpfte MADR zurück, oder findet alle Code-Referenzen zu einer bestimmten ADR-ID.
