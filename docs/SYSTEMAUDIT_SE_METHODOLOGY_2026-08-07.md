# Systemaudit: SE-Methodik von ReqogniLoom

**Datum:** 2026-08-07
**Auditor:** `se-consultant` (NASA SE Handbook / NPR 7123.1 als Bezugsrahmen)
**Prüfgegenstand:** ReqogniLoom als Produkt — Datenmodell, REST-API, MCP-Server, SE-Auditor,
Workflow-Engine, Baseline-/CM-Schicht, Frontend-Struktur
**Prüfmethode:** Code-Audit + **Live-Erprobung gegen die laufende Instanz** (Docker-Stack,
`localhost:8000`). Alle Verhaltensaussagen sind durch reale API-/MCP-Calls oder
Datei:Zeile-Zitate belegt.
**Testdaten:** Drei dedizierte Audit-Workspaces (minimal/standard/extended) wurden angelegt,
um den Dogfooding-Bestand nicht zu verunreinigen. Der temporäre API-Key wurde nach Abschluss
widerrufen (`DELETE /api/v1/api-keys/...` → 204).

| Audit-Workspace | ID | Preset |
|---|---|---|
| SE-AUDIT-2026-08-07-standard | `e3dcc02e-2562-4b19-85a0-5602deaaa851` | standard |
| SE-AUDIT-2026-08-07-minimal | `87d051f7-a876-4767-898a-3b9b84f86ef0` | minimal |
| SE-AUDIT-2026-08-07-extended | `c1c3b90e-a182-473d-bea0-26c51ed3c9bb` | extended |

---

## 1. Executive Verdict

**ReqogniLoom ist ein methodisch ernstzunehmendes SE-Werkzeug mit einem exzellenten linken
V-Ast und einer teilweise exzellenten, teilweise strukturell defekten rechten Seite. Es ist
aktuell NICHT vertrauenswürdig als Entscheidungsgrundlage, weil seine zentralen
Aggregations- und Konfigurationsmanagement-Sichten — SE-Metrik-Dashboard und Baseline-Diff —
nachweislich falsche Werte liefern, und zwar in die beruhigende Richtung.**

Das ist keine diplomatische Formulierung, sondern eine präzise: Die *Durchsetzungslogik*
(Enforcement) ist an mehreren Stellen besser als bei den meisten kommerziellen RM-Tools. Die
*Berichtslogik* (Reporting) ist an drei Stellen schlicht falsch. Ein Werkzeug, dessen Gates
korrekt sperren, dessen Dashboards aber Entwarnung geben, ist gefährlicher als eines, das
beides nicht kann — weil der Systems Engineer dem grünen Kachelwert glaubt.

### Was methodisch echt ist (belastbar nachgewiesen)

1. **Der SE-Auditor ist kein Feigenblatt.** 12 Regeln, preset-gemappt, mit echter
   BLOCKER-Semantik. Er hat meine absichtlich kaputte Kette gefunden (10 Blocker) und meine
   saubere Kette durchgelassen (0 Blocker).
2. **Baseline-Erzeugung ist SE-gegated.** Eine Baseline über einen als kaputt erkannten
   Trace-Graphen wird abgelehnt. Das ist ein echter Konfigurationskontrollpunkt und in dieser
   Form selten.
3. **`implemented → verified` ist an tatsächliche Testausführung gekoppelt.** Kein
   Verifikations-Theater auf diesem Pfad — der Übergang wurde abgelehnt, solange der TestRun
   `Not Run` war, und erst nach einem `passed`-Ergebnis akzeptiert.
4. **SE-Link-Semantik wird endpunkt-typgeprüft.** `Requirement --verifies--> Requirement` wird
   mit einer fachlich korrekten Fehlermeldung abgewiesen.
5. **CCB-Funktionstrennung ist real.** Selbstgenehmigung wird bei `extended` mit 403 abgelehnt.
6. **I5-Wurzelinvariante** (genau ein Root-ArchitectureElement) wird durchgesetzt.
7. **Row-Level-Security** ist echt (DB-Ebene, nicht nur ORM-Filter).

### Was strukturell fehlt oder falsch ist

1. **MOE/MOP/TPM existieren überhaupt nicht** — nicht als Feld, nicht als Entität, nicht als
   rekonstruierbares Muster. Die gesamte quantitative Führungsgröße des NASA-SE fehlt.
2. **Das SE-Metrik-Dashboard meldet nachweislich Null statt der Wahrheit** (Coverage und
   Risiken), Ursache: RLS-Bruch in einem ThreadPoolExecutor.
3. **Der Baseline-Diff meldet „keine Änderung" für real geänderte Artefakte.** Ursache: Diff
   schlüsselt auf `Artifact.version`, die bei Fachdatenänderungen nie hochzählt.
4. **`verification_method` wird bei jedem unbeteiligten PATCH still gelöscht.** Empirisch:
   2731 von 2735 Requirements haben keine Verifikationsmethode.
5. **Risiken sind nicht verlinkbar** — kein Trade-Study-Support.
6. **Die V-Modell-Ebene `level` ist über REST und MCP weder schreib- noch lesbar.** L3/L4
   existieren im gesamten Bestand null Mal.

**Gesamtreifegrad pro Achse:**

| Achse | Note | Begründung (Kurzform) |
|---|---|---|
| **A. Requirements** | ⚠️ **Mittel** | Syntax/Rationale nicht erzwungen; `level` nicht befüllbar; AC/VM optional und flüchtig |
| **B. Architektur & Schnittstellen** | ✅ **Gut** | Baumintegrität erzwungen, ICDs vorhanden, Semantikprüfung greift |
| **C. V&V** | ⚠️ **Gespalten** | Verifikations-Gate exzellent; Validierung (Goals) default-aus; Coverage-Reporting defekt |
| **D. Lifecycle & Review-Gates** | ✅ **Gut, mit CM-Loch** | Echte State-Machine + CCB-SoD; aber Baseline sperrt Artefakte nicht und Diff ist blind |

---

## 2. Befunde pro Fähigkeit

Severity-Skala: **S1** = untergräbt die SE-Kernaussage des Tools · **S2** = schwerwiegende
methodische Lücke · **S3** = relevante Schwäche · **S4** = Hinweis.

---

### 2.1 MOE / MOP / TPM — Measures of Effectiveness / Performance / Technical Performance

**Verdikt: VOLLSTÄNDIG ABWESEND. Nicht einmal als Freitextfeld, das sich verstellt. (S1)**

**Wie geprüft.** Volltextsuche über den gesamten Backend- und SE-Dokumentationsbaum nach
`moe`, `mop`, `tpm`, `measure_of_effectiveness`, `technical_performance`:

```
grep -rni "moe\b|measures_of_effectiveness|\bmop\b|technical_performance|\btpm\b"
        backend/ docs/se/ --include=*.py --include=*.md
→ 0 Treffer
```

Danach Prüfung, ob sich das Konzept mit vorhandenen Mitteln nachbilden ließe.

**Was beobachtet wurde.**

- Kein Artefakttyp, kein Feld, keine Entität für MOE/MOP/TPM. Die Artefakt-Typen im Bestand
  sind ausschließlich: `Requirement`, `ArchitectureElement`, `StakeholderNeed`, `Issue`,
  `TestCase:System`, `Risk`, `Adr`, `TestCase:Unit`, `Goal`, `MainGoal`.
