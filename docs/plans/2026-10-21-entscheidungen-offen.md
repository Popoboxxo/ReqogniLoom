---
type: Plan
title: "Offene Entscheidungen — Backlog-Umsetzung A–G (für den Nutzer)"
scope: "Alle „Entscheidung nötig“-Punkte der Pläne A–G und der Querreviews TECHNISCH/SICHERHEIT, konsolidiert"
status: proposed
date: 2026-10-21
author_agent: senior-developer
language: de
index: docs/plans/2026-10-21-backlog-umsetzung-index.md
---

# Offene Entscheidungen — Backlog-Umsetzung A–G

> **Nur formuliert, nicht entschieden.** Jeder Punkt nennt Frage, Optionen, Empfehlung (aus Plan
> bzw. Review), Folge bei Nichtentscheidung und blockierte Arbeitspakete. Die Empfehlung ist
> keine Entscheidung.
>
> **⚠ KONFLIKT** markiert Punkte, an denen Planbasis, ADR-Entwurf, Plan oder Review einander
> widersprechen. Die Planbasis-Entscheidungen selbst stehen **nicht** zur Disposition; offen ist
> jeweils nur der Umgang mit dem Widerspruch.
>
> **Vorläufig:** „ja“ = der Plan darf bis zur Entscheidung mit der Empfehlung weiterplanen und
> vorbereitende Tasks umsetzen. „nein“ = die blockierten WPs starten erst nach Entscheidung.
>
> IDs: `ENT-<Plan><n>`; `X` = plan-übergreifend, `V` = Reihenfolge. Quelle in Klammern
> (Plan-ID bzw. Review-Befund). Wellen und WPs siehe
> [Plan-Index](2026-10-21-backlog-umsetzung-index.md).

**Zählung:** 54 Entscheidungen (Welle 0: 10 · Welle 1: 8 · Welle 2: 12 · Welle 3: 15 · Welle 4: 9),
davon 21 als ⚠ KONFLIKT markiert. Dazu 6 Nutzer-Gates (Handlungen ohne Optionswahl, §6).

---

## 0. Entschieden am 2026-10-22 (Nutzer)

Diese vier Welle-0-Blocker sind entschieden. Die Angabe „Vorläufig: nein“ in den
betreffenden Abschnitten ist damit überholt; maßgeblich ist diese Tabelle.

| ID | Frage | Gewählt | Folge |
|---|---|---|---|
| ENT-X1 | `.env.bak-*` je geteilt? | **A — nie geteilt** | Keine Rotation; `.gitignore` härten (`.env*`, `!.env.example`). Die Backup-Dateien sind nicht mehr im Arbeitsbaum. |
| ENT-G1 | Soft-Delete-Vertrag | **A — `GET` 200 + `status:"outdated"` für alle Typen** | ArchitectureElement von 404 auf 200 angleichen (GH-443-Vertrag). G1.5/PR 5 startet. |
| ENT-G2 | Definitions-Waisen | **A+ — Archiv + FK** | `*_orphan_archive` vor Löschung, Reverse stellt wieder her, Cleanup nur mit BYPASSRLS und `--confirm-count` (QR-S16). G1.4/PR 4 startet. |
| ENT-G3 | Outbox-Waisen | **A — O-2 bleibt, keine FK** | Keine FK, keine Löschung auf `application`-Outbox-Zeilen. G1.4/PR 4 startet. |

Damit sind Welle 0 sowie die Migrationsketten `persistence 0116/0117`,
`link_types 0010` und `attribute_definitions 0010` freigegeben. Weiterhin offen
und startblockierend für ihre jeweiligen WPs: alle übrigen `ENT-*` mit
„Vorläufig: nein“.

---

## 1. Blockiert Welle 0 (vor Start klären)

### ENT-X1 — Schlüsselrotation nach `.env.bak-*`-Fund (QR-S03)
- **Plan:** übergreifend (Index §h)
- **Frage:** Drei ungetrackte `.env.bak-*` mit Produktionsgeheimnissen liegen im Repo-Root eines öffentlichen Repos. Waren sie je geteilt, synchronisiert oder in einem Commit?
- **Optionen:** A) nie geteilt → nur verschieben + `.gitignore`; B) möglicherweise geteilt → zusätzlich alle Geheimnisse rotieren (`FIELD_ENCRYPTION_KEY` mit Re-Encrypt-Plan).
- **Empfehlung:** A, falls sicher nie geteilt; sonst B.
- **Folge bei Nichtentscheidung:** Jeder `git add -A` eines Agenten kann Geheimnisse veröffentlichen; CI-`secret-scan` bleibt grün.
- **Blockiert:** Start Welle 0 (alle Agentenläufe mit `git add`).
- **Vorläufig:** nein (Sofortmaßnahme vor Welle 0).

### ENT-G1 — Soft-Delete-Vertrag für alle Typen (E-G1)
- **Plan:** G (G1.5)
- **Frage:** Welcher Vertrag gilt nach `DELETE` für alle Artefakttypen?
- **Optionen:** A) GH-443 beibehalten (`GET` 200 + `status:"outdated"`), ArchitectureElement angleichen (404 → 200); B) `GET` 404 für alle, Zugriff nur über `?include_deleted=true`; C) Status quo + Doku.
- **Empfehlung:** A.
- **Folge bei Nichtentscheidung:** G1.5 startet nicht; G2.1, G5.3, F2-T5, F4.4 verschieben sich (Queue `views.py`).
- **Blockiert:** G1.5 (PR 5), G2.1, G5.3; indirekt F4.4.
- **Vorläufig:** nein (sichtbare API-Änderung).

