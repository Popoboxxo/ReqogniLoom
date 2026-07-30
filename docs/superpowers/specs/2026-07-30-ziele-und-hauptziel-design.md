# ReqogniLoom — Ziele & Haupt-Ziel (Design)

Neues Artefakt "Ziele" (Goals) pro Workspace, plus ein per LLM aggregiertes "Haupt-Ziel"
(MainGoalVersion), das versioniert und explizit vom User freigegeben werden muss, bevor es
gültig wird. Beide unterliegen dem bestehenden generischen WorkflowEngine — keine
Sonderschienen, exakt nach dem etablierten Muster von Risk/Adr/Issue.

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
- **PromptTemplate (`persistence/models.py:1638`):** Immutable-Row-per-Version
  (`version`-Feld der `AuditableModel`-Basis zweckentfremdet, siehe Docstring dort),
  `is_active`-Flag markiert die aktuelle Version, Uniqueness applikationsseitig
  erzwungen (kein Partial-Index-Präzedenzfall im Repo). **Kein** Artifact-/TraceLink-
  Bezug — PromptTemplate ist eine Settings-Entität, kein Engineering-Artefakt.
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
  Namen aus `PromptTemplate`. Für die Haupt-Ziel-Injection in andere System-Prompts
  reicht das bestehende Lade-Muster.

---

## 2. Datenmodell

### 2.1 `Goal`

```python
class Goal(TenantScopedModel):
    artifact = models.OneToOneField(
        "persistence.Artifact", on_delete=models.CASCADE, related_name="goal",
        help_text="REQ-L2-TE-020: backing Artifact for TraceLink support.",
    )
    workspace_id = models.UUIDField(db_index=True)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    # `version` (optimistic concurrency) von TenantScopedModel geerbt, unverändert.
```

Ein `Goal` ist ein normales, in-place editierbares Artefakt (kein Versions-Log wie
PromptTemplate) — Änderungen laufen über den regulären Update-Pfad, `version` bleibt der
optimistische Concurrency-Zähler aus der Basisklasse. Genau wie bei Risk/Issue.

### 2.2 `MainGoalVersion`

```python
class MainGoalVersion(TenantScopedModel):
    artifact = models.OneToOneField(
        "persistence.Artifact", on_delete=models.CASCADE, related_name="main_goal_version",
        help_text="REQ-L2-TE-020: backing Artifact for TraceLink support. "
                   "Variante A: jede Version hat ihren eigenen dedizierten Artifact.",
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
    # `version` (optimistic concurrency) von TenantScopedModel geerbt.
    # Zusätzlicher fortlaufender Zähler pro Workspace für die menschenlesbare
    # Versionsnummer der Reihe — siehe application/goal_service.py::create_version().
    sequence_number = models.PositiveIntegerField()
```

**Design-Entscheidung (final, User-Vorgabe):** Variante A — jede `MainGoalVersion`-Zeile
bekommt ihren **eigenen** `Artifact` (OneToOne), nicht einen einzigen geteilten
Workspace-Artifact über alle Versionen hinweg. Begründung des Users:
"nachvollziehbarer" als eine geteilte Artifact-Identität über mutierende Versionen hinweg.

**Akzeptierter Trade-off (bewusst, hier explizit dokumentiert statt stillschweigend
übergangen):** TraceLinks, die auf eine bestimmte `MainGoalVersion` zeigen, sind fest an
diese eine eingefrorene Version gebunden. Wird eine neue Version erzeugt und freigegeben,
zeigt der TraceLink weiterhin auf die alte (jetzt nicht mehr gültige) Version — semantisch
"veraltet"/verwaist, ohne automatische Migration auf die neue Version. Dies ist bewusst in
Kauf genommen, nicht Teil dieses Designs zu lösen (z. B. kein automatisches
TraceLink-Umhängen bei neuer Freigabe).

### 2.3 Gültiges Haupt-Ziel

