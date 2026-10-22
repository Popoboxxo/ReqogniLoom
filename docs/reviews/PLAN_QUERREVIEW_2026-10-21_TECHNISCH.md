---
type: REVIEW
scope: "Querreview Umsetzungspläne A–G (2026-10-21), technisch"
status: open
date: 2026-10-21
author_agent: code-reviewer
basis: "docs/superpowers/specs/2026-10-21-backlog-umsetzungsplaene-design.md; docs/plans/2026-10-21-plan-{a..g}-*.md; Arbeitsbaum b175c970 (= origin/main)"
---

# Technischer Querreview der Pläne A–G

## Zusammenfassung

1. Die Pläne sind einzeln sorgfältig, plan-übergreifend aber **nicht integriert**: Fünf Pläne verweisen auf einen „Plan-Index“, der Migrationsnummern und Tool-Zähler konsolidieren soll. Diesen Index gibt es nicht.
2. **Migrationen kollidieren hart**: `persistence 0116–0118` ist dreifach belegt (A/B/G), `link_types 0010` und `attribute_definitions 0010` sind doppelt belegt (B/G). Die Reihenfolge `auth_tenancy` C↔E widerspricht der Wellenfolge.
3. **Promptfoo-Kopplung A↔D ist nicht lauffähig**: A legt Case-Dateien „neu“ an, die D schon anlegt. Die A-Assertions sind im D-Harness nicht herstellbar. A merged absichtlich einen roten Case gegen den Required Check aus D2.5. B fügt 4 Slots ohne Case-Dateien hinzu (D-Test ist dann rot).
4. Gemeinsame Bausteine sind meist eindeutig zugeordnet (Q1→C, HARD_OFF/Port→A, ETag→E, uid/Soft-Delete→G). Widersprüche bestehen bei C1↔G4.3 (Button-Geometrie), beim Subtyp-Mechanismus B3-T2↔F2, bei der Memory-Workspace-Ebene außerhalb von Q1 und beim MCP-Zähler bzw. Doku-Guard.
5. Ergebnis: **30 Befunde** (kritisch 2, hoch 7, mittel 12, niedrig 9). 60 Stichproben `datei:zeile`, davon 55 korrekt, 5 Fehlbelege. Die konfliktfreie Gesamtvergabe der Migrationen steht in §3.

Hinweis zur Signalisierung: In der Spalte „Schwere“ gilt: kritisch/hoch = **blockierend** (vor Umsetzungsstart korrigieren), mittel = blockierend nur für die betroffene Welle, niedrig = advisory. „Typ“: V = verifizierbar (Grep/Read), U = Urteil (Begründung angegeben).

---

## 1. Befundtabelle