### ENT-G2 — Waisen in `lt_/ad_workspace_definition` löschen? (E-G2, QR-S16, Sicherheits-Risiko 7)
- **Plan:** G (G1.4)
- **Frage:** Dürfen verwaiste Typdefinitionen (QA: 209 + 23) gelöscht werden, und wie reversibel?
- **Optionen:** A) Löschen in der Migration nach Backup; A+) wie A, aber vorher in `*_orphan_archive` sichern, Reverse stellt wieder her, Cleanup-Command nur mit BYPASSRLS-Rolle und `--confirm-count` (QR-S16); B) nicht löschen, FK `NOT VALID`; C) keine FK.
- **Empfehlung:** Plan G: A; Sicherheitsreview: A+ (Archiv statt reinem Backup-Vertrauen).
- **Folge bei Nichtentscheidung:** G1.4 startet nicht → `link_types 0010`/`attribute_definitions 0010` fehlen → B1-T1, B2-T1, B3-T3, F1.1-T2 können ihre Migrationen nicht in der Index-Reihenfolge mergen.
- **Blockiert:** G1.4 (PR 4); Welle-3-Migrationsketten B/F.
- **Vorläufig:** nein (destruktiv).

### ENT-G3 — ⚠ KONFLIKT Outbox-Waisen: Issue #1403 vs. O-2 (E-G3)
- **Plan:** G (G1.4)
- **Konflikt:** Planbasis G1 nennt „323 hängende `workspace_id` ohne FK“ als einen Fix; 91 davon sind Outbox-Zeilen, für die O-2 (RLS-Spec #1136) „kein Delete“ festlegt.
- **Optionen:** A) O-2 bleibt: keine FK, keine Löschung; B) FK + CASCADE (überstimmt O-2, verliert Events); C) nur veröffentlichte Waisen löschen.
- **Empfehlung:** A.
- **Folge bei Nichtentscheidung:** G1.4 startet nicht (wie ENT-G2). Bei B verschiebt sich die `application`-Kette (Index §e).
- **Blockiert:** G1.4.
- **Vorläufig:** nein.

### ENT-D8 — ⚠ KONFLIKT „Mock-Provider“ für Promptfoo (D-D8)
- **Plan:** D (D2.2, D2.4)
- **Konflikt:** Planbasis D2 nennt „Mock-Provider“; der Projekt-`MockLlmProvider` ignoriert den Prompt und prüft nichts.
- **Optionen:** A) Promptfoo-Provider `echo` (Render-Regression, LLM-frei); B) eigener Python-Provider über `llm_adapter` (Mock liefert feste Antwort).
- **Empfehlung:** A.
- **Folge bei Nichtentscheidung:** D2 kann nicht final umgesetzt werden → Promptfoo-Gate fehlt → A1 (Welle 2) blockiert.
- **Blockiert:** D2.2, D2.4, Promptfoo-Gate, alle A1-Tasks.
- **Vorläufig:** ja (Planbasis-Ziel „LLM-frei“ bleibt gewahrt).

### ENT-E1 — Ziel für #1388 Schema-Beschneidung (D-E2a)
- **Plan:** E (E2.7, E2.8)
- **Optionen:** A) Ratchet + Burn-down bis 0; B) Ratchet + dauerhafte Allowlist.
- **Empfehlung:** A.
- **Folge bei Nichtentscheidung:** E2.7 läuft (Ratchet), E2.8 nicht planbar.
- **Blockiert:** E2.8 (Welle 2).
- **Vorläufig:** ja.

### ENT-E2 — ETag für alle mutablen Typen oder Zusage einschränken (D-E2b)
- **Plan:** E (E2.5, E2.6); wirkt auf B6-T2, F2-T5, F3-T5 (QR-T13)
- **Optionen:** A) Hybrid: ETag für 11 versionierte Typen, ehrliche 412-Zusage für 6 übrige; B) Versionsprüfung in 6 weiteren Services nachrüsten (+≈ 3 PT).
- **Empfehlung:** A.
- **Folge bei Nichtentscheidung:** E P1-2/P1-3 ohne festen Umfang.
- **Blockiert:** E2.5, E2.6.
- **Vorläufig:** ja.

### ENT-E3 — ⚠ KONFLIKT `baselines/`-Routenreihenfolge als Ursache von #1380 (D-E2c)
- **Plan:** E (E2.1)
- **Konflikt:** Planbasis E2 nennt die Routenreihenfolge; die Messung (E-L3) zeigt den Tenant-Fallback im Preset-Gate als Ursache.
- **Optionen:** A) Ursache beheben, Routen unverändert; B) zusätzlich Routen verschieben (wirkungslos, Risiko für `scope-preview/`).
- **Empfehlung:** A.
- **Folge bei Nichtentscheidung:** E P1-1 bleibt offen → F4.2/F4.4 (Welle 3) blockiert.
- **Blockiert:** E2.1, F4.2, F4.4.
- **Vorläufig:** ja (Planbasis-Ziel „Route erreichbar“ wird erfüllt).

### ENT-E4 — `If-Match` auf `DELETE` (D-E2d)
- **Plan:** E (E2.4)
- **Optionen:** A) 400 „nur PATCH/PUT“; B) auswerten (nicht atomar).
- **Empfehlung:** A.
- **Folge bei Nichtentscheidung:** E P1-2 ohne festen Vertrag.
- **Blockiert:** E2.4.
- **Vorläufig:** ja.

### ENT-X3 — Live-Belege versionieren? (QR-T18, Sicherheits-Nebenbefund/Risiko 8)
- **Plan:** alle (DoD-Artefakte unter `docs/test-reports/`, gitignored)
- **Frage:** Sollen die Plan-Belege `docs/test-reports/plan-review-2026-10-21/` versioniert werden, und wenn ja, anonymisiert?
- **Optionen:** A) anonymisieren (interne QS-Adressen → „QS“) und per `.gitignore`-Ausnahme (`docs/test-reports/*` + `!…/plan-review-2026-10-21/`) versionieren; B) DoD-Artefakte künftig nach `docs/se/reports/` bzw. `docs/reviews/` schreiben, alte Belege bleiben lokal; C) nicht versionieren, Nachweise nur im PR-Text/CI-Artefakt.
- **Empfehlung:** B für künftige DoD-Artefakte, A für die bestehenden Belege.
- **Folge bei Nichtentscheidung:** Plan-Belege bleiben für Reviewer nicht nachprüfbar; DoD-Pfade in allen Plänen bleiben auf einem ignorierten Ordner.
- **Blockiert:** DoD-Formulierungen aller Pläne (Korrekturauftrag KA-*-Belege).
- **Vorläufig:** ja (C als Übergang).

