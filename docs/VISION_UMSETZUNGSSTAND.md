# ReqogniLoom Vision — Umsetzungsstand (Stand: 2026-07-25)

## 1. Kern der Vision

Aus `.local/VISION_REQOGNILOOM.md`, Abschnitt 1 („Kern"):

**ReqogniLoom** ist ein AI-natives Requirements- und Test-Management-System, das Requirements Engineering und Implementierung nahtlos verwebt. Der zentrale Leitsatz: **Es gibt kein echtes Löschen.** Statt `DELETE` wird jede Entität via `outdate()` auf `status: outdated` gesetzt — die Daten bleiben vollständig erhalten, und Context-Generatoren steuern via `include_outdated: bool` (default: `false`), ob outdated-Elemente im Kontext auftauchen.

---

## 2. Übersicht der 7 Phasen + Umsetzungsstand

### Phase 0: Status-Modell-Vereinheitlichung (Fundament)

**Plan:** `docs/superpowers/plans/2026-07-23-phase0-status-unification.md`  
**Ziel:** Ersetze alle bespoken Soft-Delete-Mechanismen durch einen universellen, von `WorkflowEngine` gestützten `outdate()`/`reactivate()` Mechanismus; mache die Zuordnung „welche States gelten als outdated" konfigurierbar pro Preset und Workspace.

**Kern-Features:**
- `state_meta` JSON-Feld neben `states`/`transitions` in `WorkflowEngineDefinition.workflow_json`
- Universelle `outdate()`/`reactivate()` Funktionen in `workflow/services.py`
- Backfill bestehender `lifecycle_status="deleted"` Records via Management-Command
- 8 existierende Delete-Callsites umgeroutet auf `outdate()`

**Status:** ✅ **VOLLSTÄNDIG** (Commits: 1a362af..25d78b6, Fixes: 7752031e, 981872c5)  
**Verfügbar seit:** Merged in `feat/reqogniloom-vision-consolidation` (Merge-Commit: b24d7640)  
**Verifikation:** 301+ Tests passing; Whole-Branch-Review: 7 tote `lifecycle_status`-Filter identifiziert + gefixt, WorkflowItemState-Selbstheilung ergänzt.

---

### Phase 1: MCP-CRUD-Vervollständigung

**Plan:** `docs/superpowers/plans/2026-07-24-phase1-mcp-crud-completion.md`  
**Ziel:** Exponiere `.outdate`/`.reactivate` als MCP-Tools auf jedem Entity-Typ; mache `.list`/`.query` MCP-Endpunkte standardmäßig outdated-ausschließend; wire 4 fehlende Entity-Typen (ChangeRequest, Diagram, CustomField read-only, Workspace-Preferences read-only).

**Kern-Features:**
- GenericCrudToolGroup: `.outdate`, `.reactivate`, `.query` auf adr, risk, issue, glossary
- Requirement/Architecture/Test/Needs: `.outdate`/`.reactivate` + `include_outdated` forwarding
- ChangeRequest, Diagram: volles CRUD via neue Tool-Groups
- CustomField, Workspace-Preferences: Read-only Access
- RBAC-Gating: 24+ neue Write-Tool-Einträge in `_WRITE_TOOL_PREFIXES`

**Status:** ✅ **VOLLSTÄNDIG** (Commits: 697190fc, 7a89327c, 1fa1a502, 94c9862c, 88fe53d1, 5ed83c66, 0de00d37; Whole-Branch-Fix: 2d4ce3e5)  
**Verfügbar seit:** Merged in `feat/reqogniloom-vision-consolidation`  
**Verifikation:** Alle 7 Tasks clean reviewed; 2 Critical Findings (RBAC-gate, StakeholderNeed dead filters) in Whole-Branch-Review identifiziert + gefixt. Struktureller Guard-Test hinzugefügt zur Vermeidung.

---

### Phase 2: Context-Generatoren

**Plan:** `docs/superpowers/plans/2026-07-24-phase2-context-generators.md`  
**Ziel:** Erweitere `workspace.get_context` mit `depth` (summary/normal/full), `include_outdated`, `role` (label-only); werte Tokens-Budgets. Neue Tools: `workspace.llm_system_prompt`, `context.test_coverage`, `context.change_impact`.

**Kern-Features:**
- `workspace.get_context`: `depth` Parameter (summary: 300 Tokens, normal: 2000, full: unbegrenzt), `include_outdated` Default false, `role` Label-only
- `workspace.llm_system_prompt`: Generiert System-Prompt aus Live-Daten
- `context.test_coverage`: Test-Cases + Lücken per Requirement
- `context.change_impact`: LLM-unterstützte Ranking betroffener Entities
- Token-Budget-Konfiguration per Workspace (`ai_prompts["context_token_budgets"]`)

**Status:** ✅ **VOLLSTÄNDIG** (Commits: b46cb7d3, bf8a3e23, 308139d2, 415d7687, cdc3a8f7, 0d8e730a, d86c505d, d625509e, c95031f2, c88d5996)  
**Verfügbar seit:** Merged in `feat/reqogniloom-vision-consolidation`  
**Verifikation:** Alle 6 Tasks clean; Konsistenz-Check auf Outdated-Ausschlussmechanismus (Phase 0/1 Bug-Klasse NICHT wiederholt). 1 Important Cross-Task: VCRM-Report-Verhalten-Änderung identifiziert + gefixt mit explizitem `include_outdated=True` auf bestehenden Callsites.

---

### Phase 3: Derive-Modi (preview + write)

**Plan:** `docs/superpowers/plans/2026-07-24-phase3-derive-write-mode.md`  
**Ziel:** Füge `mode` Parameter (preview/write) zu allen 4 existierenden Derive-Tools; ergänze 3 neue Derive-Paare (Architecture→Risk, Workspace→Glossary, Decision→ADR). `write`-Modus: erstelle Draft, trace Link, optional auto-approve via Review-Policy.

**Kern-Features:**
- `mode=preview` (unverändert, Regression-Guard) vs. `mode=write` (neu: persistieren + Traces + optional Auto-Approve)
- `policy` Parameter: `manual` (default) oder `auto`
- `_write_derived_entity` Shared-Helper: Verfolgungslinkage + Auto-Approve-Logik
- 3 Neue Derive-Paare: Architecture→Risk, Workspace→Glossary, Decision→ADR (letzteres ohne Trace-Link, da keine Quell-Entity)
- Auto-Approve: Workflow-Transitions via `workflow.services.transition()`, max 5 Hops, `is_outdated_equivalent` Skip

**Status:** ✅ **VOLLSTÄNDIG** (Commits: 61c8fdc9, 67805035, d168a3e5, 43dbfe25, 96b7d8ee, 0814c87f + 2 Fix-Runden)  
**Verfügbar seit:** Merged in `feat/reqogniloom-vision-consolidation`  
**Verifikation:** Alle 5 Tasks clean; 1 Critical Cross-Task in Whole-Branch-Review: `policy="auto"` konnte Risks/ADRs in Terminal-States fahren (kein Phase-0 `is_outdated_equivalent` Flag) → Fix: neue `auto_approve_target` State-Metadaten (Phase-0-Muster) + Backfill-Migration.

---

### Phase 4: Prompt-Template-System

**Plan:** `docs/superpowers/plans/2026-07-24-phase4-prompt-templates.md`  
**Ziel:** Konvertiere `PromptTemplate` von Tenant-Singleton (3 feste Slots) zu benanntem, versioniertem, Multi-Template-Modell mit Global-Default + per-Workspace-Override. Wechsel alle 7 Derive-Methoden zur einheitlichen Lookup-Chain.

**Kern-Features:**
- Neues Modell: `name` (open-ended, nicht fixed Enum), `content`, `version`, `is_active` Bool, `workspace_id` NULL=global
- Lookup-Fallback: workspace-override → tenant-global → factory-default
- 7 Derive-Methoden retrofitted: 3 alte Slot-Methoden + 4 neue Phase-3-Methoden nutzen `_get_template_content()`
- MCP-Tools: `prompt_template.list()`, `.create()`, `.update()` (`.get()` existiert bereits)
- REST Backward-Kompatibilität: alte 3-Slot-Endpunkte via dünner Kompatibilitäts-Layer (Tenant-Global-Rows)

**Status:** ✅ **VOLLSTÄNDIG** (Commits: 2550f95a, a9995b8b, 31209b78, 155daf07, aaa85cb2 + Whole-Branch-Fix 92d6b6f8)  
**Verfügbar seit:** Merged in `feat/reqogniloom-vision-consolidation` (ggf. Bestätigung noch erforderlich für Consolidation-→-Main später)  
**Verifikation:** Alle 4 Tasks clean; 1 Important Cross-Task in Whole-Branch-Review: MCP `.get()` vs. `AiDerivationService._get_template_content` uneinig über Factory-Default-Registry (3-entry vs. 7-entry) → Fix: Unified Registry in AiDerivationService, MCP importiert davon. Plus 4 Minor Findings (Fehlerbehandlung, Docstring, Test-Name, Kommentar) alle behoben.

---

### Phase 5: Review-Endpunkte

**Plan:** `docs/superpowers/plans/2026-07-25-phase5-review-endpoints.md`  
**Ziel:** Exponiere `review.*` MCP-Tool-Group (approve/reject/request_changes/list_pending) als dünner Wrapper über bestehenden WorkflowFacade. Introduziere per-Workspace `ReviewPolicy` (`mode` + `min_confidence`) die Auto-Approve-Gates steuert.

**Implementierte Kern-Features:**
- `ReviewPolicy` Modell: Tenant-Global + Workspace-Override-Scoping (ohne Versionierung wie PromptTemplate)
- Modes: `auto` (Status quo), `review_changes`, `review_all`, `review_high_risk`
- Shared `workflow.services.is_approval_gate()` Helper (extrahiert aus Phase-3-Code)
- MCP `ReviewToolGroup`: `review.list_pending`, `review.approve`, `review.reject`, `review.request_changes` (implementiert in `backend/mcp_server/tools/review.py`)
- Integration in `AiDerivationService._auto_approve()`: Policy-aware Gating
- RBAC-Gating: alle 3 Write-Tools in `_WRITE_TOOL_PREFIXES`

**Status:** ✅ **VOLLSTÄNDIG** (Datei: `backend/mcp_server/tools/review.py`; Merged in `feat/reqogniloom-vision-consolidation`)  
**Verifikation:** ReviewToolGroup implementiert als dünner Wrapper über WorkflowFacade; alle 4 MCP-Tools vorhanden + registriert

---

### Phase 6: Agenten-Templates für Downstream-Projekte

**Plan:** `docs/superpowers/plans/2026-07-25-phase6-agent-templates.md`  
**Ziel:** Publikation von 5 provider-agnostischen, agent-meta-kompatiblen Agent-Template-Dateien + Bootstrap-Snippet unter `docs/agent-templates/`.

**Implementierte Rollen (alle vollständig ausgearbeitet):**
1. **requirements-architect.md** — Erfasst Stakeholder Needs, leitet Systemanforderungen ab (L0–L3); Review-Profile: `review_changes`
2. **test-engineer.md** — Erstellt Test-Cases, dokumentiert Testergebnisse; Review-Profile: `auto`
3. **risk-analyst.md** — Identifiziert Risiken, verknüpft mit Requirements/Architecture; Review-Profile: `review_high_risk`
4. **change-manager.md** — Verwaltet ADRs, Issues, genehmigt Workflow-Übergänge; Review-Profile: `review_high_risk`
5. **quality-auditor.md** — Read-Only Audit auf Traceability/Coverage; Review-Profile: `auto` (keine Write-Tools)

**Zusätzliche Artefakte:**
- `README.md` — Übersicht aller Rollen + Installation/Scope
- `BOOTSTRAP.md` — Snippet für Projekt-Integration in CLAUDE.md/AGENTS.md
- `docs/agent-templates/hooks/review-policy-gate.md` + `.sh` — Optional Claude-Code Review-Policy-Hook

Jede Rolle: YAML-Frontmatter (name, version, compatible_with, tools) + Prose System-Prompt + Domain-Knowledge + Workflow-Sections.

**Status:** ✅ **VOLLSTÄNDIG** (Dateien: `docs/agent-templates/*.md` + README.md + BOOTSTRAP.md; Merged in `feat/reqogniloom-vision-consolidation`)  
**Verifikation:** Alle 5 Templates mit vollständigen YAML-Frontmattern + ausführlicher Dokumentation; Toolwhitelists gegen MCP-Registry verifiziert

---

## 3. Kompakte Status-Tabelle

| Phase | Kern-Feature | Status | Referenz |
|-------|---|---|---|
| **0** | Universelle Outdate/Reactivate + State-Meta | ✅ Vollständig | `backend/workflow/services.py`, `backend/workflow/lifecycle_manager.py` |
| **1** | MCP CRUD (outdate/reactivate/query + 4 Entities) | ✅ Vollständig | `backend/mcp_server/tools/generic.py`, `requirements.py`, `architecture.py`, `tests.py`, `needs.py` |
| **2** | Context-Generatoren (depth/budget/llm_system_prompt/coverage/change_impact) | ✅ Vollständig | `backend/mcp_server/tools/cross_cutting.py` |
| **3** | Derive Write-Modus (4 Bestehende + 3 Neue Paare) | ✅ Vollständig | `backend/application/ai_derivation_service.py`, `backend/mcp_server/tools/ai_derivation.py` |
| **4** | Prompt-Template System (Versionierung/Multi-Template) | ✅ Vollständig | `backend/persistence/models.py` (PromptTemplate), `backend/application/ai_derivation_service.py` |
| **5** | Review-Endpunkte + ReviewPolicy Gating | ✅ Vollständig | `backend/mcp_server/tools/review.py`, `backend/persistence/models.py` (ReviewPolicy) |
| **6** | Agent-Templates (5 Rollen) für Downstream | ✅ Vollständig | `docs/agent-templates/*.md`, `README.md`, `BOOTSTRAP.md` |

---

## 4. Anmerkungen zu Implementierungslücken & Abhängigkeiten

### Implementiert (Phasen 0–6) — ALLE PHASEN VOLLSTÄNDIG
- **Outdate statt Delete:** Systemweit konsistent; alle 8 Delete-Callsites + 4 fehlende Entities umgeroutet
- **Context-Filtering:** `include_outdated` durchgehend auf Query/List-Endpunkten; Outdated-Ausschlussmechanismus (Status-Mirror vs. `outdated_item_ids()` je Entity-Typ) konsistent
- **Derive Write-Modus:** Alle 7 Derive-Tools mit Preview/Write + Mode-Parametern
- **Auto-Approve-Logik:** Phase-3-fix ergänzte `auto_approve_target` State-Meta; Phase-5 ReviewPolicy-Gating integriert
- **Prompt-Template-Lookup:** Einheitliche Fallback-Chain; 7 Derive-Methoden unified
- **REST Backward-Compat:** Alte 3-Slot-Endpunkte funktionieren noch (via Compat-Layer)
- **Review-Endpunkte:** `review.list_pending`, `.approve`, `.reject`, `.request_changes` MCP-Tools + ReviewPolicy Modell
- **Agent-Templates:** 5 vollständig ausgearbeitete Downstream-Rollen mit YAML-Frontmattern + Bootstrap-Integration

### Bekannte Gaps (dokumentiert, nicht blocking)
- **Phase 0:** Pre-existing GlossaryTerm-Rows ohne WorkflowItemState; `backfill_workflow_item_states` deckt noch nicht GlossaryTerm (wird via Backfill-Command gelöst, läuft aber nicht automatisch)
- **Phase 2:** Confidence-Signale existieren nicht in `llm_adapter/`; `review_high_risk` Mode nutzt Minimal-Heuristik (Mock → 1.0, Real-Provider → None/"below-threshold")
- **Phase 3:** `review_changes` Mode verhält sich identisch zu `auto` (keine der 6 Derive-Tools modifiziert existierende Artifacts) — ist Platzhalter für Future-Tools

---

## 5. Verweisstruktur

| Dokument | Zweck |
|---|---|
| `.local/VISION_REQOGNILOOM.md` | Original-Vision (Abschnitt 10: Roadmap mit Prio 1–6) |
| `docs/superpowers/specs/2026-07-23-reqogniloom-status-unification-design.md` | Design-Dokument (7 Phasen abgeleitet) |
| `docs/superpowers/plans/2026-07-23-phase0-*.md` … `2026-07-25-phase6-*.md` | Implementierungs-Pläne (7 Dateien) |
| `.superpowers/sdd/progress*.md` | Ledger pro Phase (Commits, Findings, Verifikation) |
| `docs/CODEBASE_OVERVIEW.md` | Code-API nach Umsetzung (Domäne des documenter-Agents) |

---

**Erstellt am:** 2026-07-25 (Korrigiert: 2026-07-25)  
**Branch:** `feat/reqogniloom-vision-consolidation`  
**Abschluss:** ✅ **ALLE 7 PHASEN VOLLSTÄNDIG** — Phases 0–6 implementiert, merged + verified in Consolidation-Branch
