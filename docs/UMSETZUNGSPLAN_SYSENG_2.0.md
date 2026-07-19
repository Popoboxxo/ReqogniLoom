# ReqFlow SysEng 2.0 — Detaillierter technischer Implementierungsplan

> **Datum:** 2026-07-19 | **Status:** User Review Required (Revision nach Code-Gegenprüfung)
> **Scope:** Ontologie-Konsolidierung, zweisprachiges Link-Naming, Traceability-Auditor, AI-Erweiterungen & ADR-Erweiterung
>
> **Revisionshinweis:** Diese Fassung wurde gegen den produktiven Code geprüft (vier Recherche-/Review-Durchgänge,
> 2026-07-19). Die ursprüngliche Fassung enthielt einen kritischen Architektur-Fehler in Abschnitt 1 (SSOT-Richtung)
> und einen Sachfehler in Abschnitt 5 (ADR-REST-API wurde fälschlich als "zurückgestellt" bezeichnet, obwohl sie
> produktiv existiert). Beide sind unten korrigiert; alle Abweichungen vom ursprünglichen Plan sind mit
> Datei:Zeile-Referenzen belegt.

---

## 1. Ontologie 2.0 (Das Fundament)

### 1.1 Zwei-Track-Hierarchie statt einheitlichem SSOT (Finding F2 — korrigiert)

**Die ursprüngliche Annahme war falsch.** Der ursprüngliche Plan sah vor, `Artifact.parent` zum Single Source of
Truth (SSOT) für alle Hierarchien zu machen und `ArchitectureElement.parent` zu deprecaten. Eine Code-Gegenprüfung
zeigt: `ArchitectureElement.parent_id` ist der voll etablierte, produktiv genutzte SSOT für die
Architektur-Element-Hierarchie und wird an mehreren kritischen Stellen konsumiert:

- **CTE-Manager:** `backend/persistence/managers.py:33-105` (`get_with_level()`) — PostgreSQL `WITH RECURSIVE`
  berechnet die Baumtiefe in einer einzigen Query.
- **In-Memory-Baum:** `backend/application/architecture_service.py:350-378` (`_annotate_levels()`).
- **Invarianten-Validator:** `backend/application/validators.py:196,216-217,282,294` — Invariante I2 sowie der
  Zyklen-Check hängen direkt an `parent_id`.
- **Serializer:** `backend/rest_api/views.py:2801-2827`.
- **Workspace-Klon:** `backend/application/workspace_service.py:258-281` (Parent-Remapping beim Klonen).
- **Frontend-Tree:** `frontend/src/components/ArchitectureEditors/DecompositionTree.tsx:82-94,255,322` rendert
  direkt gegen `ArchitectureElement.parent`.

Ein Deprecaten von `ArchitectureElement.parent` würde CTE-Manager, Validator und Frontend-Tree brechen — das ist
kein Refactoring, sondern ein produktionsgefährdender Breaking Change.

Gleichzeitig ist `TraceLink(link_type='derives-from')` bereits der **de-facto-SSOT** für die
Requirement/Need-Hierarchie:

- Aktiv erzeugt in `backend/application/requirement_service.py:620,640` und
  `backend/application/management/commands/migrate_se_docs.py:971-1042`.
- Konsumiert für Traversierung in `backend/baseline/services.py:318-335` und
  `backend/baseline/delta_index_builder.py:251-271` — dort **explizit als Ersatz für `Artifact.parent`** gebaut.
- Frontend: `frontend/src/components/RequirementEditors/RequirementTreeNode.tsx:4,63-68` baut den
  Requirement-Baum aus `derives-from`-Links.

`Artifact.parent` ist trotz Deprecation-Docstring (`backend/persistence/models.py:509-529`) **nicht tot** — es hat
zwei aktive Schreibpfade: den ReqIF-Roundtrip (`backend/application/reqif_import_service.py:717-753`, bewusst für
REQ-146/147 beibehalten) und den generischen `ArtifactService.update()`-Pfad
(`backend/application/artifact_service.py:237-239`).

`TraceLink(link_type='parent-child')` ist weitgehend totes Gewicht im Sinne eines aktiven Domain-Erzeugers — mit
einer offenen Ausnahme, siehe Kasten unten.

> **DECISION**
> **context:** Welches Feld/welcher Link-Typ ist SSOT für Hierarchien in ReqFlow?
> **choice:** Kein einheitliches SSOT. Stattdessen wird das bereits gelebte **Zwei-Track-Modell** formalisiert:
>   (a) `ArchitectureElement.parent_id` bleibt SSOT für die Architektur-Element-Hierarchie (kein Deprecation).
>   (b) `TraceLink(derives-from)` wird offiziell zum SSOT für die Requirement/Need-Hierarchie erklärt (bereits
>       de-facto der Fall, wird nur noch dokumentiert statt neu gebaut).
>   (c) `Artifact.parent` wird explizit auf den ReqIF-Roundtrip-Zweck reduziert und als solcher dokumentiert
>       (kein genereller Hierarchie-Mechanismus mehr, aber wegen REQ-146/147 nicht entfernbar).
>   (d) `parent-child` → `decomposes` wird **nicht als Rename**, sondern als additiver neuer Link-Typ eingeführt
>       (siehe 1.3/1.4).
> **alternatives:**
>   - Einheitliches SSOT auf `Artifact.parent` (Original-Plan) — verworfen: bricht CTE-Manager, Validator,
>     Frontend-Tree, keine Migrationsstrategie vorhanden, hoher Blast-Radius ohne Nutzen.
>   - Einheitliches SSOT auf `ArchitectureElement.parent` inkl. Requirements — verworfen: Requirements sind kein
>     `ArchitectureElement`, Modellbruch.
>   - Rename `parent-child` → `decomposes` in-place — verworfen: siehe 1.4, bricht `SAME_TYPE`-Constraint-Historie
>     und Baseline-Reproduzierbarkeit.
> **consequences:** Zwei parallele, aber sauber getrennte Hierarchie-Mechanismen bleiben bestehen (kein
> "Aufräumen" im Sinne einer Vereinheitlichung). Dafür: keine Breaking Changes, kein Migrations-Risiko für
> bestehende Baselines/Klone. Dokumentation muss beide Tracks klar benennen, damit zukünftige Features nicht
> erneut den Fehler machen, einen der beiden Tracks für "das eine SSOT" zu halten.

> **Offene Frage — vor Phase 1 zu klären:**
> Ob `requirement_service.py:620` (`decompose()`) in der Praxis tatsächlich `parent-child`-TraceLinks erzeugt,
> war ursprünglich nicht abschließend verifiziert. **Vorläufiger Befund (Code-Check 2026-07-19):**
> `Workspace.decomposition_link_type` hat den Modell-Default `"parent-child"`
> (`backend/persistence/models.py:460-465`), und `decompose()` übernimmt diesen Default ungefiltert
> (`requirement_service.py:618-619`, `getattr(workspace, "decomposition_link_type", "parent-child")`) und erzeugt
> darüber einen TraceLink (`requirement_service.py:634-639`). Das spricht dafür, dass `parent-child`-Links **aktiv
> erzeugt werden**, solange ein Workspace den Default nicht explizit überschreibt — die Einschätzung "totes
> Gewicht" ist damit vermutlich zu optimistisch. Nicht verifiziert: ob Seed-/Produktiv-Workspaces den Default in
> der Praxis überschreiben. **Vor Phase 1 verbindlich zu klären:** Query über bestehende Workspaces
> (`decomposition_link_type` Verteilung) und über bestehende TraceLinks (Anzahl `parent-child` vs. `decomposes`),
> um die tatsächliche Datenlage zu kennen, bevor der Default umgestellt wird (siehe 1.4).

