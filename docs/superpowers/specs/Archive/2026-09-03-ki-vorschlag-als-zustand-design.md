# KI-Vorschlag als Zustand — Design

**Status:** Draft, pending user review
**Quelle:** `docs/SYSTEMAUDIT_2026-09-02_GROB.md`, Kap. Q2.1 (AI-nativ ist AI-angeschlossen),
E2.1 (API-Keys ohne Scopes und Ablauf), Priorisierung O (Rang 1b: "Der USP 'AI-nativ'
steht und fällt damit"). Fünfte von mehreren unabhängigen Folge-Specs aus demselben Audit
— siehe
[2026-09-03-attribute-definition-design.md](2026-09-03-attribute-definition-design.md),
[2026-09-03-datenmodell-konsolidierung-design.md](2026-09-03-datenmodell-konsolidierung-design.md),
[2026-09-03-traceability-semantik-design.md](2026-09-03-traceability-semantik-design.md),
[2026-09-03-interview-engine-fix-design.md](2026-09-03-interview-engine-fix-design.md).
**Scope:** Nicht Teil dieser Spec: Workflow-Transitionen als Vorschlag (bewusst
ausgeklammert — bleiben bei Signature-Gates, siehe Abschnitt 6), Memory-als-Kontext (Q2.1
dritter Baustein, eigene, noch nicht geschriebene Spec zu Kap. M), Webhook-Self-Service
(E2.2, eigenes Thema).

## 1. Problem

Die Produktstrategie sagt "Agenten sind First-Class-Clients". Der Code sagt: ein
`ApiKey` gehört einem `User` (`auth_tenancy/models.py:82`) — "Claude Code von Daniel" und
"Daniel" sind im System dieselbe Person, mit allen Rechten des Users, tenantweit,
unbefristet. Das Audit-Log kennt bereits `actor_type = agent` mit `client_name`
(`audit/writer.py:64`) — der richtige Ansatz, aber er bleibt im Log. Ein Agent, der ein
Requirement anlegt, schreibt direkt in dieselbe Wahrheit wie ein Mensch; es gibt kein
Konzept "KI schlägt vor, Mensch bestätigt" auf dem Artefakt selbst, sichtbar, filterbar,
mit Bulk-Accept. Ohne das wird die SE-Zielgruppe das Produkt aus Prinzip ablehnen (Q2.1).

## 2. Ziel

Zwei Bausteine, aufeinander aufbauend:

1. **Agenten-Identität:** ein API-Key kann explizit als Agent handeln, nicht als der
   besitzende Mensch — mit eigenem Scope, eigenem Workspace-Zugriff, eigenem Ablaufdatum.
2. **Vorschlag als Workflow-Zustand:** ein von einem Agenten erzeugtes Artefakt landet in
   einem neuen Zustand `proposed` statt im normalen Start-Zustand — **wenn** der
   aufgelöste Workflow-Graph des Typs/Presets diesen Zustand kennt. Bestätigen/Verwerfen
   sind normale, konfigurierbare Übergänge derselben Workflow-Engine, die es schon gibt.
   Kein Parallelsystem.

## 3. Agenten-Identität

`ApiKey` (`auth_tenancy/models.py:62`) erweitert um:

```python
principal_type = models.CharField(max_length=16, choices=[("user","User"),("agent","Agent")], default="user")
agent_label = models.CharField(max_length=255, blank=True)   # z.B. "Claude Code — Daniels Workspace"
scope = models.CharField(max_length=16, choices=[("read","Read"),("write","Write")], default="write")
workspace_ids = models.JSONField(default=list, blank=True)    # leer = alle Workspaces des Users
expires_at = models.DateTimeField(null=True, blank=True)
```

Das liefert nebenbei Audit-Befund E2.1 vollständig mit (Scopes + Ablauf), der laut
Priorisierung ohnehin als eigenständiger Punkt vor dieser Spec gelöst werden sollte —
kein Grund für eine separate Spec, da es dieselbe Tabelle und denselben Zweck betrifft.

Bei `principal_type="agent"` trägt der resolvte `AuthContext` `actor_type="agent"` (statt
den Zugriff wie bisher als den besitzenden User zu maskieren) — das ist exakt das
`actor_type`, das `audit/writer.py` schon in jeden Audit-Eintrag schreibt, jetzt aber
schon am Auth-Layer gesetzt, nicht erst nachträglich im Log rekonstruiert.
`agent_label` erscheint in der UI überall, wo heute der User-Name stünde (Provenienz-
Anzeigen, Audit-Verlauf, WorkflowHistoryEntry-Actor-Spalte).

## 4. Vorschlag als Workflow-Zustand

### 4.1 Neuer Zustand im Default-Graphen (standard/extended-Presets)

Der Bootstrap für `GlobalWorkflowDefinition` (bereits bestehende Infrastruktur,
`workflow/models.py`) bekommt für `standard`/`extended` einen zusätzlichen Zustand
`proposed` mit zwei ausgehenden Übergängen im Default-`workflow_json` jedes Typs:

```json
{
  "states": ["proposed", "draft", "..."],
  "transitions": [
    {"from_state": "proposed", "to_state": "draft",
     "allowed_roles": ["editor", "approver", "admin"],
     "requires_change_reason": false, "signature_gate": false},
    {"from_state": "proposed", "to_state": "rejected",
     "allowed_roles": ["editor", "approver", "admin"],
     "requires_change_reason": true, "signature_gate": false}
  ]
}
```

`minimal` behält seinen heutigen Default-Graphen **ohne** `proposed` — das ist die
gesamte Rigor-Kopplung, kein separater Schalter. `rejected` ist ein neuer Terminalzustand,
analog zu bestehenden Terminalzuständen (z. B. `deprecated`); Artefakte darin sind aus
aktiven Listen gefiltert, genau wie heute schon andere Terminalzustände.

Workspace-Admins können `proposed` in ihrem `WorkflowEngineDefinition`-Override
entfernen oder hinzufügen (bestehender Customization-Mechanismus) — ein Workspace kann
sich also bewusst gegen den Preset-Default entscheiden, das ist gewollte Flexibilität,
kein Leck.

### 4.2 Initialisierung

Jeder `create_X()`-Servicepfad (Requirement, StakeholderNeed, ArchitectureElement, Risk,
TestCase, Adr, Issue, Goal, künftig Icd/Diagram/GlossaryTerm nach der
Datenmodell-Konsolidierung-Spec) prüft beim Initialisieren des Workflow-States: ist
`ctx.actor_type == "agent"` **und** enthält der aufgelöste Graph für `(item_type,
resolved_preset)` einen Zustand `proposed`? Wenn ja, `WorkflowItemState.current_state =
"proposed"` statt des normalen Startzustands. Sonst unverändert wie heute.

Kein neues Feld auf `Artifact` oder der spezialisierten Tabelle nötig — "ist das noch ein
offener Vorschlag" ist direkt `WorkflowItemState.current_state == "proposed"`, "wer hat
vorgeschlagen" steht im `WorkflowHistoryEntry`, der bei der State-Initialisierung ohnehin
geschrieben wird (`actor_type`, `client_name` aus Abschnitt 3).

### 4.3 Harte Regel: Agent bestätigt nie sich selbst

Unabhängig von `allowed_roles`: ein Principal mit `actor_type="agent"` darf niemals eine
Transition **aus** dem Zustand `proposed` heraus ausführen — Prüfung im
Transition-Validator, nicht nur in der Preset-Konfiguration, damit ein
falsch konfiguriertes `allowed_roles` (das versehentlich eine Agent-Rolle enthält) die
Kontrolle nicht aushebeln kann.

### 4.4 Sichtbarkeit, Filter, Bulk-Accept (Frontend)

- Artefakt-Zeile/-Header zeigt bei `current_state == "proposed"` einen Hinweis
  ("Vorschlag von {agent_label}") statt des normalen Status-Badges, mit den beiden
  Aktionen als Transition-Buttons (Bestätigen/Verwerfen) — wiederverwendet exakt die
  bestehende Status-Transition-Button-Komponente, kein neues UI-Muster.
- Listenfilter "nur KI-Vorschläge" (`current_state=proposed`) — ein zusätzlicher
  Statuswert im bestehenden Statusfilter, keine neue Filterkomponente.
- Bulk-Accept: Mehrfachauswahl in der Liste + "Ausgewählte bestätigen" ruft die
  `proposed → draft`-Transition für jedes ausgewählte Artefakt auf. Minimalversion der in
  Kap. Q1.3 geforderten Massenbearbeitung — kein vollständiges Bulk-Edit, nur dieser eine
  Übergang.

## 5. TraceLink: `proposed_by`/`proposed_at` statt Workflow-Zustand

TraceLinks sind keine workflow-getrackten Items (kein `WorkflowItemState`-Eintrag pro
Link) — ein eigener Workflow-Graph nur für "Link bestätigen" wäre eine neue Abstraktion
für ein einfaches Ja/Nein. Stattdessen die beiden Felder, die die
Traceability-Semantik-Spec (Abschnitt 5) bereits als offenen Punkt notiert hat:

- `proposed_by` (FK auf den erzeugenden `ApiKey`, nullable — null sobald bestätigt oder
  wenn ein Mensch den Link direkt angelegt hat)
- `proposed_at` (Timestamp, nullable)

Bestätigen löscht beide Felder (setzt auf `null`). Verwerfen löscht den Link. Dieselbe
harte Regel wie 4.3: nur ein Nicht-Agent-Principal darf bestätigen/verwerfen.

## 6. Warum Transitionen bewusst ausgeklammert bleiben

Der Audit-Zitat-Wortlaut ("jede Transition, die ein Agent schreibt, ist proposed_by_agent
bis ein Mensch bestätigt") würde auch normale Statuswechsel durch einen Agenten
einschließen. Das braucht einen Revert-Mechanismus (Ablehnen = Zustand auf den vorherigen
`WorkflowHistoryEntry` zurücksetzen) zusätzlich zum bestehenden Signature-Gate-System —
zwei parallele Kontrollmechanismen für dieselbe Sache. Stattdessen: wer
Agenten-Transitionen kontrollieren will, setzt `signature_gate: true` auf der jeweiligen
Übergangsregel — bestehende Infrastruktur, sofort nutzbar, kein neuer Code.

## 7. Migration

Additiv, kein Datenumbau bestehender Zeilen nötig:

1. `ApiKey`-Schemaerweiterung (Abschnitt 3) — bestehende Keys erhalten
   `principal_type="user"` als Default (unverändertes Verhalten).
2. `TraceLink`-Erweiterung um `proposed_by`/`proposed_at` — läuft in derselben
   Migration wie die `rationale`/`suspect_*`-Felder aus der Traceability-Semantik-Spec
   (Abschnitt 6 dort), nicht doppelt anlegen.
3. Bootstrap-Migration der `GlobalWorkflowDefinition`-Defaults für standard/extended um
   `proposed`/`rejected` erweitern. Bestehende Workspace-`WorkflowEngineDefinition`-Zeilen
   mit `is_customized=False` übernehmen die Erweiterung automatisch (bestehendes
   Propagations-Verhalten aus dem Workflow-System); `is_customized=True`-Workspaces
   bekommen sie nicht automatisch — ein Admin kann sie über die Workflow-Editor-UI
   (bestehend) manuell nachziehen.

## 8. Risiken

- **Agent-Erkennung an vielen Stellen:** jeder `create_X()`-Pfad (aktuell 8, nach der
  Datenmodell-Konsolidierung-Spec 11) muss den `proposed`-Check einbauen — ein
  vergessener Pfad lässt einen Agenten unbemerkt direkt in `draft` schreiben. Ein
  gemeinsamer Helper (`WorkflowInitializationService.initial_state_for(ctx, item_type,
  workspace_id)`) statt Kopiercode in jedem Service ist Pflicht, nicht optional.
- **Bestehende Agent-Integrationen brechen nicht, ändern aber Verhalten:** ein heute
  produktiv genutzter API-Key eines Users, der faktisch nur von einem Agenten verwendet
  wird (z. B. Claude Code, per `.mcp.json` konfiguriert), bleibt `principal_type="user"`,
  bis der Besitzer ihn explizit auf `"agent"` umstellt — das ist Absicht (keine
  rückwirkende Verhaltensänderung ohne bewusste Migration durch den Nutzer), aber bedeutet
  auch, dass diese Spec ohne aktives Nachziehen bestehender Keys wirkungslos bleibt.
- **`rejected` als neuer Terminalzustand** muss von allen Stellen berücksichtigt werden,
  die heute "aktive" vs. "terminale" Zustände unterscheiden (Listen-Filter, Coverage-
  Berechnung, Dashboard-Zählungen) — ein vergessener Konsument zeigt abgelehnte
  KI-Vorschläge fälschlich als aktive Artefakte an.
