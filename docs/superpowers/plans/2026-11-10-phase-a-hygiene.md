# Phase A — Backlog-Hygiene Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 6 Issues schließen (#85, #1153, #1399, #1411, #1407, #946), 4 Labels korrigieren (#1247, #1287, #1578, #1230), Backlog von 31 auf 25 offene Issues bringen.

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
- #946 hat echte Bluepencil-Lücken (zentrales Löschen), die mit dem Schließen untergehen. Test: Task 6 prüft das und legt bei Bedarf ein Issue an.

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
- Read: `backend/rest_api/serializers.py:638` (`StandardPagination`)
- Read: `backend/rest_api/query_params.py` (`parse_change_reason`, `parse_int_param`)
- Read: `backend/rest_api/views.py:5439` (`TraceabilityViewSet`), `backend/rest_api/urls.py:292`
- Read: `backend/auth_tenancy/` (API-Key über `Authorization: Bearer`)
- Create: `.tmp/phase-a-1407-verdicts.md` (Scratch, nicht committen)

**Interfaces:** Produces: Urteilstabelle mit fünf Zeilen. Task 5 liest sie.

Die fünf Befunde aus #1407 und die Hypothese aus dem Quellcode (beta.29):

| # | Befund | Hypothese |
|---|---|---|
| 1 | `offset` wird ignoriert | `StandardPagination` ist seitenbasiert (`page`, `page_size`), kennt kein `offset`. Kein Fehler, wenn nicht dokumentiert. |
| 2 | `page_size=0`, `-1`, `1000000` antworten 200 mit 10 Ergebnissen | Klemmen ist dokumentiert (#571, `page_size` und `max_page_size` stehen in der Antwort). Für 0 und negativ prüfen, ob 400 gewollt ist. |
| 3 | `DELETE …?change_reason=x` antwortet 400, `DELETE` mit Body 204 | Echter Konsistenzfehler: Clients und Proxies verlieren DELETE-Bodies. Prüfen, ob `parse_change_reason` die Query liest. |
| 4 | `Authorization: Bearer <API-Key>` antwortet 200 | Vermutlich gewollt (API-Key-Authentifizierung über Bearer). Gegen Auth-Doku prüfen. |
| 5 | `GET /api/v1/traceability/` antwortet 404 | `TraceabilityViewSet` ist `GenericViewSet` ohne `list`. Nur Unter-Aktionen (impact, path, cycles). 404 ist by design. |

- [ ] **Step 1: Punkte 1, 2 und 5 durch bestehende Tests belegen**

Run: `cd backend && grep -rn "page_size" rest_api/tests/*pagination* | head; grep -rn "traceability/" rest_api/tests/ | head`
Expected: Tests für `page_size` und `max_page_size` existieren. Für Punkt 2 den Fall `page_size=0` und `-1` im Test prüfen oder per Django-Testclient ausführen (lokales Test-Setup: `DB_USER` auf den Superuser setzen, siehe Projekt-Memory).

- [ ] **Step 2: Punkt 3 reproduzieren (Test schreiben, nicht fixen)**

```python
# backend/rest_api/tests/test_delete_change_reason_query.py
def test_delete_requirement_accepts_change_reason_in_query(api_client, requirement, workspace):
    resp = api_client.delete(
        f"/api/v1/requirements/{requirement.id}/?change_reason=probe&workspace_id={workspace.id}"
    )
    assert resp.status_code == 204
```
Run: `cd backend && DB_USER=<superuser> pytest rest_api/tests/test_delete_change_reason_query.py -v`
Expected bei bestätigtem Fehler: FAIL mit 400. Bei Erfolg: Punkt 3 ist bereits behoben, Test löschen. Der Test wird nicht committet, er belegt nur das Urteil.

- [ ] **Step 3: Punkt 4 gegen die Auth-Doku prüfen**

Run: `cd backend && grep -rn "Bearer" auth_tenancy/api_key_auth*.py auth_tenancy/authentication*.py | head`
Expected: Entweder dokumentierter Pfad "API-Key über Bearer" (gewollt) oder keiner. Bei "gewollt, aber undokumentiert": Doku-Hinweis als Folge notieren.

- [ ] **Step 4: Urteile in `.tmp/phase-a-1407-verdicts.md` festhalten**

Format je Zeile: `Punkt | Urteil (gewollt / Fehler / Doku-Lücke) | Beleg (Datei:Zeile oder Testlauf)`.

---

### Task 5: #1407 abschließen

**Files:** keine.

**Interfaces:** Consumes: Urteilstabelle aus Task 4. Produces: #1407 geschlossen, null oder mehr neue Issues.

- [ ] **Step 1: Für jeden Punkt mit Urteil "Fehler" oder "Doku-Lücke" ein Einzel-Issue anlegen**

Erwartet nach Hypothese: Punkt 3 (DELETE `change_reason` als Query).
```bash
gh issue create --title "[BUG][LOW][rest] DELETE akzeptiert change_reason nur im Body, nicht als Query-Parameter" --label bug --label low --label rest --body "Aus #1407 (R3-08). DELETE ...?change_reason=x antwortet 400 'change_reason is required by preset policy', derselbe Aufruf mit Body 204. Clients und Proxies verlieren DELETE-Bodies. Erwartet: Query-Parameter wird wie Body gelesen. Beleg: Test in Task 4 der Phase-A-Pläne. Bündel: Phase B (REST-Kleinkram)."
```
Neue Issues in die Roadmap-Tabelle eintragen, Zähler nachziehen (31 − 6 + N).

- [ ] **Step 2: #1407 schließen**

```bash
gh issue close 1407 --reason "not planned" --comment "Sammel-Issue, Punkte einzeln geprüft gegen main (beta.29): 1 offset: Pagination ist seitenbasiert (page, page_size), kein offset vorgesehen. 2 page_size: Klemmen mit Echo von page_size und max_page_size ist dokumentiert (#571). 3 DELETE change_reason: <neues Issue #N | bereits behoben>. 4 Bearer mit API-Key: <gewollt | Doku-Lücke #N>. 5 GET /traceability/ 404: TraceabilityViewSet ist GenericViewSet ohne list, nur Unteraktionen, by design. Geschlossen, echte Punkte laufen in Einzel-Issues."
```
Die Platzhalter in `<...>` mit den Urteilen aus Task 4 füllen, bevor der Befehl läuft.

- [ ] **Step 3: Verifizieren**

Run: `gh issue view 1407 --json state --jq .state`
Expected: `CLOSED`

---

### Task 6: #946 schließen, Bluepencil-Lücken prüfen

**Files:**
- Read: `frontend/src/bluepencil/index.tsx`, `host.ts`, `loader.ts`

**Interfaces:** Produces: #946 geschlossen. Optional ein Bluepencil-Lücken-Issue.

- [ ] **Step 1: Prüfen, was Bluepencil bietet**

Run: `cd frontend/src/bluepencil && grep -n "export\|delete\|filter\|session\|export" index.tsx host.ts | head -40`
Expected: Overlay, Notizen, Export (Markdown/JSON) vorhanden. Zentrales Löschen nach Filter oder Sitzung: bestätigen oder als Lücke notieren.

- [ ] **Step 2: Bei Lücke ein kleines Issue anlegen, sonst überspringen**

```bash
gh issue create --title "[FEATURE][LOW][frontend] Bluepencil: Notizen zentral nach Filter oder Debug-Sitzung löschen" --label enhancement --label frontend --body "Aus #946. Bluepencil deckt Overlay, Notizen und Export ab. Es fehlt (zu bestätigen): zentrales Löschen nach Filter, nach Debug-Sitzung oder komplett, nur für Admins. Umsetzung im vendorten Layer frontend/src/bluepencil/ bzw. im Host."
```

- [ ] **Step 3: #946 schließen**

```bash
gh issue close 946 --reason "not planned" --comment "Die Fähigkeit (Overlay, Notizen, Markdown/JSON-Export) existiert über den vendorten Bluepencil-Review-Layer (frontend/src/bluepencil/). Die spezifizierte Architektur (DebugNote-Modell, REST, MCP, Build-Flag VITE_DEBUG_NOTES) wurde nie gebaut und wird nicht gebaut. Entscheidung Daniel 2026-11-10. Echte Lücken: <Issue #N | keine>."
```

- [ ] **Step 4: Verifizieren**

Run: `gh issue view 946 --json state --jq .state`
Expected: `CLOSED`

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
Expected: `25` plus Anzahl neu angelegter Issues aus Task 5 und 6.

Run: `for n in 1247 1230 1287 1578; do gh issue view $n --json state,labels --jq '"\(.state) \([.labels[].name]|join(","))"'; done`
Expected: alle `OPEN`, Labels wie in Tasks 2 und 8.

- [ ] **Step 3: Roadmap-Zähler nachziehen**

Falls Task 5 oder 6 neue Issues angelegt haben: in der Phasen-Tabelle der Roadmap eintragen (z. B. DELETE-Query-Issue in Phase B) und "Offen danach" anpassen.

- [ ] **Step 4: Commit (nur Plan-Dokumente, über den `git`-Agenten)**

```bash
git add docs/superpowers/plans/2026-11-10-phase-a-hygiene.md docs/superpowers/plans/2026-11-10-backlog-roadmap.md
git commit -m "docs: add phase A hygiene plan for the backlog roadmap"
```
Der Commit läuft über den `git`-Agenten im Worktree `.tmp/phase-plans`.

---

## Self-Review

- **Abdeckung:** Roadmap Phase A nennt #85, #1153, #1399, #1411, #1407, #946 schließen und #1247, #1287, #1578, #1230 labeln. Tasks 1 bis 3, 5, 6, 8 decken das ab. #1247 liegt in Task 2.
- **Zähler:** 31 − 6 = 25. Neue Issues aus Tasks 5 und 6 erhöhen ihn, deshalb "plus Anzahl neu angelegter".
- **Lücke gefunden und geschlossen:** #1411 hat zwei Befunde, nur einer war Planner-Verhalten. Task 3 benennt beide.
- **Offen:** Urteile zu den fünf Punkten in #1407 sind Hypothesen aus dem Quellcode, nicht ausgeführte Messungen. Task 4 belegt sie. Das Triage-Gate bleibt Pflicht.
