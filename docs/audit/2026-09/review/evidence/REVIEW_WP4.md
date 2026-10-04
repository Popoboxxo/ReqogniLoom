---
type: REVIEW
scope: "WP-4 (Data Model) — adversarial second review"
status: final
date: 2026-10-01
author_agent: code-reviewer
branch: chore/audit-review-2026-09
method: "Read-only adversarial verification against real product source (HEAD 10dc620f) and live Postgres of the running stack (ai-native-reqflow-poc-postgres-1, DB reqflow, SELECT only). Audit-owned AUDIT_EVIDENCE/* explicitly NOT used as proof. Every verdict carries a file:line counter-evidence quote checked at HEAD, or a live DB measurement."
targets:
  - AUD-2026-09-154
  - AUD-2026-09-156
  - AUD-2026-09-157
  - AUD-2026-09-158
  - AUD-2026-09-159
  - AUD-2026-09-160
  - AUD-2026-09-161
  - AUD-2026-09-162
  - AUD-2026-09-164
  - AUD-2026-09-165
  - AUD-2026-09-166
  - AUD-2026-09-167
  - AUD-2026-09-168
  - AUD-2026-09-169
  - AUD-2026-09-170
  - AUD-2026-09-171
  - AUD-2026-09-174
  - AUD-2026-09-175
  - AUD-2026-09-176
  - AUD-2026-09-180
  - AUD-2026-09-181
  - AUD-2026-09-182
  - AUD-2026-09-184
  - AUD-2026-09-185
  - AUD-2026-09-186
  - AUD-2026-09-187
  - AUD-2026-09-188
  - AUD-2026-09-189
  - AUD-2026-09-190
  - AUD-2026-09-325
  - AUD-2026-09-326
  - AUD-2026-09-327
  - AUD-2026-09-328
---

# REVIEW_WP4 — adversarial second review of the WP-4 data-model findings

**Scope.** Independent, read-only falsification of the WP-4 register claims
(`docs/audit/2026-09/AUDIT_FINDINGS.md` §3/§5, detail in `AUDIT_DATA_MODEL.md`).
ID blocks 154–190 + 325–328. Branch `chore/audit-review-2026-09`, HEAD `10dc620f`
(merge-base mit der Audit-Basis `abd61aed`; die vier Commits darüber sind
docs-only — für `backend/**` ist HEAD inhaltsgleich mit `abd61aed`).

**Methodik.**
1. Jede zitierte `file:line` neu im Produktcode aufgeschlagen; kein
   `AUDIT_EVIDENCE/*` als Beweis.
2. Live-Gegenmessung gegen die laufende Postgres (nur `SELECT`), weil mehrere
   Kernzahlen (FK-Constraints, RLS, Zählungen) nur dort entscheidbar sind.
3. Verdikt nur `BESTAETIGT`, wenn Ort **und** Aussage stimmen. Fehlzitate werden
   auch dann notiert, wenn die Aussage im Kern überlebt.
4. Keine Phantom-Gegenbeweise: wo das laufende System keine Entscheidung
   erlaubt, steht `NICHT VERIFIKABAR` + fehlender Prüfschritt.

**Snapshots-Metrik-Hinweis (für alle DB-Zahlen).** Die laufende DB weicht in
Nebenzahlen vom Audit-Schnappschuss ab (live 3442 Artefakte vs. Audit „3062“,
42 vs. „44“ `workspace_id`-Tabellen). Die qualitativen Kernaussagen sind davon
unberührt; einzelne Prozent-/Nennerzahlen sind dagegen snappshot-gebunden.

---

## 2. Gegenbeweis-Tabelle (n=33)