---

## 2. Blockiert Welle 1

### ENT-C6 — Button-Geometrie C1 vs. Trefferflächen G4.3 (QR-T09)
- **Plan:** C (T-C1-1), G (G4.3) · **Entscheider:** Design-Rolle (`design-system-architect`/`ui-ux-designer`), Nutzer bestätigt
- **Frage:** Wie passen 24-px-Icon-Buttons (WCAG 2.5.8) zur Regel „≤ 3 Button-Höhen je Route“?
- **Optionen:** A) `var(--target-min)` als zulässige Höhe für Icon-Buttons, E2E zählt sie gesondert; B) neues Token `--btn-h-xs: 24px` in der Höhenskala, Gate „≤ 3 Höhen ohne Icon-Buttons“; C) keine Ausnahme (G4.3 darf keine 24-px-Buttons einführen).
- **Empfehlung:** B (Review).
- **Folge bei Nichtentscheidung:** PR-C2 definiert ein Gate, das G4.3 später rot macht.
- **Blockiert:** PR-C2 (T-C1-1), G PR 16.
- **Vorläufig:** nein (vor PR-C2).

### ENT-C2 — ⚠ KONFLIKT #1257/#1263 in Q1 migrieren? (E-C2 / K-2 Plan C)
- **Plan:** C (Q1-Umfang)
- **Konflikt:** Planbasis Q1 nennt #1257 Nav-Baum als Verbraucher; #1257 ist geschlossen und hat einen eigenen 3-Ebenen-Store.
- **Optionen:** A) nicht migrieren, Q1 für Skalar-/Listen-Schlüssel; B) migrieren (Fassade, ≈ 3 PT, hohe Testlast).
- **Empfehlung:** A.
- **Folge bei Nichtentscheidung:** Q1-Umfang unklar; PR-C3 könnte unnötig wachsen.
- **Blockiert:** PR-C3 (Umfang), ggf. T-C2-10.
- **Vorläufig:** ja.

### ENT-C3 — Wer setzt Workspace-Defaults? (E-C3)
- **Plan:** C (Q1, T-C2-10)
- **Optionen:** A) so lassen (Q1 = Workspace-Admin, Baum/Formular = Editor); B) Baum/Formular auf Workspace-Admin + MCP-Tier angleichen (Breaking für Editoren); C) Q1 ebenfalls Editor.
- **Empfehlung:** B.
- **Folge bei Nichtentscheidung:** Inkonsistente Rechte bleiben; PR-C11 entfällt.
- **Blockiert:** PR-C11; bei C auch Q1-Kern (PR-C3).
- **Vorläufig:** ja für PR-C3 (Q1 = Workspace-Admin), nein für PR-C11.

### ENT-C5 — ⚠ KONFLIKT Migrationspfad bestehender Präferenz-Endpunkte (Planbasis O3, QR-T24)
- **Plan:** C (§2.3)
- **Konflikt:** Planbasis O3 verlangt „Migrationspfad klären“; Plan C führt es als „Fakten, keine Nutzerentscheidung“ (nur `show_readable_ids` wandert nach Q1).
- **Optionen:** A) Plan-C-Vorschlag: nur `show_readable_ids` nach Q1 (Fassade), `users/me/preferences/` und `notification-preferences` bleiben eigene Stores; B) zusätzlich `visible_metrics` nach Q1; C) alle User-Präferenzen langfristig nach Q1 (Fassaden, Contract später).
- **Empfehlung:** A.
- **Folge bei Nichtentscheidung:** O3 bleibt formal offen; T-C2-6/T-C2-9 ohne Mandat.
- **Blockiert:** T-C2-6, T-C2-9 (PR-C7, PR-C16).
- **Vorläufig:** ja.

### ENT-A1 — Honcho-Felder `peer_name`, `workspace_id`, `app_id` (E1 Plan A, QR-T24)
- **Plan:** A (T-A0b-3, T-A0b-5)
- **Frage:** Felder sind im UI sichtbar, werden vom Backend still verworfen. Was gilt?
- **Optionen:** a) persistieren und verwenden (verwaist bestehende Honcho-Daten); b) aus UI/API entfernen; c) nur anzeigen ohne Wirkung.
- **Empfehlung:** b. Bis zur Entscheidung: Felder weiter annehmen und als `deprecated` loggen, **nicht** mit 400 brechen (QR-T24).
- **Folge bei Nichtentscheidung:** T-A0b-3 läuft mit Übergangsverhalten; T-A0b-5 entfernt die UI-Felder nicht.
- **Blockiert:** endgültige Form von PR-A5/PR-A6.
- **Vorläufig:** ja, mit Übergangsverhalten.

### ENT-A4 — 57 verwaiste `mem_memory_entry`-Zeilen (E4 Plan A)
- **Plan:** A (T-A0-3)
- **Optionen:** a) behalten + dokumentieren; b) Admin-Command löscht; c) nach Honcho migrieren.
- **Empfehlung:** a.
- **Folge bei Nichtentscheidung:** keine Blockade; Zeilen bleiben.
- **Blockiert:** nichts Hartes (Doku in PR-A2).
- **Vorläufig:** ja.

