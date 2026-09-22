---
type: SPEC
scope: "#569"
status: proposed
date: 2026-09-22
revision: 3
review_iteration: 3
review_iteration_note: "Iteration 3 = factual correction after two post-implementation reviews (2026-09-22); no design change, revision stays 3."
resolves_review:
  - docs/superpowers/plans/2026-09-22-se-auditor-waivers-569-spec-review-rev2.md
  - docs/superpowers/plans/2026-09-22-se-auditor-waivers-569-spec-review-rev3.md
supersedes_revision: 2
author_agent: concept-specifier
issue: "#569"
cluster: "2 (Bundle-Plan 2026-09-21-open-issues-bundle.md)"
base_branch: "feat/se-validation-completeness (HEAD da12acf4)"
target_branch: "feat/se-audit-waivers (cut from origin/main 564e62ab) — overrides the rev2 recommendation 'fix/se-audit-trace-p1-cycle'"
---

# Technische Spezifikation — #569: SE-Auditor Findings unterdrücken (False-Positive/Waiver mit Begründung)

## Changelog

Revision 3 behebt ausschließlich die beiden offenen MAJOR-Befunde der Revision-2-Review
(`2026-09-22-se-auditor-waivers-569-spec-review-rev2.md`, Verdict `CHANGES_REQUESTED`,
`resolution.M2 = partial`) sowie die dort benannten Minor/Info-Punkte N3–N6. Alle übrigen
Verträge der Revision 2 bleiben unverändert; AC-IDs werden **nicht** umnummeriert, nur
inhaltlich präzisiert und um AC-569-28 … AC-569-33 ergänzt.

| Finding (rev2-Review) | Auflösung in rev3 | Spec-Abschnitt |
|---|---|---|
| **N1 / M-A — 400-vs-422-Kollision** | Disjunkter, deterministischer Status-Code-Vertrag: die neuen Waiver-/Report-Endpunkte emittieren **niemals 422**; 422 bleibt in diesem Audit-Modul `POST …/audit/remediate/` (Adopt-Konflikt → Modify) vorbehalten. „Finding nicht blockierend“ wandert von 422 auf **400 `WAIVER_FINDING_NOT_BLOCKING`**; Begründungs-Policy auf **400 `WAIVER_REASON_REJECTED`**; abgelaufener Bestand auf **409 `SUPPRESSION_EXPIRED`**. Begründung gegen RFC 9110 §15.5.1/§15.5.4/§15.5.5/§15.5.10/§15.5.21. | §3.4.1, AC-569-02/11/15/17/28 |
| **N2 / M-B — Reason-Policy ohne Fehlertyp über die Layer-Grenze** | L1-Domain-Fehler `baseline.exceptions.GovernanceReasonError` (SSOT in `baseline/waivers.py`), L2-Service-Fehler `application.base.WaiverReasonPolicyViolation(ValidationError)` nach dem `BaselineGateBlockedError`-Präzedenz; zusätzlich `WaiverFindingNotBlockingError` und `SuppressionExpiredError`; REST-/MCP-Übersetzung + stabile Codes; Registrierung in `_EXC_TO_HTTP`/`_EXC_TO_CODE`, `_ERROR_MESSAGES` (DE+EN), `ERROR_CODES`/`ERROR_CODE_MAP`; Policy-Konstanten verlagert + re-exportiert. | §3.1, §3.3, §3.4.2, §3.5, AC-569-29/32/33 |
| **N3 — AC-Zählung falsch** | Korrigiert: **34 ACs** (AC-569-COMPAT + AC-569-01 … AC-569-16 + AC-569-17 … AC-569-27 + AC-569-28 … AC-569-33). | §6 |
| **N4 — AC-569-24 mit stale Prämisse** | Prämisse korrigiert: `load_waived_finding_keys` bleibt **nicht** wegen `_apply_waivers` positionskompatibel (dieser Aufruf wird ersetzt), sondern als öffentlicher Bestandsvertrag für externe Aufrufer/Tests; doppelter „When“-Satz entfernt. | §3.1, AC-569-24 |
| **N5 — scope-blinder Helfer `suppressed_finding_keys`** | **Gestrichen.** Ersatzlos entfernt; Konsumenten nutzen `list_suppressions` + `suppression_applies`. Begründung: scope-blinde Key-Mengen sind genau das, was diese Spezifikation im Gate ersetzt hat. | §3.3, §7 |
| **N6 — neue Domain-Fehler nicht in den geteilten Error-Maps** | Explizit: `GovernanceReasonError`/`GovernanceAuthorityError` dürfen `_service_error_response` **nie** erreichen (Remap in beiden Fassaden); die drei neuen L2-Typen **werden** in `_EXC_TO_HTTP`/`_EXC_TO_CODE` registriert, damit ein Escape 400/409 statt 500 ergibt. | §3.4.2, AC-569-29 |
| **M7-Rest — zwei Zeilenformen derselben Finding-Klasse** | Als expliziter Vertragssatz aufgenommen: Gate-Pfad stempelt `scope="project"` (`baseline_facade.py:635`), der neue `AuditService`-Pfad `scope=""` für scope-agnostische Findings; beide sind gewollt und durch R2a/R2b gedeckt. | §1, AC-569-COMPAT(b) |
| **Zusätzlich rev3 (Auftrag): `granted_by` + Ablauf-Semantik** | Autor-Erfassung mit Leerwert-Abweisung (403); `expires_at` wird **zur Entscheidungszeit** ausgewertet (kein Job, kein State-Feld); bereits abgelaufener `expires_at` beim Anlegen → 400. | §3.2, §3.3, §5/E3, AC-569-30/31 |

### Changelog — Iteration 2 (Auflösung der rev3-Review `CHANGES_REQUESTED`)

Grundlage: `2026-09-22-se-auditor-waivers-569-spec-review-rev3.md` (Verdict `CHANGES_REQUESTED`;
`major: 1` = R3-01, `minor: 9` = R3-02…R3-10, `info: 5` = R3-11…R3-15; M-A und M-B dort bereits
**resolved**). `revision: 3` bleibt bewusst stehen — die Iteration 2 **präzisiert nur Text** der
rev3-Spezifikation, sie ändert **keine** Verträge, Endpunkte oder Designentscheidungen; sie ist über
`review_iteration: 2` und diese Tabelle nachvollziehbar. Kein AC wurde abgeschwächt oder entfernt;
wo sich die Bedeutung eines AC ändert, steht die Änderung in der Tabelle.

