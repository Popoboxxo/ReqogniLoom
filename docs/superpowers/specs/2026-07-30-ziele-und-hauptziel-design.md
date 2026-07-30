# ReqogniLoom — Ziele & MainGoal (Design)

Neues Artefakt "Ziele" (`Goal`) pro Workspace, plus ein per LLM aggregiertes "Haupt-Ziel"
(`MainGoal`), das versioniert und explizit vom User freigegeben werden muss, bevor es
gültig wird. Beide unterliegen dem bestehenden generischen WorkflowEngine — keine
Sonderschienen, exakt nach dem etablierten Muster von Risk/Adr/Issue.

Beide Modelle **pilotieren zusätzlich ein echtes, lückenloses Versionierungsmuster**
(unveränderliche Zeile pro Änderung), das im übrigen Codebase heute nicht existiert
(Abschnitt 1) — als konkreter Vorzeige-Fix für den systemweiten Befund aus Issue #213.

Nebenscope (Custom-LLM-Endpoint für Anthropic/OpenAI-Provider) wurde als eigenständiger Bug
ausgelagert: [Issue #212](https://github.com/Popoboxxo/ReqogniLoom/issues/212). Nicht Teil
dieses Designs.

---

## 1. Ist-Zustand (verifiziert gegen Code, Stand 2026-07-30)

- **Artefakt-Muster (REQ-L2-TE-020):** Jeder traceability-fähige Artefakttyp
  (`Requirement`, `StakeholderNeed`, `Adr`, `Risk`, `Issue`) hat ein Pflichtfeld
  `artifact = models.OneToOneField("persistence.Artifact", on_delete=models.CASCADE, ...)`.
  Das ist der einzige Mechanismus, über den ein Objekt als Knoten im TraceLink-Graph, in
  `artifact.search` und in `artifact.get_tree` erscheint (TraceLinks sind reine
  Artifact-zu-Artifact-Kanten). Gilt unabhängig davon, ob das Modell `TenantScopedModel`
  (`Requirement`, `StakeholderNeed`) oder ein einfaches `models.Model` (`Adr`, `Risk`,
  `Issue`) ist. Ersetzt einen früheren "UUID-Identity-Hack"
  (`Artifact.id == Issue.id`) ohne referenzielle Integrität.
- **WorkflowEngine-Muster:** `WorkflowItemState` (Tabelle `we_item_state`) verkabelt
  Artefakttypen generisch mit konfigurierbaren States/Transitions
  (`WorkflowEngineDefinition`, Workspace-Overrides, ADR-06). Service-Referenz:
  `application/risk_service.py`. Keine Änderung am Engine-Core nötig, um einen neuen
  Typ anzuschließen.
- **Systemweiter Versionierungsbefund (Issue #213, high/data-model — während dieser
  Session entdeckt, unabhängig von diesem Feature, hier nur als Kontext für die
  Design-Entscheidung in Abschnitt 2):**
  - `AuditableModel.version` (`persistence/models.py:319`) ist ein reiner
    optimistischer Concurrency-Zähler ("started at 1, incremented by writers"),
    **keine Historie**. Überschriebene Feldwerte sind für immer weg.
  - `BaselineSnapshot`/`BaselineDeltaIndexEntry` (`baseline/models.py`) ist der einzige
    echte Content-Snapshot-Mechanismus — aber manuell getriggert, Multi-Artefakt,
    Zeitpunkt-basiert. Edits zwischen zwei Baselines sind unwiederbringlich verloren.
  - Die bereits gebaute `VersionPanel`-UI (`frontend/.../ArtifactInspector/VersionPanel.tsx`)
    ruft für alle 10 Artefaktarten `GET /api/v1/<kind>/<id>/versions/` auf. Für 7 von 10
    Arten (`Requirement`, `StakeholderNeed`, `ArchitectureElement`, `TestCase`, `Adr`,
    `Risk`, `Issue`) liefert der Endpoint laut Docstring **"only the current version
    (single-row model)"** — ein Fake-Ein-Zeiler `"Current (v{n})"`
    (`application/artifact_diff_service.py:338-346, 383-413`). Switch/Compare in der UI
    haben für diese 7 Arten nie einen zweiten Eintrag zum Vergleichen. Nur `diagram` und
    `glossary` haben echte Historie-Tabellen dahinter.
  - **Konsequenz für dieses Design:** `PromptTemplate` (`persistence/models.py:1638`)
    ist bislang der einzige echte Gegenentwurf — Immutable-Row-per-Version
    (`version`-Feld der Basis zweckentfremdet), `is_active`-Flag markiert die aktuelle
    Version. **Kein** Artifact-/TraceLink-Bezug — PromptTemplate ist eine
    Settings-Entität, kein Engineering-Artefakt, daher kein direktes Vorbild für die
    Artifact-Seite.
- **PromptTemplate-Lücke (bestätigt, betrifft diese Arbeit direkt):** Das Django-Modell
  und `PROMPT_TEMPLATE_DEFAULTS` (`persistence/models.py:1631`) sind bereits
  namens-offen (`name: CharField`, kein Enum). Der komplette REST-Stack darüber ist
  aber hart auf genau drei Slots verdrahtet:
  - `PromptTemplateSerializer` (`rest_api/settings_views.py:156`) — drei feste
    `CharField`s (`need_to_sysreq`, `sysreq_to_arch_assign`,
    `sysreq_decompose_next_level`).
  - `PromptTemplateView` (`rest_api/settings_views.py:180`) — liest/schreibt exakt
    diese drei Original-Slot-Namen.
  - Frontend `PromptSlot`-Union-Type, `PROMPT_SLOTS`-Array, `PromptTemplate`/
    `PromptTemplateUpdate`-Interfaces, `SLOT_LABELS`, `EMPTY_VALUES`
    (`frontend/src/api/prompt-templates.ts`, `.../PromptTemplateSection.tsx`) — exakt
    dieselben drei Namen, hart codiert.

  Diese Arbeit braucht einen vierten Slot (`goal_aggregate`). Statt das gesamte
  PromptTemplate-System auf ein generisches Name-Keyed-Schema zu refaktorieren (zu
  große, unabhängige Änderung — YAGNI), wird der vierte Slot nach demselben
  bestehenden Muster ergänzt: ein weiteres festes Feld an allen vier Stellen
  (Serializer, View, Frontend-Type, Frontend-Labels). Konsistent mit dem Ist-Zustand,
  keine neue Sonderschiene.

- **LLM-Prompt-Injection in andere Flows:** Bestehende AI-Derivation-Services
  (`application/ai_derivation_service.py` u.a.) laden Prompt-Templates über den
  Namen aus `PromptTemplate`. Für die MainGoal-Injection in andere System-Prompts
  reicht das bestehende Lade-Muster.

---

## 2. Datenmodell

**Design-Entscheidung (final, User-Vorgabe):** `Goal` und `MainGoal` erproben beide das
echte Immutable-Row-per-Version-Muster — jede inhaltliche Änderung erzeugt eine neue,
unveränderliche Zeile statt einer In-Place-Mutation. Kein Sonderfall gegenüber
`PromptTemplate` (dasselbe Zeilen-Muster), aber **neue Kombination**: zusätzlich bekommt
**jede Version-Zeile ihren eigenen dedizierten `Artifact`** (OneToOne, REQ-L2-TE-020), was
`PromptTemplate` nicht hat, weil es keine TraceLink-Teilnahme braucht. Begründung des
Users für den eigenen Artifact pro Zeile: "nachvollziehbarer" als eine geteilte
Artifact-Identität über mutierende Versionen hinweg.

### 2.1 `Goal`

Anders als ursprünglich entworfen (in-place editierbar wie Risk/Issue) bekommt `Goal` jetzt
dasselbe Versionierungsmuster wie `MainGoal`. Da es — anders als `MainGoal`, wo
`workspace_id` allein als stabiler Gruppierungsschlüssel reicht (ein Haupt-Ziel pro
Workspace) — **mehrere unabhängige Goals pro Workspace** gibt, braucht `Goal` ein
zusätzliches stabiles `lineage_id`-Feld, das alle Versionen desselben logischen Goals
verbindet (die Zeilen-PK identifiziert nur die jeweilige Revision).

```python
class Goal(TenantScopedModel):
    lineage_id = models.UUIDField(
        default=uuid.uuid4, db_index=True,
        help_text="Stabile Identität über alle Versionen dieses Goals hinweg. "
                   "PK identifiziert nur diese eine unveränderliche Revision.",
    )
    sequence_number = models.PositiveIntegerField(
        help_text="Fortlaufende Versionsnummer innerhalb der lineage_id, startet bei 1.",
    )
    artifact = models.OneToOneField(
        "persistence.Artifact", on_delete=models.CASCADE, related_name="goal",
        help_text="REQ-L2-TE-020: backing Artifact für TraceLink-Support. "
                   "Ein dedizierter Artifact pro Version-Zeile.",
    )
    workspace_id = models.UUIDField(db_index=True)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    # `version` (optimistic concurrency) von TenantScopedModel geerbt, hier ungenutzt
    # für Versionierung (siehe sequence_number) — bleibt Standard-Locking auf der Zeile.
```

### 2.2 `MainGoal`

```python
class MainGoal(TenantScopedModel):
    sequence_number = models.PositiveIntegerField(
        help_text="Fortlaufende Versionsnummer innerhalb des Workspace, startet bei 1.",
    )
    artifact = models.OneToOneField(
        "persistence.Artifact", on_delete=models.CASCADE, related_name="main_goal",
        help_text="REQ-L2-TE-020: backing Artifact für TraceLink-Support. "
                   "Ein dedizierter Artifact pro Version-Zeile.",
    )
    workspace_id = models.UUIDField(db_index=True)
    full_text = models.TextField()
    compact_text = models.TextField(
        help_text="KI-optimierte Kurzform, im selben LLM-Schritt wie full_text generiert, "
                   "unabhängig manuell überschreibbar."
    )
    source = models.CharField(
        max_length=16, choices=[("ai", "AI-generated"), ("manual", "Manual")],
    )
    # `version` (optimistic concurrency) von TenantScopedModel geerbt, hier ungenutzt
    # für Versionierung (siehe sequence_number).
```

Keine `lineage_id` nötig — `workspace_id` ist bereits der stabile Gruppierungsschlüssel
(genau ein MainGoal-"Strang" pro Workspace).

**Akzeptierter Trade-off (bewusst, gilt jetzt für BEIDE Modelle, hier explizit
dokumentiert statt stillschweigend übergangen):** TraceLinks, die auf eine bestimmte
`Goal`- oder `MainGoal`-Version zeigen, sind fest an diese eine eingefrorene Zeile
gebunden. Wird eine neue Version erzeugt und freigegeben, zeigt der TraceLink weiterhin
auf die alte (jetzt nicht mehr gültige) Version — semantisch "veraltet"/verwaist, ohne
automatische Migration auf die neue Version. Dies ist bewusst in Kauf genommen, nicht Teil
dieses Designs zu lösen (z. B. kein automatisches TraceLink-Umhängen bei neuer Freigabe).

### 2.3 Gültige Version

Kein separates Feld "current". Zwei verschiedene Blickwinkel, beide für `Goal` (pro
`lineage_id`) und `MainGoal` (pro `workspace_id`) identisch definiert:

- **"Neueste Version"** (Standard-Anzeige beim Bearbeiten): die Zeile mit dem höchsten
  `sequence_number` in der Gruppe — unabhängig vom Workflow-State.
- **"Gültige/wirksame Version"** (wird für Haupt-Ziel-Aggregation / Prompt-Injection /
  Freigabe-Anzeige verwendet): die Zeile mit `WorkflowItemState.current_state ==
  Freigegeben`, die zuletzt in diesen State transitioniert ist, innerhalb der Gruppe.
  Existiert keine solche Zeile, gibt es keine gültige Version (nicht "vorherige Version",
  sondern "keine gesetzt").

Jede inhaltliche Mutation (Goal: `title`/`description`; MainGoal: `full_text`/
`compact_text`) läuft ausschließlich über eine einzige Mutation
`<Model>Service.create_version(...)`, die eine neue Zeile mit neuem `sequence_number`,
neuem `Artifact`, Start-State `Entwurf` anlegt. Es gibt keinen In-Place-Update-Pfad für
diese Felder auf einer bestehenden Zeile. Editiert man ein bereits `Freigegeben`-Goal,
bleibt die alte Zeile mit ihrem eingefrorenen `Freigegeben`-Historieneintrag stehen; die
neue Zeile startet bei `Entwurf` und zählt so lange **nicht** als "gültige Version" (z. B.
nicht als Input für die MainGoal-Aggregation), bis sie ihrerseits freigegeben wird — exakt
symmetrisch zum bereits vereinbarten MainGoal-Freigabe-Reset-Verhalten.

---

## 3. Workflow-Integration

Beide Modelle werden genau wie `Risk`/`Adr` unabhängig voneinander an die generische
WorkflowEngine angeschlossen (`WorkflowItemState`, eigener `WorkflowEngineDefinition`-
Preset je Typ, Workspace-override-fähig). Keine Änderung am Engine-Core. Der
Workflow-State hängt an der jeweiligen **Zeile** (also an einer bestimmten Version), nicht
an der `lineage_id`/`workspace_id`-Gruppe — jede neue Version-Zeile bekommt ihren eigenen,
frischen `WorkflowItemState`, startend bei `Entwurf`.

**Goal-Workflow (Preset `goal_default`):**

| State | Bedeutung |
|---|---|
| `Entwurf` | Initialzustand einer Version, bearbeitbar nur im Sinne von "kann freigegeben werden" (Inhalt selbst ist unveränderlich, siehe 2.3) |
| `Freigegeben` | Diese Version zählt als Input für Haupt-Ziel-Aggregation |
| `Archiviert` | Nicht mehr aktiv, nicht Teil der Aggregation |

Transitionen: `Entwurf → Freigegeben`, `Freigegeben → Archiviert`,
Rück-Transitionen `Freigegeben → Entwurf`, `Archiviert → Entwurf`.

Nur Goal-Versionen im State `Freigegeben` (die jeweils gültige Version je `lineage_id`,
siehe 2.3) fließen als Input in die MainGoal-Generierung ein.

**MainGoal-Workflow (Preset `main_goal_default`):** dieselben drei States/Transitionen,
unabhängig konfigurierbar vom Goal-Preset (separater Preset-Name, kein geteiltes
Preset-Objekt).

---

## 4. MainGoal-Generierung & Freigabe-Flow

1. **Trigger:** manuell (Button/REST/MCP-Call). Design lässt Raum für einen späteren
   automatischen Trigger (z. B. bei jeder neuen Goal-Freigabe), aber das ist explizit
   nicht Teil dieser Iteration — kein Scaffolding dafür jetzt.
2. **Generierung:** `MainGoalService.generate_ai(...)` sammelt alle Goals, deren gültige
   Version (2.3) `current_state == Freigegeben` ist, im Workspace, baut den Prompt aus dem
   `goal_aggregate`-Template (Abschnitt 6), ruft den konfigurierten LLM-Provider
   (bestehende `llm_adapter`-Abstraktion, ADR-02) in einem Schritt für `full_text` und
   `compact_text` auf, und persistiert über `create_version(source="ai", ...)`.
3. **Manuelles Setzen:** `MainGoalService.create_manual(...)` — gleicher
   `create_version`-Pfad, `source="manual"`, User liefert `full_text`/`compact_text`
   direkt.
4. **Freigabe:** Jede neue Version startet im State `Entwurf` (unabhängig von `source`).
   Sie wird erst durch eine explizite Workflow-Transition `Entwurf → Freigegeben`
   (regulärer WorkflowEngine-Transition-Call, kein Sonderpfad) zur gültigen Version.
5. **Bis zur Freigabe** bleibt die vorherige gültige Version (falls vorhanden) weiterhin
   gültig — oder es gibt keine gültige MainGoal-Version, wenn nie eine freigegeben wurde.
6. **Injection in andere Prompts:** Andere AI-Derivation-Flows können die aktuell gültige
   MainGoal-Version (`compact_text` bevorzugt, `full_text` als Fallback) über denselben
   Service-Lookup einbinden, den auch REST/MCP für den Lesezugriff nutzen — kein zweiter
   Code-Pfad.

---

## 5. Prompt-Template-Integration

Neuer vierter Slot `goal_aggregate`, ergänzt nach dem bestehenden hart-codierten
Drei-Slot-Muster (Abschnitt 1):

- `PROMPT_TEMPLATE_DEFAULTS["goal_aggregate"] = DEFAULT_GOAL_AGGREGATE` in
  `persistence/models.py`.
- `PromptTemplateSerializer`: neues `CharField goal_aggregate`.
- `PromptTemplateView`: liest/schreibt den vierten Slot-Namen mit.
- Frontend: `PromptSlot`-Union, `PROMPT_SLOTS`, `PromptTemplate`/`PromptTemplateUpdate`-
  Interfaces, `SLOT_LABELS`, `EMPTY_VALUES` je um `goal_aggregate` erweitert.

Damit ist das MainGoal-AI-Prompt-Template im bestehenden Workspace-AI-Prompt-Template-
Bereich sichtbar und editierbar — keine neue UI-Sektion nötig.

---

## 6. REST / MCP / UI

**REST** (`/api/v1/`): `GoalViewSet` (CRUD-artig — `create`/`list`/`retrieve` +
Workflow-Transition-Endpoint; kein `update`, stattdessen `create_version`-Action, die
intern eine neue Zeile anlegt — Response sieht für den Client wie ein Update aus, ist
serverseitig aber ein Insert), `MainGoalViewSet` (Read + `create` [manuell] + `generate`
[AI] + Workflow-Transition-Endpoint für Freigabe, ebenfalls kein In-Place-`update`).

**Echter `/versions/`-Endpoint (statt Fake-Stub, siehe Abschnitt 1):** Beide ViewSets
bekommen eine `versions`-Action, die **alle** Zeilen einer `lineage_id` (Goal) bzw.
eines `workspace_id`-Strangs (MainGoal) zurückgibt, chronologisch nach
`sequence_number` — analog zu `list_versions_for_diagram`/
`list_versions_for_glossary_term` (den einzigen zwei bereits echten Implementierungen),
nicht analog zu den Fake-Single-Entry-Stubs der übrigen 7 Typen. Frontend: `goal` und
`mainGoal` werden in `VERSION_SUPPORTED_KINDS`/`VERSIONS_FETCHERS`
(`ArtifactInspector/VersionPanel.tsx`) eingetragen — die bereits gebaute
Switch/Compare-UI wird dadurch für diese beiden Typen erstmals echt funktional
nutzbar, ohne Änderung an der UI-Komponente selbst.

**MCP:** neue Tool-Gruppe (analog zu `risk.*`/`adr.*`):
`goal.read`, `goal.create`, `goal.create_version`, `goal.list_versions`, `goal.delete`,
`main_goal.read` (liefert aktuell gültige Version), `main_goal.generate`,
`main_goal.create_manual`, `main_goal.list_versions`, `main_goal.approve` (Workflow-
Transition-Wrapper).

**UI:** Neuer "Ziele"-Bereich pro Workspace (Liste + Detail für Goals, analog zu
bestehenden Artefakt-Listen/Detail-Views), MainGoal-Karte mit aktueller gültiger Version,
echte Versions-Historie über `VersionPanel` (s. o.), "Generieren"-Button
(deaktiviert/Fehlermeldung wenn AI-Toggle aus), Freigabe-Button (Workflow-Transition-UI,
analog zu bestehenden Approval-Buttons).

**AI-Toggle-Verhalten:** Generierungs-Einstiegspunkte (Button, REST `generate`-Endpoint,
MCP `main_goal.generate`) bleiben sichtbar/aufrufbar, liefern aber bei deaktiviertem
Workspace-AI-Toggle einen expliziten Fehler ("AI disabled for this workspace") statt sich
zu verstecken.

**Baseline-Anbindung:** `BaselineDeltaIndexEntry.item_id` referenziert bereits
Artifact-UUIDs generisch (`entity_type` als Diskriminator). Da jede Goal-/MainGoal-Version
ihren eigenen `Artifact` hat, funktioniert die Baseline-Aufnahme automatisch, ohne
Sonderbehandlung: eine Baseline erfasst schlicht den `Artifact` der zu diesem Zeitpunkt
gültigen Version, mit vollem `state`-JSON-Snapshot (`BaselineDeltaIndexEntry.state`,
`baseline/models.py:156`) — genau wie bei jedem anderen Artefakttyp. Kein neuer Code in
`baseline/` nötig.

---

## 7. Workspace-Toggles & Testing

Zwei unabhängige Booleans auf `Workspace`: `goals_enabled` (Feature als Ganzes
sichtbar/nutzbar), `goals_ai_enabled` (nur die AI-Generierung). Beide unabhängig
umschaltbar — `goals_enabled=false` blendet den gesamten Ziele-Bereich (Goals +
MainGoal) aus REST/MCP/UI aus; `goals_ai_enabled=false` blendet nur die
Generierungs-Funktion aus (Abschnitt 6), Goals/MainGoal-Lesen/manuelles Setzen bleiben
nutzbar.

Testing folgt dem etablierten Layer-2/3/4-Muster von Risk/Adr/PromptTemplate:
Service-Unit-Tests (Layer 2, inkl. `create_version`-Immutabilität, Freigabe-Reset-
Verhalten und `lineage_id`-Gruppierung), REST-ViewSet-Tests inkl. dem echten
`versions`-Endpoint (Layer 3), MCP-Tool-Tests (Layer 3/4), E2E-Test für den kompletten
Flow (Goal anlegen → freigeben → editieren [→ Reset auf Entwurf] → erneut freigeben →
MainGoal generieren → freigeben → VersionPanel zeigt echte Historie) analog zu
bestehenden E2E-Suiten.

---

## 8. Out of Scope

- Automatischer Trigger für MainGoal-Generierung bei neuer Goal-Freigabe (Design lässt
  Raum dafür, nicht jetzt implementiert).
- Automatisches Umhängen von TraceLinks bei neuer Freigabe (akzeptierter Trade-off aus
  Abschnitt 2.2).
- Refactoring des PromptTemplate-Systems auf ein generisches Name-Keyed-Schema
  (Abschnitt 1) — nur der vierte Slot wird nach bestehendem Muster ergänzt.
- Übertragung des Immutable-Row-Versionierungsmusters auf die anderen 7 betroffenen
  Artefakttypen (Requirement, StakeholderNeed, ArchitectureElement, TestCase, Adr, Risk,
  Issue) — das ist der Gegenstand von Issue #213, eigener Design-Aufwand, nicht Teil
  dieser Arbeit. `Goal`/`MainGoal` dienen hier lediglich als Pilot/Machbarkeitsnachweis.
- Custom-LLM-Base-URL für Anthropic/OpenAI-Provider — ausgelagert nach
  [Issue #212](https://github.com/Popoboxxo/ReqogniLoom/issues/212).