### ENT-X5 — Lokal geänderte `.meta-config/project.yaml`
- **Plan:** übergreifend (Manifest-Regel Index §f.1; Plan B R-Risiko „erst nach Klärung anfassen“)
- **Frage:** Der Arbeitsbaum trägt uncommittete Änderungen an `.meta-config/project.yaml`. Committen, verwerfen oder getrennt halten, bevor Tool-PRs die Zähler dort nachziehen?
- **Optionen:** A) vorher über `agent-meta-manager` sauber committen (eigener PR); B) verwerfen; C) Tool-PRs ändern `project.yaml` nicht, Zählerabgleich gesammelt nach Welle 1.
- **Empfehlung:** A.
- **Folge bei Nichtentscheidung:** Der erste Tool-PR (C PR-C4) macht `test_meta_tool_count_drift.py` rot oder überschreibt fremde Änderungen.
- **Blockiert:** PR-C4 und jeder weitere Tool-PR.
- **Vorläufig:** nein.

### ENT-V1 — ⚠ KONFLIKT A3 in Welle 1 vorziehen?
- **Plan:** A (PR-A7, PR-A8)
- **Konflikt:** Planbasis §3 setzt A3 in Welle 2; Plan A P1 plant PR-A7/PR-A8 „parallel ab 1“ in Welle 1.
- **Optionen:** A) Planbasis-Welle 2 einhalten; B) Vorziehen als Lückenfüller erlauben (A3 ist abhängigkeitsfrei); C) generelle Regel: abhängigkeitsfreie WPs dürfen vorgezogen werden, wenn ein Slot frei ist.
- **Empfehlung:** B (nur A3), keine Generalregel.
- **Folge bei Nichtentscheidung:** A3 bleibt in Welle 2 (Index-Default).
- **Blockiert:** nichts; T-A2-6 braucht T-A3-1/2 ohnehin erst in Welle 2.
- **Vorläufig:** ja (Default Welle 2).

---

## 3. Blockiert Welle 2

### ENT-A2 — ⚠ KONFLIKT pgvector-Fallback vs. ADR-020 §4 (E2 Plan A)
- **Plan:** A (T-A2-7, P3-Eintritt)
- **Konflikt:** Planbasis A2 fordert „Fallback auf pgvector mit `degraded:true`“; ADR-020 (accepted) §4 sagt „kein Auto-Fallback“.
- **Optionen:** a) ADR-022 (Option B) löst ADR-020 §4 in diesem Punkt explizit ab; b) fail-loud wie heute (widerspricht Planbasis).
- **Empfehlung:** a.
- **Folge bei Nichtentscheidung:** P3 (A2) startet nicht.
- **Blockiert:** PR-A17 … PR-A22.
- **Vorläufig:** nein.

### ENT-X2 — ⚠ KONFLIKT ADR-Entwurfstexte ≠ Nutzerentscheidung (ADR-022/023/024, Planbasis O1)
- **Plan:** A (A1, A2, A4)
- **Konflikt:** ADR-022-Entwurf empfiehlt Option A (Qdrant abkündigen), Nutzer entschied B. ADR-023-Entwurf empfiehlt B (bedingter Ausbau), Nutzer entschied A (Vollausbau jetzt). ADR-024-Entwurf sieht ein eigenes `UserMemorySettings`-Modell vor, Nutzer entschied „über Q1“ (Plan A RB13).
- **Optionen:** A) Entwurfstexte an die Nutzerentscheidung anpassen, dann `accepted`; B) Entwürfe `superseded`, neue ADRs mit Nutzerentscheidung.
- **Empfehlung:** A (kein ADR-Wildwuchs; Audit-Trail über Git).
- **Folge bei Nichtentscheidung:** A1/A2/A4 starten ohne `accepted`-ADR (Planbasis O1 nicht erfüllt).
- **Blockiert:** A1 (ADR-024), A2 (ADR-022), A4 (ADR-023).
- **Vorläufig:** nein.

### ENT-X4 — SE-Rollen `se-architect`/`se-critic` nicht installiert
- **Plan:** A, B, F (ADR-Statuswechsel, Planbasis O1: „`se-architect` + Nutzer“)
- **Frage:** Wer bereitet ADR-Texte und Statuswechsel (ADR-004, -022, -023, -024, -025) vor, solange diese Rollen fehlen?
- **Optionen:** A) `documenter` (Text) + `concept-reviewer` (Review) + Nutzer (Statuswechsel); B) SE-Rollen per `agent-meta-manager` aktivieren; C) Nutzer selbst.
- **Empfehlung:** A.
- **Folge bei Nichtentscheidung:** ADR-gegatete Pakete (A1, A2, A4, B4, F4) haben keinen Ausführenden.
- **Blockiert:** ENT-X2-Vollzug, B4-T2, F4.0.
- **Vorläufig:** nein.

### ENT-A5 — ⚠ KONFLIKT Workspace-Memory-Ebene außerhalb Q1, ohne MCP (QR-T11)
- **Plan:** A (T-A1-3, T-A1-4), C (Register)
- **Konflikt:** Planbasis Q1 = „3-Ebenen-Präferenzdienst … REST+MCP … Nutzer: A1 Memory-Schalter“. Plan A legt die Workspace-Ebene in `WorkspaceMemorySettings` (Migration memory 0012) ohne MCP; zwei Schreibpfade für denselben User-Wert.
- **Optionen:** A) Workspace-Ebene als Q1-Schlüssel (`memory.disabled_slots` mit Ebenen global/workspace/user, `memory.allow_user_opt_out` workspace), `WorkspaceMemorySettings` nur Fassade; `/memory/me/settings/` als dünne Fassade über `PreferenceService.set_level`; B) Plan-A-Stand (eigene Spalten, REST-only) bewusst als Ausnahme von Q1 akzeptieren.
- **Empfehlung:** A.
- **Folge bei Nichtentscheidung:** T-A1-3/T-A1-4 nicht final; Migration memory 0012 ungewiss.
- **Blockiert:** PR-A11, PR-A12, PR-A15.
- **Vorläufig:** nein.

