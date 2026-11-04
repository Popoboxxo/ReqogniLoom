---
review_id: RVW-2026-11-02-002
target_spec: docs/superpowers/specs/Archive/2026-11-02-f3-workitem-design.md
iteration: 1
status: open
date: 2026-11-02
reviewer: concept-reviewer
---

# Review-Protokoll RVW-2026-11-02-002 — F3-Spec (WorkItem)

**Gegenstand:** `docs/superpowers/specs/Archive/2026-11-02-f3-workitem-design.md` (WorkItem,
Agenten-Zustand, Inline-Verweise), Textfassung vom 2026-11-02, sowie der zugehörige
Umsetzungsstand F3-T1 (Modell + RLS-Migrationen).
**Normative Quellen:** Konzept `docs/concepts/2026-10-16-dokument-artefakte-workitem.md` (#1374);
Plan F §WP F3 (`docs/plans/Archive/2026-10-21-plan-f-dokumente-baselines.md`); Entscheidungen
ENT-F3/ENT-G1/ENT-E2 in `docs/plans/2026-10-21-entscheidungen-offen.md` §0b; F2-Spec und ADR-026
als unmittelbare Vorgänger.
**Datenquelle:** eigene Prüfung von Spec, Plan und Ist-Code am 2026-11-02. Gelesen wurden u. a.
`persistence/models.py` (`Artifact`, `Document`, `ArtifactWorkspaceMirrorMixin`),
`persistence/artifact_backing.py`, `application/local_uid.py`,
`application/glossary_reference_service.py` (#1266), `link_types/builtin.py` (`references`),
`persistence/migrations/0123_document.py`/`0124_document_rls_policy.py`,
`persistence/tests/test_document_model.py`, `persistence/tests/test_rls_coverage.py`,
`rest_api/tests/test_artifact_backing_linkability_matrix_1374.py`.
**Iteration:** 1 (erste Review-Iteration zu dieser Fassung).

**Hinweis zum Status:** `status: open`, weil Minor-/Info-Befunde erfasst sind. Das Verdict
`approved` bedeutet: kein Befund blockiert den Merge; die als „eingearbeitet" markierten Punkte
sind in dieser Fassung bereits korrigiert, die übrigen sind Präzisierungen für F3-T2/T4/T8.

## Prüfmatrix

| # | Check | Ergebnis | Beleg |
|---|---|---|---|
| 1 | Ziel und Nicht-Ziele trennen F3-T0/T1 sauber von T2…T9 | **bestanden** | §1, §15: Workflow-Seeds, Link-Typen, Service, REST/MCP, Anker-Register, Events, Frontend explizit ausgeschlossen |
| 2 | ENT-F3 = a ist eingearbeitet und nicht nur zitiert | **bestanden** | §2, §7: Anzeige `[[Begriff]]`, Speicherung `[[glossary:<uuid>@<rev>]]`, keine Migration, keine zweite Grammatik; Anker-Register speichert nur den Fundort |
| 3 | Modellfeldliste deckt Plan F §WP F3 vollständig ab | **bestanden** | §3.2 nennt alle 17 Planfelder plus das geerbte `version`; `workspace` ist die eine begründete Ergänzung (§3.1) |
| 4 | Zustand liegt nicht im Modell (REQ-143/ADR-026 R2) | **bestanden** | §3.2 „Bewusst kein `item_state`-Feld"; `WorkflowItemState` als einzige Wahrheit |
| 5 | Tier-abhängige Workflows sind als Vertrag prüfbar | **bestanden** | §4: drei Schemas, Zustandsmengen, `approver`-Gate, `work_item_preset`-Provisionierung |
| 6 | Resume/Checkpoint/Heartbeat deterministisch | **bestanden** | §6: Sortierung `(ordinal, id)`, Auswahlkriterium, Checkpoint-Anlage, `last_activity_at` je Aktion |
| 7 | I-1…I-5 vollständig und widerspruchsfrei zu ENT-F3 | **bestanden** | §7: fünf Regeln inkl. `409 ANCHORS_PRESENT`, toter Verweis, Freeze-Wechselwirkung |
| 8 | Events, Regeln, Memory-Abgrenzung, ETag, UID benannt | **bestanden** | §9–§12, §8 |
| 9 | G1.1/G1.3-Registrierungen und RLS-Paar im selben PR | **bestanden** | §3.4, §13; Migrationsnummern `0125`/`0126` nach `0124` geprüft |
| 10 | Widerspruchsfreiheit Konzept ↔ Plan ↔ Spec | **teilweise** | Konzept §4.4 führt `item_state` und `uid = item:<doc>:<selektor>`; Spec weicht bewusst ab (Plan/Hausmuster) → Befund 01/04 |
| 11 | Attribut-Oberfläche des Konzepts ist verortet | **teilweise** | Konzept §4.2 nennt `owner/reporter/priority/custom_fields`; Spec sagte zunächst nicht, wo sie liegen → Befund 02 |
| 12 | Regelparameter sind konkret, nicht „X" | **teilweise** | `DOC-P5`-Schwelle war offen → Befund 03 |
| 13 | Kein stiller Scope-Zuwachs in F3-T1 | **bestanden** | §3.3: `ck_work_item_progress_range` und `idx_workitem_document_ordinal` sind additiv und begründet; keine Service-/REST-/MCP-Spalte |
| 14 | Testplan deckt Identität, Constraints, Soft-Delete, PROTECT, RLS | **bestanden** | §16: 13 benannte Tests + `makemigrations --check` + Reverse-Probe |

## Befunde

| ID | Severity | Kategorie | Befund | Fix-Vorschlag | Status |
|---|---|---|---|---|---|
| `RVW-2026-11-02-002-01` | info | Abweichung zum Konzept | Konzept §4.4 nennt `item_state` als Modellfeld und `uid = "item:<document-uid>:<selektor>"`. Die Spec weicht bewusst ab (Zustand in `WorkflowItemState`, UID `WI-NNN`), begründet das aber an zwei getrennten Stellen. | Abweichungen in §2 als Tabelle sichtbar machen (ENT-/Hausmuster-Spalte) statt nur im Fließtext. | eingearbeitet (Spec §2/§8) |
| `RVW-2026-11-02-002-02` | minor | Vollständigkeit | Konzept §4.2 verlangt für beide neuen Artefakte die „gemeinsame Attribut-Oberfläche (`owner/reporter/priority/stakeholder/custom_fields`)". Die Spec nannte diese Felder nicht; ein Leser konnte sie als fehlend interpretieren. Tatsächlich liegen sie auf dem Backing-`Artifact` (`persistence/models.py`, Attribut v3 WS2 #936). | In §3.2 einen Absatz „Gemeinsame Attribut-Oberfläche" ergänzen, der die Verortung auf `Artifact` festhält. | eingearbeitet (Spec §3.2) |
| `RVW-2026-11-02-002-03` | minor | Präzision | `DOC-P5` war als „> X Tage" formuliert — nicht prüfbar, und ein Literal im Regel-Code wäre gegen die Preset-Konfigurierbarkeit. | Default 7 Tage + Preset-Schlüssel `work_item_stale_after_days` benennen; Umsetzung F3-T8. | eingearbeitet (Spec §11) |
| `RVW-2026-11-02-002-04` | minor | Semantik | `last_actor`/`approved_by` als `CharField` weichen von der Haus-Actor-FK-Konvention ab; ohne Begründung wirkt das wie ein Modellierungsfehler. | Begründung ergänzen: Agenten haben keinen `User`; Freigabe-Semantik prüft der Service (F3-T4). | eingearbeitet (Spec §3.2) |
| `RVW-2026-11-02-002-05` | minor | Delete-Semantik | `document`-`PROTECT` war als „Dokument wird nicht gelöscht" formuliert; der reguläre Pfad ist aber Soft-Delete über `Artifact.lifecycle_status`, sodass `PROTECT` nur harte Deletes trifft. Die Formulierung konnte als Konflikt mit G1.5 gelesen werden. | §3.1 präzisieren: `PROTECT` greift nur bei hartem Delete; Soft-Delete lässt Items unangetastet. | eingearbeitet (Spec §3.1) |
| `RVW-2026-11-02-002-06` | minor | Test-Strategie | Die Linkability-Matrix braucht je Registry-Typ eine Factory; der `WorkItemService` existiert erst in F3-T4. Eine test-lokale ORM-Factory ist ein bewusstes Provisorium. | Wie F2 (R2): Factory im Test begründen und in F3-T4 durch den Service ersetzen. | akzeptiert (Spec §17 R2) |
| `RVW-2026-11-02-002-07` | info | Härtung über Plan hinaus | `ck_work_item_progress_range` steht nicht in Plan F; er ist eine additive DB-Absicherung des 0–100-Vertrags. | Beibehalten, im Spec-Text als additiv kennzeichnen (bereits §3.3). | akzeptiert |
| `RVW-2026-11-02-002-08` | minor | Schnittstelle F3-T1 ↔ F2-Gate | `workflow/precondition_rules._document_item_gate_violations` (F2-T4) liest für G-2 ein `informational`-Flag am Item, das in der F3-T1-Feldliste des Plans nicht vorkommt. Mit dem Modell wird G-2 fail-closed für jedes Item ohne Kante. | Als offenen Modellpunkt in §5 festhalten: Ausnahme kommt mit F3-T3/T4; bis dahin ist der Pfad nur über den noch fehlenden Service erreichbar. | eingearbeitet (Spec §5) |

## Verdict

**APPROVED** — 0 critical / 0 major / 6 minor / 2 info. Kein Befund blockiert den Merge von F3-T0
oder F3-T1. Die Befunde 01–05 und 08 sind in dieser Fassung eingearbeitet; 06 (test-lokale
Factory) ist ein dokumentiertes Provisorium bis F3-T4, 07 eine bewusste Härtung.

Die Spec ändert weder ADR-026 noch den F2-Vertrag; sie setzt ihn fort. Der Status bleibt
`proposed` im Sinne der SE-Kaskade — ein Statuswechsel ist hier nicht vorgesehen, weil F3-T0 kein
ADR anlegt (Plan F §WP F3 nennt nur Spec + Review).
