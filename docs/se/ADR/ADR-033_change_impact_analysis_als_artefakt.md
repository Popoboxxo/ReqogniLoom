---
adr_id: ADR-033
title: "Change-Impact-Analyse als persistiertes Artefakt und gemeinsame Workflow-Precondition"
status: proposed
date: "2026-11-28"
deciders: [orchestrator, user]
affected_reqs: [REQ-216, REQ-217, REQ-157, REQ-218]
superseded_by: null
---

# ADR-033: Change-Impact-Analyse als persistiertes Artefakt und gemeinsame Workflow-Precondition

## Kontext

Ein Change Request (CR) beantwortet heute „warum" gut, aber „was" und „was noch"
nur als Freitext (`impact_assessment`) plus eine flache Affected-Item-Liste.
`context.change_impact` liefert eine beratende Leseansicht für **ein** Artefakt:
read-only, ohne CR-Bezug, ohne Persistenz, ohne Freigabebezug. Im höchsten Rigor
fehlt ein prüfbarer Nachweis, und der Genehmiger muss den Kontext aus zehn Tools
selbst zusammensuchen.

Spec (`docs/superpowers/specs/2026-11-28-change-artefakt-wirkketten-design.md`,
§4.2, §4.5, §6) und Plan (`docs/superpowers/plans/2026-11-28-change-artefakt-
wirkketten.md`, S0/S3–S5) legen fest: die Analyse wird selbst zum Artefakt —
Lauf, Findings und Ketten werden gespeichert, über Inhalts-Fingerprints
reproduzierbar und im `extended`-Rigor als Gate durchgesetzt. Rahmen: kein neuer
Workflow-Zustand, keine automatische Genehmigung, keine Spaltenlöschung, keine
Breaking Change (REQ-157 gilt weiter, REQ-218 ist das Delta). Die Review-Matrix
(sechs Rollen, 2026-11-28) brachte B1–B13 ein: Gate-Bypass über alternative
Transition-Pfade (B1), Fingerprint-Blindheit (B2/B4), falscher Migrationsort (B6),
fail-open-Feature-Lookup (B7) und „human-only" als Authentisierungsaussage (B9).

**Leitentscheidung:** Das Change-Artefakt wird zum strukturierten Knoten. „Was
wird geändert" (Change Set) und „was ist davon betroffen" (Impact Set) werden
maschinenlesbar; Freitext bleibt die Begründung, nicht der Nachweis.

### Threat Model (4 Fragen)

1. **Was wird gebaut?** Persistierte Läufe/Findings/Ketten pro Tenant mit RLS und
   Workspace-Fence; Lesen ab Viewer, Dispositionen nur Approver/Admin und nur aus
   einer interaktiven Session. Eingaben sind Workspace-Artefakte (Titel,
   Beschreibungen, ICD-Parameter) und optional genau ein LLM-Aufruf.
2. **Was kann schiefgehen?** (a) Prompt-Injection über Artefakt-Titel oder
   CR-Text manipuliert `rationale`/Severity; (b) Tenant-/Workspace-Überlauf im
   Read oder Prompt; (c) XSS über Summary-/Rationale-Markdown; (d) Massen-
   `analyze_impact` per Agenten-Key als Kosten-DoS; (e) Freigabe auf veralteter
   oder unvollständiger Analyse.
3. **Was tun wir dagegen?** Severity entsteht deterministisch aus Gewicht,
   `coverage_relevant`, Hop-Distanz und `suspect`; das LLM liefert nur
   `rationale`, erzeugt keine IDs und ändert `severity` nicht. `impact_summary`
   ist Template-Interpolation ohne LLM; Modell-Eingaben sind auf Typ, `uid` und
   Link-Typ minimiert. RLS **plus** explizite `tenant_id`-/`workspace_id`-Filter
   je Hop, Item-Level-Read pro Artefakt, fremder Workspace ⇒ `NOT_FOUND`;
   Markdown serverseitig sanitisiert; eigener DRF-Scope mit Tagescap
   (`CHANGE_IMPACT_RATE_LIMITED`). Root-Bindung, `gate_fingerprint` und
   `truncated`-Blockade verhindern Freigabe auf altem Stand.
