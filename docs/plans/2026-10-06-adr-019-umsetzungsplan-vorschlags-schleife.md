# Umsetzungsplan ADR-019 — Generischer Vorschlags-Lebenszyklus (MVP `trace_link`)

> **Reiner Umsetzungsplan. Kein Code, keine Migration, keine Config-Änderung.**
> Dieses Dokument ordnet ausschließlich die in [ADR-019](../se/ADR/ADR-019_generischer_vorschlag_lebenszyklus.md)
> getroffenen Entscheidungen in Arbeitspakete, Dateien und eine Reihenfolge — es entscheidet
> **keine** offenen Punkte neu.

| Feld | Wert |
|---|---|
| **Status** | Entwurf — pausiert bis ADR-019 `proposed → accepted` |
| **Datum** | 2026-10-06 |
| **Bezug** | [ADR-019](../se/ADR/ADR-019_generischer_vorschlag_lebenszyklus.md) · #1155 (Aspekt 2 „Vorschlags-Schleife") · #1156 („Zuhören & Antizipieren") · #856 (nur Design) · #121 (`suggest_links` ohne Accept-Schritt) · #1089 (AI-Proposal-Authoring + Pending-Review-Queue) |
| **Grundlage** | ADR-019 (Status `proposed`, entscheidungsreif; Review-Trail `RVW-2026-10-06-001…003`, Iteration 3 APPROVED); Arbeitseinheit **AP-B5.4** in [`2026-10-05-bugfix-hub-integrationen.md`](2026-10-05-bugfix-hub-integrationen.md) §3.6 |
| **Geltung / Scope** | Backend-MVP: **genau ein Produzent** (`TraceabilitySuggestService.suggest_links` → M2-Proposal-TraceLink; Accept = `confirm_proposed_link`), neue mandanten-gescopte `Suggestion`-Entität, Per-Kind-Adapter-Registry, MCP-Tool-Gruppe + REST-Endpunkte + Manifest |
| **Nicht-Teil** | UI-Vorschlags-Inbox (eigener, nachgelagerter Schritt WP6, s. O6) · weitere Produzenten `AiDerivationService` / `ArchitectureDecomposeService` / `AuditService.propose_remediation` (O1) · Migration/Deprecation von `TraceLink.proposed_by`/`proposed_at` (O4) · Retention/GC (O9) · Human-Bearer-REST-Trigger der Produktion (explizit out of MVP, ADR-019 Decision 3/4, 001-09) · Generic-Artifact-Umstellung der Entität (O8) |

---

## 0. Ziel & Scope / Nicht-Ziele