| ID | Schwere | Typ | Plan/Task | Beleg | Auswirkung | Korrekturvorschlag (Zielformulierung) |
|---|---|---|---|---|---|---|
| QR-T01 | kritisch | V | A T-A0-5, B B5-T1/B6-T1, G G1.3/G2.2; Referenz „Plan-Index“ in A §14, B Mig.-Res., C T-C2-4, F §Mig., G §13 | A: `persistence/0116_embedding_model_columns`; B: `0116_quality_assessment`, `0117_…rls`, `0118_milestone`, `0119_…rls`; G: `0116_entity_workspace_fk_backfill`, `0117_uid_workspace_unique_constraints`, `0118_requirement_list_index`. Unter `docs/plans/` liegt kein Index-Dokument (`ls docs/plans`). | Drei Pläne erzeugen dieselben Dateinamen. Zwei Leaf-Nodes führen zu `makemigrations --check` rot bzw. `migrate` bricht mit „Conflicting migrations“ ab. Die Konsolidierung ist an ein Dokument delegiert, das es nicht gibt. | Verbindliche Vergabe nach §3 dieses Berichts in alle Pläne übernehmen. Regel ergänzen: „Die Nummer wird beim Merge vergeben (max+1 der App); die Reservierung legt nur die Reihenfolge fest. `dependencies` zeigen auf die letzte gemergte Migration.“ §3 dieses Berichts gilt als Plan-Index. |
| QR-T02 | kritisch | V | B B1-T1, B2-T1, B3-T3; G G1.4; F F1.1-T2/F2-T3/F3-T3 | B: `attribute_definitions/0010_requirement_interview_elicits_se_fields`, `link_types/0010_seed_validates_link_type`, `0011_seed_performs…`. G: `link_types/0010_workspace_definition_workspace_fk`, `attribute_definitions/0010_workspace_definition_workspace_fk`. F: „nach Plan B 0011 und Plan G 0010“ (F F1.1-T2), Kette `0012–0014`. | Zwei Apps haben doppelte `0010`. Die F-Kette setzt auf eine Zählung auf, die es so nicht gibt (B belegt 0010+0011, G belegt 0010). G läuft in Welle 0 und belegt 0010 zuerst. | G behält `0010` in beiden Apps (Welle 0). B nimmt `attribute_definitions 0011`, `link_types 0011/0012`. F nimmt `link_types 0013/0014/0015`. Der B-Seed (`0011`) läuft nach der FK-Umstellung: Die B-Migrationstests legen echte `Workspace`-Zeilen an (kein `uuid4()`). |
| QR-T03 | hoch | V | C T-C2-1 (Welle 1), E E3.1 (Welle 3) | C: „`0030` hängt an … `0027` oder, falls Plan E/E3 vorher gemergt, `0028_user_mfa`“, „`0029` bleibt frei (Puffer für Plan E)“. Planbasis §3: Q1 Welle 1, E3 Welle 3. | E3 kommt laut Wellen **nach** C. Die Annahme „0028 vorher“ trifft nicht zu. Es entsteht eine Lücke 0028/0029 und eine E-Migration `0028`, die von `0032/0033` abhängen müsste (Name ≠ Reihenfolge, Verwirrung bei Rollback-Befehlen). | C: `0028_preferencevalue`, `0029_preferencevalue_rls`, `0030_backfill_show_readable_ids`. E: `0031_user_mfa` (oder max+1 beim Merge). C-Contract `drop_…show_readable_ids` erhält die nächste freie Nummer ≥ 1 Release später. |
| QR-T04 | hoch | V | A PR-A3/PR-A5/PR-A11/PR-A19, C PR-C3/PR-C7, E P3-2, F PR-F9/F14/F22, G G1.3 TDD 5, PR 3, PR 7 | z. B. G1.3: „`0117`→`0115`→`0117`“; G PR 7: „`migrate persistence 0117`“; A PR-A11: „Migration bis 0011 zurück“; C PR-C3: „`migrate auth_tenancy 0027` (bzw. 0028)“ | Nach jeder Neuvergabe (QR-T01–T03) zeigen Rollback- und Test-Befehle auf falsche oder fremde Migrationen. Ein Rollback auf eine fremde Nummer kann Migrationen eines anderen Plans zurückdrehen. | Rollback- und Test-Befehle immer über den **Namen** und „Vorgänger“ formulieren, z. B. `migrate persistence <name der vorherigen gemergten Migration>`. Tests nutzen `MigrationExecutor` mit `loader.graph.leaf_nodes()` bzw. dem Namen statt einer festen Nummer. |
| QR-T05 | hoch | V/U | A T-A1-8 ↔ D D2.1/D2.2 | A: „neu `…/cases/bundle_compression.yaml`, `need_to_sysreq.yaml`, `interview.chat_turn.yaml`“. D2.1: Case-Datei für **alle 23 Slots**, Test `test_every_slot_has_exactly_one_case_file`. `interview.chat_turn` ist Registry-Slot (`prompt_slots.py:61`). D2.2 rendert im Nil-Tenant mit explizit übergebenem `memory_context`. | Die A-Dateien existieren nach D2 bereits, „neu anlegen“ kollidiert. Die A-Assertion „`memory_top_k=1` → genau eine Zeile `- [workspace]`“ setzt Auto-Injektion mit echten Memory-Treffern voraus. Im D-Harness gibt es weder Tenant-Daten noch ein Backend; ein explizites `memory_context` umgeht `memory_top_k`. Der Test ist so nicht herstellbar. | A T-A1-8: „**Erweitert** die bestehenden D2-Case-Dateien um Szenarien.“ Top-k/Format-Prüfungen gehören nicht in Promptfoo, sondern in `application/tests/test_prompt_resolver.py` (echte DB-Fixtures mit MemoryEntry). Promptfoo prüft nur: HARD_OFF-Slot rendert kein `Workspace context:` und `{memory_*}` ist aufgelöst. |
| QR-T06 | hoch | V | A PR-A9 → PR-A10; D D2.5 | A T-A1-8 DoD: „Die drei Cases laufen vor T-A1-1 … als Baseline: `bundle_compression` ist rot“. PR-A9 merged vor PR-A10. D2.5: `prompt-regression` ist Required Check. | PR-A9 kann nicht gemergt werden (Required Check rot), oder der Check wird umgangen. Beides bricht das Q2-Gate. | Den roten Baseline-Nachweis nur im PR-Text dokumentieren. Den `bundle_compression`-Case **im selben PR wie T-A1-1** (PR-A10) einführen bzw. scharf schalten. PR-A9 enthält nur Cases, die heute grün sind. |
| QR-T07 | hoch | V | D D2.1/D2.2 ↔ B B5-T2 | D: Exit 1 bei „`n<23`, `m>0`“, Gate G1 „`23/23 slots`“. B5-T2: +4 Slots `quality_*` („27 Slots“). B nennt keine Case-Dateien. | Mit dem Merge von PR-B15 werden `test_every_slot_has_exactly_one_case_file` (set-1-core) und `export_promptfoo_configs --check` rot. Die Zahl 23 ist hart codiert. | D2.2: Soll-Zahl = `len(get_prompt_slots())`, nicht 23, Ausgabezeile `n/<len>`. B5-T2 erhält die Pflicht-Datei `prompt_testing/cases/quality_{requirement,adr,testcase,risk}.yaml` (je 1 Szenario, `not-contains: "{memory_context}"`). Allgemeine Regel in jeden Plan mit neuen Slots: „Neuer Slot ⇒ Case-Datei im selben PR.“ |
| QR-T08 | hoch | V | A T-A3-1/3, T-A4-3/5; B B2-T2/T3, B5-T3, B6-T2; C T-C2-4; E E1.3; F F1.2-T1/T2, F4.2, F4.4, F2-T6, F3-T6 | `export_tool_manifest.py:102` schreibt nur das Manifest. `docs/agent-templates/test_doc_surface_consistency.py` (CI `agent-templates-test`) prüft die Tool-Zahl in `README.md`, `docs/api/MCP-SURFACE.md`, `docs/clients/antigravity(.de).md`, `clients/registry.yaml`. C T-C2-4 behauptet, MCP-SURFACE.md würde per Export aktualisiert. Absolute Zahlen: A „249“, B „250, 40 Präfixe“ bzw. „256“, E „bleibt 248“. | Jeder Tool-PR macht `agent-templates-test` rot. Die absoluten Zahlen der Pläne widersprechen sich je nach Merge-Reihenfolge. Summe aller Pläne: 248 + 1 (A) + 2 + 6 (B) + 4 (C) + 4 + 9 + 8 (F) = **282 Tools**, **44 Präfixe** (+quality, milestone, preference, document, work_item). | Plan-übergreifende DoD-Zeile für Tool-PRs: „`export_tool_manifest` + Zahl in README.md, MCP-SURFACE.md, antigravity(.de).md, clients/registry.yaml (+ `render.py`) + `.meta-config/project.yaml`; Pläne nennen nur Deltas, keine Absolutzahl.“ Tool-PRs merge-seriell (eine Queue über alle Pläne). |
| QR-T09 | hoch | V/U | C T-C1-1 (Check `button-geometry-off-token`, E2E ≤ 3 Höhen) ↔ G G4.3 | C: Verstoß = `height/min-height ≠ var(--btn-h-*)`. G4.3: `.deleteButton width/height: var(--target-min)` (24 px), `.copyButton min-height: var(--target-min)`. G-DoD: „Design-System-Ratchet unverändert grün“. G4.3 läuft laut beiden Plänen **nach** C1. | G4.3 erzeugt neue Fingerprints unter dem C1-Check und eine vierte Button-Höhe (24 px) je Route. Ratchet und E2E-Gate werden rot. Der Widerspruch ist in keinem Plan benannt. | C1-Regel um `var(--target-min)` als zulässige Höhe für `.btn-icon`-artige Icon-Buttons erweitern. Alternativ ein Token `--btn-h-xs: 24px` in die Höhen-Skala aufnehmen und das E2E-Gate als „≤ 3 Höhen ohne Icon-Buttons“ formulieren. G4.3 nutzt dann genau dieses Token. Entscheidung durch `ux-designer`, vor PR-C2. |
| QR-T10 | mittel | V/U | B B3-T2 ↔ F F2 (`evidences` kind-gebunden) | B3-T2: „`source_subtype`/`target_subtype` nur zulässig, wenn `*_type` = `ArchitectureElement`, sonst ValidationError“. F2: kind-Bindung „über den Subtyp-Mechanismus aus B3-T2, erweitert auf Document“. Bestand: `catalog.py:40-48` `normalize_artifact_type("TestCase:unit")` (Konvention `Typ:Subtag`). | Zwei konkurrierende Subtyp-Repräsentationen. F2 muss B-Validierung wieder öffnen (Vertragsänderung am Katalog-Schema zweimal). | B3-T2 generisch formulieren: Subtyp erlaubt für jeden Typ mit registriertem Subtyp-Feld (`ArchitectureElement.element_type`, später `Document.kind`). Bestehende `Typ:Subtag`-Notation entweder als Wire-Format übernehmen oder ausdrücklich ablösen (Doku in `catalog.py`). |
| QR-T11 | mittel | U | A T-A1-3/T-A1-4 ↔ C Q1 | Planbasis Q1: „3-Ebenen-Präferenzdienst … REST+MCP … Nutzer: A1 Memory-Schalter“. A: Workspace-Ebene in `WorkspaceMemorySettings` (Migration memory 0012), „MCP: keine neuen Tools … Sonst gilt nur REST“. C-Register: `memory.disabled_slots` nur `global, user`. Zusätzlich `/memory/me/settings/` (A) **und** `users/me/preference-values/` (C) schreiben denselben Q1-Schlüssel. | Die Memory-Schalter auf Workspace-Ebene sind über MCP nicht erreichbar. Das widerspricht Q1 „REST+MCP“ und ist nicht als Entscheidungs-Konflikt ausgewiesen. Zwei Schreibpfade für denselben User-Wert erzeugen Drift-Risiko bei Validierung und Audit. | Entweder Workspace-Ebene als Q1-Schlüssel (`memory.disabled_slots` levels `global, workspace, user`, `memory.allow_user_opt_out` workspace) mit `WorkspaceMemorySettings` als Fassade, oder als „Entscheidung nötig E5“ in Plan A ausweisen. `/memory/me/settings/` wird als dünne Fassade über `PreferenceService.set_level` spezifiziert (eine Validierung). |
| QR-T12 | mittel | V | E E2.7 (Welle 0) ↔ A T-A4-5/T-A4-7, B B5-T3/B6-T2, C T-C2-3, F F1.2-T1/F4.2/F4.4, G G1.5 | E2.7: „Neuer Eintrag ⇒ Fehlschlag; verschwundener Eintrag ⇒ Fehlschlag (shrink)“. Neue Views ohne explizite Serializer (z. B. F4.4 `rollback-*`-Actions, A Webhook-View) oder Schema-Ergänzungen (G1.5 `extend_schema` auf 18 `destroy`, F1.2-T1 `DiagramResponseSerializer`). | Ab Welle 0 macht jeder spätere REST-PR die Ratchet rot, entweder durch neue Warnungen oder durch nicht nachgezogene Shrinks. `openapi_warning_baseline.json` wird zur Konfliktdatei aller Pläne. | Plan-übergreifende DoD-Zeile: „Neue Views mit `serializer_class` oder `@extend_schema`; PR aktualisiert `openapi_warning_baseline.json` (nur Shrink); Merge seriell.“ In A/B/C/F/G je Task mit neuer Route aufnehmen. |
| QR-T13 | mittel | V | B B6-T1/B6-T2 ↔ E E2.5 | B6-T2: „ETag/If-Match wie andere mutable Typen (Plan E WP E2)“. B6-T1-Felder ohne `version`. E2.5/RB-07: `compute_etag` fällt ohne `version` auf einen Zeitstempel zurück, dann liefert jedes `If-Match` 412. | Milestone-PATCH mit gültigem ETag liefert 412. | B6-T1: `version = PositiveIntegerField(default=1)` + `expected_version` im Service, `etag_supported=True`. Alternativ `etag_supported=False` (ehrliche 412-Zusage gemäß E2.6). |
| QR-T14 | mittel | V | E E1.2/E2.3/E2.4/E2.5 ↔ G G1.5/G2.1/G5.3 (alle `rest_api/views.py`) | E (v): „Merge-Reihenfolge E2 vor G1 oder Rebase“. G-Matrix: G1.5 „parallel zu G1.1–G1.4, G3.x“, keine Erwähnung von E2.x. Beide Welle 0. | Gleichzeitige Arbeit an `partial_update`/`destroy`/`retrieve` derselben ViewSets führt zu Merge-Konflikten und zum Risiko, dass ETag-Zweige oder `include_deleted` verloren gehen. | G-Matrix ergänzen: „G1.5 nach Plan E P1-2 (E2.4/E2.5) mergen; G2.1 nach G1.5.“ Welle-0-Merge-Queue für `views.py`: E P1-1 → E P1-2 → E P1-4 → G PR 5 → E P1-3/P1-7. |
| QR-T15 | mittel | U | A T-A0b-3/T-A0b-6 | „Altspalten bleiben bis T-A0b-6“, „Ist der neue Pfad defekt, liefern die flachen Felder weiter aus den Altspalten“. Ein Schreibpfad für die Altspalten nach Migration 0011 ist nicht spezifiziert. | Wenn neuer Code nur `backend_options` schreibt, liest ein Code-Rollback (Revert PR-A5 ohne Rückmigration) veraltete Altspalten. Settings regressieren still; die expand/contract-Zusage ist nicht eingelöst. | T-A0b-3: „**Dual-Write**: Jeder PUT schreibt `backend_options` und die Altspalten, bis T-A0b-6 gemergt ist; Test `test_put_dual_writes_legacy_columns`.“ |
| QR-T16 | mittel | V | A §7 P3, §9, T-A2-1 | §7: „PR-A17 (Entkopplung) wird erst ausgerollt, wenn PR-A19 (Backfill) gelaufen ist“. Tabelle: PR-A17 = Collection v2, PR-A18 = Indexer+Backfill, PR-A19 = Hooks, PR-A21 = Entkopplung. §9: „PR-A21 erst nach … PR-A19 und PR-A18“. T-A2-1: „zusammen mit T-A2-5“. | Die Rollout-Regel nennt falsche PRs. Eine Entkopplung vor dem Backfill (leere Collection) bleibt möglich. | §7 Rollout-Regel: „PR-A21 wird erst ausgerollt, wenn PR-A18 (Backfill-Command) auf dem Zielsystem mit `failed:0` gelaufen und PR-A19 (Hooks) aktiv ist.“ T-A2-1 entsprechend angleichen. |
| QR-T17 | mittel | V | G PR 11, 13, 17 | Jobs in `.github/workflows/*.yml`: es gibt kein `build` und kein `dependency-check`. `client-smoke` ist nur `workflow_dispatch`. | Die Spalte „grün auf“ enthält Checks, die nie am PR laufen. Die DoD ist so nicht prüfbar. | PR 13/17: „grün auf `lint`, `frontend-test` (npm audit), `backend-test set-1-core` (pip-audit), `e2e`; `dependency-check` = manueller Paved-Road-Lauf (`dependency-auditor`), Ergebnis im PR-Kommentar“. PR 11: `client-smoke` per `workflow_dispatch` manuell auslösen und verlinken. |
| QR-T18 | mittel | V | alle Pläne; A T-A0-2/T-A2-6/T-A3-4, C T-C4-1 | `.gitignore:91` `docs/test-reports/` (verifiziert per `git check-ignore`). Alle Live-Belege (`plan-*/live-checks.md`, `raw/`) und mehrere DoD-Artefakte liegen dort. | Belege und DoD-Nachweise sind nicht versioniert, nicht reviewbar und gehen beim Checkout verloren. Die Plan-Behauptungen „belegt durch X-Lnn“ sind für spätere Reviewer nicht nachprüfbar. | Entweder `!docs/test-reports/plan-review-2026-10-21/` in `.gitignore` freigeben, oder DoD-Artefakte nach `docs/se/reports/` bzw. `docs/reviews/` verlegen. In jedem Plan die Zielpfade der DoD-Artefakte anpassen. |
| QR-T19 | mittel | V | D D6.2 ↔ E E3.8 | D (v): „Plan E E3.8 ändert `seed_demo` → D6.2 vorher“. D P3-1: „vor Plan E E3.8“. Planbasis/D: D6 = Welle 4, E3 = Welle 3. | Die geforderte Reihenfolge widerspricht den Wellen: Konflikt in `seed_demo.py` und in `test_seed_demo.py`. | D6.2 ausdrücklich in Welle 3 vor E3.8 ziehen (D erlaubt „vorziehbar“). In E3.8 als Eintritt „D P3-1 gemergt“ eintragen. |
| QR-T20 | mittel | V | A T-A0-3 (W1), D D1.1 (W2), G G3.3 (W2), D D3.4 (W4) | Alle ändern `deploy/docker-compose.yml`. G: „Plan D D1 ⇒ abstimmen“, D: „Merge-Reihenfolge abstimmen“. Eine konkrete Regel fehlt. | Parallele Edits an Honcho-Env, BluePencil-Service und Image-Pins in Welle 2 führen zu Konflikten. Die G3.3-Grep-Verifikation (`grep -v node:22-slim`) bricht, wenn D1.1 erst später merged. | Feste Reihenfolge: A PR-A2 → D P2-1 → G PR 13 → D P3-4. G3.3-Verifikation ohne `node:22-slim`-Ausnahme formulieren, sobald D P2-1 gemergt ist. |
| QR-T21 | mittel | V | C T-C1-2 ∥ T-C1-3 ∥ T-C1-4 (Matrix) | Alle drei senken Deckel in `frontend/src/test/design-system-ratchet.baseline.json` (T-C1-2 „−2“, T-C1-3 `maxViolations 0`, T-C1-4 „Deckel gesenkt“). | Die Matrix erlaubt Parallelität auf einer gemeinsamen Konfliktdatei. Die Baseline-JSON erzeugt Rebase-Konflikte, und der Strict-Shrink ist zwischen den PRs inkonsistent. | Matrix-Spalte „Konfliktdateien“ um `design-system-ratchet.baseline.json` ergänzen: Entwicklung parallel, Merge seriell (PR-C5 → PR-C12). Gleiches gilt für G4.3 und B5-T5 (neue CSS-Module mit Button-Selektoren). |
| QR-T22 | niedrig | V | A T-A0b-2, A P1-Austritt; C §C2 Berechtigungen; C T-C2-4 | `backend/application/tests/test_memory_entry_service.py` existiert nicht, die Datei liegt in `backend/memory/tests/`. `authorization.py:116,128` liegt unter `auth_tenancy/services/authorization.py`. `export_tool_manifest` schreibt MCP-SURFACE.md nicht (siehe QR-T08). | Der P1-Austrittsbefehl von A bricht mit „file not found“ ab. Falsche Pfade in den Belegen. | Pfade korrigieren: `memory/tests/test_memory_entry_service.py`; `auth_tenancy/services/authorization.py:116,128`; C T-C2-4: „MCP-SURFACE.md manuell bzw. per Doku-Guard nachziehen“. |
| QR-T23 | niedrig | V | A §4, B/C/F Testkonvention | `-e DB_PASSWORD="$PG_SUPERUSER_PASSWORD"` (A), `"$POSTGRES_SUPERUSER_PASSWORD"` (B/C/F). In `.env.example`/`deploy/.env` gibt es nur `DB_PASSWORD` (Superuser `DB_USER=reqogniloom`), siehe Projekt-Memory „Running backend tests locally“. | Undefinierte Shell-Variable, leeres Passwort, Auth-Fehler. Wer das nicht kennt, deutet das als Code-Regression. | Einheitlich: `-e DB_USER=reqogniloom -e DB_PASSWORD="$(grep '^DB_PASSWORD=' deploy/.env \| cut -d= -f2-)"`, als Makro einmal in der Planbasis definieren. |
| QR-T24 | niedrig | U | A E1 ↔ T-A0b-3/T-A0b-5; C §2.3 O3; B R-B5-2 | A: Die drei Honcho-Felder werden „nicht ins Schema … UI verliert diese drei Felder“ und antworten 400, obwohl E1 offen ist. C: O3-Migrationspfad als „Fakten, keine Nutzerentscheidung“. B: Abhängigkeit „B5 nutzt HARD_OFF aus A1“ als „nicht blockiert“ aufgehoben, ohne Konflikt-ID. | Die Empfehlung wird vor der Nutzerentscheidung umgesetzt (A: API-Breaking 400). O3 ist laut Planbasis eine offene Klärung, keine Faktenlage. Die geänderte Abhängigkeit B5↔A1 ist in der Wellenfolge folgenlos, aber nicht sauber ausgewiesen. | A: T-A0b-3/5 an E1 gaten („bis E1: Felder weiter angenommen und als `deprecated` geloggt, nicht 400“). C: O3 als Entscheidung „E-C5“ mit Optionen führen. B: R-B5-2 als Entscheidungs-Konflikt „K-3“ markieren. Ein B5-Merge vor A1 lässt bei Custom-Templates ein literales `{memory_context}` stehen; das ist im Plan zu nennen. |
| QR-T25 | niedrig | V | B B2-T1/B3-T3/B5-T4, F F1.1-T2/F2-T3/F3, D2 | Hart codierte Zählungen: Link-Typen „12/13“ (B), +3/+3 (F) → real 19; Audit-Regeln „19“ (B), F +DOC-P5/P7(/P8); Slots „27“. | Tests mit festen Zahlen werden je nach Merge-Reihenfolge rot. | Tests prüfen Mengen-Zugehörigkeit (`"validates" in keys`) statt Gesamtzahl. QS-Verifikationen nennen „vorher + Delta“. |
| QR-T26 | niedrig | U | C Q1 Service-Fassade `levels_for/resolve_for` | „setzen `TenantContext.set_tenant(tenant_id)` selbst“, ohne Wiederherstellung. | In Celery-Tasks oder bei verschachtelten Aufrufen bleibt ein fremder Tenant im Thread-Local gesetzt; RLS-Risiko bei Mehrmandanten-Tasks. | „Setzt den Tenant per Context-Manager und stellt den vorherigen Wert im `finally` wieder her“; Test `test_levels_for_restores_previous_tenant`. |
| QR-T27 | niedrig | U | alle Pläne (Größenlimit), A PR-A21, C PR-C7, F PR-F3 | Limit „~600 Z. ohne Tests/Migrationen“. Gemischte PRs: A PR-A21 (Entkopplung + T-A2-8 Workspace-Parameter), F PR-F3 (additives `artifact_id` + Breaking-Pflichtfeld), C PR-C7 (Datenmigration + Frontend-Hydrator). | 600 Zeilen liegen über dem Review-Richtwert von 400 (SmartBear). Ein Breaking Change im selben PR wie eine additive Änderung erschwert den Revert. | Richtwert ≤ 400 Z. Produktivcode. F PR-F3 in F1.2-T1 (additiv) und F1.2-T2 (Breaking) teilen. A PR-A21 teilen (T-A2-1 / T-A2-8). C PR-C7: Backend (T-C2-6) vor Frontend (T-C2-7). |
| QR-T28 | niedrig | V | G Kopf vs. §10 | Kopf: „3 Nutzerentscheidungen offen (E-G1…E-G3)“, §10 hat E-G1…**E-G4**. | Inkonsistenz, E-G4 könnte übersehen werden (blockiert G4.3). | Kopf auf „4 … (E-G1…E-G4)“ korrigieren. |
| QR-T29 | niedrig | V | A §5/§7 P2 ↔ D (v)/(xiii) | A-Eintritt: „Plan D/D2 … gemergt“. D: A1 erst nach D2.4 **und** D2.5 (Required Check, Nutzer). | Das A1-Eintrittskriterium ist schwächer als das Q2-Gate. | A §7 P2-Eintritt: „Promptfoo-Gate G1–G4 aus Plan D erfüllt (inkl. Required Check D2.5).“ |
| QR-T30 | niedrig | V | A T-A2-4 ↔ G E-G3 Option B | A: `application/0036_alter_domaineventoutbox_event_type`. G: „nur bei Option B: `0036_outbox_workspace_fk`“. | Bedingte Doppelbelegung. | G: bei E-G3 = B die nächste freie Nummer nach A/F (siehe §3). Empfehlung A (O-2) beibehalten. |

