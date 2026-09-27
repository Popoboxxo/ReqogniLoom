# Verifikationsprotokoll — Attribut-Analyse (3-Stufen-Modell)

**Stand:** 11.09.2026 · Basis **v1.8.0-beta.10** (`b4c3a910`) · QS `172.20.5.120`
**Zweck:** Jede tragende Aussage des Reports wurde **einzeln** nachgeprüft — live gegen die laufende
Instanz und/oder am Quellcode. Ausführbar über `docs/se/attribut/verify_all.py` (13 Prüfungen).

Ergebnis: **12/13 bestätigt**, 1 zunächst falsch bewertete Aussage wurde durch Nachprüfung **präzisiert**
(uid, s. §2) — der ursprüngliche Verdacht war richtig, mein Prüfmuster zu grob.

> **Nachtrag 2026-09-27 (ADR-005 / ADR-007) — Zeilen 14–19 sind *nicht* über `verify_all.py`
> entstanden.** Sie sind am **Quellcode** geprüft, jeweils mit dem Dateipfad in der Spalte „Beleg",
> und — wo das Verhalten maschinell prüfbar ist — mit einem benannten Regressionstest verankert.
> `verify_all.py` ist unverändert 13 Prüfungen groß und wurde in dieser Runde nicht erweitert.

---

## 1. Prüftabelle