### ENT-A6 — ⚠ KONFLIKT Memory-Budget-Default und Datengrenzen (QR-S05)
- **Plan:** A (T-A1-6)
- **Konflikt:** Sicherheitsreview fordert `memory_max_chars`-Default 4000 und feste Datengrenzen `<memory>…</memory>` im Memory-Block; Planbasis A1: „`{memory_context}` bleibt unverändert“, Plan A: Default `0` = heute.
- **Optionen:** A) Datengrenzen und Default 4000 auch für `{memory_context}` (Verhaltensänderung); B) `{memory_context}` bytegleich lassen, Datengrenzen + Budget nur für die neuen Scope-Platzhalter, Budget per Workspace-Override aktivierbar; C) Datengrenzen für alle, Default bleibt 0.
- **Empfehlung:** C als Kompromiss (Injektionsschutz ohne stille Kürzung). Single-Pass-Rendering (`re.sub`) und `{`/`}`-Neutralisierung gelten unabhängig davon (keine Planbasis-Wirkung).
- **Folge bei Nichtentscheidung:** T-A1-6 ohne festen Vertrag; Sicherheitsgate „vor Welle 2“ offen.
- **Blockiert:** PR-A14.
- **Vorläufig:** nein.

### ENT-A7 — Risikoakzeptanz: Workspace verbietet Opt-out (Sicherheits-Risiko 4)
- **Plan:** A (T-A1-2, T-A1-4)
- **Frage:** Mit `allow_user_opt_out=false` wird persönliches User-Memory trotz Opt-out injiziert. Datenschutzrechtlich (Einwilligung, Zweckbindung) zulässig?
- **Optionen:** A) akzeptieren, im UI und in der Doku sichtbar machen; B) `user`-Scope bleibt bei Opt-out immer aus (nur Workspace-/Artefakt-Memory erzwingbar).
- **Empfehlung:** B (keine Fachempfehlung im Plan; Review sieht Nutzerbewertung als Pflicht).
- **Folge bei Nichtentscheidung:** Plan-A-Regel bleibt (A) ohne dokumentierte Akzeptanz.
- **Blockiert:** PR-A11, PR-A12.
- **Vorläufig:** nein.

### ENT-D1 — BluePencil Hub-/Layer-Version (D-D1)
- **Plan:** D (D1.1, D1.2)
- **Optionen:** A) 0.5.0 (QS-geprüft); B) 0.8.0.
- **Empfehlung:** A; 0.8.0 als eigener Bump danach.
- **Folge bei Nichtentscheidung:** D1 nicht pinbar.
- **Blockiert:** D P2-1, P2-2.
- **Vorläufig:** ja.

### ENT-D2 — ⚠ KONFLIKT Hub-Auth: Plan D vs. Sicherheitsreview (D-D2, QR-S02, Sicherheits-Risiko 1)
- **Plan:** D (D1.1), verknüpft mit ENT-C4
- **Konflikt:** Plan D empfiehlt A (Entrypoint umgehen, keine Auth); Sicherheitsreview stuft das als **hoch** ein (unauthentifizierte, mandantenlose Notiz-API inkl. MCP am Frontend-Port; Upstream-Schutz wird aktiv abgeschaltet).
- **Optionen:** A) keine Auth, kein Host-Port (Plan D); B) Image-Secret + nginx injiziert `x-bluepencil-auth` + `auth_request` gegen Session-Check (QR-S02); C) wie A, Hub-MCP nur über separaten Port mit Secret; A′) wie A mit schriftlicher Risikoakzeptanz, Profil nur QS, Sandbox-Port entfernt.
- **Empfehlung:** B (Sicherheitsreview); A′ nur mit dokumentierter Akzeptanz.
- **Folge bei Nichtentscheidung:** D1 (Welle 2) startet nicht.
- **Blockiert:** D P2-1, D P2-2.
- **Vorläufig:** nein.

### ENT-D3 — Lock-Bytes für den Layer (D-D3)
- **Plan:** D (D1.2)
- **Optionen:** A) Release v0.5.0; B) QS-Bytes (Herkunft unklar).
- **Empfehlung:** A.
- **Folge bei Nichtentscheidung:** Layer nicht reproduzierbar.
- **Blockiert:** D P2-2.
- **Vorläufig:** ja.

### ENT-C1 — ⚠ KONFLIKT Trace-Links im Inspector (E-C1 / K-1 Plan C)
- **Plan:** C (T-C3-1)
- **Konflikt:** Planbasis C3 fordert ein „Trace-Links-Widget“ im Inspector; REQ-L2-RF-037 („eine Fläche, eine Aufgabe“) blendet es bewusst aus.
- **Optionen:** A) TracePanel im Inspector auf allen 7 Routen; B) Inspector ohne Trace, TestCase bekommt `TraceLinkPanel` im Detailbereich; C) Trace-CRUD komplett in den Inspector (~3 d).
- **Empfehlung:** B.
- **Folge bei Nichtentscheidung:** PR-C10 entfällt; #801 bleibt offen.
- **Blockiert:** PR-C10.
- **Vorläufig:** nein.

### ENT-C4 — BluePencil in Produktion? (E-C4, Planbasis O2)
- **Plan:** C (#946), D (D1)
- **Optionen:** A) nein, QS-only → #946 schließen ohne Folge-Issue; B) ja → Folge-Issue im Upstream (RBAC, Tenant, Audit, Retention).
- **Empfehlung:** A.
- **Folge bei Nichtentscheidung:** #946 bleibt offen; ENT-D2 ohne Rahmen.
- **Blockiert:** #946-Abschluss; Rahmen für ENT-D2.
- **Vorläufig:** ja.

### ENT-G4 — Trefferfläche nativer Checkbox/Radio (E-G4)
- **Plan:** G (G4.3)
- **Optionen:** A) 18-px-Control + Label-Zeile ≥ 24 px (Abstands-Ausnahme); B) Controls selbst 24 × 24 px.
- **Empfehlung:** A.
- **Folge bei Nichtentscheidung:** G PR 16 startet nicht.
- **Blockiert:** G4.3, G5.2 (indirekt).
- **Vorläufig:** nein.