Kein separates Feld "current" — die gültige Version ist definiert als: die
`MainGoalVersion` mit dem `WorkflowItemState.current_state` `Freigegeben`, die zuletzt in
diesen State transitioniert ist, pro Workspace. Existiert keine solche Version, gibt es
kein gültiges Haupt-Ziel (nicht "vorheriges Ziel" im Sinne einer Historie, sondern
"kein Ziel gesetzt" — siehe Abschnitt 4).

Jede Mutation von `full_text` **oder** `compact_text` (egal ob AI oder manuell) läuft
ausschließlich über eine einzige Mutation `MainGoalVersionService.create_version(...)`, die
eine neue Zeile mit `source`, neuem `sequence_number`, neuem `Artifact`,
`Freigegeben=nicht gesetzt` (Start-State `Entwurf`) anlegt. Es gibt keinen In-Place-Update-
Pfad für `full_text`/`compact_text` einer bestehenden Zeile — konsistent mit dem
PromptTemplate-Immutable-Row-Muster.

---

## 3. Workflow-Integration

Beide Modelle werden genau wie `Risk`/`Adr` unabhängig voneinander an die generische
WorkflowEngine angeschlossen (`WorkflowItemState`, eigener `WorkflowEngineDefinition`-
Preset je Typ, Workspace-override-fähig). Keine Änderung am Engine-Core.

**Goal-Workflow (Preset `goal_default`):**

| State | Bedeutung |
|---|---|
| `Entwurf` | Initialzustand, bearbeitbar |
| `Freigegeben` | Wird als Input für Haupt-Ziel-Aggregation berücksichtigt |
| `Archiviert` | Nicht mehr aktiv, nicht Teil der Aggregation |

Transitionen: `Entwurf → Freigegeben`, `Freigegeben → Archiviert`,
Rück-Transitionen `Freigegeben → Entwurf`, `Archiviert → Entwurf`.

Nur Goals im State `Freigegeben` fließen als Input in die Haupt-Ziel-Generierung ein.

**Haupt-Ziel-Workflow (Preset `main_goal_default`):** dieselben drei States/Transitionen,
unabhängig konfigurierbar vom Goal-Preset (separater Preset-Name, kein geteiltes
Preset-Objekt).

---

## 4. Haupt-Ziel-Generierung & Freigabe-Flow

1. **Trigger:** manuell (Button/REST/MCP-Call). Design lässt Raum für einen späteren
   automatischen Trigger (z. B. bei jeder neuen Goal-Freigabe), aber das ist explizit
   nicht Teil dieser Iteration — kein Scaffolding dafür jetzt.
2. **Generierung:** `MainGoalVersionService.generate_ai(...)` sammelt alle Goals mit
   `current_state == Freigegeben` im Workspace, baut den Prompt aus dem
   `goal_aggregate`-Template (Abschnitt 6), ruft den konfigurierten LLM-Provider
   (bestehende `llm_adapter`-Abstraktion, ADR-02) in einem Schritt für `full_text` und
   `compact_text` auf, und persistiert über `create_version(source="ai", ...)`.
3. **Manuelles Setzen:** `MainGoalVersionService.create_manual(...)` — gleicher
   `create_version`-Pfad, `source="manual"`, User liefert `full_text`/`compact_text`
   direkt.
4. **Freigabe:** Jede neue Version startet im State `Entwurf` (unabhängig von `source`).
   Sie wird erst durch eine explizite Workflow-Transition `Entwurf → Freigegeben`
   (regulärer WorkflowEngine-Transition-Call, kein Sonderpfad) zur gültigen Version.
5. **Bis zur Freigabe** bleibt die vorherige `Freigegeben`-Version (falls vorhanden)
   weiterhin die gültige — oder es gibt kein gültiges Haupt-Ziel, wenn nie eine Version
   freigegeben wurde.
