# reqmd — Interop-Brücke und Konzept-Lehren

> **Kein Implementierungsplan.** Dieses Dokument enthält keine `- [ ]`-Tasks. Es beantwortet
> zwei Fragen: **(1)** Wie sähe eine zweiseitige Brücke zwischen ReqogniLoom und
> [`dVoo/reqmd`](https://github.com/dVoo/reqmd) konkret aus, und **(2)** welche
> Konstruktionsideen aus reqmd sind für ReqogniLoom selbst wertvoll — unabhängig davon, ob
> die Brücke je gebaut wird. Ergebnis ist ein v1-Zuschnitt, sieben bewertete Konzepte mit
> Adopt/Adapt/Reject-Empfehlung und die offenen Punkte aus §9.
>
> **Alle Ist-Aussagen über ReqogniLoom sind gegen den Quellcode auf
> `feat/mcp-plugin-distribution`, Stand 2026-08-08, verifiziert** und mit `Datei:Zeile`
> belegt. Aussagen über reqmd stammen aus dessen README/Dokumentation, nicht aus dessen
> Go-Quellcode, und sind als solche zu behandeln.

**Kernbefund vorweg.** reqmd ist kein Traceability-Hilfswerkzeug, sondern ein
funktionsgleicher Konkurrent im selben Problemraum — mit Ebenen-Hierarchie, typisierten
Attributen, Schema-Validierung pro Ebene, Regel-Engine, Baseline-Diff und V&V-Ergebnis-
Einspeisung. Genau deshalb ist der Vergleich unbequem: **an vier Stellen ist reqmds Modell
nachweislich strenger als ReqogniLooms**, obwohl ReqogniLoom das schwerere, formalere
Werkzeug sein will.

1. **Ein Requirement gilt in ReqogniLoom als abgedeckt, wenn *irgendein* TestCase-Datensatz
   darauf zeigt — unabhängig davon, ob dieser Test je gelaufen ist oder ob er fehlschlägt.**
   `coverage_calculator.py:60` („ADR-L3-TE3-01: Only `verifies` links count"), und die
   SE-Auditor-Regel VERIF-P8 prüft ausschließlich Link-*Existenz*
   (`traceability/audit/rules/coverage_consistency.py:299`). reqmds `--results` macht genau
   daraus einen `failing-verdict`-Fehler. **Das ist die schwerwiegendste Lücke im ganzen
   Dokument.**
2. **CI kann Testergebnisse nur einspeisen, wenn sie ReqogniLooms interne UUIDs kennt.**
   `TestRunService.add_results_bulk` verlangt `test_case_id` (`test_run_service.py:263-266`),
   ebenso das MCP-Schema (`mcp_server/tools/tests.py:235`). Es gibt keinen Standardformat-
   Import. reqmd liest CTRF, das viele Runner ohnehin ausgeben, ohne eine Zeile
   Integrationscode.
3. **ReqogniLoom hat keine Inhalts-Revisionsnummer.** `AuditableModel.version` ist
   ausdrücklich „a **pure optimistic-concurrency counter** … not a content revision number"
   (`persistence/models.py:305-322`, #213). Deshalb kann ein Trace-Link nicht festhalten,
   *gegen welchen Stand* er geprüft wurde — reqmds `trace: [SYS-001~3]` kann genau das. Der
   Ersatz, das `suspect`-Flag, ist ein Boolean, wird nie automatisch zurückgesetzt und
   feuert auf jede Speicherung.
4. **Der Baseline-Diff klassifiziert über einen Zähler statt über Inhalt** — und genau
   deshalb existiert GH #398 („reports zero change for genuinely changed artifacts",
   `diff_engine.py:35`, `:75`). reqmd vergleicht zwei Git-Tags inhaltlich und ist gegen
   diese Fehlerklasse *strukturell* immun.

Die Brücke selbst ist demgegenüber der einfachere Teil: reqmds typisierte `attr`-Blöcke
mappen weitgehend 1:1 auf `Requirement`, und der Importer sieht dem ReqIF-Importer sehr
ähnlich — nicht einem Prosa-Parser.

---

## 0. reqmd auf zwei Seiten

Referenzrahmen. Quelle: README/Doku des Projekts.

### 0.1 Dokumentformat

```markdown
## IVI-FUN-001: Fast startup
​```attr
status: approved
asil: QM
maturity: Production
verify: Test
owner: TierOneSupplierA
trace: [SYS-001, SAFE-003]
version: 1
​```
The system shall display the home screen within 5 seconds after ignition on,
provided the head unit is operational.
```

- ID-Format `^[A-Z][A-Z0-9]*(-[A-Z0-9]+)*$`, endend auf eine Zahl; optional `: Titel`.
- Der Prosa-Body nach dem `attr`-Block ist die Anforderung.

### 0.2 Reservierte Attribute

| Attribut | Bedeutung |
|---|---|
| `trace` | ref[] — Upstream-Referenzen über Dokumentgrenzen |
| `disposition` | `implemented` \| `deferred` \| `rejected` — wie mit der Downstream-Absicht umgegangen wurde |
| `disposition-reason` | Pflicht, sobald `disposition ≠ implemented` |
| `requires-trace-from` | string[] — **deklarative Abdeckungserwartung**: welche Downstream-Ebenen auf dieses Requirement zeigen *müssen* |
| `version` | int — **inhaltliche** Revisionsnummer, menschlich gepflegt |
| `status` | Default `approved`; **nur `approved` zählt als gültiger Upstream-Abdeckungsgeber** |
| `reqmd-suppress` | Liste von Check-IDs, die für *dieses* Requirement unterdrückt werden |

Versions-Pinning: `trace: [SYS-001~3]` merkt sich, gegen welchen Upstream-Stand geprüft
wurde. `pin < upstream.version` → ERROR („outdated", per `--relaxed-versions` zu WARNING
degradierbar), `pin > upstream.version` → ERROR („predated", nie automatisch reparierbar).
`reqmd repin` zieht Pins nach.

### 0.3 Schema pro Verzeichnis

```yaml
x-reqmd:
  level: software-requirements
  id-prefix: IVI-FUN-
  upstream:
    level: system-requirements
    sources: [../sys/]
  mandatory-disposition: true
  external: true
  additional-status-values: [review, in-progress]
  ignore-status: true

$schema: "https://json-schema.org/draft/2020-12/schema"
type: object
required: [asil, maturity, status, verify]
properties:
  status: {type: string, enum: [draft, approved]}
  asil:   {type: string, enum: [QM, A, B, C, D]}
additionalProperties: false
```

**Jede Ebene definiert ihre eigenen Pflichtfelder und ihren eigenen Upstream-Zeiger.** Das
ist die direkte Entsprechung zu ReqogniLooms V-Modell L0–L4 — nur mit Konfigurierbarkeit
pro Ebene statt pro Workspace (§8.4).

### 0.4 CLI und Regel-Engine

`check` (mit `--json`, `--results`, `--relaxed-versions`, `--filter`, `--disjoint-check`),
`init` (Presets `generic`/`aspice`/`results`), `ls`, `stats`, `export csv|html|graph`,
`serve`, `baseline diff <tag1> <tag2>`, `repin`. Exit-Codes: 0 gültig, 1 Validierungsfehler,
2 Parse-Fehler.

Regelfamilien: gebrochene Referenz (WARNING), Zyklus via DFS (ERROR),
`requires-trace-from` nicht erfüllt (WARNING), untraced/kein Upstream **mit
Randerkennung** (Verzeichnisse ohne `upstream.sources` sind obere Grenze; Verzeichnisse, auf
die niemand zeigt, untere Grenze — Falschmeldungen an den Rändern werden automatisch
unterdrückt), Disposition ohne Grund, fehlende Pflicht-Disposition, ID-Präfix-Verstoß,
Duplikat-ID, mehrdeutige unqualifizierte Referenz, Versions-Pin veraltet/vorgezogen,
fehlender/fehlgeschlagener Verdict (mit `--results`).

### 0.5 V&V-Ergebnis-Einspeisung

`reqmd check spec/ --results ci-out/ --results reviews/` lädt **ephemere** Ergebnisse (nie
ins Spec-Repo zurückgeschrieben) aus zwei Quellen:

1. **CTRF** (Common Test Report Format, offener JSON-Standard) — Verzeichnis wird nach
   `*.ctrf.json` durchsucht; `tests[].extra["x-reqmd.id"]` bindet ein Testergebnis an eine
   Requirement-ID; Status-Mapping `passed→pass`, `failed→fail`, `skipped→skipped`,
   `flaky:true→inconclusive`.
2. **Manuelle Review-Ergebnisse** als eigene Markdown+Schema-Dokumente (`outcome`,
   `verifier`, `verified-at`, `trace`) — für Inspektions-/Review-Verifikationsmethoden.

Beide speisen dieselben `missing-verdict`/`failing-verdict`-Prüfungen.

### 0.6 Designprinzipien

Kein Lock-in (Markdown+YAML, git-diffbar) · keine Datenbank (der Trace-Graph ist ephemer und
wird pro Aufruf neu gebaut, die `.md`-Dateien sind die einzige Wahrheit) · Schemata pro
Verzeichnis · Parallelisierung über Worker-Pool · Dogfooding (233 eigene Requirements über
6 V-Modell-Ebenen in `spec/`, vom Werkzeug selbst validiert).

---

# Teil 1 — Import/Export-Brücke

## 1. Bestandsaufnahme (verifiziert)

### 1.1 Das Requirement-Datenmodell

`persistence.Requirement` (`persistence/models.py:818`):

| Feld | Zeile | reqmd-Gegenstück |
|---|---|---|
| `title` | `:848` | `## <ID>: <Titel>` — `CharField(max_length=500)`, harte Grenze |
| `description` | `:849` | Prosa-Body |
| `acceptance_criteria` | `:850` | kein Standardattribut — eigenes Schema-Feld nötig |
| `category` | `:855` | eigenes Schema-Feld |
| `status` | `:856` | `status` — **aber**: Workflow-Spiegel, nie direkt schreibbar (REQ-143) |
| `type` | `:857` | eigenes Schema-Feld (`RequirementType`) |
| `level` | `:863` | `x-reqmd.level` — **`NULL` für praktisch alle** über `decompose()` erzeugten Zeilen |
| `verification_method` | `:878` | `verify` — direkte Entsprechung |
| `complexity_fibonacci` | `:872` | eigenes Schema-Feld |
| `uid` | `:885` | die reqmd-ID — **client-vergeben, keine Auto-Generierung** |
| `suspect` | `:891` | kein Gegenstück; reqmds Äquivalent ist der Versions-Pin (§8.2) |
| `version` | `AuditableModel:305-322` | **kein** Gegenstück — Lock-Zähler, nicht Revision (§8.2) |

Zwei Detailbefunde mit direkter Entwurfsfolge:

- **`uid` ist optional und frei** (kein Generator; `RequirementService` prüft nur
  Eindeutigkeit, `application/requirement_service.py:138`). reqmds ID-Regex ist deutlich
  enger.
- **DB-erzwungene `uid`-Eindeutigkeit gibt es nur bei `Requirement`**:
  `uq_requirement_workspace_uid` (`persistence/models.py:959-963`, partiell über
  `~Q(uid=None) & ~Q(uid="")`, #133). `ArchitectureElement` (`:1017`) und `TestCase`
  (`:1320`) haben ein `uid`-Feld ohne Constraint und ohne Anwendungsprüfung (Metas `:1034`,
  `:1343`). Für einen `uid`-basierten Upsert ist das der begrenzende Faktor (§7.2, §9.6).

### 1.2 Trace-Links

`persistence.TraceLink` (`:1225-1250`): `source` FK, `target` FK, `link_type`, `embedding`.
**Sonst nichts** — keine Version, kein Pin, kein Prüfzeitpunkt, kein
Disposition-Feld. Unique `(source, target, link_type)` (`:1275`).
`traceability/types.py::LinkType` hat 16 Werte; `SE_LINK_SEMANTICS` (`:110ff`) beschränkt in
`se_mode` die zulässigen Endpunkttypen.

### 1.3 Präzedenzfall ReqIF — das Muster, dem die Brücke folgt

`application/reqif_import_service.py` (865 Zeilen) ist der einzige echte Fremdformat-Importer
und beantwortet jede Frage, die auch ein reqmd-Importer stellt:

- **Upsert zweistufig**: primär die im Export codierte Artefakt-UUID (`_<uuid>`,
  `_parse_artifact_uuid`, `:219`), **sekundär die fachliche `uid` im Workspace** (`:624-630`).
  Die zweite Stufe wurde nachgerüstet, weil ein Reimport in einen anderen Workspace mit der
  UUID-Stufe nie traf und bei jedem Lauf Duplikate erzeugte (`:617-623`). **Für reqmd ist nur
  die zweite Stufe anwendbar.**
- **`status` nie als Feld schreiben**: `_apply_status` (`:701-749`) reproduziert
  `workflow/migrations/0003_reconcile_status_mirror._map_status` wortgleich und legt einen
  `WorkflowItemState` an, falls eine `WorkflowEngineDefinition` existiert. `import_service.py:55`
  importiert dieselbe Funktion — sie ist bereits geteilt.
- **Harte vs. weiche Fehler**: Dokumentfehler → `ValidationError`, nichts wird geschrieben;
  Einzelobjektfehler → `_SoftError` im eigenen Savepoint (`:397-422`), überspringen und
  melden.
- **`dry_run` fährt die *ganze* Pipeline und rollt am äußeren Rand zurück** (`:454-459`) —
  kein zweiter Codepfad.
- **Unbekannte Attribute → `Artifact.custom_fields`**, explizit durch
  `validate_custom_fields` geschleust, weil `save(update_fields=…)` keine Validatoren
  ausführt (`:580-592`).
- **Report-DTO** `created/updated/skipped/errors` je Art plus `warnings` (`:239-288`).
- **Nur REST**, kein MCP: `rest_api/urls.py:199` / `:205`; `ReqifImportView`
  (`rest_api/views.py:5850ff`) nimmt `multipart/form-data`, Feld `file`, `?dry_run=`.

### 1.4 Präzedenzfall CSV

`export_service.py` und `import_service.py` teilen sich eine Feld-Registry
`ENTITY_FIELD_SPECS` (`export_service.py:101`), damit beide Richtungen nicht driften —
inklusive Identitätsspalten für einen verlustfreien Round-Trip.

### 1.5 `export_markdown` existiert und ist unerreichbar

`ExportService.export_markdown` (`application/export_service.py:378-436`) ist implementiert
und im Vertrag `IF-AS-EXT-IN-001` geführt — hat aber **keinen Aufrufer**: `rest_api/urls.py`
bietet nur `export/csv/` (`:193`) und `export/reqif/` (`:199`), `mcp_server/` bietet gar
keine Export-/Import-Werkzeuge. Die Ausgabe ist zudem eine Feldliste (`**key:** value`,
`:417-424`), kein Dokument. **Ein reqmd-Exporter ersetzt diese Methode; sie ist nicht die
Grundlage, sondern der Vorgänger.**

### 1.6 Negative Befunde

| Frage | Antwort | Beleg |
|---|---|---|
| Gibt es eine CLI? | **Nein.** `StdioTransportAdapter` ist definiert und wird nirgends instanziiert | `mcp_server/protocol_handler.py:261` |
| Gibt es eine VCS-Abhängigkeit? | **Nein.** Kein Git-Client in den Dependencies | `backend/requirements.txt` |
| Gibt es eingehende Webhooks? | **Nein.** `WebhookSubscription` ist rein ausgehend | `application/models.py:115` |
| Gibt es Standardformat-Import für Testergebnisse? | **Nein** (§8.1) | `application/test_run_service.py:226` |
| Gibt es eine Regel-Unterdrückung pro Artefakt? | **Nein** (§8.6) | Suche über `traceability/audit/` |

---

## 2. Mapping-Analyse

### 2.1 Was direkt abbildbar ist

| reqmd | ReqogniLoom | Bemerkung |
|---|---|---|
| ID + `## <ID>: <Titel>` | `uid` + `title` | verlustfrei, wenn `uid` reqmd-ID-tauglich (§3.3) |
| Prosa-Body | `description` | verlustfrei |
| `verify` | `verification_method` (`:878`) | Wertemenge muss ins Schema-`enum` |
| `status` | `status` (Workflow-Spiegel) | über `x-reqmd.additional-status-values` (§3.4) |
| `trace` | `derives-from` / `satisfies` TraceLinks | Richtung: Kind → Eltern, wie in ReqogniLoom |
| `x-reqmd.level` | Verzeichnisebene, aus dem Artefakttyp/der Graphtiefe abgeleitet | `Requirement.level` ist meist NULL (§2.3) |
| Beliebige Schema-Felder | `category`, `type`, `complexity_fibonacci`, `custom_fields` | ReqogniLoom generiert das `schema.yaml` aus dem eigenen Feldbestand |

### 2.2 Was nur mit Konvention abbildbar ist

- **`acceptance_criteria`** — kein reqmd-Standardattribut. Lösung: als eigenes Schema-Feld
  `acceptance-criteria` (string) im generierten `schema.yaml` deklarieren. reqmd validiert
  es dann als gewöhnliches Attribut. Sauber, weil das Schema von ReqogniLoom kommt.
- **`disposition` / `disposition-reason`** — ReqogniLoom hat kein Gegenstück (der nächste
  Verwandte ist `ChangeRequest`, aber das ist ein Änderungsantrag, kein Vermerk am
  Requirement). Beim Import: in `custom_fields` ablegen und melden. Beim Export: nicht
  erzeugen. Siehe §8.7.
- **`requires-trace-from`** — ReqogniLoom hat keine deklarative Abdeckungserwartung (§8.3).
  Der Exporter *könnte* sie aus dem Rigor-Preset ableiten (etwa: extended → jede L1-Ebene
  verlangt `verifies` von der Testebene). Das ist eine Interpretation, keine Übersetzung, und
  gehört deshalb hinter einen expliziten Schalter.

### 2.3 Was nicht abbildbar ist — und warum das wichtig ist

**`version` und Versions-Pinning.** Das ist der harte Fall, und er ist kein Formatproblem.
`AuditableModel.version` trägt eine ausdrückliche Warnung (`persistence/models.py:305-322`):

> „`version` is a **pure optimistic-concurrency counter** (issue #213). It is *not* a content
> revision number and carries no history … Any save bumps it — including writes that change
> nothing a user would recognise as content."

reqmds `version:` ist genau das Gegenteil: eine menschlich gepflegte Inhaltsrevision, gegen
die `trace: [SYS-001~3]` pinnt. Würde der Exporter `Requirement.version` in das `version:`-
Attribut schreiben, entstünde ein Pin, der bei jeder belanglosen Speicherung des Upstream-
Requirements als „outdated" ERROR feuert — ein Fehlalarmgenerator.

**Entscheidung: v1 exportiert kein `version:` und keine `~N`-Pins.** Das reqmd-Schema wird
so erzeugt, dass `version` nicht in `required` steht. Der Import liest vorhandene Pins,
speichert sie aber nur als Meldung (§4.5). Der eigentliche Fix liegt in §8.2 und ist ein
eigenes Vorhaben.

**Mandant, RBAC, Baselines, Audit-Log, Workflow-Definitionen** — per Design nicht Teil des
Formats. Kein Verlust im Sinne eines Fehlers, aber die Grenze des Round-Trips.

---

## 3. Export: ReqogniLoom → reqmd-Verzeichnisbaum

### 3.1 Struktur

Ein Workspace wird zu einem Verzeichnisbaum, **eine Ebene = ein Verzeichnis = ein
`schema.yaml`**:

```
spec/
  00-needs/          schema.yaml   x-reqmd.level: stakeholder-needs      (kein upstream)
    needs.md
  10-system/         schema.yaml   upstream.sources: [../00-needs/]
    system.md
  20-subsystem/      schema.yaml   upstream.sources: [../10-system/]
  30-component/      schema.yaml   upstream.sources: [../20-subsystem/]
  90-tests/          schema.yaml   upstream.sources: [../10-system/, ../20-subsystem/]
    tests.md
```

Die Ebenenzuordnung kommt **nicht** aus `Requirement.level` — das Feld ist für nahezu jede
real erzeugte Zeile `NULL` (dokumentiert in
`traceability/audit/rules/trace_derivation_allocation.py:14-20`: „`Requirement.level` … is
NULL for practically every Requirement created via the production path"). Der Exporter
benutzt dieselbe Ableitung wie der SE-Auditor: **die dynamische Dekompositionstiefe** —
Wurzel eines `decomposes`/`parent-child`-Teilgraphen = Ebene 1, jedes weitere Kind eine Ebene
tiefer. `StakeholderNeed` ist immer Ebene 0, `TestCase` immer die Testebene. Damit sind
Exporter und Auditor per Konstruktion einig; zwei getrennte Ebenenbegriffe wären eine
Fehlerquelle.

### 3.2 Generiertes `schema.yaml`

Pro Ebene, aus ReqogniLooms eigenem Feldbestand plus dem Rigor-Preset erzeugt:

```yaml
# generated by ReqogniLoom — do not edit; regenerate via export
x-reqmd:
  level: system-requirements
  id-prefix: ""                       # leer, solange uid frei ist (§3.3)
  upstream:
    level: stakeholder-needs
    sources: ["../00-needs/"]
  additional-status-values: [Entwurf, InPruefung, Freigegeben, Archiviert]

$schema: "https://json-schema.org/draft/2020-12/schema"
type: object
required: [status, verify]            # aus presets.registry.mandatory_fields
properties:
  status:              {type: string}
  verify:              {type: string, enum: [Test, Analysis, Inspection, Demonstration]}
  acceptance-criteria: {type: string}
  category:            {type: string}
  req-type:            {type: string, enum: [SyReq, UseCase, FeatureReq]}
  trace:               {type: array, items: {type: string}}
additionalProperties: true
```

- `required` wird aus `presets.registry` abgeleitet
  (`mandatory_fields`, `:154`/`:170`/`:186`), abzüglich der Policy-Felder, die keine
  Entitätsspalten sind (`change_reason`, `traceability_target` —
  `workflow/precondition_rules.py:163-171`).
- `additional-status-values` aus der `WorkflowEngineDefinition` des Workspace, damit reqmd
  die tatsächlich konfigurierten Zustände kennt statt nur `draft`/`approved`.
- `additionalProperties: true`, weil `Artifact.custom_fields` beliebige Schlüssel führt
  (`persistence/models.py:729-744`). `false` würde jeden Workspace mit Custom Fields
  unvalidierbar machen.

### 3.3 IDs

reqmds Regex ist `^[A-Z][A-Z0-9]*(-[A-Z0-9]+)*$`, endend auf eine Zahl. `Requirement.uid`
ist ein freies 64-Zeichen-Feld.

**Regel: `uid` wird verbatim übernommen, wenn es passt; sonst wird das Requirement
übersprungen und gemeldet — es wird nie umgeschrieben.** Eine Sanitisierung erzeugte eine
zweite, nur im Export existierende Identität, die beim Reimport den Originaldatensatz nicht
mehr trifft (`_assert_uid_unique_in_workspace` prüft gegen den unsanitisierten Wert,
`requirement_service.py:138-161`). Das ist derselbe Duplikat-Erzeuger, den
`reqif_import_service.py:617-623` bereits einmal repariert hat.

`id-prefix` bleibt in v1 leer. Es zu setzen, wäre nur sinnvoll, wenn ReqogniLoom selbst
eine Präfix-Konvention erzwingen würde — tut es nicht (§9.6).

### 3.4 Status

`Requirement.status` ist ein Read-only-Spiegel der WorkflowEngine (REQ-143). Der Exporter
schreibt ihn verbatim ins `status:`-Attribut und deklariert die zulässigen Werte über
`additional-status-values`.

**Ein Detail mit Konsequenz:** reqmd wertet nur `status: approved` als gültigen
Upstream-Abdeckungsgeber. ReqogniLooms Freigabezustand heißt je nach Workspace-Sprache und
Workflow anders (`Freigegeben`, `approved`, …). Der Exporter muss daher entweder den
Freigabezustand auf `approved` normalisieren (verlustbehaftet, aber semantisch korrekt) oder
`ignore-status: true` setzen (dann zählt jeder Zustand — reqmds Abdeckungsprüfung wird
schwächer als ReqogniLooms). **Empfehlung: normalisieren, den Originalwert zusätzlich in
einem eigenen Attribut `reqlo-status` mitführen.** Ein Round-Trip liest dann `reqlo-status`
und lässt den Workflow-Zustand unangetastet.

### 3.5 `trace`

Aus `derives-from`- und `satisfies`-TraceLinks, Richtung Kind → Eltern (die in diesem Repo
mehrfach bestätigte Konvention). Rendert die `uid` des Ziels. Ziele ohne `uid` werden
ausgelassen und gemeldet — eine reqmd-Referenz auf eine UUID wäre keine Referenz.

**Ohne `~N`-Pins** (§2.3).

### 3.6 Determinismus

Wie beim ReqIF-Export: ein zweiter Export eines unveränderten Workspace muss byte-identisch
sein, bis auf einen klar markierten Zeitstempel, der über `?stable_header=true`
unterdrückbar ist. Sortierung lexikografisch nach `uid`, nicht nach `created_at` — sonst ist
jeder Diff Rauschen und das CI-Gate aus §8.5 wertlos.

### 3.7 `reqmd check` als unabhängige Zweitmeinung — lohnt sich das?

Die naheliegende Idee: Export nach reqmd, dann `reqmd check` in CI als zweiter,
unabhängiger Validator gegen ReqogniLooms eigenen SE-Auditor laufen lassen.

**Ehrliche Antwort: als Hauptbegründung trägt es nicht, als Nebennutzen ist es echt.**

Redundant, weil ReqogniLoom es bereits hat oder strukturell nicht haben kann:

| reqmd-Check | ReqogniLoom |
|---|---|
| gebrochene Referenz | **strukturell unmöglich** — `TraceLink.source/target` sind FKs mit CASCADE |
| Zyklus (DFS) | `traceability/service.py::detect_cycles`, REST-exponiert |
| untraced / kein Upstream | TRACE-P1 / TRACE-P1b (`trace_derivation_allocation.py`) |
| fehlende Allokation | TRACE-P2 |
| fehlende Verifikation | VERIF-P8 (`coverage_consistency.py`) |
| Duplikat-ID | `uq_requirement_workspace_uid` (`persistence/models.py:959`) |

Echter Zugewinn, weil ReqogniLoom es nicht hat:

- **Randerkennung** (`upstream.sources` leer = obere Grenze; niemand zeigt hierher = untere
  Grenze). ReqogniLooms TRACE-P1b unterscheidet das über die Graphtiefe, hat aber keinen
  *deklarierten* Rand — was bei Teilbeständen zu Falschmeldungen führt.
- **ID-Präfix-Verstoß und mehrdeutige unqualifizierte Referenz** — beides existiert in
  ReqogniLoom nicht, weil es keine Präfix-Konvention gibt (§9.6).
- **Versions-Pin veraltet/vorgezogen** — kein Gegenstück (§8.2).
- **`failing-verdict`** — kein Gegenstück (§8.1). **Das ist der wertvollste Check von allen**,
  und er ist genau der, den ReqogniLoom selbst haben sollte, statt ihn extern zu leihen.

**Fazit:** der Export lohnt sich aus anderen Gründen (§8.5, PR-Sichtbarkeit); die
Zweitmeinung ist ein Bonus. Und wo reqmd echten Mehrwert liefert, ist die richtige Antwort
nicht „reqmd dazustellen", sondern die Regel in ReqogniLoom nachzuziehen.

---

## 4. Import: reqmd-Verzeichnisbaum → ReqogniLoom

Der Importer sieht dem ReqIF-Importer strukturell ähnlich — typisierte Attribute statt
Prosa-Interpretation. Das ist die wichtigste Konsequenz aus der Korrektur des Vorwissens.

### 4.1 Parsing

1. `schema.yaml` je Verzeichnis lesen → `x-reqmd.level` (Zielebene),
   `upstream.sources` (Ebenenkette), `id-prefix`, `required`, `properties`.
   **Das Schema wird als Beschreibung gelesen, nicht durchgesetzt** — reqmd hat schon
   validiert; ReqogniLoom validiert gegen sein *eigenes* Modell und meldet Abweichungen.
   Kein JSON-Schema-Validator im Backend (`requirements.txt` hat keinen), und einen
   einzuführen, um eine Prüfung zu wiederholen, die das Quellwerkzeug bereits gemacht hat,
   ist Aufwand ohne Ertrag.
2. `.md`-Dateien: `##`-Überschriften mit ID (und optionalem `: Titel`), unmittelbar gefolgt
   von einem ```` ```attr ````-Block (YAML) und dem Prosa-Body bis zur nächsten
   `##`-Überschrift.
3. YAML-Parsing: über `yaml.safe_load` — PyYAML ist als transitive Abhängigkeit vorhanden
   (u. a. über `drf-spectacular`), sollte aber für diesen Zweck **explizit in
   `requirements.txt` gepinnt** werden. Sich auf eine transitive Abhängigkeit zu verlassen,
   ist genau die Falle, die `backend/requirements.txt` bei `reqif` bewusst vermeidet.
   `safe_load`, nie `load`.
4. Größenschranken analog `_MAX_DOCUMENT_CHARS` / `_MAX_SPEC_OBJECTS`
   (`reqif_import_service.py:159-162`): harte `ValidationError` vor jedem Schreibzugriff.

### 4.2 Feld-Mapping

```
ID                        -> uid                (Upsert-Schlüssel)
Überschriftentitel         -> title             (fehlt er: erster Satz des Bodys, max. 500)
Prosa-Body                -> description
attr.acceptance-criteria  -> acceptance_criteria
attr.category             -> category
attr.req-type / attr.type -> type               (gegen RequirementType.choices, sonst Default)
attr.verify               -> verification_method (gegen VerificationMethod.choices)
attr.reqlo-status / status-> _apply_status(...) (§4.4)
attr.trace                -> TraceLinks         (§4.5)
alle übrigen attr-Schlüssel-> custom_fields, via validate_custom_fields
```

**Keine Titel-Heuristik über Prosa nötig**, solange die Überschrift eine hat — das ist der
zentrale Unterschied zu einem Prosa-Format. Der Fallback (erster Satz, 500 Zeichen) greift
nur bei `## IVI-FUN-001` ohne Titelteil und muss dann eine Kürzung **melden** (`title` ist
`CharField(max_length=500)`, `persistence/models.py:848`); stille Kürzung ist dieselbe
Fehlerklasse wie #263/#269.

### 4.3 Upsert-Identität und Round-Trip

**Vorgabe: das Muster aus `reqif_import_service` spiegeln, nicht neu erfinden.** Die
UUID-Stufe entfällt (eine reqmd-Datei trägt keine UUID); es bleibt genau die zweite Stufe
(`reqif_import_service.py:624-630`):

```
reqmd-ID -> Requirement.objects.filter(artifact__workspace_id=ws, uid=<id>)
  Treffer      -> UPDATE der gemappten Felder; Artefakt-UUID bleibt stabil
  kein Treffer -> CREATE (neues Artifact + Requirement, uid = <id>)
```

DB-seitig durch `uq_requirement_workspace_uid` (`persistence/models.py:959`) race-frei
abgesichert — **für `Requirement`**. Für `ArchitectureElement`/`TestCase` gäbe es diese
Garantie nicht (§1.1); das ist der Grund, warum v1 beim Import auf Requirements (und
optional StakeholderNeeds) beschränkt bleibt.

Ein Update fasst niemals an: `lifecycle_status`, `suspect`, `level`, `version`, und
TraceLinks außerhalb der in `trace:` genannten. Explizit im Modul-Docstring festhalten.

### 4.4 Status

`_apply_status` aus `reqif_import_service` **importieren, nicht kopieren** —
`import_service.py:55` ist der Präzedenzfall. Vorrang: `attr.reqlo-status` (der
Originalzustand aus §3.4), sonst `attr.status`, sonst leer → Initialzustand. Ein
`WorkflowItemState` wird nur angelegt, wenn eine `WorkflowEngineDefinition` existiert
(`reqif_import_service.py:730-749`).

### 4.5 `trace` → TraceLinks

Anders als bei reqmds ursprünglich angenommenem Codestellen-Modell ist das hier **direkt
abbildbar**: `trace: [SYS-001, SAFE-003]` sind fachliche IDs im selben Import-Lauf.

```
für jede Referenz:
  1. ~N-Pin abtrennen und in unresolved_pins melden (§2.3)
  2. Ziel-uid im selben Workspace auflösen (erst im Import-Lauf, dann in der DB)
  3. link_type aus der Ebenenbeziehung ableiten:
       Requirement -> StakeholderNeed        : derives-from
       Requirement -> Requirement (Upstream) : derives-from
       TestCase    -> Requirement            : verifies
       ArchElement -> Requirement            : implements
  4. get_or_create(tenant, source, target, link_type)  -- idempotent über uq_tracelink_edge
  5. unauflösbares Ziel -> _SoftError, gemeldet, nie ein harter Fehler
```

Schritt 4 ist wörtlich das Muster aus `reqif_import_service.py:839-848`
(`get_or_create`, „so re-importing the same document is idempotent").

Schritt 3 muss `check_se_link_semantics` respektieren (`traceability/types.py`), sonst
scheitert die Erzeugung in `se_mode`-Workspaces. Eine Ebenenbeziehung, für die die Matrix
keinen zulässigen Typ kennt, ist ein weicher Fehler mit Meldung — keine stille Umdeutung
auf `traces`.

### 4.6 Zwei Fallen

**Falle 1 — der Free-Text-Guard rejectet Prosa mit tag-förmigem Text.**
`persistence/free_text.py:16-22` verwirft jeden Wert, dessen `strip_tags`-Ergebnis vom
Eingabewert abweicht; der Docstring benennt den Trade-off wörtlich (`:31-35`): „prose that
legitimately contains tag-shaped text (`if <input> is empty`) … is a `400`". In Formularen
selten, in Repo-Markdown häufig (`<workspace-id>`, `List<String>`).

**Kein harter Fehler, sondern ein weicher pro Requirement** — überspringen, in `errors`
melden, Rest importieren, exakt nach `reqif_import_service.py:397-422`. Die Regel selbst
wird **nicht** gelockert; sie ist die Grundlage dafür, dass Beschreibungen im Frontend über
`MarkdownPreview` gerendert werden dürfen. Siehe §9.5.

**Falle 2 — Audit-Operation.** `ServiceBase._audit` validiert `operation=` gegen
`AuditEntry.OP_CHOICES` (`audit/models.py:130-141`) via `full_clean`; ein nicht deklarierter
String lässt die gesamte Transaktion **nach** der erfolgreichen Mutation mit 500 scheitern
(Kommentar `:123-129`, Issue #265). Also `operation="create"`,
`entity_type="ReqmdImport"` — analog `reqif_import_service.py:440-453`. Keine neue Operation
erfinden.

### 4.7 dry_run, Atomarität, Report

Wortgleich zum ReqIF-Muster: Gesamtlauf in `transaction.atomic()`, Savepoint pro
Requirement, `dry_run=True` → `transaction.set_rollback(True)` am äußeren Rand. Report:

```json
{ "success": true, "dry_run": false,
  "requirements": {"created": 12, "updated": 30, "skipped": 2, "errors": [...]},
  "links":        {"created": 41, "updated": 8,  "skipped": 3, "errors": [...]},
  "unresolved_pins":  [{"uid": "SW-001", "ref": "SYS-001", "pin": 3}],
  "unmapped_attrs":   [{"uid": "SW-001", "keys": ["disposition", "asil"]}],
  "warnings": [...] }
```

`unmapped_attrs` ist wichtig: es macht sichtbar, welche fremden Attribute in
`custom_fields` gelandet sind, statt sie stillschweigend zu schlucken.

---

## 5. Architektonische Verortung

**Zwei Layer-2-Dienste in `application/`, exakt wie ReqIF — kein neues Ext-Modul.**

`icd/` ist eine eigene App, **weil sie Tabellen besitzt** (`icd/models.py`, eigene
Migrationen, eigene RLS-Policies, Layer-1-Fassade `icd/services.py`). Die reqmd-Brücke
besitzt in v1 keine einzige Tabelle. Eine App ohne Modelle bringt `apps.py`, ein
Migrationsverzeichnis, einen `INSTALLED_APPS`-Eintrag und eine zusätzliche Importgrenze — und
keinen Fähigkeitsgewinn.

```
backend/application/reqmd_export_service.py   # COMP-AS-008-Familie
backend/application/reqmd_import_service.py   # COMP-AS-008b-Familie
```

Gemeinsame Konstanten (Attributnamen, ID-Regex, Ebenen-Verzeichnisnamen, Status-Normalisierung)
liegen im Export-Modul und werden vom Import importiert — die Kopplung, die
`reqif_import_service.py:135-146` bewusst herstellt („to keep both directions in lock step").
Beide erben `ServiceBase`; `_set_tenant_context(ctx)` + `_assert_write_permission(ctx)` sind
die ersten zwei Zeilen des Import-Einstiegspunkts. Re-Export über
`application/services_stepN.py` nach dem dokumentierten Erweiterungsmuster
(`application/services.py:24-40`), ohne `services.py` selbst zu ändern.

**REST** (neben `rest_api/urls.py:187-207`):

```
GET  /api/v1/workspaces/<uuid:pk>/export/reqmd/     -> application/zip (Verzeichnisbaum)
POST /api/v1/workspaces/<uuid:pk>/import/reqmd/     -> multipart, Feld "file" (zip), ?dry_run=
```

Ein Verzeichnisbaum ist kein einzelnes Dokument — deshalb ZIP statt Textkörper. Das ist der
einzige Punkt, an dem die reqmd-Brücke vom ReqIF-View-Muster abweicht, und er braucht eine
Größen- und Pfadprüfung beim Entpacken (Zip-Slip: jeder Eintragspfad muss nach Normalisierung
innerhalb des Zielverzeichnisses liegen, keine absoluten Pfade, keine Symlinks, harte Grenze
für entpackte Gesamtgröße).

**MCP: bewusst nicht in v1.** Weder CSV noch ReqIF haben Werkzeuge; ein ZIP ist eine
schlechte MCP-Payload. Falls später: Payload-Schlüssel nie `content` (Envelope-Kollision),
Treffer und Nicht-Treffer in derselben Form, `reqmd.import` in `_WRITE_TOOL_PREFIXES`
(`mcp_server/tool_registry.py:57ff`).

**Preset-Gate: keins.** ReqIF und CSV haben keins; die fünf Feature-Schlüssel
(`presets/registry.py:155-205`) betreffen Baselines, Approval- und Custom-Workflows sowie
`change_reason` — Interop ist keiner davon.

---

## 6. Aufwand

Personentage, grob, inklusive Tests. **[N]** = neu, **[K]** = Komposition eines vorhandenen
Musters.

| # | Fähigkeit | Art | Tage |
|---|---|---|---|
| 1 | `ReqmdExportService`: Ebenenableitung, `schema.yaml`-Generierung, `attr`-Blöcke, `trace`, Determinismus | [N] | 4–6 |
| 2 | REST-Export-View (ZIP) + OpenAPI + Tests | [K] | 1–2 |
| 3 | `ReqmdImportService`: Parser, Feld-Mapping, Upsert, Status, `trace`, Soft-Errors, Report | [N] | 5–7 |
| 4 | REST-Import-View (multipart ZIP, Zip-Slip-Guard, dry_run) + Tests | [K] | 2 |
| 5 | Round-Trip-Test (Export → Handedit → Import → Export identisch bis auf den Edit) | [K] | 2 |
| 6 | Frontend: Export-/Import-Knopf neben CSV/ReqIF | [K] | 1–2 |
| 7 | `yaml` explizit pinnen + Supply-Chain-Prüfung | [K] | <1 |
| 8 | Weitere Entitätsarten im Import (**setzt `uid`-Constraints voraus**, §9.6) | [N] | 3–5 |
| 9 | Versions-Pins (`~N`) exportieren/importieren | [N] | blockiert durch §8.2 |
| 10 | `requires-trace-from` aus dem Preset ableiten | [N] | blockiert durch §8.3 |
| 11 | MCP-Werkzeuggruppe | [K] | 2 |

**Summe v1 (1–7): 15–21 Tage.**

**v1-Zuschnitt:** nur `Requirement` und `StakeholderNeed`; Export vollständig inklusive
generiertem `schema.yaml`; Import mit `uid`-Upsert und `trace`-Auflösung; keine
Versions-Pins, kein `requires-trace-from`, keine `disposition`.

**Was v1 beweist:** dass ein Workspace als validierbarer reqmd-Baum in ein Ziel-Repository
ausgeleitet, dort von `reqmd check` geprüft, im PR bearbeitet und ohne Identitätsverlust
zurückgeführt werden kann.

---

## 7. Was der Vergleich für Teil 1 bedeutet

Die Brücke ist machbar und deutlich wertvoller als bei einem reinen Prosaformat — aber sie
ist **nicht** die wichtigste Erkenntnis aus dem Vergleich. Die vier Befunde aus dem
Kernbefund oben sind Lücken in ReqogniLoom selbst, die eine Brücke nicht schließt, sondern
nur sichtbar macht. Teil 2 behandelt sie.

---

# Teil 2 — Was reqmds Design ReqogniLoom lehren kann

Sieben Konzepte, in absteigender Wertigkeit. Für jedes: Befund gegen den Code, Bewertung,
Empfehlung.

## 8.1 Ergebnis-getriebene Abdeckung + zero-integration CTRF-Einspeisung

### Befund

Zwei getrennte, gleich schwerwiegende Lücken.

**(a) Abdeckung ignoriert das Ergebnis.**
`CoverageCalculator.coverage()` zählt Requirements „with ≥1 `verifies` TraceLink to a
TestCase" — ADR-L3-TE3-01, `traceability/coverage_calculator.py:60`. Der Prozentwert steigt,
sobald der Link existiert. Die SE-Auditor-Regel VERIF-P8 prüft ebenfalls nur Existenz
(`traceability/audit/rules/coverage_consistency.py:299`: „no verifying TestCase ('verifies'
link)").

Das Ergebnis *wird* erhoben: `_latest_testrun_status`
(`traceability/coverage_calculator.py:228-270`) löst pro TestCase das jüngste
`TestRunResult` auf und schreibt es in `CoverageData` — **aber nur für die VCRM-Anzeige**.
Weder `coverage()`s Prozentwert noch irgendeine Auditor-Regel liest es.

**Konsequenz, unmissverständlich formuliert: ein Workspace kann 100 % Abdeckung ausweisen,
während jeder einzelne verifizierende Test fehlschlägt.** In einem Werkzeug, das mit
Extended-Rigor und V&V wirbt, ist das kein Schönheitsfehler.

**(b) Einspeisung nur über interne UUIDs.**
`TestRunService.add_results_bulk` (`application/test_run_service.py:226`) verlangt pro
Eintrag ein `test_case_id` und schlägt sonst fehl (`:263-266`: „test_case_id is required for
each result entry"); der Lookup ist `TestCase.objects.filter(id=tc_id)` (`:268`) — die
ReqogniLoom-UUID, nicht die `uid`. Das MCP-Schema `test.run_report_results`
(`mcp_server/tools/tests.py:220-240`) bildet dasselbe ab. `TestRunResult.test_case` ist eine
FK (`persistence/models.py:1492`).

Damit muss jede CI-Pipeline eine Zuordnung „mein Testname → ReqogniLoom-UUID" pflegen. Es
gibt keinen Adapter für JUnit-XML, kein CTRF, kein TAP, kein Cucumber-JSON. Die
Statusmenge ist `{passed, failed, blocked, not_run}` (`test_run_service.py:41`) — kein
`inconclusive`, kein Flaky-Begriff.

### Bewertung

reqmds Lösung ist in beiden Punkten eleganter, und der Grund ist eine bewusste
Entwurfsentscheidung: **Ergebnisse sind ephemer.** Sie werden nie ins Spec-Repo
zurückgeschrieben, sondern pro Prüflauf geladen. Damit entfällt die gesamte Frage nach
Lebenszyklus, Versionierung und Aufräumen von Testergebnissen — und die Prüfung
(`missing-verdict`, `failing-verdict`) kann trotzdem hart gaten.

ReqogniLoom kann und soll Ergebnisse persistieren (das ist Teil seines Werts: Historie,
Audit, Test-Run-Protokollierung). Aber die *Verwertung* fehlt komplett.

Der CTRF-Teil ist die günstigste Verbesserung im ganzen Dokument: CTRF ist ein offener
JSON-Standard, den viele Runner bereits ausgeben, und der Bindungsmechanismus ist ein
einziges Feld pro Test (`tests[].extra["x-reqmd.id"]`). Ein Adapter, der CTRF liest, das
Bindungsfeld gegen `TestCase.uid` auflöst und `add_results_bulk` füttert, ist eine kleine,
klar abgegrenzte Komponente.

### Empfehlung: **Adopt — beide Teile, (a) mit Vorrang.**

Konkreter Zuschnitt:

1. **`uid` als alternativer Einspeise-Schlüssel.** `add_results_bulk` akzeptiert
   `test_case_uid` alternativ zu `test_case_id`. Voraussetzung: eine
   `uid`-UniqueConstraint auf `TestCase` (§9.6) — sonst ist der Lookup mehrdeutig.
   *Ohne diesen Schritt ist alles Weitere nicht machbar.*
2. **CTRF-Adapter** als eigener, dünner Übersetzer (`application/ctrf_adapter.py`), der
   CTRF-JSON nach der Eingabestruktur von `add_results_bulk` transformiert, inklusive
   Status-Mapping und `flaky → blocked` (der nächstliegende vorhandene Wert; ein neuer Wert
   `inconclusive` wäre sauberer, ändert aber ein publiziertes REST/MCP-Enum).
3. **Ergebnis-getriebene Abdeckung** als **neue, additive** Kennzahl neben der bestehenden —
   `covered` (Link existiert) *und* `verified` (jüngster Lauf `passed`). Die bestehende
   Definition darf nicht stillschweigend ihre Bedeutung ändern: sie speist VCRM, PDF-Report
   und Baseline-Vergleiche, und eine über Nacht gefallene Abdeckungszahl wäre für Nutzer ein
   Datenverlust-Erlebnis.
4. **Eine neue SE-Auditor-Regel `VERIF-P8b` („verifizierender Test schlägt fehl")**, aktiv
   auf `extended`, WARNING auf `standard`. Registrierung nach dem dokumentierten Muster
   (`traceability/audit/registry.py:18-40`) — neue Regel, neuer `rule_id`, Eintrag in
   `RULE_PRESET_MAP`, kein Eingriff in die Engine.

Aufwand: 1 ≈ 2 T, 2 ≈ 3 T, 3 ≈ 3 T, 4 ≈ 2 T. **Zusammen ~10 Tage für den größten
inhaltlichen Zugewinn im gesamten Dokument.**

## 8.2 Versions-gepinnte Trace-Links statt eines `suspect`-Booleans

### Befund

`TraceLink` (`persistence/models.py:1225-1250`) trägt `source`, `target`, `link_type`,
`embedding` — **keine Version, keinen Prüfzeitpunkt, keinen Pin**.

Der Ersatz ist das `suspect`-Flag auf `StakeholderNeed` (`:793`), `Requirement` (`:891`) und
`ArchitectureElement` (`:1023`), gesetzt durch
`TraceLinkService.propagate_suspect_status` (`application/trace_link_service.py:903-975`).
Verhalten, verifiziert:

- Ausgelöst bei jeder Änderung von `title`, `description` oder `status`
  (`application/requirement_service.py:368-417`).
- Markiert die **vollständige transitive Upstream-Hülle** (`transitive=True`, `:934-938`),
  standardmäßig **ohne Tiefenbegrenzung** (`SUSPECT_PROPAGATION_MAX_DEPTH` ist per Default
  `None`, `:940`).
- Setzt ein `BooleanField` auf `True` (`:956-966`).
- **Wird nirgends automatisch zurückgesetzt.** Ein `suspect=False` gibt es nur als
  manuelles Feld-Update (`requirement_service.py:372-373`).

Vergleich der beiden Mechanismen:

| | ReqogniLoom `suspect` | reqmd `~N`-Pin |
|---|---|---|
| Granularität | pro **Artefakt** | pro **Link** |
| Information | „irgendetwas oben hat sich geändert" | „geprüft gegen Version 3, oben steht jetzt 5" |
| Reichweite | volle transitive Hülle | genau ein Kantenende |
| Auslöser | jede Speicherung, auch inhaltsneutrale | Erhöhung der Inhaltsrevision |
| Zurücksetzen | nur manuell, pro Artefakt | `reqmd repin`, automatisch, pro Link |
| Fehlerrichtung | erkennt „vorgezogen" nicht | erkennt `pin > version` als eigenen Fehler |

**reqmds Modell ist in jeder Zeile strenger.** Und die praktische Folge des ReqogniLoom-
Modells ist absehbar: Bei einer Änderung an einem L1-Requirement wird die gesamte
Downstream-Hülle markiert; nichts löscht die Markierungen; nach kurzer Zeit ist alles
`suspect` und das Signal wertlos — die klassische Alarm-Ermüdung.

### Bewertung — und der Grund, warum es nicht einfach ist

Ein Pin braucht eine **Inhaltsrevision**, gegen die er zeigt. ReqogniLoom hat keine.
`AuditableModel.version` ist ausdrücklich ein Sperrzähler und **kein** Revisionsstand
(`persistence/models.py:305-322`, Issue #213):

> „Any save bumps it — including writes that change nothing a user would recognise as
> content. … Never present it as 'this artifact has N revisions'."

Einen Pin gegen diesen Zähler zu setzen, reproduziert exakt das Problem, das er lösen soll:
er feuert bei belanglosen Speicherungen.

Das ist also **kein einzelnes Feature, sondern eine Kette**:

1. **Eine Inhaltsrevision einführen** — eine Zahl, die nur steigt, wenn sich fachlich
   relevante Felder ändern. Präzedenzfälle im Haus: `DiagramVersion`,
   `GlossaryTermVersion`, `PromptTemplate` (in `models.py:317-318` als „the few types that
   have real version tables" genannt). Eine billigere Variante ohne Tabelle: ein stabiler
   Inhalts-Hash über die fachlichen Felder, gespeichert auf der Zeile.
2. **`verified_against` am TraceLink** (Revision oder Hash des Ziels zum Zeitpunkt der
   Bestätigung) + `verified_at` + `verified_by`.
3. **Eine Auditor-Regel „Pin veraltet"** — und, weil dann bekannt ist *wogegen* geprüft
   wurde, ein „Erneut bestätigen"-Vorgang, der genau eine Kante zurücksetzt statt einer
   ganzen Hülle.
4. **`suspect` als abgeleitete Anzeige**, nicht als gespeicherter Zustand: „mindestens eine
   ausgehende Kante ist veraltet". Damit verschwindet das Zurücksetzen-Problem, weil es
   nichts mehr zurückzusetzen gibt.

### Empfehlung: **Adopt — als eigenes, mehrstufiges Vorhaben, nicht als Anhängsel der Brücke.**

Aufwand grob: Schritt 1 ≈ 5–8 T (Modell, Migration, Backfill, Schreibpfade), Schritt 2 ≈ 3 T,
Schritt 3 ≈ 3 T, Schritt 4 ≈ 2–4 T (Umbau von `propagate_suspect_status`, UI). **~15 Tage.**
Der Nutzen ist groß, aber der erste Schritt berührt jeden Schreibpfad im System und braucht
eine eigene Entwurfsrunde (§9.2).

Zwischenschritt mit sofortigem Nutzen und minimalem Risiko: **`propagate_suspect_status`
darf nicht mehr bei jeder Speicherung feuern.** Ein Vergleich der fachlichen Felder vor und
nach dem Update (die Daten liegen im Update-Pfad ohnehin vor) unterdrückt inhaltsneutrale
Auslösungen. ~1 Tag, und die Alarm-Ermüdung sinkt sofort messbar.

## 8.3 `requires-trace-from` — Abdeckung als Vertrag statt als Code

### Befund

**Abwesend als Deklaration.** ReqogniLoom kennt drei Abdeckungsmechanismen, alle
festverdrahtet:

- `CoverageCalculator.coverage()` — eine einzige Definition („`verifies`-Links zu
  TestCases", ADR-L3-TE3-01, `coverage_calculator.py:60`). `artifact_type`/`link_type` sind
  Abfrage-*Filter* (`:65-70`), keine Deklaration eines Artefakts über sich selbst.
- SE-Auditor-Regeln — je eine Python-Klasse pro Regel; welche Regel aktiv ist, steuert
  ausschließlich `RULE_PRESET_MAP` pro Rigor-Stufe (`traceability/audit/registry.py:70ff`).
  Kein Artefakt und keine Ebene kann eine eigene Erwartung anmelden.
- `traceability_target` steht zwar in `mandatory_fields` der `extended`-Stufe
  (`presets/registry.py:186-194`), wird aber **absichtlich nicht durchgesetzt**:
  `workflow/precondition_rules.py:163-171` — „a *graph* property … deliberately NOT enforced
  here — trace completeness is the SE-Auditor's mandate … duplicating it in a scalar field
  check would produce two divergent definitions of the same policy."

### Bewertung

reqmds Modell dreht die Richtung um: nicht „das Werkzeug weiß, welche Links es geben muss",
sondern „**das Artefakt (bzw. seine Ebene) erklärt, von welchen Ebenen es Verweise
erwartet**". Zwei echte Vorteile:

- **Heterogene Bestände werden ausdrückbar.** Ein Sicherheitsrequirement verlangt sowohl
  einen Test als auch eine Analyse; ein rein informatives Requirement verlangt nichts. Heute
  ist beides dieselbe Regel mit demselben Ergebnis.
- **Die Erwartung steht neben dem Gegenstand**, nicht in einer Python-Datei — sie ist für
  Fachleute lesbar und ohne Deployment änderbar.

Der Gegeneinwand ist ernst zu nehmen und stammt aus dem Haus selbst: die eben zitierte
Stelle in `precondition_rules.py` warnt ausdrücklich vor „two divergent definitions of the
same policy". Eine deklarative Erwartung *neben* den bestehenden Auditor-Regeln erzeugt
genau das — zwei Orte, an denen Abdeckung definiert ist.

Zweiter Einwand: **pro Artefakt ist zu fein.** In einem 2000-Requirement-Workspace würde
niemand 2000 Erwartungen pflegen; sie wären leer oder kopiert, und eine leere Erwartung ist
schlechter als eine feste Regel, weil sie so aussieht, als hätte jemand entschieden.

### Empfehlung: **Adapt — auf Ebenen-/Typ-Granularität, und als Parametrisierung der bestehenden Regeln, nicht daneben.**

Konkret: eine Konfiguration pro (Workspace, Artefakttyp, Ebene) mit der Form
`requires_incoming: [{link_type, from_type, severity}]`, die die **vorhandenen** Regeln
TRACE-P1/P1b/P2/VERIF-P8 parametrisiert, statt eine zweite Prüfmaschine zu bauen. Ohne
Konfigurationszeile gilt genau das heutige, fest verdrahtete Verhalten — abwärtskompatibel,
und es gibt weiterhin nur eine Prüfstelle.

Das ist nahe verwandt mit §8.4 und sollte mit ihm zusammen entworfen werden: beide fragen
„was gilt auf welcher Ebene?".

## 8.4 Schemata pro Ebene statt pro Workspace

### Befund

**Gröber als reqmd, verifiziert an drei Stellen:**

1. `mandatory_fields` ist **ein Tupel pro Rigor-Stufe**, gültig für den ganzen Workspace:
   `("title",)` / `(… , "priority")` / `(…, "classification", "traceability_target",
   "change_reason")` (`presets/registry.py:154`, `:170`, `:186`).
2. Durchgesetzt wird es nur bei Freigabe-Übergängen und mit einem Alias-Mechanismus, der
   Felder **überspringt**, die das Entitätsmodell nicht hat
   (`workflow/precondition_rules.py:148-160`: „if none exists the policy field is **not
   applicable** to that entity type and is skipped"). Faktisch ist die Liste
   Requirement-förmig und wirkt bei anderen Typen nur teilweise.
3. `AttributeVisibilityConfig` — die einzige feinere Konfiguration — ist unique über
   `(tenant, entity_type, attribute_name)` (`persistence/models.py:1577-1581`) und damit
   **tenant-weit**: nicht pro Workspace, nicht pro Ebene, nicht pro Requirement-Typ. Sie
   trägt `is_visible` und `is_required` (`:1543-1550`).

**Es gibt also keinen Weg zu sagen: „L1-Requirements brauchen `verification_method`,
L3-Requirements nicht."** Genau das ist bei reqmd der Normalfall — jedes Verzeichnis hat sein
eigenes `required`.

### Bewertung

Das ist eine echte Lücke, und sie trifft ausgerechnet die Geschichte, mit der ReqogniLoom
wirbt: V-Modell L0–L4. Verschiedene Ebenen haben in der Praxis verschiedene Pflichtfelder —
ein Stakeholder Need braucht keine ASIL-Einstufung, ein Komponenten-Requirement keine
MoSCoW-Priorität. Heute muss man den kleinsten gemeinsamen Nenner wählen (dann ist die
strengste Ebene ungeprüft) oder den größten (dann ist die lockerste Ebene blockiert).

Zwei Einschränkungen für die Empfehlung:

- **Die drei Rigor-Presets bleiben.** Sie sind das Produktversprechen („eine Codebasis, drei
  Presets") und ein guter Grobschalter. Was fehlt, ist eine Verfeinerung *innerhalb* eines
  Presets, nicht ein Ersatz.
- **ADR-PC-02 gilt**: „preset rules live in code, never in DB"
  (`application/validators.py:19`). Eine Verfeinerung darf das nicht aushebeln. Der saubere
  Weg ist ein *Override* über der Code-Grundlage — dasselbe Muster, das
  `RIGOR_INVARIANT_PRESETS` mit `settings.ARCHITECTURE_RIGOR_INVARIANTS` schon benutzt
  (`validators.py:70-82`) und `presets/registry.py:387-390` für `mandatory_fields`.

### Empfehlung: **Adopt — den Konfigurationsschlüssel um Ebene und Typ erweitern.**

Minimaler Zuschnitt: `AttributeVisibilityConfig` bekommt zwei zusätzliche, nullable
Schlüsselspalten (`workspace` und `level`/`req_type`) und einen Auflösungsvorrang
spezifisch → allgemein (NULL = „gilt für alle"). Damit bleibt jede bestehende Zeile gültig
und wirkt weiter tenant-weit; neue Zeilen können verfeinern. Der Preis ist eine
Constraint-Änderung und eine Auflösungsfunktion an genau einer Stelle.

Zusammen mit §8.3 entwerfen. Aufwand grob 5–8 T für beides gemeinsam.

## 8.5 Baseline-Diff: nach Inhalt vergleichen, nicht nach Zähler

### Befund

ReqogniLooms Baseline speichert pro Eintrag `(item_id, version, entity_type)` **plus** einen
vollständigen Zustands-Snapshot: `BaselineDeltaIndexEntry.state` als JSONField
(`baseline/models.py:151-160`, REQ-L2-BL-012), befüllt von `baseline/state_capture.py`.

Der `DiffEngine` benutzt den Zustand aber **nur nachrangig**: er klassifiziert zuerst über
die Versionsnummer („Build dict-backed index sets: `{item_id: version}`",
`baseline/diff_engine.py:35`) und rechnet den Feld-Diff nur für die bereits als geändert
klassifizierten IDs. `ChangedItem.field_changes` ist ausdrücklich als Zusatz dokumentiert:
„callers fall back to the version-number delta" (`baseline/types.py:69-74`).

**Genau daraus entsteht GH #398** („CRITICAL: Baseline diff reports zero change for
genuinely changed artifacts"): die verglichene Version ist `Artifact.version`, die bei einer
Änderung der Fachentität auf 1 stehen bleibt, während `Requirement.version` korrekt auf 2
zählt. Im Issue steht der DB-Beleg: dieselbe `item_id`, beide Einträge `version = 1`, aber
`state->>'title'` nachweislich verschieden — der Diff meldet trotzdem „0 changed".

Und die tiefere Ursache steht in `persistence/models.py:305-322` (#213): `version` ist ein
Sperrzähler. Selbst wenn `Artifact.version` mitgezogen würde, wäre er die falsche Grundlage
für die Frage „hat sich der Inhalt geändert?" — er bewegt sich auch bei Schreibvorgängen, die
inhaltlich nichts ändern.

### Bewertung

reqmd hat gar keinen Versionszähler zur Verfügung: `baseline diff <tag1> <tag2>` liest zwei
Git-Tags und vergleicht **Inhalt**. Das ist keine Raffinesse, sondern eine erzwungene
Einfachheit — und sie macht das Werkzeug gegen diese ganze Fehlerklasse **strukturell
immun**. Man kann in reqmd nicht versehentlich „0 geändert" melden, weil es keinen Zähler
gibt, der lügen könnte.

Die Lehre ist deshalb nicht „git benutzen", sondern: **die einzige verlässliche Antwort auf
„was hat sich geändert" ist ein Inhaltsvergleich. Ein Versionszähler ist bestenfalls eine
Optimierung und schlimmstenfalls eine Fehlerquelle.** ReqogniLoom hat den Inhalt bereits in
`state` — es benutzt ihn nur an der falschen Stelle in der Reihenfolge.

Ein Nebenbefund aus #398, der die Diagnose stützt: der Snapshot erfasst
`acceptance_criteria`, `level` und `rationale` gar nicht. Eine Änderung an
Akzeptanzkriterien ist heute selbst bei korrekter Klassifikation im Diff unsichtbar.

### Empfehlung: **Adopt die Lehre — Feld-Diff zur primären Klassifikation machen.**

Das deckt sich mit der Erwartung in #398 („robuster — Feld-Level-Diff unabhängig von der
Versionsklassifikation über alle gemeinsamen Items laufen lassen"), und dieses Dokument
liefert die Begründung, warum das nicht nur die robustere, sondern die **einzig richtige**
Variante ist: der Zähler ist per Dokumentation kein Inhaltsmaß.

Konkret:

1. `changed` ergibt sich aus `state_a != state_b` über der Schnittmenge, nicht aus
   `version_a != version_b`.
2. `state` erfasst `acceptance_criteria`, `level`, `rationale` (`state_capture.py`).
3. Einträge mit `state IS NULL` (Alt-Baselines, bewusst ohne Backfill,
   `baseline/models.py:154`) behalten den Zähler-Vergleich als Rückfall — und die Antwort
   markiert diesen Fall sichtbar, statt ihn stillschweigend gleich zu behandeln.
4. Der Vergleich läuft über eine normalisierte Sicht (stabile Schlüsselreihenfolge,
   normalisierte Zeitstempel), sonst erzeugt eine Serialisierungsänderung falsche
   Änderungsmeldungen.

Punkt 3 ist wichtig und im Issue nicht genannt: die Umstellung darf die Antwort für
Alt-Baselines nicht heimlich verschlechtern.

**Das ist ein Bugfix, kein neues Feature** — es gehört an #398, nicht an dieses Dokument.
Der Beitrag hier ist die Begründung und die Reihenfolge.

## 8.6 Regel-Unterdrückung pro Artefakt — der fehlende Abweichungsnachweis

### Befund

**Vollständig abwesend.** Eine Suche über `traceability/audit/` und
`application/audit_service.py` nach `suppress`, `waiver`, `exempt`, `acknowledg`, `dismiss`
liefert **keinen einzigen Treffer**.

Die einzigen vorhandenen Granularitäten:

- `RULE_PRESET_MAP` (`traceability/audit/registry.py:70ff`) — eine Regel ist pro Rigor-Stufe
  ganz an oder ganz aus.
- `Rule.deferred_reason` (`registry.py:37-40`) — eine Regel ist dauerhaft aus, für alle.
- `_APPROVAL_GATE_EXEMPT_TYPES = frozenset({"ChangeRequest"})`
  (`workflow/precondition_rules.py:146`) — eine hartcodierte Ausnahme für genau einen
  Entitätstyp, im Code.

**Konsequenz:** Ein begründeter Einzelfall — „REQ-L1-007 hat bewusst keinen Upstream, es ist
eine regulatorische Vorgabe" — kann nicht festgehalten werden. Der Befund bleibt dauerhaft
als BLOCKER stehen; die einzige Abhilfe ist, die Regel workspace-weit abzuschalten. Damit
verliert man sie für alle 2000 anderen Requirements.

### Bewertung

Das ist eine echte Lücke, und sie ist **größer als reqmds Lösung**. reqmds
`reqmd-suppress: [untraced, id-prefix]` ist eine Liste im Attributblock, versioniert durch
git — für ein Werkzeug ohne Datenbank angemessen.

Für ein Werkzeug, das Extended-Rigor, Audit-Log und Freigabe-Workflows verkauft, ist eine
freitextlose Unterdrückungsliste **zu wenig**. Jedes ernsthafte QM-System kennt eine
Abweichung/Waiver mit vier Pflichtangaben: *was* wird abgewichen, *warum*, *wer* hat es
genehmigt, *bis wann*. Genau diese vier fehlen heute — es gibt gar nichts.

Die Alternative, die heute faktisch praktiziert wird, ist schlimmer: entweder die Regel
abschalten (dann ist die Aussage weg) oder mit dem Befund leben (dann ist der Bericht dauerhaft
rot und wird ignoriert — dieselbe Alarm-Ermüdung wie bei `suspect`, §8.2).

### Empfehlung: **Adopt, aber schwerer als reqmd — als auditierter Waiver, nicht als Unterdrückungsliste.**

Ein Modell `AuditFindingWaiver` (tenant-scoped, RLS-Migration nach dem Muster von
`0026_add_llm_settings.py`):

```
workspace     FK
rule_id       CharField      # aus traceability.audit.registry
artifact_id   UUID           # genau ein Artefakt, nie ein Platzhalter
reason        TextField      # Pflicht, nicht leer
approved_by   FK User        # Pflicht
approved_at   DateTime
expires_at    DateTime NULL  # optionaler Ablauf
UNIQUE (workspace, rule_id, artifact_id)
```

Wirkung: der RuleEngine unterdrückt den Befund **nicht**, sondern stuft ihn auf
`Severity.INFO` mit `waived: true` herab und führt Grund und Genehmiger mit. **Der Befund
verschwindet nie aus dem Bericht** — er wird zu einer bewussten, nachvollziehbaren
Abweichung. Das ist der Unterschied zwischen „unterdrücken" und „genehmigen", und es ist der
einzige Umgang, der in einem auditierten Werkzeug vertretbar ist.

Anlegen erfordert eine Rolle mit Freigaberecht; jede Anlage schreibt einen Audit-Eintrag
(`operation="create"`, `entity_type="AuditFindingWaiver"` — **muss** in `OP_CHOICES`
existieren, sonst greift die #265-Falle, `audit/models.py:123-129`).

Aufwand ≈ 5–7 T inklusive UI. **Hohe Wertigkeit**, weil es die Voraussetzung dafür ist, dass
der SE-Auditor im Alltag überhaupt grün werden *kann* — und ein Bericht, der nie grün wird,
wird nicht gelesen.

## 8.7 Kleinere Ideen — bewertet, nicht gepolstert

**`disposition` / `disposition-reason` (implemented | deferred | rejected).**
ReqogniLoom hat kein Feld, das festhält, *wie* mit einer Downstream-Absicht umgegangen
wurde. Der nächste Verwandte ist `ChangeRequest`, aber das ist ein Antrag mit eigenem
Lebenszyklus, kein Vermerk am Requirement. Praktisch heißt das: ein bewusst nicht
umgesetztes Requirement sieht aus wie ein vergessenes. **Empfehlung: Adapt, klein** — zwei
Felder auf `Requirement`, `disposition` (enum, Default `implemented`) und
`disposition_reason` (Pflicht, sobald ≠ `implemented`), durchgesetzt in derselben
Precondition-Schicht wie `mandatory_fields`. ≈2 T. Nutzen: TRACE-P1b-Befunde für bewusst
offene Requirements werden erklärbar — und es ist die leichte Variante von §8.6.

**Randerkennung für Trace-Regeln.** reqmd leitet obere/untere Ebenengrenze aus der
Schema-Topologie ab und unterdrückt Falschmeldungen dort automatisch. ReqogniLooms
TRACE-P1b bestimmt die Wurzel über die Graphtiefe
(`trace_derivation_allocation.py:22-27`) — das funktioniert, sagt aber nichts darüber, ob es
*erwartbar* ist, dass eine Ebene keinen Upstream hat. Fällt bei §8.3/§8.4 als Nebenprodukt
ab. **Kein eigenes Vorhaben.**

**`external: true` — Verzeichnisse als Stellvertreter für extern verwaltete Artefakte.**
ReqogniLoom kennt kein Artefakt, das ausdrücklich als Platzhalter für etwas außerhalb
markiert ist; ein Requirement aus einer Norm sieht aus wie ein selbst geschriebenes.
**Empfehlung: vertagen.** Ein Flag ohne konkreten Anwendungsfall ist ein Feld, das niemand
befüllt.

**Exit-Codes und `--json` als CI-Gate.** Setzt eine CLI voraus, die nicht existiert
(`mcp_server/protocol_handler.py:261` ist definiert und wird nirgends instanziiert). Eine
dünne CLI über die vorhandene REST-API (`reqlo export reqmd … `, `reqlo audit --json`,
Exit-Code ≠ 0 bei BLOCKER) kostet 4–6 T, führt keine zweite Architektur ein und ist die
Voraussetzung für §8.5-artige Gates und für jede Nutzung in fremden Pipelines.
**Empfehlung: Adopt, als eigenständige Betriebsverbesserung.** Sie ist ausdrücklich *kein*
Einstieg in einen datenbankfreien Modus — Mandantentrennung liegt in PostgreSQL-RLS
(`persistence/migrations/0003_rls_policies.py`), Workflow, Baselines und Audit-Log sind
Tabellen; ein DB-freies ReqogniLoom wäre ein zweites Produkt, kein Deployment-Modus.

**Dogfooding.** reqmd validiert seine eigenen 233 Requirements mit sich selbst.
ReqogniLooms SE-Kaskade lebt in `docs/se/` als Markdown; der einzige Weg hinein ist
`application/management/commands/migrate_se_docs.py` (55 KB), ein einmaliger
Migrationsbefehl, kein laufender Abgleich. Der SE-Auditor kann die eigene Architektur
deshalb nicht prüfen. **Ein reqmd-Export der eigenen SE-Kaskade wäre der billigste Weg zu
einem laufenden Selbsttest** — und ein hübscher Nebennutzen von Teil 1. Erwähnenswert, aber
kein eigenständiger Grund.

---

## 8.8 Gesamtwertung und Reihenfolge

| # | Konzept | Vorhanden? | Empfehlung | Aufwand | Wert |
|---|---|---|---|---|---|
| 8.1 | Ergebnis-getriebene Abdeckung + CTRF | nein | **Adopt** | ~10 T | **sehr hoch** |
| 8.6 | Auditierter Waiver statt Unterdrückung | nein | **Adopt** (schwerer als reqmd) | 5–7 T | **hoch** |
| 8.5 | Baseline-Diff nach Inhalt | fehlerhaft (#398) | **Adopt die Lehre** | Teil von #398 | **hoch** |
| 8.4 | Pflichtfelder pro Ebene/Typ | gröber | **Adopt** | 5–8 T (mit 8.3) | mittel-hoch |
| 8.3 | `requires-trace-from` als Vertrag | nein | **Adapt** (Ebene, nicht Artefakt) | mit 8.4 | mittel |
| 8.2 | Versions-gepinnte Links | nein (nur `suspect`) | **Adopt** — mehrstufig | ~15 T | hoch, teuer |
| 8.7a | `disposition` | nein | **Adapt, klein** | 2 T | mittel |
| 8.7d | CLI mit Exit-Codes | nein | **Adopt** | 4–6 T | mittel |
| 8.7c | `external: true` | nein | **Vertagen** | — | gering |

**Empfohlene Reihenfolge, mit Begründung:**

1. **§8.5** — es ist ein offener kritischer Bug (#398), und die Korrektur der
   Diff-Grundlage muss stehen, bevor irgendeine andere Kennzahl darauf aufbaut.
2. **§8.1 Schritt 1+3** (`uid`-Schlüssel, `verified`-Kennzahl) — die größte inhaltliche
   Lücke, und Schritt 1 ist Voraussetzung für Schritt 2 *und* für Teil 1/Position 8.
3. **§8.6** — ohne Waiver kann der SE-Auditor nie grün werden; alle weiteren Regeln (§8.1
   Schritt 4, §8.3) verschärfen sonst nur einen Bericht, den niemand mehr liest.
4. **§8.1 Schritt 2+4** (CTRF-Adapter, `VERIF-P8b`).
5. **§8.3 + §8.4 gemeinsam.**
6. **Teil 1** (die Brücke) — sie ist wertvoll, aber keine der Lücken oben hängt von ihr ab.
7. **§8.2** — die größte Einzelinvestition; der Zwischenschritt („`suspect` nur bei
   echter Inhaltsänderung", ~1 T) sollte allerdings sofort mitgenommen werden.

**Die unbequeme Beobachtung:** Der Anlass dieses Dokuments war eine Interop-Brücke. Der
Ertrag der Untersuchung sind vier Befunde über ReqogniLoom selbst, von denen einer
(§8.1a — Abdeckung ohne Ergebnis) das zentrale Qualitätsversprechen des Werkzeugs berührt und
zwei weitere (§8.5, §8.6) verhindern, dass die vorhandenen Prüfmechanismen im Alltag
benutzbar sind. Die Brücke ist gut und machbar — aber sie steht in der Prioritätenliste
hinter dem, was sie sichtbar gemacht hat.

---

## 9. Offene Fragen (Menschentscheidung nötig)

**9.1 Ist die Brücke gewollt — und in welche Richtung?**
Export allein (ReqogniLoom als Autorität, reqmd als Ansicht plus Zweitmeinung) ist etwa die
Hälfte des Aufwands und trägt die meisten Vorteile. Vollständiger Round-Trip lohnt sich nur,
wenn Menschen die Dateien tatsächlich bearbeiten sollen. *Gibt es ein konkretes reqmd-Projekt,
mit dem ausgetauscht werden soll, oder ist das eine Option auf Vorrat?*

**9.2 Braucht ReqogniLoom eine Inhaltsrevision (§8.2 Schritt 1)?**
Blockiert Versions-Pins, präzise Baseline-Diffs und die Ablösung des `suspect`-Flags. Berührt
jeden Schreibpfad und braucht eine eigene Entwurfsrunde. *Eigene Versionstabelle (wie
`DiagramVersion`) oder Inhalts-Hash auf der Zeile?* Empfehlung dieses Dokuments: Hash zuerst
— billiger, reversibel, und er beantwortet die eigentliche Frage („hat sich der Inhalt
geändert?") vollständig.

**9.3 Darf die Abdeckungsdefinition sich ändern (§8.1a)?**
Dieses Dokument empfiehlt ausdrücklich **nein** — `covered` bleibt, `verified` kommt daneben.
Wer sich für „Abdeckung heißt ab jetzt: der Test ist grün" entscheidet, ändert eine Zahl in
VCRM, PDF-Report und allen bestehenden Baselines. Das ist vertretbar, aber es ist eine
Produktentscheidung mit Ankündigungspflicht, keine Implementierungsentscheidung.

**9.4 Waiver: wer darf genehmigen, und laufen sie ab (§8.6)?**
Rolle und Ablauffrist sind Governance-Fragen. Ohne Ablauf sammelt sich technische Schuld
lautlos an; mit Ablauf entsteht wiederkehrende Arbeit. Empfehlung: `expires_at` optional,
aber in der UI prominent, und eine Übersicht „Waiver, die in 30 Tagen ablaufen".

**9.5 Darf ein Beschreibungsfeld tag-förmigen Text enthalten (§4.6)?**
Der Free-Text-Guard weist jede Prosa mit `<…>` ab (`persistence/free_text.py:16-35`) — in
Formularen selten, in Repo-Markdown häufig. Empfehlung: Guard **nicht** lockern, pro
Requirement weich scheitern. Zeigt ein Pilotimport, dass dadurch relevante Anteile abgewiesen
werden, ist die Regel selbst neu zu bewerten — eine Sicherheits-, keine Importer-Entscheidung.

**9.6 `uid`-Eindeutigkeit für `TestCase` und `ArchitectureElement`.**
Beide tragen ein `uid`-Feld ohne Constraint und ohne Anwendungsprüfung
(`persistence/models.py:1017`, `:1320`; Metas `:1034`, `:1343`) — anders als `Requirement`
(#133, `:959`). **Das blockiert drei Dinge gleichzeitig:** den `uid`-basierten
Ergebnis-Schlüssel aus §8.1, den Import weiterer Entitätsarten (Teil 1/Position 8) und jede
`uid`-basierte Referenz aus einem externen Werkzeug. Es ist ein Datenintegritätsbefund
**unabhängig von reqmd** und gehört als eigenes Issue erfasst — mit einer Datenbereinigung
für vorhandene Duplikate vor der Migration.

**9.7 Wer besitzt eine exportierte Datei im Ziel-Repository?**
Wenn `spec/` aus ReqogniLoom erzeugt und eingecheckt wird: darf ein Mensch sie bearbeiten?
Empfehlung: die generierten `schema.yaml` gehören dem Exporter (Kopfkommentar sagt es), die
`.md`-Dateien dem Menschen, und der Import liest nur letztere. Das ist eine bewusste
Aufteilung und muss dokumentiert sein — die Referenzimplementierung für eine solche
Eigentumsinvariante liegt in `diagram/traceability_connector.py:275` (Reconciler, der jede
Operation hart auf seinen eigenen Diskriminator filtert).

---

## 10. Referenzen im Quellcode

| Thema | Datei / Zeile |
|---|---|
| Requirement-Datenmodell, `uid`, Titel-Grenze | `backend/persistence/models.py:818`, `:848`, `:885` |
| `(workspace, uid)`-UniqueConstraint (nur Requirement) | `backend/persistence/models.py:959-963` |
| `TestCase` / `ArchitectureElement` — `uid` ohne Constraint | `backend/persistence/models.py:1017`, `:1320`, `:1034`, `:1343` |
| **`version` = Sperrzähler, keine Revision (#213)** | `backend/persistence/models.py:305-322` |
| TraceLink — keine Version, kein Pin | `backend/persistence/models.py:1225-1250`, Unique `:1275` |
| `suspect`-Felder | `backend/persistence/models.py:793`, `:891`, `:1023` |
| `suspect`-Propagierung (volle Hülle, kein Reset) | `backend/application/trace_link_service.py:903-975` |
| Auslöser der Propagierung | `backend/application/requirement_service.py:368-417` |
| **Abdeckung = Link-Existenz (ADR-L3-TE3-01)** | `backend/traceability/coverage_calculator.py:60` |
| Testergebnis nur für die VCRM-Anzeige | `backend/traceability/coverage_calculator.py:189`, `:228-270` |
| VERIF-P8 prüft nur Link-Existenz | `backend/traceability/audit/rules/coverage_consistency.py:299` |
| **Ergebnis-Einspeisung nur über interne UUID** | `backend/application/test_run_service.py:226`, `:263-268` |
| MCP-Schema `test.run_report_results` | `backend/mcp_server/tools/tests.py:220-240` |
| Baseline-Zustand (JSONB, REQ-L2-BL-012) | `backend/baseline/models.py:151-160`, `backend/baseline/state_capture.py` |
| **Diff klassifiziert über Versionszähler (#398)** | `backend/baseline/diff_engine.py:35`, `:75`; `backend/baseline/types.py:69-74` |
| SE-Auditor: Regel-Registrierung, Preset-Map | `backend/traceability/audit/registry.py:18-40`, `:70ff` |
| Ebenenableitung über Graphtiefe (nicht `level`) | `backend/traceability/audit/rules/trace_derivation_allocation.py:14-35` |
| **Keine Waiver/Suppression** | Suche über `backend/traceability/audit/` — 0 Treffer |
| `mandatory_fields` pro Rigor-Stufe | `backend/presets/registry.py:154`, `:170`, `:186` |
| Durchsetzung + Feld-Alias-Skip | `backend/workflow/precondition_rules.py:146`, `:148-171`, `:221ff` |
| `AttributeVisibilityConfig` tenant-weit | `backend/persistence/models.py:1543-1550`, `:1577-1581` |
| ADR-PC-02 + Override-Muster | `backend/application/validators.py:19`, `:70-82`; `backend/presets/registry.py:387-390` |
| ReqIF-Import: Upsert, Soft-Errors, dry_run, Status | `backend/application/reqif_import_service.py:219`, `:397-422`, `:454-459`, `:624-630`, `:701-749`, `:839-848` |
| CSV-Round-Trip-Registry | `backend/application/export_service.py:101`, `backend/application/import_service.py:49-55` |
| **`export_markdown` — vorhanden, ohne Aufrufer** | `backend/application/export_service.py:378-436` |
| REST-Routen CSV/ReqIF (Vorbild) | `backend/rest_api/urls.py:187-207`, `backend/rest_api/views.py:5799ff`, `:5850ff` |
| Free-Text-Guard, dokumentierter Trade-off | `backend/persistence/free_text.py:16-35` |
| Audit-Operationsvokabular (#265-Falle) | `backend/audit/models.py:115-141` |
| Reconciler-Muster mit Eigentumsinvariante | `backend/diagram/traceability_connector.py:275-400` |
| Erweiterungsmuster für neue Layer-2-Dienste | `backend/application/services.py:24-40`, `:184ff` |
| Ext-App *mit* Tabellen (Gegenbeispiel zu §5) | `backend/icd/models.py`, `backend/icd/services.py` |
| `StdioTransportAdapter` — definiert, nie instanziiert | `backend/mcp_server/protocol_handler.py:261` |
| RLS-Policy-Muster für neue tenant-scoped Tabellen | `backend/persistence/migrations/0026_add_llm_settings.py` |
