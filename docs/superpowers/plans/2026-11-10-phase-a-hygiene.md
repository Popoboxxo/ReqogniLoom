# Phase A — Backlog-Hygiene Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 6 Issues schließen (#85, #1153, #1399, #1411, #1407, #946), 4 Labels korrigieren (#1247, #1287, #1578, #1230), Backlog von 31 auf 26 offene Issues bringen (6 schließen, 1 neues Issue für `page_size`).

**Architecture:** Kein Code. Reine Tracker-Arbeit mit `gh`, ausgeführt vom `feedback`-Agenten. Jede Schließung hat einen Beleg im Kommentar. #1407 wird zuerst Punkt für Punkt gegen `origin/main` (4f8aa29f, beta.29) verifiziert.

**Tech Stack:** GitHub CLI (`~/.local/bin/gh`, vorher `export PATH=$PATH:~/.local/bin`), Repo `Popoboxxo/ReqogniLoom`.

**Spec:** `docs/superpowers/plans/2026-11-10-backlog-roadmap.md`, Abschnitte "Phase A" und "Entscheidungen" (#1, #2, #13).

## Global Constraints

- Nichts wird geschlossen, bevor Daniel die Liste in Task 7 freigegeben hat. Entscheidung #2 der Roadmap.
- Schließen nur mit Kommentar, der den Beleg nennt. Kein stilles Schließen.
- Kommentare auf Deutsch (interne Doku). Keine Schlüsselwörter `Fixes`/`Closes` in Kommentaren zu Issues, die nicht per PR erledigt sind.
- Keine Git-Mutationen. Das Plan-Dokument selbst wird später über den `git`-Agenten committet.
- `--reason "not planned"` für alles, was nicht gebaut wurde. `completed` nur, wenn ein PR es erledigt hat.
- Alle Befunde gegen `origin/main` 4f8aa29f prüfen, nicht gegen die veraltete Branch-Spitze im Hauptcheckout.

## Review Focus

- Falsch geschlossenes Issue: Ein Punkt in #1407 ist ein echter Fehler und geht verloren. Test: Task 4 erzeugt je Punkt ein Urteil mit Beleg, ein echter Fehler wird ein neues Issue statt geschlossen zu werden.
- #1411 enthält zwei Befunde. Der zweite (Latenz bei 10 parallelen Anfragen, p50 0,875 s gegen 0,341 s einzeln) ist kein Planner-Verhalten. Test: Task 3 benennt ihn im Schließ-Kommentar ausdrücklich.
- #1247 wird beim Re-Labeln versehentlich mitgeschlossen. Test: Task 8 prüft `state == OPEN` für #1247 und #1230.
- Label `upstream` existiert nicht. `gh issue edit --add-label` scheitert. Test: Task 2 legt es vorher an.
- #946 wird mit falscher Begründung geschlossen ("Bluepencil deckt es ab"), obwohl der Layer entfernt ist. Test: Task 6 Step 1 belegt die Entfernung (`1ad7ef17`), der Kommentar nennt sie.

---

### Task 1: #85 schließen

**Files:** keine.

**Interfaces:** Produces: #85 geschlossen, Zähler 30.

- [ ] **Step 1: Prüfen, dass #85 nur Altbefunde enthält**

Run: `gh issue view 85 --json title,body --jq '.title'`
Expected: Titel enthält "v1.0.0". Die dort genannten Befunde (Workflow-Init in `seed_demo`, `DEBUG=True`, Nginx-Prod-Build, stale Dashboard-Counts) stammen von Commit 973a620, über 600 Commits alt.

- [ ] **Step 2: Schließen**

```bash
gh issue close 85 --reason "not planned" --comment "Review stammt von v1.0.0 (Commit 973a620) und ist veraltet. Die Befunde wurden seither in eigenen Issues bearbeitet oder sind durch die Versionen 1.1 bis 1.8 überholt. Noch relevante Punkte (Empty States, Pagination) laufen in Phase B der Backlog-Roadmap (docs/superpowers/plans/2026-11-10-backlog-roadmap.md). Geschlossen im Rahmen der Backlog-Hygiene."
```

- [ ] **Step 3: Verifizieren**

Run: `gh issue view 85 --json state,stateReason --jq '.state+" "+.stateReason'`
Expected: `CLOSED NOT_PLANNED`

---

### Task 2: #1153 schließen, #1247 als Upstream-Tracker labeln

**Files:** keine.

**Interfaces:** Produces: Label `upstream`. #1247 offen mit Labels `bug`, `upstream`. Task 8 setzt das voraus.

- [ ] **Step 1: Label anlegen**

```bash
gh label create upstream --color 6f42c1 --description "Ursache liegt in einer externen Abhängigkeit, kein lokaler Fix möglich"
```
Expected: `✓ Label "upstream" created`. Falls es schon existiert: überspringen.

- [ ] **Step 2: #1153 schließen**

```bash
gh issue close 1153 --reason "not planned" --comment "Dublette von #1247. #1247 trägt den Befund weiter (Regression, gleicher Defekt). Ursache: Honcho-Dialektik sendet den konfigurierten Header x-opencode-session nicht, das liegt im Vendor-Seam (Honcho-Engine), nicht in ReqogniLoom. Entscheidung: ADR-023, Notiz docs/audit/2026-10/honcho-dialectic-upstream-note.md. Tracker: #1247."
```

- [ ] **Step 3: #1247 labeln und kommentieren**

```bash
gh issue edit 1247 --add-label bug --add-label upstream
gh issue comment 1247 --body "Bleibt als einziger Tracker für den Honcho-Dialektik-Defekt offen (400 MissingSessionID). Trigger T1 aus ADR-023: memory.ask liefert degraded:false. Erst dann werden die dialektik-abhängigen Teile von #1336 und #1337 umgesetzt (Phase D der Backlog-Roadmap). #1153 ist als Dublette geschlossen."
```

- [ ] **Step 4: Verifizieren**

Run: `gh issue view 1247 --json state,labels --jq '.state+" "+([.labels[].name]|join(","))'`
Expected: `OPEN bug,upstream`

---

### Task 3: #1399 und #1411 schließen

**Files:** keine.

**Interfaces:** Produces: beide geschlossen, Zähler 28 nach Task 3 (31 −#85 −#1153 −#1399 −#1411).

- [ ] **Step 1: Beleg für Planner-Verhalten sichern**

Die Messung in #1399 zeigt: 1908 bzw. 1060 Zeilen, Execution 13,5 ms bzw. 8,6 ms, `idx_scan=0`. Postgres wählt bei so kleinen Tabellen Seq Scan plus Top-N-Sort, weil das billiger ist als der HNSW-Index. Kein Defekt im Index.
Run: `gh issue view 1399 --json body --jq .body | head -20`
Expected: Messwerte wie oben.

- [ ] **Step 2: #1399 schließen**

```bash
gh issue close 1399 --reason "not planned" --comment "Kein Defekt. Bei 1908 (pl_tracelink) und 1060 (pl_requirement) Zeilen wählt der Planner Seq Scan plus Top-N-Sort (13,5 ms bzw. 8,6 ms), weil das billiger ist als der HNSW-Index. Die Indizes pl_tracelink_embedding_hnsw und pl_req_embedding_hnsw existieren und werden bei wachsender Tabelle genutzt. Wiedervorlage: wenn eine Tabelle über etwa 50000 Vektoren wächst, mit EXPLAIN (ANALYZE) erneut messen. Die Hybrid-Suche (#1316) misst Recall und Latenz ohnehin."
```

- [ ] **Step 3: #1411 schließen, zweiten Befund benennen**

```bash
gh issue close 1411 --reason "not planned" --comment "Befund 1 (idx_scan=0 auf pl_tracelink_embedding_hnsw, idx_requirement_fts_gin, at_refresh_token): Planner-Verhalten bei kleinen Tabellen, siehe #1399. Kein Defekt. Befund 2 (10 parallele GET /tracelinks/?page_size=100: p50 0,875 s gegen 0,341 s einzeln, alle 200): Messung auf der QS-Instanz mit Parallelität 10, ohne Fehler. Das ist ein Beobachtungswert, kein Fehler, und wird nicht separat verfolgt. Falls die Latenz relevant wird, als eigenes Performance-Issue mit Zielwert anlegen."
```

- [ ] **Step 4: Verifizieren**

Run: `gh issue view 1399 --json state --jq .state; gh issue view 1411 --json state --jq .state`
Expected: zweimal `CLOSED`

---

### Task 4: #1407 Punkt für Punkt gegen `origin/main` prüfen

**Files:**
- Read: `backend/rest_api/serializers.py` (`StandardPagination`), `backend/rest_api/query_params.py:225` (`parse_change_reason`), `backend/rest_api/views.py:5439` (`TraceabilityViewSet`), `backend/rest_api/urls.py:292`, `backend/auth_tenancy/rest.py` (Authentifizierungsklassen)
- Create: `.tmp/phase-a-1407-verdicts.md` (Scratch, nicht committen)

**Interfaces:** Produces: Urteilstabelle mit fünf Zeilen. Task 5 liest sie.

Die fünf Befunde aus #1407. Die Urteile 1, 2, 3 und 5 sind im Review am Code verifiziert, Punkt 4 ist noch offen:

| # | Befund | Urteil (Code-Beleg) |
|---|---|---|
| 1 | `offset` wird ignoriert | **gewollt.** Listen sind seitenbasiert (`page`, `page_size`). `offset` kennt nur die Allokationsliste (`rest_api/views.py:8313`, `:15021`) |
| 2 | `page_size=0`, `-1` antworten 200 mit der Standardgröße | **kleiner echter Fehler.** Zu große Werte werden geklemmt und im Envelope gespiegelt (`page_size`, `max_page_size`, #571). Werte ≤ 0 und nicht numerische fallen still auf 25 zurück (DRF-Basisverhalten, `get_page_size` erzwingt nichts). Gleiche Klasse wie #1613 (stilles Akzeptieren) |
| 3 | `DELETE …?change_reason=x` antwortet 400 | **bereits behoben.** `parse_change_reason` liest den Body zuerst und die Query als Rückfall (`rest_api/query_params.py:225`, Docstring nennt #1407). Aufrufer: `views.py:1481`, `:2428`, `:3749` |
| 4 | `Authorization: Bearer <API-Key>` antwortet 200 | **offen.** Prüfen, ob ein API-Key über den Bearer-Header gewollt ist (`auth_tenancy/rest.py`) |
| 5 | `GET /api/v1/traceability/` antwortet 404 | **gewollt.** `TraceabilityViewSet` ist `GenericViewSet` ohne `list`, nur Unteraktionen (impact, path, cycles) |

- [ ] **Step 1: Punkt 3 mit einem Test belegen**

```python
# Scratch, nicht committen: backend/rest_api/tests/test_scratch_delete_reason.py
def test_delete_accepts_change_reason_in_query(api_client, requirement, workspace):
    r = api_client.delete(f"/api/v1/requirements/{requirement.id}/?change_reason=probe&workspace_id={workspace.id}")
    assert r.status_code in (200, 204)
```
Run: `cd backend && DB_USER=<Superuser> python -m pytest rest_api/tests/test_scratch_delete_reason.py -v`
Expected: PASS (bestätigt "bereits behoben"). Bei FAIL ist das ein echter Fehler: ein Einzel-Issue statt Schließen. Scratch-Datei danach löschen.

- [ ] **Step 2: Punkt 2 reproduzieren**

```python
def test_scratch_page_size_zero_falls_back_silently(api_client, workspace):
    r = api_client.get(f"/api/v1/requirements/?workspace_id={workspace.id}&page_size=0")
    assert r.status_code == 200 and r.json()["page_size"] == 25
```
Expected: PASS bestätigt das stille Zurückfallen. Dann Task 5 Step 1.

- [ ] **Step 3: Punkt 4 klären**

Run: `cd backend && grep -n "class .*Authentication" -A30 auth_tenancy/rest.py | grep -n "Bearer\|HTTP_AUTHORIZATION\|X-API-Key" | head`
Expected: Entweder Bearer-Verarbeitung für API-Keys (gewollt, dann Doku-Lücke prüfen in `docs/api/`) oder nicht. Urteil festhalten.

- [ ] **Step 4: Urteile in `.tmp/phase-a-1407-verdicts.md` festhalten**

Format je Zeile: `Punkt | Urteil (gewollt / Fehler / bereits behoben / Doku-Lücke) | Beleg (Datei:Zeile oder Testlauf)`.

---

### Task 5: #1407 abschließen

**Files:** keine.

**Interfaces:** Consumes: Urteilstabelle aus Task 4. Produces: #1407 geschlossen, ein neues Issue für Punkt 2 (und ggf. eines für Punkt 4).

- [ ] **Step 1: Neues Issue für Punkt 2 (nach Freigabe)**

```bash
gh issue create --title "[BUG][LOW][rest] page_size <= 0 oder nicht numerisch wird still auf den Standard gesetzt" --label bug --label low --label rest --body "Aus #1407. Zu große page_size-Werte werden geklemmt und im Envelope gespiegelt (#571). Werte <= 0 und nicht numerische Werte fallen dagegen still auf 25 zurück (DRF-Basisverhalten, StandardPagination.get_page_size). Erwartet: 400 mit Hinweis wie bei ungültigen Filterwerten (#1613). Betrifft alle Listen, Änderung also mit Test über mehrere Endpunkte. Bündel: Phase B (REST-Kleinkram)."
```
Der Zähler in der Roadmap zieht um +1 nach (siehe Task 8).

- [ ] **Step 2: #1407 schließen**

```bash
gh issue close 1407 --reason "not planned" --comment "Sammel-Issue, Punkte einzeln gegen main (beta.29) geprüft: 1 offset: Listen sind seitenbasiert (page, page_size), offset ist nur bei der Allokationsliste vorgesehen. 2 page_size <= 0: stilles Zurückfallen auf den Standard, eigenes Issue #<N>. 3 DELETE change_reason als Query: bereits behoben, parse_change_reason (rest_api/query_params.py) liest Body und Query. 4 Bearer mit API-Key: <gewollt | Doku-Lücke #N>. 5 GET /traceability/ 404: TraceabilityViewSet ist ein GenericViewSet ohne list, nur Unteraktionen, gewollt. Geschlossen, der echte Punkt läuft in #<N>."
```
Die Platzhalter in `<...>` mit den Urteilen aus Task 4 füllen, bevor der Befehl läuft.

- [ ] **Step 3: Verifizieren**

Run: `gh issue view 1407 --json state --jq .state`
Expected: `CLOSED`

---

### Task 6: #946 schließen (nicht geplant)

**Files:** keine.

**Interfaces:** Produces: #946 geschlossen mit korrekter Begründung. Zähler −1.

Hintergrund (Review-Fund 2026-11-10): Die frühere Annahme "Bluepencil deckt es ab" stimmt nicht mehr. Der Bluepencil-Review-Layer wurde am 2026-11-02 bewusst entfernt (Commit `1ad7ef17`, `CHANGELOG.md`: "Breaking: the Bluepencil review layer is removed", #1643). `frontend/src/bluepencil/` existiert nicht mehr. Daniel entschied am 2026-11-10: **als nicht geplant schließen.**

- [ ] **Step 1: Beleg sichern**

Run: `git log --oneline -1 --diff-filter=D -- frontend/src/bluepencil | cat && grep -n "Bluepencil review layer is removed" CHANGELOG.md`
Expected: Commit `1ad7ef17` und die Changelog-Zeile.

- [ ] **Step 2: Schließen (nach Freigabe)**

```bash
gh issue close 946 --reason "not planned" --comment "Entschieden: nicht geplant. Der Bluepencil-Review-Layer, über den sich die Fähigkeit (Overlay, Notizen, Export) bis dahin abbilden ließ, wurde am 2026-11-02 bewusst entfernt (Commit 1ad7ef17, Changelog 'Breaking: the Bluepencil review layer is removed', #1643). Ein eigener Annotationslayer für den Admin-Debug-Modus (DebugNote, REST, Export, zentrales Löschen) ist nicht gewollt. Die Spezifikation in diesem Issue bleibt als Referenz lesbar. Bei neuem Bedarf als neues Feature-Issue aufnehmen."
```

- [ ] **Step 3: Verifizieren**

Run: `gh issue view 946 --json state,stateReason --jq '.state+" "+.stateReason'`
Expected: `CLOSED NOT_PLANNED`

---

### Task 7: Freigabe-Liste für Daniel

**Files:** keine.

**Interfaces:** Consumes: Urteile und Kommentartexte aus Task 1 bis 6. Produces: Freigabe, ohne die Tasks 1 bis 3, 5, 6 und 8 nicht laufen.

Diese Task läuft **vor** allen Schließungen. Reihenfolge der Ausführung: Task 4 (nur Lesen), Task 7, dann die übrigen.

- [ ] **Step 1: Liste zeigen**

Je Issue eine Zeile: Nummer, Aktion, geplanter Kommentar, Beleg. Dazu die Label-Änderungen aus Task 8. Format: Tabelle.

- [ ] **Step 2: Auf Freigabe warten**

Daniel bestätigt ganz oder streicht Zeilen. Gestrichene Zeilen bleiben offen und die Zähler in der Roadmap werden angepasst.

---

### Task 8: Labels korrigieren und Endstand prüfen

**Files:**
- Modify: `docs/superpowers/plans/2026-11-10-backlog-roadmap.md` (Zähler, falls neue Issues entstanden)

**Interfaces:** Consumes: Label `upstream` aus Task 2.

- [ ] **Step 1: Labels setzen**

```bash
gh issue edit 1287 --add-label enhancement --add-label low
gh issue edit 1578 --add-label enhancement
gh issue edit 1230 --add-label infra
```

- [ ] **Step 2: Endstand prüfen**

Run: `gh issue list --state open --limit 200 --json number --jq length`
Expected: `26` (31 − 6 + 1 neues Issue aus Task 5 Step 1) plus ein optionales Issue für Punkt 4.

Run: `for n in 1247 1230 1287 1578; do gh issue view $n --json state,labels --jq '"\(.state) \([.labels[].name]|join(","))"'; done`
Expected: alle `OPEN`, Labels wie in Tasks 2 und 8.

- [ ] **Step 3: Roadmap-Zähler nachziehen**

Das neue `page_size`-Issue (Task 5) und ein ggf. angelegtes Issue für Punkt 4 in der Roadmap (Abschnitt "Rest", Bündel REST-Kleinkram, kein Task in den Phasenplänen) eintragen. Die Zähler der Roadmap enthalten das `page_size`-Issue bereits.

- [ ] **Step 4: Commit (nur Plan-Dokumente, über den `git`-Agenten)**

```bash
git add docs/superpowers/plans/2026-11-10-phase-a-hygiene.md docs/superpowers/plans/2026-11-10-backlog-roadmap.md
git commit -m "docs: add phase A hygiene plan for the backlog roadmap"
```
Der Commit läuft über den `git`-Agenten im Worktree `.tmp/phase-plans`.

---

## Self-Review

- **Abdeckung:** Roadmap Phase A nennt #85, #1153, #1399, #1411, #1407, #946 schließen und #1247, #1287, #1578, #1230 labeln. Tasks 1 bis 3, 5, 6, 8 decken das ab. #1247 liegt in Task 2.
- **Zähler:** 31 − 6 + 1 = 26. Das neue Issue stammt aus Task 5 (`page_size`).
- **Lücke gefunden und geschlossen:** #1411 hat zwei Befunde, nur einer war Planner-Verhalten. Task 3 benennt beide.
- **Review 2026-11-10:** Die Urteile zu #1407 sind am Code verifiziert (Punkte 1, 2, 3, 5). Punkt 4 (Bearer mit API-Key) bleibt eine Prüfung in Task 4 Step 3. #946 wird nicht mehr mit Bluepencil begründet (Layer entfernt).
