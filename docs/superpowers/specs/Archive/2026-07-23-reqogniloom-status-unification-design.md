# ReqogniLoom — Status-Modell-Vereinheitlichung & MCP-Erweiterung (Design)

> Ausgangspunkt: `.local/VISION_REQOGNILOOM.md`. Die dortigen Home-Assistant-Beispiele
> sind reine Illustration des Vision-Autors und **nicht** Teil dieses Plans — dieser
> Plan ist produktgenerisch, keine HA-Spezifika.

Stakeholder: Daniel (Homelab-Poweruser, Single-Tenant-Betrieb, Docker-Container auf
einem internen Sandbox-Host). Kein Multi-User-Produktionsdruck — Migrationen dürfen big-bang
sein, YAGNI gilt aggressiv für Enterprise-Features (Pair-Review, Reviewer-Rollen-Listen).

---

## 1. Ist-Zustand (verifiziert gegen Code, Stand 2026-07-23)

Drei parallele, nicht verzahnte Status-Achsen existieren heute:

1. **`lifecycle_status`** (Enum `ACTIVE|OUTDATED|DEPRECATED|DELETED`, `persistence/models.py:126-138`) —
   Soft-Delete-Achse. Nur auf einem Teil der Modelle genutzt (Requirement, ADR,
   ArchitectureElement, GlossaryTerm setzen `deleted` beim Löschen). Risk, Issue,
   TestCase, ChangeRequest löschen heute **hart** (`.delete()`).
2. **`WorkflowItemState.current_state`** — Business-Prozess-Achse. Bereits für 11 von 13
   Artefakttypen verkabelt (Requirement, ArchitectureElement, TestCase, ADR, Risk, Issue,
   ChangeRequest, StakeholderNeed, GlossaryTerm, Diagram + implizit ICD), pro Workspace
   konfigurierbar (`WorkflowEngineDefinition`, `GlobalWorkflowDefinition`, ADR-06).
   **Nicht verkabelt:** CustomField, Workspace selbst.
3. **Denormalisierte `status`-Spiegel-Spalte** — Redundante Kopie von #2 für schnelle
   Queries, nur auf Requirement/TestCase/ADR/Risk/Issue/ChangeRequest vorhanden.

**Bekannter Bug:** `ChangeRequestService` (`application/change_request_service.py:295,314`) —
Docstring behauptet Soft-Delete ("status → rejected"), Code macht hartes
`.objects.filter(...).delete()`. Wird durch Phase 0 automatisch mit gelöst.

**AI-Derivation** (`application/ai_derivation_service.py`) ist heute vollständig
Draft/Accept-Pattern: LLM generiert, nichts wird persistiert, kein Write-Modus.

**Review/Approval**: kein dediziertes `review.*`-System — aber der bestehende
`workflow/`-Engine (inkl. `WorkflowHistoryEntry` für lückenlose Audit-Historie) deckt
draft→in_review→approved bereits ab, nur ohne MCP-Oberfläche.

**`workspace.get_context`** (`mcp_server/tools/cross_cutting.py:405-457`) existiert,
aber ohne `depth`, `include_outdated` oder `role` — liefert immer dieselbe schmale Form.

**PromptTemplate** ist Tenant-Singleton mit 3 festen Slots, keine Versionierung.

---

## 2. Leitprinzip

Ein Artefakt hat **eine** Wahrheit über seinen Zustand: den Workflow-State. "Outdated"
ist kein separates Feld mehr, sondern ein Meta-Flag auf dem jeweiligen State — global
mit Workspace-Override konfigurierbar, exakt nach dem bereits etablierten ADR-06-Muster.

---

## 3. Phase 0 — Status-Modell-Vereinheitlichung (Fundament)

### 3.1 Meta-Schema für Workflow-States

- `WorkflowEngineDefinition`-States bekommen ein neues Attribut:
  `is_outdated_equivalent: bool` (Default `false`). Kein separates
  `is_active_equivalent`-Flag nötig — "aktiv" = "nicht outdated".