### 1.2 Kontrolliertes, rekursives Architektur-Vokabular

Die Architektur wird streng rekursiv zerlegt (Regel HIER-003):

- `system` (Wurzel, keine architektonische Tiefenangabe außerhalb dieser Achse) darf keinen Parent haben.
- `subsystem` ist Kind eines `system` oder eines weiteren `subsystem`.
- `component` ist zwingend Kind eines `subsystem` und darf **keine weiteren architektonischen Kinder** haben.

**Achsen-Klarstellung (neu, aus Korrektur 3 übernommen):** Die ursprüngliche Fassung bezeichnete `system` als "L0".
Das kollidiert mit der in `CLAUDE.md` und dem V-Modell etablierten Traceability-Achse
(`L0` = Stakeholder Needs → `L1` = System Requirements → `L2` = Subsystems → `L3` = Components →
`L4` = Presentation). Es gibt in ReqFlow **zwei unabhängige Achsen**, die nicht denselben Namensraum teilen
dürfen:

| Achse | Zweck | Werte |
|-------|-------|-------|
| **Traceability-Achse (L0-L4)** | V-Modell-Ebene eines Requirements/Artefakts, aus `CLAUDE.md` | L0 Stakeholder Needs, L1 System Requirements, L2 Subsystems, L3 Components, L4 Presentation |
| **Architektur-Tiefenachse** | Baumtiefe eines `ArchitectureElement` relativ zur Wurzel (`level`, via CTE) | 0 = `system` (Wurzel), 1..n-1 = `subsystem`, n (Blatt) = `component` |

Verbindliche Zuordnung: Ein `ArchitectureElement` vom Typ `system` liegt inhaltlich auf Traceability-Ebene **L2**
(Subsystems im V-Modell-Sinn), `component` auf **L3**. Traceability-`L0`/`L1` (Stakeholder Needs, System
Requirements) haben **kein** `ArchitectureElement`-Gegenstück — sie sind reine Requirement-Artefakte. **L4
(Presentation)** ist in der Architektur-Tiefenachse aktuell nicht abgebildet; siehe Offener Punkt in Abschnitt 2.

Alle Regeln in Abschnitt 2 verwenden ab sofort ausschließlich die Traceability-Achse (L0-L4), wenn von
"Ebene" die Rede ist. Die Architektur-Tiefenachse wird nur noch als "Baumtiefe"/"level" bezeichnet, nie als "L*".

### 1.3 TraceLink-Konzept: Tri-Label-System (DE/EN) — Scope auf 7 Typen erweitert

Der Link-Typ `decomposes` wird **additiv neu eingeführt** (kein Rename von `parent-child`, siehe 1.4).
`allocated-to` **existiert bereits produktiv** (REQ-L1-042, `backend/traceability/types.py`, `LinkType.ALLOCATED_TO`)
— neu ist ausschließlich das Tri-Label-Anzeigeschema, nicht der Link-Typ selbst. Das muss im UI-Wording klar
kommuniziert werden, damit nicht der Eindruck entsteht, Allokation sei eine neue Fähigkeit.

TraceLinks werden dynamisch aus der Upstream-/Downstream-Perspektive gelabelt:

| Interner Typ | Sprache | Downstream (Source → Target) | Upstream (Target → Source) | Neutral |
|--------------|---------|------------------------------|-----------------------------|---------|
| `decomposes` | **DE** | **"zerlegt sich in"** | **"ist Zerlegung von"** | Dekomposition |
| | **EN** | **"decomposes into"** | **"is decomposition of"** | Decomposition |
| `allocated-to` | **DE** | **"allokiert zu"** | **"erhält Allokation von"** | Allokation |
| | **EN** | **"allocated to"** | **"receives allocation from"** | Allocation |

**Scope-Entscheidung (neu):** `LinkType` umfasst 13 Werte (`backend/traceability/types.py:33-50`:
`parent-child`, `derives-from`, `satisfies`, `verifies`, `implements`, `refines`, `documents`, `realizes`,
`traces`, `copy-of`, `allocated-to`, `uses-term`, `decides`). Der ursprüngliche Plan labelte nur 2 von 13 Typen,
obwohl in Abschnitt 2 tragende Typen wie `derives-from`, `satisfies`, `verifies`, `implements`, `refines`
ungelabelt blieben — inkonsistentes UI-Erlebnis.

> **DECISION**
> **context:** Wie viele der 13 `LinkType`-Werte bekommen ein Tri-Label?
> **choice:** Tri-Label-Schema wird auf die SE-relevante Untermenge von **7 Typen** erweitert:
> `derives-from`, `satisfies`, `verifies`, `implements`, `refines`, `allocated-to`, `decomposes`. Für die
> restlichen 6 Typen (`parent-child`, `documents`, `realizes`, `traces`, `copy-of`, `uses-term`, `decides` —
> das sind 7, siehe Korrektur unten) gilt ein expliziter **Fallback**: rohe Enum-Anzeige (kein Tri-Label,
> kein Downstream/Upstream-Wording).
> **alternatives:** Alle 13 Typen labeln — verworfen, viele Typen (`copy-of`, `uses-term`, `documents`) haben
> keine sinnvolle Upstream/Downstream-Semantik. Nur 2 Typen wie im Original — verworfen, inkonsistent zu
> Abschnitt 2.
> **consequences:** UI-Komponenten, die TraceLinks rendern, brauchen eine Fallback-Pfad-Implementierung für
> die nicht gelabelten Typen (kein reiner Lookup-Table-Zugriff mehr, sondern `if type in LABELED_SET`-Verzweigung).

*(Hinweis: 7 gelabelte + 6 Fallback-Typen = 13, konsistent mit dem vollständigen Enum.)*

### 1.4 Migrationsstrategie `decomposes` (additiv, nicht Rename)

Ein direktes Rename `parent-child` → `decomposes` wurde geprüft und verworfen:

- `SE_LINK_SEMANTICS[LinkType.PARENT_CHILD.value] = SAME_TYPE` (`backend/traceability/types.py:92-102`) ist ein
  aktiver Endpunkt-Constraint. Ein Rename würde eine Migration dieses Constraints erzwingen, ohne fachlichen
  Mehrwert.
- Baseline-Snapshots (`baseline/`-App) speichern `link_type` als unveränderlichen String je Snapshot. Ein Rename
  bestehender Datensätze würde historische Baselines nicht mehr korrekt reproduzierbar machen (ein Snapshot von
  vor der Migration zeigt dann einen Typ, der zum Snapshot-Zeitpunkt so nicht existierte).