---

## 2. Gemeinsame Bausteine: Einfach-Spezifikation geprüft

| Baustein | Besitzer laut Plänen | Konsistent? | Abweichung |
|---|---|---|---|
| Q1-Präferenzdienst | C (T-C2-1…4) | weitgehend | QR-T11 (Workspace-Ebene Memory außerhalb Q1, kein MCP; doppelter Schreibpfad), QR-T26. Schlüssel `memory.enabled`/`memory.disabled_slots` sind in A und C identisch (Typ, Default, Union-Modus, Validator gegen `MEMORY_CONSUMER_SLOTS`, Registrierung in `memory/apps.py`). |
| Memory-Port / Capabilities / Limits | A (A0b) | ja | Kein anderer Plan spezifiziert ihn neu. F3 nutzt nur den Digest. |
| HARD_OFF / Slot-Filter | A (T-A1-1, Präfix `quality_`) | ja | B verlässt sich korrekt auf das A-Präfix; Dependency-Ausweis siehe QR-T24. |
| Link-Typ-Katalog | B: `validates`, `performs` (+Subtyp-Paare). F: `blocks`, `resolves`, `threatens` (K-F1=b), `documented-in`, `evidences`, `depends-on`. G: FK auf `lt_workspace_definition`. | Besitz klar | Migrationsnummern (QR-T02), Subtyp-Mechanismus (QR-T10), Zählungen (QR-T25). Gepinnte Definitionen in Seed-Migrationen (B R-B2-2) übernimmt F, gut. |
| uid-Receiver / Soft-Delete | G (G1.1, G1.3, G1.5) | ja | F2/F3 registrieren Document/WorkItem im Receiver bzw. Constraint-Muster. F4.4 nutzt `reactivate`, passt zum GH-443-Vertrag. Offen: Prefix-Allokation `DOC-`/`WI-` in `local_uid` (F-Spec). |
| ETag / If-Match | E (E2.4–E2.6) | ja | QR-T13 (Milestone ohne `version`), QR-T14 (Merge-Reihenfolge mit G). |
| Outbox / Domain-Events / O-2 | A (neue EventTypes, 0036), F (0037/0038), G (E-G3: keine FK, kein Delete) | ja | Neue Projektoren (A T-A2-4) müssen Outbox-Zeilen mit `tenant_id NULL` tolerieren (O-2: fail-closed übersprungen). Das fehlt als Testfall in T-A2-4 (advisory). QR-T30. |
| OpenAPI-Ratchet | E (E2.7) | – | Plan-übergreifende DoD fehlt (QR-T12). |
| MCP-Manifest / Doku-Zähler | dezentral | nein | QR-T08. |
| Promptfoo-Netz | D (D2) | nein | QR-T05, QR-T06, QR-T07. |