- **Custom Fields taugen als Ersatz nicht.** `CustomFieldType`
  (`backend/persistence/models.py:276-288`) kennt exakt drei Typen: `text`, `number`,
  `dropdown`. Ein TPM benötigt mindestens: Ist-Wert, Zielwert, Schwellwert, Marge, Einheit,
  Messzeitpunkt und einen Zeitverlauf. Ein einzelnes `number`-Feld liefert einen Skalar ohne
  Einheit, ohne Ziel, ohne Toleranzband und ohne Historie. Die klassische
  TPM-Verlaufsdarstellung (z. B. Massenmarge gegen Allokation über die Zeit) ist damit nicht
  darstellbar.
- **Über MCP nicht einmal anlegbar:** die Tool-Gruppe `custom_field` hat ausschließlich
  `custom_field.get` und `custom_field.query` — beide read-only. Ein AI-Agent kann kein
  Custom Field definieren.

**Wichtige Abgrenzung — was fälschlich für TPM gehalten werden könnte.** Es gibt
`backend/se_metrics/` mit `ThresholdConfig` und einem Dashboard mit Schwellwerten
(`warning`/`critical`). Das sind jedoch **Prozessmetriken** (Trace-Coverage-Prozent,
Requirement-Volatilität, Workflow-Lücken), nicht **Produkt-Leistungsgrößen**. Sie messen die
Qualität der Requirements-Arbeit, nicht die technische Leistung des entwickelten Systems. Ein
Systems Engineer, der hier TPM-Tracking vermutet, wird in die Irre geführt.

**Lücke.** Die gesamte quantitative Steuerungsebene des NASA-SE fehlt: keine MOEs zur
Stakeholder-Zielmessung, keine MOPs zur Systemleistungsmessung, kein TPM-Tracking mit Marge
und Trend, folglich auch keine Grundlage für Trade Studies und keine „technische
Leistungsbilanz" über den Projektverlauf.

**Empfehlung.** Eigene Entität `Measure` mit `kind ∈ {MOE, MOP, TPM}`, `unit`, `target_value`,
`threshold`, `current_value`, `measured_at` sowie einer Zeitreihe; verlinkbar an
`Goal`/`StakeholderNeed` (MOE), `Requirement` (MOP) und `ArchitectureElement` (TPM). Ohne
eigene Entität nicht sinnvoll nachrüstbar.

---

### 2.2 V-Modell-Traceability L0–L4 — können Lücken sich verstecken?

**Verdikt: JA, und zwar auf drei unabhängigen Wegen. (S1)**

#### Befund 2.2.a — `Requirement.level` ist über keine API befüllbar (S2)