- Global-Default pro bestehendem Preset (Workspace kann überschreiben, gleicher
  Mechanismus wie bestehende State/Transition/Rollen-Overrides):

  | Preset | Zählt als outdated |
  |---|---|
  | Requirement minimal (`draft`, `done`) | *(keiner)* |
  | Requirement standard/extended | `deprecated` |
  | ChangeRequest (`ccb_approval`) | `rejected` |
  | StakeholderNeed (`need_default`) | `deprecated` |
  | ArchitectureElement (`architecture_default`) | `deprecated` |
  | TestCase (`testcase_default`) | `Deprecated` |
  | ADR (`adr_default`) | *(keiner — Rejected und Superseded bleiben sichtbar, beide historisch wertvoll)* |
  | Risk (`risk_default`) | *(keiner — Closed bleibt gültiger Audit-Eintrag)* |
  | Issue (`issue_default`) | `Wontfix` *(Closed bleibt sichtbar — gelöst, weiter relevant)* |
  | Diagram / GlossaryTerm / ICD (`_design_lifecycle_transitions`-Familie) | `deprecated` |

### 3.2 Universeller Outdate/Reactivate-Mechanismus (Kern-Baustein)

- Jede `WorkflowEngineDefinition` bekommt automatisch — **presetunabhängig, nicht in
  `definition_store.py` pro Preset editiert** — zwei injizierte Transitionen:
  - `outdate`: von JEDEM State aus erreichbar → synthetischer `outdated`-State,
    merkt sich den Herkunfts-State (`WorkflowItemState.pre_outdate_state`, neues Feld).
  - `reactivate`: von `outdated` zurück zum gemerkten Herkunfts-State.
- Das ist exakt das, was `workspace.close/reactivate` heute bereits informell tut —
  jetzt formalisiert und auf alle 13 Artefakttypen ausgeweitet.
- `reason` (optionaler Parameter bei `.outdate()`) landet im bestehenden
  `WorkflowHistoryEntry`-Kommentarfeld — kein neues Feld.

### 3.3 CustomField + Workspace ans Workflow-Engine anschließen

- `CustomField`: neuer `item_type="CustomField"`, einfaches Preset
  (`active` ↔ `outdated`, kein komplexer Business-Prozess nötig).
- `Workspace`: neuer `item_type="Workspace"`, ersetzt das bisherige hand-gestrickte
  `is_active`/`closed_at`/`closed_by`.

### 3.4 "Goal" als workflow-getracktes Pseudo-Artefakt

- Neuer `item_type="WorkspaceGoal"`, 1:1 an Workspace gehängt.
- States: `draft` (System-intern, KI-optimiert, nie extern sichtbar) →
  `pending_review` → `approved` (öffentlich sichtbar) / `rejected` (zurück zu `draft`).
- Ein neu approvtes Goal transitioniert das alte automatisch in `outdated` —
  volle Historie, exakt wie jedes andere Artefakt. Kein Sonderfall im Code.
- Goal-Optimierung selbst ist eine spezialisierte Instanz von Phase 3 (Derive), nutzt
  dasselbe `mode=preview`/`write`-Muster mit eigenem Prompt-Template
  (`workspace.goal_optimizer`, versioniert via Phase 4).
- Auto-Trigger: bei neuen Requirements/Architecture-Änderungen/signifikanten
  Test-Case-Änderungen/periodisch, max. 1×/Stunde (Rate-Limit, Tokens sparen).
- **Ausblick, bewusst zurückgestellt:** Goals auf Architecture-Element-Ebene (gleiches
  Prinzip, granularer). Erst nach Etablierung des Workspace-Goals angehen.

### 3.5 `lifecycle_status` retiren

- Wird computed property, abgeleitet aus aktuellem `WorkflowItemState` +
  `is_outdated_equivalent`-Flag. Kein separat gespeicherter, drift-fähiger Wert mehr.
- **Migration: Big-Bang.** Bestehende `lifecycle_status="deleted"`-Datensätze werden in
  einem Rutsch auf den `outdated`-State ihres Presets transitioniert (Backfill-Skript
  pro Entity-Typ). Kein Dual-Write, keine Übergangsphase — Single-User-System ohne
  Produktionsdruck rechtfertigt das nicht.
- ChangeRequest-Bug löst sich dabei automatisch: hartes `.delete()` wird durch
  `outdate`-Transition ersetzt.

### 3.6 Denormalisierte Status-Spiegel-Spalten

- Bleiben unverändert als Performance-Cache, Schreibzugriff weiterhin ausschließlich
  über `_sync_status_mirror` (bereits heute so). Kein Nachrüsten auf Entities ohne
  Spiegel-Spalte (Architecture, GlossaryTerm, Diagram, StakeholderNeed) ohne konkreten
  Performance-Bedarf — YAGNI.

