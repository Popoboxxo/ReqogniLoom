# Phase F — Test und Qualität Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** #587 (Promptfoo) als erledigt belegen und schließen, #1564 (typisierte Testschritte) und #1578 (automatische Qualitätsbewertung) umsetzen.

**Architecture:** #587 ist auf main schon gebaut (Export-Command, 27 Szenarien, CI-Job). #1564 ersetzt die untypisierte Liste `TestCase.steps` durch eine validierte Liste typisierter Schritte `{id, step_type, text}` mit normalisierendem Lesen alter Daten, einer einmaligen Datenmigration und einem Gherkin-Export. #1578 emittiert das bisher nie gesendete Ereignis `WORKFLOW_TRANSITIONED`, hängt einen Konsumenten an den vorhandenen Event-Bus (Muster `artifact_index_projector.py`) und ergänzt einen periodischen Sweep. Beides läuft hinter einem Feature-Flag, unter einem Service-Agent-Key je Mandant, nur im Extended-Tier.

**Tech Stack:** Django 6.1/DRF, Celery (Beat), `application/quality_service.py`, `application/event_bus.py` (Outbox), `workflow/services.py`, MCP (`mcp_server/tools/tests.py`, `quality.py`), React 19 (Task 2), promptfoo (`promptfoo/`), pytest, `gh` (`export PATH=$PATH:~/.local/bin`).

**Spec:** `docs/superpowers/plans/2026-11-10-backlog-roadmap.md`, Phase F, Entscheidungen 9 und 10. Issue-Texte #587, #1564, #1578.

## Entscheidungen (Daniel, 2026-11-10)

| # | Entscheidung |
|---|---|
| 9 | #1564: Schrittmodell `step_type` + `text` mit stabiler Schritt-ID (`given|when|then|and|but`), Normalisierung alter Schritte beim Lesen |
| 10 | #1578: Vertagung (ENT-B4 = a) aufgehoben. Feature-Flag (Default aus), Deckel für QUAL-P1, MCP-Rate-Parität, Item-Level-Permission bei Assessment-Reads. Nur Extended-Tier, nur WARNING |
| 10b | #1578 Identität: **ein Service-Agent-Key je Mandant**, aus Konfiguration. Alle Auto-Läufe (Event und periodisch) laufen darunter. Ohne Key bleibt das Feature aus |

## Befund (origin/main, Code seit 4f8aa29f unverändert)

| Issue | Stand | Beleg |
|---|---|---|
| #587 | **erledigt** | `application/management/commands/export_promptfoo_configs.py`, `application/prompt_testing/cases.py` und 27 Szenario-Dateien `application/prompt_testing/cases/*.yaml`, `promptfoo/package.json`, CI-Job "Prompt Regression (promptfoo, echo)" (`.github/workflows/ci.yml:518-531`), Tests `test_export_promptfoo_configs.py`, `test_prompt_testing_cases.py`. Der Blocker `resolve_and_render` existiert (`application/prompt_resolver.py`). `docs/superpowers/specs/index.md:91` behauptet noch "entirely missing" (veraltet) |
| #1564 | **offen** | `backend/persistence/models.py:2452` `steps = JSONField(default=list)`. Schrittformen heute: `{"step", "expected_result"}` (LLM-Ausgabe in `ai_derivation_service.py:173,1255-1275`), frei beschriebene Dicts über `test_service.py:364`, MCP-Schema `steps: array of object` (`mcp_server/tools/tests.py:495`), Frontend-Widget `TestCaseArtifactForm.tsx` (`steps_data`), Export/Diff/Baseline/Indexer lesen `steps` (`export_service.py:152`, `artifact_diff_service.py:102`, `baseline_rollback_service.py:185`, `artifact_indexer.py:182`) |
| #1578 | **offen** | `application/models.py:74` definiert `WORKFLOW_TRANSITIONED`, es wird nirgends emittiert. `QualityAssessment.Trigger` kennt nur `manual`, `mcp` (`persistence/models.py:4488`). `QualityService.assess(ctx, workspace_id, entity_type, entity_id, *, force, trigger)` (`quality_service.py:194`) verlangt Schreibrecht. Ein Rate-Limit für `quality.assess` per MCP fehlt laut Issue. Zentrale Transition: `workflow/services.py:248` `transition(...)`; daneben eigene `transition_status` in `adr_service`, `risk_service`, `change_request_service`, `document_service`, `work_item_service`. Hintergrundkontext: `application/tasks.py:195-235` baut einen `AuthContext` aus einem Agent-Key |

