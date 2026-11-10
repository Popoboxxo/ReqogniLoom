# Review aller Phasenpläne — Backlog-Roadmap

Stand: 2026-11-10, gegen `origin/main` eee309ca. Geprüft: Roadmap und die neun Phasenpläne (A, B1, B2, C, D, E, F, G, H).

## Vorgehen

1. **Pfade:** Alle Dateipfade in den Plänen gegen den Code geprüft (`scripts/check_plan_refs.py`). Nicht gefundene Pfade sind Neuanlagen der Pläne, bis auf einen (Bluepencil, siehe Befund 1).
2. **Symbole:** Alle Klassen, Funktionen und Konstanten aus den Befund-Tabellen mit `git grep` gesucht. Alle vorhanden. Ausnahmen sind gewollt: `ai_summary` (neu in Phase D) und ein Commit-Hash.
3. **Behauptungen aus Issue-Kommentaren** gegen den Code geprüft, wo Entscheidungen darauf beruhten (#946, #1407, #1094, #1287).
4. **"Im Step zu bestätigen"-Punkte** gesammelt und, soweit am Code klärbar, aufgelöst.
5. **Querprüfung:** Zähler, Abhängigkeiten, Migrationen, Tool-Zählung, Vorschläge V1 bis V9.

## Befunde und Behebung

| # | Schwere | Plan | Befund | Behebung |
|---|---|---|---|---|
| 1 | hoch | A, Roadmap (Entscheidung 13) | #946 sollte mit "Bluepencil deckt es ab" geschlossen werden. Der Layer wurde am 2026-11-02 bewusst entfernt (`1ad7ef17`, #1643). `frontend/src/bluepencil/` existiert nicht | Entscheidung von Daniel: **als nicht geplant schließen**, Kommentar mit korrekter Begründung (Task 6 neu) |
| 2 | hoch | E | D9 (Mehrfachallokation) ging von einem Normalfall aus. Die Allokation ist N:1 erzwungen (`AllocationConflictError`, `application/base.py:162`, 409). Mehrfachallokation kann nur über Altbestand, Import oder Baseline-Restore entstehen | D9 auf Schutz für Altbestand reduziert, `Allocation`-Constraint auf **eine aktive Zeile je Requirement** geändert, Test für die 409-Ablehnung im Normalbetrieb ergänzt |
| 3 | mittel | D | Plan nutzte einen Helfer `optional_bool` in `mcp_server/tools/base.py`, der nicht existiert | Boolean wird wie `min_score` im Handler gelesen, REST nutzt `parse_bool_param`. `SearchViewSet` an `rest_api/views.py:12943` festgemacht |
| 4 | mittel | G | Plan nutzte eine Fehlerklasse `ConflictError`, die nicht existiert | Neue Klasse `AdoptionHashMismatchError(ValidationError)` mit `error_code="CONFLICT"`, `http_status=409` nach dem Muster von `AllocationConflictError`, Registrierung im 409-Mapping von REST und MCP |
| 5 | mittel | G | Hook `docs/agent-templates/hooks/review-policy-gate.sh` zählt Rollen auf, der neue Agent `document-steward` fehlte | Fall `document-steward` mit `ask` für `document.adopt` und `document.update`, `review-policy-gate.md` mitziehen |
| 6 | mittel | B1 | Test unter `frontend/scripts/*.test.mjs` wäre nicht gelaufen: `vite.config.ts:36` (`test.include`) kennt nur `src/**/*.{test,spec}.{ts,tsx}` | Include-Erweiterung als eigener Schritt, Befehle auf `npx vitest run scripts` umgestellt |
| 7 | mittel | C | Login-Feld `access` und Scope `read` waren falsch. Der Login-Body trägt `token` (deprecated, #696), Cookies sind der Normalfall. Der kanonische Scope heißt `read_only` (`read` ist Legacy-Alias). Der Klartext-Key steht in `plaintext` | Befehle und Erwartungen korrigiert |
| 8 | mittel | A | #1407-Urteile waren Hypothesen. Verifiziert: `offset` gewollt, DELETE-`change_reason` per Query **bereits behoben** (`parse_change_reason`, `rest_api/query_params.py:225`), `/traceability/` gewollt, `page_size <= 0` fällt still auf 25 zurück | Neues Issue für `page_size` statt für DELETE, Punkt 4 (Bearer mit API-Key) bleibt eine Prüfung |
| 9 | niedrig | Roadmap | "G hängt an E" war veraltet. `Document` und `WorkItem` sind gebaut, S3 braucht keine Allokation | Abhängigkeiten neu gefasst, G ohne Abhängigkeit zu E und zu C (eigener JSON-RPC-Helfer) |
| 10 | niedrig | Roadmap, D | Zähler waren uneinheitlich (Phase D 13 gegen 14, Phase A 25 gegen 26) | Alle Zähler neu gerechnet: 31 → 26 → 22 → 20 → 14 → 12 → 9 → 7 → 6, am Ende sechs bewusst offen |
| 11 | niedrig | Roadmap | Vorschläge V3, V5, V7, V9 sind abgedeckt oder vorhanden, V4 vermutlich vorhanden | Vorschlagstabelle mit Stand, offen bleiben V1, V2, V8 und nach Prüfung V4, V6 |
| 12 | niedrig | F | Tier-Zugriff war offen | Bestätigt: `presets.services.get_preset(str(workspace_id)).preset == "extended"` |

## Ergänzungen

- **Frische-Check:** `scripts/check_plan_refs.py` mit Tests (`scripts/test_check_plan_refs.py`). Prüft die Dateipfade eines Plans gegen den Code. Hätte Befund 1 früh gezeigt.
- **Ausführungsreihenfolge** in vier Wellen mit Aufwand, Parallelität und Voraussetzungen.
- **Querschnittsregeln:** Frische-Check, Migrationen (nacheinander mergen, renummerieren, RLS), Tool-Zähler (nur G ändert 290 auf 293), Git- und PR-Ablauf (Trailer per Datei), Ressourcen, Schließen nach Freigabe, neue Issues.
- **Risikotabelle** und **Release-Vorschlag** (beta.30 bis beta.32).

## Was weiterhin im Step zu bestätigen ist

Diese Punkte lassen sich erst bei der Umsetzung klären und stehen in den jeweiligen Plänen:

| Plan | Punkt |
|---|---|
| A | Task 4 Step 3: Bearer-Header mit API-Key (`auth_tenancy/rest.py`) |
| B1 | Welche #598-Befunde zum Umsetzungszeitpunkt noch gelten (Review bezog sich auf v1.6.0) |
| B2 | Ob für Screenshots ein Stack erreichbar ist |
| C | Docker-Stack lokal (Speicher), Aufruf des Debug-Befehls von OpenCode, mit dem sich Tools ohne LLM-Provider auflisten lassen |
| D | `-k`-Filter der Tests in Task 1, Live-Beleg für Dream (#1336) ohne Honcho-Stack nicht möglich |
| E | Ort des Audit-Regelkatalogs, REST-Ressourcen `elements` und `allocations` |
| F | Welche `transition_status`-Pfade `workflow.services.transition` umgehen, Ort des Service-Agent-Keys je Mandant (Vorschlag Q1-Preference), Legacy-Mapping `step` + `expected_result` |
| G | Ordnerkonvention je Dokumenttyp, Statusmatrix mit `projected_version` |
| H | Ob der Hermes-Host einen Bestätigungsdialog erlaubt, Name der Clientdoku |

## Grenzen dieses Reviews

Kein Plan wurde ausgeführt. Geprüft wurde, ob Pfade, Namen und Behauptungen zum Stand von `main` passen, nicht, ob der geplante Code funktioniert. Die Datenzahlen aus #1669 (890 von 999 Requirements) stammen aus einer QS-Messung vom 2026-11-02 und wurden nicht neu erhoben.