---

## 3. Konsolidierte Migrationstabelle (Ist und Vorschlag)

Ist-Stand im Arbeitsbaum `b175c970` (per `ls backend/<app>/migrations` geprüft): persistence **0115**, auth_tenancy **0027**, link_types **0009**, memory **0008**, application **0035**, attribute_definitions **0009**, baseline **0011**, workflow **0023**, audit **0015**, icd **0013**. Alle Pläne geben diese Höchststände korrekt an.

| App | Reserviert (Plan: Nummer) | Konflikt | **Vorschlag (Welle → Nummer)** | expand/contract |
|---|---|---|---|---|
| persistence | A 0116; B 0116–0119; G 0116–0118; F 0130–0139; C „0150–0159 freigegeben“ | **dreifach 0116, doppelt 0117/0118** | W0 G1.3 → **0116** `entity_workspace_fk_backfill`, **0117** `uid_workspace_unique_constraints`; W1 A T-A0-5 → **0118** `embedding_model_columns`; W2 G2.2 → **0119** `requirement_list_index` (atomic=False); W3 B5-T1 → **0120** `quality_assessment`, **0121** `quality_assessment_rls_policy`; W4 B6-T1 (nur K-2) → **0122** `milestone`, **0123** `milestone_rls_policy`; 0124–0129 Puffer; W4 F2/F3 → **0130–0135** wie reserviert, 0136–0139 Puffer F | G1.3: Dedupe-Umbenennung ist Datenänderung im Constraint-Release (akzeptiert, nur Umbenennen). G2.2: Concurrent-Index ok. Alle übrigen expand. |
| auth_tenancy | C 0030–0033; E 0028 | Reihenfolge widerspricht Wellen (QR-T03) | W1 C → **0028** `preferencevalue`, **0029** `preferencevalue_rls`; W2 C → **0030** `backfill_show_readable_ids`; W3 E3.1 → **0031** `user_mfa`; ≥ 1 Release nach 0030 C-Contract → **0032** `drop_userdisplaypreference_show_readable_ids` | C 0030 braucht Dual-Lesen bis zum Contract (Rückrichtung vorhanden); C 0032 = contract. |
| link_types | B 0010, 0011; G 0010; F 0012–0014 | **doppelt 0010** | W0 G1.4 → **0010** `workspace_definition_workspace_fk`; W3 B2-T1 → **0011** `seed_validates_link_type`; W3 B3-T3 → **0012** `seed_performs_and_satisfies_function_pair`; W3 F1.1-T2 (K-F1=b) → **0013** `seed_issue_risk_link_types`; W4 F2-T3 → **0014** `seed_document_link_types`; W4 F3-T3 → **0015** `merge_work_item_pairs` | G 0010 löscht Waisen (destruktiv, E-G2, Backup Pflicht) und zieht die FK sofort validiert ein. Alternative für strenges expand/contract: `NOT VALID` + `VALIDATE` im Folgerelease (E-G2 Option B). |
| attribute_definitions | B 0010; G 0010 | **doppelt 0010** | W0 G1.4 → **0010** `workspace_definition_workspace_fk`; W3 B1-T1 → **0011** `requirement_interview_elicits_se_fields` | B 0011 Reverse = noop (begründet). |
| memory | A 0009–0013 | – | unverändert: **0009** (T-A0-5), **0010/0011** (T-A0b-3), **0012** (T-A1-3), **0013** (T-A0b-6, contract ≥ 1 Release) | 0010/0011 expand + Daten; **Dual-Write fehlt** (QR-T15). |
| icd | A 0014 | – | **0014** `icd_embedding_model` | expand |
| application | A 0036; F 0037, 0038; G 0036 (nur E-G3=B) | bedingt | W2 A T-A2-4 → **0036**; W4 F2-T7 → **0037**; W4 F3-T8 → **0038**; G nur bei E-G3=B → **nächste freie** | AlterField choices, unkritisch. Jede EventType-Erweiterung braucht eine eigene Choices-Migration (Konfliktpunkt `application/models.py`). |
| baseline | F 0012, 0013 | – | **0012** `baselinetag`, **0013** `baseline_tag_rls_policy` | expand |
| workflow | F 0024, 0025 | – | **0024** (F2-T2), **0025** (F3-T2) | Daten-Seed |
| audit | E 0016 | – | **0016** `alter_auditentry_op_mfa` | AlterField choices |