## Global Constraints

- Branch von `origin/main` (Fetch nur mit `git fetch origin +refs/heads/main:refs/remotes/origin/main`). Git-Mutationen nur über den `git`-Agenten. Commits englisch, Conventional Commits, höchstens 72 Zeichen, Trailer `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>` und `Claude-Session: https://claude.ai/code/session_01JYx6yrB2hSodcXeSkA5mAq`.
- Delta 0 Tools: kein neues MCP-Tool. Bestehende Tools werden erweitert, `python manage.py export_tool_manifest` ausführen, Drift-Gate `mcp_server/tests/test_tool_manifest_drift.py` grün.
- Auto-Assessment: Findings bleiben WARNING-only, blockieren nie eine Baseline, nur Extended-Tier, Default aus, kein Lauf ohne konfigurierten Service-Agent-Key.
- Bestehende Tests mit alten Schrittformen bleiben ohne Änderung grün (Lesen normalisiert).
- Neue tenant-scoped Tabellen brauchen eine RLS-Policy-Migration (`0136_workspace_tier_rls_policy.py` als Muster). Dieser Plan legt keine neue Tabelle an.
- Migrationsnummern: die nächste freie zum Zeitpunkt der Umsetzung. Datenmigrationen mit Trockenlauf-Bericht, idempotent, in Batches.
- Backend-Tests lokal mit `DB_USER` auf dem Superuser. Volle Läufe sequentiell. Frontend: `cd frontend && npx vitest run <Pfad>`, `npx tsc --noEmit -p .`.
- Schließen von Issues erst nach Freigabe durch Daniel.

## Review Focus

- Alte Schrittform geht verloren: LLM-Entwürfe und Frontend senden `{step, expected_result}`, die Normalisierung macht daraus nichts oder doppelte Schritte. Test: Task 2 prüft Legacy → typisiert und die Reihenfolge, auch für leere `expected_result`.
- Roundtrip-Verlust: Datenmigration und Lesen liefern nicht dasselbe. Test: Task 2, `normalize(normalize(x)) == normalize(x)` und Migration zweimal ausführen.
- Eventsturm: Jede Transition löst einen LLM-Aufruf aus, auch bei Massen-Transitionen. Test: Task 3 prüft Drosselung je Artefakt und Inhalts-Hash-Dedupe (kein zweiter Aufruf bei unverändertem Inhalt).
- Fremder Tier: Auto-Assessment läuft im Minimal-Tier. Test: Task 3, `minimal` und `standard` führen keinen Aufruf aus.
- Falsche Identität: Lauf ohne konfigurierten Key schreibt unter einem Nutzer. Test: Task 3, ohne Key kein Lauf und ein Log-Eintrag.
- Kostenschutz: Provider-Fehler führen zu endloser Wiederholung. Test: Task 3, `failed`-Zeile wird geschrieben, kein Retry-Sturm.
- Finding-Flut: QUAL-P1 meldet je Artefakt ohne Bewertung. Test: Task 4, Deckel mit Sammelbefund.

---

### Task 1: #587 belegen und schließen

**Files:**
- Modify: `docs/superpowers/specs/index.md:91` (veraltete Aussage korrigieren)
- Test: vorhandene `application/tests/test_export_promptfoo_configs.py`, `test_prompt_testing_cases.py`