Stattdessen: `decomposes` wird als **neuer, additiver** `LinkType`-Wert eingeführt.
`Workspace.decomposition_link_type` wird **schrittweise** (nur für neu angelegte Workspaces, dann optional per
Migrationsscript für aktive Workspaces nach Bestätigung) von `"parent-child"` auf `"decomposes"` umgestellt.
Bestehende `parent-child`-Datensätze und -Baselines bleiben unangetastet. Details zu Akzeptanzkriterien,
betroffenen Dateien und Rollback siehe Phase 1 in Abschnitt 4.

---

## 2. Der SE-Auditor (Regelwerk & Engine)

### 2.1 Verhältnis zu bestehender Endpunkt-Validierung (neu, Korrektur 3)

Der SE-Auditor implementiert **keine neue** Endpunkt-Legalitätsprüfung — diese existiert bereits als
`SE_LINK_SEMANTICS` / `check_se_link_semantics` (`backend/traceability/types.py:92-102`) und wird bei
Link-Erstellung durchgesetzt (welche Artefakttypen dürfen über welchen `LinkType` verbunden werden).

Der Auditor setzt darauf **auf** und prüft eine andere Dimension:

| | **SE_LINK_SEMANTICS (bestehend)** | **Pflichtmatrix/RuleEngine (SE-Auditor, neu)** |
|---|---|---|
| **Frage** | Dürfen diese zwei Artefakttypen über diesen Link-Typ verbunden werden? | Ist der Traceability-Graph vollständig — hat jeder Need ein Requirement, ist jedes Requirement alloziert, etc.? |
| **Zeitpunkt** | Bei Link-Erstellung (synchron) | Zur Audit-Zeit (on-demand oder periodisch) |
| **Scope** | Einzelner Link | Gesamter Graph pro Baseline-Scope |
| **Ort im Code** | `backend/traceability/types.py:92-102` | Neu: RuleEngine (Phase 2) |

Diese Abgrenzung muss in der Implementierung (Docstrings, ADR) explizit referenziert werden, damit die
RuleEngine nicht versehentlich `SE_LINK_SEMANTICS` dupliziert.

### 2.2 Die Pflichtmatrix

Alle Regeln folgen dem Format `Quelle --Linktyp--> Ziel`, konsistent zur Enum-Richtung in `SE_LINK_SEMANTICS`
(z.B. `DERIVES_FROM = {(_REQ, _REQ), (_REQ, _SN), (_SN, _SN)}` bedeutet Source=Requirement, Target=StakeholderNeed
— ein Requirement leitet sich VON einem Need AB, der Link zeigt aber vom Requirement zum Need).

| Regel-ID | Beschreibung (Pflicht im SE-Modus) | Source → Target | Rigor-Preset |
|----------|------------------------------------|------------------|--------------|
| **TRACE-P1** | Jedes `SystemRequirement` (L1) hat einen `derives-from`-Link zu einem `StakeholderNeed` (L0). | Requirement (L1) → StakeholderNeed (L0) | Standard, Extended |
| **TRACE-P1b** | Jedes Requirement **außer L0** hat einen `derives-from`-Upstream (Orphan-Requirement-Check; deckt auch L2/L3-Requirements ab, die von L1 abgeleitet sein müssen). | Requirement (Ln, n>0) → Requirement/Need (Ln-1) | Standard, Extended |
| **TRACE-P2** | Jedes Requirement ab L1 ist auf ein `ArchitectureElement` allokiert. | Requirement (≥L1) → ArchitectureElement | Extended (Standard: Warnung statt Blocker) |
| **TRACE-P3** | Jedes `ArchitectureElement` erfüllt (`satisfies`/`implements`) mindestens ein Requirement. | ArchitectureElement → Requirement | Extended |
| **TRACE-P4** | Jeder `subsystem`/`component` hat mindestens einen `decomposes`-Parent (kein architektonisches Waisenelement außer der Wurzel `system`). | ArchitectureElement → ArchitectureElement | Standard, Extended |
| **TRACE-P5** | Jede `decomposes`-Dekomposition eines Requirements erzeugt konsistente `derives-from`-Ableitungen auf der neuen Ebene (Graph-Konsistenz zwischen Architektur- und Requirement-Baum). | Requirement (Kind) → Requirement (Eltern) | Extended |
| **TRACE-P6** | Jede `TestCase` referenziert über `verifies` mindestens ein existierendes, nicht-superseded Requirement/ArchitectureElement. | TestCase → Requirement/ArchitectureElement | Standard, Extended |
| **TRACE-P7** | Baseline-Scope-Konsistenz: Trace-Links, die innerhalb eines Baseline-Scopes (Document/Project/Global) geprüft werden, referenzieren nur Artefakte desselben oder eines übergeordneten Scopes (kein Scope-Leck). | — (Graph-weite Prüfung je Baseline-Scope) | Extended |
| **ARCH-003** | Architektur-Dekomposition (`decomposes`) erzeugt immer Requirement-Ableitungen (`derives-from`) auf der neuen Ebene. | ArchitectureElement (Kind) → Requirement (neu) | Extended |
| **VERIF-P8** | Jedes Requirement (Blattebene, L3/L4) hat einen verknüpften `TestCase` (`verifies`). | TestCase → Requirement (Blatt) | Extended only (für Minimal/Standard unangemessen streng) |
| **CONS-P9** | Offene (nicht aufgelöste) `CONFLICTS_WITH`-Links blockieren die Approval-Transition eines Artefakts. | — (Zustandsprüfung, kein neuer Link) | Standard, Extended |
| **CONS-P10** | Kein aktiver TraceLink referenziert ein Artefakt, das über `SUPERCEDES` bereits ersetzt wurde (dangling-superseded-Check). | beliebig → superseded Artefakt | Standard, Extended |

**Rule-zu-Rigor-Preset-Mapping (neu, Korrektur 3):** Jede Regel ist oben mit ihrem/ihren Rigor-Preset(s)
versehen. `VERIF-P8` ("jedes Blatt-Requirement braucht einen Test") ist für **Minimal**-Rigor unangemessen streng
(Minimal-Rigor zielt auf leichtgewichtige Backlogs ohne formale Testpflicht) und wird dort nicht angewendet.
Minimal-Rigor hat aktuell **keine** Pflichtregeln aus dieser Matrix — das ist beabsichtigt (Minimal = kein
SE-Auditor-Zwang), muss aber im finalen ADR explizit als Entscheidung festgehalten werden, nicht implizit
gelten.

**Numerierungs-Korrektur:** Der ursprüngliche Phasenplan sprach von "TRACE-P1 bis P7", der Regelkatalog definierte
aber nur P1-P3 (+VERIF-P8). Diese Fassung definiert P1, P1b, P2-P7 vollständig (siehe Tabelle oben) — die
Phasenplan-Referenz in Abschnitt 4 ist jetzt konsistent dazu.

