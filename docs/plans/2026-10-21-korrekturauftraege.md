---
type: Plan
title: "Korrekturaufträge Stufe 2 — Pläne A–G nach Querreview TECHNISCH/SICHERHEIT"
scope: "Arbeitsliste für die Stufe-2-Integratoren: je Plan alle QR-T-/QR-S-Befunde mit Task-ID, Zielformulierung und Index-Abhängigkeit"
status: proposed
date: 2026-10-21
author_agent: senior-developer
language: de
index: docs/plans/2026-10-21-backlog-umsetzung-index.md
decisions: docs/plans/2026-10-21-entscheidungen-offen.md
---

# Korrekturaufträge Stufe 2 — Pläne A–G

> **Arbeitsliste.** Ein Integrator je Plan arbeitet die Einträge seines Abschnitts **und** alle
> zutreffenden Einträge aus §0 (KA-ALL) ab. Ziel: Der Plan ist danach ohne Rückfrage umsetzbar und
> widerspruchsfrei zum [Plan-Index](2026-10-21-backlog-umsetzung-index.md).
>
> **Format je Auftrag:** `KA-<Plan>-<nn>` · Quelle (Review-ID, Schwere) · **Stelle** (Task/Abschnitt
> im Plan) · **Ist** (kurz) · **Ziel** (Zielformulierung, übernehmbar) · **Tests** (falls neu) ·
> **Hängt ab von** (Index-Abschnitt bzw. `ENT-*`).
>
> **Mit `ENT-*` markierte Aufträge** brauchen eine Nutzerentscheidung. Bis dahin schreibt der
> Integrator die **Empfehlung als „vorläufig (ENT-…)“** in den Plan und lässt die betroffene Task
> mit Eintrittskriterium „ENT-… entschieden“ stehen.
>
> **Regeln für Integratoren:** keine Planbasis-Entscheidung ändern; keine Absolutzahlen für Tools,
> Link-Typen, Regeln oder Slots einführen; Migrationsnummern nur aus Index §e; keine internen
> Adressen in neue Textstellen (Bezeichnung „QS“); Review-Befund-Tabelle des Plans (§ „Review-Befunde“)
> um eine Zeile je umgesetztem QR-Befund ergänzen („korrigiert in Stufe 2, KA-…“).

**Zählung:** KA-ALL 11 · A 25 · B 15 · C 15 · D 13 · E 14 · F 14 · G 16 → **112** plan-spezifische
Aufträge plus die zutreffenden KA-ALL je Plan (A, B, C, F je 11; D 5; E 8; G 7).

---

## 0. KA-ALL — gemeinsame Aufträge (in jedem genannten Plan anwenden)

