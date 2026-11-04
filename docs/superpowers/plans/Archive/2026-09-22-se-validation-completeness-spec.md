---
type: SPEC
scope: cluster-5-se-validation-completeness
status: draft
revision: 3
date: 2026-09-22
author_agent: concept-specifier
issues: [424, 402, 399, 272]
branch: feat/se-validation-completeness
base: main @ 38a57161
bundle_plan: docs/superpowers/plans/2026-09-21-open-issues-bundle.md
resolves_review:
  - docs/superpowers/plans/2026-09-22-se-validation-completeness-review.md
  - docs/superpowers/plans/2026-09-22-se-validation-completeness-review-rev2.md
---

# Cluster 5 — SE-Completeness: Validierung als First-Class-Pillar

Technische Spezifikation für die Issues **#424**, **#402**, **#399**, **#272** (Rest).
Design only — dieses Dokument enthält **keine** Implementierung und **keine** Migration-Dateien.
Signaturen und Feldnamen sind verbindliche Interface-Contracts, keine Code-Vorschläge.

> **Revision 2** löste den Review-Befund `CHANGES_REQUESTED`
> (`docs/superpowers/plans/2026-09-22-se-validation-completeness-review.md`) auf.
> **Revision 3** löst den zweiten Review-Befund `CHANGES_REQUESTED`
> (`docs/superpowers/plans/2026-09-22-se-validation-completeness-review-rev2.md`) auf:
> die drei neuen Majors **N1** (Severity-Override für `VAL-P1`), **N2** (TenantContext
> save/restore) und **N3** (zweiter LLM-TestCase-Producer) sowie die Minor **N6**
> (historische Models in `0100`).
> Die vollständige Auflösungs-Matrix (M1–M4, m1–m11, i1–i3) steht in **§13**;
> die v2→v3-Auflösung (N1–N3, N6) steht in **§14**.

## 1. Scope & Kontext

### 1.1 Was gebaut wird

| Issue | Ziel in einem Satz |
|-------|--------------------|
| #424 | TestCases erhalten Herkunft (`origin`) und Review-Status (`reviewed`); **alle drei** Coverage-/Verifikations-Consumer werten unreviewte KI-TestCases nicht mehr als vollwertige Abdeckung. **Und alle drei LLM-getriebenen TestCase-Produzenten markieren ihre Zeilen als `ai_generated`/`unreviewed`** (§4.8). |
| #402 | Goals werden per Default aktiviert; eine neue Audit-Regel `VAL-P1` fordert Stakeholder-Goal-Traceability; TestCases erhalten eine Off-Nominal-Kategorie. |
| #399 | Baseline-Mitgliedschaft erzeugt eine **sichtbare, dauerhafte Drift-Kennzeichnung** am Artefakt (kein Hard-Block, siehe D1). |
| #272 | Rest: `verification_method` im AC-Gate, Link-Validierung gegen gelöschte Artefakte, Requirement→Test-Coverage-Report, `content_available`-Semantik für v0, realistische Demo-Fixture. |

### 1.2 Was explizit nicht gebaut wird

