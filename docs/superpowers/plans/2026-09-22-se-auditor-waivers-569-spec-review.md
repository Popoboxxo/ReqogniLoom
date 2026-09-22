---
type: REVIEW
scope: "#569 / docs/superpowers/plans/2026-09-22-se-auditor-waivers-569-spec.md"
status: done
date: 2026-09-22
author_agent: concept-reviewer
reviewer: concept-reviewer
reviewed_artifact: docs/superpowers/plans/2026-09-22-se-auditor-waivers-569-spec.md
revision_reviewed: 1
verdict: CHANGES_REQUESTED
findings:
  critical: 1
  major: 7
  minor: 7
  info: 4
---

# Review — #569 Spec: SE-Auditor Findings unterdrücken (Waiver mit Begründung)

Read-only Review der Spezifikation `2026-09-22-se-auditor-waivers-569-spec.md`
(revision 1) gegen den echten Code auf Branch `feat/se-validation-completeness`.
Kein Code geändert.

## 1. Scope

- **Gegenstand:** Vollständigkeit, Logik, Annahmen, Risiken, Feasibility, Konsistenz,
  Threat-Model-Relevanz der Spezifikation.
- **Methode:** Jede Behauptung der Ist-Zustands-Tabelle und jeder Interface-Contract
  wurde gegen `file:line` im Repo geprüft.
- **Nicht Gegenstand:** Implementierungs-Details, Code-Review, REQ-Vergabe.

## 2. Verifizierter Ist-Zustand (Positivbefund)

Die Ist-Zustands-Tabelle (§2) ist in den meisten Zeilenangaben korrekt. Stichproben
bestätigt:

- `baseline/waivers.py:56-98` (`finding_key`), `:46-53` (`canonical_artifact_ids`),
  `:126-137` (`load_waived_finding_keys`), `:140-192` (`record_waiver`) — korrekt.
- `baseline/models.py:190-269` (`BaselineGateWaiver`), UniqueConstraint `:249-252`,
  CheckConstraint `:253-256` ("reason not blank", nur `""`, kein Whitespace) — korrekt.
- `application/audit_service.py:80-85` (`finding_key`-Property), `:90` (`to_dict`) — korrekt.
- `rest_api/audit_views.py:131/167/222` (nur run/remediate/ai-review) — korrekt.
- `mcp_server/tools/audit.py:233-241` (nur query/ai_review/se_audit/dlq_list/dlq_replay)
  — korrekt; `AuditService` hat tatsächlich keine Waiver-Methoden.
- `application/baseline_facade.py:529-537` (unterdrückte zählen nicht als Blocker),
  `:336-350` (Summary + change_reason), `:370` (Event-Payload), `:645-657`
  (Waiver-Audit-Eintrag), `:739-780` (`_assert_override_permission`), `:1099`
  (`_MAX_LISTED_FINDINGS`), `:1117-1177` (`_validate_gate_reason`), `:1180-1214`
  (`_annotate_waiver`) — korrekt.
- `audit/models.py:165` (`OP_BASELINE_WAIVER_CREATE = "baseline.waiver_create"`) — korrekt.
- Migrationen `baseline/0007_…`, `0008_…`: höchste ist `0008` → `0009` ist frei;
  RLS-Policy in `0008` deckt die Tabelle ab, ein neues nullable Feld braucht keine
  Folgemigration — korrekt.
- Frontend-Anker `audit-dashboard.tsx:777-827` (nur Adopt/Modify), `:159`
  (`severityFilter`), `api/audit.ts:40-50` (`AuditFinding` ohne `finding_key`) und
  `:112-134` (nur run/remediate) — korrekt. Die Aussage "Backend liefert bereits
  `finding_key`, TS-Typ deklariert ihn nicht" trifft zu.
- AC-569-COMPAT-Anker: `test_audit_finding_identity_1021.py:115-141`, `:188-248`,
  `:261-276` — korrekt; der genannte Test existiert.
