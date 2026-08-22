# Multi-Artifact Discovery Interview — Design

## Ziel

Heute startet jedes Interview mit einem festgelegten Zieltyp (Requirement,
StakeholderNeed, ...) — der Anwender muss vorher schon wissen, was er
braucht. Diese Spec fügt einen neuen Einstieg hinzu: einen Chat, der dem
Anwender hilft herauszufinden, WELCHE Artefakte (auch mehrere, auch
unterschiedlichen Typs) er aus einem geschilderten Problem heraus braucht,
und diese nach Bestätigung im selben Gespräch anlegt — inklusive
Verknüpfungen untereinander (Trace-Links) und eines Verweises zurück auf das
erzeugende Interview.

Die bestehenden 8 Einzeltyp-Interviews bleiben unverändert nutzbar. Diese
Funktion ist eine Ergänzung, kein Ersatz.

## Ausgangslage (Ist-Zustand)

- `InterviewSession` (`backend/persistence/models.py:2258`) bindet
  `artifact_type` fix bei `start()` (`interview_service.py:42-98`) — kein
  Wechsel danach möglich.
- `InterviewService.formalize()` (`interview_service.py:596-703`) erzeugt
  genau EIN Artefakt. Nur `Requirement` ist implementiert; die anderen 7
  Typen aus `IN_SCOPE_ARTIFACT_TYPES` (`interview_protocol.py:19-28`) werfen
  `ValidationError("not implemented yet")`.
- `resulting_artifact_ids` ist als JSON-Liste angelegt, wird aber nie mit
  mehr als 1 Eintrag befüllt.
- Rechte-Modell ist grob (`auth_tenancy/services/authorization.py:35-62`):
  Erstellen jedes Artefakttyps läuft unter der `WRITE`-Operation
  (Editor/Approver/Admin dürfen, Viewer nicht) — es gibt **keine**
  Rechteprüfung pro Artefakttyp. "Zugriff auf alle Typen" heißt also: ein
  einziger `WRITE`-Check pro Workspace, keine Typ-Matrix.
- MCP-Server spiegelt die Service-Schicht 1:1: `mcp_server/tools/interview.py`
  registriert 9 Tools (`interview.start`, `.answer`, `.formalize`, ...), die
  direkt `InterviewService` aufrufen. REST (`rest_api/views.py`) macht
  dasselbe. Erweitere ich `InterviewService`, ziehen beide Oberflächen mit —
  das ist ADR-01 (Single-Entry-Point) bereits so vorgesehen.
- `formalize()` ruft für Requirement dieselbe Methode
  (`RequirementService.create_requirement()`) wie der normale REST-Create-
  Endpunkt auf; diese initialisiert intern den Workflow-Start-Status
  (`initialize_workflow_states()`, `requirement_service.py:248-263`). Kein
  Sonderweg — Workflow-Korrektheit ist also automatisch gegeben, solange
  neue Adapter denselben Grundsatz befolgen (siehe unten).