**L4 (Presentation):** Wie in 1.2 vermerkt, hat die Traceability-Achse eine Ebene L4 (Presentation), die
architektonisch nicht abgebildet ist. Für diese Fassung des Plans wird **L4 explizit als out-of-scope für die
SE-Kaskade/den SE-Auditor deklariert** — keine der obigen Regeln erzwingt eine Prüfung auf L4-Artefakten. Sollte
das benötigt werden, ist das ein eigenes Folge-Thema (neue Regel-ID-Reihe, z.B. `PRES-Px`).

### 2.3 Mapping neuer Link-Typen auf die CLAUDE.md-Taxonomie

`CLAUDE.md` definiert 8 Trace-Link-Typen als Projekt-Taxonomie: `TRACE_TO`, `DERIVED_FROM`, `IMPLEMENTS`, `TESTS`,
`VERIFIES`, `RELATED_TO`, `CONFLICTS_WITH`, `SUPERCEDES`. Der Code (`backend/traceability/types.py`) hat davon
abweichend 13 `LinkType`-Werte inklusive der hier neu eingeführten `decomposes` und des bereits bestehenden
`allocated-to`. Diese Diskrepanz ist nicht neu durch dieses Konzept verursacht, wird aber durch `decomposes`
verschärft:

| Neuer/betroffener Typ | CLAUDE.md-Taxonomie-Äquivalent | Anmerkung |
|---|---|---|
| `decomposes` | kein Äquivalent — am ehesten Spezialisierung von `TRACE_TO` | Taxonomie-Erweiterung nötig |
| `allocated-to` (bestehend) | kein Äquivalent — am ehesten Spezialisierung von `TRACE_TO`/`IMPLEMENTS` | Taxonomie-Erweiterung nötig |

**Empfehlung:** `CLAUDE.md` in Phase 1 um diese beiden Einträge ergänzen (Doku-Task, kein Code), statt eine
zweite, abweichende Taxonomie stillschweigend weiterzuführen.

---

## 3. KI-Copilot (Die Automatisierung)

### 3.1 Das Kern-Feature (N1): `architecture.decompose`

* **Workflow:** User wählt ein Subsystem. KI zerlegt es rekursiv **und** generiert die korrespondierenden
  abgeleiteten Requirements, inklusive aller internen TraceLinks (`decomposes`, `derives-from`, `allocated-to`).
* **Human-in-the-Loop / Draft-Staging (neu, Korrektur 4):** Der ursprüngliche Plan ließ N1 in einem Durchlauf
  rekursiv Architektur + Requirements + Links erzeugen, ohne Review-Schritt. Bei rekursiver Tiefe und dem
  Default-LLM-Adapter `mock` (kein produktiver LLM-Provider standardmäßig konfiguriert) ist der Blast-Radius
  eines einzelnen Aufrufs hoch (potenziell dutzende Artefakte + Links in einer Transaktion). N1 wird daher als
  **Draft-Staging-Modell** umgesetzt:
  1. LLM generiert einen Vorschlag (Artefakte + Links) in einem **nicht-persistenten Draft-Objekt**.
  2. User reviewt den Draft im UI (Diff-artige Darstellung, analog zum bestehenden Artifact-Diff-Feature).
  3. Erst nach expliziter Bestätigung wird der Draft in einer einzigen DB-Transaktion committed
     (**transaktionaler Rollback** bei Teilfehler — kein Partial-Commit von Architektur ohne zugehörige
     Requirements).
  4. **Preset-Gating:** N1 ist nur in `standard`/`extended` Rigor verfügbar, nicht in `minimal` (Minimal-Rigor
     hat keine SE-Auditor-Pflichten, gegen die der generierte Baum geprüft werden könnte).
* **Abhängigkeit zu ARCH-003:** Der von N1 erzeugte Output muss den Auditor bestehen (mindestens ARCH-003 und
  TRACE-P4/P5) — das ist ein Akzeptanzkriterium für N1, kein optionales Nice-to-have. N1 kann daher frühestens
  nach Phase 2 (RuleEngine) sinnvoll gebaut werden, nicht unabhängig davon.

### 3.2 Weitere KI-Funktionen

* **N3 (`traceability.suggest_links`):** KI schlägt TraceLinks vor, die den Audit-Regeln fehlen.
  **Infrastruktur-Abhängigkeit (neu, Korrektur 4):** Der ursprüngliche Plan nannte `pgvector`-Embeddings als
  Umsetzung, ohne dies als Abhängigkeit zu benennen. Der aktuelle Stack (PostgreSQL 16) hat **keine**
  `pgvector`-Extension installiert. Das ist kein triviales Add-on, sondern ein eigener Dependency-/Spike-Posten:
  Extension-Installation, Wahl des Embedding-Modells, initialer Backfill aller Artefakte, Re-Embedding-Strategie
  bei Artefakt-Änderungen (Trigger vs. Batch-Job). **Alternative, die geprüft werden sollte:** Da der Auditor
  (Abschnitt 2) fehlende Links bereits deterministisch findet (z.B. TRACE-P1b: Requirement ohne
  `derives-from`-Upstream), könnte N3 in einer ersten Ausbaustufe primär die **Auditor-Findings ranken und
  erklären** (welches der mehreren plausiblen Ziel-Artefakte ist am wahrscheinlichsten gemeint), statt eine
  unabhängige Vektorsuche über den gesamten Artefaktbestand zu betreiben. Das verschiebt die pgvector-Entscheidung
  auf eine spätere, optionale Ausbaustufe.
* **N5 (`test.derive_from_requirement`):** Generiert komplette `TestCase`-Drafts inkl. Testschritten basierend
  auf Requirements. Keine RuleEngine-Abhängigkeit, aber inhaltlich sinnvoll erst nutzbar, wenn VERIF-P8 (Auditor)
  Lücken aufzeigt, gegen die generiert werden kann.
* **N8 (`audit.ai_review`):** KI liest alle Auditor-Findings und bündelt sie zu strategischen
  Refactoring-Paketen. **Harte Abhängigkeit** zu Phase 2 (RuleEngine muss Findings liefern) und Phase 3
  (Findings-Format/-Persistenz aus dem Audit-Dashboard).

**Reservierte Tool-IDs (neu, Korrektur 4):** Die Nummerierung N1, N3, N5, N8 hat Lücken (N2, N4, N6, N7). Diese
sind **nicht** Tippfehler, sondern für zukünftige, in diesem Konzept noch nicht spezifizierte KI-Tools reserviert
(z.B. Requirement-Qualitätsprüfung, ADR-Vorschläge — letzteres siehe Abschnitt 5). Sie werden hier bewusst nicht
belegt, um spätere Konzepte nicht mit Nummern aus diesem Dokument zu kollidieren.

---

## 4. Umsetzungs-Phasenplan

**Grundprinzip (neu, Korrektur 6):** Jede Phase hat jetzt Akzeptanzkriterien, betroffene Dateien/Module,
Abhängigkeiten zur Vorphase und — wo DB-relevant — eine Migrations-/Rollback-Betrachtung. Zwischen Phase 1 und
Phase 2 gibt es ein verbindliches Verifikations-Gate (der ursprüngliche Plan hatte 0 Puffer und keine
Verifikationsschranke zwischen den Wochen).

