# Interview-Engine-Fix — Design

**Status:** Draft, pending user review
**Quelle:** `docs/SYSTEMAUDIT_2026-09-02_GROB.md`, Kap. L (Feature-Review Interview-Engine),
R6 (Live-Bestätigung von L2.1). Vierte von mehreren unabhängigen Folge-Specs aus demselben
Audit — siehe
[2026-09-03-attribute-definition-design.md](2026-09-03-attribute-definition-design.md),
[2026-09-03-datenmodell-konsolidierung-design.md](2026-09-03-datenmodell-konsolidierung-design.md),
[2026-09-03-traceability-semantik-design.md](2026-09-03-traceability-semantik-design.md).
**Verhältnis zur bereits archivierten Interview-Engine-Spec**
(`Archive/2026-08-14-interview-management-engine-design.md`) und der
Multi-Artefakt-Erweiterung (`Archive/2026-08-22-multi-artifact-interview-design.md`):
diese Spec ist kein Widerspruch zu deren "vollständig implementiert"-Status — beide
lieferten exakt das, was sie zusagten (Multi-Kind-Formalize über
`ARTIFACT_CREATION_ADAPTERS`, Grounding, Provenienz-Service). Der Single-Kind-Formalize-
Pfad (der vom Live-Audit getestete `POST interviews/{id}/formalize/` für ein Requirement
*oder einen anderen Typ*) war nie Teil dieser Zusage — der Code selbst sagt es:
"per the plan's Self-Review Notes" beim hartcodierten Requirement-only-Guard. Diese Spec
schließt genau diese Lücke, keine andere.

**Scope:** Nicht Teil dieser Spec: Protokoll-Ableitung aus `ai_elicit` (L2.2 — bereits
durch die Attribut-Definition-Spec, deren Abschnitt 7, gelöst), reine Übersetzungsarbeit
(L2.6), MainGoal-Interview-Support (bestehende, nicht revidierte Scope-Entscheidung der
archivierten Spec — passend zum MCP-Surface, das für MainGoal nie Schreib-Tools hatte).

## 1. Problem

Vier unabhängige, kleinere Lücken in einer ansonsten soliden Engine:

- **L2.1 (H):** `interview_service.py:839` — der Single-Kind-`formalize()`-Pfad hat einen
  hartcodierten Guard: nur `artifact_type == "Requirement"` läuft durch, alle anderen 7
  In-Scope-Typen bekommen eine `ValidationError`, deren Text ("only Requirement is wired
  in this plan; the other 7 types follow the identical pattern in a later pass.") eine
  Entwicklernotiz ist, keine Nutzermeldung. Live bestätigt (R6): Interview für Risk
  startbar, beantwortbar, nie abschließbar.
- **L2.3 (M):** `provenance_session_id()` existiert im Service, `InterviewProvenanceBadge`
  existiert als Komponente — aber kein Artefakt-Editor importiert sie. Kein Artefakt zeigt
  sichtbar, dass es aus einem Interview stammt.
- **L2.4 (M):** `interview_service.py:1271` hängt jeden Chat-Turn unbegrenzt an
  `session.transcript` (JSONField) an. Kein Cap, keine Zusammenfassung — jeder Turn lädt
  und schickt das komplette bisherige Transkript als Prompt-Kontext.
- **L2.5 (M):** Widget (Overlay, 188 Zeilen, chat-orientiert) und `/interviews`-Seite
  (Liste + Detail, 1821 Zeilen gesamt) teilen keine Komponenten außer der API — zwei
  vollständige, unabhängig gepflegte Implementierungen desselben Chat-Flows.

## 2. Ziel

L2.1 durch Wiederverwendung des bereits produktiven Multi-Kind-Mechanismus schließen
(kein neuer Code, eine Vereinheitlichung). Provenienz sichtbar machen. Transkript
deckeln, ohne den für die Elizitation nötigen Kontext zu verlieren. Genau eine
vollwertige Interview-Oberfläche statt zwei parallel gepflegten.

## 3. L2.1 — Single-Kind-Formalize über den bestehenden Adapter-Mechanismus

`ARTIFACT_CREATION_ADAPTERS` (`application/interview_artifact_adapters.py`) deckt bereits
8 Typen ab (Requirement, StakeholderNeed, ArchitectureElement, Risk, TestCase, Adr, Issue,
Goal) und wird vom Multi-Kind-Pfad seit der archivierten Spec produktiv genutzt — inkl.
korrektem `create_X()`-Aufruf (Workflow-State-Initialisierung eingeschlossen) und sauberer
Fehlerbehandlung pro Adapter.

**Fix:** der Single-Kind-Pfad ruft für `session.artifact_type` denselben Adapter aus der
Registry auf, statt den hartcodierten `if session.artifact_type != "Requirement": raise`
zu prüfen. `GlossaryTerm` bleibt vorerst über den bestehenden `_glossary_term`-Adapter
abgelehnt (klare `ValidationError`, kein stiller Fehler) — bis die ergänzte
Datenmodell-Konsolidierung-Spec ihr Artifact-Backing liefert (siehe deren Abschnitt 4),
danach ein einzeiliger Adapter-Eintrag nach demselben Muster wie die anderen acht.

Ein Regressionstest pro Typ (Requirement bereits vorhanden, sieben neu): Interview starten
→ Pflichtfelder beantworten → `formalize()` → Artefakt existiert mit korrektem
`artifact_type` und initialisiertem Workflow-State.

## 4. L2.3 — Provenienz sichtbar machen

`InterviewProvenanceBadge` wird in jeden Artefakt-Editor-`PageHeader` gemountet, sichtbar
wenn `provenance_session_id()` für das Artefakt einen Treffer liefert. Klick auf das Badge
führt zur Session unter `/interviews/{id}` (siehe Abschnitt 6 — das ist ab jetzt die
alleinige Detail-Ansicht).

## 5. L2.4 — Transkript deckeln

Neues Feld `InterviewSession.transcript_summary` (TextField, leer bei Start). Ab dem
zehnten Chat-Turn (Konstante, kein Konfigurationswert — YAGNI, ein fester Schwellwert
reicht) werden die ältesten Turns oberhalb eines gleitenden Fensters von 10 in
`transcript_summary` komprimiert (ein LLM-Call mit dem bestehenden `Mock`-Fallback-Muster,
analog zu `generate_chat_turn`) statt weiter im vollen `transcript`-JSONField zu wachsen.
Der Prompt-Kontext für den nächsten Chat-Turn besteht dann aus `transcript_summary` +
den letzten 10 Turns im Klartext, nicht mehr dem kompletten Verlauf.

**Nebeneffekt, bewusst genutzt:** `transcript_summary` ist exakt der Input, den die
Memory-Konsolidierung laut Audit M3 sowieso bräuchte ("Zusammenfassung ist ohnehin das,
was die Memory-Konsolidierung braucht") — diese Spec liefert das Feld, die
Memory-System-Anbindung selbst bleibt Sache einer eigenen, noch nicht geschriebenen Spec
zu Kap. M.

## 6. L2.5 — Eine vollwertige Oberfläche

**Entscheidung (abweichend von der Audit-Empfehlung S19):** die `/interviews`-Seite
bleibt die primäre, vollwertige Interaktionsfläche (Liste + Detail-Chat, wie heute). Das
Widget wird auf einen reinen Schnell-Einstieg reduziert: Typ wählen (oder "weiß noch
nicht genau"), Session anlegen, sofort Redirect nach `/interviews/{id}` — kein eigener
Chat-Pane mehr im Widget. Der heutige 206-Zeilen-Chat-Pane-Code im Widget entfällt
ersatzlos; nur die Popover-Typauswahl (deutlich kleiner) bleibt.

**Begründung für die Abweichung:** der Nutzer hat sich explizit für "Widget nur zum
schnellen Einstieg, Detailarbeit immer auf /interviews" entschieden — passend dazu, dass
Interviews mehrteilige Chat-Verläufe sind, die mehr Platz brauchen als ein
Overlay bequem bietet, und dass ein Overlay, das "über Seitenwechsel offen bleibt und
Formulare überlagert" (S19-Befund), ohnehin ein UX-Problem für längere Sessions ist.

**Popover-Verhalten (behält den S19-Fix bei, unabhängig von der Grundsatzfrage):**
schließt bei Navigation, hat ein `aria-label`. "Per Interview erstellen" im Seitenkopf
öffnet direkt das Widget mit vorgewähltem Typ der aktuellen Seite (statt wie heute auf die
Interviews-Liste zu führen).

## 7. Risiken

- **Transkript-Zusammenfassung ist ein LLM-Call** — schlägt der Provider fehl (siehe P0-Bug
  KI-Robustheit, Issue #846), darf das Interview nicht blockieren. Fallback: Turn 11 wird
  ohne Kompression angehängt, nächster Versuch bei Turn 12 — kein Datenverlust, nur
  verzögerte Kompression.
  - Da Kompression aus einem LLM-Call gespeist wird, könnten Details aus früheren Turns
  in der Zusammenfassung verloren gehen, die für die spätere Formalisierung relevant
  gewesen wären — ein reines Kürzen (letzte N Turns behalten, Rest verwerfen) wäre
  sicherer, aber schlechter für den Kontext. Die Zusammenfassung ist ein bewusster
  Kompromiss, kein Nullrisiko.
- **Widget-Reduktion (Abschnitt 6)** ist eine UX-Entscheidung gegen die Audit-Empfehlung —
  sollte sich in der Praxis zeigen, dass Nutzer den schnellen Overlay-Chat vermissen
  (z. B. für sehr kurze Interviews mit nur 1-2 Fragen), ist das ein Kandidat für eine
  spätere Revision, kein struktureller Fehler dieser Spec.
- Cross-Spec-Abhängigkeit: GlossaryTerm-Adapter (Abschnitt 3) kann erst nach der
  ergänzten Datenmodell-Konsolidierung-Spec (deren Abschnitt 4) fertig verdrahtet werden.