**Interfaces:** Produces: Nachweis jeder Akzeptanzkriterien des Issues, Schließ-Kommentar.

- [ ] **Step 1: Kriterien gegen den Stand prüfen**

Kriterien aus #587: Command `export_promptfoo_configs`, Szenarien als YAML je Slot, Export über den Resolver (`resolve_and_render`), CI-Job mit `--fail-on-error`, Mock-/Echo-Provider für schnelle CI.
Run: `cd backend && DB_USER=<Superuser> python -m pytest application/tests/test_export_promptfoo_configs.py application/tests/test_prompt_testing_cases.py -q`
Expected: PASS. Dazu `sed -n 518,560p ../.github/workflows/ci.yml` für den Job und `ls application/prompt_testing/cases | wc -l` (27).

- [ ] **Step 2: Abdeckung gegen die Slots prüfen**

Jeder registrierte Slot (`application/prompt_slots.py` `get_prompt_slots()`) muss ein Szenario haben, außer den dokumentierten Ausnahmen.
```python
# Falls nicht vorhanden: application/tests/test_prompt_testing_cases.py
def test_every_prompt_slot_has_a_scenario():
    missing = set(get_prompt_slots()) - set(scenario_slot_names())
    assert missing == set(), missing
```
Run: `cd backend && python -m pytest application/tests/test_prompt_testing_cases.py -q` — Expected: PASS. Lücken sind ein Befund: ein Szenario ergänzen (auch der Slot `search_summary` aus Phase D, falls schon gebaut).

- [ ] **Step 3: Veraltete Doku korrigieren**

`docs/superpowers/specs/index.md:91`: "Phase 3 (Promptfoo test infrastructure) is entirely missing" ersetzen durch "umgesetzt: `export_promptfoo_configs`, `application/prompt_testing/cases/`, CI-Job Prompt Regression (#587)".

- [ ] **Step 4: Schließen (nach Freigabe)**

```bash
gh issue close 587 --reason completed --comment "Erledigt. Command export_promptfoo_configs (application/management/commands), 27 Szenarien unter application/prompt_testing/cases/, Export über den Resolver (application/prompt_resolver.py), CI-Job 'Prompt Regression (promptfoo, echo)' in .github/workflows/ci.yml. Der im Issue genannte Blocker (Phase-1-Resolver) existiert. Doku-Stand in docs/superpowers/specs/index.md korrigiert."
```

- [ ] **Step 5: Commit** (über `git`-Agent): `docs(specs): mark promptfoo infrastructure as implemented`

---

### Task 2: #1564 — typisierte Testschritte

**Files:**
- Create: `backend/application/test_steps.py`
- Create: `backend/persistence/migrations/<nächste>_normalize_testcase_steps.py`
- Modify: `backend/application/test_service.py:364`, `backend/application/ai_derivation_service.py:173,1255-1275`, `backend/rest_api/serializers.py` (TestCase-Serializer), `backend/mcp_server/tools/tests.py:495,1017-1056,1461-1475`, `backend/application/export_service.py:152`
- Modify: `frontend/src/components/TestCaseEditors/TestCaseArtifactForm.tsx` und das Steps-Widget
- Test: `backend/application/tests/test_test_steps.py`, `backend/rest_api/tests/test_testcase_steps_api.py`, `backend/mcp_server/tests/test_testcase_steps_schema.py`, `backend/persistence/tests/test_normalize_testcase_steps_migration.py`, Frontend-Test am Widget