4. **Konsequenz?** Ohne diese Maßnahmen drohen Fehlfreigaben in regulierten
   Umgebungen und ein Datenleck über Provider oder Zähler; die Analyse bleibt
   beratend, die Verantwortung beim menschlichen CCB.

## Alternativen

- **a) Freitext-Impact behalten, nur den Prompt verbessern.** Billigste Variante,
  aber nicht prüfbar, nicht auditierbar, nicht reproduzierbar — der Nachweis
  bliebe ein Narrativ. **Verworfen.**
- **b) Das LLM entscheidet die Impact-Menge.** Klingt plausibel, ist aber
  halluzinationsanfällig, nicht reproduzierbar und als Gate-Nachweis unbrauchbar.
  **Verworfen.**
- **c) `context.change_impact` read-only weiterverwenden, ohne Persistenz.**
  Kein Lauf, keine Ketten, keine Frischezusage, keine Gate-Evidenz. **Verworfen.**
- **d) Gate nur im `ChangeRequestService`.** Kürzester Weg, aber `/transitions/`,
  `review.approve`, `change_request.submit_for_review` und
  `artifact.bulk_transition` rufen `WorkflowFacade.transition` direkt auf und
  umgingen das Gate (Review-Blocker B1). **Verworfen.**
- **e) Deterministischer Graph + persistierter Lauf + menschliche Dispositionen,
  Gate als gemeinsame Workflow-Precondition.** Reproduzierbar, auditierbar, auf
  allen Pfaden durchsetzbar. **Gewählt.**

## Entscheidung

1. **Drei neue tenant-isolierte Tabellen** `ChangeImpactRun`,
   `ChangeImpactFinding`, `ChangeImpactChain` als `TenantScopedModel` mit
   RLS-Policy und expliziter `workspace_id`-Fence am Run; Finding und Chain
   filtern über `run__workspace_id`. Die Kette hat **keinen eigenen `run`-FK**
   (Lauf über `finding.run`); `gate_open` ist eine **abgeleitete Property, nie
   eine Spalte**; effektive Disposition je Kette: `chain.disposition ??
   finding.disposition`.
2. **Zwei Inhalts-Fingerprints.** `graph_fingerprint` = SHA-256 über Wurzeln,
   erreichbare Nachbarschaft, Kanten, Hierarchie-Kanten, Link-Katalog, effektive
   Policy und `algorithm_version` (voller Laufbeleg). `gate_fingerprint` =
   SHA-256 über Wurzeln plus **alle** `visited_node_ids` mit `(content_hash,
   workflow_state, lifecycle_status, suspect)` und deren inzidenten Kanten,
   Katalog und Policy — im Gate-Read in `O(frontier)` ohne Voll-Traversierung
   nachgerechnet. `content_hash` stammt aus `baseline.state_capture` und
   **schließt** `version` (Lock-Counter), `status`/`suspect` (separat gehasht)
   und `baseline` aus; die Baseline ist **nur Provenienz**. Capture-
   Vollständigkeit ist **fail-closed**: `len(states) != len(requested_ids)` oder
   leerer Hash/Workflow-State ⇒ Lauf `failed` bzw. Gate `CHANGE_IMPACT_STALE`,
   nie ein leerer Hash.
3. **Policy über den bestehenden `PreferenceKey`-Mechanismus** (`change_impact.*`,
   siehe unten). Ebenen: **`global` (tenant-weit) und `workspace`**; **kein
   `user`-Level**, weil es eine organisatorische Policy ist. Zahl-/Enum-Werte
   werden beim Auflösen **typisiert**, damit `"200"` und `200` nicht im
   Fingerprint driften. `ui_editor` bindet die Keys in die generische
   Settings-Section ein; deployment-weite Defaults bleiben env/Settings.