- **Kein Hard-Block** für Edits an baselinierten Artefakten ohne genehmigten CR (Entscheidung **D1**, §2).
- **Keine** Neuerfindung der Link-Type-Kompatibilität (`link_types/catalog.py::validate_link_pair` existiert).
- **Kein** neues TestResult-Vokabular (`TestRunResult` Enum existiert).
- **Keine** `Measure`-Entity, keine Milestones, keine ReqIF-Identität (Cluster 6).
- **Kein** `findings`/`finding_key`-Waiver (Issue **#569**, Cluster 2) — **out of scope für Cluster 5**. Die neuen Findings von `VAL-P1` laufen durch die bestehende, noch instabile Finding-Identität; das ist akzeptiert und wird nicht hier gelöst.
- **Kein** rückwirkender Backfill von Erzeugungsinhalten für Pre-Phase-5-Artefakte ohne Revision 1 (offene Frage F3).
- **Keine** nachträgliche KI-Erkennung bestehender TestCases im Migrationslauf; sie ist als Folgeschritt F7 spezifiziert (nicht Teil der drei Migrationen, siehe §4.2).

### 1.3 Betroffene Subsysteme

`persistence` (2 Modelle + 2 Migrationen), `link_types` (Katalog + Migration), `traceability` (Coverage + `coverage_calculator`-Prädikat + neue Audit-Regel **inkl. `severity_for_tier`-Override** + VERIF-P8), `workflow.precondition_rules` (Verifikations-Evidenz), `application` (Test-, Baseline-, Requirement-, Change-Request-Service, **`interview_artifact_adapters`**), `rest_api` (3 Serializer, 4 Actions), `mcp_server` (test-Tool-Gruppe + `test.mark_reviewed`), `frontend` (TestCase-Liste/Formular, Requirement-Editor), `auth_tenancy.management.commands` (Fixture).

---

## 2. Mandatierte Entscheidungen (revidiert)

### D1 — #399: Baseline-Mitgliedschaft koppelt an Change Control

**Entscheidung: Klare Drift-Kennzeichnung (Option B). Kein Hard-Block ohne genehmigten CR in diesem Cluster.**

Begründung (unverändert gegenüber v1):

1. **Es gibt keinen „aktiven" Baseline-Begriff.** `BaselineSnapshot` ist eine unveränderliche Momentaufnahme; ein Workspace kann beliebig viele Baselines über drei Scopes halten (`bl_baseline_snapshot`, `scope ∈ {document, project, global}`). Ein Hard-Block müsste entscheiden, *welches* Baseline-Approval verlangt wird. Da `BaselineDeltaIndexEntry` bei project/global-Scope praktisch jedes Artefakt enthält, würde ein „blockiere, wenn irgendwo baseliniert" viele Artefakte dauerhaft einfrieren — ein Daten- und Usability-Fallstrick, kein Sicherheitsgewinn.
2. **Der Edit-Pfad hat keinen CCB-Kontext.** `RequirementService.update_requirement` / `TestService.update_test_case` kennen keinen ChangeRequest, keinen Reviewer und keine Separation-of-Duties (die lebt in `change_request_service.transition_status`). Ein Hard-Block müsste die CCB-Semantik in jeden Update-Pfad duplizieren — das widerspricht dem Single-Entry-Point-Pattern (ADR-01).
3. **Die bestehende `change_reason`-Policy ist eine Begründungspflicht, keine Freigabe.** `presets/registry.py` liefert `change_reason ∈ {optional, optional, mandatory}` für minimal/standard/extended; erzwungen wird nur „non-empty" in `workflow/transition_validator.py` und `requirement_service.py`. Ein Hard-Block würde diese Policy stillschweigend zu einer Approval-Policy umdeuten — ohne Reviewer, ohne SoD, ohne CR.
4. **Das Issue verlangt „mindestens deutliche Drift-Kennzeichnung".** Genau das wird geliefert: deterministisch, testbar, reversibel und kompatibel mit der unveränderlichen Baseline.

**Zusätzlich (der eigentliche fachliche Mehrwert):** Der Editor bietet an einem gedrifteten Artefakt einen direkten Einstieg in den CCB-Pfad. Der CR wird *vor* die Änderung gezogen, ohne den Edit technisch zu sperren.

**Mechanik-Korrekturen aus dem Review (M4 der Review / m4):**

- **Global-Scope ist eine Tenant-, keine Workspace-Frage.** `BaselineMetadata.workspace_id` eines `scope="global"`-Baselines ist der *aufrufende* Workspace; der Delta-Index enthält aber Artefakte aller Workspaces des Tenants (`ScopeResolver._resolve_global`). Die Mitgliedschafts-Suche darf deshalb **nicht** pauschal auf `workspace_id = <Artefakt-Workspace>` filtern (siehe §6.2).
- **`capture_states` braucht einen aktiven `TenantContext`.** Die Status-Auflösung läuft über `WorkflowItemState.objects` (tenant-*scoped*) und ignoriert das explizite `tenant_id`; ohne aktiven Kontext kommen alle Status leer zurück (stille Drift-Fehldeutung). Der Retrieve-/Service-Pfad muss den Kontext armen (siehe §6.2).
- **CR-Prefill braucht einen deklarierten Contract.** `POST /api/v1/change-requests/` akzeptiert heute **keine** `affected_item_ids` (`ChangeRequestSerializer` deklariert das Feld nicht, `ChangeRequestViewSet.create` reicht es nicht durch). Es wird additiv als write-only-Feld ergänzt (§6.3).

**Verworfene Option (dokumentiert):** Hard-Block via genehmigtem CR. Braucht einen eigenen ADR (Edit-Pfad → CCB-Kontext, Auflösung „welche Baseline", Rollback/Re-Baseline-Prozess) und ist ein eigener Cluster, nicht Teil von #399-`mindestens`.

### D2 — #402: `goals_enabled`-Default

**Entscheidung: Default wird auf `True` geflippt. Bestehende, nicht geschlossene Workspaces werden per RLS-sicherer Datenmigration aktiviert. `goals_ai_enabled` bleibt `False`. `VAL-P1` startet als `WARNING`.**

| Ebene | Ist | Soll |
|-------|-----|------|
| `Workspace.goals_enabled` (Model) | `default=False` | `default=True` (`AlterField`) |
| `WorkspaceSerializer.goals_enabled` | `BooleanField(required=False, default=False)` | `default=True` |
| `workspace_service.create_workspace(goals_enabled=None)` | `None` → Model-Default | unverändert; `None` → jetzt `True` |
| Bestehende Workspaces | gespeichertes `False` | Datenmigration: `True` für `is_active=True` (**RLS-sicher**, §5.1) |
| `goals_ai_enabled` | `False` | **unverändert `False`** (keine unangekündigte LLM-Generierung) |
| `VAL-P1`-Severity | (neu) | **`WARNING`** — advisory, **kein** Baseline-Gate (§5.4) |

**Rollout-Implikationen:**

- Das Flag gatet ausschließlich Schreib-CRUD (`goal_service.create_version`, `main_goal_service.create_manual/generate_ai`, `rest_api/views.py` Goal-Endpunkte). Ein Flip aktiviert eine rein additive Fähigkeit.
- `VAL-P1` ist **doppelt gegated** (`goals_enabled == True` **und** ≥1 aktives Goal im Workspace, §5.3). Ein Workspace mit 0 Goals (z. B. 2735 Requirements / 0 Goals) bekommt **kein** Finding.
- **Kein rückwirkender Baseline-Blocker:** `VAL-P1` ist `WARNING`; `BaselineFacade._enforce_audit_gate` → `AuditService.blocking_findings` gibt ausschließlich `Severity.BLOCKER` zurück (`test_baseline_audit_gate.py::...only BLOCKER severity gates; WARNING findings are advisory`). Bestehende, Goal-nutzende Extended-Workspaces (Estate: 4 Goals / 2 MainGoals) erhalten beim nächsten Baseline-Build **kein** Gate-Blocking. Eskalation auf BLOCKER ist als F8 geplant.
- Geschlossene Workspaces (`is_active=False`) werden nicht angefasst.
- Die Datenmigration ist fachlich einseitig; `reverse_code` ist ein dokumentierter No-op (kein Marker, welche Zeile vorher `False` war).
- **Testbruch ist eingeplant und korrigiert** (§5.1): Default-Assertions auf `False` müssen mitgezogen werden. **Brechend:** `persistence/tests/test_workspace_goals_fields.py:17`, `application/tests/test_goal_service.py:102-114`, `application/tests/test_main_goal_service.py:113-123`, `rest_api/tests/test_workspace_goals_rest.py`, `rest_api/tests/test_workspace_create_schema_conformance.py:121`. **Nicht brechend** (explizites `goals_enabled=False`): `rest_api/tests/test_goal_views.py:90`.

---

## 3. Gemeinsame Invarianten

- **RLS (Schema):** Neue Spalten auf `TestCase` (bereits `TenantScopedModel`) erben die bestehende Policy auf `pl_testcase` — **keine neue RLS-Migration**. `Workspace.goals_enabled` ist `AlterField` — keine Policy-Änderung. Es entstehen **keine neuen Tabellen** in diesem Cluster.
- **RLS (Datenmigrationen):** `pl_testcase` und `pl_workspace` sind `FORCE ROW LEVEL SECURITY` auf `app.current_tenant` (`persistence/migrations/0003_rls_policies.py:46-58`). Jede **Daten**-Operation in einer Migration muss den Tenant-Kontext pro Tenant armen (`SET app.current_tenant`, Muster `link_types/0005`) **oder** `SET LOCAL row_security = off` setzen und das Ergebnis laut assertieren. **M1 (`0099`) ist schema-only und braucht keine Arming-Logik** (§4.2); **M2 (`0100`) enthält eine Datenoperation und armt pro Tenant** (§5.1).
- **Baseline-Mitgliedschaft ist RLS-sensitiv:** `BaselineDeltaIndexEntry` ist ein plain Model **ohne** Tenant-Spalte. Jeder Membership-/Drift-Zugriff läuft zwingend über den tenant-geprüften Ladepfad (`baseline.store.BaselineStore.load_delta_index` / `load_states`, die `BaselineSnapshot.unscoped.filter(id=..., tenant_id=...)` voranstellen). Ein direktes `BaselineDeltaIndexEntry.objects.filter(item_id=...)` ohne diesen Vorbeweis ist verboten (Cross-Tenant-Leak).
- **Fail-safe-Semantik für #424 (revidiert):** Der Ausschluss ist **exakt das Paar** `origin == "ai_generated"` **und** `reviewed == False`. `reviewed` allein ist kein Ausschlusskriterium. `origin == "unknown"` (Bestandsdaten) wird bewusst **grandfathered** (zählt als Coverage), weil es weder als manuell noch als KI behauptet werden darf. Die Rest-Unsicherheit ist dokumentiert (F7).
- **Vollständigkeit der Produzenten (revidiert, löst Review-rev2 N3 + #424-Wurzel):** Der False-Green entsteht auf **zwei** Seiten — Konsumenten (die drei Consumer, §4.5) und **Produzenten**. Kein Pfad, der einen TestCase persistiert, darf `origin="manual"` implizit annehmen. Die **vollständige** Produzenten-Enumeration in §4.8 ist normativ: jeder dort gelistete Call-Site muss explizit `origin`/`reviewed` setzen oder die defaultende Service-Schicht muss KI-Kontext erkennen. Insbesondere gilt: **der Service-Default `origin=MANUAL` ist sicher, weil er nur von interaktiven Clients (REST/MCP-`test.create`) erreicht wird; jeder LLM-getriebene Pfad muss explizit `ai_generated` übergeben.** Ein Mutations-/Additivitätstest (§4.8/AC-424-16) schützt das dauerhaft.
- **Effective Severity (neu, löst Review-rev2 N1):** Die *wirksame* Severity eines Findings wird **nicht** vom `Finding`-Objekt einer Regel bestimmt, sondern ausschließlich vom `RuleEngine` über `rule.severity_for_tier(tier)` (§5.3/§5.4). Jede Regel, die advisory sein soll, **muss** diese Methode überschreiben — ein `severity=`-Argument am `Finding` ist für die Gate-Wirkung irrelevant.
- **Provider-agnostisch:** Keine plattformspezifischen Anweisungen.
- **Kompatibilität:** Alle Modell-/Serializer-Erweiterungen sind additiv; kein Feld wird umbenannt oder entfernt.

---

## 4. #424 — TestCase: Herkunft & Review-Status

### 4.1 Model-Delta (`backend/persistence/models.py`, `class TestCase` ab :1893)

| Feld | Typ | Null | Default | Choices / Werte | Zweck |
|------|-----|------|---------|-----------------|-------|
| `origin` | `CharField(max_length=20)` | `False` | `TestCaseOrigin.MANUAL` (`"manual"`) | `manual` \| `ai_generated` \| `unknown` | Herkunft des Inhalts (`unknown` = systemseitig, Bestandsdaten) |
| `reviewed` | `BooleanField` | `False` | `False` | — | menschliche inhaltliche Freigabe (**nur zusammen mit `origin` aussagekräftig**, §3) |
| `scenario_kind` | `CharField(max_length=20)` | `False` | `ScenarioKind.NOMINAL` (`"nominal"`) | `nominal` \| `off_nominal` | Off-Nominal-Kategorie (siehe §5.5, Issue #402) |

Neue `TextChoices` auf Modulebene (neben `TestCaseType`):

```
class TestCaseOrigin(models.TextChoices):
    MANUAL = "manual", "Manual"
    AI_GENERATED = "ai_generated", "AI-generated"
    UNKNOWN = "unknown", "Unknown"

class ScenarioKind(models.TextChoices):
    NOMINAL = "nominal", "Nominal"
    OFF_NOMINAL = "off_nominal", "Off-nominal"
```

- `UNKNOWN` ist ein **systemseitiger** Wert: er wird nur von der Migration gesetzt und über die API gelesen, **nicht** von Clients geschrieben (Serializer-Choices = `{manual, ai_generated}`, §4.4).
- Kein neuer Index nötig (Filter laufen workspace-scoped über `artifact__workspace_id`).
- `origin`/`reviewed`/`scenario_kind` sind **keine** `AuditableModel`-Spalten und beeinflussen `version` nicht direkt — der Version-Bump bleibt an `has_field_changes` gekoppelt (§4.3).

### 4.2 Migration M1 — schema-only, RLS-immune

**`backend/persistence/migrations/0099_testcase_origin_reviewed_scenario_kind.py`** (einzige #424-Migration)

```
dependencies = [("persistence", "0098_requirement_rationale_requirement_source")]
operations = [
  AddField(TestCase, "origin",
           CharField(max_length=20, choices=TestCaseOrigin.choices,
                     default="unknown"),   # nur zum Befüllen der Bestandszeilen
           preserve_default=False),        # danach DB-Default entfernt
  AlterField(TestCase, "origin",
             CharField(max_length=20, choices=TestCaseOrigin.choices,
                       default="manual")), # Modell-Default für Neuanlagen
  AddField(TestCase, "scenario_kind",
           CharField(max_length=20, choices=ScenarioKind.choices,
                     default="nominal")),
  AddField(TestCase, "reviewed", BooleanField(default=False)),
]
```

- **Begründung der Bestands-Semantik (löst Review-M2):** `AddField` befüllt bestehende Zeilen ausschließlich über den Spalten-Default (DDL, **kein** DML/`UPDATE`); deshalb erhalten alle Bestands-TestCases `origin="unknown"`, `reviewed=False`, `scenario_kind="nominal"`. Es wird **nicht** behauptet, sie seien manuell oder reviewt.
- **Warum kein `reviewed=True`-Backfill mehr:** Die v1-Begründung „ausnahmslos manuell" war durch #424s eigene Reproduktion widerlegt — KI-/Mock-TestCases wurden über den Derive-Pfad **unmarkiert** persistiert. Ein pauschales `reviewed=True` hätte genau die Zeilen als geprüft markiert, die #424 als False-Green meldet. `unknown`/`unreviewed` ist die einzige belegbare Aussage.
- **RLS-Sicherheit (löst Review-M3 für M1):** Die Migration enthält **keine** `RunPython`-Datenoperation. `AddField`/`AlterField` sind reine DDL und unterliegen keiner RLS-Policy; es gibt keinen stillen Zero-Row-No-op. Dies gilt ausdrücklich für dieses Schema-Only-Statement.
- **Reverse:** Standard-Django-Reverse (die drei `AddField` werden zu `RemoveField`, das `AlterField` revertiert den Default). Ein Unapply entfernt die Spalten samt Daten — das ist die inhärente, dokumentierte Reverse-Semantik von `AddField` und wird hier bewusst akzeptiert (keine eigene `RunPython`-Reverse nötig).

> **Abgrenzung:** Die nachträgliche Erkennung historischer KI-Zeilen aus dem Audit-Trail
> (`audit_entry.tool_name = "test.derive_from_requirement"`) ist **nicht** Teil dieser
> Migration. Sie erfordert einen Cross-App-Zugriff und ist erst ab #626 verlässlich
> (davor erzeugte der Derive-Write-Pfad wegen der Op-Vokabular-Lücke **null** Audit-Zeilen).
> Sie ist als Folgeschritt **F7** spezifiziert.

### 4.3 Service-Contracts (`backend/application/test_service.py`)

```
# TestService.create_test_case(...)  (:142)
def create_test_case(
    self,
    workspace_id: UUID,
    title: str,
    ctx: AuthContext,
    description: str = "",
    test_type: str = DEFAULT_TEST_TYPE,
    steps: Optional[list] = None,
    uid: Optional[str] = None,
    custom_fields: Optional[dict] = None,
    test_type_value: object = _UNSET,
    # NEU:
    origin: str = TestCaseOrigin.MANUAL,
    reviewed: Optional[bool] = None,
    scenario_kind: str = ScenarioKind.NOMINAL,
) -> TestCase
```

- Validierung: `origin` und `scenario_kind` werden gegen **ihre jeweiligen `values`** geprüft; sonst `ValidationError`. **Präzisierung (löst Review-rev2 N7):** Die *client-schreibbare* Choice-Menge ist `{manual, ai_generated}` (REST §4.4, MCP-`test.create`-Schema); `unknown` ist **ausschließlich** migrations-/systemseitig. Der Service akzeptiert `unknown` nur defensiv (damit die Migration und der Grandfathering-Pfad nicht brechen), aber kein Client-Contract exponiert es. F5 („`unknown` clientseitig gesperrt") bleibt damit korrekt; der MCP-`test.create`/`test.update`-Schema-Choice wird explizit auf `{manual, ai_generated}` gesetzt (nicht auf `TestCaseOrigin.values`).
- `reviewed`-Ableitung bei `None`: `True if origin == MANUAL else False`. Explizit übergebene Werte gewinnen. (Der `unknown`-Fall kann hier nicht eintreten: der Service-Default ist `MANUAL`, und der Derive-Pfad übergibt explizit `ai_generated`.)
- **Abgrenzung des Defaults (löst Review-m7/Wurzel #424):** Der Service-Default `MANUAL` ist **nur für interaktive Clients** gedacht (REST `POST /testcases/`, MCP `test.create`) — dort ist der Aufrufer ein Mensch bzw. ein Agent, der einen benannten TestCase anlegt. Er ist **kein** Default für LLM-generierte Inhalte; jeder LLM-getriebene Pfad übergibt `origin="ai_generated"` (siehe §4.8).
- Persistiert alle drei Felder im `TestCase.objects.create(...)`-Block und damit im `snapshot_fields(test_case, "TestCase")`-Revision-Snapshot.

```
# TestService.update_test_case(...)  (:245)
def update_test_case(
    self, test_case_id, ctx, title=None, description=None, steps=None,
    test_type=_UNSET, custom_fields=_UNSET, change_reason=None,
    expected_version=None,
    # NEU:
    scenario_kind: object = _UNSET,
) -> TestCase
```

- `origin` ist **nicht** Parameter → nach dem Anlegen unveränderlich (write-once).
- `reviewed` ist **nicht** Parameter → ausschließlich über `mark_reviewed` änderbar (Audit-Trail-Pflicht).

```
# TestService.mark_reviewed  (NEU)
def mark_reviewed(
    self,
    test_case_id: UUID,
    ctx: AuthContext,
    *,
    reviewed: bool = True,
    change_reason: str = "",
) -> TestCase
```

- Verhalten: idempotent; setzt `reviewed`; bumpt `version` genau dann, wenn sich der Wert real ändert (Muster `has_field_changes`); schreibt `ArtifactVersionService().record(...)`; `self._audit(operation="update", entity_type="TestCase", details={"reviewed": reviewed})`; emittiert kein neues Domain-Event (kein Enum-Wert vorhanden — dokumentiert).
- Berechtigung: `_assert_write_permission(ctx)` (editor/admin). Das ist bewusst, weil „reviewed" eine Prozessaussage ist und im Audit-Trail landet.

**Beziehung zu den bestehenden Review-Konzepten (löst Review-i2):** `reviewed` ist
**unabhängig** vom Workflow-Zustand (`draft→ready→approved→deprecated`) und von Rule 7
(`check_verifies_link`, das `approved` gatet). Ein TestCase kann workflow-`approved` und
`reviewed=False` sein (und umgekehrt). Die beiden Gates bedeuten Verschiedenes:
Workflow-`approved` = Prozess-Übergang des Artefakts; `reviewed` = inhaltliche Freigabe
für Coverage-/Evidenz-Zählung. UI und Audit dürfen sie nicht als dasselbe Gate darstellen;
`reviewed` impliziert **nicht** Workflow-`approved` und umgekehrt.

**`_ENTITY_FIELDS["TestCase"]` (`application/artifact_diff_service.py`, löst Review-m7):**

- `_ENTITY_FIELDS["TestCase"]` wird um `origin`, `reviewed`, `scenario_kind` erweitert.
- **Korrigierte Begründung:** Felder, die **nicht** in `_ENTITY_FIELDS` stehen, werden von
  `snapshot_fields` gar nicht aufgenommen und daher auch **nicht** gediffed. Das
  „changed/added to empty"-Risiko entsteht erst **nach** der Aufnahme — für einen Writer,
  der das Feld nie füllt, oder beim Vergleich gegen eine Pre-Upgrade-Revision.
- **Einmalige Diff-Folge (dokumentiert, analog Icd-`parameters_snapshot`):**
  `_compute_fields_diff` vereinigt die Feldnamen beider Snapshots; der erste Diff **jedes**
  bestehenden TestCases zeigt `origin`/`reviewed`/`scenario_kind` als *added*. Das ist inert
  (die ältere Revision hat die Werte tatsächlich nicht aufgezeichnet) und muss nicht
  „repariert" werden.

**MCP-Toolfläche (`backend/mcp_server/tools/tests.py`):**

- `_handle_derive_from_requirement` (:1067; der Service-Aufruf steht bei `:1114`) Write-Mode ruft künftig
  `self._service.create_test_case(..., origin="ai_generated", reviewed=False,
  scenario_kind=params.get("scenario_kind", "nominal"))`. Damit ist der **produktive**
  KI-Persistenz-Pfad ab dem Cut-over korrekt markiert.
- **`test.create` bleibt bewusst auf dem `MANUAL`-Default** (:566, **keine** Änderung):
  dieses Tool legt einen vom Aufrufer *benannten* TestCase an (interaktiver Client, kein
  LLM-Generat). Ein `origin`-Input ist optional (§4.4/Tool-Schema); der Default bleibt
  `manual`. Das wird in §4.8 als explizite Entscheidung dokumentiert (damit keine spätere
  „Vereinheitlichung" den Default stumm auf `ai_generated` oder umgekehrt dreht).
- `test.create` / `test.update` Schemas um `origin`, `scenario_kind` erweitern
  (Input-Schema in der `tools/list`-Definition, :380 ff.). `reviewed` **nicht** im
  Input-Schema — es wird über das neue `test.mark_reviewed`-Tool gesetzt.
- `test.derive_from_requirement` bleibt in `_WRITE_TOOL_PREFIXES` registriert (unverändert).

**Neues MCP-Tool `test.mark_reviewed` (löst Review-m11):**

| Aspekt | Contract |
|--------|----------|
| Name | `test.mark_reviewed` (Gruppe `test`, Write-Tool → in `_WRITE_TOOL_PREFIXES`) |
| Parameter | `test_case_id` (uuid, required), `reviewed` (bool, default `true`), `change_reason` (string, optional) |
| Delegation | `TestService().mark_reviewed(test_case_id, ctx, reviewed=..., change_reason=...)` |
| Antwort | `{ "id": "<uuid>", "reviewed": <bool>, "version": <int> }` |
| Audit | `operation="update"`, `entity_type="TestCase"`, `details={"reviewed": <bool>}` (bestehender Op-Wert) |
| Fehler | `NOT_FOUND`, `VALIDATION_ERROR`, `PERMISSION_DENIED` |
| Handler | `_handle_mark_reviewed` im `TestCaseToolGroup`; Dispatch-/Schema-Eintrag neben `_handle_derive_from_requirement` |

### 4.4 API- & Serializer-Contracts (`backend/rest_api/serializers.py`, `views.py`)

`TestCaseSerializer` (:1152) erhält:

```
origin        = ChoiceField(choices=[TestCaseOrigin.MANUAL, TestCaseOrigin.AI_GENERATED],
                            required=False, default="manual")   # UNKNOWN ist systemseitig
reviewed      = BooleanField(read_only=True)
scenario_kind = ChoiceField(choices=ScenarioKind.choices, required=False, default="nominal")
```

- `validate()`-Rejections bei `self.instance is not None` (Update):
  - gesetztes `origin` → `ValidationError({"origin": "origin is immutable after creation"})`.
  - `"reviewed"` **im Request-Body** → `ValidationError({"reviewed": "reviewed is set via POST /api/v1/testcases/{id}/review/"})`.
    Die Prüfung liest `self.initial_data` (nicht `attrs`), weil DRF ein read-only-Feld
    **vor** `validate()` verwirft. Damit ist der #851-Klasse-Silent-No-op ausgeschlossen
    (löst Review-m1).
- `reviewed` bleibt read-only in der Repräsentation; der Create-Pfad leitet es aus `origin` ab.

`TestCaseViewSet` (:2309):
- `create()` (:2382) reicht `origin`, `scenario_kind` an `create_test_case` durch.
  `reviewed` wird **nicht** durchgereicht (nicht Teil der API-Surface; der Service leitet
  es aus `origin` ab). **Der REST-Pfad ist der produktive Persistenz-Pfad des UI**
  (`DeriveTestCasePanel` → `testcasesApi.create`).
- **Neue Action:**
  `POST /api/v1/testcases/{id}/review/` → `@action(detail=True, methods=["post"], url_path="review")`
  Body `{"reviewed": true, "change_reason": "..."}` (beide optional; `reviewed` default `true`).
  Antwort: `TestCaseSerializer`-Objekt (200). Fehler: 404 `NOT_FOUND`, 400 `VALIDATION_ERROR`, 403.
- `partial_update` (:…) reicht `scenario_kind` an `update_test_case` durch, `origin`/`reviewed` **nicht**.

**Neues `ChangeRequestSerializer`-Feld (für D1-CR-Prefill, löst Review-m11):**
- `affected_item_ids = ListField(child=UUIDField(), required=False, write_only=True)`
  (additiv; erscheint nie in der Antwort).
- `ChangeRequestViewSet.create` reicht es durch:
  `create_change_request(..., affected_item_ids=data.get("affected_item_ids"))`.
  Der Service validiert die IDs bereits workspace-/tenant-scoped
  (`_validate_affected_items`) und snapshotet den „before"-Zustand.

### 4.5 Coverage-/Verifikations-Integration (alle drei False-Green-Consumer)

**Gemeinsames Prädikat (Single Source of Truth, löst Review-M1):**

```
# backend/traceability/coverage_calculator.py  (Modul-Ebene, exportiert)
def counts_as_verification_evidence(origin: str, reviewed: bool) -> bool:
    """False genau dann, wenn origin == 'ai_generated' und reviewed is False."""
```

Beide Schichten (Coverage *und* Audit) rufen ausschließlich dieses Prädikat auf, damit die
drei Pfade nicht auseinanderlaufen.

**(1) `CoverageCalculator` (`traceability/coverage_calculator.py`)**

```
def coverage(self, workspace_id, artifact_type=None, link_type=None, *,
             include_outdated: bool = False,
             include_unreviewed_ai: bool = False) -> CoverageReport

def get_coverage_data(self, workspace_id, baseline_id=None,
                      include_outdated: bool = False,
                      include_unreviewed_ai: bool = False) -> CoverageData

def _exclude_outdated_testcase_ids(self, testcase_artifact_ids: set[str], *,
                                   include_unreviewed_ai: bool = False) -> set[str]

def _filter_to_testcase_ids(self, source_ids: set[str], *,
                            include_outdated: bool = False,
                            include_unreviewed_ai: bool = False) -> set[str]
```

- `_filter_to_testcase_ids` lädt zusätzlich `origin`/`reviewed` und wendet
  `counts_as_verification_evidence` an, sofern `include_unreviewed_ai=False`.
- `_exclude_outdated_testcase_ids` ist der Wrapper, den `workflow.precondition_rules`
  direkt aufruft; er reicht `include_unreviewed_ai` durch (Default `False`).
- `CoverageReport` (`traceability/types.py`) wird **additiv** erweitert:
  `pending_ai_review: int = 0` = Anzahl der **distinct** TestCase-Artefakte, die
  (a) Quelle eines `verifies`-Links auf ein Requirement des Workspace sind, (b) nicht
  `outdated` sind und (c) **ausschließlich** wegen `origin="ai_generated" and not reviewed`
  ausgeschlossen wurden. `unknown`-Zeilen zählen hier **nicht**.
- `RequirementCoverageEntry.test_cases[]` (dict-basiert in `get_coverage_data`) erhält
  additiv `origin`, `reviewed`, `scenario_kind`, `uid`, `title`.

**(2) `check_verification_evidence` (`workflow/precondition_rules.py` :377)**

- Der Aufruf :428 wird
  `calculator._exclude_outdated_testcase_ids(testcase_artifact_ids, include_unreviewed_ai=False)`
  (expliziter Name des Wrappers, nicht `_filter_to_testcase_ids`).
- Fehlermeldung :435 wird ergänzt: „… or its only linked test case is an unreviewed
  AI-generated test case".

**(3) `LeafRequirementHasTestCaseRule` (VERIF-P8, `traceability/audit/rules/coverage_consistency.py`) — der dritte Consumer**

- **Neuer Helper** (nur für VERIF-P8; TRACE-P6 bleibt unverändert):

```
def _active_verifying_test_cases(context: AuditContext) -> Dict[str, str]:
    """{artifact_id: title} der aktiven TestCases, die als Verifikations-Evidenz zählen."""
```

  Umsetzung: `TestCase.unscoped.filter(tenant_id=..., artifact__workspace_id=...).values("id",
  "artifact_id", "title", "origin", "reviewed")`, danach derselbe `WorkflowItemState`-Aktiv-
  Filter wie `_active_test_cases`, danach `counts_as_verification_evidence(origin, reviewed)`.
- `LeafRequirementHasTestCaseRule.check` verwendet **diesen** Helper für
  `active_test_case_ids` (:282). Ergebnis: ein unreviewter KI-TestCase ist **keine**
  Verifikations-Evidenz; ein Leaf-Requirement, das nur so „verifiziert" war, löst bei
  Extended wieder einen `VERIF-P8`-BLOCKER aus.
- **`TestCaseVerifiesExistingArtifactRule` (TRACE-P6) bleibt auf `_active_test_cases`**
  (ohne Review-Filter). Begründung: TRACE-P6 fragt „verweist dieser TestCase auf ein
  existierendes Artefakt?", unabhängig von seinem Review-Status; ein Review-Filter würde
  die Regel für unreviewte KI-TestCases stillschweigend abschalten (Regel-Lücke statt
  Regel-Wirkung). Das wird als Kommentar am Helper festgehalten.

**`backend/application/test_service.py::get_coverage` (:494)** liefert additiv
`"pending_ai_review": report.pending_ai_review`.

### 4.6 Frontend-Touchpoints

| Datei | Änderung | `data-testid` |
|-------|----------|---------------|
| `frontend/src/components/TestCaseEditors/DeriveTestCasePanel.tsx` | `handleCreate` sendet `origin: "ai_generated"`, `scenario_kind: "nominal"` (kein `reviewed` — read-only); Hinweis-Text „KI-generiert, nicht geprüft" | bestehend (`derive-testcase-result`), neu `derive-testcase-ai-notice` |
| `frontend/src/components/TestCaseEditors/TestCaseList.tsx` | Nach `ArtifactRow` (:160) optionale Badges: AI + „Unreviewed" + „Off-nominal" (pro Zeile aus dem Listen-Payload; **kein** Zusatz-Request) | `tc-row-ai-badge-${tc.id}`, `tc-row-unreviewed-badge-${tc.id}`, `tc-row-offnominal-badge-${tc.id}` |
| `frontend/src/components/TestCaseEditors/TestCaseArtifactForm.tsx` (Detail-/Edit-Formular) | „Als geprüft markieren"-Button in den Header-Actions; ruft `testcasesApi.review(...)` | `tc-review-button` |
| `frontend/src/components/TestCaseEditors/TestCaseEditors.tsx` | verdrahtet den Review-Button mit dem Detail-State + Refetch | — |
| `frontend/src/components/TestCaseEditors/TestCaseArtifactForm.tsx` | `scenario_kind`-Select | `tc-scenario-kind-select` |
| `frontend/src/api/testcases.ts` | `TestCase`-Interface um `origin`, `reviewed`, `scenario_kind`; `create()`-Payload ohne `reviewed`; neue Methode `review(id, {reviewed?, change_reason?})` | — |
| `frontend/src/i18n/locales/de.json` + `en.json` | Keys `testcases.originAi`, `testcases.unreviewed`, `testcases.markReviewed`, `testcases.scenarioNominal`, `testcases.scenarioOffNominal`, `deriveTestcase.aiNotice` | — |

Regeln: ausschließlich Tokens aus `styles/tokens.css`, keine Hex-Literale; jedes neue
interaktive Element bekommt `data-testid`; `i18n-parity`- und `ui-ratchet`-Baselines werden
nach der Änderung neu gemessen und **gesenkt** (nie erhöht).

### 4.7 Acceptance Criteria #424

- **AC-424-1 (korrigiert, löst Review-m11)** Given ein Requirement und `LLM_PROVIDER=mock`, When der UI-Pfad `POST /api/v1/requirements/{id}/derive-testcase/` → anschließend `POST /api/v1/testcases/ {origin:"ai_generated"}` (ohne `reviewed`, da read-only), Then hat der erzeugte TestCase `origin == "ai_generated"` und `reviewed == false` (**abgeleitet**, nicht per Payload gesetzt).
- **AC-424-2** Given ein manuell angelegter TestCase ohne `origin`-Feld, Then ist `origin == "manual"` und `reviewed == true`.
- **AC-424-3** Given ein unreviewter KI-TestCase mit `verifies`-Link zu Requirement R, When `CoverageCalculator().coverage(ws)`, Then ist R **nicht** in `covered`, `pending_ai_review >= 1`; When `coverage(ws, include_unreviewed_ai=True)`, Then ist R in `covered`.
- **AC-424-4** Given derselbe TestCase nach `POST /api/v1/testcases/{id}/review/`, When `coverage(ws)`, Then ist R in `covered` (Default-Aufruf) und `pending_ai_review == 0`.
- **AC-424-5** Given ein unreviewter KI-TestCase als einzige `verifies`-Evidenz, When Status-Transition `→ verified` auf R, Then 400 `EC_VERIFICATION_EVIDENCE_MISSING`; nach `review` gelingt die Transition bei sonst gleichen Bedingungen.
- **AC-424-6** Given ein bestehender TestCase, When `PATCH /api/v1/testcases/{id}/ {origin:"ai_generated"}` → 400 `VALIDATION_ERROR` (`origin is immutable`); When `PATCH {reviewed:true}` → 400 `VALIDATION_ERROR` (`reviewed is set via .../review/`). **Beide** Rejections.
- **AC-424-7 (korrigiert)** Given Migration `0099` auf einer DB mit N Bestands-TestCases, Then haben alle N `origin=="unknown"`, `reviewed==false`, `scenario_kind=="nominal"`; die Coverage-KPI vor/nach der Migration ist identisch (`unknown` ist grandfathered); **kein** Bestands-TestCase wird als `manual`/`reviewed` markiert.
- **AC-424-8** Given `GET /api/v1/testcases/{id}/`, Then enthält die Antwort `origin`, `reviewed`, `scenario_kind`.
- **AC-424-9 (neu, M1/VERIF-P8)** Given ein Extended-Workspace mit einem leaf-Requirement, dessen einzige `verifies`-Evidenz ein `origin="ai_generated"`, `reviewed=false` TestCase ist, When SE-Audit, Then enthält das Ergebnis ein `VERIF-P8`-Finding für dieses Requirement; nach `review` verschwindet es.
- **AC-424-10 (neu, M1/Mutation)** Given derselbe Fall, When die `counts_as_verification_evidence`-Prüfung im Audit-Helper `_active_verifying_test_cases` entfernt wird, Then muss AC-424-9 rot werden (Mutationsprobe).
- **AC-424-11 (neu, MCP)** Given ein TestCase, When MCP `test.mark_reviewed {test_case_id, reviewed:true}`, Then ist `reviewed == true`, `version` ist gebumpt, und ein `AuditEntry` (`operation="update"`, `entity_type="TestCase"`, `details.reviewed == true`) existiert; zweiter Aufruf ist idempotent (kein zweiter Version-Bump).
- **AC-424-12 (neu, pending_ai_review)** Given `GET /api/v1/requirements/coverage-report/` mit einem unreviewten KI-TestCase, Then ist `summary.pending_ai_review >= 1`; mit `include_unreviewed_ai=true` ist es `0` (Roh-Sicht).
- **AC-424-13 (neu, i2)** Given ein workflow-`approved` TestCase mit `reviewed=false`, Then bleiben Workflow-`approved` und `reviewed` unabhängig: `GET` liefert beides unverändert; `mark_reviewed` ändert den Workflow-Zustand nicht.

### 4.8 ALLE Produzenten von TestCase (normative Enumeration — löst Review-rev2 N3, Wurzel von #424)

**Single Choke Point:** Jede Persistenz eines `TestCase` läuft über **genau einen**
Model-Write: `TestCase.objects.create(...)` in `TestService.create_test_case`
(`application/test_service.py:196`) bzw. das Pendant in
`update_test_case` (kein `origin`-Schreibpfad). Kein anderer Produktions-Code
schreibt `TestCase`-Zeilen direkt; die `TestCase.objects.create(...)`-Treffer
außerhalb von `test_service.py` stammen ausschließlich aus **Tests und Fixtures**
(`*_tests/`, `conftest.py`) und sind kein Produktionspfad.

**Produzenten-Enumeration (vollständig, per Grep über `create_test_case(` über `backend/` verifiziert):**

| # | Call-Site | Charakter | `origin` heute | Soll | Status in Cluster 5 |
|---|-----------|-----------|----------------|------|---------------------|
| P1 | `rest_api/views.py:2406` (`TestCaseViewSet.create` → `POST /api/v1/testcases/`) | **interaktiv** (UI; `DeriveTestCasePanel` → `testcasesApi.create`) | Service-Default `manual` | `manual` (Client darf `origin:"ai_generated"` senden, §4.4) | unverändert korrekt |
| P2 | `mcp_server/tools/tests.py:566` (`test.create`) | **interaktiv** (benannter TestCase, kein LLM-Generat) | Service-Default `manual` | `manual` (Default), `origin` optional im Schema | **unverändert** (bewusste Entscheidung, §4.3) |
| P3 | `mcp_server/tools/tests.py:1114` (`test.derive_from_requirement`, Write-Mode) | **LLM-getrieben** (Derive aus Requirement via LLM-Adapter) | `manual` (**FALSE-GREEN**) | **`ai_generated`, `reviewed=False`** | **v2 gepatcht** (§4.3) |
| P4 | `application/interview_artifact_adapters.py:96` → `_test_case` (registriert `:208`) | **LLM-getrieben** (Interview-Formalisierung; `interview_multi_protocol` nennt TestCase unter den Multi-Proposal-Typen; LLM emittiert fenced JSON) | `manual`, `reviewed=True` (**FALSE-GREEN**) | **`ai_generated`, `reviewed=False`** | **v3 — DIESER N3-BEFUND** |
| P5 | `auth_tenancy/management/commands/seed_toothbrush.py:400` | **Fixture** (Demo-Seed) | Service-Default | `manual`/`reviewed=True` (menschliches Demo-Material) | unverändert; §7.5 `seed_full_chain` setzt es **explizit** |

**P4-Spezifikation (der behobene Befund):**

```
# backend/application/interview_artifact_adapters.py  (_test_case)
def _test_case(fields: dict, ctx: AuthContext, workspace_id) -> CreatedArtifactRef:
    obj = TestService().create_test_case(
        workspace_id=workspace_id,
        ctx=ctx,
        origin="ai_generated",      # NEU
        reviewed=False,             # NEU
        **fields,                   # darf origin/reviewed NICHT überschreiben
    )
```

- **Überschreibschutz:** `origin`/`reviewed` werden **nach** `**fields` aufgeführt, bzw. — falls die Interview-Feldspezifikation diese Keys je enthalten könnte — `fields = {k: v for k, v in fields.items() if k not in ("origin", "reviewed")}` vor dem Aufruf. Ein Test pinnt, dass ein `origin`-Key im Proposal-Dict den Adapter-Default **nicht** kippt.
- **`reviewed=False` ist explizit** (nicht nur abgeleitet): der Interview-Pfad ist LLM-generiert, der Mensch hat den TestCase beim Formalisieren **nicht** inhaltlich geprüft. Der Review erfolgt später über `POST /testcases/{id}/review/` (§4.4) bzw. `test.mark_reviewed`.
- **Begründung ohne Ausnahme:** Der Review-rev2-Vorschlag einer „dokumentierten Ausnahme" (Interview = human-confirmed) wird **verworfen**. Die Formalisierung ist ein LLM-Extraktionsschritt ohne separates, sichtbares Human-Confirm-Gate pro TestCase; eine Ausnahme würde exakt die #424-False-Green-Klasse wieder einführen (Prompt-Ausgabe zählt als geprüfte Evidenz). Konsequent markieren (F5-Logik: `origin` ist ein Prozess-Hinweis, kein Sicherheitsmerkmal).
- **Abgrenzung zu `fields`:** Das Interview-Nutzlast-Feld `scenario_kind` darf weiterhin aus `fields` kommen; nur `origin`/`reviewed` sind adapter-gesetzt.

**Additivitäts-/Mutations-Invariante (struktureller Schutz gegen künftige Produzenten):**

- **Default-Sicherheit:** Der Service-Default bleibt `MANUAL` und `reviewed` wird bei `None` zu `True if origin == MANUAL else False` (§4.3). Ein neuer Produzent, der **keinen** `origin` übergibt, landet damit als `manual/reviewed=True` — das ist die *sichere* Richtung für interaktive Clients, aber die *unsichere* für LLM-Pfade. Deshalb ist die Enumeration oben normativ und kein Kommentar.
- **Wachtest (Additivität, AC-424-16):** Eine Testdatei hält die Liste der
  `create_test_case(`-Call-Sites **außerhalb von `*/tests/` und `*/conftest.py`** als
  eingefrorenes Set fest. Wird ein neuer Produktions-Call-Site hinzugefügt, **muss**
  dieser Test rot werden und den Autor zwingen, `origin`/`reviewed` explizit zu
  entscheiden (und die Enumeration hier zu ergänzen). So kann kein künftiger
  Produzent stumm auf `manual` defaulten.
- **Mutationsprobe (Pflicht, §9):** Entfernt man in P4 die explizite Übergabe
  `origin="ai_generated"`, muss AC-424-14 rot werden; entfernt man in P3 dasselbe,
  muss AC-424-15 rot werden.

### 4.9 Acceptance Criteria #424 — Produzenten (N3)

- **AC-424-14 (neu, N3/Interview)** Given ein Interview-Formalisierungslauf (`LLM_PROVIDER=mock`), der eine TestCase-Proposal enthält, When der Lauf abgeschlossen ist, Then hat der erzeugte TestCase `origin=="ai_generated"` und `reviewed==false`; ein `origin`-Key im Proposal-Dict ändert das **nicht** (Überschreibschutz); `POST /api/v1/testcases/{id}/review/` macht ihn danach zu `reviewed==true` und er zählt als Coverage-Evidenz (AC-424-3-Muster).
- **AC-424-15 (neu, P3/Derive)** Given `test.derive_from_requirement` (MCP, Write-Mode, `LLM_PROVIDER=mock`), Then hat der persistierte TestCase `origin=="ai_generated"` und `reviewed==false`; `CoverageCalculator().coverage(ws)` zählt ihn **nicht** als Evidenz, `pending_ai_review >= 1`.
- **AC-424-16 (neu, Additivitäts-Wachtest)** Given die Produzenten-Enumeration aus §4.8, When die Liste der produktiven `create_test_case(`-Call-Sites (außerhalb `*/tests/`, `*/conftest.py`) ermittelt wird, Then ist sie exakt die in §4.8 gelistete Menge `{P1,P2,P3,P4,P5}`; ein zusätzlicher Produktions-Call-Site lässt diesen Test rot werden (erzwingt eine explizite `origin`-Entscheidung).
- **AC-424-17 (neu, Default-Abgrenzung)** Given `test.create` (MCP) ohne `origin`-Parameter, Then ist `origin=="manual"` und `reviewed==true` — der interaktive Pfad P2 bleibt unverändert (Regressionsschutz gegen eine „Vereinheitlichung" des Defaults).

---

## 5. #402 — Goals default-on, Goal-Traceability-Regel, Off-Nominal

### 5.1 Model & Migration M2 (RLS-sicher)

**M2 — `backend/persistence/migrations/0100_workspace_goals_enabled_default.py`**

```
dependencies = [("persistence", "0099_testcase_origin_reviewed_scenario_kind")]
operations = [
  AlterField(Workspace, "goals_enabled", BooleanField(default=True)),   # schema-only
  RunPython(enable_goals_for_existing_workspaces, reverse_code=noop),   # Datenoperation
]
```

**Datenoperation `enable_goals_for_existing_workspaces` (löst Review-M3 für M2):**

1. Tenants enumerieren über das **historische** Model `apps.get_model("persistence", "Tenant")` (`pl_tenant` ist bewusst **außerhalb** RLS).
2. Pro Tenant: `SET app.current_tenant = <tenant_id>` (Muster `link_types/0005`).
3. Im armed Kontext zählen: `expected = Workspace.objects.filter(tenant_id=<t>, is_active=True,
   goals_enabled=False).count()` — wobei `Workspace = apps.get_model("persistence", "Workspace")`
   **innerhalb** der `RunPython`-Funktion aufgelöst wird.
4. `updated = Workspace.objects.filter(tenant_id=<t>, is_active=True,
   goals_enabled=False).update(goals_enabled=True)`.
5. **Assertion:** `if updated != expected: raise RuntimeError(...)` — die Migration schlägt laut
   fehl statt still null Zeilen zu melden (Muster `0073_backfill_artifact_backing.py::verify`).
6. `finally: RESET app.current_tenant`.

**Historische Models statt Live-Manager (NEU, löst Review-rev2 N6 — Feasibility):**

- Die `RunPython`-Funktion **muss** ihre Models über `apps.get_model("persistence", "Tenant")`
  und `apps.get_model("persistence", "Workspace")` auflösen, **nicht** über den importierten
  Live-`Workspace`. Vorbild: `link_types/0005_backfill_goal_reference_pairs.py:73-90`; die
  Begründung ist in `0073_backfill_artifact_backing.py:12-17` dokumentiert.
- **Warum der Live-Manager scheitert:** `TenantManager.get_queryset` liest den thread-lokalen
  `TenantContext` (`persistence/tenancy.py:135-143`) und wirft ohne aktiven Kontext
  `TenantContextNotSetError`. Die Migration armt aber nur die **DB-GUC** (`SET app.current_tenant`),
  **nicht** den Thread-Local — ein `Workspace.objects.filter(...)` würde also mit
  `TenantContextNotSetError` **abbrechen**, statt zu armieren. Die `SET`-Armierung wirkt
  ausschließlich auf die RLS-Policy, nicht auf den ORM-Manager.
- Die historischen Models bringen einen **plain** `Manager` (kein `TenantManager`), daher ist
  kein Thread-Local nötig; der explizite `tenant_id=<t>`-Filter plus die GUC-Armierung halten
  die Tenant-Trennung doppelt.
- **Konsequenz für die Assertion:** `expected` und `updated` werden gegen dasselbe historische
  Model gebildet — die Gleichheit ist damit auch unter Non-BYPASSRLS-Rolle aussagekräftig
  (AC-402-2).

`modified_at` wird bewusst **nicht** gesetzt (Konfigurationsmigration, dokumentiert).

**Weitere Änderungen:**
- `WorkspaceSerializer.goals_enabled` (`rest_api/serializers.py:1633`) → `default=True`.
- `views.py` `_workspace_to_dict` (:4589) bleibt unverändert (`getattr(..., False)` als defensiver Fallback).
- Kein `AlterField` auf `goals_ai_enabled`.

**Reverse:** `RunPython(reverse_code=noop)` — einseitig, weil kein Marker existiert, welche
Zeile vorher `False` war. Der `AlterField`-Reverse setzt nur den Default zurück. Das wird
dokumentiert (One-Way-Door, identisch zu v1).

**Korrigierte Testbruchliste:** siehe §2 (D2). `rest_api/tests/test_goal_views.py:90`
ist **nicht** betroffen (setzt `goals_enabled=False` explizit); dafür fehlt in v1
`rest_api/tests/test_workspace_create_schema_conformance.py:121` (`body["goals_enabled"] is False`)
— beide Punkte sind jetzt korrekt.

### 5.2 Link-Katalog-Erweiterung (`satisfies` StakeholderNeed → Goal)

`backend/link_types/builtin.py`, Eintrag `"satisfies"` (:165): `allowed_pairs` wird additiv um
`("StakeholderNeed", "Goal")` erweitert. `coverage_relevant=True` bleibt;
`test_only_allocated_to_verifies_and_satisfies_are_coverage_relevant` bleibt grün
(Menge unverändert).

**Mitgezogene Tests (eingeplant):** `backend/link_types/tests/test_builtin.py::test_satisfaction_types_have_the_expected_pairs` (:155) pinnt die `satisfies`-Paarliste exakt und muss um das neue Paar erweitert werden.

**M3 — `backend/link_types/migrations/0009_backfill_need_satisfies_pair.py`** (löst Review-m3)

```
dependencies = [("link_types", "0008_seed_satisfaction_link_types")]
operations = [RunPython(apply_pairs, migrations.RunPython.noop)]
```

- **Vorbild ist `0005_backfill_goal_reference_pairs.py`** (nicht nur „exakt wie 0005/0006" im Fließtext):
  - `KEY = "satisfies"`.
  - **Global:** alle `GlobalLinkTypeDefinition`-Zeilen mit `key="satisfies"`.
  - **Workspace:** nur `WorkspaceLinkTypeDefinition`-Zeilen mit `key="satisfies"` **und `is_customized=False`** (tenant-Customizations bleiben unangetastet).
  - Wanted pair: `{"source_type": "StakeholderNeed", "target_type": "Goal"}`; nur anhängen, wenn nicht vorhanden (idempotent, Reihenfolge unverändert).
  - **RLS:** pro Tenant `SET app.current_tenant`, danach `RESET` (`lt_*`-Tabellen sind `FORCE ROW LEVEL SECURITY`).
- **Reverse:** `migrations.RunPython.noop` — spiegelt `0005`. Ein reverse „Pair entfernen" würde eine bewusst hinzugefügte Tenant-Customization löschen können und bestehende StakeholderNeed→Goal-Links an einem nicht mehr erlaubten Paar zurücklassen; deshalb kein aktives Entfernen.
- **Abhängigkeit** auf `0008` ist obligatorisch: `0008` hat die `satisfies`-Zeilen überhaupt erst angelegt, die hier mutiert werden.

**Verworfene Alternative (dokumentiert):** rein transitive Definition „Need ist abgedeckt, wenn ein
Requirement `derives-from` den Need und `satisfies` ein Goal". Kein Katalog-Change, aber die
Remediation ist für Nutzer nicht direkt sichtbar. Die direkte Kante ist explizit, im UI erstellbar
und entspricht dem Issue-Wortlaut.

### 5.3 Neue Audit-Regel `VAL-P1` (revidierte Gates)

**Rule-ID:** `VAL_P1 = "VAL-P1"` — neue Konstante in `backend/traceability/audit/registry.py` neben `TRACE_P1` etc. (Kategorie „Validation").

**Preset-Platzierung:** ausschließlich **Extended** → `_EXTENDED_ONLY_RULES` (:89) und damit automatisch in `FULL_SE_RULE_IDS` und `RULE_PRESET_MAP["extended"]`. Minimal/Standard bleiben unberührt (`test_se_auditor_stage_coupling` schützt das).

**Datei:** `backend/traceability/audit/rules/validation_goals.py`, registriert per `@register_rule`; Import in `rules/__init__.py` ergänzen. `is_scope_aware = False`.

**Semantik (`check(context) -> list[Finding]`):**

1. **Aktivierungs-Gate (korrigiert, löst Review-m10 — fail-open):**

   ```
   if not Workspace.unscoped.filter(
       id=context.workspace_id,
       tenant_id=context.tenant_id,
       goals_enabled=True,
   ).exists():
       return []
   ```

   `unscoped` + explizite `tenant_id` (Audit-Konvention). Kein auflösbarer Workspace-Kontext
   oder `goals_enabled=False` → `return []`. Die v1-Variante (`filter(..., goals_enabled=False).exists()`)
   lief bei fehlendem Kontext nicht früh zurück — das ist behoben.
2. **Goal-Existenz-Gate:** Existiert **kein** aktives Goal im Workspace → `return []`. (Verhindert Findings für Goal-freie Workspaces.)
3. **Prüfung:** Für jeden aktiven `StakeholderNeed` (aktiv = nicht `outdated`, aufgelöst über `WorkflowItemState`/`state_reader` wie in `coverage_consistency._active_requirements`) muss mindestens ein `satisfies`-Link (`LinkType.SATISFIES.value`) auf ein **aktives Goal** existieren.
4. **Finding:** pro nicht abgedecktem Need
   `Finding(rule_id="VAL-P1", severity=Severity.WARNING, artifact_ids=(need_artifact_id,),
   message="[VAL-P1] StakeholderNeed '<title>' (<id>) trägt zu keinem aktiven Goal bei — 'satisfies'-Link auf ein Goal fehlt.")`.
   **Severity ist `WARNING`, nicht `BLOCKER`.**
   **Achtung (N1):** Das `severity=`-Argument am `Finding` ist **nicht** die wirksame Severity —
   der `RuleEngine` stempelt jedes Finding mit `rule.severity_for_tier(tier)` neu (§5.4). Die
   Regel **muss** deshalb zusätzlich die Methode `severity_for_tier` überschreiben (Punkt 6).
5. Datenzugriff über `context.iter_trace_links()` und `unscoped.filter(tenant_id=..., artifact__workspace_id=...)` (Audit-Konvention, §3).

6. **Expliziter Severity-Override (NEU, löst Review-rev2 N1) — der wirksame Hebel:**

   ```python
   # backend/traceability/audit/rules/validation_goals.py
   @register_rule
   class ValidationGoalsRule(Rule):
       rule_id = VAL_P1
       is_scope_aware = False

       def severity_for_tier(self, tier: str) -> Severity:
           """Immer WARNING — VAL-P1 ist advisory und darf kein Baseline-Gate sperren."""
           return Severity.WARNING

       def check(self, context: AuditContext) -> list[Finding]:
           ...
   ```

   **Verifikation des Hooks (Review-rev2 N1):** `RuleEngine._run_rule`
   (`backend/traceability/audit/rule_engine.py:137-154`) liest
   `severity = rule.severity_for_tier(tier)` und ersetzt die Severity **jedes** Findings
   durch diesen Wert (frozen-dataclass-Re-Stamp, `:145-153`). Die Basis-Implementierung
   `Rule.severity_for_tier` (`backend/traceability/audit/registry.py:233-240`) liefert
   `Severity.BLOCKER`. **Jede advisory Regel im Codebase überschreibt die Methode** —
   Muster: `LevelProgressionRule` (CONS-P11, `rule_s/level_progression.py:138-140`) und
   `TraceDerivationAllocationRule` (TRACE-P2, `rules/trace_derivation_allocation.py:403-404`).
   Eine `VAL-P1` ohne diesen Override würde trotz `Finding(severity=WARNING)` als **BLOCKER**
   wirksam, `AuditService.blocking_findings` (`application/audit_service.py:296`) gäbe sie
   zurück und `BaselineFacade._enforce_audit_gate` (`application/baseline_facade.py:440`)
   würde den Baseline-Build blockieren — der retroaktive Blocker aus #402-M4.

   > **Normativ:** Der `Finding(severity=…)`-Wert in Punkt 4 *und* der
   > `severity_for_tier`-Override in Punkt 6 sind beide verbindlich. Der erste dokumentiert
   > die Regel-Absicht, der zweite ist die **einzige** Größe, die das Gate liest.

7. **Deferred/`policy_fields_without_consumer` / `bootstrap_attribute_definitions`:** `VAL-P1` ist graph-basiert, kein `mandatory_fields`-Eintrag nötig — keine Preset-Policy-Änderung.

**MCP/Audit-Reporting:** erscheint automatisch im Regel-Katalog (`get_registered_rules`) und in `audit.se_audit`-Findings; keine Tool-Schema-Änderung.

### 5.4 Severity / Gate-Wirkung (revidiert, löst Review-M4 und Review-rev2 N1)

`VAL-P1` ist **`WARNING`**. **Die wirksame Severity stammt aus
`ValidationGoalsRule.severity_for_tier(tier)`, nicht aus dem `Finding`-Wert** — der
`RuleEngine._run_rule` stempelt jedes Finding damit neu (`rule_engine.py:137-154`).
`AuditService.blocking_findings` filtert auf `Severity.BLOCKER`
(`application/audit_service.py:296`), und `BaselineFacade._enforce_audit_gate` ist an
`blocking_findings` gebunden (`application/baseline_facade.py:440`) — **ein `WARNING` kann
den Baseline-Build nicht blockieren**. Damit feuert **kein** rückwirkender Blocker für
bestehende Goal-nutzende Extended-Workspaces. Die doppelten Gates (Aktivierung +
Goal-Existenz) schützen zusätzlich.

**Contract der beiden Größen (N1-Klarstellung):**

| Größe | Rolle | Wert | Ort |
|-------|-------|------|-----|
| `Finding.severity` | Dokumentation der Regel-Absicht | `Severity.WARNING` | §5.3 Punkt 4 |
| `ValidationGoalsRule.severity_for_tier(tier)` | **einzige** vom Gate gelesene Severity | `Severity.WARNING` für jeden Tier | §5.3 Punkt 6 |
| `AuditService.blocking_findings` | Gate-Filter | nur `Severity.BLOCKER` | `application/audit_service.py:296` |

- Die Regel erscheint als advisory Finding im bestehenden SE-Auditor und erfüllt damit #402s
  Traceability-Signal, ohne den Release-Pfad zu sperren.
- **Eskalation auf `BLOCKER`** ist als F8 geplant (eigener Release-Schritt, sobald eine
  Bulk-`satisfies`-Remediation existiert und die Waiver-Lage (#569) stabil ist). Die
  Eskalation erfolgt durch Änderung von **genau** `severity_for_tier` (nicht durch den
  `Finding`-Wert) — deshalb ist der Override der explizite Schalter.
- **Release-Note-Pflicht:** Die Einführung von `VAL-P1` als WARNING und der geplante
  Eskalationsschritt müssen in die Release Notes.
- **Fail-closed bei Regel-Crash (Review-rev2 I1):** Ein *Ausnahmefehler* in `check` wird vom
  GH-400-Handler (`baseline_facade.py:443-459`) zu einem `ValidationError` und blockiert den
  Baseline-Build trotz WARNING. Das ist bestehendes, beabsichtigtes Gate-Verhalten; es gehört
  als Hinweis in die Release Notes neben F8.

### 5.5 Off-Nominal-Kategorie

- Repräsentation: `TestCase.scenario_kind ∈ {nominal, off_nominal}` (Model-Feld aus §4.1, Migration M1).
- `nominal` = Standardfall, `off_nominal` = Fehler-/Ausnahmefall (negative Tests, Grenzfälle).
- Ausgabe: in `coverage-report` (§7.4.1) und in `get_coverage_data` je TestCase mitgeführt; im UI als Select + Badge (§4.6).
- **Bewusst keine** neue Enforcement-Regel in diesem Cluster. Eine Regel „jedes Goal braucht ≥1 off-nominalen TestCase" ist plausibel, aber nicht vom Issue gefordert → offene Frage F2.

### 5.6 Frontend-Touchpoints #402

- `WorkspaceSettings`-Formular: `goals_enabled`-Toggle bleibt bestehen; Default kommt jetzt `true` vom Backend (kein UI-Default im Code hartkodieren).
- `frontend/src/types/index.ts:62` bleibt (`goals_enabled?: boolean`).
- Kein neues UI für `VAL-P1` nötig — Findings erscheinen im bestehenden SE-Auditor.

### 5.7 Acceptance Criteria #402

- **AC-402-1** Given ein frisch über `POST /api/v1/workspaces/` (ohne `goals_enabled`) erzeugter Workspace, Then `goals_enabled == true`.
- **AC-402-2 (RLS-Nachweis)** Given Migration M2 auf einer DB mit einem aktiven `goals_enabled=False`-Workspace **und** dem `migrate`-Lauf unter einer Non-BYPASSRLS-Rolle, Then ist es danach `true`; ein `is_active=False`-Workspace bleibt `false`; die Migration asserted `updated == expected` pro Tenant.
- **AC-402-3** Given ein Extended-Workspace mit `goals_enabled=true` und ≥1 aktiven Goal und 2 aktiven StakeholderNeeds, von denen einer `satisfies`→Goal hat, When SE-Audit, Then genau **ein** `VAL-P1`-Finding für den Need ohne Link; When der zweite Link gesetzt wird, Then 0 Findings.
- **AC-402-4** Given derselbe Workspace mit `goals_enabled=false` oder 0 Goals, When SE-Audit, Then **kein** `VAL-P1`-Finding (Regressionsschutz für Bestandsdaten); When der Workspace-Kontext nicht auflösbar ist, Then ebenfalls 0 Findings (fail-open, Review-m10).
- **AC-402-5** Given ein Minimal- oder Standard-Workspace, Then enthält `active_rule_ids_for_tier(tier)` nicht `VAL-P1`.
- **AC-402-6** Given Migration M3 auf einem Workspace mit materialisiertem `satisfies`-Definition (`is_customized=False`), Then erlaubt `validate_link_pair(ws, "satisfies", "StakeholderNeed", "Goal", manual=True)` ohne Fehler; das Paar ist nicht dupliziert; ein zweiter Migrationslauf ändert nichts (idempotent); eine `is_customized=True`-Zeile bleibt unverändert; Reverse ist `noop` (Pair bleibt bestehen).
- **AC-402-7** Given `POST /api/v1/testcases/ {scenario_kind:"off_nominal"}`, Then `scenario_kind=="off_nominal"` im GET; `{scenario_kind:"invalid"}` → 400.
- **AC-402-8** Given `GET` des Requirement-`coverage-report` für einen off-nominalen TestCase, Then trägt der Eintrag `scenario_kind=="off_nominal"`.
- **AC-402-9 (korrigiert, M4/N1 — exercisiert den Override)** Given ein Extended-Workspace mit `goals_enabled=true`, ≥1 Goal und ≥1 Need ohne `satisfies`-Link, When ein Baseline-Build, Then **kein** `BaselineGateBlockedError`. **Präzisierung (N1):** Der Test prüft **beide** Größen — (a) jedes `VAL-P1`-Finding hat `severity == Severity.WARNING` **nach** dem `RuleEngine`-Re-Stamp (nicht nur im `check`-Rohrückgabewert), und (b) `AuditService.blocking_findings(...)` enthält **kein** `VAL-P1`-Finding. **Mutationsprobe:** Ändert man `ValidationGoalsRule.severity_for_tier` auf `Severity.BLOCKER`, muss dieser Test rot werden (Baseline-Build blockiert).

---

## 6. #399 — Baseline-Mitgliedschaft & Drift (Entscheidung D1)

### 6.1 Model-Delta

**Keine Schema-Änderung, keine Migration.** Drift ist eine reine Ableitung aus
`BaselineDeltaIndexEntry.state`/`.version` gegen den aktuellen Zustand. Eine zusätzliche
`drifted`-Spalte wäre denormalisiert und müsste bei jedem Baseline-Create und jedem Edit
nachgeführt werden — mehr Fehlerquellen als Nutzen.

### 6.2 Service-Contract (`backend/application/baseline_facade.py`, `class BaselineFacade` :116)

```
# NEU
@dataclass(frozen=True)
class ArtifactBaselineMembership:
    baseline_id: UUID
    baseline_name: str
    scope: str                 # document | project | global
    baselined_at: datetime
    baselined_version: int
    current_version: int
    drifted: bool
    drift_known: bool          # False bei Legacy-Einträgen ohne state (state IS NULL)

def memberships_for_artifact(
    self, artifact_id: UUID, ctx: AuthContext
) -> list[ArtifactBaselineMembership]
```

**Algorithmus (löst Review-m4):**

1. **Tenant-Kontext armen — save/restore, niemals blind clear (löst Review-rev2 N2).**
   `memberships_for_artifact` setzt vor jeder Status-Auflösung einen aktiven `TenantContext`,
   weil `baseline.state_capture.capture_states` seine Status über `WorkflowItemState.objects`
   (tenant-*scoped*) liest und ohne Kontext **still leere Status** liefern würde → falsche Drift.

   **Der Aufruf ist nested-safe:** `memberships_for_artifact` wird aus *request-scoped*
   Service-Methoden aufgerufen (`RequirementService.update_requirement`,
   `TestService.update_test_case`, die `retrieve`-Pfade — §6.2/§6.3), in denen die Middleware
   den Kontext bereits besitzt. Ein unbedingtes `clear_request_tenant()` im `finally` würde den
   fremden Kontext zerstören (`persistence/middleware.py:69-73` cleart Thread-Local **und**
   `RESET`t die GUC) — und der **nach** der Membership-Lookup laufende `self._audit(...)`-Write
   (`application/base.py:159-218`) bräuchte einen aktiven Kontext → `TenantContextNotSetError`/500.
   Der Fail-open-Wrapper um die Drift-Ermittlung deckt den *späteren* Audit-Write **nicht** ab.

   **Semantik (save/restore über die Public-API, ohne private `_thread_local`-Zugriffe):**

   ```
   # Pseudocode — exakter Contract
   prior_tenant_id = TenantContext.get_tenant() if TenantContext.is_set() else None
   armed_here = prior_tenant_id is None
   if armed_here:
       set_request_tenant(ctx.tenant_id)      # Thread-Local + SET app.current_tenant
   try:
       ...  # Status-/Drift-Auflösung (Schritte 2–5)
   finally:
       if armed_here:
           clear_request_tenant()             # nur wenn WIR armiert haben
       # sonst: fremden Kontext unangetastet lassen
   ```

   - `TenantContext.is_set()` / `TenantContext.get_tenant()` (`persistence/tenancy.py:63-98`)
     sind die dafür vorgesehenen, read-only Primitives; **kein** Zugriff auf `_thread_local`.
   - **Radikale Alternative (verworfen):** Thread-Local unbedingt capturen und im `finally`
     exakt wiederherstellen (`set_tenant(prior)` bei vorherigem Kontext). Das würde die
     GUC-Konsistenz nur über einen erneuten `SET`-Roundtrip halten und die Middleware-eigene
     `RESET`-Paarung duplizieren; die `armed_here`-Variante ist minimal-invasiv und lässt den
     Dominanzfall (Kontext schon gesetzt) **völlig unberührt**.
   - **Invariante:** Nach dem Aufruf gilt: `TenantContext.is_set()` und der effektive
     Tenant-Wert sind **identisch** zu vor dem Aufruf. Der Service verändert den Ambient-Kontext
     nie, außer er war zuvor leer — dann hinterlässt er ihn wieder leer.
2. **Kandidaten-Baselines (scope-abhängig):**
   - `scope ∈ {document, project}`: `BaselineSnapshot.unscoped.filter(tenant_id=ctx.tenant_id,
     workspace_id=<WS des Artefakts>)`.
   - `scope == "global"`: `BaselineSnapshot.unscoped.filter(tenant_id=ctx.tenant_id, scope="global")`
     — **tenant-weit, ohne Workspace-Filter**. Begründung: ein global-Baseline aus Workspace A
     enthält Artefakte aus Workspace B, speichert aber `workspace_id=A`
     (`BaselineMetadata.workspace_id` ist der aufrufende Workspace,
     `ScopeResolver._resolve_global` walkt den gesamten Tenant). Ein Workspace-Filter würde
     eine reale Mitgliedschaft verschweigen.
3. **Mitgliedschaft** je Kandidat über `BaselineStore().load_states(baseline_id, tenant_id,
   item_ids=[str(artifact_id)])` **und** `load_delta_index(...)` (beide stellen den
   Tenant-Check voran, §3). Kein Treffer im Delta-Index → keine Mitgliedschaft.
4. Für jeden Treffer: `current_version = artifact.version`; `drifted`:
   - wenn `state is not None`: `drifted = (state != current_captured_state)` mit
     `baseline.state_capture.capture_states([DeltaIndexTuple(item_id, version=0,
     entity_type="item")], tenant_id)` als aktuellem Bild (dieselbe kuratierte Feldmenge;
     profitiert vom aktiven `TenantContext` aus Schritt 1);
   - wenn `state is None` (Legacy): `drifted = (entry.version != current_version)`,
     `drift_known = False`.
5. Sortierung absteigend nach `baselined_at`.

**Edit-Integration (nicht-blockierend):**
`RequirementService.update_requirement` (:387) und `TestService.update_test_case` (:245) rufen
nach erfolgreichem Schreiben, aber **innerhalb** der Transaktion,
`BaselineFacade().memberships_for_artifact(...)` auf und reichen die gedrifteten Einträge als
`details={"baseline_drift": [{"baseline_id":…, "scope":…, "baselined_version":…}]}` an
`self._audit(...)` durch.
- Fehler in der Drift-Ermittlung dürfen den Edit **nicht** fehlschlagen lassen
  (`logger.exception`, fail-open) — es ist eine Kennzeichnung, keine Freigabe.
- Gleiches Muster für `delete_requirement` (:564) mit `operation="delete"`.

### 6.3 API-Contract (`backend/rest_api/views.py`, `class ArtifactViewSet` :1530)

**Neu:** `GET /api/v1/artifacts/{id}/baseline-membership/` → `@action(detail=True, methods=["get"], url_path="baseline-membership")`

```json
{
  "artifact_id": "uuid",
  "drifted": true,
  "memberships": [
    {"baseline_id":"uuid","baseline_name":"Release 1.8","scope":"project",
     "baselined_at":"2026-09-01T10:00:00Z","baselined_version":3,
     "current_version":4,"drifted":true,"drift_known":true}
  ]
}
```

Details: leere Liste, wenn das Artefakt in keiner Baseline liegt (`drifted=false`);
`PermissionDeniedError` respektiert die bestehende Rollenmatrix; Antwort ist tenant-scoped über
den Ladepfad aus §6.2.

Zusätzlich nutzen `RequirementViewSet.retrieve` und `TestCaseViewSet.retrieve` denselben Service
und hängen `baseline_drift: {"drifted": bool, "count": int}` **additiv** an die Antwort.
(Read-only; keine Breakage für bestehende Consumer.)

### 6.4 Frontend-Touchpoints #399 (löst Review-m8)

| Datei | Änderung | `data-testid` |
|-------|----------|---------------|
| Requirement-Editor / TestCase-Editor (Detail-Header) | Drift-Badge „Baseline: X — geändert" | `baseline-drift-badge` |
| Requirement-Editor / TestCase-Editor | „Change Request anlegen"-Shortcut, prefilled `affected_item_ids` | `raise-cr-from-drift` |
| `frontend/src/api/artifacts.ts` | `baselineMembership(id)`-Wrapper + Typ | — |
| i18n | `baseline.driftBadge`, `baseline.driftTooltip`, `baseline.raiseChangeRequest` | — |

- **Korrigierter Pfad (Review-m8):** Das geteilte Row-Component ist
  `frontend/src/components/shared/ArtifactRow/ArtifactRow.tsx` (eigenes `.module.css` + Test).
- **Kein N+1:** Das Drift-Badge wird **nicht** in `ArtifactRow` (und damit in jede Liste)
  gesetzt. Es lebt ausschließlich im **Editor-Header** (Detailansicht), der die
  `baseline-drift`-Summary bereits additiv aus `retrieve` erhält. Ein Listen-Badge würde pro
  Zeile einen `baselineMembership(id)`-Call auslösen; das ist ohne einen batch-fähigen
  Membership-Endpoint ausdrücklich **nicht** Teil dieses Clusters.
- **CR-Prefill-Contract (Review-m11):** Der Shortcut ruft
  `POST /api/v1/change-requests/` mit
  `{"workspace_id": "<ws>", "title": "<vorbefüllt>", "affected_item_ids": ["<artifact-uuid>"]}`.
  `affected_item_ids` ist das in §4.4 neu deklarierte, write-only Serializer-Feld.

### 6.5 Acceptance Criteria #399

- **AC-D1-1** Given ein Requirement, das Mitglied einer `project`-Baseline ist, When `PATCH /api/v1/requirements/{id}/` (Titel ändern), Then 200; `GET /api/v1/artifacts/{id}/baseline-membership/` liefert `drifted=true` mit `baselined_version < current_version`.
- **AC-D1-2** Given dasselbe Requirement, unverändert, Then `drifted=false`.
- **AC-D1-3** Given ein Requirement ohne Baseline-Mitgliedschaft, Then `memberships == []`, `drifted=false`.
- **AC-D1-4** Given die Änderung aus AC-D1-1, When der Audit-Eintrag der Operation gelesen wird, Then enthält er `details.baseline_drift` mit der Baseline-ID (Nachweis: Audit-Trail, nicht nur UI).
- **AC-D1-5** Given eine neue Baseline, die auf dem **geänderten** Requirement erzeugt wird, Then ist `drifted=false` (Drift wird durch Re-Baseline aufgelöst).
- **AC-D1-6 (Regression-Pin)** Given ein Standard-Workspace mit Projekt-Baseline, When PATCH ohne `change_reason`, Then 200 (Drift-Marking erzwingt **kein** `change_reason`); Given ein Extended-Workspace, When PATCH ohne `change_reason`, Then weiterhin 400 (`EC_CHANGE_REASON_REQUIRED`) — die bestehende Policy ist unverändert.
- **AC-D1-7** Given ein Cross-Tenant-Aufruf auf ein Artefakt eines anderen Tenants, Then 404/403, niemals Baseline-Metadaten des fremden Tenants (RLS-Nachweis).
- **AC-D1-8** Given ein Legacy-`BaselineDeltaIndexEntry` ohne `state`, Then ist `drift_known=false` und die Antwort bleibt stabil (kein 500).
- **AC-D1-9 (neu, M4/m4)** Given ein `scope="global"`-Baseline, erzeugt aus Workspace A, das ein Artefakt aus Workspace B enthält, When `memberships_for_artifact(<Artefakt-B>)`, Then listet die Antwort dieses globale Baseline als Mitgliedschaft auf (kein Workspace-Filter).
- **AC-D1-10 (korrigiert, m4/N2)** Given ein Drift-Aufruf **ohne** aktiven `TenantContext`, When `memberships_for_artifact(...)`, Then armet der Service ihn selbst, das Ergebnis ist identisch zum Aufruf mit vorab gesetztem Kontext (keine stillen Leer-Status), **und nach dem Aufruf ist `TenantContext.is_set() == False`** (der Service hinterlässt keinen Kontext).
- **AC-D1-12 (neu, N2 — nested/dominant case)** Given ein **bereits armerter** `TenantContext` (Wert `T`, Middleware-Szenario), When `memberships_for_artifact(...)` innerhalb einer Request-scoped Service-Methode aufgerufen wird, Then ist der Kontext nach dem Aufruf **unverändert** (`TenantContext.is_set() == True` **und** `TenantContext.get_tenant() == T`), und ein **nachfolgender** `self._audit(...)`-Write im selben Request gelingt (kein `TenantContextNotSetError`). Regression-Pin gegen den v2-Blind-Clear.
- **AC-D1-13 (neu, N2 — Edit-End-to-End)** Given ein Extended-Workspace mit CR-Pflicht und ein baseliniertes Requirement, When `PATCH /api/v1/requirements/{id}/ {title, change_reason}` unter normaler Middleware (ambienter Kontext gesetzt), Then 200; die Antwort ist kein 500; der Audit-Eintrag existiert **und** enthält `details.baseline_drift` (der Audit-Write lief **nach** der Membership-Lookup erfolgreich).
- **AC-D1-11 (neu, m8/m11)** Given ein gedriftetes Requirement im Editor-Header, Then ist `baseline-drift-badge` sichtbar; Klick auf `raise-cr-from-drift` sendet `POST /api/v1/change-requests/` mit `affected_item_ids == [<artifact-uuid>]` und der neue CR listet dieses Item unter `affected_items`.

---

## 7. #272 — Restpunkte

### 7.1 „Already satisfied / not satisfied"-Tabelle

| # | Top-5-Punkt | Status heute | Beleg | Handlung in Cluster 5 |
|---|-------------|--------------|-------|-----------------------|
| 1 | Realistische Demo-Fixture | **NICHT erfüllt** | `seed_demo.py` (109 Z.): nur Tenant/Workspace/Admin/Workflow; `seed_toothbrush.py` (~440 Z.) hat keine Goals/Baseline/CR | §7.5 — neuer Command |
| 2 | AC + `verification_method` Pflicht beim `in_review → approved` | **TEILWEISE** | `check_mandatory_fields` (:240) ist tier-aware und gated auf Approval; `_EXTENDED.mandatory_fields` (`presets/registry.py:188`) enthält `acceptance_criteria`, aber **nicht** `verification_method` | §7.2 — `verification_method` ergänzen |
| 3 | Link-Typ-Enum + Typ-Kompatibilität | **ERFÜLLT** | 11 Built-ins (`link_types/builtin.py`); `catalog.validate_link_pair` erzwingt `allowed_pairs`/`manual_creatable` | kein Rebuild (§1.2) |
| 3b | Validierung gegen gelöschte Artefakte | **NICHT erfüllt** | `TraceLinkService._check_link_pair` (:273) prüft Existenz + Typ-Paar, **nicht** den Soft-Delete-Zustand der Endpunkte | §7.3 |
| 4 | Pass/Fail-Ergebniskontrakt | **ERFÜLLT (Contract-Ebene)** | `TestRunResult` mit `passed/failed/blocked/not_run` (`models.py:2100`); `TestRun` (:2047); `test_run_service.close_test_run` aggregiert. **`executed_by` ist kein DB-Feld, sondern ein REST-Proxy** aus dem Run-Ersteller (`views.py:4199-4222`) — erfüllt den publizierten API-Contract (Review-i1) | kein Rebuild |
| 4b | Requirement→Test-Coverage-Report | **NICHT erfüllt** | Es gibt nur `allocation-coverage` an Arch-Elementen (`views.py:1889`); `CoverageCalculator` liefert intern, kein dedizierter Endpoint | §7.4.1 |
| 5 | CR ↔ Baseline + affected_items | **ERFÜLLT** | `ChangeRequest.baseline` FK (`models.py:3408`), `ChangeRequestAffectedItem` (:3444), `set_affected_items` (:769) | kein Rebuild; Baseline-Mitgliedschaft über #399 |
| 5b | `content_available` für alle Versionen (v0 = false) | **ANDERS GELÖST** | `creation_baseline_entry()` liefert `content_available: False` (`artifact_diff_service.py:213`) und dokumentiert v0 als leeren Zustand **ohne gespeicherte Payload**; `ArtifactVersionService.get_payload` liefert für v0 `None` | §7.4.2 — Semantik präzisieren statt `True` erzwingen |
| 5c | `implemented`-Gate mit Item-Migration / Re-Baseline/Rollback-Prozess | **OFFEN** | `_capture_affected_items_after` existiert ab `CCB_CLOSING_STATES` | offene Frage F4 (nicht in diesem Cluster) |

### 7.2 `verification_method` in das Approval-Gate

- `backend/presets/registry.py`: `_EXTENDED.mandatory_fields` erhält `"verification_method"` (additiv, hinter `acceptance_criteria`).
- `_STANDARD.mandatory_fields` bleibt unverändert — Standard bleibt leichtgewichtig (ADR-04).
- Wirkung: `check_mandatory_fields` löst `verification_method` über `_resolve_attribute` gegen das `Requirement`-Model auf (Spalte existiert) und blockiert `→ approved` bei leerem Wert.
- **Auflage:** `policy_fields_without_consumer` **liegt in `backend/workflow/precondition_rules.py:615`** (nicht in `presets/registry.py` — Citation korrigiert, Review-m9) und darf `verification_method` nicht als „dead policy" melden. Da `Requirement.verification_method` ein reales Model-Feld ist, greift der Column-Zweig von `_resolve_attribute` — es ist kein Attribute-Definition-Eintrag nötig. Ein Test pinnt das.
- Kein Model-Change, keine Migration.

### 7.3 Link-Validierung gegen gelöschte Artefakte

`backend/application/trace_link_service.py`, `_check_link_pair(...)`:

```
# NEU (private Helper, aufgerufen nur wenn manual=True)
def _assert_endpoints_live(self, source_artifact, target_artifact) -> None
```

- **Direkter Soft-Delete-Check (löst Review-m5):** Beide Endpunkt-`Artifact`-Zeilen sind in
  `_check_link_pair` bereits geladen (bzw. werden dort aufgelöst). Der einzige Soft-Delete-
  Marker ist `Artifact.lifecycle_status` (`"outdated"`). Also:

  ```
  for artifact in (source_artifact, target_artifact):
      if artifact.lifecycle_status == "outdated":
          raise ValidationError(
              f"Cannot create '{link_type}' link: the {item_type} endpoint "
              f"'{artifact.id}' is deleted (outdated). Reactivate it first."
          )
  ```

- **Kein** `outdated_item_ids(...)`-Roundtrip und **keine** `_resolve_entity_id_for_artifact`-
  artige Auflösung nötig (eine solche Helper existierte nicht, und `outdated_item_ids`
  liefert Entity-IDs, während Delta-Index/CR auf Artifact-IDs keyen — beides entfällt).
- Nur `manual=True`: der Diagram-Reconciler (`manual=False`) und Import-Pfade bleiben unberührt.
- Bestehende Links bleiben unverändert (soft-delete ist kein Cascade, GH-484); `reactivate()`
  macht die Endpunkte wieder verknüpfbar.

### 7.4 Requirement→Test-Coverage-Report + `content_available` v0

**7.4.1 Report-Endpoint**

`RequirementViewSet` (`views.py`), neue Action:

`GET /api/v1/requirements/coverage-report/?workspace_id=<uuid>&include_outdated=false&include_unreviewed_ai=false`

Response (Auszug):

```json
{
  "summary": {"total": 24, "covered": 21, "percentage": 87.5, "pending_ai_review": 2},
  "requirements": [
    {"requirement_id":"uuid","uid":"REQ-L1-004","title":"…","level":1,"covered":true,
     "test_cases":[{"id":"uuid","uid":"TC-007","title":"…",
                    "origin":"manual","reviewed":true,"scenario_kind":"off_nominal",
                    "latest_result":"Passed"}]}
  ]
}
```

- Datenquelle: `CoverageCalculator().coverage(...)` (Summary) + `.get_coverage_data(...)` (Zeilen), jeweils mit den neuen Parametern aus §4.5.
- `RequirementCoverageEntry` (`traceability/types.py`) wird **additiv** um `uid: str = ""`, `title: str = ""`, `level: Optional[int] = None` erweitert; `get_coverage_data` befüllt sie.
- `summary.pending_ai_review` stammt aus `CoverageReport.pending_ai_review` (§4.5); mit `include_unreviewed_ai=true` ist es `0`.
- Fehler: fehlendes/ungültiges `workspace_id` → 400 `VALIDATION_ERROR`; unbekannter Workspace → 404.
- Performance: die bestehende SLA-Konstante (`COVERAGE_SLA_MS = 500`) gilt; bei Überschreitung bleibt das Log-Warning bestehen.
- MCP (optional, nicht blockierend): `context.test_coverage` kann dieselbe Anreicherung zurückgeben; nicht Teil der Pflicht-ACs.

**7.4.2 `content_available` für v0 (korrigiert, löst Review-m6)**

- **`content_available` behält für v0 den Wert `False`.** Semantik: „hinter dieser Versionsnummer
  liegt eine gespeicherte `ArtifactVersion`-Payload". v0 ist eine **synthetische** Zeile ohne
  gespeicherte Payload (`ArtifactVersionService.get_payload` → `None`); `True` würde Konsumenten
  täuschen, die eine „Inhalt öffnen"-Aktion an das Flag binden. `{}` ist der *definierte leere
  Zustand*, nicht *gespeicherter Inhalt*.
- **Additiv neu:** `creation_baseline_entry()` liefert zusätzlich
  `"is_creation_baseline": True` (alle anderen Versionszeilen: `False`). Damit kann ein Client
  die synthetische Zeile eindeutig erkennen, ohne dass `content_available` lügt.
- Betroffen: `list_versions` (:472) und `list_versions_for_entity` (:499) — beide nutzen denselben Helper. **Produzenten-Präzisierung (löst Review-rev2 N4):** Die `is_creation_baseline`-Kennzeichnung muss **aus drei Quellen** konsistent kommen: (a) `creation_baseline_entry()` (`artifact_diff_service.py:213-222`) für die v0-Zeile → `True`; (b) die Nicht-v0-Zeilen von `list_versions` stammen aus `ArtifactVersionService.list_revisions` (`artifact_version_service.py:163-185`); (c) die Nicht-v0-Zeilen von `list_versions_for_entity` aus `_current_version_entry` (`artifact_diff_service.py:526-539`). Beide Nicht-v0-Produzenten müssen `is_creation_baseline: False` **explizit** liefern (nicht nur „fehlt, weil der Helper es setzt"). Wer den Key zentral setzt, nennt ihn in einem gemeinsamen Builder; wer dezentral bleibt, zieht alle drei Stellen nach. `rest_api/icd_views.py:740` / `diagram_views.py:373` nutzen den Helper direkt und erben den Key. Bestehende Tests, die `False` pinnen, bleiben grün.
- Abgrenzung: Für Artefakte, die vor Phase 5 erzeugt wurden und **keine** Revision 1 besitzen, bleibt die Erzeugungsinhalte-Rekonstruktion offen (F3).

### 7.5 Realistische Demo-Fixture

**Neuer Command:** `backend/auth_tenancy/management/commands/seed_full_chain.py`
(Separat von `seed_demo.py`, weil dessen Contract „nur Login-Basisdaten, schnell" ist und
E2E-Setups darauf bauen — ein 440-Zeilen-SE-Datensatz dort würde jedes E2E-Setup verlangsamen.)

**Eigenschaften:** idempotent (Workspace-Name `"SysEng Full-Chain Demo"`; bei Existenz Skip wie `seed_toothbrush`), nutzt ausschließlich bestehende Services, `set_request_tenant(...)`/`clear_request_tenant()` wie `seed_toothbrush`.

**Inhalt (Mindestmengen):**

| Artefakt | Menge | Details |
|----------|-------|---------|
| StakeholderNeeds (L0) | 4 | je mit Titel + Beschreibung; **jeder** mit `satisfies`→Goal |
| Goals | 3 | `satisfies`-Links von Requirements; ≥1 Goal mit `satisfies` von einem Need (§5.2) |
| Requirements | 24 | L1/L2 gemischt, **jedes** mit `acceptance_criteria` + `verification_method` |
| ArchitectureElements | 8 | 2 Ebenen (`decomposes`), `allocated-to` von Requirements |
| TestCases | 12 | 8 `nominal`, 4 `off_nominal`; `verifies`-Links; `origin="manual"`, `reviewed=true` |
| TestRuns | 3 | mit `TestRunResult` (gemischt `passed`/`failed`) |
| Baseline | 1 | `scope="project"` |
| ChangeRequest | 1 | `approved`, ≥2 `ChangeRequestAffectedItem`, `baseline` FK gesetzt |

**AC-Fixture:**
- **AC-272-F1** Given leere Tenant-DB, When `python manage.py seed_full_chain`, Then existiert der Workspace und die Tabelle jeder Zeile oben ist ≥ der Mindestmenge.
- **AC-272-F2** Given derselbe Command ein zweites Mal, Then kein Duplikat (idempotent).
- **AC-272-F3** Given der geseedete Workspace, When `GET /api/v1/requirements/coverage-report/`, Then `summary.total > 0` und `summary.covered > 0`.
- **AC-272-F4** Given der geseedete Workspace, When SE-Audit gegen Extended, Then `VAL-P1` liefert 0 Findings (Fixture beweist den Golden Path) und `check_mandatory_fields` blockiert kein Requirement beim `→ approved`-Versuch.

### 7.6 Schließungskriterium für #272

Ein Punkt der Top-5 gilt als in Cluster 5 geschlossen, wenn **alle** seine Testzeilen grün sind:

| Top-5-Punkt | Abgedeckt durch |
|-------------|-----------------|
| 1 Fixture | dieser Spec §7.5 |
| 2 AC + `verification_method` | §7.2 |
| 3 Link-Enum/Kompatibilität | existiert; Rest (gelöschte Endpunkte) §7.3 |
| 4 Pass/Fail + Coverage-Report | Enum/Aggregation existiert (i1); Report §7.4.1; False-Green-Ausschluss durch **#424** (§4.5) |
| 5 CR↔Baseline / `content_available` | CR-Existenz existiert; Baseline-Kopplung durch **#399** (§6); `content_available`-Semantik §7.4.2 |

Damit ist `Closes #272` **erst** zulässig, wenn #424 und #399 mit-gemerged sind — die
Issue-Referenzen im PR müssen alle vier nennen.

---

## 8. Migrations-Übersicht (Abhängigkeiten, RLS, Reverse)

**Gesamtzahl: 3 Migrationsdateien.** #399 und #272 erzeugen **keine** Migration.

| # | Datei | Typ | Inhalt | `dependencies` | RLS-Behandlung | Reverse |
|---|-------|-----|--------|----------------|----------------|---------|
| 1 | `backend/persistence/migrations/0099_testcase_origin_reviewed_scenario_kind.py` | **Schema-only** | 3× `AddField` + 1× `AlterField` (origin-Default → Model-Default) | `[("persistence","0098_requirement_rationale_requirement_source")]` | **Keine nötig:** reine DDL (`AddField`/`AlterField`), **kein** `RunPython`, keine Row-Writes → RLS nicht anwendbar, kein Zero-Row-No-op. Bestandszeilen erhalten `unknown`/`false`/`nominal` über den Spalten-Default. | Standard-Django-Reverse (`RemoveField`/Default-Revert); Entfernen drop't die Spalten samt Daten (dokumentierte Datenverlust-Semantik von `AddField`) |
| 2 | `backend/persistence/migrations/0100_workspace_goals_enabled_default.py` | Schema + **Daten** | `AlterField` (schema-only) + `RunPython` (`goals_enabled=True` für aktive Workspaces) | `[("persistence","0099_testcase_origin_reviewed_scenario_kind")]` (transitiv nach `0098`) | **Arming pro Tenant:** `SET app.current_tenant` über `Tenant`-Iteration; Zähl-/Update-Lauf im armed Kontext; **Models via `apps.get_model("persistence", …)`** (historische Models, **kein** Live-`TenantManager`/Thread-Local, N6); `assert updated == expected` (lauter Fehler statt stiller Null-Update); `finally: RESET`. `pl_workspace` ist `FORCE ROW LEVEL SECURITY`. | `RunPython(reverse_code=noop)` (kein Vorzustands-Marker); `AlterField`-Reverse revertiert nur den Default |
| 3 | `backend/link_types/migrations/0009_backfill_need_satisfies_pair.py` | Daten | `satisfies`-Paar `StakeholderNeed→Goal` für globale + nicht-customized Workspace-Definitionen | `[("link_types","0008_seed_satisfaction_link_types")]` | **Arming pro Tenant** (Muster `0005`); `lt_*`-Tabellen sind `FORCE ROW LEVEL SECURITY` | `migrations.RunPython.noop` (spiegelt `0005`; kein Entfernen, um Tenant-Customizations nicht zu zerstören) |

**Reihenfolgehinweis:** `0009` (link_types) muss **vor** dem Seed-Command (§7.5) und vor jedem
Test laufen, der `satisfies` Need→Goal erstellt. `0099`/`0100` sind untereinander geordnet
(`0100` → `0099` → `0098`).

---

## 9. Teststrategie (übergreifend)

- **Backend:** pytest; `DB_USER` lokal auf den Superuser überschreiben (sonst scheitern alle RLS-Tests). Zusätzlich ein Migrations-Testlauf unter Non-BYPASSRLS-Rolle für AC-402-2.
- **Mutationsproben (Pflicht, weil diese Änderungen False-Green-Pfade schließen):**
  - Prädikat `counts_as_verification_evidence` aus `_filter_to_testcase_ids` entfernen → AC-424-3/AC-424-5 müssen rot werden.
  - Prädikat aus dem **Audit**-Helper `_active_verifying_test_cases` entfernen → AC-424-9/AC-424-10 müssen rot werden (**neuer dritter Consumer**, Review-M1).
  - Aktivierungs-Gate in `VAL-P1` entfernen → AC-402-4 muss rot werden.
  - `ValidationGoalsRule.severity_for_tier` auf `BLOCKER` setzen → AC-402-9 muss rot werden (**N1: der Override, nicht der `Finding`-Wert, ist der Hebel**).
  - `origin="ai_generated"` im Interview-Adapter P4 entfernen → AC-424-14 muss rot werden (**N3**).
  - `origin="ai_generated"` im MCP-Derive P3 entfernen → AC-424-15 muss rot werden.
  - `memberships_for_artifact` auf blindem `clear_request_tenant()` festnageln (statt `armed_here`-Restore) → AC-D1-12 muss rot werden (**N2**).
  - Drift-Vergleich auf `drifted=False` festnageln → AC-D1-1 muss rot werden.
  - Global-Scope-Kandidatenfilter auf `workspace_id` beschränken → AC-D1-9 muss rot werden.
- **Neue Testdateien (Vorschlag):**
  `backend/application/tests/test_testcase_origin_reviewed_424.py`,
  `backend/traceability/tests/test_verif_p8_evidence_424.py`,
  `backend/traceability/tests/test_val_p1_402.py` (enthält den `severity_for_tier`-Re-Stamp-Nachweis, N1),
  `backend/application/tests/test_testcase_producers_424.py` (P3/P4-Markierung + Additivitäts-Wachtest, N3),
  `backend/application/tests/test_baseline_drift_399.py` (inkl. Nested-TenantContext-Nachweis, N2),
  `backend/rest_api/tests/test_requirement_coverage_report_272.py`,
  `backend/link_types/tests/test_backfill_need_satisfies_pair.py`.
- **Frontend:** `vitest run` grün; `i18n-parity` + `ui-ratchet` grün mit **gesenkten** Baselines.
- **E2E:** `seed_full_chain` als neuer, optionaler Fixture-Pfad; bestehende Playwright-Suite darf nicht langsamer werden.

---

## 10. Out of Scope

- **#569** (`findings` / `finding_key` / Waiver für den SE-Auditor, Cluster 2) — ausdrücklich **nicht** Teil von Cluster 5. Die neuen `VAL-P1`-Findings erben die aktuelle, noch instabile Finding-Identität.
- Hard-Block für Edits an baselinierten Artefakten ohne genehmigten CR (bräuchte eigenen ADR, siehe D1).
- `Measure`/MOE/MOP/TPM, Projekt-Meilensteine, ReqIF-Identität (Cluster 6).
- Backfill von Erzeugungsinhalten für Pre-Phase-5-Artefakte ohne Revision 1 (F3).
- `implemented`-Gate mit Item-Migration / Re-Baseline-Rollback-Prozess (F4).
- Requirement-seitige Off-Nominal-Klassifikation.
- **Nachträgliche KI-Erkennung historischer TestCases aus dem Audit-Trail** (F7) und **Batch-Membership-Endpoint** (N+1-Vermeidung für ein Listen-Badge, §6.4).

---

## 11. Offene Fragen & Risiken

| ID | Frage / Risiko | Vorschlag |
|----|----------------|-----------|
| F1 | Soll `VAL-P1` auch dann feuern, wenn `goals_enabled=true`, aber **0** Goals existieren (aktuell: Nein, Gate 2)? | Beim konservativen Gate bleiben; Eskalation nur mit explizitem Opt-in. |
| F2 | Braucht es eine Regel „jedes Goal hat ≥1 off-nominalen TestCase"? | Nicht in diesem Cluster; Follow-up-Issue, sobald `scenario_kind` produktiv Daten trägt. |
| F3 | Wie werden Erzeugungsinhalte für Artefakte rekonstruiert, die vor Phase 5 ohne Revision 1 entstanden sind? | Eigener Backfill/ADR; §7.4.2 macht nur den definierten v0-Zustand ehrlich. |
| F4 | `implemented`-Gate mit Item-Migration + Re-Baseline/Rollback-Prozess (#272 Punkt 5 letzter Satz). | Eigener Cluster; hängt an einem Re-Baseline-Konzept, das es noch nicht gibt. |
| F5 | Ist `origin` client-deklarierbar (Spoofing: Nutzer sendet `manual` für KI-Inhalt)? | Akzeptiert: `origin` ist ein Prozess-Hinweis, kein Sicherheitsmerkmal; der Audit-Trail (`test.derive_from_requirement`) bleibt die Wahrheit. `unknown` ist clientseitig gesperrt, damit der Grandfathering-Pfad kein Schlupfloch wird. |
| F6 | Coverage-KPI-Einbruch durch §4.5. | Nur für **erkannte** (`ai_generated` + unreviewed) TestCases; `unknown`-Bestandszeilen sind grandfathered → keine pauschale KPI-Regression. `pending_ai_review` macht den Effekt sichtbar; `include_unreviewed_ai=True` bleibt als Roh-Sicht. |
| **F7** | **Nachträgliche KI-Erkennung historischer TestCases:** Bestandszeilen sind `origin="unknown"`; ein Teil davon ist KI (über den Derive-Pfad unmarkiert persistiert). | **Folge-Issue (nicht Cluster 5):** Management-Command, das `audit_entry` liest (`tool_name='test.derive_from_requirement'`, `entity_type='TestCase'`, Join auf `entity_id`, gruppiert pro Tenant) und die Zuordnung `unknown → ai_generated/unreviewed` setzt. Einschränkung dokumentieren: Vor #626 erzeugte der Derive-Write-Pfad **null** Audit-Zeilen (Op-Vokabular-Lücke) → nur post-#626 verlässlich. Bis dahin ist die Rest-Unsicherheit bewusst akzeptiert. |
| **F8** | **Eskalation `VAL-P1` WARNING → BLOCKER.** | Eigener Release-Schritt nach einer Deprecation-Periode und sobald eine Bulk-`satisfies`-Remediation existiert (und #569 stabil ist). Release Notes müssen beide Zustände nennen. |
| F9 | **CR-Prefill-Feld `affected_item_ids` im Serializer** ist eine kleine API-Erweiterung außerhalb des engen #272/#399-Wortlauts. | Bewusst: D1 verlangt den CR-Einstieg am gedrifteten Artefakt; ohne deklariertes Feld gäbe es keinen Contract. Additiv + write-only. |
| **F10** | **Baseline-`state_capture` erfasst `origin`/`reviewed`/`scenario_kind` nicht** (`baseline/state_capture.py:226-243`), obwohl `scenario_kind` (PATCH) und `reviewed` (Review-Action) editierbar sind und `version` bumpen → ein Baseline-Diff sieht eine Versionsbewegung ohne Content-Change (Review-rev2 N5). | **Follow-up / Präzisierung:** die drei TestCase-Felder in den `_capture_items`-TestCase-Zweig aufnehmen **oder** die bewusste Ausklammerung (Prozess-Metadaten ≠ fachlicher Inhalt) im Modul-Contract dokumentieren. Nicht blockierend für Cluster 5; als eigener kleiner Change nach Merge. |

---

## 12. Entscheidungsregister

| ID | Entscheidung | Status |
|----|--------------|--------|
| **D1** | **#399: Drift-Kennzeichnung statt Hard-Block.** Baseline-Mitgliedschaft erzeugt eine sichtbare, auditierte Drift-Markierung; kein Edit-Verbot ohne genehmigten CR. Global-Scope-Kandidaten tenant-weit; `capture_states` mit aktivem `TenantContext`; CR-Prefill über `affected_item_ids`. | **gewählt (v2 korrigiert)** |
| **D2** | **#402: `goals_enabled`-Default → `True`.** Model-/Serializer-Default flippen; RLS-sichere Datenmigration aktiviert bestehende aktive Workspaces; `goals_ai_enabled` bleibt `False`; **`VAL-P1` startet als `WARNING`** (advisory, kein Baseline-Gate), doppelt gegated. | **gewählt (v2 korrigiert)** |
| D3 | #402: `satisfies` erhält `StakeholderNeed→Goal` als direkte Kante (statt transitiver Ableitung über Requirements). | gewählt |
| **D4** | **#424: `origin`-Backfill `unknown`, `reviewed=False` für Bestandszeilen** (schema-only, kein `RunPython`). Ausschluss ist exakt das Paar `ai_generated` + `not reviewed`; `unknown` ist grandfathered und dokumentiert (F7). Ein pauschales `reviewed=True` wird **nicht** mehr gesetzt. | **gewählt (v2 korrigiert, ersetzt v1-D4)** |
| D5 | #272: eigener `seed_full_chain`-Command statt Erweiterung von `seed_demo`. | gewählt |
| **D6** | **#272/`content_available`: v0 behält `False`; additiv `is_creation_baseline: true`.** Semantik statt Zwangs-`True`. | **gewählt (v2 neu, löst Review-m6)** |
| **D7** | **#399/Frontend: Drift-Badge nur im Editor-Header, nicht in `ArtifactRow`** (N+1-Vermeidung); Listen-Badge nur mit späterem Batch-Endpoint. | **gewählt (v2 neu, löst Review-m8)** |

---

## 13. Review-Auflösungsregister (v1 → v2)

| Finding | Auflösung |
|---------|-----------|
| **M1** — VERIF-P8 dritter False-Green-Consumer | §4.5(3): neuer Audit-Helper `_active_verifying_test_cases` wendet das gemeinsame Prädikat `counts_as_verification_evidence` an; VERIF-P8 nutzt ihn, TRACE-P6 bewusst nicht. AC-424-9/10 + Mutationsprobe. |
| **M2** — `reviewed=True`-Backfill-Prämisse widerlegt | §4.2/D4: kein `reviewed=True` mehr; Bestandszeilen `origin="unknown"`, `reviewed=False`; „ausnahmslos manuell" gestrichen; Rest-Detektion als F7. AC-424-7 neu. |
| **M3** — Migrations nicht RLS-safe | §3/§8: **M1 (0099) ist explizit schema-only** (kein `RunPython`, DDL-immune); **M2 (0100)** enthält die einzige Datenoperation und armt pro Tenant + asserted `updated == expected`; **M3 (0009)** armt pro Tenant. |
| **M4** — VAL-P1 retroaktiver Baseline-Blocker | §5.4/D2: `VAL-P1` ist `WARNING`; `blocking_findings` filtert auf BLOCKER → kein Gate-Block. AC-402-9 + Mutationsprobe. Eskalation F8. **In v2 unvollständig** — der wirksame Hebel fehlte; nachgetragen in **§14/N1** (`severity_for_tier`-Override). |
| **m1** — `reviewed`-PATCH still ignoriert | §4.4: explizite `validate()`-Rejection via `self.initial_data` für `reviewed` **und** `origin`; AC-424-6 testet beide. |
| **m2** — Testbruchliste falsch | §2/§5.1: `test_workspace_create_schema_conformance.py:121` ergänzt; `test_goal_views.py:90` als nicht-brechend korrigiert. |
| **m3** — `link_types/0009` Filter/Dependency/Reverse | §5.2/§8: `is_customized=False`-Filter explizit, `dependencies=[("link_types","0008_seed_satisfaction_link_types")]`, Reverse `RunPython.noop` (spiegelt 0005). AC-402-6 erweitert. |
| **m4** — Global-Scope + `capture_states`-Kontext | §6.2: global-Kandidaten tenant-weit ohne Workspace-Filter; `memberships_for_artifact` armet `TenantContext` (finally clear). AC-D1-9/10. |
| **m5** — `_assert_endpoints_live`-Auflösung unbestimmt | §7.3: direkter `Artifact.lifecycle_status == "outdated"`-Check auf den bereits geladenen Endpunkten; kein Entity-ID-Mapping. |
| **m6** — v0 `content_available`-Semantik | §7.4.2/D6: `content_available` bleibt `False`; additiv `is_creation_baseline: true`; Client-Contract dokumentiert. |
| **m7** — `_ENTITY_FIELDS`-Begründung invertiert | §4.3: korrigierte Begründung (nicht gelistet = nicht gesnapshottet) + Einmal-Diff-Folge analog Icd dokumentiert. |
| **m8** — ArtifactRow-Pfad + N+1 | §6.4/D7: Pfad `shared/ArtifactRow/ArtifactRow.tsx` korrigiert; Badge nur im Editor-Header; Listen-Badge out of scope. AC-D1-11. |
| **m9** — falsches Modul | §7.2: `policy_fields_without_consumer` → `backend/workflow/precondition_rules.py:615`. |
| **m10** — VAL-P1-Gate nicht fail-open | §5.3: `Workspace.unscoped.filter(..., tenant_id=..., goals_enabled=True).exists()` → else `return []`. AC-402-4 erweitert. |
| **m11** — AC-Lücken / AC-424-1 self-defeating | AC-424-1 ohne `reviewed`-Payload; neu AC-424-11 (MCP `test.mark_reviewed`), AC-424-12 (`pending_ai_review`), AC-D1-11 (Drift-Badge/CR-Shortcut), CR-Prefill-Endpoint/`affected_item_ids` in §4.4/§6.4; TestCase-Review-Button-Zieldatei benannt. |
| **i1** — `executed_by` REST-Proxy | §7.1 Punkt 4: Contract-Ebene explizit als erfüllt dokumentiert. |
| **i2** — zwei Review-Konzepte | §4.3: Verhältnis `reviewed` ↔ Workflow-`approved` ↔ Rule 7 explizit definiert; AC-424-13. |
| **i3** — #569 Scope isolation | beibehalten (§1.2, §10); keine Änderung nötig. |

---

## 14. Review-Auflösungsregister (v2 → v3) — Review `2026-09-22-…-review-rev2.md`

Verdikt der Re-Review v2 war `CHANGES_REQUESTED` mit 3 Major (N1–N3) und 4 Minor
(N4–N7), nachdem M1/M2/M3 bereits `RESOLVED` waren. Revision 3 löst **N1, N2, N3, N6**
verbindlich; N4, N5 und N7 werden bewusst als Präzisions-/Folgepunkte geparkt (siehe unten).

| Finding | Severity | Auflösung in Revision 3 |
|---------|----------|-------------------------|
| **N1** — `VAL-P1` wird vom `RuleEngine` auf BLOCKER re-gestempelt; der `Finding`-Wert ist wirkungslos | major | §5.3 Punkt 6: explizite Methode `ValidationGoalsRule.severity_for_tier(tier) -> Severity.WARNING` (Hook exakt benannt: `rule_engine.py:137-154` liest `rule.severity_for_tier`, Basis `registry.py:233-240` = BLOCKER; Muster CONS-P11/TRACE-P2). §5.4: Contract-Tabelle (Finding-Wert vs. Override vs. `blocking_findings`); Eskalation = Änderung **nur** des Overrides. **AC-402-9 korrigiert:** prüft den Re-Stamp **nach** dem Engine + `blocking_findings`; Mutationsprobe (Override→BLOCKER ⇒ AC rot) in §9. I1 (Crash fail-closed) als Release-Note ergänzt. |
| **N2** — `memberships_for_artifact` cleart einen fremden `TenantContext` | major | §6.2 Schritt 1: **save/restore** statt Blind-Clear (`is_set()`/`get_tenant()` vorher, `armed_here`-Flag, `clear_request_tenant()` nur im `finally` **wenn wir armiert haben**; Public-API, kein `_thread_local`). Invariante: Ambient-Kontext unverändert. **AC-D1-10 korrigiert** + **AC-D1-12 (nested)** + **AC-D1-13 (Edit-End-to-End mit Audit-Write nach Lookup)**. Mutationsprobe in §9. |
| **N3** — zweiter LLM-TestCase-Producer (Interview) bleibt `manual`/`reviewed=true` | major | **§4.8 neu:** normative, per Grep verifizierte Enumeration **aller** Produzenten (P1–P5) + P4-Spezifikation (`_test_case` setzt `origin="ai_generated"`, `reviewed=False`, Überschreibschutz) + Additivitäts-Wachtest (AC-424-16) + Mutationsproben. AC-424-14 (Interview), AC-424-15 (Derive), AC-424-17 (Default-Abgrenzung `test.create` bleibt `manual`). Die „dokumentierte Ausnahme" aus dem Review-Vorschlag wird **verworfen** (würde die False-Green-Klasse wieder einführen). |
| **N6** — `0100` nutzt Live-Manager statt historischer Models | minor | §5.1: `RunPython` löst `Tenant`/`Workspace` über `apps.get_model("persistence", …)` auf (Vorbild `link_types/0005:73-90`, Begründung `0073:12-17`). Erklärt, warum der Live-`TenantManager` (`tenancy.py:135-143`) mit `TenantContextNotSetError` scheitert (GUC ≠ Thread-Local). §8-Tabelle Zeile 2 nachgezogen; Assertion-Semantik unter Non-BYPASSRLS präzisiert (AC-402-2). |

**Bewusst geparkt (nicht Teil von Revision 3, kein Regress von M1–M3/m1–m11):**

- **N4** (minor, #272 §7.4.2): `is_creation_baseline: False` für Nicht-v0-Zeilen erfordert
  zusätzliche Producer (`ArtifactVersionService.list_revisions`, `_current_version_entry`).
  Als Präzisierung in §7.4.2 nachgezogen (Producer benannt), ohne die Semantik zu ändern.
- **N5** (minor): `origin`/`reviewed`/`scenario_kind` fehlen im Baseline-`state_capture`-Feldedict.
  Als offene Frage **F10** ergänzt (nicht blockierend; berührt die Drift-Semantik nur additiv).
- **N7** (minor): Service-`origin`-Validierung ist weiter als die Client-Choice-Menge
  (`unknown` durch Service-Caller schreibbar). Als Präzisierung in §4.3 dokumentiert: die
  Client-Writable-Menge ist `{manual, ai_generated}`; `unknown` bleibt system-/migrationsseitig.

**Nicht regressiert:** M1 (§4.5(3)), M2 (§4.2/D4), M3 (§3/§5.1/§8) sowie m1–m11 bleiben
unverändert bestehen; i1–i3 unverändert. #569 bleibt out of scope (§1.2, §10).

**Rest-Verdikt-Frage:** Nach Auflösung von N1–N3 + N6 ist der Cluster Gegenstand einer
erneuten `concept-reviewer`-Prüfung. Die Migration-Design-Frage (`database-engineer`) ist
seit M1–M3 sound und durch N6 zusätzlich feasibility-abgesichert.