Regeln (in alle Pläne übernehmen):
1. Die Nummer entsteht beim Merge (max+1). Die Tabelle legt die **Reihenfolge** fest. Wer zuletzt merged, rebased und setzt `dependencies` neu.
2. Rollback- und Test-Befehle verwenden Migrations**namen** (QR-T04).
3. Jeder PR mit Migration läuft `makemigrations --check --dry-run` und `migrate <app> <vorgänger>` → `migrate` rund.
4. RLS-Policy-Migration im selben PR wie das neue `TenantScopedModel` (B, C, F tun das bereits).

---

## 4. Konflikt-Datei-Matrix (plan-übergreifend)

Legende: Welle in Klammern. **fett** = gleiche Welle, Merge-Queue nötig.

| Datei | A | B | C | D | E | F | G | Regel |
|---|---|---|---|---|---|---|---|---|
| `docs/agent-templates/tool-manifest.json` (+ Doku-Zähler, QR-T08) | T-A3-1/3 (W1–2), T-A4-3/5 (W3) | B2-T2/T3, **B5-T3** (W3), B6-T2 (W4) | T-C2-4 (W1) | – | E1.3 (W0, Beschreibung) | F1.2-T1/T2, **F4.2, F4.4** (W3), F2-T6, F3-T6 (W4) | – | eine globale Merge-Queue; Zahl immer neu exportieren |
| `backend/mcp_server/tool_registry.py` | T-A1-5 (W2) | B5-T3 (W3) | T-C2-4, T-C2-10 (W1–2) | – | E1.3 (W0) | F2/F3 (W4) | – | seriell |
| `backend/rest_api/urls.py` | T-A1-4 (W2), T-A4-5/7 (W3) | **B5-T3** (W3), B6-T2 (W4) | T-C2-3 (W1) | – | E2.2 (W0), **E3.4/E3.6** (W3) | F2/F3 REST (W4) | – | seriell; Pfade alphabetisch in eigenem Block |
| `backend/rest_api/views.py` | T-A3-1, T-A2-7/8 (W1–2) | B2-T2 (W3) | – | – | **E1.2, E2.3, E2.4, E2.5** (W0) | **F4.2, F4.4** (W3) | **G1.5** (W0), G2.1, G5.3 (W2) | QR-T14-Queue |
| `backend/rest_api/tests/openapi_warning_baseline.json` (neu E2.7) | neue Views | B5-T3, B6-T2 | T-C2-3 | – | E2.7/E2.8 | F1.2-T1, F4.4 | G1.5 | nur Shrink, seriell (QR-T12) |
| `backend/application/prompt_slots.py` / `prompt_resolver.py` | T-A1-1/2/6 (W2) | B5-T2 (W3) | – | D2 liest nur | – | – | – | A1 vor B5 |
| `backend/application/prompt_testing/cases/*` | T-A1-8 (W2) | B5-T2 fehlt (QR-T07) | – | D2.1 (W0) | – | – | – | D besitzt, A/B erweitern |
| `.github/workflows/ci.yml` | – | – | – | **D1.0, D2.4** (W0), D1.2 (W2), D3.2 (W4) | – | – | – | D-intern seriell (im D-Plan korrekt) |
| `deploy/docker-compose.yml` | T-A0-3 (W1) | – | – | **D1.1** (W2), D3.4 (W4) | – | – | **G3.3** (W2) | QR-T20 |
| `persistence/models.py` | T-A0-5 (W1) | **B5-T1** (W3), B6-T1 (W4) | – | – | – | F2-T1, F3-T1 (W4) | G1.3 (W0), G2.2 (W2) | Migrationskette §3 |
| `link_types/builtin.py` + `traceability/types.py` + `traceLinkLabels.ts` | – | **B2-T1, B3-T3** (W3) | – | – | – | **F1.1-T2** (W3), F2-T3, F3-T3 (W4) | G1.4 (`models.py`, W0) | B vor F |
| `link_types/catalog.py` / `schema.py` | – | **B3-T2** (W3) | – | – | – | **F1.1-T1** (W3, indirekt), F2 Subtyp | – | QR-T10 |
| `application/models.py` (Outbox-Enum) | T-A2-4 (W2) | – | – | – | – | F2-T7, F3-T8 (W4) | (E-G3=B) | §3 application |
| `frontend/src/test/design-system-ratchet.baseline.json` | – | B5-T5 (neue CSS) | **T-C1-1…T-C1-5** (W1–2) | – | E3.8 (CSS, W3) | F4.3/F4.5 (CSS, W3) | **G4.3** (W2) | QR-T09, QR-T21 |
| `frontend/src/styles/global.css` / `tokens.css` | – | – | T-C1-2, T-C1-5 (W1–2) | – | – | – | **G4.2, G4.3** (W2) | C1 vor G4 (in beiden Plänen korrekt) |
| `frontend/src/i18n/locales/{de,en}.json` | T-A0b-5, T-A1-7 | B3-T1, B3-T2, B5-T2, B5-T5 | fast alle | – | E3.8 | F4.3, F4.5, F2-T8 | G4.1, G5.2 | Merge seriell, Paritätstest (C §6 korrekt) |
| `backend/auth_tenancy/management/commands/seed_demo.py` | – | – | – | D6.2 (W4) | **E3.8** (W3) | – | – | QR-T19 |
| `backend/auth_tenancy/management/commands/seed_toothbrush.py` | – | **B1-T2/T3** (W3) | – | – | – | – | G1.1-Test ruft es (W0) | kein Dateikonflikt |
| `llm_adapter/embedding_service.py` | T-A0-6 (W1) | – | – | – | – | – | G2.4 (W2) | sequenziell (G nennt es, A nicht; ergänzen) |
| `frontend/src/components/BaselinesView/BaselinesView.tsx` | – | B6-T2 (W4) | T-C1-6 (W2) | – | – | **F4.3, F4.5** (W3) | G4.1 (`:534`, W2) | C/G vor F |
| `NavigationShell/NavigationShell.tsx` | – | – | T-C0-1 (W0) | – | – | – | G5.2 (`:240`) | C0 vor G5.2 (beide korrekt) |
| `backend/requirements.txt`/`.lock` | T-A0-1 (W1) | – | – | – | E3.0 (W3) | – | – | `requirements-drift-check` |