### Phase 1 — Ontologie & Link-Naming (Woche 1)

**Deliverables:**
- Offene Frage aus 1.1 klären (Query über bestehende Workspaces/TraceLinks bzgl. `parent-child`-Nutzung).
- `decomposes` als additiver `LinkType`-Wert (kein Rename, siehe 1.4).
- `Workspace.decomposition_link_type`-Default für **neue** Workspaces auf `decomposes` umstellen (bestehende
  Workspaces unverändert, bis explizit migriert).
- Tri-Label-Lookup (DE/EN) für die 7 in 1.3 festgelegten Typen + Fallback-Pfad für die restlichen 6.
- `CLAUDE.md`-Taxonomie um `decomposes`/`allocated-to` ergänzen (Doku).

**Betroffene Dateien/Module:**
- `backend/traceability/types.py` (neuer `LinkType.DECOMPOSES`, `SE_LINK_SEMANTICS`-Eintrag).
- `backend/persistence/models.py` (Default-Wert-Änderung `decomposition_link_type`, nur für neue Instanzen —
  kein Schema-Migrationsbedarf, da Feld bereits existiert).
- `backend/application/requirement_service.py:618-639` (liest weiterhin den Workspace-Default, keine
  Code-Änderung nötig, sofern der Default korrekt greift).
- Neue Migration in `backend/traceability/migrations/` oder `backend/persistence/migrations/` (je nachdem, wo
  `LinkType`-Validierung technisch verankert ist — zu prüfen, ob ein reiner Enum-Wert überhaupt eine
  Django-Migration braucht, da `link_type` als `CharField` ohne DB-Constraint gespeichert wird).
- Frontend: Tri-Label-Lookup-Komponente (Ort noch offen — vermutlich `frontend/src/components/Traceability/` oder
  `frontend/src/i18n/`), `frontend/src/i18n/locales/{de,en}.json` (neue Label-Strings).
- `CLAUDE.md` (Taxonomie-Ergänzung).

**Akzeptanzkriterien:**
- [ ] Query-Ergebnis zur offenen Frage aus 1.1 liegt vor und ist im Dokument/ADR referenziert.
- [ ] Neuer Workspace erzeugt bei `decompose()` einen `decomposes`-Link (nicht `parent-child`).
- [ ] Bestehende Workspaces/TraceLinks mit `parent-child` sind unverändert (Regressionstest: bestehende
  Baseline-Snapshots mit `parent-child`-Links diffen weiterhin korrekt).
- [ ] Tri-Label wird für alle 7 definierten Typen in beiden Sprachen korrekt gerendert; Fallback für die
  restlichen 6 Typen zeigt den rohen Enum-Wert ohne Fehler.
- [ ] `ArchitectureElement.parent` bleibt unverändert funktionsfähig (CTE, Validator, Frontend-Tree — keine
  Regression, per bestehender Test-Suite verifiziert).

**Abhängigkeiten:** Keine Vorphase (Phase 1 ist der Start).

**Migration/Rollback:**
- Kein Schema-Migrationsbedarf für `link_type` selbst (CharField ohne FK/Enum-Constraint auf DB-Ebene).
- Default-Wert-Änderung an `Workspace.decomposition_link_type` betrifft nur **neu erzeugte** Workspace-Instanzen
  ab Deploy-Zeitpunkt — kein Backfill bestehender Zeilen.
- **Rollback-Pfad:** Default zurück auf `"parent-child"` setzen (reiner Code-Revert, keine Datenmigration nötig,
  da keine bestehenden Daten verändert wurden). Rollback ist damit risikoarm, sofern Phase 1 keine
  Backfill-Migration bestehender Workspaces enthält (siehe nächster Punkt).
- **Falls** zusätzlich entschieden wird, bestehende aktive Workspaces per Migrationsscript umzustellen: dieses
  Script muss idempotent und einzeln rückrollbar sein (separates Migrationsscript, nicht Teil der
  Django-Schema-Migration), und ist **nicht** Teil des Phase-1-Kern-Scopes, sondern ein optionaler Folge-Schritt
  nach dem Verifikations-Gate.

**Verifikations-Gate vor Phase 2 (Pflicht-Deliverable):**
- [ ] Alle Akzeptanzkriterien oben grün.
- [ ] Rollback-Pfad einmal in einer Nicht-Prod-Umgebung durchgespielt und verifiziert.
- [ ] Bestehende Test-Suiten (`backend/application/tests/`, `backend/traceability/`, Frontend-Vitest für
  `DecompositionTree`/`RequirementTreeNode`) grün.

### Phase 2 — Auditor Core (Woche 2, Start erst nach Verifikations-Gate Phase 1)

**Deliverables:**
- RuleEngine mit Preset-Vererbung (liest das Rule-zu-Rigor-Preset-Mapping aus 2.2).
- Scanner für TRACE-P1, P1b, P2-P7, ARCH-003, VERIF-P8, CONS-P9, CONS-P10 (vollständiger Katalog aus 2.2, nicht
  nur "P1 bis P7" wie ursprünglich unscharf formuliert).
- Explizite Referenz/Wiederverwendung von `SE_LINK_SEMANTICS` für Endpunkt-Legalität (siehe 2.1) — die RuleEngine
  dupliziert diese Prüfung nicht.
- Baseline-Scope-bewusste Ausführung (Regel TRACE-P7 erfordert, dass der Scanner pro Baseline-Scope
  Document/Project/Global getrennt läuft).

**Betroffene Dateien/Module (neu, plausibel):**
- Neues Modul, z.B. `backend/traceability/audit/` oder `backend/audit_engine/` (Namensentscheidung offen) mit
  `rule_engine.py`, `rules/` (ein Modul je Regel-Gruppe).
- `backend/presets/` (Preset-Registry-Anbindung für Rule-zu-Preset-Mapping).
- `backend/baseline/services.py` (Scope-Iteration für baseline-scope-bewusste Prüfung).
- Neue Tests: `backend/traceability/tests/test_rule_engine.py` (oder analog im gewählten Modulpfad).

**Akzeptanzkriterien:**
- [ ] Jede Regel aus 2.2 hat einen Scanner-Test mit mindestens einem Positiv- und einem Negativ-Fall.
- [ ] RuleEngine liefert für `minimal`-Preset keine Findings (siehe 2.2, Minimal hat keine Pflichtregeln).
- [ ] RuleEngine dupliziert nachweislich keine `SE_LINK_SEMANTICS`-Logik (Code-Review-Kriterium).
- [ ] Baseline-Scope-Test: Findings für Scope "Document A" unterscheiden sich korrekt von Scope "Project X", wenn
  Artefakte nur in einem der beiden Scopes vorhanden sind.

**Abhängigkeiten:** Phase 1 abgeschlossen + Verifikations-Gate bestanden (RuleEngine braucht den finalen
`decomposes`-Link-Typ und das Tri-Label-Schema als Eingabe für Finding-Texte).

**Migration/Rollback:** Kein Schema-Change (RuleEngine ist reine Lesepfad-Logik über bestehende Daten). Rollback
= Feature-Flag/Deaktivierung der RuleEngine-Endpunkte, keine Datenmigration betroffen.