---

## 4. Phase 1 — MCP-CRUD-Vervollständigung

- **1.1** `GenericCrudToolGroup`: `.delete` → `.outdate(id, reason?)`, ruft
  `workflow.transition(to=outdated)` statt Service-Delete. Symmetrisches
  `.reactivate(id)` für alle Artefakttypen (nicht nur Workspace wie heute).
- **1.2** Eigene Tool-Groups (`requirement.*`, `architecture.*`, `test.*`, `needs.*`):
  `.outdate`/`.reactivate` als dünne Wrapper ergänzen.
- **1.3** Query/List-Endpunkt für generische Entities: `include_outdated=false` als
  Default (konsistent mit Context-Generator-Prinzip aus Phase 2), explizit
  `include_outdated=true` möglich.
- **1.4** Fehlende Entity-Zugänge:
  - ChangeRequest, Diagram: volles CRUD + Outdate (vollwertige Artefakte).
  - CustomField, Workspace-Preferences: nur Read + List (Konfigurationsmetadaten,
    Schutz vor versehentlicher Fehlkonfiguration durch einen Agenten).

---

## 5. Phase 2 — Context-Generatoren

- **2.1** `workspace.get_context` erweitert: `depth` (`summary`/`normal`/`full`),
  `include_outdated`, `role` (reines Label, siehe unten).
  Token-Budgets: 300/2000/unbegrenzt als **Default**, pro Workspace konfigurierbar
  (gleicher Override-Mechanismus wie Phase 0/State-Flags) — weiche Richtwerte
  (Truncation bei Überschreitung, kein harter Fehler).
- **2.2** `workspace.llm_system_prompt` (neu): generiert System-Prompt aus Live-Daten,
  `goal_approved` als erster Satz (Phase 0.4-Integration).