4. **Preset-Feature `structured_change_impact`** (minimal/standard `false`,
   `extended` `true`), als Modulkonstante in `FEATURE_KEYS` gepinnt. Das Gate
   nutzt einen **strikten Seam** (`is_feature_enabled_strict`), der bei
   Lookup-Fehler wirft; nicht auflösbar ⇒ Block mit
   `CHANGE_IMPACT_POLICY_UNAVAILABLE`. `standard` blockiert nicht und liefert
   keinen automatischen Hinweis.
5. **Das Gate ist eine gemeinsame Workflow-Precondition**, nicht nur eine
   Service-Prüfung: in `workflow/precondition_rules.py`, ausgeführt vom
   `TransitionValidator` für `item_type="ChangeRequest"`; SoD und
   Affected-Item-Check liegen in derselben Precondition. Drei explizite Marker
   selektieren die Kanten (`change_impact_gate`: genau eine,
   `change_impact_refresh`: null oder mehr, `change_set_freeze`: genau eine) —
   keine Rollen-/Zustands-Heuristik, kein hartcodierter Zustandsname. Eine
   Datenmigration markiert `draft → submitted` in allen bestehenden
   `ccb_approval`-Definitionen; die Invariante wird bei **jedem** Definitions-
   Write geprüft und im Gate-Read fail-closed validiert.
6. **Fence und Menschlichkeit.** Jeder Read und jeder Traversierungs-Hop prüft
   `tenant_id` und `Artifact.workspace_id` der CR; zusätzlich Item-Level-Read pro
   Artefakt (gesperrte Einträge werden ausgeblendet und als `item_hidden`
   gezählt, fremder Workspace ⇒ `NOT_FOUND`). „Human-only" ist eine
   **Authentisierungsaussage**: interaktive Bearer-Session, `ctx.api_key_id is
   None` — `actor_type="user"` genügt nicht. Disposition, Adopt und
   Truncation-Waiver sind deshalb **REST-only**; der Waiver verlangt zusätzlich
   eine OTP-Session und ist auf maximal 30 Tage gedeckelt. `force` ist
   ausschließlich Approver/Admin und rate-limitiert.
7. **Migrationsort ist `persistence/0158`** (CR-Modelle liegen seit
   `persistence/0071` + `application/0024` im `persistence`-State;
   `application/0041` wäre ungültig).
8. **Präzedenz der Gate-Prüfungen:** Rollen/SoD → `RUNNING` → `INCOMPLETE` →
   `MISSING`/`STALE` → `OPEN_FINDINGS` → Summary. Ein unberechtigter Aufrufer
   sieht `PERMISSION_DENIED` statt eines Impact-Fehlercodes.

## Konsequenzen

- Positiv: „Was ist betroffen" ist maschinenlesbar, reproduzierbar und
  auditierbar; die Analyse ist auf allen Transition-Pfaden durchgesetzt, nicht
  nur in einer Fassade; ein Kontext-Read ersetzt zehn Tool-Aufrufe; Freitext
  bleibt möglich, ist aber nicht mehr der Nachweis; `minimal`/`standard` bleiben
  unverändert nutzbar; keine Spaltenlöschung.
- Negativ: drei zusätzliche Tabellen mit Retention-, Watchdog- und RLS-Aufwand;
  ein Preset-Feature und sieben Policy-Keys; zwei Fingerprints, die bei
  Katalog-/Policy-Änderungen neu berechnet werden; ein bewusst blockierendes
  Gate, wenn die Policy nicht auflösbar ist; `truncated` blockiert im `extended`
  und kostet eine begründete Approver-Quittung; der LLM-Anteil bleibt ohne
  Wirkung auf die Gate-Severity.
- Offen (nicht blockierend): `blocking`-Kalibrierung aus Fixtures (S0.6,
  ≤ 20 %-Ziel), Retention-Feinschliff und die Messbasis (S0.3, siehe unten).