Promptfoo-Gate vor A1: Die Reihenfolge ist in A (P2-Eintritt) und D (P1-Austritt G1–G4) im Grundsatz korrekt, aber unterschiedlich streng (QR-T29). In der vorliegenden Form ist es wegen QR-T05/T06 nicht lauffähig.

Welle 0 ist realistisch nur mit einer Merge-Queue für `views.py` (E/G) und `ci.yml` (D). Die Obergrenze von 4 Agenten steht in jedem Plan nur planintern. Bei 5 parallelen Welle-0-Plänen (C0, D2, G1, E1, E2) braucht es eine **globale** Zuteilung (Empfehlung: 1 Slot je E, G, D; C0 als Kurzläufer im 4. Slot).

---

## 5. Testbarkeit und DoD (Stichprobe)

- RLS-Superuser-Override: Alle backend-orientierten Pläne setzen `DB_USER=reqogniloom`, die Passwort-Variable ist aber undefiniert (QR-T23). G nutzt den Test-Overlay, das ist korrekt.
- Echte DB statt Mock: In allen Plänen gut umgesetzt. Gezielte Spies nur für „nicht aufgerufen“ (A T-A1-1, B5-T2), das ist vertretbar. F entfernt bestehendes Mock-Theater (`MagicMock` für `TraceLinkService`, R-F1-2), positiv.
- Schwache Stellen: A T-A1-2 „In-Memory-Implementierung des C2-Protokolls … Tests laufen erst ab C2“ ist widersprüchlich (advisory: streichen, Abhängigkeit hart auf PR-C3). A T-A3-4: Recall-Gate mit Mock-Provider ist nur für ID/Keyword aussagekräftig, im Plan ehrlich benannt. G2.1 `filterwarnings error::UnorderedObjectListWarning` gilt global, dadurch müssen alle neuen Listen aus A/B/C/F sortieren (gewollt; in deren DoD aufnehmen).
- CI-Zuordnung: Neue Tests liegen in den Sets der `ci.yml`-Matrix (`backend/tests` → set-4, `reqogniloom/tests` → set-2, `scripts/test_setup_script.py` → `agent-templates-test`). Ausnahmen siehe QR-T17.