- **2.3** `role`-Parameter: reines Meta-Label im Prompt-Text ("Du bist als Tester
  unterwegs"), filtert **nicht**, welche Daten geliefert werden. Einfacher, kein
  überraschendes Verhalten.
- **2.4** `context.test_coverage(requirement_id, include_outdated?)`: Test Cases +
  Status + Lücken.
- **2.5** `context.change_impact(entity_id, entity_type, change_description,
  include_outdated?)`: betroffene Entitäten via Traces + Children.

---

## 6. Phase 3 — Derive-Modi (preview + write)

- Alle bestehenden 4 Derive-Tools + neue Paare (Architecture→Risk, Workspace→Glossary,
  Decision→ADR) bekommen `mode`-Parameter: `preview` (bestehend) oder `write` (neu).
- **`mode=write` erzeugt immer erst `draft`** — unabhängig von der Review-Policy.
  Der Übergang zu `in_review` ist ein separater, expliziter Schritt (Review-Submit),
  kein impliziter Automatismus. Mehr Kontrolle, ein Schritt mehr im Ablauf.
- **Auch bei Policy `auto`** läuft die Transition durch den vollen Workflow
  (`draft` → `approved` in einem automatisierten Schritt, protokolliert in
  `WorkflowHistoryEntry` mit Vermerk "auto-approved via AI-Derivation"). Keine
  Sonderfälle im Code, volle Nachvollziehbarkeit über alle Policies hinweg.
- Traces werden bei `write` automatisch erzeugt (z.B. `verifies`, `implements`).

---

## 7. Phase 4 — Prompt-Template-System

- `PromptTemplate`: von Tenant-Singleton (3 feste Slots) zu benanntem,
  **versioniertem** Multi-Template-Modell.
- **Versionierung:** neue Version = neue Zeile, alte wird via Workflow-Outdate markiert
  (nicht überschrieben) — konsistent mit Phase-0-Prinzip, volle Historie welches
  Wording wann welche Ableitung erzeugt hat.
- **Scope:** Global mit Workspace-Override (gleiches Muster wie State-Flags/Token-
  Budgets) — globale Standard-Templates, jeder Workspace kann bei Bedarf überschreiben.
- Neue MCP-Endpunkte: `prompt_template.list()`, `.create()`, `.update()` (`.get()`
  existiert bereits).
- Templates sind produktgenerisch (kein HA-Bezug) — konkrete Beispiel-Templates werden
  bei Implementierung anhand generischer Domänen (nicht Smart-Home-spezifisch) verfasst.

---

## 8. Phase 5 — Review-Endpunkte

**STATUS: IMPLEMENTED** (Commits: fff4ede1, 2d4bbdc0, fc5fc117, 2ed96917)

Dank Phase 0 ein dünner Wrapper über den bestehenden `WorkflowFacade`, kein neues System.

- **8.1** Neue MCP-Tool-Group `review.*`: `approve`, `reject`, `request_changes`,
  `list_pending` — 1:1 pro Artefakt, kein Batch (fürs Erste; später bei Bedarf
  nachrüstbar). ✅ Umgesetzt in `backend/mcp_server/tools/review.py`, registriert in
  `tool_registry.py` mit RBAC-Gating (approver+ Rollen).
- **8.2** Review-Policy pro Workspace: `ReviewPolicy`-Modell (Felder: `mode`,
  `min_confidence`) + `SettingsService.get_effective_review_policy()` /
  `.update_review_policy()`. REST-Endpunkt `GET/PUT /api/v1/workspaces/{workspace_id}/review-policy/`
  (admin-only). ✅ Umgesetzt.
  
**Explizit deferred (Phase 5, keine Breaking-Changes erforderlich):**

1. **`review_changes` Mode-Semantik:** Aktuell verhält sich `review_changes` identisch zu `auto`,
   weil keine der 6 aktuellen AI-Derive-Tools eine bereits genehmigte Artefakt modifiziert.
   Der Modus wird weiter unterstützt; sein Verhalten wird spezifiziert, wenn Future-Derive-Tools
   (z.B. Architecture-Element-Update, Requirement-Re-Decomposition) bestehende Inhalte ändern können.
   
2. **`review_high_risk` Confidence-Signal:** Der Schwellwert `min_confidence` ist aktuell ein Platzhalter,
   da kein LLM-Adapter in dieser Codebasis einen echten Confidence-Score bereitstellt.
   Mock-Provider liefert 1.0 (alle Änderungen als „high-risk"), Real-Provider (OpenAI, Anthropic, Ollama)
   liefern `None` (kein Signal). Sobald ein Provider echte Confidence-Scores exponiert, kann die Heuristik
   produktiv werden.

---

## 9. Phase 6 — Agenten-Definitionen

- **Scope:** Templates für **Downstream-Projekte**, die ReqogniLoom via MCP nutzen
  (z.B. eine künftige Home-Assistant-Integration oder jedes andere Projekt) — **nicht**
  Agenten für die Weiterentwicklung von ReqogniLoom selbst. Keine Überschneidung mit
  den bestehenden `se-*`-Rollen dieses Repos.
- **Tiefe:** Vollständige agent-meta-Integration — 5 Rollen
  (`requirements-architect`, `test-engineer`, `risk-analyst`, `change-manager`,
  `quality-auditor`) als echte, installierbare, sync-fähige agent-meta-YAML-Definitionen,
  jeweils mit System-Prompt-Template + MCP-Tool-Whitelist + Review-Profil,
  provider-agnostisch. Ablageort: `docs/agent-templates/` (oder äquivalent) im
  ReqogniLoom-Repo, exportierbar für Konsumenten-Projekte.

---

## 10. Explizit zurückgestellt (nicht Teil dieses Plans)

- Prio 7 (Subscribe/Events, Bridges) — "später", laut Vision-Roadmap.
- Goals auf Architecture-Element-Ebene (Ausblick in 3.4).
- `allowed_reviewers`, `require_pair_review`, Batch-Review-Operationen.
- Home-Assistant-spezifische Template-Inhalte — waren nur Beispiel des
  Vision-Autors, nicht Teil der generischen Umsetzung.

---

## 11. Reihenfolge / Abhängigkeiten

Phase 0 ist Fundament für alle folgenden Phasen (Outdate-Mechanismus, Goal-Modell,
Review-Basis). Phasen 1–2 bauen direkt darauf auf und sollten als nächstes umgesetzt
werden. Phasen 3–5 hängen lose voneinander ab (Review-Endpunkte vereinfachen sich
durch Phase 0, sind aber auch ohne Phase 3 sinnvoll nutzbar). Phase 6 ist unabhängig
und kann parallel oder zuletzt erfolgen. Jede Phase durchläuft ihren eigenen
Spec→Plan→Implementierungs-Zyklus vor Beginn.

---

*Design-Dokument, erstellt via superpowers:brainstorming. Nächster Schritt:
Spec-Self-Review, dann User-Freigabe, dann `writing-plans` für Phase 0.*