- `GlossaryTerm` ist heute NICHT in `IN_SCOPE_ARTIFACT_TYPES` — kommt mit
  dieser Spec neu dazu (Anwender-Wunsch: "Requirement + passender
  Glossareintrag" muss möglich sein).

## Architektur-Überblick

```
User klickt "Ich weiß noch nicht genau, was ich brauche"
  → InterviewSession(session_kind="multi", artifact_type=None)
  → Chat läuft frei (LLM versteht Problem, stellt Rückfragen)
  → LLM kann jederzeit einen strukturierten Vorschlag emittieren:
        [{type: "StakeholderNeed", title, fields, links: []},
         {type: "Requirement", title, fields, links: [{to: 0, type: DERIVES_FROM}]},
         {type: "GlossaryTerm", title, fields, links: []}]
  → Chat rendert Vorschlag als Vorschau-Graph (React Flow), Knoten je Artefakt,
    Kanten je vorgeschlagener Trace-Link
  → Anwender bestätigt per Button (kein Freitext-Parsing von "ja")
  → interview.formalize (multi) → 1 DB-Transaktion:
        pro Eintrag: Adapter-Registry[type](fields, ctx) → echter create_X()-Service
        pro Link: TraceLink anlegen
        InterviewSessionArtifact-Zeilen anlegen (Provenienz)
  → Erfolg: alle N Artefakte sichtbar, jedes mit Link "angelegt via Interview X"
  → Fehler (z.B. Pflichtfeld fehlt): komplette Transaktion rollt zurück,
    Fehler wird im Chat angezeigt, Gespräch geht weiter, erneut bestätigbar
```

## Datenmodell-Änderungen

**`InterviewSession`** (`backend/persistence/models.py`):
- `artifact_type`: wird `null=True` (heute Pflichtfeld).
- Neues Feld `session_kind`: `CharField`, Werte `"single"` (Default, heutiges
  Verhalten) / `"multi"` (neu). Migration mit Default `"single"` für
  Bestandsdaten — keine Verhaltensänderung für existierende Sessions.
- `resulting_artifact_ids` (JSON-Liste) bleibt zur Abwärtskompatibilität
  bestehen, wird aber nicht mehr die Quelle der Wahrheit für Provenienz.

**Neu: `InterviewSessionArtifact`** (Join-Tabelle statt JSON-Liste):
- `session` (FK → InterviewSession)
- `artifact_id` (UUID, generisch — die Artefakt-Basisklasse `Artifact` hat
  eine einheitliche ID über alle Subtypen hinweg, siehe `models.py:680`)
- `artifact_type` (CharField, zur Anzeige ohne zusätzlichen Typ-Lookup)
- `created_at`

Grund für eigene Tabelle statt JSON: der Anwender will auf jeder
Artefakt-Detailseite sehen "angelegt via Interview X" — das ist eine
Rückwärtssuche (`WHERE artifact_id = ?`), die auf einer JSON-Liste ohne
GIN-Index unpraktikabel ist. Eine echte Tabelle macht das zu einem simplen,
indizierten Join.

## Adapter-Registry (formalize für alle Typen)

Ersetzt das heutige `if/elif` in `InterviewService.formalize()`:

```python
# backend/application/interview_artifact_adapters.py (neu)
ARTIFACT_CREATION_ADAPTERS: dict[str, Callable[..., Artifact]] = {
    "StakeholderNeed": lambda fields, ctx, ws: StakeholderNeedService().create_need(
        workspace_id=ws, ctx=ctx, **fields),
    "Requirement": lambda fields, ctx, ws: RequirementService().create_requirement(
        workspace_id=ws, ctx=ctx, **fields),
    "ArchitectureElement": lambda fields, ctx, ws: ArchitectureService().create_element(
        workspace_id=ws, ctx=ctx, **fields),
    "Risk": lambda fields, ctx, ws: RiskService().create_risk(
        workspace_id=ws, ctx=ctx, **fields),
    "TestCase": lambda fields, ctx, ws: TestCaseService().create_testcase(
        workspace_id=ws, ctx=ctx, **fields),
    "Adr": lambda fields, ctx, ws: AdrService().create_adr(
        workspace_id=ws, ctx=ctx, **fields),
    "Issue": lambda fields, ctx, ws: IssueService().create_issue(
        workspace_id=ws, ctx=ctx, **fields),
    "Goal": lambda fields, ctx, ws: GoalService().create_goal(
        workspace_id=ws, ctx=ctx, **fields),
    "GlossaryTerm": lambda fields, ctx, ws: GlossaryService().create_term(
        workspace_id=ws, ctx=ctx, **fields),
}
```

**Regel (bindend für jede Adapter-Implementierung):** jeder Adapter MUSS den
existierenden, produktiven `create_X()`-Service-Aufruf des jeweiligen Typs
verwenden — niemals einen eigenen/abgekürzten Insert-Pfad. Das ist der
Grund, warum Workflow-Status-Initialisierung automatisch korrekt bleibt
(siehe Ausgangslage oben): jeder `create_X()` macht das bereits selbst.

Dieser Registry-Ansatz löst nebenbei die 7 "not implemented yet"-TODOs der
bestehenden Einzeltyp-Interviews — `formalize()` (single) nutzt künftig
dieselbe Registry mit genau 1 Eintrag statt eigenem Code.

## Multi-Formalize (Anlegen mehrerer Artefakte)

```python
# InterviewService (erweitert)
def formalize(self, session_id, ctx, confirmed_proposal=None):
    session = self._get_session(session_id, ctx)
    if session.session_kind == "single":
        return self._formalize_single(session, ctx)   # heutiges Verhalten, unverändert
    return self._formalize_multi(session, ctx, confirmed_proposal)

def _formalize_multi(self, session, ctx, confirmed_proposal):
    with transaction.atomic():                         # Stück 2: alles oder nichts
        created = []
        for item in confirmed_proposal:
            adapter = ARTIFACT_CREATION_ADAPTERS[item["type"]]
            artifact = adapter(item["fields"], ctx, session.workspace_id)
            InterviewSessionArtifact.objects.create(
                session=session, artifact_id=artifact.id, artifact_type=item["type"])
            created.append(artifact)
        for link in confirmed_proposal_links:           # z.B. Req --DERIVES_FROM--> Need
            TraceLinkService().create_link(
                source=created[link["from"]], target=created[link["to"]],
                link_type=link["type"], ctx=ctx)
        session.status = "completed"
        session.save()
    return created
```

Bei Validierungsfehler in irgendeinem Schritt: Django-Transaktion rollt
automatisch zurück, kein Artefakt bleibt halb angelegt. Fehler wird an den
Chat zurückgegeben (welches Item, welches Feld), Anwender kann im selben
Gespräch nachbessern und erneut bestätigen.

## Vorschlags-Protokoll (LLM-Seite)

Neuer `PromptTemplate`-Key `interview.protocol.multi` (gleiche
3-Level-Override-Kette wie heute: Factory-Default → Tenant → Workspace, via
`prompt_resolver.py`). Anders als die heutigen Einzeltyp-Protokolle (feste
`phases[]` mit `required_fields[]` für EINEN Typ) ist das Multi-Protokoll
frei geführt: das LLM versteht das geschilderte Problem, stellt Rückfragen,
und kann jederzeit einen strukturierten Vorschlagsblock emittieren (Liste
von `{type, title, fields, links}}`) — nach demselben Muster, wie
`AiDerivationService.derive_requirements_from_need()` heute schon
`{"drafts": [...]}` liefert (`ai_derivation_service.py:401-460`). Kein neuer
Parsing-Mechanismus nötig, bestehendes Muster wird wiederverwendet.

Verfeinerung eines Vorschlags (z.B. "die zweite sollte höhere Priorität
haben") läuft über normale Chat-Nachrichten, nicht über ein separates
Bearbeiten-Formular auf der Vorschau-Karte — das LLM aktualisiert seinen
Vorschlag im nächsten Turn. Bewusste Scope-Entscheidung für v1: kein
Inline-Editor auf der Vorschau-Karte.

## Visuelle Vorschau

Neue Komponente `frontend/src/components/InterviewWidget/ProposalPreviewGraph.tsx`,
gebaut auf `@xyflow/react` (bereits Projekt-Dependency, nutzt heute schon
`WorkflowEditor` und die Diagramm-Ansicht — keine neue Library). Knoten =
vorgeschlagene Artefakte (Farbe nach Typ, aus `tokens.css`), Kanten =
vorgeschlagene Trace-Links mit Typ-Label. Reiner Anzeige-Zweck (nicht
editierbar) — Bestätigen-Button sitzt darunter/daneben, kein Bestandteil
des Graphen.

## Cross-Linking / Provenienz

- Verknüpfungen ZWISCHEN den neu angelegten Artefakten: bestehende
  `TraceLink`-Typen (`traceability/types.py`), vom LLM im Vorschlag
  spezifiziert (z.B. `DERIVES_FROM` für Requirement←Need). Kein neuer
  Link-Typ nötig.
- Verknüpfung Artefakt→Interview (Provenienz): über
  `InterviewSessionArtifact` (siehe Datenmodell oben), NICHT über TraceLink
  (TraceLink ist Artefakt-zu-Artefakt, eine Interview-Session ist kein
  Artefakt). Jede Artefakt-Detailseite bekommt einen neuen Info-Block
  "Angelegt via Interview" mit Link zum Transkript, sofern ein
  `InterviewSessionArtifact`-Eintrag existiert.

## Einstiegspunkt (Frontend)

`InterviewWidget.tsx`: zusätzlicher Button neben den 8 (bzw. jetzt 9 mit
Glossar) Typ-Buttons — "Ich weiß noch nicht genau, was ich brauche". Nur
sichtbar, wenn der Anwender `WRITE` im aktuellen Workspace hat (gleicher
Check wie heute bei den Einzeltyp-Buttons). Startet
`interviewsApi.start({session_kind: "multi"})` statt mit festem
`artifact_type`.

`InterviewChatPane.tsx` wird um zwei neue Render-Fälle erweitert:
Vorschlagskarte (mit `ProposalPreviewGraph` + Bestätigen-Button) und
Ergebnis-Zusammenfassung nach erfolgreichem Anlegen (Liste der N
Artefakte mit Typ-Badge und Link zur Detailseite).

## API / MCP

Da beide Oberflächen dünne Hüllen um `InterviewService` sind (ADR-01), reicht:

- `interview.start`: neuer optionaler Parameter `session_kind`
  (`"single"` Default, `"multi"`); `artifact_type` wird optional.
- `interview.formalize`: bei `session_kind="multi"` erwartet es zusätzlich
  `confirmed_proposal` (die vom Anwender/Agenten bestätigte Liste) und
  liefert eine Liste von Artefakt-IDs statt einer einzelnen zurück
  (Breaking Change nur für den Rückgabetyp bei `session_kind="multi"` —
  Single-Mode-Rückgabewert bleibt exakt wie heute).
- Neues Tool/Endpoint `interview.propose`: liefert den aktuellen
  strukturierten Vorschlag (falls das LLM schon einen emittiert hat) ohne
  etwas anzulegen — Chat-UI pollt/liest das für die Vorschau-Karte; ein
  MCP-Agent kann damit automatisiert vorschlagen lassen und dann gezielt
  `interview.formalize` mit demselben Vorschlag bestätigen.

Kein neuer REST-Serializer-Bruch für die 8 Einzeltyp-Flows — die ändern
sich nicht.

## Fehlerfälle

- Kein `WRITE`-Recht im Workspace → Multi-Chat-Button wird gar nicht erst
  angezeigt (Frontend-Check, wie heute bei Einzeltyp-Buttons).
- LLM liefert keinen parsbaren Vorschlag (kaputtes JSON) → Chat zeigt
  Fehlermeldung, Gespräch läuft normal weiter, kein Session-Abbruch.
- Validierungsfehler beim Anlegen (z.B. Pflichtfeld fehlt) → komplette
  Transaktion rollt zurück (siehe Multi-Formalize oben), Fehler pro Item im
  Chat angezeigt, Anwender bessert nach, bestätigt erneut.

## Testing (Überblick, Details folgen im Implementierungsplan)

- Backend: je ein Unit-Test pro neuem Adapter (StakeholderNeed, Architecture,
  Risk, TestCase, Adr, Issue, Goal, GlossaryTerm — 7 neue + Requirement
  bleibt); ein Integrationstest für `_formalize_multi()` mit 3 gemischten
  Typen + Links, inkl. Rollback-Test bei künstlich erzwungenem Fehler auf
  Item 3.
- Frontend: neuer Einstiegspunkt-Test, Vorschlagskarte-Render-Test,
  Bestätigen→Multi-Create-Mock-Test, Ergebnis-Zusammenfassung-Test.
- i18n: alle neuen UI-Strings brauchen DE/EN-Paare (bestehende
  `i18n-parity`-Ratchet-Konvention).
- `data-testid` auf allen neuen interaktiven Elementen (Projekt-Konvention).

## Bewusst außerhalb dieses Scopes (v1)

- Inline-Bearbeiten der Vorschlagskarte (Verfeinerung nur über Chat-Text).
- Multi-Mode für weitere, nicht-requirements-artige Entitäten (Diagram,
  Baseline, WorkflowDefinition, ...) — die 9 Typen aus
  `IN_SCOPE_ARTIFACT_TYPES` (+ Glossar) sind der Rahmen für v1.
- Eine dedizierte Rechte-Matrix pro Artefakttyp (heutiges grobes
  `WRITE`-Modell wird 1:1 übernommen, keine Erweiterung).
