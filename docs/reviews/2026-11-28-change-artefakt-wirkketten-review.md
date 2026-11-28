# Review-Matrix: Change-Artefakt als Wirkketten-Knoten (2026-11-28)

**Gegenstand:**
- Spec `docs/superpowers/specs/2026-11-28-change-artefakt-wirkketten-design.md`
- Plan `docs/superpowers/plans/2026-11-28-change-artefakt-wirkketten.md`

**Modus:** Sechs unabhängige, read-only Reviews gegen den Arbeitsbaum
`main` `c5b55108`. Keine Datei wurde durch die Reviewer geändert.

| Reviewer | Verdikt | Blocker | Major | Minor/Info | Schwerpunkt |
|---|---|---:|---:|---:|---|
| concept-reviewer | REQUEST_CHANGES | 2 | 13 | 21 | Vollständigkeit, Best Practices, Threat Model, Planbarkeit |
| database-engineer | nicht freigabefähig | 3 | 13 | 21 | Modell, Constraints, RLS, Migration, Fingerprint |
| api-specialist | nicht freigabereif | 3 | 16 | 19 | REST/MCP-Vertrag, Fehlercodes, Payloads, Manifest |
| security-auditor | blockiert | 1 | 8 | 9 | Gate-Bypass, human-only, Workspace-/Item-Fence, LLM |
| backend-reviewer | nicht freigabefähig | 3 | 11 | 14 | Layer, Transaktionen, Gates, Races, Celery |
| ui-reviewer | nicht review-reif | 5 | 14 | 17 | Rollen, Zustände, Ketten, A11y, i18n |

## Konsolidierte Blocker und Auflösung

| # | Befund | Quelle(n) | Auflösung in Spec/Plan |
|---|---|---|---|
| B1 | Gate nur im `ChangeRequestService` ist über `/transitions/`, `review.approve`, `bulk_transition` umgehbar | Security B1 | **D12:** gemeinsame Workflow-Precondition (`workflow/precondition_rules.py`/`TransitionValidator`); Plan S5.2/S5.9 Entry-Point-Paritätstest |
| B2 | Fingerprint über gespeicherte Besuchsmenge ist blind für neue Kanten/Knoten | Backend B1, DB B2, Concept F-01 | **D15:** Content-Hash + Re-Traversierung der erreichbaren Nachbarschaft; Plan S4.4 |
| B3 | Wurzeln/Change Set nicht im Fingerprint; Vorab-Lauf kann Gate befriedigen | Backend B2, Concept F-01 | `root_item_ids`/`roots_source`/`gate_eligible`, Mengengleichheit mit Affected Items; Spec §4.3/§4.5, AC-19 |
| B4 | `Artifact.version` ist Lock-Counter, kein Inhaltsnachweis; Suspect-/Bulk-Updates unsichtbar | DB B3 | Content-Hash aus `baseline.state_capture`, Kanten mit `suspect_flagged_at`; **D15** |
| B5 | `set_affected_items` löscht/ersetzt und zerstört `origin`/`rationale`/`version_before` | Backend M6, DB B1, API M11 | Diff-basiertes Upsert + `update_affected_item`; Plan S3.3/S5.6, Test S3 |
| B6 | Migration in `application/0041` ist ungültig (CR-Modelle seit `persistence/0071` + `application/0024` im `persistence`-State) | Concept F-02, DB m1, Security m1 | **D18:** `persistence/0158` + RLS/Constraints; Plan S3.4 |
| B7 | Gate kann fail-open verschwinden (`PresetPolicyService` schluckt Fehler) | Backend M2 | Fail-closed, Key in `FEATURE_KEYS`, Feature-Key-Pin; Plan S5.1 |
| B8 | Idempotenz ohne DB-Anker → parallele Läufe | Backend M4, DB M8 | Partielle UNIQUE `(change_request, fingerprint) WHERE forced=false` + Advisory Lock; Plan S4.7 |
| B9 | „Human-only" blockt nur `actor_type="agent"`; User-/Relay-Key darf entscheiden | Security M1 | **D13:** interaktive Bearer-Session (`api_key_id is None`); Plan S5.6 |
| B10 | Fehlende Workspace-/Item-Fence (RLS nur Tenant) | Security M2/M8, DB M13 | **D17:** `workspace_id` am Run, Workspace-Check, Item-Level-Read, Hop-Fence; Spec §4.5/§4.7 |
| B11 | Audit-Daten im Viewer-Kontext (AUTHOR-Tier) | API B3, Security m7 | Audit-Sektion gated/leer + `audit_section_hidden`; Plan S2.6 |
| B12 | Fehlercode-Transport fehlt; MCP → `-32603`, REST → 500 | API B1/B2 | Exception-Subtypen + Registrierung in beiden Katalogen; alle Gate-Codes 409; Plan S5.3 |
| B13 | UI: Rollen-Widerspruch, UUID-Ketten, Route/Nav, Zustände, i18n | UI F-01/F-07/F-13/F-23/F-28 | Plan S6.2–S6.10 (Rollen-Gating, `uid`/`title` je Hop, `NavigationShell`, sechs Zustände, `changeRequests.*`-Test) |