---

## 6. Entscheidungs-Konflikte (Bewertung)

| Stelle | Sauber ausgewiesen? | Bewertung |
|---|---|---|
| A E2 (ADR-020 §4 vs. Fallback) | ja | korrekt, P3-Eintritt gated |
| A E3 (A4 ↔ T1) | ja | Teilfreigabe (b) sauber begründet, Matrix konsistent |
| A E1 (Honcho-Felder) | teilweise | Tasks setzen (b) vorweg um, siehe QR-T24 |
| A RB13 (UserMemorySettings über Q1) | ja | korrekt |
| A Workspace-Memory-Ebene außerhalb Q1, ohne MCP | **nein** | QR-T11 |
| B K-1 (B4 erledigt) | ja | Scope-Reduktion vertretbar, P1 an K-1 gegated |
| B K-2 (Measure vs. ADR-008) | ja | vorbildlich, B6 gated |
| B R-B5-2 (B5 nicht an A1 gebunden) | nein (nur Review-Befund) | QR-T24, durch die Wellenfolge folgenlos |
| C K-1/E-C1, K-2/E-C2, E-C3, E-C4 | ja | korrekt |
| C O3 als „Fakten“ | **nein** | QR-T24 |
| D D-D8 (echo statt Mock), D-D5, D-D2 | ja | korrekt |
| E D-E2c (Routenreihenfolge) | ja | Ursache korrekt verlegt (verifiziert `preset_guard.py:236-240`) |
| F K-F0…K-F6 | ja | vorbildlich |
| G E-G1…E-G4 (E-G3 vs. O-2) | ja | korrekt; Kopfzeile zählt falsch (QR-T28) |

---

## 7. Geprüfte Stichproben `datei:zeile`

Ergebnis: **60 Stichproben, 55 OK, 5 Fehlbelege** (★).