### Phase 3 — Auditor UI (Woche 3)

**Deliverables:**
- Audit-Dashboard (Findings-Liste, gruppiert nach Regel/Scope/Rigor-Preset).
- Adopt/Modify-Workflow (User kann eine Finding-basierte Korrektur direkt übernehmen oder anpassen).

**Betroffene Dateien/Module (plausibel):**
- `frontend/src/components/Audit/` (neuer Component-Bereich, analog zu bestehenden 17 Component-Bereichen).
- `backend/rest_api/views.py` (neuer Audit-Endpoint, liest RuleEngine-Ergebnis über `application/`-Service,
  keine direkten Model-Queries in der View gemäß Code-Konvention).
- `backend/application/` (neuer `audit_service.py` als Single-Entry-Point-Fassade zur RuleEngine, ADR-01-konform).

**Akzeptanzkriterien:**
- [ ] Dashboard zeigt Findings aller in Phase 2 implementierten Regeln, gefiltert nach aktivem Rigor-Preset des
  Workspace.
- [ ] Adopt-Workflow erzeugt nachweislich einen korrekten TraceLink/Feld-Update (Regressionstest gegen die in
  Phase 2 verifizierten Negativ-Fälle — nach Adopt wird aus Negativ- ein Positiv-Fall).
- [ ] data-testid auf allen neuen interaktiven Elementen (Projekt-Konvention, E2E-Pflicht).

**Abhängigkeiten:** Phase 2 (RuleEngine muss Findings im stabilen Format liefern, auf dem das Dashboard aufbaut).

**Migration/Rollback:** Kein Schema-Change. Rollback = UI-Route deaktivieren.

### Phase 4 — KI-Copilot (Woche 4-5, aufgeteilt in zwei Teilphasen)

**Reihenfolge-Korrektur (Korrektur 6):** Der ursprüngliche Plan terminierte nur N1 in Phase 4 und ließ N3/N5/N8
unverplant, obwohl sie von RuleEngine (Phase 2) bzw. Findings-Format (Phase 3) abhängen. Diese Fassung teilt
Phase 4 entsprechend der Abhängigkeiten:

**Phase 4a (Woche 4):**
- N1 (`architecture.decompose`) im Draft-Staging-Modell (siehe 3.1). Abhängig von Phase 2 (ARCH-003/TRACE-P4/P5
  müssen prüfbar sein, bevor N1-Output dagegen validiert werden kann).
- N5 (`test.derive_from_requirement`) — keine RuleEngine-Hard-Dependency, kann parallel zu N1 laufen.

**Phase 4b (Woche 5):**
- N8 (`audit.ai_review`) — abhängig von Phase 3 (stabiles Findings-Format aus dem Audit-Dashboard).
- N3 (`traceability.suggest_links`) in der in 3.2 beschriebenen Erststufe (Ranking bestehender Auditor-Findings,
  **nicht** die volle `pgvector`-Vektorsuche — diese ist ein separater Spike, siehe unten).

**Betroffene Dateien/Module (plausibel):**
- `backend/mcp_server/` (neue Tool-Registrierungen N1/N3/N5/N8 in der jeweiligen Tool-Gruppe).
- `backend/llm_adapter/` (Prompt-Templates je Tool, Capability-Checks für graceful degradation bei `mock`-Adapter).
- `backend/application/` (Service-Fassaden je Tool, ADR-01-konform).
- Frontend: Draft-Review-UI für N1 (neue Komponente, analog zum bestehenden Artifact-Diff-Feature).

**Akzeptanzkriterien:**
- [ ] N1: Draft wird korrekt gestaged, Review-UI zeigt Diff, Commit ist transaktional (Partial-Commit-Test:
  simulierter Fehler in Requirement-Erzeugung darf keine verwaisten Architektur-Elemente hinterlassen).
- [ ] N1: mit `minimal`-Preset ist der Tool-Aufruf blockiert (Preset-Gating-Test).
- [ ] N1-Output besteht ARCH-003/TRACE-P4/P5 im automatisierten Test (RuleEngine als Prüfinstanz).
- [ ] N8: Refactoring-Pakete referenzieren reale, existierende Findings-IDs aus Phase-3-Dashboard.
- [ ] N3 (Erststufe): Ranking-Ausgabe referenziert existierende Findings, keine pgvector-Abhängigkeit im Code.

**Abhängigkeiten:** Phase 2 (für N1, N3, N8), Phase 3 (für N8, N3).

**Migration/Rollback:** Kein Schema-Change außer ggf. neue Tabelle für Draft-Staging (N1) — falls Drafts
serverseitig persistiert statt rein im Frontend-State gehalten werden, braucht das eine eigene Migration mit
TTL/Cleanup-Job. Rollback: MCP-Tool-Registrierung entfernen/deaktivieren.

**Ausgeklammerter Spike (nicht Teil von Phase 4):** `pgvector`-Extension-Evaluierung (Installation, Embedding-Modell-
Wahl, Backfill-Strategie) als eigener, zeitlich nicht fest eingeplanter Recherche-Posten — erst einplanen, wenn
die Erststufe von N3 (Findings-Ranking) als unzureichend bewertet wird.

### Phase 5 — ADR-Erweiterung (Woche 6)

**Wichtig:** Diese Phase ist **keine Greenfield-Entwicklung**. Der ADR-Funktionsumfang existiert bereits
produktiv (Datenmodell, Service, REST, MCP, Tests — siehe Abschnitt 5.1). Phase 5 erweitert den bestehenden
`adr_service.py` um MADR-Pflichtstruktur und zwei neue MCP-Tools. **eADR ist explizit nicht Teil dieser Phase**
(siehe 5.4).

**Deliverables:**
- MADR-Pflichtstruktur im Datenmodell: strukturierte Felder für Decision Drivers, Considered Options (je mit
  Pros/Cons), Justification (statt reiner Freitext-Felder `context`/`consequences`).
- MCP-Tool `adr.lint` (Validierung eines ADR-Texts gegen MADR-Struktur).
- MCP-Tool `adr.draft_y_statement` (generiert aus Kontext ein Y-Statement als optionale Zusammenfassung, siehe
  5.2 — kein Pflichtfeld).
- Content-Anti-Pattern-Checks für den Review-Workflow (siehe 5.5) — keine neuen Agenten.

**Betroffene Dateien/Module (plausibel):**
- `backend/application/models.py:191-262` (`Adr`-Modell — neue strukturierte Felder statt/zusätzlich zu
  `context`/`consequences`).
- `backend/application/migrations/` (neue Migration `0008_...` — Reihenfolge nach den bestehenden 0003, 0005,
  0006, 0007; **nicht** unter `persistence/migrations/`, da die `Adr`-Entity in der `application`-App liegt).
- `backend/application/adr_service.py:134-472` (Erweiterung um Validierung der MADR-Pflichtstruktur, neue
  Service-Methoden für `lint`/`draft_y_statement`).