**Interfaces:**
- Consumes: `TestCase.steps` (JSONField), MCP-Tools `test.create`, `test.update`, `test.derive_from_requirement`.
- Produces:
  - `StepType` (`given|when|then|and|but`) als `str`-Enum, `TestStep = TypedDict("TestStep", {"id": str, "step_type": StepType, "text": str})`
  - `normalize_steps(raw: object) -> list[TestStep]`: akzeptiert typisierte Schritte, Legacy `{"step": str, "expected_result": str}` und freie Dicts. Legacy `{"step": A, "expected_result": B}` ergibt `when` mit A und, wenn B nicht leer ist, direkt danach `then` mit B. Jede Zeile bekommt eine stabile `id` (UUID4, bei Neuberechnung aus Inhalt und Position stabil gehalten: `uuid5(NAMESPACE, f"{testcase_id}:{index}:{text}")`). Unbekannte Eingaben: `ValidationError` mit Pfad, nicht stilles Verwerfen.
  - `validate_steps(steps: list[TestStep]) -> None` (nicht leerer `text`, höchstens 200 Schritte, Text höchstens 2000 Zeichen, erster Schritt kein `and`/`but`)
  - `steps_to_gherkin(steps: Sequence[TestStep], *, title: str = "") -> str`
  - Ausgabe in REST/MCP: `steps` immer typisiert, zusätzlich Feld `steps_legacy_normalized: bool` (nur wenn beim Lesen normalisiert wurde).

- [ ] **Step 1: Failing Tests für `test_steps.py`**

```python
def test_legacy_pair_becomes_when_then():
    out = normalize_steps([{"step": "Open page", "expected_result": "Page visible"}])
    assert [s["step_type"] for s in out] == ["when", "then"] and out[0]["text"] == "Open page"

def test_legacy_without_expected_result_yields_only_when(): ...
def test_typed_steps_pass_through_unchanged(): ...
def test_ids_are_stable_across_calls(): assert normalize_steps(X, testcase_id=T) == normalize_steps(X, testcase_id=T)
def test_normalize_is_idempotent(): assert normalize_steps(normalize_steps(X)) == normalize_steps(X)
def test_unknown_shape_raises_with_path(): with pytest.raises(ValidationError, match=r"steps\[1\]"): normalize_steps([{"foo": 1}, {"x": 1}])
def test_validate_rejects_leading_and(): ...
def test_gherkin_export_keeps_order_and_keywords(): assert steps_to_gherkin(S).splitlines()[1].startswith("    Given ")
```
Run: `cd backend && python -m pytest application/tests/test_test_steps.py -q` — Expected: FAIL.

- [ ] **Step 2: `test_steps.py` implementieren**

Datei `application/test_steps.py` mit den Signaturen oben. Gherkin-Ausgabe: `Scenario: <title>` und je Schritt eingerückt das englische Schlüsselwort (`Given`, `When`, `Then`, `And`, `But`). Ein Parser Gherkin → Schritte gehört nicht zu diesem Plan (Vorschlag V8).

- [ ] **Step 3: Tests grün**

Run: `cd backend && python -m pytest application/tests/test_test_steps.py -q` — Expected: PASS.

- [ ] **Step 4: Schreibpfade und Schnittstellen**

`test_service.py:364`: `steps` vor dem Speichern durch `normalize_steps` und `validate_steps` schicken (alte MCP-Clients senden weiter `{step, expected_result}` und werden akzeptiert und normalisiert). `ai_derivation_service.py`: Prompt und Parser liefern typisierte Schritte (`given/when/then`), die alte Ausgabeform bleibt als Eingabe akzeptiert. Serializer: Lesen über `normalize_steps`, Schreiben validiert. MCP: `steps` im Schema von `type: object` auf ein Objekt mit `properties {id, step_type (enum), text}` und `required [step_type, text]` ändern, die Beschreibung nennt die alte Form als weiter akzeptiert. Manifest exportieren. Export-/Diff-/Indexer-Leser nutzen `normalize_steps` beim Lesen, ihre Ausgabeformate ändern sich nicht (Diff vergleicht nach Normalisierung).

- [ ] **Step 5: Tests für REST und MCP**