**Ziel (MVP):** Dem bisher **transienten** Vorschlag von `TraceabilitySuggestService.suggest_links`
(#121) einen dauerhaften, mandanten-sicheren **Warteplatz** geben und einen **einheitlichen
Accept/Reject-Pfad** bereitstellen, ohne die vier bestehenden Mechanismen M1–M4 umzubauen. Der
`trace_link`-Adapter **produziert beim Vorschlagen einen echten M2-Proposal-TraceLink**
(`TraceLinkService.create_trace_link`, Stempel `backend/application/trace_link_service.py:601-617`)
und **bestätigt beim Accept** über `confirm_proposed_link` (`:637-676`); Reject nutzt
`discard_proposed_link` (`:678-728`). Die `Suggestion`-Zeile ist **durable Quittung + Inbox +
Provenienz** darüber.

**Scope-Klarstellungen (aus ADR-019):**

- **MVP = ein Produzent** (`traceability.suggest_links`), nicht die volle M1–M4-Breite (Decision 4).
- **Produktion nur in Agent-/API-Key-Kontext.** Der Human-Bearer-REST-Trigger
  (`backend/rest_api/traceability_suggest_views.py:80-82`, `actor_type="user"`, kein `api_key_id`)
  ist **out of MVP scope** und wird **fail-closed** abgewiesen (`ProducerContextRequiredError` → 409),
  statt einen ungestempelten Link anzulegen (ADR-019 Decision 3, 001-09, Zusage 7(f)).
- **Accept delegiert immer** an den bestehenden Domain-Pfad (`connect` → Policy/Workflow/RBAC/Audit);
  **keine** neue State-Machine, **kein** Policy-Bypass, **kein** Blind-Merge des `payload` (Zusage 7(b)).
- **Der Agent-Guard bleibt fail-closed und greift je Adapter** (M1 Rule 0; `trace_link` über
  `AgentSelfConfirmError` in `confirm_proposed_link`/`discard_proposed_link`).

**Nicht-Ziele (MVP):**

- Keine Änderung an M1–M4 (Decision 2 „Komposition, keine Ablösung").
- Keine zweite Vorschlags-Wahrheit neben `ReviewQueueService` (Decision 5, #1089) und neben
  `ai_proposal_service.resolve_proposal_authoring` (Decision 5).
- **UI ist kein Bestandteil des Backend-MVP.** Die Vorschlags-Inbox (WP6) ist ein **eigener,
  nachgelagerter Schritt** (O6) — ohne sie erfüllt die Entität allein das DoD von #1155/#1156 nicht.

---

## 1. Vorbedingungen / Entscheidungen

**Harte Vorbedingung:** ADR-019 steht auf `proposed`. Die Umsetzung startet **erst** nach
`proposed → accepted` durch den User (Iteration 3 liegt mit Verdict APPROVED vor, `RVW-2026-10-06-003`).
Bis dahin gilt das **STOP-Gate** (ADR-019 §Offene Punkte): kein Modell, keine Migration, kein Tool.

**Offene Punkte O1–O11 — geordnet, mit aus dem ADR ableitbarer Empfehlung und Default.**
Spalte „Status" unterscheidet: **ADR-entschieden** (Empfehlung aus Decision) · **ADR-Default**
(im ADR als MVP-Default benannt) · **offen** (weiterer Produkt-Input nötig, hier nur einsortiert).

| # | Frage | Empfehlung / Default (aus ADR-019) | Status |
|---|---|---|---|
| **O1** | MVP-Produzenten-Scope | Genau **ein** Produzent: `TraceabilitySuggestService.suggest_links` | ADR-entschieden (Decision 4) |
| **O2** | Langfrist-Rolle von `Suggestion` | Dauerhaft **Kompositions-/Quittungsschicht**; Zustands-Hoheit bleibt bei M1–M4 | ADR-entschieden (Option A / Decision 2) |
| **O3** | `minimal`/`interview_default`-Semantik | Vorschlags-Schleife über die `Suggestion`-Zeile **erlauben**; der Adapter ruft den Create-Pfad mit User-Kontext, **ohne** `proposed` zu injizieren | ADR-Default (Decision 3) |
| **O4** | `TraceLink.proposed_by`/`proposed_at` | Im MVP **als M2-Feld belassen**; Migration/Deprecation in `Suggestion` ist eine eigene, spätere Entscheidung | offen (nicht MVP) |
| **O5** | MCP-Surface | Neues Präfix **`suggestion`** (`list`/`accept`/`reject`) + Manifest-Regeneration (223 → 226 Tools) | ADR-Default (Decision 6; Alternative „Fold in `review`" bleibt zulässig) |
| **O6** | UI-Inbox | **Eintrag in die bestehende Review-/Pending-Ansicht** (`ReviewsView` „proposals"-Modus) statt eigene Seite | ADR-Default (Entscheidung bei WP6) |
| **O7** | Idempotenz/Dedup (Suggestion **und** Kante) | **Kanten-Dedup:** Lookup vor `create`; existiert ein Proposal-Link auf derselben Kante (`uq_tracelink_edge`, `persistence/models.py:2037`; Mapping `trace_link_service.py:573-578`), wird die neue `Suggestion` an diesen gehängt. Suggestion-Dedup über Läufe bleibt vertagt | ADR-Default (001-10) |
| **O8** | Entitätstyp | Im MVP **eigene Tabelle**; Generic-Artifact später möglich | offen (MVP-Annahme: eigene Tabelle) |
| **O9** | Retention/GC | **Kein automatisches Löschen im MVP**; Aufbewahrungs-/Löschregel für `rejected`/`superseded` als eigener Folgepunkt | offen |
| **O10** | M2-Proposal vs. Suggestion-only | **M2-Proposal:** Produzieren = Create, Accept = Confirm (der schlankere „Accept = Create ohne M2"-Weg bleibt vertagt) | ADR-entschieden (Decision 3) |
| **O11** | Atomarität Proposal-Link ↔ Suggestion-Quittung | **Eine Transaktion** (`create_trace_link` + `Suggestion`-Insert) bzw. `Suggestion` zuerst; verwaiste Proposals zusätzlich in die Inbox aufnehmen | offen (bei WP2 umzusetzen) |

> **Nicht neu entschieden:** Diese Tabelle überträgt/ordnet nur den ADR-Stand. Die `offen`
> markierten Punkte (O4, O8, O9, O11) bleiben Produkt-/Implementierungs-Entscheidungen und
> werden in §8 erneut als Entscheidungsbedarf geführt.

---

## 2. Zielarchitektur (Kurz)

**`Suggestion`-Entität** (`backend/persistence/models.py`, Layer 0):

- Basis: `TenantScopedModel` (erbt bereits `AuditableModel` — `persistence/models.py:379-474`).
- Felder (Vorschlag, nicht abschließend): `kind` (`artifact_create | trace_link | interview_grounding | context_edge`),
  `status` (`open | accepted | rejected | superseded`), `producer` (Service-/Agent-Label),
  `proposed_by`, `proposed_at`, `decided_by`, `decided_at`, `target_item_type`, `target_item_id`
  (nullable), `payload` (JSON), Workspace-Scope.
- **RLS Pflicht:** `ENABLE` + `FORCE ROW LEVEL SECURITY` + tenant_isolation-Policy nach Muster
  `persistence/migrations/0097_uid_sequence_rls_policy.py` (bzw. `0067_rls_remaining_pl_tables.py`);
  das CI-Gate `persistence/tests/test_rls_coverage.py` erfasst die neue Tabelle automatisch (sonst rot).
- **Audit:** über `AuditableModel`-Felder + `audit.models.AuditEntry` (bzw. `write_mcp_audit` auf dem
  MCP-Pfad), konsistent mit den übrigen Tenant-Tabellen.

**Per-Kind-Adapter-Registry** (`kind` → Adapter) — Vertrag je Vorschlagsart:

| `kind` | Produzieren | Accept | Status im MVP |
|---|---|---|---|
| `trace_link` | `TraceLinkService.create_trace_link` (M2-Proposal-Stempel) | `TraceLinkService.confirm_proposed_link` | **MVP** (einziger) |
| `artifact_create` | M1-Create (`proposed`-Pfad) | M1-`confirm` (`proposed → states[0]`); ohne `proposed` (`minimal`/`interview_default`) `Suggestion`-Zeile selbst als Gate, Create mit User-Kontext | registriert, dormant |
| `interview_grounding` | M3 (`grounding_snapshot["pending_proposal"]`) | `formalize(confirmed_proposal=…)` | registriert, dormant |
| `context_edge` | M4 (`ContextEdge.origin="llm-suggested"`) | **neuer, kleiner** Origin-Adapter (kein bestehender Accept-Pfad) | registriert, dormant |

**Invarianten (ADR-019 Zusage 7):** `payload` ist **untrusted** — Accept validiert ausschließlich
über den delegierten Pfad (`_check_link_pair` `trace_link_service.py:537-544`, Link-Catalog,
Cross-Tenant-/Cycle-Prüfung), der `payload` liefert nur Kandidaten-IDs, **nie** Entscheidungen.
Provenienz (`producer`, `proposed_by`, `proposed_at`, `decided_by`, `decided_at`) ist
**server-gesetzt** aus dem authentifizierten Principal / der `ApiKey`-Zeile, **nie** aus dem
Request-Body. `ProducerContextRequiredError` (→ 409) fail-closed für Nicht-Produzenten-Kontexte.

---

## 3. Arbeitspakete WP1 … WP7

> Aufwandsangaben sind **qualitativ** (klein/mittel/groß) und ausdrücklich
> „von `effort-estimator` zu schärfen" — keine erfundenen Zahlen.

### WP1 — `Suggestion`-Entität + Migration + RLS/Audit

- **Ziel:** Neue mandanten-gescopte Tabelle mit Pflicht-RLS und CI-Coverage.
- **Files (Modify/Create):**
  - Modify: `backend/persistence/models.py` (neue Klasse `Suggestion(TenantScopedModel)`, Felder s. §2)
  - Create: `backend/persistence/migrations/0100_suggestion.py` (Modell; nächste freie Nummer nach `0099_testcase_origin_reviewed_scenario_kind.py`)
  - Create: `backend/persistence/migrations/0101_suggestion_rls_policy.py` (ENABLE+FORCE+Policy; Muster `0097_uid_sequence_rls_policy.py` / `0067_rls_remaining_pl_tables.py`)
  - Verify (kein Edit nötig): `backend/persistence/tests/test_rls_coverage.py` (erfasst `TenantScopedModel`-Subklassen automatisch)
- **Änderungen:** Entität + zwei Migrationen; `db_table`-Name konsistent zum Angular-`%(class)s`-Muster.
- **Tests:** `test_rls_coverage.py` grün (statisch + `@_pg_only`); Migration up/down sauber.
- **Aufwand:** mittel.
- **Abhängigkeit:** ADR-019 `accepted`.
- **DoD:** Migration anwendbar; `Suggestion` ist `TenantScopedModel`; RLS-Coverage grün; kein Cross-Tenant-Lesezugriff ohne Tenant-Kontext.

### WP2 — Service + Adapter-Registry

- **Ziel:** Layer-2-Fassade (`application/`) mit Registry, Accept/Reject-Delegation, Idempotenz,
  Provenienz-Setzung und Fehler-Taxonomie.
- **Files (Create/Modify):**
  - Create: `backend/application/suggestion_service.py` (Facade `SuggestionService`: `list_open`, `accept`, `reject`; `_set_tenant_context` via `ServiceBase`)
  - Create/enhalten: Adapter-Registry (z. B. `backend/application/suggestion_adapters.py`; vier Adapter `artifact_create`/`trace_link`/`interview_grounding`/`context_edge`)
  - Create: `ProducerContextRequiredError` (in `application/base.py` bzw. im Service) + `AgentSelfConfirmError`-Handling (aus `trace_link_service`)
  - Modify (nur falls nötig): `backend/application/trace_link_service.py` (dedup-Lookup-Helfer, sofern nicht im Adapter)
- **Änderungen:** Accept ruft **immer** den bestehenden Domain-Pfad und quittiert danach
  (`status=accepted`, `decided_by`/`decided_at`); Reject setzt `status=rejected` und **zerstört kein
  Ziel-Artefakt** (Zusage 7(e)); IDempotenz/Dedup nach O7; Atomarität nach O11.
- **Tests:** Unit-Tests je Adapter; Agent-Accept auf eigenen Vorschlag schlägt fehl (403/Validation, Zusage 7(c)); Fail-closed bei Nicht-Produzenten-Kontext (Zusage 7(f)).
- **Aufwand:** groß (Kernstück).
- **Abhängigkeit:** WP1.
- **DoD:** Accept/Reject delegieren nachweislich ohne neue State-Logik; Provenienz server-gesetzt; `payload` wird nie blind materialisiert.

### WP3 — MCP-Tool-Gruppe `suggestion` (list/accept/reject) + Manifest

- **Ziel:** Agenten-/Client-Surface mit Read/Write-Gate und regeneriertem kanonischem Manifest.
- **Files (Create/Modify):**
  - Create: `backend/mcp_server/tools/suggestion.py` (`SuggestionToolGroup`: `suggestion.list`, `suggestion.accept`, `suggestion.reject`)
  - Modify: `backend/mcp_server/tool_registry.py` (Import + `register_groups({... "suggestion": …})` im Block um `:953`; `suggestion.list` in `_READ_ONLY_TOOL_NAMES` `:410`; accept/reject bleiben fail-closed write-gated via `_is_write_tool` `:1468`)
  - Modify: `docs/agent-templates/tool-manifest.json` (Regeneration via `manage.py export_tool_manifest`; 223 → 226 Tools, Präfixe 35 → 36)
  - Verify: `backend/mcp_server/tests/test_tool_manifest_drift.py` (Drift-Gate grün)
  - Create: `backend/mcp_server/tests/test_suggestion_tool_group.py`
- **Änderungen:** 3 Tools; `suggestion.list` read-exempt, `accept`/`reject` write; Audit via `write_mcp_audit`; Agent-Guard-Mapping (`AgentSelfConfirmError` → Fehlercode); `ProducerContextRequiredError` → 409-Analogon.
- **Tests:** Tool-Schemas registriert; `_is_write_tool`-Klassifikation gepinnt; Manifest-Drift grün.
- **Aufwand:** klein–mittel.
- **Abhängigkeit:** WP2.
- **DoD:** `tools/list` zeigt `suggestion.*`; Manifest regeneriert; `test_tool_manifest_drift.py` grün.

### WP4 — REST-Endpunkte

- **Ziel:** REST-Parität (ADR-01: dünner Adapter → `application/`), RBAC + Fehler-Taxonomie.
- **Files (Create/Modify):**
  - Create: `backend/rest_api/suggestion_views.py` (`GET /api/v1/suggestions/`, `POST /api/v1/suggestions/{id}/accept/`, `POST /api/v1/suggestions/{id}/reject/`)
  - Modify: `backend/rest_api/urls.py` (Registrierung im Umfeld der Review-Routen `:958-972`; RBAC via `RbacPermission` `rest_api/auth_enforcer.py:60`)
  - Create: `backend/rest_api/tests/test_suggestion_views.py`
- **Änderungen:** List + Accept/Reject; Fehler-Mapping `003-01` in der REST-Fehler-Taxonomie verankern
  (`ProducerContextRequiredError` → **409 Conflict**, `AgentSelfConfirmError` → **403**); Audit.
- **Tests:** Endpunkt-Contract; Tenant-Fence (Fremd-Workspace), RBAC-Gate, Agent-Selbst-Accept → 403, Produzenten-Kontext-Verstoß → 409.
- **Aufwand:** mittel.
- **Abhängigkeit:** WP2.
- **DoD:** REST- und MCP-Fehler-Taxonomie stimmen überein (`003-01`); kein Cross-Tenant-Leak; RBAC erzwungen.

### WP5 — Produzent `suggest_links` verdrahten

- **Ziel:** Der MVP-Produzent persistiert den Vorschlag (M2-Proposal) + `Suggestion`-Zeile.
- **Files (Modify/Create):**
  - Modify: `backend/application/traceability_suggest_service.py` (`suggest_links`, `:237-338`) — Top-ranked Kandidat → `trace_link`-Adapter (Create + Suggestion)
  - Modify: `backend/mcp_server/tools/cross_cutting.py` (`traceability.suggest_links` `:941-943`) — Produzenten-Kontext (Agent + `api_key_id`) durchreichen
  - Verify/kein Proposal: `backend/rest_api/traceability_suggest_views.py` bleibt **advisory/lesend**; human-getriggerter Lauf fail-closed (`ProducerContextRequiredError` → 409)
- **Änderungen:** Kanten-Dedup (O7) vor `create`; `link_type` aus `payload.rule_id` ableiten
  (TRACE-P1/P1b → `derives-from`, TRACE-P2 → `allocated-to`); vollständige Rangliste bleibt in
  `Suggestion.payload`; Atomarität (O11).
- **Tests:** Pro Produzentenlauf genau **eine** `open`-Suggestion mit vollständiger Provenienz
  (Zusage 7(a)); wiederholter Lauf dedupliziert auf Kantenebene statt hart an `uq_tracelink_edge` zu
  scheitern; Nicht-Produzent-Kontext → `ProducerContextRequiredError` (Zusage 7(f)).
- **Aufwand:** mittel.
- **Abhängigkeit:** WP2 (+ WP1).
- **DoD:** `traceability.suggest_links` erzeugt einen bestätigbaren Proposal-TraceLink + `open`-Suggestion; der bestehende M2-Accept (`confirm_proposed_link`) greift real.

### WP6 — UI-Vorschlags-Inbox (eigener, **nachgelagerter** Schritt)

- **Ziel:** Persistierte Vorschläge werden für den Menschen sichtbar und annehmbar/ablehnbar —
  **ohne** die Entität allein als DoD-Erfüllung zu werten.
- **Files (Create/Modify):**
  - Modify: `frontend/src/components/Reviews/ReviewsView.tsx` („proposals"-Modus, `reviewsResolver.ts`, `useReviewsData.ts` — Wiederverwendung der bestehenden Pending-/Proposal-Ansicht, O6)
  - Create: `frontend/src/api/suggestions.ts` (Typen + `list`/`accept`/`reject`)
  - Modify: `frontend/src/i18n/locales/de.json` **und** `en.json` (Parität, strukturell gleiche Schlüssel)
  - Create: `frontend/src/components/Reviews/*.test.tsx` bzw. `Suggestions/*`-Tests; `data-testid` auf allen interaktiven Elementen (E2E-Pflicht)
- **Änderungen:** Provenienz-Anzeige („Vorschlag von …"), Annehmen/Ablehnen mit Bestätigung.
- **Tests:** Komponenten-Tests; i18n-Parität (`src/test/i18n-parity.test.ts`); optionaler Playwright-Smoke.
- **Aufwand:** mittel.
- **Abhängigkeit:** WP4 (REST), O6; **ausdrücklich nachgelagert** zum Backend-MVP.
- **DoD:** Vorschläge sichtbar/entscheidbar mit Provenienz; DE/EN-Parität; `data-testid` vorhanden.

### WP7 — Tests / Verifikation (querschnittlich)

- **Ziel:** Die testbaren Kern-Zusagen (ADR-019 Zusage 7(a)–(f)) sind belegt.
- **Files (Create/Verify):**
  - Create: `backend/application/tests/test_suggestion_service.py`, `backend/rest_api/tests/test_suggestion_views.py`, `backend/mcp_server/tests/test_suggestion_tool_group.py`
  - Verify: `backend/persistence/tests/test_rls_coverage.py`, `backend/mcp_server/tests/test_tool_manifest_drift.py`
  - Create/Verify (Frontend): `frontend/src/components/Reviews/*.test.tsx`, `frontend/src/test/i18n-parity.test.ts`
- **Tests:** RLS-Coverage; Manifest-Drift; Tenant-Isolation beim Accept; Agent-Guard fail-closed; Idempotenz/Kanten-Dedup; Payload-/Provenienz-Trust (Server-Setzung).
- **Aufwand:** mittel.
- **Abhängigkeit:** begleitend zu WP1–WP4; Abschluss nach WP5 (und WP6 für UI).
- **DoD:** Alle Zusagen 7(a)–(f) grün; keine Regression an M1–M4.

---

## 4. Reihenfolge / Wellen + Abhängigkeiten

| Welle | Inhalt | Typ | Abhängigkeit |
|---|---|---|---|
| **V0 (Gate)** | ADR-019 `proposed → accepted` (User-Freigabe); O1–O11 einsortiert | Entscheidung | — |
| **W1 (Fundament, seriell)** | **WP1** (Entität/Migration/RLS) → **WP2** (Service/Registry) | Backend, seriell | V0 |
| **W2 (Parallel nach W1)** | **WP3** (MCP+Manifest) ∥ **WP4** (REST) ∥ **WP5** (Produzent) | Backend | W1 |
| **W3 (nachgelagert)** | **WP6** (UI-Inbox) | Frontend | WP4, O6 |
| **durchlaufend** | **WP7** (Tests/Verifikation) | QS | begleitend; Abschluss nach WP5/WP6 |

**Kritischer Pfad:** WP1 → WP2 → WP5 → WP7. WP3/WP4 können nach WP2 parallel laufen. WP6 ist
bewusst die letzte Welle und blockiert das Backend-MVP nicht.

---

## 5. Risiken & Gegenmaßnahmen

| Risiko | Wirkung | Gegenmaßnahme |
|---|---|---|
| **Terminologie-Overload** (`Suggestion` vs. M1-`proposed` vs. `ReviewQueueService`) | zwei „Vorschlags"-Wahrheiten werden verwechselt | klare Abgrenzung im Code-Docstring; `ReviewQueueService` bleibt **die eine** Lese-Sicht (#1089), nur additiv erweitert; kein zweiter Pending-Endpoint |
| **Migration / RLS** (FORCE vergessen) | Cross-Tenant-Leak; CI rot | Policy-Muster `0097`/`0067` übernehmen; `test_rls_coverage.py` als Pflicht-Gate (statisch + `@_pg_only`) |
| **Doppel-Suggestion / harte Kollision** an `uq_tracelink_edge` | wiederholter Produzentenlauf scheitert hart | Kanten-Dedup nach O7 (Lookup vor `create`, neue Suggestion an bestehenden Proposal-Link hängen) |
| **Downstream-UI verwechselt Proposal-Quelle** | inkonsistente Anzeige | O6: Wiederverwendung der bestehenden Reviews-/Proposal-Ansicht statt Parallel-Fläche; additive Erweiterung |
| **Manifest-Drift** (neues Präfix `suggestion`) | `test_tool_manifest_drift.py` rot | Manifest-Regeneration (`manage.py export_tool_manifest`) im **selben** Arbeitspaket WP3 |
| **Payload-Injection / Provenienz-Fälschung** | injizierte Felder/Fremd-UUIDs beim Accept | Accept validiert ausschließlich über den delegierten Pfad; Provenienz **server-gesetzt**, nie aus Request-Body; kein `eval`/Blind-Merge (ADR Threat-Model) |
| **Atomarität (O11)** | verwaister Proposal-TraceLink, in der Inbox unsichtbar | `create_trace_link` + `Suggestion`-Insert in einer Transaktion (bzw. Suggestion zuerst); verwaiste Proposals ggf. in die Inbox aufnehmen |
| **Human-in-the-Loop-Bypass am REST-Trigger** | stiller ungestempelter Link | Produktions-Adapter fail-closed (`ProducerContextRequiredError` → 409), Human-REST-Trigger out of scope (001-09) |

---

## 6. Aufwandszusammenfassung

**Grob / qualitativ — von `effort-estimator` zu schärfen.** Keine belastbare Zahl in diesem
Dokument; sie wird hier bewusst nicht erfunden (ADR-019 lässt die Aufwandszahl ebenfalls offen).

| WP | Umfang (qualitativ) |
|---|---|
| WP1 | mittel — eine Tabelle + zwei Migrationen + RLS-Gate |
| WP2 | groß — Service + vier Adapter (nur einer aktiv) + Fehler-Taxonomie |
| WP3 | klein–mittel — drei MCP-Tools + Manifest-Regeneration |
| WP4 | mittel — drei REST-Endpunkte + RBAC/Fehler-Mapping |
| WP5 | mittel — Produzent verdrahten + Kanten-Dedup |
| WP6 | mittel — UI-Inbox + i18n + `data-testid` |
| WP7 | mittel — Verifikations-Suite querschnittlich |

**MVP-Gesamtumfang:** „eine neue Tabelle + Migration/RLS, ein Produzent, ein Accept-Adapter
(+ MCP-/REST-/Manifest-Folgepaket)" — deckungsgleich mit der ADR-Aufwandseinschätzung. Eine
belastbare PT-Zahl ist bei `effort-estimator` einzuholen.

---

## 7. Definition of Done (MVP)

Abgeleitet aus den Akzeptanzkriterien von **#1155** (Aspekt 2) und den testbaren Kern-Zusagen
ADR-019 §Entscheidung 7:

1. **Zusage 7(a):** Pro erfolgreicher Produzenten-Ausführung hinterlässt diese **genau eine**
   `open`-Suggestion mit tenant-korrektem Scope und vollständiger Provenienz.
2. **Zusage 7(b):** Accept ruft den bestehenden Mechanismus auf und setzt `status=accepted` +
   `decided_by`/`decided_at`; **kein** State-Übergang wird neu implementiert.
3. **Zusage 7(c):** Ein Agent-Accept auf den eigenen Vorschlag schlägt **fehl** (403/Validation), nicht still.
4. **Zusage 7(d):** `test_rls_coverage.py` und `test_tool_manifest_drift.py` sind **grün**.
5. **Zusage 7(e):** Reject setzt `status=rejected` und **zerstört kein** Ziel-Artefakt.
6. **Zusage 7(f):** Der Produktions-Adapter ist **fail-closed**: ein Nicht-Agent-/Nicht-API-Key-Kontext
   wird mit `ProducerContextRequiredError` (→ 409) abgewiesen — kein ungestempelter „Proposal"-Link,
   kein stiller Human-in-the-Loop-Bypass.
7. **#1155 Aspekt 2:** Der generische Pfad „Wissen → Vorschlag → Mensch bestätigt" ist über REST **und**
   MCP nachvollziehbar; die bestehende `ReviewQueueService`-Sicht bleibt die **eine** Queue (kein Duplikat).
8. **UI-Teil (WP6) separat:** Die Entität allein erfüllt das #1155-DoD nicht — die Vorschlags-Inbox ist
   als eigener, nachgelagerter Schritt Teil der Abnahme, nicht des Backend-MVP.

---

## 8. Offene Punkte / Entscheidungsbedarf

**Produkt-Input nötig (aus ADR-019 §Offene Punkte; hier nur geführt, nicht entschieden):**

- **O1** MVP-Produzenten-Scope (Empfehlung: ein Produzent).
- **O2** Langfrist-Rolle von `Suggestion` (Empfehlung: Kompositions-Schicht).
- **O3** `minimal`/`interview_default`-Semantik (Empfehlung: Schleife erlauben).
- **O4** Migration/Deprecation von `TraceLink.proposed_by`/`proposed_at` (**offen, nicht MVP**).
- **O5** MCP-Surface: neues Präfix `suggestion` vs. Fold in `review` (Empfehlung: neues Präfix + Manifest-Regeneration).
- **O6** UI-Inbox: eigene Seite vs. Eintrag in bestehende Review-/Pending-Ansicht (Empfehlung: bestehende Ansicht).
- **O7** Idempotenz/Dedup inkl. Kanten-Dedup `uq_tracelink_edge` (Empfehlung: Lookup vor `create`).
- **O8** Entitätstyp: eigene Tabelle vs. Generic-Artifact (**offen, MVP: eigene Tabelle**).
- **O9** Retention/GC für `rejected`/`superseded` (**offen**).
- **O10** M2-Proposal vs. Suggestion-only (Empfehlung/entschieden: M2-Proposal).
- **O11** Atomarität Proposal-Link ↔ Suggestion-Quittung (**offen, bei WP2 umzusetzen**).

**Zusätzlich zu klären:**

- **UI (O6):** Platzierung/Umfang der Vorschlags-Inbox, Wiederverwendung der bestehenden
  `ReviewsView`-„proposals"-Fläche, i18n-Texte — ist Bestandteil von WP6.
- **Verankerung des offenen Review-Befunds `003-01` (info):** HTTP-Status-Mapping `409` vs. `403`
  ist bei WP4/WP3 in der REST-/MCP-Fehler-Taxonomie zu fixieren (nicht blockierend).

**STOP-Gate bleibt gültig:** Ohne `proposed → accepted` (User-Freigabe) und ohne Klärung von
O1–O11 wird **kein** MVP implementiert — keine Migration, kein Modell, kein Tool, keine UI.

> **Ergänzung 2026-10-07:** Die **Restpfade außerhalb dieses MVP** (Human-Bearer-REST-Trigger,
> `#1095` `draft→proposed`, `#1197` async `suggest-links`, `#1196` Review-Massenfreigabe) sowie die
> Gesamt-Reihenfolge der Themen #1155/#1201/#1202/#1204 sind geordnet in
> [`2026-10-07-umsetzungsplaene-1155-1201-1202-1204.md`](2026-10-07-umsetzungsplaene-1155-1201-1202-1204.md)
> §1 bzw. §0. Dieser Plan bleibt unverändert gültig und wird nicht dupliziert.

---

*Erstellt am 2026-10-06 als reiner Umsetzungsplan zu ADR-019. Kein Produktcode, keine Migration,
keine Manifest-Änderung, kein Commit. Die Umsetzung startet erst nach `proposed → accepted`.*
