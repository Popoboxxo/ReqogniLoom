# Interview-Management-Engine — Design

**Status:** Draft, pending user review
**Scope:** Spec 1 von 3 (Engine). Spec 2 (Hermes-IDE-Plugin-Integration) und Spec 3
(natives ReqogniLoom-Web-UI-Widget + Artefakte-Panel) folgen als eigene
Brainstorming-Zyklen, sobald diese Engine implementiert ist.

## 1. Zweck

Eine plattformübergreifende Interview-Management-Funktion für ReqogniLooms
eigene Agenten-Tooling-Landschaft — nicht für Endanwender des Produkts,
sondern für die Werkzeuge, mit denen ReqogniLoom-Artefakte über KI-Agenten
erzeugt, verbessert und angepasst werden.

**Zielclients (alle konsumieren dieselbe Engine):**
- Claude-Code-Plugin
- Opencode-Plugin
- Antigravity-Plugin
- Agent-Templates (jeder Host-Agent, der strukturierte Interviews führen soll)
- Hermes-IDE-Plugin (sinnvolle Integration, Spec 2)
- Natives ReqogniLoom-Web-UI-Widget (Spec 3)

**Bestätigter Kern-Mehrwert:** Konsistenz über Hosts hinweg. Heute führt z. B.
der `se-requirements`-Agent ein freies Dialog-Interview rein über seinen
System-Prompt — jeder Host formuliert potenziell anders, weil jeder sein
eigenes Prompt-Wording hat. Die Engine macht Konsistenz zur Konstruktion
statt zur Laufzeit-Hoffnung: eine Quelle, pro Host generiert.

**Scope der Artefakte:** alle Artefakt-Typen (Needs, Requirements,
Architektur, Risk, TestCase, ADR, Issue, Goal), **außer MainGoal** — passend
zum bestehenden MCP-Surface, das für MainGoal nur `main_goal.read`/
`main_goal.list_versions` kennt und nie Schreib-Tools hatte.

**Zweck des Interviews:** Artefakte **erzeugen, verbessern und anpassen** —
nicht nur erzeugen. Ein Interview kann auf ein bestehendes Artefakt treffen
(über Grounding) und es erweitern/korrigieren, statt zwingend ein Duplikat
anzulegen.

## 2. Architektur-Überblick

Fünf Bausteine:

1. **Interview-Protokoll-Konfiguration** — pro Rolle (Artefakt-Typ) definiert:
   Phasen-Reihenfolge, Pflichtfelder, Prompt-Fragmente pro Phase.
2. **`InterviewSession`** — Server-seitiger Fortschritts-Zustand, der
   Fortsetzbarkeit über Hosts hinweg trägt.
3. **`interview.*`-MCP-Toolgroup** — einziger Zugriffsweg auf 1+2, für alle
   Hosts identisch.
4. **KI-gestütztes Grounding** — findet verwandte/duplizierte bestehende
   Artefakte, optional LLM-/Embedding-gestützt, fail-open.
5. **Formalisierungs-Logik** — entscheidet pro Artefakt "neu erzeugen" vs.
   "bestehendes anpassen", validiert gegen Schema, ruft bestehende Services.

Dazu, außerhalb der Engine selbst, aber Teil dieses Specs: Host-Paketierung
(bestehende `dist/agent-skills/`-Pipeline) und ein CI-Freshness-Check, der die
in Commit `c49a503` aufgedeckte Drift-Lücke schließt.

## 3. Datenmodell

### 3.1 Interview-Protokoll-Konfiguration — Wiederverwendung von `PromptTemplate`

**Entscheidung:** kein neues Modell. `PromptTemplate` (`backend/persistence/models.py`,
MCP-Toolgroup `prompt_template.*`) hat bereits exakt die benötigte
3-Stufen-Fallback-Kette (Workspace-Override → Tenant-Global →
Factory-Default) und einen seit Phase 4 offenen, freien `name`-Namensraum.

Interview-Protokolle werden als `PromptTemplate`-Zeilen unter dem Namensraum
`interview.protocol.<artifact_type>` gespeichert (z. B.
`interview.protocol.requirement`), Inhalt als validiertes YAML mit Struktur:

```yaml
phases:
  - name: elicitation
    required_fields: [title, rationale, acceptance_criteria]
    prompt_fragment: "..."
  - name: approval
    prompt_fragment: "..."
  - name: formalization
    prompt_fragment: "..."
```