| # | Aussage | Urteil | Beleg |
|---|---|---|---|
| 1 | Attributliste **und** `required`-Flags sind über `minimal`/`standard`/`extended` **identisch** (alle 11 Typen) | ✅ bestätigt | `GET /attribute-defaults/{type}/{preset}/` je Typ, Signaturen verglichen |
| 2 | `priority` fehlt als Requirement-Attribut | ✅ bestätigt | Attribute: `uid, category, type, level, complexity_fibonacci, verification_method, status, title, description, description_editor, acceptance_criteria` |
| 3 | `rationale` fehlt als Requirement-Attribut | ✅ bestätigt | dito |
| 4 | `source` fehlt als Requirement-Attribut | ✅ bestätigt | dito |
| 5 | `uid` ist vorhanden, aber `editable=False` | ✅ bestätigt | Definition + Bootstrap `READ_ONLY_MODEL_FIELDS = {"uid", "requestor_id"}` |
| 6 | 8 Modelle behaupten `uid "(read-only, auto-generated)"` | ✅ bestätigt | `models.py:973, 1059, 1187, 1558, 1671, 2524, 2657, 2890` |
| 7 | Es gibt **keine** uid-Generierung im Produktivcode | ✅ bestätigt (nach Präzisierung, s. §2) | 8 Grep-Treffer = 1 Validator + Migrations-Helfer |
| 8 | `uid` ist in allen Serializern `read_only` → Client kann es nicht setzen | ✅ bestätigt | 8× `serializers.CharField(read_only=True, allow_null=True)` |
| 9 | Live: **0 von 6** Requirements mit `uid` | ✅ bestätigt | Workspace `5147dcd9-60e6-4663-9fdb-f073e78208e8` |
| 10 | `mandatory_fields` ist **pro Preset**, nicht pro Item-Typ definiert | ✅ bestätigt | `presets/registry.py:170` |
| 11 | Baseline-State erfasst `Artifact.custom_fields` (inkl. „rationale"-Beispiel) | ✅ bestätigt | `baseline/state_capture.py:46` + Docstring (Issue #398) |
| 12 | QS: **0 Artefakte** mit `custom_fields` → Greenfield für Wert-Migration | ✅ bestätigt | requirements/needs/architecture/testcases geprüft |
| 13 | Interview-Adapter mappt `rationale → description` | ✅ bestätigt | `interview_artifact_adapters.py:166` |
| 14 | `level` ist **abgeleitet und schreibgeschützt**, in keiner Stufe Pflicht | ✅ bestätigt (ADR-005, 2026-09-27) | `bootstrap_attribute_definitions.py::READ_ONLY_MODEL_FIELDS` enthält `level`; `stage_matrix.py::MATRIX_OVERRIDES["Requirement"]["level"] == {"visible": {2, 3}, "mandatory": {}}`; `RequirementSerializer.level` ist `read_only=True`; `RequirementService.create_requirement`/`update_requirement` haben keinen `level`-Parameter; `mcp_server/tools/requirements.py` lehnt `level` in create/update mit `VALIDATION_ERROR` ab |
| 15 | **Kein Writer befüllt `source`** — das Feld ist reines Nutzer-Freitextfeld | ✅ bestätigt (ADR-007, 2026-09-27) | LLM-Ableitung mappt **nur** `rationale`: `mcp_server/tools/ai_derivation.py:140-142` (`_derived_requirement_custom_fields`); CSV-Export-Feldliste `application/export_service.py:121-132` ohne `source`; ReqIF-Attributkonstanten `application/reqif_export_service.py:246-253` ohne `ATTR-SOURCE`. REST/MCP lesen es nur durch: `rest_api/views.py:1107` und `mcp_server/tools/requirements.py:495` sind reine `data.get("source", "")`-Durchreichungen des Client-Payloads |
| 16 | Der **einzige** Durchsetzungspunkt für Relation-Regeln ist das Baseline-Gate | ✅ bestätigt (ADR-007, 2026-09-27) | Einziger Produktions-Aufrufer von `AuditService.blocking_findings` ist `application/baseline_facade.py:488` (fail-closed bei Auditor-Ausfall, `baseline_facade.py:493-504`); Remediation-Pfad je Finding: `baseline/waivers.py` (`BaselineGateWaiver`), `baseline/models.py:190-215`. Gepinnt in `backend/traceability/tests/test_se_rule_vocabulary_adr007.py::TestBaselineGateIsTheOnlyBlockingProducer` |
| 17 | Create-Gate-Erzwingung von Relations-/Policy-Pflichten ist **empirisch widerlegt** | ✅ bestätigt | `attribute_definitions/stage_matrix.py:30-32` und `:36-46`; Migration `attribute_definitions/migrations/0005_relax_requirement_create_required.py:3-9` („~15 E2E specs"); Regressionstest `rest_api/tests/test_bootstrapped_definition_allows_creates.py:35-46`; eigener Wächter `rest_api/tests/test_audit_adr007_create_gate_scope.py` |
| 18 | `stage_mandatory` ist **seeded, aber unconsumiert** — Verdrahtung wartet auf den AWMS-Backfill | ✅ bestätigt (ADR-007, 2026-09-27) | `stage_matrix.py:34-41` („seeded and discoverable but deliberately not yet consumed … requires the WS7/AWMS value migration (#940)"); `attribute_definitions/mandatory_fields.py` liest `required`, nicht `stage_mandatory` |
| 19 | `TRACE-P2` bleibt **WARNING** in **allen** Stufen (keine Promotion auf BLOCKER) | ✅ bestätigt (ADR-007, 2026-09-27) | `traceability/audit/rules/trace_derivation_allocation.py::RequirementAllocatedToArchitectureRule.severity_for_tier` gibt unbedingt `Severity.WARNING` zurück; Begründung (#581) im Docstring derselben Methode. Gepinnt in `traceability/tests/test_audit_calibration_581.py` und `traceability/tests/test_se_rule_vocabulary_adr007.py::TestTraceP2StaysWarning` (Standard **und** Extended) |

---

## 2. Die eine präzisierte Aussage: `uid`

**Erstbefund des Skripts:** „WIDERLEGT — 8 Treffer" für die Aussage „keine uid-Generierung".
**Ursache:** zu grobes Prüfmuster (`grep -iE 'def .*uid'`).

**Nachprüfung der 8 Treffer:**

| Treffer | Art |
|---|---|
| `migrate_se_docs.py:364/375/380/392/635/760` | **Migrations-Command** (Parameter/Helfer) — kein Produktivpfad |
| `requirement_service.py:193` `_assert_uid_unique_in_workspace` | **Validator** (prüft Eindeutigkeit, erzeugt nichts) |
| `persistence/migrations/0055_…:43` `_dedupe_uid_collisions` | **Datenmigration** (räumt Kollisionen auf) |

**Ergebnis: die Aussage ist BESTÄTIGT** — es existiert **kein** Generator.

### Der vollständige uid-Befund

```python
# backend/persistence/models.py:969-974 — identisch in 8 Modellen
uid = models.CharField(
    max_length=64, null=True, blank=True,
    help_text="Unique identifier (read-only, auto-generated)",
)
```

```
# Anlege-Signatur: uid ist ein Durchreiche-Parameter mit Default None
#
# ADR-005 (2026-09-27): `level` ist aus dieser Signatur ENTFERNT. Das Feld ist
# abgeleitet (Neuberechnung bei jeder Hierarchieänderung) und schreibgeschützt;
# ein Create legt seine Kaskadenposition allein über `parent_id` fest. Die
# Signatur lautet heute:
create_requirement(self, workspace_id, title, ctx, description="", acceptance_criteria="",
                   rationale="", source="", category="", parent_id=None, type="SyReq",
                   complexity_fibonacci=None, verification_method=None,
                   uid: Optional[str] = None,
                   custom_fields=None) -> Requirement
```

```
# Serializer: read-only → kein Client kann es setzen
uid = serializers.CharField(read_only=True, allow_null=True)      # 8×
```

| Frage | Antwort |
|---|---|
| Wird `uid` automatisch erzeugt? | **Nein** — kein Generator, kein Signal, kein Service |
| Kann ein Nutzer es setzen? | **Nein** — in allen Serializern `read_only` |
| Kann ein Agent (MCP) es setzen? | **Nein** — dieselben Serializer |
| Wer füllt es dann? | nur **Import/Migration**: `reqif_import_service.py:562/698`, `migrate_se_docs` |
| Live-Bestand | **0 von 6** Requirements |

**Folge:** Für jedes normal angelegte Artefakt ist `uid` **dauerhaft NULL**. Der `help_text` beschreibt
einen Zustand, den der Code nicht herstellt — ein gebrochenes, dokumentiertes Versprechen.

**Auswirkung auf den Report:** `uid` wurde von „Stufe-1-Pflichtfeld" auf **system-owned** korrigiert
(Challenge-Punkt **C9**). Ein Feld, das der Nutzer nicht liefern **kann**, darf keine Nutzer-Pflicht sein.

**Vorgeschlagene Lösung:** Autogenerierung implementieren — `{PREFIX}-{NNN}` je `(workspace, item_type)`,
eindeutig (der Constraint aus Migration `0055` existiert bereits), nie wiederverwendet. Andernfalls den
`help_text` auf den tatsächlichen Zustand korrigieren.

---

## 3. Nicht verifizierbar / offen

| Punkt | Warum offen |
|---|---|
| Aussage 1 nur für **globale** Defaults geprüft | Workspace-Ebene materialisiert daraus (`AttributeDefinitionService.resolve`); ein Workspace mit `is_customized=true` kann abweichen — in der QS liegt keiner vor |
| `Measure`-Entität | existiert nicht (bestätigt, #393); die Empfehlung ist ein **Vorschlag**, keine Messung |
| Migrationssystematik (AWMS) | Konzept; es gibt **keine** Implementierung zu prüfen |
| Produktionsdaten | alle Messungen stammen aus der **QS**; PROD wurde nicht angefasst |

---

## 4. Reproduktion

```bash
# auf der QS-Sandbox
cd /home/hermes/repos/ReqogniLoom
python3 verify_all.py        # 13 Prüfungen, Tabelle + Zähler
```

Voraussetzungen: `.env` mit `SYSTEM_ADMIN_PASSWORD`, Backend auf `127.0.0.1:8001`
(override via `RL_BASE`), Repo-Checkout auf `v1.8.0-beta.10`.