**KA-ALL-01** · QR-T01/T02/T03/T30 (kritisch/hoch), QR-S19 · Pläne **A, B, C, E, F, G**
- **Stelle:** Abschnitt „Migrations-Reservierung“, Kopf-Tabelle, Matrix-Spalte „Konfliktdateien / Migrationen“, Rollout-Tabelle, PR-Tabellen.
- **Ziel:** Abschnitt ersetzen durch: „Migrationen: siehe [Plan-Index §e](2026-10-21-backlog-umsetzung-index.md#e-konsolidierte-migrationsvergabe-bindend). Dieser Plan legt an: <Liste App · Name · Task>. Nummer = höchste Nummer der App auf `main` + 1 beim Merge; `dependencies` zeigen auf die zuletzt gemergte Migration. `CreateModel` und RLS-Policy im selben PR; `persistence/tests/test_rls_coverage.py` ist Pflicht-Check.“ Alle Nummern im Fließtext auf die Index-Nummer bringen (Mapping im jeweiligen Planabschnitt, Auftrag `KA-<Plan>-01`).
- **Hängt ab von:** Index §e.

**KA-ALL-02** · QR-T04 (hoch) · Pläne **A, B, C, E, F, G**
- **Stelle:** Spalte „Rollback“ aller PR-Tabellen, TDD-Schritte mit `MigrationExecutor`, Phasen-Eintritte mit `showmigrations`.
- **Ziel:** „Rollback: Revert + `python manage.py migrate <app> <name-der-vorgänger-migration>`“ (Name, nie nackte Nummer). Migrationstests verwenden Migrationsnamen bzw. `loader.graph.leaf_nodes()`.
- **Hängt ab von:** Index §e Regel 4.

**KA-ALL-03** · QR-T08 (hoch), QR-T25 (niedrig) · Pläne **A, B, C, E, F**
- **Stelle:** jede Task mit neuem/geändertem MCP-Tool; jede Stelle mit Absolutzahl (Tools, Präfixe, Link-Typen, Audit-Regeln, Slots).
- **Ziel:** DoD-Zeile: „Tool-PR: `python manage.py export_tool_manifest`; Zahl in `README.md`, `docs/api/MCP-SURFACE.md`, `clients/registry.yaml` angleichen, `python3 scripts/clients/render.py` (erzeugt `docs/clients/antigravity(.de).md`); `.meta-config/project.yaml` über `agent-meta-manager`; `pytest docs/agent-templates dist -q` und `pytest mcp_server/tests/test_tool_manifest_drift.py -q` grün; Merge über die globale Tool-Queue (Index §d.2).“ Absolutzahlen durch Deltas ersetzen („+2 Tools“, „+1 Präfix“, „+1 Link-Typ“); Tests prüfen Mengen-Zugehörigkeit statt Gesamtzahl; QS-Prüfungen „vorher + Delta“.
- **Hängt ab von:** Index §f.1; ENT-X5.

**KA-ALL-04** · QR-T12 (mittel) · Pläne **A, B, C, F, G**
- **Stelle:** jede Task mit neuer REST-Route oder Schemaänderung.
- **Ziel:** DoD-Zeile: „Neue Views mit `serializer_class` oder `@extend_schema`; der PR aktualisiert `backend/rest_api/tests/openapi_warning_baseline.json` (nur Shrink); Merge seriell (Index §d.2).“
- **Hängt ab von:** Index §f.5; Plan E P1-7 gemergt.

**KA-ALL-05** · QR-T23 (niedrig, Fehlbeleg) · Pläne **A, B, C, F**
- **Stelle:** Testkonvention (`BT`/`PYTEST`-Makro, Plan A §4 „Testlauf“).
- **Ziel:** Makro durch Verweis auf Index §f.3 ersetzen; `$PG_SUPERUSER_PASSWORD`/`$POSTGRES_SUPERUSER_PASSWORD` streichen.
- **Hängt ab von:** Index §f.3.

**KA-ALL-06** · QR-T17 (mittel, Fehlbeleg) · Pläne **alle**
- **Stelle:** Spalte „grün auf“, Phasen-Austritte, DoD-Zeilen mit Check-Namen.
- **Ziel:** Nur reale Jobs aus Index §f.2. `lint` = Frontend-ESLint (kein Python-Linter); `build`/`dependency-check` als CI-Check streichen; `dependency-check` = manueller Paved-Road-Lauf (`dependency-auditor`), Ergebnis im PR-Kommentar; `client-smoke` per `workflow_dispatch` auslösen und verlinken; `client-artifacts` nur bei Pfadtreffer; neue Jobs (`prompt-regression`, `nginx-headers-smoke`) erst nach ihrem Merge als Check nennen.
- **Hängt ab von:** Index §f.2.

**KA-ALL-07** · QR-T18 (mittel), Sicherheits-Nebenbefund · Pläne **alle**
- **Stelle:** Kopf-Hinweise „Rohbelege …/docs/test-reports/…“, DoD-Artefakte mit Zielpfad unter `docs/test-reports/`.
- **Ziel (vorläufig ENT-X3 = C):** Satz ergänzen: „Belege unter `docs/test-reports/` sind gitignored; DoD-Nachweise stehen im PR-Text bzw. als CI-Artefakt.“ Nach ENT-X3: Zielpfade auf `docs/se/reports/` bzw. `docs/reviews/` (Option B) umstellen. QS-Adressen in **neuen** Verifikationsbefehlen als Variable (`$QS_URL`) statt Literal.
- **Hängt ab von:** ENT-X3; Index §f.6.

**KA-ALL-08** · QR-T27 (niedrig) · Pläne **alle**
- **Stelle:** Phasen-Vorspann „Größenlimit ~600 Zeilen“.
- **Ziel:** „Richtwert ≤ 400 geänderte Zeilen Produktivcode, Obergrenze 600 → Split; additive und brechende Änderungen nie im selben PR.“ Konkrete Splits in KA-A-11, KA-C-10, KA-F-03.
- **Hängt ab von:** Index §f.7.

**KA-ALL-09** · QR-S03 (hoch) · Pläne **alle** (jede Nennung von `secret-scan` als Gate)
- **Ziel:** Satz in den Phasen-Vorspann: „`secret-scan` prüft bis zum Merge von KA-D-03 nur `reqlo_`-Keys; Env-Geheimnisse deckt er nicht ab. Kein `git add -A`/`git add .`, nur explizite Pfade.“
- **Hängt ab von:** Index §h, KA-D-03.

**KA-ALL-10** · Technischer Review §5 (G2.1) · Pläne **A, B, C, F**
- **Stelle:** DoD jeder Task mit neuer Listen-/Paginierungsroute.
- **Ziel:** „Liste deterministisch sortiert (`order_by` mit eindeutigem Tiebreaker); nach Plan G PR 6 macht `UnorderedObjectListWarning` den Test rot.“
- **Hängt ab von:** Index §f.5.

**KA-ALL-11** · Index §g (Rollen) · Pläne **A, B, C, D, E, F**
- **Ziel:** Nicht existierende Rollen ersetzen: `frontend-developer` → `frontend-component-engineer`; `ux-designer` → `ui-ux-designer` (Design-Token-Fragen: `design-system-architect`); `ux-reviewer` → `ui-reviewer`; `se-architect`/`se-critic` → „Rolle laut ENT-X4 + Nutzer“.
- **Hängt ab von:** ENT-X4.

---

## A — Plan A Memory & Suche (25)

**KA-A-01** · QR-T01, QR-T04, QR-S19 · Stelle: §14, §6 (Zeilen T-A0-5, T-A0b-3, T-A1-3, T-A2-4, Mermaid), §7 PR-A3/A5/A11/A19/A29 (Rollback), T-A0-5
- **Ziel (Mapping):** persistence `0116_embedding_model_columns` → **`0118_embedding_model_columns`**; memory 0009–0013, icd 0014, application 0036 bleiben. P1-Eintritt zusätzlich: „`persistence` steht auf `0117_uid_workspace_unique_constraints` (Plan G P1).“ Rollbacks: PR-A3 `migrate persistence 0117_uid_workspace_unique_constraints`, `migrate memory 0008_system_memory_qdrant_settings`, `migrate icd 0013_drop_icd_version`; PR-A5 `migrate memory 0009_memoryentry_embedding_model`; PR-A11 `migrate memory 0011_backfill_backend_options`; PR-A19 `migrate application 0035_alter_domaineventoutbox_event_type`. Hinweis: memory 0012 entfällt bei ENT-A5 = A (dann Contract = 0012).
- **Hängt ab von:** Index §e; ENT-A5.

**KA-A-02** · QR-T05 (hoch) · Stelle: T-A1-8, §6 Zeile T-A1-8
- **Ist:** „neu `…/cases/bundle_compression.yaml`, `need_to_sysreq.yaml`, `interview.chat_turn.yaml`“; Assertion `memory_top_k=1` → genau eine Zeile.
- **Ziel:** „T-A1-8 **erweitert** die D2-Case-Dateien `bundle_compression.yaml`, `need_to_sysreq.yaml`, `interview.chat_turn.yaml` um Szenarien. Promptfoo prüft nur: HARD_OFF-Slot rendert kein `Workspace context:`; alle `{memory_*}`-Platzhalter aufgelöst; Datengrenze vorhanden (KA-A-16). Top-k-, Format- und Scope-Prüfungen liegen in `application/tests/test_prompt_resolver.py` mit echten `MemoryEntry`-Fixtures.“
- **Tests:** `test_memory_top_k_one_renders_single_workspace_line`, `test_memory_format_json_is_parseable` (beide `test_prompt_resolver.py`).
- **Hängt ab von:** Index §b (QR-T05/T07-Folgen).

**KA-A-03** · QR-T06 (hoch) · Stelle: T-A1-8 DoD, §7 P2 (Eintritt, PR-A9, PR-A10)
- **Ziel:** „PR-A9 enthält nur Szenarien, die auf `main` grün sind. Das Szenario `bundle_compression` ‚ohne Memory‘ wird **in PR-A10 zusammen mit T-A1-1** eingeführt; der rote Baseline-Nachweis steht nur im PR-Text von PR-A10.“ P2-Eintritt: Satz „Baseline-Lauf … `bundle_compression` ist rot“ streichen.
- **Hängt ab von:** Index §b.

**KA-A-04** · QR-T29 (niedrig) · Stelle: §7 P2 Eintritt, WP A1 „Voraussetzungen“
- **Ziel:** „Eintritt: Promptfoo-Gate G1–G4 aus Plan D erfüllt (inkl. Required Check D2.5); PR-C3 (Q1-Kern) gemergt; T-A0b-1 gemergt.“
- **Hängt ab von:** Index §b.

**KA-A-05** · QR-T11 (mittel) · **ENT-A5** · Stelle: T-A1-3 (MCP-Absatz), T-A1-4, §5 Plan→Plan
- **Ziel (vorläufig ENT-A5 = A):** „Die Workspace-Ebene der Memory-Schalter ist Q1: `memory.disabled_slots` (Ebenen `global`, `workspace`, `user`, Union), `memory.allow_user_opt_out` (Ebene `workspace`). `WorkspaceMemorySettings` bleibt nur Fassade für den bestehenden Vertrag `PUT {"enabled": …}`; MCP-Zugriff über den Q1-Toolsatz. `/api/v1/memory/me/settings/` ist eine dünne Fassade über `PreferenceService.set_level` (eine Validierung, ein Audit-Pfad).“ Bei ENT-A5 = B: Abschnitt „Ausnahme von Q1 (REST-only), bewusst akzeptiert (ENT-A5)“.
- **Hängt ab von:** ENT-A5; KA-C-07.

**KA-A-06** · QR-T15 (mittel) · Stelle: T-A0b-3, §8 Zeile „Settings-Schema“
- **Ziel:** „**Dual-Write:** Jeder PUT schreibt `backend_options`/`backend_secrets_encrypted` **und** die Altspalten, bis T-A0b-6 gemergt ist. Ein Code-Revert ohne Rückmigration liest damit aktuelle Werte.“
- **Tests:** `test_put_dual_writes_legacy_columns`.
- **Hängt ab von:** –

**KA-A-07** · QR-T16 (mittel) · Stelle: §7 P3 „Rollout-Regel“, §9 Zeile „Entkopplung vor Backfill“, T-A2-1
- **Ziel:** „PR-A21 wird erst ausgerollt, wenn PR-A18 (Backfill-Command) auf dem Zielsystem mit `failed:0` gelaufen und PR-A19 (Hooks) aktiv ist. Bis dahin bleibt `ARTIFACT_VECTOR_BACKEND=pgvector`.“ T-A2-1 „zusammen mit T-A2-5“ entsprechend angleichen.

**KA-A-08** · QR-T22 (niedrig, Fehlbeleg) · Stelle: §7 P1 Austritt, T-A0b-2
- **Ziel:** `application/tests/test_memory_entry_service.py` → `memory/tests/test_memory_entry_service.py`.
- **Hängt ab von:** Index §f.4.

**KA-A-09** · QR-T24 (niedrig) · **ENT-A1** · Stelle: T-A0b-3 (Honcho-Schema, PUT-Vertrag), T-A0b-5, §9 Zeile „Honcho-Namensfelder“, §11 E1
- **Ist:** Altfelder `honcho_peer_name`, `honcho_workspace_id`, `honcho_app_id` antworten 400; UI verliert die Felder.
- **Ziel (vorläufig ENT-A1 = b mit Übergang):** „Bis ENT-A1 entschieden ist, werden die drei Felder weiter angenommen, nicht persistiert und als `deprecated` geloggt (kein 400). Das UI zeigt sie mit Hinweis ‚ohne Wirkung‘. Nach ENT-A1 = b: 400 `not configurable (see ADR-023 O4)` und UI-Felder entfallen.“
- **Hängt ab von:** ENT-A1.

**KA-A-10** · QR-T20 (mittel) · Stelle: T-A0-3, §5 Plan→Plan, §6 Konfliktspalte T-A0-3
- **Ziel:** „`deploy/docker-compose.yml`: Merge-Reihenfolge A PR-A2 → D P2-1 → G PR 13 → D P3-4 (Index §d.2).“

**KA-A-11** · QR-T27 (niedrig) · Stelle: §7 P3 PR-A21
- **Ziel:** PR-A21 teilen: **PR-A21a** `feat/a2-decouple-artifact-vector-backend` (T-A2-1) und **PR-A21b** `feat/a2-tracelink-icd-similarity-workspace` (T-A2-8), Reihenfolge A21a → A21b.

**KA-A-12** · Technischer Review §5 (advisory) · Stelle: T-A1-2 TDD, §9 Zeile „Q1 verzögert sich“
- **Ziel:** Satz „In-Memory-Implementierung des C2-Protokolls … Tests laufen erst ab C2“ streichen; „T-A1-2 hat eine harte Abhängigkeit auf PR-C3; Tests laufen gegen den echten Q1-Service.“

**KA-A-13** · Technischer Review §2 (advisory) · Stelle: T-A2-4
- **Ziel:** „Neue Projektoren tolerieren Outbox-Zeilen mit `tenant_id NULL` (O-2): fail-closed überspringen, zählen, WARNING.“
- **Tests:** `test_projector_skips_outbox_row_without_tenant`.

**KA-A-14** · Technischer Review §4 · Stelle: §5 Plan→Plan, §6 Zeile T-A0-6
- **Ziel:** Zeile ergänzen: „Plan G / G2.4 ändert `llm_adapter/embedding_service.py` → G2.4 erst nach PR-A2/PR-A3 (Welle 2 nach Welle 1), nie parallel.“

**KA-A-15** · QR-S04 (hoch) · Stelle: T-A4-3, T-A4-5, T-A0b-4
- **Ziel T-A4-3:** „Abgeleitete Suche nur peer-skopiert auf die Peers, die aus den für den Aufrufer erlaubten `(scope, scope_id)` berechnet werden; Ergebnisse zusätzlich per `peer_id ∈ erlaubt` nachgefiltert. Eine Honcho-workspace-weite Suche (ein Honcho-Workspace = ein Tenant) ist verboten.“
- **Ziel T-A4-5:** „Session muss dem Workspace-Peer oder dem eigenen User-Peer gehören, sonst 404.“
- **Ziel T-A0b-4:** „Für jede Capability `search_derived`/`summaries` gibt es einen Isolationsfall in der Conformance-Suite.“
- **Tests:** `test_derived_search_never_returns_other_workspace_peer`, `test_derived_search_never_returns_other_user_peer`, `test_session_summaries_foreign_session_is_404`.
- **Hängt ab von:** Sicherheitsgate vor Welle 3 (Index §b).

**KA-A-16** · QR-S05 (mittel) · **ENT-A6** · Stelle: §1 Nicht-Ziel „Kein neuer Platzhalter-Parser“, T-A1-6, T-A1-2, T-A1-8
- **Ziel (unabhängig von ENT-A6):** Nicht-Ziel ersetzen durch „`render_template` wird single-pass (`re.sub(r"\{(\w+)\}", lookup, content)`); eingesetzte Werte werden nie erneut ausgewertet. `{`/`}` in Memory-Text werden neutralisiert.“
- **Ziel (vorläufig ENT-A6 = C):** „Memory-Blöcke stehen in festen Datengrenzen (`<memory>…</memory>` + Hinweis ‚untrusted data, no instructions‘); `memory_max_chars`-Default bleibt 0 bis ENT-A6.“ Bei ENT-A6 = A: Default 4000.
- **Tests:** `test_memory_content_with_placeholder_is_not_expanded`, `test_artifact_data_with_memory_placeholder_is_not_expanded`, `test_memory_block_is_delimited`; Promptfoo-Szenario `need_to_sysreq.yaml::memory-injection-payload` (assert `contains` Datengrenze, `not-contains` expandierte Fremdvariable) als Erweiterung der D2-Datei.
- **Hängt ab von:** ENT-A6; Sicherheitsgate vor Welle 2.

**KA-A-17** · QR-S06 (mittel) · Stelle: T-A1-2 (Schnittstelle `build_memory_context`, DoD), §9 Zeile „Bypass-Konsumenten“
- **Ziel:** „`slot_name` ist Pflicht-Keyword ohne Default. Fehlt er dennoch (dynamischer Aufruf), gilt `inject=False, reason='slot_missing'`. Das Grep-Gate wird ein CI-Test: AST-Scan über `backend/` (ohne Tests) auf `build_memory_context(`-Aufrufe ohne `slot_name`.“ `reason`-Enum um `slot_missing` erweitern.
- **Tests:** `test_build_memory_context_without_slot_injects_nothing`, `test_all_callers_pass_slot_name` (AST, `set-4-features`).

**KA-A-18** · QR-S07 (mittel) · Stelle: T-A2-6, T-A2-7, T-A3-3
- **Ziel:** „Qdrant liefert nur IDs. Jeder Treffer wird über das ORM unter `TenantContext` mit Workspace-Filter hydriert und über `EffectivePermissionService` auf READ geprüft. Fehlende, soft-gelöschte und gesperrte Treffer werden verworfen. Gleiches gilt für die A3-`_TableSpec`-Pfade (TraceLink, Icd).“
- **Tests:** `test_qdrant_hit_with_foreign_workspace_payload_is_dropped`, `test_qdrant_hit_item_permission_none_is_dropped`, `test_stale_point_after_failed_delete_not_returned`.
- **Hängt ab von:** Sicherheitsgate vor Welle 2.

**KA-A-19** · QR-S13 (mittel) · Stelle: T-A0b-3 (Datenmodell, PUT-Vertrag, Migration 0011)
- **Ziel:** „Felder vom Typ `secret` werden nur über `backend_secrets.<backend>.<field>` angenommen und ausschließlich Fernet-verschlüsselt gespeichert. In `backend_options` → 400. GET liefert nur `secrets_set`. Audit und Logs redigieren. Migration 0011 entschlüsselt strikt (`InvalidToken` → Abbruch).“
- **Tests:** `test_put_secret_in_backend_options_is_400`, `test_get_never_returns_secret_values`, `test_settings_audit_redacts_secrets`, `test_backfill_0011_roundtrip_keeps_ciphertext_decryptable`.

**KA-A-20** · QR-S20 (niedrig) · Stelle: T-A3-3
- **Ziel:** „Titel und UID des Link-Ziels nur, wenn der Aufrufer READ auf den Ziel-Workspace hat, sonst `null`/`'—'`.“ (gleiche Regel wie KA-E-08)
- **Tests:** `test_search_tracelink_hides_target_title_of_unreadable_workspace`.

**KA-A-21** · QR-S21 (niedrig) · Stelle: T-A1-4 (REST-Vertrag)
- **Ziel:** „Mit `workspace_id` ist eine READ-Rolle im Workspace erforderlich, sonst 404.“
- **Tests:** `test_me_settings_effective_for_non_member_workspace_is_404`.

**KA-A-22** · QR-S23 (niedrig) · **ENT-A8** · Stelle: T-A2-1, T-A2-9, §8
- **Ziel:** „Bei `ARTIFACT_VECTOR_BACKEND=qdrant` und `DJANGO_ENV=production` ohne `QDRANT_API_KEY`: System-Check-Warnung `memory.W003` und Health-Advisory. Runbook verlangt API-Key und keinen Host-Port.“ (Vorläufig Warnung; Pflicht nach ENT-A8 = A.)
- **Tests:** `test_qdrant_without_api_key_warns_in_production`.

**KA-A-23** · QR-T08, QR-T25 · Stelle: T-A3-1, T-A3-3, T-A4-3, T-A4-5, §9 Zeile „Manifest-Drift“
- **Ziel:** KA-ALL-03 anwenden; Absolutzahlen entfernen, Deltas je PR nennen (PR-A7: Parameter `mode` = 0 neue Tools; PR-A16, PR-A25, PR-A26: „+n Tools“ laut Implementierung).

**KA-A-24** · Index §b, §e · Stelle: Kopf (ADRs), §5 (Planbasis O1), §7 P1 PR-A7/PR-A8, §7 P3/P4 Eintritt, §11
- **Ziel:** ADR-Statuswechsel mit „Rolle laut ENT-X4 + Nutzer“; Konflikt-Entscheidungen verweisen auf ENT-A2 (E2), ENT-A3 (E3), ENT-X2 (ADR-Texte); PR-A7/PR-A8: „Welle 2 laut Planbasis; Vorziehen nur nach ENT-V1“. §11 E1–E4 mit den ENT-IDs verlinken.

**KA-A-25** · Sicherheitsreview „Offene Risiken“ 4 · **ENT-A7** · Stelle: T-A1-2 (Regel), T-A1-4, §9
- **Ziel:** Risikozeile: „`allow_user_opt_out=false` injiziert persönliches User-Memory trotz Opt-out; Datenschutzbewertung offen (ENT-A7).“ Bei ENT-A7 = B: Regel ergänzen „`user`-Scope bleibt bei Opt-out immer aus“.

---

## B — Plan B SE-Modell (15)

**KA-B-01** · QR-T01, QR-T02, QR-T04, QR-S19 · Stelle: Migrations-Reservierung, (v) Task→Task (B3-T3), (v) Plan→Plan (F2), (vi) Rollout, (xii) Matrix, (xiii) PR-B1/B8/B13/B14/B19 (Rollback), P3-Eintritt
- **Ziel (Mapping):** attribute_definitions `0010_requirement_interview_elicits_se_fields` → **0011**; link_types `0010_seed_validates_link_type` → **0011**, `0011_seed_performs_and_satisfies_function_pair` → **0012**; persistence `0116_quality_assessment`/`0117_…rls_policy` → **0120/0121**; `0118_milestone`/`0119_…rls_policy` → **0128/0129**. B3-T3-Abhängigkeit: „Kette `link_types` 0011 → 0012“. Plan F setzt ab **0013** fort. Zusatz: „Nach Plan G G1.4 hat `workspace_id` eine FK: Migrations- und Seed-Tests legen echte `Workspace`-Zeilen an (kein `uuid4()`).“ P3-Eintritt: „persistence-Nummer laut Index §e“.
- **Hängt ab von:** Index §e; ENT-G2 (G1.4 zuerst).

**KA-B-02** · QR-T07 (hoch) · Stelle: B5-T2, PR-B15, P3-Austritt
- **Ziel:** „B5-T2 legt im selben PR `backend/application/prompt_testing/cases/quality_{requirement,adr,testcase,risk}.yaml` an (je ≥ 1 Szenario, `not-contains: "{memory_context}"`).“ P3-Austritt „27 Slots“ → „Slots vorher + 4, davon `quality_*` 4“.
- **Hängt ab von:** Index §b (Neuer Slot ⇒ Case-Datei).

**KA-B-03** · QR-T25 (niedrig) · Stelle: B2-T1, B3-T3, B5-T4 (Tests), P2-Austritt „count 13“, P3-Austritt „19 Regeln“, (vii) Risiko „Manifest-/Zähl-Drift“
- **Ziel:** Tests prüfen Mengen-Zugehörigkeit (`"validates" in keys`, `"QUAL-…" in rule_ids`); QS-Austritte „Link-Typen vorher + 2“, „Regeln vorher + n“.

**KA-B-04** · QR-T08 (hoch) · Stelle: B2-T2, B2-T3, B5-T3 („250 Tools, 40 Präfixe“), B6-T2/P4-Austritt („+6 Tools“), (vii)
- **Ziel:** KA-ALL-03; B5-T3: „+n Tools, +1 Präfix `quality`“; `.meta-config/project.yaml`-Zeilen (Tool-, Präfix-, Link-Typ-Zahl) über `agent-meta-manager` nach ENT-X5.
- **Hängt ab von:** ENT-X5.

**KA-B-05** · QR-T12 (mittel) · Stelle: B2-T2, B5-T3, B6-T2
- **Ziel:** KA-ALL-04 je Task als DoD-Zeile.

**KA-B-06** · QR-T13 (mittel) · Stelle: B6-T1, B6-T2
- **Ziel:** „`Milestone.version = PositiveIntegerField(default=1)`; Service nimmt `expected_version`; ViewSet `etag_supported=True` (Vertrag Plan E E2.5).“ Alternative bei ENT-E2-Folgeentscheid: `etag_supported=False` mit ehrlicher 412-Zusage (E2.6).
- **Tests:** `test_milestone_patch_with_current_etag_is_200`, `test_milestone_patch_with_stale_etag_is_412`.
- **Hängt ab von:** ENT-E2; ENT-B2.

**KA-B-07** · QR-T24 (niedrig) · **ENT-B3** · Stelle: (ii) Entscheidungs-Konflikte, (v) Plan→Plan „Plan A WP A1“, (x) R-B5-2, (xi) Nr. 3
- **Ziel:** R-B5-2 als Entscheidungs-Konflikt „K-3 (ENT-B3)“ führen; vorläufig (ENT-B3 = A): „B5 merged nach A1 (T-A1-1). Würde B5 vor A1 mergen, bliebe in Custom-Templates mit `{memory_context}` auf `quality_*`-Slots ein literaler Platzhalter stehen.“

**KA-B-08** · QR-T10 (mittel) · Stelle: B3-T2, (xii) Matrix Zeile B3-T2
- **Ziel:** „Subtyp-Paare sind generisch: zulässig für jeden Artefakttyp mit registriertem Subtyp-Feld (Register in `link_types/catalog.py`: `ArchitectureElement → element_type`; Plan F ergänzt `Document → kind`). Wire-Format ist die bestehende Notation `Typ:Subtag` (`normalize_artifact_type`, `catalog.py:40-48`); Docstring in `catalog.py` dokumentiert sie als einzige Repräsentation.“ Satz „nur zulässig, wenn `*_type` = `ArchitectureElement`, sonst ValidationError“ ersetzen durch „nur zulässig für Typen im Subtyp-Register, sonst ValidationError“.
- **Tests:** `test_subtype_pair_rejected_for_type_without_registered_subtype_field`, `test_subtype_register_lists_architecture_element`.
- **Hängt ab von:** KA-F-02.

**KA-B-09** · QR-T21 (mittel) · Stelle: B5-T5, PR-B18
- **Ziel:** „Neue CSS-Module mit Button-Selektoren unterliegen dem C1-Geometrie-Check und dem Design-System-Ratchet; Merge nach den C1-PRs, Deckel nur senken (Index §d.2).“

**KA-B-10** · QR-S08 (mittel) · Stelle: B5-T3, (vi) Zeile B5
- **Ziel:** „`assess`, `history`, `latest_for` laden Entitäten ausschließlich mit `workspace_id=<Pfad>`; Abweichung → 404 `NOT_FOUND`, kein LLM-Call. `QUALITY_ASSESS_RATE` leer bedeutet Default `60/hour`, nie ‚unbegrenzt‘.“
- **Tests:** `test_assess_entity_of_other_workspace_is_404`, `test_history_entity_of_other_workspace_is_404`, MCP-Pendant `test_mcp_quality_assess_other_workspace_entity_not_found`, gefencter Key auf fremden Workspace → `-32001`, `test_empty_quality_assess_rate_uses_default`.
- **Hängt ab von:** Sicherheitsgate vor Welle 3.

**KA-B-11** · QR-S19 · Stelle: B5-T1, B6-T1 DoD
- **Ziel:** „`CreateModel` und RLS-Policy im selben PR; DoD enthält `persistence/tests/test_rls_coverage.py` grün.“

**KA-B-12** · KA-ALL-10 · Stelle: B2-T2 (Validierungs-Coverage-Liste), B5-T3 (Historie), B6-T2 (Milestone-Liste)
- **Ziel:** DoD „deterministisch sortiert“ je Liste.

**KA-B-13** · KA-ALL-11 · Stelle: B5-T5 (`frontend-developer`), PR-B18 (`ux-designer`), B4-T2 (`se-architect`), PR-B6 (`se-critic`)
- **Ziel:** Rollen laut Index §g; ADR-004-Statuswechsel „Rolle laut ENT-X4 + Nutzer“.

**KA-B-14** · Entscheidungsverweise · Stelle: (ix), (ii), P1/P4-Eintritt
- **Ziel:** K-1 → ENT-B1, K-2 → ENT-B2, E-3 → ENT-B4, E-4 → ENT-B5, neu K-3 → ENT-B3 verlinken; Eintrittskriterien nennen die ENT-ID.

**KA-B-15** · Sicherheitsreview „Offene Risiken“ 6 · **ENT-A9** · Stelle: (vii)
- **Ziel:** Risikozeile „Prompt-Injection bleibt trotz advisory möglich (Restrisiko, ENT-A9); Score nie Gate, `reasoning` nie ungeprüft in Folgeprompts.“

---

## C — Plan C UI/UX (15)

**KA-C-01** · QR-T03 (hoch), QR-T01 · Stelle: Kopf „Migrations-Reservierung“, T-C2-1 (Dateien, Migrationsregel), T-C2-6, T-C2-9, §6 Matrix + Migrationskette, §9 Risiko, §12 R15, §14
- **Ziel (Mapping):** `0030_preferencevalue` → **`0028_preferencevalue`**, `0031_preferencevalue_rls` → **`0029_preferencevalue_rls`**, `0032_backfill_show_readable_ids` → **`0030_backfill_show_readable_ids`**, `0033_drop_userdisplaypreference_show_readable_ids` → **`0032_…`** (Contract; Plan E nimmt `0031_user_mfa`). Satz „`0029` bleibt frei (Puffer für Plan E)“ und „`persistence` 0150–0159 … freigeben“ streichen. Migrationsregel T-C2-1: „`0028` hängt an `0027_create_form_config`; Plan E/E3 folgt in Welle 3 (Index §e).“
- **Hängt ab von:** Index §e.

**KA-C-02** · QR-T04 · Stelle: T-C2-1 Rollback, PR-C3, PR-C7, PR-C16
- **Ziel:** PR-C3 `migrate auth_tenancy 0027_create_form_config`; PR-C7 `migrate auth_tenancy 0029_preferencevalue_rls` (0030 schreibt Werte in die Spalte zurück); PR-C16 Rückrichtung der Contract-Migration.

**KA-C-03** · QR-T08, QR-T22 (Fehlbeleg) · Stelle: T-C2-4 (Absatz nach der Tool-Tabelle), §9 Risiko „MCP-Zähler“
- **Ist:** „Manifest … und `docs/api/MCP-SURFACE.md` werden per `export_tool_manifest` aktualisiert (… Gesamtzahl konsolidiert der Index …)“.
- **Ziel:** „`export_tool_manifest` aktualisiert nur das Manifest. `MCP-SURFACE.md`, `README.md`, `clients/registry.yaml` (+ `render.py`) und `.meta-config/project.yaml` werden nach KA-ALL-03 nachgezogen. Delta: +4 Tools, +1 Präfix `preference`.“

**KA-C-04** · QR-T22 (Fehlbeleg) · Stelle: §C2 Berechtigungen (Beleg `authorization.py:116,128`)
- **Ziel:** Pfad `auth_tenancy/services/authorization.py:116,128`.

**KA-C-05** · QR-T09 (hoch) · **ENT-C6** · Stelle: T-C1-1 (Statischer Check, E2E-Gate), §1 Ziel 2, §5 Plan→Plan
- **Ziel (nach ENT-C6, Empfehlung B):** „Höhenskala: `--btn-h-xs: 24px` (Icon-Buttons), `--btn-h-sm/md/lg`. Statischer Check: Verstoß = `height`/`min-height` ∉ `var(--btn-h-*)`. E2E-Gate: ‚≤ 3 Höhen je Route ohne Icon-Buttons (`--btn-h-xs`)‘, ≤ 2 Radien. Plan G G4.3 nutzt `--btn-h-xs` bzw. `--target-min` als Alias.“ Eintritt PR-C2: „ENT-C6 entschieden“.
- **Hängt ab von:** ENT-C6; KA-G-05.

**KA-C-06** · QR-T21 (mittel) · Stelle: §6 Matrix (T-C1-2 … T-C1-5, Spalte „Konfliktdateien“), §7 P2/P3
- **Ziel:** Konfliktdatei `frontend/src/test/design-system-ratchet.baseline.json` bei T-C1-1 … T-C1-6 eintragen; „Entwicklung parallel, Merge seriell PR-C2 → PR-C5 → PR-C12 → PR-C13; danach Plan G PR 16“.

**KA-C-07** · QR-T11 (mittel) · **ENT-A5** · Stelle: Q1-Spezifikation (Schlüsselregister), §5 Plan→Plan
- **Ziel (vorläufig ENT-A5 = A):** Registerzeilen: `memory.enabled` (bool, Ebene `user`, Default `true`), `memory.disabled_slots` (str_list, Ebenen `global`, `workspace`, `user`, Modus `union`, Validator gegen `MEMORY_CONSUMER_SLOTS`), `memory.allow_user_opt_out` (bool, Ebene `workspace`, Default `true`); Besitzer Plan A, Registrierung in `memory/apps.py`. Satz: „Q1 erlaubt Schlüssel-Validatoren je Schlüssel (Anforderung Plan A).“

**KA-C-08** · QR-T24 (niedrig) · **ENT-C5** · Stelle: §2.3 Überschrift und O3-Absatz, §1 Nicht-Ziele (2. Punkt)
- **Ziel:** Überschrift „Antwort auf O2 (Fakten) und O3 (Entscheidung ENT-C5)“; O3-Absatz als „vorläufige Empfehlung ENT-C5 = A“ formulieren.

**KA-C-09** · QR-T26 / QR-S14 (niedrig) · Stelle: Q1 Service-Fassade (Absatz nach `levels_for`/`resolve_for`)
- **Ziel:** „`levels_for`/`resolve_for` setzen den Tenant per Kontextmanager und stellen den vorherigen Wert im `finally` wieder her (auch bei Exception).“
- **Tests:** `test_levels_for_restores_previous_tenant`, `test_levels_for_restores_previous_tenant_on_exception`.

**KA-C-10** · QR-T27 (niedrig) · Stelle: §7 P3 PR-C7
- **Ziel:** PR-C7 teilen: **PR-C7a** Backend (T-C2-6, Migration 0030, Fassade) vor **PR-C7b** Frontend (T-C2-7, Hydrator).

**KA-C-11** · KA-ALL-05 · Stelle: §4 Konventionen (`BT`)
- **Ziel:** `DB_PASSWORD="$POSTGRES_SUPERUSER_PASSWORD"` → Verweis Index §f.3.

**KA-C-12** · KA-ALL-04 · Stelle: T-C2-3 (6 neue Views)
- **Ziel:** DoD-Zeile OpenAPI-Ratchet (Shrink, seriell).

**KA-C-13** · KA-ALL-11 · Stelle: §6 Matrix (`frontend-developer` bei T-C2-5, T-C2-7, T-C2-8, T-C4-4)
- **Ziel:** `frontend-component-engineer`; QR-T09-Entscheider `design-system-architect`/`ui-ux-designer`.

**KA-C-14** · Index §b/§d · Stelle: §5 Plan→Plan („Plan G G4.3 nach PR-C5“, „Plan E E3 (`auth_tenancy 0028`)“)
- **Ziel:** „Plan G G4.3 (PR 16) nach PR-C12 (C1 vollständig)“; „Plan E E3.1 nimmt `auth_tenancy 0031_user_mfa` (Index §e)“.

**KA-C-15** · Entscheidungsverweise · Stelle: §2.2, §11, Eintrittskriterien P3
- **Ziel:** E-C1 → ENT-C1, E-C2 → ENT-C2, E-C3 → ENT-C3, E-C4 → ENT-C4 (verknüpft mit ENT-D2), neu O3 → ENT-C5, QR-T09 → ENT-C6.

---

## D — Plan D Deployment/DX (13)

**KA-D-01** · QR-T07 (hoch) · Stelle: (i) Ziel 2, D2.1 (Überschrift „23 Fall-Dateien“, Pflichtumfang, Tests), D2.2 (Ausgabezeile, Exit-Bedingung, `test_writes_one_config_per_slot`), (xiii) P1-Austritt G1, (viii) Aufwand
- **Ziel:** „Soll-Zahl = `len(get_prompt_slots())`, nie 23. Ausgabezeile `promptfoo export: <n>/<len> slots, …`; Exit 1, wenn `n < len`, `m > 0`, `u > 0` oder `a < b`.“ Tests ohne feste 23 (`assert len(files) == len(get_prompt_slots())`).
- **Hängt ab von:** Index §b (Promptfoo-Gate).

**KA-D-02** · QR-T05/T06/T07 · Stelle: D2.1 (Schema, Test-Docstring), (v) Plan→Plan
- **Ziel:** „Case-Dateien gehören Plan D. Andere Pläne **erweitern** sie um Szenarien (A: T-A1-8) bzw. legen nur für **neue** Slots eine Datei im selben PR an (B: B5-T2). In `main` wird nie ein roter Case gemergt.“ Test-Docstring von `test_every_slot_has_exactly_one_case_file` nennt diese Regel.

**KA-D-03** · QR-S03 (hoch) · Stelle: neue Task **D2.6** (Welle 0, `devops-engineer`, Review `security-auditor`), D3.2, (xii), (xiii) neuer PR **P1-4**
- **Ziel D2.6:** „`secret-scan` erhält einen zweiten, blockierenden gitleaks-Lauf über den PR-Diff mit Custom-Regel `^(SECRET_KEY|AUTH_JWT_SECRET|FIELD_ENCRYPTION_KEY|[A-Z_]*API_KEY|[A-Z_]*PASSWORD)=\S{12,}` (Ausnahmen `*.example`, Testdateien). `.gitignore` deckt `.env.bak*` (bzw. `.env*` mit `!.env.example`). Neuer Test `scripts/test_gitignore_env.py` (`git check-ignore .env.bak-x` → ignoriert) wird im selben PR an einen CI-Job angebunden (`agent-templates-test` oder neuer Schritt), da `scripts/test_*.py` sonst nicht laufen (RB-D18).“
- **Ziel D3.2:** „`setup.sh` legt Backups nur außerhalb des Repos ab.“
- **PR P1-4:** `fix/secret-scan-env-secrets`, `fix(ci): scan pull requests for env secrets`, grün auf `secret-scan`, `workflow-lint`, Reviewer `security-auditor`. Merge in der `ci.yml`-Queue nach P1-3.
- **Tests:** Negativnachweis im PR (Testdatei mit Dummy-Geheimnis → Job rot, danach revertiert).
- **Hängt ab von:** Index §h (Sofortmaßnahme zuerst); ENT-X1.

**KA-D-04** · QR-S12 (mittel) · Stelle: D2.4, (vii) Risiko „Promptfoo-Lieferkette“
- **Ziel:** „`promptfoo/package.json` + `package-lock.json` pinnen Promptfoo 0.124.1; Installation `npm ci --ignore-scripts`; Job `permissions: {contents: read}`; `actions/checkout` mit `persist-credentials: false`; keine `secrets.*` im Job (Fernet-Testschlüssel wird im Job erzeugt); `export_promptfoo_configs --deep` bricht bei `CI=true` ab.“
- **Tests:** `test_deep_refused_in_ci`; Workflow-Lint-Test: Job `prompt-regression` enthält kein `secrets.`.

**KA-D-05** · QR-S02 (hoch) · **ENT-D2** · Stelle: (i) Nicht-Ziel „Keine Auth-/Tenant-Isolation im Hub“, (ii) Konflikt D1, D1.1, (ix) D-D2, P2-1
- **Ziel (bei ENT-D2 = B, Empfehlung Sicherheit):** „Der Hub läuft mit `BLUEPENCIL_AUTH_SECRET` (Compose-Secret bzw. `.env`, nie geloggt). nginx injiziert `proxy_set_header x-bluepencil-auth` über ein envsubst-Template und schützt `location /bluepencil/api/` mit `auth_request` gegen einen Session-Check-Endpunkt (z. B. `GET /api/v1/auth/me/`). Kein Host-Port.“
- **Ziel (bei ENT-D2 = A′):** „Schriftliche Risikoakzeptanz im Plan; Profil `bluepencil` nur auf QS; Sandbox-Port aus `deploy/docker-compose.sandbox.yml` entfernt.“
- **Tests:** `test_hub_runs_with_auth_secret` (Contract), `test_nginx_bluepencil_location_requires_auth_request`, Smoke `curl /bluepencil/api/notes` ohne Session → 401, mit Session → 200.
- **Hängt ab von:** ENT-D2, ENT-C4; Sicherheitsgate vor Welle 2.

**KA-D-06** · QR-S15 (niedrig) · **ENT-D9** · Stelle: D6.2, (vi) Zeile D6.2
- **Ziel (vorläufig ENT-D9 = B):** „Das Default-Passwort gibt es nur mit explizitem Opt-in `SEED_DEMO_ALLOW_DEFAULT_PASSWORD=1` (Test-Compose/CI), unabhängig von DEBUG. Ohne Opt-in und ohne `SYSTEM_ADMIN_PASSWORD`/`DEMO_ADMIN_PASSWORD` → `CommandError`.“ CI-/E2E-Umgebung (`playwright.yml`) setzt die Variable im selben PR.
- **Tests:** `test_default_password_requires_explicit_opt_in_even_with_debug`.

**KA-D-07** · QR-S17 (niedrig) · Stelle: D1.0, (vi) Zeile D1.0
- **Ziel:** „`check-nginx-headers.sh` prüft zusätzlich: `script-src` ohne `'unsafe-inline'`/`'unsafe-eval'`, CSP enthält `frame-ancestors 'none'`. Smoke-Image `nginx:1.27-alpine` per Digest gepinnt. CSP-Verletzung → Revert, nie Aufweichen von `script-src`.“
- **Tests:** Negativfall im Job `nginx-headers-smoke` (manipulierte CSP → Exit 1).

**KA-D-08** · QR-S18 (niedrig) · Stelle: D4.1
- **Ziel:** „Beispiele nur mit exakt gepinnter Version ≥ 0.1.16: `npx -y mcp-remote@<x.y.z>`.“
- **Tests:** `test_doc_surface_consistency.py` verbietet `npx (-y )?mcp-remote(?!@\d)`.

**KA-D-09** · QR-S22 (niedrig) · Stelle: D3.3, (vi) Zeile D3.3
- **Ziel:** „Vor `down -v`: neueste Datei in `BACKUP_OFFHOST_DIR` jünger als 5 min, > 0 Byte, `gzip -t` ok, `zcat | head` enthält `PostgreSQL database dump`; sonst Abbruch.“
- **Tests:** `make -n wipe` plus Shell-Test mit leerer Datei → Abbruch (CI-angebunden, siehe KA-D-03-Hinweis RB-D18).

**KA-D-10** · QR-T19 (mittel) · Stelle: Kopf „Wellen“, WP D6 Überschrift, (v), (xii) Zeile D6.2, (xiii) P3-1
- **Ziel:** „D6.2 (PR P3-1) läuft in **Welle 3** vor Plan E P3-5 (E3.8); D6.1 bleibt Welle 4.“ Planbasis führt D6 nicht explizit in einer Welle („Rest“).

**KA-D-11** · QR-T20 (mittel) · Stelle: (v) Plan→Plan, (xii) Zeilen D1.1/D3.4, (xiii) P2-1, P3-4
- **Ziel:** „Compose-Queue: A PR-A2 → D P2-1 → G PR 13 → D P3-4.“ P2-1 Eintritt zusätzlich „A PR-A2 gemergt“.

**KA-D-12** · QR-T17 · Stelle: (xiii) Spalten „grün auf“ (P1-1, P2-2: `nginx-headers-smoke`; P3-3: `workflow-lint (n/a)`; P3-5/P3-6: `client-artifacts`)
- **Ziel:** P1-1 definiert `nginx-headers-smoke` (erst ab Merge Check für andere PRs); P3-3 „`lint` entfällt (kein Frontend), Shell-Test laut KA-D-09“; `client-artifacts` „läuft nur bei Pfadtreffer“; `lint` = ESLint.

**KA-D-13** · Entscheidungsverweise, KA-ALL-11 · Stelle: (ix), (ii), Eintritte, (xii) D1.2 (`frontend-developer`)
- **Ziel:** D-D1 → ENT-D1, D-D2 → ENT-D2, D-D3 → ENT-D3, D-D4 → ENT-D4, D-D5 → ENT-D5, D-D6 → ENT-D6, D-D7 → ENT-D7, D-D8 → ENT-D8, neu ENT-D9; Rolle `frontend-component-engineer`.

---

## E — Plan E Security/API (14)

**KA-E-01** · QR-T03 (hoch), QR-T04 · Stelle: Kopf „Migrations-Reservierung“, E3.1, (v) Plan→Plan, (xii) Zeile E3.1, P3-2 Rollback, Verifikation E3.1
- **Ziel (Mapping):** `auth_tenancy 0028_user_mfa` → **`0031_user_mfa`** (Index §e; Plan C belegt 0028–0030 in Welle 1/2); `audit 0016_alter_auditentry_op_mfa` bleibt. P3-2 Rollback: `migrate auth_tenancy 0030_backfill_show_readable_ids` (bzw. zuletzt gemergte Vorgängerin), `migrate audit 0015_alter_auditentry_op`.

**KA-E-02** · QR-T14 (mittel) · Stelle: (v) Plan→Plan („E2 vor G1 oder Rebase“), (xii) Matrix, (xiii) P1 Spalte „Merge-Reihenfolge“
- **Ziel:** „Welle-0-Queue `rest_api/views.py`: E P1-1 → E P1-2 → E P1-4 → **Plan G PR 5 (G1.5)** → E P1-3 → E P1-7 (P1-7 zusätzlich nach P1-5).“

**KA-E-03** · QR-T19 (mittel) · Stelle: E3.8, (xii) Zeile E3.8, P3-5 Eintritt
- **Ziel:** „Eintritt E3.8: Plan D P3-1 (D6.2, `seed_demo`-Guard) gemergt; `seed_demo.py`/`test_seed_demo.py` werden rebased.“

**KA-E-04** · QR-S01 (hoch) · **ENT-E7** · Stelle: E3.4, E3.6 (Tabelle `enroll`/`confirm`)
- **Ziel (vorläufig keine Umsetzung bis ENT-E7; Empfehlung A):** „Eine Enroll-Challenge wird nur ausgestellt, wenn für den User ein gültiger, einmaliger Enrollment-Grant existiert (angelegt durch Admin-Aktion oder `mfa_reset`, TTL ≤ 24 h, Audit `user.mfa_enroll_grant`). Ohne Grant: 403 `MFA_ENROLLMENT_REQUIRES_GRANT`, kein Login.“ Bei ENT-E7 = B: Grace-Fenster für Konten jünger als N h + Benachrichtigung, Risikoakzeptanz im ADR-021-Nachtrag.
- **Tests:** `test_required_unenrolled_staff_cannot_self_enroll_without_grant`, `test_enroll_grant_is_single_use_and_expires`, `test_enroll_via_challenge_writes_audit_with_source_challenge`.
- **Hängt ab von:** ENT-E7; Sicherheitsgate vor Welle 3. Migration für den Grant (falls Tabelle) folgt Index §e (auth_tenancy max+1, im PR P3-2).

**KA-E-05** · QR-S10 (mittel) · Stelle: E3.3
- **Ziel:** „Ist `mfa_required(user)` wahr und fehlt `otp` in `amr`, verweigert `RefreshView` mit 401 `MFA_STEP_UP_REQUIRED`.“
- **Tests:** `test_refresh_without_otp_rejected_when_required`.

**KA-E-06** · QR-S11 (niedrig) · Stelle: E3.2 Regel 4 (Recovery-Lookup), Challenge-Behandlung
- **Ziel:** „Lookup immer `UserRecoveryCode.objects.select_for_update().get(user=user, code_hash=…)`. Die Challenge-Nonce wird nach Erfolg bis Ablauf der TTL als verbraucht gecacht.“
- **Tests:** `test_recovery_code_of_other_user_rejected`, `test_mfa_challenge_single_use`.

**KA-E-07** · QR-S10 (mittel) · **ENT-E8** · Stelle: neue Task **E3.9** (nicht E3.7 — E3.7 ist bereits `mfa_reset`), (v) Task→Task, (vi) „E3 Einführung“, P3-Tabelle (PR P3-2 oder eigener PR)
- **Ziel:** „Command `mfa_enforce_cutover` widerruft Staff-Refresh-Tokens und Django-Admin-Sessions und listet Staff-API-Keys (Wiederverwendung `inventory_api_keys`). Er läuft im Runbook vor dem Umschalten auf `required`.“ Staff-Key-Regel nach ENT-E8 (vorläufig A: Inventur + `expires_at`-Pflicht für neue Staff-Keys).
- **Tests:** `test_cutover_revokes_staff_sessions`, `test_cutover_lists_staff_api_keys`.

**KA-E-08** · QR-S20 (niedrig) · Stelle: E2.3 (TDD)
- **Ziel:** „Titel und UID des Link-Ziels nur, wenn der Aufrufer READ auf den Ziel-Workspace hat, sonst `null`/`'—'`.“
- **Tests:** `test_retrieve_roleless_workspace_is_403_or_404`, `test_retrieve_hides_target_title_of_unreadable_workspace`, gefencter Key auf Fremd-Workspace-Link → 403.

**KA-E-09** · QR-T12 (mittel) · Stelle: E2.7, (vii) Risiko „Ratchet zu laut“
- **Ziel:** „`openapi_warning_baseline.json` ist ab P1-7 plan-übergreifende Konfliktdatei: jeder REST-PR aller Pläne aktualisiert sie (nur Shrink), Merge seriell (Index §d.2). Neue Einträge sind ein Fehlschlag; der PR löst sie durch `serializer_class`/`@extend_schema`.“

**KA-E-10** · QR-T08 · Stelle: E1.3 („`tool_count` bleibt 248“)
- **Ziel:** „Delta 0 Tools; geänderte Tool-Beschreibung → `export_tool_manifest`; Doku-Zähler unverändert (KA-ALL-03).“

**KA-E-11** · QR-T17, KA-ALL-11 · Stelle: E3.0 („`dependency-check`“), (xiii) P3-1 „grün auf“, P3-5 Reviewer `ux-reviewer`, E3.8 Rolle `frontend-developer`
- **Ziel:** E3.0: „`dependency-check` = manueller Paved-Road-Lauf (`dependency-auditor`), Ergebnis im PR-Kommentar; CI-Nachweis über pip-audit in `backend-test` `set-1-core`.“ Rollen `ui-reviewer`, `frontend-component-engineer`.

**KA-E-12** · QR-T13 (mittel) · Stelle: E2.5, E2.6
- **Ziel:** Plan-übergreifende Regel ergänzen: „Neue mutable Typen anderer Pläne setzen `etag_supported=True` nur mit `version`-Feld und `expected_version` im Service; sonst `etag_supported=False` mit ehrlicher 412-Zusage (E2.6). Betroffen: Plan B B6, Plan F F2/F3.“

**KA-E-13** · Sicherheitsreview „Offene Risiken“ 2/3 · **ENT-E6**, **ENT-E8** · Stelle: (i) Nicht-Ziele (Keys), (vi) „E3 Einführung“, E3.0 (ADR-021-Nachtrag)
- **Ziel:** „Übergangsfenster bis `required` ist befristet (Datum im ADR-021-Nachtrag, ENT-E6). Staff-API-Keys ohne zweiten Faktor sind ein akzeptiertes Restrisiko mit Inventur und Ablaufpflicht (ENT-E8).“

**KA-E-14** · Entscheidungsverweise · Stelle: (ix), (ii) Konflikt
- **Ziel:** D-E2a → ENT-E1, D-E2b → ENT-E2, D-E2c → ENT-E3, D-E2d → ENT-E4, D-E3a → ENT-E5, D-E3b → ENT-E6, neu ENT-E7, ENT-E8; Gate „Sign-off `pyotp`“ = Nutzer-Gate U-2.

---

## F — Plan F Dokumente & Baselines (14)

**KA-F-01** · QR-T01, QR-T02, QR-T04 · Stelle: Migrations-Reservierung, (vi), (v) Plan→Plan, (xii) Matrix (F1.1-T2, F2-T1, F2-T3, F3-T*), (xiii) PR-F2/F9/F14/F16/F19/F22/F23/F25/F26 (Rollback)
- **Ziel (Mapping):** link_types `0012_seed_issue_risk_link_types` → **0013**, `0013_seed_document_link_types` → **0014**, `0014_merge_work_item_pairs` → **0015**; persistence `0130_document`/`0131_…rls` → **0122/0123**, `0132_work_item`/`0133_…rls` → **0124/0125**, `0134_inline_anchor`/`0135_…rls` → **0126/0127**; Puffer 0136–0139 streichen (F5 nimmt max+1); application 0037/0038, baseline 0012/0013, workflow 0024/0025 bleiben. F1.1-T2 Abhängigkeit: „nach `link_types 0012_seed_performs_and_satisfies_function_pair` (Plan B)“. Bei ENT-F1 = a rückt F2-T3 auf 0013.
- **Hängt ab von:** Index §e; ENT-F1.

**KA-F-02** · QR-T10 (mittel) · Stelle: WP F2 (kind-Bindung `evidences`), (v) Plan→Plan „B3-T2 … falls `evidences` kind-gebunden“
- **Ziel:** „F2 registriert `Document → kind` im generischen Subtyp-Register aus B3-T2 (KA-B-08); Wire-Format `Document:<kind>`. Keine Änderung an der B-Validierung.“

**KA-F-03** · QR-T27 (niedrig) · Stelle: (xiii) PR-F3
- **Ziel:** PR-F3 teilen: **PR-F3a** `fix/diagram-expose-artifact-id` (F1.2-T1, additiv) vor **PR-F3b** `fix/diagram-require-workspace` (F1.2-T2, Breaking, Release-Note).

**KA-F-04** · QR-S09 (mittel) · Stelle: F4.2, F4.4 (R2, R6, MCP `baseline.rollback_apply`)
- **Ziel F4.2:** „`BaselineTag.workspace_id` wird ausschließlich aus `baseline.workspace_id` abgeleitet (optional DB-Check/Trigger). Neue Detailrouten übergeben den Objekt-Workspace an `_check_preset` und deklarieren `entity_key` in `resource_scope`.“
- **Ziel F4.4:** „`apply` sperrt den CR per `select_for_update()` und prüft den Status in derselben Transaktion; zweiter Aufruf → 409. Preview blendet READ-gesperrte Items aus; Apply bricht bei fehlendem WRITE ab. `rollback_apply` nur für `principal_type=user`.“
- **Tests:** `test_tag_workspace_derived_from_baseline`, `test_concurrent_apply_same_cr_only_one_succeeds` (zwei Threads, `transaction=True`), `test_preview_hides_item_permission_none`, `test_agent_key_cannot_apply_rollback`, `test_fenced_key_cannot_tag_foreign_workspace_baseline`.
- **Hängt ab von:** Sicherheitsgate vor Welle 3.

**KA-F-05** · QR-T08 · Stelle: F1.2-T1/T2, F4.2, F4.4, F2-T6, F3-T6, WP-Vorspann („Manifest: … Absolute Tool-Z…“)
- **Ziel:** KA-ALL-03 vollständig (Doku-Guards, `render.py`, `project.yaml`), Deltas je PR.

**KA-F-06** · QR-T12 · Stelle: F1.2-T1 (`DiagramResponseSerializer`), F4.2, F4.4 (`rollback-*`-Actions)
- **Ziel:** KA-ALL-04; Actions mit `@extend_schema` (Request/Response), Baseline nur Shrink.

**KA-F-07** · QR-T25 (niedrig) · Stelle: F1.1-T2 (Link-Typ-Zahl), F2-T3, F3 (`DOC-P5`/`DOC-P7`), P1-Austritt („`13 passed`“), P4-Austritt
- **Ziel:** Mengen-Zugehörigkeit statt Gesamtzahl; Linkability-Matrix parametrisiert über die Registry (`artifact_backing.py`), Austritt „alle Registry-Typen passed“.

**KA-F-08** · QR-T13 · Stelle: F2-T5, F3-T5
- **Ziel:** „`etag_supported` nur mit `version`-Feld + `expected_version` (Regel KA-E-12).“
- **Hängt ab von:** ENT-E2.

**KA-F-09** · KA-ALL-11 · Stelle: F4.0 (`se-architect`), PR-F7 (`se-critic`), PR-F10/F12/F20/F27 (`ux-designer`), „developer (Frontend)“
- **Ziel:** Rollen laut Index §g; ADR-025 über „Rolle laut ENT-X4 + Nutzer“.

**KA-F-10** · Entscheidungsverweise · Stelle: (ix), Eintritte P1–P4
- **Ziel:** K-F0 → ENT-F0, K-F1 → ENT-F1, K-F2 → ENT-F2, K-F3 → ENT-F3, K-F4 → ENT-F4, K-F5 → ENT-F5, K-F6 → ENT-F6.

**KA-F-11** · KA-ALL-10 · Stelle: F4.2 (Tag-Filter-Liste), F2-T5 (Dokumentliste), F3 (WorkItem-Liste)
- **Ziel:** DoD „deterministisch sortiert“.

**KA-F-12** · QR-T21, Index §d.2 · Stelle: (v) Plan→Plan, F4.3/F4.5
- **Ziel:** „CSS-Änderungen in F4.3/F4.5 unterliegen C1-Check und Ratchet (nur senken). `BaselinesView.tsx`: nach Plan C PR-C13 und Plan G PR 15.“

**KA-F-13** · QR-S19 · Stelle: F4.2, F2-T1, F3-T1, F3-T7 DoD
- **Ziel:** „`CreateModel` und RLS-Policy im selben PR; `persistence/tests/test_rls_coverage.py` (bzw. Baseline-Pendant) grün.“

**KA-F-14** · Index §e (ADR-Nummern) · Stelle: F4.0 („nächste freie Nummer … Index konsolidiert“)
- **Ziel:** „ADR-025 (Index §e, ADR-Nummern); Nummer beim Merge gegen `docs/se/ADR/` prüfen.“

---

## G — Plan G QA-Härtung (16)

**KA-G-01** · QR-T01, QR-T30 · Stelle: §13, §5 Matrix (G1.3, G2.2), §6 P2 PR 7, §4
- **Ziel (Mapping):** persistence `0116_entity_workspace_fk_backfill`, `0117_uid_workspace_unique_constraints` bleiben; `0118_requirement_list_index` → **`0119_requirement_list_index`** (Plan A belegt 0118 in Welle 1). link_types/attribute_definitions 0010 bleiben (G zuerst). application: „nur bei ENT-G3 = B: `0036_outbox_workspace_fk` in Welle 0; Plan A/F verschieben sich um +1 (Index §e).“

**KA-G-02** · QR-T04 (hoch) · Stelle: G1.3 TDD 4/5, §6 PR 3, PR 4, PR 7, G1.4 TDD 3
- **Ziel:** G1.3 TDD 5: „Roundtrip `0117_uid_workspace_unique_constraints` → `0115_workspace_glossary_reference_mode` → `0117_…` per Namen.“ PR 3: `migrate persistence 0115_workspace_glossary_reference_mode`; PR 4: `migrate link_types 0009_backfill_need_satisfies_pair`, `migrate attribute_definitions 0009_backfill_requirement_rationale_source`; PR 7: `migrate persistence 0118_embedding_model_columns` (Vorgängerin laut Index).

**KA-G-03** · QR-T14 (mittel) · Stelle: §5 Matrix (G1.5, G2.1), §4, §6 P1 PR 5 „unabhängig; vor PR 6“
- **Ziel:** „G1.5 (PR 5) merged in der Welle-0-Queue `views.py` nach Plan E P1-4 (Reihenfolge E P1-1 → P1-2 → P1-4 → G PR 5 → E P1-3 → P1-7); G2.1 (PR 6) nach G1.5.“

**KA-G-04** · QR-T17 (mittel, Fehlbeleg) · Stelle: §6 PR 11 (`client-smoke`), PR 13 (`build, e2e, dependency-check`), PR 17 (`frontend-test, build, dependency-check`), P3-Austritt („`dependency-check` ohne high/critical“), P5-Austritt
- **Ziel:** PR 11: „`client-smoke` per `workflow_dispatch` manuell auslösen, Lauf im PR verlinken.“ PR 13/17: „grün auf `lint`, `frontend-test` (npm audit), `backend-test` `set-1-core` (pip-audit), `e2e` (Frontend-Prod-Image); Backend-Image: lokaler `docker build` durch `devops-engineer`, Log im PR; `dependency-check` = manueller Paved-Road-Lauf (`dependency-auditor`), Ergebnis im PR-Kommentar.“

**KA-G-05** · QR-T09 (hoch) · **ENT-C6**, **ENT-G4** · Stelle: G4.3 (Änderungen, DoD), §8 Risiko „G4.3 kollidiert mit Plan C C1“
- **Ziel (nach ENT-C6, Empfehlung B):** „G4.3 nutzt das Token der C1-Höhenskala (`--btn-h-xs: 24px`; `--target-min` ist Alias darauf). `.deleteButton`, `.copyButton` sind Icon-Buttons im Sinne des C1-Gates. DoD ‚Design-System-Ratchet unverändert grün‘ gilt damit ohne Ausnahme.“ Eintritt PR 16: „Plan C PR-C12 gemergt (C1 vollständig), ENT-C6 und ENT-G4 entschieden.“
- **Hängt ab von:** ENT-C6, ENT-G4; KA-C-05.

**KA-G-06** · QR-T21 (mittel) · Stelle: §5 Matrix Zeile G4.3, §6 PR 16
- **Ziel:** Konfliktdatei `design-system-ratchet.baseline.json` eintragen; „Merge nach den C1-PRs (PR-C2 → PR-C5 → PR-C12 → PR-C13), Deckel nur senken.“

**KA-G-07** · QR-T20 (mittel) · Stelle: G3.3 (Verifikation `grep -v node:22-slim`), §5 Zeile G3.3, §11 R11, §6 PR 13
- **Ziel:** „Compose-Queue A PR-A2 → D P2-1 → G PR 13 → D P3-4. Ist D P2-1 gemergt, prüft die G3.3-Verifikation ohne `node:22-slim`-Ausnahme.“ PR 13 Eintritt „D P2-1 gemergt“.

**KA-G-08** · QR-T28 (niedrig) · Stelle: Kopf-Tabelle „Status“
- **Ziel:** „proposed — 4 Nutzerentscheidungen offen (E-G1…E-G4, §10)“.

**KA-G-09** · QR-S16 (mittel) · **ENT-G2** · Stelle: G1.4 (Migrationen, Command, Reverse), §7 „Vor P1-Migrationen“, §6 PR 4 Rollback
- **Ziel (vorläufig ENT-G2 = A+):** „Die Migration schreibt zu löschende Zeilen vorher in `lt_workspace_definition_orphan_archive` bzw. `ad_workspace_definition_orphan_archive` (gleiche Spalten + `archived_at`); Reverse stellt sie wieder her. `cleanup_workspace_orphans` verweigert den Lauf ohne BYPASSRLS-Rolle oder ohne Iteration je Tenant und bricht ab, wenn `count(pl_workspace)=0` bei `count(definitions)>0`. Löschen nur mit `--confirm-count=<n>` aus dem Dry-Run.“ Archivtabellen bekommen RLS bzw. sind begründet global (im Plan festhalten).
- **Tests:** `test_orphan_delete_is_archived_and_reversible`, `test_cleanup_aborts_without_rls_bypass`, `test_cleanup_requires_matching_confirm_count`.
- **Hängt ab von:** ENT-G2, ENT-G3.

**KA-G-10** · QR-T02 · Stelle: G1.4 DoD, §4 Plan→Plan
- **Ziel:** „Nach G1.4 legen alle Tests, die Typdefinitionen erzeugen, echte `Workspace`-Zeilen an; gilt auch für Plan B/F-Seed-Migrationstests (`link_types 0011ff.`, `attribute_definitions 0011`).“

**KA-G-11** · Technischer Review §5 · Stelle: G2.1, §4 Plan→Plan
- **Ziel:** „`filterwarnings error::UnorderedObjectListWarning` gilt global; neue Listen aus Plan A/B/C/F müssen sortieren (KA-ALL-10). Ein Verstoß ist ein Testfehler im verursachenden PR, kein Grund, G2.1 zu lockern.“

**KA-G-12** · Technischer Review §4 · Stelle: §4 (G2.4 ↔ A0), §5 Zeile G2.4, §6 PR 9
- **Ziel:** „G2.4 (PR 9/10) nach Plan A PR-A2/PR-A3 (Welle 1); nie parallel.“

**KA-G-13** · QR-T12 · Stelle: G1.5 (`extend_schema` auf 18 `destroy`)
- **Ziel:** „PR 5 aktualisiert `openapi_warning_baseline.json` (Shrink) im selben PR; Merge nach E P1-7 oder Rebase.“

**KA-G-14** · Entscheidungsverweise · Stelle: §10, §1, §6 P1/P4-Eintritt
- **Ziel:** E-G1 → ENT-G1, E-G2 → ENT-G2 (inkl. Archiv-Option A+), E-G3 → ENT-G3, E-G4 → ENT-G4.

**KA-G-15** · KA-ALL-09 · Stelle: §6 Vorspann
- **Ziel:** Hinweis `secret-scan`-Abdeckung; keine `git add -A`.

**KA-G-16** · KA-ALL-06 · Stelle: §6 P1 Austritt (SQL „→ `8`“), PR-Tabellen
- **Ziel:** Absolutzahl der Constraints beibehalten (fachlich fix: 8 Tabellen) — aber CI-Checks laut Index §f.2 benennen (`backend-test` mit Set-Angabe statt „backend-test (4 Sets)“ nur dort, wo wirklich alle Sets betroffen sind).