- Die Mutationsprobe ist valide: die Verzweigung liegt in `waivers.py:95-97`
  (`scope_part = … / if not scope_part: return base`); entfernt man sie, rendert
  `finding_key("TRACE-P1", ["a"])` zu `"TRACE-P1\x1fa\x1f"` und
  `test_the_scope_less_rendering_is_byte_identical_to_the_legacy_format`
  (`:115-122`) wird rot. ✓
- AC-Zählung "17 ACs (COMPAT + 01…16)" ist konsistent.

## 3. Findings

### Critical

#### C1 — [Completeness/Logic] Document-scoped Findings sind über die spezifizierten Oberflächen nicht unterdrückbar
- **Beschreibung:** `AuditService.suppress_finding` prüft die Existenz des Findings gegen
  `_run_engine_uncapped(...)` **ohne** `scopes` (§3.3 Schritt 3). Der RuleEngine-Default
  ist `[AuditScope("project")]` (`traceability/audit/rule_engine.py:102-104`,
  bestätigt in `audit_service.py:318-319`). Scope-aware Findings (z. B. `TRACE-P7`,
  `scope="document"`) werden ohne expliziten Document-Scope **nicht** berichtet →
  `suppress_finding` wirft `ValidationError` (422).
  Gleichzeitig akzeptiert der Request-Body `POST …/audit/waivers/` `scope` /
  `scope_artifact_id` **bewusst nicht** (§3.4: "werden nicht vom Client akzeptiert"),
  ebenso das MCP-Schema `audit.waive_finding` (§3.5). Das SE-Auditor-Dashboard erlaubt
  aber `scope="document"` (`audit-dashboard.tsx:135`, Picker ab `:191-197`) und zeigt
  document-scoped Findings. Die neue dritte Aktion würde für sie ausnahmslos 422 liefern.
  Damit ist DoD 3/5 für den Document-Scope faktisch nicht erfüllt.