---

## 4. Blockiert Welle 3

### ENT-A3 — ⚠ KONFLIKT A4 hängt an T1, ADR-023 sagt „Vollausbau jetzt“ (E3 Plan A)
- **Plan:** A (P4)
- **Konflikt:** Planbasis A4 „abhängig von … T1“; Nutzerentscheidung Honcho Option A „Vollausbau jetzt“; T1 ist upstream blockiert (#1247/#1153).
- **Optionen:** a) ganz A4 erst nach T1 (faktischer Stillstand); b) nur dialektik-abhängige Teile hinter T1, Rest startet nach Spike T-A4-1.
- **Empfehlung:** b.
- **Folge bei Nichtentscheidung:** A4 wartet auf T1, ggf. unbegrenzt.
- **Blockiert:** PR-A24 … PR-A28.
- **Vorläufig:** nein.

### ENT-A8 — Risikoakzeptanz: Honcho/Qdrant als externe Verarbeiter, ohne API-Key (Sicherheits-Risiko 5, QR-S23)
- **Plan:** A (A2, A4)
- **Frage:** Memory- und Artefaktinhalte verlassen PostgreSQL/RLS; Isolation hängt an Collection-/Peer-Namen und Netz. Betrieb ohne `QDRANT_API_KEY`/`HONCHO_API_KEY` zulässig?
- **Optionen:** A) API-Key in Produktion Pflicht (System-Check-Warnung + Runbook, QR-S23); B) Betreiberentscheidung je Installation, nur Warnung.
- **Empfehlung:** A.
- **Folge bei Nichtentscheidung:** A2/A4 ohne verbindliche Betriebsvorgabe.
- **Blockiert:** PR-A21/PR-A22 (Runbook), A4-Rollout.
- **Vorläufig:** ja (Warnung umsetzen).

### ENT-A9 — Restrisiko Prompt-Injection bestätigen (Sicherheits-Risiko 6)
- **Plan:** A (A1), B (B5)
- **Frage:** Auch mit Datengrenzen bleibt LLM-Manipulation möglich. Bestätigt der Nutzer die Einordnung „B5 advisory only, AI-Review braucht menschliche Freigabe“?
- **Optionen:** A) bestätigen; B) zusätzliche Kontrollen fordern (z. B. Memory-Freigabe vor Injektion).
- **Empfehlung:** A.
- **Folge bei Nichtentscheidung:** Restrisiko nicht formal akzeptiert.
- **Blockiert:** B P3-Abschluss (Release-Notes), A1-Abschluss.
- **Vorläufig:** ja.

### ENT-B1 — ⚠ KONFLIKT B4 beschreibt erledigte Arbeit (K-1 Plan B)
- **Plan:** B (B4)
- **Konflikt:** Planbasis B4 nennt WS3/WS4/WS7 als Arbeit; alle drei sind erledigt (Issues geschlossen).
- **Optionen:** a) B4 auf Rest reduzieren (B4-T1…T3), #934/#941 schließen; b) Zusatzarbeit definieren.
- **Empfehlung:** a.
- **Folge bei Nichtentscheidung:** Plan B P1 startet nicht (Eintrittskriterium).
- **Blockiert:** Plan B P1 (PR-B1 … PR-B7).
- **Vorläufig:** nein.

### ENT-B3 — ⚠ KONFLIKT B5 hängt nicht hart an A1-HARD_OFF (K-3 neu, R-B5-2, QR-T24)
- **Plan:** B (B5-T2), A (T-A1-1)
- **Konflikt:** Planbasis: „B5 nutzt `HARD_OFF` aus A1.“ Plan B hebt die Abhängigkeit auf (Memory-Freiheit über fehlende Slot-Deklaration).
- **Optionen:** A) harte Abhängigkeit A1 → B5 wie Planbasis; B) weich: B5 darf vor A1 mergen; Folge: Custom-Templates mit `{memory_context}` auf `quality_*`-Slots lassen den Platzhalter literal stehen, bis A1 gemergt ist.
- **Empfehlung:** A (Wellenfolge erzwingt es ohnehin; kein Gewinn durch B).
- **Folge bei Nichtentscheidung:** keine Wirkung, solange A1 (Welle 2) vor B5 (Welle 3) merged.
- **Blockiert:** nichts Hartes.
- **Vorläufig:** ja.

### ENT-B4 — Auto-Modus der Qualitätsbewertung (E-3 Plan B)
- **Plan:** B (B5)
- **Optionen:** a) Folge-Issue v2, B5 manuell; b) Auto-Modus in B5 (+4–6 d).
- **Empfehlung:** a.
- **Folge bei Nichtentscheidung:** #378 bleibt nach PR-B18 offen.
- **Blockiert:** Abschluss #378.
- **Vorläufig:** ja.

### ENT-B5 — Priority-Abbildung MoSCoW (E-4 Plan B)
- **Plan:** B (B1-T4)
- **Optionen:** a) Must→high, Should→medium, Could→low, Won't→low; b) Must→critical, Should→high, Could→medium, Won't→low.
- **Empfehlung:** a.
- **Folge bei Nichtentscheidung:** PR-B3 nicht final.
- **Blockiert:** PR-B3.
- **Vorläufig:** ja.

### ENT-E5 — QR-Code im Enrollment (D-E3a)
- **Plan:** E (E3.6, E3.8)
- **Optionen:** A) v1 ohne QR; B) QR mit weiterer Dependency.
- **Empfehlung:** A.
- **Folge bei Nichtentscheidung:** E3.8 ohne festen Umfang.
- **Blockiert:** E P3-4, P3-5.
- **Vorläufig:** ja.