| ID | Sev orig | Verdikt | Korr. Sev | Gegenbeweis (`file:line` + Zitat) |
|---|---|---|---|---|
| 154 | Medium | **BESTAETIGT** | Medium | `traceability/types.py:79` `VALID_LINK_TYPES: frozenset[str] = LinkType.values()`; `:75-78` Docstring „**No longer a validation authority**“; re-exportiert in `traceability/services.py:65` (Import) + `:472` (`__all__`); **benutzt** in `application/reqif_import_service.py:886` `if link_type not in VALID_LINK_TYPES:`. Alle drei Zitate existieren. |
| 156 | Low | **NICHT VERIFIKABAR** | Low | Zitierte Stelle `link_types/migrations/0008_…py:83` liegt in der **`unseed()`**-Rückwärtsfunktion (`WorkspaceLinkTypeDefinition.objects.filter(...).delete()`), enthält **keine** Zahl. Der Datei-Kopf `:5-8` sagt im Gegenteil: „This migration **re-runs** the same idempotent seed … for every tenant“. Die Behauptung „Datenmigration ohne Re-Run; 401 statt 402“ ist aus dem Zitat nicht ableitbar. *Fehlender Schritt:* die WP-4-Evidenz zur 401/402-Zählung. |
| 157 | Medium | **BESTAETIGT** | Medium | `traceability/trace_link_manager.py:372-374` `edges = TraceLink.objects.filter(link_type=link_type)…` + `:376-377` `if _dfs_has_cycle_to(target_id, source_id, adj): raise CycleDetectedError` — Zyklusprüfung **pro** `link_type`. Kein `source_id == target_id`-Guard im Create-Pfad; `pl_tracelink`-Constraints (live `pg_constraint`): nur `pk`, `uq_tracelink_edge UNIQUE (source_id,target_id,link_type)` + 5 FKs — **kein** `CHECK (source_id <> target_id)`. `validate_link_pair` (`link_types/catalog.py:98-152`) vergleicht nur Typen, nie Identität. Self-Link nirgends abgelehnt. |
| 158 | Info | **BESTAETIGT** (Kontrolle) | Info | Live `SELECT link_type,count(*) FROM pl_tracelink`: 7 distinkte Typen (`allocated-to`, `decomposes`, `derives-from`, `mitigates`, `references`, `verifies`, `decides`) ⇒ 11−7 = **4** ohne Link. Kontrolle hält. |
| 159 | Info | **BESTAETIGT** (Kontrolle) | Info | Live `lt_workspace_definition`: 11 distinkte `key` je Tenant; `traceability/types.py:29-67` Enum = 11; `lt_global_definition` = 44 = 11 Typen × 4 Tenants. Konsistent-offen bestätigt. |
| 160 | High | **BESTAETIGT** | High (als ADR-Anker) | `presets/registry.py:13` „This module is the Single Source of Truth for **all** preset rule data (ADR-04).“ Gegenbeweis der SSOT-Behauptung: `workflow/definition_store.py:714-733` `PRESET_SCHEMAS` (Graph hartkodiert), `:628` `SCHEMAS_WITHOUT_PROPOSED = frozenset({"minimal","interview_default"})`; `workflow/transition_validator.py:58` `_PRESET_TIERS = frozenset(...)`; `attribute_definitions/stage_matrix.py:64-68` `PRESET_STAGE`; `traceability/audit/registry.py:162-164` `RULE_PRESET_MAP`; `application/architecture_decompose_service.py:351` `if tier == "minimal"`; `presets/gate.py:536`. **≥6 unabhängige Module.** *Zahlkorrektur:* „7 datengetrieben / 5+ hartkodiert“ ist unscharf (Report-Tabelle listet 5 datengetrieben, 8 hartkodiert); „5+“ trägt, die exakte 12er-Summe nicht. |
| 161 | High | **TEILWEISE** | **High → Medium** | Seeding bestätigt: `stage_matrix.py:887` `entry["stage_mandatory"] = stage in raw["_mandatory_stages"]`, `:907/:921` Overrides. **Null Produktionskonsumenten:** `rg stage_mandatory_names backend` ⇒ nur Definition `:926` + `__all__` `:969`. **Aber** genau das ist im Modul explizit als bewusster, dokumentierter Aufschub festgeschrieben (`:41-45` „seeded and discoverable but **deliberately not yet consumed**“). Kein Defekt, sondern eine geplante Lücke ⇒ High überzogen. |
| 162 | High | **BESTAETIGT** | High | `presets/gate.py:536-549`: der **einzige** Downgrade-Inkompatibilitäts-Check läuft in `try:` (`BaselineSnapshot.unscoped.filter(workspace_id=…, scope="global").count()`), darunter `except Exception: pass` mit Kommentar „PersistenceLayer unavailable in test context; skip check.“ Fehler ⇒ Blocker wird stillschweigend übersprungen (fail-open). Zitat exakt. |
| 164 | Low | **BESTAETIGT** | Low | `stage_matrix.py:41-45` verweist auf die „WS7/AWMS value migration (**#940**)“, um `stage_mandatory` konsumierbar zu machen; Register führt #940 als geschlossen. Zitat vorhanden. *Einschränkung:* der Issue-Status selbst ist ohne GitHub offline nicht nachprüfbar. |
| 165 | Info | **TEILWEISE** (Kontrolle) | Info | Live `we_engine_definition`/`item_type='Requirement'`: `standard` 5 States/5 Transitions, `extended` 8/9 — die „5/9“ sind live. **`minimal` existiert live nicht** (`count(*)=0`; `pc_workspace_preset_config`: minimal 0, standard 311, extended 89). Die „1“ stammt aus dem Code (`definition_store.py:715-717` `["draft","done"]` + `_minimal_transitions()`), nicht aus einer Messung. Differenzierung im Kern bestätigt, Minimal-Zweig live ungetestet (deckt sich mit AUD-163). |
| 166 | Info | **BESTAETIGT** (WIDERLEGT bleibt) | Info | `workflow/services.py:306` `with transaction.atomic():` → `:308` `item_state = lifecycle.lock_item_state(...)` (`SELECT … FOR UPDATE`, `lifecycle_manager.py:278-282`) → `:318` Versionsprüfung → `:334-350` `validator.validate(req)` gegen `current_state = item_state.current_state` → `:362` `perform_transition(..., item_state=…)`. **Validierung läuft nach dem Lock** — CR-08-WIDERLEGUNG hält. |
| 167 | High | **BESTAETIGT** | High | `application/import_service.py:714-722` `WorkflowItemState.objects.create(item_id=obj.id, …, current_state=mapped_status, …)` — kein `perform_transition`, kein `WorkflowHistoryEntry`, kein `version`-Write. `mapped_status = _map_status(status_raw, valid_states)` (`:610`); `_map_status` (`reqif_import_service.py:202-228`) gibt einen beliebigen gültigen Zustand (z. B. `approved`) unverändert zurück. *Nuance:* Pfad ist die Erstanlage eines neuen Artefakts (kein Re-Transition), aber er kann einen Nicht-Initialzustand ohne Gate/History setzen. |
| 168 | High | **BESTAETIGT** | High | `application/reqif_import_service.py:789-793` `if state_row.current_state != mapped …: state_row.current_state = mapped; state_row.definition = definition; state_row.save(update_fields=["current_state","definition"])` — **kein** `version`-Bump (auch nicht in `update_fields`), obwohl `perform_transition` (`lifecycle_manager.py:378-384`) `version=F("version")+1` CAS-geschützt garantiert. CAS-Blindstelle bestätigt. |
| 169 | High | **BESTAETIGT** | High | GET-Pfad: `rest_api/interview_views.py:245-257` `@action(detail=True, methods=["get"], url_path="state")` → `_state_dict` → `InterviewService.get_state`. `interview_service.py:395` → `:269-293 _get_session` → `:274 self._lazily_abandon_if_stale(session, ctx)` → `:336-344 force_transition(...)` (Write in einem GET). `:354 except Exception:` fängt alles ab; `:367 session.status = "abandoned"` nur in-memory; `:368-369 session.version = F("version")+1; session.save(update_fields=["modified_at","version"])` — Version steigt ohne Stateänderung. Alle vier Teilaussagen bestätigt. |
| 170 | Medium | **BESTAETIGT** | Medium | `lifecycle_manager.py:416-477 force_transition(item_id, item_type, workspace_id, target_state, change_reason, actor)`: kein Rollen-Check, kein SignatureGate, kein erzwungener `change_reason`; direkter Write `:452-454 item_state.current_state = target_state; item_state.version += 1; save(...)`. Rollen-/Signatur-/Reason-Gate fehlt bestätigt. |
| 171 | Medium | **BESTAETIGT** | Medium | Live `pg_constraint` für `we_item_state`: nur `pk`, `uq_we_state_tenant_item UNIQUE (tenant_id,item_id,item_type)`, 3 FKs (`tenant`, `definition`, `created_by/modified_by`). **Kein** `workspace_id`-FK; **kein** `CHECK (current_state ∈ states(definition))`. Live `states_outside_def = 0` (die App-Normalisierung greift), der DB-Schutz fehlt. |
| 174 | Info | **BESTAETIGT** (Kontrolle) | Info | Live: `cross_tenant = 0`, `cross_ws = 0` über `pl_tracelink`×`pl_artifact`. Scope-Trennung tenant-seitig sauber. |
| 175 | Low | **BESTAETIGT** | Low | `presets/registry.py:129` `known_scopes = ("document", "project", "global")` — hartkodierte Tupel-Liste innerhalb `PresetConfig.is_scope_allowed`, neben den datengetriebenen `baseline_scopes` (`:166/:182/:214`). Zitat exakt. |
| 176 | Medium | **BESTAETIGT** | Medium | Dreifach-Sperre exakt: `bootstrap_attribute_definitions.py:309 RELABEL_KEYS = ("label","help_text")` (⇒ `kind` ∉ Relabel-Set); `:1248-1249 known = {a["name"] …}; additions = [... if a["name"] not in known]` (Diff-Key = `name`, nicht `kind`); `:1250-1251 if not additions: return False` (kein `save`, kein Bump). Alle drei Orte zitieren wie angegeben. |
| 180 | High | **TEILWEISE** | **High → Medium** | **Zähler 26 korrekt, Nenner und Flaggschiff-Beispiele falsch.** Live: 42 Tabellen mit `workspace_id`, davon **16 mit FK** (`pg_constraint`, Spalte `workspace_id → pl_workspace`), also **26 ohne** (deckt `we_item_state`, `we_history_entry`, `bl_baseline_snapshot`, `lt_workspace_definition`, `ad_workspace_definition`). **Aber:** `pl_artifact` **hat** den FK (`pl_artifact_workspace_id_b9c0a10b_fk_pl_workspace_id`; Modell `persistence/models.py:1212 workspace = models.ForeignKey(Workspace, …)`) und `pl_requirement` ebenso (`pl_requirement_workspace_id_e6e6905e_fk_pl_workspace_id`; `Requirement.workspace`-FK aus Migration 0055). Nenner live **42**, nicht 44. Die Formulierung „inkl. `pl_artifact`, `pl_requirement`“ ist **FALSCH**; die Prämisse „die DB schützt nichts“ wird dadurch entkräftet. |
| 181 | High | **BESTAETIGT** | High | Live: 99 Artefakte mit `artifact_type IN ('TestCase:Unit','TestCase:System')` (69 Unit + 30 System), davon **30 Quelle eines lebenden TraceLinks**. Migration `persistence/migrations/0093_…py:76-78` `Artifact.objects.filter(artifact_type__istartswith="TestCase:").update(artifact_type="TestCase")` (unbedingter Forward-Schritt). Der Docstring `:27-28` „no read path depends on the tag any more“ ist zu stark: `mcp_server/tools/tests.py:206` dokumentiert einen Fallback auf „the deprecated TestCase:<Type> artifact tag“; weitere Normalisierer `link_types/catalog.py:41`, `application/artifact_diff_service.py:300`. Kern bestätigt. |
| 182 | Low | **BESTAETIGT** | Low | Live `pg_constraint` `pl_tracelink`: nur `pk`, `uq_tracelink_edge`, 5 FKs. **Kein** `CHECK`/Enum an `link_type`; auch kein FK auf einen Katalog. Zitat (DB) exakt. |
| 184 | Medium | **TEILWEISE** | Medium | Live: `as_domain_event_outbox`, `as_domain_event_dlq`, `as_webhook_subscription`, `as_webhook_delivery_log` → `relrowsecurity = f` **und** Modell ohne `tenant_id` (`application/models.py:44,147,170,204`) ⇒ 4/5 bestätigt. **`bl_delta_index_entry` hat RLS** (`relrowsecurity = t`, Policy `bl_delta_index_entry_tenant_isolation`, transaktiv über `bl_baseline_snapshot.tenant_id`, Migration `baseline/migrations/0010_baseline_delta_index_entry_rls.py`) — sie hat nur keine `tenant_id`-Spalte. Die Formel „5 ohne tenant_id **und ohne RLS**“ ist damit falsch; korrekt: 5 ohne `tenant_id`, **4** davon ohne RLS. |
| 185 | Info | **BESTAETIGT** (Kontrolle) | Info | Live 29/31 `pl_*`-Tabellen mit RLS (Ausnahmen `pl_tenant`, `pl_user`). `rg "\.raw\(" backend --glob !tests --glob !migrations` ⇒ **0** Treffer (exit 1). Kontrolle hält. |
| 186 | Medium | **TEILWEISE** | Medium | `.unscoped`-Zahl exakt: `rg -o "\.unscoped" backend --glob !tests --glob !migrations \| Measure` ⇒ **263** (über alle Dateien inkl. Tests sind es 280). **Aber** „0 Constraints an 5 zentralen Tabellen“ trifft nicht zu: `pl_artifact` und `pl_requirement` **haben** einen `workspace_id`-FK (siehe 180). Korrekt wäre „0 Constraints an `we_item_state`/`we_history_entry`/`bl_baseline_snapshot`“. |
| 187 | Medium | **BESTAETIGT** | Medium | `attribute_definitions/schema.py:22-34 ITEM_TYPES` = **11**; `application/search_service.py:182-244 _TABLE_SPECS` = **10** (Requirement, ArchitectureElement, TestCase, StakeholderNeed, Adr, Risk, Issue, ChangeRequest, Goal, GlossaryTerm; `:246 _VALID_TYPES = set(_TABLE_SPECS)`); live `SELECT count(DISTINCT artifact_type) FROM pl_artifact` = **13** (zusätzlich `Icd`, `Diagram`, `Interview`, dazu die Tag-Rückstände). Drei parallele Registries 11/10/13 bestätigt. |
| 188 | Info | **BESTAETIGT** (mit Snapshot-Drift) | Info | Live 99 `TestCase:`-getaggte Artefakte. „3,2 %“ entspricht 99/3062; live sind es 3442 Artefakte ⇒ 2,9 %. Aussage (99 Tags, kleiner Anteil) hält; die Prozentzahl ist snappshot-gebunden. |
| 189 | Low | **BESTAETIGT** | Low | `frontend/src/utils/artifactRoutes.ts:17-44 ARTIFACT_ROUTE_MAP` enthält **keine** Keys `TestCase:Unit`/`TestCase:System`; `:50-52 getArtifactRoute` fällt auf `"/requirements"` zurück. Getaggte TestCases landen damit nicht auf `/testcases`. Zitat exakt (der Fallback ist im Code selbst dokumentiert). |
| 190 | Info | **NICHT VERIFIKABAR** | Info | `baseline/diff_engine.py` wurde nicht ausgeführt (kein Testlauf/Mutation) — Deklaration „BLOCKED, kein PASS“ ist korrekt und wird nicht aufgelöst. *Fehlender Schritt:* Diff-Engine mit definierten Baselines mutieren/prüfen. |
| 325 | High | **TEILWEISE** (Zahlkorrektur) | High | **Semantik bestätigt, Zählung falsch (3 → 4).** `traceability/audit/hierarchy.py:172-186`: `PARENT_TO_CHILD_LINK_TYPES = {decomposes}`, `CHILD_TO_PARENT_LINK_TYPES = {derives-from}` — `refines` fehlt; der Modul-Docstring `:34-38` „`refines` no longer exists as a link type“ ist **veraltet**, denn `link_types/builtin.py:140-164` führt `refines` als Built-in (seit #950, Requirement→Requirement). `baseline/services.py:430` SQL nur `tl.link_type = 'derives-from'` vs. Docstring `:324` „`derives-from`/`refines`“. `baseline/delta_index_builder.py:288` dito vs. Docstring `:262`. `frontend/src/utils/traceEndpoints.ts:72-75 HIERARCHY_LINK_TYPES = ["derives-from","decomposes"]`. Damit **4** Definitionen ohne `refines`, nicht 3 (Register/Report nennen „alle 3“, zitieren aber 4 Orte). |
| 326 | High | **BESTAETIGT** | High | `application/reqif_import_service.py:886-897`: `if link_type not in VALID_LINK_TYPES: raise _SoftError(...)` (globaler Enum) und danach direkt `TraceLink.objects.get_or_create(tenant=…, source=…, target=…, link_type=link_type)` — **kein** `link_types.catalog.validate_link_pair`, kein Workspace-Katalog. Umgehung bestätigt; `validate_link_pair` hat genau eine Produktionsaufrufstelle (`application/trace_link_service.py:365,388`). |
| 327 | High | **UEBERZOGEN** | **High → Medium** | Umgehung formal bestätigt: `icd/traceability_connector.py:82-87 create_trace_link(source_id=…, target_id=…, link_type="decomposes", …)`; in `traceability/trace_link_manager.py:334` läuft nur `_validate_link_type` (grober Enum-Check), nie `validate_link_pair`. **Aber** der hartkodierte Typ `decomposes` mit `allowed_pairs` `(ArchitectureElement, ArchitectureElement)` (`link_types/builtin.py:123-126`) ist für die beiden Endpunkte, die der Connector laut eigenem Docstring (`:11-22`, „Both endpoints are ArchitectureElements“) verknüpft, ein **legaler** Pair. Ein real ungültiger Pair ist nicht belegt ⇒ High nicht tragfähig. |
| 328 | Medium | **BESTAETIGT** | Medium | `traceability/services.py:227` Docstring „link_type not in **8** valid types“; `traceability/exceptions.py:18-23` „not in the **10** valid types … (parent-child, derives-from, satisfies, verifies, implements, refines, documents, realizes, traces, copy-of)“; `traceability/trace_link_manager.py:356` „the **8** relation types“. Tatsächlich **11** (`types.py:42-67`). Zahlen 8/10/11 im Code bestätigt. |

---

## 3. Register-Quercheck (§3/§5 gegen Report)

- Die WP-4-High-Zeilen in §3 (Register `:242-252`) und die §5-Volltexteinträge
  (`:1228-1380`) sind **reine Zeiger** auf `AUDIT_DATA_MODEL.md`; sie erfinden
  keine Zusatzaussage. Kein Widerspruch Report↔Register auf Substanzen.
- **Interner Zählfehler:** Überschrift/§5-Titel von `AUD-325` sagt „**allen 3**
  Hierarchie-Definitionen“, die „Ort (Reichweite)“-Zeile listet aber **4**
  (`hierarchy.py`, `baseline/services.py`, `delta_index_builder.py`,
  `traceEndpoints.ts`). Report §3.2-Zeile „3 Hierarchie-Listen“ zählt ebenso
  falsch. Korrekt: 3 Backend + 1 Frontend = 4.
- **Register-§3 vs. Report-Klassifikation:** `AUD-165/166/174/185` stehen in §3
  als `PASS → Kontrolle`; `AUD-166` als `WIDERLEGT`. Deckt sich mit dem Report
  (§6/§5). Keine Abweichung.
- **Register-§3-Zeile `AUD-154`** nennt `traceability/services.py:65,472` —
  beide Zeilen existieren (`:65` Import, `:472` `__all__`). Kein Fehlzitat.

---

## 4. Verdikt-Zählung (n=33)

| Verdikt | Anzahl | IDs |
|---|---:|---|
| **BESTAETIGT** | 24 | 154, 157, 158, 159, 160, 162, 164, 166, 167, 168, 169, 170, 171, 174, 175, 176, 181, 182, 185, 187, 188, 189, 326, 328 |
| **TEILWEISE** | 6 | 161, 165, 180, 184, 186, 325 |
| **UEBERZOGEN** | 1 | 327 (High→Medium) |
| **FALSCH** | 0 | — |
| **NICHT VERIFIKABAR** | 2 | 156, 190 |
| **KEIN REQOGNILOOM-BEZUG** | 0 | — |

**Schweregrad-Korrekturen:** `161 High→Medium`, `180 High→Medium`,
`327 High→Medium`. Alle übrigen Schweregrade bestätigt.
**Teil-Fehlzitate innerhalb BESTAETIGT:** keine.

**Kernbefunde-Check „4 State-Bypass-Pfade“:** `force_transition` (designiert,
170/BESTAETIGT), Interview-GET (`169`/BESTAETIGT), CSV-Import (`167`/
BESTAETIGT), ReqIF-Import (`168`/BESTAETIGT). Alle vier Pfade am Code
bestätigt; `176` (dreifach gesperrt) ebenfalls bestätigt.

**Kernbefund „Presets halb hartkodiert“:** `160`/BESTAETIGT, `162`/BESTAETIGT,
`175`/BESTAETIGT. Die SSOT-Docstring-Behauptung `registry.py:13` ist für die
fachlich gewichtigen Achsen tatsächlich nicht haltbar.

---

## 5. Key-Verdikte (die drei wichtigsten Korrekturen)

1. **AUD-180 — Flaggschiff-Beispiele sind falsch.** `pl_artifact` und
   `pl_requirement` **haben** einen `workspace_id`-FK auf `pl_workspace`
   (live `pg_constraint`; Modell `persistence/models.py:1212`). Der Rest-Zähler
   (26 Tabellen ohne FK) stimmt, aber die Prämisse „die DB schützt nichts“ und
   die Nennung genau dieser zwei Tabellen sind widerlegt. Nenner 44 → live 42.
2. **AUD-184 — „ohne RLS“ trifft nur 4 von 5.** `bl_delta_index_entry` hat RLS
   (`baseline/migrations/0010_…`, Policy über `bl_baseline_snapshot.tenant_id`).
   Die verbleibenden vier Outbox-/Webhook-Tabellen haben korrekt weder
   `tenant_id` noch RLS.
3. **AUD-325 — 4 statt 3 Definitionen; Docstring veraltet.** `refines` ist als
   Built-in re-introduziert (`builtin.py:140-164`) und fehlt in **vier**
   Hierarchie-Definitionen; `hierarchy.py:34-38` behauptet fälschlich, der Typ
   existiere nicht mehr.

Weitere belastbare High-Befunde: `168` (CAS-Blindstelle ohne `version`-Bump),
`169` (GET mutiert + `except Exception` + Version-Bump ohne Stateänderung),
`181` (99 Tag-Rückstände, 30 in lebenden Links), `326` (ReqIF umgeht Katalog).

---

## 6. NEU-AUDIT-LUECKE

1. **Messmethodik der DB-Integrität war unscharf.** Die Aussagen zu
   `workspace_id`-FK (180) und RLS (184) sind an genau den Stellen fehlerhaft,
   wo ein FK-Feld `workspace` heißt und die Spalte daher `workspace_id`
   (Django-Konvention), bzw. wo RLS transitiv über ein Parent-FK greift. Der
   Audit hätte FK-Constraints über `pg_constraint.conkey/confkey` auflösen
   müssen, nicht über Namensgleichheit der Spalte. Diese Klasse von Fehlzitat
   kann weitere WP-übergreifende „DB-schützt-nichts“-Aussagen betreffen.
2. **Snapshots nicht identifiziert.** 42 vs. 44 `workspace_id`-Tabellen und
   3442 vs. 3062 Artefakte zeigen, dass der Audit-Schnappschuss nicht dem
   laufenden Stand entspricht. Der Report sollte den Schema-/Datenstand
   (Migrations-Hash, `django_migrations`-Max) festhalten; Prozentzahlen wie
   AUD-188 („3,2 %“) sind dadurch nicht reproduzierbar.
3. **Semantik-Entscheidung `refines` fehlt.** `refines` ist live, hat aber 0
   Links und ist aus jeder Hierarchielogik ausgeschlossen; `Requirement.level`
   (ADR-005) und `document`-Baseline-Scope berücksichtigen es nicht. Der Audit
   behandelt „refines ist Hierarchiekante“ als gesetzt, ohne die
   Richtungs-/Stärke-Definition (`builtin.py:153-155`: schwächer als
   `derives-from`) gegen die Level-Ableitung abzuwägen. → Eigener
   Entscheidungsbedarf (ADR/Produkt), nicht nur „fehlt in 3 Listen“.
4. **Keine Live-Abdeckung des Minimal-Workflows.** 0 `minimal`-Workspaces
   (`pc_workspace_preset_config`) ⇒ die Kontrolle AUD-165 ist für den
   Minimal-Zweig nur code-abgeleitet; jeder minimale Pfad bleibt ungetestet
   (überschneidet AUD-163).
5. **Nicht untersuchte Nachbarschaft zu State-Bypass:** `force_transition`
   wird außer von `outdate()`/`reactivate()` auch vom Interview-Auto-Abandon
   (`169`) aufgerufen. Ob weitere Lese-/Nebenwirkungspfade denselben
   Escape-Hatch ohne Rollen-/Signatur-Gate nutzen, ist nicht inventarisiert.

---

*Read-only. Kein Produktcode, keine Migration, kein Push. DB ausschließlich
`SELECT`. `.kimi-code/` und `stack-seeds.md` unangetastet.*