Factory-Defaults leben analog zu `PROMPT_TEMPLATE_DEFAULTS`
(`application.ai_derivation_service`) in einer neuen, parallelen
Konstante (z. B. `INTERVIEW_PROTOCOL_DEFAULTS`), damit die bestehende
Unterscheidung "nichts erzeugt implizit eine Zeile" (issue #276-Prinzip)
erhalten bleibt — ein Workspace bekommt nur dann eine eigene Override-Zeile,
wenn jemand sie explizit anlegt.

**Offene Frage für den Implementierungsplan:** YAML-Validierung beim
`prompt_template.create`/`.update`-Schreibpfad — heute nimmt der Tool
beliebigen String-Content an. Für `interview.protocol.*`-Namen sollte
Schema-Validierung vor dem Schreiben laufen, damit ein kaputtes YAML nicht
erst beim nächsten `interview.start` auffällt.

### 3.2 `InterviewSession` (neues Modell)

Tenant-scoped (`TenantScopedModel`, RLS wie jedes andere Modell hier).

| Feld | Typ | Zweck |
|---|---|---|
| `id` | UUID | PK |
| `workspace_id` | UUID | Scope |
| `artifact_type` | str | Rolle / welches Protokoll gilt |
| `status` | str | `in_progress` \| `completed` \| `abandoned` |
| `target_artifact_id` | UUID, nullable | Gesetzt, sobald Grounding ein Ziel zum Anpassen identifiziert (statt Neuanlage) |
| `collected_fields` | JSON | Bisher gesammelte Antworten |
| `grounding_snapshot` | JSON | Letzter Grounding-Treffer-Stand |
| `resulting_artifact_ids` | JSON (Liste) | Nach `formalize`: erzeugte + angepasste Artefakt-IDs |
| `started_by` | FK User/API-Key | Audit |
| `created_at`/`updated_at` | timestamp | — |

## 4. `interview.*`-MCP-Toolgroup

RBAC/Audit nach bestehendem `_WRITE_TOOL_PREFIXES`-Muster
(`mcp_server/tool_registry.py`).

- **`interview.start(artifact_type, workspace_id, seed_context?)`** — legt
  `InterviewSession` an, liefert `session_id` + Anfangszustand (Pflichtfelder
  aus dem Protokoll, erste Grounding-Treffer).
- **`interview.get_state(session_id)`** — liefert Phase, gesammelte Felder,
  offene Felder, Grounding-Snapshot. Zentraler Baustein für
  Host-übergreifende Fortsetzbarkeit: jeder Host liest denselben
  Server-Zustand statt sich auf eigenen Gesprächsverlauf zu verlassen.
- **`interview.answer(session_id, field, value)`** — schreibt eine Antwort
  fort, aktualisiert `collected_fields`.
- **`interview.grounding_context(session_id, workspace_id)`** — vorhandene
  Artefakte zum Scope, siehe Abschnitt 6.
- **`interview.formalize(session_id)`** — Validierung + Erzeugen/Anpassen der
  Artefakte, markiert Session `completed`. Siehe Abschnitt 5.
- **`interview.list(workspace_id, status?)`**, **`interview.get(session_id)`**
  — Audit/Abruf (read-only).

## 5. Formalisierungs-Logik

Kein neuer Schreibpfad — reine Orchestrierung bestehender Services
(`NeedsService`, `RequirementService`, `ArchitectureService`, `RiskService`,
...).

Pro betroffenem Artefakt-Feld-Satz:
1. `target_artifact_id` gesetzt (Grounding fand einen Treffer, User hat ihn
   bestätigt) → Update/Erweiterung über den passenden Service.
2. Kein `target_artifact_id` → Neuanlage über den passenden Service.
3. Validierung gegen das Rollen-Schema läuft vor dem Schreiben, über die
   bestehende `custom_field`/`attribute_schema`-Mechanik.
4. **Erneute Existenzprüfung zum Schreibzeitpunkt** (nicht nur beim
   Grounding) — siehe Fehlerbehandlung.

## 6. KI-gestütztes Grounding

Zweistufig, fail-open wie der Rest des Systems (z. B.
`llm_adapter.token_tracking`, `_apply_db_settings`):

1. **Strukturelle Vorfilterung** — immer verfügbar, keine KI nötig: über die
   bestehenden Read-Services (`needs.read`, `requirement.query`,
   `architecture.query`, ...), gescoped auf Workspace + Artifact-Type.
2. **Optionale semantische Anreicherung** — neue `llm_adapter`-Capability
   (Arbeitsname `suggest_related_artifacts`), verkabelt nach demselben Muster
   wie `check_consistency`/`decompose_requirement`
   (`CapabilityRouter` → `AsyncTaskDispatcher`/sync → Provider,
   `llm_adapter/router.py`, `llm_adapter/tasks.py`). Nutzt die vorhandene
   1536-dim-pgvector-Embedding-Spalte auf `TraceLink`
   (`REQ-L2-VS-004`) zur Ähnlichkeits-/Duplikat-Einschätzung.

Ohne konfigurierten Provider (Mock-Fallback) läuft Grounding rein
strukturell weiter — die KI-Schicht verfeinert nur, blockiert nie.

## 7. Host-Paketierung (bestehende Pipeline, kein neuer Mechanismus)

`dist/agent-skills/` ist die kanonische Quelle (fünf bestehende Skills:
`ccb-approval-and-baseline`, `risk-derivation`, `test-lifecycle`,
`traceability-audit`, `vmodell-decomposition`), aus der
`dist/opencode/build_opencode_package.py` und
`dist/plugins/antigravity/build_antigravity_plugin.py` Host-Pakete bauen;
Claude Code liest das SKILL.md-Format nativ aus
`dist/plugins/claude-code/`.

**Neu:** `dist/agent-skills/interview-management/SKILL.md`, ergänzt in der
`SKILL_NAMES`-Liste beider Build-Skripte. Der Skill-Text instruiert den Host-Agenten: Dialog
frei führen, aber jeden Fortschritt über `interview.*` spiegeln statt
eigenen State zu halten — das ist der praktische Konsistenz-Hebel.

## 8. CI-Freshness-Check (schließt die c49a503-Lücke)

Heute existiert kein CI-Job, der `dist/opencode/build_opencode_package.py`
oder `dist/plugins/antigravity/build_antigravity_plugin.py` automatisch
ausführt oder deren Output gegen den committeten Stand von `dist/`
validiert. Genau das führte zu Commit `c49a503`: der Versions-Bump auf
1.6.0-beta.3 vergaß, die Plugin-Builder erneut laufen zu lassen —
`plugin.json` blieb auf beta.2 stehen, bis es manuell entdeckt und gefixt
wurde. Ohne Gegenmaßnahme wiederholt sich das garantiert mit dem neuen
Interview-Skill.

**Neuer CI-Job:** Build-Skripte in einem temporären Ausgabeverzeichnis
ausführen, Diff gegen den committeten `dist/`-Stand (`dist/opencode/`,
`dist/plugins/claude-code/`, `dist/plugins/antigravity/`) bilden, bei
jeder Abweichung failen.

## 9. Fehlerbehandlung

- **Ziel-Artefakt wird während der Session gelöscht/outdated:**
  `interview.formalize` prüft Existenz zum Schreibzeitpunkt neu, nicht nur
  beim letzten Grounding-Aufruf — sonst entstehen Waisen-Updates auf ein
  nicht mehr existentes Ziel.
- **Zwei Sessions treffen gleichzeitig dasselbe Artefakt:** wiederverwendet
  die vorhandene Versions-/Optimistic-Concurrency-Prüfung der Artefakte
  (kein neuer Locking-Mechanismus in dieser Engine).
- **RBAC-Änderung zwischen `start` und `formalize`:** `formalize` ruft
  dieselben Services wie jeder andere Schreibpfad auf, die RBAC bei jedem
  Aufruf ohnehin prüfen — nichts Zusätzliches nötig.
- **Verwaiste Sessions** (gestartet, nie fortgesetzt): lazy
  Status-Übergang zu `abandoned` beim nächsten Lesezugriff nach Ablauf
  einer TTL, statt eines eigenen Scheduled-Jobs (YAGNI für v1).

## 10. Teststrategie

- **Backend:** `SET ROLE`-Pattern für RLS auf `InterviewSession`
  (etabliertes Muster, siehe `test_rls_token_usage_444.py`,
  `test_tenant_teardown_522.py`).
- **MCP:** bestehendes `test_tool_groups.py`-Muster (RBAC-Matrix,
  Audit-Trail-Assertions).
- **Build-Skripte:** `test_build_opencode_package.py`/
  `test_build_antigravity_plugin.py` um den neuen Skill-Namen erweitern.
- **CI-Freshness-Job:** Meta-Test — künstlichen Drift erzeugen (z. B.
  `plugin.json` manuell verändern), prüfen dass der Job das erkennt und
  failt.
- **Cross-Host-Konsistenz** braucht keinen eigenen Laufzeittest: alle drei
  Hosts lesen dieselbe SKILL.md-Datei aus derselben Quelle — die Garantie
  ist strukturell (eine Datei, drei Kopien), nicht etwas, das zur Laufzeit
  geprüft werden müsste.

## 11. Explizit außerhalb dieses Specs

- **MainGoal** — bleibt read-only, kein Interview-Ziel.
- **Hermes-IDE-Plugin-Integration** — Spec 2, eigener Brainstorming-Zyklus.
- **Natives ReqogniLoom-Web-UI-Widget** (ein-/ausblendbarer Chat +
  Artefakte-Panel) — Spec 3, eigener Brainstorming-Zyklus. Nutzt dieselbe
  `interview.*`-Engine, aber eigene UX-Entscheidungen (Platzierung, Layout).
- **Server-skriptetes, wortwörtliches Q&A** (Ansatz A aus dem Brainstorming)
  — verworfen: die Wortlaut-Garantie ist bei einem LLM-Host ohnehin nicht
  hart durchsetzbar, und der Bauaufwand ist am größten.