## Policy-Keys und Ebenen (S0.4)

Alle Keys liegen in `application/change_impact_policy.py`, registriert im
`ready()` der `application`-App (Muster `backend/traceability/apps.py:64-89`).
Ebenen für **jeden** Key: `global` (tenant-weit) und `workspace` (Override) —
**kein `user`-Level**; deployment-weite Defaults bleiben env/Settings.

| Key | Typ | Default | Zulässige Werte | Ebenen |
|---|---|---|---|---|
| `change_impact.trigger` | enum | `manual` | `manual`/`on_submit`/`on_write`/`scheduled` | global, workspace |
| `change_impact.schedule_interval_hours` | enum(int) | `24` | `6`/`12`/`24`/`168` | global, workspace |
| `change_impact.semantic_edges` | bool | `false` | `true`/`false` (nie blockierend) | global, workspace |
| `change_impact.llm_annotation` | bool | `false` | `true`/`false` (nur `rationale`) | global, workspace |
| `change_impact.max_depth` | enum(int) | `4` | `2`/`3`/`4`/`5`/`6` (Hard-Cap 6) | global, workspace |
| `change_impact.max_nodes` | enum(int) | `200` | `100`/`200`/`500` (Hard-Cap 500) | global, workspace |
| `change_impact.min_weight` | enum(decimal) | `0.05` | `0.01`/`0.05`/`0.1`/`0.2` | global, workspace |

Auflösung `workspace > global > Default`; `analyze_impact` und `impact_context`
nennen die effektive Policy **und ihre Quelle je Key**. Enum-/Zahlwerte werden
**typisiert** aufgelöst (enum → `int`/`Decimal`), damit `"200"` und `200` nicht im
Fingerprint driften. `max_paths_per_finding=3` ist bewusst **keine** Policy,
sondern eine Code-Konstante. Call-Parameter dürfen die Policy nur restriktiver
machen; Überschreitungen werden geklemmt und als `policy.clamped` gemeldet.

## Messbasis (S0.3)

**Status: offen (nicht gemessen).** Es wurden keine Zahlen erfunden.

- `docker compose --env-file .env -f deploy/docker-compose.yml ps` liefert für
  dieses Compose-Projekt **keinen laufenden Service** — der Dev-Stack dieses
  Checkouts läuft nicht.
- Der einzige erreichbare Backend-Container (`reqogniloom-backend-1`, Projekt
  `reqogniloom`) gehört zu einem **anderen Checkout** (Working Dir
  `/home/hermes/reqogniloom-qs`); seine Aggregat-Abfrage ergab nur Nullen (0 CRs,
  0 Affected Items, 0 Workspaces) und ist **keine Messbasis** für dieses
  Repository.
- CR-Anzahl, Ø Affected-Item-Zahl und Workspaces im `extended`-Rigor:
  `offen (nicht gemessen)`.

Nachzuholen auf einem befüllten Dev-Stack dieses Checkouts:

```bash
docker compose --env-file .env -f deploy/docker-compose.yml ps   # Backend "Up"?
docker exec -i reqogniloom-backend-1 python manage.py shell <<'PY'
from persistence.models import ChangeRequest as C, ChangeRequestAffectedItem as A, Workspace as W
print("cr", C.objects.count(), "items", A.objects.count(),
      "avg_items", round(A.objects.count() / max(C.objects.count(), 1), 2))
print("tiers", [w.get("tier") or w.get("name")
                for w in W.objects.values_list("preset", flat=True) if isinstance(w, dict)])
PY
```

Die Zahlen dienen der Cap-/`blocking`-Kalibrierung in S4 und ersetzen nicht die
Fixture-Kalibrierung aus S0.6.

## Statuswechsel

- 2026-11-28 — `proposed`: angelegt (S0.2); Review durch concept-reviewer steht aus.
