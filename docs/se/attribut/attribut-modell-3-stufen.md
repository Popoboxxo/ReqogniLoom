# Attribut-Report: 3-Stufen-Modell — Vorschlag, Begründungen, Challenge gegen den Bestand

**Version:** 2.0 (challenged) · 11.09.2026 · Basis **v1.8.0-beta.10** (`b4c3a91`)
**Auftrag:** Detaillierter Attribut-Vorschlag mit konkreten Begründungen · vorhandene Repo-Vorarbeiten
suchen, bewerten und den eigenen Vorschlag dagegen challengen.
**Ergebnis vorab:** Mein Entwurf aus v1.0 hält in der Grundstruktur, wird aber in **5 Punkten korrigiert**
und in **3 Punkten gegen veraltete Audit-Aussagen verteidigt**.

---

## 1. Methode

| Quelle | Umfang |
|---|---|
| **Live-Bestand** | `GET /api/v1/attribute-defaults/{item_type}/{preset}/` für **11 Typen × 3 Presets** gegen die QS (Rohdaten `attr_bestand.json` (Rohdaten, nicht eingecheckt)) |
| **Preset-Definition** | `backend/presets/registry.py:154-215` |
| **Attribut-Schema** | `backend/attribute_definitions/schema.py:22-43` (`ITEM_TYPES`, `ATTRIBUTE_TYPES`) |
| **Baseline-Umfang** | `backend/baseline/state_capture.py:110-200` (Issue #398) |
| **Vorarbeiten** | `docs/archive/audits/SYSTEMAUDIT_SE_METHODOLOGY_2026-08-07.md` (985 Z.), `docs/REAUDIT_2026-09-03.md`, GH #393/#394/#408/#426/#583/#871/#912 |
| **Normen** | ISO/IEC/IEEE 29148:2018 §5.2.8 + §8.3/8.4/9.3/9.4 · ISO 15288 · ISO 42010:2022 · ISO 29119-3:2021 §8 · ISO 31000 · BABOK v3 · INCOSE/NASA (MOP/TPM) |

---

## 2. Bestandsaufnahme (live gemessen)

### 2.1 Der Kernbefund: es gibt kein Stufenmodell

```
Requirement/minimal n=11   Requirement/standard n=11   Requirement/extended n=11
StakeholderNeed/…   n=6    TestCase/…            n=6    Risk/…              n=12
Adr/…               n=8    Issue/…               n=8    Goal/…              n=3
Icd/…               n=7    GlossaryTerm/…        n=4    ChangeRequest/…     n=7
```

**Attributliste und `required`-Flags sind über alle drei Presets identisch.** Pflicht ist überall nur
`title` (+ `status`, das die Workflow-Engine füllt). Die Presets unterscheiden heute ausschließlich
Features (`baselines`, `approval_workflows`, `change_reason_mandatory`) — nicht den Attributumfang.

### 2.2 Presets fordern Felder, die es nicht gibt

`backend/presets/registry.py`:

| Preset | `mandatory_fields` |
|---|---|
| minimal | `title` |
| standard | `title, description, acceptance_criteria, priority` (Z. 170) |
| extended | + `classification, traceability_target, change_reason` (Z. 186) |

| Gefordert | Ist-Zustand |
|---|---|
| `priority` | ⚠️ **Attribut existiert nicht** |
| `classification` | ⚠️ existiert nicht |
| `traceability_target` | ⚠️ existiert nicht |
| `description`, `acceptance_criteria` | vorhanden, aber `required=false` in **allen** Presets |

Zusätzlich: die Liste ist **pro Preset, nicht pro Item-Typ** — für StakeholderNeed/TestCase/Adr/Risk/
Issue/Goal sind die Feldnamen sinnlos. Bereits gemeldet als **#912**.

### 2.3 Die 11 Typen und ihr heutiger Attributumfang

| Typ | n | Attribute |
|---|:--:|---|
| **Requirement** | 11 | uid, category, type, level, complexity_fibonacci, verification_method, status, title, description, description_editor, acceptance_criteria |
| **StakeholderNeed** | 6 | uid, category, moscow_priority, status, title, description |
| **ArchitectureElement** | 9 | uid, element_type, status, title, description, description_editor, parent_id, asil_level, make_or_buy |
| **TestCase** | 6 | uid, test_type, status, title, description, steps |
| **Adr** | 8 | uid, status, title, description, context, decision, consequences, decision_record |
| **Risk** | 12 | uid, category, probability, impact, detection, risk_matrix, status, title, description, owner, owner_user_id, mitigation_strategy |
| **Issue** | 8 | uid, category, status, title, description, severity, due_date, tag_list |
| **Goal** | 3 | status, title, description |
| **Icd** | 7 | status, source_element_id, target_element_id, name, direction, interface_type, semantic_description |
| **GlossaryTerm** | 4 | status, term, definition, abbreviation |
| **ChangeRequest** | 7 | status, title, description, impact_assessment, change_reason, requestor_id, assigned_reviewer_id |

---

## 3. Vorhandene Vorarbeiten (gefunden und bewertet)

### 3.1 `docs/archive/audits/SYSTEMAUDIT_SE_METHODOLOGY_2026-08-07.md` — SE-Methodik-Audit

Relevante Empfehlungen wörtlich:

| Prio | Punkt | Inhalt |
|---|---|---|
| P2 | **9** | „`acceptance_criteria`, `level` und ein neues `rationale` in den **Baseline-State** aufnehmen. Eine Baseline ohne Akzeptanzkriterien ist als Verifikationsreferenz untauglich." |
| P2 | **10** | „`Requirement.level` in Serializer und MCP-Schema exponieren, mit Konsistenzprüfung gegen die Elternebene." |
| P4 | **17** | „**`Measure`-Entität für MOE/MOP/TPM** einführen. Ohne sie bleibt ReqogniLoom ein Requirements-Tracking-Werkzeug und wird kein SE-Steuerungswerkzeug." |
| P4 | **19** | „Validierungsebene aktivieren: `Goals` per Default an, plus Auditregel ‚jedes L0-Need trägt zu mindestens einem Goal bei'." |
| P4 | **20** | „**Pflichtfelder je Rigor-Stufe:** ab `standard` `acceptance_criteria` und `verification_method` verpflichtend; `rationale`-Feld ergänzen." |
| P1 | 1 | „**Fehlende Endpunkt-Gruppe für Requirement-Attribute**" |

Achsenurteil: **A. Requirements = ⚠️ Mittel** („Syntax/Rationale nicht erzwungen; `level` nicht
befüllbar; AC/VM optional und flüchtig") — die schlechteste der vier Achsen.

### 3.2 Die zugehörigen GH-Issues (alle offen)

| # | Label | Konkreter Vorschlag (Zitat) |
|---|---|---|
| **#871** | `high, se, data-model` | DoD: „Felder **`rationale` (TextField)**, **`source` (CharField)**, **`owner` (ForeignKey to User)** und **`priority` (CharField: High/Med/Low)** in `backend/persistence/models.py` ergänzen." + Serializer + `RequirementForm.tsx` |
| **#583** | `high, qa, se` | „rationale-Feld im Datenmodell, uid-Autogenerierung, AC/verification_method als Gate im **extended**-Preset." Belege: `uid=null` 100 %, AC 0/50, VM 0/50 |
| **#408** | `medium, se, data-model` | „Pflichtfelder je Rigor-Stufe einführen: **ab `standard` `acceptance_criteria` und `verification_method` verpflichtend**. Neues `rationale`-Feld ergänzen." |
| **#393** | `critical, se, data-model` | „Eigene Entität **`Measure`** mit `kind ∈ {MOE, MOP, TPM}`, `unit`, `target_value`, `threshold`, `current_value`, `measured_at` sowie **Zeitreihe**" |
| **#394** | `high, se` | `Requirement.level` (L0–L4) über REST/MCP nicht setzbar, in der UI unsichtbar |
| **#426** | Sammel-Issue | Index des Audits (16 Einzelbefunde) |

### 3.3 Weitere relevante Befunde aus dem Audit (mit Bestandsdaten)

- **`verification_method` wird bei unbeteiligten PATCH-Aufrufen still gelöscht** — „2731 von 2735
  Requirements haben keine Verifikationsmethode."
- **`uid` = null bei 100 %** der Stichprobe in zwei Workspaces (#583).
- **Was fälschlich für TPM gehalten werden könnte:** `backend/se_metrics/` + Dashboard-Schellwerte sind
  **Prozessmetriken** (Coverage %, Volatilität, Workflow-Lücken), **keine** Produkt-Leistungsgrößen.
- **Custom Fields taugen nicht für TPM** — `CustomFieldType` hatte nur `text|number|dropdown`, die
  MCP-Gruppe `custom_field` war read-only.

---

## 4. Challenge — wo die Vorarbeiten meinen Entwurf korrigieren

### C1 — Mein Ansatz trägt: Extended Attributes SIND baseline-sichtbar (Audit-Aussage veraltet)

Der Audit (2026-08-07) begründete die Forderung nach Modellfeldern u. a. mit:
> „Custom Fields … (`backend/persistence/models.py:276-288`) kennt exakt drei Typen … Über MCP nicht
> einmal anlegbar."

**Das ist durch die Attribut-Definition v2 überholt:**
- `ATTRIBUTE_TYPES` (`schema.py:38-43`) umfasst heute **10 Typen**:
  `text, textarea, number, boolean, enum, multi-enum, date, reference, user, widget`.
- MCP-Gruppe `attribute_definition` existiert (`tool_registry.py:290-296`) mit `list`/`get` (read) und
  `update`/`reset` (**admin-gated write**) — ein Agent kann Definitionen also lesen, ein Admin sie ändern.
- Definitionen sind **pro `(tenant, item_type, preset)`** auflösbar (`AttributeDefinitionService.resolve`
  → `_workspace_preset()`), also genau der Träger, den ein Stufenmodell braucht.

**Und der entscheidende Punkt:** der Baseline-State erfasst `Artifact.custom_fields` **als Ganzes** —
`state_capture.py:46` (`"custom_fields": custom_fields or {}`). Der Docstring sagt es explizit:
> „… missing … `Artifact.custom_fields` (**which is where user-defined attributes such as a
> ‚rationale' live**) … Before #398 the map was missing `Requirement.acceptance_criteria` / `level` …"

→ **Die Befürchtung „ein Extended Attribute wäre in der Baseline unsichtbar" ist falsch.** Der
`#398`-Fix hat diesen Pfad geschlossen. Ein neues Attribut erscheint im Baseline-Diff, sobald es in
`custom_fields` liegt.

**Konsequenz für meinen Vorschlag:** Die Feld-vs-Attribut-Entscheidung darf **nicht** mit
Baseline-Sichtbarkeit begründet werden — sie ist bei beiden Wegen gegeben.

### C2 — Mein Vorschlag war zu schwach: MOE/MOP/TPM brauchen eine eigene Entität (KORREKTUR)

In v1.0 hatte ich `measure`, `target_value`, `unit`, `threshold` als **Attribute auf `Goal`**
vorgeschlagen. Der Audit begründet überzeugend das Gegenteil:
> „Ein TPM benötigt mindestens: Ist-Wert, Zielwert, Schwellwert, Marge, Einheit, Messzeitpunkt und einen
> **Zeitverlauf** … Die klassische TPM-Verlaufsdarstellung (z. B. Massenmarge gegen Allokation über die
> Zeit) ist damit nicht darstellbar."

Ein JSONB-Attribut speichert einen **Skalar**, keine **Zeitreihe**. Für Trend/Marge braucht es eine
eigene Entität mit Historie.

**Korrektur:** `Measure`-Entität (`kind ∈ {MOE, MOP, TPM}`) bleibt das Ziel für **Stufe 3** (#393).
Als **Stufe-2-Interim** sind statische Attribute auf `Goal` (`measure_name`, `target_value`, `unit`,
`threshold`) legitim — sie liefern Zielwert/Schwelle ohne Trend. Ich stufe sie damit von „Stufe 3"
auf „Stufe 2 (Interim), Stufe 3 = Entität" herunter und kennzeichne sie als migrierbar.

### C3 — Feld-vs-Attribut: die Entscheidung braucht andere Kriterien (PRÄZISIERUNG)

Da C1 beide Wege für baseline-fähig erklärt, entscheide ich neu:

| Kriterium | → Modellfeld | → Extended Attribute |
|---|---|---|
| Muss **sortier-/filterbar** in SQL sein (Backlog, Dashboards) | ✅ | ◐ (GIN, JSONB-Pfad) |
| Muss im **OpenAPI/MCP-Schema** als erstklassiges Feld erscheinen | ✅ | ✖ (nur über `custom_fields`) |
| **Relationale Integrität** (FK auf User/Artefakt) | ✅ | ◐ (`user`/`reference`-Typ, unindexiert) |
| Muss **pro Tenant/Preset konfigurierbar** sein | ✖ | ✅ |
| Soll **ohne Migration** änderbar sein | ✖ | ✅ |
| Ist **normativ auf jedem Artefakt dieses Typs** | ✅ | ✖ |
| Braucht **Historie/Zeitreihe** | ✅ (eigene Entität) | ✖ |

**Empfehlung — Hybrid:**
- **Modellfelder** nur für die vier ISO-29148-Kernattribute auf `Requirement`: **`rationale`, `source`,
  `priority`, `owner`** (deckt sich mit dem DoD von #871 und dem Ziel von #583/#408).
  Begründung: `priority`/`owner` werden gefiltert und sortiert; alle vier müssen im API-/MCP-Schema
  stehen, weil Agenten sie schreiben; alle vier sind normativ auf **jedem** Requirement.
- **Alles Weitere** (difficulty, criticality, verification_status, validation_method, origin_link,
  Stakeholder-Kontext, Testfall-Vollständigkeit, ADR-Alternativen, Icd-Payload, ChangeRequest-CCB …)
  über die **Attribut-Definition v2** — konfigurierbar je Tier/Tenant, keine Migration.
- **MOE/MOP/TPM** → eigene `Measure`-Entität.

### C4 — `verification_method` als Pflicht erst nach dem PATCH-Wipe-Fix (ABHÄNGIGKEIT)

Audit: „**2731 von 2735** Requirements haben keine Verifikationsmethode", Ursache ist ein
still löschender PATCH-Pfad. #408/#583 wollen `verification_method` **ab `standard` verpflichtend**.

**Konsequenz:** Mein Stufe-2-Vorschlag macht `verification_method` ebenfalls verpflichtend — aber das
ist **erst sinnvoll, wenn der Wipe behoben ist**. Sonst entsteht eine Anforderung, die der Nutzer
erfüllt und die ihm beim nächsten Speichern wieder entzogen wird. Ich setze das deshalb als
**Vorbedingung D1** in die Umsetzungsreihenfolge.

### C5 — `level` und `uid` sind heute nicht benutzbar (ABHÄNGIGKEIT)

- `Requirement.level` (V-Modell L0–L4) ist über REST/MCP nicht schreib- und lesbar (**#394**).
- `uid` ist „= null bei 100 % der Stichprobe" (**#583**) — obwohl es als Attribut definiert ist.

Mein Stufenmodell setzt `level` in **Stufe 2** und `uid` in **Stufe 1** (als Identifikation). Beides ist
ohne Fix nicht erfüllbar → **Vorbedingungen D2/D3**.

### C6 — Der Träger der Stufen ist defekt (ABHÄNGIGKEIT)

`mandatory_fields` gilt **pro Preset, nicht pro Item-Typ** (`registry.py:154-215`). Für 10 von 11 Typen
sind die Feldnamen sinnlos (**#912**). Mein Modell braucht Stufen **je Typ**. → **Vorbedingung D4**.

### C7 — `priority`-Skala: drei konkurrierende Vorschläge (OFFENER KONFLIKT)

| Quelle | Vorschlag |
|---|---|
| #871 | `priority` CharField: **High/Med/Low** |
| Bestand | `moscow_priority` auf StakeholderNeed: **MoSCoW** |
| ISO 29148 / mein v1.0 | **Stakeholder-Priority** (Skala freigestellt) |

Drei Skalen für dieselbe Sache wären ein neuer Inkonsistenz-Befund. **Empfehlung:** **eine** Skala für
alle Typen — **MoSCoW** (bereits im Bestand, im Requirement-Kontext interpretierbar als
Must = verpflichtend für die nächste Baseline). Ich übernehme damit **nicht** #871s High/Med/Low und
weiche bewusst ab; das ist im Report zu markieren.

### C8 — Der Audit unterschätzt die Attribut-Definition v2 (BEWERTUNG)

Autorität des Audits in allen SE-Fragen: **hoch** (live gegen die Instanz belegt, §5-Schlussbemerkung
ist fachlich präzise). Seine **technische** Aussage zu „Custom Fields" ist jedoch gegen das **alte
`CustomField`-Modell** geschrieben und seit der Attribut-Definition v2 (Spec `2026-09-11`) überholt
(siehe C1). Ich folge ihm fachlich, präzisiere ihn technisch.

### C9 — `uid` ist **nicht** „auto-generated": das Feld ist ein gebrochenes Versprechen (KORREKTUR + NEUER BEFUND)

**Ausgangsfrage:** „Das `uid` wird doch vom System automatisch generiert — warum also ein Pflichtfeld?"

**Antwort nach Prüfung: Es wird NICHT generiert.** Der Modell-`help_text` behauptet es nur:

```python
# backend/persistence/models.py:969-974  (identisch in 8 Modellen)
uid = models.CharField(
    max_length=64, null=True, blank=True,
    help_text="Unique identifier (read-only, auto-generated)",
)
```

| Prüfung | Befund |
|---|---|
| 8 Modelle behaupten `"(read-only, auto-generated)"` | `models.py:973, 1059, 1187, 1558, 1671, 2524, 2657, 2890` |
| **Generator-Funktion vorhanden?** | **Nein.** Kein `def generate_uid`, kein Signal, kein Service. Die 8 Grep-Treffer sind ein **Validator** (`_assert_uid_unique_in_workspace`, `requirement_service.py:193`) und **Migrations-Helfer** (`migrate_se_docs`, `_dedupe_uid_collisions`) |
| Service-Signatur | `create_requirement(..., uid: Optional[str] = None, ...)` — **Durchreiche-Parameter, Default `None`** |
| Serializer | 8× `uid = serializers.CharField(read_only=True, allow_null=True)` → **kein Client kann es setzen** |
| Live-Bestand | **0 von 6** Requirements mit `uid` (deckt sich mit #583: „uid = null bei 100 %") |
| Wer füllt es überhaupt? | nur **Import/Migration**: `reqif_import_service.py:562/698`, `migrate_se_docs` |

**Ergebnis:** Für jedes normal angelegte Artefakt bleibt `uid` **dauerhaft NULL** — weder der Nutzer noch
ein Agent kann es setzen (read-only), und das System tut es nicht. Der `help_text` beschreibt einen
Zustand, den der Code nicht herstellt.

**Korrektur an meinem Modell:** `uid` ist **system-owned** (wie `status`) und **kein** Stufe-1-Pflichtfeld
für den Nutzer. Meine v1.0-Tabelle markierte es fälschlich mit „✅P". Richtig ist:

| | SOLL |
|---|---|
| Träger | system-owned, read-only |
| Sichtbarkeit | in allen Stufen **sichtbar** (Identifikation), aber nie editierbar |
| Pflicht | **nie** als Nutzer-Pflicht — der Nutzer kann es nicht liefern |
| Erzeugung | **muss implementiert werden**: `{PREFIX}-{NNN}` je `(workspace, item_type)`, eindeutig (Constraint aus Migration `0055` existiert bereits), nie wiederverwendet |
| Stufe 1 „Identifikation" | `title` (Nutzer) **+** system-generierte `uid` |

**Konsequenz für D3:** Die Vorbedingung heißt jetzt präzise „**die zugesagte Autogenerierung existiert
nicht** — Versprechen einlösen **oder** `help_text` korrigieren". Das ist eine eigenständige, klar
abgegrenzte Aufgabe und der eigentliche Kern von #583.

---

## 5. Der korrigierte Vorschlag

### 5.1 Stufendefinition (unverändert zu v1.0)

| Stufe | Leitidee | Träger |
|---|---|---|
| **1 Basissatz** | „anlegbar, identifizierbar, auffindbar" — alles andere optional | Preset `minimal` |
| **2 Gehobene Stringenz** | „wer will es, warum, wie prüfen wir es, wie wichtig" | Preset `standard` |
| **3 Full-Blown SE** | „lückenlose SE-Kette": Rückverfolgbarkeit, Risiko, Kritikalität, MOP/TPM, Change Control | Preset `extended` |

### 5.2 Gruppierung (Sections, für alle Typen)

`identification` · `content` · `classification` · `attribution` · `verification` · `traceability` ·
`change_control` · `type_specific`

### 5.3 Requirement — Kern der Korrektur

| Gruppe | Attribut | Träger | S1 | S2 | S3 | Norm | Begründung |
|---|---|:--:|:--:|:--:|:--:|---|---|
| Identifikation | `uid` | **system-owned** | ◐ auto | ◐ auto | ◐ auto | 29148 §5.2.3 | **nicht vom Nutzer zu füllen** (read-only, system-generiert) → **C9/D3** |
| Identifikation | `title` (Heading) | Modellfeld | ✅ **P** | ✅P | ✅P | 29148 Heading | heute bereits die einzige Pflicht |
| Inhalt | `description` | Modellfeld | ○ | ✅ **P** | ✅P | 29148 Text | ohne Inhalt kein Artefakt → **Stufe-1-Frage** |
| Inhalt | `acceptance_criteria` | Modellfeld | ○ | ✅ **P** | ✅P | 29148 §5.2.5 | Audit P4-20 + #408: ab standard Pflicht |
| **Attribution** | **`rationale`** | **Modellfeld** | – | ✅ **P** | ✅P | 29148 Rationale | **#871 + Audit P4-20**; NASA-Forderung „warum" |
| **Attribution** | **`source`** | **Modellfeld** | – | ✅ | ✅P | 29148 Source | **#871**; Herkunft/Stakeholder |
| **Attribution** | **`owner`** | **Modellfeld** (FK) | – | ○ | ✅P | 29148 Owner | **#871**; Zuweisung braucht Sortierung/Join |
| **Klassifikation** | **`priority`** | **Modellfeld** | – | ✅ **P** | ✅P | 29148 Priority | **Preset fordert es schon**, Feld fehlt. Skala: MoSCoW (C7) |
| Klassifikation | `type`, `level` | Modellfeld | – | ✅ | ✅P | 29148 Type / 15288 | `level` heute nicht exposiert → **D2 (#394)** |
| Klassifikation | `difficulty` | Attribut | – | ○ | ✅ | 29148 Difficulty | Aufwandsschätzung, selten gefiltert |
| Klassifikation | `criticality` | Attribut | – | ○ | ✅ | 26262 | Safety/Security-Einstufung |
| Verifikation | `verification_method` | Modellfeld | – | ✅ **P** | ✅P | 29148 VerMethod | Audit P4-20/#408 — **aber erst nach D1 (Wipe-Fix)** |
| Verifikation | `verification_status` | Attribut | – | ○ | ✅ | 15288 | Nachweis „verifiziert" pro Requirement |
| Verifikation | `validation_method` | Attribut | – | – | ✅ | 29148 §5.2.5 | Validierung ≠ Verifikation |
| Traceability | `allocated-to` | TraceLink | ○ | ✅ | ✅P | 15288 | coverage-relevant (siehe #928) |
| Traceability | `derives-from` | TraceLink | ○ | ✅ | ✅P | 29148 | Herkunftskette |
| Traceability | `origin_link` | Attribut | – | ○ | ✅ | 29148 §5.2.8 | Referenz auf die Quellpassage |
| Traceability | **MOP/TPM-Bezug** | **`Measure`-Entität** | – | ○ (Attribut-Interim) | **✅P (Entität)** | INCOSE/NASA | **C2/#393**: Skalar ≠ Zeitreihe |
| Änderungskontrolle | `change_reason` | Modellfeld | – | ○ | ✅ **P** | 15288 | Existenzbegründung ≠ Änderungsbegründung (Audit P4-20) |

### 5.4 Die anderen 10 Typen — Kurzfassung der Änderungen ggü. v1.0

| Typ | Neu in Stufe 2 (Pflicht fett) | Neu in Stufe 3 | geändert ggü. v1.0 |
|---|---|---|---|
| **StakeholderNeed** | **`stakeholder`**, `rationale`, **`validation_criteria`** | `concern`, `effect_measure`, `owner` | unverändert |
| **ArchitectureElement** | `rationale`, `interfaces` sichtbar | `viewpoint`, `performance_budget`, `verification_method`, `technology` | unverändert |
| **TestCase** | **`expected_result`**, **`preconditions`**, `objective`, **`priority`**, **`verifies`** | `test_data`, `test_environment`, `postconditions`, `test_level`, `review_status` | + `verifies` als Pflichtkette |
| **Adr** | **`alternatives`**, `deciders`, `decided_at` | `supersedes`, `affects`, `decision_drivers` | unverändert |
| **Risk** | `severity`/RPN, `residual_risk`, `response_strategy` | `affects`, `risk_type`, `review_cycle` | unverändert |
| **Issue** | **`priority`**, `assignee` | `resolution`, `root_cause`, `affects` | unverändert |
| **Goal** | `owner`, `timeframe`, **`measure_name`**, `target_value`, `unit`, `threshold` *(Interim)* | **`Measure`-Entität** statt Attribute | **korrigiert (C2)** |
| **Icd** | **`data_elements`**, `protocol`, `version` | `timing`, `safety_classification` | unverändert |
| **ChangeRequest** | **`affected_artifacts`**, **`ccb_decision`**, `change_class` | `target_baseline`, `verification_of_change` | unverändert |
| **GlossaryTerm** | – (ausreichend) | `synonyms`, `source`, `owner` | unverändert |

---

## 6. Umsetzungsreihenfolge mit Abhängigkeiten

**Vorbedingungen (müssen vor dem Stufenmodell laufen):**

> **Korrektur nach Duplikat-/Status-Prüfung (11.09.2026):** Zwei der ursprünglich vier Vorbedingungen
> sind **bereits erledigt**:
> - **D1 (verification_method-Wipe) → GESCHLOSSEN** als **#409** (closed 2026-08-12, Commit `4b0eab79`).
> - **D2 (`level` nicht exposiert) → GESCHLOSSEN** als **#394** (closed 2026-08-13).
>   Verifiziert live: `level` steht im Requirement-Response und ist befüllt (1/6 im QS-Workspace).
>
> Damit bleiben **zwei** echte Vorbedingungen.

| ID | Vorbedingung | Bezug | Status | Warum blockierend |
|---|---|---|---|---|
| ~~D1~~ | ~~`verification_method`-Wipe bei unbeteiligten PATCH~~ | ~~Audit Befund 4~~ | **✅ erledigt** (#409) | – |
| ~~D2~~ | ~~`Requirement.level` in Serializer + MCP-Schema~~ | ~~#394~~ | **✅ erledigt** (#394) | – |
| **D3** | **`uid`-Autogenerierung implementieren** — der `help_text` in 8 Modellen verspricht „auto-generated", es gibt aber keinen Generator (live: **0/6** gefüllt, read-only im API). Entweder Versprechen einlösen oder `help_text` korrigieren | **#583** + **C9** | **offen** | Stufe 1 zeigt `uid` als Identifikation; ein dauerhaft leeres Feld ist keine Identifikation |
| **D4** | `mandatory_fields` je `(item_type, preset)` auflösen — oder ganz auf `required` der Attribut-Definition umstellen | **#912** | **offen** | sonst hat das Stufenmodell keinen Träger (C6) |

**Bezug zu bestehenden Umbrella-Issues:** **#920** („Bundle B2 — Artefakt-/Attributfelder konsistent",
P1) sammelt #886/#887/#889/#816/#820. Das Stufenmodell berührt diese Punkte, **ersetzt sie aber nicht** —
es referenziert sie und bleibt auf der Meta-Ebene (Stufen/Pflichtgrade), nicht auf der
Einzelfeld-Konsistenz.

**Danach:**

| Schritt | Inhalt | Abhängig von |
|---|---|---|
| 1 | Modellfelder `rationale`, `source`, `owner` (FK), `priority` auf `Requirement` + Serializer + Form | #871 |
| 2 | `priority`-Skala vereinheitlichen (MoSCoW für alle Typen) | C7-Entscheidung |
| 3 | Sections anlegen + Definitionen je `(item_type, preset)` seeden (Stufe 1/2/3) | D4 |
| 4 | `required`/`visible`/`audience` je Stufe setzen | 3 |
| 5 | `Measure`-Entität (`kind`, `unit`, `target_value`, `threshold`, `current_value`, `measured_at` + Zeitreihe) | #393 |
| 6 | Goal-Attribute auf `Measure` migrieren | 5 |
| 7 | SE-Auditor-Regeln an Stufe 3 koppeln (`REQ_MUST_HAVE_ALLOCATION`, `REQ_MUST_HAVE_TEST_LINK`, `REQ_MUST_HAVE_SOURCE`) | 4, #19 |

---

## 7. Offene Entscheidungen (mit meiner Empfehlung)

| # | Frage | Empfehlung |
|---|---|---|
| 1 | Stufe 1: nur `title` (heute) oder `title`+`description`? | **`title`+`description`** — ein Artefakt ohne Inhalt ist wertlos; `description` ist ohnehin schon überall da |
| 2 | `priority`-Skala | **MoSCoW** für alle Typen (Bestand-kompatibel, eine Skala) — **weicht bewusst von #871 ab** |
| 3 | `rationale` ab Stufe 2 Pflicht? | **Ja**, aber erst nach Schritt 1 (Modellfeld) und mit Prompt-Slot-Nachbesserung (`#583` nennt die Prompt-Schwäche) |
| 4 | Kritikalitäts-Skala | **generisch** `low/medium/high/critical`; `asil_level` bleibt als separates Attribut am ArchitectureElement |
| 5 | Traceability Pflicht ab Stufe 3 | **Ja, blockierend über den SE-Auditor** (konsistent zu #19) |
| 6 | `Measure` jetzt oder später? | **Später (Schritt 5)**, aber `kind`/`unit`/`target_value` bereits jetzt als Goal-**Attribute** anlegen und als migrierbar kennzeichnen |
| 7 | Soll ich das als GH-Issue anlegen? | **Ja** — Master-Issue „3-Stufen-Attributmodell" + Querbezug zu #871/#583/#408/#393/#394/#912/#19 |