```python
def test_rest_returns_typed_steps_for_legacy_row(client, legacy_testcase): ...
def test_rest_rejects_unknown_step_type(client, testcase): assert r.status_code == 400 and "steps[0].step_type" in r.json()["error"]["message"]
def test_mcp_accepts_legacy_and_typed_steps(...): ...
def test_ai_derive_returns_typed_steps(mock_llm): ...
def test_diff_between_legacy_and_typed_version_is_empty_when_equal(...): ...
```
Run: `cd backend && python -m pytest rest_api/tests/test_testcase_steps_api.py mcp_server/tests/test_testcase_steps_schema.py application/tests -k "steps" -q && python -m pytest mcp_server/tests/test_tool_manifest_drift.py -q`
Expected: PASS.

- [ ] **Step 6: Datenmigration**

Migration `normalize_testcase_steps` (`RunPython`, Batches von 500, `iterator()`): schreibt `steps` in typisierter Form, wenn `normalize_steps` etwas ändert. Rückwärts: nicht umkehrbar (`noop`), Vermerk im Docstring. Vorher Trockenlauf: Management-Command `normalize_testcase_steps --dry-run` zählt Zeilen nach Form (typisiert, legacy, unbekannt) und listet unbekannte Zeilen mit ID statt sie zu überschreiben.
Run: `cd backend && python -m pytest persistence/tests/test_normalize_testcase_steps_migration.py -q` (zweimal ausführen lassen, gleiche Zeilenzahl) — Expected: PASS. Unbekannte Zeilen bleiben unverändert.

- [ ] **Step 7: Frontend-Widget**

`TestCaseArtifactForm.tsx` und das Steps-Widget zeigen je Schritt eine Auswahl `step_type` (Given/When/Then/And/But, i18n DE/EN) und ein Textfeld. Beim Laden alter Daten zeigt das Widget die normalisierte Form. Die Übersetzung `steps_data` ↔ `steps` bleibt an der einen Stelle der Datei (siehe Kopfkommentar). `data-testid` je Zeile und Auswahl, Tokens aus `styles/tokens.css`.
Run: `cd frontend && npx vitest run src/components/TestCaseEditors && npx tsc --noEmit -p . && npx eslint src/components/TestCaseEditors`
Expected: PASS.

- [ ] **Step 8: Commit** (über `git`-Agent, zwei PRs: Backend inkl. Migration, Frontend): `feat(testcases): typed Given/When/Then steps with legacy normalization`

---

### Task 3: #1578 — Ereignis, Konsument, Flag, Identität

**Files:**
- Modify: `backend/workflow/services.py:248` (`transition`), die entitätsspezifischen `transition_status` nur, wenn sie `workflow.services.transition` nicht aufrufen
- Modify: `backend/persistence/models.py:4488` (`QualityAssessment.Trigger` um `auto_transition`, `auto_create`, `auto_periodic`), Migration (Choices)
- Create: `backend/application/quality_auto_assess.py`
- Modify: `backend/application/tasks.py` (Celery-Aufgabe), `backend/reqogniloom/settings.py` (Flag, Key-Referenz, Drosselung), `.env.example`
- Test: `backend/workflow/tests/test_transition_emits_event.py`, `backend/application/tests/test_quality_auto_assess.py`