| # | Plan | Beleg | Ergebnis |
|---|---|---|---|
| 1 | A | `memory/backends.py:335` `ask_available: bool = True` | OK |
| 2 | A | `application/memory_entry_service.py:84` `MAX_ASK_QUERY_CHARS = 10000` | OK |
| 3 | A | `application/prompt_resolver.py:51-55` `MEMORY_QUERY_MAX_CHARS = 2000` | OK |
| 4 | A | `application/vector_port.py:514-515` Gate 3 `memory_backend_not_qdrant` | OK |
| 5 | A | `application/vector_port.py:81` `ARTIFACT_VECTOR_BACKEND` existiert | OK |
| 6 | A | `deploy/docker-compose.yml:1232` Honcho v3.3.0@sha256 | OK |
| 7 | A | `requirements.txt:169` 2.5.1 / `requirements.lock:66` 2.3.0 | OK |
| 8 | A | `application/prompt_slots.py:84` `bundle_compression` mit `memory_context` | OK |
| 9 | A | `memory/context_builder.py:43` `_TOP_K_PER_SCOPE = 5` | OK |
| 10 | A | `application/search_service.py:148` `_SEMANTIC_TOP_K = 50` | OK |
| 11 | A | `memory/health.py:191-192` Klassenkonstante statt Probe | OK |
| 12 | A | `rest_api/urls.py:667` `memory/me/` | OK |
| 13 | A | `reqogniloom/settings.py:261` AuthenticationMiddleware | OK |
| 14 | A | `memory/tests/test_backend_contract.py` (35 Tests) | OK (35 `def test_`) |
| 15 | A | `application/tests/test_memory_entry_service.py` | ★ existiert nicht; liegt in `memory/tests/` |
| 16 | A | `memory/memory_rest.py:305-307` Honcho-Serializerfelder | OK |
| 17 | B | `link_types/builtin.py:90` `BUILTIN_LINK_TYPES` | OK |
| 18 | B | `persistence/models.py:109-121` `ElementType` (5 Werte) | OK |
| 19 | B | `traceability/audit/rules/trace_derivation_allocation.py:588` BLOCKER | OK |
| 20 | B | `traceability/audit/rule_engine.py:128-129` `_run_rule` | OK |
| 21 | B | `auth_tenancy/management/commands/seed_toothbrush.py:475-480` skip-if-exists | OK |
| 22 | B | `application/interview_artifact_adapters.py:193-226` Alias verwirft `rationale` | OK |
| 23 | B | `docs/agent-templates/tool-manifest.json:3` 248 (39 Präfixe) | OK |
| 24 | B | `.meta-config/project.yaml:104,152,172` „11 … Link-Typen“ | OK |
| 25 | B | `docs/se/ADR/ADR-008_moe_mop_tpm_nicht_modelliert.md` | OK |
| 26 | C | `NavigationShell/ErrorBoundary.tsx:75-77` rohe `error.message` | OK |
| 27 | C | `styles/tokens.css:822-825` Button-Tokens | OK |
| 28 | C | `BaselinesView/BaselinesView.tsx:353-359` Overflow-Aktion | OK |
| 29 | C | `rest_api/urls.py:494`, `:543` | OK |
| 30 | C | `authorization.py:116,128` WORKSPACE_CONFIG | ★ Pfad: `auth_tenancy/services/authorization.py` (Zeilen stimmen) |
| 31 | C | `mcp_server/tool_registry.py:651` `_GOVERNANCE_TOOL_NAMESPACES`, `:1108` tree_display | OK |
| 32 | C | „`export_tool_manifest` aktualisiert MCP-SURFACE.md“ | ★ schreibt nur das Manifest (`export_tool_manifest.py:102`) |
| 33 | C | `shared/ArtifactForm/widgets/MarkdownTabGroup.tsx:60` | OK |
| 34 | D | `frontend/nginx.conf:25` `strict-no-referrer` | OK |
| 35 | D | `deploy/docker-compose.yml:1575-1577` `bluepencil` `node:22-slim` | OK |
| 36 | D | `llm_adapter/providers.py:415` `MockLlmProvider` | OK |
| 37 | D | `.github/workflows/ci.yml:248` `agent-templates-test`, `:343` `frontend-test`, Sets `:50-66` | OK |
| 38 | E | `rest_api/preset_guard.py:236-242` Tenant-Fallback | OK |
| 39 | E | `rest_api/views.py:4717` `preset_endpoint_key = "baselines"` | OK |
| 40 | E | `rest_api/mixins/etag.py:162-165` `uses_if_match` | OK |
| 41 | E | `application/workspace_service.py:177-187` alle Tenant-Workspaces | OK |
| 42 | E | `mcp_server/workspace_scope.py:376-380` `workspace.list` read-exempt | OK |
| 43 | E | `rest_api/auth_enforcer.py:114` „vor `decide_access`“ | OK mit Unschärfe (`decide_access` in `:119`) |
| 44 | E | `rest_api/views.py:4060-4063` TraceLink-Retrieve 404-Stub | OK |
| 45 | E | `rest_api/collaboration_views.py:115-118` `list` 405-Stub | OK |
| 46 | E | `reqogniloom/settings.py:716-718` Postprocessing-Hooks | OK |
| 47 | F | `application/issue_service.py:50`, `:762` | OK |
| 48 | F | `application/risk_service.py:50` | OK |
| 49 | F | `application/import_service.py:966-972` `#`-Filter | OK |
| 50 | F | `baseline/state_capture.py:117-127` Warnung | OK |
| 51 | F | `baseline/migrations/0001_initial.py:159-162` Trigger | OK |
| 52 | F | `persistence/artifact_backing.py:33-47` 13 Typen | OK |
| 53 | F | `link_types/catalog.py:40-48` `Typ:Subtag` | OK |
| 54 | G | `persistence/models.py:1726-1730` `uq_requirement_workspace_uid` | OK |
| 55 | G | `link_types/models.py:58`, `attribute_definitions/models.py:72`, `application/models.py:126` UUIDField ohne FK | OK |
| 56 | G | `application/event_bus.py:1199-1201` 3× INFO | OK |
| 57 | G | `rest_api/views.py:608` `_paginate`; 18× `def destroy` | OK |
| 58 | G | `docs/audit/2026-10/1136-rls-coverage-spec.md:731-732` O-2 | OK |
| 59 | G | CI-Jobs `build`, `dependency-check`, `client-smoke` (PR) | ★ nicht vorhanden bzw. nur `workflow_dispatch` |
| 60 | A/B/C/F | `$PG_SUPERUSER_PASSWORD` / `$POSTGRES_SUPERUSER_PASSWORD` | ★ undefiniert; Env heißt `DB_PASSWORD` |

Zusatzprüfungen ohne Zeilenbezug: Höchste Migrationen je App (alle Pläne korrekt). `NavigationShell.tsx:240` `Navigate to "/"`, `architecture_service.py:409/426` `include_deleted`, `backend/pyproject.toml` `[tool.pytest.ini_options]` vorhanden: alle OK. `docs/test-reports/` gitignored: siehe QR-T18.

---

## 8. Empfohlene Reihenfolge für den Integrator

1. §3 als verbindlichen Plan-Index in die Planbasis aufnehmen (QR-T01–T04, T30).
2. Promptfoo-Kopplung reparieren (QR-T05–T07, T29), bevor D2 merged. Ziel: Slot-Zahl dynamisch, Case-Pflicht je neuem Slot.
3. Plan-übergreifende DoD-Zeilen ergänzen: Tool-PR (QR-T08), REST-View-PR (QR-T12), Liste sortiert (G2.1), Migration nach Namen (QR-T04).
4. Den C1↔G4.3-Konflikt (QR-T09) vor PR-C2 durch `ux-designer` entscheiden lassen.
5. Merge-Queues für die Hotspots aus §4 festlegen (`views.py`, Manifest, `urls.py`, `docker-compose.yml`, Ratchet-Baseline).
