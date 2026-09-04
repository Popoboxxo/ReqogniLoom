# Offene Entscheidungen aus der Plan-Erstellung (2026-09-03/04)

> Entstanden beim Schreiben der elf Implementierungspläne zu den elf Architektur-Specs aus
> `docs/SYSTEMAUDIT_2026-09-02_GROB.md` (siehe `docs/superpowers/plans/index.md` für die
> vollständige Liste). Diese Datei sammelt die Punkte, die während der Plan-Erstellung
> gefunden wurden und eine echte Entscheidung des Nutzers brauchen — plus meine Empfehlung
> zu jedem Punkt. Kein Plan- oder Spec-Dokument im Sinne der writing-plans-Skill, sondern
> ein Entscheidungsprotokoll.

**Status-Legende:** ✅ Entschieden — ⏳ Offen (Empfehlung vorhanden, wartet auf Bestätigung)

---

## 1. ✅ Entschieden — Datenmodell-Konsolidierung: Versionierungs-Ansatz (Decision D-4)

**Plan:** `docs/superpowers/plans/2026-09-03-datenmodell-konsolidierung.md`, Phase 5 (Tasks 25–29)

**Problem:** Die Spec verlangte, drei Versionstabellen (`DiagramVersion`, `IcdVersion`,
`GlossaryTermVersion`) ins bestehende Audit-Log (`backend/audit/`) zu migrieren. Das ist
wörtlich nicht umsetzbar: `VersionReconstructor` liegt in `baseline/`, nicht `audit/`,
`AuditEntry` hat keine Payload-Spalte, und 8 von 10 Artefakttypen nutzen ein
Single-Row-Modell ohne abrufbare Inhalts-Historie (`ArtifactDiffService` liefert für
alte Versionen nur `content_available: false`). Eine wörtliche Umsetzung hätte die
einzige echte Content-Historie der drei Legacy-Typen gelöscht.

**Entscheidung des Nutzers:** Zustimmung zum Ersatzansatz — neue generische
`persistence.ArtifactVersion`-Tabelle als einheitlicher Content-History-Speicher —
**unter drei ausdrücklichen Bedingungen:**

1. **Alle Artefakte im System werden korrekt und vollständig historisiert.**
2. **Alle Artefakte bleiben versionierungsfähig.**
3. **Baselining funktioniert weiterhin uneingeschränkt.**
4. **Das Ganze muss am Ende performant sein.**

### Wie der Plan diese vier Bedingungen bereits erfüllt (verifiziert)

- **Vollständigkeit (1):** Task 27 ("Record a revision on every content write")
  verdrahtet den Revision-Schreibpfad in den Create/Update-Pfaden von
  `diagram/manager.py`, `icd/icd_manager.py`, `application/glossary_service.py`,
  `requirement_service.py`, `stakeholder_need_service.py`, `test_service.py`,
  `architecture_service.py`, `adr_service.py`, `risk_service.py`, `issue_service.py` —
  zehn Typen.
- **Versionierungsfähigkeit (2):** `ArtifactVersion.payload` speichert einen vollen
  Feld-Snapshot pro Revision (keine Delta-Kette, die replayed werden müsste) — genau der
  Entwurfsgrund, der die drei Legacy-Tabellen brauchbar machte und das Audit-Log nicht.
  `ArtifactVersionService.snapshot_fields()` baut den Snapshot aus derselben
  `_ENTITY_FIELDS`-Liste, die `ArtifactDiffService` fürs Diffing nutzt — Snapshot und
  Diff-Feldmenge können nicht auseinanderlaufen.
- **Performanz (4):** `ArtifactVersion` hat einen zusammengesetzten Index auf
  `("artifact", "revision")` plus Unique-Constraint, RLS-Policy nach Bestandsmuster
  (`0067_rls_remaining_pl_tables.py`). Das Voll-Snapshot-Design (statt Delta-Replay) ist
  selbst die zentrale Performance-Entscheidung — Lesen einer beliebigen Revision ist ein
  einzelner indizierter Zeilen-Zugriff, kein Kettenlauf.
