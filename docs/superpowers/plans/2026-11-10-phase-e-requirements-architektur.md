# Phase E — Requirements ↔ Architektur Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** #1669 und #1670 abschließen. Stufe 1 des Konzepts (Spezifikationsebene aus Allokation) ist gebaut und wird abgenommen. Neu gebaut werden der Naming-Layer, Stufe 2 (Allokation als Objekt mit Lebenszyklus), Stufe 3 (Release-Kaskade, Sperren, Change-Request-Pfad, Impact-Vorschau, Rigor-Kopplung) und der Rest von Stufe 4 (Ebene in Baselines gepinnt, Audit Live ↔ Baseline).

**Architecture:** `TraceLink(allocated-to)` bleibt die Kante im Graphen. Ein neues Objekt `Allocation` trägt zusätzlich Status und Freigabestand und wird mit der Kante synchron gehalten (Dual-Write plus Invariante), statt die Kante daraus abzuleiten. Das hält alle bestehenden Leser (Coverage, Baselines, Audit, MCP) lauffähig. Stufe 3 baut auf dem vorhandenen Workflow-Freeze (`application/artifact_freeze.py`, `state_meta.freeze_on_enter`) und `ArtifactVersion` (unveränderliche Inhaltsstände) auf. Die Rigor-Kopplung liest die Preset-Stufe über `presets/`.

**Tech Stack:** Django 6.1/DRF, PostgreSQL (RLS), `persistence.models`, `application/*_service.py`, `traceability/audit/hierarchy.py`, MCP-Tool `allocation.query`, React 19 (nur Task 6), pytest.

**Spec:** `docs/superpowers/plans/2026-11-10-backlog-roadmap.md` Phase E, Entscheidung 8 ("drei Stufen, MVP zuerst"). Konzept: Issue #1670 (Anhang), `docs/se/ADR/ADR-027_leaf_relative_requirement_tiers.md` (accepted 2026-11-05), `docs/se/ADR/ADR-005_requirement_level_abgeleitet.md`.

## Entscheidungen (Daniel, 2026-11-10)

| # | Entscheidung |
|---|---|
| D9 | Mehrfachallokation, **erweitert am 2026-11-10 (nach Review): per Konfiguration schaltbar.** Zwei Einstellungen je Workspace (Q1-Preferences, Änderungen auditiert): `allocation.cardinality` = `single` (Default, heutiges Verhalten, N:1 mit 409 bei zweiter Allokation, `AllocationConflictError`, `application/base.py:162`) oder `multiple`; `allocation.conflict_severity` = `info` \| `warning` (Default) \| `blocker`. Bei `multiple` gilt: keine Rechenregel (kein min/max), die Ebene bleibt `unresolved` (`multiple_allocations`), **es sei denn genau eine Kante ist als führend markiert** (`Allocation.is_primary`). Eine Mehrfachallokation ohne führende Kante meldet der Audit immer (Regel `allocation.multiple`, Schweregrad aus der Einstellung). Der Wechsel `multiple → single` ist gesperrt, solange Mehrfachallokationen existieren (409 mit Anzahl) |
| D10 | Freigabeeinheit: **beides.** Element-Release (kaskadiert) und optionaler Einzel-Release je Requirement. Vorrang: Element-Release umfasst seine Requirements; ein Einzel-Release ist der Spezialfall, der ohne Element-Release möglich bleibt. Eine Sperre kann nie durch den anderen Pfad umgangen werden |
| D12 | Inhalt der allozierten Requirements einfrieren: **abhängig vom Rigor-Grad.** Extended (hoch): Inhaltsversion eingefroren. Standard (mittel) und Minimal (niedrig): nur Struktur und Kanten |
| übrige | D1–D8, D11, D13–D17 wie im Konzept vorbelegt. D14 gilt durch ADR-027 als erledigt |

## Befund (origin/main f20f913e, Code seit 4f8aa29f unverändert)