Das Feld existiert im Modell (`backend/persistence/models.py:863-871`, „V-model hierarchy
level (0=System … 4=Material), NULL until assigned explicitly"), ist aber weder in
`RequirementSerializer` noch im MCP-Schema enthalten.

Live-Nachweis — `level` und `uid` wurden gesendet, die Antwort war 201, beide Werte fehlen:

```
POST /api/v1/requirements/ {"title":"LEVEL PROBE","level":1,"uid":"PROBE-LVL",
                            "verification_method":"Test","acceptance_criteria":"AC"}
→ 201, Response enthält KEIN Feld "level", "uid": null
```

Bestätigung in der Datenbank:

```sql
SELECT title, level, uid, verification_method FROM pl_requirement WHERE title='LEVEL PROBE';
 LEVEL PROBE | (null) | (null) | Test
```

Folge im realen Bestand:

```sql
SELECT level, count(*) FROM pl_requirement GROUP BY level;
 0 → 92 | 1 → 277 | 2 → 369 | NULL → 1997
SELECT count(*) FROM pl_requirement WHERE level IN (3,4);  → 0
```

**1997 von 2735 Requirements (73 %) haben keine V-Modell-Ebene, und L3/L4 existieren im
gesamten Bestand kein einziges Mal** — obwohl „V-Modell-Traceability L0-L4" ein beworbenes
Kernmerkmal ist. Die Ebene wird ausschließlich durch Import-/Seed-Pfade gesetzt, nicht durch
die produktiven Schnittstellen.

#### Befund 2.2.b — Zwei konkurrierende Hierarchie-Semantiken; der Auditor sieht nur eine (S1)

Die Hierarchie wird im Datenbestand über `derives-from` ausgedrückt (1825 Links). Die
Struktur-Klassifikatoren des SE-Auditors betrachten aber ausschließlich
`decomposes`/`parent-child`:

```python
# backend/traceability/audit/rules/trace_derivation_allocation.py:83-85
# (identisch nochmals in rules/coverage_consistency.py:94-96)
_DECOMPOSITION_LINK_TYPES: FrozenSet[str] = frozenset(
    {LinkType.DECOMPOSES.value, LinkType.PARENT_CHILD.value}
)
```

`_root_requirement_ids` (`trace_derivation_allocation.py:140-157`) und
`_leaf_requirement_ids` (`coverage_consistency.py:187-203`) filtern beide auf diese Menge.
Im Bestand: **1825 `derives-from` gegen 11 `decomposes`** — praktisch der gesamte Graph ist
für die Root-/Leaf-Klassifikation unsichtbar.

Live-Nachweis im Audit-Workspace `extended`: Ich habe `r2 --derives-from--> r1` und
`r1 --derives-from--> need` angelegt, also eine korrekte Kette. Der Auditor meldete dennoch:

```
VERIF-P8 blocker: Leaf Requirement 'REQ-EXT-L1-001 Zustandsanzeige' has no verifying TestCase
TRACE-P1 blocker: Root Requirement 'REQ-EXT-L2-001 Polling' has no 'derives-from' link to a StakeholderNeed
```

Beides ist sachlich falsch: `r1` ist kein Blatt (es hat `r2` als Kind), und `r2` ist keine
Wurzel (es leitet von `r1` ab). Erst nachdem ich zusätzlich einen `decomposes`-Link
`r1 → r2` gesetzt hatte, ging der Auditor auf 0 Blocker.

**Praktische Auswirkung, gemessen am realen Dogfooding-Workspace „Demo Workspace"
(872 Requirements, 135 `derives-from`, 1 `decomposes`):**

```
GET /api/v1/workspaces/6d20f0b9-.../audit/
→ tier=extended, counts={'total': 3343, 'blockers': 3343, 'warnings': 0}
   VERIF-P8: 859 | TRACE-P2: 861 | TRACE-P1: 822 | TRACE-P1b: 731 | TRACE-P3: 64 | …
```

**3343 Blocker.** Faktisch wird jedes Requirement gleichzeitig als Wurzel *und* als Blatt
fehlklassifiziert. Zwei Konsequenzen: (1) Alarmmüdigkeit — 3343 Blocker sind nicht
abarbeitbar und werden ignoriert, womit der Auditor als Instrument entwertet ist; (2) die
Baseline-Erzeugung ist in diesem Workspace **dauerhaft blockiert**, weil das Gate auf genau
diesen Blockern aufsetzt (siehe 2.4). Das Konfigurationsmanagement ist damit in der Praxis
nicht benutzbar.

#### Befund 2.2.c — Zwei Coverage-Pfade mit unterschiedlicher Strenge (S3)

`CoverageCalculator.coverage()` prüft ausschließlich Zieltyp und Linktyp, **nicht den
Quelltyp**:

```sql
-- backend/traceability/coverage_calculator.py:313-319
SELECT DISTINCT target_id FROM pl_tracelink
WHERE target_id IN (...) AND link_type = %s AND tenant_id = %s
```

Damit zählt *jedes* Artefakt, das per `verifies` auf ein Requirement zeigt, als Testabdeckung.
Der Semantik-Gate fängt das für Kerntypen ab, hat aber eine dokumentierte Ausnahme:

```python
# backend/traceability/types.py:142-144
# Permissive default: non-core artifact types are never constrained.
if src not in SE_CORE_ARTIFACT_TYPES or tgt not in SE_CORE_ARTIFACT_TYPES:
    return None
```

Live-Nachweis: Ein **ADR** darf ein Requirement „verifizieren":

```
POST /api/v1/tracelinks/ {source=Adr, target=REQ-AUDIT-BAD-001, link_type="verifies"}
→ 201  source_type: "Adr", target_type: "Requirement"
```

**Entwarnung mit Einschränkung:** Der VCRM-Pfad `get_coverage_data()` schneidet zusätzlich
gegen echte TestCase-IDs (`coverage_calculator.py:209`) und meldete korrekt eine Lücke:

```
MCP context.test_coverage {requirement_id: REQ-AUDIT-BAD-001}
→ {"test_cases": [], "gaps": ["01e50d9f-..."]}
```

Der Kennzahlpfad `coverage()` hat diese Absicherung nicht. Beide Pfade können daher für
denselben Workspace abweichende Zahlen liefern — der eine ist gegen gefälschte Verifizierer
robust, der andere nicht.

#### Befund 2.2.d — `baseline_id` bei Coverage wird stillschweigend ignoriert (S2)

```python
# backend/traceability/coverage_calculator.py:152-154
ADR-L3-TE3-03: baseline_id triggers reading from Baseline snapshot
(currently uses live data; baseline snapshot integration is a
future extension — the parameter is accepted and forwarded).
```

Ein Aufruf „Coverage gegen Baseline X" liefert **Live-Daten** statt des Baseline-Stands, ohne
Fehler und ohne Hinweis. Das ist genau die Klasse Fehler, die einen Systems Engineer über den
Zustand seines Systems täuscht: Er glaubt, den eingefrorenen Stand zu prüfen, sieht aber den
aktuellen.

---

### 2.3 Baselines & Konfigurationskontrolle

**Verdikt: Snapshots sind echt. Der Diff ist blind. Baselines sperren nichts. (S1)**

#### Befund 2.3.a — Snapshots sind substanziell (Positiv)

Baselines schreiben echte Zustandskopien, keine Zeiger. Nachgewiesen in
`bl_delta_index_entry`: 7 Einträge pro Audit-Baseline, 1294 für eine große Bestands-Baseline,
jeweils mit vollem `state`-JSON.

#### Befund 2.3.b — Der Baseline-Diff meldet Null-Änderung für real geänderte Artefakte (S1)

**Testablauf (Workspace `extended`):**

1. Baseline `BL-EXT-1` (`2c6747b6-...`) erzeugt — 201.
2. Requirement `REQ-EXT-L1-001` geändert: Titel *und* `acceptance_criteria` — 200,
   `version` 1 → 2.
3. Baseline `BL-EXT-3` (`abd936ab-...`) erzeugt — 201.
4. Diff angefordert.

**Ergebnis:**

```
GET /api/v1/baselines/diff/?baseline_a=2c6747b6-...&baseline_b=abd936ab-...&workspace_id=...
→ 200
{"summary": {"added": 0, "removed": 0, "changed": 0}, "items": []}
```

**Die beiden Baselines enthalten nachweislich verschiedene Zustände für dasselbe Item:**

```sql
SELECT baseline_id, item_id, version, state->>'title', state->>'verification_method'
FROM bl_delta_index_entry WHERE item_id='2056745f-3f56-4591-b10b-ace64d72ceb0';

2c6747b6… | 1 | REQ-EXT-L1-001 Zustandsanzeige        | Test
abd936ab… | 1 | REQ-EXT-L1-001 CHANGED AFTER BASELINE | (null)
```

**Ursache, exakt lokalisiert.** Der DiffEngine klassifiziert über Versionsnummern:

```python
# backend/baseline/diff_engine.py:35, 75, 94-95
#   3. Build dict-backed index sets: {item_id: version}.
#   … Same item, same version → not in any category (unchanged)
```

Der Feld-Level-Diff (Zeile 97-102) läuft **nur für bereits als geändert klassifizierte IDs**.
Die im Index gespeicherte Version stammt jedoch aus `Artifact.version`, nicht aus
`Requirement.version`:

```sql
SELECT version FROM pl_artifact    WHERE id='2056745f-…';  → 1
SELECT version FROM pl_requirement WHERE id='fccbe88c-…';  → 2
```

`pl_artifact.version` bleibt bei Fachdatenänderungen auf 1 stehen. Damit gilt für **jede**
inhaltliche Requirement-Änderung: gleiche Version ⇒ „unverändert" ⇒ Feld-Diff wird nie
ausgeführt ⇒ Drift ist unsichtbar.

Das ist der schwerwiegendste CM-Befund: Die Kernfrage des Konfigurationsmanagements — „Was hat
sich seit der letzten Baseline geändert?" — wird mit „nichts" beantwortet, obwohl sich etwas
geändert hat.

#### Befund 2.3.c — Baselines snapshotten die Akzeptanzkriterien nicht (S2)

Erfasste Felder pro Requirement-Eintrag (`jsonb_object_keys(state)`):

```
uid, type, title, status, suspect, version, category, description,
artifact_type, verification_method, complexity_fibonacci
```

**Nicht enthalten: `acceptance_criteria`, `level`, `rationale`.** Eine Baseline, die die
Akzeptanzkriterien nicht einfriert, kann nicht als Verifikationsreferenz dienen — genau das
ist aber ihr Zweck. Man kann später nicht mehr rekonstruieren, *wogegen* damals verifiziert
wurde.

#### Befund 2.3.d — Baselines sperren Artefakte nicht (S2)

Nach Erzeugung von `BL-EXT-1` war das baselinierte Requirement frei editierbar:

```
PATCH /api/v1/requirements/fccbe88c-… {"title":"… CHANGED AFTER BASELINE",
                                       "acceptance_criteria":"<=99s DEGRADED",
                                       "change_reason":"audit drift probe"}
→ 200, version 1 → 2
```

Kein ChangeRequest, keine CCB-Genehmigung, keine Warnung. Bei `extended` wird immerhin ein
`change_reason` erzwungen (ohne diesen: 400 „change_reason required by workspace preset
policy") — das ist eine Begründungspflicht, aber kein Freigabegate. Nach NASA-CM muss eine
Änderung an einem baselinierten Konfigurationselement über das CCB laufen. Hier ist die
Baseline ein Foto, kein Schloss.

Zusammen mit 2.3.b ergibt das die gefährlichste Kombination: **Änderung ungebremst möglich,
Drift-Erkennung defekt.**

#### Befund 2.3.e — Das SE-Gate der Baseline fällt bei internen Fehlern offen (S2)

```python
# backend/application/baseline_facade.py:191-200
except Exception:  # noqa: BLE001
    # Fail open on an auditor malfunction: an internal error in the
    # gate must not make baselining impossible workspace-wide.
    logger.exception("BaselineFacade: SE-Auditor gate failed …; allowing the baseline build")
    return
```

Bei jedem internen Auditor-Fehler wird die Baseline **trotzdem** erzeugt — nur ein Logeintrag
bleibt. Für ein Governance-Gate ist „fail open" die falsche Voreinstellung. Dass solche
Ausnahmen real auftreten, zeigt Befund 2.5.a. Mindestens müsste am Baseline-Objekt vermerkt
werden, dass das Gate nicht ausgewertet wurde.

#### Befund 2.3.f — Zwei API-Ergonomie-Fallen (S3)

- `GET /api/v1/baselines/{id}/` liefert **`entries: []`**, obwohl die Create-Antwort die
  Einträge enthielt und die DB 7 Einträge führt. Der Snapshot ist über die Detail-Route nicht
  lesbar.
- `GET /api/v1/baselines/diff/` gibt **404 ohne `workspace_id`**, obwohl die Route
  `baseline_a`/`baseline_b` erwartet. Ursache: `self._check_preset(request)` wird ohne
  Workspace-Bezug aufgerufen (`backend/rest_api/views.py`, `diff`-Action, vgl. die
  `list`-Action, die `workspace_id` korrekt durchreicht). Der Endpunkt wirkt tot, bis man
  einen undokumentierten Zusatzparameter mitgibt.

---

### 2.4 Verifikation vs. Validierung

**Verdikt: Verifikation ist vorbildlich durchgesetzt. Validierung ist praktisch nicht
vorhanden. (S2)**

#### Befund 2.4.a — Das Verifikations-Gate ist echt (Positiv, hervorzuheben)

Der Workflow bietet keine Sprünge an — nur Nachbarübergänge:

```
GET /api/v1/requirements/{id}/transitions/
→ current_state: draft
  states: [draft, in_review, approved, implemented, verified, deprecated]
  allowed_transitions: [{target_state: in_review, requires_change_reason: true,
                         signature_gate: false}]
```

Der Übergang nach `verified` wurde **abgelehnt**, solange kein bestandener Testlauf vorlag:

```
POST …/transitions/ {"target_state":"verified"}
→ 400 "Cannot mark this Requirement as verified: the latest test run of the following
       verifying TestCase(s) is not 'Passed': b5d6710f-… (Not Run)."
```

Nach Meldung eines bestandenen Ergebnisses über MCP:

```
MCP test.run_report_results {run_id: 00a608bb-…, results:[{status:"passed"}]} → 200
POST …/transitions/ {"target_state":"verified"} → 200, previous_state: implemented,
                                                        new_state: verified
```

Das ist die sauberste Umsetzung der Verifikationskette, die ich in diesem System gefunden
habe. Sie schließt „Verifikations-Theater" auf dem Requirement-Status wirksam aus.

#### Befund 2.4.b — Validierung („das richtige System?") ist standardmäßig abgeschaltet (S2)

Die Validierungsebene sind `Goal`/`MainGoal`. Diese sind per Default deaktiviert
(`Workspace.goals_enabled = False`, `backend/persistence/models.py`):

```
POST /api/v1/goals/ {workspace_id: <extended-WS>, title:"GOAL-AUDIT-01"}
→ 403 "Goals are not enabled for workspace c1c3b90e-…"
```

Im gesamten Bestand: **4 Goals und 2 MainGoals** gegenüber 2735 Requirements. Es gibt keine
Auditregel, die Validierung gegen Stakeholder-Ziele einfordert, und keine Off-Nominal-/
Fehlerfall-Kategorie für Requirements oder TestCases. Das System kann damit die Frage „Haben
wir das richtige System gebaut?" strukturell nicht beantworten — es beantwortet ausschließlich
„Haben wir das System richtig gebaut?".

#### Befund 2.4.c — Der 4-Phasen-TestRun-Lifecycle lässt sich nicht abschließen (S3)

Der TestRun bleibt dauerhaft in `in_progress`:

```
GET /api/v1/test-runs/00a608bb-…/
→ status: "in_progress", finished_at: None,
  result_summary: {total: 2, passed: 1, failed: 0, blocked: 0, not_run: 1}
```

Es existiert weder ein REST-Endpunkt (`/complete/` → 404, `/finish/` → 404) noch ein
MCP-Tool zum Abschluss — die Gruppe `test.*` umfasst `run_create`, `run_get`,
`run_report_results`, aber kein `run_complete`. Der beworbene Lifecycle
`created → in_progress → completed/failed → archived` endet faktisch nach Phase 2.

Zusätzlich: `test.run_report_results` **ergänzt** eine zweite Ergebniszeile für denselben
TestCase, statt die bestehende zu aktualisieren — sichtbar an `total: 2` bei nur einem
TestCase, mit gleichzeitig `not_run` und `passed`. Die Zusammenfassung eines Laufs ist damit
nicht eindeutig interpretierbar.

#### Befund 2.4.d — Zwei Auditregeln sind dauerhaft wirkungslos (S3)

`CONS-P9` (offener Konflikt blockiert Freigabe) und `CONS-P10` (keine hängenden
SUPERCEDES-Referenzen) sind im Standard-Regelsatz gelistet
(`registry.py:72-82`), liefern aber konstruktionsbedingt nie Befunde:

```python
# backend/traceability/audit/rules/coverage_consistency.py:325-330, 357-362
deferred_reason = ("LinkType.CONFLICTS_WITH is not a member of traceability.types.LinkType …")
def check(self, context): return []
```

Von den 7 Regeln des Standard-Presets sind damit 2 strukturelle Leerläufer. Der Regelkatalog
suggeriert mehr Prüfumfang als tatsächlich stattfindet.

---

### 2.5 Risikomanagement

**Verdikt: Eine gute Risiko-Entität, vollständig vom Rest des Systems abgekoppelt — und im
Dashboard unsichtbar. (S1)**

#### Befund 2.5.a — Das Dashboard meldet null Risiken, obwohl Risiken existieren (S1)

Ich habe im `extended`-Workspace genau ein Risiko hoher Schwere angelegt:

```
POST /api/v1/risks/ {"title":"RISK-AUDIT-01 Polling overload","probability":"high",
                     "impact":"high","mitigation_strategy":"throttle"}
→ 201  risk_score: 9, rpn: 45, severity: "high"
```

Das Dashboard desselben Workspace:

```
GET /api/v1/metrics/?workspace_id=c1c3b90e-…
→ open_risks: {"total": 0, "by_severity": {"critical":0,"high":0,"medium":0,"low":0}}
GET /api/v1/risks/?workspace_id=c1c3b90e-…
→ 1 Risiko: ("RISK-AUDIT-01 Polling overload", "high")
```

**Ursache — ein verschluckter TypeError**, aus den Backend-Logs:

```
WARNING se_metrics.aggregator: MetricsAggregator: IF-L1-047 risk query failed for ws=…
Traceback: File "/app/se_metrics/aggregator.py", line 251, in _fetch_risks
    ctx = AuthContext(
TypeError: AuthContext.__init__() missing 1 required positional argument: 'auth_method'
```

Der Aufruf ist schlicht defekt; der umgebende `except Exception: return []` verwandelt den
Absturz in „keine Risiken". Das Frontend rendert diesen Wert als Kachel mit
`direction: "higher-bad"` und `thresholds: {warning: 5, critical: 15}`
(`frontend/src/components/MetricsDashboard/MetricsDashboard.tsx:82-90`) — **0 liegt unter
jedem Schwellwert, die Kachel ist also dauerhaft grün.** Das ist ein lupenreines False-Green:
Der Systems Engineer liest „keine offenen Risiken", während hohe Risiken erfasst sind.

#### Befund 2.5.b — Risiken sind nicht verlinkbar (S1)

Trace-Links auf ein Risiko schlagen unabhängig vom Linktyp fehl:

```
POST /api/v1/tracelinks/ {source_id: <Risk>, target_id: <Requirement>, link_type:"traces"}
→ 404 {"code":"NOT_FOUND","message":"Entity dff6e2de-… not found"}
   (ebenso für "documents" und "implements")
```

**Ursache.** Der Entity-Resolver in `backend/application/trace_link_service.py:118-166`
unterstützt exakt: `Artifact`, `Requirement`, `ArchitectureElement`, `Adr`, `Goal`,
`MainGoal`, `TestCase`, `StakeholderNeed` — und wirft danach
`NotFoundError(f"Entity {entity_id} not found")` (Zeile 166). **`Risk` und `Issue` fehlen**,
obwohl beide ein `artifact`-OneToOneField besitzen (`backend/application/models.py:322` für
`Risk`) und technisch verlinkbar wären.

**Methodische Folge.** Ein Risiko kann keinem Requirement, keinem Architekturelement und
keiner Mitigation zugeordnet werden. Damit entfällt: risikobasierte Verifikationspriorisierung,
Trade-Study-Unterstützung, Nachweis, dass eine Mitigation als Requirement implementiert wurde,
und jede Impact-Analyse „welche Risiken hängen an dieser Komponente?". Das Risk Register ist
eine isolierte Liste — im NASA-Sinn kein Risikomanagement, sondern eine Risikosammlung.

Positiv anzumerken: Die Entität selbst ist gut modelliert — `probability`, `impact`,
`detection`, berechneter `risk_score` (9) und `rpn` (45, FMEA-Logik). Die Substanz ist da; die
Verdrahtung fehlt.

---

### 2.6 Change Control / CCB

**Verdikt: Gut umgesetzt und korrekt rigor-gestaffelt — aber ohne Verbindung zur Baseline. (S2)**

#### Befund 2.6.a — Funktionstrennung wird durchgesetzt (Positiv)

```
POST /api/v1/change-requests/{id}/transition/ {"target_status":"approved"}  (als Ersteller)
→ 403 "Separation of duties: the requestor of a change request must not decide it
       (target status 'approved'). A different CCB member with the 'approver' role has to act."
```

Implementierung: `backend/application/change_request_service.py:571-625`, ausdrücklich mit
Bezug auf ISO 15288 §6.4.3. Zwei Regeln (Selbstgenehmigung; fremder Reviewer ohne
Admin-Rolle), beide nur auf `approved`/`rejected`. Die Beschränkung auf `extended`
(Feature-Flag `approval_workflows`) ist dokumentiert und methodisch vertretbar — bei minimaler
Rigorosität wäre eine erzwungene Vier-Augen-Regel eher hinderlich als sicher.

#### Befund 2.6.b — Der ChangeRequest gattet keine Artefaktänderung (S2)

Der CCB-Workflow existiert *neben* der Artefaktbearbeitung, nicht *davor*. Wie in 2.3.d
gezeigt, ist ein baseliniertes Requirement ohne jeden ChangeRequest editierbar. Es gibt keine
Prüfung „dieses Artefakt ist Teil einer Baseline ⇒ Änderung nur über genehmigten CR". Damit
ist die Änderungssteuerung ein paralleler Dokumentationsprozess, den man auch weglassen kann —
das Gegenteil eines Gates.

---

### 2.7 Review-Gates / Lifecycle-Disziplin

**Verdikt: Deutlich mehr als ein Kanban-Board mit SE-Etiketten. Der schwächste Punkt ist die
fehlende Meilenstein-Ebene. (S3)**

**Positiv, live nachgewiesen:**

- Echte State-Machine mit Nachbarschaftsbeschränkung; ein Sprung `draft → verified` wurde mit
  400 abgelehnt.
- Pro Übergang gepflegte Gate-Metadaten: `requires_change_reason` und `signature_gate`
  (letzteres implementiert in `backend/workflow/signature_gate.py`, 231 Zeilen).
- Vorbedingungsregeln greifen inhaltlich (Testlauf-Kopplung, 2.4.a) — implementiert in
  `backend/workflow/precondition_rules.py`.
- Preset-Staffelung ist strukturell garantiert: `RULE_PRESET_MAP["minimal"] = frozenset()`
  mit Import-Zeit-Assertion (`registry.py:113`) und einer Override-Sperre, die „Minimal" auch
  per Django-Setting nicht scharf schalten lässt (`registry.py:143-144`). Das ist saubere,
  bewusste Rigor-Architektur.
- Preset-Wirksamkeit empirisch bestätigt: identische Datenlage, `minimal` → 0 Befunde,
  `standard` → 15 Befunde (10 Blocker), `extended` → zusätzliche SE-Regeln (VERIF-P8 feuerte
  nur dort). **„Extended" erzwingt tatsächlich mehr, nicht nur mehr UI-Felder.**

**Lücke (S3).** Es gibt Zustände *pro Artefakt*, aber keine **projektweiten
Meilenstein-Gates** im Sinne von SRR/PDR/CDR. Ein SRR ist die Aussage „der gesamte
Requirements-Satz ist zu diesem Zeitpunkt reif" — nicht die Summe einzelner
`approved`-Requirements. Die Baseline ist der nächstliegende Kandidat dafür, trägt aber keinen
Meilenstein-Typ und keine Review-Semantik. Ein Reifegrad-Nachweis auf Projektebene ist damit
nicht führbar.

---

### 2.8 Requirements-Qualität (Achse A)

**Verdikt: Das Datenmodell erlaubt Requirements, die kein SE-Review bestehen würden. (S2)**

#### Befund 2.8.a — Nichts Wesentliches ist Pflicht

Bei `standard`-Rigorosität akzeptiert:

```
POST /api/v1/requirements/ {"workspace_id":…, "title":"REQ-AUDIT-BAD-001 System soll
                            schnell und robust sein"}
→ 201  description:"", acceptance_criteria:"", verification_method:null, uid:null
```

Ein unverifizierbares Requirement („schnell und robust") ohne Beschreibung, ohne
Akzeptanzkriterium, ohne Verifikationsmethode und ohne Rationale wird anstandslos angelegt.
Es gibt zudem **kein `rationale`-Feld** im Modell — die NASA-Forderung, festzuhalten *warum*
ein Requirement existiert und auf welchen Annahmen es beruht, ist nicht abbildbar
(`change_reason` dokumentiert Änderungen, nicht die Existenzbegründung).

Bestandsweite Auswirkung:

```sql
SELECT count(*) FROM pl_requirement WHERE coalesce(acceptance_criteria,'')='';  → 2729 / 2735
```

#### Befund 2.8.b — `verification_method` wird bei jedem unbeteiligten PATCH still gelöscht (S1)

**Reproduktion, isoliert:**

```
POST /api/v1/requirements/ {"title":"VM-WIPE-PROBE","acceptance_criteria":"AC",
                            "verification_method":"Analysis"}
→ 201  verification_method: "Analysis"

PATCH /api/v1/requirements/{id}/ {"title":"VM-WIPE-PROBE renamed","change_reason":"probe"}
→ 200  verification_method: None
       acceptance_criteria: 'AC'   (erhalten)
       description: 'd'            (erhalten)
```

Eine reine Titeländerung löscht die Verifikationsmethode. `acceptance_criteria` und
`description` überleben — der Verlust trifft gezielt die typabhängig gerenderten Felder
(`verification_method`, `complexity_fibonacci`), die in
`RequirementSerializer.to_representation` bei `type != 'SyReq'` entfernt werden
(`backend/rest_api/serializers.py`, Bereich der `to_representation`-Logik) und deren Abwesenheit
im Update-Pfad als „auf NULL setzen" interpretiert wird.

Bestandsweite Auswirkung:

```sql
SELECT verification_method, count(*) FROM pl_requirement GROUP BY 1;
 (null) → 2731 | Test → 4
```

**4 von 2735 Requirements haben eine Verifikationsmethode.** Die Verifikationsplanung des
linken V-Astes ist damit faktisch nicht existent, und der Grund ist kein Disziplinproblem der
Nutzer, sondern ein stiller Datenverlust im Tool. Das ist zugleich der Befund mit dem
höchsten Täuschungspotenzial: Der Ingenieur *hat* die Methode gesetzt und sie verschwindet
ohne jede Rückmeldung.

---

### 2.9 SE-Metrik-Dashboard — der zentrale False-Green

**Verdikt: Die Sicht, auf die ein Systems Engineer zuerst schaut, ist auf zwei von fünf
Kacheln nachweislich falsch. (S1)**

**Beobachtung am realen Dogfooding-Workspace „Demo Workspace" (872 Requirements):**

```
GET /api/v1/metrics/?workspace_id=6d20f0b9-d2cf-46a0-b916-79f8b417210f
→ traceability_coverage: {"total": 0, "covered": 0, "coverage_percent": 0.0,
                          "uncovered_ids": []}
```

**Die Wahrheit, direkt aus demselben Rechenkern ermittelt:**

```python
# ohne DB-Session-GUC (das erlebt der Worker-Thread):
CoverageCalculator().coverage(WS)  → total 0,   covered 0, pct 0.0
# mit gesetztem app.current_tenant (das erlebt der Request-Thread):
CoverageCalculator().coverage(WS)  → total 872, covered 2, pct 0.2,  870 uncovered
```

**Ursache, präzise.** `MetricsAggregator.compute` fächert vier Quellabfragen auf:

```python
# backend/se_metrics/aggregator.py:330-334
with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as executor:
    future_audit    = executor.submit(_fetch_audit_entries, …)
    future_coverage = executor.submit(_fetch_coverage, workspace_id, tenant_id)
    future_gaps     = executor.submit(_fetch_incomplete_states, …)
    future_risks    = executor.submit(_fetch_risks, …)
```

Jede Worker-Funktion setzt zwar den Python-Thread-Local (`TenantContext.set_tenant(tenant_id)`,
`aggregator.py:131`) — aber **nicht** die Postgres-Session-Variable. Diese wird ausschließlich
in der Request-Middleware gesetzt:

```python
# backend/persistence/middleware.py:47
cursor.execute("SET app.current_tenant = %s", [str(tenant_id)])
```

Ein Worker-Thread erhält eine **eigene DB-Verbindung ohne `app.current_tenant`**. Die
RLS-Policies filtern daraufhin jede mandantenbezogene Tabelle auf null Zeilen. `coverage()`
rechnet dann völlig korrekt `0/0` — es gibt keine Exception und keine Warnung, deshalb ist der
Fehler bisher unentdeckt geblieben.

**Warum das ein False-Green ist.** Das Frontend rendert ausschließlich den Prozentwert
(`MetricsDashboard.tsx:57`, `value: (m) => m.traceability_coverage.coverage_percent`) — die
Zähler `total`/`covered` erscheinen nicht in der Kachel. Der Ingenieur kann nicht unterscheiden
zwischen „0 % abgedeckt" und „nichts gemessen". Und die parallel betroffene Risiko-Kachel
(2.5.a) steht bei 0 auf Grün. In Summe: **870 verdeckte Verifikationslücken und ein hohes
Risiko, die auf dem Dashboard nicht vorkommen.**

**Warum die Testsuite das nicht gefunden hat.** Der zugehörige E2E-Test prüft ausschließlich
Sichtbarkeit, nie Werte:

```typescript
// e2e/tests/metrics-dashboard.spec.ts:25-28
const coverageTile = page.locator('[data-testid="metric-tile-coverage"]');
await expect(coverageTile).toBeVisible({ timeout: 10000 });
await expect(page.locator('[data-testid="metric-tile-volatility"]')).toBeVisible();
```

Der Unit-Test arbeitet mit gemocktem `coverage_percent: 85.5`
(`MetricsDashboard.test.tsx:34`) und kann die Aggregation daher ebenfalls nicht prüfen. Es gibt
keinen Test, der eine bekannte Datenlage anlegt und den berechneten Wert verifiziert.

---

### 2.10 MCP-Oberfläche für den vollständigen SE-Lebenszyklus

**Verdikt: 143 Tools in 26 Gruppen, aber der AI-Agent kann SE-tragende Felder nicht setzen und
Kernfragen nicht stellen. (S1)**

#### Befund 2.10.a — `requirement.create` verschluckt SE-Felder still (S1)

Schema laut `docs/agent-templates/tool-manifest.json` — nur vier Eigenschaften:

```json
"requirement.create": {"properties": {"workspace_id":…, "title":…,
                                      "description":…, "category":…},
                       "required": ["workspace_id","title"]}
```

Live-Verhalten — gesendet wurden zusätzlich `acceptance_criteria`, `verification_method`,
`level`, `type`:

```
MCP requirement.create {workspace_id, title:"MCP FIELD PROBE", description:"d",
                        acceptance_criteria:"AC via MCP", verification_method:"Test",
                        level:1, type:"SyReq"}
→ 200 {"requirement": {"id":"0462046c-…","title":"MCP FIELD PROBE","description":"d",
                       "category":"","status":"draft","version":1,…}}
```

Datenbank-Kontrolle:

```sql
SELECT title, level, verification_method, acceptance_criteria FROM pl_requirement
WHERE title='MCP FIELD PROBE';
 MCP FIELD PROBE | (null) | (leer) | (leer)
```

**Kein Fehler, keine Warnung, HTTP 200.** Ein AI-Agent, der eine Verifikationsmethode setzt,
erhält eine Erfolgsmeldung und hat nichts gesetzt. Für ein Produkt, dessen Kernversprechen
„AI-nativ" ist, ist stilles Feld-Verwerfen der schwerwiegendste denkbare Schnittstellenfehler:
Der Agent hat keine Möglichkeit, den Verlust zu bemerken, und wird nachgelagert falsche
Schlüsse ziehen.

#### Befund 2.10.b — Fehlende Tools für den SE-Lebenszyklus (S2)

Konkret fehlend, nicht „wünschenswert":

| Fehlendes Tool | Warum SE-tragend |
|---|---|
| `traceability.coverage` | Es gibt **kein** MCP-Tool für workspace-weite Abdeckung. `context.test_coverage` beantwortet nur *ein* Requirement. Ein Agent kann „Wie ist der V&V-Stand?" nicht beantworten. |
| `traceability.matrix` / VCRM-Export | Der VCRM-Generator existiert (`vcrm_report_generator.py`, 330 Zeilen), ist über MCP nicht erreichbar. |
| `audit.se_audit` (Auditor-Lauf) | `audit.query` ist Audit-**Log**, `audit.ai_review` bündelt nur. Ein Agent kann die SE-Konformität nicht direkt prüfen. |
| `test.run_complete` | TestRuns sind nicht abschließbar (2.4.c). |
| `requirement.set_level` bzw. `level` im Schema | V-Modell-Ebene über MCP nicht setzbar. |
| `custom_field.create` | Nur `get`/`query` — Agent kann kein Feld definieren (relevant als MOE/MOP-Notbehelf). |
| `risk.link` | Risiken sind nicht verknüpfbar (2.5.b). |
| Measure-/TPM-Tools | Entität fehlt (2.1). |

#### Befund 2.10.c — Dokumentation nennt vier nicht existierende Linktypen (S2)

`CLAUDE.md` und `.claude/rules/mcp-reqogniloom.md` beschreiben „8 Trace-Link-Typen
(TRACE_TO, DERIVED_FROM, IMPLEMENTS, TESTS, VERIFIES, RELATED_TO, CONFLICTS_WITH,
SUPERCEDES)". Der tatsächliche Enum (`backend/traceability/types.py:25-59`) hat 15 Mitglieder,
darunter **weder `TESTS` noch `RELATED_TO` noch `CONFLICTS_WITH` noch `SUPERCEDES`**.
Live bestätigt:

```
POST /api/v1/tracelinks/ {link_type:"conflicts-with"} → 400
POST … {"supercedes"} → 400   POST … {"tests"} → 400   POST … {"related-to"} → 400
Valid types: [allocated-to, copy-of, decides, decomposes, derives-from, diagram-ref,
              documents, implements, parent-child, realizes, refines, satisfies,
              traces, uses-term, verifies]
```

Methodisch schmerzt vor allem das Fehlen von `CONFLICTS_WITH` (Anforderungskonflikte
dokumentieren — Grundlage jeder Trade Study) und `SUPERCEDES` (Ablösung von
ADRs/Requirements). Genau diese beiden Lücken sind auch der Grund für die zwei toten
Auditregeln aus 2.4.d. Ein Agent, der der Dokumentation folgt, baut vier fehlerhafte Aufrufe.

#### Befund 2.10.d — `preset` als JSONField, das nur Strings akzeptiert (S4)

`WorkspaceSerializer` deklariert `preset = serializers.JSONField(...)`
(`backend/rest_api/serializers.py:969`); das dokumentierte Objektformat wird abgelehnt:

```
POST /api/v1/workspaces/ {"preset": {"tier":"standard"}}
→ 400 "Invalid preset '{'tier': 'standard'}'. Valid: ['extended','minimal','standard']"
POST /api/v1/workspaces/ {"preset": "standard"}
→ 201, preset: {"tier":"standard","terminology_profile":"se_mode","language":"de",…}
```

Eingabe Skalar, Ausgabe Objekt — für Agenten eine unnötige Stolperfalle.

---

## 3. Priorisierte Maßnahmenliste

Sortiert danach, wie stark der Punkt das Vertrauen in die SE-Aussagen des Werkzeugs
untergräbt.

### Priorität 1 — Das Werkzeug lügt derzeit über den Systemzustand

1. **RLS-Kontext in die Worker-Threads des MetricsAggregator durchreichen.**
   `backend/se_metrics/aggregator.py:330-334`. Jede Worker-Funktion muss neben
   `TenantContext.set_tenant()` auch `SET app.current_tenant` auf *ihrer* Verbindung setzen
   (oder der Aggregator läuft sequenziell auf der Request-Verbindung). Ohne diesen Fix ist
   jede Aussage des SE-Dashboards wertlos. — *Behebt 2.9.*
2. **`_fetch_risks` reparieren** (`aggregator.py:251`, fehlendes `auth_method`) **und die
   `except Exception`-Blöcke im Aggregator so ändern, dass ein Fehlschlag als „unbekannt"
   statt als „0" ausgewiesen wird.** Eine grüne Kachel aufgrund einer verschluckten Exception
   ist der gefährlichste Zustand des Systems. — *Behebt 2.5.a.*
3. **`verification_method` beim PATCH nicht mehr löschen.** Partielle Updates dürfen nicht
   übermittelte Felder nicht nullen. Anschließend Datenbereinigung prüfen — 2731 Requirements
   haben den Wert möglicherweise nie freiwillig verloren. — *Behebt 2.8.b.*
4. **Baseline-Diff auf Inhalt statt auf `Artifact.version` umstellen.** Entweder
   `Artifact.version` bei Änderungen der Fachentität mitziehen oder — robuster — den
   Feld-Level-Diff unabhängig von der Versionsklassifikation über alle gemeinsamen Items
   laufen lassen (`backend/baseline/diff_engine.py:75-102`). — *Behebt 2.3.b.*
5. **Stilles Feld-Verwerfen an der MCP-Grenze beenden.** Unbekannte Properties müssen zu einem
   Fehler führen (`additionalProperties: false`), und `requirement.create`/`update` müssen
   `acceptance_criteria`, `verification_method`, `level`, `type` aufnehmen. — *Behebt 2.10.a.*

### Priorität 2 — Load-bearing SE-Konzepte fehlen oder sind abgekoppelt

6. **`Risk` und `Issue` in den TraceLink-Entity-Resolver aufnehmen**
   (`backend/application/trace_link_service.py:118-166`). Einzeiliger Charakter, große
   Wirkung: macht risikobasierte Verifikation und Trade Studies überhaupt erst möglich.
   — *Behebt 2.5.b.*
7. **Hierarchie-Semantik vereinheitlichen.** Entweder `derives-from` in
   `_DECOMPOSITION_LINK_TYPES` aufnehmen oder eine Migration auf `decomposes` fahren. Solange
   1825 `derives-from` gegen 11 `decomposes` stehen, produziert der Auditor 3343 unbrauchbare
   Blocker und blockiert das Konfigurationsmanagement vollständig. — *Behebt 2.2.b.*
8. **`LinkType` um `CONFLICTS_WITH` und `SUPERCEDES` erweitern**, danach `CONS-P9`/`CONS-P10`
   aktivieren und die Dokumentation auf die tatsächliche Typenliste korrigieren.
   — *Behebt 2.4.d und 2.10.c.*
9. **`acceptance_criteria`, `level` und ein neues `rationale` in den Baseline-State aufnehmen.**
   Eine Baseline ohne Akzeptanzkriterien ist als Verifikationsreferenz untauglich.
   — *Behebt 2.3.c und 2.8.a.*
10. **`Requirement.level` in Serializer und MCP-Schema exponieren**, mit Konsistenzprüfung
    gegen die Elternebene (kein Sprung L1 → L3). — *Behebt 2.2.a.*

### Priorität 3 — Governance schließen

11. **Baseline-Mitgliedschaft an das Change Control koppeln:** Änderung eines baselinierten
    Artefakts nur über einen genehmigten ChangeRequest, mindestens aber mit deutlicher
    Drift-Kennzeichnung am Artefakt. — *Behebt 2.3.d und 2.6.b.*
12. **`baseline_id` in `coverage()`/`get_coverage_data()` implementieren oder den Parameter
    ablehnen.** Ein stillschweigend ignorierter Baseline-Bezug ist schlimmer als ein
    fehlender. — *Behebt 2.2.d.*
13. **SE-Gate der Baseline nicht mehr „fail open"** — oder mindestens am Baseline-Objekt
    persistieren, dass das Gate nicht ausgewertet werden konnte
    (`baseline_facade.py:191-200`). — *Behebt 2.3.e.*
14. **`test.run_complete` ergänzen** und `run_report_results` auf Upsert statt Append
    umstellen. — *Behebt 2.4.c.*
15. **Quelltyp-Prüfung in `_get_covered_artifact_ids`** (`coverage_calculator.py:313-319`),
    damit der Kennzahlpfad dieselbe Strenge hat wie der VCRM-Pfad. — *Behebt 2.2.c.*
16. **Baseline-Detailroute muss `entries` liefern; `baselines/diff/` darf `workspace_id` nicht
    verdeckt voraussetzen.** — *Behebt 2.3.f.*

### Priorität 4 — Fehlende Konzeptebenen

17. **`Measure`-Entität für MOE/MOP/TPM** einführen (Ausgestaltung siehe 2.1). Ohne sie bleibt
    ReqogniLoom ein Requirements-Tracking-Werkzeug und wird kein SE-Steuerungswerkzeug.
18. **Projekt-Meilensteine (SRR/PDR/CDR)** als eigene Ebene über den Artefaktzuständen —
    naheliegend als typisierte Baseline mit Review-Semantik. — *Behebt 2.7.*
19. **Validierungsebene aktivieren:** `Goals` per Default an, plus eine Auditregel „jedes
    L0-Need trägt zu mindestens einem Goal bei" und eine Off-Nominal-Kategorie für
    TestCases. — *Behebt 2.4.b.*
20. **Pflichtfelder je Rigor-Stufe:** ab `standard` `acceptance_criteria` und
    `verification_method` verpflichtend; `rationale`-Feld ergänzen. — *Behebt 2.8.a.*

### Priorität 5 — Testlücke, die all das durchgelassen hat

21. **Semantische Assertions für das Metrik-Dashboard.** Der bestehende E2E-Test prüft nur
    Sichtbarkeit (`metrics-dashboard.spec.ts:25-28`), der Unit-Test mockt den Wert. Nötig ist
    ein Integrationstest, der eine bekannte Datenlage anlegt (N Requirements, M abgedeckt,
    K Risiken) und die berechneten Werte prüft. Genau diese Lücke hat drei S1-Befunde
    unentdeckt gelassen.

---

## 4. Was nicht verifiziert werden konnte (für den `e2e-tester`-Nachlauf)

Mir standen keine Browser-Werkzeuge zur Verfügung. Die folgenden Punkte wurden **aus
Komponenten- und Spec-Code erschlossen, nicht beobachtet** — sie sind explizit als offen zu
behandeln:

1. **Darstellung der Coverage-Kachel bei `total=0`.** Aus `MetricsDashboard.tsx:51-59`
   abgeleitet: gerendert wird `coverage_percent.toFixed(1)` mit `direction: "lower-bad"` und
   `thresholds {warning: 80, critical: 50}` ⇒ 0.0 % müsste als „critical" erscheinen. **Zu
   prüfen:** Sieht der Nutzer eine rote Kachel „0.0 %" ohne Hinweis darauf, dass gar nichts
   gemessen wurde? Wird irgendwo `total`/`covered` angezeigt?
2. **Darstellung der Risiko-Kachel.** Aus `MetricsDashboard.tsx:82-90` abgeleitet: `total: 0`
   mit `warning: 5` ⇒ grün. **Zu prüfen:** Erscheint die Kachel tatsächlich grün/unauffällig,
   während im Risiko-Modul ein hohes Risiko gelistet ist? Das ist der visuelle Kern des
   False-Green-Vorwurfs und sollte per Screenshot belegt werden.
3. **`BaselinesView`** — ob der Diff-Nullbefund in der UI als „keine Änderungen" dargestellt
   wird und ob die UI den `workspace_id`-Parameter mitsendet (der REST-Aufruf 404t ohne ihn).
   Ich habe nur den API-Layer geprüft.
4. **`TraceabilityView`** — ob Orphans/Lücken visuell hervorgehoben werden oder ob eine
   unvollständige Kette wie eine vollständige aussieht.
5. **`RequirementEditors`** — ob das Formular `acceptance_criteria`/`verification_method` als
   Pflichtfelder kennzeichnet und ob der PATCH-Wipe (2.8.b) auch über die UI auftritt (die UI
   sendet womöglich alle Felder und ist dadurch zufällig immun — das wäre wichtig zu wissen,
   weil es den Blast Radius eingrenzt).
6. **Ob `level` (V-Modell-Ebene) irgendwo in der UI setzbar ist.** Über REST und MCP ist es das
   nicht; ein abweichender UI-Pfad würde erklären, wie die 738 gesetzten Werte entstanden sind.
7. **SE-Auditor-Ansicht bei 3343 Befunden** — Verhalten und Bedienbarkeit unter dieser
   Befundlast (Paginierung, Ladezeit, Gruppierung).
8. Nicht geprüft, weil außerhalb des Auftrags: ICD-Modul, Diagramm-Reconciler, ReqIF-Import,
   PDF-Export, Vector-Search.

---

## 5. Schlussbemerkung

Die SE-Substanz dieses Werkzeugs ist überdurchschnittlich. Der Regelkatalog des SE-Auditors,
das testlauf-gekoppelte Verifikations-Gate, die strukturell garantierte Preset-Staffelung und
die ISO-15288-begründete Funktionstrennung sind Arbeiten, die man in kommerziellen
RM-Werkzeugen selten in dieser Klarheit findet. Die Autoren verstehen Systems Engineering.

Der Schaden entsteht an anderer Stelle: an den Aggregations- und Vergleichspfaden, wo Fehler
nicht als Fehler auftreten, sondern als Null. Ein verschluckter `TypeError` wird zu „keine
Risiken". Ein fehlender Session-Parameter wird zu „0 von 0 Requirements". Eine nie
hochgezählte Versionsnummer wird zu „keine Änderungen seit der Baseline". In allen drei Fällen
zeigt das Werkzeug einen ruhigen Zustand an, wo Handlungsbedarf besteht — und in allen drei
Fällen ist der Nutzer strukturell außerstande, den Irrtum zu bemerken.

Die vordringliche Aufgabe ist deshalb nicht, neue SE-Konzepte zu ergänzen — das ist Priorität
4 —, sondern die bestehenden dazu zu bringen, die Wahrheit zu sagen. Solange Punkt 1 bis 5
offen sind, sollte das SE-Metrik-Dashboard als Entscheidungsgrundlage nicht verwendet und der
Baseline-Diff nicht als Nachweis der Änderungsfreiheit akzeptiert werden.

---

*Erstellt von `se-consultant`. Alle Live-Belege stammen aus Aufrufen gegen die laufende
Instanz am 2026-08-07 zwischen 17:56 und 18:25 UTC. Die drei Audit-Workspaces bleiben zur
Nachvollziehbarkeit bestehen und können nach Abarbeitung gelöscht werden.*