### ENT-E6 — Zeitpunkt `MFA_STAFF_ENFORCEMENT=required` und Befristung des Übergangs (D-E3b, Sicherheits-Risiko 3)
- **Plan:** E (Einführung)
- **Optionen:** A) Betreiber schaltet nach Enrollment aller Staff; B) Default `required` ab Release N+1. Zusatz (Review): Übergangsfenster mit Datum im ADR-021-Nachtrag befristen.
- **Empfehlung:** A + Befristung.
- **Folge bei Nichtentscheidung:** ADR-021-O5-Risikoakzeptanz gilt unbefristet weiter.
- **Blockiert:** E3-Rollout, ADR-021-Nachtrag (E3.0).
- **Vorläufig:** ja.

### ENT-E7 — Selbst-Enrollment unter `required` (QR-S01, hoch)
- **Plan:** E (E3.4, E3.6)
- **Frage:** Wer nur das Passwort eines nicht eingeschriebenen Staff-Kontos kennt, kann heute laut Plan selbst eine Authenticator-App binden.
- **Optionen:** A) Enroll-Challenge nur mit einmaligem Enrollment-Grant (Admin-Aktion oder `mfa_reset`, TTL ≤ 24 h, Audit); ohne Grant 403; B) Grace-Fenster nur für Konten jünger als N h + Benachrichtigung (Nutzer-Risikoakzeptanz).
- **Empfehlung:** A.
- **Folge bei Nichtentscheidung:** E3 hat eine Account-Takeover-Lücke; Sicherheitsgate „vor Welle 3“ offen.
- **Blockiert:** E P3-3, P3-4.
- **Vorläufig:** nein.

### ENT-E8 — Staff-API-Keys ohne zweiten Faktor (Sicherheits-Risiko 2, QR-S10)
- **Plan:** E (Nicht-Ziel „keine MFA für API-Keys“)
- **Frage:** Vor dem Cutover angelegte Staff-Keys umgehen 2FA dauerhaft.
- **Optionen:** A) akzeptieren + Key-Inventur + Ablaufpflicht (`expires_at`) für Staff-Keys; B) Staff-Keys beim Cutover widerrufen; C) akzeptieren ohne Zusatz.
- **Empfehlung:** A.
- **Folge bei Nichtentscheidung:** Cutover-Command (KA-E-07) ohne Key-Regel.
- **Blockiert:** neuer Task E3.9 (Cutover).
- **Vorläufig:** ja (Inventur umsetzen).

### ENT-D9 — ⚠ KONFLIKT `seed_demo`-Default-Passwort: DEBUG-Bindung vs. Opt-in (QR-S15)
- **Plan:** D (D6.2)
- **Konflikt:** Planbasis D6: „`seed_demo` gegen `DEBUG=False` absichern“. Sicherheitsreview: DEBUG ist im Dev-Overlay wahr und kann produktionsnah versehentlich aktiv sein; Default-Passwort nur mit explizitem Opt-in `SEED_DEMO_ALLOW_DEFAULT_PASSWORD=1`.
- **Optionen:** A) wie Planbasis (nur `DEBUG=False` sperrt); B) Opt-in-Variable zusätzlich und unabhängig von DEBUG (CI/Test-Compose setzen sie).
- **Empfehlung:** B (strenger, erfüllt Planbasis mit).
- **Folge bei Nichtentscheidung:** D P3-1 setzt A um.
- **Blockiert:** D P3-1 (Welle 3, vor E P3-5).
- **Vorläufig:** ja (A als Untergrenze).

### ENT-F0 — ⚠ KONFLIKT Eigener Spec für F1? (K-F0)
- **Plan:** F (F1)
- **Konflikt:** Planbasis: „Jede Stufe F1–F3 bekommt einen eigenen Spec.“ Plan F: F1 ist ein Bugfix-Paket, der Plan gilt als Spec.
- **Optionen:** a) Plan F gilt als F1-Spec; b) separater F1-Spec.
- **Empfehlung:** a.
- **Folge bei Nichtentscheidung:** F P1 startet nicht (Eintrittskriterium).
- **Blockiert:** PR-F1 … PR-F6.
- **Vorläufig:** nein.

### ENT-F1 — ⚠ KONFLIKT Issue-/Risk-Linkvokabeln (K-F1)
- **Plan:** F (F1.1)
- **Konflikt:** Planbasis „in zentrale Validierung“; die Vokabeln stecken in nie aufgerufenem Code, der Katalog deckt Teile über `references`/`mitigates` ab.
- **Optionen:** a) nur konsolidieren; b) konsolidieren + drei Built-ins `blocks`, `resolves`, `threatens`.
- **Empfehlung:** b.
- **Folge bei Nichtentscheidung:** PR-F2 entfällt; `link_types`-Nummern ab 0013 rücken (Index §e).
- **Blockiert:** PR-F2.
- **Vorläufig:** nein für PR-F2, ja für PR-F1.

### ENT-F6 — Rollback und nach der Baseline neu angelegte Artefakte (K-F6)
- **Plan:** F (F4.4)
- **Optionen:** a) unberührt lassen, nur melden; b) optional per Flag soft-löschen.
- **Empfehlung:** a.
- **Folge bei Nichtentscheidung:** F4.4 ohne festen Vertrag.
- **Blockiert:** PR-F11, PR-F12.
- **Vorläufig:** ja.

---

## 5. Blockiert Welle 4

### ENT-B2 — ⚠ KONFLIKT `Measure` vs. ADR-008 (K-2 Plan B)
- **Plan:** B (B6)
- **Konflikt:** Planbasis „`Milestone` + `Measure` als ein Plan“; akzeptiertes ADR-008 („MOE/MOP/TPM werden nicht modelliert“, `deciders: [user]`), #393 geschlossen.
- **Optionen:** a) B6 = nur `Milestone`, ADR-008 bleibt; b) ADR-008 durch neues ADR superseden, `Measure` bauen (+8–12 d); c) B6 streichen.
- **Empfehlung:** a.
- **Folge bei Nichtentscheidung:** B6 startet nicht; persistence 0128/0129 bleiben frei.
- **Blockiert:** PR-B19, PR-B20.
- **Vorläufig:** nein.