**Interfaces:**
- Consumes: `DomainEventBus.publish` (Outbox, Muster in `trace_link_service.py` für `TRACE_LINK_CREATED`), Konsumentenmuster `application/artifact_index_projector.py`, `QualityService.assess(ctx, workspace_id, entity_type, entity_id, *, force, trigger)`, `AuthContext`-Aufbau aus einem Agent-Key (`application/tasks.py:195-235`).
- Produces:
  - Ereignis `WORKFLOW_TRANSITIONED` mit Nutzlast `{item_type, item_id, workspace_id, from_state, to_state}`.
  - `QualityAutoAssessor.on_event(event) -> None` und `QualityAutoAssessor.run_for(entity_type: str, entity_id: UUID, workspace_id: UUID, trigger: str) -> str` (Rückgabe: `assessed|skipped:<grund>|failed`). Gründe: `flag_off`, `tier_not_extended`, `no_agent_key`, `unchanged_hash`, `throttled`, `type_not_assessable`.
  - Einstellungen: `QUALITY_AUTO_ASSESS_ENABLED` (Default `false`), `QUALITY_AUTO_ASSESS_AGENT_KEY_ID` (UUID, je Mandant über die bestehende Tenant-Konfiguration, falls dort vorgesehen, sonst als globale Einstellung für Einzelmandanten-Betrieb), `QUALITY_AUTO_ASSESS_MIN_INTERVAL_SECONDS` (Default 3600 je Artefakt).

- [ ] **Step 1: Failing Tests für das Ereignis**

```python
def test_transition_publishes_workflow_transitioned(workflow_item, ctx, event_capture):
    transition(workflow_item.id, "Approved", "ok", ctx, workspace_id=WS)
    ev = event_capture.one(EventType.WORKFLOW_TRANSITIONED)
    assert ev.payload["to_state"] == "Approved" and ev.payload["item_type"] == "Requirement"

def test_failed_transition_publishes_nothing(...): ...
def test_event_is_published_inside_the_transaction(...): ...   # Rollback => kein Ereignis in der Outbox
```
Run: `cd backend && python -m pytest workflow/tests/test_transition_emits_event.py -q` — Expected: FAIL.

- [ ] **Step 2: Ereignis emittieren**

In `workflow.services.transition` nach der erfolgreichen Zustandsänderung, innerhalb derselben Transaktion, per `DomainEventBus.publish(AuditableOperationOccurred(...))` nach dem Muster der TraceLink-Ereignisse. Prüfen, welche `transition_status`-Pfade (`adr`, `risk`, `change_request`, `document`, `work_item`) `workflow.services.transition` nicht durchlaufen, und sie am selben Punkt anbinden oder ausdrücklich als nicht bewertbar kennzeichnen (nur Typen aus `SOURCES` der Qualitätsbewertung sind relevant: Requirement, Adr, Risk, TestCase).

- [ ] **Step 3: Failing Tests für den Konsumenten**

```python
def test_flag_off_skips(...):               assert assessor.run_for(...) == "skipped:flag_off"
def test_minimal_and_standard_tier_skip(...): assert "skipped:tier_not_extended" ...
def test_no_agent_key_skips_and_logs(...):  assert result == "skipped:no_agent_key"
def test_assess_runs_under_agent_key_context(...): assert recorded_ctx.actor_type == "agent"
def test_unchanged_content_is_not_reassessed(...): assert result == "skipped:unchanged_hash"
def test_throttle_blocks_second_call_within_interval(...): ...
def test_provider_failure_writes_failed_row_without_retry_storm(...): assert retry_count == 0
def test_findings_remain_warning_only(...): ...
```
Run: `cd backend && python -m pytest application/tests/test_quality_auto_assess.py -q` — Expected: FAIL.

- [ ] **Step 4: Konsumenten implementieren**

`quality_auto_assess.py`: Handler registriert sich wie `artifact_index_projector.py` am Bus, filtert auf `WORKFLOW_TRANSITIONED` und die Erzeugungs-Ereignisse der bewertbaren Typen (`*_CREATED`). Reihenfolge der Prüfungen: Flag, Typ, Tier (`presets.services.get_preset(workspace_id)`, Extended; Zugriffsweg gegen `presets/` bestätigen), Agent-Key (Kontext wie `application/tasks.py:195-235`, kein Key: kein Lauf), Drosselung (Cache-Schlüssel je Artefakt), dann `QualityService.assess(...)` (der Inhalts-Hash der Bewertung liefert den Dedupe, `cached=True` zählt als `unchanged_hash`). Ausführung als Celery-Aufgabe in `application/tasks.py`, ohne automatischen Retry bei Provider-Fehlern (der Service schreibt bereits eine `failed`-Zeile).