6. **Injection in andere Prompts:** Andere AI-Derivation-Flows können das aktuell
   gültige Haupt-Ziel (`compact_text` bevorzugt, `full_text` als Fallback) über denselben
   Service-Lookup einbinden, den auch REST/MCP für den Lesezugriff nutzen — kein
   zweiter Code-Pfad.

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

Damit ist das Haupt-Ziel-AI-Prompt-Template im bestehenden Workspace-AI-Prompt-Template-
Bereich sichtbar und editierbar — keine neue UI-Sektion nötig.

---

## 6. REST / MCP / UI

**REST** (`/api/v1/`): `GoalViewSet` (CRUD, Workflow-Transition-Endpoint — Muster wie
bestehende Risk/Adr-ViewSets), `MainGoalVersionViewSet` (Read + `create` [manuell] +
`generate` [AI] + Workflow-Transition-Endpoint für Freigabe, kein Update auf bestehender
Zeile).

**MCP:** neue Tool-Gruppe (analog zu `risk.*`/`adr.*`):
`goal.read`, `goal.create`, `goal.update`, `goal.delete`,
`main_goal.read` (liefert aktuell gültige Version), `main_goal.generate`,
`main_goal.create_manual`, `main_goal.list_versions`, `main_goal.approve` (Workflow-
Transition-Wrapper).

**UI:** Neuer "Ziele"-Bereich pro Workspace (Liste + Detail für Goals, analog zu
bestehenden Artefakt-Listen/Detail-Views), Haupt-Ziel-Karte mit aktueller gültiger
Version, Versions-Historie, "Generieren"-Button (deaktiviert/Fehlermeldung wenn AI-Toggle
aus), Freigabe-Button (Workflow-Transition-UI, analog zu bestehenden Approval-Buttons).

**AI-Toggle-Verhalten:** Generierungs-Einstiegspunkte (Button, REST `generate`-Endpoint,
MCP `main_goal.generate`) bleiben sichtbar/aufrufbar, liefern aber bei deaktiviertem
Workspace-AI-Toggle einen expliziten Fehler ("AI disabled for this workspace") statt sich
zu verstecken.

---

## 7. Workspace-Toggles & Testing

Zwei unabhängige Booleans auf `Workspace`: `goals_enabled` (Feature als Ganzes
sichtbar/nutzbar), `goals_ai_enabled` (nur die AI-Generierung). Beide unabhängig
umschaltbar — `goals_enabled=false` blendet den gesamten Ziele-Bereich (Goals +
Haupt-Ziel) aus REST/MCP/UI aus; `goals_ai_enabled=false` blendet nur die
Generierungs-Funktion aus (Abschnitt 6), Goals/Haupt-Ziel-Lesen/manuelles Setzen bleiben
nutzbar.

Testing folgt dem etablierten Layer-2/3/4-Muster von Risk/Adr/PromptTemplate:
Service-Unit-Tests (Layer 2, inkl. `create_version`-Immutabilität und
Freigabe-Reset-Verhalten), REST-ViewSet-Tests (Layer 3), MCP-Tool-Tests (Layer 3/4),
E2E-Test für den kompletten Flow (Goal anlegen → freigeben → Haupt-Ziel generieren →
freigeben) analog zu bestehenden E2E-Suiten.

---

## 8. Out of Scope

- Automatischer Trigger für Haupt-Ziel-Generierung bei neuer Goal-Freigabe (Design lässt
  Raum dafür, nicht jetzt implementiert).
- Automatisches Umhängen von TraceLinks bei neuer Haupt-Ziel-Freigabe (akzeptierter
  Trade-off aus Abschnitt 2.2).
- Refactoring des PromptTemplate-Systems auf ein generisches Name-Keyed-Schema
  (Abschnitt 1) — nur der vierte Slot wird nach bestehendem Muster ergänzt.
- Custom-LLM-Base-URL für Anthropic/OpenAI-Provider — ausgelagert nach
  [Issue #212](https://github.com/Popoboxxo/ReqogniLoom/issues/212).