### ENT-F2 — Begriff `Document` (K-F2)
- **Plan:** F (F2)
- **Optionen:** a) #1374-`Document` ersetzt die Dokumentensicht-Spec, Baseline-Scope `document` akzeptiert zusätzlich ein `Document`; b) Koexistenz mit anderem Namen; c) Dokumentensicht zuerst.
- **Empfehlung:** a.
- **Folge bei Nichtentscheidung:** F2-Spec nicht schreibbar.
- **Blockiert:** F2-T0 und Folgende.
- **Vorläufig:** nein.

### ENT-F3 — ⚠ KONFLIKT Inline-Verweise `[[Term]]` vs. bestehendes Token-Format (K-F3)
- **Plan:** F (F3)
- **Konflikt:** Planbasis/Konzept `[[Term]]`, „keine UUIDs im Text“; Bestand (#1266) speichert `[[glossary:<uuid>@<rev>]]`.
- **Optionen:** a) Anzeige `[[Begriff]]`, Speicherung im bestehenden Token-Format, Resolver; b) neue Speicherform `[[slug]]` + Migration; c) zwei Grammatiken parallel.
- **Empfehlung:** a.
- **Folge bei Nichtentscheidung:** F3-Spec nicht schreibbar.
- **Blockiert:** F3-T0 und Folgende.
- **Vorläufig:** nein.

### ENT-F4 — Konzept-Scopes `documents:*` vs. Key-Stufen (K-F4)
- **Plan:** F (F2), Bezug Plan E
- **Optionen:** a) Abbildung auf `read_only`/`author`/`admin`; b) neue Ressourcen-Scopes (Schema-Änderung `ApiKey`).
- **Empfehlung:** a.
- **Folge bei Nichtentscheidung:** F2-API-Rechte offen.
- **Blockiert:** F2-T0, F2-T5/T6.
- **Vorläufig:** nein.

### ENT-F5 — Projektion/Adoption (K-F5)
- **Plan:** F
- **Optionen:** a) eigenes WP „F5 Projektion“ nach F3 mit eigenem Spec; b) in F2 aufnehmen.
- **Empfehlung:** a.
- **Folge bei Nichtentscheidung:** F-4/F-7/G-3 bleiben inert; `Closes #1374` in PR-F27 nicht möglich.
- **Blockiert:** F2-T0 (Umfang), PR-F27-Abschluss.
- **Vorläufig:** nein.

### ENT-D4 — Claude-Plugin-Konfiguration (D-D4)
- **Plan:** D (D4.3)
- **Optionen:** A) `userConfig` (Breaking für Env-Nutzer); B) Env behalten, nur dokumentieren.
- **Empfehlung:** A.
- **Folge bei Nichtentscheidung:** P3-7 entfällt.
- **Blockiert:** D P3-7.
- **Vorläufig:** ja.

### ENT-D5 — ⚠ KONFLIKT #92 schließen trotz UI-Lücke (D-D5)
- **Plan:** D (D6.1), Bezug Plan E
- **Konflikt:** Planbasis D6 „#92 verifizieren und schließen“; der Fence existiert, die UI-Anlage kennt aber keine Workspace-Auswahl.
- **Optionen:** A) schließen + Folge-Issue an Plan E; B) vor Schließen Workspace-/Scope-Auswahl in `ApiKeysSection`.
- **Empfehlung:** A.
- **Folge bei Nichtentscheidung:** #92 bleibt offen.
- **Blockiert:** D6.1.
- **Vorläufig:** ja.

### ENT-D6 — `server.json`-Remote (D-D6)
- **Plan:** D (D5.2)
- **Optionen:** A) URL-Template `{host}`; B) Remote weglassen; C) feste URL (existiert nicht).
- **Empfehlung:** A.
- **Folge bei Nichtentscheidung:** P3-9 entfällt.
- **Blockiert:** D P3-9.
- **Vorläufig:** ja.

### ENT-D7 — #792 Punkt 18 Dev-Overlay (D-D7)
- **Plan:** D (D3.4)
- **Optionen:** A) Health-Advisory + Doku; B) Override in `docker-compose.dev.yml` umbenennen (bricht Doku/CLAUDE.md-Befehle).
- **Empfehlung:** A.
- **Folge bei Nichtentscheidung:** P3-4 entfällt.
- **Blockiert:** D P3-4.
- **Vorläufig:** ja.

---

## 6. Nutzer-Gates (Handlungen, keine Optionswahl)

| Gate | Plan | Handlung | blockiert |
|---|---|---|---|
| U-1 | D (D2.5) | `prompt-regression` als Required Check in der Branch-Protection von `main` eintragen | Promptfoo-Gate G3 → A1 |
| U-2 | E (E3.0) | Sign-off `pyotp==2.10.0` (nach `dependency-check`/pip-audit) | E3 komplett |
| U-3 | A (T-A0-2) | Slot für den T1-Live-Beweis `memory.ask` freigeben | A4 (je nach ENT-A3) |
| U-4 | A (P3-Austritt) | Wartungsfenster für Qdrant-Stopp-Probe auf der QS freigeben | A2-Austritt |
| U-5 | D (D5, U-W1a/U-W2a/U-W3b) | Accounts/npm/MCP-Registry-Schritte | D5.2, D5.3, D4-Text |
| U-6 | übergreifend | Voller E2E-Lauf nur nach expliziter Freigabe (Projektregel) | – |

## 7. Hinweise ohne Entscheidungsbedarf

- **O5 Aufwand:** Schätzungen der Planautoren, Schärfung durch `effort-estimator` steht aus (Index §a).
- **O6 Backfill-Last A2:** wird in T-A2-5 per `--dry-run` gemessen; keine Vorab-Entscheidung nötig.
- **QR-T10 Subtyp-Mechanismus (B3-T2 ↔ F2):** technische Festlegung durch `senior-developer` in B3-T2 (Korrekturauftrag KA-B-08), keine Nutzerfrage.