| Finding (rev3-Review) | Status | Abschnitt geändert |
|---|---|---|
| **R3-01** (major) `m7`-Invariante arithmetisch unerreichbar | **resolved** | §3.3 (m7-Block neue „Immer-Identität" ergänzt), AC-569-13, V17: Die unerreichbare Ungleichung `counts.total != counts.blockers + counts.warnings` ist ersetzt durch `counts.total != total_findings_available` (Fenster vs. Gesamtlauf); explizit festgeschrieben ist jetzt `counts.blockers + counts.warnings == counts.total` als unbedingte Identität (Severity binär). Die deskriptiv-vs-absolut-Unterscheidung aus M5 bleibt erhalten. |
| **R3-02** (minor) MCP-Codes erscheinen nicht auf `tools/call` | **resolved** | §3.5 (neuer Wire-Verhalten-Absatz), AC-569-02, V6: Klarstellung, dass die drei Codes **nicht** in `_PROTOCOL_ERROR_CODES` stehen und daher auf `tools/call` als `result.isError == true` + **String**-`error_code` erscheinen (kein numerischer Code); die AC-569-02-MCP-Assertion prüft jetzt genau das, der `-32008`-Wert separat via V36. `_PROTOCOL_ERROR_CODES` bleibt bewusst unerweitert. |
| **R3-03** (minor) `_validate_gate_reason` ist module-level | **resolved** | §3.1 (M2-Block), §3.4.2-Tabelle (Zeile L1 `GovernanceReasonError`), AC-569-29(ii), V33, §7-Non-Goal: durchgängig „module-level Funktion `_validate_gate_reason` in `application/baseline_facade`" statt „`BaselineFacade`-Methode"; Delegator bleibt auf Modul-Ebene, Bestandsimport `:35` bleibt gültig. |
| **R3-04** (minor) `scope=""` ist die neue, nicht die Legacy-Form | **resolved** | §1-Tabelle (b), §3.1-Text (Verweis auf §1 „Zwei Zeilenformen"), AC-569-COMPAT(b), V2: (b) ist jetzt die **defensive R2a-Abdeckung der neuen `""`-Zeilenform**; die Gate-Zeilenform `"project"` bleibt der produktionsreale Bestandsbeleg in (c). `NULL` ist explizit als im `CharField(blank=True, default="")` nicht repräsentierbar benannt. |
| **R3-05** (minor) GET-Waiver ohne 500, GET-Report ohne 403/500 | **resolved** | §3.4.1: neue Zeilen **E19** (`GET …/audit/waivers/` 500) und **E20** (`GET …/audit/` 500) plus Absatz „Totality des GET-Status-Sets": der erweiterte Report-Endpunkt hat bewusst keine 403-Zeile (heutiges Verhalten: `except Exception` → 500, `audit_views.py:155-164`; Status-Set unverändert), der neue Waiver-Endpunkt hat E12 (403). AC-569-28/V32 referenzieren E19–E20 mit. |
| **R3-06** (minor) „422 nur bei remediate" codebase-weit falsch | **resolved** | §1/D1, §3.4.1-Invariante, §7-Non-Goal: Aussage auf „in diesem Audit-Modul" eingegrenzt; `architecture_decompose_views.py:156` als zweiter 422-Nutzer explizit als außerhalb/unberührt benannt. Belastbarer Vertrag bleibt „kein neuer Endpunkt emittiert 422". |
| **R3-07** (minor) Präzedenz E3 vs. E8 unstated | **resolved** | §3.2 (neuer R3-07-Absatz in D2), §3.3 Schritt 8, §3.4.1 E8-Zeile, 409-RFC-Bullet: die Request-`expires_at`-Prüfung (E3/D2, 400) läuft **vor** der Bestandsprüfung (m1/E8, 409) und gewinnt im kombinierten Fall. |
| **R3-08** (minor) „`granted_by` Pflicht" gilt nur auf neuen Oberflächen | **resolved** | §3.2 (neuer Geltungsbereich-Absatz), §3.4.2 Negativ-Invariante: Invariante explizit auf die zwei neuen Oberflächen gescoped; der unveränderte Gate-Pfad `baseline_facade.py:594` (Autor-Stempel, kein Blank-Check) und die unangetasteten `granted_by=""`-Bestandszeilen sind als bekannte, out-of-scope Altlast benannt. **Präzisiert (2026-09-22, C3):** Dreiteilung — (a) Reason und (c) Audit-Eintrag gelten auf **allen** Pfaden, (b) Autor nur auf den neuen. |
| **R3-09** (minor) AC-569-30-Formel vs. None-Fall | **resolved** | AC-569-30, V34: `str(ctx.user_id).strip()` ersetzt durch die None-sichere Service-Formel `str(getattr(ctx, "user_id", "") or "").strip()`; der `None`-Fall (`""`, nicht `"None"`) ist explizit benannt. |
| **R3-10** (minor) `Closes #569` fehlt | **resolved** | §9 Rollout: neuer Bullet „PR-Pflicht" mit `Closes #569` (Bundle-Plan `:49,193`) und Zielbranch-Angabe. |
| **R3-11** (info) Mutationsprobe nur im Docstring | **resolved** | AC-569-COMPAT(d): Proben zusätzlich mit Marker `# mutation-probe: …` und in der PR-Beschreibung wiederholbar dokumentiert. |
| **R3-12** (info) V31-Doku-Hälfte als Test gelistet | **resolved** | §12 V31: Threat-Model-Beantwortung explizit als **Doku-Pflicht, keine Test-Assertion** ausgewiesen. |
| **R3-13** (info) `ERROR_CODES`-Shape-Phrasing | **resolved** | §3.4.2 Registrierungs-Pflicht 4: „Message-Zeile in `ERROR_CODES` (Name → String) + numerischer Eintrag in `ERROR_CODE_MAP` (Name → int)"; Abgrenzung zu `_PROTOCOL_ERROR_CODES`. |
| **R3-14** (info) „genau eine" der R2-Klauseln | **resolved** | §3.1 R2: „OR über R2a–R2c: mindestens eine Klausel muss greifen, mehrere dürfen zugleich wahr sein". |
| **R3-15** (info) doppelte Error-Codes für eine Bedingung (E5 vs. Legacy) | **not-applicable** | Bewusst so dokumentiert (status-konsistent: neue Oberfläche `400 WAIVER_FINDING_NOT_BLOCKING`, Legacy `waived_findings` `400 VALIDATION_ERROR`); keine Änderung, kein AC berührt. |

**Reviewer-Rulings (rev3 §9) übernommen:** (1) O1-Revoke-Pfad akzeptiert + 409 ausdrücklich als
**nicht client-auflösbar bis O1** markiert (§3.4.1); (2) D2 akzeptiert + Präzedenz E3-vor-E8 (R3-07);
(3) `granted_by` blank → 403 akzeptiert + AC-Angleichung (R3-09) und Geltungsbereich (R3-08);
(4) MCP-Codes `-32008/-32009/-32010` akzeptiert + Wire-Verhalten klargestellt (R3-02);
(5) DE/EN-Wording akzeptiert — `_ERROR_MESSAGES`-Bilingual-Pflicht und V36-Beide-Sprachen-Pin
bleiben unverändert.

**Nicht geändert in rev3:** `finding_key`-Rendering und -Signatur, Modell-/Tabellennamen
(`BaselineGateWaiver`/`bl_baseline_gate_waiver`), die bestehenden Unique-/Check-Constraints,
die `override_reason`-Semantik (`baseline_facade.py:539-556`) und der bestehende
`waived_findings`-Pfad (inkl. dessen 400-`VALIDATION_ERROR`-Antwort, siehe §3.4.2).

---

## Post-implementation corrections (2026-09-22)

**Basis:** zwei unabhängige Post-Implementierungs-Reviews auf dem Zielbranch
`feat/se-audit-waivers` — eine **formale DoD-/AC-Traceability-Validierung** und eine
**adversariale Backend-Review**. Beide bestätigten unabhängig denselben Sachdefekt (C1 unten).
Diese Iteration ist eine **Faktenkorrektur**, keine Design-Änderung: `revision: 3` bleibt stehen,
`review_iteration` wird auf `3` gesetzt. Keine AC wird abgeschwächt; C1 macht AC-569-09
**präziser**, nicht vager.

### C1 — Die M3-Prämisse „`details` werden persistiert" ist FALSCH

Revision 2/3 behaupteten (gestützt auf einen veralteten Kommentar), `ServiceBase._audit`
**persistiere** den `details`-Payload, sodass `baseline.create`/`baseline.waiver_create`
`suppressed_blocker_count`, `suppressed_finding_keys`, `waiver_ids`, `matched_waiver_ids` in der
Audit-Tabelle tragen. **Verifiziert ist das Gegenteil:**

- `backend/audit/services.py:159` — `details` ist dokumentiert als *„Reserved for v2 field-level
  diff (ADR-10). Ignored in v1."* und wird **nie** geschrieben.
- `backend/audit/writer.py:190-202` — `AuditLogWriter.write` konstruiert den `AuditEntry`
  **ohne** `details`.
- `backend/audit/models.py:246-306` — `AuditEntry` hat **keine** `details`-/JSON-Spalte.
- `backend/audit/migrations/0013_alter_auditentry_op.py` — entschied sich bewusst für eine eigene
  Operation, statt „in einem `baseline.create`-details-Blob mitzureiten".

**Konsequenz:** Die `details`-Persistenz-Klausel von AC-569-09 ist auf diesem Branch **nicht
literal erfüllbar**, und ein AuditLog-Writer-Umbau ist explizites Non-Goal (§7). Der ehrliche
Vertrag ist: der **konstruierte** `details`-Payload wird **an der `_audit`-Aufrufgrenze**
asserted (Intercept/Mock); der **durable Trail** ist die `AuditEntry`-Zeile
(`op`/`entity_type`/`entity_id`/`actor`/`change_reason`) **plus** die append-only
`BaselineGateWaiver`-Zeile (`finding_key`, `rule_id`, `artifact_ids`, `scope`, `reason`,
`granted_by`, `expires_at`). „Wer / was / warum / bis wann" ist über den Join
`AuditEntry.entity_id → BaselineGateWaiver.id` rekonstruierbar — mit **einer Asymmetrie:** auf
dem MCP-Pfad ist `change_reason` `None` (`write_mcp_audit` setzt keinen `change_reason`,
`mcp_server/tools/base.py:269-306`), dort ist die Begründung **nur** über den Join erreichbar.
Strukturierte `details`-Queryability ist auf den AuditLog-Writer-Umbau verschoben (Non-Goal).
Betroffen: §1/M3, §2/DoD 4, §3.2/M4, §3.3 Schritt 8, §4, §5/E2, §7, AC-569-09, V13.

### C2 — MCP `audit.waivers` ist bewusst strenger als der reine Read-Tier

§3.5 weist `audit.waivers` den Read-Tier zu (`_READ_ONLY_TOOL_NAMES`). Die Implementierung behält
den Tier, erzwingt im Handler aber **zusätzlich** den REST-E12-Approval-Authority-Choke-Point, sodass
ein Editor/Viewer auf MCP `PERMISSION_DENIED` erhält — genau wie auf REST. Das schließt eine
Transport-Asymmetrie, über die ein Aufrufer durch bloßes Wechseln des Transports hätte lesen
können, wer was und warum unterdrückt hat. **Rationale:** die Suppressions-Liste ist
Governance-Metadaten (wer / warum). Tier = read, effektive Autorität = Approval-Authority. Siehe
§3.5, AC-569-07, V11.

### C3 — Der Autor-Invariante fehlt die Pfad-Qualifizierung

Die Invariante las sich absolut („kein Waiver ohne Autor"). Verifiziert: der **Legacy**-Gate-Pfad
(`backend/application/baseline_facade.py:587-595`, Autor-Stempel `:594`) kann weiterhin
`granted_by=""` persistieren — Reason-Policy und Authority-Check **werden** dort erzwungen, und
`baseline.waiver_create` **wird** geschrieben, der Autor aber nicht. R3-08 qualifizierte die
Invariante bereits auf die neuen Oberflächen; C3 stellt die Dreiteilung unmissverständlich fest:
(a) Reason und (c) Audit-Eintrag gelten auf **allen** Pfaden, (b) die Autor-Garantie gilt **nur**
auf den neuen Oberflächen. Der Legacy-Blank-Autor ist dokumentierte Schuld auf append-only-Zeilen
(keine History-Rewrite, kein Backfill). Siehe §3.2, §3.4.2.

---

## 1. Scope & Kontext

**Gebaut wird:** der vollständige, governance-konforme Suppression-Pfad für SE-Auditor-Findings auf
Basis der bereits existierenden `BaselineGateWaiver`-Entität (GH-821) — mit standalone
REST-/MCP-Zugang über die Layer-2-Fassade `AuditService`, Sichtbarkeit der Unterdrückung im
Audit-Report, explizit entschiedener und getesteter Gate-Semantik (§490), optionalem Ablaufdatum
sowie der dritten UI-Aktion neben Adopt/Modify plus Filter „unterdrückte anzeigen".

**Die Entität existiert bereits.** `BaselineGateWaiver(TenantScopedModel)` ist in
`backend/baseline/models.py` definiert (Tabelle `bl_baseline_gate_waiver`, Migrationen
`0007_baselinegatewaiver.py` + `0008_baseline_gate_waiver_rls.py`) und erbt über
`TenantScopedModel(AuditableModel)` (`backend/persistence/models.py:442` bzw. `:375`) bereits
`id` (UUID-PK), `created_at/created_by/modified_at/modified_by` und `version`. #569 **erzeugt keine
neue Entität** und **keine zweite Tabelle**; der Delta besteht ausschließlich aus: Pflicht-Begründung
als Service-Invariante, Autor-Erfassung, optionalem `expires_at`, dem Audit-Log-Eintrag und den
fehlenden Oberflächen.

**Ausdrücklich nicht neu erfunden wird:** die kanonische Finding-Identität
(`baseline.waivers.finding_key`, #1021), die persistente Entität (`BaselineGateWaiver`), die
Begründungs-Policy (`_validate_gate_reason`, GH-821) und der Audit-Log-Eintrag
(`baseline.waiver_create`). #569 ergänzt diese um die fehlenden Oberflächen und Semantiken.

**Betroffene Subsysteme:**

| Layer | Modul | Rolle |
|---|---|---|
| Layer 1 | `backend/baseline/waivers.py` | Finding-Identität + Suppression-Matching (SSOT) |
| Layer 1 | `backend/baseline/models.py` | `BaselineGateWaiver` (+ additives `expires_at`) |
| Layer 2 | `backend/application/audit_service.py` | `AuditService` als einzige Fassade (ADR-01) |
| Layer 2 | `backend/application/baseline_facade.py` | Gate-Konsum der Suppressions |
| Layer 3 | `backend/rest_api/audit_views.py`, `backend/rest_api/serializers.py`, `backend/rest_api/urls.py` | REST-Adapter |
| Layer 3 | `backend/mcp_server/tools/audit.py`, `backend/mcp_server/tool_registry.py` | MCP-Adapter |
| Frontend | `frontend/src/components/Audit/audit-dashboard.tsx`, `frontend/src/api/audit.ts`, `frontend/src/i18n/**` | dritte Aktion + Filter |

**Leitprinzip (aus dem Auftrag):** Nachvollziehbarkeit statt Verstecken. Eine Unterdrückung entfernt
ein Finding nicht aus der Welt — sie nimmt ihm die Blocker-Wirkung und macht die Entscheidung
(wer, was, warum, bis wann) dauerhaft sichtbar.

**Verbindliche Kompatibilitätsgarantie (GH-821) — vollständig, nicht nur das Rendering:** der
Aufruf `finding_key(rule_id, artifact_ids)` **ohne** `scope` muss byte-identisch das
Pre-#1021-Format `rule_id<US>a,b` liefern. Diese Garantie ist nicht verhandelbar, weil die
append-only `BaselineGateWaiver`-Zeilen mit exakt diesem Rendering persistiert wurden (siehe
`backend/baseline/waivers.py:69-80`). Die Garantie umfasst in Revision 2 ausdrücklich **vier**
Teile (alle in AC-569-COMPAT gepinnt):

| Teil | Gegenstand | Absicherung |
|---|---|---|
| **(a)** | Byte-exaktes **Rendering** ohne `scope` | Literal-Test + Mutationsprobe (bestehend) |
| **(b)** | **Defensive R2a-Abdeckung** der neuen `scope=""`-Zeilenform (und hypothetischer `NULL`-Werte) | `suppression_applies`-Regel R2a + Test gegen real persistierte Zeile |
| **(c)** | **Matching-Pfad-Wechsel** Gate → `suppression_applies` bricht keinen Bestandswaiver | Gate-Level-Bestandstest gegen die **produktionsreale** Zeilenform `scope="project"` |
| **(d)** | **Mutationsprobe** auf der Kompatibilitäts-Verzweigung | Wegnahme von `waivers.py:96-97` ⇒ Test rot |

**Zwei Zeilenformen derselben Finding-Klasse (expliziter Vertragssatz, M7-Rest).** Für ein
scope-agnostisches Finding (`finding.scope is None`) existieren bewusst **zwei** persistierte
Zeilenformen:

| Erzeugungspfad | Stempel | Beleg |
|---|---|---|
| Gate (`BaselineFacade._apply_waivers`) | `scope = finding.scope or build_scope` → `"project"` | `baseline_facade.py:635` |
| Neu: `AuditService.suppress_finding` | `scope = finding.scope or ""` → `""` (ungebunden) | §3.3 Schritt 7 |

Beide sind gewollt und beide werden von den Regeln R2a/R2b (§3.1) abgedeckt. Kein Pfad darf die
Zeilenform des anderen „vereinheitlichen" — das wäre ein GH-821-Bruch.

**Korrektur der M3-Prämisse (Post-Implementierungs-Review, 2026-09-22 — siehe „Post-implementation
corrections"/C1):** Die in Revision 2 und 3 aufgestellte Behauptung, `ServiceBase._audit`
**persistiere** `details`, ist **falsch** und wird hiermit zurückgezogen. Verifiziert:
`backend/audit/services.py:159` dokumentiert den `details`-Parameter als *„Reserved for v2
field-level diff (ADR-10). Ignored in v1."* und schreibt ihn nie; `backend/audit/writer.py:190-202`
konstruiert den `AuditEntry` **ohne** `details`; `backend/audit/models.py:246-306` hat **keine**
`details`-/JSON-Spalte; die Migration `backend/audit/migrations/0013_alter_auditentry_op.py` hat sich
bewusst für eine eigene Operation entschieden, statt „in einem `baseline.create`-details-Blob
mitzureiten". Der beim `baseline.create` **konstruierte** `details`-Payload
(`suppressed_blocker_count`, `suppressed_rule_ids`, `suppressed_finding_keys`, `waiver_ids`,
additiv `matched_waiver_ids`; `baseline_facade.py:272-287`) ist damit **nur an der
`_audit`-Aufrufgrenze** prüfbar (Intercept/Mock), **nicht** als persistierte Spalte. Der durable
Trail ist die `AuditEntry`-Zeile (`op`/`entity_type`/`entity_id`/`actor`/`change_reason`) **plus**
die append-only `BaselineGateWaiver`-Zeile; „wer / was / warum / bis wann" ist über den Join
`AuditEntry.entity_id → BaselineGateWaiver.id` rekonstruierbar. Strukturierte
`details`-Queryability ist auf den AuditLog-Writer-Umbau verschoben und bleibt Non-Goal (§7). Siehe
AC-569-09.

**In Revision 2 getroffene Entscheidungen** (aus dem Review beantwortete offene Fragen,
vormals O2–O6 — siehe §8): O2 = **blocker-only** (WARNING-Findings sind nicht unterdrückbar),
O3 = `include_suppressed` Default **`true`**, O4 = Ablauf **optional**, `NULL` = unbefristet,
O5 = **Description + `baseline.create`-`details`-Payload (an der `_audit`-Grenze geprüft) +
`BaselineGateWaiver`-Zeile + AuditEntry genügen** (kein Join-Modell; die frühere Begründung
„`details` sind persistiert" ist zurückgezogen, siehe §1/M3-Korrektur),
O6 = i18n-Keys **profilunabhängig neutral**. Nur O1 (Revoke) bleibt offen.

**In Revision 3 getroffene Entscheidungen:**

- **D1 — 422 ist in diesem Audit-Modul reserviert.** Kein neuer Endpunkt und keine neue
  Fehlerklasse darf HTTP 422 verwenden; 422 trägt hier ausschließlich die Bedeutung „Adopt nicht
  automatisch anwendbar → Modify anbieten" (`audit_views.py:207-213`, `client.ts:303-324`,
  `audit-dashboard.tsx:309`). Der belastbare Vertrag ist „kein neuer Endpunkt emittiert 422".
  Die codebase-weite Aussage „422 kommt ausschließlich bei `remediate` vor" ist **falsch**:
  `architecture_decompose_views.py:156` nutzt 422 ebenfalls (Decompose-Audit-Konflikt) — das liegt
  außerhalb dieses Moduls und bleibt von #569 unberührt (R3-06). Siehe §3.4.1.
- **D2 — bereits abgelaufener `expires_at` wird abgewiesen** (400 `VALIDATION_ERROR`), statt eine
  wirkungslose Zeile anzulegen. Ein Waiver, der per Konstruktion nie unterdrückt, wäre ein stiller
  No-op und verstieße gegen das Leitprinzip. Bewusst **zustandsunabhängig** geprüft (auch wenn
  bereits eine aktive Zeile existiert), damit die Antwort deterministisch bleibt.
- **D3 — Ablauf wird zur Entscheidungszeit ausgewertet**, nicht als persistiertes `state`-Feld und
  nicht per Job. `expires_at` ist ein passiver Zeitstempel; „aktiv/abgelaufen" ist abgeleitet.
- **D4 — Policy-Konstanten wandern nach Layer 1 und werden re-exportiert** (M2-Rest), damit die
  bestehende Importfläche (`test_baseline_gate_waivers_821.py:33`) unverändert bleibt.

---

## 2. Ist-Zustand pro DoD-Punkt

| DoD | Status | Beleg (file:line) | Lücke |
|---|---|---|---|
| **1** Stabile Finding-Identität dokumentiert + gegen Re-Audit getestet | **teilweise** | `backend/baseline/waivers.py:56-98` (`finding_key`), `:46-53` (`canonical_artifact_ids`); `backend/application/audit_service.py:80-85` (`AuditFindingView.finding_key`), `:90` (`to_dict` trägt `finding_key`); `backend/application/tests/test_audit_finding_identity_1021.py:115-141` (Byte-Identität, Scope), `:188-248` (Re-Audit-Stabilität) | Kein Test, der die Stabilität einer **scope-behafteten** Finding über einen Re-Audit prüft; keine explizite Dokumentation des Verhältnisses „Audit-API-Key (scoped) vs. Gate-Waiver-Key (unscoped)" für `scope != None`. `test_the_gate_matches_the_canonical_scope_less_key` (`:261-276`) deckt nur TRACE-P1 (scope-agnostisch) ab. **M7:** der Gate-Matching-Pfad (`baseline_facade.py:529-534`, `:667-671`, reine Key-Mengen-Zugehörigkeit) ist nicht gegen die in 3.1 neu eingeführte `suppression_applies`-Semantik abgesichert. |
| **2** Suppression-Entität mit Pflicht-Begründung + Audit-Log-Eintrag | **teilweise** | `backend/baseline/models.py:190-269` (`BaselineGateWaiver`: UniqueConstraint `(workspace_id, finding_key)` `:249-252`, CheckConstraint „reason not blank" `:253-256`); `backend/baseline/migrations/0007_baselinegatewaiver.py`, `0008_baseline_gate_waiver_rls.py`; `backend/baseline/waivers.py:140-192` (`record_waiver`); `backend/application/baseline_facade.py:645-657` (Audit-Eintrag), `:1117-1177` (Begründungs-Policy); `backend/audit/models.py:165` (`OP_BASELINE_WAIVER_CREATE`) | Entität ist **nur als Nebeneffekt** von `create_baseline(waived_findings=…)` erreichbar. Kein standalone Erzeugen/Listen. **Kein Ablaufdatum** (`expires_at` fehlt). Kein Revoke. Unterdrückung ist im **Audit-Report unsichtbar** (`run_audit` konsultiert keine Waiver). DB-CheckConstraint verbietet nur `""`, nicht Whitespace (`models.py:253-256`). |
| **3** REST- und MCP-Zugang über die bestehende Layer-2-Fassade | **teilweise** | REST: `backend/rest_api/views.py:3782-3830` (`waived_findings` auf `POST .../baselines/`), `backend/rest_api/serializers.py:1486-1523` (`BlockerWaiverSerializer`), `:1568-1578`; MCP: `backend/mcp_server/tools/baseline.py:117-154` (Schema), `:220-238` (Handler) — beide über `BaselineFacade` | **Kein** Zugang über die Auditor-Oberfläche: `backend/rest_api/audit_views.py` hat nur `run`/`remediate`/`ai-review` (`:131`, `:167`, `:222`), `backend/mcp_server/tools/audit.py:233-241` hat nur `query`/`ai_review`/`se_audit`/`dlq_list`/`dlq_replay`. `AuditService` besitzt **keine** Waiver-Methoden. Der geforderte Pfad `AuditService → rest_api/audit_views.py + MCP-Gruppe audit` existiert nicht. |
| **4** Explizite, getestete §490-Interplay | **teilweise** | `backend/application/baseline_facade.py:529-537` (unterdrückte zählen nicht als Blocker), `:336-350` (Summary in `details` + `change_reason`), `:370` (Event-Payload), `:1180-1214` (`_annotate_waiver` → Baseline-Description); Tests `backend/application/tests/test_baseline_gate_waivers_821.py:143-170`, `:199-225`; `backend/rest_api/tests/test_baseline_gate_waivers_821_rest.py:132-158` | **Korrigiert (Post-Implementierungs-Review, 2026-09-22):** die in rev2/rev3 angenommene `details`-Persistenz ist **widerlegt** — `ServiceBase._audit` reicht `details` zwar an `log_write` durch, der Writer ignoriert es aber (`audit/services.py:159`, `audit/writer.py:190-202`, keine Spalte in `audit/models.py:246-306`). Der `baseline.create`-Service **konstruiert** den Trail in `details` (`suppressed_blocker_count`/`suppressed_rule_ids`/`suppressed_finding_keys`/`waiver_ids`, `baseline_facade.py:272-287`), er ist aber **nur an der `_audit`-Aufrufgrenze** prüfbar. Durable ist die `AuditEntry`-Zeile plus die append-only `BaselineGateWaiver`-Zeile (Join `AuditEntry.entity_id → BaselineGateWaiver.id`). Offen: **kein Test**, der „unterdrückt ⇒ kein Blocker, aber dokumentiert" als #490-Entscheidung festnagelt, keiner für die Ablauf-Semantik, und (M4) `waiver_ids` enthält nur **neu erzeugte** Zeilen — bei wiederverwendeten Waivern ist `suppressed > 0` bei `waiver_ids == []`. |
| **5** UI: dritte Aktion + Filter „unterdrückte anzeigen" | **fehlt** | `frontend/src/components/Audit/audit-dashboard.tsx:777-827` (nur Adopt/Modify), `:159` (`severityFilter`, kein Suppressed-Filter); `frontend/src/api/audit.ts:40-50` (`AuditFinding` ohne `finding_key`/`suppressed`), `:112-134` (nur `run`/`remediate`) | Keine Waive/Suppress-Aktion, kein „unterdrückte anzeigen"-Filter, keine Suppressed-Kennzeichnung, keine Waiver-API. Zusätzlich Contract-Drift: das Backend liefert bereits `finding_key` (`audit_service.py:90`), der TS-Typ deklariert ihn nicht. |
| **6** Kein Weg, ein Blocker-Finding ohne Begründung/Audit-Spur loszuwerden | **teilweise** | `backend/application/baseline_facade.py:1117-1177` (Placeholder-/Regel-ID-Abwehr), `:739-780` (`_assert_override_permission`), `backend/baseline/models.py:253-256` (DB-Constraint), Tests `test_baseline_gate_waivers_821.py:421-451`, `test_baseline_gate_waivers_821_rest.py:187-213`, `:245-266`; `test_granular_api_key_scope_865.py:203-...` (AUTHOR-Key-Abwehr) | Gilt nur für den bestehenden `waived_findings`-Pfad. Die neuen Auditor-Endpunkte/MCP-Tools existieren noch nicht, also auch keine Negativtests für sie. Whitespace-only-Begründung ist nur app-seitig, nicht DB-seitig abgewehrt. |
| **7** (rev3) Deterministischer Status-/Fehler-Code-Vertrag | **fehlt / kollidiert** | `backend/rest_api/audit_views.py:207-213` (Modul mappt `ValidationError` → **422**), `:141-144`/`:178-184` (Parse-/Serializer-Fehler → **400**); `backend/rest_api/views.py:169-206` (`_EXC_TO_HTTP`/`_EXC_TO_CODE`, **exakte** Typ-Keys, sonst 500); `frontend/src/api/client.ts:303-324` + `errors.ts:23-48` (422 ⇒ `UnprocessableEntityError`); `frontend/src/components/Audit/audit-dashboard.tsx:309` (422 ⇒ Finding flippt auf Modify); `backend/mcp_server/protocol_handler.py:51-122` (`ERROR_CODES`/`ERROR_CODE_MAP`, höchster Server-Code `-32007`) | Ein einziger `ValidationError`-Typ kann die geforderte 400/422-Aufteilung nicht ausdrücken (Review N1). Ohne eigene L2-Fehlertypen + stabile Codes degradieren neue Fehlerklassen in `_service_error_response` zu 500 (Review N6), und die UI kann „Begründung abgelehnt" nicht von „Adopt-Konflikt → Modify" unterscheiden. |

---

## 3. Interface-Contracts

Alle Contracts sind **additiv**. Keine Renames, keine Entfernung, keine Formatänderung bestehender
Felder/Keys.

### 3.1 Finding-Identität (SSOT `backend/baseline/waivers.py`)

```python
# UNVERÄNDERT — Signatur und Rendering bleiben exakt wie heute.
def finding_key(
    rule_id: str,
    artifact_ids: Iterable[Any] | None,
    scope: Any | None = None,
) -> str: ...
```

- **Persistierte Identität** (`BaselineGateWaiver.finding_key`) ist und bleibt der **scope-lose**
  Aufruf `finding_key(rule_id, artifact_ids)`.
- Der `scope`-Parameter bleibt ausschließlich für **Anzeige/Korrelation** (Audit-API-Feld
  `finding_key`) und für die **Anwendbarkeits-Prüfung** (siehe 3.2) in Gebrauch.
- Neue benannte Helfer (additiv):

```python
@dataclass(frozen=True)
class SuppressionRecord:
    id: UUID
    finding_key: str            # persistierter, scope-loser Schlüssel (row.finding_key)
    rule_id: str
    artifact_ids: tuple[str, ...]
    scope: str                  # "" = scope-agnostisch/ungebunden
    scope_artifact_id: str      # "" = nicht an ein Dokument gebunden
    reason: str
    granted_by: str
    created_at: datetime
    expires_at: Optional[datetime]

def suppression_applies(
    record: SuppressionRecord,
    rule_id: str,
    artifact_ids: Iterable[Any] | None,
    scope: str | None = None,
    scope_artifact_id: str | None = None,
) -> bool: ...

def load_suppressions(
    workspace_id: UUID | str,
    tenant_id: UUID | str,
    *,
    include_expired: bool = False,
    now: datetime | None = None,
) -> tuple[SuppressionRecord, ...]: ...

def validate_waiver_reason(reason: str, *, label: str) -> str: ...          # M2: SSOT-Begründungspolicy

def assert_gate_waiver_authority(ctx: Any) -> None: ...                     # M2: SSOT-Autoritäts-Choke-Point
```

**`SuppressionRecord.scope` / `.scope_artifact_id` sind beim Laden defensiv normalisiert**
(`row.scope or ""`, `row.scope_artifact_id or ""`), damit ein hypothetischer `NULL`-Wert (im
`CharField(blank=True, default="")` nicht repräsentierbar) in einer künftigen nullable-Vorsprache
nicht am `str`-Typ scheitert.

**Anwendbarkeits-Regel (`suppression_applies`) — verbindlich (Revision 2, löst m4 auf):**

- **R1 — Schlüssel:** `record.finding_key == finding_key(rule_id, artifact_ids)` (scope-loser
  Vergleich; exakt das bestehende GH-821-Matching). Immer zwingend.
- **R2 — Scope-Bindung** (OR über R2a–R2c: **mindestens eine** Klausel muss greifen, mehrere
  dürfen zugleich wahr sein; `finding.scope` ist der Scope des **Findings**, nicht der Build-Scope):
  - **R2a** `record.scope == ""` → **ungebunden**: matcht jedes Finding mit demselben Schlüssel
    (GH-821-Bestandsverhalten; deckt die von #569 neu erzeugte ungebundene `scope=""`-Zeilenform
    ab, §1 „Zwei Zeilenformen" — sowie defensiv einen hypothetischen `NULL`-Wert, der im
    `CharField(blank=True, default="")` gar nicht repräsentierbar ist, R3-04).
  - **R2b** `finding.scope is None` (scope-agnostisches Finding) → matcht **nur**, wenn
    `record.scope_artifact_id == ""`. Das hält die produktionsrealen GH-821-Zeilen (für
    scope-agnostische Regeln wie TRACE-P1 vom Gate mit `scope="project"`, aber
    `scope_artifact_id=""` gestempelt) am Leben **und** verhindert, dass ein für ein
    *document*-scoped Finding gewährter Waiver (der `scope_artifact_id=<doc>` trägt) still das
    scope-agnostische Finding derselben Regel/Artefakte mitunterdrückt (**m4**).
  - **R2c** `record.scope == finding.scope` **und** (`finding.scope != "document"` **oder**
    `record.scope_artifact_id == scope_artifact_id`) → matcht ein scope-behaftetes Finding nur
    im selben Scope; für `document` zusätzlich nur im exakt selben Dokument.
- **R3 — Ablauf:** `record.expires_at is None` **oder** `record.expires_at > now` (UTC).

Die Regelmenge ist bewusst **nicht** „`finding.scope is None` matcht jeden Record" (Revision 1,
Review m4): R2b bindet die Ausnahme an `record.scope_artifact_id == ""` und hält den GH-821-Fall
(Zeilenform `scope="project"`, `scope_artifact_id=""`) stabil. Siehe AC-569-16/AC-569-27.

**M2 — Verortung des Autoritäts- und Begründungs-Choke-Points.** Die bisherigen
`BaselineFacade`-Helfer (`_validate_gate_reason`, `_assert_override_permission`,
`baseline_facade.py:738-780`, `:1117-1177`) werden in **Layer 1** verschoben — nach
`backend/baseline/waivers.py` (der bereits die SSOT für Finding-Identität und -Matching ist und
keine Fassade importiert; er importiert heute nur `baseline.models`, `:32`):

- `validate_waiver_reason(reason, *, label)` = die heutige Policy-Logik 1:1. Weil ein
  Layer-1-Modul `application.base.ValidationError` nicht importieren darf, wirft der Helfer die
  **neue Domain-Exception `baseline.exceptions.GovernanceReasonError`** (additiv, siehe §3.4.2).
  `_validate_gate_reason` ist heute eine **modul-level Funktion** in `application/baseline_facade`
  (`baseline_facade.py:1117`, aufgerufen von `_coerce_waiver_requests` `:723` und
  `_validate_override_reason` `:785`) — **nicht** eine `BaselineFacade`-Methode. Sie bleibt als
  **dünner Delegator auf Modul-Ebene** bestehen und **re-raised
  `application.base.ValidationError(str(exc))`** — Verhalten, Typ und Fehlercode des bestehenden
  `waived_findings`-Pfads bleiben damit **exakt unverändert** (Review M2-Rest, N2/R3-03); der
  bestehende Import `from application.baseline_facade import _validate_gate_reason`
  (`test_baseline_gate_waivers_821.py:35`) bleibt gültig.
- `assert_gate_waiver_authority(ctx)` = die heutige `_assert_override_permission`-Logik
  (`AuthorizationService.decide_access(..., Operation.WORKFLOW_APPROVAL)` **und**
  `scope_denial_reason(...)` für den ADMIN-Tier, #865). Der Helfer wirft die **neue
  Domain-Exception `baseline.exceptions.GovernanceAuthorityError`** (additiv); `BaselineFacade`
  **und** `AuditService` fangen sie und re-ranken sie auf `PermissionDeniedError`. Damit gibt es
  **genau einen** Choke-Point, keine Duplikation und keinen Import der Schwester-Fassade (ADR-01).
- `BaselineFacade._assert_override_permission` bleibt als `@staticmethod` **bestehen** und
  delegiert (direkte Aufrufe in `test_granular_api_key_scope_865.py:207-226` bleiben kompatibel).

**D4 — Policy-Konstanten (M2-Rest).** `MIN_OVERRIDE_REASON_LENGTH` (`:67`), `MIN_REASON_WORDS`
(`:70`), `MIN_REASON_DISTINCT_WORDS` (`:74`) sowie die privaten Muster `_MIN_REASON_WORD_LENGTH`,
`_READABLE_WORD_RE`, `_RULE_ID_TOKEN_RE` (`:78-88`) werden nach `baseline/waivers.py` verlagert.
`application/baseline_facade.py` **re-exportiert die drei öffentlichen Konstanten** als
Modul-Attribute, sodass der bestehende Import
`from application.baseline_facade import MIN_OVERRIDE_REASON_LENGTH`
(`test_baseline_gate_waivers_821.py:33`, verwendet `:382`) unverändert gültig bleibt. Die privaten
Muster werden **nicht** re-exportiert.

`load_waived_finding_keys(...)` bleibt als Kompatibilitäts-Wrapper erhalten und liefert nur noch
**aktive** (nicht abgelaufene) Schlüssel. Signatur bleibt positionskompatibel, `now` ist
**keyword-only**:

> **N4-Korrektur (rev3).** Die Positionskompatibilität ist ein **öffentlicher Bestandsvertrag** für
> externe Aufrufer und Tests — **nicht** eine Rücksicht auf `_apply_waivers`: dieser Aufruf wird
> gemäß M7 durch `load_suppressions` + `suppression_applies` ersetzt (`baseline_facade.py:608`
> entfällt damit).

```python
def load_waived_finding_keys(
    workspace_id, tenant_id, *, now: datetime | None = None
) -> frozenset[str]: ...   # == {r.finding_key for r in load_suppressions(..., include_expired=False, now=now)}
```

### 3.2 Suppression-Entität (`BaselineGateWaiver`, `backend/baseline/models.py`)

**Entscheidung: keine zweite Entität.** `BaselineGateWaiver` wird additiv erweitert. Begründung:
`backend/baseline/waivers.py:64-67` sagt bereits explizit, dass der Gate-Waiver-Match, das
`finding_key`-Feld der Audit-API **und** „(from #569) the suppression lookup" dieselbe Funktion
nutzen. Eine zweite, überlappende Governance-Tabelle wäre ein Anti-Pattern und würde zwei
Wahrheiten über „was ist ein Finding" erzeugen.

Neues Feld:

| Feld | Typ | Constraints | Semantik |
|---|---|---|---|
| `expires_at` | `DateTimeField(null=True, blank=True, default=None)` | kein Index nötig | `NULL` = unbefristet (GH-821-Verhalten). `> now` = aktiv. `<= now` = abgelaufen, unterdrückt **nicht**. |

Unverändert: `finding_key` (scope-loser Key), `scope`, `scope_artifact_id`, `reason`,
`granted_by`, `UniqueConstraint(workspace_id, finding_key)`, `CheckConstraint(reason != "")`,
Tabelle `bl_baseline_gate_waiver`.

**`granted_by` (Autor-Erfassung, rev3).** Auf den **beiden neuen Oberflächen** (REST
`POST …/audit/waivers/` und MCP `audit.waive_finding`) wird `granted_by` ausschließlich aus dem
authentifizierten Kontext befüllt — nie aus dem Request-Body:
`granted_by = str(getattr(ctx, "user_id", "") or "").strip()`. Ist das Ergebnis leer (auch bei
`ctx.user_id is None`), wird der Grant mit `PermissionDeniedError` (**403**) abgewiesen: eine
Governance-Entscheidung, die keinem Akteur zugeordnet werden kann, darf auf den neuen Oberflächen
nicht persistiert werden. Der Client kann `granted_by` **nicht** setzen (`UnknownFieldRejectionMixin`
lehnt das Feld mit 400 ab).

**Geltungsbereich der Invariante „kein Waiver ohne Autor" (R3-08; präzisiert im
Post-Implementierungs-Review, 2026-09-22).** Die Invariante ist eine **Dreiteilung** und gilt
nicht einheitlich auf allen Pfaden:

| Teil | Aussage | Geltung |
|---|---|---|
| **(a)** Pflicht-Begründung (Reason-Policy) | kein Waiver ohne policy-konforme Begründung | **alle** Pfade (neue Oberflächen **und** Legacy-Gate-Pfad, `baseline_facade.py:1117-1177`) |
| **(b)** Autor-Pflicht (`granted_by != ""`) | kein Waiver ohne auflösbaren Autor | **nur** die neuen Oberflächen (REST `POST …/audit/waivers/`, MCP `audit.waive_finding`) |
| **(c)** Audit-Eintrag (`baseline.waiver_create`) | jeder **neu** erzeugte Waiver erhält einen AuditEntry | **alle** Pfade (Gate-Pfad schreibt ihn in `baseline_facade.py:601-613`) |

Der bestehende Gate-Pfad (`baseline_facade.py:594`) stempelt `granted_by = str(getattr(ctx,
"user_id", "") or "")` **ohne** Leerwert-Prüfung — ein Waiver mit leerem Autor ist dort weiterhin
erreichbar. Das ist eine bekannte, bewusst out-of-scope gelassene **Schuld auf append-only-Zeilen**:
bereits vor #569 persistierte `granted_by=""`-Bestandszeilen bleiben **unangetastet** (keine
Datenmigration, kein Backfill, kein nachträgliches Verwerfen — die Zeile ist eine append-only
Governance-Aufzeichnung), und der Gate-Pfad wird in #569 **nicht** umgebaut. Eine History-Rewrite
wird ausdrücklich **nicht** vorgeschlagen. Nur die neuen Schreibpfade erzwingen den Autor.

`record_waiver(...)` erhält additive Keyword-Parameter:

```python
def record_waiver(
    *,
    workspace_id, tenant_id, request, rule_id, scope,
    scope_artifact_id, granted_by,
    expires_at: datetime | None = None,      # NEU, additiv
) -> tuple[BaselineGateWaiver, bool]: ...
```

`BlockerWaiverRequest` erhält ein additives Feld `expires_at: datetime | None = None`; `key`
bleibt `finding_key(rule_id, artifact_ids)` (unverändert).

**Idempotenz bleibt:** ein zweiter Waiver für denselben `finding_key` überschreibt nichts
(`get_or_create`). Das gilt auch für ein späteres `expires_at` — die erste Entscheidung
(inkl. Begründung und Autor) bleibt auf der Zeile.

**D2 — bereits abgelaufener `expires_at` beim Anlegen.** Ein `expires_at <= now` wird **vor**
`record_waiver` abgewiesen (400 `VALIDATION_ERROR`, §3.4.1/E3) — auch dann, wenn bereits eine
aktive Zeile existiert (bewusst zustandsunabhängig, deterministische Antwort). Damit existiert
kein Pfad, der eine Zeile anlegt, die per Konstruktion nie unterdrückt.

**M4 — gematchte vs. neu erzeugte Waiver-IDs (`GateWaiverOutcome`, additiv).**
`GateWaiverOutcome.waiver_ids` enthält heute ausschließlich **neu erzeugte** Zeilen
(`baseline_facade.py:104-110`, `:610-642`). Ein Build, der persistierte Waiver wiederverwendet,
hat daher `suppressed > 0` bei `waiver_ids == []` — AC-569-09 („Description nennt die
`waiver_ids`") wäre so nicht erfüllbar. Auflösung (additiv, kein Bruch des Bestandscontracts):

```python
@dataclass(frozen=True)
class GateWaiverOutcome:
    overridden: Tuple["Finding", ...] = ()
    suppressed: Tuple["Finding", ...] = ()
    waiver_ids: Tuple[UUID, ...] = ()          # UNVERÄNDERT: nur neu erzeugte Zeilen
    matched_waiver_ids: Tuple[UUID, ...] = ()  # NEU: alle gematchten Zeilen (erzeugt + wiederverwendet)
```

`_apply_waivers` lädt die aktiven Suppressions (`load_suppressions`) und gibt zusätzlich die IDs
**aller gematchten** Zeilen zurück (`load_waived_finding_keys` wird dabei durch
`load_suppressions`+`suppression_applies` ersetzt, siehe M7/§4). `_annotate_waiver` und der beim
`baseline.create` **konstruierte** `details`-Payload nennen die **gematchten** IDs (gekappt analog
`_MAX_LISTED_FINDINGS`, `baseline_facade.py:1099`, plus Zähler-Hinweis).
`details["waiver_ids"]` bleibt = neu erzeugt (Bestandscontract); additiv kommt
`details["matched_waiver_ids"]` hinzu. Der `details`-Payload ist an der `_audit`-Aufrufgrenze
prüfbar; der Writer persistiert `details` **nicht** — §1/M3-Korrektur.

**m1 — abgelaufener Bestandswaiver + neuer Grant.** `get_or_create` ist idempotent und
überschreibt `expires_at` nicht. Beantragt `suppress_finding` einen Waiver für einen
`finding_key`, dessen **einzige** Zeile abgelaufen ist (`state == "expired"`), wird die Anfrage
**nicht** still als „bereits vorhanden" quittiert: die Antwort ist `409 CONFLICT` mit Code
`SUPPRESSION_EXPIRED` (siehe §3.4). Eine 200-Antwort ohne Wirkung wäre ein stiller No-op und
würde gegen das Leitprinzip „Nachvollziehbarkeit statt Verstecken" verstoßen. Ein aktiver
Bestandswaiver liefert weiterhin `200` mit `created=false` (AC-569-04). Ein Wieder-Inkraftsetzen
ist ein eigener Governance-Akt und bleibt der offenen Frage O1 (Revoke/Re-Grant) zugeordnet.

### 3.3 Layer-2-Fassade `AuditService` (`backend/application/audit_service.py`)

Neue DTOs/Methoden (alle additiv):

```python
@dataclass
class SuppressionView:
    waiver_id: UUID
    finding_key: str                 # persistierter, scope-loser Key
    identity_key: str                # finding_key(rule_id, artifact_ids, scope) — Anzeige/Korrelation
    rule_id: str
    artifact_ids: tuple[str, ...]
    scope: str
    scope_artifact_id: str
    reason: str
    granted_by: str
    created_at: datetime
    expires_at: Optional[datetime]
    state: str                       # "active" | "expired"
    def to_dict(self) -> dict: ...

class AuditService(ServiceBase):
    def suppress_finding(
        self, workspace_id: str | UUID, ctx: AuthContext, *,
        rule_id: str,
        artifact_ids: Sequence[str],
        scope: Optional[str] = None,             # C1: nur für den Engine-Lauf, nicht persistiert
        scope_artifact_id: Optional[str] = None, # C1: Pflicht bei scope="document"
        reason: str,
        expires_at: Optional[datetime] = None,
    ) -> tuple[SuppressionView, bool]: ...
        # raises PermissionDeniedError | ValidationError
        #      | WaiverReasonPolicyViolation | WaiverFindingNotBlockingError
        #      | SuppressionExpiredError | NotFoundError

    def list_suppressions(
        self, workspace_id: str | UUID, ctx: AuthContext, *,
        state: str = "active",        # "active" | "expired" | "all"
    ) -> List[SuppressionView]: ...

    def run_audit(
        self, workspace_id, ctx, *,
        tier=None, scopes=None, limit=None, offset=0,
        include_suppressed: bool = True,     # NEU, additiv, Default = sichtbar (O3)
    ) -> AuditReport: ...
```

**N5 (rev3): `suppressed_finding_keys` wird gestrichen.** Der in Revision 2 vorgeschlagene
scope-blinde Helfer entfällt ersatzlos. Konsumenten, die Findings markieren oder filtern wollen,
nutzen `list_suppressions(...)` + `suppression_applies(...)`; eine Key-Mengen-Zugehörigkeit ohne
Scope-Bindung ist genau der Fehler, den diese Spezifikation im Gate-Pfad behebt (§3.1 R2).

Die drei neuen L2-Fehlertypen (`WaiverReasonPolicyViolation`, `WaiverFindingNotBlockingError`,
`SuppressionExpiredError`) sind **additive Exceptions in `application/base.py`** nach dem
Präzedenz von `BaselineGateBlockedError` (`application/base.py:61-77`): Subklassen von
`ValidationError` (damit jeder bestehende `except ValidationError`-Pfad weiter greift), aber
**eigene Typen** mit je einem Klassenattribut `error_code`. Übersetzung, Status und Registrierung:
§3.4.2.

`AuditFindingView` erhält additive Felder (Default-Werte → bestehende Konstruktionen bleiben gültig):

```python
suppressed: bool = False
suppressed_until: Optional[datetime] = None
suppression_reason: Optional[str] = None
suppression_id: Optional[UUID] = None
```

`AuditFindingView.to_dict()` ergänzt: `suppressed`, `suppressed_until`, `suppression_reason`,
`suppression_id`. `finding_key` bleibt unverändert der **scoped** Key.

**M5 — Zähler-Semantik bleibt deskriptiv (keine stille Contract-Änderung).**
`counts.blockers` / `counts.warnings` / `total_blockers_available` / `total_warnings_available`
behalten ihre dokumentierte Bedeutung aus `audit_service.py:99-119` **unverändert**: sie
beschreiben, was in `findings` steht (bzw. vor Cap insgesamt vorhanden war). Ein unterdrücktes
Blocker-Finding, das mit `include_suppressed=True` in `findings` steht, zählt dort weiterhin als
Blocker. Neu sind **rein additiv**:

```python
# AuditReport.to_dict()["counts"]  — additiv, bestehende Keys unverändert
"suppressed": <Anzahl der zurückgegebenen Findings mit suppressed=True>,
"suppressed_blockers": <davon Severity.BLOCKER>,
# Report-Top-Level — additiv, vor Cap/Filter berechnet
"total_suppressed_available": <Anzahl unterdrückter Findings im Gesamtlauf>,
"total_suppressed_blockers_available": <davon Severity.BLOCKER>,
```

Die Gate-Wirkung hängt **nicht** an Report-Zählern (das Gate nutzt `blocking_findings` +
`suppression_applies`, §4/E1), daher ist keine Zähler-Umdeutung nötig. Die UI kennzeichnet
unterdrückte Blocker über `counts.suppressed_blockers` und ein eigenes Badge, statt `counts.blockers`
umzudeuten.

`run_audit`-Verhalten:
- `include_suppressed=True` (Default, O3): unterdrückte Findings bleiben in `findings` und werden
  mit `suppressed=true` markiert. Nichts wird versteckt.
- `include_suppressed=False`: unterdrückte Findings werden aus `findings` gefiltert;
  `counts.*` beschreiben dann die **gefilterte** Liste, `total_*_available` weiterhin den
  **ungefilterten** (und ungecappten) Lauf.
- **m7-Invariante (explizit, dokumentiert und getestet):** bei `include_suppressed=False` gilt
  bewusst `counts.total != total_findings_available` (sofern unterdrückte Findings gefiltert
  wurden oder der Lauf gecappt ist), weil `counts.*` den zurückgegebenen Fensterinhalt und
  `total_*_available` den **ungefilterten, ungecappten** Gesamtlauf beschreiben. Der Report trägt
  bei aktivem Filter `suppressed_filtered: int` (Anzahl der aus `findings` entfernten Findings),
  damit ein Konsument die Differenz erklären kann.
- **Immer-Identität (Severity ist binär, R3-01):** `counts.blockers + counts.warnings ==
  counts.total` gilt **unbedingt** — alle drei Zähler werden aus derselben `findings`-Liste
  berechnet (`AuditReport.to_dict()`, `audit_service.py:136-151`), und `Severity` hat genau zwei
  Mitglieder `BLOCKER`/`WARNING` (`traceability/audit/types.py:35-36`). Die Filter-/Cap-Differenz
  zeigt sich ausschließlich zwischen `counts.*` (Fenster) und `total_*_available` (Gesamtlauf),
  **nie** innerhalb der `counts`-Summe. Eine `counts.total != counts.blockers + counts.warnings`-
  Ungleichung wäre arithmetisch unerreichbar und ist daher **nicht** Teil des Vertrags.

`suppress_finding`-Semantik (Revision 3):

1. `_set_tenant_context(ctx)`; `assert_gate_waiver_authority(ctx)` → fängt
   `GovernanceAuthorityError` und wirft `PermissionDeniedError` (M2 — derselbe SSOT-Choke-Point
   wie der Gate-Waiver, inkl. ADMIN-Tier für API-Keys, §865).
2. **Autor-Erfassung (rev3):** `granted_by = str(getattr(ctx, "user_id", "") or "").strip()`; ein
   leeres Ergebnis ⇒ `PermissionDeniedError` (**403**, §3.2).
3. `validate_waiver_reason(reason, label="suppression justification")` (SSOT, M2) → fängt
   `GovernanceReasonError` und wirft `WaiverReasonPolicyViolation(str(exc))`
   (**400** `WAIVER_REASON_REJECTED`, §3.4.2).
4. **Eingabe-Prüfung `expires_at` (D2):** naive Zeitstempel und `expires_at <= now` ⇒
   `ValidationError` (**400** `VALIDATION_ERROR`). Die Prüfung liegt im Serializer/Parse-Layer
   **und** defensiv im Service.
5. **C1 — Existenz-Prüfung mit Scope.** Die Prüfung läuft gegen den **vollständigen, ungecappten**
   Lauf über die vom Aufrufer benannten Scopes:
   `scopes = [AuditScope(scope, artifact_id=scope_artifact_id)] if scope else None` (bei
   `scope="document"` ist `scope_artifact_id` Pflicht, sonst `ValidationError`; ungültiger
   `scope`-Wert → `ValidationError`). Ohne `scope` bleibt der bisherige Engine-Default
   (`[AuditScope("project")]`, `rule_engine.py:102-104`) — damit sind document-scoped Findings
   (z. B. `TRACE-P7`) über die Oberflächen **unterdrückbar** (Review C1). `scope`/
   `scope_artifact_id` aus dem Request werden **nur** für diesen Engine-Lauf genutzt.
6. **O2 — blocker-only.** Gematcht wird ausschließlich gegen **BLOCKER**-Findings
   (`Severity.BLOCKER`) des ungecappten Laufs. WARNING-Findings sind nicht unterdrückbar
   (konsistent zu DoD „Blocker-Finding"); die Existenz-Prüfung basiert auf `blocking_findings`-
   Semantik, nicht auf dem vollen Lauf. Kein Treffer ⇒ `WaiverFindingNotBlockingError`
   (**400** `WAIVER_FINDING_NOT_BLOCKING`, §3.4.2 — **nicht** 422). Der Match verwendet den
   **scope-losen** `finding_key`; sind mehrere Findings mit demselben Key in
   verschiedenen Scopes unterwegs, wird bei angegebenem `scope` der scope-gleiche Treffer gewählt,
   sonst der erste Treffer (Scope des gematchten Findings ist danach maßgeblich).
7. Die **persistierten** `scope`/`scope_artifact_id` stammen weiterhin aus dem **gematchten
   Finding**, nicht vom Client (`BlockerWaiverSerializer`-Prinzip, `serializers.py:1496-1499`);
   ein scope-agnostisches Finding führt zu `scope=""` (ungebunden, §3.1 R2a; §1 Zeilenformen).
8. `record_waiver(..., granted_by=granted_by, expires_at=expires_at)` → `(row, created)`; **m1:**
   existiert nur eine **abgelaufene** Zeile für den Key, wird `SuppressionExpiredError` →
   `409 SUPPRESSION_EXPIRED` geworfen (keine stille 200). **R3-07-Präzedenz:** die
   `expires_at`-Prüfung aus Schritt 4 (E3/D2, 400) ist zu diesem Zeitpunkt bereits gelaufen und
   hat Vorrang — dieser Zweig greift nur, wenn ein **gültiges** `expires_at` (oder keines) im
   Request stand. Bei `created=True` Audit-Eintrag `baseline.waiver_create` (unverändert,
   `audit/models.py:165`). Der Service **konstruiert** einen `details`-Payload mit `finding_key`,
   `workspace_id`, `rule_id`, `artifact_ids`, `scope`, `scope_artifact_id`, `expires_at`,
   `granted_by`; dieser ist **nur an der `_audit`-Aufrufgrenze** verifizierbar — der Writer
   persistiert `details` **nicht** (§1/M3-Korrektur). **Durable** ist die `AuditEntry`-Zeile
   selbst (`op`/`entity_type`/`entity_id`/`actor`/`change_reason=reason`) **plus** die
   `BaselineGateWaiver`-Zeile; auf dem **MCP**-Pfad ist `change_reason` `None`, die Begründung
   dort nur über den Join `AuditEntry.entity_id → BaselineGateWaiver.id` erreichbar (AC-569-09).
9. Rückgabe `(SuppressionView(row), created)`.

### 3.4 REST (`backend/rest_api/audit_views.py`, `urls.py`, `serializers.py`)

**Neue Endpunkte** (Reihenfolge in `urls.py` **vor** dem generischen `audit/`-Run-Route, analog zu
`urls.py:833-845`):

| Methode | Pfad | View | Status |
|---|---|---|---|
| `POST` | `/api/v1/workspaces/<uuid:workspace_id>/audit/waivers/` | `WorkspaceAuditWaiverView.post` | 201 neu / 200 bereits vorhanden |
| `GET` | `/api/v1/workspaces/<uuid:workspace_id>/audit/waivers/` | `WorkspaceAuditWaiverView.get` | 200 |
| `GET` | `/api/v1/workspaces/<uuid:workspace_id>/audit/?include_suppressed=true\|false` | `WorkspaceAuditView.get` (erweitert) | 200 |

**Request-Body `POST …/audit/waivers/`** (neuer `WaiverCreateSerializer`,
`UnknownFieldRejectionMixin`):

```jsonc
{
  "rule_id": "TRACE-P1",            // Pflicht, max 64
  "artifact_ids": ["<uuid>", "..."],// optional, Default []
  "scope": "document",              // optional (C1): "document"|"project"|"global"; nur für den Engine-Lauf
  "scope_artifact_id": "<uuid>",    // optional (C1): Pflicht bei scope="document"
  "reason": "Accepted deviation …", // Pflicht, nicht blank, Policy via validate_waiver_reason
  "expires_at": "2026-12-31T00:00:00Z" // optional, ISO-8601; null/weggelassen = unbefristet
}
```

`scope`/`scope_artifact_id` werden **nur** zur Auswahl des Engine-Scopes für die Existenz-Prüfung
verwendet (C1); die **persistierten** Werte stammen weiterhin ausschließlich aus dem gematchten
Finding (§3.3 Schritt 7). Ohne `scope` gilt der bisherige Project-Default.
`granted_by` ist **kein** akzeptiertes Body-Feld (`UnknownFieldRejectionMixin` ⇒ 400, §3.2).

**Query-Param `?include_suppressed=true|false` (m2).** Neuer Parse-Helfer analog
`_parse_scopes`/`_parse_pagination` (`audit_views.py:90-128`): abwesend → `True` (O3); akzeptiert
werden ausschließlich die Literale `true` und `false` (case-insensitiv); jeder andere Wert wirft
`ValueError` → `400 VALIDATION_ERROR`. `?state=` auf der Waiver-Liste akzeptiert nur
`active|expired|all` (Default `active`); sonst `400 VALIDATION_ERROR`.

**Response-Shape** (`SuppressionView.to_dict()`):

```jsonc
{
  "waiver_id": "<uuid>",
  "finding_key": "TRACE-P1\u001fa1,a2",
  "identity_key": "TRACE-P1\u001fa1,a2\u001fproject",
  "rule_id": "TRACE-P1",
  "artifact_ids": ["<uuid>", "..."],
  "scope": "project",
  "scope_artifact_id": "",
  "reason": "…",
  "granted_by": "<user-id>",
  "created_at": "2026-09-22T10:00:00Z",
  "expires_at": null,
  "state": "active"
}
```

**Response `GET …/audit/waivers/?state=active|expired|all`** (Default `active`):

```jsonc
{
  "waivers": [ /* SuppressionView */ ],
  "counts": { "active": 3, "expired": 1 }
}
```

#### 3.4.1 Endpoint-/Status-Code-Vertrag (M-A) — disjunkt und deterministisch

**Verbindliche Invariante (D1, R3-06):** Die neuen Waiver-Endpunkte und der erweiterte
Report-Endpunkt emittieren **niemals HTTP 422**. **422 bleibt in diesem Audit-Modul ausschließlich
`POST …/audit/remediate/` vorbehalten** und trägt dort die Bedeutung „Adopt nicht automatisch
anwendbar → Modify anbieten"
(`audit_views.py:207-213`; Frontend: `client.ts:303-324` → `UnprocessableEntityError`,
`audit-dashboard.tsx:309` flippt das Finding auf Modify). **Kein neuer Fehlerfall darf diesen
Status wiederverwenden** — die UI würde sonst „Begründung abgelehnt" nicht von „Adopt-Konflikt"
unterscheiden können (Review N1). Der codebase-weite 422-Nutzer
`architecture_decompose_views.py:156` liegt außerhalb dieses Moduls und bleibt unberührt
(R3-06 — die Aussage „422 nur bei remediate" gilt modul-, nicht codebase-weit).

| # | Endpunkt | Bedingung | HTTP | `error.code` |
|---|---|---|---|---|
| E1 | `POST …/audit/waivers/` | Waiver neu angelegt | **201** | — |
| E2 | `POST …/audit/waivers/` | Identischer **aktiver** Waiver liegt bereits vor (idempotent, keine Änderung) | **200** | — |
| E3 | `POST …/audit/waivers/` | Body nicht parsebar / unbekanntes Feld (inkl. `granted_by`) / falscher Typ / `expires_at` malformed, naiv oder `<= now` / `scope` ungültig / `scope_artifact_id` fehlt bei `scope="document"` | **400** | `VALIDATION_ERROR` |
| E4 | `POST …/audit/waivers/` | `reason` verletzt die SSOT-Policy (blank, Platzhalter, Regel-ID-Echo) | **400** | `WAIVER_REASON_REJECTED` |
| E5 | `POST …/audit/waivers/` | Benanntes Finding ist im ungecappten Lauf **nicht als BLOCKER** berichtet (unbekannt oder nur WARNING) | **400** | `WAIVER_FINDING_NOT_BLOCKING` |
| E6 | `POST …/audit/waivers/` | Keine Admin/Approver-Rolle, API-Key unterhalb ADMIN-Tier, oder `granted_by` nicht auflösbar | **403** | `PERMISSION_DENIED` |
| E7 | `POST …/audit/waivers/` | Workspace nicht im Tenant des Aufrufers | **404** | `NOT_FOUND` |
| E8 | `POST …/audit/waivers/` | Für den `finding_key` existiert **nur** eine abgelaufene Zeile (m1). **Präzedenz (R3-07):** die E3-`expires_at`-Prüfung des Requests läuft davor — tragen Request und Bestand zugleich einen abgelaufenen Stand, gewinnt **E3 (400)**. | **409** | `SUPPRESSION_EXPIRED` |
| E9 | `POST …/audit/waivers/` | Unerwarteter Serverfehler | **500** | `INTERNAL_SERVER_ERROR` |
| E10 | `GET …/audit/waivers/` | OK | **200** | — |
| E11 | `GET …/audit/waivers/` | `state` nicht in `active\|expired\|all` | **400** | `VALIDATION_ERROR` |
| E12 | `GET …/audit/waivers/` | Kein Workspace-Zugriff | **403** | `PERMISSION_DENIED` |
| E13 | `GET …/audit/waivers/` | Workspace nicht im Tenant | **404** | `NOT_FOUND` |
| E14 | `GET …/audit/` (erweitert) | OK | **200** | — |
| E15 | `GET …/audit/` (erweitert) | `include_suppressed`/`scope`/`scope_artifact_id`/`limit`/`offset` ungültig | **400** | `VALIDATION_ERROR` |
| E16 | `GET …/audit/` (erweitert) | Workspace nicht im Tenant | **404** | `NOT_FOUND` |
| E17 | `POST …/audit/remediate/` (**unverändert**) | Automatischer Fix nicht anwendbar | **422** | `VALIDATION_ERROR` |
| E18 | jeder neue Endpunkt | **irgendetwas** | **422** | **RESERVIERT — darf nicht auftreten** |
| E19 | `GET …/audit/waivers/` | Unerwarteter Serverfehler | **500** | `INTERNAL_SERVER_ERROR` |
| E20 | `GET …/audit/` (erweitert) | Unerwarteter Serverfehler | **500** | `INTERNAL_SERVER_ERROR` |

**Totality des GET-Status-Sets (R3-05).** E10–E16 sind um die Serverfehler-Zeilen E19/E20
ergänzt. Der erweiterte Report-Endpunkt `GET …/audit/` hat bewusst **keine** eigene
403-Zeile: `WorkspaceAuditView.get` fängt heute nur `NotFoundError` → 404 und ein
`except Exception` → 500 (`audit_views.py:155-164`); ein `PermissionDeniedError` aus `run_audit`
ergäbe dort eine **500**. #569 ändert dieses Status-Set **nicht** — der Endpunkt bleibt bei
200 (E14) / 400 via Parse (E15) / 404 (E16) / 500 (E20); additiv kommt nur der Query-Param und
die 400-Zeile E15 hinzu. Der **neue** `GET …/audit/waivers/`-Endpunkt hat dagegen eine eigene
403-Zeile (E12), weil er den Autoritäts-/Workspace-Guard explizit auswertet.

**RFC-9110-Begründung der Aufteilung:**

- **400 Bad Request** (RFC 9110 §15.5.1: „cannot or will not process the request due to something
  that is perceived to be a client error … malformed request syntax … deceptive request routing")
  für alle Fälle, in denen der Request selbst fehlerhaft ist — Syntax, unbekannte Felder, ungültige
  Enum-Werte, eine Begründung, die die dokumentierte Policy nicht erfüllt, oder ein benanntes
  Finding, das im aktuellen Lauf nicht blockiert. Der letzte Fall ist zusätzlich durch
  **Konsistenz mit dem bestehenden `waived_findings`-Pfad** begründet: `_apply_waivers` wirft für
  exakt dieselbe Bedingung `ValidationError` (`baseline_facade.py:620-627`), und
  `_service_error_response` mappt das auf **400** (`views.py:170`, `:192-193`). Ein 422 für die
  neue Oberfläche würde dieselbe Bedingung auf zwei Endpunkten unterschiedlich beantworten.
- **403 Forbidden** (§15.5.4: der Server hat die Anfrage verstanden, verweigert aber die
  Autorisierung) für Rollen-/Tier-Verweigerungen.
- **404 Not Found** (§15.5.5) für einen Workspace außerhalb des Tenants — derselbe Status wie im
  bestehenden `WorkspaceAuditView` (`audit_views.py:155-159`).
- **409 Conflict** (§15.5.10: „request could not be completed due to a conflict with the current
  state of the target resource") für den m1-Fall: der Request ist wohlgeformt und autorisiert, aber
  der Zustand der Zielressource (nur eine abgelaufene Zeile zum selben `finding_key`) verbietet die
  idempotente 200-Quittung. 409 ist hier korrekt und nicht 400, weil der Fehler nicht in der
  Request-Form liegt. **Präzedenz (R3-07):** trägt der Request selbst ein abgelaufenes/naives
  `expires_at`, antwortet der Endpunkt **400 (E3)** — nicht 409 (E8); die Request-Form-Prüfung
  läuft zuerst. **Nicht client-auflösbar bis O1 (Ruling 1):** solange der Revoke-/Re-Grant-Pfad
  (O1) fehlt, kann der Client den 409 **nicht** durch eine reguläre Folgeanfrage auflösen — es gibt
  keinen Wieder-Inkraftsetzungsweg. Der 409 ist daher ein terminaler Governance-Hinweis, **keine**
  „resolve and resubmit"-Aufforderung; die heutige Antwortmöglichkeit liegt beim Auftraggeber
  (Produktentscheidung O1) bzw. beim groben, unveränderten `override_reason` (E4).
- **422 Unprocessable Content** (§15.5.21) bleibt bei seinem bestehenden, engen Wirt
  (`remediate`) und wird nicht erweitert.

#### 3.4.2 Fehler-Typ-Vertrag über die Layer-Grenze (M-B)

**Ist-Zustand (gemessen):** `rest_api/views.py:166-168` dokumentiert ausdrücklich, dass
`_EXC_TO_HTTP`/`_EXC_TO_CODE` per **exakter** Typ-Identität (`type(exc)`) nachschlagen und ein
nicht registrierter Subtyp **stillschweigend auf 500** degradiert. `audit_views.py` mappt
`ValidationError` → **422** (`:207-213`) und Parse-/Serializer-Fehler → **400** (`:141-144`,
`:178-184`). Ein einziger `ValidationError`-Typ kann die in §3.4.1 geforderte Aufteilung daher
**nicht** ausdrücken (Review N1). Auf MCP-Seite ist die Code-Menge eine geschlossene Registry
(`protocol_handler.py:51-122`); unbekannte Codes erhalten den numerischen Default `-32603`.

**Vertrag:**

| Layer | Typ | Modul | Wird geworfen von | Remap | REST | MCP-Code |
|---|---|---|---|---|---|---|
| L1 | `GovernanceReasonError(BaselineError)` | `baseline/exceptions.py` (**neu**) | `baseline.waivers.validate_waiver_reason` | module-level `_validate_gate_reason` → `ValidationError` (Bestandspfad **unverändert**); `AuditService.suppress_finding` → `WaiverReasonPolicyViolation` | (via Remap) | (via Remap) |
| L1 | `GovernanceAuthorityError(BaselineError)` | `baseline/exceptions.py` (**neu**) | `baseline.waivers.assert_gate_waiver_authority` | beide Fassaden → `PermissionDeniedError` | **403** | `PERMISSION_DENIED` |
| L2 | `WaiverReasonPolicyViolation(ValidationError)`, `error_code="WAIVER_REASON_REJECTED"` | `application/base.py` (**neu**) | `AuditService.suppress_finding` (Schritt 3) | — | **400** `WAIVER_REASON_REJECTED` | `WAIVER_REASON_REJECTED` |
| L2 | `WaiverFindingNotBlockingError(ValidationError)`, `error_code="WAIVER_FINDING_NOT_BLOCKING"` | `application/base.py` (**neu**) | `AuditService.suppress_finding` (Schritt 6) | — | **400** `WAIVER_FINDING_NOT_BLOCKING` | `WAIVER_FINDING_NOT_BLOCKING` |
| L2 | `SuppressionExpiredError(ValidationError)`, `error_code="SUPPRESSION_EXPIRED"` | `application/base.py` (**neu**) | `AuditService.suppress_finding` (Schritt 8) | — | **409** `SUPPRESSION_EXPIRED` | `SUPPRESSION_EXPIRED` |
| L0 | `ValidationError` | `persistence/errors.py` (Bestand) | Parse-/Serializer-Layer, Service-Eingabe | — | **400** `VALIDATION_ERROR` | `VALIDATION_ERROR` |
| L0 | `PermissionDeniedError` | `persistence/errors.py` (Bestand) | Autorität/Autor | — | **403** `PERMISSION_DENIED` | `PERMISSION_DENIED` |
| L0 | `NotFoundError` | `persistence/errors.py` (Bestand) | Tenant-Guard | — | **404** `NOT_FOUND` | `NOT_FOUND` |

**Warum Subklassen von `ValidationError`?** Genau das Präzedenz-Muster von
`BaselineGateBlockedError` (`application/base.py:61-77`): ein `ValidationError`-Subtyp, damit
**jeder** bestehende `except ValidationError`-Handler weiterhin greift, aber ein *distinkter* Typ,
damit die API-Schicht einen eigenen Code/Status antworten kann. Die Klasse trägt den Code als
Klassenattribut `error_code`, damit Adapter ihn nicht duplizieren.

**Registrierungs-Pflichten (N6):**

1. Die drei neuen L2-Typen **werden** in `rest_api/views.py` registriert:
   `_EXC_TO_HTTP[WaiverReasonPolicyViolation] = 400`,
   `_EXC_TO_HTTP[WaiverFindingNotBlockingError] = 400`,
   `_EXC_TO_HTTP[SuppressionExpiredError] = 409` sowie die passenden `_EXC_TO_CODE`-Einträge.
   Damit ergibt ein Escape aus einem beliebigen View **nie** einen 500 mit
   `INTERNAL_SERVER_ERROR` statt der fachlichen Antwort. (Der `WorkspaceAuditWaiverView` fängt die
   Typen ohnehin lokal — die Registrierung ist der Fail-closed-Gürtel dazu.)
2. `GovernanceReasonError` und `GovernanceAuthorityError` dürfen `_service_error_response`
   **nie** erreichen: sie werden in `BaselineFacade` und `AuditService` geremappt (Zeilen 1–2 der
   Tabelle). Ein Adapter, der sie doch sieht, hat einen Bug — die Registrierung erfolgt bewusst
   **nicht**, damit ein solcher Bug laut (500 + Log) statt still als 400 auftritt.
3. `serializers.py::_ERROR_MESSAGES` erhält DE+EN-Einträge für die drei neuen Codes
   (`WAIVER_REASON_REJECTED`, `WAIVER_FINDING_NOT_BLOCKING`, `SUPPRESSION_EXPIRED`). Die
   Registry ist bilingual vollständig zu halten (CI-Regel am Modulkommentar `:85-86`).
4. `mcp_server/protocol_handler.py` erhält je neuen Code eine **Message-Zeile in `ERROR_CODES`**
   (Mapping Name → Meldungs-String) **und einen numerischen Eintrag in `ERROR_CODE_MAP`**
   (Mapping Name → int): `WAIVER_REASON_REJECTED → -32008`,
   `WAIVER_FINDING_NOT_BLOCKING → -32009`, `SUPPRESSION_EXPIRED → -32010` (nächste freie
   Server-Codes nach `RATE_LIMITED: -32007`). Diese Registrierung ist **nicht** mit
   `_PROTOCOL_ERROR_CODES` zu verwechseln — siehe §3.5, R3-02/R3-13.

**Negativ-Invariante (DoD 6, Geltungsbereich R3-08):** „Kein Weg darf existieren, ein
Blocker-Finding ohne Begründung und Audit-Spur loszuwerden." Auf den **neuen** Oberflächen
erzwingt der Vertrag das dreifach: (a) eine Policy-Verletzung ist ein eigener, nicht
schluckbarer 400-Typ; (b) die Begründung wird als `change_reason` des
`baseline.waiver_create`-Audit-Eintrags persistiert (§3.3 Schritt 8; auf dem **MCP**-Pfad ist
`change_reason` `None` — die Begründung bleibt dort über den Join `AuditEntry.entity_id →
BaselineGateWaiver.id` erreichbar, AC-569-09); (c) `granted_by` ist auf den neuen Oberflächen
Pflicht und kommt ausschließlich aus dem AuthContext (§3.2). **Geltung der Dreiteilung
(präzisiert 2026-09-22):** (a) Reason-Policy und (c) Audit-Eintrag gelten auf **allen** Pfaden;
(b) die Autor-Pflicht gilt **nur** auf den neuen Oberflächen. Der bestehende Gate-Pfad
(`baseline_facade.py:594`) prüft den Autor **nicht** und bleibt unverändert; bereits persistierte
`granted_by=""`-Bestandszeilen werden nicht nachträglich verworfen oder migriert (dokumentierte
Schuld auf append-only-Zeilen, keine History-Rewrite).

Bestehende Response-Shapes (`remediate`, `ai-review`, `audit/`-Basis) bleiben unverändert;
`audit/` erhält nur additive Felder/Query-Param.

### 3.5 MCP (`backend/mcp_server/tools/audit.py`, `tool_registry.py`)

Neue Tools in der Gruppe `audit` (kein neuer Namespace):

| Tool | Modus | Registry-Eintrag | Handler |
|---|---|---|---|
| `audit.waive_finding` | write | `_WRITE_TOOL_PREFIXES += "audit.waive_finding"`; **neue** `_GOVERNANCE_TOOL_NAMES += "audit.waive_finding"` | `_handle_waive_finding` |
| `audit.waivers` | read | `_READ_ONLY_TOOL_NAMES += "audit.waivers"` | `_handle_waivers` |

**`audit.waivers` — Tier vs. effektive Autorität (Post-Implementierungs-Review, 2026-09-22).**
Der Tool-Tier bleibt **read** (`_READ_ONLY_TOOL_NAMES`; es endet nicht auf `.read`/`.query`), aber
der Handler `_handle_waivers` erzwingt **zusätzlich** denselben Approval-Authority-Choke-Point wie
der REST-Zwilling `GET …/audit/waivers/` (REST-E12, §3.4.1): ein Editor/Viewer erhält auf MCP
`PERMISSION_DENIED` — exakt wie auf REST. **Rationale (eine Zeile):** die Suppressions-Liste ist
Governance-Metadaten (wer / warum), und eine Lesbarkeit über die schwächere MCP-Tür wäre eine
transportabhängige Asymmetrie, die ein Aufrufer durch bloßes Wechseln des Transports ausnutzen
könnte. **Vertrag: Tier = read, effektive Autorität = Approval-Authority** (intentional strenger
als der reine Read-Tier der Tool-Tabelle). Siehe AC-569-07/V11.

**M1 — kein Namespace-Eintrag, sondern Tool-Level-Governance.** `_GOVERNANCE_TOOL_NAMESPACES`
darf **nicht** um `"audit"` erweitert werden: `audit.se_audit` steht **nicht** in
`_READ_ONLY_TOOL_NAMES` (`tool_registry.py:395-510`; dort nur `audit.query`/`audit.ai_review`,
Z. 420-421) und endet nicht auf `.read`/`.query` (Z. 512), ist also per Fail-closed-Default
(`_is_write_tool`, Z. 1392-1407) ein **Write**-Tool und mappt heute auf `Operation.WRITE`
(AUTHOR-Tier, Z. 1424-1430). Ein Namespace-Eintrag würde es still auf
`Operation.WORKSPACE_CONFIG` (ADMIN-Tier) heben und einem AUTHOR-Tier-Key den Zugriff nehmen —
entgegen der dokumentierten Nicht-Admin-Ausnahme
(`mcp_server/tests/test_mcp_rbac_role_matrix.py:250-268`). Daher:

- Neue **Tool-Level-Menge** `_GOVERNANCE_TOOL_NAMES: frozenset[str]` (additiv, enthält zunächst
  `"audit.waive_finding"`); `_required_scope_operation` prüft **erst** den exakten Tool-Namen
  gegen diese Menge und **danach** den Namespace gegen `_GOVERNANCE_TOOL_NAMESPACES`.
- `audit.se_audit` bleibt damit **AUTHOR-Tier** (`Operation.WRITE`) — nicht READ-Tier, wie in
  Revision 1 fälschlich behauptet. `audit.query`/`audit.ai_review` bleiben READ-Tier. Der
  Ist-Tier von `audit.se_audit` wird mit einem Test gepinnt (AC-569-18).
- `audit.waivers` in `_READ_ONLY_TOOL_NAMES` (exakter Name; es endet nicht auf `.read`/`.query`).

`audit.waive_finding` Input-Schema (C1: `scope`/`scope_artifact_id` additiv, nur für den
Engine-Lauf):

```jsonc
{
  "workspace_id": "<uuid>",       // Pflicht
  "rule_id": "TRACE-P1",          // Pflicht
  "artifact_ids": ["<uuid>"],     // optional
  "scope": "document",            // optional (C1): document|project|global
  "scope_artifact_id": "<uuid>",  // optional (C1): Pflicht bei scope="document"
  "reason": "…",                  // Pflicht
  "expires_at": "…Z"              // optional
}
```

Handler: delegiert ausschließlich an `AuditService().suppress_finding(...)`; auditierbar via
`write_mcp_audit(operation="baseline.waiver_create", entity_type="BaselineGateWaiver", …)` innerhalb
eines `mcp_audit_handoff()`-Blocks (Codeberg #313-Muster, `tools/audit.py:758`). Kein neuer
`AuditEntry`-OP-Wert nötig. Kein Admin-Gate im Handler (die Fassade prüft Autorität), aber
ADMIN-Tier über die Registry (`_GOVERNANCE_TOOL_NAMES`).

`audit.waivers` Input: `{ workspace_id, state? }` → Response = Shape aus 3.4.

`audit.se_audit` erhält additiven Param `include_suppressed` (Default `true`, O3) und gibt die
neuen Report-Felder unverändert durch.

**Fehler-Mapping des Handlers (M-B, identisch zur REST-Seite §3.4.2):**

| Ausnahme | MCP-`error_code` (String) | JSON-RPC-Code in `ERROR_CODE_MAP` |
|---|---|---|
| `WaiverReasonPolicyViolation` | `WAIVER_REASON_REJECTED` | `-32008` |
| `WaiverFindingNotBlockingError` | `WAIVER_FINDING_NOT_BLOCKING` | `-32009` |
| `SuppressionExpiredError` | `SUPPRESSION_EXPIRED` | `-32010` |
| `PermissionDeniedError` | `PERMISSION_DENIED` | `-32001` |
| `NotFoundError` | `NOT_FOUND` | `-32004` |
| `ValidationError` (Rest) | `VALIDATION_ERROR` | `-32602` |

Die Reihenfolge der `except`-Zweige ist **typ-spezifisch vor generisch** (die drei neuen Typen
sind `ValidationError`-Subklassen und würden sonst als `VALIDATION_ERROR` verschluckt).

**Wire-Verhalten auf `tools/call` (R3-02 — verbindlich).** Die drei neuen Codes stehen **nicht**
in `_PROTOCOL_ERROR_CODES` (`protocol_handler.py:96-103`). Auf dem Standard-`tools/call`-Pfad
greift daher der `isError`-Zweig (`:585-595`): die Antwort ist ein **erfolgreiches
JSON-RPC-Result** mit `result.isError == true` und dem **String**-`error_code`
(`WAIVER_REASON_REJECTED` / `WAIVER_FINDING_NOT_BLOCKING` / `SUPPRESSION_EXPIRED`) — **kein**
numerischer JSON-RPC-Code. Das ist identisch zu jedem anderen Tool-Ausführungsfehler (z. B.
`NOT_FOUND`). Der numerische Code (`ERROR_CODE_MAP[...]`) ist auf dem Wire nur bei
**Protokoll-Fehlern** bzw. beim **Direct-Method-Dispatch** sichtbar; dort bleibt der
JSON-RPC-Error-Vertrag. `_PROTOCOL_ERROR_CODES` wird **nicht** erweitert — das wäre eine bewusste
Frame-Shape-Änderung und ist ausdrücklich **nicht** Teil von #569.

Die Registrierung der drei neuen Codes in `ERROR_CODES`/`ERROR_CODE_MAP` ist in §3.4.2
Registrierungs-Pflicht 4 spezifiziert (nächste freie Server-Codes nach `RATE_LIMITED: -32007`);
sie ist **nicht** mit `_PROTOCOL_ERROR_CODES` zu verwechseln.

### 3.6 Frontend (`frontend/src/api/audit.ts`, `…/Audit/audit-dashboard.tsx`, `i18n/**`)

`api/audit.ts` additiv:

```ts
export interface AuditFinding {
  // bestehende Felder unverändert …
  finding_key: string;                    // NEU (Backend liefert es bereits)
  suppressed: boolean;                    // NEU
  suppressed_until: string | null;        // NEU
  suppression_reason: string | null;      // NEU
  suppression_id: string | null;          // NEU
}
export interface AuditCounts { total: number; blockers: number; warnings: number; suppressed: number; suppressed_blockers: number; }
export interface SuppressionView { /* 1:1 zu 3.4 */ }
export interface WaiveRequest {
  rule_id: string;
  artifact_ids: string[];
  scope?: AuditScopeKind;            // C1: aus dem Finding der Zeile übernommen
  scope_artifact_id?: string;        // C1: aus dem Finding der Zeile übernommen
  reason: string;
  expires_at?: string;
}
export interface RunAuditOptions { /* … */ includeSuppressed?: boolean; }

auditApi.waive(workspaceId, data: WaiveRequest): Promise<SuppressionView>;
auditApi.waivers(workspaceId, state?: "active" | "expired" | "all"): Promise<{ waivers: SuppressionView[]; counts: { active: number; expired: number } }>;
```

**C1 im UI:** der Waive-Dialog sendet den `scope`/`scope_artifact_id` **der angeklickten Zeile**
(Finding-Felder aus dem Report) mit — sonst schlägt die Existenz-Prüfung für ein document-scoped
Finding fehl. Die 4xx-Behandlung nutzt **`error.code`**, nicht nur den Status (D1/M-A):

- `WAIVER_REASON_REJECTED` → Feld-Fehler am Begründungs-Textfeld (`audit.waiveReasonRejected`).
- `WAIVER_FINDING_NOT_BLOCKING` → Hinweis, dass das Finding neu bewertet werden muss
  (`audit.waiveNotBlocking`), kein generisches Toast.
- `SUPPRESSION_EXPIRED` → eigene Meldung (`audit.waiveExpired`, verweist auf die ausstehende
  Revoke-Entscheidung O1), kein generisches Fehler-Toast.
- `VALIDATION_ERROR` → generisches Feld-Feedback.
- **422 wird auf den Waive-Pfaden nicht behandelt** (darf dort nicht auftreten, E18).

`audit-dashboard.tsx`:
- **Dritte Aktion** je Finding: „Unterdrücken" (`data-testid="audit-waive-<index>"`), sichtbar für
  `!finding.suppressed`. Öffnet einen Dialog (`data-testid="audit-waive-dialog"`) mit
  Pflicht-Textarea für die Begründung, optionalem Ablaufdatum und Bestätigung
  (`data-testid="audit-waive-confirm"`). Nach Erfolg: Finding wird in-place als unterdrückt markiert
  (kein Entfernen — Nachvollziehbarkeit), Toast `audit.waiveSuccess`.
- Unterdrückte Findings: Badge `data-testid="audit-suppressed-badge-<index>"` mit Begründung
  (`audit-suppression-reason-<index>`), Ablauf und Ausgrauen der Adopt/Modify-Aktion.
- **Filter** „unterdrückte anzeigen": Checkbox `data-testid="audit-show-suppressed"`, **Default an**
  (nichts wird standardmäßig versteckt). Abwählen filtert `suppressed === true` clientseitig.
- Counts-Badge für Unterdrückte (`data-testid="audit-count-suppressed"`, `variant="neutral"`);
  `counts.blockers` bleibt unverändert die deskriptive Blocker-Zahl (M5) — ein zusätzliches
  Badge für `counts.suppressed_blockers` macht unterdrückte Blocker sichtbar, ohne `counts.blockers`
  umzudeuten.
- **m3 — UI-Ratchet.** Für Dialog/Badge/Filter **keine neuen Inline-Styles** (`style={{ … }}`).
  `frontend/src/test/ui-ratchet.test.ts` prüft `STYLE_BRACE_BASELINE` mit **exakter** Gleichheit
  (`:1035`/`:1047`, aktuell `705` bei `:551`). Neue Styles ausschließlich als CSS-Modul mit
  `var(--…)`-Tokens aus `styles/tokens.css` bzw. als gehoistete `CSSProperties`-Konstanten. Wird
  die Inline-Zahl doch berührt, muss `STYLE_BRACE_BASELINE` im **selben** Commit bewusst
  nachgeführt werden (nie erhöht).
- i18n-Keys in `frontend/src/i18n/**` für DE und EN (Parität ist CI-relevant), **profilunabhängig
  neutral** (`audit.suppress…`; O6 — Audit-/Suppression-Begriffe sind nicht Teil des
  Terminology-Profils, `presets/terminology.py:49-74`).

---

## 4. Datenfluss

```
Finding (RuleEngine, flüchtig)
  └─ finding_key(rule_id, artifact_ids)          → persistierte Identität (scope-los, GH-821)
  └─ finding_key(rule_id, artifact_ids, scope)   → Anzeige-/Korrelationsidentität

Unterdrückung anlegen:
  REST POST /audit/waivers/  ─┐   (scope/scope_artifact_id optional, C1)
  MCP audit.waive_finding    ─┴─► AuditService.suppress_finding
                                     ├─ assert_gate_waiver_authority(ctx)      [SSOT M2: Admin/Approver + ADMIN-Tier]
                                     │    └─ GovernanceAuthorityError → PermissionDeniedError   [403]
                                     ├─ granted_by = ctx.user_id (leer → 403)
                                     ├─ validate_waiver_reason(reason)         [SSOT M2]
                                     │    └─ GovernanceReasonError → WaiverReasonPolicyViolation [400]
                                     ├─ expires_at-Guard (naiv / <= now → 400)  [D2]
                                     ├─ _run_engine_uncapped(scopes=[scope])   [C1; Default project]
                                     │    → nur BLOCKER-Findings matchen        [O2 blocker-only]
                                     │    → kein Treffer: WaiverFindingNotBlockingError [400]
                                     ├─ record_waiver(..., granted_by, expires_at) → BaselineGateWaiver-Zeile
                                     │    └─ nur abgelaufene Zeile vorhanden?  → SuppressionExpiredError [409]
                                     └─ ServiceBase._audit(baseline.waiver_create) → AuditLog

Audit-Report:
  AuditService.run_audit
    ├─ load_suppressions(workspace, tenant)       [nur aktive; R3 zur Entscheidungszeit, D3]
    ├─ suppression_applies(record, finding)       [Key R1 + Scope-Bindung R2a/b/c + Ablauf R3]
    ├─ AuditFindingView(suppressed=…, suppressed_until=…, suppression_reason=…)
    └─ counts.* deskriptiv (M5) + additiv counts.suppressed(_blockers)

Baseline-Gate (#490):
  BaselineFacade._enforce_audit_gate
    ├─ AuditService.blocking_findings(scopes=[build_scope])   [nur BLOCKER, ungecappt]
    ├─ load_suppressions + suppression_applies(record, f.rule_id, f.artifact_ids, f.scope, f.scope_artifact_id)
    │                                                          [M7: ersetzt die reine Key-Mengen-Zugehörigkeit]
    ├─ suppressed, remaining
    ├─ remaining leer?  → Baseline bauen
    └─ Description-Annotation (matched_waiver_ids, M4) + AuditLog-Aufruf mit `details`-Payload (nur an der `_audit`-Grenze prüfbar, M3-Korrektur) + Event-Payload
```

---

## 5. Gate-Semantik §490 — Entscheidung

**E1 — Zählt ein unterdrücktes Blocker-Finding als Blocker?**
**Nein.** Ein per aktiver Suppression abgedecktes Blocker-Finding wird aus `remaining` entfernt und
blockiert den Baseline-Build nicht. Das ist die bestehende GH-821-Semantik
(`baseline_facade.py:529-537`) und wird durch #569 nicht geändert. Nicht abgedeckte Blocker blockieren
weiterhin fail-closed (`BaselineGateBlockedError`), und der GH-400-„Auditor nicht auswertbar"-Pfad
bleibt unüberbrückbar. Die `override_reason`-Semantik (`:539-556`) bleibt **unverändert**; geändert
wird ausschließlich die Art, wie `suppressed` bestimmt wird (Mengen-Zugehörigkeit → R1–R3, M7).

**E2 — Wie wird die Unterdrückung in den Baseline-Metadaten mitprotokolliert?**
Dreifach, dauerhaft und ohne neues Metadaten-Schema:
1. **Immutable Baseline-Description** (`_annotate_waiver`, `baseline_facade.py:1205-1211`): die
   Beschreibung wird beim Erzeugen einmal geschrieben und ist durch die Snapshot-Immutabilität
   eingefroren. Sie wird erweitert um die **`matched_waiver_ids`** (§3.2/M4 — **alle** gematchten
   Zeilen, nicht nur die neu erzeugten; bei vielen Waivern gekappt analog `_MAX_LISTED_FINDINGS`,
   `:1099`, plus Zähler-Hinweis) und behält Anzahl + sortierte `rule_ids`.
2. **`BaselineGateWaiver`-Zeile** (append-only) mit Begründung, Autor, Scope und `expires_at`.
3. **AuditLog:** je **neu angelegtem** Waiver `baseline.waiver_create`, plus der
   `baseline.create`-Eintrag. **M3-Korrektur (Post-Implementierungs-Review, 2026-09-22):** Entgegen
   rev2/rev3 werden `details` **nicht** persistiert — der Writer ignoriert sie
   (`audit/services.py:159`, `audit/writer.py:190-202`; `AuditEntry` hat keine `details`-Spalte,
   `audit/models.py:246-306`). Der `baseline.create`-Service **konstruiert** in `details`
   `suppressed_blocker_count`, `suppressed_rule_ids`, `suppressed_finding_keys`, `waiver_ids`
   (`baseline_facade.py:272-287`) und additiv `matched_waiver_ids`, aber dieser Payload ist **nur
   an der `_audit`-Aufrufgrenze** verifizierbar. **Durable** ist (a) die `AuditEntry`-Zeile selbst
   (`op`/`entity_type`/`entity_id`/`actor`/`change_reason`) und (b) die append-only
   `BaselineGateWaiver`-Zeile; „wer / was / warum / bis wann" ist über den Join
   `AuditEntry.entity_id → BaselineGateWaiver.id` rekonstruierbar. Auf dem **MCP**-Pfad ist
   `change_reason` `None`, die Begründung dort also nur über diesen Join erreichbar (AC-569-09).
   Ein AuditLog-Writer-Umbau (der `details` persistierbar machen würde) bleibt ausdrücklich
   **Non-Goal** (§7); die strukturierte `details`-Queryability ist dorthin verschoben.

**E5 — Sind WARNING-Findings unterdrückbar? (O2, entschieden)**
**Nein — blocker-only.** `suppress_finding` prüft und matcht ausschließlich
`Severity.BLOCKER`-Findings (§3.3 Schritt 4). Das ist konsistent zum DoD-Wortlaut
(„Blocker-Finding") und zur bestehenden Gate-Praxis (`blocking_findings`, `audit_service.py:293-296`;
`_apply_waivers` validiert gegen Blocker, `baseline_facade.py:615-627`). WARNING-Findings bleiben
unverändert im Report und werden nicht markiert. Nebeneffekt (Threat-Model, m6): ein vorab
angelegter Waiver für ein heute als WARNING gewertetes Finding kann nach einem Tier-Wechsel keine
Blocker-Wirkung entfalten, weil er gar nicht erst angelegt werden kann.

**E6 — Scope-Bindung des Matchers (m4, entschieden)**
Regel R2b (§3.1) verhindert, dass ein für ein dokument-scoped Finding gewährter Waiver das
scope-agnostische Finding derselben Regel/Artefakte still mitunterdrückt. Die GH-821-Bestandszeilen
(produktionsreal `scope="project"`, `scope_artifact_id=""`) bleiben dabei wirksam. Siehe
AC-569-16/AC-569-27.

**E3 — Was passiert bei abgelaufenen Waivern? (D3)**
Ein abgelaufener Waiver (`expires_at <= now`) ist **nicht aktiv**: er unterdrückt weder im Report
noch im Gate. Das Finding erscheint wieder als normaler Blocker und blockiert den Baseline-Build,
bis es erneut unterdrückt oder global übersteuert wird. Die Waiver-Zeile bleibt erhalten und wird
über `GET …/audit/waivers/?state=expired|all` als `state: "expired"` sichtbar gemacht. Damit ist
Ablauf ein **Re-Evaluierungs-Trigger**, kein stiller Freibrief. `NULL`-Ablauf = unbefristet
(GH-821-Bestandsverhalten, keine Regression).

**Ablauf wird zur Entscheidungszeit ausgewertet, nicht in der Query persistiert (D3).** Konkret:
`load_suppressions(..., include_expired=False, now=<Auswertungszeitpunkt>)` filtert per Vergleich
gegen `now`; `suppression_applies` prüft R3 erneut. Es gibt **kein** `state`-Feld auf der Zeile,
**keinen** Celery-Job, **keine** ablaufende Cache-Invalidierung. Zwei Konsequenzen sind gewollt:
(a) ein zwischen zwei Builds ablaufender Waiver hört ohne jeden Hintergrundprozess auf zu wirken;
(b) `now` ist injizierbar (`now: datetime | None = None`) und damit in Tests deterministisch.

**E4 — Verhältnis zum globalen `override_reason` (GH-513)?**
Unverändert: per-Finding-Suppression ist selektiv, `override_reason` bleibt der grobe
Alles-oder-nichts-Hebel. Beide können koexistieren (`test_global_override_and_per_finding_waivers_coexist`).

---

## 6. Acceptance Criteria

Jedes AC ist Given/When/Then, mit Datei/Endpoint/Testname-Bezug.

### AC-569-COMPAT — byte-identischer `finding_key`-Pfad ohne `scope` (MUSS, nicht optional)

Deckt in Revision 2 die **vier** Teile der GH-821-Garantie aus §1 ab (a Rendering,
b Defensive-R2a-Abdeckung der neuen `scope=""`-Zeilenform, c Matching-Pfad-Wechsel,
d Mutationsprobe).

**(a) Rendering byte-exakt**
- **Given** die persistierten `BaselineGateWaiver`-Zeilen (GH-821) wurden mit dem Pre-#1021-Format
  `rule_id<US>a,b` geschrieben (`<US>` = `"\x1f"`).
- **When** `baseline.waivers.finding_key("TRACE-P1", ["b", "a"])` aufgerufen wird (kein `scope`).
- **Then** ist das Ergebnis exakt `"TRACE-P1\x1fa,b"` — byte-identisch; und
  `finding_key("TRACE-P1", ["a"], None) == finding_key("TRACE-P1", ["a"]) == finding_key("TRACE-P1", ["a"], "")`.
- **Test:** `backend/application/tests/test_audit_finding_identity_1021.py::TestCanonicalFindingKey::test_the_scope_less_rendering_is_byte_identical_to_the_legacy_format`
  (existiert) **plus** `backend/baseline/tests/test_waivers_569.py::test_unscoped_finding_key_is_byte_identical_to_persisted_gh821_rows`,
  der den Literal-Key zusätzlich gegen eine real persistierte Zeile vergleicht.

**(b) Defensive R2a-Abdeckung der neuen `scope=""`-Zeilenform**
- **Given** eine von #569 selbst erzeugte, ungebundene Waiver-Zeile (`scope=""` — so schreibt der
  neue `AuditService`-Pfad für scope-agnostische Findings, §1 „Zwei Zeilenformen"), und ein
  Finding mit demselben scope-losen `finding_key`. (`NULL` ist im `CharField(blank=True,
  default="")` (`models.py:230`) nicht repräsentierbar; `load_suppressions` normalisiert einen
  solchen Wert dennoch defensiv zu `""`, falls das Feld je auf nullable umgestellt wird.)
- **When** `suppression_applies(record, rule_id, artifact_ids, scope=<beliebig>)` geprüft wird.
- **Then** ist das Ergebnis `True` über **R2a** (ungebunden), unabhängig vom Scope des Findings.
- **Test:** `test_waivers_569.py::test_suppression_applies_is_gh821_backward_compatible` (R2a-Fall).

**(c) Matching-Pfad-Wechsel auf `suppression_applies` bricht keinen Bestandswaiver**
- **Given** eine **real über einen Gate-Build persistierte** GH-821-Zeile für eine
  scope-agnostische Regel (`TRACE-P1`) in der produktionsrealen Zeilenform `scope="project"`,
  `scope_artifact_id=""` (so schreibt es `record_waiver` via `finding.scope or scope`,
  `baseline_facade.py:635`), **und** der Matcher ist von reiner Key-Mengen-Zugehörigkeit auf
  `suppression_applies` umgestellt (`baseline_facade.py:529-534`, `:667-671`).
- **When** ein weiterer `create_baseline`-Lauf über denselben Workspace läuft (ohne den Waiver
  erneut mitzusenden).
- **Then** wird das Finding weiterhin als unterdrückt behandelt (kein erneuter Blocker), d. h.
  R2b greift für `finding.scope is None` + `record.scope_artifact_id == ""`.
- **Test:** `backend/application/tests/test_baseline_gate_waivers_569.py::test_pre_569_persisted_project_stamped_waiver_still_suppresses_after_matcher_switch`
  (Gate-Level; pinnt bewusst die Zeilenform `"project"`, **nicht** `""`).

**(d) Mutationsprobe (Pflicht)**
- **Mutationsprobe:** entfernt man die Kompatibilitäts-Verzweigung in
  `finding_key` (`backend/baseline/waivers.py:96-97`, `if not scope_part: return base`), dann
  **MUSS** `test_the_scope_less_rendering_is_byte_identical_to_the_legacy_format` rot werden
  (`"TRACE-P1\x1fa\x1f" != "TRACE-P1\x1fa"`). Analog: entfernt man in `suppression_applies` die
  R2a/R2b-Klauseln, wird `test_pre_569_persisted_project_stamped_waiver_still_suppresses_after_matcher_switch`
  rot. Beide Proben sind im jeweiligen Test-Docstring zu dokumentieren **und** mit einem
  wiederauffindbaren Marker `# mutation-probe: <was entfernt wird> ⇒ <welcher Test rot wird>`
  versehen; der PR-Beschreibung wird die Prozedur beigelegt, damit ein Reviewer die Probe manuell
  nachfahren kann (R3-11 — die Probe bleibt dokumentiert, nicht automatisiert).

### AC-569-01 — Finding-Identität dokumentiert + Re-Audit-stabil (auch scope-behaftet)

- **Given** ein scope-behaftetes Finding (`TRACE-P7`, `scope="document"`, `scope_artifact_id`).
- **When** zwei Audits über denselben Workspace laufen und dazwischen ein unbeteiligtes Finding
  hinzukommt.
- **Then** sind die **scope-losen** Keys (`finding_key(rule, ids)`) beider Läufe identisch und
  `AuditFindingView.finding_key` (scoped) bleibt ebenfalls stabil; `index` darf sich ändern.
- **Test:** Erweiterung von `TestStableAcrossReAudit` (`test_audit_finding_identity_1021.py:188-248`)
  um `test_a_scoped_finding_keeps_its_unscoped_key_across_re_audit`.

### AC-569-02 — Pflicht-Begründung, keine Platzhalter *(revidiert, M-A/M-B)*

- **Given** ein berichtetes Blocker-Finding.
- **When** `POST …/audit/waivers/` mit `reason="ok"`, `"aaaaaaaaaaaaaaa"`, `"test test test"`,
  `"   "` oder nur Regel-IDs (`"TRACE-P1 TRACE-P2"`) gesendet wird.
- **Then** antwortet der Endpunkt **`400` mit `error.code == "WAIVER_REASON_REJECTED"`** (nicht 422,
  nicht generisches `VALIDATION_ERROR`), es entsteht **keine** Zeile, kein AuditEntry, und der
  Fehlertext nennt die konkrete Anforderung.
- **Test:** `backend/rest_api/tests/test_audit_waivers_569_rest.py::test_placeholder_reason_is_rejected_with_400_and_dedicated_code`;
  MCP-Pendant `backend/mcp_server/tests/test_audit_tool_group.py::test_waive_placeholder_reason_returns_waiver_reason_rejected`
  (assert: `result.isError is True`, String-`error_code == "WAIVER_REASON_REJECTED"` und **kein**
  numerischer JSON-RPC-Code auf diesem `tools/call`-Pfad; der numerische Wert
  `ERROR_CODE_MAP["WAIVER_REASON_REJECTED"] == -32008` wird separat geprüft, §3.5/R3-02, V36).

### AC-569-03 — Audit-Log-Eintrag je neuem Waiver

- **Given** kein Waiver vorhanden.
- **When** ein gültiger Waiver erzeugt wird.
- **Then** existiert genau ein `AuditEntry` mit `op="baseline.waiver_create"`,
  `entity_type="BaselineGateWaiver"`, `change_reason == reason` und `actor` = Aufrufer.
- **Test:** `backend/application/tests/test_audit_waivers_569.py::test_each_new_suppression_gets_an_audit_entry`.

### AC-569-04 — REST-Create-Contract inkl. Idempotenz

- **Given** ein gültiges berichtetes Finding.
- **When** der Waiver zweimal mit identischem `rule_id`/`artifact_ids` gesendet wird.
- **Then** ist die erste Antwort `201` mit `created`-Semantik, die zweite `200`, es existiert genau
  **eine** Zeile, die ursprüngliche Begründung/Autor bleiben unverändert, und kein zweiter
  Audit-Eintrag entsteht.
- **Test:** `test_audit_waivers_569_rest.py::test_waiver_is_idempotent_per_finding`.

### AC-569-05 — REST-List-Contract

- **Given** je ein aktiver und ein abgelaufener Waiver.
- **When** `GET …/audit/waivers/` (Default) bzw. `?state=expired|all` aufgerufen wird.
- **Then** liefert der Default nur den aktiven (`state="active"`), `expired` nur den abgelaufenen,
  `all` beide; `counts` stimmen; `identity_key` trägt den Scope, `finding_key` nicht.
- **Test:** `test_audit_waivers_569_rest.py::test_list_filters_by_state`.

### AC-569-06 — MCP `audit.waive_finding` über die Fassade + Registry-Gating

- **Given** ein ADMIN-Tier-fähiger Aufrufer.
- **When** `audit.waive_finding` mit gültigen Parametern ausgeführt wird.
- **Then** wird über `AuditService.suppress_finding` persistiert, und
  `"audit.waive_finding" in _WRITE_TOOL_PREFIXES`;
  `"audit.waive_finding" in _GOVERNANCE_TOOL_NAMES`; `"audit" not in _GOVERNANCE_TOOL_NAMESPACES`;
  `"audit.waive_finding" not in _READ_ONLY_TOOL_NAMES`.
- **Test:** `backend/mcp_server/tests/test_audit_tool_group.py::test_waive_finding_is_write_and_governance_gated`.

### AC-569-07 — MCP `audit.waivers` (read) + `audit.se_audit` Sichtbarkeit

- **Given** ein aktiver Waiver und ein autorisierter Aufrufer (Approval-Authority).
- **When** `audit.waivers` bzw. `audit.se_audit` aufgerufen wird.
- **Then** listet `audit.waivers` den Waiver und ist in `_READ_ONLY_TOOL_NAMES`; `audit.se_audit`
  liefert `suppressed=true` samt `suppression_reason` am betroffenen Finding und
  `counts.suppressed`; `audit.se_audit` bleibt AUTHOR-Tier (nicht ADMIN, M1).
- **Autoritäts-Klausel (C2, Post-Implementierungs-Review 2026-09-22):** `audit.waivers` bleibt
  Tier **read**, erzwingt aber im Handler denselben Approval-Authority-Choke-Point wie REST-E12 —
  ein Editor/Viewer erhält **`PERMISSION_DENIED`**, nicht die Liste. Tier = read, effektive
  Autorität = Approval-Authority (§3.5).
- **Test:** `test_audit_tool_group.py::test_waivers_is_read_only`,
  `::test_waivers_requires_approval_authority` (Editor/Viewer ⇒ `PERMISSION_DENIED`),
  `::test_se_audit_marks_suppressed_findings` und `::test_audit_namespace_is_not_bulk_reclassified`.

### AC-569-08 — Gate: unterdrückt ≠ Blocker, nicht unterdrückt blockiert weiter

- **Given** drei Blocker-Findings, eines per aktivem Waiver unterdrückt.
- **When** `create_baseline` ohne `override_reason` aufgerufen wird.
- **Then** schlägt der Build fehl (`BaselineGateBlockedError`) und benennt nur die **zwei**
  verbleibenden; sind **alle** unterdrückt, wird die Baseline erzeugt.
- **Test:** `backend/application/tests/test_baseline_gate_waivers_821.py:143-170`
  (`test_unwaived_findings_still_block`) bleibt grün; neuer
  `test_baseline_gate_waivers_569.py::test_suppressed_blocker_does_not_block_but_is_recorded`.

### AC-569-09 — §490: Unterdrückung in Baseline-Metadaten nachvollziehbar (nicht versteckt) *(revidiert, M3/M4)*

- **Given** eine per Waiver erzeugte Baseline, wobei ein Waiver in diesem Lauf **wiederverwendet**
  wird (nicht neu erzeugt).
- **When** `baseline.get` geladen wird.
- **Then** enthält die immutable `description` die `[SE-Auditor waiver]`-Annotation mit Anzahl,
  sortierten `rule_ids` und den **`matched_waiver_ids`** (alle gematchten Zeilen — der
  Wiederverwendungsfall liefert **nicht** `[]`); die Waiver-Zeile(n) existieren; je **neu**
  erzeugtem Waiver existiert ein `baseline.waiver_create`-AuditEntry.
- **M3-Korrektur (Post-Implementierungs-Review, 2026-09-22):** die frühere Formulierung „der
  `baseline.create`-AuditEntry **trägt** diese Werte in `details`" war an eine widerlegte Prämisse
  gebunden und ist **nicht** literal erfüllbar (`details` wird nie persistiert:
  `audit/services.py:159`, `audit/writer.py:190-202`, keine Spalte in `audit/models.py:246-306`).
  Präzise gilt: der Service **konstruiert** beim `baseline.create` einen `details`-Payload mit
  `suppressed_blocker_count`, `suppressed_finding_keys`, `waiver_ids` und additiv
  `matched_waiver_ids`; dieser Payload wird **an der `_audit`-Aufrufgrenze** asserted (der Test
  fängt den `_audit`-Aufruf ab). **Persistiert wird er nicht.**
- **Durable Trail (der eigentliche Nachweis):** die `AuditEntry`-Zeile mit `op="baseline.create"`,
  `entity_type`, `entity_id`, `actor`, `change_reason` **plus** die append-only
  `BaselineGateWaiver`-Zeile (`finding_key`, `rule_id`, `artifact_ids`, `scope`, `reason`,
  `granted_by`, `expires_at`).
- **Recovery-Pfad (explizit für Reviewer):** „wer / was / warum / bis wann" ist über den Join
  `AuditEntry.entity_id → BaselineGateWaiver.id` rekonstruierbar. **Eine Asymmetrie:** auf dem
  **MCP**-Pfad ist `change_reason` **`None`** (`write_mcp_audit` setzt keinen `change_reason`,
  `mcp_server/tools/base.py:269-306`), d. h. die Begründung ist dort **nur** über den Join auf
  `BaselineGateWaiver.reason` erreichbar; auf dem REST-Pfad steht sie zusätzlich in
  `AuditEntry.change_reason` (`audit_service.py:623`). Auf **beiden** Pfaden bleibt die Begründung
  nachweisbar — nur nicht über `change_reason` allein.
- **Deferred:** strukturierte `details`-Queryability (JSON-Spalte/Filter) ist auf den
  AuditLog-Writer-Umbau verschoben und **Non-Goal** (§7).
- **Test:** Erweiterung von `backend/rest_api/tests/test_baseline_gate_waivers_821_rest.py:132-158`
  um `test_baseline_metadata_names_matched_waiver_ids_on_reuse` (zweiter Build, der die Zeile
  wiederverwendet) sowie `test_baseline_create_audit_details_carry_the_suppression_trail`
  (interceptet den `_audit`-Aufruf und prüft den **konstruierten** `details`-Payload an der
  Aufrufgrenze; prüft zusätzlich den durabilen `AuditEntry`/`BaselineGateWaiver`-Join).

### AC-569-10 — Ablauf-Semantik

- **Given** ein Waiver mit `expires_at` in der Vergangenheit.
- **When** `run_audit` läuft und ein Baseline-Build versucht wird.
- **Then** ist das Finding **nicht** `suppressed`, zählt wieder als Blocker, der Build blockiert
  (sofern kein Override), und `GET …/audit/waivers/?state=expired` zeigt den Waiver mit
  `state="expired"`.
- **Test:** `test_baseline_gate_waivers_569.py::test_expired_waiver_re_blocks` und
  `test_audit_waivers_569.py::test_expired_suppression_is_not_applied`.

### AC-569-11 — Kein Weg an Begründung/Audit-Spur vorbei (Negativ) *(revidiert, M-A)*

- **Given** ein Blocker-Finding ohne Waiver.
- **When** ein Waiver mit leerer/fehlender Begründung, unbekanntem Finding, leerem Autor
  (`ctx.user_id` fehlt) oder ohne Admin/Approver-Rolle versucht wird.
- **Then** entsteht keine Waiver-Zeile, kein `baseline.waiver_create`-Eintrag und keine Baseline;
  die Antwort ist **`400 WAIVER_REASON_REJECTED`**, **`400 WAIVER_FINDING_NOT_BLOCKING`**,
  **`403 PERMISSION_DENIED`** oder **`400 VALIDATION_ERROR`** (nie `200`/`201`, **nie `422`**).
- **Test:** `test_audit_waivers_569_rest.py::test_no_suppression_without_reason_authority_or_finding`.

### AC-569-12 — Autorität: Admin/Approver + ADMIN-Tier-Key

- **Given** ein Editor-User bzw. ein AUTHOR-Tier-API-Key.
- **When** ein Waiver erzeugt wird.
- **Then** `403 PERMISSION_DENIED`; MCP-Pendant liefert `PERMISSION_DENIED`.
- **Test:** `test_audit_waivers_569_rest.py::test_editor_waiver_is_rejected_with_403`,
  `test_granular_api_key_scope_865.py`-Erweiterung für den neuen Endpunkt.

### AC-569-13 — Report-Markierung und Filter *(revidiert, M5/m7)*

- **Given** ein aktiver Waiver auf einem Blocker-Finding.
- **When** `GET …/audit/` (Default) bzw. `?include_suppressed=false` aufgerufen wird.
- **Then** Default (`include_suppressed=true`): Finding ist in `findings` mit `suppressed=true`,
  `suppressed_until`, `suppression_reason`, `suppression_id`; `counts.blockers` zählt es
  **weiterhin** (deskriptiv, M5), `counts.suppressed` und `counts.suppressed_blockers` zählen es
  zusätzlich. `include_suppressed=false`: Finding fehlt in `findings`; `counts.*` beschreiben die
  gefilterte Liste, `total_*_available` den ungefilterten Lauf; `suppressed_filtered` ist gesetzt.
  **Invarianten:** (i) `counts.blockers + counts.warnings == counts.total` gilt in **beiden**
  Modi unbedingt (Severity ist binär, alle drei Zähler stammen aus derselben `findings`-Liste);
  (ii) bei aktivem Filter/Cap gilt `counts.total != total_findings_available` (m7 — Fenster vs.
  Gesamtlauf). Eine Ungleichung **innerhalb** der `counts`-Summe ist arithmetisch unerreichbar und
  deshalb **nicht** Teil des Vertrags (R3-01).
- **Test:** `backend/rest_api/tests/test_audit_waivers_569_rest.py::test_report_marks_and_filters_suppressed`
  und `::test_counts_stay_descriptive_and_totals_stay_absolute_when_filtered`.

### AC-569-14 — UI: dritte Aktion + Filter

- **Given** das SE-Auditor-Dashboard mit einem Blocker-Finding.
- **When** der Nutzer „Unterdrücken" wählt, eine gültige Begründung eingibt und bestätigt.
- **Then** erscheint `audit-suppressed-badge-<index>` mit Begründung, `audit-count-suppressed`
  zählt hoch, und der Checkbox `audit-show-suppressed` (Default an) blendet unterdrückte Findings
  aus/ein. DE-/EN-i18n-Keys sind vollständig (Paritätstest grün).
- **Test:** `frontend/src/components/Audit/audit-dashboard.test.tsx` — neue Fälle
  `suppresses a finding via the waive dialog` und `hides suppressed findings when the filter is off`.

### AC-569-15 — Unbekanntes (oder nicht-blockierendes) Finding wird abgewiesen *(revidiert, M-A)*

- **Given** kein berichtetes `CONS-P11`-Finding bzw. ein nur als WARNING berichtetes Finding.
- **When** ein Waiver dafür gesendet wird.
- **Then** **`400` mit `error.code == "WAIVER_FINDING_NOT_BLOCKING"`** (nicht 422), keine Zeile
  (O2: WARNING-Findings sind nicht unterdrückbar).
- **Test:** `test_audit_waivers_569_rest.py::test_waiver_for_an_unreported_finding_is_rejected_with_400_and_dedicated_code`,
  `::test_waiver_for_a_warning_finding_is_rejected_with_400_and_dedicated_code`.

### AC-569-16 — Scope-Präzision gegen die **produktionsreale** GH-821-Zeilenform *(revidiert, M7)*

- **Given** eine real per Gate-Build persistierte GH-821-Zeile für eine scope-agnostische Regel
  (`TRACE-P1`, `art-1`) in der Form `scope="project"`, `scope_artifact_id=""`, **und** ein
  `document`-scoped Finding derselben Regel/Artefakte (`scope_artifact_id="<doc>"`) sowie ein
  für dieses Dokument gewährter, ebenfalls persistierter Waiver.
- **When** `suppression_applies` jeweils geprüft wird.
- **Then** (i) matcht die `project`-gestempelte Bestandszeile das scope-agnostische Finding
  weiterhin (R2b, GH-821-Bestandsschutz, `scope != ""`); (ii) deckt der dokument-gebundene Waiver
  **nur** das passende Document-Finding ab (R2c) und **nicht** das scope-agnostische (R2b greift
  wegen `scope_artifact_id != ""` nicht); (iii) ein `scope="project"`-Record matcht **kein**
  `scope="document"`-Finding.
- **Test:** `backend/baseline/tests/test_waivers_569.py::test_suppression_applies_is_gh821_backward_compatible`
  (erzeugt die Zeile über den Gate-Build, nicht als Literal).

**Gesamt: 34 ACs** (AC-569-COMPAT + AC-569-01 … AC-569-16 + AC-569-17 … AC-569-27 +
AC-569-28 … AC-569-33).

### AC-569-17 — Document-scoped Findings sind unterdrückbar *(neu, C1; Status revidiert, M-A)*

- **Given** ein `document`-scoped BLOCKER-Finding (`TRACE-P7`) im Dokument `<doc>`, das nur mit
  `scope="document"` + `scope_artifact_id` berichtet wird (Engine-Default ist `project`).
- **When** `POST …/audit/waivers/` bzw. `audit.waive_finding` mit `scope="document"`,
  `scope_artifact_id="<doc>"` gesendet wird.
- **Then** wird der Waiver angelegt (201), die persistierte Zeile trägt `scope="document"`,
  `scope_artifact_id="<doc>"`; ohne `scope` bzw. ohne `scope_artifact_id` (bei document) liefert
  derselbe Aufruf **`400 VALIDATION_ERROR`** (kein 422); ein scope-agnostischer Aufruf erzeugt
  **keine** document-scoped Zeile.
- **Test:** `test_audit_waivers_569_rest.py::test_document_scoped_finding_is_waivable`,
  `backend/mcp_server/tests/test_audit_tool_group.py::test_waive_document_scope_requires_artifact_id`.

### AC-569-18 — `audit.se_audit` behält seinen Tier (M1)

- **Given** die Registry nach #569.
- **When** `_required_scope_operation("audit.se_audit")` / `("audit.query")` / `("audit.ai_review")`
  bzw. `("audit.waive_finding")` ausgewertet wird.
- **Then** ist `audit.se_audit` `Operation.WRITE` (AUTHOR-Tier, unverändert — **nicht**
  WORKSPACE_CONFIG/ADMIN), `audit.query`/`audit.ai_review` sind `Operation.READ`,
  `audit.waive_finding` ist `Operation.WORKSPACE_CONFIG`; `"audit" not in _GOVERNANCE_TOOL_NAMESPACES`.
- **Test:** `test_audit_tool_group.py::test_audit_namespace_is_not_bulk_reclassified`.

### AC-569-19 — Wiederverwendete Waiver liefern `matched_waiver_ids` (M4)

- **Given** ein bereits persistierter aktiver Waiver.
- **When** ein Gate-Build ihn wiederverwendet (`suppressed > 0`, `waiver_ids == []`).
- **Then** ist `GateWaiverOutcome.matched_waiver_ids` nicht leer und enthält die persistierte
  Zeilen-ID; `waiver_ids` bleibt `[]` (Bestandscontract); die Description nennt die ID.
- **Test:** `test_baseline_gate_waivers_569.py::test_reused_waiver_is_reported_in_matched_ids`.

### AC-569-20 — Autoritäts-Choke-Point ist eine SSOT (M2)

- **Given** `baseline.waivers.assert_gate_waiver_authority`.
- **When** ein Editor (keine Approval-Rolle) bzw. ein AUTHOR-Tier-Key ruft
  `AuditService.suppress_finding` **und** `BaselineFacade`-Gate-Waiver auf.
- **Then** liefern beide Pfade identisch `PERMISSION_DENIED`; `BaselineFacade._assert_override_permission`
  delegiert und bleibt direkt aufrufbar (`test_granular_api_key_scope_865.py:207-226` bleibt grün);
  es existiert kein zweiter Copy-Paste-Check.
- **Test:** `backend/application/tests/test_audit_waivers_569.py::test_authority_choke_point_is_shared`
  und `test_granular_api_key_scope_865.py::test_audit_waive_endpoint_rejects_author_tier_key`.

### AC-569-21 — Abgelaufener Bestandswaiver ⇒ `409 SUPPRESSION_EXPIRED` (m1)

- **Given** genau eine Waiver-Zeile für den `finding_key` mit `expires_at` in der Vergangenheit.
- **When** derselbe Waiver erneut beantragt wird.
- **Then** `409 SUPPRESSION_EXPIRED`, keine Zeilenänderung, kein neuer AuditEntry; das Finding
  bleibt blockierend. Ein **aktiver** Bestandswaiver liefert weiterhin `200` mit `created=false`.
- **Test:** `test_audit_waivers_569_rest.py::test_expired_existing_waiver_returns_409`.

### AC-569-22 — Query-Parsing `include_suppressed` / `state` (m2)

- **Given** `?include_suppressed` mit `true`, `false`, `TRUE`, `1`, `yes`, `banana`.
- **When** `GET …/audit/` aufgerufen wird.
- **Then** `true`/`false` (case-insensitiv) bzw. abwesend (Default `true`) → 200; `1`/`yes`/`banana`
  → `400 VALIDATION_ERROR`; analog `?state=` nur `active|expired|all`.
- **Test:** `test_audit_waivers_569_rest.py::test_include_suppressed_query_parsing`.

### AC-569-23 — UI-Ratchet bleibt grün (m3)

- **Given** Dialog, Badge und Filter aus §3.6.
- **When** `ui-ratchet.test.ts` läuft.
- **Then** ist `STYLE_BRACE_BASELINE` unverändert (`frontend/src/test/ui-ratchet.test.ts:1035/1047`);
  neue Styles liegen in CSS-Modulen/gehoisteten Konstanten. Wird die Zahl doch berührt, ist sie im
  selben Commit bewusst nachgeführt (nie erhöht).
- **Test:** `frontend/src/test/ui-ratchet.test.ts` (grün).

### AC-569-24 — `load_waived_finding_keys`-Kompatvertrag (m5; Prämisse korrigiert, N4)

- **Given** aktive und abgelaufene Waiver.
- **When** `load_waived_finding_keys(ws, tenant)` mit der positionskompatiblen 2-Argument-Signatur
  aufgerufen wird.
- **Then** gilt
  `load_waived_finding_keys(ws, tenant) == {r.finding_key for r in load_suppressions(ws, tenant, include_expired=False)}`
  und abgelaufene Keys fehlen; die 2-Argument-Signatur bleibt als **öffentlicher Bestandsvertrag**
  gültig (nicht wegen `_apply_waivers` — dieser Aufruf entfällt mit M7, siehe §3.1).
- **Test:** `test_waivers_569.py::test_load_waived_finding_keys_matches_load_suppressions`.

### AC-569-25 — MCP-Manifest ist regeneriert (M6)

- **Given** die neuen Tools `audit.waive_finding`/`audit.waivers`.
- **When** die Manifest-Ratchets laufen.
- **Then** ist `docs/agent-templates/tool-manifest.json` regeneriert (`tool_count` + InputSchema)
  und `test_tool_manifest_drift.py` sowie
  `docs/agent-templates/test_role_tools_exist_in_manifest.py` sind grün.
- **Test:** `backend/mcp_server/tests/test_tool_manifest_drift.py`.

### AC-569-26 — Kein Scope-Überlauf durch dokument-gebundene Waiver (m4)

- **Given** ein für `scope="document"`/`<doc>` gewährter Waiver (`TRACE-P1`, `art-1`) und ein
  scope-agnostisches Finding derselben Regel/Artefakte.
- **When** `suppression_applies` geprüft wird.
- **Then** matcht der dokument-gebundene Waiver das scope-agnostische Finding **nicht** (R2b,
  `scope_artifact_id != ""`), nur das Document-Finding (R2c).
- **Test:** `test_waivers_569.py::test_document_waiver_does_not_bleed_into_scope_agnostic_finding`.

### AC-569-27 — Threat-Model & Negativ-Invariante (m6/m7)

- **Given** das Governance-Feature #569.
- **When** die 4 Threat-Model-Fragen (§8) und die `include_suppressed=false`-Invariante geprüft
  werden.
- **Then** ist für (1)–(4) je eine Antwort dokumentiert; und in `include_suppressed=false` gilt
  `counts.total == len(findings)` sowie
  `total_findings_available == len(findings) + suppressed_filtered` (bei ungecapptem Lauf).
- **Test:** `test_audit_waivers_569_rest.py::test_filtered_report_invariant`.

### AC-569-28 — 422 ist reserviert, neue Endpunkte nutzen es nie *(neu, M-A)*

- **Given** die neuen Waiver-Endpunkte und der erweiterte Report-Endpunkt.
- **When** jeder Fehlerfall aus §3.4.1 (E3–E9, E11–E13, E15–E16, E19–E20) ausgelöst wird.
- **Then** ist **kein** Status `422`; die beobachteten Status sind exakt
  `400`/`403`/`404`/`409`/`500` mit den Codes aus §3.4.1; der 422-Fall bleibt in diesem
  Audit-Modul ausschließlich `POST …/audit/remediate/` (E17) vorbehalten (R3-06).
- **Test:** `backend/rest_api/tests/test_audit_waivers_569_error_contract.py::test_no_new_endpoint_emits_422`
  (parametrisiert über die Fehlerfälle; assert `response.status_code != 422` **und** exakter
  Erwartungswert je Fall) sowie
  `::test_remediate_keeps_422_for_the_modify_flip` (Regression auf den reservierten Wirt).

### AC-569-29 — Fehler-Typ-Vertrag über die Layer-Grenze *(neu, M-B/N6)*

- **Given** die neuen Typen `baseline.exceptions.GovernanceReasonError`,
  `GovernanceAuthorityError` sowie `application.base.WaiverReasonPolicyViolation`,
  `WaiverFindingNotBlockingError`, `SuppressionExpiredError`.
- **When** jede Policy-/Autoritäts-/Finding-Verletzung über REST **und** MCP ausgelöst wird.
- **Then** (i) `validate_waiver_reason` wirft `GovernanceReasonError` (nicht `ValidationError`);
  (ii) die module-level Funktion `_validate_gate_reason` in `application.baseline_facade`
  (`baseline_facade.py:1117`, kein `BaselineFacade`-Methoden-Attribut) liefert weiterhin exakt
  `application.base.ValidationError` (Bestandstest `test_baseline_gate_waivers_821.py:388-390`
  bleibt grün); (iii) REST liefert die Status/Codes aus §3.4.2; (iv) die drei L2-Typen sind in
  `_EXC_TO_HTTP`/`_EXC_TO_CODE` registriert (`type(exc)`-Lookup findet sie);
  (v) `GovernanceReasonError`/`GovernanceAuthorityError` sind **nicht** in diesen Maps.
- **Test:** `backend/application/tests/test_audit_waivers_569.py::test_reason_policy_raises_governance_reason_error`,
  `::test_gate_path_still_raises_plain_validation_error`,
  `backend/rest_api/tests/test_audit_waivers_569_error_contract.py::test_new_error_types_are_registered_in_exc_maps`,
  `::test_governance_domain_errors_are_not_registered`.

### AC-569-30 — Autor-Erfassung `granted_by` *(neu, M-B)*

- **Given** ein autorisierter Aufrufer mit `ctx.user_id` bzw. ein Kontext ohne `user_id` (`None`
  oder fehlendes Attribut).
- **When** ein Waiver erzeugt wird.
- **Then** ist `granted_by` gleich `str(getattr(ctx, "user_id", "") or "").strip()` — dieselbe
  None-sichere Service-Formel wie §3.3 Schritt 2 — und stammt **nicht** aus dem Body; ein
  Body-Feld `granted_by` ⇒ `400 VALIDATION_ERROR`; ein leerer **oder fehlender** `ctx.user_id`
  (`None` ergibt `""`, **nicht** `"None"`) ⇒ `403 PERMISSION_DENIED` und **keine** Zeile.
- **Test:** `test_audit_waivers_569_rest.py::test_granted_by_comes_from_the_auth_context_only`,
  `backend/application/tests/test_audit_waivers_569.py::test_blank_author_is_rejected`.

### AC-569-31 — Ablauf: Entscheidungszeit, kein No-op-Waiver *(neu, D2/D3)*

- **Given** (a) ein Waiver mit `expires_at` in der Zukunft und (b) ein Request mit `expires_at`
  in der Vergangenheit bzw. einem naiven Zeitstempel.
- **When** (a) die Uhr über `expires_at` hinaus vorgestellt wird (`now`-Injektion) und
  `load_suppressions`/`suppression_applies`/`run_audit` erneut ausgewertet werden; (b) der Request
  gesendet wird.
- **Then** (a) unterdrückt der Waiver **ohne** Job/State-Änderung nicht mehr, `state` ist
  `"expired"`, das Finding blockiert wieder; (b) `400 VALIDATION_ERROR`, keine Zeile.
- **Test:** `test_waivers_569.py::test_expiry_is_evaluated_at_decision_time_with_injected_now`,
  `test_audit_waivers_569_rest.py::test_past_or_naive_expires_at_is_rejected`.

### AC-569-32 — MCP- und i18n-Fehler-Code-Registry *(neu, M-B)*

- **Given** die drei neuen Codes.
- **When** `ERROR_CODES`/`ERROR_CODE_MAP` bzw. `_ERROR_MESSAGES` geprüft werden.
- **Then** existieren `WAIVER_REASON_REJECTED: -32008`, `WAIVER_FINDING_NOT_BLOCKING: -32009`,
  `SUPPRESSION_EXPIRED: -32010`; `_ERROR_MESSAGES` hat für alle drei je einen DE- **und**
  EN-Eintrag.
- **Test:** `backend/mcp_server/tests/test_audit_tool_group.py::test_new_waiver_error_codes_are_registered`,
  `backend/rest_api/tests/test_audit_waivers_569_error_contract.py::test_new_error_codes_have_de_and_en_messages`.

### AC-569-33 — Policy-Konstanten: Layer-1-Heimat + Re-Export *(neu, M2-Rest/D4)*

- **Given** die verlagerte Begründungs-Policy.
- **When** `MIN_OVERRIDE_REASON_LENGTH` aus `application.baseline_facade` importiert wird und die
  Policy-Grenzwerte geprüft werden.
- **Then** ist der Import unverändert gültig (Re-Export), die Konstanten sind in
  `baseline/waivers.py` definiert, und die abgelehnten/akzeptierten Beispielbegründungen aus
  AC-569-02 verhalten sich unverändert.
- **Test:** `test_baseline_gate_waivers_821.py` (Bestand, bleibt grün) plus
  `test_waivers_569.py::test_reason_policy_constants_are_reexported_from_the_facade`.

---

## 7. Non-Goals

- Kein Fix des „Modify"-Buttons — #451 ist erledigt (`audit-dashboard.tsx:790-809`).
- Kein Re-Audit-Scheduling, keine Celery-Jobs, keine Ablauf-Benachrichtigungen.
- Kein UI-Redesign des Dashboards über die dritte Aktion, den Filter, Badge und Dialog hinaus.
- Keine Persistenz von Findings (Identität bleibt deriviert, `types.py:39-61`).
- Keine Änderung der 11 built-in Trace-Link-Typen, keine neuen Regel-IDs.
- Keine Änderung des `override_reason`-Verhaltens oder der `BaselineGateWaiver`-Unique-/Check-
  Constraints.
- **Kein AuditLog-Writer-Umbau** — insbesondere wird keine `details`-Spalte ergänzt. **Korrigiert
  (Post-Implementierungs-Review, 2026-09-22):** entgegen rev2/rev3 werden `details` **nicht**
  persistiert (`audit/services.py:159`, `audit/writer.py:190-202`, keine Spalte in
  `audit/models.py:246-306`). Der `details`-Payload (`matched_waiver_ids` etc.) ist damit nur an
  der `_audit`-Aufrufgrenze prüfbar; die strukturierte `details`-Queryability ist ausdrücklich auf
  einen späteren Writer-Umbau verschoben und **nicht** Teil von #569.
- Keine Umdeutung von `counts.blockers`/`counts.warnings`/`total_blockers_available`/
  `total_warnings_available` — sie bleiben deskriptiv (M5); Unterdrückung wird rein additiv gezählt.
- Keine Scope-Erweiterung über die C1-Mindestmenge hinaus: kein Multi-Scope-Report, kein
  Scope-Picker-Umbau, keine scope-spezifische Regel-Logik (die Non-Goals bleiben bindend).
- Keine zweite Suppression-Tabelle, keine Bulk-Waive-all-Aktion.
- Kein Revoke-/Unterdrückung-aufheben-Pfad (siehe offene Frage O1); auch kein stilles
  Re-Grant eines abgelaufenen Waivers (m1 → 409).
- **Kein scope-blinder Suppression-Helfer** (`suppressed_finding_keys` gestrichen, N5) — der
  einzige Matcher bleibt `suppression_applies` (§3.1 R1–R3, §8 Risiko 2).
- **Keine Wiederverwendung von HTTP 422** auf den neuen Endpunkten (D1); 422 bleibt in diesem
  Audit-Modul ausschließlich `POST …/audit/remediate/` (`architecture_decompose_views.py:156`
  außerhalb bleibt unberührt, R3-06).
- **Kein persistiertes Ablauf-`state`** und kein Celery-/Scheduling-Job für Waiver-Ablauf (D3);
  `expires_at` wird zur Entscheidungszeit ausgewertet.
- **Keine Änderung des bestehenden `waived_findings`-Fehler-Codes:** jener Pfad antwortet weiterhin
  `400 VALIDATION_ERROR` (die module-level Funktion `_validate_gate_reason` in
  `application.baseline_facade` re-raised `ValidationError`), **nicht** `WAIVER_REASON_REJECTED`.

---

## 8. Risiken & offene Fragen

### Risiken

1. **Stiller Formatwechsel des `finding_key`** — der Realweg, der alle bestehenden Waiver
   verwaisen lässt. Gegenmaßnahme: AC-569-COMPAT als harter Regressionstest inkl. Mutationsprobe.
2. **Doppelte Wahrheit über „Anwendbarkeit"** — Gate und Report dürfen nicht zwei verschiedene
   Matching-Regeln entwickeln. Gegenmaßnahme: `suppression_applies` als einziger Matcher; Gate und
   `run_audit` rufen ihn auf.
3. **Description-Annotation wird zu lang** bei vielen Waivern. Gegenmaßnahme: Kappung analog
   `_MAX_LISTED_FINDINGS` (`baseline_facade.py:1099`) plus Zähler-Hinweis.
4. **Zähler-Semantik-Regression** — **entschärft (M5):** `counts.blockers` etc. werden **nicht**
   umgedeutet; Unterdrückung wird rein additiv gezählt (`counts.suppressed`/`suppressed_blockers`,
   `total_suppressed_*`). Gegenmaßnahme: AC-569-13/AC-569-27; bestehende BUG-15-Tests
   (`total_*_available`) bleiben unverändert grün.
5. **MCP-Governance-Tier-Drift** — **entschärft (M1):** `"audit"` wird **nicht** in
   `_GOVERNANCE_TOOL_NAMESPACES` aufgenommen; stattdessen exakte Tool-Level-Menge
   `_GOVERNANCE_TOOL_NAMES`. `audit.se_audit` bleibt AUTHOR-Tier. Gegenmaßnahme: AC-569-18.
6. **Matching-Regel zu breit/nach zu eng** — R2b verhindert den Scope-Überlauf (m4), könnte aber
   bei künftigen Scope-Semantiken zu eng werden. Gegenmaßnahme: AC-569-16/26; `suppression_applies`
   bleibt der einzige Matcher.
7. **Abgelaufener Waiver blockiert Re-Grant** — gewollt (m1, `409`), aber ohne Revoke (O1) ist ein
   abgelaufener Waiver bis zur Produktentscheidung nicht erneuerbar. Eskalation siehe O1.
8. **Status-Code-Regression auf den Bestandsendpunkten** — **entschärft (M-A/D1):** 422 wird
   nicht angefasst; der neue Vertrag fügt 400/409 nur auf den **neuen** Pfaden hinzu und lässt
   `remediate` unverändert. Gegenmaßnahme: AC-569-28 (inkl. Regression auf den 422-Wirt) und der
   Bestandstest `audit-dashboard.test.tsx:485-489`.
9. **Fehlertyp-Drift zwischen REST und MCP** — dieselbe Verletzung könnte auf zwei Transporten
   unterschiedlich klassifiziert werden (z. B. Reason-Policy einmal `VALIDATION_ERROR`, einmal
   `WAIVER_REASON_REJECTED`). Gegenmaßnahme: eine gemeinsame L2-Fehlertyp-Quelle (§3.4.2), je ein
   AC pro Transport (AC-569-29/32) und die idempotente Code-Registry (`ERROR_CODE_MAP`).
10. **Zwei Zeilenformen für scope-agnostische Findings** (Gate `"project"`, `AuditService` `""`)
    — bewusst (§1), aber bei künftigen Scope-Semantiken eine Fehlerquelle. Gegenmaßnahme:
    AC-569-COMPAT(b)/(c) pinnen beide Formen; `suppression_applies` bleibt der einzige Matcher.

### Threat Model — die 4 Fragen (m6)

Für ein Governance-Feature (intern, aber autoritativ) in Kurzform:

1. **Was wird gebaut?** Eine Unterdrückung (Waiver) für SE-Auditor-Blocker-Findings mit
   Pflicht-Begründung, Autoritätsprüfung (Admin/Approver **und** ADMIN-Tier-Key), Ablauf und
   dauerhafter Audit-Spur; sie nimmt dem Finding die Gate-Blocker-Wirkung, nicht seine Sichtbarkeit.
2. **Was kann schiefgehen?** (a) Autoritätsprüfung wird dupliziert und verliert den
   ADMIN-Tier-Check → AUTHOR-Key umgeht das Gate; (b) ein Waiver wirkt breiter als dokumentiert
   (Scope-Überlauf) und unterdrückt ein nicht gemeintes Finding; (c) eine Unterdrückung wird
   versteckt (Default filtert); (d) ein abgelaufener Waiver wirkt weiter.
3. **Was wird dagegen getan?** (a) ein SSOT-Choke-Point
   (`assert_gate_waiver_authority`, AC-569-20); (b) präzise `suppression_applies`-Regeln +
   AC-569-16/26; (c) `include_suppressed` Default `true` und Report-Markierung (AC-569-13);
   (d) Ablauf als Re-Evaluierungs-Trigger (E3) + AC-569-10.
4. **Konsequenzen?** Missbrauch wäre eine fail-open-Governance-Lücke mit falschen, aber
   auditierbaren Baselines; deshalb bleibt der GH-400-„nicht auswertbar"-Pfad unüberbrückbar und
   jede Unterdrückung ist auf Description, Waiver-Zeile und AuditLog dreifach belegt.

### Entscheidungen aus dem Review (vormals offene Fragen)

In Revision 2 durch den Review aus Code/Issue beantwortet und als **getroffene Entscheidungen**
übernommen:

- **O2 (WARNING unterdrückbar?)** — **Nein, blocker-only** (§3.3 Schritt 4, E5, AC-569-15).
  Der bestehende Pfad ist blocker-only (`blocking_findings`, `audit_service.py:293-296`).
- **O3 (`include_suppressed`-Default)** — **`true`** (Nachvollziehbarkeit statt Verstecken,
  konsistent zu DoD 6; AC-569-13/22).
- **O4 (Ablauf-Pflicht)** — **optional**, `NULL` = unbefristet (Bundle-Plan
  `2026-09-21-open-issues-bundle.md:182`); E3/AC-569-10.
- **O5 (Baseline-Metadaten-Träger)** — **Description-Annotation + `baseline.create`-`details`-
  Payload (an der `_audit`-Aufrufgrenze geprüft, **nicht** persistiert) + `BaselineGateWaiver`-
  Zeile + je Waiver ein Audit-Eintrag genügen**; kein Join-Modell. Die rev2/rev3-Begründung
  „`details` sind persistiert" ist zurückgezogen (Post-Implementierungs-Review 2026-09-22,
  §1/M3-Korrektur, E2, AC-569-09/AC-569-19).
- **O6 (Terminologie/i18n)** — Audit-/Suppression-Begriffe sind **nicht** Teil des
  Terminology-Profils (`presets/terminology.py:49-74`); i18n-Keys bleiben profilunabhängig neutral
  (`audit.suppress…`, §3.6).

### Offene Frage (bleibt offen — Produktentscheidung beim Auftraggeber)

- **O1 — Revoke/„Unterdrückung aufheben":** Das #569-DoD nennt keinen Widerruf. Ohne ihn ist eine
  falsch gewährte Unterdrückung permanent, und ein **abgelaufener** Waiver ist nicht erneuerbar
  (m1 liefert `409`). In Scope von #569 oder Follow-up? Falls ja: neuer `AuditEntry`-OP
  (`baseline.waiver_revoke`) + Reason-Pflicht + Audit-Spur; für Re-Grant ist eine explizite
  Governance-Entscheidung (Revoke + Neuanlage vs. kontrollierte Verlängerung derselben Zeile)
  nötig. **Bis dahin bleibt der Revoke-Pfad Non-Goal.**

---

## 9. Rollout / Migrationsbedarf

**Schema-Änderung: ja — genau eine, additiv, nullable.**

| App | Migration | Inhalt | Free-Prefix |
|---|---|---|---|
| `baseline` | `0009_baselinegatewaiver_expires_at` | `AddField` `expires_at = DateTimeField(null=True, blank=True, default=None)` auf `bl_baseline_gate_waiver` | höchste vorhandene ist `0008_baseline_gate_waiver_rls.py` → `0009` frei |

- Keine Datenmigration, kein Backfill: Bestandszeilen haben `expires_at = NULL` = unbefristet und
  behalten damit exakt ihr GH-821-Verhalten.
- **Keine** RLS-Folgemigration nötig: die Tabelle `bl_baseline_gate_waiver` ist bereits durch
  `0008_baseline_gate_waiver_rls.py` abgedeckt (neues Feld ändert die Policy nicht).
- **Kein** neuer `AuditEntry`-OP-Wert: `baseline.waiver_create` wird wiederverwendet
  (`backend/audit/models.py:165`). Nur bei Umsetzung von O1 (Revoke) käme ein `audit`-App-Migration
  für einen neuen OP hinzu.
- **Kein** neues Modell, **keine** neue Tabelle (Entscheidung in 3.2).
- **M6 — MCP-Tool-Manifest regenerieren:** nach Hinzufügen der neuen Tools
  `python backend/manage.py export_tool_manifest` ausführen und
  `docs/agent-templates/tool-manifest.json` (tool_count + InputSchemas) committen; die
  Rollen-Tool-Manifest-Prüfung mitlaufen lassen. Sonst schlagen
  `backend/mcp_server/tests/test_tool_manifest_drift.py:84-156` und
  `docs/agent-templates/test_role_tools_exist_in_manifest.py` fehl.
- **Keine** zusätzliche Migration für die M2-Verschiebung: die neuen
  `baseline.exceptions.GovernanceAuthorityError`/`GovernanceReasonError` sind reiner Code, kein
  Schema.
- **Reine Code-Änderungen ohne Migration (rev3, M-B):** die drei neuen L2-Fehlertypen in
  `application/base.py`, die Einträge in `rest_api/views.py::_EXC_TO_HTTP`/`_EXC_TO_CODE`, die
  DE/EN-Einträge in `rest_api/serializers.py::_ERROR_MESSAGES` sowie `ERROR_CODES`/
  `ERROR_CODE_MAP` in `mcp_server/protocol_handler.py`. Diese Dateien haben keinen
  Manifest-/Ratchet-Bezug außer dem MCP-Manifest (siehe nächster Punkt) — die
  `ERROR_CODES`-Erweiterung selbst ist nicht manifest-geprüft, muss aber mit den neuen
  Tool-Schemas konsistent bleiben.
- Frontend/i18n: nur additive Keys; DE/EN-Parität und `ui-ratchet` (`STYLE_BRACE_BASELINE`)
  müssen grün bleiben (m3).
- Rollback: `expires_at` ist nullable und unbenutzt ohne den Code → Migration ist reversibel ohne
  Datenverlust.
- **PR-Pflicht (bindende Auftrags-Constraint, R3-10):** der PR trägt `Closes #569` (Titel/Body
  bzw. Commit-Trailer), damit das Issue beim Merge automatisch geschlossen wird — gemäß
  Bundle-Plan `2026-09-21-open-issues-bundle.md:49,193`. Zielbranch `feat/se-audit-waivers`
  (von `origin/main` `564e62ab`); der Base-`feat/se-validation-completeness` (`da12acf4`) dient nur
  als Arbeitskontext.

---

## 10. Referenzen

- Issue #569 (SE-Auditor: Findings unterdrücken — False-Positive/Waiver mit Begründung)
- Cluster 2: `docs/superpowers/plans/2026-09-21-open-issues-bundle.md:142-194`
- GH-821: `backend/baseline/waivers.py`, `backend/baseline/models.py:190-269`,
  `backend/application/tests/test_baseline_gate_waivers_821.py`,
  `backend/rest_api/tests/test_baseline_gate_waivers_821_rest.py`
- GH-513: `backend/application/baseline_facade.py:379-568`, `:1180-1214`
- #1021: `backend/application/tests/test_audit_finding_identity_1021.py`
- #490 (Fail-closed-Gate): `backend/application/baseline_facade.py:379-511`
- #865 (API-Key-Tiers): `backend/auth_tenancy/services/authorization.py:59-112`,
  `backend/rest_api/tests/test_granular_api_key_scope_865.py:203+`
- ADR-01 (Single Entry Point), ADR-03 (Row-Level-Security)
- Revision-1-Review: `docs/superpowers/plans/2026-09-22-se-auditor-waivers-569-spec-review.md`
- **Revision-2-Review (rev3-Grundlage):** `docs/superpowers/plans/2026-09-22-se-auditor-waivers-569-spec-review-rev2.md`
  (Verdict `CHANGES_REQUESTED`, `major: 2` = N1/M-A + N2/M-B, `resolution.M2 = partial`, `minor: 4` = N3–N6)
- **Revision-3-Review (Iteration-2-Grundlage):** `docs/superpowers/plans/2026-09-22-se-auditor-waivers-569-spec-review-rev3.md`
  (Verdict `CHANGES_REQUESTED`, M-A/M-B + N1–N6 resolved, `major: 1` = R3-01, `minor: 9` = R3-02…R3-10,
  `info: 5` = R3-11…R3-15)
- RFC 9110 §15.5.1 (400), §15.5.4 (403), §15.5.5 (404), §15.5.10 (409), §15.5.21 (422)
- Fehler-Maps: `backend/rest_api/views.py:166-206` (`_EXC_TO_HTTP`/`_EXC_TO_CODE`),
  `backend/rest_api/serializers.py:85-158` (`_ERROR_MESSAGES`),
  `backend/mcp_server/protocol_handler.py:51-122` (`ERROR_CODES`/`ERROR_CODE_MAP`)

---

## 11. Revision 1 → 2 Auflösungs-Matrix

Review: `docs/superpowers/plans/2026-09-22-se-auditor-waivers-569-spec-review.md`
(Verdict CHANGES_REQUESTED: 1 critical, 7 major, 7 minor, 4 info).

| Befund | Auflösung | Betroffener Spec-Abschnitt |
|---|---|---|
| **C1** Document-Scope nicht unterdrückbar | `scope`/`scope_artifact_id` additiv in REST-Body + MCP-Schema; Existenz-Prüfung läuft über den benannten Scope (`_run_engine_uncapped(scopes=…)`), persistierter Scope weiter aus dem gematchten Finding; UI sendet den Finding-Scope mit. | §3.3 (4), §3.4, §3.5, §3.6, AC-569-17 |
| **M1** `audit`-Namespace reklassifiziert `audit.se_audit` | Statt Namespace-Erweiterung neue Tool-Level-Menge `_GOVERNANCE_TOOL_NAMES = {"audit.waive_finding"}`; `audit.se_audit` bleibt AUTHOR-Tier, `audit.waivers` in `_READ_ONLY_TOOL_NAMES`; Tier mit Test gepinnt. | §3.5, AC-569-18 |
| **M2** Verortung des Autoritäts-Choke-Points | `validate_waiver_reason` + `assert_gate_waiver_authority` als SSOT in `baseline/waivers.py`; neue Domain-Exception `GovernanceAuthorityError`; `BaselineFacade._assert_override_permission` delegiert (Bestandstests kompatibel). | §3.1 (M2-Block), AC-569-20 |
| **M3** Prämisse „`details` werden verworfen" veraltet | **Diese rev2-Auflösung ist selbst widerlegt (Post-Implementierungs-Review 2026-09-22).** Korrekt: `details` werden **nicht** persistiert (`audit/services.py:159`, `audit/writer.py:190-202`, keine Spalte in `audit/models.py:246-306`); der Payload ist nur an der `_audit`-Aufrufgrenze prüfbar, der durable Trail ist `AuditEntry` + `BaselineGateWaiver`-Zeile (Join via `entity_id`). AC-569-09 auf dieser Basis präzisiert; Writer-Umbau bleibt Non-Goal. | §1, §2 (DoD 4), §3.2/M4, §5/E2, §7, AC-569-09, V13 |
| **M4** `waiver_ids` nur neu erzeugt | `GateWaiverOutcome.matched_waiver_ids` additiv (alle gematchten Zeilen); `_apply_waivers` liefert sie; Description + `details["matched_waiver_ids"]`; `waiver_ids` bleibt Bestandscontract. | §3.2 (M4-Block), §5/E2, AC-569-09/19 |
| **M5** Zähler-Umdeutung nicht additiv | `counts.blockers`/`total_blockers_available` bleiben deskriptiv; rein additiv `counts.suppressed`, `counts.suppressed_blockers`, `total_suppressed_available`, `total_suppressed_blockers_available`. | §3.3 (M5-Block), §7, AC-569-13 |
| **M6** MCP-Manifest-Regeneration fehlt | Rollout ergänzt: `python backend/manage.py export_tool_manifest` + Manifest-Commit; Ratchet-Tests benannt. | §9, AC-569-25 |
| **M7** GH-821-Garantie unvollständig | AC-569-COMPAT auf vier Teile erweitert (a Rendering, b defensive R2a-Abdeckung der neuen `scope=""`-Zeilenform [Iteration 2 präzisiert: nicht „Bestandszeile" — der Gate-Pfad stempelt `"project"`, R3-04], c Gate-Matching-Pfad gegen produktionsreale Zeilenform `"project"`, d Mutationsproben); AC-569-16 nutzt eine real persistierte Zeile. | §1, §4, AC-569-COMPAT, AC-569-16 |
| **m1** Abgelaufener Waiver + neuer Grant | `409 SUPPRESSION_EXPIRED` statt stillem 200-No-op; aktiver Bestandswaiver bleibt 200/`created=false`. | §3.2 (m1-Block), §3.4, AC-569-21 |
| **m2** `include_suppressed`-Parsing | Parse-Helfer analog `_parse_scopes`: nur `true`/`false` (case-insensitiv), abwesend = `true`, sonst 400; `state` auf `active|expired|all` beschränkt. | §3.4, AC-569-22 |
| **m3** UI-Ratchet nicht konkretisiert | Keine neuen Inline-Styles; CSS-Module/gehoistete `CSSProperties`; `STYLE_BRACE_BASELINE` nur bewusst nachführen (nie erhöhen). | §3.6, §9, AC-569-23 |
| **m4** Regel 2 über-breit | R2b bindet scope-agnostische Findings an `record.scope_artifact_id == ""`; dokumentgebundene Waiver bleeden nicht. | §3.1 (R2), §5/E6, AC-569-16/26 |
| **m5** `load_waived_finding_keys`-Kompatvertrag untestet | Keyword-only `now`, positionskompatibler 2-Arg-Aufruf; Gleichheits-Regressionstest. | §3.1, AC-569-24 |
| **m6** Threat-Model fehlt | 4-Fragen-Sektion ergänzt. | §8 (Threat Model) |
| **m7** Invariante bei `include_suppressed=false` | Explizite Doku-Invariante + `suppressed_filtered` + Test. | §3.3, AC-569-13/27 |
| **i1–i4** | Informativ, keine Änderung nötig (Mutationsprobe/AC-Zählung bestätigt). | — |
| **O2–O6** | Als getroffene Entscheidungen übernommen (blocker-only, Default `true`, Ablauf optional, Description+Details genügen, i18n neutral). | §1, §5/E5, §8 |
| **O1** Revoke | Bleibt offen (Produktentscheidung), als solche gekennzeichnet. | §7, §8, §9 |

---

## 11.1 Revision 2 → 3 Auflösungs-Matrix

Review: `docs/superpowers/plans/2026-09-22-se-auditor-waivers-569-spec-review-rev2.md`
(Verdict CHANGES_REQUESTED: 2 major = N1/M-A + N2/M-B, 4 minor = N3–N6).
Die kompakte, für Reviewer gedachte Delta-Tabelle steht zusätzlich als `## Changelog` am
Dokumentanfang.

| Befund | Auflösung | Betroffener Spec-Abschnitt |
|---|---|---|
| **N1 / M-A** 400-vs-422-Kollision | Disjunkter Status-Code-Vertrag E1–E18; neue Endpunkte emittieren nie 422; „nicht blockierend" 422 → **400 `WAIVER_FINDING_NOT_BLOCKING`**; Reason-Policy → **400 `WAIVER_REASON_REJECTED`**; RFC-9110-Begründung. | §1/D1, §3.4.1, AC-569-02/11/15/17/28 |
| **N2 / M-B** Reason-Policy ohne Fehlertyp | L1 `GovernanceReasonError`, L2 `WaiverReasonPolicyViolation` (+ `WaiverFindingNotBlockingError`, `SuppressionExpiredError`); Remap in beiden Fassaden; Registrierung in `_EXC_TO_*`, `_ERROR_MESSAGES`, `ERROR_CODES`/`ERROR_CODE_MAP`. | §3.1, §3.3, §3.4.2, §3.5, AC-569-29/32 |
| **M2-Rest** Policy-Konstanten | Verlagerung nach `baseline/waivers.py` + Re-Export aus `application/baseline_facade.py` (Bestandsimport bleibt gültig). | §3.1/D4, AC-569-33 |
| **N3** AC-Zählung | „27" → **34**, inkl. der neuen AC-569-28 … AC-569-33. | §6 |
| **N4** stale Prämisse in AC-569-24 | Positionskompatibilität als öffentlicher Bestandsvertrag begründet (nicht wegen `_apply_waivers`); doppelter „When"-Satz entfernt. | §3.1, AC-569-24 |
| **N5** scope-blinder Helfer | `suppressed_finding_keys` gestrichen; Konsumenten nutzen `list_suppressions` + `suppression_applies`. | §3.3, §7 |
| **N6** Fehler nicht in den Maps | Remap-Pflicht + Registrierungspflichten + bewusste Nicht-Registrierung der L1-Domain-Fehler. | §3.4.2, AC-569-29 |
| **Auftrag: `granted_by`** | Autor ausschließlich aus `ctx.user_id`; leer ⇒ 403; Body-Feld ⇒ 400. | §3.2, §3.3 Schritt 2, AC-569-30 |
| **Auftrag: Ablauf-Semantik** | Auswertung zur Entscheidungszeit (kein Job/State); bereits abgelaufener `expires_at` ⇒ 400. | §3.1/R3, §3.3 Schritt 4, §5/E3, AC-569-31 |
| **M7-Rest** zwei Zeilenformen | Expliziter Vertragssatz + Risiko 10. | §1, AC-569-COMPAT(b) |

---

## 12. Verifikationsplan (AC → Test → Assertion)

Nummeriert, je Eintrag genau eine prüfbare Zusicherung. **Kein AC ohne Eintrag**, und jeder
Eintrag benennt die Assertion so konkret, dass eine Abschwächung des Tests auffällt.
`Datei::Test` = neu anzulegende Tests, sofern nicht als „(Bestand)" markiert.

| # | AC | Datei / Test | Assertion (unabschwächbar) |
|---|---|---|---|
| V1 | AC-569-COMPAT (a) | `backend/baseline/tests/test_waivers_569.py::test_unscoped_finding_key_is_byte_identical_to_persisted_gh821_rows` (+ Bestand `test_audit_finding_identity_1021.py::TestCanonicalFindingKey::test_the_scope_less_rendering_is_byte_identical_to_the_legacy_format`) | `finding_key("TRACE-P1", ["b","a"]) == "TRACE-P1\x1fa,b"` **und** `finding_key(r,ids,None) == finding_key(r,ids) == finding_key(r,ids,"")`; der Literal-Wert wird zusätzlich gegen eine real persistierte `BaselineGateWaiver.finding_key` verglichen (Byte-Gleichheit). |
| V2 | AC-569-COMPAT (b) | `test_waivers_569.py::test_suppression_applies_is_gh821_backward_compatible` | Neue `scope=""`-Zeilenform + beliebiger Finding-Scope ⇒ `suppression_applies(...) is True` über R2a; `load_suppressions` liefert `record.scope == ""` (NULL-Normalisierung bleibt als defensive Zukunftsabsicherung erhalten). |
| V3 | AC-569-COMPAT (c) | `backend/application/tests/test_baseline_gate_waivers_569.py::test_pre_569_persisted_project_stamped_waiver_still_suppresses_after_matcher_switch` | Zeile via **Gate-Build** erzeugt, `scope == "project"`, `scope_artifact_id == ""`; zweiter `create_baseline` **ohne** erneutes Mitschicken ⇒ `GateWaiverOutcome.suppressed` enthält das Finding und `remaining == ()` (R2b). |
| V4 | AC-569-COMPAT (d) | Mutationsproben (dokumentiert in beiden Test-Docstrings) | Entfernen von `waivers.py:96-97` ⇒ V1 rot; Entfernen der R2a/R2b-Klauseln ⇒ V3 rot. Beide Proben sind im Docstring benannt. |
| V5 | AC-569-01 | `test_audit_finding_identity_1021.py::TestStableAcrossReAudit::test_a_scoped_finding_keeps_its_unscoped_key_across_re_audit` | Nach zwei Läufen mit dazwischen eingefügtem Fremd-Finding: scope-loser Key **und** `AuditFindingView.finding_key` (scoped) beider Läufe identisch; `index` darf differieren. |
| V6 | AC-569-02 | `backend/rest_api/tests/test_audit_waivers_569_rest.py::test_placeholder_reason_is_rejected_with_400_and_dedicated_code` + `backend/mcp_server/tests/test_audit_tool_group.py::test_waive_placeholder_reason_returns_waiver_reason_rejected` | Für `"ok"`, `"aaaaaaaaaaaaaaa"`, `"test test test"`, `"   "`, `"TRACE-P1 TRACE-P2"`: `status_code == 400` **und** `error.code == "WAIVER_REASON_REJECTED"`; MCP auf `tools/call`: `result.isError is True` und String-`error_code == "WAIVER_REASON_REJECTED"` (**kein** numerischer Code; `ERROR_CODE_MAP`-Wert `-32008` separat via V36); `BaselineGateWaiver.objects.count() == 0`. |
| V7 | AC-569-03 | `backend/application/tests/test_audit_waivers_569.py::test_each_new_suppression_gets_an_audit_entry` | Genau ein `AuditEntry` mit `operation == "baseline.waiver_create"`, `entity_type == "BaselineGateWaiver"`, `change_reason == reason`, `actor == str(ctx.user_id)`, `details["granted_by"]` und `details["expires_at"]` gesetzt. |
| V8 | AC-569-04 | `test_audit_waivers_569_rest.py::test_waiver_is_idempotent_per_finding` | Erster POST `201`, zweiter `200`; `BaselineGateWaiver.objects.count() == 1`; `reason`/`granted_by` unverändert; `AuditEntry`-Zahl mit `operation="baseline.waiver_create"` bleibt `1`. |
| V9 | AC-569-05 | `test_audit_waivers_569_rest.py::test_list_filters_by_state` | Default ⇒ nur `state == "active"`; `?state=expired` ⇒ nur `"expired"`; `?state=all` ⇒ beide; `counts == {"active": 1, "expired": 1}`; `identity_key` enthält den Scope, `finding_key` nicht. |
| V10 | AC-569-06 | `test_audit_tool_group.py::test_waive_finding_is_write_and_governance_gated` | `"audit.waive_finding" in _WRITE_TOOL_PREFIXES`; `in _GOVERNANCE_TOOL_NAMES`; `"audit" not in _GOVERNANCE_TOOL_NAMESPACES`; `not in _READ_ONLY_TOOL_NAMES`; Persistenz über `AuditService.suppress_finding`. |
| V11 | AC-569-07 | `test_audit_tool_group.py::test_waivers_is_read_only`, `::test_waivers_requires_approval_authority`, `::test_se_audit_marks_suppressed_findings` | `"audit.waivers" in _READ_ONLY_TOOL_NAMES`; Editor/Viewer ⇒ `error_code == "PERMISSION_DENIED"` (Tier read, effektive Autorität = Approval-Authority, C2); `audit.se_audit`-Finding hat `suppressed is True` und `suppression_reason`; `counts["suppressed"] >= 1`. |
| V12 | AC-569-08 | `test_baseline_gate_waivers_569.py::test_suppressed_blocker_does_not_block_but_is_recorded` (+ Bestand `test_baseline_gate_waivers_821.py::test_unwaived_findings_still_block`) | 3 Blocker, 1 unterdrückt ⇒ `BaselineGateBlockedError` und die Meldung nennt genau die **2** verbleibenden; alle unterdrückt ⇒ Baseline wird erzeugt. |
| V13 | AC-569-09 | `test_baseline_gate_waivers_821_rest.py::test_baseline_metadata_names_matched_waiver_ids_on_reuse`, `::test_baseline_create_audit_details_carry_the_suppression_trail` | Description enthält `[SE-Auditor waiver]` + `rule_ids` + die persistierte Waiver-UUID; der beim `baseline.create` **konstruierte** `details`-Payload (abgefangen an der `_audit`-Aufrufgrenze) enthält `suppressed_blocker_count`, `suppressed_finding_keys`, `waiver_ids` **und** `matched_waiver_ids` (nicht leer beim Reuse). **Nicht** als persistierte Spalte geprüft (der Writer verwirft `details`); durable sind `AuditEntry` (`op`/`entity_type`/`entity_id`/`actor`/`change_reason`) + die `BaselineGateWaiver`-Zeile, verbunden über `AuditEntry.entity_id → BaselineGateWaiver.id` (MCP: `change_reason is None`). |
| V14 | AC-569-10 | `test_baseline_gate_waivers_569.py::test_expired_waiver_re_blocks` + `test_audit_waivers_569.py::test_expired_suppression_is_not_applied` | Abgelaufener Waiver ⇒ Finding `suppressed is False`, Build blockiert ohne Override; `GET ?state=expired` liefert `state == "expired"`. |
| V15 | AC-569-11 | `test_audit_waivers_569_rest.py::test_no_suppression_without_reason_authority_or_finding` | Für alle vier Negativfälle: `status_code in {400, 403}`, **`status_code != 422`**, `BaselineGateWaiver.objects.count() == 0`, kein `baseline.waiver_create`-`AuditEntry`. |
| V16 | AC-569-12 | `test_audit_waivers_569_rest.py::test_editor_waiver_is_rejected_with_403` + `test_granular_api_key_scope_865.py::test_audit_waive_endpoint_rejects_author_tier_key` | Editor ⇒ `403`/`PERMISSION_DENIED`; AUTHOR-Tier-Key ⇒ `403`; MCP ⇒ `error_code == "PERMISSION_DENIED"`. |
| V17 | AC-569-13 | `test_audit_waivers_569_rest.py::test_report_marks_and_filters_suppressed`, `::test_counts_stay_descriptive_and_totals_stay_absolute_when_filtered` | Default: Finding in `findings` mit `suppressed is True` + `suppressed_until`/`suppression_reason`/`suppression_id`; `counts["blockers"]` unverändert deskriptiv; `counts["suppressed"]`/`["suppressed_blockers"]` zusätzlich. **In beiden Modi** `counts["blockers"] + counts["warnings"] == counts["total"]`. `include_suppressed=false`: Finding fehlt, `counts.total == len(findings)`, `counts.total != total_findings_available` (m7, Fenster vs. Gesamtlauf) und `total_findings_available == len(findings) + suppressed_filtered`. |
| V18 | AC-569-14 | `frontend/src/components/Audit/audit-dashboard.test.tsx` — `suppresses a finding via the waive dialog`, `hides suppressed findings when the filter is off` | Nach Bestätigen existiert `audit-suppressed-badge-<index>` mit Begründungstext; `audit-count-suppressed` zeigt den erhöhten Wert; Abwählen von `audit-show-suppressed` entfernt die unterdrückte Zeile, Anwählen stellt sie wieder her; i18n-Paritätstest grün. |
| V19 | AC-569-15 | `test_audit_waivers_569_rest.py::test_waiver_for_an_unreported_finding_is_rejected_with_400_and_dedicated_code`, `::test_waiver_for_a_warning_finding_is_rejected_with_400_and_dedicated_code` | Beide Fälle: `status_code == 400`, `error.code == "WAIVER_FINDING_NOT_BLOCKING"`, **nicht** 422; keine Zeile. |
| V20 | AC-569-16 | `test_waivers_569.py::test_suppression_applies_is_gh821_backward_compatible` | (i) `"project"`-gestempelte Zeile matcht scope-agnostisches Finding; (ii) dokument-gebundener Waiver matcht nur das Document-Finding, **nicht** das scope-agnostische; (iii) `scope="project"`-Record matcht **kein** `scope="document"`-Finding. |
| V21 | AC-569-17 | `test_audit_waivers_569_rest.py::test_document_scoped_finding_is_waivable` + `test_audit_tool_group.py::test_waive_document_scope_requires_artifact_id` | Mit `scope="document"`+`scope_artifact_id` ⇒ `201`, persistierte Zeile `scope == "document"` und `scope_artifact_id == "<doc>"`; ohne `scope_artifact_id` ⇒ `400 VALIDATION_ERROR` (**nicht** 422); scope-agnostischer Aufruf erzeugt **keine** document-scoped Zeile. |
| V22 | AC-569-18 | `test_audit_tool_group.py::test_audit_namespace_is_not_bulk_reclassified` | `_required_scope_operation("audit.se_audit") is Operation.WRITE`; `("audit.query")`/`("audit.ai_review") is Operation.READ`; `("audit.waive_finding") is Operation.WORKSPACE_CONFIG`; `"audit" not in _GOVERNANCE_TOOL_NAMESPACES`. |
| V23 | AC-569-19 | `test_baseline_gate_waivers_569.py::test_reused_waiver_is_reported_in_matched_ids` | Reuse-Build: `matched_waiver_ids == (persisted_id,)`, `waiver_ids == ()`, Description enthält die ID. |
| V24 | AC-569-20 | `test_audit_waivers_569.py::test_authority_choke_point_is_shared` + `test_granular_api_key_scope_865.py:207-226` (Bestand) | Beide Pfade (`AuditService.suppress_finding`, `BaselineFacade`-Gate-Waiver) liefern identisch `PermissionDeniedError`; `BaselineFacade._assert_override_permission` bleibt direkt aufrufbar; kein zweiter Copy-Paste-Check (assert via `assert_gate_waiver_authority`-Identität). |
| V25 | AC-569-21 | `test_audit_waivers_569_rest.py::test_expired_existing_waiver_returns_409` | Nur abgelaufene Zeile ⇒ `status_code == 409` und `error.code == "SUPPRESSION_EXPIRED"`; Zeile unverändert; kein neuer `AuditEntry`. Aktive Zeile ⇒ `200` mit `created == false`. |
| V26 | AC-569-22 | `test_audit_waivers_569_rest.py::test_include_suppressed_query_parsing` | `true`/`false`/`TRUE`/abwesend ⇒ `200` (abwesend wirkt wie `true`); `1`/`yes`/`banana` ⇒ `400 VALIDATION_ERROR`; `?state=x` ⇒ `400 VALIDATION_ERROR`. |
| V27 | AC-569-23 | `frontend/src/test/ui-ratchet.test.ts` (Bestand) | `STYLE_BRACE_BASELINE` unverändert (exakte Gleichheit, `:1035`/`:1047`); Test grün. |
| V28 | AC-569-24 | `test_waivers_569.py::test_load_waived_finding_keys_matches_load_suppressions` | `load_waived_finding_keys(ws, tenant) == {r.finding_key for r in load_suppressions(ws, tenant, include_expired=False)}`; abgelaufene Keys fehlen; 2-Argument-Aufruf ohne `TypeError`. |
| V29 | AC-569-25 | `backend/mcp_server/tests/test_tool_manifest_drift.py` + `docs/agent-templates/test_role_tools_exist_in_manifest.py` (Bestand) | Manifest enthält `audit.waive_finding`/`audit.waivers`; `tool_count` stimmt mit der Registry überein; InputSchemas ohne Drift. |
| V30 | AC-569-26 | `test_waivers_569.py::test_document_waiver_does_not_bleed_into_scope_agnostic_finding` | Dokument-gebundener Waiver (`scope_artifact_id != ""`) matcht das scope-agnostische Finding **nicht** (R2b), nur das Document-Finding (R2c). |
| V31 | AC-569-27 | `test_audit_waivers_569_rest.py::test_filtered_report_invariant` | Bei `include_suppressed=false`: `counts.total == len(findings)` und `total_findings_available == len(findings) + suppressed_filtered` (ungecappter Lauf) — **Test-Assertion**. Die „§8 Threat-Model-Fragen (1)–(4) je beantwortet" ist eine **Doku-Pflicht, keine Test-Assertion** (R3-12). |
| V32 | AC-569-28 | `backend/rest_api/tests/test_audit_waivers_569_error_contract.py::test_no_new_endpoint_emits_422` + `::test_remediate_keeps_422_for_the_modify_flip` | Parametrisiert über E3–E9/E11–E13/E15–E16/E19–E20: `status_code != 422` und exakt der in §3.4.1 erwartete Status+Code; `remediate` liefert weiterhin `422`. |
| V33 | AC-569-29 | `test_audit_waivers_569.py::test_reason_policy_raises_governance_reason_error`, `::test_gate_path_still_raises_plain_validation_error`, `test_audit_waivers_569_error_contract.py::test_new_error_types_are_registered_in_exc_maps`, `::test_governance_domain_errors_are_not_registered` | `validate_waiver_reason` wirft `GovernanceReasonError`; die module-level Funktion `_validate_gate_reason` wirft `type(exc) is ValidationError`; `type(exc) in _EXC_TO_HTTP`/`_EXC_TO_CODE` für alle drei L2-Typen mit den Werten aus §3.4.2; `GovernanceReasonError`/`GovernanceAuthorityError` **nicht** in den Maps. |
| V34 | AC-569-30 | `test_audit_waivers_569_rest.py::test_granted_by_comes_from_the_auth_context_only`, `test_audit_waivers_569.py::test_blank_author_is_rejected` | `row.granted_by == str(getattr(ctx, "user_id", "") or "").strip()`; `ctx.user_id is None` ⇒ Formel liefert `""` ⇒ `403 PERMISSION_DENIED`; Body-Feld `granted_by` ⇒ `400 VALIDATION_ERROR`; keine Zeile. |
| V35 | AC-569-31 | `test_waivers_569.py::test_expiry_is_evaluated_at_decision_time_with_injected_now`, `test_audit_waivers_569_rest.py::test_past_or_naive_expires_at_is_rejected` | Mit `now > expires_at`: `suppression_applies(...) is False`, `state == "expired"`, Finding blockiert; ohne Job/DB-Änderung; `expires_at <= now` oder naiv im Request ⇒ `400 VALIDATION_ERROR`, keine Zeile. |
| V36 | AC-569-32 | `test_audit_tool_group.py::test_new_waiver_error_codes_are_registered`, `test_audit_waivers_569_error_contract.py::test_new_error_codes_have_de_and_en_messages` | `ERROR_CODE_MAP["WAIVER_REASON_REJECTED"] == -32008`, `["WAIVER_FINDING_NOT_BLOCKING"] == -32009`, `["SUPPRESSION_EXPIRED"] == -32010`; alle drei Keys in `ERROR_CODES`; `_ERROR_MESSAGES[c]` hat nicht-leere `de` **und** `en`. |
| V37 | AC-569-33 | `test_baseline_gate_waivers_821.py` (Bestand) + `test_waivers_569.py::test_reason_policy_constants_are_reexported_from_the_facade` | `from application.baseline_facade import MIN_OVERRIDE_REASON_LENGTH` funktioniert; Werte sind in `baseline.waivers` definiert und identisch (15/4/3); AC-569-02-Beispiele verhalten sich unverändert. |