- `backend/rest_api/views.py:3387-3571`, `backend/rest_api/urls.py:117` (Serializer-Erweiterung für neue Felder,
  keine neuen Routen nötig — bestehender `AdrViewSet` deckt CRUD bereits ab).
- `backend/mcp_server/tool_registry.py:301` (neue Tool-Registrierungen `adr.lint`, `adr.draft_y_statement`,
  zusätzlich zu den bestehenden `adr.read/create/update/delete`).
- `backend/application/tests/test_adr_service.py` (neue Testfälle für MADR-Validierung, Lint, Y-Statement).
- Frontend: ADR-Editor-Komponente (Ort zu identifizieren, vermutlich `frontend/src/components/` — neuer oder
  bestehender ADR-Bereich, mit strukturierten Formularfeldern statt Freitext).

**Akzeptanzkriterien:**
- [ ] Neues ADR mit unvollständiger MADR-Struktur (z.B. fehlende Considered Options) wird von `adr.lint` als
  Finding markiert, nicht hart blockiert (Lint = Warnung, kein Hard-Gate, um bestehende ADRs nicht zu brechen).
- [ ] Bestehende ADRs (vor der Migration erstellt) bleiben lesbar und editierbar (Backward-Compat-Test: alte
  Freitext-`context`/`consequences`-Werte werden nicht zerstört, sondern die neuen Felder sind additiv/optional).
- [ ] `adr.draft_y_statement` liefert einen syntaktisch korrekten Y-Statement-Text gemäß der in 5.2 zitierten
  Formel.
- [ ] Content-Anti-Pattern-Check erkennt mindestens: fehlende Alternativen, fehlende Consequences, Entscheidung
  ohne Rationale (siehe 5.5) an einem präparierten Test-ADR.

**Abhängigkeiten:** Keine Hard-Dependency zu Phase 1-4 (ADR-Erweiterung ist funktional unabhängig vom
Ontologie-/Auditor-/Copilot-Strang). Kann parallel zu Phase 2-4 gestartet werden, falls Kapazität vorhanden ist —
im sequenziellen Plan hier als Woche 6 eingeplant, um Ressourcenkonflikte zu vermeiden.

**Migration/Rollback:** Neue Felder am `Adr`-Modell werden additiv (nullable/mit Default) migriert, keine
bestehenden Spalten werden entfernt. Rollback: Migration `0008` zurückrollen, Service-Code-Revert — bestehende
`context`/`consequences`-Freitextdaten sind zu keinem Zeitpunkt betroffen.

**Explizit ausgeklammert (kein Teil von Phase 5 — siehe 5.4):**
- eADR-Scanner für `@ADR`-Code-Kommentare.
- MCP-Tool `eadr.resolve`.

---

## 5. Architecture Decision Management (MADR & eADR)

### 5.1 Ist-Stand — bereits produktiv vorhanden (neu, Korrektur 5)

**Der ursprüngliche Plan behandelte ADR-Management fälschlich als Greenfield-Feature und enthielt den
Sachfehler, die REST-API für ADRs sei "vorerst zurückgestellt". Das ist falsch — die REST-API existiert und ist
produktiv im Einsatz.** Bestehender Funktionsumfang:

- **Datenmodell:** `backend/application/models.py:191-262` — `Adr`-Entity mit `title`, `description`, `context`,
  `consequences`, `status` (Draft/In Review/Approved/Rejected/Superseded/Deleted), `version`, `uid`,
  Artifact-Backing (`OneToOne`), Append-Only-Versionierung.
- **Service:** `backend/application/adr_service.py:134-472` — vollständiges CRUD, `WorkflowFacade`-gesteuerte
  Status-Transitions, Soft-Delete, `DECIDES`-TraceLink bei Supersession.
- **REST:** `backend/rest_api/views.py:3387-3571`, Route `backend/rest_api/urls.py:117`
  (`/api/v1/adrs/`, `AdrViewSet`, REQ-L1-029) — List/Create/Detail/Patch/Delete/Diff/Versions/Status-Transition,
  alles produktiv.
- **MCP:** `adr.read/create/update/delete` via `GenericCrudToolGroup`, Registrierung
  `backend/mcp_server/tool_registry.py:301`.
- **Tests:** `backend/application/tests/test_adr_service.py` (Validator, Create, Update, Transition, Soft-Delete,
  Tenant-Isolation, Artifact-Backing).
- **Migrationen:** liegen unter `backend/application/migrations/` (`0003`, `0005`, `0006`, `0007`) — **nicht**
  unter `persistence/migrations/`, wie in einer früheren Annahme fälschlich vermutet.

Abschnitt 5 dieses Plans beschreibt damit **keine Neuentwicklung**, sondern die **Erweiterung** des bestehenden
`adr_service.py` um MADR-Pflichtstruktur (5.3) und zwei neue MCP-Tools (5.3), plus eine bewusst abgespaltene,
separate Initiative für eADR (5.4).

### 5.2 MADR als Zielformat

ReqFlow verwaltet Architekturentscheidungen nach dem **MADR**-Standard — korrekte Ausschreibung ab MADR v3+:
**"Markdown Any Decision Records"** (nicht "Architectural", wie im Original-Plan fälschlich angegeben — MADR
wurde ab Version 3 umbenannt, um auch Nicht-Architektur-Entscheidungen abzudecken).

**Y-Statement — Korrektur (neu, Korrektur 5):** Y-Statement und MADR sind **alternative/komplementäre**
Lean-Formate, kein Y-Statement ist keine MADR-Pflicht. MADR ist section-orientiert (Titel, Context & Problem
Statement, Decision Drivers, Considered Options, Decision Outcome, Consequences) und schreibt kein Y-Statement
vor. In ReqFlow wird das Y-Statement als **optionale, KI-generierbare Zusammenfassung innerhalb** eines MADR
angeboten (`adr.draft_y_statement`, siehe Phase 5), nicht als Pflichtfeld. Der Y-Statement-Wortlaut selbst war im
Original-Plan korrekt und bleibt unverändert:

> *"In the context of [ctx], facing [concern], we decided for [option] and neglected [other options] to achieve
> [quality], accepting downside [consequence]."*

**Pflicht-Struktur (Ziel nach Phase 5):** Titel, Context & Problem Statement, Decision Drivers, Considered
Options (mit Pros/Cons), Decision Outcome (inkl. Justification), Consequences (Good/Bad). Diese Struktur existiert
im aktuellen `Adr`-Modell noch **nicht** vollständig — `context`/`consequences` sind heute Freitextfelder ohne
erzwungene Untergliederung (siehe Phase 5, Akzeptanzkriterien).

### 5.3 Was in Phase 5 tatsächlich fehlt

- MADR-Pflichtstruktur im Datenmodell (Decision Drivers, Considered Options mit Pros/Cons, Justification —
  aktuell nur Freitext-Felder `context`/`consequences`).
- MCP-Tools `adr.lint` (Validierung gegen MADR-Struktur) und `adr.draft_y_statement` (siehe 5.2).
- Content-Anti-Pattern-Checks im Review-Workflow (siehe 5.5).

### 5.4 eADR (Embedded ADRs) — bewusst abgespaltener Scope