| Konzeptteil | Stand | Beleg |
|---|---|---|
| Stufe 1: Ebene aus Allokation, Leiter je Workspace | **gebaut** | ADR-027; `application/tier_ladder_service.py` (`DEFAULT_TIERS`, `WorkspaceTier`), `application/tier_compute.recompute_workspace_tiers`, `Requirement.tier_key`, `level_source` (`derived_allocation`, `derived_hierarchy`, `derived_type`, `unresolved`, `manual`) |
| D13 `allocation_intent` | **gebaut** | `persistence/models.py:288` `AllocationIntent`, `Requirement.allocation_intent` |
| Filter und Allokationsliste | **gebaut** | `rest_api/views.py:1875` (`?allocated=`, `?level=`), `application/allocation_query_service.py`, `allocation_view_service.py`, MCP `allocation.query` |
| Vorschlag der Ebene | **gebaut** | `application/requirement_level_service.py` (#1289), `RequirementService.set_manual_level` |
| Baseline sichert `tier_key` | **gebaut** | `baseline/state_capture.py:242`, `baseline/restorable_fields.py:188` |
| Workflow-Freeze für Requirement/Element | **gebaut (nur Position)** | `application/artifact_freeze.py` `is_frozen` (kein Verschieben, Umhängen, Allokieren im Freeze-Zustand), `workflow/global_definition_store.py:474` |
| Unveränderlicher Inhaltsstand | **gebaut** | `persistence/models.py:1510` `ArtifactVersion` (append-only) |
| Naming-Layer (D2/D7/D8) | **offen** | Leitername je Workspace editierbar (`WorkspaceTier.name {de,en}`), aber keine relative Regel `System/Subsystem/Component`, kein Tenant-Default, kein eigener Tier `module` |
| Stufe 2: Allokation als Objekt (Status `draft/released/revoked`) | **offen** | nur `AllocationIntent`; `allocate()` ersetzt die Kante (`trace_link_service.py:1440-1500`) |
| Stufe 3: Element-Release-Kaskade, 409 mit CR-Verweis, Impact-Vorschau, Rigor-Kopplung | **offen** | `_assert_not_frozen` liefert 409 ohne CR-Verweis |
| Stufe 4: gepinnte Ebene je Release, Audit Live ↔ Baseline | **teilweise** | `tier_key` im Snapshot, kein Release-Pin, keine Abweichungsmeldung |
| Datenlage (aus #1669, 2026-11-02, QS) | 72 Elemente, 890 von 999 Requirements mit genau einer Allokation, 0 Mehrfachallokationen, 109 ohne |

## Global Constraints

- Branch von `origin/main` (Fetch nur mit `git fetch origin +refs/heads/main:refs/remotes/origin/main`). Git-Mutationen nur über den `git`-Agenten. Commits englisch, Conventional Commits, höchstens 72 Zeichen, Trailer `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>` und `Claude-Session: https://claude.ai/code/session_01JYx6yrB2hSodcXeSkA5mAq`.
- Neue tenant-scoped Tabellen brauchen eine RLS-Policy-Migration nach dem Muster von `0136_workspace_tier_rls_policy.py` (sonst scheitert `test_rls_coverage.py`). Migrationsnummer: die nächste freie zum Zeitpunkt der Umsetzung (heute 0139).
- Keine Verhaltensänderung ohne Rigor-Bezug: auf Minimal und Standard bleibt alles wie heute, solange kein Release-Pfad benutzt wird.
- Defaults rückwärtskompatibel: bestehende Allokationen bekommen Status `draft` oder, wenn das Requirement im Freeze-Zustand ist, `released`.
- Delta 0 Tools: kein neues MCP-Tool. `allocation.query` und bestehende Tools werden erweitert. `export_tool_manifest` neu ausführen, Drift-Gate grün halten (`mcp_server/tests/test_tool_manifest_drift.py`).
- Rigor ändert nur der Change Control Board (D17). Keine neue Einstellung, die ein Nutzer nebenbei umstellen kann.
- Backend-Tests lokal mit `DB_USER` auf dem Superuser. Volle Läufe sequentiell. Datenmigrationen immer mit Trockenlauf-Bericht.
- Schließen von Issues erst nach Freigabe durch Daniel.

## Review Focus

- Drift Kante ↔ Objekt: `TraceLink(allocated-to)` und `Allocation` laufen auseinander, etwa durch einen Pfad, der nur die Kante schreibt (`create_trace_link` direkt, Import, Baseline-Restore). Test: Task 4 prüft die Invariante "jede Kante hat genau ein Objekt und umgekehrt" über alle Schreibpfade und als Konsistenzprüfung.
- Backfill nicht idempotent: Zweiter Lauf erzeugt Dubletten. Test: Task 4, Migration zweimal ausführen, gleiche Zeilenzahl.
- Mehrfachallokation (D9): erzeugt still eine Ebene oder verletzt die Einstellung. Tests: Task 3, `single`: zweite Allokation über jeden Schreibpfad (`allocate(mode="add")`, generischer TraceLink, Import, Restore) ergibt 409 `AllocationConflictError`; `multiple`: zwei Kanten ohne führende Kante lassen die Ebene `unresolved`, der Audit meldet `allocation.multiple` mit dem eingestellten Schweregrad; mit genau einer führenden Kante wird die Ebene aus ihr abgeleitet; zwei führende Kanten werden abgelehnt; Wechsel `multiple → single` mit bestehenden Mehrfachallokationen ergibt 409.
- Release ohne Rechte oder mit Rechtsumgehung: Einzel-Release umgeht die Element-Sperre. Test: Task 5, ein Requirement unter einem freigegebenen Element lässt sich nicht einzeln umhängen oder editieren (409).
- Sperre mit falschem Fehlerbild: 200 oder 500 statt 409 mit CR-Verweis. Test: Task 5.
- Release-Kaskade sehr groß: ein Element mit tausenden Requirements. Test: Task 5 prüft eine Obergrenze der Datenbankabfragen (Stapelverarbeitung statt je Requirement).
- Baseline zeigt nach Reallokation den neuen Wert statt des damaligen. Test: Task 6.

---

### Task 1: Stufe 1 abnehmen, #1669 schließen

**Files:** keine Änderung. Belege und Tests lesen.

**Interfaces:** Produces: Abnahmeliste Stufe 1, Entwurf des Schließ-Kommentars für #1669.

- [ ] **Step 1: Akzeptanzkriterien Stufe 1 gegen Tests prüfen**

Kriterien aus #1670: (a) Alle Requirements haben `level_source`, kein stiller Fallback; (b) die Levelwechsel sind in einem ADR dokumentiert; (c) Baseline-Neuberechnung gelaufen.
Run: `cd backend && DB_USER=<Superuser> python -m pytest application/tests -k "tier or level_source or allocation" -q`
Expected: grün. Dazu `grep -n "unresolved" application/tier_compute.py` (kein Raten, `NULL`/`unresolved` als ehrlicher Rest) und ADR-027 §Entscheidung Rangfolge.

- [ ] **Step 2: Offene Punkte aus #1669 gegen den Stand prüfen**

#1669 nannte: keine Filter (gebaut, `?allocated=`, `?level=`), stille Ignoranz unbekannter Parameter (`reject_unknown_query_params`, `rest_api/views.py:1875` `extra=`), kein MCP-Allokationstool (`allocation.query` in `tool_registry.py:499`). Je Punkt Datei:Zeile festhalten.

- [ ] **Step 3: Schließen (nach Freigabe durch Daniel)**

```bash
gh issue close 1669 --reason completed --comment "Erledigt in beta.29 durch ADR-027 (leaf-relative Stufen aus der Allokation), WorkspaceTier-Leiter, level_source, allocation_intent, Filter ?allocated= und ?level= sowie MCP allocation.query. Die Fortführung (Allokation als Objekt, Release und Sperren, Naming-Layer) läuft in #1670, Plan: docs/superpowers/plans/2026-11-10-phase-e-requirements-architektur.md."
```

---

### Task 2: ADR-028 und Spec für Stufen 2 bis 4, Freigabe-Gate

**Files:**
- Create: `docs/se/ADR/ADR-028_allokation_als_objekt_und_release.md`
- Create: `docs/superpowers/specs/2026-11-10-allokation-objekt-release-design.md`

**Interfaces:** Consumes: Entscheidungen oben, Konzept #1670 §2–§8. Produces: freigegebene ADR/Spec. Tasks 4, 5 und 6 starten erst danach.

- [ ] **Step 1: ADR nach MADR-Minimalstandard schreiben**

Format laut `.claude/rules/se-cascade-adr-standard.md`: Frontmatter (`adr_id: ADR-028`, `status: proposed`, `deciders: [user]`, `affected_reqs: [REQ-L0-039, REQ-L0-019]`), Abschnitte Kontext, Alternativen (mindestens zwei, inklusive verworfener Rechenregel für D9 und Element-only-Release für D10), Entscheidung, Konsequenzen. Entscheidung enthält D9, D10 (beides, mit Vorrangregel), D12 (rigor-abhängig) wörtlich aus der Tabelle oben.

- [ ] **Step 2: Spec schreiben**

Pflichtabschnitte: Zustandsmodell `Allocation` (`draft → released → revoked`, Übergänge, wer darf), Freigabekaskade (Reihenfolge der Sperren, Obergrenze der Batchgröße), Rigor-Matrix (Zeilen: minimal/standard/extended, Spalten: Ordnung, Konflikt Allokation ↔ Container, Änderung nach Freigabe, Inhaltsfreeze) aus Konzept §1c mit D12, 409-Fehlerbild mit CR-Verweis, Impact-Vorschau-Antwort, Einzel-Release gegen Element-Release (Vorrang), Baseline-Pin (D11), Migrationsplan der 890 Kanten, Nicht-Ziele.

- [ ] **Step 3: Daniel reviewt**

Fünf-Zeilen-Zusammenfassung plus Link. Erst nach Freigabe: `status: accepted`, Tasks 4 bis 6 freigeben.

- [ ] **Step 4: Commit** (über `git`-Agent): `docs(adr): propose allocation object and release cascade`

---

### Task 3: Mehrfachallokation konfigurierbar (D9) und Naming-Layer (D2/D7/D8)

**Files:**
- Modify: `backend/traceability/audit/hierarchy.py` (Mehrfachallokation: `unresolved` mit Grund `multiple_allocations`, außer bei genau einer führenden Kante), `backend/application/tier_compute.py`
- Modify: `backend/application/preference_registry.py` (neue Q1-Schlüssel `allocation.cardinality` und `allocation.conflict_severity`, Muster `ui.ids.show_readable` in `application/display_preference_service.py:59`)
- Modify: `backend/application/trace_link_service.py:1440-1500` (`allocate`: neuer Parameter `mode: Literal["replace", "add"] = "replace"`)
- Create: `backend/application/allocation_settings.py`
- Create: `backend/application/tier_naming.py`
- Modify: `backend/application/tier_ladder_service.py` (Tier `module`)
- Modify: Audit-Regel für Konflikt (Fundstelle: Regelkatalog in `backend/traceability/audit/`, Muster der bestehenden Regeln übernehmen)
- Test: `backend/application/tests/test_tier_naming.py`, `backend/application/tests/test_multi_allocation_conflict.py`

**Interfaces:**
- Consumes: `WorkspaceTier` (`tier_key`, `position`, `name {de,en}`), `recompute_workspace_tiers`.
- Produces:
  - `tier_label(tier_key: str, *, depth: int, workspace_id: UUID, locale: str = "de") -> str` mit Regel `"System"` wenn Position 1, `"Component"` wenn letzte Position, sonst `"Subsystem"` (optional nummeriert). `module` ist eine eigene Position unterhalb `Component`. Auflösung `Workspace-Override > Tenant-Default > Regel`.
  - `allocation_cardinality(workspace_id: UUID) -> Literal["single", "multiple"]` (Default `single`) und `allocation_conflict_severity(workspace_id: UUID) -> Literal["info", "warning", "blocker"]` (Default `warning`) in `application/allocation_settings.py`, gelesen über Q1 (`resolve_for`, Ebenen workspace > system > Registry-Default).
  - `TraceLinkService.allocate(requirement_id, architecture_element_id, ctx, *, mode: Literal["replace", "add"] = "replace")`. `replace` verhält sich wie heute. `add` ist nur bei `cardinality=multiple` erlaubt, sonst `AllocationConflictError` (409).
  - Audit-Befund `allocation.multiple` (Requirement mit mehreren aktiven Allokationen und ohne führende Kante). Schweregrad `allocation_conflict_severity`. `blocker` blockiert nur die Freigabe, nie den Normalbetrieb.
  - Schutz beim Zurückschalten: Schreiben von `allocation.cardinality = single` ist mit 409 abzulehnen, solange Requirements mit mehr als einer aktiven Allokation existieren (Antwort nennt die Anzahl).

- [ ] **Step 1: Failing Tests**

```python
def test_single_mode_rejects_a_second_allocation_on_every_write_path(...): ...   # allocate(mode="add"), generischer TraceLink, Import, Restore -> 409
def test_multiple_mode_without_primary_leaves_level_unresolved(requirement, el_a, el_b, ws_multiple):
    allocate(requirement, el_a, mode="add"); allocate(requirement, el_b, mode="add")
    recompute_workspace_tiers(requirement.workspace_id)
    requirement.refresh_from_db()
    assert requirement.level_source == "unresolved" and requirement.tier_key is None
def test_multiple_mode_with_one_primary_derives_level_from_it(...): ...
def test_two_primary_allocations_are_rejected(...): ...
def test_conflict_severity_setting_drives_audit_severity(...): ...   # info / warning (Default) / blocker
def test_switching_to_single_is_blocked_while_multiples_exist(...): assert response.status_code == 409 and "2" in response.json()["error"]["message"]

def test_label_rule_is_relative_to_depth():
    assert tier_label("erste", depth=4, workspace_id=WS) == "System"
    assert tier_label("letzte", depth=4, workspace_id=WS) == "Component"
    assert tier_label("dazwischen", depth=4, workspace_id=WS) == "Subsystem"

def test_workspace_override_beats_tenant_default(...): ...
def test_module_tier_sits_below_component(...): ...
```
Run: `cd backend && python -m pytest application/tests/test_tier_naming.py application/tests/test_multi_allocation_conflict.py -q` — Expected: FAIL.

- [ ] **Step 2: Implementieren**

Mehrfachallokation: in der Ebenenableitung bei mehr als einer aktiven Allokation und ohne führende Kante `unresolved` mit Grund `multiple_allocations` setzen, nie rechnen. `tier_label` als reine Funktion über die Leiter. Tenant-Default und Workspace-Override über den bestehenden Preference-Mechanismus (Q1, `application/preference_*`); Schlüssel `ui.tier.naming`. `module` als zusätzlicher Leiterschlüssel unterhalb der Blattposition, mit Migration nur der Daten, die heute `module` heißen (7 von 72 Elementen laut #1670). Trockenlauf-Bericht der Zuordnung vor dem Schreiben.

- [ ] **Step 3: Tests grün, Lint, Migration prüfen**

Run: `cd backend && python -m pytest application/tests -k "tier or allocation or naming" -q && python manage.py makemigrations --check --dry-run`
Expected: PASS, keine ungewollte Migration.

- [ ] **Step 4: Commit** (über `git`-Agent): `feat(tiers): flag multi-allocation as conflict and add naming layer`

---

### Task 4: Stufe 2 — `Allocation` als Objekt

**Files:**
- Modify: `backend/persistence/models.py` (neues Modell `Allocation`)
- Create: `backend/persistence/migrations/<nächste>_allocation_object.py`, `<nächste+1>_allocation_object_rls_policy.py`, `<nächste+2>_allocation_backfill.py`
- Create: `backend/application/allocation_service.py`
- Modify: `backend/application/trace_link_service.py:1440-1500` (`allocate`, `deallocate`, `create_trace_link` für `allocated-to`), `backend/application/allocation_query_service.py`, `backend/application/allocation_view_service.py`
- Modify: `backend/rest_api/` (Ressource `allocations`), `backend/mcp_server/tools/cross_cutting.py` (`allocation.query` erweitern)
- Test: `backend/application/tests/test_allocation_object.py`, `backend/persistence/tests/test_allocation_backfill.py`, `backend/rest_api/tests/test_allocations_api.py`

**Interfaces:**
- Consumes: `TraceLink(link_type=ALLOCATED_TO)`, `Requirement`, `ArchitectureElement`, `ArtifactVersion` (`revision`).
- Produces:
  - `Allocation(TenantScopedModel)`: `workspace`, `requirement` (FK), `element` (FK), `trace_link` (OneToOne, nullable bis Backfill), `status` (`draft|released|revoked`), `released_at`, `released_by`, `released_revision` (PositiveInteger, Revision aus `ArtifactVersion`), `released_tier_key` (SlugField, null). `is_primary` (`BooleanField`, Default `False`). Constraints: höchstens eine **führende** aktive Zeile je `requirement` (partieller Unique-Index: `UniqueConstraint(fields=["requirement"], condition=Q(is_primary=True) & ~Q(status="revoked"))`); höchstens eine aktive Zeile je `requirement` im Modus `single` wird **im Service** erzwungen (`AllocationService`, `AllocationConflictError`), weil die Einstellung je Workspace gilt und kein Datenbank-Constraint sie kennt. Bei Backfill: im Modus `single` ist die einzige Zeile je Requirement automatisch `is_primary=True`. Die Coverage-Kennzahl `multiple` ist im Modus `single` nur für Altbestand ungleich 0.
  - `AllocationService.set_primary(allocation_id: UUID, ctx: AuthContext) -> Allocation` (setzt die Kante als führend, entfernt das Flag von der bisherigen; nur im Modus `multiple`),
  - `AllocationService.set_status(allocation_id: UUID, status: str, ctx: AuthContext) -> Allocation`, `AllocationService.coverage(workspace_id: UUID, ctx: AuthContext) -> dict` mit Schlüsseln `allocated`, `partial`, `multiple`, `orphaned`, `not_allocatable`.
  - REST: `GET /api/v1/allocations/?requirement=&element=&status=`, `GET /api/v1/allocations/coverage/`, `POST /api/v1/allocations/{id}/set-primary/`; `POST` zum Anlegen akzeptiert `mode` (`replace|add`). MCP: `allocation.query` um `status` und `coverage` erweitern; die vorhandene MCP-Allokation (Schreibweg über `TraceLinkService.allocate`) bekommt `mode` und `primary` als Parameter, kein neues Tool.

- [ ] **Step 1: Failing Tests**

```python
def test_allocate_creates_object_and_edge(requirement, element, ctx):
    link = TraceLinkService().allocate(requirement_id=requirement.id, architecture_element_id=element.id, ctx=ctx)
    alloc = Allocation.objects.get(requirement=requirement)
    assert alloc.status == "draft" and alloc.trace_link_id == link.id

def test_reallocate_revokes_old_and_creates_new(...): ...
def test_deallocate_revokes_object_and_removes_edge(...): ...
def test_invariant_every_edge_has_exactly_one_object(db_with_legacy_edges): assert allocation_invariant_violations() == []
def test_backfill_is_idempotent(db_with_890_edges): run(); n = Allocation.objects.count(); run(); assert Allocation.objects.count() == n
def test_coverage_counts_allocated_partial_multiple_orphaned(...): ...
def test_set_primary_moves_the_flag_and_requires_multiple_mode(...): ...
def test_rls_tenant_isolation(...): ...
```
Run: `cd backend && python -m pytest application/tests/test_allocation_object.py persistence/tests/test_allocation_backfill.py -q` — Expected: FAIL.

- [ ] **Step 2: Modell, Migrationen und RLS**

Modell mit den Feldern oben. RLS-Migration nach `0136`-Muster. Backfill-Migration: je `allocated-to`-Kante genau eine `Allocation(status=draft)`, für Requirements im Freeze-Zustand (`is_frozen`) `released`. Idempotent über `update_or_create` auf `trace_link`. Rückwärtsmigration löscht nur Zeilen ohne Release-Daten.

- [ ] **Step 3: Dual-Write**

`allocate` legt Objekt und Kante in derselben Transaktion an, die ersetzte Kante setzt ihr Objekt auf `revoked`. `deallocate` analog. Jeder andere Schreibpfad der Kante (Import, Baseline-Restore, `create_trace_link` mit `allocated-to`) ruft `AllocationService.sync_from_edge(trace_link)`. Zusätzlich eine Funktion `allocation_invariant_violations() -> list[dict]` und ein Management-Command `check_allocation_invariants` (liest nur).

- [ ] **Step 4: Service, REST, MCP**

`AllocationService` und die Ressource nach dem Muster von `AllocationQueryService`. `allocation.query` bekommt `status` und `coverage` als Parameter, kein neues Tool. Manifest exportieren: `python manage.py export_tool_manifest`.

- [ ] **Step 5: Tests grün, Drift-Gate, RLS-Abdeckung**

Run: `cd backend && python -m pytest application/tests/test_allocation_object.py persistence/tests/test_allocation_backfill.py rest_api/tests/test_allocations_api.py mcp_server/tests/test_tool_manifest_drift.py persistence/tests/test_rls_coverage.py -q`
Expected: PASS.

- [ ] **Step 6: Frontend: Coverage-Kennzahl**

Anzeige der Coverage (`allokiert / teilweise / mehrfach / verwaist`) in der Requirements-Liste und im Dashboard über `api/` und `queries/` nach dem Muster von `queries/metrics.ts` (Phase B1). i18n DE/EN, `data-testid` je Kennzahl, Tokens aus `styles/tokens.css`. Test: `cd frontend && npx vitest run src/components/<Bereich>`.

- [ ] **Step 7: Commit** (über `git`-Agent, ein PR je Teil): `feat(allocation): add Allocation object with status and coverage`

---

### Task 5: Stufe 3 — Release-Kaskade, Sperren, CR-Pfad (nach Freigabe aus Task 2)

**Files:**
- Create: `backend/application/allocation_release_service.py`
- Modify: `backend/application/artifact_freeze.py`, `backend/application/artifact_service.py:513`, `backend/application/trace_link_service.py:1502` (`_assert_not_frozen`), `backend/application/base.py` (Fehlerklasse mit CR-Verweis)
- Modify: REST-Ressourcen `elements` (Release, Impact) und `allocations`, MCP (Erweiterung bestehender Tools)
- Test: `backend/application/tests/test_allocation_release.py`, `backend/rest_api/tests/test_release_api.py`

**Interfaces:**
- Consumes: `Allocation` (Task 4), `is_frozen`, `ArtifactVersion.revision`, Preset-Stufe über `presets.registry.PresetConfigRegistry.get_preset_config(tier)`.
- Produces:
  - `AllocationReleaseService.release_element(element_id: UUID, ctx: AuthContext) -> ReleaseResult` (`ReleaseResult`: `allocations_released: int`, `requirements_frozen: int`, `tier_pinned: int`)
  - `AllocationReleaseService.release_requirement(requirement_id: UUID, ctx: AuthContext) -> ReleaseResult` (Einzel-Release, D10)
  - `AllocationReleaseService.impact(element_id: UUID, ctx: AuthContext) -> dict` mit `requirements`, `elements`, `baselines`, `level_changes`
  - Fehler `ReleaseLockedError(WorkflowFrozenError)` (Basis `application/base.py:145`) mit `error_code = "RELEASE_LOCKED"`, `http_status = 409` nach dem Muster von `AllocationConflictError` (`base.py:162`) und dem Feld `change_request_hint: str`. REST gibt es als Feld `change_request` zurück (Verweis, wie ein CR zu eröffnen ist).

- [ ] **Step 1: Failing Tests**

```python
def test_release_element_pins_tier_and_locks_edges(...): ...
def test_extended_freezes_requirement_content_standard_does_not(...):  # D12
def test_locked_change_returns_409_with_cr_hint(client, released_element):
    r = client.post(f"/api/v1/elements/{released_element.id}/move/", {...}); assert r.status_code == 409 and r.json()["change_request"]
def test_single_release_cannot_bypass_element_lock(...): ...   # D10
def test_release_impact_lists_requirements_elements_baselines(...): ...
def test_release_query_count_is_bounded(django_assert_max_num_queries, big_element): ...
def test_minimal_preset_allows_change_after_release_and_logs_it(...): ...
```
Run: `cd backend && python -m pytest application/tests/test_allocation_release.py rest_api/tests/test_release_api.py -q` — Expected: FAIL.

- [ ] **Step 2: Kaskade implementieren**

`release_element`: in einer Transaktion Allokationen des Elements und seiner Kinder auf `released` setzen, `released_revision` aus der aktuellen `ArtifactVersion.revision` des Requirements, `released_tier_key` aus `Requirement.tier_key` (D11). Nur wenn der Rigor `extended` ist, wird der Requirement-Inhalt gesperrt (`FIELD_FROZEN`-Mechanismus, wie bei Dokumenten, ADR-026 R4); bei `standard`/`minimal` nur Struktur und Kanten. Stapelverarbeitung per `bulk_update`.

- [ ] **Step 3: Sperren und Fehlerbild**

`is_frozen` und `_assert_not_frozen` erweitern: Änderung an einer freigegebenen Allokation oder an der Position eines freigegebenen Elements liefert `ReleaseLockedError`. Wirkung nach Rigor: `minimal` erlaubt die Änderung und protokolliert sie, `standard` erlaubt mit Warnung "CR empfohlen", `extended` blockt mit 409. Der Einzel-Release nutzt dieselbe Sperrprüfung.

- [ ] **Step 4: Impact-Vorschau, REST, MCP**

`impact()` liefert Anzahl und Listen; REST `GET /api/v1/elements/{id}/release-impact/`; bestehende MCP-Tools erweitern, kein neues Tool, Manifest exportieren.

- [ ] **Step 5: Tests grün, Drift-Gate**

Run: `cd backend && python -m pytest application/tests/test_allocation_release.py rest_api/tests/test_release_api.py mcp_server/tests/test_tool_manifest_drift.py -q`
Expected: PASS.

- [ ] **Step 6: Commit** (über `git`-Agent, mehrere PRs: Kaskade, Sperren, Impact): `feat(release): cascade element release with rigor-aware locks`

---

### Task 6: Stufe 4 — gepinnte Ebene in Baselines, Audit Live ↔ Baseline

**Files:**
- Modify: `backend/baseline/state_capture.py:242`, `backend/baseline/restorable_fields.py:188`, `backend/traceability/audit/` (neue Regel)
- Test: `backend/baseline/tests/test_baseline_pinned_tier.py`

**Interfaces:**
- Consumes: `Allocation.released_tier_key`, Baseline-Snapshot.
- Produces: Der Snapshot trägt `released_tier_key` je Requirement. Audit-Regel `baseline.tier_drift` meldet Abweichung zwischen gepinnter und live berechneter Ebene.

- [ ] **Step 1: Failing Tests**

```python
def test_baseline_shows_tier_at_release_after_reallocation(...):
    # Baseline erzeugen, Requirement umhängen (nur auf minimal/standard erlaubt), Baseline lesen:
    assert baseline_view(req).tier_key == "dazwischen"   # damals, nicht live
def test_audit_reports_drift_between_live_and_baseline(...): ...
```
Run: `cd backend && python -m pytest baseline/tests/test_baseline_pinned_tier.py -q` — Expected: FAIL.

- [ ] **Step 2: Implementieren und prüfen**

Snapshot um `released_tier_key` erweitern, Restore-Pfad (`restorable_fields.py`) nicht überschreiben lassen. Run: `cd backend && python -m pytest baseline/tests -q` — Expected: PASS, bestehende Baseline-Tests unverändert grün.

- [ ] **Step 3: Commit** (über `git`-Agent): `feat(baseline): pin released tier and report drift`

---

### Task 7: #1670 schließen

**Files:** keine.

**Interfaces:** Consumes: Tasks 3 bis 6 gemergt.

- [ ] **Step 1: Akzeptanzkriterien aus #1670 prüfen**

Stufe 1: erledigt (Task 1). Stufe 2: jede Kante hat einen Status, `GET /allocations/?requirement=` und `?element=` funktionieren, Coverage in REST, MCP und UI. Stufe 3: Release sperrt Hierarchie, Kanten, Inhaltsversionen (Extended); Änderungsversuch liefert 409 mit CR-Verweis; `release-impact` nennt Requirements, Elemente und Baselines. Stufe 4: Baseline zeigt die damals gültige Ebene, Audit meldet Abweichung.

- [ ] **Step 2: Schließen (nach Freigabe durch Daniel)**

```bash
gh issue close 1670 --reason completed --comment "<Tabelle: Stufe, Kriterium, PR-Nummer, Test>"
```

- [ ] **Step 3: Endstand prüfen**

Run: `gh issue view 1670 --json state --jq .state`
Expected: `CLOSED`.

---

## Self-Review

- **Abdeckung:** Naming-Layer (D2/D7/D8) und D9 in Task 3, Stufe 2 in Task 4, Stufe 3 mit D10/D12 in Task 5, Stufe 4 in Task 6. #1669 Task 1, #1670 Task 7. Stufe 1 ist abgenommen, nicht neu gebaut.
- **Erweiterung 2026-11-10:** D9 ist jetzt per Konfiguration schaltbar (Kardinalität und Warnstufe, Default `single` und `warning`), mit führender Kante `is_primary`. Das berührt Task 3 (Einstellungen, `allocate(mode=...)`, Audit), Task 4 (Modell, Service, REST/MCP) und gehört in ADR-028.
- **Bewusste Grenze:** Tasks 4 bis 6 starten erst nach der Freigabe von ADR-028 und Spec (Task 2). D10 "beides" ist vom Konzept abweichend und verlangt eine ausdrückliche Vorrangregel. Sie steht in der Entscheidungstabelle und wird in der Spec festgeschrieben.
- **Risiko aus D10 "beides":** Zwei Freigabepfade bedeuten zwei Sperrlogiken. Die Review-Focus-Zeile "Einzel-Release umgeht die Element-Sperre" und der Test in Task 5 decken das. Die Spec muss prüfen, ob ein gemeinsamer Sperr-Check genügt.
- **Typkonsistenz:** `Allocation.released_tier_key` (Task 4) wird in Task 6 gelesen. `ReleaseLockedError` (Task 5) erweitert `WorkflowFrozenError` (`application/base.py:145`, im Review bestätigt) und trägt `http_status = 409` wie `AllocationConflictError`.
- **Nicht ausgeführt:** Kein Befehl dieses Plans lief. Fundstellen für Audit-Regelkatalog und REST-Ressourcen (`elements`, `allocations`) sind aus der Lektüre abgeleitet und in den Steps zu bestätigen. Die Datenzahlen (890/999) stammen aus der QS-Messung des Issues vom 2026-11-02.