- [ ] **Step 5: Tests grün**

Run: `cd backend && python -m pytest workflow/tests/test_transition_emits_event.py application/tests/test_quality_auto_assess.py application/tests -k "quality" -q`
Expected: PASS, bestehende Qualitätstests ohne Änderung.

- [ ] **Step 6: Commit** (über `git`-Agent, zwei PRs: Ereignis, Konsument): `feat(quality): emit WORKFLOW_TRANSITIONED and auto-assess behind a flag`

---

### Task 4: #1578 — Periodik und Folgepunkte

**Files:**
- Modify: `backend/application/tasks.py`, `backend/reqogniloom/settings.py` (`CELERY_BEAT_SCHEDULE`, `:1151`)
- Modify: `backend/traceability/audit/rules/quality_score.py` (QUAL-P1-Deckel)
- Modify: `backend/mcp_server/tools/quality.py` und den Rate-Limit-Pfad (Parität zu REST `rest_api/quality_views.py`)
- Modify: `backend/application/quality_service.py` (`history`, `latest_for`, Item-Level-Prüfung)
- Test: `backend/application/tests/test_quality_auto_assess_sweep.py`, `backend/traceability/audit/tests/test_qual_p1_cap.py`, `backend/mcp_server/tests/test_quality_assess_rate_limit.py`, `backend/application/tests/test_quality_item_permission.py`