**Scope-Trennung (neu, Korrektur 5):** Der eADR-Scanner für `@ADR`-Code-Kommentare in Nutzer-Repositories und das
MCP-Tool `eadr.resolve` sind ein **grundlegend anderer, größerer Scope-Sprung** als die reine
ADR-Datenmodell-Erweiterung in 5.3: externes Repo-/Code-Scanning, potenzieller PR-/Webhook-Zugriff auf
Nutzer-Repositories, eigene Sicherheits- und Berechtigungsfragen (Zugriff auf fremden Quellcode). Dieses Konzept
plant eADR **nicht** als Teil von Phase 5 ein. Empfehlung: eADR als **eigenes Folge-Konzept** ausarbeiten
(eigenes Dokument, eigene Phasenplanung, eigene Sicherheitsbetrachtung), sobald 5.3 abgeschlossen und stabil ist.

Ursprüngliche Idee (Referenz für das Folge-Konzept, hier nicht weiter ausgearbeitet): Code-Elemente in
Nutzer-Repositories werden über Annotationen wie `@ADR(9)` mit der zugehörigen Entscheidung verlinkt; Agenten/IDEs
der Nutzer lösen die ID über einen MCP-Endpunkt (`mcp.eadr.resolve(id)`) auf, um den vollen Architektur-Kontext
abzurufen.

### 5.5 Review-Prozess: Anti-Pattern-Korrektur (neu, Korrektur 5)

**Kategorienfehler im Original-Plan:** Pass-Through, Siding, Dead-End, Groundhog-Day, Offended-Reaction sind echte
Begriffe (Olaf Zimmermann, *"How to review architecture decisions"*, 2023) — sie beschreiben aber Anti-Patterns
des **Review-Prozesses/Reviewer-Verhaltens**, nicht Inhaltsfehler in ADR-Entwürfen. Der Original-Plan verlangte
vom `se-critic`, diese "in ADR-Entwürfen zu erkennen" — das ist fachlich nicht sinnvoll: ein LLM kann
Reviewer-Verhalten (z.B. "Reviewer nimmt jede Aussage des Autors unkritisch hin") nicht aus einem Entwurfstext
herauslesen, der ja gerade noch nicht reviewt wurde.

**Korrektur — beide Optionen kombiniert statt einer Entweder-Oder-Entscheidung:**

1. **Zimmermanns Begriffe werden zu Verhaltens-Leitplanken für den `se-critic`-eigenen Review-Prozess selbst**
   umgedeutet (z.B.: "Vermeide Pass-Through" heißt für den `se-critic`: nicht jede Autoren-Aussage unkritisch als
   erfüllt markieren, sondern aktiv gegenprüfen). Das steuert, *wie* der Agent reviewt.
2. **Für die inhaltliche Prüfung von ADR-Entwürfen (was der Agent im Text tatsächlich flaggen kann) werden echte
   ADR-Inhalts-Anti-Patterns definiert:**
   - Fehlende Alternativen (nur eine Option betrachtet, keine "Considered Options").
   - Fehlende Consequences (Entscheidung ohne dokumentierte Trade-offs).
   - Entscheidung ohne Rationale (Outcome genannt, aber keine nachvollziehbare Begründung/Justification).

Diese drei Content-Checks sind Teil der Phase-5-Akzeptanzkriterien (siehe Abschnitt 4). Zimmermann bleibt als
Quelle für die Prozess-Leitplanken korrekt benannt, wird aber nicht mehr als Quelle für Content-Checks
missverstanden.

**Agenten-Korrektur:** Der Original-Plan listete `adr-specialist` (neuer Subagent, beobachtet PRs/Issues in
Nutzer-Repositories und draftet automatisch ADRs) und `concept-reviewer` als **neu zu schaffende** Deliverables.
Zwei Korrekturen:

- `concept-reviewer` **existiert bereits** als Agent (siehe `AGENTS.md`, `.claude/agents/concept-reviewer.md`)
  und ist **kein neues Deliverable** dieses Plans. Für den ADR-Review-Loop (5.5) wird der bestehende
  `concept-reviewer` genutzt bzw. um die oben definierten Content-Checks erweitert — kein neuer Agent nötig.
- `adr-specialist` bleibt ein reiner **Vorschlag ohne verifizierten Bedarf**. Er gehört inhaltlich eng mit eADR
  zusammen (PR-/Issue-Beobachtung in Nutzer-Repositories = derselbe Scope-Sprung wie in 5.4) und wird daher
  **nicht** für diese Phase 5 eingeplant, sondern — falls überhaupt benötigt — als Teil des eADR-Folge-Konzepts
  (5.4) geprüft.

---

## Offene Entscheidungspunkte für den Nutzer

Vor Implementierungsstart (Phase 1) braucht es ein explizites OK zu folgenden Punkten:

1. **SSOT-Zwei-Track-Modell (Abschnitt 1.1):** Bestätigung, dass `ArchitectureElement.parent_id` und
   `TraceLink(derives-from)` als zwei getrennte, parallel bestehende Hierarchie-SSOTs formalisiert werden
   (statt eines einheitlichen SSOT wie ursprünglich geplant).
2. **`decomposes` additiv statt Rename (Abschnitt 1.4):** Bestätigung, dass `parent-child` als Link-Typ bestehen
   bleibt und `decomposes` nur für neue Workspaces/Links als Default gesetzt wird — kein Daten-Rename bestehender
   TraceLinks/Baselines.
3. **Offene Frage `requirement_service.py:620` (Abschnitt 1.1):** Vor Phase 1 muss per Query geklärt werden, wie
   viele bestehende Workspaces/TraceLinks aktuell `parent-child` (aktiver Default) vs. einen überschriebenen Wert
   nutzen — Ergebnis beeinflusst, ob ein zusätzliches Backfill-Migrationsscript nötig ist.
4. **eADR-Scope-Abspaltung (Abschnitt 5.4):** Bestätigung, dass eADR (Code-Scanner, `eadr.resolve`,
   `adr-specialist`) **nicht** Teil dieses Plans/Phase 5 ist, sondern als eigenes Folge-Konzept separat
   aufgesetzt wird.
5. **Tri-Label-Scope auf 7 Typen (Abschnitt 1.3):** Bestätigung, dass nur `derives-from`, `satisfies`,
   `verifies`, `implements`, `refines`, `allocated-to`, `decomposes` ein Tri-Label bekommen und die übrigen 6
   `LinkType`-Werte auf rohe Enum-Anzeige zurückfallen.
6. **Minimal-Rigor ohne Auditor-Pflichtregeln (Abschnitt 2.2):** Bestätigung, dass `minimal`-Rigor-Workspaces
   bewusst **keine** Pflichtregel aus der Auditor-Matrix erhalten (0 Findings by design, nicht als Bug
   misszuverstehen).
7. **N3-Erststufe ohne pgvector (Abschnitt 3.2/4):** Bestätigung, dass N3 zunächst als Ranking bestehender
   Auditor-Findings gebaut wird und die volle pgvector-basierte Vektorsuche ein separater, zeitlich nicht fest
   eingeplanter Spike bleibt.