- **Baselining (3):** Der Plan trennt die Zuständigkeiten explizit — `ArtifactVersion`
  ist Inhalts-Historie pro Artefakt, Baselines bleiben der Mechanismus für
  Cross-Artefakt-Zeitpunkt-Schnappschüsse ("Cross-artifact point-in-time history remains
  the job of Baselines", Task 29-Notiz). Baseline-Snapshot-Erstellung selbst wird in
  Task 8 auf die Workflow-Engine umgestellt, nicht auf `ArtifactVersion` — beide
  Mechanismen bleiben unabhängig funktionsfähig.

### Verifizierte Lücke — MUSS vor Umsetzung ergänzt werden

**Task 27 deckt `Goal`, `MainGoal` und `ChangeRequest` nicht ab.** Die Datei-Liste des
Tasks nennt zehn Services, aber weder `goal_service.py` noch `main_goal_service.py` noch
`change_request_service.py` — verifiziert per Grep gegen den Plan-Text (Zeilen 950-951
und 5210-5211 betreffen `goal_service`/`main_goal_service` nur im Kontext der
Status-Konsolidierung aus Phase 0, nicht der Revision-Aufzeichnung aus Phase 5;
`change_request_service` kommt im gesamten Plan-Text kein einziges Mal vor). Damit ist
Bedingung 1 ("alle Artefakte … vollständig historisiert") aktuell **nicht** erfüllt.

**Empfehlung:** Task 27 um drei weitere Modify-Ziele ergänzen
(`application/goal_service.py`, `application/main_goal_service.py`,
`application/change_request_service.py`, jeweils deren Create/Update-Pfade), inkl.
passender Testfälle nach demselben Muster wie die neun bestehenden Modify-Ziele. Kleiner,
gut abgegrenzter Nachtrag — keine neue Architektur, nur fehlende Konsumenten desselben
bereits gebauten `ArtifactVersionService.record()`-Aufrufs.

**Status:** Umsetzung des Nachtrags noch offen — dem Senior-Developer-Agenten, der Plan #1
geschrieben hat, zur Ergänzung zu übergeben, bevor Phase 5 implementiert wird.

---

## 2. ⏳ Offen — KI-Vorschlag-als-Zustand: Provenienz-Löschung bei TraceLinks

**Plan:** `docs/superpowers/plans/2026-09-03-ki-vorschlag-als-zustand.md`, §5 /
`docs/superpowers/specs/2026-09-03-ki-vorschlag-als-zustand-design.md`, Abschnitt 5

**Befund:** Bestätigen eines von einem Agenten vorgeschlagenen `TraceLink` löscht
`proposed_by`/`proposed_at` vollständig (auf `null`). Bei Artefakten bleibt die Herkunft
dagegen im Workflow-Verlauf (`WorkflowHistoryEntry`) erhalten, auch nachdem der
`proposed`-Zustand verlassen wurde. Für Links gibt es kein Äquivalent zum Workflow-
Verlauf — die Löschung ist also eine echte, dauerhafte Informations-Löschung, keine reine
Zustands-Bereinigung.

**Frage:** War das so gewollt (Links brauchen keine dauerhafte Herkunfts-Spur), oder ist
das ein Spec-Fehler, der behoben werden sollte?

**Meine Empfehlung:** Beheben — Konsistenz mit dem Artefakt-Verhalten herstellen. Kleinste
Lösung: `proposed_by`/`proposed_at` beim Bestätigen **nicht** auf `null` setzen, sondern
zusätzlich `confirmed_by`/`confirmed_at` setzen (Link zeigt dann "vorgeschlagen von X am
…, bestätigt von Y am …" statt nach Bestätigung spurlos "von einem Menschen angelegt"
auszusehen). Kein neues Modell nötig, zwei zusätzliche nullable Felder auf `TraceLink`.

**Status:** Wartet auf deine Entscheidung.

---

## 3. ⏳ Offen — Traceability-Semantik: Always-on-Validierung bricht bestehende Links

**Plan:** `docs/superpowers/plans/2026-09-03-traceability-semantik.md`, Tasks 9/10 /
`docs/superpowers/specs/2026-09-03-traceability-semantik-design.md`, Abschnitt 3.2

**Befund:** Die 8-Typ-Erlaubt-Matrix der Spec nennt `Goal`, `MainGoal`, `Issue` und
`Interview`-bezogene Artefakte nicht. Sobald die Matrix-Prüfung "immer gilt" statt nur im
`se_mode`, werden heute funktionierende Links dieser Typen (z. B. Goal↔Requirement, seit
Fix #237 real genutzt) unanlegbar.

**Frage:** Bestandsschutz (Default im Plan: ein Inventar-Command misst zuerst, wie viele
bestehende Links betroffen wären, bevor irgendetwas hart bricht) — oder lieber hart
brechen und die betroffenen Links vorab bereinigen/migrieren?

**Meine Empfehlung:** Bestandsschutz — der im Plan vorgesehene Inventar-Command ist der
richtige erste Schritt so oder so (er liefert die Zahl, auf der jede Entscheidung beruhen
sollte). Hart brechen ohne diese Zahl zu kennen wäre eine Entscheidung im Blindflug.

**Status:** Wartet auf deine Entscheidung.

---

## 4. ⏳ Offen — Traceability-Semantik: `refines` → `derives-from`-Zusammenlegung

**Plan:** `docs/superpowers/plans/2026-09-03-traceability-semantik.md`, Task 18 /
`docs/superpowers/specs/2026-09-03-traceability-semantik-design.md`, Abschnitt 3.1

**Befund:** `refines` ist im Code (`hierarchy.py`) bewusst **nicht** als Hierarchie-Kante
markiert — symmetrisch, ohne Ebenen-Semantik. `derives-from` ist eine gerichtete
Hierarchie-Kante. Die von der Spec vorgeschriebene Zusammenlegung macht jede bisher
symmetrische `refines`-Kante zu einer gerichteten `derives-from`-Kante — die SE-Auditor-
Regeln TRACE-P1/VERIF-P8 feuern danach auf einer anderen Kantenmenge als heute.

**Frage:** Wie spezifiziert migrieren (Default im Plan: migrieren, den Auditor-Regel-
Delta vorher messen und dokumentieren) — oder `refines` stattdessen auf `references`
abbilden (schwacher, unsemantischer Bezug, keine Hierarchie-Umdeutung)?

**Meine Empfehlung:** Migration wie spezifiziert, aber **erst nachdem** das Delta-Messen
(im Plan bereits als Schritt vorgesehen) ein überschaubares Ergebnis zeigt. Der SE-Ansatz
der Spec (`derives-from` als einzige Herkunfts-/Hierarchie-Semantik) ist konzeptionell
sauberer als ein drittes, schwaches `references`-Auffangbecken für `refines` — aber das
ist nur vertretbar, wenn die Zahl der betroffenen Requirement↔Requirement- und
Arch↔Arch-Kanten überschaubar ist. Erst messen, dann endgültig entscheiden.

**Status:** Wartet auf deine Entscheidung (Empfehlung: nach der Messung final bestätigen,
nicht blind vorab).

---

## 5. ⏳ Offen — GitHub-Jira-Integration ↔ KI-Vorschlag: `WorkflowHistoryEntry`-Felder doppelt geplant

**Pläne:** `docs/superpowers/plans/2026-09-03-github-jira-integration.md`, Task 17 /
`docs/superpowers/plans/2026-09-03-ki-vorschlag-als-zustand.md`

**Befund:** Beide Specs (KI-Vorschlag §3 und GitHub-Jira §4.2) setzen
`WorkflowHistoryEntry.actor_type`/`client_name` voraus, aber keine der beiden Specs
ordnet das Feld eindeutig einem Migrations-Owner zu. Plan #8 (GitHub-Jira) hat die Lücke
bemerkt und legt die Felder jetzt selbst an (Task 17) — Plan #4 (KI-Vorschlag) ist aber in
der Implementierungsreihenfolge **vor** Plan #8 vorgesehen und braucht dieselben Felder
schon früher.

**Frage:** Reicht es, dass Plan #8 die Felder anlegt (Plan #4 müsste dann prüfen, ob sie
schon existieren, statt sie zu duplizieren) — oder soll die Feld-Migration explizit in
Plan #4 verschoben werden, damit die Migrations-Reihenfolge zur
Implementierungsreihenfolge passt?

**Meine Empfehlung:** Migration nach Plan #4 verschieben — das ist der Plan, der laut
Reihenfolge zuerst implementiert wird und die Felder als Erster braucht. Plan #8 bekäme
dann stattdessen einen Consumes-Verweis auf Plan #4 statt einer eigenen Migration
(dasselbe Muster, das mehrere andere Pläne in dieser Serie schon für Cross-Spec-
Abhängigkeiten nutzen — "Step 0 prüft und blockiert, statt zu duplizieren").

**Status:** Wartet auf deine Entscheidung.

---

## Hinweis ohne Entscheidungsbedarf: GitHub-Issue #848

Plan #11 (Rollenbasierte-Sichten) fand, dass `NAV_ITEMS.requires` und `useHasRole` bereits
in `main` existieren (Commit `54b09760`, vor Beginn dieser Spec-Serie gemergt) — Issue
#848 ("Rollenbasierte UI fehlt"), das in dieser Session gemeldet wurde, könnte damit ganz
oder teilweise bereits erledigt sein. Keine Entscheidung nötig, nur eine Prüfung: auf
Wunsch verifiziere ich das gegen den Live-Stand und schließe das Issue, falls zutreffend.