**Interfaces:**
- Consumes: `QualityAutoAssessor.run_for` (Task 3), Hilfen für Item-Level-Rechte (`_assert_item_write_permission` in `test_service.py`, Issue #1716).
- Produces:
  - Celery-Aufgabe `application.quality_auto_assess_sweep(tenant_id: str) -> dict` (`{"assessed": int, "skipped": int, "failed": int}`), Beat-Intervall `QUALITY_AUTO_ASSESS_INTERVAL_MINUTES` (Default 1440), höchstens `QUALITY_AUTO_ASSESS_SWEEP_BATCH` (Default 50) Artefakte je Lauf, älteste Bewertung zuerst.
  - QUAL-P1 meldet höchstens `QUAL_P1_MAX_FINDINGS` (Default 50) Einzelbefunde je Lauf plus einen Sammelbefund "weitere N Artefakte ohne Bewertung".
  - `quality.assess` (MCP) nutzt dieselbe Rate-Konfiguration wie REST.
  - `QualityService.history` und `latest_for` filtern Ergebnisse nach Leserecht auf das Artefakt.

- [ ] **Step 1: Failing Tests**

```python
def test_sweep_respects_batch_and_age_order(...): assert result["assessed"] <= 50
def test_sweep_skips_when_flag_off(...): ...
def test_qual_p1_is_capped_with_summary_finding(workspace_with_300_unassessed): assert len(findings) == 51 and findings[-1].rule_id == "QUAL-P1" and "250" in findings[-1].message
def test_mcp_quality_assess_is_rate_limited_like_rest(...): ...
def test_history_hides_assessments_of_unreadable_artifacts(...): ...
```
Run: `cd backend && python -m pytest application/tests/test_quality_auto_assess_sweep.py traceability/audit/tests/test_qual_p1_cap.py mcp_server/tests/test_quality_assess_rate_limit.py application/tests/test_quality_item_permission.py -q` — Expected: FAIL.

- [ ] **Step 2: Implementieren**

Sweep über `QualityAutoAssessor.run_for(..., trigger="auto_periodic")`. Beat-Eintrag nur registrieren, wenn das Feature-Flag an ist (Muster der Dream-Aufgabe in `settings.py:1121-1142`: die Aufgabe liest die Einstellung zusätzlich selbst und gibt `disabled` zurück). Deckel im Audit-Regelmodul. Rate-Limit-Parität: den vorhandenen Mechanismus aus `admin_ops/rate_limits.py` verwenden, keinen neuen Schlüssel erfinden. Item-Level-Prüfung nach dem Muster der Schreibprüfung in `test_service.py`.

- [ ] **Step 3: Tests grün, Manifest, Lint**

Run: `cd backend && python -m pytest application/tests/test_quality_auto_assess_sweep.py traceability/audit/tests/test_qual_p1_cap.py mcp_server/tests/test_quality_assess_rate_limit.py application/tests/test_quality_item_permission.py mcp_server/tests/test_tool_manifest_drift.py -q`
Expected: PASS.

- [ ] **Step 4: Commit** (über `git`-Agent): `feat(quality): periodic auto-assessment sweep with capped QUAL-P1`

---

### Task 5: Dokumentation und Schließen

**Files:**
- Modify: `.env.example`, `deploy/README.md` (Flag, Agent-Key, Intervall, Drosselung, Kostenhinweis)
- Modify: `docs/api/MCP-SURFACE.md` (Schrittschema, `steps_legacy_normalized`)

**Interfaces:** Consumes: Tasks 2 bis 4 gemergt.

- [ ] **Step 1: Doku und Beispielwerte**

Alle neuen Einstellungen mit Default und Wirkung. Der Hinweis: Auto-Assessment erzeugt LLM-Kosten, Default aus, braucht den Service-Agent-Key (Anlage über die API-Key-Verwaltung, `principal_type=agent`).

- [ ] **Step 2: Schließen (nach Freigabe)**

```bash
gh issue close 1564 --reason completed --comment "<Tabelle: Schrittmodell, Normalisierung, Migration, REST/MCP/Frontend, PR-Nummern>"
gh issue close 1578 --reason completed --comment "<Tabelle: Ereignis, Konsument, Flag, Service-Agent-Key, Sweep, QUAL-P1-Deckel, Rate-Parität, Item-Permission, PR-Nummern>"
```

- [ ] **Step 3: Endstand**

Run: `for n in 587 1564 1578; do gh issue view $n --json state --jq .state; done`
Expected: dreimal `CLOSED`.

---

## Self-Review

- **Abdeckung:** #587 Task 1. #1564 Task 2 (Modell, Normalisierung, Migration, Schnittstellen, Frontend, Gherkin-Export). #1578 Tasks 3 und 4 (alle sechs Akzeptanzkriterien: Ereignis, Flag, Periodik mit Dedupe und Drosselung, WARNING-only, Rate-Parität und Item-Permission, QUAL-P1-Deckel). Entscheidung 10b (Service-Agent-Key) in Task 3.
- **Bewusste Grenzen:** Gherkin-Parser (Text → Schritte) und Schritt-Ergebnisse im TestRun sind Vorschlag V8 und nicht Teil dieses Plans. Das Frontend-Widget zeigt Schritttypen, ein Umbau auf Given/When/Then-Blöcke bleibt aus.
- **Unsicher, im Step zu bestätigen:** (a) Zugriffsweg auf den Tier (`presets.services.get_preset`), (b) welche `transition_status`-Pfade `workflow.services.transition` nicht durchlaufen, (c) wo je Mandant der Service-Agent-Key konfiguriert wird (Tenant-Einstellung oder global), (d) Legacy-Mapping `step`+`expected_result` → `when`+`then` als Standard, im Review der PRs sichtbar machen.
- **Typkonsistenz:** `QualityAutoAssessor.run_for` (Task 3) wird in Task 4 vom Sweep aufgerufen, `trigger`-Werte stehen in beiden Tasks gleich (`auto_transition`, `auto_create`, `auto_periodic`). `normalize_steps` (Task 2) ist der einzige Normalisierer, alle Leser rufen ihn.
- **Nicht ausgeführt:** Kein Befehl dieses Plans lief. Dateipfade und Signaturen stammen aus der Lektüre von beta.29.