## Weitere eingearbeitete Majors

- **`truncated` blockiert im `extended`** (Security M5, Concept F-18): D14,
  `CHANGE_IMPACT_INCOMPLETE` mit `reason="truncated"`.
- **Change Set ab `submitted` eingefroren; Re-Check bei `approved`**
  (Security M6): Spec §4.5.
- **LLM darf `severity` nicht ändern** (Concept F-07, Security M4): nur
  `rationale`; deterministische Gate-Severity.
- **`blocking`-Kalibrierung** (Concept F-08, O5): nicht pauschal Zieltyp;
  Fixture-Set + ≤ 20 %-Ziel vor G3.
- **Hierarchie-Union** (Concept F-10): `Requirement.parent`,
  `Document`/`WorkItem`, `ArchitectureElement.parent_id` über
  `tier_compute`.
- **Dispositions-Vererbung** (Concept F-05): per `(artifact_id, path_hash)`,
  `inherited_from_run_id`.
- **Threat Model + NFR** (Concept F-19/F-21): Spec §5.1/§5.2.
- **REQ-Traceability** (Concept F-28): neue REQs + REQ-157-Delta-CR, Plan S0.5.
- **Audit-/Coverage-Scope** (Backend M7, DB M4): gecachter Report,
  CR-Artefakt-Filter, Bulk-Lookups.
- **Watchdog/Retention** (DB M5/m12, Concept F-23): Heartbeat, Sweep,
  letzte 20 Läufe/TTL.
- **CheckConstraints** (DB M1): Enums, Wertebereiche, Notiz-/Override-Pflicht.
- **`impact_summary` read-only/deterministisch, Detail-only** (Concept F-06/F-20,
  DB M3): kein LLM, `summary_run_id`, kein Listen-Serializer.
- **Paging/Caps/`contract_version`/Warnungs-Enum** (API M2/M3, UI F-15):
  Spec §4.6/§4.7.
- **Policy als Ceiling** (API M9): Call-Parameter nur restriktiver,
  `policy.clamped`.
- **ETag/`expected_version`** (API M12, Concept F-26): 409 bei stale.
- **Markdown-Sanitizing** (Security m8, UI F-26): Plan S6.8.
- **LLM-Datenminimierung** (Security m9): nur Typ/`uid`/Link-Typ, keine
  Volltexte.

## Noch offen (nicht blockierend)

| ID | Punkt | Nächster Schritt |
|---|---|---|
| O2 | CR-Liste in v1? | Einstieg über Baseline/Rollback genügt; Liste später. |
| O4 | Semantische Edges blockierend? | Faktisch nein; Testfall bleibt. |
| O5 | `blocking`-Kalibrierung | Fixture-Set in S0.6, vor G3 schließen. |

## Runde 2 — Closure-Verifikation (2026-11-28)

Fünf fokussierte Re-Reviews (Konzept, DB, API, Security, UI) auf den
geänderten Abschnitten. Ergebnis:

| Reviewer | Geschlossen | Teilweise/offen | Neue Punkte |
|---|---:|---|---|
| Konzept | 7/10 | F-05, F-07 | Gate-Kante, Frische/Transaktion, `latest_run`/Summary, §5-LLM-Regel, Vererbungs-Bypass |
| DB | B1, M3, M6, M13, Migrationsort | B2/B3a, M1/M2/M5/M8/M10, m16 | Content-Hash enthielt `version`; Baseline-Link entwertet Lauf; `pending`-Watchdog; `tier_compute` ohne Document/WorkItem |
| API | M1, M14 | B1/B2/B3, M2–M5, M9, M11, M12, M15 | `_remap_workflow_exc`-Naht; `bulk_transition`-Envelope; Paging-Dialekt; `entity_id`/`revision`; `force`-Widerspruch |
| Security | M2, M8, m1, m3 | M1, M3, M5, M6, M7, M4 | Gate-Kante löst auf `submitted → under_review`; `truncated`-Waiver über Freitext; Freeze ohne Durchsetzung; `force`; Summary/Stats am Item-Filter vorbei; `_capture_states` fail-open |
| UI | F-23, F-26, F-29, F-09 | F-01, F-07, F-08, F-10, F-13, F-19/20/21, F-28 | Fehlende CR-Transition-UI; Zustands-/Warnungsmodell; A11y ohne AC/Axe; Drift-Badge ohne CR-Link |