- **Fix:** Entweder `scope`/`scope_artifact_id` additiv in das Request-Body- bzw.
  MCP-Schema aufnehmen (der Server nutzt sie nur für den Engine-Lauf, übernimmt sie aber
  weiterhin aus dem gematchten Finding) **oder** die Existenz-Prüfung explizit über alle
  relevanten Scopes laufen lassen und den Scope des gematchten Findings verwenden.
  Beide Varianten brauchen einen AC („Ein document-scoped Finding ist unterdrückbar").

### Major

#### M1 — [Consistency/Security] `_GOVERNANCE_TOOL_NAMESPACES += "audit"` reklassifiziert `audit.se_audit` still (AUTHOR → ADMIN)
- **Beschreibung:** Die Spec behauptet (§3.5, `tool_registry.py:530-533`), `audit.query`,
  `audit.ai_review` **und** `audit.se_audit` blieben READ-Tier. Das ist für `audit.se_audit`
  falsch: es steht nicht in `_READ_ONLY_TOOL_NAMES` (`tool_registry.py:395-510`; dort nur
  `audit.query`/`audit.ai_review`, Z. 420-421) und endet nicht auf `.read`/`.query`
  (`_READ_ONLY_TOOL_SUFFIXES`, Z. 512). `_is_write_tool("audit.se_audit")` liefert daher
  `True` (fail-closed, Z. 1392-1407), und `_required_scope_operation` mappt einen
  Write-Tool-Namespace in `_GOVERNANCE_TOOL_NAMESPACES` auf `Operation.WORKSPACE_CONFIG`
  (ADMIN-Tier, Z. 1424-1430). Mit dem vorgeschlagenen Eintrag "audit" verliert ein
  AUTHOR-Tier-Key den Zugriff auf `audit.se_audit`. Das widerspricht der dokumentierten
  Nicht-Admin-Ausnahme in `mcp_server/tests/test_mcp_rbac_role_matrix.py:250-268` und dem
  „additiv, keine Verhaltensänderung bestehender Tools"-Prinzip; AC-569-06/07 testen
  diesen Drift nicht.
- **Fix:** Nicht den Namespace, sondern exakt `audit.waive_finding` als Governance-Prefix
  führen (z. B. `_WRITE_TOOL_PREFIXES` + eine explizite Governance-Menge auf Tool-Ebene)
  oder `audit.se_audit` explizit in `_READ_ONLY_TOOL_NAMES` aufnehmen und den Tier für
  `audit.se_audit` mit einem Test pinnen. Die Aussage „bleibt READ-Tier" ist zu korrigieren.

#### M2 — [Feasibility/SSOT] `_assert_override_permission` wird von `AuditService` aufgerufen, aber nirgends neu verortet
- **Beschreibung:** Die Spec (§3.3 Schritt 1) lässt `AuditService.suppress_finding`
  `_assert_override_permission(ctx)` aufrufen und nennt es "derselbe Choke-Point wie der
  Gate-Waiver". Der Choke-Point ist heute ein `@staticmethod` von `BaselineFacade`
  (`baseline_facade.py:738-780`), und kein anderer Ort exportiert ihn. Die Spec legt
  gleichzeitig fest, dass `AuditService` die Begründungs-Policy nutzen kann, "ohne die
  Schwester-Fassade zu importieren" (§3.1). Damit ist offen, wie `AuditService` an die
  Berechtigungsprüfung gelangt: Import der Schwester-Fassade (widerspricht ADR-01-Ziel)
  oder Duplikat (zerstört die SSOT-Garantie und damit DoD 6 / AC-569-12).
- **Fix:** Beide Prüfungen (`_validate_gate_reason` **und** `_assert_override_permission`)
  in eine gemeinsame, importierbare Helper-Einheit verschieben (naheliegend:
  `baseline/waivers.py` oder ein Governance-Helfer) und `BaselineFacade` sowie
  `AuditService` nur noch delegieren lassen. Bestehende Tests
  (`test_granular_api_key_scope_865.py:207-226` rufen `BaselineFacade._assert_override_permission`
  direkt) müssen dabei kompatibel bleiben oder angepasst werden.

#### M3 — [Assumptions] Die Prämisse "`details` werden verworfen" ist veraltet — der Baseline-Metadaten-Trail existiert bereits
- **Beschreibung:** §2 (DoD 4) und §5/E2 stützen sich auf den Kommentar
  `baseline_facade.py:322-325` ("`details` is v1-reserved and currently dropped by the
  writer"). Dieser Kommentar ist falsch: `ServiceBase._audit` persistiert `details` seit
  #399/ADR-10 (`application/base.py:197-205`). Der `baseline.create`-Audit-Eintrag trägt
  bereits `suppressed_blocker_count`, `suppressed_rule_ids`, `suppressed_finding_keys`
  und `waiver_ids` (`baseline_facade.py:336-344`). Die Behauptung "kein AuditLog-Writer-
  Umbau" als Non-Goal ist okay, aber die Begründung für den Description-Umbau und die
  offene Frage O5 ("Reicht die Description-Annotation oder braucht es einen strukturierten
  Datensatz?") beruhen auf einer Fehlannahme — ein strukturierter Trail ist im Audit-Detail
  schon vorhanden.
- **Fix:** Ist-Zustand korrigieren; O5 auf Basis des echten Writer-Verhaltens neu stellen;
  AC-569-09 um eine Assertion auf die `baseline.create`-`details` (`waiver_ids`,
  `suppressed_finding_keys`) ergänzen.

#### M4 — [Logic] AC-569-09 (`waiver_ids` in der Description) ist so nicht umsetzbar/inkonsistent
- **Beschreibung:** `GateWaiverOutcome.waiver_ids` enthält ausschließlich **neu erzeugte**
  Zeilen (`baseline_facade.py:594-595` Docstring, `:610-642` nur `created_ids`,
  `:103-110` Feld-Doku "Ids of the waiver rows *created* by this request"). Ein Build, der
  persistierte Waiver wiederverwendet, hat `suppressed > 0` bei `waiver_ids == []`. Die
  Description würde dann "N blocking finding(s) suppressed …" ohne oder mit zu wenigen IDs
  ausweisen — Count und ID-Liste widersprechen sich, AC-569-09 ("Namen der waiver_ids")
  ist nicht erfüllbar. Die Spec erwähnt keine Änderung von `_apply_waivers`, um die IDs der
  **gematchten** Zeilen zurückzugeben.
- **Fix:** Entweder `_apply_waivers`/`GateWaiverOutcome` additiv um die IDs der gematchten
  (nicht nur neu erzeugten) Zeilen erweitern und das in der Spec als Contract festhalten,
  oder die ID-Nennung aus AC-569-09 streichen und auf Counts + Audit-Details beschränken.

#### M5 — [Consistency] Die Umdeutung von `counts.blockers`/`total_blockers_available` ist keine additive Änderung
- **Beschreibung:** §3.3 erklärt `counts.blockers` = Findings mit `Severity.BLOCKER` **und**
  `suppressed=false`. Der Modul-Docstring `audit_service.py:99-119` legt fest, dass
  `counts.blockers`/`warnings` beschreiben, "was tatsächlich in `findings` steht", und
  `total_blockers_available` die echte Vor-Cap-Blockerzahl ist (BUG-15-Contract für die
  Dashboard-Badges). Mit `include_suppressed=True` (Default) sind suppressed Blocker in
  `findings` enthalten, aber nicht mehr in `counts.blockers` — die dokumentierte Invariante
  bricht, obwohl die Spec den Block als "additiv" deklariert (§2 Risiko 4 spielt es herunter).
- **Fix:** `counts.blockers` und `total_blockers_available` deskriptiv belassen und nur
  additiv `counts.suppressed` / `total_suppressed_available` (bzw.
  `total_suppressed_blockers_available`) einführen. Falls die Zählung doch geändert werden
  soll, muss das als bewusste Contract-Änderung dokumentiert und mit einem Bestandstest
  abgesichert werden.

#### M6 — [Feasibility/Rollout] MCP-Tool-Manifest-Regeneration fehlt im Rollout
- **Beschreibung:** Neue MCP-Tools müssen das committed Manifest
  `docs/agent-templates/tool-manifest.json` regenerieren, sonst schlägt der Ratchet
  `mcp_server/tests/test_tool_manifest_drift.py:84-156` (tool_count + InputSchema-Drift)
  fehl; konsumentenseitig prüft `docs/agent-templates/test_role_tools_exist_in_manifest.py`.
  §9 (Rollout/Migrationsbedarf) nennt nur Frontend/i18n, nicht den Manifest-Schritt.
- **Fix:** Rollout um "`python backend/manage.py export_tool_manifest` ausführen und
  `docs/agent-templates/tool-manifest.json` committen; Rollen-Tool-Manifest prüfen"
  ergänzen.

#### M7 — [Logic/Compat] AC-569-16 prüft nicht die reale GH-821-Zeilenform; kein Gate-Level-GH-821-Test
- **Beschreibung:** AC-569-COMPAT pinnt das *Rendering* von `finding_key` sauber (Literal +
  persistierte Zeile + Mutationsprobe). Für den *Matching*-Pfad ist das nicht ausreichend:
  `record_waiver` schreibt `scope = finding.scope or scope`
  (`baseline_facade.py:635`), d. h. reale GH-821-Zeilen für scope-agnostische Regeln wie
  TRACE-P1 tragen `scope="project"`, nicht `""`. AC-569-16 konstruiert dagegen einen
  "scope-losen Waiver" und prüft damit eine Zeilenform, die in Produktion so nicht
  vorkommt. Zusätzlich wechselt §4/Risiko 2 den Gate-Matcher von reiner Key-Mengen-
  Zugehörigkeit (`baseline_facade.py:529-534`, `:667-671`) auf `suppression_applies` mit
  Scope-/Dokument-Regeln (§3.1 Regeln 2/3) — dieser semantische Wechsel ist durch keinen
  GH-821-Bestandstest abgedeckt.
- **Fix:** AC-569-16 (und die Mutations-/Bestandssicherung) gegen eine **real persistierte**
  Zeile (via Gate-Build erzeugt, `scope="project"`) formulieren; einen Gate-Level-Test
  ergänzen: "eine vor #569 persistierte Zeile unterdrückt auch nach der
  `suppression_applies`-Umstellung weiter". Erst dann ist die GH-821-Garantie vollständig
  (nicht nur das Rendering) abgedeckt.

### Minor

- **m1 — [Completeness] Abgelaufener Bestands-Waiver + neuer aktiver Grant.** `record_waiver`
  ist idempotent per `get_or_create` (`waivers.py:171-183`); ein zweiter Call mit
  `expires_at` überschreibt nichts. Die Spec (§3.2) dokumentiert das, definiert aber nicht,
  was `suppress_finding` zurückgibt, wenn ein abgelaufener Waiver existiert und ein aktiver
  beantragt wird (Client bekommt "created=False"/200, das Finding bleibt aber blockierend).
  → Verhalten + HTTP-Code (z. B. 200 mit `state="expired"` und Warnhinweis, oder 409)
  festlegen und testen.
- **m2 — [Completeness] Query-Parsing für `include_suppressed`.** Der Wert kommt als String
  (`?include_suppressed=true|false`). Das Modul hat etablierte Parse-Helfer, die bei
  ungültigem Wert 400 werfen (`audit_views.py:90-128`). Akzeptierte Literale und
  400-Verhalten spezifizieren.
- **m3 — [Consistency] UI-Ratchet nicht konkretisiert.** `audit-dashboard.tsx` ist
  inline-style-lastig (`style={{` an Z. 776/784/805/817). `ui-ratchet.test.ts` prüft die
  Inline-Style-Zahl per **exakter** Gleichheit (`STYLE_BRACE_BASELINE`, vgl.
  `docs/superpowers/plans/2026-09-03-dokumentensicht.md:25`). §9 sagt nur "müssen grün
  bleiben". → Für Dialog/Badge/Filter explizit CSS-Module/tokens oder gehoistete
  `CSSProperties`-Konstanten fordern und `STYLE_BRACE_BASELINE` als Pflicht-Update nennen.
- **m4 — [Logic] Regel 2 ist für scope-agnostische Findings über-breit.** `finding.scope is
  None` matcht **jeden** Record unabhängig von dessen Scope (§3.1). Ein für ein
  document-scoped Finding gewährter Waiver unterdrückt damit auch das scope-agnostische
  Finding derselben Regel/Artefakte. Gewollt oder nicht — dokumentieren und testen.
- **m5 — [Consistency] `load_waived_finding_keys`-Kompatvertrag untestet.** Die Gleichheit
  `load_waived_finding_keys(...) == {r.finding_key for r in load_suppressions(...)}` (§3.1)
  und die Positionskompatibilität des neuen `now=None` sind nicht durch einen AC
  abgesichert; `_apply_waivers` ruft die Funktion positionell auf
  (`baseline_facade.py:608`). → Regressionstest ergänzen.
- **m6 — [Risks/Threat-Model] 4-Fragen-Checkliste nicht ausgewiesen.** Für ein
  Governance-Feature (intern, aber autoritativ) fehlen die expliziten Antworten. Besonders
  relevant: "was kann schiefgehen" — ein vorab angelegter Waiver für ein heute WARNING-
  Finding kann später (Tier-Wechsel) still einen Blocker unterdrücken. Kurze Threat-Model-
  Sektion (4 Fragen) ergänzen.
- **m7 — [Completeness] Invariante bei `include_suppressed=false`.** §3.3 lässt `counts`/
  `total_*_available` weiter auf den ungefilterten Lauf zeigen, `counts.total` aber auf die
  gefilterte Liste. Das ist erlaubt, aber widersprüchlich (total ≠ Summe der Severity-
  Zähler) und braucht einen expliziten Doku-Satz + Test (AC-569-13 deckt nur den Happy Path).

### Info

- **i1** — Die Ist-Zustands-Einschätzungen der sechs DoD-Punkte treffen in der Substanz zu;
  die zitierten Zeilen wurden (bis auf die unter M3/M7 genannten Punkte) verifiziert.
- **i2** — `mcp_server/workspace_scope.py` erzwingt für Tools mit **required** `workspace_id`
  bereits die Ziel-Workspace-Narrowing (Z. 61-62, 100-102); die neuen Tools mit
  pflichtigem `workspace_id` sind damit korrekt abgedeckt — keine Lücke.
- **i3** — Dass `AuditService.run_audit` heute keine Waiver konsultiert, ist korrekt
  (`audit_service.py:300-414` liest nur `self._engine.run(...)`).
- **i4** — AC-Zählung und Mutationsprobe sind konsistent und prüfbar.

## 4. AC-569-COMPAT — Bewertung

**Für das Rendering: hinreichend.** Die Kombination aus Literal-Assertion
(`test_audit_finding_identity_1021.py:115-122`), neuem Vergleich gegen eine real
persistierte Zeile und dokumentierter Mutationsprobe pinnt `finding_key(rule_id, ids)`
byte-exakt und würde einen künftigen Formatwechsel zuverlässig rot machen.

**Für die GH-821-Garantie: nicht vollständig.** Zwei Lücken:
1. Der **Matcher** (Gate wechselt auf `suppression_applies`, §4/Risiko 2) ist nicht durch
   einen Bestands-/Regressionstest abgesichert; AC-569-16 prüft nur die Funktion direkt mit
   einer nicht-produktionsrealen Zeilenform (`scope=""` statt `"project"`, siehe M7).
2. Es ist nirgends zugesichert, dass die **persistierte Spalte** dauerhaft über den
   scope-losen Aufruf gefüllt wird (der neue Zeilenvergleich deckt das nur einmalig ab).

Der geforderte Regressions-Test existiert im Plan, ist aber zu eng gefasst: er schützt das
Rendering, nicht den Matching-/Persistenzpfad. Mit dem Fix unter M7 genügt AC-569-COMPAT
der GH-821-Garantie vollständig.

## 5. Gate-Semantik §490 — stiller Bypass?

**Kein definitiver *stiller* Bypass.** Die vorgeschlagene Semantik wahrt die wesentlichen
Eigenschaften:

- Pflicht-Begründung über `validate_waiver_reason` (SSOT) + DB-Constraint
  (`models.py:253-256`) — kein Waiver ohne Statement.
- Autorität Admin/Approver **und** ADMIN-Tier (§865), gleicher Choke-Point wie der
  Gate-Waiver.
- Fail-closed bleibt: nicht abgedeckte Blocker blockieren weiterhin
  (`baseline_facade.py:536-568`), der GH-400-"nicht auswertbar"-Pfad bleibt unüberbrückbar.
- Ablauf ist ein Re-Evaluierungs-Trigger, kein Freibrief (`expires_at <= now` unterdrückt
  nicht); `include_suppressed`-Default `true` = nichts wird versteckt.
- Audit-Spur je neuem Waiver (`baseline.waiver_create`) plus Summary im `baseline.create`-
  Eintrag — der Trail existiert (siehe M3).

**Zwei Restrisiken**, die die Spec adressieren sollte:
1. **Autoritäts-Choke-Point** (M2): solange unklar ist, wo `_assert_override_permission`
   lebt, droht ein Duplikat, das ggf. den ADMIN-Tier-Check verliert → dann doch ein
   stiller Bypass für AUTHOR-Keys.
2. **Scope-Matcher** (M7/m4): die permissivere Regel-2-Klausel und der ungetestete
   Matcher-Wechsel können Unterdrückungen breiter wirken lassen als dokumentiert.

## 6. Offene Fragen (Triage)

| # | Frage | Triage |
|---|---|---|
| O1 | Revoke / Unterdrückung aufheben | **Bleibt offen.** Produktentscheidung; das DoD nennt keinen Widerruf. Follow-up-Empfehlung: eigener OP `baseline.waiver_revoke` mit Reason-Pflicht + Audit. |
| O2 | Sind WARNING-Findings unterdrückbar? | **Kann aus Code/DoD beantwortet werden.** Der bestehende Pfad ist blocker-only: `blocking_findings` filtert `Severity.BLOCKER` (`audit_service.py:293-296`), `_apply_waivers` validiert gegen diese Blocker (`baseline_facade.py:615-627`). Die Spec-Erweiterung auf "voller Lauf" ist eine *Ausweitung*, keine Klärung. Empfehlung: blocker-only belassen (konsistent zu DoD "Blocker-Finding"); WARNING-Markierung nur im Report. |
| O3 | Default `include_suppressed` | **Kann beantwortet werden.** `true` ist die einzige Wahl, die zum Leitprinzip "Nachvollziehbarkeit statt Verstecken" und DoD 6 ("kein stiller Weg") passt; `false` als Default wäre selbst ein Silent-Hiding-Regress. Bestätigung bleibt Formalie. |
| O4 | Ablauf-Pflicht | **Kann beantwortet werden.** Der Bundle-Plan/Issue sagt explizit "optional expiry" (`2026-09-21-open-issues-bundle.md:182`). → optional, `NULL` = unbefristet (wie spezifiziert). |
| O5 | Baseline-Metadaten-Träger | **Kann beantwortet werden.** `baseline.create`-`details` **werden persistiert** (`application/base.py:197-205`) und tragen bereits `waiver_ids`/`suppressed_finding_keys` (`baseline_facade.py:336-344`); hinzu kommen die immutable Description-Annotation und je Waiver ein Audit-Eintrag. Ein zusätzlicher Join-Datensatz ist vom DoD nicht verlangt. → Description + Audit-Details genügen. |
| O6 | Terminologie (Unterdrücken/Waiver/False-Positive) | **Kann beantwortet werden.** Das Terminology-Profile (`presets/terminology.py:49-74`) mappt nur einen festen Key-Satz (artifact_l1/l2, requirement, architecture_element, workspace, baseline, workflow, trace_link) — Audit-/Suppression-Begriffe sind nicht Teil des Profils. Die i18n-Keys bleiben damit profilunabhängig neutral (`audit.suppress…`). |

## 7. Verdict

**CHANGES_REQUESTED.**

Die Spezifikation ist methodisch stark: Ist-Zustand weitgehend akkurat, Contracts explizit
additiv gehalten, Non-Goals klar, Risiken benannt, GH-821-Kompatibilität als harter Test
verlangt. Sie ist jedoch in mehreren Punkten nicht implementierungsreif:

- **Critical:** der Contract verschließt sich selbst den Document-Scope (C1) — eine der
  zentralen DoD-Oberflächen funktioniert für document-scoped Findings nicht.
- **Major:** stiller Tier-Drift bei `audit.se_audit` (M1), ungeklärte Verortung des
  Autoritäts-Choke-Points (M2), veraltete `details`-Prämisse (M3), inkonsistentes AC-569-09
  (M4), nicht-additive Zähler-Semantik (M5), fehlender Manifest-Rollout (M6) und eine
  AC-COMPAT-Lücke im Matching-Pfad (M7).

Nach Behebung von C1 und M1–M7 (bzw. bewusster, dokumentierter Entscheidung zu M4/M5/M7)
ist das Konzept an `requirements`/`se-requirements` übergebbar.