### Eingearbeitete Runde-2-Korrekturen

- **Gate-Kante:** explizites `change_impact_gate`-Metafeld, Provisioning
  validiert genau eine Markierung; keine Rollen-Heuristik.
- **Frische:** `gate_fingerprint` über die gespeicherte Frontier + inzidente
  Kanten, kein Voll-Graph-Walk in der Transition; Content-Hash **ohne**
  `version`/`status`/`suspect`/`baseline`; Capture-Fehler fail-closed.
- **Summary:** `summary_run_id == latest_completed_run.id`, Regeneration am
  Laufende; nur Aggregate, sichtbare Projektion für Stats/Counts.
- **Baseline:** nicht im Fingerprint (Link bei Approval entwertet sonst).
- **Watchdog:** deckt `pending` **und** `running`; `pinned` schützt vor
  Retention.
- **Vererbung:** nur bei unveränderter Severity/`path_hash`; Feld an Finding
  **und** Kette.
- **Gate-Fehler:** `EC_CHANGE_IMPACT_*`-Remap, `map_tool_exception`-Reihenfolge,
  `bulk_transition` als `VALIDATION_ERROR` + `details.change_impact_code`.
- **Rollen:** `force` nur Approver/Admin; Disposition/Adopt/Waiver REST-only
  (MCP ist API-Key-only).
- **Freeze:** `CHANGE_SET_FROZEN` in allen Change-Set-Schreibpfaden;
  `approved → implemented` prüft erneut.
- **UI:** Transition-UI, Warnungs-/Zustandsmodell, A11y-AC/Axe-Route,
  Drift-Badge-Link, Hop-`uid`/`title`, `inherited_from_run_id` sichtbar,
  Copy-Map für alle Ablehnungen.

### Runde 3 — Entscheidungen und Restpunkte

**Entschieden:**
- **O2:** Change Request als eigener Typ in der Freigaben-Queue
  (`/reviews`), keine separate CR-Liste.
- **O5:** Fixtures **jetzt** in S0.6, Ziel ≤ 20 % `blocking`.
- **Finaler Pass:** durchgeführt; die fünf verbleibenden Widersprüche
  (MCP-Adopt vs. REST-only, Baseline im `graph_fingerprint`, fehlende
  Waiver-Spalten, Gate-/Refresh-/Freeze-Marker, Summary-Projektion) sind
  eingearbeitet.

**Security-Finalcheck (Runde 3) — eingearbeitet:**
- `gate_fingerprint` hasht jetzt für alle Frontier-Knoten `content_hash`,
  `workflow_state`, `lifecycle_status`, `suspect` (nicht nur IDs/Kanten).
- Capture-Vollständigkeit ist fail-closed (`len(states) == len(ids)`, kein
  leerer Workflow-State); `capture_states` überspringt fehlende Zeilen.
- `TransitionDefinitionDTO` wird um die drei Marker erweitert, inkl.
  Backfill-Migration und Invariante bei jedem Definitions-Write.
- Re-Check, SoD und Affected-Item-Check laufen in derselben Precondition,
  nicht mehr nur im Service.
- Fail-closed-Policy über `is_feature_enabled_strict()` +
  `CHANGE_IMPACT_POLICY_UNAVAILABLE`.
- Truncation-Waiver verlangt OTP, `by IS NULL` = nicht quittiert,
  `expires_at` max. 30 Tage.
- Rate-Limit um Workspace-Dimension ergänzt.

**Nur noch Kosmetik (nicht blockierend):**
doppelte Indizes, `revision`-Nullbarkeit, S4-Nummerierung,
`max_paths_per_finding` als Konstante.

## Nächster Schritt

G0 kann geschlossen werden; danach S1 (Smart Refinement) an den
Orchestrator.
